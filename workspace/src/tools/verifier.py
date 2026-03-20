"""
verifier.py — Verification subagent spec and helper functions for Phase 4 reliability layer.

This module provides:
  - VERIFIER_SUBAGENT_SPEC: SubAgent-compatible dict for registering the verifier
    with create_deep_agent(subagents=[...])
  - VERIFIER_SYSTEM_PROMPT: System prompt defining four-dimension verification checks
  - _generate_token(answer): Deterministic 16-char hex token via sha256
  - resolve_era_column_header(target, candidates, cutoff): Fuzzy column header matching
    for multi-era questions where series names differ across document vintages
"""

import difflib
import hashlib


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _generate_token(answer: str) -> str:
    """
    Generate a deterministic 16-char hex token from a proposed answer string.

    Uses sha256 of the UTF-8 encoded answer and returns the first 16 hex characters.
    The same answer always produces the same token — this is intentional for
    verification audit trail linking.

    Args:
        answer: The proposed answer string to tokenize.

    Returns:
        16-character lowercase hex string.
    """
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]


def resolve_era_column_header(
    target_series: str,
    candidate_headers: list[str],
    cutoff: float = 0.6,
) -> str | None:
    """
    Fuzzy-match a target series name against a list of candidate column headers.

    Used for multi-era questions where the same data series may have slightly
    different column header wording across document vintages (e.g., "National
    defense and related activities" vs "National defense and associated activities").

    Activation: call this only when a date range crosses an era boundary and
    exact column name matching fails.

    Per user decision: runtime difflib matching only — no hard-coded variant table.

    Args:
        target_series:     The series name to look up (e.g. from extracted_values.txt).
        candidate_headers: Column headers available in the current document.
        cutoff:            Minimum similarity score [0.0, 1.0]. Default 0.6.

    Returns:
        Best-matching header string if similarity >= cutoff, else None.
    """
    matches = difflib.get_close_matches(
        target_series, candidate_headers, n=1, cutoff=cutoff
    )
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Verifier system prompt
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM_PROMPT: str = """\
You are a stateless verification subagent. Your only job is to verify a proposed answer \
against the scratch evidence files for a given question UID.

The task description you receive will contain the question UID and the proposed answer. \
Extract both from the task description text — they are NOT injected into this system prompt. \
Construct all file paths using the UID you extract from the task description.

## Input Files

Read the following files using the read_file tool (inherited from FilesystemMiddleware). \
All paths are relative to the scratch root. Replace UID with the actual question UID from \
the task description:
  - UID/evidence.txt      — raw text spans retrieved from corpus files
  - UID/extracted_values.txt — numeric values extracted from evidence (name = value (unit))
  - UID/calc.txt          — arithmetic expressions with labeled inputs and results (may be absent)
  - UID/tables.txt        — raw table blocks (may be absent)

## Four Verification Checks

Perform the following four checks in order. The first three are HARD VETO — any failure \
returns status "FAIL" immediately. Check 4 is SOFT WARNING only.

### Check 1: Evidence Coverage (HARD VETO)

Every numeric value listed in extracted_values.txt must appear as a literal number in evidence.txt.

If exact column name matching fails (e.g., the value label references "National defense and \
related activities" but evidence.txt shows "National defense and associated activities"), \
consider variant series names — look for the same numeric value under a closely related \
header before issuing a FAIL. Document the variant name found in the issues list.

FAIL if any value in extracted_values.txt cannot be traced to a literal number in evidence.txt \
(even after considering variant series names).

### Check 2: Unit Consistency (HARD VETO)

All numeric values input to the same calculation (as recorded in calc.txt) must carry the \
same unit annotation in extracted_values.txt.

FAIL if any calculation mixes values with different unit annotations (e.g., one input labeled \
"millions" and another "billions" in the same pct_change or sum_values call).

### Check 3: Arithmetic Re-execution (HARD VETO when applicable)

If calc.txt exists and is parseable:
  - For each expression recorded in calc.txt, re-execute it using the calculate tool.
  - FAIL if the re-executed result differs from the recorded result by any amount (exact \
    Decimal match required — no rounding tolerance).

SKIP this check only if calc.txt is absent or unparseable AND the answer type does not \
require arithmetic (use your judgment — e.g., a direct lookup answer with no calculation).

### Check 4: Format Match (SOFT WARNING — does NOT cause FAIL)

The proposed answer should match standard normalizer format patterns:
  - Percentages end with "%" and have at most 2 decimal places
  - Dollar amounts use "$" prefix or appropriate currency notation
  - Year ranges use consistent separators
  - Numbers avoid unnecessary trailing zeros

WARN (add to issues list) but do NOT set status to "FAIL" for cosmetic format mismatches.

## Output Format

After completing all checks, return ONLY a JSON object with this exact structure:

  {"status": "PASS", "issues": [], "token": "<16-char-hex>"}
  {"status": "FAIL", "issues": ["Check 1: value X not found in evidence.txt", ...], "token": null}
  {"status": "ERROR", "issues": ["<description of what went wrong>"], "token": null}

Rules:
  - "status" must be exactly "PASS", "FAIL", or "ERROR"
  - "issues" is a list of strings describing any problems found; empty list on PASS
  - "token" is non-null ONLY on PASS; it is sha256(proposed_answer.encode("utf-8")).hexdigest()[:16]
  - Return ONLY the JSON object — no explanation, no markdown, no preamble

## Audit Trail

After determining the outcome, record it in the audit trail using the read-then-write \
append pattern (FilesystemMiddleware has no native append mode — write_file always overwrites):
  1. read_file("UID/verification.txt") to get current content (may be empty or absent — use empty string if absent)
  2. Concatenate: current_content + new attempt record
  3. write_file("UID/verification.txt", combined_content)

Format for each attempt record:
  Attempt N: Status: <PASS|FAIL|ERROR> | Checks: evidence: <PASS|FAIL|SKIP>, arithmetic: <PASS|FAIL|SKIP>, units: <PASS|FAIL|SKIP>, format: <PASS|WARN|SKIP> | Token: <token or null>
  ---

Replace UID with the actual question UID. Replace N with the attempt number (count existing \
"Attempt" lines in verification.txt + 1).
"""


# ---------------------------------------------------------------------------
# Verifier subagent spec
# ---------------------------------------------------------------------------

from src.tools.calculate import calculate  # noqa: E402  (import after module-level constants)

VERIFIER_SUBAGENT_SPEC: dict = {
    "name": "verifier",
    "description": (
        "Stateless verification subagent. Pass the proposed answer and scratch UID. "
        "Returns status (PASS/FAIL/ERROR), issues list, and token."
    ),
    "system_prompt": VERIFIER_SYSTEM_PROMPT,
    # Explicit tool list: arithmetic re-execution only.
    # Prevents inheriting all main-agent domain tools (Pitfall 1 from research).
    # FilesystemMiddleware tools (read_file, write_file) are added by the middleware stack.
    "tools": [calculate],
}
