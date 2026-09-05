"""
lib/funnel.py — the 4-step selection funnel (Pond → Fish → Focus → Review).

Named "Funnel steps" deliberately: the app already uses "Stage 1-4" for
Weinstein stage analysis (lib/stages.py). Don't conflate them.

  F1 POND    mechanical screen, zero judgment  (~universe → ~20)
  F2 FISH    score + rank + correlation kill   (~20 → ~5)
  F3 FOCUS   three written questions + sizing  (~5 → 1-2)
  F4 REVIEW  re-check gates on each earnings   (hold / exit)

Every gate carries its evidence source in GATES[...]["evidence"]. These are
citations to the literature, not statistics remembered by an LLM. The app
does not (yet) re-derive these factor premia itself; if you want that, the
honest next step is a factor backtest on the same universe (see TODO).

Data: yfinance (price, quarterly statements, info), FMP analyst estimates
if FMP_API_KEY is set (revisions gate), existing lib.screener for price gates.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from . import data, screener
try:
    from . import model_panel as mp
except Exception:  # optional
    mp = None

THESIS_FILE = Path(__file__).parent.parent / ".cache" / "funnel_theses.json"

GATES = {
    "regime": {
        "label": "Regime: S&P 500 above rising 200-day MA",
        "evidence": "Faber (2007) 'A Quantitative Approach to Tactical Asset Allocation'; "
                    "Moskowitz, Ooi & Pedersen (2012) 'Time Series Momentum'. Trend filters cut drawdowns; "
                    "breakouts fail far more often in index downtrends.",
    },
    "trend": {
        "label": "Trend: Weinstein Stage 2 (price > rising 30-wk MA), within 20% of 52-wk high",
        "evidence": "Weinstein (1988); George & Hwang (2004) '52-Week High and Momentum Investing' — proximity to the "
                    "52-week high predicts returns via anchoring/underreaction.",
    },
    "rs": {
        "label": "Relative strength: 12-1 month momentum positive and above benchmark",
        "evidence": "Jegadeesh & Titman (1993); Asness, Moskowitz & Pedersen (2013) 'Value and Momentum Everywhere' — "
                    "momentum premium ~1%/month historically, replicated across markets and a century of data.",
    },
    "accel": {
        "label": "Fundamental fuel: revenue growth ACCELERATING with gross margin EXPANDING",
        "evidence": "Chan, Jegadeesh & Lakonishok (1996) 'Momentum Strategies' — earnings momentum drives price momentum; "
                    "Novy-Marx (2013) gross profitability. Acceleration + margin expansion = operating leverage inflection.",
    },
    "revisions": {
        "label": "Analysts chasing: estimates revised up / recent beats",
        "evidence": "Post-earnings-announcement drift (Ball & Brown 1968; Bernard & Thomas 1989). Markets underreact "
                    "to large beats and upward revisions for months.",
    },
    "quality": {
        "label": "Quality: gross profitability (GP/assets) high, ROIC > 15%, FCF positive",
        "evidence": "Novy-Marx (2013) 'The Other Side of Value: The Gross Profitability Premium'; Asness, Frazzini & Pedersen "
                    "(2019) 'Quality Minus Junk'. Quality predicts returns mainly through future earnings growth.",
    },
    "dilution": {
        "label": "Per-share discipline: share count not growing > 3%/yr; revenue & FCF growing PER SHARE",
        "evidence": "Pontiff & Woodgate (2008) 'Share Issuance and Cross-Sectional Returns' — net issuers underperform; "
                    "Research Affiliates on long-run revenue-per-share growth. A company can triple while owners get nothing.",
    },
    "incremental": {
        "label": "Incremental economics: operating leverage (Δ operating income / Δ revenue) rising",
        "evidence": "Practitioner (Mayer '100 Baggers', Phelps) + operating-leverage literature — the return on the NEXT dollar "
                    "invested matters more than historical ROIC.",
    },
    "crash_risk": {
        "label": "Known failure mode: momentum crashes at regime turns",
        "evidence": "Daniel & Moskowitz (2016) 'Momentum Crashes' — momentum portfolios lost >70% in 2009's reversal. "
                    "The regime gate + stops exist to survive this.",
    },
    "base_rate": {
        "label": "Base rate: only ~4% of stocks create the market's net wealth",
        "evidence": "Bessembinder (2018) 'Do Stocks Outperform Treasury Bills?' — the screen finds a pond, not the fish; "
                    "sizing and stops carry half the load.",
    },
}


# ============================================================
# F1 — POND: fundamentals per ticker (yfinance quarterly statements)
# ============================================================
def _row(df: pd.DataFrame, names: tuple[str, ...]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            return df.loc[n].dropna()
    return None


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fundamentals(ticker: str) -> dict:
    """Revenue acceleration + gross-margin delta + (optional) revisions. Never raises."""
    out = {"ticker": ticker, "rev_g_now": np.nan, "rev_g_prev": np.nan, "accel_pp": np.nan,
           "gm_now": np.nan, "gm_prev": np.nan, "gm_delta_pp": np.nan,
           "surprise_avg": np.nan, "rev_up_pct": np.nan, "accel_ok": False, "margin_ok": False, "rev_ok": None,
           "gp_assets": np.nan, "roic_pct": np.nan, "fcf_ttm": np.nan, "quality_ok": False,
           "share_growth_pct": np.nan, "rev_ps_growth_pct": np.nan, "dilution_ok": None,
           "incr_margin_pct": np.nan, "incremental_ok": None}
    fin = data.get_financials(ticker)
    qi = fin.get("income_q") if fin else None
    rev = _row(qi, ("Total Revenue", "Operating Revenue"))
    gp = _row(qi, ("Gross Profit",))
    opi = _row(qi, ("Operating Income", "EBIT"))
    # ---- quality / dilution / incremental (annual statements + info)
    try:
        ia = fin.get("income") if fin else None
        ba = fin.get("balance") if fin else None
        ca = fin.get("cashflow") if fin else None
        gp_a = _row(ia, ("Gross Profit",)); ta = _row(ba, ("Total Assets",))
        if gp_a is not None and ta is not None and len(gp_a) and len(ta):
            out["gp_assets"] = round(float(gp_a.iloc[0] / ta.iloc[0]), 2)
        ebit = _row(ia, ("EBIT", "Operating Income")); tax = _row(ia, ("Tax Rate For Calcs",))
        debt = _row(ba, ("Total Debt",)); eq = _row(ba, ("Stockholders Equity", "Total Equity Gross Minority Interest"))
        cash = _row(ba, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"))
        if ebit is not None and eq is not None and len(ebit) and len(eq):
            t = float(tax.iloc[0]) if tax is not None and len(tax) else 0.21
            ic = float(eq.iloc[0]) + (float(debt.iloc[0]) if debt is not None and len(debt) else 0.0) - (float(cash.iloc[0]) if cash is not None and len(cash) else 0.0)
            if ic > 0:
                out["roic_pct"] = round(float(ebit.iloc[0]) * (1 - t) / ic * 100, 1)
        fcf = _row(ca, ("Free Cash Flow",))
        if fcf is not None and len(fcf):
            out["fcf_ttm"] = float(fcf.iloc[0])
        out["quality_ok"] = bool((out["gp_assets"] >= 0.25 if not np.isnan(out["gp_assets"]) else False) and
                                 (out["roic_pct"] >= 15 if not np.isnan(out["roic_pct"]) else True) and
                                 (out["fcf_ttm"] > 0 if not np.isnan(out["fcf_ttm"]) else True))
        sh = _row(ia, ("Diluted Average Shares", "Basic Average Shares"))
        if sh is not None and len(sh) >= 2 and sh.iloc[1] > 0:
            out["share_growth_pct"] = round(float(sh.iloc[0] / sh.iloc[1] - 1) * 100, 1)
        rev_a = _row(ia, ("Total Revenue", "Operating Revenue"))
        if rev_a is not None and sh is not None and len(rev_a) >= 2 and len(sh) >= 2:
            rps0 = float(rev_a.iloc[0] / sh.iloc[0]); rps1 = float(rev_a.iloc[1] / sh.iloc[1])
            if rps1 > 0:
                out["rev_ps_growth_pct"] = round((rps0 / rps1 - 1) * 100, 1)
        if not np.isnan(out["share_growth_pct"]):
            out["dilution_ok"] = bool(out["share_growth_pct"] <= 3.0 and (np.isnan(out["rev_ps_growth_pct"]) or out["rev_ps_growth_pct"] > 0))
        if rev is not None and opi is not None and len(rev) >= 5 and len(opi) >= 5:
            d_rev = float(rev.iloc[0] - rev.iloc[4]); d_op = float(opi.iloc[0] - opi.iloc[4])
            if abs(d_rev) > 0:
                out["incr_margin_pct"] = round(d_op / d_rev * 100, 1)
                om_prev = float(opi.iloc[4] / rev.iloc[4]) * 100 if rev.iloc[4] else np.nan
                out["incremental_ok"] = bool(d_rev > 0 and out["incr_margin_pct"] > om_prev) if not np.isnan(om_prev) else None
    except Exception:
        pass
    try:
        if rev is not None and len(rev) >= 5:
            g_now = float(rev.iloc[0] / rev.iloc[4] - 1) * 100
            g_prev = float(rev.iloc[1] / rev.iloc[5] - 1) * 100 if len(rev) >= 6 else float(rev.iloc[1] / rev.iloc[4] - 1) * 100
            out.update(rev_g_now=round(g_now, 1), rev_g_prev=round(g_prev, 1), accel_pp=round(g_now - g_prev, 1),
                       accel_ok=bool(g_now > g_prev and g_now > 0))
        if rev is not None and gp is not None and len(rev) >= 5 and len(gp) >= 5:
            gm_now = float(gp.iloc[0] / rev.iloc[0]) * 100
            gm_prev = float(gp.iloc[4] / rev.iloc[4]) * 100
            out.update(gm_now=round(gm_now, 1), gm_prev=round(gm_prev, 1), gm_delta_pp=round(gm_now - gm_prev, 1),
                       margin_ok=bool(gm_now > gm_prev))
    except Exception:
        pass
    # revisions / beats: FMP estimates if key, else yfinance earnings surprise history
    try:
        if data.has_fmp():
            est = data.fmp_analyst_estimates(ticker)
            if est is not None and not est.empty and "estimatedEpsAvg" in est.columns:
                e = est.sort_values(est.columns[0]).tail(2)["estimatedEpsAvg"].astype(float)
                if len(e) == 2 and e.iloc[0] != 0:
                    out["rev_up_pct"] = round(float(e.iloc[1] / e.iloc[0] - 1) * 100, 1)
                    out["rev_ok"] = out["rev_up_pct"] > 0
        if out["rev_ok"] is None:
            ed = data.get_earnings_dates(ticker)
            if ed is not None and not ed.empty and "Surprise(%)" in ed.columns:
                s = ed["Surprise(%)"].dropna().astype(float).head(4)
                if len(s):
                    out["surprise_avg"] = round(float(s.mean()), 1)
                    out["rev_ok"] = bool(s.mean() > 0 and (s > 0).mean() >= 0.75)
    except Exception:
        pass
    return out


@st.cache_data(ttl=3600, show_spinner="Running the pond screen…")
def pond(tickers: list[str], bench: str = "SPY", near_high_pct: float = -20.0,
         max_fundamentals: int = 80) -> pd.DataFrame:
    """F1: price gates on the whole universe (fast), fundamentals on survivors only."""
    px = screener.screen_universe(tickers, bench=bench)
    if px.empty:
        return px
    g = px.copy()
    g["gate_trend"] = (g["stage"] == "STAGE 2") & (g["pct_from_52w_high"] >= near_high_pct)
    g["gate_rs"] = (g["12_1_mom"].fillna(-1) > 0) & (g["rs_vs_bench"].fillna(-1) > 0)
    surv = g[g["gate_trend"] & g["gate_rs"]].head(max_fundamentals)
    rows = [fundamentals(t) for t in surv["ticker"]]
    f = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ticker"])
    out = surv.merge(f, on="ticker", how="left")
    out["gate_accel"] = out["accel_ok"].fillna(False).astype(bool)
    out["gate_margin"] = out["margin_ok"].fillna(False).astype(bool)
    _b = lambda v: bool(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else False
    out["gate_rev"] = out["rev_ok"].map(_b)
    out["gate_quality"] = out["quality_ok"].fillna(False).astype(bool)
    out["gate_dilution"] = out["dilution_ok"].map(_b)
    out["gate_incremental"] = out["incremental_ok"].map(_b)
    GATE_COLS = ["gate_trend", "gate_rs", "gate_accel", "gate_margin", "gate_rev", "gate_quality", "gate_dilution", "gate_incremental"]
    out["gates_passed"] = out[GATE_COLS].sum(axis=1)
    return out.sort_values(["gates_passed", "fast_composite"], ascending=False).reset_index(drop=True)


# ============================================================
# F2 — FISH: score, rank, correlation kill
# ============================================================
def _pct_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True).fillna(0.0)


def fish(p: pd.DataFrame, min_gates: int = 5, top_n: int = 5, corr_cut: float = 0.70,
         lookback: str = "6mo") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (ranked survivors, dropped-by-correlation). Score = mean pct-rank of
    acceleration, margin delta, revisions/beats, and relative strength."""
    if p.empty:
        return p, pd.DataFrame()
    f = p[p["gates_passed"] >= min_gates].copy()
    if f.empty:
        return f, pd.DataFrame()
    rev_metric = f["rev_up_pct"].where(f["rev_up_pct"].notna(), f["surprise_avg"])
    f["score"] = (_pct_rank(f["accel_pp"]) + _pct_rank(f["gm_delta_pp"]) + _pct_rank(rev_metric) +
                  _pct_rank(f["rs_vs_bench"]) + _pct_rank(f["gp_assets"]) + _pct_rank(f["incr_margin_pct"]) -
                  _pct_rank(f["share_growth_pct"].fillna(0))) / 6 * 100
    f = f.sort_values("score", ascending=False).reset_index(drop=True)

    # correlation kill: same trade → keep the higher score
    keep, dropped = [], []
    try:
        hist = data.bulk_history(list(f["ticker"].head(30)), period=lookback)
        rets = pd.DataFrame({t: hist[t]["Close"].pct_change() for t in f["ticker"].head(30) if t in hist}).dropna(how="all")
        corr = rets.corr()
        for t in f["ticker"]:
            if t not in corr:
                keep.append(t); continue
            twin = next((k for k in keep if k in corr and corr.loc[t, k] >= corr_cut), None)
            if twin is None:
                keep.append(t)
            else:
                dropped.append({"ticker": t, "same_trade_as": twin, "corr": round(float(corr.loc[t, twin]), 2)})
            if len(keep) >= top_n:
                break
    except Exception:
        keep = list(f["ticker"].head(top_n))
    ranked = f[f["ticker"].isin(keep)].head(top_n).reset_index(drop=True)
    return ranked, pd.DataFrame(dropped)


