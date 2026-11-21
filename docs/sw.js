// Arrabona Naptár Mobil – offline működés. A saját fájljain kívül semmit nem tárol.
// Hálózat elsőbbség (így a frissítés azonnal megjelenik), hálózat nélkül a tárolt példány.
const CACHE = "anm-1.0.1";
const FILES = ["./", "index.html", "app.js", "app.css", "manifest.webmanifest",
               "icon-180.png", "icon-192.png", "icon-512.png", "logo-64.png"];

self.addEventListener("install", ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", ev => {
  ev.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", ev => {
  const url = new URL(ev.request.url);
  if (ev.request.method !== "GET" || url.origin !== location.origin) return;   // időjárás, Dropbox: nem tároljuk
  ev.respondWith(
    fetch(ev.request, { cache: "no-cache" })
      .then(r => { if (r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(ev.request, cp)); } return r; })
      .catch(() => caches.match(ev.request, { ignoreSearch: true }))
  );
});
