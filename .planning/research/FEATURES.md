# FEATURES.md — AgentBeats OfficeQA Finance Agent

## Why OfficeQA Questions Are Hard — Five Axes

1. **Multi-hop temporal lookups** — a single question may require values from two different bulletin issues (e.g. January 1941 + February 1954)
2. **Monthly-sum aggregation** — questions explicitly require summing 12 individual monthly rows, deliberately excluding the pre-printed annual total row (which differs due to revisions)
3. **Percent-change with precise rounding** — `1608.80%` vs `1608.8%` fails exact string match; trailing zeros matter
4. **Table header disambiguation** — "National defense" vs "National defense and Veterans' Adm." vs "National defense and associated activities" across bulletin eras; multi-level headers encoded as `Parent > Child > Unnamed: n_level_m`
5. **Compound statistical calculations** — geometric mean, OLS, Box-Cox, Theil index, Zipf, KL divergence, CAGR, VaR, exponential smoothing appear in ~20% of hard questions

---

## Table Stakes Features

Must have — accuracy collapses without these.

### TS-1: File Router
**Complexity**: Medium
Maps question date/topic signals to 1–3 candidate `treasury_bulletin_YYYY_MM.txt` files. Pure regex/stdlib, no LLM call. Handles calendar year, fiscal year (FY → July–June), and topic keyword fallback. Without this, BM25 searches across 697 files return noise.
**Depends on**: None (entry point)

### TS-2: BM25 + Regex Within-File Search
**Complexity**: Low–Medium
Per-file BM25 (rank-bm25) over 20-line spans, with regex fallback for exact numeric values. Returns top-5 ranked spans as text. Query must be a short targeted phrase, not the full question.
**Depends on**: TS-1 (must run after file router narrows candidates)

### TS-3: Markdown Table Block Extractor with Multi-Level Header Parsing
**Complexity**: Medium–High ← hardest table-stakes piece
Identifies pipe-delimited table blocks anchored by a heading phrase; returns the complete raw block including header rows, separator row, and footnotes. The LLM then parses multi-level headers (`Parent > Child`) to locate the correct cell. Missing the footnote row causes unit errors (see PITFALLS).
**Depends on**: TS-2 (called when a span references a table)

### TS-4: Python-Based Exact Arithmetic Calculator
**Complexity**: Low base / High for statistical formulas
AST-based safe eval with `decimal.Decimal`. Supports +, -, *, /, ** and parentheses. The LLM passes arithmetic expressions; the tool executes them safely and returns the result as a string. Must handle: sum of N values, percent change `(new - old) / old * 100`, absolute percent change, rounding to N decimal places.
**Depends on**: TS-2/TS-3 (values must be extracted before calculation)

### TS-5: Answer Normalizer
**Complexity**: Medium
Rule-based (not LLM) formatting of the final numeric value to match benchmark expected format:
- Integers: comma thousands separator, no decimal, no currency symbol (e.g. `"2,602"`)
- Percentages: exactly 2 decimal places + `%` suffix (e.g. `"1608.80%"`)
- Survey of `officeqa_full.csv` answer column must inform the complete rule set before implementation
**Depends on**: TS-4 (normalizes calculator output)

### TS-6: Per-Question Filesystem Scratch Space
**Complexity**: Low
Isolated `./scratch/{uid}/` directory per question with standardized files: `evidence.txt`, `tables.txt`, `extracted_values.txt`, `calc.txt`, `verification.txt`, `answer.txt`. Enables reproducibility, debugging, and verifier access to intermediate state. Implemented via Deep Agents `FilesystemBackend(virtual_mode=False)`.
**Depends on**: TS-1 (created at question start, keyed by UID)

### TS-7: A2A HTTP Interface — `POST /run`
**Complexity**: Low
FastAPI endpoint accepting `{uid, question}` and returning `{uid, answer}`. The exact schema must be confirmed from the AgentBeats benchmark GitHub repo before finalizing. Without this, the agent cannot be submitted to the benchmark.
**Depends on**: All tools assembled (the HTTP layer wraps the complete agent)

