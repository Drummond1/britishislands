/** Offline consent and privacy regression checks: node scripts/test_analytics_consent.mjs */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../analytics.js", import.meta.url), "utf8");
const STORAGE_KEY = "fmi.analytics.consent.v1";
const SESSION_DENIAL_KEY = "fmi.analytics.denied.v1";
const GA_DISABLE_KEY = "ga-disable-G-GGXR2KHHCZ";
const allowedEvents = new Set([
  "page_view", "map_open", "island_view", "island_save", "interest_select", "broker_click",
]);

function browser({ stored, storageError = false, writeError = false, removeError = false,
  sessionError = false, sessionStored,
  href = "https://www.findmyisland.com/?ask=private-question#private-fragment",
  canonical = "https://www.findmyisland.com/", referrer = "", cookies = "" } = {}) {
  const listeners = new Map();
  const windowListeners = new Map();
  const storage = new Map(stored ? [[STORAGE_KEY, stored]] : []);
  const session = new Map(sessionStored ? [[SESSION_DENIAL_KEY, sessionStored]] : []);
  const cookieWrites = [];
  const operations = [];
  let optOutFlag;
  let reloads = 0;
  let navigations = 0;
  let canonicalHref = canonical;
  const document = { readyState: "complete", referrer, activeElement: null };
  class Element {
    constructor(tag) {
      this.tagName = tag.toUpperCase();
      this.children = [];
      this.attributes = {};
      this.listeners = new Map();
      this.hidden = false;
      this.className = "";
    }
    append(...nodes) { this.children.push(...nodes); }
    appendChild(node) { this.append(node); return node; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, callback) { this.listeners.set(name, callback); }
    focus() { document.activeElement = this; }
    click() { this.listeners.get("click")?.({ target: this }); }
    closest(selector) {
      return selector === "a.lp-cta" && this.tagName === "A"
        && this.className.split(/\s+/).includes("lp-cta") ? this : null;
    }
  }
  document.body = new Element("body");
  document.head = new Element("head");
  document.createElement = (tag) => new Element(tag);
  document.querySelector = (selector) => selector === 'link[rel="canonical"]' && canonicalHref
    ? { href: canonicalHref } : null;
  document.getElementById = (id) => {
    const visit = (node) => node.id === id ? node : node.children.map(visit).find(Boolean);
    return visit(document.body) || visit(document.head);
  };
  document.addEventListener = (event, callback) => listeners.set(event, callback);
  Object.defineProperty(document, "cookie", {
    get: () => cookies,
    set: (value) => {
      operations.push({ operation: "cookie", optOut: optOutFlag });
      cookieWrites.push(value);
    },
  });
  const address = new URL(href);
  const window = {
    location: {
      href, origin: address.origin, hostname: address.hostname, protocol: address.protocol,
      reload: () => {
        operations.push({ operation: "reload", optOut: optOutFlag });
        reloads += 1;
      },
      replace(value) {
        operations.push({ operation: "navigate", optOut: optOutFlag });
        navigations += 1;
        const next = new URL(value);
        Object.assign(this, { href: next.href, origin: next.origin, hostname: next.hostname, protocol: next.protocol });
      },
    },
    addEventListener: (event, callback) => windowListeners.set(event, callback),
    localStorage: {
      getItem(key) { if (storageError) throw new Error("storage blocked"); return storage.get(key) ?? null; },
      setItem(key, value) {
        operations.push({ operation: "store", optOut: optOutFlag });
        if (writeError) throw new Error("storage full");
        storage.set(key, value);
      },
      removeItem(key) { if (removeError) throw new Error("storage blocked"); storage.delete(key); },
    },
    sessionStorage: {
      getItem(key) { if (sessionError) throw new Error("session storage blocked"); return session.get(key) ?? null; },
      setItem(key, value) { if (sessionError) throw new Error("session storage blocked"); session.set(key, value); },
      removeItem(key) { if (sessionError) throw new Error("session storage blocked"); session.delete(key); },
    },
  };
  Object.defineProperty(window, GA_DISABLE_KEY, {
    get: () => optOutFlag,
    set(value) {
      optOutFlag = value;
      operations.push({ operation: "optOut", value });
    },
  });
  vm.runInNewContext(source, { window, document, URL, console });
  const scripts = () => document.head.children.filter((node) => node.tagName === "SCRIPT");
  const events = () => (window.dataLayer || []).filter((row) => allowedEvents.has(row.event));
  return {
    window, document, storage, session, scripts, events, cookieWrites, operations,
    reloads: () => reloads,
    navigations: () => navigations,
    storageEvent(key, newValue) {
      if (key === null) storage.clear();
      else if (newValue === null) storage.delete(key);
      else storage.set(key, newValue);
      windowListeners.get("storage")({ key, newValue });
    },
    canonical: (value) => { canonicalHref = value; },
    accept: () => document.getElementById("fmi-analytics-accept").click(),
    decline: () => document.getElementById("fmi-analytics-decline").click(),
    loaded: () => scripts()[0].onload(),
    clickMap(href) {
      const anchor = new Element("a");
      anchor.className = "lp-cta";
      anchor.href = href;
      listeners.get("click")({ target: anchor });
    },
  };
}

