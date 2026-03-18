# Phase 2: Extraction + Calculation Core - Research

**Researched:** 2026-03-18
**Domain:** Python text extraction, AST-safe arithmetic, decimal precision, answer normalization
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Error contract**
- Tools return a structured error dict on failure — never raise exceptions to the caller, never return None/empty silently
- Error dicts use machine-readable codes (e.g., `{"error": "UNIT_MISMATCH", "reason": "..."}`) so the agent can branch on error type; the `reason` field provides a human-readable explanation
- Input validation is the tool's responsibility: validate inputs and return a structured error if invalid (e.g., empty span_text) — don't trust the caller blindly
- `extract_table_block` returns all candidate tables as a list when multiple tables are found in the span — caller/agent chooses which to use

**Calculator strictness**
- Unit mismatch rejection is based on explicit label conflicts only: reject when unit labels are present on both operands and they are incompatible (e.g., "millions" vs "billions"); unlabeled values pass through without rejection
- `sum_values` with heterogeneous units: sum all values but include a `unit_warning` field in the return — caller can act on it or ignore; do not reject the whole sum
- `pct_change` and `sum_values` accept any numeric type (str, int, float, Decimal) and convert internally to `decimal.Decimal`
- `pct_change` returns result rounded to 2 decimal places (benchmark answer format); full Decimal precision is not needed since the normalizer will format the output

**Table boundary rules**
- Always include footnotes that appear immediately after the table (captures "In millions of dollars", "* Revised figures", and similar unit annotations — critical context for the calculator)
- Include the one prose sentence immediately preceding the table (helps the agent confirm table relevance)
- If two tables appear in the same span, return both as separate items in a list — agent picks which to use
- Multi-row column headers: include all header rows as-is — do not merge or transform; classify_table_rows can interpret them

**Row classification rules**
- `classify_table_rows` returns three separate buckets: `month_rows`, `aggregate_rows`, `header_rows` — agent picks the bucket it needs for the question
- Ambiguous rows (e.g., "1940 Total", "12-month average", "Jan–Dec cumulative") are classified as aggregate (safer default — prevents accidentally summing a total into month subtotals)
- Input: raw table text (string) — function handles its own row splitting
- Output: classify AND extract numeric values per row in one pass — each row entry includes `row_type` and parsed `values`

### Claude's Discretion
- Exact BM25/regex pattern for detecting table boundaries within a text span
- Internal implementation of `decimal.Decimal` conversion from varied string formats (commas, spaces, parentheses for negatives)
- Specific error code vocabulary beyond the obvious ones (UNIT_MISMATCH, NO_TABLE_FOUND, etc.)
- Whether `normalize_answer` format patterns are implemented as a lookup table, regex dispatch, or something else (determined after the format survey in 02-01)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

Phase 2 builds four internal pipeline tools that sit between the retrieval layer (Phase 1) and the agent loop (Phase 3). The tools convert raw corpus text into exact, correctly-formatted answers: `extract_table_block` pulls complete table blocks including unit-annotation context from a retrieved span; `classify_table_rows` splits the block into month, aggregate, and header buckets; `calculate` safely evaluates arithmetic using `decimal.Decimal` with an AST whitelist; and `normalize_answer` formats raw computed values into strings that match benchmark format exactly.

The critical sequencing constraint is that the format survey (task 02-01) must run against both `officeqa_full.csv` and `officeqa_pro.csv` before a single line of normalizer code is written. The survey has now been conducted as part of this research (see Format Survey section below); its findings directly determine what `normalize_answer` must handle.

The main precision risk in this domain is float arithmetic. Any use of Python's built-in `float` for financial values will cause rounding errors that make `normalize_answer(raw) == expected` fail silently. All numeric operations must flow through `decimal.Decimal` with `getcontext().prec = 28`. The corpus itself contains cell values with footnote suffixes (e.g., `1,580 3/`, `6,404 4/`), parenthetical negatives (e.g., `(1234)`), and `nan`/`-` nulls — all of which must be stripped or handled before any arithmetic.

