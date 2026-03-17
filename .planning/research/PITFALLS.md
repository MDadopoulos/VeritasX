# PITFALLS — AgentBeats OfficeQA Finance Agent

Applies to: 697 Treasury Bulletin files (1939–2025), BM25+regex retrieval, LangChain create_agent, Deep Agents middleware, Vertex AI, A2A benchmark submission.

---

## 1. Financial QA Agents Over Historical Document Corpora

### 1.1 Wrong Table / Wrong Document Selected — CRITICAL

**What goes wrong**: The agent retrieves a table whose header matches the keyword but is from the wrong bulletin year. "Table FD-2" appears in nearly every monthly issue.

**Warning signs**:
- Agent cites a file outside the question's date scope
- Retrieved span has the right table name but wrong year in column header
- Answer passes arithmetic checks but differs from expected by exactly one year's change

**Prevention**:
- File router must extract fiscal/calendar year from the question BEFORE any BM25 query; hard-filter to matching bulletin months
- Every evidence span stored in scratch must record `(source_file, table_id, column_header_year)`
- Verifier checks that the column header year matches the question year; mismatch triggers re-retrieval

**Phase**: Retrieval design (file router + span reader) and Verifier subagent

---

### 1.2 Wrong Unit (Millions vs. Thousands vs. Billions) — CRITICAL

**What goes wrong**: Treasury Bulletin tables change unit conventions across decades. A 1940s table in thousands, the same series in the 2000s in millions. Off by 1,000×.

**Warning signs**:
- Table footnote contains "In thousands" or "Amounts in millions" — if the table extractor truncates before the footnote, unit is silently lost
- Answer is off by exactly 1,000×

**Prevention**:
- Table extractor must capture ALL rows from header through next blank line or next `##` heading, including footnotes
- Unit metadata stored alongside every extracted value in `extracted_values.txt`
- Calculator normalizes all inputs to the same unit before arithmetic; unit mismatch is a hard error

**Phase**: Table-block extractor and Python calculator tool

---

### 1.3 Wrong Year in Multi-Year Summation — HIGH

**What goes wrong**: "sum fiscal years 1995 through 1999" → agent retrieves 4 values (off-by-one on range boundary) due to ambiguous "through" interpretation.

**Warning signs**:
- Count of evidence spans does not match periods implied by the question
- Question uses "from X to Y" or "X through Y"

**Prevention**:
- Date-range parser always treats "through Y" and "to Y" as inclusive of Y
- Verifier counts retrieved data points and compares to expected count; mismatch triggers re-retrieval
- FY mapping: US Treasury FY ends September 30. FY1999 = October 1998 – September 1999

**Phase**: File-router date logic and Verifier count check

---

## 2. BM25 Retrieval for Financial Terminology

### 2.1 Identical Table Names Across 697 Files — CRITICAL

**What goes wrong**: BM25 scores "Table FD-2" equally across all 697 files. Without date-range pre-filtering, top-k results are spread across random years.

**Warning signs**:
- BM25 returns results spanning more than 3–4 years
- Top-k source files do not match question's date scope

**Prevention**:
- Two-stage search is mandatory: file router runs FIRST, THEN BM25 within candidates. BM25 never runs on the full corpus for date-scoped questions

**Phase**: Retrieval design — file router must precede BM25, not run in parallel

---

### 2.2 Financial Abbreviations Not Tokenized Correctly — HIGH

**What goes wrong**: BM25 treats "FY95" as one token; a query for "fiscal year 1995" does not match. "$2,602" and "2602" are different tokens.

**Prevention**:
- Normalize corpus at index-build time: expand "FY95" → "fiscal year 1995", strip commas from numbers, normalize dash variants
- Apply same normalization to queries at query time
- Regex fallback: if BM25 returns zero results, run regex on candidate files for the numeric value

**Phase**: Index-build step and query normalization in span-reader tool

---

