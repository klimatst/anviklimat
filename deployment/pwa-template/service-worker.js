/*
 * Optional PWA starter only. It is NOT wired into the Anvil app automatically.
 * Verify routing, authentication, cache policy and asset paths before registering it.
 * Do not cache admin/API/private responses or authenticated HTML.
 */
const CACHE_NAME = "klimaeco-static-v1";
const STATIC_ASSETS = [
  "/offline.html"
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
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Never intercept authenticated/admin or data requests. This starter only
  // provides an offline fallback for top-level navigation.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline.html"))
    );
  }
});