**Primary recommendation:** Implement all four tools as pure functions with no side effects. Each returns either a result dict or an error dict — never raises. The format survey findings below are the authoritative source of truth for the normalizer test suite.

---

## Format Survey Results (02-01 Pre-Requisite)

Conducted against `officeqa_full.csv` (246 rows) and `officeqa_pro.csv` (133 rows).

### Distinct Format Categories

| Category | Count (full) | Examples | Normalizer Rule |
|----------|-------------|---------|-----------------|
| **A. plain_integer** | 63 | `507`, `73`, `-1299`, `935851121560` | No commas, no decimal — output `str(int(val))` |
| **B. integer_comma** | 5 | `2,602`, `44,463`, `103,375` | Comma thousands separator, no decimal |
| **C. decimal_2dp** | 56 | `39482.03`, `11.60`, `678077.00` | Exactly 2 decimal places, trailing zeros preserved |
| **D. decimal_other** | 73 | `32.703`, `0.88525`, `0.00262` | Variable decimal places, preserve as-is |
| **E. pct_2dp** | 13 | `1608.80%`, `9.89%`, `-18.51%`, `13.009%` | Preserve decimal places from calculator output; `%` suffix |
| **F. pct_integer** | 2 | `69%`, `3%` | Integer percentage with `%` suffix |
| **G. list_answer** | 21 | `[0.096, -184.143]`, `[374,443, ...]` | Pass-through — normalizer does not reformat list answers |
| **H. has_unit_word** | 6 | `36080 million`, `997.3 billion`, `-1,667.86 millions` | Pass-through — unit word is part of answer |
| **I. dollar** | 4 | `$37,921,314`, `$2,760.44`, `$140.9 Billion` | Pass-through — dollar sign is part of answer |
| **J. comma_decimal** | 1 | `57,615.04` | Comma + decimal — treat as decimal with comma separator |
| **K. date** | 2 | `March 3, 1977`, `August 1986` | Pass-through — non-numeric |

**Total: 246 in full, 133 in pro.** Overlapping questions with different answers (12 UIDs) indicate the pro dataset uses different source data or rounding rules — normalizer must handle both datasets independently.

### Critical Edge Cases Observed

1. **Trailing zeros in decimals are significant.** `11.60`, `678077.00`, `22.80` — `Decimal.normalize()` would strip these. Must preserve them.
2. **Large plain integers have no commas.** `935851121560`, `254689000` — despite comma policy in CAL-05 requirements, some benchmark answers explicitly say "Do not include any commas". Category A (plain_integer) answers have no commas in the benchmark. Category B (integer_comma) do. The normalizer must infer which format the question expects OR preserve whatever the calculator produces.
3. **Percentages are not uniformly 2dp.** `13.009%` and `9.987%` exist in the benchmark. The `pct_change` function rounds to 2dp per the CONTEXT decision, but some questions ask for CAGR or other percent-based answers with 3dp. The normalizer should preserve percent decimal places rather than forcing 2dp universally.
4. **Unicode minus sign (`\u2212`)** appears in 3 answers. Normalize to ASCII minus before any parsing.
5. **Pro-only format:** `$ 682,397.00 million` (dollar sign + space + comma-decimal + unit word). Pass-through.

### Normalizer Decision Tree

```
normalize_answer(raw):
  1. Strip whitespace, normalize unicode minus to '-'
  2. If starts with '[' -> pass-through (list answer)
  3. If contains unit word (million/billion) -> pass-through
  4. If starts with '$' -> pass-through (dollar answer)
  5. If matches date pattern -> pass-through
  6. If ends with '%' -> format as percentage (preserve original dp from raw string)
  7. If contains '.' -> format as decimal (preserve original dp from raw string, add commas if val >= 1000 AND original had comma OR val >= 10000)
  8. Else -> format as integer (preserve commas from original OR strip per question instruction)
```

