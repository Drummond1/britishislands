/* Find My Island — 15-second cuts. ?mode=linkedin (1080x1350, with end card) or ?mode=home (1920x1080, text-light seamless loop). */
'use strict';
const MODE = new URLSearchParams(location.search).get('mode') || 'linkedin';
const W = MODE === 'home' ? 1920 : 1080, H = MODE === 'home' ? 1080 : 1350;
const DUR = 15.0;
const C = { bg: '#0e1412', elev: '#171f1c', chalk: '#f4f0e6', chalkSoft: '#cfc6b6', muted: '#8f978f', gold: '#e4a322', sea: '#7ec8c3', lake: '#8fbf8a', river: '#e4a322' };
const TYPEC = [C.sea, C.lake, C.river];
const cv = document.getElementById('c'); cv.width = W; cv.height = H; cv.style.width = W + 'px'; cv.style.height = H + 'px';
const ctx = cv.getContext('2d'); ctx.imageSmoothingQuality = 'high';

const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lin = (t, a, b) => clamp((t - a) / (b - a));
const eo = t => 1 - Math.pow(1 - t, 3);
const eio = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mix = (a, b, t) => a + (b - a) * t;
const fmt = n => Math.round(n).toLocaleString('en-GB');
function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
function text(str, x, y, font, color, alpha = 1, align = 'left', ls = 0) {
  if (alpha <= 0) return;
  ctx.save(); ctx.globalAlpha *= alpha; ctx.font = font; ctx.letterSpacing = ls + 'px';
  ctx.fillStyle = color; ctx.textAlign = align; ctx.fillText(str, x, y); ctx.restore();
}
function measure(str, font, ls = 0) { ctx.save(); ctx.font = font; ctx.letterSpacing = ls + 'px'; const w = ctx.measureText(str).width; ctx.restore(); return w; }
function fitFont(str, size, weight, family, maxW, style = '') {
  let s = size; while (s > 20 && measure(str, `${style} ${weight} ${s}px ${family}`) > maxW) s -= 2;
  return `${style} ${weight} ${s}px ${family}`;
}
function drawCover(img, x, y, w, h, zoom = 1, fx = 0.5, fy = 0.5, c = ctx) {
  const sc = Math.max(w / img.width, h / img.height) * zoom; const dw = img.width * sc, dh = img.height * sc;
  c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip(); c.drawImage(img, x + (w - dw) * fx, y + (h - dh) * fy, dw, dh); c.restore();
}
function off(w, h) { const o = document.createElement('canvas'); o.width = w; o.height = h; const c = o.getContext('2d'); c.imageSmoothingQuality = 'high'; return [o, c]; }
function eyebrow(str, x, y, a, size = 15) {
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = C.gold; ctx.fillRect(x, y - size * 0.42, 34, 1.5); ctx.restore();
  text(str.toUpperCase(), x + 48, y, `600 ${size}px Familjen`, C.gold, a, 'left', size * 0.21);
}
function lamp(x, y, r, a) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(C.gold, 0.10 * a)); g.addColorStop(0.5, rgba(C.gold, 0.035 * a)); g.addColorStop(1, rgba(C.gold, 0));
  ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
}
function marks() {
  ctx.save(); ctx.strokeStyle = rgba(C.chalk, 0.22); ctx.lineWidth = 1; const m = 26, l = 16;
  for (const [x, y, dx, dy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]]) { ctx.beginPath(); ctx.moveTo(x, y + dy * l); ctx.lineTo(x, y); ctx.lineTo(x + dx * l, y); ctx.stroke(); }
  ctx.restore();
}
function wordmark(x, y, a, size = 27) {
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = C.gold; ctx.lineWidth = 1.3;
  const r = size / 3; ctx.beginPath(); ctx.arc(x, y - size * 0.33, r, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x, y - size * 0.33 - r); ctx.lineTo(x + r / 3, y - size * 0.33); ctx.lineTo(x, y - size * 0.33 + r); ctx.lineTo(x - r / 3, y - size * 0.33); ctx.closePath(); ctx.fillStyle = C.gold; ctx.fill(); ctx.restore();
  text('Find My Island', x + r + 12, y, `400 ${size}px Newsreader`, C.chalk, a, 'left', -0.4);
}
function coastLine(x, y, w, p, a) {
  const sx = w / 280, sy = sx * 0.9;
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = C.gold; ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.setLineDash([w * 1.1 * p, w * 2]);
  ctx.beginPath(); ctx.moveTo(x + 1 * sx, y + 9 * sy);
  ctx.bezierCurveTo(x + 18 * sx, y + 9 * sy, x + 26 * sx, y + 3 * sy, x + 44 * sx, y + 4 * sy);
  for (const s of [[62, 5, 70, 12, 90, 10], [110, 8, 118, 3, 138, 5], [158, 7, 170, 13, 192, 9], [214, 5, 228, 3, 248, 6], [262, 9, 270, 12, 279, 8]])
    ctx.bezierCurveTo(x + s[0] * sx, y + s[1] * sy, x + s[2] * sx, y + s[3] * sy, x + s[4] * sx, y + s[5] * sy);
  ctx.stroke(); ctx.restore();
}

