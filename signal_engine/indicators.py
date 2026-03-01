"""
Signal Engine - Indicators Module
Technical indicator calculations: RSI, VWAP, EMA, ATR, Volume Spike
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """Calculate technical indicators for trading signals"""
    
    def __init__(self):
        self.default_periods = {
            'rsi': 14,
            'ema_fast': 13,
            'ema_mid': 48,
            'ema_slow': 200,
            'atr': 14,
            'volume_avg': 20
        }
    
    def calculate_all(self, data: Dict[str, Any], settings: Optional[Dict] = None) -> Dict[str, Any]:
        """Calculate all indicators for given price data"""
        try:
            prices = data.get('prices', [])
            volumes = data.get('volumes', [])
            highs = data.get('highs', prices)
            lows = data.get('lows', prices)
            opens = data.get('opens', prices)
            closes = prices
            
            if len(prices) < 20:
                logger.warning("Insufficient data for indicator calculation")
                return self._empty_indicators()
            
            return {
                'rsi': self.calculate_rsi(closes),
                'macd': self.calculate_macd(closes),
                'vwap': self.calculate_vwap(highs, lows, closes, volumes),
                'ema': self.calculate_ema_set(closes),
                'atr': self.calculate_atr(highs, lows, closes),
                'bollinger': self.calculate_bollinger(closes),
                'volume': self.calculate_volume_analysis(volumes),
                'trend': self.calculate_trend(closes),
                'support_resistance': self.calculate_support_resistance(highs, lows, closes),
                'momentum': self.calculate_momentum(closes, volumes)
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return self._empty_indicators()
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> Dict[str, Any]:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return {'value': 50, 'signal': 'NEUTRAL', 'trend': 'NEUTRAL'}
        
        prices = np.array(prices)
        deltas = np.diff(prices)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        if rsi <= 30:
            signal = 'OVERSOLD'
            trend = 'BULLISH'
        elif rsi >= 70:
            signal = 'OVERBOUGHT'
            trend = 'BEARISH'
        elif rsi <= 40:
            signal = 'WEAK'
            trend = 'NEUTRAL'
        elif rsi >= 60:
            signal = 'STRONG'
            trend = 'NEUTRAL'
        else:
            signal = 'NEUTRAL'
            trend = 'NEUTRAL'
        
        return {
            'value': round(rsi, 2),
            'signal': signal,
            'trend': trend,
            'oversold': rsi <= 30,
            'overbought': rsi >= 70
        }
    
    def calculate_macd(self, prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Any]:
        """Calculate MACD indicator"""
        if len(prices) < slow + signal:
            return {'value': 0, 'signal_line': 0, 'histogram': 0, 'signal_type': 'NEUTRAL'}
        
        prices = np.array(prices)
        
        ema_fast = self._ema(prices, fast)
        ema_slow = self._ema(prices, slow)
        
        macd_line = ema_fast - ema_slow
        signal_line = self._ema(macd_line, signal)
        histogram = macd_line - signal_line
        
        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        current_hist = histogram[-1]
        prev_hist = histogram[-2] if len(histogram) > 1 else 0
        
        if current_macd > current_signal and prev_hist < 0 and current_hist > 0:
            signal_type = 'BULLISH_CROSS'
        elif current_macd < current_signal and prev_hist > 0 and current_hist < 0:
            signal_type = 'BEARISH_CROSS'
        elif current_macd > current_signal:
            signal_type = 'BULLISH'
        elif current_macd < current_signal:
            signal_type = 'BEARISH'
        else:
            signal_type = 'NEUTRAL'
        
        return {
            'value': round(current_macd, 4),
            'signal_line': round(current_signal, 4),
            'histogram': round(current_hist, 4),
            'signal_type': signal_type,
            'crossover': 'BULLISH_CROSS' in signal_type or 'BEARISH_CROSS' in signal_type
        }
    
    def calculate_vwap(self, highs: List[float], lows: List[float], 
                       closes: List[float], volumes: List[float]) -> Dict[str, Any]:
        """Calculate Volume Weighted Average Price"""
        if len(closes) < 5 or len(volumes) < 5:
            return {'value': closes[-1] if closes else 0, 'above_vwap': True, 'distance_pct': 0}
        
        typical_price = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
        cumulative_tp_vol = sum(tp * v for tp, v in zip(typical_price, volumes))
        cumulative_vol = sum(volumes)
        
        vwap = cumulative_tp_vol / cumulative_vol if cumulative_vol > 0 else closes[-1]
        current_price = closes[-1]
        
        above_vwap = current_price > vwap
        distance_pct = ((current_price - vwap) / vwap) * 100 if vwap > 0 else 0
        
        return {
            'value': round(vwap, 2),
            'above_vwap': above_vwap,
            'distance_pct': round(distance_pct, 2),
            'signal': 'BULLISH' if above_vwap else 'BEARISH'
        }
    
    def calculate_ema_set(self, prices: List[float]) -> Dict[str, Any]:
        """Calculate EMA set (13, 48, 200)"""
        prices = np.array(prices)
        current_price = prices[-1]
        
        ema13 = self._ema(prices, 13)[-1] if len(prices) >= 13 else current_price
        ema48 = self._ema(prices, 48)[-1] if len(prices) >= 48 else current_price
        ema200 = self._ema(prices, 200)[-1] if len(prices) >= 200 else current_price
        
        above_13 = current_price > ema13
        above_48 = current_price > ema48
        above_200 = current_price > ema200
        
        if above_13 and above_48 and above_200:
            trend = 'STRONG_BULLISH'
        elif above_13 and above_48:
            trend = 'BULLISH'
        elif not above_13 and not above_48 and not above_200:
            trend = 'STRONG_BEARISH'
        elif not above_13 and not above_48:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'
        
        return {
            'ema13': round(ema13, 2),
            'ema48': round(ema48, 2),
            'ema200': round(ema200, 2),
            'above_13': above_13,
            'above_48': above_48,
            'above_200': above_200,
            'trend': trend
        }
    
    def calculate_atr(self, highs: List[float], lows: List[float], 
                      closes: List[float], period: int = 14) -> Dict[str, Any]:
        """Calculate Average True Range"""
        if len(closes) < period + 1:
            return {'value': 0, 'volatility': 'LOW'}
        
        true_ranges = []
        for i in range(1, len(closes)):
            high_low = highs[i] - lows[i]
            high_close = abs(highs[i] - closes[i-1])
            low_close = abs(lows[i] - closes[i-1])
            true_ranges.append(max(high_low, high_close, low_close))
        
        atr = np.mean(true_ranges[-period:])
        atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0
        
        if atr_pct > 3:
            volatility = 'HIGH'
        elif atr_pct > 1.5:
            volatility = 'MODERATE'
        else:
            volatility = 'LOW'
        
        return {
            'value': round(atr, 2),
            'pct': round(atr_pct, 2),
            'volatility': volatility
        }
    
    def calculate_bollinger(self, prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, Any]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            current = prices[-1] if prices else 0
            return {'upper': current, 'middle': current, 'lower': current, 'signal': 'NEUTRAL', 'bandwidth': 0}
        
        prices = np.array(prices)
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        current = prices[-1]
        
        bandwidth = ((upper - lower) / sma) * 100 if sma > 0 else 0
        
        if current <= lower:
            signal = 'OVERSOLD'
        elif current >= upper:
            signal = 'OVERBOUGHT'
        elif current > sma:
            signal = 'ABOVE_MEAN'
        else:
            signal = 'BELOW_MEAN'
        
        return {
            'upper': round(upper, 2),
            'middle': round(sma, 2),
            'lower': round(lower, 2),
            'signal': signal,
            'bandwidth': round(bandwidth, 2),
            'squeeze': bandwidth < 4
        }
    
    def calculate_volume_analysis(self, volumes: List[float], period: int = 20) -> Dict[str, Any]:
        """Analyze volume for spikes and trends"""
        if len(volumes) < period:
            return {'current': 0, 'average': 0, 'spike_ratio': 1.0, 'spike': False, 'trend': 'NEUTRAL'}
        
        current_vol = volumes[-1]
        avg_vol = np.mean(volumes[-period:])
        spike_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        
        recent_avg = np.mean(volumes[-5:])
        older_avg = np.mean(volumes[-period:-5]) if len(volumes) > 5 else avg_vol
        
        if recent_avg > older_avg * 1.5:
            trend = 'INCREASING'
        elif recent_avg < older_avg * 0.7:
            trend = 'DECREASING'
        else:
            trend = 'STABLE'
        
        return {
            'current': int(current_vol),
            'average': int(avg_vol),
            'spike_ratio': round(spike_ratio, 2),
            'spike': spike_ratio >= 2.0,
            'above_average': spike_ratio >= 1.2,
            'trend': trend
        }
    
    def calculate_trend(self, prices: List[float], short_period: int = 10, long_period: int = 30) -> Dict[str, Any]:
        """Determine overall trend direction"""
        if len(prices) < long_period:
            return {'direction': 'NEUTRAL', 'strength': 50}
        
        prices = np.array(prices)
        short_sma = np.mean(prices[-short_period:])
        long_sma = np.mean(prices[-long_period:])
        current = prices[-1]
        
        price_change = ((current - prices[-long_period]) / prices[-long_period]) * 100
        
        if current > short_sma > long_sma:
            direction = 'BULLISH'
            strength = min(100, 50 + abs(price_change) * 5)
        elif current < short_sma < long_sma:
            direction = 'BEARISH'
            strength = min(100, 50 + abs(price_change) * 5)
        else:
            direction = 'NEUTRAL'
            strength = 50
        
        return {
            'direction': direction,
            'strength': round(strength, 1),
            'price_change_pct': round(price_change, 2)
        }
    
    def calculate_support_resistance(self, highs: List[float], lows: List[float], 
                                     closes: List[float]) -> Dict[str, Any]:
        """Calculate key support and resistance levels"""
        if len(closes) < 10:
            current = closes[-1] if closes else 0
            return {'support': current * 0.98, 'resistance': current * 1.02, 
                    'near_support': False, 'near_resistance': False}
        
        recent_highs = sorted(highs[-20:], reverse=True)[:5]
        recent_lows = sorted(lows[-20:])[:5]
        
        resistance = np.mean(recent_highs)
        support = np.mean(recent_lows)
        current = closes[-1]
        
        range_size = resistance - support
        near_support = (current - support) < (range_size * 0.2) if range_size > 0 else False
        near_resistance = (resistance - current) < (range_size * 0.2) if range_size > 0 else False
        
        return {
            'support': round(support, 2),
            'resistance': round(resistance, 2),
            'near_support': near_support,
            'near_resistance': near_resistance,
            'range': round(range_size, 2)
        }
    
    def calculate_momentum(self, prices: List[float], volumes: List[float]) -> Dict[str, Any]:
        """Calculate price momentum"""
        if len(prices) < 5:
            return {'value': 0, 'direction': 'NEUTRAL', 'strength': 'WEAK'}
        
        price_change = ((prices[-1] - prices[-5]) / prices[-5]) * 100 if prices[-5] > 0 else 0
        
        if price_change > 1.0:
            direction = 'UP'
            strength = 'STRONG' if price_change > 2.0 else 'MODERATE'
        elif price_change < -1.0:
            direction = 'DOWN'
            strength = 'STRONG' if price_change < -2.0 else 'MODERATE'
        else:
            direction = 'NEUTRAL'
            strength = 'WEAK'
        
        return {
            'value': round(price_change, 2),
            'direction': direction,
            'strength': strength
        }
    
    def calculate_fibonacci(self, highs: List[float], lows: List[float], 
                             closes: List[float], lookback: int = 50) -> Dict[str, Any]:
        """Calculate Fibonacci retracement levels from recent swing high/low"""
        if len(closes) < lookback:
            current = closes[-1] if closes else 0
            return {
                'swing_high': current,
                'swing_low': current,
                'levels': {},
                'current_level': 'UNKNOWN',
                'nearest_support': current,
                'nearest_resistance': current
            }
        
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        
        swing_high = max(recent_highs)
        swing_low = min(recent_lows)
        current_price = closes[-1]
        
        price_range = swing_high - swing_low
        
        fib_levels = {
            '0.0': swing_high,
            '23.6': swing_high - (price_range * 0.236),
            '38.2': swing_high - (price_range * 0.382),
            '50.0': swing_high - (price_range * 0.500),
            '61.8': swing_high - (price_range * 0.618),
            '78.6': swing_high - (price_range * 0.786),
            '100.0': swing_low
        }
        
        current_level = 'BELOW_100'
        for level_name, level_price in fib_levels.items():
            if current_price >= level_price:
                current_level = f'ABOVE_{level_name}'
                break
        
        supports = [p for p in fib_levels.values() if p < current_price]
        resistances = [p for p in fib_levels.values() if p > current_price]
        
        nearest_support = max(supports) if supports else swing_low
        nearest_resistance = min(resistances) if resistances else swing_high
        
        retracement_pct = ((swing_high - current_price) / price_range * 100) if price_range > 0 else 0
        
        if retracement_pct <= 23.6:
            zone = 'STRONG_UPTREND'
        elif retracement_pct <= 38.2:
            zone = 'HEALTHY_PULLBACK'
        elif retracement_pct <= 50:
            zone = 'MODERATE_RETRACEMENT'
        elif retracement_pct <= 61.8:
            zone = 'DEEP_RETRACEMENT'
        elif retracement_pct <= 78.6:
            zone = 'CRITICAL_ZONE'
        else:
            zone = 'BREAKDOWN'
        
        return {
            'swing_high': round(swing_high, 2),
            'swing_low': round(swing_low, 2),
            'levels': {k: round(v, 2) for k, v in fib_levels.items()},
            'current_level': current_level,
            'retracement_pct': round(retracement_pct, 1),
            'zone': zone,
            'nearest_support': round(nearest_support, 2),
            'nearest_resistance': round(nearest_resistance, 2)
        }
    
    def _ema(self, prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return prices
        
        multiplier = 2 / (period + 1)
        ema = np.zeros_like(prices, dtype=float)
        ema[period-1] = np.mean(prices[:period])
        
        for i in range(period, len(prices)):
            ema[i] = (prices[i] * multiplier) + (ema[i-1] * (1 - multiplier))
        
        return ema
    
    def _empty_indicators(self) -> Dict[str, Any]:
        """Return empty indicator set"""
        return {
            'rsi': {'value': 50, 'signal': 'NEUTRAL', 'trend': 'NEUTRAL'},
            'macd': {'value': 0, 'signal_type': 'NEUTRAL'},
            'vwap': {'value': 0, 'above_vwap': True},
            'ema': {'trend': 'NEUTRAL'},
            'atr': {'value': 0, 'volatility': 'LOW'},
            'bollinger': {'signal': 'NEUTRAL'},
            'volume': {'spike': False, 'spike_ratio': 1.0},
            'trend': {'direction': 'NEUTRAL'},
            'support_resistance': {'support': 0, 'resistance': 0},
            'momentum': {'direction': 'NEUTRAL'}
        }
