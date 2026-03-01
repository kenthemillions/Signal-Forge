"""
Signal Engine - Scoring Module
Confidence scoring based on confluence of signals
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class SignalScorer:
    """Calculate confidence scores based on signal confluence"""
    
    def __init__(self):
        self.weights = {
            'trend_alignment': 0.20,
            'indicator_confluence': 0.25,
            'zone_position': 0.15,
            'confirmation': 0.20,
            'volume_support': 0.10,
            'regime_fit': 0.10
        }
        
        self.thresholds = {
            'strong_signal': 80,
            'signal': 65,
            'weak_signal': 50,
            'no_signal': 0
        }
    
    def calculate_score(self, indicators: Dict[str, Any], regime: Dict[str, Any],
                       zones: Dict[str, Any], confirmation: Dict[str, Any],
                       bias: str) -> Dict[str, Any]:
        """
        Calculate overall confidence score for a trade setup
        Returns: score breakdown and final signal strength
        """
        try:
            scores = {}
            
            scores['trend_alignment'] = self._score_trend_alignment(indicators, bias)
            scores['indicator_confluence'] = self._score_indicator_confluence(indicators, bias)
            scores['zone_position'] = self._score_zone_position(zones, bias)
            scores['confirmation'] = self._score_confirmation(confirmation)
            scores['volume_support'] = self._score_volume(indicators.get('volume', {}))
            scores['regime_fit'] = self._score_regime_fit(regime, bias)
            
            weighted_score = sum(
                scores[key] * self.weights[key] 
                for key in self.weights
            )
            
            final_score = min(100, max(0, weighted_score))
            
            signal_strength = self._determine_signal_strength(final_score)
            
            bullish_count, bearish_count = self._count_indicator_signals(indicators)
            
            return {
                'final_score': round(final_score, 1),
                'signal_strength': signal_strength,
                'breakdown': {k: round(v, 1) for k, v in scores.items()},
                'weights': self.weights,
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'total_indicators': bullish_count + bearish_count,
                'confidence_tier': self._get_confidence_tier(final_score),
                'action_recommendation': self._get_action_recommendation(final_score, bias)
            }
            
        except Exception as e:
            logger.error(f"Error calculating score: {e}")
            return self._empty_score()
    
    def _score_trend_alignment(self, indicators: Dict, bias: str) -> float:
        """Score how well price action aligns with the bias"""
        score = 50
        
        trend = indicators.get('trend', {})
        ema = indicators.get('ema', {})
        
        trend_direction = trend.get('direction', 'NEUTRAL')
        ema_trend = ema.get('trend', 'NEUTRAL')
        
        if bias == 'BULLISH':
            if trend_direction == 'BULLISH':
                score += 25
            if ema_trend in ['BULLISH', 'STRONG_BULLISH']:
                score += 25
        elif bias == 'BEARISH':
            if trend_direction == 'BEARISH':
                score += 25
            if ema_trend in ['BEARISH', 'STRONG_BEARISH']:
                score += 25
        
        return min(100, score)
    
    def _score_indicator_confluence(self, indicators: Dict, bias: str) -> float:
        """Score the confluence of technical indicators"""
        bullish_signals = 0
        bearish_signals = 0
        total_indicators = 5
        
        rsi = indicators.get('rsi', {})
        if rsi.get('trend') == 'BULLISH' or rsi.get('oversold'):
            bullish_signals += 1
        elif rsi.get('trend') == 'BEARISH' or rsi.get('overbought'):
            bearish_signals += 1
        
        macd = indicators.get('macd', {})
        signal_type = macd.get('signal_type', 'NEUTRAL')
        if 'BULLISH' in signal_type:
            bullish_signals += 1
        elif 'BEARISH' in signal_type:
            bearish_signals += 1
        
        vwap = indicators.get('vwap', {})
        if vwap.get('above_vwap'):
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        bb = indicators.get('bollinger', {})
        if bb.get('signal') == 'OVERSOLD':
            bullish_signals += 1
        elif bb.get('signal') == 'OVERBOUGHT':
            bearish_signals += 1
        
        momentum = indicators.get('momentum', {})
        if momentum.get('direction') == 'UP':
            bullish_signals += 1
        elif momentum.get('direction') == 'DOWN':
            bearish_signals += 1
        
        if bias == 'BULLISH':
            alignment = bullish_signals / total_indicators
        elif bias == 'BEARISH':
            alignment = bearish_signals / total_indicators
        else:
            alignment = 0.5
        
        return alignment * 100
    
    def _score_zone_position(self, zones: Dict, bias: str) -> float:
        """Score based on proximity to supply/demand zones"""
        if not zones:
            return 50
        
        score = 50
        
        if bias == 'BULLISH':
            if zones.get('in_demand_zone'):
                score = 90
            elif zones.get('nearest_demand'):
                dist = zones['nearest_demand'].get('distance_pct', 10)
                if dist < 1:
                    score = 80
                elif dist < 2:
                    score = 70
            
            if zones.get('in_supply_zone'):
                score = 30
        
        elif bias == 'BEARISH':
            if zones.get('in_supply_zone'):
                score = 90
            elif zones.get('nearest_supply'):
                dist = zones['nearest_supply'].get('distance_pct', 10)
                if dist < 1:
                    score = 80
                elif dist < 2:
                    score = 70
            
            if zones.get('in_demand_zone'):
                score = 30
        
        return score
    
    def _score_confirmation(self, confirmation: Dict) -> float:
        """Score based on confirmation signals"""
        if not confirmation:
            return 40
        
        base_score = confirmation.get('score', 0) * 100
        
        if confirmation.get('is_confirmed'):
            return min(100, base_score + 20)
        
        return base_score
    
    def _score_volume(self, volume: Dict) -> float:
        """Score based on volume analysis"""
        if not volume:
            return 50
        
        spike_ratio = volume.get('spike_ratio', 1.0)
        
        if spike_ratio >= 2.0:
            return 95
        elif spike_ratio >= 1.5:
            return 80
        elif spike_ratio >= 1.2:
            return 65
        elif spike_ratio >= 1.0:
            return 50
        else:
            return 35
    
    def _score_regime_fit(self, regime: Dict, bias: str) -> float:
        """Score how well the setup fits the market regime"""
        if not regime:
            return 50
        
        regime_type = regime.get('regime', 'UNKNOWN')
        trading_bias = regime.get('trading_bias', 'NEUTRAL')
        
        if trading_bias == 'WITH_TREND':
            return 80
        elif trading_bias == bias:
            return 90
        elif trading_bias == 'NEUTRAL':
            return 60
        else:
            return 40
    
    def _count_indicator_signals(self, indicators: Dict) -> tuple:
        """Count bullish and bearish indicator signals"""
        bullish = 0
        bearish = 0
        
        rsi = indicators.get('rsi', {})
        if rsi.get('oversold'):
            bullish += 1
        elif rsi.get('overbought'):
            bearish += 1
        
        macd = indicators.get('macd', {})
        if 'BULLISH' in macd.get('signal_type', ''):
            bullish += 1
        elif 'BEARISH' in macd.get('signal_type', ''):
            bearish += 1
        
        if indicators.get('vwap', {}).get('above_vwap'):
            bullish += 1
        else:
            bearish += 1
        
        trend = indicators.get('trend', {}).get('direction', 'NEUTRAL')
        if trend == 'BULLISH':
            bullish += 1
        elif trend == 'BEARISH':
            bearish += 1
        
        momentum = indicators.get('momentum', {}).get('direction', 'NEUTRAL')
        if momentum == 'UP':
            bullish += 1
        elif momentum == 'DOWN':
            bearish += 1
        
        return bullish, bearish
    
    def _determine_signal_strength(self, score: float) -> str:
        """Determine signal strength category"""
        if score >= self.thresholds['strong_signal']:
            return 'STRONG'
        elif score >= self.thresholds['signal']:
            return 'MODERATE'
        elif score >= self.thresholds['weak_signal']:
            return 'WEAK'
        else:
            return 'NONE'
    
    def _get_confidence_tier(self, score: float) -> str:
        """Get confidence tier for display"""
        if score >= 90:
            return 'high'
        elif score >= 70:
            return 'normal'
        else:
            return 'low'
    
    def _get_action_recommendation(self, score: float, bias: str) -> str:
        """Get action recommendation based on score"""
        if score >= 80:
            if bias == 'BULLISH':
                return 'STRONG BUY'
            elif bias == 'BEARISH':
                return 'STRONG SELL'
        elif score >= 65:
            if bias == 'BULLISH':
                return 'BUY'
            elif bias == 'BEARISH':
                return 'SELL'
        elif score >= 50:
            return 'PREPARE'
        else:
            return 'WAIT'
    
    def _empty_score(self) -> Dict[str, Any]:
        """Return empty score result"""
        return {
            'final_score': 0,
            'signal_strength': 'NONE',
            'breakdown': {},
            'bullish_count': 0,
            'bearish_count': 0,
            'confidence_tier': 'low',
            'action_recommendation': 'WAIT'
        }
