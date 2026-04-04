"""
harness.py — Custom middleware assembly harness for the DeepAgents orchestrator.

Replaces the opaque create_deep_agent() call with a purpose-built middleware stack
that isolates corpus retrieval inside a dedicated search subagent, keeping raw BM25
span text out of the orchestrator's context window. The verifier subagent is also
registered here (VER-01).

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
_DEFAULT_SCRATCH = _PROJECT_ROOT / "agentspace" / "scratch"
SCRATCH_DIR = Path(os.environ.get("SCRATCH_DIR", str(_DEFAULT_SCRATCH)))

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
## Mandatory Planning Gate

Before calling ANY tool, you MUST first call write_todos with at minimum:
1. A restatement of the question as you understand it.
2. Your planned tool call sequence in order.

You may update the todo list mid-run as new evidence changes the plan.
Mark items as completed (status: "completed") as you finish each step.

## Retrieval via Search Agent

To retrieve financial data from the corpus, call the search agent with the UID prefix:
  task(subagent_type='search-agent', description='UID: {uid} | Task: <plain English task>')

Example: task(subagent_type='search-agent',
              description='UID: UID0001 | Task: Find defense expenditures for FY1940 across all relevant files')

IMPORTANT: Every search-agent call MUST include 'UID: {uid} |' at the start of the description.
The {uid} value comes from the question preamble ("Question UID: ...").

The search agent writes evidence to {uid}/evidence.txt and extracted values to {uid}/extracted_values.txt.
It returns ONLY a file pointer — do NOT expect inline data.

Do NOT call route_files, search_in_file, or extract_table_block directly.

## Scratch File Writing Instructions

After the search-agent completes, read {uid}/extracted_values.txt to get the values for calculation.
EVERY numeric value MUST include its unit. If unit is unclear, write (unit unknown).

After EACH calculate/pct_change/sum_values result, APPEND to {uid}/calc.txt:
  Format: expression, labeled inputs with source file, result
  Example:
    pct_change(2602, 3100)
    Inputs: defense_1940=2602 (millions) [source: treasury_bulletin_1940_03.txt],
            defense_1941=3100 (millions) [source: treasury_bulletin_1941_03.txt]
    Result: 19.14%

After completing all calculations, call normalize_answer with your final answer string.

After calling normalize_answer, WRITE to {uid}/answer.txt:
  Line 1: the normalized answer string
  Line 2: a one-sentence rationale
  Example:
    19.14%
    pct_change from 2602 to 3100 over FY1940

## Tool Usage Rules

- NEVER compute percent change with inline arithmetic. ALWAYS use the pct_change tool.
- NEVER generate arithmetic formulas inline. ALWAYS use calculate() for all arithmetic.

## Verification

Before calling normalize_answer, call the verifier with the UID prefix:
  task(subagent_type='verifier', description='UID: {uid} | <answer> | Evidence: <summary>')

Only call normalize_answer after receiving a PASS from the verifier.
"""


# ---------------------------------------------------------------------------
# Search subagent system prompt
# ---------------------------------------------------------------------------

SEARCH_AGENT_SYSTEM_PROMPT: str = """\
## UID Extraction (MANDATORY)
The task description begins with 'UID: <uid> | Task: ...'.
Extract the UID from this prefix. ALL scratch file paths use this UID:
  {uid}/evidence.txt, {uid}/tables.txt, {uid}/extracted_values.txt

## Your Role
You are a corpus retrieval specialist. Given a natural language task, you search
the US Treasury bulletin corpus, extract relevant numeric values, and write
all evidence and extracted values to UID scratch files.

## Fiscal Year Adjacency Rule (MANDATORY)
US Treasury bulletins are published monthly. FY data is often summarized
retrospectively in bulletins from the FOLLOWING calendar year.

Rule: For any question about FY N data:
1. Call route_files with the original question (routes to year N bulletins).
2. ALSO call route_files with "fiscal year {N+1}" to get year N+1 bulletins.
3. Search BOTH sets of files before concluding data is absent.

Example: FY1940 data may appear in the 1940-10 through 1941-09 bulletins,
not just the 1939-10 through 1940-09 bulletins.

## Parallel Search Rule
When route_files returns 2 or more file paths, call search_in_file for
ALL relevant files in a SINGLE turn (parallel tool calls). Do not search
files one at a time — issue all search_in_file calls simultaneously.

## Evidence Recording (MANDATORY)
After EACH search_in_file call, WRITE (append) to {uid}/evidence.txt:
  Source: {file_path}
  {span_text}
  Note: {why this span was selected}
  ---

After EACH extract_table_block call, WRITE (append) to {uid}/tables.txt:
  Source: {file_path}
  {table_block}
  ---

After ALL searches and extractions complete, write to {uid}/extracted_values.txt:
  Format: one line per value: variable_name = value (unit), source: filename
  Example: defense_1940 = 2602 (millions), source: treasury_bulletin_1940_03.txt

## Return Format
Return ONLY a completion pointer. Do NOT include raw data or numeric values:
  "Evidence written to {uid}/evidence.txt. Extracted values written to {uid}/extracted_values.txt."

NEVER relay raw corpus text, table blocks, or numeric values inline back to the orchestrator.
The orchestrator will read files directly — do not summarize or repeat file contents.

If no relevant data is found, return: NO_DATA_FOUND: {explanation}
"""


