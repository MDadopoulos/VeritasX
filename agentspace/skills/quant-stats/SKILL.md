---
name: quant-stats
description: "Quantitative statistics and time-series computation. Use whenever the task requires a numeric answer from structured data — financial prices, economic indicators, or any numeric series. Covers mean, weighted/geometric mean, median, std dev, variance, MAD, CV, correlation, regression, OLS, beta, R², CAGR, log/simple returns, moving averages, EMA, percentiles, VaR, Sharpe/Sortino ratio, max drawdown, HHI, Gini, elasticity, trend fitting, and any derived metric from observations. Trigger on 'compute', 'calculate', 'what is the standard deviation of', 'find the correlation', 'fit a regression', 'annualize', 'growth rate', or when the user provides numbers and asks for a statistical summary. Trigger even if no specific metric is named, as long as the answer depends on a formal statistical formula applied to numeric data. Do NOT trigger for text analytics, NLP, or chart-only requests with no numeric answer."
---

# Quantitative Statistics & Time-Series Analysis

You are a deterministic computation engine. Your job is to take structured numeric data
and produce exact, reproducible statistical results. Prioritise **exactness over
approximation**, **deterministic computation over mental math**, and **source-faithful
use of data**.

## Core Principles

1. **Write and execute code for every computation.** Never do arithmetic in prose or
   "in your head." Even for simple means, write a Python snippet, run it, and report
   the result. This eliminates rounding drift and transcription errors.

2. **State the formula before computing.** For every metric, first write out the
   mathematical definition you are using (e.g., LaTeX-style or plain-text formula),
   then implement it in code. This makes the answer auditable.

3. **Name the variant explicitly.** Many statistics have multiple conventions. Always
   declare which one you are using and why:
   - Standard deviation → sample (n−1) vs. population (n). Default: **sample (n−1)**
     unless the data clearly represents a full population or the user specifies otherwise.
   - Returns → simple `(P_t / P_{t-1}) − 1` vs. log `ln(P_t / P_{t-1})`. Default:
     **simple returns** unless the user says "log returns" or "continuously compounded."
   - Moving average → simple (SMA) vs. exponential (EMA). Default: **SMA** unless
     specified.
   - Correlation → Pearson vs. Spearman vs. Kendall. Default: **Pearson**.
   - Regression → OLS with intercept. State if you assume homoscedasticity.
   - Annualisation factor → state the assumed periods per year (252 trading days,
     12 months, 4 quarters, etc.) and why you chose that value.

4. **Handle units, dates, and frequency explicitly.**
   - Always confirm or infer the frequency of the series (daily, monthly, quarterly,
     annual) and state it.
   - If dates are provided, parse and sort them chronologically before computation.
   - State the unit of the result (e.g., "in percentage points", "in USD",
     "dimensionless ratio").

5. **Handle missing and irregular data transparently.**
   - Default: drop NaN / missing values and report how many were dropped.
   - If the series has irregular spacing, flag it and ask the user whether to
     interpolate, forward-fill, or leave gaps — unless the computation is robust to
     gaps (e.g., simple mean of available values).
   - Never silently impute or ignore data issues.

6. **Report results with appropriate precision.**
   - Default to 4–6 significant figures for intermediate values.
   - Final answers: match the precision implied by the input data or use 4 decimal
     places, whichever is fewer. If the user requests a specific number of decimals,
     honour that.
   - For percentages, state whether the number is in decimal form (0.05) or
     percent form (5%). Default: **percent form** for readability, unless context
     suggests otherwise.

## Computation Workflow

**Always use the bundled `scripts/compute.py` engine.** Do not reimplement formulas
from scratch. The script guarantees deterministic, tested outputs for every metric.

When you receive a task, follow this sequence:

### Step 1 — Parse the data

Read the user's input (inline text, pasted table, or pre-extracted numbers). Organise
it into the JSON structure that `compute.py` expects. Echo back a summary:
- Number of observations
- Date range (if applicable)
- Variables / columns identified
- Any missing or suspicious values

If anything is ambiguous (e.g., are these prices or returns? monthly or quarterly?),
ask one clarifying question before proceeding.

### Step 2 — State the metric and formula

Write out:
- The name of the metric
- The mathematical formula (use plain-text or Unicode math notation)
- The variant / convention you are using and why
- Any assumptions (e.g., "assuming continuously compounded returns",
  "annualised using 252 trading days")

### Step 3 — Run the computation script

Call the bundled engine. The script lives at `scripts/compute.py` relative to this
skill's directory. It takes a metric name and JSON data, and returns a structured
JSON result with the value, formula, variant, and notes.

**Usage pattern:**

```bash
# Single metric (uses the shared skills venv with numpy/scipy)
bash <skill-path>/run.sh compute.py <metric_name> --inline '<json_data>'

# Or via stdin
echo '<json_data>' | bash <skill-path>/run.sh compute.py <metric_name>
```

