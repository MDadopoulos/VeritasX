# Phase 5: A2A HTTP Server - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Expose the existing agent as a single `POST /run` HTTP endpoint whose request/response schema exactly matches the AgentBeats A2A specification. Adds idempotency, concurrency isolation, LangSmith tracing wiring, and a health endpoint. No new agent capabilities — pure HTTP wrapper layer.

</domain>

<decisions>
## Implementation Decisions

### Error handling
- Distinguish error types: 500 for internal crashes, 422 for invalid/unprocessable input, 504 for timeout — each with a short `reason` field explaining what failed
- Invalid request bodies (missing uid, wrong field types) → 422 with a custom error body matching the A2A error shape (not FastAPI's default Pydantic detail format)
- Agent "cannot determine" fallback (after two failed verifier attempts) → 200 with the literal fallback answer string — treated as a valid A2A response, not an error
- Error response body echoes `uid` only when it was parseable from the request; omit if the request was malformed before uid could be extracted

### Idempotency store
- Reuse existing scratch/{uid}/answer.txt as the cache — if file exists and is non-empty, return cached answer without re-running agent
- Re-run if answer.txt is empty (indicates a prior run crashed mid-write); "cannot determine" counts as a valid cached answer and is returned as-is
- Log cache hits at INFO level: `"Returning cached answer for uid={uid}"` — useful for debugging repeated benchmark calls
- `?force=true` query param bypasses cache and re-runs the agent, overwriting scratch directory

### Concurrency model
- Concurrent (async) request handling — FastAPI handles multiple requests simultaneously, each isolated by UID scratch directory
- Per-UID asyncio lock: if two requests arrive for the same UID simultaneously, first wins and runs; second waits for first to complete, then returns the now-cached answer
- `MAX_CONCURRENT_RUNS` env var controls maximum simultaneous agent runs (default: Claude's discretion)
- When all slots are full, incoming requests queue and wait indefinitely — no timeout on queue wait

### Server config & startup
- New env vars: `SERVER_PORT` (default 8000), `SERVER_HOST` (default 0.0.0.0), `MAX_CONCURRENT_RUNS`
- Fail fast on startup: verify Vertex AI credentials and corpus directory exist before accepting any requests — clear error if missing
- `GET /health` endpoint returns dependency status: corpus file count, active model ID, credentials validity — not just a simple ping

### Claude's Discretion
- Default value for MAX_CONCURRENT_RUNS
- Exact A2A error body shape (will be informed by confirmed A2A schema from researcher)
- Server invocation pattern (`python server.py` vs `uvicorn src.server:app`) — researcher to confirm from AgentBeats spec

</decisions>

<specifics>
## Specific Ideas

- Researcher must confirm exact A2A request/response schema from AgentBeats GitHub (https://github.com/arnavsinghvi11/officeqa-leaderboard) and spec site before writing Pydantic models — this is a hard blocker for Plan 05-01
- Server invocation style should match whatever AgentBeats evaluation harness expects

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 05-a2a-http-server*
*Context gathered: 2026-03-20*
