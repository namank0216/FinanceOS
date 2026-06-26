"""
Macro Regime classifier — drives the Leverage Gate.

Inputs (FRED, via no-key public CSV):
  * VIX                — fear / volatility regime
  * 10Y-2Y spread      — recession risk; inverted = elevated risk
  * HY credit OAS      — risk appetite in fixed income
  * SPY 50d/200d       — broad trend (calculated from yfinance data)
  * Breadth            — % of S&P 500 above 50dma (estimated)

Output: Risk regime ∈ {RISK_ON, NEUTRAL, RISK_OFF}
        Leverage gate ∈ {GREEN (full 3x), YELLOW (half / 1x preferred), RED (no leverage)}
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import data


@dataclass
class MacroState:
    regime: str          # RISK_ON / NEUTRAL / RISK_OFF
    leverage_gate: str   # GREEN / YELLOW / RED
    components: dict
    summary: str


def _color_gate(gate: str) -> str:
    return {"GREEN": "#22C55E", "YELLOW": "#FF8C00", "RED": "#EF4444"}.get(gate, "#8a93a6")


def assess() -> MacroState:
    components: dict = {}
    flags = {"vix": 0, "curve": 0, "credit": 0, "trend": 0}

    # ----- VIX -----
    vix = data.fred_series("VIXCLS", days=30)
    if not vix.empty:
        cur = float(vix.iloc[-1]["value"])
        components["vix"] = round(cur, 2)
        if cur < 15:
            flags["vix"] = 1
        elif cur < 22:
            flags["vix"] = 0
        elif cur < 30:
            flags["vix"] = -1
        else:
            flags["vix"] = -2

    # ----- 10Y-2Y curve -----
    curve = data.fred_series("T10Y2Y", days=30)
    if not curve.empty:
        cur = float(curve.iloc[-1]["value"])
        components["10y_2y_spread"] = round(cur, 2)
        if cur > 0.5:
            flags["curve"] = 1
        elif cur > 0:
            flags["curve"] = 0
        elif cur > -0.5:
            flags["curve"] = -1
        else:
            flags["curve"] = -2

    # ----- HY credit (lower spread = more risk-on) -----
    hy = data.fred_series("BAMLH0A0HYM2", days=60)
    if not hy.empty:
        cur = float(hy.iloc[-1]["value"])
        recent = hy.tail(20)["value"].mean()
        components["hy_oas"] = round(cur, 2)
        components["hy_oas_20d_avg"] = round(recent, 2)
        # Tighter than 350bps = risk on, wider than 600 = risk off
        if cur < 3.5:
            flags["credit"] = 1
        elif cur < 5.0:
            flags["credit"] = 0
        elif cur < 7.0:
            flags["credit"] = -1
        else:
            flags["credit"] = -2

    # ----- SPY trend -----
    spy = data.get_history("SPY", period="1y")
    if not spy.empty and len(spy) > 200:
        c = spy["close"]
        ma50 = c.rolling(50).mean().iloc[-1]
        ma200 = c.rolling(200).mean().iloc[-1]
        cur = float(c.iloc[-1])
        components["spy_close"] = round(cur, 2)
        components["spy_ma50"] = round(ma50, 2)
        components["spy_ma200"] = round(ma200, 2)
        if cur > ma50 > ma200:
            flags["trend"] = 1
        elif cur > ma200:
            flags["trend"] = 0
        elif cur > ma50:
            flags["trend"] = 0
        else:
            flags["trend"] = -1

    # ----- Aggregate -----
    score = sum(flags.values())
    components["flags"] = flags
    components["score"] = score

    if score >= 3:
        regime, gate = "RISK_ON", "GREEN"
        summary = ("All systems go. Volatility is muted, the curve is healthy, credit is risk-on, "
                   "and the broad market is in a bullish stack. Leveraged ETFs are eligible at full size.")
    elif score >= 1:
        regime, gate = "RISK_ON", "GREEN"
        summary = ("Constructive but not perfect. 3× products are usable but lean toward the higher-quality "
                   "underlyings (TQQQ over LABU, etc.). Watch for any flag turning negative.")
    elif score >= -1:
        regime, gate = "NEUTRAL", "YELLOW"
        summary = ("Mixed signals. Reduce 3× exposure to half-size, prefer 1× ETFs (QQQ, SPY, SOXX) for new "
                   "entries until the picture clarifies. Existing 3× positions: tighten stops.")
    elif score >= -3:
        regime, gate = "RISK_OFF", "RED"
        summary = ("Risk-off conditions. Avoid new 3× longs entirely. Consider inverse leveraged ETFs (SQQQ, SOXS) "
                   "for hedging or short-side plays only with strict stops. Cash is a position.")
    else:
        regime, gate = "RISK_OFF", "RED"
        summary = ("Severe risk-off. The historical playbook says capital preservation, not opportunism. "
                   "If holding leveraged exposure, exit. Cash is the highest-conviction position.")

    return MacroState(regime=regime, leverage_gate=gate, components=components, summary=summary)
