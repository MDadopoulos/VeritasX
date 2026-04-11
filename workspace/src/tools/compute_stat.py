"""
compute_stat.py — Orchestrator tool wrapping the quant-stats computation engine.

Imports metric functions directly from agentspace/skills/quant-stats/scripts/compute.py
via importlib (no subprocess, no sys.path pollution). Returns structured results with
metric name, formula variant, value, and unit.

Supported metrics:
  Central tendency: mean, weighted_mean, geometric_mean, geometric_mean_return, trimmed_mean, median
  Dispersion: std_dev, variance, mad, coefficient_of_variation, iqr
  Correlation/regression: correlation, ols_regression, beta_capm
  Growth/returns: simple_returns, log_returns, cagr, cumulative_return, annualised_return, annualised_volatility
  Smoothing: sma, ema
  Percentile-based: percentile, var_historical, cvar
  Risk metrics: sharpe_ratio, sortino_ratio, max_drawdown, tracking_error, information_ratio
  Concentration: hhi, cr_k, gini
  Time-series: difference, autocorrelation
  Elasticity: percentage_change, arc_elasticity
  Trend: linear_trend
"""

import importlib.util
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load the quant-stats module via importlib (isolated, no sys.path side-effects)
# ---------------------------------------------------------------------------

_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "agentspace" / "skills"
_COMPUTE_PATH = _SKILLS_ROOT / "quant-stats" / "scripts" / "compute.py"

_spec = importlib.util.spec_from_file_location("_quant_compute", str(_COMPUTE_PATH))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_METRICS = _mod.METRICS

# Expose the list for prompt generation
AVAILABLE_METRICS = sorted(_METRICS.keys())


def compute_stat(metric: str, data: str) -> dict:
    """
    Compute a statistical metric on the provided data.

    Parameters
    ----------
    metric : str
        Name of the metric to compute. Must be one of the supported metrics.
        Common examples:
          - "mean", "geometric_mean", "median" (central tendency)
          - "std_dev" (use data.population=true for population SD, false for sample)
          - "mad" (mean absolute deviation, data.centre="mean" or "median")
          - "correlation" (Pearson/Spearman/Kendall, data.method="pearson")
          - "ols_regression" (data.x=[...], data.y=[...])
          - "cagr" (data.start_value, data.end_value, data.years)
          - "percentile" (data.values=[...], data.percentile=75)
          - "var_historical", "cvar" (Expected Shortfall)
          - "hhi", "gini", "arc_elasticity"
          - "sma", "ema" (smoothing)
          - "linear_trend" (with optional data.forecast_periods)
    data : str
        JSON string containing the input data for the metric.
        Each metric expects specific keys — see examples:
          mean:           {"values": [1, 2, 3, 4, 5]}
          std_dev:        {"values": [1, 2, 3], "population": true}
          correlation:    {"x": [1,2,3], "y": [4,5,6], "method": "pearson"}
          ols_regression: {"x": [1,2,3,4], "y": [2,4,5,8]}
          cagr:           {"start_value": 100, "end_value": 200, "years": 10}
          percentile:     {"values": [1,2,3,4,5], "percentile": 75}
          cvar:           {"returns": [-0.02, 0.01, -0.05, 0.03], "alpha": 5, "as_decimal": true}
          hhi:            {"values": [50, 30, 20]}
          arc_elasticity: {"p1": 10, "p2": 12, "q1": 100, "q2": 90}
          linear_trend:   {"values": [10,12,15,18], "forecast_periods": 3}

    Returns
    -------
    dict
        On success: {"metric": str, "variant": str, "formula": str, "value": ..., "unit": str, "notes": str}
        On error:   {"error": str}
    """
    # Validate metric name
    if metric not in _METRICS:
        return {
            "error": f"Unknown metric '{metric}'. Available: {', '.join(AVAILABLE_METRICS)}"
        }

    # Parse JSON data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in data parameter: {e}"}
    elif isinstance(data, dict):
        parsed = data
    else:
        return {"error": "data must be a JSON string or dict"}

    # Execute the metric function
    try:
        result = _METRICS[metric](parsed)
    except Exception as e:
        return {"error": f"Computation error in '{metric}': {e}"}

    return result
