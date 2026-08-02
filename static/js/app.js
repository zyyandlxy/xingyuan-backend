// ═══════════════════════════════════════════
// GLM Agent PWA — 应用脚本 (v2.0)
// 纯前端聊天客户端，无需额外认证
// ═══════════════════════════════════════════

// ═══════════════════════════════════════════
// SVG 图标
// ═══════════════════════════════════════════
const I = {
  star: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 2l2.4 7.2h7.6l-6 4.8 2.4 7.2-6.4-4.8-6.4 4.8 2.4-7.2-6-4.8h7.6z"/></svg>',
  user: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 4-7 8-7s8 3 8 7"/></svg>',
  send: '<svg class="icon" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9"/></svg>',
  stop: '<svg class="icon" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>',
  menu: '<svg class="icon" viewBox="0 0 24 24"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>',
  close: '<svg class="icon" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
  trash: '<svg class="icon" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
  plus: '<svg class="icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
  chat: '<svg class="icon" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
};

// ═══════════════════════════════════════════
// State
// ═══════════════════════════════════════════
const API = '/chat';
let convId = null;
let streaming = false;
let abortCtrl = null;

// ═══════════════════════════════════════════
// UI Utils
// ═══════════════════════════════════════════
function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (isError ? 'error' : '') + ' show';
  clearTimeout(t._tid);
  t._tid = setTimeout(function() { t.classList.remove('show'); }, 2500);
}

function scrollBottom() {
  var el = document.getElementById('messages');
  requestAnimationFrame(function() { el.scrollTop = el.scrollHeight; });
}

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ═══════════════════════════════════════════
// Sidebar
// ═══════════════════════════════════════════
function toggleSidebar() {
  var sb = document.getElementById('sidebar');
  var ov = document.getElementById('overlay');
  var open = !sb.classList.contains('open');
  sb.classList.toggle('open', open);
  ov.classList.toggle('show', open);
  if (open) loadConversations();
}

function loadConversations() {
  fetch('/conversations?page_size=50')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var list = document.getElementById('sidebarList');
      var html = data.items.map(function(c) {
        return '<div class="sidebar-item' + (c.id === convId ? ' active' : '') +
          '" onclick="switchConv(\'' + c.id + '\')">' +
          '<span class="title">' + esc(c.title) + '</span>' +
          '<span class="count">' + (c.message_count || 0) + '</span>' +
          '<span class="del" onclick="event.stopPropagation();delConv(\'' + c.id + '\')">' + I.trash + '</span></div>';
      }).join('');
      list.innerHTML = html || '<div style="padding:16px;color:var(--text3);text-align:center">暂无对话</div>';
    })
    .catch(function() { toast('加载对话列表失败', true); });
}

function switchConv(id) {
  convId = id;
  toggleSidebar();
  var msgs = document.getElementById('messages');
  msgs.innerHTML = '<div class="msg system"><div class="msg-bubble">加载中...</div></div>';

  fetch('/conversations/' + id)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      msgs.innerHTML = '';
      d.messages.filter(function(m) { return m.role !== 'system'; }).forEach(function(m) {
        addMsg(m.role, m.content);
      });
      if (!d.messages.length) addMsg('system', '空对话，开始聊天吧～');
    })
    .catch(function() { addMsg('system', '⚠️ 加载失败'); });
  scrollBottom();
}

function delConv(id) {
  if (!confirm('确定删除此对话？')) return;
  fetch('/conversations/' + id, { method: 'DELETE' }).then(function() {
    if (convId === id) { convId = null; newChat(); }
    loadConversations();
  });
}

function newChat() {
  convId = null;
  document.getElementById('messages').innerHTML =
    '<div class="msg system"><div class="msg-bubble">' + I.star + ' 开始新对话吧～</div></div>';
  toggleSidebar();
}

