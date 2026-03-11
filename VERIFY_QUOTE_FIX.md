# Quote fix verification (2026-03-11)

## What was changed

1. **Visible debug box** – Top of ticker card shows: currentTicker, refreshData called, loadTickerCardQuote called, quote request started, quote URL, quote status, quote response snippet, DOM update success, last function to touch price card.
2. **Only loadTickerCardQuote touches the price card** – setPriceCardError, showTickerLoading, clearLoadingState (price fields), updatePriceDisplay, socket price_update no longer write to #current-price, #price-change, #last-updated.
3. **loadTickerCardQuote is dumb and direct** – Reads currentTicker, fetches /api/quote?symbol=<sym>, awaits response, sets the three elements or shows exact error text. No silent catch.
4. **Exact request in UI** – Debug box shows quote URL (e.g. /api/quote?symbol=SPY, /api/quote?symbol=SLV), status, and response body snippet.
5. **DOM IDs** – Confirmed in dashboard.html: #current-price, #price-change, #last-updated exist in the ticker card.
6. **Version and cache bust** – console.log("APP VERSION 2026-03-11-quote-fix-1"); footer shows same string; script src uses ?v=...-2026-03-11-quote-fix so new JS loads.
7. **Add Ticker** – Flow unchanged: on Add SLV, currentTicker and dropdown are set to SLV, then refreshData() runs and calls loadTickerCardQuote() which uses currentTicker (SLV) and requests /api/quote?symbol=SLV.
8. **No permanent loading** – Initial card text is "—". Only terminal states: real quote or explicit error from loadTickerCardQuote.

## How to verify in production

1. Deploy to Render (push and deploy latest commit).
2. Hard refresh (Ctrl+Shift+R). Open dashboard.
3. **Footer** – Must show: `APP VERSION 2026-03-11-quote-fix-1`. If not, new JS is not loaded (cache or deploy issue).
4. **Debug box** – At top of ticker card, confirm: currentTicker (e.g. SPY), refreshData called: yes, loadTickerCardQuote called: yes, quote request started: yes, quote URL: /api/quote?symbol=SPY, quote status: 200, quote response: JSON snippet, DOM update success: yes, last to touch: loadTickerCardQuote (success).
5. **Network** – In DevTools Network, filter by "quote". Confirm request to /api/quote?symbol=SPY (and later /api/quote?symbol=SLV when you add SLV). Check status and response body.
6. **Add SLV** – Add ticker SLV, select SLV. Debug box should show currentTicker: SLV, quote URL: /api/quote?symbol=SLV, and price card should show SLV price or error.

## Root cause (fix 2 – boot/state)

**Exact root cause:** currentTicker was never set from the visible DOM on boot; init did not read the symbol element first or run a minimal boot that invokes refreshData(), so the debug box showed -- and no quote ran. The visible symbol is in **`<select id="ticker-select">`** (`.value` = "SPY"). Fix: at the very start of init(), read `document.getElementById('ticker-select').value`, set `currentTicker`, update init-step debug, bind Refresh, call `refreshData()`.

## Root cause (one of these) – if still broken

- **Stale cached JS** – Footer does not show 2026-03-11-quote-fix-1.
- **Wrong DOM selectors** – #current-price / #price-change / #last-updated missing; debug would show "loadTickerCardQuote (no #current-price)".
- **loadTickerCardQuote never called** – debug: loadTickerCardQuote called: no.
- **refreshData never called** – debug: refreshData called: no.
- **Add Ticker never updates currentTicker** – debug: currentTicker still SPY after adding SLV.
- **/api/quote not requested** – debug: quote request started: no or quote URL --; Network tab has no quote request.
- **/api/quote returns good JSON but render path broken** – quote status 200, quote response has price, but DOM update success: no or price card still —.
- **Another async overwrites quote** – debug: last to touch price card is not loadTickerCardQuote (success).
- **Frontend deployed incorrectly on Render** – Footer or debug box missing; static files not updated.

## Files changed

- `templates/dashboard.html` – Debug box markup, footer version, initial price/change to "—", script cache-bust suffix.
- `static/app.js` – Version log; _quoteDebug and _updateQuoteDebug(); loadTickerCardQuote() rewritten (dumb/direct + debug); refreshData sets refreshDataCalled; setPriceCardError, showTickerLoading, clearLoadingState (price parts), updatePriceDisplay, socket price_update no longer touch price card.