const fresh = browser();
assert.equal(fresh.scripts().length, 0, "no remote script before consent");
assert.equal(fresh.window.dataLayer, undefined, "no event queue before consent");
assert.equal(fresh.window[GA_DISABLE_KEY], true, "unknown consent defaults to measurement opt-out");
assert.equal(fresh.window.fmiAnalytics.track("island_view", { island_id: "islay" }), false);
fresh.clickMap("https://www.findmyisland.com/?ask=private-question");
assert.equal(fresh.events().length, 0, "pre-consent actions are discarded");
assert.equal(fresh.document.getElementById("fmi-analytics-preferences").hidden, false);

fresh.decline();
assert.equal(fresh.storage.get(STORAGE_KEY), "denied");
assert.equal(fresh.scripts().length, 0, "initial decline never loads tags");
assert.equal(fresh.reloads(), 0, "initial decline does not reload");
assert.equal(fresh.window[GA_DISABLE_KEY], true);
fresh.window.fmiAnalytics.openSettings();
assert.equal(fresh.window[GA_DISABLE_KEY], true, "opening settings cannot reset a denial");
assert.equal(fresh.document.getElementById("fmi-analytics-preferences").hidden, false);
assert.equal(fresh.document.activeElement.id, "fmi-analytics-accept");
fresh.accept();
assert.equal(fresh.window[GA_DISABLE_KEY], false, "only explicit acceptance clears opt-out");
assert.equal(fresh.storage.get(STORAGE_KEY), "granted");
assert.equal(fresh.scripts().length, 1, "later opt-in loads one container");
assert.match(fresh.scripts()[0].src, /gtm\.js\?id=GTM-M2T6LN5J$/);
assert.equal(fresh.scripts()[0].referrerPolicy, "origin", "GTM request cannot expose the page query as a referrer");
assert.equal(fresh.events().length, 0, "initial page view waits for GTM load");
fresh.loaded();
assert.equal(fresh.events().length, 1);
assert.equal(fresh.events()[0].event, "page_view");
assert.equal(fresh.events()[0].page_location, "https://www.findmyisland.com/");
assert.equal(fresh.window.fmiAnalytics.track("page_view"), false, "same canonical page is deduplicated");
assert.equal(fresh.events().length, 1, "pre-consent map action was not replayed");

fresh.canonical("https://www.findmyisland.com/islands/scotland/islay/?ask=secret#token");
assert.equal(fresh.window.fmiAnalytics.track("page_view", { island_id: "islay" }), true);
assert.equal(fresh.window.fmiAnalytics.track("page_view", { island_id: "islay" }), false);
fresh.canonical("https://www.findmyisland.com/");
assert.equal(fresh.window.fmiAnalytics.track("page_view"), true, "A to B to A is a genuine return");
assert.equal(fresh.events().length, 3);

