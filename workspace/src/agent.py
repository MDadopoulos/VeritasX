"""
agent.py — Agent system prompt and run_question entry point.

Composes all Phase 1+2 tools into a functioning agent loop with scratch
isolation, planning gate, and native Deep Agent turn management.

Public API:
    SYSTEM_PROMPT                           str   — Orchestrator system prompt (trimmed; retrieval
                                                    rules moved to search subagent in harness.py)
    run_question(uid, question)             str   — Orchestrates per-question lifecycle
    run_question_with_messages(uid, question) dict — Returns answer + full message list
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from typing import Any

load_dotenv(Path(__file__).parent.parent / ".env")

from src import harness  # noqa: E402 (after load_dotenv so env vars are set first)


def _extract_text(content: Any) -> str:
    """Extract plain text from a message content that may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = """\
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
# Question entry point
# ---------------------------------------------------------------------------


def run_question(uid: str, question: str) -> str:
    """
    Orchestrate the per-question lifecycle: wipe scratch, create agent, invoke.

    Per-question lifecycle (SCR-01, AGT-02):
    1. prepare_scratch(uid) — wipe and recreate ./scratch/{uid}/ for fresh state
    2. create_agent() — fresh CompiledGraph with fresh MemorySaver so no state
       bleeds between questions
    3. Invoke agent with UID-prefixed user message so the agent knows its scratch path
    4. Return final answer string from last message

    Args:
        uid:      Non-empty string identifying this question run (used as scratch key
                  and thread_id for the MemorySaver checkpointer).
        question: The user's question string.

    Returns:
        Final answer string from the agent's last message.
    """
    from src.scratch import prepare_scratch

    # SCR-01: wipe and recreate scratch directory for this question
    prepare_scratch(uid)

    # Create a fresh agent — fresh MemorySaver per question
    # (Pitfall 1: MemorySaver does NOT reset on scratch dir wipe; must create new instance)
    agent = harness.create_harness_agent()

    # Prepend UID preamble so the agent knows which scratch subdirectory to write to
    user_message = (
        f"Question UID: {uid}\n"
        f"Scratch directory: {uid}/\n\n"
        f"Question: {question}"
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": {"thread_id": uid}},
    )

    return _extract_text(result["messages"][-1].content)


def run_question_with_messages(uid: str, question: str) -> dict:
    """
    Orchestrate the per-question lifecycle and return both answer and full message list.

    Identical lifecycle to run_question but returns a dict with both the final
    answer string and the complete messages list for automated ordering assertions.

    Returns:
        {
            "answer": str,           # final answer string from last message
            "messages": list,        # full message list from agent result
        }
    """
    from src.scratch import prepare_scratch

    prepare_scratch(uid)
    agent = harness.create_harness_agent()

    user_message = (
        f"Question UID: {uid}\n"
        f"Scratch directory: {uid}/\n\n"
        f"Question: {question}"
    )

    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": {"thread_id": uid}},
    )

    return {
        "answer": _extract_text(result["messages"][-1].content),
        "messages": result["messages"],
    }
