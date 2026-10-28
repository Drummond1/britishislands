/* Find My Island — motion reel. Deterministic canvas renderer: renderAt(seconds). */
'use strict';
const W = 1920, H = 1080;
const C = {
  bg: '#0e1412', elev: '#171f1c', soft: '#1e2924', inset: '#0a100e',
  chalk: '#f4f0e6', chalkSoft: '#cfc6b6', muted: '#8f978f', dis: '#5e675f',
  gold: '#e4a322', sea: '#7ec8c3', lake: '#8fbf8a', river: '#e4a322'
};
const TYPEC = [C.sea, C.lake, C.river];
const cv = document.getElementById('c');
const ctx = cv.getContext('2d');
ctx.imageSmoothingQuality = 'high';

// ---------- timeline (seconds)
const HERO_DUR = 1.1, THEME_DUR = 3.0;
const S = {};
S.open = [0, 4.6];
S.atlas = [4.4, 16.6];
S.sil = [16.6, 27.6];
S.voy = [27.6, 28.8];
S.hero = [28.8, 0];
S.life = [0, 0];
S.theme = [0, 0];
S.wall = [0, 0];
S.end = [0, 0];
let DUR = 0;
function buildTimeline(nHero, nTheme) {
  S.hero[1] = S.hero[0] + nHero * HERO_DUR;
  S.life = [S.hero[1], S.hero[1] + 1.2];
  S.theme = [S.life[1], S.life[1] + nTheme * THEME_DUR];
  S.wall = [S.theme[1], S.theme[1] + 9.5];
  S.end = [S.wall[1], S.wall[1] + 5.8];
  DUR = S.end[1];
}

// ---------- helpers
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lin = (t, a, b) => clamp((t - a) / (b - a));
const eo = t => 1 - Math.pow(1 - t, 3);
const eo5 = t => 1 - Math.pow(1 - t, 5);
const ei = t => t * t * t;
const eio = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const mix = (a, b, t) => a + (b - a) * t;
const fmt = n => Math.round(n).toLocaleString('en-GB');
function within(t, r, pad = 0) { return t >= r[0] - pad && t <= r[1] + pad; }

function rgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
function setFont(f, ls = 0) { ctx.font = f; ctx.letterSpacing = ls + 'px'; }
function text(str, x, y, font, color, alpha = 1, align = 'left', ls = 0, c = ctx) {
  if (alpha <= 0) return;
  c.save(); c.globalAlpha *= alpha; c.font = font; c.letterSpacing = ls + 'px';
  c.fillStyle = color; c.textAlign = align; c.textBaseline = 'alphabetic';
  c.fillText(str, x, y); c.restore();
}
function measure(str, font, ls = 0) { ctx.save(); ctx.font = font; ctx.letterSpacing = ls + 'px'; const w = ctx.measureText(str).width; ctx.restore(); return w; }
function wrap(str, font, maxW) {
  const words = str.split(' '); const lines = []; let cur = '';
  for (const w of words) {
    const t = cur ? cur + ' ' + w : w;
    if (measure(t, font) > maxW && cur) { lines.push(cur); cur = w; } else cur = t;
  }
  if (cur) lines.push(cur);
  return lines;
}
function fitText(str, font, maxW) {
  if (measure(str, font) <= maxW) return str;
  let s = str;
  while (s.length > 3 && measure(s + '…', font) > maxW) s = s.slice(0, -1);
  return s.trimEnd() + '…';
}
function drawCover(img, x, y, w, h, zoom = 1, fx = 0.5, fy = 0.5, c = ctx) {
  const iw = img.width, ih = img.height;
  const sc = Math.max(w / iw, h / ih) * zoom;
  const dw = iw * sc, dh = ih * sc;
  c.save(); c.beginPath(); c.rect(x, y, w, h); c.clip();
  c.drawImage(img, x + (w - dw) * fx, y + (h - dh) * fy, dw, dh);
  c.restore();
}
function off(w, h) { const o = document.createElement('canvas'); o.width = w; o.height = h; const c = o.getContext('2d'); c.imageSmoothingQuality = 'high'; return [o, c]; }

// ---------- data
let D, PTS, IMG = {}, LATFIT;
const POS = { ox: 1139, oy: 50, s: 980 };

async function load() {
  D = await fetch('data.json').then(r => r.json());
  PTS = D.points;
  const fonts = ['400 20px Newsreader', 'italic 300 20px Newsreader', 'italic 400 20px Newsreader', '300 20px Newsreader', '500 20px Newsreader',
    '400 20px Familjen', '500 20px Familjen', '600 20px Familjen'];
  await Promise.all(fonts.map(f => document.fonts.load(f)));
  await document.fonts.ready;
  const keys = Object.keys(D.assets);
  await Promise.all(keys.map(k => new Promise(res => {
    const im = new Image(); im.onload = () => { IMG[k] = im; res(); }; im.onerror = () => res(); im.src = D.assets[k].src;
  })));
  buildTimeline(D.heroes.length, D.themes.length);
  prep();
  return { duration: DUR, images: Object.keys(IMG).length, assets: keys.length };
}

// ---------- pre-rendered layers
let LAYER = {};
function latToNormY() {
  // least squares fit of normalised y against latitude, for the scan line
  let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const p of PTS) { n++; sx += p[4]; sy += p[1]; sxx += p[4] * p[4]; sxy += p[4] * p[1]; }
  const b = (n * sxy - sx * sy) / (n * sxx - sx * sx); const a = (sy - b * sx) / n;
  return lat => a + b * lat;
}
function dotR(p, mul = 1) { return clamp(0.85 + 0.5 * (p[3] + 3.2), 0.85, 4.0) * mul; }
function isMainland(p) { return p[3] > 4.5; }

