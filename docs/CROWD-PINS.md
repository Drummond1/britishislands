# Crowd pins — community suggestions

Lightweight layer for **missing islands** or **unnamed features**: visitors drop a
map pin and open a pre-filled GitHub issue. Maintainers triage proposals and
append approved rows to `data/crowd_pins.json`. Nothing is merged into
`data/islands.json` without normal **provenance** rules (`docs/ETHICS.md`).

## User flow (frontend)

1. **Suggest island** (top bar) → click the map once → optional fields → **Submit
   suggestion** (in-app; no GitHub account). Optional **Submit via GitHub** fallback.
2. **Crowd pins** toggle shows gold `circleMarker`s from `data/crowd_pins.json`.
3. Popups: **Suggest a name** opens the same in-app form (pin id prefilled).

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

## Maintainer triage

1. Read the issue — check location is in project remit (~50 mi UK + Ireland).
2. Deduplicate: same skerry already in `islands.json`? Skip or close with id.
3. If keeping as a **community pin only**, add an object to `pins` in
   `data/crowd_pins.json`.
4. If promoting to the atlas, run the normal ingestion / discovery path with
   OSM/Wikidata (or other allowed sources); do **not** add atlas rows from
   coordinates alone.

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
- Optional **name source URL** helps others trust labels; absence does not block
  an unnamed pin.
- Do not publish email addresses or precise home addresses in `pins` or issues.

## Related files

- `crowd-pins.js` — fetch + GitHub URL builders + popup HTML.
- `app.js` — layer, modal, map click picker.
- `.github/ISSUE_TEMPLATE/crowd-island-suggestion.md` — manual template.
- `.github/ISSUE_TEMPLATE` — “Crowd island suggestion” from the in-app body also
  uses `docs/CROWD-PINS.md` in copy.
