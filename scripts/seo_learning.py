"""Static equivalents of the learning overlay; no canonical data writes."""
from __future__ import annotations
import html
import json
from pathlib import Path
from urllib.parse import quote, urlsplit


def esc(value):
    return html.escape(str(value or ''), quote=True)


def source_url(value):
    try:
        url = urlsplit(str(value or ''))
        return str(value) if url.scheme in ('http', 'https') and url.netloc and not url.username and not url.password else ''
    except ValueError:
        return ''


def load_learning(path: Path) -> dict:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc.get('schemaVersion') != 1:
        raise ValueError('Unsupported learning profile schema')
    return doc


def source_links(profile, ids):
    sources = {s['id']: s for s in profile.get('sources', [])}
    return ' · '.join(f'<a href="{esc(source_url(s["url"]))}">{esc(s.get("publisher") or s["label"])}</a>'
                     for sid in ids for s in [sources.get(sid, {})] if source_url(s.get('url')))


def reading_links_for(profile, islands, paths):
    rows = []
    for link in (profile or {}).get('related', []):
        island = islands.get(link['id'])
        path = paths.get(link['id'])
        if island and path:
            rows.append((path.path, island['name'], link['reason']))
    return rows


def learning_profile_html(profile, links=None):
    if not profile:
        return ''
    facts = ''.join(f'<li><h3>{esc(f["title"])}</h3><p>{esc(f["text"])} <span class="learning-source">{source_links(profile, f["sourceIds"])}</span></p></li>' for f in profile['facts'])
    timeline = ''.join(f'<li><strong>{esc(t["date"])}</strong><p>{esc(t["text"])} <span class="learning-source">{source_links(profile, t["sourceIds"])}</span></p></li>' for t in profile['timeline'])
    credits = ''.join(f'<li><a href="{esc(source_url(s["url"]))}">{esc(s["label"])}</a> · {esc(s["attribution"])} · {esc(s["licence"])}. Source checked {esc(s["checkedAt"])}.</li>' for s in profile['sources'] if source_url(s.get('url')))
    related = ''
    if links:
        related = '<section class="learning-connections"><h2>Follow the story</h2><ul>' + ''.join(f'<li><a href="{esc(path)}"><strong>{esc(name)}</strong><span>{esc(reason)}</span></a></li>' for path, name, reason in links) + '</ul></section>'
    return f'<section class="learning-profile"><h2>The island’s story</h2><p>{esc(profile["overview"])} <span class="learning-source">{source_links(profile, profile["sourceIds"])}</span></p><h2>Three things to notice</h2><ul class="learning-facts">{facts}</ul><h2>A short timeline</h2><ol class="learning-timeline">{timeline}</ol><details class="learning-sources"><summary>Reading sources and credits</summary><ul>{credits}</ul></details></section>{related}'


def journey_page_html(journey, doc, islands, paths, origin, assets):
    stops = []
    for stop in journey['stops']:
        island = islands.get(stop['id'])
        path = paths.get(stop['id'])
        profile = doc['profiles'].get(stop['id'])
        if not island or not path or not profile:
            raise ValueError('Journey refers to missing island/profile: ' + stop['id'])
        stops.append(f'<li><h2><a href="{esc(path.path)}">{esc(island["name"])}</a></h2><p>{esc(stop["note"])}</p><p>{esc(profile["hook"])} <span class="learning-source">{source_links(profile, profile["sourceIds"])}</span></p></li>')
    url = origin + '/learn/' + journey['slug'] + '/'
    body = f'<p><a href="/?journey={quote(journey["slug"])}">Open this journey in the atlas</a> · <a href="/learn/">All learning journeys</a></p><ol>{"".join(stops)}</ol>'
    return learning_page(journey['title'], journey['introduction'], url, body, assets)


def learning_page(title, intro, canonical, body, assets):
    return f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} | Find My Island</title><meta name="description" content="{esc(intro)}"><link rel="canonical" href="{esc(canonical)}">{assets}</head><body class="lp"><main class="lp-shell"><nav class="lp-nav"><a class="lp-back" href="/">← Atlas</a><a class="lp-brand" href="/learn/">Learning journeys</a></nav><header class="lp-hero"><h1>{esc(title)}</h1><p class="lp-lede">{esc(intro)}</p></header><section class="learning-journey">{body}</section><p class="lp-note"><a href="/corrections/">Report a correction</a> · <a href="/sources-licensing/">Sources and licensing</a></p></main></body></html>'''


def write_learning_pages(root, doc, islands, paths, origin, assets, hub_assets=None):
    if not doc:
        return
    directory = root / 'learn'
    directory.mkdir(exist_ok=True)
    links = []
    for journey in doc.get('journeys', []):
        out = directory / journey['slug']
        out.mkdir(exist_ok=True)
        (out/'index.html').write_text(journey_page_html(journey, doc, islands, paths, origin, assets), encoding='utf-8')
        links.append(f'<li><h2><a href="/learn/{esc(journey["slug"])}/">{esc(journey["title"])}</a></h2><p>{esc(journey["introduction"])}</p></li>')
    (directory/'index.html').write_text(learning_page('Follow a learning journey', 'Explore islands through their stories, connections and landscapes.', origin+'/learn/', '<ul>'+''.join(links)+'</ul>', hub_assets if hub_assets is not None else assets), encoding='utf-8')
