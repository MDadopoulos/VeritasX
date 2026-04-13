#!/usr/bin/env python3
"""
quant-stats computation engine.

Usage:
    python compute.py <metric> [--args in JSON] < data.json
    python compute.py <metric> --inline '<json string>'

The script reads a JSON object from stdin (or --inline) containing the data,
computes the requested metric, and prints a JSON result to stdout.

Every result includes:
  - metric: name of the metric computed
  - variant: which convention / formula variant was used
  - formula: plain-text formula
  - value: the numeric result (or dict of results)
  - unit: unit of the result
  - notes: any warnings or assumptions

Exit code 0 on success, 1 on error (with JSON error message on stdout).
"""

import sys
import json
import math
import argparse
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pct(values: list[float], as_decimal: bool = False) -> np.ndarray:
    """Convert percentage values to decimal if needed."""
    arr = np.array(values, dtype=float)
    if not as_decimal and np.any(np.abs(arr) > 1):
        # Heuristic: if values look like percentages (e.g. 2, -1, 3), convert
        arr = arr / 100.0
    return arr


def _result(metric: str, value: Any, formula: str, variant: str,
            unit: str = "", notes: str = "") -> dict:
    """Standardised result envelope."""
    # Round floats for readability
    def _round(v):
        if isinstance(v, float):
            return round(v, 8)
        if isinstance(v, dict):
            return {k: _round(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_round(vv) for vv in v]
        return v

    return {
        "metric": metric,
        "variant": variant,
        "formula": formula,
        "value": _round(value),
        "unit": unit,
        "notes": notes,
    }


def _error(msg: str) -> dict:
    return {"error": msg}


# ---------------------------------------------------------------------------
# Central Tendency
# ---------------------------------------------------------------------------

def mean(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    x_clean = x[~np.isnan(x)]
    dropped = len(x) - len(x_clean)
    val = float(np.mean(x_clean))
    notes = f"Dropped {dropped} NaN values." if dropped else ""
    return _result("arithmetic_mean", val,
                   "x̄ = (1/n) Σ xᵢ", "arithmetic", notes=notes)


def weighted_mean(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    w = np.array(data["weights"], dtype=float)
    if len(x) != len(w):
        return _error("values and weights must have the same length")
    val = float(np.average(x, weights=w))
    return _result("weighted_mean", val,
                   "x̄_w = Σ(wᵢ·xᵢ) / Σwᵢ", "weighted")


def geometric_mean(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    if np.any(x <= 0):
        return _error("geometric mean requires all positive values")
    val = float(np.exp(np.mean(np.log(x))))
    return _result("geometric_mean", val,
                   "GM = (∏ xᵢ)^(1/n)", "geometric")


def geometric_mean_return(data: dict) -> dict:
    """Geometric mean of returns (input as decimals or percentages)."""
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    val = float(np.prod(1 + r) ** (1 / len(r)) - 1)
    return _result("geometric_mean_return", val,
                   "GM_return = [∏(1+rᵢ)]^(1/n) − 1", "geometric, returns",
                   unit="decimal return")


def trimmed_mean(data: dict) -> dict:
    from scipy.stats import trim_mean as _tm
    x = np.array(data["values"], dtype=float)
    alpha = data.get("alpha", 0.05)
    val = float(_tm(x, alpha))
    return _result("trimmed_mean", val,
                   f"Trim {alpha*100:.0f}% from each tail, then arithmetic mean",
                   f"trimmed α={alpha}")


def median(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    val = float(np.median(x))
    return _result("median", val,
                   "Middle value (odd n) or average of two middle values (even n)",
                   "standard")


# ---------------------------------------------------------------------------
# Dispersion
# ---------------------------------------------------------------------------

def std_dev(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    population = data.get("population", False)
    ddof = 0 if population else 1
    val = float(np.std(x, ddof=ddof))
    variant = "population (n)" if population else "sample (n−1)"
    formula = "σ = √[Σ(xᵢ−x̄)²/n]" if population else "s = √[Σ(xᵢ−x̄)²/(n−1)]"
    return _result("standard_deviation", val, formula, variant)


def variance(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    population = data.get("population", False)
    ddof = 0 if population else 1
    val = float(np.var(x, ddof=ddof))
    variant = "population (n)" if population else "sample (n−1)"
    formula = "σ² = Σ(xᵢ−x̄)²/n" if population else "s² = Σ(xᵢ−x̄)²/(n−1)"
    return _result("variance", val, formula, variant)


def mad(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    centre = data.get("centre", "mean")
    c = np.mean(x) if centre == "mean" else np.median(x)
    val = float(np.mean(np.abs(x - c)))
    return _result("mean_absolute_deviation", val,
                   f"MAD = (1/n) Σ|xᵢ − {centre}|", f"centre={centre}")


def coefficient_of_variation(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    population = data.get("population", False)
    ddof = 0 if population else 1
    m = float(np.mean(x))
    s = float(np.std(x, ddof=ddof))
    if abs(m) < 1e-12:
        return _error("CV undefined when mean ≈ 0")
    val = s / m
    return _result("coefficient_of_variation", val,
                   "CV = s / x̄", "ratio form",
                   notes="Multiply by 100 for percentage form.")


def iqr(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    q1, q3 = float(np.percentile(x, 25)), float(np.percentile(x, 75))
    val = q3 - q1
    return _result("interquartile_range", val,
                   "IQR = Q3 − Q1", "linear interpolation",
                   notes=f"Q1={round(q1,8)}, Q3={round(q3,8)}")


# ---------------------------------------------------------------------------
# Correlation & Regression
# ---------------------------------------------------------------------------

def correlation(data: dict) -> dict:
    x = np.array(data["x"], dtype=float)
    y = np.array(data["y"], dtype=float)
    method = data.get("method", "pearson")

    if method == "pearson":
        val = float(np.corrcoef(x, y)[0, 1])
        formula = "r = Σ[(xᵢ−x̄)(yᵢ−ȳ)] / √[Σ(xᵢ−x̄)²·Σ(yᵢ−ȳ)²]"
    elif method == "spearman":
        from scipy.stats import spearmanr
        val = float(spearmanr(x, y).statistic)
        formula = "Pearson correlation on ranks"
    elif method == "kendall":
        from scipy.stats import kendalltau
        val = float(kendalltau(x, y).statistic)
        formula = "τ = (concordant − discordant) / [n(n−1)/2]"
    else:
        return _error(f"Unknown correlation method: {method}")

    return _result("correlation", val, formula, method, unit="dimensionless")


def ols_regression(data: dict) -> dict:
    x = np.array(data["x"], dtype=float)
    y = np.array(data["y"], dtype=float)

    n = len(x)
    x_mean, y_mean = np.mean(x), np.mean(y)
    beta = float(np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean) ** 2))
    alpha = float(y_mean - beta * x_mean)
    y_hat = alpha + beta * x
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else float('nan')
    rse = float(math.sqrt(ss_res / (n - 2))) if n > 2 else float('nan')

    return _result("ols_regression", {
        "intercept_alpha": round(alpha, 8),
        "slope_beta": round(beta, 8),
        "r_squared": round(r_squared, 8),
        "residual_std_error": round(rse, 8),
        "n": n,
    }, "y = α + βx; β = Cov(x,y)/Var(x)", "OLS with intercept")


def beta_capm(data: dict) -> dict:
    """CAPM beta: Cov(asset, benchmark) / Var(benchmark)."""
    asset = _parse_pct(data["asset_returns"], data.get("as_decimal", False))
    bench = _parse_pct(data["benchmark_returns"], data.get("as_decimal", False))
    cov = float(np.cov(asset, bench, ddof=1)[0, 1])
    var_bench = float(np.var(bench, ddof=1))
    val = cov / var_bench
    return _result("beta_capm", val,
                   "β = Cov(rᵢ, rₘ) / Var(rₘ)", "sample covariance, ddof=1",
                   unit="dimensionless")


# ---------------------------------------------------------------------------
# Growth & Returns
# ---------------------------------------------------------------------------

def simple_returns(data: dict) -> dict:
    prices = np.array(data["prices"], dtype=float)
    rets = (prices[1:] / prices[:-1]) - 1
    return _result("simple_returns", rets.tolist(),
                   "rₜ = Pₜ/Pₜ₋₁ − 1", "simple", unit="decimal return")


def log_returns(data: dict) -> dict:
    prices = np.array(data["prices"], dtype=float)
    rets = np.log(prices[1:] / prices[:-1])
    return _result("log_returns", rets.tolist(),
                   "rₜ = ln(Pₜ/Pₜ₋₁)", "continuously compounded",
                   unit="log return")


def cagr(data: dict) -> dict:
    v_start = float(data["start_value"])
    v_end = float(data["end_value"])
    years = float(data["years"])
    val = (v_end / v_start) ** (1 / years) - 1
    return _result("cagr", float(val),
                   "CAGR = (V_end/V_start)^(1/T) − 1", "standard",
                   unit="decimal annual return",
                   notes=f"T = {years} years")


def cumulative_return(data: dict) -> dict:
    if "prices" in data:
        prices = np.array(data["prices"], dtype=float)
        val = float(prices[-1] / prices[0] - 1)
        formula = "R_cum = P_end/P_start − 1"
    else:
        r = _parse_pct(data["returns"], data.get("as_decimal", False))
        val = float(np.prod(1 + r) - 1)
        formula = "R_cum = ∏(1+rₜ) − 1"
    return _result("cumulative_return", val, formula, "standard",
                   unit="decimal return")


def annualised_return(data: dict) -> dict:
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    periods_per_year = data.get("periods_per_year", 12)
    cum = float(np.prod(1 + r) - 1)
    n_periods = len(r)
    years = n_periods / periods_per_year
    val = float((1 + cum) ** (1 / years) - 1)
    return _result("annualised_return", val,
                   "r_annual = (1 + R_cum)^(1/T) − 1",
                   f"periods_per_year={periods_per_year}",
                   unit="decimal annual return",
                   notes=f"{n_periods} periods = {round(years,4)} years")


def annualised_volatility(data: dict) -> dict:
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    periods_per_year = data.get("periods_per_year", 12)
    population = data.get("population", False)
    ddof = 0 if population else 1
    vol_period = float(np.std(r, ddof=ddof))
    val = vol_period * math.sqrt(periods_per_year)
    variant = "population" if population else "sample (n−1)"
    return _result("annualised_volatility", val,
                   "σ_annual = σ_period × √(periods_per_year)",
                   f"{variant}, periods_per_year={periods_per_year}",
                   unit="decimal (annualised std dev)")


# ---------------------------------------------------------------------------
# Smoothing
# ---------------------------------------------------------------------------

def sma(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    k = int(data["window"])
    if k > len(x):
        return _error(f"Window {k} > series length {len(x)}")
    result = []
    for i in range(len(x) - k + 1):
        result.append(float(np.mean(x[i:i+k])))
    return _result("simple_moving_average", result,
                   "SMA_t(k) = (1/k) Σ xₜ₋ᵢ for i=0..k-1",
                   f"window={k}")


def ema(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    span = int(data["span"])
    alpha = 2.0 / (span + 1)
    result = [float(x[0])]
    for i in range(1, len(x)):
        result.append(alpha * float(x[i]) + (1 - alpha) * result[-1])
    return _result("exponential_moving_average", result,
                   "EMA_t = α·xₜ + (1−α)·EMA_{t−1}; α=2/(span+1)",
                   f"span={span}, α={round(alpha,6)}")


# ---------------------------------------------------------------------------
# Percentile-Based
# ---------------------------------------------------------------------------

def percentile(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    p = data["percentile"]
    val = float(np.percentile(x, p))
    return _result("percentile", val,
                   "Linear interpolation (numpy default)",
                   f"p={p}", unit=data.get("unit", ""))


def var_historical(data: dict) -> dict:
    """Historical Value at Risk."""
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    alpha = data.get("alpha", 5)
    cutoff = float(np.percentile(r, alpha))
    val = -cutoff  # VaR as positive loss
    return _result("value_at_risk", val,
                   f"VaR_{alpha}% = −Percentile(returns, {alpha})",
                   f"historical, α={alpha}%",
                   unit="decimal (positive = loss)",
                   notes=f"Cutoff return = {round(cutoff,8)}")


def cvar(data: dict) -> dict:
    """Conditional VaR / Expected Shortfall."""
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    alpha = data.get("alpha", 5)
    cutoff = np.percentile(r, alpha)
    tail = r[r <= cutoff]
    val = -float(np.mean(tail)) if len(tail) > 0 else float('nan')
    return _result("conditional_var", val,
                   f"CVaR_{alpha}% = −Mean(returns ≤ VaR cutoff)",
                   f"historical, α={alpha}%",
                   unit="decimal (positive = loss)")


# ---------------------------------------------------------------------------
# Risk Metrics
# ---------------------------------------------------------------------------

def sharpe_ratio(data: dict) -> dict:
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    rf_annual = data.get("risk_free_rate", 0.0)
    periods_per_year = data.get("periods_per_year", 12)

    # Convert annual rf to per-period
    rf_period = (1 + rf_annual) ** (1 / periods_per_year) - 1
    excess = r - rf_period
    sr_period = float(np.mean(excess) / np.std(excess, ddof=1))
    sr_annual = sr_period * math.sqrt(periods_per_year)

    return _result("sharpe_ratio", {
        "per_period": round(sr_period, 8),
        "annualised": round(sr_annual, 8),
    }, "SR = (r̄ − r_f) / σ; SR_annual = SR × √(periods_per_year)",
       f"sample std, rf_annual={rf_annual}, periods_per_year={periods_per_year}",
       unit="dimensionless",
       notes=f"rf per period = {round(rf_period, 8)}")


def sortino_ratio(data: dict) -> dict:
    r = _parse_pct(data["returns"], data.get("as_decimal", False))
    rf_annual = data.get("risk_free_rate", 0.0)
    periods_per_year = data.get("periods_per_year", 12)
    mar = data.get("mar", None)
    if mar is None:
        mar = (1 + rf_annual) ** (1 / periods_per_year) - 1

    downside = np.minimum(r - mar, 0)
    downside_dev = float(np.sqrt(np.mean(downside ** 2)))
    if downside_dev < 1e-15:
        return _error("Downside deviation is zero; Sortino undefined.")
    val = float((np.mean(r) - mar) / downside_dev)
    return _result("sortino_ratio", val,
                   "Sortino = (r̄ − MAR) / σ_down",
                   f"MAR={round(mar,8)}", unit="dimensionless")


def max_drawdown(data: dict) -> dict:
    prices = np.array(data["prices"], dtype=float)
    peak = np.maximum.accumulate(prices)
    dd = (prices - peak) / peak
    mdd = float(np.min(dd))
    mdd_idx = int(np.argmin(dd))

    # Find the peak before the max drawdown
    peak_idx = int(np.argmax(prices[:mdd_idx + 1]))

    return _result("max_drawdown", {
        "max_drawdown": round(mdd, 8),
        "max_drawdown_pct": round(abs(mdd) * 100, 4),
        "peak_index": peak_idx,
        "trough_index": mdd_idx,
    }, "DD_t = (P_t − Peak_t)/Peak_t; MDD = min(DD_t)",
       "standard",
       unit="decimal (negative = loss)",
       notes=f"Peak at index {peak_idx}, trough at index {mdd_idx}")


def tracking_error(data: dict) -> dict:
    rp = _parse_pct(data["portfolio_returns"], data.get("as_decimal", False))
    rb = _parse_pct(data["benchmark_returns"], data.get("as_decimal", False))
    active = rp - rb
    val = float(np.std(active, ddof=1))
    return _result("tracking_error", val,
                   "TE = σ(rₚ − rᵦ)", "sample std of active returns",
                   unit="decimal")


def information_ratio(data: dict) -> dict:
    rp = _parse_pct(data["portfolio_returns"], data.get("as_decimal", False))
    rb = _parse_pct(data["benchmark_returns"], data.get("as_decimal", False))
    active = rp - rb
    te = float(np.std(active, ddof=1))
    if te < 1e-15:
        return _error("Tracking error is zero; IR undefined.")
    val = float(np.mean(active) / te)
    return _result("information_ratio", val,
                   "IR = (r̄ₚ − r̄ᵦ) / TE", "standard",
                   unit="dimensionless")


# ---------------------------------------------------------------------------
# Concentration & Inequality
# ---------------------------------------------------------------------------

def hhi(data: dict) -> dict:
    values = np.array(data["values"], dtype=float)
    total = np.sum(values)
    shares = values / total
    val = float(np.sum(shares ** 2))
    return _result("herfindahl_hirschman_index", val,
                   "HHI = Σ sᵢ²  (shares as fractions summing to 1)",
                   "fraction form ∈ [0,1]",
                   notes=f"Market shares: {np.round(shares, 6).tolist()}")


def cr_k(data: dict) -> dict:
    values = np.array(data["values"], dtype=float)
    k = int(data.get("k", 3))
    total = np.sum(values)
    shares = values / total
    sorted_shares = np.sort(shares)[::-1]
    val = float(np.sum(sorted_shares[:k]))
    return _result(f"concentration_ratio_CR{k}", val,
                   f"CR_{k} = sum of top {k} market shares",
                   "fraction form",
                   notes=f"Top {k} shares: {np.round(sorted_shares[:k], 6).tolist()}")


def gini(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    x_sorted = np.sort(x)
    n = len(x_sorted)
    index = np.arange(1, n + 1)
    val = float((2 * np.sum(index * x_sorted)) / (n * np.sum(x_sorted)) - (n + 1) / n)
    return _result("gini_coefficient", val,
                   "G = (2·Σ i·x_(i))/(n·Σx_(i)) − (n+1)/n",
                   "sorted-values formula",
                   unit="dimensionless ∈ [0,1]")


# ---------------------------------------------------------------------------
# Time-Series Transforms
# ---------------------------------------------------------------------------

def difference(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    lag = int(data.get("lag", 1))
    diff = (x[lag:] - x[:-lag]).tolist()
    return _result("difference", diff,
                   f"Δxₜ = xₜ − xₜ₋{lag}",
                   f"lag={lag}")


def autocorrelation(data: dict) -> dict:
    x = np.array(data["values"], dtype=float)
    max_lag = int(data.get("max_lag", 10))
    x_demean = x - np.mean(x)
    denom = float(np.sum(x_demean ** 2))
    acf_vals = []
    for k in range(0, min(max_lag + 1, len(x))):
        if k == 0:
            acf_vals.append(1.0)
        else:
            num = float(np.sum(x_demean[k:] * x_demean[:-k]))
            acf_vals.append(round(num / denom, 8))
    return _result("autocorrelation", acf_vals,
                   "ρ(k) = Σ(xₜ−x̄)(xₜ₋ₖ−x̄) / Σ(xₜ−x̄)²",
                   f"max_lag={max_lag}",
                   notes="Index 0 = lag 0 (always 1.0)")


# ---------------------------------------------------------------------------
# Elasticity & Relative Change
# ---------------------------------------------------------------------------

def percentage_change(data: dict) -> dict:
    old = float(data["old_value"])
    new = float(data["new_value"])
    val = (new - old) / old * 100
    return _result("percentage_change", round(val, 8),
                   "Δ% = (x_new − x_old) / x_old × 100",
                   "standard", unit="%")


def arc_elasticity(data: dict) -> dict:
    p1, p2 = float(data["p1"]), float(data["p2"])
    q1, q2 = float(data["q1"]), float(data["q2"])
    dq = (q2 - q1) / ((q2 + q1) / 2)
    dp = (p2 - p1) / ((p2 + p1) / 2)
    if abs(dp) < 1e-15:
        return _error("Price change is zero; elasticity undefined.")
    val = dq / dp
    return _result("arc_elasticity", round(float(val), 8),
                   "ε = [ΔQ/midQ] / [ΔP/midP]",
                   "midpoint method", unit="dimensionless")


# ---------------------------------------------------------------------------
# Trend & Forecasting
# ---------------------------------------------------------------------------

def linear_trend(data: dict) -> dict:
    y = np.array(data["values"], dtype=float)
    t = np.arange(len(y), dtype=float)
    if "time_index" in data:
        t = np.array(data["time_index"], dtype=float)

    t_mean, y_mean = np.mean(t), np.mean(y)
    b = float(np.sum((t - t_mean) * (y - y_mean)) / np.sum((t - t_mean) ** 2))
    a = float(y_mean - b * t_mean)
    y_hat = a + b * t
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y_mean) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else float('nan')

    result_val = {"intercept": round(a, 8), "slope": round(b, 8),
                  "r_squared": round(r2, 8)}

    # Forecast if requested
    if "forecast_periods" in data:
        k = int(data["forecast_periods"])
        last_t = t[-1]
        future_t = np.arange(last_t + 1, last_t + k + 1)
        forecasts = (a + b * future_t).tolist()
        result_val["forecast"] = [round(f, 4) for f in forecasts]

    return _result("linear_trend", result_val,
                   "y = a + bt (OLS)", "standard",
                   notes="Extrapolation assumes trend continues unchanged.")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

METRICS = {
    # Central tendency
    "mean": mean,
    "weighted_mean": weighted_mean,
    "geometric_mean": geometric_mean,
    "geometric_mean_return": geometric_mean_return,
    "trimmed_mean": trimmed_mean,
    "median": median,
    # Dispersion
    "std_dev": std_dev,
    "variance": variance,
    "mad": mad,
    "coefficient_of_variation": coefficient_of_variation,
    "iqr": iqr,
    # Correlation & regression
    "correlation": correlation,
    "ols_regression": ols_regression,
    "beta_capm": beta_capm,
    # Growth & returns
    "simple_returns": simple_returns,
    "log_returns": log_returns,
    "cagr": cagr,
    "cumulative_return": cumulative_return,
    "annualised_return": annualised_return,
    "annualised_volatility": annualised_volatility,
    # Smoothing
    "sma": sma,
    "ema": ema,
    # Percentile-based
    "percentile": percentile,
    "var_historical": var_historical,
    "cvar": cvar,
    # Risk metrics
    "sharpe_ratio": sharpe_ratio,
    "sortino_ratio": sortino_ratio,
    "max_drawdown": max_drawdown,
    "tracking_error": tracking_error,
    "information_ratio": information_ratio,
    # Concentration
    "hhi": hhi,
    "cr_k": cr_k,
    "gini": gini,
    # Time-series
    "difference": difference,
    "autocorrelation": autocorrelation,
    # Elasticity
    "percentage_change": percentage_change,
    "arc_elasticity": arc_elasticity,
    # Trend
    "linear_trend": linear_trend,
}


def main():
    parser = argparse.ArgumentParser(description="Quant-stats computation engine")
    parser.add_argument("metric", choices=list(METRICS.keys()),
                        help="Metric to compute")
    parser.add_argument("--inline", type=str, default=None,
                        help="JSON data as a string (alternative to stdin)")
    args = parser.parse_args()

    try:
        if args.inline:
            data = json.loads(args.inline)
        else:
            data = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        print(json.dumps(_error(f"Invalid JSON input: {e}")))
        sys.exit(1)

    func = METRICS[args.metric]
    try:
        result = func(data)
    except Exception as e:
        result = _error(f"Computation error: {e}")
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
