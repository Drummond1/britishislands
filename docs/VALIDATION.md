# Validation set — regression spine

> A small, hand-curated set of islands whose properties **must remain correct**
> across pipeline runs. If any of these regress, the run is bad.

Use this checklist after every ingestion or enrichment run, before declaring
success.

## How to run

```bash
python3 - <<'PY'
import json
d = {i["id"]: i for i in json.load(open("data/islands.json"))}
expected = [
    # (id, type, nation, parentWaterBody.name or None)
    ("isle-of-skye",              "sea",   "Scotland",         None),
    ("isle-of-wight",             "sea",   "England",          None),
    ("isle-of-man",               "sea",   "Crown Dependency", None),
    ("lundy",                     "sea",   "England",          None),
    ("anglesey",                  "sea",   "Wales",            None),
    ("mull",                      "sea",   "Scotland",         None),
    ("rathlin",                   "sea",   "Northern Ireland", None),
    ("lewis-and-harris",          "sea",   "Scotland",         None),
    ("belle-isle-windermere",     "lake",  "England",          None),

    # OSM-id-keyed (stable across runs)
    ("osm-relation-380646",       "sea",   "Scotland",         None),  # Barra
    ("osm-relation-380670",       "sea",   "Scotland",         None),  # South Uist
    ("osm-relation-380685",       "sea",   "Scotland",         None),  # North Uist
    ("osm-relation-4619204",      "sea",   "Scotland",         None),  # Jura
    ("osm-relation-6045455",      "sea",   "Scotland",         None),  # Tiree
    ("osm-relation-6045364",      "sea",   "Ireland",          None),  # Achill
    ("osm-relation-3998376",      "lake",  "Northern Ireland", "Lower Lough Erne"),  # Devenish
    ("osm-relation-3512150",      "lake",  "Northern Ireland", "Lower Lough Erne"),  # Boa
    ("osm-way-26526918",          "lake",  "Ireland",          "Lough Leane"),       # Innisfallen
    ("osm-way-403472785",         "sea",   "England",          None),                # Wallasea
]
fails = 0
for id_, etype, enation, eparent in expected:
    i = d.get(id_)
    if not i:
        print(f"MISSING  {id_}")
        fails += 1
        continue
    parent = (i.get("parentWaterBody") or {}).get("name")
    ok = (i.get("type") == etype and i.get("nation") == enation and parent == eparent)
    print(f"{'OK   ' if ok else 'FAIL '} {id_:36s} type={i.get('type'):5s} nation={i.get('nation'):17s} parent={parent}")
    if not ok:
        fails += 1
print(f"\n{fails} failures out of {len(expected)}")
PY
```

## What the set covers

| Theme | Members |
|---|---|
| Largest sea islands per nation | Skye, Lewis & Harris, Mull, Anglesey, Isle of Wight, Isle of Man, Achill |
| Cross-nation balance | Scotland, England, Wales, NI, Ireland, Crown Dep |
| Inland edge cases | Belle Isle (Windermere) — lake; Devenish + Boa — multi-segment Lough Erne; Innisfallen — lake |
| Easy-to-mis-classify | Wallasea (sea, England — was occasionally tier-B-misclassified to estuary) |

## When to extend the set

Add to this list whenever:

- A bug fix touched a specific island — pin it here.
- A new ingestion source added a notable island — pin a representative.
- A schema field is added that needs regression coverage — add an expected
  value to the tuple.

Never remove an entry. If an island ceases to exist (boundary reclassification,
etc.), mark with `# RETIRED` and a date, but keep the row.

## Image regression

Image coverage is a moving target. The hard rule is **monotonic non-decrease**
during normal enrichment runs:

```bash
python3 - <<'PY'
import json
d = json.load(open("data/islands.json"))
print("with image:", sum(1 for i in d if i.get("images")))
PY
```

After an enrichment run, this count must be ≥ the previous run's count.
Record the value in [`STATE.md`](STATE.md) and [`SESSION-LOG.md`](SESSION-LOG.md).

## Sanity bounds

Reject the run if any of these is violated:

- Total islands < 6,000 or > 30,000 (current ~6,741).
- Any nation has 0 islands.
- Sea islands < 50% of total (sanity: we are a sea-island-heavy dataset).
- Curated `id`s (those in `data/curated.json`) all present.
- Any `images[i]` missing `license` or `sourcePageUrl`.
