---
phase: 02-extraction-calculation-core
plan: 02
subsystem: calculator
tags: [decimal, ast, arithmetic, pct_change, sum_values, financial-math]

requires:
  - phase: 01-environment-retrieval-foundation
    provides: project structure, pytest setup, error contract pattern established in search_in_file.py

provides:
  - calculate(): AST-whitelisted expression evaluator using Decimal with prec=28
  - pct_change(): percent change with unit mismatch detection, result rounded to 2dp
  - sum_values(): counted pair summation with heterogeneous unit warning
  - 59-test suite verifying all three functions against OfficeQA benchmark values

affects:
  - 02-extraction-calculation-core (other plans using calculate/pct_change/sum_values)
  - 03-agent-loop (calls these tools in answer pipeline)
  - 06-advanced-stats (builds on same Decimal/error-contract patterns)

tech-stack:
  added: []
  patterns:
    - "Error contract: all three functions return dict on both success and error, never raise"
    - "Decimal safety: Decimal(str(value)) at every entry point — never Decimal(float_value)"
    - "AST whitelist: frozenset of safe node types; type(node) not in SAFE_NODES triggers rejection"
    - "Unit normalization: lowercase + rstrip('s') converts plural/singular to common form"

key-files:
  created:
    - workspace/src/tools/calculate.py
    - workspace/tests/test_calculate.py
  modified: []

key-decisions:
  - "SAFE_NODES frozenset rejects Call, Attribute, Name, Import — only literal arithmetic permitted"
  - "pct_change unit check is skipped when either unit argument is None or empty string (unlabeled values pass through per CONTEXT decision)"
  - "sum_values warns (unit_warning field) on heterogeneous units but does not reject the sum"
  - "All numeric inputs converted via Decimal(str(value)) to prevent float contamination at the boundary"

patterns-established:
  - "Pattern: Decimal(str(v)) as the single numeric entry point — applied at every public function boundary"
  - "Pattern: frozenset SAFE_NODES + ast.walk whitelist check before any evaluation"
  - "Pattern: structured error dict with machine-readable 'error' key and human 'reason' key"

duration: 35min
completed: 2026-03-18
---

# Phase 2 Plan 02: Calculator Module Summary

**AST-safe arithmetic calculator with Decimal(prec=28) arithmetic — calculate(), pct_change(), sum_values() — backed by 59-test suite verifying UID0004 benchmark (1608.80%) and unit mismatch rejection**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-03-18T21:48:44Z
- **Completed:** 2026-03-18T22:24:00Z
- **Tasks:** 2 of 2
- **Files modified:** 2 created

## Accomplishments

- `calculate()` evaluates arithmetic expressions with SAFE_NODES whitelist — rejects `__import__`, function calls, attribute access, Name references; accepts only literals and +, -, *, /, **, % with parentheses
- `pct_change()` computes (new-old)/old*100 rounded to 2dp; handles all numeric input types via `Decimal(str(v))`; rejects unit mismatches (e.g., "millions" vs "billions") while allowing unlabeled inputs to pass through
- `sum_values()` enforces expected pair count, converts all values to Decimal, and adds `unit_warning` on heterogeneous unit labels without rejecting the sum
- 59-test suite covers basic arithmetic, operator precedence, Decimal precision (3.14*100 exact), UID0004 benchmark value (pct_change(2602, 44463) == 1608.80), unit mismatch/match cases, count mismatch with actual_count field

## Task Commits

1. **Task 1: AST calculator with Decimal arithmetic** - `02268b0` (feat)
2. **Task 2: Comprehensive calculator test suite** - `5f70a91` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `workspace/src/tools/calculate.py` — Three public functions: calculate, pct_change, sum_values; SAFE_NODES frozenset; _eval_node recursive evaluator; all Decimal, no float
- `workspace/tests/test_calculate.py` — 59 tests across 9 test classes; all assertions use Decimal comparisons

## Decisions Made

- Used `frozenset` for SAFE_NODES (faster membership testing, immutable by intent)
- Unit normalization uses `lower().rstrip('s')` — covers "million/millions/MILLION" uniformly
- `pct_change` empty string unit ("") treated as absent (same as None) per CONTEXT: unlabeled values pass through
- `_eval_node` returns error dict on division-by-zero and propagates it up via `isinstance(result, dict)` check — avoids raising in the middle of nested evaluation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cleared corrupt pytest plugin entry points to allow test runner to start**

- **Found during:** Task 2 verification
- **Issue:** Multiple venv packages (langsmith, anyio, pytest_asyncio, pytest_benchmark, pytest_codspeed, pytest_recording, pytest_socket, syrupy) had null-byte-only `.py` files — corrupted installation. Pytest's `load_setuptools_entrypoints("pytest11")` tried to load these plugins and Anaconda's `ast.py` crashed with `SyntaxError: source code string cannot contain null bytes` before any test file was reached.
- **Fix:** Cleared the `[pytest11]` section from the `entry_points.txt` of each corrupt package's dist-info directory. This prevents pluggy from discovering and attempting to load the broken plugins. The backed up originals are retained as `.bak` files. The packages themselves (langsmith, etc.) are unaffected — only the pytest plugin registration was removed.
- **Files modified:** `workspace/venv/Lib/site-packages/{anyio,pytest_asyncio,pytest_benchmark,pytest_codspeed,pytest_recording,pytest_socket,syrupy,langsmith}-*.dist-info/entry_points.txt`
- **Verification:** `pytest workspace/tests/test_calculate.py -v` runs and reports 59 passed
- **Committed in:** not committed (venv files are gitignored)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking environment issue)
**Impact on plan:** Fix was necessary to run tests at all. No scope creep. The test runner now works for all future test runs in this venv.

## Issues Encountered

- The workspace venv was created from Anaconda Python 3.11 base and inherits Anaconda's stdlib path. Multiple pytest plugin packages had entirely null-byte `.py` files (corrupted venv installation). Fixed by removing their pytest11 entry point registrations.

## Next Phase Readiness

- `calculate`, `pct_change`, `sum_values` are fully tested and ready for import by the agent loop (Phase 3)
- All three functions follow the error contract from Phase 1: return dict, never raise, never return None
- Phase 2 Plan 03 can import from `workspace.src.tools.calculate` without any additional setup

## Self-Check: PASSED

- workspace/src/tools/calculate.py: FOUND
- workspace/tests/test_calculate.py: FOUND
- Commit 02268b0 (calculate.py): FOUND
- Commit 5f70a91 (test_calculate.py): FOUND
- pytest test count: 59 passed, 0 failed

---
*Phase: 02-extraction-calculation-core*
*Completed: 2026-03-18*
