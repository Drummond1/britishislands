#!/usr/bin/env python3
"""Collapse atlas records that are the same physical island.

The usual pair is a named OpenStreetMap relation and a second outline
(often from the unnamed-island pass) with the same shape and place.
One record is kept. Blank fields on it are filled from the record removed.

Dry-run is the default. ``--apply`` rewrites ``data/islands.json`` and
writes the audit files. It does not rebuild the map index.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from seo_paths import assign_seo_paths  # noqa: E402

ISLANDS = ROOT / "data" / "islands.json"
CURATED = ROOT / "data" / "curated.json"
REPORT = ROOT / "data" / "duplicate_place_report.json"
ALIASES = ROOT / "data" / "duplicate_place_aliases.json"
SEO_PATHS = ROOT / "data" / "seo_path_by_id.json"
BACKUP = ROOT / "data" / "islands.json.before-same-place-dedup"

QUALIFIERS = {
    "little", "great", "big", "beg", "beag", "mor", "more", "mhor", "mòr",
    "north", "south", "east", "west", "upper", "lower",
    "old", "new", "inner", "outer", "middle",
}
_DROP_WORDS = re.compile(
    r"\b(islands?|isles?|islets?|eilean|eileanan|inis|innis|inch|rocks?|skerries|skerry)\b"
)


def norm_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("'", " ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def simplify(value: str | None) -> str:
    text = _DROP_WORDS.sub(" ", norm_name(value))
    return re.sub(r"\s+", " ", text).strip()


GLUED_QUALIFIERS = (
    "east", "west", "north", "south", "little", "great",
    "upper", "lower", "inner", "outer",
)


def tokens(text: str) -> set[str]:
    return {part for part in text.split() if part}


def qualifier_set(text: str) -> set[str]:
    found = tokens(text) & QUALIFIERS
    for token in tokens(text):
        for prefix in GLUED_QUALIFIERS:
            if token.startswith(prefix) and len(token) > len(prefix) + 2:
                found.add(prefix)
                break
    return found


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_unnamed(island: dict) -> bool:
    if island.get("nameStatus") == "unknown":
        return True
    if "unnamed" in (island.get("tags") or []):
        return True
    name = norm_name(island.get("name"))
    return name in {"", "unnamed", "unnamed island", "unnamed islet"} or name.startswith("unnamed ")


def is_discovery(island: dict) -> bool:
    if island.get("source") == "osm-unnamed":
        return True
    if "named-via-staging" in (island.get("tags") or []):
        return True
    return (island.get("classification") or {}).get("source") == "unnamed-discovery"


def area_of(island: dict) -> float:
    try:
        value = float(island.get("areaKm2") or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def radius_m(island: dict) -> float:
    area = area_of(island)
    if area <= 0:
        return 0.0
    return math.sqrt(area / math.pi) * 1000.0


def hav_m(a: dict, b: dict) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(float(a["lat"])), math.radians(float(b["lat"]))
    dlat = math.radians(float(b["lat"]) - float(a["lat"]))
    dlng = math.radians(float(b["lng"]) - float(a["lng"]))
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, h)))


def parent_name(island: dict) -> str:
    parent = island.get("parentWaterBody") or {}
    if not isinstance(parent, dict):
        return ""
    name = str(parent.get("name") or "").strip()
    if name.lower().startswith("osm relation"):
        return ""
    return norm_name(name)


def name_relation(a: dict, b: dict) -> str | None:
    """How the two names agree. ``unnamed`` means one side has no real name."""
    if is_unnamed(a) or is_unnamed(b):
        return "unnamed"
    left, right = simplify(a.get("name")), simplify(b.get("name"))
    if not left or not right:
        return None
    if qualifier_set(left) != qualifier_set(right):
        return None
    if left == right:
        return "exact"
    left_core, right_core = tokens(left) - QUALIFIERS, tokens(right) - QUALIFIERS
    if left_core and right_core and (left_core <= right_core or right_core <= left_core):
        return "exact"
    if levenshtein(left, right) <= 2 and min(len(left), len(right)) >= 6:
        return "close"
    return None


def pair_reason(a: dict, b: dict) -> str | None:
    if a.get("id") == b.get("id"):
        return None
    if a.get("lat") is None or b.get("lat") is None:
        return None
    if a.get("osmType") and a.get("osmId") is not None and a.get("osmType") == b.get("osmType") and int(a["osmId"]) == int(b["osmId"]):
        return "same-osm-object"
    distance = hav_m(a, b)
    area_a, area_b = area_of(a), area_of(b)
    names = name_relation(a, b)
    nations_differ = (a.get("nation") or "") != (b.get("nation") or "")
    if nations_differ and distance > 40:
        return None

    if area_a and area_b:
        ratio = max(area_a, area_b) / min(area_a, area_b)
        smaller = min(radius_m(a), radius_m(b))
        outline_limit = max(12.0, 0.08 * smaller)
        if names is None:
            # Different names: only when the outlines sit on top of each other.
            outline_limit = max(8.0, 0.25 * smaller)
        if ratio <= 1.03 and distance <= outline_limit:
            return "same-outline"
        if names == "exact" and ratio <= 1.25 and distance <= min(250.0, max(30.0, 0.35 * smaller)) and distance < 0.8 * (radius_m(a) + radius_m(b)):
            return "same-name"
        if names == "close" and ratio <= 1.08 and distance <= min(120.0, max(20.0, 0.25 * smaller)):
            return "close-name"
        if names == "unnamed" and ratio <= 1.20 and distance <= min(200.0, max(25.0, 0.30 * smaller)) and distance < 0.75 * (radius_m(a) + radius_m(b)):
            parents = {parent_name(a), parent_name(b)} - {""}
            if len(parents) <= 1 or (distance <= 15 and ratio <= 1.05):
                return "named-and-unnamed-outline"
        return None

    # A named point and the outline of that island.
    if names in {None}:
        return None
    if names == "close" and distance > 30:
        return None
    if (area_a > 0) ^ (area_b > 0):
        radius = radius_m(a) or radius_m(b)
        limit = min(80.0, max(35.0, 0.4 * radius)) if radius else 35.0
        if distance <= limit:
            return "point-and-outline"
    return None


def score(island: dict, curated_ids: set[str]) -> tuple:
    named = 0 if is_unnamed(island) else 1
    return (
        1 if island.get("id") in curated_ids or island.get("source") == "curated" else 0,
        1 if area_of(island) else 0,
        named,
        1 if island.get("wikidata") else 0,
        1 if island.get("wikipedia") else 0,
        1 if island.get("images") or island.get("image") else 0,
        1 if island.get("osmType") == "relation" else 0,
        1 if island.get("source") in {"osm", "curated", "wikidata"} else 0,
        1 if str(island.get("shortDescription") or "").strip() else 0,
        0 if is_discovery(island) else 1,
        str(island.get("id") or ""),
    )


def empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def remember_other_name(keeper: dict, other_name: str | None) -> None:
    """Keep a second name when the removed record called the island something else."""
    if not other_name or is_unnamed({"name": other_name}):
        return
    existing = [str(keeper.get("name") or "")]
    existing.extend(str(value) for value in (keeper.get("names") or {}).values() if value)
    other_tokens = tokens(simplify(other_name))
    for value in existing:
        if not value:
            continue
        if simplify(other_name) == simplify(value):
            return
        if other_tokens and other_tokens <= tokens(simplify(value)):
            return
    names = dict(keeper.get("names") or {})
    index = 0
    while f"alt{index}" in names:
        index += 1
    names[f"alt{index}"] = other_name
    keeper["names"] = names


def revert_borrowed_name(island: dict) -> None:
    old = island.get("name")
    island["name"] = "Unnamed island"
    island["nameStatus"] = "unknown"
    tags = [tag for tag in (island.get("tags") or []) if tag != "named-via-staging"]
    for tag in ("unnamed", "needs-name"):
        if tag not in tags:
            tags.append(tag)
    island["tags"] = tags
    names = dict(island.get("names") or {})
    if names.get("en") == old:
        names.pop("en")
    island["names"] = names or None
    sources = list(island.get("sources") or [])
    sources.append(
        {
            "name": "same-place dedup",
            "ref": (island.get("nameProvenance") or {}).get("sourceRef") or "",
            "url": (island.get("nameProvenance") or {}).get("url") or "",
            "licence": (island.get("nameProvenance") or {}).get("licence") or "",
            "retrieved": "2026-10-27",
            "attribution": (
                f"Removed the borrowed name {old}. "
                "Another record of that name is a different outline."
            ),
        }
    )
    island["sources"] = sources


def borrowed_renames(islands: list[dict]) -> list[tuple[dict, dict, float]]:
    """A nearby gazetteer name copied onto a different, larger or smaller outline."""
    real = [
        island for island in islands
        if not is_discovery(island) and not is_unnamed(island) and island.get("lat") is not None
    ]
    found: list[tuple[dict, dict, float]] = []
    for island in islands:
        provenance = island.get("nameProvenance") or {}
        distance_m = provenance.get("distanceM")
        if not is_discovery(island) or is_unnamed(island):
            continue
        if not isinstance(distance_m, (int, float)) or distance_m <= 15:
            continue
        if island.get("lat") is None:
            continue
        for other in real:
            if other.get("id") == island.get("id"):
                continue
            if name_relation(island, other) != "exact":
                continue
            distance = hav_m(island, other)
            if distance > 80:
                continue
            area_island, area_other = area_of(island), area_of(other)
            if not area_island or not area_other:
                continue
            ratio = max(area_island, area_other) / min(area_island, area_other)
            if ratio < 1.5:
                continue
            found.append((island, other, distance))
            break
    return found


def fill_blanks(keeper: dict, dropped: dict) -> None:
    for key in (
        "areaKm2", "areaSource", "areaConfidence",
        "image", "wikidata", "wikipedia",
        "shortDescription", "history", "geography", "transport", "accommodation",
        "population", "highestPointM", "highestPointName", "geology", "archipelago",
    ):
        if empty(keeper.get(key)) and not empty(dropped.get(key)):
            keeper[key] = dropped[key]
    if empty(keeper.get("images")) and dropped.get("images"):
        keeper["images"] = dropped["images"]
        if empty(keeper.get("image")):
            keeper["image"] = dropped.get("image") or dropped["images"][0].get("url", "")
    kept_parent = parent_name(keeper)
    dropped_parent = parent_name(dropped)
    if not kept_parent and dropped_parent:
        keeper["parentWaterBody"] = dropped.get("parentWaterBody")
    merged_names = dict(keeper.get("names") or {})
    for key, value in (dropped.get("names") or {}).items():
        if value and not merged_names.get(key):
            merged_names[key] = value
    if merged_names:
        keeper["names"] = merged_names
    remember_other_name(keeper, dropped.get("name"))
    if keeper.get("osmId") is None and dropped.get("osmId") is not None:
        keeper["osmType"] = dropped.get("osmType")
        keeper["osmId"] = dropped.get("osmId")
        if dropped.get("osmPlace") and not keeper.get("osmPlace"):
            keeper["osmPlace"] = dropped["osmPlace"]
    url = ""
    if dropped.get("osmType") and dropped.get("osmId") is not None:
        url = f"https://www.openstreetmap.org/{dropped['osmType']}/{dropped['osmId']}"
    sources = list(keeper.get("sources") or [])
    sources.append(
        {
            "name": "same-place dedup",
            "ref": dropped.get("id"),
            "url": url,
            "licence": "ODbL",
            "retrieved": "2026-10-27",
            "attribution": (
                f"Removed duplicate record {dropped.get('id')} "
                f"({dropped.get('name')}) for the same island."
            ),
        }
    )
    keeper["sources"] = sources


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def cluster(islands: list[dict]) -> tuple[list[tuple[dict, dict, str]], dict[str, list[dict]]]:
    by_id = {island["id"]: island for island in islands}
    cell = 0.02
    grid: dict[tuple[int, int], list[str]] = defaultdict(list)
    for island in islands:
        if island.get("lat") is None or island.get("lng") is None or not island.get("id"):
            continue
        grid[(int(float(island["lat"]) / cell), int(float(island["lng"]) / cell))].append(island["id"])

    uf = UnionFind()
    reasons: list[tuple[dict, dict, str]] = []
    seen: set[tuple[str, str]] = set()

    def consider(a: dict, b: dict) -> None:
        left, right = a["id"], b["id"]
        key = (left, right) if left < right else (right, left)
        if key in seen:
            return
        seen.add(key)
        reason = pair_reason(a, b)
        if not reason:
            return
        reasons.append((a, b, reason))
        uf.union(left, right)

    for (cy, cx), ids in grid.items():
        neighbours: list[str] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbours.extend(grid.get((cy + dy, cx + dx), []))
        id_set = set(ids)
        for left_id in ids:
            for right_id in neighbours:
                if right_id <= left_id and right_id in id_set:
                    continue
                if right_id == left_id:
                    continue
                consider(by_id[left_id], by_id[right_id])

    by_osm: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for island in islands:
        if island.get("osmType") and island.get("osmId") is not None and island.get("id"):
            by_osm[(str(island["osmType"]), int(island["osmId"]))].append(island)
    for group in by_osm.values():
        if len(group) < 2:
            continue
        for other in group[1:]:
            consider(group[0], other)

    involved = list(uf.parent)
    groups: dict[str, list[dict]] = defaultdict(list)
    for island_id in involved:
        groups[uf.find(island_id)].append(by_id[island_id])
    merged = {root: members for root, members in groups.items() if len(members) > 1}
    return reasons, merged


def component_ok(members: list[dict]) -> bool:
    if len(members) < 2:
        return False
    radii = [radius_m(island) for island in members if radius_m(island)]
    smaller = min(radii) if radii else 25.0
    limit = max(100.0, 0.45 * smaller)
    for i, left in enumerate(members):
        for right in members[i + 1 :]:
            if left.get("lat") is None or right.get("lat") is None:
                continue
            if hav_m(left, right) > limit:
                return False
    curated = [island for island in members if island.get("source") == "curated"]
    if len(curated) > 1:
        return False
    return True


def choose_keeper(members: list[dict], curated_ids: set[str]) -> dict:
    return max(members, key=lambda island: score(island, curated_ids))


def summary_row(island: dict) -> dict:
    return {
        "id": island.get("id"),
        "name": island.get("name"),
        "nation": island.get("nation"),
        "source": island.get("source"),
        "osmType": island.get("osmType"),
        "osmId": island.get("osmId"),
        "areaKm2": island.get("areaKm2"),
        "lat": island.get("lat"),
        "lng": island.get("lng"),
        "wikidata": island.get("wikidata") or "",
    }


def retarget_references(redirect: dict[str, str]) -> list[str]:
    """Point live island id references at the kept record. Returns files changed."""
    changed: list[str] = []
    json_files = [
        ROOT / "data" / "interest_index.json",
        ROOT / "data" / "interest" / "accepted_memberships.json",
        ROOT / "data" / "galleries.json",
        ROOT / "data" / "crowd_pins.json",
        ROOT / "data" / "featured_islands.json",
        ROOT / "data" / "seo_photo_gap_queue.json",
        ROOT / "data" / "image_priority_queue.json",
        ROOT / "data" / "discovery" / "property_listings_registry.json",
        ROOT / "data" / "discovery" / "property_listings_verified.json",
    ]
    for path in json_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in redirect.items():
            updated = updated.replace(f'"{old}"', f'"{new}"')
        if updated == text:
            continue
        json.loads(updated)
        path.write_text(updated, encoding="utf-8")
        changed.append(str(path.relative_to(ROOT)))

    sql_path = ROOT / "data" / "interest" / "memberships_sync.sql"
    if sql_path.exists():
        text = sql_path.read_text(encoding="utf-8")
        updated = text
        for old, new in redirect.items():
            updated = updated.replace(f"'{old}'", f"'{new}'")
        if updated != text:
            sql_path.write_text(updated, encoding="utf-8")
            changed.append(str(sql_path.relative_to(ROOT)))
    return changed


def write_seo_paths(kept: list[dict], path_aliases: dict[str, str], id_aliases: dict[str, str]) -> None:
    paths = assign_seo_paths(kept)
    payload = {
        "schemaVersion": 1,
        "generated": "2026-10-27T15:10:00Z",
        "paths": {island_id: item.path for island_id, item in paths.items()},
        "idAliases": id_aliases,
        "pathAliases": path_aliases,
    }
    SEO_PATHS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    apply = "--apply" in sys.argv
    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    curated_ids = {row["id"] for row in json.loads(CURATED.read_text(encoding="utf-8"))}
    reasons, groups = cluster(islands)
    accepted: dict[str, list[dict]] = {}
    rejected: list[dict] = []
    for root, members in groups.items():
        if component_ok(members):
            accepted[root] = members
        else:
            rejected.append({"ids": [island.get("id") for island in members], "names": [island.get("name") for island in members]})

    actions = []
    drop_ids: set[str] = set()
    for members in accepted.values():
        keeper = choose_keeper(members, curated_ids)
        dropped = [island for island in members if island is not keeper]
        if any(island.get("id") in curated_ids for island in dropped):
            raise SystemExit(f"Refusing to drop a curated island in {[island.get('id') for island in dropped]}")
        for island in dropped:
            drop_ids.add(island["id"])
        pair_notes = []
        for left, right, reason in reasons:
            ids = {left["id"], right["id"]}
            if ids <= {island["id"] for island in members}:
                pair_notes.append(reason)
        actions.append((keeper, dropped, sorted(set(pair_notes))))

    print(f"islands {len(islands)}")
    print(f"pairs {len(reasons)}")
    print(f"groups kept-as-one {len(actions)} dropping {len(drop_ids)}")
    print(f"groups rejected {len(rejected)}")
    by_reason: dict[str, int] = defaultdict(int)
    for _keeper, _dropped, notes in actions:
        for note in notes:
            by_reason[note] += 1
    for note, count in sorted(by_reason.items()):
        print(f"  {note}: {count}")

    conflicts = []
    wide = []
    for keeper, dropped, notes in actions:
        for island in dropped:
            names = name_relation(keeper, island)
            ratio = None
            if area_of(keeper) and area_of(island):
                ratio = max(area_of(keeper), area_of(island)) / min(area_of(keeper), area_of(island))
            if names not in {"exact", "unnamed"}:
                conflicts.append((keeper, island, notes, names))
            if ratio and ratio > 1.15:
                wide.append((keeper, island, ratio, notes))
    print(f"name disagreements {len(conflicts)}")
    for keeper, island, notes, names in conflicts:
        print(f"  KEEP {keeper['id']} {keeper.get('name')!r}  DROP {island['id']} {island.get('name')!r}  via {notes} ({names})  d={hav_m(keeper, island):.1f}m")
    print(f"area ratio over 1.15: {len(wide)}")
    for keeper, island, ratio, notes in wide:
        print(f"  {ratio:.3f} KEEP {keeper.get('name')!r} {area_of(keeper)}  DROP {island.get('name')!r} {area_of(island)}  {notes}  d={hav_m(keeper, island):.1f}m")
    if rejected:
        print("rejected groups:")
        for item in rejected:
            print(" ", item)
    triples = [members for members in accepted.values() if len(members) > 2]
    print(f"groups of three or more: {len(triples)}")
    for members in triples:
        print(" ", [(island.get("id"), island.get("name")) for island in members])

    borrowed = borrowed_renames(islands)
    print(f"borrowed names to clear: {len(borrowed)}")
    for island, other, distance in borrowed:
        print(f"  UNNAME {island['id']} {island.get('name')!r}  near {other['id']} {other.get('name')!r}  d={distance:.1f}m")

    leftovers = leftover_named_pairs(
        islands,
        drop_ids | {island["id"] for island, _other, _distance in borrowed},
    )
    print(f"same-name pairs still separate: {len(leftovers)}")
    for distance, left, right in leftovers:
        print(f"  {distance:.1f}m {left['id']} {left.get('name')!r}  |  {right['id']} {right.get('name')!r}")

    if not apply:
        print("dry-run only")
        return 0

    old_paths = assign_seo_paths(islands)
    borrowed_paths: list[tuple[str, str]] = []
    for island, other, _distance in borrowed:
        old = old_paths.get(island["id"])
        if old:
            borrowed_paths.append((old.path, other["id"]))
        revert_borrowed_name(island)
    redirect: dict[str, str] = {}
    precise_points: list[dict] = []
    for keeper, dropped, notes in actions:
        for island in sorted(dropped, key=lambda item: score(item, curated_ids), reverse=True):
            fill_blanks(keeper, island)
            if "same-osm-object" in notes and hav_m(keeper, island) > 500:
                keeper["lat"] = island["lat"]
                keeper["lng"] = island["lng"]
                precise_points.append(keeper)
            redirect[island["id"]] = keeper["id"]

    kept = [island for island in islands if island.get("id") not in drop_ids]
    if len(kept) + len(drop_ids) != len(islands):
        raise SystemExit("drop count does not match")
    if curated_ids - {island["id"] for island in kept}:
        raise SystemExit("a curated island would be missing after the merge")

    new_paths = assign_seo_paths(kept)
    path_aliases: dict[str, str] = {}
    for old_id, keeper_id in redirect.items():
        old = old_paths.get(old_id)
        new = new_paths.get(keeper_id)
        if old and new and old.path != new.path:
            path_aliases[old.path] = keeper_id
    for old_path, keeper_id in borrowed_paths:
        if old_path not in path_aliases:
            path_aliases[old_path] = keeper_id
    new_path_owners = {item.path: island_id for island_id, item in new_paths.items()}
    for old_path, keeper_id in list(path_aliases.items()):
        owner = new_path_owners.get(old_path)
        if owner == keeper_id or (owner and owner != keeper_id):
            del path_aliases[old_path]

    report = {
        "date": "2026-10-27",
        "before": len(islands),
        "after": len(kept),
        "dropped": len(drop_ids),
        "groups": [
            {
                "keeper": summary_row(keeper),
                "dropped": [summary_row(island) for island in dropped],
                "reasons": notes,
            }
            for keeper, dropped, notes in sorted(actions, key=lambda item: item[0].get("name") or "")
        ],
    }
    shutil.copyfile(ISLANDS, BACKUP)
    ISLANDS.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ALIASES.write_text(
        json.dumps({"idAliases": redirect, "pathAliases": path_aliases}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_seo_paths(kept, path_aliases, redirect)
    for island in precise_points:
        update_curated_point(island["id"], island["lat"], island["lng"])
    changed = retarget_references(redirect)
    print(f"wrote {len(kept)} islands, dropped {len(drop_ids)}")
    print(f"path aliases {len(path_aliases)}")
    print("retargeted", changed or "none")
    return 0


def leftover_named_pairs(islands: list[dict], skip_ids: set[str]) -> list[tuple[float, dict, dict]]:
    remaining = [
        island for island in islands
        if island.get("id") not in skip_ids and not is_unnamed(island) and island.get("lat") is not None
    ]
    cell = 0.02
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for island in remaining:
        grid[(int(float(island["lat"]) / cell), int(float(island["lng"]) / cell))].append(island)
    found: list[tuple[float, dict, dict]] = []
    seen: set[tuple[str, str]] = set()
    for (cy, cx), items in grid.items():
        neighbours: list[dict] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                neighbours.extend(grid.get((cy + dy, cx + dx), []))
        item_ids = {island["id"] for island in items}
        for left in items:
            for right in neighbours:
                if right["id"] == left["id"]:
                    continue
                if right["id"] < left["id"] and right["id"] in item_ids:
                    continue
                key = (left["id"], right["id"]) if left["id"] < right["id"] else (right["id"], left["id"])
                if key in seen:
                    continue
                seen.add(key)
                if name_relation(left, right) != "exact":
                    continue
                distance = hav_m(left, right)
                if distance <= 150:
                    found.append((distance, left, right))
    found.sort(key=lambda item: item[0])
    return found


def update_curated_point(island_id: str, lat: float, lng: float) -> None:
    text = CURATED.read_text(encoding="utf-8")
    marker = f'"id": "{island_id}"'
    start = text.find(marker)
    if start < 0:
        return
    window = text[start:start + 400]
    updated, count = re.subn(
        r'"lat": [0-9.\-]+,\n    "lng": [0-9.\-]+,',
        f'"lat": {lat},\n    "lng": {lng},',
        window,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"Could not update curated coordinates for {island_id}")
    CURATED.write_text(text[:start] + updated + text[start + 400:], encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
