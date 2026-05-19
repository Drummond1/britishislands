/* global L */

/**
 * Isles of Britain — interactive island atlas.
 *
 *  • Loads ~1,000 islands from data/islands.json (curated + OSM).
 *  • Clusters markers for performance (Leaflet.markercluster).
 *  • Virtualises the sidebar list so 1,000 entries don't choke the DOM.
 *  • Lazily fetches each island's polygon from Overpass on click.
 *  • Optional Ordnance Survey base layer — configure your key from inside
 *    the app (open any island → "Detailed map" → "Add OS Maps API key").
 *    Get a free key at https://osdatahub.os.uk/ (250k tiles / month).
 */

import { applyIslandSeo, resetIslandSeo } from "./seo-meta.js";
import {
  fetchCrowdPins,
  buildContributionIssueUrl,
  crowdPinPopupHtml,
  CROWD_MARKER_STYLE,
  loadCrowdSuggestConfig,
  isCrowdSuggestConfigured,
  validateContributionFields,
  submitCrowdSuggestion,
  formatCrowdSuggestionBody,
} from "./crowd-pins.js";

const TYPE_COLORS = {
  sea: "#4ea3ff",
  lake: "#6cd3a3",
  river: "#f5b04a",
  unknown: "#b08bd1",
};

/** Distinct map/list styling for islands with a property listing link on file. */
const FOR_SALE_MARKER_FILL = "#e8a838";
const FOR_SALE_MARKER_STROKE = "#1a1200";

const ROW_HEIGHT = 76; // px, must match .island-card sizing (incl. thumbnail)
const VIEWPORT_PADDING = 4; // extra rows rendered above/below viewport

const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
  "https://overpass.openstreetmap.fr/api/interpreter",
];

/** Settled once `state.islands` / `state.byId` are ready or load failed. */
let _islandsIndexReady = null;

const state = {
  islands: [],
  filtered: [],
  byId: new Map(),
  markers: new Map(),       // id -> L.circleMarker
  polygonCache: new Map(),  // id -> GeoJSON layer
  activeId: null,
  activePolygon: null,
  detailMap: null,          // secondary OS-style Leaflet map in details panel
  galleries: null,          // lazy-loaded: id -> [extra image record, ...]
  galleriesPromise: null,   // in-flight fetch deduplicator
  ferries: null,            // lazy-loaded {routes, terminals, operators}
  ferriesPromise: null,
  ferryIslandIds: null,     // Set<islandId> of islands reachable by a ferry route
  ferryRoutesByIsland: null, // Map<islandId, route[]> built after loadFerries
  ferryGraph: null,         // Map<islandId, {other, durationMin, routeId}[]>
  propertyListingIslandIds: null, // Set<islandId> with ≥1 for-sale outbound link
  causeways: null,          // lazy-loaded array of tidal/bridge causeway records
  causewaysPromise: null,
  favoriteIds: null,        // Set<islandId> persisted in localStorage
  crowdPins: [],
  crowdLayer: null,
  crowdMapClickHandler: null,
  crowdDraftMarker: null,
  crowdSuggestConfig: null,
  favoritesMapLayer: null,
  propertyListingMapLayer: null,
  featuredIslands: null,
  discoveryTopics: null,
  activeExploreTopic: null,
  exploreIslandIds: null,
  mobileDetailSuspended: false,
};

const SCOTLAND_QUICK_FILTERS = [
  { id: "scotland", label: "All Scotland", nation: "Scotland" },
  { id: "scotland-ferry", label: "Ferry access", nation: "Scotland", ferry: true },
  { id: "scotland-photo", label: "With photos", nation: "Scotland", photo: true },
  { id: "scotland-sea", label: "Sea islands", nation: "Scotland", type: "sea" },
];

let activeScotlandQuick = null;

// ---------- Ferries (lazy-loaded) ----------
// data/ferries.json + data/ferry_terminals.json + data/operators.json are
// fetched on first island click. Once loaded we keep them in state.* so
// every subsequent details render is synchronous.

// Ferry terminals often carry OSM ids or null islandId while the atlas
// uses curated slugs (e.g. mull vs osm-way-…). The trip planner needs a
// single canonical id per island before we can build the route graph.
const FERRY_PORT_TO_ISLAND = {
  craignure: "mull",
  fionnphort: "mull",
  fishnish: "mull",
  tobermory: "mull",
  iona: "iona",
  armadale: "isle-of-skye",
  brodick: "arran",
  tarbert: "islay",
  portavadie: "bute",
  rathlin: "rathlin",
  lundy: "lundy",
};

function _ferryNorm(s) {
  return (s || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\bthe\s+|\bisle of\s+|\bisland of\s+/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function buildFerryIslandRefIndex() {
  const ref = new Map();
  const register = (canonicalId, key) => {
    if (!canonicalId || !key || ref.has(key)) return;
    ref.set(key, canonicalId);
  };
  for (const isl of state.islands) {
    const id = isl.id;
    register(id, id);
    if (isl.wikidata) {
      register(id, isl.wikidata);
      register(id, `wd-${isl.wikidata}`);
    }
    if (isl.osmType && isl.osmId) {
      register(id, `osm-${isl.osmType}-${isl.osmId}`);
    }
  }
  return ref;
}

function _nearestSeaIslandId(lat, lon, maxKm = 25) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  let best = null;
  let bestDist = maxKm;
  for (const isl of state.islands) {
    if (isl.type !== "sea" || !Number.isFinite(isl.lat) || !Number.isFinite(isl.lng)) continue;
    const dLat = toRad(isl.lat - lat);
    const dLng = toRad(isl.lng - lon);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat)) * Math.cos(toRad(isl.lat)) * Math.sin(dLng / 2) ** 2;
    const d = 2 * R * Math.asin(Math.sqrt(a));
    if (d < bestDist) {
      bestDist = d;
      best = isl.id;
    }
  }
  return best;
}

function _preferCuratedIslandId(id) {
  if (!id || !state.byId.has(id)) return null;
  if (!String(id).startsWith("osm-")) return id;
  const isl = state.byId.get(id);
  const target = _ferryNorm(isl?.name);
  if (!target) return id;
  let best = id;
  let bestScore = 0;
  for (const cand of state.islands) {
    if (String(cand.id).startsWith("osm-")) continue;
    const n = _ferryNorm(cand.name);
    if (!n) continue;
    let score = 0;
    if (n === target) score = 100;
    else if (n.includes(target) || target.includes(n)) score = 40;
    else continue;
    score += Math.min(5, Math.log10(1 + (cand.areaKm2 || 0)));
    if (score > bestScore) {
      bestScore = score;
      best = cand.id;
    }
  }
  return best;
}

function resolveFerryIslandId(rawId, terminal, route) {
  const termKey = (terminal?.id || "").toLowerCase();
  for (const [port, islandId] of Object.entries(FERRY_PORT_TO_ISLAND)) {
    if (termKey.includes(port) && state.byId.has(islandId)) return islandId;
  }
  if (route?.id) {
    const slug = route.id.toLowerCase();
    for (const [port, islandId] of Object.entries(FERRY_PORT_TO_ISLAND)) {
      if (slug.includes(port) && state.byId.has(islandId)) return islandId;
    }
  }
  const ref = state.ferryIslandRef;
  if (rawId) {
    const hit = ref?.get(rawId) || (state.byId.has(rawId) ? rawId : null);
    if (hit) return _preferCuratedIslandId(hit);
  }
  if (terminal?.name) {
    const hit = _findIslandByName(terminal.name);
    if (hit) return hit.id;
  }
  const lat = terminal?.lat;
  const lon = terminal?.lon ?? terminal?.lng;
  return _nearestSeaIslandId(lat, lon);
}

function _addFerryGraphEdge(adj, fromId, toId, route) {
  if (!fromId || !toId || fromId === toId) return;
  const dur = Number.isFinite(route.durationMinutes) ? route.durationMinutes : 120;
  if (!adj.has(fromId)) adj.set(fromId, []);
  if (!adj.has(toId)) adj.set(toId, []);
  adj.get(fromId).push({ other: toId, durationMin: dur, routeId: route.id });
  adj.get(toId).push({ other: fromId, durationMin: dur, routeId: route.id });
}

function refreshTripPlannerDatalist() {
  const list = document.getElementById("trip-islands");
  if (!list || !state.ferryGraph?.size) return;
  list.replaceChildren();
  const names = [];
  for (const id of state.ferryGraph.keys()) {
    const isl = state.byId.get(id);
    if (isl?.name) names.push(isl.name);
  }
  names.sort((a, b) => a.localeCompare(b));
  const frag = document.createDocumentFragment();
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    frag.appendChild(opt);
  }
  list.appendChild(frag);
  list.dataset.filled = "ferry";
}

function findFerryItinerary(startId, endId) {
  const adj = state.ferryGraph;
  const start = resolveFerryIslandId(startId, null, null) || startId;
  const end = resolveFerryIslandId(endId, null, null) || endId;
  if (!adj || !adj.has(start) || !adj.has(end)) return null;
  if (start === end) return { path: [start], edges: [], totalDurationMin: 0 };
  const dist = new Map();
  const prev = new Map();
  const edgeUsed = new Map();
  dist.set(start, 0);
  const queue = [[0, start]];
  const visited = new Set();
  while (queue.length) {
    queue.sort((a, b) => a[0] - b[0]);
    const [d, u] = queue.shift();
    if (visited.has(u)) continue;
    visited.add(u);
    if (u === end) break;
    for (const e of adj.get(u) || []) {
      if (visited.has(e.other)) continue;
      const alt = d + e.durationMin;
      if (alt < (dist.get(e.other) ?? Infinity)) {
        dist.set(e.other, alt);
        prev.set(e.other, u);
        edgeUsed.set(e.other, e.routeId);
        queue.push([alt, e.other]);
      }
    }
  }
  if (!prev.has(end) && start !== end) return null;
  const path = [end];
  const edges = [];
  let cur = end;
  while (prev.has(cur)) {
    edges.unshift(edgeUsed.get(cur));
    cur = prev.get(cur);
    path.unshift(cur);
  }
  return { path, edges, totalDurationMin: dist.get(end) || 0 };
}

function _formatItinerarySummary(it) {
  const names = it.path.map((id) => state.byId.get(id)?.name || id).join(" → ");
  const h = Math.floor(it.totalDurationMin / 60);
  const m = it.totalDurationMin % 60;
  const dur = h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
  return `${names} · ~${dur} at sea · ${it.edges.length} crossing${it.edges.length === 1 ? "" : "s"}`;
}

function resolveTripIslandId(query) {
  const q = (query || "").trim();
  if (!q) return null;
  if (state.byId.has(q)) return q;
  const hit = _findIslandByName(q);
  return hit?.id || null;
}

function planTripBetween(startQuery, endQuery) {
  const startId = resolveTripIslandId(startQuery);
  const endId = resolveTripIslandId(endQuery);
  if (!startId || !endId) {
    return Promise.resolve({
      ok: false,
      error: "Couldn't match both islands — try the full island name from the suggestions.",
    });
  }
  if (startId === endId) {
    return Promise.resolve({ ok: false, error: "Choose two different islands." });
  }
  const url = new URL(window.location.href);
  url.searchParams.set("trip", `${startId},${endId}`);
  window.history.replaceState(null, "", url.toString());
  return loadFerries().then(() => {
    const adj = state.ferryGraph;
    const start = resolveFerryIslandId(startId, null, null) || startId;
    const end = resolveFerryIslandId(endId, null, null) || endId;
    if (!adj || adj.size === 0) {
      return { ok: false, error: "Ferry data is still loading. Try again in a moment." };
    }
    const startName = state.byId.get(start)?.name || startQuery.trim();
    const endName = state.byId.get(end)?.name || endQuery.trim();
    if (!adj.has(start)) {
      return {
        ok: false,
        error: `No mapped ferry routes touch «${startName}». Pick an island from the suggestions.`,
      };
    }
    if (!adj.has(end)) {
      return {
        ok: false,
        error: `No mapped ferry routes touch «${endName}». Pick an island from the suggestions.`,
      };
    }
    const it = findFerryItinerary(startId, endId);
    if (!it) {
      return {
        ok: false,
        error: `No ferry chain between «${startName}» and «${endName}» in this dataset.`,
      };
    }
    _renderItineraryBanner(it);
    return { ok: true, itinerary: it, startId, endId, summary: _formatItinerarySummary(it) };
  });
}

function tryRenderItineraryFromUrl() {
  try {
    const trip = new URLSearchParams(window.location.search).get("trip");
    if (!trip) return;
    const [startId, endId] = trip.split(",").map((s) => s.trim()).filter(Boolean);
    if (!startId || !endId) return;
    loadFerries().then(() => {
      const it = findFerryItinerary(startId, endId);
      if (it) _renderItineraryBanner(it);
    });
  } catch (_) {
    /* non-fatal */
  }
}

function _mountItineraryBanner(banner) {
  const topbar = document.querySelector("header.topbar");
  if (topbar) topbar.insertAdjacentElement("afterend", banner);
  else if (!banner.parentNode) document.body.prepend(banner);
}

function _onItineraryBannerClick(e) {
  const a = e.target.closest("a[href]");
  if (!a) return;
  const href = a.getAttribute("href") || "";
  if (!href.startsWith("?island=")) return;
  e.preventDefault();
  try {
    const q = href.startsWith("?") ? href.slice(1) : href;
    const id = new URLSearchParams(q).get("island");
    if (id && state.byId?.has(id)) focusIsland(id, { fly: true });
  } catch (_) {
    /* non-fatal */
  }
}

function _renderItineraryBanner(it) {
  const stops = it.path.map((id) => {
    const isl = state.byId.get(id);
    if (isl) {
      return `<a href="?island=${encodeURIComponent(isl.id)}">${escapeHtml(isl.name)}</a>`;
    }
    return `<span class="itinerary-banner__unknown">${escapeHtml(id)}</span>`;
  });
  if (!stops.length) return;
  const h = Math.floor(it.totalDurationMin / 60);
  const m = it.totalDurationMin % 60;
  const dur = h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
  let banner = document.getElementById("itinerary-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "itinerary-banner";
    banner.className = "itinerary-banner";
    banner.addEventListener("click", _onItineraryBannerClick);
  }
  _mountItineraryBanner(banner);
  banner.innerHTML = `
    <strong>Suggested ferry crossing:</strong>
    <span class="itinerary-banner__stops">${stops.join(' <span class="itinerary-banner__arrow">→</span> ')}</span>
    <span class="itinerary-banner__meta">~${dur} at sea · ${it.edges.length} leg${it.edges.length === 1 ? "" : "s"}</span>
    <button type="button" class="itinerary-banner__close" aria-label="Dismiss">×</button>
  `;
  banner.querySelector(".itinerary-banner__close")?.addEventListener("click", () => banner.remove());
}

function initTripPlanner() {
  const form = document.getElementById("trip-form");
  const fromInput = document.getElementById("trip-from");
  const toInput = document.getElementById("trip-to");
  const status = document.getElementById("trip-status");
  if (!form || !fromInput || !toInput) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (status) status.textContent = "Planning…";
    planTripBetween(fromInput.value, toInput.value).then((res) => {
      if (!status) return;
      if (!res || res.ok === false) {
        status.textContent = res?.error || "Couldn't plan that crossing.";
        return;
      }
      status.textContent = res.summary
        ? `${res.summary} — see banner under the header.`
        : "Crossing planned.";
    });
  });
  try {
    const trip = new URLSearchParams(window.location.search).get("trip");
    if (trip) {
      const [startId, endId] = trip.split(",").map((s) => s.trim());
      const a = state.byId.get(startId);
      const b = state.byId.get(endId);
      if (a) fromInput.value = a.name;
      if (b) toInput.value = b.name;
    }
  } catch (_) {
    /* non-fatal */
  }
  // #region agent log
  requestAnimationFrame(() => {
    const tp = document.querySelector(".trip-planner");
    const mapEl = document.getElementById("map");
    if (!tp) return;
    const tr = tp.getBoundingClientRect();
    const mr = mapEl?.getBoundingClientRect();
    const overlapsMap =
      mr &&
      tr.left < mr.right &&
      tr.right > mr.left &&
      tr.top < mr.bottom &&
      tr.bottom > mr.top;
    fetch("http://127.0.0.1:7720/ingest/def19690-94b9-4670-be7c-26220155de0a", { method: "POST", headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5f60f5" }, body: JSON.stringify({ sessionId: "5f60f5", runId: "post-fix-2", hypothesisId: "H6", location: "app.js:initTripPlanner", message: "trip-planner layout", data: { position: getComputedStyle(tp).position, inSidebar: !!tp.closest(".sidebar"), overlapsMap, tripRect: { t: Math.round(tr.top), l: Math.round(tr.left), b: Math.round(tr.bottom) }, mapRect: mr ? { t: Math.round(mr.top), b: Math.round(mr.bottom) } : null }, timestamp: Date.now() }) }).catch(() => {});
  });
  // #endregion
}

function syncFerryDiscoveryFilter() {
  const ferryToggle = els.filterFerry;
  if (!ferryToggle) return;
  const ready = state.ferryIslandIds != null;
  ferryToggle.disabled = !ready;
  const wrap = document.getElementById("filter-ferry-wrap");
  if (wrap) {
    wrap.classList.toggle("toggle--pending", !ready);
    wrap.title = ready
      ? "Show only islands served by a mapped ferry route"
      : "Loading ferry routes…";
  }
  if (!ready) ferryToggle.checked = false;
}

function islandHasPropertyListing(island) {
  if (!island) return false;
  if (island.hasPropertyListing === true) return true;
  if (Array.isArray(island.propertyListings) && island.propertyListings.length > 0) {
    return true;
  }
  return Boolean(state.propertyListingIslandIds?.has(island.id));
}

function initPropertyListingState() {
  const ids = new Set();
  for (const i of state.islands) {
    if (islandHasPropertyListing(i)) ids.add(i.id);
  }
  state.propertyListingIslandIds = ids;
  syncPropertyListingFilter();
  rebuildPropertyListingMapLayer();
}

function syncPropertyListingFilter() {
  const toggle = els.filterForSale;
  if (!toggle) return;
  const ready = state.propertyListingIslandIds != null;
  toggle.disabled = !ready;
  const wrap = document.getElementById("filter-for-sale-wrap");
  if (wrap) {
    wrap.classList.toggle("toggle--pending", !ready);
    wrap.title = ready
      ? "Show only islands with a known property listing link"
      : "Loading property listings…";
  }
  if (!ready) toggle.checked = false;
  const n = state.propertyListingIslandIds?.size ?? 0;
  const countEl = document.getElementById("for-sale-count");
  if (countEl) countEl.textContent = n ? `(${n})` : "";
}

function primaryPropertyListing(island) {
  const rows = island?.propertyListings;
  if (!Array.isArray(rows) || !rows.length) return null;
  return rows.find((r) => r?.url) || rows[0];
}

function propertyListingPopupHtml(island) {
  const rows = island.propertyListings || [];
  const links = rows
    .filter((r) => r?.url)
    .map((r) => {
      const typeLabel = _LISTING_TYPE_LABEL[r.listingType] || r.listingType || "Listing";
      const price = r.priceDisplay || (r.priceGBP != null ? `£${Number(r.priceGBP).toLocaleString("en-GB")}` : "");
      return `<li class="sale-popup__item">
        <a href="${escapeAttr(r.url)}" target="_blank" rel="noopener noreferrer" class="sale-popup__link">${escapeHtml(r.title || "View listing")} ↗</a>
        <span class="sale-popup__meta">${escapeHtml(typeLabel)}${price ? ` · ${escapeHtml(price)}` : ""}</span>
      </li>`;
    })
    .join("");
  return `<div class="sale-popup">
    <p class="sale-popup__title"><strong>${escapeHtml(island.name)}</strong></p>
    <p class="sale-popup__lead">Property link${rows.length === 1 ? "" : "s"} (opens external site):</p>
    <ul class="sale-popup__list">${links}</ul>
    <button type="button" class="sale-popup__atlas-btn" data-island-id="${escapeAttr(island.id)}">Island profile</button>
  </div>`;
}

function loadFerries() {
  if (state.ferries) return Promise.resolve(state.ferries);
  if (state.ferriesPromise) return state.ferriesPromise;
  // Ferry ↔ island resolution needs `state.byId` (wikidata/osm/slug joins).
  // If we build the graph before islands.json finishes, the graph stays empty
  // forever because this promise is cached.
  state.ferriesPromise = (_islandsIndexReady ?? Promise.resolve())
    .catch(() => {
      /* islands.json may have failed; still build whatever graph we can */
    })
    .then(() => {
      state.ferryIslandRef = buildFerryIslandRefIndex();
      return Promise.all([
        fetch("data/ferries.json").then((r) => (r.ok ? r.json() : { routes: [] })),
        fetch("data/ferry_terminals.json").then((r) => (r.ok ? r.json() : { terminals: [] })),
        fetch("data/operators.json").then((r) => (r.ok ? r.json() : { operators: [] })),
      ]);
    })
    .then(([ferriesDoc, termsDoc, opsDoc]) => {
      const routes = Array.isArray(ferriesDoc.routes) ? ferriesDoc.routes : [];
      const terminals = Array.isArray(termsDoc.terminals) ? termsDoc.terminals : [];
      const operators = Array.isArray(opsDoc.operators) ? opsDoc.operators : [];
      const termById = new Map(terminals.map((t) => [t.id, t]));
      const opById = new Map(operators.map((o) => [o.id, o]));
      const byIsland = new Map();
      const islandIds = new Set();
      const adj = new Map();
      for (const r of routes) {
        const fromTerm = termById.get(r.terminals?.from?.terminalId);
        const toTerm = termById.get(r.terminals?.to?.terminalId);
        const fromIsl = resolveFerryIslandId(
          r.terminals?.from?.islandId || fromTerm?.islandId,
          fromTerm,
          r,
        );
        const toIsl = resolveFerryIslandId(
          r.terminals?.to?.islandId || toTerm?.islandId,
          toTerm,
          r,
        );
        const enriched = Object.assign({}, r, {
          _fromTerminal: fromTerm,
          _toTerminal: toTerm,
          _fromIsland: fromIsl,
          _toIsland: toIsl,
          _operator: opById.get(r.operatorId) || null,
        });
        for (const islId of [fromIsl, toIsl]) {
          if (!islId) continue;
          if (!byIsland.has(islId)) byIsland.set(islId, []);
          byIsland.get(islId).push(enriched);
          islandIds.add(islId);
        }
        _addFerryGraphEdge(adj, fromIsl, toIsl, r);
      }
      state.ferries = { routes, terminals, operators, termById, opById };
      state.ferryIslandIds = islandIds;
      state.ferryRoutesByIsland = byIsland;
      state.ferryGraph = adj;
      try {
        refreshTripPlannerDatalist();
        syncFerryDiscoveryFilter();
        if (shouldRenderListWindow()) scheduleRenderListWindow();
      } catch (_) { /* noop */ }
      return state.ferries;
    })
    .catch((err) => {
      console.warn("loadFerries failed", err);
      state.ferries = { routes: [], terminals: [], operators: [], termById: new Map(), opById: new Map() };
      state.ferryIslandIds = new Set();
      state.ferryRoutesByIsland = new Map();
      state.ferryGraph = new Map();
      try { syncFerryDiscoveryFilter(); } catch (_) { /* noop */ }
      return state.ferries;
    })
    .finally(() => {
      state.ferriesPromise = null;
    });
  return state.ferriesPromise;
}

function findFerriesForIsland(islandId) {
  if (!state.ferryRoutesByIsland) return [];
  const key = resolveFerryIslandId(islandId, null, null) || islandId;
  return state.ferryRoutesByIsland.get(key) || [];
}


// data/causeways.json is tiny (~3 KB) but still lazy-loaded for parity
// with the other ferry data files.
function loadCauseways() {
  if (state.causeways) return Promise.resolve(state.causeways);
  if (state.causewaysPromise) return state.causewaysPromise;
  state.causewaysPromise = fetch("data/causeways.json")
    .then((r) => (r.ok ? r.json() : { causeways: [] }))
    .catch(() => ({ causeways: [] }))
    .then((doc) => {
      state.causeways = Array.isArray(doc.causeways) ? doc.causeways : [];
      return state.causeways;
    });
  return state.causewaysPromise;
}

function findCausewayForIsland(island) {
  if (!state.causeways) return null;
  // Match by explicit islandId first, then by name-hint substring.
  const byId = state.causeways.find((c) => c.islandId === island.id);
  if (byId) return byId;
  const name = (island.name || "").toLowerCase();
  for (const c of state.causeways) {
    for (const hint of (c.islandNameHints || [])) {
      if (hint && name.includes(hint.toLowerCase())) return c;
    }
  }
  return null;
}

// Compact ferry / causeway facts for chat RAG and result cards.
function chatAccessForIsland(island) {
  if (!island || typeof island !== "object") return { ferryRoutes: [], causeway: null };
  const ferryRoutes = [];
  if (state.ferryRoutesByIsland) {
    for (const route of (state.ferryRoutesByIsland.get(island.id) || []).slice(0, 4)) {
      ferryRoutes.push({
        operator: route._operator?.shortName || route._operator?.name || route.operatorId || null,
        from: route._fromTerminal?.name || null,
        to: route._toTerminal?.name || null,
        type: route.type || null,
        seasonality: route.seasonality || null,
        durationMinutes: route.durationMinutes ?? null,
        frequencyBand: route.frequencyBand || null,
        lastVerified: route.lastVerified || null,
      });
    }
  }
  const cw = findCausewayForIsland(island);
  const causeway = cw
    ? {
        kind: cw.kind || null,
        notes: typeof cw.notes === "string" ? cw.notes.slice(0, 220) : null,
        safeHours: cw.safeHours || null,
        sourceUrl: cw.sourceUrl || null,
      }
    : null;
  return { ferryRoutes, causeway };
}

function showIslandOnMap(id) {
  const island = state.byId.get(id);
  if (!island || !map) return;
  state.activeId = id;
  renderListWindow();
  const targetZoom =
    island.type === "river" ? 14 : island.areaKm2 < 1 ? 12 : island.areaKm2 < 50 ? 11 : 10;
  map.flyTo([island.lat, island.lng], targetZoom, { duration: 0.7 });
  loadAndShowPolygon(island);
}

// Lazy-fetch data/galleries.json on first island click. Extra images live
// in a separate file so they don't bloat the initial islands.json payload.
function loadGalleries() {
  if (state.galleries) return Promise.resolve(state.galleries);
  if (state.galleriesPromise) return state.galleriesPromise;
  state.galleriesPromise = fetch("data/galleries.json")
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}))
    .then((g) => {
      state.galleries = g || {};
      return state.galleries;
    });
  return state.galleriesPromise;
}

// Configuration: an OS Maps API key can be provided via either:
//   1. window.OS_MAPS_API_KEY (set in an untracked config.local.js, loaded
//      before app.js), or
//   2. localStorage.osMapsApiKey, settable interactively from devtools.
// When neither is present we fall back to the OpenStreetMap basemap so the
// detail map always renders. See docs/OS-MAPS.md for the upgrade path to the
// full EPSG:27700 OS Leisure raster via proj4leaflet.
function getOsMapsKey() {
  try {
    if (typeof window !== "undefined" && window.OS_MAPS_API_KEY) {
      return String(window.OS_MAPS_API_KEY);
    }
    return localStorage.getItem("osMapsApiKey") || "";
  } catch (_) {
    return "";
  }
}

const els = {
  list: document.getElementById("island-list"),
  count: document.getElementById("result-count"),
  listHeading: document.getElementById("list-heading"),
  search: document.getElementById("search"),
  typeFilter: document.getElementById("type-filter"),
  nationFilter: document.getElementById("nation-filter"),
  favoritesFilter: document.getElementById("favorites-filter"),
  filterPhoto: document.getElementById("filter-photo"),
  filterFerry: document.getElementById("filter-ferry"),
  filterElevation: document.getElementById("filter-elevation"),
  filterForSale: document.getElementById("filter-for-sale"),
  areaMinFilter: document.getElementById("area-min-filter"),
  subtypeFilter: document.getElementById("subtype-filter"),
  confidenceFilter: document.getElementById("confidence-filter"),
  basemap: document.getElementById("basemap"),
  cluster: document.getElementById("cluster-toggle"),
  details: document.getElementById("island-details"),
  detailsContent: document.getElementById("details-content"),
  listSection: document.getElementById("island-list-section"),
  back: document.getElementById("back-button"),
  sidebar: document.getElementById("sidebar"),
};

// ---------- Saved islands (local list; email unlocks hearts + saved view) ----------
const FAVORITES_STORAGE_KEY = "iobFavoriteIslandIds";
const FAVORITES_EMAIL_KEY = "iobFavoritesEmail";
let favoritesAccessPending = null;

function isValidFavoritesEmail(value) {
  const s = String(value || "").trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);
}

function getFavoritesEmail() {
  try {
    const raw = localStorage.getItem(FAVORITES_EMAIL_KEY);
    const email = String(raw || "").trim().toLowerCase();
    return isValidFavoritesEmail(email) ? email : "";
  } catch (_) {
    return "";
  }
}

function hasFavoritesAccess() {
  return Boolean(getFavoritesEmail());
}

function saveFavoritesEmail(email) {
  const normalized = String(email || "").trim().toLowerCase();
  if (!isValidFavoritesEmail(normalized)) {
    throw new Error("Enter a valid email address.");
  }
  localStorage.setItem(FAVORITES_EMAIL_KEY, normalized);
}

function readFavoriteIdsFromStorage() {
  try {
    const raw = localStorage.getItem(FAVORITES_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch (_) {
    return [];
  }
}

function initFavoritesState() {
  state.favoriteIds = new Set(readFavoriteIdsFromStorage());
  updateSavedUiChrome();
}

function persistFavoriteIds() {
  try {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify([...state.favoriteIds]));
  } catch (_) {
    /* private mode / quota */
  }
}

function isFavoriteIsland(id) {
  return !!(id && state.favoriteIds?.has(id));
}

function updateSavedUiChrome() {
  const btn = document.getElementById("saved-islands-btn");
  const n = state.favoriteIds?.size || 0;
  if (!btn) return;
  if (hasFavoritesAccess() && n > 0) btn.textContent = `Saved (${n})`;
  else btn.textContent = "Saved";
}

function showSavedIslandsList() {
  const run = () => {
    if (els.favoritesFilter) els.favoritesFilter.value = "favorites";
    applyFilters();
    if (els.listSection) els.listSection.hidden = false;
    if (els.details) els.details.hidden = true;
    if (typeof mobileNav !== "undefined" && mobileNav.isActive()) mobileNav.setView("islands");
    els.sidebar?.scrollTo?.(0, 0);
  };
  ensureFavoritesAccess(run);
}

function ensureFavoritesAccess(onGranted) {
  if (hasFavoritesAccess()) {
    onGranted();
    return;
  }
  favoritesAccessPending = onGranted;
  openFavoritesAccessModal();
}

function openFavoritesAccessModal() {
  const modal = document.getElementById("favorites-access-modal");
  const input = document.getElementById("favorites-email-input");
  const err = document.getElementById("favorites-access-error");
  if (!modal) return;
  if (err) {
    err.hidden = true;
    err.textContent = "";
  }
  if (input) {
    input.value = getFavoritesEmail() || "";
    modal.hidden = false;
    input.focus();
  } else {
    modal.hidden = false;
  }
}

function closeFavoritesAccessModal(cancelled) {
  const modal = document.getElementById("favorites-access-modal");
  if (modal) modal.hidden = true;
  if (cancelled) favoritesAccessPending = null;
}

function completeFavoritesAccess() {
  const input = document.getElementById("favorites-email-input");
  const err = document.getElementById("favorites-access-error");
  try {
    saveFavoritesEmail(input?.value || "");
    closeFavoritesAccessModal(false);
    updateSavedUiChrome();
    rebuildFavoritesMapLayer();
  rebuildPropertyListingMapLayer();
    rebuildMarkerLayer();
    const next = favoritesAccessPending;
    favoritesAccessPending = null;
    next?.();
  } catch (e) {
    if (err) {
      err.hidden = false;
      err.textContent = e?.message || "Could not save your email.";
    }
  }
}

function initFavoritesAccessUi() {
  const modal = document.getElementById("favorites-access-modal");
  const backdrop = document.getElementById("favorites-access-backdrop");
  const cancel = document.getElementById("favorites-access-cancel");
  const cont = document.getElementById("favorites-access-continue");
  const input = document.getElementById("favorites-email-input");
  const savedBtn = document.getElementById("saved-islands-btn");

  if (!modal) return;

  backdrop?.addEventListener("click", () => closeFavoritesAccessModal(true));
  cancel?.addEventListener("click", () => closeFavoritesAccessModal(true));
  cont?.addEventListener("click", () => completeFavoritesAccess());
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      completeFavoritesAccess();
    }
    if (e.key === "Escape") closeFavoritesAccessModal(true);
  });
  savedBtn?.addEventListener("click", () => showSavedIslandsList());

  updateSavedUiChrome();
}

