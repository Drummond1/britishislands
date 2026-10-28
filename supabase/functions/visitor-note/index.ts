// Saves a visitor note, keeps the email off the public island page,
// writes a private copy when a Google Form is configured, and emails the maintainer.

const MAINTAINER = "drummondgilbert@gmail.com";
const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 8;
const MAX_BODY = 12_000;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const buckets = new Map<string, { n: number; reset: number }>();

function originAllowed(origin: string): boolean {
  if (origin === "https://www.findmyisland.com" || origin === "https://findmyisland.com") {
    return true;
  }
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

function clientKey(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for") || "";
  return forwarded.split(",")[0].trim() || "unknown";
}

function rateLimit(req: Request): boolean {
  const now = Date.now();
  const key = clientKey(req);
  const bucket = buckets.get(key);
  if (!bucket || bucket.reset < now) {
    buckets.set(key, { n: 1, reset: now + WINDOW_MS });
    return true;
  }
  bucket.n += 1;
  return bucket.n <= MAX_PER_WINDOW;
}

function clean(value: unknown, max: number): string {
  return String(value ?? "")
    .replace(/[<>]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}

function letters(value: string): number {
  return (value.match(/[A-Za-zÀ-ÿ0-9]/g) || []).length;
}

function looksPrivate(text: string): string {
  if (/[^\s@]+@[^\s@]+\.[^\s@]+/.test(text)) {
    return "Leave out email addresses. Use the email field. It is not published.";
  }
  if (/(?:\+?\d[\d\s().-]{8,}\d)/.test(text)) return "Leave out phone numbers.";
  return "";
}

function safePage(value: string, islandId: string): string {
  const fallback = `https://www.findmyisland.com/?island=${encodeURIComponent(islandId)}&map=1`;
  try {
    const url = new URL(value);
    const host = url.hostname;
    const local = host === "localhost" || host === "127.0.0.1";
    const live = host === "www.findmyisland.com" || host === "findmyisland.com";
    if (local && url.protocol === "http:") return url.toString().slice(0, 500);
    if (live && url.protocol === "https:") return url.toString().slice(0, 500);
  } catch (_) {
    /* use the public island link */
  }
  return fallback;
}

async function insertNote(row: Record<string, string | null>): Promise<{ ok: boolean; duplicate: boolean }> {
  const url = Deno.env.get("SUPABASE_URL") || "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!url || !key) return { ok: false, duplicate: false };
  const res = await fetch(`${url}/rest/v1/island_visitor_notes`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify(row),
  });
  if (res.status === 409) return { ok: true, duplicate: true };
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    if (detail.includes("23505")) return { ok: true, duplicate: true };
    console.log(`visitor-note insert ${res.status}`);
    return { ok: false, duplicate: false };
  }
  return { ok: true, duplicate: false };
}

async function formDestination(): Promise<{ url: string; entries: Record<string, string> } | null> {
  const envUrl = Deno.env.get("VISITOR_NOTES_FORM_URL") || "";
  const envRaw = Deno.env.get("VISITOR_NOTES_FORM_ENTRIES") || "";
  if (envUrl && envRaw) {
    try {
      return { url: envUrl, entries: JSON.parse(envRaw) };
    } catch (_) {
      /* the private table is the other place this can live */
    }
  }
  const url = Deno.env.get("SUPABASE_URL") || "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!url || !key) return null;
  const res = await fetch(`${url}/rest/v1/island_note_inbox?id=eq.1&select=form_url,form_entries`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  if (!res.ok) return null;
  const rows = await res.json().catch(() => []);
  const row = Array.isArray(rows) ? rows[0] : null;
  if (!row?.form_url || !row?.form_entries) return null;
  const entries = typeof row.form_entries === "string" ? JSON.parse(row.form_entries) : row.form_entries;
  if (!entries || typeof entries !== "object") return null;
  return { url: String(row.form_url), entries };
}

async function writeGoogleForm(fields: Record<string, string>): Promise<boolean> {
  const dest = await formDestination();
  if (!dest?.url) return false;
  const formUrl = dest.url;
  const entries = dest.entries;
  const body = new URLSearchParams();
  for (const [key, entryId] of Object.entries(entries)) {
    if (!entryId) continue;
    body.set(`entry.${entryId}`, fields[key] || "");
  }
  body.set("fvv", "1");
  body.set("pageHistory", "0");
  body.set("submit", "Submit");
  const res = await fetch(formUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    redirect: "follow",
  });
  return res.ok;
}

