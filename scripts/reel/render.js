// Usage: node render.js stills 1,5.2,9  |  node render.js video out.mp4 [start] [end]   (PAGE=cut.html?mode=linkedin, REEL_URL=http://127.0.0.1:8765/)
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');

(async () => {
  const [mode, arg, a2, a3] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu-vsync'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on('console', m => { if (m.type() === 'error') console.error('PAGE', m.text()); });
  page.on('pageerror', e => console.error('PAGEERR', e.message));
  await page.goto((process.env.REEL_URL || 'http://127.0.0.1:8765/') + (process.env.PAGE || 'reel.html'));
  const info = await page.evaluate(() => window.REEL.load());
  console.error('loaded', JSON.stringify(info), JSON.stringify(await page.evaluate(() => window.REEL.S)));
  const grab = (t, q) => page.evaluate(([t, q]) => { window.REEL.renderAt(t); return document.getElementById('c').toDataURL('image/jpeg', q); }, [t, q]);
  if (mode === 'stills') {
    fs.mkdirSync('stills', { recursive: true });
    for (const s of arg.split(',')) {
      const t = parseFloat(s);
      const d = await grab(t, 0.9);
      fs.writeFileSync(`stills/${process.env.TAG || ''}t${t.toFixed(2)}.jpg`, Buffer.from(d.split(',')[1], 'base64'));
    }
  } else if (mode === 'video') {
    const fps = 30;
    const dur = info.duration;
    const start = a2 ? parseFloat(a2) : 0, end = a3 ? parseFloat(a3) : dur;
    const n = Math.round((end - start) * fps);
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-movflags', '+faststart', arg], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let f = 0; f < n; f++) {
      const d = await grab(start + f / fps, 0.95);
      const buf = Buffer.from(d.split(',')[1], 'base64');
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (f % 150 === 0) console.error(`frame ${f}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
    console.error('done', n, 'frames in', ((Date.now() - t0) / 1000).toFixed(0), 's');
  }
  await browser.close();
})();
