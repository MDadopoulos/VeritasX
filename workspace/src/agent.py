"""
agent.py — Agent factory, system prompt, and run_question entry point.

Composes all Phase 1+2 tools into a functioning agent loop with scratch
isolation, planning gate, retrieval call limiting, and exhaustion handling.

Public API:
    SYSTEM_PROMPT       str             — System prompt enforcing agent behavior
    RETRIEVAL_LIMIT     int             — Max retrieval tool calls per question (20)
    create_agent(config=None)           — Returns a fresh compiled CompiledGraph
    run_question(uid, question, config) — Orchestrates per-question lifecycle
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RETRIEVAL_LIMIT: int = 20  # per context decision — 20 calls per run, per tool

SYSTEM_PROMPT: str = """\
## Mandatory Planning Gate

Before calling ANY retrieval tool (route_files, search_in_file), you MUST first \
call write_todos with at minimum:
1. A restatement of the question as you understand it.
2. Your planned tool call sequence in order.

You may update the todo list mid-run as new evidence changes the plan.
Mark items as completed (status: "completed") as you finish each step.

## Scratch File Writing Instructions

After EACH search_in_file result, APPEND to {uid}/evidence.txt:
  Format:
    Source: {file_path}
    {span_text}
    Note: {why this span was selected}
    ---

After EACH extract_table_block result, APPEND to {uid}/tables.txt:
  Format: the raw table block as returned by the tool, followed by
    ---

After extracting numeric values from evidence/tables, WRITE to {uid}/extracted_values.txt:
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

After completing all calculation, WRITE to {uid}/verification.txt:
  Content: verification: pending (Phase 4)

After calling normalize_answer, WRITE to {uid}/answer.txt:
  Line 1: the normalized answer string
  Line 2: a one-sentence rationale
  Example:
    19.14%
    pct_change from 2602 to 3100 over FY1940

## Tool Usage Rules

- NEVER compute percent change with inline arithmetic. ALWAYS use the pct_change tool.
- NEVER generate arithmetic formulas inline. ALWAYS use calculate() for all arithmetic.
- When route_files or search_in_file returns RETRIEVAL_EXHAUSTED, STOP calling that tool.
  Attempt to answer from evidence gathered so far.
  If evidence is insufficient, respond with EXACTLY:
  "I cannot determine the answer from the available corpus."
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_agent(config: "Config | None" = None):
    """
    Create and return a fresh compiled agent with all 7 tools registered.

    Creates fresh counter-wrapped retrieval tools so each agent instance has
    its own independent call counter starting at 0. Call this once per question
    (not once per module) to guarantee AGT-02 idempotency.

    Args:
        config: Optional Config instance. If None, get_config() is called
                when the model is instantiated.

    Returns:
        A compiled LangGraph agent (CompiledGraph) ready for .invoke().
    """
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langgraph.checkpoint.memory import MemorySaver

    from src.model_adapter import get_model
    from src.tools.retrieval_wrappers import (
        make_counted_route_files,
        make_counted_search_in_file,
    )
    from src.tools.extract_table_block import extract_table_block
    from src.tools.calculate import calculate, pct_change, sum_values
    from src.tools.normalize_answer import normalize_answer

    model = get_model(config)

    # Fresh counter-wrappers per agent — this ensures per-question call limits
    counted_rf = make_counted_route_files(RETRIEVAL_LIMIT)
    counted_sif = make_counted_search_in_file(RETRIEVAL_LIMIT)

    agent = create_deep_agent(
        model=model,
        tools=[
            counted_rf,
            counted_sif,
            extract_table_block,
            calculate,
            pct_change,
            sum_values,
            normalize_answer,
        ],
        system_prompt=SYSTEM_PROMPT,
        # No ToolCallLimitMiddleware — counter-wrappers handle limiting directly
        backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
        checkpointer=MemorySaver(),
    )

    return agent


# ---------------------------------------------------------------------------
# Question entry point
# ---------------------------------------------------------------------------


def run_question(uid: str, question: str, config: "Config | None" = None) -> str:
    """
    Orchestrate the per-question lifecycle: wipe scratch, create agent, invoke.

    Per-question lifecycle (SCR-01, AGT-02):
    1. prepare_scratch(uid) — wipe and recreate ./scratch/{uid}/ for fresh state
    2. create_agent(config) — fresh CompiledGraph with fresh MemorySaver and
       fresh counter-wrappers so no state bleeds between questions
    3. Invoke agent with UID-prefixed user message so the agent knows its scratch path
    4. Return final answer string from last message

    Args:
        uid:      Non-empty string identifying this question run (used as scratch key
                  and thread_id for the MemorySaver checkpointer).
        question: The user's question string.
        config:   Optional Config instance.

    Returns:
        Final answer string from the agent's last message.
    """
    from src.scratch import prepare_scratch

    # SCR-01: wipe and recreate scratch directory for this question
    prepare_scratch(uid)

    # Create a fresh agent — fresh MemorySaver + fresh counter-wrappers per question
    # (Pitfall 1: MemorySaver does NOT reset on scratch dir wipe; must create new instance)
    agent = create_agent(config)

    # Prepend UID preamble so the agent knows which scratch subdirectory to write to
    # (per research recommendation Open Question 2)
    user_message = (
        f"Question UID: {uid}\n"
        f"Scratch directory: {uid}/\n\n"
        f"Question: {question}"
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": {"thread_id": uid}},
    )

    return result["messages"][-1].content
