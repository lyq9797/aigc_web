const state = {
  token: localStorage.getItem('aigc_token') || '',
  username: localStorage.getItem('aigc_user') || '',
};

const el = {
  tabLogin: document.getElementById('tabLogin'),
  tabRegister: document.getElementById('tabRegister'),
  loginPanel: document.getElementById('loginPanel'),
  registerPanel: document.getElementById('registerPanel'),
  authMsg: document.getElementById('authMsg'),
  loginUsername: document.getElementById('loginUsername'),
  loginPassword: document.getElementById('loginPassword'),
  registerUsername: document.getElementById('registerUsername'),
  registerPassword: document.getElementById('registerPassword'),
  loginBtn: document.getElementById('loginBtn'),
  registerBtn: document.getElementById('registerBtn'),
  logoutBtn: document.getElementById('logoutBtn'),
  currentUser: document.getElementById('currentUser'),
  inputText: document.getElementById('inputText'),
  sampleBtn: document.getElementById('sampleBtn'),
  clearBtn: document.getElementById('clearBtn'),
  detectBtn: document.getElementById('detectBtn'),
  detectMsg: document.getElementById('detectMsg'),
  wordHighlight: document.getElementById('wordHighlight'),
  sentenceList: document.getElementById('sentenceList'),
  switchInfo: document.getElementById('switchInfo'),
  refreshHistoryBtn: document.getElementById('refreshHistoryBtn'),
  historyList: document.getElementById('historyList'),
};

function setAuthState() {
  el.currentUser.textContent = state.token ? `当前用户: ${state.username}` : '未登录';
}

function showAuthTab(mode) {
  const isLogin = mode === 'login';
  el.loginPanel.classList.toggle('hidden', !isLogin);
  el.registerPanel.classList.toggle('hidden', isLogin);
  el.tabLogin.classList.toggle('active', isLogin);
  el.tabRegister.classList.toggle('active', !isLogin);
}

async function api(path, method = 'GET', body = null, needAuth = false) {
  const headers = { 'Content-Type': 'application/json' };
  if (needAuth) {
    if (!state.token) throw new Error('请先登录');
    headers.Authorization = `Bearer ${state.token}`;
  }

  const resp = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || '请求失败');
  }
  return data;
}

function saveAuth(token, username) {
  state.token = token;
  state.username = username;
  localStorage.setItem('aigc_token', token);
  localStorage.setItem('aigc_user', username);
  setAuthState();
}

function clearAuth() {
  state.token = '';
  state.username = '';
  localStorage.removeItem('aigc_token');
  localStorage.removeItem('aigc_user');
  setAuthState();
}

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderWordHighlight(words) {
  if (!words || !words.length) {
    el.wordHighlight.textContent = '暂无结果';
    return;
  }

  const html = words.map((w) => {
    const cls = w.label_id === 1 ? 'aigt' : 'hwt';
    const title = `${w.label} | 置信度 ${w.confidence}`;
    return `<span class="word ${cls}" title="${title}">${escapeHtml(w.token)}</span>`;
  }).join(' ');

  el.wordHighlight.innerHTML = html;
}

function renderSentences(sentences) {
  if (!sentences || !sentences.length) {
    el.sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }

  el.sentenceList.innerHTML = sentences.map((s) => {
    const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
    return `
      <div class="sentence-item ${cls}">
        <div><strong>句子 ${s.index + 1}</strong> | 标签: ${s.label} | 置信度: ${s.confidence}</div>
        <div>${escapeHtml(s.text)}</div>
      </div>
    `;
  }).join('');
}

function renderSwitch(summary) {
  if (!summary) {
    el.switchInfo.textContent = '切换点：暂无';
    return;
  }

  const wordPos = Number(summary.switch_word_index || 0) + 1;
  const sentPos = Number(summary.switch_sentence_index || 0) + 1;
  el.switchInfo.textContent = `检测到的切换点位于第 ${wordPos} 个词 / 第 ${sentPos} 个句子`;
}

