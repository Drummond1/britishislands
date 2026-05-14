# Measurements — sources, methods, and confidence

How we calculate every island's `areaKm2` and `highestPointM`, where the
data comes from, what licences cover it, and how confident we are.

Both fields follow the same contract:

* Publish a number only when the **method** is independently accurate to
  within ~ 2 %, or
* Publish a labelled **estimate** (elevation only) when we have lower-
  confidence evidence, or
* Set the value to `null` with `areaConfidence`/`highestPointConfidence`
  = `"n/a"` when we have no usable evidence.

Every figure on the details page is rendered next to its **confidence**
and **source**.

---

## Area (`areaKm2`)

### Calculation

Geodesic integration on the WGS84 ellipsoid:

```python
from pyproj import Geod
GEOD = Geod(ellps="WGS84")
area_m2, perimeter_m = GEOD.polygon_area_perimeter(lngs, lats)
```

`pyproj.Geod.polygon_area_perimeter` implements Karney's exact
algorithm for area on a geoid surface ([reference](https://geographiclib.sourceforge.io/C++/doc/classGeographicLib_1_1Geodesic.html)).
The method itself is sub-0.01 %-accurate — far better than the 2 % bar.
The uncertainty in our published number is therefore entirely the
accuracy of the **polygon**, not the maths.

### Polygon sources, in priority order

| Step  | Source | When used |
|-------|--------|-----------|
| **B** | The island's own `osm-way-<id>` or `osm-relation-<id>` from OpenStreetMap, OR the OSM way ID embedded in a hand-curated `<slug>-w<digits>` ID. Fetched in batches from Overpass. | The canonical case. Used for ~5,600 islands. |
| **C** | The OSM way/relation tagged `wikidata=Q…`, looked up over Overpass for `wd-Q…` islands. | ~60 islands. |
| **A** | Smallest non-mainland OSM coastline polygon containing the centroid, taken from our local cache of polygonised `natural=coastline` ways (`data/land_polygons.pickle`). | Hand-curated main-island IDs only (e.g. `mainland-orkney`, `isle-of-skye`). Restricted to prevent islets inheriting their host island's polygon. |

### Cross-check

Where the island has a Wikidata Q-ID, we fetch
**[Wikidata property P2046](https://www.wikidata.org/wiki/Property:P2046)
(area)** and compare it with our geodesic value. Wikidata P2046 is
**not** a gate — it has many unit-tagging errors (hectares marked as
km², acres marked as km², etc.). We use it as a sanity check and
recognise common unit confusions explicitly:

* ratio ≈ 100× → WD value is hectares mis-tagged as km² (still a match)
* ratio ≈ 1000× → WD value is m² mis-tagged as km²
* ratio ≈ 300× → WD value is acres mis-tagged as km²

Honest disagreements > 25 % downgrade the entry to `medium` confidence
and surface a flag in `data/area_audit.json`.

### Underlying data and licensing

| Source | What it is | Licence | Attribution |
|--------|------------|---------|-------------|
| **OpenStreetMap** | The polygon itself (`natural=coastline` ways, `place=island` ways/relations, `place=islet`, `landuse=basin` island holes). The British Isles have been mapped from licensed aerial imagery; coastline is typically aligned at mean-high-water. | ODbL 1.0 | "© OpenStreetMap contributors" |
| **Wikidata P2046** | The cross-check `area` claim, sourced by Wikidata editors usually from Wikipedia, the Statistics Office, or government cadastral data. | CC0 1.0 | No attribution required, but cited in the audit. |
| **pyproj 3.6.1** | Karney geodesic algorithm. | MIT-style PROJ licence | – |
| **shapely 2.x** | Polygon manipulation. | BSD-3 | – |

### Confidence levels

| `areaConfidence` | Rule |
|------------------|------|
| `high`   | Polygon resolved AND either no Wikidata to compare, or WD within 25 %, or WD ratio matches a known unit mis-tag. |
| `medium` | Tiny islet (< 0.001 km², < 8 polygon vertices) OR WD disagrees by > 25 % with no unit-error explanation. |
| `n/a`    | No polygon resolvable; or only Wikidata P2046 available (i.e. nothing we can independently verify against). |

### Coverage (latest run, 2026-05-12)

5,581 high (82.4 %) · 236 medium (3.5 %) · 959 n/a (14.2 %).

Spot-checks against canonical references all sit inside 2 %:
Isle of Skye 1,636.1 km² (vs 1,656; Δ 1.2 %),
Isle of Man 570.5 (vs 572; Δ 0.3 %),
Achill 148.3 (vs 148; Δ 0.2 %),
Eel Pie Island 0.038 (vs 0.038; Δ 0.1 %).

---

## Highest point (`highestPointM`, `highestPointName`)

### Sources, in priority order

| Step | Source | When used |
|------|--------|-----------|
| **1** | OSM nodes tagged `natural=peak` with `ele=*`, restricted to those whose coordinates fall inside the island's polygon. Take the one with the highest `ele`. | The canonical case. 241 islands. |
| **2** | **[Wikidata property P2044](https://www.wikidata.org/wiki/Property:P2044)** (elevation above sea level), with unit conversion (metres / feet / kilometres handled). | Fallback when no OSM peak sits inside the polygon. 45 islands. |
| **3** | Pre-existing hand-curated value retained from the dataset. | 7 islands. |

### Underlying data and licensing

OSM `ele=*` tags in the British Isles are predominantly derived from
the following authoritative datasets (re-tagged into OSM under ODbL by
contributors):

| Coverage | Underlying source | Notes |
|----------|-------------------|-------|
| England, Scotland, Wales | **[Ordnance Survey](https://www.ordnancesurvey.co.uk/)** — primarily OS OpenData spot heights, OS Terrain 50, and Geograph-verified surveys. | Triangulation-station heights are accurate to ±0.1 m; spot heights from OS Terrain to ±1 m. |
| Republic of Ireland | **[Ordnance Survey Ireland (OSi)](https://www.osi.ie/)** spot heights and Discovery Series maps. | Discovery Series elevations are typically rounded to whole metres. |
| Northern Ireland | **[Ordnance Survey of Northern Ireland (OSNI)](https://www.spatialni.gov.uk/)** Discoverer Series. | – |
| Isle of Man | Crown copyright [DEFA](https://www.gov.im/categories/business-and-industries/iomgis/) survey data. | – |
| Channel Islands | **[Digimap Guernsey](https://www.digimap.gg/)** / States of Jersey Geomatics data. | – |

| Source                 | Licence                                | Attribution         |
|------------------------|----------------------------------------|---------------------|
| OpenStreetMap          | ODbL 1.0                               | "© OSM contributors" |
| Ordnance Survey (via OSM) | OS OpenData / Public Sector Licence (passed through OSM under ODbL) | Implicit through OSM credit |
| Wikidata P2044         | CC0 1.0                                | – |

### Confidence levels

| `highestPointConfidence` | Rule |
|--------------------------|------|
| `high`     | OSM peak found inside polygon. Cross-validated by WD where available (within 5 m or 5 % keeps `high`; manual fallback also high). |
| `estimate` | Wikidata P2044 only, OR OSM/WD disagree by > 5 m **and** > 5 %. UI labels these clearly. |
| `n/a`      | No peak inside the polygon and no Wikidata elevation. |

### Why the high `n/a` rate (95.7 %)?

The dataset includes 6,776 islands; only ~ 300 of them are large enough
or prominent enough to have an OSM-tagged `natural=peak` *with*
`ele=*`. Most entries are small skerries, river islets, crannogs, or
flat sand-bar islands without a named summit. For these the honest
answer is `n/a` — we don't fabricate a value.

A future enhancement is **DEM sampling** — pulling SRTM 1-arc-sec, OS
Terrain 50, or the EU Copernicus DEM and finding the maximum-elevation
cell inside each polygon. That would close the gap to ~ 100 %. It's
queued in [`QUEUE.md`](QUEUE.md) but requires shipping a DEM bundle
(~200 MB compressed for the British Isles).

### Coverage (latest run, 2026-05-12)

239 high · 54 estimate · 6,483 n/a. Top 12 read as a who's-who of
British and Irish summits — Ben Nevis 1,345 m, Carrauntoohil 1,039,
Sgùrr Alasdair 992, Ben More 966, Goat Fell 874, Askival 812, An
Cliseam 799, Beinn an Òir 785, Croaghaun 688, Snaefell 621, Beinn
Mhòr 620, Sgùrr Mòr 494 — every value agreeing with canonical
references to the metre.

---

## Reproducing the calculations

```bash
# Areas
python3 scripts/compute_island_areas.py --fetch-osm --fetch-wd --apply

# Heights
python3 scripts/compute_island_highpoints.py --fetch --apply
```

Both scripts cache fetched data under `data/cache_*.json` so subsequent
runs are fast. Full per-island evidence (each computed value vs
Wikidata, the OSM way/peak that was used, deltas, notes) is written to
[`data/area_audit.json`](../data/area_audit.json) and
[`data/highpoint_audit.json`](../data/highpoint_audit.json).

## Citation

When citing these numbers in publications or apps, please credit:

> © OpenStreetMap contributors (ODbL 1.0). Cross-checked against
> Wikidata (CC0 1.0). Geodesic areas computed with pyproj/GeographicLib.

For media use of OS-derived `ele` tags, refer also to the
[OS OpenData licence](https://www.ordnancesurvey.co.uk/licensing).

---

## Related measurements (2026-05-13 enrichments)

The 2026-05-13 enrichment workstream (see
[`SCHEMA-ENRICHMENTS-2026-05-13.md`](SCHEMA-ENRICHMENTS-2026-05-13.md))
adds three further measurement-style fields, each with their own
source / confidence / attribution / fetchedAt quad:

* **`hillsOn[]`** — DoBIH (CC-BY 4.0) hill classifications joined to
  the island by point-in-polygon. `confidence: high` when the hill
  is in DoBIH **and** PIP succeeds. See
  `scripts/ingest_hills_dobih.py`.
* **`geology.bedrock` / `geology.superficial`** — BGS DigMapGB-625
  (OGL v3.0). Resolved by WMS `GetFeatureInfo` at island centroid
  against the 1:625K bedrock + superficial layers. GB-only;
  `confidence: n/a` outside the BGS extent. See
  `scripts/ingest_geology_bgs.py`.
* **`highestPointM`** — augmented (not replaced) by `hillsOn[0]`
  when present: the highest classified hill on the island provides
  a corroborating elevation. The existing methodology in §2 above
  remains the canonical source for `highestPointM`.

See [`DATA-SOURCES.md`](DATA-SOURCES.md) for the licence /
attribution / refresh cadence of each source.
