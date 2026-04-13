#!/usr/bin/env python3
"""
CPI-U Inflation Adjuster — deterministic constant-dollar conversion.

Usage:
    python adjust.py --amount 100 --from-year 1980 --to-year 2024
    python adjust.py --amount 100 --from-year 1980 --from-month Jun --to-year 2024 --to-month Jan
    python adjust.py --amount 100 --from-year 1980 --to-year 2024 --base-month "Jan 2000"
    python adjust.py --series '[{"year":2000,"value":50000},{"year":2010,"value":65000}]' --to-year 2024

All CPI data is bundled locally — no API calls needed.
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(SCRIPT_DIR, "..", "data", "cpi_u.json")

MONTH_MAP = {
    "jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr",
    "may": "May", "jun": "Jun", "jul": "Jul", "aug": "Aug",
    "sep": "Sep", "oct": "Oct", "nov": "Nov", "dec": "Dec",
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "june": "Jun", "july": "Jul", "august": "Aug",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
    "1": "Jan", "2": "Feb", "3": "Mar", "4": "Apr",
    "5": "May", "6": "Jun", "7": "Jul", "8": "Aug",
    "9": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
    "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
    "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
    "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
}


def load_cpi_data():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def normalize_month(raw):
    """Accept 'Jan', 'january', '1', '01' etc. and return canonical 'Jan'."""
    if raw is None:
        return None
    key = raw.strip().lower()
    if key in MONTH_MAP:
        return MONTH_MAP[key]
    # Try title-case match directly
    titled = raw.strip().title()[:3]
    if titled in ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"):
        return titled
    raise ValueError(f"Unrecognized month: '{raw}'")


def get_cpi(data, year, month=None):
    """
    Return the CPI value for a given year (and optionally month).
    If month is None, use the annual average.
    """
    year_str = str(year)

    if month:
        month_key = normalize_month(month)
        if year_str not in data["monthly"]:
            raise ValueError(f"No monthly CPI data for year {year}. Range: 1939–2026.")
        monthly = data["monthly"][year_str]
        if month_key not in monthly:
            raise ValueError(f"No CPI data for {month_key} {year}.")
        val = monthly[month_key]
        if val is None:
            raise ValueError(f"CPI data for {month_key} {year} is unavailable (BLS gap).")
        return val, f"{month_key} {year}"
    else:
        if year_str not in data["annual_average"]:
            raise ValueError(f"No annual average CPI data for {year}. Range: 1939–2025.")
        return data["annual_average"][year_str], f"{year} (annual avg)"


def adjust_single(amount, from_year, to_year, from_month=None, to_month=None,
                  base_year=None, base_month=None, data=None):
    """
    Convert `amount` from `from_year/from_month` dollars to `to_year/to_month` dollars.

    If base_year/base_month are provided, the result is expressed in that base's
    constant dollars instead (both from and to are converted to base).

    Returns a dict with the result and supporting info.
    """
    if data is None:
        data = load_cpi_data()

    from_cpi, from_label = get_cpi(data, from_year, from_month)
    to_cpi, to_label = get_cpi(data, to_year, to_month)

    if base_year is not None:
        base_cpi, base_label = get_cpi(data, base_year, base_month)
        adjusted = amount * (base_cpi / from_cpi)
        return {
            "original_amount": amount,
            "adjusted_amount": round(adjusted, 2),
            "from": from_label,
            "to": base_label + " constant dollars",
            "from_cpi": from_cpi,
            "base_cpi": base_cpi,
            "multiplier": round(base_cpi / from_cpi, 6),
        }
    else:
        adjusted = amount * (to_cpi / from_cpi)
        return {
            "original_amount": amount,
            "adjusted_amount": round(adjusted, 2),
            "from": from_label,
            "to": to_label,
            "from_cpi": from_cpi,
            "to_cpi": to_cpi,
            "multiplier": round(to_cpi / from_cpi, 6),
        }


def adjust_series(series, to_year, to_month=None, data=None):
    """
    Adjust a list of {year, [month], value} dicts to a common target year/month.
    Returns a list of result dicts.
    """
    if data is None:
        data = load_cpi_data()
    results = []
    for item in series:
        r = adjust_single(
            amount=item["value"],
            from_year=item["year"],
            to_year=to_year,
            from_month=item.get("month"),
            to_month=to_month,
            data=data,
        )
        results.append(r)
    return results


def main():
    parser = argparse.ArgumentParser(description="CPI-U inflation adjustment tool")
    parser.add_argument("--amount", type=float, help="Dollar amount to adjust")
    parser.add_argument("--from-year", type=int, help="Origin year")
    parser.add_argument("--from-month", type=str, default=None, help="Origin month (optional)")
    parser.add_argument("--to-year", type=int, help="Target year")
    parser.add_argument("--to-month", type=str, default=None, help="Target month (optional)")
    parser.add_argument("--base-year", type=int, default=None, help="Base year for constant dollars")
    parser.add_argument("--base-month", type=str, default=None, help="Base month for constant dollars")
    parser.add_argument("--series", type=str, default=None,
                        help='JSON array of {year, [month], value} for batch adjustment')
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.series:
        series = json.loads(args.series)
        if not args.to_year:
            parser.error("--to-year is required for series adjustment")
        results = adjust_series(series, args.to_year, args.to_month)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                print(f"${r['original_amount']:,.2f} ({r['from']}) -> ${r['adjusted_amount']:,.2f} ({r['to']})")
    elif args.amount is not None and args.from_year and args.to_year:
        result = adjust_single(
            args.amount, args.from_year, args.to_year,
            args.from_month, args.to_month,
            args.base_year, args.base_month,
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"${result['original_amount']:,.2f} ({result['from']}) -> ${result['adjusted_amount']:,.2f} ({result['to']})")
            print(f"  CPI multiplier: {result['multiplier']}")
    else:
        parser.error("Provide --amount/--from-year/--to-year, or --series/--to-year")


if __name__ == "__main__":
    main()
