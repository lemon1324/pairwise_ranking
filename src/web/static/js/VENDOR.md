# Vendored scripts

Third-party code checked in here rather than fetched at runtime. The application
runs on a LAN, often with no route to the internet at all, so anything a page
needs has to be in the image.

## htmx

- **File:** `htmx.min.js`
- **Version:** 2.0.10
- **Source:** <https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js>
- **Fetched:** 2026-09-17
- **Licence:** BSD Zero Clause (0BSD), <https://github.com/bigskysoftware/htmx>
- **Integrity:** `sha384-H5SrcfygHmAuTDZphMHqBJLc3FhssKjG7w/CeCpFReSfwBWDTKpkzPP8c+cLsK+V`

The integrity hash is recorded so a future update can be checked against the
published artefact; it is not put in the `<script>` tag, because the file is
served from our own origin and a stale hash there would blank the page rather
than warn anybody.

To update, download the new version, replace the file, and update the version,
date and hash above:

```bash
curl -sfS -o htmx.min.js https://unpkg.com/htmx.org@<version>/dist/htmx.min.js
openssl dgst -sha384 -binary htmx.min.js | openssl base64 -A
```
