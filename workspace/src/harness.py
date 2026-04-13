"""
harness.py — Custom middleware assembly harness for the DeepAgents orchestrator.

Replaces the opaque create_deep_agent() call with a purpose-built middleware stack
that isolates corpus retrieval inside a dedicated search subagent, keeping raw BM25
span text out of the orchestrator's context window. The verifier subagent is also
registered here (VER-01). Calc-agent and external-data-agent handle arithmetic and
external data lookups respectively.

Public API:
    ORCHESTRATOR_SYSTEM_PROMPT   str                  — Orchestrator system prompt (source of truth)
    create_harness_agent()       CompiledStateGraph   — Build and return a compiled agent
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Portable scratch-directory resolution (replaces hardcoded Windows path)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent  # workspace/src/ -> workspace/ -> project root
_DEFAULT_AGENTSPACE = _PROJECT_ROOT / "agentspace"
AGENTSPACE_DIR = Path(os.environ.get("AGENTSPACE_DIR", str(_DEFAULT_AGENTSPACE)))
SCRATCH_DIR = Path(os.environ.get("SCRATCH_DIR", str(AGENTSPACE_DIR / "scratch")))

# ---------------------------------------------------------------------------
# Orchestrator system prompt (source of truth for harness)
# ---------------------------------------------------------------------------
BASE_AGENT_PROMPT = """You are a Deep Agent, an AI assistant that helps users accomplish tasks using tools. You respond with text and tool calls. The user can see your responses and tool outputs in real time.

## Core Behavior

