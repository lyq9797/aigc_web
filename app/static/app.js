const App = {
  state: {
    token: localStorage.getItem('aigc_token') || '',
    username: localStorage.getItem('aigc_user') || '',
    historyRows: [],
  },
  nodes: {
    currentUser: document.getElementById('currentUser'),
    loginForm: document.getElementById('loginPanel'),
    registerForm: document.getElementById('registerPanel'),
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
  },
};

App.utils = {
  escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  async request(path, method = 'GET', body = null, requireAuth = false) {
    const headers = {};
    if (requireAuth) {
      if (!App.state.token) {
        throw new Error('请先登录');
      }
      headers.Authorization = `Bearer ${App.state.token}`;
    }
    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {
      method,
      headers,
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : null,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || '请求失败');
    }
    return payload;
  },
};

App.actions = {
  updateUserBadge() {
    if (!App.nodes.currentUser) return;
    App.nodes.currentUser.textContent = App.state.token ? `当前用户: ${App.state.username}` : '未登录';
  },

  saveSession(token, username) {
    App.state.token = token;
    App.state.username = username;
    localStorage.setItem('aigc_token', token);
    localStorage.setItem('aigc_user', username);
    App.actions.updateUserBadge();
  },

  clearSession() {
    App.state.token = '';
    App.state.username = '';
    localStorage.removeItem('aigc_token');
    localStorage.removeItem('aigc_user');
    App.actions.updateUserBadge();
  },

  toggleAuthPanel(type) {
    const isLogin = type === 'login';
    App.nodes.loginForm?.classList.toggle('hidden', !isLogin);
    App.nodes.registerForm?.classList.toggle('hidden', isLogin);
  },

  async login() {
    try {
      App.nodes.authMsg.textContent = '登录中...';
      const username = App.nodes.loginUsername.value.trim();
      const password = App.nodes.loginPassword.value;
      const result = await App.utils.request('/api/login', 'POST', { username, password }, false);
      App.actions.saveSession(result.token, result.username);
      App.nodes.authMsg.textContent = '登录成功';
      await App.actions.loadHistory();
    } catch (error) {
      App.nodes.authMsg.textContent = error.message;
    }
  },

  async register() {
    try {
      App.nodes.authMsg.textContent = '注册中...';
      const username = App.nodes.registerUsername.value.trim();
      const password = App.nodes.registerPassword.value;
      const confirm = App.nodes.registerConfirm.value;
      if (!username || !password || !confirm) {
        throw new Error('请填写完整信息');
      }
      if (password !== confirm) {
        throw new Error('两次密码输入不一致');
      }
      await App.utils.request('/api/register', 'POST', { username, password }, false);
      App.nodes.authMsg.textContent = '注册成功，请登录';
      App.actions.toggleAuthPanel('login');
    } catch (error) {
      App.nodes.authMsg.textContent = error.message;
    }
  },

  renderResults(words, sentences) {
    if (App.nodes.wordHighlight) {
      App.nodes.wordHighlight.innerHTML = Array.isArray(words) && words.length
        ? words.map((item) => `<span class="word ${item.label_id === 1 ? 'aigt' : 'hwt'}" title="${App.utils.escapeHtml(item.label)}">${App.utils.escapeHtml(item.token)}</span>`).join(' ')
        : '暂无结果';
    }
    if (App.nodes.sentenceList) {
      App.nodes.sentenceList.innerHTML = Array.isArray(sentences) && sentences.length
        ? sentences.map((item) => `
          <div class="sentence-item ${item.label === 'AIGT' ? 'aigt' : 'hwt'}">
            <div><strong>句子 ${item.index + 1}</strong> | ${App.utils.escapeHtml(item.label)}</div>
            <div>${App.utils.escapeHtml(item.text)}</div>
          </div>
        `).join('')
        : '<div class="muted">暂无结果</div>';
    }
  },

  async detect() {
    try {
      App.nodes.detectMsg.textContent = '检测中...';
      const text = App.nodes.inputText.value.trim();
      if (!text) {
        throw new Error('请输入文本内容');
      }
      const result = await App.utils.request('/api/detect', 'POST', { text }, true);
      App.actions.renderResults(result.result.words || [], result.result.sentences || []);
      App.nodes.detectMsg.textContent = '检测完成';
      await App.actions.loadHistory();
    } catch (error) {
      App.nodes.detectMsg.textContent = error.message;
    }
  },

  async loadHistory() {
    if (!App.state.token) {
      App.nodes.historyList.innerHTML = '<div class="muted">请先登录</div>';
      return;
    }
    try {
      const rows = await App.utils.request('/api/history', 'GET', null, true);
      App.state.historyRows = rows;
      App.nodes.historyList.innerHTML = rows.map((item) => `
        <div class="history-item">
          <div>${App.utils.escapeHtml(item.created_at)}</div>
          <div>${App.utils.escapeHtml((item.input_text || '').slice(0, 80))}</div>
        </div>
      `).join('');
    } catch (error) {
      App.nodes.historyList.innerHTML = `<div class="muted">加载失败：${App.utils.escapeHtml(error.message)}</div>`;
    }
  },
};

App.bind = function () {
  document.getElementById('tabLogin')?.addEventListener('click', () => App.actions.toggleAuthPanel('login'));
  document.getElementById('tabRegister')?.addEventListener('click', () => App.actions.toggleAuthPanel('register'));
  document.getElementById('loginBtn')?.addEventListener('click', () => App.actions.login());
  document.getElementById('registerBtn')?.addEventListener('click', () => App.actions.register());
  document.getElementById('detectBtn')?.addEventListener('click', () => App.actions.detect());
};

App.init = function () {
  App.actions.updateUserBadge();
  App.actions.toggleAuthPanel('login');
  App.bind();
  if (App.state.token) {
    App.actions.loadHistory();
  }
};

App.init();
