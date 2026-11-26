// OmniKit 個人指揮台 Service Worker（v3）：API 永遠直連，靜態外殼網路優先
const CACHE_NAME = "omnikit-cockpit-v3";
const SHELL_ASSETS = ["/", "/style.css", "/app.js", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        if (resp.ok && url.origin === self.location.origin && SHELL_ASSETS.includes(url.pathname)) {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});
