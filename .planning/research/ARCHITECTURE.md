# ARCHITECTURE.md — AgentBeats OfficeQA Finance Agent

## 1. Agent Loop Design

The top-level entry point is `create_deep_agent` (from `deepagents`) rather than bare `create_agent`. The compiled deep agent is what FastAPI wraps — invoked once per HTTP request with the question UID as `thread_id`.

```
HTTP POST /run
    │
    ▼
FastAPI handler
    │  agent.invoke({"messages": [...]}, config={"configurable": {"thread_id": uid}})
    ▼
create_deep_agent (LangGraph-backed)
    │
    ├── TodoListMiddleware  → write_todos() — plans multi-step retrieval
    ├── FilesystemMiddleware → ls/read_file/write_file/edit_file/glob/grep
    └── SubAgentMiddleware  → task(agent="verifier", instruction=...)
    │
    ├── Tool: route_files(question)              → stage 1 search
    ├── Tool: search_in_file(filename, query)    → stage 2 search
    ├── Tool: extract_table_block(filename, anchor) → table extraction
    ├── Tool: calculate(expression)              → Python Decimal calculator
    └── Tool: normalize_answer(raw)              → benchmark format normalizer
    │
    ▼
verifier subagent
    └── checks evidence coverage, units, arithmetic, answer precision
    │
    ▼
Final answer written to ./scratch/{uid}/answer.txt and returned in HTTP response
```

The model is selected via `os.environ.get("MODEL_ID", "gemini-2.0-flash")` and passed as `model=f"google-genai:{MODEL_ID}"`. Swapping to `gemini-2.5-pro` or a Vertex-hosted Claude Sonnet requires only an env var change.

---

## 2. Deep Agents Middleware Configuration

```python
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import MemorySaver

agent = create_deep_agent(
    name="officeqa-finance-agent",
    model=f"google-genai:{os.environ.get('MODEL_ID', 'gemini-2.0-flash')}",
    tools=[route_files, search_in_file, extract_table_block, calculate, normalize_answer],
    system_prompt=SYSTEM_PROMPT,
    subagents=[
        {
            "name": "verifier",
            "description": "Checks evidence coverage, units, arithmetic, and answer precision",
            "system_prompt": VERIFIER_PROMPT,
            "tools": [calculate],   # verifier gets its own calculator; no inherited skills
        }
    ],
    backend=FilesystemBackend(root_dir="./scratch", virtual_mode=False),
    checkpointer=MemorySaver(),
)
```

Key middleware notes:

- **TodoListMiddleware** (always on): the agent calls `write_todos` at the start of each question to plan retrieval and verification steps — essential for multi-date questions requiring several files.
- **FilesystemMiddleware** with `virtual_mode=False`: files are real on-disk paths rooted at `./scratch`. Required so the verifier can read evidence written by the main agent.
- **SubAgentMiddleware**: the verifier subagent is stateless (ephemeral per call). The main agent passes all evidence and the proposed answer in a single `task()` call.
- **MemorySaver checkpointer**: thread-level state continuity within a single question. Re-running the same UID overwrites scratch and starts a fresh thread.
- No `interrupt_on` — fully automated, no human-in-the-loop.

---

## 3. Two-Stage Search Architecture

### Stage 1 — File Router: `route_files(question: str) -> list[str]`

Pure stdlib, no LLM call. Extracts date and topic signals from the question and maps to 1–3 candidate filenames.

Routing logic:
1. **Year extraction**: `r'\b(19[3-9]\d|20[0-2]\d)\b'` finds all four-digit years.
2. **Month extraction**: detects month names or fiscal-year language ("FY 1940") → maps to calendar months. FY maps to July–June of the relevant year pair.
3. **Topic extraction**: keyword matching ("gold", "receipts", "expenditures", "public debt") narrows years when no explicit date.
4. **Fallback**: return 5 most recent files covering the plausible answer period.

Returns `list[str]` of absolute paths.

### Stage 2 — In-File BM25 + Regex: `search_in_file(filename: str, query: str) -> list[str]`

1. **Tokenize**: split file into non-overlapping 20-line spans. A line starting with `|` is never a span boundary (preserves table blocks).
2. **BM25 index**: build `BM25Okapi` (from `rank-bm25`) per file. Index built on first access, cached in memory for the request duration — not persisted to avoid stale state.
3. **Score and return**: top-5 BM25-ranked spans as plain text strings → written to `./scratch/{uid}/evidence.txt`.

The `query` passed by the main agent should be a short targeted phrase, not the full question (e.g. `"national defense expenditures 1940"` not the verbatim question text).

---

## 4. Table Extraction Regex

Treasury Bulletin `.txt` files use pipe-delimited markdown tables consistently across the 1939–2025 range.

**Tool:** `extract_table_block(filename: str, anchor: str) -> str`

```python
import re

TABLE_LINE = re.compile(r'^\s*\|')
HEADER_SEP = re.compile(r'^\s*\|[\s\-|]+\|')

def find_table_block(text: str, anchor: str) -> str:
    lines = text.splitlines()
    anchor_idx = next(
        (i for i, ln in enumerate(lines) if anchor.lower() in ln.lower()), None
    )
    if anchor_idx is None:
        return ""
    start = None
    for i in range(anchor_idx, min(anchor_idx + 15, len(lines))):
        if TABLE_LINE.match(lines[i]):
            start = i
            break
    if start is None:
        return ""
    end = start
    while end < len(lines) and TABLE_LINE.match(lines[end]):
        end += 1
    return "\n".join(lines[start:end])
```

