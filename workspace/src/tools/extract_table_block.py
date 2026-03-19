"""
extract_table_block.py — Extract complete pipe-delimited table blocks from corpus text spans.

Finds the first pipe-delimited table within 15 lines of an anchor phrase, walking
backward to capture unit annotation lines (e.g., "(In millions of dollars)") and
the preceding prose context line, then forward to collect all table rows and
any immediately following footnotes.

When multiple tables are found in the same span, all are returned as separate list items.

Error contract: Returns a structured error dict on failure — never raises to the caller.
"""

from __future__ import annotations

import re

from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# Unit annotation regex
# Matches: "(In millions of dollars)", "(Cumulative - in thousands of units)", etc.
# ---------------------------------------------------------------------------
UNIT_ANNOTATION_RE = re.compile(
    r'^\s*\((?:cumulative\s*[-\u2013\u2014]\s*)?in\s+\w[\w\s]*of\s+\w[\w\s]*\)',
    re.IGNORECASE,
)

# Footnote line patterns: "1/ ...", "Source: ...", numbered continuation
_FOOTNOTE_START_RE = re.compile(r'^\d{1,2}[/]|^Source:', re.IGNORECASE)


def _collect_table_block(lines: list[str], table_start: int) -> dict:
    """
    Collect a complete table block starting at table_start (0-indexed).

    Walks backward for unit annotation and prose title (up to 4 lines back).
    Walks forward collecting all consecutive pipe rows (the table body).
    Continues forward collecting footnote lines.

    Returns a dict with keys:
        prose_context   – prose title + unit annotation joined (may be empty string)
        unit_annotation – unit annotation string or None
        table_text      – all pipe rows joined with newlines
        footnotes       – footnote text joined (may be empty string)
        start_line      – 1-indexed first pipe row line
        end_line        – 1-indexed last line included (footnotes end or table end)
    """
    # --- Backward walk: find unit annotation and prose context ---
    prose_line = None
    unit_line = None

    for k in range(table_start - 1, max(-1, table_start - 5), -1):
        stripped = lines[k].strip()
        if not stripped:
            continue
        if UNIT_ANNOTATION_RE.match(stripped) and unit_line is None:
            unit_line = stripped
        elif unit_line is not None and prose_line is None:
            prose_line = stripped
            break
        elif unit_line is None and prose_line is None:
            # First non-blank line before table (no unit annotation found yet)
            prose_line = stripped
            break

    # --- Forward walk: collect all consecutive pipe rows (table body) ---
    j = table_start
    while j < len(lines) and lines[j].startswith('|'):
        j += 1
    table_end = j  # exclusive, 0-indexed

    # --- Forward walk: collect footnotes ---
    footnote_end = table_end
    while footnote_end < len(lines):
        line = lines[footnote_end].strip()
        if not line:
            # Blank line — peek ahead for more footnotes
            peek = footnote_end + 1
            while peek < len(lines) and not lines[peek].strip():
                peek += 1
            if peek < len(lines) and _FOOTNOTE_START_RE.match(lines[peek].strip()):
                footnote_end = peek + 1
                continue
            break
        if _FOOTNOTE_START_RE.match(line) or (footnote_end > table_end):
            # Only collect non-pipe continuation lines if already in footnote region
            if lines[footnote_end].startswith('|'):
                break
            footnote_end += 1
        else:
            break

    # Build context string
    context_parts = []
    if prose_line:
        context_parts.append(prose_line)
    if unit_line:
        context_parts.append(unit_line)

    table_text = "\n".join(lines[table_start:table_end])
    footnote_text = "\n".join(lines[table_end:footnote_end]).strip()

    return {
        "prose_context": "\n".join(context_parts).strip(),
        "unit_annotation": unit_line,
        "table_text": table_text,
        "footnotes": footnote_text,
        "start_line": table_start + 1,    # 1-indexed
        "end_line": footnote_end,          # 1-indexed (last line inclusive, exclusive 0-idx = 1-indexed last)
    }


def _extract_table_block_impl(span_text: str, anchor: str) -> dict:
    """
    Extract all pipe-delimited table blocks from span_text near an anchor phrase.

    Args:
        span_text: The text span to search within (from search_in_file output).
        anchor:    Case-insensitive anchor phrase to locate tables near.

    Returns:
        On success:
            {"tables": [
                {
                    "prose_context": str,
                    "unit_annotation": str | None,
                    "table_text": str,
                    "footnotes": str,
                    "start_line": int,
                    "end_line": int,
                },
                ...
            ]}

        On error:
            {"error": "INVALID_INPUT", "reason": "..."}
            {"error": "NO_TABLE_FOUND", "reason": "..."}
    """
    # --- Input validation ---
    if not span_text or not span_text.strip():
        return {"error": "INVALID_INPUT", "reason": "span_text is empty or whitespace"}
    if not anchor or not anchor.strip():
        return {"error": "INVALID_INPUT", "reason": "anchor is empty or whitespace"}

    lines = span_text.splitlines()
    anchor_lower = anchor.strip().lower()
    max_lookahead = 15

    # --- Find anchor line(s) and the first pipe row within lookahead ---
    first_table_start = None
    for i, line in enumerate(lines):
        if anchor_lower in line.lower():
            for j in range(i, min(len(lines), i + max_lookahead)):
                if lines[j].startswith('|'):
                    first_table_start = j
                    break
        if first_table_start is not None:
            break

    if first_table_start is None:
        return {
            "error": "NO_TABLE_FOUND",
            "reason": f"No pipe-delimited table found within {max_lookahead} lines of anchor '{anchor}'",
        }

    # --- Collect all tables from this span ---
    tables = []
    scan_pos = first_table_start

    while scan_pos < len(lines):
        if lines[scan_pos].startswith('|'):
            block = _collect_table_block(lines, scan_pos)
            tables.append(block)
            # Advance past this table block (table body + footnotes)
            scan_pos = block["end_line"]  # end_line is exclusive 0-indexed
        else:
            scan_pos += 1

    if not tables:
        return {
            "error": "NO_TABLE_FOUND",
            "reason": f"No pipe-delimited table found within {max_lookahead} lines of anchor '{anchor}'",
        }

    return {"tables": tables}


# ---------------------------------------------------------------------------
# @tool-decorated StructuredTool alias for create_deep_agent registration.
# ---------------------------------------------------------------------------

extract_table_block = tool("extract_table_block")(_extract_table_block_impl)
