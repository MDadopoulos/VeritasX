"""
agent.py — Agent factory, system prompt, and run_question entry point.

Composes all Phase 1+2 tools into a functioning agent loop with scratch
isolation, planning gate, and native Deep Agent turn management.

Public API:
    SYSTEM_PROMPT                           str   — System prompt enforcing agent behavior
    create_agent()                                — Returns a fresh compiled CompiledGraph
    run_question(uid, question)             str   — Orchestrates per-question lifecycle
    run_question_with_messages(uid, question) dict — Returns answer + full message list
"""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
from typing import Any

load_dotenv(Path(__file__).parent.parent / ".env")


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

After completing all calculation, proceed to the Verification and Retry Protocol section below.
verification.txt is managed by the verification protocol — do not write to it manually.

After calling normalize_answer, WRITE to {uid}/answer.txt:
  Line 1: the normalized answer string
  Line 2: a one-sentence rationale
  Example:
    19.14%
    pct_change from 2602 to 3100 over FY1940

## Tool Usage Rules

- NEVER compute percent change with inline arithmetic. ALWAYS use the pct_change tool.
- NEVER generate arithmetic formulas inline. ALWAYS use calculate() for all arithmetic.

## Verification and Retry Protocol

Before calling normalize_answer, you MUST call the verifier subagent:
  task(subagent_type="verifier", description="Verify answer for UID <uid>. Proposed answer: '<answer>'. Scratch directory: <uid>/. Check evidence coverage, unit consistency, arithmetic, and format. Return JSON with status, issues, token.")

The verifier returns a JSON object with status, issues, and token.

On PASS:
  - Use the returned token as the verification_token argument to normalize_answer.
  - Append the PASS result to verification.txt using the read-then-write pattern:
    1. read_file("{uid}/verification.txt") to get current content (may be empty)
    2. Concatenate: old_content + new attempt record
    3. write_file("{uid}/verification.txt", combined_content)
  - Format: "Attempt N: Status: PASS | Checks: evidence: PASS, arithmetic: PASS, units: PASS, format: PASS | Token: <token>\\n---\\n"

On FAIL:
  - Read the issues list to understand what failed.
  - Perform targeted re-retrieval based on issues (e.g., unit FAIL -> re-retrieve the table with unit annotation; arithmetic FAIL -> re-check calc.txt expression).
  - Append the FAIL result to verification.txt using the same read-then-write pattern.
  - Retry the full answer derivation and call the verifier again.
  - You have 3 total attempts (1 original + 2 retries).

On ERROR (verifier crashed/timed out):
  - Count this as a failed attempt. Same retry logic as FAIL.
  - Append the ERROR result to verification.txt.

After 3 failed attempts:
  - Respond with EXACTLY: "cannot determine: [last verifier issues list]"
  - The "cannot determine" response includes the last FAIL issues so callers can see why.
  - Do NOT call normalize_answer with an unverified answer.
  - Do NOT call the verifier again.

Count attempts by the number of verification attempt records in verification.txt.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_agent():
    """
    Create and return a fresh compiled agent with all 7 tools registered.

    Call this once per question (not once per module) to guarantee AGT-02
    idempotency — each call creates a fresh MemorySaver checkpointer so no
    state bleeds between questions.

    Returns:
        A compiled LangGraph agent (CompiledGraph) ready for .invoke().
    """
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langgraph.checkpoint.memory import MemorySaver

    from src.model_adapter import get_model
    from src.tools.route_files import route_files
    from src.tools.search_in_file import search_in_file
    from src.tools.extract_table_block import extract_table_block
    from src.tools.calculate import calculate, pct_change, sum_values
    from src.tools.normalize_answer import normalize_answer
    from src.tools.verifier import VERIFIER_SUBAGENT_SPEC

    model = get_model()

    agent = create_deep_agent(
        model=model,
        tools=[
            route_files,
            search_in_file,
            #extract_table_block,
            calculate,
            pct_change,
            sum_values,
            normalize_answer,
        ],
        subagents=[VERIFIER_SUBAGENT_SPEC],
        system_prompt=SYSTEM_PROMPT,
        backend=FilesystemBackend(root_dir=str(Path(__file__).parent.parent / "scratch"), virtual_mode=False),
        checkpointer=MemorySaver(),
    )

    return agent


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
    agent = create_agent()

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
    agent = create_agent()

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
