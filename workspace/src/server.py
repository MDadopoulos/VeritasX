"""
server.py — FastAPI HTTP server wrapping the existing agent behind POST /run.

This module is the HTTP transport layer that makes the agent accessible to
the AgentBeats benchmark runner. No agent logic is changed here — this is
a pure wrapper adding HTTP transport, idempotency, concurrency control,
timeout enforcement, custom error handling, and health reporting.

LangSmith tracing:
    LangSmith tracing is activated by setting LANGSMITH_TRACING=true,
    LANGSMITH_API_KEY, and LANGSMITH_PROJECT env vars. No code wiring needed
    here — LangChain auto-detects these environment variables at import time.
    The agent already uses thread_id=uid in config, which maps to LangSmith
    session grouping. Set LANGSMITH_TRACING=true in .env to enable tracing.

Server invocation:
    python src/server.py                          # embedded uvicorn
    uvicorn src.server:app --host 0.0.0.0 --port 8000  # direct uvicorn CLI
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.schemas import HealthResponse, RunRequest, RunResponse

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level app state — populated during lifespan, read by endpoints.
# asyncio primitives (Semaphore, Lock) MUST NOT be created at module level.
# They are created inside lifespan() which runs inside the event loop.
# ---------------------------------------------------------------------------

_app_state: dict = {}
_uid_locks: dict[str, asyncio.Lock] = {}


# ---------------------------------------------------------------------------
# Lifespan — startup validation and resource initialization
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: validate credentials, corpus directory, create shared resources.
    Fail fast with RuntimeError if any required dependency is missing — do NOT
    start accepting requests in a broken state.
    """
    from src.model_adapter import get_model

    # --- Startup ---

    # Read configuration from environment
    max_runs = int(os.environ.get("MAX_CONCURRENT_RUNS", "4"))
    agent_timeout = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "300"))
    _app_state["agent_timeout"] = agent_timeout

    # Fail fast: GOOGLE_CLOUD_PROJECT must be set
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if not project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT env var is required but not set. "
            "Set it to your GCP project ID before starting the server."
        )

    # Fail fast: corpus directory must exist and contain at least one .txt file
    corpus_dir_env = os.environ.get("CORPUS_DIR", "corpus/transformed")
    # Resolve relative to workspace root (parent of src/)
    workspace_root = Path(__file__).parent.parent
    corpus_dir = Path(corpus_dir_env)
    if not corpus_dir.is_absolute():
        corpus_dir = workspace_root / corpus_dir_env

    if not corpus_dir.exists():
        raise RuntimeError(
            f"Corpus directory not found: {corpus_dir}. "
            "Set CORPUS_DIR env var to the correct path."
        )

    corpus_files = list(corpus_dir.glob("*.txt"))
    if not corpus_files:
        raise RuntimeError(
            f"Corpus directory is empty (no .txt files): {corpus_dir}. "
            "Ensure corpus files are present before starting the server."
        )

    _app_state["corpus_file_count"] = len(corpus_files)

    # Create LLM model once at startup (HTTP-01: expensive setup happens once,
    # not per-request). The agent graph is still created per-request via
    # create_agent() because MemorySaver requires per-invocation isolation,
    # but the underlying LLM object is shared here.
    model = get_model()
    _app_state["model"] = model

    # Extract model_id for health endpoint
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
    _app_state["model_id"] = model_id
    _app_state["credentials"] = "ok"

    # Create asyncio primitives inside the running event loop (Pitfall 1 avoidance)
    _app_state["semaphore"] = asyncio.Semaphore(max_runs)
    _app_state["uid_locks_guard"] = asyncio.Lock()

    logger.info(
        "Server started: corpus_files=%d, model_id=%s, max_concurrent=%d, timeout=%ss",
        len(corpus_files),
        model_id,
        max_runs,
        agent_timeout,
    )

    yield

    # --- Shutdown ---
    _app_state.clear()
    _uid_locks.clear()


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AgentBeats OfficeQA Agent",
    description="A2A-compatible HTTP server wrapping the OfficeQA finance agent.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Custom exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Override FastAPI's default 422 handler to return A2A error shape instead
    of the default {"detail": [...]} format.

    Per user decision: uid is included in the error body only when it was
    parseable from the request — omit entirely if request was malformed.
    """
    uid = None
    try:
        raw_body = await request.body()
        if raw_body:
            body_dict = json.loads(raw_body)
            if isinstance(body_dict, dict):
                uid = body_dict.get("uid")
                # Only include uid if it's a non-empty string
                if uid is not None and not isinstance(uid, str):
                    uid = None
                elif uid is not None and not uid:
                    uid = None
    except Exception:
        pass

    # Build error body — omit uid key entirely if not parseable
    content: dict = {"reason": "invalid request: missing or wrong-type fields"}
    if uid:
        content["uid"] = uid

    return JSONResponse(status_code=422, content=content)


# ---------------------------------------------------------------------------
# Helper: idempotency cache read
# ---------------------------------------------------------------------------


def _get_cached_answer(uid: str) -> str | None:
    """
    Return cached answer if scratch/{uid}/answer.txt exists and is non-empty.

    Per Pitfall 3: only line 1 of answer.txt is returned (the normalized
    answer string). Line 2+ contains the rationale.

    Returns:
        Cached answer string (line 1), or None if not cached or empty file.
    """
    from src.scratch import SCRATCH_ROOT

    answer_file = SCRATCH_ROOT / uid / "answer.txt"
    if answer_file.exists():
        content = answer_file.read_text(encoding="utf-8").strip()
        if content:
            return content.splitlines()[0].strip()
    return None


# ---------------------------------------------------------------------------
# POST /run endpoint
# ---------------------------------------------------------------------------


@app.post("/run", response_model=RunResponse)
async def run_endpoint(request: RunRequest, force: bool = Query(default=False)):
    """
    Run the agent for a given question UID.

    Idempotency: if scratch/{uid}/answer.txt exists and is non-empty and
    force=false, the cached answer is returned without re-running the agent.

    Concurrency: per-UID asyncio lock serializes duplicate-UID requests.
    Global semaphore (MAX_CONCURRENT_RUNS) caps total simultaneous agent runs.

    Timeout: agent runs with asyncio.wait_for(..., timeout=AGENT_TIMEOUT_SECONDS).
    Timeout returns 504. Other exceptions return 500.

    Query params:
        force: bool (default False) — bypass cache and re-run agent.
    """
    from src.agent import run_question

    uid = request.uid

    # Step 1: Fast-path idempotency check BEFORE acquiring any locks/semaphore
    # (Pitfall 5 avoidance: check cache first, only run if cache miss or force)
    if not force:
        cached = _get_cached_answer(uid)
        if cached is not None:
            logger.info("Returning cached answer for uid=%s", uid)
            return RunResponse(uid=uid, answer=cached)

    # Step 2: Acquire per-UID lock to serialize duplicate-UID concurrent requests
    uid_locks_guard: asyncio.Lock = _app_state["uid_locks_guard"]
    async with uid_locks_guard:
        if uid not in _uid_locks:
            _uid_locks[uid] = asyncio.Lock()
    uid_lock = _uid_locks[uid]

    async with uid_lock:
        # Step 3: Double-check cache inside the lock — another request for same
        # UID may have just completed and written answer.txt
        if not force:
            cached = _get_cached_answer(uid)
            if cached is not None:
                logger.info("Returning cached answer for uid=%s (post-lock check)", uid)
                return RunResponse(uid=uid, answer=cached)

        # Step 4: Acquire global semaphore slot (queues if MAX_CONCURRENT_RUNS reached)
        semaphore: asyncio.Semaphore = _app_state["semaphore"]
        agent_timeout: float = _app_state["agent_timeout"]

        async with semaphore:
            # Step 5: Run agent with timeout — wrap synchronous run_question in
            # asyncio.to_thread to avoid blocking event loop (Pitfall 2 avoidance).
            # asyncio.wait_for enforces AGENT_TIMEOUT_SECONDS timeout.
            try:
                answer = await asyncio.wait_for(
                    asyncio.to_thread(run_question, uid, request.question),
                    timeout=agent_timeout,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Agent timed out after %.0fs for uid=%s", agent_timeout, uid
                )
                return JSONResponse(
                    status_code=504,
                    content={"uid": uid, "reason": "agent timed out"},
                )
            except Exception as e:
                logger.error(
                    "Agent crashed for uid=%s: %s", uid, str(e), exc_info=True
                )
                return JSONResponse(
                    status_code=500,
                    content={"uid": uid, "reason": f"internal error: {str(e)}"},
                )

    # Step 6: Return A2A success response
    return RunResponse(uid=uid, answer=answer)


# ---------------------------------------------------------------------------
# GET /health endpoint
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_endpoint():
    """
    Return server dependency status.

    Reports: corpus file count, active model ID, credentials validity.
    All values are read from _app_state populated during lifespan startup.
    """
    return HealthResponse(
        status="ok",
        corpus_files=_app_state.get("corpus_file_count", 0),
        model_id=_app_state.get("model_id", "unknown"),
        credentials=_app_state.get("credentials", "unknown"),
    )


# ---------------------------------------------------------------------------
# Server invocation (embedded uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SERVER_PORT", "8000"))

    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
    )
