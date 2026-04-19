// NSE Risk Monitor — Service Worker
// Cache strategy:
//   App shell  → Cache-first (fast load)
//   risk_factors.json → Stale-while-revalidate (show last known, fetch fresh in bg)
//   Yahoo Finance / CORS proxies → Network-only (never cache live prices)

const CACHE = "nse-risk-v2";
const SHELL  = ["./", "./index.html", "./manifest.json"];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // ── Network-only: live price sources ──────────────────────────────────────
  const liveHosts = ["query1.finance.yahoo.com","corsproxy.io","allorigins.win",
                     "codetabs.com","thingproxy.freeboard.io","cors.sh"];
  if (liveHosts.some(h => url.hostname.includes(h))) {
    e.respondWith(fetch(e.request).catch(() => new Response("{}", {headers:{"Content-Type":"application/json"}})));
    return;
  }

  // ── Stale-while-revalidate: daily risk data ────────────────────────────────
  if (url.pathname.endsWith("risk_factors.json")) {
    e.respondWith(
      caches.open(CACHE).then(async cache => {
        const cached = await cache.match(e.request);
        const fetchPromise = fetch(e.request)
          .then(res => { if (res.ok) cache.put(e.request, res.clone()); return res; })
          .catch(() => null);
        return cached || await fetchPromise;
      })
    );
    return;
  }

  // ── Cache-first: app shell ─────────────────────────────────────────────────
  e.respondWith(
    caches.match(e.request)
      .then(cached => cached || fetch(e.request).then(res => {
        if (res.ok && url.origin === self.location.origin) {
          caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        }
        return res;
      }))
  );
});
