// Service Worker DX Radar Pro - po první návštěvě funguje i offline (letadlový režim na balkoně)
const CACHE = 'dx-radar-v43';
const ASSETS = ['./', './index.html', './scoring.js', './legal.html', './LICENSE', './manifest.webmanifest', './icon-192.png', './icon-512.png', './schedule.json', './schedule_eibi.json'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache =>
      // schedule*.json nemusí existovat - proto allSettled, aby se instalace nezasekla
      Promise.allSettled(ASSETS.map(url => cache.add(new Request(url, { cache: 'reload' }))))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  // Cizí originy (NOAA telemetrie, streamy) SW neřeší - jdou vždy čerstvě ze sítě
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;
  // Rozvrhy (schedule*.json/meta) = network-first: aby se k nainstalované PWA dostal
  // čerstvý auto-sync z GitHubu (cron). Offline fallback = poslední z cache.
  if (/\/schedule(_eibi)?\.(json|meta\.json)$/.test(url.pathname)) {
    event.respondWith(
      fetch(event.request).then(resp => {
        // chybová odpověď (404/500) nesmí přepsat funkční offline rozvrh v cache
        if (!resp.ok) return caches.match(event.request).then(c => c || resp);
        const copy = resp.clone();
        caches.open(CACHE).then(c => c.put(event.request, copy)).catch(() => {});
        return resp;
      }).catch(() => caches.match(event.request))
    );
    return;
  }
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});
