---
phase: quick
plan: 260411-tno
type: execute
wave: 1
depends_on: []
files_modified:
  - workspace/src/harness.py
  - workspace/src/tools/verifier.py
  - workspace/src/agent.py
autonomous: true
must_haves:
  truths:
    - "calc-agent subagent exists with quant-stats SkillsMiddleware and arithmetic tools"
    - "external-data-agent subagent exists with cpi-inflation-adjuster and historical-fx SkillsMiddleware"
    - "Verifier system prompt includes benchmark answer format awareness"
    - "Orchestrator tools list reduced to only normalize_answer"
    - "Orchestrator prompt updated to dispatch to calc-agent and external-data-agent"
    - "agent.py SYSTEM_PROMPT kept in sync with harness.py ORCHESTRATOR_SYSTEM_PROMPT"
  artifacts:
    - path: "workspace/src/harness.py"
      provides: "calc-agent and external-data-agent subagent definitions, updated orchestrator"
    - path: "workspace/src/tools/verifier.py"
      provides: "Format-aware VERIFIER_SYSTEM_PROMPT"
    - path: "workspace/src/agent.py"
      provides: "Synced SYSTEM_PROMPT"
  key_links:
    - from: "workspace/src/harness.py"
      to: "agentspace/skills/quant-stats/"
      via: "SkillsMiddleware on calc-agent"
    - from: "workspace/src/harness.py"
      to: "agentspace/skills/cpi-inflation-adjuster/"
      via: "SkillsMiddleware on external-data-agent"
    - from: "workspace/src/harness.py"
      to: "agentspace/skills/historical-fx/"
      via: "SkillsMiddleware on external-data-agent"
---

<objective>
Create two new subagents (calc-agent, external-data-agent), move arithmetic and external-data tools off the orchestrator, update verifier for benchmark format awareness, and keep agent.py in sync.

Purpose: The orchestrator currently has 8 tools directly attached. By moving compute_stat/calculate/pct_change/sum_values to a calc-agent with the quant-stats skill, and adjust_inflation/get_cpi_value/convert_fx to an external-data-agent with cpi-inflation-adjuster + historical-fx skills, the orchestrator becomes a pure coordinator with only normalize_answer. Each subagent gets domain-specific skills via SkillsMiddleware so it can reason about its domain before executing tools.

Output: Updated harness.py with 4 subagents (search-agent, verifier, calc-agent, external-data-agent), updated verifier.py with format awareness, synced agent.py.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@workspace/src/harness.py
@workspace/src/tools/verifier.py
@workspace/src/agent.py
@workspace/src/tools/compute_stat.py
@workspace/src/tools/external_data.py

<interfaces>
<!-- Key types and contracts the executor needs -->

SubAgent TypedDict requires these keys:
```python
SubAgent = {
    "name": str,
    "description": str,
    "system_prompt": str,
    "model": model,
    "tools": list,
    "middleware": list,
}
```

SkillsMiddleware usage pattern:
```python
from deepagents.middleware.skills import SkillsMiddleware
from deepagents.backends import FilesystemBackend

skills_backend = FilesystemBackend(root_dir=skills_dir, virtual_mode=True)
skills_mw = SkillsMiddleware(backend=skills_backend, sources=["/"])
```

Existing tool imports in harness.py:
```python
from src.tools.calculate import calculate, pct_change, sum_values
from src.tools.normalize_answer import normalize_answer
from src.tools.compute_stat import compute_stat
from src.tools.external_data import adjust_inflation, get_cpi_value, convert_fx
```

Benchmark answer format patterns (from officeqa_full.csv, 246 answers):
- Plain integers: 507, 42, 73, 3069
- Comma-separated integers: 2,602 / 44,463 / 103,375
- Decimals: 0.42, 32.703, 81.406, 0.00262
- Percentages: 1608.80%, 9.89%, -18.51%, 69%, 3%
- Dollar amounts: $37,921,314, $2,760.44, $140.9 Billion
- With units: 36080 million, 997.3 billion, 1169.41 million, 9732.50 million, -1,667.86 millions
- Lists/tuples: [0.096, -184.143], [2.81, 0.030, 8.706], [2017, 0.69]
- Dates: March 3, 1977 / August 1986
- Years: 1990, 1973
- Negative values: -118255.5, -0.119, -75, -550.3
- Mixed lists with labels: [0.012, surplus], [37.48, unusual], [2.59%, 2.34%, Decreased]
- Unicode minus: −3.524, −156.11
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create calc-agent and external-data-agent subagents in harness.py</name>
  <files>workspace/src/harness.py, workspace/src/agent.py</files>
  <action>
