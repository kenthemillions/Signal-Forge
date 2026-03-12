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

    async function loadQuote(symbol) {
        var sym = (symbol || currentTicker || "SPY").toString().trim().toUpperCase();
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
                "simple-debug-session": qd.session || "--"
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
    }

    function showChartNoData(show) {
        var el = document.getElementById("chart-no-data");
        if (el) {
            if (show) el.classList.remove("d-none"); else el.classList.add("d-none");
        }
    }

    function computeHeikinAshi(opens, highs, lows, closes) {
        var n = (closes && closes.length) || 0;
        var ha_o = [], ha_h = [], ha_l = [], ha_c = [];
        for (var i = 0; i < n; i++) {
            var o = opens[i], h = highs[i], l = lows[i], c = closes[i];
            ha_c[i] = (o + h + l + c) / 4;
            ha_o[i] = i === 0 ? (o + c) / 2 : (ha_o[i - 1] + ha_c[i - 1]) / 2;
            ha_h[i] = Math.max(h, ha_o[i], ha_c[i]);
            ha_l[i] = Math.min(l, ha_o[i], ha_c[i]);
        }
        return { opens: ha_o, highs: ha_h, lows: ha_l, closes: ha_c };
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

    function createCandlestickChart(ohlcData, isHA) {
        if (!chartCanvas || typeof Chart === "undefined") return;
        var hasCandle = typeof Chart.controllers !== "undefined" && Chart.controllers.candlestick;
        if (priceChart) priceChart.destroy();
        if (hasCandle && ohlcData && ohlcData.length > 0) {
            priceChart = new Chart(chartCanvas.getContext("2d"), {
                type: "candlestick",
                data: {
                    datasets: [{
                        label: isHA ? "HA" : "Price",
                        data: ohlcData,
                        color: { up: "#00e676", down: "#ff5252", unchanged: "#888" },
                        borderColor: { up: "#00e676", down: "#ff5252", unchanged: "#888" }
                    }]
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
        } else {
            createLineChart();
            if (priceChart && ohlcData && ohlcData.length) {
                priceChart.data.labels = ohlcData.map(function(d) {
                    var x = d.x;
                    return (x instanceof Date) ? x.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : x;
                });
                priceChart.data.datasets[0].data = ohlcData.map(function(d) { return d.c; });
                priceChart.update("none");
            }
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
                data: { labels: [], datasets: [{ label: "Volume", data: [], backgroundColor: "rgba(100, 149, 237, 0.5)", borderColor: "#6495ed", borderWidth: 1 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
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
                setDebug({ "module-chart-result": data.error || "no data", "module-chart-bars": "0" });
                if (noDataEl) noDataEl.textContent = "No chart data for this timeframe.";
                if (priceChart) { priceChart.destroy(); priceChart = null; createLineChart(); }
                if (priceChart && priceChart.data.datasets[0]) priceChart.data.datasets[0].data = [];
                if (priceChart) priceChart.update("none");
                showChartNoData(true);
                return;
            }
            var timestamps = data.timestamps || [];
            var opens = data.opens || [];
            var highs = data.highs || [];
            var lows = data.lows || [];
            var closes = data.closes || [];
            var n = closes.length;
            setDebug({ "module-chart-bars": String(n) });

            if (mode === "candle" || mode === "ha") {
                var useOpens = opens, useHighs = highs, useLows = lows, useCloses = closes;
                if (mode === "ha") {
                    var ha = computeHeikinAshi(opens, highs, lows, closes);
                    useOpens = ha.opens; useHighs = ha.highs; useLows = ha.lows; useCloses = ha.closes;
                }
                var ohlcData = [];
                for (var i = 0; i < n; i++) {
                    ohlcData.push({
                        x: timestamps[i] ? new Date(timestamps[i]) : new Date(i),
                        o: useOpens[i], h: useHighs[i], l: useLows[i], c: useCloses[i]
                    });
                }
                createCandlestickChart(ohlcData, mode === "ha");
            } else {
                if (priceChart && priceChart.config.type !== "line") {
                    priceChart.destroy();
                    priceChart = null;
                    createLineChart();
                }
                var labels = timestamps.map(function(t) {
                    var d = new Date(t);
                    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
                });
                priceChart.data.labels = labels;
                priceChart.data.datasets[0].data = closes;
                priceChart.update("none");
            }

            var vols = data.volumes || [];
            if (volumeChart && vols.length > 0) {
                var labels = (timestamps || []).map(function(t) { var d = new Date(t); return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }); });
                var bgColors = [];
                for (var v = 0; v < vols.length; v++) {
                    var isUp = (closes[v] || 0) >= (opens[v] || 0);
                    bgColors.push(isUp ? "rgba(0, 200, 100, 0.6)" : "rgba(255, 100, 100, 0.6)");
                }
                volumeChart.data.labels = labels.length ? labels : new Array(vols.length).fill("");
                volumeChart.data.datasets[0].data = vols;
                volumeChart.data.datasets[0].backgroundColor = bgColors;
                volumeChart.update("none");
            }
            showChartNoData(false);
            setDebug({ "module-chart-result": "ok " + n + " bars" });
        } catch (e) {
            var msg = (e && e.message) ? e.message : String(e);
            setDebug({ "module-chart-result": "error: " + msg, "module-chart-bars": "--" });
            if (noDataEl) noDataEl.textContent = "Chart failed: " + msg;
            if (priceChart) { priceChart.destroy(); priceChart = null; createLineChart(); }
            if (priceChart && priceChart.data.datasets[0]) priceChart.data.datasets[0].data = [];
            if (priceChart) priceChart.update("none");
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
