/**
 * Ask — atlas tools for the language model.
 *
 * The model does not receive the whole dataset. It calls these functions,
 * which run in the browser against the loaded index, the interest overlay,
 * and (when present) data/chat_corpus.json. Full prose is loaded separately
 * by the caller via read_islands.
 */

const NATIONS = [
  "Scotland",
  "England",
  "Wales",
  "Northern Ireland",
  "Ireland",
  "Crown Dependency",
];

const TYPES = ["sea", "lake", "river"];

const STOP = new Set(
  `a an the of in on at to for and or with from within about what which where who
   how show find me my please some any are is was be there that this those these
   into looking want like tell describe island islands isle isles largest biggest
   smallest highest tallest most best famous worth visiting visit recommend near
   around close nearby`.split(/\s+/),
);

const storyCache = new WeakMap();

export function fold(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/['’]/g, "");
}

export function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, a)));
}

function tokensOf(query) {
  return fold(query)
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}

function num(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function bool(value) {
  if (value === true || value === false) return value;
  if (value === "true") return true;
  if (value === "false") return false;
  return null;
}

function canonNation(value) {
  if (!value) return null;
  const f = fold(value);
  return NATIONS.find((n) => fold(n) === f) || null;
}

function canonType(value) {
  if (!value) return null;
  const f = fold(value);
  return TYPES.includes(f) ? f : null;
}

function namedIsland(island) {
  if (!island || typeof island !== "object") return false;
  if (island.nameStatus === "unknown") return false;
  const name = (island.name || "").trim();
  return !!name && name !== "Unnamed island";
}

export function findIslandByName(raw, islands) {
  const target = fold(raw)
    .replace(/\b(the|isle of|island of)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!target || target.length < 3) return null;
  let best = null;
  let bestScore = 0;
  for (const island of islands || []) {
    if (!namedIsland(island)) continue;
    const name = fold(island.name)
      .replace(/\b(the|isle of|island of)\b/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    let score = 0;
    if (name === target) score = 100;
    else if (name.startsWith(target) || (target.startsWith(name) && name.length >= 4)) score = 40;
    else continue;
    score += Math.min(8, Math.log10(1 + (island.areaKm2 || 0)));
    if (score > bestScore) {
      bestScore = score;
      best = island;
    }
  }
  return bestScore >= 40 ? best : null;
}

function corpusOf(ctx, id) {
  const rows = ctx.corpus?.rows || ctx.corpus || {};
  return rows[id] || {};
}

function waterName(ctx, island) {
  return (
    corpusOf(ctx, island.id).w ||
    (island.parentWaterBody && island.parentWaterBody.name) ||
    ""
  );
}

function peakName(ctx, island) {
  return corpusOf(ctx, island.id).p || island.highestPointName || "";
}

function buildStoryCache(interestIndex) {
  const byId = new Map();
  const stories = interestIndex?.stories || {};
  for (const [slug, islands] of Object.entries(stories)) {
    if (!islands || typeof islands !== "object") continue;
    for (const [id, items] of Object.entries(islands)) {
      if (!Array.isArray(items)) continue;
      let bucket = byId.get(id);
      if (!bucket) {
        bucket = { items: [], text: "" };
        byId.set(id, bucket);
      }
      const bits = [];
      for (const item of items) {
        if (!item || typeof item !== "object") continue;
        const title = typeof item.title === "string" ? item.title : "";
        const summary = typeof item.summary === "string" ? item.summary : "";
        bucket.items.push({
          collection: slug,
          title,
          facet: item.facet || null,
          subdivision: item.subdivision || null,
          summary,
        });
        if (title) bits.push(title);
        if (summary) bits.push(summary.slice(0, 180));
      }
      bucket.text = fold(bits.join(" "));
    }
  }
  const highlights = interestIndex?.highlights || {};
  for (const islands of Object.values(highlights)) {
    if (!islands || typeof islands !== "object") continue;
    for (const [id, titles] of Object.entries(islands)) {
      if (!Array.isArray(titles)) continue;
      let bucket = byId.get(id);
      if (!bucket) {
        bucket = { items: [], text: "" };
        byId.set(id, bucket);
      }
      const extra = titles
        .map((item) => (item && typeof item === "object" ? item.title : item))
        .filter((t) => typeof t === "string" && t);
      if (extra.length) bucket.text = fold(`${bucket.text} ${extra.join(" ")}`);
    }
  }
  return byId;
}

function storyCacheFor(interestIndex) {
  if (!interestIndex) return new Map();
  let cache = storyCache.get(interestIndex);
  if (!cache) {
    cache = buildStoryCache(interestIndex);
    storyCache.set(interestIndex, cache);
  }
  return cache;
}

function whiskySubdivisions(interestIndex) {
  const cat = (interestIndex?.categories || []).find((c) => c.slug === "whisky-distilleries");
  return Array.isArray(cat?.subdivisions) ? cat.subdivisions : [];
}

function storyMatchesFacet(slug, item, facet, interestIndex) {
  if (!facet) return true;
  const want = fold(facet);
  if (slug === "whisky-distilleries") {
    const spec = whiskySubdivisions(interestIndex).find((row) => fold(row.id) === want);
    if (spec?.match === "facet") return fold(item.facet) === want;
    if (spec?.match === "subdivision") {
      return fold(item.subdivision) === want && item.facet === "distillery";
    }
    return fold(item.facet) === want || fold(item.subdivision) === want;
  }
  if (slug === "film-art-music") return fold(item.facet) === want;
  return fold(item.facet) === want || fold(item.subdivision) === want;
}

function memberSet(interestIndex, slug) {
  const ids = interestIndex?.members?.[slug];
  return Array.isArray(ids) ? new Set(ids) : null;
}

function collectionSlug(interestIndex, value) {
  if (!value) return null;
  const f = fold(value);
  const cats = interestIndex?.categories || [];
  const hit = cats.find((c) => fold(c.slug) === f || fold(c.label) === f);
  return hit ? hit.slug : null;
}

export function listCollections(interestIndex) {
  return (interestIndex?.categories || []).map((c) => ({
    slug: c.slug,
    label: c.label,
    blurb: c.blurb || "",
    count: c.count || interestIndex?.members?.[c.slug]?.length || 0,
    facets: (c.subdivisions || []).map((s) => ({
      id: s.id,
      label: s.label,
      blurb: s.blurb || "",
    })),
  }));
}

function resolveNear(args, ctx) {
  const near = args?.near;
  if (!near || typeof near !== "object") return null;
  const radius = Math.min(250, Math.max(1, num(near.radiusKm) ?? 40));
  const lat = num(near.lat);
  const lng = num(near.lng);
  if (lat != null && lng != null) {
    if (lat < 48 || lat > 62.5 || lng < -12 || lng > 3) {
      return {
        error:
          "Those coordinates are outside this atlas (Britain, Ireland, and the nearby crown dependencies).",
      };
    }
    return {
      lat,
      lng,
      radiusKm: radius,
      label: String(near.label || near.place || "that point"),
    };
  }
  const place = String(near.place || near.label || "").trim();
  if (!place) return { error: "near needs lat and lng, or a place name." };
  const places = ctx.places || {};
  const key = Object.keys(places).find((k) => fold(k) === fold(place));
  if (key) {
    return { lat: places[key][0], lng: places[key][1], radiusKm: radius, label: key };
  }
  const island = findIslandByName(place, ctx.islands);
  if (island && Number.isFinite(island.lat) && Number.isFinite(island.lng)) {
    return {
      lat: island.lat,
      lng: island.lng,
      radiusKm: radius,
      label: island.name,
      excludeId: island.id,
    };
  }
  return {
    error: `No coordinates for "${place}". Pass lat and lng (48–62.5°N, 12°W–3°E), or a town the atlas already knows.`,
  };
}

function hasConstraint(args, tokens, near) {
  return !!(
    tokens.length ||
    args.nation ||
    args.type ||
    args.subtype ||
    args.archipelago ||
    args.water ||
    near ||
    args.collection ||
    num(args.minAreaKm2) != null ||
    num(args.maxAreaKm2) != null ||
    num(args.minElevationM) != null ||
    bool(args.inhabited) != null ||
    bool(args.hasPhoto) === true
  );
}

function prepareFilters(args, ctx) {
  const nation = args.nation ? canonNation(args.nation) : null;
  if (args.nation && !nation) {
    return { error: `Unknown nation "${args.nation}". Use one of: ${NATIONS.join(", ")}.` };
  }
  const type = args.type ? canonType(args.type) : null;
  if (args.type && !type) {
    return { error: `Unknown type "${args.type}". Use sea, lake, or river.` };
  }
  let collection = null;
  if (args.collection) {
    collection = collectionSlug(ctx.interestIndex, args.collection);
    if (!collection) {
      const known = listCollections(ctx.interestIndex).map((c) => c.slug);
      return {
        error: known.length
          ? `Unknown collection "${args.collection}". Use one of: ${known.join(", ")}.`
          : "Interest collections are not loaded yet.",
      };
    }
  }
  const near = resolveNear(args, ctx);
  if (near?.error) return { error: near.error };
  return {
    nation,
    type,
    subtype: args.subtype ? fold(args.subtype) : null,
    archipelago: args.archipelago ? fold(args.archipelago) : null,
    water: args.water ? fold(args.water) : null,
    minArea: num(args.minAreaKm2),
    maxArea: num(args.maxAreaKm2),
    minElev: num(args.minElevationM),
    inhabited: bool(args.inhabited),
    hasPhoto: bool(args.hasPhoto),
    collection,
    facet: args.facet ? String(args.facet) : null,
    near,
    tokens: tokensOf(args.query || ""),
  };
}

function islandMatches(island, filters, ctx) {
  if (!namedIsland(island)) return false;
  if (filters.near?.excludeId && island.id === filters.near.excludeId) return false;
  if (filters.nation && island.nation !== filters.nation) return false;
  if (filters.type && island.type !== filters.type) return false;
  if (filters.subtype && fold(island.subtype) !== filters.subtype) return false;
  if (filters.archipelago && !fold(island.archipelago).includes(filters.archipelago)) return false;
  const water = waterName(ctx, island);
  if (filters.water && !fold(water).includes(filters.water)) return false;
  if (filters.minArea != null && !(island.areaKm2 >= filters.minArea)) return false;
  if (filters.maxArea != null && !(island.areaKm2 > 0 && island.areaKm2 <= filters.maxArea)) {
    return false;
  }
  if (filters.minElev != null && !(island.highestPointM >= filters.minElev)) return false;
  if (filters.inhabited === true && !(island.population > 0)) return false;
  if (filters.inhabited === false && island.population > 0) return false;
  if (filters.hasPhoto === true && !(island.hasImage || island.image || island.images?.length)) {
    return false;
  }
  if (filters.collection) {
    const members = memberSet(ctx.interestIndex, filters.collection);
    if (!members || !members.has(island.id)) return false;
    if (filters.facet) {
      const items = storyCacheFor(ctx.interestIndex).get(island.id)?.items || [];
      const ok = items.some((item) =>
        item.collection === filters.collection &&
        storyMatchesFacet(filters.collection, item, filters.facet, ctx.interestIndex),
      );
      if (!ok) return false;
    }
  }
  let distanceKm = null;
  if (filters.near) {
    if (!Number.isFinite(island.lat) || !Number.isFinite(island.lng)) return false;
    distanceKm = haversineKm(filters.near.lat, filters.near.lng, island.lat, island.lng);
    if (distanceKm > filters.near.radiusKm) return false;
  }

  let score = 1;
  let matchedOn = "filter";
  if (filters.tokens.length) {
    const name = fold(island.name);
    const arch = fold(island.archipelago);
    const story = storyCacheFor(ctx.interestIndex).get(island.id)?.text || "";
    const extra = corpusOf(ctx, island.id);
    const desc = fold(extra.d);
    const alts = fold(extra.n);
    const peak = fold(peakName(ctx, island));
    const waterFold = fold(water);
    let nameHits = 0;
    let waterHits = 0;
    let storyHits = 0;
    let archHits = 0;
    let peakHits = 0;
    for (const token of filters.tokens) {
      const inName = name.includes(token) || alts.includes(token);
      const inWater = waterFold.includes(token);
      const inStory = story.includes(token) || desc.includes(token);
      const inArch = arch.includes(token);
      const inPeak = peak.includes(token);
      if (!inName && !inWater && !inStory && !inArch && !inPeak) return false;
      if (inName) nameHits++;
      if (inWater) waterHits++;
      if (inStory) storyHits++;
      if (inArch) archHits++;
      if (inPeak) peakHits++;
    }
    if (nameHits === filters.tokens.length) {
      score += 40 + nameHits;
      matchedOn = "name";
    } else if (nameHits) {
      score += 15 + nameHits * 3;
      matchedOn = "name";
    }
    if (waterHits) {
      score += waterHits === filters.tokens.length ? 28 : 10;
      if (matchedOn === "filter") matchedOn = "water";
    }
    if (archHits) {
      score += 12;
      if (matchedOn === "filter") matchedOn = "archipelago";
    }
    if (peakHits) {
      score += 18;
      if (matchedOn === "filter") matchedOn = "summit";
    }
    if (storyHits) {
      score += 6 + storyHits * 2;
      if (matchedOn === "filter") matchedOn = "story";
    }
    const bare = name.replace(/\b(isle|island|of|the)\b/g, " ").replace(/\s+/g, " ").trim();
    if (bare === filters.tokens.join(" ")) score += 30;
  } else {
    score += Math.min(5, Math.log10(1 + (island.areaKm2 || 0)));
    if (island.hasImage || island.image) score += 0.4;
  }
  return { island, score, matchedOn, distanceKm, water, peak: peakName(ctx, island) };
}

function sortHits(hits, sort) {
  const key = sort || "relevance";
  hits.sort((a, b) => {
    if (key === "distance") return (a.distanceKm ?? 1e9) - (b.distanceKm ?? 1e9);
    if (key === "name") return String(a.island.name).localeCompare(String(b.island.name));
    if (key === "elevation") return (b.island.highestPointM || 0) - (a.island.highestPointM || 0);
    if (key === "population") return (b.island.population || 0) - (a.island.population || 0);
    if (key === "area") return (b.island.areaKm2 || 0) - (a.island.areaKm2 || 0);
    return b.score - a.score || (b.island.areaKm2 || 0) - (a.island.areaKm2 || 0);
  });
}

function briefRow(hit) {
  const island = hit.island;
  const row = {
    id: island.id,
    name: island.name,
    nation: island.nation || null,
    type: island.type || null,
    matchedOn: hit.matchedOn,
  };
  if (island.subtype) row.subtype = island.subtype;
  if (island.archipelago) row.archipelago = island.archipelago;
  if (hit.water) row.water = hit.water;
  if (island.areaKm2 > 0) row.areaKm2 = +Number(island.areaKm2).toFixed(2);
  if (island.highestPointM) row.highestPointM = Math.round(island.highestPointM);
  if (hit.peak) row.highestPointName = hit.peak;
  if (island.population > 0) row.population = island.population;
  if (island.hasImage || island.image || island.images?.length) row.hasPhoto = true;
  if (hit.distanceKm != null) row.distanceKm = Math.round(hit.distanceKm);
  return row;
}

function collectHits(args, ctx) {
  const filters = prepareFilters(args || {}, ctx);
  if (filters.error) return filters;
  const hits = [];
  for (const island of ctx.islands || []) {
    const hit = islandMatches(island, filters, ctx);
    if (hit) hits.push(hit);
  }
  return { filters, hits };
}

export function searchIslands(ctx, args) {
  const collected = collectHits(args || {}, ctx);
  if (collected.error) return { error: collected.error };
  const { filters, hits } = collected;
  if (!hasConstraint(args || {}, filters.tokens, filters.near)) {
    return {
      error:
        "That search has no filter. Set a nation, type, water, place, collection, size, or a name. " +
        `The atlas has ${namedCount(ctx)} named islands.`,
    };
  }
  let sort = args.sort || null;
  if (!sort) {
    if (filters.near) sort = "distance";
    else if (filters.tokens.length) sort = "relevance";
    else sort = "area";
  }
  sortHits(hits, sort);
  const limit = Math.min(12, Math.max(1, num(args.limit) || 8));
  const shown = hits.slice(0, limit).map(briefRow);
  const payload = {
    matched: hits.length,
    showing: shown.length,
    truncated: hits.length > shown.length,
    sort,
    islands: shown,
  };
  if (filters.near) {
    payload.near = {
      label: filters.near.label,
      radiusKm: filters.near.radiusKm,
      lat: +filters.near.lat.toFixed(3),
      lng: +filters.near.lng.toFixed(3),
    };
  }
  if (payload.truncated) {
    payload.hint = "Narrow the search or call read_islands on the ids you will mention.";
  }
  if (!shown.length) {
    payload.hint = "Nothing matched. Drop a filter, widen the radius, or call list_collections.";
  }
  return payload;
}

function namedCount(ctx) {
  let n = 0;
  for (const island of ctx.islands || []) if (namedIsland(island)) n++;
  return n;
}

export function countIslands(ctx, args) {
  const raw = args || {};
  const collected = collectHits(raw, ctx);
  if (collected.error) return { error: collected.error };
  const { filters, hits } = collected;
  const constrained = hasConstraint(raw, filters.tokens, filters.near);
  const groupBy = raw.groupBy || (constrained ? null : "nation");
  const payload = { total: hits.length };
  if (!constrained) {
    payload.note =
      "This is every named island in the atlas. Population is recorded for only some of them, so do not treat a population count as a census.";
  }
  if (groupBy) {
    const groups = new Map();
    for (const hit of hits) {
      let key = "unrecorded";
      if (groupBy === "nation") key = hit.island.nation || "unrecorded";
      else if (groupBy === "type") key = hit.island.type || "unrecorded";
      else if (groupBy === "archipelago") key = hit.island.archipelago || "(none)";
      else if (groupBy === "water") key = hit.water || "(none)";
      else key = hit.island.nation || "unrecorded";
      groups.set(key, (groups.get(key) || 0) + 1);
    }
    const ranked = [...groups.entries()].sort((a, b) => b[1] - a[1]);
    const top = ranked.slice(0, 12).map(([key, count]) => ({ key, count }));
    const rest = ranked.slice(12).reduce((sum, row) => sum + row[1], 0);
    payload.groupBy = groupBy === "water" || groupBy === "type" || groupBy === "archipelago" || groupBy === "nation"
      ? groupBy
      : "nation";
    payload.groups = top;
    if (rest) payload.other = rest;
  }
  sortHits(hits, "area");
  payload.examples = hits.slice(0, 5).map((hit) => ({ id: hit.island.id, name: hit.island.name }));
  return payload;
}

export function storiesForIsland(interestIndex, islandId, args = {}) {
  const bucket = storyCacheFor(interestIndex).get(islandId);
  const items = bucket?.items || [];
  const collection = args.collection
    ? collectionSlug(interestIndex, args.collection)
    : null;
  const facet = args.facet || null;
  const filtered = items.filter((item) => {
    if (collection && item.collection !== collection) return false;
    if (facet && !storyMatchesFacet(item.collection, item, facet, interestIndex)) return false;
    return true;
  });
  return { total: filtered.length, items: filtered };
}

function trim(value, limit) {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text) return null;
  if (text.length <= limit) return text;
  return text.slice(0, limit - 1).trim() + "…";
}

function dropEmpty(obj) {
  const out = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value == null) continue;
    if (typeof value === "string" && value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return out;
}

export function serialiseIslandRecord(island, storyPack) {
  const names = island.names && typeof island.names === "object" ? island.names : null;
  const otherNames = {};
  if (names) {
    for (const [lang, value] of Object.entries(names)) {
      if (lang === "en") continue;
      if (typeof value === "string" && value.trim()) otherNames[lang] = value.trim();
    }
  }
  const listings = Array.isArray(island.propertyListings)
    ? island.propertyListings.slice(0, 3).map((listing) =>
        dropEmpty({
          title: listing.title || null,
          listingType: listing.listingType || null,
          priceDisplay: listing.priceDisplay || null,
        }),
      )
    : [];
  const cited = (storyPack?.items || []).slice(0, 8).map((item) =>
    dropEmpty({
      collection: item.collection,
      title: item.title || null,
      facet: item.facet,
      subdivision: item.subdivision,
      summary: trim(item.summary, 280),
    }),
  );
  const record = dropEmpty({
    id: island.id,
    name: island.name,
    otherNames: Object.keys(otherNames).length ? otherNames : null,
    nation: island.nation || null,
    type: island.type || null,
    subtype: island.subtype || null,
    archipelago: island.archipelago || null,
    water: island.parentWaterBody?.name || null,
    lat: typeof island.lat === "number" ? +island.lat.toFixed(3) : null,
    lng: typeof island.lng === "number" ? +island.lng.toFixed(3) : null,
    areaKm2: island.areaKm2 > 0 ? +Number(island.areaKm2).toFixed(2) : null,
    highestPointM: island.highestPointM ? Math.round(island.highestPointM) : null,
    highestPointName: island.highestPointName || null,
    population: island.population > 0 ? island.population : null,
    populationNote:
      island.population > 0
        ? null
        : "No population figure is recorded. That is not proof the island is uninhabited.",
    shortDescription: trim(island.shortDescription, 900),
    geography: trim(island.geography, 500),
    history: trim(island.history, 700),
    transport: trim(island.transport, 320),
    accommodation: trim(island.accommodation, 240),
    hasPhoto: !!(island.image || island.images?.length),
    listings,
    cited,
  });
  if (storyPack && storyPack.total > cited.length) {
    record.citedTotal = storyPack.total;
    record.citedNote = `Showing ${cited.length} of ${storyPack.total} cited rows. Pass collection and facet to narrow.`;
  }
  return record;
}

const NATION_SYNONYMS = {
  "Northern Ireland": ["northern ireland"],
  "Crown Dependency": [
    "crown dependency",
    "isle of man",
    "manx",
    "jersey",
    "guernsey",
    "channel islands",
    "channel isle",
  ],
  Scotland: ["scotland", "scottish", "scots", "alba", "caledonia"],
  England: ["england", "english", "cornwall"],
  Wales: ["wales", "welsh", "cymru", "cymraeg"],
  Ireland: ["republic of ireland", "ireland", "irish", "eire"],
};

function phrasePresent(hay, phrase) {
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|[^a-z0-9])${escaped}(?=$|[^a-z0-9])`, "i").test(hay);
}

/** Longer nation names win, so "Northern Ireland" is not also the Republic. */
export function nationsInQuestion(text) {
  let hay = ` ${fold(text)} `;
  const found = [];
  const order = [
    "Northern Ireland",
    "Crown Dependency",
    "Scotland",
    "England",
    "Wales",
    "Ireland",
  ];
  for (const nation of order) {
    const syns = [...NATION_SYNONYMS[nation]].sort((a, b) => b.length - a.length);
    for (const syn of syns) {
      if (!phrasePresent(hay, syn)) continue;
      found.push(nation);
      hay = hay.replace(new RegExp(syn.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), " ");
      break;
    }
  }
  const folded = fold(text);
  if (/\bhighlands?\b/.test(folded) && !/\bhighland park\b/.test(folded) && !found.includes("Scotland")) {
    found.push("Scotland");
  }
  return found;
}

/** "in Loch Lomond" / "on Lough Corrib". A bare "river island" is not a water body. */
export function waterInQuestion(text) {
  const folded = fold(text);
  const match = folded.match(
    /\b(?:in|on|around|of|from)\s+((?:loch|lough|lake|llyn|river)\s+[a-z][a-z'-]{1,24}(?:\s+[a-z][a-z'-]{1,24}){0,2})/,
  );
  if (!match) return null;
  let phrase = match[1].replace(/\b(and|with|that|which|near|islands?|the)\b.*$/, "").trim();
  if (/^(loch|lough|lake|llyn|river)\s+(island|islands|isle|isles)$/.test(phrase)) return null;
  return phrase || null;
}

export function editDistance(a, b) {
  if (a === b) return 0;
  const left = String(a || "");
  const right = String(b || "");
  if (!left.length || !right.length) return Math.max(left.length, right.length);
  if (Math.abs(left.length - right.length) > 2) return 3;
  const prev = new Array(right.length + 1);
  const cur = new Array(right.length + 1);
  for (let j = 0; j <= right.length; j++) prev[j] = j;
  for (let i = 1; i <= left.length; i++) {
    cur[0] = i;
    let rowMin = cur[0];
    for (let j = 1; j <= right.length; j++) {
      const cost = left[i - 1] === right[j - 1] ? 0 : 1;
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
      if (cur[j] < rowMin) rowMin = cur[j];
    }
    if (rowMin > 2) return 3;
    for (let j = 0; j <= right.length; j++) prev[j] = cur[j];
  }
  return prev[right.length];
}

/** A near miss on an island name: "Skie" → Isle of Skye. Exact names win first. */
export function fuzzyIslandByName(raw, islands) {
  const exact = findIslandByName(raw, islands);
  if (exact) return exact;
  const target = fold(raw)
    .replace(/\b(the|isle of|island of)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (target.length < 4 || target.length > 40) return null;
  const maxDist = target.length >= 8 ? 2 : 1;
  let best = null;
  let bestDist = maxDist + 1;
  for (const island of islands || []) {
    if (!namedIsland(island)) continue;
    const name = fold(island.name)
      .replace(/\b(the|isle of|island of)\b/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!name || Math.abs(name.length - target.length) > maxDist) continue;
    const dist = editDistance(target, name);
    if (dist < bestDist || (dist === bestDist && (island.areaKm2 || 0) > (best?.areaKm2 || 0))) {
      bestDist = dist;
      best = island;
    }
  }
  return bestDist <= maxDist ? best : null;
}

/** Closest gazetteer towns when "near Obn" does not resolve. */
export function suggestPlaceNames(raw, places) {
  const target = fold(raw);
  if (!target || target.length < 3) return [];
  const scored = [];
  for (const key of Object.keys(places || {})) {
    const folded = fold(key);
    let dist = editDistance(target, folded);
    if (folded.startsWith(target) || target.startsWith(folded)) dist = Math.min(dist, 1);
    if (dist <= 2) scored.push({ key, dist });
  }
  scored.sort((a, b) => a.dist - b.dist || a.key.localeCompare(b.key));
  const out = [];
  for (const row of scored) {
    if (!out.includes(row.key)) out.push(row.key);
    if (out.length >= 3) break;
  }
  return out;
}

export const CHAT_AGENT_TOOLS = [
  {
    name: "search_islands",
    description:
      "Search named islands. Filters combine with AND. Returns compact rows (no long prose). " +
      "Call read_islands before you describe an island's story. " +
      "population is missing for most islands: inhabited true means a recorded population above zero, not a census. " +
      "Do not invent a loch, a collection, or a place that this tool did not return.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "Name, summit, loch, or words from a cited story. Omit for a pure filter.",
        },
        nation: {
          type: "string",
          enum: NATIONS,
          description: "Ireland is the Republic. Northern Ireland is separate.",
        },
        type: { type: "string", enum: TYPES },
        subtype: {
          type: "string",
          description: "estuary, tidal, canal, reservoir, crannog, or oxbow.",
        },
        archipelago: { type: "string" },
        water: {
          type: "string",
          description: "Parent loch, lough, or river, e.g. Loch Lomond. Sea islands usually have none.",
        },
        near: {
          type: "object",
          properties: {
            place: { type: "string", description: "Town or island name, if you do not have coordinates." },
            label: { type: "string" },
            lat: { type: "number" },
            lng: { type: "number" },
            radiusKm: { type: "number", description: "1–250. Default 40." },
          },
        },
        minAreaKm2: { type: "number" },
        maxAreaKm2: { type: "number" },
        minElevationM: { type: "number" },
        inhabited: { type: "boolean" },
        hasPhoto: { type: "boolean" },
        collection: {
          type: "string",
          description: "Slug from list_collections, e.g. whisky-distilleries or film-art-music.",
        },
        facet: {
          type: "string",
          description: "A facet id from that collection, e.g. islay, film, artwork, silent.",
        },
        sort: {
          type: "string",
          enum: ["relevance", "area", "elevation", "population", "distance", "name"],
        },
        limit: { type: "number", description: "1–12. Default 8." },
      },
    },
  },
  {
    name: "read_islands",
    description:
      "Load the full atlas record for up to 6 islands: description, history, geography, other-language names, and cited works. " +
      "Pass ids from search_islands. Call this before writing more than a clause about an island.",
    parameters: {
      type: "object",
      properties: {
        ids: {
          type: "array",
          items: { type: "string" },
          description: "Atlas ids, or exact island names if you do not have the id yet.",
        },
        collection: { type: "string", description: "Optional. Limit cited rows to this collection slug." },
        facet: { type: "string" },
      },
      required: ["ids"],
    },
  },
  {
    name: "count_islands",
    description:
      "Count islands matching the same filters as search_islands. With no filters, returns the atlas total by nation. " +
      "Use this for how-many questions. Do not guess a count.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string" },
        nation: { type: "string", enum: NATIONS },
        type: { type: "string", enum: TYPES },
        subtype: { type: "string" },
        archipelago: { type: "string" },
        water: { type: "string" },
        near: {
          type: "object",
          properties: {
            place: { type: "string" },
            label: { type: "string" },
            lat: { type: "number" },
            lng: { type: "number" },
            radiusKm: { type: "number" },
          },
        },
        minAreaKm2: { type: "number" },
        maxAreaKm2: { type: "number" },
        minElevationM: { type: "number" },
        inhabited: { type: "boolean" },
        hasPhoto: { type: "boolean" },
        collection: { type: "string" },
        facet: { type: "string" },
        groupBy: {
          type: "string",
          enum: ["nation", "type", "archipelago", "water"],
        },
      },
    },
  },
  {
    name: "list_collections",
    description:
      "List published interest collections (unusual news, whisky, film and art, wildlife, tidal islands, castles, books, traditions, for sale) with their facet ids.",
    parameters: { type: "object", properties: {} },
  },
  {
    name: "show_on_map",
    description:
      "Frame the atlas map and the island list on these ids. Call it when the visitor asks to see places on the map, or to browse a short list you just found. Skip it for a question about one island's story.",
    parameters: {
      type: "object",
      properties: {
        ids: {
          type: "array",
          items: { type: "string" },
          description: "Atlas ids from search_islands or read_islands. At most 80.",
        },
        label: {
          type: "string",
          description: "Short list heading, e.g. Castles in Wales.",
        },
      },
      required: ["ids"],
    },
  },
  {
    name: "reply",
    description:
      "Finish the turn once you have looked the answer up. Call this alone, not in the same step as a search, a read, or show_on_map.",
    parameters: {
      type: "object",
      properties: {
        answer: {
          type: "string",
          description:
            "Natural prose for the visitor. 2–5 sentences, or a short bullet list when they asked for several islands. " +
            "Use **bold** for island names. No HTML.",
        },
        islandIds: {
          type: "array",
          items: { type: "string" },
          description: "Ids you name in the answer, in card order. Only ids returned this turn. Maximum 6. Empty if you are asking a clarifying question.",
        },
        followups: {
          type: "array",
          items: { type: "string" },
          description: "Three short questions the visitor might ask next.",
        },
      },
      required: ["answer", "islandIds", "followups"],
    },
  },
];
