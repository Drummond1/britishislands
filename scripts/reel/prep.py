"""Build the data the reel renders from: points, land, silhouettes, photo picks, fetch list.

Reads the live atlas data, so every number in the video comes from data/islands.json and
data/interest_index.json at build time. Writes .reel-build/build/reel-data.json and fetchlist.json.
"""
import json, math, re, random, collections, os
from pathlib import Path
from urllib.parse import unquote
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.ops import unary_union

REPO = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('REEL_WORK', REPO / '.reel-build'))
D = str(REPO / 'data') + '/'
OUT = str(WORK / 'build') + '/'
os.makedirs(OUT, exist_ok=True)

islands = json.load(open(D + 'islands.json'))
byid = {i['id']: i for i in islands}
ix = json.load(open(D + 'interest_index.json'))
geoms = json.load(open(D + 'cache_osm_geometries.json'))

# ---- projection: Lambert azimuthal equal-area centred on the isles
L0, P0 = math.radians(-4.5), math.radians(54.6)
def proj(lng, lat):
    l, p = math.radians(lng), math.radians(lat)
    k = math.sqrt(2 / (1 + math.sin(P0) * math.sin(p) + math.cos(P0) * math.cos(p) * math.cos(l - L0)))
    x = k * math.cos(p) * math.sin(l - L0)
    y = k * (math.cos(P0) * math.sin(p) - math.sin(P0) * math.cos(p) * math.cos(l - L0))
    return x, -y  # screen y grows downwards

# frame on the main archipelago (Rockall sits off the left edge as a lone dot)
xs, ys = zip(*[proj(i['lng'], i['lat']) for i in islands if i['lng'] > -11.0])
minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
span = max(maxx - minx, maxy - miny)
def norm(lng, lat):
    x, y = proj(lng, lat)
    return round((x - minx) / span, 5), round((y - miny) / span, 5)
aspect = (maxx - minx) / (maxy - miny)

# ---- points (every island)
TYPE = {'sea': 0, 'lake': 1, 'river': 2}
pts = []
for i in islands:
    x, y = norm(i['lng'], i['lat'])
    a = i.get('areaKm2') or 0
    pts.append([x, y, TYPE.get(i['type'], 0), round(math.log10(a + 1e-4), 2), round(i['lat'], 3)])
pts.sort(key=lambda p: -p[4])  # north to south reveal order
counts = collections.Counter(i['type'] for i in islands)
nations = collections.Counter(i['nation'] for i in islands)

# ---- land (Natural Earth admin-1, dissolved and simplified)
ne = json.load(open(D + 'cache_ne10m_admin1_uk_ie.geojson'))
land = unary_union([shape(f['geometry']) for f in ne['features']]).simplify(0.008, preserve_topology=True)
polys = list(land.geoms) if isinstance(land, MultiPolygon) else [land]
landrings = []
for pg in polys:
    if pg.area < 0.01: continue
    c_ = pg.centroid
    if c_.x > 2.5 or c_.y < 49.1: continue
    ring = [norm(x, y) for x, y in pg.exterior.coords]
    landrings.append([c for xy in ring for c in xy])

# ---- silhouettes
def outer_ring(g):
    if 'coords' in g: return g['coords']
    if 'outers' in g and g['outers']:
        return max(g['outers'], key=lambda r: len(r))
    return None
def silhouette(i):
    key = f"{i.get('osmType')}:{i.get('osmId')}"
    g = geoms.get(key)
    if not g: return None
    r = outer_ring(g)
    if not r or len(r) < 24: return None
    try:
        pg = Polygon(r)
        if not pg.is_valid: pg = pg.buffer(0)
        if pg.is_empty: return None
        if isinstance(pg, MultiPolygon): pg = max(pg.geoms, key=lambda q: q.area)
        lat = i['lat']; c = math.cos(math.radians(lat))
        pts_ = [((x - i['lng']) * c, -(y - lat)) for x, y in pg.exterior.coords]
        sp = Polygon(pts_).simplify(max(Polygon(pts_).length / 900, 1e-7))
        coords = list(sp.exterior.coords)
        if len(coords) < 12: return None
        segs = [math.hypot(coords[k][0]-coords[k-1][0], coords[k][1]-coords[k-1][1]) for k in range(1, len(coords))]
        if max(segs) / sum(segs) > 0.14: return None
        full = Polygon(coords)
        if full.area / full.convex_hull.area < 0.35: return None
        sx = [p[0] for p in coords]; sy = [p[1] for p in coords]
        w, h = max(sx) - min(sx), max(sy) - min(sy); s = max(w, h)
        if s == 0: return None
        out = []
        for x, y in coords:
            out += [round((x - min(sx) - w / 2) / s, 4), round((y - min(sy) - h / 2) / s, 4)]
        return out
    except Exception:
        return None

