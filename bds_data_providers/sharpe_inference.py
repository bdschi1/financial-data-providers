"""Sharpe ratio inference — rigorous statistical testing for Sharpe ratios.

Implements the methods from:

    Bailey, D. H. & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting, and Non-Normality.
    Journal of Portfolio Management, 40(5), 94-107.

    Bailey, D. H. & Lopez de Prado, M. (2012). The Sharpe Ratio Efficient
    Frontier. Journal of Risk, 15(2), 3-44.

    Lo, A. (2002). The Statistics of Sharpe Ratios. Financial Analysts
    Journal, 58(4), 36-52.

Companion code adapted from zoonek/2025-sharpe-ratio (MIT License),
which accompanies "Sharpe Ratio Inference: A New Standard".

Functions:
    sharpe_ratio_variance      — Full asymptotic variance (non-normality + autocorrelation + multiple testing)
    probabilistic_sharpe_ratio — P(true SR > SR_0)
    minimum_track_record_length — Minimum observations for significance
    critical_sharpe_ratio      — Threshold SR for rejecting H_0
    sharpe_ratio_power         — Statistical power (1-beta)
    posterior_fdr / observed_fdr — False discovery rates
    control_for_fdr            — FDR-controlled strategy testing
    adjusted_p_values_*        — FWER corrections (Bonferroni, Sidak, Holm)
    expected_maximum_sharpe_ratio — E[max SR] under the null
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import norm


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_expectation_gh(n_nodes: int = 200):
    """Return a function that computes E[g(Z)] via Gauss-Hermite quadrature.

    Z ~ N(0,1). The returned callable takes g: Callable[[ndarray], ndarray]
    and returns float ~ E[g(Z)].
    """
    nodes, weights = np.polynomial.hermite.hermgauss(n_nodes)
    # Transform from Hermite weight exp(-x^2) to standard normal
    nodes_std = nodes * math.sqrt(2)
    weights_norm = weights / math.sqrt(math.pi)

    def expectation(g) -> float:
        return float(np.sum(weights_norm * g(nodes_std)))

    return expectation


def _moments_mk(k: int, rho: float = 0.0):
    """Compute E[M_k], E[M_k^2], Var[M_k] for the maximum of k correlated normals.

    M_k = max(Z_1, ..., Z_k) where Z_i are standard normal with common
    pairwise correlation rho. Uses Gauss-Hermite quadrature.

    Returns:
        (e_mk, e_mk2, var_mk) -- mean, second moment, variance of M_k.
    """
    if k <= 0:
        return 0.0, 0.0, 0.0
    if k == 1:
        return 0.0, 1.0, 1.0

    E = _make_expectation_gh(200)

    rho = max(0.0, min(rho, 1.0))
    sqrt_1mrho = math.sqrt(1.0 - rho) if rho < 1.0 else 0.0

    if rho >= 1.0 - 1e-12:
        # Perfect correlation: max of identical normals = single normal
        return 0.0, 1.0, 1.0

    # E[max of k standard normals] for iid case via GH quadrature
    e_max_iid = E(lambda z: z * k * norm.cdf(z) ** (k - 1))
    e_max_iid_sq = E(lambda z: z**2 * k * norm.cdf(z) ** (k - 1))

    # For correlated normals with common correlation rho:
    # Z_i = sqrt(rho)*W + sqrt(1-rho)*X_i, W,X_i iid N(0,1)
    # max(Z_i) = sqrt(rho)*W + sqrt(1-rho)*max(X_i)
    # E[max(Z_i)] = sqrt(1-rho) * E[max(X_i)]  (since E[W]=0)
    e_mk = sqrt_1mrho * e_max_iid

    # E[max(Z_i)^2] = rho * E[W^2] + (1-rho) * E[max(X_i)^2]
    # = rho + (1-rho) * E[max(X_i)^2]
    e_mk2 = rho + (1.0 - rho) * e_max_iid_sq

    var_mk = max(e_mk2 - e_mk ** 2, 0.0)

    return e_mk, e_mk2, var_mk


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sharpe_ratio_variance(
    sr: float,
    t: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    num_trials: int = 1,
) -> float:
    """Full asymptotic variance of the Sharpe ratio estimator.

    Accounts for non-normality (via skewness gamma_3 and kurtosis gamma_4),
    autocorrelation (rho), and multiple testing (K trials).

    The formula generalizes Lo (2002):

        Var(SR_hat) ~ (1/(T_eff)) * [1 - gamma_3*SR + (gamma_4-1)/4 * SR^2]

    where T_eff = T * (1-rho)/(1+rho) adjusts for first-order autocorrelation,
    and gamma_3, gamma_4 are the skewness and kurtosis of returns.

    For K > 1 trials, the variance of the *maximum* SR across K independent
    tests is returned instead (via the moments of the order statistic).

    Args:
        sr: Observed (annualized) Sharpe ratio.
        t: Number of observations.
        skew: Skewness of returns (gamma_3). Default 0 (symmetric).
        kurtosis: Kurtosis of returns (gamma_4). Default 3 (normal).
            Note: this is *regular* kurtosis, not excess kurtosis.
        autocorr: First-order autocorrelation (rho). Default 0.
        num_trials: Number of independent strategies tested (K). Default 1.

    Returns:
        Variance of the Sharpe ratio estimator.
    """
    if t <= 1:
        return float("inf")

    # Effective sample size (autocorrelation adjustment)
    rho = max(-0.99, min(autocorr, 0.99))
    t_eff = t * (1.0 - rho) / (1.0 + rho)
    t_eff = max(t_eff, 2.0)

    # Single-strategy variance (Lo 2002, extended for non-normality)
    excess_kurt = kurtosis - 3.0
    var_single = (1.0 - skew * sr + (excess_kurt + 2.0) / 4.0 * sr ** 2) / t_eff

    if num_trials <= 1:
        return max(var_single, 0.0)

    # For multiple trials, scale by Var[M_K] / 1 where M_K is max of K normals
    _, _, var_mk = _moments_mk(num_trials, rho=0.0)
    return max(var_single * var_mk, 0.0)


def probabilistic_sharpe_ratio(
    sr: float,
    sr0: float = 0.0,
    *,
    t: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
) -> float:
    """Probabilistic Sharpe Ratio: P(true SR > SR_0).

    PSR = Phi[ (SR_hat - SR_0) / sigma(SR_hat) ]

    where sigma(SR_hat) = sqrt(Var(SR_hat)) from sharpe_ratio_variance().

    Args:
        sr: Observed Sharpe ratio.
        sr0: Benchmark Sharpe ratio to test against. Default 0.
        t: Number of observations.
        skew: Skewness of returns.
        kurtosis: Kurtosis of returns (regular, not excess).
        autocorr: First-order autocorrelation.

    Returns:
        Probability in [0, 1] that the true SR exceeds SR_0.
    """
    var = sharpe_ratio_variance(sr, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr)
    if var <= 0 or math.isinf(var):
        return 1.0 if sr > sr0 else 0.0
    se = math.sqrt(var)
    return float(norm.cdf((sr - sr0) / se))


def minimum_track_record_length(
    sr: float,
    sr0: float = 0.0,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    alpha: float = 0.05,
) -> float:
    """Minimum Track Record Length (MinTRL).

    The minimum number of observations T* needed so that
    PSR(SR, SR_0, T*) >= 1 - alpha.

    MinTRL = [ (z_alpha * sigma_unit) / (SR - SR_0) ]^2

    where sigma_unit^2 = 1 - gamma_3*SR + (gamma_4-1)/4*SR^2 is the
    per-observation variance factor, and z_alpha = Phi_inv(1-alpha).

    Args:
        sr: Observed Sharpe ratio.
        sr0: Benchmark Sharpe ratio.
        skew: Skewness of returns.
        kurtosis: Kurtosis of returns (regular).
        autocorr: First-order autocorrelation.
        alpha: Significance level (default 0.05).

    Returns:
        Minimum number of observations (float). Returns inf if SR <= SR_0.
    """
    if sr <= sr0:
        return float("inf")

    z_alpha = float(norm.ppf(1.0 - alpha))

    excess_kurt = kurtosis - 3.0
    var_unit = 1.0 - skew * sr + (excess_kurt + 2.0) / 4.0 * sr ** 2
    var_unit = max(var_unit, 0.01)

    # Autocorrelation adjustment: need more observations when autocorrelated
    rho = max(-0.99, min(autocorr, 0.99))
    rho_factor = (1.0 + rho) / (1.0 - rho) if abs(1.0 - rho) > 1e-10 else 1.0

    min_trl = (z_alpha ** 2 * var_unit / (sr - sr0) ** 2) * rho_factor
    return max(min_trl, 1.0)


def critical_sharpe_ratio(
    sr0: float,
    t: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    alpha: float = 0.05,
    num_trials: int = 1,
) -> float:
    """Critical Sharpe Ratio -- threshold SR for rejecting H_0: SR <= SR_0.

    SR* = SR_0 + z_alpha * sigma(SR_hat)

    When num_trials > 1, the expected maximum SR under the null is used
    as the benchmark instead of SR_0.

    Args:
        sr0: Null hypothesis Sharpe ratio.
        t: Number of observations.
        skew: Skewness of returns.
        kurtosis: Kurtosis of returns (regular).
        autocorr: First-order autocorrelation.
        alpha: Significance level.
        num_trials: Number of strategies tested.

    Returns:
        Critical SR value.
    """
    z_alpha = float(norm.ppf(1.0 - alpha))

    # Use sr0 as a reasonable estimate for the variance calculation
    var = sharpe_ratio_variance(sr0, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr)
    se = math.sqrt(max(var, 0.0))

    if num_trials <= 1:
        return sr0 + z_alpha * se
    else:
        e_max = expected_maximum_sharpe_ratio(num_trials, var, sr0)
        return e_max + z_alpha * se


def sharpe_ratio_power(
    sr0: float,
    sr1: float,
    t: int,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    alpha: float = 0.05,
    num_trials: int = 1,
) -> float:
    """Statistical power: P(reject H_0 | true SR = SR_1).

    Power = Phi[ (SR_1 - SR*) / sigma(SR_hat) ]

    where SR* is the critical Sharpe ratio.

    Args:
        sr0: Null hypothesis SR.
        sr1: True (alternative) SR.
        t: Number of observations.
        skew: Skewness.
        kurtosis: Kurtosis (regular).
        autocorr: Autocorrelation.
        alpha: Significance level.
        num_trials: Number of strategies tested.

    Returns:
        Power in [0, 1].
    """
    sr_crit = critical_sharpe_ratio(
        sr0, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr,
        alpha=alpha, num_trials=num_trials,
    )

    # Variance under the alternative (SR = SR_1)
    var = sharpe_ratio_variance(sr1, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr)
    if var <= 0:
        return 1.0 if sr1 > sr_crit else 0.0
    se = math.sqrt(var)

    return float(norm.cdf((sr1 - sr_crit) / se))


def posterior_fdr(p_h1: float, alpha: float, beta: float) -> float:
    """Posterior False Discovery Rate (pFDR).

    pFDR = P(H_0 | reject H_0)
         = (1 - p_H1) * alpha / [(1 - p_H1) * alpha + p_H1 * (1 - beta)]

    Args:
        p_h1: Prior probability that H_1 is true.
        alpha: Type I error rate (significance level).
        beta: Type II error rate (1 - power).

    Returns:
        pFDR in [0, 1].
    """
    p_h0 = 1.0 - p_h1
    numerator = p_h0 * alpha
    denominator = p_h0 * alpha + p_h1 * (1.0 - beta)
    if denominator <= 0:
        return 0.0
    return min(max(numerator / denominator, 0.0), 1.0)


def observed_fdr(
    sr: float,
    sr0: float,
    sr1: float,
    t: int,
    p_h1: float,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    num_trials: int = 1,
) -> float:
    """Observed False Discovery Rate (oFDR).

    Computes the posterior FDR using the observed SR to derive
    the implied significance level and power.

    Args:
        sr: Observed Sharpe ratio.
        sr0: Null hypothesis SR.
        sr1: Alternative hypothesis SR.
        t: Number of observations.
        p_h1: Prior probability that H_1 is true.
        skew: Skewness.
        kurtosis: Kurtosis (regular).
        autocorr: Autocorrelation.
        num_trials: Number of strategies tested.

    Returns:
        oFDR in [0, 1].
    """
    # Implied alpha: P(SR_hat >= observed | H_0: true SR = SR_0)
    var0 = sharpe_ratio_variance(sr0, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr)
    if var0 <= 0:
        return 0.0
    se0 = math.sqrt(var0)
    alpha_obs = 1.0 - float(norm.cdf((sr - sr0) / se0))

    # Implied beta: P(SR_hat < observed | H_1: true SR = SR_1)
    var1 = sharpe_ratio_variance(sr1, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr)
    if var1 <= 0:
        return 0.0
    se1 = math.sqrt(var1)
    beta_obs = float(norm.cdf((sr - sr1) / se1))

    return posterior_fdr(p_h1, alpha_obs, beta_obs)


def control_for_fdr(
    q: float,
    *,
    sr0: float = 0.0,
    sr1: float = 0.5,
    p_h1: float = 0.05,
    t: int = 24,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    autocorr: float = 0.0,
    num_trials: int = 1,
) -> tuple[float, float, float]:
    """Find the critical SR that controls the FDR at level q.

    Searches for the alpha level such that pFDR <= q, then returns
    the corresponding critical SR, alpha, and power.

    Args:
        q: Target FDR level (e.g. 0.05 for 5%).
        sr0: Null SR.
        sr1: Alternative SR.
        p_h1: Prior probability that H_1 is true.
        t: Number of observations.
        skew: Skewness.
        kurtosis: Kurtosis (regular).
        autocorr: Autocorrelation.
        num_trials: Number of strategies tested.

    Returns:
        (critical_sr, alpha, power) tuple.
    """
    # Solve for alpha: pFDR(p_h1, alpha, beta(alpha)) = q
    # Use bisection on alpha in (0, 0.5)
    lo, hi = 1e-8, 0.5
    best_alpha = lo

    for _ in range(100):  # bisection iterations
        mid = (lo + hi) / 2.0
        critical_sharpe_ratio(
            sr0, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr,
            alpha=mid, num_trials=num_trials,
        )
        power = sharpe_ratio_power(
            sr0, sr1, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr,
            alpha=mid, num_trials=num_trials,
        )
        beta = 1.0 - power
        fdr = posterior_fdr(p_h1, mid, beta)

        if fdr <= q:
            best_alpha = mid
            lo = mid
        else:
            hi = mid

    # Final values at best_alpha
    final_sr = critical_sharpe_ratio(
        sr0, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr,
        alpha=best_alpha, num_trials=num_trials,
    )
    final_power = sharpe_ratio_power(
        sr0, sr1, t, skew=skew, kurtosis=kurtosis, autocorr=autocorr,
        alpha=best_alpha, num_trials=num_trials,
    )
    return final_sr, best_alpha, final_power


# ---------------------------------------------------------------------------
# Multiple testing corrections (FWER)
# ---------------------------------------------------------------------------

def adjusted_p_values_bonferroni(p_values: np.ndarray) -> np.ndarray:
    """Bonferroni correction: p_adj = min(p * K, 1).

    Args:
        p_values: Array of raw p-values.

    Returns:
        Array of adjusted p-values.
    """
    p = np.asarray(p_values, dtype=float)
    k = len(p)
    if k == 0:
        return p
    return np.minimum(p * k, 1.0)


def adjusted_p_values_sidak(p_values: np.ndarray) -> np.ndarray:
    """Sidak correction: p_adj = 1 - (1 - p)^K.

    Slightly less conservative than Bonferroni for independent tests.

    Args:
        p_values: Array of raw p-values.

    Returns:
        Array of adjusted p-values.
    """
    p = np.asarray(p_values, dtype=float)
    k = len(p)
    if k == 0:
        return p
    return 1.0 - (1.0 - p) ** k


def adjusted_p_values_holm(
    p_values: np.ndarray,
    *,
    variant: str = "bonferroni",
) -> np.ndarray:
    """Holm step-down procedure.

    Sort p-values ascending, apply correction with decreasing multiplier.
    Variant controls the per-step correction:
        "bonferroni": p_adj[i] = p[i] * (K - i)
        "sidak": p_adj[i] = 1 - (1 - p[i])^(K - i)

    Args:
        p_values: Array of raw p-values.
        variant: "bonferroni" (default) or "sidak".

    Returns:
        Array of adjusted p-values (in original order).
    """
    p = np.asarray(p_values, dtype=float)
    k = len(p)
    if k == 0:
        return p

    order = np.argsort(p)
    sorted_p = p[order]

    adjusted = np.empty(k)
    for i in range(k):
        m = k - i  # decreasing multiplier
        if variant == "sidak":
            adjusted[i] = 1.0 - (1.0 - sorted_p[i]) ** m
        else:
            adjusted[i] = sorted_p[i] * m

    # Enforce monotonicity (step-down: each adjusted p >= previous)
    for i in range(1, k):
        adjusted[i] = max(adjusted[i], adjusted[i - 1])
    adjusted = np.minimum(adjusted, 1.0)

    # Restore original order
    result = np.empty(k)
    result[order] = adjusted
    return result


# ---------------------------------------------------------------------------
# Expected maximum Sharpe ratio
# ---------------------------------------------------------------------------

def expected_maximum_sharpe_ratio(
    num_trials: int,
    variance: float,
    sr0: float = 0.0,
) -> float:
    """Expected maximum Sharpe ratio under the null.

    E[max(SR_hat_1, ..., SR_hat_K)] = SR_0 + sqrt(V) * E[max(Z_1, ..., Z_K)]

    where Z_i are standard normal and V is the variance of a single SR_hat.

    This is a strict improvement over the simple sqrt(2*ln(K)) approximation
    (which is the asymptotic limit for large K and ignores the SR_0 offset
    and the exact small-K correction).

    Args:
        num_trials: Number of independent strategies (K).
        variance: Variance of a single SR estimator.
        sr0: Null hypothesis SR (default 0).

    Returns:
        Expected maximum SR.
    """
    if num_trials <= 0:
        return sr0
    if num_trials == 1:
        return sr0

    e_mk, _, _ = _moments_mk(num_trials, rho=0.0)
    return sr0 + math.sqrt(max(variance, 0.0)) * e_mk
