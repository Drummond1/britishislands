#!/usr/bin/env python3
"""Recover ``data/islands.json`` after a v5-enrichment crash.

The v5 image-enrichment run wrote partial output before being killed by
the OS, truncating ``data/islands.json`` mid-write.  Strategy:

1. The clean ``before-v5`` backup (6,776 islands, never modified by v5)
   is our authoritative skeleton.
2. The corrupted live file is a valid JSON array up to ~line 268,409 -
   every island object preceding that line is intact and carries any
   v5 adoptions made before the crash.
3. We stream-parse the corrupted file, salvage every complete island
   object, then merge by ``id`` into the backup (the corrupted version
   wins because it has the v5 adoptions on top).
4. Atomic write.  Never touches the backup file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TARGET = DATA / "islands.json"
BACKUP = DATA / "islands.json.before-v5"


def salvage_objects(text: str) -> list[dict]:
    """Walk the corrupted text from the start, capturing each top-level
    object as soon as its braces balance.  Stops on the first un-
    parseable object."""
    out: list[dict] = []
    i, n = 0, len(text)
    # Skip to first '['
    while i < n and text[i] != "[":
        i += 1
    i += 1
    while i < n:
        # Skip whitespace and commas.
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        if text[i] != "{":
            break
        # Find balanced brace span using a small state machine.
        depth = 0
        in_str = False
        esc = False
        start = i
        while i < n:
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start : i + 1]
                        try:
                            out.append(json.loads(chunk))
                        except json.JSONDecodeError:
                            # Stop at first unparseable - everything after
                            # is presumed truncated.
                            return out
                        i += 1
                        break
            i += 1
        else:
            # Hit EOF mid-object.
            break
    return out


def main() -> int:
    if not BACKUP.exists():
        print(f"FATAL: backup {BACKUP} missing", file=sys.stderr)
        return 2

    # Verify backup parses cleanly.
    base = json.loads(BACKUP.read_text(encoding="utf-8"))
    print(f"Backup OK: {len(base):,} islands")

    if not TARGET.exists():
        print("Live file missing; writing backup verbatim.")
        TARGET.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    # Check whether live parses.
    try:
        live = json.loads(TARGET.read_text(encoding="utf-8"))
        if isinstance(live, list) and len(live) >= len(base):
            print(f"Live file parses OK ({len(live):,} islands); nothing to recover.")
            return 0
        print(f"Live file parses but shrank ({len(live)} vs {len(base)}); will heal.")
    except json.JSONDecodeError as exc:
        print(f"Live file is corrupted: {exc}")
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive = TARGET.with_name(f"islands.json.corrupt-{ts}")
        shutil.copy2(TARGET, archive)
        print(f"  archived → {archive.name}")
        live = None

    if live is None:
        text = TARGET.read_text(encoding="utf-8")
        live = salvage_objects(text)
        print(f"Salvaged {len(live):,} islands from corrupted file")

    # Merge: live entries (with v5 adoptions) win over backup.
    by_id: dict[str, dict] = {i["id"]: i for i in base if i.get("id")}
    new_count = 0
    enriched_count = 0
    for isl in live:
        iid = isl.get("id")
        if not iid:
            continue
        if iid in by_id:
            # If the corrupted-file copy has more images, use that.
            base_imgs = len(by_id[iid].get("images") or [])
            live_imgs = len(isl.get("images") or [])
            if live_imgs > base_imgs:
                by_id[iid] = isl
                enriched_count += 1
        else:
            by_id[iid] = isl
            new_count += 1

    merged = list(by_id.values())
    print(f"Merged: {enriched_count} islands enriched, {new_count} new from live")
    print(f"Total: {len(merged):,} islands")

    tmp = TARGET.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, TARGET)

    # Read-back sanity.
    final = json.loads(TARGET.read_text(encoding="utf-8"))
    have_imgs = sum(1 for i in final if i.get("images"))
    print(f"OK: {TARGET.name} now holds {len(final):,} islands, {have_imgs:,} with images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
