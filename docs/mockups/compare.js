// Compare mockup behaviour: sample pairs, keyboard votes, undo, and the state picker.
// Mockup only; the real app renders pairs server-side and posts votes with HTMX.

(() => {
  const ITEMS = {
    oilking: { name: "Gateron Oil King", slot: "12", cat: "Linear", desc: "Deep, muted bottom-out. Smooth all the way down, slight spring ping on release." },
    mxblack: { name: "Cherry MX Black Clear-Top (Hyperglide)", slot: "7", cat: "Linear", desc: "Heavier spring, sharper top-out. Scratchier than expected for this batch." },
    cream: { name: "NovelKeys Cream", slot: "3", cat: "Linear", desc: "Scratchy until broken in; hollow, clacky POM sound." },
    t1: { name: "Durock T1", slot: "B-14", cat: "Tactile", desc: "Sharp bump right at the top, short travel after it." },
    jade: { name: "Kailh Box Jade", slot: "21", cat: "Clicky", desc: "Loud, crisp click bar. Heavy for long sessions." },
    lavender: { name: "Akko Lavender Purple", slot: "9", cat: "Tactile", desc: "" },
    boba: { name: "Gazzew Boba U4T", slot: "15", cat: "Tactile", desc: "Round, full-travel bump with a thick, quiet bottom-out." },
    alpaca: { name: "Alpaca V2", slot: "4", cat: "Linear", desc: "Light, smooth, a bit of stem wobble." },
  };

  const PAIRS = [
    ["oilking", "mxblack"],
    ["cream", "alpaca"],
    ["t1", "boba"],
    ["jade", "lavender"],
    ["oilking", "alpaca"],
    ["boba", "lavender"],
    ["mxblack", "cream"],
  ];

  const STRENGTH = { 3: "Much better", 2: "Better", 1: "Slightly better" };

  const $ = (id) => document.getElementById(id);
  const sheet = $("sheet");
  const frame = $("frame");
  const stations = [...document.querySelectorAll(".station")];

  const initial = () => ({
    pairIndex: 0,
    votes: 203,
    session: 14,
    pairsCompared: 118,
    settled: 31,
    tolerance: 38,
    log: [
      { rev: 202, winner: "jade", loser: "cream", weight: 1, time: "21:03", undone: false, snap: null },
      { rev: 203, winner: "boba", loser: "t1", weight: 2, time: "21:04", undone: false, snap: null },
    ],
  });

  let s = initial();
  let mode = "normal";

  const blinded = () => mode === "blinded";
  const label = (key) => (blinded() ? ITEMS[key].slot : ITEMS[key].name);
  const now = () => new Date().toTimeString().slice(0, 5);

  function setText(id, text) {
    const el = $(id);
    if (el.textContent === text) return;
    el.textContent = text;
    el.classList.remove("is-stepping");
    void el.offsetWidth;
    el.classList.add("is-stepping");
  }

  function renderPair(animate) {
    const [a, b] = PAIRS[s.pairIndex % PAIRS.length];
    const apply = () => {
      for (const [side, key] of [["a", a], ["b", b]]) {
        const it = ITEMS[key];
        $("name-" + side).textContent = blinded() ? "Slot " + it.slot : it.name;
        $("desc-" + side).textContent = it.desc;
        $("slot-" + side).textContent = it.slot;
        $("blind-" + side).textContent = it.slot;
        $("cat-" + side).textContent = it.cat;
      }
    };
    const bodies = document.querySelectorAll(".view-body");
    if (!animate || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      apply();
      return;
    }
    bodies.forEach((el) => el.classList.add("is-leaving"));
    setTimeout(() => {
      apply();
      bodies.forEach((el) => el.classList.remove("is-leaving"));
    }, 140);
  }

  function renderFigures() {
    setText("votes", String(s.votes));
    $("session").innerHTML = `${s.session} this<br>session`;
    setText("settled", s.votes ? `${s.settled}/41` : "—");
    setText("tolerance", s.votes ? `±${s.tolerance}` : "—");
    setText("pairs", `${s.pairsCompared} of 861`);
  }

  function renderLog(newRev) {
    const rows = $("rev-rows");
    rows.innerHTML = "";
    const shown = s.log.slice(-2);
    if (!shown.length) {
      const li = document.createElement("li");
      li.className = "rev-empty";
      li.textContent = "No votes yet. The first vote you record appears here.";
      rows.append(li);
    }
    shown.forEach((entry, i) => {
      const li = document.createElement("li");
      li.className = "rev-row";
      if (i < shown.length - 1) li.classList.add("is-previous");
      if (entry.undone) li.classList.add("is-undone");
      if (entry.rev === newRev) li.classList.add("is-new");
      const text = blinded()
        ? `Slot ${label(entry.winner)} over slot ${label(entry.loser)}`
        : `${label(entry.winner)} over ${label(entry.loser)}`;
      li.innerHTML =
        `<span class="rev-no">R${entry.rev}</span>` +
        `<span><span class="rev-text">${text} <span class="rev-strength">· ${STRENGTH[entry.weight]}</span></span>` +
        (entry.undone ? `<span class="rev-tag">Undone · pair re-offered</span>` : "") +
        `</span><span class="rev-time">${entry.time}</span>`;
      rows.append(li);
    });
    $("undo").disabled = !s.log.some((e) => !e.undone) || mode === "empty";
  }

  function mark(station) {
    stations.forEach((el) => el.classList.remove("is-marked"));
    station.classList.add("is-marked");
    setTimeout(() => station.classList.remove("is-marked"), 420);
  }

  function vote(station) {
    if (station.disabled) return;
    mark(station);
    if (mode === "save-failed") return;
    const side = station.dataset.side;
    if (side === "equal") {
      skip();
      return;
    }
    const [a, b] = PAIRS[s.pairIndex % PAIRS.length];
    const weight = Number(station.dataset.weight);
    s.log = s.log.filter((e) => !e.undone);
    const snap = { pairIndex: s.pairIndex, settled: s.settled, tolerance: s.tolerance, pairsCompared: s.pairsCompared };
    s.votes += 1;
    s.session += 1;
    s.pairsCompared += 1;
    if (s.settled < 41 && s.votes % 2 === 0) s.settled += 1;
    if (s.tolerance > 12) s.tolerance -= 1;
    s.log.push({
      rev: s.votes,
      winner: side === "a" ? a : b,
      loser: side === "a" ? b : a,
      weight,
      time: now(),
      undone: false,
      snap,
    });
    s.pairIndex += 1;
    renderLog(s.votes);
    renderFigures();
    renderPair(true);
  }

  function skip() {
    if (mode === "empty" || mode === "save-failed") return;
    s.pairIndex += 1;
    renderPair(true);
  }

  function undo() {
    if ($("undo").disabled) return;
    const entry = [...s.log].reverse().find((e) => !e.undone);
    if (!entry) return;
    entry.undone = true;
    s.votes -= 1;
    s.session = Math.max(0, s.session - 1);
    if (entry.snap) {
      Object.assign(s, entry.snap);
    } else {
      s.pairsCompared -= 1;
      s.pairIndex = PAIRS.findIndex(([x, y]) => [x, y].includes(entry.winner) && [x, y].includes(entry.loser));
      if (s.pairIndex < 0) {
        PAIRS.push([entry.winner, entry.loser]);
        s.pairIndex = PAIRS.length - 1;
      }
    }
    renderLog();
    renderFigures();
    renderPair(true);
  }

  function setMode(next) {
    mode = next;
    s = initial();
    if (next === "fresh") {
      s.votes = 0;
      s.session = 0;
      s.pairsCompared = 0;
      s.log = [];
    }
    frame.classList.toggle("is-blinded", next === "blinded");
    frame.classList.toggle("is-empty", next === "empty");
    frame.classList.toggle("is-save-failed", next === "save-failed");
    $("notice").hidden = next !== "changed";
    $("sheet-file").classList.toggle("is-warn", next === "save-failed");
    stations.forEach((el) => (el.disabled = next === "empty"));
    $("skip").disabled = next === "empty";
    $("mode-text").textContent = next === "blinded" ? "Blinded" : "Open";
    $("mode-icon").setAttribute("href", next === "blinded" ? "#i-eye-off" : "#i-eye");
    renderLog();
    renderFigures();
    renderPair(false);
  }

  stations.forEach((el) => el.addEventListener("click", () => vote(el)));
  $("skip").addEventListener("click", skip);
  $("undo").addEventListener("click", undo);
  $("retry").addEventListener("click", () => {
    document.querySelector('input[name="state"][value="normal"]').click();
  });
  $("notice-dismiss").addEventListener("click", () => ($("notice").hidden = true));

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      undo();
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (/^[1-7]$/.test(e.key)) {
      e.preventDefault();
      vote(stations[Number(e.key) - 1]);
    } else if (e.key.toLowerCase() === "s") {
      e.preventDefault();
      mark(stations[3]);
      skip();
    }
  });

  document.querySelectorAll('input[name="state"]').forEach((input) =>
    input.addEventListener("change", () => setMode(input.value))
  );
  document.querySelectorAll('input[name="theme"]').forEach((input) =>
    input.addEventListener("change", () => {
      if (input.value === "auto") document.documentElement.removeAttribute("data-theme");
      else document.documentElement.setAttribute("data-theme", input.value);
    })
  );

  // ?state=blinded&theme=dark opens the mockup in a given state (used for review captures).
  const params = new URLSearchParams(location.search);
  const startTheme = params.get("theme");
  if (startTheme) document.querySelector(`input[name="theme"][value="${startTheme}"]`)?.click();
  const startState = params.get("state") || "normal";
  const picker = document.querySelector(`input[name="state"][value="${startState}"]`);
  if (picker) picker.checked = true;
  setMode(picker ? startState : "normal");
})();