def good_name(n):
    return n and not n.startswith('osm-') and not re.match(r'^(Island|Islet)\s*\d*$', n) and '"' not in n

random.seed(7)
sil_pages = {}
for t, want in [('sea', 60), ('lake', 60), ('river', 60)]:
    cands = [i for i in islands if i['type'] == t and good_name(i['name']) and not (i['lng'] > -1.95 and i['lat'] < 50.0) and i['lat'] < 61.0 and (i.get('areaKm2') or 0) > (0.02 if t != 'river' else 0.004)]
    random.shuffle(cands)
    cands.sort(key=lambda i: 0 if i.get('wikidata') else 1)
    seen, page = set(), []
    for i in cands:
        if i['name'] in seen: continue
        s = silhouette(i)
        if not s: continue
        seen.add(i['name'])
        page.append({'name': i['name'], 'path': s, 'area': i.get('areaKm2')})
        if len(page) >= want: break
    random.shuffle(page)
    sil_pages[t] = page

# ---- photo helpers
def file_title(u):
    m = re.search(r'File:([^?#]+)', u or '')
    if m: return unquote(m.group(1)).replace('_', ' ')
    m = re.search(r'FilePath/([^?#]+)', u or '')
    return unquote(m.group(1)).replace('_', ' ') if m else None

fetch = {}
def want_file(title, width):
    fetch[title] = max(fetch.get(title, 0), width)

def fmt_area(a):
    if not a: return None
    if a >= 100: return f"{a:,.0f} km²"
    if a >= 1: return f"{a:.1f} km²"
    return f"{a*100:.1f} ha"

def coord(lat, lng):
    return f"{abs(lat):.2f}°{'N' if lat>=0 else 'S'}  {abs(lng):.2f}°{'W' if lng<0 else 'E'}"

WATER = {'sea': 'Sea island', 'lake': 'Lake island', 'river': 'River island'}


def sil_fallback(i):
    base = re.sub(r'\s*\(.*\)', '', i['name']).strip()
    alts = {"St Michael's Mount": "St Michael's Mount", 'Lindisfarne': 'Holy Island', 'St Kilda': 'Hirta', 'Fair Isle':'Fair Isle', 'Isle of Skye':'Skye'}
    names = {base, alts.get(base, base), base.replace('Isle of ', ''), base.replace(' Island','')}
    best = None
    for j in islands:
        if j is i: continue
        nm = re.sub(r'\s*\(.*\)', '', j['name']).strip()
        if nm in names or nm.replace('Isle of ','') in names:
            dd = (j['lat']-i['lat'])**2 + (j['lng']-i['lng'])**2
            if dd < 0.05**2 and (best is None or dd < best[0]):
                s_ = silhouette(j)
                if s_: best = (dd, s_)
    return best[1] if best else None

