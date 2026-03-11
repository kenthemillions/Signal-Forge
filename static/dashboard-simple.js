(function() {
    "use strict";
    var currentTicker = "SPY";

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
            setDebug({
                "simple-debug-symbol": (data.symbol || sym),
                "simple-debug-price": String(price.toFixed(2)),
                "simple-debug-error": "none"
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

        var refreshBtn = document.getElementById("ticker-card-refresh");
        if (refreshBtn) refreshBtn.addEventListener("click", function() { loadQuote(currentTicker); });

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
                setDebug({ "module-analysis-result": "Invalid JSON" });
                if (signalText) signalText.textContent = "WAIT";
                if (signalSummary) signalSummary.textContent = "Analysis request failed (invalid response).";
                if (panel) { panel.classList.remove("signal-buy", "signal-sell"); panel.classList.add("signal-wait"); }
                if (trafficLight) setTrafficLight(trafficLight, "yellow");
                return;
            }
            if (data.error) {
                setDebug({ "module-analysis-result": "error: " + data.error });
                if (signalText) signalText.textContent = "WAIT";
                if (signalSummary) signalSummary.textContent = "Analysis failed: " + data.error;
                if (panel) { panel.classList.remove("signal-buy", "signal-sell"); panel.classList.add("signal-wait"); }
                if (trafficLight) setTrafficLight(trafficLight, "yellow");
                return;
            }
            var mainSignal = (data.main_signal || "WAIT").toString();
            var summary = data.summary || "No summary.";
            setDebug({ "module-analysis-result": "ok " + mainSignal });
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
            setDebug({ "module-analysis-result": "error: " + msg });
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
