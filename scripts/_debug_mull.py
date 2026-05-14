#!/usr/bin/env python3
import json, pickle, math
from shapely.geometry import Point
from shapely.strtree import STRtree

islands = json.load(open('data/islands.json'))
land = pickle.load(open('data/land_polygons.pickle', 'rb'))
polys = list(getattr(land, 'geoms', [land]))
tree = STRtree(polys)
pt = Point(-5.95, 56.45)
candidates = []
for idx in tree.query(pt, predicate='intersects'):
    p = polys[int(idx)]
    if p.contains(pt):
        c = p.centroid
        area = (p.area * 111320 * 111320 * math.cos(math.radians(c.y))) / 1e6
        candidates.append((int(idx), area, c.x, c.y))
print(f'Polygons containing Mull point: {len(candidates)}')
for idx, area, cx, cy in sorted(candidates, key=lambda x: -x[1]):
    print(f'  idx={idx}  area={area:.1f} km²  centroid=({cy:.4f},{cx:.4f})')
print()
if candidates:
    largest_idx, largest_area, *_ = max(candidates, key=lambda x: x[1])
    P = polys[largest_idx]
    Pc = P.centroid
    inside = []
    for i in islands:
        try:
            ipt = Point(i['lng'], i['lat'])
        except Exception:
            continue
        if P.contains(ipt):
            d = math.hypot(i['lng'] - Pc.x, i['lat'] - Pc.y)
            nm = i.get('name') or ''
            inside.append((d, i['id'], nm, i['lat'], i['lng']))
    inside.sort()
    print(f'Islands inside that polygon ({largest_area:.0f} km², centroid {Pc.y:.4f},{Pc.x:.4f}):')
    for d, iid, nm, lat, lng in inside[:15]:
        print(f'  d={d:.4f}  id={iid:<28}  {nm[:48]}')
