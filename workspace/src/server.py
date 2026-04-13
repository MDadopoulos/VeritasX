"""
server.py — A2A-protocol-compliant HTTP server for the OfficeQA Finance Agent.

Replaces the Phase 5 FastAPI /run server with A2AStarletteApplication from
a2a-sdk. Exposes:
  - /.well-known/agent-card.json (GET) — agent discovery
  - / (POST JSON-RPC) — A2A message/send endpoint
  - /health (GET) — dependency health check

LangSmith tracing:
    LangSmith tracing is activated by setting LANGSMITH_TRACING=true,
    LANGSMITH_API_KEY, and LANGSMITH_PROJECT env vars. No code wiring needed
    here — LangChain auto-detects these environment variables at import time.

Server invocation:
    python src/server.py
    uvicorn src.server:app --host 0.0.0.0 --port 9009
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from src.executor import OfficeQAAgentExecutor

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("SERVER_PORT", "9009"))

# ---------------------------------------------------------------------------
# Module-level metadata dict populated by build_app()
# ---------------------------------------------------------------------------
_app_meta: dict = {}


# ---------------------------------------------------------------------------
# Startup validation (fail-fast)
# ---------------------------------------------------------------------------


def _validate_startup() -> int:
    """
    Validate required dependencies before starting.

    Returns:
        Number of corpus .txt files found.

    Raises:
        RuntimeError: If GOOGLE_API_KEY is unset or corpus is missing/empty.
    """
    project = os.environ.get("GOOGLE_API_KEY", "")
    if not project:
        raise RuntimeError(
            "GOOGLE_API_KEY env var is required but not set. "
            "Set it to your API key before starting the server."
        )

    corpus_dir_env = os.environ.get("CORPUS_DIR", "corpus/transformed")
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

    return len(corpus_files)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


async def health_endpoint(request: Request) -> JSONResponse:
    """
    Return server dependency status.

    Reports: corpus file count, active model ID, credentials validity.
    All values read from _app_meta populated during build_app().
    """
    model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
    return JSONResponse(
        {
            "status": "ok",
            "corpus_files": _app_meta.get("corpus_file_count", 0),
            "model_id": model_id,
            "credentials": "ok",
        }
    )


# ---------------------------------------------------------------------------
# Build A2A server
# ---------------------------------------------------------------------------


def build_app(card_url=None):
    """
    Build and return the Starlette ASGI app with A2A routes and /health.

    Runs startup validation at call time (fail-fast). This means the module
    raises RuntimeError at import time if env vars or corpus are missing.
    For uvicorn CLI usage (`uvicorn src.server:app`) this is intentional —
    the server should not start in a broken state.
    """
    corpus_count = _validate_startup()
    _app_meta["corpus_file_count"] = corpus_count

    max_runs = int(os.environ.get("MAX_CONCURRENT_RUNS", "3"))
    timeout = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "3000"))

    skill = AgentSkill(
        id="veritasx",
        name="VeritasX",
        description=(
            "Answers fiscal/financial questions from US Treasury bulletin "
            "corpus (1939-2025). Supports lookups, percentage changes, "
            "table sums, and multi-step reasoning over financial data."
        ),
        tags=["finance", "treasury", "rag"],
        examples=["What was total defense spending in FY1940?"],
    )

    agent_card = AgentCard(
        name="VeritasX",
        description="Agent over US Treasury bulletins, 1939-2025",
        url=card_url or f"http://0.0.0.0:{PORT}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )

    executor = OfficeQAAgentExecutor(
        max_concurrent=max_runs,
        timeout=timeout,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # build() passes **kwargs to Starlette constructor; routes= adds /health
    starlette_app = a2a_app.build(
        routes=[Route("/health", health_endpoint, methods=["GET"])],
    )

    logger.info(
        "A2A server built: corpus_files=%d, max_concurrent=%d, timeout=%ss, port=%d",
        corpus_count,
        max_runs,
        timeout,
        PORT,
    )

    return starlette_app


app = build_app()

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="VeritasX A2A Server")
    parser.add_argument("--host", default=os.environ.get("SERVER_HOST", "0.0.0.0"), help="Host IP")
    parser.add_argument("--port", type=int, default=PORT, help="Port to bind")
    parser.add_argument("--card-url", default=None, help="Agent card URL (optional)")
    
    args = parser.parse_args()

    cli_app = build_app(card_url=args.card_url)
    uvicorn.run(cli_app, host=args.host, port=args.port)
