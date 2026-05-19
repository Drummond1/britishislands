/**
 * Thin Supabase client for the static atlas (no build step).
 * Loads @supabase/supabase-js from esm.sh when URL + anon key are configured.
 *
 * Set in config.local.js (gitignored):
 *   window.IOB_SUPABASE_URL = "https://xxxx.supabase.co";
 *   window.IOB_SUPABASE_ANON_KEY = "eyJ...";
 *
 * Or via meta tags (optional):
 *   <meta name="iob-supabase-url" content="...">
 *   <meta name="iob-supabase-anon-key" content="...">
 */
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.8";

function readMeta(name) {
  return document.querySelector(`meta[name="${name}"]`)?.getAttribute("content")?.trim() || "";
}

export function getSupabaseConfig() {
  const url = (window.IOB_SUPABASE_URL || readMeta("iob-supabase-url") || "").replace(/\/$/, "");
  const anonKey = window.IOB_SUPABASE_ANON_KEY || readMeta("iob-supabase-anon-key") || "";
  return { url, anonKey, configured: Boolean(url && anonKey) };
}

let _client = null;

/** Singleton client; null if not configured. */
export function getSupabase() {
  const { url, anonKey, configured } = getSupabaseConfig();
  if (!configured) return null;
  if (!_client) {
    _client = createClient(url, anonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }
  return _client;
}

/** List saved island ids for the signed-in user (empty if logged out). */
export async function fetchSavedIslandIds() {
  const sb = getSupabase();
  if (!sb) return [];
  const { data: session } = await sb.auth.getSession();
  if (!session?.session?.user) return [];
  const { data, error } = await sb
    .from("saved_islands")
    .select("island_id")
    .order("created_at", { ascending: true });
  if (error) {
    console.warn("[supabase] saved_islands:", error.message);
    return [];
  }
  return (data || []).map((r) => r.island_id);
}

/** Replace saved islands for the current user (requires sign-in). */
export async function syncSavedIslandIds(islandIds) {
  const sb = getSupabase();
  if (!sb) return { ok: false, reason: "not_configured" };
  const { data: session } = await sb.auth.getSession();
  const uid = session?.session?.user?.id;
  if (!uid) return { ok: false, reason: "not_signed_in" };

  const unique = [...new Set(islandIds.filter(Boolean))];
  const { error: delErr } = await sb.from("saved_islands").delete().eq("user_id", uid);
  if (delErr) return { ok: false, reason: delErr.message };
  if (!unique.length) return { ok: true };

  const rows = unique.map((island_id) => ({ user_id: uid, island_id }));
  const { error: insErr } = await sb.from("saved_islands").insert(rows);
  if (insErr) return { ok: false, reason: insErr.message };
  return { ok: true };
}
