/**
 * Browse order for each interest filter.
 *
 * Higher scores sit first. The number is not shown. A search still wins
 * over this order. See docs/METHODOLOGY-INTEREST-RANK.md.
 */

const NAME_SKIP = new Set(["isle", "island", "islands", "isles", "the", "of", "and", "unnamed"]);

function fold(value) {
  return String(value || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "");
}

function storyText(item) {
  return fold(`${item?.title || ""} ${item?.summary || ""} ${item?.tie || ""}`);
}

function hasPicture(item) {
  return Boolean(item?.image?.thumbUrl);
}

/** A picture of the cited subject, not a stand-in photograph of the island. */
export function hasSubjectPicture(item) {
  if (!hasPicture(item)) return false;
  return !fold(item?.image?.note).includes("photograph of the island");
}

function hasIslandStandIn(item) {
  return hasPicture(item) && fold(item?.image?.note).includes("photograph of the island");
}

function richness(item, cap) {
  return Math.min(String(item?.summary || "").length, cap * 100) / 100;
}

export function isThinCitation(item) {
  return /musicbrainz|wikidata q\d+|commons category|in the musicbrainz area/i.test(storyText(item));
}

function plainName(island) {
  return fold(island?.name)
    .replace(/\([^)]*\)/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function islandTokens(island) {
  return plainName(island)
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 5 && !NAME_SKIP.has(token));
}

function mentionsIsland(text, island) {
  const hay = fold(text);
  const full = plainName(island);
  if (full.length >= 4 && hay.includes(full)) return true;
  const short = full.replace(/^isle of /, "");
  if (short.length >= 4 && short !== full && hay.includes(short)) return true;
  return islandTokens(island).some((token) => new RegExp(`\\b${token}\\b`).test(hay));
}

function phraseNearIsland(text, island, pattern) {
  const hay = fold(text);
  const match = hay.match(pattern);
  if (!match || match.index == null) return false;
  const window = hay.slice(Math.max(0, match.index - 90), match.index + match[0].length + 90);
  return mentionsIsland(window, island);
}

function isRiverPlot(island) {
  const name = fold(island?.name);
  return island?.type === "river" || /\beyot\b|\bait\b/.test(name);
}

function bestItem(items, score) {
  let top = 0;
  let seen = false;
  for (const item of items || []) {
    const value = score(item);
    if (!seen || value > top) top = value;
    seen = true;
  }
  return seen ? top : 0;
}

function extraItems(count, each, cap) {
  return each * Math.min(Math.max(count - 1, 0), cap);
}

