"""
Institutional Mode Analysis Engine
Multi-timeframe analysis with WAIT/PREPARE/BUY/SELL state machine
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, time
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ZoneInfo:
    level: float
    zone_type: str
    strength: int
    rejections: int
    last_test: Optional[datetime] = None


@dataclass
class InstitutionalSignal:
    state: str
    confidence: int
    bias: str
    reasons: List[str]
    waiting_for: List[str]
    regime: str
    location: str
    zone_status: str
    confirmations: Dict[str, bool]
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    risk_reward: Optional[float] = None


class InstitutionalEngine:
    """
    Core institutional analysis engine implementing:
    - Multi-timeframe analysis
    - Market regime detection (TREND vs RANGE/DISTRIBUTION)
    - Supply/demand zone detection with rejection tracking
    - WAIT/PREPARE/BUY/SELL state machine
    - Session filters
    """
    
    def __init__(self):
        self.ema_periods = [13, 48, 200]
        self.rsi_period = 14
        self.atr_period = 14
        self.volume_avg_period = 20
        self.zone_threshold = 0.005
        self.zone_lookback = 50
        
    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str = '5m',
                session_rules: Optional[Dict] = None) -> InstitutionalSignal:
        """
        Run full institutional analysis on price data
        """
        if df is None or len(df) < 50:
            return self._empty_signal()
        
        try:
            df = self._calculate_indicators(df)
            regime = self._detect_regime(df)
            zones = self._detect_zones(df)
            location = self._determine_location(df, zones)
            confirmations = self._check_confirmations(df, regime, location)
            
            if session_rules and not self._is_trading_allowed(session_rules):
                return self._create_signal(
                    state='WAIT',
                    confidence=0,
                    bias='NEUTRAL',
                    reasons=['Outside trading hours - no trades allowed'],
                    waiting_for=['Trading window to open'],
                    regime=regime,
                    location=location,
                    zone_status=zones.get('status', 'MIDDLE'),
                    confirmations=confirmations,
                    df=df
                )
            
            state, confidence, bias, reasons, waiting_for = self._determine_state(
                df, regime, location, zones, confirmations
            )
            
            return self._create_signal(
                state=state,
                confidence=confidence,
                bias=bias,
                reasons=reasons,
                waiting_for=waiting_for,
                regime=regime,
                location=location,
                zone_status=zones.get('status', 'MIDDLE'),
                confirmations=confirmations,
                df=df
            )
            
        except Exception as e:
            logger.error(f"Institutional analysis error: {e}")
            return self._empty_signal()
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all required indicators"""
        df = df.copy()
        
        for period in self.ema_periods:
            df[f'ema_{period}'] = df['Close'].ewm(span=period, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, 0.0001)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()
        
        df['volume_avg'] = df['Volume'].rolling(window=self.volume_avg_period).mean()
        df['volume_spike'] = df['Volume'] > (df['volume_avg'] * 1.5)
        
        df['typical_price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['vwap'] = (df['typical_price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        
        df['rsi_prev'] = df['rsi'].shift(5)
        df['price_prev'] = df['Close'].shift(5)
        df['bullish_divergence'] = (df['Close'] < df['price_prev']) & (df['rsi'] > df['rsi_prev'])
        df['bearish_divergence'] = (df['Close'] > df['price_prev']) & (df['rsi'] < df['rsi_prev'])
        
        return df
    
    def _detect_regime(self, df: pd.DataFrame) -> str:
        """Detect market regime: TREND or RANGE"""
        if len(df) < 20:
            return 'UNKNOWN'
        
        recent = df.tail(20)
        close = recent['Close'].values
        ema_200 = recent['ema_200'].values[-1] if 'ema_200' in df.columns else close.mean()
        
        highs = []
        lows = []
        for i in range(2, len(close) - 2):
            if close[i] > close[i-1] and close[i] > close[i-2] and close[i] > close[i+1] and close[i] > close[i+2]:
                highs.append(close[i])
            if close[i] < close[i-1] and close[i] < close[i-2] and close[i] < close[i+1] and close[i] < close[i+2]:
                lows.append(close[i])
        
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2] if len(highs) >= 2 else False
            hl = lows[-1] > lows[-2] if len(lows) >= 2 else False
            ll = lows[-1] < lows[-2] if len(lows) >= 2 else False
            lh = highs[-1] < highs[-2] if len(highs) >= 2 else False
            
            current_price = close[-1]
            
            if (hh and hl) and current_price > ema_200:
                return 'TREND_UP'
            elif (ll and lh) and current_price < ema_200:
                return 'TREND_DOWN'
        
        ema_13 = df['ema_13'].tail(10).values
        ema_slope = (ema_13[-1] - ema_13[0]) / ema_13[0] * 100
        
        if abs(ema_slope) < 0.3:
            return 'RANGE'
        
        price_range = (recent['High'].max() - recent['Low'].min()) / recent['Close'].mean()
        if price_range < 0.02:
            return 'RANGE'
        
        return 'DISTRIBUTION'
    
    def _detect_zones(self, df: pd.DataFrame) -> Dict:
        """Detect supply and demand zones using swing high/low clustering"""
        if len(df) < self.zone_lookback:
            return {'supply': [], 'demand': [], 'status': 'MIDDLE'}
        
        recent = df.tail(self.zone_lookback)
        close = recent['Close'].values
        high = recent['High'].values
        low = recent['Low'].values
        current_price = close[-1]
        
        swing_highs = []
        swing_lows = []
        
        for i in range(2, len(close) - 2):
            if high[i] > high[i-1] and high[i] > high[i-2] and high[i] > high[i+1] and high[i] > high[i+2]:
                swing_highs.append(high[i])
            if low[i] < low[i-1] and low[i] < low[i-2] and low[i] < low[i+1] and low[i] < low[i+2]:
                swing_lows.append(low[i])
        
        def cluster_levels(levels: List[float], threshold: float) -> List[float]:
            if not levels:
                return []
            sorted_levels = sorted(levels)
            clusters = []
            current_cluster = [sorted_levels[0]]
            
            for level in sorted_levels[1:]:
                if abs(level - current_cluster[-1]) / current_cluster[-1] < threshold:
                    current_cluster.append(level)
                else:
                    clusters.append(sum(current_cluster) / len(current_cluster))
                    current_cluster = [level]
            
            if current_cluster:
                clusters.append(sum(current_cluster) / len(current_cluster))
            
            return clusters
        
        supply_zones = cluster_levels(swing_highs, self.zone_threshold)
        demand_zones = cluster_levels(swing_lows, self.zone_threshold)
        
        status = 'MIDDLE'
        if supply_zones and current_price >= max(supply_zones) * 0.995:
            status = 'IN_SUPPLY'
        elif demand_zones and current_price <= min(demand_zones) * 1.005:
            status = 'IN_DEMAND'
        elif supply_zones and demand_zones:
            mid_point = (max(supply_zones) + min(demand_zones)) / 2
            if current_price > mid_point:
                status = 'PREMIUM'
            else:
                status = 'DISCOUNT'
        
        return {
            'supply': supply_zones[-3:] if len(supply_zones) > 3 else supply_zones,
            'demand': demand_zones[-3:] if len(demand_zones) > 3 else demand_zones,
            'status': status
        }
    
    def _determine_location(self, df: pd.DataFrame, zones: Dict) -> str:
        """Determine price location relative to VWAP and zones"""
        if len(df) < 5:
            return 'UNKNOWN'
        
        current_price = df['Close'].iloc[-1]
        vwap = df['vwap'].iloc[-1] if 'vwap' in df.columns else current_price
        
        vwap_diff = (current_price - vwap) / vwap * 100
        
        zone_status = zones.get('status', 'MIDDLE')
        
        if zone_status == 'IN_SUPPLY':
            if vwap_diff > 0.5:
                return 'SUPPLY_PREMIUM'
            return 'SUPPLY_ZONE'
        elif zone_status == 'IN_DEMAND':
            if vwap_diff < -0.5:
                return 'DEMAND_DISCOUNT'
            return 'DEMAND_ZONE'
        elif vwap_diff > 0.3:
            return 'VWAP_PREMIUM'
        elif vwap_diff < -0.3:
            return 'VWAP_DISCOUNT'
        else:
            return 'VWAP_NEUTRAL'
    
    def _check_recovery(self, df: pd.DataFrame, atr: float) -> Optional[Dict]:
        """
        Detect strong intraday recovery or rejection patterns.
        Returns signal data if a recovery is detected, None otherwise.
        """
        if len(df) < 20:
            return None
        
        # Get today's data only
        today = df.index[-1].date() if hasattr(df.index[-1], 'date') else None
        if today:
            today_df = df[df.index.date == today]
        else:
            today_df = df.tail(78)  # ~6.5 hours of 5min candles
        
        if len(today_df) < 10:
            return None
        
        current_price = today_df['Close'].iloc[-1]
        session_open = today_df['Open'].iloc[0]
        session_high = today_df['High'].max()
        session_low = today_df['Low'].min()
        session_range = session_high - session_low
        
        if session_range < atr * 0.5:  # Not enough movement
            return None
        
        # Calculate where price is relative to session range
        price_position = (current_price - session_low) / session_range if session_range > 0 else 0.5
        
        # Recovery from lows (bullish): price dropped significantly but recovered
        drop_from_open = session_open - session_low
        recovery_from_low = current_price - session_low
        
        # Recovery detection: >= 40% rebound from session low, price above 40% of range
        if drop_from_open > atr * 0.3 and recovery_from_low > drop_from_open * 0.4 and price_position > 0.4:
            # Bullish recovery detected
            recovery_pct = (recovery_from_low / drop_from_open) * 100
            return {
                'state': 'BUY',
                'reason': f"Bullish recovery: Dropped ${drop_from_open:.2f}, recovered {recovery_pct:.0f}%",
                'confidence_boost': min(int(recovery_pct * 0.25), 30)
            }
        
        # Rejection from highs (bearish): price rallied but got rejected
        rally_from_open = session_high - session_open
        rejection_from_high = session_high - current_price
        
        # Rejection detection: >= 40% rejection from session high, price below 60% of range
        if rally_from_open > atr * 0.3 and rejection_from_high > rally_from_open * 0.4 and price_position < 0.6:
            # Strong bearish rejection
            rejection_pct = (rejection_from_high / rally_from_open) * 100
            return {
                'state': 'SELL',
                'reason': f"Bearish rejection: Rallied ${rally_from_open:.2f}, rejected {rejection_pct:.0f}%",
                'confidence_boost': min(int(rejection_pct * 0.3), 35)
            }
        
        return None
    
    def _check_candle_patterns(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Detect instant-trigger candle patterns (hammer, engulfing, etc.)"""
        if len(df) < 3:
            return {'hammer': False, 'inverted_hammer': False, 'bullish_engulfing': False, 
                    'bearish_engulfing': False, 'morning_star': False, 'evening_star': False}
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        body = abs(current['Close'] - current['Open'])
        total_range = current['High'] - current['Low']
        upper_wick = current['High'] - max(current['Close'], current['Open'])
        lower_wick = min(current['Close'], current['Open']) - current['Low']
        prev_body = abs(prev['Close'] - prev['Open'])
        
        # Hammer: small body at top, long lower wick (bullish reversal)
        hammer = (lower_wick > body * 2 and upper_wick < body * 0.5 and 
                  current['Close'] > current['Open'] and total_range > 0)
        
        # Inverted Hammer: small body at bottom, long upper wick (bearish reversal)
        inverted_hammer = (upper_wick > body * 2 and lower_wick < body * 0.5 and 
                          current['Close'] < current['Open'] and total_range > 0)
        
        # Bullish Engulfing: current green candle fully engulfs previous red candle
        bullish_engulfing = (prev['Close'] < prev['Open'] and  # prev is red
                             current['Close'] > current['Open'] and  # current is green
                             current['Open'] < prev['Close'] and  # opens below prev close
                             current['Close'] > prev['Open'] and  # closes above prev open
                             body > prev_body * 0.8)  # significant size
        
        # Bearish Engulfing: current red candle fully engulfs previous green candle
        bearish_engulfing = (prev['Close'] > prev['Open'] and  # prev is green
                             current['Close'] < current['Open'] and  # current is red
                             current['Open'] > prev['Close'] and  # opens above prev close
                             current['Close'] < prev['Open'] and  # closes below prev open
                             body > prev_body * 0.8)  # significant size
        
        return {
            'hammer': bool(hammer),
            'inverted_hammer': bool(inverted_hammer),
            'bullish_engulfing': bool(bullish_engulfing),
            'bearish_engulfing': bool(bearish_engulfing),
            'morning_star': False,  # Would need 3 candles
            'evening_star': False
        }
    
    def _check_momentum(self, df: pd.DataFrame, atr: float) -> Dict:
        """Check for quick momentum moves that warrant immediate action"""
        if len(df) < 5 or atr <= 0:
            return {'quick_bullish': False, 'quick_bearish': False, 'momentum_strength': 0}
        
        # Look at last 3-5 candles for quick momentum
        recent = df.tail(5)
        first_close = recent['Close'].iloc[0]
        last_close = recent['Close'].iloc[-1]
        move = last_close - first_close
        move_pct = abs(move) / first_close * 100
        
        # Strong momentum = move of 0.5+ ATR in 5 candles
        is_strong = abs(move) >= atr * 0.5
        
        # Count consecutive green/red candles
        green_count = sum(1 for i in range(1, len(recent)) 
                         if recent['Close'].iloc[i] > recent['Close'].iloc[i-1])
        red_count = sum(1 for i in range(1, len(recent)) 
                       if recent['Close'].iloc[i] < recent['Close'].iloc[i-1])
        
        quick_bullish = move > 0 and is_strong and green_count >= 3
        quick_bearish = move < 0 and is_strong and red_count >= 3
        
        return {
            'quick_bullish': bool(quick_bullish),
            'quick_bearish': bool(quick_bearish),
            'momentum_strength': min(int(abs(move) / atr * 50), 40) if is_strong else 0,
            'move_pct': round(move_pct, 2)
        }
    
    def _check_confirmations(self, df: pd.DataFrame, regime: str, location: str) -> Dict[str, bool]:
        """Check all confirmation criteria"""
        if len(df) < 5:
            return {
                'rejection_candle': False,
                'lower_high': False,
                'higher_low': False,
                'vwap_rejection': False,
                'rsi_divergence': False,
                'volume_spike': False,
                'structure_break': False
            }
        
        current = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        body = abs(current['Close'] - current['Open'])
        total_range = current['High'] - current['Low']
        upper_wick = current['High'] - max(current['Close'], current['Open'])
        lower_wick = min(current['Close'], current['Open']) - current['Low']
        
        bearish_rejection = upper_wick > body * 2 and current['Close'] < current['Open']
        bullish_rejection = lower_wick > body * 2 and current['Close'] > current['Open']
        rejection_candle = bearish_rejection or bullish_rejection
        
        recent_highs = df['High'].tail(10).values
        recent_lows = df['Low'].tail(10).values
        lower_high = len(recent_highs) >= 3 and recent_highs[-1] < max(recent_highs[:-1])
        higher_low = len(recent_lows) >= 3 and recent_lows[-1] > min(recent_lows[:-1])
        
        vwap = current.get('vwap', current['Close'])
        vwap_rejection = (
            (prev['Close'] > vwap and current['Close'] < vwap) or
            (prev['Close'] < vwap and current['Close'] > vwap)
        )
        
        rsi_divergence = current.get('bearish_divergence', False) or current.get('bullish_divergence', False)
        
        volume_spike = current.get('volume_spike', False)
        
        ema_13 = current.get('ema_13', current['Close'])
        structure_break = (
            (prev['Close'] < ema_13 and current['Close'] > ema_13) or
            (prev['Close'] > ema_13 and current['Close'] < ema_13)
        )
        
        return {
            'rejection_candle': bool(rejection_candle),
            'bearish_rejection': bool(bearish_rejection),
            'bullish_rejection': bool(bullish_rejection),
            'lower_high': bool(lower_high),
            'higher_low': bool(higher_low),
            'vwap_rejection': bool(vwap_rejection),
            'rsi_divergence': bool(rsi_divergence),
            'volume_spike': bool(volume_spike),
            'structure_break': bool(structure_break)
        }
    
    def _determine_state(self, df: pd.DataFrame, regime: str, location: str, 
                         zones: Dict, confirmations: Dict) -> Tuple[str, int, str, List[str], List[str]]:
        """Determine trading state using the state machine logic - FAST DECISION MODE"""
        
        current = df.iloc[-1]
        rsi = current.get('rsi', 50)
        vwap = current.get('vwap', current['Close'])
        price = current['Close']
        atr = current.get('atr', 0)
        ema_13 = current.get('ema_13', price)
        
        reasons = []
        waiting_for = []
        confidence = 0
        
        # Check candle patterns and momentum for fast triggers
        patterns = self._check_candle_patterns(df)
        momentum = self._check_momentum(df, atr)
        zone_status = zones.get('status', 'MIDDLE')
        
        # Zone-based support - zone alignment is MANDATORY (regime only boosts, never overrides)
        in_bullish_zone = (zone_status in ['IN_DEMAND', 'DISCOUNT'] or 
                          location in ['DEMAND_ZONE', 'DEMAND_DISCOUNT', 'VWAP_DISCOUNT'])
        in_bearish_zone = (zone_status in ['IN_SUPPLY', 'PREMIUM'] or 
                          location in ['SUPPLY_ZONE', 'SUPPLY_PREMIUM', 'VWAP_PREMIUM'])
        zone_neutral = not in_bullish_zone and not in_bearish_zone
        
        # Block entries that conflict with zone
        blocks_bullish = in_bearish_zone  # Don't buy in supply zones
        blocks_bearish = in_bullish_zone  # Don't sell in demand zones
        
        # FAST PATH 1: Candle pattern in demand zone (not supply!) = BUY trigger
        if (patterns.get('hammer') or patterns.get('bullish_engulfing')) and not blocks_bullish:
            reasons.append("Bullish reversal pattern detected")
            confidence += 35
            if in_bullish_zone:
                reasons.append("Pattern in demand zone")
                confidence += 15
            if price > vwap or confirmations.get('structure_break'):
                reasons.append("VWAP reclaimed - entry confirmed")
                return 'BUY', min(confidence + 20, 80), 'BULLISH', reasons, []
            else:
                waiting_for.append("VWAP reclaim for confirmation")
                return 'PREPARE', min(confidence, 65), 'BULLISH', reasons, waiting_for
        
        # FAST PATH 1b: Bearish pattern in supply zone (not demand!) = SELL trigger
        if (patterns.get('inverted_hammer') or patterns.get('bearish_engulfing')) and not blocks_bearish:
            reasons.append("Bearish reversal pattern detected")
            confidence += 35
            if in_bearish_zone:
                reasons.append("Pattern in supply zone")
                confidence += 15
            if price < vwap or confirmations.get('structure_break'):
                reasons.append("Below VWAP - entry confirmed")
                return 'SELL', min(confidence + 20, 80), 'BEARISH', reasons, []
            else:
                waiting_for.append("Price to reject below VWAP")
                return 'PREPARE', min(confidence, 65), 'BEARISH', reasons, waiting_for
        
        # FAST PATH 2: Strong momentum + VWAP + not blocked by zone
        if momentum.get('quick_bullish') and not blocks_bullish and price > vwap:
            reasons.append(f"Strong bullish momentum ({momentum.get('move_pct', 0):.1f}% move)")
            reasons.append("Price above VWAP")
            confidence += momentum.get('momentum_strength', 0) + 20
            if in_bullish_zone:
                confidence += 10
            return 'BUY', min(confidence, 75), 'BULLISH', reasons, []
        elif momentum.get('quick_bullish') and not blocks_bullish:
            reasons.append(f"Bullish momentum building ({momentum.get('move_pct', 0):.1f}% move)")
            waiting_for.append("VWAP reclaim to confirm")
            return 'PREPARE', min(confidence + 20, 60), 'BULLISH', reasons, waiting_for
        
        if momentum.get('quick_bearish') and not blocks_bearish and price < vwap:
            reasons.append(f"Strong bearish momentum ({momentum.get('move_pct', 0):.1f}% move)")
            reasons.append("Price below VWAP")
            confidence += momentum.get('momentum_strength', 0) + 20
            if in_bearish_zone:
                confidence += 10
            return 'SELL', min(confidence, 75), 'BEARISH', reasons, []
        elif momentum.get('quick_bearish') and not blocks_bearish:
            reasons.append(f"Bearish momentum building ({momentum.get('move_pct', 0):.1f}% move)")
            waiting_for.append("Price to stay below VWAP")
            return 'PREPARE', min(confidence + 20, 60), 'BEARISH', reasons, waiting_for
        
        # FAST PATH 3: Intraday recovery - only if not blocked by zone
        recovery_signal = self._check_recovery(df, atr)
        if recovery_signal:
            reasons.append(recovery_signal['reason'])
            confidence += recovery_signal['confidence_boost']
            
            if recovery_signal['state'] == 'BUY' and not blocks_bullish:
                # Require VWAP reclaim OR structure confirmation for BUY
                if price > vwap:
                    reasons.append("Reclaimed VWAP - bullish entry")
                    return 'BUY', min(confidence + 30, 75), 'BULLISH', reasons, []
                elif confirmations.get('bullish_rejection') or confirmations.get('higher_low'):
                    reasons.append("Structure confirms recovery")
                    return 'BUY', min(confidence + 20, 70), 'BULLISH', reasons, []
                else:
                    waiting_for.append("VWAP reclaim or bullish confirmation")
                    return 'PREPARE', min(confidence + 10, 60), 'BULLISH', reasons, waiting_for
            elif recovery_signal['state'] == 'BUY' and blocks_bullish:
                reasons.append("Recovery in supply zone - wait for zone break")
                waiting_for.append("Price to exit supply zone")
                return 'PREPARE', min(confidence, 50), 'BULLISH', reasons, waiting_for
            
            if recovery_signal['state'] == 'SELL' and not blocks_bearish:
                if price < vwap:
                    reasons.append("Below VWAP - bearish entry")
                    return 'SELL', min(confidence + 30, 75), 'BEARISH', reasons, []
                elif confirmations.get('bearish_rejection') or confirmations.get('lower_high'):
                    reasons.append("Structure confirms rejection")
                    return 'SELL', min(confidence + 20, 70), 'BEARISH', reasons, []
                else:
                    waiting_for.append("Break below VWAP or bearish confirmation")
                    return 'PREPARE', min(confidence + 10, 60), 'BEARISH', reasons, waiting_for
            elif recovery_signal['state'] == 'SELL' and blocks_bearish:
                reasons.append("Rejection in demand zone - wait for zone break")
                waiting_for.append("Price to exit demand zone")
                return 'PREPARE', min(confidence, 50), 'BEARISH', reasons, waiting_for
        
        if zone_status in ['IN_SUPPLY', 'SUPPLY_PREMIUM'] or location in ['SUPPLY_ZONE', 'SUPPLY_PREMIUM']:
            
            if regime in ['RANGE', 'DISTRIBUTION']:
                reasons.append(f"Price in supply zone (range/distribution regime)")
                
                if rsi > 60:
                    reasons.append(f"RSI extended ({rsi:.0f} > 60)")
                    confidence += 20
                
                if price > vwap:
                    reasons.append("Trading above VWAP in premium")
                    confidence += 15
                
                sell_confirms = 0
                if confirmations.get('bearish_rejection'):
                    reasons.append("Bearish rejection candle confirmed")
                    sell_confirms += 1
                    confidence += 20
                
                if confirmations.get('lower_high'):
                    reasons.append("Lower high formed after sweep")
                    sell_confirms += 1
                    confidence += 15
                
                if confirmations.get('vwap_rejection'):
                    reasons.append("VWAP rejection confirmed")
                    sell_confirms += 1
                    confidence += 10
                
                if confirmations.get('rsi_divergence') and current.get('bearish_divergence'):
                    reasons.append("Bearish RSI divergence detected")
                    sell_confirms += 1
                    confidence += 15
                
                if confirmations.get('volume_spike'):
                    reasons.append("Volume spike on rejection")
                    confidence += 10
                
                # FAST: 1 confirmation is enough for SELL (was 2)
                if sell_confirms >= 1:
                    return 'SELL', min(confidence, 85), 'BEARISH', reasons, []
                elif rsi > 60 or price > vwap:
                    # Setup forming, enter PREPARE quickly
                    waiting_for.append("Any bearish confirmation")
                    return 'PREPARE', min(confidence + 10, 65), 'BEARISH', reasons, waiting_for
                else:
                    waiting_for.append("RSI to extend (>60)")
                    return 'WAIT', confidence, 'NEUTRAL', reasons, waiting_for
            
            elif regime == 'TREND_UP':
                reasons.append("Trending up - caution on shorts at supply")
                waiting_for.append("Trend exhaustion signal")
                return 'WAIT', 20, 'NEUTRAL', reasons, waiting_for
        
        elif zone_status in ['IN_DEMAND', 'DEMAND_DISCOUNT'] or location in ['DEMAND_ZONE', 'DEMAND_DISCOUNT']:
            
            if regime in ['RANGE', 'DISTRIBUTION', 'TREND_UP']:
                reasons.append(f"Price in demand zone")
                
                if rsi < 40:
                    reasons.append(f"RSI oversold ({rsi:.0f} < 40)")
                    confidence += 20
                
                if price < vwap:
                    reasons.append("Trading below VWAP at discount")
                    confidence += 15
                
                buy_confirms = 0
                if confirmations.get('bullish_rejection'):
                    reasons.append("Bullish rejection candle confirmed")
                    buy_confirms += 1
                    confidence += 20
                
                if confirmations.get('higher_low'):
                    reasons.append("Higher low structure formed")
                    buy_confirms += 1
                    confidence += 15
                
                if confirmations.get('structure_break') and price > vwap:
                    reasons.append("Reclaimed VWAP/structure")
                    buy_confirms += 1
                    confidence += 15
                
                if confirmations.get('rsi_divergence') and current.get('bullish_divergence'):
                    reasons.append("Bullish RSI divergence detected")
                    buy_confirms += 1
                    confidence += 15
                
                if confirmations.get('volume_spike'):
                    reasons.append("Volume spike on bounce")
                    confidence += 10
                
                # FAST: 1 confirmation is enough for BUY (was 2)
                if buy_confirms >= 1:
                    return 'BUY', min(confidence, 85), 'BULLISH', reasons, []
                elif rsi < 40 or price < vwap:
                    # Setup forming, enter PREPARE quickly
                    waiting_for.append("Any bullish confirmation")
                    return 'PREPARE', min(confidence + 10, 65), 'BULLISH', reasons, waiting_for
                else:
                    waiting_for.append("RSI to drop (<40)")
                    return 'WAIT', confidence, 'NEUTRAL', reasons, waiting_for
            
            elif regime == 'TREND_DOWN':
                reasons.append("Trending down - caution on longs at demand")
                waiting_for.append("Trend exhaustion signal")
                return 'WAIT', 20, 'NEUTRAL', reasons, waiting_for
        
        else:
            reasons.append("Price in middle zone - no edge")
            if zone_status == 'PREMIUM':
                waiting_for.append("Price to reach supply zone")
            elif zone_status == 'DISCOUNT':
                waiting_for.append("Price to reach demand zone")
            else:
                waiting_for.append("Price to reach a key zone")
            waiting_for.append("Clear regime identification")
            return 'WAIT', 25, 'NEUTRAL', reasons, waiting_for
        
        reasons.append("Conditions unclear")
        waiting_for.append("Better setup alignment")
        return 'WAIT', 15, 'NEUTRAL', reasons, waiting_for
    
    def _is_trading_allowed(self, session_rules: Dict) -> bool:
        """Check if trading is allowed based on session rules"""
        now = datetime.now()
        current_time = now.time()
        
        no_trade_before = session_rules.get('noTradeBefore', '09:30')
        no_trade_after = session_rules.get('noTradeAfter', '16:00')
        
        try:
            before_parts = no_trade_before.split(':')
            after_parts = no_trade_after.split(':')
            
            start_time = time(int(before_parts[0]), int(before_parts[1]))
            end_time = time(int(after_parts[0]), int(after_parts[1]))
            
            if current_time < start_time or current_time > end_time:
                return False
        except:
            pass
        
        weekday = now.weekday()
        if session_rules.get('noMonday') and weekday == 0:
            return False
        if session_rules.get('noFriday') and weekday == 4:
            return False
        
        return True
    
    def _create_signal(self, state: str, confidence: int, bias: str, reasons: List[str],
                       waiting_for: List[str], regime: str, location: str, 
                       zone_status: str, confirmations: Dict, df: pd.DataFrame) -> InstitutionalSignal:
        """Create the final signal object"""
        
        entry_price = None
        stop_price = None
        target_price = None
        risk_reward = None
        
        if state in ['BUY', 'SELL'] and len(df) > 0:
            current = df.iloc[-1]
            atr = current.get('atr', 0)
            price = current['Close']
            
            # Use options-appropriate stop/target levels ($1-2 range on underlying)
            # Clamp ATR multiplier to keep stops tight for options trading
            stop_distance = min(atr * 0.3, 2.0) if atr else min(price * 0.003, 1.50)
            target_distance = stop_distance * 2  # 2:1 reward-to-risk
            
            if state == 'BUY':
                entry_price = price
                stop_price = price - stop_distance
                target_price = price + target_distance
            else:
                entry_price = price
                stop_price = price + stop_distance
                target_price = price - target_distance
            
            if stop_price and entry_price:
                risk = abs(entry_price - stop_price)
                reward = abs(target_price - entry_price) if target_price else risk * 2
                risk_reward = round(reward / risk, 2) if risk > 0 else 2.0
        
        return InstitutionalSignal(
            state=state,
            confidence=confidence,
            bias=bias,
            reasons=reasons[:7],
            waiting_for=waiting_for[:5],
            regime=regime,
            location=location,
            zone_status=zone_status,
            confirmations=confirmations,
            entry_price=round(entry_price, 2) if entry_price else None,
            stop_price=round(stop_price, 2) if stop_price else None,
            target_price=round(target_price, 2) if target_price else None,
            risk_reward=risk_reward
        )
    
    def _empty_signal(self) -> InstitutionalSignal:
        """Return empty signal when data is insufficient"""
        return InstitutionalSignal(
            state='WAIT',
            confidence=0,
            bias='NEUTRAL',
            reasons=['Insufficient data for analysis'],
            waiting_for=['More price data required'],
            regime='UNKNOWN',
            location='UNKNOWN',
            zone_status='UNKNOWN',
            confirmations={}
        )


institutional_engine = InstitutionalEngine()
