#!/usr/bin/env python3
"""
Generate sample historical FX data for the historical-fx skill.

In production, this data would come from FRED CSV downloads. This script
creates realistic synthetic data for development and testing purposes.

To use real data instead:
1. Download CSVs from FRED (e.g., DEXJPUS, DEXUSUK, DEXCAUS, etc.)
2. Place them in data/raw/
3. Run build_from_fred.py instead
"""

import json
import os
import random
import math
from datetime import datetime, timedelta, date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

# Approximate historical FX rates (realistic anchor points)
# Format: {currency: [(year, rate), ...]} where rate is in the native H.10 quote
ANCHOR_RATES = {
    # per_usd currencies
    "JPY": [(1971, 357.0), (1980, 226.7), (1990, 144.8), (1995, 94.1),
            (2000, 107.8), (2005, 110.2), (2010, 87.8), (2012, 79.8),
            (2015, 121.0), (2020, 106.8), (2024, 151.3), (2025, 149.0)],
    "CAD": [(1971, 1.01), (1980, 1.17), (1990, 1.17), (1995, 1.37),
            (2000, 1.49), (2005, 1.21), (2010, 1.03), (2015, 1.28),
            (2020, 1.34), (2024, 1.36), (2025, 1.38)],
    "INR": [(1973, 7.74), (1980, 7.86), (1990, 17.50), (1995, 32.43),
            (2000, 44.94), (2005, 44.10), (2010, 45.73), (2015, 64.15),
            (2020, 74.10), (2024, 83.40), (2025, 85.50)],
    "CHF": [(1971, 4.32), (1980, 1.68), (1990, 1.39), (1995, 1.18),
            (2000, 1.69), (2005, 1.25), (2010, 1.04), (2015, 0.96),
            (2020, 0.94), (2024, 0.88), (2025, 0.90)],
    "DKK": [(1971, 7.49), (1980, 5.64), (1990, 6.19), (1995, 5.60),
            (2000, 8.09), (2005, 5.99), (2010, 5.62), (2015, 6.73),
            (2020, 6.54), (2024, 6.89), (2025, 7.05)],
    "CNY": [(1981, 1.70), (1990, 4.78), (1995, 8.35), (2000, 8.28),
            (2005, 8.19), (2010, 6.77), (2015, 6.23), (2020, 6.90),
            (2024, 7.22), (2025, 7.30)],
    "HKD": [(1981, 5.70), (1990, 7.79), (1995, 7.74), (2000, 7.79),
            (2005, 7.78), (2010, 7.77), (2015, 7.75), (2020, 7.76),
            (2024, 7.82), (2025, 7.80)],
    "KRW": [(1981, 681.0), (1990, 707.8), (1995, 771.3), (2000, 1131.0),
            (2005, 1024.1), (2010, 1156.1), (2015, 1131.5), (2020, 1180.3),
            (2024, 1363.0), (2025, 1400.0)],
    "MYR": [(1971, 3.06), (1980, 2.18), (1990, 2.70), (1995, 2.50),
            (2000, 3.80), (2005, 3.79), (2010, 3.22), (2015, 3.91),
            (2020, 4.20), (2024, 4.72), (2025, 4.50)],
    "MXN": [(1993, 3.11), (1995, 6.42), (2000, 9.46), (2005, 10.90),
            (2010, 12.64), (2015, 15.85), (2020, 21.49), (2024, 17.10),
            (2025, 20.30)],
    "NOK": [(1971, 7.14), (1980, 4.94), (1990, 6.26), (1995, 6.34),
            (2000, 8.80), (2005, 6.44), (2010, 6.04), (2015, 8.07),
            (2020, 9.41), (2024, 10.70), (2025, 11.00)],
    "SGD": [(1981, 2.11), (1990, 1.81), (1995, 1.42), (2000, 1.72),
            (2005, 1.66), (2010, 1.36), (2015, 1.37), (2020, 1.38),
            (2024, 1.34), (2025, 1.35)],
    "ZAR": [(1971, 0.71), (1980, 0.78), (1990, 2.59), (1995, 3.63),
            (2000, 6.94), (2005, 6.36), (2010, 7.32), (2015, 12.76),
            (2020, 16.46), (2024, 18.30), (2025, 18.00)],
    "LKR": [(1971, 5.95), (1980, 16.53), (1990, 40.06), (1995, 51.25),
            (2000, 77.01), (2005, 100.5), (2010, 113.1), (2015, 135.9),
            (2020, 185.5), (2024, 298.0), (2025, 300.0)],
    "SEK": [(1971, 5.17), (1980, 4.23), (1990, 5.92), (1995, 7.13),
            (2000, 9.16), (2005, 7.47), (2010, 7.21), (2015, 8.44),
            (2020, 9.21), (2024, 10.50), (2025, 10.70)],
    "TWD": [(1983, 40.27), (1990, 26.89), (1995, 26.48), (2000, 31.23),
            (2005, 32.17), (2010, 31.64), (2015, 31.90), (2020, 29.58),
            (2024, 31.60), (2025, 32.50)],
    "THB": [(1981, 21.82), (1990, 25.59), (1995, 24.92), (2000, 40.11),
            (2005, 40.22), (2010, 31.69), (2015, 34.25), (2020, 31.29),
            (2024, 35.70), (2025, 34.50)],
    "DEM": [(1971, 3.49), (1975, 2.46), (1980, 1.82), (1985, 2.94),
            (1990, 1.62), (1995, 1.43), (1998, 1.76)],
    # usd_per currencies
    "GBP": [(1971, 2.44), (1980, 2.33), (1985, 1.30), (1990, 1.78),
            (1995, 1.58), (2000, 1.52), (2005, 1.82), (2007, 2.00),
            (2010, 1.55), (2015, 1.53), (2016, 1.36), (2020, 1.28),
            (2024, 1.27), (2025, 1.25)],
    "EUR": [(1999, 1.17), (2000, 0.92), (2002, 1.06), (2005, 1.24),
            (2008, 1.47), (2010, 1.33), (2012, 1.29), (2015, 1.11),
            (2020, 1.14), (2022, 1.05), (2024, 1.08), (2025, 1.04)],
    "AUD": [(1971, 1.12), (1980, 1.14), (1985, 0.70), (1990, 0.78),
            (1995, 0.74), (2000, 0.58), (2005, 0.76), (2010, 0.92),
            (2012, 1.04), (2015, 0.75), (2020, 0.69), (2024, 0.66),
            (2025, 0.63)],
    "NZD": [(1971, 1.12), (1980, 1.03), (1985, 0.44), (1990, 0.60),
            (1995, 0.66), (2000, 0.46), (2005, 0.70), (2010, 0.72),
            (2015, 0.68), (2020, 0.65), (2024, 0.61), (2025, 0.57)],
    "BRL": [(1995, 0.97), (2000, 1.83), (2002, 2.92), (2005, 2.43),
            (2010, 1.76), (2015, 3.33), (2020, 5.16), (2024, 4.99),
            (2025, 5.80)],
    "VEF": [(1995, 170.0), (2000, 680.0), (2005, 2150.0), (2010, 4300.0),
            (2015, 6300.0), (2018, 248488.0)],
}

