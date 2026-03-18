"""
Tests for classify_table_rows.py

Covers:
- Simple table with header, month rows, total row -> correct bucket assignment
- Ambiguous "1940 Total" row -> classified as aggregate
- "12-month average" -> aggregate
- "Jan-Dec cumulative" -> aggregate
- Separator row | --- | --- | -> header
- Year inheritance: 1953-January followed by February -> February gets year="1953"
- Cell value parsing: commas, footnote suffixes, parenthetical negatives, null cells
- Empty table_text -> INVALID_INPUT error
- Multi-row column headers all classified as header_rows
- Bare year rows (1942, 1953) -> aggregate
- Year with annotation "1954 (Est.)" -> aggregate
- "Fiscal years:" / "Calendar years:" rows -> header
- "Cal. yr" -> aggregate
- "1954 to date" -> aggregate
- parse_cell_value module-level function directly
"""

import pytest
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.classify_table_rows import classify_table_rows, parse_cell_value


# ---------------------------------------------------------------------------
# parse_cell_value unit tests
# ---------------------------------------------------------------------------

def test_parse_cell_value_plain_integer():
    assert parse_cell_value("1234") == Decimal("1234")


def test_parse_cell_value_with_commas():
    assert parse_cell_value("1,580") == Decimal("1580")


def test_parse_cell_value_footnote_suffix_slash():
    assert parse_cell_value("1,580 3/") == Decimal("1580")


def test_parse_cell_value_footnote_suffix_two_digits():
    assert parse_cell_value("33,791 14/") == Decimal("33791")


def test_parse_cell_value_revised_marker():
    assert parse_cell_value("6,052r") == Decimal("6052")


def test_parse_cell_value_parenthetical_negative():
    assert parse_cell_value("(1234)") == Decimal("-1234")


def test_parse_cell_value_parenthetical_negative_with_comma():
    assert parse_cell_value("(1,234)") == Decimal("-1234")


def test_parse_cell_value_null_dash():
    assert parse_cell_value("-") is None


def test_parse_cell_value_null_double_dash():
    assert parse_cell_value("--") is None


def test_parse_cell_value_null_nan():
    assert parse_cell_value("nan") is None


def test_parse_cell_value_null_na():
    assert parse_cell_value("N/A") is None


def test_parse_cell_value_empty_string():
    assert parse_cell_value("") is None


def test_parse_cell_value_n_a_dot():
    assert parse_cell_value("n.a.") is None


def test_parse_cell_value_plus_prefix():
    assert parse_cell_value("+241") == Decimal("241")


def test_parse_cell_value_negative_plain():
    assert parse_cell_value("-21490.0") == Decimal("-21490.0")


def test_parse_cell_value_decimal():
    assert parse_cell_value("39482.03") == Decimal("39482.03")


def test_parse_cell_value_float_string():
    assert parse_cell_value("3.14") == Decimal("3.14")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_empty_table_text_returns_invalid_input():
    result = classify_table_rows("")
    assert result.get("error") == "INVALID_INPUT"
    assert "table_text" in result["reason"].lower()


def test_whitespace_only_returns_invalid_input():
    result = classify_table_rows("   \n  \t  ")
    assert result.get("error") == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# Simple table: header, month rows, total
# ---------------------------------------------------------------------------

SIMPLE_TABLE = """\
| Fiscal year or month | Receipts | Expenditures |
| --- | --- | --- |
| January | 5061 | 5737 |
| February | 5479 | 5595 |
| March | 10502 | 6187 |
| Total | 21042 | 17519 |
"""

def test_simple_table_month_rows():
    result = classify_table_rows(SIMPLE_TABLE)
    assert "error" not in result
    months = [r["label"] for r in result["month_rows"]]
    assert "January" in months
    assert "February" in months
    assert "March" in months
    assert len(result["month_rows"]) == 3


def test_simple_table_aggregate_row():
    result = classify_table_rows(SIMPLE_TABLE)
    aggregates = [r["label"] for r in result["aggregate_rows"]]
    assert "Total" in aggregates