**Practical note:** The normalizer's job is NOT to reformat everything — it is to ensure the raw output from the calculator matches the benchmark exactly. Pass-through for complex types. For the 5 core numeric types (A-F), apply formatting rules above.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `decimal` (stdlib) | Python 3.11 | Exact decimal arithmetic, no float errors | Mandatory for financial calculations; `getcontext().prec = 28` |
| `ast` (stdlib) | Python 3.11 | Safe arithmetic expression parsing | Whitelist approach blocks injection; already in stdlib |
| `re` (stdlib) | Python 3.11 | Table boundary detection, cell value parsing | No deps; regex is the right tool for line-pattern matching |
| `pytest` | already installed | Unit test runner | Already used in Phase 1 tests |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rank_bm25` | already installed | Used by Phase 1 search | Not needed in Phase 2 directly |

**No new package installations required.** All tools use Python stdlib only.

---

## Architecture Patterns

### Recommended Project Structure

```
workspace/src/tools/
├── extract_table_block.py     # EXT-01, EXT-02
├── classify_table_rows.py     # EXT-03, EXT-04
├── calculate.py               # CAL-01, CAL-02, CAL-03, CAL-04
├── normalize_answer.py        # CAL-05, CAL-06
workspace/tests/
├── test_extract_table_block.py
├── test_classify_table_rows.py
├── test_calculate.py
├── test_normalize_answer.py
└── fixtures/                  # reuse treasury_bulletin_1941_01.txt + add 1954_02
```

Each tool is a single module with one primary public function. Consistent with the Phase 1 pattern of `search_in_file.py` and `route_files.py`.

### Pattern 1: Structured Error Return

All tools return `dict` on both success and error. Never raise to the caller. Never return `None`.

```python
# Source: CONTEXT.md error contract decision

# Success
return {"tables": [...], "prose_context": "..."}

# Error
return {"error": "NO_TABLE_FOUND", "reason": "No pipe-delimited table found within 15 lines of anchor"}

# Input validation error
if not span_text or not span_text.strip():
    return {"error": "INVALID_INPUT", "reason": "span_text is empty or whitespace"}
```

**Established error codes (from requirements + CONTEXT decisions):**
- `INVALID_INPUT` — empty/null required argument
- `NO_TABLE_FOUND` — no pipe-delimited table in span
- `UNIT_MISMATCH` — explicit unit label conflict between operands
- `DIVISION_BY_ZERO` — denominator is zero in arithmetic
- `DISALLOWED_NODE` — AST node not in whitelist
- `COUNT_MISMATCH` — `sum_values` pair count doesn't match expected

### Pattern 2: AST Safe Calculator

```python
# Source: Python 3.11 stdlib ast module

import ast
from decimal import Decimal, getcontext, InvalidOperation
getcontext().prec = 28

SAFE_NODES = frozenset({
    ast.Expression, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.UAdd, ast.USub,
    ast.Constant,   # Python 3.8+; replaces ast.Num
})

def _safe_eval(tree):
    """Recursively evaluate an AST tree using Decimal."""
    if isinstance(tree, ast.Expression):
        return _safe_eval(tree.body)
    if isinstance(tree, ast.Constant):
        return Decimal(str(tree.value))   # str() avoids float imprecision
    if isinstance(tree, ast.BinOp):
        left = _safe_eval(tree.left)
        right = _safe_eval(tree.right)
        # ... dispatch on op type
    if isinstance(tree, ast.UnaryOp):
        # ... handle USub, UAdd
```

**Critical:** Convert `Constant` values with `Decimal(str(node.value))`, NOT `Decimal(node.value)`. The AST parses `3.14` as a Python float first; `str()` produces `"3.14"` which Decimal then parses exactly.

### Pattern 3: Numeric String Parser for Corpus Cells

Corpus cell values have multiple variants that must parse to `Decimal`:

```python
import re
from decimal import Decimal, InvalidOperation

_FOOTNOTE_SUFFIX = re.compile(r'\s+\d+[r/]?\s*$')   # " 3/", " 2r", " 14/"
_REVISED_SUFFIX = re.compile(r'r$')                   # trailing 'r' = revised

