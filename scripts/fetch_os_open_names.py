#!/usr/bin/env python3
"""Download OS Open Names CSV into data/raw/os_opennames.csv (OGL v3.0).

Requires ``OS_DATAHUB_API_KEY`` or ``OS_MAPS_API_KEY`` in ``.env.local``.
Register at https://osdatahub.os.uk/ and attach the Open Names product.

Run::

    python3 scripts/fetch_os_open_names.py
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw"
OUT_CSV = OUT_DIR / "os_opennames.csv"
ENV_LOCAL = ROOT / ".env.local"
USER_AGENT = "isles-of-britain/0.1 (fetch-os-open-names)"

# OS Data Hub Open Names CSV extract (GB)
DOWNLOAD_URL = (
    "https://api.os.uk/downloads/v1/products/OpenNames/downloads"
    "?area=GB&format=CSV&extract=yes"
)


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


def _api_key() -> str:
    return (
        os.environ.get("OS_DATAHUB_API_KEY")
        or os.environ.get("OS_MAPS_API_KEY")
        or os.environ.get("OS_MAPS_KEY")
        or ""
    ).strip()


def main() -> int:
    _load_dotenv(ENV_LOCAL)
    key = _api_key()
    if not key:
        print(
            "OS_DATAHUB_API_KEY missing in .env.local — get one at https://osdatahub.os.uk/",
            file=sys.stderr,
        )
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        DOWNLOAD_URL,
        headers={"User-Agent": USER_AGENT, "key": key},
    )
    print(f"Downloading OS Open Names…", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        print(f"Download failed HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        return 1

    if blob[:2] == b"PK":
        with zipfile.ZipFile(BytesIO(blob)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                print("Zip contained no CSV", file=sys.stderr)
                return 1
            target = max(csv_names, key=lambda n: zf.getinfo(n).file_size)
            OUT_CSV.write_bytes(zf.read(target))
    else:
        OUT_CSV.write_bytes(blob)

    size_mb = OUT_CSV.stat().st_size / (1024 * 1024)
    print(f"Wrote {OUT_CSV} ({size_mb:.1f} MiB)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
