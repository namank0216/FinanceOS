"""
🎯 Today — single-screen daily snapshot.

Layout:
  1. Macro hero (regime + leverage gate)
  2. AI briefing slot  (filled LAST after all data loads, with full context)
  3. Indices strip
  4. Two-column: sector heatmap | top news with sentiment
  5. Biggest movers (S&P 500 + Nasdaq)
  6. Technical details collapsed below
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, data, macro, narrator, sentiment as sent_lib, universe, vix_analysis

st.title("🎯 Today")

# ============================================================
# 1 — Macro hero
# ============================================================
state = macro.assess()
gate_color = {"GREEN": "#22C55E", "YELLOW": "#FF8C00", "RED": "#EF4444"}[state.leverage_gate]

vix_state = vix_analysis.current_state() or {}
vix_now = vix_state.get("current")
vix_pctile = vix_state.get("percentile")
curve = state.components.get("10y_2y_spread")

c1, c2, c3 = st.columns([3, 1, 1])
with c1:
    st.markdown(
        f"<div style='background:#11182A;padding:1rem;border-left:5px solid {gate_color};border-radius:6px'>"
        f"<div style='color:#8a93a6;font-size:0.75rem;text-transform:uppercase'>"
        f"Macro regime &middot; Leverage gate</div>"
        f"<div style='font-size:1.6rem;font-weight:bold;color:{gate_color}'>"
        f"{state.regime} &middot; {state.leverage_gate}</div></div>",
        unsafe_allow_html=True,
    )
with c2:
    if vix_now is not None:
        cc = "#22C55E" if vix_now < 18 else "#FF8C00" if vix_now < 28 else "#EF4444"
        st.markdown(
            f"<div style='background:#11182A;padding:1rem;border-left:5px solid {cc};border-radius:6px'>"
            f"<div style='color:#8a93a6;font-size:0.75rem'>VIX</div>"
            f"<div style='font-size:1.6rem;font-weight:bold;color:{cc}'>{vix_now:.1f}</div>"
            f"<div style='color:#bcc3d6;font-size:0.78rem'>p{vix_pctile:.0f} historically</div></div>",
            unsafe_allow_html=True,
        )
with c3:
    if curve is not None:
        cc = "#22C55E" if curve > 0 else "#EF4444"
        lbl = "Healthy" if curve > 0 else "Inverted ⚠"
        st.markdown(
            f"<div style='background:#11182A;padding:1rem;border-left:5px solid {cc};border-radius:6px'>"
            f"<div style='color:#8a93a6;font-size:0.75rem'>10Y-2Y curve</div>"
            f"<div style='font-size:1.6rem;font-weight:bold;color:{cc}'>{curve:+.2f}%</div>"
            f"<div style='color:#bcc3d6;font-size:0.78rem'>{lbl}</div></div>",
            unsafe_allow_html=True,
        )

# ============================================================
# 2 — AI BRIEFING SLOT (reserved here, filled LAST after data loads)
# ============================================================
ai_slot = st.empty()

# ============================================================
# 3 — Indices strip
# ============================================================
st.markdown("### 📊 Indices today")

INDICES = ["SPY", "QQQ", "IWM", "DIA", "MDY"]
idx_data = []
for tk in INDICES:
    q = data.get_quote(tk)
    if not q.get("last") or not q.get("prev_close"):
        continue
    chg_today = (q["last"] - q["prev_close"]) / q["prev_close"] * 100
    # 1-month change
    df = data.get_history(tk, period="3mo")
    chg_1m = ((df["close"].iloc[-1] / df["close"].iloc[-21] - 1) * 100
              if len(df) >= 21 else None)
    idx_data.append({"ticker": tk, "last": q["last"],
                     "today": chg_today, "month": chg_1m})

idx_cols = st.columns(len(idx_data) if idx_data else 1)
for col, idx in zip(idx_cols, idx_data):
    today_color = "#22C55E" if idx["today"] > 0 else "#EF4444"
    month_str = (f"{idx['month']:+.1f}%" if idx['month'] is not None else "—")
    col.markdown(
        f"<div style='background:#11182A;padding:0.7rem;border-left:3px solid {today_color}'>"
        f"<div style='color:#8a93a6;font-size:0.7rem'>{idx['ticker']}</div>"
        f"<div style='font-size:1.1rem;color:#E6E8EE;font-weight:bold'>${idx['last']:,.2f}</div>"
        f"<div style='color:{today_color};font-size:0.85rem'>{idx['today']:+.2f}% today</div>"
        f"<div style='color:#8a93a6;font-size:0.72rem'>1M: {month_str}</div></div>",
        unsafe_allow_html=True,
    )

# ============================================================
# 4 — Side-by-side: sector heatmap | top news with sentiment
# ============================================================
st.markdown("### 🌐 Leadership & 📰 News flow")

# Compute sector data
sec_today = []
sec_month = []
for tk, name in universe.SECTOR_ETFS.items():
    q = data.get_quote(tk)
    if q.get("last") and q.get("prev_close"):
        chg = (q["last"] - q["prev_close"]) / q["prev_close"] * 100
        sec_today.append({"Sector": name, "ETF": tk, "Change %": chg})
    df = data.get_history(tk, period="3mo")
    if len(df) >= 21:
        ret = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) * 100
        sec_month.append({"Sector": name, "ETF": tk, "1M %": ret})

sec_today_df = pd.DataFrame(sec_today).sort_values("Change %", ascending=False).reset_index(drop=True) if sec_today else pd.DataFrame()
sec_month_df = pd.DataFrame(sec_month).sort_values("1M %", ascending=False).reset_index(drop=True) if sec_month else pd.DataFrame()

story = narrator.sector_story(sec_today_df, sec_month_df) if not sec_today_df.empty else None

# Compute news data
news = data.get_market_news(max_per_feed=15)
if not news.empty:
    scores = []
    for _, row in news.iterrows():
        text = (str(row["title"]) + " " + str(row.get("summary", "")))[:1500]
        scores.append(sent_lib.score_text(text)["score"])
    news["sentiment"] = scores
    news["sentiment_label"] = news["sentiment"].map(sent_lib.label)
    news = news.sort_values("ts", ascending=False)

mean_sent = news["sentiment"].mean() if not news.empty else 0
news_tone = "🟢 BULLISH" if mean_sent > 0.15 else "🔴 BEARISH" if mean_sent < -0.15 else "🟡 MIXED"
news_color = "#22C55E" if mean_sent > 0.15 else "#EF4444" if mean_sent < -0.15 else "#FFD700"

left, right = st.columns([1, 1])

# LEFT — Sector 1-month bars
with left:
    st.markdown("**Sector leadership — past month**")
    if not sec_month_df.empty:
        fig = go.Figure(go.Bar(
            x=sec_month_df["1M %"], y=sec_month_df["Sector"],
            orientation="h",
            marker_color=["#22C55E" if v > 0 else "#EF4444" for v in sec_month_df["1M %"]],
            text=[f"{v:+.1f}%" for v in sec_month_df["1M %"]], textposition="outside",
        ))
        fig.update_layout(template="plotly_dark", height=400,
                          paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                          xaxis=dict(title="1M %", ticksuffix="%"),
                          yaxis=dict(autorange="reversed"),
                          margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

# RIGHT — News with sentiment tone banner + headline list
with right:
    st.markdown(
        f"**Market news — overall tone:** "
        f"<span style='color:{news_color};font-weight:bold'>{news_tone}</span> "
        f"<span style='color:#8a93a6;font-size:0.85rem'>(avg sentiment {mean_sent:+.2f})</span>",
        unsafe_allow_html=True,
    )
    if news.empty:
        st.info("No news pulled — RSS feeds may be temporarily unavailable.")
    else:
        for _, row in news.head(8).iterrows():
            sent_color = ("#22C55E" if row["sentiment"] > 0.15
                          else "#EF4444" if row["sentiment"] < -0.15
                          else "#8a93a6")
            age = pd.Timestamp.utcnow() - row["ts"]
            age_str = (f"{int(age.total_seconds()/3600)}h ago"
                       if age < pd.Timedelta(days=1) else f"{age.days}d ago")
            link_html = (
                "<div style='background:#11182A;padding:0.5rem 0.7rem;"
                f"border-left:3px solid {sent_color};margin-bottom:0.3rem;border-radius:3px'>"
                f"<div style='font-size:0.7rem;color:#8a93a6'>{row['source']} &middot; {age_str}</div>"
                f"<div style='font-size:0.88rem;color:#E6E8EE;line-height:1.35;margin-top:0.2rem'>"
                f"<a href='{row['link']}' target='_blank' style='color:#E6E8EE;text-decoration:none'>"
                f"{row['title']}</a></div></div>"
            )
            st.markdown(link_html, unsafe_allow_html=True)


# ============================================================
# 5 — Biggest movers
# ============================================================
st.markdown("### Biggest movers today")


@st.cache_data(ttl=300)
def _movers(top_n: int = 8):
    tickers = universe.get_full_universe()[:300]
    rows = []
    for tk in tickers:
        q = data.get_quote(tk)
        if not q.get("last") or not q.get("prev_close"):
            continue
        chg = (q["last"] - q["prev_close"]) / q["prev_close"] * 100
        rows.append({"ticker": tk, "last": q["last"], "change": chg})
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
    df = pd.DataFrame(rows)
    return (df.nlargest(top_n, "change").reset_index(drop=True),
            df.nsmallest(top_n, "change").reset_index(drop=True))


with st.spinner("Scanning movers..."):
    gainers, losers = _movers(top_n=8)

mc1, mc2 = st.columns(2)
with mc1:
    st.markdown("**Top gainers**")
    if not gainers.empty:
        for _, r in gainers.iterrows():
            row_html = (
                "<div style='background:#11182A;padding:0.4rem 0.7rem;"
                "border-left:3px solid #22C55E;margin-bottom:0.25rem;display:flex;justify-content:space-between'>"
                f"<span style='font-weight:bold;color:#E6E8EE'>{r['ticker']}</span>"
                f"<span style='color:#bcc3d6'>${r['last']:,.2f}</span>"
                f"<span style='color:#22C55E;font-weight:bold'>{r['change']:+.2f}%</span></div>"
            )
            st.markdown(row_html, unsafe_allow_html=True)
with mc2:
    st.markdown("**Top losers**")
    if not losers.empty:
        for _, r in losers.iterrows():
            row_html = (
                "<div style='background:#11182A;padding:0.4rem 0.7rem;"
                "border-left:3px solid #EF4444;margin-bottom:0.25rem;display:flex;justify-content:space-between'>"
                f"<span style='font-weight:bold;color:#E6E8EE'>{r['ticker']}</span>"
                f"<span style='color:#bcc3d6'>${r['last']:,.2f}</span>"
                f"<span style='color:#EF4444;font-weight:bold'>{r['change']:+.2f}%</span></div>"
            )
            st.markdown(row_html, unsafe_allow_html=True)


# ============================================================
# 6 — Technical details
# ============================================================
with st.expander("VIX 1-year history"):
    vix_hist = data.fred_series("VIXCLS", days=365)
    if not vix_hist.empty:
        fig = go.Figure(go.Scatter(x=vix_hist["date"], y=vix_hist["value"],
                                    fill="tozeroy", line=dict(color="#FF8C00", width=2)))
        fig.add_hline(y=15, line_dash="dot", line_color="#22C55E")
        fig.add_hline(y=22, line_dash="dot", line_color="#FFD700")
        fig.add_hline(y=30, line_dash="dot", line_color="#EF4444")
        fig.update_layout(template="plotly_dark", height=260,
                          paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                          margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 7 — Fill the AI BRIEFING SLOT with FULL context (everything is loaded now)
# ============================================================
ctx_parts = [
    f"Macro regime: {state.regime}, leverage gate: {state.leverage_gate}.",
]
if vix_now is not None:
    ctx_parts.append(f"VIX: {vix_now:.1f} (p{vix_pctile:.0f} of 30y history)")
if curve is not None:
    ctx_parts.append(f"10Y-2Y curve: {curve:+.2f}%")
if idx_data:
    ctx_parts.append("Indices today: " +
                     ", ".join(f"{i['ticker']} {i['today']:+.2f}%" for i in idx_data))
    month_parts = [f"{i['ticker']} {i['month']:+.1f}%"
                   for i in idx_data if i['month'] is not None]
    if month_parts:
        ctx_parts.append("Indices 1M: " + ", ".join(month_parts))
if not sec_month_df.empty:
    top3 = sec_month_df.head(3)
    bot3 = sec_month_df.tail(3)
    ctx_parts.append("Sector 1M leaders: " +
                     ", ".join(f"{r['Sector']} {r['1M %']:+.1f}%" for _, r in top3.iterrows()))
    ctx_parts.append("Sector 1M laggards: " +
                     ", ".join(f"{r['Sector']} {r['1M %']:+.1f}%" for _, r in bot3.iterrows()))
if story:
    ctx_parts.append(f"Group avgs: growth {story['metrics']['growth_1m']:+.1f}%, "
                     f"defensives {story['metrics']['defensive_1m']:+.1f}%, "
                     f"cyclicals {story['metrics']['cyclical_1m']:+.1f}%")
if not news.empty:
    ctx_parts.append(f"News tone: {news_tone}, mean sentiment {mean_sent:+.2f} across {len(news)} headlines.")
    top_titles = news.head(5)["title"].tolist()
    ctx_parts.append("Top 5 headlines:\n" + "\n".join(f"- {t}" for t in top_titles))
if not gainers.empty:
    ctx_parts.append("Top gainers: " +
                     ", ".join(f"{r['ticker']} {r['change']:+.1f}%"
                              for _, r in gainers.head(5).iterrows()))
if not losers.empty:
    ctx_parts.append("Top losers: " +
                     ", ".join(f"{r['ticker']} {r['change']:+.1f}%"
                              for _, r in losers.head(5).iterrows()))

ctx = "\n".join(p for p in ctx_parts if p)

if story:
    fallback = (
        f"<b>Verdict:</b> {story['regime']}<br>"
        f"<b>Why:</b> {story['headline']} News tone: {news_tone} ({mean_sent:+.2f}).<br>"
        f"<b>Action:</b> {story['actions'][0] if story['actions'] else 'Monitor.'}<br>"
        f"<b>Watch for:</b> Sector leadership flipping growth/defensive."
    )
else:
    fallback = (
        f"<b>Verdict:</b> {state.regime}<br>"
        f"<b>Why:</b> Leverage gate {state.leverage_gate}. {state.summary}<br>"
        f"<b>Action:</b> Confirm regime before initiating new positions."
    )

with ai_slot.container():
    ai_summary.auto_summarize(st, ctx, page_kind="today", fallback_text=fallback)

st.caption("Research and decision-support tool. Not financial advice.")
