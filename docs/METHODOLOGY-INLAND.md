# Methodology — inland island classifier (Tier A + Tier B)

Deep-dive into how `scripts/classify_inland.py` decides whether an island is
in the sea, a lake, or a river — and how it discovers inland islands that
aren't yet in the dataset.

## Why this is hard

OpenStreetMap models islands in two very different ways:

1. As standalone `place=island` / `natural=island` polygons or nodes. These
   are easy to find but their relationship to a surrounding **water body** is
   not declared.
2. As **inner rings** of a `natural=water` multipolygon. The water body owns
   the geometry of the island as a hole; there is no "island" element at all.

Most lake and river islands are modelled by (2), often without any name on
the inner ring. We need:

- For islands found via (1), the **type** (sea/lake/river) and **parent water
  body**. This is Tier B.
- New islands found via (2). This is Tier A.

## Tier A — inner-ring extraction

Inputs:

- Cached water-body Overpass response at `data/water_raw.json` (~274 MB).
  Contains every `natural=water` multipolygon in the UK + IE bbox, with the
  member ways' geometry inline.

Algorithm:

1. For each water-body relation:
   - Classify the body via `classify_body()` → `lake` / `river` / `sea`.
     Sea-tagged or tidal-tagged bodies are dropped (we don't want sea-loch
     islands miscounted).
   - Determine its `subtype` (`reservoir`, `canal`, `estuary`, `oxbow`, …) via
     `subtype_for()`.
   - Assemble the **outer polygon** via `assemble_water_polygon()`. This uses
     `shapely.ops.polygonize` on the union of outer ways — necessary because
     bodies like Lough Erne are 119 separate way segments that must be stitched
     before they form a valid polygon.
   - Extract each **inner ring** (the holes). Each inner ring is a candidate
     inland island.
2. For each candidate inner ring:
   - Skip if **unnamed** — too noisy. ~5,400 unnamed inner-ring features
     exist; almost all are tiny untracked features and adding them as
     anonymous "islands" pollutes the dataset.
   - Skip if `nation_for(centroid)` is not in `{Scotland, England, Wales,
     Northern Ireland, Ireland, Crown Dependency}`. Drops French/Faroese
     bleed-through from the bbox edges.
   - Find the **most specific** parent body if the inner ring is contained
     by multiple water-body candidates: smallest area wins; lake beats
     river on tie.
   - **Match against existing islands** within 1 km that share a name (via
     `_name_key` normalisation). If matched → merge the OSM
     way/relation IDs into the existing entry rather than creating a duplicate.
     If no match → add a new entry with `source: "osm-inland"`,
     `classification: { source: "tier-a", confidence: "high" }`.

Why "high" confidence: the geometry IS the water body's hole. There is no
spatial ambiguity.

## Tier B — point-in-polygon for legacy sea-typed islands

After Tier A, any island still typed `sea` is run through point-in-polygon
testing:

1. Build an STRtree of all assembled water-body polygons.
2. For each `sea` island: candidate = STRtree.query(point, predicate='intersects').
3. For each candidate: manually test `polygon.contains(point)`. Take the
   smallest containing polygon (most specific body) — same tiebreaker as Tier A.
4. Reclassify the island accordingly and set `parentWaterBody`.

Confidence is:

- **`high`** when the island sits clearly inside the polygon (centroid > 10 m
  from the boundary).
- **`medium`** when within 10 m — could be a coastal/boundary noise case.
- **`low`** otherwise; the algorithm doesn't reclassify these but flags them
  in the report.

## Why polygonize is necessary

A naive `Polygon(way.coords)` per outer way of Lough Erne yields 119 tiny
non-closed polygons. None of them individually contain Devenish Island's
centroid. We need to stitch them into one big polygon before the
point-in-polygon test makes any sense. `shapely.ops.polygonize(unary_union(...))`
gives us exactly that, even when the outer is a complex multi-segment ring.

This fix is why Devenish and Boa now classify correctly as `lake`.

## Sea-loch handling (subtle)

A *Scottish sea loch* (Loch Linnhe, Loch Duich, …) is open to the sea and
**not** typically modelled as `natural=water` in OSM. So sea-loch islands
never enter the Tier A/B pipeline. They stay typed `sea`. This is the
correct behaviour: a sea loch is sea.

If, in future, OSM starts modelling sea lochs as `natural=water` + `salt=yes`,
the existing salt/tidal filter in `classify_body()` will already exclude them.

## Subtype assignment

`subtype_for(body_tags)` derives `subtype` from the parent body's tags:

| Subtype | When |
|---|---|
| `reservoir` | `water=reservoir` |
| `canal` | `waterway=canal` (river-type) |
| `estuary` | `estuary=yes` or known estuary name |
| `oxbow` | `water=oxbow` |
| `crannog` | Hand-tagged via the crannog discovery workstream |
| (null) | Otherwise |

Subtype is carried on the **island** record, not the parent. It describes the
context: e.g. "an island in a reservoir" → `type: lake`, `subtype: reservoir`.

## Outputs

| Artefact | Purpose |
|---|---|
| `data/inland_classification_report.json` | Per-island audit, keyed by `id`. For each island it records the `tier`, the `parentWaterBody` chosen, all candidate parents considered, and the reasoning. |
| `data/islands.json` (mutated) | `type`, `subtype`, `parentWaterBody`, `classification` fields updated/added. |
| `data/water_raw.json` (cache) | Raw Overpass water-body response. |

## Re-run discipline

The classifier is **idempotent**: rerunning on the same `data/islands.json`
should produce the same result. If it doesn't, suspect:

- A schema change that hasn't been propagated.
- A change to `_name_key` or `_haversine_km` thresholds.
- An expanded/contracted water-body cache.

Always diff before/after via `git diff data/islands.json` (or by comparing the
`islands.json.before-ingest` backup).

## Open work

- **Cultural names on inner rings**: many inner rings have Gaelic/Welsh/Irish
  names tagged only on the way, not as a separate Wikidata item. We should
  carry these into the future `names: { gd, cy, ga, … }` schema field rather
  than dropping non-English names.
- **River island catch-up**: many river islands are tagged as standalone
  ways, not inner rings, and currently fall to Tier B. The Thames sweep is
  the first per-river deep-dive; extend to Tay, Severn, Bann, Shannon next.
- **Confidence calibration**: the 10 m boundary threshold for Tier B is a
  heuristic. We should sample-validate against OS OpenMap.
