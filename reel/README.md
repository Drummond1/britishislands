# Island reel

Three cuts made from the atlas data. Built by `scripts/reel/` (see its README to rebuild).

| File | Use | Sound | Numbers on screen |
|---|---|---|---|
| `islands-reel-1080p.mp4`, `islands-reel-720p.mp4`, `islands-reel-1080p.webm` | The 88-second film | Score | Yes |
| `islands-reel-linkedin.mp4` + `linkedin-thumbnail.jpg` | 15-second 4:5 cut for LinkedIn, upload the thumbnail as the cover | Sting | Yes |
| `home-loop-1080p.mp4`, `home-loop-720p.mp4` + `home-loop-poster.jpg` | 15-second silent homepage loop | None | No |
| `poster.jpg` | First-paint image for the film | — | — |
| `credits/index.html` | Author and licence for every photograph | — | — |
| `reel-stats.json` | The counts the current videos show, and when they were built | — | — |

The film and the loop start and end on the site's ink colour, so both loop without a visible cut.

## Homepage loop

The loop deliberately shows no counts, so it never goes out of date. Put the live number in the HTML beside it, read from the same index the atlas already loads.

```html
<div class="home-reel">
  <video autoplay muted loop playsinline preload="auto" poster="/reel/home-loop-poster.jpg" aria-hidden="true">
    <source src="/reel/home-loop-720p.mp4" type="video/mp4" media="(max-width: 800px)">
    <source src="/reel/home-loop-1080p.mp4" type="video/mp4">
  </video>
  <p class="home-reel__count"><span data-island-count>11,380</span> islands around Britain and Ireland</p>
</div>
```

```css
.home-reel { position: relative; aspect-ratio: 16 / 9; background: #0e1412; overflow: hidden; }
.home-reel video { width: 100%; height: 100%; object-fit: cover; display: block; }
@media (prefers-reduced-motion: reduce) { .home-reel video { display: none; } }
```

## The film

```html
<video controls playsinline preload="metadata" poster="/reel/poster.jpg"
       aria-label="Find My Island: the British and Irish islands in 88 seconds">
  <source src="/reel/islands-reel-1080p.webm" type="video/webm">
  <source src="/reel/islands-reel-720p.mp4" type="video/mp4" media="(max-width: 800px)">
  <source src="/reel/islands-reel-1080p.mp4" type="video/mp4">
</video>
<p>Photographs: Wikimedia Commons contributors. <a href="/reel/credits/">Credits</a>. Music: generated with ElevenLabs.</p>
```

The film has a score, so give it controls rather than autoplay; browsers block autoplay with sound.

## Keeping the numbers current

`.github/workflows/reel.yml` checks monthly whether the counts in `reel-stats.json` still match the data. When an on-screen count (islands, sea, lake, river, photographed) moves by 1% or more, it re-renders the film and the LinkedIn cut, commits this folder and redeploys.

The theme sections (castles, whisky, wildlife and the rest) deliberately show no counts. Those collections are still being researched, so each leads with its name and a map of the islands found so far. Run it by hand from the Actions tab at any time ("force" rebuilds regardless). The homepage loop is never rebuilt automatically because it has nothing to go stale.

## Licensing

Most photographs are CC BY-SA, so publish the film and cuts under CC BY-SA 4.0 and keep `credits/` live wherever they appear. The music was generated with ElevenLabs Music; check that the workspace plan used covers commercial use before posting.
