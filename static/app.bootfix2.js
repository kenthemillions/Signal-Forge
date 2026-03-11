document.documentElement.style.border = "10px solid red";
document.body.insertAdjacentHTML(
  "afterbegin",
  "<div id='boot-probe-banner' style='position:fixed;top:0;left:0;right:0;z-index:999999;background:red;color:white;font-size:24px;padding:12px;text-align:center;'>BOOT PROBE RAN - APP.BOOTFIX2.JS</div>"
);
console.log("BOOT PROBE RAN - APP.BOOTFIX2.JS");

(function boot() {
  var debugEl = document.createElement("div");
  debugEl.id = "boot-debug-box";
  debugEl.setAttribute("style", "position:fixed;top:80px;left:0;z-index:999998;background:black;color:lime;padding:10px;font-size:12px;font-family:monospace;max-width:90vw;");
  debugEl.innerHTML = "boot entered: <span id='boot-entered'>--</span><br>currentTicker: <span id='boot-ticker'>--</span><br>quote status: <span id='boot-quote-status'>--</span><br>quote body: <span id='boot-quote-body'>--</span>";
  if (document.body) document.body.insertAdjacentElement("afterbegin", debugEl);

  var set = function(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(val);
  };
  set("boot-entered", "yes");
  window.currentTicker = "SPY";
  set("boot-ticker", "SPY");

  fetch("/api/quote?symbol=SPY")
    .then(function(r) {
      set("boot-quote-status", r.status);
      return r.text();
    })
    .then(function(t) {
      set("boot-quote-body", t.length > 200 ? t.substring(0, 200) + "..." : t);
      var data;
      try { data = JSON.parse(t); } catch (e) { return; }
      var priceEl = document.getElementById("current-price");
      if (priceEl && data && data.price != null) priceEl.textContent = "$" + Number(data.price).toFixed(2);
    })
    .catch(function(e) {
      set("boot-quote-status", "err");
      set("boot-quote-body", (e && e.message) || String(e));
    });
})();
