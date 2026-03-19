"""
test_route_files.py — Unit tests for src/tools/route_files.py

Tests cover:
  - extract_years: FY 4-digit, FY 2-digit, calendar year, explicit calendar year,
    multiple years, no year
  - fy_to_calendar_months: correct month mapping including Y2K boundary
  - route_files: real corpus path validation, FY mapping, no-year error,
    edge cases (FY 1939 with missing Oct-Dec 1938 files)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.route_files import (
    extract_years,
    fy_to_calendar_months,
    route_files,
    year_to_months,
    _route_files_impl,
)
from src.config import Config

REPO_ROOT = Path(__file__).parent.parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "transformed"
CSV_FULL = REPO_ROOT / "officeqa_full.csv"
CSV_PRO = REPO_ROOT / "officeqa_pro.csv"


def _make_config(**kwargs) -> Config:
    defaults = dict(
        model_id="claude-sonnet-4-6",
        google_cloud_project="test-project",
        google_cloud_location="us-east5",
        google_genai_use_vertexai=True,
        google_application_credentials="",
        corpus_source="local",
        corpus_dir=CORPUS_DIR,
        csv_full_path=CSV_FULL,
        csv_pro_path=CSV_PRO,
    )
    defaults.update(kwargs)
    return Config(**defaults)


# ---------------------------------------------------------------------------
# extract_years tests
# ---------------------------------------------------------------------------


class TestExtractYears:
    def test_fy_with_space_4digit(self):
        result = extract_years("FY 1940 defense expenditures")
        assert result == [{"year": 1940, "type": "fiscal"}]

    def test_fy_no_space_4digit(self):
        result = extract_years("FY1999 total receipts")
        assert result == [{"year": 1999, "type": "fiscal"}]

    def test_fiscal_year_spelled_out(self):
        result = extract_years("fiscal year 1940 budget")
        assert result == [{"year": 1940, "type": "fiscal"}]

    def test_calendar_year_explicit(self):
        result = extract_years("calendar year 2005 receipts")
        assert result == [{"year": 2005, "type": "calendar"}]

    def test_bare_4digit_year(self):
        result = extract_years("1941 national defense")
        assert result == [{"year": 1941, "type": "calendar"}]

    def test_fy_2digit_ge30_maps_to_1900s(self):
        result = extract_years("FY95 data")
        assert result == [{"year": 1995, "type": "fiscal"}]

    def test_fy_2digit_lt30_maps_to_2000s(self):
        result = extract_years("FY05 data")
        assert result == [{"year": 2005, "type": "fiscal"}]

    def test_two_bare_years(self):
        result = extract_years("Compare 1950 and 1955 data")
        years = [r["year"] for r in result]
        assert 1950 in years
        assert 1955 in years
        assert len(result) == 2

    def test_no_year(self):
        result = extract_years("What is the GDP?")
        assert result == []

    def test_fy_2digit_no_space(self):
        result = extract_years("FY25 budget")
        assert result == [{"year": 2025, "type": "fiscal"}]

    def test_fy_2digit_boundary_30(self):
        # 30 is the boundary: FY30 -> 1930
        result = extract_years("FY30 data")
        assert result == [{"year": 1930, "type": "fiscal"}]

    def test_fy_2digit_boundary_29(self):
        # 29 < 30 -> 2029
        result = extract_years("FY29 data")
        assert result == [{"year": 2029, "type": "fiscal"}]

    def test_fy_not_double_counted(self):
        # "FY 1940" should produce only one fiscal year entry
        result = extract_years("FY 1940")
        assert len(result) == 1
        assert result[0] == {"year": 1940, "type": "fiscal"}

    def test_year_out_of_corpus_range_ignored(self):
        # 1899 is before corpus start (1939); should not appear
        result = extract_years("The year 1899 saw many changes")
        assert all(r["year"] != 1899 for r in result)

    def test_fy_and_bare_year_both_extracted(self):
        result = extract_years("FY 1940 compared to 1945 data")
        types = {r["type"] for r in result}
        assert "fiscal" in types
        # 1940 (fiscal) and 1945 (calendar) — the bare 1940 should NOT be double-counted
        fiscal = [r for r in result if r["type"] == "fiscal"]
        calendar = [r for r in result if r["type"] == "calendar"]
        assert len(fiscal) == 1
        assert fiscal[0]["year"] == 1940
        # 1945 should be calendar
        assert any(r["year"] == 1945 for r in calendar)


# ---------------------------------------------------------------------------
# fy_to_calendar_months tests
# ---------------------------------------------------------------------------


class TestFyToCalendarMonths:
    def test_fy1940_starts_oct_1939(self):
        months = fy_to_calendar_months(1940)
        assert months[0] == (1939, 10)

    def test_fy1940_ends_sep_1940(self):
        months = fy_to_calendar_months(1940)
        assert months[-1] == (1940, 9)

    def test_fy1940_has_12_entries(self):
        months = fy_to_calendar_months(1940)
        assert len(months) == 12

    def test_fy1999_starts_oct_1998(self):
        months = fy_to_calendar_months(1999)
        assert months[0] == (1998, 10)
        assert months[-1] == (1999, 9)

    def test_fy2000_y2k_boundary(self):
        months = fy_to_calendar_months(2000)
        assert months[0] == (1999, 10)
        assert months[-1] == (2000, 9)

    def test_month_sequence_is_contiguous(self):
        months = fy_to_calendar_months(1950)
        # Oct, Nov, Dec, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep
        expected_months = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        assert [m for _, m in months] == expected_months


class TestYearToMonths:
    def test_calendar_year_has_12_entries(self):
        months = year_to_months(1941)
        assert len(months) == 12

    def test_calendar_year_starts_jan(self):
        months = year_to_months(1941)
        assert months[0] == (1941, 1)

    def test_calendar_year_ends_dec(self):
        months = year_to_months(1941)
        assert months[-1] == (1941, 12)


# ---------------------------------------------------------------------------
# route_files integration tests (real corpus)
# ---------------------------------------------------------------------------


class TestRouteFilesWithRealCorpus:
    def test_fy1940_returns_existing_paths(self):
        config = _make_config()
        result = _route_files_impl("FY 1940 defense expenditures", config)

        assert "paths" in result
        assert "error" not in result
        assert result["fy_mapped"] is True

        # FY1940 = Oct 1939 - Sep 1940. All 12 months exist in corpus.
        assert len(result["paths"]) == 12

        # Spot-check specific files
        path_names = [Path(p).name for p in result["paths"]]
        assert "treasury_bulletin_1939_10.txt" in path_names
        assert "treasury_bulletin_1940_09.txt" in path_names

    def test_1941_calendar_returns_existing_paths(self):
        config = _make_config()
        result = _route_files_impl("1941 national defense", config)

        assert "paths" in result
        assert result["fy_mapped"] is False

        path_names = [Path(p).name for p in result["paths"]]
        assert "treasury_bulletin_1941_01.txt" in path_names
        assert "treasury_bulletin_1941_12.txt" in path_names

    def test_all_returned_paths_exist_on_disk(self):
        config = _make_config()
        for question in [
            "FY 1940 defense expenditures",
            "1941 national defense",
            "FY 1999 fiscal summary",
            "2005 treasury receipts",
        ]:
            result = _route_files_impl(question, config)
            for p in result.get("paths", []):
                assert Path(p).exists(), f"Path does not exist: {p}"

    def test_no_year_returns_error_dict(self):
        config = _make_config()
        result = _route_files_impl("What is GDP?", config)
        assert "error" in result
        assert result["error"] == "no_year_found"
        assert result["question"] == "What is GDP?"

    def test_no_hallucinated_filenames(self):
        config = _make_config()
        corpus_files = {f.name for f in CORPUS_DIR.iterdir() if f.is_file()}
        result = _route_files_impl("FY 1940 defense", config)
        for p in result.get("paths", []):
            assert Path(p).name in corpus_files, f"Hallucinated file: {p}"

    def test_fy1939_handles_missing_oct_dec_1938(self):
        # FY1939 = Oct 1938 - Sep 1939. Oct-Dec 1938 don't exist (corpus starts Jan 1939).
        config = _make_config()
        result = _route_files_impl("FY 1939 data", config)
        assert "paths" in result
        # Oct-Dec 1938 should NOT be in results (they don't exist)
        path_names = [Path(p).name for p in result["paths"]]
        assert "treasury_bulletin_1938_10.txt" not in path_names
        assert "treasury_bulletin_1938_11.txt" not in path_names
        assert "treasury_bulletin_1938_12.txt" not in path_names
        # But Jan-Sep 1939 should be present
        assert "treasury_bulletin_1939_01.txt" in path_names

    def test_two_digit_fy95_maps_to_1995(self):
        config = _make_config()
        result = _route_files_impl("FY95 data", config)
        assert result["fy_mapped"] is True
        assert any(r["year"] == 1995 for r in result["years_found"])
        # 1995 files should exist in corpus
        path_names = [Path(p).name for p in result["paths"]]
        assert len(path_names) > 0

    def test_two_digit_fy25_maps_to_2025(self):
        config = _make_config()
        result = _route_files_impl("FY25 data", config)
        assert any(r["year"] == 2025 for r in result["years_found"])

    def test_error_dict_has_question_key(self):
        config = _make_config()
        result = _route_files_impl("no year here", config)
        assert result.get("error") == "no_year_found"
        assert "question" in result

    def test_paths_capped_at_12(self):
        # A question with two years should not exceed 12 paths
        config = _make_config()
        result = _route_files_impl("FY 1940 and FY 1941 data", config)
        assert len(result.get("paths", [])) <= 12

    def test_fy_paths_come_before_calendar_paths(self):
        # When both FY and bare calendar year appear, FY paths should be first
        config = _make_config()
        # "FY 1940 and 1942" — FY1940 (Oct1939-Sep1940) then 1942 (Jan-Dec)
        result = _route_files_impl("FY 1940 and 1942 national defense", config)
        paths = result.get("paths", [])
        if len(paths) >= 2:
            # First path should belong to FY1940 range
            first_name = Path(paths[0]).name
            # FY1940 starts Oct 1939
            assert "1939" in first_name or "1940" in first_name
