// Sample project for the Items and Rankings mockups: 64 keyswitches, a 60-slot tester board, and
// synthetic ratings, uncertainties and weighted records. Deterministic, so captures are repeatable.
// All descriptions and figures are invented for the mockup.

(() => {
  const NAMES = [
    ["Gateron Oil King", "Linear", "Deep, muted bottom-out. Smooth all the way down, slight spring ping on release."],
    ["Cherry MX Black Clear-Top (Hyperglide)", "Linear", "Heavier spring, sharper top-out. Scratchier than expected for this batch."],
    ["NovelKeys Cream", "Linear", "Scratchy until broken in; hollow, clacky POM sound."],
    ["Durock T1", "Tactile", "Sharp bump right at the top, short travel after it."],
    ["Kailh Box Jade", "Clicky", "Loud, crisp click bar. Heavy for long sessions."],
    ["Akko Lavender Purple", "Tactile", ""],
    ["Gazzew Boba U4T", "Tactile", "Round, full-travel bump with a thick, quiet bottom-out."],
    ["Alpaca V2", "Linear", "Light, smooth, a bit of stem wobble."],
    ["Gateron Ink Black V2", "Linear", "Smoky housing, deeper pitch than the Yellows."],
    ["Gateron Milky Yellow Pro", "Linear", "Budget pick; slightly gritty but consistent."],
    ["Gateron Box CJ", "Linear", "Very smooth once lubed; muted and a touch mushy."],
    ["Gateron North Pole", "Linear", ""],
    ["Cherry MX Brown", "Tactile", "Barely-there bump. Hard to tell from a linear blind."],
    ["Cherry MX Blue", "Clicky", "Classic click, rattly spring."],
    ["Cherry MX2A Silent Red", "Silent", "Quiet dampened bottom-out, slightly spongy."],
    ["NovelKeys Blueberry", "Tactile", "Big tactile event, loud top-out."],
    ["Tangerine V2 (62g)", "Linear", "Long spring, bouncy return."],
    ["Durock POM Linear", "Linear", "Dry, clacky, very consistent between switches."],
    ["Durock Dolphin", "Linear", ""],
    ["Kailh Box Navy", "Clicky", "Heaviest click in the set; fatigue after a few minutes."],
    ["Kailh Box White V2", "Clicky", "Crisp and light; pleasant pitch."],
    ["Kailh Speed Silver", "Linear", "Short travel, early actuation, feels twitchy."],
    ["Kailh Deep Sea Silent Box Pink", "Silent", "Near-silent; soft landing."],
    ["Akko Cream Yellow", "Linear", "Light and smooth for the price."],
    ["Akko Jelly Pink", "Linear", ""],
    ["Akko Rosewood", "Tactile", "Mild rounded bump, quiet."],
    ["Gazzew Boba U4 Silent", "Silent", "Silent tactile; bump feels thicker than U4T."],
    ["Gazzew Boba LT", "Linear", "Thocky long pole, faint scratch."],
    ["Zeal Zealios V2 67g", "Tactile", "Sharp, prominent bump; premium feel."],
    ["Zeal Tealios V2", "Linear", "Buttery smooth, quiet."],
    ["Zeal Healios", "Silent", "Silent linear; slight rubbery bottom."],
    ["Zeal Roselios", "Silent", ""],
    ["Holy Panda X", "Tactile", "Snappy bump, loud-ish bottom-out."],
    ["Invyr Holy Panda", "Tactile", "Rounder bump than the X; scratch on one sample."],
    ["Drop Halo True", "Tactile", "Rounded bump through most of the travel."],
    ["Drop Halo Clear", "Tactile", "Lighter than True; similar shape."],
    ["Everglide Oreo", "Tactile", "Short sharp bump, deep sound."],
    ["Everglide Aqua King", "Linear", "Slippery, high-pitched clack."],
    ["Outemu Silent Lemon", "Silent", "Quiet but inconsistent between samples."],
    ["JWK Black Linear", "Linear", "Heavier, smooth, low pitch."],
    ["JWK Lavender", "Linear", ""],
    ["SP-Star Meteor White", "Linear", "Very light; accidental presses."],
    ["TTC Gold Pink V2", "Linear", "Smooth; slightly sharp bottom-out."],
    ["TTC Bluish White", "Tactile", "Sharp small bump, crisp."],
    ["KTT Strawberry", "Linear", "Budget; scratchy out of the box."],
    ["KTT Kang White", "Linear", "Crisp, clacky, light."],
    ["HMX Cloud", "Linear", "Soft, marbly sound."],
    ["HMX Hyacinth V2", "Linear", "Creamy, deep, a favourite so far."],
    ["Wuque WS Morandi", "Linear", "Light, smooth, a little hollow."],
    ["Wuque WS Heavy Tactile", "Tactile", "Very strong bump; tiring."],
    ["Haimu Heartbeat", "Tactile", "Pronounced rounded bump; long spring."],
    ["Haimu Mint", "Linear", ""],
    ["Mode Signal", "Tactile", "Clean bump, smooth after it."],
    ["Mode Chosen", "Linear", "Smooth and quiet; slight spring noise."],
    ["C³ Tangerine Light Green", "Linear", "Light variant; bouncy."],
    ["SwitchOddity Pineapple", "Linear", "Muted, round sound."],
    ["Raw Studio Yaki Nasu", "Tactile", "Short bump; sounds thin."],
    ["Durock Shrimp Silent", "Silent", "Silent linear, very smooth."],
    ["Kinetic Labs Salmon", "Tactile", "Rounded bump; stem wobble noticeable."],
    ["Kinetic Labs Penguin", "Tactile", "Silent-ish tactile; deeper sound than expected."],
    ["Gateron Melodic", "Linear", "Bright, poppy; polarising."],
    ["Cherry MX Red", "Linear", "Baseline reference; scratchy."],
    ["Durock Sunflower", "Tactile", ""],
    ["Akko V3 Piano Pro", "Tactile", "Soft bump, low pitch."],
  ];

  // Slots 1-60 on the tester board; 9, 31, 44 and 57 are free.
  const SLOTS = Array.from({ length: 60 }, (_, i) => String(i + 1));
  const FREE = new Set(["9", "31", "44", "57"]);
  const RETIRED = new Set([13, 24, 38, 41, 44, 61]); // indexes into NAMES
  const NO_SLOT = new Set([52, 63]); // active but not yet placed on the board

  let seed = 20260916;
  const rand = () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  const freeSlots = SLOTS.filter((s) => !FREE.has(s));
  let nextSlot = 0;
  const items = NAMES.map(([name, cat, desc], i) => {
    const retired = RETIRED.has(i);
    let slot = "";
    if (!retired && !NO_SLOT.has(i)) slot = freeSlots[nextSlot++];
    return { id: `it${i + 1}`, name, cat, desc, slot, status: retired ? "retired" : "active" };
  });
  // Put the two Compare-mockup items in the slots that screen shows.
  const swap = (id, slot) => {
    const holder = items.find((it) => it.slot === slot);
    const item = items.find((it) => it.id === id);
    if (holder && holder !== item) holder.slot = item.slot;
    item.slot = slot;
  };
  swap("it1", "12");
  swap("it2", "7");

  // Synthetic model output: log-strength, SE, comparisons.
  const logStrength = items.map(() => (rand() - 0.5) * 3.2);
  logStrength[0] = 1.45; // Oil King near the top
  logStrength[47] = 1.62; // Hyacinth V2 on top
  const mean = logStrength.reduce((a, b) => a + b, 0) / items.length;
  const sd = Math.sqrt(logStrength.reduce((a, b) => a + (b - mean) ** 2, 0) / items.length);
  items.forEach((it, i) => {
    const comparisons = 4 + Math.floor(rand() * 19);
    const seLog = 0.9 / Math.sqrt(comparisons) + rand() * 0.05;
    it.logStrength = logStrength[i];
    it.strength = Math.exp(logStrength[i]);
    it.rating = Math.round(1500 + (200 * (logStrength[i] - mean)) / sd);
    it.se = Math.round((200 * seLog) / sd);
    it.seLog = seLog;
    it.comparisons = comparisons;
    it.votes = comparisons;
  });

  // Weighted record against opponents, consistent in direction with the rating gap.
  items.forEach((it, i) => {
    const opponents = new Map();
    let left = it.comparisons;
    while (left > 0) {
      const j = Math.floor(rand() * items.length);
      if (j === i) continue;
      const other = items[j];
      const p = 1 / (1 + Math.exp(-(it.logStrength - other.logStrength)));
      const weight = 1 + Math.floor(rand() * 3);
      const rec = opponents.get(other.id) || { id: other.id, won: 0, lost: 0 };
      if (rand() < p) rec.won += weight;
      else rec.lost += weight;
      opponents.set(other.id, rec);
      left -= 1;
    }
    it.record = [...opponents.values()].sort((a, b) => b.won + b.lost - (a.won + a.lost));
  });

  window.SAMPLE = {
    title: "Linear switches, winter shortlist",
    file: "switches-2026.pairrank",
    slots: SLOTS,
    items,
  };
})();
