# Signal Forge – Site Synopsis & How It Works

This document explains what the Signal Forge SaaS does, how each area works, what was fixed/upgraded, and how to deploy it on Render.

---

## What Signal Forge Is

Signal Forge is a **stock/options trading signal SaaS**. It gives you:

- **Real-time BUY/SELL/WAIT signals** (traffic light) for the ticker you select
- **Charts** with indicators (RSI, MACD, EMAs, VWAP, Bollinger, support/resistance)
- **Multi-timeframe confluence** (1m, 2m, 5m, 15m, 1h, 4h)
- **Fibonacci & ATR** for best retracement entries and “how far price can go”
- **Institutional flow** (BUY/SELL/PREPARE with entry/stop/target)
- **Scanners**: lottery hour, last-hour, market open, premarket
- **AI Coach** (rule-based + optional DeepSeek) for trade questions
- **Options flow**, earnings, news, and more

Everything is **ticker-coherent**: when you pick SPY (or any symbol), charts, signals, Fib, institutional, and coach all use that same ticker.

---

## How Each Area Works

### 1. Traffic Light (Stop Light) & Main Signal Panel

- **What it is:** The main “stop light” (red / yellow / green) and the big text (BUY, SELL, WAIT, PREPARE, STRONG BUY, etc.).
- **How it works:**
  - Frontend calls **Refresh** or auto-refresh (every 5–8 seconds) → `loadTradeRecommendation()`.
  - That calls **`/api/trade-recommendation/<SYMBOL>?interval=5m`** (or whatever timeframe you have selected).
  - Backend uses **data_fetcher** (Yahoo Finance), **indicator_engine**, and **strategy_orchestrator** to compute a signal (BUY/SELL/WAIT/PREPARE/WATCH, strength, reasons, entry/stop/target).
  - Response includes `main_signal`, `summary`, `confidence_pct`, `edge_direction` (CALL/PUT/FLAT), etc.
  - **`updateTrafficLight(data.main_signal)`** turns on:
    - **Green** = BUY or STRONG BUY  
    - **Red** = SELL or STRONG SELL  
    - **Yellow** = PREPARE, WATCH, or WAIT  
  - **`updateMainSignalPanel(data)`** updates the signal text, summary, confidence, “What I’m waiting for,” and option edge (CALL/PUT/FLAT).
- **Checked/fixed:** Logic already matched API; panel class (signal-buy, signal-sell, signal-wait, etc.) and light selection are correct. No code change needed; verified flow.

### 2. Charts (1m, 2m, 5m, 15m, 1h, 4h)

- **What it is:** Price chart (line or candle) with volume and indicators (EMA 13/48/200, RSI, MACD, Bollinger, VWAP, S/R).
- **How it works:**
  - When you change **ticker** or **timeframe** (1m, 2m, 5m, 15m, 1h, 4h), `loadChartData()` runs.
  - It requests **`/api/market-data/<SYMBOL>?period=…&interval=…`** and **`/api/indicators/<SYMBOL>?period=…&interval=…`**.
  - Backend uses **data_fetcher.get_stock_data(symbol, period, interval)** (Yahoo Finance).
  - Frontend only applies the response if the **selected ticker** still matches (`requestedSymbol === currentTicker`), so you never see another ticker’s data.
- **Checked/fixed:** Cache no longer cleared on every request (so charts load faster). All six timeframes use correct period/interval; 2m added to multi-timeframe API.

### 3. Fibonacci & ATR (Scalping Levels)

- **What it is:** Best retracement zone (e.g. “38.2–50 (buy zone)”), ATR move in $ and %, Fib levels (23.6%, 38.2%, 50%, 61.8%, 78.6%), support/resistance, per timeframe (1m–4h).
- **How it works:**
  - **`/api/scalping-levels/<SYMBOL>`** calls **get_scalping_levels(data_fetcher, symbol)**.
  - That uses **data_fetcher.get_multi_timeframe_data(symbol)** (1m, 2m, 5m, 15m, 1h, 4h), then computes Fib, ATR, and VWAP per timeframe and picks a “best” retracement (e.g. 5m or 15m).
  - Frontend shows exact numbers (2 decimals), symbol in the header, and ATR range.
