/**
 * Optional production SEO hooks (load before app.js).
 * Set in config.local.js (gitignored):
 *   window.IOB_GOOGLE_SITE_VERIFICATION = "paste-from-search-console";
 */
(function () {
  const token = window.IOB_GOOGLE_SITE_VERIFICATION;
  if (!token || typeof token !== "string") return;
  const content = token.trim();
  if (!content) return;
  if (document.querySelector('meta[name="google-site-verification"]')) return;
  const meta = document.createElement("meta");
  meta.name = "google-site-verification";
  meta.content = content;
  document.head.appendChild(meta);
})();
