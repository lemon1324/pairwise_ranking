---
name: Pairwise Ranking
description: Every screen is a sheet from an engineering drawing set; controls are ruled cells, uncertainty is stated as tolerance.
colors:
  paper: "#f5f4ef"
  paper-2: "#ebe9e2"
  paper-3: "#e1dfd6"
  ink: "#17181a"
  ink-2: "#414246"
  ink-3: "#66676b"
  line: "#8e8c85"
  hair: "#cbc9c0"
  markup: "#1d5bc2"
  markup-wash: "#dde6f4"
  warn: "#8f4700"
  warn-mark: "#d9822b"
  warn-wash: "#f5e5d1"
  paper-dark: "#131518"
  paper-2-dark: "#1b1e22"
  paper-3-dark: "#23272c"
  ink-dark: "#e8e6df"
  ink-2-dark: "#c0beb7"
  ink-3-dark: "#97958f"
  line-dark: "#6a6e75"
  hair-dark: "#353a41"
  markup-dark: "#86aef0"
  markup-wash-dark: "#1d2a40"
  warn-dark: "#f2ab62"
  warn-wash-dark: "#36271a"
typography:
  display:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "clamp(1.625rem, 1rem + 1.6vw, 2.625rem)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.005em"
  lead:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
  title-compact:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.005em"
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  body-secondary:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
  body-compact:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.3
  label:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.08em"
  label-small:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.06em"
  tab:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    letterSpacing: "0.06em"
  figure:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "1.5rem"
    fontWeight: 500
    lineHeight: 1.1
    fontFeature: "\"tnum\" 1"
  number:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "0.8125rem"
    fontWeight: 400
    fontFeature: "\"tnum\" 1"
rounded:
  none: "0"
  balloon: "999px"
spacing:
  s-1: "0.25rem"
  s-2: "0.5rem"
  s-3: "0.75rem"
  s-4: "1rem"
  s-5: "1.5rem"
  s-6: "2rem"
  s-7: "3rem"
  frame-weight: "2px"
  cell-weight: "1px"
  zone-band: "1.375rem"
  bom-column-min: "36rem"
  keys-block: "8.25rem"
components:
  cell-button:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.none}"
    padding: "0 0.75rem"
    height: "2.25rem"
  cell-button-hover:
    backgroundColor: "{colors.paper-3}"
  cell-button-disabled:
    textColor: "{colors.ink-3}"
  sheet-tab:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    typography: "{typography.tab}"
    padding: "0 1.5rem"
  sheet-tab-current:
    backgroundColor: "{colors.paper-2}"
    textColor: "{colors.ink}"
  station:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.75rem 0.5rem"
    height: "7.5rem"
  station-hover:
    backgroundColor: "{colors.paper-2}"
  station-active:
    backgroundColor: "{colors.paper-3}"
  station-marked:
    backgroundColor: "{colors.markup-wash}"
    textColor: "{colors.markup}"
  title-block-cell:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "0.5rem 0.75rem 0.75rem"
  title-block-cell-compact:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "0.375rem 0.75rem 0.5rem"
  keys-block:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-2}"
    typography: "{typography.number}"
    width: "8.25rem"
  key-legend:
    textColor: "{colors.ink}"
    typography: "{typography.number}"
    rounded: "{rounded.none}"
    padding: "0 0.3rem"
    height: "1.5rem"
  key-legend-small:
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "1.25rem"
  balloon:
    textColor: "{colors.ink}"
    typography: "{typography.number}"
    rounded: "{rounded.balloon}"
    height: "2rem"
  balloon-list:
    textColor: "{colors.ink}"
    rounded: "{rounded.balloon}"
    height: "1.75rem"
  balloon-empty:
    textColor: "{colors.ink-3}"
    rounded: "{rounded.balloon}"
    height: "1.75rem"
  bom-header-cell:
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    padding: "0.5rem 0.75rem"
  bom-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    padding: "0.375rem 0.75rem"
  bom-row-hover:
    backgroundColor: "{colors.paper-2}"
  bom-row-selected:
    backgroundColor: "{colors.markup-wash}"
    textColor: "{colors.ink}"
  bom-row-retired:
    textColor: "{colors.ink-3}"
  tag:
    textColor: "{colors.ink-2}"
    typography: "{typography.label-small}"
    rounded: "{rounded.none}"
    padding: "0.0625rem 0.3rem"
  row-callout:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
  callout-action:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "0.25rem 0.75rem"
    height: "2.5rem"
  callout-action-hover:
    backgroundColor: "{colors.paper-2}"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0.3rem 0.5rem"
    height: "2.25rem"
  warning:
    backgroundColor: "{colors.warn-wash}"
    textColor: "{colors.ink}"
    padding: "0.5rem 0.75rem"
  notice:
    backgroundColor: "{colors.paper-2}"
    textColor: "{colors.ink}"
    padding: "0.5rem 1.5rem"
