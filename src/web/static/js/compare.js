// The Compare sheet's keys, and the small motions a vote makes.
//
// Loaded once, outside the frame htmx swaps, and bound to the document: every
// press looks its button up afresh, so nothing here has to be re-wired when a
// vote lands a new frame. The keys only ever *click* a button the page drew -
// a station, Skip, Undo - so what a key does is exactly what the button does,
// with JavaScript and htmx or without them.
//
//   1-7     press that station (Equal, 4, records nothing and moves on)
//   S       mark Equal and press Skip, as the mockup does
//   Ctrl+Z  press Undo
//
// The motions are the mockup's (docs/mockups/compare.js): the station pressed
// takes the markup colour for 420 ms, the views fade out and back in around a
// new pair, and a figure that changed steps into place. None of them under
// reduced motion but the mark, which is a colour rather than a movement.

(() => {
  "use strict";

  const MARK_MS = 420;
  const LEAVE_MS = 140;

  // The station last pressed and when its mark ends; re-applied to the
  // station of the same number in a frame swapped in before it has.
  let mark = null;
  // The figures as they read before a swap, by id.
  let figures = {};

  const motion = () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const station = (key) => document.getElementById("station-" + key);

  function press(button) {
    if (!button || button.disabled) return false;
    button.click();
    return true;
  }

  function applyMark() {
    document.querySelectorAll(".station.is-marked").forEach((el) => el.classList.remove("is-marked"));
    if (!mark) return;
    const left = mark.until - Date.now();
    const el = station(mark.key);
    if (left <= 0 || !el) {
      mark = null;
      return;
    }
    el.classList.add("is-marked");
    const current = mark;
    // Clears whichever station carries the mark when it ends, not `el`: a
    // swap in the meantime re-marks the new frame's station, and the timer
    // set before the swap is the one that ends the mark on time.
    setTimeout(() => {
      if (mark !== current) return;
      mark = null;
      document.querySelectorAll(".station.is-marked").forEach((station) => station.classList.remove("is-marked"));
    }, left);
  }

  function markStation(key) {
    mark = { key: String(key), until: Date.now() + MARK_MS };
    applyMark();
  }

  // A click on a station, by mouse or by its key, marks it. Dismiss on the
  // changed-on-disk notice only hides the strip: its link, which reloads the
  // pair, is for a page without JavaScript.
  document.addEventListener("click", (event) => {
    if (!event.target.closest) return;
    const dismiss = event.target.closest("#notice-dismiss");
    if (dismiss) {
      event.preventDefault();
      document.getElementById("notice").hidden = true;
      return;
    }
    const button = event.target.closest(".station");
    if (button && !button.disabled) markStation(button.dataset.key);
  });

  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    if (event.target.closest && event.target.closest("input, textarea, select")) return;
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && !event.altKey && key.toLowerCase() === "z") {
      event.preventDefault();
      if (!event.repeat) press(document.getElementById("undo"));
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (/^[1-7]$/.test(key)) {
      event.preventDefault();
      // A held key would vote again on every pair it lands on.
      if (!event.repeat) press(station(key));
    } else if (key === "s" || key === "S") {
      event.preventDefault();
      const skip = document.getElementById("skip");
      if (event.repeat || !skip || skip.disabled) return;
      markStation(4);
      skip.click();
    }
  });

  // One request for the frame at a time, from the press until the new frame
  // is in. hx-sync="#frame:drop" is not enough on its own: htmx lets go of the
  // request when the answer arrives, before the delayed swap below has put
  // the new pair in, so for LEAVE_MS the old frame's stations would post a
  // second vote on the old pair. A request made while busy is refused.
  let busy = false;

  document.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.target?.id !== "frame") return;
    if (busy) {
      event.preventDefault();
      return;
    }
    busy = true;
  });

  // A request that failed never lands a frame, so nothing else would clear
  // the flag. Nor would it say anything: htmx swaps no 4xx or 5xx answer. So
  // an error answer is shown as a page of its own - the file gone, damaged, or
  // from a newer version - by loading the address again (the registry has
  // dropped the project, so it draws the error) or, for Skip's GET, the address
  // that failed. A server that cannot be reached is said in the notice strip.
  document.addEventListener("htmx:afterRequest", (event) => {
    if (event.detail.target?.id === "frame" && !event.detail.successful) busy = false;
  });

  document.addEventListener("htmx:responseError", (event) => {
    if (event.detail.target?.id !== "frame") return;
    const detail = event.detail;
    const failed = detail.requestConfig?.verb === "get" && detail.xhr?.responseURL;
    window.location.assign(failed || window.location.href);
  });

  document.addEventListener("htmx:sendError", (event) => {
    if (event.detail.target?.id !== "frame") return;
    const lead = "Could not reach the server.";
    const text = "The page has not changed; press again to retry.";
    const notice = document.getElementById("notice");
    if (notice) {
      const p = document.createElement("p");
      const strong = document.createElement("strong");
      strong.textContent = lead;
      p.append(strong, " " + text);
      const dismiss = document.createElement("a");
      dismiss.className = "cell-button";
      dismiss.id = "notice-dismiss";
      dismiss.href = window.location.href;
      dismiss.textContent = "Dismiss";
      notice.replaceChildren(p, dismiss);
      notice.hidden = false;
    }
    const status = document.getElementById("callout-status");
    if (status) status.textContent = lead + " " + text;
  });

  // Before a new frame goes in: remember the figures, and let the views go.
  document.addEventListener("htmx:beforeSwap", (event) => {
    if (!event.detail.shouldSwap) return;
    figures = {};
    document.querySelectorAll("#frame .tb-figure .num[id]").forEach((el) => {
      figures[el.id] = el.textContent;
    });
    if (!motion()) return;
    document.querySelectorAll("#frame .view-body").forEach((el) => el.classList.add("is-leaving"));
    event.detail.swapOverride = "outerHTML swap:" + LEAVE_MS + "ms";
  });

  // A new frame is in: bring the views back, step what changed, keep the mark.
  document.addEventListener("htmx:load", (event) => {
    if (event.target.id !== "frame") return;
    busy = false;
    applyMark();
    if (motion()) {
      const bodies = event.target.querySelectorAll(".view-body");
      bodies.forEach((el) => el.classList.add("is-leaving"));
      void event.target.offsetWidth;
      bodies.forEach((el) => el.classList.remove("is-leaving"));
      event.target.querySelectorAll(".tb-figure .num[id]").forEach((el) => {
        if (el.id in figures && figures[el.id] !== el.textContent) el.classList.add("is-stepping");
      });
    }
    figures = {};
    // The receipt's live region went out with the old frame, and a region
    // that arrives already filled is not read out; so the row the vote or
    // undo just wrote is said in the page's own status region instead, after
    // the changed-on-disk notice when one came with it (it is swapped in whole
    // too). A failed save is an alert, which is announced as it arrives.
    const status = document.getElementById("callout-status");
    const said = [];
    const notice = document.getElementById("notice");
    if (notice && !notice.hidden) said.push(notice.querySelector("p")?.textContent || "");
    const row = event.target.querySelector(".rev-row.is-new, .rev-row.is-undone, #rev-refused");
    if (row && !event.target.querySelector(".save-warning")) said.push(row.textContent);
    if (status) status.textContent = said.join(" ").replace(/\s+/g, " ").trim();
  });
})();
