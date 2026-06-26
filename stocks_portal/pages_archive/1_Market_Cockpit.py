"""Market Cockpit — daily glance at indices, sectors, breadth."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import ai_summary, data, explainers, narrator, universe

st.set_page_config(page_title="Market Cockpit", layout="wide")
st.title("📊 Market Cockpit")
st.caption("Indices · sectors · breadth · VIX. Your daily snapshot.")

explainers.help_box(st, "What this page tells you (in plain English)", """
**The 60-second daily check** — what happened today, who led, who lagged.

- **Indices grid** — SPY, QQQ, IWM, DIA, MDY today's performance + 52-week range position.
- **Sectors today** — which of the 11 SPDR sectors are leading vs lagging right now.
- **Sectors 1-month** — same view but over the last month (filters out daily noise).
- **VIX 12-month chart** — fear gauge with calm/elevated/stress reference lines. <15 = complacency,
  15-22 = normal, 22-30 = elevated fear, >30 = panic.
- **S&P 500 chart** — 1 year with 50-day, 150-day (= 30-week, the Weinstein line), and 200-day
  moving averages.

**How to read the sector colors:** when defensives (XLP, XLU, XLV) are leading, the market is
playing defense — risk-off undertone. When tech (XLK), discretionary (XLY), and small caps are
leading, that's risk-on. Notice the regime, then position accordingly on individual names.
""")

# --- Indices grid ---
indices = ["SPY", "QQQ", "IWM", "DIA", "MDY"]
rows = []
for tk in indices:
    q = data.get_quote(tk)
    if not q.get("last"):
        continue
    chg = (q["last"] - q["prev_close"]) / q["prev_close"] * 100 if q.get("prev_close") else 0
    pct_52w = (q["last"] - q["year_low"]) / (q["year_high"] - q["year_low"]) * 100 \
        if q.get("year_high") and q.get("year_low") and q["year_high"] != q["year_low"] else None
    rows.append({"ETF": tk, "Last": q["last"], "Change %": chg,
                 "52w Range Pos %": pct_52w, "Day High": q.get("day_high"),
                 "Day Low": q.get("day_low")})

if rows:
    idx_df = pd.DataFrame(rows)
    fmt = idx_df.copy()
    fmt["Last"] = fmt["Last"].map(lambda x: f"${x:,.2f}")
    fmt["Change %"] = fmt["Change %"].map(lambda x: f"{x:+.2f}%")
    fmt["52w Range Pos %"] = fmt["52w Range Pos %"].map(
        lambda x: f"{x:.0f}%" if x is not None else "—")
    fmt["Day High"] = fmt["Day High"].map(lambda x: f"${x:,.2f}" if x else "—")
    fmt["Day Low"] = fmt["Day Low"].map(lambda x: f"${x:,.2f}" if x else "—")
    st.dataframe(fmt, use_container_width=True, hide_index=True)

st.divider()

explainers.help_box(st, "Defensive vs Risk-On — what the sector colors actually mean", """
The 11 sector ETFs you'll see below aren't just buckets — they tell you **who's winning the
risk-on vs defensive battle today**. That signal alone is worth more than most technical indicators.

**🟢 Risk-on / Growth sectors** (lead when investors are optimistic):
- **XLK Technology** — Apple, Microsoft, Nvidia. The growth engine.
- **XLY Consumer Discretionary** — Amazon, Tesla, Home Depot. Things people buy when they have spare cash.
- **XLC Communication Services** — Meta, Google, Netflix. Mostly mega-cap tech.

**🟡 Cyclical sectors** (lead when the economy is expanding):
- **XLF Financials** — Banks, JPM, BAC. Make more on rising rates UNTIL recession hits credit.
- **XLI Industrials** — Boeing, Caterpillar. Construction, manufacturing, defense.
- **XLB Materials** — Chemicals, mining. Tied to global commodity demand.
- **XLE Energy** — Exxon, Chevron. Oil prices drive these.

**🔴 Defensive sectors** (lead when investors are nervous):
- **XLP Consumer Staples** — Coca-Cola, Walmart, P&G. People buy soap and food regardless.
- **XLV Health Care** — Pfizer, Lilly, J&J. Inelastic demand — recessions don't stop heart attacks.
- **XLU Utilities** — Duke, NextEra. People always need electricity. Dividend-heavy.
- **XLRE Real Estate** — REITs. Defensive but rate-sensitive.

**The decision rule:**
- When 🔴 **defensives lead and 🟢 risk-on lags** → **risk-off undertone**. Reduce equity exposure.
  Tighten stops. The smart money is hiding.
- When 🟢 **risk-on leads and 🔴 defensives lag** → **risk-on confirmed**. Add to growth, cyclicals,
  small caps. Leveraged ETFs are eligible.
- When **commodity sectors (XLE, XLB) lead with defensives** → **stagflation risk** — the worst
  outcome for traditional 60/40 portfolios.

