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
  label:
    fontFamily: "Barlow Condensed, Barlow, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.08em"
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
  key-legend:
    textColor: "{colors.ink}"
    typography: "{typography.number}"
    rounded: "{rounded.none}"
    padding: "0 0.3rem"
    height: "1.5rem"
  balloon:
    textColor: "{colors.ink}"
    typography: "{typography.number}"
    rounded: "{rounded.balloon}"
    height: "2rem"
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

Every screen of the web app is one sheet from a single engineering drawing set. The ground is drafting paper, structure is drawn in ink at a strict line-weight scale, and a sheet is read the way a drawing is read: a frame with zone markings, views in the drawing area, notes in the lower-left, a closed ruled title block in the lower-right. Compare is the first sheet (two views and a dimensioned seven-station scale). Items and Rankings are meant to be parts-list (BOM) sheets in the same set, and Settings and the project picker are sheets too. A new surface should look like another sheet of the same set, not like a new app.

The world is dense but calm. Space, alignment and line weight carry the hierarchy. There are no cards, no shadows, no button chrome and no rounded corners except the item balloon, which is round because drawings circle their part identifiers. Drafting notation is what gives the sheets their character: zones per ASME Y14.1, balloons, dimension lines with arrowheads, underlined view titles, revision rows, tolerance given as ±. None of it is decoration. Each piece has the job it has on a real drawing.

Colour is almost absent. Ink on paper does the work. One markup blue marks the live thing (the station just pressed, keyboard focus, selection), and one warning orange appears only with an icon and words. The primary user has deuteranopia, so colour never carries meaning alone: side A is a solid fill and side B is hatched, strength is shown by bar count, and every state has a label or a shape.

**Key Characteristics:**
- A drafting-paper ground with ink linework in three weights: frame 2px, cell 1px, construction hairline.
- The sheet anatomy is fixed: a zoned frame, views, notes in the lower-left and the title block in the lower-right.
- Controls are ruled cells. Nothing is raised, rounded or filled with chrome.
- Three families, each with one job: a condensed caps label face, a workhorse sans for names and prose, and tabular mono for every number.
- Solid means A and hatched means B, so sides and states never depend on colour.
- Motion is one short, discrete tick per action, and none under reduced motion.

## Colors

The palette is warm paper and near-black ink, with one blue for markup and one orange for problems. Both themes are first-class. Dark mode is ink-on-blueprint-dark, not an inversion afterthought, and each light token has a `-dark` twin with the same role.

### Primary
- **Markup Blue** (`markup`; dark `markup-dark`): the checker's pencil. It is used only for the station just pressed (its border, key and bars), the `:focus-visible` outline (2px, 2px offset; -4px inset inside cells), text selection and native accent controls. **Markup Wash** (`markup-wash`) fills the marked station behind the blue.

### Secondary
- **Warning Orange**: a set of three. **Warn** (`warn`) is for warning text, the icon and the button border. **Warn Mark** (`warn-mark`) is the warning box rule. **Warn Wash** (`warn-wash`) fills the warning box. It is used for save failures and for a problem with the file name, and never for anything positive or neutral.

### Neutral
- **Drafting Paper** (`paper`): the sheet ground and title-block cell fill.
- **Paper 2** (`paper-2`): hover on cells and tabs, the current tab and the notice strip.
- **Paper 3** (`paper-3`): the pressed (`:active`) state and cell-button hover.
- **Ink** (`ink`): text, frame and cell rules, the A fill and B hatch, and the title-block grid, which shows through its 1px gaps.
- **Ink 2** (`ink-2`): descriptions, notes and secondary prose.
- **Ink 3** (`ink-3`): labels, units, zone letters and numbers, timestamps, previous revisions and disabled text.
- **Line** (`line`): construction marks such as zone ticks, station ticks and dashed ghost outlines.
- **Hair** (`hair`): the lightest rules (between revision rows, the footer) and disabled borders and bars.

### Named Rules
**The One Pencil Rule.** Markup blue marks only what is live right now: the pressed station, focus and selection. It is never used for decoration, brand, headings or a resting state.

