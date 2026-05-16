# Pipeline — how to rebuild the dataset end-to-end

> Default mode is **cached** (re-uses `data/*_raw.json` and `data/cache_*.json`).
> Pass `--no-cache` to force fresh API calls. Be polite — Overpass and
> Wikimedia have rate limits and are operated by volunteers.

## Prerequisites

```bash
python3 --version   # 3.9+ (Shapely 2.x works)
pip install requests shapely
```

No virtualenv assumed; system Python at
`/Library/Developer/CommandLineTools/.../python3` is fine.

## 0. Sanity checks before any run

- Read [`STATE.md`](STATE.md) → **"Currently running"**. If a pipeline is
  already running, stop. They mutate `data/islands.json` in place.
- Make a backup if you're about to do something risky:
  ```bash
  cp data/islands.json data/islands.json.before-$(date +%Y%m%d-%H%M)
  ```
  (The discovery script also writes a `.before-ingest` backup automatically.)

## 1. Fetch / refresh OSM island base set

```bash
python3 scripts/fetch_islands.py --cache
```

What it does:

- Queries Overpass for `place=island`, `place=islet`, `natural=island` across
  the UK + Ireland + Channel Is. bbox.
- Caches the raw response at `data/osm_raw.json`.
- Normalises each element, computes `lat`/`lng`, area where available, derives
  `nation` from a bbox lookup.
- Merges with `data/curated.json` — curated wins on conflict. Curated entries
  get matched to OSM IDs via name + 25 km proximity (`_haversine_km`).
- Writes `data/islands.json`.

Output: ~5,800 sea islands (most of the dataset).

## 2. Classify inland islands (Tier A + Tier B)

```bash
python3 scripts/classify_inland.py --cache
```

What it does:

- Queries Overpass for `natural=water` multipolygons (lakes, lochs, reservoirs)
  and key river ways across the UK + Ireland bbox. Caches at
  `data/water_raw.json` (~274 MB — keep cached).
- **Tier A**: for each water body, extracts every **inner ring**. Each named
  inner ring becomes an inland-island candidate. Smart parent-body selection:
  smallest containing body wins; lake preferred over river on tie.
- **Tier B**: for every island still typed `sea` after Tier A, runs a
  point-in-polygon test (Shapely STRtree → manual `polygon.contains(point)`)
  against the union of water-body polygons.
- Reclassifies existing islands (`type: sea → lake/river`) and merges discovered
  inner-ring geometries into existing entries that match on name + 1 km
  proximity.
- Writes:
  - `data/inland_classification_report.json` — audit trail by island id.
  - `data/islands.json` — updated in place.

See [`METHODOLOGY-INLAND.md`](METHODOLOGY-INLAND.md) for the full algorithm.

## 3. Discovery extension (Wikidata + per-river + cultural)

The discovery layer is **modular**. Each source has its own script (some still
inlined in `enrich_images.py` / `fetch_islands.py` — these will be split out
during the next refactor; see `NEXT-SESSION-PLAN.md`).

Currently produced candidate files (see `data/candidates_*.json`):

- `candidates_wikidata.json` — Wikidata Q-IDs of islands not in OSM.
- `candidates_thames.json` — Thames river-islands sweep.
- `candidates_crannogs.json` — Crannog stub set.
- `candidates_designations.json` — Statutory designations stub.

Each candidate set is merged into `data/islands.json` with `source` set to
the workstream name and a corresponding entry in
`data/discovery_ingestion_report.json`.

## 4. Image enrichment

```bash
python3 scripts/enrich_images.py
```

What it does:

- For each island with a `wikidata` Q-ID: fetch P18 (image property) via
  Wikidata SPARQL. Cache in `data/cache_wikidata.json`.
- Fallback for islands without P18: fetch the lead image from the Wikipedia
  article via the `pageimages` extension. Cache in
  `data/cache_pageimages.json`.
- For each image URL: fetch file metadata from Commons (license, author,
  source page URL). Cache in `data/cache_commons.json`.
- Build the `images[]` array on each island with full provenance. Mirror the
  primary image to top-level `image`.
- Writes `data/image_enrichment_report.json` with per-island outcome:
  `ok` / `dropped` / `suspect`.

**Politeness**: batched MediaWiki calls (50 per request), 1 rps SPARQL, a
contactable User-Agent. Re-running is safe and cheap thanks to the caches.

## 5. Verify (regression)

After each run, verify against [`VALIDATION.md`](VALIDATION.md):

```bash
python3 - <<'PY'
import json
d = {i["id"]: i for i in json.load(open("data/islands.json"))}
required = ["isle-of-skye", "devenish-island", "isle-of-wight", "achill-island"]
for k in required:
    i = d.get(k)
    print(k, "->", i["type"] if i else "MISSING", i.get("nation") if i else "")
PY
```

Then update [`STATE.md`](STATE.md) and append a [`SESSION-LOG.md`](SESSION-LOG.md)
entry.

## 5b. Regenerate `islands_index.json` (frontend first paint)

After **any** change to `data/islands.json`, refresh the slim map/list payload:

```bash
python3 scripts/build_islands_index.py
```

The browser loads `data/islands_index.json` first (~half the bytes of the full
dataset — long prose and image galleries omitted), then merges full records
from `islands.json` in place (`app.js` → `loadIslands`).

## 6. Preview

```bash
python3 -m http.server 8767
# open http://localhost:8767
```

(If 8767 is busy, pick any free port; check `STATE.md` for the current one.)

## Full rebuild from scratch (cold cache, ~hours)

```bash
rm -f data/osm_raw.json data/water_raw.json data/cache_*.json
python3 scripts/fetch_islands.py
python3 scripts/classify_inland.py
python3 scripts/enrich_images.py
```

Expect: ~30 min Overpass time, ~5 min classifier (after caches warm), ~30–60
min image enrichment depending on Wikimedia load. Always prefer `--cache` if
you only need to reprocess.
