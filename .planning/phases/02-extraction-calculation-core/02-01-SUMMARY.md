---
phase: 02-extraction-calculation-core
plan: 01
subsystem: extraction
tags: [pipe-delimited-tables, corpus-parsing, regex, decimal, row-classification]

# Dependency graph
requires:
  - phase: 01-environment-retrieval-foundation
    provides: "search_in_file returns span_text strings containing corpus tables"
provides:
  - "extract_table_block: extracts complete table blocks (prose context, unit annotation, table body, footnotes) from corpus spans"
  - "classify_table_rows: separates table rows into month_rows, aggregate_rows, header_rows with parsed Decimal values"
  - "parse_cell_value: module-level helper for corpus cell parsing (commas, footnote suffixes, parens negatives)"
  - "treasury_bulletin_1954_02.txt: real corpus fixture with monthly rows and year inheritance"
affects: ["02-02-calculation-core", "03-agent-loop", "04-verification-gate"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern: structured error dicts with machine-readable codes (INVALID_INPUT, NO_TABLE_FOUND)"
    - "Pattern: backward walk from first pipe row to capture unit annotation up to 4 lines back"
    - "Pattern: aggregate detection before month detection (higher specificity) to prevent total rows entering month bucket"
    - "Pattern: year inheritance — YYYY-MonthName row propagates year to subsequent bare-month rows"

key-files:
  created:
    - workspace/src/tools/extract_table_block.py
    - workspace/src/tools/classify_table_rows.py
    - workspace/tests/test_extract_table_block.py
    - workspace/tests/test_classify_table_rows.py
    - workspace/tests/fixtures/treasury_bulletin_1954_02.txt
  modified:
    - workspace/pytest.ini

key-decisions:
  - "Aggregate detection applied FIRST (higher specificity) — prevents 1940 Total, Cal. yr, cumulative rows from landing in month bucket"
  - "parse_cell_value is module-level (not private) — will be reused by Phase 3 calculator"
  - "pytest.ini: added -p no:anyio -p no:asyncio etc. to suppress broken Anaconda plugin entrypoints in this venv"
  - "15-line lookahead is a half-open range: range(anchor_idx, anchor_idx + 15) — anchor included in window"
  - "Rows before | --- | separator always classified as header_rows regardless of content"

patterns-established:
  - "Pattern 1: All tools return dict (success or error) — never raise, never return None"
  - "Pattern 2: Input validation at top of every public function before any processing"
  - "Pattern 3: Footnote detection uses FOOTNOTE_START_RE matching 'N/' or 'Source:' prefix"

# Metrics
duration: 45min
completed: 2026-03-18
---

# Phase 2 Plan 01: Extraction Core Summary

**Pipe-delimited table extraction with unit annotation capture (extract_table_block) and three-bucket row classification with year inheritance and Decimal parsing (classify_table_rows)**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-03-18T00:00:00Z
- **Completed:** 2026-03-18T00:45:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- `extract_table_block` finds tables within 15-line anchor lookahead, walks backward for unit annotation and prose context, walks forward for complete table body and footnotes, returns all tables in span as a list
- `classify_table_rows` separates rows into month/aggregate/header buckets with aggregate detection first, year inheritance for YYYY-MonthName rows, and full Decimal parsing of corpus cell values
- `parse_cell_value` handles all corpus cell formats: commas, footnote suffixes (3/, 14/), revised markers (r), parenthetical negatives, null cells (-, --, nan, N/A)
- 64 tests total (22 extract_table_block + 42 classify_table_rows), all pass
- Fixed pytest plugin loading issue (Anaconda-based venv with broken entrypoints)

## Task Commits

1. **Task 1: extract_table_block with unit annotation, footnote capture, multi-table support** - `baf9a08` (feat)
2. **Task 2: classify_table_rows with three-bucket classification and value extraction** - `a6ab699` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `workspace/src/tools/extract_table_block.py` - Table block extraction from corpus spans; returns structured dict with prose_context, unit_annotation, table_text, footnotes, start_line, end_line
- `workspace/src/tools/classify_table_rows.py` - Row classification into month/aggregate/header buckets; includes parse_cell_value helper
- `workspace/tests/test_extract_table_block.py` - 22 unit tests including real 1941 and 1954 fixture tests
- `workspace/tests/test_classify_table_rows.py` - 42 unit tests including parse_cell_value tests and year inheritance tests
- `workspace/tests/fixtures/treasury_bulletin_1954_02.txt` - 125-line real corpus fixture with monthly rows, unit annotation, footnotes, and two tables
- `workspace/pytest.ini` - Added `-p no:anyio -p no:asyncio -p no:benchmark -p no:codspeed -p no:recording -p no:socket -p no:syrupy` to suppress Anaconda plugin loading errors

## Decisions Made
- **Aggregate before month**: Per CONTEXT.md, aggregate detection is checked first. "1940 Total" matches both bare-year and total patterns — aggregate wins. "Jan-Dec cumulative" contains month names but aggregate wins via `\bcumulative\b`.
- **parse_cell_value module-level**: Not private — Phase 3 calculator will import it directly to parse cell strings before arithmetic.
- **pytest.ini fix**: The venv uses Anaconda as its Python 3.11 base, which has broken plugin entrypoints (`anyio`, `asyncio`, etc.) that fail with `source code string cannot contain null bytes`. Adding `-p no:X` disables them before load. This is a deviation (Rule 3 - blocking).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed pytest plugin loading from Anaconda entrypoints**
- **Found during:** Task 1 (running verification)
- **Issue:** `venv/Scripts/python.exe -m pytest` failed during plugin discovery because the venv uses Anaconda as its Python 3.11 base and Anaconda's pytest11 entrypoints (anyio, asyncio, benchmark, codspeed, recording, socket, syrupy) fail to load with `SyntaxError: source code string cannot contain null bytes`
- **Fix:** Added `-p no:anyio -p no:asyncio -p no:benchmark -p no:codspeed -p no:recording -p no:socket -p no:syrupy` to pytest.ini addopts
- **Files modified:** `workspace/pytest.ini`
- **Verification:** `python -m pytest tests/test_extract_table_block.py -v` runs without error, 22 passed
- **Committed in:** `baf9a08` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed test_pipe_table_at_exactly_15_lines_after_anchor_is_found**
- **Found during:** Task 1 (running verification)
- **Issue:** Test was miscounting the lookahead window. The range is `range(anchor_idx, anchor_idx + 15)` which is a half-open range of 15 elements (anchor line through anchor+14). Test placed the pipe row at anchor+15 (outside window) and expected it to be found.
- **Fix:** Updated test to correctly reflect the half-open range behavior, renamed to `test_pipe_table_within_lookahead_window_is_found` and `test_pipe_table_outside_lookahead_window_not_found`
- **Files modified:** `workspace/tests/test_extract_table_block.py`
- **Verification:** 22/22 tests pass
- **Committed in:** `baf9a08`

**3. [Rule 1 - Bug] Fixed test_1954_fixture_month_rows_classified**
- **Found during:** Task 2 (running verification)
- **Issue:** Test provided table_text without a `| --- |` separator row. Since rows before the separator are always headers by the plan spec, all rows were classified as headers and no month rows were found.
- **Fix:** Updated test to include proper header row and separator, matching actual `extract_table_block` output format
- **Files modified:** `workspace/tests/test_classify_table_rows.py`
- **Verification:** 42/42 tests pass
- **Committed in:** `a6ab699`

---

**Total deviations:** 3 auto-fixed (1 blocking env fix, 2 test corrections)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
- Anaconda-based venv causes pytest plugin discovery to fail — documented and fixed via pytest.ini addopts.
- The "15-line lookahead" spec in the plan was ambiguous (inclusive vs. exclusive). Resolved: `range(i, i+15)` checks 15 lines starting FROM the anchor (anchor counts as line 1 of the window).

## User Setup Required
None - no external service configuration required.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| workspace/src/tools/extract_table_block.py | FOUND |
| workspace/src/tools/classify_table_rows.py | FOUND |
| workspace/tests/test_extract_table_block.py | FOUND |
| workspace/tests/test_classify_table_rows.py | FOUND |
| workspace/tests/fixtures/treasury_bulletin_1954_02.txt | FOUND |
| .planning/phases/02-extraction-calculation-core/02-01-SUMMARY.md | FOUND |
| Commit baf9a08 (Task 1) | FOUND |
| Commit a6ab699 (Task 2) | FOUND |
| pytest result: 64 passed | PASS |

## Next Phase Readiness
- `extract_table_block` and `classify_table_rows` are ready for use in Phase 3 agent loop
- `parse_cell_value` is importable from `tools.classify_table_rows` for the calculator
- Note: `calculate.py` was already committed in a prior session (commit `02268b0`) — check if 02-02 needs to redo that work or can build on it
- All 64 tests pass: `python -m pytest tests/test_extract_table_block.py tests/test_classify_table_rows.py -v`

---
*Phase: 02-extraction-calculation-core*
*Completed: 2026-03-18*