def test_simple_table_header_rows():
    result = classify_table_rows(SIMPLE_TABLE)
    # Header rows: column header row + separator row
    assert len(result["header_rows"]) >= 2


def test_simple_table_values_parsed():
    result = classify_table_rows(SIMPLE_TABLE)
    january = next(r for r in result["month_rows"] if r["label"] == "January")
    assert january["values"][0] == Decimal("5061")
    assert january["values"][1] == Decimal("5737")


# ---------------------------------------------------------------------------
# Ambiguous row classification
# ---------------------------------------------------------------------------

def test_1940_total_is_aggregate():
    table = "| Col |\n| --- |\n| 1940 Total | 12345 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "1940 Total" in agg_labels


def test_twelve_month_average_is_aggregate():
    table = "| Col |\n| --- |\n| 12-month average | 5000 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "12-month average" in agg_labels


def test_jan_dec_cumulative_is_aggregate():
    table = "| Col |\n| --- |\n| Jan-Dec cumulative | 60000 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "Jan-Dec cumulative" in agg_labels


def test_bare_year_is_aggregate():
    table = "| Year | Value |\n| --- | --- |\n| 1942 | 16290 |\n| 1943 | 34483 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "1942" in agg_labels
    assert "1943" in agg_labels


def test_year_with_est_annotation_is_aggregate():
    table = "| Year | Value |\n| --- | --- |\n| 1954 (Est.) | 67628 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "1954 (Est.)" in agg_labels


def test_cal_yr_is_aggregate():
    table = "| Col |\n| --- |\n| Cal. yr | 30524 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "Cal. yr" in agg_labels


def test_to_date_is_aggregate():
    table = "| Col |\n| --- |\n| 1954 to date | 26137 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "1954 to date" in agg_labels


# ---------------------------------------------------------------------------
# Separator row
# ---------------------------------------------------------------------------

def test_separator_row_is_header():
    table = "| Col A | Col B |\n| --- | --- |\n| January | 100 |\n"
    result = classify_table_rows(table)
    assert "error" not in result
    header_labels = [r["label"] for r in result["header_rows"]]
    # The separator row itself should be in headers
    separator_found = any("---" in r["raw"] for r in result["header_rows"])
    assert separator_found


# ---------------------------------------------------------------------------
# Year inheritance
# ---------------------------------------------------------------------------

def test_year_inheritance_basic():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| 1953-January | 5061 |\n"
        "| February | 5479 |\n"
        "| March | 10502 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result

    months = {r["label"]: r for r in result["month_rows"]}
    assert "1953-January" in months
    assert months["1953-January"]["year"] == "1953"
    assert "February" in months
    assert months["February"]["year"] == "1953"
    assert "March" in months
    assert months["March"]["year"] == "1953"


def test_year_inheritance_resets_on_new_prefix():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| 1952-January | 4953 |\n"
        "| February | 5553 |\n"
        "| 1953-January | 5061 |\n"
        "| February | 5479 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result

    months = result["month_rows"]
    # First January: year 1952
    assert months[0]["year"] == "1952"
    # First February: inherited 1952
    assert months[1]["year"] == "1952"
    # Second January: year 1953
    assert months[2]["year"] == "1953"
    # Second February: inherited 1953
    assert months[3]["year"] == "1953"


def test_year_none_before_any_prefix():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| January | 5061 |\n"
        "| February | 5479 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result

    months = result["month_rows"]
    assert months[0]["year"] is None
    assert months[1]["year"] is None


# ---------------------------------------------------------------------------
# Multi-row column headers
# ---------------------------------------------------------------------------