# Currency start dates (first available trading day)
START_DATES = {
    "AUD": "1971-01-04", "BRL": "1995-01-02", "CAD": "1971-01-04",
    "CNY": "1981-01-02", "DKK": "1971-01-04", "EUR": "1999-01-04",
    "GBP": "1971-01-04", "HKD": "1981-01-02", "INR": "1973-01-02",
    "JPY": "1971-01-04", "KRW": "1981-04-13", "MYR": "1971-01-04",
    "MXN": "1993-11-08", "NZD": "1971-01-04", "NOK": "1971-01-04",
    "SGD": "1981-01-02", "ZAR": "1971-01-04", "LKR": "1971-01-04",
    "SEK": "1971-01-04", "CHF": "1971-01-04", "TWD": "1983-10-03",
    "THB": "1981-01-02", "VEF": "1995-01-02", "DEM": "1971-01-04",
}

END_DATES = {
    "DEM": "1998-12-31",
    "VEF": "2018-12-31",
}


def interpolate_rate(anchors, target_year_frac):
    """Linear interpolation between anchor points."""
    if target_year_frac <= anchors[0][0]:
        return anchors[0][1]
    if target_year_frac >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        y0, r0 = anchors[i]
        y1, r1 = anchors[i + 1]
        if y0 <= target_year_frac <= y1:
            t = (target_year_frac - y0) / (y1 - y0)
            return r0 + t * (r1 - r0)
    return anchors[-1][1]


