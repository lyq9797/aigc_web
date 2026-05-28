/**
 * AI 文本检测系统 - 核心应用逻辑
 * 
 * 【安全检测说明】
 * 1. 本文件包含敏感凭证处理与 DOM 渲染逻辑，需严格防范 XSS 与 CSRF 攻击。
 * 2. 生产环境必须配合 HTTPS 传输，并建议配置严格的 Content-Security-Policy (CSP)。
 */
(function () {
  'use strict';

  /* ==========================================
   * 1. 常量与配置 (Constants & Configuration)
   * ========================================== */
  const CONFIG = {
    STORAGE_KEYS: {
      TOKEN: 'aigc_token',
      USER: 'aigc_user',
    },
    API_PATHS: {
      REGISTER: '/api/register',
      LOGIN: '/api/login',
      DETECT: '/api/detect',
      HISTORY: '/api/history',
    },
    UI_COLORS: {
      SUCCESS: '#0a7f6f',
      ERROR: '#b13f00',
      INFO: '#5f6c75',
    },
    SAMPLE_TEXT: 'This is an interesting paper on how to handle reparameterization in VAEs when you have discrete variables. They propose a new architecture called Discrete Variational Autoencoders (DVAEs) which combines an undirected discrete component and a directed hierarchical continuous component. This allows them to learn both the class of objects in an image as well as their specific realization in pixels. They show that DVAEs outperform other state-of-the-art methods on several benchmark datasets.',
  };

  /* ==========================================
   * 2. 状态与 DOM 缓存 (State & DOM Cache)
   * ========================================== */
  
  /** @type {{ token: string, username: string }} */
  const state = {
    token: localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN) ?? '',
    username: localStorage.getItem(CONFIG.STORAGE_KEYS.USER) ?? '',
  };

  /** 缓存所有需要频繁访问的 DOM 元素，避免重复查询 */
  const el = {
    // 认证模块
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
    // 检测模块
    inputText: document.getElementById('inputText'),
    sampleBtn: document.getElementById('sampleBtn'),
    clearBtn: document.getElementById('clearBtn'),
    detectBtn: document.getElementById('detectBtn'),
    detectMsg: document.getElementById('detectMsg'),
    // 结果展示模块
    wordHighlight: document.getElementById('wordHighlight'),
    sentenceList: document.getElementById('sentenceList'),
    switchInfo: document.getElementById('switchInfo'),
    // 历史记录模块
    refreshHistoryBtn: document.getElementById('refreshHistoryBtn'),
    historyList: document.getElementById('historyList'),
  };

  /* ==========================================
   * 3. 工具与安全函数 (Utilities & Security)
   * ========================================== */

  /**
   * HTML 实体转义，防止 DOM 型 XSS 攻击
   * 【安全检测核心】所有动态插入 innerHTML 的用户输入或后端数据必须经过此函数处理
   * @param {string} str - 需要转义的原始字符串
   * @returns {string} 转义后的安全字符串
   */
  function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return str.replace(/[&<>"']/g, (char) => map[char]);
  }

  /**
   * 安全地更新提示消息
   * @param {HTMLElement} element - 目标 DOM 元素
   * @param {string} message - 消息内容
   * @param {'success' | 'error' | 'info'} type - 消息类型
   */
  function setMessage(element, message, type = 'info') {
    if (!element) return;
    // 【安全说明】此处使用 textContent 而非 innerHTML，从根本上免疫 XSS 注入
    element.textContent = message;
    element.style.color = CONFIG.UI_COLORS[type.toUpperCase()] || CONFIG.UI_COLORS.INFO;
  }

  /* ==========================================
   * 4. 认证状态管理 (Auth State Management)
   * ========================================== */

  /**
   * 【安全检测注释】
   * 当前使用 localStorage 存储 Token。
   * 风险：若页面存在 XSS 漏洞，Token 可被恶意脚本窃取。
   * 建议：生产环境应优先使用 HttpOnly + Secure + SameSite=Strict 的 Cookie 存储 Token。
   */
  function saveAuth(token, username) {
    state.token = token;
    state.username = username;
    localStorage.setItem(CONFIG.STORAGE_KEYS.TOKEN, token);
    localStorage.setItem(CONFIG.STORAGE_KEYS.USER, username);
    updateAuthUI();
  }

  function clearAuth() {
    state.token = '';
    state.username = '';
    localStorage.removeItem(CONFIG.STORAGE_KEYS.TOKEN);
    localStorage.removeItem(CONFIG.STORAGE_KEYS.USER);
    updateAuthUI();
  }

  function updateAuthUI() {
    if (el.currentUser) {
      el.currentUser.textContent = state.token ? `当前用户: ${state.username}` : '未登录';
    }
  }

  function showAuthTab(mode) {
    const isLogin = mode === 'login';
    el.loginPanel?.classList.toggle('hidden', !isLogin);
    el.registerPanel?.classList.toggle('hidden', isLogin);
    el.tabLogin?.classList.toggle('active', isLogin);
    el.tabRegister?.classList.toggle('active', !isLogin);
    
    // 更新 ARIA 属性以支持无障碍访问
    if (el.tabLogin) el.tabLogin.setAttribute('aria-selected', String(isLogin));
    if (el.tabRegister) el.tabRegister.setAttribute('aria-selected', String(!isLogin));
  }

  /* ==========================================
   * 5. 网络请求封装 (API Request Wrapper)
   * ========================================== */

  /**
   * 统一的 API 请求封装
   * @param {string} path - API 路径
   * @param {'GET' | 'POST' | 'PUT' | 'DELETE'} method - HTTP 方法
   * @param {Object|null} body - 请求体数据
   * @param {boolean} needAuth - 是否需要携带认证 Token
   * @returns {Promise<any>} 解析后的 JSON 数据
   */
  async function api(path, method = 'GET', body = null, needAuth = false) {
    const headers = { 'Content-Type': 'application/json' };
    
    if (needAuth) {
      if (!state.token) throw new Error('会话已过期，请重新登录');
      headers['Authorization'] = `Bearer ${state.token}`;
    }

    try {
      const resp = await fetch(path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
        // 【安全说明】明确指定 credentials，若后端使用 Cookie 认证需设为 'include'
        credentials: 'same-origin', 
      });

      // 尝试解析 JSON，若响应非 JSON 格式则回退为空对象
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        // 优先使用后端返回的详细错误信息，否则使用 HTTP 状态文本
        throw new Error(data.detail || data.message || resp.statusText || '请求失败');
      }
      
      return data;
    } catch (error) {
      // 区分网络层异常（如断网）和业务层异常
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('网络连接失败，请检查您的网络设置');
      }
      throw error;
    }
  }

  /* ==========================================
   * 6. 业务逻辑与渲染 (Business Logic & Rendering)
   * ========================================== */

  async function doRegister() {
    try {
      const username = el.registerUsername.value.trim();
      const password = el.registerPassword.value;
      
      // 【安全说明】密码通过 HTTPS 传输，前端不应记录或打印明文密码
      const res = await api(CONFIG.API_PATHS.REGISTER, 'POST', { username, password });
      saveAuth(res.token, res.username);
      setMessage(el.authMsg, '注册成功，已自动登录', 'success');
      await loadHistory();
    } catch (err) {
      setMessage(el.authMsg, err.message, 'error');
    }
  }

  async function doLogin() {
    try {
      const username = el.loginUsername.value.trim();
      const password = el.loginPassword.value;
      
      const res = await api(CONFIG.API_PATHS.LOGIN, 'POST', { username, password });
      saveAuth(res.token, res.username);
      setMessage(el.authMsg, '登录成功', 'success');
      await loadHistory();
    } catch (err) {
      setMessage(el.authMsg, err.message, 'error');
    }
  }

  async function doDetect() {
    try {
      setMessage(el.detectMsg, '检测中，请稍候...', 'info');
      const text = el.inputText.value.trim();
      
      if (!text) {
        throw new Error('请输入待检测的文本');
      }

      const res = await api(CONFIG.API_PATHS.DETECT, 'POST', { text }, true);
      
      renderSwitch(res.result?.summary);
      renderWordHighlight(res.result?.words);
      renderSentences(res.result?.sentences);
      
      setMessage(el.detectMsg, '检测完成', 'success');
      await loadHistory();
    } catch (err) {
      setMessage(el.detectMsg, err.message, 'error');
    }
  }

  async function loadHistory() {
    if (!state.token) {
      if (el.historyList) el.historyList.innerHTML = '<div class="muted">请先登录</div>';
      return;
    }

    try {
      const rows = await api(CONFIG.API_PATHS.HISTORY, 'GET', null, true);
      
      if (!rows || !rows.length) {
        el.historyList.innerHTML = '<div class="muted">暂无历史记录</div>';
        return;
      }

      // 【安全检测核心】使用 escapeHtml 处理所有动态数据，防止存储型 XSS 通过历史记录回显攻击
      el.historyList.innerHTML = rows.map((r) => {
        const summary = r.result?.summary ?? {};
        const rawText = r.input_text ?? '';
        const preview = rawText.slice(0, 100);
        const hasMore = rawText.length > 100;
        
        return `
          <div class="history-item">
            <div class="time">${escapeHtml(r.created_at)}</div>
            <div>切换词位: ${Number(summary.switch_word_index ?? 0) + 1} | 切换句位: ${Number(summary.switch_sentence_index ?? 0) + 1}</div>
            <div>${escapeHtml(preview)}${hasMore ? '...' : ''}</div>
          </div>
        `;
      }).join('');
    } catch (err) {
      el.historyList.innerHTML = `<div class="muted">加载失败: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderWordHighlight(words) {
    if (!words || !words.length) {
      el.wordHighlight.textContent = '暂无结果';
      return;
    }

    const html = words.map((w) => {
      const cls = w.label_id === 1 ? 'aigt' : 'hwt';
      // 对 title 属性中的动态数据也进行转义，防止属性注入
      const title = `${escapeHtml(w.label)} | 置信度 ${escapeHtml(String(w.confidence))}`;
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
          <div><strong>句子 ${s.index + 1}</strong> | 标签: ${escapeHtml(s.label)} | 置信度: ${escapeHtml(String(s.confidence))}</div>
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

    const wordPos = Number(summary.switch_word_index ?? 0) + 1;
    const sentPos = Number(summary.switch_sentence_index ?? 0) + 1;
    el.switchInfo.textContent = `检测到的切换点位于第 ${wordPos} 个词 / 第 ${sentPos} 个句子`;
  }

  /* ==========================================
   * 7. 事件绑定与初始化 (Event Binding & Init)
   * ========================================== */

  function bindEvents() {
    // 认证相关
    el.tabLogin?.addEventListener('click', () => showAuthTab('login'));
    el.tabRegister?.addEventListener('click', () => showAuthTab('register'));
    el.registerBtn?.addEventListener('click', doRegister);
    el.loginBtn?.addEventListener('click', doLogin);

    el.logoutBtn?.addEventListener('click', () => {
      clearAuth();
      if (el.authMsg) el.authMsg.textContent = '';
      if (el.detectMsg) el.detectMsg.textContent = '';
      if (el.historyList) el.historyList.innerHTML = '<div class="muted">请先登录</div>';
    });

    // 检测相关
    el.sampleBtn?.addEventListener('click', () => {
      if (el.inputText) el.inputText.value = CONFIG.SAMPLE_TEXT;
    });

    el.clearBtn?.addEventListener('click', () => {
      if (el.inputText) el.inputText.value = '';
      if (el.wordHighlight) el.wordHighlight.textContent = '暂无结果';
      if (el.sentenceList) el.sentenceList.innerHTML = '';
      if (el.switchInfo) el.switchInfo.textContent = '切换点：暂无';
      if (el.detectMsg) el.detectMsg.textContent = '';
    });

    el.detectBtn?.addEventListener('click', doDetect);
    el.refreshHistoryBtn?.addEventListener('click', loadHistory);
  }

  function init() {
    updateAuthUI();
    bindEvents();
    loadHistory();
  }

  // 启动应用
  init();
})();
