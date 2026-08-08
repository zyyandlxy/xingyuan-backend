// ═══════════════════════════════════════════
// 星媛 — 主应用脚本 (v2.7)
// 纯前端壳：后端公网部署，bootstrapUrls 自动寻址
// 模块化、Capacitor Preferences 优先、SVG 图标
// ═══════════════════════════════════════════

// ═══════════════════════════════════════════
// 应用配置（内联，不可外部修改）
// ═══════════════════════════════════════════
const CONFIG = {
  // 多个引导地址（按优先级排序）
  // GitHub Raw: 更新即时，国内可能慢但通常能通
  // jsDelivr: CDN 缓存 12h，国内快但更新滞后
  bootstrapUrls: [
    'https://raw.githubusercontent.com/zyyandlxy/xingyuan-backend/master/backend-url.txt',
    'https://cdn.jsdelivr.net/gh/zyyandlxy/xingyuan-backend@master/backend-url.txt',
  ],
  // 硬编码兜底（当所有引导源都不可达时使用）
  // ⚠ 仅限开发/局域网环境，公网用户无法使用
  fallbackLan: 'https://xingyuan-backend.onrender.com',
  // 单个引导源超时（ms）
  bootstrapTimeout: 8000,
  // 健康检查超时（ms）
  healthTimeout: 4000,
  // 重试间隔（ms）
  retryDelay: 2000,
  appName: '星媛',
  appDescription: '你的专属 AI 智能助手',
};

// ═══════════════════════════════════════════
// SVG 图标库（替代所有 emoji）
// ═══════════════════════════════════════════
const I = {
  // 星标 — Logo / 助手头像（五色渐变：红→橙→黄→绿→紫）
  star: '<svg class="icon" viewBox="0 0 24 24"><defs><linearGradient id="starGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#ef4444"/><stop offset="20%" stop-color="#f97316"/><stop offset="40%" stop-color="#facc15"/><stop offset="60%" stop-color="#22c55e"/><stop offset="80%" stop-color="#a855f7"/></linearGradient></defs><path d="M12 2l2.4 7.2h7.6l-6 4.8 2.4 7.2-6.4-4.8-6.4 4.8 2.4-7.2-6-4.8h7.6z" style="fill:url(#starGrad);stroke:none"/></svg>',
  // 用户
  user: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-7 8-7s8 3 8 7"/></svg>',
  // 发送箭头
  send: '<svg class="icon" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9"/></svg>',
  // 停止方块
  stop: '<svg class="icon" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>',
  // 菜单汉堡
  menu: '<svg class="icon" viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  // 关闭 X
  close: '<svg class="icon" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  // 垃圾桶
  trash: '<svg class="icon" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
  // 加号
  plus: '<svg class="icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  // 退出
  logout: '<svg class="icon" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
  // 大脑/记忆
  brain: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 2a4 4 0 0 1 4 4c0 1.2-.5 2.3-1.3 3a4 4 0 0 1 0 6 4 4 0 1 1-5.4-6 4 4 0 0 1 0-6A4 4 0 0 1 12 2z"/><path d="M12 6v12"/></svg>',
  // 在线圆点
  dot: '<svg class="icon-fill" viewBox="0 0 8 8" style="width:8px;height:8px"><circle cx="4" cy="4" r="3" fill="#22c55e"/></svg>',
  // 聊天气泡
  chat: '<svg class="icon" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
};

// ═══════════════════════════════════════════
// 持久化存储（Capacitor Preferences 优先，localStorage 兜底）
// ═══════════════════════════════════════════
const Store = {
  async _cap() {
    try {
      // Capacitor 6: Preferences 在 Capacitor.Plugins 下
      const P = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Preferences;
      if (P) return P;
    } catch (e) { /* 降级到 localStorage */ }
    return null;
  },

  async get(key) {
    const cap = await this._cap();
    if (cap) {
      try { const r = await cap.get({ key }); return r.value || ''; } catch (e) {}
    }
    return localStorage.getItem(key) || '';
  },

  async set(key, value) {
    const cap = await this._cap();
    if (cap) {
      try { await cap.set({ key, value: String(value || '') }); return; } catch (e) {}
    }
    localStorage.setItem(key, value || '');
  },

  async remove(key) {
    const cap = await this._cap();
    if (cap) {
      try { await cap.remove({ key }); return; } catch (e) {}
    }
    localStorage.removeItem(key);
  },

  async getJSON(key) {
    const raw = await this.get(key);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
  },

  async setJSON(key, obj) {
    await this.set(key, JSON.stringify(obj));
  },
};

// ═══════════════════════════════════════════
// 全局状态
// ═══════════════════════════════════════════
let A = '';            // 运行时后端地址（启动时自动获取）
let T = '';           // JWT token
let U = null;         // 用户对象
let cid = null;       // 当前会话 ID
let convs = [];       // 会话列表
let busy = false;     // 是否正在生成
let ac = null;        // AbortController
let authMode = 'login';
let _picked = [];     // 待发送图片 [{src}]
let _lastImgs = [];   // 最近一次携带的图片（供重试）

