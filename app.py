import eventlet
eventlet.monkey_patch()

import os
import time
import logging

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, make_response
from flask_socketio import SocketIO, emit
from datetime import datetime
import json

from models import db, Signal, UserSettings, SignalPerformance, Ticker, PaperTrade, PaperAccount, BetaFeedback, User, Watchlist, JournalEntry
from auth import (
    get_current_user, login_required, admin_required,
    hash_password, verify_password, get_plan_max_watchlist
)
from config import Config
from indicators import IndicatorEngine
from strategies import StrategyOrchestrator
from data_fetcher import MarketDataFetcher
from options_analytics import options_analytics
from config import Config
from services.signal_service import signal_service
from services.scalping_levels import get_scalping_levels
from signal_engine.institutional import institutional_engine
from signal_engine.seasonality import seasonality_analyzer
from signal_engine.smart_coach import analyze_trade, ask_deepseek

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


app = Flask(__name__)
Config.init_app(app)
logger.info(f"Database backend: {app.config.get('SQLALCHEMY_DATABASE_URI', 'not set')[:30]}...")


db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')


data_fetcher = MarketDataFetcher()
indicator_engine = IndicatorEngine()
strategy_orchestrator = StrategyOrchestrator()

_cheap_options_cache = {'data': None, 'timestamp': None}
_db_ready = False
_DEFAULT_TICKERS = [{'symbol': s} for s in ['SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'SLV', 'GLD']]


def _normalized_quote(symbol: str):
    """
    Single adapter: Yahoo (data_fetcher) -> one stable format for frontend.
    Returns dict with keys: symbol, price, change, percentChange OR error.
    Never raises; never returns None.
    """
    symbol = (symbol or '').strip().upper()
    if not symbol:
        return {'error': 'Missing symbol', 'symbol': ''}
    try:
        logger.info('market_data request symbol=%s upstream=yfinance get_stock_data', symbol)
        data = data_fetcher.get_stock_data(symbol, period='1d', interval='1m')
        if not data:
            logger.warning('market_data symbol=%s upstream returned None', symbol)
            return {'error': 'No data', 'symbol': symbol}
        if data.get('error'):
            logger.warning('market_data symbol=%s upstream error=%s', symbol, data.get('error'))
            return {'error': data.get('error', 'Unknown'), 'symbol': symbol}
        price = data.get('current_price')
        if price is None or (isinstance(price, (int, float)) and price <= 0):
            logger.warning('market_data symbol=%s no valid current_price', symbol)
            return {'error': 'No price', 'symbol': symbol}
        prev = data.get('previous_close') or 0
        ch = data.get('change', 0)
        pct = data.get('change_percent', 0)
        out = {
            'symbol': symbol,
            'price': round(float(price), 2),
            'change': round(float(ch), 2),
            'percentChange': round(float(pct), 2),
            'quote_debug': {
                'symbol': symbol,
                'price_source': data.get('price_source', '--'),
                'previous_close': round(float(prev), 2),
                'computed_change': round(float(price) - float(prev), 2),
                'computed_percentChange': round((float(price) - float(prev)) / float(prev) * 100, 2) if prev else 0,
                'session': data.get('session', '--'),
            }
        }
        logger.info('market_data symbol=%s status=ok price=%s', symbol, out['price'])
        return out
    except Exception as e:
        logger.exception('market_data symbol=%s exception=%s', symbol, e)
        return {'error': str(e), 'symbol': symbol}


def _init_db():
    global _db_ready
    try:
        with app.app_context():
            db.create_all()
            if Ticker.query.count() == 0:
                for symbol in ['SPY', 'SLV', 'GLD', 'AAPL', 'QQQ', 'TSLA', 'NVDA']:
                    db.session.add(Ticker(symbol=symbol, is_active=True))
                db.session.commit()
            if UserSettings.query.first() is None:
                db.session.add(UserSettings(
                    rsi_oversold=30, rsi_overbought=70, macd_sensitivity=1.0,
                    volume_spike_threshold=2.0, bollinger_period=20, bollinger_std=2.0,
                    audio_enabled=True, notification_level='all'
                ))
                db.session.commit()
            if User.query.filter_by(role='admin').first() is None:
                db.session.add(User(
                    email='admin@signalforge.com', username=Config.MASTER_USERNAME,
                    password_hash=hash_password(Config.MASTER_PASSWORD),
                    role='admin', plan='elite', is_active=True
                ))
                db.session.commit()
            if User.query.filter_by(role='beta').first() is None:
                db.session.add(User(
                    email='beta@signalforge.com', username=Config.BETA_USERNAME,
                    password_hash=hash_password(Config.BETA_PASSWORD),
                    role='beta', plan='beta', is_active=True
                ))
                db.session.commit()
            _db_ready = True
            logger.info('Database initialized')
    except Exception as e:
        logger.warning('Database init failed (app will still run with defaults): %s', e)
        _db_ready = False


_init_db()
data_fetcher.clear_cache()
logger.info('Data fetcher cache cleared; using Yahoo Finance only.')

def background_price_updater():
    """Background task to push real-time price updates to connected clients."""
    while True:
        try:
            with app.app_context():
                tickers = Ticker.query.filter_by(is_active=True).all()
                for ticker in tickers:
                    try:
                        data = data_fetcher.get_stock_data(ticker.symbol, period='1d', interval='1m')
                        if data and 'error' not in data and 'current_price' in data:
                            socketio.emit('price_update', {
                                'symbol': ticker.symbol,
                                'price': data.get('current_price', 0),
                                'change': data.get('change', 0),
                                'change_percent': data.get('change_percent', 0),
                                'session': data.get('session', 'regular'),
                                'timestamp': datetime.now().isoformat()
                            })
                    except Exception as e:
                        logger.debug('Price update failed for %s: %s', ticker.symbol, e)
                    eventlet.sleep(0.5)
        except Exception as e:
            logger.debug('Background price updater: %s', e)
        eventlet.sleep(5)

def background_cheap_options_scanner():
    while True:
        try:
            from services.cheap_option_radar import cheap_option_radar as _radar
            result = _radar.scan(limit=10)
            _cheap_options_cache['data'] = result
            _cheap_options_cache['timestamp'] = datetime.now().isoformat()
            logger.info("Cheap options cache refreshed")
        except Exception as e:
            logger.debug('Background cheap options scanner: %s', e)
        eventlet.sleep(300)

@app.route('/health')
def health_check():
    """Simple health check endpoint for deployment"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/app')
@login_required
def dashboard():
    static_version = os.environ.get('RENDER_GIT_COMMIT', str(int(time.time())))
    resp = make_response(render_template('dashboard.html', current_user=get_current_user(), static_version=static_version))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp

@app.route('/login', methods=['GET'])
def login_page():
    if get_current_user():
        return redirect(url_for('dashboard'))
    next_url = request.args.get('next', url_for('dashboard'))
    return render_template('login.html', next=next_url)

@app.route('/login', methods=['POST'])
def login_post():
    username_or_email = (request.form.get('username') or request.form.get('email') or '').strip()
    password = request.form.get('password') or ''
    next_url = request.form.get('next') or request.args.get('next') or url_for('dashboard')
    if not username_or_email or not password:
        return render_template('login.html', error='Username/email and password required', next=next_url)
    user = User.query.filter(
        (User.username == username_or_email) | (User.email == username_or_email)
    ).first()
    if not user or not verify_password(user, password):
        return render_template('login.html', error='Invalid username or password', next=next_url)
    if not getattr(user, 'is_active', True):
        return render_template('login.html', error='Account is disabled', next=next_url)
    session['user_id'] = user.id
    return redirect(next_url)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('landing'))

@app.route('/signup', methods=['GET'])
def signup_page():
    if get_current_user():
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/signup', methods=['POST'])
def signup_post():
    email = (request.form.get('email') or '').strip().lower()
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    confirm = request.form.get('confirm_password') or ''
    if not email or not username or not password:
        return render_template('signup.html', error='Email, username, and password required')
    if password != confirm:
        return render_template('signup.html', error='Passwords do not match')
    if User.query.filter_by(email=email).first():
        return render_template('signup.html', error='Email already registered')
    if User.query.filter_by(username=username).first():
        return render_template('signup.html', error='Username already taken')
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role='user',
        plan=Config.DEFAULT_PLAN,
        is_active=True
    )
    db.session.add(user)
    db.session.commit()
    session['user_id'] = user.id
    return redirect(url_for('dashboard'))

@app.route('/account')
@login_required
def account_page():
    user = get_current_user()
    plan = getattr(user, 'plan', None) or Config.DEFAULT_PLAN
    features = Config.get_plan_features(plan)
    return render_template('account.html', user=user, plan_name=features.get('name', plan),
        plan_features=features,
        stripe_publishable=app.config.get('STRIPE_PUBLISHABLE_KEY', ''),
        stripe_price_pro=app.config.get('STRIPE_PRICE_PRO_ID', ''),
        stripe_price_elite=app.config.get('STRIPE_PRICE_ELITE_ID', ''))

@app.route('/terms')
def terms_page():
    return render_template('terms.html')

@app.route('/privacy')
def privacy_page():
    return render_template('privacy.html')

@app.route('/disclaimer')
def disclaimer_page():
    return render_template('disclaimer.html')

@app.route('/checkout/<plan>')
@login_required
def stripe_checkout(plan):
    if plan not in ('pro', 'elite'):
        return redirect(url_for('account_page'))
    price_id = app.config.get('STRIPE_PRICE_ELITE_ID') if plan == 'elite' else app.config.get('STRIPE_PRICE_PRO_ID')
    secret = app.config.get('STRIPE_SECRET_KEY')
    if not secret or not price_id:
        return redirect(url_for('account_page'))
    try:
        import stripe
        stripe.api_key = secret
        user = get_current_user()
        session_obj = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=request.host_url.rstrip('/') + url_for('account_page') + '?success=1',
            cancel_url=request.host_url.rstrip('/') + url_for('account_page'),
            customer_email=getattr(user, 'email', None),
            metadata={'user_id': str(user.id), 'plan': plan}
        )
        return redirect(session_obj.url)
    except Exception as e:
        logger.exception("Stripe checkout error: %s", e)
        return redirect(url_for('account_page'))

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature', '')
    secret = app.config.get('STRIPE_WEBHOOK_SECRET')
    if not secret:
        return jsonify({'error': 'Webhook not configured'}), 400
    try:
        import stripe
        stripe.api_key = app.config.get('STRIPE_SECRET_KEY')
        event = stripe.Webhook.construct_event(payload, sig, secret)
    except Exception as e:
        logger.warning("Stripe webhook signature error: %s", e)
        return jsonify({'error': 'Invalid signature'}), 400
    def _customer_email(sub):
        if sub.get('customer_email'):
            return sub['customer_email']
        cid = sub.get('customer')
        if not cid:
            return None
        try:
            return stripe.Customer.retrieve(cid).email
        except Exception:
            return None

    if event['type'] == 'customer.subscription.created' or event['type'] == 'customer.subscription.updated':
        sub = event['data']['object']
        items = sub.get('items', {}).get('data', [])
        price_obj = items[0].get('price', {}) if items else {}
        plan = sub.get('metadata', {}).get('plan') or price_obj.get('metadata', {}).get('plan')
        if not plan:
            price_id = price_obj.get('id')
            plan = 'elite' if price_id == app.config.get('STRIPE_PRICE_ELITE_ID') else 'pro'
        status = sub.get('status', '')
        if status in ('active', 'trialing'):
            customer_email = _customer_email(sub)
            if customer_email:
                user = User.query.filter_by(email=customer_email).first()
                if user:
                    user.plan = plan
                    db.session.commit()
    elif event['type'] == 'customer.subscription.deleted':
        sub = event['data']['object']
        customer_email = _customer_email(sub)
        if customer_email:
            user = User.query.filter_by(email=customer_email).first()
            if user:
                user.plan = Config.DEFAULT_PLAN
                db.session.commit()
    return jsonify({'received': True}), 200

@app.route('/onboarding')
def onboarding():
    return render_template('onboarding.html')

@app.route('/api/waitlist', methods=['POST'])
def join_waitlist():
    data = request.get_json()
    email = data.get('email', '').strip()
    if email:
        logger.info(f"Waitlist signup: {email}")
    return jsonify({'success': True})

@app.route('/api/onboarding/complete', methods=['POST'])
def complete_onboarding():
    data = request.get_json()
    logger.info(f"Onboarding completed with settings: {data}")
    return jsonify({'success': True})

def _aggregate_df_to_4h(df):
    """Aggregate OHLCV DataFrame (e.g. 1h bars) to 4h bars. Groups every 4 rows."""
    import pandas as pd
    if len(df) < 4:
        return df
    n = len(df) // 4
    rows = []
    for i in range(n):
        start = i * 4
        end = start + 4
        chunk = df.iloc[start:end]
        rows.append({
            'Open': chunk['Open'].iloc[0],
            'High': chunk['High'].max(),
            'Low': chunk['Low'].min(),
            'Close': chunk['Close'].iloc[-1],
            'Volume': chunk['Volume'].sum()
        })
    return pd.DataFrame(rows)


@app.route('/api/institutional/<symbol>')
def get_institutional_signal(symbol):
    """Get institutional mode analysis for a symbol. Uses same data source as dashboard (data_fetcher, Yahoo Finance)."""
    try:
        symbol = symbol.upper()
        timeframe = request.args.get('timeframe', '5m')
        session_rules = None
        
        session_str = request.args.get('session_rules')
        if session_str:
            try:
                session_rules = json.loads(session_str)
            except Exception:
                pass
        
        period_map = {
            '1m': '1d', '5m': '5d', '15m': '5d',
            '1h': '1mo', '4h': '3mo'
        }
        interval_map = {
            '1m': '1m', '5m': '5m', '15m': '15m',
            '1h': '1h', '4h': '1h'
        }
        period = period_map.get(timeframe, '5d')
        interval = interval_map.get(timeframe, '5m')
        
        market_data = data_fetcher.get_stock_data(symbol, period=period, interval=interval)
        if not market_data or market_data.get('error') or not market_data.get('closes'):
            return jsonify({
                'state': 'WAIT',
                'confidence': 0,
                'bias': 'NEUTRAL',
                'reasons': ['Unable to fetch data for this symbol'],
                'waiting_for': ['Data connection'],
                'regime': 'UNKNOWN',
                'location': 'UNKNOWN',
                'zone_status': 'UNKNOWN',
                'confirmations': {}
            })
        
        import pandas as pd
        timestamps = market_data.get('timestamps', [])
        opens = market_data.get('opens', [])
        highs = market_data.get('highs', [])
        lows = market_data.get('lows', [])
        closes = market_data.get('closes', [])
        volumes = market_data.get('volumes', [])
        if timestamps:
            try:
                index = pd.DatetimeIndex(pd.to_datetime(timestamps))
            except Exception:
                index = pd.RangeIndex(len(closes))
        else:
            index = pd.RangeIndex(len(closes))
        df = pd.DataFrame({
            'Open': opens, 'High': highs, 'Low': lows, 'Close': closes, 'Volume': volumes
        }, index=index)
        
        if timeframe == '4h' and len(closes) >= 4:
            df = _aggregate_df_to_4h(df)
        
        signal = institutional_engine.analyze(df, symbol, timeframe, session_rules)
        
        return jsonify({
            'state': signal.state,
            'confidence': signal.confidence,
            'bias': signal.bias,
            'reasons': signal.reasons,
            'waiting_for': signal.waiting_for,
            'regime': signal.regime,
            'location': signal.location,
            'zone_status': signal.zone_status,
            'confirmations': signal.confirmations,
            'entry_price': signal.entry_price,
            'stop_price': signal.stop_price,
            'target_price': signal.target_price,
            'risk_reward': signal.risk_reward,
            'symbol': symbol.upper(),
            'timeframe': timeframe,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Institutional analysis error for {symbol}: {e}")
        return jsonify({
            'state': 'WAIT',
            'confidence': 0,
            'error': str(e)
        }), 500

@app.route('/api/seasonality/<symbol>')
def get_seasonality(symbol):
    """Get seasonality analysis for a symbol - day high/low timing patterns"""
    try:
        result = seasonality_analyzer.analyze(symbol)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Seasonality analysis error for {symbol}: {e}")
        return jsonify({
            'symbol': symbol.upper(),
            'error': str(e),
            'days_analyzed': 0,
            'insights': ['Unable to analyze - try again later']
        }), 500

@app.route('/api/coach', methods=['POST'])
def ask_coach_endpoint():
    """Smart Coach - analyze trade questions using same data as dashboard (data_fetcher + indicator_engine). Optional DeepSeek AI."""
    try:
        data = request.get_json()
        question = data.get('question', '')
        symbol = (data.get('symbol') or 'SPY').strip().upper()
        use_ai = data.get('use_ai', False)
        api_key = (data.get('api_key') or '').strip()
        
        market_data = data_fetcher.get_stock_data(symbol, period='5d', interval='5m')
        if not market_data or market_data.get('error') or not market_data.get('closes'):
            return jsonify({
                'success': False,
                'response': "Couldn't get market data for that symbol. Try again.",
                'symbol': symbol,
                'mode': 'error'
            })
        
        import pandas as pd
        timestamps = market_data.get('timestamps', [])
        opens = market_data.get('opens', [])
        highs = market_data.get('highs', [])
        lows = market_data.get('lows', [])
        closes = market_data.get('closes', [])
        volumes = market_data.get('volumes', [])
        if not timestamps:
            index = pd.RangeIndex(len(closes))
        else:
            try:
                index = pd.DatetimeIndex(pd.to_datetime(timestamps))
            except Exception:
                index = pd.RangeIndex(len(closes))
        df = pd.DataFrame({
            'Open': opens, 'High': highs, 'Low': lows, 'Close': closes, 'Volume': volumes
        }, index=index)
        
        signal = institutional_engine.analyze(df, symbol, timeframe='5m')
        institutional_data = {
            'state': signal.state,
            'confidence': signal.confidence,
            'regime': signal.regime,
            'location': signal.location,
            'bias': signal.bias,
            'confirmations': signal.confirmations,
            'zones': getattr(signal, 'zones', {}),
            'reasons': signal.reasons
        }
        
        settings = UserSettings.query.first()
        indicators = indicator_engine.calculate_all(market_data, settings)
        if indicators.get('error'):
            return jsonify({
                'success': False,
                'response': "Couldn't compute indicators. Try again.",
                'symbol': symbol,
                'mode': 'error'
            })
        indicators['current_price'] = market_data.get('current_price') or (closes[-1] if closes else 0)
        
        mode = 'rules'
        response = None
        
        if use_ai and api_key:
            response = ask_deepseek(question, symbol, institutional_data, api_key, indicators)
            if response:
                mode = 'ai'
        
        if not response:
            try:
                seasonality_data = seasonality_analyzer.analyze(symbol)
            except Exception:
                seasonality_data = None
            response = analyze_trade(question, symbol, institutional_data, seasonality_data)
            mode = 'rules'
        
        return jsonify({
            'success': True,
            'response': response,
            'symbol': symbol,
            'mode': mode
        })
    except Exception as e:
        logger.error(f"Coach error: {e}")
        return jsonify({
            'success': False,
            'response': "Sorry, I couldn't analyze that right now. Try again.",
            'error': str(e),
            'mode': 'error'
        }), 500

@app.route('/api/coach/status')
def coach_status():
    return jsonify({'server_ai_available': bool(Config.DEEPSEEK_API_KEY)})


@app.route('/api/test-quote')
def test_quote():
    """Minimal quote for stack verification. Always 200 + JSON."""
    symbol = (request.args.get('symbol') or 'SPY').strip().upper()
    logger.info('route=test-quote symbol=%s upstream=_normalized_quote', symbol)
    try:
        out = _normalized_quote(symbol)
        logger.info('route=test-quote symbol=%s result=%s body=%s', symbol, 'error' if out.get('error') else 'ok', str(out)[:120])
        return jsonify(out), 200
    except Exception as e:
        logger.exception('route=test-quote symbol=%s exception=%s', symbol, e)
        return jsonify({'error': str(e), 'symbol': symbol}), 200


@app.route('/api/quote')
def api_quote():
    """Quote for ticker card. Same normalized format. Always 200 + JSON."""
    symbol = (request.args.get('symbol') or 'SPY').strip().upper()
    logger.info('route=quote symbol=%s upstream=_normalized_quote', symbol)
    try:
        out = _normalized_quote(symbol)
        logger.info('route=quote symbol=%s result=%s body=%s', symbol, 'error' if out.get('error') else 'ok', str(out)[:120])
        return jsonify(out), 200
    except Exception as e:
        logger.exception('route=quote symbol=%s exception=%s', symbol, e)
        return jsonify({'error': str(e), 'symbol': symbol}), 200


@app.route('/api/tickers')
def get_tickers():
    if not _db_ready:
        return jsonify(_DEFAULT_TICKERS)
    try:
        tickers = Ticker.query.filter_by(is_active=True).all()
        if not tickers:
            return jsonify(_DEFAULT_TICKERS)
        return jsonify([t.to_dict() for t in tickers])
    except Exception as e:
        logger.warning('Tickers fetch failed: %s', e)
        return jsonify(_DEFAULT_TICKERS)

@app.route('/api/tickers', methods=['POST'])
def add_ticker():
    data = request.get_json() or {}
    raw = (data.get('symbol') or data.get('ticker') or '').strip().upper()
    if not raw:
        return jsonify({'error': 'Symbol required', 'success': False}), 400
    
    symbols = [s.strip() for s in raw.replace(',', ' ').split() if s.strip() and len(s.strip()) <= 12]
    if not symbols:
        return jsonify({'error': 'Enter at least one symbol (e.g. AAPL or AAPL, MSFT)', 'success': False}), 400
    symbols = symbols[:20]  
    added = []
    errors = []
    for symbol in symbols:
        try:
            existing = Ticker.query.filter_by(symbol=symbol).first()
            if existing:
                existing.is_active = True
                db.session.commit()
                added.append(existing.to_dict())
            else:
                ticker = Ticker(symbol=symbol, is_active=True)
                db.session.add(ticker)
                db.session.commit()
                added.append(ticker.to_dict())
        except Exception as e:
            errors.append(f'{symbol}: {str(e)[:80]}')
    if not added and errors:
        return jsonify({'error': '; '.join(errors[:3]), 'success': False}), 400
    return jsonify({'added': added, 'errors': errors, 'success': True})

@app.route('/api/tickers/<symbol>', methods=['DELETE'])
def remove_ticker(symbol):
    ticker = Ticker.query.filter_by(symbol=symbol.upper()).first()
    if ticker:
        ticker.is_active = False
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/market-data/<symbol>')
def get_market_data(symbol):
    symbol = (symbol or '').strip().upper()
    period = request.args.get('period', '1d')
    interval = request.args.get('interval', '5m')
    logger.info('market_data symbol=%s period=%s interval=%s', symbol, period, interval)
    try:
        data = data_fetcher.get_stock_data(symbol, period=period, interval=interval)
        if not data:
            logger.warning('market_data symbol=%s returned None', symbol)
            return jsonify({'error': 'No data', 'closes': [], 'timestamps': [], 'opens': [], 'highs': [], 'lows': [], 'volumes': []}), 200
        if data.get('error'):
            logger.warning('market_data symbol=%s error=%s', symbol, data.get('error'))
            return jsonify({**data, 'closes': data.get('closes', []), 'timestamps': data.get('timestamps', []), 'opens': data.get('opens', []), 'highs': data.get('highs', []), 'lows': data.get('lows', []), 'volumes': data.get('volumes', [])}), 200
        logger.info('market_data symbol=%s status=ok bars=%s', symbol, len(data.get('closes', [])))
        return jsonify(data), 200
    except Exception as e:
        logger.exception('market_data symbol=%s exception=%s', symbol, e)
        return jsonify({'error': str(e), 'closes': [], 'timestamps': [], 'opens': [], 'highs': [], 'lows': [], 'volumes': []}), 200

@app.route('/api/chart-levels/<symbol>')
def get_chart_levels(symbol):
    """Return PDH, PDL, PMH, PML for chart overlays. Used by Chart Intelligence Layer."""
    symbol = (symbol or '').strip().upper()
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo('America/New_York')
    except ImportError:
        try:
            import pytz
            et_tz = pytz.timezone('America/New_York')
        except ImportError:
            et_tz = None
    result = {'pdh': None, 'pdl': None, 'pmh': None, 'pml': None}
    try:
        daily = data_fetcher.get_stock_data(symbol, period='5d', interval='1d')
        if daily and not daily.get('error') and daily.get('highs') and len(daily['highs']) >= 2:
            highs = daily['highs']
            lows = daily['lows']
            result['pdh'] = round(float(highs[-2]), 2)
            result['pdl'] = round(float(lows[-2]), 2)
        intra = data_fetcher.get_stock_data(symbol, period='1d', interval='5m')
        if intra and not intra.get('error') and et_tz and intra.get('timestamps') and intra.get('highs'):
            from datetime import datetime
            pm_highs, pm_lows = [], []
            for i, ts in enumerate(intra['timestamps']):
                try:
                    if isinstance(ts, (int, float)):
                        dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=et_tz)
                    else:
                        s = str(ts).strip().replace('Z', '+00:00')
                        dt = datetime.fromisoformat(s)
                        if dt.tzinfo is None:
                            dt = et_tz.localize(dt) if hasattr(et_tz, 'localize') else dt.replace(tzinfo=et_tz)
                        else:
                            dt = dt.astimezone(et_tz)
                except Exception:
                    continue
                if dt.hour < 9 or (dt.hour == 9 and dt.minute < 30):
                    pm_highs.append(float(intra['highs'][i]))
                    pm_lows.append(float(intra['lows'][i]))
            if pm_highs:
                result['pmh'] = round(max(pm_highs), 2)
            if pm_lows:
                result['pml'] = round(min(pm_lows), 2)
        return jsonify(result), 200
    except Exception as e:
        logger.exception('chart_levels symbol=%s exception=%s', symbol, e)
        return jsonify(result), 200

@app.route('/api/indicators/<symbol>')
def get_indicators(symbol):
    symbol = (symbol or '').strip().upper()
    period = request.args.get('period', '5d')
    interval = request.args.get('interval', '5m')
    logger.info('indicators symbol=%s period=%s interval=%s', symbol, period, interval)
    try:
        data = data_fetcher.get_stock_data(symbol, period=period, interval=interval)
        if not data or data.get('error'):
            logger.warning('indicators symbol=%s no data or error=%s', symbol, data.get('error') if data else 'None')
            return jsonify({'error': data.get('error', 'Failed to fetch data') if data else 'No data'}), 200
        settings = UserSettings.query.first()
        settings_dict = settings.to_dict() if settings else None
        indicators = indicator_engine.calculate_all(data, settings_dict)
        import numpy as np
        opens = np.array(data.get('opens', []))
        highs = np.array(data.get('highs', []))
        lows = np.array(data.get('lows', []))
        closes = np.array(data.get('closes', []))
        if len(closes) > 1:
            indicators['heiken_ashi'] = indicator_engine.calculate_heiken_ashi(opens, highs, lows, closes)
        logger.info('indicators symbol=%s status=ok', symbol)
        return jsonify(indicators), 200
    except Exception as e:
        logger.exception('indicators symbol=%s exception=%s', symbol, e)
        return jsonify({'error': str(e)}), 200

@app.route('/api/signals')
def get_signals():
    limit = request.args.get('limit', 50, type=int)
    signals = Signal.query.order_by(Signal.timestamp.desc()).limit(limit).all()
    return jsonify([s.to_dict() for s in signals])

@app.route('/api/signals/generate/<symbol>')
def generate_signal(symbol):
    settings = UserSettings.query.first()
    data = data_fetcher.get_stock_data(symbol, period='5d', interval='5m')
    
    if not data or 'error' in data:
        return jsonify({'error': 'Failed to fetch data'})
    
    indicators = indicator_engine.calculate_all(data, settings)
    signal = strategy_orchestrator.generate_signal(symbol, indicators, data, settings)
    
    db_signal = Signal(
        symbol=symbol,
        signal_type=signal['type'],
        strength=signal['strength'],
        price=signal['price'],
        indicators_summary=json.dumps(signal['indicators']),
        strategy=signal['strategy'],
        timestamp=datetime.utcnow()
    )
    db.session.add(db_signal)
    db.session.commit()
    
    socketio.emit('new_signal', db_signal.to_dict())
    
    return jsonify(signal)

@app.route('/api/settings')
def get_settings():
    settings = UserSettings.query.first()
    if not settings:
        settings = UserSettings()
        db.session.add(settings)
        db.session.commit()
    return jsonify(settings.to_dict())

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.get_json()
    settings = UserSettings.query.first()
    if not settings:
        settings = UserSettings()
        db.session.add(settings)
    
    for key, value in data.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
    
    db.session.commit()
    return jsonify(settings.to_dict())

@app.route('/api/performance')
def get_performance():
    performances = SignalPerformance.query.order_by(SignalPerformance.date.desc()).limit(30).all()
    return jsonify([p.to_dict() for p in performances])

@app.route('/api/performance/stats')
def get_performance_stats():
    signals = Signal.query.all()
    total = len(signals)
    wins = len([s for s in signals if s.outcome == 'WIN'])
    losses = len([s for s in signals if s.outcome == 'LOSS'])
    
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return jsonify({
        'total_signals': total,
        'winning_signals': wins,
        'losing_signals': losses,
        'pending_signals': total - wins - losses,
        'win_rate': round(win_rate, 1),
        'avg_gain': 0,
        'avg_loss': 0
    })

@app.route('/api/market-status')
def get_market_status():
    try:
        return jsonify(strategy_orchestrator.get_market_status())
    except Exception as e:
        logger.warning('Market status failed: %s', e)
        return jsonify({
            'current_session': 'UNKNOWN',
            'session_description': 'Status unavailable',
            'is_market_open': False,
            'countdowns': {'market_close': '--:--:--', 'lottery_hour': '--:--:--'}
        }), 200

@app.route('/api/quick-analysis/<symbol>')
def quick_analysis(symbol):
    """Quick analysis endpoint - instant directional assessment when ticker is entered"""
    data = data_fetcher.get_stock_data(symbol.upper(), period='1d', interval='5m')
    
    if not data or 'error' in data:
        return jsonify({'error': f'Could not fetch data for {symbol}'})
    
    settings = UserSettings.query.first()
    indicators = indicator_engine.calculate_all(data, settings)
    signal = strategy_orchestrator.generate_signal(symbol.upper(), indicators, data, settings)
    
    
    bullish_count = 0
    bearish_count = 0
    
    if indicators.get('rsi', {}).get('signal') in ['OVERSOLD', 'STRONG']:
        bullish_count += 1
    elif indicators.get('rsi', {}).get('signal') in ['OVERBOUGHT', 'WEAK']:
        bearish_count += 1
    
    if indicators.get('macd', {}).get('signal_type') in ['BULLISH', 'BULLISH_CROSS']:
        bullish_count += 1
    elif indicators.get('macd', {}).get('signal_type') in ['BEARISH', 'BEARISH_CROSS']:
        bearish_count += 1
    
    if indicators.get('vwap', {}).get('above_vwap'):
        bullish_count += 1
    else:
        bearish_count += 1
    
    if indicators.get('bollinger', {}).get('signal') == 'OVERSOLD':
        bullish_count += 1
    elif indicators.get('bollinger', {}).get('signal') == 'OVERBOUGHT':
        bearish_count += 1
    
    if indicators.get('support_resistance', {}).get('near_support'):
        bullish_count += 1
    if indicators.get('support_resistance', {}).get('near_resistance'):
        bearish_count += 1
    
    return jsonify({
        'symbol': symbol.upper(),
        'price': data.get('current_price', 0),
        'change': data.get('change', 0),
        'change_percent': data.get('change_percent', 0),
        'direction': signal.get('direction', 'NEUTRAL'),
        'entry_action': signal.get('entry_action', 'WAIT'),
        'entry_alert': signal.get('entry_alert', False),
        'signal_type': signal.get('type', 'NEUTRAL'),
        'strength': signal.get('strength', 50),
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
        'indicators': indicators,
        'reasons': signal.get('reasons', []),
        'vwap': indicators.get('vwap', {}),
        'market_status': strategy_orchestrator.get_market_status()
    })

@app.route('/api/options-flow/<symbol>')
def get_options_flow(symbol):
    """
    Get options flow analysis with unusual activity detection
    Updates every 60 seconds
    """
    symbol = symbol.upper()
    
    options_data = data_fetcher.get_options_flow(symbol)
    
    if 'error' in options_data:
        return jsonify(options_data)
    
    return jsonify(options_data)

@app.route('/api/vix')
def get_vix():
    """Get VIX data and volatility regime"""
    vix_data = data_fetcher.get_vix_data()
    return jsonify(vix_data)

@app.route('/api/earnings/<symbol>')
def get_earnings(symbol):
    """Get earnings calendar for a symbol"""
    earnings = data_fetcher.get_earnings_calendar(symbol.upper())
    return jsonify(earnings)

@app.route('/api/news/<symbol>')
def get_news(symbol):
    """Get recent news for a symbol"""
    limit = request.args.get('limit', 5, type=int)
    news = data_fetcher.get_news(symbol.upper(), limit)
    return jsonify({'symbol': symbol.upper(), 'news': news})


_trend_cache = {}
_trend_cache_max_age_sec = 120


def _detect_trend_reversal(symbol: str, data: dict, indicators: dict,
                            higher_tf_trend: str, trend_5m: str) -> dict:
    """
    Detect TRUE trend reversal in real time: multi-timeframe flip or structure break.
    Returns: { detected: bool, direction: str, reason: str, severity: str }
    """
    result = {'detected': False, 'direction': None, 'reason': '', 'severity': 'high'}
    if not data or 'closes' not in data or len(data['closes']) < 20:
        return result
    closes = data['closes']
    highs = data.get('highs', closes)
    lows = data.get('lows', closes)
    current_price = closes[-1]
    macd = indicators.get('macd', {})
    macd_signal = macd.get('signal_type', 'NEUTRAL')
    
    cur_5m = trend_5m if trend_5m in ('BULLISH', 'BEARISH') else 'NEUTRAL'
    cur_15m = higher_tf_trend if higher_tf_trend in ('BULLISH', 'BEARISH') else 'NEUTRAL'
    
    key = symbol.upper()
    prev = _trend_cache.get(key)
    _trend_cache[key] = {'5m': cur_5m, '15m': cur_15m, 'ts': datetime.utcnow()}
    if prev:
        p5, p15 = prev.get('5m'), prev.get('15m')
        if p5 == 'BULLISH' and p15 == 'BULLISH' and cur_5m == 'BEARISH' and cur_15m == 'BEARISH':
            result['detected'] = True
            result['direction'] = 'BULLISH_TO_BEARISH'
            result['reason'] = '5m and 15m both flipped to BEARISH — trend reversing down.'
            result['severity'] = 'high'
            return result
        if p5 == 'BEARISH' and p15 == 'BEARISH' and cur_5m == 'BULLISH' and cur_15m == 'BULLISH':
            result['detected'] = True
            result['direction'] = 'BEARISH_TO_BULLISH'
            result['reason'] = '5m and 15m both flipped to BULLISH — trend reversing up.'
            result['severity'] = 'high'
            return result
    
    lookback = 12
    if len(closes) < lookback + 2:
        return result
    swing_low = min(lows[-lookback:-2])
    swing_high = max(highs[-lookback:-2])
    
    if current_price < swing_low and cur_5m == 'BEARISH' and ('BEARISH' in macd_signal or macd.get('histogram', 0) < 0):
        result['detected'] = True
        result['direction'] = 'BULLISH_TO_BEARISH'
        result['reason'] = f'Structure break: price broke below swing low ${swing_low:.2f} with bearish momentum.'
        result['severity'] = 'high'
        return result
    
    if current_price > swing_high and cur_5m == 'BULLISH' and ('BULLISH' in macd_signal or macd.get('histogram', 0) > 0):
        result['detected'] = True
        result['direction'] = 'BEARISH_TO_BULLISH'
        result['reason'] = f'Structure break: price broke above swing high ${swing_high:.2f} with bullish momentum.'
        result['severity'] = 'high'
        return result
    return result


def get_central_time_info():
    """Get current time in Central Time (America/Chicago) and trading windows"""
    try:
        from zoneinfo import ZoneInfo
        ct = ZoneInfo('America/Chicago')
    except ImportError:
        try:
            import pytz
            ct = pytz.timezone('America/Chicago')
        except ImportError:
            ct = None
    
    if ct:
        now = datetime.now(ct)
    else:
        from datetime import timedelta
        now = datetime.utcnow() - timedelta(hours=6)  
    
    hour = now.hour
    minute = now.minute
    total_minutes = hour * 60 + minute
    
    
    
    before_945 = total_minutes < 585  
    prime_window = 585 <= total_minutes <= 870  
    late_session = total_minutes > 870  
    pre_market = total_minutes < 510  
    
    return {
        'time_ct': now.strftime('%H:%M CT'),
        'hour': hour,
        'minute': minute,
        'total_minutes': total_minutes,
        'before_945': before_945,
        'prime_window': prime_window,
        'late_session': late_session,
        'pre_market': pre_market
    }

def classify_signal_with_guardrails(raw_signal, confidence_pct, volume_ratio, rsi_val, macd_signal, 
                                     vwap_above, trend_direction, ct_info, is_premarket=False):
    """
    Classify signal with time-of-day guardrails and confidence requirements.
    Returns: (final_signal, signal_class, reason_text, education_text, entry_window, entry_type)
    """
    
    is_bullish = raw_signal in ['STRONG BUY', 'BUY']
    is_bearish = raw_signal in ['STRONG SELL', 'SELL']
    has_bias = is_bullish or is_bearish
    
    
    final_signal = raw_signal
    signal_class = 'wait'
    reason_text = ""
    education_text = "No edge — protect capital."
    entry_window = "Wait for setup"
    entry_type = "No clear entry"
    conviction_label = ""
    
    
    wait_for_text = ""
    if is_bullish and rsi_val >= 70 and macd_signal in ['BEARISH', 'BEARISH_CROSS'] and volume_ratio <= 1.0:
        final_signal = 'PREPARE'
        signal_class = 'prepare'
        reason_text = "Extended/overbought — wait for pullback to improve risk/reward."
        education_text = "Bias is forming — waiting improves entry price and stops."
        entry_type = "Wait for pullback / VWAP retest"
        wait_for_text = "Waiting for RSI to cool down and pullback to VWAP."
        return final_signal, signal_class, reason_text, education_text, entry_window, entry_type, conviction_label, wait_for_text
    
    if is_bearish and rsi_val <= 30 and macd_signal in ['BULLISH', 'BULLISH_CROSS'] and volume_ratio <= 1.0:
        final_signal = 'PREPARE'
        signal_class = 'prepare'
        reason_text = "Extended/oversold — wait for bounce to improve entry."
        education_text = "Bias is forming — waiting improves entry price and stops."
        entry_type = "Wait for bounce / VWAP reject"
        wait_for_text = "Waiting for bounce into VWAP to reject."
        return final_signal, signal_class, reason_text, education_text, entry_window, entry_type, conviction_label, wait_for_text
    
    
    
    
    
    if is_premarket or ct_info['pre_market']:
        entry_window = "Pre-market (confirm at open)"
    elif ct_info['before_945']:
        entry_window = "Early session (opening range)"
    elif ct_info['late_session']:
        entry_window = "Late session"
    else:
        entry_window = "Now (confirm on 5m)"
    
    
    if has_bias:
        
        if confidence_pct >= 90:
            conviction_label = "HIGH CONVICTION"
        
        
        if confidence_pct < 60:
            final_signal = 'PREPARE'
            signal_class = 'prepare'
            reason_text = f"Confidence {confidence_pct:.0f}% — need more confirmation."
            education_text = "Bias is forming — waiting improves entry price and stops."
        else:
            
            final_signal = raw_signal
            signal_class = 'strong-buy' if raw_signal == 'STRONG BUY' else \
                          'buy' if raw_signal == 'BUY' else \
                          'strong-sell' if raw_signal == 'STRONG SELL' else \
                          'sell' if raw_signal == 'SELL' else 'watch'
            education_text = "Confirmed — enter with defined stop."
    else:
        final_signal = raw_signal
        signal_class = 'watch' if raw_signal == 'WATCH' else 'wait'
    
    
    wait_for_text = ""
    if is_bullish:
        if rsi_val >= 70:
            entry_type = "Wait for pullback / VWAP retest"
            wait_for_text = "Waiting for pullback to VWAP or 9 EMA."
        elif vwap_above and volume_ratio < 1.2:
            entry_type = "Range break with volume"
            wait_for_text = "Waiting for volume expansion (>= 1.2x)."
        elif vwap_above and trend_direction == 'BULLISH':
            entry_type = "VWAP reclaim continuation"
        else:
            entry_type = "Range break with volume"
            if final_signal == 'PREPARE':
                wait_for_text = "Waiting for opening range break + hold."
    elif is_bearish:
        if rsi_val <= 30:
            entry_type = "Wait for bounce / VWAP reject"
            wait_for_text = "Waiting for bounce into VWAP to reject."
        elif not vwap_above and volume_ratio < 1.2:
            entry_type = "Range break with volume"
            wait_for_text = "Waiting for volume expansion (>= 1.2x)."
        elif not vwap_above and trend_direction == 'BEARISH':
            entry_type = "VWAP rejection continuation"
        else:
            entry_type = "Range break with volume"
            if final_signal == 'PREPARE':
                wait_for_text = "Waiting for opening range break + hold."
    
    
    if final_signal == 'PREPARE' and not wait_for_text:
        wait_for_text = "Waiting for opening range break + hold."
    
    return final_signal, signal_class, reason_text, education_text, entry_window, entry_type, conviction_label, wait_for_text

@app.route('/api/trade-recommendation/<symbol>')
def get_trade_recommendation(symbol):
    """Get actionable trade recommendation. Always 200 + JSON."""
    symbol = (symbol or '').strip().upper()
    logger.info('trade_recommendation symbol=%s', symbol)
    if not symbol:
        return jsonify({'error': 'Symbol required', 'current_price': None, 'main_signal': 'WAIT', 'has_signal': False}), 200
    try:
        cache_key = f"{symbol}_5d_5m"
        if cache_key in getattr(data_fetcher, '_cache', {}):
            data_fetcher._cache.pop(cache_key, None)
        if cache_key in getattr(data_fetcher, '_cache_expiry', {}):
            data_fetcher._cache_expiry.pop(cache_key, None)
        data = data_fetcher.get_stock_data(symbol, period='5d', interval='5m')
        if not data:
            logger.warning('trade_recommendation symbol=%s upstream returned None', symbol)
            return jsonify({'error': 'No data', 'current_price': None, 'main_signal': 'WAIT', 'has_signal': False}), 200
        if data.get('error'):
            logger.warning('trade_recommendation symbol=%s upstream error=%s', symbol, data.get('error'))
            return jsonify({'error': data.get('error', 'Failed to fetch data'), 'current_price': None, 'main_signal': 'WAIT', 'has_signal': False}), 200
        settings = UserSettings.query.first() if _db_ready else None
        indicators = indicator_engine.calculate_all(data, settings)
        signal = strategy_orchestrator.generate_signal(symbol, indicators, data, settings)
        market_status = strategy_orchestrator.get_market_status()
        ct_info = get_central_time_info()
        current_price = data.get('current_price', 0)
        direction = signal.get('direction', 'NEUTRAL')
        strength = signal.get('strength', 50)
        bullish_count = 0
        bearish_count = 0
        reasons = []
        evaluated_indicators = []

        rsi = indicators.get('rsi', {})
        rsi_val = rsi.get('value', 50)
        evaluated_indicators.append('RSI')
        if rsi_val < 30:
           bullish_count += 1
           reasons.append(f"RSI oversold at {rsi_val:.0f}")
        elif rsi_val > 70:
           bearish_count += 1
           reasons.append(f"RSI overbought at {rsi_val:.0f}")

        macd = indicators.get('macd', {})
        evaluated_indicators.append('MACD')
        if macd.get('signal_type') in ['BULLISH', 'BULLISH_CROSS']:
           bullish_count += 1
           reasons.append("MACD bullish crossover")
        elif macd.get('signal_type') in ['BEARISH', 'BEARISH_CROSS']:
           bearish_count += 1
           reasons.append("MACD bearish crossover")

        vwap = indicators.get('vwap', {})
        evaluated_indicators.append('VWAP')
        if vwap.get('above_vwap'):
           bullish_count += 1
           reasons.append("Price above VWAP")
        else:
           bearish_count += 1
           reasons.append("Price below VWAP")

        trend = indicators.get('trend', {})
        evaluated_indicators.append('Trend')
        if trend.get('direction') == 'BULLISH':
           bullish_count += 1
           reasons.append(f"Trend bullish ({trend.get('strength', 0)}%)")
        elif trend.get('direction') == 'BEARISH':
           bearish_count += 1
           reasons.append(f"Trend bearish ({trend.get('strength', 0)}%)")

        change_pct = data.get('change_percent', 0)
        evaluated_indicators.append('Momentum')
        if change_pct >= 0.5:
           bullish_count += 1
           reasons.append(f"STRONG price momentum UP (+{change_pct:.2f}%)")
        elif change_pct >= 0.2:
           bullish_count += 1
           reasons.append(f"Price momentum UP (+{change_pct:.2f}%)")
        elif change_pct <= -0.5:
           bearish_count += 1
           reasons.append(f"STRONG price momentum DOWN ({change_pct:.2f}%)")
        elif change_pct <= -0.2:
           bearish_count += 1
           reasons.append(f"Price momentum DOWN ({change_pct:.2f}%)")

        total_count = len(evaluated_indicators)
        bullish_count = min(bullish_count, total_count)
        bearish_count = min(bearish_count, total_count)

        vol = indicators.get('volume', {})
        vol_ratio = vol.get('spike_ratio', 1)
        if vol.get('spike'):
           reasons.append(f"Volume: {vol_ratio:.1f}x average (SPIKE)")
        elif vol_ratio >= 1.2:
           reasons.append(f"Volume: Above average ({vol_ratio:.1f}x)")
        else:
           reasons.append(f"Volume: Below average ({vol_ratio:.1f}x)")
    
        vol = indicators.get('volume', {})
        volume_above_avg = vol.get('spike_ratio', 1) >= 1.2
        volume_spike = vol.get('spike', False)
    
        total_indicators = bullish_count + bearish_count
    
    
        if bullish_count >= 4 and volume_spike:
           raw_signal = 'STRONG BUY'
        elif bullish_count >= 3 and bullish_count > bearish_count:
           raw_signal = 'BUY'
        elif bearish_count >= 4 and volume_spike:
           raw_signal = 'STRONG SELL'
        elif bearish_count >= 3 and bearish_count > bullish_count:
           raw_signal = 'SELL'
        elif bullish_count >= 2 or bearish_count >= 2:
           raw_signal = 'WATCH'
        else:
           raw_signal = 'WAIT'
    
    
        if raw_signal in ['BUY', 'SELL'] and vol_ratio < 1.0:
           raw_signal = 'PREPARE'
           reasons.append(f"Need volume confirmation (current {vol_ratio:.1f}x average).")
    
    
        higher_tf_trend = None  
        try:
           data_15m = data_fetcher.get_stock_data(symbol, period='5d', interval='15m')
           if data_15m and 'error' not in data_15m:
               indicators_15m = indicator_engine.calculate_all(data_15m, settings)
               higher_tf_trend = indicators_15m.get('trend', {}).get('direction', 'NEUTRAL')
               if raw_signal in ['STRONG BUY', 'BUY'] and higher_tf_trend == 'BEARISH':
                   raw_signal = 'PREPARE'
                   reasons.append("Higher timeframe (15m) still bearish — wait for trend alignment.")
               elif raw_signal in ['STRONG SELL', 'SELL'] and higher_tf_trend == 'BULLISH':
                   raw_signal = 'PREPARE'
                   reasons.append("Higher timeframe (15m) still bullish — wait for trend alignment.")
            
               if raw_signal == 'STRONG BUY' and higher_tf_trend != 'BULLISH':
                   raw_signal = 'BUY'
                   reasons.append("15m not yet bullish — STRONG CALL requires 5m & 15m alignment.")
               elif raw_signal == 'STRONG SELL' and higher_tf_trend != 'BEARISH':
                   raw_signal = 'SELL'
                   reasons.append("15m not yet bearish — STRONG PUT requires 5m & 15m alignment.")
        except Exception:
           pass
    
    
        confidence_pct = strength  
    
    
        main_signal, signal_class, guardrail_reason, education_text, entry_window, entry_type, conviction_label, wait_for_text = \
           classify_signal_with_guardrails(
               raw_signal=raw_signal,
               confidence_pct=confidence_pct,
               volume_ratio=vol_ratio,
               rsi_val=rsi_val,
               macd_signal=macd.get('signal_type', 'NEUTRAL'),
               vwap_above=vwap.get('above_vwap', False),
               trend_direction=trend.get('direction', 'NEUTRAL'),
               ct_info=ct_info,
               is_premarket=market_status.get('current_session') == 'PRE_MARKET'
           )
    
    
        summary = ""
        if main_signal == 'STRONG BUY':
           summary = f"{bullish_count} of {total_count} indicators bullish + volume surge! High conviction call setup."
        elif main_signal == 'BUY':
           summary = f"{bullish_count} of {total_count} indicators bullish. Good setup for calls."
        elif main_signal == 'STRONG SELL':
           summary = f"{bearish_count} of {total_count} indicators bearish + volume surge! High conviction put setup."
        elif main_signal == 'SELL':
           summary = f"{bearish_count} of {total_count} indicators bearish. Good setup for puts."
        elif main_signal == 'PREPARE':
           summary = guardrail_reason if guardrail_reason else f"Bias forming ({max(bullish_count, bearish_count)} of {total_count} aligned). Wait for confirmation."
        elif main_signal == 'WATCH':
           summary = f"Building setup ({max(bullish_count, bearish_count)} of {total_count} aligned). Watch for confirmation."
        else:
           summary = f"Mixed signals ({bullish_count} bullish, {bearish_count} bearish). Wait for confirmation."
    
    
        trend_reversal = _detect_trend_reversal(
           symbol, data, indicators,
           higher_tf_trend or 'NEUTRAL',
           trend.get('direction', 'NEUTRAL')
        )
    
    
        if main_signal in ['STRONG BUY', 'BUY']:
           edge_direction = 'CALL'
           edge_pct = round(confidence_pct)
        elif main_signal in ['STRONG SELL', 'SELL']:
           edge_direction = 'PUT'
           edge_pct = round(confidence_pct)
        else:
           edge_direction = 'FLAT'
           edge_pct = 50
    
        parts = []
        if higher_tf_trend and higher_tf_trend != 'NEUTRAL':
           parts.append(f"15m {higher_tf_trend.lower()}")
        parts.append("above VWAP" if vwap.get('above_vwap') else "below VWAP")
        parts.append(f"vol {vol_ratio:.1f}x")
        if edge_direction == 'FLAT':
           edge_one_liner = "No edge — wait for trend + volume alignment."
        else:
           edge_one_liner = f"5m & 15m agree, {', '.join(parts)}."
    
        sr = indicators.get('support_resistance', {})
        support = sr.get('support', current_price * 0.98)
        resistance = sr.get('resistance', current_price * 1.02)
    
        if support >= current_price:
           support = current_price * 0.985
        if resistance <= current_price:
           resistance = current_price * 1.015
    
        entry = current_price
    
    
        vwap_value = vwap.get('value', current_price)
    
    
        is_bullish_bias = raw_signal in ['STRONG BUY', 'BUY'] or bullish_count > bearish_count
    
        if main_signal in ['STRONG BUY', 'BUY'] or (main_signal == 'PREPARE' and is_bullish_bias):
           stop = max(support, entry * 0.985)
           if stop >= entry:
               stop = entry * 0.985
           risk = entry - stop
           target = entry + (risk * 2)
           if target < resistance:
               target = resistance
           option_type = "CALL"
           strike = round(current_price / 5) * 5
        
           hard_stop = max(min(vwap_value, support), entry * 0.97)
           stop_guidance = f"Below VWAP (${vwap_value:.2f}) or support (${support:.2f})"
        elif main_signal in ['STRONG SELL', 'SELL'] or (main_signal == 'PREPARE' and not is_bullish_bias):
           stop = min(resistance, entry * 1.015)
           if stop <= entry:
               stop = entry * 1.015
           risk = stop - entry
           target = entry - (risk * 2)
           if target > support:
               target = support
           option_type = "PUT"
           strike = round(current_price / 5) * 5
        
           hard_stop = min(max(vwap_value, resistance), entry * 1.03)
           stop_guidance = f"Above VWAP (${vwap_value:.2f}) or resistance (${resistance:.2f})"
        else:
           if bullish_count >= bearish_count:
               stop = max(support, entry * 0.985)
               if stop >= entry:
                   stop = entry * 0.985
               risk = entry - stop
               target = entry + (risk * 2)
               option_type = "CALL" if bullish_count > bearish_count else "-"
               hard_stop = max(min(vwap_value, support), entry * 0.97)
               stop_guidance = f"Below VWAP (${vwap_value:.2f}) or support (${support:.2f})"
           else:
               stop = min(resistance, entry * 1.015)
               if stop <= entry:
                   stop = entry * 1.015
               risk = stop - entry
               target = entry - (risk * 2)
               option_type = "PUT"
               hard_stop = min(max(vwap_value, resistance), entry * 1.03)
               stop_guidance = f"Above VWAP (${vwap_value:.2f}) or resistance (${resistance:.2f})"
           strike = round(current_price / 5) * 5
    
        from datetime import datetime, timedelta
        today = datetime.now()
        days_to_friday = (4 - today.weekday()) % 7
        if days_to_friday == 0:
           days_to_friday = 7
        next_friday = today + timedelta(days=days_to_friday)
        expiry = next_friday.strftime('%m/%d')
    
    
        confidence_tier = 'high' if confidence_pct >= 90 else ('normal' if confidence_pct >= 70 else 'muted')
        confidence_label = 'HIGH' if strength >= 75 else ('MODERATE' if strength >= 50 else 'LOW')
        position_contracts = max(1, min(5, int(10000 * 0.02 / (current_price * 0.05))))
        max_risk = position_contracts * current_price * 0.05
    
        return jsonify({
           'has_signal': main_signal not in ['WAIT', 'WATCH'],
           'main_signal': main_signal,
           'raw_signal': raw_signal,
           'signal_class': signal_class,
           'summary': summary,
           'evaluated_indicators': evaluated_indicators,
           'bullish_count': bullish_count,
           'bearish_count': bearish_count,
           'total_count': total_count,
           'confidence': confidence_label,
           'confidence_pct': round(confidence_pct, 1),
           'confidence_tier': confidence_tier,
           'conviction_label': conviction_label,
           'strength': strength,
           'bullish_count': bullish_count,
           'bearish_count': bearish_count,
           'reasons': reasons,
           'entry': round(entry, 2),
           'target': round(target, 2),
           'stop': round(stop, 2),
           'hard_stop': round(hard_stop, 2),
           'stop_guidance': stop_guidance,
           'max_loss_rule': "Exit if option premium drops 30%",
           'option_type': option_type,
           'strike': strike,
           'expiry': expiry,
           'position_contracts': position_contracts,
           'max_risk': round(max_risk, 2),
           'current_price': current_price,
           'change': data.get('change', 0),
           'change_percent': data.get('change_percent', 0),
           'education_text': education_text,
           'entry_window': entry_window,
           'entry_type': entry_type,
           'wait_for_text': wait_for_text if main_signal == 'PREPARE' else '',
           'time_ct': ct_info['time_ct'],
           'indicators': {
               'rsi': rsi,
               'macd': macd,
               'vwap': vwap,
               'trend': trend,
               'volume': vol,
               'bollinger': indicators.get('bollinger', {}),
               'support_resistance': sr,
               'ema': indicators.get('ema', {}),
           },
           'market_status': market_status,
           'higher_tf_trend': higher_tf_trend,
           'edge_direction': edge_direction,
           'edge_pct': edge_pct,
           'edge_one_liner': edge_one_liner,
           'trend_reversal_detected': trend_reversal.get('detected', False),
           'trend_reversal_direction': trend_reversal.get('direction'),
           'trend_reversal_reason': trend_reversal.get('reason', ''),
        'trend_reversal_severity': trend_reversal.get('severity', 'high'),
        'last_updated': datetime.now().isoformat()
    })
    except Exception as e:
        logger.exception('trade_recommendation symbol=%s exception=%s', symbol, e)
        return jsonify({'error': str(e), 'current_price': None, 'main_signal': 'WAIT', 'has_signal': False, 'summary': 'Click Refresh to retry.'}), 200

@app.route('/api/pivot-points/<symbol>')
def get_pivot_points(symbol):
    """Get pivot points and fibonacci levels"""
    pivot_data = data_fetcher.get_pivot_points(symbol.upper())
    return jsonify(pivot_data)


@app.route('/api/scalping-levels/<symbol>')
def get_scalping_levels_api(symbol):
    """
    Scalping levels: 1m, 2m, 5m, 15m, 1h, 4h.
    Per timeframe: Fibonacci retracement levels, ATR (how far it can go), VWAP with bands.
    Best retracement range auto for ticker (true range + ATR).
    """
    try:
        result = get_scalping_levels(data_fetcher, symbol.upper())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Scalping levels error for {symbol}: {e}")
        return jsonify({'symbol': symbol.upper(), 'error': str(e), 'timeframes': {}, 'best_retracement_range': {}}), 500

@app.route('/api/scan-top-10', methods=['POST'])
def scan_top_10():
    """Scan top 10 market movers and rank by trade score"""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    start_time = time.time()
    data = request.get_json() or {}
    
    filters = {
        'bullish_only': data.get('bullish_only', False),
        'bearish_only': data.get('bearish_only', False),
        'min_score': data.get('min_score', 0),
        'include_etfs': data.get('include_etfs', True)
    }
    
    custom_tickers = data.get('tickers', [])
    if custom_tickers and isinstance(custom_tickers, list) and len(custom_tickers) > 0:
        tickers = [t.upper() for t in custom_tickers]
    else:
        tickers = data_fetcher.get_top_movers()
    
    results = []
    errors = []
    
    def analyze_ticker(symbol):
        return data_fetcher.scan_stock(symbol, indicator_engine, strategy_orchestrator)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_symbol = {executor.submit(analyze_ticker, symbol): symbol for symbol in tickers}
        
        for future in as_completed(future_to_symbol, timeout=60):
            symbol = future_to_symbol[future]
            try:
                result = future.result(timeout=30)
                if result and 'error' not in result:
                    results.append(result)
                else:
                    errors.append({'symbol': symbol, 'error': result.get('error', 'Unknown error') if result else 'No result'})
            except Exception as e:
                errors.append({'symbol': symbol, 'error': str(e)})
    
    if filters['bullish_only']:
        results = [r for r in results if r['direction'] == 'BULLISH']
    elif filters['bearish_only']:
        results = [r for r in results if r['direction'] == 'BEARISH']
    
    if filters['min_score'] > 0:
        results = [r for r in results if r['trade_score'] >= filters['min_score']]
    
    results.sort(key=lambda x: x['trade_score'], reverse=True)
    
    for i, result in enumerate(results):
        if i == 0:
            result['rank'] = 1
            result['medal'] = '🥇'
        elif i == 1:
            result['rank'] = 2
            result['medal'] = '🥈'
        elif i == 2:
            result['rank'] = 3
            result['medal'] = '🥉'
        else:
            result['rank'] = i + 1
            result['medal'] = ''
        
        if result['trade_score'] >= 95:
            result['special'] = '🔥'
        elif result['confidence'] == 'AVOID':
            result['special'] = '⚠️'
        else:
            result['special'] = ''
    
    elapsed = round(time.time() - start_time, 1)
    
    bullish_count = sum(1 for r in results if r['direction'] == 'BULLISH')
    bearish_count = sum(1 for r in results if r['direction'] == 'BEARISH')
    high_confidence = sum(1 for r in results if r['confidence'] == 'HIGH')
    avoid_count = sum(1 for r in results if r['confidence'] == 'AVOID')
    
    top_opportunity = results[0] if results else None
    
    market_status = strategy_orchestrator.get_market_status()
    session = market_status.get('current_session', 'CLOSED')
    
    session_advice = {
        'MARKET_OPEN': 'Prioritize momentum breakouts, gap plays',
        'MID_DAY': 'Prioritize mean reversion, range trades',
        'AFTERNOON': 'Prioritize trend continuation setups',
        'END_OF_DAY': 'High conviction trades only',
        'LOTTERY_HOUR': 'Extreme momentum only, 95+ scores'
    }.get(session, 'Market closed - showing last available data')
    
    return jsonify({
        'results': results,
        'errors': errors,
        'summary': {
            'total_analyzed': len(tickers),
            'successful': len(results),
            'failed': len(errors),
            'elapsed_seconds': elapsed,
            'bullish_setups': bullish_count,
            'bearish_setups': bearish_count,
            'high_confidence': high_confidence,
            'avoid_count': avoid_count,
            'top_opportunity': {
                'symbol': top_opportunity['symbol'],
                'direction': top_opportunity['direction'],
                'score': top_opportunity['trade_score']
            } if top_opportunity else None
        },
        'session': session,
        'session_advice': session_advice,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/comprehensive-analysis/<symbol>')
def comprehensive_analysis(symbol):
    """
    Comprehensive multi-timeframe analysis with institutional flow detection
    Analyzes 1m, 5m, 15m with 1h/4h confirmation. Always returns 200 with error key on failure.
    """
    symbol = symbol.upper()
    safe_default = {
        'symbol': symbol,
        'price': 0,
        'change': 0,
        'change_percent': 0,
        'direction': 'NEUTRAL',
        'overall_signal': 'NEUTRAL',
        'entry_action': 'WAIT',
        'entry_alert': False,
        'strength': 50,
        'confluence_score': 0,
        'timeframe_trends': {},
        'timeframe_analysis': {},
        'short_term': {'bullish': 0, 'bearish': 0},
        'higher_timeframe': {'bullish': 0, 'bearish': 0},
        'institutional': {},
        'confluence_signals': [],
        'vwap_alignment': 0,
        'market_status': strategy_orchestrator.get_market_status(),
        'timestamp': None
    }
    try:
        mtf_data = data_fetcher.get_multi_timeframe_data(symbol)
        if not mtf_data.get('timeframes'):
            safe_default['error'] = f'Could not fetch multi-timeframe data for {symbol}'
            return jsonify(safe_default), 200

        institutional = data_fetcher.detect_institutional_activity(symbol)
        analysis = strategy_orchestrator.analyze_multi_timeframe(
            symbol, mtf_data, indicator_engine, institutional
        )

        tf_5m = mtf_data.get('timeframes', {}).get('5m', {})
        current_price = tf_5m.get('current_price', 0)
        change = tf_5m.get('change', 0)
        change_percent = tf_5m.get('change_percent', 0)

        return jsonify({
            'symbol': symbol,
            'price': current_price,
            'change': change,
            'change_percent': change_percent,
            'direction': analysis.get('direction', 'NEUTRAL'),
            'overall_signal': analysis.get('overall_signal', 'NEUTRAL'),
            'entry_action': analysis.get('entry_action', 'WAIT'),
            'entry_alert': analysis.get('entry_alert', False),
            'strength': analysis.get('strength', 50),
            'confluence_score': analysis.get('confluence_score', 0),
            'timeframe_trends': analysis.get('timeframe_trends', {}),
            'timeframe_analysis': analysis.get('timeframe_analysis', {}),
            'short_term': {
                'bullish': analysis.get('short_term_bullish', 0),
                'bearish': analysis.get('short_term_bearish', 0)
            },
            'higher_timeframe': {
                'bullish': analysis.get('higher_tf_bullish', 0),
                'bearish': analysis.get('higher_tf_bearish', 0)
            },
            'institutional': institutional,
            'confluence_signals': analysis.get('confluence_signals', []),
            'vwap_alignment': analysis.get('vwap_alignment', 0),
            'market_status': strategy_orchestrator.get_market_status(),
            'timestamp': analysis.get('timestamp')
        }), 200
    except Exception as e:
        logger.exception('comprehensive_analysis symbol=%s exception=%s', symbol, e)
        safe_default['error'] = str(e)
        return jsonify(safe_default), 200

@app.route('/api/risk-calculator', methods=['POST'])
def calculate_risk():
    data = request.get_json()
    account_size = data.get('account_size', 10000)
    risk_percent = data.get('risk_percent', 2)
    entry_price = data.get('entry_price', 0)
    stop_loss = data.get('stop_loss', 0)
    
    if entry_price <= 0 or stop_loss <= 0:
        return jsonify({'error': 'Invalid prices'})
    
    risk_amount = account_size * (risk_percent / 100)
    price_diff = abs(entry_price - stop_loss)
    shares = int(risk_amount / price_diff) if price_diff > 0 else 0
    position_value = shares * entry_price
    
    return jsonify({
        'shares': shares,
        'position_value': round(position_value, 2),
        'risk_amount': round(risk_amount, 2),
        'risk_per_share': round(price_diff, 2)
    })

@app.route('/api/paper-account')
def get_paper_account():
    """Get paper trading account status"""
    account = PaperAccount.query.first()
    if not account:
        account = PaperAccount(balance=10000, starting_balance=10000)
        db.session.add(account)
        db.session.commit()
    
    open_positions = PaperTrade.query.filter_by(status='OPEN').all()
    return jsonify({
        'account': account.to_dict(),
        'open_positions': [p.to_dict() for p in open_positions]
    })

@app.route('/api/paper-trade', methods=['POST'])
def execute_paper_trade():
    """Execute a paper trade"""
    data = request.get_json()
    symbol = data.get('symbol', 'SPY').upper()
    side = data.get('side', 'BUY')
    quantity = int(data.get('quantity', 1))
    
    stock_data = data_fetcher.get_stock_data(symbol, period='1d', interval='5m')
    if 'error' in stock_data:
        return jsonify({'error': 'Could not get current price'})
    
    current_price = stock_data.get('current_price', 0)
    
    account = PaperAccount.query.first()
    if not account:
        account = PaperAccount(balance=10000, starting_balance=10000)
        db.session.add(account)
        db.session.commit()
    
    position_cost = current_price * quantity
    
    if side == 'BUY' and position_cost > account.balance:
        return jsonify({'error': 'Insufficient balance'})
    
    trade = PaperTrade(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=current_price,
        status='OPEN',
        signal_type=data.get('signal_type', 'MANUAL')
    )
    db.session.add(trade)
    
    if side == 'BUY':
        account.balance -= position_cost
    else:
        account.balance += position_cost
    
    db.session.commit()
    
    return jsonify({
        'trade': trade.to_dict(),
        'account': account.to_dict()
    })

@app.route('/api/paper-trade/<int:trade_id>/close', methods=['POST'])
def close_paper_trade(trade_id):
    """Close a paper trade"""
    trade = PaperTrade.query.get(trade_id)
    if not trade or trade.status != 'OPEN':
        return jsonify({'error': 'Trade not found or already closed'})
    
    stock_data = data_fetcher.get_stock_data(trade.symbol, period='1d', interval='5m')
    current_price = stock_data.get('current_price', trade.entry_price)
    
    trade.exit_price = current_price
    trade.exit_time = datetime.utcnow()
    trade.status = 'CLOSED'
    
    if trade.side == 'BUY':
        trade.pnl = (current_price - trade.entry_price) * trade.quantity
    else:
        trade.pnl = (trade.entry_price - current_price) * trade.quantity
    
    account = PaperAccount.query.first()
    if account:
        if trade.side == 'BUY':
            account.balance += current_price * trade.quantity
        else:
            account.balance -= current_price * trade.quantity
        account.total_trades += 1
        account.total_pnl += trade.pnl
        if trade.pnl > 0:
            account.winning_trades += 1
        elif trade.pnl < 0:
            account.losing_trades += 1
    
    db.session.commit()
    
    return jsonify({
        'trade': trade.to_dict(),
        'account': account.to_dict()
    })

@app.route('/api/paper-trades')
def get_paper_trades():
    """Get paper trading history"""
    trades = PaperTrade.query.order_by(PaperTrade.entry_time.desc()).limit(50).all()
    return jsonify([t.to_dict() for t in trades])

@app.route('/api/edge-analysis/<symbol>')
def get_edge_analysis(symbol):
    """Get comprehensive edge analysis for a symbol"""
    try:
        market_data = data_fetcher.get_stock_data(symbol.upper(), period='5d', interval='5m')
        if not market_data or 'closes' not in market_data:
            return jsonify({'error': 'Unable to fetch market data'}), 400
        
        current_price = market_data['closes'][-1] if market_data['closes'] else 0
        prices = market_data['closes'][-100:] if len(market_data['closes']) > 100 else market_data['closes']
        
        iv = request.args.get('iv', 25.0, type=float)
        
        edge_summary = options_analytics.get_edge_summary(
            symbol=symbol.upper(),
            spot_price=current_price,
            prices=prices,
            iv=iv
        )
        
        return jsonify(edge_summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/volatility-regime/<symbol>')
def get_volatility_regime(symbol):
    """Get volatility regime analysis"""
    try:
        market_data = data_fetcher.get_stock_data(symbol.upper(), period='5d', interval='5m')
        if not market_data or 'closes' not in market_data:
            return jsonify({'error': 'Unable to fetch market data'}), 400
        
        prices = market_data['closes']
        volumes = market_data.get('volumes', [])
        
        regime = options_analytics.calculate_volatility_regime(prices, volumes)
        return jsonify(regime)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/greeks-calculator')
def calculate_greeks():
    """Calculate options Greeks"""
    try:
        spot = request.args.get('spot', 0, type=float)
        strike = request.args.get('strike', 0, type=float)
        days = request.args.get('days', 30, type=int)
        iv = request.args.get('iv', 25, type=float) / 100
        option_type = request.args.get('type', 'call')
        
        if spot <= 0 or strike <= 0:
            return jsonify({'error': 'Invalid spot or strike price'}), 400
        
        greeks = options_analytics.calculate_greeks(spot, strike, days, iv, option_type)
        return jsonify(greeks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/probability/<symbol>')
def get_probability(symbol):
    """Get probability of profit analysis"""
    try:
        strike = request.args.get('strike', 0, type=float)
        days = request.args.get('days', 30, type=int)
        option_type = request.args.get('type', 'call')
        
        market_data = data_fetcher.get_stock_data(symbol.upper(), period='5d', interval='5m')
        if not market_data or 'closes' not in market_data:
            return jsonify({'error': 'Unable to fetch market data'}), 400
        
        spot = market_data['closes'][-1]
        prices = market_data['closes']
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices)) if prices[i-1] > 0]
        volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5 * (252 ** 0.5) if returns else 0.25
        
        if strike <= 0:
            strike = spot
        
        prob = options_analytics.calculate_probability_of_profit(spot, strike, days, volatility, option_type)
        return jsonify(prob)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/landing')
def landing_page():
    """Serve the landing page"""
    return render_template('landing.html')

@app.route('/api/multi-timeframe/<symbol>')
def get_multi_timeframe_analysis(symbol):
    """Get multi-timeframe analysis across 1m, 5m, 15m, 1h, 4h"""
    symbol = symbol.upper()
    timeframes = {
        '1m': {'period': '1d', 'interval': '1m'},
        '2m': {'period': '1d', 'interval': '2m'},
        '5m': {'period': '5d', 'interval': '5m'},
        '15m': {'period': '5d', 'interval': '15m'},
        '1h': {'period': '1mo', 'interval': '1h'},
        '4h': {'period': '60d', 'interval': '1h', 'aggregate': 4}
    }
    
    settings = UserSettings.query.first()
    results = {}
    
    for tf_name, tf_config in timeframes.items():
        try:
            data = data_fetcher.get_stock_data(symbol, period=tf_config['period'], interval=tf_config['interval'])
            
            if tf_config.get('aggregate') and data and 'closes' in data:
                agg = tf_config['aggregate']
                closes = data['closes']
                if len(closes) >= agg:
                    data['closes'] = [sum(closes[i:i+agg])/agg for i in range(0, len(closes)-agg+1, agg)]
                    if 'highs' in data:
                        data['highs'] = [max(data['highs'][i:i+agg]) for i in range(0, len(data['highs'])-agg+1, agg)]
                    if 'lows' in data:
                        data['lows'] = [min(data['lows'][i:i+agg]) for i in range(0, len(data['lows'])-agg+1, agg)]
                    if 'volumes' in data:
                        data['volumes'] = [sum(data['volumes'][i:i+agg]) for i in range(0, len(data['volumes'])-agg+1, agg)]
                    data['current_price'] = data['closes'][-1] if data['closes'] else 0
            
            if data and 'closes' in data and len(data['closes']) > 0:
                indicators = indicator_engine.calculate_all(data, settings)
                
                trend = indicators.get('trend', {}).get('direction', 'NEUTRAL')
                momentum = indicators.get('momentum', {}).get('signal', 'NEUTRAL')
                rsi = indicators.get('rsi', {})
                macd = indicators.get('macd', {})
                vwap = indicators.get('vwap', {})
                ema = indicators.get('ema', {})
                
                if trend == 'BULLISH':
                    signal = 'BUY'
                    color = '#22C55E'
                elif trend == 'BEARISH':
                    signal = 'SELL'
                    color = '#EF4444'
                else:
                    signal = 'WAIT'
                    color = '#F59E0B'
                
                results[tf_name] = {
                    'trend': trend,
                    'signal': signal,
                    'color': color,
                    'momentum': momentum,
                    'rsi': round(rsi.get('value', 50), 1),
                    'rsi_signal': rsi.get('signal', 'NEUTRAL'),
                    'macd_signal': macd.get('signal_type', 'NEUTRAL'),
                    'above_vwap': vwap.get('above_vwap', False),
                    'price_vs_ema13': ema.get('price_vs_ema_13', 'NEUTRAL'),
                    'price_vs_ema48': ema.get('price_vs_ema_48', 'NEUTRAL'),
                    'current_price': round(data.get('current_price', 0), 2)
                }
            else:
                results[tf_name] = {'signal': 'N/A', 'color': '#888', 'trend': 'UNKNOWN'}
        except Exception as e:
            results[tf_name] = {'signal': 'ERROR', 'color': '#888', 'trend': 'UNKNOWN', 'error': str(e)}
    
    bullish_count = sum(1 for tf in results.values() if tf.get('trend') == 'BULLISH')
    bearish_count = sum(1 for tf in results.values() if tf.get('trend') == 'BEARISH')
    total = len([tf for tf in results.values() if tf.get('trend') in ['BULLISH', 'BEARISH', 'NEUTRAL']])
    
    if bullish_count >= 3:
        confluence = 'STRONG_BULLISH'
        confluence_signal = 'STRONG BUY'
        confluence_color = '#22C55E'
    elif bullish_count >= 2:
        confluence = 'BULLISH'
        confluence_signal = 'BUY'
        confluence_color = '#4ADE80'
    elif bearish_count >= 3:
        confluence = 'STRONG_BEARISH'
        confluence_signal = 'STRONG SELL'
        confluence_color = '#EF4444'
    elif bearish_count >= 2:
        confluence = 'BEARISH'
        confluence_signal = 'SELL'
        confluence_color = '#F87171'
    else:
        confluence = 'MIXED'
        confluence_signal = 'WAIT'
        confluence_color = '#F59E0B'
    
    return jsonify({
        'symbol': symbol,
        'timeframes': results,
        'confluence': {
            'status': confluence,
            'signal': confluence_signal,
            'color': confluence_color,
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'total': total
        },
        'timestamp': datetime.now().isoformat(),
        'refresh_id': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/api/premarket-analysis/<symbol>')
def get_premarket_analysis(symbol):
    """Get premarket/afterhours trend analysis using data_fetcher for correct prices."""
    try:
        symbol = symbol.upper()
        data = data_fetcher.get_stock_data(symbol, period='1d', interval='5m')
        if not data or data.get('error'):
            return jsonify({'error': data.get('error', 'No data'), 'trend': 'UNKNOWN'})
        current = data.get('current_price') or (data.get('closes', []) and data['closes'][-1]) or 0
        previous_close = data.get('previous_close') or 0
        change = data.get('change', 0)
        change_pct = data.get('change_percent', 0)
        session_key = (data.get('session') or 'regular').lower()
        if session_key == 'premarket':
            session = 'PREMARKET'
        elif session_key == 'afterhours':
            session = 'AFTER HOURS'
        else:
            session = 'MARKET'
        if change_pct >= 1.5:
            trend = 'STRONG BULLISH'
            direction = 'UP'
            color = '#22C55E'
            outlook = 'Strong gap up expected at open'
        elif change_pct >= 0.5:
            trend = 'BULLISH'
            direction = 'UP'
            color = '#4ADE80'
            outlook = 'Positive momentum building'
        elif change_pct >= 0.1:
            trend = 'SLIGHTLY BULLISH'
            direction = 'UP'
            color = '#86EFAC'
            outlook = 'Mild upward bias'
        elif change_pct <= -1.5:
            trend = 'STRONG BEARISH'
            direction = 'DOWN'
            color = '#EF4444'
            outlook = 'Strong gap down expected at open'
        elif change_pct <= -0.5:
            trend = 'BEARISH'
            direction = 'DOWN'
            color = '#F87171'
            outlook = 'Negative pressure building'
        elif change_pct <= -0.1:
            trend = 'SLIGHTLY BEARISH'
            direction = 'DOWN'
            color = '#FCA5A5'
            outlook = 'Mild downward bias'
        else:
            trend = 'NEUTRAL'
            direction = 'FLAT'
            color = '#F59E0B'
            outlook = 'Expecting flat open near previous close'
        return jsonify({
            'symbol': symbol,
            'session': session,
            'current_price': round(float(current), 2),
            'previous_close': round(float(previous_close), 2),
            'change': round(float(change), 2),
            'change_percent': round(float(change_pct), 2),
            'trend': trend,
            'direction': direction,
            'color': color,
            'outlook': outlook,
            'timestamp': datetime.now().strftime('%I:%M:%S %p')
        })
    except Exception as e:
        return jsonify({'error': str(e), 'trend': 'UNKNOWN'})

@app.route('/api/beta-feedback', methods=['POST'])
def submit_beta_feedback():
    """Submit beta user feedback"""
    try:
        data = request.get_json()
        category = data.get('category', 'General')
        suggestion = data.get('suggestion', '')
        email = data.get('email', '')
        rating = data.get('rating', 0)
        
        if not suggestion:
            return jsonify({'success': False, 'error': 'Please enter your suggestion'}), 400
        
        feedback = BetaFeedback(
            category=category,
            suggestion=suggestion,
            email=email,
            rating=rating
        )
        db.session.add(feedback)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Thank you for your feedback! We appreciate beta testers like you.',
            'feedback_id': feedback.id
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/beta-feedback', methods=['GET'])
def get_beta_feedback():
    """Get all beta feedback (admin view)"""
    feedback = BetaFeedback.query.order_by(BetaFeedback.created_at.desc()).all()
    return jsonify([f.to_dict() for f in feedback])

@app.route('/admin/feedback')
def admin_feedback_view():
    """Admin page to view all beta feedback"""
    feedback = BetaFeedback.query.order_by(BetaFeedback.created_at.desc()).all()
    
    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Beta Feedback - Admin</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>body { background: #1a1a2e; color: #eee; }</style>
    </head>
    <body>
        <div class="container py-4">
            <h1 class="mb-4"><i class="bi bi-chat-heart-fill text-info"></i> Beta Feedback Dashboard</h1>
            <div class="alert alert-info">
                <strong>Feedback notifications go to:</strong> pkjohnson71@gmail.com<br>
                <a href="/api/beta-feedback" class="btn btn-sm btn-outline-light mt-2">Export as JSON</a>
            </div>
            <div class="table-responsive">
                <table class="table table-dark table-striped">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Category</th>
                            <th>Suggestion</th>
                            <th>Email</th>
                            <th>Rating</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
    '''
    
    for f in feedback:
        rating_stars = '★' * (f.rating or 0) + '☆' * (5 - (f.rating or 0))
        html += f'''
                        <tr>
                            <td>{f.id}</td>
                            <td><span class="badge bg-info">{f.category}</span></td>
                            <td style="max-width: 400px;">{f.suggestion}</td>
                            <td>{f.email or 'N/A'}</td>
                            <td class="text-warning">{rating_stars}</td>
                            <td>{f.created_at.strftime('%Y-%m-%d %H:%M') if f.created_at else 'N/A'}</td>
                        </tr>
        '''
    
    html += '''
                    </tbody>
                </table>
            </div>
            <a href="/" class="btn btn-primary">Back to Dashboard</a>
        </div>
    </body>
    </html>
    '''
    
    return html

@app.route('/api/lottery-scan')
def lottery_play_scan():
    """
    3:54 PM Daily Lottery Play Scanner (also strong 3 PM - 4:15 PM).
    Finds options with highest probability for big end-of-day moves.
    When in last-hour window (3-4:15 PM), weights last 75 min momentum for accuracy.
    """
    try:
        tickers = Ticker.query.filter_by(is_active=True).all()
        if not tickers:
            return jsonify({
                'success': True,
                'in_last_hour_window': _is_last_hour_window_et(),
                'scan_time': datetime.now().strftime('%I:%M:%S %p'),
                'lottery_picks': [],
                'total_scanned': 0,
                'qualifying': 0,
                'message': 'Add tickers to your watchlist to run the lottery scan.',
                'disclaimer': {
                    'warning': 'OPTIONS ARE RISKY - TRADE AT YOUR OWN DISCRETION',
                    'purpose': 'These alerts are for EDUCATIONAL PURPOSES ONLY',
                    'advice': 'Never risk more than you can afford to lose. Past performance does not guarantee future results.'
                }
            })
        settings = UserSettings.query.first()
        in_last_hour = _is_last_hour_window_et()
        lottery_candidates = []
        
        for ticker in tickers:
            try:
                symbol = ticker.symbol
                data = data_fetcher.get_stock_data(symbol, period='5d', interval='5m')
                
                if not data or 'closes' not in data or len(data['closes']) < 20:
                    continue
                if data.get('error'):
                    continue
                
                current_price = data.get('current_price') or data['closes'][-1]
                current_price = float(current_price)
                volumes = data.get('volumes', [])
                
                indicators = indicator_engine.calculate_all(data, settings)
                
                rsi = indicators.get('rsi', {}).get('value', 50)
                macd = indicators.get('macd', {})
                macd_hist = macd.get('histogram', 0)
                bb = indicators.get('bollinger', {})
                bb_percent = bb.get('percent_b', 0.5)
                
                recent_volumes = volumes[-20:] if len(volumes) >= 20 else volumes
                avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1
                current_volume = volumes[-1] if volumes else 0
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                high_5d = max(data['highs'][-100:]) if 'highs' in data and data['highs'] else current_price
                low_5d = min(data['lows'][-100:]) if 'lows' in data and data['lows'] else current_price
                range_5d = high_5d - low_5d
                range_percent = (range_5d / current_price * 100) if current_price > 0 else 0
                
                momentum_score = 0
                direction = 'NEUTRAL'
                bullish_signals = 0
                bearish_signals = 0
                
                price_change = data.get('change_percent', 0)
                if in_last_hour and len(data.get('closes', [])) >= 15:
                    closes_75m = data['closes'][-15:]
                    open_75m = closes_75m[0]
                    close_now = closes_75m[-1]
                    last_hour_pct = (close_now - open_75m) / open_75m * 100 if open_75m else price_change
                    price_change = last_hour_pct
                if abs(price_change) >= 2.0:
                    momentum_score += 30
                elif abs(price_change) >= 1.0:
                    momentum_score += 20
                elif abs(price_change) >= 0.5:
                    momentum_score += 10
                
                if price_change > 0.3:
                    bullish_signals += 1
                elif price_change < -0.3:
                    bearish_signals += 1
                
                if rsi < 30:
                    momentum_score += 25
                    bullish_signals += 2
                elif rsi > 70:
                    momentum_score += 25
                    bearish_signals += 2
                elif rsi < 40:
                    momentum_score += 15
                    bullish_signals += 1
                elif rsi > 60:
                    momentum_score += 15
                    bearish_signals += 1
                
                if macd_hist > 0:
                    momentum_score += 20
                    bullish_signals += 1
                elif macd_hist < 0:
                    momentum_score += 20
                    bearish_signals += 1
                
                if bb_percent > 0.8:
                    momentum_score += 15
                    bearish_signals += 1
                elif bb_percent < 0.2:
                    momentum_score += 15
                    bullish_signals += 1
                
                if volume_ratio > 2.5:
                    momentum_score += 30
                elif volume_ratio > 2.0:
                    momentum_score += 25
                elif volume_ratio > 1.5:
                    momentum_score += 15
                elif volume_ratio > 1.2:
                    momentum_score += 10
                
                if range_percent > 3:
                    momentum_score += 15
                elif range_percent > 2:
                    momentum_score += 10
                
                if bullish_signals > bearish_signals:
                    direction = 'BULLISH'
                elif bearish_signals > bullish_signals:
                    direction = 'BEARISH'
                else:
                    direction = 'BULLISH' if price_change >= 0 else 'BEARISH'
                
                if momentum_score >= 25:
                    option_type = 'CALL' if direction == 'BULLISH' else 'PUT'
                    
                    if option_type == 'CALL':
                        strike = round(current_price * 1.01, 0)
                        target_move = '+2-5%'
                    else:
                        strike = round(current_price * 0.99, 0)
                        target_move = '-2-5%'
                    
                    reason_parts = []
                    if abs(price_change) >= 1.0:
                        reason_parts.append(f"{'Strong rally' if price_change > 0 else 'Sharp drop'} ({price_change:+.1f}%)")
                    if volume_ratio >= 2.0:
                        reason_parts.append(f"Volume surge ({volume_ratio:.1f}x)")
                    elif volume_ratio >= 1.5:
                        reason_parts.append(f"High volume ({volume_ratio:.1f}x)")
                    if rsi < 35:
                        reason_parts.append(f"Oversold RSI ({rsi:.0f})")
                    elif rsi > 65:
                        reason_parts.append(f"Overbought RSI ({rsi:.0f})")
                    if not reason_parts:
                        reason_parts.append(f"Momentum building ({direction.lower()})")
                    
                    lottery_candidates.append({
                        'symbol': symbol,
                        'current_price': round(current_price, 2),
                        'option_type': option_type,
                        'suggested_strike': strike,
                        'expiry': '0DTE or Weekly',
                        'momentum_score': momentum_score,
                        'volume_ratio': round(volume_ratio, 2),
                        'rsi': round(rsi, 1),
                        'price_change': round(price_change, 2),
                        'target_move': target_move,
                        'reason': ' + '.join(reason_parts),
                        'direction': direction
                    })
                    
            except Exception as e:
                continue
        
        lottery_candidates.sort(key=lambda x: x['momentum_score'], reverse=True)
        top_3 = lottery_candidates[:3]
        
        return jsonify({
            'success': True,
            'in_last_hour_window': in_last_hour,
            'scan_time': datetime.now().strftime('%I:%M:%S %p'),
            'lottery_picks': top_3,
            'total_scanned': len(tickers),
            'qualifying': len(lottery_candidates),
            'disclaimer': {
                'warning': 'OPTIONS ARE RISKY - TRADE AT YOUR OWN DISCRETION',
                'purpose': 'These alerts are for EDUCATIONAL PURPOSES ONLY',
                'advice': 'Never risk more than you can afford to lose. Past performance does not guarantee future results.'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'lottery_picks': [],
            'disclaimer': {
                'warning': 'OPTIONS ARE RISKY - TRADE AT YOUR OWN DISCRETION',
                'purpose': 'These alerts are for EDUCATIONAL PURPOSES ONLY',
                'advice': 'Never risk more than you can afford to lose.'
            }
        })


def _is_last_hour_window_et():
    """True if current time is 3:00 PM - 4:15 PM ET (last trading hour / lottery window)."""
    try:
        from datetime import time
        try:
            from zoneinfo import ZoneInfo
            et = ZoneInfo('America/New_York')
        except ImportError:
            import pytz
            et = pytz.timezone('America/New_York')
        now = datetime.now(et)
        t = now.time()
        return time(15, 0) <= t < time(16, 16)
    except Exception:
        return False


@app.route('/api/last-hour-scan')
def last_hour_strong_scan():
    """
    Last trading hour (3 PM - 4:15 PM ET) strongest plays.
    High-accuracy scan: uses only last 75 min of 1m data for direction + volume + momentum.
    Returns e.g. SLV strong PUT, GLD strong CALL for end-of-day / lottery advantage.
    """
    try:
        tickers = Ticker.query.filter_by(is_active=True).all()
        if not tickers:
            return jsonify({
                'success': True,
                'in_last_hour_window': _is_last_hour_window_et(),
                'strongest_plays': [],
                'scan_time': datetime.now().strftime('%I:%M %p ET'),
                'message': 'Add tickers to your watchlist to run the last-hour scan.',
            })
        settings = UserSettings.query.first()
        in_window = _is_last_hour_window_et()
        last_hour_minutes = 75
        candidates = []
        for ticker in tickers:
            try:
                symbol = ticker.symbol
                data = data_fetcher.get_stock_data(symbol, period='1d', interval='1m')
                if not data or 'closes' not in data or len(data['closes']) < 20:
                    continue
                if data.get('error'):
                    continue
                closes = data['closes']
                opens_arr = data.get('opens', closes)
                highs = data.get('highs', closes)
                lows = data.get('lows', closes)
                volumes = data.get('volumes', [1] * len(closes))
                n = min(last_hour_minutes, len(closes) - 1)
                if n < 10:
                    continue
                slice_closes = closes[-n:]
                slice_opens = (opens_arr[-n:] if opens_arr else slice_closes)
                slice_volumes = volumes[-n:] if len(volumes) >= n else [1] * n
                open_75 = slice_closes[0] if slice_closes else closes[-1]
                close_now = slice_closes[-1]
                display_price = data.get('current_price') or close_now
                last_hour_move_pct = (close_now - open_75) / open_75 * 100 if open_75 else 0
                avg_vol = sum(slice_volumes) / len(slice_volumes) if slice_volumes else 1
                recent_vol = slice_volumes[-1] if slice_volumes else 1
                vol_ratio = recent_vol / avg_vol if avg_vol else 1
                slice_data = {
                    'closes': slice_closes,
                    'opens': slice_opens,
                    'highs': highs[-n:] if len(highs) >= n else slice_closes,
                    'lows': lows[-n:] if len(lows) >= n else slice_closes,
                    'volumes': slice_volumes,
                    'current_price': close_now
                }
                indicators = indicator_engine.calculate_all(slice_data, settings)
                rsi = indicators.get('rsi', {}).get('value', 50)
                macd = indicators.get('macd', {})
                macd_hist = macd.get('histogram', 0)
                direction = 'NEUTRAL'
                if last_hour_move_pct >= 0.25:
                    direction = 'BULLISH'
                elif last_hour_move_pct <= -0.25:
                    direction = 'BEARISH'
                if direction == 'NEUTRAL':
                    continue
                momentum_aligned = (direction == 'BULLISH' and macd_hist > 0 and rsi < 70) or \
                                   (direction == 'BEARISH' and macd_hist < 0 and rsi > 30)
                strength_score = abs(last_hour_move_pct) * 4 + min(vol_ratio * 8, 25) + (30 if momentum_aligned else 10)
                strength_score = min(100, strength_score)
                play = 'CALL' if direction == 'BULLISH' else 'PUT'
                reason_parts = []
                reason_parts.append(f"Last hour {last_hour_move_pct:+.2f}%")
                if vol_ratio >= 1.3:
                    reason_parts.append(f"Vol {vol_ratio:.1f}x")
                if momentum_aligned:
                    reason_parts.append("Momentum aligned")
                if rsi < 35 and direction == 'BULLISH':
                    reason_parts.append(f"RSI {rsi:.0f}")
                elif rsi > 65 and direction == 'BEARISH':
                    reason_parts.append(f"RSI {rsi:.0f}")
                candidates.append({
                    'symbol': symbol,
                    'direction': direction,
                    'play': play,
                    'strength_score': round(strength_score, 1),
                    'last_hour_move_pct': round(last_hour_move_pct, 2),
                    'volume_ratio': round(vol_ratio, 2),
                    'rsi': round(rsi, 1),
                    'reason': ' · '.join(reason_parts),
                    'current_price': round(float(display_price), 2),
                    'label': f"{symbol} strong {play}",
                })
            except Exception:
                continue
        candidates.sort(key=lambda x: x['strength_score'], reverse=True)
        strongest = candidates[:8]
        return jsonify({
            'success': True,
            'in_last_hour_window': in_window,
            'strongest_plays': strongest,
            'scan_time': datetime.now().strftime('%I:%M %p ET'),
            'message': 'Last hour (3 PM - 4:15 PM) strongest plays' if in_window else 'Last 75 min momentum scan',
        })
    except Exception as e:
        logger.error(f"Last hour scan error: {e}")
        return jsonify({
            'success': False,
            'in_last_hour_window': False,
            'strongest_plays': [],
            'error': str(e),
        })


@app.route('/api/market-open-scan')
def market_open_scan():
    """
    Market Open Scanner - Finds top 3 trending stocks at open
    Scans at premarket, 5min, 15min, and 30min after open.
    Premarket phase: move is vs previous close. Other phases: move is from session open.
    """
    try:
        scan_phase = request.args.get('phase', '5min')
        tickers = Ticker.query.filter_by(is_active=True).all()
        if not tickers:
            return jsonify({
                'success': True,
                'scan_time': datetime.now().strftime('%I:%M:%S %p'),
                'scan_phase': scan_phase,
                'phase_label': {'premarket': 'Pre-Market', '5min': 'First 5 Minutes', '15min': 'First 15 Minutes', '30min': 'First 30 Minutes'}.get(scan_phase, scan_phase),
                'trending_picks': [],
                'total_scanned': 0,
                'qualifying': 0,
                'tip': 'Add tickers to your watchlist to run the market open scan.',
            })
        settings = UserSettings.query.first()
        trending_candidates = []
        
        for ticker in tickers:
            try:
                symbol = ticker.symbol
                data = data_fetcher.get_stock_data(symbol, period='1d', interval='1m')
                
                if not data or 'closes' not in data or len(data['closes']) < 10:
                    continue
                if data.get('error'):
                    continue
                
                closes = data['closes']
                opens_arr = data.get('opens', closes)
                volumes = data.get('volumes', [])
                
                current_price = data.get('current_price') or closes[-1]
                current_price = float(current_price)
                if scan_phase == 'premarket':
                    previous_close = data.get('previous_close') or (opens_arr[0] if opens_arr else current_price)
                    open_price = float(previous_close) if previous_close else current_price
                    price_change = current_price - open_price
                    price_change_pct = float(data.get('change_percent', (price_change / open_price * 100) if open_price else 0))
                else:
                    open_price = float(opens_arr[0]) if opens_arr else current_price
                    price_change = current_price - open_price
                    price_change_pct = (price_change / open_price * 100) if open_price > 0 else 0
                
                indicators = indicator_engine.calculate_all(data, settings)
                rsi = indicators.get('rsi', {}).get('value', 50)
                macd = indicators.get('macd', {})
                macd_hist = macd.get('histogram', 0)
                
                recent_volumes = volumes[-10:] if len(volumes) >= 10 else volumes
                avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1
                current_volume = volumes[-1] if volumes else 0
                total_volume = sum(volumes) if volumes else 0
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                trend_score = 0
                direction = 'NEUTRAL'
                bullish_signals = 0
                bearish_signals = 0
                consistency_score = 0
                
                if abs(price_change_pct) >= 1.5:
                    trend_score += 35
                elif abs(price_change_pct) >= 1.0:
                    trend_score += 25
                elif abs(price_change_pct) >= 0.5:
                    trend_score += 15
                
                if price_change_pct > 0.2:
                    bullish_signals += 2
                elif price_change_pct < -0.2:
                    bearish_signals += 2
                
                if volume_ratio >= 2.5:
                    trend_score += 30
                elif volume_ratio >= 2.0:
                    trend_score += 25
                elif volume_ratio >= 1.5:
                    trend_score += 15
                elif volume_ratio >= 1.2:
                    trend_score += 10
                
                if macd_hist > 0:
                    trend_score += 15
                    bullish_signals += 1
                elif macd_hist < 0:
                    trend_score += 15
                    bearish_signals += 1
                
                if rsi < 35:
                    bullish_signals += 1
                elif rsi > 65:
                    bearish_signals += 1
                
                if len(closes) >= 5:
                    up_bars = sum(1 for i in range(1, min(5, len(closes))) if closes[-i] > closes[-i-1])
                    down_bars = 5 - up_bars
                    if up_bars >= 4:
                        consistency_score = 20
                        bullish_signals += 1
                    elif down_bars >= 4:
                        consistency_score = 20
                        bearish_signals += 1
                    elif up_bars >= 3:
                        consistency_score = 10
                    elif down_bars >= 3:
                        consistency_score = 10
                
                trend_score += consistency_score
                
                if bullish_signals > bearish_signals:
                    direction = 'BULLISH'
                elif bearish_signals > bullish_signals:
                    direction = 'BEARISH'
                else:
                    direction = 'BULLISH' if price_change_pct >= 0 else 'BEARISH'
                
                if trend_score >= 25:
                    reason_parts = []
                    if abs(price_change_pct) >= 0.5:
                        reason_parts.append(f"{'Surging' if price_change_pct > 0 else 'Dropping'} {abs(price_change_pct):.1f}%")
                    if volume_ratio >= 2.0:
                        reason_parts.append(f"Heavy volume ({volume_ratio:.1f}x)")
                    elif volume_ratio >= 1.5:
                        reason_parts.append(f"Strong volume ({volume_ratio:.1f}x)")
                    if consistency_score >= 15:
                        reason_parts.append("Consistent trend")
                    if not reason_parts:
                        reason_parts.append(f"Building {direction.lower()} momentum")
                    
                    is_fakeout = False
                    fakeout_warning = ""
                    if volume_ratio < 1.3 and abs(price_change_pct) > 0.5:
                        is_fakeout = True
                        fakeout_warning = "Low volume - possible fakeout"
                        trend_score -= 10
                    if consistency_score < 10 and abs(price_change_pct) > 0.5:
                        is_fakeout = True
                        fakeout_warning = "Choppy action - wait for confirmation"
                    
                    trending_candidates.append({
                        'symbol': symbol,
                        'current_price': round(current_price, 2),
                        'open_price': round(open_price, 2),
                        'price_change': round(price_change, 2),
                        'price_change_pct': round(price_change_pct, 2),
                        'direction': direction,
                        'option_type': 'CALL' if direction == 'BULLISH' else 'PUT',
                        'trend_score': trend_score,
                        'volume_ratio': round(volume_ratio, 2),
                        'total_volume': total_volume,
                        'rsi': round(rsi, 1),
                        'consistency': consistency_score,
                        'reason': ' + '.join(reason_parts),
                        'is_fakeout': is_fakeout,
                        'fakeout_warning': fakeout_warning,
                        'scan_phase': scan_phase
                    })
                    
            except Exception as e:
                continue
        
        trending_candidates.sort(key=lambda x: x['trend_score'], reverse=True)
        top_3 = trending_candidates[:3]
        
        phase_labels = {
            'premarket': 'Pre-Market',
            '5min': 'First 5 Minutes',
            '15min': 'First 15 Minutes', 
            '30min': 'First 30 Minutes'
        }
        
        return jsonify({
            'success': True,
            'scan_time': datetime.now().strftime('%I:%M:%S %p'),
            'scan_phase': scan_phase,
            'phase_label': phase_labels.get(scan_phase, scan_phase),
            'trending_picks': top_3,
            'total_scanned': len(tickers),
            'qualifying': len(trending_candidates),
            'tip': 'Wait for confirmation in first 15-30 min to avoid fakeouts'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'trending_picks': []
        })



from services.time_edge_analyzer import time_edge_analyzer
from services.late_day_gatekeeper import late_day_gatekeeper
from services.trading_intelligence import get_full_trading_intelligence

@app.route('/api/trading-intelligence/<symbol>')
def get_trading_intelligence(symbol):
    """Step 5: Full trading intelligence (signals, momentum, R:R, scoring, market phase)."""
    symbol = (symbol or '').strip().upper()
    if not symbol:
        return jsonify({'error': 'Symbol required'}), 400
    try:
        data = data_fetcher.get_stock_data(symbol, period='5d', interval='5m')
        if not data or data.get('error'):
            return jsonify({'error': data.get('error', 'No data'), 'symbol': symbol}), 200
        settings = UserSettings.query.first() if _db_ready else None
        indicators = indicator_engine.calculate_all(data, settings)
        result = get_full_trading_intelligence(symbol, '5m', data, indicators)
        return jsonify(result)
    except Exception as e:
        logger.exception('trading_intelligence symbol=%s error=%s', symbol, e)
        return jsonify({'error': str(e), 'symbol': symbol}), 200

@app.route('/api/cheap-options')
def cheap_options_scan():
    """Cheap Option Radar - serve from background cache"""
    if _cheap_options_cache['data']:
        return jsonify(_cheap_options_cache['data'])
    return jsonify({
        'candidates': [],
        'pending': True,
        'message': 'Initial scan in progress, please try again in 30 seconds',
        'timestamp': datetime.now().isoformat()
    }), 202

@app.route('/api/cheap-options-radar/<symbol>')
def cheap_options_radar_symbol(symbol):
    """Step 5: Cheap Options Radar for a single symbol - strike, expiration, premium, R:R, signal score."""
    symbol = (symbol or '').strip().upper()
    if not symbol:
        return jsonify({'error': 'Symbol required', 'contracts': []}), 400
    try:
        from services.cheap_option_radar import CheapOptionRadar
        radar = CheapOptionRadar()
        result = radar.scan(universe=[symbol], limit=10)
        candidates = result.get('candidates', [])
        contracts = []
        for c in candidates:
            opt = c.get('option') or {}
            atr_pct = c.get('atr_pct') or 0
            contracts.append({
                'symbol': c.get('symbol'),
                'strike': opt.get('strike') or c.get('strike'),
                'expiration': opt.get('expiration') or c.get('expiration'),
                'premium': c.get('premium') or opt.get('premium', 0),
                'option_type': (c.get('option_type') or opt.get('type', 'call')).upper(),
                'estimated_rr': round(atr_pct * 100, 1) if atr_pct else None,
                'signal_score': c.get('score', 0),
                'reason': (c.get('reasons') or [])[0] if c.get('reasons') else '',
            })
        return jsonify({
            'symbol': symbol,
            'contracts': contracts,
            'scanned': result.get('scanned', 1),
            'qualified': result.get('qualified', 0),
            'timestamp': result.get('timestamp', datetime.now().isoformat()),
        })
    except Exception as e:
        logger.exception('cheap_options_radar symbol=%s error=%s', symbol, e)
        return jsonify({'error': str(e), 'symbol': symbol, 'contracts': []}), 200

@app.route('/api/time-edge/<symbol>')
def time_edge_analysis(symbol):
    """Time-of-Day Edge analysis for a ticker"""
    try:
        settings = UserSettings.query.first()
        timezone = settings.timezone if settings else 'CT'
        timezone = request.args.get('tz', timezone)
        
        result = time_edge_analyzer.analyze(symbol.upper(), timezone=timezone)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Time edge error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gatekeeper')
def gatekeeper_status():
    """Get Late-Day Gatekeeper status"""
    try:
        settings = UserSettings.query.first()
        timezone = settings.timezone if settings else 'CT'
        
        
        late_day_gatekeeper.reset_daily(settings)
        if settings:
            db.session.commit()
        
        result = late_day_gatekeeper.check_window(settings, timezone)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Gatekeeper error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gatekeeper/mark-green', methods=['POST'])
def mark_green():
    """Mark that a profitable trade was made today"""
    try:
        settings = UserSettings.query.first()
        if settings:
            late_day_gatekeeper.mark_profitable(settings)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Marked as green for today'})
        return jsonify({'success': False, 'message': 'No settings found'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/gatekeeper', methods=['POST'])
def update_gatekeeper_settings():
    """Update Late-Day Gatekeeper settings"""
    try:
        data = request.get_json()
        settings = UserSettings.query.first()
        
        if not settings:
            settings = UserSettings()
            db.session.add(settings)
        
        if 'enabled' in data:
            settings.gatekeeper_enabled = data['enabled']
        if 'start_hour' in data:
            settings.gatekeeper_start_hour = data['start_hour']
        if 'start_minute' in data:
            settings.gatekeeper_start_minute = data['start_minute']
        if 'end_hour' in data:
            settings.gatekeeper_end_hour = data['end_hour']
        if 'end_minute' in data:
            settings.gatekeeper_end_minute = data['end_minute']
        if 'stop_when_green' in data:
            settings.gatekeeper_stop_when_green = data['stop_when_green']
        if 'timezone' in data:
            settings.timezone = data['timezone']
        
        db.session.commit()
        return jsonify({'success': True, 'settings': settings.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/watchlist/add', methods=['POST'])
@login_required
def add_to_watchlist():
    """Add a ticker to the user's watchlist (and global tickers if needed). Plan limit enforced."""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Login required'}), 401
        data = request.get_json()
        symbol = (data.get('symbol') or '').upper().strip()
        if not symbol:
            return jsonify({'success': False, 'error': 'Symbol required'}), 400
        max_allowed = get_plan_max_watchlist(getattr(user, 'plan', None) or Config.DEFAULT_PLAN)
        if max_allowed != -1:
            current_count = Watchlist.query.filter_by(user_id=user.id).count()
            if current_count >= max_allowed:
                return jsonify({
                    'success': False,
                    'error': f'Watchlist limit reached ({max_allowed} symbols). Upgrade to add more.',
                    'upgrade': True
                }), 403
        existing_wl = Watchlist.query.filter_by(user_id=user.id, symbol=symbol).first()
        if existing_wl:
            db.session.commit()
            return jsonify({'success': True, 'message': f'{symbol} already in watchlist'})
        wl = Watchlist(user_id=user.id, symbol=symbol)
        db.session.add(wl)
        existing = Ticker.query.filter_by(symbol=symbol).first()
        if existing:
            existing.is_active = True
        else:
            db.session.add(Ticker(symbol=symbol, is_active=True))
        db.session.commit()
        return jsonify({'success': True, 'message': f'{symbol} added to watchlist'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'Connected to trading signals server'})

