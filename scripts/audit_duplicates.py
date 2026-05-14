#!/usr/bin/env python3
"""Find candidate duplicate-island pairs in ``data/islands.json``.

Two records are flagged as candidate duplicates when **all** of:

  * Great-circle distance ≤ ``--max-km`` (default 0.5 km), AND
  * Name similarity ≥ ``--min-name`` (default 0.75 token-set Jaccard),
    after diacritic + punctuation normalisation, OR identical normalised
    names regardless of similarity threshold.

Output is a human-reviewable JSON report; nothing is mutated.

Usage::

    python3 scripts/audit_duplicates.py
    python3 scripts/audit_duplicates.py --max-km 0.3 --min-name 0.8

Output::

    data/duplicate_candidates_report.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
REPORT = DATA / "duplicate_candidates_report.json"


def normalise(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower())
    return re.sub(r"\b(island|isle|isles|eilean|ynys|oilean|holm|holm|skerry)\b", "",
                  s).strip()


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-km", type=float, default=0.5)
    ap.add_argument("--min-name", type=float, default=0.75)
    args = ap.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pts = []
    for i, isl in enumerate(islands):
        if not isinstance(isl, dict):
            continue
        lat = isl.get("lat")
        lng = isl.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        pts.append((i, lat, lng, normalise(isl.get("name") or ""), isl.get("name") or "",
                    isl.get("id") or ""))
    print(f"checking {len(pts)} islands for near-neighbour duplicates within "
          f"{args.max_km} km", file=sys.stderr)

    # Spatial bucketing for performance.
    BUCKET = 0.02  # ~2.2 km at the equator, finer near poles, fine enough for our threshold
    buckets: dict[tuple[int,int], list[int]] = {}
    for j, (idx, lat, lng, nname, name, iid) in enumerate(pts):
        key = (int(lat / BUCKET), int(lng / BUCKET))
        buckets.setdefault(key, []).append(j)

    pairs = []
    seen: set[tuple[int, int]] = set()
    for j, (idx, lat, lng, nname, name, iid) in enumerate(pts):
        bkx = int(lat / BUCKET)
        bky = int(lng / BUCKET)
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidates.extend(buckets.get((bkx+dx, bky+dy), []))
        for k in candidates:
            if k <= j:
                continue
            key = (j, k)
            if key in seen:
                continue
            seen.add(key)
            idx2, lat2, lng2, nn2, name2, iid2 = pts[k]
            d = haversine_km(lat, lng, lat2, lng2)
            if d > args.max_km:
                continue
            # Exact normalised name OR Jaccard ≥ threshold
            sim = 1.0 if (nname and nname == nn2) else jaccard(nname, nn2)
            if sim < args.min_name:
                continue
            pairs.append({
                "distanceKm": round(d, 4),
                "nameSimilarity": round(sim, 3),
                "a": {"id": iid, "name": name, "lat": lat, "lng": lng,
                      "nation": islands[idx].get("nation")},
                "b": {"id": iid2, "name": name2, "lat": lat2, "lng": lng2,
                      "nation": islands[idx2].get("nation")},
            })

    pairs.sort(key=lambda p: (p["distanceKm"], -p["nameSimilarity"]))
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.utcnow().isoformat(timespec="seconds"),
        "maxKm": args.max_km,
        "minNameSim": args.min_name,
        "candidatePairs": len(pairs),
        "pairs": pairs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"flagged {len(pairs)} candidate duplicate pairs → "
          f"{REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
