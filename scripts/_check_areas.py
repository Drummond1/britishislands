#!/usr/bin/env python3
"""Quick read-only diagnostics for area_audit.json."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
audit = json.load(open(ROOT / "data/area_audit.json"))
islands = json.load(open(ROOT / "data/islands.json"))
by_id = {i["id"]: i for i in islands}

have = [r for r in audit if r["computedAreaKm2"]]
have.sort(key=lambda r: r["computedAreaKm2"], reverse=True)

print("--- Top 30 by computed geodesic area ---")
print(f"{'Rank':>4}  {'Computed':>10}  {'Existing':>10}  {'Type':<5}  Name")
print("-" * 80)
for i, r in enumerate(have[:30], 1):
    cur = r.get("currentAreaKm2")
    cur_s = f"{cur:>10.1f}" if isinstance(cur, (int, float)) else "       --"
    isl = by_id.get(r["id"]) or {}
    typ = isl.get("type", "?")
    name = r["name"] or "(no name)"
    print(f"{i:>4}  {r['computedAreaKm2']:>10,.1f}  {cur_s}  {typ:<5}  {name}")

print()
print("--- Coverage by island type (Step A only) ---")
covered = Counter()
total = Counter()
for r in audit:
    isl = by_id.get(r["id"])
    if not isl:
        continue
    t = isl.get("type", "?")
    total[t] += 1
    if r["computedAreaKm2"] is not None:
        covered[t] += 1
for t in sorted(total):
    pct = 100 * covered[t] / total[t] if total[t] else 0
    print(f"  {t:8s}  {covered[t]:>5,} / {total[t]:>5,}  ({pct:>5.1f}%)")

print()
print("--- Spot-check well-known islands ---")
TARGETS = {
    "Isle of Skye": 1656,
    "Lewis and Harris": 2179,
    "Isle of Man": 572,
    "Anglesey": 715,
    "Mainland, Shetland": 967,
    "Mull": 875,
    "Islay": 619,
    "Mainland, Orkney": 523,
    "Arran": 432,
    "Achill Island": 146,
    "Isle of Wight": 380,
    "Holy Island, Northumberland": 4,
    "Iona": 8.77,
    "Bryher": 1.32,
}
# Build name index across audit
for target, expected in TARGETS.items():
    hits = [r for r in audit if (r["name"] or "").lower() == target.lower()]
    if not hits:
        # fuzzier - contains
        hits = [r for r in audit if target.lower() in (r["name"] or "").lower()]
    if not hits:
        print(f"  {target:<28s}  → not found")
        continue
    for r in hits[:3]:
        comp = r["computedAreaKm2"]
        delta = f"{100 * abs(comp - expected) / expected:+.1f}%" if comp else "  -- "
        print(f"  {(r['name'] or '')[:28]:<28s}  computed={comp!s:>10}  expected≈{expected!s:>6}  Δ={delta}")