---

## Differentiating Features

Competitive advantage for hard questions (top quartile of difficulty).

### D-1: Verifier Subagent
**Complexity**: Medium
Deep Agents subagent (stateless per call) that independently re-checks: (a) evidence coverage — every value used in calculation has a source span in `evidence.txt`; (b) unit consistency — all addends in the same unit; (c) arithmetic correctness — re-executes the expression; (d) answer precision — format matches benchmark conventions. On `FAIL`, the main agent retries retrieval or calculation. Without the verifier, systematic arithmetic errors and unit mismatches go undetected.
**Depends on**: TS-2, TS-4, TS-6 (reads scratch files written by main agent)

### D-2: Multi-Level Header Resolver with Era-Aware Column Disambiguation
**Complexity**: Medium–High
Treasury Bulletin column headers changed names across decades. "National defense" in a 1940 table vs "National defense and associated activities" in a 1953 table refer to the same series, but the LLM must be guided to identify the correct column despite the label mismatch. Requires a curated mapping of known series name variants + a prompt strategy that asks the LLM to identify the column by series description rather than exact label match.
**Depends on**: TS-3 (column disambiguation applied to extracted table blocks)

### D-3: Monthly-vs-Annual Row Discriminator
**Complexity**: Low–Medium
Several questions explicitly require summing individual monthly rows and NOT using the annual total row (which may differ due to retrospective revisions). A regex heuristic identifies rows labeled with month names (January–December) vs rows labeled "Total" or "Annual". The LLM is instructed to prefer individual monthly rows when the question says "using specifically only the reported values for all individual calendar months".
**Depends on**: TS-3 (applied after table block extraction)

### D-4: Statistical Formula Library
**Complexity**: Medium
Pre-validated Python implementations (callable as tools or invoked by the calculator) for formulas that appear in ~20% of hard questions: geometric mean, CAGR, OLS slope/intercept, Box-Cox transformation, Theil inequality index, Zipf law fit, KL divergence, VaR (historical), exponential smoothing. The LLM must not generate these formulas inline — it calls the validated tool. Each formula has a unit test asserting known output for known input.
**Depends on**: TS-4 (extended calculator)

### D-5: Cross-Bulletin Continuity Resolver for Multi-File Time Series
**Complexity**: High
Some questions span a time range covered by 3–10 bulletin issues (e.g. "sum all monthly values from 1950 to 1955"). The file router returns all relevant files; the agent must retrieve the same series from each and handle cases where the series appears under slightly different table IDs or section headings in different bulletin eras. A cross-bulletin lookup strategy (guided by the file manifest and series metadata) reduces missing-value errors for long time series.
**Depends on**: TS-1, TS-2, D-2

---

## Anti-Features

Things to deliberately NOT build.

| Anti-feature | Why |
|---|---|
| Vector embeddings (FAISS, Chroma, Pinecone) | Adds GPU/cost overhead; BM25 + regex is sufficient for exact figure lookup in structured text |
| Hardcoded UID-keyed answers | Benchmark-unsafe; fails on held-out questions |
| Web search during inference | Violates strict grounding constraint; answers must come from local corpus only |
| Full-document LLM context | Sending entire bulletin files as context wastes tokens and hits context limits; targeted span retrieval is the right approach |
| Browser/mobile UI | Pure API/CLI; out of scope |
| Streaming HTTP responses | Benchmark evaluator expects a complete `answer` field; streaming complicates response parsing |

---

## Feature Build Order

**Phase 1 (foundation — required for any correct answer):**
TS-1 → TS-2 → TS-3 → TS-4 (basic arithmetic) → TS-5 → TS-7

**Phase 2 (reliability — reduces systematic errors):**
D-3 (monthly discriminator) → D-2 (header resolver) → TS-6 (scratch space) → D-1 (verifier)

**Phase 3 (hard questions — statistical and multi-file):**
D-4 (statistical formulas) → D-5 (cross-bulletin continuity)
