// ============================================================================
// Authentication Module
// ============================================================================

const Auth = {
  // =========================
  // Getters
  // =========================
  
  /** 获取存储的认证令牌 */
  get token() {
    return localStorage.getItem('aigc_token') || '';
  },
  
  /** 获取存储的用户名 */
  get username() {
    return localStorage.getItem('aigc_user') || '';
  },
  
  /** 检查是否已登录 */
  get isLoggedIn() {
    return !!this.token;
  },
  
  // =========================
  // Setters
  // =========================
  
  /** 保存认证信息 */
  set(token, username) {
    if (token) {
      localStorage.setItem('aigc_token', token);
    }
    if (username) {
      localStorage.setItem('aigc_user', username);
    }
  },
  
  /** 清除所有认证信息 */
  clear() {
    localStorage.removeItem('aigc_token');
    localStorage.removeItem('aigc_user');
  },
  
  // =========================
  // Token Management
  // =========================
  
  /** 获取Token过期时间（从JWT解析） */
  getTokenExpiry() {
    const token = this.token;
    if (!token) return null;
    
    try {
      const payload = token.split('.')[1];
      const decoded = JSON.parse(atob(payload));
      return decoded.exp ? decoded.exp * 1000 : null;
    } catch {
      return null;
    }
  },
  
  /** 检查Token是否即将过期（5分钟内） */
  isTokenExpiringSoon() {
    const expiry = this.getTokenExpiry();
    if (!expiry) return false;
    const fiveMinutes = 5 * 60 * 1000;
    return (expiry - Date.now()) < fiveMinutes;
  },
};


// ============================================================================
// HTML escaping
// ============================================================================

/** 转义HTML特殊字符，防止XSS攻击 */
function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}


// ============================================================================
// HTTP Request Helpers
// ============================================================================

/** 构建请求头 */
function buildHeaders(needAuth) {
  const headers = {
    'Accept': 'application/json',
  };
  if (needAuth) {
    if (!Auth.token) {
      throw new Error('请先登录');
    }
    headers['Authorization'] = `Bearer ${Auth.token}`;
  }
  return headers;
}


/** 封装的API请求函数，支持超时控制 */
async function api(path, method = 'GET', body = null, needAuth = false, timeoutMs = 15000) {
  const headers = buildHeaders(needAuth);
  let requestBody = null;

  if (body instanceof FormData) {
    requestBody = body;
  } else if (body !== null && body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestBody = JSON.stringify(body);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const response = await fetch(path, {
    method,
    headers,
    body: requestBody,
    signal: controller.signal,
  }).finally(() => clearTimeout(timeout));

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || '请求失败');
    error.detail = data.detail;
    error.status = response.status;
    throw error;
  }
  return data;
}


/** 带重试的API请求 */
async function apiWithRetry(path, method = 'GET', body = null, needAuth = false, retries = 2) {
  let lastError;
  for (let i = 0; i <= retries; i++) {
    try {
      return await api(path, method, body, needAuth);
    } catch (error) {
      lastError = error;
      if (i < retries && error.status !== 401) {
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
  }
  throw lastError;
}


// ============================================================================
// Authentication Guards
// ============================================================================

/** 要求用户已登录，否则跳转到登录页 */
function requireLogin() {
  if (!Auth.token) {
    window.location.href = '/login';
    return false;
  }
  return true;
}


/** 要求用户未登录，否则跳转到检测页 */
function requireGuest() {
  if (Auth.token) {
    window.location.href = '/detect';
    return false;
  }
  return true;
}


// ============================================================================
// User Interface Helpers
// ============================================================================

/** 挂载用户信息到指定元素 */
function mountUserInfo(elUser, onLogout) {
  if (!elUser) return;
  elUser.textContent = Auth.username ? `当前用户: ${Auth.username}` : '未登录';
  if (typeof onLogout === 'function') {
    onLogout();
  }
}


/** 显示提示消息 */
function showMessage(element, message, type = 'info') {
  if (!element) return;
  element.textContent = message;
  const colors = {
    error: '#b13f00',
    success: '#0a7f6f',
    warning: '#e67e22',
    info: '#5f6c75'
  };
  element.style.color = colors[type] || colors.info;
  
  if (type !== 'error') {
    setTimeout(() => {
      if (element.textContent === message) {
        element.textContent = '';
      }
    }, 3000);
  }
}


/** 显示加载状态 */
function showLoading(button, isLoading, originalText = null) {
  if (!button) return;
  if (isLoading) {
    button.dataset.originalText = originalText || button.textContent;
    button.textContent = '处理中...';
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}