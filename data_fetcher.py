"""
Market Data Fetcher Module
Uses Yahoo Finance (yfinance) only for OHLCV, quotes, and session data.
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import pandas as pd
import numpy as np


class MarketDataFetcher:
    """Fetches market data from Yahoo Finance"""
    
    def __init__(self):
        self._cache = {}
        self._cache_expiry = {}
        self.cache_duration_regular = 3  
        self.cache_duration_extended = 1  
        self._options_cache = {}
        self._options_cache_expiry = {}
        self.options_cache_duration = 30  
        self._pc_ratio_history = {}  
        self._info_cache = {}
        self._info_cache_expiry = {}
        self.info_cache_duration = 10 
    
    def _get_cache_duration(self) -> int:
        """Return appropriate cache duration based on market session"""
        try:
            from zoneinfo import ZoneInfo
            et = ZoneInfo('America/New_York')
        except ImportError:
            try:
                from pytz import timezone
                et = timezone('US/Eastern')
            except ImportError:
                
                et = None
        
        if et:
            now = datetime.now(et)
        else:
            
            now = datetime.utcnow() - timedelta(hours=5)
        
        hour = now.hour
        minute = now.minute
        
        
        is_regular = (hour == 9 and minute >= 30) or (10 <= hour < 16)
        
        return self.cache_duration_regular if is_regular else self.cache_duration_extended
    
    def get_stock_data(self, symbol: str, period: str = '1d', interval: str = '5m') -> Dict:
        """
        Fetch stock data for a symbol
        
        Args:
            symbol: Stock ticker symbol (e.g., 'SPY', 'AAPL')
            period: Data period ('1d', '5d', '1mo', '3mo', '1y')
            interval: Data interval ('1m', '5m', '15m', '30m', '1h', '1d')
        
        Returns:
            Dictionary with OHLCV data and metadata
        """
        cache_key = f"{symbol}_{period}_{interval}"
        
        if cache_key in self._cache:
            if datetime.now() < self._cache_expiry.get(cache_key, datetime.min):
                return self._cache[cache_key]
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, prepost=True)
            
            if df.empty:
                df = ticker.history(period=period, interval=interval, prepost=False)
                if df.empty:
                    return {'error': f'No data available for {symbol}', 'symbol': symbol}
            
            def _safe_float(v, default=0):
                try:
                    if v is None or (isinstance(v, float) and np.isnan(v)):
                        return default
                    return float(v)
                except (TypeError, ValueError):
                    return default

            # Primary: last close from history (includes extended hours when prepost=True)
            intraday_last = _safe_float(df['Close'].iloc[-1] if len(df) > 0 else None)
            
            info = {}
            try:
                info = ticker.info
            except Exception:
                pass
            
            # fast_info is faster and often has last_price when info is empty/delayed
            fast_price = None
            fast_previous = None
            try:
                fi = getattr(ticker, 'fast_info', None)
                if fi is not None:
                    fast_price = getattr(fi, 'last_price', None)
                    fast_previous = getattr(fi, 'previous_close', None)
            except Exception:
                pass
            
            previous_close = (
                info.get('previousClose') or info.get('regularMarketPreviousClose')
                or fast_previous or (float(df['Open'].iloc[0]) if len(df) > 0 else 0)
            )
            if previous_close is None:
                previous_close = float(df['Open'].iloc[0]) if len(df) > 0 else 0
            
            premarket_price = info.get('preMarketPrice')
            postmarket_price = info.get('postMarketPrice')
            market_state = (info.get('marketState') or '').upper()
            
            # Determine session from market state or ET time
            session = 'regular'
            et_tz = None
            try:
                from zoneinfo import ZoneInfo
                et_tz = ZoneInfo('America/New_York')
            except ImportError:
                try:
                    import pytz
                    et_tz = pytz.timezone('America/New_York')
                except ImportError:
                    pass
            if et_tz:
                now_et = datetime.now(et_tz)
                hour, minute = now_et.hour, now_et.minute
                if hour < 9 or (hour == 9 and minute < 30):
                    session = 'premarket'
                elif hour >= 16:
                    session = 'afterhours'
                else:
                    session = 'regular'
            if 'PRE' in market_state or 'PREOPEN' in market_state:
                session = 'premarket'
            elif 'POST' in market_state or 'CLOSED' in market_state:
                if session == 'regular':
                    session = 'afterhours'
            
            # Current price: prefer explicit pre/post from info, else fast_info last_price, else last bar (includes extended hours)
            api_price = info.get('regularMarketPrice') or info.get('currentPrice') or 0
            regular_price = intraday_last if intraday_last > 0 else (api_price or fast_price or 0)
            if regular_price is None:
                regular_price = intraday_last
            
            bid_price = info.get('bid', 0) or 0
            ask_price = info.get('ask', 0) or 0
            
            if session == 'premarket' and (premarket_price is None or premarket_price <= 0):
                premarket_price = intraday_last if intraday_last > 0 else fast_price
            if session == 'afterhours' and (postmarket_price is None or postmarket_price <= 0):
                postmarket_price = intraday_last if intraday_last > 0 else fast_price

            price_source = 'unknown'
            if premarket_price and premarket_price > 0 and session == 'premarket':
                current_price = float(premarket_price)
                price_source = 'preMarketPrice'
                change = current_price - (float(previous_close or 0))
                change_percent = (change / float(previous_close or 1)) * 100 if previous_close else 0
            elif postmarket_price and postmarket_price > 0 and session == 'afterhours':
                current_price = float(postmarket_price)
                price_source = 'postMarketPrice'
                change = current_price - (float(previous_close or 0))
                change_percent = (change / float(previous_close or 1)) * 100 if previous_close else 0
            else:
                # Regular session: prefer Yahoo regularMarketPrice so quote matches official last price
                api_f = float(api_price) if api_price else 0
                if api_f and api_f > 0:
                    current_price = api_f
                    price_source = 'regularMarketPrice'
                elif fast_price and float(fast_price) > 0:
                    current_price = float(fast_price)
                    price_source = 'fast_info.last_price'
                else:
                    current_price = intraday_last if intraday_last and intraday_last > 0 else api_f
                    price_source = 'history.Close.last' if (intraday_last and intraday_last > 0) else 'fallback'
                change = current_price - (float(previous_close or 0))
                change_percent = (change / float(previous_close or 1)) * 100 if previous_close else 0

            change = round(float(change), 2)
            change_percent = round(float(change_percent), 2)
            previous_close_f = float(previous_close or 0)
            regular_close = float(api_price or current_price) if api_price else current_price

            result = {
                'symbol': symbol,
                'timestamps': [ts.isoformat() for ts in df.index.tolist()],
                'opens': df['Open'].tolist(),
                'highs': df['High'].tolist(),
                'lows': df['Low'].tolist(),
                'closes': df['Close'].tolist(),
                'volumes': df['Volume'].tolist(),
                'current_price': float(round(current_price, 2)),
                'regular_close': float(round(regular_close, 2)),
                'session': session,
                'price_source': price_source,
                'previous_close': float(round(previous_close_f, 2)),
                'open_price': float(round(df['Open'].iloc[0], 2)) if len(df) > 0 else 0,
                'high': float(round(df['High'].max(), 2)) if len(df) > 0 else 0,
                'low': float(round(df['Low'].min(), 2)) if len(df) > 0 else 0,
                'volume': int(df['Volume'].sum()) if len(df) > 0 else 0,
                'change': change,
                'change_percent': change_percent,
                'market_cap': info.get('marketCap', 0),
                'pe_ratio': info.get('trailingPE', 0),
                'last_updated': datetime.now().isoformat()
            }
            
            self._cache[cache_key] = result
            self._cache_expiry[cache_key] = datetime.now() + timedelta(seconds=self._get_cache_duration())
            
            return result
            
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
    
    def get_multiple_stocks(self, symbols: List[str], period: str = '1d', interval: str = '5m') -> Dict[str, Dict]:
        """Fetch data for multiple symbols"""
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_stock_data(symbol, period, interval)
        return results

    def _get_info(self, ticker: yf.Ticker, symbol: str) -> Dict:
        """Helper to get ticker info with long-duration caching"""
        now = datetime.now()
        if symbol in self._info_cache:
            if now < self._info_cache_expiry.get(symbol, datetime.min):
                return self._info_cache[symbol]

        try:
            info = ticker.info
            if info:
                self._info_cache[symbol] = info
                self._info_cache_expiry[symbol] = now + timedelta(seconds=self.info_cache_duration)
                return info
        except Exception:
            pass
        return self._info_cache.get(symbol, {})
    
    def get_quote(self, symbol: str) -> Dict:
        """Get current quote for a symbol (Yahoo Finance)"""
        try:
            ticker = yf.Ticker(symbol)
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                pass
            fast_price = None
            try:
                fi = getattr(ticker, 'fast_info', None)
                if fi is not None:
                    fast_price = getattr(fi, 'last_price', None)
            except Exception:
                pass
            price = info.get('currentPrice') or info.get('regularMarketPrice') or fast_price or 0
            prev = info.get('regularMarketPreviousClose') or info.get('previousClose')
            if price and prev:
                try:
                    change = float(price) - float(prev)
                    change_pct = (change / float(prev)) * 100 if prev else 0
                except (TypeError, ValueError):
                    change = 0
                    change_pct = 0
            else:
                change = info.get('regularMarketChange')
                change_pct = info.get('regularMarketChangePercent')
                if change is None:
                    change = 0
                if change_pct is None:
                    change_pct = 0
            return {
                'symbol': symbol,
                'price': float(price) if price is not None else 0,
                'change': float(change) if change is not None else 0,
                'change_percent': float(change_pct) if change_pct is not None else 0,
                'volume': info.get('regularMarketVolume', 0) or 0,
                'avg_volume': info.get('averageVolume', 0) or 0,
                'bid': info.get('bid', 0) or 0,
                'ask': info.get('ask', 0) or 0,
                'day_high': info.get('dayHigh', 0) or 0,
                'day_low': info.get('dayLow', 0) or 0,
                'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0) or 0,
                'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0) or 0,
                'last_updated': datetime.now().isoformat()
            }
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
    
    def search_symbols(self, query: str) -> List[Dict]:
        """Search for ticker symbols"""
        try:
            
            ticker = yf.Ticker(query.upper())
            info = self._get_info(ticker, query.upper())
            
            if info.get('symbol'):
                return [{
                    'symbol': info.get('symbol'),
                    'name': info.get('shortName', info.get('longName', '')),
                    'type': info.get('quoteType', 'EQUITY')
                }]
            return []
        except:
            return []
    
    def clear_cache(self, symbol: str = None):
        """Clear cached data"""
        if symbol:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(symbol)]
            for key in keys_to_remove:
                if key in self._cache: del self._cache[key]
                if key in self._cache_expiry: del self._cache_expiry[key]
            
            if symbol in self._info_cache: del self._info_cache[symbol]
            if symbol in self._info_cache_expiry: del self._info_cache_expiry[symbol]
        else:
            self._cache.clear()
            self._cache_expiry.clear()
            self._info_cache.clear()
            self._info_cache_expiry.clear()
    
    def get_multi_timeframe_data(self, symbol: str) -> Dict:
        """
        Fetch data for multiple timeframes for scalping & analysis
        1m, 2m, 5m, 15m for scalping | 1h, 4h for trend confirmation
        """
        timeframes = {
            '1m': {'period': '1d', 'interval': '1m'},
            '2m': {'period': '5d', 'interval': '2m'},
            '5m': {'period': '5d', 'interval': '5m'},
            '15m': {'period': '5d', 'interval': '15m'},
            '1h': {'period': '1mo', 'interval': '1h'},
            '4h': {'period': '3mo', 'interval': '1h'} 
        }
        
        result = {'symbol': symbol, 'timeframes': {}}
        
        for tf_name, params in timeframes.items():
            data = self.get_stock_data(symbol, params['period'], params['interval'])
            if 'error' not in data:
                if tf_name == '4h' and len(data.get('closes', [])) > 0:
                    data = self._aggregate_to_4h(data)
                result['timeframes'][tf_name] = data
        
        return result
    
    def _aggregate_to_4h(self, hourly_data: Dict) -> Dict:
        """Aggregate 1h data to 4h candles"""
        if not hourly_data.get('closes'):
            return hourly_data
        
        closes = hourly_data['closes']
        opens = hourly_data['opens']
        highs = hourly_data['highs']
        lows = hourly_data['lows']
        volumes = hourly_data['volumes']
        timestamps = hourly_data['timestamps']
        
        agg_closes, agg_opens, agg_highs, agg_lows, agg_volumes, agg_timestamps = [], [], [], [], [], []
        
        for i in range(0, len(closes) - 3, 4):
            chunk_end = min(i + 4, len(closes))
            agg_opens.append(opens[i])
            agg_closes.append(closes[chunk_end - 1])
            agg_highs.append(max(highs[i:chunk_end]))
            agg_lows.append(min(lows[i:chunk_end]))
            agg_volumes.append(sum(volumes[i:chunk_end]))
            agg_timestamps.append(timestamps[i])
        
        return {
            **hourly_data,
            'opens': agg_opens,
            'closes': agg_closes,
            'highs': agg_highs,
            'lows': agg_lows,
            'volumes': agg_volumes,
            'timestamps': agg_timestamps,
            'current_price': agg_closes[-1] if agg_closes else hourly_data.get('current_price', 0)
        }
    
    def detect_institutional_activity(self, symbol: str) -> Dict:
        """
        Detect institutional buying/selling activity based on:
        - Large volume spikes (>3x average)
        - Price movement with volume confirmation
        - Block trades patterns
        """
        data = self.get_stock_data(symbol, period='5d', interval='5m')
        
        if 'error' in data or not data.get('volumes'):
            return {'detected': False, 'activity': 'NONE', 'confidence': 0}
        
        volumes = np.array(data['volumes'])
        closes = np.array(data['closes'])
        opens = np.array(data['opens'])
        
        if len(volumes) < 20:
            return {'detected': False, 'activity': 'NONE', 'confidence': 0}
        
        avg_volume = np.mean(volumes[-100:]) if len(volumes) >= 100 else np.mean(volumes)
        recent_volume = volumes[-20:]
        recent_closes = closes[-20:]
        recent_opens = opens[-20:]
        
        volume_spikes = recent_volume > (avg_volume * 2.5)
        spike_count = np.sum(volume_spikes)
        
        price_changes = recent_closes - recent_opens
        spike_indices = np.where(volume_spikes)[0]
        
        bullish_spikes = 0
        bearish_spikes = 0
        
        for idx in spike_indices:
            if price_changes[idx] > 0:
                bullish_spikes += 1
            elif price_changes[idx] < 0:
                bearish_spikes += 1
        
        total_recent_volume = int(np.sum(recent_volume))
        avg_recent_volume = int(np.mean(recent_volume))
        volume_trend = 'INCREASING' if avg_recent_volume > avg_volume * 1.2 else ('DECREASING' if avg_recent_volume < avg_volume * 0.8 else 'STABLE')
        
        if bullish_spikes > bearish_spikes and spike_count >= 2:
            activity = 'INSTITUTIONAL_BUYING'
            confidence = min(90, 50 + bullish_spikes * 10)
            detected = True
        elif bearish_spikes > bullish_spikes and spike_count >= 2:
            activity = 'INSTITUTIONAL_SELLING'
            confidence = min(90, 50 + bearish_spikes * 10)
            detected = True
        elif spike_count >= 3:
            activity = 'HIGH_ACTIVITY'
            confidence = min(70, 40 + spike_count * 5)
            detected = True
        else:
            activity = 'NORMAL'
            confidence = 0
            detected = False
        
        return {
            'detected': detected,
            'activity': activity,
            'confidence': confidence,
            'volume_spikes': int(spike_count),
            'bullish_spikes': int(bullish_spikes),
            'bearish_spikes': int(bearish_spikes),
            'avg_volume': int(avg_volume),
            'recent_avg_volume': avg_recent_volume,
            'volume_ratio': round(avg_recent_volume / avg_volume, 2) if avg_volume > 0 else 1,
            'volume_trend': volume_trend,
            'total_recent_volume': total_recent_volume
        }
    
    def get_options_flow(self, symbol: str) -> Dict:
        """
        Fetch options data and analyze unusual activity
        Returns put/call ratio, unusual volume, block trades, sweeps
        """
        cache_key = f"options_{symbol}"
        
        if cache_key in self._options_cache:
            if datetime.now() < self._options_cache_expiry.get(cache_key, datetime.min):
                return self._options_cache[cache_key]
        
        try:
            ticker = yf.Ticker(symbol)
            
            expirations = ticker.options
            if not expirations:
                return {'error': 'No options data available', 'symbol': symbol}
            
            next_expiry = expirations[0]
            second_expiry = expirations[1] if len(expirations) > 1 else None
            
            calls_df = ticker.option_chain(next_expiry).calls
            puts_df = ticker.option_chain(next_expiry).puts
            
            if second_expiry:
                calls_df2 = ticker.option_chain(second_expiry).calls
                puts_df2 = ticker.option_chain(second_expiry).puts
                calls_df = pd.concat([calls_df, calls_df2], ignore_index=True)
                puts_df = pd.concat([puts_df, puts_df2], ignore_index=True)
            
            current_price = ticker.history(period='1d')['Close'].iloc[-1] if not ticker.history(period='1d').empty else 0
            
            total_call_volume = int(calls_df['volume'].sum()) if 'volume' in calls_df.columns else 0
            total_put_volume = int(puts_df['volume'].sum()) if 'volume' in puts_df.columns else 0
            total_call_oi = int(calls_df['openInterest'].sum()) if 'openInterest' in calls_df.columns else 0
            total_put_oi = int(puts_df['openInterest'].sum()) if 'openInterest' in puts_df.columns else 0
            
            pc_ratio = round(total_put_volume / total_call_volume, 2) if total_call_volume > 0 else 0
            pc_oi_ratio = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0
            
            prev_pc = self._pc_ratio_history.get(symbol, {}).get('ratio', pc_ratio)
            pc_change = round((pc_ratio - prev_pc) / prev_pc * 100, 1) if prev_pc > 0 else 0
            pc_shift_alert = abs(pc_change) > 30
            
            self._pc_ratio_history[symbol] = {
                'ratio': pc_ratio,
                'timestamp': datetime.now().isoformat()
            }
            
            unusual_calls = self._detect_unusual_options(calls_df, 'CALL', current_price)
            unusual_puts = self._detect_unusual_options(puts_df, 'PUT', current_price)
            
            block_trades = self._detect_block_trades(calls_df, puts_df, current_price)
            
            sweeps = self._detect_sweeps(calls_df, puts_df, current_price)
            
            top_strikes = self._get_top_active_strikes(calls_df, puts_df, current_price)
            
            call_premium = self._estimate_premium_flow(calls_df)
            put_premium = self._estimate_premium_flow(puts_df)
            total_premium = call_premium + put_premium
            call_flow_pct = round(call_premium / total_premium * 100, 1) if total_premium > 0 else 50
            put_flow_pct = round(100 - call_flow_pct, 1)
            
            stock_data = self.get_stock_data(symbol, '1d', '5m')
            stock_volume = stock_data.get('volume', 1) if stock_data else 1
            options_to_stock_ratio = round((total_call_volume + total_put_volume) * 100 / stock_volume, 2) if stock_volume > 0 else 0
            
            has_hot_calls = len(unusual_calls) > 0
            has_unusual_puts = len(unusual_puts) > 0
            has_block_trades = len(block_trades) > 0
            has_sweeps = len(sweeps) > 0
            
            volume_5x_alert = any(item.get('volume_ratio', 0) >= 5 for item in unusual_calls + unusual_puts)
            large_order_alert = any(item.get('premium', 0) >= 100000 for item in block_trades)
            
            iv_data = self._calculate_iv_rank(calls_df, puts_df, symbol)
            
            result = {
                'symbol': symbol,
                'expiration': next_expiry,
                'current_price': float(round(current_price, 2)),
                'put_call_ratio': pc_ratio,
                'put_call_oi_ratio': pc_oi_ratio,
                'pc_ratio_change': pc_change,
                'pc_shift_alert': pc_shift_alert,
                'total_call_volume': total_call_volume,
                'total_put_volume': total_put_volume,
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'options_to_stock_ratio': options_to_stock_ratio,
                'unusual_calls': unusual_calls[:5],
                'unusual_puts': unusual_puts[:5],
                'block_trades': block_trades[:5],
                'sweeps': sweeps[:5],
                'top_strikes': top_strikes,
                'call_flow_pct': call_flow_pct,
                'put_flow_pct': put_flow_pct,
                'call_premium': int(call_premium),
                'put_premium': int(put_premium),
                'iv_rank': iv_data.get('iv_rank', 50),
                'iv_percentile': iv_data.get('iv_percentile', 50),
                'current_iv': iv_data.get('current_iv', 0),
                'iv_status': iv_data.get('status', 'NORMAL'),
                'indicators': {
                    'hot_calls': has_hot_calls,
                    'unusual_puts': has_unusual_puts,
                    'block_trades': has_block_trades,
                    'sweeps': has_sweeps
                },
                'alerts': {
                    'volume_5x': volume_5x_alert,
                    'pc_shift': pc_shift_alert,
                    'large_order': large_order_alert
                },
                'sentiment': 'BULLISH' if call_flow_pct > 60 else ('BEARISH' if put_flow_pct > 60 else 'NEUTRAL'),
                'last_updated': datetime.now().isoformat()
            }
            
            self._options_cache[cache_key] = result
            self._options_cache_expiry[cache_key] = datetime.now() + timedelta(seconds=self.options_cache_duration)
            
            return result
            
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
    
    def _detect_unusual_options(self, df: pd.DataFrame, option_type: str, current_price: float) -> List[Dict]:
        """Detect unusual options activity (volume > 3x open interest or very high volume)"""
        unusual = []
        
        if df.empty or 'volume' not in df.columns:
            return unusual
        
        df = df.copy()
        df['volume'] = df['volume'].fillna(0)
        df['openInterest'] = df['openInterest'].fillna(1)
        
        avg_volume = df['volume'].mean() if len(df) > 0 else 1
        
        for _, row in df.iterrows():
            volume = row.get('volume', 0)
            oi = max(row.get('openInterest', 1), 1)
            strike = row.get('strike', 0)
            last_price = row.get('lastPrice', 0)
            
            volume_ratio = volume / avg_volume if avg_volume > 0 else 0
            vol_oi_ratio = volume / oi
            
            if volume_ratio >= 3 or vol_oi_ratio >= 2:
                premium = volume * last_price * 100
                unusual.append({
                    'strike': float(strike),
                    'type': option_type,
                    'volume': int(volume),
                    'open_interest': int(oi),
                    'volume_ratio': round(volume_ratio, 1),
                    'vol_oi_ratio': round(vol_oi_ratio, 1),
                    'last_price': float(round(last_price, 2)),
                    'premium': int(premium),
                    'distance_from_price': round((strike - current_price) / current_price * 100, 1)
                })
        
        return sorted(unusual, key=lambda x: x['volume'], reverse=True)
    
    def _detect_block_trades(self, calls_df: pd.DataFrame, puts_df: pd.DataFrame, current_price: float) -> List[Dict]:
        """Detect block trades (>500 contracts in single strike)"""
        blocks = []
        
        for df, opt_type in [(calls_df, 'CALL'), (puts_df, 'PUT')]:
            if df.empty or 'volume' not in df.columns:
                continue
            
            for _, row in df.iterrows():
                volume = row.get('volume', 0)
                if volume >= 500:
                    strike = row.get('strike', 0)
                    last_price = row.get('lastPrice', 0)
                    premium = volume * last_price * 100
                    
                    blocks.append({
                        'strike': float(strike),
                        'type': opt_type,
                        'volume': int(volume),
                        'last_price': float(round(last_price, 2)),
                        'premium': int(premium),
                        'distance_from_price': round((strike - current_price) / current_price * 100, 1),
                        'is_large': premium >= 100000
                    })
        
        return sorted(blocks, key=lambda x: x['premium'], reverse=True)
    
    def _detect_sweeps(self, calls_df: pd.DataFrame, puts_df: pd.DataFrame, current_price: float) -> List[Dict]:
        """
        Detect sweep patterns - multiple strikes with unusual volume
        Simulated based on volume distribution across strikes
        """
        sweeps = []
        
        for df, opt_type in [(calls_df, 'CALL'), (puts_df, 'PUT')]:
            if df.empty or 'volume' not in df.columns:
                continue
            
            df = df.copy()
            df['volume'] = df['volume'].fillna(0)
            avg_vol = df['volume'].mean()
            
            hot_strikes = df[df['volume'] > avg_vol * 2]
            
            if len(hot_strikes) >= 3:
                total_sweep_volume = int(hot_strikes['volume'].sum())
                strikes = sorted(hot_strikes['strike'].tolist())
                avg_price = hot_strikes['lastPrice'].mean()
                
                sweeps.append({
                    'type': opt_type,
                    'strike_range': f"${strikes[0]:.0f}-${strikes[-1]:.0f}",
                    'num_strikes': len(strikes),
                    'total_volume': total_sweep_volume,
                    'avg_price': float(round(avg_price, 2)),
                    'estimated_premium': int(total_sweep_volume * avg_price * 100),
                    'direction': 'AGGRESSIVE_BUY' if opt_type == 'CALL' else 'AGGRESSIVE_SELL'
                })
        
        return sorted(sweeps, key=lambda x: x['total_volume'], reverse=True)
    
    def _get_top_active_strikes(self, calls_df: pd.DataFrame, puts_df: pd.DataFrame, current_price: float) -> List[Dict]:
        """Get top 5 most active option strikes"""
        all_strikes = []
        
        for df, opt_type in [(calls_df, 'CALL'), (puts_df, 'PUT')]:
            if df.empty or 'volume' not in df.columns:
                continue
            
            for _, row in df.iterrows():
                volume = row.get('volume', 0)
                if volume > 0:
                    strike = row.get('strike', 0)
                    last_price = row.get('lastPrice', 0)
                    
                    all_strikes.append({
                        'strike': float(strike),
                        'type': opt_type,
                        'volume': int(volume),
                        'last_price': float(round(last_price, 2)),
                        'premium': int(volume * last_price * 100),
                        'distance_pct': round((strike - current_price) / current_price * 100, 1)
                    })
        
        return sorted(all_strikes, key=lambda x: x['volume'], reverse=True)[:5]
    
    def _estimate_premium_flow(self, df: pd.DataFrame) -> float:
        """Estimate total premium flowing into options"""
        if df.empty or 'volume' not in df.columns or 'lastPrice' not in df.columns:
            return 0
        
        df = df.copy()
        df['volume'] = df['volume'].fillna(0)
        df['lastPrice'] = df['lastPrice'].fillna(0)
        
        return float((df['volume'] * df['lastPrice'] * 100).sum())
    
    def _calculate_iv_rank(self, calls_df: pd.DataFrame, puts_df: pd.DataFrame, symbol: str) -> Dict:
        """Calculate IV Rank and IV Percentile from options data"""
        try:
            all_iv = []
            for df in [calls_df, puts_df]:
                if 'impliedVolatility' in df.columns:
                    ivs = df['impliedVolatility'].dropna().tolist()
                    all_iv.extend(ivs)
            
            if not all_iv:
                return {'iv_rank': 50, 'iv_percentile': 50, 'current_iv': 0, 'status': 'NORMAL'}
            
            current_iv = round(np.mean(all_iv) * 100, 1)
            
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1y', interval='1d')
            
            if len(hist) < 30:
                iv_rank = 50
                iv_percentile = 50
            else:
                returns = hist['Close'].pct_change().dropna()
                hist_vol = returns.rolling(window=20).std() * np.sqrt(252) * 100
                hist_vol = hist_vol.dropna()
                
                if len(hist_vol) > 0:
                    vol_52w_high = hist_vol.max()
                    vol_52w_low = hist_vol.min()
                    
                    if vol_52w_high > vol_52w_low:
                        iv_rank = round((current_iv - vol_52w_low) / (vol_52w_high - vol_52w_low) * 100, 1)
                    else:
                        iv_rank = 50
                    
                    iv_percentile = round((hist_vol < current_iv).sum() / len(hist_vol) * 100, 1)
                else:
                    iv_rank = 50
                    iv_percentile = 50
            
            iv_rank = max(0, min(100, iv_rank))
            iv_percentile = max(0, min(100, iv_percentile))
            
            if iv_rank < 25:
                status = 'LOW'
            elif iv_rank < 50:
                status = 'BELOW_NORMAL'
            elif iv_rank < 75:
                status = 'ABOVE_NORMAL'
            else:
                status = 'HIGH'
            
            return {
                'iv_rank': iv_rank,
                'iv_percentile': iv_percentile,
                'current_iv': current_iv,
                'status': status
            }
        except Exception as e:
            return {'iv_rank': 50, 'iv_percentile': 50, 'current_iv': 0, 'status': 'NORMAL'}
    
    def get_earnings_calendar(self, symbol: str) -> Dict:
        """Get upcoming earnings date for a symbol"""
        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar
            
            if calendar is None or calendar.empty if hasattr(calendar, 'empty') else not calendar:
                info = ticker.info
                earnings_date = info.get('earningsDate')
                if earnings_date:
                    if isinstance(earnings_date, list) and len(earnings_date) > 0:
                        next_earnings = datetime.fromtimestamp(earnings_date[0])
                    else:
                        next_earnings = None
                else:
                    next_earnings = None
            else:
                if isinstance(calendar, pd.DataFrame):
                    if 'Earnings Date' in calendar.index:
                        next_earnings = calendar.loc['Earnings Date'].iloc[0]
                    else:
                        next_earnings = None
                elif isinstance(calendar, dict):
                    next_earnings = calendar.get('Earnings Date', [None])[0] if calendar.get('Earnings Date') else None
                else:
                    next_earnings = None
            
            if next_earnings:
                if hasattr(next_earnings, 'date'):
                    earnings_date_str = next_earnings.strftime('%Y-%m-%d')
                    days_until = (next_earnings.date() - datetime.now().date()).days if hasattr(next_earnings, 'date') else 999
                else:
                    earnings_date_str = str(next_earnings)
                    days_until = 999
                
                warning = days_until <= 7 and days_until >= 0
                
                if days_until <= 1:
                    urgency = 'CRITICAL'
                    message = f"EARNINGS TOMORROW - High IV Crush Risk!"
                elif days_until <= 3:
                    urgency = 'HIGH'
                    message = f"Earnings in {days_until} days - Consider IV Crush!"
                elif days_until <= 7:
                    urgency = 'MODERATE'
                    message = f"Earnings in {days_until} days"
                else:
                    urgency = 'NONE'
                    message = None
                
                return {
                    'symbol': symbol,
                    'next_earnings': earnings_date_str,
                    'days_until': days_until,
                    'warning': warning,
                    'urgency': urgency,
                    'message': message
                }
            
            return {
                'symbol': symbol,
                'next_earnings': None,
                'days_until': 999,
                'warning': False,
                'message': None
            }
        except Exception as e:
            return {
                'symbol': symbol,
                'next_earnings': None,
                'days_until': 999,
                'warning': False,
                'error': str(e)
            }
    
    def get_news(self, symbol: str, limit: int = 5) -> List[Dict]:
        """Get recent news for a symbol with basic sentiment detection"""
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            if not news:
                return []
            
            bullish_words = ['surge', 'soar', 'jump', 'rally', 'gain', 'rise', 'beat', 'exceed', 
                           'upgrade', 'buy', 'bullish', 'strong', 'growth', 'profit', 'boost',
                           'record', 'high', 'breakout', 'positive', 'outperform', 'win']
            bearish_words = ['fall', 'drop', 'plunge', 'sink', 'decline', 'loss', 'miss', 
                           'downgrade', 'sell', 'bearish', 'weak', 'cut', 'layoff', 'warning',
                           'crash', 'concern', 'risk', 'negative', 'underperform', 'fail', 'lawsuit']
            
            result = []
            for item in news[:limit]:
                content = item.get('content', item)
                
                title = content.get('title', item.get('title', ''))
                
                provider = content.get('provider', {})
                publisher = provider.get('displayName', '') if isinstance(provider, dict) else item.get('publisher', '')
                
                canonical_url = content.get('canonicalUrl', {})
                link = canonical_url.get('url', '') if isinstance(canonical_url, dict) else item.get('link', '')
                
                pub_date = content.get('pubDate', '')
                if pub_date:
                    try:
                        from dateutil import parser
                        parsed_date = parser.parse(pub_date)
                        published = parsed_date.strftime('%Y-%m-%d %H:%M')
                    except:
                        published = pub_date[:10] if len(pub_date) >= 10 else ''
                else:
                    pub_time = item.get('providerPublishTime', 0)
                    published = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M') if pub_time else ''
                
                title_lower = title.lower()
                bull_count = sum(1 for word in bullish_words if word in title_lower)
                bear_count = sum(1 for word in bearish_words if word in title_lower)
                
                if bull_count > bear_count:
                    sentiment = 'bullish'
                elif bear_count > bull_count:
                    sentiment = 'bearish'
                else:
                    sentiment = 'neutral'
                
                if title:
                    result.append({
                        'title': title,
                        'publisher': publisher,
                        'link': link,
                        'published': published,
                        'type': content.get('contentType', item.get('type', 'STORY')),
                        'sentiment': sentiment
                    })
            
            return result
        except Exception as e:
            return []
    
    def get_vix_data(self) -> Dict:
        """Fetch VIX data and calculate volatility regime"""
        cache_key = "vix_data"
        
        if cache_key in self._cache:
            if datetime.now() < self._cache_expiry.get(cache_key, datetime.min):
                return self._cache[cache_key]
        
        try:
            vix = yf.Ticker("^VIX")
            df = vix.history(period='5d', interval='5m')
            
            if df.empty:
                return {'error': 'No VIX data available'}
            
            current_vix = float(df['Close'].iloc[-1])
            prev_vix = float(df['Close'].iloc[-13]) if len(df) >= 13 else current_vix
            
            df_30d = vix.history(period='30d', interval='1d')
            vix_30d_high = float(df_30d['High'].max()) if not df_30d.empty else current_vix
            vix_30d_low = float(df_30d['Low'].min()) if not df_30d.empty else current_vix
            
            percentile = 0
            if vix_30d_high > vix_30d_low:
                percentile = (current_vix - vix_30d_low) / (vix_30d_high - vix_30d_low) * 100
            
            vix_change = current_vix - prev_vix
            vix_trend = 'RISING' if vix_change > 0.5 else 'FALLING' if vix_change < -0.5 else 'STABLE'
            
            if current_vix < 15:
                regime = 'LOW_VOL'
                regime_name = 'Breakout Watch'
                signal_threshold = 60
                color = 'success'
            elif current_vix < 20:
                regime = 'NORMAL'
                regime_name = 'Standard Trading'
                signal_threshold = 70
                color = 'info'
            elif current_vix < 30:
                regime = 'ELEVATED'
                regime_name = 'Caution Mode'
                signal_threshold = 80
                color = 'warning'
            else:
                regime = 'HIGH_VOL'
                regime_name = 'Crisis Mode'
                signal_threshold = 90
                color = 'danger'
            
            result = {
                'current': round(current_vix, 2),
                'change': round(vix_change, 2),
                'trend': vix_trend,
                'percentile': round(percentile, 1),
                'regime': regime,
                'regime_name': regime_name,
                'signal_threshold': signal_threshold,
                'color': color,
                'vix_30d_high': round(vix_30d_high, 2),
                'vix_30d_low': round(vix_30d_low, 2),
                'last_updated': datetime.now().isoformat()
            }
            
            self._cache[cache_key] = result
            self._cache_expiry[cache_key] = datetime.now() + timedelta(seconds=300)
            
            return result
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_pivot_points(self, symbol: str) -> Dict:
        """Calculate pivot points and Fibonacci levels"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='5d', interval='1d')
            
            if len(df) < 2:
                return {'error': 'Not enough data'}
            
            prev_day = df.iloc[-2]
            high = float(prev_day['High'])
            low = float(prev_day['Low'])
            close = float(prev_day['Close'])
            
            pivot = (high + low + close) / 3
            
            r1 = 2 * pivot - low
            r2 = pivot + (high - low)
            r3 = high + 2 * (pivot - low)
            s1 = 2 * pivot - high
            s2 = pivot - (high - low)
            s3 = low - 2 * (high - pivot)
            
            swing_range = high - low
            current_price = float(df.iloc[-1]['Close'])
            
            fib_levels = {
                'fib_0': round(low, 2),
                'fib_236': round(low + swing_range * 0.236, 2),
                'fib_382': round(low + swing_range * 0.382, 2),
                'fib_50': round(low + swing_range * 0.5, 2),
                'fib_618': round(low + swing_range * 0.618, 2),
                'fib_786': round(low + swing_range * 0.786, 2),
                'fib_100': round(high, 2)
            }
            
            all_levels = []
            level_names = {
                'R3': r3, 'R2': r2, 'R1': r1, 'Pivot': pivot,
                'S1': s1, 'S2': s2, 'S3': s3,
                'Prev High': high, 'Prev Low': low
            }
            
            for name, price in level_names.items():
                distance = (price - current_price) / current_price * 100
                strength = 'STRONG' if abs(distance) < 0.5 else 'MODERATE' if abs(distance) < 1 else 'WEAK'
                all_levels.append({
                    'name': name,
                    'price': round(price, 2),
                    'distance_pct': round(distance, 2),
                    'strength': strength,
                    'type': 'resistance' if price > current_price else 'support'
                })
            
            all_levels.sort(key=lambda x: x['price'], reverse=True)
            
            nearest_support = None
            nearest_resistance = None
            for level in all_levels:
                if level['type'] == 'support' and level['price'] < current_price:
                    if nearest_support is None or level['price'] > nearest_support['price']:
                        nearest_support = level
                elif level['type'] == 'resistance' and level['price'] > current_price:
                    if nearest_resistance is None or level['price'] < nearest_resistance['price']:
                        nearest_resistance = level
            
            return {
                'pivot': round(pivot, 2),
                'r1': round(r1, 2),
                'r2': round(r2, 2),
                'r3': round(r3, 2),
                's1': round(s1, 2),
                's2': round(s2, 2),
                's3': round(s3, 2),
                'prev_high': round(high, 2),
                'prev_low': round(low, 2),
                'fibonacci': fib_levels,
                'all_levels': all_levels,
                'nearest_support': nearest_support,
                'nearest_resistance': nearest_resistance,
                'current_price': round(current_price, 2)
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def get_top_movers(self) -> List[str]:
        """Get list of top market movers to scan"""
        default_tickers = ['SPY', 'QQQ', 'NVDA', 'TSLA', 'AAPL', 'AMZN', 'MSFT', 'GOOGL', 'META', 'AMD']
        
        try:
            movers = []
            for symbol in default_tickers:
                try:
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(period='1d', interval='5m')
                    if not df.empty and len(df) > 0:
                        open_price = df['Open'].iloc[0]
                        if open_price > 0:
                            change_pct = (df['Close'].iloc[-1] - open_price) / open_price * 100
                        else:
                            change_pct = 0
                        avg_vol = df['Volume'].mean()
                        movers.append({
                            'symbol': symbol,
                            'change_pct': abs(change_pct),
                            'volume': avg_vol
                        })
                    else:
                        movers.append({'symbol': symbol, 'change_pct': 0, 'volume': 0})
                except Exception:
                    movers.append({'symbol': symbol, 'change_pct': 0, 'volume': 0})
            
            if not movers:
                return default_tickers
            
            movers.sort(key=lambda x: x['change_pct'], reverse=True)
            return [m['symbol'] for m in movers[:10]]
        except Exception:
            return default_tickers
    
    def scan_stock(self, symbol: str, indicator_engine, strategy_orchestrator) -> Dict:
        """Analyze a single stock and return trade score"""
        try:
            data = self.get_stock_data(symbol, period='5d', interval='5m')
            if not data or 'error' in data:
                return {'symbol': symbol, 'error': data.get('error', 'No data'), 'trade_score': 0}
            
            mtf_data = self.get_multi_timeframe_data(symbol)
            indicators = indicator_engine.calculate_all(data, None)
            institutional = self.detect_institutional_activity(symbol)
            
            analysis = strategy_orchestrator.analyze_multi_timeframe(
                symbol, mtf_data, indicator_engine, institutional
            )
            
            rsi = indicators.get('rsi', {}).get('value', 50)
            macd = indicators.get('macd', {})
            volume_ratio = indicators.get('volume', {}).get('ratio', 1)
            
            signal_score = min(30, analysis.get('strength', 50) * 0.3)
            
            tf_trends = analysis.get('timeframe_trends', {})
            bullish_count = sum(1 for v in tf_trends.values() if v == 'BULLISH')
            bearish_count = sum(1 for v in tf_trends.values() if v == 'BEARISH')
            total_tfs = len(tf_trends) if tf_trends else 1
            confluence = max(bullish_count, bearish_count) / total_tfs
            confluence_score = min(25, confluence * 25)
            
            vol_score = min(20, min(volume_ratio, 5) * 4)
            
            momentum = 0
            if macd.get('histogram', 0) > 0 and macd.get('signal', 'NEUTRAL') == 'BULLISH':
                momentum = 15
            elif macd.get('histogram', 0) < 0 and macd.get('signal', 'NEUTRAL') == 'BEARISH':
                momentum = 15
            else:
                momentum = 5
            
            pivot_data = self.get_pivot_points(symbol)
            setup_score = 5
            if not pivot_data.get('error'):
                nearest_sr = pivot_data.get('nearest_support') or pivot_data.get('nearest_resistance')
                if nearest_sr:
                    distance = abs(nearest_sr.get('distance_pct', 10))
                    if distance < 0.5:
                        setup_score = 10
                    elif distance < 1:
                        setup_score = 7
            
            trade_score = int(min(100, max(0, signal_score + confluence_score + vol_score + momentum + setup_score)))
            
            direction = analysis.get('direction', 'NEUTRAL')
            if direction == 'NEUTRAL':
                if bullish_count > bearish_count:
                    direction = 'BULLISH'
                elif bearish_count > bullish_count:
                    direction = 'BEARISH'
            
            if trade_score >= 90:
                confidence = 'HIGH'
                confidence_icon = '🟢'
            elif trade_score >= 75:
                confidence = 'MODERATE'
                confidence_icon = '🟡'
            elif trade_score >= 60:
                confidence = 'LOW'
                confidence_icon = '🟠'
            else:
                confidence = 'AVOID'
                confidence_icon = '⚫'
            
            reasons = []
            if confluence > 0.8:
                reasons.append(f"{int(confluence*100)}% timeframe agreement")
            if volume_ratio > 2:
                reasons.append(f"{volume_ratio:.1f}x avg volume")
            if rsi > 70:
                reasons.append("RSI overbought")
            elif rsi < 30:
                reasons.append("RSI oversold")
            if momentum == 15:
                reasons.append("Strong MACD momentum")
            if setup_score >= 7:
                reasons.append("Near key S/R level")
            
            return {
                'symbol': symbol,
                'trade_score': trade_score,
                'direction': direction,
                'recommendation': 'CALLS' if direction == 'BULLISH' else 'PUTS' if direction == 'BEARISH' else 'WAIT',
                'confidence': confidence,
                'confidence_icon': confidence_icon,
                'current_price': data.get('current_price', 0),
                'change_percent': data.get('change_percent', 0),
                'signal_strength': int(analysis.get('strength', 50)),
                'timeframe_agreement': f"{max(bullish_count, bearish_count)}/{total_tfs}",
                'volume_ratio': round(volume_ratio, 1),
                'momentum': 'ACCELERATING' if momentum == 15 else 'FADING',
                'rsi': round(rsi, 1),
                'reasons': reasons,
                'nearest_support': pivot_data.get('nearest_support', {}).get('price') if not pivot_data.get('error') else None,
                'nearest_resistance': pivot_data.get('nearest_resistance', {}).get('price') if not pivot_data.get('error') else None,
                'institutional': institutional
            }
        except Exception as e:
            return {'symbol': symbol, 'error': str(e), 'trade_score': 0}
