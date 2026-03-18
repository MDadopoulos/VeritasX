"""
Tests for extract_table_block.py

Covers:
- Basic extraction: anchor found, single table returned with correct fields
- Anchor not found -> NO_TABLE_FOUND error
- Empty span_text -> INVALID_INPUT error
- Empty anchor -> INVALID_INPUT error
- Table with no footnotes -> footnotes field is empty string
- Two tables in span -> both returned in list
- Unit annotation "(In millions of dollars)" captured correctly
- Multi-row column headers preserved (before | --- | separator)
- 1941_01 fixture: real corpus table extraction
- 1954_02 fixture: monthly table with year-prefixed rows
"""

import os
import pytest
from pathlib import Path

# Add workspace/src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tools.extract_table_block import extract_table_block

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper: load fixture content
# ---------------------------------------------------------------------------

def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------

def test_empty_span_text_returns_invalid_input():
    result = extract_table_block("", "some anchor")
    assert result.get("error") == "INVALID_INPUT"
    assert "span_text" in result["reason"].lower()


def test_whitespace_only_span_text_returns_invalid_input():
    result = extract_table_block("   \n  \t  ", "some anchor")
    assert result.get("error") == "INVALID_INPUT"


def test_empty_anchor_returns_invalid_input():
    result = extract_table_block("some text\n| col1 | col2 |", "")
    assert result.get("error") == "INVALID_INPUT"
    assert "anchor" in result["reason"].lower()


def test_whitespace_only_anchor_returns_invalid_input():
    result = extract_table_block("some text\n| col1 | col2 |", "   ")
    assert result.get("error") == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# No table found
# ---------------------------------------------------------------------------

def test_anchor_not_in_span_returns_no_table_found():
    span = "This is some text.\nNo tables here at all."
    result = extract_table_block(span, "missing anchor phrase")
    assert result.get("error") == "NO_TABLE_FOUND"


def test_anchor_found_but_no_pipe_table_within_15_lines():
    # Anchor at line 0, no pipe table within 15 lines
    lines = ["The anchor phrase is here."]
    for i in range(20):
        lines.append(f"Plain text line {i}")
    lines.append("| col1 | col2 |")  # Line 22, too far
    span = "\n".join(lines)
    result = extract_table_block(span, "anchor phrase")
    assert result.get("error") == "NO_TABLE_FOUND"


# ---------------------------------------------------------------------------
# Basic single table extraction
# ---------------------------------------------------------------------------

def test_single_table_basic_extraction():
    span = (
        "Federal Receipts and Expenditures\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Item | 1940 | 1941 |\n"
        "| --- | --- | --- |\n"
        "| Receipts | 5387 | 7013 |\n"
        "| Expenditures | 9468 | 13653 |\n"
        "| Net deficit | 4081 | 6640 |\n"
    )
    result = extract_table_block(span, "Federal Receipts")
    assert "error" not in result
    assert "tables" in result
    assert len(result["tables"]) == 1

    table = result["tables"][0]
    assert "Item" in table["table_text"]
    assert "Receipts" in table["table_text"]
    assert table["unit_annotation"] is not None
    assert "millions" in table["unit_annotation"].lower()
    assert "Federal Receipts" in table["prose_context"]
    assert table["footnotes"] == ""


def test_unit_annotation_captured():
    span = (
        "Table Title Here\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Column A | Column B |\n"
        "| --- | --- |\n"
        "| 100 | 200 |\n"
    )
    result = extract_table_block(span, "Table Title")
    assert "error" not in result
    table = result["tables"][0]
    assert table["unit_annotation"] is not None
    assert "(In millions of dollars)" in table["unit_annotation"]


def test_table_with_footnotes_included():
    span = (
        "Budget Summary\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Year | Receipts | Expenditures |\n"
        "| --- | --- | --- |\n"
        "| 1948 | 42211 | 33,791 14/ |\n"
        "| 1949 | 38246 | 40,057 14/ |\n"
        "\n"
        "Source: Daily Treasury Statement.\n"
        "14/ Revised figures.\n"
    )
    result = extract_table_block(span, "Budget Summary")
    assert "error" not in result
    table = result["tables"][0]
    assert "Source" in table["footnotes"] or "14/" in table["footnotes"]


def test_table_without_footnotes_has_empty_footnotes_field():
    span = (
        "Simple Table\n"
        "| A | B |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
        "\n"
        "Next section starts here.\n"
    )
    result = extract_table_block(span, "Simple Table")
    assert "error" not in result
    table = result["tables"][0]
    assert table["footnotes"] == ""


# ---------------------------------------------------------------------------
# Multi-row column headers
# ---------------------------------------------------------------------------

def test_multi_row_column_headers_preserved():
    span = (
        "Detailed Table\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Period | Revenue > Col A | Revenue > Col B |\n"
        "| Period | Sub-label A | Sub-label B |\n"
        "| --- | --- | --- |\n"
        "| January | 100 | 200 |\n"
        "| February | 150 | 250 |\n"
    )
    result = extract_table_block(span, "Detailed Table")
    assert "error" not in result
    table = result["tables"][0]
    # Both header rows should be in table_text
    assert "Revenue > Col A" in table["table_text"]
    assert "Sub-label A" in table["table_text"]
    assert "January" in table["table_text"]


# ---------------------------------------------------------------------------
# Multiple tables in one span
# ---------------------------------------------------------------------------

def test_two_tables_in_span_returns_both():
    span = (
        "First Table\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Item | Value |\n"
        "| --- | --- |\n"
        "| Revenue | 1000 |\n"
        "\n"
        "Second Table\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Category | Amount |\n"
        "| --- | --- |\n"
        "| Defense | 5000 |\n"
    )
    result = extract_table_block(span, "First Table")
    assert "error" not in result
    assert len(result["tables"]) == 2
    # First table has "Revenue"
    assert "Revenue" in result["tables"][0]["table_text"]
    # Second table has "Defense"
    assert "Defense" in result["tables"][1]["table_text"]