function drawLand(c, ox, oy, s, fill, stroke, lw = 1) {
  c.save(); c.beginPath();
  for (const r of D.land) {
    c.moveTo(ox + r[0] * s, oy + r[1] * s);
    for (let i = 2; i < r.length; i += 2) c.lineTo(ox + r[i] * s, oy + r[i + 1] * s);
    c.closePath();
  }
  if (fill) { c.fillStyle = fill; c.fill('evenodd'); }
  if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw; c.stroke(); }
  c.restore();
}
function drawAllDots(c, ox, oy, s, alpha, sizeMul, colorFn) {
  for (let ty = 0; ty < 3; ty++) {
    c.fillStyle = colorFn ? colorFn(ty) : TYPEC[ty];
    c.globalAlpha = alpha;
    c.beginPath();
    for (const p of PTS) {
      if (p[2] !== ty || isMainland(p)) continue;
      const r = dotR(p, sizeMul);
      const x = ox + p[0] * s, y = oy + p[1] * s;
      c.moveTo(x + r, y); c.arc(x, y, r, 0, Math.PI * 2);
    }
    c.fill();
  }
  c.globalAlpha = 1;
}
function miniMap(s, landA, dotA, sizeMul, mono) {
  const w = Math.ceil(0.62 * s) + 24, h = Math.ceil(s) + 24;
  const [o, c] = off(w, h);
  drawLand(c, 12, 12, s, rgba(C.chalk, landA), null);
  drawAllDots(c, 12, 12, s, dotA, sizeMul, mono ? () => C.chalkSoft : null);
  return o;
}
function prep() {
  LATFIT = latToNormY();
  // atlas base land
  { const [o, c] = off(W, H); drawLand(c, POS.ox, POS.oy, POS.s, C.elev, rgba(C.chalk, 0.16), 1); LAYER.land = o; }
  // full map faint (end card)
  { const [o, c] = off(W, H); drawLand(c, POS.ox, POS.oy, POS.s, rgba(C.chalk, 0.04), null); drawAllDots(c, POS.ox, POS.oy, POS.s, 0.55, 0.9); LAYER.mapFaint = o; }
  LAYER.heroMini = miniMap(340, 0.06, 0.34, 0.5, true);
  LAYER.themeMini = miniMap(330, 0.06, 0.28, 0.5, true);
  // silhouettes: lengths
  for (const t of ['sea', 'lake', 'river']) for (const sh of D.sil[t]) {
    let L = 0; const p = sh.path;
    for (let i = 2; i < p.length; i += 2) L += Math.hypot(p[i] - p[i - 2], p[i + 1] - p[i - 1]);
    sh.len = L;
  }
  // theme backdrops (blurred, small)
  for (const th of D.themes) for (const it of th.items) {
    const im = IMG[it.asset]; if (!im) continue;
    const [o, c] = off(290, 270); c.filter = 'blur(7px) brightness(0.55) saturate(0.9)';
    drawCover(im, -20, -20, 330, 310, 1, 0.5, 0.5, c); it.blur = o;
  }
  // wall tiles
  const cols = 27, rows = 16, tw = Math.ceil(W / cols), th = Math.ceil(H / rows);
  LAYER.wall = { cols, rows, cw: W / cols, ch: H / rows, tiles: [] };
  D.wall.forEach((w, i) => {
    const im = IMG[w.asset]; const [o, c] = off(tw + 1, th + 1);
    if (im) drawCover(im, 0, 0, tw + 1, th + 1, 1, 0.5, 0.5, c);
    LAYER.wall.tiles.push(o);
  });
}

// ---------- shared chrome
function chrome(t) {
  // registration marks
  ctx.save(); ctx.strokeStyle = rgba(C.chalk, 0.22); ctx.lineWidth = 1;
  const m = 30, l = 18;
  for (const [x, y, dx, dy] of [[m, m, 1, 1], [W - m, m, -1, 1], [m, H - m, 1, -1], [W - m, H - m, -1, -1]]) {
    ctx.beginPath(); ctx.moveTo(x, y + dy * l); ctx.lineTo(x, y); ctx.lineTo(x + dx * l, y); ctx.stroke();
  }
  ctx.restore();
  // wordmark and section label
  const a = lin(t, S.atlas[0] + 0.4, S.atlas[0] + 1.2) * (1 - lin(t, S.wall[1] - 0.4, S.wall[1]));
  if (a > 0) {
    ctx.save(); ctx.globalAlpha = a;
    ctx.strokeStyle = C.gold; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.arc(76, 62, 9, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(76, 51); ctx.lineTo(79, 62); ctx.lineTo(76, 73); ctx.lineTo(73, 62); ctx.closePath(); ctx.fillStyle = C.gold; ctx.fill();
    ctx.restore();
    text('Find My Island', 96, 71, '400 27px Newsreader', C.chalk, a, 'left', -0.4);
    const sec = t < S.sil[0] ? '01   The atlas' : t < S.voy[0] ? '02   Shapes' : t < S.life[0] ? '03   North to south' : t < S.wall[0] ? '04   What brings them to life' : '05   Photographs';
    text(sec.toUpperCase(), W - 72, 68, '600 13px Familjen', C.chalkSoft, a * 0.85, 'right', 2.6);
  }
}
function eyebrow(str, x, y, a, color = C.gold) {
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = color; ctx.fillRect(x, y - 6, 34 * a, 1.5); ctx.restore();
  text(str.toUpperCase(), x + 48, y, '600 15px Familjen', color, a, 'left', 3.2);
}
function lamp(x, y, r, a) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(C.gold, 0.10 * a)); g.addColorStop(0.5, rgba(C.gold, 0.035 * a)); g.addColorStop(1, rgba(C.gold, 0));
  ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2);
}
function coastLine(x, y, w, p, a, color = C.gold) {
  // the site's hand-drawn coast rule, drawn on
  const pts = [[1, 9], [18, 9, 26, 3, 44, 4], [62, 5, 70, 12, 90, 10], [110, 8, 118, 3, 138, 5], [158, 7, 170, 13, 192, 9], [214, 5, 228, 3, 248, 6], [262, 9, 270, 12, 279, 8]];
  const sx = w / 280, sy = sx * 0.9;
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = color; ctx.lineWidth = 2.2; ctx.lineCap = 'round';
  ctx.setLineDash([w * 1.1 * p, w * 2]);
  ctx.beginPath(); ctx.moveTo(x + pts[0][0] * sx, y + pts[0][1] * sy);
  // approximate the cubic path from the SVG (C x1 y1 x2 y2 x y with smooth continuation)
  ctx.bezierCurveTo(x + 18 * sx, y + 9 * sy, x + 26 * sx, y + 3 * sy, x + 44 * sx, y + 4 * sy);
  const segs = [[62, 5, 70, 12, 90, 10], [110, 8, 118, 3, 138, 5], [158, 7, 170, 13, 192, 9], [214, 5, 228, 3, 248, 6], [262, 9, 270, 12, 279, 8]];
  for (const s of segs) ctx.bezierCurveTo(x + s[0] * sx, y + s[1] * sy, x + s[2] * sx, y + s[3] * sy, x + s[4] * sx, y + s[5] * sy);
  ctx.stroke(); ctx.restore();
}

