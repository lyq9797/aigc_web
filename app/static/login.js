// ============================================================================
// DOM Elements
// ============================================================================

const loginBtn = document.getElementById('loginBtn');
const goRegisterBtn = document.getElementById('goRegisterBtn');

const usernameEl = document.getElementById('username');
const passwordEl = document.getElementById('password');

const togglePasswordBtn =
  document.getElementById('togglePasswordBtn');

const msgEl = document.getElementById('msg');


// ============================================================================
// Constants & State
// ============================================================================

const USERNAME_PATTERN =
  /^[a-zA-Z0-9_]{4,20}$/;

let loginInProgress = false;


// ============================================================================
// Initialization
// ============================================================================

document.addEventListener(
  'DOMContentLoaded',
  async () => {

    restoreLastUsername();

    await checkAuthStatus();
  }
);


// ============================================================================
// Authentication Check
// ============================================================================

/**
 * 检查当前Token是否有效
 * 有效则直接跳转到检测页面
 */
async function checkAuthStatus() {

  if (!Auth.token) return;

  try {

    await api(
      '/api/auth/verify',
      'GET'
    );

    window.location.href =
      '/detect';

  } catch {

    Auth.clear();
  }
}


// ============================================================================
// UI Helpers
// ============================================================================

/**
 * 设置提示消息
 *
 * @param {string} text
 * @param {'normal'|'success'|'error'} level
 */
function setMessage(
  text,
  level = 'normal'
) {

  const color =
    level === 'error'
      ? '#b13f00'
      : level === 'success'
      ? '#0a7f6f'
      : '#5f6c75';

  if (msgEl) {

    msgEl.style.color = color;

    msgEl.textContent = text;
  }
}

/**
 * 切换密码可见性
 */
function togglePasswordVisibility() {

  const isHidden =
    passwordEl.type === 'password';

  passwordEl.type =
    isHidden ? 'text' : 'password';

  if (togglePasswordBtn) {

    togglePasswordBtn.setAttribute(
      'aria-pressed',
      String(isHidden)
    );

    togglePasswordBtn.title =
      isHidden
        ? '隐藏密码'
        : '显示密码';
  }
}

/**
 * 恢复上次登录用户名
 */
function restoreLastUsername() {

  const username =
    localStorage.getItem(
      'last_username'
    );

  if (username) {

    usernameEl.value = username;
  }
}


// ============================================================================
// Validation
// ============================================================================

/**
 * 验证登录输入
 *
 * @returns {{
 *   username:string,
 *   password:string
 * }}
 */
function validateLoginInput() {

  const username =
    usernameEl.value.trim();

  const password =
    passwordEl.value;

  if (!username) {

    usernameEl.focus();

    throw new Error(
      '请输入用户名'
    );
  }

  if (
    !USERNAME_PATTERN.test(
      username
    )
  ) {

    usernameEl.focus();

    throw new Error(
      '用户名格式不正确'
    );
  }

  if (!password) {

    passwordEl.focus();

    throw new Error(
      '请输入密码'
    );
  }

  return {
    username,
    password
  };
}


// ============================================================================
// Login Logic
// ============================================================================

/**
 * 执行登录
 */
async function doLogin() {

  if (loginInProgress) {
    return;
  }

  loginInProgress = true;

  loginBtn.disabled = true;

  try {

    setMessage(
      '登录中...'
    );

    const {
      username,
      password
    } = validateLoginInput();

    const res = await api(
      '/api/login',
      'POST',
      {
        username,
        password
      },
      false
    );

    localStorage.setItem(
      'last_username',
      username
    );

    Auth.set(
      res.token,
      res.username
    );

    setMessage(
      '登录成功，正在跳转...',
      'success'
    );

    setTimeout(() => {

      window.location.href =
        '/detect';

    }, 500);

  } catch (err) {

    let errorMsg = err.message;

    if (
      err.message ===
      'Invalid username or password'
    ) {

      errorMsg =
        '用户名或密码不正确';
    }

    if (
      err.message.includes(
        'Network'
      )
    ) {

      errorMsg =
        '网络连接失败，请稍后重试';
    }

    setMessage(
      errorMsg,
      'error'
    );

  } finally {

    loginBtn.disabled = false;

    loginInProgress = false;
  }
}


// ============================================================================
// Event Listeners
// ============================================================================

togglePasswordBtn?.addEventListener(
  'click',
  togglePasswordVisibility
);

loginBtn?.addEventListener(
  'click',
  doLogin
);

goRegisterBtn?.addEventListener(
  'click',
  () => {

    window.location.href =
      '/register';
  }
);

/**
 * 回车提交登录
 */
document.addEventListener(
  'keydown',
  (event) => {

    if (
      event.key !== 'Enter'
    ) {
      return;
    }

    if (
      document.activeElement ===
        usernameEl ||
      document.activeElement ===
        passwordEl
    ) {

      event.preventDefault();

      doLogin();
    }
  }
);