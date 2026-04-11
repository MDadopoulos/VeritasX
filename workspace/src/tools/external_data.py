"""
external_data.py — Orchestrator tools for CPI inflation adjustment and FX conversion.

Imports skill logic directly via importlib (no subprocess). All data is bundled
locally — no API calls needed at runtime.

Tools:
  adjust_inflation  — Convert nominal dollars to constant dollars using BLS CPI-U (1939-2025)
  convert_fx        — Convert currencies using Fed H.10 exchange rates (1971-2025)
  get_cpi_value     — Look up raw CPI-U index value for a year/month
"""

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load skill modules via importlib (isolated, no sys.path side-effects)
# ---------------------------------------------------------------------------

_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "agentspace" / "skills"


def _load_module(name: str, path: Path):
    """Load a Python module from an arbitrary file path without polluting sys.path."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# CPI module
_CPI_PATH = _SKILLS_ROOT / "cpi-inflation-adjuster" / "scripts" / "adjust.py"
_cpi_mod = _load_module("_cpi_adjust", _CPI_PATH)

# FX module
_FX_PATH = _SKILLS_ROOT / "historical-fx" / "scripts" / "convert.py"
_fx_mod = _load_module("_fx_convert", _FX_PATH)

# ---------------------------------------------------------------------------
# Lazy-loaded data caches (loaded once on first call)
# ---------------------------------------------------------------------------

_cpi_data_cache = None
_fx_data_cache = None


def _get_cpi_data():
    global _cpi_data_cache
    if _cpi_data_cache is None:
        _cpi_data_cache = _cpi_mod.load_cpi_data()
    return _cpi_data_cache


def _get_fx_data():
    """Load all FX data files once. Returns (daily, monthly, annual, metadata)."""
    global _fx_data_cache
    if _fx_data_cache is None:
        _fx_data_cache = {
            "metadata": _fx_mod.load_metadata(),
            "daily": _fx_mod.load_json("daily.json"),
            "monthly": _fx_mod.load_json("monthly.json"),
            "annual": _fx_mod.load_json("annual.json"),
        }
    return _fx_data_cache


# ---------------------------------------------------------------------------
# Tool: adjust_inflation
# ---------------------------------------------------------------------------

def adjust_inflation(
    amount: float,
    from_year: int,
    to_year: int,
    from_month: str = None,
    to_month: str = None,
) -> dict:
    """
    Convert a dollar amount from one year's dollars to another using CPI-U.

    Uses BLS CPI-U data (base: 1982-1984 = 100). Annual averages used when
    month is omitted; specific monthly CPI used when month is provided.

    Parameters
    ----------
    amount : float
        The dollar amount to adjust.
    from_year : int
        The origin year (1939-2025).
    to_year : int
        The target year (1939-2025).
    from_month : str, optional
        Origin month (e.g., "Jan", "March", "6"). If omitted, uses annual average CPI.
    to_month : str, optional
        Target month. If omitted, uses annual average CPI.

    Returns
    -------
    dict
        On success: {"original_amount", "adjusted_amount", "from", "to",
                      "from_cpi", "to_cpi", "multiplier"}
        On error:   {"error": str}

    Examples
    --------
    adjust_inflation(1000, 1950, 2020)
    → Converts $1,000 in 1950 dollars to 2020 dollars using annual averages.

    adjust_inflation(500, 1980, 1970, from_month="Mar", to_month="Mar")
    → Converts $500 from March 1980 dollars to March 1970 dollars.
    """
    try:
        data = _get_cpi_data()
        result = _cpi_mod.adjust_single(
            amount=amount,
            from_year=from_year,
            to_year=to_year,
            from_month=from_month,
            to_month=to_month,
            data=data,
        )
        return result
    except (ValueError, KeyError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"CPI adjustment error: {e}"}


def get_cpi_value(year: int, month: str = None) -> dict:
    """
    Look up the raw CPI-U index value for a given year and optional month.

    Useful when the question asks for the CPI index itself, or when you need
    to compute a custom inflation formula rather than a simple adjustment.

    Parameters
    ----------
    year : int
        The year (1939-2025).
    month : str, optional
        Month name or number (e.g., "Jan", "March", "6"). If omitted, returns annual average.

    Returns
    -------
    dict
        On success: {"cpi_value": float, "period": str, "base": "1982-1984=100"}
        On error:   {"error": str}
    """
    try:
        data = _get_cpi_data()
        value, label = _cpi_mod.get_cpi(data, year, month)
        return {"cpi_value": value, "period": label, "base": "1982-1984=100"}
    except (ValueError, KeyError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"CPI lookup error: {e}"}


# ---------------------------------------------------------------------------
# Tool: convert_fx
# ---------------------------------------------------------------------------

def convert_fx(
    amount: float,
    from_currency: str,
    to_currency: str,
    date: str,
    convention: str = None,
) -> dict:
    """
    Convert an amount between currencies using historical Fed H.10 exchange rates.

    Supports 25+ currencies (1971-2025). DEM auto-chains through EUR post-1998.
    Cross-rates computed via USD triangulation.

    Parameters
    ----------
    amount : float
        The amount to convert.
    from_currency : str
        Source currency ISO code (e.g., "USD", "GBP", "JPY", "DEM", "CAD", "EUR").
    to_currency : str
        Target currency ISO code.
    date : str
        Date string. Accepted formats:
          - "YYYY-MM-DD" (e.g., "2020-03-15") → spot rate
          - "YYYY-MM" (e.g., "2020-03") → monthly average
          - "YYYY" (e.g., "2020") → annual average
          - "March 2020" → monthly average
    convention : str, optional
        Rate convention. If omitted, inferred from date precision.
        Options: "spot", "first_of_month", "monthly_avg", "annual_avg"

    Returns
    -------
    dict
        On success: {"from_currency", "to_currency", "convention", "original_amount",
                      "converted_amount", "date_used", "rate_raw", ...}
        On error:   {"error": str}

    Examples
    --------
    convert_fx(1000, "USD", "JPY", "2020-03-15")
    → Spot rate conversion of $1000 to JPY on March 15, 2020.

    convert_fx(500, "GBP", "DEM", "1995-06", convention="monthly_avg")
    → Monthly average cross-rate conversion from GBP to DEM in June 1995.
    """
    try:
        fx = _get_fx_data()

        from_ccy = _fx_mod.resolve_currency(from_currency, fx["metadata"])
        to_ccy = _fx_mod.resolve_currency(to_currency, fx["metadata"])

        year, month, day = _fx_mod.parse_date_input(date)
        conv = _fx_mod.infer_convention(year, month, day, convention)

        result = _fx_mod.convert(
            amount=amount,
            from_ccy=from_ccy,
            to_ccy=to_ccy,
            year=year,
            month=month,
            day=day,
            convention=conv,
            daily=fx["daily"],
            monthly=fx["monthly"],
            annual=fx["annual"],
            metadata=fx["metadata"],
        )
        return result
    except SystemExit:
        # The FX module calls sys.exit on errors — catch and convert
        return {"error": f"FX conversion failed for {amount} {from_currency} -> {to_currency} on {date}"}
    except Exception as e:
        return {"error": f"FX conversion error: {e}"}
