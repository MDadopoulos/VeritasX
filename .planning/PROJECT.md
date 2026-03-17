# AgentBeats OfficeQA Finance Agent

## What This Is

A LangChain `create_agent` finance agent with Deep Agents middleware built for submission to the Berkeley RDI AgentX/AgentBeats OfficeQA benchmark. It exposes one A2A-compatible HTTP endpoint (the "purple agent") that answers complex financial questions strictly grounded in the local U.S. Treasury Bulletin corpus (697 files, 1939–2025). Internally it runs a retrieval → calculation → verification pipeline before returning any answer.

## Core Value

Every answer must be traceable to a specific sentence or table cell in the local corpus — no hallucination, no web search, exact arithmetic.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] A2A-compatible HTTP server exposing a single agent endpoint that accepts a question and returns a final answer
- [ ] Two-stage corpus search: file-level routing by date/topic metadata, then BM25 + regex within identified files
- [ ] Small focused tools: file router, span reader, table block extractor, Python calculator, answer normalizer
- [ ] Lightweight verifier subagent that checks evidence coverage, units, arithmetic, and answer precision before finalizing
- [ ] Filesystem-backed scratch space for per-question evidence, extracted values, and intermediate calculations
- [ ] All LLM calls go through Vertex AI only (Gemini or Anthropic); model configurable via MODEL_ID env var (default: gemini-2.0-flash)
- [ ] Works against both officeqa_full.csv (790 Qs) and officeqa_pro.csv (416 Qs)
- [ ] Reproducible results: same question always produces same answer given same corpus
- [ ] Setup documentation for GCP project + Vertex AI credential configuration

### Out of Scope

- Web search or external APIs during answer generation — strict grounding in local corpus only
- Hardcoded answers keyed to specific question UIDs — benchmark-safe generality required
- GPU/embedding infrastructure for vector search — BM25 + regex keeps it cost-free and fast
- Mobile or browser UI — pure API/CLI

## Context

- **Corpus**: `corpus/transformed/*.txt` — 697 Treasury Bulletin issues, January 1939 through September 2025, ~368MB total. Each file named `treasury_bulletin_YYYY_MM.txt`. Files contain markdown-formatted tables and prose.
- **Benchmark data**: `officeqa_full.csv` (790 questions) and `officeqa_pro.csv` (416 questions). Each row has `uid`, `question`, `answer`, `source_docs`, `source_files`, `difficulty`.
- **Questions require**: extracting exact figures from prose/tables, summing monthly values, computing percent changes, comparing across years — all demanding precise retrieval + arithmetic, not semantic similarity.
- **A2A spec**: to be confirmed from the benchmark GitHub repo during research phase.
- **Framework stack**: LangChain `create_agent`, Deep Agents middleware for verifier subagent and filesystem state.
- **LLM**: Vertex AI only — configurable MODEL_ID env var; GCP project needs Vertex AI API enabled.

## Constraints

- **LLM Provider**: Vertex AI only (no direct OpenAI, no direct Anthropic API) — hackathon constraint
- **Search**: No vector embeddings or paid search APIs — BM25 + regex only
- **Grounding**: All evidence must come from local corpus files — no external data sources during inference
- **Generality**: No UID-keyed hardcoded answers — must generalize to held-out questions
- **Cost**: Optimize for minimal token usage per question (targeted retrieval, not full-corpus prompting)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Two-stage corpus search (file router → in-file BM25/regex) | 697 files × avg ~1800 lines = too large to search at once; routing by bulletin date narrows to 1-3 files before text search | — Pending |
| Verifier as Deep Agents subagent (not inline prompt) | Separates evidence QA from answer generation; can be skipped in fast mode | — Pending |
| Filesystem scratch space per question | Reproducibility and debuggability; avoids cross-question state contamination | — Pending |
| Configurable MODEL_ID env var | Lets us swap Gemini 2.0 Flash ↔ 2.5 Pro ↔ Claude Sonnet on Vertex without code changes | — Pending |
| A2A interface as HTTP POST /run | Simplest interop; confirm exact spec from benchmark repo | — Pending |

---
*Last updated: 2026-03-17 after initialization*