# ---------------------------------------------------------------------------
# Case-insensitive anchor matching
# ---------------------------------------------------------------------------

def test_anchor_matching_is_case_insensitive():
    span = (
        "SUMMARY OF FEDERAL FISCAL OPERATIONS\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Period | Net receipts |\n"
        "| --- | --- |\n"
        "| 1953 | 65218 |\n"
    )
    result = extract_table_block(span, "summary of federal fiscal operations")
    assert "error" not in result
    assert len(result["tables"]) == 1


# ---------------------------------------------------------------------------
# Start/end line tracking
# ---------------------------------------------------------------------------

def test_start_line_is_1_indexed():
    span = (
        "Line 1\n"
        "Line 2\n"
        "Line 3 - anchor\n"
        "\n"
        "(In millions of dollars)\n"
        "\n"
        "| Col |\n"
        "| --- |\n"
        "| 42 |\n"
    )
    result = extract_table_block(span, "anchor")
    assert "error" not in result
    table = result["tables"][0]
    # Pipe table starts at line 7 (1-indexed): lines 1-3 text, 4 blank, 5 unit, 6 blank, 7 pipe
    assert table["start_line"] == 7


# ---------------------------------------------------------------------------
# 15-line lookahead limit
# ---------------------------------------------------------------------------

def test_pipe_table_within_lookahead_window_is_found():
    # Anchor at line 0, pipe table at line 14 (0-indexed) = 15th line total,
    # within the range(0, 15) = lines 0..14 lookahead window.
    lines = ["The anchor is here."]
    # Add 13 intervening lines (indices 1-13), pipe at index 14
    for i in range(13):
        lines.append(f"Intervening line {i}")
    lines.append("| Col | Val |")
    lines.append("| --- | --- |")
    lines.append("| Jan | 100 |")
    span = "\n".join(lines)
    result = extract_table_block(span, "anchor")
    assert "error" not in result


def test_pipe_table_outside_lookahead_window_not_found():
    # Anchor at line 0, pipe table at line 15 (0-indexed) = beyond range(0, 15)
    lines = ["The anchor is here."]
    # 14 intervening lines => pipe at index 15, outside window
    for i in range(14):
        lines.append(f"Intervening line {i}")
    lines.append("| Col | Val |")
    span = "\n".join(lines)
    result = extract_table_block(span, "anchor")
    assert result.get("error") == "NO_TABLE_FOUND"


# ---------------------------------------------------------------------------
# Real fixture tests
# ---------------------------------------------------------------------------

def test_1941_fixture_single_table_extraction():
    """Test real corpus fixture from 1941 bulletin."""
    content = load_fixture("treasury_bulletin_1941_01.txt")
    # Use a known phrase from the 1941 fixture
    result = extract_table_block(content, "Budget Receipte and Expendituree")
    assert "error" not in result
    assert len(result["tables"]) >= 1
    table = result["tables"][0]
    assert table["table_text"].startswith("|")
    assert "Receipte" in table["table_text"] or "Expendituree" in table["table_text"]


def test_1954_fixture_monthly_rows_present():
    """Test 1954_02 fixture contains monthly table data."""
    content = load_fixture("treasury_bulletin_1954_02.txt")
    result = extract_table_block(content, "SUMMARY OF FEDERAL FISCAL OPERATIONS")
    assert "error" not in result
    assert len(result["tables"]) >= 1
    table = result["tables"][0]
    # Should contain month rows
    assert "January" in table["table_text"] or "1952-January" in table["table_text"]


def test_1954_fixture_unit_annotation_captured():
    """Unit annotation (In millions of dollars) captured in 1954 fixture."""
    content = load_fixture("treasury_bulletin_1954_02.txt")
    result = extract_table_block(content, "SUMMARY OF FEDERAL FISCAL OPERATIONS")
    assert "error" not in result
    table = result["tables"][0]
    assert table["unit_annotation"] is not None
    assert "millions" in table["unit_annotation"].lower()


def test_1954_fixture_footnotes_captured():
    """Footnotes with Source: prefix captured from 1954 fixture."""
    content = load_fixture("treasury_bulletin_1954_02.txt")
    result = extract_table_block(content, "SUMMARY OF FEDERAL FISCAL OPERATIONS")
    assert "error" not in result
    table = result["tables"][0]
    assert "Source" in table["footnotes"] or "1/" in table["footnotes"]


def test_1954_fixture_two_tables_found():
    """1954 fixture has two separate tables near fiscal operations content."""
    content = load_fixture("treasury_bulletin_1954_02.txt")
    result = extract_table_block(content, "SUMMARY OF FEDERAL FISCAL OPERATIONS")
    assert "error" not in result
    # The fixture contains the summary table AND the table 1 receipts table
    assert len(result["tables"]) >= 2


def test_all_table_rows_included_not_truncated():
    """Table body is never truncated at 15 lines; all rows collected."""
    # Build a table with 30 data rows
    rows = ["Anchor phrase here", "", "(In millions of dollars)", ""]
    rows.append("| Month | Value |")
    rows.append("| --- | --- |")
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    for i in range(30):
        month = months[i % 12]
        rows.append(f"| {month} | {1000 + i} |")
    span = "\n".join(rows)
    result = extract_table_block(span, "Anchor phrase")
    assert "error" not in result
    table = result["tables"][0]
    # Count pipe rows in table_text
    pipe_rows = [l for l in table["table_text"].splitlines() if l.startswith("|")]
    assert len(pipe_rows) == 32  # 1 header + 1 separator + 30 data rows
