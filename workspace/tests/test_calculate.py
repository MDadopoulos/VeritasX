"""
test_calculate.py — Comprehensive test suite for calculate.py

Covers:
    calculate()    -- safe expression evaluation, AST whitelist, Decimal precision
    pct_change()   -- direction, rounding, unit mismatch, edge cases
    sum_values()   -- count enforcement, unit warnings, value conversion

All numeric assertions use Decimal comparisons, not float.

Note: calculate, pct_change, sum_values are @tool-decorated StructuredTool instances.
Use .run(expr) for single-arg tools, .invoke({...}) for multi-arg tools.
"""

import pytest
from decimal import Decimal

from src.tools.calculate import calculate, pct_change, sum_values


# ---------------------------------------------------------------------------
# calculate() tests
# ---------------------------------------------------------------------------


class TestCalculateBasicArithmetic:
    def test_addition(self):
        r = calculate.run("2 + 3")
        assert r == {"result": Decimal("5")}

    def test_subtraction(self):
        r = calculate.run("10 - 3")
        assert r == {"result": Decimal("7")}

    def test_multiplication(self):
        r = calculate.run("4 * 5")
        assert r == {"result": Decimal("20")}

    def test_division_exact(self):
        r = calculate.run("10 / 2")
        assert "result" in r
        assert r["result"] == Decimal("5")

    def test_division_repeating(self):
        """10 / 3 should return a high-precision Decimal, not a float."""
        r = calculate.run("10 / 3")
        assert "result" in r
        assert isinstance(r["result"], Decimal)
        # Should have many decimal places, not just 0.333...
        assert r["result"] > Decimal("3.333")
        assert r["result"] < Decimal("3.334")

    def test_operator_precedence(self):
        """2 + 3 * 4 == 14, not 20."""
        r = calculate.run("2 + 3 * 4")
        assert r == {"result": Decimal("14")}

    def test_parentheses_override_precedence(self):
        r = calculate.run("(2 + 3) * 4")
        assert r == {"result": Decimal("20")}

    def test_unary_minus(self):
        r = calculate.run("-5 + 3")
        assert r == {"result": Decimal("-2")}

    def test_power(self):
        r = calculate.run("2 ** 10")
        assert r == {"result": Decimal("1024")}

    def test_modulo(self):
        r = calculate.run("10 % 3")
        assert r == {"result": Decimal("1")}


class TestCalculateDecimalPrecision:
    def test_pi_multiplication_exact(self):
        """3.14 * 100 must return exactly 314.00, not 314.0000...124."""
        r = calculate.run("3.14 * 100")
        assert "result" in r
        # Must equal 314 exactly (no float contamination)
        assert r["result"] == Decimal("314")
        # String representation should not have float imprecision
        result_str = str(r["result"])
        assert "124" not in result_str, f"Float contamination detected: {result_str}"

    def test_complex_expression(self):
        """(1580 + 6404) * 1000000 — exact integer result."""
        r = calculate.run("(1580 + 6404) * 1000000")
        assert "result" in r
        assert r["result"] == Decimal("7984000000")

    def test_known_financial_addition(self):
        """2602 + 44463 — values from OfficeQA benchmark."""
        r = calculate.run("2602 + 44463")
        assert "result" in r
        assert r["result"] == Decimal("47065")

    def test_result_is_decimal_not_float(self):
        """All results must be Decimal instances."""
        r = calculate.run("1 + 1")
        assert isinstance(r["result"], Decimal)


class TestCalculateErrorHandling:
    def test_empty_string(self):
        r = calculate.run("")
        assert r["error"] == "INVALID_INPUT"

    def test_whitespace_only(self):
        r = calculate.run("   ")
        assert r["error"] == "INVALID_INPUT"

    def test_syntax_error_incomplete(self):
        r = calculate.run("2 +")
        assert r["error"] == "SYNTAX_ERROR"

    def test_division_by_zero(self):
        r = calculate.run("1 / 0")
        assert r["error"] == "DIVISION_BY_ZERO"

    def test_division_by_zero_expression(self):
        r = calculate.run("100 / (5 - 5)")
        assert r["error"] == "DIVISION_BY_ZERO"


