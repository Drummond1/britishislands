#!/usr/bin/env python3
"""Read-only geosearch yield simulation (v3 vs v5 rules on cached Commons geo).

Writes data/geosearch_yield_simulation.json — does not mutate islands or caches.
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "geosearch_yield_simulation.json"

# ---------- v3-style helpers (substring, len>=3 variants) ----------

_NON_PHOTO_V3 = re.compile(
    r"(?:^|[_ \-])("
    r"flag|coat[_ \-]of[_ \-]arms|coat[_ \-]arms|arms[_ \-]of|"
    r"crest|emblem|seal|logo|badge|"
    r"location[_ \-]map|outline[_ \-]map|locator[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing|"
    r"chart|diagram|graph|plan[_ \-]of"
    r")",
    re.IGNORECASE,
)

_NON_PHOTO_V5 = re.compile(
    r"(?:^|[_ \-\(\[])("
    r"flag|coat[_ \-]of[_ \-]arms|crest|emblem|seal|logo|badge|"
    r"location[_ \-]map|outline[_ \-]map|locator[_ \-]map|"
    r"map[_ \-]of|map[_ \-]showing|chart|diagram|graph|plan[_ \-]of|"
    r"plat|plats|atlas|page[_ \-]?\d|court[_ \-]record|"
    r"dpla|loc\.gov|library[_ \-]of[_ \-]congress|"
    r"land[_ \-]grant|deed[_ \-]book|"
    r"engraving|woodcut|lithograph|"
    r"postage[_ \-]stamp|stamp[_ \-]of|"
    r"painting[_ \-]of|portrait[_ \-]of"
    r")",
    re.IGNORECASE,
)


def _canon(fname: str) -> str:
    if not fname:
        return ""
    if fname.startswith("File:"):
        fname = fname[len("File:") :]
    return fname.replace("_", " ")


def _looks_non_photo_v3(fname: str) -> bool:
    if not fname:
        return True
    if fname.lower().endswith((".svg", ".pdf", ".tif", ".tiff")):
        return True
    return bool(_NON_PHOTO_V3.search(fname))


def _looks_non_photo_v5(fname: str) -> bool:
    if not fname:
        return True
    if fname.lower().endswith((".svg", ".pdf", ".tif", ".tiff", ".gif")):
        return True
    return bool(_NON_PHOTO_V5.search(fname))


def _name_variants_v3(island: dict) -> list[str]:
    bag: set[str] = set()
    v = (island.get("name") or "").strip().lower()
    if v:
        bag.add(v)
        for stripped in (
            v.replace("isle of ", ""),
            v.replace("island", "").strip(),
            v.replace("'", "").replace("ʼ", ""),
        ):
            if stripped:
                bag.add(stripped)
    return [x for x in bag if len(x) >= 3]


def _mentions_v3(text: str, island: dict) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(v in t for v in _name_variants_v3(island))


def _strip_diacritics(s: str) -> str:
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


_NAME_WORDBOUND_CACHE: dict[str, re.Pattern] = {}


def _name_regex(variant_ascii: str) -> re.Pattern:
    pat = _NAME_WORDBOUND_CACHE.get(variant_ascii)
    if pat is None:
        escaped = re.escape(variant_ascii)
        escaped = escaped.replace(r"\'", "[']?")
        pat = re.compile(rf"(?:^|[^a-z0-9]){escaped}(?:[^a-z0-9]|$)", re.IGNORECASE)
        _NAME_WORDBOUND_CACHE[variant_ascii] = pat
    return pat


def _name_variants_v5(island: dict) -> list[str]:
    bag: set[str] = set()
    raw = (island.get("name") or "").strip()
    if raw:
        bag.add(raw.lower())
        for ap in ("'", "\u2019", ""):
            bag.add(raw.lower().replace("'", ap).replace("\u2019", ap))
        low = raw.lower()
        if low.startswith("isle of "):
            tail = low[len("isle of ") :].strip()
            if len(tail) >= 5 and (
                " " in tail
                or any(
                    tail.endswith(s)
                    for s in ("skerry", "holm", "eilean", "ynys", "inis", "eyot", "ait")
                )
            ):
                bag.add(tail)
    for nm in (island.get("names") or {}).values():
        nm = (nm or "").strip().lower()
        if nm and len(nm) >= 4:
            bag.add(nm)
    return [v for v in bag if len(v) >= 5]


def _mentions_v5(text: str, variants: list[str]) -> bool:
    if not text:
        return False
    ascii_text = _strip_diacritics(text)
    for v in variants:
        v_ascii = _strip_diacritics(v)
        if _name_regex(v_ascii).search(ascii_text):
            return True
    return False


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _v3_search_radius_m(island: dict, max_dist_m: int = 800) -> int:
    area = island.get("areaKm2") or 0.0
    radius = max_dist_m
    if area and area < 0.05:
        radius = max(max_dist_m, 1200)
    elif area and area < 0.2:
        radius = max(max_dist_m, 1000)
    return radius


def _geo_key(lat: float, lon: float, radius_m: int) -> str:
    return f"{lat:.4f},{lon:.4f};{radius_m}"


def _has_license(meta: dict) -> bool:
    lic = (meta.get("license") or "").strip()
    return bool(lic) and "fair use" not in lic.lower()


def _normalize_hits(raw: list) -> list[dict]:
    out = []
    for h in raw:
        title = h.get("title") or ""
        dist = h.get("dist_m")
        if dist is None:
            dist = h.get("dist")
        out.append(
            {
                "title": _canon(title),
                "lat": h.get("lat"),
                "lon": h.get("lon"),
                "dist_m": dist,
            }
        )
    return out


def _pick_v3(island: dict, hits: list[dict], cm: dict) -> dict | None:
    if not hits:
        return None
    name_hits = [
        h
        for h in hits
        if not _looks_non_photo_v3(h["title"])
        and _mentions_v3(h["title"], island)
    ]
    pool = name_hits or [
        h
        for h in hits
        if not _looks_non_photo_v3(h["title"]) and (h.get("dist_m") or 1e9) <= 200
    ]
    if not pool:
        return None
    pool.sort(
        key=lambda h: (
            0 if _mentions_v3(h["title"], island) else 1,
            h.get("dist_m") or 1e9,
        )
    )
    for h in pool[:8]:
        fname = h["title"]
        m = cm.get(fname, {})
        if _has_license(m):
            return {
                "file": fname,
                "name_match": _mentions_v3(fname, island) or _mentions_v3(m.get("caption", ""), island),
                "dist_m": h.get("dist_m"),
                "rule": "name" if _mentions_v3(fname, island) else "proximity_200m",
            }
    return None


def _pick_v5(
    island: dict,
    hits: list[dict],
    cm: dict,
    radius_m: int,
    lat: float,
    lon: float,
) -> dict | None:
    if not hits:
        return None
    max_dist_m = radius_m * 1.05
    variants = _name_variants_v5(island)
    keep = [h for h in hits if not _looks_non_photo_v5(h.get("title", ""))]
    for h in keep[:8]:
        fname = h["title"]
        m = cm.get(fname, {})
        if not _has_license(m):
            continue
        if not (_mentions_v5(fname, variants) or _mentions_v5(m.get("caption", ""), variants)):
            continue
        try:
            dist_m = _haversine_m(
                lat,
                lon,
                float(h.get("lat") or 0),
                float(h.get("lon") or 0),
            )
        except Exception:
            dist_m = h.get("dist_m") or 1e9
        if dist_m > max_dist_m:
            continue
        return {
            "file": fname,
            "dist_m": round(dist_m, 1),
            "rule": "name_and_distance",
        }
    return None


def main() -> int:
    islands = json.loads((DATA / "islands.json").read_text())
    geo = json.loads((DATA / "cache_commons_geo.json").read_text())
    cm = json.loads((DATA / "cache_commons.json").read_text())
    wd_cache = {}
    if (DATA / "cache_wikidata.json").exists():
        wd_cache = json.loads((DATA / "cache_wikidata.json").read_text())

    def has_image(i: dict) -> bool:
        return bool(i.get("images") or i.get("image"))

    def is_named(i: dict) -> bool:
        n = (i.get("name") or "").strip()
        return len(n) >= 2 and not n.lower().startswith("unnamed")

    pending = [i for i in islands if not has_image(i) and is_named(i)]
    total = len(islands)
    with_img = sum(1 for i in islands if has_image(i))

    radii_check = (500, 800, 1000, 1200, 1500)
    cache_radius_counts: dict[str, int] = {}
    for k in geo:
        if ";" in k:
            cache_radius_counts[k.split(";", 1)[1]] = (
                cache_radius_counts.get(k.split(";", 1)[1], 0) + 1
            )

    stats = {
        "pending_named": len(pending),
        "cache_key_500": 0,
        "cache_key_1500": 0,
        "cache_key_any_radius": 0,
        "cache_key_v3_radius": 0,
        "v3_would_adopt": 0,
        "v5_500_would_adopt": 0,
        "v5_1500_would_adopt": 0,
        "v3_only": 0,
        "v5_500_only": 0,
        "both_v3_and_v5_500": 0,
        "neither": 0,
    }
    examples_v3_only: list[dict] = []
    examples_v5_only: list[dict] = []
    diag = {
        "pendingWith1500CacheNonEmpty": 0,
        "anyV5NameMatchIn1500Hits": 0,
        "anyV3NameMatchIn1500Hits": 0,
    }

    for isl in pending:
        lat, lon = isl.get("lat"), isl.get("lng")
        if lon is None:
            lon = isl.get("lon")
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)

        key500 = _geo_key(lat, lon, 500)
        key1500 = _geo_key(lat, lon, 1500)
        r_v3 = _v3_search_radius_m(isl)
        key_v3 = _geo_key(lat, lon, r_v3)

        hits500 = _normalize_hits(geo.get(key500, []))
        hits1500 = _normalize_hits(geo.get(key1500, []))
        hits_v3 = _normalize_hits(geo.get(key_v3, []))

        if hits1500:
            diag["pendingWith1500CacheNonEmpty"] += 1
            variants5 = _name_variants_v5(isl)
            for h in hits1500[:50]:
                fn = h["title"]
                m = cm.get(fn, {})
                if _mentions_v5(fn, variants5) or _mentions_v5(m.get("caption", ""), variants5):
                    diag["anyV5NameMatchIn1500Hits"] += 1
                    break
            for h in hits1500[:50]:
                if _mentions_v3(h["title"], isl):
                    diag["anyV3NameMatchIn1500Hits"] += 1
                    break

        if key500 in geo:
            stats["cache_key_500"] += 1
        if key1500 in geo:
            stats["cache_key_1500"] += 1
        if any(_geo_key(lat, lon, r) in geo for r in radii_check):
            stats["cache_key_any_radius"] += 1
        if key_v3 in geo:
            stats["cache_key_v3_radius"] += 1

        # v5@500: prefer ;500 cache, else filter ;1500 hits to 500m
        pool500 = hits500 if hits500 else [
            h for h in hits1500 if (h.get("dist_m") or 1e9) <= 500
        ]
        pick_v3 = _pick_v3(isl, hits_v3 or hits1500 or hits500, cm)
        pick_v5_500 = _pick_v5(isl, pool500, cm, 500, lat, lon)
        pick_v5_1500 = _pick_v5(isl, hits1500, cm, 1500, lat, lon)

        if pick_v3:
            stats["v3_would_adopt"] += 1
        if pick_v5_500:
            stats["v5_500_would_adopt"] += 1
        if pick_v5_1500:
            stats["v5_1500_would_adopt"] += 1

        if pick_v3 and pick_v5_500:
            stats["both_v3_and_v5_500"] += 1
        elif pick_v3:
            stats["v3_only"] += 1
            if len(examples_v3_only) < 15:
                examples_v3_only.append(
                    {"id": isl["id"], "name": isl.get("name"), "v3": pick_v3}
                )
        elif pick_v5_500:
            stats["v5_500_only"] += 1
            if len(examples_v5_only) < 15:
                examples_v5_only.append(
                    {"id": isl["id"], "name": isl.get("name"), "v5": pick_v5_500}
                )
        elif not pick_v3 and not pick_v5_500:
            stats["neither"] += 1

    # v2 wikidata pending analysis
    import re as re_mod

    pending_wd = [
        i
        for i in islands
        if not has_image(i)
        and re_mod.match(r"^Q\d+$", (i.get("wikidata") or "").strip())
    ]
    wd_not_cached = []
    wd_no_p18 = []
    wd_has_p18_untried = []
    for i in pending_wd:
        q = i["wikidata"].strip()
        if q not in wd_cache:
            wd_not_cached.append(i["id"])
            continue
        fn = (wd_cache[q].get("filename") or "").strip()
        if fn:
            wd_has_p18_untried.append({"id": i["id"], "qid": q, "filename": fn})
        else:
            wd_no_p18.append(i["id"])

    target_6000 = 6000
    gap = target_6000 - with_img
    # Upper bound if geosearch adds all simulated (not independent of other sources)
    geo_ceiling = with_img + stats["v5_500_would_adopt"]

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "method": "read-only dry simulation on cache_commons_geo.json + cache_commons.json",
        "dataset": {
            "totalIslands": total,
            "withImage": with_img,
            "withoutImage": total - with_img,
            "pendingNamedWithoutImage": len(pending),
            "target6000Gap": gap,
        },
        "cacheCommonsGeo": {
            "totalKeys": len(geo),
            "keysByRadiusSuffix": dict(
                sorted(cache_radius_counts.items(), key=lambda x: -x[1])
            ),
            "note": "No ;500 keys in cache at simulation time; v5@500m uses ;1500 hits filtered to dist<=500m when ;500 absent.",
        },
        "rulesCompared": {
            "v3_commons_geosearch": {
                "searchRadiusM": "800 default; 1000 if area<0.2 km²; 1200 if area<0.05 km²",
                "adoption": "name substring in filename (len>=3 variants) OR closest photo within 200m; license required",
                "nameMatching": "substring (_mentions_island), variants >=3 chars",
            },
            "v5_geosearch_wide_500m": {
                "searchRadiusM": 500,
                "adoption": "word-boundary name match in filename OR caption AND haversine distance <= 525m (500×1.05); license required",
                "nameMatching": "strict word-boundary (_mentions), variants >=5 chars",
            },
        },
        "simulationOnPendingNamed": stats,
        "diagnostics": diag,
        "incrementalYield": {
            "v3GeosearchFromCache": stats["v3_would_adopt"],
            "v5Geosearch500mFromCache": stats["v5_500_would_adopt"],
            "v5Geosearch1500mStrictFromCache": stats["v5_1500_would_adopt"],
            "v3OnlyNotV5_500": stats["v3_only"],
            "v5_500OnlyNotV3": stats["v5_500_only"],
        },
        "v2WikidataPending": {
            "pendingWithQid": len(pending_wd),
            "qidNotInCacheWikidata": len(wd_not_cached),
            "inCacheNoP18": len(wd_no_p18),
            "inCacheWithP18StillNoImage": len(wd_has_p18_untried),
            "sampleP18Untried": wd_has_p18_untried[:10],
            "note": "v2 only helps islands with Wikidata P18; 0 pending had cached P18 at run time.",
        },
        "examples": {
            "v3OnlyNotV5_500": examples_v3_only,
            "v5_500OnlyNotV3": examples_v5_only,
        },
        "recommendation": {},
    }

    # Build recommendation text
    pct_named = (
        round(100 * stats["v5_500_would_adopt"] / max(1, len(pending)), 1)
    )
    conf_90 = False
    rec_lines = []
    if geo_ceiling < target_6000:
        rec_lines.append(
            f"Cached geosearch alone cannot reach 6,000 images "
            f"(ceiling ~{geo_ceiling:,} = current {with_img:,} + {stats['v5_500_would_adopt']} simulated)."
        )
    rec_lines.append(
        f"Among {len(pending):,} pending named islands, cached geo would adopt "
        f"{stats['v5_500_would_adopt']} under v5@500m rules ({pct_named}%) vs "
        f"{stats['v3_would_adopt']} under v3 rules."
    )
    rec_lines.append(
        "v2 Wikidata P18 has no remaining yield on pending Q-IDs (987 cached without P18)."
    )
    if gap > 0:
        need = gap
        rec_lines.append(
            f"Need +{need:,} images for 6,000; plan text-search + OSM tags + fresh geosearch API "
            f"(cache lacks ;500 keys) rather than geosearch-only."
        )
    # 90% confidence needs ~2,383 new images; cached geo + v2 P18 << gap
    conf_90 = False
    report["recommendation"] = {
        "hit6000With90PctConfidence": conf_90,
        "summary": " ".join(rec_lines),
        "suggestedOrder": [
            "Run v5 with --geosearch-radius 500 after populating cache (or accept 1500 cache + 500m filter)",
            "Continue commons-text-search (in flight)",
            "v3 osm-image-tag + commons-category for Q-ID islands",
            "Do not re-run v2 bulk SPARQL expecting P18 gains on current pending set",
        ],
    }

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("dataset", "simulationOnPendingNamed", "v2WikidataPending", "recommendation")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
