"""
Signal Engine - Explanations Module
Generate plain-English reasoning for trading signals
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ExplanationGenerator:
    """Generate human-readable explanations for trading signals"""
    
    def __init__(self):
        self.templates = {
            'bullish_strong': [
                "Strong bullish setup detected.",
                "Multiple indicators aligned for upside.",
                "High conviction long opportunity."
            ],
            'bullish_moderate': [
                "Bullish bias forming.",
                "Conditions favor upside move.",
                "Setup developing for calls."
            ],
            'bearish_strong': [
                "Strong bearish setup detected.",
                "Multiple indicators aligned for downside.",
                "High conviction short opportunity."
            ],
            'bearish_moderate': [
                "Bearish bias forming.",
                "Conditions favor downside move.",
                "Setup developing for puts."
            ],
            'neutral': [
                "Mixed signals - no clear edge.",
                "Wait for better setup.",
                "Protect capital - stay patient."
            ]
        }
    
    def generate_explanation(self, indicators: Dict[str, Any], regime: Dict[str, Any],
                            zones: Dict[str, Any], confirmation: Dict[str, Any],
                            score: Dict[str, Any], bias: str) -> Dict[str, Any]:
        """
        Generate comprehensive explanation for the current signal
        Returns: main reason, bullet points, education text, entry guidance
        """
        try:
            reasons = self._build_reason_list(indicators, regime, zones, confirmation)
            main_reason = self._get_main_reason(score, bias)
            education = self._get_education_text(score, confirmation, bias)
            entry_guidance = self._get_entry_guidance(indicators, zones, confirmation, bias)
            wait_for = self._get_wait_for_text(indicators, confirmation, bias)
            
            return {
                'main_reason': main_reason,
                'reasons': reasons,
                'education_text': education,
                'entry_guidance': entry_guidance,
                'wait_for_text': wait_for,
                'summary': self._build_summary(score, bias),
                'action_text': self._get_action_text(score, bias)
            }
            
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            return self._empty_explanation()
    
    def _build_reason_list(self, indicators: Dict, regime: Dict, 
                          zones: Dict, confirmation: Dict) -> List[str]:
        """Build list of bullet point reasons"""
        reasons = []
        
        rsi = indicators.get('rsi', {})
        rsi_val = rsi.get('value', 50)
        if rsi_val <= 30:
            reasons.append(f"RSI oversold at {rsi_val:.0f} - potential bounce")
        elif rsi_val >= 70:
            reasons.append(f"RSI overbought at {rsi_val:.0f} - caution on longs")
        elif rsi_val < 45:
            reasons.append(f"RSI weak at {rsi_val:.0f}")
        elif rsi_val > 55:
            reasons.append(f"RSI showing strength at {rsi_val:.0f}")
        
        macd = indicators.get('macd', {})
        signal_type = macd.get('signal_type', 'NEUTRAL')
        if signal_type == 'BULLISH_CROSS':
            reasons.append("MACD bullish crossover - momentum shifting up")
        elif signal_type == 'BEARISH_CROSS':
            reasons.append("MACD bearish crossover - momentum shifting down")
        elif signal_type == 'BULLISH':
            reasons.append("MACD bullish - upward momentum")
        elif signal_type == 'BEARISH':
            reasons.append("MACD bearish - downward momentum")
        
        vwap = indicators.get('vwap', {})
        if vwap.get('above_vwap'):
            reasons.append("Price above VWAP - bullish intraday bias")
        else:
            reasons.append("Price below VWAP - bearish intraday bias")
        
        ema = indicators.get('ema', {})
        ema_trend = ema.get('trend', 'NEUTRAL')
        if ema_trend == 'STRONG_BULLISH':
            reasons.append("Price above all EMAs (13/48/200) - strong uptrend")
        elif ema_trend == 'BULLISH':
            reasons.append("Price above key EMAs - uptrend intact")
        elif ema_trend == 'STRONG_BEARISH':
            reasons.append("Price below all EMAs - strong downtrend")
        elif ema_trend == 'BEARISH':
            reasons.append("Price below key EMAs - downtrend intact")
        
        volume = indicators.get('volume', {})
        spike_ratio = volume.get('spike_ratio', 1.0)
        if spike_ratio >= 2.0:
            reasons.append(f"Volume spike {spike_ratio:.1f}x average - high conviction")
        elif spike_ratio >= 1.5:
            reasons.append(f"Strong volume {spike_ratio:.1f}x average")
        elif spike_ratio < 0.8:
            reasons.append(f"Low volume {spike_ratio:.1f}x - weak conviction")
        
        if regime:
            regime_type = regime.get('regime', 'UNKNOWN')
            if regime_type == 'STRONG_TREND':
                reasons.append("Strong trend regime - trade with trend")
            elif regime_type == 'RANGE':
                reasons.append("Ranging market - fade extremes")
            elif regime_type == 'DISTRIBUTION':
                reasons.append("Distribution detected - caution on longs")
        
        if zones:
            if zones.get('in_demand_zone'):
                reasons.append("Price at demand zone - support area")
            elif zones.get('in_supply_zone'):
                reasons.append("Price at supply zone - resistance area")
        
        if confirmation and confirmation.get('confirmations'):
            for conf in confirmation['confirmations'][:2]:
                if conf.get('description'):
                    reasons.append(conf['description'])
        
        return reasons[:7]
    
    def _get_main_reason(self, score: Dict, bias: str) -> str:
        """Get the main reason for the signal"""
        final_score = score.get('final_score', 0)
        bullish_count = score.get('bullish_count', 0)
        bearish_count = score.get('bearish_count', 0)
        
        if final_score >= 80:
            if bias == 'BULLISH':
                return f"Strong bullish setup: {bullish_count} of 5 indicators aligned with high confluence."
            else:
                return f"Strong bearish setup: {bearish_count} of 5 indicators aligned with high confluence."
        elif final_score >= 65:
            if bias == 'BULLISH':
                return f"Bullish setup forming: {bullish_count} of 5 indicators aligned."
            else:
                return f"Bearish setup forming: {bearish_count} of 5 indicators aligned."
        elif final_score >= 50:
            return f"Mixed signals: {bullish_count} bullish, {bearish_count} bearish. Wait for confirmation."
        else:
            return "No clear edge detected. Protect capital and wait for better setup."
    
    def _get_education_text(self, score: Dict, confirmation: Dict, bias: str) -> str:
        """Get educational coaching text"""
        action = score.get('action_recommendation', 'WAIT')
        
        if action in ['STRONG BUY', 'STRONG SELL']:
            return "High conviction setup - enter with defined stop. Size appropriately."
        elif action in ['BUY', 'SELL']:
            return "Confirmed setup - enter with stop below support/above resistance."
        elif action == 'PREPARE':
            return "Bias forming - wait for confirmation to improve entry and reduce risk."
        else:
            return "No edge detected - protect capital. Best trade is sometimes no trade."
    
    def _get_entry_guidance(self, indicators: Dict, zones: Dict, 
                           confirmation: Dict, bias: str) -> Dict[str, Any]:
        """Get specific entry guidance"""
        vwap = indicators.get('vwap', {})
        sr = indicators.get('support_resistance', {})
        current_price = vwap.get('value', 0) or sr.get('support', 0)
        
        entry_type = "Market"
        entry_level = current_price
        stop_level = 0
        target_level = 0
        
        if bias == 'BULLISH':
            entry_type = "VWAP reclaim" if not vwap.get('above_vwap') else "Pullback to VWAP"
            stop_level = min(sr.get('support', current_price * 0.98), vwap.get('value', current_price) * 0.995)
            target_level = sr.get('resistance', current_price * 1.02)
        else:
            entry_type = "VWAP rejection" if vwap.get('above_vwap') else "Breakdown continuation"
            stop_level = max(sr.get('resistance', current_price * 1.02), vwap.get('value', current_price) * 1.005)
            target_level = sr.get('support', current_price * 0.98)
        
        risk = abs(current_price - stop_level)
        reward = abs(target_level - current_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        return {
            'entry_type': entry_type,
            'entry_level': round(current_price, 2),
            'stop_level': round(stop_level, 2),
            'target_level': round(target_level, 2),
            'risk_reward': round(rr_ratio, 2),
            'stop_rationale': f"Stop placed below {'VWAP/support' if bias == 'BULLISH' else 'VWAP/resistance'}",
            'max_loss_rule': "Exit if option premium drops 30%"
        }
    
    def _get_wait_for_text(self, indicators: Dict, confirmation: Dict, bias: str) -> str:
        """Get text explaining what we're waiting for"""
        if confirmation and confirmation.get('is_confirmed'):
            return ""
        
        rsi = indicators.get('rsi', {})
        vwap = indicators.get('vwap', {})
        volume = indicators.get('volume', {})
        
        if bias == 'BULLISH':
            if rsi.get('overbought'):
                return "Waiting for RSI to cool down and pullback to VWAP."
            elif not vwap.get('above_vwap'):
                return "Waiting for price to reclaim VWAP."
            elif volume.get('spike_ratio', 1) < 1.2:
                return "Waiting for volume expansion to confirm breakout."
            else:
                return "Waiting for entry confirmation (rejection candle, higher low)."
        else:
            if rsi.get('oversold'):
                return "Waiting for bounce into resistance to fade."
            elif vwap.get('above_vwap'):
                return "Waiting for price to lose VWAP."
            elif volume.get('spike_ratio', 1) < 1.2:
                return "Waiting for volume expansion to confirm breakdown."
            else:
                return "Waiting for entry confirmation (rejection candle, lower high)."
    
    def _build_summary(self, score: Dict, bias: str) -> str:
        """Build a one-line summary"""
        action = score.get('action_recommendation', 'WAIT')
        confidence = score.get('final_score', 0)
        
        if action == 'STRONG BUY':
            return f"High conviction bullish ({confidence:.0f}% confidence) - enter long"
        elif action == 'BUY':
            return f"Bullish setup ({confidence:.0f}% confidence) - good for calls"
        elif action == 'STRONG SELL':
            return f"High conviction bearish ({confidence:.0f}% confidence) - enter short"
        elif action == 'SELL':
            return f"Bearish setup ({confidence:.0f}% confidence) - good for puts"
        elif action == 'PREPARE':
            return f"Bias forming ({confidence:.0f}% confidence) - wait for confirmation"
        else:
            return "No clear setup - wait for better opportunity"
    
    def _get_action_text(self, score: Dict, bias: str) -> str:
        """Get the action text for the main signal display"""
        return score.get('action_recommendation', 'WAIT')
    
    def _empty_explanation(self) -> Dict[str, Any]:
        """Return empty explanation"""
        return {
            'main_reason': 'Unable to analyze - insufficient data',
            'reasons': [],
            'education_text': 'Wait for more data',
            'entry_guidance': {},
            'wait_for_text': '',
            'summary': 'Analyzing...',
            'action_text': 'WAIT'
        }
