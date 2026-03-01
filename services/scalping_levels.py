"""
Scalping Levels Service
Multi-timeframe Fibonacci retracement, ATR range, and VWAP (with bands) for 1m, 2m, 5m, 15m, 1h, 4h.
Auto-computes "best retracement range" and "how far it can go" (ATR) per ticker.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Lookback candles per TF for Fib swing high/low (scalping = shorter lookback on lower TFs)
FIB_LOOKBACK = {
    '1m': 60,
    '2m': 50,
    '5m': 50,
    '15m': 48,
    '1h': 30,
    '4h': 24,
}


def _compute_fib(highs: List[float], lows: List[float], closes: List[float], lookback: int) -> Dict[str, Any]:
    """Compute Fib levels from swing high/low. Uses 0-100 from high to low (retracement down)."""
    if not highs or not lows or len(closes) < min(lookback, 10):
        return {}
    recent_h = highs[-lookback:]
    recent_l = lows[-lookback:]
    swing_high = max(recent_h)
    swing_low = min(recent_l)
    current = closes[-1]
    price_range = swing_high - swing_low
    if price_range <= 0:
        return {}
    fib = {
        '0': round(swing_high, 2),
        '23.6': round(swing_high - price_range * 0.236, 2),
        '38.2': round(swing_high - price_range * 0.382, 2),
        '50': round(swing_high - price_range * 0.5, 2),
        '61.8': round(swing_high - price_range * 0.618, 2),
        '78.6': round(swing_high - price_range * 0.786, 2),
        '100': round(swing_low, 2),
    }
    retracement_pct = (swing_high - current) / price_range * 100
    # Zone name for scalping
    if retracement_pct <= 23.6:
        zone = '0-23.6 (strong trend)'
    elif retracement_pct <= 38.2:
        zone = '23.6-38.2 (shallow)'
    elif retracement_pct <= 50:
        zone = '38.2-50 (buy zone)'
    elif retracement_pct <= 61.8:
        zone = '50-61.8 (deep)'
    elif retracement_pct <= 78.6:
        zone = '61.8-78.6 (critical)'
    else:
        zone = '78.6-100 (breakdown)'
    supports = [v for v in fib.values() if v < current]
    resistances = [v for v in fib.values() if v > current]
    return {
        'levels': fib,
        'swing_high': round(swing_high, 2),
        'swing_low': round(swing_low, 2),
        'true_range': round(price_range, 2),
        'true_range_pct': round(price_range / current * 100, 2) if current else 0,
        'retracement_pct': round(retracement_pct, 1),
        'zone': zone,
        'nearest_support': round(max(supports), 2) if supports else swing_low,
        'nearest_resistance': round(min(resistances), 2) if resistances else swing_high,
    }


def _compute_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Dict[str, Any]:
    """ATR and range (how far price can go in one move)."""
    if len(closes) < period + 1:
        return {'value': 0, 'pct': 0, 'range_low': closes[-1], 'range_high': closes[-1]}
    tr_list = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_list.append(max(hl, hc, lc))
    atr = sum(tr_list[-period:]) / period
    current = closes[-1]
    atr_pct = (atr / current * 100) if current else 0
    return {
        'value': round(atr, 2),
        'pct': round(atr_pct, 2),
        'range_low': round(current - atr, 2),
        'range_high': round(current + atr, 2),
        'range_1_5_low': round(current - atr * 1.5, 2),
        'range_1_5_high': round(current + atr * 1.5, 2),
    }


def _compute_vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float]) -> Dict[str, Any]:
    """VWAP and bands (VWAP ± ATR for scalping premium/discount)."""
    if len(closes) < 5 or len(volumes) < 5:
        current = closes[-1] if closes else 0
        return {'value': current, 'upper': current, 'lower': current, 'above_vwap': True}
    typical = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    cum_tpv = sum(t * v for t, v in zip(typical, volumes))
    cum_v = sum(volumes)
    vwap = cum_tpv / cum_v if cum_v else closes[-1]
    current = closes[-1]
    atr_val = _compute_atr(highs, lows, closes)['value']
    vwap_upper = vwap + atr_val
    vwap_lower = vwap - atr_val
    return {
        'value': round(vwap, 2),
        'upper': round(vwap_upper, 2),
        'lower': round(vwap_lower, 2),
        'above_vwap': current > vwap,
        'distance_pct': round((current - vwap) / vwap * 100, 2) if vwap else 0,
    }


def get_scalping_levels(data_fetcher, symbol: str) -> Dict[str, Any]:
    """
    Build scalping levels for symbol across 1m, 2m, 5m, 15m, 1h, 4h.
    Returns Fib levels, ATR range (how far it can go), VWAP with bands, and best retracement range.
    """
    symbol = symbol.upper()
    mtf = data_fetcher.get_multi_timeframe_data(symbol)
    timeframes_data = mtf.get('timeframes', {})
    current_price = None
    timeframes = {}

    for tf_name in ['1m', '2m', '5m', '15m', '1h', '4h']:
        data = timeframes_data.get(tf_name)
        if not data or 'closes' not in data or len(data['closes']) < 20:
            timeframes[tf_name] = {'error': 'Insufficient data'}
            continue
        closes = data['closes']
        highs = data.get('highs', closes)
        lows = data.get('lows', closes)
        volumes = data.get('volumes', [1] * len(closes))
        if current_price is None:
            current_price = data.get('current_price') or closes[-1]
        lookback = min(FIB_LOOKBACK.get(tf_name, 50), len(closes) - 1)
        fib = _compute_fib(highs, lows, closes, lookback)
        atr = _compute_atr(highs, lows, closes)
        vwap = _compute_vwap(highs, lows, closes, volumes)
        timeframes[tf_name] = {
            'fib': fib,
            'atr': atr,
            'vwap': vwap,
            'current_price': round(closes[-1], 2),
        }

    # Best retracement range: use 5m (primary for scalping) or 15m if 5m missing
    best_tf = None
    best_fib = None
    best_atr = None
    for tf in ['5m', '15m', '2m', '1m']:
        tf_data = timeframes.get(tf, {})
        if isinstance(tf_data, dict) and 'error' not in tf_data and tf_data.get('fib'):
            best_tf = tf
            best_fib = tf_data['fib']
            best_atr = tf_data.get('atr', {})
            break
    best_retracement_range = {}
    if best_tf and best_fib:
        best_retracement_range = {
            'timeframe': best_tf,
            'zone': best_fib.get('zone', ''),
            'true_range': best_fib.get('true_range'),
            'true_range_pct': best_fib.get('true_range_pct'),
            'swing_high': best_fib.get('swing_high'),
            'swing_low': best_fib.get('swing_low'),
            'nearest_support': best_fib.get('nearest_support'),
            'nearest_resistance': best_fib.get('nearest_resistance'),
            'atr_move': best_atr.get('value'),
            'atr_pct': best_atr.get('pct'),
            'range_low': best_atr.get('range_low'),
            'range_high': best_atr.get('range_high'),
            'levels': best_fib.get('levels', {}),
        }

    return {
        'symbol': symbol,
        'current_price': round(current_price or 0, 2),
        'timeframes': timeframes,
        'best_retracement_range': best_retracement_range,
    }
