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
export function buildNewCrowdSuggestionIssueUrl(fields) {
  const lat = Number(fields.lat);
  const lng = Number(fields.lng);
  const name = (fields.name || "").trim();
  const note = (fields.note || "").trim();
  const nameSourceUrl = (fields.nameSourceUrl || "").trim();
  const credit = (fields.credit || "").trim();
  const existingPinId = (fields.existingPinId || "").trim();

  const title = `Crowd island: ${name || "Unnamed pin"}`;
  const lines = [
    "## Location",
    "",
    `- **Latitude**: ${lat}`,
    `- **Longitude**: ${lng}`,
    existingPinId ? `- **Existing crowd pin id**: \`${existingPinId}\`` : "",
    "",
    "## Name (optional)",
    "",
    name || "_Unknown — help identify_",
    "",
    "## What you see (optional)",
    "",
    note || "_—_",
    "",
    "## Name source URL (optional)",
    "",
    nameSourceUrl || "_—_",
    "",
    "## Credit (optional)",
    "",
    credit || "_Anonymous_",
    "",
    "## For reviewers",
    "",
    "Please triage per `docs/CROWD-PINS.md` and `docs/ETHICS.md`.",
    "",
  ].filter((x) => x !== "");
  const body = lines.join("\n");
  const params = new URLSearchParams({ title, body });
  return `https://github.com/${crowdIssueRepoSlug()}/issues/new?${params.toString()}`;
}

export function buildNameCrowdPinIssueUrl(pin) {
  const title = `Name crowd pin ${pin.id}`;
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
    "<!-- Your suggested name -->",
    "",
    "## Name source (optional)",
    "",
    "<!-- URL to Wikipedia, OSM, gazetteer, etc. -->",
    "",
    "## Credit (optional)",
    "",
    "<!-- How you'd like to appear -->",
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
      <a class="crowd-popup__action" href="${esc(simpleNameIssue)}" target="_blank" rel="noopener noreferrer">Suggest a name ↗</a>
    </div>`;
}

export const CROWD_MARKER_STYLE = {
  radius: 8,
  color: "#3d2e0a",
  weight: 2,
  fillColor: "#f5c542",
  fillOpacity: 0.92,
};
