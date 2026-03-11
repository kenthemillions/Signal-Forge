console.log('APP VERSION 2026-03-11-quote-fix-2-boot');

class TradingSignalsApp {
    constructor() {
        this.socket = null;
        this.chart = null;
        this.currentTicker = 'SPY';
        this._quoteDebug = {
            domReady: false,
            initStarted: false,
            symbolElFound: false,
            symbolSelector: '--',
            rawSymbol: '--',
            currentTickerAssigned: '--',
            refreshDataCalled: false,
            loadTickerCardQuoteCalled: false,
            quoteRequestStarted: false,
            quoteUrl: '--',
            quoteStatus: '--',
            quoteBody: '--',
            domUpdateSuccess: false,
            lastTouch: '--'
        };
        this.audioEnabled = true;
        this.audioVolume = 0.5;
        this.settings = {};
        this.audioContext = null;
        this.advancedVisible = false;
        this.currentInterval = '5m';
        this.currentPeriod = '1d';
        this.chartType = 'line';
        
        this.TIMEFRAME_CONFIG = {
            '1m':  { barThickness: 4,  timeUnit: 'minute', stepSize: 5,  maxPoints: 120, period: '1d' },
            '2m':  { barThickness: 5,  timeUnit: 'minute', stepSize: 10, maxPoints: 100, period: '1d' },
            '5m':  { barThickness: 6,  timeUnit: 'minute', stepSize: 15, maxPoints: 80,  period: '1d' },
            '15m': { barThickness: 8,  timeUnit: 'minute', stepSize: 30, maxPoints: 60,  period: '5d' },
            '1h':  { barThickness: 12, timeUnit: 'hour',   stepSize: 1,  maxPoints: 50,  period: '1mo' },
            '4h':  { barThickness: 16, timeUnit: 'hour',   stepSize: 4,  maxPoints: 40,  period: '3mo' }
        };
        this.lastSignal = null;
        this.indicatorToggles = {
            rsi: true, macd: true, bollinger: true,
            ema13: true, ema48: true, ema200: true,
            vwap: true, volume: true, sr: true
        };
        this.tickerSelection = {};
        this.scannerTickerSelection = {};
        this.lastScanResults = [];
        this.lastPrice = 0;
        this.performanceData = this.loadPerformanceData();
        this.alertsEnabled = false;
        this.bellSound = null;
        this.alertSound = null;
        this.lotteryHourActive = false;
        this.lastLotteryAlert = null;
        this.lastReversalKey = null;
        this.signalHistory = this.loadSignalHistory();
        
        this.init();
    }
    
