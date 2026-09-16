---
version: 1
slug: "docs-mockups-compare-html"
primary_target: "docs/mockups/compare.html"
related_targets: []
---

# Compare (web) surface brief

Scope: the Compare screen of the planned FastAPI + Jinja2 + HTMX web app, desktop and phone. Static
mid-fi mockup first (`docs/mockups/compare.html`); it sets the visual world the Items, Rankings and
Settings mockups inherit. Visitor mode: Operate.

Audience and job: the owner, at a desk or on a phone beside the physical items, in short bursts.
Answer the next pair in one key or tap, catch a mis-tap from the receipt, see a short session move
the confidence reading.

Behaviour that stays: Equal records nothing and advances; weights 3/2/1; keys 1-7, S, Ctrl+Z; undo
re-offers the undone pair.

States: normal pair (name leads, description and identifier secondary); blinded (identifier only in
views and receipt, no settled or tolerance readings, nothing but slots); not enough items (ghosted
views, reason, link to Items); just voted; nothing to undo; undone; save failed; file changed on disk.

Confidence reading (confirmed): share of adjacent active-rank neighbours whose order is at least 80%
likely from log-strength gap and both SEs, plus median SE as ± tolerance. Must be a separate,
swappable core function.

Accessibility: deuteranopia-safe palette, colour never the sole signal (PRODUCT.md).

## Direction contract

THESIS: Each comparison is a sheet from a component datasheet: View A and View B, a dimensioned
seven-station scale, and the ranking's uncertainty stated as tolerance in the title block. Refuses the
category default of two bordered cards, "VS", and a row of rounded buttons.

OWN-WORLD: Drafting paper ground, ink lines in a strict weight scale (frame heavy, cells medium,
construction lines hairline), zone ticks on the frame, a ruled title block. Item balloons (circled
identifiers) mark slots. A side solid fill, B side hatched fill. One blue markup colour reserved for
the live station and focus; orange only for warnings, always with an icon and words. Condensed
drafting sans for labels, a workhorse sans for names, tabular mono for every number. No button chrome,
no rounded cards, no shadows: controls are ruled cells.

STORY: The visitor reads two names, presses the station that matches their judgement, sees the new
revision row confirm what was recorded, and watches settled and tolerance figures step. They trust
it because the uncertainty is on the sheet, and undo is one cell away.

FIRST VIEWPORT: A drawing frame fills the viewport under a one-line sheet header (project, file,
sheet tabs). Top two thirds: VIEW A left, VIEW B right, names at display scale. Below: a full-width
dimension line with seven numbered station cells, strength stepping outward, Equal centred; this is
the primary action. Bottom-right title block: settled, tolerance, votes, last revision with Undo,
Skip, blinded mode. Phone: views stacked, stations in two columns with Equal spanning, title block
collapsed to one ruled line above the bottom sheet tabs.

FORM: Engineering Datasheet, position 3 of the grounded list, seed key a009a751 (re-roll 1).
Signature interaction: a vote is a drawing revision; the station marks, a revision row slides into
the title block, figures step. Motion grammar: one short discrete tick per vote, none under reduced
motion.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Open decisions

- Fonts are chosen at build and self-hosted in the real app (the mockup may load them from Google
  Fonts).