// ---------- data and layers
let D, PTS, IMG = {}, LAYER = {};
const byName = n => D.heroes.find(h => h.name === n);
const isMain = p => p[3] > 4.5;
const dotR = (p, m = 1) => clamp(0.85 + 0.5 * (p[3] + 3.2), 0.85, 4.0) * m;
function drawLand(c, ox, oy, s, fill, stroke) {
  c.save(); c.beginPath();
  for (const r of D.land) { c.moveTo(ox + r[0] * s, oy + r[1] * s); for (let i = 2; i < r.length; i += 2) c.lineTo(ox + r[i] * s, oy + r[i + 1] * s); c.closePath(); }
  if (fill) { c.fillStyle = fill; c.fill('evenodd'); } if (stroke) { c.strokeStyle = stroke; c.lineWidth = 1; c.stroke(); } c.restore();
}
function dots(c, ox, oy, s, alpha, mul, latMin = -99, flashLat = null) {
  for (let ty = 0; ty < 3; ty++) {
    c.fillStyle = TYPEC[ty]; c.globalAlpha = alpha; c.beginPath();
    for (const p of PTS) {
      if (p[2] !== ty || isMain(p) || p[4] < latMin) continue;
      const r = dotR(p, mul), x = ox + p[0] * s, y = oy + p[1] * s; c.moveTo(x + r, y); c.arc(x, y, r, 0, Math.PI * 2);
    }
    c.fill();
  }
  if (flashLat !== null) {
    c.fillStyle = C.chalk; c.globalAlpha = alpha * 0.55; c.beginPath();
    for (const p of PTS) {
      const d = p[4] - flashLat; if (d < 0 || d > 0.35 || isMain(p)) continue;
      const r = dotR(p, mul) * (1 + 1.4 * (1 - d / 0.35)), x = ox + p[0] * s, y = oy + p[1] * s; c.moveTo(x + r, y); c.arc(x, y, r, 0, Math.PI * 2);
    }
    c.fill();
  }
  c.globalAlpha = 1;
}

// layout per mode
const L = MODE === 'home'
  ? { map: { ox: 960 - 0.307 * 1000, oy: 40, s: 1000 } }
  : { map: { ox: 540 - 0.307 * 860, oy: 430, s: 860 } };

const HOME_HEROES = ['Eilean Donan', 'Staffa', 'Ailsa Craig', 'Devenish Island', 'Skomer', 'Fastnet Rock', 'Sark'];
const LI_HEROES = ['St Kilda (Hirta)', 'Isle of Skye', 'Eilean Donan', 'Staffa', 'Bass Rock', 'Lindisfarne', 'Inishmore', "St Michael's Mount"];
const LI_THEMES = [['island-castles', 0], ['tidal-islands', 0], ['whisky-distilleries', 0], ['film-art-music', 0]];
// focal points for tall crops (x, y in 0..1 of the overflow)
const FOCUS = { 'St Kilda (Hirta)': [0.55, 0.5], 'Isle of Skye': [0.42, 0.5], 'Eilean Donan': [0.38, 0.5], 'Staffa': [0.5, 0.5], 'Bass Rock': [0.42, 0.5], 'Lindisfarne': [0.5, 0.5], 'Inishmore': [0.62, 0.5], "St Michael's Mount": [0.5, 0.5], 'Ailsa Craig': [0.5, 0.5], 'Devenish Island': [0.5, 0.5], 'Skomer': [0.5, 0.5], 'Fastnet Rock': [0.5, 0.5], 'Sark': [0.5, 0.5] };

