# Phase 1: Environment + Retrieval Foundation - Research

**Researched:** 2026-03-17
**Domain:** Vertex AI LangChain adapters, BM25 span retrieval, corpus manifest validation, pytest offline/integration split
**Confidence:** HIGH (stack verified via PyPI + official docs; corpus structure verified by direct inspection)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Startup failure behavior**
- `CORPUS_SOURCE` env var controls corpus behavior — `local` mode fails hard and exits if files are missing
- Vertex AI auth failure is always fatal — fail hard and exit, no degraded startup
- Missing-file warnings (in future non-local modes) output to both stderr and a startup log file
- Manifest check source (hardcoded vs CSV-derived): Claude's discretion

**Span design**
- When a table exceeds 20 lines, expand to the full table — never truncate mid-table regardless of size
- Span overlap/deduplication strategy: Claude's discretion
- When BM25 and regex fallback both find nothing, return a structured no-results error object (with the query echoed back) — not an empty list
- Each returned span includes full metadata: source file path, start/end line numbers, BM25 score, and whether regex fallback was used

**Model adapter interface**
- Model selected via `MODEL_ID` env var only — no CLI flag
- Default when `MODEL_ID` is unset: `claude-sonnet-4-6`
- Tool schema strictness between Gemini and Claude adapters: Claude's discretion
- Adapter interface depth (thin wrapper vs capability metadata): Claude's discretion

**Test isolation strategy**
- Two separate test suites: unit tests (mocked Vertex AI, run offline) + integration tests (real credentials, opt-in only)
- Unit test fixtures: 1-2 real bulletin files copied into the test directory — no synthetic fabrication
- Integration tests are opt-in only: run with `pytest -m integration`, not triggered automatically in CI
- Phase completion bar: Claude's discretion

### Claude's Discretion
- Manifest check: whether to derive expected file list from CSV source columns or use a hardcoded list
- Span overlap: deduplication strategy when multiple spans cover the same table
- Model adapter: how strict schema identity needs to be between Gemini and Claude
- Model adapter: whether to expose capability metadata or just wrap the call
- Phase completion criteria: what combination of tests must pass

### Deferred Ideas (OUT OF SCOPE)
- Remote corpus download — when `CORPUS_SOURCE=remote`, agent searches and downloads missing bulletin files from online sources; this is its own capability and belongs in a future phase
</user_constraints>

---

## Summary

This phase bootstraps all foundational runtime components: Vertex AI credential wiring for both Gemini and Claude, a model adapter that normalises the LangChain interface between the two, a corpus manifest check, and the two retrieval tools (`route_files` and `search_in_file`). Nothing in the downstream phases can run without these pieces, so correctness and fail-fast behaviour at startup are paramount.

The key complexity in this phase is that two very different LangChain integrations must present an identical `bind_tools` interface to callers. `ChatGoogleGenerativeAI` (langchain-google-genai 4.2.1) uses the consolidated `google-genai` SDK and is routed via `GOOGLE_GENAI_USE_VERTEXAI=true`. `ChatAnthropicVertex` (langchain-google-vertexai 3.2.2 with `[anthropic]` extra) routes Claude models through Vertex AI Model Garden and requires `GOOGLE_APPLICATION_CREDENTIALS` + a service-account JSON. The two packages have different auth paths and different tool-schema constraints (Gemini rejects `z.record(z.unknown())`-style open objects; Claude via Vertex follows Anthropic tool schema conventions), so the adapter layer must paper over those differences explicitly.

BM25 retrieval using `rank_bm25 0.2.2` is straightforward but requires careful span-boundary logic: the corpus files use pipe-delimited Markdown tables (`| col | col |`) and a single table block in a 1940s bulletin can easily exceed 20 lines. The span-building algorithm must detect when a 20-line boundary falls inside a table and extend the span to the next non-pipe line before closing.

