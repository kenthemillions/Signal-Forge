"""
Smart Coach - Rule-based trade analysis with optional DeepSeek AI
Analyzes questions about trades using existing signal data
Falls back to rule-based when no AI key is provided
"""
import re
import requests

DEEPSEEK_SYSTEM_PROMPT = """You are an experienced options trading coach analyzing real market data.
You have access to technical indicators (RSI, MACD, VWAP, trend, momentum, volume, EMA alignment), Fibonacci levels, and signal data.
Give clear, actionable guidance in 2-4 sentences. Be direct - start with YES, NO, or WAIT.
Reference only the actual data state provided (e.g. "RSI at 45", "price above VWAP", "MACD bullish cross"). Do not make generic or unverifiable claims (e.g. "typically makes highs at 10:00").
Session timing may be framed as: opening range 9:30-9:35; institutional clarity 9:35-10:00; VWAP tests mid-morning; lunch consolidation 11:30-1:30; power hour after 3:00. Do not state specific times as statistical facts for a symbol unless the data explicitly supports it.
Never guarantee profits - trading involves risk."""

def ask_deepseek(question: str, symbol: str, institutional_data: dict, api_key: str, indicators: dict = None) -> str:
    """Call DeepSeek API for AI response with full indicator context"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        ind = indicators or {}
        rsi = ind.get('rsi', {})
        macd = ind.get('macd', {})
        bollinger = ind.get('bollinger', {})
        vwap = ind.get('vwap', {})
        ema = ind.get('ema', {})
        fib = ind.get('fibonacci', {})
        volume = ind.get('volume', {})
        support_resistance = ind.get('support_resistance', {})
        
        context = f"""Symbol: {symbol}
Current Price: ${ind.get('current_price', 'N/A')}

=== SIGNAL STATE ===
Signal: {institutional_data.get('state', 'UNKNOWN')}
Confidence: {institutional_data.get('confidence', 0)}%
Market Regime: {institutional_data.get('regime', 'UNKNOWN')}
Bias: {institutional_data.get('bias', 'NEUTRAL')}
Location: {institutional_data.get('location', 'UNKNOWN')}

=== TECHNICAL INDICATORS ===
RSI: {rsi.get('value', 'N/A')} ({rsi.get('signal', 'N/A')})
MACD: {macd.get('signal_type', 'N/A')} (Histogram: {macd.get('histogram', 'N/A')})
Bollinger: {bollinger.get('signal', 'N/A')} (Upper: ${bollinger.get('upper', 'N/A')}, Lower: ${bollinger.get('lower', 'N/A')})
VWAP: ${vwap.get('value', 'N/A')} ({'Above' if vwap.get('above_vwap') else 'Below'} VWAP)
EMA: 13=${ema.get('ema_13', ema.get('ema13', 'N/A'))}, 48=${ema.get('ema_48', ema.get('ema48', 'N/A'))} (Price vs 13: {ema.get('price_vs_ema_13', 'N/A')})
Volume: {volume.get('spike_ratio', 1):.1f}x average (spike: {volume.get('spike', False)})

=== FIBONACCI RETRACEMENT ===
Swing High: ${fib.get('swing_high', 'N/A')} | Swing Low: ${fib.get('swing_low', 'N/A')}
Current Retracement: {fib.get('retracement_pct', 'N/A')}%
Fib Zone: {fib.get('zone', 'N/A')}
Key Levels: 38.2%=${fib.get('levels', {}).get('38.2', 'N/A')}, 50%=${fib.get('levels', {}).get('50.0', 'N/A')}, 61.8%=${fib.get('levels', {}).get('61.8', 'N/A')}
Nearest Fib Support: ${fib.get('nearest_support', 'N/A')}
Nearest Fib Resistance: ${fib.get('nearest_resistance', 'N/A')}

