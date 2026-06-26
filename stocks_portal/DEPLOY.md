# Deploy EquityTerm to Streamlit Community Cloud (free)

You'll get a private URL like `https://equityterm.streamlit.app` that you can
access from your phone, laptop, anywhere. Free tier limits: 1 GB RAM, public
or private app (private = only people you invite by email can see it).

**Time required: 15 minutes the first time.**

---

## Step 1 — Install Git (skip if already installed)

Check by opening a terminal and running:
```bash
git --version
```
If you see a version number, skip ahead. Otherwise:
- **Windows:** https://git-scm.com/download/win  → install with defaults
- **Mac:** runs from Terminal automatically; if not, `xcode-select --install`

---

## Step 2 — Create a private GitHub repo

1. Sign up at https://github.com (free) if you don't have an account.
2. Click the **+** in the top right → **New repository**.
3. Name it `equityterm` (or whatever you want).
4. **Important: choose "Private"**, not Public. This keeps your code yours.
5. Do NOT initialize with README/license — your folder already has files.
6. Click **Create repository**.

You'll see a page with commands. Keep that tab open — you'll use it in Step 4.

---

## Step 3 — Initialize git in your stocks_portal folder

Open a terminal **in your `stocks_portal` folder**. On Windows, hold Shift and
right-click in the folder, then "Open PowerShell window here" or "Open Terminal here".

```bash
git init
git add .
git status   # double-check .env is NOT in the list — only .env.example should be
git commit -m "Initial commit"
```

If `.env` shows up in `git status`, STOP. The `.gitignore` isn't working.
Run `git rm --cached .env` and try again.

---

## Step 4 — Push to GitHub

Copy the commands from your GitHub repo page (Step 2). They look like:

```bash
git remote add origin https://github.com/YOUR_USERNAME/equityterm.git
git branch -M main
git push -u origin main
```

GitHub will ask for your username and a password. The "password" is actually
a **Personal Access Token** — not your real password. Create one at:
https://github.com/settings/tokens → Generate new token (classic) →
check `repo` scope → copy the token → paste as password.

---

## Step 5 — Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io
2. Sign in with your GitHub account (lets Streamlit see your repos).
3. Click **New app**.
4. Pick your `equityterm` repo, branch `main`, main file path `app.py`.
5. Under **Advanced settings → Python version**, choose **3.11**.
6. Click **Deploy**.

First build takes ~3-5 minutes (installing yfinance, plotly, etc.). You'll
see streaming logs. When it's done you'll get a URL like
`https://yourname-equityterm.streamlit.app`.

---

## Step 6 — Add your API keys (CRITICAL)

The app needs your keys to work. Don't push them to GitHub — paste them
into Streamlit's Secrets panel instead.

1. From your deployed app's page, click **⋮ Manage app → Settings → Secrets**.
2. Paste this TOML format (replace with YOUR keys from `.env`):

```toml
FINNHUB_API_KEY = "d7vi6c9r01qldb7g17a0d7vi6c9r01qldb7g17ag"
FMP_API_KEY = "233a61e2636b762fa2b38fe9d237df30"
FRED_API_KEY = ""

GROQ_API_KEY = "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"

GEMINI_API_KEY = "AIzaSyCSmUQ5CQJSLpZlhGckrLo9asrTaM6Gga0"
GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_GROUNDING = "true"
AI_COMPARE_MODE = "true"
```

3. Click **Save**. The app auto-reboots and pulls in the new keys.

---

## Step 7 — Make it private (optional, recommended)

By default the app is public — anyone with the URL can use it (and burn through
your API quotas).

1. From the app page → **⋮ Manage app → Settings → Sharing**.
2. Toggle **Private app**.
3. Paste the email addresses of anyone you want to give access (just yourself
   is fine). They'll need a free Streamlit account at that email.

Now only you can open the URL. Your phone, laptop, anywhere — just log in.

---

## Step 8 — Update the app later

Every time you (or Claude) edit a file:

```bash
git add .
git commit -m "describe what you changed"
git push
```

Streamlit Cloud auto-detects the push and redeploys in ~1 minute. Zero
configuration needed.

---

## Troubleshooting

**App sleeps after 7 days inactivity.** First visit after sleep takes ~30s to
wake. To prevent this, just open it once a week.

**yfinance returns empty data on cloud.** Yahoo aggressively rate-limits cloud
IPs. The aggressive caching in `lib/` mitigates this, but if you see lots of
empty tables, that's why. Workaround: switch heavy queries to Finnhub or FMP
(already wired into `lib/data.py`).

**"Module not found" error.** Some dep is missing from `requirements.txt`.
Check the build logs in Streamlit Cloud and add the missing package.

**API rate limits.** Gemini Pro is 50 req/day. With 8 pages × 2 providers
(compare mode) + 10-min caching, one session refresh = ~16 calls. So 3 full
refreshes per day. Auto-fallback to Flash handles the rest.

---

## Alternative free hosts (if Streamlit Cloud doesn't work for you)

| Host | Pros | Cons |
|------|------|------|
| **Streamlit Cloud** | Native, easy, free private | 1 GB RAM, sleeps |
| **Hugging Face Spaces** | 16 GB RAM, doesn't sleep | Public only on free |
| **Render** | More control, persistent disk | Cold starts ~30s |
| **Fly.io** | Generous free tier | Credit card required |

Streamlit Cloud is the right pick 99% of the time for this app.
