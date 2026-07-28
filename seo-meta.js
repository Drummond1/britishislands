/**
 * Island SEO / structured-data head tags — updates <title>, meta description,
 * Open Graph, Twitter Cards, canonical URL, and JSON-LD. No visible DOM changes.
 *
 * Set window.IOB_SITE_ORIGIN (e.g. "https://example.com") if the public URL
 * differs from location.origin (CDN, reverse proxy).
 */

const HOME_SEO = {
  title: "Find My Island — Isles of Britain atlas",
  description:
    "Find My Island: explore 7,000+ islands of the UK and Ireland on an interactive map — photos, ferry routes, Gaelic names, and island profiles for Scotland, Wales, England, and Ireland.",
  canonical: "https://www.findmyisland.com/",
  ogType: "website",
  ogTitle: "Find My Island — Isles of Britain atlas",
  ogDescription:
    "Interactive map of 7,000+ British and Irish islands — sea, loch, and river — with photos, ferries, and island guides.",
  ogUrl: "https://www.findmyisland.com/",
  twitterCard: "summary_large_image",
  twitterTitle: "Find My Island — Isles of Britain atlas",
  twitterDescription:
    "Explore 7,000+ islands of the UK and Ireland on an interactive map with ferry guides and island profiles.",
};

let _baselineTitle = "";
let _baselineDescription = "";

function siteOrigin() {
  if (typeof window === "undefined") return "";
  const o = window.IOB_SITE_ORIGIN;
  if (o && typeof o === "string") return o.replace(/\/$/, "");
  return window.location.origin;
}

function pagePathname() {
  if (typeof window === "undefined") return "/";
  return window.location.pathname || "/";
}

function absoluteUrl(href) {
  if (!href || typeof href !== "string") return "";
  const h = href.trim();
  if (h.startsWith("https://") || h.startsWith("http://")) return h;
  if (h.startsWith("//")) return `https:${h}`;
  try {
    return new URL(h, siteOrigin() + pagePathname()).toString();
  } catch {
    return "";
  }
}

/**
 * Prefer public /islands/{nation}/{slug}/ when island.seoPath is present
 * (stamped by build_islands_index / generate_seo_artifacts). Fall back to
 * legacy ?island= deep link only when missing.
 */
function canonicalUrlForIsland(island) {
  try {
    const origin = siteOrigin();
    const seoPath = island && typeof island.seoPath === "string" ? island.seoPath.trim() : "";
    if (seoPath.startsWith("/islands/")) {
      return `${origin}${seoPath.endsWith("/") ? seoPath : `${seoPath}/`}`;
    }
    const islandId = island && island.id;
    if (!islandId) return "";
    const u = new URL(pagePathname(), origin);
    u.search = "";
    u.hash = "";
    u.searchParams.set("island", islandId);
    return u.toString();
  } catch {
    return "";
  }
}

function pageTitleForIsland(island) {
  const name = island.name || island.id || "Island";
  const nation = (island.nation || "").trim();
  if (nation) return `${name}, ${nation} — map & profile | Find My Island`;
  return `${name} — map & profile | Find My Island`;
}

