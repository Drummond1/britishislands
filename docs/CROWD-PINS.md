# Crowd pins — community suggestions

Lightweight layer for **missing islands** or **unnamed features**: visitors drop a
map pin and open a pre-filled GitHub issue. Maintainers triage proposals and
append approved rows to `data/crowd_pins.json`. Nothing is merged into
`data/islands.json` without normal **provenance** rules (`docs/ETHICS.md`).

## Name an island

Click an island marked with a question mark. The page asks one question:
what it is called. Then your name, and your email. The line under the email
says we don’t publish it. One button: **Name it**.

The name shows on the map, the list, and the profile, as **Named by** that
person. `islands.json` stays unnamed until a published source is added.

The same three fields are the naming step if someone is placing a missing
island. A source, a note, and GitHub are not part of naming.

**Named by the public**, next to All islands, shows only these names, newest
first.

Each save inserts `public.island_name_log`. Anonymous clients can insert and
cannot read the table. The map reads `island_names_public()`, which returns
the name, the person’s name, and the place, and does not return the email.
A database trigger emails drummondgilbert@gmail.com through FormSubmit. The
first message is an activation link; after that link is opened, each name
sends an email. The same rows are available as a private CSV for the Google
Sheet **Find My Island — names from the public**, with columns Submitted,
Island, Named by, Email, Island id, Latitude, Longitude. The token for that
CSV is not in the repo. Creating the spreadsheet needs a connected Google
Sheets account.

If Supabase is not configured, the form is sent through the suggestion inbox
(`data/crowd_suggest_config.json`) and the name is kept in this browser.

## What's interesting, and what you can do

On a named island, under the description:

1. Two boxes: what's interesting, and what you can do. One of them is enough.
2. Your name, which is shown on the note.
3. Email, optional. The label says **Not published**. It is not shown on the island, not stored in the browser’s public note, and not returned by `island_visitor_notes_public()`.
4. **Add to this island.** The note appears under “From visitors. Not checked.” The page does not jump back to the top.

It is not written into `islands.json`. Leave out private addresses, phone numbers, and anything meant as a guide for boats or wildlife. The public text is in `island_visitor_notes`. The email sits in `contributor_email` on that row. Anonymous clients can insert and cannot select the table.

Each new note is also emailed to drummondgilbert@gmail.com through FormSubmit, with the island name, place, page, the short listing, both answers, the name, and the email. The first send asks FormSubmit for a one-time activation click in that inbox. If the server send does not go through, the browser sends the same message.

A private Google Form can also append the same fields to a spreadsheet. The form address and entry ids live in `island_note_inbox` (one row, id 1), which anonymous clients cannot read. Until that row is filled, the sheet is not written. Do not put the form address in the site JavaScript.

## User flow (frontend)

1. **More → Contribute.** Two choices: add a missing island, or name one that is
   already on the map. A listed island whose text is wrong is a quieter third link.
2. **Add a missing island** opens the map. On a phone the list sheet tucks away.
   The bar says to zoom in and click the middle of the land, not the water.
   Another click, or a drag of the gold dot, moves it. **Use this spot** opens
   the name step.
3. **What is it called?** The name, your name, and your email. The email is
   not published. **Name it** saves it. **Move the pin** goes back to the map.
4. **Crowd pins** toggle shows gold markers from `data/crowd_pins.json`.
   An unnamed pin’s popup says **Name this place** and opens the same form.

### Native submit configuration

Static hosting cannot write to the repo from the browser. Configure one provider in
`data/crowd_suggest_config.json` (see `data/crowd_suggest_config.example.json`), or
override before `app.js`:

