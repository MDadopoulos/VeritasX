#!/usr/bin/env python3
"""
Historical FX conversion using bundled Fed H.10 data.

Supports:
  - Same-day spot lookup
  - First-of-month rate
  - Monthly average
  - Annual average
  - Cross-rate computation via USD triangulation
  - DEM auto-chaining through EUR (post-1998)
  - Batch/series conversion
  - Rate-only lookups (no amount)

No external dependencies — pure Python 3.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

# DEM → EUR irrevocable conversion rate
DEM_EUR_RATE = 1.95583
DEM_TRANSITION = date(1999, 1, 1)

CONVENTIONS = ("spot", "first_of_month", "monthly_avg", "annual_avg")

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"Error: Data file not found: {path}", file=sys.stderr)
        print(f"Run scripts/generate_sample_data.py first, or place real FRED data in {DATA_DIR}/", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def load_metadata():
    return load_json("metadata.json")


def resolve_currency(code, metadata):
    """Resolve a currency code or alias to its canonical ISO code."""
    code_upper = code.upper().strip()
    if code_upper == "USD":
        return "USD"
    if code_upper in metadata["currencies"]:
        return code_upper
    aliases = metadata.get("aliases", {})
    if code_upper in aliases:
        return aliases[code_upper]
    # Try case-insensitive alias match
    for alias, resolved in aliases.items():
        if alias.upper() == code_upper:
            return resolved
    print(f"Error: Unknown currency '{code}'. Available: USD, {', '.join(sorted(metadata['currencies'].keys()))}", file=sys.stderr)
    sys.exit(1)


def parse_date_input(date_str):
    """
    Parse flexible date input. Returns (year, month, day) where month/day may be None.
    Determines the appropriate default convention.
    """
    date_str = date_str.strip()

    # YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", date_str)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    # YYYY-MM
    m = re.match(r"(\d{4})[-/](\d{1,2})$", date_str)
    if m:
        return int(m.group(1)), int(m.group(2)), None

    # YYYY
    m = re.match(r"(\d{4})$", date_str)
    if m:
        return int(m.group(1)), None, None

    # "March 2020", "Mar 2020"
    m = re.match(r"([A-Za-z]+)\s+(\d{4})$", date_str)
    if m:
        month_name = m.group(1).lower()
        if month_name in MONTH_NAMES:
            return int(m.group(2)), MONTH_NAMES[month_name], None

    # "2020 March"
    m = re.match(r"(\d{4})\s+([A-Za-z]+)$", date_str)
    if m:
        month_name = m.group(2).lower()
        if month_name in MONTH_NAMES:
            return int(m.group(1)), MONTH_NAMES[month_name], None

    print(f"Error: Cannot parse date '{date_str}'. Use YYYY, YYYY-MM, YYYY-MM-DD, or 'March 2020'.", file=sys.stderr)
    sys.exit(1)


def infer_convention(year, month, day, explicit_convention):
    """If no convention given, infer from date precision."""
    if explicit_convention:
        return explicit_convention
    if day is not None:
        return "spot"
    if month is not None:
        return "monthly_avg"
    return "annual_avg"


def get_rate_usd(currency, year, month, day, convention, daily, monthly, annual, metadata):
    """
    Get the exchange rate for currency vs USD.
    Returns (rate, quote_direction, actual_date_used, notes).
    
    rate: the raw H.10 number
    quote_direction: "per_usd" or "usd_per"
    actual_date_used: the date string actually used (may differ for weekends)
    notes: list of strings with any caveats
    """
    notes = []

    # Handle DEM specially
    if currency == "DEM":
        target_date = date(year, month or 1, day or 1)
        if target_date >= DEM_TRANSITION:
            # Auto-chain through EUR
            eur_rate, eur_dir, eur_date, eur_notes = get_rate_usd(
                "EUR", year, month, day, convention, daily, monthly, annual, metadata
            )
            notes.extend(eur_notes)
            notes.append(f"DEM auto-chained via EUR (1 EUR = {DEM_EUR_RATE} DEM)")
            # EUR is "usd_per" (USD per 1 EUR)
            # DEM is "per_usd" (DEM per 1 USD)
            # 1 USD = (1/eur_rate) EUR = (1/eur_rate) * DEM_EUR_RATE DEM
            dem_rate = DEM_EUR_RATE / eur_rate
            return dem_rate, "per_usd", eur_date, notes

    ccy_meta = metadata["currencies"].get(currency)
    if not ccy_meta:
        print(f"Error: No metadata for '{currency}'", file=sys.stderr)
        sys.exit(1)

    quote_dir = ccy_meta["quote"]

    if convention == "annual_avg":
        year_key = str(year)
        if year_key not in annual:
            print(f"Error: No annual data for year {year}", file=sys.stderr)
            sys.exit(1)
        if currency not in annual[year_key]:
            print(f"Error: No annual data for {currency} in {year}", file=sys.stderr)
            sys.exit(1)
        return annual[year_key][currency], quote_dir, year_key, notes

    if convention == "monthly_avg":
        if month is None:
            print(f"Error: Monthly average requires a month. Use --date YYYY-MM.", file=sys.stderr)
            sys.exit(1)
        month_key = f"{year:04d}-{month:02d}"
        if month_key not in monthly:
            print(f"Error: No monthly data for {month_key}", file=sys.stderr)
            sys.exit(1)
        if currency not in monthly[month_key]:
            print(f"Error: No monthly data for {currency} in {month_key}", file=sys.stderr)
            sys.exit(1)
        return monthly[month_key][currency], quote_dir, month_key, notes

    if convention == "first_of_month":
        if month is None:
            print(f"Error: First-of-month requires a month. Use --date YYYY-MM.", file=sys.stderr)
            sys.exit(1)
        # Find first trading day of the month
        d = date(year, month, 1)
        for offset in range(7):  # at most 7 days to find a weekday
            check = d + timedelta(days=offset)
            check_str = check.isoformat()
            if check_str in daily and currency in daily[check_str]:
                notes.append(f"First trading day of {year:04d}-{month:02d}: {check_str}")
                return daily[check_str][currency], quote_dir, check_str, notes
        print(f"Error: No trading day found for first of {year:04d}-{month:02d}", file=sys.stderr)
        sys.exit(1)

    if convention == "spot":
        if month is None or day is None:
            print(f"Error: Spot rate requires a full date. Use --date YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
        target = date(year, month, day)
        target_str = target.isoformat()
        # Try exact date, then fall back to nearest prior trading day
        for offset in range(7):
            check = target - timedelta(days=offset)
            check_str = check.isoformat()
            if check_str in daily and currency in daily[check_str]:
                if offset > 0:
                    notes.append(f"Requested {target_str} (non-trading day); used nearest prior: {check_str}")
                return daily[check_str][currency], quote_dir, check_str, notes
        print(f"Error: No daily data found near {target_str} for {currency}", file=sys.stderr)
        sys.exit(1)

    print(f"Error: Unknown convention '{convention}'", file=sys.stderr)
    sys.exit(1)


def to_usd(amount, rate, quote_dir):
    """Convert an amount in foreign currency to USD."""
    if quote_dir == "per_usd":
        # rate = foreign per 1 USD → USD = amount / rate
        return amount / rate
    else:
        # rate = USD per 1 foreign → USD = amount * rate
        return amount * rate


def from_usd(usd_amount, rate, quote_dir):
    """Convert a USD amount to foreign currency."""
    if quote_dir == "per_usd":
        # rate = foreign per 1 USD → foreign = usd * rate
        return usd_amount * rate
    else:
        # rate = USD per 1 foreign → foreign = usd / rate
        return usd_amount / rate


def convert(amount, from_ccy, to_ccy, year, month, day, convention,
            daily, monthly, annual, metadata):
    """
    Convert amount from from_ccy to to_ccy.
    Returns dict with result and details.
    """
    notes = []
    result = {
        "from_currency": from_ccy,
        "to_currency": to_ccy,
        "convention": convention,
    }

    if amount is not None:
        result["original_amount"] = amount

    if from_ccy == "USD" and to_ccy == "USD":
        if amount is not None:
            result["converted_amount"] = amount
            result["rate"] = 1.0
        return result

    if from_ccy == "USD":
        rate, quote_dir, date_used, rate_notes = get_rate_usd(
            to_ccy, year, month, day, convention, daily, monthly, annual, metadata
        )
        notes.extend(rate_notes)
        result["date_used"] = date_used
        result["rate_raw"] = rate
        result["rate_quote"] = metadata["currencies"][to_ccy if to_ccy != "DEM" or date(year, month or 1, day or 1) < DEM_TRANSITION else to_ccy]["unit_label"] if to_ccy in metadata["currencies"] else f"{to_ccy} per USD"
        
        if amount is not None:
            converted = from_usd(amount, rate, quote_dir)
            result["converted_amount"] = round(converted, 4)
            result["effective_rate"] = round(rate if quote_dir == "per_usd" else 1.0 / rate, 6)
            result["effective_rate_label"] = f"{to_ccy} per 1 USD"

    elif to_ccy == "USD":
        rate, quote_dir, date_used, rate_notes = get_rate_usd(
            from_ccy, year, month, day, convention, daily, monthly, annual, metadata
        )
        notes.extend(rate_notes)
        result["date_used"] = date_used
        result["rate_raw"] = rate

        if amount is not None:
            converted = to_usd(amount, rate, quote_dir)
            result["converted_amount"] = round(converted, 4)

    else:
        # Cross-rate via USD triangulation
        rate_from, dir_from, date_from, notes_from = get_rate_usd(
            from_ccy, year, month, day, convention, daily, monthly, annual, metadata
        )
        rate_to, dir_to, date_to, notes_to = get_rate_usd(
            to_ccy, year, month, day, convention, daily, monthly, annual, metadata
        )
        notes.extend(notes_from)
        notes.extend(notes_to)
        notes.append(f"Cross-rate computed via USD triangulation: {from_ccy} -> USD -> {to_ccy}")

        result["date_used"] = date_from  # should be the same
        result["intermediate_rates"] = {
            f"{from_ccy}/USD": rate_from,
            f"{to_ccy}/USD": rate_to,
        }

        if amount is not None:
            usd_amount = to_usd(amount, rate_from, dir_from)
            converted = from_usd(usd_amount, rate_to, dir_to)
            result["converted_amount"] = round(converted, 4)
            result["usd_intermediate"] = round(usd_amount, 4)

        # Compute effective cross rate (1 from_ccy = ? to_ccy)
        one_usd_from = to_usd(1.0, rate_from, dir_from)  # Not useful for cross
        cross = from_usd(to_usd(1.0, rate_from, dir_from), rate_to, dir_to)
        result["effective_cross_rate"] = round(cross, 6)
        result["effective_rate_label"] = f"{to_ccy} per 1 {from_ccy}"

    if notes:
        result["notes"] = notes
    return result


def format_result(r, json_output=False):
    """Format a single conversion result for display."""
    if json_output:
        return json.dumps(r, indent=2)

    lines = []
    if "original_amount" in r:
        amt = r["original_amount"]
        conv = r.get("converted_amount", "N/A")
        lines.append(f"{amt:,.4f} {r['from_currency']} -> {conv:,.4f} {r['to_currency']}")
    else:
        lines.append(f"Rate lookup: {r['from_currency']}/{r['to_currency']}")

    lines.append(f"Convention: {r['convention']}")

    if "date_used" in r:
        lines.append(f"Date: {r['date_used']}")

    if "rate_raw" in r:
        lines.append(f"H.10 rate: {r['rate_raw']}")

    if "effective_rate" in r:
        lines.append(f"Effective: {r['effective_rate']} ({r.get('effective_rate_label', '')})")

    if "effective_cross_rate" in r:
        lines.append(f"Cross rate: {r['effective_cross_rate']} ({r.get('effective_rate_label', '')})")

    if "intermediate_rates" in r:
        for k, v in r["intermediate_rates"].items():
            lines.append(f"  {k}: {v}")

    if "usd_intermediate" in r:
        lines.append(f"USD intermediate: {r['usd_intermediate']:,.4f}")

    if "notes" in r:
        for note in r["notes"]:
            lines.append(f"  Note: {note}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Historical FX conversion using Fed H.10 data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --amount 1000 --from USD --to JPY --date 2020-03-15
  %(prog)s --amount 1000 --from USD --to GBP --date 2020-06 --convention monthly_avg
  %(prog)s --amount 500 --from USD --to DEM --date 1995-06-15
  %(prog)s --from GBP --to JPY --date 2019 --convention annual_avg
  %(prog)s --series '[{"date":"2020-01","amount":1000},{"date":"2020-06","amount":2000}]' --from USD --to EUR
        """
    )
    parser.add_argument("--amount", type=float, help="Amount to convert (omit for rate-only lookup)")
    parser.add_argument("--from", dest="from_ccy", required=True, help="Source currency (e.g., USD, GBP, JPY)")
    parser.add_argument("--to", dest="to_ccy", required=True, help="Target currency")
    parser.add_argument("--date", help="Date: YYYY, YYYY-MM, YYYY-MM-DD, or 'March 2020'")
    parser.add_argument("--convention", choices=CONVENTIONS,
                        help="Rate convention (default: inferred from date precision)")
    parser.add_argument("--series", help="JSON array of {date, amount} objects for batch conversion")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--nsa", action="store_true",
                        help="Not seasonally adjusted — acknowledged (all H.10 data is NSA)")

    args = parser.parse_args()

    if args.nsa:
        if not args.json:
            print("Note: All Federal Reserve H.10 exchange rate data is Not Seasonally Adjusted (NSA).")
            print("      This is the only form available — there is no seasonally adjusted variant.\n")

    # Load data
    metadata = load_metadata()
    daily = load_json("daily.json")
    monthly = load_json("monthly.json")
    annual = load_json("annual.json")

    from_ccy = resolve_currency(args.from_ccy, metadata)
    to_ccy = resolve_currency(args.to_ccy, metadata)

    if args.series:
        # Batch mode
        try:
            series = json.loads(args.series)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --series: {e}", file=sys.stderr)
            sys.exit(1)

        results = []
        for item in series:
            item_date = item.get("date")
            item_amount = item.get("amount", args.amount)
            if not item_date:
                print(f"Error: Each series item must have a 'date' field", file=sys.stderr)
                sys.exit(1)
            year, month, day = parse_date_input(item_date)
            convention = infer_convention(year, month, day, args.convention)
            r = convert(item_amount, from_ccy, to_ccy, year, month, day, convention,
                        daily, monthly, annual, metadata)
            r["input_date"] = item_date
            results.append(r)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            # Table output
            print(f"{'Date':<12} {'Amount':>14} {from_ccy:>6} {'Converted':>14} {to_ccy:>6} {'Rate':>12} Convention")
            print("-" * 80)
            for r in results:
                date_str = r.get("input_date", r.get("date_used", "?"))
                amt = r.get("original_amount", "")
                conv = r.get("converted_amount", "")
                rate = r.get("effective_rate", r.get("effective_cross_rate", r.get("rate_raw", "")))
                conv_str = r.get("convention", "")
                if isinstance(amt, (int, float)):
                    amt = f"{amt:,.2f}"
                if isinstance(conv, (int, float)):
                    conv = f"{conv:,.2f}"
                print(f"{date_str:<12} {amt:>14} {from_ccy:>6} {conv:>14} {to_ccy:>6} {rate:>12} {conv_str}")
            if any("notes" in r for r in results):
                print("\nNotes:")
                for r in results:
                    for n in r.get("notes", []):
                        print(f"  - {n}")
    else:
        # Single conversion
        if not args.date:
            print("Error: --date is required for single conversion", file=sys.stderr)
            sys.exit(1)

        year, month, day = parse_date_input(args.date)
        convention = infer_convention(year, month, day, args.convention)
        r = convert(args.amount, from_ccy, to_ccy, year, month, day, convention,
                    daily, monthly, annual, metadata)

        print(format_result(r, args.json))


if __name__ == "__main__":
    main()