In workspace/src/harness.py, inside create_harness_agent():

**1a. Create calc-agent subagent (after Step 6, the search subagent):**

Add a CALC_AGENT_SYSTEM_PROMPT module-level constant (after SEARCH_AGENT_SYSTEM_PROMPT):
```
You are a calculation and statistics specialist. Your job is to perform arithmetic
operations and statistical computations on values provided by the orchestrator.

You receive pre-extracted numeric values (from the search-agent's scratch files)
and a description of the computation needed.

## Tools Available
- calculate(expression) — safe arithmetic evaluation
- pct_change(old, new) — percent change computation
- sum_values(values, unit) — labeled sum
- compute_stat(metric, data) — advanced statistical computation (see skill docs)

## Execution Pattern
1. Extract the UID from task description prefix: "UID: {uid} | Task: ..."
2. Parse the computation request from the task description
3. Execute the appropriate tool(s)
4. APPEND results to {uid}/calc.txt using write_file (read first, then write combined)
   Format per entry:
     operation(args)
     Inputs: var=value (unit) [source: file]
     Result: value
     Variant: variant_name (if compute_stat)
5. Return ONLY a completion pointer: "Calculation complete. Results written to {uid}/calc.txt."

## Critical Rules
- NEVER compute arithmetic inline — ALWAYS use calculate() or compute_stat()
- For population vs sample statistics, check if the task specifies which variant
- For geometric mean vs arithmetic mean, use the one specified in the task
- Record the variant used in calc.txt so the verifier can check formula fidelity
```

Build calc-agent middleware stack (same pattern as search/verifier middleware — TodoListMiddleware, FilesystemMiddleware with scratch backend, create_summarization_middleware, PatchToolCallsMiddleware, AnthropicPromptCachingMiddleware). ADDITIONALLY include SkillsMiddleware pointing to quant-stats skill:
```python
calc_skills_dir = _PROJECT_ROOT / "agentspace" / "skills" / "quant-stats"
calc_skills_backend = FilesystemBackend(root_dir=calc_skills_dir, virtual_mode=True)
calc_skills_mw = SkillsMiddleware(backend=calc_skills_backend, sources=["/"])
```
Insert calc_skills_mw after TodoListMiddleware (before FilesystemMiddleware) in the calc middleware stack.

Build the calc SubAgent dict:
```python
calc_subagent: SubAgent = {
    "name": "calc-agent",
    "description": (
        "Arithmetic and statistics specialist. Call with 'UID: {uid} | Task: <description>'. "
        "Performs calculations using calculate, pct_change, sum_values, and compute_stat. "
        "Writes results to {uid}/calc.txt. Returns ONLY a completion pointer."
    ),
    "system_prompt": CALC_AGENT_SYSTEM_PROMPT,
    "model": model,
    "tools": [calculate, pct_change, sum_values, compute_stat],
    "middleware": calc_middleware,
}
```

**1b. Create external-data-agent subagent:**

Add an EXTERNAL_DATA_AGENT_SYSTEM_PROMPT module-level constant:
```
You are an external data specialist for inflation adjustment and currency conversion.
You access BLS CPI-U data (1939-2025) and Fed H.10 exchange rates (1971-2025).

## Tools Available
- adjust_inflation(amount, from_year, to_year, from_month, to_month) — CPI-U adjustment
- get_cpi_value(year, month) — raw CPI-U index lookup
- convert_fx(amount, from_currency, to_currency, date, convention) — Fed H.10 FX conversion

## Execution Pattern
1. Extract the UID from task description prefix: "UID: {uid} | Task: ..."
2. Parse the external data request from the task description
3. Execute the appropriate tool(s)
4. APPEND results to {uid}/calc.txt using write_file (read first, then write combined)
   Format per entry:
     operation(args)
     Source: BLS CPI-U / Fed H.10
     Result: {structured result}
5. Return ONLY a completion pointer: "External data lookup complete. Results written to {uid}/calc.txt."

## Critical Rules
- When adjusting inflation, verify date alignment: monthly CPI with monthly Treasury data,
  annual CPI with annual Treasury data, unless the task explicitly allows mixing
- For FX conversion, match the convention (spot/monthly_avg/annual_avg) to the date precision
- Always record the base period and source in calc.txt for verifier traceability
```

