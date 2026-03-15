// Glade service worker — cache-first shell, network-first everything else.
// Gives the app a proper "offline" screen instead of a blank error when the
// server is unreachable.  Does NOT cache API calls or ttyd terminal streams.

const CACHE = 'glade-shell-v4';
const SHELL  = ['/'];   // just the app shell; manifest is versioned by URL

self.addEventListener('install', function (e) {
    e.waitUntil(
        caches.open(CACHE).then(function (c) { return c.addAll(SHELL); })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (e) {
    e.waitUntil(
        caches.keys().then(function (names) {
            return Promise.all(
                names.filter(function (n) { return n !== CACHE; })
                     .map(function (n) { return caches.delete(n); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function (e) {
    if (e.request.method !== 'GET') return;

    const url = new URL(e.request.url);

    // Never intercept API calls or ttyd WebSocket proxies — they need live connections.
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ttyd/')) return;

    // Navigation requests: network-first, fall back to cached shell.
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request)
                .then(function (res) {
                    var clone = res.clone();
                    caches.open(CACHE).then(function (c) { c.put(e.request, clone); });
                    return res;
                })
                .catch(function () {
                    return caches.match('/');
                })
        );
        return;
    }

    // Static assets: network-first, cache as fallback.
    e.respondWith(
        fetch(e.request)
            .then(function (res) {
                var clone = res.clone();
                caches.open(CACHE).then(function (c) { c.put(e.request, clone); });
                return res;
            })
            .catch(function () {
                return caches.match(e.request);
            })
    );
});

// Notification click — focus the existing Glade window or open a new one.
self.addEventListener('notificationclick', function (e) {
    e.notification.close();
    e.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(function (clients) {
                for (var i = 0; i < clients.length; i++) {
                    var c = clients[i];
                    if (c.url.startsWith(self.location.origin) && 'focus' in c) {
                        return c.focus();
                    }
                }
                return self.clients.openWindow('/');
            })
    );
});
