# Roadmap: AgentBeats OfficeQA Finance Agent

## Overview

Starting from a bare environment, each phase adds one complete capability layer: retrieval foundation, arithmetic pipeline, agent loop with scratch isolation, reliability via verifier, A2A HTTP wrapper, and finally the statistical/multi-file tools that target the hardest benchmark questions. Nothing is wired to the benchmark until Phase 5; everything is testable in isolation before it is composed.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Environment + Retrieval Foundation** - Vertex AI auth, file router, BM25 in-file search — the entry point for all downstream tools
- [ ] **Phase 2: Extraction + Calculation Core** - Table block extractor, AST calculator with named operations, rule-based answer normalizer
- [ ] **Phase 3: Agent Loop + Scratch Space** - Wire all tools into `create_deep_agent` with filesystem scratch isolation per question UID
- [ ] **Phase 4: Verifier Subagent + Reliability** - Mandatory verification gate, monthly-row discriminator, era-aware header resolver
- [ ] **Phase 5: A2A HTTP Server** - FastAPI `POST /run` endpoint, confirmed A2A schema, LangSmith tracing
- [ ] **Phase 6: Hard Questions — Statistical + Multi-File** - Advanced statistical formula library, cross-bulletin continuity resolver

---

## Phase Details

### Phase 1: Environment + Retrieval Foundation
**Goal**: The project runs against Vertex AI and retrieves the correct candidate spans from the corpus for any date-scoped question
**Depends on**: Nothing (first phase)
**Requirements**: ENV-01, ENV-02, ENV-03, ENV-04, ENV-05, ENV-06, RET-01, RET-02, RET-03, RET-04, RET-05, RET-06, TST-01, TST-02
**Success Criteria** (what must be TRUE):
  1. Running the stub agent with `MODEL_ID=gemini-2.0-flash` returns a static answer without an authentication error — Vertex AI credentials are valid
  2. Running the stub agent with `MODEL_ID=claude-sonnet-4-6` also returns without error — both Gemini and Claude adapters work, tool schemas are identical regardless of model
  3. `route_files("FY 1940 defense expenditures")` returns absolute paths to the October 1939 – September 1940 bulletin files and no hallucinated paths
  4. `search_in_file(path, "defense expenditures 1940")` returns the top-5 ranked 20-line spans covering the correct table rows, with the regex fallback activating on a numeric-only query
  5. Startup corpus manifest check logs zero missing files (or logs a specific warning for each missing file rather than silently succeeding)
**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md — Environment setup: requirements.txt, Vertex AI credential wiring, model adapter factory, corpus manifest check
- [ ] 01-02-PLAN.md — File router (route_files): year/FY extraction, fiscal-to-calendar mapping, path validation, unit tests
- [ ] 01-03-PLAN.md — BM25 in-file search (search_in_file): span indexing with table-boundary preservation, query normalization, regex fallback, unit tests

### Phase 2: Extraction + Calculation Core
**Goal**: The arithmetic pipeline produces exact, correctly-formatted answers from raw corpus text with no float rounding errors and no unit confusion
**Depends on**: Phase 1
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04, CAL-01, CAL-02, CAL-03, CAL-04, CAL-05, CAL-06, TST-03, TST-04
**Success Criteria** (what must be TRUE):
  1. `extract_table_block(span_text, "defense expenditures")` returns the complete table including header rows, separator row, data rows, and footnote rows — the unit annotation ("In millions") is present in the output
  2. `classify_table_rows(table_block)` correctly separates month-name rows from "Total"/"Annual" rows for a real bulletin table; when the question asks for "only individual calendar months", the agent uses only the month-name list
  3. `calculate("pct_change(2602, 3100)")` returns the correct percentage using `decimal.Decimal`; passing inputs with mismatched units returns a structured error rather than a silent wrong answer
  4. `normalize_answer(raw)` produces exact benchmark-format strings for every distinct pattern observed in the `officeqa_full.csv` answer column — integers have comma separators, percentages have exactly two decimal places with trailing zeros preserved
  5. Unit test suite passes for all calculator operations (arithmetic, `pct_change`, `sum_values` count mismatch, unit mismatch rejection) and all normalizer format patterns
**Plans:** 3 plans

Plans:
- [ ] 02-01-PLAN.md — Table block extractor (extract_table_block) + row classifier (classify_table_rows) with unit tests
- [ ] 02-02-PLAN.md — AST calculator (calculate) with decimal.Decimal, pct_change, sum_values, unit mismatch rejection, and full unit test suite
- [ ] 02-03-PLAN.md — Format survey fixture + answer normalizer (normalize_answer) built from survey results; parametrized tests for all format patterns

### Phase 3: Agent Loop + Scratch Space
**Goal**: The full retrieval-to-answer pipeline runs end-to-end through the agent with isolated per-question scratch files and an infinite-loop guard
**Depends on**: Phase 2
**Requirements**: AGT-01, AGT-02, AGT-03, AGT-04, SCR-01, SCR-02, SCR-03
**Success Criteria** (what must be TRUE):
  1. Running a sample question end-to-end creates `./scratch/{uid}/` containing all six expected files (`evidence.txt`, `tables.txt`, `extracted_values.txt`, `calc.txt`, `verification.txt`, `answer.txt`) — each with non-empty content
  2. Every numeric value in `extracted_values.txt` includes its unit alongside the value (e.g., `defense_1940 = 2602 (millions)`)
  3. Running the same question UID a second time overwrites the prior scratch directory without raising an error and produces the same answer
  4. Calling any single tool more than 4 times in one question returns `RETRIEVAL_EXHAUSTED` — the agent does not loop indefinitely
  5. The agent writes a `write_todos` plan before first retrieval on every question; the system prompt constraint is visibly enforced in the trace
