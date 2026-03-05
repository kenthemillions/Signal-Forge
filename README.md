# Signal Forge - Options Trading Signals Application

## Synopsis — What Signal Forge Does

**Signal Forge** is a live options-trading coach web app that keeps you connected to the market and gives you clear, actionable signals. It is built to:

- **Deliver real-time data** — Live prices and signal updates over WebSockets so the dashboard stays current without manual refresh.
- **Accept and track tickers** — Add symbols in the ticker box (single or multiple, e.g. `AAPL` or `AAPL, MSFT, NVDA`); the app stores them and includes them in scans and price updates.
- **Generate trading signals** — Combines indicators (RSI, MACD, VWAP, EMAs, Bollinger, volume), market regime, supply/demand zones, and entry confirmation to output BUY/SELL/PREPARE/WAIT with confidence and plain-English reasoning.
- **Support multiple modes** — Basic (traffic-light signals + chart), Institutional (zones, options flow, multi-timeframe), and Seasonality (time-of-day edge).
- **Help you practice** — Paper trading, journal, and Smart Coach (rule-based + optional AI) so you can refine strategy without real money.

Deploy by pushing this repo to GitHub and connecting it to Render (see `render.yaml` and **How to Run** below).

---

## Overview
A production-ready Python Flask web application providing real-time options trading signals. Signal Forge is a "market condition + location + confirmation" coach that provides actionable trading signals with confidence scoring based on confluence of indicators, market regime detection, supply/demand zones, and entry confirmations.

## User Preferences
- Clear, actionable information preferred
- Iterative development with major changes discussed before implementation
- Detailed explanations for complex features
- Maintain existing code structure and naming conventions
- No hardcoded secrets - use environment variables

## Project Architecture

### File Structure
```
signal_forge/
├── app.py                    # Main Flask application entry point
├── config.py                 # Environment variable handling & app settings
├── models.py                 # SQLAlchemy database models
├── indicators.py             # Legacy indicator calculations (compatibility)
├── strategies.py             # Legacy strategy orchestrator (compatibility)
├── data_fetcher.py           # Market data fetching (Yahoo Finance)
├── options_analytics.py      # Options-specific analytics
│
├── signal_engine/            # NEW: Modular signal generation engine
│   ├── __init__.py           # Package exports
│   ├── indicators.py         # RSI, VWAP, EMA, ATR, volume spike
│   ├── market_regime.py      # Trend vs range/distribution detection
│   ├── zones.py              # Supply/demand zone detection (swing high/low clustering)
│   ├── confirmation.py       # Entry confirmation (rejection candles, VWAP, divergence)
│   ├── scoring.py            # Confluence-based confidence scoring
│   ├── explanations.py       # Plain-English signal reasoning
│   └── institutional.py      # Institutional Mode state machine engine
│
├── services/                 # Business logic services
│   ├── __init__.py
│   └── signal_service.py     # High-level signal orchestration
│
├── api/                      # API blueprints
│   ├── __init__.py
│   └── routes.py             # Organized API endpoints
│
├── templates/
│   ├── landing.html          # Marketing landing page
│   ├── onboarding.html       # 4-step onboarding wizard
│   └── dashboard.html        # Main trading dashboard
│
└── static/
    ├── app.js                # Frontend JavaScript
    └── styles.css            # Custom styles
```

### Database Schema (SQLite)
- **users**: id, email, plan (free/pro/elite)
- **watchlist**: user_id, symbol, added_at, notes
- **signals**: symbol, timeframe, state, bias, confidence, reasons, entry/stop/target prices
- **journal_entries**: user_id, symbol, thesis, direction, entry/exit prices, result, PnL, notes
- **tickers**: symbol, is_active (preserved from original)
- **user_settings**: indicator parameters, notification preferences (preserved)
- **paper_account/paper_trade**: Paper trading functionality (preserved)

### Signal Engine Architecture
The signal engine uses weighted confluence scoring:
- Trend Alignment: 20%
- Indicator Confluence: 25%
- Zone Position: 15%
- Confirmation: 20%
- Volume Support: 10%
- Regime Fit: 10%

**Signal Flow:**
1. `IndicatorCalculator` → Calculate RSI, MACD, VWAP, EMA, ATR, Bollinger Bands
2. `MarketRegimeDetector` → Detect trend/range/distribution regime
3. `ZoneDetector` → Find supply/demand zones via swing high/low clustering
4. `ConfirmationEngine` → Check for entry confirmations (rejection candles, structure)
5. `SignalScorer` → Calculate confidence score from confluence
6. `ExplanationGenerator` → Generate plain-English reasoning

### SaaS Tiers
- **Free Beta** ($0): 5 watchlist items, basic signals
- **Pro Coach** ($59/mo): 25 watchlist, multi-timeframe, zones, journal, alerts
- **Elite Funded** ($129/mo): Unlimited watchlist, all features, priority support

## How to Run
```bash
python app.py
```
The app runs on port 5000 with Flask-SocketIO for real-time updates.

## Environment Variables
- `SESSION_SECRET` - Flask session secret key
- `DATABASE_URL` - PostgreSQL connection (optional, defaults to SQLite)
- `POLYGON_API_KEY` - Polygon.io API key (optional, for enhanced data)
- `ALPHA_VANTAGE_KEY` - Alpha Vantage API key (optional)
- `LOG_LEVEL` - Logging level (default: INFO)

