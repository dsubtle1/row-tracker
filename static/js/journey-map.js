/* Row Tracker — real Leaflet/OpenStreetMap journey maps.
 *
 * Replaces the old hand-tuned SVG route illustrations. Waypoints carry
 * real lat/lon (see blueprints/gamification.py); the route line between
 * them is a smoothed curve through those real points (Catmull-Rom), not a
 * literally-traced river/highway path — see docs/feature-ideas.md for why.
 *
 * Map tiles are fetched live from OpenStreetMap on every view — unlike the
 * rest of the app's charts, there's no offline tile cache, so this one
 * feature needs network access to render fully. Standard OSM tiles are
 * always a bright basemap regardless of the app's own dark/light theme —
 * a free dark-tile alternative (CARTO) was tried and dropped because it
 * now requires an API key, which this app's self-hosted/no-signup ethos
 * rules out for a cosmetic-only improvement.
 */

function _journeyEsc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

/* Catmull-Rom spline through [lat, lon] points -> a denser point list for
 * a smooth-looking polyline, without any external routing dependency. */
function _journeySmooth(points, segmentsPerLeg) {
  segmentsPerLeg = segmentsPerLeg || 12;
  if (points.length < 3) return points;
  const at = (i) => points[Math.max(0, Math.min(points.length - 1, i))];
  const out = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
    for (let t = 0; t < segmentsPerLeg; t++) {
      const s = t / segmentsPerLeg, s2 = s * s, s3 = s2 * s;
      const lat = 0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * s
        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * s2
        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * s3);
      const lon = 0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * s
        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * s2
        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * s3);
      out.push([lat, lon]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

function _journeyWpIcon(wp, isCurrent) {
  let cls = "wp-hit journey-wp-dot";
  if (wp.passed) cls += " journey-wp-dot--passed";
  if (isCurrent) cls += " journey-wp-dot--current";
  const html =
    '<div class="' + cls + '" ' +
    'data-name="' + _journeyEsc(wp.name) + '" ' +
    'data-emoji="' + _journeyEsc(wp.emoji) + '" ' +
    'data-km="' + wp.km + '" ' +
    'data-passed="' + (wp.passed ? "true" : "false") + '"></div>';
  return L.divIcon({ className: "journey-wp-icon", html, iconSize: [18, 18], iconAnchor: [9, 9] });
}

function _journeyMarkerIcon() {
  return L.divIcon({
    className: "journey-marker-icon",
    html: '<div class="journey-marker-dot"></div>',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

/**
 * containerId: id of an empty <div> to render into.
 * waypoints: [{lat, lon, name, emoji, km, passed}, ...] in route order.
 * marker: {lat, lon} for "you are here", or null to omit (journey complete).
 */
function initJourneyMap(containerId, waypoints, marker) {
  const el = document.getElementById(containerId);
  if (!el || typeof L === "undefined") return;

  const map = L.map(containerId, { scrollWheelZoom: false });

  // Standard OSM raster tiles — free, keyless, no usage-tier surprises.
  // (CartoDB's free dark basemap now requires an API key, so it's not used
  // here despite being a nicer visual match for the dark theme.)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    subdomains: "abc",
    maxZoom: 19,
  }).addTo(map);

  const rawPoints = waypoints.map((wp) => [wp.lat, wp.lon]);
  const smoothed = _journeySmooth(rawPoints);
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--color-teal").trim() || "#cdfa3f";
  L.polyline(smoothed, { color: accent, weight: 4, opacity: 0.85 }).addTo(map);

  waypoints.forEach((wp) => {
    L.marker([wp.lat, wp.lon], { icon: _journeyWpIcon(wp, false) }).addTo(map);
  });

  if (marker) {
    L.marker([marker.lat, marker.lon], { icon: _journeyMarkerIcon(), zIndexOffset: 1000 }).addTo(map);
  }

  const bounds = L.latLngBounds(rawPoints);
  map.fitBounds(bounds, { padding: [30, 30] });

  // Re-enable scroll-to-zoom only once the map has focus, so scrolling the
  // page past the map doesn't accidentally zoom it.
  el.addEventListener("mouseenter", () => map.scrollWheelZoom.enable());
  el.addEventListener("mouseleave", () => map.scrollWheelZoom.disable());
}
