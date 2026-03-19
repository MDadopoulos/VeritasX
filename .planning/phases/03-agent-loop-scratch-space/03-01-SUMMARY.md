---
phase: 03-agent-loop-scratch-space
plan: 01
subsystem: agent
tags: [deepagents, langchain-core, langchain, langgraph, tool-decoration, scratch-directory]

requires:
  - phase: 02-extraction-calculation-core
    provides: "All 5 tool modules with public functions (route_files, search_in_file, extract_table_block, calculate, pct_change, sum_values, normalize_answer)"

provides:
  - "deepagents==0.4.11 installed with transitive deps (langchain==1.2.12, langgraph==1.1.3)"
  - "All 7 public tool functions decorated as @tool StructuredTool instances (via wrapper pattern)"
  - "scratch.py module: prepare_scratch(uid), verify_scratch_complete(uid), SCRATCH_FILES constant"

affects: [03-02, 03-03, agent-wiring, smoke-tests]

tech-stack:
  added:
    - deepagents==0.4.11
    - langchain==1.2.12
    - langgraph==1.1.3
    - langchain-anthropic==1.4.0
    - langchain_core.tools.tool (decorator)
  patterns:
    - "Wrapper pattern: original functions renamed _impl, StructuredTool alias at module bottom"
    - "route_files uses thin _route_files_agent wrapper to exclude config arg from schema"
    - "Tests for invalid-type inputs (None, int, list) call _impl directly to bypass Pydantic schema validation"
    - "Optional[str] type hints required for Pydantic to accept None in tool.invoke()"

key-files:
  created:
    - workspace/src/scratch.py
  modified:
    - workspace/requirements.txt
    - workspace/src/tools/route_files.py
    - workspace/src/tools/search_in_file.py
    - workspace/src/tools/extract_table_block.py
    - workspace/src/tools/calculate.py
    - workspace/src/tools/normalize_answer.py
    - workspace/tests/test_calculate.py
    - workspace/tests/test_route_files.py
    - workspace/tests/test_search_in_file.py
    - workspace/tests/test_extract_table_block.py
    - workspace/tests/test_normalize_answer.py

key-decisions:
  - "@tool(name='x') keyword-arg syntax is invalid in langchain_core 1.2.20; correct form is @tool('x') positional or tool('x')(fn)"
  - "Wrapper pattern chosen over direct @tool decoration: original _impl functions stay callable, StructuredTool aliases registered with agent"
  - "route_files: thin _route_files_agent wrapper created without config param — Config is TYPE_CHECKING import, causes NameError in Pydantic schema introspection"
  - "pct_change unit_old/unit_new must be typed Optional[str] not str=None for Pydantic to accept None in .invoke()"
  - "Tests calling tools with invalid types (None, int, list) updated to call _impl directly — StructuredTool Pydantic layer validates before function runs"
  - "classify_table_rows.py excluded from tool decoration — internal helper used by extract_table_block, not registered as agent tool"

patterns-established:
  - "Pattern: Tool wrapper at module bottom — def _func_impl(...): ... ; func = tool('func')(_func_impl)"
  - "Pattern: Single-arg tools invoked via .run(value), multi-arg tools via .invoke({...})"
  - "Pattern: scratch lifecycle — prepare_scratch(uid) before agent invocation, verify_scratch_complete(uid) after"

duration: 13min
completed: 2026-03-19
---

# Phase 3 Plan 01: Tool Decoration + Scratch Lifecycle Summary

**deepagents 0.4.11 installed, all 7 public tool functions wrapped as StructuredTool via @tool decorator, and scratch.py lifecycle module created — agent infrastructure foundation complete**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-19T11:31:39Z
- **Completed:** 2026-03-19T11:44:02Z
- **Tasks:** 2
- **Files modified:** 11 (6 tools + 5 tests + requirements + new scratch.py)

## Accomplishments

- deepagents==0.4.11 installed into workspace/.venv with langchain==1.2.12 and langgraph==1.1.3 as transitive dependencies
- All 7 public tool functions (`route_files`, `search_in_file`, `extract_table_block`, `calculate`, `pct_change`, `sum_values`, `normalize_answer`) are now `StructuredTool` instances with `.name` attribute — ready for `create_deep_agent` registration
- `classify_table_rows.py` explicitly left undecorated as an internal helper
- `scratch.py` module delivers `prepare_scratch(uid)`, `verify_scratch_complete(uid)`, `SCRATCH_ROOT`, and `SCRATCH_FILES` — satisfies SCR-01 (wipe-on-rerun) and SCR-02 (completeness check)
- All 361 existing tests continue to pass with updated call syntax

## Task Commits

1. **Task 1: Install deepagents and add @tool wrappers** — `48034a1` (feat)
2. **Task 2: Create scratch.py lifecycle module** — `7a4ca31` (feat)

## Files Created/Modified

- `workspace/requirements.txt` — Added `deepagents==0.4.11`
- `workspace/src/tools/calculate.py` — `_calculate_impl`, `_pct_change_impl`, `_sum_values_impl` + aliases; `Optional[str]` type hints for pct_change unit args
- `workspace/src/tools/route_files.py` — `_route_files_impl` + `_route_files_agent` thin wrapper (excludes Config from schema) + `route_files` alias
- `workspace/src/tools/search_in_file.py` — `_search_in_file_impl` + `search_in_file` alias
- `workspace/src/tools/extract_table_block.py` — `_extract_table_block_impl` + `extract_table_block` alias
- `workspace/src/tools/normalize_answer.py` — `_normalize_answer_impl` + `normalize_answer` alias
- `workspace/src/scratch.py` — Created with `prepare_scratch`, `verify_scratch_complete`, `SCRATCH_FILES`, `SCRATCH_ROOT`
- `workspace/tests/test_calculate.py` — Updated to `.run()` / `.invoke()` syntax; None/invalid-type tests use `_impl` directly
- `workspace/tests/test_route_files.py` — Integration tests updated to use `_route_files_impl(question, config)`
- `workspace/tests/test_search_in_file.py` — Updated to `search_in_file.invoke({...})`
- `workspace/tests/test_extract_table_block.py` — Updated to `extract_table_block.invoke({...})`
- `workspace/tests/test_normalize_answer.py` — Updated to `.run()`; None/invalid-type tests use `_normalize_answer_impl`