// ═══════════════════════════════════════════
// UI 工具函数
// ═══════════════════════════════════════════
function tt(m) {
  const e = document.getElementById('toast');
  e.textContent = m;
  e.className = 'toast show';
  clearTimeout(e._t);
  e._t = setTimeout(() => e.classList.remove('show'), 2200);
}

function sd() {
  requestAnimationFrame(() => {
    const e = document.getElementById('ml');
    e.scrollTop = e.scrollHeight;
  });
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function htm(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function ss(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function autoResize(e) {
  e.style.height = 'auto';
  e.style.height = Math.min(e.scrollHeight, 100) + 'px';
}

// ═══════════════════════════════════════════
// Auth 认证
// ═══════════════════════════════════════════
function swAt(m) {
  authMode = m;
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('loginForm').style.display = m === 'login' ? '' : 'none';
  document.getElementById('regForm').style.display = m === 'reg' ? '' : 'none';
  document.querySelectorAll('.auth-tab')[m === 'login' ? 0 : 1].classList.add('active');
}

async function doLogin(e) {
  e.preventDefault();
  const b = document.getElementById('lb');
  b.disabled = true; b.textContent = '登录中...';
  try {
    const r = await fetch(A + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: document.getElementById('lu').value.trim(),
        password: document.getElementById('lp').value,
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '失败');
    T = d.data.token;
    U = { id: d.data.id, username: d.data.username, nickname: d.data.nickname, avatar: d.data.avatar || '' };
    await Store.set('xyt', T);
    await Store.setJSON('xyu', U);
    tt('欢迎回来，' + U.nickname + ' ✨');
    enterChat();
  } catch (e) { tt('❌ ' + e.message); }
  b.disabled = false; b.textContent = '登 录';
}

async function doReg(e) {
  e.preventDefault();
  const p = document.getElementById('rp').value;
  if (p !== document.getElementById('rp2').value) { tt('❌ 两次密码不一致'); return; }
  if (p.length < 8) { tt('❌ 密码至少需要 8 位'); return; }
  if (!/[a-zA-Z]/.test(p)) { tt('❌ 密码需要包含至少一个字母'); return; }
  if (!/\d/.test(p)) { tt('❌ 密码需要包含至少一个数字'); return; }
  const un = document.getElementById('ru').value.trim().toLowerCase();
  if (un && p.toLowerCase().includes(un)) { tt('❌ 密码不能包含用户名'); return; }
  const b = document.getElementById('rb');
  b.disabled = true; b.textContent = '注册中...';
  try {
    const r = await fetch(A + '/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: document.getElementById('ru').value.trim(),
        password: p,
        nickname: document.getElementById('rn').value.trim(),
      }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || '失败');
    T = d.data.token;
    U = { id: d.data.id, username: d.data.username, nickname: d.data.nickname, avatar: d.data.avatar || '' };
    await Store.set('xyt', T);
    await Store.setJSON('xyu', U);
    tt('注册成功！' + U.nickname + ' 🎉');
    enterChat();
  } catch (e) { tt('❌ ' + e.message); }
  b.disabled = false; b.textContent = '注 册';
}

async function logout() {
  T = ''; U = null; cid = null; convs = [];
  await Store.remove('xyt');
  await Store.remove('xyu');
  closeSb();
  ss('authScreen');
  tt('已退出');
}

// ═══════════════════════════════════════════
// Chat 聊天核心
// ═══════════════════════════════════════════
function ab(r, c, retryCb) {
  const el = document.createElement('div');
  el.className = 'msg-row ' + r;
  const icon = r === 'user' ? I.user : r === 'assistant' ? I.star : '';
  // 用户已设置头像时，用头像图片替代默认图标
  const avHtml = r === 'system' ? '' :
    (r === 'user' && U && U.avatar)
      ? '<div class="msg-av"><img class="av-img" src="' + U.avatar + '" alt=""/></div>'
      : '<div class="msg-av">' + icon + '</div>';
  let h = avHtml + '<div class="msg-b"></div>';
  if (retryCb && r === 'system') {
    h += '<div class="msg-actions"><button class="retry-btn">🔄 重试</button></div>';
  }
  el.innerHTML = h;
  renderMsgBody(el.querySelector('.msg-b'), c);
  if (retryCb && r === 'system') {
    el.querySelector('.retry-btn').onclick = retryCb;
  }
  document.getElementById('ml').appendChild(el);
  sd();
  return el;
}

function at() {
  const el = document.createElement('div');
  el.className = 'msg-row assistant msg-typing';
  el.id = 'ty';
  el.innerHTML = '<div class="msg-av">' + I.star + '</div><div class="msg-b"><div class="dots"><span></span><span></span><span></span></div></div>';
  document.getElementById('ml').appendChild(el);
  sd();
}

function rt() { const e = document.getElementById('ty'); if (e) e.remove(); }

function kd(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}

async function send(retryText, retryImgs) {
  if (busy) { stop(); return; }
  hideFeedback();
  const inp = document.getElementById('inp');
  const imgs = retryImgs || _picked.map(function (p) { return p.src; });
  const hasImg = imgs.length > 0;
  const text = (retryText || inp.value.trim()) || (hasImg ? '看看这张图片' : '');
  if (!text && !hasImg) return;
  if (!retryText) {
    inp.value = ''; inp.style.height = 'auto';
    _lastImgs = imgs;
    clearTray();
    ab('user', renderContentWithImages(text, imgs));
  }
  at();
  const btn = document.getElementById('sbtn');
  btn.innerHTML = I.stop;
  btn.classList.add('stop');
  busy = true;
  await stream(text, imgs);
  btn.innerHTML = I.send;
  btn.classList.remove('stop');
  busy = false;
}

function stop() { if (ac) { ac.abort(); ac = null; } }

async function stream(text, imgs) {
  ac = new AbortController();
  let b = null, full = '';
  try {
    const r = await fetch(A + '/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + T },
      body: JSON.stringify({
        messages: [{ role: 'user', content: text }],
        images: (imgs && imgs.length) ? imgs : undefined,
        stream: true,
        conversation_id: cid || undefined,
      }),
      signal: ac.signal,
    });
    if (!r.ok) {
      // 非 2xx：通常是 401（token 失效）或 502（后端错误）
      let detail = '请求失败 (' + r.status + ')';
      try {
        const err = await r.json();
        if (err && err.detail) detail = err.detail;
      } catch (e) { /* 非 JSON 响应 */ }
      if (r.status === 401) {
        // token 失效，清理会话并返回登录页
        T = ''; U = null; cid = null;
        await Store.remove('xyt');
        await Store.remove('xyu');
        ss('authScreen');
        tt('登录已过期，请重新登录');
        return;
      }
      rt();
      ab('system', '⚠ ' + detail, () => send(text, imgs));
      return;
    }
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let ev = '';  // 当前 SSE 事件名（event: 行）
    rt();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const l of lines) {
        const line = l.replace(/\r$/, '');
        // sse-starlette 格式：event: xxx 与 data: {json} 各占一行
        if (line.startsWith('event:')) { ev = line.slice(6).trim(); continue; }
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (!raw || raw === '[DONE]') { ev = ''; continue; }
        try {
          const p = JSON.parse(raw);
          if (ev === 'done') {
            cid = p.conversation_id || cid;
          } else if (ev === 'delta') {
            const d = p.delta || '';
            if (d) {
              full += d;
              if (!b) { rt(); b = ab('assistant', ''); }
              b.querySelector('.msg-b').textContent = full;
              sd();
            }
          } else if (ev === 'error') {
            if (!b) { rt(); b = ab('system', '', () => send(text, imgs)); }
            b.querySelector('.msg-b').textContent = '⚠ ' + (p.error || '出错了');
          }
          ev = '';
        } catch (e) { /* 忽略解析错误 */ }
      }
    }
    if (!full && b) b.querySelector('.msg-b').textContent = '(空)';
    if (full) showFeedback();
  } catch (e) {
    if (e.name !== 'AbortError') {
      rt();
      ab('system', '⚠ ' + (e.message || '网络请求失败'), () => send(text, imgs));
    }
  }
  ac = null;
}

