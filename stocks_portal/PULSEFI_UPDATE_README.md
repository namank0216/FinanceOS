# PulseFi update — Crypto Cycle + Funnel (Sep 2026)

## 1. Files (drop into `stocks_portal/`)

| file | what |
|---|---|
| `lib/crypto_cycle.py` | BTC/ETH engine: Coin Metrics history (+ CoinGecko extension), live price, all signals, structure S/R, **evidence recomputed in-app** |
| `lib/crypto_agents.py` | **Agent layer** run on page launch: halving projection from block height, Fear&Greed + funding, tagged crypto news, FOMC/CPI/expiry calendar, ETF flows (best-effort), adaptive recalibration, state snapshot + change detection, LLM analyst + auditor |
| `views/crypto.py` | Crypto Cycle page — built on the agent pipeline; live header auto-refreshes every 60 s |
| `scripts/refresh_crypto.py` + `.github/workflows/crypto_refresh.yml` | Daily headless refresh (GitHub Actions cron, free) that commits the snapshot so history accrues without visits |
| `lib/funnel.py` | Pond → Fish → Focus → Review engine, gates with literature citations, correlation kill, sizing |
| `views/funnel.py` | Funnel page (5 tabs) |

## 2. `app.py` — add two NAV lines

```python
st.Page("views/crypto.py", title="Crypto Cycle", icon="₿"),
st.Page("views/funnel.py", title="Funnel",       icon="🎣"),
```

## 3. `requirements.txt` — bump Streamlit (needed for `st.fragment(run_every=...)`)

```
streamlit>=1.40
```

No new packages otherwise (requests, pandas, numpy, plotly already present).
Create `.cache/` (already used by universe.py) — plan and theses persist there.
On Streamlit Cloud that folder resets on redeploy; for durable storage move the two
JSON files to `st.secrets`-backed GitHub Gist or a free Supabase table (5 lines of code).

## 3b. How the page stays alive (agents)

On every launch (cached 15 min, "Force refresh" button clears it) `crypto_agents.run_pipeline()`:

1. **halving_agent** — reads the live block height (mempool.space → blockchain.info), projects the
   next halving from the observed block interval, and feeds it into the 500-day dates. The static
   2028-03-25 assumption is only a fallback; the card shows the drift in days.
2. **recalibrate** — derives the euphoria threshold from the declining peak-MVRV series
   (5.06 → 4.25 → 2.72 → 2.22; next expected ≈ 1.7) → threshold = max(2.0, 0.85 × last peak).
   `EUPHORIA` is only labelled inside the post-halving peak window; outside it the same reading is `ELEVATED`.
3. **sentiment_agent / etf_agent / calendar_agent / news_agent** — positioning, flows, dated catalysts,
   and 48h headlines tagged MACRO / ETF-FLOWS / REGULATION / LIQUIDATION / ON-CHAIN / SECURITY.
4. **snapshot** — writes `.cache/crypto_state.json` + appends `crypto_state_history.jsonl`; the page opens
   with **"Changed since last visit"** (signal flips, >5% price moves, new ATH → clock reset).
5. **analyst_agent → auditor_agent** (LLM, optional) — the analyst writes a 4-section note from numbers
   only; the auditor is a second model call that must trace every claim back to the context and prints
   `AUDIT PASS` or the unsupported claims. Generator + verifier is the cheapest way to make LLM notes
   trustworthy; the raw context is shown in an expander so you can check both.

Every agent fails quietly and labels its source. A missing card means a source was unreachable.

**Streamlit Cloud has no cron**, so the GitHub Actions workflow runs the same pipeline daily at 13:15 UTC
(free tier is plenty) and commits the snapshot files; Streamlit redeploys on push, so the app opens
already refreshed and the history chart builds day by day. Add `GROQ_API_KEY`/`GEMINI_API_KEY` as repo
secrets if you want the LLM notes in the cron run too.

## 4. Real-time data — what's actually free, and the trade-offs

| need | source | cost | limits / notes |
|---|---|---|---|
| Crypto live price | **CoinGecko** `simple/price` | free, no key | ~30 req/min; used here with 60 s cache |
| Crypto history + on-chain (MVRV, realized cap) | **Coin Metrics Community** CSV on GitHub | free, no key | daily, can lag days–weeks; we extend price with CoinGecko `market_chart` |
| Crypto tick/websocket | Coinbase / Binance public WS | free | Streamlit can't hold a socket; poll instead (below) |
| Stock quotes (delayed-free) | yfinance (unofficial) | free | rate-limits on Cloud; keep Stooq fallback |
| Stock quotes, real-time, websocket | **Finnhub** free tier | free key | 60 req/min, US stocks real-time trades; already wired in `lib/data.py` |
| Fundamentals / estimates / revisions | **FMP** free tier | free key | 250 req/day — enough for the Funnel's survivors only (that's why F1 caps lookups) |
| Cheap upgrade if you outgrow free | Polygon Starter (~$29/mo) or FMP Starter (~$22/mo) | paid | unlimited-ish, official, reliable on Cloud |

**The "live pointers" trick without websockets:** Streamlit ≥1.37 `@st.fragment(run_every="60s")`
re-runs only that block on a timer (used in `views/crypto.py` for the header). Set 15–30 s on
stock pages if Finnhub key is present; don't go below 10 s on free tiers.

## 5. AI summaries — free/cheap

Already supported by `lib/ai_summary.py`; set ONE key in Streamlit Secrets:

- **Groq** (Llama 3.3 70B) — free tier, fast, fine for briefings. Best zero-cost pick.
- **Gemini 2.5 Flash** — free tier, larger context; set `GEMINI_MODEL=gemini-2.5-flash`.
- **Anthropic Claude Haiku** — pennies per briefing, best instruction-following; `ANTHROPIC_API_KEY`.
- **Ollama** — free/local, only if you self-host (not on Streamlit Cloud).

The Crypto and Funnel pages pass numbers-only context and force the model to cite them; if you
see a briefing that invents a figure not on the page, that's the model — switch provider.

## 6. Methodology changes vs. the chat (evidence-driven corrections)

1. **Sell-side MVRV fixed.** In-app backtest: MVRV > 3 alone was a *bad* exit (67% of those days
   were higher a year later) and peak MVRV fell 5.1 → 4.3 → 2.7 → 2.2 across cycles, so a fixed 3.0
   never fired in 2021 or 2025. Sell signal is now: post-halving peak window (primary, 1y fwd median
   −48%, 19% positive) + MVRV > **2.5 inside** the window (−58%). Update the Pine indicator's
   "Euphoria level" input to 2.5 accordingly, and treat the peak window as the primary exit.
2. **Sample sizes shown as episodes, not days.** Every stat carries an episode count (20–27 for
   the buy signals, 3–4 for the cycle timing) so the UI can't overstate confidence.
3. **Baseline row.** Every evidence table includes "ANY day" so you can see how much of a signal's
   record is just Bitcoin's drift (~75% of days positive 1y forward).
4. **Naming.** "Stage 1–4" stays Weinstein (price structure). The selection pipeline is
   "Funnel F1–F4" to avoid the collision.
5. **Halving clock applied to ETH** on the BTC schedule (its 2017/2021 peaks landed inside
   BTC's window) and labeled as such; ETH gets no 500-day rule of its own.
6. **Funnel gates cite literature, not memory** — and the README says plainly the app doesn't
   yet re-derive factor premia itself. That factor backtest on the app's own universe is the
   next honest step if you want the Funnel to match the Crypto page's standard.

Not financial advice. 3–4 crypto cycles and ~30 years of factor data are tilted odds, not rules.
