"""
Signal Forge - API Package
RESTful API endpoints organized by domain
"""

from flask import Blueprint

api_bp = Blueprint('api', __name__, url_prefix='/api')

from . import routes
