# STACK.md — AgentBeats OfficeQA Finance Agent

## Recommended Stack

| Layer | Choice | Package / Version | Notes |
|---|---|---|---|
| **Language** | Python | 3.10+ | LangChain 1.0 requirement; 3.12 recommended |
| **Agent framework** | LangChain `create_agent` | `langchain>=1.0,<2.0` | Single-purpose Q&A agent; fixed tool loop is sufficient |
| **Orchestration / middleware** | Deep Agents | `deepagents` (latest) | Verifier runs as a named subagent via `SubAgentMiddleware`; `FilesystemMiddleware` provides per-question scratch space; `TodoListMiddleware` tracks multi-step retrieval plans |
| **LangChain core** | langchain-core | `langchain-core>=1.0,<2.0` | Always install explicitly alongside `langchain` |
| **Graph / checkpointing** | LangGraph (transitive) | `langgraph>=1.0,<2.0` | Pulled in by `deepagents`; use `MemorySaver` checkpointer for thread state |
| **LLM provider** | Vertex AI (Google Gen AI SDK) | `google-genai` (latest) | Hackathon constraint — all LLM calls via Vertex AI only |
| **LangChain ↔ Vertex AI bridge** | langchain-google-genai | latest | Wires the Gen AI SDK into LangChain's model interface |
| **Model (default)** | `gemini-2.0-flash` | via `MODEL_ID` env var | Fast, balanced; swap to `gemini-2.5-pro` for harder questions |
| **Corpus search — file routing** | Custom file-router tool | stdlib (`pathlib`, `re`) | Parses `treasury_bulletin_YYYY_MM.txt` filenames; date/topic extraction from question; narrows 697 files to 1–3 candidates |
| **Corpus search — in-file** | BM25 + regex | `rank-bm25` (latest) | No embeddings, no GPU, no cost; per-file BM25 index built on demand; regex for exact figure extraction |
| **Table extraction** | Custom table-block extractor tool | stdlib (`re`) | Identifies markdown table blocks in `.txt` files; returns raw block for LLM to parse |
| **Arithmetic / calculation** | Python calculator tool | stdlib (`ast`, `decimal`) | Safe eval-style calculation with `decimal` for financial precision; no external dependency |
| **Answer normalization** | Custom normalizer tool | stdlib | Strips commas, currency symbols, trailing zeros; enforces benchmark answer format |
| **Verifier subagent** | Deep Agents `SubAgentMiddleware` | via `deepagents` | Separate subagent checks evidence coverage, units, arithmetic, and answer precision before finalizing |
| **Per-question scratch space** | Deep Agents `FilesystemMiddleware` | via `deepagents` | `FilesystemBackend(root_dir="./scratch")`; stores evidence spans, extracted values, intermediate calculations keyed by question UID |
| **HTTP server (A2A endpoint)** | FastAPI | `fastapi`, `uvicorn` (latest) | Single `POST /run` endpoint; A2A-compatible request/response; lightweight |
| **Observability / tracing** | LangSmith | `langsmith>=0.3.0` | `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` env vars; traces all LLM calls and tool invocations |
| **Dependency pinning** | requirements.txt | see below | No `pyproject.toml` needed for hackathon scope |

---

## Key Integration Notes

### Vertex AI authentication
Set three environment variables; initialize `genai.Client()` with no arguments:
```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=true
```
The LangChain bridge (`langchain-google-genai`) reads these automatically when the model string is passed as `"google-genai:gemini-2.0-flash"` to `create_agent` / `create_deep_agent`.

### MODEL_ID env var pattern
The agent must read `os.environ.get("MODEL_ID", "gemini-2.0-flash")` and pass it as the `model=` argument. This allows swapping Gemini 2.5 Pro or a Vertex-hosted Claude Sonnet without code changes.

### Two-stage retrieval as tools
Both retrieval stages are LangChain `@tool` functions registered on the main agent — not a separate RAG pipeline or vector store. No embeddings are needed:
1. `route_files(question: str) -> list[str]` — returns 1–3 matching filenames
2. `search_in_file(filename: str, query: str) -> list[str]` — returns BM25-ranked spans

### Verifier as Deep Agents subagent
The verifier is registered as a named subagent in `create_deep_agent(subagents=[...])`. The main agent calls `task(agent="verifier", instruction="Check answer X against evidence Y")`. The verifier subagent has its own tools (arithmetic checker, unit validator) and does **not** inherit skills from the main agent.

### Filesystem scratch space
Use `FilesystemBackend(root_dir="./scratch", virtual_mode=False)` so scratch files are real on-disk paths. Key them by question UID: `./scratch/{uid}/evidence.txt`, `./scratch/{uid}/calc.txt`, `./scratch/{uid}/answer.txt`. Re-running the same UID overwrites prior scratch for reproducibility.

### Deep Agents vs plain `create_agent`
The main entry point uses `create_deep_agent` (not bare `create_agent`) because:
- `FilesystemMiddleware` provides the scratch space without manual implementation
- `SubAgentMiddleware` wires the verifier subagent with one config dict
- `TodoListMiddleware` lets the agent plan multi-step retrieval for complex questions

The compiled agent is then wrapped by FastAPI — `agent.invoke({"messages": [...]}, config={"configurable": {"thread_id": uid}})`.

### Minimal `requirements.txt`
```
langchain>=1.0,<2.0
langchain-core>=1.0,<2.0
langgraph>=1.0,<2.0
langsmith>=0.3.0
deepagents
langchain-google-genai
google-genai
rank-bm25
fastapi
uvicorn[standard]
pydantic>=2.0
```

---

## What NOT to Use

| Do NOT use | Why |
|---|---|
| Vector embeddings (FAISS, Chroma, Pinecone, etc.) | Adds GPU/cost overhead; BM25 + regex is sufficient for exact figure lookup in structured text |
| `google-cloud-aiplatform` (legacy) | Deprecated; use `google-genai` (Gen AI SDK) instead |
| Direct OpenAI or Anthropic API keys | Hackathon constraint — all LLM calls must go through Vertex AI only |
| Web search tools (Tavily, etc.) | Strict grounding in local corpus only; no external data sources during inference |
| Hardcoded UID-keyed answers | Benchmark-unsafe; violates generality constraint |
| `langchain-community` (unpinned) | Does not follow semver; breaking changes on minor version bumps |
| LangGraph as top-level orchestrator | Deep Agents wraps LangGraph and provides middleware for free; use Deep Agents at top level |
| Mobile/browser UI | Pure API/CLI; out of scope |

---

## Open Questions

1. **A2A schema**: What is the exact HTTP request/response body required by the AgentBeats benchmark? Must be confirmed from the benchmark GitHub repo before endpoint is finalized.

2. **MODEL_ID for Claude on Vertex**: If `MODEL_ID` is set to a Claude model, does `langchain-google-genai` handle it, or does it require a different LangChain package pointed at the Vertex AI endpoint?

3. **BM25 index strategy**: Should the BM25 index be built once per file on first access and cached to `./scratch/bm25_cache/`, or rebuilt per question?

4. **Corpus completeness**: Are all `source_files` referenced in `officeqa_full.csv` present in `corpus/transformed/`? Missing files need to be identified before benchmark submission.

5. **Table extraction consistency**: Do Treasury Bulletin files from 1939 vs 2025 use consistent enough markdown table formatting for a single regex heuristic?
