"""
Valuation Engine.
  * Simplified DCF (terminal value + 5y FCF projection)
  * Peer multiple comparison (P/E, P/S, EV/EBITDA vs sector median)
  * Historical multiple regression (current vs 5-year avg)
  * Composite "fair value" range with under/over-valued verdict
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class FairValue:
    low: float
    mid: float
    high: float
    current: float
    verdict: str        # UNDERVALUED / FAIR / OVERVALUED
    upside_pct: float
    method_breakdown: dict


def simple_dcf(fcf_ttm: float, growth_yr1_5: float = 0.10,
               terminal_growth: float = 0.025, discount_rate: float = 0.10,
               shares: float | None = None) -> dict:
    """
    Two-stage DCF.
    fcf_ttm: trailing free cash flow in dollars.
    growth_yr1_5: assumed CAGR for years 1-5.
    terminal_growth: perpetual growth after year 5.
    discount_rate: WACC proxy.
    Returns equity value (and per-share if shares supplied).
    """
    if not fcf_ttm or fcf_ttm <= 0:
        return {}

    fcfs = [fcf_ttm * (1 + growth_yr1_5) ** y for y in range(1, 6)]
    pv_fcfs = sum(f / (1 + discount_rate) ** y for y, f in enumerate(fcfs, 1))

    # Terminal value (Gordon)
    tv = fcfs[-1] * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_tv = tv / (1 + discount_rate) ** 5

    enterprise = pv_fcfs + pv_tv
    out = {
        "enterprise_value": enterprise,
        "pv_fcfs": pv_fcfs,
        "pv_terminal": pv_tv,
        "assumptions": {
            "growth_5y_cagr": growth_yr1_5,
            "terminal_growth": terminal_growth,
            "discount_rate":  discount_rate,
        },
    }
    if shares and shares > 0:
        out["per_share"] = enterprise / shares
    return out


def peer_multiple_estimate(pe: float | None, ps: float | None,
                           sector_pe_median: float | None, sector_ps_median: float | None,
                           current_eps: float | None, current_sales: float | None,
                           shares: float | None = None) -> dict:
    """Per-share fair value using sector-median multiples."""
    out = {}
    if pe and sector_pe_median and current_eps:
        out["pe_fair"] = sector_pe_median * current_eps
    if ps and sector_ps_median and current_sales and shares:
        out["ps_fair"] = sector_ps_median * (current_sales / shares)
    return out


def historical_multiple_estimate(current_pe: float | None,
                                 historical_avg_pe: float | None,
                                 current_eps: float | None) -> dict:
    """Reverts current P/E to its 5-year average (Lynch's earnings-line method)."""
    if not (current_pe and historical_avg_pe and current_eps):
        return {}
    return {
        "historical_pe_fair": historical_avg_pe * current_eps,
        "current_pe": current_pe,
        "5y_avg_pe": historical_avg_pe,
        "premium_pct": (current_pe / historical_avg_pe - 1) * 100,
    }


def fair_value_consensus(estimates: dict[str, float], current_price: float) -> FairValue:
    """
    Average multiple methods → fair value range.
    estimates: e.g. {'dcf': 150.0, 'pe_fair': 145.0, 'ps_fair': 140.0, 'historical_pe_fair': 155.0}
    """
    vals = [v for v in estimates.values() if v and v > 0]
    if not vals or not current_price:
        return FairValue(0, 0, 0, current_price, "UNKNOWN", 0, estimates)

    arr = np.array(vals)
    low = float(np.percentile(arr, 25))
    mid = float(np.median(arr))
    high = float(np.percentile(arr, 75))

    upside = (mid - current_price) / current_price * 100

    if current_price < low:
        verdict = "UNDERVALUED"
    elif current_price > high:
        verdict = "OVERVALUED"
    else:
        verdict = "FAIR"

    return FairValue(low=low, mid=mid, high=high, current=current_price,
                     verdict=verdict, upside_pct=upside,
                     method_breakdown=estimates)


def verdict_color(verdict: str) -> str:
    return {"UNDERVALUED": "#22C55E", "FAIR": "#FFD700",
            "OVERVALUED": "#EF4444", "UNKNOWN": "#8a93a6"}.get(verdict, "#8a93a6")
