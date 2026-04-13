"""
agent.py — Agent and run_question entry point.

Composes all Phase 1+2 tools into a functioning agent loop with scratch
isolation, planning gate, and native Deep Agent turn management.

Public API:
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
    import os
    # import logging
    from src.scratch import prepare_scratch

    # logging.basicConfig(level=logging.DEBUG)
    # logger = logging.getLogger(__name__)

    # print(f"[DEBUG] run_question called: uid={uid}")
    # print(f"[DEBUG] LANGSMITH_TRACING={os.environ.get('LANGSMITH_TRACING')}")
    # print(f"[DEBUG] LANGCHAIN_TRACING_V2={os.environ.get('LANGCHAIN_TRACING_V2')}")
    # print(f"[DEBUG] LANGSMITH_PROJECT={os.environ.get('LANGSMITH_PROJECT')}")
    # print(f"[DEBUG] LANGSMITH_ENDPOINT={os.environ.get('LANGSMITH_ENDPOINT')}")
    # print(f"[DEBUG] LANGSMITH_API_KEY set={bool(os.environ.get('LANGSMITH_API_KEY'))}")
    # print(f"[DEBUG] MODEL_ID={os.environ.get('MODEL_ID')}")

    # # --- Tracing diagnostics ---
    # try:
    #     from langsmith import Client
    #     ls_client = Client()
    #     print(f"[TRACE] LangSmith client endpoint: {ls_client.api_url}")
    #     print(f"[TRACE] LangSmith client info: {ls_client.info}")
    # except Exception as e:
    #     print(f"[TRACE] LangSmith client FAILED: {e}")

    # # Check if tracer is available
    # try:
    #     from langchain_core.tracers.langchain import LangChainTracer
    #     print(f"[TRACE] LangChainTracer importable: True")
    # except ImportError as e:
    #     print(f"[TRACE] LangChainTracer import FAILED: {e}")

    # # Enable langsmith debug logging
    # logging.getLogger("langsmith").setLevel(logging.DEBUG)
    # logging.getLogger("langchain_core.tracers").setLevel(logging.DEBUG)

    # SCR-01: wipe and recreate scratch directory for this question
    # print(f"[DEBUG] Preparing scratch for {uid}...")
    prepare_scratch(uid)
    # print(f"[DEBUG] Scratch ready.")

    # Create a fresh agent — fresh MemorySaver per question
    # (Pitfall 1: MemorySaver does NOT reset on scratch dir wipe; must create new instance)
    # print(f"[DEBUG] Creating harness agent...")
    agent = harness.create_harness_agent()
    # print(f"[DEBUG] Harness agent created successfully. Type: {type(agent).__name__}")

    # Prepend UID preamble so the agent knows which scratch subdirectory to write to
    user_message = (
        f"Question UID: {uid}\n"
        f"Scratch directory: scratch/{uid}/\n\n"
        f"Question: {question}"
    )

    # # Explicitly wire LangSmith tracer as callback
    # from langchain_core.tracers.langchain import LangChainTracer
    # tracer = LangChainTracer(project_name=os.environ.get("LANGSMITH_PROJECT", "default"))
    # invoke_config = {
    #     "configurable": {"thread_id": uid},
    #     "callbacks": [tracer],
    # }
    # print(f"[TRACE] Invoke config: {invoke_config}")
    # print(f"[TRACE] Agent type: {type(agent)}")
    # print(f"[TRACE] Agent config_specs: {getattr(agent, 'config_specs', 'N/A')}")

    # print(f"[DEBUG] Invoking agent...")
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
        f"Scratch directory: scratch/{uid}/\n\n"
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
