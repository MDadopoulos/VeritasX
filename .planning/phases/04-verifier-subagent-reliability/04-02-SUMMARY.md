---
phase: 04-verifier-subagent-reliability
plan: 02
subsystem: normalize-answer
tags: [verification, token-gate, bypass-prevention, function-signature]
dependency_graph:
  requires: []
  provides: [normalize_answer(raw, verification_token) with mandatory token gate]
  affects: [any caller of normalize_answer — must now pass verification_token]
tech_stack:
  added: []
  patterns: [mandatory parameter gate, ValueError for programming errors vs error-dict for runtime data errors]
key_files:
  created: []
  modified:
    - workspace/src/tools/normalize_answer.py
decisions:
  - "verification_token has no default value — Pydantic/JSON schema marks it required, LLM cannot omit it (Pitfall 2)"
  - "Falsy token raises ValueError (not error dict) — absent token is a programming error (bypass attempt), not a runtime data problem"
  - "Verification gate is first check in function body, before all other validation — cannot be bypassed by passing bad raw input first"
metrics:
  duration: "5 minutes"
  completed: "2026-03-20"
  tasks: 1
  files_modified: 1
  files_deleted: 0
---

# Phase 04 Plan 02: normalize_answer Verification Token Gate Summary

**One-liner:** Added mandatory `verification_token: str` parameter to `normalize_answer` with a falsy-check ValueError gate as the first operation, enforcing VER-04 at the function-signature level so verification cannot be bypassed by convention.

## What Was Built

Modified `workspace/src/tools/normalize_answer.py` to satisfy VER-04: no answer can be normalized without passing a non-null verification token from the verifier subagent.

### Changes to normalize_answer.py

**Signature change:** `normalize_answer(raw: str) -> dict` became `normalize_answer(raw: str, verification_token: str) -> dict`. The `verification_token` parameter has no default value, making it required in the Pydantic-generated JSON schema — the LLM cannot omit it when calling this tool.

**Verification gate (first check in body):**
```python
if not verification_token:
    raise ValueError(
        "normalize_answer requires a non-null verification_token from the verifier. "
        "Call task(subagent_type='verifier') first and pass its token."
    )
```
A `ValueError` is raised (not `{"error": ...}` dict) because an absent token is a programming error (bypass attempt), not a runtime data problem. This surfaces clearly in tests and logs.

**Module docstring:** Added "Requires a verification_token from the verifier subagent — raises ValueError if absent." to the header.

**Function docstring:** Added `verification_token` to the Parameters section with full description including sha256 hex prefix note.

**Existing logic:** All 8 normalization decision-tree branches (strip, list, unit word, dollar, date, percentage, decimal, integer) are completely unchanged.

## Verification Results

```
PASS 1: empty string raises ValueError
PASS 2: None raises ValueError
PASS 3: {'result': '19.14%'}
PASS 4: verification_token has no default value
PASS 5-branch ['[a, b]']: {'result': '[a, b]'}
PASS 5-branch ['5 million']: {'result': '5 million'}
PASS 5-branch ['$500']: {'result': '$500'}
PASS 5-branch ['January 2020']: {'result': 'January 2020'}
PASS 5-branch ['19.14%']: {'result': '19.14%'}
PASS 5-branch ['11.60']: {'result': '11.60'}
PASS 5-branch ['2,602']: {'result': '2,602'}
```

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash    | Description                                                       |
|---------|-------------------------------------------------------------------|
| f1b9e06 | feat(04-02): add verification_token gate to normalize_answer      |

## Self-Check: PASSED

- workspace/src/tools/normalize_answer.py: FOUND
- Commit f1b9e06: FOUND
- signature contains "verification_token: str": FOUND
- no default on verification_token: CONFIRMED (inspect.Parameter.empty)
- ValueError raised on falsy token: CONFIRMED
- gate is first check before input validation: CONFIRMED
- all 8 normalization branches unchanged: CONFIRMED
