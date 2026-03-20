# Phase 4: Verifier Subagent + Reliability - Research

**Researched:** 2026-03-20
**Domain:** deepagents SubAgentMiddleware, verification gate pattern, Python Decimal re-execution, fuzzy column header matching
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Retry behavior
- 3 total attempts: 1 original + 2 retries before "cannot determine"
- On FAIL: targeted re-retrieval — agent uses the FAIL issues list to guide what to re-fetch (e.g., unit FAIL → re-retrieve the table with unit annotation)
- On ERROR (verifier crash/timeout): counts as a failed attempt, same retry logic as FAIL — no special-casing
- "Cannot determine" response includes the last verifier FAIL issues list so callers can see why

#### Verification strictness
- Arithmetic re-execution: exact Decimal match required — no tolerance
- Evidence coverage: Claude's discretion on the coverage heuristic
- Missing/unparseable calc.txt: Claude decides whether to FAIL or skip the arithmetic check based on whether the answer type requires arithmetic
- Check tiering: Claude assigns which checks are hard vetoes (definitively wrong answers) vs. soft warnings (cosmetic issues) — arithmetic and units are likely hard vetoes, but Claude decides the final tiers

#### Era-aware series mapping
- Fuzzy match at runtime — no hard-coded variant table
- Multiple candidates in same bulletin: Claude decides the selection strategy to minimize false positives
- When no confident match found: resolver returns null, main agent decides how to handle the gap
- Activation: multi-era questions only (date range crosses era boundary) — single-year lookups use exact column name matching

#### Verifier result transparency
- FAIL issues: written to verification.txt AND returned in VerifierResult so main agent can act on them for targeted retry
- PASS result in verification.txt: verification token + summary of which checks passed (e.g., "evidence: PASS, arithmetic: PASS, units: PASS, format: PASS")
- Each retry attempt is appended to verification.txt (full history preserved, not overwritten)
- "Cannot determine" final response: includes last FAIL issues list in the HTTP response body (for Phase 5 A2A schema)

### Claude's Discretion
- Evidence coverage heuristic (what counts as "covered")
- Whether missing calc.txt is a hard FAIL or skipped check
- Which verification dimensions are hard vetoes vs. soft warnings
- Fuzzy match candidate selection strategy (minimize false positives)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

Phase 4 adds a mandatory reliability layer on top of the working Phase 3 agent. Nothing in this phase changes retrieval or calculation logic. The work is: (1) a verifier subagent registered via `create_deep_agent(subagents=[...])`, (2) a `verification_token` gate on `normalize_answer`, (3) a retry loop in the main agent's system prompt plus a "cannot determine" fallback after 2 failed attempts, and (4) an era-aware column header resolver as a plain Python helper that the verifier invokes when checking evidence coverage.

The critical architectural discovery is that `create_deep_agent` already has a native `subagents` parameter (not a separate `SubAgentMiddleware` in the `middleware` list). Passing `subagents=[{...}]` to `create_deep_agent` builds the verifier as a real LangChain `create_agent` runnable, registers it under the `task` tool with the name `"verifier"`, and automatically injects the correct subagent prompt. The main agent calls the verifier via `task(subagent_type="verifier", description="...")`. There is no separate `SubAgentMiddleware(...)` to construct — `create_deep_agent` builds and inserts it internally from the `subagents` list.

The four verification checks are pure Python logic that lives inside the verifier subagent's system prompt and toolset. The verifier reads `evidence.txt`, `extracted_values.txt`, and `calc.txt` from scratch via the `read_file` filesystem tool it inherits, then returns a structured JSON result. The `verification_token` is generated only on PASS (a short deterministic hash of the answer string suffices). The `normalize_answer` function is modified to require the token argument and raise on absent/null token.

**Primary recommendation:** Use `create_deep_agent(subagents=[{"name": "verifier", ...}])` — not `SubAgentMiddleware` in the `middleware` list. The verifier subagent receives no custom tools (it reads scratch files via the inherited filesystem tools). Token generation uses `hashlib.sha256` over the answer string. Evidence coverage heuristic: every numeric value in `extracted_values.txt` must appear as a literal in `evidence.txt` (allowing minor formatting variation). Arithmetic and units are hard vetoes; format is a soft warning.

---

## Standard Stack

