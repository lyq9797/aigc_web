const App = {
  state: {
    token: localStorage.getItem('aigc_token') || '',
    username: localStorage.getItem('aigc_user') || '',
    historyRows: [],
  },
  elements: {
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

  async request(path, method = 'GET', body = null, secure = false) {
    const headers = {};
    if (secure) {
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
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || '请求失败');
    }
    return data;
  },

  setMessage(element, text, type = 'normal') {
    if (!element) return;
    element.textContent = text;
    element.style.color = type === 'error' ? '#b13f00' : type === 'success' ? '#0a7f6f' : '#5f6c75';
  },
};

App.actions = {
  updateUserDisplay() {
    if (!App.elements.currentUser) return;
    App.elements.currentUser.textContent = App.state.token ? `当前用户: ${App.state.username}` : '未登录';
  },

  saveSession(token, username) {
    App.state.token = token;
    App.state.username = username;
    localStorage.setItem('aigc_token', token);
    localStorage.setItem('aigc_user', username);
    App.actions.updateUserDisplay();
  },

  clearSession() {
    App.state.token = '';
    App.state.username = '';
    localStorage.removeItem('aigc_token');
    localStorage.removeItem('aigc_user');
    App.actions.updateUserDisplay();
  },

  setActiveAuthPanel(type) {
    const isLogin = type === 'login';
    App.elements.loginForm?.classList.toggle('hidden', !isLogin);
    App.elements.registerForm?.classList.toggle('hidden', isLogin);
  },

  async login() {
    try {
      App.utils.setMessage(App.elements.authMsg, '登录中...');
      const username = App.elements.loginUsername.value.trim();
      const password = App.elements.loginPassword.value;
      if (!username || !password) {
        throw new Error('用户名和密码不能为空');
      }
      const result = await App.utils.request('/api/login', 'POST', { username, password }, false);
      App.actions.saveSession(result.token, result.username);
      App.utils.setMessage(App.elements.authMsg, '登录成功', 'success');
      await App.actions.loadHistory();
    } catch (error) {
      App.utils.setMessage(App.elements.authMsg, error.message, 'error');
    }
  },

  async register() {
    try {
      App.utils.setMessage(App.elements.authMsg, '注册中...');
      const username = App.elements.registerUsername.value.trim();
      const password = App.elements.registerPassword.value;
      const confirm = App.elements.registerConfirm.value;
      if (!username || !password || !confirm) {
        throw new Error('请填写完整信息');
      }
      if (password !== confirm) {
        throw new Error('两次密码输入不一致');
      }
      await App.utils.request('/api/register', 'POST', { username, password }, false);
      App.utils.setMessage(App.elements.authMsg, '注册成功，请登录', 'success');
      App.actions.setActiveAuthPanel('login');
    } catch (error) {
      App.utils.setMessage(App.elements.authMsg, error.message, 'error');
    }
  },

  renderDetectResults(words, sentences) {
    if (App.elements.wordHighlight) {
      App.elements.wordHighlight.innerHTML = Array.isArray(words) && words.length
        ? words.map((item) => `<span class="word ${item.label_id === 1 ? 'aigt' : 'hwt'}" title="${App.utils.escapeHtml(item.label)}">${App.utils.escapeHtml(item.token)}</span>`).join(' ')
        : '暂无结果';
    }
    if (App.elements.sentenceList) {
      App.elements.sentenceList.innerHTML = Array.isArray(sentences) && sentences.length
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
      App.utils.setMessage(App.elements.detectMsg, '检测中...');
      const text = App.elements.inputText.value.trim();
      if (!text) {
        throw new Error('请输入要检测的文本');
      }
      const data = await App.utils.request('/api/detect', 'POST', { text }, true);
      App.actions.renderDetectResults(data.result.words || [], data.result.sentences || []);
      App.utils.setMessage(App.elements.detectMsg, '检测完成', 'success');
      await App.actions.loadHistory();
    } catch (error) {
      App.utils.setMessage(App.elements.detectMsg, error.message, 'error');
    }
  },

  async loadHistory() {
    if (!App.state.token) {
      if (App.elements.historyList) {
        App.elements.historyList.innerHTML = '<div class="muted">请先登录</div>';
      }
      return;
    }
    try {
      const rows = await App.utils.request('/api/history', 'GET', null, true);
      App.state.historyRows = rows;
      if (App.elements.historyList) {
        App.elements.historyList.innerHTML = rows.map((item) => `
          <div class="history-item">
            <div>${App.utils.escapeHtml(item.created_at)}</div>
            <div>${App.utils.escapeHtml((item.input_text || '').slice(0, 80))}</div>
          </div>
        `).join('');
      }
    } catch (error) {
      if (App.elements.historyList) {
        App.elements.historyList.innerHTML = `<div class="muted">加载失败：${App.utils.escapeHtml(error.message)}</div>`;
      }
    }
  },
};

App.bindEvents = function () {
  document.getElementById('tabLogin')?.addEventListener('click', () => App.actions.setActiveAuthPanel('login'));
  document.getElementById('tabRegister')?.addEventListener('click', () => App.actions.setActiveAuthPanel('register'));
  document.getElementById('loginBtn')?.addEventListener('click', () => App.actions.login());
  document.getElementById('registerBtn')?.addEventListener('click', () => App.actions.register());
  document.getElementById('detectBtn')?.addEventListener('click', () => App.actions.detect());
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    if (document.activeElement === App.elements.loginPassword) {
      App.actions.login();
    }
    if (document.activeElement === App.elements.registerConfirm) {
      App.actions.register();
    }
  });
};

App.init = function () {
  App.actions.updateUserDisplay();
  App.actions.setActiveAuthPanel('login');
  App.bindEvents();
  if (App.state.token) {
    App.actions.loadHistory();
  }
};

App.init();