def generate_daily_rate(anchors, d, prev_rate=None, volatility=0.005):
    """Generate a plausible daily rate with some random walk noise."""
    year_frac = d.year + (d.timetuple().tm_yday / 365.25)
    base = interpolate_rate(anchors, year_frac)
    if prev_rate is not None:
        # Random walk around previous day with mean reversion toward base
        reversion = 0.02
        noise = random.gauss(0, volatility * prev_rate)
        rate = prev_rate + noise + reversion * (base - prev_rate)
        # Don't let it go negative
        rate = max(rate, base * 0.3)
    else:
        rate = base * (1 + random.gauss(0, 0.01))
    return round(rate, 4)


def is_trading_day(d):
    """Weekdays only (simplified — doesn't account for US holidays)."""
    return d.weekday() < 5


def generate_all_data():
    """Generate daily, monthly, and annual JSON data files."""
    random.seed(42)  # Reproducible

    end_date = date(2025, 12, 31)
    daily = {}
    monthly_accum = {}  # {YYYY-MM: {currency: [rates]}}
    annual_accum = {}   # {YYYY: {currency: [rates]}}

    # Generate daily rates
    prev_rates = {}
    d = date(1971, 1, 4)
    while d <= end_date:
        if is_trading_day(d):
            date_str = d.isoformat()
            daily[date_str] = {}
            month_key = f"{d.year:04d}-{d.month:02d}"
            year_key = str(d.year)

            if month_key not in monthly_accum:
                monthly_accum[month_key] = {}
            if year_key not in annual_accum:
                annual_accum[year_key] = {}

            for ccy, anchors in ANCHOR_RATES.items():
                start = date.fromisoformat(START_DATES[ccy])
                end = date.fromisoformat(END_DATES.get(ccy, "2025-12-31"))
                if d < start or d > end:
                    continue

                vol = 0.003  # default daily vol
                if ccy in ("VEF", "BRL", "MXN", "ZAR", "KRW"):
                    vol = 0.008  # EM currencies more volatile
                elif ccy in ("HKD",):
                    vol = 0.0002  # pegged

                rate = generate_daily_rate(anchors, d, prev_rates.get(ccy), vol)
                daily[date_str][ccy] = rate
                prev_rates[ccy] = rate

                if ccy not in monthly_accum[month_key]:
                    monthly_accum[month_key][ccy] = []
                monthly_accum[month_key][ccy].append(rate)

                if ccy not in annual_accum[year_key]:
                    annual_accum[year_key][ccy] = []
                annual_accum[year_key][ccy].append(rate)

        d += timedelta(days=1)

    # Compute monthly averages
    monthly = {}
    for mk, currencies in monthly_accum.items():
        monthly[mk] = {}
        for ccy, rates in currencies.items():
            monthly[mk][ccy] = round(sum(rates) / len(rates), 4)

    # Compute annual averages
    annual = {}
    for yk, currencies in annual_accum.items():
        annual[yk] = {}
        for ccy, rates in currencies.items():
            annual[yk][ccy] = round(sum(rates) / len(rates), 4)

    return daily, monthly, annual


def main():
    print("Generating historical FX data...")
    print("This will take a moment (~55 years of daily data for 25 currencies)")

    daily, monthly, annual = generate_all_data()

    # Write files
    os.makedirs(DATA_DIR, exist_ok=True)

    daily_path = DATA_DIR / "daily.json"
    monthly_path = DATA_DIR / "monthly.json"
    annual_path = DATA_DIR / "annual.json"

    print(f"Writing {len(daily)} trading days to daily.json...")
    with open(daily_path, "w") as f:
        json.dump(daily, f, separators=(",", ":"))

    print(f"Writing {len(monthly)} months to monthly.json...")
    with open(monthly_path, "w") as f:
        json.dump(monthly, f, indent=2)

    print(f"Writing {len(annual)} years to annual.json...")
    with open(annual_path, "w") as f:
        json.dump(annual, f, indent=2)

    # Summary stats
    total_points = sum(len(v) for v in daily.values())
    size_daily = daily_path.stat().st_size / (1024 * 1024)
    size_monthly = monthly_path.stat().st_size / 1024
    size_annual = annual_path.stat().st_size / 1024

    print(f"\nDone!")
    print(f"  daily.json:   {size_daily:.1f} MB ({len(daily)} days, {total_points} data points)")
    print(f"  monthly.json: {size_monthly:.1f} KB ({len(monthly)} months)")
    print(f"  annual.json:  {size_annual:.1f} KB ({len(annual)} years)")


if __name__ == "__main__":
    main()
