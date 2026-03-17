# Requirements: AgentBeats OfficeQA Finance Agent

**Defined:** 2026-03-17
**Core Value:** Every answer must be traceable to a specific sentence or table cell in the local corpus — no hallucination, no web search, exact arithmetic.

## v1 Requirements

### Environment

- [ ] **ENV-01**: System reads `MODEL_ID` env var (default: `gemini-2.0-flash`) and routes to the correct LangChain model adapter at startup — no code change required to swap models
- [ ] **ENV-02**: System supports Gemini models on Vertex AI via `google-genai` + `langchain-google-genai` when `MODEL_ID` is a `gemini-*` model string
- [ ] **ENV-03**: System supports Anthropic Claude models on Vertex AI via `langchain-google-vertexai`'s `ChatAnthropicVertex` when `MODEL_ID` is a `claude-*` model string (e.g. `claude-sonnet-4-6`)
- [ ] **ENV-04**: Model adapter layer normalizes message format and function-calling schema differences between Gemini and Claude so all tools work identically regardless of which model is active
- [ ] **ENV-05**: GCP credentials configured via `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`, `GOOGLE_GENAI_USE_VERTEXAI=true` (Gemini) and `GOOGLE_APPLICATION_CREDENTIALS` (Claude via Vertex)
- [ ] **ENV-06**: Corpus manifest check runs at startup: validates all `source_files` referenced in `officeqa_full.csv` and `officeqa_pro.csv` exist in `corpus/transformed/`; logs missing files as warnings

### Retrieval

- [ ] **RET-01**: File router (`route_files`) extracts calendar year(s), fiscal year(s), and topic keywords from a question using regex/stdlib — no LLM call — and returns 1–5 candidate `treasury_bulletin_YYYY_MM.txt` absolute paths
- [ ] **RET-02**: File router correctly maps fiscal year questions (e.g. "FY 1940") to the corresponding calendar months (FY ends September 30); maps "FY1999" to October 1998 – September 1999 files
- [ ] **RET-03**: File router validates all returned paths against the corpus manifest and returns a structured error if a path does not exist (no hallucinated filenames)
- [ ] **RET-04**: BM25 in-file search (`search_in_file`) builds a `BM25Okapi` index over non-overlapping 20-line spans of the candidate file, preserving table block boundaries (lines starting with `|` are never span boundaries)
- [ ] **RET-05**: BM25 in-file search returns top-5 ranked spans as plain text strings; falls back to regex search if BM25 returns zero results for a query containing a numeric value or fiscal-year abbreviation
- [ ] **RET-06**: BM25 query normalization: expands "FY95" → "fiscal year 1995", strips commas from numbers, normalizes dash variants before indexing and querying

### Extraction

- [ ] **EXT-01**: Table block extractor (`extract_table_block`) locates the first pipe-delimited table block within 15 lines of an anchor phrase (case-insensitive) and returns the complete block including header rows, separator row, data rows, and footnote rows
- [ ] **EXT-02**: Table block extractor never truncates before footnote rows — footnotes carry unit metadata ("In thousands", "Amounts in millions of dollars") required for correct arithmetic
- [ ] **EXT-03**: Monthly-vs-annual row discriminator (`classify_table_rows`) accepts a raw table block and returns two lists: rows labeled with individual month names (January–December) and rows labeled with "Total", "Annual", or similar aggregate labels
- [ ] **EXT-04**: When a question contains the phrase "using specifically only the reported values for all individual calendar months", the agent uses the monthly row list only and explicitly excludes aggregate rows

### Calculation

