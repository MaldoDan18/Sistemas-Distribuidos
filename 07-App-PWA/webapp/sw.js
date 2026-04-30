const CACHE_NAME = 'pwa-shell-v1';
const ASSETS = [
  '/webapp/index.html', '/webapp/styles.css', '/webapp/app.js', '/webapp/manifest.json'
];

self.addEventListener('install', evt => {
  evt.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', evt => {
  evt.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', evt => {
  const url = new URL(evt.request.url);
  // network-first for API calls
  if(url.pathname.startsWith('/api/')){
    evt.respondWith(fetch(evt.request).catch(()=>caches.match('/webapp/index.html')));
    return;
  }
  // cache-first for shell
  evt.respondWith(caches.match(evt.request).then(res => res || fetch(evt.request)));
});