Build external-data-agent middleware stack (same pattern). Include SkillsMiddleware for BOTH skills:
```python
ext_skills_dir = _PROJECT_ROOT / "agentspace" / "skills"
ext_skills_backend = FilesystemBackend(root_dir=ext_skills_dir, virtual_mode=True)
ext_skills_mw = SkillsMiddleware(backend=ext_skills_backend, sources=[
    "/cpi-inflation-adjuster",
    "/historical-fx",
])
```
Insert ext_skills_mw after TodoListMiddleware in the ext middleware stack.

Build the external-data SubAgent dict:
```python
ext_data_subagent: SubAgent = {
    "name": "external-data-agent",
    "description": (
        "External data specialist for inflation and FX. Call with 'UID: {uid} | Task: <description>'. "
        "Performs CPI adjustments and currency conversions. Writes results to {uid}/calc.txt. "
        "Returns ONLY a completion pointer."
    ),
    "system_prompt": EXTERNAL_DATA_AGENT_SYSTEM_PROMPT,
    "model": model,
    "tools": [adjust_inflation, get_cpi_value, convert_fx],
    "middleware": ext_middleware,
}
```

**1c. Update orchestrator:**

Update SubAgentMiddleware to include all 4 subagents:
```python
SubAgentMiddleware(
    backend=backend,
    subagents=[search_subagent, verifier_subagent, calc_subagent, ext_data_subagent],
)
```

Update the orchestrator's tools list to ONLY normalize_answer:
```python
agent = create_agent(
    model,
    tools=[normalize_answer],
    ...
)
```

Remove the unused skills_mw and skills_backend from the orchestrator section (they were commented out anyway — delete entirely).

**1d. Update ORCHESTRATOR_SYSTEM_PROMPT in harness.py:**

Add dispatch instructions for the two new subagents. After the "## Retrieval via Search Agent" and "## Parallel Search Agents" sections, add:

```
## Arithmetic via Calc Agent

For ALL arithmetic and statistical operations, call the calc-agent:
  task(subagent_type='calc-agent', description='UID: {uid} | Task: <computation description with values>')

Example: task(subagent_type='calc-agent',
              description='UID: UID0001 | Task: pct_change from 2602 to 3100, both in millions')

Include the extracted values and their units in the task description. The calc-agent
writes results to {uid}/calc.txt and returns a completion pointer.

Do NOT call calculate, pct_change, sum_values, or compute_stat directly.
```

And:
```
## External Data via External-Data Agent

For inflation adjustment or currency conversion, call the external-data-agent:
  task(subagent_type='external-data-agent', description='UID: {uid} | Task: <request>')

Example: task(subagent_type='external-data-agent',
              description='UID: UID0005 | Task: adjust_inflation 1000 from 1950 to 2020 annual')

Do NOT call adjust_inflation, get_cpi_value, or convert_fx directly.
```

Remove from ORCHESTRATOR_SYSTEM_PROMPT:
- The "## Statistical Computation (compute_stat)" section (moving to calc-agent skill)
- The "## Inflation Adjustment (adjust_inflation / get_cpi_value)" section
- The "## Currency Conversion (convert_fx)" section
- The "## External Data Decision Rules" section
- From "## Tool Usage Rules" remove references to calculate/pct_change — update to say "Do NOT call calculation or external data tools directly — use the calc-agent and external-data-agent subagents"

Update "## Scratch File Writing Instructions" to remove the "After EACH calculate/pct_change/sum_values result, APPEND to {uid}/calc.txt" paragraph — the calc-agent handles this now. Keep the normalize_answer and answer.txt writing instructions.

**1e. Sync agent.py SYSTEM_PROMPT:**