def parse_cell_value(s: str) -> Decimal | None:
    """Parse a corpus table cell value to Decimal. Returns None for null cells."""
    s = s.strip()
    if s in ('-', '--', 'nan', 'N/A', '', 'n.a.'):
        return None
    # Strip footnote number suffixes like "3/", "14/", revised marker "r"
    s = _FOOTNOTE_SUFFIX.sub('', s).strip()
    s = _REVISED_SUFFIX.sub('', s).strip()
    # Parenthetical negative: (1234) -> -1234
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    # Strip leading '+' (change values like '+241')
    s = s.lstrip('+')
    # Strip commas
    s = s.replace(',', '')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None
```

**Verified against corpus:** handles `1,580 3/`, `6,404 4/`, `(1234)`, `+241`, `nan`, `-`, `6,052r`, `33,791 14/`.

### Pattern 4: Table Block Extraction

The corpus structure (verified against 82 tables in `treasury_bulletin_1941_01.txt`):

```
[prose title line]          <- include as context
                            <- blank line
[(In millions of dollars)]  <- unit annotation — MUST be in output
                            <- blank line
| header cols... |          <- first pipe row = table start
| --- | --- |               <- separator row
| data rows |               <- data
                            <- blank line (end of table)
Source: ...                 <- footnote start (no pipe)
1/ footnote text...         <- numbered footnotes
2/ ...
                            <- blank line (end of footnotes)
[next section]
```

**Boundary detection algorithm:**
1. Find first `|`-prefixed line within 15 lines of anchor phrase (case-insensitive substring match)
2. Walk backward from table start to find unit annotation: look up to 4 lines back for `(In ... of ...)` or `(Cumulative - In ... )` pattern
3. Include the non-blank prose line immediately before the unit annotation (the table title)
4. Walk forward past all `|` rows (the table body)
5. Continue forward collecting footnote lines: stop when a blank line is followed by a non-footnote line (non-footnote = does not start with digit+`/`, `Source:`, or continuation of prior footnote)
6. If a second `|` table starts within the footnote region (before the next section), capture it as a second table entry

### Pattern 5: Row Classification

Row type is determined from the **first-column label** of each `|` row:

```python
MONTH_FULL = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
MONTH_ABBR = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?'
MONTH_PATTERN = re.compile(
    rf'^(?:\d{{4}}-)?(?:{MONTH_FULL}|{MONTH_ABBR})\s*(?:\d+[r/]*)?\s*$',
    re.IGNORECASE
)

AGGREGATE_PATTERNS = [
    re.compile(r'^\d{4}$'),                    # bare year: 1935
    re.compile(r'^\d{4}\s*\('),               # 1954 (Est.)
    re.compile(r'^\d{4}-\w+', re.I),          # fiscal year prefixed (not month)
    re.compile(r'\btotal\b', re.I),
    re.compile(r'\bannual\b', re.I),
    re.compile(r'\bfiscal year\b', re.I),
    re.compile(r'^cal\.', re.I),              # Cal. yr.
    re.compile(r'\bto date\b', re.I),
    re.compile(r'\baverage\b', re.I),
    re.compile(r'\bcumulative\b', re.I),
    re.compile(r'\bestimate\b', re.I),
]

