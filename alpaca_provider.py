"""
Alpaca market data provider for Signal Forge.
Returns the same dict shape as data_fetcher.get_stock_data for drop-in use.
Uses Alpaca Data API (free with account) for bars and latest quote.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

# Optional: only import when used
def _get_alpaca_client():
    import os
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    key = os.environ.get('ALPACA_API_KEY') or os.environ.get('APCA_API_KEY_ID')
    secret = os.environ.get('ALPACA_SECRET_KEY') or os.environ.get('APCA_API_SECRET_KEY')
    if not key or not secret:
        return None
    base_url = os.environ.get('ALPACA_BASE_URL')
    if base_url:
        return StockHistoricalDataClient(key, secret, url_override=base_url)
    return StockHistoricalDataClient(key, secret)

def _et_now():
    if ZoneInfo:
        return datetime.now(ZoneInfo('America/New_York'))
    return datetime.utcnow() - timedelta(hours=5)

def _period_to_timedelta(period: str) -> timedelta:
    m = {'1d': 1, '5d': 5, '1mo': 30, '3mo': 90, '1y': 365}
    days = m.get(period, 5)
    return timedelta(days=days)

def _interval_to_timeframe(interval: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    unit_map = {'1m': (1, TimeFrameUnit.Minute), '2m': (2, TimeFrameUnit.Minute),
                '5m': (5, TimeFrameUnit.Minute), '15m': (15, TimeFrameUnit.Minute),
                '30m': (30, TimeFrameUnit.Minute), '1h': (1, TimeFrameUnit.Hour), '1d': (1, TimeFrameUnit.Day)}
    if interval in unit_map:
        amt, unit = unit_map[interval]
        return TimeFrame(amount=amt, unit=unit)
    return TimeFrame(amount=5, unit=TimeFrameUnit.Minute)

def get_stock_data_alpaca(symbol: str, period: str = '1d', interval: str = '5m') -> Dict:
    """
    Fetch OHLCV and current price from Alpaca. Return shape matches data_fetcher.get_stock_data.
    """
    try:
        client = _get_alpaca_client()
        if not client:
            return {'error': 'Alpaca not configured (set ALPACA_API_KEY and ALPACA_SECRET_KEY)', 'symbol': symbol}
    except Exception as e:
        return {'error': f'Alpaca client: {e}', 'symbol': symbol}

    try:
        from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        sym = symbol.upper()
        et = _et_now()
        delta = _period_to_timedelta(period)
        start = et - delta
        tf = _interval_to_timeframe(interval)

        req = StockBarsRequest(
            symbol_or_symbols=sym,
            timeframe=tf,
            start=start,
            end=et,
            limit=5000,
        )
        bars = client.get_stock_bars(req)
        data = getattr(bars, 'data', bars) if bars else {}
        if not data or sym not in data:
            return {'error': f'No bars for {symbol}', 'symbol': symbol}
        bar_list = data[sym]
        if not bar_list:
            return {'error': f'No data for {symbol}', 'symbol': symbol}

        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        timestamps = []
        for b in bar_list:
            opens.append(float(b.open))
            highs.append(float(b.high))
            lows.append(float(b.low))
            closes.append(float(b.close))
            volumes.append(int(b.volume))
            ts = b.timestamp
            timestamps.append(ts.isoformat() if hasattr(ts, 'isoformat') else str(ts))

        previous_close = float(opens[0]) if opens else 0
        current_price = float(closes[-1]) if closes else 0
        regular_close = current_price
        change = round(current_price - previous_close, 2) if previous_close else 0
        change_percent = round((change / previous_close) * 100, 2) if previous_close else 0

        # Infer session from ET time
        hour = et.hour
        minute = et.minute
        if hour < 9 or (hour == 9 and minute < 30):
            session = 'premarket'
        elif hour >= 16:
            session = 'afterhours'
        else:
            session = 'regular'

        return {
            'symbol': symbol,
            'timestamps': timestamps,
            'opens': opens,
            'highs': highs,
            'lows': lows,
            'closes': closes,
            'volumes': volumes,
            'current_price': round(current_price, 2),
            'regular_close': round(regular_close, 2),
            'session': session,
            'open_price': round(opens[0], 2) if opens else 0,
            'high': round(max(highs), 2) if highs else 0,
            'low': round(min(lows), 2) if lows else 0,
            'volume': sum(volumes),
            'change': change,
            'change_percent': change_percent,
            'previous_close': round(previous_close, 2),
            'market_cap': 0,
            'pe_ratio': 0,
            'last_updated': datetime.now().isoformat(),
        }
    except Exception as e:
        return {'error': str(e), 'symbol': symbol}


def get_quote_alpaca(symbol: str) -> Dict:
    """Get latest quote from Alpaca. Same shape as data_fetcher.get_quote."""
    try:
        client = _get_alpaca_client()
        if not client:
            return {'error': 'Alpaca not configured', 'symbol': symbol}
        from alpaca.data.requests import StockLatestQuoteRequest
        req = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
        quotes = client.get_stock_latest_quote(req)
        qdata = getattr(quotes, 'data', quotes) if quotes else {}
        if not qdata or symbol.upper() not in qdata:
            return {'error': 'No quote', 'symbol': symbol}
        q = qdata[symbol.upper()]
        if not q:
            return {'error': 'No quote', 'symbol': symbol}
        mid = (float(q.ask_price) + float(q.bid_price)) / 2 if (q.ask_price and q.bid_price) else float(q.ask_price or q.bid_price or 0)
        return {
            'symbol': symbol,
            'price': mid,
            'change': 0,
            'change_percent': 0,
            'volume': 0,
            'avg_volume': 0,
            'bid': float(q.bid_price or 0),
            'ask': float(q.ask_price or 0),
            'day_high': 0,
            'day_low': 0,
            'fifty_two_week_high': 0,
            'fifty_two_week_low': 0,
            'last_updated': datetime.now().isoformat(),
        }
    except Exception as e:
        return {'error': str(e), 'symbol': symbol}


def alpaca_configured() -> bool:
    import os
    key = os.environ.get('ALPACA_API_KEY') or os.environ.get('APCA_API_KEY_ID')
    secret = os.environ.get('ALPACA_SECRET_KEY') or os.environ.get('APCA_API_SECRET_KEY')
    return bool(key and secret)
