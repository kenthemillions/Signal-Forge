# Get Signal Forge Live on Render

Code is pushed to GitHub (commit: deploy-ready). To get https://signal-forge-3435.onrender.com/app live:

## 1. Trigger a new deploy on Render

- Go to **https://dashboard.render.com**
- Open your **signal-forge** web service
- Click **"Manual Deploy"** → **"Deploy latest commit"**  
  (This forces a new build even if auto-deploy didn’t run.)

## 2. Required environment variable

In the same service, go to **Environment** and add:

- **SESSION_SECRET** = any long random string (e.g. `openssl rand -hex 24`)  
  Without this, login sessions won’t persist and the app can misbehave.

## 3. After deploy (2–5 min)

- **Health:** Open **https://signal-forge-3435.onrender.com/health** — should show `{"status":"healthy"}`.
- **App:** Open **https://signal-forge-3435.onrender.com/app** — you should see the login page; after login, the dashboard loads (first load may take 30–60 s on cold start).
- **Hard refresh:** Use **Ctrl+Shift+R** (Windows) or **Cmd+Shift+R** (Mac) so the browser loads the latest JS.

## 4. What’s connected

- **Financial data:** yfinance (market data, prices, indicators).
- **Charts:** Dashboard chart + indicators from `/api/market-data` and `/api/indicators`.
- **AI / Coach:** Smart Coach (rule-based + optional DeepSeek) via `/api/coach`.
- **Real-time:** WebSockets (SocketIO) for price/signal updates when the server is running.
- **APIs:** Tickers, market status, trade recommendation, premarket, scalping levels, multi-timeframe, options flow — all wired and resilient (fallbacks if one fails).

If the dashboard stays on “Connecting…” or “—”, wait for cold start then click **Refresh** on the page.
