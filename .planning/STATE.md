# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Every answer must be traceable to a specific sentence or table cell in the local corpus — no hallucination, no web search, exact arithmetic.
**Current focus:** Phase 3 — Agent Loop + Scratch Space

## Current Position

Phase: 3 of 6 (Agent Loop + Scratch Space)
Plan: 3 of 3 in current phase (03-03 at checkpoint — awaiting human-verify)
Status: Phase 3 Plan 03 tasks 1-2 complete — test_scratch.py (7 unit tests), test_agent.py (5 integration smoke tests), 368 tests pass; stopped at Task 3 checkpoint:human-verify
Last activity: 2026-03-19 — Phase 3 Plan 03 partial execution (tasks 1-2), 368 tests pass

Progress: [████░░░░░░] 42%

## Performance Metrics

**Velocity:**
- Total plans completed: 9 (Phase 1: 01-01, 01-02, 01-03 | Phase 2: 02-01, 02-02, 02-01-retroactive, 02-03 | Phase 3: 03-01, 03-02) — 03-03 at checkpoint
- Total execution time: 4 sessions

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| 1: Environment + Retrieval Foundation | 3/3 | Complete |
| 2: Extraction + Calculation Core | 3/3 | Complete |
| 3: Agent Loop + Scratch Space | 2/3 + checkpoint | In progress (03-03 awaiting human-verify) |

**Execution Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 02-extraction-calculation-core P01 | 45min | 2 tasks | 6 files |
| Phase 02-extraction-calculation-core P02 | 35min | 2 tasks | 2 files |
| Phase 02-extraction-calculation-core P03 | 25min | 2 tasks | 4 files |
| Phase 03-agent-loop-scratch-space P01 | 13min | 2 tasks | 12 files |
| Phase 03-agent-loop-scratch-space P03 | 7min | 2 tasks (partial) | 4 files |

*Updated after each plan completion*

## Accumulated Context

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
- [Phase 03-01]: @tool decorator — name arg must be positional: tool("name")(fn) not @tool(name="name")
- [Phase 03-01]: Wrapper pattern: original functions renamed _impl, StructuredTool aliases registered; avoids direct @tool decoration which breaks positional-arg test call sites
- [Phase 03-01]: route_files needs thin _route_files_agent wrapper (no config param) — Config is TYPE_CHECKING import, causes NameError in Pydantic schema introspection
- [Phase 03-01]: Optional[str] required for pct_change unit_old/unit_new — Pydantic V2 rejects None for str=None typed params in .invoke()
- [Phase 03-01]: Tests for invalid-type inputs (None, int, list) call _impl directly — StructuredTool Pydantic validates before function, so INVALID_INPUT dict never reached via .run(None)
- [Phase 03-03]: run_question_with_messages() added to agent.py — exposes message list for ToolMessage ordering assertions without breaking run_question signature
- [Phase 03-03]: Integration test Q selection: Q1=UID0002 (easy lookup), Q2=UID0004 (pct_change), Q3=UID0003 (table sum)
- [Phase 03-03]: ToolMessage ordering test uses getattr(msg, 'name', None) — compatible across langchain_core versions

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Open question Q-2 — run corpus manifest diff (`set(csv_source_files) - set(corpus_files)`) before writing any retrieval code to surface missing files early
- [Phase 1]: Open question Q-5 — confirm correct LangChain package for Claude on Vertex (`langchain-google-vertexai` ChatAnthropicVertex) in dev environment before finalizing ENV-03
- [Phase 5]: Open question Q-1 — A2A schema must be confirmed from AgentBeats GitHub repo before writing Pydantic models; Phase 5 plan 05-01 is blocked until this is read

## Session Continuity

Last session: 2026-03-19
Stopped at: Phase 3 Plan 03 checkpoint:human-verify (Task 3) — test_scratch.py + test_agent.py created, 368 tests pass. Awaiting human to run integration tests with Vertex AI credentials.
Next: After human verifies integration test output, confirm Task 3 done and close out 03-03-SUMMARY.md
Resume file: None