**Primary recommendation:** Install `langchain-google-genai==4.2.1`, `langchain-google-vertexai[anthropic]==3.2.2`, and `rank-bm25==0.2.2`; build a thin `get_model()` factory that dispatches on `MODEL_ID` prefix; implement span-building as a separate function with clear table-continuation logic; drive the manifest check from CSV source columns (not a hardcoded list) to stay in sync with the dataset automatically.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langchain-google-genai | 4.2.1 | `ChatGoogleGenerativeAI` for `gemini-*` models via Vertex AI | Official LangChain Gemini integration; 4.x unified with google-genai SDK |
| langchain-google-vertexai | 3.2.2 `[anthropic]` | `ChatAnthropicVertex` for `claude-*` models via Vertex AI Model Garden | Only LangChain-native path for Claude on Vertex; must install with `[anthropic]` extra |
| google-genai | (pulled by langchain-google-genai 4.x) | Underlying SDK for Gemini on Vertex AI | Replaces deprecated google-cloud-aiplatform generative AI; required by requirements |
| rank-bm25 | 0.2.2 | `BM25Okapi` index for in-file span search | Standard Python BM25 library; exactly what RET-04 names |
| pytest | latest stable (8.x) | Unit + integration test runner | Standard; supports custom markers for `integration` opt-in |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | latest | Load `.env` for local dev credential wiring | Dev-time convenience; not required in production |
| pytest-mock / unittest.mock | stdlib | Mock `ChatGoogleGenerativeAI` and `ChatAnthropicVertex` in unit tests | All unit tests — Vertex AI calls must never run offline |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| rank-bm25 | bm25s | bm25s is faster at scale but adds numpy/scipy dependency and is less battle-tested for this use-case; rank-bm25 is simpler and sufficient for single-file indexing |
| CSV-derived manifest | hardcoded file list | Hardcoded list drifts from dataset; CSV-derived is always correct and costs one parse at startup |
| `get_model()` factory | inline dispatch per tool | Factory centralises the model swap logic; inline dispatch would scatter adapter code across every tool |

**Installation:**
```bash
pip install \
  langchain-google-genai==4.2.1 \
  "langchain-google-vertexai[anthropic]==3.2.2" \
  rank-bm25==0.2.2 \
  python-dotenv \
  pytest
```

---

## Architecture Patterns

### Recommended Project Structure

```
workspace/
├── src/
│   ├── config.py            # env var loading, fail-fast startup checks
│   ├── corpus_manifest.py   # parse CSVs, build set of required files, validate
│   ├── model_adapter.py     # get_model() factory, adapter wrapper
│   ├── tools/
│   │   ├── route_files.py   # route_files tool — year/FY extraction + path validation
│   │   └── search_in_file.py # search_in_file tool — BM25 + regex fallback
│   └── __init__.py
├── tests/
│   ├── fixtures/            # 1-2 real bulletin .txt files copied here
│   ├── test_config.py
│   ├── test_corpus_manifest.py
│   ├── test_route_files.py
│   └── test_search_in_file.py
├── requirements.txt
├── pytest.ini               # registers 'integration' marker
└── .env.example             # documents required env vars
```

### Pattern 1: Model Adapter Factory

**What:** A single `get_model()` function reads `MODEL_ID` from the environment, dispatches to the correct LangChain chat class, and returns an object that supports `.bind_tools([...])`. All downstream code calls `get_model()` and never imports a specific model class directly.

**When to use:** At application startup; injected into every tool wrapper that makes LLM calls (downstream phases only — this phase wires the adapter but does not invoke the model).

**Example:**
```python
# Source: langchain-google-genai official docs + langchain-google-vertexai PyPI
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

def get_model():
    model_id = os.environ.get("MODEL_ID", "claude-sonnet-4-6")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

    if model_id.startswith("gemini-"):
        return ChatGoogleGenerativeAI(
            model=model_id,
            project=project,
            location=location,
        )
    elif model_id.startswith("claude-"):
        return ChatAnthropicVertex(
            model_name=model_id,
            project=project,
            location=location,
        )
    else:
        raise ValueError(f"Unsupported MODEL_ID: {model_id!r}. Must start with 'gemini-' or 'claude-'.")
```

**Auth difference to know:** For `ChatGoogleGenerativeAI` on Vertex, also set `GOOGLE_GENAI_USE_VERTEXAI=true` in the environment. For `ChatAnthropicVertex`, set `GOOGLE_APPLICATION_CREDENTIALS` pointing to a service-account JSON. Both can coexist in the same `.env` — only one code path runs at a time.

### Pattern 2: Span Builder with Table-Boundary Preservation

