"""Lat/lon → British / Irish National Grid references for Geograph API."""

from __future__ import annotations

import math
import re

try:
    from pyproj import Transformer
except ImportError as exc:
    raise SystemExit("pyproj is required: pip install pyproj") from exc

try:
    import osgb
except ImportError as exc:
    raise SystemExit("osgb is required: pip install osgb") from exc

# OSGB36 (EPSG:27700) — GB + NI (approximate)
_OSG_B = Transformer.from_crs("EPSG:4326", "EPSG:27700", always_xy=True)
# ITM (EPSG:29903) — Republic of Ireland
_ITM = Transformer.from_crs("EPSG:4326", "EPSG:29903", always_xy=True)

_GRID_COMPACT_RE = re.compile(r"^[A-Z]{2}\d{4,6}$")


def _compact_osgb_grid(easting: float, northing: float, digits: int = 6) -> str | None:
    """Two-letter British National Grid ref (no spaces), via osgb."""
    if not (0 <= easting < 700_000 and 0 <= northing < 1_300_000):
        return None
    try:
        formatted = osgb.format_grid((easting, northing)).replace(" ", "")
    except (ValueError, TypeError):
        return None
    if digits == 6:
        return formatted if _GRID_COMPACT_RE.match(formatted) else None
    if digits == 4:
        return formatted[:4] if len(formatted) >= 4 else None
    return None


def _irish_grid_ref(easting: float, northing: float, digits: int = 6) -> str | None:
    """Irish grid (as used by geograph.ie / geograph.org.uk for Ireland)."""
    if not (20_000 <= easting < 720_000 and 0 <= northing < 1_000_000):
        return None
    cols = int((easting - 20_000) // 100_000)
    rows = int(northing // 100_000)
    if cols < 0 or cols > 4 or rows < 0 or rows > 4:
        return None
    # 5×5 Irish grid letter layout (A–Z excluding I)
    irish_letters = [
        ["V", "W", "X", "Y", "Z"],
        ["Q", "R", "S", "T", "U"],
        ["L", "M", "N", "O", "P"],
        ["F", "G", "H", "J", "K"],
        ["A", "B", "C", "D", "E"],
    ]
    let = irish_letters[4 - rows][cols]
    e = int(easting) % 100_000
    n = int(northing) % 100_000
    if digits == 6:
        e //= 1000
        n //= 1000
        return f"{let}{e:03d}{n:03d}"
    if digits == 4:
        e //= 10_000
        n //= 10_000
        return f"{let}{e:02d}{n:02d}"
    return None


def grid_ref_for_island(lat: float, lon: float, nation: str = "", digits: int = 6) -> str | None:
    nation_l = (nation or "").strip().lower()
    if nation_l == "ireland":
        e, n = _ITM.transform(lon, lat)
        return _irish_grid_ref(e, n, digits)
    e, n = _OSG_B.transform(lon, lat)
    ref = _compact_osgb_grid(e, n, digits)
    if ref:
        return ref
    if nation_l in ("northern ireland",):
        e, n = _ITM.transform(lon, lat)
        return _irish_grid_ref(e, n, digits)
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