function toggleFavoriteIsland(id) {
  if (!id || !state.favoriteIds) return;
  const applyToggle = () => {
    if (state.favoriteIds.has(id)) state.favoriteIds.delete(id);
    else state.favoriteIds.add(id);
    persistFavoriteIds();
    updateSavedUiChrome();
    scheduleRenderListWindow();
    rebuildMarkerLayer();
    syncDetailsFavoriteButton(id);
  };
  if (!hasFavoritesAccess()) {
    ensureFavoritesAccess(applyToggle);
    return;
  }
  applyToggle();
}

function syncDetailsFavoriteButton(islandId) {
  const btn = document.getElementById("details-favorite-btn");
  if (!btn || state.activeId !== islandId) return;
  const on = isFavoriteIsland(islandId);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  btn.setAttribute("aria-label", on ? "Remove from saved islands" : "Save island to list");
  btn.textContent = on ? "♥" : "♡";
  btn.classList.toggle("is-favorite", on);
}

// ---------- Suggest a correction (GitHub issues; no accounts on-site) ----------
// Override at deploy time: window.IOB_CORRECTION_REPO = "owner/repo"
const CORRECTION_REPO_DEFAULT = "Drummond1/britishislands";

function correctionRepoSlug() {
  if (typeof window !== "undefined" && window.IOB_CORRECTION_REPO) {
    return String(window.IOB_CORRECTION_REPO).replace(/^https?:\/\/github\.com\//i, "").replace(/\/$/, "");
  }
  return CORRECTION_REPO_DEFAULT;
}

function buildCorrectionIssueUrl(island) {
  const title = `Data correction: ${island.name}`;
  const lines = [
    "## Island",
    "",
    `- **Atlas id**: \`${island.id}\``,
    `- **Display name**: ${island.name}`,
    `- **Nation**: ${island.nation || "—"}`,
    `- **Type**: ${island.type || "—"}${island.subtype ? ` (${island.subtype})` : ""}`,
    `- **Coordinates**: ${island.lat}, ${island.lng}`,
    island.archipelago ? `- **Archipelago**: ${island.archipelago}` : "",
    island.wikidata
      ? `- **Wikidata**: https://www.wikidata.org/wiki/${encodeURIComponent(island.wikidata)}`
      : "",
    island.osmType && island.osmId != null
      ? `- **OpenStreetMap**: https://www.openstreetmap.org/${island.osmType}/${island.osmId}`
      : "",
    island.source ? `- **Atlas source tag**: ${island.source}` : "",
    "",
    "## What is wrong?",
    "",
    "<!-- Describe the error (name, type, location, population, duplicate, etc.) -->",
    "",
    "## Proposed correction",
    "",
    "<!-- What should the atlas show instead? -->",
    "",
    "## Evidence (required)",
    "",
    "Link at least one authoritative or open-licence source (OSM, Wikidata, official stats, gazetteer, operator page):",
    "",
    "- ",
    "",
    "## Optional contact",
    "",
    "<!-- Email if you want a reply when we have reviewed this -->",
  ].filter(Boolean);
  const body = lines.join("\n");
  const params = new URLSearchParams({ title, body });
  return `https://github.com/${correctionRepoSlug()}/issues/new?${params.toString()}`;
}

function renderCorrectionReport(island) {
  const issueUrl = buildCorrectionIssueUrl(island);
  const curatedNote =
    island.source === "curated"
      ? `<p class="correction-report__note">This is a <strong>curated spine</strong> entry — we only change it after checking your sources against our regression set.</p>`
      : "";
  const unconfirmedNote =
    island.classification?.confidence === "unconfirmed"
      ? `<p class="correction-report__note">This row is marked <strong>not confirmed</strong> in the atlas; your report helps us verify or remove it.</p>`
      : "";
  return `
    <div class="section correction-report">
      <h3>Contribute improvements</h3>
      <p class="correction-report__lead">
        Suggest a better <strong>name</strong>, <strong>description</strong>, or <strong>photo links</strong>.
        If you propose a name, add a source link so we can verify it.
      </p>
      ${curatedNote}
      ${unconfirmedNote}
      <p class="correction-report__actions">
        <button type="button" class="correction-report__btn correction-report__btn--primary" data-contribute-island="${escapeAttr(island.id)}">
          Edit this island…
        </button>
        <a class="correction-report__btn correction-report__btn--ghost" href="${escapeAttr(issueUrl)}" target="_blank" rel="noopener noreferrer">
          GitHub form ↗
        </a>
      </p>
      <p class="correction-report__fine">
        Atlas islands use coloured dots. Community suggestions use <strong>gold pins</strong> until approved.
      </p>
    </div>`;
}

// ---------- Map ----------
const map = L.map("map", {
  center: [55.5, -4.0],
  zoom: 6,
  minZoom: 4,
  maxZoom: 18,
  worldCopyJump: true,
  preferCanvas: true,
  tapTolerance: 22,
});

const LOW_ZOOM_MARKER_MAX = 7;
let markerViewportTimer = null;

const baseLayers = {
  osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }),
  topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", {
    maxZoom: 17,
    attribution:
      'Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>, SRTM | Style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
  }),
  satellite: L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution:
        "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
    },
  ),
  cartoLight: L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    {
      maxZoom: 19,
      subdomains: "abcd",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  ),
  cartoDark: L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    {
      maxZoom: 19,
      subdomains: "abcd",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  ),
};

// Build (or rebuild) the main-map OS Maps base layer using the current key
// from `getOsMapsKey()`. Called once at startup and again whenever the user
// pastes / clears a key via the in-app form. When no key is present, the
// dropdown option stays disabled and labelled to point users at the form.
function setupMainOsMapsLayer() {
  const key = getOsMapsKey();
  const osOption = els.basemap.querySelector('option[value="osMaps"]');
  if (key) {
    baseLayers.osMaps = L.tileLayer(
      `https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`,
      {
        maxZoom: 20,
        attribution:
          "Contains OS data &copy; Crown copyright and database rights " +
          new Date().getFullYear(),
      },
    );
    // Log the first failure to the console so it's debuggable without
    // having to hunt through Leaflet internals.
    let logged = false;
    baseLayers.osMaps.on("tileerror", async (e) => {
      if (logged) return; logged = true;
      const url = (e.tile && e.tile.src) || "";
      let status = "?";
      try { status = String((await fetch(url)).status); } catch (_) { /* */ }
      console.warn(
        "[OS Maps] Main-map tile failed (HTTP " + status + "). " +
        "Open any island's 'Detailed map' section and click 'Test key' for a clearer diagnostic.",
      );
    });
    if (osOption) {
      osOption.disabled = false;
      osOption.textContent = "OS Maps (Outdoor)";
    }
  } else {
    delete baseLayers.osMaps;
    if (osOption) {
      osOption.disabled = true;
      osOption.textContent = "OS Maps (open an island to add a key)";
    }
  }
}
setupMainOsMapsLayer();

let currentBase = baseLayers.osm.addTo(map);

els.basemap.addEventListener("change", (event) => {
  const next = baseLayers[event.target.value];
  if (!next) return;
  map.removeLayer(currentBase);
  currentBase = next.addTo(map);
});

// ---------- Marker layers (cluster vs flat) ----------
const clusterLayer = L.markerClusterGroup({
  chunkedLoading: true,
  showCoverageOnHover: false,
  maxClusterRadius: 50,
  spiderfyOnMaxZoom: true,
});
const flatLayer = L.layerGroup();
let activeMarkerLayer = clusterLayer;
clusterLayer.addTo(map);

function getFavoritesMapPane() {
  if (!map.getPane("favoritesPane")) {
    const pane = map.createPane("favoritesPane");
    pane.style.zIndex = "650";
  }
  return "favoritesPane";
}

function makeFavoriteHeartMarker(island) {
  const marker = L.marker([island.lat, island.lng], {
    icon: L.divIcon({
      className: "map-heart-marker",
      html: '<span class="map-heart-marker__heart" aria-hidden="true">♥</span>',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    }),
    pane: getFavoritesMapPane(),
    zIndexOffset: 1000,
  });
  marker.bindTooltip(island.name, {
    direction: "top",
    offset: [0, -12],
    className: "map-heart-tooltip",
  });
  marker.on("click", () => focusIsland(island.id, { fly: false }));
  return marker;
}

function getPropertyListingMapPane() {
  if (!map.getPane("propertyListingPane")) {
    const pane = map.createPane("propertyListingPane");
    pane.style.zIndex = "640";
  }
  return "propertyListingPane";
}

function makeForSaleMapMarker(island) {
  const marker = L.marker([island.lat, island.lng], {
    icon: L.divIcon({
      className: "map-sale-marker",
      html: '<span class="map-sale-marker__ring" aria-hidden="true"></span><span class="map-sale-marker__badge">£</span>',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
    }),
    pane: getPropertyListingMapPane(),
    zIndexOffset: 850,
  });
  const lead = primaryPropertyListing(island);
  const tip = lead?.url
    ? `<span class="map-sale-tooltip"><strong>For sale</strong> · ${escapeHtml(island.name)}<br><a class="map-sale-tooltip__link" href="${escapeAttr(lead.url)}" target="_blank" rel="noopener noreferrer">Open listing ↗</a></span>`
    : `<span class="map-sale-tooltip"><strong>For sale</strong> · ${escapeHtml(island.name)}</span>`;
  marker.bindTooltip(tip, {
    direction: "top",
    offset: [0, -14],
    className: "map-sale-tooltip-wrap",
    interactive: true,
  });
  marker.bindPopup(propertyListingPopupHtml(island), {
    maxWidth: 300,
    className: "sale-popup-wrap",
  });
  marker.on("popupopen", (ev) => {
    const btn = ev.popup.getElement()?.querySelector(".sale-popup__atlas-btn");
    btn?.addEventListener("click", () => {
      map.closePopup();
      focusIsland(island.id, { fly: false });
    });
  });
  marker.on("click", () => focusIsland(island.id, { fly: false }));
  return marker;
}

function rebuildPropertyListingMapLayer() {
  if (!map || !state.propertyListingIslandIds) return;
  if (!state.propertyListingMapLayer) {
    state.propertyListingMapLayer = L.layerGroup();
    state.propertyListingMapLayer.addTo(map);
  }
  state.propertyListingMapLayer.clearLayers();
  for (const id of state.propertyListingIslandIds) {
    const island = state.byId.get(id);
    if (!island || !Number.isFinite(island.lat) || !Number.isFinite(island.lng)) continue;
    state.propertyListingMapLayer.addLayer(makeForSaleMapMarker(island));
  }
}

function rebuildFavoritesMapLayer() {
  if (!map) return;
  if (!state.favoritesMapLayer) {
    state.favoritesMapLayer = L.layerGroup();
    state.favoritesMapLayer.addTo(map);
  }
  state.favoritesMapLayer.clearLayers();
  if (!hasFavoritesAccess() || !state.favoriteIds?.size) return;
  for (const id of state.favoriteIds) {
    const island = state.byId.get(id);
    if (!island) continue;
    state.favoritesMapLayer.addLayer(makeFavoriteHeartMarker(island));
  }
}

els.cluster.addEventListener("change", () => {
  const wasOn = map.hasLayer(activeMarkerLayer);
  if (wasOn) map.removeLayer(activeMarkerLayer);
  activeMarkerLayer = els.cluster.checked ? clusterLayer : flatLayer;
  rebuildMarkerLayer();
  activeMarkerLayer.addTo(map);
});

// ---------- Crowd-sourced pins (community layer) ----------
function clearCrowdDraftMarker() {
  if (state.crowdDraftMarker && map) {
    try {
      map.removeLayer(state.crowdDraftMarker);
    } catch (_) {
      /* ignore */
    }
    state.crowdDraftMarker = null;
  }
}

function setCrowdPickMode(on) {
  const modal = document.getElementById("crowd-modal");
  if (modal) modal.classList.toggle("crowd-modal--picking", Boolean(on));
}

function setCrowdDraftMarker(lat, lng) {
  if (!map) return;
  clearCrowdDraftMarker();
  state.crowdDraftMarker = L.circleMarker([lat, lng], {
    ...CROWD_MARKER_STYLE,
    radius: 11,
    weight: 3,
  });
  state.crowdDraftMarker.addTo(map);
}

function clearCrowdMapPicker() {
  if (state.crowdMapClickHandler && map) {
    map.off("click", state.crowdMapClickHandler);
    state.crowdMapClickHandler = null;
  }
  const wrap = document.getElementById("map");
  if (wrap) wrap.classList.remove("map--crowd-pick");
  clearCrowdDraftMarker();
  setCrowdPickMode(false);
}

function rebuildCrowdPinsLayer() {
  if (!map) return;
  if (state.crowdLayer) {
    map.removeLayer(state.crowdLayer);
    state.crowdLayer = null;
  }
  state.crowdLayer = L.layerGroup();
  for (const pin of state.crowdPins) {
    if (pin.lat == null || pin.lng == null) continue;
    const m = L.circleMarker([pin.lat, pin.lng], { ...CROWD_MARKER_STYLE });
    m.bindPopup(crowdPinPopupHtml(pin), { maxWidth: 320, className: "crowd-popup-wrap" });
    state.crowdLayer.addLayer(m);
  }
  syncCrowdLayerVisibility();
}

function syncCrowdLayerVisibility() {
  if (!state.crowdLayer || !map) return;
  const el = document.getElementById("crowd-show-toggle");
  const on = !el || el.checked;
  if (on && !map.hasLayer(state.crowdLayer)) state.crowdLayer.addTo(map);
  if (!on && map.hasLayer(state.crowdLayer)) map.removeLayer(state.crowdLayer);
}

async function loadCrowdPinsAndRender() {
  state.crowdPins = await fetchCrowdPins();
  rebuildCrowdPinsLayer();
}

function readCrowdFormFields(modal) {
  const kind = document.getElementById("crowd-field-kind")?.value || "new_pin";
  const atlasId = document.getElementById("crowd-field-atlas-id")?.value || "";
  const island = atlasId ? state.byId.get(atlasId) : null;
  return {
    lat: Number(modal.dataset.crowdLat),
    lng: Number(modal.dataset.crowdLng),
    name: document.getElementById("crowd-field-name")?.value || "",
    note: document.getElementById("crowd-field-note")?.value || "",
    nameSourceUrl: document.getElementById("crowd-field-source")?.value || "",
    credit: document.getElementById("crowd-field-credit")?.value || "",
    existingPinId: document.getElementById("crowd-field-existing-id")?.value || "",
    contactEmail: document.getElementById("crowd-field-email")?.value || "",
    photoUrls: document.getElementById("crowd-field-photos")?.value || "",
    proposedChanges: document.getElementById("crowd-field-proposed")?.value || "",
    contributionKind: kind,
    atlasIslandId: atlasId,
    atlasIslandName: island?.name || "",
    skipSourceCheck: Boolean(document.getElementById("crowd-field-skip-source")?.checked),
  };
}

function resetCrowdFormFields() {
  for (const id of [
    "crowd-field-name",
    "crowd-field-note",
    "crowd-field-source",
    "crowd-field-credit",
    "crowd-field-existing-id",
    "crowd-field-email",
    "crowd-field-photos",
    "crowd-field-proposed",
    "crowd-field-atlas-id",
  ]) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  const kindEl = document.getElementById("crowd-field-kind");
  if (kindEl) kindEl.value = "new_pin";
  const nameLabel = document.getElementById("crowd-label-name");
  if (nameLabel) nameLabel.textContent = "Name";
  const skip = document.getElementById("crowd-field-skip-source");
  if (skip) skip.checked = false;
}

function applyContributeFormUi(kind) {
  const banner = document.getElementById("crowd-context-banner");
  const proposedWrap = document.getElementById("crowd-field-proposed-wrap");
  const pinWrap = document.getElementById("crowd-field-pin-id-wrap");
  const coordsEl = document.getElementById("crowd-coords-label");
  const kindEl = document.getElementById("crowd-field-kind");
  if (kindEl) kindEl.value = kind;

  if (banner) {
    if (kind === "fix_atlas") {
      const aid = document.getElementById("crowd-field-atlas-id")?.value || "";
      const isl = aid ? state.byId.get(aid) : null;
      banner.hidden = false;
      banner.className = "crowd-context-banner crowd-context-banner--atlas";
      banner.textContent = isl
        ? `Atlas island “${isl.name}” — link sources for name changes; we review before updates go live.`
        : "Atlas island — your changes are reviewed with linked sources before they go live.";
    } else if (kind === "update_pin") {
      banner.hidden = false;
      banner.className = "crowd-context-banner crowd-context-banner--community";
      banner.textContent =
        "Community pin — appears as a gold marker after maintainer approval.";
    } else {
      banner.hidden = false;
      banner.className = "crowd-context-banner crowd-context-banner--community";
      banner.textContent =
        "New community pin — not in the main atlas until verified and sourced.";
    }
  }
  if (proposedWrap) proposedWrap.hidden = kind !== "fix_atlas";
  if (pinWrap) pinWrap.hidden = kind === "fix_atlas";
  if (coordsEl && kind === "fix_atlas") {
    coordsEl.textContent = "Location taken from the atlas island you have open.";
  }
}

function updateContributeSubmitButtons(cfg) {
  const nativeBtn = document.getElementById("crowd-native-submit");
  const githubBtn = document.getElementById("crowd-github-submit");
  const mailtoBtn = document.getElementById("crowd-mailto-submit");
  const hint = document.getElementById("crowd-config-hint");
  const configured = isCrowdSuggestConfigured(cfg);
  if (nativeBtn) {
    nativeBtn.hidden = !configured;
    nativeBtn.textContent = "Send contribution";
  }
  if (mailtoBtn) {
    mailtoBtn.hidden = configured;
    mailtoBtn.classList.toggle("crowd-modal__btn--primary", !configured);
    mailtoBtn.classList.toggle("crowd-modal__btn--ghost", configured);
  }
  if (githubBtn) {
    githubBtn.classList.remove("crowd-modal__btn--primary");
    githubBtn.classList.add("crowd-modal__btn--ghost");
    if (configured && nativeBtn) {
      nativeBtn.classList.add("crowd-modal__btn--primary");
      nativeBtn.classList.remove("crowd-modal__btn--ghost");
    }
  }
  if (nativeBtn && !configured) {
    nativeBtn.classList.remove("crowd-modal__btn--primary");
    nativeBtn.classList.add("crowd-modal__btn--ghost");
  }
  if (hint) {
    if (configured) {
      hint.hidden = true;
    } else {
      hint.hidden = false;
      hint.textContent =
        "One-click send: add GitHub repo secret CROWD_FORM_EMAIL (FormSubmit) or set config.local.js. Until then use GitHub, email app, or copy the pre-filled issue.";
    }
  }
}

function prefillCrowdFormFromPin(pin) {
  if (!pin) return;
  const nameEl = document.getElementById("crowd-field-name");
  const noteEl = document.getElementById("crowd-field-note");
  const srcEl = document.getElementById("crowd-field-source");
  const idEl = document.getElementById("crowd-field-existing-id");
  if (nameEl && pin.name) nameEl.value = pin.name;
  if (noteEl && pin.note) noteEl.value = pin.note;
  if (srcEl && pin.nameSourceUrl) srcEl.value = pin.nameSourceUrl;
  if (idEl) idEl.value = pin.id || "";
}

function initCrowdSuggestUi() {
  const modal = document.getElementById("crowd-modal");
  const btnOpen = document.getElementById("crowd-suggest-btn");
  const stepHub = document.getElementById("crowd-step-hub");
  const stepPick = document.getElementById("crowd-step-pick");
  const stepForm = document.getElementById("crowd-step-form");
  const stepSuccess = document.getElementById("crowd-step-success");
  const backdrop = document.getElementById("crowd-modal-backdrop");
  const hubCancel = document.getElementById("crowd-hub-cancel");
  const cancelPick = document.getElementById("crowd-cancel-pick");
  const closeForm = document.getElementById("crowd-close-form");
  const pickAgain = document.getElementById("crowd-pick-again");
  const githubBtn = document.getElementById("crowd-github-submit");
  const nativeBtn = document.getElementById("crowd-native-submit");
  const successDone = document.getElementById("crowd-success-done");
  const formError = document.getElementById("crowd-form-error");
  const coordsEl = document.getElementById("crowd-coords-label");
  const pickContext = document.getElementById("crowd-pick-context");
  const toggle = document.getElementById("crowd-show-toggle");

  if (!modal || !btnOpen) return;

  let contributeKind = "new_pin";

  loadCrowdSuggestConfig().then((cfg) => {
    state.crowdSuggestConfig = cfg;
    updateContributeSubmitButtons(cfg);
  });

  function hideFormError() {
    if (!formError) return;
    formError.hidden = true;
    formError.textContent = "";
  }

  function showFormError(msg) {
    if (!formError) return;
    formError.hidden = false;
    formError.textContent = msg;
  }

  function showStep(which) {
    if (stepHub) stepHub.hidden = which !== "hub";
    if (stepPick) stepPick.hidden = which !== "pick";
    if (stepForm) stepForm.hidden = which !== "form";
    if (stepSuccess) stepSuccess.hidden = which !== "success";
  }

  function closeModal() {
    clearCrowdMapPicker();
    hideFormError();
    modal.hidden = true;
    contributeKind = "new_pin";
    showStep("hub");
    resetCrowdFormFields();
  }

  function showForm(lat, lng, opts = {}) {
    hideFormError();
    setCrowdPickMode(false);
    const kind = opts.kind || contributeKind;
    contributeKind = kind;
    applyContributeFormUi(kind);
    showStep("form");
    if (coordsEl && kind !== "fix_atlas") {
      coordsEl.textContent = `Pin: ${lat.toFixed(5)}, ${lng.toFixed(5)} (WGS84)`;
    }
    modal.dataset.crowdLat = String(lat);
    modal.dataset.crowdLng = String(lng);
    if (opts.existingPinId) {
      const idEl = document.getElementById("crowd-field-existing-id");
      if (idEl) idEl.value = opts.existingPinId;
    }
    if (opts.atlasIslandId) {
      const aEl = document.getElementById("crowd-field-atlas-id");
      if (aEl) aEl.value = opts.atlasIslandId;
      const isl = state.byId.get(opts.atlasIslandId);
      const proposedEl = document.getElementById("crowd-field-proposed");
      if (isl && proposedEl) {
        proposedEl.placeholder = `What to change about “${isl.name}” — name, description, photos…`;
      }
      const nameLabel = document.getElementById("crowd-label-name");
      if (nameLabel) {
        nameLabel.textContent =
          kind === "fix_atlas" ? "New name (only if changing)" : "Name";
      }
    }
    if (opts.prefillPin) prefillCrowdFormFromPin(opts.prefillPin);
    loadCrowdSuggestConfig().then((cfg) => {
      state.crowdSuggestConfig = cfg;
      updateContributeSubmitButtons(cfg);
    });
  }

  function startPick(kind, hintText) {
    contributeKind = kind || "new_pin";
    clearCrowdMapPicker();
    hideFormError();
    showStep("pick");
    setCrowdPickMode(true);
    if (pickContext) {
      if (hintText) {
        pickContext.hidden = false;
        pickContext.textContent = hintText;
        pickContext.className = "crowd-context-banner crowd-context-banner--community";
      } else {
        pickContext.hidden = true;
      }
    }
    const wrap = document.getElementById("map");
    if (wrap) wrap.classList.add("map--crowd-pick");
    const handler = (e) => {
      if (state.crowdMapClickHandler && map) {
        map.off("click", state.crowdMapClickHandler);
        state.crowdMapClickHandler = null;
      }
      if (wrap) wrap.classList.remove("map--crowd-pick");
      setCrowdDraftMarker(e.latlng.lat, e.latlng.lng);
      showForm(e.latlng.lat, e.latlng.lng, { kind: contributeKind });
    };
    state.crowdMapClickHandler = handler;
    if (!map) return;
    map.on("click", handler);
  }

  function openContributeHub() {
    modal.hidden = false;
    showStep("hub");
    hideFormError();
  }

  function openCrowdModal(opts = {}) {
    modal.hidden = false;
    if (opts.kind === "fix_atlas" && opts.atlasIslandId) {
      const isl = state.byId.get(opts.atlasIslandId);
      if (isl) {
        contributeKind = "fix_atlas";
        resetCrowdFormFields();
        showForm(isl.lat, isl.lng, opts);
        return;
      }
    }
    if (opts.lat != null && opts.lng != null) {
      clearCrowdMapPicker();
      contributeKind = opts.kind || (opts.existingPinId ? "update_pin" : "new_pin");
      setCrowdDraftMarker(Number(opts.lat), Number(opts.lng));
      showForm(Number(opts.lat), Number(opts.lng), opts);
    } else {
      openContributeHub();
    }
  }

  window.openCrowdSuggestModal = openCrowdModal;
  window.openContributeForIsland = (islandId) => {
    const isl = state.byId.get(islandId);
    if (!isl) return;
    openCrowdModal({
      kind: "fix_atlas",
      atlasIslandId: islandId,
      lat: isl.lat,
      lng: isl.lng,
    });
  };

  btnOpen.addEventListener("click", () => openContributeHub());
  document.getElementById("contribute-new-pin")?.addEventListener("click", () => {
    resetCrowdFormFields();
    startPick("new_pin");
  });
  document.getElementById("contribute-update-pin")?.addEventListener("click", () => {
    resetCrowdFormFields();
    startPick(
      "update_pin",
      "Click a gold community pin on the map, or drop a new pin if you are adding one.",
    );
  });
  document.getElementById("contribute-fix-atlas")?.addEventListener("click", () => {
    resetCrowdFormFields();
    if (state.activeId && state.byId.has(state.activeId)) {
      openCrowdModal({
        kind: "fix_atlas",
        atlasIslandId: state.activeId,
        lat: state.byId.get(state.activeId).lat,
        lng: state.byId.get(state.activeId).lng,
      });
      return;
    }
    hideFormError();
    showStep("hub");
    showFormError(
      "Open an island from the list first (so we know which atlas entry you mean), then tap Contribute → Improve an atlas island.",
    );
  });
  hubCancel?.addEventListener("click", closeModal);
  backdrop?.addEventListener("click", () => {
    if (modal.classList.contains("crowd-modal--picking")) return;
    closeModal();
  });
  cancelPick?.addEventListener("click", () => {
    clearCrowdMapPicker();
    openContributeHub();
  });
  closeForm?.addEventListener("click", closeModal);
  successDone?.addEventListener("click", closeModal);
  pickAgain?.addEventListener("click", () => {
    const kind = document.getElementById("crowd-field-kind")?.value || contributeKind;
    resetCrowdFormFields();
    clearCrowdDraftMarker();
    if (kind === "fix_atlas") {
      const aid = state.activeId;
      const isl = aid ? state.byId.get(aid) : null;
      if (isl) {
        showForm(isl.lat, isl.lng, { kind: "fix_atlas", atlasIslandId: aid });
        return;
      }
    }
    startPick(kind);
  });

  async function submitContribution(viaGithub) {
    hideFormError();
    const fields = readCrowdFormFields(modal);
    const v = validateContributionFields(fields);
    if (!v.ok) {
      showFormError(v.message);
      return;
    }
    if (fields.contributionKind !== "fix_atlas") {
      if (!Number.isFinite(fields.lat) || !Number.isFinite(fields.lng)) {
        showFormError("Pick a location on the map first.");
        return;
      }
    }
    if (viaGithub) {
      const url = buildContributionIssueUrl(fields);
      try {
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (_) {
        window.location.href = url;
      }
      showStep("success");
      return;
    }
    const cfg = state.crowdSuggestConfig || (await loadCrowdSuggestConfig());
    state.crowdSuggestConfig = cfg;
    if (!isCrowdSuggestConfigured(cfg)) {
      showFormError("Use “Send via GitHub” — one-click send is not configured on this site yet.");
      return;
    }
    nativeBtn.disabled = true;
    const prevLabel = nativeBtn.textContent;
    nativeBtn.textContent = "Sending…";
    try {
      await submitCrowdSuggestion(fields, cfg);
      showStep("success");
    } catch (err) {
      showFormError(
        `${err?.message || "Could not send."} Try “Send via GitHub” — it works without site setup.`,
      );
    } finally {
      nativeBtn.disabled = false;
      nativeBtn.textContent = prevLabel;
    }
  }

  function submitContributionViaMailto() {
    hideFormError();
    const fields = readCrowdFormFields(modal);
    const v = validateContributionFields(fields);
    if (!v.ok) {
      showFormError(v.message);
      return;
    }
    const body = formatCrowdSuggestionBody(fields);
    const label = fields.name?.trim() || "Unnamed island pin";
    const subject = encodeURIComponent(`Isles of Britain — ${label}`);
    const mailto = `mailto:?subject=${subject}&body=${encodeURIComponent(body)}`;
    window.location.href = mailto;
    showStep("success");
  }

  githubBtn?.addEventListener("click", () => submitContribution(true));
  document.getElementById("crowd-mailto-submit")?.addEventListener("click", submitContributionViaMailto);
  nativeBtn?.addEventListener("click", () => submitContribution(false));

  document.addEventListener("click", (e) => {
    const btn = e.target.closest?.(
      ".crowd-popup__action--edit-details, .crowd-popup__action--suggest-name",
    );
    if (!btn) return;
    e.preventDefault();
    const lat = Number(btn.dataset.crowdLat);
    const lng = Number(btn.dataset.crowdLng);
    const existingPinId = btn.dataset.crowdId || "";
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    map.closePopup();
    const pin = state.crowdPins.find((p) => p.id === existingPinId);
    openCrowdModal({
      lat,
      lng,
      existingPinId,
      kind: "update_pin",
      prefillPin: pin,
    });
  });

  els.detailsContent?.addEventListener("click", (e) => {
    const btn = e.target.closest?.("[data-contribute-island]");
    if (!btn) return;
    e.preventDefault();
    const id = btn.getAttribute("data-contribute-island");
    if (id) openContributeForIsland(id);
  });

  toggle?.addEventListener("change", () => syncCrowdLayerVisibility());
}


function syncIslandUrl(id) {
  try {
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("island", id);
    else url.searchParams.delete("island");
    window.history.replaceState(null, "", url.toString());
  } catch (_) {
    /* non-fatal */
  }
}

function applyRouteFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    const islandId = params.get("island");
    if (islandId && state.byId?.has(islandId)) {
      focusIsland(islandId, { fly: true });
      return;
    }
    const exploreId = params.get("explore");
    if (exploreId && state.discoveryTopics?.some((t) => t.id === exploreId)) {
      setExploreTopic(exploreId, { skipUrl: true });
      return;
    }
    if (params.get("trip")) tryRenderItineraryFromUrl();
  } catch (_) {
    /* non-fatal */
  }
}

// ---------- Data load ----------
/** Merge `full` island record keys onto stub (same object refs as in state.islands). */
function mergeIslandDetailFromFull(stub, full) {
  if (!stub || !full) return;
  for (const k of Object.keys(full)) {
    stub[k] = full[k];
  }
}