**What:** Read all lines from the corpus file. Walk lines in 20-line windows. When a window boundary falls on a pipe-table line (`line.startswith("|")`), extend the window forward until the first non-pipe line, then close the span there. Each span carries `{text, start_line, end_line}` metadata.

**When to use:** Inside `search_in_file` before building the BM25Okapi index.

**Example:**
```python
# Source: derived from RET-04 requirement + direct corpus inspection
def build_spans(lines: list[str], window: int = 20) -> list[dict]:
    spans = []
    i = 0
    while i < len(lines):
        end = min(i + window, len(lines))
        # Extend if we are cutting through a table block
        while end < len(lines) and lines[end].startswith("|"):
            end += 1
        spans.append({
            "text": "\n".join(lines[i:end]),
            "start_line": i + 1,   # 1-indexed for metadata
            "end_line": end,       # inclusive end (1-indexed)
        })
        i = end
    return spans
```

**Why this exact logic:** Corpus files use Markdown-style pipe tables. A large table in a 1940s bulletin (e.g., the 24-row Budget Receipts and Expenditures table in `treasury_bulletin_1941_01.txt`) would be split mid-row without this extension, producing spans with broken rows that BM25 cannot match.

### Pattern 3: BM25 Indexing + Regex Fallback

**What:** Build a `BM25Okapi` over the span texts (tokenized by whitespace after query normalisation). Retrieve top-5. If BM25 returns all-zero scores and the query contains a digit or fiscal-year abbreviation, fall back to `re.search(pattern, span_text, re.IGNORECASE)` across all spans.

**Example:**
```python
# Source: rank_bm25 PyPI docs + RET-04/RET-05 requirements
from rank_bm25 import BM25Okapi
import re

def normalize_query(query: str) -> str:
    # RET-06: expand FY abbreviations, strip commas, normalise dashes
    query = re.sub(r'\bFY\s*(\d{2,4})\b',
                   lambda m: f"fiscal year {_expand_year(m.group(1))}",
                   query, flags=re.IGNORECASE)
    query = query.replace(",", "")
    query = re.sub(r'[\u2013\u2014\u2012]', '-', query)
    return query

def search_spans(spans, query, fallback_on_empty=True):
    norm_query = normalize_query(query)
    tokenized_corpus = [s["text"].lower().split() for s in spans]
    tokenized_query = norm_query.lower().split()
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenized_query)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
    results = [
        {**spans[i], "bm25_score": scores[i], "regex_fallback": False}
        for i in top_indices if scores[i] > 0
    ]

    if not results and fallback_on_empty and re.search(r'\d|FY', query, re.IGNORECASE):
        # Regex fallback
        pattern = re.escape(norm_query.strip())
        results = [
            {**s, "bm25_score": 0.0, "regex_fallback": True}
            for s in spans if re.search(pattern, s["text"], re.IGNORECASE)
        ][:5]

    if not results:
        return {"error": "no_results", "query": query}

    return results
```

### Pattern 4: Fiscal Year → Calendar Month Mapping

**What:** US federal fiscal year ends September 30. "FY1940" = October 1939 through September 1940. The file router maps an FY reference to 12 filenames across two calendar years.

**Mapping rule:**
```python
# FY YYYY → months Oct(YYYY-1) through Sep(YYYY)
def fy_to_calendar_months(fy_year: int) -> list[tuple[int, int]]:
    """Returns list of (year, month) tuples for the 12 months of the fiscal year."""
    months = []
    for month in range(10, 13):          # Oct, Nov, Dec of prior year
        months.append((fy_year - 1, month))
    for month in range(1, 10):           # Jan through Sep of fiscal year
        months.append((fy_year, month))
    return months
```

**Example:** FY1940 → [(1939,10),(1939,11),(1939,12),(1940,1),...,(1940,9)]

**Note:** A question asking "FY 1940" therefore maps to `treasury_bulletin_1939_10.txt` through `treasury_bulletin_1940_09.txt`. Only return paths that exist in the corpus manifest.

### Pattern 5: Corpus Manifest Check (CSV-Derived)

**What:** At startup, parse both `officeqa_full.csv` and `officeqa_pro.csv`, extract the `source_files` column (values are **newline-separated**, not comma-separated — verified by direct inspection), build a set, then assert each file exists in `corpus/transformed/`. Fail hard if `CORPUS_SOURCE=local` and any file is missing.

