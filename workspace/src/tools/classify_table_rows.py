"""
classify_table_rows.py — Classify pipe-delimited table rows into month, aggregate,
and header buckets with parsed numeric values.

Consumes the table_text string output from extract_table_block and separates rows
into three buckets for downstream arithmetic. Applies aggregate detection first
(higher specificity) to prevent aggregate rows from appearing in the month bucket.

Year inheritance: when a row has a YYYY-MonthName prefix, the year is propagated
to subsequent bare-month rows until a new year prefix appears.

Error contract: Returns a structured error dict on failure — never raises to the caller.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


# ---------------------------------------------------------------------------
# Null cell values
# ---------------------------------------------------------------------------

NULL_CELLS = frozenset({'-', '--', 'nan', 'N/A', '', 'n.a.', 'None', 'none'})


# ---------------------------------------------------------------------------
# Cell value parser (module-level, also used by calculator in Phase 3)
# ---------------------------------------------------------------------------

# Footnote number suffix: " 3/", " 14/", " 2r" — space + digits + optional r/
_FOOTNOTE_RE = re.compile(r'\s+\d{1,2}[r/]\s*$')
# Trailing 'r' (revised marker) — only at end of string, case-insensitive
_TRAILING_R = re.compile(r'r$', re.IGNORECASE)


def parse_cell_value(s: str) -> Decimal | None:
    """
    Parse a corpus table cell value string to Decimal.

    Handles:
    - Null cells ('-', '--', 'nan', 'N/A', '', 'n.a.') -> None
    - Footnote suffixes: '1,580 3/' -> Decimal('1580')
    - Revised markers: '6,052r' -> Decimal('6052')
    - Parenthetical negatives: '(1234)' -> Decimal('-1234')
    - Leading '+': '+241' -> Decimal('241')
    - Commas in numbers: '33,791' -> Decimal('33791')

    Returns:
        Decimal value, or None if the cell is null/unparseable.
    """
    if not isinstance(s, str):
        # Handle non-string inputs (int, float, Decimal) gracefully
        try:
            return Decimal(str(s))
        except (InvalidOperation, ValueError):
            return None

    s = s.strip()
    if s in NULL_CELLS:
        return None

    # Strip footnote number suffixes like " 3/", " 14/", " 2r"
    s = _FOOTNOTE_RE.sub('', s).strip()
    # Strip trailing 'r' (revised marker)
    s = _TRAILING_R.sub('', s).strip()

    if not s or s in NULL_CELLS:
        return None

    # Parenthetical negative: (1234) -> -1234
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]

    # Strip leading '+'
    s = s.lstrip('+')

    # Strip commas (thousands separators)
    s = s.replace(',', '')

    if not s:
        return None

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


# ---------------------------------------------------------------------------
# Row classification patterns
# Per RESEARCH.md Pattern 5
# ---------------------------------------------------------------------------

_MONTH_FULL = (
    r'(?:January|February|March|April|May|June|July|'
    r'August|September|October|November|December)'
)
_MONTH_ABBR = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?'

# Month row pattern: optional "YYYY-" prefix, then month name, optional trailing noise
MONTH_PATTERN = re.compile(
    rf'^(?:\d{{4}}-)?(?:{_MONTH_FULL}|{_MONTH_ABBR})\s*(?:\d+[r/]*)?\s*$',
    re.IGNORECASE,
)

# Aggregate patterns — checked BEFORE month patterns (higher specificity)
AGGREGATE_PATTERNS = [
    re.compile(r'^\d{4}$'),                         # bare year: 1935
    re.compile(r'^\d{4}\s*[\(\[]'),                 # 1954 (Est.) or 1954 [note]
    re.compile(r'^\d{4}-(?!(?:' + _MONTH_FULL + r'|' + _MONTH_ABBR + r'))', re.IGNORECASE),
    re.compile(r'\btotal\b', re.IGNORECASE),
    re.compile(r'\bannual\b', re.IGNORECASE),
    re.compile(r'\bfiscal\s+year\b', re.IGNORECASE),
    re.compile(r'^cal\.', re.IGNORECASE),           # Cal. yr.
    re.compile(r'\bto\s+date\b', re.IGNORECASE),
    re.compile(r'\baverage\b', re.IGNORECASE),
    re.compile(r'\bcumulative\b', re.IGNORECASE),
    re.compile(r'\bestimate\b', re.IGNORECASE),
]

# Header row patterns — separator row or known header label patterns
HEADER_PATTERNS = [
    re.compile(r'^-{3,}$'),                         # separator row ---
    re.compile(r'^fiscal\s+year\s+or\s+month', re.IGNORECASE),
    re.compile(r'^calendar\s+year', re.IGNORECASE),
    re.compile(r'nan$'),                            # all-NaN row = sub-header
    re.compile(r':$'),                              # "Expenditures:" sub-header
]


def _classify_label(label: str) -> str:
    """
    Classify a row label into 'header', 'aggregate', or 'month'.

    Per RESEARCH.md: aggregate detection applied first (higher specificity).
    Rows before the | --- | separator are header rows regardless of label.

    Returns: 'header', 'aggregate', or 'month'
    """
    label = label.strip()

    # Check header patterns
    for pat in HEADER_PATTERNS:
        if pat.search(label):
            return 'header'

    # Check aggregate patterns FIRST (higher specificity)
    for pat in AGGREGATE_PATTERNS:
        if pat.search(label):
            return 'aggregate'

    # Check month pattern
    if MONTH_PATTERN.match(label):
        return 'month'

    # Default: header (unrecognized row labels are treated as headers/sub-headers)
    return 'header'


def _parse_row_cells(row: str) -> tuple[str, list[str]]:
    """
    Parse a pipe-delimited row into (label, value_cells).

    The label is the first non-empty cell. Value cells are all remaining cells.
    """
    parts = [p.strip() for p in row.split('|')]
    # Strip empty parts from leading/trailing pipes
    parts = [p for p in parts if True]  # keep all, including empty at start/end
    # Remove first and last if empty (from leading/trailing |)
    while parts and parts[0] == '':
        parts.pop(0)
    while parts and parts[-1] == '':
        parts.pop()

    if not parts:
        return ('', [])

    label = parts[0]
    values = parts[1:] if len(parts) > 1 else []
    return (label, values)


def _extract_year_from_label(label: str) -> str | None:
    """Extract YYYY prefix from a label like '1953-January' -> '1953'."""
    m = re.match(r'^(\d{4})-', label)
    if m:
        return m.group(1)
    return None


def classify_table_rows(table_text: str) -> dict:
    """
    Classify rows of a pipe-delimited table into three buckets.

    Args:
        table_text: Raw pipe-delimited table text (from extract_table_block output).
                    Each line should start with '|'.

    Returns:
        On success:
            {
                "header_rows": [{"label": str, "raw": str}],
                "month_rows": [
                    {"label": str, "year": str|None, "month": str,
                     "values": [Decimal|None, ...], "raw": str}
                ],
                "aggregate_rows": [
                    {"label": str, "values": [Decimal|None, ...], "raw": str}
                ]
            }

        On error:
            {"error": "INVALID_INPUT", "reason": "..."}
    """
    # --- Input validation ---
    if not table_text or not table_text.strip():
        return {"error": "INVALID_INPUT", "reason": "table_text is empty or whitespace"}

    lines = [l for l in table_text.splitlines() if l.strip()]

    header_rows: list[dict] = []
    month_rows: list[dict] = []
    aggregate_rows: list[dict] = []

    # Track whether we've passed the separator row | --- | --- |
    past_separator = False

    # Year inheritance state for month rows
    current_year: str | None = None

    for raw_line in lines:
        # Skip non-pipe lines
        if not raw_line.strip().startswith('|'):
            continue

        label, value_cells = _parse_row_cells(raw_line)

        if not label:
            continue

        # --- Separator row detection ---
        # A separator row has cells like "---" or "----"
        is_separator = all(
            re.match(r'^-{3,}$', c.strip()) or c.strip() == ''
            for c in raw_line.split('|')
            if c.strip()  # ignore empty cells from leading/trailing pipes
        )

        if is_separator:
            past_separator = True
            header_rows.append({"label": label, "raw": raw_line})
            continue

        # Rows before the separator are always headers (per plan spec)
        if not past_separator:
            header_rows.append({"label": label, "raw": raw_line})
            continue

        # --- Post-separator classification ---
        row_type = _classify_label(label)

        if row_type == 'header':
            header_rows.append({"label": label, "raw": raw_line})

        elif row_type == 'aggregate':
            parsed_values = [parse_cell_value(c) for c in value_cells]
            aggregate_rows.append({
                "label": label,
                "values": parsed_values,
                "raw": raw_line,
            })
            # Don't update year from aggregate rows

        else:  # month
            # Year inheritance
            year_in_label = _extract_year_from_label(label)
            if year_in_label:
                current_year = year_in_label

            # Extract bare month name from label (strip YYYY- prefix and trailing noise)
            month_name = re.sub(r'^\d{4}-', '', label).strip()
            month_name = re.sub(r'\s*\d+[r/]*\s*$', '', month_name).strip()

            parsed_values = [parse_cell_value(c) for c in value_cells]
            month_rows.append({
                "label": label,
                "year": current_year,
                "month": month_name,
                "values": parsed_values,
                "raw": raw_line,
            })

    return {
        "header_rows": header_rows,
        "month_rows": month_rows,
        "aggregate_rows": aggregate_rows,
    }
