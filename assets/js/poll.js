// Your Call reader poll. Each <div class="dd-poll" data-q="13-20270315"> becomes a slider
// (0-100% in steps of 5). The crowd's answers stay hidden until this browser has voted.
(function () {
  var API = (document.documentElement.getAttribute("data-poll-api") || "").replace(/\/$/, "");
  var polls = document.querySelectorAll(".dd-poll[data-q]");
  if (!API || !polls.length) return;

  function voterId() {
    var id = null;
    try { id = localStorage.getItem("dd-voter"); } catch (e) {}
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2)));
      try { localStorage.setItem("dd-voter", id); } catch (e) {}
    }
    return id;
  }
  var VOTER = voterId();

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function pct(x) { return (Math.round(x * 10) / 10).toString().replace(/\.0$/, "") + "%"; }
  function closeLabel(q) {
    var d = q.split("-")[1];
    var dt = new Date(Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8)));
    return dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  }

  function renderResults(box, data) {
    var res = box.querySelector(".poll-results") || box.appendChild(el("div", "poll-results"));
    res.innerHTML = "";
    if (!data.count) { res.appendChild(el("p", "poll-note", "No answers yet.")); return; }
    var max = Math.max.apply(null, data.buckets);
    var chart = el("div", "poll-chart");
    chart.setAttribute("role", "img");
    chart.setAttribute("aria-label", data.count + " answers; median " + pct(data.median) + ", average " + pct(data.mean));
    data.buckets.forEach(function (n, i) {
      var col = el("div", "poll-col" + (data.mine === i * 5 ? " mine" : ""));
      var bar = el("div", "poll-bar");
      bar.style.height = (max ? Math.max(n ? 6 : 0, (n / max) * 100) : 0) + "%";
      bar.title = (i * 5) + "%: " + n + (n === 1 ? " answer" : " answers");
      col.appendChild(bar);
      chart.appendChild(col);
    });
    var med = el("div", "poll-median");
    med.style.left = "calc(" + (data.median / 100) + " * (100% - 100% / 21) + 100% / 42)";
    med.title = "Median " + pct(data.median);
    chart.appendChild(med);
    res.appendChild(chart);
    var axis = el("div", "poll-axis");
    ["0%", "25%", "50%", "75%", "100%"].forEach(function (t) { axis.appendChild(el("span", null, t)); });
    res.appendChild(axis);
    var stats = el("p", "poll-stats");
    stats.innerHTML = "<strong>" + data.count + "</strong> " + (data.count === 1 ? "answer" : "answers") +
      " &middot; median <strong>" + pct(data.median) + "</strong> &middot; average <strong>" + pct(data.mean) + "</strong>" +
      (data.mine != null ? " &middot; your call <strong>" + data.mine + "%</strong>" : "");
    res.appendChild(stats);
  }

  function build(box) {
    var q = box.getAttribute("data-q");
    box.innerHTML = "";
    box.appendChild(el("p", "poll-title", "What's your call? Chance this resolves Yes"));
    var form = el("div", "poll-form");
    var readout = el("output", "poll-readout", "50%");
    var slider = el("input", "poll-slider");
    slider.type = "range"; slider.min = 0; slider.max = 100; slider.step = 5; slider.value = 50;
    slider.setAttribute("aria-label", "Your probability, in steps of 5%");
    slider.addEventListener("input", function () { readout.textContent = slider.value + "%"; });
    var btn = el("button", "poll-button", "Lock in my call");
    btn.type = "button";
    form.appendChild(readout); form.appendChild(slider); form.appendChild(btn);
    box.appendChild(form);
    var note = el("p", "poll-note", "Loading…");
    box.appendChild(note);

    function show(data) {
      if (data.voted || data.closed) {
        form.style.display = "none";
        note.textContent = data.closed
          ? "Voting closed on " + closeLabel(q) + "."
          : "Your call is locked in. Here's how everyone has answered so far.";
        renderResults(box, data);
      } else {
        note.textContent = (data.count ? data.count + (data.count === 1 ? " person has" : " people have") + " answered. " : "") +
          "Results appear after you lock in your call. Voting closes " + closeLabel(q) + ".";
      }
    }

    btn.addEventListener("click", function () {
      btn.disabled = true; btn.textContent = "Saving…";
      fetch(API + "/vote", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: q, voter: VOTER, prob: +slider.value })
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (data.error && !("count" in data)) throw new Error(data.error);
        if (data.error) note.textContent = data.error;
        show(data);
      }).catch(function () {
        btn.disabled = false; btn.textContent = "Lock in my call";
        note.textContent = "Couldn't save your call just now. Please try again.";
      });
    });

    fetch(API + "/results?q=" + encodeURIComponent(q) + "&voter=" + encodeURIComponent(VOTER))
      .then(function (r) { return r.json(); }).then(show)
      .catch(function () { note.textContent = "The poll is unavailable right now."; });
  }

  Array.prototype.forEach.call(polls, build);
})();