**The Never Alone Rule.** Every colour signal has a non-colour twin. Warnings carry an icon and words. Sides carry solid versus hatched fills and left versus right position. Strength carries bar count. Red against green never carries meaning.

## Typography

**Display Font:** Barlow (with system-ui)
**Body Font:** Barlow (with system-ui)
**Label/Mono Font:** Barlow Condensed for labels (with Barlow, system-ui); JetBrains Mono for numbers (with ui-monospace)

**Character:** This is a drafting-office type set. The condensed caps read like lettering on a title block, Barlow reads plainly at any size, and mono keeps every figure aligned like a table of dimensions. The mockup loads fonts from Google Fonts, but the real app must self-host them because it runs on a LAN.

### Hierarchy
- **Display** (600, clamp(1.625rem, 1rem + 1.6vw, 2.625rem), 1.08, -0.015em, balanced wrap): item names in a view, the largest words on a sheet. 1.5rem on phones.
- **Title** (600, 1.1875rem, 1.2): the project name in the title block's TITLE cell. The phone top bar uses the same style at 1–1.125rem.
- **Body** (400, 1rem, 1.45, tabular figures on): default text. Station names use 600 at 1rem.
- **Body secondary** (400, 0.9375rem): notes (max 60ch), revision rows, warning copy and category values. Item descriptions sit at 1.0625rem in ink 2, max 42ch.
- **Label** (Barlow Condensed 600, 0.75rem, 0.08em, uppercase, ink 3): the caption for every cell, view title and note heading. Tabs and cell buttons use the same face at 0.875–0.9375rem with 0.06em tracking.
- **Figure** (JetBrains Mono 500, 1.5rem, 1.1): title-block readings (settled, tolerance, votes), each followed by a two-line unit in 0.8125rem ink 3.
- **Number** (JetBrains Mono 400–500, 0.75–0.875rem): keys, balloons, weights, revision numbers and times, list markers, and the file name.

### Named Rules
**The Every Number In Mono Rule.** Any figure the user might compare or scan (a count, rating, weight, slot, time, key or file name) is set in JetBrains Mono with tabular numerals. Words stay in Barlow.

**The Caption Not Kicker Rule.** Condensed caps labels name the cell or view they sit in, the way lettering names a field on a title block. They never float above a heading as a decorative eyebrow.

## Layout

**Sheet shell.** A top bar with a 2px ink bottom rule, 3.25rem tall (2.75rem on phones), holds the sheet tabs and a Project menu. An optional notice strip sits below it. Below that is the drawing frame, which fills the rest of the viewport.

**Frame and zones.** The outer frame is a 2px ink border with a 1.375rem zone band inside it, then a 1px inner border. Zone markings follow ASME Y14.1. Numbers run right to left along the top and bottom borders, and letters run bottom to top on both sides, so zone A1 is the lower-right corner. Labels are Barlow Condensed 500 at 0.6875rem in ink 3. Boundary ticks are 1px × 0.5rem in `line`, drawn inward from the outer frame line. The zone count adapts to the sheet width through container queries, keeping the count even at about one zone per 170px: 4 zones below 44rem, 6 from 44rem, 8 from 64rem, 10 from 85rem, and 12 from 106rem. The high numbers drop off the left end first. Letters stay A–D. Phones (≤40rem) drop the outer frame and zones and give the inner frame the 2px weight.

**Drawing area.** The inner frame is a grid. The drawing area spans the full width. Below it, notes and the title block share the bottom row: notes take `1fr` and the title block takes `minmax(34rem, 46rem)`. Both are bottom-aligned, so notes sit in the lower-left corner and the title block closes the lower-right corner, flush against the frame's right and bottom edges. At 64rem and below, the title block goes full width and notes are hidden.

**No dividing rules in the drawing area.** Views, the vote scale and notes are separated by space and alignment, not by lines. The only closed ruled region in the drawing area is the title block. Content inside a view is centred on the view's axis. There is no centre line between views.

**Spacing rhythm.** The spacing scale runs 0.25 / 0.5 / 0.75 / 1 / 1.5 / 2 / 3rem (`s-1`–`s-7`). Views pad `s-4 s-6 s-5`, cells pad `s-2 s-3 s-3`, and the frame sits `s-4 s-5 s-5` from the viewport. Phones tighten to `s-2`–`s-4`.

