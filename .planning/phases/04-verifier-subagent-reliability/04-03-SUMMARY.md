---
phase: 04-verifier-subagent-reliability
plan: 03
subsystem: tests-verifier-and-normalize
tags: [testing, verifier, normalize-answer, token-gate, era-resolver, unit-tests]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [test_verifier.py with 16 unit tests, test_agent.py Phase4-compatible, test_normalize_answer.py two-arg form]
  affects: [any future changes to verifier.py, normalize_answer.py]
tech_stack:
  added: []
  patterns: [pure Python unit tests no LLM, ast-based bulk token insertion, parametrized survey tests]
key_files:
  created:
    - workspace/tests/test_verifier.py
  modified:
    - workspace/tests/test_agent.py
    - workspace/tests/test_normalize_answer.py
decisions:
  - "test_verifier.py uses class-based grouping (TestGenerateToken, TestResolveEraColumnHeader, TestNormalizeAnswerTokenGate, TestVerifierSpec) for clarity and pytest output readability"
  - "test_smoke_verification_txt_is_stub renamed to test_smoke_verification_txt_has_records — checks for PASS/FAIL/Status:/Attempt indicators"
  - "test_normalize_answer.py updated via AST-based line-targeted replacement — handles comma-containing args correctly (list literals, dollar amounts, percentage strings)"
metrics:
  duration: "60 minutes"
  completed: "2026-03-20"
  tasks: 3
  files_modified: 3
  files_created: 1
---

# Phase 04 Plan 03: Verifier Test Suite + normalize_answer Migration Summary

**One-liner:** Created 16 pure-Python unit tests for verifier helpers (_generate_token, resolve_era_column_header, token gate) and migrated all 59 normalize_answer call sites to the mandatory two-arg form.

## What Was Built

### Task 1: test_verifier.py (NEW)

Created `workspace/tests/test_verifier.py` with 16 unit tests organized in four classes:

- **TestGenerateToken (3 tests):** Validates VER-03 — `_generate_token("19.14%")` returns 16-char lowercase hex matching `[0-9a-f]{16}`, same input always returns same token, different inputs return different tokens.

- **TestResolveEraColumnHeader (4 tests):** Validates VER-06 — exact match returns header, "National defense and associated activities" fuzzy-matches "National defense and related activities" (difflib default cutoff 0.6), completely unrelated string returns None, custom cutoff=0.9 rejects partial matches.

- **TestNormalizeAnswerTokenGate (5 tests):** Validates VER-04 — empty string raises `ValueError` matching "verification_token", None raises ValueError/TypeError, valid token allows normalization to proceed for percentage and integer-comma inputs, empty raw with valid token still returns `{"error": "INVALID_INPUT"}`.

- **TestVerifierSpec (4 tests):** Validates spec structure — all four required keys present, `name == "verifier"`, `calculate` function present in tools list by identity, `"{uid}"` not in system_prompt (Pitfall 3 — UID is extracted by LLM, not format-injected).

All 16 tests pass in 0.07s with no LLM calls.

### Task 2: test_agent.py (UPDATED)

- Renamed `test_smoke_verification_txt_is_stub` to `test_smoke_verification_txt_has_records`
- Replaced assertion checking for `"pending"` or `"phase 4"` (old stub content) with check for any of: `"PASS"`, `"FAIL"`, `"Status:"`, `"Attempt"` — real verification record indicators
- Updated module docstring point 4 from "stub content for Phase 4" to "real verification records from verifier subagent"
- All 6 integration tests remain in collection; test collection succeeds with no import errors

### Task 3: test_normalize_answer.py (UPDATED)

Updated all 59 `normalize_answer(x)` single-argument calls to `normalize_answer(x, "test_token")` two-arg form. Used AST-based line-targeted replacement (finding the exact closing paren by tracking bracket depth) to handle commas inside arguments correctly — naive regex `[^,)]+` failed on patterns like `normalize_answer("[0.096, -184.143]")` and `normalize_answer("2,602")`.

All 128 tests pass (parametrized survey tests + all 14 class-based test groups), including the critical `test_never_raises` loop which previously would have raised `TypeError` for every bad input (since `normalize_answer(bad_input)` with one arg now hits the gate check first, which expects two args).

## Verification Results

1. `python -m pytest tests/test_verifier.py -v` — 16 passed
2. `python -m pytest tests/test_agent.py --co -q -m integration` — 6 collected, `test_smoke_verification_txt_has_records` present, `test_smoke_verification_txt_is_stub` absent
3. `python -m pytest tests/test_normalize_answer.py -v` — 128 passed
4. AST verification: Total calls=59, Single-arg calls=0

## Deviations from Plan

**1. [Rule 3 - Blocking] AST-based replacement instead of manual editing**

- **Found during:** Task 3
- **Issue:** The plan described manual call-site-by-call-site updates across 14 test groups. A naive regex `normalize_answer([^,)]+)` failed to match 17 of 59 calls because many arguments contain commas (e.g., `normalize_answer("[0.096, -184.143]")`, `normalize_answer("March 3, 1977")`, `normalize_answer("2,602")`).
- **Fix:** Used Python AST to identify exact line numbers of single-arg calls, then applied a bracket-depth-tracking function to insert `', "test_token"'` before the exact closing paren on each line.
- **Files modified:** none beyond test_normalize_answer.py (the intended file)
- **Commit:** 167164f

## Commits

| Hash    | Description                                                                             |
|---------|-----------------------------------------------------------------------------------------|
| f843630 | test(04-03): create test_verifier.py with 16 unit tests for verifier helpers            |
| 138c051 | feat(04-03): update test_agent.py for Phase 4 verification protocol                     |
| 167164f | feat(04-03): update all 59 normalize_answer calls in test_normalize_answer.py           |

## Self-Check

Files exist:
- workspace/tests/test_verifier.py: FOUND
- workspace/tests/test_agent.py: FOUND (modified)
- workspace/tests/test_normalize_answer.py: FOUND (modified)

Commits exist:
- f843630: FOUND
- 138c051: FOUND
- 167164f: FOUND
