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

const TYPE_COLORS = {
  sea: "#4ea3ff",
  lake: "#6cd3a3",
  river: "#f5b04a",
};

const ROW_HEIGHT = 64; // px, must match .island-card sizing
const VIEWPORT_PADDING = 4; // extra rows rendered above/below viewport

const OVERPASS_ENDPOINTS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
  "https://overpass.openstreetmap.fr/api/interpreter",
];

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
  causeways: null,          // lazy-loaded array of tidal/bridge causeway records
  causewaysPromise: null,
};

// ---------- Ferries (lazy-loaded) ----------
// data/ferries.json + data/ferry_terminals.json + data/operators.json are
// fetched on first island click. Once loaded we keep them in state.* so
// every subsequent details render is synchronous.
function loadFerries() {
  if (state.ferries) return Promise.resolve(state.ferries);
  if (state.ferriesPromise) return state.ferriesPromise;
  state.ferriesPromise = Promise.all([
    fetch("data/ferries.json").then((r) => (r.ok ? r.json() : { routes: [] })),
    fetch("data/ferry_terminals.json").then((r) => (r.ok ? r.json() : { terminals: [] })),
    fetch("data/operators.json").then((r) => (r.ok ? r.json() : { operators: [] })),
  ])
    .then(([ferriesDoc, termsDoc, opsDoc]) => {
      const routes = Array.isArray(ferriesDoc.routes) ? ferriesDoc.routes : [];
      const terminals = Array.isArray(termsDoc.terminals) ? termsDoc.terminals : [];
      const operators = Array.isArray(opsDoc.operators) ? opsDoc.operators : [];
      const termById = new Map(terminals.map((t) => [t.id, t]));
      const opById = new Map(operators.map((o) => [o.id, o]));
      // Build island-id -> [routes...] index by checking both endpoints'
      // terminal.islandId (preferred) and falling back to terminal direct
      // attachment.
      const byIsland = new Map();
      const islandIds = new Set();
      for (const r of routes) {
        const fromTerm = termById.get(r.terminals?.from?.terminalId);
        const toTerm = termById.get(r.terminals?.to?.terminalId);
        const fromIsl = r.terminals?.from?.islandId || fromTerm?.islandId || null;
        const toIsl = r.terminals?.to?.islandId || toTerm?.islandId || null;
        const enriched = Object.assign({}, r, {
          _fromTerminal: fromTerm,
          _toTerminal: toTerm,
          _fromIsland: fromIsl,
          _toIsland: toIsl,
          _operator: opById.get(r.operatorId) || null,
        });
        if (fromIsl) {
          if (!byIsland.has(fromIsl)) byIsland.set(fromIsl, []);
          byIsland.get(fromIsl).push(enriched);
          islandIds.add(fromIsl);
        }
        if (toIsl && toIsl !== fromIsl) {
          if (!byIsland.has(toIsl)) byIsland.set(toIsl, []);
          byIsland.get(toIsl).push(enriched);
          islandIds.add(toIsl);
        }
      }
      state.ferries = { routes, terminals, operators, termById, opById };
      state.ferryIslandIds = islandIds;
      state.ferryRoutesByIsland = byIsland;
      // Build adjacency list for the itinerary planner (Phase 6f).
      // Each edge is { other, durationMin, route }. Symmetric -- we add
      // both directions because most ferries operate both ways.
      const adj = new Map();
      for (const r of routes) {
        const fId = r.terminals?.from?.islandId || (termById.get(r.terminals?.from?.terminalId) || {}).islandId;
        const tId = r.terminals?.to?.islandId || (termById.get(r.terminals?.to?.terminalId) || {}).islandId;
        if (!fId || !tId || fId === tId) continue;
        const dur = Number.isFinite(r.durationMinutes) ? r.durationMinutes : 120;
        if (!adj.has(fId)) adj.set(fId, []);
        if (!adj.has(tId)) adj.set(tId, []);
        adj.get(fId).push({ other: tId, durationMin: dur, routeId: r.id });
        adj.get(tId).push({ other: fId, durationMin: dur, routeId: r.id });
      }
      state.ferryGraph = adj;
      try { renderListWindow(); } catch (_) { /* noop */ }
      return state.ferries;
    })
    .catch((err) => {
      console.warn("loadFerries failed", err);
      state.ferries = { routes: [], terminals: [], operators: [], termById: new Map(), opById: new Map() };
      state.ferryIslandIds = new Set();
      state.ferryRoutesByIsland = new Map();
      return state.ferries;
    });
  return state.ferriesPromise;
}