### Core (verified from installed library source at `.venv/Lib/site-packages/deepagents/`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| deepagents | 0.4.11 | `create_deep_agent(subagents=[...])` — builds verifier runnable and task tool | Project requirement; already pinned |
| langchain (core) | transitive | `create_agent` inside SubAgentMiddleware — the underlying verifier graph | deepagents dependency |
| langgraph | transitive | `MemorySaver`, graph state | deepagents dependency |
| Python stdlib `decimal` | stdlib | Exact Decimal re-execution of calc expressions | No float contamination; already used in `calculate.py` |
| Python stdlib `hashlib` | stdlib | `sha256` for verification token generation | Deterministic, no new dependency |
| Python stdlib `difflib` | stdlib | `get_close_matches` for era-aware fuzzy header matching | Verified working in repo Python; no new dependency |

### No New Dependencies Required
All libraries needed for Phase 4 are either already in `requirements.txt` or Python stdlib. This phase installs no new packages.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `difflib.get_close_matches` | `rapidfuzz`, `fuzzywuzzy` | stdlib is sufficient; no dependency; tested and returns correct matches at cutoff=0.6 |
| `hashlib.sha256` for token | UUID, timestamp | sha256 is deterministic (same answer → same token), which is testable |
| Verifier as subagent (task tool) | Verifier as a plain Python function called before normalize | Subagent approach matches VER-01 requirement exactly; plain function approach would not satisfy "registered via SubAgentMiddleware" requirement |

---

## Architecture Patterns

### Recommended File Layout After Phase 4

```
workspace/src/
├── agent.py                  # MODIFIED: add subagents=[verifier_spec], retry logic in SYSTEM_PROMPT
├── tools/
│   ├── normalize_answer.py   # MODIFIED: add verification_token argument, raise on absent/null
│   └── verifier.py           # NEW: verifier_spec dict + era_resolver helper function
├── scratch.py                # UNCHANGED
├── model_adapter.py          # UNCHANGED
└── [all other files]         # UNCHANGED
tests/
├── test_verifier.py          # NEW: unit tests for verifier logic (pure Python, no LLM)
└── test_agent.py             # MODIFIED: update verification.txt assertion, add retry/cannot-determine tests
```

### Pattern 1: Registering the Verifier Subagent

**What:** Pass a `SubAgent` dict to `create_deep_agent(subagents=[...])`. The library builds the `create_agent(...)` runnable, wraps it in `SubAgentMiddleware`, and exposes it via the `task` tool under the `name` key.

**Critical finding from `graph.py` lines 209-238:** When a `SubAgent` dict is in the `subagents` list, `create_deep_agent` automatically prepends a default middleware stack (TodoListMiddleware, FilesystemMiddleware, SummarizationMiddleware, etc.) to the subagent. This means the verifier subagent inherits filesystem tools (`read_file`, `write_file`, etc.) without any explicit `tools` key in the spec.

**When to use:** Exactly once, in `create_agent()` in `agent.py`.

**Example:**
```python
# Source: workspace/.venv/Lib/site-packages/deepagents/graph.py lines 81-99, 209-238
from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

def create_agent():
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langgraph.checkpoint.memory import MemorySaver
    from src.model_adapter import get_model
    from src.tools.route_files import route_files
    from src.tools.search_in_file import search_in_file
    from src.tools.extract_table_block import extract_table_block
    from src.tools.calculate import calculate, pct_change, sum_values
    from src.tools.normalize_answer import normalize_answer

    model = get_model()

    return create_deep_agent(
        model=model,
        tools=[
            route_files,
            search_in_file,
            extract_table_block,
            calculate,
            pct_change,
            sum_values,
            normalize_answer,
        ],
        subagents=[VERIFIER_SUBAGENT_SPEC],   # ← verifier registered here
        system_prompt=SYSTEM_PROMPT,
        backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
        checkpointer=MemorySaver(),
    )
```

**SubAgent spec structure (from `subagents.py` SubAgent TypedDict):**
```python
# Source: workspace/.venv/Lib/site-packages/deepagents/middleware/subagents.py lines 22-78
VERIFIER_SUBAGENT_SPEC: SubAgent = {
    "name": "verifier",
    "description": (
        "Stateless verification subagent. Checks four dimensions: "
        "evidence coverage, unit consistency, arithmetic correctness, and answer format. "
        "Call this with all scratch file paths and the proposed answer before normalize_answer."
    ),
    "system_prompt": VERIFIER_SYSTEM_PROMPT,   # see Pattern 2
    # No 'tools' key → inherits filesystem tools from default middleware stack
    # No 'model' key → inherits main agent's model
}
```