// ═══════════════════════════════════════════
// Sidebar 侧边栏
// ═══════════════════════════════════════════
function openSb() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('ov').classList.add('show');
  renderSb();
}

function closeSb() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('ov').classList.remove('show');
}

async function loadCvs() {
  try {
    const r = await fetch(A + '/conversations?page_size=50', {
      headers: { 'Authorization': 'Bearer ' + T },
    });
    if (r.ok) { const d = await r.json(); convs = d.items || []; }
  } catch (e) { /* 静默处理 */ }
}

async function renderSb() {
  await loadCvs();
  const el = document.getElementById('cvList');
  if (!convs.length) {
    el.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text3);font-size:12px">暂无对话</div>';
    return;
  }
  el.innerHTML = convs.map(c =>
    '<div class="cv-item' + (c.id === cid ? ' on' : '') + '" onclick="swCv(\'' + c.id + '\')">' +
    '<span class="ct">' + esc(c.title) + '</span>' +
    '<span class="cn">' + (c.message_count || 0) + '</span>' +
    '<span class="cd" onclick="event.stopPropagation();delCv(\'' + c.id + '\')">' + I.trash + '</span></div>'
  ).join('');
}

async function swCv(id) {
  cid = id; closeSb();
  const ml = document.getElementById('ml');
  ml.innerHTML = '<div class="msg-row system"><div class="msg-b">加载中...</div></div>';
  try {
    const r = await fetch(A + '/conversations/' + id, {
      headers: { 'Authorization': 'Bearer ' + T },
    });
    const d = await r.json();
    ml.innerHTML = '';
    (d.messages || []).filter(m => m.role !== 'system').forEach(m => ab(m.role, m.content));
    if (!d.messages?.length) ab('system', '开始聊天吧 ✨');
  } catch (e) { ab('system', '⚠ 加载失败'); }
  sd();
}

