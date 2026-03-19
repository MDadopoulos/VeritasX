# Phase 3: Agent Loop + Scratch Space - Research

**Researched:** 2026-03-19
**Domain:** Deep Agents (langchain-ai/deepagents), LangChain 1.x middleware, LangGraph MemorySaver
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Scratch file content
- **evidence.txt** — Annotated spans: raw retrieved span text + source file path + one-line agent note on why this span was selected
- **tables.txt** — Raw extracted table block only (what `extract_table_block` returned, unparsed)
- **extracted_values.txt** — Every numeric value includes its unit alongside the value (e.g., `defense_1940 = 2602 (millions)`) — already required by success criterion
- **calc.txt** — Claude's discretion: format that makes downstream verification straightforward (expression, result, labeled inputs with source)
- **answer.txt** — Normalized answer on first line, followed by a one-sentence rationale (e.g., `pct_change from 2602 to 3100 over FY1940`)

#### Write-todos protocol
- Agent must write a todo list containing at minimum: (1) restatement of the question as understood, (2) planned tool call sequence in order — before any retrieval tool is called
- Agent **may** update the todo list mid-run as new evidence changes the plan
- Agent **checks off** completed items as it progresses — progress is visible in trace and scratch files
- Enforcement of the pre-retrieval gate: Claude's discretion (balance hard blocking vs. trace debuggability)

