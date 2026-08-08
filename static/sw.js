// 星媛 — PWA Service Worker
// v8（2026-08-08）：3.0.0 App 远程加载模式，app.js 变更，缓存版本升到 v8
//   - activate 时清掉所有旧缓存（glm-agent-v2 / xingyuan-shell-v7 等）
//   - 静态资源：stale-while-revalidate（先返回缓存、后台更新，兼顾速度与新鲜度）
//   - API 请求：一律网络直连、绝不缓存（/auth /health /chat /conversations /iteration）
//   - SW 更新后自动刷新所有受控页面，让老用户立即拿到新界面
const CACHE = 'xingyuan-shell-v8';
const SHELL = ['/', '/manifest.json', '/js/app.js', '/css/app.css'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(SHELL))
      .catch(() => {}) // 缺个别资源不影响安装
  );
  self.skipWaiting(); // 立即接管，不等旧页面关闭
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
      // 强制刷新所有已打开的页面，避免继续用旧版 index.html
      .then(() => self.clients.matchAll({ type: 'window' }))
      .then(clients => clients.forEach(c => c.navigate(c.url)))
  );
});

// API 路径一律不缓存（路径含这些片段即视为 API）
function isApi(url) {
  return /\/auth\/|\/health|\/chat\b|\/conversations|\/iteration|\/feedback|\/memory/.test(url.pathname);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // POST/PUT/DELETE 不处理
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;  // 跨域请求不处理
  if (isApi(url)) return;                           // API 走网络

  // 静态资源：stale-while-revalidate
  e.respondWith(
    caches.open(CACHE).then(async cache => {
      const cached = await cache.match(req, { ignoreSearch: req.mode === 'navigate' });
      const network = fetch(req)
        .then(res => {
          if (res.ok && res.type === 'basic') cache.put(req, res.clone());
          return res;
        })
        .catch(() => null);
      return cached || network;
    })
  );
});
