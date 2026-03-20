"""
test_normalize_answer.py — Tests for normalize_answer tool (CAL-06, TST-04).

Strategy:
- Parametrized tests load every example from format_survey.json fixture and
  assert normalize(raw) == expected. This covers all 11 survey categories
  (A-K) plus edge cases.
- Explicit additional tests cover invalid input, unicode minus, trailing
  zeros, comma handling, and each pass-through type.
"""

import json
import pytest
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "format_survey.json"


def load_survey():
    """Load all (raw, expected, category) tuples from the format survey fixture."""
    with open(FIXTURE, encoding="utf-8") as f:
        data = json.load(f)
    cases = []
    for cat_name, cat in data["categories"].items():
        for ex in cat["examples"]:
            cases.append((ex["raw"], ex["expected"], cat_name))
    for ec in data["edge_cases"]:
        cases.append((ec["raw"], ec["expected"], ec.get("note", "edge")))
    return cases


@pytest.mark.parametrize("raw,expected,category", load_survey())
def test_normalize_matches_benchmark(raw, expected, category):
    """Every example in format_survey.json must normalize to the exact benchmark value."""
    from src.tools.normalize_answer import normalize_answer
    result = normalize_answer(raw, "test_token")
    assert "result" in result, (
        f"Expected success for category '{category}': normalize({raw!r}), got {result}"
    )
    assert result["result"] == expected, (
        f"Category '{category}': normalize({raw!r}) = {result['result']!r}, expected {expected!r}"
    )


# ---------------------------------------------------------------------------
# Invalid input tests
# ---------------------------------------------------------------------------

