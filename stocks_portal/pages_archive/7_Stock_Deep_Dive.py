"""Stock Deep Dive — single-ticker comprehensive view: chart, fundamentals, holders, news."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import ai_summary, data, explainers, factors, sentiment as sent_lib, stages, universe

st.set_page_config(page_title="Stock Deep Dive", layout="wide")
st.title("🔬 Stock Deep Dive")

explainers.help_box(st, "What this page tells you (in plain English)", """
This is the **research workbench for one stock**. You'll find:

- 📈 **Chart** — price history with the three moving averages that matter (50-day, 150-day = 30-week, 200-day).
- 💰 **Fundamentals** — the five questions every fundamental investor asks: Is it cheap? Is it profitable?
  Is it growing? Is the balance sheet sound? Are margins expanding or contracting? Each ratio shipped
  with a plain-English verdict — no need to memorise what 'good ROE' means.
- 📊 **Estimates** — analyst targets and consensus.
- 🏛 **Holders** — who owns it (institutional ownership matters; >70% = heavily institutional).
- 📰 **News** — recent headlines with sentiment scoring.

**For the institutional position-trader workflow:** screen first (Stock Screener), narrow to Stage 2
candidates, then run each through this page to verify the fundamentals back up the chart action,
then send the final candidates to the Valuation Engine for the under/over-valued verdict.
""")

c1, c2 = st.columns([2, 4])
query = c1.text_input("Ticker or company name", value="NVDA",
                      placeholder="e.g. NVDA, Nvidia, Apple")
if not query:
    st.stop()

ticker, candidates = universe.resolve_ticker(query)
if not ticker:
    st.error(f"Could not resolve '{query}'.")
    st.stop()
if len(candidates) > 1 and candidates[0][1]:
    options = [f"{tk} — {name}" for tk, name in candidates]
    chosen = c2.selectbox("Multiple matches — pick one:", options, index=0)
    ticker = chosen.split(" — ")[0]
elif candidates and candidates[0][1]:
    c2.caption(f"→ Resolved to **{ticker}** ({candidates[0][1]})")

# ---------- Pull everything ----------
quote = data.get_quote(ticker)
info = data.get_info(ticker)
hist = data.get_history(ticker, period="2y")
fmp_metrics = data.fmp_key_metrics(ticker) if data.has_fmp() else {}
fmp_ratios = data.fmp_ratios(ticker) if data.has_fmp() else {}
fmp_pt = data.fmp_price_target(ticker) if data.has_fmp() else {}
recs = data.get_recommendations(ticker)
holders = data.get_holders(ticker)
fh_news = data.fh_news(ticker, days=14) if data.has_finnhub() else pd.DataFrame()

if hist.empty:
    st.error(f"No data for {ticker}.")
    st.stop()

hist = stages.classify(hist)
last = hist.iloc[-1]

# ---------- Header ----------
st.subheader(f"{info.get('shortName', ticker)} ({ticker})")
st.caption(f"{info.get('sector', '—')} · {info.get('industry', '—')} · "
           f"{info.get('country', '—')}")

# ---------- KPI strip ----------
chg_pct = (quote["last"] - quote["prev_close"]) / quote["prev_close"] * 100 \
    if quote.get("last") and quote.get("prev_close") else 0
mc = quote.get("market_cap") or 0
if mc and mc > 1e12:
    mc_str = f"${mc/1e12:.2f}T"
elif mc and mc > 1e9:
    mc_str = f"${mc/1e9:.1f}B"
elif mc and mc > 1e6:
    mc_str = f"${mc/1e6:.0f}M"
else:
    mc_str = "—"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Last", f"${quote.get('last', 0):,.2f}", f"{chg_pct:+.2f}%")
k2.metric("Market Cap", mc_str)
k3.metric("Stage", stages.stage_label(str(last["stage"])))
k4.metric("% from 52w high", f"{last['pct_from_52w_high']:+.1f}%")
k5.metric("ATR (14d)", f"{last['atr_pct']:.2f}%")

# AI elaboration on the whole stock
ai_ctx = (
    f"Stock: {info.get('shortName', ticker)} ({ticker}) — "
    f"{info.get('sector', '')} / {info.get('industry', '')}\n"
    f"Price ${quote.get('last', 0):,.2f}, today {chg_pct:+.2f}%, market cap {mc_str}\n"
    f"Stage: {last['stage']}, % from 52w high {last['pct_from_52w_high']:+.1f}%\n"
    f"Valuation: P/E {info.get('trailingPE')}, Forward P/E {info.get('forwardPE')}, "
    f"P/S {info.get('priceToSalesTrailing12Months')}, PEG {info.get('trailingPegRatio')}\n"
    f"Profitability: ROE {(info.get('returnOnEquity') or 0) * 100:.1f}%, "
    f"profit margin {(info.get('profitMargins') or 0) * 100:.1f}%, "
    f"D/E {info.get('debtToEquity')}\n"
    f"Growth: revenue {(info.get('revenueGrowth') or 0) * 100:.1f}%, "
    f"earnings {(info.get('earningsGrowth') or 0) * 100:.1f}%"
)
ai_summary.render_ai_button(st, ai_ctx, key=f"deepdive_{ticker}")

st.divider()

# ---------- Tabs ----------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Chart", "💰 Fundamentals", "📊 Estimates",
                                        "🏛 Holders", "📰 News"])

# === TAB 1: Chart ===
with tab1:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["open"], high=hist["high"], low=hist["low"],
        close=hist["close"], increasing_line_color="#22C55E",
        decreasing_line_color="#EF4444", name=ticker,
    ))
    for n, col in [(50, "#FFD700"), (150, "#FF8C00"), (200, "#E6E8EE")]:
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist["close"].rolling(n).mean(),
            mode="lines", name=f"MA{n}", line=dict(color=col, width=1.5),
        ))
    fig.update_layout(template="plotly_dark", height=550,
                      paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                      xaxis_rangeslider_visible=False,
                      margin=dict(l=0, r=0, t=20, b=0),
                      legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, use_container_width=True)

# === TAB 2: Fundamentals ===
with tab2:
    st.caption("Each metric shipped with a plain-English verdict. The technical numbers stay; "
               "the interpretation is added.")

    # ---- Valuation block ----
    st.markdown("### 💸 Valuation — is it cheap or expensive?")
    pe = info.get("trailingPE")
    fwd_pe = info.get("forwardPE")
    peg = info.get("trailingPegRatio")
    ps = info.get("priceToSalesTrailing12Months")
    ev_ebitda = info.get("enterpriseToEbitda")
    pb = info.get("priceToBook")

    val_cols = st.columns(3)
    if pe:
        v, exp = explainers.interpret_pe(pe)
        val_cols[0].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #FF8C00;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">P/E Ratio (trailing)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{pe:.1f}</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{exp}</div>
        </div>""", unsafe_allow_html=True)
    if peg:
        v, exp = explainers.interpret_peg(peg)
        val_cols[1].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #FF8C00;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">PEG (Price/Earnings to Growth)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{peg:.2f}</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{exp}</div>
        </div>""", unsafe_allow_html=True)
    if fwd_pe:
        if pe:
            disc = (pe - fwd_pe) / pe * 100
            disc_text = f"Forward P/E is **{abs(disc):.0f}% {'lower' if disc > 0 else 'higher'}** than trailing — analysts expect earnings to {'grow' if disc > 0 else 'fall'}."
        else:
            disc_text = "Forward P/E is based on next year's expected earnings."
        val_cols[2].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #FF8C00;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">Forward P/E (next year)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{fwd_pe:.1f}</div>
          <div style="color:#bcc3d6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{disc_text}</div>
        </div>""", unsafe_allow_html=True)

    # Secondary valuation row — show technical detail without verdicts
    sec_cols = st.columns(4)
    for col, (val, lab, suffix) in zip(sec_cols, [
        (ps, "P/S (Price to Sales)", ""),
        (pb, "P/B (Price to Book)", ""),
        (ev_ebitda, "EV/EBITDA", ""),
        ((info.get("dividendYield") or 0) * 100 if info.get("dividendYield") else None, "Dividend Yield", "%"),
    ]):
        if val is not None:
            col.metric(lab, f"{val:.2f}{suffix}",
                       help=explainers.GLOSSARY.get(lab.split(' (')[0].split(' ')[0], {}).get("long", ""))

    st.divider()

    # ---- Quality block ----
    st.markdown("### 💎 Quality — is the business itself any good?")
    roe = info.get("returnOnEquity")
    roic_fmp = (fmp_metrics or {}).get("roicTTM")
    fcfy_fmp = (fmp_metrics or {}).get("freeCashFlowYieldTTM")
    de = info.get("debtToEquity")

    qcols = st.columns(2)
    if roe is not None:
        v, exp = explainers.interpret_roe(roe)
        qcols[0].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #22C55E;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">Return on Equity (ROE)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{roe*100:.1f}%</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{exp}</div>
        </div>""", unsafe_allow_html=True)
    if roic_fmp is not None:
        v, exp = explainers.interpret_roe(roic_fmp)
        qcols[1].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #22C55E;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">ROIC (Return on Invested Capital)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{roic_fmp*100:.1f}%</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">The single best long-term predictor of compounders. >15% sustained = wide moat.</div>
        </div>""", unsafe_allow_html=True)

    qcols2 = st.columns(2)
    if fcfy_fmp is not None:
        v, exp = explainers.interpret_fcf_yield(fcfy_fmp)
        qcols2[0].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #22C55E;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">FCF Yield (cash thrown off vs market cap)</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{fcfy_fmp*100:.2f}%</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{exp}</div>
        </div>""", unsafe_allow_html=True)
    if de is not None:
        v, exp = explainers.interpret_debt_equity(de)
        qcols2[1].markdown(f"""
        <div style="background:#11182A;padding:0.8rem;border-left:3px solid #FFD700;margin-bottom:0.5rem">
          <div style="color:#8a93a6;font-size:0.72rem">Debt / Equity</div>
          <div style="font-size:1.4rem;font-weight:bold;color:#E6E8EE">{de:.2f}</div>
          <div style="color:#bcc3d6;font-size:0.85rem;margin-top:0.2rem">{v}</div>
          <div style="color:#8a93a6;font-size:0.78rem;margin-top:0.3rem;line-height:1.3">{exp}</div>
        </div>""", unsafe_allow_html=True)

    # Margins row
    st.markdown("**Margins** (the higher the better — wider margins = pricing power)")
    mcols = st.columns(3)
    for col, key, label in zip(mcols, ["grossMargins", "operatingMargins", "profitMargins"],
                                ["Gross Margin", "Operating Margin", "Profit Margin"]):
        v = info.get(key)
        if v is not None:
            pct = v * 100
            color = "#22C55E" if pct > 25 else "#FFD700" if pct > 10 else "#EF4444"
            verdict = "Excellent" if pct > 40 else "Strong" if pct > 25 else "Average" if pct > 15 else "Thin"
            col.markdown(f"""
            <div style="background:#11182A;padding:0.7rem;border-left:3px solid {color}">
              <div style="color:#8a93a6;font-size:0.72rem">{label}</div>
              <div style="font-size:1.3rem;font-weight:bold;color:{color}">{pct:.1f}%</div>
              <div style="color:#bcc3d6;font-size:0.78rem">{verdict}</div>
            </div>""", unsafe_allow_html=True)

    # Growth row
    st.markdown("**Growth** (positive = expanding business)")
    gcols = st.columns(2)
    rev_g = info.get("revenueGrowth")
    eps_g = info.get("earningsGrowth")
    if rev_g is not None:
        rg = rev_g * 100
        color = "#22C55E" if rg > 10 else "#FFD700" if rg > 0 else "#EF4444"
        verdict = "Fast-growing" if rg > 20 else "Healthy growth" if rg > 5 else "Slow growth" if rg > 0 else "Declining"
        gcols[0].markdown(f"""
        <div style="background:#11182A;padding:0.7rem;border-left:3px solid {color}">
          <div style="color:#8a93a6;font-size:0.72rem">Revenue Growth (YoY)</div>
          <div style="font-size:1.3rem;font-weight:bold;color:{color}">{rg:+.1f}%</div>
          <div style="color:#bcc3d6;font-size:0.78rem">{verdict}</div>
        </div>""", unsafe_allow_html=True)
    if eps_g is not None:
        eg = eps_g * 100
        color = "#22C55E" if eg > 10 else "#FFD700" if eg > 0 else "#EF4444"
        verdict = "Earnings expanding" if eg > 20 else "Modest growth" if eg > 0 else "Earnings shrinking"
        gcols[1].markdown(f"""
        <div style="background:#11182A;padding:0.7rem;border-left:3px solid {color}">
          <div style="color:#8a93a6;font-size:0.72rem">Earnings Growth (YoY)</div>
          <div style="font-size:1.3rem;font-weight:bold;color:{color}">{eg:+.1f}%</div>
          <div style="color:#bcc3d6;font-size:0.78rem">{verdict}</div>
        </div>""", unsafe_allow_html=True)

# === TAB 3: Estimates ===
with tab3:
    if fmp_pt:
        c1, c2, c3 = st.columns(3)
        target = fmp_pt.get("targetConsensus")
        if target:
            upside = (target - quote["last"]) / quote["last"] * 100
            c1.metric("Analyst target", f"${target:.2f}", f"{upside:+.1f}% upside")
        c2.metric("High target", f"${fmp_pt.get('targetHigh', 0):.2f}")
        c3.metric("Low target",  f"${fmp_pt.get('targetLow', 0):.2f}")
    else:
        st.info("Add FMP API key for analyst targets (free tier).")

    if not recs.empty:
        st.markdown("**Recommendation summary**")
        st.dataframe(recs, use_container_width=True, hide_index=True)

# === TAB 4: Holders ===
with tab4:
    inst = holders.get("institutional")
    if inst is not None and not inst.empty:
        st.markdown("**Top institutional holders**")
        st.dataframe(inst, use_container_width=True, hide_index=True)
    major = holders.get("major")
    if major is not None and not major.empty:
        st.markdown("**Ownership breakdown**")
        st.dataframe(major, use_container_width=True, hide_index=True)
    if (inst is None or inst.empty) and (major is None or major.empty):
        st.info("No holder data available.")

# === TAB 5: News ===
with tab5:
    if not fh_news.empty:
        st.markdown(f"**Finnhub news for {ticker} (last 14 days)**")
        for _, row in fh_news.head(30).iterrows():
            headline = row.get("headline", "")
            sentiment = sent_lib.score_text(headline)
            label = sent_lib.label(sentiment["score"])
            color = {"VERY BULLISH": "#22C55E", "BULLISH": "#16A34A",
                     "NEUTRAL": "#8a93a6",
                     "BEARISH": "#DC2626", "VERY BEARISH": "#EF4444"}.get(label, "#8a93a6")
            ts = row["datetime"].strftime("%Y-%m-%d %H:%M")
            st.markdown(f"""
            <div style="background:#11182A;padding:0.6rem;border-left:3px solid {color};margin-bottom:0.4rem">
              <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:#8a93a6">
                <span>{row.get('source', '')} · {ts}</span>
                <span style="color:{color}">{label} ({sentiment['score']:+.2f})</span>
              </div>
              <div style="margin:0.3rem 0;color:#E6E8EE">
                <a href="{row.get('url', '')}" target="_blank" style="color:#E6E8EE;text-decoration:none">
                  {headline}
                </a>
              </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No ticker-specific news. Add Finnhub API key for richer feed (free tier).")