=== SUPPORT/RESISTANCE ===
Support: ${support_resistance.get('support', 'N/A')}
Resistance: ${support_resistance.get('resistance', 'N/A')}"""
        
        logger.info(f"DeepSeek API call for {symbol} with key starting: {api_key[:10]}...")
        
        response = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Market Context:\n{context}\n\nQuestion: {question}"}
                ],
                "max_tokens": 200,
                "temperature": 0.7
            },
            timeout=15
        )
        
        logger.info(f"DeepSeek response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logger.error(f"DeepSeek exception: {str(e)}")
        return None

def parse_question(question: str) -> dict:
    """Parse user question to extract intent"""
    q = question.lower()
    
    result = {
        'direction': None,
        'action': 'entry'
    }
    
    if any(word in q for word in ['call', 'calls', 'long', 'buy', 'bullish']):
        result['direction'] = 'CALL'
    elif any(word in q for word in ['put', 'puts', 'short', 'sell', 'bearish']):
        result['direction'] = 'PUT'
    
    if any(word in q for word in ['exit', 'close', 'take profit', 'stop']):
        result['action'] = 'exit'
    
    return result

def analyze_trade(question: str, symbol: str, institutional_data: dict, seasonality_data: dict = None) -> str:
    """Generate coaching response based on market data"""
    
    parsed = parse_question(question)
    direction = parsed['direction']
    
    state = institutional_data.get('state', 'WAIT')
    confidence = institutional_data.get('confidence', 0)
    regime = institutional_data.get('regime', 'UNKNOWN')
    location = institutional_data.get('location', 'UNKNOWN')
    bias = institutional_data.get('bias', 'NEUTRAL')
    confirmations = institutional_data.get('confirmations', {})
    zones = institutional_data.get('zones', {})
    
    active_confirms = [k.replace('_', ' ') for k, v in confirmations.items() if v]
    
    response_parts = []
    verdict = ""
    
    if direction == 'CALL':
        if state == 'BUY' and confidence >= 60:
            verdict = "YES - This looks like a solid CALL setup."
            response_parts.append(f"Signal is BUY with {confidence}% confidence.")
        elif state == 'PREPARE' and bias in ['BULLISH', 'NEUTRAL']:
            verdict = "ALMOST - Setup is forming, wait for confirmation."
            response_parts.append(f"Signal is PREPARE ({confidence}% confidence). Wait for a BUY trigger.")
        elif regime == 'TREND_DOWN':
            verdict = "NO - You'd be fighting the trend."
            response_parts.append("Market regime is trending DOWN. Calls are risky here.")
        elif state == 'SELL':
            verdict = "NO - Signal says SELL, not BUY."
            response_parts.append(f"Current signal is SELL with {confidence}% confidence. Don't buy calls against the signal.")
        else:
            verdict = "WAIT - Conditions aren't right yet."
            response_parts.append(f"Current state is {state}. No clear bullish setup.")
    
    elif direction == 'PUT':
        if state == 'SELL' and confidence >= 60:
            verdict = "YES - This looks like a solid PUT setup."
            response_parts.append(f"Signal is SELL with {confidence}% confidence.")
        elif state == 'PREPARE' and bias in ['BEARISH', 'NEUTRAL']:
            verdict = "ALMOST - Setup is forming, wait for confirmation."
            response_parts.append(f"Signal is PREPARE ({confidence}% confidence). Wait for a SELL trigger.")
        elif regime == 'TREND_UP':
            verdict = "NO - You'd be fighting the trend."
            response_parts.append("Market regime is trending UP. Puts are risky here.")
        elif state == 'BUY':
            verdict = "NO - Signal says BUY, not SELL."
            response_parts.append(f"Current signal is BUY with {confidence}% confidence. Don't buy puts against the signal.")
        else:
            verdict = "WAIT - Conditions aren't right yet."
            response_parts.append(f"Current state is {state}. No clear bearish setup.")
    
    else:
        if state in ['BUY', 'SELL']:
            verdict = f"SIGNAL ACTIVE: {state} at {confidence}% confidence"
            if state == 'BUY':
                response_parts.append("Bullish setup detected. Consider calls if you're looking for direction.")
            else:
                response_parts.append("Bearish setup detected. Consider puts if you're looking for direction.")
        elif state == 'PREPARE':
            verdict = f"PREPARE mode - Setup forming ({confidence}%)"
            response_parts.append("Watch for confirmation before entering.")
        else:
            verdict = "WAIT - No clear setup right now"
            response_parts.append("Market conditions don't favor a trade. Be patient.")
    
    regime_text = {
        'TREND_UP': 'Market is trending UP',
        'TREND_DOWN': 'Market is trending DOWN', 
        'RANGE': 'Market is choppy/ranging',
        'DISTRIBUTION': 'Market in distribution phase'
    }
    if regime in regime_text:
        response_parts.append(regime_text[regime] + ".")
    
    location_text = {
        'DEMAND_DISCOUNT': 'Price is at a demand zone (discount area)',
        'SUPPLY_PREMIUM': 'Price is at a supply zone (premium area)',
        'EQUILIBRIUM': 'Price is in the middle - no clear zone advantage'
    }
    if location in location_text:
        response_parts.append(location_text[location] + ".")
    
    if active_confirms:
        response_parts.append(f"Confirmations present: {', '.join(active_confirms[:3])}.")
    elif state in ['BUY', 'SELL']:
        response_parts.append("Waiting for more confirmations would strengthen this setup.")
    
    # Session timing: only use correctly framed, non-misleading statements
    if seasonality_data and seasonality_data.get('all_days'):
        all_days = seasonality_data['all_days']
        high_time = (all_days.get('high_time_common') or '').strip()
        low_time = (all_days.get('low_time_common') or '').strip()
        days_analyzed = all_days.get('days_analyzed') or 0
        if days_analyzed >= 20 and high_time and low_time and high_time != '--' and low_time != '--':
            response_parts.append(
                f"Session context (from {days_analyzed} days): opening range forms 9:30–9:35; "
                "institutional direction often clearer 9:35–10:00; VWAP tests often mid-morning; "
                "lunch consolidation typically 11:30–1:30; power hour momentum often after 3:00. "
                f"In this sample, common high time was {high_time}, low time {low_time} (use as context only, not a guarantee)."
            )
    
    full_response = f"**{verdict}**\n\n" + " ".join(response_parts)
    
    return full_response