**Key insight from source:** `SubAgent.tools` is `NotRequired`. When absent, the `subagent` inherits `tools or []` from the main agent spec (graph.py line 235: `spec.get("tools", tools or [])`). Since the main agent's tools list contains our domain tools (route_files, normalize_answer, etc.), the verifier will also inherit them. To prevent the verifier from calling domain tools directly, give it an explicit empty tools list or a restricted set. The verifier should only read scratch files (filesystem tools) — not call route_files or normalize_answer. Recommendation: pass `"tools": []` explicitly so the verifier only has the filesystem tools from the default middleware stack.

### Pattern 2: Verifier System Prompt

**What:** The system prompt passed to the verifier subagent spec must be precise about the four checks, the output format (a JSON-like structured message), and the token generation rule.

**Example:**
```python
VERIFIER_SYSTEM_PROMPT = """\
You are a stateless verifier. You receive a task description containing:
- The proposed answer
- The UID of the scratch directory to read

Read {uid}/evidence.txt, {uid}/extracted_values.txt, {uid}/calc.txt, and {uid}/answer.txt
using read_file.

Perform four checks and return a structured result as your final message:

## Check 1: Evidence Coverage (HARD VETO)
Every numeric value in extracted_values.txt must appear (as a literal) in evidence.txt.
FAIL if any extracted value has no matching span in evidence.txt.

## Check 2: Unit Consistency (HARD VETO)
All values in extracted_values.txt that are inputs to the same calculation must carry the same unit.
FAIL if heterogeneous units are mixed without normalization.

## Check 3: Arithmetic Re-execution (HARD VETO — only when calc.txt exists and is parseable)
Re-execute each expression in calc.txt using exact Decimal arithmetic.
FAIL if re-executed result differs from the recorded result by any amount.
SKIP this check if calc.txt is absent or unparseable AND the answer type does not require arithmetic.

## Check 4: Format Match (SOFT WARNING)
Proposed answer must match one of the normalizer format patterns (%, $, list, integer, decimal, unit-word).
WARN (do not FAIL) if format seems cosmetically off but the numeric value is correct.

## Output Format
Return ONLY this structure as your final message:
{
  "status": "PASS" or "FAIL" or "ERROR",
  "issues": ["issue description 1", ...],  // empty list on PASS
  "token": "<sha256-of-answer>" or null    // non-null ONLY on PASS
}
"""
```

### Pattern 3: Verification Token Generation

**What:** A `sha256` digest of the answer string. Deterministic: same answer always produces the same token. The token is generated inside the verifier's reasoning (it constructs the JSON output with the hash). Alternatively, generate it in Python after parsing the verifier's JSON response.

**Recommended approach:** Generate token in `normalize_answer` after verifying the token is structurally valid (non-null, correct format). The verifier returns a token string; `normalize_answer` checks it is non-null and non-empty. This keeps token generation out of the LLM's reasoning.

```python
# Source: Python stdlib hashlib — no installation needed
import hashlib

def _generate_token(answer: str) -> str:
    """Generate a deterministic verification token for an answer string."""
    return hashlib.sha256(answer.encode()).hexdigest()[:16]
```

The token need not be cryptographically secure — it is a bypass-prevention gate, not an authentication secret. A 16-char hex prefix is sufficient.

### Pattern 4: normalize_answer Verification Gate

**What:** Add `verification_token` parameter to `normalize_answer`. Raise `ValueError` if token is absent or null. This is the code-level bypass prevention from VER-04.

**Example:**
```python
def normalize_answer(raw: str, verification_token: str) -> dict:
    """
    Normalize a raw answer string to match benchmark format exactly.

    Parameters
    ----------
    raw : str
        The raw answer string.
    verification_token : str
        Non-null token from the verifier subagent. Raises ValueError if absent or null.
    """
    if not verification_token:
        raise ValueError(
            "normalize_answer requires a non-null verification_token. "
            "Call the verifier subagent first and pass its token."
        )
    # ... existing normalization logic unchanged ...
```

**Important:** This is a plain Python `raise` (not a `return {"error": ...}` dict). The design rationale is that absent token is a programming error (bypass attempt), not a runtime data problem. A `ValueError` surfaces clearly in tests and logs.

**Pydantic schema impact:** Adding `verification_token: str` to the function signature makes it a required field in the tool's JSON schema. The LLM must always include it when calling `normalize_answer`. This is the desired behavior — it cannot be accidentally omitted.

### Pattern 5: Retry Loop via System Prompt Instructions