- [ ] **CAL-01**: Python AST calculator (`calculate`) evaluates arithmetic expressions using `decimal.Decimal` with `getcontext().prec = 28`; permits only numeric literals, +, -, *, /, ** and parentheses; rejects all function calls, attribute access, and imports via AST whitelist
- [ ] **CAL-02**: Calculator exposes a named `pct_change` operation: `(new - old) / old * 100`; the LLM calls this as a tool argument pattern, never generates the formula inline
- [ ] **CAL-03**: Calculator exposes a named `sum_values` operation that accepts an explicit list of `(label, value)` pairs and logs the pair count before summing; returns an error if the pair count does not match the expected count passed by the caller
- [ ] **CAL-04**: Calculator rejects any arithmetic where input values carry different units (e.g. one in millions, one in thousands); returns a structured error requiring the caller to normalize units first
- [ ] **CAL-05**: Answer normalizer (`normalize_answer`) is rule-based (not LLM-generated); formats integers with comma thousands separators and no decimal point or currency symbol; formats percentages to exactly 2 decimal places with `%` suffix using `f"{value:.2f}%"` — trailing zeros are preserved
- [ ] **CAL-06**: Answer normalizer is built after a statistical survey of the `answer` column in `officeqa_full.csv` and `officeqa_pro.csv`; a test suite asserts `normalize(raw) == expected` for all distinct answer format patterns observed in the survey
- [ ] **CAL-07**: Statistical formula library (`stat_tools`) provides pre-validated Python implementations callable as agent tools: geometric mean, CAGR, OLS slope and intercept, Box-Cox transformation, Theil inequality index, Zipf law fit, KL divergence, VaR (historical), exponential smoothing (ETS); each formula has a unit test asserting known output for a known input

### Agent Orchestration

- [ ] **AGT-01**: Main agent is constructed with `create_deep_agent` using `FilesystemMiddleware` (`FilesystemBackend(root_dir="./scratch", virtual_mode=False)`), `TodoListMiddleware`, and `SubAgentMiddleware`
- [ ] **AGT-02**: Agent uses `MemorySaver` checkpointer with `thread_id` set to the question UID; re-running the same UID starts a fresh thread and overwrites prior scratch files
- [ ] **AGT-03**: Agent is configured with `max_iterations=12`; a per-tool call counter in each tool wrapper returns `RETRIEVAL_EXHAUSTED` if any single tool is called more than 4 times within one question
- [ ] **AGT-04**: System prompt instructs the agent: (1) always write a plan with `write_todos` before first retrieval, (2) call `verify_answer` before `normalize_answer`, (3) never generate arithmetic formulas inline — always use named tools, (4) percent change is always `(new - old) / old × 100` — always use `pct_change` tool

### Scratch Space

- [ ] **SCR-01**: Each question gets an isolated directory `./scratch/{uid}/` created at the start of processing; the directory is asserted empty (or freshly created) before processing begins to prevent cross-question state contamination
- [ ] **SCR-02**: Scratch space contains: `evidence.txt` (BM25 spans, one section per source file), `tables.txt` (raw table blocks), `extracted_values.txt` (named values: `key = value (unit)`), `calc.txt` (expression + result per step), `verification.txt` (verifier report), `answer.txt` (final normalized answer)
- [ ] **SCR-03**: All extracted numeric values written to `extracted_values.txt` include unit metadata alongside the value: `defense_1940 = 2602 (millions)`

### Verification

- [ ] **VER-01**: Verifier subagent is registered via `SubAgentMiddleware` with name `"verifier"`; it is stateless — the main agent passes all evidence paths and the proposed answer in a single `task()` call
- [ ] **VER-02**: Verifier checks all four dimensions: (a) evidence coverage — every value used in calculation has a corresponding span in `evidence.txt`; (b) unit consistency — all arithmetic inputs carry the same unit; (c) arithmetic correctness — re-executes the calculation expression; (d) answer format — proposed answer matches normalizer format rules
- [ ] **VER-03**: Verifier returns a structured result: `status` ("PASS"|"FAIL"|"ERROR"), `issues` (list of strings), `token` (non-null only on PASS)
- [ ] **VER-04**: `normalize_answer` tool requires a `verification_token` argument; it raises an error if the token is absent or null — verification cannot be bypassed
- [ ] **VER-05**: Main agent on verifier `FAIL` or `ERROR`: retries retrieval or recalculation; never emits an unverified answer; returns a standardized "cannot determine" response after 2 failed verification attempts
- [ ] **VER-06**: Era-aware column header resolver provides a curated mapping of known series name variants across bulletin eras (e.g. "National defense" → "National defense and associated activities"); the verifier uses this mapping when checking evidence coverage for multi-era questions

### HTTP Interface

- [ ] **HTTP-01**: FastAPI server exposes `POST /run` endpoint; the agent is created once at application startup — not per-request
- [ ] **HTTP-02**: Request and response Pydantic models match the exact A2A schema confirmed from the AgentBeats benchmark GitHub repository (schema must be verified before this requirement is implemented)
- [ ] **HTTP-03**: Re-submitting the same `uid` produces the same answer (reproducible); the endpoint is idempotent with respect to the corpus
- [ ] **HTTP-04**: LangSmith tracing is enabled when `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` env vars are set; all LLM calls and tool invocations are traced per question UID

