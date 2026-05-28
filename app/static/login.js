/**
 * AI 文本检测系统 - 登录页面核心逻辑 (Login Page Logic)
 * 
 * 【安全检测全局说明】
 * 1. 本页面涉及敏感凭证（密码）的收集与传输，必须强制使用 HTTPS 以防止中间人攻击 (MITM)。
 * 2. 前端路由守卫（已登录跳转）仅用于提升用户体验，真正的会话校验必须在后端 API 层完成。
 */
(function (AppUtils) {
  'use strict';

  // 校验公共模块是否加载
  if (!AppUtils || !AppUtils.api) {
    console.error('AppUtils 未加载，请确保 common.js 在 login.js 之前引入');
    return;
  }

  const { Auth, api } = AppUtils;

  /* ==========================================
   * 1. 常量与配置 (Constants & Configuration)
   * ========================================== */
  const CONFIG = {
    API_PATHS: {
      LOGIN: '/api/login',
    },
    ROUTES: {
      DETECT: '/detect',
      REGISTER: '/register',
    },
    UI_COLORS: {
      INFO: '#D8DBB3',
      SUCCESS: '#0a7f6f',
      ERROR: '#b13f00',
    },
    // 错误消息映射表：将后端返回的英文错误码映射为前端展示的中文提示
    ERROR_MESSAGES: {
      'Invalid username or password': '用户名或密码不正确',
      'User not found': '用户不存在',
      'Account disabled': '账号已被禁用',
      'default': '登录失败，请稍后重试',
    },
    ICONS: {
      // 【安全说明】SVG 图标作为硬编码常量存储，通过 innerHTML 插入时免疫 XSS 攻击。
      // 严禁将后端或用户输入的数据拼接到此类 HTML 模板中。
      EYE_CLOSED: '<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" class="eye-icon"><path d="M469.333333 681.386667c-36.053333-2.432-71.253333-8.533333-104.96-17.92l-69.802666 149.674666a42.368 42.368 0 0 1-56.533334 20.266667 42.666667 42.666667 0 0 1-20.821333-56.32l66.986667-143.658667a451.712 451.712 0 0 1-148.906667-112.682666 388.693333 388.693333 0 0 1-70.570667-119.338667 42.666667 42.666667 0 1 1 80.128-29.354667 303.445333 303.445333 0 0 0 55.210667 93.098667C270.634667 547.413333 383.018667 597.333333 505.728 597.333333c122.752 0 235.136-49.962667 305.706667-132.181333a303.445333 303.445333 0 0 0 55.210666-93.098667 42.666667 42.666667 0 0 1 80.128 29.354667 388.693333 388.693333 0 0 1-70.570666 119.338667 423.68 423.68 0 0 1-18.773334 20.48l104.362667 104.362666a42.666667 42.666667 0 0 1-0.298667 60.032 42.368 42.368 0 0 1-60.032 0.298667l-109.653333-109.653333c-20.48 14.08-42.24 26.581333-65.024 37.418666l66.901333 143.36a42.666667 42.666667 0 0 1-20.821333 56.362667 42.368 42.368 0 0 1-56.533333-20.266667l-69.717334-149.546666a520.533333 520.533333 0 0 1-91.946666 16.810666v130.645334A42.666667 42.666667 0 0 1 512 853.333333c-23.722667 0-42.666667-18.944-42.666667-42.24v-129.706666z" fill="#3D3D3D"></path><path d="M176.128 524.373333a42.368 42.368 0 0 1 60.032 0.256 42.666667 42.666667 0 0 1 0.298667 60.074867l-121.216 121.216a42.368 42.368 0 0 1-60.074667-0.298667 42.666667 42.666667 0 0 1-0.298667-60.032l121.258667-121.258666z" fill="#3D3D3D"></path></svg>',
      EYE_OPEN: '<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" class="eye-icon"><path d="M518.826667 763.733333c-98.190222 0-177.777778-79.587556-177.777778-177.777777s79.587556-177.777778 177.777778-177.777778 177.777778 79.587556 177.777777 177.777778-79.587556 177.777778-177.777777 177.777777z m0-99.555555a78.222222 78.222222 0 1 0 0-156.444445 78.222222 78.222222 0 0 0 0 156.444445z" fill="#000000"></path><path d="M522.467556 814.520889c124.529778 0 249.287111-73.244444 374.357333-224.199111-109.155556-151.054222-233.244444-224.241778-374.357333-224.241778-141.255111 0-269.909333 73.329778-387.569778 224.284444 133.575111 150.798222 262.869333 224.156444 387.569778 224.156445z m373.063111-380.344889c36.750222 37.432889 71.68 81.038222 104.803555 130.744889l19.911111 29.880889-22.087111 28.330666C848.284444 815.317333 689.706667 914.062222 522.467556 914.062222c-166.684444 0-329.742222-98.176-489.571556-289.664L8.149333 594.773333l22.570667-31.331555c44.743111-62.122667 91.818667-114.673778 141.169778-157.482667l-84.337778-89.827555a35.555556 35.555556 0 1 1 51.84-48.668445l88.789333 94.577778c51.342222-35.726222 104.96-61.525333 160.768-77.226667l-43.079111-101.674666a35.555556 35.555556 0 1 1 65.479111-27.733334l48.739556 115.000889a499.527111 499.527111 0 0 1 62.378667-3.868444c36.508444 0 72.007111 3.882667 106.481777 11.619555l56.945778-125.297778a35.555556 35.555556 0 0 1 64.739556 29.44l-53.105778 116.821334c51.043556 19.911111 99.612444 48.938667 145.621333 86.897778l103.936-103.950223a35.555556 35.555556 0 0 1 50.289778 50.289778l-101.831111 101.831111z" fill="#000000"></path></svg>',
    },
  };

  /* ==========================================
   * 2. 状态与 DOM 缓存 (State & DOM Cache)
   * ========================================== */
  
  /** 页面运行时状态 */
  const state = {
    isPasswordVisible: false,
    isSubmitting: false, // 防止重复提交
  };

  /** 缓存所有需要频繁访问的 DOM 元素 */
  const el = {
    loginBtn: document.getElementById('loginBtn'),
    goRegisterBtn: document.getElementById('goRegisterBtn'),
    username: document.getElementById('username'),
    password: document.getElementById('password'),
    togglePasswordBtn: document.getElementById('togglePasswordBtn'),
    msg: document.getElementById('msg'),
  };

  /* ==========================================
   * 3. 工具函数 (Utilities)
   * ========================================== */

  /** 
   * 安全地更新提示消息 
   * 【安全说明】使用 textContent 防止 XSS，避免将后端返回的错误信息直接作为 HTML 渲染
   */
  function setMessage(message, type = 'info') {
    if (!el.msg) return;
    el.msg.textContent = message;
    el.msg.style.color = CONFIG.UI_COLORS[type.toUpperCase()] || CONFIG.UI_COLORS.INFO;
  }

  /** 获取本地化的错误消息 */
  function getLocalizedErrorMessage(err) {
    const rawMsg = err?.message || 'default';
    return CONFIG.ERROR_MESSAGES[rawMsg] || CONFIG.ERROR_MESSAGES['default'];
  }

  /* ==========================================
   * 4. 核心业务逻辑 (Core Business Logic)
   * ========================================== */

  /** 处理登录请求 */
  async function doLogin() {
    // 防止重复提交
    if (state.isSubmitting) return;

    const username = el.username?.value.trim();
    const password = el.password?.value;

    // 前端基础校验
    if (!username || !password) {
      setMessage('请输入用户名和密码', 'error');
      return;
    }

    state.isSubmitting = true;
    if (el.loginBtn) el.loginBtn.disabled = true;
    
    try {
      setMessage('登录中...', 'info');
      
      // 【安全说明】密码通过 HTTPS 传输，前端不应记录或打印明文密码
      const res = await api(CONFIG.API_PATHS.LOGIN, 'POST', { username, password }, false);
      
      Auth.set(res.token, res.username);
      setMessage('登录成功，正在跳转...', 'success');
      
      // 延迟跳转以确保用户能看到成功提示
      setTimeout(() => {
        window.location.href = CONFIG.ROUTES.DETECT;
      }, 500);
      
    } catch (err) {
      setMessage(getLocalizedErrorMessage(err), 'error');
    } finally {
      state.isSubmitting = false;
      if (el.loginBtn) el.loginBtn.disabled = false;
    }
  }

  /** 切换密码可见性 */
  function togglePasswordVisibility() {
    if (!el.password || !el.togglePasswordBtn) return;

    state.isPasswordVisible = !state.isPasswordVisible;
    
    // 更新输入框类型
    el.password.type = state.isPasswordVisible ? 'text' : 'password';
    
    // 更新图标
    el.togglePasswordBtn.innerHTML = state.isPasswordVisible 
      ? CONFIG.ICONS.EYE_OPEN 
      : CONFIG.ICONS.EYE_CLOSED;
      
    // 更新无障碍 (a11y) 属性
    el.togglePasswordBtn.setAttribute('aria-label', state.isPasswordVisible ? '隐藏密码' : '显示密码');
  }

  /* ==========================================
   * 5. 事件绑定与初始化 (Event Binding & Init)
   * ========================================== */

  function bindEvents() {
    // 登录按钮点击
    el.loginBtn?.addEventListener('click', doLogin);
    
    // 支持回车键提交表单
    el.password?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') doLogin();
    });

    // 跳转注册页
    el.goRegisterBtn?.addEventListener('click', () => {
      window.location.href = CONFIG.ROUTES.REGISTER;
    });

    // 密码可见性切换
    el.togglePasswordBtn?.addEventListener('click', togglePasswordVisibility);
  }

  function init() {
    // 【安全检测注释】
    // 前端路由守卫：如果已存在有效 Token，则直接跳转至检测页。
    // 注意：此处的 Token 校验仅基于本地存储，真正的有效性验证需依赖后端 API。
    if (Auth.token) {
      window.location.href = CONFIG.ROUTES.DETECT;
      return;
    }

    // 初始化密码切换按钮状态
    if (el.togglePasswordBtn) {
      el.togglePasswordBtn.innerHTML = CONFIG.ICONS.EYE_CLOSED;
      el.togglePasswordBtn.setAttribute('aria-label', '显示密码');
      el.togglePasswordBtn.setAttribute('role', 'button');
      el.togglePasswordBtn.setAttribute('tabindex', '0');
    }

    bindEvents();
  }

  // 启动应用
  init();

})(window.AppUtils);
