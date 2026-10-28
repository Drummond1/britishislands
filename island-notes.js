/**
 * Visitor notes on an island: what's interesting, and what you can do.
 * The note shows on that island. The email is not part of the note.
 * A copy is emailed to the maintainer and, when configured, a Google Sheet.
 */

const LOCAL_KEY = "iobIslandNotes";
const NAME_KEY = "iobVisitorName";
const EMAIL_KEY = "iobVisitorEmail";
const MAINTAINER = "drummondgilbert@gmail.com";
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
  if (/[^\s@]+@[^\s@]+\.[^\s@]+/.test(text)) {
    return "Leave out email addresses. Use the email field. It is not published.";
  }
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
  if (looksPrivate(`${interesting} ${canDo} ${contributorName}`)) return null;
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

export function visitorEmail() {
  try {
    const value = clean(localStorage.getItem(EMAIL_KEY) || "", 200);
    return EMAIL_RE.test(value) ? value : "";
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

function supabaseConfig() {
  const url = String(window.IOB_SUPABASE_URL || document.querySelector('meta[name="iob-supabase-url"]')?.getAttribute("content") || "")
    .trim()
    .replace(/\/$/, "");
  const key = String(window.IOB_SUPABASE_ANON_KEY || document.querySelector('meta[name="iob-supabase-anon-key"]')?.getAttribute("content") || "").trim();
  if (!url || !key) return null;
  return { url, key };
}

export async function refreshIslandNotes() {
  let changed = false;
  try {
    const cfg = supabaseConfig();
    if (!cfg) return false;
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

function placeLine(island) {
  return [island?.nation, island?.archipelago, island?.parentWaterBody?.name]
    .filter(Boolean)
    .join(" · ");
}

function pageUrl(island, pagePath) {
  const origin = String(window.location?.origin || "https://www.findmyisland.com").replace(/\/$/, "");
  const path = String(pagePath || "");
  if (path.startsWith("/")) return `${origin}${path}`;
  if (island?.id) return `${origin}/?island=${encodeURIComponent(island.id)}&map=1`;
  return origin;
}

async function postShared(payload) {
  const cfg = supabaseConfig();
  if (!cfg) return null;
  const res = await fetch(`${cfg.url}/functions/v1/visitor-note`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: cfg.key,
      Authorization: `Bearer ${cfg.key}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (data && data.ok) return { ok: true, mailed: Boolean(data.mailed), sheet: Boolean(data.sheet) };
  if (data && data.message && res.status < 500) return { ok: false, message: String(data.message) };
  return null;
}

async function insertDirect(row) {
  const cfg = supabaseConfig();
  if (!cfg) return false;
  const res = await fetch(`${cfg.url}/rest/v1/island_visitor_notes`, {
    method: "POST",
    headers: {
      apikey: cfg.key,
      Authorization: `Bearer ${cfg.key}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify({
      id: row.id,
      island_id: row.islandId,
      interesting: row.interesting || null,
      can_do: row.canDo || null,
      contributor_name: row.contributorName,
      contributor_email: row.email || null,
    }),
  });
  return res.ok || res.status === 409;
}

async function mailMaintainer(row, island, link) {
  const fd = new FormData();
  fd.append("_subject", `Visitor note: ${island.name || island.id}`);
  fd.append("_template", "table");
  fd.append("_captcha", "false");
  if (row.email) fd.append("_replyto", row.email);
  const fields = {
    Island: island.name || island.id,
    "Island id": island.id,
    Place: placeLine(island),
    Page: link,
    "About this island": clean(island.shortDescription || island.accommodation || "", 400),
    "What's interesting": row.interesting,
    "What you can do": row.canDo,
    From: row.contributorName,
    "Email (not published)": row.email,
    "Note id": row.id,
  };
  for (const [key, value] of Object.entries(fields)) fd.append(key, value || "—");
  const res = await fetch(`https://formsubmit.co/ajax/${encodeURIComponent(MAINTAINER)}`, {
    method: "POST",
    headers: { Accept: "application/json" },
    body: fd,
  });
  const data = await res.json().catch(() => ({}));
  return res.ok && String(data.success || "") !== "false";
}

/**
 * @returns {Promise<{ok: true, where: "shared" | "sent" | "here"} | {ok: false, message: string}>}
 */
export async function saveIslandNote({ island, personName, email, interesting, canDo, pagePath }) {
  const who = clean(personName, 60);
  const interest = clean(interesting, 280);
  const doing = clean(canDo, 280);
  const mail = clean(email, 200);
  if (!island?.id) return { ok: false, message: "Open an island, then try again." };
  if (letters(interest) < 4 && letters(doing) < 4) {
    return { ok: false, message: "Say what's interesting, or what you can do." };
  }
  const privacy = looksPrivate(`${interest} ${doing} ${who}`);
  if (privacy) return { ok: false, message: privacy };
  if (letters(who) < 2) return { ok: false, message: "Type your name." };
  if (mail && !EMAIL_RE.test(mail)) return { ok: false, message: "That email does not look right." };

  const row = {
    id: crypto.randomUUID(),
    islandId: island.id,
    interesting: interest,
    canDo: doing,
    contributorName: who,
    email: mail,
    at: new Date().toISOString(),
    shared: false,
  };
  const link = pageUrl(island, pagePath);
  const payload = {
    id: row.id,
    islandId: row.islandId,
    islandName: clean(island.name || "", 120),
    place: placeLine(island),
    listing: clean(island.shortDescription || island.accommodation || "", 400),
    pageUrl: link,
    interesting: row.interesting,
    canDo: row.canDo,
    contributorName: row.contributorName,
    email: row.email,
  };

  let where = "here";
  try {
    const remote = await postShared(payload);
    if (remote && remote.ok) {
      row.shared = true;
      where = "shared";
      if (!remote.mailed) {
        try {
          await mailMaintainer(row, island, link);
        } catch (_) {
          /* the note is already on the island */
        }
      }
    } else if (remote && remote.message) {
      return { ok: false, message: remote.message };
    }
  } catch (_) {
    /* try the table directly */
  }

  if (where !== "shared") {
    try {
      if (await insertDirect(row)) {
        row.shared = true;
        where = "shared";
      }
    } catch (_) {
      /* stays on this computer */
    }
    try {
      if (await mailMaintainer(row, island, link)) where = row.shared ? "shared" : "sent";
    } catch (_) {
      /* the note can still show here */
    }
  }

  remember(row);
  try {
    localStorage.setItem(NAME_KEY, who);
    if (mail) localStorage.setItem(EMAIL_KEY, mail);
    else localStorage.removeItem(EMAIL_KEY);
  } catch (_) {
    /* ignore */
  }
  return { ok: true, where };
}
