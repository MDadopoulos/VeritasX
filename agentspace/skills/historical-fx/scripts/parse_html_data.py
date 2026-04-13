#!/usr/bin/env python3
"""
Parse Fed H.10 HTML country data pages into JSON data files.

This script reads HTML files saved from:
  https://www.federalreserve.gov/releases/h10/hist/dat{era}_{code}.htm

The HTML pages contain tables with Date|Rate pairs.
Date format in HTML: D-MON-YY (e.g., "3-JAN-00", "15-MAR-07")

Usage:
    # First, save HTML files to data/raw/ (manually or via wget)
    # Then:
    python parse_html_data.py

    # Or pipe HTML content directly (for use with web_fetch):
    python parse_html_data.py --stdin --currency JPY --era 00 < dat00_ja.html
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from html.parser import HTMLParser

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
RAW_DIR = DATA_DIR / "raw"

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def parse_html_date(date_str):
    """Parse 'D-MON-YY' format from HTML tables."""
    date_str = date_str.strip()
    m = re.match(r"(\d{1,2})-([A-Z]{3})-(\d{2})", date_str)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTH_MAP.get(m.group(2))
    if month is None:
        return None
    yy = int(m.group(3))
    year = 2000 + yy if yy < 71 else 1900 + yy
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_rates_from_html(html_content):
    """Extract (date, rate) pairs from Fed H.10 HTML page content."""
    rates = []
    # Find all table rows with date|rate pattern
    # The HTML uses simple table structure: | date | rate |
    # We use regex since the HTML is simple and well-structured
    
    # Pattern: date cell followed by rate cell
    # Dates look like "3-JAN-00" and rates look like "101.7000" or "ND"
    pattern = re.compile(
        r'(\d{1,2}-[A-Z]{3}-\d{2})\s*\|?\s*'
        r'([\d.]+|ND|NC)',
        re.MULTILINE
    )
    
    for match in pattern.finditer(html_content):
        date_str = match.group(1)
        val_str = match.group(2)
        
        if val_str in ("ND", "NC"):
            continue
        
        d = parse_html_date(date_str)
        if d is None:
            continue
        
        try:
            rate = float(val_str)
            rates.append((d, rate))
        except ValueError:
            continue
    
    return rates


def extract_rates_from_markdown(md_content):
    """Extract rates from markdown-converted HTML (as returned by web_fetch)."""
    rates = []
    
    # Pattern for markdown table rows: | date | rate |
    pattern = re.compile(
        r'\|\s*(\d{1,2}-[A-Z]{3}-\d{2})\s*\|\s*([\d.]+|ND|NC)\s*\|',
        re.MULTILINE
    )
    
    for match in pattern.finditer(md_content):
        date_str = match.group(1)
        val_str = match.group(2)
        
        if val_str in ("ND", "NC"):
            continue
        
        d = parse_html_date(date_str)
        if d is None:
            continue
        
        try:
            rate = float(val_str)
            rates.append((d, rate))
        except ValueError:
            continue
    
    return rates


def build_json_from_rates(all_rates):
    """
    Build daily, monthly, annual JSON structures from collected rates.
    all_rates: dict of {currency: [(date, rate), ...]}
    """
    daily = {}
    monthly_accum = defaultdict(lambda: defaultdict(list))
    annual_accum = defaultdict(lambda: defaultdict(list))
    
    for ccy, rates in all_rates.items():
        rates.sort(key=lambda x: x[0])
        seen = set()
        for d, rate in rates:
            if d in seen:
                continue
            seen.add(d)
            
            date_str = d.isoformat()
            month_key = f"{d.year:04d}-{d.month:02d}"
            year_key = str(d.year)
            
            if date_str not in daily:
                daily[date_str] = {}
            daily[date_str][ccy] = rate
            
            monthly_accum[month_key][ccy].append(rate)
            annual_accum[year_key][ccy].append(rate)
        
        if rates:
            print(f"  {ccy}: {len(seen)} daily rates ({rates[0][0]} to {rates[-1][0]})")
    
    # Compute averages
    monthly = {}
    for mk in sorted(monthly_accum.keys()):
        monthly[mk] = {}
        for ccy, r in monthly_accum[mk].items():
            monthly[mk][ccy] = round(sum(r) / len(r), 4)
    
    annual = {}
    for yk in sorted(annual_accum.keys()):
        annual[yk] = {}
        for ccy, r in annual_accum[yk].items():
            annual[yk][ccy] = round(sum(r) / len(r), 4)
    
    return dict(sorted(daily.items())), monthly, annual


def write_json(daily, monthly, annual):
    """Write JSON data files."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    dp = DATA_DIR / "daily.json"
    mp = DATA_DIR / "monthly.json"
    ap = DATA_DIR / "annual.json"
    
    print(f"\nWriting {len(daily)} trading days...")
    with open(dp, "w") as f:
        json.dump(daily, f, separators=(",", ":"))
    
    print(f"Writing {len(monthly)} months...")
    with open(mp, "w") as f:
        json.dump(monthly, f, indent=2)
    
    print(f"Writing {len(annual)} years...")
    with open(ap, "w") as f:
        json.dump(annual, f, indent=2)
    
    total = sum(len(v) for v in daily.values())
    print(f"\nDone! {total} total data points across {len(daily)} days")


