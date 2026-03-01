"""
Signal Forge - API Routes
Organized API endpoints for the trading signals application
"""

from flask import jsonify, request, current_app
from . import api_bp
import logging

logger = logging.getLogger(__name__)