### 2.3 High-IDF Terms That Are Ubiquitous in This Corpus — MEDIUM

**What goes wrong**: Standard BM25 weights "Treasury" very high globally, but in a Treasury-only corpus it is the lowest-signal word possible.

**Prevention**:
- Build IDF index on the full 697-file corpus so "Treasury", "Department", "fiscal year", "Table" receive near-zero IDF weights
- Add domain-specific stopword list for IDF suppression

**Phase**: Index-build step

---

## 3. LangChain `create_agent` Tool-Call Loops

### 3.1 Infinite Retrieval Loops — HIGH

**What goes wrong**: Agent calls span-reader, does not find exact match, rephrases and retries indefinitely. `create_agent` does not impose a tool-call budget by default.

**Warning signs**:
- Same tool name appears more than 3 times in intermediate steps
- Wall-clock time exceeds 60 seconds without final answer

**Prevention**:
- Set `max_iterations` on the LangChain agent (e.g. 12 steps)
- Per-tool call counter in tool wrappers; return `RETRIEVAL_EXHAUSTED` after 4 calls to the same tool
- System prompt: "You must move to calculation after at most 3 retrieval attempts."

**Phase**: Agent construction and system prompt design

---

### 3.2 Hallucinated Tool Arguments — HIGH

**What goes wrong**: LLM generates a filename that does not exist (e.g. `treasury_bulletin_1999_13.txt`). Tool raises FileNotFoundError; agent retries with another hallucinated name.

**Prevention**:
- Provide the complete file manifest at startup (list of valid filenames) in the system prompt or a manifest-lookup tool
- All file-accepting tools validate the filename against the manifest and return a structured error: `{"error": "file_not_found", "valid_range": "1939-01 to 2025-09"}`

**Phase**: Tool implementation (file router and span reader)

---

### 3.3 Skipping the Verification Step — CRITICAL

**What goes wrong**: Agent produces an arithmetic result and immediately formats it as the final answer, bypassing the verifier subagent.

**Warning signs**:
- Final answer appears in fewer than 4 tool calls for a multi-file summation
- No call to the verifier tool in the agent trace

**Prevention**:
- Make verification a mandatory step: the `normalize_answer` tool requires a `verification_token` argument produced only by the verifier tool. Without it, normalizer raises an error.
- System prompt: "You MUST call the verifier before calling normalize_answer."

**Phase**: Agent construction and Deep Agents middleware design

---

## 4. Arithmetic in LLM Agents

### 4.1 Off-by-One in Range Summations — HIGH

**What goes wrong**: Agent sums 4 values for "FY1990 through FY1994" instead of 5 — generates `range(1990, 1994)` instead of `range(1990, 1995)`.

**Prevention**:
- Calculator tool receives explicit lists of `(year, value)` pairs, never a range
- Tool signature: `sum_values(pairs: list[tuple[str, float]]) -> float`
- Before summing, calculator logs pair count; if count != expected_count, returns an error

**Phase**: Python calculator tool design

---

### 4.2 Wrong Percent-Change Formula — CRITICAL

**What goes wrong**: LLM computes `(new - old) / new * 100` instead of `(new - old) / old * 100`.

**Prevention**:
- Hard-code: `pct_change(old, new) = (new - old) / old * 100`. LLM calls this tool; never generates the formula inline.
- System prompt: "Percent change is always (new - old) / old × 100. Never compute it inline; always use pct_change tool."
- Verifier confirms both `old_value` and `new_value` are in evidence and formula was applied in the right direction

**Phase**: Python calculator tool and Verifier subagent

---

### 4.3 Unit Confusion in Arithmetic — CRITICAL

**What goes wrong**: One addend in millions, one in thousands. Sum is off by 1,000× for one term.

**Prevention**:
- Calculator rejects any input list where units are not all identical
- LLM must call `normalize_units(values, target_unit)` before arithmetic
- Assert in calculator: `assert len(set(units)) == 1`. Fail loudly.