Observed column header format: `Parent > Child > Unnamed: n_level_m`. The extractor returns the raw block; the LLM parses headers and locates the target cell.

---

## 5. Calculation Tool Safety

**Tool:** `calculate(expression: str) -> str`

AST-based safe eval with `decimal.Decimal` — no `eval()`, no function calls, no imports.

```python
import ast, decimal
from decimal import Decimal

ALLOWED_NODES = {
    ast.Expression, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mul, ast.Div, ast.Pow, ast.USub, ast.UAdd,
    ast.Constant,
}

def _safe_eval(node):
    if type(node) not in ALLOWED_NODES:
        raise ValueError(f"Disallowed: {type(node).__name__}")
    if isinstance(node, ast.Expression):  return _safe_eval(node.body)
    if isinstance(node, ast.Constant):    return Decimal(str(node.value))
    if isinstance(node, ast.BinOp):
        L, R, op = _safe_eval(node.left), _safe_eval(node.right), node.op
        if isinstance(op, ast.Add):  return L + R
        if isinstance(op, ast.Sub):  return L - R
        if isinstance(op, ast.Mul):  return L * R
        if isinstance(op, ast.Div):  return L / R
        if isinstance(op, ast.Pow):  return L ** R
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub): return -_safe_eval(node.operand)
        if isinstance(node.op, ast.UAdd): return +_safe_eval(node.operand)
    raise ValueError(f"Unhandled: {ast.dump(node)}")
```

Errors returned as `"ERROR: ..."` strings — the LLM can detect and retry with a corrected expression.

---

## 6. A2A HTTP Server

**Provisional design — exact A2A schema must be confirmed from benchmark GitHub repo:**

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="OfficeQA Finance Agent")

class RunRequest(BaseModel):
    uid: str
    question: str

class RunResponse(BaseModel):
    uid: str
    answer: str

@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": req.question}]},
        config={"configurable": {"thread_id": req.uid}},
    )
    answer = result["messages"][-1].content
    return RunResponse(uid=req.uid, answer=answer)
```

Notes:
- Agent created once at startup, not per-request.
- Re-submitting the same UID overwrites scratch and starts a fresh thread → reproducible.
- No authentication (open benchmark endpoint).
- If A2A spec requires different path/envelope, only the route decorator and Pydantic models change.

---

## 7. Evidence Scratch Space Layout

```
./scratch/
└── {uid}/                      e.g. UID0001/
    ├── evidence.txt            raw BM25 spans, one section per source file
    ├── tables.txt              raw table blocks from extract_table_block
    ├── extracted_values.txt    named values: "defense_1940 = 2602"
    ├── calc.txt                expression + result per calculation step
    ├── verification.txt        verifier report: PASS/FAIL + notes
    └── answer.txt              final normalized answer string
```

File lifecycle per question:
1. `route_files` → candidate filenames noted in `evidence.txt` header
2. `search_in_file` per file → spans appended to `evidence.txt`
3. `extract_table_block` → raw blocks written to `tables.txt`
4. LLM extracts numeric values → `extracted_values.txt`
5. `calculate` → expression + result appended to `calc.txt`
6. `task(agent="verifier")` → verifier reads evidence/calc, writes `verification.txt`
7. Verification passes → `normalize_answer` → `answer.txt` → returned in HTTP response
8. Verification fails → main agent retries retrieval/calculation; files overwritten

Cross-question isolation: each UID directory is fully independent. No shared state at the filesystem level.

---

## 8. Suggested Build Order

| Phase | Deliverable | Validates |
|-------|-------------|-----------|
| **1. Environment & skeleton** | `requirements.txt` installed; Vertex AI auth verified; stub `create_deep_agent` returns static answer | Vertex AI credentials, `google-genai` SDK, `deepagents` import |
| **2. File router tool** | `route_files` passes unit tests for 10 sample questions | Regex year/month extraction; fiscal-year → calendar-month mapping |
| **3. BM25 in-file search tool** | `search_in_file` returns correct spans for 5 known question/answer pairs | `rank-bm25` integration; span boundary logic |
| **4. Table extractor & calculator** | Both tools pass unit tests including Decimal precision and AST safety | Regex table detection; Decimal arithmetic; error handling |
| **5. Scratch space wiring** | Full pipeline (no verifier) writes all scratch files for 3 E2E questions | FilesystemMiddleware paths; TodoListMiddleware planning; thread isolation |
| **6. Verifier subagent** | Verifier rejects a wrong answer; main agent retries on rejection | SubAgentMiddleware delegation; stateless verifier contract |
| **7. FastAPI server** | `POST /run` returns correct answers for 10 questions over HTTP | FastAPI/uvicorn startup; agent invocation from HTTP handler |
| **8. Benchmark sweep** | Full run against `officeqa_full.csv` and `officeqa_pro.csv` | End-to-end correctness; missing corpus files identified |

**Phase 1 prerequisite checklist:**
- GCP project with Vertex AI API enabled
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_VERTEXAI=true`
- `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` for tracing
- Python 3.12 recommended (3.10+ required)
- Fresh virtual environment + `pip install -r requirements.txt`