**What:** The retry logic lives in the main agent's `SYSTEM_PROMPT` as instructions, not as Python code in `run_question`. The agent's LLM reads the verifier result and decides to retry or give up.

**Rationale:** The main agent is an LLM agent running in a graph. There is no imperative retry loop in `run_question` — the loop is the agent's natural tool-call cycle. The system prompt instructs the agent what to do when `task(subagent_type="verifier")` returns FAIL.

**System prompt addition:**
```
## Verification and Retry Protocol

Before calling normalize_answer, you MUST call:
  task(subagent_type="verifier", description="Verify answer for UID {uid}: <proposed_answer>. Scratch path: {uid}/")

The verifier returns a JSON object with status, issues, and token.

On FAIL:
  - Read the issues list to understand what failed.
  - Perform targeted re-retrieval: if unit FAIL, re-fetch the table that showed units.
    If arithmetic FAIL, re-check your calc.txt expression.
  - Retry the full answer derivation and call the verifier again.
  - You have 3 total attempts (1 original + 2 retries).

On ERROR (verifier crashed):
  - Count this as a failed attempt. Same retry logic as FAIL.

After 3 failed attempts:
  - Respond with EXACTLY: "cannot determine: <last_verifier_issues_list>"
  - Do NOT call normalize_answer with an unverified answer.

On PASS:
  - Use the returned token as the verification_token argument to normalize_answer.
```

### Pattern 6: Era-Aware Column Header Resolver

**What:** A plain Python function (not a tool) in `src/tools/verifier.py` that the verifier subagent invokes internally via its reasoning. Since the verifier runs as an LLM agent with filesystem tools, the resolver must be exposed as a tool the verifier subagent can call.

**Key constraint from CONTEXT.md:** Fuzzy match at runtime — no hard-coded variant table. Use `difflib.get_close_matches` with a sensible cutoff.

**Verified behavior of `difflib.get_close_matches`:**
```python
# Source: Python stdlib difflib — tested in repo environment
import difflib

difflib.get_close_matches(
    "National defense and associated activities",
    ["National defense", "National defense and related activities",
     "Expenditures for national defense", "National defense and Veterans Administration"],
    n=3, cutoff=0.6
)
# Returns: ['National defense and related activities', 'National defense and Veterans Administration']
```

**Recommended design:**
```python
import difflib

def resolve_era_column_header(
    target_series: str,
    candidate_headers: list[str],
    cutoff: float = 0.6,
) -> str | None:
    """
    Find the closest matching column header for a series name across era variants.

    Returns the best match string, or None if no candidate exceeds the cutoff.
    Used only for multi-era questions (date range crosses era boundary).

    Args:
        target_series: Series name to match (e.g. "National defense and associated activities")
        candidate_headers: All column headers found in the bulletin table
        cutoff: Minimum similarity ratio (0.0-1.0). Default 0.6.

    Returns:
        Best matching header string, or None if no match found.
    """
    matches = difflib.get_close_matches(target_series, candidate_headers, n=1, cutoff=cutoff)
    return matches[0] if matches else None
```

**Activation logic:** The verifier applies era-aware matching only when checking evidence coverage for a question that spans multiple eras (i.e., the task description from the main agent includes year ranges crossing a known era boundary). The verifier's system prompt instructs it to apply fuzzy matching when exact column name matching fails during evidence coverage check.

**Multiple candidates problem:** When multiple headers match above the cutoff, take the one with the highest similarity ratio. `difflib.SequenceMatcher(None, a, b).ratio()` gives the numeric score for ranking. Return only the highest-scoring match (n=1 in `get_close_matches`).

### Anti-Patterns to Avoid

- **Implementing SubAgentMiddleware directly:** Do NOT construct `SubAgentMiddleware(backend=..., subagents=[...])` and add it to the `middleware` list manually. Use `create_deep_agent(subagents=[...])` instead — the library constructs SubAgentMiddleware internally from the `subagents` parameter. Manual construction at the middleware level duplicates what the library already does.

- **Giving the verifier domain tools (route_files, normalize_answer):** Pass `"tools": []` explicitly in the verifier spec. The verifier should only read scratch files via filesystem tools, not call retrieval or normalization tools directly. If it inherits the full tool set, it could call `normalize_answer` bypassing its own gate.

- **Token as LLM-generated string:** If the LLM generates the token string itself, it could hallucinate a token. Generate the token deterministically in Python from the answer string. The verifier's job is to decide PASS/FAIL; token generation is a mechanical step.