**Breakpoints.** At 40rem the layout switches to phone: bottom tabs, stacked views, 2-column stations, and a compressed title block. At 64rem the title block goes full width and notes are hidden. The zone thresholds at 44, 64, 85 and 106rem are measured on the frame container, not the viewport.

**Navigation.** Desktop sheet tabs sit in the top bar. On phones they move to a sticky 4-column bottom bar with a 2px top rule, and the project name moves into the top bar, because the title block's TITLE and FILE cells are hidden on phones.

## Elevation & Depth

The system is flat, and depth is conveyed only by line weight. Frame rules are 2px, cell rules 1px, and construction marks are 1px in the lighter `line` or `hair` colours. Nothing floats. There are no box-shadows for elevation. The only `box-shadow` values in the build are drawing devices: a 4px inset ink underline on the current tab, and a 1px inset outline that closes the edge of a hatched fill. Overlays are not stacked cards. For example, the empty-scale message sits on an 88% paper wash over the dimmed stations.

### Named Rules
**The Line Weight Is Depth Rule.** To make something more important, draw its border heavier (1px to 2px) or move it into the title block. Never lift it with a shadow, and never round it into a card.

## Shapes

The form language is rectilinear. Every cell, button, key legend, station, warning box and tab has square corners (radius 0). The single round form is the **item balloon**, a full circle (999px) around an identifier, as on a parts list. Keep it exclusive to slot identifiers so it stays readable as "this is a physical slot". Adjacent ruled cells share borders. Stations overlap by -1px, and the title block uses a 1px ink gap over an ink background, so rules never double. The dimension line uses filled triangular arrowheads (9px) and a mono `0` at the centre. Ghost placeholders use a 1px dashed `line` border. Side swatches are 14px squares, solid for A and 45° hatched (1.5px ink every 4px) for B.

## Components

### Buttons (cell buttons)
Ruled and quiet, like a field on a form you can press.
- **Shape:** square (0), 1px ink border, 2.25rem minimum height.
- **Default:** transparent fill, label type (Barlow Condensed 600, 0.875rem, 0.06em, uppercase), optional 1rem stroke icon.
- **Hover / Focus:** hover fills `paper-3`. Focus is the global 2px markup outline.
- **Disabled:** ink 3 text, `hair` border, not-allowed cursor.
- **Title-block action cells:** Undo, Skip and Mode are whole cells, not bordered buttons. A cell has a caption label, a 600 action line with an icon, and a key legend. Hover fills `paper-2`, and focus draws the outline inset by -4px.

### Key legend
A keyboard shortcut is drawn as a ruled mono cell (1px currentColor border, 1.5rem, JetBrains Mono 500 at 0.8125rem), never as a raised keycap. Smaller 1.25rem legends sit inline in notes.

### Item balloon
A circled mono identifier (2rem, 1px ink). In a blinded view the balloon is the whole content: 5.5rem, 2px border, 2.25rem numerals (4rem on phones).

### Views
Each item is a view in the drawing area, centred on its own axis. Contents run in this order: the name (display), the description (ink 2), then a small definition grid with Category stacked above Slot. In that grid, labels are right-aligned and values left-aligned, meeting at the axis. On phones the grid collapses to one centred line without labels. Under each view is an underlined view title: a swatch (solid A or hatched B) plus a "VIEW A" / "VIEW B" label with a 1px ink rule beneath. Views are separated only by space.

### Station scale (signature)
This is the primary action on Compare: a dimension line ("A preferred", arrowhead, 0, arrowhead, "B preferred") above seven ruled stations sharing borders. Each station stacks, top to bottom: a key legend, strength bars, a name and a mono weight. A 0.75rem tick connects each station to the dimension line. Strength bars ascend low to high on both sides (33/66/100%): solid for A, hatched for B, and a single 1px line for Equal. Hover fills `paper-2` and press fills `paper-3`. **Marked** is the only coloured state: `markup-wash` fill, markup border, bars and key, held for 420ms after a vote. On phones the stations form 2 columns (A keys 1–3 left, B keys 7–5 right, mirrored, Equal spanning the bottom row), and the dimension line and weights are hidden.