function scoreNewsItem(item) {
  const text = storyText(item);
  const tiers = [
    [/declared|principality|sovereign|anthrax|vanished|left hirta|last 36|castaway|forty days|\b40 days\b|feudal|politician|whisky from the wreck|beach is the runway|cable car/, 5],
    [/\bking\b|\bprince\b|crowned|parliament|puffin coin|chessmen|dinosaur|rocket|people's republic|bought their island/, 4],
    [/\bfire\b|\bwreck\b|fossil|mermaid|haggis|prisoners of war|chapel|wallab/, 3],
  ];
  let tier = 2;
  for (const [pattern, level] of tiers) {
    if (pattern.test(text)) {
      tier = level;
      break;
    }
  }
  return tier * 8 + (hasSubjectPicture(item) ? 4 : 0) + richness(item, 2);
}

function scoreCastleItem(item, island) {
  const text = storyText(item);
  let score = hasSubjectPicture(item) ? 14 : 0;
  const area = island?.areaKm2;
  if (area == null) score += 1;
  else if (area < 0.05) score += 8;
  else if (area < 1) score += 6;
  else if (area < 8) score += 3;
  else if (area > 200) score -= 5;
  if (/mansion|country house|gothic revival/.test(text)) score -= 8;
  if (/eilean donan|dunvegan|lindisfarne castle|castle rushen|duart|kisimul|caisteal chiosmuil|lochleven|loch leven|carisbrooke|beaumaris|castle stalker|castle tioram|brodick castle|scalloway|peel castle|mont orgueil|rothesay|piel castle|gylen|noltland|st michael/.test(text)) {
    score += 7;
  }
  if (/tower house/.test(text) && !hasSubjectPicture(item)) score -= 5;
  if (plainName(island) === "oxford") score -= 20;
  return score + richness(item, 4);
}

function wildlifeNamesIsland(item, island) {
  const opening = `${item?.title || ""}. ${String(item?.summary || "").slice(0, 320)}`;
  return mentionsIsland(opening, island);
}

/** The island is one name in a list of countries, not the place the species belongs to. */
function listedAmongCountries(text, island) {
  const hay = fold(text);
  const name = plainName(island);
  const at = name ? hay.indexOf(name) : -1;
  if (at < 0) return false;
  const around = hay.slice(Math.max(0, at - 48), at + name.length + 48);
  return /\b(ireland|wales|scotland|england|cornwall|britain|france|europe|normandy)\b/.test(around);
}

function scoreWildlifeItem(item, island) {
  const text = storyText(item);
  const named = wildlifeNamesIsland(item, island);
  const shared = listedAmongCountries(text, island);
  let score = hasSubjectPicture(item) ? 8 : 1;
  if (!shared && ((named && /\bendemic\b/.test(text)) || phraseNearIsland(text, island, /\bendemic\b/))) score += 10;
  if (named && !shared && /subspecies|subsp\.|race of|own unique/.test(text)) score += 5;
  if (mentionsIsland(item?.title, island)) score += 6;
  if (!shared && phraseNearIsland(text, island, /found only|only known|restricted to|confined to|only native|stronghold|the largest/)) {
    score += 5;
  }
  if (/\bextinct\b/.test(text)) score -= 8;
  if (!named && /european hedgehog|red squirrel \(sciurus vulgaris\)/.test(text)) score -= 6;
  return score + richness(item, 3);
}

const FAMOUS_STILL = /laphroaig|lagavulin|ardbeg|bowmore|bruichladdich|caol ila|bunnahabhain|port charlotte|talisker|highland park|\bscapa\b|jura distillery|tobermory|ledaig|arran distillery|harris distillery|abhainn dearg|raasay distillery|torabhaig|ardnahoe/;

function scoreWhiskyItem(item) {
  const facet = item?.facet;
  let score = { distillery: 16, silent: 7, story: 5, planned: 2 }[facet] || 1;
  if (hasSubjectPicture(item)) score += facet === "distillery" ? 8 : 3;
  if (facet === "distillery" && FAMOUS_STILL.test(storyText(item))) score += 5;
  if (facet === "story" && /whisky galore|politician|loch shiel/.test(storyText(item))) score += 3;
  const hints = storyText(item).match(/oldest|founded|established|peated|northernmost|classic malt|\bonly\b/g);
  score += Math.min(hints?.length || 0, 2) * 2;
  return score;
}

const FAMOUS_BOOK = /kidnapped|to the lighthouse|potato peel|whisky galore|the blackhouse|the outrun|catriona|peveril of the peak|mr pye|toilers of the sea|the deemster|the manxman|where the world ends/;

function scoreBookItem(item) {
  let score = hasSubjectPicture(item) ? 12 : hasIslandStandIn(item) ? 4 : 0;
  const text = storyText(item);
  if (/\bnovel\b|\bmemoir\b/.test(text)) score += 3;
  if (FAMOUS_BOOK.test(text)) score += 6;
  return score + richness(item, 4);
}

function scoreTraditionItem(item) {
  const text = storyText(item);
  let score = hasSubjectPicture(item) ? 6 : hasIslandStandIn(item) ? 2 : 0;
  if (/up helly aa|tynwald|sword dance|guga|mailboat|st kilda parliament|\bthe ba\b/.test(text)) score += 14;
  else if (/hop-tu-naa|harris tweed|fair isle knitting|clameur|battle of flowers|stone skimming|fèis|king of /.test(text)) score += 6;
  return score + richness(item, 4);
}

const FAMOUS_WALK = /lindisfarne|holy island|michael's mount|burgh island|cramond|lihou|hilbre|brough of birsay|hestan|northey|oronsay|erraid|omey|davaar|worms head|gateholm|chapel island/;

function scoreTidalIsland(island, otherSlugs) {
  let score = island?.hasImage ? 8 : 0;
  if (FAMOUS_WALK.test(plainName(island))) score += 12;
  score += Math.min((otherSlugs || []).length, 2) * 5;
  const pop = island?.population;
  if (typeof pop === "number" && pop > 0 && pop < 3000) score += 2;
  if (isRiverPlot(island)) score -= 8;
  const area = island?.areaKm2 || 0;
  if (area >= 0.02 && area <= 20) score += 2;
  else if (area > 30) score -= 3;
  return score;
}

const FAMOUS_WORK = /fingal|the hebrides|whisky galore|highlander|father ted|macbeth|edge of the world|skye boat|wet leg|mendelssohn/;

function scoreCultureItem(item) {
  if (isThinCitation(item)) return hasSubjectPicture(item) ? 3 : 1;
  const facet = item?.facet;
  let score = { film: 10, music: 7, artwork: 5 }[facet] || 3;
  if (hasSubjectPicture(item)) score += 6;
  if (FAMOUS_WORK.test(storyText(item))) score += 6;
  return score + richness(item, 4);
}

function scoreCultureIsland(items) {
  const real = (items || []).filter((item) => !isThinCitation(item));
  const pool = real.length ? real : items || [];
  const facets = new Set(real.map((item) => item?.facet).filter(Boolean));
  const variety = facets.size >= 3 ? 4 : facets.size === 2 ? 2 : 0;
  return bestItem(pool, scoreCultureItem) + variety + extraItems(real.length, 0.4, 3);
}

function scoreForSaleIsland(island, items) {
  let score = island?.type === "lake" ? 2 : isRiverPlot(island) ? -8 : 6;
  if (island?.hasImage) score += 5;
  const area = island?.areaKm2 || 0;
  if (area >= 0.02 && area <= 15) score += 4;
  else if (area > 0 && area < 0.02) score += 2;
  else if (area > 40) score -= 4;
  const pop = island?.population;
  if (pop == null || pop <= 30) score += 3;
  else if (pop > 400) score -= 4;
  const titles = fold((items || []).map((item) => item?.title || "").join(" "));
  if (/bungalow|\bresidence\b|\bapartment\b|\bhomes\b|waters edge|croft and house/.test(titles)) score -= 6;
  if (/private island|whole island|acre estate|private islands online|\(vladi\)/.test(titles)) score += 5;
  return score;
}

function scoreWhiskyIsland(items) {
  const rows = items || [];
  const working = rows.filter((item) => item?.facet === "distillery").length;
  return bestItem(rows, scoreWhiskyItem) + extraItems(working, 1.2, 5);
}

/** Score one cited row. Used for the card and the order inside a profile. */
export function scoreCitedItem(slug, item, island) {
  if (!item) return 0;
  if (slug === "unusual-news") return scoreNewsItem(item);
  if (slug === "island-castles") return scoreCastleItem(item, island);
  if (slug === "unusual-wildlife") return scoreWildlifeItem(item, island);
  if (slug === "whisky-distilleries") return scoreWhiskyItem(item);
  if (slug === "island-books") return scoreBookItem(item);
  if (slug === "local-traditions") return scoreTraditionItem(item);
  if (slug === "film-art-music") return scoreCultureItem(item);
  if (slug === "tidal-islands") return hasSubjectPicture(item) ? 2 : 1;
  return hasSubjectPicture(item) ? 2 : 1;
}

/**
 * Score one island inside a filter. `otherSlugs` is every other interest
 * filter that already cites this island.
 */
export function scoreInterestIsland(slug, island, items, otherSlugs) {
  const rows = Array.isArray(items) ? items : [];
  if (slug === "for-sale") return scoreForSaleIsland(island, rows);
  if (slug === "tidal-islands") return scoreTidalIsland(island, otherSlugs);
  if (slug === "film-art-music") return scoreCultureIsland(rows);
  if (slug === "whisky-distilleries") return scoreWhiskyIsland(rows);
  if (slug === "unusual-news") return bestItem(rows, scoreNewsItem) + extraItems(rows.length, 0.75, 2);
  if (slug === "island-castles") {
    return bestItem(rows, (item) => scoreCastleItem(item, island)) + extraItems(rows.length, 0.4, 3);
  }
  if (slug === "unusual-wildlife") {
    return bestItem(rows, (item) => scoreWildlifeItem(item, island)) + extraItems(rows.length, 0.7, 3);
  }
  if (slug === "island-books") return bestItem(rows, scoreBookItem) + extraItems(rows.length, 0.35, 4);
  if (slug === "local-traditions") return bestItem(rows, scoreTraditionItem) + extraItems(rows.length, 0.2, 2);
  return bestItem(rows, (item) => scoreCitedItem(slug, item, island));
}

const REMOTE_OUTPOST = /rockall|north rona|st kilda|staffa|sula sgeir|sùla sgeir/;

/** Uninhabited sea islands with no ferry: storied outposts before empty skerries. */
export function scoreRemoteIsland(island, slugs) {
  if (!island) return 0;
  let score = 0;
  const area = island.areaKm2 || 0;
  if (area > 8000) score -= 40;
  if (island.hasImage) score += 10;
  const cited = (slugs || []).filter((slug) => slug !== "for-sale");
  score += Math.min(cited.length, 3) * 4;
  if (cited.includes("unusual-news")) score += 4;
  if (area >= 0.05 && area <= 40) score += 4;
  else if (area > 100) score -= 4;
  if ((island.highestPointM || 0) >= 100) score += 2;
  if (REMOTE_OUTPOST.test(plainName(island))) score += 8;
  return score;
}

function byScore(rows) {
  rows.sort((a, b) => b.score - a.score || String(a.island?.name || "").localeCompare(String(b.island?.name || "")));
  return rows.map((row) => row.island);
}

export function rankIslands(slug, islands, getItems, getSlugs) {
  const rows = (islands || []).map((island) => ({
    island,
    score: scoreInterestIsland(
      slug,
      island,
      getItems(slug, island?.id) || [],
      (getSlugs(island?.id) || []).filter((item) => item !== slug),
    ),
  }));
  return byScore(rows);
}

export function rankRemoteIslands(islands, getSlugs) {
  const rows = (islands || []).map((island) => ({
    island,
    score: scoreRemoteIsland(island, getSlugs(island?.id) || []),
  }));
  return byScore(rows);
}