---

# Design System: Pairwise Ranking

## Overview

**Creative North Star: "The Drawing Set"**

Every screen of the web app is one sheet from a single engineering drawing set. The ground is drafting paper, structure is drawn in ink at a strict line-weight scale, and a sheet is read the way a drawing is read: a frame with zone markings, the drawing area, and a closed ruled title block in the lower-right. Compare is a view sheet (two views, a dimensioned seven-station scale and notes in the lower-left). Items and Rankings are parts-list (BOM) sheets: a ruled table snapped to the frame, folding into columns and continuation sheets, with a keys block inside the title block. Settings and the project picker are sheets too. A new surface should look like another sheet of the same set, not like a new app.

The world is dense but calm. Space, alignment and line weight carry the hierarchy. There are no cards, no shadows, no button chrome and no rounded corners except the item balloon, which is round because drawings circle their part identifiers, and the leader dot that ties a callout to its row. Drafting notation is what gives the sheets their character: zones per ASME Y14.1, balloons and find numbers, dimension lines with arrowheads, underlined view titles, revision rows, parts lists, sheet n of N, and tolerance given as ±. None of it is decoration. Each piece has the job it has on a real drawing.

Colour is almost absent. Ink on paper does the work. One markup blue marks the live thing (the station just pressed, the selected row, keyboard focus), and one warning orange appears only with an icon and words. The primary user has deuteranopia, so colour never carries meaning alone: side A is a solid fill and side B is hatched, strength is shown by bar count, and every state has a label or a shape.

**Key Characteristics:**
- A drafting-paper ground with ink linework in three weights: frame 2px, cell 1px, construction hairline.
- The sheet anatomy is fixed: a zoned frame, the drawing area, and the title block closing the lower-right corner.
- Controls are ruled cells. Nothing is raised, rounded or filled with chrome.
- Three families, each with one job: a condensed caps label face, a workhorse sans for names and prose, and tabular mono for every number.
- Solid means A and hatched means B, so sides and states never depend on colour.
- Lists are parts lists: ruled tables that fold into columns and sheets rather than scroll, with the selected row's work in a popover callout tied to its row by a leader.
- Motion is one short, discrete tick per action, and none under reduced motion.

## Colors

The palette is warm paper and near-black ink, with one blue for markup and one orange for problems. Both themes are first-class. Dark mode is ink-on-blueprint-dark, not an inversion afterthought, and each light token has a `-dark` twin with the same role.

### Primary
- **Markup Blue** (`markup`; dark `markup-dark`): the checker's pencil. It is used only for the station just pressed (its border, key and bars), the `:focus-visible` outline (2px, 2px offset; -4px inset inside cells, -2px on table rows, -1px plus a markup border on inputs), text selection and native accent controls. **Markup Wash** (`markup-wash`) fills the marked station and the selected parts-list row.

### Secondary
- **Warning Orange**: a set of three. **Warn** (`warn`) is for warning text, the icon and the button border. **Warn Mark** (`warn-mark`) is the warning box rule and the doubled border of a field in error. **Warn Wash** (`warn-wash`) fills the warning box and the delete confirmation. It is used for save failures, file-name problems, invalid field values and destructive confirmation, and never for anything positive or neutral.