async function doRegister() {
  try {
    const username = el.registerUsername.value.trim();
    const password = el.registerPassword.value;
    const res = await api('/api/register', 'POST', { username, password }, false);
    saveAuth(res.token, res.username);
    el.authMsg.style.color = '#0a7f6f';
    el.authMsg.textContent = '注册成功，已自动登录';
    await loadHistory();
  } catch (err) {
    el.authMsg.style.color = '#b13f00';
    el.authMsg.textContent = err.message;
  }
}

async function doLogin() {
  try {
    const username = el.loginUsername.value.trim();
    const password = el.loginPassword.value;
    const res = await api('/api/login', 'POST', { username, password }, false);
    saveAuth(res.token, res.username);
    el.authMsg.style.color = '#0a7f6f';
    el.authMsg.textContent = '登录成功';
    await loadHistory();
  } catch (err) {
    el.authMsg.style.color = '#b13f00';
    el.authMsg.textContent = err.message;
  }
}

async function doDetect() {
  try {
    el.detectMsg.style.color = '#5f6c75';
    el.detectMsg.textContent = '检测中，请稍候...';
    const text = el.inputText.value.trim();
    const res = await api('/api/detect', 'POST', { text }, true);
    renderSwitch(res.result.summary);
    renderWordHighlight(res.result.words);
    renderSentences(res.result.sentences);
    el.detectMsg.style.color = '#0a7f6f';
    el.detectMsg.textContent = '检测完成';
    await loadHistory();
  } catch (err) {
    el.detectMsg.style.color = '#b13f00';
    el.detectMsg.textContent = err.message;
  }
}

async function loadHistory() {
  if (!state.token) {
    el.historyList.innerHTML = '<div class="muted">请先登录</div>';
    return;
  }

  try {
    const rows = await api('/api/history', 'GET', null, true);
    if (!rows.length) {
      el.historyList.innerHTML = '<div class="muted">暂无历史记录</div>';
      return;
    }

    el.historyList.innerHTML = rows.map((r) => {
      const summary = r.result.summary || {};
      const preview = (r.input_text || '').slice(0, 100);
      return `
        <div class="history-item">
          <div class="time">${escapeHtml(r.created_at)}</div>
          <div>切换词位: ${Number(summary.switch_word_index || 0) + 1} | 切换句位: ${Number(summary.switch_sentence_index || 0) + 1}</div>
          <div>${escapeHtml(preview)}${r.input_text.length > 100 ? '...' : ''}</div>
        </div>
      `;
    }).join('');
  } catch (err) {
    el.historyList.innerHTML = `<div class="muted">加载失败: ${escapeHtml(err.message)}</div>`;
  }
}

function bindEvents() {
  el.tabLogin.addEventListener('click', () => showAuthTab('login'));
  el.tabRegister.addEventListener('click', () => showAuthTab('register'));
  el.registerBtn.addEventListener('click', doRegister);
  el.loginBtn.addEventListener('click', doLogin);

  el.logoutBtn.addEventListener('click', () => {
    clearAuth();
    el.authMsg.textContent = '';
    el.detectMsg.textContent = '';
    el.historyList.innerHTML = '<div class="muted">请先登录</div>';
  });

  el.sampleBtn.addEventListener('click', () => {
    el.inputText.value = 'This is an interesting paper on how to handle reparameterization in VAEs when you have discrete variables. They propose a new architecture called Discrete Variational Autoencoders (DVAEs) which combines an undirected discrete component and a directed hierarchical continuous component. This allows them to learn both the class of objects in an image as well as their specific realization in pixels. They show that DVAEs outperform other state-of-the-art methods on several benchmark datasets.';
  });

  el.clearBtn.addEventListener('click', () => {
    el.inputText.value = '';
    el.wordHighlight.textContent = '暂无结果';
    el.sentenceList.innerHTML = '';
    el.switchInfo.textContent = '切换点：暂无';
    el.detectMsg.textContent = '';
  });

  el.detectBtn.addEventListener('click', doDetect);
  el.refreshHistoryBtn.addEventListener('click', loadHistory);
}

function init() {
  setAuthState();
  bindEvents();
  loadHistory();
}

init();
