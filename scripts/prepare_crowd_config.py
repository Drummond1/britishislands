#!/usr/bin/env python3
"""Write data/crowd_suggest_config.json from env (for CI / local deploy prep).

Usage:
  CROWD_FORM_EMAIL=you@example.com python3 scripts/prepare_crowd_config.py
  python3 scripts/prepare_crowd_config.py --email you@example.com

Does not commit; run before deploy or in GitHub Actions with secret CROWD_FORM_EMAIL.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "crowd_suggest_config.json"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", help="FormSubmit inbox (overrides CROWD_FORM_EMAIL)")
    p.add_argument(
        "--provider",
        default="formsubmit",
        choices=("formsubmit", "formspree", "web3forms", "webhook", "none"),
    )
    args = p.parse_args()
    email = (args.email or os.environ.get("CROWD_FORM_EMAIL") or "").strip()
    if args.provider == "formsubmit" and not email:
        print("No email set — crowd_suggest_config.json left unchanged.")
        print("Set CROWD_FORM_EMAIL or pass --email. Production can use GitHub submit only.")
        return 0
    data = {
        "provider": args.provider,
        "formsubmitEmail": email if args.provider == "formsubmit" else "",
        "subject": "Isles of Britain — crowd island suggestion",
    }
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} (provider={args.provider})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
