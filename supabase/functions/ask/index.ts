// Shared Ask proxy. OPENAI_API_KEY is a Supabase secret and never leaves this function.
// The browser sends the public anon key only. Questions are not logged.

const ALLOWED_TOOLS = new Set([
  "search_islands",
  "count_islands",
  "list_collections",
  "read_islands",
  "show_on_map",
  "reply",
]);

const WINDOW_MS = 10 * 60 * 1000;
const MAX_PER_WINDOW = 30;
const MAX_BODY = 400_000;
const buckets = new Map<string, { n: number; reset: number }>();

function originAllowed(origin: string): boolean {
  if (origin === "https://www.findmyisland.com" || origin === "https://findmyisland.com") {
    return true;
  }
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

function clientKey(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for") || "";
  const ip = forwarded.split(",")[0].trim() || "unknown";
  return ip;
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

function toolNames(body: Record<string, unknown>): string[] {
  const tools = Array.isArray(body.tools) ? body.tools : [];
  const names: string[] = [];
  for (const tool of tools) {
    if (!tool || typeof tool !== "object") continue;
    const row = tool as Record<string, unknown>;
    const fn = row.function;
    if (fn && typeof fn === "object" && typeof (fn as Record<string, unknown>).name === "string") {
      names.push((fn as Record<string, string>).name);
    }
  }
  return names;
}

Deno.serve(async (req) => {
  const origin = req.headers.get("origin") || "";
  const allow = originAllowed(origin) ? origin : "https://www.findmyisland.com";
  const cors: Record<string, string> = {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Headers": "authorization, apikey, content-type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    Vary: "Origin",
  };
  const json = (payload: unknown, status: number) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { ...cors, "Content-Type": "application/json" },
    });

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  const apiKey = Deno.env.get("OPENAI_API_KEY") || "";
  if (req.method === "GET") {
    return json({ ready: Boolean(apiKey) }, apiKey ? 200 : 503);
  }
  if (req.method !== "POST") return json({ error: { message: "POST only." } }, 405);
  if (!originAllowed(origin)) {
    return json({ error: { message: "This chat is only for findmyisland.com." } }, 403);
  }
  if (!apiKey) {
    return json({ error: { message: "Shared Ask is not configured yet." } }, 503);
  }
  if (!rateLimit(req)) {
    return json({ error: { message: "Too many questions from this connection. Try again in a few minutes." } }, 429);
  }

  const raw = await req.text();
  if (raw.length > MAX_BODY) {
    return json({ error: { message: "That question is too large." } }, 413);
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw);
  } catch {
    return json({ error: { message: "The request was not valid JSON." } }, 400);
  }
  if (!Array.isArray(body.messages) || body.messages.length === 0 || body.messages.length > 40) {
    return json({ error: { message: "Missing messages." } }, 400);
  }

  const names = toolNames(body);
  const atlasTurn = names.length > 0;
  const maxTokens = Number(body.max_tokens || 0);
  if (atlasTurn) {
    if (!names.every((name) => ALLOWED_TOOLS.has(name))) {
      return json({ error: { message: "Unknown tool." } }, 400);
    }
    const system = body.messages.find(
      (row) => row && typeof row === "object" && (row as Record<string, unknown>).role === "system",
    ) as Record<string, unknown> | undefined;
    const content = typeof system?.content === "string" ? system.content : "";
    if (!content.includes("atlas of islands")) {
      return json({ error: { message: "Shared Ask only answers atlas questions." } }, 400);
    }
  } else if (!(maxTokens > 0 && maxTokens <= 32)) {
    return json({ error: { message: "Shared Ask only answers atlas questions." } }, 400);
  }

  const upstream = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "gpt-4o-mini",
      max_tokens: Math.min(atlasTurn ? 1400 : 32, maxTokens || 1400),
      temperature: 0.3,
      messages: body.messages,
      ...(atlasTurn ? { tools: body.tools, tool_choice: body.tool_choice || "auto" } : {}),
    }),
  });
  const text = await upstream.text();
  return new Response(text, {
    status: upstream.status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
});