    _updateQuoteDebug(updates) {
        if (!this._quoteDebug) return;
        try {
            Object.assign(this._quoteDebug, updates);
            const d = this._quoteDebug;
            const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = String(val ?? '--'); };
            set('debug-dom-ready', d.domReady ? 'yes' : 'no');
            set('debug-init-started', d.initStarted ? 'yes' : 'no');
            set('debug-symbol-el-found', d.symbolElFound ? 'yes' : 'no');
            set('debug-symbol-selector', d.symbolSelector);
            set('debug-raw-symbol', d.rawSymbol);
            set('debug-current-ticker', d.currentTickerAssigned !== '--' ? d.currentTickerAssigned : (this.currentTicker || '--'));
            set('debug-refresh-called', d.refreshDataCalled ? 'yes' : 'no');
            set('debug-quote-called', d.loadTickerCardQuoteCalled ? 'yes' : 'no');
            set('debug-request-started', d.quoteRequestStarted ? 'yes' : 'no');
            set('debug-quote-url', d.quoteUrl);
            set('debug-quote-status', d.quoteStatus);
            set('debug-quote-body', (d.quoteBody && d.quoteBody.length > 80) ? d.quoteBody.substring(0, 80) + '...' : d.quoteBody);
            set('debug-dom-ok', d.domUpdateSuccess ? 'yes' : 'no');
            set('debug-last-touch', d.lastTouch);
        } catch (e) {
            console.error('_updateQuoteDebug error:', e);
        }
    }
    
    loadSignalHistory() {
        try {
            const stored = localStorage.getItem('signalHistory');
            return stored ? JSON.parse(stored) : [];
        } catch (e) {
            return [];
        }
    }
    
    saveSignalHistory() {
        try {
            if (this.signalHistory.length > 500) {
                this.signalHistory = this.signalHistory.slice(-500);
            }
            localStorage.setItem('signalHistory', JSON.stringify(this.signalHistory));
        } catch (e) {}
    }
    
    logSignal(ticker, signal, price, strength, reasons) {
        this.signalHistory.push({
            ticker,
            signal,
            price,
            strength,
            reasons: reasons || [],
            timestamp: Date.now(),
            date: new Date().toLocaleDateString(),
            time: new Date().toLocaleTimeString()
        });
        this.saveSignalHistory();
    }
    
    loadPerformanceData() {
        try {
            const stored = localStorage.getItem('signalPerformance');
            return stored ? JSON.parse(stored) : { signals: [], wins: 0, losses: 0, totalGain: 0, totalLoss: 0 };
        } catch (e) {
            return { signals: [], wins: 0, losses: 0, totalGain: 0, totalLoss: 0 };
        }
    }
    
    savePerformanceData() {
        try {
            localStorage.setItem('signalPerformance', JSON.stringify(this.performanceData));
        } catch (e) {}
    }
    
    trackSignalPerformance(data) {
        if (!data.current_price) return;
        
        const signals = this.performanceData.signals || [];
        
        if (data.main_signal && data.main_signal !== 'WAIT') {
            const hasRecent = signals.some(s => 
                s.ticker === this.currentTicker && 
                Date.now() - s.timestamp < 300000
            );
            
            if (!hasRecent) {
                signals.push({
                    ticker: this.currentTicker,
                    direction: data.main_signal,
                    entry: data.current_price,
                    timeframe: this.currentInterval,
                    timestamp: Date.now(),
                    resolved: false,
                    outcome: null
                });
                this.performanceData.totalSignals = (this.performanceData.totalSignals || 0) + 1;
            }
        }
        
        signals.forEach(sig => {
            if (sig.resolved) return;
            if (sig.ticker !== this.currentTicker) return;
            
            const priceChange = ((data.current_price - sig.entry) / sig.entry) * 100;
            const timeElapsed = Date.now() - sig.timestamp;
            
            if (sig.direction === 'BUY') {
                if (priceChange >= 1) {
                    sig.resolved = true;
                    sig.outcome = 'win';
                    sig.profit = priceChange;
                    this.performanceData.wins++;
                    this.performanceData.totalGain += priceChange;
                } else if (priceChange <= -1.5 || timeElapsed > 3600000) {
                    sig.resolved = true;
                    sig.outcome = 'loss';
                    sig.profit = priceChange;
                    this.performanceData.losses++;
                    this.performanceData.totalLoss += Math.abs(priceChange);
                }
            } else if (sig.direction === 'SELL') {
                if (priceChange <= -1) {
                    sig.resolved = true;
                    sig.outcome = 'win';
                    sig.profit = Math.abs(priceChange);
                    this.performanceData.wins++;
                    this.performanceData.totalGain += Math.abs(priceChange);
                } else if (priceChange >= 1.5 || timeElapsed > 3600000) {
                    sig.resolved = true;
                    sig.outcome = 'loss';
                    sig.profit = -priceChange;
                    this.performanceData.losses++;
                    this.performanceData.totalLoss += priceChange;
                }
            }
        });
        
        if (signals.length > 200) {
            signals.splice(0, signals.length - 200);
        }
        
        this.performanceData.signals = signals;
        this.savePerformanceData();
        this.updatePerformanceDisplay();
    }
    
    updatePerformanceDisplay() {
        const totalSignals = this.performanceData.totalSignals || 0;
        const resolved = this.performanceData.wins + this.performanceData.losses;
        const minTradesForStats = 20;
        const hasEnoughData = resolved >= minTradesForStats;
        const winRate = hasEnoughData ? ((this.performanceData.wins / resolved) * 100).toFixed(0) : '--';
        const avgWin = this.performanceData.wins > 0 ? (this.performanceData.totalGain / this.performanceData.wins).toFixed(1) : '0';
        const avgLoss = this.performanceData.losses > 0 ? (this.performanceData.totalLoss / this.performanceData.losses).toFixed(1) : '0';
        
        const totalSignalsEl = document.getElementById('total-signals');
        const winRateEl = document.getElementById('win-rate');
        const winRateBadgeEl = document.getElementById('win-rate-badge');
        const avgWinEl = document.getElementById('avg-win');
        const avgLossEl = document.getElementById('avg-loss');
        const bestTfEl = document.getElementById('best-timeframe');
        
        if (totalSignalsEl) totalSignalsEl.textContent = totalSignals;
        if (winRateEl) winRateEl.textContent = hasEnoughData ? winRate + '%' : '--';
        if (winRateBadgeEl) {
            if (!hasEnoughData) {
                winRateBadgeEl.textContent = 'Collecting Data';
                winRateBadgeEl.className = 'badge bg-secondary';
            } else {
                winRateBadgeEl.textContent = winRate + '% Win';
                const rate = parseInt(winRate) || 0;
                winRateBadgeEl.className = 'badge ' + (rate >= 60 ? 'bg-success' : rate >= 50 ? 'bg-info' : 'bg-warning');
            }
        }
        if (avgWinEl) avgWinEl.textContent = '+' + avgWin + '%';
        if (avgLossEl) avgLossEl.textContent = '-' + avgLoss + '%';
        
        const tfStats = {};
        (this.performanceData.signals || []).filter(s => s.resolved && s.outcome === 'win').forEach(s => {
            tfStats[s.timeframe] = (tfStats[s.timeframe] || 0) + 1;
        });
        
        let bestTf = '5m';
        let bestCount = 0;
        Object.entries(tfStats).forEach(([tf, count]) => {
            if (count > bestCount) {
                bestTf = tf;
                bestCount = count;
            }
        });
        
        if (bestTfEl) bestTfEl.textContent = hasEnoughData ? `${bestTf} - ${winRate}% win rate` : `${bestTf} - collecting data`;
    }
    
    async init() {
        // --- MINIMAL BOOT: read symbol from DOM, set currentTicker, update debug, run refreshData ---
        const SYMBOL_SELECTOR = '#ticker-select';
        try {
            this._updateQuoteDebug({ domReady: true, initStarted: true });
            const symbolEl = document.getElementById('ticker-select');
            this._updateQuoteDebug({ symbolSelector: SYMBOL_SELECTOR, symbolElFound: !!symbolEl });
            let rawSymbol = '';
            if (symbolEl && typeof symbolEl.value === 'string') rawSymbol = symbolEl.value.trim();
            if (!rawSymbol) rawSymbol = 'SPY';
            this.currentTicker = (rawSymbol || 'SPY').toUpperCase();
            this._updateQuoteDebug({ rawSymbol: rawSymbol || '(empty)', currentTickerAssigned: this.currentTicker });
            const tickerCardRefresh = document.getElementById('ticker-card-refresh');
            if (tickerCardRefresh) tickerCardRefresh.addEventListener('click', () => this.refreshData());
            const refreshBtn = document.getElementById('refresh-signal');
            if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshData());
            this.refreshData().catch(e => console.warn('Boot refreshData failed:', e));
        } catch (e) {
            console.error('Init boot error:', e);
            this.currentTicker = 'SPY';
            this._updateQuoteDebug({ currentTickerAssigned: 'SPY', rawSymbol: '(fallback)', symbolElFound: false });
            this.refreshData().catch(() => {});
        }
        const sessionText = document.getElementById('session-text');
        if (sessionText) sessionText.textContent = 'Loading…';
        this.initAudioContext();
        this.initSocket();
        this.initChart();
        this.bindEvents();
        this.bindKeyboardShortcuts();
        this.startTimers();
        this.startLotteryHourTimer();
        this.initMarketOpenScanner();
        this.loadPaperAccount();
        this.updateIndicatorCount();
        this.updatePerformanceDisplay();
        this.playStartupSound();
        this.initFeedbackForm();
        this.debugMode = false;
        setTimeout(() => this.clearLoadingState(), 1500);
        try {
            await this.loadTickers();
        } catch (e) {
            console.error('loadTickers failed:', e);
            this.setPriceCardError('Backend unavailable', (e && e.message) ? e.message : 'Tickers failed');
            const sel = document.getElementById('ticker-select');
            if (sel && sel.options.length === 0) {
                const opt = document.createElement('option');
                opt.value = 'SPY';
                opt.textContent = 'SPY';
                sel.appendChild(opt);
                sel.value = 'SPY';
                this.currentTicker = 'SPY';
            }
            this.clearLoadingState();
        }
        this.loadSettings();
        this.loadSignals();
        
        const enableAlertsBtn = document.getElementById('enable-alerts-btn');
        if (enableAlertsBtn) enableAlertsBtn.addEventListener('click', () => this.enableTradingAlerts());
        const debugToggle = document.getElementById('debug-toggle');
        if (debugToggle) debugToggle.addEventListener('click', () => this.toggleDebugMode());
        const reversalDismiss = document.getElementById('trend-reversal-dismiss');
        if (reversalDismiss) reversalDismiss.addEventListener('click', () => {
            const banner = document.getElementById('trend-reversal-banner');
            if (banner) banner.classList.add('d-none');
        });
        const lastHourRefresh = document.getElementById('last-hour-refresh');
        if (lastHourRefresh) lastHourRefresh.addEventListener('click', () => this.loadLastHourScan());
        
        setTimeout(() => this.clearLoadingState(), 3000);
        this.startLoadingTimeout();
        
        // Run refresh so ticker card gets price/change or explicit error
        this.refreshData().catch(e => {
            console.warn('Initial refresh failed:', e);
            this.setPriceCardError('Backend unavailable', (e && e.message) ? e.message : 'Refresh failed');
            this.clearLoadingState();
        });
    }
    
    startLoadingTimeout() {
        setTimeout(() => {
            const badge = document.getElementById('market-status');
            const textEl = document.getElementById('session-text');
            const premarketTrend = document.getElementById('premarket-trend');
            if (badge && badge.textContent === 'Loading...') {
                badge.textContent = '—';
                badge.className = 'badge bg-secondary';
            }
        if (textEl && /Loading|Connecting/.test(textEl.textContent)) {
            textEl.textContent = 'Server may be waking up. Click Refresh in a moment.';
                const iconEl = document.getElementById('session-icon');
                if (iconEl) iconEl.textContent = '📡';
            }
            if (premarketTrend && premarketTrend.textContent.trim() === 'Loading...') {
                premarketTrend.textContent = 'Refresh for data';
                premarketTrend.className = 'h5 text-muted';
            }
        }, 8000);
    }
    
    async loadPremarketAnalysis() {
        const directionEl = document.getElementById('premarket-direction');
        const trendEl = document.getElementById('premarket-trend');
        const priceEl = document.getElementById('premarket-price');
        const changeEl = document.getElementById('premarket-change');
        const outlookEl = document.getElementById('premarket-outlook');
        try {
            const response = await fetch(`/api/premarket-analysis/${this.currentTicker}?_t=${Date.now()}`);
            const data = await response.json();
            if (data.error || !data.trend) {
                if (trendEl) trendEl.textContent = '—';
                if (directionEl) directionEl.textContent = '→';
                if (priceEl) priceEl.textContent = '—';
                if (changeEl) changeEl.textContent = '—';
                if (outlookEl) outlookEl.textContent = 'Refresh for premarket data';
                return;
            }
            if (directionEl) {
                const arrow = data.direction === 'UP' ? '↑' : data.direction === 'DOWN' ? '↓' : '→';
                directionEl.textContent = arrow;
                directionEl.style.color = data.color || '#666';
            }
            if (trendEl) {
                trendEl.textContent = data.trend;
                trendEl.style.color = data.color || '#666';
            }
            if (priceEl) priceEl.textContent = `$${Number(data.current_price).toFixed(2)}`;
            if (changeEl) {
                const sign = data.change >= 0 ? '+' : '';
                changeEl.textContent = `${sign}${Number(data.change).toFixed(2)} (${sign}${Number(data.change_percent).toFixed(2)}%)`;
                changeEl.className = `fw-bold ${data.change >= 0 ? 'text-success' : 'text-danger'}`;
            }
            if (outlookEl) outlookEl.textContent = data.outlook || '';
            const badge = document.getElementById('market-status');
            if (badge && data.session === 'PREMARKET') {
                badge.textContent = 'PRE MARKET';
                badge.className = 'badge bg-info';
            }
        } catch (error) {
            if (trendEl) trendEl.textContent = '—';
            if (directionEl) directionEl.textContent = '→';
            if (priceEl) priceEl.textContent = '—';
            if (changeEl) changeEl.textContent = '—';
            if (outlookEl) outlookEl.textContent = 'Refresh for data';
        }
    }
    
    initFeedbackForm() {
        const submitBtn = document.getElementById('submit-feedback-btn');
        const ratingBtns = document.querySelectorAll('.rating-btn');
        
        let selectedRating = 0;
        
        ratingBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                selectedRating = parseInt(btn.dataset.rating);
                ratingBtns.forEach(b => b.classList.remove('btn-warning', 'active'));
                ratingBtns.forEach(b => {
                    if (parseInt(b.dataset.rating) <= selectedRating) {
                        b.classList.add('btn-warning');
                        b.classList.remove('btn-outline-warning');
                    } else {
                        b.classList.add('btn-outline-warning');
                        b.classList.remove('btn-warning');
                    }
                });
            });
        });
        
        if (submitBtn) {
            submitBtn.addEventListener('click', async () => {
                const category = document.getElementById('feedback-category').value;
                const suggestion = document.getElementById('feedback-suggestion').value;
                const email = document.getElementById('feedback-email').value;
                
                if (!suggestion.trim()) {
                    this.showNotification('Please enter your suggestion', 'warning');
                    return;
                }
                
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="bi bi-hourglass"></i> Sending...';
                
                try {
                    const response = await fetch('/api/beta-feedback', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            category,
                            suggestion,
                            email,
                            rating: selectedRating
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        this.showNotification('Thank you for your feedback! We truly appreciate beta testers like you.', 'success');
                        document.getElementById('feedback-suggestion').value = '';
                        document.getElementById('feedback-email').value = '';
                        selectedRating = 0;
                        ratingBtns.forEach(b => {
                            b.classList.remove('btn-warning');
                            b.classList.add('btn-outline-warning');
                        });
                        bootstrap.Modal.getInstance(document.getElementById('feedbackModal')).hide();
                    } else {
                        this.showNotification(data.error || 'Error submitting feedback', 'danger');
                    }
                } catch (error) {
                    this.showNotification('Error submitting feedback. Please try again.', 'danger');
                }
                
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="bi bi-send"></i> Submit Feedback';
            });
        }
    }
    
    playStartupSound() {
        setTimeout(() => {
            if (this.audioContext) {
                try {
                    const osc = this.audioContext.createOscillator();
                    const gain = this.audioContext.createGain();
                    osc.connect(gain);
                    gain.connect(this.audioContext.destination);
                    
                    osc.type = 'sine';
                    const now = this.audioContext.currentTime;
                    
                    osc.frequency.setValueAtTime(523.25, now);
                    osc.frequency.setValueAtTime(659.25, now + 0.1);
                    osc.frequency.setValueAtTime(783.99, now + 0.2);
                    osc.frequency.setValueAtTime(1046.50, now + 0.3);
                    
                    gain.gain.setValueAtTime(0.3, now);
                    gain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
                    
                    osc.start(now);
                    osc.stop(now + 0.5);
                    
                    console.log('🎵 Trading Signals Active!');
                } catch (e) {
                    console.log('Startup sound requires user interaction first');
                }
            }
        }, 500);
    }
    
    initAudioContext() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.bellSound = new Audio('https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3');
            this.alertSound = new Audio('https://assets.mixkit.co/active_storage/sfx/1337/1337-preview.mp3');
            this.bellSound.volume = this.audioVolume;
            this.alertSound.volume = this.audioVolume;
        } catch (e) {
            console.log('Audio context not available');
        }
    }
    
    enableTradingAlerts() {
        this.alertsEnabled = true;
        if (this.bellSound) this.bellSound.play().then(() => this.bellSound.pause()).catch(() => {});
        if (this.alertSound) this.alertSound.play().then(() => this.alertSound.pause()).catch(() => {});
        const btn = document.getElementById('enable-alerts-btn');
        if (btn) {
            btn.innerHTML = '<i class="bi bi-bell-fill"></i> Alerts Enabled';
            btn.className = 'btn btn-success btn-sm';
        }
        this.showNotification('Trading alerts enabled! You\'ll hear bells at 3:50 PM and 3:54 PM ET.');
        this.requestPushNotificationPermission();
    }
    
    requestPushNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    this.showNotification('Desktop notifications enabled!', 'success');
                }
            });
        }
    }
    
    sendPushNotification(title, body, tag = 'trading-signal') {
        if (!this.alertsEnabled) return;
        if ('Notification' in window && Notification.permission === 'granted') {
            try {
                const notification = new Notification(title, {
                    body: body,
                    icon: '/static/favicon.ico',
                    tag: tag,
                    requireInteraction: true,
                    silent: false
                });
                
                notification.onclick = () => {
                    window.focus();
                    notification.close();
                };
                
                setTimeout(() => notification.close(), 10000);
            } catch (e) {}
        }
    }
    
    showNotification(message, type = 'info') {
        const container = document.getElementById('notification-container') || document.body;
        const toast = document.createElement('div');
        toast.className = `alert alert-${type === 'warning' ? 'warning' : type === 'danger' ? 'danger' : 'info'} position-fixed`;
        toast.style.cssText = 'top: 70px; right: 20px; z-index: 9999; max-width: 350px; animation: fadeIn 0.3s;';
        toast.innerHTML = `<strong>${message}</strong><button type="button" class="btn-close float-end" onclick="this.parentElement.remove()"></button>`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }
    
    speak(text) {
        if (!this.alertsEnabled) return;
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 0.9;
            utterance.pitch = 1;
            utterance.volume = this.audioVolume;
            const voices = window.speechSynthesis.getVoices();
            const preferredVoice = voices.find(v => v.name.includes('Google') || v.name.includes('Female') || v.name.includes('Samantha'));
            if (preferredVoice) utterance.voice = preferredVoice;
            window.speechSynthesis.speak(utterance);
        }
    }
    
    getMotivationalQuote() {
        const quotes = [
            "Focus. Discipline. Execute.",
            "Trust the process. Follow the signals.",
            "Patience pays. Let the trade come to you.",
            "Protect your capital. Live to trade another day.",
            "The trend is your friend.",
            "Cut losers fast. Let winners run.",
            "One good trade at a time.",
            "Stay calm. Trade your plan.",
            "Discipline beats emotion every time.",
            "Small consistent wins build fortunes.",
            "Risk management is your edge.",
            "The best trade might be no trade.",
            "Wait for the setup. Don't chase.",
            "Confidence comes from preparation.",
            "Trade what you see, not what you hope."
        ];
        return quotes[Math.floor(Math.random() * quotes.length)];
    }
    
    playMarketOpenMelody() {
        if (!this.audioContext || !this.alertsEnabled) return;
        try {
            const now = this.audioContext.currentTime;
            const notes = [523.25, 659.25, 783.99, 1046.50];
            notes.forEach((freq, i) => {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now + i * 0.15);
                gain.gain.setValueAtTime(this.audioVolume * 0.3, now + i * 0.15);
                gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.15 + 0.4);
                osc.start(now + i * 0.15);
                osc.stop(now + i * 0.15 + 0.5);
            });
        } catch (e) {}
    }
    
    playLotteryHourMelody() {
        if (!this.audioContext || !this.alertsEnabled) return;
        try {
            const now = this.audioContext.currentTime;
            const notes = [440, 554.37, 659.25, 880, 659.25, 880];
            notes.forEach((freq, i) => {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                osc.type = 'triangle';
                osc.frequency.setValueAtTime(freq, now + i * 0.1);
                gain.gain.setValueAtTime(this.audioVolume * 0.25, now + i * 0.1);
                gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.1 + 0.25);
                osc.start(now + i * 0.1);
                osc.stop(now + i * 0.1 + 0.3);
            });
        } catch (e) {}
    }
    
    playMarketCloseMelody() {
        if (!this.audioContext || !this.alertsEnabled) return;
        try {
            const now = this.audioContext.currentTime;
            const notes = [783.99, 659.25, 523.25, 392.00];
            notes.forEach((freq, i) => {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now + i * 0.2);
                gain.gain.setValueAtTime(this.audioVolume * 0.25, now + i * 0.2);
                gain.gain.exponentialRampToValueAtTime(0.01, now + i * 0.2 + 0.5);
                osc.start(now + i * 0.2);
                osc.stop(now + i * 0.2 + 0.6);
            });
        } catch (e) {}
    }
    
    showEndOfDayCheckIn() {
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.cssText = 'display: block; background: rgba(0,0,0,0.8);';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content bg-dark text-light border-warning">
                    <div class="modal-header border-warning">
                        <h5 class="modal-title"><i class="bi bi-chat-heart"></i> Trading Coach Check-In</h5>
                    </div>
                    <div class="modal-body text-center py-4">
                        <h4 class="mb-4">How was your trading day?</h4>
                        <div class="d-flex justify-content-center gap-3 mb-4">
                            <button class="btn btn-lg btn-outline-success checkin-btn" data-mood="great">
                                <i class="bi bi-emoji-laughing"></i><br>Great!
                            </button>
                            <button class="btn btn-lg btn-outline-warning checkin-btn" data-mood="okay">
                                <i class="bi bi-emoji-neutral"></i><br>Okay
                            </button>
                            <button class="btn btn-lg btn-outline-danger checkin-btn" data-mood="tough">
                                <i class="bi bi-emoji-frown"></i><br>Tough
                            </button>
                        </div>
                        <p class="text-muted mb-0" id="coach-response"></p>
                    </div>
                    <div class="modal-footer border-warning justify-content-center">
                        <button class="btn btn-warning" id="close-checkin">See You Tomorrow!</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        const responses = {
            great: ["Amazing work! Keep that momentum going!", "You're on fire! Consistency is key.", "Excellent! Remember what worked today."],
            okay: ["Every day is a lesson. Tomorrow is a new opportunity.", "Steady progress beats big swings. You're doing fine.", "Review your trades. Small adjustments lead to big results."],
            tough: ["Tough days build tough traders. You've got this.", "Protect your capital. Live to trade another day.", "Step back, breathe. The market will be there tomorrow."]
        };
        
        modal.querySelectorAll('.checkin-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const mood = e.currentTarget.dataset.mood;
                const responseList = responses[mood];
                const response = responseList[Math.floor(Math.random() * responseList.length)];
                document.getElementById('coach-response').textContent = response;
                this.speak(response);
                modal.querySelectorAll('.checkin-btn').forEach(b => b.classList.remove('active'));
                e.currentTarget.classList.add('active');
            });
        });
        
        document.getElementById('close-checkin').addEventListener('click', () => {
            modal.remove();
            this.speak("See you tomorrow. Rest well and come back ready!");
        });
    }
    
    getEasternTime() {
        const now = new Date();
        const etString = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
        return new Date(etString);
    }
    
    checkLotteryHourAlerts() {
        const et = this.getEasternTime();
        const hours = et.getHours();
        const minutes = et.getMinutes();
        const today = et.toDateString();
        
        if (hours === 15 && minutes >= 55) {
            if (!this.lotteryHourActive) {
                this.lotteryHourActive = true;
                this.activateLotteryHourMode();
            }
        } else if (hours === 16 || (hours < 15) || (hours === 15 && minutes < 55)) {
            if (this.lotteryHourActive) {
                this.lotteryHourActive = false;
                this.deactivateLotteryHourMode();
            }
        }
        
        if (hours < 15 || hours >= 16) {
            this.lastLotteryAlert = null;
            this.lastLotteryAlertDate = null;
        }
        
        if (!this.alertsEnabled) return;
        
        const alertKey = `${today}-15:50`;
        if (hours === 15 && minutes === 50 && this.lastLotteryAlert !== alertKey) {
            this.lastLotteryAlert = alertKey;
            this.playLotteryBell();
            this.showNotification('🔔 LOTTERY HOUR in 5 minutes! High momentum trades only.', 'warning');
        }
        
        const alertKey53 = `${today}-15:53`;
        if (hours === 15 && minutes === 53 && this.lastLotteryAlert !== alertKey53) {
            this.lastLotteryAlert = alertKey53;
            this.playLotteryAlert();
            this.showNotification('⚠️ 2 MINUTES to Lottery Hour! Auto-scanning now...', 'danger');
            this.runLotteryHourScan();
        }
        
        const alertKey54 = `${today}-15:54`;
        if (hours === 15 && minutes === 54 && this.lastLotteryAlert !== alertKey54) {
            this.lastLotteryAlert = alertKey54;
            this.runLotteryScan();
            this.speak('Lottery play scan complete! Check your top 3 picks now.');
        }
        
        const alertKey55 = `${today}-15:55`;
        if (hours === 15 && minutes === 55 && this.lastLotteryAlert !== alertKey55) {
            this.lastLotteryAlert = alertKey55;
            this.showNotification('🎰 LOTTERY HOUR IS NOW! Extreme momentum plays only!', 'danger');
            this.speak('Lottery hour is now active. Only high momentum trades.');
        }
        
        const alertKey925 = `${today}-09:25`;
        if (hours === 9 && minutes === 25 && this.lastLotteryAlert !== alertKey925) {
            this.lastLotteryAlert = alertKey925;
            this.playMarketOpenMelody();
            const quote = this.getMotivationalQuote();
            this.showNotification(`🌅 Market opens in 5 minutes! ${quote}`, 'info');
            this.speak(`Good morning trader! The market opens in 5 minutes. Remember: ${quote}. Let's have a great trading day!`);
        }
        
        const alertKey930 = `${today}-09:30`;
        if (hours === 9 && minutes === 30 && this.lastLotteryAlert !== alertKey930) {
            this.lastLotteryAlert = alertKey930;
            this.playMarketOpenMelody();
            this.showNotification('🔔 MARKET IS NOW OPEN! Time to execute!', 'success');
            this.speak("The bell has rung! Market is open. Stay focused, stay disciplined, and trade your plan!");
        }
        
        const alertKey355 = `${today}-15:55`;
        if (hours === 15 && minutes === 55 && this.lastLotteryAlert !== alertKey355) {
            this.lastLotteryAlert = alertKey355;
            this.playLotteryHourMelody();
            this.showNotification('🎰 LOTTERY HOUR! High momentum plays only!', 'danger');
            this.speak("Lottery hour is now active! Only high conviction trades. Protect your gains!");
        }
        
        const alertKey400 = `${today}-16:00`;
        if (hours === 16 && minutes === 0 && this.lastLotteryAlert !== alertKey400) {
            this.lastLotteryAlert = alertKey400;
            this.playMarketCloseMelody();
            this.showNotification('🔔 MARKET IS NOW CLOSED', 'warning');
            this.speak("The closing bell has rung. Great work today! Take a moment to review your trades.");
            setTimeout(() => this.showEndOfDayCheckIn(), 3000);
        }
    }
    
    playLotteryBell() {
        if (this.bellSound && this.alertsEnabled) {
            this.bellSound.currentTime = 0;
            this.bellSound.volume = this.audioVolume;
            this.bellSound.play().catch(() => {});
        }
    }
    
    playLotteryAlert() {
        if (this.audioContext && this.alertsEnabled) {
            try {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                
                osc.type = 'sawtooth';
                const now = this.audioContext.currentTime;
                
                osc.frequency.setValueAtTime(150, now);
                osc.frequency.setValueAtTime(120, now + 0.1);
                osc.frequency.setValueAtTime(150, now + 0.2);
                osc.frequency.setValueAtTime(120, now + 0.3);
                osc.frequency.setValueAtTime(150, now + 0.4);
                
                gain.gain.setValueAtTime(this.audioVolume * 0.4, now);
                gain.gain.setValueAtTime(this.audioVolume * 0.2, now + 0.1);
                gain.gain.setValueAtTime(this.audioVolume * 0.4, now + 0.2);
                gain.gain.setValueAtTime(this.audioVolume * 0.2, now + 0.3);
                gain.gain.setValueAtTime(this.audioVolume * 0.4, now + 0.4);
                gain.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
                
                osc.start(now);
                osc.stop(now + 0.5);
            } catch (e) {}
        }
    }
    
    playStrongBuyAlert() {
        if (this.alertsEnabled && this.alertSound) {
            this.alertSound.currentTime = 0;
            this.alertSound.volume = this.audioVolume;
            this.alertSound.play().catch(() => {});
        }
        this.playBuyAlert();
    }
    
    /** Dramatic alarm for TRUE trend reversal — impossible to miss */
    playReversalAlert() {
        if (!this.audioContext || !this.audioEnabled) return;
        try {
            const ctx = this.audioContext;
            const now = ctx.currentTime;
            const gainNode = ctx.createGain();
            gainNode.connect(ctx.destination);
            gainNode.gain.setValueAtTime(this.audioVolume * 0.6, now);
            const playBeep = (t, freq, dur) => {
                const osc = ctx.createOscillator();
                osc.type = 'square';
                osc.frequency.setValueAtTime(freq, t);
                osc.connect(gainNode);
                osc.start(t);
                osc.stop(t + dur);
            };
            playBeep(now, 440, 0.15);
            playBeep(now + 0.18, 440, 0.15);
            playBeep(now + 0.36, 350, 0.2);
            playBeep(now + 0.6, 350, 0.2);
            playBeep(now + 0.84, 280, 0.25);
            gainNode.gain.setValueAtTime(this.audioVolume * 0.6, now);
            gainNode.gain.exponentialRampToValueAtTime(0.01, now + 1.2);
        } catch (e) {}
    }
    
    async loadLastHourScan() {
        const panel = document.getElementById('last-hour-panel');
        const playsEl = document.getElementById('last-hour-plays');
        const timeEl = document.getElementById('last-hour-scan-time');
        if (!panel || !playsEl) return;
        try {
            const res = await fetch('/api/last-hour-scan?_t=' + Date.now());
            const data = await res.json();
            if (!data.success) {
                panel.classList.add('d-none');
                return;
            }
            if (!data.strongest_plays || data.strongest_plays.length === 0) {
                if (data.in_last_hour_window || data.message) {
                    const msg = data.message || 'No strong plays in last hour yet.';
                    playsEl.innerHTML = `<span class="text-muted small">${msg}</span>`;
                    panel.classList.remove('d-none');
                } else {
                    panel.classList.add('d-none');
                }
                if (timeEl) timeEl.textContent = data.scan_time || '';
                return;
            }
            if (data.in_last_hour_window) panel.classList.remove('d-none');
            if (timeEl) timeEl.textContent = data.scan_time || '';
            playsEl.innerHTML = data.strongest_plays.map(p => {
                    const isCall = p.play === 'CALL';
                    const btnClass = isCall ? 'btn-success' : 'btn-danger';
                    const safeReason = (p.reason || '').replace(/"/g, '&quot;');
return `<button type="button" class="btn btn-sm ${btnClass} last-hour-play" data-symbol="${p.symbol}" data-play="${p.play}" title="${safeReason}">${p.symbol} strong ${p.play} <span class="badge bg-dark">${p.strength_score}</span></button>`;
                }).join('');
                playsEl.querySelectorAll('.last-hour-play').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const sym = btn.getAttribute('data-symbol');
                        if (!sym) return;
                        const tickerSelect = document.getElementById('ticker-select');
                        if (tickerSelect) tickerSelect.value = sym;
                        this.currentTicker = sym;
                        this.lastReversalKey = null;
                        if (this.socket) this.socket.emit('subscribe', { symbol: sym });
                        this.refreshData();
                    });
                });
            }
        } catch (e) {
            if (panel) panel.classList.add('d-none');
        }
    }

    handleTrendReversalAlert(data) {
        const banner = document.getElementById('trend-reversal-banner');
        if (!banner) return;
        if (!data.trend_reversal_detected || !data.trend_reversal_direction) {
            banner.classList.add('d-none');
            return;
        }
        const key = (this.currentTicker || '') + (data.trend_reversal_direction || '');
        const textEl = document.getElementById('trend-reversal-text');
        const reasonEl = document.getElementById('trend-reversal-reason');
        const dir = data.trend_reversal_direction;
        const label = dir === 'BULLISH_TO_BEARISH' ? '⚠️ TREND REVERSAL — BULLISH TO BEARISH' : '⚠️ TREND REVERSAL — BEARISH TO BULLISH';
        if (textEl) textEl.textContent = label + ' ' + (this.currentTicker || '');
        if (reasonEl) {
            reasonEl.textContent = data.trend_reversal_reason || 'Structure break or multi-timeframe flip.';
            reasonEl.classList.remove('d-none');
        }
        banner.classList.remove('d-none');
        const isNewReversal = key !== this.lastReversalKey;
        if (isNewReversal && this.audioEnabled) {
            this.playReversalAlert();
            this.lastReversalKey = key;
            if (this.sendPushNotification) {
                this.sendPushNotification('TREND REVERSAL — ' + this.currentTicker, data.trend_reversal_reason || 'The trend is changing. Beware.', 'reversal');
            }
        }
    }

    activateLotteryHourMode() {
        const panel = document.getElementById('main-signal-panel');
        if (panel) panel.classList.add('lottery-hour-mode');
        
        const banner = document.getElementById('lottery-hour-banner');
        if (banner) banner.style.display = 'block';
        
        const lotteryPanel = document.getElementById('lottery-picks-panel');
        if (lotteryPanel) lotteryPanel.style.display = 'block';
        
        this.showNotification('🎰 LOTTERY HOUR ACTIVE - Extreme moves possible!', 'warning');
    }
    
    deactivateLotteryHourMode() {
        const panel = document.getElementById('main-signal-panel');
        if (panel) panel.classList.remove('lottery-hour-mode');
        
        const banner = document.getElementById('lottery-hour-banner');
        if (banner) banner.style.display = 'none';
    }
    
    async runLotteryHourScan() {
        const extendedHoursTickers = ['SPY', 'QQQ', 'GLD', 'SLV', 'IWM', 'DIA', 'XLF', 'XLE', 'TLT'];
        const allTickers = this.getSelectedScannerTickers();
        
        if (allTickers.length === 0) {
            this.showNotification('No tickers selected for lottery scan!', 'warning');
            return;
        }
        
        this.showNotification(`🎰 LOTTERY SCAN: Analyzing ${allTickers.length} tickers...`, 'warning');
        
        const results = [];
        for (const ticker of allTickers) {
            try {
                const response = await fetch(`/api/comprehensive-analysis/${ticker}`);
                if (response.ok) {
                    const data = await response.json();
                    const isExtended = extendedHoursTickers.includes(ticker.toUpperCase());
                    const closeTime = isExtended ? '4:15 PM' : '4:00 PM';
                    
                    results.push({
                        ticker,
                        signal: data.main_signal,
                        strength: data.strength || 50,
                        price: data.current_price,
                        summary: data.summary,
                        isExtended,
                        closeTime,
                        reasons: data.reasons || []
                    });
                }
            } catch (e) {}
        }
        
        results.sort((a, b) => {
            const aScore = this.getLotteryScore(a);
            const bScore = this.getLotteryScore(b);
            return bScore - aScore;
        });
        
        this.displayLotteryResults(results);
    }
    
    getLotteryScore(result) {
        let score = result.strength;
        if (result.signal === 'STRONG BUY' || result.signal === 'STRONG SELL') score += 30;
        else if (result.signal === 'BUY' || result.signal === 'SELL') score += 15;
        if (result.isExtended) score += 10;
        return score;
    }
    
    async runLotteryScan() {
        const panel = document.getElementById('lottery-picks-panel');
        const content = document.getElementById('lottery-picks-content');
        
        if (panel) panel.style.display = 'block';
        if (content) {
            content.innerHTML = `
                <div class="text-center text-warning py-3">
                    <i class="bi bi-arrow-clockwise spin"></i> Scanning for lottery plays...
                </div>
            `;
        }
        
        try {
            const response = await fetch('/api/lottery-scan');
            const data = await response.json();
            
            if (data.success && data.lottery_picks.length > 0) {
                const picksHtml = data.lottery_picks.map((pick, i) => {
                    const isCall = pick.option_type === 'CALL';
                    const isHot = pick.momentum_score >= 60;
                    const glowClass = isCall ? 'lottery-glow-green' : 'lottery-glow-red';
                    const hotClass = isHot ? 'lottery-hot' : '';
                    const priceChange = pick.price_change || 0;
                    const changeDisplay = priceChange !== 0 ? `<span class="${priceChange >= 0 ? 'text-success' : 'text-danger'}">${priceChange >= 0 ? '+' : ''}${priceChange.toFixed(2)}%</span>` : '';
                    return `
                    <div class="lottery-pick-card ${glowClass} ${hotClass} ${i === 0 ? 'lottery-top-pick' : ''} mb-2">
                        <div class="lottery-pick-header">
                            <div class="d-flex align-items-center gap-2">
                                <span class="lottery-rank ${i === 0 ? 'top' : ''}">#${i+1}</span>
                                <span class="lottery-symbol">${pick.symbol}</span>
                                <span class="lottery-direction ${isCall ? 'call' : 'put'}">
                                    <i class="bi bi-arrow-${isCall ? 'up' : 'down'}-circle-fill"></i> ${pick.option_type}
                                </span>
                            </div>
                            <div class="lottery-price">
                                $${pick.current_price} ${changeDisplay}
                            </div>
                        </div>
                        <div class="lottery-pick-body">
                            <div class="lottery-strike">
                                <span class="label">Strike:</span> $${pick.suggested_strike}
                                <span class="lottery-target ms-2">${pick.target_move}</span>
                            </div>
                            <div class="lottery-reason">${pick.reason}</div>
                        </div>
                        <div class="lottery-pick-footer">
                            <span class="lottery-stat"><i class="bi bi-bar-chart-fill"></i> ${pick.volume_ratio}x Vol</span>
                            <span class="lottery-stat"><i class="bi bi-speedometer2"></i> RSI ${pick.rsi}</span>
                            <span class="lottery-score">${pick.momentum_score} pts</span>
                        </div>
                    </div>
                `}).join('');
                
                content.innerHTML = `
                    <div class="mb-2 text-center">
                        <small class="text-muted">Scanned at ${data.scan_time} | ${data.total_scanned} tickers checked</small>
                    </div>
                    ${picksHtml}
                `;
                
                this.showNotification(`🎰 Found ${data.lottery_picks.length} lottery plays!`, 'warning');
            } else if (!data.success) {
                content.innerHTML = `
                    <div class="text-center text-danger py-3">
                        <i class="bi bi-exclamation-triangle"></i> Scan failed.
                        <br><small>${(data.error || '').replace(/</g, '&lt;') || 'Try again later.'}</small>
                    </div>
                `;
            } else {
                const msg = (data.total_scanned === 0 && data.message) ? data.message : 'No high-probability plays found right now.';
                const hint = data.total_scanned === 0 ? 'Add tickers to your watchlist and try again.' : 'Check back closer to market close.';
                content.innerHTML = `
                    <div class="text-center text-muted py-3">
                        <i class="bi bi-${data.total_scanned === 0 ? 'list-ul' : 'emoji-frown'}"></i> ${msg}
                        <br><small>${hint}</small>
                    </div>
                `;
            }
        } catch (error) {
            content.innerHTML = `
                <div class="text-center text-danger py-3">
                    <i class="bi bi-exclamation-triangle"></i> Error scanning. Try again.
                </div>
            `;
        }
    }
    
    async runMarketOpenScan(phase = '5min') {
        const content = document.getElementById('market-open-content');
        const phaseLabel = document.getElementById('market-open-phase');
        
        const phaseLabels = {
            'premarket': 'Pre-Market Analysis',
            '5min': 'First 5 Minutes',
            '15min': 'First 15 Minutes',
            '30min': 'First 30 Minutes'
        };
        
        if (phaseLabel) {
            phaseLabel.innerHTML = `<span class="badge bg-info"><i class="bi bi-arrow-clockwise spin"></i> Scanning ${phaseLabels[phase]}...</span>`;
        }
        
        if (content) {
            content.innerHTML = `
                <div class="text-center text-info py-3">
                    <i class="bi bi-arrow-clockwise spin"></i> Finding top trending stocks...
                </div>
            `;
        }
        
        try {
            const response = await fetch(`/api/market-open-scan?phase=${phase}`);
            const data = await response.json();
            
            if (phaseLabel) {
                phaseLabel.innerHTML = `<span class="badge bg-success">${data.phase_label || phaseLabels[phase]}</span>`;
            }
            
            if (data.success && data.trending_picks.length > 0) {
                const picksHtml = data.trending_picks.map((pick, i) => {
                    const isCall = pick.option_type === 'CALL';
                    const isHot = pick.trend_score >= 50;
                    const glowClass = isCall ? 'lottery-glow-green' : 'lottery-glow-red';
                    const hotClass = isHot ? 'lottery-hot' : '';
                    const fakeoutClass = pick.is_fakeout ? 'fakeout-warning' : '';
                    
                    return `
                    <div class="lottery-pick-card ${glowClass} ${hotClass} ${fakeoutClass} ${i === 0 ? 'lottery-top-pick' : ''} mb-2">
                        <div class="lottery-pick-header">
                            <div class="d-flex align-items-center gap-2">
                                <span class="lottery-rank ${i === 0 ? 'top' : ''}">#${i+1}</span>
                                <span class="lottery-symbol">${pick.symbol}</span>
                                <span class="lottery-direction ${isCall ? 'call' : 'put'}">
                                    <i class="bi bi-arrow-${isCall ? 'up' : 'down'}-circle-fill"></i> ${pick.option_type}
                                </span>
                            </div>
                            <div class="lottery-price">
                                $${pick.current_price} 
                                <span class="${pick.price_change_pct >= 0 ? 'text-success' : 'text-danger'}">
                                    ${pick.price_change_pct >= 0 ? '+' : ''}${pick.price_change_pct}%
                                </span>
                            </div>
                        </div>
                        <div class="lottery-pick-body">
                            <div class="lottery-reason">${pick.reason}</div>
                            ${pick.is_fakeout ? `<div class="fakeout-alert"><i class="bi bi-exclamation-triangle"></i> ${pick.fakeout_warning}</div>` : ''}
                        </div>
                        <div class="lottery-pick-footer">
                            <span class="lottery-stat"><i class="bi bi-bar-chart-fill"></i> ${pick.volume_ratio}x Vol</span>
                            <span class="lottery-stat"><i class="bi bi-speedometer2"></i> RSI ${pick.rsi}</span>
                            <span class="lottery-stat"><i class="bi bi-graph-up"></i> ${pick.consistency >= 15 ? 'Strong' : 'Building'}</span>
                            <span class="lottery-score">${pick.trend_score} pts</span>
                        </div>
                    </div>
                `}).join('');
                
                content.innerHTML = `
                    <div class="mb-2 text-center">
                        <small class="text-muted">Scanned at ${data.scan_time} | ${data.total_scanned} tickers</small>
                    </div>
                    ${picksHtml}
                `;
                
                this.showNotification(`📈 Found ${data.trending_picks.length} trending stocks!`, 'info');
            } else {
                content.innerHTML = `
                    <div class="text-center text-muted py-3">
                        <i class="bi bi-search"></i> No strong trends found yet.
                        <br><small>Market may be consolidating.</small>
                    </div>
                `;
            }
        } catch (error) {
            content.innerHTML = `
                <div class="text-center text-danger py-3">
                    <i class="bi bi-exclamation-triangle"></i> Error scanning.
                </div>
            `;
        }
    }
    
    checkMarketOpenAlerts() {
        const et = this.getEasternTime();
        const hours = et.getHours();
        const minutes = et.getMinutes();
        const today = et.toDateString();
        
        if (!this.alertsEnabled) return;
        
        const alertKey925 = `open-${today}-09:25`;
        if (hours === 9 && minutes === 25 && this.lastMarketOpenAlert !== alertKey925) {
            this.lastMarketOpenAlert = alertKey925;
            this.runMarketOpenScan('premarket');
            this.showNotification('🌅 Pre-market scan complete! Top movers identified.', 'info');
        }
        
        const alertKey935 = `open-${today}-09:35`;
        if (hours === 9 && minutes === 35 && this.lastMarketOpenAlert !== alertKey935) {
            this.lastMarketOpenAlert = alertKey935;
            this.runMarketOpenScan('5min');
            this.speak('First 5 minute scan complete. Checking for true trends.');
            this.showNotification('⏱️ 5-Minute scan! Initial trends forming...', 'info');
        }
        
        const alertKey945 = `open-${today}-09:45`;
        if (hours === 9 && minutes === 45 && this.lastMarketOpenAlert !== alertKey945) {
            this.lastMarketOpenAlert = alertKey945;
            this.runMarketOpenScan('15min');
            this.speak('15 minute scan complete. Trend confirmation improving.');
            this.showNotification('📊 15-Minute scan! Trends solidifying...', 'info');
        }
        
        const alertKey1000 = `open-${today}-10:00`;
        if (hours === 10 && minutes === 0 && this.lastMarketOpenAlert !== alertKey1000) {
            this.lastMarketOpenAlert = alertKey1000;
            this.runMarketOpenScan('30min');
            this.speak('30 minute scan complete. True trends confirmed.');
            this.showNotification('✅ 30-Minute scan! True trends identified!', 'success');
        }
    }
    
    initMarketOpenScanner() {
        document.querySelectorAll('.open-scan-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.open-scan-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                const phase = e.target.dataset.phase;
                this.runMarketOpenScan(phase);
            });
        });
        
        setInterval(() => this.checkMarketOpenAlerts(), 30000);
        this.lastMarketOpenAlert = null;
    }
    
    displayLotteryResults(results) {
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.id = 'lotteryResultsModal';
        modal.style.cssText = 'display: block; background: rgba(0,0,0,0.8);';
        
        const topPicks = results.slice(0, 5);
        const extendedPicks = results.filter(r => r.isExtended).slice(0, 3);
        
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content bg-dark text-light">
                    <div class="modal-header bg-warning text-dark">
                        <h5 class="modal-title"><i class="bi bi-lightning-charge-fill"></i> LOTTERY HOUR PICKS</h5>
                        <button type="button" class="btn-close" onclick="document.getElementById('lotteryResultsModal').remove()"></button>
                    </div>
                    <div class="modal-body">
                        <div class="alert alert-warning mb-3">
                            <strong>⚡ Top ${topPicks.length} Momentum Plays</strong> - Ranked by signal strength
                        </div>
                        <div class="row g-2 mb-4">
                            ${topPicks.map((r, i) => `
                                <div class="col-12">
                                    <div class="card ${r.signal.includes('BUY') ? 'border-success' : r.signal.includes('SELL') ? 'border-danger' : 'border-secondary'}" style="background: #1a1a2e;">
                                        <div class="card-body py-2">
                                            <div class="d-flex justify-content-between align-items-center">
                                                <div>
                                                    <span class="badge ${i === 0 ? 'bg-warning text-dark' : 'bg-secondary'} me-2">#${i+1}</span>
                                                    <strong class="fs-5">${r.ticker}</strong>
                                                    ${r.isExtended ? '<span class="badge bg-info ms-2">Until 4:15</span>' : '<span class="badge bg-secondary ms-2">Closes 4:00</span>'}
                                                </div>
                                                <div class="text-end">
                                                    <span class="badge ${r.signal.includes('BUY') ? 'bg-success' : r.signal.includes('SELL') ? 'bg-danger' : 'bg-warning'} fs-6">${r.signal}</span>
                                                    <div class="small text-muted">$${r.price?.toFixed(2) || 'N/A'} | ${r.strength}%</div>
                                                </div>
                                            </div>
                                            <div class="small text-light mt-1">${r.summary || ''}</div>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        ${extendedPicks.length > 0 ? `
                            <div class="alert alert-info">
                                <strong>🕓 Extended Hours (4:15 PM close):</strong> ${extendedPicks.map(r => r.ticker).join(', ')}
                            </div>
                        ` : ''}
                        <div class="alert alert-danger">
                            <i class="bi bi-exclamation-triangle-fill"></i> <strong>WARNING:</strong> Wide bid-ask spreads! Check spreads before entering.
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-warning" onclick="document.getElementById('lotteryResultsModal').remove()">Got it!</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        this.playLotteryBell();
    }
    
    startLotteryHourTimer() {
        setInterval(() => this.checkLotteryHourAlerts(), 30000);
        this.checkLotteryHourAlerts();
    }
    
    initSocket() {
        this.socket = io();
        
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.socket.emit('subscribe', { symbol: this.currentTicker });
        });
        
        this.socket.on('price_update', (data) => {
            if (data.symbol === this.currentTicker) this.lastPrice = data.price;
            // BYPASS: only loadTickerCardQuote may touch price card
        });
        
        this.socket.on('new_signal', (signal) => {
            this.addSignalToFeed(signal);
            if (this.audioEnabled && signal.entry_alert) {
                const isNewSignal = !this.lastSignal || this.lastSignal.type !== signal.signal_type;
                if (isNewSignal) {
                    this.playAlert(signal.signal_type);
                    this.lastSignal = { type: signal.signal_type, time: Date.now() };
                }
            }
        });
    }
    
    initChart() {
        const ctx = document.getElementById('price-chart');
        if (!ctx) return;
        
        this.chartCanvas = ctx;
        this.createLineChart();
        this.initVolumeChart();
    }
    
    initVolumeChart() {
        const volumeCtx = document.getElementById('volume-chart');
        if (!volumeCtx) return;
        
        this.volumeCanvas = volumeCtx;
        this.volumeChart = new Chart(volumeCtx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Volume',
                    data: [],
                    backgroundColor: [],
                    borderColor: [],
                    borderWidth: 1,
                    borderRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const vol = ctx.raw;
                                if (vol >= 1000000) return `Vol: ${(vol/1000000).toFixed(1)}M`;
                                if (vol >= 1000) return `Vol: ${(vol/1000).toFixed(0)}K`;
                                return `Vol: ${vol}`;
                            }
                        }
                    }
                },
                scales: {
                    x: { display: false },
                    y: { display: false }
                }
            }
        });
    }
    
    updateVolumeChart(volumes, closes, opens) {
        if (!this.volumeChart || !volumes || volumes.length === 0) return;
        
        const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
        const maxVolume = Math.max(...volumes);
        
        const bgColors = [];
        const borderColors = [];
        let hasSpike = false;
        let spikeCount = 0;
        
        for (let i = 0; i < volumes.length; i++) {
            const vol = volumes[i];
            const ratio = vol / avgVolume;
            const isBullish = closes[i] >= opens[i];
            
            if (ratio >= 2.5) {
                hasSpike = true;
                spikeCount++;
                if (isBullish) {
                    bgColors.push('rgba(0, 255, 128, 0.95)');
                    borderColors.push('#00ff80');
                } else {
                    bgColors.push('rgba(255, 60, 60, 0.95)');
                    borderColors.push('#ff3c3c');
                }
            } else if (ratio >= 1.5) {
                if (isBullish) {
                    bgColors.push('rgba(0, 230, 118, 0.8)');
                    borderColors.push('#00e676');
                } else {
                    bgColors.push('rgba(255, 82, 82, 0.8)');
                    borderColors.push('#ff5252');
                }
            } else if (ratio >= 1.2) {
                if (isBullish) {
                    bgColors.push('rgba(0, 200, 100, 0.6)');
                    borderColors.push('#00c864');
                } else {
                    bgColors.push('rgba(255, 100, 100, 0.6)');
                    borderColors.push('#ff6464');
                }
            } else {
                if (isBullish) {
                    bgColors.push('rgba(100, 149, 237, 0.4)');
                    borderColors.push('#6495ed');
                } else {
                    bgColors.push('rgba(150, 130, 200, 0.4)');
                    borderColors.push('#9682c8');
                }
            }
        }
        
        this.volumeChart.data.datasets[0].data = volumes;
        this.volumeChart.data.datasets[0].backgroundColor = bgColors;
        this.volumeChart.data.datasets[0].borderColor = borderColors;
        this.volumeChart.data.labels = new Array(volumes.length).fill('');
        this.volumeChart.update('none');
        
        const spikeAlert = document.getElementById('volume-spike-alert');
        if (spikeAlert) {
            if (spikeCount >= 3 || (hasSpike && volumes[volumes.length - 1] / avgVolume >= 2)) {
                spikeAlert.style.display = 'block';
                this.addVolumeGlow();
            } else {
                spikeAlert.style.display = 'none';
                this.removeVolumeGlow();
            }
        }
    }
    
    addVolumeGlow() {
        const container = document.querySelector('.volume-chart-container');
        if (container) {
            container.style.boxShadow = '0 0 20px rgba(255, 165, 0, 0.6), 0 0 40px rgba(255, 69, 0, 0.3)';
            container.style.transition = 'box-shadow 0.3s ease';
        }
    }
    
    removeVolumeGlow() {
        const container = document.querySelector('.volume-chart-container');
        if (container) {
            container.style.boxShadow = 'none';
        }
    }
    
    createLineChart() {
        if (this.chart) this.chart.destroy();
        
        this.chart = new Chart(this.chartCanvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    { label: 'Price', data: [], borderColor: '#4dabf7', backgroundColor: 'rgba(77, 171, 247, 0.1)', borderWidth: 2, fill: true, tension: 0.1, pointRadius: 0, yAxisID: 'y' },
                    { label: 'EMA 13', data: [], borderColor: '#FCD34D', borderWidth: 1.5, fill: false, pointRadius: 0, hidden: false, yAxisID: 'y' },
                    { label: 'EMA 48', data: [], borderColor: '#FB923C', borderWidth: 1.5, fill: false, pointRadius: 0, hidden: false, yAxisID: 'y' },
                    { label: 'EMA 200', data: [], borderColor: '#C084FC', borderWidth: 1.5, fill: false, pointRadius: 0, hidden: false, yAxisID: 'y' },
                    { label: 'Support', data: [], borderColor: 'rgba(76, 175, 80, 0.7)', borderWidth: 1, borderDash: [5, 5], fill: false, pointRadius: 0, yAxisID: 'y' },
                    { label: 'Resistance', data: [], borderColor: 'rgba(244, 67, 54, 0.7)', borderWidth: 1, borderDash: [5, 5], fill: false, pointRadius: 0, yAxisID: 'y' },
                    { label: 'RSI', data: [], borderColor: '#22C55E', borderWidth: 2, fill: false, pointRadius: 0, yAxisID: 'rsi', borderDash: [] },
                    { label: 'RSI 30', data: [], borderColor: 'rgba(34, 197, 94, 0.3)', borderWidth: 1, borderDash: [3, 3], fill: false, pointRadius: 0, yAxisID: 'rsi' },
                    { label: 'RSI 70', data: [], borderColor: 'rgba(239, 68, 68, 0.3)', borderWidth: 1, borderDash: [3, 3], fill: false, pointRadius: 0, yAxisID: 'rsi' }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { intersect: false, mode: 'index' },
                plugins: { 
                    legend: { display: false },
                    tooltip: { enabled: window.innerWidth > 768 }
                },
                scales: {
                    x: { display: true, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', maxTicksLimit: 8 } },
                    y: { display: true, position: 'left', grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888' } },
                    rsi: { display: true, position: 'right', min: 0, max: 100, grid: { display: false }, ticks: { color: '#22C55E', stepSize: 30 }, title: { display: true, text: 'RSI', color: '#22C55E' } }
                }
            }
        });
    }
    
    createCandlestickChart() {
        if (this.chart) this.chart.destroy();
        
        const config = this.TIMEFRAME_CONFIG[this.currentInterval] || this.TIMEFRAME_CONFIG['5m'];
        
        this.chart = new Chart(this.chartCanvas.getContext('2d'), {
            type: 'candlestick',
            data: {
                datasets: [
                    { 
                        label: 'Price', 
                        data: [], 
                        color: { up: '#00e676', down: '#ff5252', unchanged: '#888888' },
                        barThickness: config.barThickness,
                        maxBarThickness: config.barThickness + 4
                    },
                    { type: 'line', label: 'EMA 13', data: [], borderColor: '#FCD34D', borderWidth: 1.5, fill: false, pointRadius: 0 },
                    { type: 'line', label: 'EMA 48', data: [], borderColor: '#FB923C', borderWidth: 1.5, fill: false, pointRadius: 0 },
                    { type: 'line', label: 'EMA 200', data: [], borderColor: '#C084FC', borderWidth: 1.5, fill: false, pointRadius: 0 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { 
                    legend: { display: false },
                    tooltip: { enabled: window.innerWidth > 768 }
                },
                scales: {
                    x: { 
                        type: 'timeseries', 
                        time: { unit: config.timeUnit, stepSize: config.stepSize }, 
                        grid: { color: 'rgba(255, 255, 255, 0.1)' }, 
                        ticks: { color: '#888', maxTicksLimit: 8 } 
                    },
                    y: { display: true, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888' } }
                }
            }
        });
    }
    
    async loadTickers() {
        const select = document.getElementById('ticker-select');
        const defaultSymbols = [{ symbol: 'SPY' }, { symbol: 'QQQ' }, { symbol: 'AAPL' }, { symbol: 'TSLA' }, { symbol: 'NVDA' }];
        const normalize = (list) => {
            if (!Array.isArray(list)) return defaultSymbols;
            return list.map(t => {
                const sym = (t && (t.symbol || t)) ? String(t.symbol || t).trim().toUpperCase() : '';
                return sym ? { symbol: sym } : null;
            }).filter(Boolean);
        };
        if (!select) {
            this.currentTicker = 'SPY';
            this.clearLoadingState();
            return;
        }
        if (select.options.length === 0) {
            const opt = document.createElement('option');
            opt.value = 'SPY';
            opt.textContent = 'SPY';
            select.appendChild(opt);
            this.currentTicker = 'SPY';
            select.value = 'SPY';
        }
        let tickers = [];
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000);
            const response = await fetch('/api/tickers', { signal: controller.signal });
            clearTimeout(timeoutId);
            if (response.ok) {
                const raw = await response.json();
                tickers = normalize(raw);
            }
            if (tickers.length === 0) tickers = defaultSymbols;
        } catch (error) {
            console.warn('Tickers load failed, using defaults:', error);
            tickers = defaultSymbols;
        }
        tickers = tickers.length ? tickers : defaultSymbols;
        const savedSelection = localStorage.getItem('scannerTickerSelection');
        let savedObj = {};
        try { if (savedSelection) savedObj = JSON.parse(savedSelection); } catch (e) {}
        this.scannerTickerSelection = {};
        select.innerHTML = '';
        tickers.forEach(ticker => {
            const sym = ticker.symbol || '';
            if (!sym) return;
            const option = document.createElement('option');
            option.value = sym;
            option.textContent = sym;
            select.appendChild(option);
            this.tickerSelection[sym] = true;
            this.scannerTickerSelection[sym] = savedObj[sym] !== false;
        });
        if (select.options.length === 0) {
            const opt = document.createElement('option');
            opt.value = 'SPY';
            opt.textContent = 'SPY';
            select.appendChild(opt);
            tickers = [{ symbol: 'SPY' }];
        }
        const firstSym = (tickers[0] && tickers[0].symbol) || 'SPY';
        this.currentTicker = firstSym;
        if (select.options.length) {
            select.value = firstSym;
            this.currentTicker = select.value || firstSym;
        }
        this.updateCoachPlaceholder();
        try { this.renderScannerTickerList(tickers); } catch (e) { console.warn('renderScannerTickerList', e); }
        try { this.renderBodyScannerGrid(tickers); } catch (e) { console.warn('renderBodyScannerGrid', e); }
        this.updateNavBadge();
        this.updateAllScanCounts();
        this.clearLoadingState();
    }
    
    renderBodyScannerGrid(tickers) {
        const container = document.getElementById('body-ticker-grid');
        if (!container) return;
        
        container.innerHTML = '';
        
        tickers.forEach(ticker => {
            const isSelected = this.scannerTickerSelection[ticker.symbol] !== false;
            const item = document.createElement('div');
            item.className = `scanner-body-item ${isSelected ? 'selected' : 'dimmed'}`;
            item.dataset.symbol = ticker.symbol;
            item.innerHTML = `
                <div class="cb"><i class="bi bi-check"></i></div>
                <span class="sym">${ticker.symbol}</span>
                <span class="scan-status">${isSelected ? 'Scanning' : 'Skip'}</span>
            `;
            item.addEventListener('click', () => this.toggleBodyTicker(ticker.symbol));
            container.appendChild(item);
        });
        
        this.updateAllScanCounts();
    }
    
    toggleBodyTicker(symbol) {
        this.scannerTickerSelection[symbol] = !this.scannerTickerSelection[symbol];
        const isSelected = this.scannerTickerSelection[symbol];
        
        const bodyItem = document.querySelector(`#body-ticker-grid .scanner-body-item[data-symbol="${symbol}"]`);
        if (bodyItem) {
            bodyItem.classList.toggle('selected', isSelected);
            bodyItem.classList.toggle('dimmed', !isSelected);
            bodyItem.querySelector('.scan-status').textContent = isSelected ? 'Scanning' : 'Skip';
        }
        
        const scannerItem = document.querySelector(`.scanner-ticker-item[data-symbol="${symbol}"]`);
        if (scannerItem) {
            scannerItem.classList.toggle('selected', isSelected);
            scannerItem.classList.toggle('dimmed', !isSelected);
        }
        
        const modalItem = document.querySelector(`#modal-ticker-list .scanner-modal-item[data-symbol="${symbol}"]`);
        if (modalItem) {
            modalItem.classList.toggle('selected', isSelected);
            modalItem.classList.toggle('dimmed', !isSelected);
        }
        
        this.saveScannerSelection();
        this.updateAllScanCounts();
    }
    
    bodySelectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = true;
        });
        
        document.querySelectorAll('#body-ticker-grid .scanner-body-item').forEach(item => {
            item.classList.add('selected');
            item.classList.remove('dimmed');
            item.querySelector('.scan-status').textContent = 'Scanning';
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.add('selected');
            item.classList.remove('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateAllScanCounts();
    }
    
    bodyDeselectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = false;
        });
        
        document.querySelectorAll('#body-ticker-grid .scanner-body-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.add('dimmed');
            item.querySelector('.scan-status').textContent = 'Skip';
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.add('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateAllScanCounts();
    }
    
    async runBodyScan() {
        const selected = Object.entries(this.scannerTickerSelection)
            .filter(([_, v]) => v)
            .map(([symbol]) => symbol);
        
        if (selected.length === 0) {
            alert('Please select at least 1 ticker to scan');
            return;
        }
        
        const scanBtn = document.getElementById('body-scan-btn');
        const scanBtnText = document.getElementById('body-scan-btn-text');
        const scanStatus = document.getElementById('body-scan-status');
        
        if (scanBtn) scanBtn.disabled = true;
        if (scanBtnText) scanBtnText.textContent = `Scanning ${selected.length}...`;
        if (scanStatus) {
            scanStatus.style.display = 'block';
            scanStatus.innerHTML = `<i class="bi bi-hourglass-split"></i> Scanning ${selected.join(', ')}...`;
        }
        
        const bullishOnly = document.getElementById('body-filter-bullish')?.checked || false;
        const bearishOnly = document.getElementById('body-filter-bearish')?.checked || false;
        const highConfidence = document.getElementById('body-filter-high')?.checked || false;
        
        try {
            const response = await fetch('/api/scan-top-10', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    tickers: selected,
                    bullish_only: bullishOnly,
                    bearish_only: bearishOnly,
                    min_score: highConfidence ? 90 : 0
                })
            });
            const data = await response.json();
            
            let results = data.results || [];
            
            if (bullishOnly) {
                results = results.filter(r => r.direction === 'BULLISH');
            }
            if (bearishOnly) {
                results = results.filter(r => r.direction === 'BEARISH');
            }
            if (highConfidence) {
                results = results.filter(r => (r.trade_score || r.confidence || 0) >= 90);
            }
            
            this.displayScannerResults(results, selected.length);
            
        } catch (error) {
            console.error('Scan error:', error);
            this.displayScannerResults([], 0);
        } finally {
            if (scanBtn) scanBtn.disabled = false;
            if (scanBtnText) scanBtnText.textContent = 'Scan Selected';
            if (scanStatus) scanStatus.style.display = 'none';
        }
    }
    
    displayScannerResults(results, selectedCount = 0) {
        this.lastScanResults = results;
        
        const container = document.getElementById('body-scan-results');
        const list = document.getElementById('body-scan-results-list');
        
        if (!container || !list) return;
        
        const populatedCount = results ? results.length : 0;
        const headerHtml = `<div class="text-center mb-2 small text-info"><i class="bi bi-check2-square"></i> ${selectedCount} checked, ${populatedCount} populated</div>`;
        
        if (!results || results.length === 0) {
            list.innerHTML = headerHtml + '<div class="text-muted text-center py-3">No results to display</div>';
            container.style.display = 'block';
            return;
        }
        
        list.innerHTML = headerHtml;
        
        results.forEach(result => {
            const isBullish = result.direction === 'BULLISH' || result.recommendation === 'CALLS';
            const isBearish = result.direction === 'BEARISH' || result.recommendation === 'PUTS';
            
            const signalColor = isBullish ? 'success' : isBearish ? 'danger' : 'warning';
            const signalText = isBullish ? 'BUY' : isBearish ? 'SELL' : 'NEUTRAL';
            const signalIcon = isBullish ? 'arrow-up-circle-fill' : isBearish ? 'arrow-down-circle-fill' : 'dash-circle-fill';
            
            const score = result.trade_score || 50;
            const price = result.current_price || result.price || 0;
            const reason = (result.reasons && result.reasons.length > 0) ? result.reasons[0] : 'Scanning...';
            
            const item = document.createElement('div');
            item.className = 'scan-result-item mb-2 p-2 rounded';
            item.style.background = isBullish ? 'rgba(34, 197, 94, 0.15)' : isBearish ? 'rgba(239, 68, 68, 0.15)' : 'rgba(234, 179, 8, 0.15)';
            item.style.border = `2px solid ${isBullish ? '#22C55E' : isBearish ? '#EF4444' : '#EAB308'}`;
            
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-center gap-2">
                        <i class="bi bi-${signalIcon} text-${signalColor}" style="font-size: 1.5rem;"></i>
                        <div>
                            <span class="fw-bold text-light" style="font-size: 1.1rem;">${result.symbol}</span>
                            <span class="badge bg-${signalColor} ms-2" style="font-size: 0.85rem;">${signalText}</span>
                        </div>
                    </div>
                    <div class="text-end">
                        <div class="fw-bold text-light">$${price.toFixed(2)}</div>
                        <div class="small text-muted">Score: ${score}</div>
                    </div>
                </div>
                <div class="small mt-1" style="color: #9CA3AF;">${reason}</div>
            `;
            
            item.style.cursor = 'pointer';
            item.addEventListener('click', () => {
                const select = document.getElementById('ticker-select');
                if (select) {
                    select.value = result.symbol;
                    this.currentTicker = result.symbol;
                    this.refreshData();
                }
            });
            
            list.appendChild(item);
        });
        
        container.style.display = 'block';
    }
    
    updateAllScanCounts() {
        const total = Object.keys(this.scannerTickerSelection).length;
        const selected = Object.values(this.scannerTickerSelection).filter(v => v).length;
        
        const bodyScanCount = document.getElementById('body-scan-count');
        if (bodyScanCount) {
            bodyScanCount.textContent = `${selected} of ${total} selected`;
            bodyScanCount.className = 'badge ' + (selected === 0 ? 'bg-danger' : selected === total ? 'bg-success' : 'bg-info');
        }
        
        const bodyScanBtn = document.getElementById('body-scan-btn');
        const bodyScanBtnText = document.getElementById('body-scan-btn-text');
        if (bodyScanBtn && bodyScanBtnText) {
            if (selected === 0) {
                bodyScanBtnText.textContent = 'Select tickers';
                bodyScanBtn.disabled = true;
            } else {
                bodyScanBtnText.textContent = `Scan ${selected} Tickers`;
                bodyScanBtn.disabled = false;
            }
        }
        
        const refreshBtn = document.getElementById('refresh-signal');
        const refreshText = document.getElementById('refresh-btn-text');
        if (refreshBtn && refreshText) {
            if (selected === 0) {
                refreshText.textContent = 'Select at least 1 ticker';
                refreshBtn.disabled = true;
            } else {
                refreshText.textContent = `Refresh Analysis (${selected})`;
                refreshBtn.disabled = false;
            }
        }
        
        this.updateNavBadge();
        this.updateScannerSelectionCount();
        this.updateModalCount();
    }
    
    renderScannerTickerList(tickers) {
        const container = document.getElementById('scanner-ticker-list');
        if (!container) return;
        
        container.innerHTML = '';
        
        tickers.forEach(ticker => {
            const isSelected = this.scannerTickerSelection[ticker.symbol] !== false;
            const item = document.createElement('div');
            item.className = `scanner-ticker-item ${isSelected ? 'selected' : 'dimmed'}`;
            item.dataset.symbol = ticker.symbol;
            item.innerHTML = `
                <div class="ticker-checkbox"><i class="bi bi-check"></i></div>
                <span class="ticker-symbol">${ticker.symbol}</span>
                <span class="not-scanning-label">(skip)</span>
            `;
            
            item.addEventListener('click', () => this.toggleScannerTicker(ticker.symbol));
            container.appendChild(item);
        });
        
        this.updateScannerSelectionCount();
    }
    
    toggleScannerTicker(symbol) {
        this.scannerTickerSelection[symbol] = !this.scannerTickerSelection[symbol];
        
        const item = document.querySelector(`.scanner-ticker-item[data-symbol="${symbol}"]`);
        if (item) {
            item.classList.toggle('selected', this.scannerTickerSelection[symbol]);
            item.classList.toggle('dimmed', !this.scannerTickerSelection[symbol]);
        }
        
        this.saveScannerSelection();
        this.updateScannerSelectionCount();
    }
    
    scannerSelectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = true;
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.add('selected');
            item.classList.remove('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateScannerSelectionCount();
    }
    
    scannerDeselectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = false;
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.add('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateScannerSelectionCount();
    }
    
    saveScannerSelection() {
        localStorage.setItem('scannerTickerSelection', JSON.stringify(this.scannerTickerSelection));
    }
    
    updateScannerSelectionCount() {
        const total = Object.keys(this.scannerTickerSelection).length;
        const selected = Object.values(this.scannerTickerSelection).filter(v => v).length;
        
        const countEl = document.getElementById('scanner-selection-count');
        if (countEl) {
            countEl.textContent = `${selected} of ${total} selected`;
            countEl.className = 'badge ' + (selected === 0 ? 'bg-danger' : selected === total ? 'bg-success' : 'bg-info');
        }
    }
    
    getSelectedScannerTickers() {
        return Object.entries(this.scannerTickerSelection)
            .filter(([symbol, selected]) => selected)
            .map(([symbol]) => symbol);
    }
    
    openScannerModal() {
        this.renderModalTickerList();
        const modal = new bootstrap.Modal(document.getElementById('scannerModal'));
        modal.show();
    }
    
    renderModalTickerList() {
        const container = document.getElementById('modal-ticker-list');
        if (!container) return;
        
        container.innerHTML = '';
        const tickers = Object.keys(this.scannerTickerSelection);
        
        tickers.forEach(symbol => {
            const isSelected = this.scannerTickerSelection[symbol] !== false;
            const item = document.createElement('div');
            item.className = `scanner-modal-item ${isSelected ? 'selected' : 'dimmed'}`;
            item.dataset.symbol = symbol;
            item.innerHTML = `
                <div class="checkbox"><i class="bi bi-check"></i></div>
                <span class="symbol">${symbol}</span>
            `;
            item.addEventListener('click', () => this.toggleModalTicker(symbol));
            container.appendChild(item);
        });
        
        this.updateModalCount();
        this.updateNavBadge();
    }
    
    toggleModalTicker(symbol) {
        this.scannerTickerSelection[symbol] = !this.scannerTickerSelection[symbol];
        
        const modalItem = document.querySelector(`#modal-ticker-list .scanner-modal-item[data-symbol="${symbol}"]`);
        if (modalItem) {
            modalItem.classList.toggle('selected', this.scannerTickerSelection[symbol]);
            modalItem.classList.toggle('dimmed', !this.scannerTickerSelection[symbol]);
        }
        
        const scannerItem = document.querySelector(`.scanner-ticker-item[data-symbol="${symbol}"]`);
        if (scannerItem) {
            scannerItem.classList.toggle('selected', this.scannerTickerSelection[symbol]);
            scannerItem.classList.toggle('dimmed', !this.scannerTickerSelection[symbol]);
        }
        
        this.saveScannerSelection();
        this.updateModalCount();
        this.updateScannerSelectionCount();
        this.updateNavBadge();
    }
    
    modalSelectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = true;
        });
        
        document.querySelectorAll('#modal-ticker-list .scanner-modal-item').forEach(item => {
            item.classList.add('selected');
            item.classList.remove('dimmed');
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.add('selected');
            item.classList.remove('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateModalCount();
        this.updateScannerSelectionCount();
        this.updateNavBadge();
    }
    
    modalDeselectAll() {
        Object.keys(this.scannerTickerSelection).forEach(symbol => {
            this.scannerTickerSelection[symbol] = false;
        });
        
        document.querySelectorAll('#modal-ticker-list .scanner-modal-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.add('dimmed');
        });
        
        document.querySelectorAll('.scanner-ticker-item').forEach(item => {
            item.classList.remove('selected');
            item.classList.add('dimmed');
        });
        
        this.saveScannerSelection();
        this.updateModalCount();
        this.updateScannerSelectionCount();
        this.updateNavBadge();
    }
    
    updateModalCount() {
        const total = Object.keys(this.scannerTickerSelection).length;
        const selected = Object.values(this.scannerTickerSelection).filter(v => v).length;
        
        const countEl = document.getElementById('modal-scanner-count');
        if (countEl) {
            countEl.textContent = `${selected} of ${total} selected`;
            countEl.className = 'badge ' + (selected === 0 ? 'bg-danger' : selected === total ? 'bg-success' : 'bg-info');
        }
    }
    
    updateNavBadge() {
        const selected = Object.values(this.scannerTickerSelection).filter(v => v).length;
        const badge = document.getElementById('scanner-badge');
        if (badge) {
            badge.textContent = selected;
            badge.className = 'badge ms-1 ' + (selected === 0 ? 'bg-danger text-white' : 'bg-light text-dark');
        }
    }
    
    async runModalScan() {
        const selectedTickers = this.getSelectedScannerTickers();
        
        if (selectedTickers.length === 0) {
            this.showScannerError();
            return;
        }
        
        const btn = document.getElementById('modal-scan-btn');
        const status = document.getElementById('modal-scanner-status');
        const scanText = document.getElementById('modal-scan-text');
        
        const filters = {
            bullish_only: document.getElementById('modal-filter-bullish')?.checked || false,
            bearish_only: document.getElementById('modal-filter-bearish')?.checked || false,
            min_score: document.getElementById('modal-filter-high')?.checked ? 90 : 0,
            tickers: selectedTickers
        };
        
        if (btn) btn.disabled = true;
        if (status) status.style.display = 'block';
        if (scanText) {
            const tickerList = selectedTickers.slice(0, 3).join(', ');
            const more = selectedTickers.length > 3 ? `... (${selectedTickers.length} tickers)` : '';
            scanText.textContent = `Scanning ${tickerList}${more}`;
        }
        
        try {
            const response = await fetch('/api/scan-top-10', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filters)
            });
            
            const data = await response.json();
            
            bootstrap.Modal.getInstance(document.getElementById('scannerModal'))?.hide();
            
            const results = document.getElementById('scanner-results');
            const summary = document.getElementById('scanner-summary');
            
            if (summary && data.summary) {
                document.getElementById('summary-analyzed').textContent = `${data.summary.successful}/${data.summary.total_analyzed}`;
                document.getElementById('summary-bullish').textContent = data.summary.bullish_setups;
                document.getElementById('summary-bearish').textContent = data.summary.bearish_setups;
                document.getElementById('summary-high-conf').textContent = data.summary.high_confidence;
                summary.style.display = 'block';
            }
            
            if (results) {
                if (!data.results || data.results.length === 0) {
                    results.innerHTML = '<div class="text-center text-muted py-3">No stocks matched your filters</div>';
                } else {
                    results.innerHTML = data.results.map(r => this.renderScanResult(r)).join('');
                }
            }
            
        } catch (error) {
            console.error('Modal scan error:', error);
        } finally {
            if (btn) btn.disabled = false;
            if (status) status.style.display = 'none';
        }
    }
    
    async loadSettings() {
        try {
            const response = await fetch('/api/settings');
            this.settings = await response.json();
            this.audioEnabled = this.settings.audio_enabled !== false;
            this.audioVolume = (this.settings.audio_volume || 50) / 100;
            this.updateAudioToggle();
            
            const saved = localStorage.getItem('indicatorToggles');
            if (saved) {
                this.indicatorToggles = JSON.parse(saved);
                Object.keys(this.indicatorToggles).forEach(key => {
                    const el = document.getElementById(`toggle-${key}`);
                    if (el) el.checked = this.indicatorToggles[key];
                });
            }
        } catch (error) {
            console.error('Error loading settings:', error);
        }
    }
    
    async loadSignals() {
        try {
            const response = await fetch('/api/signals?limit=20');
            const signals = await response.json();
            const feed = document.getElementById('signal-feed');
            if (!feed) return;
            feed.innerHTML = '';
            
            if (signals.length === 0) {
                feed.innerHTML = '<div class="list-group-item bg-dark text-muted text-center py-3">No signals yet</div>';
                return;
            }
            
            signals.slice(0, 10).forEach(signal => this.addSignalToFeed(signal, false));
        } catch (error) {
            console.error('Error loading signals:', error);
        }
    }
    
    bindEvents() {
        const tickerSelect = document.getElementById('ticker-select');
        if (tickerSelect) {
            tickerSelect.addEventListener('change', (e) => {
                const sym = (e.target.value || '').trim().toUpperCase();
                if (!sym) return;
                this.currentTicker = sym;
                this.lastReversalKey = null;
                this.socket.emit('subscribe', { symbol: this.currentTicker });
                this.showTickerLoading(true);
                this.updateCoachPlaceholder();
                this.refreshData();
            });
        }
        
        document.querySelectorAll('.timeframe-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.timeframe-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.currentInterval = e.target.dataset.interval;
                this.currentPeriod = e.target.dataset.period;
                document.getElementById('chart-timeframe-label').textContent = this.currentInterval;
                this.loadChartData();
                this.loadTradeRecommendation();
            });
        });
        
        document.querySelectorAll('[data-period]').forEach(btn => {
            if (!btn.dataset.interval) {
                btn.addEventListener('click', (e) => {
                    this.currentPeriod = e.target.dataset.period;
                    this.loadChartData();
                });
            }
        });
        
        ['chart-line', 'chart-candle', 'chart-heiken'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.addEventListener('click', () => {
                    document.querySelectorAll('.chart-type-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    this.chartType = id.replace('chart-', '');
                    this.loadChartData();
                });
            }
        });
        
        const refreshBtn = document.getElementById('refresh-signal');
        if (refreshBtn) refreshBtn.addEventListener('click', () => this.refreshData());
        const tickerCardRefresh = document.getElementById('ticker-card-refresh');
        if (tickerCardRefresh) tickerCardRefresh.addEventListener('click', () => {
            this.showTickerLoading(true);
            this.refreshData();
        });
        
        const audioToggle = document.getElementById('audio-toggle');
        if (audioToggle) {
            audioToggle.addEventListener('click', () => {
                this.audioEnabled = !this.audioEnabled;
                this.updateAudioToggle();
            });
        }
        
        const toggleAdvanced = document.getElementById('toggle-advanced');
        if (toggleAdvanced) {
            toggleAdvanced.addEventListener('click', () => {
                this.advancedVisible = !this.advancedVisible;
                const section = document.getElementById('advanced-section');
                if (section) section.style.display = this.advancedVisible ? 'block' : 'none';
                toggleAdvanced.classList.toggle('btn-primary', this.advancedVisible);
                toggleAdvanced.classList.toggle('btn-outline-secondary', !this.advancedVisible);
                if (this.advancedVisible) this.loadAdvancedData();
            });
        }
        
        const addTickerSubmit = document.getElementById('add-ticker-submit');
        if (addTickerSubmit) addTickerSubmit.addEventListener('click', () => this.addTicker());
        
        const addTickerModalEl = document.getElementById('addTickerModal');
        if (addTickerModalEl && typeof bootstrap !== 'undefined') {
            addTickerModalEl.addEventListener('show.bs.modal', () => {
                const btn = document.getElementById('add-ticker-submit');
                if (btn) { btn.disabled = false; btn.textContent = 'Add'; }
                const input = document.getElementById('new-ticker');
                if (input) input.value = '';
            });
        }
        
        const newTickerInput = document.getElementById('new-ticker');
        if (newTickerInput) {
            newTickerInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.addTicker();
            });
        }
        
        const removeTickerBtn = document.getElementById('remove-ticker-btn');
        if (removeTickerBtn) {
            removeTickerBtn.addEventListener('click', () => this.confirmRemoveTicker());
        }
        
        const saveSettings = document.getElementById('save-settings');
        if (saveSettings) saveSettings.addEventListener('click', () => this.saveSettings());
        
        const audioVolumeSlider = document.getElementById('audio-volume');
        if (audioVolumeSlider) {
            audioVolumeSlider.addEventListener('input', (e) => {
                this.audioVolume = e.target.value / 100;
                document.getElementById('volume-level-display').textContent = e.target.value + '%';
            });
        }
        
        const testBuySound = document.getElementById('test-buy-sound');
        if (testBuySound) testBuySound.addEventListener('click', () => this.playBuyAlert());
        
        const testSellSound = document.getElementById('test-sell-sound');
        if (testSellSound) testSellSound.addEventListener('click', () => this.playSellAlert());
        
        document.querySelectorAll('[id^="toggle-"]').forEach(toggle => {
            toggle.addEventListener('change', () => this.updateIndicatorCount());
        });
        
        const paperBuyBtn = document.getElementById('paper-buy-btn');
        const paperSellBtn = document.getElementById('paper-sell-btn');
        if (paperBuyBtn) paperBuyBtn.addEventListener('click', () => this.openPaperTrade('long'));
        if (paperSellBtn) paperSellBtn.addEventListener('click', () => this.openPaperTrade('short'));
        
        const paperExecute = document.getElementById('paper-execute');
        if (paperExecute) paperExecute.addEventListener('click', () => this.executePaperTrade());
        
        const scanBtn = document.getElementById('scan-top-10-btn');
        if (scanBtn) scanBtn.addEventListener('click', () => this.scanTop10());
        
        const selectAllBtn = document.getElementById('scanner-select-all');
        if (selectAllBtn) selectAllBtn.addEventListener('click', () => this.scannerSelectAll());
        
        const deselectAllBtn = document.getElementById('scanner-deselect-all');
        if (deselectAllBtn) deselectAllBtn.addEventListener('click', () => this.scannerDeselectAll());
        
        const openScannerModal = document.getElementById('open-scanner-modal');
        if (openScannerModal) openScannerModal.addEventListener('click', () => this.openScannerModal());
        
        const modalSelectAll = document.getElementById('modal-select-all');
        if (modalSelectAll) modalSelectAll.addEventListener('click', () => this.modalSelectAll());
        
        const modalDeselectAll = document.getElementById('modal-deselect-all');
        if (modalDeselectAll) modalDeselectAll.addEventListener('click', () => this.modalDeselectAll());
        
        const modalScanBtn = document.getElementById('modal-scan-btn');
        if (modalScanBtn) modalScanBtn.addEventListener('click', () => this.runModalScan());
        
        const bodySelectAll = document.getElementById('body-select-all');
        if (bodySelectAll) bodySelectAll.addEventListener('click', () => this.bodySelectAll());
        
        const bodyDeselectAll = document.getElementById('body-deselect-all');
        if (bodyDeselectAll) bodyDeselectAll.addEventListener('click', () => this.bodyDeselectAll());
        
        const bodyScanBtn = document.getElementById('body-scan-btn');
        if (bodyScanBtn) bodyScanBtn.addEventListener('click', () => this.runBodyScan());
        
        const prevTickerBtn = document.getElementById('prev-ticker-btn');
        if (prevTickerBtn) prevTickerBtn.addEventListener('click', () => this.navigateTicker(-1));
        
        const nextTickerBtn = document.getElementById('next-ticker-btn');
        if (nextTickerBtn) nextTickerBtn.addEventListener('click', () => this.navigateTicker(1));
        
        const exportScanBtn = document.getElementById('export-scan-btn');
        if (exportScanBtn) exportScanBtn.addEventListener('click', () => this.exportScanResults());
        
        const refreshNewsBtn = document.getElementById('refresh-news-btn');
        if (refreshNewsBtn) refreshNewsBtn.addEventListener('click', () => this.loadNewsData());
    }
    
    navigateTicker(direction) {
        const select = document.getElementById('ticker-select');
        if (!select) return;
        
        const options = Array.from(select.options);
        const currentIndex = options.findIndex(opt => opt.value === this.currentTicker);
        let newIndex = currentIndex + direction;
        
        if (newIndex < 0) newIndex = options.length - 1;
        if (newIndex >= options.length) newIndex = 0;
        
        this.currentTicker = options[newIndex].value;
        select.value = this.currentTicker;
        this.refreshData();
    }
    
    exportScanResults() {
        if (!this.lastScanResults || this.lastScanResults.length === 0) {
            alert('No scan results to export. Run a scan first.');
            return;
        }
        
        const now = new Date();
        const timestamp = now.toISOString().slice(0,16).replace('T','_').replace(':','-');
        
        const escapeCSV = (str) => {
            if (!str) return '';
            str = String(str);
            if (str.includes('"') || str.includes(',') || str.includes('\n')) {
                return '"' + str.replace(/"/g, '""') + '"';
            }
            return str;
        };
        
        let csv = 'Ticker,Signal,Score,Price,Reason,Timestamp\n';
        this.lastScanResults.forEach(r => {
            const signal = r.direction === 'BULLISH' ? 'BUY' : r.direction === 'BEARISH' ? 'SELL' : 'NEUTRAL';
            const price = r.current_price || r.price || 0;
            const reasons = (r.reasons && r.reasons.length > 0) ? r.reasons.join(' | ') : '';
            csv += `${r.symbol},${signal},${r.trade_score || 0},$${price.toFixed(2)},${escapeCSV(reasons)},${now.toISOString()}\n`;
        });
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `scan_results_${timestamp}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }
    
    bindKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            
            switch (e.code) {
                case 'Space':
                    e.preventDefault();
                    this.refreshData();
                    break;
                case 'KeyA':
                    this.refreshData();
                    break;
                case 'KeyM':
                    this.audioEnabled = !this.audioEnabled;
                    this.updateAudioToggle();
                    break;
            }
        });
    }
    
    startTimers() {
        setInterval(() => {
            this.updateTime();
            this.updateMarketStatus();
            this.updateDataStaleness();
        }, 1000);
        
        // Dynamic refresh rate - faster during extended hours when data is more volatile
        this.startDynamicRefresh();
        
        this.updateMotivationalQuote();
        setInterval(() => this.updateMotivationalQuote(), 60000);
    }
    
    startDynamicRefresh() {
        const getRefreshInterval = () => {
            const now = new Date();
            const hour = now.toLocaleString('en-US', { timeZone: 'America/New_York', hour: 'numeric', hour12: false });
            const hourNum = parseInt(hour);
            
            // Regular market hours (9:30-16:00 ET): 8 second refresh
            // Extended hours: 5 second refresh for faster updates
            if (hourNum >= 10 && hourNum < 16) {
                return 8000;
            } else {
                return 5000; // Faster refresh during extended hours
            }
        };
        
        const scheduleNextRefresh = () => {
            const interval = getRefreshInterval();
            setTimeout(() => {
                this.refreshData();
                scheduleNextRefresh();
            }, interval);
        };
        
        scheduleNextRefresh();
    }
    
    updateDataStaleness() {
        const lastRefreshEl = document.getElementById('last-refresh-time');
        if (lastRefreshEl && this.lastRefreshTimestamp) {
            const elapsed = Math.floor((Date.now() - this.lastRefreshTimestamp) / 1000);
            if (elapsed > 15) {
                lastRefreshEl.classList.add('text-warning');
                lastRefreshEl.title = `Data may be stale (${elapsed}s old)`;
            } else {
                lastRefreshEl.classList.remove('text-warning');
                lastRefreshEl.title = 'Data is fresh';
            }
        }
    }
    
    updateMotivationalQuote() {
        const el = document.getElementById('daily-motivation');
        if (el) {
            el.textContent = this.getMotivationalQuote();
        }
    }
    
    updateTime() {
        const now = new Date();
        const el = document.getElementById('current-time');
        if (el) {
            el.textContent = now.toLocaleTimeString('en-US', { 
                timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
            }) + ' ET';
        }
    }
    
    async updateMarketStatus() {
        const badge = document.getElementById('market-status');
        const textEl = document.getElementById('session-text');
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 12000);
            const response = await fetch('/api/market-status', { signal: controller.signal });
            clearTimeout(timeoutId);
            if (!response.ok) {
                this.setPriceCardError('API error', 'market-status ' + response.status);
                throw new Error('market-status ' + response.status);
            }
            const status = await response.json();
            if (!status || !status.current_session) {
                this.setPriceCardError('No data returned', 'market-status empty');
                throw new Error('No status');
            }
            if (badge) {
                badge.textContent = status.current_session.replace(/_/g, ' ');
                badge.className = 'badge ' + (status.is_market_open ? 'bg-success' : 'bg-secondary');
            }
            const sessionName = document.getElementById('session-name');
            if (sessionName) sessionName.textContent = status.current_session.replace(/_/g, ' ');
            const sessionDesc = document.getElementById('session-description');
            if (sessionDesc) sessionDesc.textContent = status.session_description || '';
            const closeCountdown = document.getElementById('close-countdown');
            if (closeCountdown) closeCountdown.textContent = status.countdowns?.market_close || '--:--:--';
            const lotteryCountdown = document.getElementById('lottery-countdown');
            if (lotteryCountdown) lotteryCountdown.textContent = status.countdowns?.lottery_hour || '--:--:--';
            this.updateSessionBanner(status);
        } catch (error) {
            this.setPriceCardError('Backend unavailable', (error && error.message) ? error.message : 'market-status failed');
            if (badge) { badge.textContent = '—'; badge.className = 'badge bg-secondary'; }
            if (textEl) textEl.textContent = 'Data loaded. Click Refresh when server is ready.';
            this.updateSessionBanner(null);
        }
    }
    
    updateSessionBanner(status) {
        const iconEl = document.getElementById('session-icon');
        const textEl = document.getElementById('session-text');
        const badgeEl = document.getElementById('next-action-badge');
        const checklistEl = document.getElementById('signal-checklist');
        const checklistText = document.getElementById('checklist-text');
        const bannerEl = document.getElementById('market-session-banner');
        
        if (!textEl) return;
        
        const session = status?.current_session;
        let icon = '⏳';
        let text = 'Loading...';
        let badge = '';
        let badgeClass = 'bg-secondary';
        let checklist = '';
        let bannerBg = 'rgba(0,0,0,0.5)';
        
        if (!status || session == null) {
            icon = '📡';
            text = 'Data loaded. Use Refresh or reload page for live market status.';
            badge = '—';
        } else {
        const isMarketOpen = status.is_market_open === true;
        
        if (session === 'PRE_MARKET') {
            icon = '🌅';
            text = 'Pre-Market: Analyzing stocks before market open';
            badge = 'Scanning';
            badgeClass = 'bg-info';
            checklist = 'Pre-market analysis active. Confirm signals after market opens.';
            bannerBg = 'rgba(59, 130, 246, 0.15)';
        } else if (isMarketOpen || session === 'REGULAR' || session === 'MARKET_OPEN' || session === 'MID_MORNING' || session === 'MIDDAY' || session === 'AFTERNOON' || session === 'POWER_HOUR') {
            icon = '🟢';
            text = 'Market Open: Full signals active all day';
            badge = 'ACTIVE';
            badgeClass = 'bg-success';
            checklist = '';
            bannerBg = 'rgba(34, 197, 94, 0.15)';
        } else if (session === 'AFTER_HOURS') {
            icon = '🌙';
            text = 'After-Hours: Market closed, reviewing data only';
            badge = 'Closed';
            badgeClass = 'bg-secondary';
            checklist = 'Use this time to review today\'s signals and prepare for tomorrow.';
            bannerBg = 'rgba(100, 100, 100, 0.15)';
        } else {
            icon = '😴';
            text = 'Market Closed: Next session opens at 9:30 AM ET';
            badge = 'Closed';
            badgeClass = 'bg-secondary';
            checklist = 'Market is closed. Signals will activate when trading resumes.';
            bannerBg = 'rgba(100, 100, 100, 0.15)';
        }
        }
        
        if (iconEl) iconEl.textContent = icon;
        if (textEl) textEl.textContent = text;
        if (badgeEl) {
            badgeEl.textContent = badge;
            badgeEl.className = 'badge ' + badgeClass;
        }
        if (checklistEl && checklistText) {
            if (checklist) {
                checklistText.textContent = checklist;
                checklistEl.style.display = 'block';
            } else {
                checklistEl.style.display = 'none';
            }
        }
        if (bannerEl) {
            bannerEl.style.background = bannerBg;
        }
    }
    
    /**
     * ONLY function that may write to #current-price, #price-change, #last-updated.
     * Dumb and direct: fetch /api/quote, then set DOM or show exact error.
     */
    async loadTickerCardQuote() {
        const sym = (this.currentTicker || 'SPY').trim().toUpperCase();
        const currentPriceEl = document.getElementById('current-price');
        const priceChangeEl = document.getElementById('price-change');
        const lastUpdatedEl = document.getElementById('last-updated');
        this._updateQuoteDebug({ loadTickerCardQuoteCalled: true, lastTouch: 'loadTickerCardQuote (entry)' });
        if (!currentPriceEl) {
            this._updateQuoteDebug({ lastTouch: 'loadTickerCardQuote (no #current-price)' });
            return;
        }
        const url = `/api/quote?symbol=${encodeURIComponent(sym)}`;
        this._updateQuoteDebug({ quoteRequestStarted: true, quoteUrl: url, lastTouch: 'loadTickerCardQuote (fetch start)' });
        let response;
        let data;
        try {
            response = await fetch(url);
            this._updateQuoteDebug({ quoteStatus: response.status, quoteBody: '(parsing...)', lastTouch: 'loadTickerCardQuote (got response)' });
            const raw = await response.text();
            try {
                data = JSON.parse(raw);
            } catch (_) {
                data = null;
            }
            this._updateQuoteDebug({ quoteBody: raw.length > 120 ? raw.substring(0, 120) + '...' : raw });
        } catch (e) {
            this._updateQuoteDebug({ quoteStatus: 'err', quoteBody: (e && e.message) || String(e), lastTouch: 'loadTickerCardQuote (catch)' });
            currentPriceEl.innerHTML = '<span class="text-warning">Error: ' + this.escapeHtml((e && e.message) || 'Request failed') + '</span>';
            if (priceChangeEl) priceChangeEl.textContent = '—';
            if (lastUpdatedEl) lastUpdatedEl.textContent = 'Updated: —';
            return;
        }
        if (data === null) {
            this._updateQuoteDebug({ domUpdateSuccess: false, lastTouch: 'loadTickerCardQuote (not JSON)' });
            currentPriceEl.innerHTML = '<span class="text-warning">Invalid quote response (not JSON)</span>';
            if (priceChangeEl) priceChangeEl.textContent = '—';
            if (lastUpdatedEl) lastUpdatedEl.textContent = 'Updated: —';
            return;
        }
        if (data.error) {
            this._updateQuoteDebug({ domUpdateSuccess: false, lastTouch: 'loadTickerCardQuote (API error)' });
            currentPriceEl.innerHTML = '<span class="text-warning">' + this.escapeHtml(data.error) + '</span>';
            if (priceChangeEl) priceChangeEl.textContent = '—';
            if (lastUpdatedEl) lastUpdatedEl.textContent = 'Updated: —';
            return;
        }
        const price = data.price != null ? Number(data.price) : NaN;
        const change = data.change != null ? Number(data.change) : 0;
        const pct = data.percentChange != null ? Number(data.percentChange) : 0;
        if (isNaN(price) || price <= 0) {
            this._updateQuoteDebug({ domUpdateSuccess: false, lastTouch: 'loadTickerCardQuote (invalid price)' });
            currentPriceEl.innerHTML = '<span class="text-warning">No valid price in response</span>';
            if (priceChangeEl) priceChangeEl.textContent = '—';
            if (lastUpdatedEl) lastUpdatedEl.textContent = 'Updated: —';
            return;
        }
        currentPriceEl.innerHTML = '$' + price.toFixed(2);
        if (priceChangeEl) {
            const sign = change >= 0 ? '+' : '';
            const pctStr = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
            priceChangeEl.innerHTML = `<span class="${change >= 0 ? 'text-success' : 'text-danger'}">${sign}${change.toFixed(2)} (${pctStr})</span>`;
        }
        if (lastUpdatedEl) lastUpdatedEl.textContent = 'Updated: ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        this._updateQuoteDebug({ domUpdateSuccess: true, lastTouch: 'loadTickerCardQuote (success)' });
    }

    async refreshData() {
        this._updateQuoteDebug({ refreshDataCalled: true });
        const refreshBtn = document.getElementById('refresh-signal');
        const refreshText = document.getElementById('refresh-btn-text');
        const lastRefreshEl = document.getElementById('last-refresh-time');
        
        if (refreshBtn) { refreshBtn.disabled = true; refreshBtn.classList.add('refreshing'); }
        if (refreshText) refreshText.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Refreshing...';
        
        this.loadLastHourScan();
        await this.loadTickerCardQuote();
        
        const critical = [
            () => this.updateMarketStatus(),
            () => this.loadTradeRecommendation(),
            () => this.loadChartData()
        ];
        const secondary = [
            () => this.loadPremarketAnalysis(),
            () => this.loadScalpingLevels(),
            () => this.loadEarningsData(),
            () => this.loadNewsData(),
            () => this.loadOptionsFlowData(),
            () => this.loadMultiTimeframeAnalysis()
        ];
        
        for (const fn of critical) {
            try { await fn(); } catch (e) { console.warn('Refresh:', e); }
        }
        this.clearLoadingState();
        
        Promise.allSettled(secondary.map(fn => fn().catch(e => console.warn(e)))).then(() => {
            this.updateWinRate();
            if (this.advancedVisible) this.loadAdvancedData();
        });
        
        const now = new Date();
        this.lastRefreshTimestamp = Date.now();
        const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        if (lastRefreshEl) {
            lastRefreshEl.textContent = timeStr;
            lastRefreshEl.classList.add('flash-update');
            setTimeout(() => lastRefreshEl.classList.remove('flash-update'), 500);
        }
        this.showRefreshSuccess();
        this.clearLoadingState();
        
        if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.classList.remove('refreshing'); }
        if (refreshText) {
            const selected = Object.keys(this.scannerTickerSelection || {}).filter(k => this.scannerTickerSelection[k]).length;
            refreshText.innerHTML = `<i class="bi bi-arrow-clockwise"></i> Refresh Analysis`;
        }
    }
    
    showTickerLoading(show) {
        // BYPASS: only loadTickerCardQuote may touch price card
    }
    
    updateCoachPlaceholder() {
        const input = document.getElementById('coach-question');
        const sym = (this.currentTicker || 'SPY').toUpperCase();
        if (input) input.placeholder = `e.g. Is this a good buy for ${sym} calls?`;
    }
    
    setPriceCardError(title, detail) {
        // BYPASS: only loadTickerCardQuote may touch price card
    }

    clearLoadingState() {
        const badge = document.getElementById('market-status');
        const textEl = document.getElementById('session-text');
        const premarketTrend = document.getElementById('premarket-trend');
        if (badge && (badge.textContent === 'Loading...' || badge.textContent === 'Refreshing...')) {
            badge.textContent = '—';
            badge.className = 'badge bg-secondary';
        }
        if (textEl && /Loading|Connecting/.test(textEl.textContent)) {
            textEl.textContent = 'Data loaded. Click Refresh for live status.';
            const iconEl = document.getElementById('session-icon');
            if (iconEl) iconEl.textContent = '📡';
        }
        const signalSummary = document.getElementById('signal-summary');
        if (signalSummary && /Analyzing market conditions/i.test(signalSummary.textContent)) {
            signalSummary.textContent = 'Click Refresh for live analysis.';
        }
        if (premarketTrend && premarketTrend.textContent.trim() === 'Loading...') {
            premarketTrend.textContent = '—';
            premarketTrend.className = 'h5 text-muted';
        }
        // BYPASS: do not touch #current-price or #last-updated; only loadTickerCardQuote may
    }
    
    showRefreshSuccess() {
        const signalPanel = document.getElementById('main-signal-panel');
        if (signalPanel) {
            signalPanel.classList.add('flash-update');
            setTimeout(() => signalPanel.classList.remove('flash-update'), 500);
        }
    }
    
    async loadMultiTimeframeAnalysis() {
        try {
            const response = await fetch(`/api/multi-timeframe/${this.currentTicker}?_t=${Date.now()}`);
            const data = await response.json();
            
            this.updateTimeframePanel(data);
            this.updateConfluenceDisplay(data.confluence);
            
        } catch (error) {
            console.error('Error loading multi-timeframe:', error);
        }
    }
    
    async loadScalpingLevels() {
        const loadingEl = document.getElementById('scalping-loading');
        const bestRangeEl = document.getElementById('scalping-best-range');
        const atrRangeEl = document.getElementById('scalping-atr-range');
        const fibLevelsEl = document.getElementById('scalping-fib-levels');
        const timeframesEl = document.getElementById('scalping-timeframes');
        if (!bestRangeEl && !fibLevelsEl) return;
        try {
            if (loadingEl) loadingEl.textContent = 'Loading Fib levels...';
            const response = await fetch(`/api/scalping-levels/${this.currentTicker}?_t=${Date.now()}`);
            const data = await response.json();
            if (loadingEl) loadingEl.style.display = 'none';
            if (data.error) {
                if (bestRangeEl) bestRangeEl.innerHTML = `<span class="text-warning small">${data.error}</span>`;
                if (atrRangeEl) atrRangeEl.innerHTML = '';
                if (fibLevelsEl) fibLevelsEl.innerHTML = '';
                if (timeframesEl) timeframesEl.innerHTML = '';
                return;
            }
            const best = data.best_retracement_range || {};
            const timeframes = data.timeframes || {};
            const sym = (data.symbol || this.currentTicker || '').toUpperCase();
            const fmt = (v) => (v != null && v !== '') ? Number(v).toFixed(2) : '—';
            const fmtPct = (v) => (v != null && v !== '') ? Number(v).toFixed(2) + '%' : '—';
            if (bestRangeEl) {
                bestRangeEl.innerHTML = `
                    <div class="fw-bold text-info small">Best retracement ${sym ? `(${sym}) ` : ''}${best.timeframe || '—'}</div>
                    <div class="text-muted small">Zone: ${best.zone || '—'} · SH: $${fmt(best.swing_high)} SL: $${fmt(best.swing_low)}</div>
                    <div class="small">Support: $${fmt(best.nearest_support)} · Resistance: $${fmt(best.nearest_resistance)}</div>
                `;
            }
            if (atrRangeEl && (best.atr_move != null || best.range_low != null)) {
                atrRangeEl.innerHTML = `
                    <div class="text-muted small">ATR move: $${fmt(best.atr_move)} (${fmtPct(best.atr_pct)})</div>
                    <div class="small">Range: $${fmt(best.range_low)} – $${fmt(best.range_high)}</div>
                `;
            } else if (atrRangeEl) atrRangeEl.innerHTML = '';
            const levels = best.levels || {};
            if (fibLevelsEl && Object.keys(levels).length) {
                const parts = ['23.6', '38.2', '50', '61.8', '78.6'].filter(k => levels[k] != null).map(k => `${k}%: $${fmt(levels[k])}`);
                fibLevelsEl.innerHTML = `<div class="text-muted small">Fib: ${parts.join(' · ')}</div>`;
            } else if (fibLevelsEl) fibLevelsEl.innerHTML = '';
            const tfOrder = ['1m', '2m', '5m', '15m', '1h', '4h'];
            let tfHtml = '';
            tfOrder.forEach(tf => {
                const tfData = timeframes[tf];
                if (!tfData || tfData.error) return;
                const fib = tfData.fib || {};
                const zone = fib.zone || '—';
                const ret = fib.retracement_pct != null ? fib.retracement_pct + '%' : '—';
                tfHtml += `<div class="d-flex justify-content-between small mb-1"><span>${tf}</span><span class="text-info">${zone} (${ret})</span></div>`;
            });
            if (timeframesEl) timeframesEl.innerHTML = tfHtml || '<span class="text-muted small">No timeframe data</span>';
        } catch (error) {
            console.error('Error loading scalping levels:', error);
            if (loadingEl) {
                loadingEl.style.display = '';
                loadingEl.textContent = 'Select a ticker to load levels.';
            }
            if (bestRangeEl) bestRangeEl.innerHTML = '';
            if (atrRangeEl) atrRangeEl.innerHTML = '';
            if (fibLevelsEl) fibLevelsEl.innerHTML = '';
            if (timeframesEl) timeframesEl.innerHTML = '';
        }
    }
    
    updateTimeframePanel(data) {
        const container = document.getElementById('timeframe-confluence');
        if (!container) return;
        
        const timeframes = data.timeframes || {};
        const tfOrder = ['1m', '5m', '15m', '1h', '4h'];
        
        let html = '<div class="d-flex justify-content-between align-items-center mb-2">';
        html += '<small class="text-muted">Multi-Timeframe Confluence</small>';
        html += `<small class="text-info" id="mtf-refresh-time">${data.refresh_id || ''}</small>`;
        html += '</div>';
        html += '<div class="timeframe-grid">';
        
        tfOrder.forEach(tf => {
            const tfData = timeframes[tf] || { signal: 'N/A', color: '#888' };
            const signalClass = tfData.trend === 'BULLISH' ? 'tf-bullish' : 
                               tfData.trend === 'BEARISH' ? 'tf-bearish' : 'tf-neutral';
            
            html += `
                <div class="tf-item ${signalClass}" title="RSI: ${tfData.rsi || 'N/A'} | MACD: ${tfData.macd_signal || 'N/A'}">
                    <div class="tf-label">${tf}</div>
                    <div class="tf-signal" style="color: ${tfData.color}">${tfData.signal}</div>
                    <div class="tf-indicator">
                        <span class="tf-rsi">${tfData.rsi ? Math.round(tfData.rsi) : '-'}</span>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        
        const confluence = data.confluence || {};
        html += `
            <div class="confluence-summary mt-2 p-2 rounded" style="background: rgba(0,0,0,0.3); border-left: 3px solid ${confluence.color || '#888'}">
                <div class="d-flex justify-content-between align-items-center">
                    <span class="fw-bold" style="color: ${confluence.color}">${confluence.signal || 'ANALYZING'}</span>
                    <span class="small text-muted">${confluence.bullish_count || 0}/${confluence.total || 5} Bullish</span>
                </div>
            </div>
        `;
        
        container.innerHTML = html;
        container.classList.add('flash-update');
        setTimeout(() => container.classList.remove('flash-update'), 500);
        
        // Update entry timing note based on main signal state
        this.updateEntryTimingNote(confluence);
    }
    
    updateEntryTimingNote(confluence) {
        const noteEl = document.getElementById('entry-timing-note');
        if (!noteEl) return;
        
        const mainSignal = this.lastTradeData?.main_signal || 'WAIT';
        const isBullish = confluence?.bullish_count > confluence?.bearish_count;
        
        let noteText = '';
        if (mainSignal === 'PREPARE') {
            if (isBullish) {
                noteText = '<i class="bi bi-info-circle"></i> Higher timeframe bias bullish — entry timing pending.';
            } else {
                noteText = '<i class="bi bi-info-circle"></i> Higher timeframe bias bearish — entry timing pending.';
            }
            noteEl.style.display = 'block';
        } else if (mainSignal.includes('BUY') || mainSignal.includes('SELL')) {
            noteText = '<i class="bi bi-check-circle text-success"></i> Entry confirmed on primary timeframe.';
            noteEl.style.display = 'block';
        } else {
            noteText = '<i class="bi bi-dash-circle"></i> No confluence edge — wait.';
            noteEl.style.display = 'block';
        }
        
        noteEl.innerHTML = noteText;
    }
    
    updateConfluenceDisplay(confluence) {
        const confluenceEl = document.getElementById('confluence-signal');
        if (confluenceEl && confluence) {
            confluenceEl.textContent = confluence.signal || 'WAIT';
            confluenceEl.style.color = confluence.color || '#F59E0B';
        }
    }
    
    async loadEarningsData() {
        try {
            const response = await fetch(`/api/earnings/${this.currentTicker}`);
            const data = await response.json();
            
            const earningsWarning = document.getElementById('earnings-warning');
            const earningsText = document.getElementById('earnings-text');
            
            if (earningsWarning && data.warning) {
                earningsWarning.style.display = 'inline-block';
                earningsText.textContent = data.message || `Earnings in ${data.days_until} days!`;
                
                if (data.urgency === 'CRITICAL') {
                    earningsWarning.className = 'badge bg-danger p-2 earnings-pulse';
                    earningsWarning.innerHTML = `<i class="bi bi-exclamation-triangle-fill"></i> <span id="earnings-text">${data.message}</span>`;
                } else if (data.urgency === 'HIGH') {
                    earningsWarning.className = 'badge bg-warning text-dark p-2';
                    earningsWarning.innerHTML = `<i class="bi bi-calendar-event-fill"></i> <span id="earnings-text">${data.message}</span>`;
                } else {
                    earningsWarning.className = 'badge bg-info p-2';
                    earningsWarning.innerHTML = `<i class="bi bi-calendar-event"></i> <span id="earnings-text">${data.message}</span>`;
                }
            } else if (earningsWarning) {
                earningsWarning.style.display = 'none';
            }
        } catch (error) {}
    }
    
    async loadNewsData() {
        try {
            const response = await fetch(`/api/news/${this.currentTicker}?limit=5`);
            const data = await response.json();
            
            const newsList = document.getElementById('news-list');
            if (!newsList) return;
            
            if (data.news && data.news.length > 0) {
                newsList.innerHTML = data.news.map(item => {
                    const sentimentClass = item.sentiment === 'bullish' ? 'news-bullish' : 
                                          item.sentiment === 'bearish' ? 'news-bearish' : 'news-neutral';
                    const sentimentIcon = item.sentiment === 'bullish' ? '<i class="bi bi-arrow-up-circle-fill text-success"></i>' : 
                                         item.sentiment === 'bearish' ? '<i class="bi bi-arrow-down-circle-fill text-danger"></i>' : '';
                    return `
                    <a href="${item.link}" target="_blank" class="list-group-item list-group-item-action bg-transparent text-light border-secondary py-2 ${sentimentClass}">
                        <div class="d-flex w-100 justify-content-between align-items-start">
                            <small class="fw-bold" style="max-width: 85%;">${sentimentIcon} ${this.escapeHtml(item.title)}</small>
                            <small class="text-muted">${item.published.split(' ')[0]}</small>
                        </div>
                        <small class="text-muted">${item.publisher}</small>
                    </a>
                `}).join('');
            } else {
                newsList.innerHTML = '<div class="list-group-item bg-transparent text-muted border-0">No recent news</div>';
            }
        } catch (error) {
            console.error('Error loading news:', error);
        }
    }
    
    async loadOptionsFlowData() {
        try {
            const response = await fetch(`/api/options-flow/${this.currentTicker}?_t=${Date.now()}`);
            const data = await response.json();
            
            const ivBadge = document.getElementById('iv-badge');
            const ivRankValue = document.getElementById('iv-rank-value');
            
            if (ivBadge && data.iv_rank !== undefined) {
                ivBadge.style.display = 'inline-block';
                ivRankValue.textContent = data.iv_rank.toFixed(0);
                
                if (data.iv_rank < 25) {
                    ivBadge.className = 'badge bg-success p-2';
                    ivBadge.title = 'IV is LOW - Options are cheap. Good time to buy options!';
                } else if (data.iv_rank < 50) {
                    ivBadge.className = 'badge bg-info p-2';
                    ivBadge.title = 'IV is below average. Fair pricing.';
                } else if (data.iv_rank < 75) {
                    ivBadge.className = 'badge bg-warning text-dark p-2';
                    ivBadge.title = 'IV is elevated. Options are getting expensive.';
                } else {
                    ivBadge.className = 'badge bg-danger p-2';
                    ivBadge.title = 'IV is HIGH - Options are expensive! Consider selling instead.';
                }
            }
        } catch (error) {}
    }
    
    updateWinRate() {
        const winRateBadge = document.getElementById('win-rate-value');
        if (!winRateBadge) return;
        
        // Hide win rate until we have meaningful data (minimum 20 resolved trades)
        const minTradesRequired = 20;
        
        const signals = this.signalHistory.filter(s => s.ticker === this.currentTicker);
        const total = signals.length;
        
        if (total === 0) {
            winRateBadge.textContent = '--';
            return;
        }
        
        const recentSignals = signals.slice(-20);
        let wins = 0;
        
        for (let i = 0; i < recentSignals.length - 1; i++) {
            const sig = recentSignals[i];
            const nextSig = recentSignals[i + 1];
            if (sig.signal === 'BUY' || sig.signal === 'STRONG BUY') {
                if (nextSig.price > sig.price) wins++;
            } else if (sig.signal === 'SELL' || sig.signal === 'STRONG SELL') {
                if (nextSig.price < sig.price) wins++;
            }
        }
        
        // Only show win rate if we have enough data for meaningful statistics
        const resolvedTrades = recentSignals.length - 1;
        if (resolvedTrades < minTradesRequired) {
            winRateBadge.textContent = '--';
            const badge = document.getElementById('win-rate-badge');
            if (badge) {
                badge.className = 'badge bg-secondary p-2';
                badge.title = `Need ${minTradesRequired - resolvedTrades} more trades for statistics`;
            }
            return;
        }
        
        const winRate = Math.round((wins / resolvedTrades) * 100);
        winRateBadge.textContent = winRate;
        
        const badge = document.getElementById('win-rate-badge');
        if (badge) {
            if (winRate >= 70) badge.className = 'badge bg-success p-2';
            else if (winRate >= 50) badge.className = 'badge bg-info p-2';
            else badge.className = 'badge bg-warning text-dark p-2';
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    async loadTradeRecommendation() {
        console.log('LOAD TRADE RECOMMENDATION RUNNING', this.currentTicker || 'SPY');
        const requestedSymbol = (this.currentTicker || '').toUpperCase();
        try {
            const cacheBuster = Date.now();
            const ac = new AbortController();
            const t = setTimeout(() => ac.abort(), 15000);
            const response = await fetch(`/api/trade-recommendation/${requestedSymbol}?interval=${this.currentInterval}&_t=${cacheBuster}`, { signal: ac.signal });
            clearTimeout(t);
            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                this.setSignalPanelWaitState('Invalid response');
                return;
            }
            if (!response.ok) {
                this.setSignalPanelWaitState('API ' + response.status);
                return;
            }
            if ((this.currentTicker || '').toUpperCase() !== requestedSymbol) return;
            if (data.error || !data.current_price) {
                console.warn('Trade recommendation:', data.error || 'No price data');
                this.setSignalPanelWaitState(data.error || 'No price data');
                return;
            }
            this.updateTrafficLight(data.main_signal);
            this.updateMainSignalPanel(data);
            this.updateRecommendationPanels(data);
            this.updateIndicatorsSummary(data.indicators);
            this.updateKeyLevels(data.indicators.support_resistance, data.current_price);
            if (typeof this.loadScalpingLevels === 'function') this.loadScalpingLevels();
            this.checkHotStock(data);
            this.handleTrendReversalAlert(data);
            const isNewSignal = this.lastSignal?.type !== data.main_signal;
            if (isNewSignal && data.main_signal !== 'WAIT' && this.audioEnabled) {
                if (data.main_signal === 'BUY' || data.main_signal === 'STRONG BUY') {
                    this.playBuyAlert();
                    this.sendPushNotification(
                        `${data.main_signal}: ${this.currentTicker}`,
                        `$${data.current_price} - ${data.summary}`,
                        'buy-signal'
                    );
                } else if (data.main_signal === 'SELL' || data.main_signal === 'STRONG SELL') {
                    this.playSellAlert();
                    this.sendPushNotification(
                        `${data.main_signal}: ${this.currentTicker}`,
                        `$${data.current_price} - ${data.summary}`,
                        'sell-signal'
                    );
                }
                this.lastSignal = { type: data.main_signal, time: Date.now() };
                this.logSignal(this.currentTicker, data.main_signal, data.current_price, data.strength, data.reasons);
            }
            
        } catch (error) {
            console.warn('Trade recommendation load failed:', error);
            this.setSignalPanelWaitState(error && error.message ? error.message : 'Load failed');
        }
    }
    
    /**
     * Set signal panel to WAIT with a clear message so we never leave "Analyzing market conditions..." stuck.
     */
    setSignalPanelWaitState(reason) {
        this.updateTrafficLight('WAIT');
        const signalText = document.getElementById('main-signal-text');
        const summary = document.getElementById('signal-summary');
        const panel = document.getElementById('main-signal-panel');
        if (signalText) signalText.textContent = 'WAIT';
        if (summary) summary.textContent = reason ? `No signal data — ${reason}. Click Refresh.` : 'Click Refresh for live analysis.';
        if (panel) panel.className = 'card mb-3 signal-wait';
    }
    
    getSignalBadge(data) {
        const confidence = data.confidence_pct || data.strength || 0;
        const volumeMultiplier = data.indicators?.volume?.spike_ratio || 1;
        const signalState = data.main_signal || 'WAIT';
        const timeCT = data.time_ct || '';
        
        // Parse CT time to check if after 2:30 PM (14:30)
        let hourCT = 0;
        if (timeCT) {
            const match = timeCT.match(/(\d+):(\d+)/);
            if (match) hourCT = parseInt(match[1]);
        }
        const isLateSession = hourCT >= 14 && parseInt(timeCT.split(':')[1]) >= 30;
        const isPreMarket = data.market_status?.current_session === 'PRE_MARKET';
        const isMarketHours = data.market_status?.current_session === 'REGULAR';
        
        // HOT badge rules: only show when confidence >= 85, volume >= 1.2x, 
        // and (BUY/SELL OR PREPARE during market hours)
        // Never show in pre-market or after 2:30 PM CT
        const isBuySell = signalState.includes('BUY') || signalState.includes('SELL');
        const isPrepareInMarket = signalState === 'PREPARE' && isMarketHours;
        
        const showHot = confidence >= 85 && 
                       volumeMultiplier >= 1.2 && 
                       (isBuySell || isPrepareInMarket) && 
                       !isPreMarket && 
                       !isLateSession;
        
        if (showHot) {
            return { type: 'hot', text: 'HOT', icon: 'bi-fire', class: 'bg-danger' };
        } else if (isBuySell) {
            return { type: 'confirmed', text: 'CONFIRMED', icon: 'bi-check-circle-fill', class: 'bg-success' };
        } else if (signalState === 'PREPARE') {
            return { type: 'watch', text: 'WATCH', icon: 'bi-eye-fill', class: 'bg-warning text-dark' };
        } else {
            return null; // No badge for NEUTRAL/WAIT
        }
    }
    
    checkHotStock(data) {
        const panel = document.getElementById('main-signal-panel');
        const badge = this.getSignalBadge(data);
        const isHot = badge?.type === 'hot';
        
        if (panel) {
            panel.classList.toggle('hot-stock', isHot);
        }
        
        // Remove existing badge
        const existingBadge = document.getElementById('signal-badge');
        if (existingBadge) existingBadge.remove();
        
        // Add new badge if applicable
        if (badge) {
            const signalText = document.getElementById('main-signal-text');
            if (signalText) {
                const badgeEl = document.createElement('span');
                badgeEl.id = 'signal-badge';
                badgeEl.className = `badge ${badge.class} ms-2`;
                badgeEl.innerHTML = `<i class="bi ${badge.icon}"></i> ${badge.text}`;
                badgeEl.style.cssText = 'font-size: 0.9rem; padding: 0.4em 0.6em;';
                signalText.parentNode.insertBefore(badgeEl, signalText.nextSibling);
            }
        }
        
        this.trackSignalPerformance(data);
    }
    
    toggleDebugMode() {
        this.debugMode = !this.debugMode;
        const panel = document.getElementById('debug-panel');
        const toggle = document.getElementById('debug-toggle');
        
        if (panel) {
            panel.style.display = this.debugMode ? 'block' : 'none';
        }
        if (toggle) {
            toggle.style.opacity = this.debugMode ? '1' : '0.4';
            toggle.classList.toggle('btn-outline-warning', this.debugMode);
            toggle.classList.toggle('btn-outline-dark', !this.debugMode);
        }
    }
    
    updateDebugPanel(data) {
        if (!this.debugMode) return;
        
        const setEl = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value || '--';
        };
        
        setEl('debug-time-ct', data.time_ct);
        setEl('debug-session', data.market_status?.current_session);
        setEl('debug-confidence', data.confidence_pct ? `${data.confidence_pct.toFixed(1)}%` : '--');
        setEl('debug-volume', data.indicators?.volume?.spike_ratio ? `${data.indicators.volume.spike_ratio.toFixed(2)}x` : '--');
        setEl('debug-signal', `${data.main_signal} (raw: ${data.raw_signal || '--'})`);
        setEl('debug-entry-window', data.entry_window);
        setEl('debug-entry-type', data.entry_type);
        setEl('debug-wait-for', data.wait_for_text || 'N/A');
        setEl('debug-15m-trend', data.higher_tf_trend || '--');
    }
    
    updateConfidenceFactors(data) {
        const setFactor = (id, label, pass) => {
            const el = document.getElementById(id);
            if (!el) return;
            if (pass === null || pass === undefined) {
                el.innerHTML = `<i class="bi bi-dash-circle"></i> ${label}: --`;
                el.className = 'text-secondary';
            } else if (pass) {
                el.innerHTML = `<i class="bi bi-check-circle-fill"></i> ${label}: Pass`;
                el.className = 'text-success';
            } else {
                el.innerHTML = `<i class="bi bi-x-circle-fill"></i> ${label}: Fail`;
                el.className = 'text-danger';
            }
        };
        
        const ind = data.indicators || {};
        const reasons = (data.reasons || []).join(' ').toLowerCase();
        
        const trendPass = reasons.includes('bullish') || reasons.includes('uptrend') || 
                          (ind.macd && ind.macd.histogram > 0 && data.direction === 'BULLISH') ||
                          (ind.macd && ind.macd.histogram < 0 && data.direction === 'BEARISH');
        const vwapPass = ind.vwap ? (data.direction === 'BULLISH' ? ind.vwap.above : !ind.vwap.above) : null;
        const volumePass = ind.volume ? ind.volume.spike_ratio >= 1.2 : null;
        const rsiPass = ind.rsi ? (ind.rsi.value >= 30 && ind.rsi.value <= 70) : null;
        const macdPass = ind.macd ? Math.abs(ind.macd.histogram) > 0.01 : null;
        const tfPass = data.timeframe_confluence ? data.timeframe_confluence >= 3 : null;
        
        setFactor('cf-trend', 'Trend', trendPass);
        setFactor('cf-vwap', 'VWAP', vwapPass);
        setFactor('cf-volume', 'Volume', volumePass);
        setFactor('cf-timeframes', 'Timeframes', tfPass);
        setFactor('cf-rsi', 'RSI', rsiPass);
        setFactor('cf-macd', 'MACD', macdPass);
    }
    
    updateTrafficLight(signal) {
        const lights = document.querySelectorAll('.traffic-light .light');
        lights.forEach(l => l.classList.remove('active'));
        
        if (signal === 'BUY' || signal === 'STRONG BUY') {
            document.querySelector('.traffic-light .light.green')?.classList.add('active');
        } else if (signal === 'SELL' || signal === 'STRONG SELL') {
            document.querySelector('.traffic-light .light.red')?.classList.add('active');
        } else if (signal === 'PREPARE') {
            document.querySelector('.traffic-light .light.yellow')?.classList.add('active');
        } else {
            document.querySelector('.traffic-light .light.yellow')?.classList.add('active');
        }
        
        const panel = document.getElementById('main-signal-panel');
        if (panel) {
            let signalClass = 'wait';
            if (signal === 'STRONG BUY') signalClass = 'strong-buy';
            else if (signal === 'BUY') signalClass = 'buy';
            else if (signal === 'STRONG SELL') signalClass = 'strong-sell';
            else if (signal === 'SELL') signalClass = 'sell';
            else if (signal === 'PREPARE') signalClass = 'prepare';
            else if (signal === 'WATCH') signalClass = 'watch';
            panel.className = 'card mb-3 signal-' + signalClass;
            
            if (this.lotteryHourActive) {
                panel.classList.add('lottery-hour-mode');
            }
        }
    }
    
    updateMainSignalPanel(data) {
        const signalText = document.getElementById('main-signal-text');
        if (signalText) {
            let displaySignal = data.main_signal;
            if (data.conviction_label) {
                displaySignal += ` <span class="badge bg-warning text-dark ms-2">${data.conviction_label}</span>`;
            }
            signalText.innerHTML = displaySignal;
        }
        
        const tfLabel = document.getElementById('chart-timeframe-label');
        const tfNote = tfLabel ? ` (${tfLabel.textContent} timeframe)` : '';
        
        const summary = document.getElementById('signal-summary');
        if (summary) summary.textContent = data.summary + tfNote;
        
        // Options Edge: one clear call (CALL / PUT / FLAT)
        const edgeEl = document.getElementById('signal-edge');
        if (edgeEl && data.edge_direction) {
            const oneLiner = data.edge_one_liner || '';
            if (data.edge_direction === 'FLAT') {
                edgeEl.innerHTML = `<span class="text-secondary">Edge: FLAT</span> — ${oneLiner}`;
            } else {
                const cls = data.edge_direction === 'CALL' ? 'text-success' : 'text-danger';
                const pct = (data.edge_pct != null && !isNaN(data.edge_pct)) ? data.edge_pct : '';
                edgeEl.innerHTML = `<span class="${cls}">Edge: ${data.edge_direction} ${pct}%</span> — ${oneLiner}`;
            }
            edgeEl.style.display = 'block';
        } else if (edgeEl) {
            edgeEl.style.display = 'none';
        }
        
        // Education text below signal
        const educationEl = document.getElementById('signal-education');
        if (educationEl) {
            educationEl.textContent = data.education_text || '';
            educationEl.style.display = data.education_text ? 'block' : 'none';
        }
        
        // "What I'm Waiting For" line for PREPARE signals
        const waitForEl = document.getElementById('signal-wait-for');
        if (waitForEl) {
            if (data.main_signal === 'PREPARE' && data.wait_for_text) {
                waitForEl.innerHTML = `<em>What I'm waiting for: ${data.wait_for_text}</em>`;
                waitForEl.style.display = 'block';
            } else {
                waitForEl.style.display = 'none';
            }
        }
        
        // Update debug panel if visible
        this.updateDebugPanel(data);
        
        const confidence = document.getElementById('signal-confidence');
        if (confidence) {
            const tierClass = data.confidence_tier === 'high' ? 'bg-success fw-bold' : 
                             data.confidence_tier === 'normal' ? 'bg-warning text-dark' : 'bg-secondary opacity-75';
            const confValue = (data.confidence_pct != null && !isNaN(data.confidence_pct)) 
                ? Math.round(data.confidence_pct) 
                : (data.strength || 50);
            let confHtml = `<span class="badge ${tierClass}">Confidence: ${confValue}%</span>`;
            confHtml += `<button class="btn btn-link btn-sm text-muted p-0 ms-2" type="button" data-bs-toggle="collapse" data-bs-target="#confidence-reasons" aria-expanded="false" title="Why this confidence?"><i class="bi bi-question-circle"></i> Why?</button>`;
            if (data.time_ct) {
                confHtml += ` <small class="text-muted ms-2">${data.time_ct}</small>`;
            }
            confidence.innerHTML = confHtml;
        }
        
        this.updateConfidenceFactors(data);
        
        const reasonsContainer = document.getElementById('signal-reasons');
        const reasonsList = document.getElementById('reasons-list');
        if (reasonsContainer && reasonsList && data.reasons && data.reasons.length > 0) {
            reasonsContainer.style.display = 'block';
            reasonsList.innerHTML = data.reasons.map(r => {
                const icon = r.includes('bullish') || r.includes('above') || r.includes('SPIKE') 
                    ? '<i class="bi bi-check-circle-fill text-success"></i>' 
                    : r.includes('bearish') || r.includes('below') || r.includes('overbought') || r.includes('Below')
                    ? '<i class="bi bi-x-circle-fill text-danger"></i>'
                    : '<i class="bi bi-dash-circle text-secondary"></i>';
                return `<li>${icon} ${r}</li>`;
            }).join('');
        } else if (reasonsContainer) {
            reasonsContainer.style.display = 'none';
        }
        
        if (data.main_signal === 'STRONG BUY' && this.lastSignal?.type !== 'STRONG BUY') {
            this.playStrongBuyAlert();
            this.logSignal(this.currentTicker, data.main_signal, data.current_price, data.strength, data.reasons);
        } else if (data.main_signal !== 'WAIT' && data.main_signal !== 'WATCH' && this.lastSignal?.type !== data.main_signal) {
            this.logSignal(this.currentTicker, data.main_signal, data.current_price, data.strength, data.reasons);
        }
    }
    
    updateRecommendationPanels(data) {
        const actionPanel = document.getElementById('recommended-action-panel');
        const whyPanel = document.getElementById('why-this-trade-panel');
        
        // Show panel for PREPARE signals too (bias forming)
        const showPanel = data.has_signal || data.main_signal === 'PREPARE';
        
        if (showPanel) {
            if (actionPanel) {
                actionPanel.style.display = 'block';
                let borderColor = data.main_signal.includes('BUY') ? 'success' : 
                                 data.main_signal.includes('SELL') ? 'danger' : 
                                 data.main_signal === 'PREPARE' ? 'warning' : 'secondary';
                let headerColor = data.main_signal.includes('BUY') ? 'bg-success' : 
                                 data.main_signal.includes('SELL') ? 'bg-danger' : 
                                 data.main_signal === 'PREPARE' ? 'bg-warning text-dark' : 'bg-secondary';
                actionPanel.className = `card bg-dark mb-3 border-${borderColor}`;
                const header = actionPanel.querySelector('.card-header');
                if (header) header.className = `card-header ${headerColor} fw-bold`;
            }
            
            const tradeRec = document.getElementById('trade-recommendation');
            if (tradeRec) {
                let textColor = data.main_signal.includes('BUY') ? 'success' : 
                               data.main_signal.includes('SELL') ? 'danger' : 
                               data.main_signal === 'PREPARE' ? 'warning' : 'secondary';
                let optionDisplay = data.option_type === '-' ? '' : data.option_type;
                let displayText = data.main_signal === 'PREPARE' ? `PREPARE ${this.currentTicker} ${optionDisplay}` :
                                 data.main_signal === 'WATCH' ? `WATCHING ${this.currentTicker}` :
                                 `${data.main_signal} ${this.currentTicker} ${optionDisplay}`;
                tradeRec.textContent = displayText.trim();
                tradeRec.className = `h5 text-${textColor}`;
            }
            
            const tradeReason = document.getElementById('trade-reason');
            if (tradeReason) tradeReason.textContent = data.summary;
            
            // Entry Window display
            const entryWindowEl = document.getElementById('entry-window');
            if (entryWindowEl) {
                entryWindowEl.textContent = data.entry_window || '';
            }
            
            // Entry Type display
            const entryTypeEl = document.getElementById('entry-type');
            if (entryTypeEl) {
                entryTypeEl.textContent = data.entry_type || '';
            }
            
            document.getElementById('entry-price')?.textContent && (document.getElementById('entry-price').textContent = '$' + data.entry.toFixed(2));
            document.getElementById('target-price')?.textContent && (document.getElementById('target-price').textContent = '$' + data.target.toFixed(2));
            document.getElementById('stop-price')?.textContent && (document.getElementById('stop-price').textContent = '$' + data.stop.toFixed(2));
            
            // Hard stop and stop guidance
            const hardStopEl = document.getElementById('hard-stop');
            if (hardStopEl) {
                const hardStopValue = (data.hard_stop != null && !isNaN(data.hard_stop)) ? data.hard_stop : data.stop;
                hardStopEl.textContent = `$${hardStopValue?.toFixed(2) || '--'}`;
            }
            const stopGuidanceEl = document.getElementById('stop-guidance');
            if (stopGuidanceEl) {
                stopGuidanceEl.textContent = data.stop_guidance || '';
            }
            const maxLossRuleEl = document.getElementById('max-loss-rule');
            if (maxLossRuleEl) {
                maxLossRuleEl.textContent = data.max_loss_rule || '';
            }
            
            const optionSuggestion = document.getElementById('option-suggestion');
            if (optionSuggestion) optionSuggestion.textContent = `${this.currentTicker} $${data.strike} ${data.option_type}`;
            
            document.getElementById('suggested-strike')?.textContent && (document.getElementById('suggested-strike').textContent = '$' + data.strike);
            document.getElementById('suggested-expiry')?.textContent && (document.getElementById('suggested-expiry').textContent = data.expiry);
            document.getElementById('position-size')?.textContent && (document.getElementById('position-size').textContent = data.position_contracts + ' contracts');
            document.getElementById('max-risk')?.textContent && (document.getElementById('max-risk').textContent = '$' + data.max_risk.toFixed(0));
            
            if (whyPanel) {
                whyPanel.style.display = 'block';
                const reasonsList = document.getElementById('trade-reasons-list');
                if (reasonsList && data.reasons) {
                    reasonsList.innerHTML = data.reasons.map(r => `<li class="text-light">${r}</li>`).join('');
                }
            }
        } else {
            if (actionPanel) actionPanel.style.display = 'none';
            if (whyPanel) whyPanel.style.display = 'none';
        }
    }
    
    updateIndicatorsSummary(indicators) {
        if (!indicators) return;
        
        const rsiValue = document.getElementById('rsi-value');
        const rsiSignal = document.getElementById('rsi-signal');
        if (rsiValue && indicators.rsi) {
            rsiValue.textContent = indicators.rsi.value?.toFixed(0) || '--';
            const rsiClass = indicators.rsi.value < 30 ? 'bg-success' : indicators.rsi.value > 70 ? 'bg-danger' : 'bg-secondary';
            if (rsiSignal) {
                rsiSignal.textContent = indicators.rsi.signal || 'NEUTRAL';
                rsiSignal.className = 'badge ' + rsiClass + ' small';
            }
        }
        
        const macdValue = document.getElementById('macd-value');
        const macdSignal = document.getElementById('macd-signal');
        if (macdValue && indicators.macd) {
            macdValue.textContent = indicators.macd.histogram?.toFixed(2) || '--';
            const macdType = indicators.macd.signal_type || 'NEUTRAL';
            const macdClass = macdType.includes('BULLISH') ? 'bg-success' : macdType.includes('BEARISH') ? 'bg-danger' : 'bg-secondary';
            if (macdSignal) {
                macdSignal.textContent = macdType;
                macdSignal.className = 'badge ' + macdClass + ' small';
            }
        }
        
        const bbPosition = document.getElementById('bb-position');
        const bbSignal = document.getElementById('bb-signal');
        if (bbPosition && indicators.bollinger) {
            bbPosition.textContent = indicators.bollinger.price_position || '--';
            if (bbSignal) {
                bbSignal.textContent = indicators.bollinger.signal || 'NEUTRAL';
                bbSignal.className = 'badge bg-secondary small';
            }
        }
        
        const volumeValue = document.getElementById('volume-value');
        const volumeSignal = document.getElementById('volume-signal');
        if (volumeValue && indicators.volume) {
            volumeValue.textContent = (indicators.volume.spike_ratio || 1).toFixed(1) + 'x';
            if (volumeSignal) {
                volumeSignal.textContent = indicators.volume.spike ? 'SPIKE' : 'Normal';
                volumeSignal.className = 'badge ' + (indicators.volume.spike ? 'bg-warning' : 'bg-secondary') + ' small';
            }
        }
        
        const vwapValue = document.getElementById('vwap-value');
        const vwapSignal = document.getElementById('vwap-signal');
        if (vwapValue && indicators.vwap) {
            vwapValue.textContent = indicators.vwap.above_vwap ? 'Above' : 'Below';
            if (vwapSignal) {
                vwapSignal.textContent = indicators.vwap.signal || 'NEUTRAL';
                vwapSignal.className = 'badge ' + (indicators.vwap.above_vwap ? 'bg-success' : 'bg-danger') + ' small';
            }
        }
        
        const trendValue = document.getElementById('trend-value');
        const trendSignal = document.getElementById('trend-signal');
        if (trendValue && indicators.trend) {
            trendValue.textContent = (indicators.trend.strength || 50) + '%';
            if (trendSignal) {
                const dir = indicators.trend.direction || 'NEUTRAL';
                trendSignal.textContent = dir;
                trendSignal.className = 'badge ' + (dir === 'BULLISH' ? 'bg-success' : dir === 'BEARISH' ? 'bg-danger' : 'bg-secondary') + ' small';
            }
        }
        
        if (indicators.ema) {
            const price = this.lastPrice || 0;
            const formatEma = (val, label) => {
                if (!val || val === 0) return '--';
                const arrow = price > val ? ' ↑' : price < val ? ' ↓' : '';
                const color = price > val ? '#22C55E' : price < val ? '#EF4444' : '#9CA3AF';
                return `<span style="color:${color}">$${val.toFixed(2)}${arrow}</span>`;
            };
            
            const el13 = document.getElementById('ema-13-value');
            const el48 = document.getElementById('ema-48-value');
            const el200 = document.getElementById('ema-200-value');
            if (el13) el13.innerHTML = formatEma(indicators.ema.ema_13);
            if (el48) el48.innerHTML = formatEma(indicators.ema.ema_48);
            if (el200) el200.innerHTML = formatEma(indicators.ema.ema_200);
            
            const crossoverAlert = document.getElementById('ema-crossover-alert');
            if (crossoverAlert && indicators.ema.crossovers && indicators.ema.crossovers.length > 0) {
                crossoverAlert.style.display = 'block';
                crossoverAlert.textContent = indicators.ema.crossovers.map(c => `${c.type} (${c.pair})`).join(', ');
            } else if (crossoverAlert) {
                crossoverAlert.style.display = 'none';
            }
        }
        
        let bullish = 0, bearish = 0;
        if (indicators.rsi?.value < 30) bullish++; else if (indicators.rsi?.value > 70) bearish++;
        if (indicators.macd?.signal_type?.includes('BULLISH')) bullish++; else if (indicators.macd?.signal_type?.includes('BEARISH')) bearish++;
        if (indicators.vwap?.above_vwap) bullish++; else bearish++;
        if (indicators.trend?.direction === 'BULLISH') bullish++; else if (indicators.trend?.direction === 'BEARISH') bearish++;
        
        const indicatorsSummary = document.getElementById('indicators-summary');
        if (indicatorsSummary) {
            indicatorsSummary.textContent = `${bullish} Bullish / ${bearish} Bearish`;
            indicatorsSummary.className = 'badge ' + (bullish > bearish ? 'bg-success' : bearish > bullish ? 'bg-danger' : 'bg-warning');
        }
        
        const stripPrice = document.getElementById('strip-price');
        const stripEma13 = document.getElementById('strip-ema13');
        const stripEma48 = document.getElementById('strip-ema48');
        const stripRsi = document.getElementById('strip-rsi');
        if (stripPrice && this.lastPrice) stripPrice.textContent = '$' + this.lastPrice.toFixed(2);
        if (stripEma13 && indicators.ema?.ema_13) stripEma13.textContent = indicators.ema.ema_13.toFixed(1);
        if (stripEma48 && indicators.ema?.ema_48) stripEma48.textContent = indicators.ema.ema_48.toFixed(1);
        if (stripRsi && indicators.rsi?.value) {
            const rsiVal = indicators.rsi.value.toFixed(0);
            const rsiColor = indicators.rsi.value < 30 ? '#22C55E' : indicators.rsi.value > 70 ? '#EF4444' : '#9CA3AF';
            stripRsi.innerHTML = `<span style="color:${rsiColor}">${rsiVal}</span>`;
        }
    }
    
    updatePriceDisplay(data) {
        this.lastPrice = data.current_price;
        // BYPASS: only loadTickerCardQuote may touch #current-price, #price-change
    }
    
    updateKeyLevels(sr, currentPrice) {
        if (!sr) return;
        
        document.getElementById('resistance-level')?.textContent && (document.getElementById('resistance-level').textContent = '$' + (sr.resistance || 0).toFixed(2));
        document.getElementById('support-level')?.textContent && (document.getElementById('support-level').textContent = '$' + (sr.support || 0).toFixed(2));
        document.getElementById('sr-current-price')?.textContent && (document.getElementById('sr-current-price').textContent = '$' + currentPrice.toFixed(2));
        
        const positionBar = document.getElementById('price-position-bar');
        if (positionBar && sr.support && sr.resistance) {
            const range = sr.resistance - sr.support;
            const position = range > 0 ? ((currentPrice - sr.support) / range) * 100 : 50;
            positionBar.style.width = Math.max(0, Math.min(100, position)) + '%';
        }
    }
    
    async loadChartData() {
        if (!this.chartCanvas) return;
        const requestedSymbol = (this.currentTicker || '').toUpperCase();
        try {
            const cacheBuster = Date.now();
            const ac = new AbortController();
            const t = setTimeout(() => ac.abort(), 15000);
            const response = await fetch(`/api/market-data/${requestedSymbol}?period=${this.currentPeriod}&interval=${this.currentInterval}&_t=${cacheBuster}`, { signal: ac.signal });
            clearTimeout(t);
            const data = await response.json();
            
            if ((this.currentTicker || '').toUpperCase() !== requestedSymbol) return;
            
            if (data.error) {
                if (this.chart?.data?.datasets?.[0]) this.chart.data.datasets[0].data = [];
                if (this.chart) this.chart.update('none');
                this.showChartNoData(true);
                return;
            }
            
            const ac2 = new AbortController();
            const t2 = setTimeout(() => ac2.abort(), 15000);
            const indicatorsRes = await fetch(`/api/indicators/${requestedSymbol}?period=${this.currentPeriod}&interval=${this.currentInterval}&_t=${cacheBuster}`, { signal: ac2.signal });
            clearTimeout(t2);
            const indicators = await indicatorsRes.json();
            if ((this.currentTicker || '').toUpperCase() !== requestedSymbol) return;
            
            if (this.chartType === 'candle' || this.chartType === 'heiken') {
                this.renderCandlestickChart(data, indicators);
            } else {
                this.renderLineChart(data, indicators);
            }
            if ((this.currentTicker || '').toUpperCase() !== requestedSymbol) return;
            if (data.volumes && data.closes && data.opens) {
                this.updateVolumeChart(data.volumes, data.closes, data.opens);
            }
        } catch (error) {
            console.warn('Chart load:', error);
            if (this.chart?.data?.datasets?.[0]) this.chart.data.datasets[0].data = [];
            if (this.chart) this.chart.update('none');
            this.showChartNoData(true);
        }
    }
    
    showChartNoData(show) {
        const el = document.getElementById('chart-no-data');
        if (el) {
            if (show) el.classList.remove('d-none'); else el.classList.add('d-none');
        }
    }
    
    renderLineChart(data, indicators) {
        if (!this.chart || this.chart.config.type !== 'line') {
            this.createLineChart();
        }
        
        const labels = data.timestamps?.map(t => {
            const d = new Date(t);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }) || [];
        
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = data.closes || [];
        
        if (indicators.ema) {
            const len = labels.length;
            this.chart.data.datasets[1].data = this.padArray(indicators.ema.ema_13_series || [], len);
            this.chart.data.datasets[2].data = this.padArray(indicators.ema.ema_48_series || [], len);
            this.chart.data.datasets[3].data = this.padArray(indicators.ema.ema_200_series || [], len);
            
            this.chart.data.datasets[1].hidden = !this.indicatorToggles.ema13;
            this.chart.data.datasets[2].hidden = !this.indicatorToggles.ema48;
            this.chart.data.datasets[3].hidden = !this.indicatorToggles.ema200;
        }
        
        const support = indicators.support_resistance?.support || (data.closes ? Math.min(...data.closes) * 0.998 : 0);
        const resistance = indicators.support_resistance?.resistance || (data.closes ? Math.max(...data.closes) * 1.002 : 0);
        this.chart.data.datasets[4].data = new Array(labels.length).fill(support);
        this.chart.data.datasets[5].data = new Array(labels.length).fill(resistance);
        
        if (indicators.rsi?.series) {
            const rsiSeries = this.padArray(indicators.rsi.series, labels.length);
            this.chart.data.datasets[6].data = rsiSeries;
            this.chart.data.datasets[7].data = new Array(labels.length).fill(30);
            this.chart.data.datasets[8].data = new Array(labels.length).fill(70);
        }
        
        this.chart.update('none');
        this.showChartNoData(false);
    }
    
    renderCandlestickChart(data, indicators) {
        const useCandlestick = typeof Chart.controllers?.candlestick !== 'undefined';
        
        if (!useCandlestick) {
            this.renderOHLCBars(data, indicators);
            return;
        }
        
        if (!this.chart || this.chart.config.type !== 'candlestick') {
            this.createCandlestickChart();
        }
        
        const config = this.TIMEFRAME_CONFIG[this.currentInterval] || this.TIMEFRAME_CONFIG['5m'];
        const maxPoints = config.maxPoints;
        
        const sliceStart = Math.max(0, data.timestamps.length - maxPoints);
        const timestamps = data.timestamps.slice(sliceStart);
        const opens = data.opens.slice(sliceStart);
        const highs = data.highs.slice(sliceStart);
        const lows = data.lows.slice(sliceStart);
        const closes = data.closes.slice(sliceStart);
        
        let ohlcData;
        if (this.chartType === 'heiken' && indicators.heiken_ashi) {
            const ha = indicators.heiken_ashi;
            const haOpens = ha.opens.slice(sliceStart);
            const haHighs = ha.highs.slice(sliceStart);
            const haLows = ha.lows.slice(sliceStart);
            const haCloses = ha.closes.slice(sliceStart);
            ohlcData = timestamps.map((t, i) => ({
                x: new Date(t).getTime(),
                o: haOpens[i] || opens[i],
                h: haHighs[i] || highs[i],
                l: haLows[i] || lows[i],
                c: haCloses[i] || closes[i]
            }));
        } else {
            ohlcData = timestamps.map((t, i) => ({
                x: new Date(t).getTime(),
                o: opens[i],
                h: highs[i],
                l: lows[i],
                c: closes[i]
            }));
        }
        
        this.chart.data.datasets[0].data = ohlcData;
        this.chart.data.datasets[0].barThickness = config.barThickness;
        this.chart.data.datasets[0].maxBarThickness = config.barThickness + 4;
        
        if (this.chart.options.scales.x.time) {
            this.chart.options.scales.x.time.unit = config.timeUnit;
            this.chart.options.scales.x.time.stepSize = config.stepSize;
        }
        
        if (indicators.ema) {
            const emaData = (series) => timestamps.map((t, i) => ({
                x: new Date(t).getTime(),
                y: series[i] || null
            }));
            
            const ema13Sliced = (indicators.ema.ema_13_series || []).slice(sliceStart);
            const ema48Sliced = (indicators.ema.ema_48_series || []).slice(sliceStart);
            const ema200Sliced = (indicators.ema.ema_200_series || []).slice(sliceStart);
            this.chart.data.datasets[1].data = emaData(this.padArray(ema13Sliced, timestamps.length));
            this.chart.data.datasets[2].data = emaData(this.padArray(ema48Sliced, timestamps.length));
            this.chart.data.datasets[3].data = emaData(this.padArray(ema200Sliced, timestamps.length));
        }
        
        this.chart.update('none');
        this.showChartNoData(false);
    }
    
    renderOHLCBars(data, indicators) {
        if (!this.chart || this.chart.config.type !== 'bar') {
            if (this.chart) this.chart.destroy();
            
            this.chart = new Chart(this.chartCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Range', data: [], backgroundColor: [], borderColor: [], borderWidth: 2, barPercentage: 0.8 },
                        { type: 'line', label: 'EMA 13', data: [], borderColor: '#FCD34D', borderWidth: 1.5, fill: false, pointRadius: 0 },
                        { type: 'line', label: 'EMA 48', data: [], borderColor: '#FB923C', borderWidth: 1.5, fill: false, pointRadius: 0 },
                        { type: 'line', label: 'EMA 200', data: [], borderColor: '#C084FC', borderWidth: 1.5, fill: false, pointRadius: 0 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `O: ${data.opens[ctx.dataIndex]?.toFixed(2)} H: ${data.highs[ctx.dataIndex]?.toFixed(2)} L: ${data.lows[ctx.dataIndex]?.toFixed(2)} C: ${data.closes[ctx.dataIndex]?.toFixed(2)}` } } },
                    scales: {
                        x: { display: true, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', maxTicksLimit: 8 } },
                        y: { display: true, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888' } }
                    }
                }
            });
        }
        
        const labels = data.timestamps?.map(t => {
            const d = new Date(t);
            return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }) || [];
        
        let opens, highs, lows, closes;
        if (this.chartType === 'heiken' && indicators.heiken_ashi) {
            opens = indicators.heiken_ashi.opens;
            highs = indicators.heiken_ashi.highs;
            lows = indicators.heiken_ashi.lows;
            closes = indicators.heiken_ashi.closes;
        } else {
            opens = data.opens;
            highs = data.highs;
            lows = data.lows;
            closes = data.closes;
        }
        
        const barData = [];
        const bgColors = [];
        const bdColors = [];
        
        for (let i = 0; i < closes.length; i++) {
            const bullish = closes[i] >= opens[i];
            barData.push([lows[i], highs[i]]);
            bgColors.push(bullish ? 'rgba(0, 230, 118, 0.7)' : 'rgba(255, 82, 82, 0.7)');
            bdColors.push(bullish ? '#00e676' : '#ff5252');
        }
        
        this.chart.data.labels = labels;
        this.chart.data.datasets[0].data = barData;
        this.chart.data.datasets[0].backgroundColor = bgColors;
        this.chart.data.datasets[0].borderColor = bdColors;
        
        if (indicators.ema) {
            const len = labels.length;
            this.chart.data.datasets[1].data = this.padArray(indicators.ema.ema_13_series || [], len);
            this.chart.data.datasets[2].data = this.padArray(indicators.ema.ema_48_series || [], len);
            this.chart.data.datasets[3].data = this.padArray(indicators.ema.ema_200_series || [], len);
        }
        
        this.chart.update('none');
        this.showChartNoData(false);
    }
    
    padArray(arr, targetLen) {
        if (arr.length >= targetLen) return arr.slice(-targetLen);
        const padding = new Array(targetLen - arr.length).fill(null);
        return [...padding, ...arr];
    }
    
    async loadAdvancedData() {
        try {
            const [analysisRes, vixRes, optionsRes] = await Promise.all([
                fetch(`/api/comprehensive-analysis/${this.currentTicker}`),
                fetch('/api/vix'),
                fetch(`/api/options-flow/${this.currentTicker}`)
            ]);
            
            const analysis = await analysisRes.json();
            const vix = await vixRes.json();
            const options = await optionsRes.json();
            
            this.updateMultiTimeframeDisplay(analysis);
            this.updateVixDisplay(vix);
            this.updateOptionsFlowDisplay(options);
            this.updateInstitutionalDisplay(analysis.institutional);
            
        } catch (error) {
            console.error('Error loading advanced data:', error);
        }
    }
    
    updateMultiTimeframeDisplay(data) {
        if (!data.timeframe_trends) return;
        
        ['1m', '5m', '15m', '1h', '4h'].forEach(tf => {
            const el = document.getElementById(`tf-${tf}`);
            if (el) {
                const trend = data.timeframe_trends[tf] || 'NEUTRAL';
                el.textContent = trend;
                el.className = 'badge ' + (trend === 'BULLISH' ? 'bg-success' : trend === 'BEARISH' ? 'bg-danger' : 'bg-warning');
                
                if (tf === this.currentInterval) {
                    el.classList.add('border', 'border-white');
                }
            }
        });
        
        const confluenceEl = document.getElementById('confluence-score');
        if (confluenceEl && data.confluence_score !== undefined) {
            confluenceEl.textContent = data.confluence_score.toFixed(1);
            confluenceEl.className = data.confluence_score > 0 ? 'fw-bold text-success' : data.confluence_score < 0 ? 'fw-bold text-danger' : 'fw-bold text-warning';
        }
    }
    
    updateVixDisplay(vix) {
        document.getElementById('vix-value')?.textContent && (document.getElementById('vix-value').textContent = vix.current?.toFixed(2) || '--');
        document.getElementById('vix-trend')?.textContent && (document.getElementById('vix-trend').textContent = vix.trend || '--');
        
        const vixBadge = document.getElementById('vix-regime-badge');
        if (vixBadge) {
            const regime = vix.regime || 'NORMAL';
            vixBadge.textContent = regime;
            vixBadge.className = 'badge ms-2 ' + (regime === 'LOW' ? 'bg-success' : regime === 'HIGH' ? 'bg-danger' : 'bg-info');
        }
    }
    
    updateOptionsFlowDisplay(options) {
        if (options.error) return;
        
        document.getElementById('pc-ratio')?.textContent && (document.getElementById('pc-ratio').textContent = options.put_call_ratio?.toFixed(2) || '--');
        document.getElementById('total-call-vol')?.textContent && (document.getElementById('total-call-vol').textContent = this.formatNumber(options.total_call_volume || 0));
        document.getElementById('total-put-vol')?.textContent && (document.getElementById('total-put-vol').textContent = this.formatNumber(options.total_put_volume || 0));
        
        const hotCalls = document.getElementById('hot-calls-badge');
        const unusualPuts = document.getElementById('unusual-puts-badge');
        const blockTrades = document.getElementById('block-trades-badge');
        const sweeps = document.getElementById('sweeps-badge');
        
        if (hotCalls) hotCalls.style.display = options.indicators?.hot_calls ? 'inline-block' : 'none';
        if (unusualPuts) unusualPuts.style.display = options.indicators?.unusual_puts ? 'inline-block' : 'none';
        if (blockTrades) blockTrades.style.display = options.indicators?.block_trades ? 'inline-block' : 'none';
        if (sweeps) sweeps.style.display = options.indicators?.sweeps ? 'inline-block' : 'none';
    }
    
    updateInstitutionalDisplay(institutional) {
        if (!institutional) return;
        
        const activity = document.getElementById('institutional-activity');
        if (activity) {
            activity.textContent = institutional.activity_level || 'NORMAL';
            activity.className = 'h5 mb-0 ' + (institutional.activity_level === 'HIGH' ? 'text-warning' : 'text-secondary');
        }
        
        document.getElementById('inst-buy-spikes')?.textContent && (document.getElementById('inst-buy-spikes').textContent = institutional.bullish_spikes || 0);
        document.getElementById('inst-sell-spikes')?.textContent && (document.getElementById('inst-sell-spikes').textContent = institutional.bearish_spikes || 0);
    }
    
    addSignalToFeed(signal, prepend = true) {
        const feed = document.getElementById('signal-feed');
        if (!feed) return;
        
        if (feed.querySelector('.text-muted.text-center')) feed.innerHTML = '';
        
        const item = document.createElement('div');
        item.className = 'list-group-item bg-dark border-secondary py-2';
        
        const typeClass = signal.signal_type?.includes('BUY') ? 'text-success' : 
                         signal.signal_type?.includes('SELL') ? 'text-danger' : 'text-warning';
        
        const time = signal.timestamp ? new Date(signal.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '--:--';
        
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <span class="fw-bold text-light">${signal.symbol || '--'}</span>
                    <span class="badge ${typeClass.replace('text-', 'bg-')} ms-2">${signal.signal_type || '--'}</span>
                </div>
                <small class="text-muted">${time}</small>
            </div>
            <div class="small text-light">$${(signal.price || 0).toFixed(2)} | ${signal.strength || 0}%</div>
        `;
        
        if (prepend) {
            feed.prepend(item);
            while (feed.children.length > 10) feed.removeChild(feed.lastChild);
        } else {
            feed.appendChild(item);
        }
    }
    
    async addTicker() {
        const input = document.getElementById('new-ticker');
        if (!input) return;
        
        const raw = input.value.trim();
        if (!raw) return;
        
        const submitBtn = document.getElementById('add-ticker-submit');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Adding...';
        }
        
        try {
            const ac = new AbortController();
            const timeoutId = setTimeout(() => ac.abort(), 15000);
            const res = await fetch('/api/tickers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: raw }),
                signal: ac.signal
            });
            clearTimeout(timeoutId);
            const data = await res.json().catch(() => ({}));
            
            input.value = '';
            const select = document.getElementById('ticker-select');
            let firstSymbol = (raw.replace(/,/g, ' ').split(/\s+/).map(s => s.trim().toUpperCase()).filter(Boolean))[0] || raw.trim().toUpperCase();

            if (!res.ok) {
                this.showTickerToast((data.error || 'Could not save to list') + '; loading data…', 'warning');
                if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Add'; }
                if (select && firstSymbol) {
                    const exists = Array.from(select.options).some(opt => opt.value === firstSymbol);
                    if (!exists) {
                        const opt = document.createElement('option');
                        opt.value = firstSymbol;
                        opt.textContent = firstSymbol;
                        select.appendChild(opt);
                    }
                    select.value = firstSymbol;
                    this.currentTicker = firstSymbol;
                    this.showTickerLoading(true);
                    await this.refreshData();
                }
                const modal = bootstrap.Modal.getInstance(document.getElementById('addTickerModal'));
                if (modal) modal.hide();
                return;
            }
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Add'; }

            const added = data.added || (data.symbol ? [data] : []);
            const errors = data.errors || [];
            added.forEach(t => { this.scannerTickerSelection[t.symbol] = true; });
            this.saveScannerSelection();

            await this.loadTickers();

            if (added.length) {
                firstSymbol = added[0].symbol || added[0];
                this.currentTicker = firstSymbol;
                if (select) select.value = firstSymbol;
                this.showTickerToast(`Added: ${added.map(t => t.symbol).join(', ')}. Loading data…`, 'success');
                this.showTickerLoading(true);
                await this.refreshData();
            } else if (firstSymbol && select && Array.from(select.options).some(opt => opt.value === firstSymbol)) {
                this.currentTicker = firstSymbol;
                select.value = firstSymbol;
                this.showTickerLoading(true);
                await this.refreshData();
            }
            if (errors.length) this.showTickerToast(errors.slice(0, 3).join('; '), 'warning');
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('addTickerModal'));
            if (modal) modal.hide();
        } catch (error) {
            console.error('Error adding ticker:', error);
            this.showTickerToast('Network error or timeout. Try again or click Refresh.', 'danger');
            const modal = bootstrap.Modal.getInstance(document.getElementById('addTickerModal'));
            if (modal) modal.hide();
        } finally {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Add'; }
        }
    }
    
    showTickerToast(message, type) {
        const id = 'ticker-toast-' + Date.now();
        const el = document.createElement('div');
        el.id = id;
        el.className = `alert alert-${type} position-fixed top-0 start-50 translate-middle-x mt-3 shadow`;
        el.style.zIndex = '9999';
        el.setAttribute('role', 'alert');
        el.textContent = message;
        document.body.appendChild(el);
        setTimeout(() => { const e = document.getElementById(id); if (e) e.remove(); }, 5000);
    }
    
    confirmRemoveTicker() {
        const select = document.getElementById('ticker-select');
        if (!select) return;
        
        const tickerCount = select.options.length;
        if (tickerCount <= 1) {
            this.showRemoveError();
            return;
        }
        
        const symbol = this.currentTicker;
        this.showRemoveConfirmation(symbol);
    }
    
    showRemoveError() {
        const existingModal = document.getElementById('removeErrorModal');
        if (existingModal) existingModal.remove();
        
        const modal = document.createElement('div');
        modal.id = 'removeErrorModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-sm">
                <div class="modal-content bg-dark text-light border-danger">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title text-danger"><i class="bi bi-exclamation-triangle"></i> Cannot Remove</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <p class="text-light mb-0">At least one ticker must remain in the watchlist.</p>
                    </div>
                    <div class="modal-footer border-secondary justify-content-center">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">OK</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        modal.addEventListener('hidden.bs.modal', () => modal.remove());
    }
    
    showRemoveConfirmation(symbol) {
        const existingModal = document.getElementById('removeConfirmModal');
        if (existingModal) existingModal.remove();
        
        const modal = document.createElement('div');
        modal.id = 'removeConfirmModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-sm">
                <div class="modal-content bg-dark text-light border-warning">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title"><i class="bi bi-trash"></i> Remove Ticker</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <p class="text-light">Remove <strong class="text-warning">${symbol}</strong> from watchlist?</p>
                    </div>
                    <div class="modal-footer border-secondary justify-content-center">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-danger" id="confirm-remove-btn">Remove</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        
        document.getElementById('confirm-remove-btn').addEventListener('click', async () => {
            bsModal.hide();
            await this.removeTicker(symbol);
        });
        
        modal.addEventListener('hidden.bs.modal', () => modal.remove());
    }
    
    async removeTicker(symbol) {
        try {
            await fetch(`/api/tickers/${symbol}`, { method: 'DELETE' });
            
            this.clearTickerData(symbol);
            
            delete this.scannerTickerSelection[symbol];
            this.saveScannerSelection();
            
            await this.loadTickers();
            
            this.refreshData();
            
        } catch (error) {
            console.error('Error removing ticker:', error);
        }
    }
    
    clearTickerData(symbol) {
        const feed = document.getElementById('signal-feed');
        if (feed) {
            const items = feed.querySelectorAll('.list-group-item');
            items.forEach(item => {
                if (item.textContent.includes(symbol)) {
                    item.remove();
                }
            });
        }
    }
    
    async saveSettings() {
        this.indicatorToggles = {
            rsi: document.getElementById('toggle-rsi')?.checked ?? true,
            macd: document.getElementById('toggle-macd')?.checked ?? true,
            bollinger: document.getElementById('toggle-bollinger')?.checked ?? true,
            ema13: document.getElementById('toggle-ema13')?.checked ?? true,
            ema48: document.getElementById('toggle-ema48')?.checked ?? true,
            ema200: document.getElementById('toggle-ema200')?.checked ?? true,
            vwap: document.getElementById('toggle-vwap')?.checked ?? true,
            volume: document.getElementById('toggle-volume')?.checked ?? true,
            sr: document.getElementById('toggle-sr')?.checked ?? true
        };
        
        localStorage.setItem('indicatorToggles', JSON.stringify(this.indicatorToggles));
        
        const settings = {
            rsi_period: parseInt(document.getElementById('rsi-period')?.value) || 14,
            rsi_oversold: parseInt(document.getElementById('rsi-oversold')?.value) || 30,
            rsi_overbought: parseInt(document.getElementById('rsi-overbought')?.value) || 70,
            volume_spike_threshold: parseFloat(document.getElementById('volume-threshold')?.value) || 2.0,
            audio_enabled: document.getElementById('audio-notifications')?.checked ?? true,
            audio_volume: parseInt(document.getElementById('audio-volume')?.value) || 50
        };
        
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            this.settings = settings;
            this.audioEnabled = settings.audio_enabled;
            this.audioVolume = settings.audio_volume / 100;
            
            this.loadChartData();
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
            if (modal) modal.hide();
        } catch (error) {
            console.error('Error saving settings:', error);
        }
    }
    
    updateIndicatorCount() {
        let count = 0;
        document.querySelectorAll('[id^="toggle-"]').forEach(toggle => {
            if (toggle.checked) count++;
        });
        
        const countEl = document.getElementById('active-indicator-count');
        if (countEl) countEl.textContent = `Using ${count} of 10`;
    }
    
    updateAudioToggle() {
        const toggle = document.getElementById('audio-toggle');
        if (toggle) {
            toggle.innerHTML = this.audioEnabled ? '<i class="bi bi-volume-up"></i>' : '<i class="bi bi-volume-mute"></i>';
            toggle.className = 'btn btn-sm ' + (this.audioEnabled ? 'btn-outline-success' : 'btn-outline-secondary');
        }
    }
    
    playBuyAlert() {
        if (!this.audioContext) return;
        
        const frequencies = [440, 523, 659];
        const duration = 0.15;
        
        frequencies.forEach((freq, i) => {
            setTimeout(() => {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                osc.frequency.value = freq;
                osc.type = 'sine';
                gain.gain.value = this.audioVolume * 0.3;
                gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + duration);
                osc.start();
                osc.stop(this.audioContext.currentTime + duration);
            }, i * 120);
        });
    }
    
    playSellAlert() {
        if (!this.audioContext) return;
        
        const frequencies = [523, 349];
        const duration = 0.2;
        
        frequencies.forEach((freq, i) => {
            setTimeout(() => {
                const osc = this.audioContext.createOscillator();
                const gain = this.audioContext.createGain();
                osc.connect(gain);
                gain.connect(this.audioContext.destination);
                osc.frequency.value = freq;
                osc.type = 'sine';
                gain.gain.value = this.audioVolume * 0.3;
                gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + duration);
                osc.start();
                osc.stop(this.audioContext.currentTime + duration);
            }, i * 150);
        });
    }
    
    playAlert(signalType) {
        if (signalType?.includes('BUY')) this.playBuyAlert();
        else if (signalType?.includes('SELL')) this.playSellAlert();
    }
    
    async loadPaperAccount() {
        try {
            const response = await fetch('/api/paper-account');
            const data = await response.json();
            
            const balance = document.getElementById('paper-balance');
            if (balance && data.balance !== undefined) {
                balance.textContent = '$' + data.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            
            const positions = document.getElementById('paper-positions');
            if (positions && data.positions) {
                if (data.positions.length === 0) {
                    positions.innerHTML = '<div class="text-muted text-center">No open positions</div>';
                } else {
                    positions.innerHTML = data.positions.map(p => `
                        <div class="d-flex justify-content-between border-bottom border-secondary py-1">
                            <span class="text-light">${p.symbol} ${p.side.toUpperCase()}</span>
                            <span class="${p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}">$${p.unrealized_pnl.toFixed(2)}</span>
                        </div>
                    `).join('');
                }
            }
        } catch (error) {
            console.error('Error loading paper account:', error);
        }
    }
    
    openPaperTrade(side) {
        this.paperTradeSide = side;
        
        const title = document.getElementById('paper-trade-title');
        if (title) title.textContent = side === 'long' ? 'Buy (Long)' : 'Sell (Short)';
        
        const symbol = document.getElementById('paper-symbol');
        if (symbol) symbol.value = this.currentTicker;
        
        const execute = document.getElementById('paper-execute');
        if (execute) {
            execute.className = 'btn btn-sm ' + (side === 'long' ? 'btn-success' : 'btn-danger');
            execute.textContent = side === 'long' ? 'Buy' : 'Sell';
        }
        
        const modal = new bootstrap.Modal(document.getElementById('paperTradeModal'));
        modal.show();
    }
    
    async executePaperTrade() {
        const symbol = document.getElementById('paper-symbol')?.value;
        const quantity = parseInt(document.getElementById('paper-quantity')?.value) || 10;
        
        try {
            await fetch('/api/paper-trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol, side: this.paperTradeSide, quantity })
            });
            
            const modal = bootstrap.Modal.getInstance(document.getElementById('paperTradeModal'));
            if (modal) modal.hide();
            
            await this.loadPaperAccount();
        } catch (error) {
            console.error('Error executing paper trade:', error);
        }
    }
    
    async scanTop10() {
        const selectedTickers = this.getSelectedScannerTickers();
        
        if (selectedTickers.length === 0) {
            this.showScannerError();
            return;
        }
        
        const btn = document.getElementById('scan-top-10-btn');
        const loading = document.getElementById('scanner-loading');
        const loadingText = document.getElementById('scanner-loading-text');
        const results = document.getElementById('scanner-results');
        const summary = document.getElementById('scanner-summary');
        
        const filters = {
            bullish_only: document.getElementById('filter-bullish')?.checked || false,
            bearish_only: document.getElementById('filter-bearish')?.checked || false,
            min_score: document.getElementById('filter-high-score')?.checked ? 90 : 0,
            tickers: selectedTickers
        };
        
        if (btn) btn.disabled = true;
        if (loading) loading.style.display = 'block';
        if (loadingText) {
            const tickerList = selectedTickers.slice(0, 3).join(', ');
            const more = selectedTickers.length > 3 ? `... (${selectedTickers.length} tickers)` : ` (${selectedTickers.length} ticker${selectedTickers.length > 1 ? 's' : ''})`;
            loadingText.textContent = `Scanning ${tickerList}${more}`;
        }
        if (results) results.innerHTML = '';
        if (summary) summary.style.display = 'none';
        
        try {
            const response = await fetch('/api/scan-top-10', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filters)
            });
            
            const data = await response.json();
            
            if (summary && data.summary) {
                document.getElementById('summary-analyzed').textContent = `${data.summary.successful}/${data.summary.total_analyzed}`;
                document.getElementById('summary-bullish').textContent = data.summary.bullish_setups;
                document.getElementById('summary-bearish').textContent = data.summary.bearish_setups;
                document.getElementById('summary-high-conf').textContent = data.summary.high_confidence;
                summary.style.display = 'block';
            }
            
            const advice = document.getElementById('session-advice');
            if (advice) advice.textContent = data.session_advice || '';
            
            if (results) {
                if (!data.results || data.results.length === 0) {
                    results.innerHTML = '<div class="text-center text-muted py-3">No stocks matched your filters</div>';
                } else {
                    results.innerHTML = data.results.map(r => this.renderScanResult(r)).join('');
                }
            }
            
        } catch (error) {
            console.error('Scan error:', error);
            if (results) results.innerHTML = '<div class="text-center text-danger py-3">Error scanning markets</div>';
        } finally {
            if (btn) btn.disabled = false;
            if (loading) loading.style.display = 'none';
        }
    }
    
    showScannerError() {
        const existingModal = document.getElementById('scannerErrorModal');
        if (existingModal) existingModal.remove();
        
        const modal = document.createElement('div');
        modal.id = 'scannerErrorModal';
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered modal-sm">
                <div class="modal-content bg-dark text-light border-warning">
                    <div class="modal-header border-secondary">
                        <h5 class="modal-title text-warning"><i class="bi bi-exclamation-triangle"></i> No Tickers Selected</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body text-center">
                        <p class="text-light mb-0">Please select at least one ticker to scan.</p>
                    </div>
                    <div class="modal-footer border-secondary justify-content-center">
                        <button type="button" class="btn btn-primary" data-bs-dismiss="modal">OK</button>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
        modal.addEventListener('hidden.bs.modal', () => modal.remove());
    }
    
    renderScanResult(result) {
        const direction = result.direction || 'NEUTRAL';
        const directionClass = direction === 'BULLISH' ? 'success' : direction === 'BEARISH' ? 'danger' : 'warning';
        const tradeScore = result.trade_score || 0;
        const reasons = result.reasons || [];
        
        return `
            <div class="scanner-result border border-${directionClass} rounded p-2 mb-2">
                <div class="d-flex justify-content-between align-items-center">
                    <span class="fw-bold text-light">${result.medal || ''} ${result.symbol}</span>
                    <span class="badge bg-${directionClass}">${tradeScore}/100</span>
                </div>
                <div class="small text-light">${reasons.slice(0, 2).join(', ') || 'No strong signals'}</div>
                <button class="btn btn-outline-${directionClass} btn-sm mt-1 w-100" onclick="app.switchToTicker('${result.symbol}')">
                    View ${result.symbol}
                </button>
            </div>
        `;
    }
    
    switchToTicker(symbol) {
        const select = document.getElementById('ticker-select');
        if (select) {
            const exists = Array.from(select.options).some(opt => opt.value === symbol);
            if (!exists) {
                const option = document.createElement('option');
                option.value = symbol;
                option.textContent = symbol;
                select.appendChild(option);
            }
            select.value = symbol;
            this.currentTicker = symbol;
            this.socket.emit('subscribe', { symbol: this.currentTicker });
            this.refreshData();
        }
    }
    
    formatNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
        return num.toString();
    }
    
    initCheapOptionRadar() {
        const refreshBtn = document.getElementById('radar-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.scanCheapOptions());
        }
        this.scanCheapOptions();
    }
    
    async scanCheapOptions() {
        const statusEl = document.getElementById('radar-status');
        const resultsEl = document.getElementById('radar-results');
        const refreshBtn = document.getElementById('radar-refresh-btn');
        
        if (!resultsEl) return;
        
        if (statusEl) statusEl.style.display = 'block';
        if (refreshBtn) refreshBtn.disabled = true;
        resultsEl.innerHTML = '<div class="text-center text-muted small py-2"><i class="bi bi-hourglass-split"></i> Scanning 50 liquid stocks...</div>';
        
        try {
            const response = await fetch('/api/cheap-options?limit=10');
            const data = await response.json();
            
            if (statusEl) statusEl.style.display = 'none';
            if (refreshBtn) refreshBtn.disabled = false;
            
            if (data.candidates && data.candidates.length > 0) {
                let html = '';
                data.candidates.forEach((c, i) => {
                    const directionClass = c.direction === 'CALLS' ? 'success' : c.direction === 'PUTS' ? 'danger' : 'secondary';
                    const directionLabel = c.direction === 'CALLS' ? 'CALL' : c.direction === 'PUTS' ? 'PUT' : '—';
                    const changeSign = c.intraday_change >= 0 ? '+' : '';
                    const changeClass = c.intraday_change >= 0 ? 'success' : 'danger';
                    
                    html += `
                        <div class="card bg-dark border-${directionClass} mb-2">
                            <div class="card-body py-2 px-3">
                                <div class="d-flex justify-content-between align-items-center">
                                    <div>
                                        <span class="h6 mb-0 me-2">#${i + 1}</span>
                                        <span class="fw-bold text-light me-2">${c.symbol}</span>
                                        <span class="badge bg-${directionClass}">${directionLabel}</span>
                                    </div>
                                    <div class="text-end">
                                        <div class="text-light">$${c.price.toFixed(2)}</div>
                                        <small class="text-${changeClass}">${changeSign}${c.intraday_change}%</small>
                                    </div>
                                </div>
                                ${c.option ? `
                                <div class="small text-muted mt-1">
                                    Strike: $${c.option.strike} <span class="text-${changeClass}">±${(Math.abs(c.option.strike - c.price) / c.price * 100).toFixed(0)}%</span> | 
                                    Premium: <span class="text-success">$${c.option.premium.toFixed(2)}</span>
                                </div>` : ''}
                                <div class="small text-muted mt-1">
                                    ${c.reasons.slice(0, 2).join(' | ')}
                                </div>
                                <div class="d-flex gap-2 mt-1">
                                    <span class="badge bg-secondary small"><i class="bi bi-graph-up"></i> ${c.rvol}x Vol</span>
                                    <span class="badge bg-secondary small"><i class="bi bi-activity"></i> RSI ${c.rsi || '--'}</span>
                                    <span class="badge bg-warning text-dark small">${c.score} pts</span>
                                </div>
                            </div>
                        </div>
                    `;
                });
                resultsEl.innerHTML = html;
            } else {
                resultsEl.innerHTML = `
                    <div class="text-center text-muted small py-3">
                        <i class="bi bi-info-circle"></i> No cheap options found (market may be closed)
                    </div>
                `;
            }
        } catch (error) {
            console.error('Cheap option radar error:', error);
            if (statusEl) statusEl.style.display = 'none';
            if (refreshBtn) refreshBtn.disabled = false;
            resultsEl.innerHTML = `
                <div class="text-center text-danger small py-3">
                    <i class="bi bi-exclamation-triangle"></i> Error scanning: ${error.message}
                </div>
            `;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new TradingSignalsApp();
    window.tradingApp = window.app;
    window.app.initCheapOptionRadar();
});
