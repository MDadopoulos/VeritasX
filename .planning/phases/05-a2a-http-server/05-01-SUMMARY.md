---
phase: 05-a2a-http-server
plan: 01
subsystem: api
tags: [fastapi, uvicorn, pydantic, asyncio, a2a, http-server, concurrency, idempotency, langsmith]

# Dependency graph
requires:
  - phase: 04-verifier-subagent-reliability
    provides: run_question(uid, question) entry point, scratch/answer.txt lifecycle
  - phase: 03.1-architecture-refactor
    provides: get_model(), SCRATCH_ROOT, model_adapter pattern
provides:
  - FastAPI HTTP server exposing POST /run and GET /health (A2A-compatible)
  - workspace/src/schemas.py with RunRequest, RunResponse, ErrorResponse, HealthResponse
  - workspace/src/server.py with lifespan, concurrency control, idempotency, timeout
affects: [05-a2a-http-server, evaluation-pipeline, benchmark-submission]

# Tech tracking
tech-stack:
  added: [fastapi>=0.115, uvicorn[standard]>=0.32, pytest-anyio]
  patterns:
    - "FastAPI lifespan context manager for startup validation and resource init"
    - "asyncio.wait_for(asyncio.to_thread(sync_fn)) pattern for blocking-to-async wrapping"
    - "Per-UID asyncio.Lock + global asyncio.Semaphore for concurrency control"
    - "answer.txt idempotency cache with double-check inside UID lock"
    - "Custom RequestValidationError handler returning A2A error shape"

key-files:
  created:
    - workspace/src/schemas.py
    - workspace/src/server.py
  modified:
    - workspace/requirements.txt

key-decisions:
  - "asyncio primitives (Semaphore, Lock) created inside lifespan(), never at module level — avoids Python 3.10+ DeprecationWarning"
  - "get_model() called once in lifespan startup, stored in _app_state['model'] — LLM object shared across requests (HTTP-01)"
  - "Idempotency cache checked BEFORE acquiring UID lock and semaphore — avoids holding concurrency slots for cache hits"
  - "ErrorResponse uid field omitted entirely (not null) when uid not parseable from malformed request body"
  - "LangSmith tracing activated via env vars only (LANGSMITH_TRACING=true) — no code wiring in server.py"
  - "pytest-anyio installed for async integration test support (future test_server.py)"

patterns-established:
  - "Pattern: FastAPI lifespan with fail-fast startup validation before accepting requests"
  - "Pattern: asyncio.wait_for wrapping asyncio.to_thread for timeout-enforced sync-in-async execution"
  - "Pattern: Per-UID lock with guard lock for safe lazy creation of per-key locks"
  - "Pattern: Double-check cache inside UID lock after acquisition (concurrent same-UID serialization)"

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 5 Plan 01: A2A HTTP Server Summary

**FastAPI HTTP server wrapping run_question() behind POST /run with per-UID async locks, global semaphore, AGENT_TIMEOUT_SECONDS timeout (504), idempotency via scratch/answer.txt, and custom A2A error shapes for 422/500/504**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-20T17:51:08Z
- **Completed:** 2026-03-20T17:56:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `workspace/src/schemas.py` with 4 Pydantic V2 models: RunRequest, RunResponse, ErrorResponse, HealthResponse — all with `extra="forbid"` for A2A schema strictness
- Created `workspace/src/server.py` implementing the full FastAPI server: lifespan startup validation, POST /run with idempotency/concurrency/timeout, GET /health, custom 422 handler
- Updated `workspace/requirements.txt` with fastapi>=0.115, uvicorn[standard]>=0.32, pytest-anyio; installed in project venv

## Task Commits

Each task was committed atomically:

1. **Task 1: Pydantic A2A schema models and requirements update** - `9119399` (feat)
2. **Task 2: FastAPI server with POST /run, GET /health, concurrency, idempotency, timeout** - `2ed3182` (feat)

## Files Created/Modified

- `workspace/src/schemas.py` — Pydantic models: RunRequest (with model_validator), RunResponse, ErrorResponse (Optional uid), HealthResponse
- `workspace/src/server.py` — FastAPI app: lifespan, POST /run, GET /health, custom 422 handler, idempotency helper
- `workspace/requirements.txt` — Added fastapi>=0.115, uvicorn[standard]>=0.32, pytest-anyio

## Decisions Made

- **asyncio primitives in lifespan:** Semaphore and uid_locks_guard Lock are created inside `lifespan()` (in the running event loop), not at module level — avoids Python 3.10+ "no current event loop" DeprecationWarning
- **LLM model shared across requests:** `get_model()` called once in lifespan and stored in `_app_state["model"]` — satisfies HTTP-01 (expensive model/credentials setup happens once). Agent graph still created per-request via `create_agent()` because MemorySaver requires per-invocation isolation.
- **Cache check ordering:** Idempotency cache is checked BEFORE acquiring UID lock and semaphore (fast path), then double-checked inside the lock (race condition correctness). This avoids holding concurrency slots just to read a file.
- **ErrorResponse uid omission:** When a request is malformed, uid is omitted entirely from the 422 body (not set to null) — matches "Error response body echoes uid only when parseable" user decision
- **asyncio.wait_for placement:** Wraps `asyncio.to_thread(run_question, ...)` — the timeout applies to the entire synchronous agent run, not just the thread dispatch

## Deviations from Plan

None — plan executed exactly as written.

The only environmental deviation was that the project venv lacked pip — resolved by running `python -m ensurepip` to bootstrap pip into the existing venv before installing fastapi/uvicorn. This is a one-time setup action, not a code deviation.

## Issues Encountered

- Python 3.12 system interpreter had a corrupt pydantic_core installation — the project venv (`.venv/`) uses a separate Python 3.11 interpreter where pydantic works correctly. All verifications run through `.venv/Scripts/python.exe`.
- Project venv had no pip binary — resolved by bootstrapping with `python -m ensurepip` then using `python -m pip install`.

## User Setup Required

None — no external service configuration required beyond what was already established in Phase 1-4 (GOOGLE_CLOUD_PROJECT, MODEL_ID, etc.).

To run the server:
```bash
# From workspace/ directory with venv activated:
uvicorn src.server:app --host 0.0.0.0 --port 8000
# Or: python src/server.py
```

## Next Phase Readiness

- FastAPI server complete and importable: `from src.server import app`
- POST /run and GET /health verified working
- Server runnable via `uvicorn src.server:app` or `python src/server.py`
- Ready for Phase 5 Plan 02: integration tests (test_server.py) using httpx.AsyncClient + ASGITransport

---
*Phase: 05-a2a-http-server*
*Completed: 2026-03-20*
