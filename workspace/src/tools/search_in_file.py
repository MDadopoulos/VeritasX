"""
search_in_file.py — BM25 in-file span search with table-boundary preservation.

Second stage of the two-stage retrieval pipeline. Indexes a single bulletin
file into non-overlapping spans (window=20 lines), preserves complete tables
(never splits mid-table regardless of table size), ranks spans by BM25
relevance, and falls back to regex when BM25 finds no results for numeric
queries.

Key behaviours (per project decisions):
- Table rows (lines starting with '|') are never span boundaries.
- A table longer than 20 lines becomes a single span.
- When BM25 + regex both fail, returns a structured error dict (not []).
- Each result includes: text, source_file, start_line, end_line,
  bm25_score, regex_fallback.
- FY abbreviations and comma-formatted numbers are normalised before
  BM25 tokenisation.
"""

from __future__ import annotations

import re
import os
from pathlib import Path

from rank_bm25 import BM25Okapi

# ---------------------------------------------------------------------------
# Query normalisation
# ---------------------------------------------------------------------------

# FY expansion: "FY95" or "FY 95" -> "fiscal year 1995"
_RE_FY = re.compile(r"\bfy\s*(\d{2,4})\b", re.IGNORECASE)
# Comma in numbers: "2,602" -> "2602"
_RE_COMMA_NUM = re.compile(r"(\d),(\d)")
# En-dash / em-dash to ASCII hyphen
_RE_DASHES = re.compile(r"[\u2013\u2014]")


def _expand_fy(match: re.Match) -> str:
    digits = match.group(1)
    if len(digits) == 4:
        return f"fiscal year {digits}"
    yy = int(digits)
    year = 1900 + yy if yy >= 30 else 2000 + yy
    return f"fiscal year {year}"


def normalize_query(query: str) -> str:
    """
    Normalise a query string before BM25 tokenisation.

    Transformations:
    - Expand FY abbreviations: "FY95" -> "fiscal year 1995"
    - Strip commas from numbers: "2,602" -> "2602"
    - Normalise en-dash/em-dash to ASCII hyphen
    - Lowercase

    Returns:
        Normalised lowercase string.
    """
    q = _RE_DASHES.sub("-", query)
    q = _RE_FY.sub(_expand_fy, q)
    q = _RE_COMMA_NUM.sub(r"\1\2", q)
    # Apply comma stripping repeatedly (handles "1,234,567")
    while _RE_COMMA_NUM.search(q):
        q = _RE_COMMA_NUM.sub(r"\1\2", q)
    return q.lower()


# ---------------------------------------------------------------------------
# Span builder
# ---------------------------------------------------------------------------


def build_spans(lines: list[str], window: int = 20) -> list[dict]:
    """
    Build non-overlapping spans from file lines, never splitting tables.

    A table is defined as one or more consecutive lines starting with '|'.
    When a span boundary falls inside a table, the span is extended until
    the table ends. Tables longer than `window` lines become a single span.

    Args:
        lines: List of line strings (no trailing newlines required).
        window: Target number of lines per span.

    Returns:
        List of span dicts, each with keys:
            text       – joined span text
            start_line – 1-indexed first line
            end_line   – 1-indexed last line (inclusive)
            line_count – number of lines in span
    """
    n = len(lines)
    spans: list[dict] = []
    i = 0  # current start position (0-indexed)

    while i < n:
        # Tentative end (exclusive, 0-indexed)
        end = min(i + window, n)

        # If the tentative end lands inside a table, extend forward to close it.
        while end < n and lines[end].startswith("|"):
            end += 1

        # If the span start is inside a table (the previous line is also a
        # table row), extend the start BACKWARD to include the full table.
        # This can only happen if a previous span left off mid-table — in
        # practice our loop advances i=end so this guards edge cases.
        actual_start = i
        if actual_start > 0 and lines[actual_start - 1].startswith("|"):
            # Walk back to the first line of this table block
            while actual_start > 0 and lines[actual_start - 1].startswith("|"):
                actual_start -= 1
            # Merge with previous span if overlap would occur
            if spans and actual_start < spans[-1]["end_line"]:
                # Extend previous span instead of creating a new one
                prev = spans[-1]
                # Recalculate new end from extended start
                new_end = min(actual_start + window, n)
                while new_end < n and lines[new_end].startswith("|"):
                    new_end += 1
                prev_start_0 = prev["start_line"] - 1
                merged_end = max(new_end, end)
                prev["text"] = "\n".join(lines[prev_start_0:merged_end])
                prev["end_line"] = merged_end
                prev["line_count"] = merged_end - prev_start_0
                i = merged_end
                continue

        span_text = "\n".join(lines[actual_start:end])
        spans.append(
            {
                "text": span_text,
                "start_line": actual_start + 1,   # 1-indexed
                "end_line": end,                   # 1-indexed last line = exclusive 0-idx
                "line_count": end - actual_start,
            }
        )
        i = end

    return spans


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------


