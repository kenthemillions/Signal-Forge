# Get Signal Forge Live on Render

**Fresh deployments:** Push to GitHub (see step below), then on Render click **Manual Deploy → Deploy latest commit** so the site builds and runs the latest code. If Auto-Deploy is on for `main`, each push to GitHub starts a new deploy automatically.

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

- **Financial data:** **Yahoo Finance (yfinance)** only. All market data from Yahoo; same source for charts, institutional flow, Fib/ATR, and coach.
- **Charts:** Dashboard chart + indicators from `/api/market-data` and `/api/indicators` (1m, 2m, 5m, 15m, 1h, 4h).
- **Institutional flow:** Buy/Sell/WAIT with entry, stop, target — uses same data as dashboard; 5m, 15m, 1h, 4h timeframes.
- **Fibonacci & ATR:** Scalping levels per ticker (best retracement zone, ATR move, Fib levels) from `/api/scalping-levels/<symbol>`.
- **AI / Coach:** Smart Coach (rule-based) + **DeepSeek** when you add your API key in Coach → AI Settings and enable “Enable AI responses”. Key is stored in browser only.
- **Real-time:** WebSockets (SocketIO) for price/signal updates when the server is running.
- **APIs:** Tickers, market status, trade recommendation, premarket, scalping levels, multi-timeframe, options flow — all wired and resilient (fallbacks if one fails).

If the dashboard stays on “Connecting…” or “—”, wait for cold start then click **Refresh** on the page.

**Ticker mismatch (e.g. SLV selected but SPY numbers):** The app now ignores late API responses so the selected ticker’s data is not overwritten. 
**Full site breakdown:** See **SITE_SYNOPSIS.md** for how each area works (traffic light, charts, Fib/ATR, institutional, scanners, coach) and what was fixed.

---

## 6. What was fixed (ensure these are deployed)

- **Data & prices:** data_fetcher uses history + fast_info + info; correct current/premarket/after-hours and session.
- **Charts:** Cache kept; 1m, 2m, 5m, 15m, 1h, 4h; ticker consistency (ignores late responses).
- **Traffic light:** Green=BUY, Red=SELL, Yellow=WAIT/PREPARE; driven by trade-recommendation API.
- **Premarket:** `/api/premarket-analysis` uses data_fetcher; frontend shows — on error.
- **Scanners:** Lottery, last-hour, market-open, premarket use data_fetcher and current_price; empty watchlist message; ET timezone for lottery window.
- **Institutional:** `/api/institutional` uses data_fetcher + DataFrame; 4h aggregation.
- **Coach:** Uses data_fetcher + indicator_engine; DeepSeek context; placeholder = current ticker; **requests** in requirements.
- **Fib/ATR:** Exact numbers (2 decimals); symbol in “Best retracement (SYMBOL)”.
- **Data:** Yahoo Finance (yfinance) only; all APIs use the same data path.
