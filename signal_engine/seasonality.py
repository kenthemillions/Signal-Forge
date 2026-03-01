"""
Seasonality Analysis Module
Analyzes intraday patterns to find common times for day highs/lows
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import logging

logger = logging.getLogger(__name__)


class SeasonalityAnalyzer:
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(minutes=30)
    
    def analyze(self, symbol: str) -> dict:
        cache_key = f"{symbol}_seasonality"
        now = datetime.now()
        
        if cache_key in self.cache:
            cached_time, cached_data = self.cache[cache_key]
            if now - cached_time < self.cache_duration:
                return cached_data
        
        try:
            result = self._calculate_seasonality(symbol)
            self.cache[cache_key] = (now, result)
            return result
        except Exception as e:
            logger.error(f"Seasonality analysis error for {symbol}: {e}")
            return self._empty_result()
    
    def _calculate_seasonality(self, symbol: str) -> dict:
        ticker = yf.Ticker(symbol.upper())
        df = ticker.history(period="1mo", interval="5m")
        
        if df.empty or len(df) < 100:
            return self._empty_result()
        
        df = df.reset_index()
        if 'Datetime' in df.columns:
            df['datetime'] = pd.to_datetime(df['Datetime'])
        else:
            df['datetime'] = pd.to_datetime(df.index)
        
        df['date'] = df['datetime'].dt.date
        df['time'] = df['datetime'].dt.strftime('%H:%M')
        df['hour'] = df['datetime'].dt.hour
        df['minute'] = df['datetime'].dt.minute
        
        daily_stats = []
        for date, group in df.groupby('date'):
            if len(group) < 20:
                continue
            
            day_high_idx = group['High'].idxmax()
            day_low_idx = group['Low'].idxmin()
            day_open = group.iloc[0]['Open']
            day_close = group.iloc[-1]['Close']
            
            is_up_day = day_close > day_open
            
            high_time = group.loc[day_high_idx, 'time']
            low_time = group.loc[day_low_idx, 'time']
            high_price = group.loc[day_high_idx, 'High']
            low_price = group.loc[day_low_idx, 'Low']
            
            pullback_after_high = (high_price - day_close) / high_price * 100 if high_price > 0 else 0
            
            daily_stats.append({
                'date': date,
                'is_up_day': is_up_day,
                'high_time': high_time,
                'low_time': low_time,
                'pullback_after_high': pullback_after_high,
                'day_range': (high_price - low_price) / low_price * 100 if low_price > 0 else 0
            })
        
        if not daily_stats:
            return self._empty_result()
        
        stats_df = pd.DataFrame(daily_stats)
        
        up_days = stats_df[stats_df['is_up_day']]
        down_days = stats_df[~stats_df['is_up_day']]
        
        def get_time_distribution(times):
            if len(times) == 0:
                return []
            time_counts = times.value_counts().head(5)
            total = len(times)
            return [
                {'time': t, 'count': int(c), 'percent': round(c/total*100, 1)}
                for t, c in time_counts.items()
            ]
        
        def get_most_common_time(times):
            if len(times) == 0:
                return "N/A"
            return times.mode().iloc[0] if len(times.mode()) > 0 else times.iloc[0]
        
        result = {
            'symbol': symbol.upper(),
            'days_analyzed': len(stats_df),
            'up_days_count': len(up_days),
            'down_days_count': len(down_days),
            
            'all_days': {
                'high_time_common': get_most_common_time(stats_df['high_time']),
                'low_time_common': get_most_common_time(stats_df['low_time']),
                'high_time_distribution': get_time_distribution(stats_df['high_time']),
                'low_time_distribution': get_time_distribution(stats_df['low_time']),
                'avg_pullback_after_high': round(stats_df['pullback_after_high'].mean(), 2),
                'avg_day_range': round(stats_df['day_range'].mean(), 2)
            },
            
            'up_days': {
                'high_time_common': get_most_common_time(up_days['high_time']) if len(up_days) > 0 else "N/A",
                'low_time_common': get_most_common_time(up_days['low_time']) if len(up_days) > 0 else "N/A",
                'high_time_distribution': get_time_distribution(up_days['high_time']),
                'low_time_distribution': get_time_distribution(up_days['low_time']),
                'avg_pullback_after_high': round(up_days['pullback_after_high'].mean(), 2) if len(up_days) > 0 else 0
            },
            
            'down_days': {
                'high_time_common': get_most_common_time(down_days['high_time']) if len(down_days) > 0 else "N/A",
                'low_time_common': get_most_common_time(down_days['low_time']) if len(down_days) > 0 else "N/A",
                'high_time_distribution': get_time_distribution(down_days['high_time']),
                'low_time_distribution': get_time_distribution(down_days['low_time']),
                'avg_pullback_after_high': round(down_days['pullback_after_high'].mean(), 2) if len(down_days) > 0 else 0
            },
            
            'insights': self._generate_insights(stats_df, up_days, down_days)
        }
        
        return result
    
    def _generate_insights(self, all_days, up_days, down_days) -> list:
        insights = []
        
        if len(all_days) > 5:
            common_high = all_days['high_time'].mode()
            if len(common_high) > 0:
                insights.append(f"Day highs most often occur around {common_high.iloc[0]} ET")
            
            common_low = all_days['low_time'].mode()
            if len(common_low) > 0:
                insights.append(f"Day lows most often occur around {common_low.iloc[0]} ET")
            
            avg_pullback = all_days['pullback_after_high'].mean()
            if avg_pullback > 0.3:
                insights.append(f"After hitting day high, price typically pulls back {avg_pullback:.1f}%")
        
        if len(up_days) > 3:
            up_low_mode = up_days['low_time'].mode()
            if len(up_low_mode) > 0:
                insights.append(f"On UP days, the low often forms around {up_low_mode.iloc[0]} (buy dip opportunity)")
        
        if len(down_days) > 3:
            down_high_mode = down_days['high_time'].mode()
            if len(down_high_mode) > 0:
                insights.append(f"On DOWN days, the high often forms around {down_high_mode.iloc[0]} (fade opportunity)")
        
        return insights
    
    def _empty_result(self) -> dict:
        return {
            'symbol': 'N/A',
            'days_analyzed': 0,
            'up_days_count': 0,
            'down_days_count': 0,
            'all_days': {
                'high_time_common': 'N/A',
                'low_time_common': 'N/A',
                'high_time_distribution': [],
                'low_time_distribution': [],
                'avg_pullback_after_high': 0,
                'avg_day_range': 0
            },
            'up_days': {
                'high_time_common': 'N/A',
                'low_time_common': 'N/A',
                'high_time_distribution': [],
                'low_time_distribution': [],
                'avg_pullback_after_high': 0
            },
            'down_days': {
                'high_time_common': 'N/A',
                'low_time_common': 'N/A',
                'high_time_distribution': [],
                'low_time_distribution': [],
                'avg_pullback_after_high': 0
            },
            'insights': ['Not enough data for analysis']
        }


seasonality_analyzer = SeasonalityAnalyzer()