def search_in_file(
    file_path: str,
    query: str,
    top_k: int = 5,
) -> list[dict] | dict:
    """
    Search a bulletin file for the most relevant spans using BM25.

    Args:
        file_path: Path to the bulletin text file.
        query: The search query (will be normalised internally).
        top_k: Maximum number of results to return.

    Returns:
        On success (BM25 or regex hits):
            List of up to top_k dicts, each with:
                text         – span text
                source_file  – absolute path to file
                start_line   – 1-indexed start line
                end_line     – 1-indexed end line
                bm25_score   – float BM25 score (0.0 for regex-fallback results)
                regex_fallback – bool

        On no results:
            {"error": "no_results", "query": query, "file": file_path,
             "spans_searched": int}
    """
    abs_path = str(Path(file_path).resolve())

    with open(file_path, encoding="utf-8") as f:
        raw_lines = [line.rstrip("\n") for line in f]

    spans = build_spans(raw_lines)
    norm_query = normalize_query(query)

    # Tokenise spans and query
    tokenised_spans = [span["text"].lower().split() for span in spans]
    query_tokens = norm_query.split()

    # BM25 scoring
    bm25 = BM25Okapi(tokenised_spans)
    scores = bm25.get_scores(query_tokens)

    # Collect top-k results with score > 0
    scored = [(score, idx) for idx, score in enumerate(scores) if score > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    top_indices = [idx for _, idx in scored[:top_k]]

    if top_indices:
        results = []
        for rank, idx in enumerate(top_indices):
            span = spans[idx]
            results.append(
                {
                    "text": span["text"],
                    "source_file": abs_path,
                    "start_line": span["start_line"],
                    "end_line": span["end_line"],
                    "bm25_score": float(scored[rank][0]),
                    "regex_fallback": False,
                }
            )
        return results

    # --- Regex fallback ---
    # Only attempt if the original query contains a digit or "FY"
    has_digit_or_fy = bool(re.search(r"\d|fy", query, re.IGNORECASE))
    if has_digit_or_fy:
        # Build a flexible pattern from the normalised query tokens
        escaped_tokens = [re.escape(t) for t in query_tokens if t]
        pattern = r"\s+".join(escaped_tokens) if escaped_tokens else None

        if pattern:
            try:
                rx = re.compile(pattern, re.IGNORECASE)
                fallback_results = []
                for span in spans:
                    if rx.search(span["text"]):
                        fallback_results.append(
                            {
                                "text": span["text"],
                                "source_file": abs_path,
                                "start_line": span["start_line"],
                                "end_line": span["end_line"],
                                "bm25_score": 0.0,
                                "regex_fallback": True,
                            }
                        )
                    if len(fallback_results) >= top_k:
                        break
                if fallback_results:
                    return fallback_results
            except re.error:
                pass

    # Both BM25 and regex (if attempted) found nothing.
    return {
        "error": "no_results",
        "query": query,
        "file": file_path,
        "spans_searched": len(spans),
    }