HEADER_PATTERNS = [
    re.compile(r'^---+$'),                    # separator row
    re.compile(r'^fiscal year or month', re.I),
    re.compile(r'^calendar year', re.I),
    re.compile(r'nan$'),                      # all-NaN row = sub-header
    re.compile(r':$'),                        # "Expenditures:" sub-header
]
```

**Ambiguous rows (classify as aggregate per CONTEXT decision):**
- `1940 Total` — matches both year and "total" → aggregate
- `Jan-Dec cumulative` — contains month names but is aggregate period → aggregate
- `12-month average` → aggregate

### Anti-Patterns to Avoid

- **Using `float` for any financial value.** `float('3.14')` introduces binary representation error. Always `Decimal(str(value))`.
- **Using Python `eval()` directly.** Even with `globals={}`, `eval()` is not safe — use the AST whitelist approach.
- **Truncating table block at 15 lines.** The 15-line limit is for finding the table START, not the block size. Once a table is found, include all rows regardless of length.
- **Stripping trailing zeros from decimals.** `Decimal.normalize()` converts `11.60` to `11.6`, breaking `normalize_answer('11.60') == '11.60'`. Never call `.normalize()` when formatting output.
- **Calling `int()` to detect integers.** Use `val == val.to_integral_value()` with Decimal.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Safe expression evaluation | Custom parser/tokenizer | `ast.parse()` + node whitelist | AST handles operator precedence, parentheses, unary ops correctly |
| Decimal arithmetic | Float math + manual rounding | `decimal.Decimal` with `prec=28` | Binary float cannot represent 0.1 exactly; financial values require exact decimal arithmetic |
| Unit tests | Custom test runner | `pytest` (already installed) | Already used in Phase 1; fixture sharing pattern established |

**Key insight:** The AST whitelist approach rejects `__import__`, `getattr`, function calls, subscripts, and all other Python constructs with zero code — just check `type(node) not in SAFE_NODES`. This is far more robust than string-parsing the expression.

---

## Common Pitfalls

### Pitfall 1: Float Contamination in Decimal Calculations

**What goes wrong:** `Decimal(3.14)` produces `3.140000000000000124344978758017...` because the float `3.14` already has rounding error before Decimal sees it.
**Why it happens:** Corpus cells read as strings are fine, but AST `Constant` nodes store Python float objects for decimal literals.
**How to avoid:** Always `Decimal(str(node.value))` in the AST evaluator, never `Decimal(node.value)` directly.
**Warning signs:** Test `calculate("3.14 * 100")` — should return `314.00`, not `314.0000000000000124...`.

### Pitfall 2: Footnote Suffixes on Cell Values

**What goes wrong:** `parse_cell_value("1,580 3/")` returns `None` if the footnote suffix isn't stripped, or raises if passed directly to `Decimal()`.
**Why it happens:** OCR-converted corpus tables embed footnote markers inline with numeric values (e.g., `1,580 3/`, `33,791 14/`, `6,052r`).
**How to avoid:** Strip footnote suffixes before numeric parsing. Pattern: `\s+\d+[r/]?\s*$` and trailing `r`.
**Warning signs:** Unexpected `None` values from `parse_cell_value` for cells that visually contain numbers.

### Pitfall 3: Unit Annotation Above the Table

**What goes wrong:** `extract_table_block` returns only the `|` rows, missing `(In millions of dollars)` which appears 1-2 lines before the first `|` row.
**Why it happens:** The unit annotation is not a pipe row — it's a parenthetical prose line. Naive "collect all `|` lines" logic misses it.
**How to avoid:** Walk backward from the first `|` row looking for unit annotation pattern `\(In .* of .*\)` or `\(Cumulative - In .* \)`.
**Warning signs:** Calculator receives values but has no unit context — unit mismatch detection is blind.

### Pitfall 4: `|` Rows Inside Multi-Row Column Headers

**What goes wrong:** In the corpus, multi-level column headers appear as multiple consecutive `|` rows before the `| --- |` separator. Treating the first `|` row as a data row corrupts value extraction.
**Why it happens:** pandas multi-level columns are serialized as multiple header rows in the text format.
**How to avoid:** The `| --- |` separator row reliably marks the boundary between headers and data. Everything before `| --- |` is a header row; everything after is data.
**Warning signs:** First row of "data" has no numeric values, only column names.

### Pitfall 5: Aggregate Row Appearing in Month Bucket

**What goes wrong:** A `Cal. yr.` or `1953` row gets classified as a month row and included in the `sum_values` call, doubling the sum.
**Why it happens:** In some bulletins, year rows appear interspersed with month rows (e.g., `| 1953 |` immediately before `| 1953-Jan. |`).
**How to avoid:** Apply aggregate detection first (higher specificity), then month detection. Any row matching an aggregate pattern is aggregate, even if it also contains a partial month string.
**Warning signs:** `sum_values` result is roughly twice the expected value.

### Pitfall 6: Trailing Zeros in Decimal Output

**What goes wrong:** `normalize_answer("11.60")` returns `"11.6"` because the formatter calls `str(Decimal("11.60"))` which is `"11.60"` but `str(Decimal("11.60").normalize())` is `"11.6"`.
**Why it happens:** `Decimal.normalize()` strips trailing zeros. The benchmark has `11.60`, `678077.00`, `22.80` which must preserve trailing zeros.
**How to avoid:** When formatting decimal output, count the decimal places in the RAW input string and use `f"{val:.{dp}f}"` to preserve them.
**Warning signs:** `normalize_answer(raw) == expected` fails for `C. decimal_2dp` category answers.

---

## Code Examples

Verified patterns from corpus analysis and Python 3.11 stdlib:

### AST Safe Evaluator (CAL-01)

```python
# Source: Python 3.11 ast module docs + verification run 2026-03-18

