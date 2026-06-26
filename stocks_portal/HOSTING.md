# Hosting EquityTerm publicly — safe, legal, and free

You can share this with friends/colleagues without spending money. Here's how to do it correctly.

---

## 1. The hosting options (cheapest first)

### 🆓 Streamlit Community Cloud (recommended for free hosting)

- **Cost:** Free for public apps.
- **What you get:** Public URL like `your-app.streamlit.app`, auto-deploy from GitHub, 1GB RAM.
- **Setup:**
  1. Push your `stocks_portal` folder to a public GitHub repo (or private — paid tiers).
  2. Sign in at https://share.streamlit.io with your GitHub account.
  3. Point it at your repo's `app.py`. Done.
  4. Add API keys via the "Secrets" panel (NOT in the repo).

**Best for:** sharing with 5-50 people. Cold starts after inactivity (~30s on first visit).

### 🆓 Hugging Face Spaces

- **Cost:** Free for public Spaces.
- **What you get:** Persistent URL on hf.co, 16GB RAM (more than Streamlit Cloud).
- **Setup:** create a Space → choose Streamlit template → upload files.

**Best for:** if you outgrow Streamlit Cloud's resource limits.

### 💸 Render / Railway / Fly.io ($5-10/month)

If your app gets popular: pay-as-you-go cloud hosting. Same Streamlit Docker container, no cold starts, custom domain. Worth it once you have 100+ regular users.

---

## 2. API key safety in production

**Never commit `.env` or `.env.example` with real keys to a public GitHub repo.** Even if you delete it later, the keys are forever in git history.

**The right pattern:**

1. Add `.env`, `.env.example`, and `.cache/` to `.gitignore` before your first push.
2. Put real keys in your hosting provider's secrets panel:
   - **Streamlit Cloud:** Settings → Secrets → paste in TOML format
     ```toml
     FINNHUB_API_KEY = "your_key"
     FMP_API_KEY = "your_key"
     GROQ_API_KEY = "your_key"
     ```
   - **Hugging Face Spaces:** Settings → Variables and secrets
   - **Render/Railway:** Environment Variables panel
3. Streamlit auto-loads from `st.secrets` — but our `lib/data.py` reads `os.environ`. Most platforms inject secrets into env vars automatically, so it just works.

---

## 3. Legal & regulatory considerations

This is **important** if you're hosting publicly. I'm not a lawyer; consult one for your jurisdiction. General observations for US users:

### What's safe

- Personal-use research dashboards.
- Sharing with friends explicitly stating "this is not advice."
- Educational content that explains methodology and shows historical data.
- Subscription-based services that **publish methodology, not specific buy/sell calls**.

### What gets you in trouble

- **Personalised investment recommendations** to non-clients without being a registered investment advisor (RIA). The bar in the US is "providing advice for compensation." The SEC and state regulators take this seriously.
- **Performance claims** ("this system returned X%") without a verified track record.
- **Redistribution of paid data** that violates ToS (Bloomberg, Reuters, paid feeds). yfinance is a gray area — Yahoo's ToS prohibits scraping, but the library is widely used. CoinGecko's free tier explicitly allows attribution-based redistribution.
- **Soliciting deposits or operating as a broker** without licensing.

### Concrete safety steps

1. **Add a prominent disclaimer on every page** (the existing footer is a start; beef it up):
   > *"EquityTerm is a research and decision-support tool, not investment advice. Past performance does not guarantee future results. The author is not a registered investment advisor. You alone are responsible for your trading decisions. Consult a licensed advisor for personalised guidance."*
2. **Don't recommend specific securities** in marketing materials. The dashboard can show what its rules SAY about a stock, but you don't endorse the rules as financial advice.
3. **Don't take fees** for personalised picks unless you're an RIA. Generic "subscription to access the tool" is different and generally OK.
4. **AI-generated commentary** — make it doubly clear this is educational. The AI summaries on each page already include that caveat. Keep it.
5. **Use Terms of Service** if you charge anything: Streamlit Cloud lets you add a Privacy Policy and ToS link.

### EU/UK considerations

GDPR applies if any user is in the EU/UK. The current app stores nothing about users (no accounts, no tracking) so you're largely fine. If you add user accounts or analytics, you need a privacy policy, cookie banner, and data-deletion mechanism.

---

## 4. Authentication (if you want a private deployment)

Free options to gate access:

- **Streamlit Cloud (paid Teams plan):** SSO + access control built-in.
- **streamlit-authenticator** (free Python package): username/password with hashed creds in a YAML file. Easy to add.
- **Cloudflare Access** in front of your Render/Fly deployment: free for up to 50 users, OAuth via Google/GitHub.
- **HTTP basic auth via reverse proxy:** simplest. nginx + a single password.

---

## 5. AI provider cost guide (per the AI summary buttons)

| Provider | Tier | Cost | Speed | Quality |
|---|---|---|---|---|
| **Groq** | Free | 30 req/min | ⚡⚡⚡ very fast | High (Llama 70B) |
| **Ollama (local)** | Free | runs on your machine | Variable | Decent (Llama 3.2) |
| **Anthropic Claude Haiku** | Paid | ~$0.25 / 1M input tokens | Fast | Excellent |
| **Anthropic Claude Sonnet** | Paid | ~$3 / 1M input tokens | Fast | Best for nuance |
| **OpenAI GPT-4o-mini** | Paid | ~$0.15 / 1M input tokens | Fast | Excellent |

**Worked cost example:** if 10 users each click "Ask AI" on 5 pages per day = 50 calls/day at ~600 tokens per call = 30k tokens/day. Anthropic Haiku: ~$0.30/month. Groq/Ollama: free.

**My recommendation for your use case:** start with **Groq free tier**. If you need higher quality or are public-hosting and Groq's rate limits become a constraint, switch to Anthropic Haiku — it's the best price/performance for short market commentary.

---

## 6. Deployment checklist (Streamlit Cloud)

1. ✅ Add `.env`, `.env.example`, `.cache/`, `cryptoterm.db` to `.gitignore`
2. ✅ `pip freeze > requirements.txt` (or use the existing one)
3. ✅ `git init && git add . && git commit -m "Initial"`
4. ✅ Create GitHub repo, push: `git push -u origin main`
5. ✅ At https://share.streamlit.io: New app → point at repo → `app.py`
6. ✅ Add secrets in the Streamlit dashboard (NOT in repo)
7. ✅ Verify live URL works
8. ✅ Add a footer disclaimer and link to Terms / Privacy
9. ✅ Share the URL

You're live, legal, and free.
