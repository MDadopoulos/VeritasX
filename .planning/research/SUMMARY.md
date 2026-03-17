# Research Summary: AgentBeats OfficeQA Finance Agent

**Project:** AgentBeats OfficeQA Finance Agent
**Domain:** Financial document QA over historical corpus (697 Treasury Bulletin files, 1939–2025)
**Researched:** 2026-03-17
**Confidence:** HIGH

---

## Executive Summary

This is a benchmark financial QA agent that must answer precise numeric questions grounded strictly in a local corpus of 697 Treasury Bulletin `.txt` files. The correct architecture is a two-stage retrieval pipeline (file router → BM25 in-file search) feeding a LangChain `create_deep_agent` loop, with a separate verifier subagent that independently checks evidence coverage, unit consistency, arithmetic correctness, and answer format before the final answer is emitted. No vector embeddings, no web search, and no hardcoded answers are appropriate — BM25 plus regex is sufficient and far cheaper for this structured-text corpus.

The recommended stack is Python 3.12 + LangChain >=1.0 + Deep Agents middleware + `google-genai` (Vertex AI, Gemini 2.0 Flash default) + FastAPI for the A2A endpoint. Deep Agents is the correct top-level orchestrator because it provides filesystem scratch isolation per question, a verifier subagent via `SubAgentMiddleware`, and multi-step planning via `TodoListMiddleware` — all without manual implementation. LangGraph is present as a transitive dependency and should not be used as the top-level orchestrator.

The dominant risks fall into three clusters: (1) retrieval failures — retrieving data from the wrong bulletin year or the wrong table due to identical table names across 697 files; (2) arithmetic errors — wrong units (millions vs thousands), wrong percent-change formula direction, and float rounding; (3) format failures — trailing zeros and comma separators causing exact-match failures against the benchmark. All three clusters are mitigated by the verifier subagent, mandatory unit normalization in the calculator tool, and a rule-based answer normalizer built and tested before any benchmark submission.

---

## Recommended Stack (top 8 most important choices with versions)

| # | Choice | Version / Package | Rationale |
|---|--------|-------------------|-----------|
| 1 | **Python** | 3.12 (3.10+ required) | LangChain 1.0 minimum requirement; 3.12 recommended for performance |
| 2 | **Deep Agents** (`deepagents`) | latest | Provides `FilesystemMiddleware`, `SubAgentMiddleware`, `TodoListMiddleware` out of the box — eliminates manual scratch space and verifier wiring |
| 3 | **LangChain** | `langchain>=1.0,<2.0` + `langchain-core>=1.0,<2.0` | Agent loop, tool registration, model abstraction — always install both explicitly |
| 4 | **LangGraph** | `langgraph>=1.0,<2.0` | Transitive via deepagents; use `MemorySaver` checkpointer for per-question thread state |
| 5 | **Vertex AI (google-genai + langchain-google-genai)** | latest both | Hackathon constraint — all LLM calls must go through Vertex AI; `google-genai` is the current SDK (`google-cloud-aiplatform` is deprecated) |
| 6 | **Model** | `gemini-2.0-flash` via `MODEL_ID` env var | Fast, 1M-token context, balanced; swap to `gemini-2.5-pro` via env var for hard questions — no code change required |
| 7 | **BM25 retrieval** | `rank-bm25` latest | No GPU, no cost, no embeddings; per-file BM25 index built on demand; regex fallback for exact numeric matches |
| 8 | **FastAPI + uvicorn** | latest both | Single `POST /run` A2A endpoint; agent created once at startup, not per-request |

**Do NOT use:** FAISS/Chroma/Pinecone (no embeddings needed), `google-cloud-aiplatform` (deprecated), Tavily/web search (corpus-only constraint), `langchain-community` (unpinned, breaks on minor bumps), LangGraph as top-level orchestrator.

---

## Table Stakes Features (must-haves for any correct answer)

These 7 features are required before the agent can answer any benchmark question correctly. Accuracy collapses without all of them.

