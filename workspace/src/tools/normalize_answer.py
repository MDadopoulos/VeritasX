"""
normalize_answer.py — Rule-based answer normalizer.

Requires a verification_token from the verifier subagent — raises ValueError if absent.

Formats raw calculator output to match benchmark answer format exactly.
The normalizer is fundamentally a pass-through for format: its job is to
clean whitespace and unicode, not to reformat numbers. The benchmark
answers ARE the expected format.

Decision tree (derived from format survey categories A-K):
  1. Strip whitespace, normalize unicode minus (\u2212) to ASCII '-'.
  2. If starts with '[' -> pass-through (list answer).
  3. If contains unit word (million/billion/thousand, case-insensitive) -> pass-through.
  4. If starts with '$' -> pass-through (dollar answer).
  5. If matches date pattern (month name + digits/year) -> pass-through.
  6. If ends with '%' -> percentage: preserve number exactly as-is (including decimal places).
  7. If contains '.' -> decimal: preserve exact decimal places from raw string.
  8. Else -> integer: preserve commas from original if present, do not add them if absent.

Returns:
  {"result": str} on success
  {"error": str, "reason": str} on invalid input
"""

import re

# Regex for unit words (million/billion/thousand, with or without 's', case-insensitive)
_UNIT_WORD_RE = re.compile(r'\b(millions?|billions?|thousands?)\b', re.IGNORECASE)

# Regex for month names (full or abbreviated) to detect date answers
_MONTH_NAMES = (
    r'January|February|March|April|May|June|July|August|'
    r'September|October|November|December|'
    r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec'
)
_DATE_RE = re.compile(
    rf'^\s*(?:{_MONTH_NAMES})\b',
    re.IGNORECASE
)

# Unicode minus character
_UNICODE_MINUS = '\u2212'


def normalize_answer(raw: str, verification_token: str = None) -> dict:
    """
    Normalize a raw answer string to match benchmark format exactly.

    Parameters
    ----------
    raw : str
        The raw answer string from the calculator or extracted from the corpus.
        Must be a non-empty string.
    verification_token : str
        Token from the verifier subagent (16-char hex from PASS response). Required.

    Returns
    -------
    dict
        {"result": str} on success.
        {"error": "INVALID_INPUT", "reason": str} on invalid input.
    """
    # --- Verification gate — requires token from verifier subagent ---
    if not verification_token:
        return {
            "error": "VERIFICATION_REQUIRED",
            "reason": (
                "normalize_answer requires a non-null verification_token from the verifier. "
                "Call task(subagent_type='verifier') first and pass its token."
            ),
        }

    # --- Input validation ---
    if raw is None or not isinstance(raw, str):
        return {"error": "INVALID_INPUT", "reason": "raw must be a non-empty string"}
    if not raw.strip():
        return {"error": "INVALID_INPUT", "reason": "raw must be a non-empty string"}

    # --- Step 1: Strip whitespace and normalize unicode minus ---
    cleaned = raw.strip().replace(_UNICODE_MINUS, '-')

    # --- Step 2: List answer pass-through ---
    # Starts with '[' -> list answer (may contain strings, numbers, percentages)
    if cleaned.startswith('['):
        return {"result": cleaned}

    # --- Step 3: Unit word pass-through ---
    # Contains "million", "billion", "thousand" (with or without 's') -> pass-through
    if _UNIT_WORD_RE.search(cleaned):
        return {"result": cleaned}

    # --- Step 4: Dollar answer pass-through ---
    # Starts with '$' -> pass-through (dollar sign is part of the answer format)
    if cleaned.startswith('$'):
        return {"result": cleaned}

    # --- Step 5: Date answer pass-through ---
    # Starts with a month name -> pass-through (non-numeric date answer)
    if _DATE_RE.match(cleaned):
        return {"result": cleaned}

    # --- Step 6: Percentage ---
    # Ends with '%' -> preserve the numeric part exactly as-is (decimal places, commas, etc.)
    # The benchmark preserves the original decimal precision (13.009%, 9.987%, 1608.80%)
    if cleaned.endswith('%'):
        return {"result": cleaned}

    # --- Step 7: Decimal ---
    # Contains '.' -> preserve the exact number of decimal places from the raw string.
    # Never strip trailing zeros (11.60 stays 11.60, not 11.6).
    # Never add trailing zeros (0.88525 stays 0.88525).
    # Commas are also preserved if present (57,615.04 stays 57,615.04).
    if '.' in cleaned:
        return {"result": cleaned}

    # --- Step 8: Integer ---
    # No decimal point, no percent, no special prefix/suffix.
    # Preserve commas from original (2,602 stays 2,602).
    # Do not add commas if absent (935851121560 stays 935851121560).
    return {"result": cleaned}
