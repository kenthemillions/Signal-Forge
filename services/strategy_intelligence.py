"""
Step 6: Strategy Intelligence Layer
Pattern recognition, recommendation engine, position risk manager, trade journal, confidence engine.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import json
import os

logger = logging.getLogger(__name__)

# In-memory trade journal (persist to DB in production)
_trade_journal: List[Dict[str, Any]] = []
JOURNAL_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'trade_journal.json')


def _ensure_journal_dir():
    d = os.path.dirname(JOURNAL_PATH)
    if d and not os.path.isdir(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass


def detect_strategy_patterns(
    symbol: str,
    indicators: Dict[str, Any],
    momentum: Dict[str, Any],
    market_phase: str,
    closes: List[float],
    vwap_value: float,
    current_price: float,
) -> List[Dict[str, Any]]:
    """
    Strategy pattern recognition: VWAP bounce, VWAP rejection, trend pullback continuation,
    opening range breakout, failed breakout reversal, momentum expansion.
    """
    patterns = []
    if not closes or len(closes) < 10:
        return patterns
    vwap = indicators.get('vwap', {})
    above_vwap = vwap.get('above_vwap', True)
    rsi = indicators.get('rsi', {}).get('value', 50)
    trend = indicators.get('trend', {}).get('direction', 'NEUTRAL')
    bs = momentum.get('breakout_structure', 'neutral')

    # VWAP bounce: price near/below VWAP and bouncing
    if vwap_value and current_price <= vwap_value * 1.005 and rsi < 45 and trend == 'BULLISH':
        patterns.append({'pattern': 'VWAP Bounce', 'direction': 'BULLISH', 'confidence': 65})
    # VWAP rejection: price near/above VWAP and rejecting
    if vwap_value and current_price >= vwap_value * 0.995 and rsi > 55 and trend == 'BEARISH':
        patterns.append({'pattern': 'VWAP Rejection', 'direction': 'BEARISH', 'confidence': 65})
    # Trend pullback continuation
    if trend in ('BULLISH', 'BEARISH') and 40 <= rsi <= 60:
        patterns.append({'pattern': 'Trend Pullback Continuation', 'direction': trend, 'confidence': 60})
    # Opening range breakout
    if bs == 'breakout' and market_phase == 'Breakout Setup':
        patterns.append({'pattern': 'Opening Range Breakout', 'direction': 'BULLISH', 'confidence': 70})
    if bs == 'breakdown' and market_phase == 'Breakout Setup':
        patterns.append({'pattern': 'Opening Range Breakdown', 'direction': 'BEARISH', 'confidence': 70})
    # Failed breakout reversal (was near high, now dropping)
    if bs == 'neutral' and momentum.get('trend_strength', 50) < 45 and above_vwap and rsi < 50:
        patterns.append({'pattern': 'Failed Breakout Reversal', 'direction': 'BEARISH', 'confidence': 55})
    # Momentum expansion
    if momentum.get('volatility_score', 0) > 60 and momentum.get('momentum_score', 0) > 60:
        patterns.append({'pattern': 'Momentum Expansion', 'direction': trend if trend != 'NEUTRAL' else 'BULLISH', 'confidence': 65})
    return patterns


def strategy_recommendation_engine(
    symbol: str,
    signals: List[Dict],
    patterns: List[Dict],
    risk_reward: Dict[str, Any],
    market_phase: str,
) -> Dict[str, Any]:
    """
    Convert signals and market phase into actionable suggestions: direction, entry zones, stop, targets.
    """
    direction = 'NEUTRAL'
    entry_zone = (0, 0)
    stop = 0
    targets = []
    if risk_reward and not risk_reward.get('error'):
        direction = risk_reward.get('direction', 'NEUTRAL')
        entry_zone = (risk_reward.get('entry_price', 0), risk_reward.get('entry_price', 0))
        stop = risk_reward.get('stop_loss', 0)
        targets = [risk_reward.get('take_profit_1'), risk_reward.get('take_profit_2')]
    if signals:
        s = signals[0]
        direction = s.get('trend_direction', direction)
    if patterns:
        p = patterns[0]
        direction = p.get('direction', direction)
    return {
        'symbol': symbol,
        'suggested_direction': direction,
        'entry_zone': entry_zone,
        'stop_placement': stop,
        'profit_targets': targets,
        'market_phase': market_phase,
        'pattern_count': len(patterns),
        'signal_count': len(signals),
    }


def position_risk_manager(
    account_risk_pct: float,
    entry_price: float,
    stop_loss: float,
    account_size: float,
) -> Dict[str, Any]:
    """
    Trade size recommendation based on ATR risk and user-defined account risk %.
    """
    if account_size <= 0 or entry_price <= 0:
        return {'error': 'Invalid inputs', 'position_size': 0}
    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share <= 0:
        return {'position_size': 0, 'risk_amount': 0, 'risk_reward_note': 'No stop distance'}
    risk_amount = account_size * (account_risk_pct / 100)
    shares = int(risk_amount / risk_per_share)
    return {
        'position_size': shares,
        'risk_amount': round(risk_amount, 2),
        'risk_per_share': round(risk_per_share, 2),
        'account_risk_pct': account_risk_pct,
        'account_size': account_size,
    }


def trade_journal_log(
    symbol: str,
    signal_type: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: float,
    score: float,
    outcome: Optional[str] = None,
    outcome_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Record a trade setup for historical performance."""
    entry = {
        'symbol': symbol,
        'signal_type': signal_type,
        'direction': direction,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit_1': take_profit_1,
        'take_profit_2': take_profit_2,
        'score': score,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'outcome': outcome,
        'outcome_price': outcome_price,
    }
    _trade_journal.append(entry)
    try:
        _ensure_journal_dir()
        with open(JOURNAL_PATH, 'w') as f:
            json.dump(_trade_journal[-500:], f, indent=0)
    except Exception as e:
        logger.debug('Journal save failed: %s', e)
    return entry


def get_trade_journal(symbol: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return journal entries, optionally filtered by symbol."""
    try:
        if os.path.isfile(JOURNAL_PATH):
            with open(JOURNAL_PATH) as f:
                _trade_journal.clear()
                _trade_journal.extend(json.load(f))
    except Exception:
        pass
    out = _trade_journal[-limit:]
    if symbol:
        out = [e for e in out if (e.get('symbol') or '').upper() == symbol.upper()]
    return out


def confidence_engine(
    momentum_score: float,
    signal_score: float,
    volatility_state: str,
    market_phase: str,
) -> float:
    """
    Aggregate momentum score, signal score, volatility state, market phase -> final confidence 0-100.
    """
    conf = (momentum_score + signal_score) / 2
    if volatility_state == 'high':
        conf += 5
    elif volatility_state == 'low':
        conf -= 5
    phase_adj = {'Trending Up': 5, 'Trending Down': 0, 'Breakout Setup': 8, 'Reversal Risk': -5, 'Consolidation': -2}.get(market_phase, 0)
    conf += phase_adj
    return min(100, max(0, round(conf, 1)))