async function delCv(id) {
  if (!confirm('删除此对话？')) return;
  await fetch(A + '/conversations/' + id, {
    method: 'DELETE',
    headers: { 'Authorization': 'Bearer ' + T },
  });
  if (cid === id) { cid = null; newChat(); }
  renderSb();
}

function newChat() {
  cid = null; closeSb();
  document.getElementById('ml').innerHTML =
    '<div class="msg-row system"><div class="msg-b">✨ 新对话 — 开始和星媛聊天吧</div></div>';
}

// ═══════════════════════════════════════════
// 反馈 & 记忆
// ═══════════════════════════════════════════

function showFeedback() {
  hideFeedback();
  var el = document.createElement('div');
  el.className = 'feedback-bar';
  el.id = 'fbar';
  el.innerHTML = '<span>评价</span>' +
    '<button onclick="rate(5)">👍</button>' +
    '<button onclick="rate(3)">👌</button>' +
    '<button onclick="rate(1)">👎</button>';
  document.getElementById('ml').appendChild(el);
  sd();
}

function hideFeedback() {
  var el = document.getElementById('fbar');
  if (el) el.remove();
  el = document.getElementById('fbar');
  if (el) el.remove();
}

async function rate(v) {
  try {
    await fetch(A + '/iteration/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + T },
      body: JSON.stringify({ rating: v, conv_id: cid || '' }),
    });
    tt(v >= 4 ? '感谢好评 ❤️' : v >= 3 ? '谢谢 🙏' : '我会改进 💪');
  } catch (e) { /* 静默 */ }
}

async function showMem() {
  closeSb();
  try {
    const r = await fetch(A + '/iteration/memory', {
      headers: { 'Authorization': 'Bearer ' + T },
    });
    const d = await r.json();
    if (d.data && d.data.length > 0) {
      // 高频提问类直接展示 value（含问题与次数），其余展示 key: value
      alert('🧠 星媛的记忆 (' + d.total + '条):\n\n' +
        d.data.map(m => '• ' + (m.category === 'frequent_question' ? m.value : m.key + ': ' + m.value)).join('\n'));
    } else {
      alert('🧠 还没有记忆，多和星媛聊天吧～');
    }
  } catch (e) { tt('加载失败'); }
}

// ═══════════════════════════════════════════
// 聊天壁纸 — 用户自定义聊天背景（预设渐变 / 上传图片）
// ═══════════════════════════════════════════
const WPS = [
  { name: '默认',   css: '' },
  { name: '星河紫', css: 'radial-gradient(circle at 30% 20%, #6d28d9 0%, #1e1b4b 45%, #0a0a1a 80%)' },
  { name: '极光',   css: 'linear-gradient(135deg, #0ea5e9 0%, #6366f1 45%, #a855f7 75%, #1e1b4b 100%)' },
  { name: '落日',   css: 'linear-gradient(160deg, #1e1b4b 0%, #7c2d12 55%, #fb923c 100%)' },
  { name: '深海',   css: 'linear-gradient(180deg, #0f172a 0%, #1e3a8a 55%, #0891b2 100%)' },
  { name: '森林',   css: 'linear-gradient(160deg, #0a0f0a 0%, #14532d 55%, #4ade80 100%)' },
  { name: '樱粉',   css: 'linear-gradient(160deg, #1b0f1e 0%, #831843 55%, #f9a8d4 100%)' },
];
const WP_STORE = 'xy_bg';     // 值：''(默认) / 'preset:N' / 'img'
const WP_IMG = 'xy_bg_img';   // 上传图片 dataURL

async function getWpSetting() {
  const raw = await Store.get(WP_STORE);
  if (!raw) return { type: 'default' };
  if (raw.indexOf('preset:') === 0) return { type: 'preset', idx: parseInt(raw.slice(7), 10) || 0 };
  if (raw === 'img') return { type: 'img' };
  return { type: 'default' };
}

function wpBgCss(setting, imgData) {
  if (setting.type === 'preset') {
    const p = WPS[setting.idx];
    return p && p.css ? p.css : '';
  }
  if (setting.type === 'img' && imgData) return 'url("' + imgData + '") center/cover no-repeat';
  return '';
}

async function applyWp() {
  const cs = document.getElementById('chatScreen');
  if (!cs) return;
  const setting = await getWpSetting();
  const bg = setting.type === 'img'
    ? wpBgCss(setting, await Store.get(WP_IMG))
    : wpBgCss(setting);
  cs.style.background = bg;
  cs.classList.toggle('has-wp', !!bg);
}

