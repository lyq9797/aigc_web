/**
 * AI 文本检测系统 - 公共工具与核心模块 (Common Utilities)
 * 
 * 【安全检测全局说明】
 * 1. 本文件包含全局共享的凭证管理、网络请求与 DOM 渲染工具。
 * 2. 生产环境必须强制使用 HTTPS，并建议配置严格的 Content-Security-Policy (CSP)。
 */
(function (global) {
  'use strict';

  /* ==========================================
   * 1. 常量与配置 (Constants & Configuration)
   * ========================================== */
  const CONFIG = {
    STORAGE_KEYS: {
      TOKEN: 'aigc_token',
      USER: 'aigc_user',
    },
    ROUTES: {
      LOGIN: '/login',
    },
  };

  /* ==========================================
   * 2. 认证状态管理 (Auth State Management)
   * ========================================== */
  
  const Auth = {
    get token() {
      return localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN) ?? '';
    },
    get username() {
      return localStorage.getItem(CONFIG.STORAGE_KEYS.USER) ?? '';
    },
    
    /**
     * 保存认证凭证
     * 【安全检测注释】
     * 风险：当前使用 localStorage 存储 Token。若页面存在 XSS 漏洞，Token 可被恶意脚本直接窃取。
     * 建议：高安全要求场景下，应推动后端改为 HttpOnly + Secure + SameSite=Strict 的 Cookie 方案。
     */
    set(token, username) {
      localStorage.setItem(CONFIG.STORAGE_KEYS.TOKEN, token);
      localStorage.setItem(CONFIG.STORAGE_KEYS.USER, username);
    },
    
    clear() {
      localStorage.removeItem(CONFIG.STORAGE_KEYS.TOKEN);
      localStorage.removeItem(CONFIG.STORAGE_KEYS.USER);
    },
  };

  /* ==========================================
   * 3. 安全与工具函数 (Security & Utilities)
   * ========================================== */

  /**
   * HTML 实体转义，防止 DOM 型 XSS 攻击
   * 【安全检测核心】所有动态插入 innerHTML 的用户输入或后端数据必须经过此函数处理
   * @param {string|number|boolean} str - 需要转义的原始数据
   * @returns {string} 转义后的安全字符串
   */
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    };
    return String(str).replace(/[&<>"']/g, (char) => map[char]);
  }

  /* ==========================================
   * 4. 网络请求封装 (API Request Wrapper)
   * ========================================== */

  /**
   * 统一的 API 请求封装
   * @param {string} path - API 路径
   * @param {'GET' | 'POST' | 'PUT' | 'DELETE'} method - HTTP 方法
   * @param {Object|FormData|null} body - 请求体数据
   * @param {boolean} needAuth - 是否需要携带认证 Token
   * @returns {Promise<any>} 解析后的 JSON 数据
   */
  async function api(path, method = 'GET', body = null, needAuth = false) {
    const headers = {};
    
    // 处理认证头
    if (needAuth) {
      if (!Auth.token) {
        throw new Error('会话已过期，请重新登录');
      }
      headers['Authorization'] = `Bearer ${Auth.token}`;
    }

    let requestBody = null;
    
    // 处理请求体与 Content-Type
    if (body instanceof FormData) {
      requestBody = body;
      // 【关键修复】FormData 必须交由浏览器自动设置 Content-Type 及 Boundary，手动设置会导致请求失败
    } else if (body !== null && body !== undefined) {
      headers['Content-Type'] = 'application/json';
      requestBody = JSON.stringify(body);
    }

    try {
      const resp = await fetch(path, {
        method,
        headers,
        body: requestBody,
        // 【安全说明】明确指定 credentials，若后端使用 Cookie 认证需设为 'include'
        credentials: 'same-origin',
      });

      // 尝试解析 JSON，若响应非 JSON 格式则回退为空对象
      const data = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        const error = new Error(data.detail || data.message || '请求失败');
        error.detail = data.detail;
        error.status = resp.status;
        throw error;
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
   * 5. 路由与 UI 交互 (Routing & UI Interaction)
   * ========================================== */

  /**
   * 鉴权拦截器
   * 【安全检测注释】前端路由守卫仅用于提升用户体验，真正的鉴权必须在后端 API 网关层完成。
   */
  function requireLogin() {
    if (!Auth.token) {
      // 使用相对路径重定向，避免开放重定向 (Open Redirect) 风险
      window.location.href = CONFIG.ROUTES.LOGIN;
      return false;
    }
    return true;
  }

  /**
   * 挂载用户信息与退出逻辑
   * 【关键修复】原代码在挂载时会立即执行 onLogout 回调，现已修正为事件绑定模式。
   * 
   * @param {HTMLElement} elUser - 显示用户名的 DOM 元素
   * @param {HTMLElement} elLogoutBtn - 退出按钮 DOM 元素
   * @param {Function} onLogoutCallback - 点击退出后执行的清理回调函数
   */
  function mountUserInfo(elUser, elLogoutBtn, onLogoutCallback) {
    // 渲染用户信息
    if (elUser) {
      // 【安全说明】此处使用 textContent 渲染，从根本上免疫 XSS 注入
      elUser.textContent = `当前用户: ${Auth.username || '未知用户'}`;
    }
    
    // 绑定退出事件
    if (elLogoutBtn && typeof onLogoutCallback === 'function') {
      elLogoutBtn.addEventListener('click', () => {
        Auth.clear();
        onLogoutCallback();
        // 退出后重定向到登录页
        window.location.href = CONFIG.ROUTES.LOGIN;
      });
    }
  }

  /* ==========================================
   * 6. 模块导出 (Module Export)
   * ========================================== */
  
  // 将公共 API 挂载到全局对象，供其他页面脚本调用
  global.AppUtils = {
    Auth,
    escapeHtml,
    api,
    requireLogin,
    mountUserInfo,
  };

})(window);
// ============================================
// 补充说明：common.js 前端逻辑维护
// 提交日期标识：2026.3.2
// 脚本执行时间：2026-05-28 13:16:23
// ============================================
