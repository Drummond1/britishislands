#!/usr/bin/env python3
"""
Stage a GitHub Pages deploy directory (_site/) with CI-built assets that
.gitignore hides from git but must ship to production (nation shards, profiles).

Also omits dev-only blobs (monolithic islands.json, caches, logs) so the live
site loads index + shards instead of ~40+ MiB of duplicate JSON.

Run in CI after generate_seo_artifacts.py and build_islands_index.py:
  python3 scripts/prepare_pages_artifact.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"

# Top-level / path segments never copied into the static site artifact.
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".github",
        ".cursor",
        ".venv",
        "venv",
        "__pycache__",
        "logs",
        "adapters",
        "node_modules",
        "_site",
        "scripts",
        "docs",
    }
)

# File name globs (basename patterns) skipped anywhere in the tree.
SKIP_FILE_SUFFIXES = (
    ".py",
    ".pyc",
    ".md",
    ".log",
    ".pickle",
    ".gtfs.zip",
    ".tmp",
)

SKIP_BASENAMES = frozenset(
    {
        ".DS_Store",
        ".env",
        ".env.local",
        "Thumbs.db",
    }
)

# Paths relative to repo root excluded from the artifact (bandwidth / secrets).
SKIP_REL_PATHS = frozenset(
    {
        "data/islands.json",
        "data/water_raw.json",
        "data/water_raw_v2.json",
        "data/coastline_raw.json",
        "data/osm_raw.json",
        "data/osm_ferries_raw.json",
        "data/land_polygons.pickle",
        "data/gtfs",
    }
)


def _should_skip_file(path: Path, rel: str) -> bool:
    if rel in SKIP_REL_PATHS:
        return True
    if path.name in SKIP_BASENAMES:
        return True
    if path.name.startswith(".env"):
        return True
    if path.name.startswith("cache_") and path.suffix == ".json":
        return True
    if path.name.startswith("islands.json.before-"):
        return True
    if path.suffix in SKIP_FILE_SUFFIXES and rel not in {"styles.css"}:
        # Keep .css; drop .py/.md etc. (scripts/ already excluded as dir)
        if path.suffix != ".css":
            if path.suffix in {".py", ".pyc", ".md", ".log", ".pickle"}:
                return True
    if rel.startswith("data/mlx_lora/"):
        return True
    if rel.startswith("data/cache_"):
        return True
    if rel.startswith("data/discovery/") and path.suffix == ".json":
        # Large discovery audit JSONs — not needed on the static site
        return True
    if rel.startswith("data/terrain/"):
        return True
    return False


def _copy_tree(src: Path, dst: Path) -> None:
    for item in sorted(src.iterdir()):
        rel = item.relative_to(ROOT).as_posix()
        if item.is_dir():
            if item.name in SKIP_DIR_NAMES:
                continue
            if rel in SKIP_REL_PATHS:
                continue
            _copy_tree(item, dst / item.name)
            continue
        if _should_skip_file(item, rel):
            continue
        target = dst / item.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def main() -> None:
    shards_manifest = ROOT / "data" / "shards" / "manifest.json"
    index_path = ROOT / "data" / "islands_index.json"
    if not index_path.exists():
        print("ERROR: run build_islands_index.py first", file=sys.stderr)
        sys.exit(1)
    if not shards_manifest.exists():
        print("ERROR: missing data/shards/manifest.json — run build_islands_index.py", file=sys.stderr)
        sys.exit(1)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    _copy_tree(ROOT, OUT)

    # Force-include CI outputs that .gitignore hides from git (may not be in copy_tree if absent)
    for forced in (
        ROOT / "data" / "shards",
        ROOT / "profiles",
        ROOT / "sitemap.xml",
        ROOT / "robots.txt",
        ROOT / "llms.txt",
    ):
        if not forced.exists():
            continue
        dest = OUT / forced.relative_to(ROOT)
        if forced.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(forced, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(forced, dest)

    # Explicitly drop monolithic islands.json from production (shards are canonical).
    monolith = OUT / "data" / "islands.json"
    if monolith.exists():
        monolith.unlink()

    (OUT / ".nojekyll").touch()

    shard_count = len(list((OUT / "data" / "shards").glob("*.json"))) - 1
    profile_count = len(list((OUT / "profiles").glob("*.html"))) if (OUT / "profiles").exists() else 0
    index_mb = (OUT / "data" / "islands_index.json").stat().st_size / 1024 / 1024
    print(
        f"Staged _site/ — index {index_mb:.2f} MiB, {shard_count} nation shards, "
        f"{profile_count} profile landings, monolithic islands.json omitted",
        file=sys.stderr,
    )

    if not (OUT / "data" / "shards" / "manifest.json").exists():
        print("ERROR: shards missing from _site", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