for (const event of allowedEvents) {
  if (event !== "page_view") assert.equal(fresh.window.fmiAnalytics.track(event), true);
}
for (const event of ["send", "submit", "email", "arbitrary_custom_event"]) {
  assert.equal(fresh.window.fmiAnalytics.track(event, { email: "private@example.org" }), false);
}
fresh.window.fmiAnalytics.track("broker_click", {
  island_id: "osm-relation-1234", category: "for-sale", outbound_host: "WWW.EXAMPLE.ORG",
  ask: "private question", email: "private@example.org", name: "Private Name",
  notes: "private note", latitude: 55.123, longitude: -6.321, api_key: "PRIVATE_KEY",
  page_location: "https://evil.example/private", page_referrer: "https://evil.example/private",
});
const broker = fresh.events().at(-1);
assert.equal(broker.island_id, "osm-relation-1234");
assert.equal(broker.category, "for-sale");
assert.equal(broker.outbound_host, "www.example.org");
assert.deepEqual(Object.keys(broker).sort(), [
  "event", "island_id", "category", "outbound_host", "page_location", "page_referrer",
].sort());
assert.ok(!JSON.stringify(fresh.window.dataLayer).includes("PRIVATE_KEY"));
assert.ok(!JSON.stringify(fresh.window.dataLayer).includes("private-question"));
fresh.window.fmiAnalytics.track("island_view", {
  island_id: "private@example.org", category: "private-text", outbound_host: "https://example.org/private",
});
assert.equal(fresh.events().at(-1).island_id, null);
assert.equal(fresh.events().at(-1).category, null);
assert.equal(fresh.events().at(-1).outbound_host, null, "stale parameters are cleared too");
for (const island_id of ["an-caipín", "da-rønnie-stane", "carn-a\u0301rd"]) {
  fresh.window.fmiAnalytics.track("island_view", { island_id });
  assert.equal(fresh.events().at(-1).island_id, island_id, "public IDs retain letters and combining marks");
}

const returning = browser({ stored: "granted", referrer: "https://chatgpt.com/c/PRIVATE?token=SECRET#fragment" });
assert.equal(returning.scripts().length, 1);
returning.loaded();
assert.equal(returning.events()[0].page_referrer, "https://chatgpt.com/");
assert.ok(!JSON.stringify(returning.window.dataLayer).includes("SECRET"));
assert.ok(!JSON.stringify(returning.window.dataLayer).includes("PRIVATE"));
const internal = browser({ stored: "granted", referrer: "https://www.findmyisland.com/collections/island-books/?ask=SECRET#fragment" });
internal.loaded();
assert.equal(internal.events()[0].page_referrer, "https://www.findmyisland.com/collections/island-books/");
const hostileCanonical = browser({ stored: "granted", canonical: "https://other.example/private@example.org?api_key=SECRET" });
hostileCanonical.loaded();
assert.equal(hostileCanonical.events()[0].page_location, "https://www.findmyisland.com/");
for (const path of ["/contact/", "/editorial-policy/"]) {
  const trust = browser({ stored: "granted", canonical: "https://www.findmyisland.com" + path });
  trust.loaded();
  assert.equal(trust.events()[0].page_location, "https://www.findmyisland.com" + path);
}

const denied = browser({ stored: "denied" });
assert.equal(denied.scripts().length, 0);
assert.equal(denied.document.getElementById("fmi-analytics-preferences").hidden, true);
assert.equal(denied.window.fmiAnalytics.track("map_open"), false);
assert.equal(denied.window[GA_DISABLE_KEY], true, "saved denial retains measurement opt-out");
denied.window.fmiAnalytics.openSettings();
assert.equal(denied.window[GA_DISABLE_KEY], true);
denied.window.fmiAnalytics.track("page_view");
assert.ok(!denied.operations.some((row) => row.operation === "optOut" && row.value === false),
  "denied page lifecycle must never re-enable measurement");
