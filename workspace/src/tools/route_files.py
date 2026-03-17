"""
route_files.py — File routing tool: extract year references and map to bulletin paths.

First stage of the two-stage retrieval pipeline. Takes a question, extracts
calendar/fiscal year references, maps them to bulletin filenames, and returns
only paths that actually exist in the corpus directory.

Supported year patterns:
  - "FY YYYY" / "FY{YYYY}" / "fiscal year YYYY"  -> fiscal year
  - "FY YY" / "FY{YY}"  (two-digit)              -> fiscal year (>=30 = 19xx, <30 = 20xx)
  - "calendar year YYYY"                          -> explicit calendar year
  - bare four-digit year (1939-2025)              -> calendar year

US fiscal year: FY YYYY = October (YYYY-1) through September (YYYY).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config

# Corpus date range constants
_CORPUS_START_YEAR = 1939
_CORPUS_END_YEAR = 2025

# Regex patterns — order matters: more specific patterns first.
# FY with 4-digit year: "FY 1940", "FY1940", "fiscal year 1940"
_RE_FY_4 = re.compile(
    r"\b(?:fiscal\s+year|fy)\s*(\d{4})\b",
    re.IGNORECASE,
)
# FY with 2-digit year: "FY95", "FY 95"
_RE_FY_2 = re.compile(
    r"\bfy\s*(\d{2})\b",
    re.IGNORECASE,
)
# Explicit calendar year: "calendar year 1940"
_RE_CAL_EXPLICIT = re.compile(
    r"\bcalendar\s+year\s+(\d{4})\b",
    re.IGNORECASE,
)
# Bare four-digit year in corpus range (not preceded by "fiscal year" or "fy")
# Use a negative lookbehind to skip years already matched by FY patterns.
_RE_BARE_YEAR = re.compile(
    r"(?<![/\-])(?<!fiscal\s)(?<!year\s)\b(1[0-9]{3}|20[0-2][0-9])\b",
    re.IGNORECASE,
)


def _expand_2digit_fy(yy: int) -> int:
    """Expand a two-digit FY abbreviation to four digits."""
    return 1900 + yy if yy >= 30 else 2000 + yy


def extract_years(question: str) -> list[dict]:
    """
    Extract all year references from a question string.

    Returns:
        List of {"year": int, "type": "fiscal" | "calendar"} dicts.
        Duplicate years with the same type are deduplicated.
        Order reflects appearance in the question.
    """
    results: list[dict] = []
    seen: set[tuple] = set()

    # Track positions consumed by FY patterns to avoid double-counting bare years
    fy_spans: list[tuple[int, int]] = []

    # FY 4-digit
    for m in _RE_FY_4.finditer(question):
        year = int(m.group(1))
        key = (year, "fiscal")
        if key not in seen:
            seen.add(key)
            results.append({"year": year, "type": "fiscal"})
        fy_spans.append(m.span())

    # FY 2-digit (skip positions already matched by FY 4-digit)
    for m in _RE_FY_2.finditer(question):
        # Skip if this match overlaps with an already-matched FY 4-digit span
        if any(s <= m.start() < e for s, e in fy_spans):
            continue
        year = _expand_2digit_fy(int(m.group(1)))
        key = (year, "fiscal")
        if key not in seen:
            seen.add(key)
            results.append({"year": year, "type": "fiscal"})
        fy_spans.append(m.span())

    # Calendar year explicit ("calendar year YYYY")
    cal_spans: list[tuple[int, int]] = []
    for m in _RE_CAL_EXPLICIT.finditer(question):
        year = int(m.group(1))
        key = (year, "calendar")
        if key not in seen:
            seen.add(key)
            results.append({"year": year, "type": "calendar"})
        cal_spans.append(m.span())

    # Bare four-digit year — skip positions already consumed by FY or explicit cal patterns
    all_consumed = fy_spans + cal_spans
    for m in _RE_BARE_YEAR.finditer(question):
        year = int(m.group(1))
        if year < _CORPUS_START_YEAR or year > _CORPUS_END_YEAR:
            continue
        # Skip if this digit sequence is inside an already-matched span
        if any(s <= m.start() < e for s, e in all_consumed):
            continue
        key = (year, "calendar")
        if key not in seen:
            seen.add(key)
            results.append({"year": year, "type": "calendar"})

    return results


def fy_to_calendar_months(fy_year: int) -> list[tuple[int, int]]:
    """
    Return the 12 (year, month) tuples for a US fiscal year.

    US fiscal year YYYY = October (YYYY-1) through September (YYYY).
    """
    months = []
    prev = fy_year - 1
    for month in range(10, 13):   # Oct, Nov, Dec of previous year
        months.append((prev, month))
    for month in range(1, 10):    # Jan-Sep of fiscal year
        months.append((fy_year, month))
    return months


def year_to_months(year: int) -> list[tuple[int, int]]:
    """Return the 12 (year, month) tuples for a calendar year."""
    return [(year, m) for m in range(1, 13)]


def route_files(question: str, config: "Config | None" = None) -> dict:
    """
    Extract year references from question and return matching bulletin file paths.

    Args:
        question: The user's question string.
        config: Optional Config. If None, get_config() is called.

    Returns:
        On success:
            {
                "paths": [list of absolute path strings that exist on disk],
                "years_found": [list of {"year": int, "type": str} dicts],
                "fy_mapped": bool  # True if any FY years were found
            }
        On no-year-found:
            {"error": "no_year_found", "question": question}
    """
    if config is None:
        from src.config import get_config
        config = get_config()

    years = extract_years(question)

    if not years:
        return {"error": "no_year_found", "question": question}

    # Build the set of actual files in the corpus directory for validation.
    corpus_dir = Path(config.corpus_dir)
    if corpus_dir.is_dir():
        actual_files = {f.name for f in corpus_dir.iterdir() if f.is_file()}
    else:
        actual_files = set()

    # Separate FY and calendar years for ordering: FY first (more specific).
    fy_years = [y for y in years if y["type"] == "fiscal"]
    cal_years = [y for y in years if y["type"] == "calendar"]

    # Collect candidate (year, month) pairs: FY first, then calendar.
    seen_ym: set[tuple[int, int]] = set()
    ordered_pairs: list[tuple[int, int]] = []

    for y in fy_years:
        for ym in fy_to_calendar_months(y["year"]):
            if ym not in seen_ym:
                seen_ym.add(ym)
                ordered_pairs.append(ym)

    for y in cal_years:
        for ym in year_to_months(y["year"]):
            if ym not in seen_ym:
                seen_ym.add(ym)
                ordered_pairs.append(ym)

    # Cap at 12 pairs to avoid returning huge lists for multi-year questions.
    ordered_pairs = ordered_pairs[:12]

    # Construct filenames and validate against actual corpus.
    paths: list[str] = []
    for year, month in ordered_pairs:
        fname = f"treasury_bulletin_{year}_{month:02d}.txt"
        if fname in actual_files:
            paths.append(str(corpus_dir / fname))

    return {
        "paths": paths,
        "years_found": years,
        "fy_mapped": bool(fy_years),
    }
