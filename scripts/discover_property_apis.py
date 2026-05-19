#!/usr/bin/env python3
"""
Catalogue UK/IE property listing APIs for the Isles of Britain atlas.

Writes ``data/discovery/property_sources.json`` — research artefact for
adopt/reject decisions (see docs/PROPERTY-LISTINGS.md). Does not fetch listings.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "discovery" / "property_sources.json"

SOURCES = [
    {
        "id": "rightmove",
        "name": "Rightmove",
        "kind": "aggregator",
        "apiAvailable": "agent_only",
        "apiNotes": (
            "Real Time Data Feed (ADF) is for estate agents to publish stock, "
            "not a consumer search API."
        ),
        "scraping": "prohibited_by_tos",
        "redistribution": "no_public_feed",
        "decision": "reject",
        "decisionReason": "No searchable public API; scraping blocked by ETHICS.md.",
        "docsUrl": "https://media.rightmove.co.uk/ps/pdf/guides/adf/Rightmove_Real_Time_Datafeed_Specification.pdf",
    },
    {
        "id": "zoopla",
        "name": "Zoopla (ZPG)",
        "kind": "aggregator",
        "apiAvailable": "commercial_only",
        "apiNotes": "Public listings API discontinued; agent leads/performance APIs remain.",
        "scraping": "prohibited_by_tos",
        "redistribution": "partnership_required",
        "decision": "reject",
        "decisionReason": "No public listings API without ZPG commercial agreement.",
        "docsUrl": "https://developers.zoopla.co.uk/",
    },
    {
        "id": "onthemarket",
        "name": "OnTheMarket / PrimeLocation",
        "kind": "aggregator",
        "apiAvailable": "commercial_only",
        "apiNotes": "Same ZPG ecosystem as Zoopla.",
        "scraping": "prohibited_by_tos",
        "redistribution": "partnership_required",
        "decision": "reject",
        "decisionReason": "No open aggregate feed for third-party atlas use.",
        "docsUrl": "https://www.onthemarket.com/",
    },
    {
        "id": "homedata",
        "name": "Homedata UK",
        "kind": "aggregate_api",
        "apiAvailable": "yes_key_required",
        "apiNotes": (
            "REST API includes live-listings and bulk export; cites OGL underlying "
            "sources. Must confirm Terms allow static redistribution in islands.json."
        ),
        "scraping": "not_needed",
        "redistribution": "verify_terms",
        "decision": "evaluate",
        "decisionReason": "First aggregate API candidate; implement behind HOMEDATA_API_KEY.",
        "docsUrl": "https://homedata.co.uk/docs/endpoints",
    },
    {
        "id": "propertydata",
        "name": "PropertyData",
        "kind": "analytics_api",
        "apiAvailable": "paid",
        "apiNotes": "68+ endpoints; agent/market analytics focus.",
        "scraping": "not_needed",
        "redistribution": "likely_no_static",
        "decision": "defer",
        "decisionReason": "Paid; redistribution terms unlikely to suit static JSON ship.",
        "docsUrl": "https://propertydata.co.uk/api",
    },
    {
        "id": "hmlr_price_paid",
        "name": "HM Land Registry Price Paid",
        "kind": "open_government",
        "apiAvailable": "yes_ogl",
        "apiNotes": "Completed sales only — not current for-sale listings.",
        "scraping": "not_needed",
        "redistribution": "ogl_v3",
        "decision": "reject_for_feature",
        "decisionReason": "Wrong signal for 'for sale now'; useful for history only.",
        "docsUrl": "https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads",
    },
    {
        "id": "curated_specialist",
        "name": "Curated specialist brokers",
        "kind": "manual",
        "apiAvailable": "none",
        "apiNotes": (
            "Maintainer-edited data/curated_property_listings.json with outbound URLs "
            "to private-island brokers and regional agents."
        ),
        "scraping": "not_used",
        "redistribution": "link_out_only",
        "decision": "adopt",
        "decisionReason": "MVP path; ethics-safe; ships with ingest_property_listings.py.",
        "docsUrl": "docs/PROPERTY-LISTINGS.md",
    },
]


def main() -> int:
    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "purpose": "API/source catalogue for island for-sale listings feature",
        "adoptedForMvp": ["curated_specialist"],
        "evaluateNext": ["homedata"],
        "rejected": [s["id"] for s in SOURCES if s["decision"] == "reject"],
        "sources": SOURCES,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(SOURCES)} sources)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
