/* Row Tracker — main.js */

// ---- CSRF ----
// For fetch() calls that send no form body (e.g. bare POST triggers) to
// carry the token from the <meta> tag set in base.html — Flask-WTF checks
// this header when there's no form-encoded csrf_token field to read.
function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.content : "";
}

// ---- Theme toggle ----

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  localStorage.setItem("rt-theme", next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  const icon = document.querySelector(".theme-icon");
  if (icon) icon.textContent = theme === "dark" ? "☀️" : "🌙";
}

// Restore saved theme on load
(function () {
  const saved = localStorage.getItem("rt-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  updateThemeIcon(saved);
})();

// ── Shared theme-color reader for Chart.js instances ────────────────────
// Canvas colors must be resolved strings (Chart.js can't consume raw
// var(...) syntax), so every chart re-reads these from the live CSS
// custom properties instead of hardcoding a duplicate palette guess.
function cssVar(name, fallback) {
  const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return val || fallback;
}

// ── Journey waypoint modal ──────────────────────────────────────────────
// Delegated so it works on every journey route page without per-page
// init code — .wp-hit is used on both SVG waypoint markers and the
// waypoint-timeline rows.
document.addEventListener("click", function (e) {
  const hit = e.target.closest(".wp-hit");
  if (!hit) return;
  openWaypointModal(hit.dataset);
});

function openWaypointModal(data) {
  const backdrop = document.getElementById("waypointModalBackdrop");
  const modal    = document.getElementById("waypointModal");
  if (!backdrop || !modal) return;

  const passed = data.passed === "true";
  document.getElementById("waypointModalTitle").textContent = `${data.emoji} ${data.name}`;
  document.getElementById("waypointModalKm").textContent = `${Number(data.km).toLocaleString()} km mark`;

  const statusEl = document.getElementById("waypointModalStatus");
  statusEl.textContent = passed ? "✓ Passed" : "Not yet reached";
  statusEl.className = "waypoint-modal-status " + (passed ? "wpt-passed" : "wpt-locked");

  // Strip decorative suffixes/parentheticals so the search lands on the
  // actual place (e.g. "St. Louis, MO — Gateway Arch" -> "St. Louis, MO").
  const wikiTerm = data.name.split("—")[0].split(" (")[0].split(" / ")[0].trim();
  document.getElementById("waypointModalWikiLink").href =
    "https://en.wikipedia.org/wiki/Special:Search/" + encodeURIComponent(wikiTerm);

  backdrop.classList.add("day-modal-backdrop--open");
  modal.classList.add("day-modal--open");
}

function closeWaypointModal() {
  document.getElementById("waypointModalBackdrop").classList.remove("day-modal-backdrop--open");
  document.getElementById("waypointModal").classList.remove("day-modal--open");
}