async function loadIslands() {
  let settleIslandsIndex;
  _islandsIndexReady = new Promise((r) => {
    settleIslandsIndex = r;
  });
  let usedIndex = false;
  try {
    const idxRes = await fetch("data/islands_index.json");
    if (idxRes.ok) {
      const indexRows = await idxRes.json();
      if (Array.isArray(indexRows) && indexRows.length > 0) {
        state.islands = indexRows;
        state.byId = new Map(indexRows.map((i) => [i.id, i]));
        settleIslandsIndex?.();
        usedIndex = true;
        initFavoritesState();
        populateNationFilter();
        populateSubtypeFilter();
        renderScotlandQuickChips();
        applyFilters();
        loadCrowdPinsAndRender();
        loadFerries().catch(() => {});
        loadFeaturedIslands().catch(() => {});
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      }
    }

    const res = await fetch("data/islands.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const fullRows = await res.json();
    if (!Array.isArray(fullRows) || !fullRows.length) {
      throw new Error("islands.json empty");
    }

    if (usedIndex && state.islands.length === fullRows.length) {
      const fullById = new Map(fullRows.map((i) => [i.id, i]));
      for (const row of state.islands) {
        const full = fullById.get(row.id);
        if (full) mergeIslandDetailFromFull(row, full);
      }
    } else {
      if (usedIndex) {
        console.warn(
          "islands_index.json length mismatch vs islands.json; using full dataset only",
        );
      }
      state.islands = fullRows;
      state.byId = new Map(fullRows.map((i) => [i.id, i]));
    }
    settleIslandsIndex?.();
  } catch (error) {
    console.error("Failed to load islands.json", error);
    els.list.innerHTML = `<li class="island-card" style="color:#ff8a8a">Failed to load island data: ${error.message}. Are you serving the site over HTTP (not file://)?</li>`;
    settleIslandsIndex?.();
    return;
  }

  initFavoritesState();
  initPropertyListingState();
  populateNationFilter();
  populateSubtypeFilter();
  renderScotlandQuickChips();
  applyFilters();
  applyRouteFromUrl();
  loadCrowdPinsAndRender();
  loadFerries().catch(() => {});
  loadFeaturedIslands().catch(() => {});
  loadDiscoveryTopics().catch(() => {});
}

async function loadFeaturedIslands() {
  try {
    const res = await fetch("data/featured_islands.json");
    if (!state.activeExploreTopic) {
      if (!res.ok) return;
      const data = await res.json();
      const rows = Array.isArray(data?.islands) ? data.islands : [];
      state.featuredIslands = rows.filter((r) => r?.id && state.byId?.has(r.id));
      renderExploreStrip(state.featuredIslands, "Notable islands");
    }
  } catch (e) {
    console.warn("featured_islands.json unavailable", e);
  }
}

async function loadDiscoveryTopics() {
  try {
    const res = await fetch("data/discovery_topics.json");
    if (!res.ok) return;
    const data = await res.json();
    state.discoveryTopics = Array.isArray(data?.topics) ? data.topics : [];
    renderDiscoverChips();
    document.getElementById("discover-panel")?.removeAttribute("hidden");
    const exploreId = new URLSearchParams(window.location.search).get("explore");
    if (exploreId && state.discoveryTopics.some((t) => t.id === exploreId)) {
      setExploreTopic(exploreId, { skipUrl: true });
    }
  } catch (e) {
    console.warn("discovery_topics.json unavailable", e);
  }
}

function renderDiscoverChips() {
  const host = document.getElementById("discover-chips");
  if (!host || !state.discoveryTopics?.length) return;
  host.replaceChildren();
  const mk = (id, label, pressed) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "discover-chip" + (pressed ? " is-active" : "");
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", pressed ? "true" : "false");
    b.dataset.topicId = id;
    b.textContent = label;
    return b;
  };
  const all = mk("", "All", !state.activeExploreTopic);
  all.addEventListener("click", () => clearExploreTopic());
  host.appendChild(all);
  for (const t of state.discoveryTopics) {
    const b = mk(t.id, t.title, state.activeExploreTopic === t.id);
    b.addEventListener("click", () => setExploreTopic(t.id));
    host.appendChild(b);
  }
}

function syncExploreUrl(topicId) {
  try {
    const url = new URL(window.location.href);
    if (topicId) url.searchParams.set("explore", topicId);
    else url.searchParams.delete("explore");
    window.history.replaceState(null, "", url.toString());
  } catch (_) {
    /* non-fatal */
  }
}

function clearExploreTopic() {
  state.activeExploreTopic = null;
  state.exploreIslandIds = null;
  const hint = document.getElementById("discover-hint");
  if (hint) {
    hint.hidden = true;
    hint.textContent = "";
  }
  renderDiscoverChips();
  syncExploreUrl(null);
  loadFeaturedIslands().catch(() => {});
  applyFilters();
}

function setExploreTopic(topicId, { skipUrl = false } = {}) {
  const topic = state.discoveryTopics?.find((t) => t.id === topicId);
  if (!topic) return;
  state.activeExploreTopic = topicId;
  state.exploreIslandIds = new Set(
    (topic.islandIds || []).filter((id) => state.byId?.has(id)),
  );
  const hint = document.getElementById("discover-hint");
  if (hint) {
    hint.hidden = false;
    hint.textContent = topic.subtitle || "";
  }
  const presets = topic.filterPresets || {};
  if (els.filterPhoto) els.filterPhoto.checked = Boolean(presets.photosFirst);
  if (els.filterFerry) els.filterFerry.checked = Boolean(presets.ferry);
  if (els.filterElevation) els.filterElevation.checked = Boolean(presets.elevation);
  const scotlandTopics = new Set([
    "scotland-classics",
    "inner-hebrides",
    "outer-hebrides",
    "orkney-shetland",
    "scotland-ferry-hops",
  ]);
  if (els.nationFilter && scotlandTopics.has(topicId)) {
    els.nationFilter.value = "Scotland";
    activeScotlandQuick = null;
    renderScotlandQuickChips();
  }
  renderDiscoverChips();
  renderExploreStrip(topic.islands || [], topic.title);
  if (!skipUrl) syncExploreUrl(topicId);
  applyFilters();
  const pts = (topic.islands || [])
    .map((r) => state.byId.get(r.id))
    .filter((i) => i && i.lat != null && i.lng != null);
  if (pts.length && typeof L !== "undefined" && map) {
    const bounds = L.latLngBounds(pts.map((i) => [i.lat, i.lng]));
    map.fitBounds(bounds.pad(0.12), { maxZoom: 9, duration: 0.6 });
  }
}

function renderExploreStrip(rows, title) {
  const strip = document.getElementById("featured-strip");
  const scroll = document.getElementById("featured-strip-scroll");
  const heading = document.getElementById("featured-heading");
  if (!strip || !scroll || !rows?.length) {
    if (strip) strip.hidden = true;
    return;
  }
  if (heading) heading.textContent = title || "Explore";
  strip.hidden = false;
  scroll.replaceChildren();
  const seenNames = new Set();
  for (const row of rows) {
    const island = state.byId.get(row.id);
    if (!island) continue;
    const nameKey = (row.name || island.name || "").trim().toLowerCase();
    if (nameKey && seenNames.has(nameKey)) continue;
    if (nameKey) seenNames.add(nameKey);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "featured-card";
    btn.setAttribute("role", "listitem");
    btn.setAttribute("aria-label", `${row.name}, ${row.nation || island.nation}`);
    const thumb = row.thumbUrl || island.image;
    const imgHtml = thumb
      ? `<img class="featured-card__img" src="${escapeAttr(thumb)}" alt="" loading="lazy" />`
      : `<span class="featured-card__placeholder" aria-hidden="true">◍</span>`;
    const blurb = row.shortDescription || island.shortDescription || "";
    btn.innerHTML = `
      ${imgHtml}
      <span class="featured-card__body">
        <span class="featured-card__name">${escapeHtml(row.name)}</span>
        ${blurb ? `<span class="featured-card__blurb">${escapeHtml(blurb)}</span>` : ""}
      </span>`;
    btn.addEventListener("click", () => focusIsland(row.id, { fly: true }));
    scroll.appendChild(btn);
  }
}

function populateNationFilter() {
  const nations = Array.from(
    new Set(state.islands.map((i) => i.nation)),
  ).sort();
  const sel = els.nationFilter;
  const keep = sel.querySelector('option[value=""]');
  sel.replaceChildren(keep);
  for (const nation of nations) {
    const opt = document.createElement("option");
    opt.value = nation;
    opt.textContent = nation;
    sel.appendChild(opt);
  }
}

function populateSubtypeFilter() {
  const sel = els.subtypeFilter;
  if (!sel) return;
  const subtypes = Array.from(
    new Set(state.islands.map((i) => i.subtype).filter(Boolean)),
  ).sort();
  const keep = sel.querySelector('option[value=""]');
  sel.replaceChildren(keep);
  for (const sub of subtypes) {
    const opt = document.createElement("option");
    opt.value = sub;
    opt.textContent = formatSubtypeLabel(sub);
    sel.appendChild(opt);
  }
}

function islandHasPhoto(island) {
  if (!island) return false;
  if (island.hasImage === true) return true;
  if (island.images?.length) return true;
  if (island.image) return true;
  const extra = state.galleries?.[island.id];
  return Array.isArray(extra) && extra.length > 0;
}

function islandHasElevation(island) {
  if (!island) return false;
  if (typeof island.highestPointM === "number" && Number.isFinite(island.highestPointM)) {
    return true;
  }
  const conf = island.highestPointConfidence;
  return Boolean(conf && conf !== "n/a");
}

function islandThumbUrl(island) {
  if (!island) return null;
  const img = island.images?.[0];
  if (img?.thumbUrl) return img.thumbUrl;
  if (img?.url) return img.url;
  if (island.image) return island.image;
  const extra = state.galleries?.[island.id]?.[0];
  if (extra?.thumbUrl) return extra.thumbUrl;
  if (extra?.url) return extra.url;
  return null;
}

function renderScotlandQuickChips() {
  const host = document.getElementById("scotland-quick-chips");
  if (!host) return;
  host.replaceChildren();
  for (const preset of SCOTLAND_QUICK_FILTERS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className =
      "scotland-quick__chip" + (activeScotlandQuick === preset.id ? " is-active" : "");
    b.textContent = preset.label;
    b.addEventListener("click", () => applyScotlandQuickFilter(preset));
    host.appendChild(b);
  }
}

function applyScotlandQuickFilter(preset) {
  if (activeScotlandQuick === preset.id) {
    activeScotlandQuick = null;
    if (els.nationFilter) els.nationFilter.value = "";
    if (els.typeFilter) els.typeFilter.value = "";
    if (els.filterPhoto) els.filterPhoto.checked = false;
    if (els.filterFerry) els.filterFerry.checked = false;
    renderScotlandQuickChips();
    applyFilters();
    return;
  }
  activeScotlandQuick = preset.id;
  if (state.activeExploreTopic) {
    state.activeExploreTopic = null;
    state.exploreIslandIds = null;
    const hint = document.getElementById("discover-hint");
    if (hint) {
      hint.hidden = true;
      hint.textContent = "";
    }
    renderDiscoverChips();
    syncExploreUrl(null);
    loadFeaturedIslands().catch(() => {});
  }
  if (els.nationFilter) els.nationFilter.value = preset.nation || "";
  if (els.typeFilter) els.typeFilter.value = preset.type || "";
  if (els.filterPhoto) els.filterPhoto.checked = Boolean(preset.photo);
  if (els.filterFerry && !els.filterFerry.disabled) {
    els.filterFerry.checked = Boolean(preset.ferry);
  }
  renderScotlandQuickChips();
  applyFilters();
  if (preset.nation === "Scotland" && map) {
    map.setView([57.2, -4.5], 6, { animate: true, duration: 0.5 });
  }
}

function resetAllFilters() {
  activeScotlandQuick = null;
  if (els.search) els.search.value = "";
  if (els.typeFilter) els.typeFilter.value = "";
  if (els.nationFilter) els.nationFilter.value = "";
  if (els.favoritesFilter) els.favoritesFilter.value = "";
  if (els.areaMinFilter) els.areaMinFilter.value = "";
  if (els.subtypeFilter) els.subtypeFilter.value = "";
  if (els.confidenceFilter) els.confidenceFilter.value = "";
  if (els.filterPhoto) els.filterPhoto.checked = false;
  if (els.filterFerry) els.filterFerry.checked = false;
  if (els.filterElevation) els.filterElevation.checked = false;
  renderScotlandQuickChips();
  if (state.activeExploreTopic) clearExploreTopic();
  else applyFilters();
}

function renderActiveFilterChips() {
  const host = document.getElementById("active-filter-chips");
  if (!host) return;
  const chips = [];
  const q = els.search?.value?.trim();
  if (q) {
    chips.push({
      label: `Search: ${q}`,
      clear: () => {
        if (els.search) els.search.value = "";
      },
    });
  }
  if (els.nationFilter?.value) {
    chips.push({
      label: els.nationFilter.value,
      clear: () => {
        els.nationFilter.value = "";
        activeScotlandQuick = null;
        renderScotlandQuickChips();
      },
    });
  }
  if (els.typeFilter?.value) {
    const labels = { sea: "Sea", lake: "Loch / lake", river: "River", unknown: "Needs review" };
    chips.push({
      label: labels[els.typeFilter.value] || els.typeFilter.value,
      clear: () => {
        els.typeFilter.value = "";
      },
    });
  }
  if (els.favoritesFilter?.value === "favorites") {
    chips.push({
      label: "Saved",
      clear: () => {
        els.favoritesFilter.value = "";
      },
    });
  }
  if (els.filterPhoto?.checked) {
    chips.push({
      label: "Has photo",
      clear: () => {
        els.filterPhoto.checked = false;
      },
    });
  }
  if (els.filterFerry?.checked) {
    chips.push({
      label: "Ferry",
      clear: () => {
        els.filterFerry.checked = false;
      },
    });
  }
  if (els.filterElevation?.checked) {
    chips.push({
      label: "Summit",
      clear: () => {
        els.filterElevation.checked = false;
      },
    });
  }
  if (els.filterForSale?.checked) {
    chips.push({
      label: "For sale",
      clear: () => {
        els.filterForSale.checked = false;
      },
    });
  }
  const areaMin = parseFloat(els.areaMinFilter?.value) || 0;
  if (areaMin > 0) {
    chips.push({
      label: `≥ ${areaMin} km²`,
      clear: () => {
        if (els.areaMinFilter) els.areaMinFilter.value = "";
      },
    });
  }
  if (els.subtypeFilter?.value) {
    chips.push({
      label: formatSubtypeLabel(els.subtypeFilter.value),
      clear: () => {
        els.subtypeFilter.value = "";
      },
    });
  }
  if (els.confidenceFilter?.value) {
    const confLabels = {
      curated: "Curated",
      "hide-unconfirmed": "Hide needs review",
    };
    chips.push({
      label: confLabels[els.confidenceFilter.value] || els.confidenceFilter.value,
      clear: () => {
        els.confidenceFilter.value = "";
      },
    });
  }
  if (state.activeExploreTopic) {
    const t = state.discoveryTopics?.find((x) => x.id === state.activeExploreTopic);
    if (t) {
      chips.push({
        label: t.title,
        clear: () => clearExploreTopic(),
      });
    }
  }
  host.hidden = chips.length === 0;
  host.replaceChildren();
  for (const chip of chips) {
    const el = document.createElement("span");
    el.className = "filter-chip";
    const label = document.createElement("span");
    label.textContent = chip.label;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "filter-chip__clear";
    btn.setAttribute("aria-label", `Remove filter: ${chip.label}`);
    btn.textContent = "×";
    btn.addEventListener("click", () => {
      chip.clear();
      applyFilters();
    });
    el.append(label, btn);
    host.appendChild(el);
  }
}

function updateMapIslandPeek(islandId) {
  const bar = document.getElementById("map-island-peek");
  const nameEl = document.getElementById("map-island-peek-name");
  if (!bar || !nameEl) return;
  const isl = islandId ? state.byId.get(islandId) : null;
  if (!isl || !mobileNav.isActive() || mobileNav.view !== "map") {
    bar.hidden = true;
    return;
  }
  nameEl.textContent = isl.name;
  bar.hidden = false;
}

function hideMapIslandPeek() {
  const bar = document.getElementById("map-island-peek");
  if (bar) bar.hidden = true;
}

function listSortCompare(a, b, { photosFirst = false } = {}) {
  if (photosFirst) {
    const ap = islandHasPhoto(a) ? 1 : 0;
    const bp = islandHasPhoto(b) ? 1 : 0;
    if (ap !== bp) return bp - ap;
  }
  return a.name.localeCompare(b.name);
}

// ---------- Filtering ----------
// Normalise a string for searching: NFKD-decompose, strip diacritics and
// non-alphanumerics, lowercase. Cached on the island object so we don't
// redo it 6,748× per keystroke.
function _searchNorm(s) {
  if (!s) return "";
  return s
    .toString()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function _ensureSearchIndex(island) {
  if (island.__searchName != null) return;
  island.__searchName = _searchNorm(island.name);
  // Lower-priority fields searched as a fallback only.
  island.__searchHay = _searchNorm(
    [
      island.archipelago,
      island.nation,
      island.shortDescription,
      ...(island.tags || []),
      ...(island.names ? Object.values(island.names) : []),
    ]
      .filter(Boolean)
      .join(" "),
  );
}

// Fuzzy score for a query against an island. Returns -Infinity if the
// query doesn't appear at all, else a positive score (higher = better).
// Tuning prioritises name matches: exact > prefix > word-start > subseq.
function _scoreIsland(island, q) {
  _ensureSearchIndex(island);
  const name = island.__searchName;
  if (!q) return 0;
  if (!name) return -Infinity;
  // 1. Exact name.
  if (name === q) return 1000;
  // 2. Prefix (very common from typing).
  if (name.startsWith(q)) return 800 - name.length;
  // 3. Word-start (any word in the name begins with the query).
  const words = name.split(" ");
  for (const w of words) {
    if (w.startsWith(q)) return 600 - name.length;
  }
  // 4. Substring of name.
  if (name.includes(q)) return 400 - name.indexOf(q);
  // 5. Subsequence: all query chars appear in name in order, possibly
  //    with gaps. Penalised by gap length so contiguous beats spread.
  let qi = 0;
  let gap = 0;
  let runs = 0;
  let lastHit = -1;
  for (let i = 0; i < name.length && qi < q.length; i++) {
    if (name[i] === q[qi]) {
      if (lastHit !== -1 && i - lastHit > 1) gap += i - lastHit - 1;
      else if (lastHit !== -1) runs++;
      lastHit = i;
      qi++;
    }
  }
  if (qi === q.length) {
    return 200 - gap - (name.length - q.length);
  }
  // 6. Substring of the broader haystack (archipelago, nation, etc.).
  if (island.__searchHay.includes(q)) return 50;
  return -Infinity;
}

function applyFilters() {
  const q = _searchNorm(els.search.value);
  const type = els.typeFilter.value;
  const nation = els.nationFilter.value;
  const favOnly = els.favoritesFilter?.value === "favorites";
  const photoOnly = Boolean(els.filterPhoto?.checked);
  const ferryOnly = Boolean(els.filterFerry?.checked);
  const forSaleOnly = Boolean(els.filterForSale?.checked);
  const elevationOnly = Boolean(els.filterElevation?.checked);
  const areaMin = parseFloat(els.areaMinFilter?.value) || 0;
  const subtype = els.subtypeFilter?.value || "";
  const confidence = els.confidenceFilter?.value || "";
  const topic = state.discoveryTopics?.find((t) => t.id === state.activeExploreTopic);
  const photosFirst = photoOnly || Boolean(topic?.filterPresets?.photosFirst);
  if (els.listHeading) {
    if (favOnly) els.listHeading.textContent = "Saved islands";
    else if (topic) els.listHeading.textContent = topic.title;
    else els.listHeading.textContent = "Islands";
  }

  const passesScope = (i) => {
    if (state.exploreIslandIds && !state.exploreIslandIds.has(i.id)) return false;
    if (type && i.type !== type) return false;
    if (nation && i.nation !== nation) return false;
    if (favOnly && !isFavoriteIsland(i.id)) return false;
    if (photoOnly && !islandHasPhoto(i)) return false;
    if (ferryOnly) {
      if (!state.ferryIslandIds?.has(i.id)) return false;
    }
    if (forSaleOnly && !islandHasPropertyListing(i)) return false;
    if (elevationOnly && !islandHasElevation(i)) return false;
    if (areaMin > 0 && (i.areaKm2 || 0) < areaMin) return false;
    if (subtype && i.subtype !== subtype) return false;
    if (confidence === "curated" && i.source !== "curated") return false;
    if (
      confidence === "hide-unconfirmed"
      && i.classification?.confidence === "unconfirmed"
    ) {
      return false;
    }
    return true;
  };

  if (q) {
    // Score and rank.
    const scored = [];
    for (const i of state.islands) {
      if (!passesScope(i)) continue;
      const s = _scoreIsland(i, q);
      if (s > -Infinity) scored.push({ island: i, score: s });
    }
    // Stable secondary: photos first (when enabled), then name.
    scored.sort((a, b) =>
      b.score - a.score
        || listSortCompare(a.island, b.island, { photosFirst }),
    );
    state.filtered = scored.map((x) => x.island);
  } else {
    state.filtered = state.islands.filter(passesScope);
    state.filtered.sort((a, b) => listSortCompare(a, b, { photosFirst }));
  }

  renderList();
  rebuildMarkerLayer();
  renderActiveFilterChips();
}

[
  els.search,
  els.typeFilter,
  els.nationFilter,
  els.areaMinFilter,
  els.subtypeFilter,
  els.confidenceFilter,
].forEach((el) => {
  if (!el) return;
  el.addEventListener("input", applyFilters);
  el.addEventListener("change", applyFilters);
});

[els.filterPhoto, els.filterFerry, els.filterElevation, els.filterForSale].forEach((el) => {
  if (!el) return;
  el.addEventListener("change", applyFilters);
});

if (els.favoritesFilter) {
  els.favoritesFilter.addEventListener("change", () => {
    const wantSaved = els.favoritesFilter.value === "favorites";
    if (wantSaved && !hasFavoritesAccess()) {
      const revert = els.favoritesFilter.dataset.prevValue || "";
      ensureFavoritesAccess(() => {
        els.favoritesFilter.value = "favorites";
        applyFilters();
      });
      els.favoritesFilter.value = revert;
      return;
    }
    if (!wantSaved) els.favoritesFilter.dataset.prevValue = els.favoritesFilter.value;
    applyFilters();
  });
}

// ---------- Virtualised list ----------
let listScroller = null;
let listSpacer = null;
let listInner = null;
let listRenderRaf = 0;

function shouldRenderListWindow() {
  if (typeof mobileNav !== "undefined" && mobileNav.isActive() && mobileNav.view !== "islands") {
    return false;
  }
  return true;
}

function scheduleRenderListWindow() {
  if (!shouldRenderListWindow()) return;
  if (listRenderRaf) return;
  listRenderRaf = window.requestAnimationFrame(() => {
    listRenderRaf = 0;
    renderListWindow();
  });
}

function ensureListScaffolding() {
  if (listScroller) return;
  els.list.style.position = "relative";
  els.list.style.padding = "8px";
  listScroller = els.sidebar; // sidebar is the actual scroll container
  listSpacer = document.createElement("div");
  listSpacer.style.height = "0px";
  listSpacer.style.pointerEvents = "none";
  listInner = document.createElement("div");
  listInner.style.position = "absolute";
  listInner.style.top = "0";
  listInner.style.left = "8px";
  listInner.style.right = "8px";
  els.list.appendChild(listSpacer);
  els.list.appendChild(listInner);
  listScroller.addEventListener("scroll", scheduleRenderListWindow, { passive: true });
  window.addEventListener("resize", scheduleRenderListWindow);
}

function renderList() {
  ensureListScaffolding();
  els.count.textContent = state.filtered.length.toString();
  listSpacer.style.height = `${state.filtered.length * ROW_HEIGHT}px`;
  // Reset scroll to top when filter changes
  listScroller.scrollTop = 0;
  scheduleRenderListWindow();
}

function renderListWindow() {
  if (!listInner || !shouldRenderListWindow()) return;
  // Sidebar scrolls as a whole; subtract the section header to get the
  // offset into the list.
  const headerHeight =
    els.list.parentElement.querySelector(".sidebar-section-header")
      ?.offsetHeight || 0;
  const scrollTop = Math.max(0, listScroller.scrollTop - headerHeight);
  const viewportH = listScroller.clientHeight;
  const total = state.filtered.length;

  const first = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - VIEWPORT_PADDING);
  const last = Math.min(
    total,
    Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + VIEWPORT_PADDING,
  );

  listInner.style.transform = `translateY(${first * ROW_HEIGHT}px)`;
  listInner.innerHTML = "";

  for (let i = first; i < last; i++) {
    const island = state.filtered[i];
    if (!island) continue;
    const wrap = document.createElement("div");
    const hasListing = islandHasPropertyListing(island);
    const listingLead = hasListing ? primaryPropertyListing(island) : null;
    wrap.className =
      "island-card" +
      (island.id === state.activeId ? " is-active" : "") +
      (hasListing ? " island-card--for-sale" : "");
    wrap.dataset.id = island.id;

    const main = document.createElement("button");
    main.type = "button";
    main.className = "island-card__main";
    main.style.height = `${ROW_HEIGHT - 8}px`;
    main.setAttribute(
      "aria-label",
      `${island.name}, ${island.nation}, ${formatPopulation(island.population)}`,
    );
    const hasFerry = state.ferryIslandIds && state.ferryIslandIds.has(island.id);
    const unconfirmed = island.classification?.confidence === "unconfirmed";
    const fav = isFavoriteIsland(island.id);
    const thumb = islandThumbUrl(island);
    const thumbHtml = thumb
      ? `<img class="island-card__thumb" src="${escapeAttr(thumb)}" alt="" loading="lazy" decoding="async" />`
      : `<span class="island-card__thumb island-card__thumb--empty" aria-hidden="true">No photo</span>`;
    main.innerHTML = `
      ${thumbHtml}
      <div class="island-card__text">
        <div class="island-card__title">
          <span class="dot dot--${island.type}"></span>
          ${escapeHtml(island.name)}
          ${unconfirmed ? '<span class="island-card__unconfirmed" title="Needs review">?</span>' : ""}
          ${hasFerry ? '<span class="island-card__ferry-icon" title="Ferry-accessible">⛴</span>' : ""}
          ${hasListing ? '<span class="island-card__sale-pill">For sale</span>' : ""}
        </div>
        <div class="island-card__meta">
          <span>${escapeHtml(island.nation)}</span>
          ${island.archipelago ? `<span>${escapeHtml(island.archipelago)}</span>` : ""}
          <span>${formatPopulation(island.population)}</span>
        </div>
      </div>
    `;
    main.addEventListener("click", () => focusIsland(island.id, { fly: true }));

    const favBtn = document.createElement("button");
    favBtn.type = "button";
    favBtn.className = "island-card__fav" + (fav ? " is-favorite" : "");
    favBtn.dataset.favId = island.id;
    favBtn.setAttribute("aria-pressed", fav ? "true" : "false");
    favBtn.setAttribute(
      "aria-label",
      fav ? "Remove from saved islands" : "Save island to list",
    );
    favBtn.title = fav ? "Remove from saved" : "Save to list";
    favBtn.textContent = fav ? "♥" : "♡";
    favBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFavoriteIsland(island.id);
    });

    wrap.appendChild(main);
    if (listingLead?.url) {
      const listBtn = document.createElement("a");
      listBtn.className = "island-card__listing-link";
      listBtn.href = listingLead.url;
      listBtn.target = "_blank";
      listBtn.rel = "noopener noreferrer";
      listBtn.title = listingLead.title || "Open property listing";
      listBtn.setAttribute("aria-label", `Open property listing for ${island.name}`);
      listBtn.textContent = "Listing ↗";
      listBtn.addEventListener("click", (e) => e.stopPropagation());
      wrap.appendChild(listBtn);
    }
    wrap.appendChild(favBtn);
    listInner.appendChild(wrap);
  }
}

// ---------- Markers ----------
function islandsForMarkerPaint() {
  const list = state.filtered.length ? state.filtered : state.islands;
  if (!list.length) return list;
  const z = map.getZoom();
  const bounds = map.getBounds();
  if (!bounds?.isValid?.()) return list;
  // Always cull to the viewport — painting the full filtered set at high zoom
  // left thousands of canvas circles and caused dark streaks on the map.
  const pad = z <= LOW_ZOOM_MARKER_MAX ? 0.15 : z <= 11 ? 0.1 : 0.06;
  const padded = bounds.pad(pad);
  return list.filter(
    (i) =>
      Number.isFinite(i.lat) &&
      Number.isFinite(i.lng) &&
      padded.contains([i.lat, i.lng]),
  );
}

function makeMarker(island) {
  const color = TYPE_COLORS[island.type] || TYPE_COLORS.sea;
  let radius = Math.max(
    7,
    Math.min(15, Math.log10((island.areaKm2 || 0.05) + 1) * 6 + 5),
  );
  let fillColor = color;
  let fillOpacity = 0.9;
  let strokeColor = "#ffffff";
  let strokeWeight = 1.2;
  let className = "marker-vis";
  if (state.exploreIslandIds?.has(island.id)) {
    fillColor = "#f4d35e";
    radius = Math.min(17, radius + 2);
    fillOpacity = 1;
  }
  const onSale = islandHasPropertyListing(island);
  if (onSale) {
    fillColor = FOR_SALE_MARKER_FILL;
    strokeColor = FOR_SALE_MARKER_STROKE;
    strokeWeight = 2.4;
    radius = Math.min(18, radius + 3);
    fillOpacity = 1;
    className = "marker-vis marker-vis--for-sale";
  }

  const paintRadius = Math.max(radius, onSale ? 12 : 10);
  const marker = L.circleMarker([island.lat, island.lng], {
    radius: paintRadius,
    color: strokeColor,
    weight: strokeWeight,
    fillColor,
    fillOpacity,
    className,
  });
  if (onSale) {
    const lead = primaryPropertyListing(island);
    const tip = lead?.url
      ? `<span class="map-sale-tooltip"><strong>For sale</strong> · ${escapeHtml(island.name)}<br><a class="map-sale-tooltip__link" href="${escapeAttr(lead.url)}" target="_blank" rel="noopener noreferrer">Open listing ↗</a></span>`
      : `<span class="map-sale-tooltip"><strong>For sale</strong> · ${escapeHtml(island.name)}</span>`;
    marker.bindTooltip(tip, {
      direction: "top",
      offset: [0, -6],
      className: "map-sale-tooltip-wrap",
      interactive: true,
    });
    marker.bindPopup(propertyListingPopupHtml(island), {
      maxWidth: 300,
      className: "sale-popup-wrap",
    });
    marker.on("popupopen", (ev) => {
      const btn = ev.popup.getElement()?.querySelector(".sale-popup__atlas-btn");
      btn?.addEventListener("click", () => {
        map.closePopup();
        focusIsland(island.id, { fly: false });
      });
    });
  } else {
    marker.bindTooltip(island.name, { direction: "top", offset: [0, -4] });
  }
  marker.on("click", () => focusIsland(island.id, { fly: false }));
  return marker;
}

