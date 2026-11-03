/** Learning/content integrity and failure cases. node --experimental-default-type=module scripts/test_learning.mjs */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { learningProfile, discoveryHook, renderLearningProfile, relatedDiscoveries, renderDiscoveryConnections,
  surpriseIsland, weeklyIsland, recentIslandIds, rememberIsland, factualReferences, answerReferences, sourceUrl, geographicGroups } from "../learning.js";
import { serialiseIslandRecord, storiesForIsland, packToolResult } from "../chat-agent.js";

const doc = JSON.parse(readFileSync(new URL("../data/learning_profiles.json", import.meta.url)));
const islands = JSON.parse(readFileSync(new URL("../data/islands.json", import.meta.url)));
const index = JSON.parse(readFileSync(new URL("../data/interest_index.json", import.meta.url)));
const byId = new Map(islands.map((island) => [island.id, island]));
let checks = 0;
function check(label, fn) { fn(); checks++; console.log(`PASS ${label}`); }

check("20 complete, source-linked profiles and 60 explained connections", () => {
  assert.equal(Object.keys(doc.profiles).length, 20);
  for (const [id, profile] of Object.entries(doc.profiles)) {
    assert.ok(byId.has(id), id);
    assert.equal(profile.facts.length, 3, id);
    assert.ok(profile.timeline.length >= 2, id);
    const sources = new Set(profile.sources.filter((s) => sourceUrl(s.url) && s.attribution && s.licence && /^\d{4}-\d{2}-\d{2}$/.test(s.checkedAt)).map((s) => s.id));
    for (const claim of [profile, ...profile.facts, ...profile.timeline]) {
      assert.ok(claim.sourceIds?.length && claim.sourceIds.every((sid) => sources.has(sid)), id);
    }
    const related = relatedDiscoveries(byId.get(id), index, doc, byId);
    assert.equal(related.length, 3, id);
    assert.equal(new Set(related.map((r) => r.island.id)).size, 3, id);
    assert.ok(related.every((r) => r.island.id !== id && r.reason.length > 20), id);
    const html = renderLearningProfile(profile);
    for (const fact of profile.facts) assert.ok(html.includes(fact.text.replaceAll('&', '&amp;')), id);
  }
});

check("three eight-stop journeys have no missing or repeated islands", () => {
  assert.equal(doc.journeys.length, 3);
  const covered = new Set();
  for (const journey of doc.journeys) {
    assert.equal(journey.stops.length, 8);
    assert.equal(new Set(journey.stops.map((s) => s.id)).size, 8);
    for (const stop of journey.stops) { assert.ok(doc.profiles[stop.id] && byId.has(stop.id)); covered.add(stop.id); }
  }
  assert.equal(covered.size, 20);
});

check("uncertain Llanddwyn identity stays out of the learning pilot", () => {
  assert.equal(doc.profiles['osm-way-310149701'], undefined);
  assert.ok(doc.profiles.anglesey);
  assert.ok(!JSON.stringify(doc.journeys).includes('osm-way-310149701'));
});

check("unknown region labels cannot create false geographic neighbours", () => {
  assert.deepEqual(geographicGroups({archipelago:'—',parentWaterBody:{name:'unknown'}}), {archipelago:'',water:''});
  assert.deepEqual(geographicGroups({archipelago:'',parentWaterBody:{name:'River Thames'}}), {archipelago:'',water:'River Thames'});
});

check("default hooks use meaningful cited stories and degrade without the overlay", () => {
  assert.match(discoveryHook(byId.get('lundy'), index, doc), /puffin coins/i);
  assert.ok(discoveryHook(byId.get('lundy'), index, null).length > 30);
  const thin = { stories: { art: { test: [{ title:'Artwork', summary:'In the Commons category', sourceUrl:'https://example.org' }] } } };
  assert.equal(discoveryHook({id:'test', shortDescription:'Known summary'}, thin, null), 'Known summary');
  assert.equal(learningProfile(null, 'missing'), null);
});