function showWp() {
  closeSb();
  if (document.getElementById('wpm')) return;
  var ov = document.createElement('div');
  ov.id = 'wpm';
  ov.className = 'wp-overlay';
  ov.addEventListener('click', function (e) { if (e.target === ov) closeWp(); });
  var box = document.createElement('div');
  box.className = 'wp-box';
  box.innerHTML =
    '<div class="wp-title">聊天壁纸</div>' +
    '<div class="wp-sub">选择一个背景，或上传自己的图片</div>' +
    '<div class="wp-grid" id="wplist"></div>' +
    '<div style="display:flex;gap:10px;margin-top:14px">' +
    '<button class="btn-primary" style="flex:1" onclick="pickWpImg()">上传图片</button>' +
    '<button class="btn-ghost" style="flex:1" onclick="closeWp()">完成</button>' +
    '</div>';
  ov.appendChild(box);
  document.body.appendChild(ov);
  renderWpGrid();
}

async function renderWpGrid() {
  const grid = document.getElementById('wplist');
  if (!grid) return;
  const cur = await getWpSetting();
  const hasImg = cur.type === 'img';
  const onFor = function (i) {
    if (hasImg) return '';
    if (cur.type === 'preset') return i === cur.idx ? ' on' : '';
    return i === 0 ? ' on' : '';
  };
  grid.innerHTML = WPS.map(function (p, i) {
    const style = p.css ? 'style="background:' + p.css + '"' : '';
    return '<div class="wp-swatch' + onFor(i) + '" ' + style + ' onclick="setWp(' + i + ')">' +
      '<span>' + p.name + '</span></div>';
  }).join('') +
    '<div class="wp-swatch wp-upload' + (hasImg ? ' on' : '') + '" onclick="pickWpImg()">' +
    '<span>' + (hasImg ? '已上传' : '上传图片') + '</span></div>';
}

async function setWp(i) {
  await Store.set(WP_STORE, i === 0 ? '' : 'preset:' + i);
  if (i === 0) await Store.remove(WP_IMG);
  await applyWp();
  closeWp();
  tt(i === 0 ? '已恢复默认壁纸' : '已应用壁纸');
}

function pickWpImg() {
  var inp = document.getElementById('wpFile');
  if (!inp) {
    inp = document.createElement('input');
    inp.id = 'wpFile';
    inp.type = 'file';
    inp.accept = 'image/*';
    inp.style.display = 'none';
    inp.addEventListener('change', function () { if (inp.files && inp.files[0]) onWpFile(inp.files[0]); });
    document.body.appendChild(inp);
  }
  inp.click();
}

async function onWpFile(file) {
  if (file.size > 12 * 1024 * 1024) { tt('图片太大，请小于 12MB'); return; }
  try {
    const img = await loadImage(file);
    const dataUrl = compressImage(img, 1280, 0.78);
    await Store.set(WP_STORE, 'img');
    await Store.set(WP_IMG, dataUrl);
    await applyWp();
    closeWp();
    tt('已设置自定义壁纸');
  } catch (e) { tt('图片处理失败，请换一张'); }
}

