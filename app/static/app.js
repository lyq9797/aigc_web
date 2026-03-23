const appState = {
  token: localStorage.getItem('aigc_token') || '',
  username: localStorage.getItem('aigc_user') || '',
};

const nodes = {
  pageLogin: document.getElementById('loginPanel'),
  pageRegister: document.getElementById('registerPanel'),
  loginUsername: document.getElementById('loginUsername'),
  loginPassword: document.getElementById('loginPassword'),
  registerUsername: document.getElementById('registerUsername'),
  registerPassword: document.getElementById('registerPassword'),
  registerConfirm: document.getElementById('registerConfirmPassword'),
  authMsg: document.getElementById('authMsg'),
  detectBtn: document.getElementById('detectBtn'),
  inputText: document.getElementById('inputText'),
  detectMsg: document.getElementById('detectMsg'),
  wordHighlight: document.getElementById('wordHighlight'),
  sentenceList: document.getElementById('sentenceList'),
  historyList: document.getElementById('historyList'),
};

function updateCurrentUser() {
  const currentUser = document.getElementById('currentUser');
  if (currentUser) {
    currentUser.textContent = appState.token ? `当前用户: ${appState.username}` : '未登录';
  }
}

function persistToken(token, username) {
  appState.token = token;
  appState.username = username;
  localStorage.setItem('aigc_token', token);
  localStorage.setItem('aigc_user', username);
  updateCurrentUser();
}

function dropToken() {
  appState.token = '';
  appState.username = '';
  localStorage.removeItem('aigc_token');
  localStorage.removeItem('aigc_user');
  updateCurrentUser();
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function request(path, method = 'GET', body = null, secure = false) {
  const headers = {};
  if (secure) {
    if (!appState.token) {
      throw new Error('请先登录');
    }
    headers.Authorization = `Bearer ${appState.token}`;
  }
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, {
    method,
    headers,
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : null,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || '请求失败');
  }
  return data;
}

function switchAuthTab(type) {
  const isLogin = type === 'login';
  nodes.pageLogin?.classList.toggle('hidden', !isLogin);
  nodes.pageRegister?.classList.toggle('hidden', isLogin);
}

async function signIn() {
  try {
    nodes.authMsg.textContent = '正在登录...';
    const username = nodes.loginUsername.value.trim();
    const password = nodes.loginPassword.value;
    const result = await request('/api/login', 'POST', { username, password }, false);
    persistToken(result.token, result.username);
    nodes.authMsg.textContent = '登录成功';
    return loadHistory();
  } catch (err) {
    nodes.authMsg.textContent = err.message;
  }
}

async function signUp() {
  try {
    nodes.authMsg.textContent = '正在注册...';
    const username = nodes.registerUsername.value.trim();
    const password = nodes.registerPassword.value;
    const confirm = nodes.registerConfirm.value;
    if (!username || !password || !confirm) {
      throw new Error('请填写完整信息');
    }
    if (password !== confirm) {
      throw new Error('两次密码不一致');
    }
    await request('/api/register', 'POST', { username, password }, false);
    nodes.authMsg.textContent = '注册成功，请登录';
    switchAuthTab('login');
  } catch (err) {
    nodes.authMsg.textContent = err.message;
  }
}

function renderJieGuo(words) {
  if (!nodes.wordHighlight) return;
  if (!Array.isArray(words) || words.length === 0) {
    nodes.wordHighlight.textContent = '暂无结果';
    return;
  }
  nodes.wordHighlight.innerHTML = words
    .map((item) => `<span class="word ${item.label_id === 1 ? 'aigt' : 'hwt'}" title="${escapeHtml(item.label)}">${escapeHtml(item.token)}</span>`)
    .join(' ');
}

function renderSentenceList(sentences) {
  if (!nodes.sentenceList) return;
  if (!Array.isArray(sentences) || sentences.length === 0) {
    nodes.sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  nodes.sentenceList.innerHTML = sentences.map((item) => `
    <div class="sentence-item ${item.label === 'AIGT' ? 'aigt' : 'hwt'}">
      <div><strong>句子 ${item.index + 1}</strong> | ${escapeHtml(item.label)}</div>
      <div>${escapeHtml(item.text)}</div>
    </div>
  `).join('');
}

async function detectText() {
  try {
    nodes.detectMsg.textContent = '检测中...';
    const text = nodes.inputText.value.trim();
    if (!text) {
      throw new Error('请输入文本后再检测');
    }
    const data = await request('/api/detect', 'POST', { text }, true);
    renderJieGuo(data.result.words || []);
    renderSentenceList(data.result.sentences || []);
    nodes.detectMsg.textContent = '检测完成';
    await loadHistory();
  } catch (err) {
    nodes.detectMsg.textContent = err.message;
  }
}

async function loadHistory() {
  if (!appState.token) {
    nodes.historyList.innerHTML = '<div class="muted">请先登录</div>';
    return;
  }
  try {
    const rows = await request('/api/history', 'GET', null, true);
    nodes.historyList.innerHTML = rows.map((item) => `
      <div class="history-item">
        <div>${escapeHtml(item.created_at)}</div>
        <div>${escapeHtml((item.input_text || '').slice(0, 80))}</div>
      </div>
    `).join('');
  } catch (err) {
    nodes.historyList.innerHTML = `<div class="muted">加载失败：${escapeHtml(err.message)}</div>`;
  }
}

function init() {
  updateCurrentUser();
  switchAuthTab('login');
  document.getElementById('tabLogin')?.addEventListener('click', () => switchAuthTab('login'));
  document.getElementById('tabRegister')?.addEventListener('click', () => switchAuthTab('register'));
  nodes.loginBtn?.addEventListener('click', signIn);
  nodes.registerBtn?.addEventListener('click', signUp);
  nodes.detectBtn?.addEventListener('click', detectText);
  if (appState.token) {
    loadHistory();
  }
}

init();
