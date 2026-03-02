"""Shared utilities for building standardized IV surfaces from options chains.

Used by Yahoo, Bloomberg, and IB provider implementations to avoid
duplicating surface-building logic. Each provider fetches raw chain data
in its own format, then delegates to these helpers for standardization.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


def time_to_expiry_years(expiration_date: str) -> float:
    """Convert ISO date string to fractional years until expiry.

    Args:
        expiration_date: ISO format date string (e.g. "2026-06-19")

    Returns:
        Fractional years to expiry (minimum 1/365 to avoid division by zero).
    """
    exp = date.fromisoformat(expiration_date)
    today = date.today()
    days = (exp - today).days
    return max(days / 365.0, 1.0 / 365.0)


def find_atm_strike_idx(strikes: list[float], spot: float) -> int:
    """Return index of the strike nearest to spot price.

    Args:
        strikes: Sorted list of strike prices.
        spot: Current spot price.

    Returns:
        Index into strikes of the nearest-to-ATM strike.
    """
    if not strikes:
        return 0
    diffs = [abs(k - spot) for k in strikes]
    return diffs.index(min(diffs))


def compute_skew_metrics(
    iv_row: list[float | None],
    strikes: list[float],
    spot: float,
) -> dict[str, float | None]:
    """Compute skew metrics for a single-maturity IV row.

    Extracts put-wing, ATM, and call-wing IVs, then computes
    25-delta skew approximation (put_wing - call_wing).

    Args:
        iv_row: Implied vols aligned with strikes (None for missing).
        strikes: Strike prices.
        spot: Current spot price.

    Returns:
        Dict with put_wing, atm, call_wing, skew_25d (all in % terms).
    """
    if not strikes or not iv_row:
        return {"put_wing": None, "atm": None, "call_wing": None, "skew_25d": None}

    atm_idx = find_atm_strike_idx(strikes, spot)
    n = len(strikes)

    # Put wing: ~25-delta put (roughly 85-90% of spot)
    put_target = spot * 0.90
    put_idx = find_atm_strike_idx(strikes, put_target)

    # Call wing: ~25-delta call (roughly 110-115% of spot)
    call_target = spot * 1.10
    call_idx = find_atm_strike_idx(strikes, call_target)

    def _safe_iv(idx: int) -> float | None:
        if 0 <= idx < len(iv_row):
            return iv_row[idx]
        return None

    put_iv = _safe_iv(put_idx)
    atm_iv = _safe_iv(atm_idx)
    call_iv = _safe_iv(call_idx)

    skew_25d = None
    if put_iv is not None and call_iv is not None:
        skew_25d = round(put_iv - call_iv, 2)

    return {
        "put_wing": round(put_iv, 2) if put_iv is not None else None,
        "atm": round(atm_iv, 2) if atm_iv is not None else None,
        "call_wing": round(call_iv, 2) if call_iv is not None else None,
        "skew_25d": skew_25d,
    }


def assess_chain_liquidity(chain: dict[str, Any]) -> dict[str, Any]:
    """Assess liquidity quality of an options chain.

    Args:
        chain: Standardized chain dict with 'calls' and 'puts' lists.

    Returns:
        Dict with coverage_pct, avg_volume, total_oi, illiquid flag.
    """
    contracts = (chain.get("calls") or []) + (chain.get("puts") or [])
    if not contracts:
        return {
            "coverage_pct": 0.0,
            "avg_volume": 0,
            "total_oi": 0,
            "illiquid": True,
        }

    has_iv = sum(1 for c in contracts if c.get("implied_vol") is not None and c["implied_vol"] > 0)
    coverage = (has_iv / len(contracts)) * 100 if contracts else 0

    volumes = [c.get("volume") or 0 for c in contracts]
    avg_vol = sum(volumes) / len(volumes) if volumes else 0

    total_oi = sum(c.get("open_interest") or 0 for c in contracts)

    return {
        "coverage_pct": round(coverage, 1),
        "avg_volume": round(avg_vol, 1),
        "total_oi": total_oi,
        "illiquid": coverage < 30 or avg_vol < 5,
    }


def build_iv_surface_from_chains(
    ticker: str,
    provider_name: str,
    spot: float,
    chains: list[dict[str, Any]],
    num_strikes: int = 15,
) -> dict[str, Any] | None:
    """Build a standardized IV surface dict from a list of chain dicts.

    Aggregates multiple expiration chains into the surface schema that
    MAIC's vol intelligence pipeline expects.

    Args:
        ticker: Stock ticker.
        provider_name: Data provider name (for labeling).
        spot: Current spot price.
        chains: List of standardized chain dicts (from get_options_chain).
        num_strikes: Number of strikes to include per expiration.

    Returns:
        Standardized surface dict, or None if insufficient data.
    """
    if not chains or spot <= 0:
        return None

    iv_surface_pct: dict[str, dict[str, float]] = {}
    atm_term_structure: dict[str, float] = {}
    skew_by_maturity: dict[str, dict[str, float | None]] = {}
    quality_scores: list[dict[str, Any]] = []

    for chain in chains:
        exp = chain.get("expiration")
        if not exp:
            continue

        tte = time_to_expiry_years(exp)
        maturity_label = f"{tte:.3f}y"

        # Merge calls and puts for IV data; prefer puts for OTM puts, calls for OTM calls
        calls = chain.get("calls") or []
        puts = chain.get("puts") or []

        # Build strike -> IV mapping
        strike_iv: dict[float, float] = {}
        for c in calls:
            strike = c.get("strike")
            iv = c.get("implied_vol")
            if strike is not None and iv is not None and iv > 0:
                # Use call IV for ATM and OTM calls (strike >= spot)
                if strike >= spot:
                    strike_iv[strike] = iv

        for p in puts:
            strike = p.get("strike")
            iv = p.get("implied_vol")
            if strike is not None and iv is not None and iv > 0:
                # Use put IV for OTM puts (strike < spot)
                if strike < spot:
                    strike_iv[strike] = iv
                # Fill in ATM from puts if calls didn't have it
                elif strike not in strike_iv:
                    strike_iv[strike] = iv

        if not strike_iv:
            continue

        # Sort strikes and limit to num_strikes centered around ATM
        sorted_strikes = sorted(strike_iv.keys())
        atm_idx = find_atm_strike_idx(sorted_strikes, spot)
        half = num_strikes // 2
        start = max(0, atm_idx - half)
        end = min(len(sorted_strikes), start + num_strikes)
        start = max(0, end - num_strikes)
        selected_strikes = sorted_strikes[start:end]

        # Build IV row and surface entry
        iv_row: list[float | None] = []
        for k in selected_strikes:
            iv_val = strike_iv.get(k)
            iv_row.append(iv_val)
            if iv_val is not None:
                strike_pct = f"{(k / spot) * 100:.0f}%"
                if maturity_label not in iv_surface_pct:
                    iv_surface_pct[maturity_label] = {}
                iv_surface_pct[maturity_label][strike_pct] = round(iv_val, 2)

        # ATM term structure
        atm_iv_val = strike_iv.get(
            selected_strikes[find_atm_strike_idx(selected_strikes, spot)]
        )
        if atm_iv_val is not None:
            atm_term_structure[maturity_label] = round(atm_iv_val, 2)

        # Skew metrics
        skew = compute_skew_metrics(iv_row, list(selected_strikes), spot)
        skew_by_maturity[maturity_label] = skew

        # Chain liquidity
        quality_scores.append(assess_chain_liquidity(chain))

    if not atm_term_structure:
        return None

    # Aggregate quality
    avg_coverage = (
        sum(q["coverage_pct"] for q in quality_scores) / len(quality_scores)
        if quality_scores
        else 0
    )
    avg_volume = (
        sum(q["avg_volume"] for q in quality_scores) / len(quality_scores)
        if quality_scores
        else 0
    )

    # Term structure direction
    sorted_maturities = sorted(atm_term_structure.keys())
    if len(sorted_maturities) >= 2:
        first_iv = atm_term_structure[sorted_maturities[0]]
        last_iv = atm_term_structure[sorted_maturities[-1]]
        if last_iv > first_iv + 1:
            term_structure = "contango"
        elif last_iv < first_iv - 1:
            term_structure = "backwardation"
        else:
            term_structure = "flat"
    else:
        term_structure = "insufficient_data"

    # Average skew
    skew_vals = [
        s["skew_25d"]
        for s in skew_by_maturity.values()
        if s.get("skew_25d") is not None
    ]
    avg_skew = round(sum(skew_vals) / len(skew_vals), 2) if skew_vals else None

    # Build interpretation
    interp_parts = [f"Market IV surface for {ticker} from {provider_name}."]
    if avg_skew is not None:
        interp_parts.append(f"Avg 25d skew: {avg_skew:.1f}pp.")
    interp_parts.append(f"Term structure: {term_structure}.")
    if avg_coverage < 50:
        interp_parts.append("Caution: limited IV coverage — surface may be noisy.")

    return {
        "iv_surface_pct": iv_surface_pct,
        "atm_term_structure": atm_term_structure,
        "skew_by_maturity": skew_by_maturity,
        "summary": {
            "avg_skew_25d": avg_skew,
            "term_structure": term_structure,
            "interpretation": " ".join(interp_parts),
        },
        "data_quality": {
            "coverage_pct": round(avg_coverage, 1),
            "avg_volume": round(avg_volume, 1),
            "num_expirations": len(atm_term_structure),
        },
        "provider": provider_name,
    }