const blockedStorage = browser({ storageError: true, writeError: true });
assert.equal(blockedStorage.scripts().length, 0, "unreadable storage defaults to off");
blockedStorage.accept();
blockedStorage.loaded();
assert.equal(blockedStorage.events().length, 1, "explicit page-only consent works if storage fails");

const withdrawal = browser({ stored: "granted", cookies: "_ga=ANALYTICS; _ga_STREAM=SESSION; session=KEEP" });
withdrawal.loaded();
const beforeWithdrawal = withdrawal.window.dataLayer.length;
const beforeWithdrawalOperations = withdrawal.operations.length;
withdrawal.window.fmiAnalytics.openSettings();
withdrawal.decline();
const withdrawalOperations = withdrawal.operations.slice(beforeWithdrawalOperations);
assert.deepEqual(withdrawalOperations[0], { operation: "optOut", value: true },
  "measurement opt-out must be the first withdrawal side effect");
assert.ok(withdrawalOperations.filter((row) => ["store", "cookie", "reload"].includes(row.operation))
  .every((row) => row.optOut === true), "opt-out precedes persistence, cookie removal and unload");
assert.equal(withdrawal.window[GA_DISABLE_KEY], true);
withdrawal.scripts()[0].onload();
assert.equal(withdrawal.window[GA_DISABLE_KEY], true, "a late tag load cannot reset withdrawal");
assert.equal(withdrawal.storage.get(STORAGE_KEY), "denied");
assert.equal(withdrawal.reloads(), 1, "withdrawal removes previously loaded tags through reload");
assert.equal(withdrawal.window.fmiAnalytics.track("island_view", { island_id: "islay" }), false);
assert.equal(withdrawal.window.dataLayer.length, beforeWithdrawal, "withdrawal emits no denied-mode ping or event");
assert.ok(withdrawal.cookieWrites.some((cookie) => cookie.startsWith("_ga=; Max-Age=0;")));
assert.ok(withdrawal.cookieWrites.some((cookie) => cookie.startsWith("_ga_STREAM=; Max-Age=0;")));
assert.ok(withdrawal.cookieWrites.some((cookie) => cookie.includes("Domain=.findmyisland.com")));
assert.ok(withdrawal.cookieWrites.every((cookie) => !cookie.startsWith("session=")), "unrelated cookies remain");

const fullStore = browser({ stored: "granted", writeError: true });
fullStore.loaded();
fullStore.decline();
assert.equal(fullStore.storage.has(STORAGE_KEY), false, "withdrawal removes the stale grant if writing denial fails");
assert.equal(fullStore.session.get(SESSION_DENIAL_KEY), "denied");
assert.equal(fullStore.reloads(), 1);
const afterFullStoreReload = browser({ stored: fullStore.storage.get(STORAGE_KEY), sessionStored: fullStore.session.get(SESSION_DENIAL_KEY) });
assert.equal(afterFullStoreReload.scripts().length, 0, "a failed denial write cannot restart tracking after reload");

const sessionFallback = browser({ stored: "granted", writeError: true, removeError: true });
sessionFallback.loaded();
sessionFallback.decline();
assert.equal(sessionFallback.storage.get(STORAGE_KEY), "granted");
assert.equal(sessionFallback.session.get(SESSION_DENIAL_KEY), "denied");
const afterSessionReload = browser({ stored: "granted", sessionStored: "denied" });
assert.equal(afterSessionReload.scripts().length, 0, "tab denial takes precedence over an unwritable saved grant");