**Key finding from corpus diff:** All 285 unique source files referenced in both CSVs are present in the 697-file `corpus/transformed/` directory. The manifest check will pass on this machine. Still implement it: it protects against accidental corpus deletion and documents the contract.

**Recommendation (Claude's Discretion — manifest source):** Use CSV-derived. The corpus has 697 files but only 285 are referenced by the dataset; a hardcoded list would require manual maintenance. CSV-derived is always authoritative.

```python
# Source: direct corpus inspection 2026-03-17
import csv, os

def load_manifest(csv_paths: list[str], corpus_dir: str) -> set[str]:
    """Returns set of all source_file basenames referenced in the CSVs."""
    required = set()
    for path in csv_paths:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                for fname in row.get("source_files", "").replace("\n", " ").split():
                    fname = fname.strip()
                    if fname:
                        required.add(fname)
    return required

def validate_corpus(required: set[str], corpus_dir: str) -> list[str]:
    """Returns list of missing filenames."""
    return [f for f in required if not os.path.isfile(os.path.join(corpus_dir, f))]
```

### Anti-Patterns to Avoid

- **Calling `BM25Okapi` with raw (untokenized) strings:** The library requires `list[list[str]]`. Passing raw strings silently produces wrong scores.
- **Splitting `source_files` column by comma:** The CSV field uses newline separators, not commas. Splitting by comma produces multi-filename strings as single tokens (verified by direct inspection of the CSV).
- **Using `ChatVertexAI` from `langchain-google-vertexai`:** Deprecated in 3.x; migrated to `ChatGoogleGenerativeAI` from `langchain-google-genai`. See official discussion #1422.
- **Using `google-cloud-aiplatform` generative AI APIs:** Explicitly listed as out-of-scope in REQUIREMENTS.md; replaced by `google-genai` SDK.
- **Open-property tool schemas with Gemini:** `ChatGoogleGenerativeAI` rejects tool schemas containing unrestricted `additionalProperties` or `record(unknown)`. All tool input schemas must enumerate properties explicitly.
- **Running integration tests in CI without opt-in:** Integration tests must be marked `@pytest.mark.integration` and excluded from default `pytest` runs. Credential leakage in CI is the risk.
- **Truncating a span mid-table:** The corpus tables can be 20-40+ lines. A 20-line fixed window will split rows, producing malformed spans that BM25 cannot rank correctly. Always extend to the end of the current table block.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| BM25 scoring | Custom TF-IDF scoring loop | `rank_bm25.BM25Okapi` | IDF calculation, term saturation (k1/b parameters), score normalisation all handled; hand-rolled TF-IDF consistently underperforms |
| LangChain model interface | Direct API calls with `google-genai` SDK | `ChatGoogleGenerativeAI` / `ChatAnthropicVertex` | `bind_tools`, message formatting, retry logic, structured output all come for free; downstream phases (agent loop) require the LangChain interface |
| CSV parsing with embedded newlines | Custom string splitting | `csv.DictReader` with `encoding='utf-8'` | The `source_files` field contains embedded newlines within a quoted CSV cell; Python's `csv` module handles RFC 4180 quoting correctly; naive `split(",")` does not |

**Key insight:** The retrieval stack in this phase is intentionally non-LLM. BM25 and regex are the only ranking mechanisms. Do not reach for embedding models, vector similarity, or LangChain retrievers — they add complexity without benefit for this structured-text corpus.

---

## Common Pitfalls

### Pitfall 1: Wrong `GOOGLE_CLOUD_LOCATION` for Claude on Vertex

**What goes wrong:** `ChatAnthropicVertex` initialisation raises a 400/404 error even with valid credentials.
**Why it happens:** Claude on Vertex AI Model Garden is only available in specific regions (typically `us-east5` or `europe-west1`), not `global`. The ENV-05 requirement specifies `GOOGLE_CLOUD_LOCATION=global` which is correct for Gemini via `google-genai`, but Claude needs a region-specific value.
**How to avoid:** Use separate location env vars or check the GCP console for available Claude regions before hardcoding. For Gemini: `GOOGLE_CLOUD_LOCATION=global`. For Claude: `GOOGLE_CLOUD_LOCATION=us-east5` (verify against GCP console for the specific project).
**Warning signs:** `400 Bad Request` or model-not-found errors during `ChatAnthropicVertex` instantiation.

### Pitfall 2: `source_files` CSV field uses newline separators

**What goes wrong:** Manifest check counts 285 distinct files but the code reads 115 "missing" entries that are actually multi-file strings like `"treasury_bulletin_1939_01.txt\ntreasury_bulletin_1939_02.txt"`.
**Why it happens:** Questions spanning multiple bulletins have multiple filenames in the `source_files` cell separated by `\n`. Python's `csv` module preserves the embedded newlines inside the quoted field. Splitting on `,` (or not splitting at all) yields the raw multi-line string.
**How to avoid:** After reading each `source_files` cell, replace `\n` with a space or split on whitespace. See the `load_manifest()` pattern above. This was verified by direct inspection — the corpus diff showed 0 missing files when handled correctly.
**Warning signs:** Manifest check reports missing files with names like `"treasury_bulletin_1939_01.txt\ntreasury_bulletin_1939_02.txt"`.

### Pitfall 3: BM25 scores are all zero for numeric queries

**What goes wrong:** `search_in_file("treasury_bulletin_1941_01.txt", "2602")` returns zero results.
**Why it happens:** BM25 is a term-frequency model. Numeric tokens like `"2602"` or `"1,580"` are rare in the tokenized corpus; comma-formatted numbers don't match non-comma versions. `BM25Okapi` returns 0.0 scores for all spans when no tokens match.
**How to avoid:** Apply query normalization (RET-06): strip commas from all numbers before tokenizing both spans and query. The regex fallback (RET-05) handles residual zero-score cases when BM25 fails on numeric tokens.
**Warning signs:** `get_scores()` returns an array of all zeros for any numeric query.

### Pitfall 4: Fiscal year off-by-one in file router

**What goes wrong:** "FY 1940" resolves to files for calendar year 1940 only (wrong), missing October-December 1939.
**Why it happens:** US fiscal year ends September 30. FY1940 = Oct 1939 through Sep 1940. The most natural mistake is to map FY year directly to calendar year.
**How to avoid:** Use the `fy_to_calendar_months(fy_year)` pattern above. Explicitly test edge cases: FY1939 (includes 1938-10 through 1939-09), FY1940 (1939-10 through 1940-09).
**Warning signs:** Unit test TST-02 fiscal-year mapping cases fail; files for October/November/December of the prior year are never returned for FY queries.

### Pitfall 5: langchain-google-vertexai `[anthropic]` extra not installed

**What goes wrong:** `ImportError: cannot import name 'ChatAnthropicVertex' from 'langchain_google_vertexai'`.
**Why it happens:** `ChatAnthropicVertex` requires an optional `anthropic` dependency that is not installed by default. The bare `pip install langchain-google-vertexai` is insufficient.
**How to avoid:** `pip install "langchain-google-vertexai[anthropic]"`. Document this in `requirements.txt` as `langchain-google-vertexai[anthropic]==3.2.2`.
**Warning signs:** Import error at startup when `MODEL_ID` starts with `claude-`.

### Pitfall 6: Span deduplication when table spans multiple 20-line windows

**What goes wrong:** A 40-line table produces one very long span (window extends through the full table on the first pass), and subsequent starts are correct — but if the window logic restarts mid-table (bug), the same table rows appear in two overlapping spans.
**Why it happens:** The span-building loop must advance `i` to `end` after each span, not by a fixed `window` increment. If `i += window` is used instead of `i = end`, the extension logic is bypassed.
**How to avoid:** Always use `i = end` to advance past the extended span boundary. Recommendation (Claude's Discretion — deduplication): use non-overlapping spans (advance `i = end`) rather than sliding-window overlaps. Non-overlapping spans mean each table row appears in exactly one span, eliminating the deduplication problem entirely.
**Warning signs:** Two spans with the same `start_line` appearing in results for a table query.

---

## Code Examples

Verified patterns from official sources:

### BM25Okapi — build index and query
```python
# Source: https://pypi.org/project/rank-bm25/ (rank-bm25 0.2.2)
from rank_bm25 import BM25Okapi

tokenized_corpus = [span["text"].lower().split() for span in spans]
bm25 = BM25Okapi(tokenized_corpus)

tokenized_query = query.lower().split()
scores = bm25.get_scores(tokenized_query)   # ndarray, one score per span
top5 = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
```

### ChatGoogleGenerativeAI — Vertex AI init
```python
# Source: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai
# langchain-google-genai 4.2.1 — requires GOOGLE_GENAI_USE_VERTEXAI=true in env
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)
llm_with_tools = llm.bind_tools([route_files_tool, search_in_file_tool])
```

### ChatAnthropicVertex — Vertex AI Model Garden init
```python
# Source: https://docs.langchain.com/oss/python/integrations/chat/google_anthropic_vertex
# langchain-google-vertexai[anthropic] 3.2.2
# Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing to service-account JSON
from langchain_google_vertexai.model_garden import ChatAnthropicVertex

llm = ChatAnthropicVertex(
    model_name="claude-sonnet-4-6",
    project=os.environ["GOOGLE_CLOUD_PROJECT"],
    location=os.environ["GOOGLE_CLOUD_LOCATION"],  # e.g. "us-east5"
)
llm_with_tools = llm.bind_tools([route_files_tool, search_in_file_tool])
```

### pytest.ini — register integration marker
```ini
# Source: https://docs.pytest.org/en/stable/example/markers.html
[pytest]
markers =
    integration: marks tests as requiring live Vertex AI credentials (deselect with -m "not integration")
```

### Unit test pattern — mock model adapter offline
```python
# Source: https://docs.pytest.org/en/stable/
# unittest.mock is stdlib — no extra install
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_model():
    m = MagicMock()
    m.bind_tools.return_value = m
    return m

def test_route_files_calendar_year(mock_model):
    from src.tools.route_files import route_files
    result = route_files("What were defense expenditures in 1940?")
    assert any("1940" in p for p in result["paths"])

@pytest.mark.integration
def test_model_adapter_live():
    from src.model_adapter import get_model
    model = get_model()
    response = model.invoke("Say hello")
    assert response.content
```

### FY normalization regex
```python
# Source: derived from RET-06 requirement
import re

_FY_PATTERN = re.compile(r'\bFY\s*(\d{2,4})\b', re.IGNORECASE)

def _expand_year(short: str) -> str:
    y = int(short)
    if y < 100:
        # Two-digit: 95 -> 1995, 05 -> 2005; threshold at 40
        return str(1900 + y if y >= 40 else 2000 + y)
    return str(y)

def normalize_query(query: str) -> str:
    query = _FY_PATTERN.sub(
        lambda m: f"fiscal year {_expand_year(m.group(1))}",
        query
    )
    query = re.sub(r'(\d),(\d)', r'\1\2', query)          # strip thousands commas
    query = re.sub(r'[\u2013\u2014\u2012\u2010]', '-', query)  # normalise dashes
    return query
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ChatVertexAI` from langchain-google-vertexai for Gemini | `ChatGoogleGenerativeAI` from langchain-google-genai | langchain-google-genai 4.0.0 (late 2025) | `ChatVertexAI` is deprecated; new code must use genai package for Gemini |
| `google-cloud-aiplatform` generative AI | `google-genai` SDK | 2025 | Requirements.md explicitly marks google-cloud-aiplatform as out of scope |
| Separate Vertex and Gemini auth paths | Unified via `GOOGLE_GENAI_USE_VERTEXAI=true` | langchain-google-genai 4.0.0 | Simplifies Gemini-on-Vertex setup; no longer need langchain-google-vertexai for Gemini |
| Sliding-window chunking | Non-overlapping spans with table-boundary extension | This project | Eliminates duplicate rows in results; tables are atomic retrieval units |

**Deprecated/outdated:**
- `ChatVertexAI`: replaced by `ChatGoogleGenerativeAI` in langchain-google-genai 4.x
- `VertexAIEmbeddings`: also deprecated (not needed in this project — BM25 only)
- `google-cloud-aiplatform` generative AI SDKs: out of scope per requirements

---

## Open Questions

1. **Claude's Vertex AI region for this GCP project**
   - What we know: `ChatAnthropicVertex` requires a region where Claude is available in Model Garden (not `global`); common regions are `us-east5`, `europe-west1`
   - What's unclear: Which region is enabled for the specific GCP project that will be used
   - Recommendation: Document as a required manual step in setup; fail hard with a clear error message that includes the region requirement; unit tests mock this away so no blocker for offline dev

2. **Tool schema strictness between Gemini and Claude adapters (Claude's Discretion)**
   - What we know: Gemini rejects open-property schemas; Claude on Vertex follows Anthropic conventions; both support `bind_tools` in LangChain
   - What's unclear: Whether a single Pydantic/TypedDict tool schema definition works for both without per-adapter translation
   - Recommendation: Define tools with fully-enumerated Pydantic `BaseModel` input schemas (no `Dict[str, Any]` fields). This satisfies both Gemini's strict schema requirement and Anthropic's conventions. No per-adapter schema translation needed if input models are explicit.

3. **Phase completion criteria (Claude's Discretion)**
   - What we know: TST-01 requires 5+ test cases per tool; TST-02 requires specific router coverage; integration tests are opt-in
   - What's unclear: Whether all unit tests must pass, or some subset
   - Recommendation: Phase complete when: (a) all unit tests pass offline (`pytest -m "not integration"`), (b) `pytest -m integration` passes against real Vertex AI for both `gemini-2.0-flash` and `claude-sonnet-4-6`, (c) ENV-01 through RET-06 requirements are met per test assertions

---

## Corpus Inspection Findings

These findings were verified by direct inspection of the corpus on 2026-03-17:

- **697 total files** in `corpus/transformed/`, naming pattern `treasury_bulletin_YYYY_MM.txt`
- **File size range:** ~1,800–4,800 lines per file (1939 bulletins ~1,800 lines; 1954 bulletins ~4,800 lines)
- **Table format:** Markdown pipe tables with `|` as first character on every data/header/separator row
- **Separator rows:** `| --- | --- | --- |` pattern; these are also pipe-prefixed
- **Multi-level headers:** Some tables have 2-3 row headers encoded as `Level1 > Level2 > Level3` within a single pipe-delimited cell
- **Footnote rows:** Appear as regular numbered lines after the last `|` row (e.g., `1/ Excludes...`); these are NOT pipe-prefixed, so they will be included in the next span naturally
- **Source files in CSVs:** 285 unique filenames across both CSVs; all 285 are present in `corpus/transformed/`
- **CSV `source_files` column:** Newline-separated (embedded `\n` inside quoted CSV cell), not comma-separated — verified by corpus diff analysis

---

## Sources

### Primary (HIGH confidence)
- PyPI: rank-bm25 0.2.2 — version, API, get_scores/get_top_n methods confirmed
- PyPI: langchain-google-genai 4.2.1 — version, last release date (2026-02-19)
- PyPI: langchain-google-vertexai 3.2.2 — version, anthropic extra, last release date (2026-01-30)
- LangChain official docs: https://docs.langchain.com/oss/python/integrations/chat/google_anthropic_vertex — ChatAnthropicVertex initialization
- LangChain official docs: https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai — ChatGoogleGenerativeAI Vertex AI init
- Direct corpus inspection — file count, line counts, table format, CSV field structure

### Secondary (MEDIUM confidence)
- GitHub discussion langchain-ai/langchain-google #1422 — langchain-google-genai 4.0.0 changes (ChatVertexAI deprecation, Vertex AI auth simplification, performance notes)
- DeepWiki langchain-google/7.1-anthropic-models-on-vertex-ai — ChatAnthropicVertex import path confirmed (`langchain_google_vertexai.model_garden`)
- pytest official docs: https://docs.pytest.org/en/stable/example/markers.html — custom marker registration

### Tertiary (LOW confidence — flag for validation)
- Claude Vertex AI region availability (`us-east5`) — sourced from GitHub issue #1256 in langchain-google repo; specific region must be confirmed against the target GCP project
- `GOOGLE_CLOUD_LOCATION=global` for ChatGoogleGenerativeAI on Vertex — ENV-05 specifies `global`; most LangChain docs default to `us-central1`; verify this works for Gemini before finalizing

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified on PyPI with current versions and release dates
- Architecture: HIGH — patterns derived from official docs + direct corpus structure inspection
- Pitfalls: HIGH for corpus/CSV findings (empirically verified); MEDIUM for region availability (single source)

**Research date:** 2026-03-17
**Valid until:** 2026-04-17 (packages stable; langchain-google moves fast — re-verify if >30 days pass)
