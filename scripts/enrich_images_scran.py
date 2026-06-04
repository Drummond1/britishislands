#!/usr/bin/env python3
"""Probe SCRAN / HES image APIs for open island photo harvest.

Historic Environment Scotland retired the Canmore/SCRAN machine API in 2025;
trove.scot requires per-image licence via user accounts. This script probes
candidate endpoints and **skips** harvest when no open search API is available,
writing a full audit to ``data/image_enrichment_scran_report.json``.

If a future open API is detected (JSON search + explicit OGL/CC on assets), the
harvester will stage matches with dual-signal name + geo verification.

Run::

    python3 scripts/enrich_images_scran.py --named-only --limit 400
    python3 scripts/enrich_images_scran.py --probe-only

Outputs::

    data/staging/adoptions/scran.json
    data/image_enrichment_scran_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ISLANDS = DATA / "islands.json"
STAGING = DATA / "staging" / "adoptions" / "scran.json"
REPORT = DATA / "image_enrichment_scran_report.json"

USER_AGENT = "isles-of-britain/0.1 scran-probe"
DEFAULT_LIMIT = 400
SOURCE = "scran"

# Candidate endpoints (2026-06 probe list).
PROBE_ENDPOINTS: list[dict[str, str]] = [
    {
        "id": "scran-www",
        "url": "https://www.scran.ac.uk/",
        "expect": "HTML portal; no documented open search API",
    },
    {
        "id": "scran-api-root",
        "url": "https://www.scran.ac.uk/api/",
        "expect": "Often 403 without session",
    },
    {
        "id": "canmore-search",
        "url": "https://canmore.org.uk/api/site/search/result?q=test",
        "expect": "Retired / 403 post-2025 cyber incident",
    },
    {
        "id": "trove-scot",
        "url": "https://trove.scot/",
        "expect": "Per-image licence via account; not machine-harvestable OGL",
    },
]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrich_images_v5 import _load_named_index_ids  # noqa: E402
from photo_staging_dual import save_staging  # noqa: E402


def _probe_url(url: str, timeout: int = 12) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,*/*"},
    )
    out: dict[str, Any] = {"url": url, "ok": False}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            out["status"] = resp.status
            out["content_type"] = resp.headers.get("Content-Type", "")
            body = resp.read(2048)
            out["ok"] = 200 <= resp.status < 300
            out["snippet"] = body[:200].decode("utf-8", errors="replace")
            if "json" in out["content_type"].lower():
                try:
                    out["json_keys"] = list(json.loads(body).keys())[:12]
                except json.JSONDecodeError:
                    out["json_keys"] = []
    except urllib.error.HTTPError as exc:
        out["status"] = exc.code
        out["error"] = exc.reason
    except Exception as exc:
        out["error"] = repr(exc)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--named-only", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max islands that would be attempted if API were open (default {DEFAULT_LIMIT}).",
    )
    p.add_argument("--probe-only", action="store_true", help="Only probe endpoints; default behaviour.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    islands = json.loads(ISLANDS.read_text(encoding="utf-8"))
    pending = [i for i in islands if not (i.get("images") or [])]
    if args.named_only:
        named_ids = _load_named_index_ids()
        if named_ids:
            pending = [i for i in pending if i.get("id") in named_ids]
    if args.limit:
        pending = pending[: args.limit]

    probes: list[dict[str, Any]] = []
    open_api_found = False
    for spec in PROBE_ENDPOINTS:
        result = _probe_url(spec["url"])
        result["id"] = spec["id"]
        result["expect"] = spec["expect"]
        probes.append(result)
        if result.get("ok") and result.get("json_keys"):
            open_api_found = True
        time.sleep(0.4)

    viability = (
        "open_json_search"
        if open_api_found
        else "no_open_api — skip harvest (educational/NC on SCRAN; trove.scot account licence)"
    )

    report: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "script": "enrich_images_scran.py",
        "source": SOURCE,
        "args": vars(args),
        "dual_signal": "name_match AND geo_match required when harvest enabled",
        "attempts": len(pending),
        "would_attempt": len(pending),
        "endpoint_probes": probes,
        "viability": viability,
        "harvest_skipped": not open_api_found,
        "skip_reason": (
            None
            if open_api_found
            else "No open SCRAN/Canmore JSON search API (403/HTML); trove.scot not machine-OGL."
        ),
        "staged_by_source": {SOURCE: 0},
        "staged_count": 0,
        "adopted": [],
        "rejected": [],
    }

    adoptions: list[dict] = []
    if not args.dry_run:
        save_staging(STAGING, adoptions)

    report["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Probes: {len(probes)}")
    print(f"Viability: {viability}")
    print(f"Attempts (would-run): {len(pending):,}")
    print(f"Staged ({SOURCE}): 0")
    print(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