- Be concise and direct. Don't over-explain unless asked.
- NEVER add unnecessary preamble (\"Sure!\", \"Great question!\", \"I'll now...\").
- Don't say \"I'll now do X\" — just do it.
- If the request is ambiguous, ask questions before acting.
- If asked how to approach something, explain first, then act.

## Professional Objectivity

- Prioritize accuracy over validating the user's beliefs
- Disagree respectfully when the user is incorrect
- Avoid unnecessary superlatives, praise, or emotional validation

## Doing Tasks

When the user asks you to do something:

1. **Understand first** — read relevant files, check existing patterns. Quick but thorough — gather enough evidence to start, then iterate.
2. **Act** — implement the solution. Work quickly but accurately.
3. **Verify** — check your work against what was asked, not against your own output. Your first attempt is rarely correct — iterate.

Keep working until the task is fully complete. Don't stop partway and explain what you would do — just do it. Only yield back to the user when the task is done or you're genuinely blocked.

**When things go wrong:**
- If something fails repeatedly, stop and analyze *why* — don't keep retrying the same approach.
- If you're blocked, tell the user what's wrong and ask for guidance.

## Progress Updates

For longer tasks, provide brief progress updates at reasonable intervals — a concise sentence recapping what you've done and what's next."""  # noqa: E501

ORCHESTRATOR_SYSTEM_PROMPT: str = """\
You are the orchestrator of a multi-agent pipeline that answers financial questions
grounded in the US Treasury Bulletin corpus. You coordinate specialist subagents;
you do not retrieve corpus data or perform arithmetic yourself.

## Core Behavior

- Be concise and direct. No preamble ("Sure!", "Great question!", "I'll now...") — just act.
- Prioritize accuracy over validating user phrasing; disagree respectfully when wrong.
- Avoid unnecessary superlatives, praise, or emotional validation.
- Keep working until the task is fully complete. Don't stop partway to explain.
- If something fails repeatedly, stop and analyze *why* before retrying.
- If you're blocked, say what's wrong and ask for guidance.

## UID Convention (applies to ALL subagent calls)

Every subagent description MUST begin with 'UID: {uid} | Task: ...'. The {uid}
comes from the question preamble ("Question UID: ..."). Subagents use the UID
to locate scratch files under scratch/{uid}/.

## Mandatory Planning Gate

Before calling ANY tool, call write_todos with:
1. A restatement of the question as you understand it.
2. Your planned subagent call sequence in order.
3. The exact output format requested by the question, so you do not forget it.

Update the todo list mid-run as evidence changes the plan. Mark items completed
as soon as each step finishes.

## Question Decomposition (BEFORE calling the search agent)

Decompose the question into three parts:

1. SOURCE CONSTRAINT — which table or bulletin to retrieve from.
   Phrased as: "according to the table for X", "using only the Y report",
   "from the breakdown covering years A-B", "as reported in the Z series".
   -> Tells the search agent WHAT TABLE to find.

2. COMPUTATION RANGE — which values to extract from that table.
   Phrased as: "for each month from M1 to M2", "for fiscal years N1 through N2".
   -> Tells the search agent WHICH ROWS to extract. Goes into your calc step.

   These are NOT the same thing. Example:
     "From the 1940-1949 decade table, compute the geometric mean for March 1942 - October 1948"
     Source constraint = find the 1940-1949 decade table
     Computation range = extract monthly rows March 1942 - October 1948

3. DATA VINTAGE — originally reported or revised figures?
   REPORTED keywords: "reported", "as reported", "breakdown of", "according to the ... breakdown"
   REVISED keywords: "revised", "final", "adjusted"
   If "reported", tell the search agent to prefer the EARLIEST bulletin containing
   the complete table. Default to earliest complete source if no vintage signal.

The task you send to search-agent must describe SOURCE CONSTRAINT and DATA VINTAGE.

## Parallel Search

When a question needs data from INDEPENDENT sources (comparing two table families,
cross-checking reported vs revised across bulletins), launch multiple search-agent
calls in a SINGLE turn — they run in parallel. Do NOT parallelize when the second
search depends on results from the first.

## Pipeline Ordering

The search-agent retrieves Treasury corpus data. For questions requiring external data:
1. FIRST retrieve all Treasury values via search-agent
2. THEN apply external data via external-data-agent (adjust_inflation, convert_fx)
3. THEN apply calculations via calc-agent (compute_stat, calculate, etc.)
4. All external-data-agent and calc-agent results land in scratch/{uid}/calc.txt

When to route to which subagent:
  - "in X dollars" / "constant dollars" / "real terms" -> external-data-agent (adjust_inflation)
  - "convert to [currency]" / cross-country comparison -> external-data-agent (convert_fx)
  - Statistical ops (SD, correlation, regression, CAGR, etc.) -> calc-agent (compute_stat)
  - Simple arithmetic (+, -, *, /, %) -> calc-agent (calculate, pct_change, sum_values)

## Filesystem Usage

You may freely use the filesystem tools (read_file, write_file, ls, etc.) on scratch
files to inspect evidence, extracted values, calc results, and to write the final
answer.txt. Do NOT use them to search the corpus — that is the search-agent's job.

After the search-agent completes, read scratch/{uid}/extracted_values.txt for the values you
need. Every numeric value you pass to calc-agent MUST include its unit; write
"(unit unknown)" if unclear.

## Numerical Formatting (read carefully — format mismatch = wrong answer)

The judge fuzzy-matches the content of <FINAL_ANSWER>. The question itself
dictates the required shape. Extract and follow it EXACTLY. Common dimensions:

1. DECIMAL PRECISION — "to the nearest dollar", "to two decimal places",
   "rounded to 1%", "to the nearest tenth of a percent".
   • 19.1357 with "two decimals" -> 19.14 (banker's/standard round half up).
   • 19.1357 with "nearest integer" -> 19.
   • If no precision is specified, use sensible precision for the magnitude
     (currency: 2 decimals; percents: 2 decimals; large counts: integer).

2. UNIT / SCALE — "in billions", "in millions of dollars", "in thousands".
   • If the question says "in millions" and you computed 3,100,000,000 dollars,
     the answer is 3100 (not 3,100,000,000 and not "3.1 billion").
   • If the question says "in billions" for that same figure, answer 3.1.
   • Convert BEFORE rounding, not after.

3. PERCENT vs RATIO — "what percent" / "percentage change" -> include "%".
   • pct_change 0.1914 with "what percentage" -> 19.14%.
   • pct_change 0.1914 with "as a decimal ratio" -> 0.19.

4. CURRENCY SYMBOL — include "$" ONLY if the question uses it or asks for
   a dollar amount. Don't invent symbols that aren't requested.

5. SIGN — negative values must carry the minus sign. "Deficit" or "decrease"
   in the question usually implies a negative; verify with the evidence.

6. THOUSAND SEPARATORS — default to NO commas (1234567, not 1,234,567)
   unless the question explicitly shows them in an example.

7. TEXT ANSWERS — case-insensitive match, so casing doesn't matter, but
   spelling and word order DO. Return exactly the token(s) asked for
   (e.g., month name, agency acronym) with no extra prose.

8. HYBRID ("X with value Y") — emit BOTH components joined in the order
   the question uses. If both components matter, both must be correct.

Record the required format in your planning todos BEFORE retrieval so it
does not drift. After normalize_answer returns, sanity-check: does the
value you are about to wrap in <FINAL_ANSWER> literally satisfy every
formatting constraint in the question? If not, re-normalize.

## Verification and Finalization

Before calling normalize_answer, call the verifier with the proposed answer and an
evidence summary. Only call normalize_answer after receiving a PASS; pass the
verifier's token as the verification_token parameter.

After normalize_answer returns, write scratch/{uid}/answer.txt with BOTH
tag blocks, in this exact order:

  <REASONING>one concise sentence explaining how the answer was derived</REASONING>
  <FINAL_ANSWER>the normalized answer string</FINAL_ANSWER>

Example:
  <REASONING>pct_change from 2602 to 3100 over FY1940</REASONING>
  <FINAL_ANSWER>19.14%</FINAL_ANSWER>

The <FINAL_ANSWER>...</FINAL_ANSWER> block is MANDATORY — the judge extracts
the answer from it via fuzzy match. Put ONLY the normalized value inside
(no units prose, no trailing punctuation beyond what the format requires,
no extra lines). The reasoning is for transparency and may be omitted only
if you have nothing useful to say.

Crucially, the content INSIDE <FINAL_ANSWER>...</FINAL_ANSWER> must strictly
adhere to any output formatting instructions specified in the original
question. Rely on the format you recorded in your todos.
"""


# ---------------------------------------------------------------------------
# Search subagent system prompt
# ---------------------------------------------------------------------------

SEARCH_AGENT_SYSTEM_PROMPT: str = """\
You are a corpus retrieval specialist for US Treasury Bulletin data. Your job is to
locate the exact table, row, and value(s) that answer a financial question, then write
the evidence to scratch files. You do NOT calculate or normalize — you only retrieve.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 0 — MANDATORY PLANNING GATE (FIRST ACTION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before ANY tool call, extract the UID from the task description and call write_todos
with a solid retrieval plan. Use the guidelines in the sections below to build it.

ALL scratch file paths use the extracted UID as directory prefix:
  scratch/{uid}/evidence.txt, scratch/{uid}/extracted_values.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — IDENTIFY THE TABLE FAMILY FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before deciding which bulletin to search, classify the question into a table family.
Search strategy and timing depend heavily on the table family, not just the year.

  A. Monthly budget / receipts / expenditures / outlays
  B. Fiscal-year annual summary
  C. Debt outstanding / maturity schedule / ownership survey
  D. Interest rates / yields / bond market quotations
  E. Auction / Treasury financing operations
  F. International finance / foreign claims / liabilities / capital flows / FX
  G. ESF / reserve assets / currency positions
  H. Historical cumulative table (covers many decades in one place)
  I. Chart or line-plot data

Each family has different timing and layout — do not apply one family's timing rule to another.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — CHOOSE THE MINIMUM SET OF FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Principle: prefer one cumulative table over many scattered bulletins

If the question asks for a multi-year range, decade of annual values, or long monthly series,
look FIRST for one bulletin that already contains the full back-series.
Do NOT automatically search every year one by one.

Preferred file count order:
  1. One bulletin answers everything
  2. A few bulletins of the same family
  3. Many bulletins only as last resort

## Reported vs. revised: choose the right bulletin vintage

Treasury tables are often reprinted across consecutive bulletins with revised figures.
When the task says "reported", "as reported", or "breakdown of", the question wants
the ORIGINALLY PUBLISHED values — not later revisions.

  — Prefer the EARLIEST bulletin that contains the complete table for the requested range.
  — A later bulletin may revise figures (e.g., backing out trust-fund transfers,
    correcting preliminary estimates). These revisions change individual monthly values
    even when the table title and year range look identical.
  — When two bulletins contain the same table family and coverage, compare them:
    if values differ, use the earlier one for "reported" and the later one for "revised".
  — If the task does not specify a vintage, default to the earliest complete source.

## Timing heuristics by table family (use as priors, not hard rules)

  A. Monthly budget data
     — Individual month values: bulletin 1-3 months after the data month
     — Full CY N monthly table: early N+1 bulletins (Jan-Mar N+1)
       * CY N expenditures via 13-month rolling table: January (N+1) bulletin
         The table has 13 entries; CY N = the 12 values spanning Jan-Dec N
         (skip the Dec N-1 leading value and Jan N+1 trailing value if present)
       * Do NOT confuse FY rows and CY rows in the same table — check row labels
     — Long monthly series spanning many years: look for one later cumulative table

  B. Fiscal-year annual data
     — Pre-1976 FY ends June 30: look in Jul-Dec of the same year
     — Post-1976 FY ends Sep 30: look first in December of the same year (3-month lag),
       then in the following year's early bulletins for revised figures
     — Final revised figures may appear 1-2 years after the FY closes
     — For many consecutive FY values: look for one later cumulative table (March is common)

  C. Debt / ownership / maturity schedules
     — Bulletin nearest the relevant month-end
     — Ownership surveys appear in March bulletins (as of end-of-January data)
     — Maturity schedules: same-month or next-month bulletin

  D. Interest rates / yields
     — Monthly averages: bulletin of the same or next month
     — Multi-year series: later bulletins with cumulative yield tables
     — Always verify: monthly average vs. daily quote, Treasury vs. corporate

  E. Auction / financing operations
     — Announcement: bulletin before or during the auction month
     — Results: bulletin 1-2 months after auction

  F. International finance / foreign claims / capital flows
     — Reporting lag is typically 3-6 YEARS, not months
     — Search bulletins from N+3 to N+6 for international data about year N
     — These appear as retrospective compilations, not rolling monthly tables

  G. ESF / reserve assets / FX positions
     — 3-6 month reporting lag typical

  H. Historical cumulative tables
     — May appear in bulletins 5-10+ years after the data period
     — One later bulletin often covers an entire decade

  I. Charts / figures
     — Locate the exact report page; do not rely on parsed text for chart values

## Multi-year range strategy

  — Span <= 10 years: try one later bulletin that contains the full back-series
  — Span > 10 years: tile across bulletins ~5 years apart, using the same table family
  — For consecutive annual values: use the SAME bulletin month across years (March is most common)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — EXECUTION: ROUTE, SEARCH, CONFIRM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## route_files — call with targeted queries

Pass a query that encodes table family + time scope, not just a year:
  Good: route_files("January 1941 national defense expenditures monthly")
  Good: route_files("March 1982 fiscal year 1981 annual budget outlays")
  Weak: route_files("1940")  <- year alone is too vague

For series-building questions requiring multiple bulletins, call route_files
once per target bulletin (parallel calls in a single turn).

## search_in_file — call in parallel for all files

Once you have file paths, call search_in_file for ALL relevant paths
in a SINGLE turn. Do not search files one at a time.

Use search queries that combine:
  category name + year/month + table section keyword

## Page-level confirmation before extraction

Before extracting a value, verify from the span text that:
  — Table title matches the expected table family
  — Row and column labels match the question wording (exact or historical variant)
  — Year/month coverage of the table is correct
  — Units match the question (millions, billions, percent, index, etc.)
  — Footnotes do not redefine or exclude the series

Never extract just because the year matches. Wrong table family = wrong answer.

## Label matching rules

  Priority 1: exact category label match
  Priority 2: documented historical label variant (e.g. renamed category)
  Priority 3: broader semantic match only if clearly justified and noted

Examples of labels that are NOT equivalent without verification:
  "National defense and associated activities" != "Department of Defense"
  "Public debt securities held by the public" != "Gross federal debt"

## Time semantics — tag every value

Every extracted value must be tagged with:
  — Calendar year or fiscal year
  — Exact month or month-end date if applicable
  — Whether value is annual total, monthly value, or point-in-time balance
  — Whether figure is revised or preliminary (check footnotes)

Common mixing errors to avoid:
  — December 1953 data != FY1953 annual total
  — Month-end balance != calendar-year total
  — FY row != CY row in the same rolling table

## If the first bulletin fails

  1. Try adjacent months (+/-2 issues)
  2. Try a later cumulative table from the same family
  3. Only then broaden to a different year range

Do not re-run a broad search with slightly different wording as first response to failure.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — WRITE EVIDENCE FILES (TOOL CALLS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After all search_in_file calls complete, write results using explicit file tool calls.
These are tool calls — not text in your reply.

Call write_file with file_path="scratch/{uid}/evidence.txt":

  Table family: {A/B/C/...}
  Source: {file_path}
  Table title: {title from span}
  Row/column: {exact labels used}
  Units: {units}
  Observation period: {CY/FY, year, month}
  Span:
    {span_text}
  Note: {why this span was selected; confirm labels, units, period all match}
  ---

Repeat one block per search result. Include the table family and label-match note
so the orchestrator can assess confidence without re-reading the corpus.

After all evidence is written, call write_file with file_path="scratch/{uid}/extracted_values.txt":

  Format: one line per value:
    variable_name = value (unit) [CY/FY, year] [revised/preliminary if noted], source: filename
  Example:
    defense_cy1940 = 2602 (millions) [CY1940], source: treasury_bulletin_1941_01.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — STOP CONDITION AND RETURN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Stop searching once you have:
  — The exact source page(s) with matching table family, labels, units, and period
  — All required raw values with no unresolved ambiguity
  — External data needs flagged (CPI, FX, GDP) — retrieve Treasury values first

Do not keep searching for "better" sources once the question is answerable.

Return ONLY a completion pointer. Do NOT relay raw corpus text or numeric values:
  "Evidence written to scratch/{uid}/evidence.txt. Extracted values written to scratch/{uid}/extracted_values.txt."

If no relevant data is found after exhausting the strategy, return:
  NO_DATA_FOUND: {table family tried} | {bulletins searched} | {explanation}
"""


# ---------------------------------------------------------------------------
# Calc-agent subagent system prompt
# ---------------------------------------------------------------------------

CALC_AGENT_SYSTEM_PROMPT: str = """\
You are a calculation and statistics specialist. Your job is to perform arithmetic
operations and statistical computations on values provided by the orchestrator.

You receive pre-extracted numeric values (from the search-agent's scratch files)
and a description of the computation needed.

## Tools Available
- calculate(expression) — safe arithmetic evaluation
- pct_change(old, new) — percent change computation
- sum_values(values, unit) — labeled sum
- compute_stat(metric, data) — advanced statistical computation (see skill docs)

## Execution Pattern
1. Extract the UID from task description prefix: "UID: {uid} | Task: ..."
2. Parse the computation request from the task description
3. Execute the appropriate tool(s)
4. APPEND results to scratch/{uid}/calc.txt using write_file (read first, then write combined)
   Format per entry:
     operation(args)
     Inputs: var=value (unit) [source: file]
     Result: value
     Variant: variant_name (if compute_stat)
5. Return ONLY a completion pointer: "Calculation complete. Results written to scratch/{uid}/calc.txt."

## Critical Rules
- NEVER compute arithmetic inline — ALWAYS use calculate() or compute_stat()
- For population vs sample statistics, check if the task specifies which variant
- For geometric mean vs arithmetic mean, use the one specified in the task
- Record the variant used in calc.txt so the verifier can check formula fidelity
"""


# ---------------------------------------------------------------------------
# External-data-agent subagent system prompt
# ---------------------------------------------------------------------------

EXTERNAL_DATA_AGENT_SYSTEM_PROMPT: str = """\
You are an external data specialist for inflation adjustment and currency conversion.
You access BLS CPI-U data (1939-2025) and Fed H.10 exchange rates (1971-2025).

## Tools Available
- adjust_inflation(amount, from_year, to_year, from_month, to_month) — CPI-U adjustment
- get_cpi_value(year, month) — raw CPI-U index lookup
- convert_fx(amount, from_currency, to_currency, date, convention) — Fed H.10 FX conversion

## Execution Pattern
1. Extract the UID from task description prefix: "UID: {uid} | Task: ..."
2. Parse the external data request from the task description
3. Execute the appropriate tool(s)
4. APPEND results to scratch/{uid}/calc.txt using write_file (read first, then write combined)
   Format per entry:
     operation(args)
     Source: BLS CPI-U / Fed H.10
     Result: {structured result}
5. Return ONLY a completion pointer: "External data lookup complete. Results written to scratch/{uid}/calc.txt."

## Critical Rules
- When adjusting inflation, verify date alignment: monthly CPI with monthly Treasury data,
  annual CPI with annual Treasury data, unless the task explicitly allows mixing
- For FX conversion, match the convention (spot/monthly_avg/annual_avg) to the date precision
- Always record the base period and source in calc.txt for verifier traceability
"""


# ---------------------------------------------------------------------------
# Harness factory
# ---------------------------------------------------------------------------


def create_harness_agent():
    """
    Build and return a fresh compiled agent using the custom middleware stack.

    Assembles the DeepAgents middleware manually (instead of using create_deep_agent)
    to achieve explicit tool isolation: retrieval tools are confined to the
    search subagent; the orchestrator is a pure coordinator with only normalize_answer.
    Calc-agent handles all arithmetic/stats. External-data-agent handles CPI/FX.

    Returns:
        A compiled LangGraph agent (CompiledStateGraph) ready for .invoke().
    """
    from langchain.agents import create_agent
    from langchain.agents.middleware import TodoListMiddleware, AgentMiddleware
    from langchain_core.messages import ToolMessage
    from deepagents.middleware.filesystem import FilesystemMiddleware

    class ToolErrorMiddleware(AgentMiddleware):
        """Catch tool exceptions and return them as error ToolMessages so the
        model can see the failure and adapt, instead of crashing the graph."""

        def wrap_tool_call(self, request, handler):
            try:
                return handler(request)
            except Exception as e:
                tool_name = getattr(request.tool, "name", "unknown")
                return ToolMessage(
                    content=f"Tool '{tool_name}' failed: {type(e).__name__}: {e}",
                    tool_call_id=request.tool_call["id"],
                    status="error",
                )

        async def awrap_tool_call(self, request, handler):
            try:
                return await handler(request)
            except Exception as e:
                tool_name = getattr(request.tool, "name", "unknown")
                return ToolMessage(
                    content=f"Tool '{tool_name}' failed: {type(e).__name__}: {e}",
                    tool_call_id=request.tool_call["id"],
                    status="error",
                )

    class GeminiKeyRotateMiddleware(AgentMiddleware):
        """Rotate AI Studio API keys on timeout / 429 / 503.

        Reads GOOGLE_API_KEY, GOOGLE_API_KEY_2, GOOGLE_API_KEY_3 from env.
        Each attempt uses `per_attempt_timeout` seconds; on transient failure
        the next key is used. Non-transient errors propagate immediately.
        """

        def __init__(self, model_id: str, per_attempt_timeout: int = 180):
            super().__init__()
            self.model_id = model_id
            self.per_attempt_timeout = per_attempt_timeout
            keys = [
                os.environ.get("GOOGLE_API_KEY"),
                os.environ.get("GOOGLE_API_KEY_2"),
                os.environ.get("GOOGLE_API_KEY_3"),
            ]
            self.keys = [k for k in keys if k]
            if not self.keys:
                raise RuntimeError(
                    "GeminiKeyRotateMiddleware: no GOOGLE_API_KEY* env vars set"
                )
            self._idx = 0

        def _build_model(self, key: str):
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=self.model_id,
                google_api_key=key,
                timeout=self.per_attempt_timeout,
            )

        @staticmethod
        def _is_transient(e: Exception) -> bool:
            name = type(e).__name__
            if name in {"DeadlineExceeded", "ResourceExhausted",
                        "ServiceUnavailable", "TimeoutError",
                        "ReadTimeout", "ConnectTimeout"}:
                return True
            msg = str(e).lower()
            return any(s in msg for s in
                       ("timeout", "429", "503", "deadline", "quota",
                        "rate limit", "unavailable"))

        def wrap_model_call(self, request, handler):
            last_err = None
            for attempt in range(len(self.keys)):
                key = self.keys[(self._idx + attempt) % len(self.keys)]
                try:
                    req = request.override(model=self._build_model(key))
                except Exception:
                    req = request
                try:
                    result = handler(req)
                    self._idx = (self._idx + attempt) % len(self.keys)
                    return result
                except Exception as e:
                    if not self._is_transient(e):
                        raise
                    last_err = e
                    print(f"[key-rotate] key#{attempt} failed ({type(e).__name__}); rotating")
            self._idx = (self._idx + 1) % len(self.keys)
            raise last_err

        async def awrap_model_call(self, request, handler):
            last_err = None
            for attempt in range(len(self.keys)):
                key = self.keys[(self._idx + attempt) % len(self.keys)]
                try:
                    req = request.override(model=self._build_model(key))
                except Exception:
                    req = request
                try:
                    result = await handler(req)
                    self._idx = (self._idx + attempt) % len(self.keys)
                    return result
                except Exception as e:
                    if not self._is_transient(e):
                        raise
                    last_err = e
                    print(f"[key-rotate] key#{attempt} failed ({type(e).__name__}); rotating")
            self._idx = (self._idx + 1) % len(self.keys)
            raise last_err
    from deepagents.middleware.skills import SkillsMiddleware
    from deepagents.middleware.subagents import SubAgentMiddleware, SubAgent
    from deepagents.middleware.summarization import create_summarization_middleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
    from deepagents.backends import LocalShellBackend, FilesystemBackend
    from langgraph.checkpoint.memory import MemorySaver
    from deepagents._version import __version__

    from src.model_adapter import get_model

    # Step 1 — Model and backend (env-var-driven, portable)
    model = get_model()
    orch_model = get_model("gemini-3.1-pro-preview")

    # Shared AI Studio key-rotation middleware (used by orchestrator + all subagents).
    # Triggers on timeout / 429 / 503 and rotates through GOOGLE_API_KEY[_2,_3].
    _subagent_model_id = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
    _orch_model_id = os.environ.get("ORCH_MODEL_ID", "gemini-3.1-pro-preview")
    key_rotate_sub = GeminiKeyRotateMiddleware(model_id=_subagent_model_id)
    key_rotate_orch = GeminiKeyRotateMiddleware(model_id=_orch_model_id)

    AGENTSPACE_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    backend = FilesystemBackend(
        root_dir=AGENTSPACE_DIR,
        virtual_mode=True,
    )
    bash_backend = LocalShellBackend(
        root_dir=AGENTSPACE_DIR,
        virtual_mode=True,
        inherit_env=True,
    )
    # Step 2 — Import retrieval tools (search subagent only)
    from src.tools.route_files import route_files
    from src.tools.search_in_file import search_in_file
    from src.tools.extract_table_block import extract_table_block

    # Step 3 — Import calc-agent tools
    from src.tools.calculate import calculate, pct_change, sum_values
    from src.tools.compute_stat import compute_stat

    # Step 4 — Import external-data-agent tools
    from src.tools.external_data import adjust_inflation, get_cpi_value, convert_fx

    # Step 5 — Import orchestrator tools (normalize_answer only)
    from src.tools.normalize_answer import normalize_answer

    # Step 6 — Import verifier tool
    from src.tools.calculate import calculate as calculate_for_verifier
    from src.tools.verifier import VERIFIER_SYSTEM_PROMPT

    # Step 7 — Build search subagent middleware stack
    # NOTE: No SkillsMiddleware — search-agent is a pure retrieval worker
    search_middleware = [
        ToolErrorMiddleware(),
        key_rotate_sub,
        TodoListMiddleware(),
    ]
    search_middleware.extend([
        FilesystemMiddleware(backend=backend),
        create_summarization_middleware(model,backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 8 — Build search subagent spec (SubAgent TypedDict, new API)
    search_subagent: SubAgent = {
        "name": "search-agent",
        "description": (
            "Corpus retrieval specialist. Call with 'UID: {uid} | Task: <description>'. "
            "Searches the corpus, writes evidence to scratch/{uid}/evidence.txt and extracted "
            "values to scratch/{uid}/extracted_values.txt. Returns ONLY a completion pointer."
        ),
        "system_prompt": SEARCH_AGENT_SYSTEM_PROMPT,
        "model": model,
        "tools": [route_files, search_in_file],#, extract_table_block],
        "middleware": search_middleware,
    }

    # Step 9 — Build verifier subagent middleware stack
    # NOTE: No SkillsMiddleware — verifier is unchanged per locked decision

    calc_skills_mw = SkillsMiddleware(backend=bash_backend, sources=["/skills/"])

    verifier_middleware = [
        ToolErrorMiddleware(),
        key_rotate_sub,
        TodoListMiddleware(),
        calc_skills_mw,
    ]
    verifier_middleware.extend([
        FilesystemMiddleware(backend=bash_backend),
        create_summarization_middleware(model, bash_backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 10 — Build verifier subagent spec (VER-01: registered with name "verifier")
    verifier_subagent: SubAgent = {
        "name": "verifier",
        "description": (
            "Independent verification specialist. Call with the proposed answer and "
            "evidence summary. Returns PASS with token or FAIL with issues list."
        ),
        "system_prompt": VERIFIER_SYSTEM_PROMPT,
        "model": model,
        "tools": [calculate_for_verifier, pct_change, sum_values, compute_stat],
        "middleware": verifier_middleware,
    }

    # Step 11 — Build calc-agent subagent middleware stack
    # SkillsMiddleware for quant-stats skill
    # _SKILLS_DIR = _PROJECT_ROOT / "agentspace" / "skills"
    # calc_skills_dir = _SKILLS_DIR / "quant-stats"
    # calc_skills_backend = LocalShellBackend(root_dir=_SKILLS_DIR, virtual_mode=True, inherit_env=True)
    #calc_skills_mw = SkillsMiddleware(backend=bash_backend, sources=["/skills/"])

    calc_middleware = [
        ToolErrorMiddleware(),
        key_rotate_sub,
        TodoListMiddleware(),
        calc_skills_mw,
    ]
    calc_middleware.extend([
        FilesystemMiddleware(backend=bash_backend),
        create_summarization_middleware(model, bash_backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 12 — Build calc-agent subagent spec
    calc_subagent: SubAgent = {
        "name": "calc-agent",
        "description": (
            "Arithmetic and statistics specialist. Call with 'UID: {uid} | Task: <description>'. "
            "Performs calculations using calculate, pct_change, sum_values, and compute_stat. "
            "Writes results to scratch/{uid}/calc.txt. Returns ONLY a completion pointer."
        ),
        "system_prompt": CALC_AGENT_SYSTEM_PROMPT,
        "model": model,
        "tools": [calculate, pct_change, sum_values, compute_stat],
        #"skills":["skills/quant-stats"],
        "middleware": calc_middleware,
    }

    # Step 13 — Build external-data-agent subagent middleware stack
    # SkillsMiddleware for cpi-inflation-adjuster + historical-fx skills
    # ext_skills_backend = FilesystemBackend(root_dir=_SKILLS_DIR, virtual_mode=True)
    # ext_skills_mw = SkillsMiddleware(backend=ext_skills_backend, sources=[
    #     "/cpi-inflation-adjuster/",
    #     "/historical-fx/",
    # ])

    ext_middleware = [
        ToolErrorMiddleware(),
        key_rotate_sub,
        TodoListMiddleware(),
        calc_skills_mw,
    ]
    ext_middleware.extend([
        FilesystemMiddleware(backend=bash_backend),
        create_summarization_middleware(model, bash_backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 14 — Build external-data-agent subagent spec
    ext_data_subagent: SubAgent = {
        "name": "external-data-agent",
        "description": (
            "External data specialist for inflation and FX. Call with 'UID: {uid} | Task: <description>'. "
            "Performs CPI adjustments and currency conversions. Writes results to scratch/{uid}/calc.txt. "
            "Returns ONLY a completion pointer."
        ),
        "system_prompt": EXTERNAL_DATA_AGENT_SYSTEM_PROMPT,
        "model": model,
        "tools": [adjust_inflation, get_cpi_value, convert_fx],
        "middleware": ext_middleware,
    }

    # Step 15 — Build orchestrator middleware stack (exact order from graph.py)
    # No SkillsMiddleware on orchestrator — skills are on domain subagents now
    orchestrator_middleware = [
        ToolErrorMiddleware(),
        key_rotate_orch,
        TodoListMiddleware(),
    ]
    orchestrator_middleware.extend([
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            backend=backend,
            subagents=[search_subagent, verifier_subagent, calc_subagent, ext_data_subagent],
        ),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 16 — Combine system prompt (CRITICAL: create_agent() does NOT append BASE_AGENT_PROMPT)
    final_system_prompt = ORCHESTRATOR_SYSTEM_PROMPT

    # Step 17 — Call create_agent() and return
    # Orchestrator tool list: ONLY [normalize_answer]
    # All arithmetic, stats, retrieval, and external data tools are on subagents
    # Wire LangSmith tracer if tracing is enabled
    from langchain_core.tracers.langchain import LangChainTracer
    _callbacks = []
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        _callbacks.append(
            LangChainTracer(project_name=os.environ.get("LANGSMITH_PROJECT", "default"))
        )

    agent = create_agent(
        orch_model,
        tools=[normalize_answer],
        middleware=orchestrator_middleware,
        system_prompt=final_system_prompt,
        checkpointer=MemorySaver(),
        name="Office QA Agent",
    ).with_config(
        {
            "recursion_limit": 10_001,
            "callbacks": _callbacks,
            "metadata": {
                "ls_integration": "deepagents",
                "versions": {"deepagents": __version__},
                "lc_agent_name": "Office QA Agent",
            },
        }
    )
    return agent
