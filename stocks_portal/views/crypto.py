"""
₿ Crypto Cycle — a living decision framework, not a static page.

On launch, lib/crypto_agents.run_pipeline() (cached 15 min):
  data agents  → block-height halving projection, live price, Fear&Greed, funding,
                 ETF flows, tagged news, macro calendar
  recalibrate  → adaptive euphoria threshold from the declining peak-MVRV series
  snapshot     → persists state; "what changed since last visit"
  LLM analyst  → structured morning note from numbers only
  LLM auditor  → second pass flags any claim not traceable to the numbers
Optional: a daily GitHub Actions cron (scripts/refresh_crypto.py) does the same
headless and commits the snapshot, so history accrues even when nobody opens the app.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import crypto_agents as ag, crypto_cycle as cc, model_panel as mp

st.title("₿ Crypto Cycle")
PLAN_FILE = Path(__file__).parent.parent / ".cache" / "crypto_plan.json"
GREEN, RED, AMBER, GREY, BLUE = "#22C55E", "#EF4444", "#FF8C00", "#8a93a6", "#3B82F6"


def _load_plan() -> dict:
    try:
        return json.loads(PLAN_FILE.read_text())
    except Exception:
        return {}


def _save_plan(plan: dict):
    try:
        PLAN_FILE.parent.mkdir(exist_ok=True); PLAN_FILE.write_text(json.dumps(plan))
    except Exception:
        pass


def _card(col, label, value, sub="", color=GREY):
    col.markdown(
        f"<div style='border-left:4px solid {color};padding:8px 12px;margin:4px 0;"
        f"background:rgba(255,255,255,0.03);border-radius:6px'>"
        f"<div style='font-size:12px;color:#8a93a6'>{label}</div>"
        f"<div style='font-size:20px;font-weight:700'>{value}</div>"
        f"<div style='font-size:12px;color:#8a93a6'>{sub}</div></div>", unsafe_allow_html=True)


# ------------------------------------------------------------ controls + pipeline
top = st.columns([1.3, 1.6, 1.4, 1, 0.8])
pick = top[0].radio("Asset", ["BTC", "ETH", "SOL", "XRP", "HYPE", "Other…"], horizontal=True)
asset = pick
if pick == "Other…":
    q = top[1].text_input("Search any coin (name or symbol)", st.session_state.get("coin_query", ""), placeholder="e.g. hyperliquid, sui, link")
    st.session_state["coin_query"] = q
    hits = cc.search_coins(q) if q else []
    if hits:
        labels = [f"{h['symbol']} · {h['name']}" + (f" (#{h['rank']})" if h.get("rank") else "") for h in hits]
        ch = top[1].selectbox("Match", labels, index=0)
        h = hits[labels.index(ch)]
        asset = cc.register_asset(h["symbol"], h["id"], h["name"])
    elif q:
        top[1].caption("No CoinGecko match."); st.stop()
    else:
        st.info("Type a coin name or symbol above."); st.stop()
else:
    top[1].caption(f"{cc.ASSETS.get(asset, {}).get('name', asset)} · Coin Metrics + CoinGecko")
years = top[2].slider("Chart window (years)", 1, 12, 4)
use_llm = top[3].toggle("LLM agents", value=True, help="Analyst + auditor, plus the multi-model panel below")
if top[4].button("Force refresh"):
    st.cache_data.clear()

main, side = st.columns([3.2, 1.25])

R = ag.run_pipeline(asset, use_llm=use_llm, use_panel=st.session_state.get("use_panel", True))
sig, p, meta = R["sig"], R["params"], R["meta"]
if sig is None:
    st.error("Not enough history for this asset (needs ~120 days) or data sources unreachable. Try Force refresh."); st.stop()
df = R["df"]
for n in sig.notes:
    st.caption("ℹ️ " + n)

# ------------------------------------------------------------ SIDE PANEL: news that moves this asset
with side:
    st.markdown("#### 📰 What's moving it")
    web = R.get("web") or {}
    if web.get("text"):
        srcs = " · ".join(f"<a href='{u}' target='_blank'>{(t or u)[:28]}</a>" for t, u in web.get("sources", [])[:5])
        st.markdown(f"<div style='border-left:4px solid {BLUE};padding:8px 10px;background:rgba(59,130,246,0.06);border-radius:6px;font-size:13px'>"
                    f"<b>Web brief</b> <span style='color:{GREY};font-size:11px'>Gemini + Google Search · {web.get('model')}</span><br>"
                    f"{web['text'].replace(chr(10), '<br>')}<br><span style='font-size:11px'>{srcs}</span></div>", unsafe_allow_html=True)
    elif web.get("error"):
        st.caption(f"Web brief unavailable: {web['error'][:80]}")
    news = R["news"]
    if news is None or news.empty:
        st.caption("No headlines fetched (feeds unreachable).")
    else:
        flt = st.multiselect("Filter", ["ASSET", "MACRO", "ETF/FLOWS", "REGULATION", "LIQUIDATION/LEVERAGE", "ON-CHAIN", "SECURITY/RISK"],
                             default=[], label_visibility="collapsed", placeholder="All tags")
        nn = news if not flt else news[news["tags"].fillna("").apply(lambda t: any(f in t for f in flt))]
        if "channel" not in nn.columns:
            nn = nn.assign(channel="direct")
        direct = nn[nn["channel"] == "direct"].head(14)
        indirect = nn[nn["channel"] == "indirect"].head(8)
        def _render(dfn, hdr):
            if dfn.empty:
                return
            st.markdown(f"<div style='font-size:12px;color:{GREY};margin:6px 0 2px'>{hdr}</div>", unsafe_allow_html=True)
            for r in dfn.itertuples():
                tg = f"<span style='color:{AMBER};font-size:11px'>{r.tags}</span> " if r.tags else ""
                ts = f"<span style='color:{GREY};font-size:11px'>{pd.to_datetime(r.time).strftime('%d %b %H:%M') if pd.notna(r.time) else ''}</span>"
                st.markdown(f"<div style='font-size:13px;line-height:1.3;margin:0 0 8px'>{tg}<a href='{r.link}' target='_blank' style='text-decoration:none'>{r.title}</a><br>{ts} · {r.source}</div>", unsafe_allow_html=True)
        _render(direct, "DIRECT — crypto desks")
        _render(indirect, "INDIRECT — macro / Fed / SEC")
    cal = R["calendar"]
    if cal.get("ok") and len(cal["upcoming"]):
        st.markdown(f"<div style='font-size:12px;color:{GREY};margin:10px 0 2px'>DATED CATALYSTS</div>", unsafe_allow_html=True)
        for r in cal["upcoming"].itertuples():
            st.markdown(f"<div style='font-size:13px'>• {r.event} — <b>{r.date}</b> (+{r.days}d)</div>", unsafe_allow_html=True)
    sent = R["sentiment"]
    if sent.get("ok"):
        st.markdown(f"<div style='font-size:12px;color:{GREY};margin:10px 0 2px'>POSITIONING</div><div style='font-size:13px'>"
                    f"Fear&Greed <b>{sent.get('fear_greed','—')}</b> {sent.get('fear_greed_label','')} (7d ago {sent.get('fear_greed_7d_ago','—')})<br>"
                    + (f"Funding {sent.get('funding_8h_pct')}%/8h → {sent.get('funding_read')}" if sent.get('funding_8h_pct') is not None else "Funding n/a")
                    + "</div>", unsafe_allow_html=True)

main.__enter__()

# ------------------------------------------------------------ live header (60s)
@st.fragment(run_every="60s")
def live_header():
    live = cc.live_price(asset)
    s2 = cc.compute_signals(df, asset, live, p) or sig
    st.session_state["crypto_sig"] = s2
    c = st.columns(5)
    chg = live.get("change_24h", np.nan)
    c[0].metric(f"{asset} · {live['source']}", f"${s2.price:,.4g}" if s2.price < 100 else f"${s2.price:,.0f}", f"{chg:+.2f}% 24h" if not np.isnan(chg) else None)
    c[1].metric("vs 200-week MA", f"{s2.ratio:.2f}x" if not np.isnan(s2.ratio) else "n/a", f"MA ${s2.wma200:,.4g}" if not np.isnan(s2.wma200) else "short history", delta_color="off")
    c[2].metric("Days since ATH", f"{s2.days_since_ath}d", "IN BOTTOM WINDOW" if s2.in_bottom_window else f"window {p['win_start']}-{p['win_end']}d", delta_color="off")
    c[3].metric("MVRV (live-scaled)", f"{s2.mvrv:.2f}" if not np.isnan(s2.mvrv) else "n/a", s2.mvrv_state, delta_color="off")
    c[4].metric("Signals", f"BUY {s2.buy_count}/3", f"SELL {s2.sell_count}/2", delta_color="off")
    st.caption(f"{datetime.now(timezone.utc):%H:%M:%S} UTC · price history to {meta['price_end']} · on-chain to {meta['mvrv_end']} · "
               f"agents last ran {R['diff'].get('previous_saved', '—') or 'first run'}")


live_header()
sig = st.session_state.get("crypto_sig", sig)

# ------------------------------------------------------------ what changed
diff = R["diff"]
if diff.get("changes"):
    st.warning("**Changed since last visit:** " + " · ".join(diff["changes"]))
elif not diff.get("first_run"):
    st.info("No signal changes since last snapshot.")

# ------------------------------------------------------------ signal cards
r1 = st.columns(4)
_card(r1[0], "1 · Price vs 200WMA", "n/a (short history)" if np.isnan(sig.wma200) else "BELOW ✅" if sig.below_wma else "above",
      f"0.85x ${sig.band1_lvl:,.4g} · 0.66x ${sig.band2_lvl:,.4g}" if not np.isnan(sig.wma200) else "needs 200 weeks of data", GREEN if sig.below_wma else GREY)
_card(r1[1], "2 · Post-peak clock", "IN WINDOW ✅" if sig.in_bottom_window else f"day {sig.days_since_ath}",
      f"ATH ${sig.ath:,.0f} {sig.ath_date:%Y-%m-%d} · proj. trough {sig.projected_bottom:%Y-%m-%d}", GREEN if sig.in_bottom_window else GREY)
_card(r1[2], "3 · MVRV", sig.mvrv_state, f"{sig.mvrv:.2f} · realized ${sig.realized_price:,.0f}" if not np.isnan(sig.mvrv) else "no on-chain",
      GREEN if sig.mvrv_state == "CAPITULATION" else RED if sig.mvrv_state == "EUPHORIA" else GREY)
_card(r1[3], "Structure", sig.structure, f"S ${sig.support:,.0f} · R ${sig.resistance:,.0f}",
      GREEN if sig.structure.startswith("BULL") else RED if sig.structure.startswith("BEAR") else AMBER)

h = R["halving"]; sent = R["sentiment"]; etf = R["etf"]; recal = R["recal"]
r2 = st.columns(4)
_card(r2[0], "Halving clock · SELL A" + ("" if asset == "BTC" else " (BTC schedule)"),
      "PEAK WINDOW ⚠️" if sig.in_peak_window else f"{sig.days_since_halving}d since",
      (f"next ~{sig.next_halving:%Y-%m-%d} from block {h['height']:,} ({h['drift_vs_static_days']:+d}d vs static)" if h.get("ok") else f"next ~{sig.next_halving:%Y-%m-%d} (static)"),
      RED if sig.in_peak_window else GREY)
_card(r2[1], "500d BUY date (backstop)", "NOW" if sig.in_buy_date else f"in {sig.days_to_buy_date}d", f"{sig.buy_date:%Y-%m-%d}", GREEN if sig.in_buy_date else GREY)
_card(r2[2], "Euphoria threshold (adaptive)", f"MVRV > {p['mvrv_high']}",
      f"peak MVRV {recal.get('peak_mvrv_series')} → next ≈ {recal.get('expected_next_peak_mvrv')}" if recal else "from data", AMBER)
_card(r2[3], "Sentiment / positioning",
      f"F&G {sent.get('fear_greed', '—')} {sent.get('fear_greed_label', '')}",
      (f"funding {sent.get('funding_8h_pct')}%/8h → {sent.get('funding_read')} ({sent.get('funding_source')})" if sent.get("funding_8h_pct") is not None else "funding n/a")
      + (f" · ETF 5d {etf['last5_sum_musd']:+.0f}M" if etf.get("ok") else ""),
      RED if (sent.get("fear_greed") or 50) > 75 else GREEN if (sent.get("fear_greed") or 50) < 25 else GREY)


# ------------------------------------------------------------ plan → verdict
st.subheader("Your written plan")
plan = _load_plan().get(asset, {})
pc = st.columns([1, 1, 2, 1])
mode = pc[0].radio("Position", ["cash", "long"], index=0 if plan.get("mode", "cash") == "cash" else 1, horizontal=True)
if mode == "cash":
    rebuy = pc[1].number_input("Rebuy on daily close >", 0.0, 1e7, float(plan.get("rebuy_close") or 0), 100.0)
    ladder_txt = pc[2].text_input("Ladder buy levels (comma)", ",".join(str(int(x)) for x in plan.get("ladder", [])))
    ladder = [float(x) for x in ladder_txt.replace(" ", "").split(",") if x]
    new_plan = {"mode": "cash", "rebuy_close": rebuy or None, "ladder": ladder}
else:
    stop = pc[1].number_input("Stop", 0.0, 1e7, float(plan.get("stop") or 0), 100.0)
    new_plan = {"mode": "long", "stop": stop or None}
if pc[3].button("Save plan"):
    allp = _load_plan(); allp[asset] = new_plan; _save_plan(allp); st.cache_data.clear(); st.success("Saved — agents will re-run with the new plan.")
for line in cc.verdict(sig, new_plan):
    st.markdown(f"• {line}")

# ------------------------------------------------------------ analyst + auditor
st.subheader("Agent notes")
if R["analysis"]:
    a, b = st.columns([3, 2])
    a.markdown(f"<div style='border-left:4px solid {BLUE};padding:10px 14px;background:rgba(59,130,246,0.06);border-radius:6px'>"
               f"<b>Analyst</b><br>{R['analysis'].replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
    aud = R["audit"] or "(auditor unavailable)"
    col = GREEN if aud.startswith("AUDIT PASS") else RED
    b.markdown(f"<div style='border-left:4px solid {col};padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:6px'>"
               f"<b>Auditor</b><br>{aud.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
else:
    st.info("Set GROQ_API_KEY or GEMINI_API_KEY (free tiers) in Secrets to enable the analyst + auditor agents. "
            "Everything above is deterministic and already live.")
with st.expander("Context the agents were given (numbers only)"):
    st.code(R["context"] or "—")

# ------------------------------------------------------------ multi-model panel
st.subheader("Model panel — same numbers, every model, scored over time")
st.session_state["use_panel"] = st.toggle("Run the panel on refresh", value=st.session_state.get("use_panel", True))
panel = R.get("panel") or []
if panel:
    cols = st.columns(min(3, len(panel)))
    for i, r in enumerate(panel):
        with cols[i % len(cols)]:
            ok = r.get("audit_pass"); col = GREEN if ok else RED if ok is False else GREY
            head = f"<b>{r['label']}</b> · {r['latency_s']}s · bias {r.get('bias_7d')} c{r.get('conviction')} · key {r.get('key_level')}"
            if r.get("resolved_note"):
                head += f"<br><span style='color:{AMBER};font-size:11px'>{r['resolved_note']}</span>"
            body = (r["note"] or f"error: {r['error']}").replace(chr(10), "<br>")
            st.markdown(f"<div style='border-left:4px solid {col};padding:8px 12px;background:rgba(255,255,255,0.03);border-radius:6px;font-size:13px;max-height:420px;overflow:auto'>{head}<br><br>{body}</div>", unsafe_allow_html=True)
            if r.get("audit"):
                with st.expander("auditor"):
                    st.write(r["audit"])
else:
    st.info("No panel notes: add keys (GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, NVIDIA_API_KEY …) in Secrets and enable models in the roster below.")

lb = mp.score(df["price"], asset)
if not lb.empty:
    st.markdown("**Leaderboard** — accuracy_7d = realized 7-day direction vs each note's bias (flat = |move| < 2%); audit_pass = claims traceable to context.")
    st.dataframe(lb, use_container_width=True, hide_index=True)
    st.caption("Needs ~30+ scored notes per model before differences mean anything; daily cron runs build this even without visits.")

with st.expander("Model roster (free IDs rotate — a broken ID only errors its own card)"):
    roster = mp.load_roster()
    rdf = pd.DataFrame(roster)
    keys = {p: bool(mp._key(v["key"])) for p, v in mp.PROVIDERS.items()}
    st.caption("Keys present: " + ", ".join(f"{k}={'✅' if v else '—'}" for k, v in keys.items()))
    edited = st.data_editor(rdf, num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("Save roster"):
        mp.save_roster(edited.to_dict("records")); st.cache_data.clear(); st.success("Roster saved — refresh to run.")
    if st.button("List OpenRouter ':free' models now"):
        st.write(mp.openrouter_free_models() or "unreachable")


# ------------------------------------------------------------ chart
st.subheader("Chart")
cut = df.index[-1] - pd.Timedelta(days=365 * years)
d = df[df.index >= cut]
wma = df["price"].rolling(p["wma_days"]).mean()[df.index >= cut]
fig = go.Figure()
fig.add_trace(go.Scatter(x=d.index, y=d["price"], name=asset, line=dict(color="#e5e7eb", width=1.5)))
if wma.notna().any():
    fig.add_trace(go.Scatter(x=wma.index, y=wma, name="200-week MA", line=dict(color="#f59e0b", width=2)))
    fig.add_trace(go.Scatter(x=wma.index, y=wma * p["band1"], name="0.85x", line=dict(color="#f59e0b", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=wma.index, y=wma * p["band2"], name="0.66x", line=dict(color="#ef4444", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=d.index, y=np.where(d["price"] < wma, d["price"], np.nan), mode="markers", name="below 200WMA", marker=dict(color=GREEN, size=4)))
fig.add_vrect(x0=sig.ath_date + pd.Timedelta(days=p["win_start"]), x1=sig.ath_date + pd.Timedelta(days=p["win_end"]),
              fillcolor=BLUE, opacity=0.12, line_width=0, annotation_text="post-peak window")
for hv in cc.HALVINGS + [sig.next_halving]:
    if hv and cut <= hv <= d.index[-1] + pd.Timedelta(days=800):
        fig.add_vline(x=hv, line=dict(color=GREY, dash="dot"), annotation_text="halving")
        fig.add_vline(x=hv - pd.Timedelta(days=p["lead_days"]), line=dict(color=GREEN, dash="dash"), annotation_text="-500d")
        fig.add_vline(x=hv + pd.Timedelta(days=p["lag_days"]), line=dict(color=RED, dash="dash"), annotation_text="+500d")
        fig.add_vrect(x0=hv + pd.Timedelta(days=p["peak_start"]), x1=hv + pd.Timedelta(days=p["peak_end"]), fillcolor=RED, opacity=0.08, line_width=0)
fig.add_hline(y=sig.resistance, line=dict(color=RED, width=1), annotation_text=f"R {sig.resistance:,.0f}")
fig.add_hline(y=sig.support, line=dict(color=GREEN, width=1), annotation_text=f"S {sig.support:,.0f}")
fig.update_layout(template="plotly_dark", height=520, yaxis_type="log", margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.05))
st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------ snapshot history
hist = ag.history()
if len(hist) > 2:
    with st.expander("Snapshot history (every agent run)"):
        st.line_chart(hist.set_index("saved")[["ratio", "mvrv"]])
        st.dataframe(hist.tail(30).iloc[::-1], use_container_width=True, hide_index=True)

# ------------------------------------------------------------ evidence
ev = R["evidence"]
with st.expander("📚 Evidence — recomputed from the data this session", expanded=False):
    if not ev:
        st.info("No evidence available.")
    else:
        st.caption(f"Coin Metrics daily {ev['data_start']} → {ev['data_end']} ({ev['n_days']:,} days). "
                   "'episodes' = separate runs of the condition — the honest sample size.")
        t = ev["signals"].copy(); t["pct_positive"] = t["pct_positive"].round(0); t["median"] = t["median"].round(0)
        st.dataframe(t, use_container_width=True, hide_index=True)
        st.markdown("Buy-side signals have near-perfect forward records on ~20–27 episodes; the baseline row shows any day was "
                    "positive ~75% of the time, so part of every record is drift. A fixed MVRV threshold alone is **not** a good "
                    "exit; the post-halving peak window is the strongest exit evidence (3–4 episodes), sharpened by MVRV above "
                    "the adaptive threshold inside it.")
        if not ev["troughs"].empty:
            st.dataframe(ev["troughs"], use_container_width=True, hide_index=True)
        if not ev["halving"].empty:
            st.dataframe(ev["halving"], use_container_width=True, hide_index=True)

st.caption("Sources: Coin Metrics Community, CoinGecko, mempool.space, alternative.me, Binance/OKX public, Farside, crypto RSS. "
           "Agents fail quietly and label their source; a missing card means a source was unreachable, not that the signal is off. Not financial advice.")

main.__exit__(None, None, None)
