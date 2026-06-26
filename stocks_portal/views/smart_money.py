"""Smart Money — Dataroma superinvestors + Congressional trades + insider activity."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import ai_summary, data, explainers, smart_money, universe

st.title("💰 Smart Money Tracker")
st.caption("Superinvestor portfolios · Congressional trades · Corporate insiders. The institutional lens.")
tab1, tab2, tab3 = st.tabs(["🏛 Superinvestors (Dataroma)",
                            "🇺🇸 Congressional Trades",
                            "🏢 Corporate Insiders"])

# ============================================================
# TAB 1: Dataroma superinvestors
# ============================================================
with tab1:
    st.subheader("🏛 Dataroma Grand Portfolio")
    st.caption("Official aggregated portfolio across ALL tracked superinvestors — "
               "directly from [dataroma.com/m/g/portfolio.php](https://dataroma.com/m/g/portfolio.php?pct=0&o=c). "
               "Updated quarterly from 13F filings.")

    with st.spinner("Pulling Dataroma Grand Portfolio (cached 12h)…"):
        grand = smart_money.get_grand_portfolio()

    if not grand.empty:
        st.dataframe(grand.head(75), use_container_width=True, hide_index=True)
        st.markdown("""
        **How to use this.** This is the closest thing to a "smart-money index" that exists for free.
        Every stock here is held by multiple legendary managers who built their reputations on getting
        these calls right over decades. Names with high # of holders + recent buying activity are the
        highest-conviction setups when they also pass your bottom-up factor screen.
        """)
    else:
        st.warning("Could not load Grand Portfolio. Dataroma may have changed its HTML structure.")

    st.divider()

    st.subheader("Consensus picks — local aggregation (top 10 managers)")
    st.caption("My own aggregation across the curated list of 18 superinvestors below. "
               "Cross-check against the Grand Portfolio above for consistency.")

    with st.spinner("Aggregating across managers (first run takes ~30s, then cached 12h)…"):
        consensus = smart_money.get_top_holdings_aggregate(top_n_managers=10, top_n_holdings=30)

    if not consensus.empty:
        # Visual
        fig = go.Figure(go.Bar(
            x=consensus["n_managers"], y=consensus["ticker"],
            orientation="h",
            marker_color="#FF8C00",
            text=consensus["n_managers"], textposition="outside",
        ))
        fig.update_layout(
            template="plotly_dark", height=600,
            paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
            xaxis=dict(title="# of tracked superinvestors holding"),
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(consensus, use_container_width=True, hide_index=True)
    else:
        st.warning("Could not pull consensus holdings. Dataroma may have changed its HTML structure.")

    st.divider()

    st.subheader("Per-manager portfolio")
    mgr_choice = st.selectbox(
        "Select manager",
        options=list(smart_money.SUPERINVESTORS.keys()),
        format_func=lambda c: f"{c} — {smart_money.SUPERINVESTORS[c]}",
        index=0,
    )

    with st.spinner("Pulling Dataroma…"):
        holdings = smart_money.get_holdings(mgr_choice)

    if holdings.empty:
        st.info("Holdings unavailable for this manager.")
    else:
        st.markdown("**Current holdings (full table — sortable)**")
        st.dataframe(holdings, use_container_width=True, hide_index=True)

        # Build the activity view from the same holdings frame (Dataroma's
        # dedicated activity page parses badly; the RecentActivity column on
        # holdings is the clean source of the same info).
        activity = smart_money.get_recent_activity(mgr_choice)
        if not activity.empty:
            st.markdown("**Recent moves only — buys / sells / adds / reductions**")
            st.dataframe(activity, use_container_width=True, hide_index=True)

    st.markdown("""
    **How to use this lens.** Consensus picks are stocks where multiple legendary investors
    independently arrived at the same conclusion. That's a signal worth weighting — not because
    they're always right, but because their analysis is independent of each other and of you.
    Combine with your composite score: a stock that scores high on your factors *and* shows up on
    multiple superinvestor portfolios is a high-conviction setup.
    """)

# ============================================================
# TAB 2: Congressional trades
# ============================================================
with tab2:
    st.subheader("US House STOCK Act disclosures — last 60 days")
    st.caption("Required disclosures within 45 days under the STOCK Act. Data: housestockwatcher.com")

    with st.spinner("Pulling Congressional trade dataset…"):
        ctrades = smart_money.get_congress_trades(days=60)

    if ctrades.empty:
        st.warning("Could not pull Congressional trades. Source may be temporarily unavailable.")
    else:
        st.success(f"Loaded {len(ctrades):,} Congressional transactions over the period.")

        # Aggregate by ticker
        agg = smart_money.aggregate_congress_by_ticker(ctrades, days=60)
        if not agg.empty:
            st.markdown("**Most-traded tickers in Congress**")
            top = agg.head(25).copy()
            fig = go.Figure(go.Bar(
                x=top["ticker"], y=top["n_trades"],
                marker_color=["#22C55E" if n > 0 else "#EF4444" if n < 0 else "#8a93a6"
                              for n in top["net"]],
                text=[f"{r['buys']}B/{r['sells']}S" for _, r in top.iterrows()],
                textposition="outside",
            ))
            fig.update_layout(
                template="plotly_dark", height=400,
                paper_bgcolor="#0A0E1A", plot_bgcolor="#0A0E1A",
                yaxis=dict(title="Trades (last 60d)"),
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(top, use_container_width=True, hide_index=True)

        st.divider()

        # Filter UI
        st.markdown("**Recent transactions — filterable**")
        f1, f2, f3 = st.columns(3)
        ticker_filter = f1.text_input("Ticker filter", placeholder="e.g. NVDA")
        rep_filter = f2.text_input("Politician filter", placeholder="e.g. Pelosi")
        type_filter = f3.selectbox("Type",
                                   ["All", "Purchase", "Sale", "Exchange"], index=0)

        filtered = ctrades.copy()
        if ticker_filter and "ticker" in filtered.columns:
            filtered = filtered[filtered["ticker"].astype(str).str.contains(
                ticker_filter.upper(), na=False)]
        if rep_filter and "representative" in filtered.columns:
            filtered = filtered[filtered["representative"].astype(str).str.contains(
                rep_filter, case=False, na=False)]
        if type_filter != "All" and "type" in filtered.columns:
            filtered = filtered[filtered["type"].astype(str).str.contains(
                type_filter.lower(), case=False, na=False)]

        # Sort by date descending
        if "transaction_date" in filtered.columns:
            filtered = filtered.sort_values("transaction_date", ascending=False)

        st.dataframe(filtered.head(100), use_container_width=True, hide_index=True)

# ============================================================
# TAB 3: Corporate insiders
# ============================================================
with tab3:
    st.subheader("Corporate insider activity (Form 4)")

    if not data.has_finnhub():
        st.info("Add a free Finnhub API key to enable insider data. "
                "Sign up at https://finnhub.io (60 seconds, no credit card).")
    else:
        ins_query = st.text_input("Ticker or company name", value="NVDA",
                                  placeholder="e.g. NVDA, Nvidia")
        ins_ticker, _ = universe.resolve_ticker(ins_query) if ins_query else (None, [])
        if ins_ticker:
            with st.spinner("Pulling Finnhub insider data…"):
                ins_df = data.fh_insider(ins_ticker)
            if not ins_df.empty:
                ins_df = ins_df.sort_values("transactionDate", ascending=False)

                # Aggregate net buys/sells last 90 days
                cutoff = pd.Timestamp.now() - pd.Timedelta(days=90)
                recent = ins_df[ins_df["transactionDate"] >= cutoff]
                if not recent.empty:
                    buys = recent[recent["transactionCode"] == "P"]["share"].sum()
                    sells = recent[recent["transactionCode"] == "S"]["share"].sum()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("90d insider buys (shares)", f"{int(buys):,}")
                    c2.metric("90d insider sells (shares)", f"{int(sells):,}")
                    net = buys - abs(sells)
                    c3.metric("Net", f"{int(net):,}",
                              "Buying" if net > 0 else "Selling")

                st.dataframe(ins_df.head(50), use_container_width=True, hide_index=True)

                st.markdown("""
                **Reading insider activity.**
                - Code **P** = Open-market purchase. Strong positive signal — insiders rarely
                  buy with their own money for "diversification."
                - Code **S** = Open-market sale. Mildly negative but noisy (vesting, taxes,
                  diversification all show up here).
                - Code **F** = Tax withholding on equity comp. Ignore.
                - Cluster buying (multiple execs buying simultaneously) is the strongest insider signal.
                """)
            else:
                st.info("No recent insider activity for this ticker.")
