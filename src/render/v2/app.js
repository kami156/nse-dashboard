/* NSE Market Intelligence v2 — dependency-free interactions.
   Deep links use replaceState and explicit scroll offsets; no element
   scroll-into-view calls, which break the embedded preview. */
(function () {
  "use strict";
  var root = document.documentElement;
  var $ = function (s, c) { return (c || document).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || document).querySelectorAll(s)); };
  /* resolved up front: refreshCounts() runs during workspace init, before the
     filter wiring further down the file. */
  var search = $("#global-search");
  var filters = $$(".js-filter") || [];

  /* ------------------------------------------------------------------ theme */
  var themeBtn = $("#theme-toggle");
  function syncTheme() {
    if (!themeBtn) return;
    var dark = root.getAttribute("data-theme") === "dark";
    themeBtn.textContent = dark ? "Light" : "Dark";
    themeBtn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    themeBtn.setAttribute("aria-pressed", dark ? "true" : "false");
  }
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("nse-theme", next); } catch (e) {}
      syncTheme();
    });
  }
  syncTheme();

  /* ------------------------------------------------------- workspace tabs */
  var tabs = $$(".tab[data-ws]");
  var panes = $$(".ws[data-ws]");
  function showWorkspace(id, scroll) {
    var found = false;
    panes.forEach(function (p) {
      var on = p.getAttribute("data-ws") === id;
      p.hidden = !on;
      if (on) found = true;
    });
    if (!found) return false;
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-ws") === id;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    });
    try { localStorage.setItem("nse-workspace", id); } catch (e) {}
    if (history.replaceState) history.replaceState(null, "", "#" + id);
    if (scroll && window.scrollTo) window.scrollTo({ top: 0, behavior: "auto" });
    refreshCounts();
    return true;
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { showWorkspace(t.getAttribute("data-ws"), true); });
    t.addEventListener("keydown", function (e) {
      var i = tabs.indexOf(t), n = null;
      if (e.key === "ArrowRight") n = tabs[(i + 1) % tabs.length];
      else if (e.key === "ArrowLeft") n = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (e.key === "Home") n = tabs[0];
      else if (e.key === "End") n = tabs[tabs.length - 1];
      if (n) { e.preventDefault(); n.focus(); showWorkspace(n.getAttribute("data-ws"), true); }
    });
  });
  var hash = (location.hash || "").replace("#", "");
  var saved = null;
  try { saved = localStorage.getItem("nse-workspace"); } catch (e) {}
  if (!showWorkspace(hash || saved || (tabs[0] && tabs[0].getAttribute("data-ws")))) {
    if (tabs[0]) showWorkspace(tabs[0].getAttribute("data-ws"));
  }

  /* ---------------------------------------------------------- sub tabs */
  $$(".subtab[data-group]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var group = btn.getAttribute("data-group");
      $$('.subtab[data-group="' + group + '"]').forEach(function (b) {
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      $$('.js-sub[data-group="' + group + '"]').forEach(function (p) {
        p.hidden = p.getAttribute("data-sub") !== btn.getAttribute("data-sub");
      });
      try { localStorage.setItem("nse-sub-" + group, btn.getAttribute("data-sub")); } catch (e) {}
      refreshCounts();
    });
    var group = btn.getAttribute("data-group");
    var want = null;
    try { want = localStorage.getItem("nse-sub-" + group); } catch (e) {}
    if (want && btn.getAttribute("data-sub") === want) btn.click();
  });

  /* --------------------------------------------------------- sort tables */
  $$("table.tbl").forEach(function (table) {
    $$("thead th", table).forEach(function (th, idx) {
      var btn = $(".sort", th);
      if (!btn) return;
      btn.addEventListener("click", function () {
        var body = table.tBodies[0];
        if (!body) return;
        var asc = th.getAttribute("aria-sort") !== "ascending";
        $$("thead th", table).forEach(function (o) { o.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        var rows = $$("tr", body);
        rows.sort(function (a, b) {
          var ac = a.children[idx], bc = b.children[idx];
          var av = ac ? (ac.getAttribute("data-sort") || ac.innerText.trim()) : "";
          var bv = bc ? (bc.getAttribute("data-sort") || bc.innerText.trim()) : "";
          var an = parseFloat(String(av).replace(/[^0-9eE+\-.]/g, ""));
          var bn = parseFloat(String(bv).replace(/[^0-9eE+\-.]/g, ""));
          var both = !isNaN(an) && !isNaN(bn) &&
            /[0-9]/.test(String(av)) && /[0-9]/.test(String(bv));
          if (both) return asc ? an - bn : bn - an;
          return asc ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });

  /* ------------------------------------------------------------- filters */
  filters.forEach(function (sel) { sel.addEventListener("change", refreshCounts); });

  function passesRow(tr) {
    var ws = tr.closest(".ws[data-ws]");
    if (ws && ws.hidden) return true;
    var q = search ? search.value.toLowerCase().trim() : "";
    if (q && tr.innerText.toLowerCase().indexOf(q) === -1) return false;
    var table = tr.closest("table");
    if (!table) return true;
    for (var i = 0; i < filters.length; i++) {
      var f = filters[i];
      if (f.getAttribute("data-table") !== table.id || !f.value) continue;
      var cell = tr.children[parseInt(f.getAttribute("data-col"), 10)];
      if (!cell || cell.innerText.trim() !== f.value) return false;
    }
    return true;
  }
  function refreshCounts() {
    $$("table.tbl[data-count]").forEach(function (table) {
      var body = table.tBodies[0];
      if (!body) return;
      var vis = 0;
      $$("tr", body).forEach(function (tr) {
        var show = passesRow(tr);
        tr.hidden = !show;
        if (show) vis++;
      });
      var out = document.querySelector('.js-count[data-for="' + table.getAttribute("data-count") + '"]');
      if (out) out.textContent = vis + " / " + $$("tr", body).length + " rows";
      var panel = table.closest(".panel");
      var emp = panel ? $(".js-empty", panel) : null;
      if (emp) emp.hidden = vis !== 0;
    });
    $$(".js-filterable").forEach(function (el) {
      var ws = el.closest(".ws[data-ws]");
      if (ws && ws.hidden) return;
      var q = search ? search.value.toLowerCase().trim() : "";
      el.hidden = !!q && el.innerText.toLowerCase().indexOf(q) === -1;
    });
  }
  if (search) search.addEventListener("input", refreshCounts);
  refreshCounts();

  /* ----------------------------------------------------------- CSV export */
  $$(".js-csv").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var table = document.getElementById(btn.getAttribute("data-target"));
      if (!table) return;
      var rows = [];
      var heads = $$("thead th", table).map(function (th) { return th.innerText.trim(); });
      rows.push(heads);
      $$("tbody tr", table).forEach(function (tr) {
        if (tr.hidden) return;
        rows.push($$("td", tr).map(function (td) {
          var t = td.innerText.trim().replace(/\s+/g, " ");
          return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
        }));
      });
      var csv = rows.map(function (r) { return r.join(","); }).join("\r\n");
      var url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
      var a = document.createElement("a");
      a.href = url;
      a.download = (btn.getAttribute("data-target") || "table") + ".csv";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1500);
      var old = btn.textContent;
      btn.textContent = "Saved";
      setTimeout(function () { btn.textContent = old; }, 1200);
    });
  });

  /* --------------------------------------------------------- line charts */
  $$(".chart[data-values]").forEach(function (wrap) {
    var vals;
    try { vals = JSON.parse(wrap.getAttribute("data-values") || "[]"); } catch (err) { vals = []; }
    vals = vals.filter(function (v) { return typeof v === "number" && isFinite(v); });
    if (vals.length < 2) return;
    var svg = $("svg", wrap), tip = $(".tip", wrap);
    if (!svg) return;
    var W = 1000, H = 260, PL = 8, PR = 8, PT = 12, PB = 22;
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
    var pad = (mx - mn || 1) * 0.08, lo = mn - pad, hi = mx + pad, rng = hi - lo;
    var n = vals.length;
    var X = function (i) { return PL + (i / (n - 1)) * (W - PL - PR); };
    var Y = function (v) { return PT + (1 - (v - lo) / rng) * (H - PT - PB); };
    var line = vals.map(function (v, i) { return X(i).toFixed(1) + "," + Y(v).toFixed(1); }).join(" ");
    var area = line + " " + X(n - 1).toFixed(1) + "," + (H - PB) + " " + X(0).toFixed(1) + "," + (H - PB);
    var ticks = [{ v: mx, t: "max" }, { v: (mx + mn) / 2, t: "mid" }, { v: mn, t: "min" }];
    var ref = vals[0];

    function fmt(v) { return v.toLocaleString(undefined, { maximumFractionDigits: 2 }); }

    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.innerHTML =
      ticks.map(function (k) {
        return '<line class="gridline" x1="0" y1="' + Y(k.v).toFixed(1) + '" x2="' + W + '" y2="' + Y(k.v).toFixed(1) + '"/>';
      }).join("") +
      '<line class="ref" x1="0" y1="' + Y(ref).toFixed(1) + '" x2="' + W + '" y2="' + Y(ref).toFixed(1) + '"/>' +
      '<polygon class="area" points="' + area + '"/>' +
      '<polyline class="series" points="' + line + '"/>' +
      '<line class="cross" x1="0" y1="' + PT + '" x2="0" y2="' + (H - PB) + '" style="display:none"/>' +
      '<circle class="dot" r="3.5" style="display:none"/>';

    var cross = $(".cross", svg), dot = $(".dot", svg);
    var labels = ticks.map(function (k) {
      var el = document.createElement("span");
      el.className = "ytick";
      el.textContent = fmt(k.v);
      wrap.appendChild(el);
      return el;
    });
    function placeLabels() {
      var box = svg.getBoundingClientRect();
      var inner = parseFloat(getComputedStyle(wrap).paddingTop) || 0;
      ticks.forEach(function (k, i) {
        labels[i].style.top = (inner + (Y(k.v) / H) * box.height).toFixed(1) + "px";
      });
    }
    placeLabels();
    window.addEventListener("resize", placeLabels);
    window.addEventListener("load", placeLabels);

    var unit = wrap.getAttribute("data-unit") || "";
    function move(evt) {
      var box = svg.getBoundingClientRect();
      if (!box.width) return;
      var cx = (evt.touches ? evt.touches[0].clientX : evt.clientX) - box.left;
      var frac = Math.min(1, Math.max(0, (cx / box.width - PL / W) / ((W - PL - PR) / W)));
      var i = Math.round(frac * (n - 1));
      var v = vals[i], x = X(i), y = Y(v);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x);
      cross.style.display = ""; dot.style.display = "";
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      var ago = n - 1 - i;
      tip.innerHTML = "<b>" + fmt(v) + unit + "</b><span>" +
        (ago === 0 ? "latest session" : ago + " session" + (ago > 1 ? "s" : "") + " ago") + "</span>";
      tip.style.left = (box.left - wrap.getBoundingClientRect().left + (x / W) * box.width) + "px";
      tip.style.opacity = "1";
    }
    function leave() { tip.style.opacity = "0"; cross.style.display = "none"; dot.style.display = "none"; }
    wrap.addEventListener("mousemove", move);
    wrap.addEventListener("mouseleave", leave);
    wrap.addEventListener("touchmove", move, { passive: true });
    wrap.addEventListener("touchend", leave);
  });
})();