Look at the 1-month bar chart further down to filter out daily noise — that's the signal that matters.
""")

# --- Sector heatmap ---
st.subheader("Sectors today")
sec_rows = []
for tk, name in universe.SECTOR_ETFS.items():
    q = data.get_quote(tk)
    if not q.get("last") or not q.get("prev_close"):
        continue
    chg = (q["last"] - q["prev_close"]) / q["prev_close"] * 100
    sec_rows.append({"Sector": name, "ETF": tk, "Change %": chg, "Last": q["last"]})

if sec_rows:
    sec_df = pd.DataFrame(sec_rows).sort_values("Change %", ascending=False).reset_index(drop=True)
    # Treemap-style bar chart
    fig = go.Figure(go.Bar(
        x=sec_df["Sector"],
        y=sec_df["Change %"],
        marker_color=["#22C55E" if v > 0 else "#EF4444" for v in sec_df["Change %"]],
        text=[f"{v:+.2f}%" for v in sec_df["Change %"]],
        textposition="outside",
    ))
    fig.update_layout(
        template="plotly_dark", height=380,
        paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
        yaxis=dict(title="Today %", ticksuffix="%"),
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 1-month performance
    st.subheader("Sectors — 1 month")
    sec_perf = []
    for tk, name in universe.SECTOR_ETFS.items():
        df = data.get_history(tk, period="3mo")
        if len(df) < 21:
            continue
        ret_1m = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) * 100
        sec_perf.append({"Sector": name, "ETF": tk, "1M %": ret_1m})
    if sec_perf:
        sp_df = pd.DataFrame(sec_perf).sort_values("1M %", ascending=False)
        fig = go.Figure(go.Bar(
            x=sp_df["Sector"], y=sp_df["1M %"],
            marker_color=["#22C55E" if v > 0 else "#EF4444" for v in sp_df["1M %"]],
            text=[f"{v:+.1f}%" for v in sp_df["1M %"]],
            textposition="outside",
        ))
        fig.update_layout(
            template="plotly_dark", height=380,
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            yaxis=dict(title="1M %", ticksuffix="%"),
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ============================================================
        # 🧠 The Narrator — what this is telling you (deterministic)
        # ============================================================
        sec_today_df = pd.DataFrame(sec_rows) if sec_rows else pd.DataFrame()
        story = narrator.sector_story(sec_today_df, sp_df)

        narrator.render_narrator_card(
            st,
            headline=story["headline"],
            narrative=story["narrative"],
            flags=story.get("flags", []),
            actions=story.get("actions", []),
            badge_color=story["badge_color"],
            regime=story["regime"],
        )

        # ============================================================
        # Optional AI elaboration — if user has an API key configured
        # ============================================================
        if ai_summary.has_ai():
            with st.expander(f"🤖 Ask AI to elaborate ({ai_summary.provider_label()})", expanded=False):
                if st.button("Generate AI commentary", key="ai_sector"):
                    with st.spinner("Generating AI interpretation…"):
                        ctx = ai_summary.build_sector_context(
                            sec_today_df, sp_df, story["regime"],
                            story["metrics"]["growth_1m"],
                            story["metrics"]["defensive_1m"],
                            story["metrics"]["cyclical_1m"],
                        )
                        result = ai_summary.ask_ai(ctx, max_tokens=400)
                        if result:
                            st.markdown(result)
                            st.caption("⚠ AI-generated commentary — for education only, not financial advice.")
                        else:
                            st.info("No response from AI provider.")
        else:
            with st.expander("🤖 Want richer AI commentary on this data?", expanded=False):
                st.markdown("""
The summary above is **deterministic** (rules-based) and runs instantly. For AI-generated
commentary, you can plug in any of:

- **🆓 Groq (free)** — sign up at https://console.groq.com → 30 req/min, very fast.
  Add `GROQ_API_KEY=your-key` to `.env`.
- **🆓 Ollama (local, free)** — install from https://ollama.com, run `ollama pull llama3.2`,
  then add `OLLAMA_HOST=http://localhost:11434` to `.env`. Runs entirely on your machine.
- **💸 Anthropic Claude** — pay-per-token, ~$0.25/1M input tokens for Haiku.
  Add `ANTHROPIC_API_KEY=your-key` to `.env`.
- **💸 OpenAI** — similar pricing. Add `OPENAI_API_KEY=your-key` to `.env`.

Restart Streamlit after editing `.env`. The page will then show an "Ask AI" button here.
""")

st.divider()

# --- VIX history ---
st.subheader("VIX — 12 months")
vix = data.fred_series("VIXCLS", days=365)
if not vix.empty:
    fig = go.Figure(go.Scatter(
        x=vix["date"], y=vix["value"], fill="tozeroy",
        line=dict(color="#FF8C00", width=2),
    ))
    fig.add_hline(y=15, line_dash="dot", line_color="#22C55E", annotation_text="Calm <15")
    fig.add_hline(y=22, line_dash="dot", line_color="#FFD700", annotation_text="Elevated >22")
    fig.add_hline(y=30, line_dash="dot", line_color="#EF4444", annotation_text="Stress >30")
    fig.update_layout(
        template="plotly_dark", height=320,
        paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Index chart with breadth context ---
st.subheader("S&P 500 — 1 year w/ key MAs")
spy = data.get_history("SPY", period="1y")
if not spy.empty:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=spy.index, open=spy["open"], high=spy["high"], low=spy["low"],
        close=spy["close"], increasing_line_color="#22C55E",
        decreasing_line_color="#EF4444", name="SPY",
    ))
    for n, col in [(50, "#FFD700"), (150, "#FF8C00"), (200, "#E6E8EE")]:
        fig.add_trace(go.Scatter(
            x=spy.index, y=spy["close"].rolling(n).mean(),
            mode="lines", name=f"MA{n}", line=dict(color=col, width=1.5),
        ))
    fig.update_layout(
        template="plotly_dark", height=520,
        paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=1.05),
    )
    st.plotly_chart(fig, use_container_width=True)
