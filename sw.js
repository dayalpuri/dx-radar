// Service Worker DX Radar Pro - po první návštěvě funguje i offline (letadlový režim na balkoně)
const CACHE = 'dx-radar-v19';
const ASSETS = ['./', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './eibi.json'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE).then(cache =>
      // eibi.json nemusí existovat - proto allSettled, aby se instalace nezasekla
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
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return; // NOAA API necháme online
  // NOAA telemetrii vždy ber čerstvou z webu (network-first), zbytek z cache
  if (url.hostname.startsWith('services.swpc.noaa.gov')) return;
  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});
