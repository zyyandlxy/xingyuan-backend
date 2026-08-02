// GLM Agent — PWA Service Worker
// v2: 新增用户认证 + 静态资源版本化（升版本号强制 PWA 刷新旧缓存）
const CACHE = 'glm-agent-v2';
const URLS = ['/', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(URLS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  // API 请求不缓存，直接透传
  if (e.request.url.includes('/chat') || e.request.url.includes('/conversations')) {
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
