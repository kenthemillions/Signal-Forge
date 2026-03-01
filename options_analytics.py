"""
Advanced Options Analytics Module
Provides edge-driving features for options traders:
- Greeks sensitivity analysis
- Volatility regime detection
- Institutional flow heatmaps
- Probability calculations
"""
import numpy as np
from scipy.stats import norm
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import math

class OptionsAnalytics:
    """Advanced options analytics for competitive edge"""
    
    def __init__(self):
        self.risk_free_rate = 0.05
    
    def calculate_greeks(self, spot_price: float, strike: float, 
                        days_to_expiry: int, volatility: float,
                        option_type: str = 'call') -> Dict:
        """Calculate Black-Scholes Greeks for options"""
        if days_to_expiry <= 0 or volatility <= 0 or spot_price <= 0:
            return self._empty_greeks()
        
        T = days_to_expiry / 365
        S = spot_price
        K = strike
        r = self.risk_free_rate
        sigma = volatility
        
        try:
            d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            d2 = d1 - sigma * math.sqrt(T)
            
            if option_type.lower() == 'call':
                delta = norm.cdf(d1)
                theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) - 
                        r * K * math.exp(-r * T) * norm.cdf(d2)) / 365
            else:
                delta = -norm.cdf(-d1)
                theta = (-S * norm.pdf(d1) * sigma / (2 * math.sqrt(T)) + 
                        r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365
            
            gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
            vega = S * norm.pdf(d1) * math.sqrt(T) / 100
            rho = K * T * math.exp(-r * T) * norm.cdf(d2 if option_type.lower() == 'call' else -d2) / 100
            
            return {
                'delta': round(delta, 4),
                'gamma': round(gamma, 6),
                'theta': round(theta, 4),
                'vega': round(vega, 4),
                'rho': round(rho, 4),
                'delta_dollars': round(delta * spot_price, 2),
                'theta_decay_1d': round(theta, 2),
                'theta_decay_7d': round(theta * 7, 2),
                'gamma_risk': self._gamma_risk_level(gamma, spot_price),
                'theta_warning': theta < -0.05,
                'interpretation': self._interpret_greeks(delta, gamma, theta, vega, option_type)
            }
        except Exception:
            return self._empty_greeks()
    
    def _empty_greeks(self) -> Dict:
        return {
            'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0, 'rho': 0,
            'delta_dollars': 0, 'theta_decay_1d': 0, 'theta_decay_7d': 0,
            'gamma_risk': 'LOW', 'theta_warning': False, 'interpretation': []
        }
    
    def _gamma_risk_level(self, gamma: float, price: float) -> str:
        gamma_dollars = gamma * price * price * 0.01
        if gamma_dollars > 5:
            return 'HIGH'
        elif gamma_dollars > 2:
            return 'MEDIUM'
        return 'LOW'
    
    def _interpret_greeks(self, delta: float, gamma: float, 
                         theta: float, vega: float, option_type: str) -> List[str]:
        insights = []
        
        abs_delta = abs(delta)
        if abs_delta > 0.7:
            insights.append(f"Deep {'ITM' if delta > 0 else 'OTM'} - moves like stock")
        elif abs_delta > 0.4:
            insights.append("ATM zone - max gamma sensitivity")
        else:
            insights.append("Far OTM - low probability of profit")
        
        if gamma > 0.05:
            insights.append("High gamma - delta changes rapidly near expiry")
        
        if theta < -0.10:
            insights.append("Heavy theta decay - consider shorter holds")
        elif theta < -0.03:
            insights.append("Moderate time decay")
        
        if vega > 0.15:
            insights.append("Vega sensitive - watch for IV crush")
        
        return insights
    
    def calculate_volatility_regime(self, prices: List[float], 
                                   volumes: List[float] = None) -> Dict:
        """Detect current volatility regime for strategy selection"""
        if len(prices) < 20:
            return {'regime': 'UNKNOWN', 'confidence': 0}
        
        prices_arr = np.array(prices)
        returns = np.diff(np.log(prices_arr))
        
        recent_vol = np.std(returns[-5:]) * np.sqrt(252) * 100
        short_vol = np.std(returns[-10:]) * np.sqrt(252) * 100
        long_vol = np.std(returns[-20:]) * np.sqrt(252) * 100
        
        vol_trend = (short_vol - long_vol) / long_vol * 100 if long_vol > 0 else 0
        
        range_5d = (max(prices[-5:]) - min(prices[-5:])) / prices[-5] * 100
        range_20d = (max(prices[-20:]) - min(prices[-20:])) / prices[-20] * 100
        range_compression = range_5d / range_20d if range_20d > 0 else 1
        
        if recent_vol < 15 and range_compression < 0.5:
            regime = 'LOW_VOLATILITY'
            description = 'Low volatility environment - spreads & iron condors favor'
            color = '#22C55E'
        elif recent_vol > 35 or vol_trend > 30:
            regime = 'HIGH_VOLATILITY'
            description = 'High volatility - directional plays, wide stops needed'
            color = '#EF4444'
        elif vol_trend > 15:
            regime = 'EXPANDING'
            description = 'Volatility expanding - momentum strategies work well'
            color = '#F59E0B'
        elif vol_trend < -15:
            regime = 'CONTRACTING'
            description = 'Volatility contracting - prepare for breakout'
            color = '#3B82F6'
        else:
            regime = 'NORMAL'
            description = 'Normal volatility - standard strategies apply'
            color = '#8B5CF6'
        
        strategies = self._get_regime_strategies(regime)
        
        return {
            'regime': regime,
            'description': description,
            'color': color,
            'metrics': {
                'recent_vol': round(recent_vol, 1),
                'short_vol': round(short_vol, 1),
                'long_vol': round(long_vol, 1),
                'vol_trend': round(vol_trend, 1),
                'range_compression': round(range_compression, 2)
            },
            'recommended_strategies': strategies,
            'confidence': min(95, 60 + abs(vol_trend))
        }
    
    def _get_regime_strategies(self, regime: str) -> List[Dict]:
        strategies = {
            'LOW_VOLATILITY': [
                {'name': 'Iron Condor', 'reason': 'Collect premium in range-bound market'},
                {'name': 'Credit Spreads', 'reason': 'High probability trades'},
                {'name': 'Calendar Spreads', 'reason': 'Benefit from vol expansion'}
            ],
            'HIGH_VOLATILITY': [
                {'name': 'Debit Spreads', 'reason': 'Defined risk, reduced cost'},
                {'name': 'Long Straddles', 'reason': 'Capture big moves'},
                {'name': 'Wide Stop Plays', 'reason': 'Avoid whipsaws'}
            ],
            'EXPANDING': [
                {'name': 'Momentum Calls/Puts', 'reason': 'Ride the trend'},
                {'name': 'Breakout Plays', 'reason': 'Volume confirms direction'},
                {'name': 'ATM Options', 'reason': 'Max delta capture'}
            ],
            'CONTRACTING': [
                {'name': 'Strangles (Long)', 'reason': 'Cheap pre-breakout entry'},
                {'name': 'Butterfly Spreads', 'reason': 'Low cost directional bet'},
                {'name': 'Watch Mode', 'reason': 'Wait for breakout confirmation'}
            ],
            'NORMAL': [
                {'name': 'Swing Trades', 'reason': 'Standard 2-5 day holds'},
                {'name': 'Vertical Spreads', 'reason': 'Balanced risk/reward'},
                {'name': 'Follow Signals', 'reason': 'Trust technical analysis'}
            ]
        }
        return strategies.get(regime, strategies['NORMAL'])
    
    def calculate_iv_analysis(self, current_iv: float, iv_history: List[float] = None) -> Dict:
        """Calculate IV Rank and Percentile with trading recommendations"""
        if iv_history is None or len(iv_history) < 20:
            iv_history = [current_iv * 0.9] * 10 + [current_iv] * 10
        
        iv_min = min(iv_history)
        iv_max = max(iv_history)
        
        if iv_max > iv_min:
            iv_rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100
        else:
            iv_rank = 50
        
        iv_percentile = sum(1 for iv in iv_history if iv < current_iv) / len(iv_history) * 100
        
        if iv_rank < 25:
            recommendation = 'BUY OPTIONS'
            explanation = 'IV is low - options are cheap, good for buying'
            color = '#22C55E'
            strategies = ['Long Calls/Puts', 'Long Straddles', 'Debit Spreads']
        elif iv_rank > 75:
            recommendation = 'SELL OPTIONS'
            explanation = 'IV is high - options are expensive, good for selling'
            color = '#EF4444'
            strategies = ['Credit Spreads', 'Iron Condors', 'Covered Calls']
        else:
            recommendation = 'NEUTRAL'
            explanation = 'IV is average - use directional signals'
            color = '#F59E0B'
            strategies = ['Follow Technical Signals', 'Vertical Spreads']
        
        return {
            'current_iv': round(current_iv, 1),
            'iv_rank': round(iv_rank, 1),
            'iv_percentile': round(iv_percentile, 1),
            'iv_min': round(iv_min, 1),
            'iv_max': round(iv_max, 1),
            'recommendation': recommendation,
            'explanation': explanation,
            'color': color,
            'strategies': strategies,
            'warning': iv_rank > 85
        }
    
    def calculate_probability_of_profit(self, spot: float, strike: float,
                                       days: int, volatility: float,
                                       option_type: str = 'call') -> Dict:
        """Calculate probability of option finishing ITM"""
        if days <= 0 or volatility <= 0:
            return {'pop': 0, 'confidence': 'LOW'}
        
        T = days / 365
        sigma = volatility
        
        try:
            d2 = (math.log(spot / strike) + (self.risk_free_rate - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
            
            if option_type.lower() == 'call':
                pop = norm.cdf(d2) * 100
            else:
                pop = norm.cdf(-d2) * 100
            
            if pop > 70:
                confidence = 'HIGH'
                color = '#22C55E'
            elif pop > 50:
                confidence = 'MEDIUM'
                color = '#F59E0B'
            else:
                confidence = 'LOW'
                color = '#EF4444'
            
            return {
                'pop': round(pop, 1),
                'pop_display': f"{round(pop)}%",
                'confidence': confidence,
                'color': color,
                'strike_distance': round((strike - spot) / spot * 100, 2),
                'breakeven': strike
            }
        except Exception:
            return {'pop': 0, 'pop_display': 'N/A', 'confidence': 'LOW', 'color': '#888'}
    
    def generate_flow_heatmap(self, options_data: List[Dict]) -> Dict:
        """Generate institutional flow heatmap data"""
        if not options_data:
            return self._empty_heatmap()
        
        call_volume = sum(o.get('call_volume', 0) for o in options_data)
        put_volume = sum(o.get('put_volume', 0) for o in options_data)
        total_volume = call_volume + put_volume
        
        if total_volume == 0:
            return self._empty_heatmap()
        
        call_ratio = call_volume / total_volume * 100
        put_ratio = put_volume / total_volume * 100
        
        bullish_strikes = []
        bearish_strikes = []
        
        for o in options_data:
            strike = o.get('strike', 0)
            call_oi = o.get('call_oi', 0)
            put_oi = o.get('put_oi', 0)
            
            if call_oi > put_oi * 1.5:
                bullish_strikes.append({'strike': strike, 'intensity': call_oi})
            elif put_oi > call_oi * 1.5:
                bearish_strikes.append({'strike': strike, 'intensity': put_oi})
        
        if call_ratio > 65:
            sentiment = 'STRONGLY_BULLISH'
            color = '#22C55E'
        elif call_ratio > 55:
            sentiment = 'BULLISH'
            color = '#4ADE80'
        elif put_ratio > 65:
            sentiment = 'STRONGLY_BEARISH'
            color = '#EF4444'
        elif put_ratio > 55:
            sentiment = 'BEARISH'
            color = '#F87171'
        else:
            sentiment = 'NEUTRAL'
            color = '#F59E0B'
        
        return {
            'sentiment': sentiment,
            'color': color,
            'call_volume': call_volume,
            'put_volume': put_volume,
            'call_ratio': round(call_ratio, 1),
            'put_ratio': round(put_ratio, 1),
            'bullish_strikes': sorted(bullish_strikes, key=lambda x: x['intensity'], reverse=True)[:5],
            'bearish_strikes': sorted(bearish_strikes, key=lambda x: x['intensity'], reverse=True)[:5],
            'max_pain': self._calculate_max_pain(options_data),
            'unusual_activity': self._detect_unusual_activity(options_data)
        }
    
    def _empty_heatmap(self) -> Dict:
        return {
            'sentiment': 'UNKNOWN', 'color': '#888',
            'call_volume': 0, 'put_volume': 0,
            'call_ratio': 50, 'put_ratio': 50,
            'bullish_strikes': [], 'bearish_strikes': [],
            'max_pain': 0, 'unusual_activity': []
        }
    
    def _calculate_max_pain(self, options_data: List[Dict]) -> float:
        """Calculate max pain strike price"""
        if not options_data:
            return 0
        
        strikes = [o.get('strike', 0) for o in options_data if o.get('strike', 0) > 0]
        if not strikes:
            return 0
        
        total_oi = {}
        for o in options_data:
            strike = o.get('strike', 0)
            total_oi[strike] = o.get('call_oi', 0) + o.get('put_oi', 0)
        
        if total_oi:
            max_pain = max(total_oi.keys(), key=lambda k: total_oi[k])
            return max_pain
        return 0
    
    def _detect_unusual_activity(self, options_data: List[Dict]) -> List[Dict]:
        """Detect unusual options activity"""
        unusual = []
        
        for o in options_data:
            call_vol = o.get('call_volume', 0)
            call_oi = o.get('call_oi', 1)
            put_vol = o.get('put_volume', 0)
            put_oi = o.get('put_oi', 1)
            
            call_ratio = call_vol / call_oi if call_oi > 0 else 0
            put_ratio = put_vol / put_oi if put_oi > 0 else 0
            
            if call_ratio > 3:
                unusual.append({
                    'type': 'CALL',
                    'strike': o.get('strike'),
                    'ratio': round(call_ratio, 1),
                    'signal': 'BULLISH',
                    'description': f"Call volume {call_ratio:.1f}x open interest"
                })
            
            if put_ratio > 3:
                unusual.append({
                    'type': 'PUT',
                    'strike': o.get('strike'),
                    'ratio': round(put_ratio, 1),
                    'signal': 'BEARISH',
                    'description': f"Put volume {put_ratio:.1f}x open interest"
                })
        
        return sorted(unusual, key=lambda x: x['ratio'], reverse=True)[:5]
    
    def get_edge_summary(self, symbol: str, spot_price: float,
                        prices: List[float], iv: float,
                        options_data: List[Dict] = None) -> Dict:
        """Generate comprehensive edge analysis summary"""
        vol_regime = self.calculate_volatility_regime(prices)
        iv_analysis = self.calculate_iv_analysis(iv)
        flow_heatmap = self.generate_flow_heatmap(options_data or [])
        
        edge_signals = []
        edge_score = 50
        
        if vol_regime['regime'] in ['EXPANDING', 'CONTRACTING']:
            edge_signals.append({
                'type': 'VOLATILITY',
                'signal': vol_regime['regime'],
                'action': vol_regime['recommended_strategies'][0]['name']
            })
            edge_score += 10
        
        if iv_analysis['iv_rank'] < 25 or iv_analysis['iv_rank'] > 75:
            edge_signals.append({
                'type': 'IV_EXTREME',
                'signal': iv_analysis['recommendation'],
                'action': iv_analysis['strategies'][0]
            })
            edge_score += 15
        
        if flow_heatmap['sentiment'] in ['STRONGLY_BULLISH', 'STRONGLY_BEARISH']:
            edge_signals.append({
                'type': 'FLOW',
                'signal': flow_heatmap['sentiment'],
                'action': 'Follow institutional flow'
            })
            edge_score += 20
        
        if flow_heatmap['unusual_activity']:
            edge_signals.append({
                'type': 'UNUSUAL_ACTIVITY',
                'signal': 'DETECTED',
                'action': 'Monitor for breakout'
            })
            edge_score += 10
        
        edge_score = min(95, edge_score)
        
        if edge_score >= 75:
            verdict = 'STRONG EDGE'
            color = '#22C55E'
        elif edge_score >= 60:
            verdict = 'MODERATE EDGE'
            color = '#F59E0B'
        else:
            verdict = 'WAIT FOR SETUP'
            color = '#EF4444'
        
        return {
            'symbol': symbol,
            'edge_score': edge_score,
            'verdict': verdict,
            'verdict_color': color,
            'signals': edge_signals,
            'volatility_regime': vol_regime,
            'iv_analysis': iv_analysis,
            'flow_heatmap': flow_heatmap,
            'timestamp': datetime.now().isoformat()
        }


options_analytics = OptionsAnalytics()