### Neutral
- **Drafting Paper** (`paper`): the sheet ground, title-block cells, callouts and inputs.
- **Paper 2** (`paper-2`): hover on cells, tabs and table rows, the current tab, the notice strip and a primary cell button.
- **Paper 3** (`paper-3`): the pressed (`:active`) state and cell-button hover.
- **Ink** (`ink`): text, frame and cell rules, table header rules, the callout rule and leader dot, the A fill and B hatch, and the title-block grid, which shows through its 1px gaps.
- **Ink 2** (`ink-2`): descriptions, notes, table headers, categories, status and secondary prose.
- **Ink 3** (`ink-3`): labels, units, zone letters and numbers, timestamps, previous revisions, retired rows, hints, and disabled text.
- **Line** (`line`): construction marks such as zone ticks, station ticks, dashed ghost outlines and empty balloons, tag rules and input borders.
- **Hair** (`hair`): the lightest rules (between table rows and cells, between revision rows, the footer) and disabled borders and bars.

### Named Rules
**The One Pencil Rule.** Markup blue marks only what is live right now: the pressed station, the selected row, focus and text selection. It is never used for decoration, brand, headings or a resting state.

**The Never Alone Rule.** Every colour signal has a non-colour twin. Warnings carry an icon and words. Sides carry solid versus hatched fills and left versus right position. Strength carries bar count. A selected row also bolds its name, and a retired row also carries a RETIRED tag. Red against green never carries meaning.

## Typography

**Display Font:** Barlow (with system-ui)
**Body Font:** Barlow (with system-ui)
**Label/Mono Font:** Barlow Condensed for labels (with Barlow, system-ui); JetBrains Mono for numbers (with ui-monospace)

**Character:** This is a drafting-office type set. The condensed caps read like lettering on a title block, Barlow reads plainly at any size, and mono keeps every figure aligned like a table of dimensions. The mockup loads fonts from Google Fonts, but the real app must self-host them because it runs on a LAN.

### Hierarchy
- **Display** (600, clamp(1.625rem, 1rem + 1.6vw, 2.625rem), 1.08, -0.015em, balanced wrap): item names in a view, the largest words on a sheet. 1.5rem on phones.
- **Title** (600, 1.1875rem, 1.2): the project name in a view sheet's TITLE cell. The phone top bar sets the project name at 1rem.
- **Lead** (600, 1.125rem): the lead sentence of an empty state, on Compare's empty scale and on an empty parts list.
- **Title compact** (600, 1.0625rem, 1.2): the project name in a parts-list sheet's TITLE cell, one step down because those title blocks carry more cells. Compare uses the same size for item descriptions (400, ink 2, max 42ch) and for phone title-block figures.
- **Body** (400, 1rem, 1.45, tabular figures on): default text. Station names and the sheet number use 1rem.
- **Body secondary** (400, 0.9375rem): notes (max 60ch), revision rows, warning and confirmation copy, category values, inputs, callout actions and titles. Parts-list item names use this size at 500 (600 when selected).
- **Body compact** (400, 0.875rem, 1.3): the parts-list data size. Categories and status in table rows, title-block text cells (slots, counts, last change, summary), and the description in the Rankings detail. Mono figures in table cells and the detail list use it too.
- **Label** (Barlow Condensed 600, 0.75rem, 0.08em, uppercase): the caption for every cell, view title, note heading and table header (ink 3 on cells, ink 2 on table headers). Tabs and cell buttons use the same face at 0.875–0.9375rem with 0.06em tracking.
- **Label small** (Barlow Condensed 500–600, 0.6875rem, 0.06em, uppercase): tags (RETIRED, NO SLOT, NEW), the headers of the weighted-record sub-table, and zone labels (500, no tracking). The same size sets the mono glyph inside every small 1.25rem key legend: title-block and keys-block legends, legends inside cell buttons, and phone station keys.
- **Figure** (JetBrains Mono 500, 1.5rem, 1.1): title-block readings (settled, tolerance, votes), each followed by a two-line unit in 0.8125rem ink 3.
- **Number** (JetBrains Mono 400–500, 0.75–0.9375rem): keys, balloons, weights, revision numbers and times, list markers, the file name, and the Rankings rank (500, 0.9375rem). Parts-list descriptions and hints sit at the same 0.8125rem in Barlow.

### Named Rules
**The Every Number In Mono Rule.** Any figure the user might compare or scan (a count, rating, rank, weight, slot, time, key or file name) is set in JetBrains Mono with tabular numerals. Words stay in Barlow.

**The Caption Not Kicker Rule.** Condensed caps labels name the cell, column or view they sit in, the way lettering names a field on a title block. They never float above a heading as a decorative eyebrow.

## Layout