# ---- heroes, voyage north to south
HEROES = [
 ('osm-relation-10221718', None, 'Muckle Flugga'), ('fair-isle', None, None), ('st-kilda', None, 'St Kilda (Hirta)'),
 ('isle-of-skye', 'Old_Man_of_Storr', None), ('osm-way-201511514', None, None), ('osm-way-885235014', None, None),
 ('staffa', None, None), ('osm-way-8134808', None, None), ('osm-way-3469292', None, None), ('lindisfarne', None, 'Lindisfarne'),
 ('rathlin', None, None), ('osm-way-495525351', None, None), ('osm-relation-3998376', None, None),
('osm-relation-6045552', None, None), ('osm-relation-2856487', None, None),
 ('eel-pie-island', None, None), ('wd-Q373978', None, None), ('lundy', None, None),
 ('csv-geocoded-Q24659597', None, "St Michael's Mount"), ('osm-way-2956937', None, None),
]
REGION_FIX = {'osm-relation-6045552': 'Aran Islands', 'osm-relation-2856487': 'Pembrokeshire', 'rathlin': 'County Antrim',
              'osm-relation-3998376': 'Fermanagh', 'osm-way-4560826': 'County Sligo', 'wd-Q373978': 'County Cork',
              'osm-way-201511514': 'Loch Duich'}
NATION_LABEL = {'Crown Dependency': 'Crown Dependency'}
# Sharper Commons photographs for heroes whose atlas photo is under 1,280px wide.
HERO_PHOTO = {
    'staffa': 'Staffa Island 05.jpg',
    'st-kilda': 'St Kilda - Hirta - Village Bay from SSW in 2022 (52094858541).jpg',
    'fair-isle': 'Western Fair Isle - geograph.org.uk - 4999421.jpg',
    'wd-Q373978': 'Fastnet Rock Lighthouse - geograph.org.uk - 6008802.jpg',
    'osm-way-885235014': 'Mingulay - view SSW along the beach - geograph.org.uk - 6890286.jpg',
    'osm-relation-3998376': 'Devenish 1.jpg',
}
heroes = []
for iid, pick, rename in HEROES:
    i = byid[iid]
    ims = i['images']
    im = next((m for m in ims if pick and pick in (m.get('sourcePageUrl') or '')), ims[0])
    t = HERO_PHOTO.get(iid) or file_title(im.get('sourcePageUrl') or im['url'])
    if iid in HERO_PHOTO:
        im = {'attribution': None, 'license': None}
    want_file(t, 1920)
    region = REGION_FIX.get(iid) or (i.get('archipelago') if i.get('archipelago') not in ('', '—', None) else None)
    if region and ',' in region: region = region.split(',')[0]
    water = WATER[i['type']]
    if i.get('parentWaterBody') and i['type'] != 'sea': water += ' · ' + i['parentWaterBody']['name']
    elif i['type'] != 'sea' and i.get('archipelago') not in ('', '—', None): water += ' · ' + i['archipelago']
    x, y = norm(i['lng'], i['lat'])
    heroes.append({'id': iid, 'name': rename or i['name'], 'nation': i['nation'], 'region': region if i['type']=='sea' else None,
                   'water': water, 'area': fmt_area(i.get('areaKm2')), 'coord': coord(i['lat'], i['lng']),
                   'x': x, 'y': y, 'file': t, 'credit': im.get('attribution'), 'license': im.get('license'),
                   'sil': silhouette(i) or sil_fallback(i)})

# ---- themes
def story(cat, island_id, title_sub):
    for r in ix['stories'][cat].get(island_id, []):
        if title_sub.lower() in r['title'].lower() and r.get('image'):
            return r
    raise KeyError((cat, island_id, title_sub))
def find_island(name):
    return next(i for i in islands if i['name'] == name)

