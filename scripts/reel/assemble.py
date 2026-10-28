"""Merge the island data with the downloaded photographs and their Commons licence metadata.

Writes .reel-build/build/data.json and .reel-build/build/photos/, which reel.js and cut.js render from.
"""
import json, os, re
from pathlib import Path
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('REEL_WORK', REPO / '.reel-build'))
P = WORK / 'photos'
B = WORK / 'build'
(B / 'photos').mkdir(parents=True, exist_ok=True)

d = json.load(open(B / 'reel-data.json'))
man = json.load(open(P / 'manifest.json'))['manifest']
by = {(x['title'], x['w']): x for x in man}

# Wall photos reviewed by eye on 26 Oct 2026 and left out: streets, maps, wind farms, buildings, paths.
REJECT = set(json.load(open(Path(__file__).with_name('wall_rejects.json'))))

assets = {}
def asset(title, w):
    x = by.get((title, w))
    if x is None:
        return None
    key = f"p{len(assets):04d}"
    im = Image.open(P / x['file']).convert('RGB')
    out = f"photos/{key}.jpg"
    im.save(B / out, quality=92)
    assets[key] = {'src': out, 'title': title, 'artist': x['artist'] or 'Unknown', 'license': x['license'],
                   'licenseUrl': x.get('licenseUrl', ''), 'page': x['page'], 'w': im.size[0], 'h': im.size[1]}
    return key

heroes = []
for h in d['heroes']:
    h['asset'] = asset(h['file'], 1920)
    if h['asset']:
        heroes.append(h)
    else:
        print('hero photo missing, skipped:', h['name'])
d['heroes'] = heroes

for th in d['themes']:
    keep = []
    for it in th['items']:
        it['asset'] = asset(it['file'], 1280)
        if it['asset']:
            keep.append(it)
    th['items'] = keep

wall = []
for t in d['wall']:
    if t['file'] in REJECT or (t['lng'] > -1.95 and t['lat'] < 50.0):
        continue
    t['asset'] = asset(t['file'], 330)
    if t['asset']:
        wall.append(t)
d['wall'] = wall[:432]

# tidy author strings for the credits page
db_credit = {w['asset']: w.get('credit') for w in d['wall']}
for k, x in assets.items():
    s = x['artist']
    m = re.search(r'copyright on this image is owned by (.+?) and is licensed', s)
    if m: s = m.group(1)
    m = re.search(r'(\S+) assumed \(based on copyright claims\)', s)
    if m: s = m.group(1)
    s = re.sub(r'^Original uploader was (\S+) at .*$', r'\1', s)
    s = re.sub(r'^taken by ([^,]+),.*$', r'\1', s)
    if s in ('', 'Unknown') and db_credit.get(k):
        m = re.match(r'Photo by (.+?) \(', db_credit[k] or '')
        s = m.group(1) if m else s
    x['artist'] = s.strip() if s.strip() not in ('', 'Unknown') else 'Author not recorded on the file page'

d['assets'] = assets
json.dump(d, open(B / 'data.json', 'w'), ensure_ascii=False)
print('heroes', len(heroes), 'theme items', sum(len(t['items']) for t in d['themes']), 'wall', len(d['wall']), 'assets', len(assets))
if len(heroes) != 20 or len(d['themes']) != 7 or len(d['wall']) < 400:
    raise SystemExit('Unexpected shape: the music is timed to 20 islands, 7 themes and a full wall. Check prep.py picks.')