def merge_into_existing(new_rates, existing_daily_path=None):
    """Merge new rates into existing daily.json if it exists."""
    daily = {}
    if existing_daily_path and Path(existing_daily_path).exists():
        with open(existing_daily_path) as f:
            daily = json.load(f)
        print(f"Loaded existing daily.json with {len(daily)} days")
    
    monthly_accum = defaultdict(lambda: defaultdict(list))
    annual_accum = defaultdict(lambda: defaultdict(list))
    
    # Add existing data to accumulators
    for date_str, currencies in daily.items():
        d = date.fromisoformat(date_str)
        mk = f"{d.year:04d}-{d.month:02d}"
        yk = str(d.year)
        for ccy, rate in currencies.items():
            monthly_accum[mk][ccy].append(rate)
            annual_accum[yk][ccy].append(rate)
    
    # Merge new rates
    for ccy, rates in new_rates.items():
        count = 0
        for d, rate in rates:
            date_str = d.isoformat()
            mk = f"{d.year:04d}-{d.month:02d}"
            yk = str(d.year)
            
            if date_str not in daily:
                daily[date_str] = {}
            if ccy not in daily[date_str]:
                daily[date_str][ccy] = rate
                monthly_accum[mk][ccy].append(rate)
                annual_accum[yk][ccy].append(rate)
                count += 1
        print(f"  {ccy}: merged {count} new rates")
    
    monthly = {mk: {c: round(sum(r)/len(r), 4) for c, r in cs.items()}
               for mk, cs in sorted(monthly_accum.items())}
    annual = {yk: {c: round(sum(r)/len(r), 4) for c, r in cs.items()}
              for yk, cs in sorted(annual_accum.items())}
    
    return dict(sorted(daily.items())), monthly, annual


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdin", action="store_true", help="Read HTML from stdin")
    parser.add_argument("--currency", help="Currency code (with --stdin)")
    parser.add_argument("--era", help="Era code: 89, 96, or 00 (with --stdin)")
    parser.add_argument("--merge", action="store_true", help="Merge into existing data")
    parser.add_argument("files", nargs="*", help="HTML files to parse")
    args = parser.parse_args()
    
    all_rates = defaultdict(list)
    
    if args.stdin:
        if not args.currency:
            print("Error: --currency required with --stdin", file=sys.stderr)
            sys.exit(1)
        content = sys.stdin.read()
        rates = extract_rates_from_markdown(content)
        if not rates:
            rates = extract_rates_from_html(content)
        all_rates[args.currency] = rates
        print(f"Parsed {len(rates)} rates for {args.currency}")
    
    elif args.files:
        for filepath in args.files:
            with open(filepath) as f:
                content = f.read()
            # Try to infer currency from filename
            name = Path(filepath).stem  # e.g., "dat00_ja"
            rates = extract_rates_from_markdown(content)
            if not rates:
                rates = extract_rates_from_html(content)
            print(f"{filepath}: {len(rates)} rates")
    
    if all_rates:
        if args.merge:
            daily, monthly, annual = merge_into_existing(
                all_rates, DATA_DIR / "daily.json"
            )
        else:
            daily, monthly, annual = build_json_from_rates(all_rates)
        write_json(daily, monthly, annual)
