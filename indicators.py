"""
Technical Indicators Module
Calculates RSI, MACD, Bollinger Bands, Volume Spikes, and Support/Resistance
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any

class IndicatorEngine:
    """Engine for calculating technical indicators"""
    
    def calculate_all(self, market_data: Dict, settings=None) -> Dict:
        """Calculate all indicators for given market data"""
        if not market_data or 'closes' not in market_data:
            return {'error': 'Invalid market data'}
        
        closes = np.array(market_data['closes'])
        highs = np.array(market_data.get('highs', closes))
        lows = np.array(market_data.get('lows', closes))
        volumes = np.array(market_data.get('volumes', [0] * len(closes)))
        
        realtime_price = market_data.get('current_price', 0)
        if realtime_price and len(closes) > 0 and realtime_price != closes[-1]:
            closes = closes.copy()
            highs = highs.copy()
            lows = lows.copy()
            closes[-1] = realtime_price
            if realtime_price > highs[-1]:
                highs[-1] = realtime_price
            if realtime_price < lows[-1]:
                lows[-1] = realtime_price
        
        rsi_period = getattr(settings, 'rsi_period', 14) if settings else 14
        rsi_oversold = getattr(settings, 'rsi_oversold', 30) if settings else 30
        rsi_overbought = getattr(settings, 'rsi_overbought', 70) if settings else 70
        macd_fast = getattr(settings, 'macd_fast', 12) if settings else 12
        macd_slow = getattr(settings, 'macd_slow', 26) if settings else 26
        macd_signal_period = getattr(settings, 'macd_signal', 9) if settings else 9
        bb_period = getattr(settings, 'bollinger_period', 20) if settings else 20
        bb_std = getattr(settings, 'bollinger_std', 2.0) if settings else 2.0
        volume_threshold = getattr(settings, 'volume_spike_threshold', 2.0) if settings else 2.0
        volume_period = getattr(settings, 'volume_period', 20) if settings else 20
        sr_lookback = getattr(settings, 'sr_lookback', 50) if settings else 50
        
        rsi = self.calculate_rsi(closes, rsi_period)
        rsi_series = self.calculate_rsi_series(closes, rsi_period)
        macd, signal, histogram = self.calculate_macd(closes, macd_fast, macd_slow, macd_signal_period)
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(closes, bb_period, bb_std)
        volume_spike = self.detect_volume_spike(volumes, volume_period, volume_threshold)
        support, resistance = self.calculate_support_resistance(highs, lows, closes, sr_lookback)
        
        ema_13 = self.calculate_ema_series(closes, 13)
        ema_48 = self.calculate_ema_series(closes, 48)
        ema_200 = self.calculate_ema_series(closes, 200)
        
        current_price = closes[-1] if len(closes) > 0 else 0
        
        ema_crossovers = self.detect_ema_crossovers(ema_13, ema_48, ema_200)
        
        return {
            'rsi': {
                'value': float(round(rsi, 2)) if not np.isnan(rsi) else 50.0,
                'oversold': float(rsi_oversold),
                'overbought': float(rsi_overbought),
                'signal': self._rsi_signal(rsi, rsi_oversold, rsi_overbought),
                'series': rsi_series[-100:] if len(rsi_series) > 100 else rsi_series
            },
            'macd': {
                'macd': float(round(macd, 4)) if not np.isnan(macd) else 0.0,
                'signal': float(round(signal, 4)) if not np.isnan(signal) else 0.0,
                'histogram': float(round(histogram, 4)) if not np.isnan(histogram) else 0.0,
                'signal_type': self._macd_signal(macd, signal, histogram)
            },
            'bollinger': {
                'upper': float(round(upper_band, 2)) if not np.isnan(upper_band) else float(current_price),
                'middle': float(round(middle_band, 2)) if not np.isnan(middle_band) else float(current_price),
                'lower': float(round(lower_band, 2)) if not np.isnan(lower_band) else float(current_price),
                'price_position': self._bollinger_position(current_price, upper_band, middle_band, lower_band),
                'signal': self._bollinger_signal(current_price, upper_band, middle_band, lower_band)
            },
            'volume': {
                'current': int(volumes[-1]) if len(volumes) > 0 else 0,
                'average': int(np.mean(volumes[-volume_period:])) if len(volumes) >= volume_period else int(np.mean(volumes)),
                'spike': bool(volume_spike),
                'spike_ratio': float(round(volumes[-1] / np.mean(volumes[-volume_period:]), 2)) if len(volumes) >= volume_period and np.mean(volumes[-volume_period:]) > 0 else 1.0
            },
            'support_resistance': {
                'support': float(round(support, 2)) if not np.isnan(support) else float(current_price * 0.98),
                'resistance': float(round(resistance, 2)) if not np.isnan(resistance) else float(current_price * 1.02),
                'near_support': bool(current_price <= support * 1.01) if support > 0 else False,
                'near_resistance': bool(current_price >= resistance * 0.99) if resistance > 0 else False
            },
            'vwap': self.calculate_vwap_indicator(highs, lows, closes, volumes, current_price),
            'trend': self.calculate_trend(closes),
            'momentum': self.calculate_momentum(closes),
            'ema': {
                'ema_13': float(round(ema_13[-1], 2)) if len(ema_13) > 0 else current_price,
                'ema_48': float(round(ema_48[-1], 2)) if len(ema_48) > 0 else current_price,
                'ema_200': float(round(ema_200[-1], 2)) if len(ema_200) > 0 else current_price,
                'ema_13_series': [float(round(x, 2)) for x in ema_13[-50:]] if len(ema_13) > 0 else [],
                'ema_48_series': [float(round(x, 2)) for x in ema_48[-50:]] if len(ema_48) > 0 else [],
                'ema_200_series': [float(round(x, 2)) for x in ema_200[-50:]] if len(ema_200) > 0 else [],
                'crossovers': ema_crossovers,
                'price_vs_ema_13': 'ABOVE' if current_price > (ema_13[-1] if len(ema_13) > 0 else current_price) else 'BELOW',
                'price_vs_ema_48': 'ABOVE' if current_price > (ema_48[-1] if len(ema_48) > 0 else current_price) else 'BELOW',
                'price_vs_ema_200': 'ABOVE' if current_price > (ema_200[-1] if len(ema_200) > 0 else current_price) else 'BELOW'
            },
            'current_price': float(round(current_price, 2))
        }
    
    def calculate_ema_series(self, closes: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA series for all data points"""
        if len(closes) < period:
            return np.array([np.mean(closes)] * len(closes))
        
        multiplier = 2 / (period + 1)
        ema = np.zeros(len(closes))
        ema[period-1] = np.mean(closes[:period])
        
        for i in range(period, len(closes)):
            ema[i] = (closes[i] - ema[i-1]) * multiplier + ema[i-1]
        
        for i in range(period-1):
            ema[i] = ema[period-1]
        
        return ema
    
    def detect_ema_crossovers(self, ema_13: np.ndarray, ema_48: np.ndarray, ema_200: np.ndarray) -> List[Dict]:
        """Detect EMA crossover signals"""
        crossovers = []
        
        if len(ema_13) < 2 or len(ema_48) < 2:
            return crossovers
        
        if ema_13[-2] <= ema_48[-2] and ema_13[-1] > ema_48[-1]:
            crossovers.append({'type': 'GOLDEN_CROSS', 'pair': '13/48', 'signal': 'BULLISH'})
        elif ema_13[-2] >= ema_48[-2] and ema_13[-1] < ema_48[-1]:
            crossovers.append({'type': 'DEATH_CROSS', 'pair': '13/48', 'signal': 'BEARISH'})
        
        if len(ema_48) >= 2 and len(ema_200) >= 2:
            if ema_48[-2] <= ema_200[-2] and ema_48[-1] > ema_200[-1]:
                crossovers.append({'type': 'GOLDEN_CROSS', 'pair': '48/200', 'signal': 'STRONG_BULLISH'})
            elif ema_48[-2] >= ema_200[-2] and ema_48[-1] < ema_200[-1]:
                crossovers.append({'type': 'DEATH_CROSS', 'pair': '48/200', 'signal': 'STRONG_BEARISH'})
        
        return crossovers
    
    def calculate_heiken_ashi(self, opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> Dict:
        """Calculate Heiken Ashi candles"""
        if len(closes) < 2:
            return {'opens': [], 'highs': [], 'lows': [], 'closes': []}
        
        ha_close = (opens + highs + lows + closes) / 4
        
        ha_open = np.zeros(len(closes))
        ha_open[0] = (opens[0] + closes[0]) / 2
        for i in range(1, len(closes)):
            ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
        
        ha_high = np.maximum(highs, np.maximum(ha_open, ha_close))
        ha_low = np.minimum(lows, np.minimum(ha_open, ha_close))
        
        colors = ['green' if ha_close[i] >= ha_open[i] else 'red' for i in range(len(closes))]
        
        return {
            'opens': [float(round(x, 2)) for x in ha_open],
            'highs': [float(round(x, 2)) for x in ha_high],
            'lows': [float(round(x, 2)) for x in ha_low],
            'closes': [float(round(x, 2)) for x in ha_close],
            'colors': colors
        }
    
    def calculate_trend(self, closes: np.ndarray) -> Dict:
        """Determine overall trend direction"""
        if len(closes) < 20:
            return {'direction': 'NEUTRAL', 'strength': 0}
        
        sma_5 = np.mean(closes[-5:])
        sma_10 = np.mean(closes[-10:])
        sma_20 = np.mean(closes[-20:])
        current = closes[-1]
        
        bullish_signals = 0
        bearish_signals = 0
        
        if current > sma_5:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if sma_5 > sma_10:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if sma_10 > sma_20:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if current > sma_20:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if bullish_signals >= 3:
            direction = 'BULLISH'
            strength = bullish_signals * 25
        elif bearish_signals >= 3:
            direction = 'BEARISH'
            strength = bearish_signals * 25
        else:
            direction = 'NEUTRAL'
            strength = 50
        
        return {
            'direction': direction,
            'strength': int(strength),
            'sma_5': float(round(sma_5, 2)),
            'sma_10': float(round(sma_10, 2)),
            'sma_20': float(round(sma_20, 2)),
            'price_vs_sma20': 'ABOVE' if current > sma_20 else 'BELOW'
        }
    
    def calculate_momentum(self, closes: np.ndarray) -> Dict:
        """Calculate price momentum"""
        if len(closes) < 14:
            return {'value': 0, 'signal': 'NEUTRAL'}
        
        momentum = ((closes[-1] - closes[-14]) / closes[-14]) * 100
        
        roc = ((closes[-1] - closes[-10]) / closes[-10]) * 100 if len(closes) >= 10 else 0
        
        if momentum > 2:
            signal = 'STRONG_BULLISH'
        elif momentum > 0.5:
            signal = 'BULLISH'
        elif momentum < -2:
            signal = 'STRONG_BEARISH'
        elif momentum < -0.5:
            signal = 'BEARISH'
        else:
            signal = 'NEUTRAL'
        
        return {
            'value': float(round(momentum, 2)),
            'roc': float(round(roc, 2)),
            'signal': signal
        }
    
    def calculate_vwap_indicator(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray, current_price: float) -> Dict:
        """Calculate VWAP and related signals"""
        vwap = self.calculate_vwap(highs, lows, closes, volumes)
        
        if vwap == 0 or np.isnan(vwap):
            return {
                'value': float(current_price),
                'distance': 0.0,
                'distance_percent': 0.0,
                'signal': 'NEUTRAL',
                'above_vwap': False
            }
        
        distance = current_price - vwap
        distance_percent = (distance / vwap) * 100 if vwap > 0 else 0
        above_vwap = current_price > vwap
        
        if distance_percent > 1.0:
            signal = 'OVERBOUGHT'
        elif distance_percent < -1.0:
            signal = 'OVERSOLD'
        elif above_vwap:
            signal = 'BULLISH'
        else:
            signal = 'BEARISH'
        
        return {
            'value': float(round(vwap, 2)),
            'distance': float(round(distance, 2)),
            'distance_percent': float(round(distance_percent, 2)),
            'signal': signal,
            'above_vwap': bool(above_vwap)
        }
    
    def calculate_vwap(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, volumes: np.ndarray) -> float:
        """Calculate Volume Weighted Average Price"""
        if len(closes) < 2 or len(volumes) < 2:
            return closes[-1] if len(closes) > 0 else 0.0
        
        typical_price = (highs + lows + closes) / 3
        cumulative_tp_vol = np.cumsum(typical_price * volumes)
        cumulative_vol = np.cumsum(volumes)
        
        if cumulative_vol[-1] == 0:
            return closes[-1]
        
        vwap = cumulative_tp_vol[-1] / cumulative_vol[-1]
        return float(vwap)
    
    def calculate_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(closes) < period + 1:
            return 50.0
        
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_rsi_series(self, closes: np.ndarray, period: int = 14) -> list:
        """Calculate RSI series for charting"""
        if len(closes) < period + 1:
            return [50.0] * len(closes)
        
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        rsi_series = [None] * period
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        for i in range(period, len(deltas)):
            if avg_loss == 0:
                rsi_series.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_series.append(100 - (100 / (1 + rs)))
            
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        rsi_series.append(rsi_series[-1] if rsi_series else 50.0)
        
        return [float(x) if x is not None else None for x in rsi_series]
    
    def calculate_macd(self, closes: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9):
        """Calculate MACD, Signal Line, and Histogram"""
        if len(closes) < slow + signal_period:
            return 0.0, 0.0, 0.0
        
        # Calculate EMAs
        ema_fast = self._ema(closes, fast)
        ema_slow = self._ema(closes, slow)
        
        macd_line = ema_fast - ema_slow
        
        # Signal line (EMA of MACD)
        if len(closes) >= slow + signal_period:
            macd_values = []
            for i in range(slow, len(closes)):
                ef = self._ema(closes[:i+1], fast)
                es = self._ema(closes[:i+1], slow)
                macd_values.append(ef - es)
            
            signal_line = self._ema(np.array(macd_values), signal_period) if len(macd_values) >= signal_period else macd_line
        else:
            signal_line = macd_line
        
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def _ema(self, data: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(data) < period:
            return np.mean(data)
        
        multiplier = 2 / (period + 1)
        ema = data[:period].mean()
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def calculate_bollinger_bands(self, closes: np.ndarray, period: int = 20, std_dev: float = 2.0):
        """Calculate Bollinger Bands"""
        if len(closes) < period:
            mean = np.mean(closes)
            std = np.std(closes)
            return mean + std_dev * std, mean, mean - std_dev * std
        
        middle = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        return upper, middle, lower
    
    def detect_volume_spike(self, volumes: np.ndarray, period: int = 20, threshold: float = 2.0) -> bool:
        """Detect if current volume is a spike"""
        if len(volumes) < period:
            return False
        
        avg_volume = np.mean(volumes[-period:-1]) if len(volumes) > period else np.mean(volumes[:-1])
        current_volume = volumes[-1]
        
        if avg_volume == 0:
            return False
        
        return current_volume >= avg_volume * threshold
    
    def calculate_support_resistance(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, lookback: int = 50):
        """Calculate support and resistance levels"""
        if len(closes) < lookback:
            lookback = len(closes)
        
        if lookback < 5:
            current = closes[-1]
            return current * 0.98, current * 1.02
        
        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        
        # Find significant levels using pivots
        resistance = np.percentile(recent_highs, 90)
        support = np.percentile(recent_lows, 10)
        
        return support, resistance
    
    def _rsi_signal(self, rsi: float, oversold: float, overbought: float) -> str:
        """Determine RSI signal"""
        if rsi <= oversold:
            return 'OVERSOLD'
        elif rsi >= overbought:
            return 'OVERBOUGHT'
        elif rsi < 45:
            return 'WEAK'
        elif rsi > 55:
            return 'STRONG'
        return 'NEUTRAL'
    
    def _macd_signal(self, macd: float, signal: float, histogram: float) -> str:
        """Determine MACD signal"""
        if macd > signal and histogram > 0:
            return 'BULLISH'
        elif macd < signal and histogram < 0:
            return 'BEARISH'
        elif macd > signal:
            return 'BULLISH_CROSS'
        elif macd < signal:
            return 'BEARISH_CROSS'
        return 'NEUTRAL'
    
    def _bollinger_position(self, price: float, upper: float, middle: float, lower: float) -> str:
        """Determine price position within Bollinger Bands"""
        if price >= upper:
            return 'ABOVE_UPPER'
        elif price <= lower:
            return 'BELOW_LOWER'
        elif price > middle:
            return 'UPPER_HALF'
        else:
            return 'LOWER_HALF'
    
    def _bollinger_signal(self, price: float, upper: float, middle: float, lower: float) -> str:
        """Determine Bollinger Band signal"""
        if price <= lower:
            return 'OVERSOLD'
        elif price >= upper:
            return 'OVERBOUGHT'
        return 'NEUTRAL'