THEMES = [
 ('island-castles', 'Islands with castles', [('Isle of Mull', 'Duart'), ('Peel Castle', 'Peel'), ('Stony Island', 'Cloughoughter'), ('Guernsey', 'Castle Cornet')]),
 ('whisky-distilleries', 'Whisky', [('Islay', 'Lagavulin'), ('Mainland (Orkney)', 'Highland Park'), ('Isle of Skye', 'Talisker')]),
 ('unusual-wildlife', 'Unusual wildlife', [('Puffin Island', 'puffin'), ('St Kilda (Hirta)', 'wren'), ('Brownsea Island', 'squirrel')]),
 ('local-traditions', 'Local traditions', [('Mainland (Shetland)', 'Up Helly', 'Shetland'), ("St Mary's (Isles of Scilly)", 'gig'), ('Lewis and Harris', 'Tweed')]),
 ('film-art-music', 'Film, art and music', [('Isle of Skye', 'Loch Coruisk, Isle of Skye, Dawn'), ('Isle of Skye', 'Loch Scavaig, Isle of Skye'), ('Anglesey (Ynys Môn)', 'South Stack', 'South Stack, Anglesey')]),
 ('unusual-news', 'Unusual news', [('Principality of Sealand', 'Sealand'), ('Rockall', 'Forty'), ('Canna', 'Boat names')]),
]
cats = {c['slug']: c for c in ix['categories']}
themes = []
for slug, label, picks in THEMES:
    items = []
    for pick in picks:
        iname, sub = pick[0], pick[1]
        # island ids keyed in stories; resolve by name among members of the category
        iid = next((k for k in ix['stories'].get(slug, {}) if byid.get(k, {}).get('name') == iname), None)
        if iid is None:
            print('theme item gone, skipped:', slug, iname); continue
        r = None
        for row in ix['stories'][slug][iid]:
            if sub.lower() in (row['title'] + ' ' + row['image']['pageUrl'] if row.get('image') else row['title']).lower() and row.get('image'):
                r = row; break
        if r is None:
            print('theme item gone, skipped:', slug, iname, sub); continue
        t = file_title(r['image']['pageUrl'])
        want_file(t, 1280)
        isl = byid[iid]
        lab = pick[2] if len(pick) > 2 else {'Principality of Sealand': 'Sealand', 'Peel Castle': "St Patrick's Isle"}.get(isl['name'], isl['name'])
        items.append({'title': r['title'], 'island': lab,
                      'file': t, 'credit': r['image'].get('attribution'), 'license': r['image'].get('licence'),
                      'x': norm(isl['lng'], isl['lat'])[0], 'y': norm(isl['lng'], isl['lat'])[1]})
    themes.append({'slug': slug, 'label': label, 'count': cats[slug]['count'], 'blurb': cats[slug]['blurb'], 'items': items})

# tidal: island photos
tidal_items = []
for iid, nm in [('osm-relation-1658182', 'Cramond Island'), ('osm-way-3404368', 'Lihou'), ('burgh-island', 'Burgh Island'), ('osm-way-250292715', 'Hilbre Island')]:
    i = byid[iid]; im = i['images'][0]; t = file_title(im.get('sourcePageUrl') or im['url']); want_file(t, 1280)
    st = ix['stories']['tidal-islands'].get(iid, [{}])[0].get('title', 'Tidal island')
    tidal_items.append({'title': st, 'island': nm, 'file': t, 'credit': im.get('attribution'), 'license': im.get('license'),
                        'x': norm(i['lng'], i['lat'])[0], 'y': norm(i['lng'], i['lat'])[1]})
themes.insert(3, {'slug': 'tidal-islands', 'label': 'Tidal islands', 'count': cats['tidal-islands']['count'], 'blurb': cats['tidal-islands']['blurb'], 'items': tidal_items})

