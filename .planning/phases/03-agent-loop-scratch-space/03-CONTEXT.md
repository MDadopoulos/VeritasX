# Phase 3: Agent Loop + Scratch Space - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire all Phase 1+2 tools into `create_deep_agent` with per-question filesystem scratch isolation, a mandatory `write_todos` planning gate before retrieval, and a call-count loop guard. The agent must produce six scratch files per question UID and handle exhaustion gracefully.

</domain>

<decisions>
## Implementation Decisions

### Scratch file content

- **evidence.txt** — Annotated spans: raw retrieved span text + source file path + one-line agent note on why this span was selected
- **tables.txt** — Raw extracted table block only (what `extract_table_block` returned, unparsed)
- **extracted_values.txt** — Every numeric value includes its unit alongside the value (e.g., `defense_1940 = 2602 (millions)`) — already required by success criterion
- **calc.txt** — Claude's discretion: format that makes downstream verification straightforward (expression, result, labeled inputs with source)
- **answer.txt** — Normalized answer on first line, followed by a one-sentence rationale (e.g., `pct_change from 2602 to 3100 over FY1940`)

### Write-todos protocol

- Agent must write a todo list containing at minimum: (1) restatement of the question as understood, (2) planned tool call sequence in order — before any retrieval tool is called
- Agent **may** update the todo list mid-run as new evidence changes the plan
- Agent **checks off** completed items as it progresses — progress is visible in trace and scratch files
- Enforcement of the pre-retrieval gate: Claude's discretion (balance hard blocking vs. trace debuggability)

### Exhaustion + failure behavior

- Call limit applies to **retrieval tools only** (`route_files`, `search_in_file`) — `calculate` and `extract_table_block` are uncapped
- Per-question retrieval call limit: **20 calls** (raised from roadmap's original 4)
- When limit is hit: agent attempts a best-effort answer using evidence gathered so far
- If agent judges the evidence insufficient to answer: emit exactly `"I cannot determine the answer from the available corpus."`
- Sufficiency judgment: agent decides based on what it has found (no hard rule)

### Claude's Discretion

- `calc.txt` exact format (expression layout, labeling style)
- Enforcement mechanism for the pre-retrieval `write_todos` gate
- `max_iterations` and `MemorySaver` checkpointer configuration details
- Scratch directory layout within `./scratch/{uid}/`

</decisions>

<specifics>
## Specific Ideas

- Retrieval limit raised to 20 to give the agent more room on hard multi-span questions before exhausting
- "cannot determine" phrasing: `"I cannot determine the answer from the available corpus."` — explicit corpus reference distinguishes it from model uncertainty

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-agent-loop-scratch-space*
*Context gathered: 2026-03-19*