function loadImage(file) {
  return new Promise(function (res, rej) {
    const fr = new FileReader();
    fr.onload = function () {
      const im = new Image();
      im.onload = function () { res(im); };
      im.onerror = rej;
      im.src = fr.result;
    };
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}

function compressImage(img, maxW, q) {
  let w = img.width, h = img.height;
  if (w > maxW) { h = Math.round(h * maxW / w); w = maxW; }
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  c.getContext('2d').drawImage(img, 0, 0, w, h);
  return c.toDataURL('image/jpeg', q);
}

// ═══════════════════════════════════════════
// 聊天图片 — 选择/压缩/预览/渲染
// ═══════════════════════════════════════════

// 渲染气泡内容：把 [图片]data:...[/图片] 标记解析为 <img>，其余文本 createTextNode 安全转义
function renderMsgBody(bEl, c) {
  const re = /\[图片\](.*?)\[\/图片\]/gs;
  let last = 0, m;
  while ((m = re.exec(c)) !== null) {
    if (m.index > last) bEl.appendChild(document.createTextNode(c.slice(last, m.index)));
    const uri = m[1];
    if (/^data:image\/(?:jpeg|png|webp|gif);base64,/.test(uri)) {
      const img = document.createElement('img');
      img.className = 'msg-img';
      img.src = uri;
      img.alt = '[图片]';
      bEl.appendChild(img);
    } else {
      bEl.appendChild(document.createTextNode('[图片]' + uri + '[/图片]'));
    }
    last = m.index + m[0].length;
  }
  if (last < c.length) bEl.appendChild(document.createTextNode(c.slice(last)));
  if (!bEl.hasChildNodes()) bEl.appendChild(document.createTextNode(c));
}

// 上屏用存储形态：text + 每张图一个 [图片] 标记（与后端持久化 B 视图同构）
function renderContentWithImages(text, imgs) {
  return text + (imgs || []).map(function (u) { return '[图片]' + u + '[/图片]'; }).join('');
}

function showImgMenu() { document.getElementById('imgMenu').classList.add('show'); }
function hideImgMenu() { document.getElementById('imgMenu').classList.remove('show'); }
function pickImgCam() { hideImgMenu(); getImgInput('cam').click(); }
function pickImgGal() { hideImgMenu(); getImgInput('gal').click(); }

// 惰性创建 file input（复用 pickWpImg 模式）：相机 capture=environment，相册 multiple 多选
function getImgInput(kind) {
  const id = kind === 'cam' ? 'imgCam' : 'imgGal';
  let inp = document.getElementById(id);
  if (!inp) {
    inp = document.createElement('input');
    inp.id = id;
    inp.type = 'file';
    inp.accept = 'image/*';
    inp.style.display = 'none';
    if (kind === 'cam') inp.setAttribute('capture', 'environment');
    else inp.setAttribute('multiple', '');
    inp.addEventListener('change', function () {
      if (inp.files && inp.files.length) onImgFiles(Array.from(inp.files));
      inp.value = '';   // 允许连续选择同一文件
    });
    document.body.appendChild(inp);
  }
  return inp;
}

async function onImgFiles(files) {
  for (const f of files) {
    if (_picked.length >= 9) { tt('最多发送 9 张图片'); break; }
    if (f.size > 12 * 1024 * 1024) { tt('图片太大，请小于 12MB'); continue; }
    try {
      const img = await loadImage(f);
      _picked.push({ src: compressImage(img, 1280, 0.78) });
    } catch (e) { /* 坏图跳过 */ }
  }
  renderImgTray();
}

function renderImgTray() {
  const tray = document.getElementById('itray');
  tray.innerHTML = '';
  tray.style.display = _picked.length ? 'flex' : 'none';
  _picked.forEach(function (p, i) {
    const d = document.createElement('div');
    d.className = 'img-t';
    d.innerHTML = '<img src="' + p.src + '" alt=""/>' +
      '<button class="img-del" onclick="delImg(' + i + ')">' + I.close + '</button>';
    tray.appendChild(d);
  });
}

function delImg(i) { _picked.splice(i, 1); renderImgTray(); }
function clearTray() { _picked = []; renderImgTray(); }

function closeWp() {
  const ov = document.getElementById('wpm');
  if (ov) ov.remove();
}

// ═══════════════════════════════════════════
// 个人资料 — 昵称 / 头像 / 密码设置
// ═══════════════════════════════════════════
var _pfAvatar = '';   // 本次会话尚未保存的新头像 dataURL

function showProfile() {
  closeSb();
  if (document.getElementById('pfm')) return;
  var ov = document.createElement('div');
  ov.id = 'pfm';
  ov.className = 'wp-overlay';
  ov.addEventListener('click', function (e) { if (e.target === ov) closeProfile(); });
  var box = document.createElement('div');
  box.className = 'wp-box';
  box.innerHTML =
    '<div class="wp-title">个人资料</div>' +
    '<div class="pf-av" onclick="pickAvatar()" title="点击更换头像">' + avatarPreviewHtml() +
    '<span class="pf-av-tip">点击更换头像</span></div>' +
    '<label class="pf-label">昵称</label>' +
    '<input class="pf-input" id="pfNick" maxlength="30" placeholder="给自己取个名字"/>' +
    '<div style="display:flex;gap:10px;margin-top:12px">' +
    '<button class="btn-primary" style="flex:1" onclick="saveProfile()">保存资料</button>' +
    '<button class="btn-ghost" style="flex:1" onclick="closeProfile()">完成</button>' +
    '</div>' +
    '<div class="pf-div">修改登录密码</div>' +
    '<label class="pf-label">当前密码</label>' +
    '<input class="pf-input" id="pfOld" type="password" placeholder="当前密码"/>' +
    '<label class="pf-label">新密码</label>' +
    '<input class="pf-input" id="pfNew" type="password" placeholder="至少8位，含字母和数字"/>' +
    '<label class="pf-label">确认新密码</label>' +
    '<input class="pf-input" id="pfNew2" type="password" placeholder="再次输入"/>' +
    '<button class="btn-primary" style="margin-top:12px" onclick="savePwd()">更新密码</button>';
  ov.appendChild(box);
  document.body.appendChild(ov);
  document.getElementById('pfNick').value = (U && U.nickname) || '';
}

function avatarPreviewHtml() {
  var av = U && U.avatar ? U.avatar : '';
  return av
    ? '<img class="pf-av-img" src="' + av + '" alt="头像"/>'
    : I.user;
}

function pickAvatar() {
  var inp = document.getElementById('pfFile');
  if (!inp) {
    inp = document.createElement('input');
    inp.id = 'pfFile';
    inp.type = 'file';
    inp.accept = 'image/*';
    inp.style.display = 'none';
    inp.addEventListener('change', function () { if (inp.files && inp.files[0]) onAvatarFile(inp.files[0]); });
    document.body.appendChild(inp);
  }
  inp.click();
}

async function onAvatarFile(file) {
  if (file.size > 12 * 1024 * 1024) { tt('图片太大，请小于 12MB'); return; }
  try {
    var img = await loadImage(file);
    var dataUrl = compressAvatar(img);
    var av = document.getElementById('pfm').querySelector('.pf-av');
    if (av) {
      av.innerHTML = '<img class="pf-av-img" src="' + dataUrl + '" alt="头像"/>' +
        '<span class="pf-av-tip">点击更换头像</span>';
    }
    _pfAvatar = dataUrl;
    tt('头像已选择，点"保存资料"生效');
  } catch (e) { tt('图片处理失败，请换一张'); }
}

function compressAvatar(img) {
  var size = 128;
  var s = Math.min(img.width, img.height);
  var c = document.createElement('canvas');
  c.width = size; c.height = size;
  c.getContext('2d').drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
  return c.toDataURL('image/jpeg', 0.82);
}

async function saveProfile() {
  var nick = document.getElementById('pfNick').value.trim();
  if (!nick) { tt('昵称不能为空'); return; }
  var body = { nickname: nick };
  if (_pfAvatar) body.avatar = _pfAvatar;
  try {
    var r = await fetch(A + '/auth/me', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + T },
      body: JSON.stringify(body),
    });
    var d = await r.json();
    if (!r.ok) throw new Error(d.detail || '保存失败');
    U.nickname = d.data.nickname;
    U.avatar = d.data.avatar;
    await Store.setJSON('xyu', U);
    document.getElementById('ul').textContent = U.nickname;
    _pfAvatar = '';
    tt('资料已保存 ✨');
    closeProfile();
  } catch (e) { tt('❌ ' + e.message); }
}