function rebuildMarkerLayer() {
  if (!state.islands.length) return;
  const bounds = map.getBounds();
  if (!bounds?.isValid?.()) return;
  // Clear & rebuild the active marker layer with the currently-filtered set.
  // Markers are cheap to recreate; reusing them across cluster/flat would
  // double the memory.
  clusterLayer.clearLayers();
  flatLayer.clearLayers();
  state.markers.clear();

  const layer = activeMarkerLayer;
  const paintSet = islandsForMarkerPaint();
  for (const island of paintSet) {
    // Saved islands are shown as ♥ markers on favoritesMapLayer (always visible).
    if (hasFavoritesAccess() && isFavoriteIsland(island.id)) continue;
    // For-sale islands use dedicated £ badges on propertyListingMapLayer (always on map).
    if (islandHasPropertyListing(island)) continue;
    const m = makeMarker(island);
    state.markers.set(island.id, m);
    if (layer === clusterLayer) {
      clusterLayer.addLayer(m);
    } else {
      flatLayer.addLayer(m);
    }
  }
  rebuildFavoritesMapLayer();
  rebuildPropertyListingMapLayer();
  // #region agent log
  const paintN = islandsForMarkerPaint().length;
  const hitEls = document.querySelectorAll(".marker-hit").length;
  const b = map.getBounds();
  fetch("http://127.0.0.1:7720/ingest/def19690-94b9-4670-be7c-26220155de0a", { method: "POST", headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5f60f5" }, body: JSON.stringify({ sessionId: "5f60f5", runId: "post-fix-4", hypothesisId: "H8", location: "app.js:rebuildMarkerLayer", message: "markers rebuilt", data: { zoom: map.getZoom(), paintN, filteredLen: state.filtered.length, islandsLen: state.islands.length, boundsValid: b?.isValid?.(), markersOnLayer: state.markers.size }, timestamp: Date.now() }) }).catch(() => {});
  // #endregion
}

function scheduleMarkerViewportRefresh() {
  if (markerViewportTimer) clearTimeout(markerViewportTimer);
  markerViewportTimer = setTimeout(() => {
    markerViewportTimer = null;
    rebuildMarkerLayer();
  }, 120);
}

map.on("moveend zoomend", scheduleMarkerViewportRefresh);

// ---------- Details panel ----------
function focusIsland(id, { fly } = { fly: true }) {
  const island = state.byId.get(id);
  if (!island) return;

  state.activeId = id;
  syncIslandUrl(id);
  // Re-render list so the active card is highlighted (cheap because virtualised)
  scheduleRenderListWindow();

  renderDetails(island);
  // #region agent log
  fetch("http://127.0.0.1:7720/ingest/def19690-94b9-4670-be7c-26220155de0a", { method: "POST", headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5f60f5" }, body: JSON.stringify({ sessionId: "5f60f5", hypothesisId: "H4", location: "app.js:focusIsland", message: "island focused", data: { id, zoom: map.getZoom(), markerHits: document.querySelectorAll(".marker-hit").length, hasPoly: !!state.activePolygon }, timestamp: Date.now() }) }).catch(() => {});
  // #endregion
  if (mobileNav.isActive()) mobileNav.setView("islands");

  if (fly) {
    const targetZoom = island.type === "river" ? 14 : island.areaKm2 < 1 ? 12 : island.areaKm2 < 50 ? 11 : 10;
    map.flyTo([island.lat, island.lng], targetZoom, { duration: 0.7 });
  }

  loadAndShowPolygon(island);

  // Lazy-fetch the gallery extras and re-render the hero block once they
  // arrive. Subsequent island clicks reuse the cached galleries dict.
  loadGalleries().then(() => {
    if (state.activeId !== id) return;  // user navigated away while loading
    if (island.__galleryMerged) return; // already had extras for this island
    const extras = state.galleries[id];
    if (!Array.isArray(extras) || !extras.length) return;
    refreshGalleryInPlace(island);
  });

  // Lazy-fetch the ferry data and re-render the "How to get there" block
  // once it arrives. Subsequent island clicks are synchronous.
  Promise.all([loadFerries(), loadCauseways()]).then(() => {
    if (state.activeId !== id) return;
    refreshFerriesInPlace(island);
  });

  applyIslandSeo(island);
}

// Drop-in replacement for the ferry block when ferries.json has finished
// loading. Preserves scroll and the OS detail map.
function refreshFerriesInPlace(island) {
  const block = document.getElementById("ferry-block");
  if (!block) return;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = renderFerries(island);
  const fresh = wrapper.firstElementChild;
  if (fresh) block.replaceWith(fresh);
}

// Order routes that touch this island so the most useful crossing comes
// first: car ferries > foot ferries; year-round > seasonal; several-daily
// > daily > weekly > on-demand.
const _FERRY_TYPE_RANK = { "car-and-foot": 0, "foot-only": 1, "passenger-only": 1, "charter": 2 };
const _FERRY_SEASON_RANK = { "year-round": 0, "seasonal": 1, "summer-only": 1, "on-demand": 2 };
const _FERRY_FREQ_RANK = { "several-daily": 0, "daily": 1, "weekly": 2, "on-demand": 3, null: 4, undefined: 4 };

function _ferryRouteScore(r) {
  return (
    (_FERRY_TYPE_RANK[r.type] ?? 9) * 1000 +
    (_FERRY_SEASON_RANK[r.seasonality] ?? 9) * 100 +
    (_FERRY_FREQ_RANK[r.frequencyBand] ?? 9) * 10
  );
}

const _FERRY_TYPE_LABEL = {
  "car-and-foot": "Car + foot",
  "foot-only": "Foot only",
  "passenger-only": "Foot only",
  "charter": "Charter",
};
const _FERRY_SEASON_LABEL = {
  "year-round": "Year-round",
  "summer-only": "Summer only",
  "seasonal": "Seasonal",
  "on-demand": "On demand",
};
const _FERRY_FREQ_LABEL = {
  "several-daily": "Several daily",
  "daily": "Daily",
  "weekly": "Weekly",
  "on-demand": "On demand",
};

function _ferryFreshnessNote(routes) {
  if (!routes?.length) return "";
  const dates = routes
    .map((r) => r.lastVerified)
    .filter(Boolean)
    .map((d) => Date.parse(d))
    .filter((t) => Number.isFinite(t));
  if (!dates.length) {
    return `<p class="ferry-freshness">Route schedules are indicative — confirm times with the operator before you travel.</p>`;
  }
  const newest = new Date(Math.max(...dates));
  const oldest = new Date(Math.min(...dates));
  const staleCount = routes.filter((r) => r.lastVerified && _routeIsStale(r.lastVerified, 180)).length;
  const fmt = (d) => d.toISOString().slice(0, 10);
  let line = `Data last verified between ${fmt(oldest)} and ${fmt(newest)}.`;
  if (staleCount > 0) {
    line += ` ${staleCount} connection${staleCount === 1 ? "" : "s"} marked stale (>180 days) — check the operator timetable.`;
  }
  return `<p class="ferry-freshness">${escapeHtml(line)}</p>`;
}

function _routeIsStale(lastVerifiedStr, maxDays) {
  if (!lastVerifiedStr) return false;
  const t = Date.parse(lastVerifiedStr);
  if (!Number.isFinite(t)) return false;
  const ageDays = (Date.now() - t) / (24 * 60 * 60 * 1000);
  return ageDays > maxDays;
}

function _formatDuration(min) {
  if (min == null || !Number.isFinite(min)) return "—";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function _bestTerminalName(term) {
  if (!term) return "—";
  if (term.names && typeof term.names === "object") {
    const en = term.names.en;
    if (en) return en;
  }
  return term.name || "—";
}

// Returns the first regional-language label that isn't the English one,
// or null if none available. Drives the "(Gàidhlig)" annotation in
// ferry cards.
function _localTerminalName(term) {
  if (!term?.names) return null;
  for (const lang of ["gd", "cy", "ga", "gv", "kw", "fr", "nrf"]) {
    const v = term.names[lang];
    if (v && v !== term.names.en) {
      return { lang, value: v, label: (LANG_LABELS && LANG_LABELS[lang]) || lang };
    }
  }
  return null;
}

const _LISTING_TYPE_LABEL = {
  whole_island: "Whole island",
  residential: "Residential",
  land: "Land",
};

function renderPropertyListings(island) {
  const listings = island.propertyListings;
  if (!Array.isArray(listings) || !listings.length) {
    return "";
  }
  const items = listings
    .map((L) => {
      const typeLabel = _LISTING_TYPE_LABEL[L.listingType] || L.listingType || "Listing";
      const price = L.priceDisplay || (L.priceGBP != null ? `£${Number(L.priceGBP).toLocaleString("en-GB")}` : "");
      const conf =
        L.matchedConfidence === "low"
          ? ' <span class="property-listing__low" title="Match needs verification">?</span>'
          : "";
      const src = L.source ? `<span class="property-listing__source">${escapeHtml(L.source)}</span>` : "";
      return `<li class="property-listing">
        <a class="property-listing__link" href="${escapeAttr(L.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(L.title || "View listing")} ↗</a>
        <span class="property-listing__meta">${escapeHtml(typeLabel)}${price ? ` · ${escapeHtml(price)}` : ""}${conf} ${src}</span>
      </li>`;
    })
    .join("");
  return `<div class="section property-listings-section">
    <h3>On the market</h3>
    <p class="property-listings__lead">Outbound links to estate agents and brokers — not hosted by this atlas. Confirm price and availability on the source site.</p>
    <ul class="property-listing-list">${items}</ul>
    <p class="property-listings__disclaimer">We are not an estate agent. Listings may be incomplete or out of date.</p>
  </div>`;
}

function renderFerries(island) {
  if (!state.ferryRoutesByIsland) {
    return `<div class="section ferry-section" id="ferry-block">
      <h3>How to get there</h3>
      <p class="ferry-loading">Loading ferry connections…</p>
    </div>`;
  }
  const routes = findFerriesForIsland(island.id);
  const causeway = findCausewayForIsland(island);
  if (!routes.length && !causeway) {
    return `<div class="section ferry-section" id="ferry-block" hidden></div>`;
  }

  const sorted = routes.slice().sort((a, b) => _ferryRouteScore(a) - _ferryRouteScore(b));
  const cards = sorted.map((r) => _renderFerryCard(r, island)).join("");
  const causewayBlock = causeway ? _renderCausewayBlock(causeway) : "";
  const freshnessNote = _ferryFreshnessNote(sorted);

  const title = routes.length ? "How to get there" : "Causeway access";

  return `<div class="section ferry-section" id="ferry-block">
    <h3>${escapeHtml(title)}</h3>
    ${routes.length ? `<p class="ferry-subtitle">${sorted.length} ferry connection${sorted.length === 1 ? "" : "s"} published for this island.</p>` : ""}
    ${freshnessNote}
    ${causewayBlock}
    ${cards ? `<div class="ferry-card-list">${cards}</div>` : ""}
    ${routes.length ? `<p class="ferry-disclosure">Some onward-travel links below are affiliate links (<abbr title="Sponsored / commission-paying link">sponsored</abbr>) - they cost you nothing extra and help keep this atlas free. Ferry operator links are not affiliated.</p>` : ""}
  </div>`;
}

function _renderCausewayBlock(c) {
  const accessLabel = ({
    "vehicle-causeway": "Vehicle causeway · tidal",
    "foot-causeway": "Foot causeway · tidal",
    "vehicle-bridge": "Permanent road bridge",
    "foot-bridge": "Permanent footbridge",
  })[c.accessType] || c.accessType;
  return `<aside class="causeway-card" role="note">
    <header class="causeway-card__header">
      <span class="causeway-card__icon" aria-hidden="true">⚠</span>
      <div>
        <div class="causeway-card__type">${escapeHtml(accessLabel)}</div>
        <div class="causeway-card__summary">${escapeHtml(c.summary || "")}</div>
      </div>
    </header>
    ${c.safeCrossingWindow ? `<p class="causeway-card__window"><strong>Safe crossing:</strong> ${escapeHtml(c.safeCrossingWindow)}</p>` : ""}
    ${c.warning ? `<p class="causeway-card__warning">${escapeHtml(c.warning)}</p>` : ""}
    ${c.officialSource ? `<a class="causeway-card__source" href="${escapeAttr(c.officialSource)}" target="_blank" rel="noopener">${escapeHtml(c.officialSourceLabel || "Official tide-times")} ↗</a>` : ""}
  </aside>`;
}

function _renderFerryCard(route, island) {
  const op = route._operator;
  const opLabel = op ? (op.shortName || op.name) : (route.operatorId || "Unknown operator");
  const fromTerm = route._fromTerminal;
  const toTerm = route._toTerminal;

  // Decide which terminal is the "mainland" one (i.e. NOT this island) and
  // which is the "island" terminal — used for naming the affiliate links.
  let mainlandTerm = null;
  let mainlandSide = null;
  if (route._fromIsland === island.id && route._toIsland !== island.id) {
    mainlandTerm = toTerm;
    mainlandSide = "to";
  } else if (route._toIsland === island.id && route._fromIsland !== island.id) {
    mainlandTerm = fromTerm;
    mainlandSide = "from";
  } else if (route._fromIsland === island.id) {
    mainlandTerm = toTerm;
    mainlandSide = "to";
  } else {
    mainlandTerm = fromTerm;
    mainlandSide = "from";
  }

  const fromName = _bestTerminalName(fromTerm);
  const toName = _bestTerminalName(toTerm);
  const fromLocal = _localTerminalName(fromTerm);
  const toLocal = _localTerminalName(toTerm);
  const fromLocalLabel = fromLocal
    ? `<span class="ferry-card__local-name" title="${escapeAttr(fromLocal.label)}"> · ${escapeHtml(fromLocal.value)}</span>`
    : "";
  const toLocalLabel = toLocal
    ? `<span class="ferry-card__local-name" title="${escapeAttr(toLocal.label)}"> · ${escapeHtml(toLocal.value)}</span>`
    : "";

  const typeLabel = _FERRY_TYPE_LABEL[route.type] || route.type || "—";
  const seasonLabel = _FERRY_SEASON_LABEL[route.seasonality] || route.seasonality || "—";
  const freqLabel = _FERRY_FREQ_LABEL[route.frequencyBand] || (route.frequencyBand ?? "—");
  const dur = _formatDuration(route.durationMinutes);

  const hasGtfs = (route.timetable?.source || "").startsWith("gtfs");
  const dayCounts = hasGtfs && Array.isArray(route.timetable?.weekly)
    ? route.timetable.weekly.map((w) => `${w.day}:${(w.outbound || []).length}`).join(" ")
    : null;

  const op_url = route.bookingUrl || (op ? op.timetablesUrl || op.homepage : null);
  const opLogo = op?.logoUrl
    ? `<img class="ferry-card__logo" src="${escapeAttr(op.logoUrl)}" alt="${escapeAttr(opLabel)} logo" loading="lazy">`
    : `<div class="ferry-card__logo ferry-card__logo--placeholder" aria-hidden="true">${escapeHtml(opLabel.slice(0, 2).toUpperCase())}</div>`;

  // Affiliate links - Trainline (train to mainland terminal) + Discover
  // Cars (car hire at mainland terminal). All marked rel="sponsored" per
  // GEO/SEO best practice; per-link (affiliate) micro-tag.
  const affiliate = mainlandTerm ? _renderAffiliateLinks(mainlandTerm, op) : "";

  // Drive-time bands from the major hub cities. We only render the
  // closest one + one mid-range so the card stays compact.
  const driveBands = mainlandTerm ? _renderDriveTimes(mainlandTerm) : "";

  // Last-verified age. Routes older than 180 days get a "stale - verify"
  // badge so we never claim outdated schedules are current.
  let verifiedBlock = "";
  if (route.lastVerified) {
    const stale = _routeIsStale(route.lastVerified, 180);
    verifiedBlock = stale
      ? `<span class="ferry-card__stale" title="Source last verified ${escapeAttr(route.lastVerified)} - re-verify with the operator">Stale (verified ${escapeHtml(route.lastVerified)})</span>`
      : `<span class="ferry-card__verified" title="Source last verified ${escapeAttr(route.lastVerified)}">Verified ${escapeHtml(route.lastVerified)}</span>`;
  }

  return `<article class="ferry-card" data-route-id="${escapeAttr(route.id)}">
    <div class="ferry-card__header">
      ${opLogo}
      <div class="ferry-card__title">
        <div class="ferry-card__op">${escapeHtml(opLabel)}</div>
        <div class="ferry-card__route">${escapeHtml(fromName)}${fromLocalLabel} <span aria-hidden="true">→</span> ${escapeHtml(toName)}${toLocalLabel}</div>
      </div>
    </div>
    <ul class="ferry-card__meta">
      <li><span>${escapeHtml(typeLabel)}</span></li>
      <li><span>${escapeHtml(seasonLabel)}</span></li>
      <li><span>${escapeHtml(freqLabel)}</span></li>
      <li><span>${dur}</span></li>
    </ul>
    ${route.timetable?.notes ? `<p class="ferry-card__notes">${escapeHtml(route.timetable.notes)}</p>` : ""}
    ${dayCounts ? `<p class="ferry-card__schedule" title="Departures per day per direction in this week's schedule">${escapeHtml(dayCounts)}</p>` : ""}
    ${driveBands}
    <div class="ferry-card__actions">
      ${op_url ? `<a class="ferry-card__book" href="${escapeAttr(op_url)}" target="_blank" rel="noopener">Book / timetable ↗</a>` : ""}
      ${affiliate}
    </div>
    <div class="ferry-card__foot">
      ${verifiedBlock}
      ${(route.sources || []).slice(0, 2).map((s) => s.url ? `<a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.type)} ↗</a>` : "").filter(Boolean).join("")}
    </div>
  </article>`;
}

// Render drive-time band from up to two hub cities (closest + one
// mid-range). Returns "" if no data has been computed yet.
function _renderDriveTimes(mainlandTerm) {
  const dt = mainlandTerm?.driveTimeMinutes;
  if (!dt) return "";
  const entries = Object.entries(dt).filter(([_, v]) => Number.isFinite(v));
  if (!entries.length) return "";
  entries.sort((a, b) => a[1] - b[1]);
  const pick = entries.slice(0, 2);
  const fmt = (min) => {
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    const m = min % 60;
    return m ? `${h}h ${m}m` : `${h}h`;
  };
  return `<p class="ferry-card__drive" title="Approximate driving time via OSRM">${
    pick.map(([city, mins]) => `<span class="ferry-card__drive-pill">${fmt(mins)} from ${escapeHtml(city)}</span>`).join("")
  }</p>`;
}

// Build affiliate links for the mainland terminal. We use generic, ToS-
// compliant deep-links: Trainline's `?stationFilter=` opens their UK
// timetable search prefilled with the port name; Discover Cars accepts a
// `pickupLocation=` parameter. These deep-links are public but the
// embedded `aid` value should be replaced with the site's affiliate ID
// when one is registered — for now they're plain links plus a sponsored
// rel attribute and a micro-disclosure tag, so we're never claiming a
// commission relationship that doesn't exist.
function _renderAffiliateLinks(mainlandTerm, op) {
  const stop = _bestTerminalName(mainlandTerm);
  const trainSearch = encodeURIComponent(stop + " station");
  const carSearch = encodeURIComponent(stop);
  const trainHref = `https://www.thetrainline.com/buytickets?searchTerm=${trainSearch}`;
  const carHref = `https://www.discovercars.com/?pickup_loc=${carSearch}`;
  // Optionally also link to the operator's own affiliate program if there
  // is one - rendered without a sponsored tag because it's the operator's
  // own page, but marked (affiliate) when op.affiliateProgram is set.
  const affiliateLabel = op?.affiliateProgram ? "(affiliate)" : "";
  return `
    <a class="ferry-card__affiliate" href="${escapeAttr(trainHref)}" target="_blank" rel="sponsored noopener">Train to ${escapeHtml(stop)} ↗ <span class="ferry-card__aff-tag" title="Trainline affiliate link">(affiliate)</span></a>
    <a class="ferry-card__affiliate" href="${escapeAttr(carHref)}" target="_blank" rel="sponsored noopener">Car hire at ${escapeHtml(stop)} ↗ <span class="ferry-card__aff-tag" title="Discover Cars affiliate link">(affiliate)</span></a>
    ${affiliateLabel ? `<span class="ferry-card__aff-meta">${escapeHtml(affiliateLabel)}</span>` : ""}
  `;
}

// Rebuild only the hero gallery section, avoiding a full renderDetails()
// re-flow (preserves scroll, the OS detail map, etc.).
function refreshGalleryInPlace(island) {
  const hero = document.getElementById("details-hero");
  if (!hero) return;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = renderGallery(island);
  const fresh = wrapper.firstElementChild;
  if (fresh) hero.replaceWith(fresh);
}

function renderDetails(island) {
  els.listSection.hidden = true;
  els.details.hidden = false;
  if (mobileNav.isActive()) {
    document.body.dataset.islandDetail = "open";
  }
  els.sidebar.scrollTop = 0;

  const typeLabel =
    island.type === "unknown"
      ? `Unverified <span style="color:var(--text-muted)">(needs review)</span>`
      : `${capitalize(island.type)} island`;

  const subtypeChips = island.subtype
    ? `<div class="subtype-chips" role="list" aria-label="Island subtype">
        <span class="subtype-chip" role="listitem">${escapeHtml(
          formatSubtypeLabel(island.subtype),
        )}</span>
      </div>`
    : "";

  const parentBody = island.parentWaterBody;
  const parentLabel = parentBody
    ? parentBody.name
      ? `${escapeHtml(parentBody.name)} <span style="color:var(--text-muted)">(${escapeHtml(parentBody.type)})</span>`
      : `<span style="color:var(--text-muted)">Unnamed ${escapeHtml(parentBody.type)}</span>`
    : island.type === "sea" || island.type === "unknown"
      ? null
      : "—";

  const stats = [
    { label: "Type", value: typeLabel },
    { label: "Nation", value: island.nation || "—" },
    { label: "Archipelago", value: island.archipelago || "—" },
    { label: "Area", value: formatAreaRow(island) },
    { label: "Population", value: formatPopulationCell(island) },
    {
      label: "Highest point",
      value: formatHighPointRow(island),
    },
  ];
  const bedrock = formatBedrockStat(island);
  if (bedrock) {
    stats.push({ label: "Bedrock", value: bedrock });
  }
  if (parentLabel) {
    stats.push({ label: "In water body", value: parentLabel });
  }
  if (island.heritageDesignation) {
    stats.push({
      label: "Heritage",
      value: `<span style="font-size:12px">${escapeHtml(island.heritageDesignation)}</span>`,
    });
  }
  if (island.classification && island.classification.source !== "manual") {
    const confRaw = island.classification.confidence;
    const confLabel =
      confRaw === "unconfirmed"
        ? "Not confirmed"
        : { high: "High", medium: "Medium", low: "Low" }[confRaw] || "—";
    let value = `<span style="font-size:12px">${escapeHtml(
      island.classification.source,
    )} · ${escapeHtml(confLabel)} confidence</span>`;
    if (confRaw === "unconfirmed") {
      value += `<br><span style="font-size:11px;color:var(--river)">Shown for exploration — not verified as a definitive island record.</span>`;
      if (island.classification.reviewHint) {
        value += `<br><span style="font-size:11px;color:var(--text-muted)">${escapeHtml(
          island.classification.reviewHint,
        )}</span>`;
      }
    }
    stats.push({
      label: "Classified by",
      value,
    });
  }

  const tags = (island.tags || [])
    .map((t) => `<span class="tag">${escapeHtml(t)}</span>`)
    .join("");

  const altNames = renderAltNames(island);
  const sourcesBlock = renderSourcesBlock(island);

  const richSections =
    section("History", island.history) +
    section("Geography", island.geography) +
    section("Transport", island.transport) +
    section("Accommodation", island.accommodation);

  const isOsmOnly = island.source === "osm" && !richSections;
  const osmHint = isOsmOnly
    ? `<div class="section">
         <h3>Crowd-sourced entry</h3>
         <p>This island was imported from OpenStreetMap. Detailed history,
            transport and accommodation notes haven't been written yet.
            ${
              island.osmType && island.osmId
                ? `<a href="https://www.openstreetmap.org/${island.osmType}/${island.osmId}" target="_blank" rel="noopener">View on OpenStreetMap ↗</a>`
                : ""
            }
         </p>
       </div>`
    : "";

  const gallery = renderGallery(island);
  const favActive = isFavoriteIsland(island.id);

  els.detailsContent.innerHTML = `
    ${gallery}
    <div class="details-title-row">
      <div class="details-title-block">
        <span class="layer-badge layer-badge--atlas" title="Verified atlas island">Atlas</span>
        <h2 class="details-title">${escapeHtml(island.name)}</h2>
      </div>
      <button type="button" id="details-favorite-btn" class="details-fav${
        favActive ? " is-favorite" : ""
      }" aria-pressed="${favActive ? "true" : "false"}" aria-label="${
        favActive ? "Remove from saved islands" : "Save island to list"
      }">${favActive ? "♥" : "♡"}</button>
    </div>
    ${subtypeChips}
    ${altNames}
    ${island.shortDescription ? `<p class="details-subtitle">${escapeHtml(island.shortDescription)}</p>` : ""}

    <div class="trip-priority-block">
    ${renderFerries(island)}
    ${renderPropertyListings(island)}
    </div>

    <div class="stat-grid">
      ${stats
        .map(
          (s) => `
        <div class="stat">
          <div class="stat__label">${escapeHtml(s.label)}</div>
          <div class="stat__value">${s.value}</div>
        </div>`,
        )
        .join("")}
    </div>

    ${renderMaritimeAidsSection(island)}
    ${renderReservesWildlifeSection(island)}

    ${tags ? `<div class="tags">${tags}</div>` : ""}

    ${richSections}
    ${osmHint}

    <div class="section detail-map-section">
      <h3>Detailed map</h3>
      <div class="detail-map__switcher-row">
        <div id="detail-map-switcher" class="detail-map__switcher" role="group" aria-label="Basemap"></div>
        <div id="detail-map-keycfg" class="detail-map__keycfg"></div>
      </div>
      <div id="detail-map" class="detail-map" aria-label="Detailed map of ${escapeAttr(island.name)}"></div>
      <p class="detail-map__hint" id="detail-map-hint"></p>
    </div>

    <div class="poly-loading" id="poly-status"></div>

    <div class="external-links">
      ${
        island.wikipedia
          ? `<a href="${escapeAttr(island.wikipedia)}" target="_blank" rel="noopener">Wikipedia ↗</a>`
          : `<a href="https://en.wikipedia.org/w/index.php?search=${encodeURIComponent(island.name)}" target="_blank" rel="noopener">Search Wikipedia ↗</a>`
      }
      <a href="https://www.google.com/search?q=${encodeURIComponent(
        island.name + " accommodation",
      )}" target="_blank" rel="noopener">Find accommodation ↗</a>
      <a href="https://www.google.com/maps?q=${island.lat},${island.lng}" target="_blank" rel="noopener">Google Maps ↗</a>
      ${
        island.osmType && island.osmId
          ? `<a href="https://www.openstreetmap.org/${island.osmType}/${island.osmId}" target="_blank" rel="noopener">OpenStreetMap ↗</a>`
          : ""
      }
      ${
        island.wikidata
          ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(island.wikidata)}" target="_blank" rel="noopener">Wikidata ↗</a>`
          : ""
      }
    </div>

    ${renderCorrectionReport(island)}

    ${sourcesBlock}
  `;

  document.getElementById("details-favorite-btn")?.addEventListener("click", (e) => {
    e.preventDefault();
    toggleFavoriteIsland(island.id);
  });

  renderDetailMap(island);
}

// Cached British National Grid CRS (EPSG:27700), built lazily via
// proj4leaflet. Returns null if proj4leaflet isn't available, in which case
// we silently fall back to Outdoor / OSM.
let _bngCrs = null;
function getBngCrs() {
  if (_bngCrs) return _bngCrs;
  if (typeof L === "undefined" || !L.Proj || !L.Proj.CRS) return null;
  // Resolutions (metres / pixel) and origin from the OS DataHub Leisure
  // tile grid spec; tile size is 256 px. This matches the documented
  // "Leisure_27700" layer.
  _bngCrs = new L.Proj.CRS(
    "EPSG:27700",
    "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 " +
      "+x_0=400000 +y_0=-100000 +ellps=airy " +
      "+towgs84=446.448,-125.157,542.06,0.15,0.247,0.842,-20.489 " +
      "+units=m +no_defs",
    {
      origin: [-238375.0, 1376256.0],
      resolutions: [896, 448, 224, 112, 56, 28, 14, 7, 3.5, 1.75],
      bounds: L.bounds([-238375.0, 0.0], [900000.0, 1376256.0]),
    },
  );
  return _bngCrs;
}

// Leisure tiles only cover Great Britain (England, Scotland, Wales).
// Northern Ireland, Ireland and the Crown Dependencies fall outside.
// We trust `island.nation` when set; otherwise apply a loose bounding box
// (avoids most of Ireland but isn't perfect — fine for a basemap heuristic).
function isInGreatBritainForLeisure(island) {
  const gbNations = new Set(["Scotland", "Wales", "England"]);
  if (island.nation && gbNations.has(island.nation)) return true;
  if (island.nation) return false;
  // Fallback bbox: roughly GB envelope, excluding the western Irish chunk.
  if (
    Number.isFinite(island.lat) &&
    Number.isFinite(island.lng) &&
    island.lat >= 49.5 &&
    island.lat <= 61 &&
    island.lng >= -8 &&
    island.lng <= 2 &&
    // crude NI/IE exclusion: west of -5.5 and south of 55.3 is mostly Ireland
    !(island.lng < -5.5 && island.lat < 55.3)
  ) {
    return true;
  }
  return false;
}

// Persist the user's basemap choice across island switches.
function getPreferredDetailBasemap() {
  try {
    return localStorage.getItem("detailBasemap") || null;
  } catch (_) {
    return null;
  }
}
function setPreferredDetailBasemap(b) {
  try {
    localStorage.setItem("detailBasemap", b);
  } catch (_) {
    /* ignore */
  }
}

// Initialise (or re-initialise) the in-panel detail map for `island`. The
// container is destroyed and rebuilt on every island / basemap switch so we
// don't leak Leaflet instances or accumulate event listeners.
function renderDetailMap(island) {
  const container = document.getElementById("detail-map");
  const hintEl = document.getElementById("detail-map-hint");
  const switcher = document.getElementById("detail-map-switcher");
  if (!container) return;

  if (state.detailMap) {
    try { state.detailMap.remove(); } catch (_) { /* ignore */ }
    state.detailMap = null;
  }

  if (!Number.isFinite(island.lat) || !Number.isFinite(island.lng)) {
    container.style.display = "none";
    if (switcher) switcher.innerHTML = "";
    if (hintEl) hintEl.textContent = "No coordinates available for this island.";
    return;
  }
  container.style.display = "";

  const key = getOsMapsKey();
  const inGB = isInGreatBritainForLeisure(island);
  const haveProj = !!getBngCrs();

  // Decide which basemaps are available for this island.
  const available = new Set(["osm"]);
  if (key) available.add("outdoor");
  if (key && inGB && haveProj) available.add("leisure");

  // Choose the default basemap.
  //   1. Honour the user's saved preference if it's still available.
  //   2. Else prefer Leisure (paper detail) when available.
  //   3. Else Outdoor when key but non-GB / no proj4.
  //   4. Else OSM.
  const pref = getPreferredDetailBasemap();
  let basemap = "osm";
  if (available.has("leisure")) basemap = "leisure";
  else if (available.has("outdoor")) basemap = "outdoor";
  if (pref && available.has(pref)) basemap = pref;

  if (switcher) renderDetailMapSwitcher(switcher, available, basemap, island);
  renderOsKeyControl(island);
  buildDetailMap(container, island, basemap, hintEl, key);
}

// Surface tile-load failures in the hint area. Leaflet's `tileerror` event
// fires for every failed tile; we collapse the storm into a single message
// per layer instance, then fetch one of the failing URLs to read the actual
// HTTP status (Leaflet hides it behind an opaque <img> error). The status
// tells the user what's actually wrong — almost always 401 (bad key) or
// 403 (project missing the OS Maps product / over quota).
function attachOsTileErrorHandler(layer, layerName, hintEl, key) {
  let reported = false;
  layer.on("tileerror", async (e) => {
    if (reported || !hintEl) return;
    reported = true;
    const url = (e.tile && e.tile.src) || "";
    let status = "?";
    let bodyHint = "";
    try {
      // CORS on api.os.uk is permissive for GET tile requests, so we can
      // fetch the same URL to read the status code.
      const res = await fetch(url, { method: "GET", mode: "cors" });
      status = String(res.status);
      try {
        const txt = await res.text();
        if (txt && txt.length < 400) bodyHint = txt.trim().slice(0, 200);
      } catch (_) { /* ignore body read failure */ }
    } catch (_) {
      status = "network/CORS";
    }
    const reason =
      status === "401"
        ? "Your API key is rejected. Re-check the value or regenerate it on osdatahub.os.uk."
        : status === "403"
          ? "OS rejected the request. Most common cause: your DataHub project doesn't have the <strong>OS Maps API</strong> product attached. Visit <a href=\"https://osdatahub.os.uk/projects\" target=\"_blank\" rel=\"noopener\">your projects ↗</a>, open the project, click <em>Add API product</em>, and pick <em>OS Maps API</em>. The same key will then start working."
          : status === "429"
            ? "Rate-limited. Free tier is 250k tiles/month — wait or rotate to a fresh key."
            : status === "404"
              ? "Layer <code>" + layerName + "</code> not found. Make sure your project has access to the OS Maps API."
              : "Tile request failed (status <code>" + status + "</code>). Switching to OSM may help.";
    hintEl.innerHTML =
      "<strong>OS tile error.</strong> " +
      reason +
      (bodyHint ? ' <span class="os-key__detail">Server said: <code>' + escapeHtml(bodyHint) + "</code></span>" : "");
  });
}

// ---------- OS Maps API key control ----------
// In-app affordance for pasting / clearing the user's OS DataHub key.
// Writes to localStorage.osMapsApiKey (per-browser, never committed).
// On save/clear we re-run setupMainOsMapsLayer() so the main-map dropdown
// stays in sync, then re-render the detail map.

function renderOsKeyControl(island) {
  const host = document.getElementById("detail-map-keycfg");
  if (!host) return;
  const hasKey = !!getOsMapsKey();
  const isStored = !!(() => {
    try { return localStorage.getItem("osMapsApiKey"); } catch (_) { return null; }
  })();
  const isWindowKey = hasKey && !isStored;

  host.innerHTML = `
    <button type="button" id="os-key-toggle" class="os-key__toggle"
            aria-expanded="false" aria-controls="os-key-form"
            title="Configure your free OS DataHub API key">
      <span class="os-key__icon" aria-hidden="true">⚙</span>
      <span class="os-key__label">${
        hasKey
          ? (isWindowKey
              ? "OS key (loaded from page)"
              : "OS key configured ✓")
          : "Add OS Maps API key"
      }</span>
    </button>
    <div id="os-key-form" class="os-key__form" hidden>
      <p class="os-key__intro">
        Paste your free <a href="https://osdatahub.os.uk/" target="_blank" rel="noopener">OS DataHub</a>
        <strong>OS Maps API</strong> key. It's stored in this browser only
        (<code>localStorage.osMapsApiKey</code>) — nothing is sent anywhere
        except OS's own tile servers.
      </p>
      <label class="os-key__field">
        <span class="os-key__label">API key</span>
        <input type="password" id="os-key-input"
               autocomplete="off" spellcheck="false"
               placeholder="paste key here"
               value="${escapeAttr(isStored || "")}" />
      </label>
      <div class="os-key__actions">
        <button type="button" id="os-key-save" class="os-key__save">Save</button>
        <button type="button" id="os-key-test" class="os-key__test"
                title="Send one test tile request to verify the key works">Test key</button>
        <button type="button" id="os-key-cancel" class="os-key__cancel">Cancel</button>
        ${isStored
          ? '<button type="button" id="os-key-clear" class="os-key__clear">Clear stored key</button>'
          : ""}
        <button type="button" id="os-key-show" class="os-key__show" aria-pressed="false"
                title="Show / hide the key">Show</button>
      </div>
      <p id="os-key-status" class="os-key__status" role="status"></p>
      ${isWindowKey
        ? '<p class="os-key__note">A key is currently provided by <code>window.OS_MAPS_API_KEY</code>. ' +
          'Pasting one here will not override it until you remove the page-level key.</p>'
        : ""}
    </div>
  `;

  const toggle = host.querySelector("#os-key-toggle");
  const form = host.querySelector("#os-key-form");
  const input = host.querySelector("#os-key-input");
  const showBtn = host.querySelector("#os-key-show");
  const status = host.querySelector("#os-key-status");

  toggle.addEventListener("click", () => {
    const open = !form.hidden ? true : false;
    form.hidden = open;
    toggle.setAttribute("aria-expanded", String(!open));
    if (!open && input) setTimeout(() => input.focus(), 0);
  });
  showBtn?.addEventListener("click", () => {
    const showing = showBtn.getAttribute("aria-pressed") === "true";
    showBtn.setAttribute("aria-pressed", String(!showing));
    showBtn.textContent = showing ? "Show" : "Hide";
    input.type = showing ? "password" : "text";
  });
  host.querySelector("#os-key-cancel")?.addEventListener("click", () => {
    form.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  });
  const saveBtn = host.querySelector("#os-key-save");
  saveBtn?.addEventListener("click", () => {
    const v = (input.value || "").trim();
    if (!v) {
      status.textContent = "Paste a key first, or use Clear to remove the stored one.";
      status.className = "os-key__status is-warn";
      return;
    }
    // Light validation: OS DataHub keys are typically 32-character
    // alphanumeric tokens. Don't be too strict (formats sometimes change).
    const looksLikeKey = /^[A-Za-z0-9_-]{16,128}$/.test(v);
    if (!looksLikeKey && saveBtn.dataset.confirm !== "1") {
      status.textContent =
        "That doesn't look like an OS DataHub key. Click Save again to confirm.";
      status.className = "os-key__status is-warn";
      saveBtn.dataset.confirm = "1";
      setTimeout(() => { delete saveBtn.dataset.confirm; }, 5000);
      return;
    }
    delete saveBtn.dataset.confirm;
    try {
      localStorage.setItem("osMapsApiKey", v);
    } catch (e) {
      status.textContent = "Couldn't save (private mode?): " + e.message;
      status.className = "os-key__status is-err";
      return;
    }
    status.textContent = "Saved. Refreshing map…";
    status.className = "os-key__status is-ok";
    setupMainOsMapsLayer();
    renderDetailMap(island);
  });
  host.querySelector("#os-key-test")?.addEventListener("click", async () => {
    const candidate = ((input.value || "").trim()) || getOsMapsKey();
    if (!candidate) {
      status.textContent = "Paste a key first, or save one, before testing.";
      status.className = "os-key__status is-warn";
      return;
    }
    status.textContent = "Testing… (sending one tile request to OS)";
    status.className = "os-key__status";
    // Tile (8/126/82) covers central Scotland — small payload, definitely
    // within the standard Outdoor pyramid. We don't render it; just check
    // the HTTP response.
    const url =
      "https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/8/126/82.png?key=" +
      encodeURIComponent(candidate);
    try {
      const res = await fetch(url, { method: "GET", mode: "cors" });
      const ct = res.headers.get("content-type") || "";
      let bodySnip = "";
      try {
        if (!ct.startsWith("image/")) {
          const t = await res.text();
          if (t && t.length < 400) bodySnip = t.trim().slice(0, 200);
        }
      } catch (_) { /* ignore */ }
      if (res.ok && ct.startsWith("image/")) {
        status.innerHTML =
          "Success — OS returned a tile (HTTP " + res.status +
          ", " + ct + "). Your key works.";
        status.className = "os-key__status is-ok";
      } else if (res.status === 401) {
        status.innerHTML =
          "HTTP 401 — key rejected. Double-check the value (no stray spaces) or regenerate it.";
        status.className = "os-key__status is-err";
      } else if (res.status === 403) {
        status.innerHTML =
          "HTTP 403 — auth ok but <strong>OS Maps API isn't attached to your project</strong>. " +
          'Open <a href="https://osdatahub.os.uk/projects" target="_blank" rel="noopener">your DataHub projects ↗</a>, ' +
          "click your project, choose <em>Add API product</em>, and select <strong>OS Maps API</strong>. " +
          "The same key then starts working." +
          (bodySnip ? "<br><span class=\"os-key__detail\">Server said: <code>" + escapeHtml(bodySnip) + "</code></span>" : "");
        status.className = "os-key__status is-err";
      } else if (res.status === 429) {
        status.innerHTML = "HTTP 429 — rate-limited. Wait a minute and retry.";
        status.className = "os-key__status is-warn";
      } else {
        status.innerHTML =
          "HTTP " + res.status + " — unexpected. " +
          (bodySnip ? "<span class=\"os-key__detail\">Server said: <code>" + escapeHtml(bodySnip) + "</code></span>" : "");
        status.className = "os-key__status is-err";
      }
    } catch (e) {
      status.textContent = "Network error during probe: " + e.message;
      status.className = "os-key__status is-err";
    }
  });

  host.querySelector("#os-key-clear")?.addEventListener("click", () => {
    try {
      localStorage.removeItem("osMapsApiKey");
    } catch (_) { /* ignore */ }
    setupMainOsMapsLayer();
    // If the main map is currently on the OS layer, fall back to OSM
    // so we don't leave a now-broken tile layer.
    if (els.basemap.value === "osMaps") {
      els.basemap.value = "osm";
      els.basemap.dispatchEvent(new Event("change"));
    }
    renderDetailMap(island);
  });
}

// Render the small basemap selector above the detail map.
function renderDetailMapSwitcher(switcher, available, current, island) {
  switcher.innerHTML = "";
  const labels = {
    leisure: ["OS Leisure", "1:25k paper-map detail (GB only)"],
    outdoor: ["OS Outdoor", "Web Mercator OS tiles"],
    osm: ["OSM", "OpenStreetMap fallback"],
  };
  // Always render all three buttons; disable any that aren't available so
  // the user sees what would unlock with a key / proj4.
  for (const key of ["leisure", "outdoor", "osm"]) {
    const [label, title] = labels[key];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "detail-map__basemap";
    btn.textContent = label;
    btn.title = title;
    btn.dataset.basemap = key;
    if (current === key) btn.classList.add("is-active");
    if (!available.has(key)) {
      btn.disabled = true;
      btn.classList.add("is-disabled");
    }
    btn.addEventListener("click", () => {
      if (btn.disabled || btn.classList.contains("is-active")) return;
      setPreferredDetailBasemap(key);
      renderDetailMap(island);
    });
    switcher.appendChild(btn);
  }
}

// Build the Leaflet map for the chosen basemap. Separated from
// renderDetailMap so we can fully rebuild on basemap switch.
function buildDetailMap(container, island, basemap, hintEl, key) {
  const baseZoom = (() => {
    const a = island.areaKm2 || 0;
    if (island.type === "river") return 15;
    if (a < 0.5) return 14;
    if (a < 5) return 13;
    if (a < 50) return 12;
    return 11;
  })();

  const mapOpts = {
    center: [island.lat, island.lng],
    zoom: baseZoom,
    zoomControl: true,
    attributionControl: true,
  };

  if (basemap === "leisure") {
    const crs = getBngCrs();
    mapOpts.crs = crs;
    // Leisure tile pyramid is z=0..9; cap accordingly so Leaflet doesn't
    // try to fetch beyond what OS publishes.
    mapOpts.minZoom = 5;
    mapOpts.maxZoom = 9;
    // Leisure's "natural" zoom for an individual island sits at 7–9;
    // remap the size-based heuristic to that band.
    const a = island.areaKm2 || 0;
    mapOpts.zoom = island.type === "river" ? 9 : a < 0.5 ? 9 : a < 5 ? 8 : a < 50 ? 7 : 6;
  } else if (basemap === "outdoor") {
    mapOpts.minZoom = 7;
    mapOpts.maxZoom = 16;
  } else {
    mapOpts.minZoom = 7;
    mapOpts.maxZoom = 19;
  }

  const m = L.map(container, mapOpts);
  state.detailMap = m;

  if (basemap === "leisure") {
    const layer = L.tileLayer(
      `https://api.os.uk/maps/raster/v1/zxy/Leisure_27700/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`,
      {
        attribution:
          'Contains OS data © Crown copyright & database right ' +
          new Date().getFullYear() +
          ' — OS Leisure 1:25k/1:50k',
        tileSize: 256,
      },
    ).addTo(m);
    attachOsTileErrorHandler(layer, "Leisure_27700", hintEl, key);
    if (hintEl) {
      hintEl.innerHTML =
        'Showing <strong>OS Leisure</strong> (EPSG:27700, paper-map detail). ' +
        'Pan and zoom to explore footpaths, contours and named features. ' +
        '<a href="docs/OS-MAPS.md" target="_blank" rel="noopener">About OS Maps integration ↗</a>';
    }
  } else if (basemap === "outdoor") {
    const layer = L.tileLayer(
      `https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}`,
      {
        maxZoom: 16,
        attribution:
          'Contains OS data © Crown copyright & database right ' +
          new Date().getFullYear(),
      },
    ).addTo(m);
    attachOsTileErrorHandler(layer, "Outdoor_3857", hintEl, key);
    if (hintEl) {
      hintEl.innerHTML =
        'Showing <strong>OS Outdoor</strong> (EPSG:3857). ' +
        'Use the toggle above for the paper-style Leisure layer (GB only). ' +
        '<a href="docs/OS-MAPS.md" target="_blank" rel="noopener">About OS Maps integration ↗</a>';
    }
  } else {
    L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
    ).addTo(m);
    if (hintEl) {
      const reason = !key
        ? 'No Ordnance Survey API key configured. Set <code>localStorage.osMapsApiKey</code> ' +
          'or define <code>window.OS_MAPS_API_KEY</code> to unlock OS tiles. '
        : !isInGreatBritainForLeisure(island)
          ? 'Leisure tiles cover Great Britain only; Outdoor and OSM remain available. '
          : !getBngCrs()
            ? 'proj4leaflet failed to load, so Leisure (EPSG:27700) is unavailable. '
            : '';
      hintEl.innerHTML =
        reason +
        'Showing OpenStreetMap. ' +
        '<a href="docs/OS-MAPS.md" target="_blank" rel="noopener">About OS Maps integration ↗</a>';
    }
  }

  // Marker so the user can pinpoint the island on busy basemaps.
  L.circleMarker([island.lat, island.lng], {
    radius: 6,
    color: "#0ea5e9",
    weight: 2,
    fillColor: "#38bdf8",
    fillOpacity: 0.85,
  }).addTo(m);

  // Draw ferry routes once ferry data is available. We don't await
  // anything here - loadFerries already returns synchronously once cached.
  drawFerryRoutesOnDetailMap(m, island, basemap);

  // Leaflet mis-sizes when the container was hidden during initialisation.
  setTimeout(() => {
    try { m.invalidateSize(); } catch (_) { /* ignore */ }
  }, 60);
}