@socketio.on('subscribe')
def handle_subscribe(data):
    symbol = data.get('symbol', 'SPY')
    emit('subscribed', {'symbol': symbol})

@socketio.on('request_update')
def handle_update_request(data):
    symbol = data.get('symbol', 'SPY')
    settings = UserSettings.query.first()
    market_data = data_fetcher.get_stock_data(symbol, period='1d', interval='1m')
    
    if market_data and 'error' not in market_data:
        indicators = indicator_engine.calculate_all(market_data, settings)
        signal = strategy_orchestrator.generate_signal(symbol, indicators, market_data, settings)
        emit('signal_update', {
            'symbol': symbol,
            'data': market_data,
            'indicators': indicators,
            'signal': signal,
            'market_status': strategy_orchestrator.get_market_status()
        })

def background_updates():
    while True:
        socketio.sleep(15)
        with app.app_context():
            tickers = Ticker.query.filter_by(is_active=True).all()
            settings = UserSettings.query.first()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔃 Scanning {len(tickers)} symbols for new signals...")
            
            for ticker in tickers:
                try:
                    market_data = data_fetcher.get_stock_data(ticker.symbol, period='1d', interval='1m')
                    if market_data and 'error' not in market_data:
                        indicators = indicator_engine.calculate_all(market_data, settings)
                        signal = strategy_orchestrator.generate_signal(
                            ticker.symbol, indicators, market_data, settings
                        )
                        socketio.emit('signal_update', {
                            'symbol': ticker.symbol,
                            'data': market_data,
                            'indicators': indicators,
                            'signal': signal,
                            'market_status': strategy_orchestrator.get_market_status()
                        })
                except Exception as e:
                    print(f"Error updating {ticker.symbol}: {e}")

socketio.start_background_task(background_updates)
socketio.start_background_task(background_price_updater)
socketio.start_background_task(background_cheap_options_scanner)

if __name__ == '__main__':
    print("🚀 Signal Forge starting on http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, log_output=True)