# ============================================================
# F3 — FOCUS: theses + sizing
# ============================================================
def load_theses() -> dict:
    try:
        return json.loads(THESIS_FILE.read_text())
    except Exception:
        return {}


def save_thesis(ticker: str, thesis: dict):
    allt = load_theses()
    allt[ticker] = thesis
    try:
        THESIS_FILE.parent.mkdir(exist_ok=True)
        THESIS_FILE.write_text(json.dumps(allt, indent=1))
    except Exception:
        pass


def size_position(portfolio: float, max_loss_pct: float, entry: float, stop: float) -> dict:
    """Shares such that hitting the stop costs max_loss_pct of the portfolio."""
    if entry <= 0 or stop <= 0 or stop >= entry:
        return {}
    risk_per_share = entry - stop
    dollars_at_risk = portfolio * max_loss_pct / 100
    shares = int(dollars_at_risk // risk_per_share)
    return {"shares": shares, "position_$": round(shares * entry), "position_pct": round(shares * entry / portfolio * 100, 1),
            "risk_$": round(shares * risk_per_share), "stop_dist_pct": round((entry / stop - 1) * 100, 1)}


# ============================================================
# F4 — REVIEW
# ============================================================
def review(ticker: str) -> dict:
    """Re-run the gates for a held name + next earnings date."""
    f = fundamentals(ticker)
    ed = data.get_earnings_dates(ticker)
    nxt = None
    try:
        fut = ed[ed.index > pd.Timestamp.now(tz=ed.index.tz)] if ed is not None and not ed.empty else pd.DataFrame()
        nxt = fut.index.min().date() if not fut.empty else None
    except Exception:
        pass
    df = data.get_history(ticker, period="2y")
    trend_ok = rs_ok = None
    if not df.empty and len(df) > 200:
        from . import stages
        d = stages.classify(df); last = d.iloc[-1]
        trend_ok = bool(last["stage"] == "STAGE 2")
        rs_ok = bool(df["close"].iloc[-1] / df["close"].iloc[-252] - 1 > 0) if len(df) >= 252 else None
    return {**f, "next_earnings": nxt, "gate_trend": trend_ok, "gate_rs": rs_ok,
            "gates_ok": sum(bool(x) for x in (trend_ok, rs_ok, f["accel_ok"], f["margin_ok"], f["rev_ok"], f["quality_ok"], f["dilution_ok"], f["incremental_ok"]))}


# ============================================================
# F3 — FOCUS (AI): fact pack → thesis → audit → scenarios
# ============================================================
def fact_pack(ticker: str) -> dict:
    """Everything the agents need, fetched — the user shouldn't type what an API knows."""
    fp = {"ticker": ticker, "fund": fundamentals(ticker)}
    try:
        fp["quote"] = data.get_quote(ticker) or {}
    except Exception:
        fp["quote"] = {}
    try:
        info = data.get_info(ticker) or {}
        fp["info"] = {k: info.get(k) for k in ("longName", "sector", "industry", "marketCap", "trailingPE", "forwardPE",
                                              "priceToSalesTrailing12Months", "revenueGrowth", "grossMargins", "operatingMargins",
                                              "returnOnEquity", "debtToEquity", "heldPercentInsiders", "heldPercentInstitutions",
                                              "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions", "longBusinessSummary")}
        if fp["info"].get("longBusinessSummary"):
            fp["info"]["longBusinessSummary"] = fp["info"]["longBusinessSummary"][:700]
    except Exception:
        fp["info"] = {}
    try:
        n = data.fh_news(ticker, days=14) if data.has_finnhub() else pd.DataFrame()
        fp["news"] = n["headline"].head(10).tolist() if not n.empty and "headline" in n else []
    except Exception:
        fp["news"] = []
    try:
        ed = data.get_earnings_dates(ticker)
        fut = ed[ed.index > pd.Timestamp.now(tz=ed.index.tz)] if ed is not None and not ed.empty else pd.DataFrame()
        fp["next_earnings"] = str(fut.index.min().date()) if not fut.empty else None
    except Exception:
        fp["next_earnings"] = None
    try:
        h = data.get_history(ticker, period="6mo")
        if not h.empty:
            tr = (h["high"] - h["low"]).rolling(14).mean().iloc[-1]
            fp["atr14"] = float(tr); fp["price"] = float(h["close"].iloc[-1])
            fp["high_52w"] = float(data.get_history(ticker, period="1y")["high"].max())
    except Exception:
        pass
    return fp


THESIS_PROMPT = """You are a buy-side analyst. Using ONLY the FACTS below, write a Stage-3 thesis card for {ticker}.
Return STRICT JSON with these keys and nothing else:
{{
 "wave": "<one sentence: the structural wave and why THIS company tolls it>",
 "invalidation": "<one sentence naming a specific metric/threshold that would prove the thesis wrong>",
 "edge": "<one sentence: why the market may be mispricing it right now>",
 "same_trade_as": "<tickers that are the same underlying bet, or 'none'>",
 "bear": {{"rev_cagr_pct": <num>, "op_margin_pct": <num>, "terminal_multiple": <num>}},
 "base": {{"rev_cagr_pct": <num>, "op_margin_pct": <num>, "terminal_multiple": <num>}},
 "bull": {{"rev_cagr_pct": <num>, "op_margin_pct": <num>, "terminal_multiple": <num>}},
 "stop_rationale": "<one sentence: where a stop belongs and why>",
 "gate_flags": ["<any gate the facts say is weak or failing>"]
}}
Numbers must be traceable to FACTS or clearly labelled assumptions inside the sentence. No hype.

FACTS:
{facts}
"""


def ai_thesis(ticker: str, fp: dict | None = None) -> dict:
    """Agent-written thesis card (+ audit). Returns {} if no LLM key."""
    if mp is None:
        return {}
    fp = fp or fact_pack(ticker)
    facts = json.dumps({k: v for k, v in fp.items() if k != "ticker"}, default=str)[:6000]
    prov = None
    for cand in ("gemini", "groq", "openrouter", "anthropic"):
        if mp._key(mp.PROVIDERS[cand]["key"]):
            prov = cand; break
    if not prov:
        return {}
    model = {"gemini": "gemini-flash-latest", "groq": "openai/gpt-oss-120b", "openrouter": "nvidia/nemotron-3-ultra-550b-a55b:free",
             "anthropic": "claude-haiku-4-5-20251001"}[prov]
    try:
        text, lat = mp._chat(prov, model, THESIS_PROMPT.format(ticker=ticker, facts=facts), max_tokens=900)
        j = json.loads(text[text.find("{"): text.rfind("}") + 1])
        j["_model"] = f"{prov}:{model}"; j["_latency_s"] = lat
        aud = mp.audit(json.dumps(j), facts)
        j["_audit"] = aud.get("audit", ""); j["_audit_pass"] = aud.get("audit_pass")
        return j
    except Exception as e:
        return {"_error": str(e)[:160]}


def scenario_returns(market_cap: float, revenue_ttm: float, years: int, scen: dict) -> dict:
    """Expected annual return under a scenario: future FCF-proxy × multiple vs today's cap."""
    try:
        fut_rev = revenue_ttm * (1 + scen["rev_cagr_pct"] / 100) ** years
        fut_op = fut_rev * scen["op_margin_pct"] / 100
        fut_cap = fut_op * scen["terminal_multiple"]
        cagr = (fut_cap / market_cap) ** (1 / years) - 1
        return {"future_cap": round(fut_cap), "multiple_of_today": round(fut_cap / market_cap, 2), "cagr_pct": round(cagr * 100, 1)}
    except Exception:
        return {}
