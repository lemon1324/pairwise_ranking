---
version: 1
slug: "docs-mockups-rankings-html"
primary_target: "docs/mockups/rankings.html"
related_targets: ["docs/mockups/items.html"]
---

# Rankings (web) surface brief

Scope: the Rankings sheet of the planned web app, desktop and phone. Static mid-fi mockup
(`docs/mockups/rankings.html`), extending the Drawing Set world in DESIGN.md and sharing the parts-list
table system with Items. Visitor mode: Operate.

Audience and job: the owner reading the result: the order, how certain each rating is, and why an item
sits where it does.

Direction (confirmed): a BOM-style sheet. Rank as the find number; Name; Category; Rating; ± SE shown as
tolerance; Comparisons. Retired items appear only with Show Retired, carry no rank, sort by rating and
are tagged. The selected row's callout strip shows strength, log-strength, SE, description and a
weighted wins/losses sub-table per opponent.

Overflow, selection and paging: identical to Items (fold into columns >= 36rem, continuation sheets,
phone scroll). ↵ toggles the strip.

Title block: TITLE, FILE, Category filter, Show Retired H, Export CSV X (exports exactly what the filters
show), summary ("38 active shown · 4 retired hidden"), sheet number, keys. Note that ratings are relative
to the current item set.

States: normal, row expanded, category filtered, retired shown, fewer than 2 items, no votes.

Assumptions: no blinded mode on Rankings; fixed sort by rating.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