| ID | Feature | Why It Is Required |
|----|---------|-------------------|
| **TS-1** | **File Router** (`route_files`) | Maps question date/topic signals to 1–3 candidate files from 697; pure stdlib/regex, no LLM call. Without this, BM25 returns noise from random years. |
| **TS-2** | **BM25 + Regex In-File Search** (`search_in_file`) | Retrieves top-5 ranked 20-line spans per candidate file. Regex fallback for exact numeric values. Must run AFTER TS-1, never on the full corpus. |
| **TS-3** | **Markdown Table Block Extractor** (`extract_table_block`) | Extracts complete pipe-delimited table blocks including header rows and footnotes. Missing the footnote row silently loses unit metadata (millions vs thousands). |
| **TS-4** | **Python AST Calculator** (`calculate`) | AST-based safe eval with `decimal.Decimal`. No `eval()`. LLM passes expressions; tool executes safely. Must support `pct_change`, `sum_values`, and rounding. |
| **TS-5** | **Answer Normalizer** (`normalize_answer`) | Rule-based (not LLM) formatting: integers with comma separators, percentages to exactly 2 decimal places. Survey `officeqa_full.csv` answer column BEFORE writing rules. |
| **TS-6** | **Per-Question Filesystem Scratch Space** | `./scratch/{uid}/` with `evidence.txt`, `tables.txt`, `extracted_values.txt`, `calc.txt`, `verification.txt`, `answer.txt`. Enables verifier access and reproducibility. |
| **TS-7** | **A2A HTTP Endpoint** (`POST /run`) | FastAPI endpoint accepting `{uid, question}`, returning `{uid, answer}`. Exact schema must be confirmed from AgentBeats GitHub before implementation. |

**Build order for table stakes:** TS-1 → TS-2 → TS-3 → TS-4 → TS-5 → TS-6 → TS-7 (each depends on the prior)

---

## Differentiating Features (what wins hard questions)

These features address the top quartile of difficulty (~20% of questions). Without them, the agent will fail multi-hop, multi-file, and statistically complex questions.

| ID | Feature | What It Solves |
|----|---------|---------------|
| **D-1** | **Verifier Subagent** | Independently re-checks evidence coverage, unit consistency, arithmetic correctness, and answer precision. On FAIL, main agent retries. Makes verification mandatory via `verification_token` gate on `normalize_answer`. |
| **D-2** | **Era-Aware Column Header Resolver** | "National defense" (1940) vs "National defense and associated activities" (1953) — same series, different label. Curated series-name variant mapping + prompt strategy for label-agnostic column lookup. |
| **D-3** | **Monthly-vs-Annual Row Discriminator** | Regex identifies month-name rows vs "Total"/"Annual" rows. Required when questions say "using only the reported values for all individual calendar months" — annual total row differs due to revisions. |
| **D-4** | **Statistical Formula Library** | Pre-validated tool implementations for geometric mean, CAGR, OLS slope/intercept, Box-Cox, Theil index, Zipf, KL divergence, VaR, exponential smoothing. LLM calls tools — never generates formulas inline. |
| **D-5** | **Cross-Bulletin Continuity Resolver** | For questions spanning 3–10 bulletin issues (e.g. "sum 1950–1955"), retrieves the same series from each file and handles table-ID and section-heading changes across bulletin eras. |

**Build order for differentiators (after all TS features):** D-3 → D-2 → D-1 → D-4 → D-5

---

## Critical Pitfalls (severity: Critical only)

Ten pitfalls rated Critical — each will directly tank benchmark score if not prevented.

| # | Pitfall | Prevention |
|---|---------|-----------|
| **P-1** | **Wrong document/table selected** — "Table FD-2" appears in every monthly issue; BM25 without date pre-filtering returns results from random years | File router MUST run first and hard-filter to matching bulletin months. Verifier checks that source file year matches question year. |
| **P-2** | **Unit convention mismatch (millions vs thousands)** — treasury tables change unit conventions across decades; silent off-by-1,000x errors | Table extractor must capture footnotes (unit metadata). `extracted_values.txt` records unit per value. Calculator rejects mixed-unit inputs with a hard assert. |
| **P-3** | **Identical table names across 697 files** — BM25 scores "Table FD-2" equally across all files; without pre-filtering, top-k spans are from random years | Two-stage architecture is mandatory: file router FIRST, then BM25 within candidates. BM25 never runs on the full corpus for date-scoped questions. |
| **P-4** | **Skipping verification step** — agent produces arithmetic result and immediately emits answer, bypassing verifier | `normalize_answer` tool requires a `verification_token` argument produced only by the verifier. Without it, normalizer raises an error — verification cannot be skipped. |
| **P-5** | **Wrong percent-change formula** — LLM computes `(new-old)/new` instead of `(new-old)/old` | Hard-code `pct_change(old, new)` as a named tool. LLM never generates this formula inline. System prompt explicitly prohibits inline percent-change. Verifier confirms formula direction. |
| **P-6** | **Unit confusion in arithmetic** — one addend in millions, one in thousands; sum is off by 1,000x for one term | Calculator asserts `len(set(units)) == 1` before any arithmetic. LLM must call `normalize_units()` first. Calculator fails loudly on mismatch. |
| **P-7** | **Number format mismatch** — benchmark answer is `"2,602"`, agent returns `"2602"` or `"$2,602 million"` | Analyze `answer` column of both CSV files BEFORE writing normalizer. Normalizer is rule-based: integers get comma separator, no currency, no decimal; percentages get exactly 2 decimal places. |
| **P-8** | **Trailing zero inconsistency** — benchmark expects `"1608.80%"`, agent returns `"1608.8%"` | All percentage formatting uses `f"{value:.2f}%"`. LLM never formats the final answer string directly. Regex validator in normalizer asserts exactly 2 decimal places for percentages. |
| **P-9** | **Filesystem state leakage between questions** — evidence from question N bleeds into question N+1 if scratch directory is not isolated | Scratch paths namespaced by UID: `scratch/{uid}/`. Assert empty (or create fresh) at question start. Integration test: two back-to-back questions with disjoint answers must not interfere. |
| **P-10** | **Float rounding producing wrong final answer** — `decimal.Decimal` not used, float arithmetic produces `2601.9999999` | All financial arithmetic uses `decimal.Decimal` with `getcontext().prec = 28`. Normalizer rule: integers formatted without decimal point; percentages to exactly 2 decimal places. |

