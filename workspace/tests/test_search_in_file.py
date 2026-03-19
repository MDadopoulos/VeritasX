"""
test_search_in_file.py — Unit tests for src/tools/search_in_file.py

Tests cover:
  - normalize_query: FY expansion, comma stripping, dash normalization
  - build_spans: non-overlapping, table boundary preservation, total line coverage
  - search_in_file: BM25 results, regex fallback, no-results error dict,
    metadata on each result

Note: search_in_file is a plain Python function. Call directly:
    search_in_file(file_path, query, top_k)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.search_in_file import (
    build_spans,
    normalize_query,
    search_in_file,
)

FIXTURE = Path(__file__).parent / "fixtures" / "treasury_bulletin_1941_01.txt"


# ---------------------------------------------------------------------------
# normalize_query tests
# ---------------------------------------------------------------------------


class TestNormalizeQuery:
    def test_fy2digit_ge30(self):
        assert normalize_query("FY95 defense") == "fiscal year 1995 defense"

    def test_fy4digit(self):
        assert normalize_query("FY2005 receipts") == "fiscal year 2005 receipts"

    def test_comma_stripped_from_number(self):
        assert normalize_query("2,602 millions") == "2602 millions"

    def test_fy_with_space_4digit(self):
        assert normalize_query("FY 1940 national defense") == "fiscal year 1940 national defense"

    def test_en_dash_replaced(self):
        result = normalize_query("1939\u20131940")
        assert "\u2013" not in result
        assert "-" in result

    def test_em_dash_replaced(self):
        result = normalize_query("pre\u2014post")
        assert "\u2014" not in result
        assert "-" in result

    def test_lowercased(self):
        assert normalize_query("DEFENSE Expenditures") == "defense expenditures"

    def test_large_comma_number(self):
        assert normalize_query("1,234,567") == "1234567"

    def test_fy2digit_lt30(self):
        assert normalize_query("FY05 budget") == "fiscal year 2005 budget"

    def test_no_change_plain_text(self):
        result = normalize_query("national defense expenditures")
        assert result == "national defense expenditures"


# ---------------------------------------------------------------------------
# build_spans tests (use real fixture file)
# ---------------------------------------------------------------------------


class TestBuildSpans:
    @pytest.fixture(autouse=True)
    def load_fixture(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.lines = [line.rstrip("\n") for line in f]
        self.spans = build_spans(self.lines)

    def test_spans_are_non_overlapping(self):
        """Consecutive spans must not overlap in line coverage."""
        for i in range(len(self.spans) - 1):
            curr_end = self.spans[i]["end_line"]
            next_start = self.spans[i + 1]["start_line"]
            assert next_start > curr_end or next_start == curr_end + 1, (
                f"Overlap between span {i} (end={curr_end}) and span {i+1} (start={next_start})"
            )

    def test_no_span_boundary_splits_table(self):
        """
        For each span whose last line starts with '|', the next span's first
        line must NOT start with '|' (the table was fully absorbed).
        """
        for i, span in enumerate(self.spans[:-1]):
            last_line = span["text"].split("\n")[-1]
            if last_line.startswith("|"):
                next_first = self.spans[i + 1]["text"].split("\n")[0]
                assert not next_first.startswith("|"), (
                    f"Span {i} ends with table row but next span also starts with '|'"
                )

    def test_table_longer_than_20_lines_in_single_span(self):
        """A table with >20 pipe rows must be fully contained in one span."""
        # Lines 317-364 (1-indexed) form a 48-row table in the fixture.
        # Find a span that contains line 317.
        target_line = 317
        containing_spans = [
            s for s in self.spans
            if s["start_line"] <= target_line <= s["end_line"]
        ]
        assert len(containing_spans) == 1, (
            f"Expected 1 span containing line {target_line}, got {len(containing_spans)}"
        )
        span = containing_spans[0]
        # The table runs at least through line 364 — verify the span covers it
        assert span["end_line"] >= 364, (
            f"Span ends at line {span['end_line']}, expected >= 364 (table end)"
        )

    def test_total_lines_covered(self):
        """All lines in the file must be covered by exactly one span."""
        covered = set()
        for span in self.spans:
            for line_no in range(span["start_line"], span["end_line"] + 1):
                assert line_no not in covered, f"Line {line_no} covered by multiple spans"
                covered.add(line_no)
        total = len(self.lines)
        for line_no in range(1, total + 1):
            assert line_no in covered, f"Line {line_no} not covered by any span"

    def test_each_span_has_required_keys(self):
        required_keys = {"text", "start_line", "end_line", "line_count"}
        for span in self.spans:
            assert required_keys.issubset(span.keys()), (
                f"Span missing keys: {required_keys - span.keys()}"
            )

    def test_span_metadata_consistent(self):
        for span in self.spans:
            assert span["end_line"] >= span["start_line"]
            assert span["start_line"] >= 1
            # end_line is the last covered line (1-indexed) — line_count should match
            assert span["line_count"] == span["end_line"] - span["start_line"] + 1, (
                f"line_count mismatch: {span['line_count']} vs "
                f"{span['end_line'] - span['start_line'] + 1}"
            )

    def test_span_text_line_count_matches(self):
        for span in self.spans:
            actual_lines = len(span["text"].split("\n"))
            assert actual_lines == span["line_count"], (
                f"text has {actual_lines} lines but line_count={span['line_count']}"
            )


# ---------------------------------------------------------------------------
# search_in_file BM25 tests
# ---------------------------------------------------------------------------


class TestSearchInFile:
    def test_returns_list_for_known_query(self):
        result = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) >= 1

    def test_top_result_contains_defense(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        assert "defense" in results[0]["text"].lower()

    def test_result_has_all_required_keys(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        required = {"text", "source_file", "start_line", "end_line", "bm25_score", "regex_fallback"}
        for r in results:
            assert required.issubset(r.keys()), f"Missing keys: {required - r.keys()}"

    def test_results_sorted_by_bm25_score_descending(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        scores = [r["bm25_score"] for r in results]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score desc"

    def test_bm25_results_have_regex_fallback_false(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        for r in results:
            assert r["regex_fallback"] is False

    def test_source_file_is_absolute_path(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        for r in results:
            assert Path(r["source_file"]).is_absolute(), (
                f"source_file not absolute: {r['source_file']}"
            )

    def test_start_end_line_are_positive_integers(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r["start_line"], int) and r["start_line"] >= 1
            assert isinstance(r["end_line"], int) and r["end_line"] >= r["start_line"]

    def test_source_file_matches_input_path(self):
        results = search_in_file(str(FIXTURE), "national defense expenditures")
        assert isinstance(results, list)
        abs_fixture = str(FIXTURE.resolve())
        for r in results:
            assert r["source_file"] == abs_fixture


# ---------------------------------------------------------------------------
# Regex fallback tests
# ---------------------------------------------------------------------------


class TestRegexFallback:
    def test_gibberish_number_not_in_file_returns_no_results(self):
        result = search_in_file(str(FIXTURE), "99999999")
        assert isinstance(result, dict)
        assert result.get("error") == "no_results"

    def test_no_results_error_has_required_keys(self):
        result = search_in_file(str(FIXTURE), "99999999")
        assert isinstance(result, dict)
        required = {"error", "query", "file", "spans_searched"}
        assert required.issubset(result.keys()), f"Missing keys: {required - result.keys()}"

    def test_no_results_error_echoes_query(self):
        query = "99999999"
        result = search_in_file(str(FIXTURE), query)
        assert isinstance(result, dict)
        assert result["query"] == query

    def test_gibberish_text_returns_no_results(self):
        result = search_in_file(str(FIXTURE), "xyzzyplugh")
        assert isinstance(result, dict)
        assert result.get("error") == "no_results"

    def test_no_digit_query_no_regex_attempt(self):
        # "xyzzyplugh" has no digits or FY — should return no_results without regex
        result = search_in_file(str(FIXTURE), "xyzzyplugh")
        assert isinstance(result, dict)
        assert result["error"] == "no_results"

    def test_spans_searched_count_in_no_results(self):
        result = search_in_file(str(FIXTURE), "99999999")
        assert isinstance(result, dict)
        assert isinstance(result["spans_searched"], int)
        assert result["spans_searched"] > 0

    def test_known_number_in_file_found_via_bm25_or_regex(self):
        # "406" appears in the national defense row (line 130).
        # Either BM25 or regex fallback should find it.
        result = search_in_file(str(FIXTURE), "406")
        # Should NOT be a no-results error
        if isinstance(result, dict):
            assert result.get("error") != "no_results", (
                f"Expected to find '406' but got: {result}"
            )
        else:
            assert isinstance(result, list)
            assert len(result) > 0

    def test_fy_abbreviation_in_query_triggers_normalisation(self):
        # "FY1941" should normalise to "fiscal year 1941" before BM25.
        # The fixture covers FY1941 data so BM25 or regex should find something.
        result = search_in_file(str(FIXTURE), "FY1941")
        assert not (isinstance(result, dict) and result.get("error") == "no_results"), (
            f"Expected results for FY1941 query, got: {result}"
        )