class TestCalculateDisallowedNodes:
    def test_import_via_dunder(self):
        """__import__('os') must be rejected."""
        r = calculate.run("__import__('os')")
        assert r["error"] == "DISALLOWED_NODE"

    def test_function_call(self):
        """foo(1) contains a Call node — must be rejected."""
        r = calculate.run("foo(1)")
        assert r["error"] == "DISALLOWED_NODE"

    def test_attribute_access(self):
        """x.y contains an Attribute node — must be rejected."""
        r = calculate.run("x.y")
        assert r["error"] == "DISALLOWED_NODE"

    def test_list_literal(self):
        """[1, 2] contains a List node — must be rejected."""
        r = calculate.run("[1, 2]")
        assert r["error"] == "DISALLOWED_NODE"

    def test_name_reference(self):
        """Bare name reference like 'x' contains a Name node — must be rejected."""
        r = calculate.run("x + 1")
        assert r["error"] == "DISALLOWED_NODE"


# ---------------------------------------------------------------------------
# pct_change() tests
# ---------------------------------------------------------------------------


class TestPctChangeDirection:
    def test_positive_change(self):
        """2602 -> 3100 is a positive increase."""
        r = pct_change.invoke({"old": 2602, "new": 3100})
        assert "result" in r
        assert r["result"] == Decimal("19.14")

    def test_negative_change(self):
        """3100 -> 2602 is a decrease — result must be negative."""
        r = pct_change.invoke({"old": 3100, "new": 2602})
        assert "result" in r
        assert r["result"] < Decimal("0")

    def test_large_change_benchmark_uid0004(self):
        """pct_change(2602, 44463) must equal 1608.80 per UID0004 benchmark."""
        r = pct_change.invoke({"old": 2602, "new": 44463})
        assert "result" in r
        assert r["result"] == Decimal("1608.80")

    def test_no_change(self):
        """Same old and new -> 0.00."""
        r = pct_change.invoke({"old": 100, "new": 100})
        assert "result" in r
        assert r["result"] == Decimal("0.00")


class TestPctChangeInputTypes:
    def test_string_inputs(self):
        """str inputs should produce same result as int inputs."""
        r_int = pct_change.invoke({"old": 2602, "new": 3100})
        r_str = pct_change.invoke({"old": "2602", "new": "3100"})
        assert r_str["result"] == r_int["result"]

    def test_float_inputs(self):
        """float inputs converted via str() to avoid contamination."""
        r = pct_change.invoke({"old": 2602.0, "new": 3100.0})
        assert "result" in r
        assert r["result"] == Decimal("19.14")

    def test_decimal_inputs(self):
        """Decimal inputs should work directly."""
        r = pct_change.invoke({"old": Decimal("2602"), "new": Decimal("3100")})
        assert "result" in r
        assert r["result"] == Decimal("19.14")

    def test_result_is_decimal(self):
        r = pct_change.invoke({"old": 100, "new": 200})
        assert isinstance(r["result"], Decimal)

    def test_result_rounded_to_2dp(self):
        """Result must be rounded to exactly 2 decimal places."""
        r = pct_change.invoke({"old": 3, "new": 4})
        result_str = str(r["result"])
        # Should have at most 2 decimal places
        if "." in result_str:
            decimal_part = result_str.split(".")[1]
            assert len(decimal_part) <= 2, f"More than 2dp: {result_str}"


class TestPctChangeErrors:
    def test_zero_old_value(self):
        r = pct_change.invoke({"old": 0, "new": 100})
        assert r["error"] == "DIVISION_BY_ZERO"

    def test_invalid_old_value(self):
        r = pct_change.invoke({"old": "abc", "new": 100})
        assert r["error"] == "INVALID_INPUT"

    def test_invalid_new_value(self):
        r = pct_change.invoke({"old": 100, "new": "xyz"})
        assert r["error"] == "INVALID_INPUT"


class TestPctChangeUnitMismatch:
    def test_unit_mismatch_millions_vs_billions(self):
        r = pct_change.invoke({"old": 100, "new": 200, "unit_old": "millions", "unit_new": "billions"})
        assert r["error"] == "UNIT_MISMATCH"

    def test_unit_mismatch_thousands_vs_millions(self):
        r = pct_change.invoke({"old": 100, "new": 200, "unit_old": "thousands", "unit_new": "millions"})
        assert r["error"] == "UNIT_MISMATCH"

    def test_units_match_singular_plural(self):
        """'millions' and 'million' normalize to the same unit — should succeed."""
        r = pct_change.invoke({"old": 100, "new": 200, "unit_old": "millions", "unit_new": "million"})
        assert "result" in r
        assert r.get("error") is None

    def test_units_match_both_same(self):
        r = pct_change.invoke({"old": 100, "new": 200, "unit_old": "billion", "unit_new": "billion"})
        assert "result" in r

    def test_one_unit_none_passes_through(self):
        """Unlabeled values (unit=None) pass through without unit check."""
        from src.tools.calculate import _pct_change_impl
        r = _pct_change_impl(100, 200, unit_old="millions", unit_new=None)
        assert "result" in r
        assert r.get("error") is None

    def test_both_units_none_passes_through(self):
        from src.tools.calculate import _pct_change_impl
        r = _pct_change_impl(100, 200, unit_old=None, unit_new=None)
        assert "result" in r

    def test_unit_old_empty_string_passes_through(self):
        """Empty string unit is treated as absent — passes through."""
        r = pct_change.invoke({"old": 100, "new": 200, "unit_old": "", "unit_new": "millions"})
        assert "result" in r


