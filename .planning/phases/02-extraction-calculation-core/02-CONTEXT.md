# Phase 2: Extraction + Calculation Core - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Four internal pipeline tools the agent calls: `extract_table_block`, `classify_table_rows`, `calculate` (with `pct_change` and `sum_values`), and `normalize_answer`. These convert raw corpus text into exact, correctly-formatted answers. Phase begins with a format survey of the answer column before any normalization code is written. Agent loop (Phase 3) and verification gate (Phase 4) are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Error contract
- Tools return a structured error dict on failure — never raise exceptions to the caller, never return None/empty silently
- Error dicts use machine-readable codes (e.g., `{"error": "UNIT_MISMATCH", "reason": "..."}`) so the agent can branch on error type; the `reason` field provides a human-readable explanation
- Input validation is the tool's responsibility: validate inputs and return a structured error if invalid (e.g., empty span_text) — don't trust the caller blindly
- `extract_table_block` returns all candidate tables as a list when multiple tables are found in the span — caller/agent chooses which to use

### Calculator strictness
- Unit mismatch rejection is based on explicit label conflicts only: reject when unit labels are present on both operands and they are incompatible (e.g., "millions" vs "billions"); unlabeled values pass through without rejection
- `sum_values` with heterogeneous units: sum all values but include a `unit_warning` field in the return — caller can act on it or ignore; do not reject the whole sum
- `pct_change` and `sum_values` accept any numeric type (str, int, float, Decimal) and convert internally to `decimal.Decimal`
- `pct_change` returns result rounded to 2 decimal places (benchmark answer format); full Decimal precision is not needed since the normalizer will format the output

### Table boundary rules
- Always include footnotes that appear immediately after the table (captures "In millions of dollars", "* Revised figures", and similar unit annotations — critical context for the calculator)
- Include the one prose sentence immediately preceding the table (helps the agent confirm table relevance)
- If two tables appear in the same span, return both as separate items in a list — agent picks which to use
- Multi-row column headers: include all header rows as-is — do not merge or transform; classify_table_rows can interpret them

### Row classification rules
- `classify_table_rows` returns three separate buckets: `month_rows`, `aggregate_rows`, `header_rows` — agent picks the bucket it needs for the question
- Ambiguous rows (e.g., "1940 Total", "12-month average", "Jan–Dec cumulative") are classified as aggregate (safer default — prevents accidentally summing a total into month subtotals)
- Input: raw table text (string) — function handles its own row splitting
- Output: classify AND extract numeric values per row in one pass — each row entry includes `row_type` and parsed `values`

### Claude's Discretion
- Exact BM25/regex pattern for detecting table boundaries within a text span
- Internal implementation of `decimal.Decimal` conversion from varied string formats (commas, spaces, parentheses for negatives)
- Specific error code vocabulary beyond the obvious ones (UNIT_MISMATCH, NO_TABLE_FOUND, etc.)
- Whether `normalize_answer` format patterns are implemented as a lookup table, regex dispatch, or something else (determined after the format survey in 02-01)

</decisions>

<specifics>
## Specific Ideas

- The format survey (02-01) must run against both `officeqa_full.csv` and `officeqa_pro.csv` and document every distinct answer format pattern before any normalization code is written — this is an explicit sequencing constraint
- Unit annotation lines like "In millions" must survive into the table block output so the calculator can reject mismatched arithmetic
- Phase 2 success criterion: `normalize_answer(raw) == expected` for every format pattern surfaced in the survey — not just common patterns

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-extraction-calculation-core*
*Context gathered: 2026-03-18*