- **Using `str` not `Optional[str]` for verification_token default:** If a default of `None` is needed for backward compatibility, type it as `Optional[str]` not `str = None` — Pydantic V2 requires the former. However, since the gate should be mandatory with no default, do NOT give `verification_token` a default value at all.

- **Overwriting verification.txt on retry:** The FilesystemMiddleware `write_file` tool creates/overwrites files only — there is NO native append mode (verified from `filesystem.py` `WRITE_FILE_TOOL_DESCRIPTION`). The `edit_file` tool does exact string replacement (requires reading first). To build an audit trail, instruct the agent to: (1) `read_file` current verification.txt content, (2) concatenate old content + new attempt record, (3) `write_file` the full combined content. This is the correct pattern for append-like behavior. Document this explicitly in the system prompt.

- **Parsing the verifier's JSON output in `run_question`:** The verifier communicates with the main agent via the `task` tool's return value (a `ToolMessage`). The main agent LLM reads and acts on the JSON. Python code in `run_question` does not parse the verifier response — the agent handles it in its reasoning loop.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Subagent registration | Manual `SubAgentMiddleware(backend=..., subagents=[...])` in `middleware` list | `create_deep_agent(subagents=[...])` | Library builds middleware, adds GP agent, applies default middleware stack automatically |
| Fuzzy string matching | Levenshtein or trigram custom implementation | `difflib.get_close_matches` (stdlib) | Already available; tested working at cutoff=0.6; no new dependency |
| Token generation | UUID or random string | `hashlib.sha256(answer.encode()).hexdigest()[:16]` | Deterministic; testable; stdlib |
| Decimal re-execution | Re-implement arithmetic evaluator | Reuse `calculate()` from `calculate.py` | Already AST-safe; Decimal-exact; tested |

**Key insight:** The verifier's arithmetic re-execution check should call the existing `calculate()` function by parsing the expression from `calc.txt`. This is the one place where the verifier could use a domain tool — but since it runs as an LLM subagent with system prompt instructions, it should be instructed to apply the Decimal arithmetic mentally or call `calculate()` if the spec allows. Simplest: expose `calculate` in the verifier's tool list so it can call it directly.

---

## Common Pitfalls

### Pitfall 1: Verifier Inheriting All Main Agent Tools

**What goes wrong:** `create_deep_agent` fills in `spec.get("tools", tools or [])` for subagents that don't specify `tools`. This means the verifier inherits `route_files`, `normalize_answer`, etc. The verifier could then call `normalize_answer` from within its own reasoning, bypassing the token gate.

**Why it happens:** The `SubAgent.tools` field is `NotRequired` (line 65 of `subagents.py`). Omitting it triggers the default inheritance path in `graph.py` line 235.

**How to avoid:** Always set `"tools": []` explicitly in `VERIFIER_SUBAGENT_SPEC`. The verifier will still get filesystem tools from the default middleware stack (FilesystemMiddleware adds `read_file`, `write_file`, etc.). If arithmetic re-execution is needed as a tool call, pass `"tools": [calculate]` explicitly.

**Warning signs:** Test shows verifier calling `normalize_answer` — a circular dependency that bypasses the gate.

### Pitfall 2: Verification Token as Optional with Default None

**What goes wrong:** If `normalize_answer(raw, verification_token=None)` is defined with a `None` default, Pydantic V2 generates a schema where `verification_token` is optional. The LLM can omit it without error, defeating VER-04.

**Why it happens:** Pydantic infers optionality from the default value.

**How to avoid:** Define `normalize_answer(raw: str, verification_token: str)` with NO default. Pydantic V2 marks it as required in the JSON schema. The LLM cannot call it without providing the token. The existing tests that call `normalize_answer("someraw")` without a token will break — update those tests to pass a valid token.

**Warning signs:** `normalize_answer` tool schema in debug output shows `"required": ["raw"]` without `"verification_token"`.

### Pitfall 3: Verifier System Prompt References `{uid}` Without Substitution

**What goes wrong:** The system prompt template contains `{uid}` but the main agent passes the actual UID in the task description, not via system prompt interpolation. If the verifier's system prompt has `{uid}` as a literal Python format placeholder that never gets substituted, it shows `{uid}` to the LLM.

**Why it happens:** `SubAgent.system_prompt` is a plain string passed once at agent creation time. It is not re-formatted per task invocation.

**How to avoid:** The verifier system prompt must NOT contain `{uid}` as a format placeholder. Instead, instruct the verifier: "The task description will tell you the UID. Extract it from the task description and use it to construct file paths." The main agent passes the UID in the task description string.

