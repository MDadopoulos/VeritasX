---
phase: 02-extraction-calculation-core
verified: 2026-03-19T00:00:00Z
status: passed
score: 17/17 must-haves verified
re_verification: false
---

# Phase 2: Extraction + Calculation Core Verification Report

**Phase Goal:** The arithmetic pipeline produces exact, correctly-formatted answers from raw corpus text with no float rounding errors and no unit confusion
**Verified:** 2026-03-19
**Status:** passed
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | extract_table_block finds the first pipe-delimited table within 15 lines of an anchor phrase and returns the complete block | VERIFIED | range(i, i+max_lookahead) with startswith pipe check at lines 152-155; 1941_01 fixture returns 82 tables |
| 2 | Table output includes unit annotation lines and footnote rows, never truncated | VERIFIED | Backward walk at lines 51-63; unit_annotation confirmed against real corpus fixture |
| 3 | When multiple tables exist in the span, all are returned as separate list items | VERIFIED | while scan_pos loop at line 169; 1954_02 fixture returns 3 separate table dicts |
| 4 | classify_table_rows separates month rows, aggregate rows, and header rows into three buckets | VERIFIED | 25 month_rows, 26 aggregate_rows from 1954_02 fixture; three-bucket dict returned |
| 5 | Ambiguous rows like 1940 Total are classified as aggregate not month | VERIFIED | AGGREGATE_PATTERNS checked before MONTH_PATTERN at lines 148-155; test passes |
| 6 | Each classified row includes parsed numeric values extracted in the same pass | VERIFIED | parse_cell_value called per cell at lines 268, 286; values confirmed in live run |
| 7 | calculate evaluates arithmetic using decimal.Decimal prec=28 and permits only literals and safe operators via AST whitelist | VERIFIED | getcontext().prec=28 at line 17; SAFE_NODES frozenset lines 20-33; 3.14*100 returns Decimal(314.00) |
| 8 | Function calls, attribute access, imports are rejected with DISALLOWED_NODE error | VERIFIED | type(node) not in SAFE_NODES check at lines 113-118; Call, Attribute, Name absent from frozenset |
| 9 | pct_change computes (new-old)/old*100 and returns result rounded to 2 decimal places | VERIFIED | Line 175 formula; round(result, 2); pct_change(2602, 44463) returns Decimal(1608.80) matching UID0004 |
| 10 | sum_values accepts (label, value) pairs, rejects on count mismatch, warns on heterogeneous units | VERIFIED | COUNT_MISMATCH at lines 202-207; unit_warning at lines 230-231; 59 tests pass |
| 11 | Unit mismatch rejection works on explicit label conflicts only -- unlabeled values pass through | VERIFIED | Guard at line 160: both unit_old and unit_new must be non-None and non-empty before check runs |
| 12 | All numeric inputs convert internally to Decimal via str() | VERIFIED | Decimal(str(old)), Decimal(str(new)), Decimal(str(value)) at lines 154-155, 214 of calculate.py |
| 13 | normalize_answer is rule-based and formats raw calculator output to match benchmark answer format exactly | VERIFIED | 8-step decision tree; 128 tests pass; parametrized against 258 real benchmark answers from both CSVs |
| 14 | Decimals preserve trailing zeros: 11.60 stays 11.60 not 11.6 | VERIFIED | Step 7 returns cleaned string unchanged; live call confirms trailing zeros preserved |
| 15 | Percentages preserve original decimal places: 13.009% stays 13.009% | VERIFIED | Step 6 returns cleaned unchanged; live call confirms decimal places preserved |
| 16 | Unicode minus sign is normalized to ASCII minus | VERIFIED | cleaned = raw.strip().replace(unicode_minus, ASCII_minus) at line 67; live run: U+2212 507 returns -507 |
| 17 | Test suite asserts normalize(raw) == expected for every distinct format pattern from the survey | VERIFIED | 68 parametrized tests load all examples from format_survey.json (categories A-K + 6 edge cases); all pass |

**Score:** 17/17 truths verified

