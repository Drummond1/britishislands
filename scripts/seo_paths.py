#!/usr/bin/env python3
"""
Public SEO paths for island profiles.

Canonical shape (no keyword stuffing):
  /islands/{nation-segment}/{name-slug}/

Internal `id` stays stable for ?island= and data joins. This module only
derives the public URL path.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Display nation → URL segment (hubs live at /islands/{segment}/)
NATION_SEGMENT: dict[str, str] = {
    "Scotland": "scotland",
    "England": "england",
    "Wales": "wales",
    "Ireland": "ireland",
    "Northern Ireland": "northern-ireland",
    "Crown Dependency": "crown-dependencies",
    "Isle of Man": "isle-of-man",
}

NATION_HUB_TITLE: dict[str, str] = {
    "scotland": "Scottish islands map",
    "england": "English islands map",
    "wales": "Welsh islands map",
    "ireland": "Irish islands map",
    "northern-ireland": "Northern Ireland islands map",
    "crown-dependencies": "Crown Dependency islands map",
    "isle-of-man": "Isle of Man islands map",
}

NATION_HUB_BLURB: dict[str, str] = {
    "scotland": "Explore sea, loch, and river islands across Scotland on an interactive map.",
    "england": "Explore sea, lake, and river islands across England on an interactive map.",
    "wales": "Explore sea, lake, and river islands across Wales on an interactive map.",
    "ireland": "Explore coastal and inland islands across Ireland on an interactive map.",
    "northern-ireland": "Explore islands in Northern Ireland on an interactive map.",
    "crown-dependencies": "Explore islands of the Crown Dependencies on an interactive map.",
    "isle-of-man": "Explore islands around the Isle of Man on an interactive map.",
}

_MACHINE_ID = re.compile(
    r"^(osm-|wd-|csv-|way-|node-|relation-)", re.IGNORECASE
)
_UNNAMED = re.compile(r"unnamed", re.IGNORECASE)


@dataclass(frozen=True)
class SeoPath:
    """Public path bits for one island."""

    nation_segment: str
    slug: str
    path: str  # e.g. /islands/ireland/achill-island/
    legacy_profile: str  # e.g. /profiles/osm-relation-6045364.html

    @property
    def index_rel(self) -> str:
        """Relative path under site root to index.html."""
        return f"islands/{self.nation_segment}/{self.slug}/index.html"


def nation_segment(nation: str | None) -> str:
    n = (nation or "").strip()
    if n in NATION_SEGMENT:
        return NATION_SEGMENT[n]
    # Fallback: slugify unknown nation labels
    return slugify(n) or "other"


def slugify(text: str) -> str:
    """ASCII-folded, lowercase, hyphenated slug."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKD", str(text))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"['’`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80]


def is_unnamed_island(isl: dict) -> bool:
    if isl.get("nameStatus") == "unknown":
        return True
    name = str(isl.get("name") or "")
    if _UNNAMED.search(name):
        return True
    tags = isl.get("tags") or []
    return "unnamed" in tags


def is_machine_id(iid: str) -> bool:
    return bool(_MACHINE_ID.match(iid or ""))


def base_slug_for_island(isl: dict) -> str:
    """Preferred slug before collision disambiguation."""
    iid = str(isl.get("id") or "")
    if is_unnamed_island(isl):
        return slugify(iid) or "unnamed"

    name = str(isl.get("name") or "").strip()
    from_name = slugify(name)
    # Prefer an existing human id when it is already a clean name slug
    if iid and not is_machine_id(iid):
        id_slug = slugify(iid)
        if id_slug and (not from_name or id_slug == from_name or from_name.startswith(id_slug)):
            return id_slug
        if id_slug and len(id_slug) >= 3:
            # Curated ids like isle-of-skye / rathlin — keep them stable in the path
            return id_slug

    if from_name:
        return from_name
    return slugify(iid) or "island"


def _disambiguators(isl: dict) -> list[str]:
    out: list[str] = []
    parent = isl.get("parentWaterBody") or {}
    pname = parent.get("name") if isinstance(parent, dict) else None
    if pname:
        out.append(slugify(str(pname)))
    arch = isl.get("archipelago")
    if arch:
        out.append(slugify(str(arch)))
    # County-ish hint sometimes in tags — skip
    iid = str(isl.get("id") or "")
    # Last resort: stable id tail
    id_slug = slugify(iid)
    if id_slug:
        out.append(id_slug)
    return [x for x in out if x]


def assign_seo_paths(islands: list[dict]) -> dict[str, SeoPath]:
    """
    Assign unique /islands/{nation}/{slug}/ paths for every island with an id.
    Collisions within a nation get parent / archipelago / id suffixes.
    """
    # First pass: group by nation segment + tentative slug
    tentative: list[tuple[str, dict, str]] = []
    for isl in islands:
        iid = isl.get("id")
        if not iid:
            continue
        seg = nation_segment(isl.get("nation"))
        tentative.append((str(iid), isl, base_slug_for_island(isl)))

    used: dict[str, set[str]] = {}
    result: dict[str, SeoPath] = {}

    # Process in stable order so collisions are deterministic
    tentative.sort(key=lambda t: (nation_segment(t[1].get("nation")), t[2], t[0]))

    for iid, isl, base in tentative:
        seg = nation_segment(isl.get("nation"))
        bucket = used.setdefault(seg, set())
        slug = base or "island"
        if slug in bucket:
            for extra in _disambiguators(isl):
                candidate = f"{base}-{extra}" if base else extra
                candidate = candidate[:90]
                if candidate not in bucket:
                    slug = candidate
                    break
            else:
                # Absolute fallback
                n = 2
                while f"{base}-{n}" in bucket:
                    n += 1
                slug = f"{base}-{n}"
        bucket.add(slug)
        path = f"/islands/{seg}/{slug}/"
        result[iid] = SeoPath(
            nation_segment=seg,
            slug=slug,
            path=path,
            legacy_profile=f"/profiles/{iid}.html",
        )

    return result


def page_title(isl: dict) -> str:
    name = str(isl.get("name") or isl.get("id") or "Island")
    nation = str(isl.get("nation") or "").strip()
    if nation:
        return f"{name}, {nation} — map & profile | Find My Island"
    return f"{name} — map & profile | Find My Island"