async function load() {
  D = await fetch('data.json').then(r => r.json()); PTS = D.points;
  await Promise.all(['400 20px Newsreader', 'italic 300 20px Newsreader', '300 20px Newsreader', 'italic 400 20px Newsreader', '400 20px Familjen', '500 20px Familjen', '600 20px Familjen'].map(f => document.fonts.load(f)));
  await document.fonts.ready;
  const need = new Set();
  [...HOME_HEROES, ...LI_HEROES].forEach(n => need.add(byName(n).asset));
  for (const [slug, k] of LI_THEMES) need.add(D.themes.find(t => t.slug === slug).items[k].asset);
  D.wall.forEach(w => need.add(w.asset));
  await Promise.all([...need].map(k => new Promise(res => { const im = new Image(); im.onload = () => { IMG[k] = im; res(); }; im.onerror = res; im.src = D.assets[k].src; })));
  const { ox, oy, s } = L.map;
  { const [o, c] = off(W, H); drawLand(c, ox, oy, s, C.elev, rgba(C.chalk, 0.16)); LAYER.land = o; }
  { const [o, c] = off(W, H); drawLand(c, ox, oy, s, C.elev, rgba(C.chalk, 0.16)); dots(c, ox, oy, s, 0.9, MODE === 'home' ? 1.05 : 0.95); LAYER.full = o; }
  // wall tiles
  const cols = MODE === 'home' ? 27 : 15, rows = MODE === 'home' ? 16 : 19;
  LAYER.wall = { cols, rows, cw: W / cols, ch: H / rows, tiles: [] };
  const tw = Math.ceil(W / cols) + 1, th = Math.ceil(H / rows) + 1;
  D.wall.slice(0, cols * rows).forEach(w => { const im = IMG[w.asset]; const [o, c] = off(tw, th); if (im) drawCover(im, 0, 0, tw, th, 1, 0.5, 0.5, c); LAYER.wall.tiles.push(o); });
  return { mode: MODE, W, H, duration: DUR };
}

// ---------- shared pieces
function photoCard(name, t, start, dur, opts = {}) {
  const h = byName(name), im = IMG[h.asset]; if (!im) return;
  const u = clamp((t - start) / (dur + 0.3));
  const f = FOCUS[name] || [0.5, 0.5];
  drawCover(im, 0, 0, W, H, mix(1.12, 1.03, eo(u)), f[0], f[1]);
}
function photoOverlay(strength = 1) {
  let g = ctx.createLinearGradient(0, H, 0, H * 0.45);
  g.addColorStop(0, rgba(C.bg, 0.88 * strength)); g.addColorStop(1, rgba(C.bg, 0)); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  g = ctx.createLinearGradient(0, 0, 0, 160); g.addColorStop(0, rgba(C.bg, 0.6 * strength)); g.addColorStop(1, rgba(C.bg, 0)); ctx.fillStyle = g; ctx.fillRect(0, 0, W, 160);
}
function regionLine(h) { return [h.region, h.nation].filter(Boolean).join('  ·  ').toUpperCase(); }
function wipeSequence(t, t0, names, dur, drawText) {
  const n = names.length, i = clamp(Math.floor((t - t0) / dur), 0, n - 1), start = t0 + i * dur, u = t - start, WIPE = 0.22;
  const wp = i === 0 ? 1 : eio(clamp(u / WIPE)), wx = W * (1 - wp);
  const layer = (k, st, x0, x1) => {
    ctx.save(); ctx.beginPath(); ctx.rect(x0, 0, x1 - x0, H); ctx.clip();
    photoCard(names[k], t, st, dur); drawText(names[k], t - st, k); ctx.restore();
  };
  if (i > 0 && u < WIPE) layer(i - 1, start - dur, 0, wx + 1);
  layer(i, start, wx, W);
  if (i > 0 && u < WIPE) { ctx.fillStyle = C.gold; ctx.fillRect(wx - 1, 0, 2.5, H); }
}

