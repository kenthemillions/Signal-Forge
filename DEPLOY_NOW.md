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

## 4. (Optional) Alpaca for accurate live data

To use **Alpaca** instead of Yahoo for market data (recommended for correct ticker-specific data on Render):

- In Render **Environment**, add:
  - **ALPACA_API_KEY** = your Alpaca API key
  - **ALPACA_SECRET_KEY** = your Alpaca secret key
- Redeploy. When both are set, Signal Forge uses Alpaca for bars and quotes; yfinance remains for options/news/earnings.

## 5. What’s connected

- **Financial data:** **Alpaca** (if `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` are set) or **Yahoo (yfinance)** when Alpaca is not configured. Same data source is used for charts, institutional flow, Fib/ATR, and coach.
- **Charts:** Dashboard chart + indicators from `/api/market-data` and `/api/indicators` (1m, 2m, 5m, 15m, 1h, 4h).
- **Institutional flow:** Buy/Sell/WAIT with entry, stop, target — uses same data as dashboard; 5m, 15m, 1h, 4h timeframes.
- **Fibonacci & ATR:** Scalping levels per ticker (best retracement zone, ATR move, Fib levels) from `/api/scalping-levels/<symbol>`.
- **AI / Coach:** Smart Coach (rule-based) + **DeepSeek** when you add your API key in Coach → AI Settings and enable “Enable AI responses”. Key is stored in browser only.
- **Real-time:** WebSockets (SocketIO) for price/signal updates when the server is running.
- **APIs:** Tickers, market status, trade recommendation, premarket, scalping levels, multi-timeframe, options flow — all wired and resilient (fallbacks if one fails).

If the dashboard stays on “Connecting…” or “—”, wait for cold start then click **Refresh** on the page.

**Ticker mismatch (e.g. SLV selected but SPY numbers):** The app now ignores late API responses so the selected ticker’s data is not overwritten. Using Alpaca (step 4) also improves data consistency on Render.

**Full site breakdown:** See **SITE_SYNOPSIS.md** for how each area works (traffic light, charts, Fib/ATR, institutional, scanners, coach) and what was fixed.
