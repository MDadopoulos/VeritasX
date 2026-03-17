---
status: complete
phase: 01-environment-retrieval-foundation
source: [01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md]
started: 2026-03-18T00:00:00Z
updated: 2026-03-18T01:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Default MODEL_ID is claude-sonnet-4-6
expected: get_config() with MODEL_ID unset returns model_id == "claude-sonnet-4-6"
result: pass

### 2. Missing GOOGLE_CLOUD_PROJECT raises RuntimeError
expected: get_config() with no GOOGLE_CLOUD_PROJECT env var raises RuntimeError with a clear message about the missing project ID
result: pass

### 3. Model adapter dispatches gemini prefix
expected: get_model() with MODEL_ID=gemini-2.0-flash returns a ChatGoogleGenerativeAI instance
result: pass
note: verified via 110-test suite (test_model_adapter.py)

### 4. Model adapter dispatches claude prefix
expected: get_model() with MODEL_ID=claude-sonnet-4-6 returns a ChatAnthropicVertex instance
result: pass
note: verified via 110-test suite (test_model_adapter.py)

### 5. Unsupported MODEL_ID raises ValueError
expected: get_model() with MODEL_ID=gpt-4 raises ValueError with message containing "gpt-4"
result: pass
note: verified via 110-test suite (test_model_adapter.py)

### 6. Corpus manifest reports 285 files
expected: load_manifest(['../officeqa_full.csv', '../officeqa_pro.csv']) returns exactly 285 unique filenames
result: pass
note: verified via test_corpus_manifest.py::test_manifest_returns_285_unique_files

### 7. Corpus manifest fails hard on missing files in local mode
expected: validate_corpus() with a temp corpus dir missing 1 file raises SystemExit(1) and prints WARNING to stderr
result: pass
note: verified via test_corpus_manifest.py::test_missing_file_raises_system_exit_in_local_mode

### 8. route_files maps FY 1940 to Oct 1939 – Sep 1940
expected: route_files("FY 1940 defense expenditures") returns 12 paths. First path contains "1939_10", last contains "1940_09". All paths exist on disk.
result: pass
note: verified directly — 12 paths, treasury_bulletin_1939_10.txt → treasury_bulletin_1940_09.txt

### 9. route_files returns calendar year 1941 paths
expected: route_files("1941 national defense") returns 12 paths, all named treasury_bulletin_1941_XX.txt, all existing on disk
result: pass
note: verified via test_route_files.py

### 10. route_files returns no hallucinated paths
expected: Every path in route_files("FY 1940 defense") is a real file that exists at corpus/transformed/.
result: pass
note: verified via test_route_files.py::test_no_hallucinated_filenames

### 11. route_files returns error dict for no-year questions
expected: route_files("What is GDP?") returns {"error": "no_year_found", "question": "What is GDP?"}
result: pass
note: verified directly — output: {'error': 'no_year_found', 'question': 'What is GDP?'}

### 12. search_in_file returns BM25-ranked spans for defense query
expected: search_in_file(fixture, "national defense expenditures 1940") returns list with ≥1 result, first result contains "defense", bm25_score > 0
result: pass
note: verified directly — 5 results, score 4.58, defense in text: True

### 13. Spans never split tables
expected: The 48-row table at lines 317-364 in the fixture is entirely contained in a single span
result: pass
note: verified via test_search_in_file.py::test_table_longer_than_20_lines_in_single_span

### 14. Regex fallback and no-results error
expected: search_in_file(fixture, "xyzzyplugh") returns {"error": "no_results", ...} with query echoed back
result: pass
note: verified directly — {'error': 'no_results', 'query': 'xyzzyplugh', 'spans_searched': 12}

### 15. Each search result has full metadata
expected: Every result contains: text, source_file (absolute path), start_line, end_line, bm25_score, regex_fallback
result: pass
note: verified directly — keys: ['bm25_score', 'end_line', 'regex_fallback', 'source_file', 'start_line', 'text']

## Summary

total: 15
passed: 15
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
