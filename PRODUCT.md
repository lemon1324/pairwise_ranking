# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Two frontends over one shared, Qt-free Python core (`src/models/`, `src/data/`):

- **Desktop (incumbent):** PyQt6, `main.py`. Stays supported; its tests must keep passing.
- **Web (in progress):** FastAPI + Jinja2 + HTMX, server-rendered, minimal JS, one Docker
  container on the owner's Unraid NAS. Planning notes live in `data/webapp-conversion-handoff.md`.

## Users

The primary user is the owner, almost exclusively. They rank physical or sensory things where
comparing two side by side is easy but giving each an absolute score is hard: keyswitches on a
tester board, samples in a tasting flight, a shortlist being narrowed to a decision.

Secondary, occasional: friends on the same LAN, and later people signed in through an OIDC
provider. Anyone who finds the public MIT repo is welcome to self-host it, but they are not a
design target.

## Product Purpose

Turn a stream of "which of these two is better?" answers into a trustworthy ranked list. The app
fits a Bradley-Terry model to weighted pairwise votes and reports ELO-style ratings with a
per-item uncertainty estimate. Success means the owner reaches a ranking they believe, with as few
comparisons as possible, without ever doing bookkeeping by hand.

## Positioning

It is not a poll or a scoring sheet. The mechanism is statistical: an active pair selector picks
the next comparison to reduce uncertainty, join disconnected parts of the comparison graph,
refresh stale votes and cover uncompared items. It also models the physical world the items live
in: slots on a board or rack, retiring an item while keeping its history, and replacing it with a
successor that inherits its slot. The data is one human-readable `.pairrank` JSON file the owner
controls.

## Operating Context

- **Sessions are short bursts:** a few minutes of votes at a time, repeated over weeks. Every
  change saves immediately; there is no Save command. Resuming has to be instant.
- **Typical project:** 10 to 50 items.
- **Devices, equally:** a desk with a keyboard, and a phone held while standing at the objects.
  The Compare flow must be fast on both: number keys 1-7, S and Ctrl+Z on a keyboard, and large
  touch targets on a phone.
- **Physical workflow:** items sit in identifiable slots. Blinded mode shows only identifiers so
  the owner judges the object, not the name.
- **Hosting:** LAN-only container, `.pairrank` files on a bind mount at `/data`. The same files
  may also be opened by the desktop app, sometimes over SMB.

## Capabilities and Constraints

Confirmed (desktop today, planned for web):

- Projects: create, open, rename, duplicate without votes, save as. On the web, the picker lists
  every `.pairrank` in the data directory, with import by upload instead of file dialogs.
- Items: name, description, free-text category, identifier (the physical slot). Add, edit,
  retire, replace, reactivate, delete. Delete removes every vote involving the item.
- Optional slot list per project; identifiers are chosen from free slots and slot usage is shown.
- Compare: seven-point scale (A much better ... Equal ... B much better, weights 3/2/1), skip,
  undo of the last vote, which offers that pair again.
- Rankings: ELO rating, standard error, comparisons, weighted wins and losses against each
  opponent, category filter, show retired, CSV export of exactly what is shown.
- Settings: pair-selection weights, vote decay half-life, top-tier focus mode, cross-category
  rate, blinded mode, slots. Reset to defaults leaves slots alone.

Constraints:

- The `.pairrank` format is shared with the desktop app; the web app must not fork it.
- No login in v1, but every route must sit behind one current-user dependency so OIDC or a
  forward-auth proxy can be added later. Serve under a configurable root path.
- ELO ratings are relative to the current item set; they shift when items are added or retired.
  UI must not present them as absolute or comparable across snapshots.

Terminology: *item*, *identifier*, *slot*, *retire*, *replace*, *reactivate*, *vote*, *skip*,
*blinded mode*, *project*.

Undecided:

- Whether friends voting in the same project should have their votes attributed. The file format
  has no voter field today; adding one would be a format version 3. Out of scope for v1.
- Live updates between open tabs (not planned for v1).

## Evidence on Hand

- Real project data in `data/` (gitignored): `project.pairrank` and legacy CSVs.
- `README.md` documents behaviour, file format and the algorithm in detail.
- No logo, icon, screenshots, testimonials or user counts exist. Do not invent them.

## Product Principles

1. **The next vote is one keystroke or one tap away.** Comparing is the core loop and is done in
   short bursts; nothing should stand between opening the app and answering.
2. **Show the uncertainty, not just the order.** A ranking is an estimate; surface how sure it is
   and never imply more precision than the model has.
3. **History is kept, not destroyed.** Retire over delete, undo over confirm, backups on every
   save. Destructive actions are explicit about what they remove.
4. **The file is the product's truth.** Human-readable, portable between desktop and web, owned by
   the user.
5. **Match the physical setup.** Slots, identifiers and blinded mode exist because the items are
   real objects in real places; design around that scene.

## Accessibility & Inclusion

- **Red-green colour blindness (deuteranopia) is a hard requirement.** The primary user has it.
  Every palette must stay distinguishable under deuteranopia, never pair red against green to
  carry meaning, and never use colour as the only signal for a state, side or category: pair it
  with a label, position, shape or pattern.
