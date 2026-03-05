# Why Signal Forge "Fails to Load" and How to Fix It

## Research result: the backend is working

Checked live:

- **https://signal-forge-3435.onrender.com/health** → `{"status":"healthy"}`
- **https://signal-forge-3435.onrender.com/** → Landing page loads
- **https://signal-forge-3435.onrender.com/app** → Login page loads
- **https://signal-forge-3435.onrender.com/api/tickers** → Returns SPY, SLV, GLD, AAPL, QQQ, TSLA, NVDA
- **https://signal-forge-3435.onrender.com/api/market-status** → Returns session, countdowns
- **https://signal-forge-3435.onrender.com/api/trade-recommendation/SPY** → Returns full price/signal data

So the app is **not** broken. You do **not** need to start over.

## What’s actually going wrong

1. **Old or cached JavaScript**  
   The dashboard (after login) runs `app.js`. If the browser or Render is serving an old/cached version, you still get "Loading...", "$--", and no updates. New fixes (refresh after add ticker, fallbacks, Promise.allSettled) only apply when the **latest** `app.js` is loaded.

2. **Render cold start**  
   On the free tier, the service sleeps after inactivity. The first request can take 30–60 seconds. If the page or API calls give up before that, the UI never gets data and looks “stuck.”

3. **SESSION_SECRET not set**  
   If `SESSION_SECRET` is missing in Render, login state can be unreliable and the dashboard may not behave correctly.

## Fix (do this, in order)

### 1. Deploy the latest code

- In Cursor/terminal, from the project folder:
  - `git add -A`
  - `git commit -m "Fix dashboard load and ticker refresh"`
  - `git push origin main`
- In **Render**: Dashboard → your **signal-forge** service → **Manual Deploy** → **Deploy latest commit**. Wait until the deploy is **Live**.

### 2. Set SESSION_SECRET on Render

- Render → your **signal-forge** service → **Environment**.
- Add: **SESSION_SECRET** = any long random string (e.g. 32+ characters).
- Save. Render will redeploy; wait for it to finish.

### 3. Hard refresh and test

- Open **https://signal-forge-3435.onrender.com/app** in a **new tab or incognito** (to avoid old cache).
- Log in.
- If the dashboard still shows "Loading..." or "$--", wait **up to 60 seconds** (cold start), then click the **Refresh** button on the page.
- Do a **hard refresh**: **Ctrl+Shift+R** (Windows) or **Cmd+Shift+R** (Mac).

### 4. If it still “fails to load”

- In Render → your service → **Logs**, check for Python errors or 500s.
- In the browser: **F12** → **Network** tab. Reload the dashboard and see if any request to `/api/tickers` or `/api/trade-recommendation/...` is red (failed) or very slow.
- Confirm the **script** tag in the page source (right‑click → View Page Source) loads `app.js?v=...` with a **new** value after a deploy (so cache bust is working).

## Summary

- **Backend:** Working (health, APIs, DB).
- **Do not** start over. Deploy latest code, set `SESSION_SECRET`, hard refresh (and wait for cold start if needed). If it still fails, use Logs + Network to see the real error.