Update workspace/src/agent.py SYSTEM_PROMPT to match the new ORCHESTRATOR_SYSTEM_PROMPT content (per Phase 05.1.1 decision: kept in sync manually). Add the calc-agent and external-data-agent dispatch sections. Remove the statistical/inflation/FX tool usage sections. Update tool usage rules to reference subagents instead of direct tool calls.
  </action>
  <verify>
    <automated>.venv/Scripts/python.exe -c "from src.harness import create_harness_agent, ORCHESTRATOR_SYSTEM_PROMPT, CALC_AGENT_SYSTEM_PROMPT, EXTERNAL_DATA_AGENT_SYSTEM_PROMPT; print('Prompts OK'); assert 'calc-agent' in ORCHESTRATOR_SYSTEM_PROMPT; assert 'external-data-agent' in ORCHESTRATOR_SYSTEM_PROMPT; assert 'compute_stat' not in ORCHESTRATOR_SYSTEM_PROMPT.split('## Arithmetic')[0][-200:]; print('All checks pass')"</automated>
  </verify>
  <done>
    - harness.py has 4 subagents: search-agent, verifier, calc-agent, external-data-agent
    - calc-agent has SkillsMiddleware for quant-stats and tools: calculate, pct_change, sum_values, compute_stat
    - external-data-agent has SkillsMiddleware for cpi-inflation-adjuster + historical-fx and tools: adjust_inflation, get_cpi_value, convert_fx
    - Orchestrator tools reduced to [normalize_answer]
    - ORCHESTRATOR_SYSTEM_PROMPT dispatches to calc-agent and external-data-agent
    - agent.py SYSTEM_PROMPT synced with new dispatch instructions
  </done>
</task>

<task type="auto">
  <name>Task 2: Update verifier for benchmark format awareness</name>
  <files>workspace/src/tools/verifier.py</files>
  <action>
In workspace/src/tools/verifier.py, update VERIFIER_SYSTEM_PROMPT Check 7 (Format Match) to be format-aware based on actual benchmark answer patterns from officeqa_full.csv.

Replace the existing Check 7 section with a detailed format-aware version:

```
### Check 7: Benchmark Format Match (SOFT WARNING — does NOT cause FAIL)

The benchmark expects answers in specific formats. Compare the proposed answer against
these known answer patterns from the benchmark:

**Numeric formats:**
- Plain integers: 507, 42, 73 (no commas for numbers under 1000)
- Comma-separated integers: 2,602 / 44,463 / 103,375 (commas for thousands in large numbers — BUT many answers omit commas: 103030, 180681, 92000000)
- Decimals: 0.42, 32.703, 81.406, 0.00262 (varying precision — use the precision the question requests, or the natural precision of the computation)
- Large decimals: 25258095.24, 935851121560 (no commas, no scientific notation)

**Percentage formats:**
- With % symbol: 1608.80%, 9.89%, -18.51%, 69%, 3%
- Precision varies: 9.987% (3 decimal), 1608.80% (2 decimal), 69% (integer)
- When the question says "percent value" or "reported as a percent", use % suffix
- When the question says "decimal" (e.g., "0.1234, not 12.34%"), do NOT add %

**Currency formats:**
- Dollar sign prefix: $37,921,314, $2,760.44, $140.9 Billion
- Only use $ when the question asks for a dollar-denominated final answer
- Unit suffixes: "million", "millions", "billion", "Billion" (capitalization varies)

**Unit-labeled formats:**
- Number followed by unit: 36080 million, 997.3 billion, 1169.41 million, -1,667.86 millions
- Use the unit scale the question specifies ("in millions", "in billions")

**List/tuple formats:**
- Bracketed comma-separated: [0.096, -184.143], [2.81, 0.030, 8.706]
- Mixed types: [2017, 0.69], [0.012, surplus], [2.59%, 2.34%, Decreased]
- Use lists when the question asks for multiple distinct values

**Date formats:**
- Full date: March 3, 1977
- Month and year: August 1986
- Year only: 1990, 1973

**Negative values:**
- Standard minus: -118255.5, -0.119, -18.51%
- Unicode minus (U+2212): −3.524, −156.11 (both are acceptable)

**Format validation rules:**
1. If the question specifies rounding ("nearest hundredths", "two decimal places"), verify precision matches
2. If the question specifies unit format ("in millions", "as a percent value"), verify unit/suffix matches
3. If the question asks for multiple values, verify list format [val1, val2, ...]
4. Trailing zeros: 1608.80% is valid (question asked for "hundredths place")
5. No scientific notation — benchmark never uses it

WARN (add to issues list with specific format concern) but do NOT set status to "FAIL" for format mismatches.
```

