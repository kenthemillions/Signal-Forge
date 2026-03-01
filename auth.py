"""
Signal Forge - Authentication helpers
Login, session, and plan enforcement
"""

from functools import wraps
from flask import session, redirect, request, url_for, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

def hash_password(password: str) -> str:
    return generate_password_hash(password, method='pbkdf2:sha256')

def verify_password(user, password: str) -> bool:
    if not user or not user.password_hash:
        return False
    return check_password_hash(user.password_hash, password)

def get_current_user():
    from models import User
    user_id = session.get('user_id')
    if not user_id:
        return None
    return User.query.get(int(user_id))

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from auth import get_current_user
        if get_current_user() is None:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                return jsonify({'error': 'Login required'}), 401
            return redirect(url_for('login_page', next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from auth import get_current_user
        user = get_current_user()
        if user is None:
            return redirect(url_for('login_page', next=request.url))
        if not user.is_admin:
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def get_plan_max_watchlist(plan: str) -> int:
    from config import Config
    features = Config.PLAN_FEATURES.get(plan, Config.PLAN_FEATURES['free'])
    return features.get('max_watchlist', 5)
