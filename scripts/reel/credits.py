"""Write the photo credits page that the video's end card points to: findmyisland.com/reel/credits/"""
import json, html, os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get('REEL_WORK', REPO / '.reel-build'))
d = json.load(open(WORK / 'build' / 'data.json'))
A = d['assets']

def row(subject, key):
    a = A[key]
    lic = html.escape(a['license'])
    if a.get('licenseUrl'):
        lic = f'<a href="{html.escape(a["licenseUrl"])}">{lic}</a>'
    title = html.escape(a['title'])
    return (f'<tr><td>{html.escape(subject)}</td><td><a href="{html.escape(a["page"])}">{title}</a></td>'
            f'<td>{html.escape(a["artist"])}</td><td>{lic}</td></tr>')

sections = []
sections.append(('North to south', [row(h['name'], h['asset']) for h in d['heroes']]))
rows = []
for th in d['themes']:
    for it in th['items']:
        rows.append(row(f"{it['title']} — {it['island']} ({th['label']})", it['asset']))
sections.append(('What brings them to life', rows))
sections.append(('The wall of photographs', [row(w['name'], w['asset']) for w in d['wall']]))

n = sum(len(r) for _, r in sections)
body = '\n'.join(
    f'<h2>{html.escape(t)} <span>{len(r)}</span></h2>\n<table><thead><tr><th>Island or subject</th><th>File on Wikimedia Commons</th><th>Author</th><th>Licence</th></tr></thead><tbody>\n' + '\n'.join(r) + '\n</tbody></table>'
    for t, r in sections)

page = f'''<!doctype html>
<html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photo credits for the island reel — Find My Island</title>
<meta name="description" content="Authors and licences for the {n} photographs and artworks used in the Find My Island video.">
<style>
:root{{--bg:#0e1412;--text:#f4f0e6;--soft:#cfc6b6;--muted:#8f978f;--gold:#e4a322;--line:rgba(244,240,230,.12)}}
body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 "Familjen Grotesk","Avenir Next","Segoe UI",sans-serif}}
main{{width:min(100% - 40px,1100px);margin:0 auto;padding:64px 0 96px}}
h1{{font:400 44px/1.1 "Newsreader",Georgia,serif;margin:0 0 12px}}
h2{{font:400 28px/1.2 "Newsreader",Georgia,serif;margin:56px 0 12px}}
h2 span{{color:var(--gold);font-size:18px;margin-left:8px}}
p{{color:var(--soft);max-width:720px}}
a{{color:var(--text);text-decoration-color:var(--gold);text-underline-offset:3px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{text-align:left;color:var(--muted);font-weight:500;padding:8px 10px;border-bottom:1px solid var(--line)}}
td{{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top;color:var(--soft)}}
td:first-child{{color:var(--text)}}
.eyebrow{{color:var(--gold);letter-spacing:.24em;text-transform:uppercase;font-size:12px;font-weight:600}}
</style></head>
<body><main>
<p class="eyebrow">Find My Island</p>
<h1>Photo credits for the island reel</h1>
<p>The video uses {n} photographs and artworks from Wikimedia Commons. Each is listed below with its author and licence, as recorded on its Commons file page. Island facts and counts come from the Find My Island atlas.</p>
<p><a href="/">Back to the atlas</a></p>
{body}
</main></body></html>
'''
out = REPO / 'reel' / 'credits' / 'index.html'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(page)
print('credits rows', n)
