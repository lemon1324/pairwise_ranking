---
version: 1
slug: "docs-mockups-projects-html"
primary_target: "docs/mockups/projects.html"
related_targets: []
---

# Project picker (web) surface brief

Scope: the project picker, the web app's landing sheet when no project is open. Static mid-fi mockup
(`docs/mockups/projects.html`) in the Drawing Set world (DESIGN.md). Visitor mode: Operate.

Job: the owner picks a project to open, starts a new one, or imports a `.pairrank` from the desktop
app. On the web there are no file dialogs: the picker lists every `*.pairrank` in the data directory
(`/data` bind mount).

Direction (extends the world, no new roll): a drawing register, the index sheet of the set. Uses the
parts-list engine (folding, callout popover, keys). Columns: No., Project (name, file name as mono
second line), Items, Votes, Modified. Callout: Open ↵, Duplicate without votes D, Download. Title block:
KEYS block, TITLE "Drawing register", DATA DIR, counts, New project N, Import I, SHEET n OF N. No
sheet tabs in the top bar (no project is open); the app name sits there instead.

New project: form in a callout on a pseudo row at the top; the file name is derived live with
safe_project_filename; an existing file name is an error with icon and words.
Import: callout with a dashed drop zone and file picker; shows the parsed file (name, items, votes)
before importing; a non-.pairrank or unreadable file is an error.

File conditions shown as tags plus words (never colour alone): format v1 (upgraded on first open,
original kept as .v1.bak), newer format (cannot be opened by this version), unreadable (with reason).

States: normal, selected, new project (with name conflict), import (file parsed), import error,
problem files, empty data directory.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
