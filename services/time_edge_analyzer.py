"""
Time-of-Day Edge Analyzer
Computes historical patterns for when tickers make highs, lows, pullbacks, and expansions
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import pytz

logger = logging.getLogger(__name__)


class TimeEdgeAnalyzer:
    """Analyzes time-of-day patterns for trading edge"""
    
    def __init__(self):
        self.ct_tz = pytz.timezone('America/Chicago')
        self.et_tz = pytz.timezone('America/New_York')
        
        # Time buckets (5-minute intervals grouped into 30-min buckets)
        self.time_buckets = [
            ('09:30', '10:00'),
            ('10:00', '10:30'),
            ('10:30', '11:00'),
            ('11:00', '11:30'),
            ('11:30', '12:00'),
            ('12:00', '12:30'),
            ('12:30', '13:00'),
            ('13:00', '13:30'),
            ('13:30', '14:00'),
            ('14:00', '14:30'),
            ('14:30', '15:00'),
            ('15:00', '15:30'),
            ('15:30', '16:00'),
        ]
    
    def analyze(self, symbol, days=30, timezone='CT'):
        """
        Analyze time-of-day patterns for a ticker
        
        Args:
            symbol: Ticker symbol
            days: Number of trading days to analyze
            timezone: 'CT' for Central or 'ET' for Eastern
        
        Returns:
            dict with pattern analysis and chart data
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get 5-minute data for last month
            df = ticker.history(period='1mo', interval='5m')
            
            if df.empty or len(df) < 100:
                return self._empty_result(symbol)
            
            # Convert to target timezone
            target_tz = self.ct_tz if timezone == 'CT' else self.et_tz
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            df.index = df.index.tz_convert(target_tz)
            
            # Group by date
            df['date'] = df.index.date
            df['time'] = df.index.strftime('%H:%M')
            
            # Analyze patterns
            high_times = []
            low_times = []
            pullback_times = []
            expansion_times = []
            
            for date, day_df in df.groupby('date'):
                if len(day_df) < 20:  # Skip incomplete days
                    continue
                
                # Find time of day high
                high_idx = day_df['High'].idxmax()
                high_times.append(high_idx.strftime('%H:%M'))
                
                # Find time of day low
                low_idx = day_df['Low'].idxmin()
                low_times.append(low_idx.strftime('%H:%M'))
                
                # Find largest pullback (biggest drop from prior high)
                pullback_time = self._find_largest_pullback(day_df)
                if pullback_time:
                    pullback_times.append(pullback_time)
                
                # Find late-day expansion (biggest move after 2pm)
                expansion_time = self._find_late_expansion(day_df, timezone)
                if expansion_time:
                    expansion_times.append(expansion_time)
            
            # Calculate distributions
            high_distribution = self._time_distribution(high_times)
            low_distribution = self._time_distribution(low_times)
            pullback_distribution = self._time_distribution(pullback_times)
            expansion_distribution = self._time_distribution(expansion_times)
            
            # Get most common times using different methods for differentiation
            avg_high_time = self._mode_time(high_times)
            avg_low_time = self._mode_time(low_times)
            
            # If high and low times are the same bucket, try median first
            if avg_high_time == avg_low_time and avg_high_time != '--:--':
                median_high = self._median_time(high_times)
                median_low = self._median_time(low_times)
                
                # If medians are different, use them
                if median_high != median_low:
                    avg_high_time = median_high
                    avg_low_time = median_low
                # Otherwise use secondary mode (second most common bucket)
                else:
                    secondary_high = self._secondary_mode_time(high_times)
                    secondary_low = self._secondary_mode_time(low_times)
                    if secondary_high and secondary_high != avg_high_time:
                        avg_high_time = secondary_high
                    elif secondary_low and secondary_low != avg_low_time:
                        avg_low_time = secondary_low
            
            avg_pullback_time = self._mode_time(pullback_times)
            avg_expansion_time = self._mode_time(expansion_times)
            
            # Generate summary text
            summary = self._generate_summary(
                symbol, avg_high_time, avg_low_time, 
                avg_pullback_time, avg_expansion_time, timezone
            )
            
            # Create chart data (bucket-based for bar chart)
            chart_data = self._create_chart_data(
                high_distribution, low_distribution,
                pullback_distribution, expansion_distribution
            )
            
            return {
                'symbol': symbol,
                'days_analyzed': len(set(df['date'])),
                'timezone': timezone,
                'avg_high_time': avg_high_time,
                'avg_low_time': avg_low_time,
                'avg_pullback_time': avg_pullback_time,
                'avg_expansion_time': avg_expansion_time,
                'high_distribution': high_distribution,
                'low_distribution': low_distribution,
                'pullback_distribution': pullback_distribution,
                'expansion_distribution': expansion_distribution,
                'chart_data': chart_data,
                'summary': summary,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Time edge analysis error for {symbol}: {e}")
            return self._empty_result(symbol)
    
    def _find_largest_pullback(self, day_df):
        """Find the time of the largest pullback (price drop)"""
        try:
            prices = day_df['Close'].values
            times = day_df.index
            
            max_drawdown = 0
            pullback_idx = None
            
            running_max = prices[0]
            for i, price in enumerate(prices):
                if price > running_max:
                    running_max = price
                drawdown = (running_max - price) / running_max
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    pullback_idx = i
            
            if pullback_idx is not None and max_drawdown > 0.003:  # At least 0.3% pullback
                return times[pullback_idx].strftime('%H:%M')
            return None
            
        except:
            return None
    
    def _find_late_expansion(self, day_df, timezone):
        """Find the time of late-day expansion (after 2pm local)"""
        try:
            cutoff_hour = 14 if timezone == 'CT' else 14  # 2pm
            
            late_df = day_df[day_df.index.hour >= cutoff_hour]
            if len(late_df) < 5:
                return None
            
            # Find largest candle (high - low)
            late_df = late_df.copy()
            late_df['range'] = late_df['High'] - late_df['Low']
            max_range_idx = late_df['range'].idxmax()
            
            return max_range_idx.strftime('%H:%M')
            
        except:
            return None
    
    def _time_distribution(self, times):
        """Create time distribution grouped by 30-min buckets"""
        if not times:
            return []
        
        bucket_counts = {}
        for bucket_start, bucket_end in self.time_buckets:
            bucket_counts[f"{bucket_start}-{bucket_end}"] = 0
        
        for t in times:
            hour, minute = map(int, t.split(':'))
            time_val = hour * 60 + minute
            
            for bucket_start, bucket_end in self.time_buckets:
                start_h, start_m = map(int, bucket_start.split(':'))
                end_h, end_m = map(int, bucket_end.split(':'))
                
                start_val = start_h * 60 + start_m
                end_val = end_h * 60 + end_m
                
                if start_val <= time_val < end_val:
                    bucket_key = f"{bucket_start}-{bucket_end}"
                    bucket_counts[bucket_key] += 1
                    break
        
        total = sum(bucket_counts.values())
        result = []
        for bucket, count in bucket_counts.items():
            pct = round((count / total) * 100, 1) if total > 0 else 0
            result.append({
                'bucket': bucket,
                'count': count,
                'percent': pct
            })
        
        return result
    
    def _mode_time(self, times):
        """Get most common time using 15-minute buckets for better precision"""
        if not times:
            return '--:--'
        
        # Group by 15-min buckets for better precision
        bucket_counts = {}
        for t in times:
            hour, minute = map(int, t.split(':'))
            bucket_min = (minute // 15) * 15
            bucket = f"{hour:02d}:{bucket_min:02d}"
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        
        if bucket_counts:
            return max(bucket_counts, key=bucket_counts.get)
        return '--:--'
    
    def _median_time(self, times):
        """Get median time for more accurate representation"""
        if not times:
            return '--:--'
        
        # Convert to minutes from midnight
        minutes_list = []
        for t in times:
            hour, minute = map(int, t.split(':'))
            minutes_list.append(hour * 60 + minute)
        
        minutes_list.sort()
        median_minutes = minutes_list[len(minutes_list) // 2]
        
        hour = median_minutes // 60
        minute = median_minutes % 60
        return f"{hour:02d}:{minute:02d}"
    
    def _secondary_mode_time(self, times):
        """Get second most common time bucket"""
        if not times or len(times) < 2:
            return None
        
        # Group by 15-min buckets
        bucket_counts = {}
        for t in times:
            hour, minute = map(int, t.split(':'))
            bucket_min = (minute // 15) * 15
            bucket = f"{hour:02d}:{bucket_min:02d}"
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        
        if len(bucket_counts) < 2:
            return None
        
        # Sort by count and get second highest
        sorted_buckets = sorted(bucket_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_buckets[1][0] if len(sorted_buckets) > 1 else None
    
    def _generate_summary(self, symbol, high_time, low_time, pullback_time, expansion_time, tz):
        """Generate plain-English summary of patterns"""
        tz_label = 'CT' if tz == 'CT' else 'ET'
        
        parts = []
        
        if high_time != '--:--' and low_time != '--:--':
            if high_time == low_time:
                # Check if this is near market open (8:30-9:30 CT or 9:30-10:30 ET)
                open_start = 8 if tz == 'CT' else 9
                open_end = 10 if tz == 'CT' else 11
                try:
                    hour = int(high_time.split(':')[0])
                    if open_start <= hour < open_end:
                        parts.append(f"{symbol} shows high volatility near market open ({high_time} {tz_label}) with both extremes forming early.")
                    else:
                        parts.append(f"{symbol} shows concentrated price action around {high_time} {tz_label}.")
                except:
                    parts.append(f"{symbol} shows concentrated price action around {high_time} {tz_label}.")
            elif high_time < low_time:
                parts.append(f"{symbol} typically makes its high around {high_time} {tz_label} and low around {low_time} {tz_label}.")
            else:
                parts.append(f"{symbol} typically makes its low around {low_time} {tz_label} and high around {high_time} {tz_label}.")
        
        if pullback_time != '--:--':
            parts.append(f"The largest pullbacks often occur around {pullback_time} {tz_label}.")
        
        if expansion_time != '--:--':
            parts.append(f"Late-day expansion typically happens around {expansion_time} {tz_label}.")
        
        if not parts:
            return f"Not enough data to determine time patterns for {symbol}."
        
        return ' '.join(parts)
    
    def _create_chart_data(self, high_dist, low_dist, pullback_dist, expansion_dist):
        """Create data structure for Chart.js bar chart"""
        labels = [b['bucket'] for b in high_dist] if high_dist else []
        
        return {
            'labels': labels,
            'datasets': [
                {
                    'label': 'Day High',
                    'data': [b['percent'] for b in high_dist],
                    'backgroundColor': 'rgba(40, 167, 69, 0.7)'
                },
                {
                    'label': 'Day Low',
                    'data': [b['percent'] for b in low_dist],
                    'backgroundColor': 'rgba(220, 53, 69, 0.7)'
                },
                {
                    'label': 'Pullback',
                    'data': [b['percent'] for b in pullback_dist],
                    'backgroundColor': 'rgba(255, 193, 7, 0.7)'
                },
                {
                    'label': 'Late Expansion',
                    'data': [b['percent'] for b in expansion_dist],
                    'backgroundColor': 'rgba(0, 123, 255, 0.7)'
                }
            ]
        }
    
    def _empty_result(self, symbol):
        """Return empty result structure"""
        return {
            'symbol': symbol,
            'days_analyzed': 0,
            'timezone': 'CT',
            'avg_high_time': '--:--',
            'avg_low_time': '--:--',
            'avg_pullback_time': '--:--',
            'avg_expansion_time': '--:--',
            'high_distribution': [],
            'low_distribution': [],
            'pullback_distribution': [],
            'expansion_distribution': [],
            'chart_data': {'labels': [], 'datasets': []},
            'summary': f'Not enough data for {symbol}.',
            'timestamp': datetime.now().isoformat()
        }


# Singleton instance
time_edge_analyzer = TimeEdgeAnalyzer()