#### Exhaustion + failure behavior
- Call limit applies to **retrieval tools only** (`route_files`, `search_in_file`) — `calculate` and `extract_table_block` are uncapped
- Per-question retrieval call limit: **20 calls** (raised from roadmap's original 4)
- When limit is hit: agent attempts a best-effort answer using evidence gathered so far
- If agent judges the evidence insufficient to answer: emit exactly `"I cannot determine the answer from the available corpus."`
- Sufficiency judgment: agent decides based on what it has found (no hard rule)

### Claude's Discretion
- `calc.txt` exact format (expression layout, labeling style)
- Enforcement mechanism for the pre-retrieval `write_todos` gate
- `max_iterations` and `MemorySaver` checkpointer configuration details
- Scratch directory layout within `./scratch/{uid}/`

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

Phase 3 wires the Phase 1+2 tools into a `create_deep_agent` call from the `deepagents` (v0.4.11) package. The package is published on PyPI and installable via `pip install deepagents`. It wraps LangChain 1.2.x's `create_agent` factory (itself LangGraph-backed) and automatically stacks `TodoListMiddleware`, `FilesystemMiddleware`, and `SubAgentMiddleware` on the compiled agent. The `FilesystemBackend(root_dir="./scratch", virtual_mode=False)` constructor provides real on-disk file operations rooted at `./scratch`.

The call-count loop guard is implemented via `ToolCallLimitMiddleware` from `langchain.agents.middleware`, passed as a custom middleware item to `create_deep_agent`. This middleware accepts a `tool_name` to target only the retrieval tools, a `run_limit` of 20, and an `exit_behavior` of `"continue"` so the agent can attempt a best-effort answer rather than hard-stopping. The `TodoListMiddleware` is included automatically by `create_deep_agent` — the pre-retrieval gate is enforced through the system prompt and the tool description.

The scratch directory isolation uses `FilesystemBackend` with `root_dir` pointing to the UID-keyed subdirectory, OR the agent uses the backend's write tools with `./scratch/{uid}/` paths — both patterns work with `virtual_mode=False`. The `MemorySaver` checkpointer keyed by `thread_id=uid` provides within-question state continuity; re-running the same UID creates fresh state if the scratch directory is wiped before invocation.

**Primary recommendation:** Install `deepagents==0.4.11` plus `langchain==1.2.12` and `langgraph>=1.1.1,<1.2.0` (deepagents' locked transitive dependency). Use `ToolCallLimitMiddleware` with `tool_name` applied separately to `"route_files"` and `"search_in_file"` to respect the 20-call combined limit.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| deepagents | 0.4.11 (latest) | `create_deep_agent`, `FilesystemMiddleware`, `SubAgentMiddleware` | Locked by project decisions — provides all three middleware automatically |
| langchain | 1.2.12 | `create_agent`, `TodoListMiddleware`, `ToolCallLimitMiddleware` | deepagents hard-requires `langchain>=1.2.11,<2.0.0` |
| langgraph | >=1.1.1,<1.2.0 | State graph, `MemorySaver`, thread checkpointing | Transitive dependency of langchain 1.2.x |
| langchain-core | >=1.2.18 | Base types, `SystemMessage`, `BaseTool` | Required by all langchain packages |
| langchain-google-genai | 4.2.1 | Already installed — model bridge for Gemini/Claude via Vertex AI | Pre-existing in project |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langgraph.checkpoint.memory | (part of langgraph) | `MemorySaver` — in-memory checkpointer | Thread state within a single question run |
| langchain.agents.middleware | (part of langchain 1.2.12) | `TodoListMiddleware`, `ToolCallLimitMiddleware` | Loop guard and planning gate |
| deepagents.backends | (part of deepagents) | `FilesystemBackend` | Real on-disk scratch files |

### Installation

```bash
# From workspace directory, using uv (project uses uv per Phase 2 UAT notes):
uv add deepagents==0.4.11

# Or pip into project venv:
pip install deepagents==0.4.11
# This pulls: langchain==1.2.12, langchain-anthropic>=1.3.4, langgraph>=1.1.1,<1.2.0, wcmatch
```

**Note:** `deepagents` also installs `langchain-anthropic` — this is harmless since the project uses `langchain-google-vertexai` for the actual model calls via `model_adapter.py`. The `deepagents` default model is Claude Sonnet but the project overrides this by passing an initialized model instance.

---

## Architecture Patterns

### Recommended Project Structure

```
workspace/src/
├── agent.py             # create_deep_agent wiring — create_deep_agent(), SYSTEM_PROMPT
├── scratch.py           # scratch lifecycle helpers — ensure_fresh_uid_dir(), write_scratch_file()
├── tools/               # Phase 1+2 tools (existing)
│   ├── route_files.py
│   ├── search_in_file.py
│   ├── extract_table_block.py
│   ├── calculate.py
│   └── normalize_answer.py
└── config.py            # existing
workspace/scratch/       # created at runtime — one subdir per question UID
└── {uid}/
    ├── evidence.txt
    ├── tables.txt
    ├── extracted_values.txt
    ├── calc.txt
    ├── verification.txt   # written by Phase 4 verifier; stub for Phase 3
    └── answer.txt
```

### Pattern 1: create_deep_agent Wiring

**What:** Construct the agent with `FilesystemBackend` pointing at `./scratch`, custom middleware including `ToolCallLimitMiddleware`, a `MemorySaver` checkpointer, and all Phase 1+2 tools.

**When to use:** Once at module import time (or once per HTTP request in Phase 5). The compiled agent is stateless between invocations if you use `MemorySaver`.

```python
# Source: deepagents 0.4.11 graph.py + langchain 1.2.12 middleware __init__.py
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import ToolCallLimitMiddleware
from langgraph.checkpoint.memory import MemorySaver

from src.tools.route_files import route_files
from src.tools.search_in_file import search_in_file
from src.tools.extract_table_block import extract_table_block
from src.tools.calculate import calculate, pct_change, sum_values
from src.tools.normalize_answer import normalize_answer

RETRIEVAL_LIMIT = 20  # per context decision — 20 calls per run

agent = create_deep_agent(
    model=get_model(),                        # returns ChatAnthropicVertex or ChatGoogleGenerativeAI
    tools=[
        route_files,
        search_in_file,
        extract_table_block,
        calculate,
        pct_change,
        sum_values,
        normalize_answer,
    ],
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        # Two separate limiters for the two retrieval tools; both count against run_limit=20
        ToolCallLimitMiddleware(
            tool_name="route_files",
            run_limit=RETRIEVAL_LIMIT,
            exit_behavior="continue",         # agent gets error message, not hard stop
        ),
        ToolCallLimitMiddleware(
            tool_name="search_in_file",
            run_limit=RETRIEVAL_LIMIT,
            exit_behavior="continue",
        ),
    ],
    backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
    checkpointer=MemorySaver(),
)
```

**Critical:** `middleware` in `create_deep_agent` is **appended after** the built-in middleware stack (`TodoListMiddleware`, `FilesystemMiddleware`, `SubAgentMiddleware`). The built-in stack runs first. Custom `ToolCallLimitMiddleware` instances are added at the end.

### Pattern 2: MemorySaver + Fresh Thread Per Question

**What:** Use `thread_id=uid` in the invoke config. For a fresh start on a re-run, wipe the scratch directory AND use a unique config key — `MemorySaver` stores state in RAM keyed by `thread_id`. Re-using the same `thread_id` without clearing state means the agent sees prior conversation history.

**When to use:** Every question invocation. Re-running the same UID should produce a fresh start.

```python
# Source: langgraph MemorySaver docs + deepagents graph.py with_config usage
from langgraph.checkpoint.memory import MemorySaver

# Re-run isolation: wipe scratch dir, then invoke with same thread_id
import shutil
from pathlib import Path

def run_question(uid: str, question: str) -> str:
    # SCR-01: assert/recreate fresh scratch dir
    scratch_dir = Path("./scratch") / uid
    if scratch_dir.exists():
        shutil.rmtree(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    # MemorySaver: using the same thread_id after rmtree means no old checkpoint exists
    # The checkpointer will start fresh because there is no persisted state for this thread_id
    # IF you want to guarantee isolation, also clear the MemorySaver internal state:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": uid}},
    )
    return result["messages"][-1].content
```

**Pitfall:** `MemorySaver` is in-RAM. Wiping the scratch directory does NOT wipe the MemorySaver checkpoint. For true re-run isolation, either create a new `MemorySaver()` per invocation, or use a `thread_id` that encodes the run (e.g., `f"{uid}_run_{int(time.time())}`). The simplest approach: create a new `MemorySaver()` per question run if idempotency is required.

### Pattern 3: ToolCallLimitMiddleware — Retrieval Exhaustion

**What:** When `exit_behavior="continue"`, the middleware injects an error `ToolMessage` with content `"Tool call limit exceeded. Do not call '{tool_name}' again."` The agent receives this as a tool response and is expected to stop calling that tool and work with existing evidence.

**The `RETRIEVAL_EXHAUSTED` signal in requirements:** The requirements say the tool returns `RETRIEVAL_EXHAUSTED`. The `ToolCallLimitMiddleware` with `exit_behavior="continue"` injects that error message automatically — but as a `ToolMessage`, not as a tool return value. The wording is slightly different from `RETRIEVAL_EXHAUSTED`. Two implementation options:

1. **Wrap `route_files`/`search_in_file` in a counter wrapper** that returns `{"error": "RETRIEVAL_EXHAUSTED"}` after 20 calls — this is manual but produces the exact string.
2. **Use `ToolCallLimitMiddleware`** with `exit_behavior="continue"` and customize the message via the source (not configurable in v0.4.11 without subclassing).

**Recommendation:** Use a thin wrapper function around the retrieval tools that maintains a counter in a mutable container (not LangGraph state). Pass the wrapped versions to `create_deep_agent`. This guarantees the exact `RETRIEVAL_EXHAUSTED` string and is testable independently.

### Pattern 4: System Prompt for Write-Todos Gate

**What:** The `TodoListMiddleware` automatically injects its own system prompt guidance into every model call. To enforce that `write_todos` is called BEFORE retrieval, the custom `system_prompt` passed to `create_deep_agent` must include an explicit rule. The middleware-injected guidance does not block tool calls — it's advisory.

**Enforcement via system prompt (soft gate):**
```python
SYSTEM_PROMPT = """
## Mandatory Planning Gate
Before calling any retrieval tool (route_files, search_in_file), you MUST call write_todos
with at minimum:
1. A restatement of the question as you understand it.
2. Your planned tool call sequence in order.

Failure to write todos before retrieval will result in disorganized evidence collection.
You may update the todo list mid-run as evidence changes the plan.
Mark items as completed as you finish each step.

## Tool Usage Rules
- NEVER compute percent change inline. Always use pct_change(old, new) tool.
- ALWAYS call verify_answer before normalize_answer (Phase 4 requirement — stub for now).
- NEVER generate arithmetic formulas inline. Use calculate() for all arithmetic.

## Exhaustion Handling
If route_files or search_in_file returns RETRIEVAL_EXHAUSTED, stop calling that tool.
Attempt to answer from evidence gathered so far.
If evidence is insufficient, respond with exactly:
"I cannot determine the answer from the available corpus."
"""
```

**Trace visibility:** The `TodoListMiddleware` stores todos in the `PlanningState.todos` list, which is part of the LangGraph state and visible in LangSmith traces. Each `write_todos` call produces a `ToolMessage` in the message history — this is the "visible in trace" requirement.

### Pattern 5: Scratch File Writes

**What:** The `FilesystemMiddleware` provides `write_file`, `edit_file`, `read_file`, `ls`, `glob`, `grep` tools. The agent calls `write_file(path, content)` to write scratch files. With `FilesystemBackend(root_dir="./scratch", virtual_mode=False)`, paths like `{uid}/evidence.txt` resolve to `./scratch/{uid}/evidence.txt` on disk.

**The six files and when the agent writes them:**

| File | Written when | Content |
|------|-------------|---------|
| `evidence.txt` | After each `search_in_file` call | Append: source path + span text + agent note on why selected |
| `tables.txt` | After each `extract_table_block` call | Append: raw table block as returned |
| `extracted_values.txt` | After reading table/evidence | One line per value: `name = value (unit)` |
| `calc.txt` | After each `calculate`/`pct_change` call | Expression, labeled inputs with source, result |
| `verification.txt` | Phase 4 (verifier subagent) | Stub content for Phase 3: "verification pending" |
| `answer.txt` | After `normalize_answer` call | Line 1: normalized answer; Line 2: one-sentence rationale |

**Important:** The agent uses the `write_file` / `edit_file` tools provided by `FilesystemMiddleware` to write these files — the tool call appears in the trace. Do not build a separate file-writing mechanism; rely on the middleware's tools.

### Anti-Patterns to Avoid

- **Passing `backend` as a class, not an instance:** `create_deep_agent` accepts either a `BackendProtocol` instance or a factory callable. Passing `FilesystemBackend` (the class) instead of `FilesystemBackend(root_dir=..., virtual_mode=False)` (an instance) will cause `FilesystemBackend` to be used as a factory with no arguments — the `virtual_mode` deprecation warning will fire and the root_dir will be `cwd`, not `./scratch`.

- **Sharing one MemorySaver across re-runs of the same UID:** `MemorySaver` stores conversation history in RAM keyed by `thread_id`. Re-invoking with the same `thread_id` resumes the conversation from where it left off. For idempotent re-runs, either clear the checkpointer's state or create a new `MemorySaver()` per question.

- **Setting `max_iterations` as a parameter to `create_deep_agent`:** There is no `max_iterations` parameter on `create_deep_agent` (v0.4.11) or on `create_agent` (langchain 1.2.12). The underlying LangGraph graph uses `recursion_limit=1000` (set by `create_deep_agent`) and `10_000` (set by `create_agent`). Iteration limiting must be done via `ModelCallLimitMiddleware` (model call count) or `ToolCallLimitMiddleware` (per-tool call count), not via a parameter.

- **Setting `virtual_mode=True` for scratch isolation:** `virtual_mode=True` only restricts path traversal (`..`, `~`). It does NOT provide sandbox isolation. For scratch isolation, use per-UID subdirectories and pre-clear them before each run. The `virtual_mode` flag is about path security semantics, not state isolation.

- **Using `FilesystemMiddleware` directly with a custom backend instance:** `FilesystemMiddleware` accepts a `backend` argument. However, `create_deep_agent` already constructs `FilesystemMiddleware(backend=backend)` internally using the `backend` argument you pass to `create_deep_agent`. Do not instantiate `FilesystemMiddleware` yourself and also pass `backend` — the middleware is already handled.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Todo list state and write_todos tool | Custom state dict + custom tool | `TodoListMiddleware` (auto-included in `create_deep_agent`) | State schema, parallel-call guard, and system prompt injection are all in the middleware |
| Filesystem tools (write_file, read_file, ls) | Custom file-writing tools | `FilesystemMiddleware` (auto-included in `create_deep_agent`) | Already provides 6 tools; the agent uses them natively |
| Per-tool call counting | Mutable global counter | `ToolCallLimitMiddleware(tool_name=..., run_limit=20)` | Thread-safe, state-managed, produces correct ToolMessage error response |
| Thread state for within-question continuity | Custom message history | `MemorySaver` checkpointer | Standard LangGraph pattern; zero boilerplate |
| Subagent delegation scaffold | Custom subprocess or nested agent call | `SubAgentMiddleware` (auto-included) | Message passing, error propagation, and context isolation already handled |

**Key insight:** `create_deep_agent` already includes `TodoListMiddleware`, `FilesystemMiddleware`, and `SubAgentMiddleware` — the only things to add are the custom tools, system prompt, `FilesystemBackend` backend, `MemorySaver` checkpointer, and the `ToolCallLimitMiddleware` instances for retrieval limiting.

---

## Common Pitfalls

### Pitfall 1: MemorySaver Does Not Reset on Scratch Dir Wipe

**What goes wrong:** Test re-runs the agent with the same UID after wiping `./scratch/{uid}/`. The scratch directory is empty but the `MemorySaver` still has the prior conversation history. The agent "remembers" the previous question and skips retrieval.

**Why it happens:** `MemorySaver` is in-RAM, keyed by `thread_id`. Wiping files has no effect on RAM.

**How to avoid:** For idempotent re-runs, create a new `MemorySaver()` instance per question OR use a compound thread_id like `f"{uid}_{run_count}"`. The simplest production approach: create the agent fresh for each question with `MemorySaver()`.

**Warning signs:** Agent returns an answer after 1-2 tool calls on a re-run where the first run took 8+ calls.

### Pitfall 2: ToolCallLimitMiddleware run_limit vs. thread_limit

**What goes wrong:** `ToolCallLimitMiddleware` raises `ValueError` if `run_limit > thread_limit` (when both are set). If only `run_limit` is set and no `thread_limit`, it works fine.

**How to avoid:** For this project, set only `run_limit=20` and leave `thread_limit=None`. The `run_limit` resets each invocation (each call to `agent.invoke()`), which matches the per-question budget.

**Warning signs:** `ValueError: run_limit (20) cannot exceed thread_limit` — this means `thread_limit` was accidentally set below 20.

### Pitfall 3: FilesystemBackend virtual_mode Deprecation Warning

**What goes wrong:** `FilesystemBackend(root_dir="./scratch")` without `virtual_mode` argument emits a `DeprecationWarning` and defaults to `virtual_mode=False`. Not a breaking error but will pollute test output.

**How to avoid:** Always pass `virtual_mode=False` explicitly: `FilesystemBackend(root_dir="./scratch", virtual_mode=False)`.

### Pitfall 4: Agent Does Not Write Scratch Files Without Explicit Instruction

**What goes wrong:** The `FilesystemMiddleware` provides file tools but the agent only uses them if the system prompt explicitly instructs it to write evidence/tables/calc/answer to specific files. Without instruction, the agent may reason in its reply text without persisting anything.

**How to avoid:** The system prompt must include explicit file-writing instructions for each stage:
- "After each search_in_file result, write the span to `{uid}/evidence.txt`."
- "After each extract_table_block result, write the raw block to `{uid}/tables.txt`."
- "After extracting numeric values, write them to `{uid}/extracted_values.txt` with units."
- etc.

The `uid` value needs to be injected into the system prompt or the initial user message so the agent knows the correct path prefix.

**Warning signs:** End-to-end smoke test shows final answer correct but one or more scratch files are empty or missing.

### Pitfall 5: tools Must be @tool Decorated for create_deep_agent

**What goes wrong:** `create_deep_agent` passes `tools` through to `create_agent`, which wraps them as `StructuredTool`. If the tool functions are plain callables (not `@tool`-decorated), the tool schema may be inferred incorrectly from type hints — but more importantly, the tool name used in `ToolCallLimitMiddleware(tool_name=...)` must exactly match the name LangChain assigns to the tool.

**How to avoid:** Use `@tool` decorator on all tool functions with explicit `name` set:
```python
from langchain_core.tools import tool

@tool(name="route_files")
def route_files_tool(question: str) -> dict:
    ...
```
Then pass `tool_name="route_files"` to `ToolCallLimitMiddleware`. Verify by printing `tool.name` after decoration.

**Warning signs:** `ToolCallLimitMiddleware` never fires even after 25 retrieval calls.

### Pitfall 6: Scratch Directory Must Exist Before Agent Writes Files

**What goes wrong:** `FilesystemBackend` with `virtual_mode=False` uses `Path(root_dir)` as the cwd for relative paths. The agent writes `{uid}/evidence.txt` which resolves to `./scratch/{uid}/evidence.txt`. If `./scratch/{uid}/` does not exist, `write_file` fails with `FileNotFoundError`.

**How to avoid:** Pre-create `./scratch/{uid}/` before invoking the agent. Include this in the per-question lifecycle:
```python
Path(f"./scratch/{uid}").mkdir(parents=True, exist_ok=True)
```

---

## Code Examples

### create_deep_agent Minimal Wiring

```python
# Source: deepagents 0.4.11 graph.py — actual create_deep_agent signature
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import ToolCallLimitMiddleware
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    model=get_model(),             # BaseChatModel instance from model_adapter.py
    tools=[...],                   # @tool-decorated Phase 1+2 functions
    system_prompt=SYSTEM_PROMPT,   # str — prepended before BASE_AGENT_PROMPT
    middleware=[                   # appended AFTER built-in middleware stack
        ToolCallLimitMiddleware(tool_name="route_files",    run_limit=20, exit_behavior="continue"),
        ToolCallLimitMiddleware(tool_name="search_in_file", run_limit=20, exit_behavior="continue"),
    ],
    backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
    checkpointer=MemorySaver(),
)
```

### Invoking with thread_id

```python
# Source: LangGraph MemorySaver pattern + deepagents docs
result = agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    config={"configurable": {"thread_id": uid}},
)
final_answer = result["messages"][-1].content
```

### ToolCallLimitMiddleware Signature

```python
# Source: langchain 1.2.12 langchain/agents/middleware/tool_call_limit.py
from langchain.agents.middleware.tool_call_limit import ToolCallLimitMiddleware

ToolCallLimitMiddleware(
    tool_name="route_files",   # None = limit all tools
    thread_limit=None,         # across all runs of same thread_id
    run_limit=20,              # per single agent.invoke() call
    exit_behavior="continue",  # "continue" | "error" | "end"
)
# Note: ValueError if run_limit > thread_limit when both are set
# Safe pattern: set only run_limit, leave thread_limit=None
```

### FilesystemBackend Constructor

```python
# Source: deepagents 0.4.11 deepagents/backends/filesystem.py
from deepagents.backends import FilesystemBackend

backend = FilesystemBackend(
    root_dir="./scratch",    # Optional; defaults to cwd
    virtual_mode=False,      # Must specify explicitly (deprecation warning otherwise)
    max_file_size_mb=10,     # Optional; default 10MB
)
```

### TodoListMiddleware write_todos Tool

```python
# Source: langchain 1.2.12 langchain/agents/middleware/todo.py
# The write_todos tool accepts a list[Todo] where:
# Todo = {"content": str, "status": "pending" | "in_progress" | "completed"}
#
# The agent calls it like:
# write_todos(todos=[
#     {"content": "Understand question: what was defense spending FY1940?", "status": "in_progress"},
#     {"content": "Call route_files for FY1940", "status": "pending"},
#     {"content": "Call search_in_file for defense spending", "status": "pending"},
#     ...
# ])
#
# The middleware updates PlanningState.todos and returns a ToolMessage confirming the update.
# Todos are visible in LangSmith trace as ToolMessage content.
```

### Scratch Directory Lifecycle (per question)

```python
# Recommended pattern for SCR-01 compliance
import shutil
from pathlib import Path

def prepare_scratch(uid: str) -> Path:
    """Wipe and recreate the scratch directory for a question UID."""
    scratch = Path("./scratch") / uid
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    return scratch
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `create_react_agent` from `langgraph.prebuilt` | `create_agent` from `langchain` 1.2.x (used internally by `create_deep_agent`) | langchain 1.x release (early 2025) | New middleware system; old `create_react_agent` lacks middleware hook protocol |
| Manual file writing tools | `FilesystemMiddleware` from deepagents | deepagents 0.1.x | No-boilerplate scratch files; middleware stacked automatically |
| `AgentExecutor` with `max_iterations` | `ToolCallLimitMiddleware(run_limit=N)` | langchain 1.0 | `AgentExecutor` is deprecated; middleware-based limiting replaces `max_iterations` |
| `ConversationBufferMemory` | `MemorySaver` checkpointer (LangGraph) | LangGraph 0.1+ | LangGraph state graph replaces legacy memory classes |

**Deprecated/outdated:**
- `AgentExecutor.max_iterations`: Removed in langchain 1.x. Use `ModelCallLimitMiddleware(run_limit=N)` for model call budget or `ToolCallLimitMiddleware` for tool-specific budget.
- `langchain.agents.initialize_agent`: Removed. Use `create_agent` (plain) or `create_deep_agent` (with middleware).

---

## Open Questions

1. **ToolCallLimitMiddleware run_limit scope — combined or per-tool?**
   - What we know: Two separate `ToolCallLimitMiddleware` instances (one for `route_files`, one for `search_in_file`) each have their own `run_limit=20`.
   - What's unclear: The context decision says "per-question retrieval call limit: 20 calls" — does this mean 20 per tool or 20 combined across both tools?
   - Recommendation: Implement as 20 per tool (i.e., two middleware instances each with `run_limit=20`). If the intent is 20 combined, use a single `ToolCallLimitMiddleware(tool_name=None, run_limit=20)` to cap all tool calls — but this would also cap `calculate` and `extract_table_block`, contradicting the "uncapped" requirement. Safest: per-tool limiters.

2. **How to inject UID into system prompt for scratch paths?**
   - What we know: The system prompt must tell the agent which subdirectory to write scratch files to.
   - What's unclear: Whether the UID is injected into `system_prompt` at agent construction time (requires rebuilding agent per question) or injected as part of the initial user message.
   - Recommendation: Prepend a preamble to the user message: `f"Question UID: {uid}\nScratch directory: scratch/{uid}/\n\nQuestion: {question}"`. This avoids rebuilding the agent for each question.

3. **verification.txt for Phase 3 (no verifier yet)**
   - What we know: Phase 3 does not include the verifier subagent (that's Phase 4). But SCR-02 requires all six files.
   - What's unclear: Whether Phase 3 should stub `verification.txt` or leave it as a Phase 4 concern.
   - Recommendation: The agent writes `verification.txt` with stub content `"verification: pending (Phase 4)"` after completing calculation, satisfying the non-empty file requirement.

---

## Sources

### Primary (HIGH confidence)
- deepagents 0.4.11 wheel (inspected directly) — `graph.py`, `backends/filesystem.py`, `backends/__init__.py`, `middleware/__init__.py`, `middleware/subagents.py`
- langchain 1.2.12 wheel (inspected directly) — `agents/factory.py`, `agents/middleware/__init__.py`, `agents/middleware/todo.py`, `agents/middleware/tool_call_limit.py`, `agents/middleware/model_call_limit.py`
- PyPI deepagents page: https://pypi.org/project/deepagents/
- GitHub langchain-ai/deepagents: https://github.com/langchain-ai/deepagents

### Secondary (MEDIUM confidence)
- LangChain docs — middleware: https://docs.langchain.com/oss/python/deepagents/middleware
- DeepWiki deepagents create_deep_agent: https://deepwiki.com/langchain-ai/deepagents/5.1-create_deep_agent
- Existing project research docs: `.planning/research/ARCHITECTURE.md`, `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — deepagents 0.4.11 wheel inspected directly; exact API verified
- Architecture: HIGH — `create_deep_agent` source read, middleware order confirmed, `FilesystemBackend` constructor confirmed
- ToolCallLimitMiddleware: HIGH — source read, parameters verified, behavior documented
- `max_iterations` absence: HIGH — confirmed not a parameter in `create_deep_agent` or `create_agent` 1.2.12
- Pitfalls: HIGH for implementation-specific ones (confirmed from source); MEDIUM for runtime behavior (based on code reading, not live testing)

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (deepagents moves fast — recheck if version advances past 0.4.x)
