"""
Cheap Option Radar - Find high-potential cheap options
Scans for tickers with volatility + momentum + cheap premiums
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CheapOptionRadar:
    """Scans for cheap options with high potential based on technical criteria"""
    
    # S&P 50 High Liquidity Stocks - ETFs + Most Active Names
    DEFAULT_UNIVERSE = [
        # Major ETFs
        'SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'XLF', 'XLE', 'XLK', 'XLV',
        # Mega-cap Tech
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'NFLX', 'CRM',
        # Financials
        'JPM', 'BAC', 'GS', 'MS', 'WFC', 'C', 'V', 'MA',
        # Energy
        'XOM', 'CVX', 'COP', 'OXY',
        # Healthcare
        'JNJ', 'UNH', 'PFE', 'MRK', 'ABBV', 'LLY',
        # Consumer
        'WMT', 'HD', 'MCD', 'NKE', 'SBUX', 'DIS', 'COST',
        # Industrial/Other
        'BA', 'CAT', 'DE', 'UPS', 'FDX',
        # High Volatility Popular
        'COIN', 'HOOD', 'RIVN', 'PLTR', 'SOFI'
    ]
    
    def __init__(self):
        self.min_atr_pct = 1.0      # ATR >= 1.0% (lowered for more results)
        self.min_rvol = 1.0         # Relative volume >= 1.0 (lowered)
        self.min_intraday_move = 0.5  # Intraday move >= 0.5% (lowered)
        self.min_premium = 0.05     # Min option premium $0.05 (lowered)
        self.max_premium = 1.00     # Max option premium $1.00 (expanded)
        self.max_spread = 0.15      # Max bid-ask spread $0.15
    
    def scan(self, universe=None, limit=10):
        """
        Scan universe for cheap option candidates
        Returns ranked list of top candidates
        """
        if universe is None:
            universe = self.DEFAULT_UNIVERSE
        
        candidates = []
        
        for symbol in universe:
            try:
                result = self._analyze_ticker(symbol)
                if result and result.get('qualifies'):
                    candidates.append(result)
            except Exception as e:
                logger.debug(f"Error analyzing {symbol}: {e}")
                continue
        
        # Sort by score (highest first)
        candidates.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return {
            'candidates': candidates[:limit],
            'scanned': len(universe),
            'qualified': len(candidates),
            'timestamp': datetime.now().isoformat()
        }
    
    def _analyze_ticker(self, symbol):
        """Analyze a single ticker for cheap option criteria"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Get intraday data (5m candles for today)
            df = ticker.history(period='5d', interval='5m')
            if df.empty or len(df) < 20:
                return None
            
            # Get daily data for ATR calculation
            daily_df = ticker.history(period='1mo', interval='1d')
            if daily_df.empty or len(daily_df) < 14:
                return None
            
            current_price = df['Close'].iloc[-1]
            
            # Calculate ATR (14-period)
            atr = self._calculate_atr(daily_df)
            atr_pct = (atr / current_price) * 100
            
            # Calculate RVOL (relative volume)
            rvol = self._calculate_rvol(df)
            
            # Calculate intraday move - THIS IS KEY FOR DIRECTION
            today_df = df[df.index.date == df.index[-1].date()]
            if len(today_df) > 0:
                day_open = today_df['Open'].iloc[0]
                day_high = today_df['High'].max()
                day_low = today_df['Low'].min()
                intraday_range_pct = ((day_high - day_low) / day_open) * 100
                # Calculate actual price change from open (not just range)
                intraday_change_pct = ((current_price - day_open) / day_open) * 100
            else:
                intraday_range_pct = 0
                intraday_change_pct = 0
            
            # Check for pullback against trend
            ema_trend = self._get_trend_direction(df)
            is_pullback = self._detect_pullback(df, ema_trend)
            
            # Score the candidate
            score = 0
            reasons = []
            
            # ATR check
            if atr_pct >= self.min_atr_pct:
                score += 25
                reasons.append(f"High volatility (ATR {atr_pct:.1f}%)")
            
            # RVOL check
            if rvol >= self.min_rvol:
                score += 25
                reasons.append(f"Strong volume ({rvol:.1f}x average)")
            
            # Intraday move check
            if intraday_range_pct >= self.min_intraday_move:
                score += 25
                reasons.append(f"Active intraday ({intraday_range_pct:.1f}% range)")
            
            # Pullback check (use EMA trend for this)
            if is_pullback:
                score += 25
                reasons.append(f"Pullback in {ema_trend} trend")
            
            # FIXED: Determine direction based on INTRADAY PRICE ACTION first, not EMA
            # This prevents recommending PUTs during strong rallies
            if abs(intraday_change_pct) >= 0.5:
                # Strong intraday move - use that direction
                if intraday_change_pct > 0:
                    direction = 'CALLS'
                    reasons.insert(0, f"Strong rally (+{intraday_change_pct:.1f}%)")
                else:
                    direction = 'PUTS'
                    reasons.insert(0, f"Sharp drop ({intraday_change_pct:.1f}%)")
            else:
                # Small intraday move - fall back to EMA trend
                if ema_trend == 'UP':
                    direction = 'CALLS'
                elif ema_trend == 'DOWN':
                    direction = 'PUTS'
                else:
                    direction = 'NEUTRAL'
            
            # Try to get options data
            option_data = self._get_cheap_option(ticker, direction, current_price)
            
            # Lower qualification threshold - any stock with score >= 25 qualifies
            qualifies = score >= 25 and len(reasons) >= 1
            
            # Confidence level
            if score >= 75:
                confidence = 'HIGH'
                confidence_color = 'success'
            elif score >= 50:
                confidence = 'MEDIUM'
                confidence_color = 'warning'
            else:
                confidence = 'LOW'
                confidence_color = 'danger'
            
            # Determine display trend based on direction
            display_trend = 'UP' if direction == 'CALLS' else 'DOWN' if direction == 'PUTS' else 'NEUTRAL'
            
            result = {
                'symbol': symbol,
                'price': float(round(current_price, 2)),
                'atr_percent': float(round(atr_pct / 100, 3)),
                'atr_pct': float(round(atr_pct, 2)),
                'rvol': float(round(rvol, 2)),
                'intraday_range': float(round(intraday_range_pct, 2)),
                'intraday_change': float(round(intraday_change_pct, 2)),
                'trend': display_trend,
                'ema_trend': ema_trend,
                'is_pullback': bool(is_pullback),
                'direction': direction,
                'option_type': 'call' if direction == 'CALLS' else 'put' if direction == 'PUTS' else 'neutral',
                'score': int(score),
                'confidence': confidence,
                'confidence_color': confidence_color,
                'reasons': reasons[:3],
                'qualifies': bool(qualifies),
                'option': option_data
            }
            
            # Add premium from option data if available
            if option_data and option_data.get('premium'):
                result['premium'] = option_data['premium']
            else:
                result['premium'] = 0.0
            
            return result
            
        except Exception as e:
            logger.debug(f"Error analyzing {symbol}: {e}")
            return None
    
    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else 0
    
    def _calculate_rvol(self, df, period=20):
        """Calculate Relative Volume (current vs average)"""
        if len(df) < period:
            return 1.0
        
        # Get today's volume so far
        today_df = df[df.index.date == df.index[-1].date()]
        today_volume = today_df['Volume'].sum() if len(today_df) > 0 else 0
        
        # Get average daily volume
        daily_volumes = df.groupby(df.index.date)['Volume'].sum()
        if len(daily_volumes) > 1:
            avg_volume = daily_volumes[:-1].mean()  # Exclude today
        else:
            avg_volume = daily_volumes.mean()
        
        if avg_volume > 0:
            return today_volume / avg_volume
        return 1.0
    
    def _get_trend_direction(self, df):
        """Determine overall trend direction using EMAs"""
        if len(df) < 20:
            return 'NEUTRAL'
        
        ema_9 = df['Close'].ewm(span=9).mean().iloc[-1]
        ema_21 = df['Close'].ewm(span=21).mean().iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        if ema_9 > ema_21 and current_price > ema_9:
            return 'UP'
        elif ema_9 < ema_21 and current_price < ema_9:
            return 'DOWN'
        return 'NEUTRAL'
    
    def _detect_pullback(self, df, trend):
        """Detect if price is pulling back against the dominant trend"""
        if len(df) < 10:
            return False
        
        # Look at last 5 candles
        recent = df.tail(5)
        
        if trend == 'UP':
            # In uptrend, pullback means recent red candles or lower lows
            red_candles = (recent['Close'] < recent['Open']).sum()
            return red_candles >= 2
        elif trend == 'DOWN':
            # In downtrend, pullback means recent green candles or higher highs
            green_candles = (recent['Close'] > recent['Open']).sum()
            return green_candles >= 2
        
        return False
    
    def _get_cheap_option(self, ticker, direction, current_price):
        """Try to find a cheap option matching criteria"""
        try:
            # Get next expiration
            expirations = ticker.options
            if not expirations:
                return None
            
            # Get nearest expiration (weekly preferred)
            exp_date = expirations[0]
            
            chain = ticker.option_chain(exp_date)
            
            if direction == 'CALLS':
                options = chain.calls
            elif direction == 'PUTS':
                options = chain.puts
            else:
                # For neutral, check both
                calls = chain.calls
                puts = chain.puts
                options = pd.concat([calls, puts])
            
            if options.empty:
                return None
            
            # Filter ATM ± 1 strike
            atm_strikes = options[
                (options['strike'] >= current_price * 0.97) &
                (options['strike'] <= current_price * 1.03)
            ]
            
            if atm_strikes.empty:
                atm_strikes = options
            
            # Filter by premium range
            cheap_options = atm_strikes[
                (atm_strikes['lastPrice'] >= self.min_premium) &
                (atm_strikes['lastPrice'] <= self.max_premium)
            ]
            
            if cheap_options.empty:
                # Fallback: just find cheapest near ATM
                cheap_options = atm_strikes.nsmallest(3, 'lastPrice')
            
            if cheap_options.empty:
                return None
            
            # Pick best candidate (highest volume)
            best = cheap_options.loc[cheap_options['volume'].fillna(0).idxmax()]
            
            spread = best.get('ask', 0) - best.get('bid', 0)
            
            return {
                'strike': float(best['strike']),
                'premium': float(best['lastPrice']),
                'bid': float(best.get('bid', 0)),
                'ask': float(best.get('ask', 0)),
                'spread': round(spread, 2),
                'volume': int(best.get('volume', 0) or 0),
                'open_interest': int(best.get('openInterest', 0) or 0),
                'expiration': exp_date,
                'type': 'CALL' if direction == 'CALLS' else 'PUT'
            }
            
        except Exception as e:
            logger.debug(f"Error getting options: {e}")
            return None


# Singleton instance
cheap_option_radar = CheapOptionRadar()