---

## Build Order (phase sequence derived from feature dependencies)

### Phase 1: Environment and Retrieval Foundation
**Rationale:** Nothing can run without Vertex AI auth and the two-stage retrieval pipeline. File router and BM25 search are the entry point for all downstream features. Build and unit-test these before wiring any agent.
**Deliverables:**
- `requirements.txt` installed; Vertex AI credentials verified (`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_VERTEXAI=true`)
- Stub `create_deep_agent` returns static answer (proves SDK imports and auth work)
- `route_files` tool with unit tests on 10 sample questions (year/month extraction, FY-to-calendar mapping)
- `search_in_file` tool with BM25 + regex fallback; correct spans for 5 known question/answer pairs
**Features:** TS-1, TS-2
**Avoids:** P-1 (wrong document), P-3 (identical table names across files)

### Phase 2: Extraction and Calculation Core
**Rationale:** Table extraction, the calculator, and answer normalization form the arithmetic pipeline. All three must be tested together before any agent loop, because errors here are the most common source of wrong answers.
**Deliverables:**
- `extract_table_block` tool with footnote capture (unit metadata preserved)
- `calculate` tool with AST safe eval, `decimal.Decimal`, `pct_change` and `sum_values` named functions
- `normalize_answer` tool built after statistical survey of `answer` column in `officeqa_full.csv`
- Unit test suite for normalizer asserting all known format patterns
**Features:** TS-3, TS-4, TS-5
**Avoids:** P-2 (unit mismatch), P-5 (wrong percent-change formula), P-6 (unit confusion), P-7 (number format), P-8 (trailing zeros), P-10 (float rounding)

### Phase 3: Agent Loop with Scratch Space
**Rationale:** Wire all tools into `create_deep_agent` with `FilesystemMiddleware` and `TodoListMiddleware`. Validate the full retrieval-to-answer pipeline end-to-end on 3+ questions before adding the verifier.
**Deliverables:**
- Full `create_deep_agent` with all 5 tools registered
- `FilesystemBackend(root_dir="./scratch", virtual_mode=False)` wired; scratch files written correctly per question UID
- `TodoListMiddleware` planning for multi-date questions
- End-to-end test: 3 questions produce correct scratch file layout and correct answers
- `max_iterations=12` set; per-tool call counter for infinite-loop guard
**Features:** TS-6
**Avoids:** P-9 (state leakage), P-4 (verification bypass — gated in next phase), infinite retrieval loops

### Phase 4: Verifier Subagent and Reliability Features
**Rationale:** Verifier is the reliability layer that catches unit errors, arithmetic mistakes, and wrong-year retrievals before they reach the benchmark evaluator. Monthly row discriminator and header resolver address the two most common table-level errors.
**Deliverables:**
- Verifier subagent registered via `SubAgentMiddleware`; returns `VerifierResult(status, issues, token)`
- `normalize_answer` gated on `verification_token` — verification cannot be bypassed
- `ERROR` status from verifier treated same as `FAIL`; main agent retries, never emits unverified answer
- D-3: monthly-vs-annual row discriminator regex
- D-2: era-aware column header resolver with series-name variant mapping
**Features:** D-1, D-2, D-3
**Avoids:** P-4 (skipping verification), P-1 (wrong year — verifier checks source file year), P-2 (unit mismatch — verifier checks unit consistency)

