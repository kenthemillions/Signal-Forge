"""
Signal Engine - Zones Module
Supply/Demand zone detection using swing highs/lows and clustering
"""

import numpy as np
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Zone:
    """Represents a supply or demand zone"""
    zone_type: str  # 'SUPPLY' or 'DEMAND'
    upper: float
    lower: float
    strength: float  # 0-1 based on touches and reactions
    touches: int
    created_at_index: int
    still_valid: bool = True


class ZoneDetector:
    """Detect supply and demand zones from price action"""
    
    def __init__(self, cluster_threshold: float = 0.005):
        self.cluster_threshold = cluster_threshold  # 0.5% default clustering
        self.min_zone_width = 0.002  # Minimum 0.2% zone width
        self.max_zone_width = 0.02   # Maximum 2% zone width
    
    def detect_zones(self, highs: List[float], lows: List[float], 
                     closes: List[float], volumes: List[float]) -> Dict[str, Any]:
        """
        Detect supply and demand zones from price data
        Returns: zones with current price position
        """
        try:
            if len(closes) < 30:
                return self._empty_zones(closes[-1] if closes else 0)
            
            swing_highs = self._find_swing_highs(highs, lows)
            swing_lows = self._find_swing_lows(highs, lows)
            
            supply_zones = self._cluster_into_zones(swing_highs, 'SUPPLY', closes)
            demand_zones = self._cluster_into_zones(swing_lows, 'DEMAND', closes)
            
            self._validate_zones(supply_zones, closes)
            self._validate_zones(demand_zones, closes)
            
            supply_zones = [z for z in supply_zones if z.still_valid]
            demand_zones = [z for z in demand_zones if z.still_valid]
            
            current_price = closes[-1]
            
            return {
                'supply_zones': [self._zone_to_dict(z) for z in supply_zones[:3]],
                'demand_zones': [self._zone_to_dict(z) for z in demand_zones[:3]],
                'nearest_supply': self._find_nearest_zone(supply_zones, current_price, 'above'),
                'nearest_demand': self._find_nearest_zone(demand_zones, current_price, 'below'),
                'current_price': current_price,
                'in_supply_zone': self._is_in_zone(current_price, supply_zones),
                'in_demand_zone': self._is_in_zone(current_price, demand_zones),
                'zone_bias': self._determine_zone_bias(current_price, supply_zones, demand_zones)
            }
        except Exception as e:
            logger.error(f"Error detecting zones: {e}")
            return self._empty_zones(closes[-1] if closes else 0)
    
    def _find_swing_highs(self, highs: List[float], lows: List[float], 
                          lookback: int = 5) -> List[Tuple[int, float]]:
        """Find swing high points"""
        swing_highs = []
        
        for i in range(lookback, len(highs) - lookback):
            is_swing_high = True
            current_high = highs[i]
            
            for j in range(1, lookback + 1):
                if highs[i - j] >= current_high or highs[i + j] >= current_high:
                    is_swing_high = False
                    break
            
            if is_swing_high:
                swing_highs.append((i, current_high))
        
        return swing_highs
    
    def _find_swing_lows(self, highs: List[float], lows: List[float],
                         lookback: int = 5) -> List[Tuple[int, float]]:
        """Find swing low points"""
        swing_lows = []
        
        for i in range(lookback, len(lows) - lookback):
            is_swing_low = True
            current_low = lows[i]
            
            for j in range(1, lookback + 1):
                if lows[i - j] <= current_low or lows[i + j] <= current_low:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                swing_lows.append((i, current_low))
        
        return swing_lows
    
    def _cluster_into_zones(self, points: List[Tuple[int, float]], 
                            zone_type: str, closes: List[float]) -> List[Zone]:
        """Cluster swing points into zones"""
        if not points:
            return []
        
        sorted_points = sorted(points, key=lambda x: x[1])
        
        zones = []
        current_cluster = [sorted_points[0]]
        
        for i in range(1, len(sorted_points)):
            prev_price = sorted_points[i-1][1]
            curr_price = sorted_points[i][1]
            
            threshold = prev_price * self.cluster_threshold
            
            if abs(curr_price - prev_price) <= threshold:
                current_cluster.append(sorted_points[i])
            else:
                if len(current_cluster) >= 1:
                    zone = self._create_zone(current_cluster, zone_type, closes)
                    if zone:
                        zones.append(zone)
                current_cluster = [sorted_points[i]]
        
        if current_cluster:
            zone = self._create_zone(current_cluster, zone_type, closes)
            if zone:
                zones.append(zone)
        
        zones.sort(key=lambda z: z.strength, reverse=True)
        
        return zones
    
    def _create_zone(self, cluster: List[Tuple[int, float]], 
                     zone_type: str, closes: List[float]) -> Zone:
        """Create a zone from a cluster of points"""
        prices = [p[1] for p in cluster]
        indices = [p[0] for p in cluster]
        
        zone_upper = max(prices)
        zone_lower = min(prices)
        
        width_pct = (zone_upper - zone_lower) / zone_lower if zone_lower > 0 else 0
        
        if width_pct < self.min_zone_width:
            mid = (zone_upper + zone_lower) / 2
            half_width = mid * self.min_zone_width / 2
            zone_upper = mid + half_width
            zone_lower = mid - half_width
        elif width_pct > self.max_zone_width:
            mid = (zone_upper + zone_lower) / 2
            half_width = mid * self.max_zone_width / 2
            zone_upper = mid + half_width
            zone_lower = mid - half_width
        
        touches = len(cluster)
        recency = max(indices) / len(closes) if closes else 0.5
        
        strength = min(1.0, (touches * 0.2) + (recency * 0.3) + 0.3)
        
        return Zone(
            zone_type=zone_type,
            upper=round(zone_upper, 2),
            lower=round(zone_lower, 2),
            strength=round(strength, 2),
            touches=touches,
            created_at_index=min(indices),
            still_valid=True
        )
    
    def _validate_zones(self, zones: List[Zone], closes: List[float]) -> None:
        """Check if zones have been violated (broken through with conviction)"""
        if len(closes) < 10:
            return
        
        for zone in zones:
            for i in range(-10, 0):
                close = closes[i]
                
                if zone.zone_type == 'SUPPLY':
                    if close > zone.upper * 1.01:
                        zone.still_valid = False
                        break
                else:
                    if close < zone.lower * 0.99:
                        zone.still_valid = False
                        break
    
    def _find_nearest_zone(self, zones: List[Zone], price: float, 
                          direction: str) -> Dict[str, Any]:
        """Find the nearest zone above or below current price"""
        if not zones:
            return None
        
        if direction == 'above':
            above_zones = [z for z in zones if z.lower > price]
            if not above_zones:
                return None
            nearest = min(above_zones, key=lambda z: z.lower - price)
        else:
            below_zones = [z for z in zones if z.upper < price]
            if not below_zones:
                return None
            nearest = max(below_zones, key=lambda z: z.upper)
        
        distance_pct = abs((nearest.lower if direction == 'above' else nearest.upper) - price) / price * 100
        
        return {
            'zone': self._zone_to_dict(nearest),
            'distance_pct': round(distance_pct, 2)
        }
    
    def _is_in_zone(self, price: float, zones: List[Zone]) -> bool:
        """Check if price is currently in any zone"""
        for zone in zones:
            if zone.lower <= price <= zone.upper:
                return True
        return False
    
    def _determine_zone_bias(self, price: float, supply_zones: List[Zone], 
                            demand_zones: List[Zone]) -> str:
        """Determine trading bias based on zone position"""
        in_supply = self._is_in_zone(price, supply_zones)
        in_demand = self._is_in_zone(price, demand_zones)
        
        if in_supply:
            return 'BEARISH'
        elif in_demand:
            return 'BULLISH'
        
        nearest_supply = self._find_nearest_zone(supply_zones, price, 'above')
        nearest_demand = self._find_nearest_zone(demand_zones, price, 'below')
        
        if nearest_supply and nearest_demand:
            supply_dist = nearest_supply['distance_pct']
            demand_dist = nearest_demand['distance_pct']
            
            if supply_dist < demand_dist * 0.5:
                return 'BEARISH'
            elif demand_dist < supply_dist * 0.5:
                return 'BULLISH'
        
        return 'NEUTRAL'
    
    def _zone_to_dict(self, zone: Zone) -> Dict[str, Any]:
        """Convert Zone object to dictionary"""
        return {
            'type': zone.zone_type,
            'upper': zone.upper,
            'lower': zone.lower,
            'strength': zone.strength,
            'touches': zone.touches,
            'valid': zone.still_valid
        }
    
    def _empty_zones(self, current_price: float) -> Dict[str, Any]:
        """Return empty zones response"""
        return {
            'supply_zones': [],
            'demand_zones': [],
            'nearest_supply': None,
            'nearest_demand': None,
            'current_price': current_price,
            'in_supply_zone': False,
            'in_demand_zone': False,
            'zone_bias': 'NEUTRAL'
        }
