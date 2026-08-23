/* School Virtual Library - service worker (Phase 11).
 *
 * Caching policy is deliberately conservative:
 *  - Static assets (CSS, icons, manifest): stale-while-revalidate.
 *  - Navigations (pages): NETWORK FIRST. Authenticated content, PDFs,
 *    search results and AI answers are never stored offline; only the
 *    static shell falls back when the network is gone.
 *  - The worker itself is served with no-store.
 */

const CACHE_NAME = "svl-shell-v1";
const SHELL = [
  "/offline/",
  "/static/css/site.css",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((hit) => {
        if (hit) {
          fetch(request).then((response) => {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
          }).catch(() => {});
          return hit;
        }
        return fetch(request).then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
          return response;
        });
      })
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => caches.match("/offline/"))
    );
  }
});