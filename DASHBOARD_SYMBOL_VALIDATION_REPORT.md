# Final Live Dashboard Validation Report — Symbol Switching (SPY, SLV, AAPL, TSLA)

**Date:** Pre–Step 5 validation  
**Scope:** Confirm each module receives `currentTicker` and refreshes when the symbol changes.  
**Stack:** Dashboard uses `dashboard-simple.js` (ticker-select → `onSymbolChanged(sym)`).

---

## 1. Symbol switching flow

- **Trigger:** User selects a new symbol from `#ticker-select` (SPY, SLV, AAPL, TSLA).
- **Handler:** `onSymbolChanged(sym)` in `static/dashboard-simple.js`.
- **Sync:** At the **start** of `onSymbolChanged`, `currentTicker` and `window.__currentTicker` are set to the new symbol so inline scripts and `getCurrentTicker()` always see the new value before any async work.

---

## 2. Module-by-module status

| Module | Receives current ticker? | Refreshes on symbol change? | Notes |
|--------|--------------------------|-----------------------------|--------|
| **Quote** | Yes | Yes | `loadQuote(sym)` — price/change/updated. |
| **Chart** | Yes | Yes | `loadChart(sym, ...)` — price chart for selected symbol. |
| **Volume** | Yes | Yes | Updated inside `loadChart()` from same `/api/market-data` response. |
| **Analysis** | Yes | Yes | `loadAnalysis(sym)` → `/api/trade-recommendation/<sym>`. |
| **Timeframe Analysis** | Yes | Yes | `loadTimeframeAnalysis(sym)` → `/api/multi-timeframe/<sym>`. |
| **Key Levels** | Yes | Yes | `loadKeyLevels(sym)` → `/api/pivot-points/<sym>`. |
| **Scalping Levels** | Yes | Yes | `loadScalpingLevels(sym)` → `/api/scalping-levels/<sym>`. |
| **Premarket Trend** | Yes | Yes | `loadPremarketTrend(sym)` → `/api/premarket-analysis/<sym>`. |
| **Trading Session** | N/A | N/A | Market-wide (session name, countdown). Not symbol-specific; no refresh on symbol change. |
| **Opening Range** | Yes (scan includes watchlist) | Yes | `loadMarketOpenScan(phase)` re-run on symbol change; phase buttons (Pre/5m/15m/30m) bound to refresh panel. |
| **Recent Signals** | Yes | Yes | `loadSignals(sym)` → `/api/signals`; feed filtered to current symbol. |
| **News** | Yes | Yes | `loadNews(sym)` → `/api/news/<sym>`. |

---

## 3. Inline script / global sync

- **`window.__currentTicker`** — Set at the very start of `onSymbolChanged(sym)` so dashboard inline logic (institutional, time-edge, seasonality) always reads the new symbol.
- **`window.getCurrentTicker()`** — Provided by `dashboard-simple.js`; returns `currentTicker` (e.g. used by Premarket refresh button).
- **`symbolChanged` event** — Dispatched at the end of `onSymbolChanged`; inline listeners run `refreshSeasonality()`, `refreshInstitutionalAnalysis()`, `refreshTimeEdge()` which use the updated ticker.

---

## 4. Patches applied (before Step 5)

1. **`window.__currentTicker`** — Set synchronously at the top of `onSymbolChanged(symbol)` so no module or inline script sees a stale ticker.
2. **Recent Signals** — Added `loadSignals(symbol)`; fetches `/api/signals?limit=20`, filters by `symbol`, renders into `#signal-feed`; called from `onSymbolChanged(sym)`.
3. **Opening Range** — Added `loadMarketOpenScan(phase)`; calls `/api/market-open-scan?phase=...`; called from `onSymbolChanged` (using active phase) and bound to `.open-scan-btn` clicks.
4. **Ticker card Refresh** — Ticker card “Refresh” button now calls `onSymbolChanged(currentTicker)` instead of only `loadQuote(currentTicker)`, so all modules refresh together.

---

## 5. How to test (SPY → SLV → AAPL → TSLA)

1. Open the dashboard and wait for initial load (e.g. SPY).
2. Change symbol to **SLV** — confirm Quote, Chart, Volume, Analysis, Timeframe, Key Levels, Scalping, Premarket, Opening Range, Recent Signals, and News all update to SLV.
3. Switch to **AAPL**, then **TSLA** — same checks.
4. Click **Refresh** on the ticker card — all modules should refresh for the current symbol (no stale data).
5. Use **Premarket** refresh button — should use `getCurrentTicker()` (current symbol).
6. Open **Opening Range** and switch phase (Pre / 5m / 15m / 30m) — panel should refresh; switching symbol should re-run scan for the active phase.

---

## 6. Stale data

- **Before patches:** Recent Signals and Opening Range did not refresh on symbol change; ticker card Refresh only updated the quote.
- **After patches:** All listed modules (except Trading Session, which is market-wide) receive the current symbol and refresh when it changes or when the ticker card Refresh is clicked.

---

## 7. Note on Lottery Scan

The “3:54 PM Lottery Plays” button uses `window.tradingApp.runLotteryScan()`. `tradingApp` is set only when the full app (`app.bootfix2.js` / `app.js`) is loaded. The dashboard currently loads only `dashboard-simple.js`, so this button will be undefined unless the full app is also included. This is unchanged by this validation; consider either loading the full app or adding a `runLotteryScan` implementation in `dashboard-simple.js` if Lottery Scan is required on this dashboard.

---

**Conclusion:** Symbol switching (SPY, SLV, AAPL, TSLA) is validated. Each of Quote, Chart, Volume, Analysis, Timeframe Analysis, Key Levels, Scalping Levels, Premarket Trend, Opening Range, Recent Signals, and News receives the current ticker and refreshes when the symbol changes. No remaining stale-data issues identified for these modules before Step 5.
