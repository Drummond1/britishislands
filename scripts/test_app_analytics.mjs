/** Offline checks of the real app hooks; no browser, network or visitor data. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const hooks = source.slice(
  source.indexOf("// ---------- Optional, consent-gated analytics ----------"),
  source.indexOf("/** Showcase islands with pre-generated 3D terrain"),
);
function actualFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `missing ${name}`);
  return source.slice(start, source.indexOf("\n}\n", start) + 2);
}

const noop = () => {};
function fixture({ consent = true, api = true } = {}) {
  const calls = [];
  const listeners = new Map();
  const islands = [
    { id: "isle-of-skye", name: "Private test label", lat: 57, lng: -6 },
    { id: "fair-isle", name: "Another label", lat: 59, lng: -1 },
  ];
  const state = {
    byId: new Map(islands.map((island) => [island.id, island])),
    islandIdAliases: { "old-skye": "isle-of-skye" },
    favoriteIds: new Set(), galleries: {}, activeId: null,
  };
  const context = vm.createContext({
    URL,
    console,
    window: api ? { fmiAnalytics: { track(event, params) {
      if (!consent) return false;
      calls.push(JSON.parse(JSON.stringify({ event, params })));
      return true;
    } } } : {},
    document: {
      addEventListener: (name, fn) => listeners.set(name, fn),
      getElementById: () => null,
      body: { classList: { contains: () => false, remove: noop }, dataset: {} },
    },
    state,
    els: { details: {}, listSection: {}, filterForSale: {} },
    map: {},
    mobileNav: { isActive: () => false },
    dismissMapHint: noop,
    syncIslandUrl: noop,
    scheduleRenderListWindow: noop,
    renderDetails: noop,
    scheduleIsland3DMount: noop,
    loadAndShowPolygon: noop,
    loadGalleries: () => Promise.resolve(),
    loadCauseways: () => Promise.resolve(),
    refreshFerriesInPlace: noop,
    applyIslandSeo: noop,
    ensureIslandDetailLoaded: (island) => Promise.resolve(island),
    markJustSaved: noop,
    persistFavoriteIds: noop,
    updateSavedUiChrome: noop,
    rebuildMarkerLayer: noop,
    syncDetailsFavoriteButton: noop,
    clearAskFocus: noop,
    interestCategories: () => [{ slug: "castles" }, { slug: "for-sale" }],
    renderScotlandQuickChips: noop,
    renderInterestFilters: noop,
    renderBrowseQuickChips: noop,
    syncInterestUrl: noop,
    applyFilters: noop,
    closeOsIslandView: noop,
    viewBeforeIsland: null,
    atlasViewLock: 0,
    resetIslandSeo: noop,
    hideMapIslandPeek: noop,
    syncListVirtualPauseState: noop,
    syncChatLauncherContext: noop,
    atlasViews: [],
    syncAtlasBackControl: noop,
  });
  vm.runInContext(actualFunction("canonicalIslandId"), context);
  vm.runInContext(hooks, context);
  for (const name of ["toggleFavoriteIsland", "setActiveInterest", "focusIsland", "releaseIslandDetailView"]) {
    vm.runInContext(actualFunction(name), context);
  }
  return { context, calls, listeners, islands, state };
}

// Optional analytics must neither break the atlas nor replay pre-consent actions.
for (const options of [{ api: false }, { consent: false }]) {
  const { context, calls, islands } = fixture(options);
  context.trackOpenedIsland(islands[0]);
  assert.equal(calls.length, 0);
}
{
  const { context, islands } = fixture();
  context.window.fmiAnalytics.track = () => { throw new Error("Unavailable analytics"); };
  assert.doesNotThrow(() => context.trackOpenedIsland(islands[0]));
}

// A stub plus its full-record callback is one view, with metadata applied first.
{
  const { context, calls, state } = fixture();
  const order = [];
  context.renderDetails = () => order.push("render");
  context.applyIslandSeo = () => order.push("seo");
  context.window.fmiAnalytics.track = (event, params) => {
    assert.equal(order.at(-1), "seo", "page_view must use the updated canonical");
    calls.push({ event, params: { ...params } });
  };
  context.focusIsland("isle-of-skye", { fly: false, fromHistory: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(order.filter((step) => step === "render").length, 2);
  assert.deepEqual(calls.map(({ event }) => event), ["page_view", "island_view"]);
  context.focusIsland("isle-of-skye", { fly: false, fromHistory: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.length, 2, "opening the current island again must not duplicate the view");
  context.focusIsland("fair-isle", { fly: false, fromHistory: true });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls.filter(({ event }) => event === "island_view").length, 2);
  assert.equal(state.activeId, "fair-isle");
  context.window.fmiAnalytics.track = (event, params) => calls.push({ event, params: { ...params } });
  context.releaseIslandDetailView({ clearUrl: true });
  context.trackOpenedIsland(state.byId.get("fair-isle"));
  assert.equal(calls.filter(({ event }) => event === "island_view").length, 3,
    "closing and reopening is a new island view");
  assert.ok(calls.every(({ params }) => Object.keys(params).every((key) => key === "island_id")));
}

// No event when detail rendering fails or the requested island does not exist.
{
  const { context, calls } = fixture();
  context.focusIsland("unknown-island", { fly: false, fromHistory: true });
  assert.equal(calls.length, 0);
  context.renderDetails = () => { throw new Error("Render failed"); };
  assert.throws(() => context.focusIsland("isle-of-skye", { fly: false, fromHistory: true }));
  assert.equal(calls.length, 0);
}

// Save additions count; removals and unknown IDs never do.
{
  const { context, calls } = fixture();
  context.toggleFavoriteIsland("isle-of-skye");
  context.toggleFavoriteIsland("isle-of-skye");
  context.toggleFavoriteIsland("unknown-island");
  assert.deepEqual(calls, [{ event: "island_save", params: { island_id: "isle-of-skye" } }]);
}

// Only a selected category from the published index is sent, never free text.
{
  const { context, calls } = fixture();
  context.setActiveInterest("castles");
  context.setActiveInterest("castles"); // deselect
  context.setActiveInterest("private search text or email@example.com");
  assert.deepEqual(calls, [{ event: "interest_select", params: { category: "castles" } }]);
}

// Both broker link surfaces use a single delegated handler; payloads contain no URL path/query.
{
  const { context, calls, listeners } = fixture();
  assert.equal(listeners.get("click"), listeners.get("auxclick"));
  const activation = (href, id = "isle-of-skye", extra = {}) => ({
    type: "click", button: 0, defaultPrevented: false,
    target: { closest(selector) {
      assert.equal(selector, "a[data-broker-island]");
      return { href, getAttribute: () => id };
    } }, ...extra,
  });
  context.trackBrokerLinkActivation(activation("https://broker.example/listing/private?email=hidden@example.com#notes"));
  context.trackBrokerLinkActivation(activation("https://broker.example/listing?token=secret", "old-skye",
    { type: "auxclick", button: 1 }));
  context.trackBrokerLinkActivation(activation("https://broker.example", "unknown"));
  context.trackBrokerLinkActivation(activation("javascript:alert(1)"));
  context.trackBrokerLinkActivation(activation("https://broker.example", "isle-of-skye", { defaultPrevented: true }));
  context.trackBrokerLinkActivation(activation("https://broker.example", "isle-of-skye", { type: "auxclick", button: 2 }));
  assert.deepEqual(calls, Array.from({ length: 2 }, () => ({
    event: "broker_click", params: { island_id: "isle-of-skye", outbound_host: "broker.example" },
  })));
  for (const name of ["propertyListingPopupHtml", "renderPropertyListings"]) {
    assert.match(actualFunction(name), /data-broker-island="\$\{escapeAttr\(island\.id\)\}"/);
  }
}

console.log("ok: consent-safe app hooks, island view deduplication, additions-only saves, published categories and broker host privacy");
