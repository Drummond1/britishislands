/**
 * Query checks for Ask's atlas tools. Run:
 *   node --experimental-default-type=module scripts/test_chat_agent.mjs
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import {
  searchIslands,
  countIslands,
  findIslandByName,
  serialiseIslandRecord,
} from "../chat-agent.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function expand(row) {
  if (!row || row.name !== undefined) return row;
  const island = {
    id: row.id,
    name: row.n,
    lat: row.y,
    lng: row.x,
    type: row.t || "sea",
    nation: row.o || "",
  };
  if (row.a != null) island.areaKm2 = row.a;
  if (row.g) island.archipelago = row.g;
  if (row.s) island.subtype = row.s;
  if (row.p != null) island.population = row.p;
  if (row.h) island.highestPointM = row.h;
  if (row.img) island.hasImage = true;
  return island;
}

const index = JSON.parse(readFileSync(join(root, "data/islands_index.json"), "utf8"));
const islands = (index.rows || []).map(expand);
const corpus = JSON.parse(readFileSync(join(root, "data/chat_corpus.json"), "utf8"));
const interestIndex = JSON.parse(readFileSync(join(root, "data/interest_index.json"), "utf8"));
const ctx = {
  islands,
  interestIndex,
  corpus,
  places: { Oban: [56.4153, -5.4747] },
};

const skye = searchIslands(ctx, { query: "Skye", limit: 5 });
assert.equal(skye.islands[0].name, "Isle of Skye", "Skye should resolve to the Isle of Skye");
assert.equal(skye.islands[0].id, "isle-of-skye");

const lomond = searchIslands(ctx, { water: "Loch Lomond", limit: 12 });
assert.ok(lomond.matched >= 10, `expected many Loch Lomond islands, got ${lomond.matched}`);
assert.ok(lomond.islands.every((row) => /loch lomond/i.test(row.water)));
assert.ok(!lomond.islands.some((row) => row.name === "Unnamed island"));

const islay = searchIslands(ctx, {
  collection: "whisky-distilleries",
  facet: "islay",
  limit: 12,
});
assert.ok(islay.matched >= 1, "Islay whisky facet should match");
assert.ok(islay.islands.some((row) => row.id === "islay"));
assert.ok(!islay.islands.some((row) => row.id === "mainland-orkney"));

const puffin = searchIslands(ctx, { query: "puffin", limit: 8 });
assert.ok(puffin.matched >= 1, "puffin should hit a cited wildlife story");

const near = searchIslands(ctx, { near: { place: "Oban", radiusKm: 25 }, limit: 12 });
assert.ok(near.matched >= 1);
assert.ok(near.islands.every((row) => row.distanceKm <= 25));

const outside = searchIslands(ctx, { near: { lat: 10, lng: 10, radiusKm: 20 } });
assert.match(outside.error, /outside/i);

const broad = searchIslands(ctx, {});
assert.match(broad.error, /no filter/i);

const devenishIe = searchIslands(ctx, { query: "Devenish", nation: "Ireland", limit: 5 });
const devenishNi = searchIslands(ctx, { query: "Devenish", nation: "Northern Ireland", limit: 5 });
assert.ok(devenishNi.matched >= 1);
assert.ok(devenishIe.islands.every((row) => row.nation === "Ireland"));
assert.ok(devenishNi.islands.every((row) => row.nation === "Northern Ireland"));
assert.ok(devenishIe.islands.every((row) => row.id !== devenishNi.islands[0].id));

const totals = countIslands(ctx, {});
assert.ok(totals.total > 5000);
assert.ok(totals.groups.some((group) => group.key === "Ireland"));
assert.ok(totals.groups.some((group) => group.key === "Northern Ireland"));

const mull = findIslandByName("Mull", islands);
assert.equal(mull.id, "mull");
assert.equal(mull.name, "Isle of Mull");

const record = serialiseIslandRecord(
  {
    id: "iona",
    name: "Iona",
    nation: "Scotland",
    type: "sea",
    shortDescription: "Abbey island.",
    names: { en: "Iona", gd: "Ì Chaluim Chille" },
    propertyListings: [
      { title: "A cottage", priceDisplay: "POA", url: "https://example.test/secret" },
    ],
  },
  { total: 1, items: [{ collection: "film-art-music", title: "A song", summary: "About Iona.", facet: "music" }] },
);
assert.equal(record.otherNames.gd, "Ì Chaluim Chille");
assert.equal(record.listings[0].url, undefined);
assert.equal(record.cited[0].title, "A song");
assert.equal(record.ferryRoutes, undefined);

console.log("chat-agent checks passed");
console.log(
  JSON.stringify(
    {
      skye: skye.islands[0].id,
      lomond: lomond.matched,
      islayWhisky: islay.matched,
      puffin: puffin.matched,
      nearOban: near.matched,
      named: totals.total,
    },
    null,
    2,
  ),
);
