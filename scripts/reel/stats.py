"""The numbers that appear on screen, read from the live atlas data. Shared by build.py and check_drift.py."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Theme collections are still being researched, so the film shows no theme counts and they do not trigger rebuilds.
THEMES = []


def current():
    isl = json.load(open(REPO / 'data' / 'islands.json'))
    ix = json.load(open(REPO / 'data' / 'interest_index.json'))
    cats = {c['slug']: c['count'] for c in ix['categories']}
    s = {
        'islands': len(isl),
        'sea': sum(1 for i in isl if i['type'] == 'sea'),
        'lake': sum(1 for i in isl if i['type'] == 'lake'),
        'river': sum(1 for i in isl if i['type'] == 'river'),
        'photographed': sum(1 for i in isl if i.get('images')),
    }
    for t in THEMES:
        s[t] = cats.get(t, 0)
    return s


def changed(old, new, core=0.01, theme=0.10):
    """Which on-screen numbers moved enough to be worth a re-render.

    The on-screen counts (islands, sea, lake, river, photographed) trigger at a 1% move.
    Small daily movements are ignored, so the repository is not filled with near-identical videos.
    """
    out = []
    for k, v in new.items():
        o = old.get(k)
        if o is None:
            out.append(k); continue
        limit = theme if k in THEMES else core
        if o == 0 or abs(v - o) / o >= limit:
            out.append(k)
    return out
