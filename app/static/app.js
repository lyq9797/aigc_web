// ============================================================================
// Application State
// ============================================================================

const App = {
  state: {
    token: localStorage.getItem('aigc_token') || '',
    username: localStorage.getItem('aigc_user') || '',
    historyRows: [],
    currentDetectResult: null,
    loading: false,
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
    loadingOverlay: document.getElementById('loadingOverlay'),
  },
};


// ============================================================================
// Utility Functions
// ============================================================================

App.utils = {
  /** 转义HTML特殊字符，防止XSS攻击 */
  escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  /** 格式化日期时间 */
  formatDateTime(isoString) {
    if (!isoString) return '未知时间';
    const date = new Date(isoString);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  },

  /** 显示加载状态 */
  showLoading(show) {
    App.state.loading = show;
    if (App.elements.loadingOverlay) {
      App.elements.loadingOverlay.classList.toggle('hidden', !show);
    }
    // 禁用检测按钮
    if (App.elements.detectBtn) {
      App.elements.detectBtn.disabled = show;
    }
  },

  /** 封装HTTP请求，支持超时和重试 */
  async request(path, method = 'GET', body = null, secure = false, retries = 1) {
    const headers = {};
    if (secure) {
      if (!App.state.token) {
        throw new Error('请先登录');
      }
      headers['Authorization'] = `Bearer ${App.state.token}`;
    }
    if (body && !(body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const makeRequest = async () => {
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
    };

    for (let i = 0; i <= retries; i++) {
      try {
        return await makeRequest();
      } catch (error) {
        if (i === retries) throw error;
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
  },

  /** 设置提示消息 */
  setMessage(element, text, type = 'normal') {
    if (!element) return;
    element.textContent = text;
    const colors = { error: '#b13f00', success: '#0a7f6f', warning: '#e67e22', normal: '#5f6c75' };
    element.style.color = colors[type] || colors.normal;
    // 3秒后自动清除普通消息
    if (type === 'normal' && text) {
      setTimeout(() => {
        if (element.textContent === text) element.textContent = '';
      }, 3000);
    }
  },

  /** 防抖函数 */
  debounce(func, delay) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => func.apply(this, args), delay);
    };
  },
};


// ============================================================================
// Core Actions
// ============================================================================

App.actions = {
  /** 更新用户显示信息 */
  updateUserDisplay() {
    if (!App.elements.currentUser) return;
    App.elements.currentUser.textContent = App.state.token 
      ? `👤 ${App.state.username}` 
      : '未登录';
  },

  /** 保存登录会话 */
  saveSession(token, username) {
    App.state.token = token;
    App.state.username = username;
    localStorage.setItem('aigc_token', token);
    localStorage.setItem('aigc_user', username);
    App.actions.updateUserDisplay();
  },

  /** 清除登录会话 */
  clearSession() {
    App.state.token = '';
    App.state.username = '';
    localStorage.removeItem('aigc_token');
    localStorage.removeItem('aigc_user');
    App.actions.updateUserDisplay();
    window.location.href = '/login';
  },

  /** 切换认证面板 */
  setActiveAuthPanel(type) {
    const isLogin = type === 'login';
    if (App.elements.loginForm) {
      App.elements.loginForm.classList.toggle('hidden', !isLogin);
    }
    if (App.elements.registerForm) {
      App.elements.registerForm.classList.toggle('hidden', isLogin);
    }
    // 清空表单和消息
    if (App.elements.authMsg) App.elements.authMsg.textContent = '';
  },

  /** 清空表单 */
  clearForms() {
    if (App.elements.loginUsername) App.elements.loginUsername.value = '';
    if (App.elements.loginPassword) App.elements.loginPassword.value = '';
    if (App.elements.registerUsername) App.elements.registerUsername.value = '';
    if (App.elements.registerPassword) App.elements.registerPassword.value = '';
    if (App.elements.registerConfirm) App.elements.registerConfirm.value = '';
    if (App.elements.inputText) App.elements.inputText.value = '';
  },

  /** 用户登录 */
  async login() {
    try {
      App.utils.setMessage(App.elements.authMsg, '登录中...');
      const username = App.elements.loginUsername.value.trim();
      const password = App.elements.loginPassword.value;
      
      if (!username || !password) {
        throw new Error('用户名和密码不能为空');
      }
      if (username.length < 3 || username.length > 50) {
        throw new Error('用户名长度应为3-50字符');
      }
      
      const result = await App.utils.request('/api/login', 'POST', { username, password }, false);
      App.actions.saveSession(result.token, result.username);
      App.utils.setMessage(App.elements.authMsg, '登录成功，正在跳转...', 'success');
      
      setTimeout(() => {
        window.location.href = '/detect';
      }, 1000);
    } catch (error) {
      App.utils.setMessage(App.elements.authMsg, error.message, 'error');
    }
  },

  /** 用户注册 */
  async register() {
    try {
      App.utils.setMessage(App.elements.authMsg, '注册中...');
      const username = App.elements.registerUsername.value.trim();
      const password = App.elements.registerPassword.value;
      const confirm = App.elements.registerConfirm.value;
      
      if (!username || !password || !confirm) {
        throw new Error('请填写完整信息');
      }
      if (username.length < 3 || username.length > 50) {
        throw new Error('用户名长度应为3-50字符');
      }
      if (password.length < 6) {
        throw new Error('密码长度至少6位');
      }
      if (password !== confirm) {
        throw new Error('两次密码输入不一致');
      }
      
      await App.utils.request('/api/register', 'POST', { username, password }, false);
      App.utils.setMessage(App.elements.authMsg, '注册成功，请登录', 'success');
      
      setTimeout(() => {
        App.actions.setActiveAuthPanel('login');
        App.actions.clearForms();
      }, 1500);
    } catch (error) {
      App.utils.setMessage(App.elements.authMsg, error.message, 'error');
    }
  },

  /** 渲染检测结果 */
  renderDetectResults(words, sentences, summary = null) {
    // 渲染词级高亮
    if (App.elements.wordHighlight) {
      if (Array.isArray(words) && words.length) {
        const wordHtml = words.map((item) => `
          <span class="word ${item.label_id === 1 ? 'aigt' : 'hwt'}" 
                title="标签: ${App.utils.escapeHtml(item.label)}">
            ${App.utils.escapeHtml(item.token)}
          </span>
        `).join(' ');
        App.elements.wordHighlight.innerHTML = wordHtml;
      } else {
        App.elements.wordHighlight.innerHTML = '<div class="muted">暂无结果</div>';
      }
    }
    
    // 渲染句子级结果
    if (App.elements.sentenceList) {
      if (Array.isArray(sentences) && sentences.length) {
        const sentenceHtml = sentences.map((item) => `
          <div class="sentence-item ${item.label === 'AIGT' ? 'aigt' : 'hwt'}">
            <div class="sentence-header">
              <strong>句子 ${item.index + 1}</strong>
              <span class="sentence-label">标签: ${App.utils.escapeHtml(item.label)}</span>
              ${item.confidence ? `<span class="sentence-confidence">置信度: ${(item.confidence * 100).toFixed(1)}%</span>` : ''}
            </div>
            <div class="sentence-text">${App.utils.escapeHtml(item.text)}</div>
          </div>
        `).join('');
        App.elements.sentenceList.innerHTML = sentenceHtml;
      } else {
        App.elements.sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
      }
    }
    
    // 显示摘要信息
    if (summary && App.elements.detectMsg) {
      const timeMsg = summary.processing_time_ms ? ` (耗时 ${summary.processing_time_ms}ms)` : '';
      App.utils.setMessage(App.elements.detectMsg, `检测完成${timeMsg}`, 'success');
    }
  },

  /** 加载示例文本 */
  loadSampleText() {
    const sample = "人工智能技术正在快速发展，深度学习模型在自然语言处理领域取得了显著成果。然而，AI生成的内容检测仍然是一个具有挑战性的问题。研究人员正在开发更精确的检测方法来识别机器生成的文本。";
    if (App.elements.inputText) {
      App.elements.inputText.value = sample;
      App.utils.setMessage(App.elements.detectMsg, '示例文本已加载', 'success');
    }
  },

  /** 清除输入文本 */
  clearInputText() {
    if (App.elements.inputText) {
      App.elements.inputText.value = '';
      App.utils.setMessage(App.elements.detectMsg, '已清除', 'normal');
    }
    // 清空检测结果
    if (App.elements.wordHighlight) {
      App.elements.wordHighlight.innerHTML = '<div class="muted">暂无结果</div>';
    }
    if (App.elements.sentenceList) {
      App.elements.sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    }
  },

  /** 执行文本检测 */
  async detect() {
    if (App.state.loading) {
      App.utils.setMessage(App.elements.detectMsg, '请等待上一次检测完成', 'warning');
      return;
    }
    
    try {
      App.utils.showLoading(true);
      App.utils.setMessage(App.elements.detectMsg, '检测中，请稍候...');
      
      const text = App.elements.inputText.value.trim();
      if (!text) {
        throw new Error('请输入要检测的文本');
      }
      if (text.length > 10000) {
        throw new Error('文本长度超过限制（最大10000字符）');
      }
      
      const data = await App.utils.request('/api/detect', 'POST', { text }, true);
      App.state.currentDetectResult = data.result;
      App.actions.renderDetectResults(
        data.result.words || [], 
        data.result.sentences || [],
        data.result.summary
      );
      
      // 刷新历史记录
      await App.actions.loadHistory();
    } catch (error) {
      App.utils.setMessage(App.elements.detectMsg, error.message, 'error');
    } finally {
      App.utils.showLoading(false);
    }
  },

  /** 加载历史记录 */
  async loadHistory() {
    if (!App.state.token) {
      if (App.elements.historyList) {
        App.elements.historyList.innerHTML = '<div class="muted">请先登录查看历史记录</div>';
      }
      return;
    }
    
    try {
      const rows = await App.utils.request('/api/history', 'GET', null, true);
      App.state.historyRows = rows;
      
      if (App.elements.historyList) {
        if (!rows || rows.length === 0) {
          App.elements.historyList.innerHTML = '<div class="muted">暂无检测记录</div>';
        } else {
          App.elements.historyList.innerHTML = rows.map((item) => `
            <div class="history-item" data-id="${item.id}">
              <div class="history-time">${App.utils.formatDateTime(item.created_at)}</div>
              <div class="history-text">${App.utils.escapeHtml((item.input_text || '').slice(0, 80))}${(item.input_text || '').length > 80 ? '...' : ''}</div>
            </div>
          `).join('');
        }
      }
    } catch (error) {
      if (App.elements.historyList) {
        App.elements.historyList.innerHTML = `<div class="muted">加载失败：${App.utils.escapeHtml(error.message)}</div>`;
      }
    }
  },

  /** 清空历史记录 */
  async clearHistory() {
    if (!confirm('确定要清空所有历史记录吗？此操作不可恢复。')) return;
    
    try {
      const result = await App.utils.request('/api/history', 'DELETE', null, true);
      App.utils.setMessage(App.elements.detectMsg, `已清空 ${result.deleted} 条记录`, 'success');
      await App.actions.loadHistory();
    } catch (error) {
      App.utils.setMessage(App.elements.detectMsg, error.message, 'error');
    }
  },
};


// ============================================================================
// Event Binding
// ============================================================================

App.bindEvents = function () {
  // 标签页切换
  const tabLogin = document.getElementById('tabLogin');
  const tabRegister = document.getElementById('tabRegister');
  tabLogin?.addEventListener('click', () => App.actions.setActiveAuthPanel('login'));
  tabRegister?.addEventListener('click', () => App.actions.setActiveAuthPanel('register'));
  
  // 按钮事件
  const loginBtn = document.getElementById('loginBtn');
  const registerBtn = document.getElementById('registerBtn');
  const detectBtn = document.getElementById('detectBtn');
  const sampleBtn = document.getElementById('sampleBtn');
  const clearBtn = document.getElementById('clearBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const clearHistoryBtn = document.getElementById('clearHistoryBtn');
  
  loginBtn?.addEventListener('click', () => App.actions.login());
  registerBtn?.addEventListener('click', () => App.actions.register());
  detectBtn?.addEventListener('click', () => App.actions.detect());
  sampleBtn?.addEventListener('click', () => App.actions.loadSampleText());
  clearBtn?.addEventListener('click', () => App.actions.clearInputText());
  logoutBtn?.addEventListener('click', () => App.actions.clearSession());
  clearHistoryBtn?.addEventListener('click', () => App.actions.clearHistory());
  
  // 历史记录点击查看详情
  const historyList = document.getElementById('historyList');
  historyList?.addEventListener('click', (event) => {
    const item = event.target.closest('.history-item');
    if (item && item.dataset.id) {
      const record = App.state.historyRows.find(r => r.id === parseInt(item.dataset.id));
      if (record) {
        App.actions.renderDetectResults(
          record.result?.words || [],
          record.result?.sentences || []
        );
        if (App.elements.inputText) {
          App.elements.inputText.value = record.input_text;
        }
        App.utils.setMessage(App.elements.detectMsg, `已加载历史记录 #${record.id}`, 'success');
      }
    }
  });
  
  // 键盘快捷提交
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      if (document.activeElement === App.elements.loginPassword) {
        event.preventDefault();
        App.actions.login();
      } else if (document.activeElement === App.elements.registerConfirm) {
        event.preventDefault();
        App.actions.register();
      } else if (document.activeElement === App.elements.inputText && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        App.actions.detect();
      }
    }
  });
  
  // 输入框防抖自动保存
  const inputText = App.elements.inputText;
  if (inputText) {
    const saveDraft = App.utils.debounce(() => {
      localStorage.setItem('aigc_draft', inputText.value);
    }, 500);
    inputText.addEventListener('input', saveDraft);
    
    // 恢复草稿
    const draft = localStorage.getItem('aigc_draft');
    if (draft && !inputText.value) {
      inputText.value = draft;
    }
  }
};


// ============================================================================
// Application Initialization
// ============================================================================

App.init = function () {
  App.actions.updateUserDisplay();
  App.actions.setActiveAuthPanel('login');
  App.bindEvents();
  
  if (App.state.token) {
    App.actions.loadHistory();
    // 如果当前在检测页面，加载草稿
    if (window.location.pathname === '/detect') {
      const draft = localStorage.getItem('aigc_draft');
      if (draft && App.elements.inputText) {
        App.elements.inputText.value = draft;
      }
    }
  }
};

// 页面可见性变化时刷新历史
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && App.state.token && window.location.pathname === '/detect') {
    App.actions.loadHistory();
  }
});

App.init();