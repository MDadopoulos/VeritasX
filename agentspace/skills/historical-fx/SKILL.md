---
name: historical-fx
description: Deterministic historical FX conversion using bundled Fed H.10 data. Covers 25+ currencieswith daily, monthly, and annual rates from 1971–2025. Supports spot, first-of-month,monthly average, annual average, and cross-rate conversions via USD triangulation. HandlesDEM-to-EUR auto-chaining (fixed 1.95583 rate). Use whenever the user asks about historicalexchange rates, FX conversion at a past date, "what was X in Y currency on Z date","convert USD to JPY in March 2015", "DEM to USD in 1995", cross-rates like "GBP to JPY",or mentions "spot rate", "monthly average", "annual average", "not seasonally adjusted","H.10", or "noon buying rate". Also handles batch/series conversions. Local data only — no API calls or web search needed.
---

# Historical FX Converter

Convert amounts between currencies at historical exchange rates using Federal Reserve H.10 data.
All data is bundled locally — fully deterministic, offline computation.

## When to use this skill

- "What was the USD/JPY rate on March 15, 2008?"
- "Convert $1000 to GBP using the monthly average for June 2020"
- "How many Deutsche Marks was $500 worth in 1995?"
- "What's the annual average GBP/JPY cross rate for 2019?"
- "Convert this series of USD amounts to CAD at each date"
- Any historical FX lookup, currency conversion at a past date, or rate comparison over time
- Questions mentioning "not seasonally adjusted" — FX rates from the Fed are inherently NSA;
  the skill recognizes this and confirms it to the user rather than erroring

## Data coverage

- **Source**: Federal Reserve H.10 / G.5 release (noon buying rates in New York)
- **Daily rates**: 1971-01-04 through ~2025 (varies by currency; some start later)
- **Monthly averages**: Averages of available daily rates within each month
- **Annual averages**: Averages of available daily rates within each year
- **Currencies**: 25+ including AUD, BRL, CAD, CNY, DKK, EUR, GBP, HKD, INR, JPY, KRW,
  MYR, MXN, NZD, NOK, SGD, ZAR, LKR, SEK, CHF, TWD, THB, VEB/VEF, and legacy
  currencies (DEM, FRF, ITL, etc.) via the EUR auto-chain
- **Quote convention**: Most rates are "foreign currency units per 1 USD." Exceptions:
  GBP, EUR, AUD, NZD are quoted as "USD per 1 unit of foreign currency."
- **DEM (Deutsche Mark)**: Native data 1971–1998. For dates 1999+, the skill auto-chains
  through EUR using the irrevocable conversion rate of 1 EUR = 1.95583 DEM.

The data files live in `data/` relative to this skill's directory:
- `data/daily.json` — daily spot rates keyed by ISO date
- `data/monthly.json` — monthly averages keyed by YYYY-MM
- `data/annual.json` — annual averages keyed by YYYY
- `data/metadata.json` — currency metadata (name, quote direction, start date, FRED series ID)

## How to perform conversions

### Understanding conventions

Users may ask for rates using different conventions. Here's how to map them:

| User says | Convention | Data source |
|---|---|---|
| "spot rate", "on [date]", "rate for March 15" | `spot` | `daily.json` — exact date |
| "first of month", "beginning of month" | `first_of_month` | `daily.json` — first available trading day of the month |
| "monthly average", "average for March 2020" | `monthly_avg` | `monthly.json` |
| "annual average", "average for 2020", just a year | `annual_avg` | `annual.json` |
| "not seasonally adjusted", "NSA" | Any of the above | All H.10 FX data is NSA — confirm this to the user |

If the user gives only a year (no month or day), default to `annual_avg`.
If they give a year and month but no day, default to `monthly_avg`.
If they give a full date, default to `spot`.

### Using the script

Run via `run.sh` which activates the shared skills venv automatically.

**Single spot conversion:**
```bash
bash <skill-path>/run.sh convert.py --amount 1000 --from USD --to JPY --date 2020-03-15
```

**Monthly average:**
```bash
bash <skill-path>/run.sh convert.py --amount 1000 --from USD --to GBP --date 2020-06 --convention monthly_avg
```

**Annual average:**
```bash
bash <skill-path>/run.sh convert.py --amount 1000 --from USD --to CAD --date 2019 --convention annual_avg
```

**First of month:**
```bash
bash <skill-path>/run.sh convert.py --amount 500 --from USD --to INR --date 2018-07 --convention first_of_month
```

