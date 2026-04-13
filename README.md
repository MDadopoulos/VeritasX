# VeritasX

A retrieval-grounded multi-agent system that answers fiscal and financial questions against the **US Treasury Bulletin** corpus (1939–2025). VeritasX is a purple agent packaged for [AgentBeats](https://agentbeats.dev) and exposed over the A2A protocol.

---

## Abstract

VeritasX decomposes each question into its *source constraint*, *computation range*, and *data vintage* (reported vs. revised), then coordinates four specialist subagents that communicate **exclusively through an isolated per-question scratch filesystem** (`scratch/{uid}/`) rather than by passing raw data through the orchestrator's context window:

- **search-agent** — BM25 retrieval and table-aware extraction over the local corpus. Writes `evidence.txt` and `extracted_values.txt` with every value tagged by unit, period, and revised/preliminary status. Raw corpus spans never reach the orchestrator.
- **calc-agent** — all arithmetic and statistics through sandboxed tools (`calculate`, `pct_change`, `sum_values`, `compute_stat` for CAGR, geometric mean, regression, etc.). Appends to `calc.txt`.
- **external-data-agent** — BLS CPI-U inflation adjustments and Fed H.10 FX conversions.
- **verifier** — gates finalization with a single-use token that `normalize_answer` requires before the orchestrator emits the answer.

Domain logic for statistics, inflation, and FX is factored out of the agent code into **Anthropic-style Skills** (`agentspace/skills/quant-stats`, `cpi-inflation-adjuster`, `historical-fx`) — self-contained `SKILL.md` + `scripts/` + bundled `data/` packages that the calc and external-data subagents invoke on demand. This keeps prompts lean, makes reference data auditable and versioned alongside the code, and lets new quantitative capabilities be added without touching the harness.

The scratch filesystem is the coordination substrate: each subagent reads its predecessors' artifacts (`evidence.txt` → `extracted_values.txt` → `calc.txt` → `answer.txt`) and writes its own, giving the pipeline a durable, inspectable audit trail per question. Combined with mandatory planning, strict retrieval/computation/verification separation, and format-aware normalization that forces the final `<FINAL_ANSWER>` payload to literally satisfy the question's precision, scale, and unit constraints, VeritasX ships as a DeepAgents/LangGraph harness, containerized, and exposed to AgentBeats via an A2A endpoint.

---

## Architecture

```
                          ┌────────────────────────────┐
 user question ─────────▶ │        Orchestrator        │
                          │  (decomposes + plans only) │
                          └──────────────┬─────────────┘
                                         │ UID-scoped tasks
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
   ┌──────────────────┐       ┌────────────────────┐       ┌──────────────────┐
   │   search-agent   │       │ external-data-agent│       │    calc-agent    │
   │  route_files     │       │  adjust_inflation  │       │  calculate       │
   │  search_in_file  │       │  convert_fx        │       │  compute_stat    │
   │  extract_table…  │       │   (Skills: CPI/FX) │       │  (Skill: stats)  │
   └────────┬─────────┘       └─────────┬──────────┘       └────────┬─────────┘
            │                           │                           │
            ▼                           ▼                           ▼
       evidence.txt              calc.txt (adj.)                calc.txt
     extracted_values.txt               │                           │
            │                           │                           │
            └───────────────────────────┴─────────────┬─────────────┘
                                                     ▼
                                            ┌────────────────┐
                                            │    verifier    │ ── PASS token ─▶ normalize_answer
                                            └────────┬───────┘                          │
                                                     ▼                                  ▼
                                              verify.txt                     <FINAL_ANSWER>…</FINAL_ANSWER>
                                                                                  answer.txt
```

All inter-agent communication is file-based under `scratch/{uid}/`. A fresh `MemorySaver` and a wiped scratch directory are created per question so no state bleeds between runs.

---

## Repository layout

```
LucidOwlF/
├── corpus/transformed/                 # 1939–2025 Treasury bulletins (plain text)
├── agentspace/
│   ├── skills/                         # Anthropic-style Skills
│   │   ├── quant-stats/                #   CAGR, geomean, regression, SD…
│   │   ├── cpi-inflation-adjuster/     #   BLS CPI-U (1939–2025)
│   │   └── historical-fx/              #   Fed H.10 FX (1971–2025)
│   └── scratch/                        # per-UID working files (runtime)
└── workspace/
    ├── amber-manifest.json5            # AgentBeats registration manifest
    ├── Dockerfile
    ├── requirements.txt
    └── src/
        ├── server.py                   # A2A HTTP server (port 9009)
        ├── executor.py                 # A2A executor wrapper
        ├── agent.py                    # run_question entry point
        ├── harness.py                  # orchestrator + subagent prompts, middleware
        ├── model_adapter.py            # Gemini adapter + API-key rotation
        ├── corpus_manifest.py          # corpus index
        ├── scratch.py                  # per-UID scratch lifecycle
        ├── schemas.py / config.py
        └── tools/
            ├── route_files.py
            ├── search_in_file.py       # BM25 retrieval
            ├── extract_table_block.py
            ├── classify_table_rows.py
            ├── calculate.py
            ├── compute_stat.py
            ├── external_data.py        # adjust_inflation, convert_fx
            ├── verifier.py
            └── normalize_answer.py
```

---

## Configuration

Environment variables (secrets marked ★):

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` ★ | — | Gemini AI Studio API key (required) |
| `GOOGLE_API_KEY_2` ★ | — | Backup key for rotation |
| `GOOGLE_API_KEY_3` ★ | — | Backup key for rotation |
| `MODEL_ID` | `gemini-3-flash-preview` | Subagent model |
| `ORCH_MODEL_ID` | `gemini-3.1-pro-preview` | Orchestrator model |
| `CORPUS_DIR` | `corpus/transformed` | Path to bulletin `.txt` files |
| `SKILLS_DIR` | `agentspace/skills` | Path to Skills bundle |
| `AGENT_TIMEOUT_SECONDS` | `3000` | Per-question timeout |
| `MAX_CONCURRENT_RUNS` | `3` | Concurrent A2A tasks |
| `SERVER_PORT` | `9009` | A2A server port |
| `LANGSMITH_API_KEY` ★ | — | Optional tracing |
| `LANGSMITH_TRACING` | `true` | Auto-detected by LangChain |

Put secrets in `workspace/.env` for local runs, or provide them through the AgentBeats config when deploying.

---

## Running locally

```bash
cd workspace
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

export GOOGLE_API_KEY=...
python -m src.server                                  # listens on :9009
# or: uvicorn src.server:app --host 0.0.0.0 --port 9009
```

Health and discovery:

```bash
curl http://localhost:9009/health
curl http://localhost:9009/.well-known/agent-card.json
```

Programmatic entry point:

```python
from src.agent import run_question
print(run_question(uid="demo-1", question="What was total defense spending in FY1940?"))
```

---

## Running in Docker

```bash
docker build -t veritasx -f workspace/Dockerfile .
docker run --rm -p 9009:9009 -e GOOGLE_API_KEY=$GOOGLE_API_KEY veritasx
```

The published image used by the AgentBeats manifest is `ghcr.io/mdadopoulos/veritasx:latest`.

---

## AgentBeats deployment

`workspace/amber-manifest.json5` registers VeritasX with AgentBeats: declares required secrets, pins static env (model IDs, corpus path, timeouts), and exposes the A2A endpoint on port 9009.

---

## Testing

```bash
cd workspace
pytest                                  # full suite
pytest tests/test_agent.py              # end-to-end agent
pytest tests/test_search_in_file.py     # BM25 retrieval
pytest tests/test_verifier.py           # verifier gate
```

Fixtures live in `workspace/tests/fixtures/`.

---

## Answer contract

Every response ends with:

```
<REASONING>one concise sentence explaining how the answer was derived</REASONING>
<FINAL_ANSWER>the normalized answer string</FINAL_ANSWER>
```

The judge fuzzy-matches the contents of `<FINAL_ANSWER>`. The orchestrator records the required format (precision, scale, unit, sign, currency symbol) in its plan *before* retrieval so it does not drift, and `normalize_answer` refuses to emit without a valid verifier token.
