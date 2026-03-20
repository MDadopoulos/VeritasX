# Phase 4: Verifier Subagent + Reliability - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Mandatory verification gate that every answer must pass before reaching `normalize_answer`. Four independent checks: evidence coverage, unit consistency, arithmetic re-execution, format match. Retry loop on FAIL/ERROR with targeted re-retrieval. Era-aware column header resolver for multi-decade series lookups. No new retrieval or calculation capabilities — reliability layer only.

</domain>

<decisions>
## Implementation Decisions

### Retry behavior
- 3 total attempts: 1 original + 2 retries before "cannot determine"
- On FAIL: targeted re-retrieval — agent uses the FAIL issues list to guide what to re-fetch (e.g., unit FAIL → re-retrieve the table with unit annotation)
- On ERROR (verifier crash/timeout): counts as a failed attempt, same retry logic as FAIL — no special-casing
- "Cannot determine" response includes the last verifier FAIL issues list so callers can see why

### Verification strictness
- Arithmetic re-execution: exact Decimal match required — no tolerance
- Evidence coverage: Claude's discretion on the coverage heuristic
- Missing/unparseable calc.txt: Claude decides whether to FAIL or skip the arithmetic check based on whether the answer type requires arithmetic
- Check tiering: Claude assigns which checks are hard vetoes (definitively wrong answers) vs. soft warnings (cosmetic issues) — arithmetic and units are likely hard vetoes, but Claude decides the final tiers

### Era-aware series mapping
- Fuzzy match at runtime — no hard-coded variant table
- Multiple candidates in same bulletin: Claude decides the selection strategy to minimize false positives
- When no confident match found: resolver returns null, main agent decides how to handle the gap
- Activation: multi-era questions only (date range crosses era boundary) — single-year lookups use exact column name matching

### Verifier result transparency
- FAIL issues: written to verification.txt AND returned in VerifierResult so main agent can act on them for targeted retry
- PASS result in verification.txt: verification token + summary of which checks passed (e.g., "evidence: PASS, arithmetic: PASS, units: PASS, format: PASS")
- Each retry attempt is appended to verification.txt (full history preserved, not overwritten)
- "Cannot determine" final response: includes last FAIL issues list in the HTTP response body (for Phase 5 A2A schema)

### Claude's Discretion
- Evidence coverage heuristic (what counts as "covered")
- Whether missing calc.txt is a hard FAIL or skipped check
- Which verification dimensions are hard vetoes vs. soft warnings
- Fuzzy match candidate selection strategy (minimize false positives)

</decisions>

<specifics>
## Specific Ideas

- Verification attempts appended to a single verification.txt — audit trail of all attempts per question UID in scratch
- The "cannot determine" answer should carry the issues forward all the way to the HTTP response so benchmark callers understand why (not just internal logging)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-verifier-subagent-reliability*
*Context gathered: 2026-03-20*