**Production (GitHub Pages):** add repository secret `CROWD_FORM_EMAIL` with a
[FormSubmit](https://formsubmit.co/) inbox you control. The
`.github/workflows/pages.yml` workflow injects it into `crowd_suggest_config.json`
on each deploy. Until the secret is set, contributors can use **Send via GitHub**,
**Send via email app** (mailto with pre-filled body), or copy the issue text.

**Local:** copy `config.local.example.js` → `config.local.js` (gitignored) or run:

`CROWD_FORM_EMAIL=you@example.com python3 scripts/prepare_crowd_config.py`

Override before `app.js` (alternative):

```html
<script>
  window.IOB_SUGGEST_CONFIG = {
    provider: "formsubmit",
    formsubmitEmail: "suggestions@yourdomain.com"
  };
</script>
```

Supported `provider` values: `formsubmit`, `formspree`, `web3forms`, `webhook`.
FormSubmit sends email to the address you verify on first use (free tier).

Override the issue repo with `window.IOB_CORRECTION_REPO` (same as corrections),
or the default `Drummond1/britishislands` is used (`crowd-pins.js`).

## Maintainer triage workflow

Work newest-first. Each submission should end in one of: **close (duplicate)**,
**community pin only**, or **promote to atlas**.

### 1. Intake

- Read the issue or FormSubmit email — confirm coordinates are in remit (~50 mi of
  UK + Ireland, including inland river/lake islands where relevant).
- Check `nameSourceUrl` when a name is proposed; reject or ask for a public source
  if the label is contentious or unsourced.
- Never paste contributor email addresses into `crowd_pins.json` or issues.

### 2. Deduplicate

- Search `islands.json` / the live map at the same coordinates (±100 m).
- Search existing `crowd_pins.json` for the same skerry.
- If the feature is already an atlas island, close with the canonical `id` and thank
  the reporter.

### 3. Community pin only

When the suggestion is useful on the map but not yet atlas-ready:

1. Assign the next stable id: `crowd-YYYY-NNN`.
2. Append to `data/crowd_pins.json` → `pins[]` with `lat`, `lng`, optional `name`,
   `note`, `nameSourceUrl`, `status: "open"`, and `credits[]` (pin / named roles).
3. Commit with a one-line note referencing the GitHub issue number.
4. Close the issue: “Shown as community pin `crowd-…`”.

### 4. Promote to atlas

When OSM/Wikidata (or another allowed source in `docs/DATA-SOURCES.md`) backs the
feature:

1. Run the normal discovery / ingestion path — e.g.
   `python3 scripts/discover_islands_pipeline.py --stage=catalog_scanner` then
   verifier → enricher → `site_update --apply` after review.
2. **Do not** hand-add rows from coordinates alone; provenance is mandatory
   (`docs/ETHICS.md`, `docs/DATA-SCHEMA.md`).
3. Set the crowd pin `status` to `merged` (or remove the pin if redundant).
4. Run `python3 scripts/build_islands_index.py` after `islands.json` changes.
5. Close the issue with the new atlas `id`.

### 5. Production deploy

- Crowd overlay ships with the static site; merging `crowd_pins.json` to `main`
  updates production on the next GitHub Pages deploy.
- Native submit needs secret `CROWD_FORM_EMAIL` in the repo (see
  `.github/workflows/pages.yml`); without it, contributors use GitHub / mailto
  fallbacks only.

## `crowd_pins.json` shape

Top level:

| Field | Type | Notes |
|-------|------|--------|
| `schemaVersion` | number | Currently `1`. Bump only if fields change. |
| `about` | string | Human note for editors. |
| `pins` | array | May be empty. |

Each **pin** (informal contract — not `islands.json` schema):

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `id` | string | yes | Stable id, e.g. `crowd-2026-001`. |
| `lat` | number | yes | WGS84. |
| `lng` | number | yes | WGS84. |
| `name` | string | no | Omit or empty = unnamed (popup shows “needs ID”). |
| `note` | string | no | Short description from contributor or editor. |
| `nameSourceUrl` | string | no | Optional public URL backing the name. |
| `status` | string | no | e.g. `open`, `named`, `merged` — display only. |
| `placedBy` | string | no | **Recognition** line (who placed / reported). |
| `namedBy` | string | no | **Recognition** line (who suggested the name). |
| `credits` | array | no | Structured credits; see below. |

`credits[]` entries:

| Field | Type | Notes |
|-------|------|--------|
| `role` | string | `pin`, `named`, or `verified` (maps to Pin / Name / Verification in UI). |
| `label` | string | Display name / handle (no email). |
| `sourceUrl` | string | Optional; shown in popup list. |

Keep personal data minimal; prefer GitHub @handles or first names only.

## Ethics

- Crowd pins are **not** assertions of legal title or exact boundaries — they are
  pointers for review.
- The contribute form keeps **Add a source** collapsed. Most people will not
  have one, and a name can still be sent. Open it for a link, a book, or a
  sentence. Reviewers still ask when a label is contentious.
- Do not publish email addresses or precise home addresses in `pins` or issues.

## Related files

- `crowd-pins.js` — fetch + GitHub URL builders + popup HTML.
- `app.js` — layer, modal, map click picker.
- `.github/ISSUE_TEMPLATE/crowd-island-suggestion.md` — manual template.
- `.github/ISSUE_TEMPLATE` — “Crowd island suggestion” from the in-app body also
  uses `docs/CROWD-PINS.md` in copy.
