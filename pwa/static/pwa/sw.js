/* School Virtual Library - service worker (Work Package 8, offline-first).
 *
 * Caching policy (privacy-safe by design; shared lab machines are assumed):
 *  - Static assets (CSS, icons, manifest): stale-while-revalidate.
 *  - The offline shell (/offline/) is precached at install.
 *  - EVERYTHING else is NETWORK FIRST and is NEVER written to a cache by the
 *    worker. Authenticated pages, search results, AI answers and files are
 *    only stored when the USER explicitly opts in, via the page scripts
 *    (offline-reader.js writes to FILES_CACHE, offline-practice.js writes to
 *    ATTEMPTS_CACHE). The worker only ever READS those caches as an offline
 *    fallback for the exact URLs the user chose.
 *  - Logging out lands on /login/, where offline-clear.js erases those two
 *    device caches so nothing survives a session end.
 */

const SHELL_CACHE = "svl-shell-v2";
const PRECACHE_SHELL = [
  "/offline/",
  "/static/css/site.css",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(PRECACHE_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // same-origin policy

  if (url.pathname.startsWith("/static/")) {
    // Static assets: cache-first with background revalidation.
    event.respondWith(
      caches.match(request).then((hit) => {
        if (hit) {
          fetch(request)
            .then((response) => {
              if (response.ok) {
                const copy = response.clone();
                caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy)).catch(() => {});
              }
            })
            .catch(() => {});
          return hit;
        }
        return fetch(request).then((response) => {
          const copy = response.clone();
          caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy)).catch(() => {});
          return response;
        });
      })
    );
    return;
  }

  // Everything else: NETWORK FIRST with an explicit offline fallback that
  // only reads caches the USER built from the page (offline-reader.js /
  // offline-practice.js). The worker never writes these responses anywhere.
  event.respondWith(
    fetch(request).catch(() => {
      return caches.match(request).then((hit) => {
        if (hit) return hit;
        if (request.mode === "navigate") return caches.match("/offline/");
        return undefined;
      });
    })
  );
});