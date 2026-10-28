"""Download the photographs the reel needs from Wikimedia Commons, with author and licence.

Reads .reel-build/build/fetchlist.json (written by prep.py) and fills .reel-build/photos/:
  img/<width>/<n>.<ext>   the thumbnails
  manifest.json           title, width, file, author, licence, licence URL, Commons page

Already-downloaded files are kept, so a rebuild only fetches photos that are new.
Polite to Commons: one API call per 40 titles, standard thumbnail widths, a user agent, retries on 429.
"""
import json, os, re, sys, time, html
import urllib.parse, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('REEL_WORK', REPO / '.reel-build'))
P = WORK / 'photos'
API = 'https://commons.wikimedia.org/w/api.php'
UA = 'FindMyIslandReel/1.0 (https://www.findmyisland.com; reel build)'


def get(url, binary=False, tries=4):
    for a in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            return data if binary else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and a < tries - 1:
                time.sleep(5 * (a + 1)); continue
            raise
        except urllib.error.URLError:
            if a < tries - 1:
                time.sleep(3); continue
            raise


def strip(h):
    return html.unescape(re.sub(r'<[^>]+>', '', h or '')).strip()


def main():
    fl = json.load(open(WORK / 'build' / 'fetchlist.json'))
    P.mkdir(parents=True, exist_ok=True)
    mpath = P / 'manifest.json'
    manifest = json.load(open(mpath))['manifest'] if mpath.exists() else []
    have = {(m['title'], m['w']) for m in manifest if (P / m['file']).exists()}
    todo = [f for f in fl if (f['t'], f['w']) not in have]
    print(f'{len(fl)} photos needed, {len(todo)} to download', flush=True)
    errors = []
    by_w = {}
    for f in todo:
        by_w.setdefault(f['w'], []).append(f['t'])
    n = len(manifest)
    for w, titles in by_w.items():
        (P / 'img' / str(w)).mkdir(parents=True, exist_ok=True)
        for i in range(0, len(titles), 40):
            batch = titles[i:i + 40]
            q = urllib.parse.urlencode({'action': 'query', 'format': 'json', 'prop': 'imageinfo',
                                        'iiprop': 'url|size|extmetadata|mime', 'iiurlwidth': w, 'redirects': 1,
                                        'iiextmetadatafilter': 'Artist|LicenseShortName|LicenseUrl|Credit',
                                        'titles': '|'.join('File:' + t for t in batch)})
            r = get(API + '?' + q)
            back = {}
            for x in r['query'].get('normalized', []):
                back[x['to']] = x['from']
            for x in r['query'].get('redirects', []):
                back[x['to']] = back.get(x['from'], x['from'])
            for pg in r['query']['pages'].values():
                title = back.get(pg['title'], pg['title']).replace('File:', '', 1)
                if 'imageinfo' not in pg:
                    errors.append('missing: ' + title); continue
                ii = pg['imageinfo'][0]
                url = ii.get('thumburl') or ii['url']
                mime = ii.get('thumbmime') or ii.get('mime') or 'image/jpeg'
                ext = 'png' if 'png' in mime else 'gif' if 'gif' in mime else 'jpg'
                rel = f'img/{w}/{n:04d}.{ext}'
                try:
                    (P / rel).write_bytes(get(url, binary=True))
                except Exception as e:
                    errors.append(f'download: {title}: {e}'); continue
                m = ii.get('extmetadata', {})
                manifest.append({'title': title, 'w': w, 'file': rel, 'tw': ii.get('thumbwidth'), 'th': ii.get('thumbheight'),
                                 'artist': strip(m.get('Artist', {}).get('value')),
                                 'license': strip(m.get('LicenseShortName', {}).get('value')),
                                 'licenseUrl': m.get('LicenseUrl', {}).get('value', ''),
                                 'credit': strip(m.get('Credit', {}).get('value'))[:300],
                                 'page': ii.get('descriptionurl')})
                n += 1
                time.sleep(0.1)
            time.sleep(0.5)
            json.dump({'manifest': manifest, 'errors': errors}, open(mpath, 'w'), ensure_ascii=False, indent=1)
    json.dump({'manifest': manifest, 'errors': errors}, open(mpath, 'w'), ensure_ascii=False, indent=1)
    print(f'manifest: {len(manifest)} photos, {len(errors)} errors', flush=True)
    for e in errors[:20]:
        print('  ', e)


if __name__ == '__main__':
    sys.exit(main())