**Cross-rate (non-USD pair):**
```bash
bash <skill-path>/run.sh convert.py --amount 1000 --from GBP --to JPY --date 2020-03-15
```
Cross-rates are computed via USD triangulation: GBP -> USD -> JPY.

**DEM conversion (auto-chains through EUR after 1998):**
```bash
bash <skill-path>/run.sh convert.py --amount 500 --from USD --to DEM --date 1995-06-15
bash <skill-path>/run.sh convert.py --amount 500 --from USD --to DEM --date 2020-06-15
```

**Rate-only lookup (no amount):**
```bash
bash <skill-path>/run.sh convert.py --from USD --to JPY --date 2020-03-15
```

**Batch series (JSON input):**
```bash
bash <skill-path>/run.sh convert.py --series '[{"date":"2020-01","amount":1000},{"date":"2020-06","amount":2000},{"date":"2021-01","amount":1500}]' --from USD --to EUR --convention monthly_avg
```

**JSON output:**
```bash
bash <skill-path>/run.sh convert.py --amount 1000 --from USD --to JPY --date 2020-03-15 --json
```

### Date formats accepted

The script is flexible: `2020-03-15`, `2020-03`, `2020`, `March 2020`, `Mar 2020`, `2020/03/15`.

### Direct data lookup

For raw rate lookups without conversion, read the JSON files directly:
- `daily.json["2020-03-15"]["JPY"]` → 107.84 (JPY per USD)
- `monthly.json["2020-03"]["JPY"]` → 108.09
- `annual.json["2020"]["JPY"]` → 106.77
- `daily.json["2020-03-15"]["GBP"]` → 1.2285 (USD per GBP — note inverted quote)

### Inline computation (without the script)

For simple one-off lookups:

1. Look up the rate from the appropriate JSON file
2. Check the quote direction in `metadata.json` — is it "per_usd" or "usd_per"?
3. Apply conversion:
   - If converting USD → foreign and rate is "per_usd": `result = amount × rate`
   - If converting USD → foreign and rate is "usd_per": `result = amount / rate`
   - For cross-rates: convert from_currency → USD first, then USD → to_currency
4. For DEM after 1998: look up EUR rate, then multiply by 1.95583

## Response guidelines

- Always state the rate used, the date, the convention, and the quote direction
- If the user requests a date that falls on a weekend/holiday (no trading day),
  the script automatically falls back to the nearest prior trading day — mention this
- For cross-rates, show the intermediate USD step so the user can verify
- When a user says "not seasonally adjusted" or "NSA", confirm that all Fed H.10
  rates are inherently not seasonally adjusted — this is not an error, it's the default
- For DEM queries after 1998, explain the auto-chain: "DEM was replaced by EUR on
  Jan 1, 1999 at a fixed rate of 1 EUR = 1.95583 DEM. I'm using the EUR rate for
  this date and applying the fixed conversion factor."
- For series/batch, present results in a clean table
- If a date is outside the data range, say so clearly

## Updating the data

The skill ships with **sample data** generated from realistic historical anchors. For production
use with exact Fed H.10 rates, replace the JSON files using one of these methods:

### Method 1: Fed H.10 text files (recommended)
1. Visit https://www.federalreserve.gov/releases/h10/hist/
2. For each currency, download the `.txt` files for all 3 eras (pre-1990, 1990-99, 2000+)
3. Save them in `data/raw/` (e.g., `dat89_ja.txt`, `dat96_ja.txt`, `dat00_ja.txt` for JPY)
4. Run: `bash <skill-path>/run.sh build_from_fed.py --from-cache`

### Method 2: Fed DDP CSV package
1. Visit https://www.federalreserve.gov/datadownload/choose.aspx?rel=h10
2. Select all daily bilateral exchange rates, set "all observations", CSV format
3. Download and place in `data/raw/`
4. Run: `bash <skill-path>/run.sh build_from_fed.py --from-cache --csv`

### Method 3: FRED API
Use pandas_datareader or the FRED API to download series like DEXJPUS (daily JPY),
EXJPUS (monthly JPY), AEXJPUS (annual JPY) — see `data/metadata.json` for all series IDs.

After updating, verify with: `bash <skill-path>/run.sh convert.py --from USD --to JPY --date 2020-03-15`
The Fed's noon buying rate for JPY on that date should be approximately 107.84.