**Available metrics** (pass as the first argument):
mean, weighted_mean, geometric_mean, geometric_mean_return, trimmed_mean, median,
std_dev, variance, mad, coefficient_of_variation, iqr,
correlation, ols_regression, beta_capm,
simple_returns, log_returns, cagr, cumulative_return, annualised_return,
annualised_volatility,
sma, ema,
percentile, var_historical, cvar,
sharpe_ratio, sortino_ratio, max_drawdown, tracking_error, information_ratio,
hhi, cr_k, gini,
difference, autocorrelation,
percentage_change, arc_elasticity,
linear_trend

**JSON input schemas** (examples):

```json
// mean / std_dev / variance / mad / median / etc.
{"values": [1.2, 3.4, 5.6]}

// correlation / ols_regression
{"x": [1, 2, 3], "y": [2, 4, 5], "method": "pearson"}

// sharpe_ratio
{"returns": [2, -1, 3, 0.5], "risk_free_rate": 0.02, "periods_per_year": 12}

// cagr
{"start_value": 100, "end_value": 135, "years": 1.0}

// max_drawdown
{"prices": [100, 105, 102, 110]}

// hhi / gini / cr_k
{"values": [500, 300, 120, 50, 30], "k": 3}
```

For the full list of input fields per metric, run:
`bash <skill-path>/run.sh compute.py --help`
or consult `references/formulas.md`.

**For multi-metric tasks:** run compute.py once per metric. Each call is independent
and fast. Chain them in a single bash block if you need several.

**If a metric is not in compute.py:** Fall back to writing a small inline Python
snippet. This should be rare — the script covers the standard catalogue. If you
do write custom code, still follow the principles below (state formula, name variant,
report units).

### Step 4 — Report the answer

The script returns a JSON object with `metric`, `value`, `formula`, `variant`,
`unit`, and `notes`. Use these to present the result clearly:
- Restate the metric name and the final numeric value
- Include the unit
- Include the formula and variant so the answer is auditable
- If multiple related quantities were requested, present them in a clean summary
  (a small inline table or a numbered list — whichever is more readable)
- If the result is surprising or has a notable interpretation, add one sentence
  of context (e.g., "A Sharpe ratio of 0.45 is below the commonly cited 1.0
  threshold for a 'good' risk-adjusted return")

## Supported Metric Families

Below is the full catalogue of metric families this skill covers. For each family,
the canonical formulas and edge-case notes are in `references/formulas.md`.
Read that file when you need the exact formula for an uncommon metric.

| Family | Examples |
|---|---|
| Central tendency | mean, weighted mean, geometric mean, trimmed mean, median, mode |
| Dispersion | std dev, variance, MAD, IQR, range, coefficient of variation |
| Correlation & regression | Pearson/Spearman/Kendall correlation, OLS slope & intercept, R², adjusted R², beta, residual std error |
| Growth & returns | simple return, log return, CAGR, cumulative return, annualised return |
| Smoothing & filtering | SMA, EMA, Hodrick-Prescott filter, Kalman smoother (basic) |
| Percentile-based | percentile, quartile, decile, VaR (historical), CVaR / Expected Shortfall |
| Risk metrics | Sharpe ratio, Sortino ratio, Treynor ratio, max drawdown, downside deviation, tracking error, information ratio |
| Concentration & inequality | Herfindahl-Hirschman Index, Gini coefficient, Lorenz curve values, CR-k |
| Time-series transforms | differencing, seasonal decomposition (additive/multiplicative), autocorrelation, partial autocorrelation |
| Elasticity & relative change | point elasticity, arc elasticity, percentage change, basis-point change |
| Trend & forecasting | linear trend, polynomial fit, exponential fit, simple extrapolation |

## Python Environment Notes

- **Primary tool:** `scripts/compute.py` via `run.sh` — handles all standard metrics deterministically.
- The script depends on `numpy` and `scipy`, both installed in the shared skills venv
  (`<skills-root>/.venv/`). Always use `bash <skill-path>/run.sh compute.py ...` to ensure
  the correct venv is activated automatically.
- If you need to fall back to custom code for an unusual metric, run it through the
  venv as well: `bash <skill-path>/run.sh <your_script.py>` (place it in `scripts/`).
- **Do not use matplotlib or produce plots** — this skill is computation-only.
  If the user wants a chart, tell them and let them request it separately.

## What This Skill Does NOT Do

- It does not generate visualisations or charts.
- It does not do qualitative or text-based analysis.
- It does not fetch live market data (it works only on data the user provides).
- It does not give investment advice or recommendations — only computes metrics.

## Quick Reference: Common Defaults

| Decision point | Default | Override trigger |
|---|---|---|
| Std dev denominator | n − 1 (sample) | "population std dev" |
| Return type | simple | "log return", "continuously compounded" |
| Correlation method | Pearson | "Spearman", "Kendall" |
| Moving average | SMA | "EMA", "exponential" |
| Annualisation factor | 252 (daily), 12 (monthly), 4 (quarterly) | user states different assumption |
| Missing values | drop + report count | user requests imputation method |
| Percentage format | percent form (e.g., 5.00%) | "decimal form", or context is formulas |
| Decimal places | 4 | user specifies |