# ---- the wall: hundreds of island photographs, north to south
BAD = re.compile(r'rugby|palmer arms|ram inn|boars hill|toll island|old wall|bromford|el turner|gate in wall|caisson|reef location|logboat|greenham|red gable|whitewashed cottage|outbuildings|sneuksbrae|water lilies|waterfall|rough grassland|autumn colours|bovagli|lower slopes|pound rock|roddam|elm bush|heyspan|promenade|postcard|bridge -|forestry|lochspouts|lough view near|coast path|gateway leading|ferry approaching|track on|main street|driveway|boats moored|cottage overlooking|lerwick harbour|village|oxford from|museum|church|inn,|junction|pier|kailyards|crois an|weir on|sentinel|landsat|\bmap\b|opendata|blaeu|atlas of|chart|plan |diagram|aerial photo of mapped|satellite|ordnance|\.svg|\.tif|\.pdf|logo|coat of arms|flag', re.I)
used = set(h['id'] for h in heroes)
wall_c = []
for i in islands:
    if i['id'] in used or not i.get('images') or not good_name(i['name']): continue
    if i['name'] in ('Great Britain', 'Ireland'): continue
    if i['lat'] > 61.0 or (i['lng'] > 0 and i['lat'] < 50.6): continue
    if re.search(r'Shoal|Sand Bank|Hill$|Point$|Ledge|Burrow', i['name']): continue
    im = i['images'][0]
    src = im.get('source', '')
    cap = im.get('caption', '') + ' ' + (im.get('sourcePageUrl') or '')
    if BAD.search(cap): continue
    GENERIC = {'island','isle','isles','islet','eilean','rock','rocks','holm','sgeir','sgeirean','the','of','na','nan','an','a','mor','mhor','beag','bheag','loch','lough','great','little','north','south','east','west','upper','lower','inis','inish','ynys','carreg','stack','skerry','skerries','glas','dubh','ban','island,','st'}
    import unicodedata
    def fold(s): return unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower()
    toks = [t for t in re.findall(r'[a-z]+', fold(i['name'])) if t not in GENERIC and len(t) > 2]
    capn = re.sub(r'[^a-z]', '', fold(cap))
    named = bool(toks) and any(t in capn for t in toks)
    if src == 'curated' or named:
        t = file_title(im.get('sourcePageUrl') or im['url'])
        if not t: continue
        wall_c.append((i, t, im))
# The wall keeps the photographs already reviewed by eye (wall_picks.json), so a rebuild changes the
# numbers, not the pictures. Islands that have left the atlas drop out and are topped up from new candidates.
PICKS = Path(__file__).with_name('wall_picks.json')
picked, byname = [], set()
if PICKS.exists():
    for pk in json.load(open(PICKS)):
        i = byid.get(pk['id'])
        if not i:
            continue
        im = next((m for m in i.get('images', []) if file_title(m.get('sourcePageUrl') or m.get('url')) == pk['file']), {})
        picked.append((i, pk['file'], im)); byname.add(i['name'])
random.seed(11)
random.shuffle(wall_c)
bands = collections.defaultdict(list)
for i, t, im in wall_c:
    if i['name'] in byname:
        continue
    byname.add(i['name'])
    bands[int(i['lat'] * 4)].append((i, t, im))
quota = 432 if len(picked) >= 432 else 440
while len(picked) < quota and any(bands.values()):
    for b in sorted(bands, reverse=True):
        if bands[b] and len(picked) < quota:
            picked.append(bands[b].pop())
picked.sort(key=lambda r: -r[0]['lat'])
wall = []
for i, t, im in picked:
    want_file(t, 330)
    x, y = norm(i['lng'], i['lat'])
    wall.append({'id': i['id'], 'name': i['name'], 'lat': i['lat'], 'lng': i['lng'], 'x': x, 'y': y, 'type': i['type'], 'file': t,
                 'credit': im.get('attribution'), 'license': im.get('license')})

for th in themes:
    mem = ix['members'].get(th['slug'], [])
    th['members'] = [list(norm(byid[m]['lng'], byid[m]['lat'])) for m in mem if m in byid]
summary = {'total': len(islands), 'sea': counts['sea'], 'lake': counts['lake'], 'river': counts['river'],
           'nations': nations, 'withPhoto': sum(1 for i in islands if i.get('images')), 'aspect': aspect}
json.dump({'summary': summary, 'points': pts, 'land': landrings, 'sil': sil_pages, 'heroes': heroes,
           'themes': themes, 'wall': wall}, open(OUT + 'reel-data.json', 'w'), ensure_ascii=False)
fl = [{'t': t, 'w': w} for t, w in sorted(fetch.items())]
json.dump(fl, open(OUT + 'fetchlist.json', 'w'), ensure_ascii=False)
print(summary)
print('land rings', len(landrings), 'sil', {k: len(v) for k, v in sil_pages.items()}, 'heroes', len(heroes),
      'themes', [(t['label'], len(t['items'])) for t in themes], 'wall', len(wall), 'files', len(fl),
      collections.Counter(f['w'] for f in fl))
print('hero sil missing', [h['name'] for h in heroes if not h['sil']])
