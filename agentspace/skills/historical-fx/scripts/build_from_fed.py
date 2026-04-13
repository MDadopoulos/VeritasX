#!/usr/bin/env python3
"""
Download real Federal Reserve H.10 exchange rate data and build the JSON data pack.

Data source: https://www.federalreserve.gov/releases/h10/hist/
Files are plain-text with format:
    D-Mon-YY  rate
    or ND/NC for no data

Three eras per currency:
    dat89_XX.txt  (through 1989)
    dat96_XX.txt  (1990-1999)
    dat00_XX.txt  (2000-present)

Usage:
    python build_from_fed.py                    # download + build
    python build_from_fed.py --from-cache       # build from already-downloaded files in data/raw/
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

try:
    import urllib.request
    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw"

BASE_URL = "https://www.federalreserve.gov/releases/h10/hist"

# Map of ISO currency code -> (Fed 2-letter code, eras available)
# Eras: 89 = pre-1990, 96 = 1990-1999, 00 = 2000-present
CURRENCY_FILES = {
    "AUD": ("al", ["89", "96", "00"]),
    "EUR": ("eu", ["00"]),         # EUR starts Jan 1999, but Fed puts 1999 in dat00
    "NZD": ("nz", ["89", "96", "00"]),
    "GBP": ("uk", ["89", "96", "00"]),
    "BRL": ("bz", ["96", "00"]),   # starts 1995
    "CAD": ("ca", ["89", "96", "00"]),
    "CNY": ("ch", ["89", "96", "00"]),
    "DKK": ("dn", ["89", "96", "00"]),
    "HKD": ("hk", ["89", "96", "00"]),
    "INR": ("in", ["89", "96", "00"]),
    "JPY": ("ja", ["89", "96", "00"]),
    "MYR": ("ma", ["89", "96", "00"]),
    "MXN": ("mx", ["96", "00"]),   # starts Nov 1993
    "NOK": ("no", ["89", "96", "00"]),
    "ZAR": ("sf", ["89", "96", "00"]),
    "SGD": ("si", ["89", "96", "00"]),
    "KRW": ("ko", ["89", "96", "00"]),
    "LKR": ("sl", ["89", "96", "00"]),
    "SEK": ("sd", ["89", "96", "00"]),
    "CHF": ("sz", ["89", "96", "00"]),
    "TWD": ("ta", ["89", "96", "00"]),
    "THB": ("th", ["89", "96", "00"]),
    "VEF": ("ve", ["96", "00"]),   # starts 1995
    # Legacy currencies
    "DEM": ("ge", ["89", "96"]),   # Deutsche Mark: through 1998
}

# Month abbreviation map for parsing "D-Mon-YY" dates
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# For the DDP CSV format - H.10 series identifiers (alternative source)
# These map the column headers from the preformatted CSV package to ISO codes
DDP_SERIES_TO_ISO = {
    "RXI$US_N.B.AL": "AUD",
    "RXI$US_N.B.EU": "EUR",
    "RXI$US_N.B.NZ": "NZD",
    "RXI$US_N.B.UK": "GBP",
    "RXI_N.B.BZ": "BRL",
    "RXI_N.B.CA": "CAD",
    "RXI_N.B.CH": "CNY",
    "RXI_N.B.DN": "DKK",
    "RXI_N.B.HK": "HKD",
    "RXI_N.B.IN": "INR",
    "RXI_N.B.JA": "JPY",
    "RXI_N.B.MA": "MYR",
    "RXI_N.B.MX": "MXN",
    "RXI_N.B.NO": "NOK",
    "RXI_N.B.SF": "ZAR",
    "RXI_N.B.SI": "SGD",
    "RXI_N.B.KO": "KRW",
    "RXI_N.B.SL": "LKR",
    "RXI_N.B.SD": "SEK",
    "RXI_N.B.SZ": "CHF",
    "RXI_N.B.TA": "TWD",
    "RXI_N.B.TH": "THB",
    "RXI_N.B.VES": "VEF",
}


def parse_fed_date(date_str):
    """
    Parse Fed H.10 text file date format: 'D-Mon-YY' or 'DD-Mon-YY'.
    The 2-digit year needs careful handling:
      - dat89 files: years 00-89 (but really 1971-1989 or similar)
      - dat96 files: years 90-99
      - dat00 files: years 00-26+
    We handle this by using the era context.
    """
    parts = date_str.strip().split("-")
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = MONTH_MAP.get(parts[1])
        if month is None:
            return None
        yy = int(parts[2])
        # Determine century from 2-digit year
        if yy >= 71:
            year = 1900 + yy
        else:
            year = 2000 + yy
        return date(year, month, day)
    except (ValueError, KeyError):
        return None


def download_file(url, dest_path):
    """Download a file from URL to local path."""
    if not HAS_URLLIB:
        print(f"  urllib not available, skipping download of {url}", file=sys.stderr)
        return False
    try:
        print(f"  Downloading {url}...")
        urllib.request.urlretrieve(url, dest_path)
        return True
    except Exception as e:
        print(f"  Warning: Could not download {url}: {e}", file=sys.stderr)
        return False


def parse_fed_txt(filepath, currency):
    """
    Parse a Fed H.10 text file. Returns list of (date, rate) tuples.
    Skips ND (no data) and NC (not calculated) entries.
    """
    rates = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Skip header lines
            if line.startswith("VERSION") or line.startswith("--") or "SPOT EXCHANGE" in line:
                continue
            # Try to parse as "date rate"
            parts = line.split()
            if len(parts) < 2:
                continue
            date_str = parts[0]
            val_str = parts[1]
            if val_str in ("ND", "NC"):
                continue
            try:
                rate = float(val_str)
            except ValueError:
                continue
            d = parse_fed_date(date_str)
            if d is None:
                continue
            rates.append((d, rate))
    return rates


def parse_ddp_csv(filepath):
    """
    Parse a Fed DDP preformatted CSV file (the 'all currencies' daily package).
    Returns dict: {date_str: {currency_iso: rate}}.
    """
    import csv

    data = {}
    iso_columns = {}  # column_index -> iso_code

    with open(filepath, "r") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find the "Time Period" row (header for data)
    header_row_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Time Period":
            header_row_idx = i
            # Map column indices to ISO codes
            for j, col in enumerate(row[1:], 1):
                col = col.strip()
                if col in DDP_SERIES_TO_ISO:
                    iso_columns[j] = DDP_SERIES_TO_ISO[col]
            break

    if header_row_idx is None:
        print(f"  Warning: Could not find 'Time Period' header in {filepath}", file=sys.stderr)
        return data

    # Parse data rows
    for row in rows[header_row_idx + 1:]:
        if not row or not row[0].strip():
            continue
        date_str = row[0].strip()
        # DDP dates are YYYY-MM-DD
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            continue
        data[date_str] = {}
        for j, iso in iso_columns.items():
            if j < len(row):
                val = row[j].strip()
                if val and val not in ("ND", "NC", ""):
                    try:
                        data[date_str][iso] = float(val)
                    except ValueError:
                        pass

    return data


def download_all_txt_files():
    """Download all H.10 text files from the Fed website."""
    os.makedirs(RAW_DIR, exist_ok=True)

    total = 0
    for iso, (code, eras) in CURRENCY_FILES.items():
        for era in eras:
            filename = f"dat{era}_{code}.txt"
            url = f"{BASE_URL}/{filename}"
            dest = RAW_DIR / filename
            if dest.exists():
                print(f"  Already have {filename}, skipping")
                total += 1
                continue
            if download_file(url, dest):
                total += 1

    print(f"Downloaded/found {total} files in {RAW_DIR}")


def build_from_txt_files():
    """Build daily.json, monthly.json, annual.json from downloaded .txt files."""
    daily = {}
    monthly_accum = defaultdict(lambda: defaultdict(list))
    annual_accum = defaultdict(lambda: defaultdict(list))

    files_processed = 0

    for iso, (code, eras) in CURRENCY_FILES.items():
        all_rates = []
        for era in eras:
            filename = f"dat{era}_{code}.txt"
            filepath = RAW_DIR / filename
            if not filepath.exists():
                print(f"  Warning: Missing {filename}, skipping", file=sys.stderr)
                continue
            rates = parse_fed_txt(filepath, iso)
            all_rates.extend(rates)
            files_processed += 1

        # Sort by date and deduplicate
        all_rates.sort(key=lambda x: x[0])
        seen = set()
        for d, rate in all_rates:
            if d in seen:
                continue
            seen.add(d)
            date_str = d.isoformat()
            month_key = f"{d.year:04d}-{d.month:02d}"
            year_key = str(d.year)

            if date_str not in daily:
                daily[date_str] = {}
            daily[date_str][iso] = rate

            monthly_accum[month_key][iso].append(rate)
            annual_accum[year_key][iso].append(rate)

        if all_rates:
            print(f"  {iso}: {len(seen)} daily rates ({all_rates[0][0]} to {all_rates[-1][0]})")

    # Compute monthly averages
    monthly = {}
    for mk in sorted(monthly_accum.keys()):
        monthly[mk] = {}
        for ccy, rates in monthly_accum[mk].items():
            monthly[mk][ccy] = round(sum(rates) / len(rates), 4)

    # Compute annual averages
    annual = {}
    for yk in sorted(annual_accum.keys()):
        annual[yk] = {}
        for ccy, rates in annual_accum[yk].items():
            annual[yk][ccy] = round(sum(rates) / len(rates), 4)

    print(f"\nProcessed {files_processed} text files")
    return daily, monthly, annual


def build_from_ddp_csv():
    """Build from a DDP preformatted CSV (alternative data source)."""
    csv_files = list(RAW_DIR.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in data/raw/. Use .txt files instead.", file=sys.stderr)
        return None, None, None

    daily = {}
    monthly_accum = defaultdict(lambda: defaultdict(list))
    annual_accum = defaultdict(lambda: defaultdict(list))

    for csv_file in csv_files:
        print(f"  Parsing {csv_file.name}...")
        file_data = parse_ddp_csv(csv_file)
        for date_str, currencies in file_data.items():
            if date_str not in daily:
                daily[date_str] = {}
            daily[date_str].update(currencies)

            d = date.fromisoformat(date_str)
            month_key = f"{d.year:04d}-{d.month:02d}"
            year_key = str(d.year)
            for ccy, rate in currencies.items():
                monthly_accum[month_key][ccy].append(rate)
                annual_accum[year_key][ccy].append(rate)

    monthly = {mk: {ccy: round(sum(r)/len(r), 4) for ccy, r in ccys.items()}
               for mk, ccys in sorted(monthly_accum.items())}
    annual = {yk: {ccy: round(sum(r)/len(r), 4) for ccy, r in ccys.items()}
              for yk, ccys in sorted(annual_accum.items())}

    return daily, monthly, annual


def write_data(daily, monthly, annual):
    """Write the JSON data files."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # Sort daily by date
    daily_sorted = dict(sorted(daily.items()))

    daily_path = DATA_DIR / "daily.json"
    monthly_path = DATA_DIR / "monthly.json"
    annual_path = DATA_DIR / "annual.json"

    print(f"\nWriting {len(daily_sorted)} trading days to daily.json...")
    with open(daily_path, "w") as f:
        json.dump(daily_sorted, f, separators=(",", ":"))

    print(f"Writing {len(monthly)} months to monthly.json...")
    with open(monthly_path, "w") as f:
        json.dump(monthly, f, indent=2)

    print(f"Writing {len(annual)} years to annual.json...")
    with open(annual_path, "w") as f:
        json.dump(annual, f, indent=2)

    total_points = sum(len(v) for v in daily_sorted.values())
    size_daily = daily_path.stat().st_size / (1024 * 1024)
    size_monthly = monthly_path.stat().st_size / 1024
    size_annual = annual_path.stat().st_size / 1024

    print(f"\nDone!")
    print(f"  daily.json:   {size_daily:.1f} MB ({len(daily_sorted)} days, {total_points} data points)")
    print(f"  monthly.json: {size_monthly:.1f} KB ({len(monthly)} months)")
    print(f"  annual.json:  {size_annual:.1f} KB ({len(annual)} years)")


def main():
    parser = argparse.ArgumentParser(description="Build FX data pack from Federal Reserve H.10 data")
    parser.add_argument("--from-cache", action="store_true",
                        help="Build from already-downloaded files in data/raw/ (no download)")
    parser.add_argument("--csv", action="store_true",
                        help="Build from DDP CSV file(s) in data/raw/ instead of .txt files")
    args = parser.parse_args()

    if not args.from_cache:
        print("Step 1: Downloading H.10 text files from Federal Reserve...")
        download_all_txt_files()
    else:
        print("Step 1: Using cached files from data/raw/")

    print("\nStep 2: Parsing and building data pack...")
    if args.csv:
        daily, monthly, annual = build_from_ddp_csv()
    else:
        daily, monthly, annual = build_from_txt_files()

    if daily is None:
        print("Error: No data to build from.", file=sys.stderr)
        sys.exit(1)

    print("\nStep 3: Writing JSON files...")
    write_data(daily, monthly, annual)


if __name__ == "__main__":
    main()
