"""
Stage Analysis (Stan Weinstein, modernised).

  Stage 1 — Basing.   Sideways action below or hugging the 30-week MA.
                      Volatility contraction. Accumulation.
  Stage 2 — Advance.  Price above rising 30wk MA. Higher highs. Volume on rallies.
                      THIS IS THE ONLY STAGE TO BUY.
  Stage 3 — Topping.  Sideways above the now-flattening 30wk MA. Volume on
                      declines exceeds rallies. Distribution.
  Stage 4 — Decline.  Price below falling 30wk MA. Lower lows. THE 'NO TOUCH' ZONE.

Daily bars but the 30-week MA = 150-day MA (approx).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _slope(s: pd.Series, n: int = 20) -> pd.Series:
    """% change of a series over n bars, smoothed."""
    return (s - s.shift(n)) / s.shift(n) * 100


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add stage classification columns to a price DataFrame."""
    if df.empty or len(df) < 200:
        return df

    out = df.copy()
    c = out["close"]

    # Moving averages (Weinstein original: 30wk SMA, here in daily ≈ 150 days)
    out["ma30w"] = c.rolling(150).mean()
    out["ma10w"] = c.rolling(50).mean()    # 10-week ≈ 50d
    out["ma40w"] = c.rolling(200).mean()   # confirmation

    # Slope of the 30wk MA — flat / rising / falling
    out["ma30w_slope"] = _slope(out["ma30w"], 20)
    # Position of price relative to 30wk MA (% above/below)
    out["pct_to_ma30w"] = (c - out["ma30w"]) / out["ma30w"] * 100

    # 52-week high/low context
    out["52w_high"] = c.rolling(252).max()
    out["52w_low"] = c.rolling(252).min()
    out["pct_from_52w_high"] = (c - out["52w_high"]) / out["52w_high"] * 100

    # Volume regime
    out["vol_avg_50"] = out["volume"].rolling(50).mean()
    out["vol_ratio"] = out["volume"] / out["vol_avg_50"]

    # Volatility — ATR%
    high_low = out["high"] - out["low"]
    high_close = (out["high"] - out["close"].shift()).abs()
    low_close = (out["low"] - out["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    out["atr14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    out["atr_pct"] = out["atr14"] / c * 100

    # ----- Stage classification -----
    above_ma30 = c > out["ma30w"]
    rising_ma30 = out["ma30w_slope"] > 0.5         # > 0.5%/20d
    flat_ma30 = out["ma30w_slope"].abs() <= 0.5
    falling_ma30 = out["ma30w_slope"] < -0.5

    near_52w_high = out["pct_from_52w_high"] > -15  # within 15% of 52w high
    near_52w_low = out["pct_from_52w_high"] < -50   # >50% off the 52w high

    stage = pd.Series(index=out.index, dtype=object)

    stage[above_ma30 & rising_ma30] = "STAGE 2"
    stage[above_ma30 & flat_ma30] = "STAGE 3"
    stage[~above_ma30 & flat_ma30] = "STAGE 1"
    stage[~above_ma30 & falling_ma30] = "STAGE 4"
    # Fill remaining ambiguous bars by carrying forward
    stage = stage.ffill().fillna("STAGE 1")

    out["stage"] = stage
    return out


def stage_label(stage: str) -> str:
    return {
        "STAGE 1": "🟡 Stage 1 (Basing)",
        "STAGE 2": "🟢 Stage 2 (Advancing)",
        "STAGE 3": "🟠 Stage 3 (Topping)",
        "STAGE 4": "🔴 Stage 4 (Declining)",
    }.get(stage, stage)


def stage_color(stage: str) -> str:
    return {
        "STAGE 1": "#FFD700",
        "STAGE 2": "#22C55E",
        "STAGE 3": "#FF8C00",
        "STAGE 4": "#EF4444",
    }.get(stage, "#8a93a6")


def stage_action(stage: str) -> str:
    return {
        "STAGE 1": "Watch for breakout. Don't anticipate.",
        "STAGE 2": "ELIGIBLE TO BUY. Pullbacks to 10wk MA are entries.",
        "STAGE 3": "TIGHTEN STOPS. Reduce size. Don't add.",
        "STAGE 4": "DO NOT TOUCH. Or short, if your system supports.",
    }.get(stage, "")
