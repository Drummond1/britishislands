/* Optional, consent-gated analytics. Never pass visitor text to this API. */
(function initialiseAnalytics(window, document) {
  "use strict";
  if (window.fmiAnalytics) return;

  const CONTAINER_ID = "GTM-M2T6LN5J";
  const STORAGE_KEY = "fmi.analytics.consent.v1";
  const SESSION_DENIAL_KEY = "fmi.analytics.denied.v1";
  const SITE_HOSTS = new Set(["findmyisland.com", "www.findmyisland.com"]);
  const EVENTS = new Set([
    "page_view", "map_open", "island_view", "island_save", "interest_select", "broker_click",
  ]);
  const CATEGORIES = new Set([
    "all", "island-castles", "whisky-distilleries", "tidal-islands", "for-sale",
    "unusual-wildlife", "island-books", "local-traditions", "unusual-news", "film-art-music",
  ]);
  const PUBLIC_PATH = /^(?:\/(?:about|methodology|sources-licensing|corrections|dataset|contact|editorial-policy)\/|\/(?:islands|collections)\/(?:[a-z0-9-]+\/){0,2})$/;
  let consent = "unknown";
  let ready = false;
  let started = false;
  let pending = [];
  let lastPageLocation = "";
  let banner;
  let settingsButton;

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "granted" || stored === "denied") consent = stored;
  } catch {
    // Private browsing and blocked storage must leave analytics off by default.
  }
  try {
    if (window.sessionStorage.getItem(SESSION_DENIAL_KEY) === "denied") consent = "denied";
  } catch { /* Session storage may be restricted independently. */ }
  try {
    if (new URL(window.location.href).searchParams.get("fmi_analytics") === "off") consent = "denied";
  } catch { /* An unreadable address must never opt a visitor in. */ }

  function publicPath(pathname) {
    const path = pathname === "/index.html" ? "/" : pathname;
    return path === "/" || PUBLIC_PATH.test(path) ? path : "/";
  }

  function pageContext() {
    let pageLocation = "https://www.findmyisland.com/";
    let pageReferrer = "";
    try {
      const current = new URL(window.location.href);
      const canonical = document.querySelector('link[rel="canonical"]');
      const candidate = new URL(canonical ? canonical.href : current.href, current);
      const chosen = candidate.protocol === "https:" && SITE_HOSTS.has(candidate.hostname)
        ? candidate : current;
      pageLocation = chosen.origin + publicPath(chosen.pathname);
    } catch {
      // Never fall back to an unfiltered address.
    }
    try {
      const referrer = new URL(document.referrer);
      if (referrer.protocol === "https:" || referrer.protocol === "http:") {
        // External referrers need only their origin; paths may identify private documents.
        pageReferrer = referrer.origin
          + (SITE_HOSTS.has(referrer.hostname) ? publicPath(referrer.pathname) : "/");
      }
    } catch {
      // No referrer, or an unsupported protocol.
    }
    return { page_location: pageLocation, page_referrer: pageReferrer };
  }

  function safeParams(params) {
    const clean = { island_id: null, category: null, outbound_host: null };
    if (!params || typeof params !== "object") return clean;
    if (typeof params.island_id === "string"
        && /^[\p{L}\p{N}][\p{L}\p{M}\p{N}_-]{0,99}$/u.test(params.island_id)) {
      clean.island_id = params.island_id;
    }
    if (CATEGORIES.has(params.category)) clean.category = params.category;
    if (typeof params.outbound_host === "string") {
      const host = params.outbound_host.toLowerCase();
      if (host.length <= 253
          && /^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(host)) {
        clean.outbound_host = host;
      }
    }
    return clean;
  }

  function track(event, params) {
    if (consent !== "granted" || !started || !EVENTS.has(event)) return false;
    if (!ready && pending.length >= 50) return false;
    const context = pageContext();
    if (event === "page_view" && context.page_location === lastPageLocation) return false;
    if (event === "page_view") lastPageLocation = context.page_location;
    const payload = { event, ...safeParams(params), ...context };
    if (ready) window.dataLayer.push(payload);
    else pending.push(payload);
    return true;
  }

  function loadContainer() {
    if (started || consent !== "granted" || !SITE_HOSTS.has(window.location.hostname)) return;
    started = true;
    window.dataLayer = window.dataLayer || [];
    const command = function () { window.dataLayer.push(arguments); };
    command("consent", "default", {
      analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied",
      ad_personalization: "denied",
    });
    command("set", {
      ...pageContext(), send_page_view: false, allow_google_signals: false,
      allow_ad_personalization_signals: false, ads_data_redaction: true,
    });
    command("consent", "update", {
      analytics_storage: "granted", ad_storage: "denied", ad_user_data: "denied",
      ad_personalization: "denied",
    });
    // Initialise clean Data Layer variables before the Google tag reads them.
    window.dataLayer.push({ ...safeParams(), ...pageContext() });
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
    track("page_view");
    const script = document.createElement("script");
    script.async = true;
    script.referrerPolicy = "origin";
    script.src = "https://www.googletagmanager.com/gtm.js?id=" + CONTAINER_ID;
    script.onload = function () {
      if (consent !== "granted") return;
      ready = true;
      const queued = pending;
      pending = [];
      queued.forEach((event) => window.dataLayer.push(event));
    };
    script.onerror = function () {
      pending = [];
      // An unavailable or blocked tag must not interrupt island discovery.
    };
    document.head.appendChild(script);
  }

  function clearAnalyticsCookies() {
    try {
      const names = document.cookie.split(";").map((cookie) => cookie.trim().split("=")[0]);
      const domains = ["", window.location.hostname, ".findmyisland.com"];
      for (const name of names) {
        if (!/^_ga(?:_|$)/.test(name)) continue;
        for (const domain of domains) {
          document.cookie = name + "=; Max-Age=0; Path=/; SameSite=Lax"
            + (domain ? "; Domain=" + domain : "")
            + (window.location.protocol === "https:" ? "; Secure" : "");
        }
      }
    } catch { /* Browser cookie restrictions must not prevent withdrawal. */ }
  }

  function chooseConsent(choice) {
    consent = choice;
    let denialPersists = false;
    try {
      window.localStorage.setItem(STORAGE_KEY, choice);
      denialPersists = choice === "denied";
    } catch {
      if (choice === "denied") {
        // A full store may refuse updates while still allowing an old grant to be removed.
        try { window.localStorage.removeItem(STORAGE_KEY); denialPersists = true; } catch { /* Try the tab sentinel. */ }
      }
    }
    try {
      if (choice === "denied") {
        window.sessionStorage.setItem(SESSION_DENIAL_KEY, "denied");
        denialPersists = true;
      } else window.sessionStorage.removeItem(SESSION_DENIAL_KEY);
    } catch { /* A URL marker is the final withdrawal fallback. */ }
    if (banner) banner.hidden = true;
    if (settingsButton) settingsButton.setAttribute("aria-expanded", "false");
    if (settingsButton) settingsButton.focus();
    if (choice === "granted") {
      try {
        const current = new URL(window.location.href);
        if (current.searchParams.has("fmi_analytics")) {
          current.searchParams.delete("fmi_analytics");
          window.history.replaceState(window.history.state, "", current.href);
        }
      } catch { /* Explicit consent remains valid for this page if the address cannot change. */ }
      loadContainer();
    }
    else {
      ready = false;
      pending = [];
      clearAnalyticsCookies();
      if (started) {
        // Never reload into a stale stored grant when browser storage is unwritable.
        if (denialPersists) window.location.reload();
        else {
          const current = new URL(window.location.href);
          const canonical = new URL(pageContext().page_location);
          window.location.replace(current.origin + publicPath(canonical.pathname) + "?fmi_analytics=off");
        }
      }
    }
  }

  function openSettings() {
    if (!banner) return;
    banner.hidden = false;
    if (settingsButton) settingsButton.setAttribute("aria-expanded", "true");
    const accept = document.getElementById("fmi-analytics-accept");
    if (accept) accept.focus();
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function mountControls() {
    settingsButton = element("button", "fmi-privacy-settings", "Privacy settings");
    settingsButton.type = "button";
    settingsButton.setAttribute("aria-controls", "fmi-analytics-preferences");
    settingsButton.setAttribute("aria-expanded", consent === "unknown" ? "true" : "false");
    settingsButton.addEventListener("click", openSettings);
    banner = element("aside", "fmi-analytics-banner");
    banner.id = "fmi-analytics-preferences";
    banner.setAttribute("aria-labelledby", "fmi-analytics-title");
    banner.hidden = consent !== "unknown";
    const title = element("h2", "fmi-analytics-title", "Help improve the atlas?");
    title.id = "fmi-analytics-title";
    const explanation = element("p", "fmi-analytics-copy",
      "Optional Google Analytics measures page visits and island interactions. "
      + "It stays off until you choose. You can change your choice in Privacy settings.");
    const actions = element("div", "fmi-analytics-actions");
    const accept = element("button", "fmi-analytics-choice", "Accept analytics");
    accept.id = "fmi-analytics-accept";
    accept.type = "button";
    accept.addEventListener("click", () => chooseConsent("granted"));
    const decline = element("button", "fmi-analytics-choice", "Decline");
    decline.id = "fmi-analytics-decline";
    decline.type = "button";
    decline.addEventListener("click", () => chooseConsent("denied"));
    actions.append(accept, decline);
    banner.append(title, explanation, actions);
    document.body.append(settingsButton, banner);
    if (consent === "granted") loadContainer();
  }

  document.addEventListener("click", (event) => {
    const link = event.target && event.target.closest ? event.target.closest("a.lp-cta") : null;
    if (!link) return;
    try {
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin || url.pathname !== "/") return;
      const params = {};
      const islandId = url.searchParams.get("island");
      const category = url.searchParams.get("interest");
      if (islandId) params.island_id = islandId;
      if (category) params.category = category;
      track("map_open", params);
    } catch { /* Ignore invalid links. */ }
  });

  window.fmiAnalytics = Object.freeze({ track, openSettings });
  window.addEventListener("storage", (event) => {
    if ((event.key === STORAGE_KEY && event.newValue !== "granted") || event.key === null) {
      chooseConsent("denied");
    }
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountControls, { once: true });
  else mountControls();
})(window, document);
