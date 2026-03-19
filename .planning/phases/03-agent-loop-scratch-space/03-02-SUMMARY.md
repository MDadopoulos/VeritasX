---
phase: 03-agent-loop-scratch-space
plan: 02
subsystem: agent
tags: [deepagents, langchain-core, langgraph, system-prompt, retrieval-wrappers, run-question]

requires:
  - phase: 03-agent-loop-scratch-space
    plan: 01
    provides: "All 7 @tool-decorated StructuredTool instances, scratch.py lifecycle module"

provides:
  - "SYSTEM_PROMPT constant with planning gate, scratch file instructions, and tool usage rules"
  - "create_agent() factory wiring all 7 tools via create_deep_agent with FilesystemBackend + MemorySaver"
  - "run_question(uid, question, config) entry point with per-question scratch lifecycle"
  - "retrieval_wrappers.py with make_counted_route_files/make_counted_search_in_file factories (20-call limit)"

affects: [03-03, smoke-tests]

tech-stack:
  added:
    - deepagents.create_deep_agent
    - deepagents.backends.FilesystemBackend
    - langgraph.checkpoint.memory.MemorySaver
  patterns:
    - "Counter-wrapper closure pattern: make_counted_*() creates fresh {n:0} dict per call — counter resets per question naturally"
    - "Per-question fresh agent: run_question calls create_agent() each time — fresh MemorySaver + fresh counters"
    - "UID preamble injection: user message prefixed with 'Question UID: {uid}\nScratch directory: {uid}/'"
    - "Imports deferred to function body in create_agent/run_question — avoids module-level import side effects"

key-files:
  created:
    - workspace/src/agent.py
    - workspace/src/tools/retrieval_wrappers.py

key-decisions:
  - "retrieval_wrappers.py imports _route_files_agent (not _route_files_impl) and _search_in_file_impl directly — calls underlying fn, not StructuredTool"
  - "SYSTEM_PROMPT uses {uid} as a placeholder notation — actual UID injected via user message preamble in run_question, not baked into system prompt"
  - "SYSTEM_PROMPT does NOT reference verify_answer — that tool does not exist until Phase 4"
  - "FilesystemBackend(root_dir='./scratch', virtual_mode=False) — explicit virtual_mode=False per Pitfall 3"
  - "No module-level global agent instance — each run_question creates its own to guarantee AGT-02 idempotency"

patterns-established:
  - "Pattern: Counter-wrapper factory — call_count = {'n': 0}; @tool('name') inner fn increments and checks limit"
  - "Pattern: run_question lifecycle — prepare_scratch → create_agent → invoke with UID preamble → return last message content"

duration: recovered (files were complete from prior session, summary missing)
completed: 2026-03-19
---

# Phase 3 Plan 02: Agent Wiring + Retrieval Counter-Wrappers Summary

**agent.py and retrieval_wrappers.py complete — agent factory, system prompt, counter-wrappers, and run_question entry point all verified passing**

## Performance

- **Duration:** recovered (prior session had completed both files; only summary was missing)
- **Completed:** 2026-03-19
- **Tasks:** 2
- **Files created:** 2 (`workspace/src/agent.py`, `workspace/src/tools/retrieval_wrappers.py`)

## Accomplishments

- `SYSTEM_PROMPT` defined with mandatory planning gate (write_todos before retrieval), six scratch file format instructions, and tool usage rules (pct_change rule, RETRIEVAL_EXHAUSTED handling, "I cannot determine" fallback). No `verify_answer` reference.
- `RETRIEVAL_LIMIT = 20` module-level constant.
- `create_agent(config)` wires all 7 tools: `counted_rf`, `counted_sif`, `extract_table_block`, `calculate`, `pct_change`, `sum_values`, `normalize_answer` via `create_deep_agent` with `FilesystemBackend` and fresh `MemorySaver`.
- `run_question(uid, question, config)` orchestrates per-question lifecycle: `prepare_scratch → create_agent → invoke → return last message content`.
- `make_counted_route_files(limit)` and `make_counted_search_in_file(limit)` return fresh StructuredTool closures with independent call counters — reset per question because `create_agent` is called fresh each time.
- All 361 tests pass — no regressions.

## Verification Results

```
agent.py OK
retrieval_wrappers.py OK
361 passed, 3 deselected in 3.42s
```

All plan verification checks passed:
- `from src.agent import create_agent, run_question, SYSTEM_PROMPT, RETRIEVAL_LIMIT` — no errors
- `RETRIEVAL_LIMIT == 20` — confirmed
- SYSTEM_PROMPT contains: `write_todos`, `RETRIEVAL_EXHAUSTED`, `pct_change`, `evidence.txt`, `verification: pending` — confirmed
- SYSTEM_PROMPT does NOT contain: `verify_answer` — confirmed
- `from src.tools.retrieval_wrappers import make_counted_route_files, make_counted_search_in_file` — no errors

## Files Created

- `workspace/src/agent.py` — SYSTEM_PROMPT, RETRIEVAL_LIMIT, create_agent(), run_question() (192 lines)
- `workspace/src/tools/retrieval_wrappers.py` — make_counted_route_files(), make_counted_search_in_file() (107 lines)

## Deviations from Plan

None. Both files matched plan spec exactly:
- `_route_files_agent` used directly (not `.func` accessor) — correct since Plan 01 already created the thin wrapper
- `_search_in_file_impl` used directly — same pattern

## Next Phase Readiness

- `create_agent()` is the entry point for Plan 03 smoke tests
- `run_question(uid, question)` is the full end-to-end interface
- No blockers — ready to execute Plan 03

## Self-Check: PASSED

Files confirmed present and importable.
Tests: 361 passed.
