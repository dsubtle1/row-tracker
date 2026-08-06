/*
 * Row Tracker — service worker.
 * Cache-first for static assets (CSS/JS/icons) so the shell loads instantly
 * and the app is installable. Everything else (pages, /api/*) goes straight
 * to the network, uncached — this app's data changes daily (nightly sync,
 * badges, WOD) and a stale cached dashboard would be actively misleading.
 */

const CACHE_NAME = "row-tracker-static-v1";

const STATIC_ASSETS = [
  "/static/css/main.css",
  "/static/css/feedback.css",
  "/static/js/main.js",
  "/static/js/feedback.js",
  "/static/js/vendor/chart.umd.min.js",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png",
  "/static/img/icon-512-maskable.png",
  "/static/img/apple-touch-icon.png",
  "/static/img/favicon-32.png",
  "/static/img/favicon-64.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) {
    return; // let the browser handle it — no offline fallback for dynamic pages/API
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      });
    })
  );
});
