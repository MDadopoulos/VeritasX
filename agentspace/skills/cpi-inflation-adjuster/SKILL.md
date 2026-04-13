---
name: cpi-inflation-adjuster
description: Deterministic inflation adjustment using bundled BLS CPI-U data (1939–2025, monthly + annual).Converts nominal dollars to constant/real dollars, compares purchasing power across years,and normalizes time-series values to a common base. Use this skill whenever the user asks aboutinflation adjustment, real vs nominal dollars, constant dollars, purchasing power, CPI conversion,"what would X cost today", "how much was Y worth in Z year", adjusting salaries/prices/budgetsfor inflation, or normalizing financial data to a base year. Also trigger for any mention ofCPI-U, Consumer Price Index lookups, or requests to deflate/inflate dollar amounts. This skill uses local data — no API calls, no web search needed.
---

# CPI-U Inflation Adjuster

Convert nominal dollar amounts to real (constant) dollars using BLS CPI-U data.
All data is bundled locally — this is a fully deterministic, offline computation.

## When to use this skill

- "What is $100 from 1980 worth today?"
- "Adjust this salary series for inflation"
- "Convert to 2020 constant dollars"
- "What was the CPI in March 2008?"
- "Compare purchasing power between 1960 and 2024"
- Any deflation/inflation of dollar amounts across time

## Data coverage

- **Annual averages**: 1939–2025
- **Monthly CPI-U**: 1939–2025 (plus Jan–Feb 2026)
- **Base period**: 1982–1984 = 100 (standard BLS base)
- **Source**: BLS CPI-U via Minneapolis Fed / usinflationcalculator.com
- **Note**: October 2025 is unavailable due to the 2025 BLS lapse in appropriations

The data file is at `data/cpi_u.json` relative to this skill's directory.

## How to perform adjustments

### Formula

The core conversion is:

```
Adjusted Amount = Original Amount × (Target CPI / Origin CPI)
```

Where CPI values can be either monthly or annual averages depending on the user's request.

### Using the script

Run via `run.sh` which activates the shared skills venv automatically.

**Single amount:**
```bash
bash <skill-path>/run.sh adjust.py --amount 100 --from-year 1980 --to-year 2024
```

**With monthly precision:**
```bash
bash <skill-path>/run.sh adjust.py --amount 100 --from-year 1980 --from-month Jun --to-year 2024 --to-month Jan
```

**Constant-dollar base (e.g., express in year-2000 dollars):**
```bash
bash <skill-path>/run.sh adjust.py --amount 100 --from-year 1980 --to-year 2024 --base-year 2000
```

**Batch series (JSON input):**
```bash
bash <skill-path>/run.sh adjust.py --series '[{"year":2000,"value":50000},{"year":2010,"value":65000},{"year":2020,"value":80000}]' --to-year 2024
```

**JSON output (for programmatic use):**
```bash
bash <skill-path>/run.sh adjust.py --amount 100 --from-year 1980 --to-year 2024 --json
```

### Month formats accepted

The script is flexible with month inputs: `Jan`, `january`, `1`, `01` all work.

### Direct data lookup

If the user just wants a raw CPI value (not a conversion), read `data/cpi_u.json` directly:
- `annual_average["2024"]` → 313.689
- `monthly["2024"]["Jun"]` → 314.175

### Inline computation (without the script)

For simple one-off calculations, you can compute directly without running the script:

1. Look up the two CPI values from `data/cpi_u.json`
2. Apply: `result = amount × (target_cpi / origin_cpi)`
3. Round to 2 decimal places

This is useful when you want to show the math step-by-step to the user.

## Response guidelines

- Always state the CPI values used and the year/month so the user can verify
- If the user says just a year (no month), use the annual average
- If the user specifies a month, use the monthly CPI
- When the user says "today" or "current dollars", use the most recent available data (2025 annual avg or latest monthly)
- For series/batch adjustments, present results in a clean table
- Mention the BLS base period (1982-84 = 100) if the user asks about raw CPI values
- If a requested date is outside the data range (before 1939 or a future month not yet available), say so clearly

## Updating the data

The bundled data goes through 2025 (annual) and Feb 2026 (monthly). To update:
1. Fetch the latest BLS CPI-U supplemental file from https://www.bls.gov/cpi/tables/supplemental-files/
2. Add new rows to `data/cpi_u.json` in both `annual_average` and `monthly` sections
3. Update the `metadata.last_updated` field
