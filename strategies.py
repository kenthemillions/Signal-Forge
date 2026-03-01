"""
Trading Strategies Module
Time-based strategies and signal generation
"""
from datetime import datetime, time, timedelta
from typing import Dict, Any
import pytz

class StrategyOrchestrator:
    """Orchestrates trading strategies and generates signals"""
    
    def __init__(self):
        self.eastern = pytz.timezone('US/Eastern')
        
        # Define trading sessions
        self.sessions = {
            'PRE_MARKET': (time(4, 0), time(9, 30)),
            'MARKET_OPEN': (time(9, 30), time(10, 30)),
            'MID_MORNING': (time(10, 30), time(11, 30)),
            'MID_DAY': (time(11, 30), time(14, 0)),
            'AFTERNOON': (time(14, 0), time(15, 0)),
            'END_OF_DAY': (time(15, 0), time(15, 55)),
            'LOTTERY_HOUR': (time(15, 55), time(16, 0)),
            'AFTER_HOURS': (time(16, 0), time(20, 0)),
            'CLOSED': (time(20, 0), time(4, 0))
        }
        
        # Strategy weights by session
        self.session_weights = {
            'MARKET_OPEN': {'momentum': 1.5, 'volume': 1.5, 'reversal': 0.5},
            'MID_DAY': {'momentum': 0.8, 'volume': 0.8, 'reversal': 1.2},
            'END_OF_DAY': {'momentum': 1.2, 'volume': 1.0, 'reversal': 1.0},
            'LOTTERY_HOUR': {'momentum': 2.0, 'volume': 2.0, 'reversal': 0.3}
        }
    
    def get_current_session(self) -> str:
        """Get the current trading session"""
        now = datetime.now(self.eastern)
        current_time = now.time()
        
        for session, (start, end) in self.sessions.items():
            if session == 'CLOSED':
                if current_time >= start or current_time < end:
                    return session
            elif start <= current_time < end:
                return session
        
        return 'CLOSED'
    
    def get_market_status(self) -> Dict:
        """Get current market status and session info"""
        now = datetime.now(self.eastern)
        current_time = now.time()
        session = self.get_current_session()
        
        # Check if it's a weekend
        is_weekend = now.weekday() >= 5
        
        # Get session times
        session_info = self.sessions.get(session, (time(0, 0), time(0, 0)))
        
        # Calculate time until next session
        next_session = self._get_next_session(session)
        time_until_next = self._time_until(session_info[1]) if session != 'CLOSED' else self._time_until(time(9, 30))
        
        # Calculate countdown for key times
        countdowns = {
            'market_open': self._time_until(time(9, 30)) if current_time < time(9, 30) else None,
            'market_close': self._time_until(time(16, 0)) if time(9, 30) <= current_time < time(16, 0) else None,
            'lottery_hour': self._time_until(time(15, 55)) if time(9, 30) <= current_time < time(15, 55) else None,
            'session_end': self._time_until(session_info[1]) if session not in ['CLOSED', 'AFTER_HOURS'] else None
        }
        
        return {
            'current_session': session,
            'is_market_open': session not in ['PRE_MARKET', 'AFTER_HOURS', 'CLOSED'],
            'is_weekend': is_weekend,
            'current_time': now.strftime('%H:%M:%S ET'),
            'next_session': next_session,
            'time_until_next': time_until_next,
            'countdowns': countdowns,
            'session_description': self._get_session_description(session)
        }
    
    def _get_next_session(self, current: str) -> str:
        """Get the next trading session"""
        order = ['MARKET_OPEN', 'MID_MORNING', 'MID_DAY', 'AFTERNOON', 'END_OF_DAY', 'LOTTERY_HOUR', 'AFTER_HOURS', 'CLOSED']
        try:
            idx = order.index(current)
            return order[(idx + 1) % len(order)]
        except ValueError:
            return 'MARKET_OPEN'
    
    def _time_until(self, target: time) -> str:
        """Calculate time until a target time"""
        now = datetime.now(self.eastern)
        target_dt = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)
        
        if target_dt < now:
            target_dt = target_dt + timedelta(days=1)
        
        diff = target_dt - now
        hours, remainder = divmod(int(diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def _get_session_description(self, session: str) -> str:
        """Get human-readable session description"""
        descriptions = {
            'PRE_MARKET': 'Pre-Market: Wait for market open',
            'MARKET_OPEN': 'Market Open: High volatility, momentum trades favored',
            'MID_MORNING': 'Mid-Morning: Trend continuation possible',
            'MID_DAY': 'Mid-Day: Lower volatility, range-bound trading',
            'AFTERNOON': 'Afternoon: Building momentum for close',
            'END_OF_DAY': 'End of Day: Position for close, high conviction trades',
            'LOTTERY_HOUR': 'Lottery Hour: Extreme moves possible, high risk/reward',
            'AFTER_HOURS': 'After Hours: Limited liquidity',
            'CLOSED': 'Market Closed'
        }
        return descriptions.get(session, 'Unknown session')
    
    def generate_signal(self, symbol: str, indicators: Dict, market_data: Dict, settings=None) -> Dict:
        """Generate a trading signal based on indicators and current session"""
        session = self.get_current_session()
        weights = self.session_weights.get(session, {'momentum': 1.0, 'volume': 1.0, 'reversal': 1.0})
        
        # Extract indicator values
        rsi = indicators.get('rsi', {})
        macd = indicators.get('macd', {})
        bollinger = indicators.get('bollinger', {})
        volume = indicators.get('volume', {})
        sr = indicators.get('support_resistance', {})
        current_price = indicators.get('current_price', 0)
        
        # Calculate individual scores (-2 to +2)
        scores = []
        reasons = []
        
        # RSI Score
        rsi_value = rsi.get('value', 50)
        rsi_signal = rsi.get('signal', 'NEUTRAL')
        if rsi_signal == 'OVERSOLD':
            scores.append(2 * weights.get('reversal', 1))
            reasons.append(f"RSI oversold ({rsi_value:.1f})")
        elif rsi_signal == 'OVERBOUGHT':
            scores.append(-2 * weights.get('reversal', 1))
            reasons.append(f"RSI overbought ({rsi_value:.1f})")
        elif rsi_value < 45:
            scores.append(-0.5)
            reasons.append(f"RSI weak ({rsi_value:.1f})")
        elif rsi_value > 55:
            scores.append(0.5)
            reasons.append(f"RSI strong ({rsi_value:.1f})")
        
        # MACD Score
        macd_signal = macd.get('signal_type', 'NEUTRAL')
        histogram = macd.get('histogram', 0)
        if macd_signal == 'BULLISH':
            scores.append(1.5 * weights.get('momentum', 1))
            reasons.append("MACD bullish")
        elif macd_signal == 'BEARISH':
            scores.append(-1.5 * weights.get('momentum', 1))
            reasons.append("MACD bearish")
        elif macd_signal == 'BULLISH_CROSS':
            scores.append(1 * weights.get('momentum', 1))
            reasons.append("MACD bullish crossover")
        elif macd_signal == 'BEARISH_CROSS':
            scores.append(-1 * weights.get('momentum', 1))
            reasons.append("MACD bearish crossover")
        
        # Bollinger Bands Score
        bb_signal = bollinger.get('signal', 'NEUTRAL')
        bb_position = bollinger.get('price_position', 'NEUTRAL')
        if bb_signal == 'OVERSOLD':
            scores.append(1.5 * weights.get('reversal', 1))
            reasons.append("Price at lower Bollinger Band")
        elif bb_signal == 'OVERBOUGHT':
            scores.append(-1.5 * weights.get('reversal', 1))
            reasons.append("Price at upper Bollinger Band")
        
        # Volume Score
        volume_spike = volume.get('spike', False)
        if volume_spike:
            spike_ratio = volume.get('spike_ratio', 1)
            scores.append(1 * weights.get('volume', 1))
            reasons.append(f"Volume spike ({spike_ratio:.1f}x avg)")
        
        # Support/Resistance Score
        near_support = sr.get('near_support', False)
        near_resistance = sr.get('near_resistance', False)
        if near_support:
            scores.append(1 * weights.get('reversal', 1))
            reasons.append(f"Near support (${sr.get('support', 0):.2f})")
        if near_resistance:
            scores.append(-1 * weights.get('reversal', 1))
            reasons.append(f"Near resistance (${sr.get('resistance', 0):.2f})")
        
        # Real-time Price Momentum Score (premarket/afterhours - higher weight)
        change_percent = market_data.get('change_percent', 0)
        premarket_boost = 2.0 if session in ['PRE_MARKET', 'AFTER_HOURS'] else 1.0
        if change_percent:
            if change_percent >= 1.0:
                scores.append(4.0 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"STRONG upward momentum (+{change_percent:.2f}%)")
            elif change_percent >= 0.4:
                scores.append(3.0 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"Positive momentum (+{change_percent:.2f}%)")
            elif change_percent >= 0.15:
                scores.append(1.5 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"Mild upward momentum (+{change_percent:.2f}%)")
            elif change_percent <= -1.0:
                scores.append(-4.0 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"STRONG downward momentum ({change_percent:.2f}%)")
            elif change_percent <= -0.4:
                scores.append(-3.0 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"Negative momentum ({change_percent:.2f}%)")
            elif change_percent <= -0.15:
                scores.append(-1.5 * premarket_boost * weights.get('momentum', 1))
                reasons.append(f"Mild downward momentum ({change_percent:.2f}%)")
        
        # VWAP Score
        vwap = indicators.get('vwap', {})
        vwap_signal = vwap.get('signal', 'NEUTRAL')
        vwap_value = vwap.get('value', 0)
        above_vwap = vwap.get('above_vwap', False)
        
        if vwap_signal == 'BULLISH':
            scores.append(1.5 * weights.get('momentum', 1))
            reasons.append(f"Price above VWAP (${vwap_value:.2f})")
        elif vwap_signal == 'BEARISH':
            scores.append(-1.5 * weights.get('momentum', 1))
            reasons.append(f"Price below VWAP (${vwap_value:.2f})")
        elif vwap_signal == 'OVERSOLD':
            scores.append(1 * weights.get('reversal', 1))
            reasons.append(f"Extended below VWAP - potential bounce")
        elif vwap_signal == 'OVERBOUGHT':
            scores.append(-1 * weights.get('reversal', 1))
            reasons.append(f"Extended above VWAP - potential pullback")
        
        # Calculate total score
        total_score = sum(scores) if scores else 0
        max_possible = len(scores) * 2 if scores else 1
        strength = min(100, max(0, (total_score / max_possible + 1) * 50)) if max_possible > 0 else 50
        
        # Determine signal type
        if total_score >= 3:
            signal_type = 'STRONG_BUY'
        elif total_score >= 1.5:
            signal_type = 'BUY'
        elif total_score <= -3:
            signal_type = 'STRONG_SELL'
        elif total_score <= -1.5:
            signal_type = 'SELL'
        else:
            signal_type = 'NEUTRAL'
        
        # Determine entry recommendation
        if signal_type in ['STRONG_BUY', 'BUY']:
            entry_action = 'ENTER LONG'
            direction = 'BULLISH'
            entry_alert = signal_type == 'STRONG_BUY'
        elif signal_type in ['STRONG_SELL', 'SELL']:
            entry_action = 'ENTER SHORT'
            direction = 'BEARISH'
            entry_alert = signal_type == 'STRONG_SELL'
        else:
            entry_action = 'WAIT'
            direction = 'NEUTRAL'
            entry_alert = False
        
        return {
            'symbol': symbol,
            'type': signal_type,
            'strength': float(round(strength, 1)),
            'score': float(round(total_score, 2)),
            'price': float(current_price) if current_price else 0.0,
            'session': session,
            'strategy': session,
            'reasons': reasons,
            'direction': direction,
            'entry_action': entry_action,
            'entry_alert': entry_alert,
            'indicators': {
                'rsi': float(rsi_value) if rsi_value else 50.0,
                'macd_histogram': float(histogram) if histogram else 0.0,
                'bb_position': bb_position,
                'volume_spike': bool(volume_spike),
                'near_support': bool(near_support),
                'near_resistance': bool(near_resistance),
                'above_vwap': bool(above_vwap)
            },
            'timestamp': datetime.now(self.eastern).isoformat()
        }
    
    def analyze_multi_timeframe(self, symbol: str, mtf_data: Dict, indicator_engine, institutional_data: Dict) -> Dict:
        """
        Comprehensive multi-timeframe analysis
        Checks confluence across 1m, 5m, 15m and confirms with 1h/4h trends
        """
        timeframes = mtf_data.get('timeframes', {})
        
        tf_analysis = {}
        tf_trends = {'1m': None, '5m': None, '15m': None, '1h': None, '4h': None}
        
        for tf_name, tf_data in timeframes.items():
            if tf_data and 'closes' in tf_data and len(tf_data['closes']) > 0:
                indicators = indicator_engine.calculate_all(tf_data, None)
                trend = indicators.get('trend', {}).get('direction', 'NEUTRAL')
                momentum = indicators.get('momentum', {}).get('signal', 'NEUTRAL')
                rsi = indicators.get('rsi', {})
                macd = indicators.get('macd', {})
                vwap = indicators.get('vwap', {})
                
                tf_analysis[tf_name] = {
                    'trend': trend,
                    'momentum': momentum,
                    'rsi': rsi.get('value', 50),
                    'rsi_signal': rsi.get('signal', 'NEUTRAL'),
                    'macd_signal': macd.get('signal_type', 'NEUTRAL'),
                    'above_vwap': vwap.get('above_vwap', False),
                    'price': tf_data.get('current_price', 0)
                }
                tf_trends[tf_name] = trend
        
        short_term_bullish = 0
        short_term_bearish = 0
        for tf in ['1m', '5m', '15m']:
            if tf in tf_analysis:
                if tf_analysis[tf]['trend'] == 'BULLISH':
                    short_term_bullish += 1
                elif tf_analysis[tf]['trend'] == 'BEARISH':
                    short_term_bearish += 1
                
                if 'BULLISH' in tf_analysis[tf].get('momentum', ''):
                    short_term_bullish += 0.5
                elif 'BEARISH' in tf_analysis[tf].get('momentum', ''):
                    short_term_bearish += 0.5
        
        higher_tf_bullish = 0
        higher_tf_bearish = 0
        for tf in ['1h', '4h']:
            if tf in tf_analysis:
                if tf_analysis[tf]['trend'] == 'BULLISH':
                    higher_tf_bullish += 1
                elif tf_analysis[tf]['trend'] == 'BEARISH':
                    higher_tf_bearish += 1
        
        confluence_score = 0
        confluence_signals = []
        
        if short_term_bullish >= 2:
            confluence_score += 2
            confluence_signals.append(f"Short-term bullish ({int(short_term_bullish)}/3 timeframes)")
        elif short_term_bearish >= 2:
            confluence_score -= 2
            confluence_signals.append(f"Short-term bearish ({int(short_term_bearish)}/3 timeframes)")
        
        if higher_tf_bullish >= 1:
            confluence_score += 1.5
            confluence_signals.append("Higher timeframe bullish confirmation")
        elif higher_tf_bearish >= 1:
            confluence_score -= 1.5
            confluence_signals.append("Higher timeframe bearish confirmation")
        
        inst = institutional_data
        if inst.get('detected'):
            if inst.get('activity') == 'INSTITUTIONAL_BUYING':
                confluence_score += 2
                confluence_signals.append(f"Institutional BUYING detected ({inst.get('confidence')}% confidence)")
            elif inst.get('activity') == 'INSTITUTIONAL_SELLING':
                confluence_score -= 2
                confluence_signals.append(f"Institutional SELLING detected ({inst.get('confidence')}% confidence)")
            elif inst.get('activity') == 'HIGH_ACTIVITY':
                confluence_signals.append("Heavy institutional activity detected")
        
        if '5m' in tf_analysis:
            rsi_5m = tf_analysis['5m'].get('rsi', 50)
            if rsi_5m < 30:
                confluence_score += 1
                confluence_signals.append(f"5m RSI oversold ({rsi_5m:.1f})")
            elif rsi_5m > 70:
                confluence_score -= 1
                confluence_signals.append(f"5m RSI overbought ({rsi_5m:.1f})")
        
        vwap_alignment = 0
        for tf in ['1m', '5m', '15m']:
            if tf in tf_analysis and tf_analysis[tf].get('above_vwap'):
                vwap_alignment += 1
        
        if vwap_alignment >= 2:
            confluence_score += 1
            confluence_signals.append("Price above VWAP on multiple timeframes")
        elif vwap_alignment == 0:
            confluence_score -= 1
            confluence_signals.append("Price below VWAP on all timeframes")
        
        if confluence_score >= 4:
            overall_signal = 'STRONG_BUY'
            direction = 'BULLISH'
            entry_action = 'ENTER LONG'
            entry_alert = True
        elif confluence_score >= 2:
            overall_signal = 'BUY'
            direction = 'BULLISH'
            entry_action = 'CONSIDER LONG'
            entry_alert = False
        elif confluence_score <= -4:
            overall_signal = 'STRONG_SELL'
            direction = 'BEARISH'
            entry_action = 'ENTER SHORT'
            entry_alert = True
        elif confluence_score <= -2:
            overall_signal = 'SELL'
            direction = 'BEARISH'
            entry_action = 'CONSIDER SHORT'
            entry_alert = False
        else:
            overall_signal = 'NEUTRAL'
            direction = 'NEUTRAL'
            entry_action = 'WAIT'
            entry_alert = False
        
        strength = min(100, max(0, 50 + confluence_score * 10))
        
        return {
            'symbol': symbol,
            'overall_signal': overall_signal,
            'direction': direction,
            'entry_action': entry_action,
            'entry_alert': entry_alert,
            'strength': float(round(strength, 1)),
            'confluence_score': float(round(confluence_score, 2)),
            'timeframe_analysis': tf_analysis,
            'timeframe_trends': tf_trends,
            'short_term_bullish': float(short_term_bullish),
            'short_term_bearish': float(short_term_bearish),
            'higher_tf_bullish': int(higher_tf_bullish),
            'higher_tf_bearish': int(higher_tf_bearish),
            'institutional': institutional_data,
            'confluence_signals': confluence_signals,
            'vwap_alignment': int(vwap_alignment),
            'timestamp': datetime.now(self.eastern).isoformat()
        }