def test_multi_row_column_headers_all_in_header_rows():
    table = (
        "| Period | Revenue > Col A | Revenue > Col B |\n"
        "| Period | Sub-label A | Sub-label B |\n"
        "| --- | --- | --- |\n"
        "| January | 100 | 200 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    # Rows before separator should all be headers
    header_labels = [r["label"] for r in result["header_rows"]]
    assert "Period" in header_labels
    # There should be at least 3 header rows (2 header rows + separator)
    assert len(result["header_rows"]) >= 3


# ---------------------------------------------------------------------------
# Cell value footnote suffixes in real data
# ---------------------------------------------------------------------------

def test_footnote_values_in_table_parsed():
    table = (
        "| Year | Total | Defense |\n"
        "| --- | --- | --- |\n"
        "| 1948 | 33,791 14/ | 11500 |\n"
        "| 1949 | 40,057 14/ | 12158 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    agg_rows = result["aggregate_rows"]
    assert len(agg_rows) == 2
    assert agg_rows[0]["values"][0] == Decimal("33791")
    assert agg_rows[1]["values"][0] == Decimal("40057")


def test_revised_values_in_table_parsed():
    table = (
        "| Period | Receipts | Expenditures |\n"
        "| --- | --- | --- |\n"
        "| July | 3,293r | 6,052r |\n"
        "| August | 4,475r | 5,948r |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    months = result["month_rows"]
    assert len(months) == 2
    assert months[0]["values"][0] == Decimal("3293")
    assert months[0]["values"][1] == Decimal("6052")


# ---------------------------------------------------------------------------
# Fiscal years / Calendar years sub-header rows
# ---------------------------------------------------------------------------

def test_fiscal_years_label_is_header():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| Fiscal years: | nan |\n"
        "| 1942 | 16290 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    header_labels = [r["label"] for r in result["header_rows"]]
    assert "Fiscal years:" in header_labels


def test_calendar_years_label_is_header():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| Calendar years: | nan |\n"
        "| 1942 | 16290 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    header_labels = [r["label"] for r in result["header_rows"]]
    assert "Calendar years:" in header_labels


def test_months_sub_header_is_header():
    table = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| Months: | nan |\n"
        "| 1952-January | 4953 |\n"
    )
    result = classify_table_rows(table)
    assert "error" not in result
    header_labels = [r["label"] for r in result["header_rows"]]
    assert "Months:" in header_labels


# ---------------------------------------------------------------------------
# Real corpus fixture integration
# ---------------------------------------------------------------------------

def test_1954_fixture_month_rows_classified():
    """Test month rows from real 1954 corpus data (includes separator as in real extract_table_block output)."""
    # Includes the header row + separator as extract_table_block would return
    table_text = (
        "| Period | Net receipts | Expenditures | Surplus |\n"
        "| --- | --- | --- | --- |\n"
        "| Months: | nan | nan | nan |\n"
        "| 1952-January | 4953 | 5455 | -501.0 |\n"
        "| February | 5553 | 5105 | 448.0 |\n"
        "| March | 9886 | 5704 | 4182.0 |\n"
    )
    result = classify_table_rows(table_text)
    assert "error" not in result
    # Months: is a header (colon suffix)
    header_labels = [r["label"] for r in result["header_rows"]]
    assert "Months:" in header_labels
    # Month rows
    month_labels = [r["label"] for r in result["month_rows"]]
    assert "1952-January" in month_labels
    assert "February" in month_labels
    assert "March" in month_labels
    # Year inheritance
    months = {r["label"]: r for r in result["month_rows"]}
    assert months["1952-January"]["year"] == "1952"
    assert months["February"]["year"] == "1952"
    assert months["March"]["year"] == "1952"


def test_1954_fixture_aggregate_rows_classified():
    """Test aggregate rows from real 1954 corpus data."""
    table_text = (
        "| Period | Value |\n"
        "| --- | --- |\n"
        "| Fiscal years: | nan |\n"
        "| 1942 | 12696 |\n"
        "| 1953 | 65218 |\n"
        "| 1954 (Est.) | 67628 |\n"
        "| 1955 (Est.) | 62642 |\n"
        "| Calendar years: | nan |\n"
        "| 1942 | 16290 |\n"
    )
    result = classify_table_rows(table_text)
    assert "error" not in result
    agg_labels = [r["label"] for r in result["aggregate_rows"]]
    assert "1942" in agg_labels
    assert "1953" in agg_labels
    assert "1954 (Est.)" in agg_labels
    # Should have no month rows
    assert len(result["month_rows"]) == 0
