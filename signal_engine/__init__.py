"""
Signal Forge - Signal Engine Package
A modular trading signal generation system
"""

from .indicators import IndicatorCalculator
from .market_regime import MarketRegimeDetector
from .zones import ZoneDetector
from .confirmation import ConfirmationEngine
from .scoring import SignalScorer
from .explanations import ExplanationGenerator
from .institutional import InstitutionalEngine, institutional_engine
from .seasonality import SeasonalityAnalyzer, seasonality_analyzer

__all__ = [
    'IndicatorCalculator',
    'MarketRegimeDetector', 
    'ZoneDetector',
    'ConfirmationEngine',
    'SignalScorer',
    'ExplanationGenerator',
    'InstitutionalEngine',
    'institutional_engine',
    'SeasonalityAnalyzer',
    'seasonality_analyzer'
]
