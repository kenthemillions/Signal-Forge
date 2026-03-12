"""
Step 5: Trading Intelligence Layer
Signal Engine + Momentum Scanner + Risk/Reward + Trade Scoring + Market Phase
All outputs keyed by symbol and refresh when ticker changes.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import math

logger = logging.getLogger(__name__)

SIGNAL_TYPES = [
    'Bullish Momentum', 'Bearish Momentum', 'VWAP Reclaim', 'VWAP Rejection',
    'Breakout', 'Breakdown', 'Pullback Entry', 'Trend Continuation', 'Exhaustion Warning'
]


def run_momentum_scanner(
    symbol: str,
    closes: List[float],
    volumes: List[float],
    highs: List[float],
    lows: List[float],
    opens: List[float],
    vwap_value: float,
    atr_value: float,
    current_price: float,
) -> Dict[str, Any]:
    """
    Momentum Scanner: high relative volume, directional candles, volatility expansion,
    VWAP separation, intraday breakout structures.
    Returns momentum_score, trend_strength, volatility_score.
    """
    if not closes or len(closes) < 10:
        return {'momentum_score': 0, 'trend_strength': 0, 'volatility_score': 0, 'error': 'Insufficient data'}
    n = len(closes)
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else (sum(volumes) / len(volumes) if volumes else 1)
    rel_vol = volumes[-1] / avg_vol if avg_vol > 0 else 1.0
    # Directional candles: last 3 closes vs opens
    bullish_candles = sum(1 for i in range(max(0, n - 5), n) if i < len(opens) and closes[i] > opens[i])
    bearish_candles = sum(1 for i in range(max(0, n - 5), n) if i < len(opens) and closes[i] < opens[i])
    direction_strength = (bullish_candles - bearish_candles) / 5.0 if n >= 5 else 0  # -1 to 1
    # Volatility expansion: recent ATR vs older ATR
    recent_range = max(highs[-10:]) - min(lows[-10:]) if len(highs) >= 10 and len(lows) >= 10 else 0
    older_range = max(highs[-30:-10]) - min(lows[-30:-10]) if len(highs) >= 30 and len(lows) >= 30 else recent_range
    vol_expansion = (recent_range / older_range) if older_range > 0 else 1.0
    # VWAP separation (distance %)
    vwap_sep = 0.0
    if vwap_value and vwap_value > 0:
        vwap_sep = abs(current_price - vwap_value) / vwap_value * 100
    # Breakout structure: price vs recent high/low
    recent_high = max(highs[-20:]) if len(highs) >= 20 else max(highs) if highs else current_price
    recent_low = min(lows[-20:]) if len(lows) >= 20 else min(lows) if lows else current_price
    near_high = current_price >= recent_high * 0.998 if recent_high > 0 else False
    near_low = current_price <= recent_low * 1.002 if recent_low > 0 else False
    breakout_structure = 1.0 if near_high else (-1.0 if near_low else 0)
    # Composite scores 0-100
    breakout_val = 0.5 + (0.5 if breakout_structure == 'breakout' else (-0.5 if breakout_structure == 'breakdown' else 0))
    momentum_score = min(100, max(0,
        20 * min(2.0, rel_vol) * 0.5 +
        25 * (0.5 + direction_strength * 0.5) +
        20 * min(2.0, vol_expansion) * 0.5 +
        15 * min(2.0, vwap_sep / 2.0) * 0.5 +
        20 * breakout_val
    ))
    trend_strength = (0.5 + direction_strength * 0.5) * 100 if direction_strength else 50
    volatility_score = min(100, vol_expansion * 50) if vol_expansion else 50
    return {
        'symbol': symbol,
        'momentum_score': round(momentum_score, 1),
        'trend_strength': round(trend_strength, 1),
        'volatility_score': round(volatility_score, 1),
        'relative_volume': round(rel_vol, 2),
        'direction_strength': round(direction_strength, 2),
        'vwap_separation_pct': round(vwap_sep, 2),
        'breakout_structure': 'breakout' if near_high else ('breakdown' if near_low else 'neutral'),
    }


def run_signal_engine(
    symbol: str,
    timeframe: str,
    indicators: Dict[str, Any],
    momentum_result: Dict[str, Any],
    current_price: float,
) -> List[Dict[str, Any]]:
    """
    Signal Engine: RSI, MACD, VWAP position, price trend, momentum strength,
    volume spikes, timeframe alignment -> actionable signal types.
    Each signal: symbol, timestamp, signal_type, confidence, price, trend_direction, timeframe.
    """
    signals = []
    ts = datetime.utcnow().isoformat() + 'Z'
    rsi = indicators.get('rsi', {})
    macd = indicators.get('macd', {})
    vwap = indicators.get('vwap', {})
    volume = indicators.get('volume', {})
    trend = indicators.get('trend', {})
    rsi_val = rsi.get('value', 50)
    above_vwap = vwap.get('above_vwap', True)
    vwap_val = vwap.get('value', current_price)
    macd_hist = macd.get('histogram', 0)
    vol_spike = volume.get('spike', False) or (volume.get('spike_ratio', 1) or 1) >= 1.5
    trend_dir = trend.get('direction', 'NEUTRAL')
    mom_score = momentum_result.get('momentum_score', 50)
    trend_strength = momentum_result.get('trend_strength', 50)

    # Bullish Momentum
    if rsi_val < 70 and (trend_dir == 'BULLISH' or trend_strength > 55) and above_vwap and (macd_hist is None or macd_hist >= 0):
        conf = min(95, 50 + (mom_score - 50) * 0.5 + (10 if vol_spike else 0))
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Bullish Momentum',
            'confidence': round(conf, 1), 'price': current_price, 'trend_direction': 'BULLISH', 'timeframe': timeframe,
        })
    # Bearish Momentum
    if rsi_val > 30 and (trend_dir == 'BEARISH' or trend_strength < 45) and not above_vwap and (macd_hist is None or macd_hist <= 0):
        conf = min(95, 50 + (50 - mom_score) * 0.5 + (10 if vol_spike else 0))
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Bearish Momentum',
            'confidence': round(conf, 1), 'price': current_price, 'trend_direction': 'BEARISH', 'timeframe': timeframe,
        })
    # VWAP Reclaim
    if above_vwap and (rsi_val < 65 or trend_dir == 'BULLISH'):
        dist_pct = vwap.get('distance_pct', 0) or 0
        if dist_pct >= -0.5 and dist_pct <= 2.0:  # just reclaimed zone
            signals.append({
                'symbol': symbol, 'timestamp': ts, 'signal_type': 'VWAP Reclaim',
                'confidence': round(55 + min(30, dist_pct * 5) + (10 if vol_spike else 0), 1),
                'price': current_price, 'trend_direction': 'BULLISH', 'timeframe': timeframe,
            })
    # VWAP Rejection
    if not above_vwap and (rsi_val > 35 or trend_dir == 'BEARISH'):
        dist_pct = vwap.get('distance_pct', 0) or 0
        if dist_pct <= 0.5 and dist_pct >= -2.0:
            signals.append({
                'symbol': symbol, 'timestamp': ts, 'signal_type': 'VWAP Rejection',
                'confidence': round(55 + min(30, abs(dist_pct) * 5) + (10 if vol_spike else 0), 1),
                'price': current_price, 'trend_direction': 'BEARISH', 'timeframe': timeframe,
            })
    # Breakout / Breakdown
    bs = momentum_result.get('breakout_structure', 'neutral')
    if bs == 'breakout' and above_vwap:
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Breakout',
            'confidence': round(60 + mom_score * 0.2, 1), 'price': current_price, 'trend_direction': 'BULLISH', 'timeframe': timeframe,
        })
    if bs == 'breakdown' and not above_vwap:
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Breakdown',
            'confidence': round(60 + (100 - mom_score) * 0.2, 1), 'price': current_price, 'trend_direction': 'BEARISH', 'timeframe': timeframe,
        })
    # Pullback Entry
    if rsi_val >= 35 and rsi_val <= 55 and trend_dir == 'BULLISH' and above_vwap:
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Pullback Entry',
            'confidence': round(50 + (vwap_val and abs(current_price - vwap_val) / current_price * 100 < 0.5 and 15 or 0), 1),
            'price': current_price, 'trend_direction': 'BULLISH', 'timeframe': timeframe,
        })
    # Trend Continuation
    if (trend_strength > 60 and above_vwap and trend_dir == 'BULLISH') or (trend_strength < 40 and not above_vwap and trend_dir == 'BEARISH'):
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Trend Continuation',
            'confidence': round(50 + abs(trend_strength - 50) * 0.4, 1), 'price': current_price,
            'trend_direction': trend_dir, 'timeframe': timeframe,
        })
    # Exhaustion Warning
    if (rsi_val >= 70 and above_vwap) or (rsi_val <= 30 and not above_vwap):
        signals.append({
            'symbol': symbol, 'timestamp': ts, 'signal_type': 'Exhaustion Warning',
            'confidence': round(60 + abs(rsi_val - 50) / 2, 1), 'price': current_price,
            'trend_direction': 'BEARISH' if rsi_val >= 70 else 'BULLISH', 'timeframe': timeframe,
        })
    return signals


def run_risk_reward_engine(
    symbol: str,
    entry_price: float,
    support: float,
    resistance: float,
    atr: float,
    vwap_value: float,
    direction: str,
) -> Dict[str, Any]:
    """
    Risk/Reward Engine: entry_price, stop_loss, take_profit_1, take_profit_2, risk_reward_ratio
    using ATR, VWAP distance, key levels, volatility.
    """
    if entry_price <= 0:
        return {'error': 'Invalid entry price'}
    atr = atr or entry_price * 0.02
    is_bull = direction.upper() in ('BULLISH', 'BUY', 'LONG', 'BULL')
    if is_bull:
        stop_loss = min(support, vwap_value if vwap_value else entry_price * 0.98, entry_price - 1.5 * atr)
        stop_loss = max(stop_loss, entry_price * 0.97)
        tp1 = entry_price + 1.0 * atr
        tp2 = min(resistance, entry_price + 2.0 * atr) if resistance > entry_price else entry_price + 2.0 * atr
    else:
        stop_loss = max(resistance, vwap_value if vwap_value else entry_price * 1.02, entry_price + 1.5 * atr)
        stop_loss = min(stop_loss, entry_price * 1.03)
        tp1 = entry_price - 1.0 * atr
        tp2 = max(support, entry_price - 2.0 * atr) if support > 0 and support < entry_price else entry_price - 2.0 * atr
    risk = abs(entry_price - stop_loss)
    reward1 = abs(tp1 - entry_price)
    reward2 = abs(tp2 - entry_price)
    rr1 = (reward1 / risk) if risk > 0 else 0
    rr2 = (reward2 / risk) if risk > 0 else 0
    return {
        'symbol': symbol,
        'entry_price': round(entry_price, 2),
        'stop_loss': round(stop_loss, 2),
        'take_profit_1': round(tp1, 2),
        'take_profit_2': round(tp2, 2),
        'risk_reward_ratio': round(rr2, 2),
        'risk_reward_tp1': round(rr1, 2),
        'risk_reward_tp2': round(rr2, 2),
        'direction': 'BULLISH' if is_bull else 'BEARISH',
    }


def run_trade_scoring(
    signals: List[Dict],
    momentum_result: Dict[str, Any],
    market_phase: str,
    vwap_above: bool,
    trend_alignment: bool,
    volume_confirmation: bool,
    key_level_proximity: bool,
) -> Dict[str, Any]:
    """
    Trade Scoring 0-100: trend alignment, momentum strength, VWAP position,
    volume confirmation, key level proximity, market phase.
    Categories: Weak (0-39), Moderate (40-59), Strong (60-79), High Probability (80-100).
    """
    score = 50.0
    score += 15 if trend_alignment else -10
    mom = momentum_result.get('momentum_score', 50)
    score += (mom - 50) * 0.2
    score += 10 if vwap_above else -5
    score += 10 if volume_confirmation else 0
    score += 8 if key_level_proximity else 0
    phase_bonus = {'Trending Up': 5, 'Trending Down': -5, 'Breakout Setup': 8, 'Reversal Risk': -8, 'Consolidation': 0}.get(market_phase, 0)
    score += phase_bonus
    if signals:
        best_conf = max(s.get('confidence', 0) for s in signals)
        score = (score + best_conf) / 2
    score = min(100, max(0, score))
    if score >= 80:
        category = 'High Probability'
    elif score >= 60:
        category = 'Strong'
    elif score >= 40:
        category = 'Moderate'
    else:
        category = 'Weak'
    return {
        'score': round(score, 1),
        'category': category,
        'breakdown': {
            'trend_alignment': trend_alignment,
            'momentum_strength': mom,
            'vwap_position': 'above' if vwap_above else 'below',
            'volume_confirmation': volume_confirmation,
            'key_level_proximity': key_level_proximity,
            'market_phase': market_phase,
        },
    }


def run_market_phase_detection(
    closes: List[float],
    vwap_above: bool,
    atr_current: float,
    atr_avg: float,
    above_ema_short: bool,
    above_ema_long: bool,
    support: float,
    resistance: float,
    current_price: float,
) -> Dict[str, Any]:
    """
    Market Phase: Trending Up, Trending Down, Consolidation, Breakout Setup, Reversal Risk.
    """
    if not closes or len(closes) < 20:
        return {'phase': 'Consolidation', 'confidence': 0, 'description': 'Insufficient data'}
    n = len(closes)
    short_slope = (closes[-1] - closes[-5]) / closes[-5] * 100 if n >= 5 and closes[-5] else 0
    long_slope = (closes[-1] - closes[-20]) / closes[-20] * 100 if n >= 20 and closes[-20] else 0
    atr_expansion = (atr_current / atr_avg) if atr_avg and atr_avg > 0 else 1.0
    range_pct = (resistance - support) / current_price * 100 if (support and resistance and current_price) else 1.0

    if above_ema_short and above_ema_long and short_slope > 0.2 and long_slope > 0.1:
        phase = 'Trending Up'
        desc = 'Price above key MAs with positive slope'
    elif not above_ema_short and not above_ema_long and short_slope < -0.2 and long_slope < -0.1:
        phase = 'Trending Down'
        desc = 'Price below key MAs with negative slope'
    elif atr_expansion > 1.2 and (short_slope > 0.3 or short_slope < -0.3):
        phase = 'Breakout Setup'
        desc = 'Volatility expansion with directional move'
    elif (short_slope > 0.3 and long_slope < -0.2) or (short_slope < -0.3 and long_slope > 0.2):
        phase = 'Reversal Risk'
        desc = 'Short-term vs long-term divergence'
    else:
        phase = 'Consolidation'
        desc = 'Range-bound; wait for breakout or breakdown'
    confidence = min(95, 50 + abs(short_slope) * 20 + (15 if atr_expansion > 1.1 else 0))
    return {
        'phase': phase,
        'confidence': round(confidence, 1),
        'description': desc,
        'short_slope_pct': round(short_slope, 2),
        'long_slope_pct': round(long_slope, 2),
        'atr_expansion': round(atr_expansion, 2),
    }


def get_full_trading_intelligence(
    symbol: str,
    timeframe: str,
    market_data: Dict[str, Any],
    indicators: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Orchestrate: momentum scanner -> signal engine -> risk/reward -> scoring -> market phase.
    Returns one payload for the dashboard; all keyed by symbol.
    """
    closes = market_data.get('closes', [])
    volumes = market_data.get('volumes', [])
    highs = market_data.get('highs', closes)
    lows = market_data.get('lows', closes)
    opens = market_data.get('opens', closes)
    current_price = market_data.get('current_price') or (closes[-1] if closes else 0)
    vwap = indicators.get('vwap', {})
    atr_val = indicators.get('atr', {}).get('value') or indicators.get('atr', 0)
    if isinstance(atr_val, dict):
        atr_val = atr_val.get('value', 0)
    sr = indicators.get('support_resistance', {})
    support = sr.get('support', current_price * 0.98)
    resistance = sr.get('resistance', current_price * 1.02)
    vwap_value = vwap.get('value', current_price)
    above_vwap = vwap.get('above_vwap', True)

    momentum_result = run_momentum_scanner(
        symbol, closes, volumes, highs, lows, opens,
        vwap_value, atr_val or current_price * 0.02, current_price,
    )
    signals = run_signal_engine(symbol, timeframe, indicators, momentum_result, current_price)
    market_phase_result = run_market_phase_detection(
        closes, above_vwap, atr_val or 0, atr_val or 0,
        indicators.get('ema', {}).get('above_13', True),
        indicators.get('ema', {}).get('above_48', True),
        support, resistance, current_price,
    )
    direction = 'BULLISH' if (signals and signals[0].get('trend_direction') == 'BULLISH') or above_vwap else 'BEARISH'
    rr = run_risk_reward_engine(symbol, current_price, support, resistance, atr_val, vwap_value, direction)
    scoring = run_trade_scoring(
        signals, momentum_result, market_phase_result.get('phase', 'Consolidation'),
        above_vwap,
        indicators.get('trend', {}).get('direction') in ('BULLISH', 'BEARISH'),
        (indicators.get('volume', {}).get('spike_ratio') or 1) >= 1.2,
        current_price <= support * 1.01 or current_price >= resistance * 0.99,
    )
    # Attach score to each signal for feed
    for s in signals:
        s['trade_score'] = scoring.get('score', 50)
        s['score_category'] = scoring.get('category', 'Moderate')

    # Step 6: Strategy patterns + recommendation + confidence
    patterns = []
    recommendation = {}
    final_confidence = scoring.get('score', 50)
    try:
        from services.strategy_intelligence import (
            detect_strategy_patterns,
            strategy_recommendation_engine,
            confidence_engine,
            trade_journal_log,
        )
        patterns = detect_strategy_patterns(
            symbol, indicators, momentum_result, market_phase_result.get('phase', ''),
            closes, vwap_value, current_price,
        )
        recommendation = strategy_recommendation_engine(
            symbol, signals, patterns, rr, market_phase_result.get('phase', ''),
        )
        vol_state = 'high' if (momentum_result.get('volatility_score', 0) or 0) > 60 else 'low' if (momentum_result.get('volatility_score', 0) or 0) < 40 else 'normal'
        final_confidence = confidence_engine(
            momentum_result.get('momentum_score', 50),
            scoring.get('score', 50),
            vol_state,
            market_phase_result.get('phase', ''),
        )
        if signals and signals[0].get('confidence', 0) >= 60:
            trade_journal_log(
                symbol, signals[0].get('signal_type', 'Signal'),
                signals[0].get('trend_direction', 'NEUTRAL'),
                current_price, rr.get('stop_loss'), rr.get('take_profit_1'), rr.get('take_profit_2'),
                scoring.get('score', 50),
            )
    except Exception as e:
        logger.debug('Strategy intelligence: %s', e)

    return {
        'symbol': symbol,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'timeframe': timeframe,
        'signals': signals,
        'momentum': momentum_result,
        'risk_reward': rr,
        'trade_scoring': scoring,
        'market_phase': market_phase_result,
        'current_price': current_price,
        'strategy_patterns': patterns,
        'strategy_recommendation': recommendation,
        'final_confidence': final_confidence,
    }
