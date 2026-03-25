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

from pathlib import Path

# ---------------------------------------------------------------------------
# Orchestrator system prompt (source of truth for harness)
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM_PROMPT: str = """\
## Mandatory Planning Gate

Before calling ANY tool, you MUST first call write_todos with at minimum:
1. A restatement of the question as you understand it.
2. Your planned tool call sequence in order.

You may update the todo list mid-run as new evidence changes the plan.
Mark items as completed (status: "completed") as you finish each step.

## Retrieval via Search Agent

To retrieve financial data from the corpus, call the search agent:
  task(subagent_type='search-agent', description='<plain English task>')

Example: task(subagent_type='search-agent',
              description='Find defense expenditures for FY1940 across all relevant files')

The search agent handles fiscal year adjacency and parallel file searching automatically.
It returns compact findings:
  variable_name = value (unit), source: filename

Do NOT call route_files, search_in_file, or extract_table_block directly.

## Scratch File Writing Instructions

After receiving compact findings from the search agent, WRITE to {uid}/extracted_values.txt:
  Format: one line per value: variable_name = value (unit)
  Example: defense_1940 = 2602 (millions)
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

Before calling normalize_answer, call the verifier:
  task(subagent_type='verifier', description='<answer> | Evidence: <summary>')

Only call normalize_answer after receiving a PASS from the verifier.
"""


# ---------------------------------------------------------------------------
# Search subagent system prompt
# ---------------------------------------------------------------------------

SEARCH_AGENT_SYSTEM_PROMPT: str = """\
## Your Role
You are a corpus retrieval specialist. Given a natural language task, you search
the US Treasury bulletin corpus, extract relevant numeric values, and return a
compact findings summary to the orchestrator.

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

## Evidence Recording
After each search_in_file result, APPEND to the scratch evidence.txt:
  Source: {file_path}
  {span_text}
  Note: {why this span was selected}
  ---

## Return Format
Return ONLY a compact findings summary. Do not return raw corpus text.
Format each finding as one line:
  variable_name = value (unit), source: filename

Example:
  defense_1940 = 2602 (millions), source: treasury_bulletin_1940_03.txt
  defense_1941 = 3100 (millions), source: treasury_bulletin_1941_06.txt

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
    from deepagents.middleware.subagents import SubAgentMiddleware, SubAgent
    from deepagents.middleware.summarization import create_summarization_middleware
    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
    from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware
    from deepagents.graph import BASE_AGENT_PROMPT
    from deepagents.backends import FilesystemBackend
    from langgraph.checkpoint.memory import MemorySaver

    from src.model_adapter import get_model

    # Step 1 — Model and backend
    model = get_model()
    backend = FilesystemBackend(
        root_dir=str((Path(__file__).parent.parent / "scratch").resolve()),
        virtual_mode=False,
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
    search_middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ]

    # Step 6 — Build search subagent spec (SubAgent TypedDict, new API)
    search_subagent: SubAgent = {
        "name": "search-agent",
        "description": (
            "Corpus retrieval specialist. Call with a natural language task describing "
            "what financial data to find (e.g., 'Find defense expenditures for FY1940 "
            "across all relevant files'). Returns compact findings: "
            "variable_name = value (unit), source: file"
        ),
        "system_prompt": SEARCH_AGENT_SYSTEM_PROMPT,
        "model": model,
        "tools": [route_files, search_in_file, extract_table_block],
        "middleware": search_middleware,
    }

    # Step 7 — Build verifier subagent middleware stack (exact order from graph.py)
    verifier_middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ]

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

    # Step 9 — Build orchestrator middleware stack (exact order from graph.py)
    orchestrator_middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            backend=backend,
            subagents=[search_subagent, verifier_subagent],
        ),
        create_summarization_middleware(model, backend),
        PatchToolCallsMiddleware(),
        AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore"),
    ]

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
    )
    return agent