// ---------- scene: opening
function sceneOpen(t) {
  const out = eio(lin(t, 3.85, 4.6));
  const a = 1 - out, dx = -60 * out;
  lamp(560, 520, 820, lin(t, 0, 1.6) * a);
  const x = 160 + dx;
  eyebrow('A world a little closer to home', x, 330, eo(lin(t, 0.2, 1.0)) * a);
  // Same headline as the site: two italic lines, the second in gold.
  const hf = 'italic 300 156px Newsreader';
  const a1 = eo(lin(t, 0.55, 1.45));
  text('An Atlas for', x, 486 + 24 * (1 - a1), hf, C.chalk, a1 * a, 'left', -3);
  const a2 = eo(lin(t, 0.95, 1.95));
  text('local adventures.', x, 640 + 30 * (1 - a2), hf, C.gold, a2 * a, 'left', -3);
  coastLine(x + 4, 676, 940, eo(lin(t, 1.8, 3.1)), a);
  text(fmt(D.summary.total) + ' islands around Britain and Ireland.', x + 4, 790, '400 26px Familjen', C.chalkSoft, eo(lin(t, 2.4, 3.2)) * a);
}

// ---------- scene: atlas
function sceneAtlas(t) {
  const t0 = S.atlas[0];
  const fin = eo(lin(t, t0 + 0.1, t0 + 0.9));
  const fout = 1 - eio(lin(t, S.atlas[1] - 0.7, S.atlas[1]));
  const A = fin * fout;
  const { ox, oy, s } = POS;
  ctx.save(); ctx.globalAlpha = A; ctx.drawImage(LAYER.land, 0, 0); ctx.restore();
  // scan: latitude sweeps north to south
  const scanP = eio(lin(t, t0 + 0.6, t0 + 6.6));
  const latTop = 61.6, latBot = 48.95;
  const scanLat = mix(latTop, latBot, scanP);
  // highlight phases
  const hl = [[t0 + 7.0, t0 + 8.2], [t0 + 8.2, t0 + 9.4], [t0 + 9.4, t0 + 10.6]];
  const dimOf = ty => {
    let d = 1;
    for (let k = 0; k < 3; k++) {
      const e = lin(t, hl[k][0], hl[k][0] + 0.25) * (1 - lin(t, hl[k][1] - 0.15, hl[k][1] + 0.1));
      if (e > 0) d = Math.min(d, ty === k ? 1 : mix(1, 0.18, e));
    }
    return d;
  };
  let count = 0;
  const dims = [dimOf(0), dimOf(1), dimOf(2)];
  for (let ty = 0; ty < 3; ty++) {
    ctx.fillStyle = TYPEC[ty];
    ctx.globalAlpha = 0.9 * A * dims[ty];
    ctx.beginPath();
    for (const p of PTS) {
      if (p[2] !== ty) continue;
      if (p[4] < scanLat) continue;
      if (isMainland(p)) continue;
      const r = dotR(p);
      const x = ox + p[0] * s, y = oy + p[1] * s;
      ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, Math.PI * 2);
    }
    ctx.fill();
  }
  // flash band just above the scan line
  if (scanP > 0 && scanP < 1) {
    ctx.fillStyle = C.chalk; ctx.globalAlpha = A;
    ctx.beginPath();
    for (const p of PTS) {
      const d = p[4] - scanLat;
      if (d < 0 || d > 0.32 || isMainland(p)) continue;
      const k = 1 - d / 0.32; const r = dotR(p) * (1 + 1.4 * k);
      const x = ox + p[0] * s, y = oy + p[1] * s;
      ctx.moveTo(x + r, y); ctx.arc(x, y, r, 0, Math.PI * 2);
    }
    ctx.globalAlpha = A * 0.55; ctx.fill();
  }
  ctx.globalAlpha = 1;
  for (const p of PTS) if (p[4] >= scanLat) count++;
  // scan line
  const sa = A * (1 - lin(scanP, 0.94, 1)) * lin(scanP, 0, 0.03);
  if (sa > 0) {
    const y = oy + LATFIT(scanLat) * s;
    ctx.save(); ctx.globalAlpha = sa; ctx.strokeStyle = C.gold; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(ox - 260, y); ctx.lineTo(ox + 0.66 * s, y); ctx.stroke(); ctx.restore();
    text(scanLat.toFixed(1) + '°N', ox + 0.66 * s + 14, y + 5, '500 15px Familjen', C.gold, sa, 'left', 1.5);
  }
  // Rockall, alone out west
  const rock = PTS.find(p => p[0] < -0.05 && p[4] > 57.4 && p[4] < 57.7);
  if (rock && rock[4] >= scanLat) {
    const x = ox + rock[0] * s, y = oy + rock[1] * s;
    ctx.save(); ctx.globalAlpha = A; ctx.fillStyle = C.sea; ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    text('Rockall', x + 10, y + 6, 'italic 400 18px Newsreader', C.chalkSoft, A * 0.85);
  }
  // counter
  const x0 = 160;
  eyebrow('The atlas', x0, 300, A * eo(lin(t, t0 + 0.4, t0 + 1.2)));
  const ca = A * eo(lin(t, t0 + 0.5, t0 + 1.2));
  text(fmt(count), x0 - 6, 500, '300 210px Newsreader', C.chalk, ca, 'left', -6);
  text('islands around Britain and Ireland', x0, 568, 'italic 400 44px Newsreader', C.chalkSoft, ca);
  // legend rows
  const sum = D.summary;
  const rows = [[0, sum.sea, 'at sea'], [1, sum.lake, 'in lakes and lochs'], [2, sum.river, 'in rivers']];
  rows.forEach(([ty, n, lab], k) => {
    const ra = A * eo(lin(t, hl[k][0] - 0.1, hl[k][0] + 0.45));
    if (ra <= 0) return;
    const y = 690 + k * 86;
    const active = lin(t, hl[k][0], hl[k][0] + 0.2) * (1 - lin(t, hl[k][1] - 0.1, hl[k][1] + 0.2));
    ctx.save(); ctx.globalAlpha = ra; ctx.fillStyle = TYPEC[ty];
    ctx.beginPath(); ctx.arc(x0 + 9, y - 16, 7 + 3 * active, 0, Math.PI * 2); ctx.fill(); ctx.restore();
    text(fmt(n), x0 + 36, y, '400 60px Newsreader', C.chalk, ra, 'left', -1.5);
    const nw = measure(fmt(n), '400 60px Newsreader', -1.5);
    text(lab, x0 + 36 + nw + 16, y - 4, '400 26px Familjen', mix(0, 1, 1) ? C.chalkSoft : C.muted, ra * (0.75 + 0.25 * active));
  });
}