async function mailMaintainer(fields: Record<string, string>, replyTo: string, subject: string): Promise<boolean> {
  const fd = new FormData();
  fd.append("_subject", subject);
  fd.append("_template", "table");
  fd.append("_captcha", "false");
  if (replyTo) fd.append("_replyto", replyTo);
  for (const [key, value] of Object.entries(fields)) fd.append(key, value || "—");
  const res = await fetch(`https://formsubmit.co/ajax/${encodeURIComponent(MAINTAINER)}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Origin: "https://www.findmyisland.com",
      Referer: "https://www.findmyisland.com/",
      "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    },
    body: fd,
  });
  const data = await res.json().catch(() => ({}));
  const success = String((data as { success?: string }).success || "");
  return res.ok && success !== "false";
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin") || "";
  const allow = originAllowed(origin) ? origin : "https://www.findmyisland.com";
  const cors: Record<string, string> = {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
  const json = (payload: unknown, status: number) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { ...cors, "Content-Type": "application/json" },
    });

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (req.method !== "POST") return json({ ok: false, message: "POST only." }, 405);
  if (!originAllowed(origin)) return json({ ok: false, message: "Open an island, then try again." }, 403);
  if (!rateLimit(req)) return json({ ok: false, message: "Too many notes just now. Try again in a few minutes." }, 429);

  const length = Number(req.headers.get("content-length") || "0");
  if (length > MAX_BODY) return json({ ok: false, message: "That note is too long." }, 413);

  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch (_) {
    return json({ ok: false, message: "Open an island, then try again." }, 400);
  }

  const islandId = clean(body.islandId, 200);
  const islandName = clean(body.islandName, 120) || islandId;
  const place = clean(body.place, 200);
  const listing = clean(body.listing, 400);
  const interesting = clean(body.interesting, 280);
  const canDo = clean(body.canDo, 280);
  const contributorName = clean(body.contributorName, 60);
  const email = clean(body.email, 200);
  const id = clean(body.id, 80);
  const pageUrl = safePage(clean(body.pageUrl, 500), islandId);

  if (!/^[0-9a-f-]{36}$/i.test(id)) return json({ ok: false, message: "Open an island, then try again." }, 400);
  if (!islandId) return json({ ok: false, message: "Open an island, then try again." }, 400);
  if (letters(interesting) < 4 && letters(canDo) < 4) {
    return json({ ok: false, message: "Say what's interesting, or what you can do." }, 400);
  }
  const privacy = looksPrivate(`${interesting} ${canDo} ${contributorName}`);
  if (privacy) return json({ ok: false, message: privacy }, 400);
  if (letters(contributorName) < 2) return json({ ok: false, message: "Type your name." }, 400);
  if (email && !EMAIL_RE.test(email)) {
    return json({ ok: false, message: "That email does not look right." }, 400);
  }

  const saved = await insertNote({
    id,
    island_id: islandId,
    interesting: interesting || null,
    can_do: canDo || null,
    contributor_name: contributorName,
    contributor_email: email || null,
  });
  if (!saved.ok) return json({ ok: false, message: "Could not save that. Try again." }, 502);

  const fields: Record<string, string> = {
    Island: islandName,
    "Island id": islandId,
    Place: place,
    Page: pageUrl,
    "About this island": listing,
    "What's interesting": interesting,
    "What you can do": canDo,
    From: contributorName,
    "Email (not published)": email,
    "Note id": id,
  };
  let sheet = false;
  let mailed = false;
  if (!saved.duplicate) {
    try {
      sheet = await writeGoogleForm(fields);
    } catch (_) {
      sheet = false;
    }
    try {
      mailed = await mailMaintainer(fields, email, `Visitor note: ${islandName}`);
    } catch (_) {
      mailed = false;
    }
  } else {
    mailed = true;
    sheet = true;
  }

  return json({ ok: true, mailed, sheet }, 200);
});