import ast
from decimal import Decimal, getcontext, InvalidOperation

getcontext().prec = 28

SAFE_NODES = frozenset({
    ast.Expression, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.UAdd, ast.USub,
    ast.Constant,
})

def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        return Decimal(str(node.value))   # MUST use str() to avoid float imprecision
    if isinstance(node, ast.BinOp):
        L = _eval_node(node.left)
        R = _eval_node(node.right)
        if isinstance(node.op, ast.Add):  return L + R
        if isinstance(node.op, ast.Sub):  return L - R
        if isinstance(node.op, ast.Mult): return L * R
        if isinstance(node.op, ast.Div):
            if R == 0:
                return {"error": "DIVISION_BY_ZERO", "reason": "Denominator is zero"}
            return L / R
        if isinstance(node.op, ast.Pow):  return L ** R
        if isinstance(node.op, ast.Mod):  return L % R
    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.USub): return -operand
        if isinstance(node.op, ast.UAdd): return +operand
    return {"error": "UNSUPPORTED_NODE", "reason": f"{type(node).__name__}"}

def calculate(expr: str) -> dict:
    if not expr or not expr.strip():
        return {"error": "INVALID_INPUT", "reason": "Expression is empty"}
    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except SyntaxError as e:
        return {"error": "SYNTAX_ERROR", "reason": str(e)}
    for node in ast.walk(tree):
        if type(node) not in SAFE_NODES:
            return {"error": "DISALLOWED_NODE", "reason": f"AST node {type(node).__name__} not allowed"}
    result = _eval_node(tree)
    if isinstance(result, dict):  # propagated error
        return result
    return {"result": result}
```

### pct_change Operation (CAL-02)

```python
# Source: Verified against benchmark UID0001/UID0004 2026-03-18

def pct_change(old, new) -> dict:
    """
    Calculate absolute percent change from old to new.
    Returns result rounded to 2 decimal places.
    Accepts str, int, float, or Decimal.
    """
    try:
        old_d = Decimal(str(old))
        new_d = Decimal(str(new))
    except InvalidOperation as e:
        return {"error": "INVALID_INPUT", "reason": f"Cannot convert to Decimal: {e}"}
    if old_d == 0:
        return {"error": "DIVISION_BY_ZERO", "reason": "old value is zero, cannot compute pct_change"}
    result = (new_d - old_d) / old_d * Decimal('100')
    return {"result": round(result, 2)}

# Verification:
# pct_change(2602, 3100)  -> {"result": Decimal("19.14")}
# pct_change(2602, 44463) -> {"result": Decimal("1608.80")}  (matches UID0004 answer)
```

### sum_values Operation (CAL-03)

```python
# Source: CONTEXT.md CAL-03 specification

