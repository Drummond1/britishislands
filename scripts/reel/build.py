"""Rebuild every reel video from the live atlas data, in one command.

    python3 scripts/reel/build.py            # full film + LinkedIn cut (+ homepage loop if missing)
    python3 scripts/reel/build.py --all      # also re-render the homepage loop
    python3 scripts/reel/build.py --offline  # skip downloading photos (use what is cached)

Needs: Python 3.10+ with Pillow and Shapely, Node 18+, ffmpeg. First run: `npm install` in scripts/reel
and `npx playwright install chromium`. Takes about ten minutes on a laptop.

Every number on screen is read from data/islands.json and data/interest_index.json at build time.
Chapter lengths are fixed (20 islands, 7 themes), so the music in scripts/reel/music/ stays in sync.
"""
import json, os, shutil, subprocess, sys, time, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = Path(os.environ.get('REEL_WORK', REPO / '.reel-build'))
B = WORK / 'build'
OUT = REPO / 'reel'
MUSIC = HERE / 'music'
FULL_DUR = 88.3
CUT_DUR = 15.0
PORT = os.environ.get('REEL_PORT', '8765')


def run(cmd, **kw):
    print('$', ' '.join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def ff(*args):
    run(['ffmpeg', '-v', 'error', '-y', *args])


def with_music(video, music, out, dur, vargs, fade):
    """Copy or re-encode the video and lay the score under it, trimmed, faded and loudness-normalised for the web."""
    if music and music.exists():
        af = f'atrim=0:{dur},afade=t=in:d=0.05,afade=t=out:st={dur - fade:.2f}:d={fade},loudnorm=I=-16:TP=-1.5:LRA=11'
        acodec = ['-c:a', 'libopus', '-b:a', '128k'] if str(out).endswith('.webm') else ['-c:a', 'aac', '-b:a', '160k']
        ff('-i', video, '-i', music, '-map', '0:v', '-map', '1:a', *vargs, '-af', af, *acodec, '-t', str(dur), out)
    else:
        print(f'  no music at {music}, writing silent {out.name}')
        ff('-i', video, *vargs, '-an', out)


H264 = lambda crf, maxrate: ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(crf), '-maxrate', maxrate,
                             '-bufsize', str(int(maxrate[:-1]) * 2) + 'k', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-movflags', '+faststart']
VP9 = ['-c:v', 'libvpx-vp9', '-crf', '36', '-b:v', '0', '-row-mt', '1', '-cpu-used', '5', '-deadline', 'good', '-tile-columns', '2']


def main():
    args = set(sys.argv[1:])
    t0 = time.time()
    py = sys.executable
    run([py, HERE / 'prep.py'])
    if '--offline' not in args:
        run([py, HERE / 'fetch_photos.py'])
    run([py, HERE / 'assemble.py'])
    run([py, HERE / 'credits.py'])

    # renderer files and fonts next to the data
    for f in ['reel.html', 'reel.js', 'cut.html', 'cut.js']:
        shutil.copy(HERE / f, B / f)
    fonts = B / 'fonts'; fonts.mkdir(exist_ok=True)
    nm = HERE / 'node_modules'
    if not nm.exists():
        run(['npm', 'install', '--no-audit', '--no-fund'], cwd=HERE)
    for src in [nm / '@fontsource-variable/newsreader/files/newsreader-latin-opsz-normal.woff2',
                nm / '@fontsource-variable/newsreader/files/newsreader-latin-opsz-italic.woff2',
                nm / '@fontsource/familjen-grotesk/files/familjen-grotesk-latin-400-normal.woff2',
                nm / '@fontsource/familjen-grotesk/files/familjen-grotesk-latin-500-normal.woff2',
                nm / '@fontsource/familjen-grotesk/files/familjen-grotesk-latin-600-normal.woff2']:
        shutil.copy(src, fonts / src.name)

    server = subprocess.Popen([py, '-m', 'http.server', PORT, '--bind', '127.0.0.1'], cwd=B,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    tmp = WORK / 'render'; tmp.mkdir(exist_ok=True)
    env = dict(os.environ, REEL_URL=f'http://127.0.0.1:{PORT}/')
    try:
        def render(page, out):
            run(['node', HERE / 'render.js', 'video', out], env=dict(env, PAGE=page), cwd=WORK)
        render('reel.html', tmp / 'full.mp4')
        render('cut.html?mode=linkedin', tmp / 'linkedin.mp4')
        home_needed = '--all' in args or not (OUT / 'home-loop-1080p.mp4').exists()
        if home_needed:
            render('cut.html?mode=home', tmp / 'home.mp4')
    finally:
        server.terminate()

    OUT.mkdir(exist_ok=True)
    score, sting = MUSIC / 'score-88s.mp3', MUSIC / 'sting-15s.mp3'
    with_music(tmp / 'full.mp4', score, OUT / 'islands-reel-1080p.mp4', FULL_DUR, H264(23, '4500k'), 1.2)
    with_music(tmp / 'full.mp4', score, OUT / 'islands-reel-720p.mp4', FULL_DUR, ['-vf', 'scale=1280:720:flags=lanczos', *H264(23, '2500k')], 1.2)
    with_music(tmp / 'full.mp4', score, OUT / 'islands-reel-1080p.webm', FULL_DUR, VP9, 1.2)
    with_music(tmp / 'linkedin.mp4', sting, OUT / 'islands-reel-linkedin.mp4', CUT_DUR, H264(20, '8000k'), 0.5)
    ff('-ss', '15.2', '-i', tmp / 'full.mp4', '-frames:v', '1', '-q:v', '3', OUT / 'poster.jpg')
    if home_needed:
        ff('-i', tmp / 'home.mp4', *H264(26, '3000k'), '-an', OUT / 'home-loop-1080p.mp4')
        ff('-i', tmp / 'home.mp4', '-vf', 'scale=1280:720:flags=lanczos', *H264(26, '1500k'), '-an', OUT / 'home-loop-720p.mp4')
        ff('-ss', '0.5', '-i', tmp / 'home.mp4', '-frames:v', '1', '-q:v', '3', OUT / 'home-loop-poster.jpg')

    sys.path.insert(0, str(HERE))
    from stats import current
    json.dump({'built': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
               'numbers': current()}, open(OUT / 'reel-stats.json', 'w'), indent=1)
    print(f'done in {time.time() - t0:.0f}s')


if __name__ == '__main__':
    main()
