/**
 * Name an island that the atlas still lists as unnamed.
 * The public map stores the suggested name and who suggested it.
 * The email stays in the private log (Supabase, or the suggestion inbox).
 */

import { loadCrowdSuggestConfig, isCrowdSuggestConfigured, submitCrowdSuggestion } from "./crowd-pins.js?v=visitor-note-1";

const LOCAL_KEY = "iobSuggestedNames";

/** @type {Map<string, {islandId: string, islandName: string, contributorName: string, attribution: string, at: string}>} */
const byId = new Map();

function clean(value, max) {
  return String(value || "")
    .replace(/[<>]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

function isPlaceholderName(name) {
  const n = name.toLowerCase().replace(/[^a-z]/g, "");
  return n === "unnamed" || n === "unnamedisland" || n === "unknown" || n === "noname";
}

function persistLocal() {
  try {
    localStorage.setItem(LOCAL_KEY, JSON.stringify([...byId.values()]));
  } catch (_) {
    /* private mode */
  }
}

function loadLocal() {
  try {
    const raw = JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]");
    if (!Array.isArray(raw)) return;
    for (const row of raw) {
      if (!row?.islandId || !row?.islandName) continue;
      byId.set(row.islandId, {
        islandId: String(row.islandId),
        islandName: clean(row.islandName, 80),
        contributorName: clean(row.contributorName, 60),
        attribution: clean(row.attribution, 300),
        at: String(row.at || ""),
      });
    }
  } catch (_) {
    /* ignore */
  }
}

loadLocal();

export function suggestedName(islandId) {
  if (!islandId) return null;
  return byId.get(islandId) || null;
}

function remember(row) {
  const prev = byId.get(row.islandId);
  byId.set(row.islandId, row);
  persistLocal();
  return !prev
    || prev.islandName !== row.islandName
    || prev.contributorName !== row.contributorName
    || prev.attribution !== row.attribution;
}

export async function refreshSuggestedNames() {
  let changed = false;
  try {
    const { getSupabase } = await import("./supabase-client.js");
    const sb = getSupabase();
    if (!sb) return false;
    const { data, error } = await sb.rpc("island_names_public");
    if (error || !Array.isArray(data)) return false;
    for (const row of data) {
      const next = {
        islandId: String(row.island_id || ""),
        islandName: clean(row.island_name, 80),
        contributorName: clean(row.contributor_name, 60),
        attribution: clean(row.attribution, 300),
        at: String(row.created_at || ""),
      };
      if (!next.islandId || !next.islandName) continue;
      const prev = byId.get(next.islandId);
      const nextTime = Date.parse(next.at) || 0;
      const prevTime = Date.parse(prev?.at || "") || 0;
      if (prev && prevTime > nextTime) continue;
      if (remember(next)) changed = true;
    }
  } catch (_) {
    return false;
  }
  return changed;
}

async function writeSupabaseLog(row) {
  const { getSupabase } = await import("./supabase-client.js");
  const sb = getSupabase();
  if (!sb) return false;
  const { error } = await sb.from("island_name_log").insert({
    island_id: row.islandId,
    island_name: row.islandName,
    contributor_name: row.contributorName,
    contributor_email: row.email,
    attribution: row.attribution || null,
    lat: Number.isFinite(row.lat) ? row.lat : null,
    lng: Number.isFinite(row.lng) ? row.lng : null,
  });
  return !error;
}

async function writeInboxLog(row) {
  const cfg = await loadCrowdSuggestConfig();
  if (!isCrowdSuggestConfigured(cfg)) return false;
  await submitCrowdSuggestion(
    {
      lat: row.lat,
      lng: row.lng,
      name: row.islandName,
      note: row.attribution || "",
      nameSourceUrl: /^https?:\/\//i.test(row.attribution) ? row.attribution : "",
      credit: row.contributorName,
      contactEmail: row.email,
      contributionKind: "fix_atlas",
      atlasIslandId: row.islandId,
      atlasIslandName: row.islandName,
      proposedChanges: "Name for an unnamed island",
      skipSourceCheck: true,
    },
    cfg,
  );
  return true;
}

/**
 * @returns {Promise<{ok: true} | {ok: false, message: string}>}
 */
export async function saveIslandName({ island, personName, email, islandName, attribution }) {
  const called = clean(islandName, 80);
  const who = clean(personName, 60);
  const mail = clean(email, 200);
  const source = clean(attribution, 300);
  if (!called || called.length < 2) return { ok: false, message: "Type the name of the island." };
  if (isPlaceholderName(called)) return { ok: false, message: "Type the name people use for this island." };
  if (!who || who.length < 2) return { ok: false, message: "Type your name." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail)) return { ok: false, message: "Type an email address." };
  if (!island?.id) return { ok: false, message: "Choose an island on the map, then try again." };

  const row = {
    islandId: island.id,
    islandName: called,
    contributorName: who,
    attribution: source,
    email: mail,
    lat: island.lat,
    lng: island.lng,
    at: new Date().toISOString(),
  };

  let logged = false;
  try {
    logged = await writeSupabaseLog(row);
  } catch (_) {
    logged = false;
  }
  if (!logged) {
    try {
      logged = await writeInboxLog(row);
    } catch (_) {
      logged = false;
    }
  }
  if (!logged) return { ok: false, message: "Could not save. Check the connection and try again." };

  remember({
    islandId: row.islandId,
    islandName: row.islandName,
    contributorName: row.contributorName,
    attribution: row.attribution,
    at: row.at,
  });
  return { ok: true };
}