// ═══════════════════════════════════════════
// Messages
// ═══════════════════════════════════════════
function addMsg(role, content) {
  var el = document.createElement('div');
  el.className = 'msg ' + role;
  var avatarHtml = '';
  if (role === 'user') {
    avatarHtml = '<div class="msg-avatar">' + I.user + '</div>';
  } else if (role === 'assistant') {
    avatarHtml = '<div class="msg-avatar">' + I.star + '</div>';
  } else {
    avatarHtml = '';
  }
  el.innerHTML = avatarHtml + '<div class="msg-bubble">' + escapeHtml(content) + '</div>';
  document.getElementById('messages').appendChild(el);
  scrollBottom();
  return el;
}

function addStreamBubble() {
  var el = document.createElement('div');
  el.className = 'msg assistant';
  el.id = 'streamMsg';
  el.innerHTML = '<div class="msg-avatar">' + I.star + '</div><div class="msg-bubble"></div>';
  document.getElementById('messages').appendChild(el);
  return el.querySelector('.msg-bubble');
}

function addTyping() {
  var el = document.createElement('div');
  el.className = 'msg assistant msg-typing';
  el.id = 'typing';
  el.innerHTML = '<div class="msg-avatar">' + I.star + '</div><div class="msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>';
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function removeTyping() {
  var el = document.getElementById('typing');
  if (el) el.remove();
}

// ═══════════════════════════════════════════
// Send / Stream
// ═══════════════════════════════════════════
function onKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
}

function autoResize() {
  var ta = document.getElementById('input');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
}

function send() {
  if (streaming) { stopStream(); return; }

  var input = document.getElementById('input');
  var text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';

  addMsg('user', text);
  addTyping();

  var btn = document.getElementById('sendBtn');
  btn.innerHTML = I.stop;
  btn.classList.add('stop');

  streamChat(text);
}

function streamChat(text) {
  streaming = true;
  abortCtrl = new AbortController();
  var bubble = addStreamBubble();
  removeTyping();

  var body = { messages: [{ role: 'user', content: text }], stream: true };
  if (convId) body.conversation_id = convId;

  fetch(API + '/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: abortCtrl.signal,
  })
    .then(function(r) { return r.body.getReader(); })
    .then(function(reader) {
      var decoder = new TextDecoder();
      var buf = '';

      function pump() {
        return reader.read().then(function(_a) {
          var done = _a.done, value = _a.value;
          if (done) {
            if (!bubble.textContent) bubble.textContent = '(空回复)';
            finish();
            return;
          }
          buf += decoder.decode(value, { stream: true });
          var lines = buf.split('\n');
          buf = lines.pop() || '';

          var eventName = null;
          for (var _i = 0, lines_1 = lines; _i < lines_1.length; _i++) {
            var line = lines_1[_i].replace(/\r$/, '');
            if (line.startsWith('event:')) {
              eventName = line.slice(6).trim();
              continue;
            }
            if (!line.startsWith('data:')) continue;
            var data = line.slice(5).trim();
            if (!data || data === '[DONE]') continue;

            try {
              var parsed = JSON.parse(data);
              if (eventName === 'done') {
                if (parsed.conversation_id) convId = parsed.conversation_id;
              } else if (eventName === 'error') {
                bubble.textContent = '⚠️ ' + (parsed.error || '未知错误');
              } else if (eventName === 'delta' && parsed.delta) {
                bubble.textContent += parsed.delta;
                scrollBottom();
              }
            } catch (e) { /* skip parse errors */ }
          }
          return pump();
        });
      }
      return pump();
    })
    .catch(function(e) {
      if (e.name !== 'AbortError') {
        bubble.textContent = '⚠️ 请求失败: ' + e.message;
        toast('发送失败，请重试', true);
      }
      finish();
    });

  function finish() {
    streaming = false;
    var btn = document.getElementById('sendBtn');
    btn.innerHTML = I.send;
    btn.classList.remove('stop');
    abortCtrl = null;
  }
}

function stopStream() {
  if (abortCtrl) abortCtrl.abort();
}

// ═══════════════════════════════════════════
// PWA Service Worker
// ═══════════════════════════════════════════
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/sw.js').catch(function() {});
  });
}
