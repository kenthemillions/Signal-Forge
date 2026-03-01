"""
Signal Forge - Configuration Module
Environment variable handling and application settings
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Config:
    """Application configuration from environment variables"""
    
    SECRET_KEY = os.environ.get('SESSION_SECRET', os.urandom(24).hex())
    
    DATABASE_URL = os.environ.get('DATABASE_URL')
    SQLITE_PATH = os.environ.get('SQLITE_PATH', 'trading_signals.db')
    
    # Production (e.g. Render): set DATABASE_URL for persistent DB. Else SQLite (data lost on redeploy).
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = ('postgresql://' + DATABASE_URL[11:]) if DATABASE_URL.startswith('postgres://') else DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///trading_signals.db'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    YFINANCE_ENABLED = True
    POLYGON_API_KEY = os.environ.get('POLYGON_API_KEY')
    ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_KEY')
    
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 60))
    
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    SOCKETIO_ASYNC_MODE = 'eventlet'
    SOCKETIO_CORS_ALLOWED_ORIGINS = '*'
    
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))
    
    RSI_PERIOD = int(os.environ.get('RSI_PERIOD', 14))
    EMA_FAST = int(os.environ.get('EMA_FAST', 13))
    EMA_MID = int(os.environ.get('EMA_MID', 48))
    EMA_SLOW = int(os.environ.get('EMA_SLOW', 200))
    ATR_PERIOD = int(os.environ.get('ATR_PERIOD', 14))
    VOLUME_AVG_PERIOD = int(os.environ.get('VOLUME_AVG_PERIOD', 20))
    
    STRONG_SIGNAL_THRESHOLD = int(os.environ.get('STRONG_SIGNAL_THRESHOLD', 80))
    SIGNAL_THRESHOLD = int(os.environ.get('SIGNAL_THRESHOLD', 65))
    
    DEFAULT_PLAN = 'free'
    MASTER_USERNAME = os.environ.get('MASTER_USERNAME', 'admin')
    MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD', 'SignalForge2026!')
    BETA_USERNAME = os.environ.get('BETA_USERNAME', 'beta')
    BETA_PASSWORD = os.environ.get('BETA_PASSWORD', 'BetaAccess2026!')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    STRIPE_PRICE_PRO_ID = os.environ.get('STRIPE_PRICE_PRO_ID', '')
    STRIPE_PRICE_ELITE_ID = os.environ.get('STRIPE_PRICE_ELITE_ID', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    PLAN_FEATURES = {
        'free': {
            'name': 'Free',
            'price': 0,
            'max_watchlist': 5,
            'multi_timeframe': False,
            'zones': False,
            'journal': False,
            'alerts': False
        },
        'beta': {
            'name': 'Beta Tester',
            'price': 0,
            'max_watchlist': 10,
            'multi_timeframe': True,
            'zones': True,
            'journal': False,
            'alerts': True
        },
        'pro': {
            'name': 'Pro Coach',
            'price': 59,
            'max_watchlist': 25,
            'multi_timeframe': True,
            'zones': True,
            'journal': True,
            'alerts': True
        },
        'elite': {
            'name': 'Elite Funded',
            'price': 129,
            'max_watchlist': -1,
            'multi_timeframe': True,
            'zones': True,
            'journal': True,
            'alerts': True,
            'priority_support': True
        }
    }
    
    @classmethod
    def init_app(cls, app):
        """Initialize app with configuration"""
        app.config.from_object(cls)
        
        if not app.config.get('SECRET_KEY'):
            logger.warning("No SESSION_SECRET set - using random key")
        
        logging.basicConfig(
            level=getattr(logging, cls.LOG_LEVEL.upper()),
            format=cls.LOG_FORMAT
        )
        
        logger.info(f"App initialized with database: {cls.SQLALCHEMY_DATABASE_URI}")
    
    @classmethod
    def get_plan_features(cls, plan: str) -> dict:
        """Get features for a subscription plan"""
        return cls.PLAN_FEATURES.get(plan, cls.PLAN_FEATURES['free'])


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': Config
}


def get_config(env: Optional[str] = None) -> Config:
    """Get configuration based on environment"""
    if env is None:
        env = os.environ.get('FLASK_ENV', 'default')
    return config.get(env, Config)