def sum_values(pairs: list[tuple[str, any]], expected_count: int) -> dict:
    """
    Sum a list of (label, value) pairs.
    Returns error if len(pairs) != expected_count.
    Returns unit_warning if units are heterogeneous.
    """
    if len(pairs) != expected_count:
        return {
            "error": "COUNT_MISMATCH",
            "reason": f"Expected {expected_count} pairs, got {len(pairs)}",
            "actual_count": len(pairs),
        }
    total = Decimal('0')
    units = set()
    for label, value in pairs:
        try:
            val = Decimal(str(value))
        except InvalidOperation:
            return {"error": "INVALID_INPUT", "reason": f"Cannot parse value for label {repr(label)}"}
        total += val
        # Extract unit from label if present
        unit_match = re.search(r'\b(millions?|billions?|thousands?)\b', label, re.I)
        if unit_match:
            units.add(unit_match.group(1).lower().rstrip('s'))  # normalize plural
    result = {"result": total, "pair_count": len(pairs)}
    if len(units) > 1:
        result["unit_warning"] = f"Heterogeneous units in labels: {sorted(units)}"
    return result
```

### Corpus Cell Value Parser

```python
# Source: Verified against treasury_bulletin_1941_01.txt and treasury_bulletin_1954_02.txt

import re
from decimal import Decimal, InvalidOperation

_FOOTNOTE_RE = re.compile(r'\s+\d{1,2}[r/]\s*$')  # " 3/", " 14/", " 2r"
_TRAILING_R = re.compile(r'r$', re.IGNORECASE)

NULL_CELLS = frozenset({'-', '--', 'nan', 'N/A', '', 'n.a.', 'None'})

def parse_cell_value(s: str) -> Decimal | None:
    s = s.strip()
    if s in NULL_CELLS:
        return None
    s = _FOOTNOTE_RE.sub('', s).strip()
    s = _TRAILING_R.sub('', s).strip()
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    s = s.lstrip('+')
    s = s.replace(',', '')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None
```

### Table Block Boundary Detection (EXT-01)

```python
# Source: Verified against 82 tables in treasury_bulletin_1941_01.txt

UNIT_ANNOTATION_RE = re.compile(
    r'^\s*\((?:cumulative\s*[-–]\s*)?in\s+\w[\w\s]*of\s+\w[\w\s]*\)',
    re.IGNORECASE
)

def _find_table_in_span(lines: list[str], anchor: str, max_lookahead: int = 15) -> int | None:
    """Return 0-indexed line number of first | row within max_lookahead of anchor phrase."""
    anchor_lower = anchor.lower()
    for i, line in enumerate(lines):
        if anchor_lower in line.lower():
            # Found anchor; look ahead for pipe row
            for j in range(i, min(len(lines), i + max_lookahead)):
                if lines[j].startswith('|'):
                    return j
    return None

