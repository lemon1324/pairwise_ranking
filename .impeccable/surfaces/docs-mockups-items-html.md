---
version: 1
slug: "docs-mockups-items-html"
primary_target: "docs/mockups/items.html"
related_targets: ["docs/mockups/rankings.html"]
---

# Items (web) surface brief

Scope: the Items sheet of the planned web app, desktop and phone. Static mid-fi mockup
(`docs/mockups/items.html`), extending the established Drawing Set world in DESIGN.md. Visitor mode:
Operate. Sibling of Rankings (`docs/mockups/rankings.html`), which shares the parts-list table system.

Audience and job: the owner, keeping the item list in step with the physical setup; several edits in a
row, keyboard-first on desktop, touch on phone.

Direction (confirmed, extends the world; no new direction roll): an assembly BOM sheet. Table anchored
top-left with a header row; slot balloons as find numbers; closed title block bottom-right. The selected
row grows a ruled callout strip directly beneath it carrying its actions with key hints; Edit, New,
Replace and Reactivate open as forms inside that strip, Delete confirms inside it. No modals, no toolbar.

Overflow (confirmed): desktop sheet is fixed at viewport height; rows fold into as many columns as fit at
>= 36rem each, header repeated per column; when full, continuation sheets SHEET n OF N (PgUp/PgDn).
Phone: one scrolling table, title block at the end. Without JS: long sheet.

Columns: Slot (balloon; dashed empty balloon plus "no slot" for missing), Name with description as a
smaller second line, Category, Status. Retired rows in ink 3 with a "retired" tag.

Title block: TITLE, FILE, Slots ("40 of 42 used · free: 9, 31" / "none free" / no slot list), item
counts, last change, Add Item N, Show Retired H, name filter /, sheet number, keys.

Keys (confirmed): ↑↓ or J K select, Home/End, PgUp/PgDn sheet, ↵ edit, N new, R retire, P replace,
A reactivate, Del delete (confirm), H show retired, / filter, Esc clear. Focus: new item selected after
save; after Retire or Delete selection moves to next row; closing a form returns focus to its row.

Behaviour that stays: Retire keeps votes and frees the slot; Replace retires and prefills slot and
category; Delete removes the item and its votes; slots unique among active items; Reactivate assigns a
slot.

States: normal, selected, editing, slot conflict, confirm delete, retired shown, no items, no slot list,
slots full, overflow onto a second sheet (64 sample items).

Anti-goals: card grid, toolbar row, modal dialogs, colour-only signals.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
