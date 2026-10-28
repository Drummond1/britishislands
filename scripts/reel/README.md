# Island reel: renderer and rebuild pipeline

Builds everything in `reel/` from the live atlas data:

| Output | What | Numbers on screen? |
|---|---|---|
| `islands-reel-1080p.mp4`, `-720p.mp4`, `-1080p.webm` | The 88-second film, with score | Yes |
| `islands-reel-linkedin.mp4` | 15-second 4:5 cut for LinkedIn, with sting | Yes |
| `home-loop-1080p.mp4`, `-720p.mp4` | 15-second silent homepage loop | No, so it never goes stale |
| `credits/index.html` | Author and licence for every photograph | — |
| `reel-stats.json` | The numbers the current videos show | — |

## How it stays current

- **Every number is read at build time** from `data/islands.json`: the 11,380 total, the sea/lake/river split, the photographed count and each island's facts. Those are the atlas's own totals.
- **Theme sections show no counts.** Castles, whisky, wildlife and the rest are collections still being researched, so they lead with the theme name and a map marked "on the map so far". The map dots come from `data/interest_index.json` at build time.
- **The timeline is fixed** (20 islands, 7 themes, 88.3 s), so the music in `music/` never needs regenerating. `assemble.py` stops the build if a change in the data would break that shape.
- **The pictures stay put.** `wall_picks.json` pins the 432 wall photographs that were checked by eye, and `wall_rejects.json` lists the ones turned down. Islands that leave the atlas drop out and are topped up from new candidates.
- **The rebuild is one command**, and `.github/workflows/reel.yml` runs it monthly when an on-screen count has moved by 1% or more. Smaller daily movements are ignored so the repository isn't filled with near-identical videos (each rebuild adds about 55 MB to git history).
- **The homepage loop carries no numbers.** Show the live count in the page's HTML beside it instead.

## Run it locally

```bash
cd scripts/reel && npm install && npx playwright install chromium && cd ../..
pip install -r scripts/reel/requirements.txt          # Pillow, Shapely; ffmpeg must be on PATH
python3 scripts/reel/check_drift.py                    # what has moved since the last build
python3 scripts/reel/build.py                          # about ten minutes
python3 scripts/reel/build.py --all                    # also re-render the homepage loop
```

Work files go in `.reel-build/` (git-ignored). Photos are cached there, so later builds only download new ones.

## Files

- `prep.py` points, coastline, outlines, photo picks, fetch list
- `fetch_photos.py` downloads from Wikimedia Commons with author and licence
- `assemble.py` merges data and photos, applies the reviewed picks
- `credits.py` writes `reel/credits/index.html`
- `reel.html` / `reel.js` the 88-second film; `cut.html` / `cut.js` the two 15-second cuts
- `render.js` renders a page frame by frame with Playwright into ffmpeg; `node render.js stills 12,40` writes stills for checking
- `stats.py`, `check_drift.py` the numbers on screen and whether they are stale
- `music/score-88s.mp3`, `music/sting-15s.mp3` generated with ElevenLabs Music (instrumental)

## Changing the film

To swap a hero island, edit `HEROES` and `HERO_PHOTO` in `prep.py` (keep it at 20). To change a theme's example photos, edit `THEMES` (keep 7 themes). Then run `build.py` and check the stills before pushing.