## Key Features
- **Real-time Data & Analysis:** Yahoo Finance integration, technical indicators
- **Multi-Timeframe Confluence:** 1m, 5m, 15m, 1h, 4h analysis
- **Supply/Demand Zones:** Swing high/low clustering with 0.5% threshold
- **Signal Generation:** BUY/SELL/PREPARE/WAIT with confidence percentages
- **Entry Confirmations:** Rejection candles, VWAP reclaims, higher-low structure
- **Plain-English Explanations:** Coach-style reasoning for every signal
- **Trading Journal:** Track thesis, entries, exits, and lessons learned
- **Paper Trading:** Practice without risk

## Recent Changes (January 2026)
- Refactored into modular signal_engine package
- Added User, Watchlist, JournalEntry database models
- Created config.py for environment variable handling
- Added SignalService for high-level signal orchestration
- Implemented supply/demand zone detection with clustering
- Added entry confirmation logic (rejection candles, structure, VWAP)
- Created confluence-based scoring system
- **NEW: Fast-Path Signal Algorithm** for quicker entries/exits:
  - Candle pattern detection: hammer, inverted hammer, bullish/bearish engulfing
  - Momentum-based entries: 0.5+ ATR move in 5 candles triggers faster signals
  - Recovery detection: 40%+ rebound from session lows/highs = instant signal
  - Zone-blocking safeguards: blocks_bullish prevents BUY in supply zones, blocks_bearish prevents SELL in demand zones
  - Lowered confirmation threshold from 2 to 1 for faster BUY/SELL decisions
  - Options-appropriate stops: $1-2 max (instead of stock-based $10-11 ATR stops)
- **NEW: Landing page** with headline, 3 benefits, demo, pricing, waitlist, disclaimer
- **NEW: Onboarding flow** - 4-step wizard (watchlist, session rules, risk rules, tutorial)
- **NEW: Smart Coach** - Shared ask-the-coach component visible on all dashboard tabs
  - Rule-based analysis (free, no API key required)
  - Optional DeepSeek AI integration when user provides their own API key
  - API key stored in browser localStorage only (not on server)
  - **Full indicator context**: RSI, MACD, Bollinger Bands, VWAP, EMA, Volume, Support/Resistance
  - **Fibonacci retracement**: Calculates key levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) for buy zones; Scalping Levels panel loads Fib + ATR in real time when a ticker is selected or data is refreshed
  - AI references specific price levels and indicator values in responses
- **NEW: Institutional Mode** - multi-timeframe WAIT/PREPARE/BUY/SELL state machine
  - Market regime detection (TREND_UP/DOWN, RANGE, DISTRIBUTION)
  - Supply/demand zone detection with rejection tracking
  - Entry confirmations (rejection candles, structure breaks, VWAP, RSI divergence)
  - Session filters (no-trade windows, Monday/Friday toggles)
  - Timeframes: 5m, 15m, 1h, 4h
- **NEW: Cheap Option Radar** (services/cheap_option_radar.py)
  - Scans for high-volatility tickers (ATR >= 1.5%, RVOL >= 1.3)
  - Finds cheap options in $0.10-$0.75 range (expanded)
  - ATM ± 1 strike filtering with tight spread requirement
  - Detects pullback patterns for optimal entry
  - **FIXED: Direction now based on intraday price action, not lagging EMAs**
    - Strong rally (+0.5%+) = CALL recommendation
    - Sharp drop (-0.5%+) = PUT recommendation
    - Falls back to EMA trend only when intraday move is small
- **NEW: Time-of-Day Edge Analyzer** (services/time_edge_analyzer.py)
  - Analyzes 30-day historical patterns for high/low timing
  - Identifies best times for pullbacks and late-day expansion
  - Supports CT and ET timezone display
- **NEW: Late-Day Gatekeeper** (services/late_day_gatekeeper.py)
  - Enforces 1:25 PM - 2:25 PM CT trading window
  - Optional "stop when green" after profitable trade
  - Market hours awareness and session tracking
- **3-Tab Navigation System** (Basic / Institutional / Seasonality)
  - Tab selection persists in localStorage across sessions
  - **Basic Mode**: Traffic light signals, chart, indicators, scanner (novice-friendly)
  - **Institutional Mode**: Basic + Institutional Activity panel + Options Flow (advanced traders)
  - **Seasonality Mode**: Basic + Time Edge panel with current time vs edge display
  - Collapsible "Why?" confidence factors (Trend, VWAP, Volume, Timeframes, RSI, MACD)
  - Panels auto-hide/show based on active mode - no overlapping features
  - Smooth instant tab switching without unnecessary data re-fetching

## Routes
- `/` - Landing page (marketing)
- `/app` - Trading dashboard
- `/onboarding` - Setup wizard
- `/api/institutional/<symbol>` - Institutional mode analysis

## External Dependencies
- **yfinance**: Yahoo Finance market data
- **Flask-SocketIO**: WebSocket real-time updates
- **SQLAlchemy**: ORM for database
- **pandas/numpy/scipy**: Data analysis
- **Bootstrap 5 / Chart.js**: Frontend UI
