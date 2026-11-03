/** Small, source-linked learning overlay. Canonical records and photographs stay separate. */
import { isThinCitation, scoreCitedItem } from "./interest-rank.js";

export function escapeLearning(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function sourceUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : "";
  } catch (_) { return ""; }
}

export function learningProfile(doc, id) { return doc?.profiles?.[id] || null; }

export function geographicGroups(island) {
  const valid = (label) => {
    const value = String(label || "").trim();
    return /^(?:[—–-]+|unknown|not known|n\/a)$/i.test(value) ? "" : value;
  };
  return { archipelago: valid(island.archipelago), water: valid(island.parentWaterBody?.name) };
}

export function islandReadingPath(island) {
  return /^\/islands\/[^?#<>" ]+\/$/.test(island?.seoPath || "")
    ? island.seoPath : `/?island=${encodeURIComponent(island?.id || "")}`;
}

const storyCaches = new WeakMap();
export function citedDiscoveryStories(index, island) {
  if (!index || !island?.id) return [];
  if (!storyCaches.has(index)) {
    const byId = new Map();
    for (const [slug, islands] of Object.entries(index.stories || {})) {
      for (const [id, rows] of Object.entries(islands || {})) {
        for (const item of Array.isArray(rows) ? rows : []) {
          if (!sourceUrl(item?.sourceUrl) || !item.summary || isThinCitation(item)) continue;
          if (!byId.has(id)) byId.set(id, []);
          byId.get(id).push({ ...item, collection: slug });
        }
      }
    }
    storyCaches.set(index, byId);
  }
  return (storyCaches.get(index).get(island.id) || []).slice().sort((a, b) =>
    scoreCitedItem(b.collection, island, b) - scoreCitedItem(a.collection, island, a));
}

export function discoveryHook(island, index, doc) {
  const profile = learningProfile(doc, island?.id);
  if (profile?.hook) return profile.hook;
  const order = ["unusual-news", "island-books", "local-traditions", "island-castles", "whisky-distilleries", "unusual-wildlife", "tidal-islands", "film-art-music"];
  const stories = citedDiscoveryStories(index, island).filter((s) => !/the record names|is an? (?:artwork|drawing|painting|photograph) in/i.test(s.summary));
  stories.sort((a, b) => order.indexOf(a.collection) - order.indexOf(b.collection));
  const story = stories[0];
  return story?.tie || story?.summary || island?.shortDescription || "";
}

function references(profile, ids) {
  return (ids || []).map((id) => profile.sources?.find((s) => s.id === id))
    .filter((s) => s && sourceUrl(s.url));
}

function sourceLinks(profile, ids) {
  return references(profile, ids).map((s) => `<a href="${escapeLearning(sourceUrl(s.url))}" target="_blank" rel="noopener noreferrer" aria-label="Source: ${escapeLearning(s.label)}">${escapeLearning(s.publisher || s.label)}</a>`).join(" · ");
}

export function renderLearningProfile(profile) {
  if (!profile) return "";
  const facts = (profile.facts || []).map((f) => `<li><h4>${escapeLearning(f.title)}</h4><p>${escapeLearning(f.text)} <span class="learning-source">${sourceLinks(profile, f.sourceIds)}</span></p></li>`).join("");
  const timeline = (profile.timeline || []).map((t) => `<li><strong>${escapeLearning(t.date)}</strong><p>${escapeLearning(t.text)} <span class="learning-source">${sourceLinks(profile, t.sourceIds)}</span></p></li>`).join("");
  const sources = (profile.sources || []).filter((s) => sourceUrl(s.url)).map((s) => `<li><a href="${escapeLearning(sourceUrl(s.url))}" target="_blank" rel="noopener noreferrer">${escapeLearning(s.label)}</a> · ${escapeLearning(s.publisher)}. ${escapeLearning(s.attribution)} · ${escapeLearning(s.licence)}. Source checked ${escapeLearning(s.checkedAt)}.</li>`).join("");
  return `<section class="learning-profile" aria-label="The island’s story"><h3>The island’s story</h3><p>${escapeLearning(profile.overview)} <span class="learning-source">${sourceLinks(profile, profile.sourceIds)}</span></p><h3>Three things to notice</h3><ul class="learning-facts">${facts}</ul><h3>A short timeline</h3><ol class="learning-timeline">${timeline}</ol><details class="learning-sources"><summary>Reading sources and credits</summary><ul>${sources}</ul></details></section>`;
}

export function relatedDiscoveries(island, index, doc, byId, limit = 3) {
  const result = [];
  const seen = new Set([island.id]);
  function add(id, reason) {
    if (seen.has(id) || !byId.has(id)) return;
    seen.add(id); result.push({ island: byId.get(id), reason });
  }
  for (const row of learningProfile(doc, island.id)?.related || []) add(row.id, row.reason);
  if (result.length >= limit) return result.slice(0, limit);
  const mine = citedDiscoveryStories(index, island);
  const categories = [...new Set(mine.map((s) => s.collection))];
  for (const slug of categories) {
    const label = index?.categories?.find((c) => c.slug === slug)?.label || "this theme";
    const peers = Object.keys(index?.stories?.[slug] || {}).map((id) => byId.get(id))
      .filter((other) => other && !seen.has(other.id) && citedDiscoveryStories(index, other).some((s) => s.collection === slug));
    peers.sort((a, b) => scoreCitedItem(slug, b, (index.stories[slug][b.id] || [])[0]) - scoreCitedItem(slug, a, (index.stories[slug][a.id] || [])[0]));
    for (const peer of peers) {
      add(peer.id, `Explore another island with a cited story in ${label.toLowerCase()}.`);
      if (result.length >= limit) return result;
    }
  }
  return result.slice(0, limit);
}

export function renderDiscoveryConnections(rows) {
  if (!rows.length) return "";
  return `<section class="learning-connections" aria-label="Follow the story"><h3>Follow the story</h3><ul>${rows.map(({island, reason}) => `<li><a data-learning-island="${escapeLearning(island.id)}" href="${escapeLearning(islandReadingPath(island))}"><strong>${escapeLearning(island.name)}</strong><span>${escapeLearning(reason)}</span></a></li>`).join("")}</ul></section>`;
}

export function substantiveProfileIds(doc, byId) {
  return Object.entries(doc?.profiles || {}).filter(([id, p]) => byId.has(id) && p.facts?.length >= 3 && p.sources?.some((s) => sourceUrl(s.url))).map(([id]) => id);
}

export function surpriseIsland(doc, byId, exclude = [], random = Math.random) {
  const all = substantiveProfileIds(doc, byId);
  const candidates = all.filter((id) => !exclude.includes(id));
  const pool = candidates.length ? candidates : all.filter((id) => id !== exclude[0]);
  if (!pool.length) return null;
  return byId.get(pool[Math.min(pool.length - 1, Math.floor(Math.max(0, random()) * pool.length))]);
}

export function weeklyIsland(doc, byId, date = new Date()) {
  const ids = substantiveProfileIds(doc, byId);
  if (!ids.length) return null;
  const week = Math.floor(date.getTime() / (7 * 86400000));
  return byId.get(ids[((week % ids.length) + ids.length) % ids.length]);
}

const RECENT_KEY = "iobRecentLearningIslands";
export function recentIslandIds(storage) {
  try { const ids = JSON.parse(storage.getItem(RECENT_KEY) || "[]"); return Array.isArray(ids) ? ids.filter((id) => typeof id === "string").slice(0, 12) : []; } catch (_) { return []; }
}
export function rememberIsland(storage, id) {
  try { storage.setItem(RECENT_KEY, JSON.stringify([id, ...recentIslandIds(storage).filter((other) => other !== id)].slice(0, 12))); } catch (_) { /* Browsing works without storage. */ }
}

export function factualReferences(island, profile, storyPack) {
  const out = [];
  const seen = new Set();
  const add = (url, label) => { const safe = sourceUrl(url); if (safe && !seen.has(safe)) { seen.add(safe); out.push({ url: safe, label }); } };
  for (const s of profile?.sources || []) add(s.url, `${s.publisher}: ${s.label}`);
  for (const s of storyPack?.items || []) add(s.sourceUrl, s.sourceTitle || s.title || "Story source");
  if (island.wikipedia) add(island.wikipedia, "Wikipedia: island background");
  return out.slice(0, 8);
}

/** Prefer references actually cited. Otherwise identify island background as background. */
export function answerReferences(answer, references, islands, doc) {
  const unique = [...new Map(references.filter((r) => sourceUrl(r.url)).map((r) => [sourceUrl(r.url), r])).values()];
  const cited = unique.filter((r) => String(answer).includes(r.url));
  if (cited.length) return { label: "Sources cited in this answer", items: cited };
  const background = new Set(islands.flatMap((island) => [
    ...(learningProfile(doc, island.id)?.sources || []).map((s) => sourceUrl(s.url)),
    sourceUrl(island.wikipedia),
  ]).filter(Boolean));
  return { label: "Island background read for this answer", items: unique.filter((r) => background.has(sourceUrl(r.url))) };
}
