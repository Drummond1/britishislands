// Private CSV of public island names, for the Google Sheet.
// The token is checked against island_name_sheet_token. Email addresses are in the CSV.
// Do not call this without the token. The map uses island_names_public() instead.

function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

Deno.serve(async (req) => {
  if (req.method !== "GET" && req.method !== "HEAD") {
    return new Response("GET only", { status: 405 });
  }
  const url = Deno.env.get("SUPABASE_URL") || "";
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!url || !key) return new Response("Unavailable", { status: 503 });

  const token = new URL(req.url).searchParams.get("token") || "";
  const headers = { apikey: key, Authorization: `Bearer ${key}` };
  const tokenRes = await fetch(
    `${url}/rest/v1/island_name_sheet_token?id=eq.1&select=token`,
    { headers },
  );
  if (!tokenRes.ok) return new Response("Unavailable", { status: 503 });
  const tokenRows = await tokenRes.json();
  const expected = Array.isArray(tokenRows) ? tokenRows[0]?.token : "";
  if (!expected || token !== expected) return new Response("Not found", { status: 404 });

  if (req.method === "HEAD") return new Response(null, { status: 200 });

  const dataRes = await fetch(
    `${url}/rest/v1/island_name_log?select=created_at,island_name,contributor_name,contributor_email,island_id,lat,lng&order=created_at.asc`,
    { headers },
  );
  if (!dataRes.ok) return new Response("Unavailable", { status: 503 });
  const rows = await dataRes.json();
  const lines = ["Submitted,Island,Named by,Email,Island id,Latitude,Longitude"];
  if (Array.isArray(rows)) {
    for (const row of rows) {
      lines.push(
        [
          row.created_at,
          row.island_name,
          row.contributor_name,
          row.contributor_email,
          row.island_id,
          row.lat,
          row.lng,
        ].map(csvCell).join(","),
      );
    }
  }
  return new Response(lines.join("\n") + "\n", {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
});