**Sheet shell.** A top bar with a 2px ink bottom rule, 3.25rem tall (2.75rem on phones), holds the sheet tabs and a Project menu. An optional notice strip sits below it. Below that is the drawing frame, which fills the rest of the viewport.

**Frame and zones.** The outer frame is a 2px ink border with a 1.375rem zone band inside it, then a 1px inner border. Zone markings follow ASME Y14.1. Numbers run right to left along the top and bottom borders, and letters run bottom to top on both sides, so zone A1 is the lower-right corner. Labels are Barlow Condensed 500 at 0.6875rem in ink 3. Boundary ticks are 1px × 0.5rem in `line`, drawn inward from the outer frame line. The zone count follows the frame's width through container queries, about one zone per 240px and always even: 4 zones below 60rem, 6 from 60rem, and 8 from 90rem, which is the cap. The lists run 8..1, so narrower sheets hide the high numbers at the left end first. Letters stay A–D. Phones (≤40rem) drop the outer frame and zones and give the inner frame the 2px weight.

**View sheets (Compare).** The inner frame is a grid. The drawing area spans the full width. Below it, notes and the title block share the bottom row: notes take `1fr` and the title block takes `minmax(34rem, 46rem)`. Both are bottom-aligned, so notes sit in the lower-left corner and the title block closes the lower-right corner, flush against the frame's right and bottom edges. At 64rem and below, the title block goes full width and notes are hidden.

**Parts-list sheets (Items, Rankings).** On desktop the sheet is exactly the viewport and never scrolls. The table fills the inner frame and snaps to its lines: it drops its own top rule, the first column drops its left rule, and a full rightmost column drops its right rule. Rows fold into as many columns as fit at 36rem or wider each, then onto continuation sheets. Every column repeats the header row. Adjacent columns overlap by 1px so they share one continuous vertical rule. The title block is pinned to the lower-right corner at exactly the rightmost column's width, and that column stops 0.75rem above it. Parts-list sheets carry no notes; their keys live in the title block. On phones (and without JavaScript) the sheet is one long scrolling table with the title block full width after it.

**No dividing rules in a view.** On view sheets, views, the vote scale and notes are separated by space and alignment, not by lines, and the title block is the only closed ruled region in the drawing area. Content inside a view is centred on the view's axis. There is no centre line between views. A parts list is itself a ruled table, so this rule does not apply inside it.

**Spacing rhythm.** The spacing scale runs 0.25 / 0.5 / 0.75 / 1 / 1.5 / 2 / 3rem (`s-1`–`s-7`). Views pad `s-4 s-6 s-5`, title-block cells pad `s-2 s-3 s-3` (0.375rem `s-3` `s-2` on parts-list sheets), table cells pad 0.375rem `s-3` (headers `s-2 s-3`), callout bodies pad `s-3`, and the frame sits `s-4 s-5 s-5` from the viewport. Phones tighten to `s-2`–`s-4`.

**Breakpoints.** At 40rem the layout switches to phone: bottom tabs, stacked views, 2-column stations, a compressed title block, and single-table parts lists that hide the category and Compared columns. At 64rem the Compare title block goes full width and notes are hidden. The zone thresholds at 60 and 90rem are measured on the frame container, not the viewport. Parts-list column count is measured on the drawing area (width ÷ 36rem, rounded down).

**Navigation.** Desktop sheet tabs sit in the top bar. On phones they move to a sticky 4-column bottom bar with a 2px top rule, and the project name moves into the top bar, because the title block's TITLE and FILE cells are hidden on phones.

## Elevation & Depth

The system is flat, and depth is conveyed only by line weight. Frame rules are 2px, cell rules 1px, and construction marks are 1px in the lighter `line` or `hair` colours. There are no box-shadows for elevation. The only `box-shadow` values in the build are drawing devices: a 4px inset ink underline on the current tab, a 1px inset outline that closes the edge of a hatched fill, and a 1px inset `warn-mark` line that doubles the border of a field in error. The row callout is the one popover, the one thing drawn over other content, and it is set off by line weight alone: a 2px frame-weight ink rule all round on opaque `paper`, tied to its row by a 1px leader. The empty-scale message on Compare sits on an 88% paper wash over the dimmed stations.

### Named Rules
**The Line Weight Is Depth Rule.** To make something more important, draw its border heavier (1px to 2px) or move it into the title block. Never lift it with a shadow, and never round it into a card.