- **Checked/fixed:** All values formatted with `.toFixed(2)`; symbol shown in “Best retracement (SPY) 5m” so it’s clear which ticker it is.

### 4. Institutional Flow (BUY/SELL/PREPARE with Entry/Stop/Target)

- **What it is:** Institutional mode panel with state (BUY, SELL, PREPARE, WAIT), confidence, regime, location, zone, confirmations, reasons, and entry/stop/target prices.
- **How it works:**
  - **`/api/institutional/<SYMBOL>?timeframe=5m|15m|1h|4h`** is called when you’re in Institutional mode (and on ticker change).
  - **Fixed:** It uses **data_fetcher.get_stock_data(symbol, period, interval)** and builds a pandas DataFrame for **institutional_engine.analyze()**, same data as the rest of the app (Yahoo Finance). For 4h, 1h bars are aggregated to 4h.
- **Checked/fixed:** No more raw yfinance here; same ticker, same data source, correct timeframes.

### 5. Scanners (Lottery Hour, Last-Hour, Market Open, Premarket)

- **What it is:** Scans that find “lottery” plays (3–4:15 PM), last-hour strong plays, market-open trending stocks, and premarket move.
- **How it works:**
  - **Lottery:** `/api/lottery-scan` – uses watchlist tickers, **data_fetcher.get_stock_data** (5d/5m), momentum/volume/RSI/MACD to rank and return top 3.
  - **Last-hour:** `/api/last-hour-scan` – uses 1d/1m, last 75 minutes, direction + volume + momentum; returns strongest CALL/PUT plays.
  - **Market open:** `/api/market-open-scan?phase=premarket|5min|15min|30min` – uses 1d/1m; for premarket phase, move is vs **previous close** (not first bar of day).
  - **Premarket (single ticker):** `/api/premarket-analysis/<SYMBOL>` – uses **data_fetcher** for current price, session, change % and trend/outlook.
- **Checked/fixed:** All scanners use **data_fetcher** (and thus `current_price` where relevant), handle empty watchlist with a clear message, and use ET timezone for “lottery window.”

### 6. AI Coach (Rule-Based + DeepSeek)

- **What it is:** “Ask the Coach” – you type a question (e.g. “Is this a good buy for SPY calls?”); you get a short answer (rule-based or AI).
- **How it works:**
  - Frontend sends **question**, **symbol** (from ticker dropdown), and (if enabled) **use_ai** + **api_key** to **`/api/coach`**.
  - Backend uses **data_fetcher.get_stock_data(symbol, 5d, 5m)** and **indicator_engine.calculate_all()** so the coach sees the same data as the dashboard. It builds institutional_data from a DataFrame and calls **analyze_trade()** (rules) or **ask_deepseek()** (AI) with that context.
  - DeepSeek is used only when the user has set an API key in Coach → AI Settings and turned on “Enable AI responses”; the key is stored in the browser and sent only to the coach endpoint.
- **Checked/fixed:** Coach no longer uses raw yfinance; it uses data_fetcher + indicator_engine. DeepSeek context uses the same indicator keys (e.g. ema_13, volume.spike_ratio). Placeholder updates to current ticker (e.g. “Is this a good buy for SPY calls?”).

### 7. Data Source: Yahoo Finance Only

- **What it is:** All market data (OHLCV, current price, premarket/after-hours) comes from **Yahoo Finance (yfinance)**.
- **How it works:**
  - **data_fetcher** uses **yfinance** only: **history(prepost=True)**, **fast_info**, and **info** for current/pre/post price and session. Same data path for charts, trade recommendation, institutional, coach, and scanners.

### 8. Ticker Consistency Everywhere

