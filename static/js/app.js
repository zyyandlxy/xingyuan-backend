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
  // 星标 — Logo / 助手头像
  star: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 2l2.4 7.2h7.6l-6 4.8 2.4 7.2-6.4-4.8-6.4 4.8 2.4-7.2-6-4.8h7.6z"/></svg>',
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
    U = { id: d.data.id, username: d.data.username, nickname: d.data.nickname };
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
    U = { id: d.data.id, username: d.data.username, nickname: d.data.nickname };
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
  const avHtml = r === 'system' ? '' : '<div class="msg-av">' + icon + '</div>';
  let h = avHtml + '<div class="msg-b">' + htm(c) + '</div>';
  if (retryCb && r === 'system') {
    h += '<div class="msg-actions"><button class="retry-btn">🔄 重试</button></div>';
  }
  el.innerHTML = h;
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

async function send(retryText) {
  if (busy) { stop(); return; }
  hideFeedback();
  const inp = document.getElementById('inp');
  const t = retryText || inp.value.trim();
  if (!t) return;
  if (!retryText) {
    inp.value = ''; inp.style.height = 'auto';
    ab('user', t);
  }
  at();
  const btn = document.getElementById('sbtn');
  btn.innerHTML = I.stop;
  btn.classList.add('stop');
  busy = true;
  await stream(t);
  btn.innerHTML = I.send;
  btn.classList.remove('stop');
  busy = false;
}

function stop() { if (ac) { ac.abort(); ac = null; } }

async function stream(text) {
  ac = new AbortController();
  let b = null, full = '';
  try {
    const r = await fetch(A + '/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + T },
      body: JSON.stringify({
        messages: [{ role: 'user', content: text }],
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
      ab('system', '⚠ ' + detail, () => send(text));
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
            if (!b) { rt(); b = ab('system', '', () => send(text)); }
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
      ab('system', '⚠ ' + (e.message || '网络请求失败'), () => send(text));
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
      alert('🧠 星媛的记忆 (' + d.total + '条):\n\n' +
        d.data.map(m => '• ' + m.key + ': ' + m.value).join('\n'));
    } else {
      alert('🧠 还没有记忆，多和星媛聊天吧～');
    }
  } catch (e) { tt('加载失败'); }
}

// ═══════════════════════════════════════════
// 进入聊天 + 初始化
// ═══════════════════════════════════════════
function enterChat() {
  document.getElementById('ul').textContent = U.nickname;
  ss('chatScreen');
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

document.addEventListener('DOMContentLoaded', init);
