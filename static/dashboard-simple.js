(function() {
    "use strict";
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
        if (refreshBtn) refreshBtn.addEventListener("click", function() { loadQuote(currentTicker); });

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

        onSymbolChanged(currentTicker);
    }

    async function onSymbolChanged(symbol) {
        var sym = (symbol || "SPY").toString().trim().toUpperCase();
        currentTicker = sym;
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
                    bgColors.push(isUp ? "rgba(0, 200, 100, 0.7)" : "rgba(255, 100, 100, 0.7)");
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
        if (el) el.innerHTML = "<div class=\"text-center text-muted py-2\"><i class=\"bi bi-arrow-clockwise spin\"></i> Loading...</div>";
        try {
            var res = await fetch(url);
            if (statusEl) statusEl.textContent = String(res.status);
            var data = null;
            try { data = await res.json(); } catch (e) {}
            if (!data || data.error) {
                if (el) el.innerHTML = "<div class=\"text-center text-muted py-2\">No timeframe data for " + escapeHtml(sym) + ".</div>";
                setDebug({ "module-timeframe-result": data && data.error ? data.error : "no data" });
                return;
            }
            var cf = data.confluence || {};
            var html = "<div class=\"small\"><span class=\"badge me-2\" style=\"background:" + (cf.color || "#888") + "\">" + (cf.signal || "WAIT") + "</span> Bullish: " + (cf.bullish_count || 0) + " Bearish: " + (cf.bearish_count || 0) + " Total: " + (cf.total || 0) + "</div>";
            if (data.timeframes && typeof data.timeframes === "object") {
                for (var k in data.timeframes) {
                    if (!data.timeframes.hasOwnProperty(k)) continue;
                    var tf = data.timeframes[k];
                    html += "<div class=\"d-flex justify-content-between py-1 border-bottom border-secondary\"><span>" + escapeHtml(k) + "</span><span style=\"color:" + (tf.color || "#888") + "\">" + (tf.signal || tf.trend || "—") + "</span></div>";
                }
            }
            if (el) el.innerHTML = html;
            var lastRef = document.getElementById("last-refresh-time");
            if (lastRef) lastRef.textContent = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            setDebug({ "module-timeframe-result": "ok" });
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            if (el) el.innerHTML = "<div class=\"text-center text-danger py-2\">Error loading timeframe data.</div>";
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
            var summary = data.summary || "No summary.";
            var indList = (data.evaluated_indicators || []).join(", ") || "--";
            var bull = data.bullish_count != null ? String(data.bullish_count) : "--";
            var bear = data.bearish_count != null ? String(data.bearish_count) : "--";
            var tot = data.total_count != null ? String(data.total_count) : "--";
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

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initSimpleDashboard);
    } else {
        initSimpleDashboard();
    }
    window.addEventListener("load", function() {
        if (!window.__simpleDashboardInitialized) initSimpleDashboard();
    });
})();