- **What it is:** When you select SPY (or any ticker), every section should show data for that ticker only.
- **How it works:**
  - **Charts / trade recommendation:** Request with `requestedSymbol`; response is ignored if `currentTicker` changed before the response arrives.
  - **Socket:** Price/signal updates are applied only when `data.symbol === currentTicker`.
  - **Premarket, multi-timeframe, scalping, earnings, news, options flow, institutional, coach:** All use **currentTicker** (or the dropdown value, kept in sync) in the request URL or body.
- **Checked/fixed:** Confirmed all critical paths use the selected ticker and ignore stale responses where applicable.

---

## What Was Fixed / Upgraded (Summary)

| Area | Fix / upgrade |
|------|----------------|
| **Data (prices/session)** | data_fetcher uses history + fast_info + info; session from ET time + marketState; pre/post price fallback from last bar when info is empty. |
| **Charts** | Cache kept (no delete on every request); 2m added to multi-timeframe; period/interval correct for 1m–4h. |
| **Trade recommendation / traffic light** | Already correct; uses data_fetcher; response shape matches updateTrafficLight/updateMainSignalPanel. |
| **Premarket** | `/api/premarket-analysis` uses data_fetcher; frontend shows “—” and “Refresh for data” on error. |
| **Lottery / last-hour / market-open** | Use current_price from data_fetcher; empty watchlist returns a message; ET window for lottery; premarket phase vs previous close. |
| **Institutional** | `/api/institutional` uses data_fetcher + DataFrame; 4h aggregation from 1h bars. |
| **Coach** | Uses data_fetcher + indicator_engine; DeepSeek context uses correct indicator keys; placeholder = current ticker. |
| **Fibonacci / ATR** | Exact numbers (2 decimals) in UI; symbol in “Best retracement (SPY)” header. |
| **Dependency** | **requests** added to requirements.txt for DeepSeek API calls. |

---

## Deploy on Render (All Fixes Apply)

1. **Push** your latest code (including the above fixes and `requests` in requirements) to GitHub.
2. In **Render** → your **signal-forge** web service:
   - **Manual Deploy** → **Deploy latest commit**.
   - **Environment:** Set **SESSION_SECRET** (required).
3. After deploy (2–5 min): open **/health** (should be healthy), then **/app** (login → dashboard). Do a **hard refresh** (Ctrl+Shift+R / Cmd+Shift+R) so the browser loads the latest JS.
4. If the dashboard is slow or “Connecting…”, wait for cold start then click **Refresh**.

Details and optional steps (e.g. DeepSeek) are in **DEPLOY_NOW.md**.

---

## Quick Test Checklist (You Can Run This Mentally or Manually)

- **Traffic light:** Change ticker → Refresh → light and main signal text match (BUY=green, SELL=red, WAIT/PREPARE=yellow).
- **Charts:** Switch 1m, 2m, 5m, 15m, 1h, 4h → chart and volume update for the selected ticker.
- **Fibonacci / ATR:** Open scalping section → see “Best retracement (SYMBOL) 5m”, ATR in $ and %, Fib levels with two decimals.
- **Institutional:** Switch to Institutional mode → pick 5m/15m/1h/4h → see state, entry/stop/target for the selected ticker.
- **Scanners:** Run lottery / last-hour / market-open / premarket → results or “Add tickers…” message; no crash.
- **Coach:** Ask a question with a ticker selected → rule-based answer; with DeepSeek key and “Enable AI” → AI answer for that ticker.

---

## Optional Upgrades You Could Add Later

- **Backtest / history:** Store past signals and show “If you had followed last N signals, win rate would be X%.”
- **Alerts:** Browser push or email when signal flips to BUY/SELL for a watched ticker (you have some notification hooks already).
- **More data sources:** Optional Polygon or Alpha Vantage for redundancy (config already has placeholders).
- **Mobile-friendly:** Ensure touch targets and layout work on small screens (Bootstrap is already used).

---

Everything above is implemented and deploy-ready. After you push and redeploy on Render, the fixes and behavior described here will be live.
