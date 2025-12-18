const CACHE_NAME = "fruitveg-cache-v2";  // v2 kiya taaki old cache clearho jaye
const urlsToCache = [
  "/",                        // home page
  "/login",                   // login page cache
  "/static/css/style.css",    // main CSS
  "/static/js/main.js",        // JS file (agar hai toh)
  "/static/manifest.json",    // manifest
  "/static/images/android-chrome-192x192.png",
  "/static/images/android-chrome-512x512.png",
  "/static/images/apple-touch-icon.png",
  "/static/images/favicon-16x16.png",
  "/static/images/favicon-32x32.png",
  "/static/images/favicon.ico"
];

// Install Service Worker & cache files
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("Caching PWA files...");
      return cache.addAll(urlsToCache);
    })
  );
});

// Activate & clear old cache
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))
      );
    })
  );
});


// Fetch from cache first, then network
self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});