// ---------- LinkedIn: 1080 x 1350
function linkedin(t) {
  const { ox, oy, s } = L.map;
  // 0 - 3.7  the count
  if (t < 3.9) {
    const out = 1 - eio(lin(t, 3.4, 3.9));
    lamp(540, 300, 700, out);
    const scanLat = mix(61.6, 48.95, eio(lin(t, 0.25, 2.7)));
    ctx.save(); ctx.globalAlpha = out; ctx.drawImage(LAYER.land, 0, 0); ctx.restore();
    dots(ctx, ox, oy, s, 0.92 * out, 0.95, scanLat, scanLat > 49 ? scanLat : null);
    let n = 0; for (const p of PTS) if (p[4] >= scanLat) n++;
    const a = out * eo(lin(t, 0.05, 0.45));
    eyebrow('Every island, one atlas', 110, 150, a, 19);
    text(fmt(n), 104, 340, '300 236px Newsreader', C.chalk, a, 'left', -7);
    text('islands around Britain and Ireland', 110, 410, 'italic 400 48px Newsreader', C.chalkSoft, a);
  }
  // 3.7 - 9.7  eight islands, north to south
  const H0 = 3.7, HD = 0.75, HE = H0 + LI_HEROES.length * HD;
  if (t >= H0 && t < HE + 0.1) {
    const fade = eo(lin(t, H0, H0 + 0.2)) * (1 - eio(lin(t, HE - 0.15, HE + 0.1)));
    ctx.save(); ctx.globalAlpha = fade;
    wipeSequence(t, H0, LI_HEROES, HD, (name, u, k) => {
      photoOverlay();
      const h = byName(name), a = eo(lin(u, 0.1, 0.32));
      text(String(k + 1).padStart(2, '0') + ' / ' + String(LI_HEROES.length).padStart(2, '0'), 90, H - 330, '600 20px Familjen', C.gold, a, 'left', 3);
      text(h.name, 86, H - 222 + 16 * (1 - a), fitFont(h.name, 112, 400, 'Newsreader', W - 170), C.chalk, a, 'left', -2);
      text(regionLine(h), 90, H - 164, '500 22px Familjen', C.chalkSoft, a, 'left', 2.6);
      text([h.water.split(' · ')[0], h.area].filter(Boolean).join('   ·   '), 90, H - 122, '400 26px Familjen', C.chalkSoft, a * 0.9);
    });
    ctx.restore();
  }
  // 9.7 - 12.5  what brings them to life
  const T0 = HE, TD = 0.7, TE = T0 + LI_THEMES.length * TD;
  if (t >= T0 && t < TE + 0.1) {
    const k = clamp(Math.floor((t - T0) / TD), 0, LI_THEMES.length - 1), u = t - T0 - k * TD;
    const th = D.themes.find(x => x.slug === LI_THEMES[k][0]), it = th.items[LI_THEMES[k][1]];
    const fade = 1 - eio(lin(t, TE - 0.12, TE + 0.1));
    ctx.save(); ctx.globalAlpha = fade;
    drawCover(IMG[it.asset], 0, 0, W, H, mix(1.1, 1.04, eo(clamp(u / TD))));
    ctx.fillStyle = rgba(C.bg, 0.6); ctx.fillRect(0, 0, W, H); photoOverlay(0.9);
    const a = eo(lin(u, 0.0, 0.18));
    // theme name leads; collections are still growing, so no count
    const tf = '300 118px Newsreader';
    const tl = (() => { const words = th.label.split(' '), out = []; let cur = '';
      for (const w of words) { const t2 = cur ? cur + ' ' + w : w; if (measure(t2, tf, -3) > 860 && cur) { out.push(cur); cur = w; } else cur = t2; }
      if (cur) out.push(cur); return out.slice(0, 2); })();
    const ty = 700 - (tl.length - 1) * 118;
    eyebrow('What brings them to life', 110, ty - 150, 1, 19);
    tl.forEach((ln, q) => text(ln, 102, ty + q * 118 + 20 * (1 - a), tf, q === tl.length - 1 ? C.gold : C.chalk, a, 'left', -3));
    { const bf = '400 28px Familjen', words = th.blurb.split(' '), bl = []; let cur = '';
      for (const w of words) { const t2 = cur ? cur + ' ' + w : w; if (measure(t2, bf) > 860 && cur) { bl.push(cur); cur = w; } else cur = t2; }
      if (cur) bl.push(cur);
      bl.slice(0, 3).forEach((ln, q) => text(ln, 110, 790 + q * 40, bf, C.chalkSoft, a * 0.95)); }
    text((it.title + ', ' + it.island), 110, H - 110, 'italic 400 30px Newsreader', C.chalkSoft, a * 0.9);
    ctx.restore();
  }
  // 12.5 - 15  end card
  if (t >= TE - 0.05) {
    const a = eo(lin(t, TE, TE + 0.5));
    ctx.save(); ctx.globalAlpha = a * 0.55; ctx.drawImage(LAYER.full, 0, 160); ctx.restore();
    ctx.fillStyle = rgba(C.bg, 0.35 * a); ctx.fillRect(0, 0, W, H);
    lamp(540, 480, 760, a);
    eyebrow('A world a little closer to home', 110, 330, a, 19);
    // Same headline as the site, set on three lines for the portrait frame.
    const hf = 'italic 300 140px Newsreader', a2 = eo(lin(t, TE + 0.25, TE + 0.8));
    text('An Atlas for', 100, 470, hf, C.chalk, a * eo(lin(t, TE + 0.1, TE + 0.6)), 'left', -3);
    text('local', 100, 630, hf, C.gold, a * a2, 'left', -3);
    text('adventures.', 100, 790, hf, C.gold, a * a2, 'left', -3);
    coastLine(110, 830, 700, eo(lin(t, TE + 0.5, TE + 1.3)), a);
    const a3 = eo(lin(t, TE + 0.8, TE + 1.3));
    text('findmyisland.com', 110, 960, '600 52px Familjen', C.gold, a * a3, 'left', 1.5);
    text('The British & Irish Islands Atlas', 110, 1018, '400 30px Familjen', C.chalkSoft, a * a3);
    text('Photographs: Wikimedia Commons contributors. Credits: findmyisland.com/reel/credits', 110, H - 70, '400 17px Familjen', C.muted, a * a3);
  }
  wordmark(80, 82, 1 - lin(t, TE - 0.1, TE + 0.3), 30);
  marks();
}