function upsertMetaByName(name, content) {
  let el = document.querySelector(`meta[name="${CSS.escape(name)}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("name", name);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertMetaProperty(prop, content) {
  let el = document.querySelector(`meta[property="${CSS.escape(prop)}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute("property", prop);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href) {
  let el = document.querySelector(`link[rel="${CSS.escape(rel)}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function nationToCountryHint(nation) {
  const n = String(nation || "");
  if (n === "Ireland") return "IE";
  if (n === "Northern Ireland" || n === "England" || n === "Scotland" || n === "Wales")
    return "GB";
  if (n === "Crown Dependency") return "GB"; /* bailiwicks: rough aggregate */
  return n || undefined;
}

function buildDescription(island) {
  const parts = [];
  const t = island.type === "lake" ? "lake island" : island.type === "river" ? "river island" : "island";
  parts.push(`${island.name} — ${t} in ${island.nation || "the British Isles"}.`);
  if (island.shortDescription) {
    parts.push(String(island.shortDescription).replace(/\s+/g, " ").trim().slice(0, 280));
  } else if (island.archipelago) {
    parts.push(`Part of ${island.archipelago}.`);
  }
  parts.push("Explore on the Isles of Britain visual atlas — map, photos, transport and ferry context.");
  return parts.join(" ").slice(0, 320);
}

function injectJsonLd(data) {
  let el = document.getElementById("iob-jsonld-island");
  if (!el) {
    el = document.createElement("script");
    el.type = "application/ld+json";
    el.id = "iob-jsonld-island";
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data).replace(/</g, "\\u003c");
}

function removeJsonLd() {
  document.getElementById("iob-jsonld-island")?.remove();
}

export function initSeoBaseline() {
  _baselineTitle = document.title || HOME_SEO.title;
  _baselineDescription =
    document.querySelector('meta[name="description"]')?.getAttribute("content") || "";
}

export function applyIslandSeo(island) {
  if (!island || !island.id) return;

  const title = pageTitleForIsland(island);
  const desc = buildDescription(island);
  const canonical = canonicalUrlForIsland(island);
  const pageUrl = canonical || (typeof window !== "undefined" ? window.location.href : "");

  document.title = title;
  upsertMetaByName("description", desc);

  if (canonical) upsertLink("canonical", canonical);

  // SPA ?island= URLs must not compete with /islands/{nation}/{slug}/ in Google.
  // Keep them crawlable via follow, but noindex the query-string view.
  // When the address bar already shows /islands/…, leave indexing alone.
  try {
    const q = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
    const onSeoPath =
      typeof window !== "undefined" &&
      (window.location.pathname || "").startsWith("/islands/");
    if (q && q.has("island") && canonical && canonical.includes("/islands/") && !onSeoPath) {
      upsertMetaByName("robots", "noindex,follow,max-image-preview:large");
    }
  } catch {
    /* ignore */
  }

  upsertMetaProperty("og:type", "article");
  upsertMetaProperty("og:title", title);
  upsertMetaProperty("og:description", desc);
  if (pageUrl) upsertMetaProperty("og:url", pageUrl);

  const img = island.image || (Array.isArray(island.images) && island.images[0]?.url) || "";
  const ogImg = absoluteUrl(img);
  if (ogImg) upsertMetaProperty("og:image", ogImg);

  upsertMetaByName("twitter:card", ogImg ? "summary_large_image" : "summary");
  upsertMetaByName("twitter:title", title);
  upsertMetaByName("twitter:description", desc);
  if (ogImg) upsertMetaByName("twitter:image", ogImg);

  const geoCountry = nationToCountryHint(island.nation);
  const schema = {
    "@context": "https://schema.org",
    "@type": "Island",
    name: island.name,
    description: (island.shortDescription || desc).slice(0, 2000),
    url: pageUrl || undefined,
    geo: {
      "@type": "GeoCoordinates",
      latitude: island.lat,
      longitude: island.lng,
    },
  };
  if (geoCountry) schema.addressCountry = geoCountry;
  if (island.population != null && island.population !== "") {
    schema.additionalProperty = [
      {
        "@type": "PropertyValue",
        name: "population",
        value: Number(island.population),
      },
    ];
  }
  const sameAs = [];
  if (island.wikipedia) sameAs.push(island.wikipedia);
  if (island.wikidata) sameAs.push(`https://www.wikidata.org/wiki/${island.wikidata}`);
  if (sameAs.length) schema.sameAs = sameAs;
  if (island.parentWaterBody?.name) {
    schema.containedInPlace = {
      "@type": "Place",
      name: island.parentWaterBody.name,
      additionalType: island.parentWaterBody.type === "river" ? "https://schema.org/RiverBodyOfWater" : "https://schema.org/LakeBodyOfWater",
    };
  }

  injectJsonLd(schema);
}

export function resetIslandSeo() {
  const home = HOME_SEO;
  document.title = _baselineTitle || home.title;
  upsertMetaByName("description", _baselineDescription || home.description);
  upsertLink("canonical", home.canonical);
  // Restore default indexing when leaving an island deep-link
  upsertMetaByName("robots", "index,follow,max-image-preview:large");
  upsertMetaProperty("og:type", home.ogType);
  upsertMetaProperty("og:title", home.ogTitle);
  upsertMetaProperty("og:description", home.ogDescription);
  upsertMetaProperty("og:url", home.ogUrl);
  document.querySelector('meta[property="og:image"]')?.remove();
  upsertMetaByName("twitter:card", home.twitterCard);
  upsertMetaByName("twitter:title", home.twitterTitle);
  upsertMetaByName("twitter:description", home.twitterDescription);
  document.querySelector('meta[name="twitter:image"]')?.remove();
  removeJsonLd();
}

function bootstrapBaseline() {
  if (typeof document === "undefined") return;
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initSeoBaseline(), { once: true });
  } else {
    initSeoBaseline();
  }
}

bootstrapBaseline();