async function savePwd() {
  var oldp = document.getElementById('pfOld').value;
  var np = document.getElementById('pfNew').value;
  var np2 = document.getElementById('pfNew2').value;
  if (!oldp) { tt('请输入当前密码'); return; }
  if (np.length < 8) { tt('新密码至少需要 8 位'); return; }
  if (!/[a-zA-Z]/.test(np)) { tt('新密码需要包含至少一个字母'); return; }
  if (!/\d/.test(np)) { tt('新密码需要包含至少一个数字'); return; }
  if (np !== np2) { tt('两次输入的新密码不一致'); return; }
  try {
    var r = await fetch(A + '/auth/me/password', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + T },
      body: JSON.stringify({ old_password: oldp, new_password: np }),
    });
    var d = await r.json();
    if (!r.ok) throw new Error(d.detail || '修改失败');
    document.getElementById('pfOld').value = '';
    document.getElementById('pfNew').value = '';
    document.getElementById('pfNew2').value = '';
    tt('密码已更新，下次登录请使用新密码');
  } catch (e) { tt('❌ ' + e.message); }
}

function closeProfile() {
  const ov = document.getElementById('pfm');
  if (ov) ov.remove();
  _pfAvatar = '';
}

// ═══════════════════════════════════════════
// 进入聊天 + 初始化
// ═══════════════════════════════════════════
function enterChat() {
  document.getElementById('ul').textContent = U.nickname;
  ss('chatScreen');
  applyWp();
  loadCvs();
}

async function init() {
  // ── 0. 立即检查是否有已保存 token ──
  T = await Store.get('xyt');
  U = await Store.getJSON('xyu');
  var hasSavedToken = !!(T && U);

  var isPWA = window.location.protocol.startsWith('http') && !window.Capacitor;

  // ── 1. 寻址 ──
  //    PWA：前后端同域，直接用相对路径，跳过引导（省掉每次打开的额外网络等待）
  //    Capacitor/App：缓存优先 → 多源引导 → 兜底
  if (isPWA) {
    A = '';
  } else {
    for (var attempt = 0; attempt < 3; attempt++) {
      A = await Store.get('xy_api');
      if (A) {
        try {
          var _r = await fetch(A + '/health', { signal: AbortSignal.timeout(CONFIG.healthTimeout) });
          var _d = await _r.json();
          if (_d.status === 'ok') break;
        } catch (e) { A = ''; }
      }
      if (A) break;

      // 多源拉取
      var urlList = [];
      for (var si = 0; si < CONFIG.bootstrapUrls.length; si++) {
        try {
          var sr = await fetch(CONFIG.bootstrapUrls[si], { signal: AbortSignal.timeout(CONFIG.bootstrapTimeout) });
          var st = (await sr.text()).trim();
          urlList = st.split('\n').map(function(s) { return s.trim(); }).filter(function(s) { return s.startsWith('http'); });
          if (urlList.length > 0) break;
        } catch (e) { continue; }
      }
      if (urlList.length === 0 && CONFIG.fallbackLan) urlList = [CONFIG.fallbackLan];

      for (var ui = 0; ui < urlList.length; ui++) {
        try {
          var ur = await fetch(urlList[ui] + '/health', { signal: AbortSignal.timeout(CONFIG.healthTimeout) });
          var ud = await ur.json();
          if (ud.status === 'ok') { A = urlList[ui]; await Store.set('xy_api', A); break; }
        } catch (e) { continue; }
      }
      if (A) break;
      if (attempt < 2) await new Promise(function(r) { setTimeout(r, CONFIG.retryDelay); });
    }
  }

  // ── 1.5 新版本检测（不阻塞，后台探测）──
  checkUpdate();

  // ── 2. 恢复会话 ──
  //    有本地 token：立即进聊天（不阻塞等待网络），后台再校验 token 有效性
  if (hasSavedToken) {
    enterChat();
    if (isPWA || A) {
      validateTokenBackground(isPWA ? '' : A);
    }
    return;
  }

  // ── 3. 没有有效 token → 停留登录页 ──
  if (!isPWA && !A) {
    document.getElementById('authScreen').innerHTML =
      '<div style="text-align:center;padding:40px"><p>⚠️ 无法连接到服务器</p><p style="font-size:12px;color:var(--text3)">请检查网络后重试</p><button class="btn-primary" onclick="location.reload()" style="margin-top:16px">重试</button></div>';
  }
}

