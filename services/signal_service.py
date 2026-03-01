"""
Signal Forge - Signal Service
High-level service that orchestrates the signal engine components
"""

import logging
from typing import Dict, Any, Optional, List

from signal_engine import (
    IndicatorCalculator,
    MarketRegimeDetector,
    ZoneDetector,
    ConfirmationEngine,
    SignalScorer,
    ExplanationGenerator
)

logger = logging.getLogger(__name__)


class SignalService:
    """
    High-level service that coordinates all signal engine components
    to generate comprehensive trading signals
    """
    
    def __init__(self):
        self.indicator_calc = IndicatorCalculator()
        self.regime_detector = MarketRegimeDetector()
        self.zone_detector = ZoneDetector()
        self.confirmation_engine = ConfirmationEngine()
        self.scorer = SignalScorer()
        self.explainer = ExplanationGenerator()
    
    def generate_signal(self, symbol: str, data: Dict[str, Any], 
                       settings: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive trading signal for a symbol
        
        Args:
            symbol: Ticker symbol
            data: Market data with prices, volumes, highs, lows
            settings: Optional user settings
            
        Returns:
            Complete signal with indicators, regime, zones, confirmations, score, explanation
        """
        try:
            prices = data.get('closes', data.get('prices', []))
            volumes = data.get('volumes', [])
            highs = data.get('highs', prices)
            lows = data.get('lows', prices)
            opens = data.get('opens', prices)
            
            if len(prices) < 20:
                return self._insufficient_data_signal(symbol, data)
            
            indicator_data = {
                'prices': prices,
                'volumes': volumes,
                'highs': highs,
                'lows': lows,
                'opens': opens
            }
            
            indicators = self.indicator_calc.calculate_all(indicator_data, settings)
            
            regime = self.regime_detector.detect_regime(prices, volumes, indicators)
            
            zones = self.zone_detector.detect_zones(highs, lows, prices, volumes)
            
            bias = self._determine_bias(indicators, regime, zones)
            
            confirmation = self.confirmation_engine.check_confirmations(
                indicator_data, indicators, zones, bias
            )
            
            score = self.scorer.calculate_score(
                indicators, regime, zones, confirmation, bias
            )
            
            explanation = self.explainer.generate_explanation(
                indicators, regime, zones, confirmation, score, bias
            )
            
            main_signal = score.get('action_recommendation', 'WAIT')
            confidence = score.get('final_score', 0)
            
            return {
                'symbol': symbol,
                'main_signal': main_signal,
                'bias': bias,
                'confidence': confidence,
                'confidence_pct': round(confidence, 1),
                'confidence_tier': score.get('confidence_tier', 'low'),
                
                'indicators': indicators,
                'regime': regime,
                'zones': zones,
                'confirmation': confirmation,
                'score': score,
                'explanation': explanation,
                
                'main_reason': explanation.get('main_reason', ''),
                'reasons': explanation.get('reasons', []),
                'education_text': explanation.get('education_text', ''),
                'wait_for_text': explanation.get('wait_for_text', ''),
                'entry_window': self._get_entry_window(regime, confirmation, score),
                
                'entry_guidance': explanation.get('entry_guidance', {}),
                'stop_level': explanation.get('entry_guidance', {}).get('stop_level', 0),
                'target_level': explanation.get('entry_guidance', {}).get('target_level', 0),
                
                'current_price': prices[-1] if prices else 0,
                'vwap': indicators.get('vwap', {}).get('value', 0),
                'rsi': indicators.get('rsi', {}).get('value', 50),
                'macd_signal': indicators.get('macd', {}).get('signal_type', 'NEUTRAL'),
                'volume_spike': indicators.get('volume', {}).get('spike_ratio', 1.0),
                
                'bullish_count': score.get('bullish_count', 0),
                'bearish_count': score.get('bearish_count', 0),
                'total_indicators': score.get('total_indicators', 5)
            }
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return self._error_signal(symbol, str(e))
    
    def _determine_bias(self, indicators: Dict, regime: Dict, zones: Dict) -> str:
        """Determine the overall market bias"""
        bullish_signals = 0
        bearish_signals = 0
        
        trend = indicators.get('trend', {}).get('direction', 'NEUTRAL')
        if trend == 'BULLISH':
            bullish_signals += 2
        elif trend == 'BEARISH':
            bearish_signals += 2
        
        ema_trend = indicators.get('ema', {}).get('trend', 'NEUTRAL')
        if 'BULLISH' in ema_trend:
            bullish_signals += 1
        elif 'BEARISH' in ema_trend:
            bearish_signals += 1
        
        if indicators.get('vwap', {}).get('above_vwap'):
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        macd = indicators.get('macd', {}).get('signal_type', 'NEUTRAL')
        if 'BULLISH' in macd:
            bullish_signals += 1
        elif 'BEARISH' in macd:
            bearish_signals += 1
        
        rsi = indicators.get('rsi', {})
        if rsi.get('oversold'):
            bullish_signals += 1
        elif rsi.get('overbought'):
            bearish_signals += 1
        
        zone_bias = zones.get('zone_bias', 'NEUTRAL')
        if zone_bias == 'BULLISH':
            bullish_signals += 1
        elif zone_bias == 'BEARISH':
            bearish_signals += 1
        
        if bullish_signals > bearish_signals + 1:
            return 'BULLISH'
        elif bearish_signals > bullish_signals + 1:
            return 'BEARISH'
        else:
            return 'NEUTRAL'
    
    def _get_entry_window(self, regime: Dict, confirmation: Dict, score: Dict) -> str:
        """Generate entry window guidance text"""
        confidence = score.get('final_score', 0)
        is_confirmed = confirmation.get('is_confirmed', False)
        
        if confidence >= 80 and is_confirmed:
            return "Now (confirmed setup)"
        elif confidence >= 70 and is_confirmed:
            return "Now (confirm on 5m candle close)"
        elif confidence >= 65:
            return "On next pullback to VWAP"
        elif confidence >= 50:
            return "Wait for confirmation"
        else:
            return "No entry - wait for setup"
    
    def _insufficient_data_signal(self, symbol: str, data: Dict) -> Dict[str, Any]:
        """Return signal when there's insufficient data"""
        price = 0
        if data:
            prices = data.get('closes', data.get('prices', []))
            if prices:
                price = prices[-1]
        
        return {
            'symbol': symbol,
            'main_signal': 'WAIT',
            'bias': 'NEUTRAL',
            'confidence': 0,
            'confidence_pct': 0,
            'confidence_tier': 'low',
            'main_reason': 'Insufficient data for analysis',
            'reasons': ['Need at least 20 data points for reliable signals'],
            'education_text': 'Wait for more market data to accumulate',
            'entry_window': 'No entry - insufficient data',
            'wait_for_text': 'Collecting market data...',
            'current_price': price,
            'indicators': {},
            'regime': {},
            'zones': {},
            'confirmation': {},
            'score': {},
            'explanation': {}
        }
    
    def _error_signal(self, symbol: str, error: str) -> Dict[str, Any]:
        """Return signal when an error occurs"""
        return {
            'symbol': symbol,
            'main_signal': 'WAIT',
            'bias': 'NEUTRAL',
            'confidence': 0,
            'confidence_pct': 0,
            'confidence_tier': 'low',
            'main_reason': f'Analysis error: {error}',
            'reasons': ['Unable to complete signal analysis'],
            'education_text': 'Technical issue - please refresh',
            'entry_window': 'No entry - analysis error',
            'wait_for_text': 'Retrying...',
            'current_price': 0,
            'error': error
        }
    
    def get_multi_timeframe_analysis(self, symbol: str, data_by_timeframe: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Analyze multiple timeframes and return confluence score
        
        Args:
            symbol: Ticker symbol
            data_by_timeframe: Dict mapping timeframe to market data
            
        Returns:
            Multi-timeframe analysis with confluence
        """
        results = {}
        bullish_tfs = 0
        bearish_tfs = 0
        
        for tf, data in data_by_timeframe.items():
            signal = self.generate_signal(symbol, data)
            results[tf] = {
                'signal': signal.get('main_signal'),
                'bias': signal.get('bias'),
                'confidence': signal.get('confidence_pct')
            }
            
            if signal.get('bias') == 'BULLISH':
                bullish_tfs += 1
            elif signal.get('bias') == 'BEARISH':
                bearish_tfs += 1
        
        total_tfs = len(data_by_timeframe)
        
        if bullish_tfs > total_tfs * 0.6:
            confluence = 'BULLISH'
            confluence_score = (bullish_tfs / total_tfs) * 100
        elif bearish_tfs > total_tfs * 0.6:
            confluence = 'BEARISH'
            confluence_score = (bearish_tfs / total_tfs) * 100
        else:
            confluence = 'MIXED'
            confluence_score = 50
        
        return {
            'symbol': symbol,
            'timeframes': results,
            'confluence': confluence,
            'confluence_score': round(confluence_score, 1),
            'bullish_timeframes': bullish_tfs,
            'bearish_timeframes': bearish_tfs,
            'total_timeframes': total_tfs
        }


signal_service = SignalService()
