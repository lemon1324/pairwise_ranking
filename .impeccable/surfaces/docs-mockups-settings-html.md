---
version: 1
slug: "docs-mockups-settings-html"
primary_target: "docs/mockups/settings.html"
related_targets: []
---

# Settings (web) surface brief

Scope: Settings sheet of the planned web app, desktop and phone. Static mid-fi mockup
(`docs/mockups/settings.html`) in the Drawing Set world (DESIGN.md). Visitor mode: Operate.

Job: the owner occasionally tunes pair selection and edits the slot list. Rare, deliberate edits;
must show what changed from the saved values and from defaults before saving.

Direction (extends the world, no new roll): a specification sheet. Left: one ruled parameter table
snapped to the frame, grouped by Pair selection weights, Vote decay, Top-tier focus, Category
comparisons, Comparison mode; columns Parameter (with a one-line explanation), Value (input), Default,
Range/unit. Right: the slot list as a ruled panel (textarea plus parsed balloons and duplicate/blank
warnings). Title block bottom-right with KEYS block, TITLE, FILE, status (unsaved changes / saved),
Save (Ctrl+S), Reset to defaults, SHEET 1 OF 1.

Behaviour that stays: Save applies settings and slots together; Reset to defaults restores algorithm
settings only and leaves slots alone; decay 0 disables decay; cross-category rate 0..1.

Changed-value signal: a revision triangle beside the value plus bold value (never colour alone).
Errors: field error with icon and words; Save disabled with the reason in the status cell.

States: normal, changed (unsaved), invalid value, saved, slots with duplicates.

Owner direction during the build (binding):
- Parameters and slots are two separately ruled tables, anchored top-left and top-right, not
  sharing a centre line or the title block's lines.
- Slot board: in use is a filled balloon, free is an open ring.
- Real app: normalize the saved slot list to one comma-separated line (the desktop app currently
  saves newline-separated), so the Settings view reads well.
- Slots can be names (a keyboard tester has "Apostrophe"). Lists, tables and the slot board show a
  short label of at most 2 characters; full names show in edit forms, Compare views and on hover.
  Mocked syntax for an explicit short label: `Apostrophe = '`; without one, the first two
  characters. Collisions between auto labels are an open decision for the real app.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
