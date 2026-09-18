# Self-hosted fonts

Three families, self-hosted because the application runs on a LAN and must not
depend on fonts.gstatic.com being reachable. The `@font-face` rules are in
`../css/sheet.css`.

| Family | Weights | Why |
| --- | --- | --- |
| Barlow | 400, 500, 600 | Names, prose and title-block titles |
| Barlow Condensed | 500, 600 | Drafting labels, tabs and zone letters |
| JetBrains Mono | 400, 500 | Every figure, key legend, slot and file name |

Those are exactly the weights `DESIGN.md`'s type ramp uses, and exactly what the
mockups asked Google Fonts for. Nothing here is loaded at any other weight, so
no synthesised bold ever appears.

## Provenance

Downloaded 2026-09-17 from the Google Fonts CSS API v2, the same request the
mockups make:

```
https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600&family=Barlow:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap
```

Barlow and Barlow Condensed are at `v13`, JetBrains Mono at `v24`. Only the
`latin` and `latin-ext` subsets are kept: the application's own text is English
and a project's own names are the only other text on a sheet, so the Greek,
Cyrillic and Vietnamese subsets would be bytes nobody fetches.

JetBrains Mono is served as a single variable font, so weights 400 and 500 are
the **same file** — hence one pair of files with a `font-weight: 400 500` range
rather than two identical pairs under different names.

## Licence

All three are under the SIL Open Font License 1.1; the licence text ships beside
the fonts as `OFL-Barlow.txt`, `OFL-BarlowCondensed.txt` and
`OFL-JetBrainsMono.txt`, which is what the OFL asks of anyone redistributing
them.
