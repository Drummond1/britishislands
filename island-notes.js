/**
 * Visitor notes on an island: what's interesting, and what you can do.
 * The note shows on that island. It is not part of the canonical record.
 * No email is collected.
 */

import { loadCrowdSuggestConfig, isCrowdSuggestConfigured, submitCrowdSuggestion } from "./crowd-pins.js?v=visitor-note-1";

const LOCAL_KEY = "iobIslandNotes";
const NAME_KEY = "iobVisitorName";

/** @type {Map<string, Array<{id: string, islandId: string, interesting: string, canDo: string, contributorName: string, at: string, shared: boolean}>>} */
const byIsland = new Map();

function clean(value, max) {
  return String(value || "")
    .replace(/[<>]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

function letters(value) {
  return (String(value || "").match(/[A-Za-zÀ-ÿ0-9]/g) || []).length;
}

function looksPrivate(text) {
  if (/[^\s@]+@[^\s@]+\.[^\s@]+/.test(text)) return "Leave out email addresses.";
  if (/(?:\+?\d[\d\s().-]{8,}\d)/.test(text)) return "Leave out phone numbers.";
  return "";
}

function persistLocal() {
  try {
    const rows = [];
    for (const list of byIsland.values()) rows.push(...list);
    localStorage.setItem(LOCAL_KEY, JSON.stringify(rows));
  } catch (_) {
    /* private mode */
  }
}

function loadLocal() {
  try {
    const raw = JSON.parse(localStorage.getItem(LOCAL_KEY) || "[]");
    if (!Array.isArray(raw)) return;
    for (const row of raw) remember(row, { persist: false });
  } catch (_) {
    /* ignore */
  }
}

function normalise(row) {
  const interesting = clean(row.interesting, 280);
  const canDo = clean(row.canDo, 280);
  const contributorName = clean(row.contributorName, 60);
  const islandId = String(row.islandId || "").trim();
  const id = String(row.id || "").trim();
  if (!islandId || !id || !contributorName) return null;
  if (letters(interesting) < 4 && letters(canDo) < 4) return null;
  return {
    id,
    islandId,
    interesting,
    canDo,
    contributorName,
    at: String(row.at || row.created_at || ""),
    shared: Boolean(row.shared),
  };
}

function remember(row, { persist = true } = {}) {
  const next = normalise(row);
  if (!next) return false;
  const list = byIsland.get(next.islandId) || [];
  const idx = list.findIndex((item) => item.id === next.id);
  if (idx >= 0) {
    const prev = list[idx];
    if (
      prev.interesting === next.interesting &&
      prev.canDo === next.canDo &&
      prev.contributorName === next.contributorName &&
      prev.shared === next.shared
    ) {
      return false;
    }
    list[idx] = next;
  } else {
    list.push(next);
  }
  byIsland.set(next.islandId, list);
  if (persist) persistLocal();
  return true;
}

loadLocal();

export function visitorName() {
  try {
    return clean(localStorage.getItem(NAME_KEY) || "", 60);
  } catch (_) {
    return "";
  }
}

export function notesForIsland(islandId) {
  const list = byIsland.get(islandId) || [];
  return list
    .slice()
    .sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0));
}

function supabaseReady() {
  const url = String(window.IOB_SUPABASE_URL || document.querySelector('meta[name="iob-supabase-url"]')?.getAttribute("content") || "").trim();
  const key = String(window.IOB_SUPABASE_ANON_KEY || document.querySelector('meta[name="iob-supabase-anon-key"]')?.getAttribute("content") || "").trim();
  return Boolean(url && key);
}

export async function refreshIslandNotes() {
  let changed = false;
  try {
    if (!supabaseReady()) return false;
    const { getSupabase } = await import("./supabase-client.js");
    const sb = getSupabase();
    if (!sb) return false;
    const { data, error } = await sb.rpc("island_visitor_notes_public");
    if (error || !Array.isArray(data)) return false;
    for (const row of data) {
      if (
        remember({
          id: row.id,
          islandId: row.island_id,
          interesting: row.interesting,
          canDo: row.can_do,
          contributorName: row.contributor_name,
          at: row.created_at,
          shared: true,
        })
      ) {
        changed = true;
      }
    }
  } catch (_) {
    return false;
  }
  return changed;
}

async function writeSupabase(row) {
  if (!supabaseReady()) return false;
  const { getSupabase } = await import("./supabase-client.js");
  const sb = getSupabase();
  if (!sb) return false;
  const { error } = await sb.from("island_visitor_notes").insert({
    id: row.id,
    island_id: row.islandId,
    interesting: row.interesting || null,
    can_do: row.canDo || null,
    contributor_name: row.contributorName,
  });
  return !error;
}

async function writeInbox(row, island) {
  const cfg = await loadCrowdSuggestConfig();
  if (!isCrowdSuggestConfigured(cfg)) return false;
  const bits = [];
  if (row.interesting) bits.push(`What's interesting: ${row.interesting}`);
  if (row.canDo) bits.push(`What you can do: ${row.canDo}`);
  await submitCrowdSuggestion(
    {
      lat: island.lat,
      lng: island.lng,
      name: island.name || "",
      note: bits.join("\n"),
      credit: row.contributorName,
      contributionKind: "visitor_note",
      atlasIslandId: island.id,
      atlasIslandName: island.name || island.id,
      proposedChanges: "Visitor note: what's interesting, and what you can do",
      skipSourceCheck: true,
    },
    cfg,
  );
  return true;
}

/**
 * @returns {Promise<{ok: true, where: "shared" | "sent" | "here"} | {ok: false, message: string}>}
 */
export async function saveIslandNote({ island, personName, interesting, canDo }) {
  const who = clean(personName, 60);
  const interest = clean(interesting, 280);
  const doing = clean(canDo, 280);
  if (!island?.id) return { ok: false, message: "Open an island, then try again." };
  if (letters(interest) < 4 && letters(doing) < 4) {
    return { ok: false, message: "Say what's interesting, or what you can do." };
  }
  const privacy = looksPrivate(`${interest} ${doing} ${who}`);
  if (privacy) return { ok: false, message: privacy };
  if (letters(who) < 2) return { ok: false, message: "Type your name." };

  const row = {
    id: crypto.randomUUID(),
    islandId: island.id,
    interesting: interest,
    canDo: doing,
    contributorName: who,
    at: new Date().toISOString(),
    shared: false,
  };

  let where = "here";
  try {
    if (await writeSupabase(row)) {
      row.shared = true;
      where = "shared";
    }
  } catch (_) {
    /* try the inbox */
  }
  if (where !== "shared") {
    try {
      if (await writeInbox(row, island)) where = "sent";
    } catch (_) {
      /* stays on this computer */
    }
  }

  remember(row);
  try {
    localStorage.setItem(NAME_KEY, who);
  } catch (_) {
    /* ignore */
  }
  return { ok: true, where };
}