## Shapes

The form language is rectilinear. Every cell, button, key legend, station, table, callout, input, tag, warning box and tab has square corners (radius 0). The round forms are drafting marks: the **item balloon**, a full circle (999px) around a slot identifier, as on a parts list, and the **leader dot**, a 7px filled ink circle at the selected row's edge where the callout's leader starts, as at the end of a balloon leader. Leaders are 1px ink elbows (one vertical run, one horizontal run), never diagonal. Keep balloons exclusive to slot identifiers so they stay readable as "this is a physical slot"; an item with no slot gets a dashed empty balloon in `line`. Adjacent ruled cells share borders. Stations and folded table columns overlap by -1px, and the title block uses a 1px ink gap over an ink background, so rules never double. The dimension line uses filled triangular arrowheads (9px) and a mono `0` at the centre. Ghost placeholders use a 1px dashed `line` border. Side swatches are 14px squares, solid for A and 45° hatched (1.5px ink every 4px) for B.

## Components

### Buttons (cell buttons)
Ruled and quiet, like a field on a form you can press.
- **Shape:** square (0), 1px ink border, 2.25rem minimum height.
- **Default:** transparent fill, label type (Barlow Condensed 600, 0.875rem, 0.06em, uppercase), optional 1rem stroke icon or a small key legend.
- **Hover / Focus:** hover fills `paper-3`. Focus is the global 2px markup outline.
- **Primary:** the default action in a callout form (Save) rests on `paper-2`.
- **Destructive:** a `warn` border, used only inside the delete confirmation.
- **Disabled:** ink 3 text, `hair` border, not-allowed cursor.
- **Title-block action cells:** Undo, Skip, Mode, Add, Retired and CSV are whole cells, not bordered buttons. A cell has a caption label, a 600 action line with an icon, and a key legend. Hover fills `paper-2`, press fills `paper-3`, and focus draws the outline inset by -4px.

### Key legend
A keyboard shortcut is drawn as a ruled mono cell (1px currentColor border, 1.5rem, JetBrains Mono 500 at 0.8125rem), never as a raised keycap. Small legends (1.25rem, 0.6875rem) sit inline in notes, cell buttons and title-block cells; callout actions use 1.375rem at 0.75rem. Phones hide title-block key legends.

### Item balloon
A circled mono identifier (2rem, 1px ink). In a parts list it is 1.75rem at 0.8125rem, and an item with no slot shows a dashed `line` balloon with a dash in ink 3. In a blinded view the balloon is the whole content: 5.5rem, 2px border, 2.25rem numerals (4rem on phones).

### Tag
A ruled condensed label (1px `line` border, label small, ink 2): RETIRED, NO SLOT and NEW. It is the non-colour twin of a row state and sits in the Status column on Items and after the name on Rankings.

### Inputs
Square fields with a 1px `line` border on `paper`, 2.25rem tall (2.75rem and 1rem text on phones, 2rem inside title-block cells), 0.9375rem text, mono for numeric fields, ink 3 placeholders. Hover darkens the border to ink 2. Focus draws the markup outline at -1px with a markup border. A field in error doubles its border in `warn-mark` and shows a line below with a `warn` icon, a bold `warn` lead and the reason in ink; hints sit below in 0.8125rem ink 3. Labels are the drafting label above the field.

### Views
Each item is a view in the drawing area, centred on its own axis. Contents run in this order: the name (display), the description (ink 2), then a small definition grid with Category stacked above Slot. In that grid, labels are right-aligned and values left-aligned, meeting at the axis. On phones the grid collapses to one centred line without labels. Under each view is an underlined view title: a swatch (solid A or hatched B) plus a "VIEW A" / "VIEW B" label with a 1px ink rule beneath. Views are separated only by space.

### Station scale (signature)
This is the primary action on Compare: a dimension line ("A preferred", arrowhead, 0, arrowhead, "B preferred") above seven ruled stations sharing borders. Each station stacks, top to bottom: a key legend, strength bars, a name and a mono weight. A 0.75rem tick connects each station to the dimension line. Strength bars ascend low to high on both sides (33/66/100%): solid for A, hatched for B, and a single 1px line for Equal. Hover fills `paper-2` and press fills `paper-3`. **Marked** is the only coloured state: `markup-wash` fill, markup border, bars and key, held for 420ms after a vote. On phones the stations form 2 columns (A keys 1–3 left, B keys 7–5 right, mirrored, Equal spanning the bottom row), and the dimension line and weights are hidden.