// ---------- scene: silhouettes
const SIL_PAGES = [['sea', 'At sea'], ['lake', 'In lakes and lochs'], ['river', 'In rivers']];
function sceneSil(t) {
  const t0 = S.sil[0];
  const PAGE = (S.sil[1] - S.sil[0] - 0.3) / 3;
  const cols = 12, rows = 5, cw = 133, chh = 140, gx = 162, gy = 316;
  eyebrow('No two the same shape', 160, 160, eo(lin(t, t0, t0 + 0.6)) * (1 - lin(t, S.sil[1] - 0.4, S.sil[1])));
  for (let k = 0; k < 3; k++) {
    const ps = t0 + 0.15 + k * PAGE, pe = ps + PAGE;
    if (t < ps - 0.05 || t > pe + 0.05) continue;
    const u = t - ps;
    const pageOut = 1 - eio(lin(t, pe - 0.35, pe));
    const [ty, title] = SIL_PAGES[k];
    const tyIdx = k;
    const ha = eo(lin(u, 0, 0.45)) * pageOut;
    text(title, 160, 252 + 14 * (1 - ha), '400 66px Newsreader', C.chalk, ha, 'left', -1.2);
    const tw = measure(title, '400 66px Newsreader', -1.2);
    const n = [D.summary.sea, D.summary.lake, D.summary.river][k];
    text(fmt(n) + ' islands', 160 + tw + 26, 250, 'italic 400 34px Newsreader', TYPEC[tyIdx], ha);
    const list = D.sil[ty];
    list.forEach((sh, i) => {
      const col = i % cols, row = Math.floor(i / cols);
      const d = (col + row * 1.6) * 0.045;
      const p1 = eo(lin(u, 0.1 + d, 0.6 + d));
      const p2 = eo(lin(u, 0.45 + d, 0.85 + d));
      if (p1 <= 0) return;
      const cx = gx + col * cw + cw / 2, cy = gy + row * chh + 46;
      const box = 84;
      const path = sh.path;
      ctx.save(); ctx.globalAlpha = pageOut;
      ctx.beginPath();
      ctx.moveTo(cx + path[0] * box, cy + path[1] * box);
      for (let j = 2; j < path.length; j += 2) ctx.lineTo(cx + path[j] * box, cy + path[j + 1] * box);
      ctx.closePath();
      ctx.fillStyle = rgba(TYPEC[tyIdx], 0.24 * p2); ctx.fill();
      ctx.setLineDash([sh.len * box * p1, sh.len * box * 2]);
      ctx.strokeStyle = TYPEC[tyIdx]; ctx.lineWidth = 1.4; ctx.lineJoin = 'round'; ctx.stroke();
      ctx.restore();
      const nm = fitText(sh.name, '400 13px Familjen', cw - 14);
      text(nm, cx, cy + 74, '400 13px Familjen', C.chalkSoft, p2 * pageOut * 0.85, 'center');
    });
  }
}