### Title block (signature)
A closed ruled grid of 6 columns in the lower-right corner, drawn as 1px ink gaps over an ink background with `paper` cells. Every cell has a caption label followed by content. Rows on Compare: TITLE (span 4) and FILE (span 2, mono), then readings of two columns each (a mono figure plus a two-line unit), then REVISIONS (span 5) with UNDO (span 1), then state, SKIP and MODE (two columns each). Revision rows use a mono number, text and a mono time, separated by `hair` rules. The previous row is ink 3, and an undone row is struck through with an uppercase tag. A new row slides up in 260ms, and figures step in 220ms. Blinded mode swaps the readings for a single explanatory cell. On phones TITLE and FILE are hidden and the grid becomes 2 flexible columns plus a 7.5rem action column. Future sheets should reuse this cell grammar (caption plus content, spans on a 6-column grid) and not invent a new status panel.

### Notes
A "NOTES" label over a numbered list (mono markers in ink 3, 0.9375rem ink 2 text, max 60ch). Notes sit in the lower-left corner, bottom-aligned with the title block, with no border. They hold keys, legends and caveats. Hidden at 64rem and below.

### Navigation (sheet tabs)
Condensed caps tabs separated by 1px ink rules in the top bar. The current tab gets `paper-2`, ink text and a 4px inset ink underline. The Project menu sits at the far right as a tab-styled cell with a chevron, and its hover fills `paper-2`. On phones the tabs become a sticky bottom bar of 4 equal cells.

### Notice strip and warning box
**Notice strip:** a `paper-2` band under the header with a 1px ink rule, an icon, a bold lead sentence and a Dismiss cell button. It is used for neutral events such as "file changed on disk". **Warning box:** a `warn-wash` fill, a 1px `warn-mark` rule, a `warn` icon and bold lead, the cause and the recovery in words, and a cell button with a `warn` border. It replaces the content it concerns (for example, the revision rows) rather than stacking over it.

### Parts lists (for Items and Rankings sheets)
No component exists yet. These sheets should extend the title-block cell grammar: ruled 1px cells, caption labels, mono for every number and identifier, balloons for slots, `hair` rules between body rows, ink 3 for retired or previous entries, and strike-through plus a tag for removed ones. This paragraph is guidance for extending the system, not a documented component.

## Do's and Don'ts

### Do:
- **Do** draw every new screen as a sheet in the same set: the zoned frame, content in the drawing area, notes in the lower-left, and a closed ruled title block in the lower-right carrying TITLE and FILE.
- **Do** mark zones per ASME Y14.1: numbers right to left on the top and bottom, letters bottom to top on both sides, and a zone count that follows sheet width.
- **Do** keep line weights to the scale: 2px frame, 1px cells, `line` or `hair` for construction and row rules.
- **Do** set every number, key, slot and file name in JetBrains Mono with tabular figures.
- **Do** pair every colour signal with a shape, pattern, position or words: solid A, hatched B, bar count for strength, and an icon plus text for warnings.
- **Do** keep markup blue for the live mark, focus and selection only.
- **Do** keep motion to one discrete tick per action (140–260ms, `cubic-bezier(0.16, 1, 0.3, 1)`), with none under `prefers-reduced-motion`.
- **Do** self-host Barlow, Barlow Condensed and JetBrains Mono in the real app.

### Don't:
- **Don't** divide views, scales or notes with rules, and don't draw a centre line. Space and alignment separate them, and the title block is the only closed ruled region in the drawing area.
- **Don't** use shadows for elevation, rounded cards, pill buttons or raised keycaps. Controls are ruled cells.
- **Don't** round anything except slot-identifier balloons.
- **Don't** use markup blue or warning orange decoratively, and don't use orange without an icon and words.
- **Don't** convey side, state, category or strength by colour alone, and never set red against green.
- **Don't** put condensed caps labels above headings as eyebrows. A label names the cell or view it belongs to.
- **Don't** present ratings as absolute. Readings carry units and ± tolerance.
