"""Photo Finder Agent — licence-safe images for verified candidates."""

from __future__ import annotations

import re
import sys
import time
import urllib.parse
from typing import Any

from . import common as c


COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def _commons_meta(filename: str) -> dict:
    cache = c.load_json(c.CACHE_COMMONS, {})
    if filename in cache:
        return cache[filename]
    params = {
        "action": "query",
        "titles": f"File:{filename}",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 640,
        "format": "json",
    }
    payload = c.get_json(COMMONS_API, params)
    pages = (payload.get("query") or {}).get("pages") or {}
    meta: dict[str, Any] = {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata") or {}

        def take(key: str) -> str:
            return ((ext.get(key) or {}).get("value") or "").strip()

        meta = {
            "url": info.get("thumburl") or info.get("url") or "",
            "fullUrl": info.get("url") or "",
            "license": take("LicenseShortName"),
            "attribution": take("Artist") or take("Credit"),
            "sourcePageUrl": info.get("descriptionurl") or "",
            "caption": take("ImageDescription"),
        }
        break
    cache[filename] = meta
    c.save_json(c.CACHE_COMMONS, cache)
    time.sleep(c.DELAY_S)
    return meta


def _p18_for_qid(qid: str) -> str | None:
    entity = c.load_json(c.CACHE_WD, {}).get(qid)
    if not entity:
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "claims",
            "format": "json",
        }
        payload = c.get_json("https://www.wikidata.org/w/api.php", params)
        entity = (payload.get("entities") or {}).get(qid) or {}
    claim = ((entity.get("claims") or {}).get("P18") or [{}])[0]
    value = (claim.get("mainsnak") or {}).get("datavalue", {}).get("value")
    if not value:
        return None
    return str(value)


def _image_from_osm_tags(candidate: dict) -> str | None:
    # The scanner does not persist raw tags; rely on verified wikidata / wikipedia only.
    return None


def _image_from_wikipedia(url: str) -> dict | None:
    if not url:
        return None
    m = re.search(r"https://([a-z-]+)\.wikipedia\.org/wiki/([^?#]+)", url)
    if not m:
        return None
    lang, title = m.group(1), urllib.parse.unquote(m.group(2).replace("_", " "))
    params = {
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "piprop": "thumbnail|original",
        "pithumbsize": 640,
        "format": "json",
    }
    api = f"https://{lang}.wikipedia.org/w/api.php"
    payload = c.get_json(api, params)
    pages = (payload.get("query") or {}).get("pages") or {}
    for page in pages.values():
        thumb = page.get("thumbnail") or {}
        original = page.get("original") or {}
        source_url = thumb.get("source") or original.get("source")
        if not source_url:
            return None
        filename = source_url.rsplit("/", 1)[-1]
        filename = urllib.parse.unquote(filename).replace("_", " ")
        meta = _commons_meta(filename)
        if not c.license_ok(meta.get("license")):
            return None
        return {
            "url": meta.get("url") or source_url,
            "fullUrl": meta.get("fullUrl") or original.get("source") or source_url,
            "caption": meta.get("caption") or candidate_caption(title),
            "source": "wikipedia-pageimage",
            "sourceRef": title,
            "sourcePageUrl": meta.get("sourcePageUrl") or url,
            "license": meta.get("license"),
            "attribution": meta.get("attribution") or f"Via {lang}.wikipedia.org",
            "primary": True,
        }
    return None


def candidate_caption(title: str) -> str:
    return title.replace("_", " ")


def _image_from_wikidata(qid: str) -> dict | None:
    filename = _p18_for_qid(qid)
    if not filename:
        return None
    meta = _commons_meta(filename)
    if not c.license_ok(meta.get("license")):
        return None
    return {
        "url": meta.get("url") or "",
        "fullUrl": meta.get("fullUrl") or meta.get("url") or "",
        "caption": meta.get("caption") or filename,
        "source": "wikidata-p18",
        "sourceRef": qid,
        "sourcePageUrl": meta.get("sourcePageUrl") or f"https://www.wikidata.org/wiki/{qid}",
        "license": meta.get("license"),
        "attribution": meta.get("attribution") or "Wikimedia Commons",
        "primary": True,
    }


def _find_photo(candidate: dict) -> dict | None:
    qid = candidate.get("wikidata") or ""
    if qid:
        image = _image_from_wikidata(qid)
        if image:
            return image
    return _image_from_wikipedia(candidate.get("wikipedia") or "")


def run(*, limit: int | None = None) -> dict[str, Any]:
    verification = c.load_json(c.VERIFY_PATH, {})
    rows = [row for row in (verification.get("records") or []) if row.get("verified")]
    if limit:
        rows = rows[:limit]

    with_photo: list[dict] = []
    without_photo: list[dict] = []
    skipped_license = 0
    for idx, row in enumerate(rows, start=1):
        image = _find_photo(row)
        payload = {**row, "image": image}
        if image:
            with_photo.append(payload)
        else:
            without_photo.append(payload)
            skipped_license += 1
        if idx % 20 == 0:
            print(f"Photo Finder: {idx}/{len(rows)}", file=sys.stderr)

    report = {
        "agent": "photo_finder",
        "inputVerified": len(rows),
        "withPhoto": len(with_photo),
        "withoutPhoto": len(without_photo),
        "skippedUnclearLicense": skipped_license,
        "records": with_photo + without_photo,
    }
    c.save_json(c.PHOTOS_PATH, report)
    print(
        f"Photo Finder: {len(with_photo)} with photo, {len(without_photo)} without",
        file=sys.stderr,
    )
    return report