// 后台校验 token：6s 超时，401 则清除会话回到登录页，网络波动则保留本地会话
async function validateTokenBackground(base) {
  try {
    var mr = await fetch(base + '/auth/me', {
      headers: { 'Authorization': 'Bearer ' + T },
      signal: AbortSignal.timeout(6000),
    });
    if (mr.status === 401) {
      T = ''; U = null; cid = null; convs = [];
      await Store.remove('xyt');
      await Store.remove('xyu');
      ss('authScreen');
      tt('登录已过期，请重新登录');
      return;
    }
    if (mr.ok) {
      var d = await mr.json();
      U = d.data;
      await Store.setJSON('xyu', U);
      document.getElementById('ul').textContent = U.nickname;
    }
  } catch (e) { /* 网络波动：保留本地会话，下次再校验 */ }
}

// ═══════════════════════════════════════════
// 新版本更新提示
// 部署新版本后，用户打开 App 显示"发现新版本"提示条，点击才刷新，不打断对话。
// ⚠ 发版时必须同步递增三处版本号：
//   main.py create_app(version=...) 、static/routers/health.py 返回的 version 、下方 APP_VERSION
// ═══════════════════════════════════════════
const APP_VERSION = '2.8.0';

var _dismissedVer = '';
try { _dismissedVer = localStorage.getItem('xy_uver') || ''; } catch (e) { /* 隐私模式等 */ }

async function _fetchHealthVersion(base) {
  try {
    var r = await fetch(base + '/health', { signal: AbortSignal.timeout(CONFIG.healthTimeout) });
    var d = await r.json();
    return (d && d.version) ? String(d.version) : '';
  } catch (e) { return ''; }
}

async function checkUpdate() {
  if (document.visibilityState === 'hidden') return;
  var ver = await _fetchHealthVersion(A);
  if (!ver || ver === APP_VERSION) return;
  if (_dismissedVer === ver) return;          // 用户已忽略该版本
  if (document.getElementById('uv')) return;  // 已在显示
  showUpdateBanner(ver);
}

function showUpdateBanner(ver) {
  var b = document.createElement('div');
  b.id = 'uv';
  b.setAttribute('data-ver', ver);
  b.style.cssText = [
    'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:9999',
    'display:flex', 'align-items:center', 'justify-content:center',
    'gap:10px', 'padding:9px 46px',
    'background:linear-gradient(90deg,#6d5dfc,#9a5dfc)',
    'color:#fff', 'font-size:13px', 'line-height:1.5',
    'box-shadow:0 2px 12px rgba(0,0,0,.25)',
  ].join(';');
  b.innerHTML =
    '<span style="display:flex;align-items:center;gap:6px">' + I.star +
    '发现新版本 v' + esc(ver) + '</span>' +
    '<button onclick="forceRefresh()" style="background:#fff;color:#6d5dfc;border:none;border-radius:14px;padding:4px 14px;font-size:12px;font-weight:600;cursor:pointer">点击更新</button>' +
    '<button onclick="dismissUpdate()" title="忽略" style="position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;color:#fff;cursor:pointer;padding:6px;display:flex">' + I.close + '</button>';
  document.body.appendChild(b);
}

function dismissUpdate() {
  var el = document.getElementById('uv');
  if (el) el.remove();
  var ver = el ? el.getAttribute('data-ver') : '';
  if (ver) {
    _dismissedVer = ver;
    try { localStorage.setItem('xy_uver', ver); } catch (e) {}
  }
}

async function forceRefresh() {
  // 先清 SW 旧缓存，保证刷新后拿到最新资源
  try {
    var keys = await caches.keys();
    await Promise.all(keys.map(function (k) { return caches.delete(k); }));
  } catch (e) { /* 无缓存或失败，直接刷新 */ }
  location.reload();
}

// 触发时机：初始化寻址完成后、切回前台、以及每 5 分钟
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'visible') checkUpdate();
});
setInterval(checkUpdate, 5 * 60 * 1000);

document.addEventListener('DOMContentLoaded', init);