### Multi-File Time Series

- [ ] **MFS-01**: Cross-bulletin continuity resolver (`resolve_time_series`) accepts a date range and a series name; it invokes `route_files` for each sub-period, searches for the series in each file, and handles table-ID and section-heading changes across bulletin eras by using the era-aware header resolver
- [ ] **MFS-02**: Cross-bulletin continuity resolver detects gaps (years where the series is missing or renamed) and reports them as warnings in `evidence.txt` rather than silently returning an incomplete sum

### Testing

- [ ] **TST-01**: Each tool module has a co-located unit test file (`tests/test_*.py`) written alongside the implementation; tests assert correct output for at least 5 known inputs including edge cases
- [ ] **TST-02**: File router unit tests cover: calendar year extraction, fiscal year → calendar month mapping, topic-keyword fallback, unknown year handling
- [ ] **TST-03**: Calculator unit tests cover: basic arithmetic, `pct_change` direction, `sum_values` count mismatch error, unit mismatch rejection, Decimal precision for known financial values, all 9 statistical formula implementations
- [ ] **TST-04**: Answer normalizer unit tests assert `normalize(raw) == expected` for every distinct format pattern observed in the `officeqa_full.csv` answer column survey
- [ ] **TST-05**: Integration test posts 10 sample questions to `POST /run` and asserts both the answer string and the A2A response schema
- [ ] **TST-06**: State isolation test: runs two back-to-back questions with disjoint answers and asserts that scratch files for question N do not contain any reference to question N-1's source files or values

## v2 Requirements

### Retrieval Enhancements

- **RET-V2-01**: Cross-decade BM25 normalization improvements (domain-specific stopword IDF suppression for "Treasury", "Department", "Table", "fiscal year")
- **RET-V2-02**: Persistent BM25 index cache (`./scratch/bm25_cache/`) to reduce per-request latency on repeated file lookups

### Performance

- **PERF-V2-01**: Per-question Vertex AI rate-limit handling: exponential backoff (max 3 retries, jitter), per-question delay for batch evaluation runs
- **PERF-V2-02**: `FAST_MODE=true` env var to skip verifier subagent for latency-sensitive runs
- **PERF-V2-03**: Context-budget tracker: before each LLM call, estimate token count; compress older evidence spans when approaching 80% of model context window

### Observability

- **OBS-V2-01**: Per-question latency breakdown logging (file router, BM25, table extraction, calculator, verifier, normalizer) to identify bottlenecks

## Out of Scope

| Feature | Reason |
|---------|--------|
| Vector embeddings (FAISS, Chroma, Pinecone) | BM25 + regex sufficient; adds GPU/cost overhead and setup complexity |
| Web search during inference (Tavily, etc.) | Strict corpus-grounding constraint; all evidence must come from `corpus/transformed/` |
| Hardcoded UID-keyed answers | Benchmark-unsafe; fails on held-out questions |
| `google-cloud-aiplatform` SDK | Deprecated; replaced by `google-genai` |
| Mobile/browser UI | Pure API/CLI; out of scope |
| Streaming HTTP responses | Benchmark evaluator expects complete `answer` field |
| Direct OpenAI or Anthropic API keys | All LLM calls must go through Vertex AI only |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENV-01 through ENV-06 | Phase 1 | Pending |
| RET-01 through RET-06 | Phase 1 | Pending |
| EXT-01 through EXT-04 | Phase 2 | Pending |
| CAL-01 through CAL-07 | Phase 2 | Pending |
| AGT-01 through AGT-04 | Phase 3 | Pending |
| SCR-01 through SCR-03 | Phase 3 | Pending |
| VER-01 through VER-06 | Phase 4 | Pending |
| HTTP-01 through HTTP-04 | Phase 5 | Pending |
| MFS-01 through MFS-02 | Phase 6 | Pending |
| TST-01 through TST-06 | Spans phases 1–6 | Pending |

**Coverage:**
- v1 requirements: 44 total
- Mapped to phases: 44
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-17*
*Last updated: 2026-03-17 after initial definition*
