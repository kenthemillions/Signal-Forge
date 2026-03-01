"""
Late-Day Gatekeeper
Controls trading signals based on time-of-day rules
"""

from datetime import datetime, time
import pytz
import logging

logger = logging.getLogger(__name__)


class LateDayGatekeeper:
    """
    Manages late-day trading window rules:
    - Disable BUY signals before 1:25 PM CT and after 2:25 PM CT
    - Allow PREPARE alerts before window, but no entries
    - Track daily profitability
    """
    
    def __init__(self):
        self.ct_tz = pytz.timezone('America/Chicago')
        self.et_tz = pytz.timezone('America/New_York')
    
    def check_window(self, settings=None, timezone='CT'):
        """
        Check if current time is within the late-day trading window
        
        Args:
            settings: UserSettings object with gatekeeper config
            timezone: 'CT' or 'ET'
        
        Returns:
            dict with window status and messaging
        """
        # Default settings if none provided
        start_hour = 13
        start_minute = 25
        end_hour = 14
        end_minute = 25
        enabled = True
        stop_when_green = True
        is_green = False
        
        if settings:
            enabled = getattr(settings, 'gatekeeper_enabled', True)
            start_hour = getattr(settings, 'gatekeeper_start_hour', 13)
            start_minute = getattr(settings, 'gatekeeper_start_minute', 25)
            end_hour = getattr(settings, 'gatekeeper_end_hour', 14)
            end_minute = getattr(settings, 'gatekeeper_end_minute', 25)
            stop_when_green = getattr(settings, 'gatekeeper_stop_when_green', True)
            is_green = getattr(settings, 'daily_profitable_trade', False)
        
        if not enabled:
            return {
                'enabled': False,
                'window_open': True,
                'allow_buy': True,
                'allow_prepare': True,
                'message': None,
                'status': 'DISABLED'
            }
        
        # Get current time in target timezone
        tz = self.ct_tz if timezone == 'CT' else self.et_tz
        now = datetime.now(tz)
        current_time = now.time()
        
        # Define window times
        window_start = time(start_hour, start_minute)
        window_end = time(end_hour, end_minute)
        
        # Check market hours (9:30 AM - 4:00 PM)
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        if current_time < market_open or current_time > market_close:
            return {
                'enabled': True,
                'window_open': False,
                'allow_buy': False,
                'allow_prepare': False,
                'message': 'Market closed.',
                'status': 'MARKET_CLOSED',
                'current_time': now.strftime('%I:%M %p %Z')
            }
        
        # Check if already profitable today
        if stop_when_green and is_green:
            return {
                'enabled': True,
                'window_open': False,
                'allow_buy': False,
                'allow_prepare': True,
                'message': 'You are green. Consider stopping.',
                'status': 'GREEN_STOP',
                'current_time': now.strftime('%I:%M %p %Z')
            }
        
        # Check if within window
        if window_start <= current_time <= window_end:
            return {
                'enabled': True,
                'window_open': True,
                'allow_buy': True,
                'allow_prepare': True,
                'message': f'Late-day window OPEN until {end_hour}:{end_minute:02d} {timezone}',
                'status': 'WINDOW_OPEN',
                'current_time': now.strftime('%I:%M %p %Z'),
                'window_closes_at': f'{end_hour}:{end_minute:02d}'
            }
        
        # Before window
        if current_time < window_start:
            mins_until = (start_hour * 60 + start_minute) - (current_time.hour * 60 + current_time.minute)
            return {
                'enabled': True,
                'window_open': False,
                'allow_buy': False,
                'allow_prepare': True,
                'message': f'Wait. Late-day window opens in {mins_until} minutes.',
                'status': 'BEFORE_WINDOW',
                'current_time': now.strftime('%I:%M %p %Z'),
                'window_opens_at': f'{start_hour}:{start_minute:02d}',
                'minutes_until': mins_until
            }
        
        # After window
        return {
            'enabled': True,
            'window_open': False,
            'allow_buy': False,
            'allow_prepare': True,
            'message': 'Wait. Late-day window closed for today.',
            'status': 'AFTER_WINDOW',
            'current_time': now.strftime('%I:%M %p %Z')
        }
    
    def filter_signal(self, signal, settings=None, timezone='CT'):
        """
        Filter a signal based on gatekeeper rules
        
        Args:
            signal: Signal dict with 'state' field
            settings: UserSettings object
            timezone: 'CT' or 'ET'
        
        Returns:
            Modified signal dict with gatekeeper messaging
        """
        window_status = self.check_window(settings, timezone)
        
        signal = dict(signal)  # Copy to avoid modifying original
        signal['gatekeeper'] = window_status
        
        if not window_status['enabled']:
            return signal
        
        signal_state = signal.get('state', 'WAIT')
        
        # If BUY signal but window not open, convert to PREPARE
        if signal_state == 'BUY' and not window_status['allow_buy']:
            signal['state'] = 'PREPARE'
            signal['gatekeeper_blocked'] = True
            signal['gatekeeper_message'] = window_status['message']
        
        # If SELL signal but window not open, also block
        if signal_state == 'SELL' and not window_status['allow_buy']:
            signal['state'] = 'PREPARE'
            signal['gatekeeper_blocked'] = True
            signal['gatekeeper_message'] = window_status['message']
        
        return signal
    
    def mark_profitable(self, settings):
        """Mark that a profitable trade was made today"""
        from datetime import date
        if settings:
            settings.daily_profitable_trade = True
            settings.daily_session_date = date.today()
            return True
        return False
    
    def reset_daily(self, settings):
        """Reset daily tracking (call at market open or session start)"""
        from datetime import date
        if settings:
            today = date.today()
            if settings.daily_session_date != today:
                settings.daily_profitable_trade = False
                settings.daily_session_date = today
                return True
        return False


# Singleton instance
late_day_gatekeeper = LateDayGatekeeper()
