# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Every answer must be traceable to a specific sentence or table cell in the local corpus — no hallucination, no web search, exact arithmetic.
**Current focus:** Phase 5.1 — Enhance Agent Prompts, Tools and AgentBeats A2A Integration

## Current Position

Phase: 5.1 of 6 (Enhance Agent Prompts, Tools and AgentBeats A2A Integration) — IN PROGRESS
Plan: 2 of 3 complete in Phase 5.1 (05.1-01, 05.1-02 complete)
Status: Phase 5.1 Plan 02 complete — A2AStarletteApplication replaces FastAPI /run; OfficeQAAgentExecutor wraps run_question(); agent card + JSON-RPC + /health exposed.
Last activity: 2026-03-21 — Phase 5.1 Plan 02 complete (2 tasks, 3 files)

Progress: [█████████░] 85%

## Performance Metrics

**Velocity:**
- Total plans completed: 15 (Phase 1: 01-01, 01-02, 01-03 | Phase 2: 02-01, 02-02, 02-01-retroactive, 02-03 | Phase 3: 03-01, 03-02 | Phase 3.1: 03.1-01, 03.1-02, 03.1-03 | Phase 4: 04-01, 04-02, 04-03) — 03-03 at checkpoint
- Total execution time: 6 sessions

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| 1: Environment + Retrieval Foundation | 3/3 | Complete |
| 2: Extraction + Calculation Core | 3/3 | Complete |
| 3: Agent Loop + Scratch Space | 2/3 + checkpoint | In progress (03-03 awaiting human-verify) |
| 3.1: Architecture Refactor | 3/3 | Complete |
| 5: A2A HTTP Server | 2/2 | Complete |
| 5.1: Enhance Agent Prompts + Tools | 2/3 | In progress |

**Execution Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 02-extraction-calculation-core P01 | 45min | 2 tasks | 6 files |
| Phase 02-extraction-calculation-core P02 | 35min | 2 tasks | 2 files |
| Phase 02-extraction-calculation-core P03 | 25min | 2 tasks | 4 files |
| Phase 03-agent-loop-scratch-space P01 | 13min | 2 tasks | 12 files |
| Phase 03-agent-loop-scratch-space P03 | 7min | 2 tasks (partial) | 4 files |

| Phase 03.1-architecture-refactor P01 | 12min | 2 tasks | 11 files |
| Phase 03.1-architecture-refactor P02 | 6min | 2 tasks | 3 files |
| Phase 03.1-architecture-refactor P03 | 15min | 2 tasks | 4 files |
| Phase 04-verifier-subagent-reliability P02 | 5min | 1 task | 1 file |
| Phase 04-verifier-subagent-reliability P03 | 60min | 3 tasks | 3 files |
| Phase 05-a2a-http-server P01 | 5min | 2 tasks | 3 files |

*Updated after each plan completion*
| Phase 05-a2a-http-server P02 | 15min | 3 tasks (2 auto + 1 human-verify) | 4 files |
| Phase 05.1-enhance-agent-prompts-tools-and-agentbeats-a2a-integration P01 | 4min | 2 tasks | 6 files |
| Phase 05.1-enhance-agent-prompts-tools-and-agentbeats-a2a-integration P02 | 15min | 2 tasks | 3 files |

## Accumulated Context

### Roadmap Evolution