// ---------- Homepage: 1920 x 1080, seamless, no counts
function home(t) {
  const { ox, oy, s } = L.map;
  // 0 - 4.2  the islands appear, north to south (frame 0 = empty chart, as the loop's last frame)
  if (t < 4.6) {
    const out = 1 - eio(lin(t, 4.0, 4.6));
    lamp(960, 540, 900, out * 0.8);
    ctx.save(); ctx.globalAlpha = out; ctx.drawImage(LAYER.land, 0, 0); ctx.restore();
    const scanLat = mix(61.6, 48.95, eio(lin(t, 0.15, 3.6)));
    dots(ctx, ox, oy, s, 0.92 * out, 1.05, scanLat, scanLat > 49 ? scanLat : null);
  }
  // 4.2 - 11.2  seven islands
  const H0 = 4.2, HD = 1.0, HE = H0 + HOME_HEROES.length * HD;
  if (t >= H0 && t < HE + 0.3) {
    const fade = eo(lin(t, H0, H0 + 0.4)) * (1 - eio(lin(t, HE - 0.2, HE + 0.3)));
    ctx.save(); ctx.globalAlpha = fade;
    wipeSequence(t, H0, HOME_HEROES, HD, (name, u) => {
      const g = ctx.createLinearGradient(0, H, 0, H - 300); g.addColorStop(0, rgba(C.bg, 0.7)); g.addColorStop(1, rgba(C.bg, 0)); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      const h = byName(name), a = eo(lin(u, 0.15, 0.4));
      text(h.name, 96, H - 92, 'italic 400 44px Newsreader', C.chalk, a);
      text(regionLine(h), 98, H - 54, '500 15px Familjen', C.chalkSoft, a * 0.9, 'left', 2.4);
    });
    ctx.restore();
  }
  // 11.0 - 15  the wall fills, then settles back to the empty chart
  if (t >= HE - 0.2) {
    const Lw = LAYER.wall, n = Lw.tiles.length, fill = 2.0, t0 = HE - 0.1;
    const fadeOut = 1 - eio(lin(t, DUR - 1.3, DUR - 0.25));
    ctx.save(); ctx.globalAlpha = fadeOut;
    for (let i = 0; i < n; i++) {
      // fill in a diagonal sweep so the grid reads as one surface
      const col = i % Lw.cols, row = Math.floor(i / Lw.cols);
      const ti = t0 + fill * ((col + row) / (Lw.cols + Lw.rows - 2));
      const p = eo(lin(t, ti, ti + 0.4)); if (p <= 0) continue;
      const sc = mix(0.6, 1, p);
      ctx.globalAlpha = p * fadeOut;
      ctx.drawImage(Lw.tiles[i], col * Lw.cw + Lw.cw * (1 - sc) / 2, row * Lw.ch + Lw.ch * (1 - sc) / 2, Lw.cw * sc + 0.6, Lw.ch * sc + 0.6);
    }
    ctx.restore();
    ctx.fillStyle = rgba(C.bg, 0.25 * fadeOut); ctx.fillRect(0, 0, W, H);
    // the empty chart returns under the fading wall, matching frame 0
    const back = lin(t, DUR - 1.3, DUR - 0.25);
    ctx.save(); ctx.globalAlpha = back; ctx.drawImage(LAYER.land, 0, 0); ctx.restore();
    lamp(960, 540, 900, back * 0.8);
  }
  marks();
}

function renderAt(t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.filter = 'none'; ctx.letterSpacing = '0px';
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  if (MODE === 'home') home(t); else linkedin(t);
}
window.REEL = { load, renderAt, get duration() { return DUR; }, W, H };