**Phase**: Python calculator tool

---

### 4.4 Float Rounding Producing Wrong Final Answer — HIGH

**What goes wrong**: Python float arithmetic produces `2601.9999999` or `2602.0000001`; normalizer produces `"2602.0"` instead of `"2602"`.

**Prevention**:
- Use `decimal.Decimal` for all financial arithmetic with `getcontext().prec = 28`
- Normalizer rules: integers formatted without decimal point; percentages to exactly 2 decimal places

**Phase**: Python calculator tool and answer normalizer

---

## 5. A2A Benchmark Submission — Answer Format Mismatch

### 5.1 Number Formatting Divergence — CRITICAL

**What goes wrong**: Benchmark answer is `"2,602"`. Agent returns `"2602"` or `"$2,602 million"`. Exact string match fails.

**Prevention**:
- Before writing any normalizer code, run statistical analysis of the `answer` column in both CSV files to enumerate all format patterns
- Normalizer is rule-based, not LLM-generated:
  - Integers: comma thousands separator, no decimal, no currency symbol
  - Percentages: exactly 2 decimal places + `%` suffix
- Maintain a format test suite asserting `normalize(raw) == expected` for all known benchmark samples

**Phase**: Answer normalizer tool, built and tested before any benchmark submission

---

### 5.2 Trailing Zero Inconsistency — CRITICAL

**What goes wrong**: Benchmark answer is `"1608.80%"` (trailing zero). Agent returns `"1608.8%"`.

**Prevention**:
- All percentage formatting uses `f"{value:.2f}%"`. LLM never formats the final answer string directly.
- Regex validator in normalizer: if answer matches percentage pattern, assert exactly 2 decimal places

**Phase**: Answer normalizer tool

---

### 5.3 A2A Protocol Response Schema Mismatch — HIGH

**What goes wrong**: A2A spec requires `{"result": "2,602"}` but agent returns `{"answer": "2,602"}`. Benchmark evaluator reads `null`.

**Prevention**:
- Confirm exact A2A response schema from AgentBeats benchmark GitHub repo BEFORE implementing the HTTP endpoint
- Write integration test: POST a sample question to the local agent and assert the response matches the A2A schema exactly

**Phase**: Research phase (confirm spec) and integration testing before first submission

---

## 6. Deep Agents Middleware

### 6.1 Filesystem State Leakage Between Questions — CRITICAL

**What goes wrong**: If scratch directory is not isolated per question (e.g. shared `scratch/current/`), evidence from question N bleeds into question N+1.

**Warning signs**:
- Running questions in sequence produces different results than running each in isolation
- Verifier finds evidence spans from files not referenced in the current question

**Prevention**:
- Scratch paths namespaced by question UID: `scratch/{uid}/`. UID comes from the A2A request.
- At start of each question, assert scratch directory for that UID is empty (or create it fresh)
- Integration test: run two back-to-back questions with disjoint answers; verify they do not interfere

**Phase**: Deep Agents middleware design and per-question lifecycle management

---

### 6.2 Subagent Error Handling — Silent Failures — HIGH

**What goes wrong**: Verifier subagent encounters an error and returns a Python exception. Parent agent catches it and proceeds to return the unverified answer anyway.

**Prevention**:
- Verifier returns structured result: `VerifierResult(status: "PASS"|"FAIL"|"ERROR", issues: list[str], token: str|None)`
- `ERROR` status treated same as `FAIL`
- Parent agent on `FAIL`/`ERROR`: retries retrieval/calculation or returns "cannot determine" — never the unverified answer

**Phase**: Deep Agents middleware and Verifier subagent error contract

---

### 6.3 Subagent Invocation Overhead Causing Timeouts — MEDIUM

**What goes wrong**: Deep Agents subagent calls add latency. Complex multi-file questions may exceed benchmark timeouts.

