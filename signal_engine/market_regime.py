"""
Signal Engine - Market Regime Module
Detect whether market is trending, ranging, or in distribution
"""

import numpy as np
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class MarketRegimeDetector:
    """Detect current market regime (trend vs range vs distribution)"""
    
    def __init__(self):
        self.regime_thresholds = {
            'strong_trend': 0.7,
            'trend': 0.5,
            'range': 0.3
        }
    
    def detect_regime(self, prices: List[float], volumes: List[float], 
                      indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect the current market regime
        Returns: regime type, confidence, characteristics
        """
        try:
            if len(prices) < 30:
                return self._default_regime()
            
            trend_score = self._calculate_trend_score(prices, indicators)
            range_score = self._calculate_range_score(prices)
            distribution_score = self._calculate_distribution_score(prices, volumes)
            
            regime = self._determine_regime(trend_score, range_score, distribution_score)
            
            return {
                'regime': regime['type'],
                'confidence': regime['confidence'],
                'trend_score': round(trend_score, 2),
                'range_score': round(range_score, 2),
                'distribution_score': round(distribution_score, 2),
                'characteristics': regime['characteristics'],
                'trading_bias': regime['trading_bias'],
                'entry_approach': regime['entry_approach']
            }
        except Exception as e:
            logger.error(f"Error detecting market regime: {e}")
            return self._default_regime()
    
    def _calculate_trend_score(self, prices: List[float], indicators: Dict[str, Any]) -> float:
        """Calculate how strongly the market is trending"""
        prices = np.array(prices)
        
        ema_data = indicators.get('ema', {})
        trend_data = indicators.get('trend', {})
        
        short_slope = (prices[-1] - prices[-10]) / prices[-10] if len(prices) >= 10 else 0
        long_slope = (prices[-1] - prices[-30]) / prices[-30] if len(prices) >= 30 else 0
        
        slope_alignment = 1.0 if (short_slope > 0 and long_slope > 0) or (short_slope < 0 and long_slope < 0) else 0.5
        
        ema_alignment = 0
        if ema_data.get('above_13') and ema_data.get('above_48'):
            ema_alignment = 1.0
        elif not ema_data.get('above_13') and not ema_data.get('above_48'):
            ema_alignment = 1.0
        else:
            ema_alignment = 0.3
        
        trend_strength = trend_data.get('strength', 50) / 100
        
        higher_highs, higher_lows = self._count_higher_highs_lows(prices)
        hh_hl_score = (higher_highs + higher_lows) / 10
        
        trend_score = (slope_alignment * 0.3 + ema_alignment * 0.3 + 
                      trend_strength * 0.2 + hh_hl_score * 0.2)
        
        return min(1.0, max(0, trend_score))
    
    def _calculate_range_score(self, prices: List[float]) -> float:
        """Calculate how strongly the market is ranging"""
        if len(prices) < 20:
            return 0.5
        
        prices = np.array(prices[-30:])
        
        high = np.max(prices)
        low = np.min(prices)
        range_pct = ((high - low) / low) * 100 if low > 0 else 0
        
        mean_price = np.mean(prices)
        std_dev = np.std(prices)
        cv = (std_dev / mean_price) * 100 if mean_price > 0 else 0
        
        range_score = 0
        
        if range_pct < 3:
            range_score += 0.4
        elif range_pct < 5:
            range_score += 0.2
        
        if cv < 2:
            range_score += 0.3
        elif cv < 4:
            range_score += 0.15
        
        touches = self._count_level_touches(prices, high, low)
        if touches >= 4:
            range_score += 0.3
        elif touches >= 2:
            range_score += 0.15
        
        return min(1.0, max(0, range_score))
    
    def _calculate_distribution_score(self, prices: List[float], volumes: List[float]) -> float:
        """Calculate if market is in distribution (topping) or accumulation (bottoming)"""
        if len(prices) < 20 or len(volumes) < 20:
            return 0
        
        prices = np.array(prices[-30:])
        volumes = np.array(volumes[-30:])
        
        up_volume = 0
        down_volume = 0
        
        for i in range(1, len(prices)):
            if prices[i] > prices[i-1]:
                up_volume += volumes[i]
            else:
                down_volume += volumes[i]
        
        volume_ratio = down_volume / up_volume if up_volume > 0 else 1
        
        recent_high = np.max(prices[-10:])
        overall_high = np.max(prices)
        
        near_highs = recent_high >= overall_high * 0.98
        
        distribution_score = 0
        
        if near_highs and volume_ratio > 1.2:
            distribution_score = 0.7
        elif near_highs and volume_ratio > 1.0:
            distribution_score = 0.4
        elif volume_ratio > 1.5:
            distribution_score = 0.3
        
        return distribution_score
    
    def _count_higher_highs_lows(self, prices: List[float]) -> tuple:
        """Count higher highs and higher lows in price series"""
        if len(prices) < 10:
            return 0, 0
        
        higher_highs = 0
        higher_lows = 0
        
        window = 5
        for i in range(window, len(prices) - window, window):
            prev_high = max(prices[i-window:i])
            curr_high = max(prices[i:i+window])
            prev_low = min(prices[i-window:i])
            curr_low = min(prices[i:i+window])
            
            if curr_high > prev_high:
                higher_highs += 1
            if curr_low > prev_low:
                higher_lows += 1
        
        return higher_highs, higher_lows
    
    def _count_level_touches(self, prices: np.ndarray, high: float, low: float) -> int:
        """Count how many times price touched support/resistance levels"""
        threshold = (high - low) * 0.1
        
        touches = 0
        for price in prices:
            if abs(price - high) <= threshold or abs(price - low) <= threshold:
                touches += 1
        
        return touches
    
    def _determine_regime(self, trend_score: float, range_score: float, 
                         distribution_score: float) -> Dict[str, Any]:
        """Determine the final regime classification"""
        
        if distribution_score > 0.5:
            return {
                'type': 'DISTRIBUTION',
                'confidence': distribution_score,
                'characteristics': ['High volume on down moves', 'Price near recent highs', 'Potential top forming'],
                'trading_bias': 'BEARISH',
                'entry_approach': 'Wait for breakdown confirmation or fade rallies'
            }
        
        if trend_score >= self.regime_thresholds['strong_trend']:
            return {
                'type': 'STRONG_TREND',
                'confidence': trend_score,
                'characteristics': ['Clear directional movement', 'EMAs aligned', 'Higher highs/lows'],
                'trading_bias': 'WITH_TREND',
                'entry_approach': 'Buy pullbacks to EMA or VWAP in uptrend, sell rallies in downtrend'
            }
        
        if trend_score >= self.regime_thresholds['trend']:
            return {
                'type': 'TREND',
                'confidence': trend_score,
                'characteristics': ['Moderate trend', 'Some pullbacks', 'Trend intact'],
                'trading_bias': 'WITH_TREND',
                'entry_approach': 'Look for trend continuation setups'
            }
        
        if range_score >= self.regime_thresholds['range']:
            return {
                'type': 'RANGE',
                'confidence': range_score,
                'characteristics': ['Price bouncing between levels', 'Low volatility', 'Mean reversion'],
                'trading_bias': 'NEUTRAL',
                'entry_approach': 'Buy at support, sell at resistance, avoid middle'
            }
        
        return {
            'type': 'TRANSITIONAL',
            'confidence': 0.5,
            'characteristics': ['Mixed signals', 'Regime unclear', 'Wait for clarity'],
            'trading_bias': 'NEUTRAL',
            'entry_approach': 'Reduce position size, wait for clearer setup'
        }
    
    def _default_regime(self) -> Dict[str, Any]:
        """Return default regime when detection fails"""
        return {
            'regime': 'UNKNOWN',
            'confidence': 0,
            'trend_score': 0,
            'range_score': 0,
            'distribution_score': 0,
            'characteristics': ['Insufficient data'],
            'trading_bias': 'NEUTRAL',
            'entry_approach': 'Wait for more data'
        }