check("discovery never promotes a broken, current or content-free record", () => {
  const picked = surpriseIsland(doc, byId, ['lundy'], () => 0);
  assert.ok(picked && picked.id !== 'lundy' && doc.profiles[picked.id]);
  assert.equal(surpriseIsland(doc, new Map()), null);
  const date = new Date('2026-11-03T12:00:00Z');
  assert.equal(weeklyIsland(doc, byId, date).id, weeklyIsland(doc, byId, date).id);
  assert.equal(weeklyIsland(null, byId, date), null);
});

check("local history handles invalid and blocked storage and stays bounded", () => {
  const memory = new Map(); const storage = { getItem:k=>memory.get(k), setItem:(k,v)=>memory.set(k,v) };
  for (let n=0;n<15;n++) rememberIsland(storage, `island-${n}`);
  assert.equal(recentIslandIds(storage).length, 12);
  rememberIsland(storage, 'island-5'); assert.equal(recentIslandIds(storage)[0], 'island-5');
  const blocked = { getItem(){throw Error('blocked')}, setItem(){throw Error('blocked')} };
  assert.deepEqual(recentIslandIds(blocked), []); assert.doesNotThrow(()=>rememberIsland(blocked, 'lundy'));
  storage.setItem('iobRecentLearningIslands', '{invalid'); assert.deepEqual(recentIslandIds(storage), []);
});

check("Ask records retain evidence; photo credits cannot become factual references", () => {
  const island = byId.get('lundy'); const pack = storiesForIsland(index, island.id);
  assert.ok(pack.items.some((s)=>sourceUrl(s.sourceUrl)));
  const record = serialiseIslandRecord(island, pack, doc.profiles.lundy);
  assert.equal(record.learning.facts.length, 3);
  assert.ok(record.cited.some((s)=>sourceUrl(s.sourceUrl)));
  const refs = factualReferences(island, doc.profiles.lundy, pack);
  assert.ok(refs.some((r)=>r.url === 'https://en.wikipedia.org/wiki/Lundy'));
  assert.ok(!refs.some((r)=>/upload\.wikimedia|File:/.test(r.url)));
});

check("oversized tool output remains parseable with explicit omissions", () => {
  const result = { islands: Array.from({length:6}, (_,n)=>({id:String(n), text:'x'.repeat(5000)})) };
  const text = packToolResult(result); const parsed = JSON.parse(text);
  assert.ok(text.length <= 14000 && parsed.islands.length < 6 && parsed.omittedIds.length);
  assert.equal(parsed.islands.length + parsed.omittedIds.length, 6);
  assert.ok(JSON.parse(packToolResult({text:'x'.repeat(15000)})).error);
});

check("Ask distinguishes cited references from background it read", () => {
  const island = byId.get('lundy');
  const background = {url:'https://en.wikipedia.org/wiki/Lundy', label:'Lundy'};
  const artwork = {url:'https://example.org/artwork', label:'Artwork'};
  assert.deepEqual(answerReferences('A background answer', [background, artwork], [island], doc), {
    label:'Island background read for this answer', items:[background],
  });
  assert.deepEqual(answerReferences('See [artwork](https://example.org/artwork).', [background, artwork], [island], doc), {
    label:'Sources cited in this answer', items:[artwork],
  });
});

check("source protocols and authored text are safely rendered", () => {
  assert.equal(sourceUrl('javascript:alert(1)'), '');
  assert.equal(sourceUrl('https://password@example.org'), '');
  const dangerous = {overview:'<img src=x onerror=alert(1)>', sources:[], facts:[], timeline:[]};
  assert.ok(!renderLearningProfile(dangerous).includes('<img'));
  const html = renderDiscoveryConnections([{island:{id:'bad"',name:'<script>alert(1)</script>'},reason:'<svg onload=alert(1)>'}]);
  assert.ok(!html.includes('<script>') && !html.includes('<svg'));
});
console.log(JSON.stringify({ checks, profiles:20, facts:60, timelineEvents:Object.values(doc.profiles).reduce((n,p)=>n+p.timeline.length,0), connections:60, journeys:3, coveredIslands:20 },null,2));