function findFerriesForIsland(islandId) {
  if (!state.ferryRoutesByIsland) return [];
  return state.ferryRoutesByIsland.get(islandId) || [];
}

// Dijkstra over the ferry graph. Returns { path: [islandId, ...],
// edges: [routeId, ...], totalDurationMin } or null when unreachable.
function findFerryItinerary(startId, endId) {
  const adj = state.ferryGraph;
  if (!adj || !adj.has(startId) || !adj.has(endId)) return null;
  if (startId === endId) return { path: [startId], edges: [], totalDurationMin: 0 };
  const dist = new Map();
  const prev = new Map();
  const edgeUsed = new Map();
  dist.set(startId, 0);
  const queue = [[0, startId]]; // (priority, islandId) -- naive O(V^2) but graph is small
  const visited = new Set();
  while (queue.length) {
    queue.sort((a, b) => a[0] - b[0]);
    const [d, u] = queue.shift();
    if (visited.has(u)) continue;
    visited.add(u);
    if (u === endId) break;
    for (const e of (adj.get(u) || [])) {
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
  if (!prev.has(endId) && startId !== endId) return null;
  // Reconstruct path
  const path = [endId];
  const edges = [];
  let cur = endId;
  while (prev.has(cur)) {
    edges.unshift(edgeUsed.get(cur));
    cur = prev.get(cur);
    path.unshift(cur);
  }
  return { path, edges, totalDurationMin: dist.get(endId) || 0 };
}

// Render a banner at the top of the details panel showing the chosen
// itinerary (used when the URL contains ?trip=startId,endId).
function tryRenderItineraryFromUrl() {
  try {
    const url = new URL(window.location.href);
    const trip = url.searchParams.get("trip");
    if (!trip) return;
    const [startId, endId] = trip.split(",").map((s) => s.trim()).filter(Boolean);
    if (!startId || !endId) return;
    loadFerries().then(() => {
      const it = findFerryItinerary(startId, endId);
      if (!it) {
        console.warn("No ferry itinerary from", startId, "to", endId);
        return;
      }
      _renderItineraryBanner(it);
    });
  } catch (_) {
    /* non-fatal */
  }
}

function _renderItineraryBanner(it) {
  const stops = it.path
    .map((id) => state.byId.get(id))
    .filter(Boolean)
    .map((isl) => `<a href="?island=${encodeURIComponent(isl.id)}">${escapeHtml(isl.name)}</a>`);
  if (!stops.length) return;
  const h = Math.floor(it.totalDurationMin / 60);
  const m = it.totalDurationMin % 60;
  const dur = h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
  let banner = document.getElementById("itinerary-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "itinerary-banner";
    banner.className = "itinerary-banner";
    document.body.prepend(banner);
  }
  banner.innerHTML = `
    <strong>Suggested ferry itinerary:</strong>
    <span class="itinerary-banner__stops">${stops.join(" <span class=\"itinerary-banner__arrow\">→</span> ")}</span>
    <span class="itinerary-banner__meta">~${dur} at sea over ${it.edges.length} crossing${it.edges.length === 1 ? "" : "s"}</span>
    <button type="button" class="itinerary-banner__close" aria-label="Dismiss">×</button>
  `;
  banner.querySelector(".itinerary-banner__close")?.addEventListener("click", () => banner.remove());
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
  search: document.getElementById("search"),
  typeFilter: document.getElementById("type-filter"),
  nationFilter: document.getElementById("nation-filter"),
  basemap: document.getElementById("basemap"),
  cluster: document.getElementById("cluster-toggle"),
  details: document.getElementById("island-details"),
  detailsContent: document.getElementById("details-content"),
  listSection: document.getElementById("island-list-section"),
  back: document.getElementById("back-button"),
  sidebar: document.getElementById("sidebar"),
};

// ---------- Map ----------
const map = L.map("map", {
  center: [55.5, -4.0],
  zoom: 6,
  minZoom: 4,
  maxZoom: 18,
  worldCopyJump: true,
  preferCanvas: true,
});

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

els.cluster.addEventListener("change", () => {
  const wasOn = map.hasLayer(activeMarkerLayer);
  if (wasOn) map.removeLayer(activeMarkerLayer);
  activeMarkerLayer = els.cluster.checked ? clusterLayer : flatLayer;
  rebuildMarkerLayer();
  activeMarkerLayer.addTo(map);
});

// ---------- Data load ----------
async function loadIslands() {
  try {
    const res = await fetch("data/islands.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.islands = await res.json();
    state.byId = new Map(state.islands.map((i) => [i.id, i]));
  } catch (error) {
    console.error("Failed to load islands.json", error);
    els.list.innerHTML = `<li class="island-card" style="color:#ff8a8a">Failed to load island data: ${error.message}. Are you serving the site over HTTP (not file://)?</li>`;
    return;
  }

  populateNationFilter();
  applyFilters();
}

function populateNationFilter() {
  const nations = Array.from(
    new Set(state.islands.map((i) => i.nation)),
  ).sort();
  for (const nation of nations) {
    const opt = document.createElement("option");
    opt.value = nation;
    opt.textContent = nation;
    els.nationFilter.appendChild(opt);
  }
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

  if (q) {
    // Score and rank.
    const scored = [];
    for (const i of state.islands) {
      if (type && i.type !== type) continue;
      if (nation && i.nation !== nation) continue;
      const s = _scoreIsland(i, q);
      if (s > -Infinity) scored.push({ island: i, score: s });
    }
    // Stable secondary: name ascending so equal scores are predictable.
    scored.sort((a, b) =>
      b.score - a.score || a.island.name.localeCompare(b.island.name),
    );
    state.filtered = scored.map((x) => x.island);
  } else {
    state.filtered = state.islands.filter((i) => {
      if (type && i.type !== type) return false;
      if (nation && i.nation !== nation) return false;
      return true;
    });
    state.filtered.sort((a, b) => a.name.localeCompare(b.name));
  }

  renderList();
  rebuildMarkerLayer();
}

[els.search, els.typeFilter, els.nationFilter].forEach((el) =>
  el.addEventListener("input", applyFilters),
);

// ---------- Virtualised list ----------
let listScroller = null;
let listSpacer = null;
let listInner = null;

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
  listScroller.addEventListener("scroll", renderListWindow);
  window.addEventListener("resize", renderListWindow);
}

function renderList() {
  ensureListScaffolding();
  els.count.textContent = state.filtered.length.toString();
  listSpacer.style.height = `${state.filtered.length * ROW_HEIGHT}px`;
  // Reset scroll to top when filter changes
  listScroller.scrollTop = 0;
  renderListWindow();
}

function renderListWindow() {
  if (!listInner) return;
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
    const card = document.createElement("button");
    card.type = "button";
    card.className = "island-card" + (island.id === state.activeId ? " is-active" : "");
    card.style.height = `${ROW_HEIGHT - 8}px`;
    card.dataset.id = island.id;
    card.setAttribute(
      "aria-label",
      `${island.name}, ${island.nation}, ${formatPopulation(island.population)}`,
    );
    const hasFerry = state.ferryIslandIds && state.ferryIslandIds.has(island.id);
    card.innerHTML = `
      <div class="island-card__title">
        <span class="dot dot--${island.type}"></span>
        ${escapeHtml(island.name)}
        ${hasFerry ? '<span class="island-card__ferry-icon" title="Ferry-accessible">⛴</span>' : ""}
      </div>
      <div class="island-card__meta">
        <span>${escapeHtml(island.nation)}</span>
        ${island.archipelago ? `<span>${escapeHtml(island.archipelago)}</span>` : ""}
        <span>${formatPopulation(island.population)}</span>
      </div>
    `;
    card.addEventListener("click", () => focusIsland(island.id, { fly: true }));
    listInner.appendChild(card);
  }
}

// ---------- Markers ----------
function makeMarker(island) {
  const color = TYPE_COLORS[island.type] || TYPE_COLORS.sea;
  const radius = Math.max(
    4,
    Math.min(14, Math.log10((island.areaKm2 || 0.05) + 1) * 6 + 4),
  );

  const marker = L.circleMarker([island.lat, island.lng], {
    radius,
    color: "#ffffff",
    weight: 1.2,
    fillColor: color,
    fillOpacity: 0.9,
  });

  marker.bindTooltip(island.name, { direction: "top", offset: [0, -4] });
  marker.on("click", () => focusIsland(island.id, { fly: false }));

  return marker;
}

function rebuildMarkerLayer() {
  // Clear & rebuild the active marker layer with the currently-filtered set.
  // Markers are cheap to recreate; reusing them across cluster/flat would
  // double the memory.
  clusterLayer.clearLayers();
  flatLayer.clearLayers();
  state.markers.clear();

  const layer = activeMarkerLayer;
  for (const island of state.filtered) {
    const m = makeMarker(island);
    state.markers.set(island.id, m);
    if (layer === clusterLayer) {
      clusterLayer.addLayer(m);
    } else {
      flatLayer.addLayer(m);
    }
  }
}

// ---------- Details panel ----------
function focusIsland(id, { fly } = { fly: true }) {
  const island = state.byId.get(id);
  if (!island) return;

  state.activeId = id;
  // Re-render list so the active card is highlighted (cheap because virtualised)
  renderListWindow();

  renderDetails(island);

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

  const title = routes.length ? "How to get there" : "Causeway access";

  return `<div class="section ferry-section" id="ferry-block">
    <h3>${escapeHtml(title)}</h3>
    ${routes.length ? `<p class="ferry-subtitle">${sorted.length} ferry connection${sorted.length === 1 ? "" : "s"} published for this island.</p>` : ""}
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
  els.sidebar.scrollTop = 0;

  const typeLabel = island.subtype
    ? `${capitalize(island.subtype)} (${island.type})`
    : `${capitalize(island.type)} island`;

  const parentBody = island.parentWaterBody;
  const parentLabel = parentBody
    ? parentBody.name
      ? `${escapeHtml(parentBody.name)} <span style="color:var(--text-muted)">(${escapeHtml(parentBody.type)})</span>`
      : `<span style="color:var(--text-muted)">Unnamed ${escapeHtml(parentBody.type)}</span>`
    : island.type !== "sea"
      ? "—"
      : null;

  const stats = [
    { label: "Type", value: typeLabel },
    { label: "Nation", value: island.nation || "—" },
    { label: "Archipelago", value: island.archipelago || "—" },
    { label: "Area", value: formatArea(island.areaKm2) },
    { label: "Population", value: formatPopulation(island.population) },
    {
      label: "Highest point",
      value: island.highestPointM
        ? `${island.highestPointM} m${
            island.highestPointName ? " (" + escapeHtml(island.highestPointName) + ")" : ""
          }`
        : "—",
    },
  ];
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
    const conf =
      { high: "High", medium: "Medium", low: "Low" }[island.classification.confidence] ||
      "—";
    stats.push({
      label: "Classified by",
      value: `<span style="font-size:12px">${escapeHtml(
        island.classification.source,
      )} · ${conf} confidence</span>`,
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

  els.detailsContent.innerHTML = `
    ${gallery}
    <h2 class="details-title">${escapeHtml(island.name)}</h2>
    ${altNames}
    ${island.shortDescription ? `<p class="details-subtitle">${escapeHtml(island.shortDescription)}</p>` : ""}

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

    ${tags ? `<div class="tags">${tags}</div>` : ""}

    ${richSections}
    ${osmHint}

    ${renderFerries(island)}

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

    ${sourcesBlock}
  `;

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

// Merge the lead image(s) from islands.json with the lazily-loaded
// extras from data/galleries.json. Lead image(s) always come first;
// extras are appended in script order. Mutates `island.images` once the
// merge has been applied so subsequent renders don't redo the work.
function ensureGalleryMerged(island) {
  if (!state.galleries) return; // not loaded yet — skip; will be re-rendered
  if (island.__galleryMerged) return;
  const extras = state.galleries[island.id];
  if (Array.isArray(extras) && extras.length) {
    const lead = Array.isArray(island.images) ? island.images : [];
    const have = new Set(lead.map((x) => x.fileName || x.url));
    const merged = lead.slice();
    for (const ex of extras) {
      const key = ex.fileName || ex.url;
      if (key && have.has(key)) continue;
      merged.push({ ...ex, primary: false });
      have.add(key);
    }
    island.images = merged;
  }
  island.__galleryMerged = true;
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

  const thumbStrip =
    images.length > 1
      ? `<div class="thumb-strip" role="tablist" aria-label="Island images">${images
          .map(
            (img, idx) => `
              <button class="thumb${
                idx === primaryIdx ? " is-active" : ""
              }" data-img-idx="${idx}" role="tab" aria-selected="${idx === primaryIdx}" aria-label="Image ${idx + 1}">
                <img src="${escapeAttr(img.url)}" alt="" loading="lazy" onerror="this.style.opacity='0.25'"/>
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
  els.details.hidden = true;
  els.listSection.hidden = false;
  if (state.activePolygon) {
    map.removeLayer(state.activePolygon);
    state.activePolygon = null;
  }
  // Release the detail map; its DOM is about to be hidden anyway, and we'd
  // rather not keep tile requests alive when the panel isn't visible.
  if (state.detailMap) {
    try { state.detailMap.remove(); } catch (_) { /* ignore */ }
    state.detailMap = null;
  }
});

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

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
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
  ferry: ["ferry", "ferries", "calmac", "passenger boat"],
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
  "Scottish islands with mountains",
  "Uninhabited islands in lakes",
  "Islands with a castle",
  "Largest islands in Wales",
  "Crannogs in Ireland",
  "Tidal islands in England",
  "Islands near Oban",
  "Within 30 km of Mallaig",
  "Car ferries to the Hebrides",
  "Summer ferries to Pembrokeshire islands",
  "Islands you can reach by ferry from Oban",
  "CalMac islands with castles",
];

function chatTokens(text) {
  return text.toLowerCase().normalize("NFKD");
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
    // Ferry intent — set when the user clearly wants ferry-accessible
    // islands or the routes themselves.
    ferryIntent: false,
    ferryTypeWanted: null,        // 'car-and-foot' | 'foot-only'
    ferrySeasonWanted: null,      // 'year-round' | 'summer-only'
    ferryOperatorWanted: null,    // operator-id substring match
    ferryFromPort: null,          // free-text port name to match against terminal names
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
  for (const [feat, syn] of Object.entries(CHAT_FEATURES)) {
    if (syn.some((w) => text.includes(w))) q.features.add(feat);
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

  // "smaller than X km", "larger than X km"
  let m = text.match(/(?:smaller|less than|under)\s+(\d+(?:\.\d+)?)\s*(?:km2|km²|sq km|square km|km)/);
  if (m) q.sizeMax = parseFloat(m[1]);
  m = text.match(/(?:larger|bigger|more than|over)\s+(\d+(?:\.\d+)?)\s*(?:km2|km²|sq km|square km|km)/);
  if (m) q.sizeMin = parseFloat(m[1]);

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
    ...Object.keys(CHAT_SORTS),
    "island", "islands", "show", "me", "the", "a", "an", "with", "and",
    "in", "of", "to", "for", "find", "i", "want", "you", "have", "are",
    "is", "that", "where", "which", "what", "any", "some", "all", "near",
    "off", "on", "from",
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
  return [
    island.name,
    island.archipelago,
    island.shortDescription,
    island.geography,
    island.history,
    island.transport,
    island.accommodation,
    (island.tags || []).join(" "),
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
    } else if (hits > 0) {
      score += 2 + Math.min(3, hits);
    } else if (q.features.size === 1) {
      score -= 1;
    }
  }

  const nameHay = (island.name || "").toLowerCase();
  let nameHits = 0;
  for (const k of q.keywords) {
    if (nameHay.includes(k)) {
      score += 5;
      nameHits++;
    } else if (hay.includes(k)) {
      score += 1;
    }
  }
  // Reward an exact-name match heavily so "Belle Isle" lands the right island.
  if (q.keywords.length && nameHits === q.keywords.length) score += 4;

  if (island.images && island.images.length) score += 0.6;
  if (island.population) score += 0.3;
  if (island.areaKm2) score += Math.min(1, Math.log10(1 + island.areaKm2));

  return score;
}

function searchChatIslands(rawText, limit = 6) {
  const q = parseChatQuery(rawText);
  const scored = [];
  for (const i of state.islands) {
    const s = scoreChatIsland(i, q);
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
    return { query: q, results: sortable.slice(0, limit), total: sortable.length };
  }
  scored.sort((a, b) => b.score - a.score);
  return { query: q, results: scored.slice(0, limit), total: scored.length };
}

function composeChatResponse({ query, results, total }) {
  if (!results.length) {
    const hints = [];
    if (!query.nations.size) hints.push("a nation (Scotland, Wales, …)");
    if (!query.types.size) hints.push("a type (sea, lake, river)");
    if (!query.features.size) hints.push("a feature (mountains, castle, ferry)");
    return (
      "I couldn't find any matches. Try mentioning " +
      hints.join(", ") +
      "."
    );
  }
  const parts = [];
  const totalLabel = total === 1 ? "1 match" : `${total.toLocaleString()} matches`;
  const facets = [];
  if (query.nations.size) facets.push([...query.nations].join("/"));
  if (query.types.size) facets.push([...query.types].map((t) => t + " islands").join("/"));
  else facets.push("islands");
  if (query.archipelagos.size) facets.push("in " + [...query.archipelagos].join("/"));
  if (query.features.size) facets.push("with " + [...query.features].join(" + "));
  if (query.near) {
    const km = Math.round(query.near.radiusKm);
    facets.push(`within ${km} km of ${query.near.name}`);
  }
  if (query.sort) facets.push("(sorted by " + query.sort.sortBy + ")");
  parts.push(`Found ${totalLabel} for ${facets.join(" ")}.`);
  if (results.length < total) {
    parts.push(`Showing the top ${results.length}.`);
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
  setTimeout(() => chatEls.input.focus(), 50);
  if (!chatEls.messages.dataset.bootstrapped) {
    chatRenderBot(
      "Hi! Describe what kind of island you're looking for — by nation, type, or feature. " +
        "Everything happens locally; no data leaves your browser.",
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

function chatRenderBot(text, { suggestions, results, query } = {}) {
  const div = document.createElement("div");
  div.className = "chat-msg chat-msg--bot";
  div.innerHTML = escapeHtml(text);

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
    for (const r of results) {
      const isl = r.island;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-result";
      btn.dataset.id = isl.id;

      const thumb = document.createElement("div");
      thumb.className = "chat-result__thumb";
      const imgUrl = isl.image || (isl.images && isl.images[0] && isl.images[0].url) || "";
      if (imgUrl) {
        thumb.style.backgroundImage = `url('${imgUrl.replace(/'/g, "\\'")}')`;
      } else {
        thumb.classList.add("chat-result__thumb--empty");
        thumb.textContent = "◍";
      }
      btn.appendChild(thumb);

      const body = document.createElement("div");
      body.className = "chat-result__body";
      const title = document.createElement("strong");
      title.textContent = isl.name;
      body.appendChild(title);
      const meta = document.createElement("span");
      meta.className = "chat-result__meta";
      const parts = [];
      if (isl.nation) parts.push(isl.nation);
      if (isl.type) {
        parts.push(
          isl.subtype ? `${isl.subtype} (${isl.type})` : `${isl.type} island`
        );
      }
      if (isl.parentWaterBody && isl.parentWaterBody.name) {
        parts.push(isl.parentWaterBody.name);
      }
      if (isl.areaKm2) parts.push(formatArea(isl.areaKm2));
      if (query && query.near &&
          Number.isFinite(isl.lat) && Number.isFinite(isl.lng)) {
        const km = chatHaversineKm(query.near.lat, query.near.lng, isl.lat, isl.lng);
        parts.push(`${Math.round(km)} km from ${query.near.name}`);
      }
      meta.textContent = parts.join(" · ");
      body.appendChild(meta);

      // Source cross-reference: if there's a primary image with a
      // sourcePageUrl, render a tiny clickable link so the user can verify
      // where the photo came from. Mirrors the detail panel.
      const primaryImg =
        (isl.images && isl.images.find((x) => x.primary)) ||
        (isl.images && isl.images[0]) ||
        null;
      if (primaryImg && primaryImg.sourcePageUrl) {
        const srcLink = document.createElement("a");
        srcLink.className = "chat-result__source";
        srcLink.href = primaryImg.sourcePageUrl;
        srcLink.target = "_blank";
        srcLink.rel = "noopener";
        srcLink.textContent =
          (SOURCE_LABELS[primaryImg.source] || primaryImg.source || "source") +
          " ↗";
        srcLink.addEventListener("click", (e) => e.stopPropagation());
        body.appendChild(srcLink);
      }

      btn.appendChild(body);

      btn.addEventListener("click", () => {
        focusIsland(isl.id);
        if (window.innerWidth <= 640) chatClose();
      });

      list.appendChild(btn);
    }
    div.appendChild(list);
  }

  chatAppend(div);
}

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
  const prep = probe.ferryIntent && !state.ferries
    ? loadFerries()
    : Promise.resolve();

  prep.then(() => {
    const r = searchChatIslands(t, 6);
    thinking.remove();
    if (!r.results.length) {
      chatRenderBot(composeChatResponse(r), { suggestions: CHAT_SUGGESTIONS });
    } else {
      chatRenderBot(composeChatResponse(r), { results: r.results, query: r.query });
    }
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
loadIslands();
chatAutoLoadFromUrl();
tryRenderItineraryFromUrl();