# ---------------------------------------------------------------------------
# sum_values() tests
# ---------------------------------------------------------------------------


class TestSumValuesBasic:
    def test_basic_sum_three_pairs(self):
        pairs = [("Revenue", 100), ("Cost", 50), ("Tax", 25)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 3})
        assert "result" in r
        assert r["result"] == Decimal("175")
        assert r["pair_count"] == 3

    def test_two_pairs(self):
        pairs = [("A", 1000), ("B", 2000)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert r["result"] == Decimal("3000")
        assert r["pair_count"] == 2

    def test_result_is_decimal(self):
        pairs = [("X", 10), ("Y", 20)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert isinstance(r["result"], Decimal)


class TestSumValuesCountMismatch:
    def test_fewer_pairs_than_expected(self):
        pairs = [("A", 10), ("B", 20)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 3})
        assert r["error"] == "COUNT_MISMATCH"
        assert r["actual_count"] == 2
        assert "3" in r["reason"]
        assert "2" in r["reason"]

    def test_more_pairs_than_expected(self):
        pairs = [("A", 10), ("B", 20), ("C", 30)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert r["error"] == "COUNT_MISMATCH"
        assert r["actual_count"] == 3

    def test_empty_list_expected_one(self):
        r = sum_values.invoke({"pairs": [], "expected_count": 1})
        assert r["error"] == "COUNT_MISMATCH"
        assert r["actual_count"] == 0


class TestSumValuesValueConversion:
    def test_string_values(self):
        pairs = [("Label A", "100.50"), ("Label B", "200.25")]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert r["result"] == Decimal("300.75")

    def test_float_values(self):
        pairs = [("A", 1.5), ("B", 2.5)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert r["result"] == Decimal("4")

    def test_decimal_values(self):
        pairs = [("A", Decimal("10.5")), ("B", Decimal("9.5"))]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert r["result"] == Decimal("20.0")

    def test_invalid_value_returns_error(self):
        pairs = [("A", 10), ("B", "abc")]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert r["error"] == "INVALID_INPUT"
        assert "B" in r["reason"]


class TestSumValuesUnitWarning:
    def test_heterogeneous_units_produce_warning(self):
        """Labels with 'millions' and 'billions' -> unit_warning included."""
        pairs = [
            ("Revenue in millions", 100),
            ("Expenditure in billions", 50),
        ]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert "unit_warning" in r
        assert "billion" in r["unit_warning"]
        assert "million" in r["unit_warning"]

    def test_heterogeneous_units_still_sums(self):
        """Unit warning does NOT prevent sum — warning only."""
        pairs = [
            ("Revenue in millions", 100),
            ("Expenditure in billions", 50),
        ]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert r["result"] == Decimal("150")

    def test_homogeneous_units_no_warning(self):
        """All labels have 'millions' -> no unit_warning."""
        pairs = [
            ("Revenue in millions", 100),
            ("Cost in millions", 50),
        ]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert "unit_warning" not in r

    def test_no_unit_labels_no_warning(self):
        """Plain labels without unit words -> no unit_warning."""
        pairs = [("Revenue", 100), ("Cost", 50)]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        assert "unit_warning" not in r

    def test_thousands_and_millions_heterogeneous(self):
        pairs = [
            ("Small item in thousands", 500),
            ("Big item in millions", 10),
        ]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "unit_warning" in r

    def test_unit_plural_normalizes_to_singular_for_comparison(self):
        """'millions' and 'million' should be treated as the same unit."""
        pairs = [
            ("Revenue in millions", 100),
            ("Cost in million", 50),
        ]
        r = sum_values.invoke({"pairs": pairs, "expected_count": 2})
        assert "result" in r
        # Both normalize to 'million' -> homogeneous -> no warning
        assert "unit_warning" not in r