// ---------- scene: voyage intro + heroes
function heroMini(t, i, a, x, y) {
  const s = 340;
  ctx.save(); ctx.globalAlpha = a;
  ctx.fillStyle = rgba(C.bg, 0.42); roundRect(x - 18, y - 18, LAYER.heroMini.width + 12, LAYER.heroMini.height + 12, 10); ctx.fill();
  ctx.drawImage(LAYER.heroMini, x - 12, y - 12);
  const P = D.heroes.map(h => [x + h.x * s, y + h.y * s]);
  // route so far
  ctx.strokeStyle = rgba(C.gold, 0.85); ctx.lineWidth = 1.4; ctx.setLineDash([3, 4]);
  ctx.beginPath(); ctx.moveTo(P[0][0], P[0][1]);
  for (let k = 1; k <= i; k++) ctx.lineTo(P[k][0], P[k][1]);
  ctx.stroke(); ctx.setLineDash([]);
  for (let k = 0; k < i; k++) { ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(P[k][0], P[k][1], 2.2, 0, Math.PI * 2); ctx.fill(); }
  const pulse = (t * 1.6) % 1;
  ctx.strokeStyle = rgba(C.gold, 1 - pulse); ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(P[i][0], P[i][1], 5 + 14 * pulse, 0, Math.PI * 2); ctx.stroke();
  ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(P[i][0], P[i][1], 4.5, 0, Math.PI * 2); ctx.fill();
  ctx.restore();
}
function roundRect(x, y, w, h, r) { ctx.beginPath(); ctx.roundRect(x, y, w, h, r); }
function sceneVoy(t) {
  const t0 = S.voy[0];
  const a = eo(lin(t, t0, t0 + 0.4)) * (1 - eio(lin(t, S.voy[1] - 0.1, S.voy[1] + 0.25)));
  lamp(600, 560, 760, a);
  eyebrow('A voyage', 160, 420, a);
  text('Twenty islands,', 160, 530, '300 104px Newsreader', C.chalk, a, 'left', -2);
  text('north to south.', 160, 640, 'italic 300 104px Newsreader', C.gold, a * eo(lin(t, t0 + 0.15, t0 + 0.6)), 'left', -2);
  // the route, drawn on
  const s = 760, x = 1270, y = 160;
  ctx.save(); ctx.globalAlpha = a; ctx.drawImage(LAYER.mapFaint, 0, 0, W, H, x - POS.ox * s / POS.s, y - POS.oy * s / POS.s, W * s / POS.s, H * s / POS.s); ctx.restore();
  const P = D.heroes.map(h => [x + h.x * s, y + h.y * s]);
  const pr = eo(lin(t, t0 + 0.1, S.voy[1]));
  const upto = pr * (P.length - 1);
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = C.gold; ctx.lineWidth = 1.6; ctx.setLineDash([4, 5]);
  ctx.beginPath(); ctx.moveTo(P[0][0], P[0][1]);
  for (let k = 1; k <= Math.floor(upto); k++) ctx.lineTo(P[k][0], P[k][1]);
  const f = upto - Math.floor(upto), k = Math.floor(upto);
  if (k + 1 < P.length) ctx.lineTo(mix(P[k][0], P[k + 1][0], f), mix(P[k][1], P[k + 1][1], f));
  ctx.stroke(); ctx.setLineDash([]);
  P.forEach((p, j) => { if (j <= upto + 0.01) { ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(p[0], p[1], 3.2, 0, Math.PI * 2); ctx.fill(); } });
  ctx.restore();
}
const HERO_FOCUS = { 'osm-relation-10221718': [0.5, 0.6], 'isle-of-skye': [0.5, 0.45], 'st-kilda': [0.5, 0.55] };
function drawHeroPhoto(i, t, start) {
  const h = D.heroes[i], im = IMG[h.asset]; if (!im) return;
  const u = clamp((t - start) / (HERO_DUR + 0.3));
  const z = mix(1.12, 1.03, eo(u));
  const dir = i % 2 ? 1 : -1;
  const f = HERO_FOCUS[h.id] || [0.5, 0.5];
  drawCover(im, 0, 0, W, H, z, clamp(f[0] + dir * 0.06 * (u - 0.5)), f[1]);
}
function drawHeroLayer(i, t, start, x0, x1) {
  const h = D.heroes[i], n = D.heroes.length;
  const u = t - start;
  ctx.save(); ctx.beginPath(); ctx.rect(x0, 0, x1 - x0, H); ctx.clip();
  drawHeroPhoto(i, t, start);
  let g = ctx.createLinearGradient(0, 0, 1250, 0);
  g.addColorStop(0, rgba(C.bg, 0.86)); g.addColorStop(0.45, rgba(C.bg, 0.5)); g.addColorStop(1, rgba(C.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  g = ctx.createLinearGradient(0, H, 0, H - 520);
  g.addColorStop(0, rgba(C.bg, 0.8)); g.addColorStop(1, rgba(C.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  g = ctx.createLinearGradient(0, 0, 0, 170);
  g.addColorStop(0, rgba(C.bg, 0.6)); g.addColorStop(1, rgba(C.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 170);
  const out = 1 - lin(t, S.hero[1] - 0.25, S.hero[1]);
  const ta = eo(lin(u, 0.16, 0.42)) * out;
  const x = 120, base = 838;
  text(String(i + 1).padStart(2, '0') + ' / ' + String(n).padStart(2, '0'), x, base - 136 + 10 * (1 - ta), '600 17px Familjen', C.gold, ta, 'left', 3);
  const nf = h.name.length > 15 ? '400 92px Newsreader' : '400 108px Newsreader';
  text(h.name, x - 4, base + 22 * (1 - ta), nf, C.chalk, ta, 'left', -2);
  const region = [h.region, h.nation].filter(Boolean).join('  ·  ').toUpperCase();
  const ta2 = eo(lin(u, 0.26, 0.5)) * out;
  text(region, x, base + 56, '500 19px Familjen', C.chalkSoft, ta2, 'left', 2.6);
  const facts = [h.water, h.area, h.coord].filter(Boolean).join('   ·   ');
  text(facts, x, base + 96, '400 23px Familjen', C.chalkSoft, ta2 * 0.9);
  const A = D.assets[h.asset];
  const credit = 'Photo: ' + fitText(A.artist, '400 14px Familjen', 300) + '  ·  ' + A.license + '  ·  Wikimedia Commons';
  text(credit, W - 72, H - 56, '400 14px Familjen', C.chalk, ta2 * 0.72, 'right');
  ctx.restore();
}
function sceneHero(t) {
  const t0 = S.hero[0];
  const n = D.heroes.length;
  const i = clamp(Math.floor((t - t0) / HERO_DUR), 0, n - 1);
  const start = t0 + i * HERO_DUR;
  const u = t - start;
  const WIPE = 0.26;
  const wp = i === 0 ? eo(lin(t, t0 - 0.15, t0 + 0.2)) : eio(clamp(u / WIPE));
  const wx = W * (1 - wp);
  const endA = 1 - eio(lin(t, S.hero[1] - 0.3, S.hero[1] + 0.05));
  if (endA <= 0) return;
  ctx.save(); ctx.globalAlpha = endA;
  if (i > 0 && u < WIPE) drawHeroLayer(i - 1, t, start - HERO_DUR, 0, wx + 1);
  drawHeroLayer(i, t, start, wx, W);
  ctx.restore();
  if (u < WIPE && i > 0) { ctx.fillStyle = C.gold; ctx.fillRect(wx - 1, 0, 2.5, H); }
  const ma = eo(lin(t, t0 - 0.1, t0 + 0.4)) * (1 - lin(t, S.hero[1] - 0.25, S.hero[1]));
  heroMini(t, i, ma, W - 96 - 0.62 * 340, 330);
}

// ---------- scene: what brings them to life
function sceneLife(t) {
  const t0 = S.life[0];
  const a = eo(lin(t, t0 + 0.05, t0 + 0.4)) * (1 - eio(lin(t, S.life[1] - 0.3, S.life[1])));
  lamp(700, 520, 800, a);
  eyebrow('Beyond the map', 160, 400, a);
  text('What brings them', 160, 512, '300 100px Newsreader', C.chalk, a, 'left', -2);
  text('to life.', 160, 616, 'italic 300 100px Newsreader', C.gold, a * eo(lin(t, t0 + 0.12, t0 + 0.5)), 'left', -2);
  // chips
  let x = 164; const y = 720; const f = '500 20px Familjen';
  const chipX = [];
  D.themes.forEach((th, k) => {
    const w = measure(th.label, f) + 40;
    const ca = a * eo(lin(t, t0 + 0.15 + k * 0.06, t0 + 0.45 + k * 0.06));
    ctx.save(); ctx.globalAlpha = ca; ctx.strokeStyle = rgba(C.chalk, 0.32); ctx.lineWidth = 1;
    roundRect(x, y - 30, w, 46, 23); ctx.stroke(); ctx.restore();
    text(th.label, x + 20, y + 1, f, C.chalk, ca);
    chipX.push([x, w]); x += w + 12;
  });
  // gold rule travelling the chips
  const p = eio(lin(t, t0 + 0.3, S.life[1]));
  const idx = Math.min(chipX.length - 1, Math.floor(p * chipX.length));
  const [cx, cw] = chipX[idx];
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = C.gold; ctx.fillRect(cx + 20, y + 26, cw - 40, 2); ctx.restore();
}
function sceneTheme(t) {
  const t0 = S.theme[0];
  const n = D.themes.length;
  const k = clamp(Math.floor((t - t0) / THEME_DUR), 0, n - 1);
  const ts = t0 + k * THEME_DUR, u = t - ts;
  const th = D.themes[k];
  const sceneA = eo(lin(t, t0, t0 + 0.35)) * (1 - eio(lin(t, S.theme[1] - 0.35, S.theme[1])));
  // right: blurred backdrop + framed print
  const items = th.items, m = items.length;
  const per = THEME_DUR / m;
  const j = clamp(Math.floor(u / per), 0, m - 1);
  const ju = u - j * per;
  const drawItem = (it, alpha, zu, capA = alpha) => {
    const im = IMG[it.asset]; if (!im) return;
    ctx.save(); ctx.globalAlpha = alpha * sceneA;
    if (it.blur) ctx.drawImage(it.blur, 760, 0, W - 760, H);
    // print
    const maxW = 1000, maxH = 690;
    const ratio = clamp(im.width / im.height, 1.3, 1.8);
    let pw = Math.min(maxW, maxH * ratio), ph = pw / ratio;
    const up = Math.max(pw / im.width, ph / im.height);
    if (up > 1.45) { pw /= up / 1.45; ph /= up / 1.45; }
    const z = mix(1.0, 1.035, zu);
    const cx = 760 + (W - 760) / 2, cy = 470;
    const x = cx - pw / 2, y = cy - ph / 2;
    ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 14;
    ctx.fillStyle = C.bg; ctx.fillRect(x, y, pw, ph);
    ctx.shadowColor = 'transparent';
    drawCover(im, x, y, pw, ph, z);
    ctx.strokeStyle = rgba(C.chalk, 0.5); ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, pw - 1, ph - 1);
    ctx.restore();
    // caption under print
    const capY = cy + ph / 2 + 64;
    text(fitText(it.title, 'italic 400 40px Newsreader', 980), x, capY, 'italic 400 40px Newsreader', C.chalk, capA * sceneA);
    text(('on ' + it.island).toUpperCase(), x, capY + 38, '600 15px Familjen', C.gold, capA * sceneA, 'left', 2.8);
    const A = D.assets[it.asset];
    const credit = fitText(A.artist, '400 14px Familjen', 280) + '  ·  ' + A.license + '  ·  Wikimedia Commons';
    text(credit, x + pw, capY + 38, '400 14px Familjen', C.chalkSoft, capA * sceneA * 0.8, 'right');
  };
  // previous theme's last item fades under the first item of this theme
  const XF = 0.22;
  const first = k === 0 && j === 0;
  const raw = first ? 1 : clamp((j === 0 ? u : ju) / XF);
  const ia = eo(raw);
  const oldCap = 1 - clamp(raw / 0.4), newCap = first ? 1 : clamp((raw - 0.4) / 0.6);
  if (j === 0 && k > 0 && u < XF) {
    const pth = D.themes[k - 1]; drawItem(pth.items[pth.items.length - 1], 1, 1, oldCap);
  } else if (j > 0 && ju < XF) {
    drawItem(items[j - 1], 1, 1, oldCap);
  }
  drawItem(items[j], ia, clamp(ju / per), newCap);
  // left panel
  ctx.save(); ctx.globalAlpha = sceneA; ctx.fillStyle = C.bg; ctx.fillRect(0, 0, 760, H);
  ctx.fillStyle = rgba(C.chalk, 0.12); ctx.fillRect(759, 0, 1, H); ctx.restore();
  const la = sceneA * eo(lin(u, 0.0, 0.4)) * (1 - (k < n - 1 ? eio(lin(u, THEME_DUR - 0.25, THEME_DUR)) : 0));
  const dy = 16 * (1 - eo(lin(u, 0, 0.4)));
  eyebrow('What brings them to life', 120, 196, sceneA);
  // progress pips
  for (let q = 0; q < n; q++) {
    ctx.save(); ctx.globalAlpha = sceneA * (q === k ? 1 : 0.35); ctx.fillStyle = q === k ? C.gold : C.chalk;
    ctx.fillRect(120 + q * 22, 236, q === k ? 16 : 10, 2); ctx.restore();
  }
  // The theme name leads. Theme collections are still being researched, so no count is shown.
  const tf = '300 92px Newsreader';
  const tl = wrap(th.label, tf, 580).slice(0, 2);
  tl.forEach((ln, q) => text(ln, 114, 400 + dy + q * 96, tf, q === tl.length - 1 ? C.gold : C.chalk, la, 'left', -2));
  const by = 400 + (tl.length - 1) * 96 + 72;
  const lines = wrap(th.blurb, '400 24px Familjen', 540);
  lines.slice(0, 3).forEach((ln, q) => text(ln, 120, by + dy + q * 34, '400 24px Familjen', C.chalkSoft, la));
  // mini map with member islands
  const s = 330, mx = 132, my = 690;
  ctx.save(); ctx.globalAlpha = sceneA; ctx.drawImage(LAYER.themeMini, mx - 12, my - 12); ctx.restore();
  ctx.save(); ctx.globalAlpha = la; ctx.fillStyle = C.gold;
  ctx.beginPath();
  th.members.forEach((p, q) => {
    const r = 3.2 * eo(lin(u, 0.1 + q * 0.004, 0.5 + q * 0.004));
    if (r <= 0) return;
    ctx.moveTo(mx + p[0] * s + r, my + p[1] * s); ctx.arc(mx + p[0] * s, my + p[1] * s, r, 0, Math.PI * 2);
  });
  ctx.fill(); ctx.restore();
  // current item locator
  const it = items[j];
  ctx.save(); ctx.globalAlpha = la; ctx.strokeStyle = C.chalk; ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.arc(mx + it.x * s, my + it.y * s, 8, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  text('On the map so far', 360, 1000, '400 17px Familjen', C.chalkSoft, la * 0.85);
  ctx.save(); ctx.globalAlpha = la; ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(348, 994, 4, 0, Math.PI * 2); ctx.fill(); ctx.restore();
}

// ---------- scene: the wall of photographs
function sceneWall(t) {
  const t0 = S.wall[0];
  const L = LAYER.wall, n = D.wall.length;
  const fill = 5.6;
  const zoomOut = eio(lin(t, S.wall[1] - 1.4, S.wall[1]));
  const sc = mix(1, 0.94, zoomOut);
  let latest = -1;
  ctx.save();
  ctx.translate(W / 2, H / 2); ctx.scale(sc, sc); ctx.translate(-W / 2, -H / 2);
  for (let i = 0; i < n; i++) {
    const ti = t0 + 0.2 + fill * Math.pow(i / n, 0.92);
    const p = eo(lin(t, ti, ti + 0.35));
    if (p <= 0) continue;
    latest = i;
    const col = i % L.cols, row = Math.floor(i / L.cols);
    const x = col * L.cw, y = row * L.ch;
    const s2 = mix(0.55, 1, p);
    ctx.globalAlpha = p;
    ctx.drawImage(L.tiles[i], x + L.cw * (1 - s2) / 2, y + L.ch * (1 - s2) / 2, L.cw * s2 + 0.6, L.ch * s2 + 0.6);
    const flash = 1 - lin(t, ti, ti + 0.5);
    if (flash > 0) { ctx.globalAlpha = flash * 0.9; ctx.strokeStyle = C.gold; ctx.lineWidth = 2; ctx.strokeRect(x + 1, y + 1, L.cw - 2, L.ch - 2); }
  }
  ctx.globalAlpha = 1; ctx.restore();
  // dim for the plate
  const plate = eo(lin(t, t0 + 6.0, t0 + 6.7));
  const toEnd = eio(lin(t, S.wall[1] - 0.9, S.wall[1]));
  ctx.fillStyle = rgba(C.bg, 0.12 + 0.48 * plate + 0.4 * toEnd); ctx.fillRect(0, 0, W, H);
  // top band for the wordmark
  const g = ctx.createLinearGradient(0, 0, 0, 150); g.addColorStop(0, rgba(C.bg, 0.85)); g.addColorStop(1, rgba(C.bg, 0));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, 150);
  // ticker band
  const ba = (1 - plate) * eo(lin(t, t0 + 0.2, t0 + 0.6));
  if (ba > 0 && latest >= 0) {
    ctx.save(); ctx.globalAlpha = ba; ctx.fillStyle = rgba(C.bg, 0.9); ctx.fillRect(0, H - 92, W, 92);
    ctx.fillStyle = C.gold; ctx.fillRect(0, H - 92, W * (latest + 1) / n, 2); ctx.restore();
    const w = D.wall[latest];
    text(w.lat.toFixed(2) + '°N', 120, H - 36, '500 18px Familjen', C.gold, ba, 'left', 2);
    text(fitText(w.name, 'italic 400 34px Newsreader', 1100), 250, H - 34, 'italic 400 34px Newsreader', C.chalk, ba);
    text(fmt(latest + 1) + ' photographs', W - 120, H - 36, '500 18px Familjen', C.chalkSoft, ba, 'right', 2);
  }
  // plate
  const pa = plate * (1 - toEnd);
  if (pa > 0) {
    const pw = 1080, ph = 330, px = (W - pw) / 2, py = (H - ph) / 2;
    ctx.save(); ctx.globalAlpha = pa; ctx.fillStyle = rgba(C.bg, 0.94); roundRect(px, py + 16 * (1 - pa), pw, ph, 6); ctx.fill();
    ctx.strokeStyle = rgba(C.gold, 0.6); ctx.lineWidth = 1; roundRect(px + 0.5, py + 16 * (1 - pa) + 0.5, pw - 1, ph - 1, 6); ctx.stroke(); ctx.restore();
    const yy = py + 16 * (1 - pa);
    eyebrow('Photographed', px + 70, yy + 80, pa);
    text(fmt(D.summary.withPhoto) + ' islands', px + 66, yy + 186, '300 104px Newsreader', C.chalk, pa, 'left', -2);
    text('pictured in the atlas, from open-licence photographs.', px + 70, yy + 252, '400 26px Familjen', C.chalkSoft, pa);
  }
}

// ---------- scene: end card
function sceneEnd(t) {
  const t0 = S.end[0];
  const a = eo(lin(t, t0, t0 + 0.7)) * (1 - eio(lin(t, S.end[1] - 0.7, S.end[1] - 0.05)));
  ctx.save(); ctx.globalAlpha = a * 0.7; ctx.drawImage(LAYER.mapFaint, 170, 0); ctx.restore();
  lamp(560, 520, 820, a);
  const x = 160;
  eyebrow('A world a little closer to home', x, 330, a * eo(lin(t, t0 + 0.1, t0 + 0.7)));
  const hf = 'italic 300 156px Newsreader';
  const a1 = eo(lin(t, t0 + 0.25, t0 + 1.0));
  text('An Atlas for', x, 486 + 20 * (1 - a1), hf, C.chalk, a * a1, 'left', -3);
  const a2 = eo(lin(t, t0 + 0.45, t0 + 1.2));
  text('local adventures.', x, 640 + 24 * (1 - a2), hf, C.gold, a * a2, 'left', -3);
  coastLine(x + 4, 676, 940, eo(lin(t, t0 + 0.8, t0 + 1.8)), a);
  const a3 = eo(lin(t, t0 + 1.2, t0 + 1.9));
  text('findmyisland.com', x + 4, 790, '600 40px Familjen', C.gold, a * a3, 'left', 1.5);
  text('The British & Irish Islands Atlas', x + 4, 838, '400 24px Familjen', C.chalkSoft, a * a3);
  text('Photographs: Wikimedia Commons contributors, each credited at findmyisland.com/reel/credits', x + 4, H - 66, '400 15px Familjen', C.muted, a * a3);
}

// ---------- frame
function renderAt(t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1; ctx.filter = 'none'; ctx.letterSpacing = '0px';
  ctx.fillStyle = C.bg; ctx.fillRect(0, 0, W, H);
  if (within(t, S.open)) sceneOpen(t);
  if (within(t, S.atlas)) sceneAtlas(t);
  if (within(t, S.sil)) sceneSil(t);
  if (within(t, S.voy, 0.3)) sceneVoy(t);
  if (within(t, S.hero, 0.2) && t >= S.hero[0] - 0.15) sceneHero(t);
  if (within(t, S.life, 0.2)) sceneLife(t);
  if (within(t, S.theme) && t >= S.theme[0] - 0.1) sceneTheme(t);
  if (within(t, S.wall)) sceneWall(t);
  if (within(t, S.end)) sceneEnd(t);
  chrome(t);
}
window.REEL = { load, renderAt, get duration() { return DUR; }, S };
