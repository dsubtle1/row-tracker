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