### Phase 5: A2A HTTP Server
**Rationale:** HTTP layer is pure wrapping — implement only after the agent is verified to produce correct answers. Confirm the exact A2A request/response schema from the AgentBeats benchmark GitHub repo BEFORE writing Pydantic models.
**Deliverables:**
- FastAPI `POST /run` endpoint; agent created once at startup
- Pydantic models matching confirmed A2A schema exactly
- Integration test: POST sample question, assert response schema matches A2A spec
- LangSmith tracing enabled (`LANGSMITH_API_KEY` + `LANGSMITH_PROJECT`)
**Features:** TS-7
**Avoids:** P-10 (A2A response schema mismatch — confirm spec before coding)

### Phase 6: Hard Questions — Statistical and Multi-File
**Rationale:** Statistical formula library and cross-bulletin continuity resolver target the top-difficulty quartile. Build only after Phase 5 baseline is producing good benchmark scores on standard questions.
**Deliverables:**
- D-4: statistical formula library (geometric mean, CAGR, OLS, Box-Cox, Theil, Zipf, KL divergence, VaR, exponential smoothing) — each with unit test asserting known output
- D-5: cross-bulletin continuity resolver for time-series spanning 3–10 issues
- Full benchmark sweep against `officeqa_full.csv` and `officeqa_pro.csv`; missing corpus files identified
- Vertex AI rate-limit handling: exponential backoff, per-question delay for batch runs
**Features:** D-4, D-5
**Avoids:** Token budget exhaustion (context-budget tracker before each LLM call), rate limit silent degradation

---

## Open Questions (must resolve before coding)

These are unresolved as of research completion. Each blocks a specific phase if unanswered.

| # | Question | Blocks | How to Resolve |
|---|----------|--------|---------------|
| **Q-1** | **What is the exact A2A request/response schema?** Is it `{uid, question}` → `{uid, answer}` or something different? | Phase 5 (A2A endpoint) | Read AgentBeats benchmark GitHub repo before writing Pydantic models or the FastAPI route |
| **Q-2** | **Are all `source_files` in `officeqa_full.csv` present in `corpus/transformed/`?** Missing files will cause silent retrieval failures | Phase 1 (file router) | Run a manifest diff: `set(csv_source_files) - set(corpus_files)` before any development |
| **Q-3** | **BM25 index caching strategy:** build once per file on first access and cache in-memory for the request, or persist to `./scratch/bm25_cache/`? | Phase 1 (search tool) | In-memory per-request is safer for correctness (no stale index); persist only if latency profiling shows rebuild cost is unacceptable |
| **Q-4** | **Do Treasury Bulletin files from 1939 vs 2025 use consistent enough markdown table formatting** for a single `TABLE_LINE = re.compile(r'^\s*\|')` heuristic? | Phase 2 (table extractor) | Manually inspect 5 files from each decade (1939, 1950, 1970, 1990, 2010, 2025) before finalizing the regex |
| **Q-5** | **If `MODEL_ID` is set to a Claude model on Vertex**, does `langchain-google-genai` handle it, or is a different LangChain package required? | Phase 1 (env setup) | Test with a Claude Vertex endpoint in the dev environment; document the correct package if different |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technology choices have clear rationale from official docs and hackathon constraints. The `google-genai` vs `google-cloud-aiplatform` distinction is confirmed. |
| Features | HIGH | Five axes of question difficulty are directly observable in `officeqa_full.csv`. Feature dependencies are deterministic (TS-1 → TS-2 → TS-3, etc.). |
| Architecture | HIGH | `create_deep_agent` pattern with middleware is documented. Two-stage retrieval design is the only viable approach for 697-file corpus without embeddings. |
| Pitfalls | HIGH | All Critical pitfalls are grounded in observable corpus properties (697 files, identical table names, decade-spanning unit changes) and benchmark format constraints (exact string match). |

**Overall confidence:** HIGH

### Gaps to Address

- **A2A schema (Q-1):** Cannot finalize Phase 5 without reading the benchmark spec. Do this on day 1.
- **Corpus completeness (Q-2):** Missing files produce silent failures late in development. Run the manifest diff before writing any retrieval code.
- **Table format consistency across decades (Q-4):** The table extractor regex is assumed to work across 1939–2025. Spot-check 5 files per decade before committing to the implementation.

---

*Research completed: 2026-03-17*
*Ready for roadmap: yes*