- Phase 3.1 inserted after Phase 3: Architecture Refactor: Deep Agent Native Tools + Model-Agnostic Pipeline (URGENT)
- Phase 5.1 inserted after Phase 5: Enhance agent prompts, tools and AgentBeats A2A integration (URGENT)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: CAL-07 split — basic calculator operations (pct_change, sum_values) delivered in Phase 2 via CAL-02/CAL-03; advanced statistical formulas (CAGR, OLS, Box-Cox, etc.) deferred to Phase 6 where they are needed for hard questions
- [Roadmap]: Phase 2 begins with a format survey of `officeqa_full.csv` answer column before any normalizer code is written — prevents format mismatch failures late
- [Phase 02-extraction-calculation-core]: Calculator: SAFE_NODES frozenset rejects Call/Attribute/Name/Import — only literal arithmetic allowed
- [Phase 02-extraction-calculation-core]: pct_change: unit check skipped when either unit arg is None or empty string — unlabeled values pass through
- [Phase 02-extraction-calculation-core]: sum_values: warns (unit_warning) on heterogeneous units but does not reject the sum
- [Phase 02-01]: Aggregate detection applied first (higher specificity) — 1940 Total, Cal. yr, cumulative -> aggregate bucket, not month
- [Phase 02-01]: parse_cell_value is module-level in classify_table_rows.py — importable by Phase 3 calculator
- [Phase 02-01]: pytest.ini: -p no:anyio etc. needed to suppress Anaconda entrypoint loading errors in this venv
- [Phase 02-extraction-calculation-core]: normalize_answer: pass-through design — 8-step decision tree identifies format type, returns cleaned string unchanged; benchmark format IS expected format
- [Phase 02-extraction-calculation-core]: format_survey.json as living fixture: parametrized tests load it — adding examples automatically adds tests; verified against 258 unique answers from both CSVs
- [Phase 03-01]: @tool decorator — name arg must be positional: tool("name")(fn) not @tool(name="name") [SUPERSEDED by Phase 03.1]
- [Phase 03-01]: Wrapper pattern: original functions renamed _impl, StructuredTool aliases registered [SUPERSEDED by Phase 03.1 — plain functions used directly]
- [Phase 03-01]: route_files needs thin _route_files_agent wrapper (no config param) [SUPERSEDED by Phase 03.1 — _CORPUS_DIR env var]
- [Phase 03-01]: Optional[str] required for pct_change unit_old/unit_new — Pydantic V2 rejects None [SUPERSEDED by Phase 03.1 — no Pydantic wrapper]
- [Phase 03-01]: Tests for invalid-type inputs call _impl directly [SUPERSEDED by Phase 03.1 — call plain functions directly]
- [Phase 03-03]: run_question_with_messages() added to agent.py — exposes message list for ToolMessage ordering assertions without breaking run_question signature
- [Phase 03-03]: Integration test Q selection: Q1=UID0001 (1940 defense lookup), Q2=UID0004 (pct_change), Q3=UID0003 (table sum)
- [Phase 03-03]: ToolMessage ordering test uses getattr(msg, 'name', None) — compatible across langchain_core versions
- [Phase 03.1]: Tools exported as plain functions — no @tool decorator, no StructuredTool
- [Phase 03.1]: route_files reads CORPUS_DIR from env via module-level _CORPUS_DIR constant
- [Phase 03.1]: get_model reads MODEL_ID from env directly, no Config param
- [Phase 03.1]: retrieval_wrappers.py deleted — Deep Agents max-turns replaces counter wrappers
- [Phase 03.1]: SYSTEM_PROMPT rewritten without RETRIEVAL_EXHAUSTED references
- [Phase 03.1]: create_agent() has no parameters — calls get_model() with no args which reads env at call time
- [Phase 03.1]: model-switch integration test added — asserts both gemini-2.0-flash and claude-sonnet-4-6 produce non-empty answers for same question
- [Phase 04-02]: verification_token has no default value — Pydantic/JSON schema marks it required, LLM cannot omit it (Pitfall 2)
- [Phase 04-02]: Falsy token raises ValueError (not error dict) — absent token is a programming error (bypass attempt), not a runtime data problem
- [Phase 04-02]: Verification gate is first check in function body, before all other validation — cannot be bypassed by passing bad raw input first
- [Phase 04-03]: test_normalize_answer.py updated via AST-based bracket-depth-tracking replacement — handles commas inside arguments (list literals, comma-decimals, date strings) correctly where naive regex failed
- [Phase 04-03]: test_smoke_verification_txt_is_stub renamed to test_smoke_verification_txt_has_records — checks PASS/FAIL/Status:/Attempt indicators instead of "pending"/"Phase 4" stub
- [Phase 05-01]: asyncio primitives (Semaphore, Lock) created inside lifespan(), never at module level — avoids Python 3.10+ DeprecationWarning
- [Phase 05-01]: get_model() called once in lifespan startup and stored in _app_state["model"] — LLM object shared across requests (HTTP-01); agent graph still created per-request for MemorySaver isolation
- [Phase 05-01]: Idempotency cache checked BEFORE acquiring UID lock and semaphore — avoids holding concurrency slots for cache hits (fast path)
- [Phase 05-01]: ErrorResponse uid field omitted entirely (not null) when uid not parseable from malformed request body
- [Phase 05-01]: LangSmith tracing activated via env vars only (LANGSMITH_TRACING=true) — no code wiring in server.py
- [Phase 05-02]: asgi-lifespan LifespanManager required for FastAPI lifespan in httpx tests — ASGITransport alone does not trigger startup events
- [Phase 05-02]: Patch src.agent.run_question not src.server.run_question — server imports at function call time
- [Phase 05-02]: anyio plugin re-enabled in pytest.ini — removed -p no:anyio so @pytest.mark.anyio works
- [Phase 05-02]: AGENT_TIMEOUT_SECONDS needs tuning for production — default is low (suited for mocked tests); real Vertex AI runs require 120–300s; live smoke test correctly returned 504 (expected behavior, not a bug)
- [Phase 05.1]: FY Adjacency Rule inserted in SYSTEM_PROMPT — agent must call route_files twice for FY N questions (year N + year N+1)
- [Phase 05.1]: Parallel Search Rule added to SYSTEM_PROMPT — search_in_file must be called for all paths in a single turn
- [Phase 05.1-02]: AgentCard uses snake_case Pydantic fields (default_input_modes, default_output_modes) — not camelCase
- [Phase 05.1-02]: A2AStarletteApplication.build(routes=[...]) passes routes kwarg to Starlette constructor — correct way to add /health
- [Phase 05.1-02]: context.get_user_input() is the SDK helper for extracting text from A2A message parts — replaces manual TextPart traversal
- [Phase 05.1-02]: a2a-sdk[http-server] extra required for sse-starlette — base install raises ImportError at A2AStarletteApplication init

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Open question Q-2 — run corpus manifest diff (`set(csv_source_files) - set(corpus_files)`) before writing any retrieval code to surface missing files early
- [Phase 1]: Open question Q-5 — confirm correct LangChain package for Claude on Vertex (`langchain-google-vertexai` ChatAnthropicVertex) in dev environment before finalizing ENV-03
- [Phase 5 RESOLVED]: A2A schema confirmed from project documents (not external URL) — POST /run with {uid, question} -> {uid, answer}; simplified variant, not full Google A2A JSON-RPC SDK

## Session Continuity

Last session: 2026-03-21
Stopped at: 05.1-02-PLAN.md — complete (A2AStarletteApplication replaces FastAPI; OfficeQAAgentExecutor created; agent card + JSON-RPC + /health)
Next: Phase 5.1 Plan 03 (05.1-03-PLAN.md)
Resume file: None