const allStorageBlocked = browser({ stored: "granted", writeError: true, removeError: true, sessionError: true });
allStorageBlocked.loaded();
const beforeBlockedWithdrawal = allStorageBlocked.window.dataLayer.length;
allStorageBlocked.decline();
assert.equal(allStorageBlocked.reloads(), 0, "do not reload directly into an unchangeable old grant");
assert.equal(allStorageBlocked.navigations(), 1, "force document unload with a controlled off marker");
assert.equal(allStorageBlocked.window[GA_DISABLE_KEY], true);
assert.ok(allStorageBlocked.operations.filter((row) => row.operation === "navigate")
  .every((row) => row.optOut === true), "fallback navigation starts only after measurement opt-out");
assert.equal(allStorageBlocked.window.location.href, "https://www.findmyisland.com/?fmi_analytics=off");
assert.equal(allStorageBlocked.window.dataLayer.length, beforeBlockedWithdrawal, "fallback withdrawal sends no ping");
const afterBlockedNavigation = browser({
  stored: "granted", writeError: true, removeError: true, sessionError: true,
  href: allStorageBlocked.window.location.href,
});
assert.equal(afterBlockedNavigation.scripts().length, 0, "off marker prevents automatic restart despite the stale grant");
assert.equal(afterBlockedNavigation.window.fmiAnalytics.track("page_view"), false);
assert.equal(afterBlockedNavigation.window[GA_DISABLE_KEY], true, "off marker keeps measurement disabled");
const blockedIsland = browser({
  stored: "granted", writeError: true, removeError: true, sessionError: true,
  canonical: "https://www.findmyisland.com/islands/scotland/islay/",
});
blockedIsland.loaded();
blockedIsland.decline();
assert.equal(blockedIsland.window.location.href, "https://www.findmyisland.com/islands/scotland/islay/?fmi_analytics=off", "fallback preserves the readable canonical island page");

for (const newValue of ["denied", null]) {
  const otherTab = browser({ stored: "granted" });
  otherTab.loaded();
  const beforeOtherTabWithdrawal = otherTab.window.dataLayer.length;
  const beforeOtherTabOperations = otherTab.operations.length;
  otherTab.storageEvent(STORAGE_KEY, newValue);
  const otherTabOperations = otherTab.operations.slice(beforeOtherTabOperations);
  assert.deepEqual(otherTabOperations[0], { operation: "optOut", value: true },
    "cross-tab withdrawal sets the opt-out before any unload work");
  assert.equal(otherTab.window[GA_DISABLE_KEY], true);
  assert.ok(otherTabOperations.filter((row) => row.operation === "reload")
    .every((row) => row.optOut === true));
  assert.equal(otherTab.reloads(), 1, "another tab's denial or removal unloads active tags");
  assert.equal(otherTab.window.fmiAnalytics.track("island_view", { island_id: "islay" }), false);
  assert.equal(otherTab.window.dataLayer.length, beforeOtherTabWithdrawal, "cross-tab withdrawal sends no ping");
}

const map = browser({ stored: "granted" });
map.loaded();
map.clickMap("https://www.findmyisland.com/?interest=island-books&ask=PRIVATE");
assert.equal(map.events().at(-1).event, "map_open");
assert.equal(map.events().at(-1).category, "island-books");
assert.ok(!JSON.stringify(map.events()).includes("PRIVATE"));
const beforeExternal = map.events().length;
map.clickMap("https://external.example/?interest=island-books");
assert.equal(map.events().length, beforeExternal);
const local = browser({ stored: "granted", href: "http://localhost:8000/" });
assert.equal(local.scripts().length, 0, "local previews cannot pollute production analytics");

const commands = returning.window.dataLayer.filter((row) => row[0] === "set" || row[0] === "consent");
const settings = commands.find((row) => row[0] === "set")[1];
assert.equal(settings.send_page_view, false);
assert.equal(settings.allow_google_signals, false);
assert.equal(settings.allow_ad_personalization_signals, false);
for (const command of commands.filter((row) => row[0] === "consent")) {
  assert.equal(command[2].ad_storage, "denied");
  assert.equal(command[2].ad_user_data, "denied");
  assert.equal(command[2].ad_personalization, "denied");
}

console.log("Analytics consent, withdrawal, URL sanitisation and event contract checks passed.");