// Draw dashed polylines from this island to each connected mainland
// terminal, plus a small marker at each terminal. OSM ferry-route
// geometries are approximate, so we keep the line dashed with an
// "indicative" tooltip.
function drawFerryRoutesOnDetailMap(m, island, basemap) {
  const apply = () => {
    if (!state.ferryRoutesByIsland) return;
    const routes = findFerriesForIsland(island.id);
    if (!routes.length) return;
    // Leisure basemap uses EPSG:27700 CRS — we can still draw lat/lng
    // polylines because Leaflet will project them via the CRS.
    for (const r of routes) {
      const from = r._fromTerminal;
      const to = r._toTerminal;
      if (!from || !to) continue;
      try {
        const a = [Number(from.lat), Number(from.lon)];
        const b = [Number(to.lat), Number(to.lon)];
        if (!a.every(Number.isFinite) || !b.every(Number.isFinite)) continue;
        const opLabel = r._operator?.shortName || r._operator?.name || r.operatorId || "ferry";
        const line = L.polyline([a, b], {
          color: "#4ea3ff",
          weight: 2.5,
          opacity: 0.8,
          dashArray: "5,6",
        }).addTo(m);
        line.bindTooltip(
          `${escapeHtml(opLabel)}: ${escapeHtml(_bestTerminalName(from))} → ${escapeHtml(_bestTerminalName(to))} (indicative route)`,
          { sticky: true },
        );
        // Terminal markers (other endpoint only; the island already has
        // its own pin).
        const otherTerm = r._fromIsland === island.id ? to : from;
        if (otherTerm) {
          L.circleMarker([Number(otherTerm.lat), Number(otherTerm.lon)], {
            radius: 5,
            color: "#fff",
            weight: 1.5,
            fillColor: "#4ea3ff",
            fillOpacity: 0.95,
          })
            .addTo(m)
            .bindTooltip(`${escapeHtml(_bestTerminalName(otherTerm))} terminal (${escapeHtml(opLabel)})`);
        }
      } catch (_) {
        /* ignore one bad route */
      }
    }
  };
  if (state.ferries) {
    apply();
  } else {
    loadFerries().then(() => {
      if (state.detailMap === m) apply();
    });
  }
}

const LANG_LABELS = {
  ga: "Gaeilge",
  gd: "Gàidhlig",
  cy: "Cymraeg",
  gv: "Gaelg",
  kw: "Kernewek",
  sco: "Scots",
  fr: "Français",
  nrf: "Nourmaund",
  en: "English",
};

function renderAltNames(island) {
  const names = island.names || {};
  const entries = Object.entries(names)
    .filter(([lang, val]) => val && val.trim() && val.trim() !== island.name && lang !== "en")
    .map(
      ([lang, val]) =>
        `<span class="alt-name"><span class="alt-name__lang">${escapeHtml(
          LANG_LABELS[lang] || lang,
        )}:</span> <span class="alt-name__val">${escapeHtml(val)}</span></span>`,
    );
  if (!entries.length) return "";
  return `<div class="alt-names">${entries.join("")}</div>`;
}

function renderSourcesBlock(island) {
  const sources = Array.isArray(island.sources) ? island.sources : [];
  if (!sources.length) return "";
  const rows = sources
    .map((s) => {
      const name = escapeHtml(s.name || "Source");
      const licence = s.licence ? ` <span class="src-lic">${escapeHtml(s.licence)}</span>` : "";
      const ref =
        s.url
          ? ` <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">${escapeHtml(
              s.ref || s.url,
            )}</a>`
          : s.ref
            ? ` <span class="src-ref">${escapeHtml(s.ref)}</span>`
            : "";
      const attrib = s.attribution
        ? `<div class="src-attrib">${escapeHtml(s.attribution)}</div>`
        : "";
      return `<li class="src"><div class="src-line">${name}${ref}${licence}</div>${attrib}</li>`;
    })
    .join("");
  return `<div class="section sources-section">
    <h3>Sources & attribution</h3>
    <ul class="sources-list">${rows}</ul>
  </div>`;
}

function section(title, body) {
  if (!body) return "";
  return `
    <div class="section">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body)}</p>
    </div>
  `;
}

/** Normalise Commons / Wikimedia URLs to a stable dedup key (same photo, many URL forms). */
function normalizeCommonsFileName(name) {
  let n = decodeURIComponent(String(name || "")).replace(/\.[a-z0-9]+$/i, "");
  n = n.replace(/_/g, " ");
  n = n.replace(/\s*,\s*\d{4}[-–]\d{2}[-–]\d{2}.*$/i, "");
  n = n.replace(/\s*\(geograph[^)]*\)\s*/gi, "");
  return n.trim().toLowerCase().replace(/\s+/g, "_");
}