**Prevention**:
- Implement `FAST_MODE=true` env var that skips the verifier for latency-sensitive runs
- Profile per-question latency breakdown on 10 questions before optimizing
- Set explicit timeout on subagent calls; `ERROR` if no response within N seconds

**Phase**: Performance optimization after initial correctness validation

---

## 7. Vertex AI LangChain Integration

### 7.1 Rate Limits Causing Silent Answer Degradation — HIGH

**What goes wrong**: Agent hits Vertex AI per-minute token quota mid-question. LangChain may retry silently, return a truncated response, or raise an exception that causes a tool call to be skipped.

**Prevention**:
- Instrument all Vertex AI calls with explicit retry-with-backoff (exponential, max 3 retries, jitter)
- Log all rate-limit events with timestamp and UID; pause batch run if more than 3 events in 60 seconds
- Request quota increase before submitting more than ~200 questions per hour
- Add per-question delay (e.g. 2 seconds) for batch evaluation runs

**Phase**: Vertex AI integration layer, before batch evaluation

---

### 7.2 Streaming Mode Producing Malformed Tool Arguments — HIGH

**What goes wrong**: If streaming is enabled, agent may process partial responses as complete tool-call arguments, producing truncated JSON.

**Prevention**:
- Use non-streaming mode for all tool-call generating model calls: `streaming=False` in the Vertex AI constructor
- Add JSON validation step in each tool's argument parser; return structured error on invalid JSON

**Phase**: Vertex AI integration layer

---

### 7.3 Token Budget Exhaustion on Multi-File Questions — HIGH

**What goes wrong**: Complex questions require passing multiple retrieved spans to the LLM. Total context exceeds model window; LangChain silently drops earlier evidence spans.

**Prevention**:
- Context-budget tracker: before each LLM call, estimate token count; if > 80% of context window, compress older evidence spans (summarize to key facts already in scratch)
- Store all extracted values in filesystem scratch, not in LangChain conversation history
- Use `gemini-2.0-flash` (1M token context) as default; switch to `gemini-2.5-pro` only for questions requiring very large context

**Phase**: Agent construction and evidence management design

---

## Summary Table

| # | Pitfall | Severity | Phase |
|---|---------|----------|-------|
| 1.1 | Wrong document/table selected | Critical | Retrieval design |
| 1.2 | Unit convention mismatch | Critical | Table extractor + Calculator |
| 1.3 | Off-by-one date range | High | File router + Verifier |
| 2.1 | Identical table names across 697 files | Critical | Retrieval design |
| 2.2 | Abbreviations not tokenized | High | Index build + Query normalization |
| 2.3 | High-IDF terms ubiquitous in corpus | Medium | Index build |
| 3.1 | Infinite retrieval loops | High | Agent construction |
| 3.2 | Hallucinated tool arguments | High | Tool implementation |
| 3.3 | Skipping verification step | Critical | Agent construction + Middleware |
| 4.1 | Off-by-one in summation ranges | High | Calculator tool |
| 4.2 | Wrong percent-change formula | Critical | Calculator tool + Verifier |
| 4.3 | Unit confusion in arithmetic | Critical | Calculator tool |
| 4.4 | Float rounding wrong string | High | Calculator + Normalizer |
| 5.1 | Number format mismatch | Critical | Answer normalizer |
| 5.2 | Trailing zero inconsistency | Critical | Answer normalizer |
| 5.3 | A2A response schema mismatch | High | Research phase + Integration test |
| 6.1 | Filesystem state leakage | Critical | Middleware design |
| 6.2 | Silent subagent failures | High | Middleware + Verifier contract |
| 6.3 | Subagent latency / timeouts | Medium | Performance optimization |
| 7.1 | Vertex AI rate limits | High | Vertex AI integration |
| 7.2 | Streaming malformed tool args | High | Vertex AI integration |
| 7.3 | Token budget exhaustion | High | Agent construction |
