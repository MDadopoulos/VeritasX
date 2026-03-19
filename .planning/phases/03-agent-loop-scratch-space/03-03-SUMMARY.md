---
phase: 03-agent-loop-scratch-space
plan: 03
subsystem: agent
tags: [pytest, unit-tests, integration-tests, smoke-tests, scratch-lifecycle, agent-pipeline]

requires:
  - phase: 03-agent-loop-scratch-space
    plan: 02
    provides: "agent.py (run_question, create_agent, SYSTEM_PROMPT), retrieval_wrappers.py"

provides:
  - "test_scratch.py: 7 unit tests covering prepare_scratch and verify_scratch_complete"
  - "test_agent.py: 5 integration smoke tests covering all Phase 3 success criteria"
  - "run_question_with_messages() helper in agent.py for message-ordering assertions"

affects: [04-verifier-subagent, smoke-test-baseline]

tech-stack:
  added:
    - pytest.mark.integration (skip pattern for Vertex AI tests)
    - pytest.mark.timeout (registered in pytest.ini)
  patterns:
    - "monkeypatch SCRATCH_ROOT to tmp_path for unit test isolation"
    - "requires_vertex skipif marker for conditional integration test execution"
    - "run_question_with_messages() returns dict with answer + messages list"
    - "ToolMessage ordering assertion via isinstance + getattr name check"

key-files:
  created:
    - workspace/tests/test_scratch.py
    - workspace/tests/test_agent.py
  modified:
    - workspace/src/agent.py
    - workspace/pytest.ini

key-decisions:
  - "run_question_with_messages() added to agent.py to expose message list without breaking existing run_question signature"
  - "Q1=UID0002 (simple lookup), Q2=UID0004 (pct_change calculation), Q3=UID0003 (sum of monthly table values)"
  - "ToolMessage ordering test uses getattr(msg, 'name', None) — compatible with langchain_core ToolMessage.name attribute"
  - "timeout marker registered in pytest.ini to suppress PytestUnknownMarkWarning"
  - "test_smoke_rerun_idempotent asserts structural completeness, NOT answer equality (LLM non-determinism)"

duration: 7min
completed: 2026-03-19
status: awaiting-checkpoint (Task 3: human-verify)
---

# Phase 3 Plan 03: Scratch Lifecycle Tests + Agent Smoke Tests Summary

**7 unit tests for scratch lifecycle (all passing) and 5 integration smoke tests for the agent pipeline — awaiting human verification at Task 3 checkpoint**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-19T12:12:05Z
- **Completed (tasks 1-2):** 2026-03-19T12:18:53Z
- **Tasks completed:** 2 of 3 (Task 3 is checkpoint:human-verify)
- **Files created/modified:** 4

## Accomplishments

- `test_scratch.py` created with 7 unit tests covering `prepare_scratch` and `verify_scratch_complete` — all pass in 0.27s
- `test_agent.py` created with 5 integration smoke tests, all skipping with clear reason when `GOOGLE_CLOUD_PROJECT` not set
- `run_question_with_messages()` helper added to `agent.py` so test 5 can inspect `ToolMessage` ordering without breaking the existing `run_question` signature
- `pytest.ini` updated to register `timeout` marker, suppressing `PytestUnknownMarkWarning`
- Total non-integration test count: 368 passing (361 prior + 7 new scratch unit tests)

## Task Commits

1. **Task 1: Unit tests for scratch lifecycle** — `6cd1873` (test)
2. **Task 2: Integration smoke tests** — `8d57e8a` (test)

## Files Created/Modified

- `workspace/tests/test_scratch.py` — 7 unit tests (160 lines)
- `workspace/tests/test_agent.py` — 5 integration smoke tests (220 lines)
- `workspace/src/agent.py` — Added `run_question_with_messages()` helper (36 lines added)
- `workspace/pytest.ini` — Registered `timeout` marker

## Questions Selected for Integration Tests

| Role | UID | Type | Answer |
|------|-----|------|--------|
| Q1 (simple lookup) | UID0002 | VA expenditures FY1934, easy | 507 |
| Q2 (calculation) | UID0004 | Defense pct change 1940 vs 1953, hard | 1608.80% |
| Q3 (table) | UID0003 | Sum of 1953 defense monthly values, hard | 44,463 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] run_question_with_messages() helper needed for message-ordering test**
- **Found during:** Task 2 (writing test_smoke_write_todos_before_retrieval)
- **Issue:** `run_question()` only returns the answer string — test 5 needs the full `result["messages"]` list to assert ToolMessage ordering
- **Fix:** Added `run_question_with_messages(uid, question, config)` to `agent.py` that returns `{"answer": str, "messages": list}`. The plan explicitly anticipated this: "or refactor run_question to optionally return messages"
- **Files modified:** `workspace/src/agent.py`
- **Commit:** `8d57e8a` (Task 2)

**2. [Rule 1 - Bug] pytest.mark.timeout not registered — PytestUnknownMarkWarning**
- **Found during:** Task 2 (test collection)
- **Issue:** `@pytest.mark.timeout` warnings appeared in test output since marker was not registered
- **Fix:** Added `timeout` marker registration to `pytest.ini`
- **Files modified:** `workspace/pytest.ini`
- **Commit:** `8d57e8a` (Task 2)

## Awaiting

Task 3 checkpoint: human verification of agent trace and scratch output.
Requires Vertex AI credentials (`GOOGLE_CLOUD_PROJECT`) to run integration tests.

## Self-Check: PASSED

Files confirmed:
- `workspace/tests/test_scratch.py` — exists (7 tests, 368 passing)
- `workspace/tests/test_agent.py` — exists (5 integration tests, skip without credentials)
- `workspace/src/agent.py` — exists, contains `run_question_with_messages`

Commits confirmed:
- `6cd1873` — Task 1: test_scratch.py
- `8d57e8a` — Task 2: test_agent.py + agent.py helper + pytest.ini
