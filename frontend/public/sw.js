/**
 * Service worker: installable, and honest about being offline.
 *
 * What it deliberately does NOT do is cache anything from the API. A cached list of users,
 * a cached `/me`, a cached permission set — each of those is an authorization decision
 * frozen in a file on somebody's phone. Suspend an account and the stale copy still says
 * "active"; revoke a role and the stale copy still lists the menu. Nothing under the API
 * path is stored here, ever, and a request to it is never answered from a cache.
 *
 * What it does is keep the built shell — the HTML, the JavaScript, the CSS, the fonts and
 * icons — so that opening the app with no signal shows the app saying "you are offline"
 * rather than the browser's error page. Which screen a person sees when the train enters a
 * tunnel is the whole difference between "the app told me" and "the app is broken".
 */

// Bumped whenever the cached shell should be thrown away. The build's own asset names are
// hashed, so stale JavaScript is already impossible; this is for the entries that are not.
const CACHE = "dhruv-shell-v1";

// Enough to render the application frame and its branding with no network at all.
const SHELL = ["/", "/manifest.webmanifest", "/favicon-32.png", "/icon-192.png"];

self.addEventListener("install", (event) => {
  // One missing file must not fail the whole install, so each is added on its own.
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => Promise.allSettled(SHELL.map((path) => cache.add(path))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

/** True for anything that talks to the API — never cached, never served from a cache. */
function isApi(url) {
  return url.pathname.startsWith("/api/");
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (isApi(url)) return; // Straight to the network, and a failure stays a failure.

  // A navigation: the network decides, and the cached shell is the fallback. Network-first
  // rather than cache-first because a deployed fix should reach people on the next load,
  // not whenever a cache happens to expire.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          void caches.open(CACHE).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/").then((cached) => cached ?? offlinePage())),
    );
    return;
  }

  // Same-origin assets only. Build output is content-hashed, so a cached hit is always the
  // right file and a miss is fetched and kept.
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ??
        fetch(request).then((response) => {
          if (response.ok && response.type === "basic") {
            const copy = response.clone();
            void caches.open(CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        }),
    ),
  );
});

/** Last resort: the cached shell is gone too, so say so in plain words. */
function offlinePage() {
  return new Response(
    `<!doctype html><html lang="en"><head><meta charset="utf-8">
     <meta name="viewport" content="width=device-width,initial-scale=1">
     <title>You are offline</title>
     <style>body{font-family:system-ui,sans-serif;margin:0;display:grid;place-items:center;
     min-height:100vh;background:#f6f8fb;color:#1e293b;padding:2rem;text-align:center}
     h1{font-size:1.25rem;margin:0 0 .5rem}p{margin:0;color:#475569}</style></head>
     <body><div><h1>You are offline</h1>
     <p>Dhruv Online Academy needs a connection. Reconnect and reload this page.</p>
     </div></body></html>`,
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}
