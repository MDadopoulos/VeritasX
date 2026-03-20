# Phase 5: A2A HTTP Server - Research

**Researched:** 2026-03-20
**Domain:** FastAPI HTTP server wrapping an existing LangChain agent; A2A schema confirmation; idempotency; async concurrency control; LangSmith tracing
**Confidence:** HIGH (FastAPI/uvicorn stack), MEDIUM (A2A schema — see findings), HIGH (LangSmith env var pattern)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Error handling
- Distinguish error types: 500 for internal crashes, 422 for invalid/unprocessable input, 504 for timeout — each with a short `reason` field explaining what failed
- Invalid request bodies (missing uid, wrong field types) → 422 with a custom error body matching the A2A error shape (not FastAPI's default Pydantic detail format)
- Agent "cannot determine" fallback (after two failed verifier attempts) → 200 with the literal fallback answer string — treated as a valid A2A response, not an error
- Error response body echoes `uid` only when it was parseable from the request; omit if the request was malformed before uid could be extracted

#### Idempotency store
- Reuse existing scratch/{uid}/answer.txt as the cache — if file exists and is non-empty, return cached answer without re-running agent
- Re-run if answer.txt is empty (indicates a prior run crashed mid-write); "cannot determine" counts as a valid cached answer and is returned as-is
- Log cache hits at INFO level: `"Returning cached answer for uid={uid}"` — useful for debugging repeated benchmark calls
- `?force=true` query param bypasses cache and re-runs the agent, overwriting scratch directory

#### Concurrency model
- Concurrent (async) request handling — FastAPI handles multiple requests simultaneously, each isolated by UID scratch directory
- Per-UID asyncio lock: if two requests arrive for the same UID simultaneously, first wins and runs; second waits for first to complete, then returns the now-cached answer
- `MAX_CONCURRENT_RUNS` env var controls maximum simultaneous agent runs (default: Claude's discretion)
- When all slots are full, incoming requests queue and wait indefinitely — no timeout on queue wait

#### Server config & startup
- New env vars: `SERVER_PORT` (default 8000), `SERVER_HOST` (default 0.0.0.0), `MAX_CONCURRENT_RUNS`
- Fail fast on startup: verify Vertex AI credentials and corpus directory exist before accepting any requests — clear error if missing
- `GET /health` endpoint returns dependency status: corpus file count, active model ID, credentials validity — not just a simple ping

### Claude's Discretion
- Default value for MAX_CONCURRENT_RUNS
- Exact A2A error body shape (will be informed by confirmed A2A schema from researcher)
- Server invocation pattern (`python server.py` vs `uvicorn src.server:app`) — researcher to confirm from AgentBeats spec

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

This phase wraps the existing `run_question(uid, question)` function behind a FastAPI HTTP layer. The agent itself is unchanged; the server adds HTTP transport, idempotency via scratch/answer.txt, per-UID asyncio locks, a global concurrency semaphore, startup validation, and LangSmith tracing wiring.

**Critical finding on A2A schema:** The officeqa_agentbeats reference implementation uses Google's `a2a-python` SDK with a full JSON-RPC protocol (`POST /v1/message:send`, `A2AStarletteApplication`, `DefaultRequestHandler`). However, this project's own design documents (PROJECT.md, REQUIREMENTS.md, CONTEXT.md) consistently specify a simpler custom schema: `POST /run` accepting `{uid, question}` and returning `{uid, answer}`. This project is NOT using the full A2A SDK — it is implementing a simplified A2A-compatible HTTP interface. The schema below is derived from the project's own documents and is the authoritative spec for this implementation.

**Primary recommendation:** Use FastAPI 0.115+ with `uvicorn src.server:app --host $HOST --port $PORT` invocation. The agent is blocking (synchronous), so wrap `run_question` with `asyncio.to_thread()` inside an `async def` endpoint to avoid blocking the event loop.

---

## A2A Schema: Confirmed (from project documents)

This is the confirmed schema for `POST /run` for this project. Source: REQUIREMENTS.md HTTP-01/HTTP-02, PROJECT.md, CONTEXT.md.

### Request Body

```json
{
  "uid":      "UID0001",
  "question": "What were total expenditures for U.S. national defense in 1940?"
}
```

| Field      | Type   | Required | Notes                                    |
|------------|--------|----------|------------------------------------------|
| `uid`      | string | YES      | Non-empty; used as scratch key           |
| `question` | string | YES      | The question text                        |

### Success Response (HTTP 200)

```json
{
  "uid":    "UID0001",
  "answer": "2,602"
}
```

| Field    | Type   | Notes                                         |
|----------|--------|-----------------------------------------------|
| `uid`    | string | Echoed from request                           |
| `answer` | string | Normalized answer string or "cannot determine: ..." |

### Error Responses

| HTTP Status | When | Body Shape |
|-------------|------|------------|
| 422 | Missing `uid` / `question`, wrong types | `{"uid": "...", "reason": "..."}` — omit `uid` if not parseable |
| 500 | Agent crash / unhandled exception | `{"uid": "...", "reason": "internal error: <msg>"}` |
| 504 | Agent timeout | `{"uid": "...", "reason": "agent timed out"}` |

**Note on 422:** Override FastAPI's default Pydantic validation handler to return the custom body shape instead of FastAPI's `{"detail": [...]}` format.

### Health Endpoint

```
GET /health
```

Response (HTTP 200):
```json
{
  "status":       "ok",
  "corpus_files": 697,
  "model_id":     "claude-sonnet-4-6",
  "credentials":  "ok"
}
```

**Confidence:** MEDIUM — derived from project documents, not from an external spec URL. The reference repo uses a different (full A2A SDK) protocol. This project chose to implement a simplified variant.

---

## Standard Stack

### Core

| Library    | Version  | Purpose                         | Why Standard |
|------------|----------|---------------------------------|--------------|
| fastapi    | 0.115+   | HTTP framework, Pydantic models | Industry standard for Python APIs; built-in Pydantic v2 |
| uvicorn    | 0.32+    | ASGI server                     | FastAPI's recommended production server |
| httpx      | 0.28.1   | Already installed; async test client | Needed for integration tests with ASGITransport |

### Supporting

| Library       | Version | Purpose                              | When to Use |
|---------------|---------|--------------------------------------|-------------|
| langsmith     | 0.7.20  | Already installed; LangSmith tracing | When LANGSMITH_API_KEY + LANGSMITH_PROJECT are set |
| pytest-anyio  | latest  | Async test support for httpx.AsyncClient | Required for `@pytest.mark.anyio` async test pattern |

### Alternatives Considered

| Instead of    | Could Use          | Tradeoff |
|---------------|--------------------|----------|
| uvicorn       | gunicorn+uvicorn   | gunicorn adds multi-process; overkill for single-instance benchmark |
| pytest-anyio  | pytest-asyncio     | Both work; anyio is what FastAPI's own async test docs show |

### Installation

```bash
pip install fastapi uvicorn[standard] pytest-anyio
```

Add to `workspace/requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
pytest-anyio
```

---

## Architecture Patterns

### Recommended Project Structure

```
workspace/
├── src/
│   ├── server.py          # FastAPI app, lifespan, POST /run, GET /health
│   └── agent.py           # Existing — run_question() called from server
├── tests/
│   ├── test_server.py     # Integration: 10 questions via httpx.AsyncClient
│   └── test_isolation.py  # State isolation: Q_N scratch has no Q_{N-1} content
└── requirements.txt       # Add fastapi, uvicorn, pytest-anyio
```

### Pattern 1: Lifespan for Startup Validation

Use FastAPI's `lifespan` context manager (not deprecated `@app.on_event`) to fail fast before accepting requests.

```python
# Source: https://fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
from fastapi import FastAPI

_app_state: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: validate credentials, corpus, create agent once
    from src.config import get_config
    from src.agent import create_agent
    from pathlib import Path

    cfg = get_config()  # raises RuntimeError if GOOGLE_CLOUD_PROJECT missing
    corpus_dir = cfg.corpus_dir
    if not corpus_dir.exists():
        raise RuntimeError(f"Corpus directory not found: {corpus_dir}")

    corpus_files = list(corpus_dir.glob("*.txt"))
    if not corpus_files:
        raise RuntimeError(f"Corpus directory empty: {corpus_dir}")

    _app_state["corpus_file_count"] = len(corpus_files)
    _app_state["model_id"] = cfg.model_id
    # Note: create_agent() is NOT called at startup — a fresh agent is created
    # per request (required for MemorySaver isolation per existing design)
    yield
    _app_state.clear()

app = FastAPI(lifespan=lifespan)
```

**Why NOT create one agent at startup:** `create_agent()` uses `MemorySaver` which must be fresh per question for state isolation (AGT-02). The agent factory is cheap; the LLM model object is what's expensive, but `get_model()` is also cheap (no network call until first invoke).

### Pattern 2: Per-UID Lock + Global Semaphore

Two concurrency controls:
1. `asyncio.Semaphore(MAX_CONCURRENT_RUNS)` — caps total simultaneous agent runs
2. `dict[str, asyncio.Lock]` — per-UID mutex to serialize duplicate-UID requests

```python
import asyncio
from collections import defaultdict

_uid_locks: dict[str, asyncio.Lock] = {}
_uid_locks_meta = asyncio.Lock()  # protects the dict itself

async def get_uid_lock(uid: str) -> asyncio.Lock:
    async with _uid_locks_meta:
        if uid not in _uid_locks:
            _uid_locks[uid] = asyncio.Lock()
        return _uid_locks[uid]
```

**Important:** Locks must be created in an async context (after the event loop starts). Do NOT create them at module level — create them lazily on first request or in lifespan.

**Global semaphore:**
```python
_run_semaphore: asyncio.Semaphore | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _run_semaphore
    max_runs = int(os.environ.get("MAX_CONCURRENT_RUNS", "4"))
    _run_semaphore = asyncio.Semaphore(max_runs)
    yield
```

**Recommended default for MAX_CONCURRENT_RUNS: 4.** Rationale: each agent run makes multiple Vertex AI API calls; Vertex AI has per-project rate limits. 4 concurrent runs is a reasonable default that won't saturate the API. Adjustable via env var.

### Pattern 3: Wrapping Synchronous run_question with asyncio.to_thread

`run_question()` is synchronous (blocking). In an `async def` endpoint, it must not block the event loop. Use `asyncio.to_thread()`:

```python
import asyncio

@app.post("/run")
async def run(body: RunRequest, force: bool = False):
    ...
    answer = await asyncio.to_thread(run_question, uid, body.question)
    ...
```

`asyncio.to_thread()` is available in Python 3.9+ and is the idiomatic way to run sync functions without blocking the event loop. It is equivalent to `loop.run_in_executor(None, fn, *args)` but with cleaner syntax.

### Pattern 4: Idempotency via answer.txt Cache

```python
from pathlib import Path

SCRATCH_ROOT = Path(__file__).parent.parent / "scratch"

def _get_cached_answer(uid: str) -> str | None:
    """Return cached answer if scratch/{uid}/answer.txt exists and is non-empty."""
    answer_file = SCRATCH_ROOT / uid / "answer.txt"
    if answer_file.exists():
        content = answer_file.read_text(encoding="utf-8").strip()
        if content:
            # answer.txt has at least 2 lines: answer string + rationale
            # Return only line 1 (the normalized answer)
            return content.splitlines()[0].strip()
    return None  # empty file = prior run crashed mid-write, re-run
```

**Cache logic:**
- `answer.txt` exists and non-empty → return cached (line 1 = answer string)
- `answer.txt` exists but empty → re-run (crash recovery)
- `answer.txt` does not exist → run normally
- `?force=true` → skip cache check, call `prepare_scratch(uid)` to wipe, then re-run

### Pattern 5: Override FastAPI Validation Error Handler

FastAPI's default 422 response is `{"detail": [...]}`. The locked decision requires a custom body matching the A2A error shape. Override with `exception_handler`:

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Try to extract uid from the raw body for the error response
    uid = None
    try:
        body = await request.json()
        uid = body.get("uid")
    except Exception:
        pass

    content = {"reason": "invalid request: missing or wrong-type fields"}
    if uid is not None:
        content["uid"] = uid

    return JSONResponse(status_code=422, content=content)
```

### Pattern 6: LangSmith Tracing via Environment Variables

LangSmith tracing with LangChain is automatic when env vars are set. No code change to `agent.py` required.

```python
# In server lifespan startup — set these BEFORE any LangChain imports run
# (or set in .env — dotenv load_dotenv() handles this)
# Required env vars:
#   LANGSMITH_TRACING=true
#   LANGSMITH_API_KEY=<key>
#   LANGSMITH_PROJECT=<project-name>
#   LANGSMITH_ENDPOINT=https://api.smith.langchain.com  (optional, this is default)
```

LangChain reads `LANGSMITH_TRACING` (or the older `LANGCHAIN_TRACING_V2`) at import time. When `true`, every LLM call and tool invocation is automatically traced. To associate traces with a question UID, set `LANGCHAIN_RUN_NAME` or use `langsmith.traceable` decorator — but for this project, the existing `thread_id=uid` in `agent.invoke(config={"configurable": {"thread_id": uid}})` already provides per-question grouping in LangSmith.

**Note on LANGSMITH_PROJECT:** Setting `LANGSMITH_PROJECT` routes all traces to that named project. If not set, LangSmith uses a default project.

### Pattern 7: Server Invocation

**Confirmed invocation style: `uvicorn src.server:app`**

The officeqa_agentbeats reference implementation uses `python main.py --host ... --port ...` (with argparse), but that approach is specific to the A2A SDK's `A2AStarletteApplication`. For a plain FastAPI app, the standard is:

```bash
# Development
uvicorn src.server:app --host 0.0.0.0 --port 8000 --reload

# Production / benchmark submission
uvicorn src.server:app --host $SERVER_HOST --port $SERVER_PORT
```

Alternatively, embed uvicorn in `server.py`:

```python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.server:app",
        host=os.environ.get("SERVER_HOST", "0.0.0.0"),
        port=int(os.environ.get("SERVER_PORT", "8000")),
    )
```

Then invoke with `python -m src.server` or `python workspace/src/server.py`. Both patterns are valid; embed-in-server is more convenient for the benchmark harness since it requires no separate uvicorn command knowledge.

**Recommendation:** Support BOTH — embed uvicorn in `server.py` for `python src/server.py` invocation, and ensure it also works as `uvicorn src.server:app` for development.

### Anti-Patterns to Avoid

- **Blocking event loop:** Never call `run_question()` directly in `async def` — always wrap with `asyncio.to_thread()`. A blocking call will freeze all concurrent requests.
- **Creating asyncio primitives at module level:** `asyncio.Semaphore` and `asyncio.Lock` must be created inside the running event loop. Create them in the `lifespan` function or lazily on first request.
- **Sharing one agent across requests:** `create_agent()` uses `MemorySaver`; sharing it would bleed state between questions. Create fresh per request.
- **FastAPI's default 422 format:** The locked decision requires a custom error body. Must override `RequestValidationError` handler.
- **Not reading answer.txt line 1:** The file has 2+ lines (answer + rationale). The HTTP response must return only line 1 (the normalized answer string).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ASGI server | Custom socket server | uvicorn | Production-grade, handles keep-alive, HTTP/1.1, graceful shutdown |
| Request/response validation | Manual dict parsing | FastAPI Pydantic models | Type safety, automatic docs, proper error codes |
| Async-safe thread offloading | `threading.Thread` + queue | `asyncio.to_thread()` | Integrates with event loop, proper exception propagation |
| Concurrency limiting | Custom queue + counter | `asyncio.Semaphore` | Correct async semantics, no busy-waiting |
| Integration test HTTP client | `requests` library | `httpx.AsyncClient` + `ASGITransport` | Tests the app in-process without a live server |

**Key insight:** The concurrency problem (per-UID locking + global cap) has non-obvious edge cases around lock lifecycle and event loop initialization. Use asyncio primitives, not threading primitives.

---

## Common Pitfalls

### Pitfall 1: asyncio Primitives Created Outside Event Loop

**What goes wrong:** `asyncio.Semaphore()` or `asyncio.Lock()` created at module import time will fail or behave incorrectly because they bind to the running event loop — which doesn't exist yet at import time in Python 3.10+.
**Why it happens:** Python 3.10 deprecated `asyncio.get_event_loop()` creating a new loop implicitly; primitives now must be created in a running loop.
**How to avoid:** Create semaphores and locks inside `lifespan()` (which runs in the event loop) or lazily inside `async def` functions.
**Warning signs:** `DeprecationWarning: There is no current event loop` at startup; or `RuntimeError: no running event loop`.

### Pitfall 2: Blocking event loop with run_question

**What goes wrong:** If `run_question()` is called directly in an `async def` endpoint (without `asyncio.to_thread`), the entire ASGI event loop blocks for the duration of the agent run (60–300 seconds). All other concurrent requests time out.
**Why it happens:** FastAPI runs async endpoints on the event loop; synchronous code without `await` blocks it.
**How to avoid:** Always `await asyncio.to_thread(run_question, uid, question)`.
**Warning signs:** Concurrent requests hang; server appears non-responsive during agent runs.

### Pitfall 3: answer.txt Multi-Line Format

**What goes wrong:** Returning the full `answer.txt` content as the `answer` field — includes the rationale line 2+.
**Why it happens:** `answer.txt` has format: `line 1 = normalized answer`, `line 2 = rationale`. The entire file content is returned instead of just line 1.
**How to avoid:** Always `content.splitlines()[0].strip()` when reading the cached answer.
**Warning signs:** Integration test assertions fail with `answer` containing newlines.

### Pitfall 4: Per-UID Lock Memory Leak

**What goes wrong:** `_uid_locks` dict grows unbounded as more UIDs are processed.
**Why it happens:** Locks are created per UID but never removed.
**How to avoid:** For a benchmark with known UID set this is acceptable. If needed, use `weakref.WeakValueDictionary` or an LRU cache for the lock dict. For this phase, accept unbounded growth — the benchmark runs a fixed question set.
**Warning signs:** Memory grows linearly with number of unique UIDs processed.

### Pitfall 5: prepare_scratch Wipes on Cache Hit

**What goes wrong:** The idempotency cache check (read answer.txt) is done BEFORE `prepare_scratch()`. If `force=false` and cache hits, `prepare_scratch()` must NOT be called (it would wipe the cached answer).
**Why it happens:** Control flow error — calling `prepare_scratch` unconditionally then checking the cache.
**How to avoid:** Check cache FIRST; only call `run_question` (which calls `prepare_scratch` internally) if cache miss or `force=true`. For `force=true`, call `prepare_scratch(uid)` explicitly before `run_question` OR just let `run_question` handle it (it calls `prepare_scratch` internally).

### Pitfall 6: LangSmith LANGCHAIN_TRACING_V2 vs LANGSMITH_TRACING

**What goes wrong:** Setting the old `LANGCHAIN_TRACING_V2=true` which is deprecated; or setting only `LANGSMITH_API_KEY` without `LANGSMITH_TRACING=true`, which leaves tracing disabled.
**Why it happens:** LangSmith changed env var names in SDK versions ≥0.1.0.
**How to avoid:** Use `LANGSMITH_TRACING=true` (current) as the activation flag. Both the old and new names are supported in langsmith 0.7.20, but document the current name.
**Warning signs:** Traces don't appear in LangSmith UI despite API key being set.

---

## Code Examples

### Complete POST /run endpoint skeleton

```python
# Source: FastAPI docs + project design decisions
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# --- Pydantic models ---

class RunRequest(BaseModel):
    uid: str
    question: str

class RunResponse(BaseModel):
    uid: str
    answer: str

# --- App state (populated in lifespan) ---
_app_state: dict = {}
_run_semaphore: asyncio.Semaphore | None = None
_uid_locks: dict[str, asyncio.Lock] = {}
_uid_locks_guard: asyncio.Lock | None = None

# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _run_semaphore, _uid_locks_guard
    from src.config import get_config

    cfg = get_config()  # raises RuntimeError if GOOGLE_CLOUD_PROJECT missing
    corpus_dir = cfg.corpus_dir
    if not corpus_dir.exists() or not list(corpus_dir.glob("*.txt")):
        raise RuntimeError(f"Corpus not found or empty: {corpus_dir}")

    max_runs = int(os.environ.get("MAX_CONCURRENT_RUNS", "4"))
    _run_semaphore = asyncio.Semaphore(max_runs)
    _uid_locks_guard = asyncio.Lock()

    _app_state["corpus_file_count"] = len(list(corpus_dir.glob("*.txt")))
    _app_state["model_id"] = cfg.model_id

    yield
    _app_state.clear()

app = FastAPI(lifespan=lifespan)

# --- Override 422 handler ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    uid = None
    try:
        body = await request.json()
        uid = body.get("uid") if isinstance(body, dict) else None
    except Exception:
        pass
    content = {"reason": "invalid request: missing or wrong-type fields"}
    if uid is not None:
        content["uid"] = str(uid)
    return JSONResponse(status_code=422, content=content)

# --- Endpoints ---

@app.get("/health")
async def health():
    from src.config import get_config
    cfg = get_config()
    return {
        "status": "ok",
        "corpus_files": _app_state.get("corpus_file_count", 0),
        "model_id": cfg.model_id,
        "credentials": "ok" if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") else "missing",
    }

@app.post("/run", response_model=RunResponse)
async def run(body: RunRequest, force: bool = Query(default=False)):
    uid = body.uid
    question = body.question

    # Per-UID lock
    async with _uid_locks_guard:
        if uid not in _uid_locks:
            _uid_locks[uid] = asyncio.Lock()
    uid_lock = _uid_locks[uid]

    async with uid_lock:
        # Idempotency: check cache unless force=true
        if not force:
            cached = _get_cached_answer(uid)
            if cached is not None:
                logger.info("Returning cached answer for uid=%s", uid)
                return RunResponse(uid=uid, answer=cached)

        # Acquire global semaphore (queues if MAX_CONCURRENT_RUNS reached)
        async with _run_semaphore:
            try:
                answer = await asyncio.to_thread(_run_and_get_answer, uid, question, force)
            except Exception as exc:
                raise  # let 500 handler deal with it

    return RunResponse(uid=uid, answer=answer)
```

### Integration test skeleton

```python
# Source: https://fastapi.tiangolo.com/advanced/async-tests/
import pytest
from httpx import ASGITransport, AsyncClient
from src.server import app

@pytest.mark.anyio
@pytest.mark.integration
async def test_post_run_returns_a2a_schema():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post("/run", json={"uid": "UID0001", "question": "..."})
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"uid", "answer"}
    assert data["uid"] == "UID0001"
    assert isinstance(data["answer"], str) and len(data["answer"]) > 0
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` context manager | FastAPI 0.93 (2023) | `on_event` is deprecated; lifespan is the official pattern |
| `LANGCHAIN_TRACING_V2=true` | `LANGSMITH_TRACING=true` | langsmith SDK ≥0.1.0 (2024) | Both still work in langsmith 0.7.20 but document current name |
| `loop.run_in_executor(None, fn)` | `asyncio.to_thread(fn, *args)` | Python 3.9 (2020) | to_thread is cleaner; both work |
| `TestClient` (sync) | `httpx.AsyncClient` + `ASGITransport` | FastAPI async tests docs | Required when test code is async (e.g., uses `await`) |

**Deprecated/outdated:**
- `@app.on_event("startup")` / `@app.on_event("shutdown")`: Works but deprecated since FastAPI 0.93. Use `lifespan`.
- `LANGCHAIN_TRACING_V2`: Legacy name. Use `LANGSMITH_TRACING` for new setups.

---

## Open Questions

1. **A2A schema: no external authoritative URL found**
   - What we know: The project's own documents (REQUIREMENTS.md HTTP-02, PROJECT.md, CONTEXT.md) specify `POST /run` with `{uid, question}` → `{uid, answer}`. The officeqa_agentbeats reference repo uses the full Google A2A SDK (JSON-RPC, `A2AStarletteApplication`), which is a completely different protocol.
   - What's unclear: Whether the AgentBeats evaluation harness will call `POST /run` (as this project's docs assume) or use the full A2A JSON-RPC protocol.
   - Recommendation: Proceed with `POST /run` as specified in project documents. If the benchmark harness uses full A2A SDK, a migration would be needed — but that is out of scope for this phase.

2. **answer.txt line format after "cannot determine"**
   - What we know: Agent returns `"cannot determine: [issues list]"` as a single string. The system prompt says to write this to answer.txt.
   - What's unclear: Does the agent write "cannot determine: ..." as line 1 of answer.txt followed by a rationale line, or just the single string?
   - Recommendation: Check answer.txt line 1 only; strip; return as-is if it starts with "cannot determine". The locked decision confirms this is treated as a valid 200 response.

3. **LangSmith trace grouping by UID**
   - What we know: `LANGSMITH_TRACING=true` enables automatic tracing. The agent uses `thread_id=uid` as the LangGraph config key.
   - What's unclear: Whether `thread_id` automatically becomes the trace name in LangSmith, or whether an explicit `langsmith.traceable` wrapper with `run_name=uid` is needed.
   - Recommendation: Test empirically. If traces don't appear grouped by UID in LangSmith, add `os.environ["LANGCHAIN_RUN_NAME"] = uid` before each `run_question` call — but this is NOT thread-safe with concurrent requests. Use `langsmith.Context` for per-request trace naming if needed.

---

## Sources

### Primary (HIGH confidence)
- FastAPI official docs — lifespan events: https://fastapi.tiangolo.com/advanced/events/
- FastAPI official docs — async tests: https://fastapi.tiangolo.com/advanced/async-tests/
- Project documents: REQUIREMENTS.md, PROJECT.md, CONTEXT.md (for A2A schema spec)
- Existing codebase: `workspace/src/agent.py`, `workspace/src/scratch.py` (for integration constraints)

### Secondary (MEDIUM confidence)
- LangSmith tracing quickstart: https://docs.langchain.com/langsmith/observability-quickstart — env var names verified
- officeqa_agentbeats participant/src/server.py — confirmed full A2A SDK (not POST /run) is used by reference impl
- a2a-protocol.org/v0.3.0/specification — confirmed standard A2A uses JSON-RPC, not a simple POST /run

### Tertiary (LOW confidence)
- asyncio per-key lock dictionary pattern — described in multiple community sources but no single canonical reference

---

## Metadata

**Confidence breakdown:**
- Standard stack (FastAPI, uvicorn, httpx): HIGH — verified in official docs
- A2A request/response schema: MEDIUM — derived from project documents; no external canonical URL found; reference implementation uses a different protocol
- Architecture patterns (lifespan, semaphore, to_thread): HIGH — verified in FastAPI official docs
- LangSmith env vars: HIGH — verified in LangSmith official docs, langsmith 0.7.20 already installed
- Pitfalls: HIGH — derived from FastAPI docs + known Python async behavior

**Research date:** 2026-03-20
**Valid until:** 2026-04-20 (FastAPI 0.115 is stable; no expected breaking changes)
