# Quick Task 260411-tno: Summary

## Task
Create arithmetic and external-data subagents, update verifier for benchmark format awareness

## Changes

### Task 1: Create calc-agent and external-data-agent subagents
**Files:** workspace/src/harness.py, workspace/src/agent.py
**Commit:** 79c51cc

- Added `CALC_AGENT_SYSTEM_PROMPT` — calculation/statistics specialist with quant-stats SkillsMiddleware
- Added `EXTERNAL_DATA_AGENT_SYSTEM_PROMPT` — CPI/FX specialist with cpi-inflation-adjuster + historical-fx SkillsMiddleware
- Built middleware stacks for both subagents (TodoList, Skills, Filesystem, Summarization, PatchToolCalls, AnthropicPromptCaching)
- calc-agent tools: [calculate, pct_change, sum_values, compute_stat]
- external-data-agent tools: [adjust_inflation, get_cpi_value, convert_fx]
- SubAgentMiddleware now has 4 subagents: search-agent, verifier, calc-agent, external-data-agent
- Orchestrator tools reduced to [normalize_answer]
- ORCHESTRATOR_SYSTEM_PROMPT updated: added calc-agent and external-data-agent dispatch sections, removed inline tool documentation
- agent.py SYSTEM_PROMPT synced with orchestrator prompt

### Task 2: Update verifier for benchmark format awareness
**Files:** workspace/src/tools/verifier.py
**Commit:** ddd0733

- Added "Question Patterns" section to VERIFIER_SYSTEM_PROMPT with common question format patterns
- Replaced Check 7 (Format Match) with detailed "Benchmark Format Match" section covering all 8 format categories from officeqa_full.csv
- Format categories: plain integers, comma-separated integers, decimals, percentages, currency, unit-labeled, lists/tuples, dates, negatives
- Added format validation rules for rounding, unit format, list format, trailing zeros, no scientific notation

## Metrics
- Tasks: 2/2 complete
- Files modified: 5 (harness.py, agent.py, verifier.py, compute_stat.py, external_data.py)
- Duration: ~8min