## Decisions Made

- `@tool('name')(fn)` wrapper pattern chosen over direct `@tool` decoration — allows original `_impl` functions to remain callable for internal use and preserves backward compat for test patterns that need raw callables
- `route_files` needs a thin wrapper without the `config` parameter — `Config` is under `TYPE_CHECKING` guard and causes `NameError` during Pydantic schema introspection at import time
- `pct_change` `unit_old`/`unit_new` parameters typed as `Optional[str]` (not `str = None`) — Pydantic V2 requires explicit `Optional` to accept `None` in `.invoke()` calls
- Tests that test invalid-type input handling (None, int, list, float) updated to call `_impl` directly — the StructuredTool Pydantic layer validates before function, so the function's own `INVALID_INPUT` error dict is never reached via `.run(None)`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] @tool keyword argument syntax invalid in langchain_core 1.2.20**
- **Found during:** Task 1 (go/no-go gate on calculate.py)
- **Issue:** `@tool(name="calculate")` raises `TypeError: tool() got an unexpected keyword argument 'name'`. The `name` argument must be positional: `tool("calculate")(fn)`.
- **Fix:** Switched from `@tool(name=...)` to `tool("name")(fn)` wrapper pattern throughout all modules.
- **Files modified:** All 5 tool modules
- **Verification:** `calculate.name == 'calculate'` confirmed for all 7 tools
- **Committed in:** `48034a1` (Task 1)

**2. [Rule 1 - Bug] StructuredTool not directly callable with positional args**
- **Found during:** Task 1 (go/no-go gate results)
- **Issue:** `calculate("2 + 3")` raises `TypeError: 'StructuredTool' object is not callable`. Tests use positional args.
- **Fix:** Renamed original functions to `_impl` variants; StructuredTool aliases take the public names. Updated all test call sites to `.run(arg)` for single-arg tools and `.invoke({...})` for multi-arg tools. Tests needing invalid-type inputs (None, int, list) call `_impl` directly.
- **Files modified:** All 5 tool modules + 5 test files
- **Verification:** 361 tests pass
- **Committed in:** `48034a1` (Task 1)

**3. [Rule 3 - Blocking] Config forward reference causes NameError in Pydantic schema introspection**
- **Found during:** Task 1 (route_files tool alias creation)
- **Issue:** `tool("route_files")(_route_files_impl)` fails at import with `NameError: name 'Config' is not defined` — the `config: "Config | None"` type hint string is evaluated during schema creation, but `Config` is only imported under `TYPE_CHECKING`.
- **Fix:** Created `_route_files_agent(question: str)` thin wrapper that calls `_route_files_impl(question)` without the config parameter. The StructuredTool is built from this wrapper.
- **Files modified:** `workspace/src/tools/route_files.py`, `workspace/tests/test_route_files.py`
- **Verification:** Import succeeds, `route_files.name == 'route_files'` confirmed
- **Committed in:** `48034a1` (Task 1)

**4. [Rule 1 - Bug] Optional[str] required for pct_change unit params to accept None in .invoke()**
- **Found during:** Task 1 (test suite run)
- **Issue:** Pydantic V2 rejects `None` for `str = None` typed params. `pct_change.invoke({"old": 100, "new": 200, "unit_old": None})` raises `ValidationError: Input should be a valid string`.
- **Fix:** Changed `unit_old: str = None` and `unit_new: str = None` to `unit_old: Optional[str] = None` and `unit_new: Optional[str] = None` in `_pct_change_impl`.
- **Files modified:** `workspace/src/tools/calculate.py`
- **Verification:** Tests for `unit_old=None` pass (2 tests updated to call `_pct_change_impl` directly for the None case)
- **Committed in:** `48034a1` (Task 1)

---

**Total deviations:** 4 auto-fixed (all Rule 1/3 — bugs and blocking issues)
**Impact on plan:** All deviations discovered during the plan's own go/no-go gate. The wrapper approach was anticipated by the plan as a fallback. No scope creep.

## Issues Encountered

- Pydantic V2's strict validation surfaces earlier than function-level validation — a known tradeoff when wrapping plain Python functions with StructuredTool. Handled by calling `_impl` directly in tests that specifically test type-error handling.

## Next Phase Readiness

- All 7 tools are StructuredTool instances ready to pass to `create_deep_agent(tools=[...])`
- `prepare_scratch(uid)` is the lifecycle entry point for Plan 02 (agent wiring)
- `verify_scratch_complete(uid)` is the exit check for Plan 03 (smoke tests)
- No blockers

## Self-Check: PASSED

Files confirmed:
- `workspace/src/scratch.py` — exists
- `workspace/src/tools/calculate.py` — exists, contains `calculate = tool("calculate")(_calculate_impl)`
- `workspace/src/tools/route_files.py` — exists, contains `route_files = tool("route_files")(_route_files_agent)`

Commits confirmed:
- `48034a1` — Task 1 commit
- `7a4ca31` — Task 2 commit

---
*Phase: 03-agent-loop-scratch-space*
*Completed: 2026-03-19*