class TestInvalidInput:
    """normalize_answer must return INVALID_INPUT error dict for bad inputs."""

    def test_none_input(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer(None, "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result

    def test_empty_string(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("", "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result

    def test_whitespace_only(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("   ", "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result

    def test_integer_input(self):
        """Non-string inputs must return INVALID_INPUT."""
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer(123, "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result

    def test_float_input(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer(1.5, "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result

    def test_list_input(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer(["a", "b"], "test_token")
        assert result.get("error") == "INVALID_INPUT"
        assert "reason" in result


# ---------------------------------------------------------------------------
# Unicode minus normalization
# ---------------------------------------------------------------------------

class TestUnicodeMinus:
    """Unicode minus (\u2212) must be normalized to ASCII hyphen-minus."""

    def test_unicode_minus_plain_integer(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("\u2212507", "test_token")
        assert result == {"result": "-507"}

    def test_unicode_minus_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("\u2212156.11", "test_token")
        assert result == {"result": "-156.11"}

    def test_unicode_minus_decimal_3dp(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("\u22123.524", "test_token")
        assert result == {"result": "-3.524"}

    def test_ascii_minus_unchanged(self):
        """ASCII minus should not be modified."""
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("-1299", "test_token")
        assert result == {"result": "-1299"}


# ---------------------------------------------------------------------------
# Whitespace stripping
# ---------------------------------------------------------------------------

class TestWhitespaceStripping:
    """Leading and trailing whitespace must be stripped."""

    def test_leading_trailing_spaces_integer(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("  507  ", "test_token")
        assert result == {"result": "507"}

    def test_leading_trailing_spaces_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("  11.60  ", "test_token")
        assert result == {"result": "11.60"}

    def test_tabs_stripped(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("\t73\t", "test_token")
        assert result == {"result": "73"}


# ---------------------------------------------------------------------------
# Trailing zeros preserved (decimal categories C and D)
# ---------------------------------------------------------------------------

class TestTrailingZerosPreserved:
    """Trailing zeros in decimal values must be preserved."""

    def test_two_dp_trailing_zero(self):
        """11.60 must stay 11.60, not 11.6."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("11.60", "test_token") == {"result": "11.60"}

    def test_two_dp_double_trailing_zero(self):
        """678077.00 must stay 678077.00, not 678077."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("678077.00", "test_token") == {"result": "678077.00"}

    def test_three_dp_trailing_zero(self):
        """1.600 must stay 1.600."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("1.600", "test_token") == {"result": "1.600"}

    def test_four_dp_trailing_zeros(self):
        """3.9970 must stay 3.9970."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("3.9970", "test_token") == {"result": "3.9970"}

    def test_zero_with_dp(self):
        """0.0 must stay 0.0."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("0.0", "test_token") == {"result": "0.0"}

    def test_22_80(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("22.80", "test_token") == {"result": "22.80"}


# ---------------------------------------------------------------------------
# Plain integer (Category A) -- no comma, no decimal
# ---------------------------------------------------------------------------

class TestPlainInteger:
    """Plain integers must be returned as-is (no commas added or removed)."""

    def test_small_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("507", "test_token") == {"result": "507"}

    def test_two_digit_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("73", "test_token") == {"result": "73"}

    def test_negative_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("-1299", "test_token") == {"result": "-1299"}

    def test_large_integer_no_commas(self):
        """Large integers without commas must not have commas added."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("935851121560", "test_token") == {"result": "935851121560"}

    def test_large_integer_no_commas_2(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("254689000", "test_token") == {"result": "254689000"}


# ---------------------------------------------------------------------------
# Integer with comma (Category B)
# ---------------------------------------------------------------------------

class TestIntegerComma:
    """Integers with comma thousands separators must preserve commas."""

    def test_four_digit_comma(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("2,602", "test_token") == {"result": "2,602"}

    def test_five_digit_comma(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("44,463", "test_token") == {"result": "44,463"}

    def test_six_digit_comma(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("103,375", "test_token") == {"result": "103,375"}

    def test_six_digit_comma_2(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("907,654", "test_token") == {"result": "907,654"}


# ---------------------------------------------------------------------------
# Percentage (Categories E and F)
# ---------------------------------------------------------------------------

class TestPercentage:
    """Percentages must preserve exact decimal places and % suffix."""

    def test_pct_2dp(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("9.89%", "test_token") == {"result": "9.89%"}

    def test_pct_2dp_trailing_zero(self):
        """1608.80% must stay 1608.80%, not 1608.8%."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("1608.80%", "test_token") == {"result": "1608.80%"}

    def test_pct_3dp(self):
        """13.009% must stay 13.009%."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("13.009%", "test_token") == {"result": "13.009%"}

    def test_pct_987_3dp(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("9.987%", "test_token") == {"result": "9.987%"}

    def test_pct_negative(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("-18.51%", "test_token") == {"result": "-18.51%"}

    def test_pct_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("69%", "test_token") == {"result": "69%"}

    def test_pct_integer_single(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("3%", "test_token") == {"result": "3%"}


# ---------------------------------------------------------------------------
# Dollar pass-through (Category I)
# ---------------------------------------------------------------------------

class TestDollarPassThrough:
    """Dollar answers must be returned as-is (pass-through)."""

    def test_dollar_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("$37,921,314", "test_token") == {"result": "$37,921,314"}

    def test_dollar_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("$2,760.44", "test_token") == {"result": "$2,760.44"}

    def test_dollar_billion(self):
        """Dollar + unit word is still pass-through (starts with $)."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("$140.9 Billion", "test_token") == {"result": "$140.9 Billion"}

    def test_dollar_space_comma_decimal_unit(self):
        """Pro-only format: '$ 682,397.00 million' starts with '$'."""
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("$ 682,397.00 million", "test_token") == {"result": "$ 682,397.00 million"}


# ---------------------------------------------------------------------------
# List pass-through (Category G)
# ---------------------------------------------------------------------------

class TestListPassThrough:
    """List answers must be returned as-is (pass-through)."""

    def test_list_two_floats(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("[0.096, -184.143]", "test_token") == {"result": "[0.096, -184.143]"}

    def test_list_three_elements(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("[-0.153, 0.847, -1.162]", "test_token") == {"result": "[-0.153, 0.847, -1.162]"}

    def test_list_with_string_element(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("[0.012, surplus]", "test_token") == {"result": "[0.012, surplus]"}

    def test_list_with_pct_and_string(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("[2.59%, 2.34%, Decreased]", "test_token") == {"result": "[2.59%, 2.34%, Decreased]"}

    def test_list_integers(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("[1444, 3174]", "test_token") == {"result": "[1444, 3174]"}


# ---------------------------------------------------------------------------
# Unit word pass-through (Category H)
# ---------------------------------------------------------------------------

class TestUnitWordPassThrough:
    """Answers containing unit words must be returned as-is (pass-through)."""

    def test_million_integer(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("36080 million", "test_token") == {"result": "36080 million"}

    def test_billion_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("997.3 billion", "test_token") == {"result": "997.3 billion"}

    def test_millions_plural_negative_comma(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("-1,667.86 millions", "test_token") == {"result": "-1,667.86 millions"}

    def test_million_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("1169.41 million", "test_token") == {"result": "1169.41 million"}

    def test_million_with_trailing_zero(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("9732.50 million", "test_token") == {"result": "9732.50 million"}

    def test_million_comma(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("93,349 million", "test_token") == {"result": "93,349 million"}


# ---------------------------------------------------------------------------
# Date pass-through (Category K)
# ---------------------------------------------------------------------------

class TestDatePassThrough:
    """Date answers (starting with month name) must be returned as-is."""

    def test_date_with_day(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("March 3, 1977", "test_token") == {"result": "March 3, 1977"}

    def test_month_year(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("August 1986", "test_token") == {"result": "August 1986"}


# ---------------------------------------------------------------------------
# Comma+decimal (Category J)
# ---------------------------------------------------------------------------

class TestCommaDecimal:
    """Comma+decimal values must be preserved as-is."""

    def test_comma_decimal(self):
        from src.tools.normalize_answer import normalize_answer
        assert normalize_answer("57,615.04", "test_token") == {"result": "57,615.04"}


# ---------------------------------------------------------------------------
# Return structure guarantees
# ---------------------------------------------------------------------------

class TestReturnStructure:
    """normalize_answer always returns a dict with 'result' or 'error' key."""

    def test_success_returns_dict(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("507", "test_token")
        assert isinstance(result, dict)

    def test_success_result_is_string(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("507", "test_token")
        assert isinstance(result["result"], str)

    def test_error_returns_dict(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer(None, "test_token")
        assert isinstance(result, dict)

    def test_error_has_reason(self):
        from src.tools.normalize_answer import normalize_answer
        result = normalize_answer("", "test_token")
        assert "error" in result
        assert "reason" in result

    def test_never_raises(self):
        """normalize_answer must not raise for any input type."""
        from src.tools.normalize_answer import normalize_answer
        for bad_input in [None, "", 0, 1.5, [], {}, True, b"bytes"]:
            try:
                result = normalize_answer(bad_input, "test_token")
                assert isinstance(result, dict)
            except Exception as e:
                pytest.fail(f"normalize_answer raised {type(e).__name__} for input {bad_input!r}")
