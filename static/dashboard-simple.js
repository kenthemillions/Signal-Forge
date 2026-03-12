(function() {
    "use strict";
    try {
        var _s = localStorage.getItem("user_settings");
        window.DEVELOPER_MODE = _s ? !!(JSON.parse(_s).developerMode) : false;
    } catch (e) {
        window.DEVELOPER_MODE = false;
    }
    var currentTicker = "SPY";
    var priceChart = null;
    var volumeChart = null;
    var selectedTimeframe = { interval: "5m", period: "1d" };
    var selectedChartMode = "line";
    var chartCanvas = null;

    var TIMEFRAME_MAP = {
        "1m":  { period: "1d",  interval: "1m" },
        "2m":  { period: "1d",  interval: "2m" },
        "5m":  { period: "1d",  interval: "5m" },
        "15m": { period: "5d",  interval: "15m" },
        "1h":  { period: "1mo", interval: "1h" },
        "4h":  { period: "3mo", interval: "1h" },
        "1D":  { period: "5d",  interval: "1d" },
        "5D":  { period: "1mo", interval: "1d" },
        "1M":  { period: "3mo", interval: "1d" }
    };

    function setDebug(o) {
        if (typeof window !== "undefined" && window.DEVELOPER_MODE !== true) return;
        var k, el;
        for (k in o) {
            if (o.hasOwnProperty(k)) {
                el = document.getElementById(k);
                if (el) el.textContent = o[k];
            }
        }
    }

    window.getCurrentTicker = function() { return currentTicker; };

    async function loadQuote(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        currentTicker = sym;
        if (typeof window !== "undefined") window.__currentTicker = sym;
        var select = document.getElementById("ticker-select");
        if (select) {
            var found = false;
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].value === sym) { found = true; break; }
            }
            if (!found) {
                var opt = document.createElement("option");
                opt.value = sym;
                opt.textContent = sym;
                select.appendChild(opt);
            }
            select.value = sym;
        }
        var url = "/api/quote?symbol=" + encodeURIComponent(sym);
        setDebug({
            "simple-debug-ticker": currentTicker,
            "simple-debug-url": url,
            "simple-debug-status": "...",
            "simple-debug-symbol": "--",
            "simple-debug-price": "--",
            "simple-debug-error": "none"
        });
        var priceEl = document.getElementById("current-price");
        var changeEl = document.getElementById("price-change");
        var updatedEl = document.getElementById("last-updated");
        if (!priceEl) return;
        try {
            var res = await fetch(url);
            setDebug({ "simple-debug-status": String(res.status) });
            var text = await res.text();
            var data = null;
            try { data = JSON.parse(text); } catch (e) {}
            if (!data) {
                setDebug({ "simple-debug-error": "Invalid JSON", "simple-debug-price": "--" });
                priceEl.innerHTML = "<span class=\"text-warning\">Invalid response</span>";
                if (changeEl) changeEl.textContent = "—";
                if (updatedEl) updatedEl.textContent = "Updated: —";
                return;
            }
            if (data.error) {
                setDebug({ "simple-debug-error": data.error, "simple-debug-price": "--" });
                priceEl.innerHTML = "<span class=\"text-warning\">" + escapeHtml(data.error) + "</span>";
                if (changeEl) changeEl.textContent = "—";
                if (updatedEl) updatedEl.textContent = "Updated: —";
                return;
            }
            var price = data.price != null ? Number(data.price) : NaN;
            var change = data.change != null ? Number(data.change) : 0;
            var pct = data.percentChange != null ? Number(data.percentChange) : 0;
            if (isNaN(price) || price <= 0) {
                setDebug({ "simple-debug-error": "No valid price", "simple-debug-price": "--" });
                priceEl.innerHTML = "<span class=\"text-warning\">No valid price</span>";
                if (changeEl) changeEl.textContent = "—";
                if (updatedEl) updatedEl.textContent = "Updated: —";
                return;
            }
            priceEl.textContent = "$" + price.toFixed(2);
            if (changeEl) {
                var sign = change >= 0 ? "+" : "";
                var pctStr = (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
                changeEl.innerHTML = "<span class=\"" + (change >= 0 ? "text-success" : "text-danger") + "\">" + sign + change.toFixed(2) + " (" + pctStr + ")</span>";
            }
            if (updatedEl) updatedEl.textContent = "Updated: " + new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            var qd = data.quote_debug || {};
            setDebug({
                "simple-debug-symbol": (data.symbol || sym),
                "simple-debug-price": String(price.toFixed(2)),
                "simple-debug-error": "none",
                "simple-debug-price-source": qd.price_source || "--",
                "simple-debug-prev-close": qd.previous_close != null ? String(qd.previous_close) : "--",
                "simple-debug-session": qd.session || "--",
                "simple-debug-computed-change": qd.computed_change != null ? String(qd.computed_change) : (change != null ? String(change) : "--"),
                "simple-debug-computed-pct": qd.computed_percentChange != null ? String(qd.computed_percentChange) : (pct != null ? String(pct) + "%" : "--")
            });
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            setDebug({ "simple-debug-error": msg, "simple-debug-price": "--" });
            priceEl.innerHTML = "<span class=\"text-warning\">Error: " + escapeHtml(msg) + "</span>";
            if (changeEl) changeEl.textContent = "—";
            if (updatedEl) updatedEl.textContent = "Updated: —";
        }
    }

    function escapeHtml(s) {
        var div = document.createElement("div");
        div.textContent = s;
        return div.innerHTML;
    }

    function initSimpleDashboard() {
        if (window.__simpleDashboardInitialized) return;
        window.__simpleDashboardInitialized = true;

        var select = document.getElementById("ticker-select");
        if (!select) return;
        var raw = (select.value || "SPY").toString().trim().toUpperCase();
        currentTicker = raw || "SPY";
        if (select.options.length === 0 || !select.value) {
            select.innerHTML = "";
            var o = document.createElement("option");
            o.value = "SPY";
            o.textContent = "SPY";
            select.appendChild(o);
            select.value = "SPY";
            currentTicker = "SPY";
        } else {
            currentTicker = (select.value || "SPY").toString().trim().toUpperCase();
        }

        if (typeof window !== "undefined") window.__currentTicker = currentTicker;
        setDebug({ "simple-debug-initialized": "yes", "simple-debug-ticker": currentTicker });

        initCharts();
        var refreshBtn = document.getElementById("ticker-card-refresh");
        if (refreshBtn) refreshBtn.addEventListener("click", function() { onSymbolChanged(currentTicker); });

        var timeframeLabel = document.getElementById("chart-timeframe-label");
        document.querySelectorAll(".timeframe-btn").forEach(function(btn) {
            btn.addEventListener("click", function() {
                var period = this.getAttribute("data-period") || "1d";
                var interval = this.getAttribute("data-interval") || "5m";
                selectedTimeframe = { period: period, interval: interval };
                if (timeframeLabel) timeframeLabel.textContent = this.textContent.trim();
                document.querySelectorAll(".timeframe-btn").forEach(function(b) { b.classList.remove("active"); });
                this.classList.add("active");
                loadChart(currentTicker, selectedTimeframe, selectedChartMode);
            });
        });

        document.querySelectorAll(".chart-type-btn").forEach(function(btn) {
            btn.addEventListener("click", function() {
                var mode = "line";
                if (this.id === "chart-candle") mode = "candle";
                else if (this.id === "chart-heiken") mode = "ha";
                selectedChartMode = mode;
                document.querySelectorAll(".chart-type-btn").forEach(function(b) { b.classList.remove("active"); });
                this.classList.add("active");
                loadChart(currentTicker, selectedTimeframe, selectedChartMode);
            });
        });

        ["overlay-fib", "overlay-vwap", "overlay-ema", "overlay-pd", "overlay-pm", "overlay-or", "overlay-atr", "overlay-signals"].forEach(function(id) {
            var el = document.getElementById(id);
            if (!el) return;
            if (id === "overlay-fib" || id === "overlay-vwap") el.checked = true;
            el.addEventListener("change", function() {
                if (priceChart && lastOverlayData) applyChartOverlays(priceChart, lastOverlayData);
            });
        });

        var refreshNewsBtn = document.getElementById("refresh-news-btn");
        if (refreshNewsBtn) refreshNewsBtn.addEventListener("click", function() { loadNews(currentTicker); });

        var addSubmit = document.getElementById("add-ticker-submit");
        if (addSubmit) {
            addSubmit.addEventListener("click", function() {
                var input = document.getElementById("new-ticker");
                if (!input) return;
                var sym = input.value.trim().toUpperCase();
                if (!sym) return;
                input.value = "";
                var modal = document.getElementById("addTickerModal");
                if (modal && typeof bootstrap !== "undefined") {
                    var m = bootstrap.Modal.getInstance(modal);
                    if (m) m.hide();
                }
                onSymbolChanged(sym);
            });
        }

        select.addEventListener("change", function() {
            onSymbolChanged((select.value || "SPY").toString().trim().toUpperCase());
        });

        var refreshSignalBtn = document.getElementById("refresh-signal");
        if (refreshSignalBtn) refreshSignalBtn.addEventListener("click", function() { onSymbolChanged(currentTicker); });

        document.querySelectorAll(".open-scan-btn").forEach(function(btn) {
            btn.addEventListener("click", function() {
                document.querySelectorAll(".open-scan-btn").forEach(function(b) { b.classList.remove("active"); });
                this.classList.add("active");
                var phase = this.getAttribute("data-phase") || "5min";
                loadMarketOpenScan(phase);
            });
        });

        var cheapRadarRefresh = document.getElementById("cheap-options-radar-refresh");
        if (cheapRadarRefresh) cheapRadarRefresh.addEventListener("click", function() { loadCheapOptionsRadar(currentTicker); });

        startLotteryAlertCheck();
        onSymbolChanged(currentTicker);
    }

    var lastLotteryAlertKey = "";
    function startLotteryAlertCheck() {
        setInterval(function() {
            var now = new Date();
            var etHour = parseInt(now.toLocaleString("en-US", { timeZone: "America/New_York", hour: "numeric", hour12: false }), 10);
            var etMin = parseInt(now.toLocaleString("en-US", { timeZone: "America/New_York", minute: "numeric" }), 10);
            var etStr = now.toLocaleString("en-US", { timeZone: "America/New_York" });
            var key = now.toDateString() + "-15:55";
            if (etHour === 15 && etMin >= 55 && lastLotteryAlertKey !== key) {
                lastLotteryAlertKey = key;
                if (typeof console !== "undefined" && console.log) {
                    console.log("[Lottery Alert] 3:55 PM ET — Lottery hour active. Triggered at " + etStr + " ET.");
                }
                var banner = document.getElementById("lottery-hour-banner");
                if (banner) banner.style.display = "block";
            }
            if (etHour < 15 || (etHour === 15 && etMin < 55) || etHour >= 16) {
                if (etHour >= 16 || etHour < 15) lastLotteryAlertKey = "";
            }
        }, 10000);
    }

    async function onSymbolChanged(symbol) {
        var sym = (symbol || "SPY").toString().trim().toUpperCase();
        currentTicker = sym;
        if (typeof window !== "undefined") window.__currentTicker = sym;
        var select = document.getElementById("ticker-select");
        if (select) {
            var found = false;
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].value === sym) { found = true; break; }
            }
            if (!found) {
                var opt = document.createElement("option");
                opt.value = sym;
                opt.textContent = sym;
                select.appendChild(opt);
            }
            select.value = sym;
        }
        await loadQuote(sym);
        await loadAnalysis(sym);
        await loadChart(sym, selectedTimeframe, selectedChartMode);
        await loadNews(sym);
        await loadTimeframeAnalysis(sym);
        await loadKeyLevels(sym);
        await loadScalpingLevels(sym);
        await loadPremarketTrend(sym);
        await loadSignals(sym);
        var activePhase = (document.querySelector(".open-scan-btn.active") && document.querySelector(".open-scan-btn.active").getAttribute("data-phase")) || "5min";
        await loadMarketOpenScan(activePhase);
        await loadTradingIntelligence(sym);
        await loadCheapOptionsRadar(sym);
        try {
            if (typeof window !== "undefined" && window.dispatchEvent) {
                window.dispatchEvent(new CustomEvent("symbolChanged", { detail: { symbol: sym } }));
            }
        } catch (evErr) {}
    }

    function showChartNoData(show) {
        var el = document.getElementById("chart-no-data");
        if (el) {
            if (show) el.classList.remove("d-none"); else el.classList.add("d-none");
        }
    }

    function safeNum(v) {
        if (v == null) return NaN;
        if (typeof v === "number" && isNaN(v)) return NaN;
        var n = Number(v);
        return isNaN(n) ? NaN : n;
    }

    function filterValidOhlcBars(timestamps, opens, highs, lows, closes) {
        var n = Math.min(
            (timestamps && timestamps.length) || 0,
            (opens && opens.length) || 0,
            (highs && highs.length) || 0,
            (lows && lows.length) || 0,
            (closes && closes.length) || 0
        );
        var outTs = [], outO = [], outH = [], outL = [], outC = [];
        var removed = 0;
        for (var i = 0; i < n; i++) {
            var ts = timestamps[i];
            var o = safeNum(opens[i]), h = safeNum(highs[i]), l = safeNum(lows[i]), c = safeNum(closes[i]);
            if (!ts) { removed++; continue; }
            if (isNaN(o) || isNaN(h) || isNaN(l) || isNaN(c)) { removed++; continue; }
            if (h < l) { removed++; continue; }
            if (h < o || h < c) { removed++; continue; }
            if (l > o || l > c) { removed++; continue; }
            outTs.push(ts);
            outO.push(o);
            outH.push(h);
            outL.push(l);
            outC.push(c);
        }
        var len = outC.length;
        if (len < 2) return { timestamps: outTs, opens: outO, highs: outH, lows: outL, closes: outC, removed: removed };
        var ranges = [];
        for (var j = 0; j < len; j++) ranges.push(outH[j] - outL[j]);
        ranges.sort(function(a, b) { return a - b; });
        var medianRange = ranges[Math.floor(len / 2)] || 0;
        var maxAllowed = medianRange * 5;
        if (maxAllowed <= 0) maxAllowed = Infinity;
        var outTs2 = [], outO2 = [], outH2 = [], outL2 = [], outC2 = [];
        for (var k = 0; k < len; k++) {
            if ((outH[k] - outL[k]) > maxAllowed) { removed++; continue; }
            outTs2.push(outTs[k]);
            outO2.push(outO[k]);
            outH2.push(outH[k]);
            outL2.push(outL[k]);
            outC2.push(outC[k]);
        }
        return { timestamps: outTs2, opens: outO2, highs: outH2, lows: outL2, closes: outC2, removed: removed };
    }

    function computeHeikinAshi(opens, highs, lows, closes) {
        var n = (closes && closes.length) || 0;
        var ha_o = [], ha_h = [], ha_l = [], ha_c = [];
        for (var i = 0; i < n; i++) {
            var o = Number(opens[i]), h = Number(highs[i]), l = Number(lows[i]), c = Number(closes[i]);
            var hc = (o + h + l + c) / 4;
            var ho = i === 0 ? (o + c) / 2 : (ha_o[i - 1] + ha_c[i - 1]) / 2;
            ha_c[i] = Math.round(hc * 1e4) / 1e4;
            ha_o[i] = Math.round(ho * 1e4) / 1e4;
            ha_h[i] = Math.round((Math.max(h, ha_o[i], ha_c[i])) * 1e4) / 1e4;
            ha_l[i] = Math.round((Math.min(l, ha_o[i], ha_c[i])) * 1e4) / 1e4;
        }
        return { opens: ha_o, highs: ha_h, lows: ha_l, closes: ha_c };
    }

    function barToAudit(b) {
        if (!b) return "null";
        if (typeof b.x !== "undefined") return "x=" + (b.x instanceof Date ? b.x.getTime() : b.x) + " o=" + b.o + " h=" + b.h + " l=" + b.l + " c=" + b.c;
        return JSON.stringify(b).slice(0, 80);
    }

    var candlestickDrawPlugin = {
        id: "candlestickDraw",
        afterDatasetsDraw: function(chart) {
            var opts = chart.options.plugins && chart.options.plugins.candlestickDraw;
            if (!opts || !opts.ohlcData || !opts.ohlcData.length) return;
            var ohlc = opts.ohlcData;
            var xScale = chart.scales.x;
            var yScale = chart.scales.y;
            if (!xScale || !yScale) return;
            var ctx = chart.ctx;
            var n = ohlc.length;
            var categoryWidth = n > 1 ? Math.abs(xScale.getPixelForValue(1) - xScale.getPixelForValue(0)) : 40;
            var bodyWidth = Math.max(2, Math.min(categoryWidth * 0.7, 24));
            var wickColor = "rgba(148, 163, 184, 0.95)";
            var upColor = "rgba(34, 197, 94, 0.95)";
            var downColor = "rgba(239, 68, 68, 0.95)";
            ctx.save();
            for (var i = 0; i < n; i++) {
                var b = ohlc[i];
                var o = Number(b.o), h = Number(b.h), l = Number(b.l), c = Number(b.c);
                var xPix = xScale.getPixelForValue(i);
                var yH = yScale.getPixelForValue(h);
                var yL = yScale.getPixelForValue(l);
                var yO = yScale.getPixelForValue(o);
                var yC = yScale.getPixelForValue(c);
                ctx.strokeStyle = wickColor;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(xPix, yH);
                ctx.lineTo(xPix, yL);
                ctx.stroke();
                var bodyTop = Math.min(yO, yC);
                var bodyBottom = Math.max(yO, yC);
                var bodyHeight = bodyBottom - bodyTop;
                if (bodyHeight < 1) bodyHeight = 1;
                bodyBottom = bodyTop + bodyHeight;
                var half = bodyWidth / 2;
                ctx.fillStyle = c >= o ? upColor : downColor;
                ctx.fillRect(xPix - half, bodyTop, bodyWidth, bodyHeight);
            }
            ctx.restore();
        }
    };
    if (typeof Chart !== "undefined" && Chart.register) Chart.register(candlestickDrawPlugin);

    var lastOverlayData = null;
    var lastMainSignal = "";

    function overlayToggle(id) { var el = document.getElementById(id); return el ? el.checked : false; }
    function computeEMA(closes, period) {
        var out = [], k = 2 / (period + 1), i;
        for (i = 0; i < closes.length; i++) {
            if (i < period - 1) { out.push(null); continue; }
            if (i === period - 1) {
                var sum = 0; for (var j = 0; j < period; j++) sum += closes[j];
                out.push(sum / period);
                continue;
            }
            out.push((closes[i] - out[i - 1]) * k + out[i - 1]);
        }
        return out;
    }
    function computeVwapArray(highs, lows, closes, volumes) {
        var out = [], cumTpv = 0, cumV = 0, i;
        for (i = 0; i < closes.length; i++) {
            var tp = ((highs[i] || 0) + (lows[i] || 0) + (closes[i] || 0)) / 3;
            var v = (volumes && volumes[i] != null) ? Number(volumes[i]) : 0;
            cumTpv += tp * v;
            cumV += v;
            out.push(cumV > 0 ? cumTpv / cumV : (closes[i] || 0));
        }
        return out;
    }
    function isInOpeningRangeET(ts) {
        if (ts == null) return false;
        var d = (typeof ts === "number" || typeof ts === "string") ? new Date(ts) : new Date();
        var etStr = d.toLocaleString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false });
        var parts = etStr.split(/[\s:]+/);
        var h = parseInt(parts[0], 10), m = parseInt(parts[1], 10);
        if (h < 9) return false;
        if (h === 9 && m < 30) return false;
        if (h === 9 && m >= 30 && m < 35) return true;
        if (h === 9 && m >= 35) return false;
        return false;
    }
    function getORFromBars(timestamps, highs, lows) {
        var orh = -Infinity, orl = Infinity, i;
        for (i = 0; i < (timestamps && timestamps.length) || 0; i++) {
            if (!isInOpeningRangeET(timestamps[i])) continue;
            if (highs[i] != null && highs[i] > orh) orh = highs[i];
            if (lows[i] != null && lows[i] < orl) orl = lows[i];
        }
        return { orh: orh === -Infinity ? null : orh, orl: orl === Infinity ? null : orl };
    }
    function getFibLevels(highs, lows) {
        var n = (highs && highs.length) || 0;
        var lookback = Math.min(50, Math.floor(n * 0.6));
        if (n < 20) return null;
        var slice = n - lookback;
        var recentHigh = Math.max.apply(null, highs.slice(slice));
        var recentLow = Math.min.apply(null, lows.slice(slice));
        var range = recentHigh - recentLow;
        if (range <= 0) return null;
        return {
            fib236: recentLow + range * 0.236,
            fib382: recentLow + range * 0.382,
            fib50: recentLow + range * 0.5,
            fib618: recentLow + range * 0.618,
            fib786: recentLow + range * 0.786,
            srHigh: recentHigh,
            srLow: recentLow
        };
    }
    function getATRBands(highs, lows, closes, period) {
        period = period || 14;
        var len = (closes && closes.length) || 0;
        if (len < period) return null;
        var sum = 0;
        for (var j = len - period; j < len - 1; j++) {
            if (j >= 0) sum += Math.max((highs[j] - lows[j]), Math.abs(highs[j] - (closes[j - 1] || closes[j])), Math.abs(lows[j] - (closes[j - 1] || closes[j])));
        }
        var atr = sum / (period - 1) || 0;
        var last = closes[len - 1];
        return { upper: last + atr, lower: last - atr };
    }
    var signalTagPlugin = {
        id: "signalTag",
        afterDatasetsDraw: function(chart) {
            var opts = chart.options.plugins && chart.options.plugins.signalTag;
            if (!opts || !opts.signal || !opts.show) return;
            var meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data || meta.data.length === 0) return;
            var lastPoint = meta.data[meta.data.length - 1];
            var ctx = chart.ctx;
            ctx.save();
            ctx.font = "bold 10px sans-serif";
            var text = opts.signal === "BUY" ? "BUY" : (opts.signal === "SELL" ? "SELL" : "PREPARE");
            var color = opts.signal === "BUY" ? "#22c55e" : (opts.signal === "SELL" ? "#ef4444" : "#eab308");
            ctx.fillStyle = color;
            ctx.fillText(text, lastPoint.x + 4, lastPoint.y - 4);
            ctx.restore();
        }
    };
    if (typeof Chart !== "undefined" && Chart.register) Chart.register(signalTagPlugin);

    function applyChartOverlays(chart, data) {
        if (!chart || !data || !data.labels || !data.closes || data.closes.length < 2) return;
        lastOverlayData = data;
        var labels = data.labels, highs = data.highs || [], lows = data.lows || [], closes = data.closes, opens = data.opens || [], volumes = data.volumes || [], timestamps = data.timestamps || [];
        var chartLevels = data.chartLevels || {};
        var len = labels.length;
        function constArr(v) { var a = []; for (var i = 0; i < len; i++) a.push(v); return a; }
        var overlayDatasets = [];
        if (overlayToggle("overlay-fib")) {
            var fib = getFibLevels(highs, lows);
            if (fib) {
                overlayDatasets.push({ label: "Fib 0.236", data: constArr(fib.fib236), borderColor: "rgba(34, 197, 94, 0.75)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
                overlayDatasets.push({ label: "Fib 0.382", data: constArr(fib.fib382), borderColor: "rgba(34, 197, 94, 0.8)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
                overlayDatasets.push({ label: "Fib 0.5", data: constArr(fib.fib50), borderColor: "rgba(234, 179, 8, 0.8)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
                overlayDatasets.push({ label: "Fib 0.618", data: constArr(fib.fib618), borderColor: "rgba(249, 115, 22, 0.8)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
                overlayDatasets.push({ label: "Fib 0.786", data: constArr(fib.fib786), borderColor: "rgba(239, 68, 68, 0.75)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
            }
        }
        if (overlayToggle("overlay-vwap") && volumes && volumes.length === len) {
            var vwapArr = computeVwapArray(highs, lows, closes, volumes);
            overlayDatasets.push({ label: "VWAP", data: vwapArr, borderColor: "rgba(168, 85, 247, 0.95)", borderWidth: 2, fill: false, pointRadius: 0, tension: 0.1 });
        }
        if (overlayToggle("overlay-ema")) {
            var e9 = computeEMA(closes, 9), e21 = computeEMA(closes, 21), e48 = computeEMA(closes, 48), e200 = computeEMA(closes, 200);
            overlayDatasets.push({ label: "EMA 9", data: e9, borderColor: "rgba(252, 211, 77, 0.9)", borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0.1 });
            overlayDatasets.push({ label: "EMA 21", data: e21, borderColor: "rgba(251, 146, 60, 0.9)", borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0.1 });
            overlayDatasets.push({ label: "EMA 48", data: e48, borderColor: "rgba(96, 165, 250, 0.9)", borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0.1 });
            overlayDatasets.push({ label: "EMA 200", data: e200, borderColor: "rgba(192, 132, 252, 0.9)", borderWidth: 1.5, fill: false, pointRadius: 0, tension: 0.1 });
        }
        if (overlayToggle("overlay-pd") && (chartLevels.pdh != null || chartLevels.pdl != null)) {
            if (chartLevels.pdh != null) overlayDatasets.push({ label: "PDH", data: constArr(chartLevels.pdh), borderColor: "rgba(239, 68, 68, 0.8)", borderWidth: 1.5, borderDash: [6, 3], fill: false, pointRadius: 0 });
            if (chartLevels.pdl != null) overlayDatasets.push({ label: "PDL", data: constArr(chartLevels.pdl), borderColor: "rgba(34, 197, 94, 0.8)", borderWidth: 1.5, borderDash: [6, 3], fill: false, pointRadius: 0 });
        }
        if (overlayToggle("overlay-pm") && (chartLevels.pmh != null || chartLevels.pml != null)) {
            if (chartLevels.pmh != null) overlayDatasets.push({ label: "PMH", data: constArr(chartLevels.pmh), borderColor: "rgba(251, 146, 60, 0.8)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
            if (chartLevels.pml != null) overlayDatasets.push({ label: "PML", data: constArr(chartLevels.pml), borderColor: "rgba(96, 165, 250, 0.8)", borderWidth: 1, borderDash: [4, 2], fill: false, pointRadius: 0 });
        }
        if (overlayToggle("overlay-or")) {
            var orLevels = getORFromBars(timestamps, highs, lows);
            if (orLevels.orh != null) overlayDatasets.push({ label: "ORH", data: constArr(orLevels.orh), borderColor: "rgba(234, 179, 8, 0.85)", borderWidth: 1.5, borderDash: [4, 2], fill: false, pointRadius: 0 });
            if (orLevels.orl != null) overlayDatasets.push({ label: "ORL", data: constArr(orLevels.orl), borderColor: "rgba(34, 197, 94, 0.85)", borderWidth: 1.5, borderDash: [4, 2], fill: false, pointRadius: 0 });
        }
        if (overlayToggle("overlay-atr")) {
            var atr = getATRBands(highs, lows, closes, 14);
            if (atr) {
                overlayDatasets.push({ label: "ATR Upper", data: constArr(atr.upper), borderColor: "rgba(148, 163, 184, 0.65)", borderWidth: 1, borderDash: [2, 2], fill: false, pointRadius: 0 });
                overlayDatasets.push({ label: "ATR Lower", data: constArr(atr.lower), borderColor: "rgba(148, 163, 184, 0.65)", borderWidth: 1, borderDash: [2, 2], fill: false, pointRadius: 0 });
            }
        }
        while (chart.data.datasets.length > 1) chart.data.datasets.pop();
        overlayDatasets.forEach(function(ds) { chart.data.datasets.push(ds); });
        if (chart.options.plugins) chart.options.plugins.signalTag = { signal: data.mainSignal || lastMainSignal, show: overlayToggle("overlay-signals") };
        else chart.options.plugins = { signalTag: { signal: data.mainSignal || lastMainSignal, show: overlayToggle("overlay-signals") } };
        chart.update("none");
    }

    function createLineChart() {
        if (!chartCanvas || typeof Chart === "undefined") return;
        if (priceChart) priceChart.destroy();
        priceChart = new Chart(chartCanvas.getContext("2d"), {
            type: "line",
            data: {
                labels: [],
                datasets: [{ label: "Price", data: [], borderColor: "#4dabf7", backgroundColor: "rgba(77, 171, 247, 0.1)", borderWidth: 2, fill: true, tension: 0.1, pointRadius: 0 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: true, grid: { color: "rgba(255,255,255,0.1)" }, ticks: { color: "#888", maxTicksLimit: 8 } },
                    y: { display: true, grid: { color: "rgba(255,255,255,0.1)" }, ticks: { color: "#888" } }
                }
            }
        });
    }

    function createCandlestickChart(ohlcData, isHA, setRenderType) {
        if (!chartCanvas || typeof Chart === "undefined") return false;
        if (priceChart) priceChart.destroy();
        priceChart = null;
        if (!ohlcData || ohlcData.length < 2) {
            if (setRenderType) setDebug({ "module-chart-render-type": "none (not enough bars)" });
            createLineChart();
            if (priceChart && priceChart.data.datasets[0]) {
                priceChart.data.labels = [];
                priceChart.data.datasets[0].data = [];
                priceChart.update("none");
            }
            return false;
        }
        var n = ohlcData.length;
        var dataMin = Infinity, dataMax = -Infinity;
        for (var d = 0; d < n; d++) {
            var bar = ohlcData[d];
            if (bar.l < dataMin) dataMin = bar.l;
            if (bar.h > dataMax) dataMax = bar.h;
        }
        if (dataMin === Infinity) dataMin = 0;
        if (dataMax === -Infinity) dataMax = 100;
        var pad = (dataMax - dataMin) * 0.005 || 0.5;
        var yMin = dataMin - pad;
        var yMax = dataMax + pad;

        var labels = [];
        var closeData = [];
        for (var i = 0; i < n; i++) {
            var b = ohlcData[i];
            var xVal = b.x;
            labels.push(typeof xVal === "number" ? new Date(xVal).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : (xVal instanceof Date ? xVal.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : String(i)));
            closeData.push(b.c);
        }

        try {
            priceChart = new Chart(chartCanvas.getContext("2d"), {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: isHA ? "Heikin Ashi" : "OHLC",
                        data: closeData,
                        borderWidth: 0,
                        pointRadius: 0,
                        fill: false,
                        tension: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        candlestickDraw: { ohlcData: ohlcData }
                    },
                    scales: {
                        x: {
                            display: true,
                            grid: { color: "rgba(255,255,255,0.08)" },
                            ticks: { color: "#94a3b8", maxTicksLimit: 14, font: { size: 10 }, autoSkip: true }
                        },
                        y: {
                            display: true,
                            position: "right",
                            suggestedMin: yMin,
                            suggestedMax: yMax,
                            grid: { color: "rgba(255,255,255,0.08)" },
                            ticks: { color: "#94a3b8", font: { size: 10 } }
                        }
                    }
                }
            });
            if (setRenderType) setDebug({ "module-chart-render-type": isHA ? "HA (canvas)" : "candle (canvas)" });
            return true;
        } catch (err) {
            if (setRenderType) setDebug({ "module-chart-render-type": "error: " + (err.message || String(err)) });
            createLineChart();
            if (priceChart && priceChart.data.datasets[0]) {
                priceChart.data.labels = [];
                priceChart.data.datasets[0].data = [];
                priceChart.update("none");
            }
            return false;
        }
    }

    function initCharts() {
        var priceCtx = document.getElementById("price-chart");
        var volCtx = document.getElementById("volume-chart");
        if (!priceCtx || typeof Chart === "undefined") return;
        chartCanvas = priceCtx;
        createLineChart();
        if (volCtx) {
            if (volumeChart) volumeChart.destroy();
            volumeChart = new Chart(volCtx.getContext("2d"), {
                type: "bar",
                data: { labels: [], datasets: [{ label: "Volume", data: [], backgroundColor: "rgba(100, 149, 237, 0.6)", borderColor: "rgba(100, 149, 237, 0.8)", borderWidth: 1 }] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { display: true, grid: { display: false }, ticks: { color: "#888", maxTicksLimit: 10, font: { size: 10 } } },
                        y: { display: true, grid: { color: "rgba(255,255,255,0.08)" }, ticks: { color: "#888", font: { size: 10 } } }
                    },
                    datasets: { bar: { barPercentage: 0.85, categoryPercentage: 0.9 } }
                }
            });
        }
        showChartNoData(true);
    }

    async function loadChart(symbol, timeframe, mode) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var period = (timeframe && timeframe.period) ? timeframe.period : "1d";
        var interval = (timeframe && timeframe.interval) ? timeframe.interval : "5m";
        var url = "/api/market-data/" + encodeURIComponent(sym) + "?period=" + encodeURIComponent(period) + "&interval=" + encodeURIComponent(interval);
        setDebug({
            "module-chart-symbol": sym,
            "module-chart-endpoint": url,
            "module-chart-status": "...",
            "module-chart-result": "...",
            "module-chart-mode": mode || "line",
            "module-chart-timeframe": interval,
            "module-chart-period": period,
            "module-chart-interval": interval,
            "module-chart-bars": "--"
        });
        var noDataEl = document.getElementById("chart-no-data");
        if (noDataEl) noDataEl.textContent = "Loading chart...";
        showChartNoData(true);
        try {
            var res = await fetch(url);
            setDebug({ "module-chart-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data) {
                setDebug({ "module-chart-result": "Invalid JSON", "module-chart-bars": "0" });
                if (noDataEl) noDataEl.textContent = "No chart data for this timeframe — invalid response.";
                if (priceChart) { priceChart.destroy(); priceChart = null; createLineChart(); }
                if (priceChart && priceChart.data.datasets[0]) priceChart.data.datasets[0].data = [];
                if (priceChart) priceChart.update("none");
                showChartNoData(true);
                return;
            }
            if (data.error || !(data.closes && data.closes.length > 0)) {
                setDebug({ "module-chart-result": data.error || "no data", "module-chart-bars": "0", "module-chart-invalid-removed": "--", "module-chart-render-type": "--" });
                if (noDataEl) noDataEl.textContent = "No chart data for this timeframe.";
                if (priceChart) { priceChart.destroy(); priceChart = null; createLineChart(); }
                if (priceChart && priceChart.data.datasets[0]) priceChart.data.datasets[0].data = [];
                if (priceChart) priceChart.update("none");
                showChartNoData(true);
                return;
            }
            var rawTs = data.timestamps || [];
            var rawO = data.opens || [];
            var rawH = data.highs || [];
            var rawL = data.lows || [];
            var rawC = data.closes || [];
            var filtered = filterValidOhlcBars(rawTs, rawO, rawH, rawL, rawC);
            var timestamps = filtered.timestamps;
            var opens = filtered.opens;
            var highs = filtered.highs;
            var lows = filtered.lows;
            var closes = filtered.closes;
            var n = closes.length;
            var removed = filtered.removed;
            var totalBars = (rawC && rawC.length) || 0;

            var first2 = [], last2 = [];
            for (var fi = 0; fi < Math.min(2, n); fi++) {
                first2.push({ x: timestamps[fi], o: opens[fi], h: highs[fi], l: lows[fi], c: closes[fi] });
            }
            for (var li = Math.max(0, n - 2); li < n; li++) {
                last2.push({ x: timestamps[li], o: opens[li], h: highs[li], l: lows[li], c: closes[li] });
            }
            if (typeof console !== "undefined" && console.log) {
                console.log("[chart audit] symbol=" + sym + " timeframe=" + interval + " mode=" + (mode || "line") + " total=" + totalBars + " valid=" + n + " dropped=" + removed + " renderer=" + (mode === "line" ? "line" : (mode === "ha" ? "HA" : "candle")));
                console.log("[chart audit] first2=" + JSON.stringify(first2));
                console.log("[chart audit] last2=" + JSON.stringify(last2));
            }
            setDebug({
                "module-chart-bars": String(n),
                "module-chart-total-bars": String(totalBars),
                "module-chart-invalid-removed": String(removed),
                "module-chart-render-type": mode === "line" ? "line" : (mode === "ha" ? "HA (canvas)" : "candle (canvas)")
            });

            if (mode === "candle" || mode === "ha") {
                if (n < 2) {
                    setDebug({ "module-chart-result": "Not enough OHLC for candle", "module-chart-render-type": "none" });
                    if (noDataEl) noDataEl.textContent = "Not enough OHLC data for candle mode.";
                    if (priceChart) { priceChart.destroy(); priceChart = null; }
                    createLineChart();
                    if (priceChart && priceChart.data.datasets[0]) { priceChart.data.labels = []; priceChart.data.datasets[0].data = []; priceChart.update("none"); }
                    showChartNoData(true);
                    return;
                }
                var useOpens = opens, useHighs = highs, useLows = lows, useCloses = closes;
                if (mode === "ha") {
                    var ha = computeHeikinAshi(opens, highs, lows, closes);
                    useOpens = ha.opens; useHighs = ha.highs; useLows = ha.lows; useCloses = ha.closes;
                }
                var ohlcData = [];
                for (var i = 0; i < n; i++) {
                    var ts = timestamps[i];
                    var xVal = (ts && (typeof ts === "number" || typeof ts === "string")) ? new Date(ts).getTime() : i;
                    var o = Number(Number(useOpens[i]).toFixed(4));
                    var h = Number(Number(useHighs[i]).toFixed(4));
                    var l = Number(Number(useLows[i]).toFixed(4));
                    var c = Number(Number(useCloses[i]).toFixed(4));
                    ohlcData.push({ x: xVal, o: o, h: h, l: l, c: c });
                }
                var rendered = createCandlestickChart(ohlcData, mode === "ha", true);
                if (rendered && priceChart) {
                    var candleLabels = timestamps.map(function(t) { var d = (t && (typeof t === "number" || typeof t === "string")) ? new Date(t) : new Date(); return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); });
                    (async function() {
                        var chartLevels = {};
                        try { var r = await fetch("/api/chart-levels/" + encodeURIComponent(sym)); var j = await r.json(); if (j) chartLevels = j; } catch (e) {}
                        applyChartOverlays(priceChart, { labels: candleLabels, highs: useHighs, lows: useLows, closes: useCloses, opens: useOpens, volumes: data.volumes || [], timestamps: timestamps, chartLevels: chartLevels, mainSignal: lastMainSignal });
                    })();
                }
                if (!rendered && noDataEl) noDataEl.textContent = "Not enough OHLC data for candle mode.";
                showChartNoData(!rendered);
                setDebug({ "module-chart-result": rendered ? "ok " + n + " bars" : "candle render failed" });
            } else {
                setDebug({ "module-chart-render-type": "line" });
                if (priceChart && priceChart.config && priceChart.config.type !== "line") {
                    priceChart.destroy();
                    priceChart = null;
                    createLineChart();
                }
                var labels = timestamps.map(function(t) {
                    var d = (t && (typeof t === "number" || typeof t === "string")) ? new Date(t) : new Date();
                    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
                });
                priceChart.data.labels = labels;
                priceChart.data.datasets[0].data = closes;
                priceChart.update("none");
                (async function() {
                    var chartLevels = {};
                    try { var r = await fetch("/api/chart-levels/" + encodeURIComponent(sym)); var j = await r.json(); if (j) chartLevels = j; } catch (e) {}
                    applyChartOverlays(priceChart, { labels: labels, highs: highs, lows: lows, closes: closes, opens: opens, volumes: data.volumes || [], timestamps: timestamps, chartLevels: chartLevels, mainSignal: lastMainSignal });
                })();
                showChartNoData(false);
                setDebug({ "module-chart-result": "ok " + n + " bars" });
            }

            var vols = data.volumes || [];
            var rawLen = rawC.length;
            if (volumeChart && vols.length > 0) {
                var volLabels = (rawTs || []).map(function(t) { var d = (t && (typeof t === "number" || typeof t === "string")) ? new Date(t) : new Date(); return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); });
                var bgColors = [];
                for (var v = 0; v < vols.length; v++) {
                    var isUp = (rawC[v] != null && rawO[v] != null && rawC[v] >= rawO[v]);
                    bgColors.push(isUp ? "rgba(34, 197, 94, 0.85)" : "rgba(239, 68, 68, 0.85)");
                }
                volumeChart.data.labels = volLabels.length ? volLabels : new Array(vols.length).fill("");
                volumeChart.data.datasets[0].data = vols;
                volumeChart.data.datasets[0].backgroundColor = bgColors;
                volumeChart.update("none");

                var volStateEl = document.getElementById("volume-state-alert");
                var volIconEl = document.getElementById("volume-state-icon");
                var volTextEl = document.getElementById("volume-state-text");
                if (volStateEl && volIconEl && volTextEl) {
                    var sum = 0, count = 0;
                    for (var vi = 0; vi < vols.length; vi++) { if (vols[vi] != null && !isNaN(vols[vi])) { sum += vols[vi]; count++; } }
                    var avgVol = count > 0 ? sum / count : 0;
                    var recentCount = Math.min(5, Math.max(1, Math.floor(vols.length * 0.2)));
                    var recentSum = 0;
                    for (var ri = vols.length - recentCount; ri < vols.length; ri++) { if (ri >= 0 && vols[ri] != null) recentSum += vols[ri]; }
                    var recentAvg = recentCount > 0 ? recentSum / recentCount : 0;
                    if (avgVol > 0 && recentAvg >= avgVol * 1.5) {
                        volStateEl.className = "volume-state-indicator volume-on-fire";
                        volIconEl.innerHTML = "<i class=\"bi bi-fire\"></i> ";
                        volTextEl.textContent = "On fire";
                        volStateEl.style.display = "";
                    } else if (avgVol > 0 && recentAvg <= avgVol * 0.5) {
                        volStateEl.className = "volume-state-indicator volume-weak";
                        volIconEl.innerHTML = "<i class=\"bi bi-droplet-half\"></i> ";
                        volTextEl.textContent = "Weak";
                        volStateEl.style.display = "";
                    } else {
                        volStateEl.style.display = "none";
                    }
                }
            } else {
                var volStateEl = document.getElementById("volume-state-alert");
                if (volStateEl) volStateEl.style.display = "none";
            }
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            setDebug({ "module-chart-result": "error: " + msg, "module-chart-bars": "--", "module-chart-invalid-removed": "--", "module-chart-render-type": "--" });
            if (noDataEl) noDataEl.textContent = "Chart failed: " + msg;
            if (priceChart) { priceChart.destroy(); priceChart = null; }
            createLineChart();
            if (priceChart && priceChart.data.datasets[0]) { priceChart.data.datasets[0].data = []; priceChart.update("none"); }
            showChartNoData(true);
        }
    }

    async function loadNews(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/news/" + encodeURIComponent(sym) + "?limit=5";
        setDebug({
            "module-news-symbol": sym,
            "module-news-endpoint": url,
            "module-news-status": "...",
            "module-news-count": "--",
            "module-news-result": "..."
        });
        var listEl = document.getElementById("news-list");
        if (listEl) listEl.innerHTML = "<div class=\"list-group-item bg-transparent text-muted border-0\">Loading news...</div>";
        try {
            var res = await fetch(url);
            setDebug({ "module-news-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data) {
                setDebug({ "module-news-count": "0", "module-news-result": "Invalid JSON" });
                if (listEl) listEl.innerHTML = "<div class=\"list-group-item bg-transparent text-muted border-0\">No news available.</div>";
                return;
            }
            var articles = (data.news && Array.isArray(data.news)) ? data.news : [];
            setDebug({ "module-news-count": String(articles.length), "module-news-result": articles.length ? "ok" : "no data" });
            if (!listEl) return;
            if (articles.length === 0) {
                listEl.innerHTML = "<div class=\"list-group-item bg-transparent text-muted border-0\">No news available.</div>";
                return;
            }
            var html = "";
            for (var i = 0; i < articles.length; i++) {
                var a = articles[i];
                var title = (a.title || a.headline || "").trim() || "No title";
                var link = a.link || a.url || "#";
                var pub = a.publisher || a.source || "";
                html += "<a href=\"" + escapeHtml(link) + "\" target=\"_blank\" rel=\"noopener\" class=\"list-group-item list-group-item-action bg-transparent border-secondary text-light\">" + escapeHtml(title) + (pub ? " <small class=\"text-muted\">" + escapeHtml(pub) + "</small>" : "") + "</a>";
            }
            listEl.innerHTML = html;
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            setDebug({ "module-news-count": "--", "module-news-result": "error: " + msg });
            if (listEl) listEl.innerHTML = "<div class=\"list-group-item bg-transparent text-muted border-0\">No news available.</div>";
        }
    }

    async function loadTimeframeAnalysis(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/multi-timeframe/" + encodeURIComponent(sym);
        var el = document.getElementById("timeframe-confluence");
        var statusEl = document.getElementById("module-timeframe-status");
        if (statusEl) statusEl.textContent = "...";
        ["1m", "5m", "15m", "1h", "4h"].forEach(function(tfKey) {
            var sigEl = document.getElementById("tf-block-signal-" + tfKey);
            if (sigEl) { sigEl.textContent = "..."; sigEl.className = "badge bg-secondary"; }
        });
        try {
            var res = await fetch(url);
            if (statusEl) statusEl.textContent = String(res.status);
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                var c = document.getElementById("confluence-summary");
                if (c) c.textContent = "No data";
                ["1m", "5m", "15m", "1h", "4h"].forEach(function(tfKey) {
                    var s = document.getElementById("tf-block-signal-" + tfKey);
                    if (s) { s.textContent = "--"; s.className = "badge bg-secondary"; }
                });
                setDebug({ "module-timeframe-result": data && data.error ? data.error : "no data" });
                return;
            }
            var cf = data.confluence || {};
            var tfOrder = ["1m", "5m", "15m", "1h", "4h"];
            var timeframes = data.timeframes || {};
            tfOrder.forEach(function(tfKey) {
                var symEl = document.getElementById("tf-block-symbol-" + tfKey);
                var sigEl = document.getElementById("tf-block-signal-" + tfKey);
                var blockEl = document.querySelector(".timeframe-block[data-tf=\"" + tfKey + "\"]");
                if (symEl) symEl.textContent = sym;
                var tf = timeframes[tfKey] || {};
                var signal = (tf.signal || tf.trend || "WAIT").toString().toUpperCase();
                if (signal.indexOf("BUY") !== -1) signal = "BUY";
                else if (signal.indexOf("SELL") !== -1) signal = "SELL";
                else if (signal === "PREPARE" || (tf.trend && tf.trend !== "NEUTRAL")) signal = "PREPARE";
                else signal = "WAIT";
                if (sigEl) {
                    sigEl.textContent = signal;
                    sigEl.className = "badge ";
                    if (signal === "BUY") sigEl.className += "bg-success";
                    else if (signal === "SELL") sigEl.className += "bg-danger";
                    else if (signal === "PREPARE") sigEl.className += "bg-warning text-dark";
                    else sigEl.className += "bg-secondary";
                }
                if (blockEl) {
                    blockEl.classList.remove("border-success", "border-danger", "border-warning", "border-secondary");
                    if (signal === "BUY") blockEl.classList.add("border-success");
                    else if (signal === "SELL") blockEl.classList.add("border-danger");
                    else if (signal === "PREPARE") blockEl.classList.add("border-warning");
                    else blockEl.classList.add("border-secondary");
                }
            });
            var confSummary = document.getElementById("confluence-summary");
            if (confSummary) confSummary.textContent = (cf.signal || "WAIT") + " · " + (cf.bullish_count || 0) + "/" + (cf.total || 0) + " bullish";
            var lastRef = document.getElementById("last-refresh-time");
            if (lastRef) lastRef.textContent = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            setDebug({ "module-timeframe-result": "ok" });
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            var c = document.getElementById("confluence-summary");
            if (c) c.textContent = "Error";
            setDebug({ "module-timeframe-status": "err", "module-timeframe-result": msg });
        }
    }

    async function loadKeyLevels(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/pivot-points/" + encodeURIComponent(sym);
        setDebug({ "module-keylevels-symbol": sym, "module-keylevels-status": "..." });
        var resEl = document.getElementById("resistance-level");
        var supEl = document.getElementById("support-level");
        var priceEl = document.getElementById("sr-current-price");
        var barEl = document.getElementById("price-position-bar");
        try {
            var res = await fetch(url);
            setDebug({ "module-keylevels-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                if (resEl) resEl.textContent = "--";
                if (supEl) supEl.textContent = "--";
                if (priceEl) priceEl.textContent = "--";
                if (barEl) barEl.style.width = "50%";
                setDebug({ "module-keylevels-result": data && data.error ? data.error : "no data" });
                return;
            }
            var cur = data.current_price != null ? Number(data.current_price) : NaN;
            var r = data.nearest_resistance && data.nearest_resistance.price != null ? Number(data.nearest_resistance.price) : null;
            var s = data.nearest_support && data.nearest_support.price != null ? Number(data.nearest_support.price) : null;
            if (resEl) resEl.textContent = r != null ? r.toFixed(2) : "--";
            if (supEl) supEl.textContent = s != null ? s.toFixed(2) : "--";
            if (priceEl) priceEl.textContent = !isNaN(cur) ? cur.toFixed(2) : "--";
            if (barEl && !isNaN(cur) && r != null && s != null && r > s) {
                var pct = ((cur - s) / (r - s)) * 100;
                pct = Math.max(0, Math.min(100, pct));
                barEl.style.width = pct + "%";
            }
            setDebug({ "module-keylevels-result": "ok" });
        } catch (e) {
            if (resEl) resEl.textContent = "--";
            if (supEl) supEl.textContent = "--";
            if (priceEl) priceEl.textContent = "--";
            setDebug({ "module-keylevels-status": "err", "module-keylevels-result": (e && e.message) ? e.message : String(e) });
        }
    }

    async function loadScalpingLevels(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/scalping-levels/" + encodeURIComponent(sym);
        var wrap = document.getElementById("scalping-levels-body");
        var loadingEl = document.getElementById("scalping-loading");
        setDebug({ "module-scalping-symbol": sym, "module-scalping-status": "..." });
        if (loadingEl) loadingEl.textContent = "Loading levels...";
        try {
            var res = await fetch(url);
            setDebug({ "module-scalping-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                if (loadingEl) loadingEl.textContent = "No scalping levels for " + sym + ".";
                setDebug({ "module-scalping-result": data && data.error ? data.error : "no data" });
                return;
            }
            if (loadingEl) loadingEl.style.display = "none";
            var best = document.getElementById("scalping-best-range");
            var atr = document.getElementById("scalping-atr-range");
            var fib = document.getElementById("scalping-fib-levels");
            var tfs = document.getElementById("scalping-timeframes");
            var br = data.best_retracement_range || {};
            if (best) best.textContent = br.zone ? "Best zone: " + br.zone + (br.timeframe ? " (" + br.timeframe + ")" : "") : "";
            if (atr) atr.textContent = (br.atr_move != null) ? "ATR move: " + br.atr_move + (br.atr_pct != null ? " (" + br.atr_pct + "%)" : "") : "";
            if (fib && br.levels && typeof br.levels === "object") {
                var parts = [];
                for (var lk in br.levels) { if (br.levels.hasOwnProperty(lk)) parts.push(lk + " " + br.levels[lk]); }
                fib.innerHTML = parts.length ? parts.join(" · ") : "";
            } else if (fib) fib.innerHTML = "";
            if (tfs && data.timeframes && typeof data.timeframes === "object") {
                var tfHtml = "";
                for (var k in data.timeframes) {
                    if (!data.timeframes.hasOwnProperty(k)) continue;
                    var tfd = data.timeframes[k];
                    tfHtml += "<div class=\"small text-muted\">" + escapeHtml(k) + (tfd && tfd.current_price != null ? " $" + tfd.current_price : "") + "</div>";
                }
                tfs.innerHTML = tfHtml || "";
            }
            setDebug({ "module-scalping-result": "ok" });
        } catch (e) {
            if (loadingEl) { loadingEl.style.display = ""; loadingEl.textContent = "Error loading levels."; }
            setDebug({ "module-scalping-status": "err", "module-scalping-result": (e && e.message) ? e.message : String(e) });
        }
    }

    async function loadPremarketTrend(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/premarket-analysis/" + encodeURIComponent(sym);
        setDebug({ "module-premarket-symbol": sym, "module-premarket-status": "..." });
        var dirEl = document.getElementById("premarket-direction");
        var trendEl = document.getElementById("premarket-trend");
        var priceEl = document.getElementById("premarket-price");
        var changeEl = document.getElementById("premarket-change");
        var outlookEl = document.getElementById("premarket-outlook");
        try {
            var res = await fetch(url);
            setDebug({ "module-premarket-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                if (dirEl) dirEl.textContent = "--";
                if (trendEl) trendEl.textContent = "No premarket data for " + sym;
                if (priceEl) priceEl.textContent = "$--";
                if (changeEl) changeEl.textContent = "--";
                if (outlookEl) outlookEl.textContent = "";
                setDebug({ "module-premarket-result": data && data.error ? data.error : "no data" });
                return;
            }
            if (dirEl) dirEl.textContent = data.direction || "--";
            if (dirEl && data.color) dirEl.style.color = data.color;
            if (trendEl) trendEl.textContent = data.trend || "--";
            if (trendEl && data.color) trendEl.style.color = data.color;
            if (priceEl) priceEl.textContent = data.current_price != null ? "$" + Number(data.current_price).toFixed(2) : "$--";
            if (changeEl) {
                var ch = data.change != null ? Number(data.change) : 0;
                var pct = data.change_percent != null ? Number(data.change_percent) : 0;
                changeEl.innerHTML = (ch >= 0 ? "+" : "") + ch.toFixed(2) + " (" + (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%)";
                changeEl.className = ch >= 0 ? "fw-bold text-success" : "fw-bold text-danger";
            }
            if (outlookEl) outlookEl.textContent = data.outlook || "";
            setDebug({ "module-premarket-result": "ok" });
        } catch (e) {
            if (dirEl) dirEl.textContent = "--";
            if (trendEl) trendEl.textContent = "Error loading premarket.";
            setDebug({ "module-premarket-status": "err", "module-premarket-result": (e && e.message) ? e.message : String(e) });
        }
    }
    window.refreshPremarket = loadPremarketTrend;

    async function loadSignals(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var feed = document.getElementById("signal-feed");
        if (!feed) return;
        feed.innerHTML = "<div class=\"list-group-item bg-dark text-muted text-center py-3\">Loading...</div>";
        try {
            var res = await fetch("/api/signals?limit=20");
            var data = null;
            try { data = await res.json(); } catch (e) {}
            var signals = Array.isArray(data) ? data : [];
            var forSymbol = signals.filter(function(s) { return (s.symbol || "").toUpperCase() === sym; }).slice(0, 10);
            feed.innerHTML = "";
            if (forSymbol.length === 0) {
                feed.innerHTML = "<div class=\"list-group-item bg-dark text-muted text-center py-3\">No signals yet for " + sym + "</div>";
                return;
            }
            forSymbol.forEach(function(signal) {
                var typeClass = (signal.signal_type || "").indexOf("BUY") >= 0 ? "text-success" : (signal.signal_type || "").indexOf("SELL") >= 0 ? "text-danger" : "text-warning";
                var time = signal.timestamp ? new Date(signal.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "--:--";
                var item = document.createElement("div");
                item.className = "list-group-item bg-dark border-secondary py-2";
                item.innerHTML = "<div class=\"d-flex justify-content-between align-items-center\"><div><span class=\"fw-bold text-light\">" + escapeHtml(signal.symbol || "--") + "</span><span class=\"badge " + typeClass.replace("text-", "bg-") + " ms-2\">" + escapeHtml(signal.signal_type || "--") + "</span></div><small class=\"text-muted\">" + time + "</small></div><div class=\"small text-light\">$" + (signal.price != null ? Number(signal.price).toFixed(2) : "0.00") + " | " + (signal.strength != null ? signal.strength : 0) + "%</div>";
                feed.appendChild(item);
            });
        } catch (e) {
            feed.innerHTML = "<div class=\"list-group-item bg-dark text-muted text-center py-3\">No signals yet</div>";
        }
    }

    async function loadMarketOpenScan(phase) {
        var ph = phase || "5min";
        var content = document.getElementById("market-open-content");
        var phaseLabel = document.getElementById("market-open-phase");
        var phaseLabels = { premarket: "Pre-Market Analysis", "5min": "First 5 Minutes", "15min": "First 15 Minutes", "30min": "First 30 Minutes" };
        if (phaseLabel) phaseLabel.innerHTML = "<span class=\"badge bg-info\"><i class=\"bi bi-arrow-clockwise spin\"></i> Scanning...</span>";
        if (content) content.innerHTML = "<div class=\"text-center text-info py-3\"><i class=\"bi bi-arrow-clockwise spin\"></i> Finding top trending stocks...</div>";
        try {
            var res = await fetch("/api/market-open-scan?phase=" + encodeURIComponent(ph));
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (phaseLabel) phaseLabel.innerHTML = "<span class=\"badge bg-success\">" + (data && data.phase_label ? data.phase_label : phaseLabels[ph] || ph) + "</span>";
            if (data && data.success && data.trending_picks && data.trending_picks.length > 0) {
                var picksHtml = data.trending_picks.map(function(pick, i) {
                    var isCall = pick.option_type === "CALL";
                    var glowClass = isCall ? "lottery-glow-green" : "lottery-glow-red";
                    return "<div class=\"lottery-pick-card " + glowClass + " mb-2\"><div class=\"lottery-pick-header\"><span class=\"lottery-rank\">#" + (i + 1) + "</span><span class=\"lottery-symbol\">" + escapeHtml(pick.symbol || "") + "</span><span class=\"lottery-direction\">" + (pick.option_type || "") + "</span></div><div class=\"lottery-price\">$" + (pick.current_price != null ? Number(pick.current_price).toFixed(2) : "") + " <span class=\"" + (pick.price_change_pct >= 0 ? "text-success" : "text-danger") + "\">" + (pick.price_change_pct >= 0 ? "+" : "") + (pick.price_change_pct != null ? Number(pick.price_change_pct).toFixed(1) : "") + "%</span></div><div class=\"lottery-pick-body\"><div class=\"lottery-reason\">" + escapeHtml(pick.reason || "") + "</div></div></div>";
                }).join("");
                content.innerHTML = "<div class=\"mb-2 text-center\"><small class=\"text-muted\">Scanned at " + (data.scan_time || "") + " | " + (data.total_scanned || 0) + " tickers</small></div>" + picksHtml;
            } else {
                content.innerHTML = "<div class=\"text-center text-muted py-3\"><i class=\"bi bi-search\"></i> No strong trends found yet.</div>";
            }
        } catch (e) {
            if (phaseLabel) phaseLabel.innerHTML = "<span class=\"badge bg-secondary\">Scan failed</span>";
            if (content) content.innerHTML = "<div class=\"text-center text-danger py-3\">Error scanning.</div>";
        }
    }

    var ALERT_SCORE_THRESHOLD = 70;
    var lastAlertKey = "";

    function triggerAlert(title, body, type) {
        if (typeof console !== "undefined" && console.log) {
            console.log("[Alert] " + title + " | " + body);
        }
        try {
            if (typeof window !== "undefined" && window.Notification && Notification.permission === "granted") {
                new Notification(title, { body: body });
            }
        } catch (e) {}
    }

    async function loadTradingIntelligence(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var phaseEl = document.getElementById("market-phase-value");
        var phaseDesc = document.getElementById("market-phase-desc");
        var phaseConf = document.getElementById("market-phase-confidence");
        try {
            var res = await fetch("/api/trading-intelligence/" + encodeURIComponent(sym) + "?_t=" + Date.now());
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                if (phaseEl) phaseEl.textContent = "--";
                if (phaseDesc) phaseDesc.textContent = data && data.error ? data.error : "No data";
                if (phaseConf) phaseConf.textContent = "--";
                updateDebugPanelStep5(null, sym);
                return;
            }
            var mp = data.market_phase || {};
            if (phaseEl) phaseEl.textContent = mp.phase || "--";
            if (phaseDesc) phaseDesc.textContent = mp.description || "--";
            if (phaseConf) phaseConf.textContent = (mp.confidence != null ? Math.round(mp.confidence) + "%" : "--");
            var signals = data.signals || [];
            var feed = document.getElementById("signal-feed");
            if (feed && signals.length > 0) {
                var existingPlaceholder = feed.querySelector(".text-muted.text-center");
                if (existingPlaceholder) existingPlaceholder.remove();
                for (var i = 0; i < Math.min(signals.length, 5); i++) {
                    var s = signals[i];
                    var typeClass = (s.signal_type || "").indexOf("Bear") !== -1 || (s.trend_direction || "") === "BEARISH" ? "text-danger" : "text-success";
                    var timeStr = s.timestamp ? new Date(s.timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "--:--";
                    var scoreStr = s.trade_score != null ? " Score " + Math.round(s.trade_score) : "";
                    var item = document.createElement("div");
                    item.className = "list-group-item bg-dark border-secondary py-2";
                    item.innerHTML = "<div class=\"d-flex justify-content-between align-items-center\"><div><span class=\"fw-bold text-light\">" + escapeHtml(sym) + "</span> <span class=\"badge " + typeClass.replace("text-", "bg-") + " ms-1\">" + escapeHtml(s.signal_type || "Signal") + "</span><span class=\"badge bg-info ms-1\">" + (s.trade_score != null ? Math.round(s.trade_score) : "--") + "</span></div><small class=\"text-muted\">" + timeStr + "</small></div><div class=\"small text-light\">$" + (s.price != null ? Number(s.price).toFixed(2) : "--") + " | " + (s.confidence != null ? s.confidence + "%" : "") + scoreStr + "</div>";
                    if (!feed.querySelector(".list-group-item:first-child") || feed.querySelector(".list-group-item:first-child").textContent.indexOf(sym) === -1) {
                        feed.insertBefore(item, feed.firstChild);
                    }
                }
                while (feed.children.length > 15) feed.removeChild(feed.lastChild);
            }
            updateDebugPanelStep5(data, sym);
            var mom = data.momentum || {};
            var score = (data.trade_scoring || {}).score;
            if (score != null && score >= ALERT_SCORE_THRESHOLD) {
                var key = sym + "|" + score + "|" + (signals[0] && signals[0].signal_type);
                if (key !== lastAlertKey) {
                    lastAlertKey = key;
                    triggerAlert("High-probability signal: " + sym, (signals[0] && signals[0].signal_type) + " Score " + Math.round(score), "signal");
                }
            }
            if (signals.length > 0 && (signals[0].signal_type === "VWAP Reclaim" || signals[0].signal_type === "Breakout")) {
                var key2 = sym + "|vwap|" + (signals[0].timestamp || "");
                if (key2 !== lastAlertKey) {
                    lastAlertKey = key2;
                    triggerAlert(signals[0].signal_type + " " + sym, "Price $" + (signals[0].price != null ? signals[0].price.toFixed(2) : ""), "event");
                }
            }
        } catch (e) {
            if (phaseEl) phaseEl.textContent = "--";
            if (phaseDesc) phaseDesc.textContent = "Error loading";
            updateDebugPanelStep5(null, sym);
        }
    }

    function updateDebugPanelStep5(data, symbol) {
        if (typeof window !== "undefined" && window.DEVELOPER_MODE !== true) return;
        var sym = (symbol || currentTicker || "").toString().toUpperCase();
        setEl("debug-current-ticker", sym || "--");
        setEl("debug-signal-count", data && data.signals ? String(data.signals.length) : "0");
        setEl("debug-options-scanner-status", data ? "ok" : "--");
        setEl("debug-momentum-score", data && data.momentum && data.momentum.momentum_score != null ? String(data.momentum.momentum_score) : "--");
        setEl("debug-market-phase", data && data.market_phase ? (data.market_phase.phase || "--") : "--");
        setEl("debug-engine-status", data ? "ok" : "--");
        var lastSig = data && data.signals && data.signals[0] ? data.signals[0].timestamp : null;
        setEl("debug-last-signal-time", lastSig ? new Date(lastSig).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--");
        function setEl(id, val) {
            var el = document.getElementById(id);
            if (el) el.textContent = val;
        }
    }

    async function loadCheapOptionsRadar(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var content = document.getElementById("cheap-options-radar-content");
        if (!content) return;
        content.innerHTML = "<div class=\"text-muted text-center py-2\"><i class=\"bi bi-arrow-clockwise spin\"></i> Loading...</div>";
        try {
            var res = await fetch("/api/cheap-options-radar/" + encodeURIComponent(sym) + "?_t=" + Date.now());
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                content.innerHTML = "<div class=\"text-muted text-center py-2\">" + (data && data.error ? data.error : "No options data") + "</div>";
                return;
            }
            var contracts = data.contracts || [];
            if (contracts.length === 0) {
                content.innerHTML = "<div class=\"text-muted text-center py-2\">No cheap options found for " + sym + "</div>";
                return;
            }
            var html = "";
            for (var i = 0; i < contracts.length; i++) {
                var c = contracts[i];
                html += "<div class=\"d-flex justify-content-between align-items-center py-1 border-bottom border-secondary\"><span>" + escapeHtml(c.option_type || "CALL") + " $" + (c.strike != null ? c.strike : "--") + "</span><span>$" + (c.premium != null ? Number(c.premium).toFixed(2) : "--") + "</span><span class=\"badge bg-secondary\">" + (c.signal_score != null ? c.signal_score : "--") + "</span></div>";
                if (c.expiration) html += "<div class=\"small text-muted\">Exp " + c.expiration + "</div>";
            }
            content.innerHTML = html;
        } catch (e) {
            content.innerHTML = "<div class=\"text-muted text-center py-2\">Error loading options.</div>";
        }
    }

    async function loadAnalysis(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
        var url = "/api/trade-recommendation/" + encodeURIComponent(sym);
        setDebug({
            "module-analysis-symbol": sym,
            "module-analysis-endpoint": url,
            "module-analysis-status": "...",
            "module-analysis-result": "..."
        });
        var signalText = document.getElementById("main-signal-text");
        var signalSummary = document.getElementById("signal-summary");
        var panel = document.getElementById("main-signal-panel");
        var trafficLight = document.getElementById("traffic-light");
        if (signalSummary) signalSummary.textContent = "Loading analysis...";
        try {
            var res = await fetch(url);
            setDebug({ "module-analysis-status": String(res.status) });
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data) {
                setDebug({ "module-analysis-result": "Invalid JSON", "module-analysis-indicators": "--", "module-analysis-bullish": "--", "module-analysis-bearish": "--", "module-analysis-total": "--" });
                if (signalText) signalText.textContent = "WAIT";
                if (signalSummary) signalSummary.textContent = "Analysis request failed (invalid response).";
                if (panel) { panel.classList.remove("signal-buy", "signal-sell"); panel.classList.add("signal-wait"); }
                if (trafficLight) setTrafficLight(trafficLight, "yellow");
                return;
            }
            if (data.error) {
                setDebug({ "module-analysis-result": "error: " + data.error, "module-analysis-indicators": "--", "module-analysis-bullish": "--", "module-analysis-bearish": "--", "module-analysis-total": "--" });
                if (signalText) signalText.textContent = "WAIT";
                if (signalSummary) signalSummary.textContent = "Analysis failed: " + data.error;
                if (panel) { panel.classList.remove("signal-buy", "signal-sell"); panel.classList.add("signal-wait"); }
                if (trafficLight) setTrafficLight(trafficLight, "yellow");
                return;
            }
            var mainSignal = (data.main_signal || "WAIT").toString();
            lastMainSignal = mainSignal.indexOf("BUY") !== -1 ? "BUY" : (mainSignal.indexOf("SELL") !== -1 ? "SELL" : "PREPARE");
            var summary = data.summary || "No summary.";
            var indList = (data.evaluated_indicators || []).join(", ") || "--";
            var bull = data.bullish_count != null ? String(data.bullish_count) : "--";
            var bear = data.bearish_count != null ? String(data.bearish_count) : "--";
            var tot = data.total_count != null ? String(data.total_count) : "--";
            updateIndicatorsPanel(data.indicators || {});
            if (priceChart && lastOverlayData) applyChartOverlays(priceChart, Object.assign({}, lastOverlayData, { mainSignal: lastMainSignal }));
            setDebug({
                "module-analysis-result": "ok " + mainSignal,
                "module-analysis-indicators": indList,
                "module-analysis-bullish": bull,
                "module-analysis-bearish": bear,
                "module-analysis-total": tot
            });
            if (signalText) signalText.textContent = mainSignal;
            if (signalSummary) signalSummary.textContent = summary;
            if (panel) {
                panel.classList.remove("signal-buy", "signal-sell", "signal-wait");
                if (mainSignal.indexOf("BUY") !== -1) panel.classList.add("signal-buy");
                else if (mainSignal.indexOf("SELL") !== -1) panel.classList.add("signal-sell");
                else panel.classList.add("signal-wait");
            }
            if (trafficLight) {
                if (mainSignal.indexOf("BUY") !== -1) setTrafficLight(trafficLight, "green");
                else if (mainSignal.indexOf("SELL") !== -1) setTrafficLight(trafficLight, "red");
                else setTrafficLight(trafficLight, "yellow");
            }
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            setDebug({ "module-analysis-result": "error: " + msg, "module-analysis-indicators": "--", "module-analysis-bullish": "--", "module-analysis-bearish": "--", "module-analysis-total": "--" });
            if (signalText) signalText.textContent = "WAIT";
            if (signalSummary) signalSummary.textContent = "Analysis failed: " + msg;
            if (panel) { panel.classList.remove("signal-buy", "signal-sell"); panel.classList.add("signal-wait"); }
            if (trafficLight) setTrafficLight(trafficLight, "yellow");
        }
    }

    function setTrafficLight(container, activeColor) {
        if (!container) return;
        var lights = container.querySelectorAll(".light");
        for (var i = 0; i < lights.length; i++) {
            var l = lights[i];
            if (l.classList.contains(activeColor)) l.classList.add("active");
            else l.classList.remove("active");
        }
    }

    function updateIndicatorsPanel(ind) {
        function set(id, text, badgeClass) {
            var el = document.getElementById(id);
            if (!el) return;
            el.textContent = text != null && text !== "" ? text : "--";
            if (badgeClass && el.classList && el.classList.contains("badge")) {
                el.className = "badge small " + badgeClass;
            }
        }
        var rsi = ind.rsi || {};
        var rsiVal = rsi.value != null ? Math.round(rsi.value) : "--";
        set("rsi-value", rsiVal);
        var rsiSig = "Neutral";
        if (rsi.value != null) { if (rsi.value >= 70) rsiSig = "Overbought"; else if (rsi.value <= 30) rsiSig = "Oversold"; }
        set("rsi-signal", rsiSig, rsiSig === "Overbought" ? "bg-danger" : rsiSig === "Oversold" ? "bg-success" : "bg-secondary");
        var macd = ind.macd || {};
        set("macd-value", macd.histogram != null ? macd.histogram.toFixed(3) : "--");
        var macdSig = (macd.signal_type || "Neutral").toString();
        if (macdSig.indexOf("BULLISH") !== -1) macdSig = "Bullish Cross";
        else if (macdSig.indexOf("BEARISH") !== -1) macdSig = "Bearish Cross";
        else macdSig = "Neutral";
        set("macd-signal", macdSig, macdSig === "Bullish Cross" ? "bg-success" : macdSig === "Bearish Cross" ? "bg-danger" : "bg-secondary");
        var bb = ind.bollinger || {};
        set("bb-position", bb.price_position || "--");
        set("bb-signal", bb.signal || "--", "bg-secondary");
        var vol = ind.volume || {};
        var volRatio = vol.spike_ratio != null ? vol.spike_ratio : 1;
        set("volume-value", volRatio !== 1 ? volRatio.toFixed(1) + "x" : "1x");
        set("volume-signal", vol.spike ? "Expanding" : (volRatio >= 1.2 ? "Expanding" : "Weak"), vol.spike || volRatio >= 1.2 ? "bg-success" : "bg-secondary");
        var vwap = ind.vwap || {};
        set("vwap-value", vwap.value != null ? "$" + Number(vwap.value).toFixed(2) : "--");
        set("vwap-signal", vwap.above_vwap ? "Above" : "Below", vwap.above_vwap ? "bg-success" : "bg-danger");
        var trend = ind.trend || {};
        var dir = (trend.direction || "NEUTRAL").toString();
        var trendLabel = dir === "BULLISH" ? "Uptrend" : dir === "BEARISH" ? "Downtrend" : "Range";
        set("trend-value", trend.strength != null ? trend.strength + "%" : "--");
        set("trend-signal", trendLabel, dir === "BULLISH" ? "bg-success" : dir === "BEARISH" ? "bg-danger" : "bg-secondary");
        var ema = ind.ema || {};
        set("ema-13-value", ema.price_vs_ema_13 === "ABOVE" ? "Above" : ema.price_vs_ema_13 === "BELOW" ? "Below" : "--");
        set("ema-48-value", ema.price_vs_ema_48 === "ABOVE" ? "Above" : ema.price_vs_ema_48 === "BELOW" ? "Below" : "--");
        set("ema-200-value", ema.price_vs_ema_200 === "ABOVE" ? "Above" : ema.price_vs_ema_200 === "BELOW" ? "Below" : "--");
        var sumEl = document.getElementById("indicators-summary");
        if (sumEl) sumEl.textContent = (rsiVal !== "--" ? "RSI " + rsiVal : "") + (trendLabel ? " · " + trendLabel : "") + (vwap.above_vwap !== undefined ? (vwap.above_vwap ? " · Above VWAP" : " · Below VWAP") : "");
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initSimpleDashboard);
    } else {
        initSimpleDashboard();
    }
    window.addEventListener("load", function() {
        if (!window.__simpleDashboardInitialized) initSimpleDashboard();
    });
})();
