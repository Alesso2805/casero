declare const self: ServiceWorkerGlobalScope;

// It makes the app installable and stores nothing: no offline mode and no cached /api
// (CLAUDE.md, stack). Push notifications arrive here with CS-33.
self.addEventListener("install", () => {
  void self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

export {};