# ---------------------------------------------------------------------------
# Harness factory
# ---------------------------------------------------------------------------


def create_harness_agent():
    """
    Build and return a fresh compiled agent using the custom middleware stack.

    Assembles the DeepAgents middleware manually (instead of using create_deep_agent)
    to achieve explicit tool isolation: retrieval tools are confined to the
    search subagent; the orchestrator sees only calculation/normalization tools.

    Returns:
        A compiled LangGraph agent (CompiledStateGraph) ready for .invoke().
    """
    from langchain.agents import create_agent
    from langchain.agents.middleware import TodoListMiddleware
    from deepagents.middleware.filesystem import FilesystemMiddleware
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

    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    backend = LocalShellBackend(
        root_dir=SCRATCH_DIR,
        virtual_mode=True,
        inherit_env=True,
    )

    # Step 1b — Skills backend and middleware (orchestrator only)
    _SKILLS_DIR = Path(os.environ.get("SKILLS_DIR", str(_PROJECT_ROOT / "skills")))
    skills_backend = FilesystemBackend(root_dir=_SKILLS_DIR, virtual_mode=True)
    skills_mw = SkillsMiddleware(
        backend=skills_backend,
        sources=["/quant-stats/", "/cpi-inflation-adjuster/", "/historical-fx/"],
    )

    # Step 2 — Import retrieval tools (search subagent only)
    from src.tools.route_files import route_files
    from src.tools.search_in_file import search_in_file
    from src.tools.extract_table_block import extract_table_block

    # Step 3 — Import orchestrator tools
    from src.tools.calculate import calculate, pct_change, sum_values
    from src.tools.normalize_answer import normalize_answer

    # Step 4 — Import verifier tool
    from src.tools.calculate import calculate as calculate_for_verifier
    from src.tools.verifier import VERIFIER_SYSTEM_PROMPT

    # Step 5 — Build search subagent middleware stack (exact order from graph.py)
    # NOTE: No SkillsMiddleware — search-agent is a pure retrieval worker
    search_middleware = [
        TodoListMiddleware(),
    ]
    search_middleware.extend([
        FilesystemMiddleware(backend=backend),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 6 — Build search subagent spec (SubAgent TypedDict, new API)
    search_subagent: SubAgent = {
        "name": "search-agent",
        "description": (
            "Corpus retrieval specialist. Call with 'UID: {uid} | Task: <description>'. "
            "Searches the corpus, writes evidence to {uid}/evidence.txt and extracted "
            "values to {uid}/extracted_values.txt. Returns ONLY a completion pointer."
        ),
        "system_prompt": SEARCH_AGENT_SYSTEM_PROMPT,
        "model": model,
        "tools": [route_files, search_in_file, extract_table_block],
        "middleware": search_middleware,
    }

    # Step 7 — Build verifier subagent middleware stack (exact order from graph.py)
    # NOTE: No SkillsMiddleware — verifier is unchanged per locked decision
    verifier_middleware = [
        TodoListMiddleware(),
    ]
    verifier_middleware.extend([
        FilesystemMiddleware(backend=backend),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    # Step 8 — Build verifier subagent spec (VER-01: registered with name "verifier")
    verifier_subagent: SubAgent = {
        "name": "verifier",
        "description": (
            "Independent verification specialist. Call with the proposed answer and "
            "evidence summary. Returns PASS with token or FAIL with issues list."
        ),
        "system_prompt": VERIFIER_SYSTEM_PROMPT,
        "model": model,
        "tools": [calculate_for_verifier],
        "middleware": verifier_middleware,
    }

    ###CAN ADD GENERAL SUBAGENT AS WELL..abs

    # Step 9 — Build orchestrator middleware stack (exact order from graph.py)
    # Skills on orchestrator ONLY (Claudie principle: orchestrator reasons, workers execute)
    orchestrator_middleware = [
        TodoListMiddleware(),
        skills_mw,
    ]
    orchestrator_middleware.extend([
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            backend=backend,
            subagents=[search_subagent, verifier_subagent],
        ),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ])

    ###if want to add the rest later..
    ##if middleware:
    ##    deepagent_middleware.extend(middleware)
    #  if memory is not None:
    #     deepagent_middleware.append(MemoryMiddleware(backend=backend, sources=memory))
    # if interrupt_on is not None:
    #     deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

    # Step 10 — Combine system prompt (CRITICAL: create_agent() does NOT append BASE_AGENT_PROMPT)
    final_system_prompt = ORCHESTRATOR_SYSTEM_PROMPT + "\n\n" + BASE_AGENT_PROMPT

    # Step 11 — Call create_agent() and return
    # Orchestrator tool list: ONLY [calculate, pct_change, sum_values, normalize_answer]
    # route_files, search_in_file, extract_table_block are on the search subagent only
    agent = create_agent(
        model,
        tools=[calculate, pct_change, sum_values, normalize_answer],
        middleware=orchestrator_middleware,
        system_prompt=final_system_prompt,
        checkpointer=MemorySaver(),
        name="Office QA Agent",
    ).with_config(
        {
            "recursion_limit": 10_001,
            "metadata": {
                "ls_integration": "deepagents",
                "versions": {"deepagents": __version__},
                "lc_agent_name": "Office QA Agent",
            },
        }
    )
    return agent