**Plans**: TBD

Plans:
- [ ] 03-01: `create_deep_agent` wiring — `FilesystemMiddleware`, `TodoListMiddleware`, all tools registered, `MemorySaver` checkpointer, `thread_id` = question UID
- [ ] 03-02: Scratch space layout — per-UID directory lifecycle, all six file writers, unit metadata enforcement in `extracted_values.txt`
- [ ] 03-03: System prompt + iteration controls — `max_iterations=12`, per-tool call counter, `write_todos` pre-retrieval rule, `pct_change`-only percent change rule; end-to-end smoke test on 3 questions

### Phase 4: Verifier Subagent + Reliability
**Goal**: No answer reaches the normalizer without passing a four-dimension independent verification — evidence coverage, unit consistency, arithmetic correctness, and format match
**Depends on**: Phase 3
**Requirements**: VER-01, VER-02, VER-03, VER-04, VER-05, VER-06
**Success Criteria** (what must be TRUE):
  1. Calling `normalize_answer` without a `verification_token` raises an error — verification cannot be bypassed at the code level, not just by convention
  2. The verifier subagent returns `status: PASS` with a non-null `token` for a correctly-answered sample question; it returns `status: FAIL` with a specific `issues` list when given an answer where units are mismatched
  3. When the verifier returns `FAIL` or `ERROR`, the main agent retries retrieval or recalculation; after two failed attempts it returns a standardized "cannot determine" response rather than emitting an unverified answer
  4. A multi-era question (series name changed between decades) resolves correctly because the era-aware column header resolver maps both label variants to the same evidence span
**Plans**: TBD

Plans:
- [ ] 04-01: Verifier subagent — `SubAgentMiddleware` registration, four-dimension checks (evidence coverage, unit consistency, arithmetic re-execution, format match), `VerifierResult` schema
- [ ] 04-02: Verification gate on `normalize_answer` — `verification_token` argument, token generation on PASS only, error on absent token
- [ ] 04-03: Retry logic + era-aware header resolver — main agent FAIL/ERROR handling, "cannot determine" fallback after 2 attempts, curated series-name variant mapping

### Phase 5: A2A HTTP Server
**Goal**: The agent is reachable via a single `POST /run` HTTP endpoint whose request/response schema exactly matches the AgentBeats A2A specification
**Depends on**: Phase 4
**Requirements**: HTTP-01, HTTP-02, HTTP-03, HTTP-04, TST-05, TST-06
**Success Criteria** (what must be TRUE):
  1. `POST /run` with a valid `{uid, question}` payload returns a response that passes schema validation against the confirmed A2A spec — no extra fields, no missing fields
  2. Posting the same `uid` twice returns the same `answer` string both times — the endpoint is idempotent
  3. An integration test posting 10 sample questions all return HTTP 200 with correct A2A schema and non-empty answer strings
  4. When `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` are set, every LLM call and tool invocation appears as a distinct span in the LangSmith trace for the corresponding question UID
  5. A state isolation test confirms that scratch files for question N contain no filenames or values from question N-1
**Plans**: TBD

Plans:
- [ ] 05-01: Confirm A2A schema from AgentBeats benchmark GitHub repo; define Pydantic request/response models
- [ ] 05-02: FastAPI server — `POST /run` endpoint, agent created once at startup, LangSmith tracing wiring
- [ ] 05-03: Integration tests — 10-question schema assertion, idempotency test, state isolation test

### Phase 6: Hard Questions — Statistical + Multi-File
**Goal**: The agent correctly answers the top-difficulty questions requiring statistical formulas or multi-bulletin time-series aggregation
**Depends on**: Phase 5
**Requirements**: CAL-07, MFS-01, MFS-02
**Success Criteria** (what must be TRUE):
  1. Each of the 9 statistical tool functions (geometric mean, CAGR, OLS slope/intercept, Box-Cox, Theil index, Zipf fit, KL divergence, VaR, exponential smoothing) has a passing unit test asserting known output for a known input — the LLM calls them as tools and never generates these formulas inline
  2. `resolve_time_series("national defense", "1950", "1955")` retrieves the correct series from each of the 6 annual bulletin files, handles any table-heading rename across that span, and returns a complete value list with no silent gaps
  3. When a year's series is missing or renamed in the corpus, `resolve_time_series` emits a warning entry in `evidence.txt` rather than silently returning a sum that excludes that year
**Plans**: TBD

Plans:
- [ ] 06-01: Statistical formula library (`stat_tools`) — 9 formula implementations with unit tests, registered as agent tools
- [ ] 06-02: Cross-bulletin continuity resolver (`resolve_time_series`) — date-range iteration over `route_files`, era-aware header resolver integration, gap detection and warning emission

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Environment + Retrieval Foundation | 3/3 | Complete | 2026-03-18 |
| 2. Extraction + Calculation Core | 3/3 | Complete | 2026-03-18 |
| 3. Agent Loop + Scratch Space | 0/3 | Not started | - |
| 4. Verifier Subagent + Reliability | 0/3 | Not started | - |
| 5. A2A HTTP Server | 0/3 | Not started | - |
| 6. Hard Questions — Statistical + Multi-File | 0/2 | Not started | - |

---
*Roadmap created: 2026-03-17*
*Last updated: 2026-03-18 after Phase 2 execution*
