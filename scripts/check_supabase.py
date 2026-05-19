#!/usr/bin/env python3
"""Smoke-test Supabase env vars and REST reachability (read-only)."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv_local() -> None:
    path = ROOT / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main() -> int:
    load_dotenv_local()
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        print(
            "Missing SUPABASE_URL or SUPABASE_ANON_KEY.\n"
            "Copy .env.local.example → .env.local and fill from Supabase → Settings → API.",
            file=sys.stderr,
        )
        return 1

    req = urllib.request.Request(
        f"{url}/rest/v1/profiles?select=id&limit=1",
        headers={
            "apikey": anon,
            "Authorization": f"Bearer {anon}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"OK {resp.status} — REST reachable at {url}")
            print("profiles table:", "ready" if resp.status == 200 else resp.status)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("REST reachable but profiles missing — run the SQL migration.", file=sys.stderr)
            return 2
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
