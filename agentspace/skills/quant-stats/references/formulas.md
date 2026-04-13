# Formulas Reference

Canonical formulas for all metric families. When computing any metric below, use
the exact formula listed here. If the user requests a variant not listed, derive it
from first principles and state the derivation.

## Table of Contents

1. [Central Tendency](#central-tendency)
2. [Dispersion](#dispersion)
3. [Correlation & Regression](#correlation--regression)
4. [Growth & Returns](#growth--returns)
5. [Smoothing & Filtering](#smoothing--filtering)
6. [Percentile-Based Measures](#percentile-based-measures)
7. [Risk Metrics](#risk-metrics)
8. [Concentration & Inequality](#concentration--inequality)
9. [Time-Series Transforms](#time-series-transforms)
10. [Elasticity & Relative Change](#elasticity--relative-change)
11. [Trend & Forecasting](#trend--forecasting)

---

## Central Tendency

### Arithmetic Mean
  x̄ = (1/n) Σ xᵢ

### Weighted Mean
  x̄_w = Σ(wᵢ · xᵢ) / Σ wᵢ
  - Weights must sum to a positive number; normalise if they don't sum to 1.

### Geometric Mean
  GM = (∏ xᵢ)^(1/n)
  - All xᵢ must be positive. For returns, use (1 + rᵢ) and subtract 1 at the end:
    GM_return = [∏(1 + rᵢ)]^(1/n) − 1

### Trimmed Mean
  Trim fraction α from each tail, then take the arithmetic mean of the remaining
  observations. Default α = 0.05 (5% each side) unless specified.

### Median
  - Odd n: middle value of sorted data.
  - Even n: average of two middle values.

### Mode
  Most frequently occurring value. Report all modes if multimodal.

---

## Dispersion

### Variance
  Sample: s² = Σ(xᵢ − x̄)² / (n − 1)
  Population: σ² = Σ(xᵢ − x̄)² / n

### Standard Deviation
  s = √(s²)  or  σ = √(σ²)

### Mean Absolute Deviation (MAD)
  MAD = (1/n) Σ |xᵢ − x̄|
  Note: some definitions use median instead of mean as the centre. Default: **mean**.

### Interquartile Range (IQR)
  IQR = Q3 − Q1 (using the same percentile method as the percentile section below)

### Range
  Range = max(x) − min(x)

### Coefficient of Variation (CV)
  CV = s / x̄
  Report as a ratio or multiply by 100 for percentage form. Default: ratio form.
  - Undefined or misleading when x̄ ≈ 0.

---

## Correlation & Regression

### Pearson Correlation
  r = Σ[(xᵢ − x̄)(yᵢ − ȳ)] / √[Σ(xᵢ − x̄)² · Σ(yᵢ − ȳ)²]

### Spearman Rank Correlation
  Replace values with their ranks, then compute Pearson on the ranks.

### Kendall Tau
  τ = (concordant − discordant) / [n(n−1)/2]

### OLS Linear Regression (y = α + βx + ε)
  β = Σ[(xᵢ − x̄)(yᵢ − ȳ)] / Σ(xᵢ − x̄)²
  α = ȳ − β · x̄

### R-Squared
  R² = 1 − [Σ(yᵢ − ŷᵢ)² / Σ(yᵢ − ȳ)²]

### Adjusted R-Squared
  R²_adj = 1 − [(1 − R²)(n − 1) / (n − k − 1)]
  where k = number of predictors (excluding intercept).

### Beta (CAPM-style)
  β = Cov(rᵢ, rₘ) / Var(rₘ)
  where rᵢ = asset returns, rₘ = market/benchmark returns.

### Residual Standard Error
  RSE = √[Σ(yᵢ − ŷᵢ)² / (n − k − 1)]

---

## Growth & Returns

### Simple Return
  rₜ = (Pₜ − Pₜ₋₁) / Pₜ₋₁ = Pₜ/Pₜ₋₁ − 1

### Log Return (Continuously Compounded)
  rₜ = ln(Pₜ / Pₜ₋₁)

### Cumulative Return
  R_cum = (P_end / P_start) − 1
  Or from a return series: R_cum = ∏(1 + rₜ) − 1

### CAGR (Compound Annual Growth Rate)
  CAGR = (V_end / V_start)^(1/T) − 1
  where T = number of years (can be fractional).

### Annualised Return from Sub-Annual Returns
  r_annual = (1 + r_period)^(periods_per_year) − 1
  Or for log returns: r_annual = r_period × periods_per_year

### Annualised Volatility
  σ_annual = σ_period × √(periods_per_year)

---

## Smoothing & Filtering

### Simple Moving Average (SMA)
  SMA_t(k) = (1/k) Σ_{i=0}^{k-1} xₜ₋ᵢ

### Exponential Moving Average (EMA)
  EMA_t = α · xₜ + (1 − α) · EMA_{t−1}
  where α = 2/(k+1) for span k. Initialise EMA₁ = x₁ (or SMA of first k values).

### Hodrick-Prescott Filter
  Minimise: Σ(yₜ − τₜ)² + λ Σ[(τₜ₊₁ − τₜ) − (τₜ − τₜ₋₁)]²
  Default λ: 1600 (quarterly), 6.25 (annual), 129600 (monthly).

---

## Percentile-Based Measures

### Percentile
  Use the **linear interpolation** method (numpy default, `method='linear'`):
  - Rank r = (p/100) × (n − 1)
  - Lower index i = floor(r), fraction f = r − i
  - Percentile = x[i] + f × (x[i+1] − x[i])

### Quartiles
  Q1 = 25th percentile, Q2 = 50th (median), Q3 = 75th.

### Value at Risk (VaR) — Historical
  VaR_α = −Percentile(returns, α)
  Default α = 5% (i.e., the 5th percentile of the return distribution, sign-flipped
  so VaR is reported as a positive loss).

### Conditional VaR (Expected Shortfall / CVaR)
  CVaR_α = −Mean(returns where return ≤ Percentile(returns, α))

---

## Risk Metrics

### Sharpe Ratio
  SR = (r̄ − r_f) / σ
  where r̄ = mean return, r_f = risk-free rate, σ = std dev of returns.
  If r_f is not provided, assume r_f = 0 and state this assumption.
  For annualised Sharpe: SR_annual = SR_period × √(periods_per_year).

### Sortino Ratio
  Sortino = (r̄ − r_f) / σ_down
  where σ_down = √[(1/n) Σ min(rₜ − r_f, 0)²]  (downside deviation).

### Treynor Ratio
  Treynor = (r̄ − r_f) / β

### Maximum Drawdown
  DD_t = (P_t − Peak_t) / Peak_t  where Peak_t = max(P₁, ..., Pₜ)
  Max Drawdown = min(DD_t)  (most negative value)
  Report as a positive percentage representing the largest peak-to-trough decline.

### Downside Deviation
  σ_down = √[(1/n) Σ min(rₜ − MAR, 0)²]
  MAR = Minimum Acceptable Return. Default: 0 (or r_f if provided).

### Tracking Error
  TE = σ(rₚ − rᵦ)  (std dev of active returns)

### Information Ratio
  IR = (r̄ₚ − r̄ᵦ) / TE

---

## Concentration & Inequality

### Herfindahl-Hirschman Index (HHI)
  HHI = Σ sᵢ²
  where sᵢ = market share of firm i (as a fraction summing to 1).
  Some conventions use percentages (sᵢ in [0,100]), giving HHI in [0, 10000].
  Default: **fraction form** (HHI ∈ [0, 1]). State which.

### Gini Coefficient
  G = [Σᵢ Σⱼ |xᵢ − xⱼ|] / (2n²x̄)
  Equivalently using sorted values: G = (2 Σᵢ i·x_(i)) / (n Σ x_(i)) − (n+1)/n
  Range: 0 (perfect equality) to 1 (perfect inequality).

### Concentration Ratio (CR-k)
  CR_k = Σ (top k shares)  (sum of the k largest market shares).

---

## Time-Series Transforms

### First Difference
  Δxₜ = xₜ − xₜ₋₁

### Seasonal Difference
  Δₛ xₜ = xₜ − xₜ₋ₛ  (s = seasonal period)

### Autocorrelation (ACF) at lag k
  ρ(k) = Σ_{t=k+1}^{n} (xₜ − x̄)(xₜ₋ₖ − x̄) / Σ(xₜ − x̄)²

### Partial Autocorrelation (PACF)
  Use the Durbin-Levinson recursion or statsmodels implementation.

### Seasonal Decomposition
  Additive: xₜ = Tₜ + Sₜ + Rₜ
  Multiplicative: xₜ = Tₜ × Sₜ × Rₜ
  Default: **additive** unless the user specifies or the data shows
  variance proportional to level.

---

## Elasticity & Relative Change

### Percentage Change
  Δ% = (x_new − x_old) / x_old × 100

### Basis-Point Change
  Δbps = (x_new − x_old) × 10000  (for rates in decimal form)

### Point Elasticity
  ε = (∂Q/∂P) × (P/Q)

### Arc Elasticity (Midpoint Method)
  ε = [(Q₂ − Q₁)/((Q₂ + Q₁)/2)] / [(P₂ − P₁)/((P₂ + P₁)/2)]

---

## Trend & Forecasting

### Linear Trend
  Fit y = a + bt via OLS. Report a, b, and R².

### Polynomial Fit (degree d)
  Fit y = a₀ + a₁t + a₂t² + ... + aₔtᵈ via least squares.
  Default: prompt the user for degree. Warn about overfitting if d > 3.

### Exponential Fit
  Fit ln(y) = a + bt, then y = exp(a) · exp(bt).
  Only valid for positive y.

### Simple Extrapolation
  Extend the fitted trend by k periods. State the model used and that
  extrapolation assumes the trend continues unchanged.