def _collect_table_block(lines: list[str], table_start: int) -> dict:
    """Collect complete table block: context before + table body + footnotes."""
    # Walk backward for unit annotation and prose title
    prose_line = None
    unit_line = None
    for k in range(table_start - 1, max(-1, table_start - 5), -1):
        stripped = lines[k].strip()
        if not stripped:
            continue
        if UNIT_ANNOTATION_RE.match(stripped) and unit_line is None:
            unit_line = lines[k]
        elif unit_line is not None and prose_line is None:
            prose_line = lines[k]
            break
        elif unit_line is None and prose_line is None:
            prose_line = lines[k]   # first non-blank before table = prose context
            break

    # Walk forward collecting table rows
    j = table_start
    while j < len(lines) and lines[j].startswith('|'):
        j += 1

    # Walk forward collecting footnotes
    footnote_end = j
    while footnote_end < len(lines):
        line = lines[footnote_end].strip()
        if not line:
            # Blank line — peek ahead; if next non-blank is also footnote, continue
            peek = footnote_end + 1
            while peek < len(lines) and not lines[peek].strip():
                peek += 1
            if peek < len(lines) and re.match(r'^\d+[/]|^Source:', lines[peek]):
                footnote_end = peek + 1
                continue
            break
        footnote_end += 1

    context_lines = []
    if prose_line:
        context_lines.append(prose_line)
    if unit_line:
        context_lines.append(unit_line)

    table_text = "\n".join(lines[table_start:j])
    footnote_text = "\n".join(lines[j:footnote_end]).strip()

    return {
        "prose_context": "\n".join(context_lines).strip(),
        "table_text": table_text,
        "footnotes": footnote_text,
        "start_line": table_start + 1,    # 1-indexed
        "end_line": footnote_end,
    }
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ast.Num` node type | `ast.Constant` node type | Python 3.8 | `ast.Num` deprecated; `ast.Constant` handles all literal types |
| `float` for financial math | `decimal.Decimal` | Python 2→3 era | Eliminates binary rounding errors in financial computations |
| `eval()` with restricted globals | `ast.parse()` + node whitelist | Best practice | AST approach is provably safe; `eval()` approaches are not |

**Deprecated:**
- `ast.Num`: replaced by `ast.Constant` in Python 3.8+. The Phase 2 code targets Python 3.11 (confirmed in venv). Use `ast.Constant` only.

---

## Open Questions

1. **Integer comma convention — when to add commas vs preserve raw**
   - What we know: 63 benchmark answers are plain integers without commas (including large ones like `935851121560`); 5 have commas. Questions explicitly saying "do not include commas" produce no-comma answers.
   - What's unclear: Should the normalizer add commas to computed sums like `44,463`, or should the agent call normalizer with the formatting instruction in scope?
   - Recommendation: The normalizer should be a passthrough for format — it takes `raw` as the calculator output string and only formats known types (percentages, specific decimal counts). For integer output, preserve exactly what the calculator returns. The AGENT is responsible for specifying comma format as part of the prompt to the LLM which calls `calculate`.

2. **Multi-table in same span — anchor phrase matching**
   - What we know: CONTEXT decision says return both tables as a list when two tables appear in same span; agent picks.
   - What's unclear: If the anchor phrase appears in the prose preceding Table A, but Table B is the relevant one (closer to the right year), how does the agent know which to use?
   - Recommendation: Return both with their `prose_context` — agent uses prose_context (title + unit line) to select. This is an agent loop (Phase 3) concern, not Phase 2.

3. **`classify_table_rows` — multi-year tables with interleaved months**
   - What we know: Some tables have rows like `| 1940-January |` followed by `| February |` (abbreviated month, no year prefix). The year is inherited from the previous row's prefix.
   - What's unclear: Should `classify_table_rows` track year inheritance to populate `year` field on continuation month rows?
   - Recommendation: Yes — include `year` field in each `month_row` entry. Walk rows in order; when a row has `YYYY-MonthName` pattern, capture `YYYY` and propagate to subsequent abbreviation-only month rows until a new year prefix appears.

---

## Sources

### Primary (HIGH confidence)
- Python 3.11 stdlib `decimal` module — `getcontext().prec`, `Decimal(str(...))` pattern, `to_integral_value()`
- Python 3.11 stdlib `ast` module — `ast.Constant`, `ast.walk()`, `ast.parse(mode='eval')`
- Direct corpus analysis: `treasury_bulletin_1941_01.txt` (82 tables, 1000+ lines) — table boundary patterns
- Direct corpus analysis: `treasury_bulletin_1954_02.txt` — monthly row format variations
- Direct CSV analysis: `officeqa_full.csv` (246 rows) and `officeqa_pro.csv` (133 rows) — all 246 answer format patterns enumerated

### Secondary (MEDIUM confidence)
- Phase 1 source code (`search_in_file.py`, `route_files.py`) — established error contract and module structure patterns

### Tertiary (LOW confidence)
- None — all findings verified against primary sources

---

## Metadata

**Confidence breakdown:**
- Format survey results: HIGH — enumerated directly from CSV data
- Standard stack: HIGH — all stdlib, no external deps
- Architecture: HIGH — derived from CONTEXT decisions and verified corpus structure
- Cell value parsing: HIGH — verified against real corpus cell patterns
- Pitfalls: HIGH — all derived from verified code experiments or direct corpus inspection

**Research date:** 2026-03-18
**Valid until:** 2026-04-18 (corpus structure is stable; Python 3.11 stdlib is stable)