**Warning signs:** LLM reads `{uid}/evidence.txt` literally and fails `read_file`.

### Pitfall 4: No Native Append Mode in FilesystemMiddleware

**What goes wrong:** The system prompt instructs the agent to "append" to verification.txt, but FilesystemMiddleware's `write_file` tool only creates/overwrites a file. If the agent calls `write_file` naively with just the new attempt record, it wipes prior records.

**Why it happens:** Verified from `filesystem.py` `WRITE_FILE_TOOL_DESCRIPTION` (line 171): "The write_file tool will create a new file." There is no `append_file` tool. The `edit_file` tool does exact string replacement (requires reading the file first, and the old_string must be present verbatim).

**How to avoid:** Instruct the agent with this explicit sequence for writing each verification attempt:
1. `read_file(path="{uid}/verification.txt")` — get current content (or empty string if file does not exist yet)
2. Build new_content = old_content + new_attempt_record
3. `write_file(path="{uid}/verification.txt", content=new_content)`

This produces the audit trail behavior. The system prompt must spell out these three steps explicitly.

Also: update the Phase 3 smoke test `test_smoke_verification_txt_is_stub` — Phase 4 replaces the "pending" stub with real verification records. The test assertion must change.

**Warning signs:** verification.txt contains only the LAST attempt's record (overwrite without read-first happened).

### Pitfall 5: Retry Count Confusion — Agent Doesn't Track Attempt Number

**What goes wrong:** The main agent has no built-in counter. If it loses track of how many verification attempts were made, it may retry more than twice or give up too early.

**Why it happens:** LLM agents don't natively count turns. They reason from message history.

**How to avoid:** The system prompt must instruct the agent to count attempts by reading the verification.txt audit trail (each attempt is appended, so the number of separator sections equals the number of attempts). Alternatively, instruct the agent to append attempt number to each verification.txt entry. Either way, verification.txt serves as the ground truth for attempt counting.

**Warning signs:** Agent retries 3+ times, or gives up after 1 failed attempt.

### Pitfall 6: `difflib.get_close_matches` Cutoff Too Low or Too High

**What goes wrong:** At cutoff=0.4, unrelated headers like "Veterans' Administration" match "National defense and associated activities". At cutoff=0.85, valid variants like "National defense and related activities" fail to match.

**Why it happens:** `difflib.SequenceMatcher` uses the Ratcliff/Obershelp algorithm, which scores character-level overlap. Short shared substrings ("National defense") drive the score.

**How to avoid:** Use cutoff=0.6 as the default. In the context of our corpus, column headers for defense spending across eras share the prefix "National defense" and differ in the suffix. 0.6 keeps valid variants without false-positives from unrelated categories (e.g., "Veterans' Administration" scores ~0.45 against "National defense and related activities").

**Warning signs:** Era resolver returns null for valid variants (cutoff too high) or returns wrong column (cutoff too low).

### Pitfall 7: The "Cannot Determine" Response Bypasses normalize_answer

**What goes wrong:** After 3 failed attempts, the agent must NOT call `normalize_answer`. If the system prompt is unclear, the agent might still call it with the last answer and a null/missing token, triggering the `ValueError` gate — producing a stack trace rather than a clean "cannot determine" response.

**Why it happens:** The agent is reasoning under uncertainty and may try one more normalization as a last resort.

**How to avoid:** System prompt must explicitly state: "After 3 failed attempts, return the 'cannot determine' message directly as your final text response. Do NOT call normalize_answer. Do NOT call the verifier again."

**Warning signs:** Integration test for "cannot determine" scenario shows a `ValueError` in the agent's message history.

---

## Code Examples

Verified patterns from installed library source and stdlib:

### SubAgent TypedDict (from deepagents source)
```python
# Source: workspace/.venv/Lib/site-packages/deepagents/middleware/subagents.py lines 22-78
# SubAgent is a TypedDict with required: name, description, system_prompt
# Optional: tools, model, middleware, interrupt_on, skills

VERIFIER_SUBAGENT_SPEC: SubAgent = {
    "name": "verifier",
    "description": (
        "Stateless verification subagent. Pass the proposed answer and scratch UID. "
        "Returns status (PASS/FAIL/ERROR), issues list, and token."
    ),
    "system_prompt": VERIFIER_SYSTEM_PROMPT,
    "tools": [calculate],   # explicit — arithmetic re-execution; no domain tools
}
```

