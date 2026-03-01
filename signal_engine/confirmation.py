"""
Signal Engine - Confirmation Module
Entry confirmation logic: rejection candles, lower-highs, VWAP rejection, RSI divergence
"""

import numpy as np
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class ConfirmationEngine:
    """Validate trade setups with confirmation signals"""
    
    def __init__(self):
        self.confirmation_weights = {
            'rejection_candle': 0.25,
            'structure': 0.20,
            'vwap_rejection': 0.20,
            'rsi_divergence': 0.15,
            'volume_confirmation': 0.20
        }
    
    def check_confirmations(self, data: Dict[str, Any], indicators: Dict[str, Any],
                           zones: Dict[str, Any], bias: str) -> Dict[str, Any]:
        """
        Check for entry confirmation signals
        Returns: confirmation status with score and details
        """
        try:
            prices = data.get('prices', [])
            opens = data.get('opens', prices)
            highs = data.get('highs', prices)
            lows = data.get('lows', prices)
            closes = prices
            volumes = data.get('volumes', [])
            
            if len(prices) < 10:
                return self._no_confirmation("Insufficient data")
            
            confirmations = []
            total_score = 0
            
            rejection = self._check_rejection_candle(opens, highs, lows, closes, bias)
            if rejection['confirmed']:
                confirmations.append(rejection)
                total_score += rejection['score'] * self.confirmation_weights['rejection_candle']
            
            structure = self._check_structure(highs, lows, closes, bias)
            if structure['confirmed']:
                confirmations.append(structure)
                total_score += structure['score'] * self.confirmation_weights['structure']
            
            vwap = self._check_vwap_confirmation(closes, indicators.get('vwap', {}), bias)
            if vwap['confirmed']:
                confirmations.append(vwap)
                total_score += vwap['score'] * self.confirmation_weights['vwap_rejection']
            
            divergence = self._check_rsi_divergence(closes, indicators.get('rsi', {}), bias)
            if divergence['confirmed']:
                confirmations.append(divergence)
                total_score += divergence['score'] * self.confirmation_weights['rsi_divergence']
            
            volume = self._check_volume_confirmation(volumes, indicators.get('volume', {}), bias)
            if volume['confirmed']:
                confirmations.append(volume)
                total_score += volume['score'] * self.confirmation_weights['volume_confirmation']
            
            zone_conf = self._check_zone_confirmation(closes[-1], zones, bias)
            if zone_conf['confirmed']:
                confirmations.append(zone_conf)
                total_score *= 1.2
            
            is_confirmed = total_score >= 0.4 and len(confirmations) >= 2
            
            return {
                'is_confirmed': is_confirmed,
                'score': round(total_score, 2),
                'confirmations': confirmations,
                'confirmation_count': len(confirmations),
                'status': 'CONFIRMED' if is_confirmed else 'PENDING' if confirmations else 'NO_CONFIRMATION',
                'summary': self._generate_confirmation_summary(confirmations, is_confirmed)
            }
        
        except Exception as e:
            logger.error(f"Error checking confirmations: {e}")
            return self._no_confirmation(str(e))
    
    def _check_rejection_candle(self, opens: List[float], highs: List[float],
                                lows: List[float], closes: List[float], 
                                bias: str) -> Dict[str, Any]:
        """Check for rejection candle patterns (pin bars, hammers, engulfing)"""
        if len(closes) < 3:
            return {'type': 'rejection_candle', 'confirmed': False}
        
        o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
        body = abs(c - o)
        total_range = h - l if h > l else 0.01
        body_pct = body / total_range
        
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        
        if bias == 'BULLISH':
            if lower_wick > body * 2 and upper_wick < body * 0.5:
                return {
                    'type': 'rejection_candle',
                    'confirmed': True,
                    'pattern': 'HAMMER',
                    'score': 0.8,
                    'description': 'Bullish hammer rejection'
                }
            
            prev_body = abs(closes[-2] - opens[-2])
            if c > o and body > prev_body * 1.5 and closes[-2] < opens[-2]:
                return {
                    'type': 'rejection_candle',
                    'confirmed': True,
                    'pattern': 'BULLISH_ENGULFING',
                    'score': 0.9,
                    'description': 'Bullish engulfing pattern'
                }
        
        elif bias == 'BEARISH':
            if upper_wick > body * 2 and lower_wick < body * 0.5:
                return {
                    'type': 'rejection_candle',
                    'confirmed': True,
                    'pattern': 'SHOOTING_STAR',
                    'score': 0.8,
                    'description': 'Bearish shooting star rejection'
                }
            
            prev_body = abs(closes[-2] - opens[-2])
            if c < o and body > prev_body * 1.5 and closes[-2] > opens[-2]:
                return {
                    'type': 'rejection_candle',
                    'confirmed': True,
                    'pattern': 'BEARISH_ENGULFING',
                    'score': 0.9,
                    'description': 'Bearish engulfing pattern'
                }
        
        return {'type': 'rejection_candle', 'confirmed': False}
    
    def _check_structure(self, highs: List[float], lows: List[float],
                        closes: List[float], bias: str) -> Dict[str, Any]:
        """Check for structural confirmation (lower-high, higher-low)"""
        if len(closes) < 10:
            return {'type': 'structure', 'confirmed': False}
        
        recent_high = max(highs[-5:])
        prev_high = max(highs[-10:-5])
        recent_low = min(lows[-5:])
        prev_low = min(lows[-10:-5])
        
        if bias == 'BULLISH':
            if recent_low > prev_low:
                return {
                    'type': 'structure',
                    'confirmed': True,
                    'pattern': 'HIGHER_LOW',
                    'score': 0.7,
                    'description': 'Higher low forming - bullish structure'
                }
        
        elif bias == 'BEARISH':
            if recent_high < prev_high:
                return {
                    'type': 'structure',
                    'confirmed': True,
                    'pattern': 'LOWER_HIGH',
                    'score': 0.7,
                    'description': 'Lower high forming - bearish structure'
                }
        
        return {'type': 'structure', 'confirmed': False}
    
    def _check_vwap_confirmation(self, closes: List[float], vwap_data: Dict,
                                 bias: str) -> Dict[str, Any]:
        """Check for VWAP reclaim or rejection"""
        if not vwap_data or len(closes) < 5:
            return {'type': 'vwap', 'confirmed': False}
        
        vwap_value = vwap_data.get('value', closes[-1])
        current = closes[-1]
        prev = closes[-2] if len(closes) > 1 else current
        
        if bias == 'BULLISH':
            if prev < vwap_value and current > vwap_value:
                return {
                    'type': 'vwap',
                    'confirmed': True,
                    'pattern': 'VWAP_RECLAIM',
                    'score': 0.85,
                    'description': 'Price reclaimed VWAP - bullish'
                }
            
            if current > vwap_value and abs(closes[-3] - vwap_value) / vwap_value < 0.002:
                return {
                    'type': 'vwap',
                    'confirmed': True,
                    'pattern': 'VWAP_BOUNCE',
                    'score': 0.75,
                    'description': 'Price bounced off VWAP support'
                }
        
        elif bias == 'BEARISH':
            if prev > vwap_value and current < vwap_value:
                return {
                    'type': 'vwap',
                    'confirmed': True,
                    'pattern': 'VWAP_REJECTION',
                    'score': 0.85,
                    'description': 'Price rejected at VWAP - bearish'
                }
        
        return {'type': 'vwap', 'confirmed': False}
    
    def _check_rsi_divergence(self, closes: List[float], rsi_data: Dict,
                              bias: str) -> Dict[str, Any]:
        """Check for RSI divergence"""
        if not rsi_data or len(closes) < 20:
            return {'type': 'rsi_divergence', 'confirmed': False}
        
        rsi_value = rsi_data.get('value', 50)
        
        if bias == 'BULLISH' and rsi_value < 35:
            recent_low = min(closes[-10:])
            prev_low = min(closes[-20:-10])
            
            if recent_low < prev_low:
                return {
                    'type': 'rsi_divergence',
                    'confirmed': True,
                    'pattern': 'BULLISH_DIVERGENCE',
                    'score': 0.7,
                    'description': 'Potential bullish RSI divergence'
                }
        
        elif bias == 'BEARISH' and rsi_value > 65:
            recent_high = max(closes[-10:])
            prev_high = max(closes[-20:-10])
            
            if recent_high > prev_high:
                return {
                    'type': 'rsi_divergence',
                    'confirmed': True,
                    'pattern': 'BEARISH_DIVERGENCE',
                    'score': 0.7,
                    'description': 'Potential bearish RSI divergence'
                }
        
        return {'type': 'rsi_divergence', 'confirmed': False}
    
    def _check_volume_confirmation(self, volumes: List[float], volume_data: Dict,
                                   bias: str) -> Dict[str, Any]:
        """Check for volume confirmation"""
        if not volume_data or len(volumes) < 5:
            return {'type': 'volume', 'confirmed': False}
        
        spike_ratio = volume_data.get('spike_ratio', 1.0)
        is_above_avg = volume_data.get('above_average', False)
        
        if spike_ratio >= 1.5:
            return {
                'type': 'volume',
                'confirmed': True,
                'pattern': 'VOLUME_SPIKE',
                'score': 0.85,
                'description': f'Volume spike ({spike_ratio:.1f}x average) confirms move'
            }
        elif is_above_avg:
            return {
                'type': 'volume',
                'confirmed': True,
                'pattern': 'ABOVE_AVERAGE',
                'score': 0.6,
                'description': 'Above average volume supports move'
            }
        
        return {'type': 'volume', 'confirmed': False}
    
    def _check_zone_confirmation(self, price: float, zones: Dict, bias: str) -> Dict[str, Any]:
        """Check if price is at a key zone that confirms bias"""
        if not zones:
            return {'type': 'zone', 'confirmed': False}
        
        if bias == 'BULLISH' and zones.get('in_demand_zone'):
            return {
                'type': 'zone',
                'confirmed': True,
                'pattern': 'AT_DEMAND_ZONE',
                'score': 0.8,
                'description': 'Price at demand zone - high probability long'
            }
        
        elif bias == 'BEARISH' and zones.get('in_supply_zone'):
            return {
                'type': 'zone',
                'confirmed': True,
                'pattern': 'AT_SUPPLY_ZONE',
                'score': 0.8,
                'description': 'Price at supply zone - high probability short'
            }
        
        return {'type': 'zone', 'confirmed': False}
    
    def _generate_confirmation_summary(self, confirmations: List[Dict], is_confirmed: bool) -> str:
        """Generate human-readable confirmation summary"""
        if not confirmations:
            return "No confirmation signals detected - wait for setup"
        
        patterns = [c.get('pattern', 'Unknown') for c in confirmations]
        
        if is_confirmed:
            return f"CONFIRMED: {', '.join(patterns)} - Entry conditions met"
        else:
            return f"PENDING: {', '.join(patterns)} - Need more confirmation"
    
    def _no_confirmation(self, reason: str = "") -> Dict[str, Any]:
        """Return empty confirmation result"""
        return {
            'is_confirmed': False,
            'score': 0,
            'confirmations': [],
            'confirmation_count': 0,
            'status': 'NO_DATA',
            'summary': f"Cannot check confirmations: {reason}" if reason else "No confirmation data"
        }