### Parts list (signature)
The table on Items and Rankings sheets, drawn as a drawing's parts list.
- **Frame:** 1px ink outer rule (dropped where it lies on the inner frame), a 1px ink rule under the header and between header cells, and `hair` rules between body rows and cells. Fixed table layout; names, descriptions and categories truncate with an ellipsis on one line.
- **Header:** drafting label in ink 2, bottom-aligned, repeated at the top of every folded column.
- **Find number:** the first column, centred. Items shows the slot balloon; Rankings shows the rank as a mono 500 figure (a dash when unranked). Numeric columns are right-aligned mono.
- **Row:** name (500, 0.9375rem) with an optional description line (0.8125rem ink 2), then category and status in body compact.
- **States:** hover fills `paper-2`. Selected fills `markup-wash` and bolds the name to 600. Retired sets the row in ink 3 and adds a RETIRED tag. No slot shows the dashed empty balloon and a NO SLOT tag. The row being added appears as a NEW ghost row with its name in ink 3. Row focus draws the markup outline at -2px.
- **Folding:** rows fill a column to its limit, then the next column, then a continuation sheet; the rightmost column's limit is the top of the title block. Selecting a row never refolds the sheet; moving the selection onto another sheet turns to that sheet.
- **Interaction:** click selects; clicking the selected row again does exactly what Esc does (closes an open form or detail, otherwise clears the selection). Arrows or J/K move, Home/End jump, PgUp/PgDn turn sheets.
- **Empty:** a dashed `line` ghost box (max 36rem) with a lead sentence, a detail line in ink 2, and a cell button when there is somewhere to go.

### Row callout (signature)
The selected row's work, drawn as a popover on the sheet. Its left edge starts 0.375rem right of the find-number column, so every row's number stays visible and clickable, and its right edge sits 0.375rem inside the column's right rule. It sits 0.5rem off the selected row, below it, or above it when there is no room below (the rightmost column's limit is the top of the title block), and it is exactly as tall as its content. It is set off by line weight, not shadow: a 2px frame-weight ink rule all round on opaque `paper`. A leader ties it to the row: a 7px ink dot on the selected row's edge, placed in the space between the number and the column rule (never through a number), with a 1px ink elbow that runs across the gap and enters the popover's side 1.125rem from its near edge. It steps in over 160ms from 0.25rem toward the row.
- **Actions:** a strip of equal cells sharing 1px ink gaps (Edit, Retire, Replace, Delete; or Reactivate, Delete), each with a 600 label and a key legend at the far end. Hover `paper-2`, press `paper-3`, focus inset -4px. On phones the actions form 2 columns at 2.75rem.
- **Forms:** a title line (600, 0.9375rem), a 2-column grid of inputs (1 column on phones), then cell buttons with key legends (Save as primary, Cancel with Esc).
- **Delete confirmation:** the warning box in place of the actions: `warn-wash` fill, `warn` icon, bold `warn` question, the consequence and the alternative in words, then a destructive Delete and a Cancel.
- **Rankings detail:** a title with rank and name, then two columns: a label/mono definition list (rating ±, strength, log-strength, SE, times compared) with the description, and a weighted-record sub-table (Opponent, Won, Lost) with label-small headers, an ink header rule, `hair` row rules, 0.8125rem text and an "and n more" line.

### Title block (signature)
A closed ruled grid of 6 columns in the lower-right corner, drawn as 1px ink gaps over an ink background with `paper` cells. Every cell has a caption label followed by content. Rows on Compare: TITLE (span 4) and FILE (span 2, mono), then readings of two columns each (a mono figure plus a two-line unit), then REVISIONS (span 5) with UNDO (span 1), then state, SKIP and MODE (two columns each). Revision rows use a mono number, text and a mono time, separated by `hair` rules. The previous row is ink 3, and an undone row is struck through with an uppercase tag. A new row slides up in 260ms, and figures step in 220ms. Blinded mode swaps the readings for a single explanatory cell. On phones TITLE and FILE are hidden and the grid becomes 2 flexible columns plus a 7.5rem action column. Future sheets should reuse this cell grammar (caption plus content, spans on a 6-column grid) and not invent a new status panel.

