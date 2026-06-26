"""News Flow — market news with sentiment scoring."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, data, sentiment

st.title("📰 News Flow")
st.caption("Market headlines with lexicon sentiment. Filter by source, sentiment, or keyword.")

news = data.get_market_news(max_per_feed=25)
if news.empty:
    st.error("No news pulled. RSS feeds may be temporarily unavailable.")
    st.stop()

# Score
with st.spinner("Scoring sentiment…"):
    scores = []
    for _, row in news.iterrows():
        text = (str(row["title"]) + " " + str(row["summary"]))[:2000]
        s = sentiment.score_text(text)
        scores.append(s["score"])
    news["sentiment"] = scores
    news["sentiment_label"] = news["sentiment"].map(sentiment.label)

# AI briefing on what the news is saying
top_headlines = news.head(15)["title"].tolist()
mean_sent = news["sentiment"].mean()
news_ctx = (
    f"Recent news sentiment summary: mean score {mean_sent:+.2f} across "
    f"{len(news)} headlines. Top 15 headlines:\n" +
    "\n".join(f"- {h}" for h in top_headlines)
)
fb_label = ("🟢 BULLISH" if mean_sent > 0.15 else
            "🔴 BEARISH" if mean_sent < -0.15 else "🟡 MIXED")
fallback = (f"<b>News tone:</b> {fb_label} (avg sentiment {mean_sent:+.2f}). "
            f"Skim the top headlines below for the dominant story today.")
ai_summary.auto_summarize(st, news_ctx, page_kind="news", fallback_text=fallback)

# 7-day aggregate sentiment
st.subheader("Aggregate market sentiment — last 7 days")
recent = news[news["ts"] >= (pd.Timestamp.utcnow() - pd.Timedelta(days=7))].copy()
if not recent.empty:
    recent["day"] = recent["ts"].dt.tz_convert("UTC").dt.floor("D")
    agg = recent.groupby("day")["sentiment"].agg(["mean", "count"]).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=agg["day"], y=agg["mean"],
        marker_color=["#22C55E" if v > 0 else "#EF4444" for v in agg["mean"]],
        name="Mean sentiment",
    ))
    fig.add_trace(go.Scatter(
        x=agg["day"], y=agg["count"] / max(agg["count"].max(), 1),
        name="Article volume (norm)", yaxis="y2",
        line=dict(color="#FF8C00", dash="dot"),
    ))
    fig.update_layout(
        template="plotly_dark", height=320,
        paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
        yaxis=dict(title="Mean sentiment", range=[-1, 1]),
        yaxis2=dict(title="Volume", overlaying="y", side="right"),
        margin=dict(l=0, r=0, t=20, b=0),
        legend=dict(orientation="h", y=1.05),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# Filter UI
c1, c2, c3, c4 = st.columns(4)
categories = ["All"]
if "category" in news.columns:
    categories += sorted(news["category"].dropna().unique().tolist())
cat_filter = c1.selectbox("Category", categories)
sources = ["All"] + sorted(news["source"].unique().tolist())
src = c2.selectbox("Source", sources)
keyword = c3.text_input("Keyword (e.g. NVDA, fed, earnings)")
sent_range = c4.slider("Sentiment range", -1.0, 1.0, (-1.0, 1.0), 0.1)
only_high_impact = st.checkbox(
    "🔥 Show only high-impact news (Fed, tariffs, geopolitical, CPI, etc.)",
    value=False,
    help="Auto-detected: stories containing keywords like 'Fed', 'Powell', 'tariff', 'war', 'CPI'",
)

filtered = news.copy()
if cat_filter != "All" and "category" in filtered.columns:
    filtered = filtered[filtered["category"] == cat_filter]
if src != "All":
    filtered = filtered[filtered["source"] == src]
if keyword:
    kw = keyword.lower()
    filtered = filtered[
        filtered["title"].str.lower().str.contains(kw, na=False)
        | filtered["summary"].str.lower().str.contains(kw, na=False)
    ]
filtered = filtered[(filtered["sentiment"] >= sent_range[0])
                    & (filtered["sentiment"] <= sent_range[1])]
if only_high_impact and "high_impact" in filtered.columns:
    filtered = filtered[filtered["high_impact"]]

st.subheader(f"Headlines ({len(filtered)})")

def _color_label(label: str) -> str:
    return {
        "VERY BULLISH": "background:#15803D;color:white",
        "BULLISH":      "background:#166534;color:white",
        "NEUTRAL":      "background:#374151;color:#bcc3d6",
        "BEARISH":      "background:#991B1B;color:white",
        "VERY BEARISH": "background:#7F1D1D;color:white",
    }.get(label, "")


for _, row in filtered.head(60).iterrows():
    age = pd.Timestamp.utcnow() - row["ts"]
    age_str = (f"{int(age.total_seconds()/3600)}h ago" if age < pd.Timedelta(days=1)
               else f"{age.days}d ago")
    cat_badge = row.get("category", "")
    impact_badge = " 🔥" if row.get("high_impact", False) else ""
    label_style = _color_label(row["sentiment_label"])
    st.markdown(
        f"<div style=\"background:#11182A;padding:0.7rem;border-left:3px solid #FF8C00;margin-bottom:0.4rem\">"
        f"<div style=\"display:flex;justify-content:space-between;font-size:0.75rem;color:#8a93a6\">"
        f"<span>{row['source']} &middot; {age_str}</span>"
        f"<span style=\"padding:1px 6px;border-radius:3px;{label_style};font-size:0.7rem\">"
        f"{row['sentiment_label']} ({row['sentiment']:+.2f})</span></div>"
        f"<div style=\"margin:0.3rem 0;font-weight:bold;color:#E6E8EE\">"
        f"<a href=\"{row['link']}\" target=\"_blank\" style=\"color:#E6E8EE;text-decoration:none\">"
        f"{row['title']}</a></div></div>",
        unsafe_allow_html=True,
    )
