# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Every answer must be traceable to a specific sentence or table cell in the local corpus — no hallucination, no web search, exact arithmetic.
**Current focus:** Phase 2 — Extraction + Calculation Core

## Current Position

Phase: 2 of 6 (Extraction + Calculation Core)
Plan: 4 of N in current phase (03 complete)
Status: Phase 2 plan 03 complete — normalize_answer + format_survey fixture + 128 tests pass; 361 full suite pass
Last activity: 2026-03-18 — 02-03 normalize_answer (format-exact answer normalizer) executed and committed

Progress: [███░░░░░░░] 28%

## Performance Metrics

**Velocity:**
- Total plans completed: 7 (Phase 1: 01-01, 01-02, 01-03 | Phase 2: 02-01, 02-02, 02-01-retroactive, 02-03)
- Total execution time: 3 sessions

**By Phase:**

| Phase | Plans | Status |
|-------|-------|--------|
| 1: Environment + Retrieval Foundation | 3/3 | Complete |
| 2: Extraction + Calculation Core | 3/? | In progress (01, 02, 03 done; 04+ pending) |

**Execution Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 02-extraction-calculation-core P01 | 45min | 2 tasks | 6 files |
| Phase 02-extraction-calculation-core P02 | 35min | 2 tasks | 2 files |
| Phase 02-extraction-calculation-core P03 | 25min | 2 tasks | 4 files |

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Open question Q-2 — run corpus manifest diff (`set(csv_source_files) - set(corpus_files)`) before writing any retrieval code to surface missing files early
- [Phase 1]: Open question Q-5 — confirm correct LangChain package for Claude on Vertex (`langchain-google-vertexai` ChatAnthropicVertex) in dev environment before finalizing ENV-03
- [Phase 5]: Open question Q-1 — A2A schema must be confirmed from AgentBeats GitHub repo before writing Pydantic models; Phase 5 plan 05-01 is blocked until this is read

## Session Continuity

Last session: 2026-03-18
Stopped at: Completed 02-extraction-calculation-core 02-03-PLAN.md — normalize_answer + 128 tests pass, 361 full suite pass.
Next: Continue Phase 2 — plan 02-04 or next plan per roadmap.
Resume file: None
