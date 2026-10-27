/* KampusDey service worker: static assets + offline page only.
   Never caches map tiles, authenticated responses or other HTML. */
const VERSION = "kd-{{ version|escapejs }}-v1";
const ASSETS = {{ assets|safe }};
const OFFLINE = "/offline/";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll([...ASSETS, OFFLINE])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // tiles and third parties: never touched
  if (req.mode === "navigate") {
    // Network-first for HTML; fall back to the offline page only.
    event.respondWith(fetch(req).catch(() => caches.match(OFFLINE)));
    return;
  }
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data.json(); } catch (e) { data = { head: "KampusDey", body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.head || "KampusDey", { body: data.body || "", data: { url: data.url || "/" }, icon: "/static/img/icon-192.png" }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(self.clients.openWindow(event.notification.data.url || "/"));
});