**Parts-list variant.** A KEYS block runs the full height of the title block at its left edge (8.25rem), the way a standard-tolerance block sits in a drawing's title block: a list of small key legends beside their verbs in 0.8125rem ink 2. To its right is the usual 6-column grid with tighter cells (0.375rem `s-3` `s-2`) and the compact title: TITLE and FILE (span 3 each), text cells (Slots, Items or a summary), a Filter or Category control cell with its key, and action cells. **SHEET n OF N** is always the bottom-right cell (span 2): a mono 1rem count followed by previous and next square cell buttons (1.625rem). On phones the keys block, TITLE, FILE and SHEET cells are hidden and the grid becomes 2 columns.

### Notes
A "NOTES" label over a numbered list (mono markers in ink 3, 0.9375rem ink 2 text, max 60ch). Notes sit in the lower-left corner of view sheets, bottom-aligned with the title block, with no border. They hold keys, legends and caveats. Hidden at 64rem and below. Parts-list sheets put their keys in the title block's keys block instead.

### Navigation (sheet tabs)
Condensed caps tabs separated by 1px ink rules in the top bar. The current tab gets `paper-2`, ink text and a 4px inset ink underline. The Project menu sits at the far right as a tab-styled cell with a chevron, and its hover fills `paper-2`. On phones the tabs become a sticky bottom bar of 4 equal cells.

### Notice strip and warning box
**Notice strip:** a `paper-2` band under the header with a 1px ink rule, an icon, a bold lead sentence and a Dismiss cell button. It is used for neutral events such as "file changed on disk". **Warning box:** a `warn-wash` fill, a 1px `warn-mark` rule, a `warn` icon and bold lead, the cause and the recovery in words, and a cell button with a `warn` border. It replaces the content it concerns (for example, the revision rows or a callout's actions) rather than stacking over it; inside a callout the callout's ink rule stands in for the `warn-mark` rule.

## Do's and Don'ts

### Do:
- **Do** draw every new screen as a sheet in the same set: the zoned frame, content in the drawing area, and a closed ruled title block in the lower-right carrying TITLE and FILE. View sheets put notes in the lower-left; parts-list sheets put their keys in the title block.
- **Do** mark zones per ASME Y14.1: numbers right to left on the top and bottom, letters bottom to top on both sides, and an even zone count that follows sheet width (4, 6 or 8).
- **Do** keep line weights to the scale: 2px frame, 1px cells, `line` or `hair` for construction and row rules.
- **Do** set every number, key, slot, rank and file name in JetBrains Mono with tabular figures.
- **Do** pair every colour signal with a shape, pattern, position or words: solid A, hatched B, bar count for strength, a bold name for selection, a tag for retired or unslotted rows, and an icon plus text for warnings.
- **Do** keep markup blue for the live mark, the selected row, focus and text selection only.
- **Do** show lists as parts lists that fold into columns and continuation sheets, snapped to the frame, with the sheet number in the title block's bottom-right cell.
- **Do** put a selected row's actions, forms and detail in the row callout popover, and make clicking the selected row again equal Esc.
- **Do** keep motion to one discrete tick per action (140–260ms, `cubic-bezier(0.16, 1, 0.3, 1)`), with none under `prefers-reduced-motion`.
- **Do** self-host Barlow, Barlow Condensed and JetBrains Mono in the real app.

### Don't:
- **Don't** divide views, scales or notes with rules, and don't draw a centre line. Space and alignment separate them on view sheets.
- **Don't** use shadows for elevation, rounded cards, pill buttons, modal dialogs or raised keycaps. Controls are ruled cells, and the row callout popover is set off by its 2px rule, not a shadow.
- **Don't** round anything except slot-identifier balloons and the callout's leader dot.
- **Don't** refold a parts list when a row is selected, and don't cover the find-number column; the callout is a popover beside it, tied to the row by a leader.
- **Don't** use markup blue or warning orange decoratively, and don't use orange without an icon and words.
- **Don't** convey side, state, category or strength by colour alone, and never set red against green.
- **Don't** put condensed caps labels above headings as eyebrows. A label names the cell, column or view it belongs to.
- **Don't** present ratings as absolute. Readings carry units and ± tolerance.