function imageDedupKey(img) {
  if (!img) return "";
  if (img.fileName) return normalizeCommonsFileName(img.fileName);
  const u = img.url || img.fullUrl || "";
  if (!u) return "";
  const decoded = decodeURIComponent(u);
  let m = decoded.match(/(?:FilePath\/|\/wiki\/(?:File|Image):)([^?#]+)/i);
  if (m) return normalizeCommonsFileName(m[1]);
  m = decoded.match(/\/commons\/(?:thumb\/)?[a-f0-9]\/[a-f0-9]{2}\/([^/?#]+)/i);
  if (m) return normalizeCommonsFileName(m[1]);
  m = decoded.match(/\/([^/?#]+\.(?:jpe?g|png|gif|webp|svg))(?:\?|$)/i);
  if (m) return normalizeCommonsFileName(m[1]);
  return u.split("?")[0].toLowerCase();
}

function dedupeImagesByKey(images) {
  const seen = new Set();
  const out = [];
  for (const img of images) {
    const key = imageDedupKey(img);
    if (key && seen.has(key)) continue;
    if (key) seen.add(key);
    out.push(img);
  }
  return out;
}

// Merge the lead image(s) from islands.json with the lazily-loaded
// extras from data/galleries.json. Lead image(s) always come first;
// extras are appended in script order. Mutates `island.images` once the
// merge has been applied so subsequent renders don't redo the work.
function ensureGalleryMerged(island) {
  if (!state.galleries) return; // not loaded yet — skip; will be re-rendered
  if (island.__galleryMerged) {
    if (Array.isArray(island.images) && island.images.length > 1) {
      island.images = dedupeImagesByKey(island.images);
    }
    return;
  }
  const extras = state.galleries[island.id];
  if (Array.isArray(extras) && extras.length) {
    const lead = Array.isArray(island.images) ? island.images : [];
    const have = new Set(lead.map((x) => imageDedupKey(x)));
    const merged = lead.slice();
    for (const ex of extras) {
      const key = imageDedupKey(ex);
      if (key && have.has(key)) continue;
      merged.push({ ...ex, primary: false });
      if (key) have.add(key);
    }
    island.images = dedupeImagesByKey(merged);
  } else if (Array.isArray(island.images) && island.images.length > 1) {
    island.images = dedupeImagesByKey(island.images);
  }
  island.__galleryMerged = true;
  // #region agent log
  if (island.id?.includes("aigas")) {
    const imgs = Array.isArray(island.images) ? island.images : [];
    const keys = imgs.map((x, i) => ({ i, key: imageDedupKey(x), url: (x.url || "").slice(0, 80) }));
    fetch("http://127.0.0.1:7720/ingest/def19690-94b9-4670-be7c-26220155de0a", { method: "POST", headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5f60f5" }, body: JSON.stringify({ sessionId: "5f60f5", runId: "post-fix", hypothesisId: "H1", location: "app.js:ensureGalleryMerged", message: "gallery merged", data: { id: island.id, count: imgs.length, keys }, timestamp: Date.now() }) }).catch(() => {});
  }
  // #endregion
}

function renderGallery(island) {
  ensureGalleryMerged(island);
  // Resolve the canonical image list. `images[]` is the new schema; fall
  // back to the legacy `image` field for any entry that hasn't been
  // through the enrichment pipeline yet.
  const images =
    Array.isArray(island.images) && island.images.length
      ? island.images
      : island.image
        ? [{ url: island.image, fullUrl: island.image, source: "legacy", primary: true }]
        : [];

  if (!images.length) return "";

  const primaryIdx = Math.max(
    0,
    images.findIndex((i) => i.primary),
  );
  const primary = images[primaryIdx];
  const heroHtml = renderHeroImg(primary, island.name);
  const attribution = renderAttribution(primary);

  // #region agent log
  if (island.id?.includes("aigas")) {
    const dupPairs = [];
    for (let a = 0; a < images.length; a++) {
      for (let b = a + 1; b < images.length; b++) {
        if (images[a].url === images[b].url) dupPairs.push([a, b, "same-url"]);
      }
    }
    const thumbOnly = images.length - 1;
    fetch("http://127.0.0.1:7720/ingest/def19690-94b9-4670-be7c-26220155de0a", { method: "POST", headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5f60f5" }, body: JSON.stringify({ sessionId: "5f60f5", runId: "post-fix", hypothesisId: "H2", location: "app.js:renderGallery", message: "thumb strip", data: { id: island.id, imageCount: images.length, primaryIdx, thumbOnly, dupPairs, urls: images.map((x, i) => ({ i, u: (x.url || "").slice(0, 70) })) }, timestamp: Date.now() }) }).catch(() => {});
  }
  // #endregion

  const thumbIndices = images.map((_, idx) => idx).filter((idx) => idx !== primaryIdx);
  const thumbStrip =
    thumbIndices.length > 0
      ? `<div class="thumb-strip" role="tablist" aria-label="Island images">${thumbIndices
          .map(
            (idx) => `
              <button class="thumb" data-img-idx="${idx}" role="tab" aria-selected="false" aria-label="Image ${idx + 1}">
                <img src="${escapeAttr(images[idx].url)}" alt="" loading="lazy" onerror="this.style.opacity='0.25'"/>
              </button>`,
          )
          .join("")}</div>`
      : "";

  return `
    <div class="details-hero" id="details-hero" data-island-id="${escapeAttr(
      island.id,
    )}" data-active-idx="${primaryIdx}">
      ${heroHtml}
      ${attribution}
      ${thumbStrip}
    </div>
  `;
}

function renderHeroImg(img, fallbackAlt) {
  const src = img.fullUrl || img.url || "";
  const caption = (img.caption || fallbackAlt || "").trim();
  return `<img class="hero-img" src="${escapeAttr(src)}" alt="${escapeAttr(
    caption || fallbackAlt,
  )}" loading="lazy" onerror="window.__heroFallback && window.__heroFallback(this)"/>`;
}

// Hero load-failure fallback: try the next image in the gallery. Hide the
// hero only if every image in the gallery fails.
window.__heroFallback = function (heroImgEl) {
  const hero = heroImgEl.closest(".details-hero");
  if (!hero) {
    heroImgEl.style.display = "none";
    return;
  }
  const id = hero.dataset.islandId;
  const island = state.byId.get(id);
  if (!island || !Array.isArray(island.images)) {
    hero.classList.add("hero-failed");
    return;
  }
  const triedRaw = hero.dataset.tried || "";
  const tried = new Set(triedRaw.split(",").filter(Boolean));
  const currentIdx = Number(hero.dataset.activeIdx);
  tried.add(String(currentIdx));
  // Find the next un-tried image
  const nextIdx = island.images.findIndex(
    (_, i) => !tried.has(String(i)),
  );
  if (nextIdx === -1) {
    hero.classList.add("hero-failed");
    return;
  }
  hero.dataset.tried = [...tried].join(",");
  hero.dataset.activeIdx = String(nextIdx);
  const next = island.images[nextIdx];
  heroImgEl.src = next.fullUrl || next.url;
  heroImgEl.alt = next.caption || island.name;
  const attrib = hero.querySelector(".hero-attrib");
  if (attrib) attrib.outerHTML = renderAttribution(next);
  hero.querySelectorAll(".thumb").forEach((b) => {
    const isActive = Number(b.dataset.imgIdx) === nextIdx;
    b.classList.toggle("is-active", isActive);
    b.setAttribute("aria-selected", isActive ? "true" : "false");
  });
};

function renderAttribution(img) {
  if (!img || img.source === "legacy") return "";
  const sourceLabel =
    img.source === "wikidata"
      ? "Wikidata"
      : img.source === "pageimage"
        ? "Wikipedia"
        : img.source === "curated"
          ? "Wikimedia Commons"
          : img.source || "";
  const parts = [];
  if (img.attribution) parts.push(`Photo: ${escapeHtml(img.attribution)}`);
  if (img.license) parts.push(escapeHtml(img.license));
  parts.push(
    img.sourcePageUrl
      ? `<a href="${escapeAttr(img.sourcePageUrl)}" target="_blank" rel="noopener">${escapeHtml(
          sourceLabel,
        )} ↗</a>`
      : escapeHtml(sourceLabel),
  );
  return `<div class="hero-attrib">${parts.join(" · ")}</div>`;
}

// Delegate thumbnail clicks for the dynamically-rendered gallery
els.detailsContent.addEventListener("click", (e) => {
  const btn = e.target.closest(".thumb");
  if (!btn) return;
  const hero = btn.closest(".details-hero");
  if (!hero) return;
  const idx = Number(btn.dataset.imgIdx);
  const id = hero.dataset.islandId;
  const island = state.byId.get(id);
  if (!island || !Array.isArray(island.images) || !island.images[idx]) return;
  const target = island.images[idx];
  hero.dataset.activeIdx = String(idx);
  const heroImg = hero.querySelector(".hero-img");
  if (heroImg) {
    heroImg.src = target.fullUrl || target.url;
    heroImg.alt = target.caption || island.name;
  }
  const attrib = hero.querySelector(".hero-attrib");
  if (attrib) {
    attrib.outerHTML = renderAttribution(target);
  }
  hero.querySelectorAll(".thumb").forEach((b) => {
    b.classList.toggle("is-active", b === btn);
    b.setAttribute("aria-selected", b === btn ? "true" : "false");
  });
});

els.back.addEventListener("click", () => {
  releaseIslandDetailView({ clearUrl: true });
  if (mobileNav.isActive()) mobileNav.setView("islands");
  scheduleRenderListWindow();
});

function releaseIslandDetailView({ clearUrl = false } = {}) {
  resetIslandSeo();
  state.mobileDetailSuspended = false;
  hideMapIslandPeek();
  els.details.hidden = true;
  els.listSection.hidden = false;
  if (mobileNav.isActive()) {
    document.body.dataset.islandDetail = "closed";
  }
  state.activeId = null;
  if (state.activePolygon) {
    map.removeLayer(state.activePolygon);
    state.activePolygon = null;
  }
  if (state.detailMap) {
    try { state.detailMap.remove(); } catch (_) { /* ignore */ }
    state.detailMap = null;
  }
  if (clearUrl) syncIslandUrl(null);
}

function resetAtlasHome() {
  releaseIslandDetailView({ clearUrl: true });
  els.search.value = "";
  els.typeFilter.value = "";
  els.nationFilter.value = "";
  if (els.favoritesFilter) els.favoritesFilter.value = "";
  if (els.filterPhoto) els.filterPhoto.checked = false;
  if (els.filterFerry) els.filterFerry.checked = false;
  if (els.filterForSale) els.filterForSale.checked = false;
  if (els.filterElevation) els.filterElevation.checked = false;
  if (els.areaMinFilter) els.areaMinFilter.value = "";
  if (els.subtypeFilter) els.subtypeFilter.value = "";
  if (els.confidenceFilter) els.confidenceFilter.value = "";
  applyFilters();
  document.body.classList.remove("filters-open");
  document.getElementById("filters-toggle")?.setAttribute("aria-expanded", "false");
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("trip");
    url.searchParams.delete("ask");
    url.searchParams.delete("explore");
    url.searchParams.delete("island");
    clearExploreTopic();
    window.history.replaceState(null, "", url.toString());
  } catch (_) {
    /* non-fatal */
  }
  if (typeof chatClose === "function") {
    chatClose();
  }
  if (mobileNav.isActive()) {
    mobileNav.setView("map", { skipChatSync: true });
  }
}

// ---------- Polygon overlay (lazy) ----------
async function loadAndShowPolygon(island) {
  if (state.activePolygon) {
    map.removeLayer(state.activePolygon);
    state.activePolygon = null;
  }

  if (!island.osmType || !island.osmId || island.osmType === "node") {
    setPolyStatus("Outline not available for this entry.");
    return;
  }

  const cached = state.polygonCache.get(island.id);
  if (cached) {
    state.activePolygon = cached.addTo(map);
    fitToPolygon(cached);
    setPolyStatus("");
    return;
  }

  setPolyStatus("Fetching island outline from OpenStreetMap…");

  try {
    const geojson = await fetchOsmPolygon(island.osmType, island.osmId);
    if (!geojson) {
      setPolyStatus("No outline geometry returned from OSM.");
      return;
    }
    const layer = L.geoJSON(geojson, {
      style: {
        color: "#4ea3ff",
        weight: 2,
        fillColor: "#4ea3ff",
        fillOpacity: 0.18,
      },
    });
    state.polygonCache.set(island.id, layer);
    state.activePolygon = layer.addTo(map);
    fitToPolygon(layer);
    setPolyStatus("");
  } catch (err) {
    console.warn("polygon fetch failed", err);
    setPolyStatus(`Couldn't load outline (${err.message}).`);
  }
}

function fitToPolygon(layer) {
  try {
    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14, animate: true });
    }
  } catch {
    /* noop */
  }
}

function setPolyStatus(msg) {
  const el = document.getElementById("poly-status");
  if (el) el.textContent = msg;
}

async function fetchOsmPolygon(osmType, osmId) {
  const q = `[out:json][timeout:25];${osmType}(${osmId});out geom;`;
  let lastErr;
  for (const endpoint of OVERPASS_ENDPOINTS) {
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: "data=" + encodeURIComponent(q),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      return overpassToGeoJSON(json);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("All Overpass mirrors failed");
}

function overpassToGeoJSON(payload) {
  const features = [];
  for (const el of payload.elements || []) {
    if (el.type === "way" && Array.isArray(el.geometry)) {
      const coords = el.geometry.map((p) => [p.lon, p.lat]);
      // Close the ring if needed
      if (
        coords.length > 2 &&
        (coords[0][0] !== coords[coords.length - 1][0] ||
          coords[0][1] !== coords[coords.length - 1][1])
      ) {
        coords.push(coords[0]);
      }
      features.push({
        type: "Feature",
        properties: { id: el.id },
        geometry: { type: "Polygon", coordinates: [coords] },
      });
    } else if (el.type === "relation" && Array.isArray(el.members)) {
      const outers = [];
      const inners = [];
      for (const m of el.members) {
        if (m.type !== "way" || !Array.isArray(m.geometry)) continue;
        const ring = m.geometry.map((p) => [p.lon, p.lat]);
        if (m.role === "inner") inners.push(ring);
        else outers.push(ring);
      }
      // Stitch each outer way into a closed polygon (simplified — doesn't
      // perfectly assemble multi-segment outers, but works for the vast
      // majority of single-way island relations).
      for (const outer of outers) {
        if (outer.length < 4) continue;
        if (
          outer[0][0] !== outer[outer.length - 1][0] ||
          outer[0][1] !== outer[outer.length - 1][1]
        ) {
          outer.push(outer[0]);
        }
        features.push({
          type: "Feature",
          properties: { id: el.id, role: "outer" },
          geometry: { type: "Polygon", coordinates: [outer, ...inners] },
        });
      }
    }
  }
  if (!features.length) return null;
  return { type: "FeatureCollection", features };
}

// ---------- Enrichment detail renderers (P0b) ----------
const HILL_CLASS_SLUG = {
  Munro: "munro",
  Furth: "furth",
  Corbett: "corbett",
  Graham: "graham",
  Donald: "donald",
  Murdo: "murdo",
  Marilyn: "marilyn",
  HuMP: "hump",
  Hewitt: "hewitt",
  Nuttall: "nuttall",
  Wainwright: "wainwright",
  Birkett: "birkett",
};

const WILDLIFE_SPECIES_LABELS = {
  gannet: "Northern gannet",
  puffin: "Atlantic puffin",
  kittiwake: "Black-legged kittiwake",
  guillemot: "Common guillemot",
  razorbill: "Razorbill",
  fulmar: "Northern fulmar",
  "manx-shearwater": "Manx shearwater",
  "storm-petrel": "European storm petrel",
  "leachs-petrel": "Leach's storm petrel",
  "arctic-tern": "Arctic tern",
  "common-tern": "Common tern",
  "roseate-tern": "Roseate tern",
  "sandwich-tern": "Sandwich tern",
  "little-tern": "Little tern",
  eider: "Common eider",
  shag: "European shag",
  cormorant: "Great cormorant",
  "great-skua": "Great skua",
  "arctic-skua": "Arctic skua",
  "herring-gull": "Herring gull",
  "black-headed-gull": "Black-headed gull",
  "lesser-black-backed-gull": "Lesser black-backed gull",
  "great-black-backed-gull": "Great black-backed gull",
  "black-guillemot": "Black guillemot",
  "red-throated-diver": "Red-throated diver",
  "black-throated-diver": "Black-throated diver",
  "great-northern-diver": "Great northern diver",
  "white-tailed-eagle": "White-tailed eagle",
  "golden-eagle": "Golden eagle",
  peregrine: "Peregrine falcon",
  "hen-harrier": "Hen harrier",
  merlin: "Merlin",
  "short-eared-owl": "Short-eared owl",
  corncrake: "Corncrake",
  chough: "Red-billed chough",
  "grey-seal": "Grey seal",
  "common-seal": "Common seal",
  "harbour-porpoise": "Harbour porpoise",
  "common-dolphin": "Short-beaked common dolphin",
  "bottlenose-dolphin": "Bottlenose dolphin",
  "minke-whale": "Minke whale",
  "basking-shark": "Basking shark",
  otter: "Eurasian otter",
};

function formatSpeciesLabel(speciesId) {
  if (!speciesId) return "";
  return (
    WILDLIFE_SPECIES_LABELS[speciesId] ||
    speciesId
      .split("-")
      .map((w) => capitalize(w))
      .join(" ")
  );
}

function enrichmentAttribution(text) {
  if (!text) return "";
  return `<p class="enrichment-attribution">${escapeHtml(text)}</p>`;
}

function formatPopulationCell(island) {
  let html = formatPopulation(island.population);
  if (island.populationYear) {
    html += ` <span class="stat-meta">· census ${escapeHtml(String(island.populationYear))}</span>`;
  }
  if (island.populationConfidence && island.populationConfidence !== "n/a") {
    const conf =
      { high: "official island figure", medium: "aggregated estimate", low: "indicative" }[
        island.populationConfidence
      ] || island.populationConfidence;
    html += ` <span class="stat-meta">· ${escapeHtml(conf)}</span>`;
  }
  const pd = island.populationDetails;
  if (!pd || typeof pd !== "object") return html;

  const rows = [];
  if (pd.households != null) {
    rows.push(
      `<dt>Households</dt><dd>${escapeHtml(new Intl.NumberFormat("en-GB").format(pd.households))}</dd>`,
    );
  }
  const ages = pd.ageStructure;
  if (ages && typeof ages === "object") {
    if (ages.under16 != null) {
      rows.push(`<dt>Under 16</dt><dd>${escapeHtml(String(ages.under16))}</dd>`);
    }
    if (ages["16to64"] != null) {
      rows.push(`<dt>Aged 16–64</dt><dd>${escapeHtml(String(ages["16to64"]))}</dd>`);
    }
    if (ages["65plus"] != null) {
      rows.push(`<dt>65 and over</dt><dd>${escapeHtml(String(ages["65plus"]))}</dd>`);
    }
  }
  if (pd.gaelicSpeakers != null) {
    rows.push(`<dt>Gaelic speakers</dt><dd>${escapeHtml(String(pd.gaelicSpeakers))}</dd>`);
  }
  if (pd.welshSpeakers != null) {
    rows.push(`<dt>Welsh speakers</dt><dd>${escapeHtml(String(pd.welshSpeakers))}</dd>`);
  }
  if (pd.irishSpeakers != null) {
    rows.push(`<dt>Irish speakers</dt><dd>${escapeHtml(String(pd.irishSpeakers))}</dd>`);
  }
  if (!rows.length) return html;

  html += `<details class="population-detail"><summary>Census breakdown</summary><dl class="population-detail__grid">${rows.join("")}</dl></details>`;
  if (island.populationAttribution) {
    html += enrichmentAttribution(island.populationAttribution);
  }
  return html;
}

function formatBedrockStat(island) {
  const bed = island.geology?.bedrock;
  if (!bed?.name) return "";
  const parts = [escapeHtml(bed.name)];
  if (bed.lithology) parts.push(`<span class="stat-meta">${escapeHtml(bed.lithology)}</span>`);
  if (bed.ageStart) {
    const age =
      bed.ageStart === bed.ageEnd || !bed.ageEnd
        ? bed.ageStart
        : `${bed.ageStart} – ${bed.ageEnd}`;
    parts.push(`<span class="stat-meta">${escapeHtml(age)}</span>`);
  }
  let html = parts.join(" ");
  if (island.geology?.attribution) {
    html += enrichmentAttribution(island.geology.attribution);
  }
  return html;
}

function renderHillsOnBlock(island) {
  const hills = island.hillsOn;
  if (!Array.isArray(hills) || !hills.length) return "";
  const cap = 6;
  const shown = hills.slice(0, cap);
  const extra = hills.length - shown.length;
  const items = shown
    .map((h) => {
      const topClass = (h.classifications || [])[0] || "";
      const slug = HILL_CLASS_SLUG[topClass] || "other";
      const cls = topClass
        ? `<span class="hill-class hill-class-${slug}">${escapeHtml(topClass)}</span>`
        : "";
      const ele =
        h.elevationM != null
          ? `<span class="hill-ele">${escapeHtml(String(h.elevationM))} m</span>`
          : "";
      const wiki = h.wikipedia
        ? ` <a class="hill-link" href="${escapeAttr(h.wikipedia)}" target="_blank" rel="noopener">↗</a>`
        : "";
      return `<li><span class="hill-name">${escapeHtml(h.name || "Summit")}</span>${cls}${ele}${wiki}</li>`;
    })
    .join("");
  const more =
    extra > 0 ? `<p class="hills-on__more">${extra} more classified summit${extra === 1 ? "" : "s"} on this island</p>` : "";
  return `<div class="hills-on">
    <h4 class="hills-on__title">Classified hills</h4>
    <ul class="hills-on__list">${items}</ul>
    ${more}
    ${enrichmentAttribution(island.hillsOnAttribution)}
  </div>`;
}

function renderMaritimeAidsSection(island) {
  const lights = island.lighthouses;
  if (!Array.isArray(lights) || !lights.length) return "";
  const onshore = [];
  const offshore = [];
  for (const l of lights) {
    (l.offshore ? offshore : onshore).push(l);
  }
  const renderOne = (l) => {
    const meta = [];
    if (l.characteristic) meta.push(escapeHtml(l.characteristic));
    if (l.rangeNm != null) meta.push(`${escapeHtml(String(l.rangeNm))} nm`);
    if (l.heightM != null) meta.push(`${escapeHtml(String(l.heightM))} m tower`);
    if (l.establishedYear) meta.push(`since ${escapeHtml(String(l.establishedYear))}`);
    if (l.operator) meta.push(escapeHtml(l.operator));
    if (l.status && l.status !== "unknown") meta.push(escapeHtml(l.status));
    const metaHtml = meta.length
      ? `<p class="lighthouse-meta">${meta.join(" · ")}</p>`
      : "";
    const wiki = l.wikipedia
      ? `<a href="${escapeAttr(l.wikipedia)}" target="_blank" rel="noopener">Wikipedia ↗</a>`
      : "";
    const osm =
      l.osmType && l.osmId != null
        ? `<a href="https://www.openstreetmap.org/${escapeAttr(l.osmType)}/${l.osmId}" target="_blank" rel="noopener">OSM ↗</a>`
        : "";
    const links = [wiki, osm].filter(Boolean).join(" · ");
    return `<article class="lighthouse">
      <h4 class="lighthouse__name">${escapeHtml(l.name || "Lighthouse")}</h4>
      ${metaHtml}
      ${links ? `<p class="lighthouse__links">${links}</p>` : ""}
    </article>`;
  };
  const list = (arr, title) =>
    arr.length
      ? `<div class="lighthouses__group"><h4 class="lighthouses__subtitle">${escapeHtml(title)}</h4>${arr.map(renderOne).join("")}</div>`
      : "";
  return `<div class="section lighthouses">
    <h3>Maritime aids</h3>
    <p class="lighthouses__nav-warning" role="note"><strong>Not for navigation.</strong> Summaries for interest only — verify with official charts and notices to mariners.</p>
    ${list(onshore, "On island")}
    ${list(offshore, "Offshore (within 200 m)")}
    ${enrichmentAttribution(island.lighthousesAttribution)}
  </div>`;
}

function renderReservesWildlifeSection(island) {
  const reserves = island.rspbReserves;
  const colonies = island.wildlifeColonies;
  const hasReserves = Array.isArray(reserves) && reserves.length;
  const hasColonies = Array.isArray(colonies) && colonies.length;
  if (!hasReserves && !hasColonies) return "";

  let reservesHtml = "";
  if (hasReserves) {
    const cards = reserves
      .map((r) => {
        const meta = [];
        if (r.designation) meta.push(escapeHtml(r.designation));
        if (r.areaHa != null) meta.push(`${escapeHtml(String(r.areaHa))} ha`);
        if (r.established) meta.push(`from ${escapeHtml(String(r.established))}`);
        const link = r.url
          ? `<a href="${escapeAttr(r.url)}" target="_blank" rel="noopener">Reserve page ↗</a>`
          : "";
        return `<article class="reserve">
          <h4 class="reserve__name">${escapeHtml(r.name || "Nature reserve")}</h4>
          ${meta.length ? `<p class="reserve__meta">${meta.join(" · ")}</p>` : ""}
          ${link}
        </article>`;
      })
      .join("");
    reservesHtml = `<div class="reserves"><h4 class="reserves-wildlife__subtitle">Reserves</h4>${cards}</div>`;
  }

  let coloniesHtml = "";
  if (hasColonies) {
    const chips = colonies
      .map((c) => {
        const label = formatSpeciesLabel(c.species);
        const sched =
          c.scheduleListed === true
            ? ' <span class="colony-species-scheduled" title="Protected schedule species — disturbance risks offence">protected</span>'
            : "";
        const season = c.season ? ` <span class="colony-species-season">${escapeHtml(c.season)}</span>` : "";
        return `<li class="colony-species colony-species-${escapeAttr(c.species || "unknown")}">${escapeHtml(label)}${sched}${season}</li>`;
      })
      .join("");
    coloniesHtml = `<div class="wildlife-colonies">
      <h4 class="reserves-wildlife__subtitle">Breeding &amp; resident wildlife</h4>
      <p class="wildlife-colonies__note">Island-level presence only — no colony counts or nest locations.</p>
      <ul class="wildlife-colonies__list">${chips}</ul>
    </div>`;
  }

  const attr = [island.rspbReservesAttribution, island.wildlifeColoniesAttribution]
    .filter(Boolean)
    .join(" ");

  return `<div class="section reserves-wildlife">
    <h3>Reserves &amp; wildlife</h3>
    ${reservesHtml}
    ${coloniesHtml}
    ${enrichmentAttribution(attr)}
  </div>`;
}

// ---------- Helpers ----------
function formatPopulation(n) {
  if (n === 0) return "Uninhabited";
  if (n == null) return "Population unknown";
  return new Intl.NumberFormat("en-GB").format(n) + " people";
}

function formatArea(km2) {
  if (km2 == null) return "—";
  if (km2 < 0.01) return `${(km2 * 1_000_000).toFixed(0)} m²`;
  if (km2 < 1) return `${(km2 * 100).toFixed(1)} ha`;
  return `${new Intl.NumberFormat("en-GB", {
    maximumFractionDigits: km2 < 10 ? 1 : 0,
  }).format(km2)} km²`;
}

function formatHighPointRow(island) {
  const hillsBlock = renderHillsOnBlock(island);
  if (island.highestPointM == null) {
    if (hillsBlock) return hillsBlock;
    return `<span title="No surveyed peak or Wikidata elevation found inside this island's polygon.">—</span>`;
  }
  const namePart = island.highestPointName
    ? ` (${escapeHtml(island.highestPointName)})`
    : "";
  const value = `${island.highestPointM} m${namePart}`;
  const conf = island.highestPointConfidence;
  if (!conf || conf === "n/a") return value + hillsBlock;
  const sourceLabel =
    {
      "osm-peak": "OSM surveyed peak",
      "wikidata-p2044": "Wikidata estimate",
      "manual": "hand-curated",
    }[island.highestPointSource] || "";
  if (conf === "estimate") {
    return `${value} <span style="color:var(--text-muted);font-size:12px">· estimate${sourceLabel ? " · " + sourceLabel : ""}</span>${hillsBlock}`;
  }
  return `${value} <span style="color:var(--text-muted);font-size:12px">· ${sourceLabel || "high confidence"}</span>${hillsBlock}`;
}

function formatAreaRow(island) {
  if (island.areaKm2 == null) {
    return `<span title="No verified polygon for this island - we publish areas only where we can vouch for them to within 2 %.">N/A</span>`;
  }
  const value = formatArea(island.areaKm2);
  const conf = island.areaConfidence;
  if (!conf || conf === "n/a") return value;
  const sourceLabel =
    {
      "osm-way": "OSM way",
      "osm-relation": "OSM multipolygon",
      "osm-coastline-polygon": "OSM coastline",
      "osm-via-wikidata-way": "OSM (via Wikidata)",
      "osm-via-wikidata-relation": "OSM (via Wikidata)",
    }[island.areaSource] || "OSM";
  const confLabel = conf === "high" ? "high confidence" : "medium confidence";
  return `${value} <span style="color:var(--text-muted);font-size:12px">· ${confLabel} · ${sourceLabel}</span>`;
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

function formatSubtypeLabel(sub) {
  if (!sub) return "";
  return sub.split("-").map((w) => capitalize(w)).join(" ");
}

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

// ---------- Chatbot ----------
//
// A local, privacy-preserving "AI chatbot style" island finder. It parses a
// natural-language request and ranks islands in the dataset by relevance.
// No external API calls, no data leaves the browser.

const CHAT_NATIONS = {
  Scotland: ["scotland", "scottish", "scots", "alba", "caledonia", "highlands", "highland"],
  England: ["england", "english", "cornish", "cornwall", "yorkshire", "essex"],
  Wales: ["wales", "welsh", "cymru", "cymraeg"],
  "Northern Ireland": ["northern ireland", "ulster", "nornia", "ni "],
  Ireland: ["ireland", "irish", "eire", "éire", "republic of ireland", "roi "],
  "Crown Dependency": [
    "crown dependency", "crown dep", "isle of man", "manx",
    "jersey", "guernsey", "channel islands", "channel isle",
  ],
};

const CHAT_TYPES = {
  sea: ["sea", "coastal", "offshore", "ocean", "atlantic", "saltwater", "salt water"],
  lake: ["lake", "loch", "lough", "tarn", "reservoir", "mere", "llyn"],
  river: ["river", "fluvial", "stream"],
};

const CHAT_SUBTYPES = {
  reservoir: ["reservoir", "reservoirs"],
  canal: ["canal", "canals"],
  estuary: ["estuary", "estuarine", "estuaries"],
  crannog: ["crannog", "crannogs", "artificial island", "artificial islands"],
  oxbow: ["oxbow", "oxbows"],
};

const CHAT_ARCHIPELAGOS = {
  "Inner Hebrides": ["inner hebrides"],
  "Outer Hebrides": ["outer hebrides", "western isles"],
  Orkney: ["orkney", "orcadian"],
  Shetland: ["shetland", "shetlandic", "zetland"],
  "Isles of Scilly": ["scilly", "scillonian"],
  "Aran Islands": ["aran islands", "árainn"],
  "Channel Islands": ["channel islands"],
};

const CHAT_FEATURES = {
  mountain: ["mountain", "mountains", "mountainous", "peak", "peaks", "summit",
    "summits", "munro", "munros", "corbett", "sgurr", "sgùrr", "beinn", "ben ",
    "ridge", "cuillin"],
  hill: ["hill", "hills", "hilltop", "fell", "moor", "moorland"],
  castle: ["castle", "fortress", "tower house", "keep"],
  abbey: ["abbey", "priory", "monastery", "monastic", "convent", "nunnery"],
  broch: ["broch", "hillfort", "iron age"],
  ferry: ["ferry", "ferries", "calmac", "passenger boat", "ferry-accessible",
    "ferry accessible", "ferry served", "ferry islands"],
  photo: ["photo", "photos", "photograph", "photographs", "pictured", "with image",
    "has a photo", "has photo", "with photos"],
  bridge: ["bridge"],
  causeway: ["causeway", "tidal road", "walk across"],
  lighthouse: ["lighthouse", "beacon"],
  wildlife: ["wildlife", "birds", "bird", "seabird", "seabirds", "puffin",
    "puffins", "gannet", "gannets", "seal", "seals", "deer", "sea eagle",
    "white-tailed eagle", "rspb", "nature reserve"],
  whisky: ["whisky", "whiskey", "distillery", "distilleries", "malt"],
  beach: ["beach", "beaches", "sand", "sandy"],
  tidal: ["tidal"],
  uninhabited: ["uninhabited", "empty", "deserted", "abandoned", "no one",
    "no one lives", "nobody", "no inhabitants"],
  inhabited: ["inhabited", "populated", "people live", "village", "villages",
    "community", "town", "city"],
  walkable: ["walkable", "you can walk", "walk to"],
  remote: ["remote", "isolated", "far", "lonely", "outermost"],
  forsale: ["for sale", "on the market", "buy", "buying", "property", "listing",
    "listings", "estate agent", "for-sale"],
};

const CHAT_SORTS = {
  largest: { sortBy: "areaKm2", dir: "desc" },
  biggest: { sortBy: "areaKm2", dir: "desc" },
  smallest: { sortBy: "areaKm2", dir: "asc" },
  tiniest: { sortBy: "areaKm2", dir: "asc" },
  "most populous": { sortBy: "population", dir: "desc" },
  "most populated": { sortBy: "population", dir: "desc" },
  "highest": { sortBy: "highestPointM", dir: "desc" },
  "tallest": { sortBy: "highestPointM", dir: "desc" },
};

// Small gazetteer of major UK + IE + Crown Dep places, for "near <city>"
// proximity filtering. lat/lng are city-centre approximations.
const CHAT_PLACES = {
  London: [51.5074, -0.1278],
  Edinburgh: [55.9533, -3.1883],
  Glasgow: [55.8642, -4.2518],
  Aberdeen: [57.1497, -2.0943],
  Inverness: [57.4778, -4.2247],
  Oban: [56.4153, -5.4747],
  Mallaig: [57.008, -5.829],
  Ullapool: [57.895, -5.1622],
  Stornoway: [58.209, -6.387],
  Cardiff: [51.4816, -3.1791],
  Holyhead: [53.3092, -4.6296],
  Liverpool: [53.4084, -2.9916],
  Belfast: [54.5973, -5.9301],
  Derry: [54.9966, -7.3086],
  Dublin: [53.3498, -6.2603],
  Galway: [53.2707, -9.0568],
  Cork: [51.8985, -8.4756],
  Limerick: [52.6638, -8.6267],
  Newcastle: [54.9783, -1.6178],
  Plymouth: [50.3755, -4.1427],
  Bristol: [51.4545, -2.5879],
  Manchester: [53.4808, -2.2426],
  Penzance: [50.1186, -5.5373],
  Portsmouth: [50.8198, -1.088],
  Southampton: [50.9097, -1.4044],
  Douglas: [54.1509, -4.4854],
  "St Helier": [49.1903, -2.1093],
  "St Peter Port": [49.4555, -2.5368],
  Kirkwall: [58.981, -2.961],
  Lerwick: [60.1551, -1.1469],
};
const CHAT_PLACE_KEYS = Object.keys(CHAT_PLACES);

function chatHaversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

const CHAT_SUGGESTIONS = [
  "How tall is Skye?",
  "How big is Anglesey?",
  "What's the largest island in Wales?",
  "What's the highest island in Scotland?",
  "How many crannogs are there in Ireland?",
  "How many uninhabited islands in Scotland?",
  "Compare Mull and Islay",
  "Lewis vs Skye",
  "Scottish islands with mountains",
  "Islands with a castle near Oban",
  "Scottish islands with puffins",
  "Tidal islands in England",
  "Summer ferries to Pembrokeshire islands",
];

// Controlled semantic tags (loaded from data/chat_tag_vocabulary.json).
let CHAT_SEMANTIC_TAGS = {};
let chatTagVocabularyPromise = null;

function chatBuildSemanticTagMap(vocab) {
  const out = {};
  for (const entry of vocab?.tags || []) {
    if (!entry?.id) continue;
    const syns = [entry.id, ...(entry.synonyms || [])]
      .map((s) => String(s).toLowerCase().trim())
      .filter(Boolean);
    out[entry.id] = syns;
  }
  return out;
}

function ensureChatTagVocabulary() {
  if (!chatTagVocabularyPromise) {
    chatTagVocabularyPromise = fetch("data/chat_tag_vocabulary.json")
      .then((r) => (r.ok ? r.json() : { tags: [] }))
      .then((vocab) => {
        CHAT_SEMANTIC_TAGS = chatBuildSemanticTagMap(vocab);
        return vocab;
      })
      .catch(() => {
        CHAT_SEMANTIC_TAGS = {};
        return { tags: [] };
      });
  }
  return chatTagVocabularyPromise;
}

function chatTokens(text) {
  return text.toLowerCase().normalize("NFKD");
}

/** Escape a string for safe use inside a RegExp. */
function chatEscapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * True when `token` appears in `hay` as a whole token (not as a substring
 * inside another word — avoids "worth" matching "Isleworth").
 */
function chatWholeWord(hay, token) {
  if (!hay || !token || token.length < 2) return false;
  const re = new RegExp(
    "(?:^|[^a-z0-9à-ÿ])" + chatEscapeRe(token) + "(?:$|[^a-z0-9à-ÿ])",
    "i",
  );
  return re.test(" " + hay + " ");
}

function parseChatQuery(rawText) {
  const text = chatTokens(rawText);
  const q = {
    rawText,
    nations: new Set(),
    types: new Set(),
    subtypes: new Set(),
    archipelagos: new Set(),
    features: new Set(),
    sort: null,
    sizeMin: null,
    sizeMax: null,
    near: null,        // { name, lat, lng, radiusKm }
    keywords: [],
    /** "Worth visiting" / best / recommend — rank visitor-worthy islands. */
    recommendationIntent: false,
    /** Parsed count (e.g. "five islands") for recommendation replies. */
    recommendN: null,
    // Ferry intent — set when the user clearly wants ferry-accessible
    // islands or the routes themselves.
    ferryIntent: false,
    ferryTypeWanted: null,        // 'car-and-foot' | 'foot-only'
    ferrySeasonWanted: null,      // 'year-round' | 'summer-only'
    ferryOperatorWanted: null,    // operator-id substring match
    ferryFromPort: null,          // free-text port name to match against terminal names
    photoOnly: false,
    elevationOnly: false,
    curatedOnly: false,
    hideUnconfirmed: false,
    semanticTags: new Set(),
    nearUnresolved: null,
  };

  for (const [nation, syn] of Object.entries(CHAT_NATIONS)) {
    if (syn.some((w) => text.includes(w))) q.nations.add(nation);
  }
  for (const [type, syn] of Object.entries(CHAT_TYPES)) {
    if (syn.some((w) => text.includes(w))) q.types.add(type);
  }
  for (const [sub, syn] of Object.entries(CHAT_SUBTYPES)) {
    if (syn.some((w) => text.includes(w))) q.subtypes.add(sub);
  }
  for (const [arch, syn] of Object.entries(CHAT_ARCHIPELAGOS)) {
    if (syn.some((w) => text.includes(w))) q.archipelagos.add(arch);
  }
  // "The Hebrides" / "in the Hebrides" — treat as both Inner + Outer unless
  // the user already narrowed to one chain.
  if (
    (/\bhebrides\b/.test(text) || /\bhebridean\b/.test(text)) &&
    !/\binner\s+hebrides\b/.test(text) &&
    !/\bouter\s+hebrides\b/.test(text) &&
    !/\bwestern\s+isles\b/.test(text)
  ) {
    q.archipelagos.add("Inner Hebrides");
    q.archipelagos.add("Outer Hebrides");
  }

  for (const [feat, syn] of Object.entries(CHAT_FEATURES)) {
    if (syn.some((w) => text.includes(w))) q.features.add(feat);
  }
  for (const [tagId, syn] of Object.entries(CHAT_SEMANTIC_TAGS)) {
    if (syn.some((w) => text.includes(w))) q.semanticTags.add(tagId);
  }
  // Disambiguate `inhabited` substring inside `uninhabited`.
  if (q.features.has("uninhabited")) q.features.delete("inhabited");

  for (const [k, sortDef] of Object.entries(CHAT_SORTS)) {
    if (text.includes(k)) {
      q.sort = sortDef;
      break;
    }
  }

  // Ferry intent detection. Triggered when the user explicitly mentions
  // ferries / sailings / boats-to or a known operator. Conservative so
  // mentions of "ferry crossing" inside a free-text description don't
  // hijack the rest of the query.
  if (/\b(ferry|ferries|sailings?|boat to|ferry from|ferry to|ferry route)\b/.test(text)) {
    q.ferryIntent = true;
  }
  if (/\b(car ferr|car-and-foot|vehicle ferry)/.test(text)) {
    q.ferryTypeWanted = "car-and-foot";
    q.ferryIntent = true;
  }
  if (/\b(foot ferr|passenger ferr|foot-only|pedestrian ferry)/.test(text)) {
    q.ferryTypeWanted = "foot-only";
    q.ferryIntent = true;
  }
  if (/\b(summer ferr|summer only|summer sailings)/.test(text)) {
    q.ferrySeasonWanted = "summer-only";
    q.ferryIntent = true;
  }
  if (/\b(year-round|all year|winter ferry|winter sailings?)/.test(text)) {
    q.ferrySeasonWanted = "year-round";
    q.ferryIntent = true;
  }
  // "ferry from <port>" / "sailings from <port>"
  let fromMatch = text.match(/(?:ferry|ferries|sailings?|boat)s?\s+from\s+([a-zà-ÿ' -]{3,40}?)(?:\s+(?:to|and|with|that|in|on|that)\b|$)/);
  if (fromMatch) {
    q.ferryFromPort = fromMatch[1].trim();
    q.ferryIntent = true;
  }
  // "calmac ferries", "wightlink", etc.
  const KNOWN_OPS = ["calmac", "northlink", "pentland", "wightlink", "red funnel",
                     "hovertravel", "scillonian", "lundy", "steam packet",
                     "condor", "stena", "irish ferries", "p&o", "dfds",
                     "brittany", "rathlin", "aran", "doolin", "cape clear",
                     "tory", "sark", "manche iles"];
  for (const op of KNOWN_OPS) {
    if (text.includes(op)) {
      q.ferryOperatorWanted = op;
      q.ferryIntent = true;
      break;
    }
  }

  // ----- "Worth visiting" / best-of lists -----
  const wordToRecommendN = {
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8,
    nine: 9,
    ten: 10,
    eleven: 11,
    twelve: 12,
  };
  let numPick = text.match(
    /\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s+islands?\b/,
  );
  if (!numPick) {
    numPick = text.match(
      /\b(?:give|list|name|pick|tell)\s+(?:me\s+)?(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b/,
    );
  }
  if (!numPick) {
    numPick = text.match(
      /\b(?:top|best)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b/,
    );
  }
  if (!numPick) {
    numPick = text.match(
      /\b(?:top|best)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+islands?\b/,
    );
  }
  if (numPick) {
    const rawN = numPick[1];
    const n = /^\d+$/.test(rawN)
      ? parseInt(rawN, 10)
      : wordToRecommendN[rawN] ?? null;
    if (n != null && n >= 1 && n <= 25) q.recommendN = n;
  }
  if (
    /\b(worth\s+visiting|worth\s+a\s+visit|nice\s+to\s+visit|good\s+to\s+visit|places?\s+to\s+visit|must-?see|must\s+see|recommend(?:ations?)?|suggested\s+islands?|best\s+islands?|top\s+islands?|famous\s+islands?|great\s+islands?|interesting\s+islands?)\b/.test(
      text,
    )
  ) {
    q.recommendationIntent = true;
  }
  if (!q.recommendationIntent && q.recommendN && (q.archipelagos.size || q.nations.size)) {
    q.recommendationIntent = true;
  }
  if (q.recommendationIntent && !q.types.size) {
    q.types.add("sea");
  }

  // "smaller than X km", "larger than X km"
  let m = text.match(/(?:smaller|less than|under)\s+(\d+(?:\.\d+)?)\s*(?:km2|km²|sq km|square km|km)/);
  if (m) q.sizeMax = parseFloat(m[1]);
  m = text.match(/(?:larger|bigger|more than|over)\s+(\d+(?:\.\d+)?)\s*(?:km2|km²|sq km|square km|km)/);
  if (m) q.sizeMin = parseFloat(m[1]);
  if (/\blarge\s+islands?\b|\bbig\s+islands?\b/.test(text) && q.sizeMin == null) {
    q.sizeMin = 10;
  }
  if (/\b(with\s+)?(a\s+)?photos?\b|\bhas\s+(a\s+)?photo\b|\bpictured\b/.test(text)) {
    q.photoOnly = true;
  }
  if (/\b(with\s+)?elevation\b|\bhigh\s+point\b|\bhas\s+a\s+summit\b/.test(text)) {
    q.elevationOnly = true;
  }
  if (/\bcurated\s+only\b|\bcanonical\s+islands?\b/.test(text)) {
    q.curatedOnly = true;
  }
  if (/\bhide\s+unconfirmed\b|\bconfirmed\s+only\b|\bno\s+unconfirmed\b/.test(text)) {
    q.hideUnconfirmed = true;
  }
  if (/\bferry[- ]?(accessible|access|served)\b|\bferry\s+islands?\b/.test(text)) {
    q.ferryIntent = true;
  }

  // Proximity: "within N miles/km of <place>" → radius + place.
  // Or "near <place>" / "off <place>" / "around <place>" → default 100 km.
  let nearMatch = text.match(
    /within\s+(\d+(?:\.\d+)?)\s*(km|miles?|mi)\s+of\s+(.+?)(?:\s+(?:and|with|that|which|in|on)\b|$)/
  );
  let placeName = "";
  let radiusKm = 100;
  if (nearMatch) {
    const n = parseFloat(nearMatch[1]);
    radiusKm = /mi/.test(nearMatch[2]) ? n * 1.60934 : n;
    placeName = nearMatch[3].trim();
  } else {
    nearMatch = text.match(/(?:near|off|around|close to)\s+(.+?)(?:\s+(?:and|with|that|which|in|on)\b|$)/);
    if (nearMatch) placeName = nearMatch[1].trim();
  }
  if (placeName) {
    // Case-insensitive match against known place names; allow partial prefix.
    const hit = CHAT_PLACE_KEYS.find(
      (k) => k.toLowerCase() === placeName ||
             k.toLowerCase().startsWith(placeName) ||
             placeName.startsWith(k.toLowerCase()),
    );
    if (hit) {
      const [lat, lng] = CHAT_PLACES[hit];
      q.near = { name: hit, lat, lng, radiusKm };
    } else {
      q.nearUnresolved = placeName;
    }
  }

  // Strip out words we already matched to find residual keywords.
  let residual = " " + text + " ";
  const stripList = [
    ...Object.values(CHAT_NATIONS).flat(),
    ...Object.values(CHAT_TYPES).flat(),
    ...Object.values(CHAT_SUBTYPES).flat(),
    ...Object.values(CHAT_ARCHIPELAGOS).flat(),
    ...Object.values(CHAT_FEATURES).flat(),
    ...Object.values(CHAT_SEMANTIC_TAGS).flat(),
    ...Object.keys(CHAT_SORTS),
    "island", "islands", "show", "me", "the", "a", "an", "with", "and",
    "in", "of", "to", "for", "find", "i", "want", "you", "have", "are",
    "is", "that", "where", "which", "what", "any", "some", "all", "near",
    "off", "on", "from",
    "worth", "visiting", "visit", "worthwhile", "recommend", "recommendation",
    "recommendations", "suggestion", "suggestions", "beautiful", "famous",
    "interesting", "picks", "seeing", "hebrides", "hebridean",
  ];
  for (const w of stripList) {
    residual = residual.split(" " + w + " ").join(" ");
  }
  q.keywords = residual
    .split(/[^a-zà-ÿ0-9'-]+/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 3);

  return q;
}

function chatHaystack(island) {
  // Defensive: tags is normally an array but a malformed record could ship
  // it as a string / object / null.  Coerce safely to a flat string.
  let tagStr = "";
  if (Array.isArray(island.tags)) tagStr = island.tags.join(" ");
  else if (typeof island.tags === "string") tagStr = island.tags;
  return [
    island.name,
    island.archipelago,
    island.shortDescription,
    island.geography,
    island.history,
    island.transport,
    island.accommodation,
    tagStr,
    Array.isArray(island.hillsOn)
      ? island.hillsOn.map((h) => [h.name, h.classification].filter(Boolean).join(" ")).join(" ")
      : "",
    Array.isArray(island.wildlifeColonies)
      ? island.wildlifeColonies.map((w) => [w.species, w.category].filter(Boolean).join(" ")).join(" ")
      : "",
    (island.parentWaterBody && island.parentWaterBody.name) || "",
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function scoreChatIsland(island, q) {
  let score = 0;
  if (q.nations.size && q.nations.has(island.nation)) score += 6;
  else if (q.nations.size) return -Infinity; // hard filter

  if (q.types.size && q.types.has(island.type)) score += 6;
  else if (q.types.size) return -Infinity;

  if (q.subtypes.size && q.subtypes.has(island.subtype)) score += 5;
  else if (q.subtypes.size) return -Infinity;

  if (q.archipelagos.size && island.archipelago && q.archipelagos.has(island.archipelago)) {
    score += 4;
  } else if (q.archipelagos.size) {
    return -Infinity;
  }

  if (q.sizeMin != null && (island.areaKm2 || 0) < q.sizeMin) return -Infinity;
  if (q.sizeMax != null && (island.areaKm2 || 0) > q.sizeMax) return -Infinity;
  if (q.photoOnly && !islandHasPhoto(island)) return -Infinity;
  if (q.elevationOnly && !islandHasElevation(island)) return -Infinity;
  if (q.curatedOnly && island.source !== "curated") return -Infinity;
  if (q.hideUnconfirmed && island.classification?.confidence === "unconfirmed") {
    return -Infinity;
  }

  // Visitor "best of" lists: drop anonymous micro-islets in a region.
  if (q.recommendationIntent && (q.archipelagos.size || q.nations.size)) {
    const area = island.areaKm2 || 0;
    const pop = island.population || 0;
    const hasImg = (island.images && island.images.length) || island.image;
    const substantial =
      area >= 3 ||
      pop > 0 ||
      island.source === "curated" ||
      (hasImg && area >= 0.8);
    if (!substantial) return -Infinity;
  }

  // Proximity hard filter and scoring.
  if (q.near) {
    if (!Number.isFinite(island.lat) || !Number.isFinite(island.lng)) {
      return -Infinity;
    }
    const d = chatHaversineKm(q.near.lat, q.near.lng, island.lat, island.lng);
    if (d > q.near.radiusKm) return -Infinity;
    score += 6 * (1 - d / q.near.radiusKm);
  }

  // Ferry intent. Only applied when the ferry index has loaded; otherwise
  // we just rely on the existing `ferry` feature text-match below so the
  // chat still returns something useful before the first details click.
  if (q.ferryIntent && state.ferryRoutesByIsland) {
    const routes = state.ferryRoutesByIsland.get(island.id) || [];
    if (!routes.length) return -Infinity;
    let ferryScore = 0;
    let typeMatch = !q.ferryTypeWanted;
    let seasonMatch = !q.ferrySeasonWanted;
    let opMatch = !q.ferryOperatorWanted;
    let portMatch = !q.ferryFromPort;
    for (const r of routes) {
      if (q.ferryTypeWanted && r.type === q.ferryTypeWanted) typeMatch = true;
      if (q.ferrySeasonWanted && r.seasonality === q.ferrySeasonWanted) seasonMatch = true;
      if (q.ferryOperatorWanted) {
        const opName = (r._operator?.name || r.operatorId || "").toLowerCase();
        if (opName.includes(q.ferryOperatorWanted)) opMatch = true;
      }
      if (q.ferryFromPort) {
        const f = (r._fromTerminal?.name || "").toLowerCase();
        const t = (r._toTerminal?.name || "").toLowerCase();
        if (f.includes(q.ferryFromPort) || t.includes(q.ferryFromPort)) portMatch = true;
      }
    }
    if (!typeMatch || !seasonMatch || !opMatch || !portMatch) return -Infinity;
    ferryScore += 6 + Math.min(4, routes.length); // baseline + small bonus for many routes
    if (routes.some((r) => r.type === "car-and-foot")) ferryScore += 1;
    if (routes.some((r) => r.seasonality === "year-round")) ferryScore += 1;
    score += ferryScore;
  }

  const hay = chatHaystack(island);
  const islandTags = new Set(
    (Array.isArray(island.tags) ? island.tags : [])
      .map((t) => String(t).toLowerCase()),
  );

  for (const tagId of q.semanticTags) {
    if (islandTags.has(tagId)) score += 7;
    else {
      const syns = CHAT_SEMANTIC_TAGS[tagId] || [];
      let hits = 0;
      for (const w of syns) {
        if (hay.includes(w)) hits++;
      }
      if (hits > 0) score += 3 + Math.min(3, hits);
      else if (q.semanticTags.size === 1) score -= 2;
    }
  }

  for (const feat of q.features) {
    const syn = CHAT_FEATURES[feat] || [];
    let hits = 0;
    for (const w of syn) {
      if (hay.includes(w)) hits++;
    }
    if (feat === "inhabited") {
      if ((island.population || 0) > 0) score += 4;
      else if (q.features.has("inhabited")) score -= 3;
    } else if (feat === "uninhabited") {
      if (!island.population) score += 4;
      else score -= 3;
    } else if (feat === "tidal" && island.subtype === "estuary") {
      score += 4;
    } else if (feat === "photo" && islandHasPhoto(island)) {
      score += 4;
    } else if (feat === "forsale" && islandHasPropertyListing(island)) {
      score += 5;
    } else if (feat === "forsale") {
      score -= 3;
    } else if (hits > 0) {
      score += 2 + Math.min(3, hits);
    } else if (q.features.size === 1) {
      score -= 1;
    }
  }

  const nameHay = (island.name || "").toLowerCase();
  let nameHits = 0;
  for (const k of q.keywords) {
    if (k.length < 3) continue;
    if (chatWholeWord(nameHay, k)) {
      score += 5;
      nameHits++;
    } else if (chatWholeWord(hay, k)) {
      score += 1;
    }
  }
  // Reward an exact-name match heavily so "Belle Isle" lands the right island.
  if (q.keywords.length && nameHits === q.keywords.length) score += 4;

  if (q.recommendationIntent) {
    if ((island.population || 0) > 500) score += 2.2;
    else if ((island.population || 0) > 50) score += 1.6;
    else if ((island.population || 0) > 0) score += 1.1;
    if (island.shortDescription && island.shortDescription.length > 100) score += 1.8;
    else if (island.shortDescription && island.shortDescription.length > 50) score += 1;
    if (island.images && island.images.length) score += 1.8;
    else if (island.image) score += 1.2;
    if ((island.areaKm2 || 0) > 200) score += 1.6;
    else if ((island.areaKm2 || 0) > 30) score += 0.9;
    if (island.wikipedia) score += 0.5;
  }

  if (island.images && island.images.length) score += 0.6;
  if (island.population) score += 0.3;
  if (island.areaKm2) score += Math.min(1, Math.log10(1 + island.areaKm2));

  return score;
}

function searchChatIslands(rawText, limit = 6) {
  const q = parseChatQuery(rawText);
  const outLimit = q.recommendationIntent
    ? q.recommendN && q.recommendN >= 1 && q.recommendN <= 25
      ? q.recommendN
      : 8
    : limit;
  const scored = [];
  for (const i of state.islands) {
    if (!i || typeof i !== "object") continue;
    let s;
    try {
      s = scoreChatIsland(i, q);
    } catch (_err) {
      // One malformed record must never break the whole query; skip it.
      continue;
    }
    if (s > -Infinity && s > 0) scored.push({ island: i, score: s });
  }
  if (q.sort) {
    // Drop entries without a value for the sort key — null doesn't
    // belong at either end of a "largest" / "smallest" list.
    const sortable = scored.filter((x) => {
      const v = x.island[q.sort.sortBy];
      return typeof v === "number" && Number.isFinite(v) && v > 0;
    });
    sortable.sort((a, b) => {
      const av = a.island[q.sort.sortBy];
      const bv = b.island[q.sort.sortBy];
      return q.sort.dir === "desc" ? bv - av : av - bv;
    });
    return { query: q, results: sortable.slice(0, outLimit), total: sortable.length };
  }
  const photosFirst = q.photoOnly;
  scored.sort(
    (a, b) =>
      b.score - a.score
        || listSortCompare(a.island, b.island, { photosFirst }),
  );
  return { query: q, results: scored.slice(0, outLimit), total: scored.length };
}

// ----- Direct-answer engine -----
//
// Detect question intent (count, superlative, comparison, lookup,
// aggregation) and compute a direct factual answer.  When the intent
// fires we prepend a one-sentence answer above the standard "found N
// matches" summary, so a query like "How tall is Ben More?" gets an
// immediate "Ben More (on Mull) rises to 966 m above sea level" rather
// than just a card list.

const _CHAT_NUMBER_FMT = new Intl.NumberFormat("en-GB");

function _fmtKm2(v) {
  if (v == null) return "—";
  if (v < 0.01) return `${(v * 1_000_000).toFixed(0)} m²`;
  if (v < 1)    return `${(v * 100).toFixed(1)} ha`;
  if (v < 10)   return `${v.toFixed(1)} km²`;
  return `${_CHAT_NUMBER_FMT.format(Math.round(v))} km²`;
}

function _fmtM(v) {
  if (v == null) return "—";
  return `${Math.round(v)} m`;
}

function _islandShortLabel(i) {
  const bits = [i.name];
  if (i.archipelago && i.archipelago !== i.name) bits.push("(" + i.archipelago + ")");
  return bits.join(" ");
}

function detectAnswerIntent(rawText) {
  const t = rawText.toLowerCase().trim();
  // Count: "how many … islands" / "number of … islands" / "count of …"
  if (/\b(how many|number of|count of|count the)\b/.test(t)) {
    return { kind: "count" };
  }
  // Comparison: "compare A and B" / "X vs Y" / "is X bigger than Y"
  let m = t.match(/\bcompare\s+(.+?)\s+(?:and|with|to|vs\.?)\s+(.+?)\s*\??$/);
  if (m) return { kind: "compare", a: m[1].trim(), b: m[2].trim() };
  m = t.match(/^(?:is\s+)?(.+?)\s+(?:bigger|larger|smaller|taller|higher|lower)\s+than\s+(.+?)\s*\??$/);
  if (m) return { kind: "compare", a: m[1].trim(), b: m[2].trim() };
  m = t.match(/^(.+?)\s+vs\.?\s+(.+?)\s*\??$/);
  if (m && m[1].length > 1 && m[2].length > 1 && !/\b(island|loch|sea|river|lake)\b/.test(m[1] + " " + m[2])) {
    return { kind: "compare", a: m[1].trim(), b: m[2].trim() };
  }
  // Superlative: "what is the largest/tallest/highest/smallest/most populous"
  m = t.match(
    /\bwhat(?:'s|\s+is)?\s+the\s+(largest|biggest|smallest|tiniest|tallest|highest|lowest|most populous|most populated|most remote|northernmost|southernmost|easternmost|westernmost)\b/,
  );
  if (m) return { kind: "superlative", which: m[1] };
  m = t.match(/^(?:the\s+)?(largest|biggest|smallest|tiniest|tallest|highest|lowest|most populous|most populated|most remote|northernmost|southernmost|easternmost|westernmost)\s+/);
  if (m) return { kind: "superlative", which: m[1] };
  // Lookup: "how big/tall/high is X" / "area/elevation of X" / "what is the area of X"
  m = t.match(/\bhow\s+(big|large|tall|high|wide|long|small)\s+is\s+(.+?)\s*\??$/);
  if (m) return { kind: "lookup", attr: m[1], name: m[2].trim() };
  m = t.match(/\b(area|size|elevation|height|highest\s*point|population|peak|summit)\s+of\s+(.+?)\s*\??$/);
  if (m) return { kind: "lookup", attr: m[1].replace(/\s+/g, ""), name: m[2].trim() };
  m = t.match(/\bwhat(?:'s|\s+is)\s+(?:the\s+)?(area|size|elevation|height|highest\s*point|population|peak|summit)\s+of\s+(.+?)\s*\??$/);
  if (m) return { kind: "lookup", attr: m[1].replace(/\s+/g, ""), name: m[2].trim() };
  // Aggregation: "total area", "combined population", "sum of …"
  m = t.match(/\b(total|combined|sum of|aggregate)\s+(area|size|population)\b/);
  if (m) return { kind: "aggregate", attr: m[2] };
  return null;
}

function _islandsMatchingFilter(query) {
  // Re-use the existing score function as a pure filter (drop islands
  // that fail any hard filter; keep everything else).
  const list = [];
  for (const i of state.islands) {
    const s = scoreChatIsland(i, query);
    if (s > -Infinity) list.push(i);
  }
  return list;
}

function _findIslandByName(name) {
  if (!name) return null;
  const norm = (s) => (s || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\bthe\s+|\bisle of\s+|\bisland of\s+/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  const target = norm(name);
  if (!target) return null;
  let best = null;
  let bestScore = -Infinity;
  for (const i of state.islands) {
    const n = norm(i.name);
    if (!n) continue;
    let s = 0;
    if (n === target) s = 100;
    else if (n.startsWith(target) || target.startsWith(n)) s = 50 + Math.min(target.length, n.length);
    else if (n.includes(target) || target.includes(n)) s = 20 + Math.min(target.length, n.length);
    else continue;
    // Bias toward larger / more-populated islands so "Skye" picks the big one.
    s += Math.min(5, Math.log10(1 + (i.areaKm2 || 0)));
    s += Math.min(3, Math.log10(1 + (i.population || 0)));
    if (s > bestScore) { bestScore = s; best = i; }
  }
  return best;
}

function _superlativeWinner(islands, which) {
  const tied = [];
  const want = which;
  let comparator;
  let formatter;
  switch (want) {
    case "largest": case "biggest":
      comparator = (a, b) => (b.areaKm2 || 0) - (a.areaKm2 || 0);
      formatter = (i) => _fmtKm2(i.areaKm2);
      break;
    case "smallest": case "tiniest":
      comparator = (a, b) => (a.areaKm2 || Infinity) - (b.areaKm2 || Infinity);
      formatter = (i) => _fmtKm2(i.areaKm2);
      break;
    case "tallest": case "highest":
      comparator = (a, b) => (b.highestPointM || 0) - (a.highestPointM || 0);
      formatter = (i) => _fmtM(i.highestPointM)
        + (i.highestPointName ? ` (${i.highestPointName})` : "");
      break;
    case "lowest":
      comparator = (a, b) => (a.highestPointM || Infinity) - (b.highestPointM || Infinity);
      formatter = (i) => _fmtM(i.highestPointM);
      break;
    case "most populous": case "most populated":
      comparator = (a, b) => (b.population || 0) - (a.population || 0);
      formatter = (i) => `${_CHAT_NUMBER_FMT.format(i.population || 0)} residents`;
      break;
    case "most remote":
      // Distance from nearest of London / Edinburgh / Dublin / Cardiff
      // as a rough "remote-ness" proxy.
      const anchors = [
        [51.5074, -0.1278], [55.9533, -3.1883],
        [53.3498, -6.2603], [51.4816, -3.1791],
      ];
      const distToAnchor = (i) => {
        let m = Infinity;
        for (const [la, ln] of anchors) {
          const d = chatHaversineKm(la, ln, i.lat, i.lng);
          if (d < m) m = d;
        }
        return m;
      };
      comparator = (a, b) => distToAnchor(b) - distToAnchor(a);
      formatter = (i) => `${Math.round(distToAnchor(i))} km from the nearest capital`;
      break;
    case "northernmost":
      comparator = (a, b) => (b.lat || -Infinity) - (a.lat || -Infinity);
      formatter = (i) => `lat ${i.lat?.toFixed(2)}°`;
      break;
    case "southernmost":
      comparator = (a, b) => (a.lat || Infinity) - (b.lat || Infinity);
      formatter = (i) => `lat ${i.lat?.toFixed(2)}°`;
      break;
    case "easternmost":
      comparator = (a, b) => (b.lng || -Infinity) - (a.lng || -Infinity);
      formatter = (i) => `lng ${i.lng?.toFixed(2)}°`;
      break;
    case "westernmost":
      comparator = (a, b) => (a.lng || Infinity) - (b.lng || Infinity);
      formatter = (i) => `lng ${i.lng?.toFixed(2)}°`;
      break;
    default:
      return null;
  }
  // Only include islands with the relevant attribute set
  const filtered = islands.filter((i) => {
    if (["largest","biggest","smallest","tiniest"].includes(want)) return i.areaKm2 != null && i.areaKm2 > 0;
    if (["tallest","highest","lowest"].includes(want)) return i.highestPointM != null;
    if (["most populous","most populated"].includes(want)) return (i.population || 0) > 0;
    return Number.isFinite(i.lat) && Number.isFinite(i.lng);
  });
  if (!filtered.length) return null;
  filtered.sort(comparator);
  return { winner: filtered[0], value: formatter(filtered[0]), ranking: filtered.slice(0, 5) };
}

function answerIntent(intent, query) {
  if (!intent) return null;
  const filtered = _islandsMatchingFilter(query);

  // ----- COUNT -----
  if (intent.kind === "count") {
    const n = filtered.length;
    const facets = [];
    if (query.nations.size) facets.push([...query.nations].join("/"));
    if (query.types.size) facets.push([...query.types].join("/"));
    if (query.subtypes.size) facets.push([...query.subtypes].join("/"));
    if (query.archipelagos.size) facets.push("in " + [...query.archipelagos].join("/"));
    if (query.features.size) facets.push("with " + [...query.features].join(" + "));
    if (query.near) facets.push("within " + Math.round(query.near.radiusKm) + " km of " + query.near.name);
    const facetStr = facets.length ? " " + facets.join(" ") : "";
    if (n === 0) return { answer: `I couldn't find any islands${facetStr}.`, results: [] };
    return {
      answer: `There ${n === 1 ? "is 1 island" : `are ${_CHAT_NUMBER_FMT.format(n)} islands`} matching${facetStr}.`,
      results: filtered.slice(0, 6),
    };
  }

  // ----- SUPERLATIVE -----
  if (intent.kind === "superlative") {
    const pool = filtered.length ? filtered : state.islands;
    const sup = _superlativeWinner(pool, intent.which);
    if (!sup) return null;
    const w = sup.winner;
    const where = [];
    if (w.nation) where.push(w.nation);
    if (w.archipelago && w.archipelago !== w.name) where.push(w.archipelago);
    const whereStr = where.length ? ` (${where.join(" · ")})` : "";
    const intro = intent.which.charAt(0).toUpperCase() + intent.which.slice(1);
    return {
      answer: `${intro}: ${w.name}${whereStr} — ${sup.value}.`,
      results: sup.ranking,
    };
  }

  // ----- LOOKUP -----
  if (intent.kind === "lookup") {
    const island = _findIslandByName(intent.name);
    if (!island) {
      return { answer: `I couldn't find an island matching "${intent.name}".`, results: [] };
    }
    const attr = intent.attr;
    let answer;
    if (/(area|size|big|large|wide|long|small)/.test(attr)) {
      const conf = island.areaConfidence === "high" ? "" :
                   island.areaConfidence === "medium" ? " (medium-confidence)" :
                   " — area not available";
      answer = island.areaKm2 != null
        ? `${_islandShortLabel(island)} covers ${_fmtKm2(island.areaKm2)}${conf}.`
        : `We don't have a verified area for ${_islandShortLabel(island)}.`;
    } else if (/(elevation|height|tall|high|peak|summit|highestpoint)/.test(attr)) {
      if (island.highestPointM != null) {
        const name = island.highestPointName ? ` (${island.highestPointName})` : "";
        const conf = island.highestPointConfidence === "estimate" ? " — estimate" : "";
        answer = `${_islandShortLabel(island)} rises to ${_fmtM(island.highestPointM)}${name}${conf}.`;
      } else {
        answer = `We don't have a verified highest point for ${_islandShortLabel(island)}.`;
      }
    } else if (/population/.test(attr)) {
      const p = island.population;
      answer = p == null
        ? `Population of ${_islandShortLabel(island)} is unknown.`
        : p === 0
        ? `${_islandShortLabel(island)} is uninhabited.`
        : `${_islandShortLabel(island)} has a population of about ${_CHAT_NUMBER_FMT.format(p)}.`;
    } else {
      return null;
    }
    return { answer, results: [island] };
  }

  // ----- COMPARE -----
  if (intent.kind === "compare") {
    const a = _findIslandByName(intent.a);
    const b = _findIslandByName(intent.b);
    if (!a || !b) {
      return {
        answer: !a && !b
          ? `I couldn't find islands matching "${intent.a}" or "${intent.b}".`
          : `I couldn't find an island matching "${a ? intent.b : intent.a}".`,
        results: [a, b].filter(Boolean),
      };
    }
    const lines = [];
    if (a.areaKm2 != null && b.areaKm2 != null) {
      const ratio = (a.areaKm2 / b.areaKm2).toFixed(2);
      const bigger = a.areaKm2 > b.areaKm2 ? a : b;
      lines.push(
        `${a.name} is ${_fmtKm2(a.areaKm2)} · ${b.name} is ${_fmtKm2(b.areaKm2)}` +
        ` — ${bigger.name} is ${a.areaKm2 > b.areaKm2 ? ratio + "×" : (1/ratio).toFixed(2) + "×"} larger.`,
      );
    }
    if (a.highestPointM != null && b.highestPointM != null) {
      const taller = a.highestPointM > b.highestPointM ? a : b;
      lines.push(
        `Highest points: ${a.name} ${_fmtM(a.highestPointM)} · ${b.name} ${_fmtM(b.highestPointM)}` +
        ` — ${taller.name} is higher.`,
      );
    }
    if (a.population != null && b.population != null) {
      lines.push(
        `Population: ${a.name} ${_CHAT_NUMBER_FMT.format(a.population)} · ` +
        `${b.name} ${_CHAT_NUMBER_FMT.format(b.population)}.`,
      );
    }
    if (!lines.length) {
      lines.push(`Comparing ${a.name} and ${b.name}: not enough data on both islands.`);
    }
    return { answer: lines.join(" "), results: [a, b] };
  }

  // ----- AGGREGATE -----
  if (intent.kind === "aggregate") {
    const pool = filtered.length ? filtered : state.islands;
    const attr = intent.attr;
    if (attr === "area" || attr === "size") {
      let total = 0; let n = 0;
      for (const i of pool) {
        if (typeof i.areaKm2 === "number" && i.areaKm2 > 0) { total += i.areaKm2; n++; }
      }
      return {
        answer: `Total area of ${_CHAT_NUMBER_FMT.format(n)} matching islands: ${_fmtKm2(total)}.`,
        results: pool.slice().sort((x, y) => (y.areaKm2 || 0) - (x.areaKm2 || 0)).slice(0, 5),
      };
    }
    if (attr === "population") {
      let total = 0; let n = 0;
      for (const i of pool) {
        if (typeof i.population === "number" && i.population > 0) { total += i.population; n++; }
      }
      return {
        answer: `Combined population of ${_CHAT_NUMBER_FMT.format(n)} inhabited matching islands: ${_CHAT_NUMBER_FMT.format(total)}.`,
        results: pool.slice().sort((x, y) => (y.population || 0) - (x.population || 0)).slice(0, 5),
      };
    }
  }
  return null;
}

function composeChatResponse({ query, results, total }) {
  if (!results.length) {
    const hints = [];
    if (query.nearUnresolved) {
      return (
        `I couldn't find “${query.nearUnresolved}” in the atlas gazetteer. ` +
        "Try a major ferry town — Oban, Mallaig, Ullapool, Stornoway, Penzance, Holyhead — " +
        "or ask without a place filter."
      );
    }
    if (!query.nations.size) hints.push("a nation (Scotland, Wales, …)");
    if (!query.types.size) hints.push("a type (sea, lake, river)");
    if (!query.features.size && !query.semanticTags.size) {
      hints.push("a feature (mountains, castle, ferry, puffins)");
    }
    return (
      "I couldn't find any matches. Try mentioning " +
      hints.join(", ") +
      "."
    );
  }
  const parts = [];
  if (query.recommendationIntent) {
    const whereBits = [];
    if (query.archipelagos.size) {
      whereBits.push([...query.archipelagos].join(" · "));
    }
    if (query.nations.size) {
      whereBits.push([...query.nations].join("/"));
    }
    const whereStr = whereBits.length ? ` in **${whereBits.join(" · ")}**` : "";
    parts.push(
      `Here are **${results.length}** sea-island picks${whereStr} — larger or inhabited places with solid atlas coverage (photos, descriptions, or ferries).`,
    );
  }
  const totalLabel = total === 1 ? "1 match" : `${total.toLocaleString()} matches`;
  const facets = [];
  if (query.nations.size) facets.push([...query.nations].join("/"));
  if (query.types.size) facets.push([...query.types].map((t) => t + " islands").join("/"));
  else facets.push("islands");
  if (query.archipelagos.size) facets.push("in " + [...query.archipelagos].join("/"));
  if (query.semanticTags.size) facets.push("tagged " + [...query.semanticTags].join(" + "));
  if (query.features.size) facets.push("with " + [...query.features].join(" + "));
  if (query.near) {
    const km = Math.round(query.near.radiusKm);
    facets.push(`within ${km} km of ${query.near.name}`);
  }
  if (query.sort) facets.push("(sorted by " + query.sort.sortBy + ")");
  if (!query.recommendationIntent) {
    parts.push(`Found ${totalLabel} for ${facets.join(" ")}.`);
    if (results.length < total) {
      parts.push(`Showing the top ${results.length}.`);
    }
  } else if (total > results.length) {
    parts.push(
      `${total.toLocaleString()} islands passed the filters; these ${results.length} rank highest for visitor appeal in the atlas data.`,
    );
  }
  return parts.join(" ");
}

const chatEls = {
  launcher: document.getElementById("chat-launcher"),
  panel: document.getElementById("chat-panel"),
  close: document.getElementById("chat-close"),
  form: document.getElementById("chat-form"),
  input: document.getElementById("chat-input"),
  messages: document.getElementById("chat-messages"),
};

function chatOpen() {
  chatEls.panel.classList.add("is-open");
  chatEls.panel.setAttribute("aria-hidden", "false");
  chatEls.launcher.setAttribute("aria-expanded", "true");
  chatEls.launcher.classList.add("is-hidden");
  if (mobileNav.isActive()) mobileNav.setView("ask", { skipChatSync: true });
  ensureChatTagVocabulary();
  setTimeout(() => chatEls.input.focus(), 50);
  if (!chatEls.messages.dataset.bootstrapped) {
    chatRenderBot(
      "Hi! Ask me anything about British or Scottish islands — counts, sizes, peaks, comparisons, or what's near a place. " +
        "I'll answer directly and surface the islands you mean. Everything runs locally; no data leaves your browser.",
      { suggestions: CHAT_SUGGESTIONS }
    );
    chatEls.messages.dataset.bootstrapped = "1";
  }
}

function chatClose() {
  chatEls.panel.classList.remove("is-open");
  chatEls.panel.setAttribute("aria-hidden", "true");
  chatEls.launcher.setAttribute("aria-expanded", "false");
  chatEls.launcher.classList.remove("is-hidden");
  if (mobileNav.isActive() && mobileNav.view === "ask") {
    mobileNav.setView("map", { skipChatSync: true });
  }
}

function chatAppend(node) {
  chatEls.messages.appendChild(node);
  chatEls.messages.scrollTop = chatEls.messages.scrollHeight;
}

function chatRenderUser(text) {
  const div = document.createElement("div");
  div.className = "chat-msg chat-msg--user";
  div.textContent = text;
  chatAppend(div);
}

// Render a bot reply as safe HTML.
//
// We HTML-escape *first*, then re-introduce a tiny, known subset of
// inline markup:
//   - `**bold**`   → <strong>bold</strong>
//   - `*italic*`   → <em>italic</em>
//   - lines starting with `- ` → grouped <ul><li>…</li></ul>
//   - single newline → <br>, blank line → paragraph break
// Anything else stays escaped, so the model can't smuggle raw HTML.
function chatFormatBotText(raw) {
  if (!raw) return "";
  let s = escapeHtml(String(raw));
  s = s.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  const lines = s.split("\n");
  const out = [];
  let textBuf = [];
  let listBuf = [];
  const flushText = () => {
    if (textBuf.length) {
      out.push(textBuf.join("<br>"));
      textBuf = [];
    }
  };
  const flushList = () => {
    if (listBuf.length) {
      out.push(
        '<ul class="chat-msg__list"><li>' +
          listBuf.join("</li><li>") +
          "</li></ul>"
      );
      listBuf = [];
    }
  };
  for (const line of lines) {
    const m = /^\s*-\s+(.+)$/.exec(line);
    if (m) {
      flushText();
      listBuf.push(m[1]);
    } else {
      flushList();
      textBuf.push(line);
    }
  }
  flushText();
  flushList();
  return out.join("");
}

function chatRenderBot(text, { suggestions, results, query, badge } = {}) {
  const div = document.createElement("div");
  div.className = "chat-msg chat-msg--bot";
  div.innerHTML = chatFormatBotText(text);

  // Optional badge ("AI", etc.) appended to the bot's bubble.
  if (badge) {
    const b = document.createElement("span");
    b.className = "chat-msg__badge";
    b.textContent = badge;
    b.title = "Generated with AI from local atlas data";
    div.appendChild(b);
  }

  if (suggestions && suggestions.length) {
    const sug = document.createElement("div");
    sug.className = "chat-suggestions";
    for (const s of suggestions) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = s;
      b.addEventListener("click", () => chatSubmit(s));
      sug.appendChild(b);
    }
    div.appendChild(sug);
  }

  if (results && results.length) {
    const list = document.createElement("div");
    list.className = "chat-results";
    let renderedCount = 0;
    for (const r of results) {
      // Defensive: skip null entries or entries without an island record.
      // Render every other entry inside its own try/catch so a single bad
      // record can never blank out the whole reply.
      if (!r) continue;
      const isl = r && r.island;
      if (!isl || typeof isl !== "object" || !isl.id) continue;
      try {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chat-result";
        btn.dataset.id = isl.id;

        const thumb = document.createElement("div");
        thumb.className = "chat-result__thumb";
        const imgUrl =
          isl.image ||
          (Array.isArray(isl.images) && isl.images[0] && isl.images[0].url) ||
          "";
        if (imgUrl) {
          thumb.style.backgroundImage = `url('${String(imgUrl).replace(/'/g, "\\'")}')`;
        } else {
          thumb.classList.add("chat-result__thumb--empty");
          thumb.textContent = "◍";
        }
        btn.appendChild(thumb);

        const body = document.createElement("div");
        body.className = "chat-result__body";
        const title = document.createElement("strong");
        title.textContent = isl.name || "(unnamed)";
        body.appendChild(title);
        const meta = document.createElement("span");
        meta.className = "chat-result__meta";
        const parts = [];
        if (isl.nation) parts.push(isl.nation);
        if (isl.type) {
          parts.push(
            isl.subtype ? `${isl.subtype} (${isl.type})` : `${isl.type} island`,
          );
        }
        if (isl.parentWaterBody && isl.parentWaterBody.name) {
          parts.push(isl.parentWaterBody.name);
        }
        if (typeof isl.areaKm2 === "number" && isl.areaKm2 > 0 &&
            typeof formatArea === "function") {
          parts.push(formatArea(isl.areaKm2));
        }
        if (query && query.near &&
            Number.isFinite(isl.lat) && Number.isFinite(isl.lng)) {
          const km = chatHaversineKm(query.near.lat, query.near.lng, isl.lat, isl.lng);
          parts.push(`${Math.round(km)} km from ${query.near.name}`);
        }
        meta.textContent = parts.join(" · ");
        body.appendChild(meta);

        // Source cross-reference: if there's a primary image with a
        // sourcePageUrl, render a tiny clickable link so the user can
        // verify where the photo came from. Mirrors the detail panel.
        const imgs = Array.isArray(isl.images) ? isl.images : [];
        const primaryImg = imgs.find((x) => x && x.primary) || imgs[0] || null;
        if (primaryImg && primaryImg.sourcePageUrl) {
          const srcLink = document.createElement("a");
          srcLink.className = "chat-result__source";
          srcLink.href = primaryImg.sourcePageUrl;
          srcLink.target = "_blank";
          srcLink.rel = "noopener";
          const labelMap =
            (typeof SOURCE_LABELS !== "undefined" && SOURCE_LABELS) || {};
          srcLink.textContent =
            (labelMap[primaryImg.source] || primaryImg.source || "source") +
            " ↗";
          srcLink.addEventListener("click", (e) => e.stopPropagation());
          body.appendChild(srcLink);
        }

        btn.appendChild(body);

        const access = chatAccessForIsland(isl);
        if (access.causeway?.notes) {
          const cw = document.createElement("p");
          cw.className = "chat-result__causeway";
          cw.textContent = access.causeway.notes;
          body.appendChild(cw);
        }
        if (access.ferryRoutes.length) {
          const ferryWrap = document.createElement("div");
          ferryWrap.className = "chat-result__ferries";
          for (const route of access.ferryRoutes.slice(0, 2)) {
            const row = document.createElement("div");
            row.className = "chat-ferry-snippet";
            const op = route.operator || "Ferry";
            const from = route.from || "mainland";
            const to = route.to || "island";
            const season = route.seasonality ? ` · ${route.seasonality}` : "";
            row.textContent = `${op}: ${from} → ${to}${season}`;
            ferryWrap.appendChild(row);
          }
          body.appendChild(ferryWrap);
        }

        const actions = document.createElement("div");
        actions.className = "chat-result__actions";
        const mapBtn = document.createElement("button");
        mapBtn.type = "button";
        mapBtn.className = "chat-result__map-btn";
        mapBtn.textContent = "Show on map";
        mapBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          showIslandOnMap(isl.id);
          if (window.innerWidth <= 640) chatClose();
        });
        const detailBtn = document.createElement("button");
        detailBtn.type = "button";
        detailBtn.className = "chat-result__detail-btn";
        detailBtn.textContent = "Open profile";
        detailBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          focusIsland(isl.id);
          if (window.innerWidth <= 640) chatClose();
        });
        actions.appendChild(mapBtn);
        actions.appendChild(detailBtn);
        body.appendChild(actions);

        list.appendChild(btn);
        renderedCount++;
      } catch (cardErr) {
        // Skip a single bad card without poisoning the rest of the reply.
        console.warn("[chat] skipped result card", isl && isl.id, cardErr);
      }
    }
    if (renderedCount > 0) div.appendChild(list);
  }

  chatAppend(div);
}

// ---------- Optional LLM layer ----------
//
// Hybrid RAG: the local engine is always the source of truth.  When
// "smart answers" is enabled, we additionally pass the question + the top
// ~12 candidate islands + recent chat history to the user's chosen LLM
// (OpenAI or Anthropic, BYOK).  The LLM is *only* allowed to use the
// candidates we hand it; it returns JSON with an answer, the island IDs
// it cited, and three short follow-up suggestions.  Everything stays
// opt-in and the API key never leaves localStorage.

const LLM_PROVIDERS = {
  openai: {
    label: "OpenAI",
    models: [
      { id: "gpt-4o-mini", label: "gpt-4o-mini · fast & cheap (default)" },
      { id: "gpt-4o", label: "gpt-4o · best reasoning" },
      { id: "gpt-4.1-mini", label: "gpt-4.1-mini" },
    ],
    defaultModel: "gpt-4o-mini",
    endpoint: "https://api.openai.com/v1/chat/completions",
  },
  anthropic: {
    label: "Anthropic",
    models: [
      { id: "claude-3-5-haiku-latest", label: "claude-3-5-haiku · fast & cheap (default)" },
      { id: "claude-3-5-sonnet-latest", label: "claude-3-5-sonnet · best reasoning" },
    ],
    defaultModel: "claude-3-5-haiku-latest",
    endpoint: "https://api.anthropic.com/v1/messages",
  },
};

const LLM_HISTORY_TURNS = 6;
const LLM_CANDIDATE_LIMIT = 12;

function chatLLMGetSettings() {
  try {
    const raw = localStorage.getItem("chatAI");
    const obj = raw ? JSON.parse(raw) : {};
    return {
      enabled: !!obj.enabled,
      provider: obj.provider || "openai",
      model: obj.model || LLM_PROVIDERS.openai.defaultModel,
      apiKey: obj.apiKey || "",
    };
  } catch (_) {
    return { enabled: false, provider: "openai", model: "gpt-4o-mini", apiKey: "" };
  }
}

function chatLLMSaveSettings(patch) {
  const current = chatLLMGetSettings();
  const next = Object.assign({}, current, patch);
  try {
    localStorage.setItem("chatAI", JSON.stringify(next));
  } catch (_) {
    /* non-fatal */
  }
  chatLLMRefreshUI();
  return next;
}

// Build a richer LLM-friendly representation of each candidate island.
// We give the model enough narrative context to write naturally without
// blowing the prompt budget — descriptions trimmed at ~480 chars,
// history/transport at ~340.  Empty fields are dropped so the model isn't
// tempted to comment on missing data.
function chatLLMSerialiseIsland(isl) {
  if (!isl || typeof isl !== "object") return null;
  const trim = (s, n) =>
    typeof s === "string" && s.trim()
      ? s.length > n
        ? s.slice(0, n - 1).trim() + "…"
        : s.trim()
      : null;
  const dropEmpty = (obj) => {
    const out = {};
    for (const k of Object.keys(obj)) {
      const v = obj[k];
      if (v == null) continue;
      if (typeof v === "string" && v === "") continue;
      if (Array.isArray(v) && v.length === 0) continue;
      out[k] = v;
    }
    return out;
  };
  return dropEmpty({
    id: isl.id,
    name: isl.name,
    nation: isl.nation,
    type: isl.type,
    subtype: isl.subtype || null,
    archipelago: isl.archipelago || null,
    parentWaterBody:
      isl.parentWaterBody && isl.parentWaterBody.name
        ? isl.parentWaterBody.name
        : null,
    lat: typeof isl.lat === "number" ? +isl.lat.toFixed(3) : null,
    lng: typeof isl.lng === "number" ? +isl.lng.toFixed(3) : null,
    areaKm2: typeof isl.areaKm2 === "number" ? +isl.areaKm2.toFixed(3) : null,
    areaConfidence: isl.areaConfidence || null,
    highestPointM:
      typeof isl.highestPointM === "number" ? Math.round(isl.highestPointM) : null,
    highestPointName: isl.highestPointName || null,
    population: typeof isl.population === "number" ? isl.population : null,
    inhabited:
      typeof isl.population === "number" ? isl.population > 0 : null,
    tidal: isl.tidal || null,
    shortDescription: trim(isl.shortDescription, 480),
    geography: trim(isl.geography, 340),
    history: trim(isl.history, 340),
    transport: trim(isl.transport, 340),
    accommodation: trim(isl.accommodation, 240),
    tags: Array.isArray(isl.tags) ? isl.tags.slice(0, 16) : [],
    descriptionSource: isl.descriptionSource || null,
    descriptionConfidence: isl.descriptionConfidence || null,
    hasPhoto: !!(isl.image || (Array.isArray(isl.images) && isl.images[0])),
    wikipedia: isl.wikipedia || null,
    ...chatAccessForIsland(isl),
  });
}

// Atlas-level summary so the LLM understands what data set it's drawing
// from.  Computed once per page-load and reused; recounting 6,776
// records every turn would be wasteful.
let _atlasSummaryCache = null;
function chatLLMAtlasSummary() {
  if (_atlasSummaryCache) return _atlasSummaryCache;
  const islands = state.islands || [];
  const byNation = {};
  const byType = {};
  let inhabitedCount = 0;
  let withAreaCount = 0;
  let withPeakCount = 0;
  let largestArea = 0;
  let highestPeak = 0;
  for (const i of islands) {
    if (!i) continue;
    if (i.nation) byNation[i.nation] = (byNation[i.nation] || 0) + 1;
    if (i.type) byType[i.type] = (byType[i.type] || 0) + 1;
    if (typeof i.population === "number" && i.population > 0) inhabitedCount++;
    if (typeof i.areaKm2 === "number" && i.areaKm2 > 0) {
      withAreaCount++;
      if (i.areaKm2 > largestArea) largestArea = i.areaKm2;
    }
    if (typeof i.highestPointM === "number") {
      withPeakCount++;
      if (i.highestPointM > highestPeak) highestPeak = i.highestPointM;
    }
  }
  _atlasSummaryCache = {
    totalIslands: islands.length,
    inhabitedCount,
    withVerifiedArea: withAreaCount,
    withVerifiedPeak: withPeakCount,
    largestAreaKm2: +largestArea.toFixed(0),
    highestPeakM: Math.round(highestPeak),
    byNation,
    byType,
  };
  return _atlasSummaryCache;
}

const LLM_SYSTEM_PROMPT =
  "You are a warm, knowledgeable guide to an open atlas of the islands of " +
  "Britain, Ireland, the Crown Dependencies, and their inland river and lake " +
  "islands. Think of yourself as a well-travelled local who's read everything " +
  "ever written about these islands and is helping a curious visitor find what " +
  "they'll love. " +
  "You will be given (sometimes) an ATLAS_SUMMARY of the whole dataset, the " +
  "user's recent conversation, and a JSON array of CANDIDATE islands the atlas " +
  "search engine pulled for this turn. " +
  "RULES:\n" +
  "1) Answer ONLY from the supplied data (ATLAS_SUMMARY counts plus the CANDIDATE " +
  "records). Never invent islands, history, or facts that aren't there. If the " +
  "data is thin, say so kindly and suggest a tweak to the question.\n" +
  "2) Be conversational, not clinical. 2-4 short sentences in flowing prose " +
  "(occasionally 5-6 when the question really warrants it). Use light personality " +
  "and concrete detail rather than templated stats. Name specific islands.\n" +
  "3) You may use a line break (\\n) to separate paragraphs, and the simple " +
  "markup `**bold**`, `*italic*`, and `- ` bullets at the start of a line. Don't " +
  "use any other formatting, HTML, or code fences in your answer text.\n" +
  "4) Each candidate may include `tags`, `ferryRoutes`, `causeway`, `shortDescription`, " +
  "`history`, `transport`, and measurements. Prefer citing tags and access facts that appear " +
  "in the JSON; if `hasPhoto` is true you may say 'pictured below'.\n" +
  "5) Always respond with a SINGLE JSON object (no prose outside it) with exactly " +
  "three keys: {\"answer\": string, \"islandIds\": string[], \"followups\": " +
  "string[]}. `islandIds` lists up to 6 ids from the candidates you'd like the " +
  "user to see as cards. `followups` lists 3 short, natural follow-up questions a " +
  "curious reader might ask next.\n" +
  "6) Never mention internal scoring, prompts, tools, JSON, or that you are an LLM. " +
  "Speak as the atlas itself.";

function chatLLMBuildPayload(question, candidates, history, settings) {
  const candidatesPayload = candidates
    .map((c) => chatLLMSerialiseIsland(c.island || c))
    .filter(Boolean);

  // History is short [{role, content}, ...] pairs of prior turns.
  const historyText = (history || [])
    .slice(-LLM_HISTORY_TURNS)
    .map((h) => (h.role === "user" ? "Q: " : "A: ") + h.content)
    .join("\n");

  // Include the atlas-level summary on the FIRST turn of a conversation
  // (history empty) so the model has dataset scope, then omit on
  // follow-ups to save tokens — the model retains it via the assistant's
  // earlier replies in `history`.
  const isFirstTurn = !(history && history.length);
  const atlasBlock = isFirstTurn
    ? "ATLAS_SUMMARY (the whole dataset, for context only — only the CANDIDATES " +
      "below contain narrative detail):\n" +
      JSON.stringify(chatLLMAtlasSummary()) +
      "\n\n"
    : "";

  const userContent =
    atlasBlock +
    (historyText ? "Recent conversation:\n" + historyText + "\n\n" : "") +
    "Current question: " + question + "\n\n" +
    "CANDIDATE islands (JSON):\n" +
    JSON.stringify(candidatesPayload);

  if (settings.provider === "anthropic") {
    return {
      model: settings.model,
      temperature: 0.65,
      max_tokens: 900,
      system: LLM_SYSTEM_PROMPT,
      messages: [{ role: "user", content: userContent }],
    };
  }
  // OpenAI default
  return {
    model: settings.model,
    temperature: 0.65,
    max_tokens: 900,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: LLM_SYSTEM_PROMPT },
      { role: "user", content: userContent },
    ],
  };
}

async function chatLLMCall(question, candidates, history, settings) {
  const provider = LLM_PROVIDERS[settings.provider];
  if (!provider) throw new Error("Unknown provider: " + settings.provider);
  if (!settings.apiKey) throw new Error("No API key configured");

  const body = chatLLMBuildPayload(question, candidates, history, settings);
  const headers = { "Content-Type": "application/json" };
  if (settings.provider === "openai") {
    headers["Authorization"] = "Bearer " + settings.apiKey;
  } else if (settings.provider === "anthropic") {
    headers["x-api-key"] = settings.apiKey;
    headers["anthropic-version"] = "2023-06-01";
    // Anthropic requires this header for direct browser requests.
    headers["anthropic-dangerous-direct-browser-access"] = "true";
  }

  const resp = await fetch(provider.endpoint, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = "";
    try {
      const errBody = await resp.json();
      detail = errBody.error?.message || JSON.stringify(errBody).slice(0, 240);
    } catch (_) {
      detail = await resp.text().catch(() => "");
    }
    throw new Error(`HTTP ${resp.status} from ${provider.label}: ${detail}`);
  }
  const data = await resp.json();

  // Extract the text payload, handling both API shapes.
  let raw = "";
  if (settings.provider === "openai") {
    raw = data.choices?.[0]?.message?.content || "";
  } else {
    raw = (data.content || [])
      .map((b) => (b && b.type === "text" ? b.text : ""))
      .join("");
  }

  // Parse the JSON response.  Be forgiving: strip code fences if the model
  // wrapped its reply in ```json … ``` despite instructions.
  let parsed;
  try {
    const cleaned = raw
      .replace(/^```(?:json)?\s*/i, "")
      .replace(/```\s*$/i, "")
      .trim();
    parsed = JSON.parse(cleaned);
  } catch (e) {
    throw new Error("LLM returned non-JSON: " + raw.slice(0, 200));
  }
  if (!parsed || typeof parsed.answer !== "string") {
    throw new Error("LLM JSON missing `answer` field");
  }
  return {
    answer: parsed.answer.trim(),
    islandIds: Array.isArray(parsed.islandIds) ? parsed.islandIds.slice(0, 6) : [],
    followups: Array.isArray(parsed.followups) ? parsed.followups.slice(0, 3) : [],
  };
}

async function chatLLMTest(settings) {
  // A tiny call with the cheapest possible payload, just to verify the key.
  const probe = {
    answer: "ok",
    islandIds: [],
    followups: [],
  };
  const fakeCands = [chatLLMSerialiseIsland(state.islands?.[0] || {})];
  const res = await chatLLMCall(
    "Reply with the JSON object: " + JSON.stringify(probe),
    fakeCands.filter(Boolean),
    [],
    settings,
  );
  return res;
}

// ---------- Chat settings UI wiring ----------

const chatSettingsEls = {
  toggle: () => document.getElementById("chat-settings-toggle"),
  panel: () => document.getElementById("chat-settings"),
  aiToggle: () => document.getElementById("chat-ai-toggle"),
  provider: () => document.getElementById("chat-ai-provider"),
  model: () => document.getElementById("chat-ai-model"),
  key: () => document.getElementById("chat-ai-key"),
  test: () => document.getElementById("chat-ai-test"),
  clear: () => document.getElementById("chat-ai-clear"),
  status: () => document.getElementById("chat-ai-status"),
  modeSub: () => document.getElementById("chat-mode-sub"),
};

function chatLLMRefreshUI() {
  const s = chatLLMGetSettings();
  const toggleBtn = chatSettingsEls.toggle();
  const modeSub = chatSettingsEls.modeSub();
  const btnLabel = document.getElementById("chat-ai-btn-label");
  const keyLink = document.getElementById("chat-ai-key-link");
  if (toggleBtn) toggleBtn.classList.toggle("is-on", !!s.enabled && !!s.apiKey);
  if (btnLabel) {
    if (s.enabled && s.apiKey) {
      btnLabel.textContent = `AI: ${LLM_PROVIDERS[s.provider]?.label || s.provider}`;
    } else if (s.apiKey) {
      btnLabel.textContent = "AI off";
    } else {
      btnLabel.textContent = "Set up AI";
    }
  }
  if (keyLink) {
    keyLink.href =
      s.provider === "anthropic"
        ? "https://console.anthropic.com/settings/keys"
        : "https://platform.openai.com/api-keys";
  }
  if (modeSub) {
    if (s.enabled && s.apiKey) {
      modeSub.textContent =
        `AI mode · sending questions to ${LLM_PROVIDERS[s.provider]?.label || s.provider}.`;
    } else if (s.enabled && !s.apiKey) {
      modeSub.textContent =
        "AI mode is on but no key is set. Open settings to add one.";
    } else {
      modeSub.textContent = "Local mode · nothing leaves your browser.";
    }
  }
}

function chatLLMPopulateModels(provider) {
  const sel = chatSettingsEls.model();
  if (!sel) return;
  const opts = LLM_PROVIDERS[provider]?.models || [];
  sel.innerHTML = "";
  for (const m of opts) {
    const o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.label;
    sel.appendChild(o);
  }
}

function chatLLMInitSettingsUI() {
  const s = chatLLMGetSettings();
  const aiToggle = chatSettingsEls.aiToggle();
  const provider = chatSettingsEls.provider();
  const key = chatSettingsEls.key();
  const test = chatSettingsEls.test();
  const clear = chatSettingsEls.clear();
  const toggleBtn = chatSettingsEls.toggle();
  const panel = chatSettingsEls.panel();
  if (!aiToggle || !provider || !key) return;

  aiToggle.checked = s.enabled;
  provider.value = s.provider;
  chatLLMPopulateModels(s.provider);
  const model = chatSettingsEls.model();
  if (model) model.value = s.model;
  if (s.apiKey) key.placeholder = "•••••• (saved in this browser)";

  aiToggle.addEventListener("change", () => {
    chatLLMSaveSettings({ enabled: aiToggle.checked });
  });
  provider.addEventListener("change", () => {
    const def = LLM_PROVIDERS[provider.value]?.defaultModel;
    chatLLMPopulateModels(provider.value);
    chatLLMSaveSettings({ provider: provider.value, model: def });
    const m = chatSettingsEls.model();
    if (m) m.value = def;
  });
  const modelSel = chatSettingsEls.model();
  if (modelSel) {
    modelSel.addEventListener("change", () => {
      chatLLMSaveSettings({ model: modelSel.value });
    });
  }
  key.addEventListener("change", () => {
    const v = key.value.trim();
    chatLLMSaveSettings({ apiKey: v });
    if (v) {
      key.value = "";
      key.placeholder = "•••••• (saved in this browser)";
    }
  });
  test.addEventListener("click", async () => {
    const status = chatSettingsEls.status();
    if (!status) return;
    const live = chatLLMGetSettings();
    if (!live.apiKey) {
      status.className = "chat-settings__status is-err";
      status.textContent = "Add an API key first.";
      return;
    }
    status.className = "chat-settings__status";
    status.textContent = "Testing…";
    try {
      await chatLLMTest(live);
      status.className = "chat-settings__status is-ok";
      status.textContent = "Connection OK — AI is ready.";
    } catch (err) {
      status.className = "chat-settings__status is-err";
      status.textContent = "Test failed: " + (err.message || err);
    }
  });
  clear.addEventListener("click", () => {
    chatLLMSaveSettings({ apiKey: "" });
    key.value = "";
    key.placeholder = "sk-… or sk-ant-…";
    const status = chatSettingsEls.status();
    if (status) {
      status.className = "chat-settings__status";
      status.textContent = "Key cleared.";
    }
  });
  if (toggleBtn && panel) {
    toggleBtn.addEventListener("click", () => {
      const open = panel.hasAttribute("hidden") === false;
      if (open) {
        panel.setAttribute("hidden", "");
        panel.setAttribute("aria-hidden", "true");
      } else {
        panel.removeAttribute("hidden");
        panel.setAttribute("aria-hidden", "false");
      }
    });
  }
  chatLLMRefreshUI();
}

// Initialise once the DOM is parsed.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", chatLLMInitSettingsUI);
} else {
  chatLLMInitSettingsUI();
}

// ---------- Chat submit ----------

// Recent conversation history for AI-mode follow-ups.  Capped at
// LLM_HISTORY_TURNS * 2 entries (alternating user / assistant).
const chatHistory = [];

function chatSubmit(text) {
  const t = (text || "").trim();
  if (!t) return;
  chatRenderUser(t);
  chatEls.input.value = "";

  // Reflect the latest query in the URL so it's bookmarkable / shareable.
  // We use replaceState to avoid stuffing the back-button history.
  try {
    const url = new URL(window.location.href);
    url.searchParams.set("ask", t);
    window.history.replaceState(null, "", url.toString());
  } catch (_) {
    /* non-fatal */
  }

  const thinking = document.createElement("div");
  thinking.className = "chat-msg chat-msg--system";
  thinking.textContent = "Searching the atlas…";
  chatAppend(thinking);

  // If the query mentions ferries, wait for the ferry index to load so
  // proper structured filtering kicks in. Falls back to the text-based
  // ferry feature heuristic when the index can't be loaded.
  const probe = parseChatQuery(t);
  const prep = Promise.all([
    loadFerries(),
    loadCauseways(),
    ensureChatTagVocabulary(),
  ]);

  // Wrap the whole pipeline in try/catch so a single thrown error can never
  // leave the user staring at a perpetual "Searching the atlas…" dot.
  prep.then(async () => {
    try {
      const r = searchChatIslands(t, LLM_CANDIDATE_LIMIT);
      thinking.remove();

      const aiSettings = chatLLMGetSettings();
      const aiActive = aiSettings.enabled && aiSettings.apiKey && r.results.length > 0;

      if (aiActive) {
        // Show a different spinner while the LLM is thinking.
        const aiThinking = document.createElement("div");
        aiThinking.className = "chat-msg chat-msg--system";
        aiThinking.textContent = `Thinking with ${LLM_PROVIDERS[aiSettings.provider]?.label || "AI"}…`;
        chatAppend(aiThinking);
        try {
          const llm = await chatLLMCall(t, r.results, chatHistory, aiSettings);
          aiThinking.remove();

          // Resolve cited island ids back to records; fall back to the
          // local top results if the LLM cited nothing usable.
          const cited = (llm.islandIds || [])
            .map((id) => state.islands.find((i) => i && i.id === id))
            .filter(Boolean);
          const wrapped = (cited.length ? cited : r.results.slice(0, 5).map((x) => x.island))
            .map((isl) => ({ island: isl }));

          chatHistory.push({ role: "user", content: t });
          chatHistory.push({ role: "assistant", content: llm.answer });
          while (chatHistory.length > LLM_HISTORY_TURNS * 2) chatHistory.shift();

          chatRenderBot(llm.answer, {
            results: wrapped,
            query: r.query,
            suggestions: llm.followups.length ? llm.followups : undefined,
            badge: "AI",
          });
          return;
        } catch (llmErr) {
          aiThinking.remove();
          console.warn("[chat] LLM call failed; falling back to local engine", llmErr);
          // Tell the user once that AI failed, then continue with local.
          const note = document.createElement("div");
          note.className = "chat-msg chat-msg--system";
          note.textContent =
            "AI is unreachable (" + (llmErr.message || "error") +
            ") — showing local results instead.";
          chatAppend(note);
          // Fall through to local engine below.
        }
      }

      // Local engine (also the fallback path when AI is off or failed).
      // Direct-answer pass: if the question is a count/superlative/lookup/
      // comparison/aggregate, prepend a one-sentence factual answer and
      // surface the most relevant islands for that answer.  Defensive:
      // if intent detection or answer-building throws, just fall through
      // to the standard search-results path rather than blanking the
      // whole reply.
      let intent = null;
      let direct = null;
      try {
        intent = detectAnswerIntent(t);
        if (intent) direct = answerIntent(intent, r.query);
      } catch (intentErr) {
        console.warn("[chat] answer-engine error", intentErr);
        intent = null;
        direct = null;
      }
      if (direct) {
        // chatRenderBot expects [{island, score}, ...]; answerIntent
        // returns plain island objects, so wrap them.  Fall back to the
        // already-wrapped r.results when the direct branch has none.
        const wrappedDirect = (direct.results || []).map((x) => ({
          island: x,
        }));
        const results = wrappedDirect.length ? wrappedDirect : r.results;
        const tail = r.results.length && intent && intent.kind === "count"
          ? "" // count answer already says "there are N"
          : results.length
          ? ""
          : " " + composeChatResponse(r);
        chatRenderBot(direct.answer + tail, { results, query: r.query });
        return;
      }

      if (!r.results.length) {
        chatRenderBot(composeChatResponse(r), { suggestions: CHAT_SUGGESTIONS });
      } else {
        chatRenderBot(composeChatResponse(r), { results: r.results, query: r.query });
      }
    } catch (err) {
      thinking.remove();
      console.error("[chat] pipeline error", err);
      chatRenderBot(
        "Sorry — something went wrong while searching. Try rephrasing, or pick a suggestion below.",
        { suggestions: CHAT_SUGGESTIONS },
      );
    }
  }).catch((err) => {
    thinking.remove();
    console.error("[chat] prep promise rejected", err);
    chatRenderBot(
      "Sorry — couldn't load the ferry data needed for that question. Try a different question.",
      { suggestions: CHAT_SUGGESTIONS },
    );
  });
}

// If the page is opened with ?ask=…, auto-open the chat and run that query.
// Waits until islands have loaded so we have data to search against.
function chatAutoLoadFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    const ask = params.get("ask");
    if (!ask) return;
    const run = () => {
      chatOpen();
      // Give the bootstrap greeting a tick to render before the user message.
      setTimeout(() => chatSubmit(ask), 60);
    };
    if (state.islands && state.islands.length) {
      run();
    } else {
      // Poll briefly for data; loadIslands() pushes to state.islands on success.
      let tries = 0;
      const t = setInterval(() => {
        tries++;
        if (state.islands && state.islands.length) {
          clearInterval(t);
          run();
        } else if (tries > 200) {
          clearInterval(t); // give up after ~10s
        }
      }, 50);
    }
  } catch (_) {
    /* non-fatal */
  }
}

if (chatEls.launcher) {
  chatEls.launcher.addEventListener("click", chatOpen);
  chatEls.close.addEventListener("click", chatClose);
  chatEls.form.addEventListener("submit", (e) => {
    e.preventDefault();
    chatSubmit(chatEls.input.value);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && chatEls.panel.classList.contains("is-open")) {
      chatClose();
    }
  });
}

// ---------- Boot ----------
const mobileNav = (() => {
  const mq = window.matchMedia("(max-width: 900px)");
  const nav = document.getElementById("mobile-nav");
  const filtersToggle = document.getElementById("filters-toggle");
  let view = "map";
  let mapSizeTimer = 0;

  function isActive() {
    return mq.matches;
  }

  function syncMapSize() {
    if (typeof map === "undefined" || !map) return;
    if (mapSizeTimer) window.clearTimeout(mapSizeTimer);
    mapSizeTimer = window.setTimeout(() => {
      mapSizeTimer = 0;
      try {
        map.invalidateSize();
      } catch (_) {
        /* ignore */
      }
    }, 180);
  }

  function syncMobileSidebarPanels() {
    const detailOpen = !els.details.hidden;
    els.listSection.hidden = detailOpen;
    document.body.dataset.islandDetail = detailOpen ? "open" : "closed";
    if (!detailOpen) scheduleRenderListWindow();
  }

  function setView(next, { skipChatSync = false } = {}) {
    if (!isActive()) return;
    view = next;
    document.body.dataset.mobileView = next;
    nav?.querySelectorAll(".mobile-nav__btn").forEach((btn) => {
      const active = btn.dataset.mobileView === next;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-current", active ? "page" : "false");
    });
    if (next === "ask") {
      if (!skipChatSync && chatEls.panel && !chatEls.panel.classList.contains("is-open")) {
        chatOpen();
      }
    } else if (!skipChatSync && chatEls.panel?.classList.contains("is-open")) {
      chatClose();
    }
    if (next === "map") {
      if (!els.details.hidden && state.activeId) {
        state.mobileDetailSuspended = true;
        els.details.hidden = true;
        els.listSection.hidden = true;
        document.body.dataset.islandDetail = "suspended";
        updateMapIslandPeek(state.activeId);
      } else {
        hideMapIslandPeek();
      }
    } else {
      hideMapIslandPeek();
    }
    if (next === "islands") {
      if (state.mobileDetailSuspended && state.activeId) {
        state.mobileDetailSuspended = false;
        els.details.hidden = false;
        els.listSection.hidden = true;
        document.body.dataset.islandDetail = "open";
      } else {
        syncMobileSidebarPanels();
      }
    }
    syncMapSize();
  }

  function applyMode() {
    if (isActive()) {
      document.body.dataset.mobileView = view;
    } else {
      delete document.body.dataset.mobileView;
      document.body.classList.remove("filters-open");
      filtersToggle?.setAttribute("aria-expanded", "false");
    }
    syncMapSize();
  }

  nav?.addEventListener("click", (e) => {
    const btn = e.target.closest(".mobile-nav__btn");
    if (!btn?.dataset.mobileView) return;
    const next = btn.dataset.mobileView;
    if (next === "islands" && view === "islands" && !els.details.hidden) {
      releaseIslandDetailView({ clearUrl: true });
    }
    setView(next);
  });

  filtersToggle?.addEventListener("click", () => {
    const open = document.body.classList.toggle("filters-open");
    filtersToggle.setAttribute("aria-expanded", open ? "true" : "false");
  });

  mq.addEventListener("change", applyMode);
  window.addEventListener("orientationchange", syncMapSize);
  window.visualViewport?.addEventListener("resize", syncMapSize);
  applyMode();
  return { isActive, setView, get view() { return view; } };
})();

document.getElementById("home-link")?.addEventListener("click", resetAtlasHome);

document.getElementById("filter-reset-btn")?.addEventListener("click", resetAllFilters);

document.getElementById("map-island-peek")?.addEventListener("click", () => {
  if (!state.activeId) return;
  mobileNav.setView("islands");
  focusIsland(state.activeId, { fly: false });
});

loadIslands();
initFavoritesAccessUi();
initCrowdSuggestUi();
initTripPlanner();
chatAutoLoadFromUrl();