### create_deep_agent with subagents (from graph.py)
```python
# Source: workspace/.venv/Lib/site-packages/deepagents/graph.py lines 81-99, 240-267
# subagents parameter accepts list[SubAgent | CompiledSubAgent]
# Library prepends: TodoListMiddleware, FilesystemMiddleware, SummarizationMiddleware,
#   AnthropicPromptCachingMiddleware, PatchToolCallsMiddleware
# Then appends spec.get("middleware", [])

agent = create_deep_agent(
    model=model,
    tools=[...],
    subagents=[VERIFIER_SUBAGENT_SPEC],   # verified parameter name from graph.py line 87
    system_prompt=SYSTEM_PROMPT,
    backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
    checkpointer=MemorySaver(),
)
```

### How main agent calls verifier (task tool)
```python
# The main agent LLM calls the task tool with subagent_type="verifier"
# Source: subagents.py lines 430-446 — task() function signature

# In agent reasoning (pseudocode — LLM generates this tool call):
task(
    subagent_type="verifier",
    description=(
        f"Verify answer for UID {uid}. "
        f"Proposed answer: '19.14%'. "
        f"Scratch directory: {uid}/. "
        f"Check evidence coverage, unit consistency, arithmetic (if calc.txt exists), "
        f"and format. Return JSON with status, issues, token."
    )
)
# Returns ToolMessage with the verifier's final message content
```

### Verification token generation
```python
# Source: Python stdlib hashlib — no installation needed
import hashlib

def _generate_token(answer: str) -> str:
    """Short deterministic token for a verified answer."""
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]

# Example: _generate_token("19.14%") → "a3f8c2d1e0b7904f" (deterministic)
```

### normalize_answer signature change
```python
# Modified signature — verification_token is REQUIRED (no default)
def normalize_answer(raw: str, verification_token: str) -> dict:
    if not verification_token:
        raise ValueError(
            "normalize_answer requires a non-null verification_token from the verifier. "
            "Call task(subagent_type='verifier') first."
        )
    # existing normalization logic unchanged
    ...
```

### Era-aware resolver
```python
# Source: Python stdlib difflib — tested in repo Python environment
import difflib

def resolve_era_column_header(
    target_series: str,
    candidate_headers: list[str],
    cutoff: float = 0.6,
) -> str | None:
    """Return best-matching column header, or None if no match above cutoff."""
    matches = difflib.get_close_matches(target_series, candidate_headers, n=1, cutoff=cutoff)
    return matches[0] if matches else None
```

