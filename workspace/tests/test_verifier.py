"""
test_verifier.py — Unit tests for verifier helper functions and normalize_answer token gate.

Covers (all pure Python, no LLM calls):
  - VER-03: _generate_token() deterministic 16-char hex token
  - VER-04: normalize_answer() verification_token gate (ValueError on absent/empty token)
  - VER-06: resolve_era_column_header() fuzzy matching with configurable cutoff
  - Spec structure: VERIFIER_SUBAGENT_SPEC required keys, name, tools, no {uid} placeholder
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Token generation tests (VER-03)
# ---------------------------------------------------------------------------


class TestGenerateToken:
    """_generate_token returns a deterministic 16-char lowercase hex string."""

    def test_generate_token_returns_16_char_hex(self):
        """sha256 hex prefix of '19.14%' is exactly 16 characters, all hex digits."""
        import re
        from src.tools.verifier import _generate_token

        token = _generate_token("19.14%")
        assert len(token) == 16, f"Expected 16 chars, got {len(token)}: {token!r}"
        assert re.fullmatch(r"[0-9a-f]{16}", token), (
            f"Token must match [0-9a-f]{{16}}, got: {token!r}"
        )

    def test_generate_token_deterministic(self):
        """Same input always produces the same token."""
        from src.tools.verifier import _generate_token

        assert _generate_token("test") == _generate_token("test"), (
            "_generate_token must be deterministic for the same input"
        )

    def test_generate_token_different_inputs(self):
        """Different inputs produce different tokens (collision-free for typical inputs)."""
        from src.tools.verifier import _generate_token

        assert _generate_token("a") != _generate_token("b"), (
            "Different inputs must produce different tokens"
        )


# ---------------------------------------------------------------------------
# Era-aware resolver tests (VER-06)
# ---------------------------------------------------------------------------


class TestResolveEraColumnHeader:
    """resolve_era_column_header fuzzy-matches series names against candidate headers."""

    def test_resolve_era_header_exact_match(self):
        """Exact string match returns the matched header."""
        from src.tools.verifier import resolve_era_column_header

        result = resolve_era_column_header(
            "National defense",
            ["National defense", "Veterans"],
        )
        assert result == "National defense", f"Expected 'National defense', got: {result!r}"

    def test_resolve_era_header_fuzzy_match(self):
        """Similar strings above default cutoff (0.6) are matched."""
        from src.tools.verifier import resolve_era_column_header

        result = resolve_era_column_header(
            "National defense and associated activities",
            [
                "National defense and related activities",
                "Veterans Administration",
            ],
        )
        assert result == "National defense and related activities", (
            f"Expected fuzzy match, got: {result!r}"
        )

    def test_resolve_era_header_no_match(self):
        """A completely unrelated target returns None."""
        from src.tools.verifier import resolve_era_column_header

        result = resolve_era_column_header(
            "Completely unrelated",
            ["National defense", "Veterans"],
        )
        assert result is None, f"Expected None for no match, got: {result!r}"

    def test_resolve_era_header_custom_cutoff(self):
        """With cutoff=0.9, a string similar at ~0.6 does not match."""
        from src.tools.verifier import resolve_era_column_header

        # "National defense spending" vs "National defense" — similar but not 90%+ identical
        result = resolve_era_column_header(
            "National defense spending",
            ["National defense"],
            cutoff=0.9,
        )
        assert result is None, (
            f"With cutoff=0.9, partial match should return None, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# normalize_answer token gate tests (VER-04)
# ---------------------------------------------------------------------------


class TestNormalizeAnswerTokenGate:
    """normalize_answer raises ValueError when verification_token is absent or empty."""

    def test_normalize_answer_raises_on_empty_token(self):
        """Empty string token raises ValueError with 'verification_token' in message."""
        import pytest
        from src.tools.normalize_answer import normalize_answer

        with pytest.raises(ValueError, match="verification_token"):
            normalize_answer("test", "")

    def test_normalize_answer_raises_on_none_token(self):
        """None token raises ValueError or TypeError (both prevent bypass)."""
        from src.tools.normalize_answer import normalize_answer

        try:
            normalize_answer("test", None)
            assert False, "Expected ValueError or TypeError for None token"
        except (ValueError, TypeError):
            pass  # Either is acceptable — None must not be allowed through

    def test_normalize_answer_works_with_valid_token(self):
        """Valid non-empty token allows normalization to proceed."""
        from src.tools.normalize_answer import normalize_answer

        result = normalize_answer("19.14%", "abc123")
        assert result == {"result": "19.14%"}, f"Expected {{'result': '19.14%'}}, got: {result!r}"

    def test_normalize_answer_integer_with_token(self):
        """Integer comma value normalizes correctly when token is provided."""
        from src.tools.normalize_answer import normalize_answer

        result = normalize_answer("2,602", "validtoken")
        assert result == {"result": "2,602"}, f"Expected {{'result': '2,602'}}, got: {result!r}"

    def test_normalize_answer_invalid_input_still_returns_error(self):
        """Existing input validation still runs when token is valid (empty raw string)."""
        from src.tools.normalize_answer import normalize_answer

        result = normalize_answer("", "validtoken")
        assert result.get("error") == "INVALID_INPUT", (
            f"Expected INVALID_INPUT error for empty raw, got: {result!r}"
        )


# ---------------------------------------------------------------------------
# Verifier spec structure tests
# ---------------------------------------------------------------------------


class TestVerifierSpec:
    """VERIFIER_SUBAGENT_SPEC has correct structure and content."""

    def test_verifier_spec_has_required_keys(self):
        """Spec dict must contain name, description, system_prompt, tools."""
        from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

        for key in ("name", "description", "system_prompt", "tools"):
            assert key in VERIFIER_SUBAGENT_SPEC, (
                f"VERIFIER_SUBAGENT_SPEC missing required key: {key!r}"
            )

    def test_verifier_spec_name_is_verifier(self):
        """Spec name must be exactly 'verifier'."""
        from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

        assert VERIFIER_SUBAGENT_SPEC["name"] == "verifier", (
            f"Expected name='verifier', got: {VERIFIER_SUBAGENT_SPEC['name']!r}"
        )

    def test_verifier_spec_tools_contains_calculate(self):
        """tools list must contain the calculate function (by identity)."""
        from src.tools.calculate import calculate
        from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

        tools = VERIFIER_SUBAGENT_SPEC["tools"]
        assert isinstance(tools, list), f"tools must be a list, got: {type(tools)}"
        assert calculate in tools, (
            "VERIFIER_SUBAGENT_SPEC['tools'] must contain the calculate function"
        )

    def test_verifier_system_prompt_no_uid_placeholder(self):
        """system_prompt must NOT contain '{uid}' format placeholder (Pitfall 3)."""
        from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

        prompt = VERIFIER_SUBAGENT_SPEC["system_prompt"]
        assert "{uid}" not in prompt, (
            "system_prompt must not contain '{uid}' placeholder — UID is extracted by the LLM "
            "from the task description, not injected at format time"
        )
