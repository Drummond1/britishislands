#!/usr/bin/env python3
"""
Build Terrarium DEM heightmaps for showcase islands.

Fetches OSM polygon outlines via Overpass, samples Mapzen Terrarium tiles
(AWS S3), masks heights outside the island polygon, and writes JSON grids
to ``data/terrain/{id}.json`` plus ``data/terrain/manifest.json``.

Run:
    python3 scripts/build_island_terrain.py
    python3 scripts/build_island_terrain.py --ids staffa,iona
    python3 scripts/build_island_terrain.py --cache   # reuse Overpass + tile cache
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS_PATH = DATA / "islands.json"
TERRAIN_DIR = DATA / "terrain"
OVERPASS_CACHE_DIR = DATA / "cache_overpass_terrain"
TERRARIUM_CACHE_DIR = DATA / "cache_terrarium"

SHOWCASE_IDS = [
    "staffa",
    "iona",
    "st-kilda",
    "lindisfarne",
    "lundy",
    "brownsea",
    "rathlin",
    "burgh-island",
    "fair-isle",
    "inchcailloch",
]

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

TERRARIUM_URL = (
    "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
)

USER_AGENT = "isles-of-britain/0.1 (build-island-terrain; static-site)"

TERRARIUM_ATTRIBUTION = (
    "Terrain elevation from Mapzen Terrarium tiles on AWS Open Data "
    "(elevation-tiles-prod); decode: (R×256 + G + B/256) − 32768 m."
)


# -----------------------------------------------------------------------------
# I/O helpers
# -----------------------------------------------------------------------------
def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _http_get(url: str, *, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_post_form(url: str, form: dict[str, str], *, timeout: int = 90) -> bytes:
    body = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# -----------------------------------------------------------------------------
# Overpass
# -----------------------------------------------------------------------------
def overpass_query(osm_type: str, osm_id: int) -> str:
    return f"[out:json][timeout:25];{osm_type}({osm_id});out geom;"


def fetch_overpass(osm_type: str, osm_id: int, *, use_cache: bool) -> dict:
    cache_key = f"{osm_type}-{osm_id}.json"
    cache_path = OVERPASS_CACHE_DIR / cache_key
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    query = overpass_query(osm_type, osm_id)
    last_err: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            raw = _http_post_form(endpoint, {"data": query}, timeout=90)
            data = json.loads(raw.decode("utf-8"))
            OVERPASS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except Exception as exc:
            last_err = exc
            print(f"    {endpoint}: {exc}", file=sys.stderr)
            time.sleep(1.0)
    raise RuntimeError(f"Overpass failed for {osm_type}/{osm_id}: {last_err}")


def _close_ring(coords: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(coords) < 3:
        return coords
    if coords[0] != coords[-1]:
        return coords + [coords[0]]
    return coords


def rings_from_overpass(payload: dict) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    """Return (outer_rings, inner_rings) as lists of closed (lng, lat) rings."""
    outers: list[list[tuple[float, float]]] = []
    inners: list[list[tuple[float, float]]] = []
    for el in payload.get("elements") or []:
        if el.get("type") == "way" and el.get("geometry"):
            ring = [(p["lon"], p["lat"]) for p in el["geometry"]]
            outers.append(_close_ring(ring))
        elif el.get("type") == "relation":
            for m in el.get("members") or []:
                if m.get("type") != "way" or not m.get("geometry"):
                    continue
                ring = [(p["lon"], p["lat"]) for p in m["geometry"]]
                if len(ring) < 3:
                    continue
                closed = _close_ring(ring)
                if m.get("role") == "inner":
                    inners.append(closed)
                else:
                    outers.append(closed)
    return outers, inners


def bbox_from_rings(
    rings: list[list[tuple[float, float]]],
    *,
    pad_frac: float = 0.15,
) -> tuple[float, float, float, float]:
    lngs = [c[0] for ring in rings for c in ring]
    lats = [c[1] for ring in rings for c in ring]
    if not lngs:
        raise ValueError("empty polygon")
    west, east = min(lngs), max(lngs)
    south, north = min(lats), max(lats)
    pad_lng = (east - west) * pad_frac
    pad_lat = (north - south) * pad_frac
    if pad_lng == 0:
        pad_lng = 0.0005
    if pad_lat == 0:
        pad_lat = 0.0005
    return west - pad_lng, south - pad_lat, east + pad_lng, north + pad_lat


# -----------------------------------------------------------------------------
# Point-in-polygon (ray casting)
# -----------------------------------------------------------------------------
def _point_in_ring(lng: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 4:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_polygon(
    lng: float,
    lat: float,
    outers: list[list[tuple[float, float]]],
    inners: list[list[tuple[float, float]]],
) -> bool:
    if not outers:
        return False
    in_outer = any(_point_in_ring(lng, lat, ring) for ring in outers)
    if not in_outer:
        return False
    if any(_point_in_ring(lng, lat, ring) for ring in inners):
        return False
    return True


# -----------------------------------------------------------------------------
# Grid / zoom selection
# -----------------------------------------------------------------------------
def pick_grid_and_zoom(area_km2: float | None) -> tuple[int, int, int]:
    """Return (grid_size, zoom) — square grid grid_size × grid_size."""
    a = area_km2 if area_km2 and area_km2 > 0 else 1.0
    if a < 0.12:
        return 256, 14
    if a < 0.35:
        return 224, 14
    if a < 0.8:
        return 192, 13
    if a < 2.5:
        return 160, 13
    if a < 5.0:
        return 128, 12
    if a < 9.0:
        return 96, 12
    return 64, 11


# -----------------------------------------------------------------------------
# Web Mercator tile math + Terrarium
# -----------------------------------------------------------------------------
def _lat_to_tile_y(lat: float, zoom: int) -> float:
    lat_rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * (2**zoom)


def _lon_to_tile_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (2**zoom)


def lon_lat_to_tile_pixel(lon: float, lat: float, zoom: int) -> tuple[int, int, int, int]:
    xt = _lon_to_tile_x(lon, zoom)
    yt = _lat_to_tile_y(lat, zoom)
    tx = int(xt)
    ty = int(yt)
    px = min(255, max(0, int((xt - tx) * 256)))
    py = min(255, max(0, int((yt - ty) * 256)))
    return tx, ty, px, py


def terrarium_decode(r: int, g: int, b: int) -> float:
    return (r * 256 + g + b / 256.0) - 32768.0


def _png_chunks(data: bytes) -> dict[bytes, bytes]:
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    chunks: dict[bytes, bytes] = {}
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        cdata = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IEND":
            break
        if ctype == b"IDAT":
            idat.extend(cdata)
        else:
            chunks[ctype] = cdata
    chunks[b"IDAT"] = bytes(idat)
    return chunks


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_scanline(
    filter_type: int,
    row: bytearray,
    prev: bytearray | None,
    bpp: int,
) -> None:
    if filter_type == 0:
        return
    if prev is None:
        prev = bytearray(len(row))
    for i in range(len(row)):
        raw = row[i]
        a = row[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if filter_type == 1:
            row[i] = (raw + a) & 0xFF
        elif filter_type == 2:
            row[i] = (raw + b) & 0xFF
        elif filter_type == 3:
            row[i] = (raw + (a + b) // 2) & 0xFF
        elif filter_type == 4:
            row[i] = (raw + _paeth(a, b, c)) & 0xFF


def decode_png_rgb(data: bytes) -> tuple[int, int, bytes]:
    """Decode 8-bit RGB/RGBA PNG → (width, height, rgb_bytes)."""
    try:
        from PIL import Image  # type: ignore
        import io

        img = Image.open(io.BytesIO(data)).convert("RGB")
        w, h = img.size
        return w, h, img.tobytes()
    except ImportError:
        pass

    chunks = _png_chunks(data)
    ihdr = chunks.get(b"IHDR")
    if not ihdr or len(ihdr) < 13:
        raise ValueError("missing IHDR")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", ihdr[:10])
    if bit_depth != 8 or color_type not in (2, 6):
        raise ValueError(f"unsupported PNG {bit_depth=}/{color_type=}")
    bpp = 3 if color_type == 2 else 4
    raw = zlib.decompress(chunks[b"IDAT"])
    stride = width * bpp
    out = bytearray(height * stride)
    pos = 0
    prev_row: bytearray | None = None
    for y in range(height):
        filter_type = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride
        _unfilter_scanline(filter_type, row, prev_row, bpp)
        out[y * stride : (y + 1) * stride] = row
        prev_row = row
    if color_type == 6:
        rgb = bytearray(width * height * 3)
        for y in range(height):
            for x in range(width):
                si = y * stride + x * 4
                di = (y * width + x) * 3
                rgb[di : di + 3] = out[si : si + 3]
        return width, height, bytes(rgb)
    return width, height, bytes(out)


class TerrariumTileCache:
    def __init__(self, *, use_cache: bool) -> None:
        self.use_cache = use_cache
        self._mem: dict[tuple[int, int, int], tuple[int, int, bytes]] = {}

    def get(self, z: int, x: int, y: int) -> tuple[int, int, bytes]:
        key = (z, x, y)
        if key in self._mem:
            return self._mem[key]
        cache_path = TERRARIUM_CACHE_DIR / str(z) / str(x) / f"{y}.png"
        if self.use_cache and cache_path.exists():
            data = cache_path.read_bytes()
        else:
            url = TERRARIUM_URL.format(z=z, x=x, y=y)
            data = _http_get(url, timeout=45)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
            time.sleep(0.05)
        w, h, rgb = decode_png_rgb(data)
        self._mem[key] = (w, h, rgb)
        return w, h, rgb

    def sample(self, lon: float, lat: float, zoom: int) -> float | None:
        n = 2**zoom
        tx, ty, px, py = lon_lat_to_tile_pixel(lon, lat, zoom)
        if tx < 0 or ty < 0 or tx >= n or ty >= n:
            return None
        w, h, rgb = self.get(zoom, tx, ty)
        if px >= w or py >= h:
            return None
        i = (py * w + px) * 3
        r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
        return terrarium_decode(r, g, b)


# -----------------------------------------------------------------------------
# Heightmap build
# -----------------------------------------------------------------------------
def build_heightmap(
    island_id: str,
    name: str,
    outers: list[list[tuple[float, float]]],
    inners: list[list[tuple[float, float]]],
    area_km2: float | None,
    tiles: TerrariumTileCache,
) -> dict[str, Any]:
    west, south, east, north = bbox_from_rings(outers + inners)
    grid_size, zoom = pick_grid_and_zoom(area_km2)
    grid_w = grid_h = grid_size

    heights: list[float | None] = []
    min_elev = float("inf")
    max_elev = float("-inf")

    for j in range(grid_h):
        lat = south + (j / (grid_h - 1) if grid_h > 1 else 0) * (north - south)
        for i in range(grid_w):
            lon = west + (i / (grid_w - 1) if grid_w > 1 else 0) * (east - west)
            if not point_in_polygon(lon, lat, outers, inners):
                heights.append(None)
                continue
            elev = tiles.sample(lon, lat, zoom)
            if elev is None or not math.isfinite(elev):
                heights.append(None)
                continue
            # Treat obvious ocean nodata as masked
            if elev < -500:
                heights.append(None)
                continue
            heights.append(round(elev, 2))
            min_elev = min(min_elev, elev)
            max_elev = max(max_elev, elev)

    if min_elev == float("inf"):
        min_elev = None
        max_elev = None
    else:
        min_elev = round(min_elev, 2)
        max_elev = round(max_elev, 2)

    return {
        "id": island_id,
        "name": name,
        "bounds": [round(west, 6), round(south, 6), round(east, 6), round(north, 6)],
        "gridW": grid_w,
        "gridH": grid_h,
        "zoom": zoom,
        "heights": heights,
        "minElev": min_elev,
        "maxElev": max_elev,
        "source": "terrarium",
        "attribution": TERRARIUM_ATTRIBUTION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def load_island(island_id: str, islands: list[dict]) -> dict:
    for isl in islands:
        if isl.get("id") == island_id:
            return isl
    raise KeyError(f"island id not found: {island_id}")


def process_island(
    island_id: str,
    islands: list[dict],
    *,
    use_cache: bool,
    tiles: TerrariumTileCache,
) -> dict[str, Any]:
    isl = load_island(island_id, islands)
    osm_type = isl.get("osmType")
    osm_id = isl.get("osmId")
    if not osm_type or osm_id is None:
        raise ValueError(f"{island_id}: missing osmType/osmId")
    print(f"  {island_id}: Overpass {osm_type}/{osm_id}…", flush=True)
    payload = fetch_overpass(str(osm_type), int(osm_id), use_cache=use_cache)
    outers, inners = rings_from_overpass(payload)
    if not outers:
        raise ValueError(f"{island_id}: no polygon rings in Overpass response")
    print(f"    rings: {len(outers)} outer, {len(inners)} inner", flush=True)
    hm = build_heightmap(
        island_id,
        isl.get("name") or island_id,
        outers,
        inners,
        isl.get("areaKm2"),
        tiles,
    )
    out_path = TERRAIN_DIR / f"{island_id}.json"
    _atomic_write(out_path, hm)
    print(
        f"    wrote {out_path.name} grid={hm['gridW']} zoom={hm['zoom']} "
        f"elev {hm['minElev']}…{hm['maxElev']} m",
        flush=True,
    )
    return hm


def write_manifest(results: list[dict[str, Any]], failures: list[dict[str, str]]) -> None:
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "terrarium",
        "attribution": TERRARIUM_ATTRIBUTION,
        "islands": [
            {
                "id": r["id"],
                "name": r["name"],
                "bounds": r["bounds"],
                "gridW": r["gridW"],
                "gridH": r["gridH"],
                "zoom": r["zoom"],
                "minElev": r["minElev"],
                "maxElev": r["maxElev"],
                "file": f"{r['id']}.json",
            }
            for r in results
        ],
        "failures": failures,
    }
    _atomic_write(TERRAIN_DIR / "manifest.json", manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Terrarium heightmaps for showcase islands.")
    parser.add_argument(
        "--ids",
        default=",".join(SHOWCASE_IDS),
        help="Comma-separated island ids (default: all showcase)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Reuse cached Overpass responses and Terrarium PNG tiles",
    )
    args = parser.parse_args()
    ids = [s.strip() for s in args.ids.split(",") if s.strip()]
    if not ids:
        print("No island ids specified.", file=sys.stderr)
        return 2

    if not ISLANDS_PATH.exists():
        print(f"Missing {ISLANDS_PATH}", file=sys.stderr)
        return 2

    print(f"Loading islands from {ISLANDS_PATH.name}…", flush=True)
    islands = json.loads(ISLANDS_PATH.read_text(encoding="utf-8"))
    TERRAIN_DIR.mkdir(parents=True, exist_ok=True)

    tiles = TerrariumTileCache(use_cache=args.cache)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    for island_id in ids:
        print(f"\n→ {island_id}", flush=True)
        try:
            hm = process_island(island_id, islands, use_cache=args.cache, tiles=tiles)
            results.append(hm)
        except Exception as exc:
            msg = str(exc)
            print(f"  FAILED: {msg}", file=sys.stderr)
            failures.append({"id": island_id, "error": msg})

    write_manifest(results, failures)
    print(f"\nDone: {len(results)} ok, {len(failures)} failed", flush=True)
    if failures:
        for f in failures:
            print(f"  ✗ {f['id']}: {f['error']}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