### verification.txt append pattern (system prompt instruction)
```
After calling task(subagent_type="verifier"), APPEND to {uid}/verification.txt:
  Format:
    Attempt {N}: {timestamp}
    Status: {PASS|FAIL|ERROR}
    Issues: {issues_list or "none"}
    Token: {token or "null"}
    ---
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| verification.txt stub "verification: pending (Phase 4)" | Real verification records appended per attempt | Phase 4 | test_smoke_verification_txt_is_stub must be updated |
| normalize_answer(raw) — no token required | normalize_answer(raw, verification_token) — token required | Phase 4 | All callers of normalize_answer must pass token |
| SubAgentMiddleware as separate middleware item | `create_deep_agent(subagents=[...])` parameter | Phase 3.1 research clarified | library handles middleware construction internally |

**Deprecated after Phase 4:**
- `verification.txt` stub content: replaced by real verification records
- `normalize_answer(raw)` single-argument call: replaced by two-argument form

---

## Open Questions

1. **Whether the verifier should get `calculate` in its explicit tools list**
   - What we know: The verifier needs to re-execute arithmetic expressions for Check 3. It can either do this mentally (Decimal arithmetic in LLM reasoning) or call `calculate()` as a tool.
   - What's unclear: LLM arithmetic reasoning is unreliable. For exact Decimal match, calling `calculate()` is safer.
   - Recommendation: Pass `"tools": [calculate]` in the verifier spec. The `calculate()` function is already tested and handles all arithmetic safely. The verifier gets `calculate` for re-execution plus filesystem tools from the default middleware stack for reading scratch files.

2. **How to handle the token in the verifier's final message**
   - What we know: The verifier subagent returns its final message as a `ToolMessage` to the main agent (see `subagents.py` line 414: `result["messages"][-1].text`). The main agent must parse the JSON to extract the token.
   - What's unclear: The LLM-generated JSON may have formatting variation. Strict JSON parsing could fail on minor formatting differences.
   - Recommendation: The verifier system prompt must instruct it to return ONLY the JSON object as its final message (no prose). Use `json.loads` defensively with a try/except in the system prompt instruction to the main agent. Alternatively, instruct the verifier to use Python-dict-like syntax that is unambiguous.

3. **Test strategy for verifier integration (no LLM)**
   - What we know: `test_verifier.py` should be unit tests (no LLM call). The verifier logic is pure file-reading + checks. But the verifier runs AS an LLM subagent, so unit testing it in isolation means testing the helper functions (resolve_era_column_header, _generate_token) separately from the LLM reasoning.
   - What's unclear: How to test the four checks without spinning up an LLM.
   - Recommendation: Test the helper functions directly as plain Python (no LLM). Integration test for full verifier behavior requires LLM. Unit tests: `test_resolve_era_column_header`, `test_generate_token`, `test_normalize_answer_requires_token`.

4. **RESOLVED: System prompt update for verification.txt — no native append**
   - What we know: FilesystemMiddleware `write_file` creates/overwrites (verified from `filesystem.py` line 171). `edit_file` does string replacement. No append mode exists.
   - Resolution: Use read-then-write pattern (read_file + write_file with concatenated content). Document in system prompt with explicit 3-step sequence.
   - Confidence: HIGH
---

## Sources

### Primary (HIGH confidence — verified from installed library source)
- `workspace/.venv/Lib/site-packages/deepagents/middleware/subagents.py` — `SubAgent` TypedDict (lines 22-78), `SubAgentMiddleware.__init__` (lines 545-619), `_get_subagents` new API (lines 621-670), `_build_task_tool` (lines 374-471), task tool signature (lines 430-446)
- `workspace/.venv/Lib/site-packages/deepagents/graph.py` — `create_deep_agent` signature (lines 81-99), subagent processing (lines 209-238), main middleware stack construction (lines 248-267), `BASE_AGENT_PROMPT` (lines 35-67)
- `workspace/.venv/Lib/site-packages/deepagents/middleware/__init__.py` — public exports: `SubAgent`, `CompiledSubAgent`, `SubAgentMiddleware`

### Primary (HIGH confidence — verified from codebase)
- `workspace/src/agent.py` — current `create_agent()`, `SYSTEM_PROMPT`, `run_question`
- `workspace/src/tools/normalize_answer.py` — current signature (single `raw` arg), normalization logic
- `workspace/src/tools/calculate.py` — `calculate()`, `pct_change()`, `sum_values()` — reusable for verifier arithmetic
- `workspace/src/scratch.py` — `SCRATCH_FILES`, `prepare_scratch`
- `workspace/tests/test_agent.py` — existing integration tests to update
- `workspace/requirements.txt` — pinned library versions, no new deps needed

### Primary (HIGH confidence — Python stdlib, verified functional)
- `difflib.get_close_matches` — tested in repo environment: correctly matches "National defense and related activities" from similar series names at cutoff=0.6
- `hashlib.sha256` — stdlib, deterministic token generation
- `decimal.Decimal` — already imported and used in `calculate.py`

### Secondary (MEDIUM confidence)
- `workspace/.venv/Lib/site-packages/deepagents/middleware/filesystem.py` — `WRITE_FILE_TOOL_DESCRIPTION` (line 171): write_file creates/overwrites only. `EDIT_FILE_TOOL_DESCRIPTION` (line 162): edit_file does exact string replacement. No append mode. Tools available: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`.

---

## Metadata

**Confidence breakdown:**
- SubAgentMiddleware / create_deep_agent API: HIGH — read directly from installed library source (subagents.py, graph.py)
- Verifier subagent pattern: HIGH — derived from library source + SubAgent TypedDict
- normalize_answer gate: HIGH — derived from existing function + Pydantic V2 behavior (confirmed in Phase 3.1 research)
- Fuzzy matching: HIGH — difflib.get_close_matches tested in repo environment with representative corpus column headers
- Token generation: HIGH — Python stdlib hashlib, deterministic
- Retry loop via system prompt: MEDIUM — pattern is sound but exact LLM behavior in counting attempts is not mechanically guaranteed; relies on agent reading verification.txt for attempt count
- FilesystemMiddleware append support: HIGH — verified from source; write_file=overwrite, edit_file=string-replace, no native append; use read-then-write pattern

**Research date:** 2026-03-20
**Valid until:** 2026-04-19 (deepagents 0.4.11 is pinned in requirements.txt — stable for 30 days)
