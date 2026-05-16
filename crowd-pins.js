/**
 * Crowd-sourced island pins — data load + GitHub issue URL helpers.
 * Map wiring lives in app.js.
 */

const REPO_DEFAULT = "Drummond1/britishislands";

export function crowdIssueRepoSlug() {
  if (typeof window !== "undefined" && window.IOB_CORRECTION_REPO) {
    return String(window.IOB_CORRECTION_REPO)
      .replace(/^https?:\/\/github\.com\//i, "")
      .replace(/\/$/, "");
  }
  return REPO_DEFAULT;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

export async function fetchCrowdPins() {
  try {
    const res = await fetch("data/crowd_pins.json");
    if (!res.ok) return [];
    const data = await res.json();
    const pins = data.pins;
    return Array.isArray(pins) ? pins : [];
  } catch {
    return [];
  }
}

function formatCreditsLines(pin) {
  const lines = [];
  const credits = pin.credits;
  if (Array.isArray(credits) && credits.length) {
    for (const c of credits) {
      if (!c || !c.label) continue;
      const roleLabel =
        c.role === "named"
          ? "Name"
          : c.role === "verified"
            ? "Verification"
            : "Pin";
      let line = `${roleLabel}: ${c.label}`;
      if (c.sourceUrl) line += ` (source: ${c.sourceUrl})`;
      lines.push(line);
    }
  }
  if (pin.placedBy) lines.push(`Placed by: ${pin.placedBy}`);
  if (pin.namedBy) lines.push(`Named by: ${pin.namedBy}`);
  return lines;
}

/**
 * Build GitHub new-issue URL for a fresh suggestion from the in-app form.
 */
export function buildContributionIssueUrl(fields) {
  const lat = Number(fields.lat);
  const lng = Number(fields.lng);
  const name = (fields.name || "").trim();
  const note = (fields.note || "").trim();
  const nameSourceUrl = (fields.nameSourceUrl || "").trim();
  const credit = (fields.credit || "").trim();
  const existingPinId = (fields.existingPinId || "").trim();
  const kind = fields.contributionKind || "new_pin";
  const atlasId = (fields.atlasIslandId || "").trim();
  const atlasName = (fields.atlasIslandName || "").trim();

  let title = `Crowd island: ${name || "Unnamed pin"}`;
  if (kind === "fix_atlas" && atlasId) {
    title = `Atlas update: ${atlasName || atlasId}`;
  } else if (kind === "update_pin" && existingPinId) {
    title = `Community pin update: ${existingPinId}`;
  }

  const body = formatCrowdSuggestionBody(fields);
  const params = new URLSearchParams({ title, body });
  return `https://github.com/${crowdIssueRepoSlug()}/issues/new?${params.toString()}`;
}

export function buildNewCrowdSuggestionIssueUrl(fields) {
  return buildContributionIssueUrl(fields);
}

let _suggestConfigPromise = null;

/** Load routing for native submit (`window.IOB_SUGGEST_CONFIG` overrides JSON). */
export async function loadCrowdSuggestConfig() {
  if (typeof window !== "undefined" && window.IOB_SUGGEST_CONFIG && typeof window.IOB_SUGGEST_CONFIG === "object") {
    return normalizeCrowdSuggestConfig(window.IOB_SUGGEST_CONFIG);
  }
  if (!_suggestConfigPromise) {
    _suggestConfigPromise = fetch("data/crowd_suggest_config.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : {}))
      .then((raw) => normalizeCrowdSuggestConfig(raw))
      .catch(() => normalizeCrowdSuggestConfig({}));
  }
  return _suggestConfigPromise;
}

function normalizeCrowdSuggestConfig(raw) {
  return {
    provider: String(raw?.provider || "none").toLowerCase(),
    formsubmitEmail: String(raw?.formsubmitEmail || "").trim(),
    formspreeId: String(raw?.formspreeId || "").trim(),
    web3formsAccessKey: String(raw?.web3formsAccessKey || "").trim(),
    webhookUrl: String(raw?.webhookUrl || "").trim(),
    subject: String(raw?.subject || "Isles of Britain — crowd island suggestion").trim(),
  };
}

export function isCrowdSuggestConfigured(config) {
  const p = String(config?.provider || "none").toLowerCase();
  if (p === "formsubmit") return Boolean(config?.formsubmitEmail);
  if (p === "formspree") return Boolean(config?.formspreeId);
  if (p === "web3forms") return Boolean(config?.web3formsAccessKey);
  if (p === "webhook") return Boolean(config?.webhookUrl);
  return false;
}

/** Soft verification: names should cite a public source when possible. */
export function validateContributionFields(fields) {
  const name = String(fields?.name || "").trim();
  const source = String(fields?.nameSourceUrl || "").trim();
  const skip = Boolean(fields?.skipSourceCheck);
  const note = String(fields?.note || "").trim();
  const proposed = String(fields?.proposedChanges || "").trim();
  const photos = String(fields?.photoUrls || "").trim();
  const kind = fields?.contributionKind || "new_pin";

  if (kind === "fix_atlas") {
    if (!proposed && !note && !name && !photos) {
      return {
        ok: false,
        message:
          "Describe what you want to improve — use “What should change?”, description, name, or photo links.",
      };
    }
  } else if (!name && !note && !photos) {
    return {
      ok: false,
      message: "Add at least a name, description, or photo link so reviewers know what you mean.",
    };
  }

  if (name && !source && !skip) {
    return {
      ok: false,
      message:
        "Please add a name source link (Wikipedia, OSM, gazetteer, etc.) so we can verify the name. " +
        "Or tick “No public link yet” below.",
    };
  }
  if (source) {
    try {
      const u = new URL(source);
      if (!/^https?:$/i.test(u.protocol)) {
        return { ok: false, message: "Source link must start with http:// or https://" };
      }
    } catch {
      return { ok: false, message: "Source link doesn’t look like a valid URL." };
    }
  }
  return { ok: true };
}

export function formatCrowdSuggestionBody(fields) {
  const {
    lat,
    lng,
    name = "",
    note = "",
    nameSourceUrl = "",
    credit = "",
    existingPinId = "",
    contactEmail = "",
    photoUrls = "",
    contributionKind = "new_pin",
    atlasIslandId = "",
    atlasIslandName = "",
    proposedChanges = "",
  } = fields;
  const kindLabel =
    {
      new_pin: "New island / map pin",
      update_pin: "Update community pin",
      fix_atlas: "Suggest atlas changes",
    }[contributionKind] || contributionKind;

  const photos = String(photoUrls)
    .split(/\n/)
    .map((s) => s.trim())
    .filter(Boolean);

  const lines = [
    "Isles of Britain — contributor submission",
    "",
    `Type: ${kindLabel}`,
    contributionKind === "fix_atlas" && atlasIslandId
      ? `Atlas island: ${atlasIslandName || atlasIslandId} (id: ${atlasIslandId})`
      : "",
    Number.isFinite(lat) && Number.isFinite(lng)
      ? `Coordinates: ${lat}, ${lng} (WGS84)`
      : "",
    Number.isFinite(lat) && Number.isFinite(lng)
      ? `Map: https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=15/${lat}/${lng}`
      : "",
    "",
    `Suggested name: ${String(name).trim() || "(unchanged / unnamed)"}`,
    `Description / notes: ${String(note).trim() || "—"}`,
    proposedChanges ? `Proposed changes: ${String(proposedChanges).trim()}` : "",
    `Name source URL: ${String(nameSourceUrl).trim() || "—"}`,
    photos.length ? `Photo URLs:\n${photos.map((u) => `- ${u}`).join("\n")}` : "Photo URLs: —",
    `Credit / recognition: ${String(credit).trim() || "—"}`,
    `Existing crowd pin id: ${String(existingPinId).trim() || "—"}`,
    `Contact (optional): ${String(contactEmail).trim() || "—"}`,
    "",
    `Submitted from: ${typeof location !== "undefined" ? location.href : "—"}`,
    `Time (UTC): ${new Date().toISOString()}`,
  ].filter(Boolean);
  return lines.join("\n");
}

/** POST to FormSubmit, Formspree, Web3Forms, or a custom webhook. */
export async function submitCrowdSuggestion(fields, config) {
  const cfg = config || (await loadCrowdSuggestConfig());
  const body = formatCrowdSuggestionBody(fields);
  const subject = cfg.subject;
  const label = fields.name?.trim() || "Unnamed island pin";

  if (cfg.provider === "formsubmit" && cfg.formsubmitEmail) {
    const fd = new FormData();
    fd.append("_subject", subject);
    fd.append("_template", "table");
    fd.append("_captcha", "false");
    fd.append("name", label);
    fd.append("message", body);
    if (fields.contactEmail?.trim()) fd.append("_replyto", fields.contactEmail.trim());
    const res = await fetch(
      `https://formsubmit.co/ajax/${encodeURIComponent(cfg.formsubmitEmail)}`,
      { method: "POST", body: fd, headers: { Accept: "application/json" } },
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.message || `Submit failed (${res.status})`);
    return { provider: "formsubmit" };
  }

  if (cfg.provider === "formspree" && cfg.formspreeId) {
    const res = await fetch(`https://formspree.io/f/${cfg.formspreeId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        _subject: subject,
        name: label,
        message: body,
        email: fields.contactEmail?.trim() || undefined,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.error || `Submit failed (${res.status})`);
    return { provider: "formspree" };
  }

  if (cfg.provider === "web3forms" && cfg.web3formsAccessKey) {
    const res = await fetch("https://api.web3forms.com/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        access_key: cfg.web3formsAccessKey,
        subject,
        from_name: label,
        message: body,
        email: fields.contactEmail?.trim() || "anonymous@findmyisland.com",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data?.success === false) {
      throw new Error(data?.message || `Submit failed (${res.status})`);
    }
    return { provider: "web3forms" };
  }

  if (cfg.provider === "webhook" && cfg.webhookUrl) {
    const res = await fetch(cfg.webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ subject, name: label, body, fields }),
    });
    if (!res.ok) throw new Error(`Submit failed (${res.status})`);
    return { provider: "webhook" };
  }

  throw new Error(
    "Online submission is not configured on this site. The maintainer can set data/crowd_suggest_config.json.",
  );
}

export function buildNameCrowdPinIssueUrl(pin, fields = {}) {
  const name = (fields.name || "").trim();
  const nameSourceUrl = (fields.nameSourceUrl || "").trim();
  const credit = (fields.credit || "").trim();
  const note = (fields.note || "").trim();
  const title = `Name crowd pin ${pin.id}: ${name || "proposal"}`;
  const lines = [
    "## Existing crowd pin",
    "",
    `- **id**: \`${pin.id}\``,
    `- **Current label**: ${pin.name || "(unnamed)"}`,
    `- **Coordinates**: ${pin.lat}, ${pin.lng}`,
    pin.note ? `- **Existing note**: ${pin.note}` : "",
    "",
    "## Proposed name",
    "",
    name || "_Unknown — help identify_",
    "",
    note ? ["## What you see", "", note, ""].join("\n") : "",
    "## Name source (optional)",
    "",
    nameSourceUrl || "_—_",
    "",
    "## Credit (optional)",
    "",
    credit || "_Anonymous_",
    "",
  ].filter(Boolean);
  const body = lines.join("\n");
  const params = new URLSearchParams({ title, body });
  return `https://github.com/${crowdIssueRepoSlug()}/issues/new?${params.toString()}`;
}

export function crowdPinPopupHtml(pin) {
  const name = pin.name ? esc(pin.name) : "<em>Unnamed — needs ID</em>";
  const status = esc(pin.status || "open");
  const note = pin.note ? `<p class="crowd-popup__note">${esc(pin.note)}</p>` : "";
  const src =
    pin.nameSourceUrl
      ? `<p class="crowd-popup__src"><a href="${esc(pin.nameSourceUrl)}" target="_blank" rel="noopener noreferrer">Name source ↗</a></p>`
      : "";

  const creditLines = formatCreditsLines(pin);
  let creditsBlock = "";
  if (creditLines.length) {
    creditsBlock =
      `<div class="crowd-popup__credit"><strong>Recognition</strong><ul>` +
      creditLines.map((l) => `<li>${esc(l)}</li>`).join("") +
      `</ul></div>`;
  }

  const simpleNameIssue = buildNameCrowdPinIssueUrl(pin);

  return `
    <div class="crowd-popup">
      <strong class="crowd-popup__title">${name}</strong>
      <span class="crowd-popup__badge">Community · ${status}</span>
      ${note}
      ${src}
      ${creditsBlock}
      <p class="crowd-popup__id"><code>${esc(pin.id)}</code></p>
      <button
        type="button"
        class="crowd-popup__action crowd-popup__action--edit-details"
        data-crowd-id="${esc(pin.id)}"
        data-crowd-lat="${Number(pin.lat)}"
        data-crowd-lng="${Number(pin.lng)}"
      >Add or edit details</button>
      <a class="crowd-popup__action crowd-popup__action--github" href="${esc(simpleNameIssue)}" target="_blank" rel="noopener noreferrer">GitHub issue ↗</a>
    </div>`;
}

export const CROWD_MARKER_STYLE = {
  radius: 8,
  color: "#3d2e0a",
  weight: 2,
  fillColor: "#f5c542",
  fillOpacity: 0.92,
};