---

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Status |
|----------|-----------|--------------|--------|
| workspace/src/tools/extract_table_block.py | -- | 185 | VERIFIED |
| workspace/src/tools/classify_table_rows.py | -- | 300 | VERIFIED |
| workspace/src/tools/calculate.py | -- | 234 | VERIFIED |
| workspace/src/tools/normalize_answer.py | -- | 108 | VERIFIED |
| workspace/tests/test_extract_table_block.py | 80 | 370 | VERIFIED |
| workspace/tests/test_classify_table_rows.py | 80 | 447 | VERIFIED |
| workspace/tests/test_calculate.py | 120 | 391 | VERIFIED |
| workspace/tests/test_normalize_answer.py | 100 | 420 | VERIFIED |
| workspace/tests/fixtures/treasury_bulletin_1954_02.txt | -- | 125 | VERIFIED |
| workspace/tests/fixtures/format_survey.json | -- | 131 | VERIFIED |

All 10 artifacts: exist, are substantive (all exceed minimum line counts where specified), and are wired (imported and exercised by passing tests).

---

### Key Link Verification

| From | To | Via | Status | Detail |
|------|----|-----|--------|--------|
| extract_table_block.py | corpus text spans | startswith(pipe) detection + backward walk for unit annotation | WIRED | Lines 51-63 backward walk; lines 152-155 pipe detection; confirmed against real fixtures |
| classify_table_rows.py | extract_table_block.py output | MONTH_PATTERN, AGGREGATE_PATTERNS on table_text string | WIRED | Both patterns defined at module level; pipeline tested end-to-end with 1954_02 fixture |
| calculate.py | decimal.Decimal | Decimal(str(value)) at every numeric entry point | WIRED | 4 call sites confirmed: lines 47, 154, 155, 214; no Decimal(float) path anywhere |
| calculate.py | ast module | SAFE_NODES frozenset + ast.walk whitelist check | WIRED | SAFE_NODES at line 20; ast.walk(tree) at line 113; whitelist gate runs before any evaluation |
| normalize_answer.py | format_survey.json | Decision tree derived from survey categories A-K | WIRED | 68 parametrized tests load format_survey.json; all pass |
| test_normalize_answer.py | format_survey.json | load_survey() at module collection time | WIRED | FIXTURE path at line 16; loaded during pytest parametrize; all 68 cases verified |

---

### Anti-Patterns Found

None. All four source modules scanned for TODO/FIXME/XXX, empty implementations, placeholder comments, and stub handlers. None found.

---

### Test Results Summary

| Test File | Tests | Result |
|-----------|-------|--------|
| test_extract_table_block.py | 22 | All pass |
| test_classify_table_rows.py | 42 | All pass |
| test_calculate.py | 59 | All pass |
| test_normalize_answer.py | 128 | All pass |
| Phase 2 total | 251 | All pass |
| Full suite (Phase 1 + Phase 2) | 361 pass, 3 fail | 3 failures are Phase 1 live GCP/API credential tests -- unrelated to Phase 2 |

---

### Human Verification Required

None. All observable behaviors -- Decimal precision, AST node rejection, unit mismatch logic, normalizer pass-through, trailing-zero preservation -- are programmatically verified by the test suite against real corpus fixtures and real benchmark values.

---

## Summary

Phase 2 fully achieves its goal. The arithmetic pipeline:

1. Extracts complete table blocks (with unit annotations, footnotes, all rows) from raw corpus text via extract_table_block -- confirmed against real Treasury Bulletin fixtures producing correct unit_annotation and 25 classified month rows from the 1954_02 fixture.

2. Classifies rows into month/aggregate/header buckets with correct precedence (aggregate before month) and year inheritance, via classify_table_rows -- Decimal values throughout, no float.

3. Calculates exactly without float contamination: calculate(3.14 * 100) returns Decimal(314.00). The UID0004 benchmark value (pct_change(2602, 44463) = 1608.80) is reproduced exactly.

4. Rejects unit mismatches at the arithmetic boundary and warns on heterogeneous units without blocking valid sums.

5. Formats answers to exact benchmark format via normalize_answer: trailing zeros preserved, unicode minus normalized, commas preserved as-is -- verified parametrically against all 258 unique answers from both benchmark CSVs.

All 251 Phase 2 tests pass. No stubs, no placeholders, no float contamination paths.

---

_Verified: 2026-03-19_
_Verifier: Claude (gsd-verifier)_