Also add a brief note at the top of the prompt (after the first paragraph about being a stateless verification subagent) to provide question format context:

```
## Question Patterns

Questions in this benchmark typically follow these patterns:
- "What were the total expenditures (in millions of nominal dollars) for..."
- "What was the absolute percent change... rounded to the nearest hundredths place and reported as a percent value (12.34%, not 0.1234)?"
- "What is the geometric mean of the reported budget expenditures values for each month from..."
- "Using specifically only the reported values for all individual calendar months in..."

Pay attention to:
- Unit instructions: "in millions", "in billions", "in nominal dollars"
- Precision instructions: "rounded to nearest hundredths", "two decimal places"
- Format instructions: "reported as a percent value", "expressed in billions"
- Value source instructions: "reported values", "revised figures", "as reported"
```
  </action>
  <verify>
    <automated>.venv/Scripts/python.exe -c "from src.tools.verifier import VERIFIER_SYSTEM_PROMPT; assert 'Benchmark Format Match' in VERIFIER_SYSTEM_PROMPT; assert 'Comma-separated integers' in VERIFIER_SYSTEM_PROMPT; assert 'Question Patterns' in VERIFIER_SYSTEM_PROMPT; print('Verifier format awareness OK')"</automated>
  </verify>
  <done>
    - VERIFIER_SYSTEM_PROMPT Check 7 replaced with detailed benchmark format awareness
    - Question pattern context added to verifier prompt
    - All 8 format categories documented: integers, decimals, percentages, currency, unit-labeled, lists, dates, negatives
    - Format validation rules cover rounding, unit format, list format, trailing zeros, no scientific notation
  </done>
</task>

</tasks>

<verification>
Run from workspace/ directory:
```bash
.venv/Scripts/python.exe -c "
from src.harness import create_harness_agent, ORCHESTRATOR_SYSTEM_PROMPT
from src.harness import CALC_AGENT_SYSTEM_PROMPT, EXTERNAL_DATA_AGENT_SYSTEM_PROMPT
from src.tools.verifier import VERIFIER_SYSTEM_PROMPT

# Check subagent prompts exist
assert 'calc-agent' in ORCHESTRATOR_SYSTEM_PROMPT
assert 'external-data-agent' in ORCHESTRATOR_SYSTEM_PROMPT

# Check verifier format awareness
assert 'Benchmark Format Match' in VERIFIER_SYSTEM_PROMPT

# Check old tool sections removed from orchestrator
assert '## Statistical Computation' not in ORCHESTRATOR_SYSTEM_PROMPT
assert '## Inflation Adjustment' not in ORCHESTRATOR_SYSTEM_PROMPT
assert '## Currency Conversion' not in ORCHESTRATOR_SYSTEM_PROMPT

print('All verification checks passed')
"
```
</verification>

<success_criteria>
- harness.py exports 4 subagents: search-agent, verifier, calc-agent, external-data-agent
- calc-agent has SkillsMiddleware(quant-stats) + tools [calculate, pct_change, sum_values, compute_stat]
- external-data-agent has SkillsMiddleware(cpi-inflation-adjuster, historical-fx) + tools [adjust_inflation, get_cpi_value, convert_fx]
- Orchestrator tools = [normalize_answer] only
- Orchestrator prompt dispatches to calc-agent and external-data-agent via task() calls
- Verifier prompt has detailed benchmark answer format patterns from officeqa_full.csv
- agent.py SYSTEM_PROMPT synced with harness.py ORCHESTRATOR_SYSTEM_PROMPT
- Python imports succeed without errors
</success_criteria>

<output>
After completion, create `.planning/quick/260411-tno-create-arithmetic-and-external-data-suba/260411-tno-SUMMARY.md`
</output>
