const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
function extract(name) {
  const start = source.indexOf(`function ${name}(`);
  assert(start >= 0, name);
  const next = source.indexOf('\nfunction ', start + 1);
  return source.slice(start, next < 0 ? source.length : next).replace(/\n\/\/[^\n]*(?:\n\/\/[^\n]*)*\s*$/, '');
}
const ctx = {state: {galleries: {}, byId: new Map()}, window:{}, escapeAttr:s=>String(s??'').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;'), escapeHtml:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;'),renderAttribution:i=>`<div class="hero-attrib">${i.attribution} ${i.license}</div>`};
vm.createContext(ctx);
for (const name of ['normalizeCommonsFileName','imageDedupKey','dedupeImagesByKey','ensureGalleryMerged','renderSupportingPhotos','renderGallery','islandHasPhoto','islandThumbUrl']) vm.runInContext(extract(name),ctx);
// renderHeroImg has a following assigned fallback, so take it with the fallback.
vm.runInContext(source.slice(source.indexOf('function renderHeroImg('),source.indexOf('\nfunction renderAttribution(')),ctx);
const lead={url:'https://example.org/lead.jpg',primary:true,source:'test',attribution:'Lead author',license:'CC BY 4.0'};
const context={url:'https://example.org/context.jpg',contextOnly:true,caption:'Neighbouring harbour & landmark',source:'test',attribution:'Context author',license:'CC BY-SA 4.0'};
const regular={url:'https://example.org/regular.jpg',source:'test',attribution:'Regular author',license:'CC BY 4.0'};
function setup(images, extras) {const island={id:'test',name:'Test Island',images:JSON.parse(JSON.stringify(images)),image:''};ctx.state.galleries={test:JSON.parse(JSON.stringify(extras))};ctx.state.byId=new Map([['test',island]]);return island;}
let checks=[];
let i=setup([], [context]);
assert.equal(ctx.islandThumbUrl(i),null);assert.equal(ctx.islandHasPhoto(i),false);checks.push('context-only sidecar never supplies list/featured thumbnail or photo-coverage flag');
ctx.ensureGalleryMerged(i);assert.equal(i.images.length,0);assert.equal(ctx.renderGallery(i),'');checks.push('no-main-photo case preserves empty hero');
let support=ctx.renderSupportingPhotos(i);assert(support.includes('Neighbouring harbour &amp; landmark'));assert(support.includes('Context author'));assert(support.includes('CC BY-SA 4.0'));assert(support.includes('context.jpg'));checks.push('supporting photo retains visible actual-scene caption and credit');
i=setup([], [context,regular]);assert.equal(ctx.islandThumbUrl(i),regular.url);assert.equal(ctx.islandHasPhoto(i),true);ctx.ensureGalleryMerged(i);assert.equal(i.images.length,1);assert.equal(i.images[0].url,regular.url);assert(!ctx.renderGallery(i).includes('context.jpg'));checks.push('mixed sidecar skips context first entry and keeps ordinary cover eligibility');
i=setup([lead], [context,regular]);ctx.ensureGalleryMerged(i);let hero=ctx.renderGallery(i);assert(hero.includes('lead.jpg'));assert(hero.includes('regular.jpg'));assert(!hero.includes('context.jpg'));checks.push('lead and ordinary gallery remain in hero while context stays separate');
ctx.ensureGalleryMerged(i);assert.equal(i.images.length,2);checks.push('repeated merge is stable');
function heroFixture(island){const classes=new Set();const hero={dataset:{islandId:island.id,activeIdx:'0'},classList:{add:c=>classes.add(c)},querySelector:()=>null,querySelectorAll:()=>[]};const el={src:lead.url,style:{},closest:()=>hero};return {hero,el,classes};}
i=setup([lead],[context]);ctx.ensureGalleryMerged(i);let f=heroFixture(i);ctx.window.__heroFallback(f.el);assert(f.classes.has('hero-failed'));assert.equal(f.el.src,lead.url);checks.push('failed sole lead does not fall back to contextual photograph');
i=setup([lead],[context,regular]);ctx.ensureGalleryMerged(i);f=heroFixture(i);ctx.window.__heroFallback(f.el);assert.equal(f.el.src,regular.url);ctx.window.__heroFallback(f.el);assert(f.classes.has('hero-failed'));assert.notEqual(f.el.src,context.url);checks.push('failed lead tries only eligible ordinary gallery then stops');
i=setup([],[]);assert(ctx.renderSupportingPhotos(i).includes(' hidden'));checks.push('empty support section stays hidden');
i=setup([context],[]);assert.equal(ctx.islandThumbUrl(i),null);assert.equal(ctx.islandHasPhoto(i),false);checks.push('list and coverage helpers defensively ignore canonical context entries');
const report={checkedAt:new Date().toISOString(),checks:checks.length,passed:true,behaviours:checks};console.log(JSON.stringify(report,null,2));
