"""Compare the numbers in the published reel with the live atlas data.

Exit 0 and print 'rebuild=false' when the video is still accurate enough.
Print 'rebuild=true' (and the numbers that moved) when it should be re-rendered.
In GitHub Actions the result is also written to $GITHUB_OUTPUT.
"""
import json, os, sys
from pathlib import Path
from stats import REPO, current, changed

published = REPO / 'reel' / 'reel-stats.json'
new = current()
old = json.load(open(published))['numbers'] if published.exists() else {}
moved = changed(old, new)
force = '--force' in sys.argv
rebuild = force or bool(moved)
for k in moved:
    print(f'  {k}: {old.get(k)} -> {new[k]}')
print('rebuild=' + ('true' if rebuild else 'false'))
if os.environ.get('GITHUB_OUTPUT'):
    with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
        f.write('rebuild=' + ('true' if rebuild else 'false') + '\n')
        f.write('moved=' + ','.join(moved) + '\n')
