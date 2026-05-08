// ============================================================================
// DOM Elements
// ============================================================================

const registerBtn = document.getElementById('registerBtn');
const goLoginBtn = document.getElementById('goLoginBtn');
const regUsernameEl = document.getElementById('regUsername');
const regPasswordEl = document.getElementById('regPassword');
const regConfirmEl = document.getElementById('regConfirmPassword');
const regMsgEl = document.getElementById('regMsg');
const togglePasswordBtn = document.getElementById('togglePasswordBtn');
const toggleConfirmBtn = document.getElementById('toggleConfirmPasswordBtn');


// ============================================================================
// Initialization
// ============================================================================

// 已登录用户直接跳转到检测页面
if (Auth.token) {
  window.location.href = '/detect';
}


// ============================================================================
// UI Helpers
// ============================================================================

/**
 * 设置注册页面提示消息
 * @param {string} text - 消息内容
 * @param {'normal'|'success'|'error'} style - 消息样式
 */
function setRegisterMessage(text, style = 'normal') {
  if (regMsgEl) {
    const colors = { error: '#b13f00', success: '#0a7f6f', warning: '#e67e22', normal: '#5f6c75' };
    regMsgEl.style.color = colors[style] || colors.normal;
    regMsgEl.textContent = text;
  }
}

/** 清除提示消息 */
function clearMessage() {
  if (regMsgEl) {
    regMsgEl.textContent = '';
  }
}

/** 显示加载状态 */
function setLoading(isLoading) {
  if (registerBtn) {
    registerBtn.disabled = isLoading;
    registerBtn.textContent = isLoading ? '注册中...' : '注册';
  }
}


// ============================================================================
// Password Visibility Toggle
// ============================================================================

/** 切换密码可见性 */
function togglePasswordVisibility(inputEl, buttonEl) {
  if (!inputEl || !buttonEl) return;
  const isHidden = inputEl.type === 'password';
  inputEl.type = isHidden ? 'text' : 'password';
  buttonEl.textContent = isHidden ? '🙈' : '👁️';
  buttonEl.setAttribute('aria-label', isHidden ? '隐藏密码' : '显示密码');
  buttonEl.setAttribute('title', isHidden ? '隐藏密码' : '显示密码');
}

/** 绑定密码切换事件 */
function bindPasswordToggle() {
  if (togglePasswordBtn && regPasswordEl) {
    togglePasswordBtn.addEventListener('click', () => togglePasswordVisibility(regPasswordEl, togglePasswordBtn));
  }
  if (toggleConfirmBtn && regConfirmEl) {
    toggleConfirmBtn.addEventListener('click', () => togglePasswordVisibility(regConfirmEl, toggleConfirmBtn));
  }
}


// ============================================================================
// Validation Functions
// ============================================================================

/** 验证用户名 */
function validateUsername(username) {
  if (!username) {
    throw new Error('请输入用户名');
  }
  if (username.length < 3) {
    throw new Error('用户名长度至少 3 位');
  }
  if (username.length > 50) {
    throw new Error('用户名长度不能超过 50 位');
  }
  if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username)) {
    throw new Error('用户名只能包含字母、数字、下划线或中文');
  }
  return username;
}

/** 验证密码 */
function validatePassword(password, confirm) {
  if (!password) {
    regPasswordEl.focus();
    throw new Error('请输入密码');
  }
  if (password.length < 6) {
    regPasswordEl.focus();
    throw new Error('密码长度至少 6 位');
  }
  if (password.length > 128) {
    regPasswordEl.focus();
    throw new Error('密码长度不能超过 128 位');
  }
  if (!confirm) {
    regConfirmEl.focus();
    throw new Error('请确认密码');
  }
  if (password !== confirm) {
    regConfirmEl.focus();
    throw new Error('两次密码输入不一致');
  }
  return password;
}

/**
 * 验证注册表单字段
 * @returns {{username: string, password: string}}
 * @throws {Error} 输入无效时抛出错误
 */
function validateRegisterFields() {
  const username = regUsernameEl.value.trim();
  const password = regPasswordEl.value;
  const confirm = regConfirmEl.value;
  
  validateUsername(username);
  validatePassword(password, confirm);
  
  return { username, password };
}


// ============================================================================
// Registration Logic
// ============================================================================

/** 执行注册 */
async function doRegister() {
  // 防止重复提交
  if (registerBtn.disabled) return;
  
  try {
    clearMessage();
    setLoading(true);
    setRegisterMessage('📝 注册中...');
    
    const { username, password } = validateRegisterFields();
    
    await api('/api/register', 'POST', { username, password }, false);
    
    setRegisterMessage('✅ 注册成功！3 秒后跳转到登录页...', 'success');
    
    // 保存用户名到 localStorage 方便登录页填充
    localStorage.setItem('aigc_registered_username', username);
    
    setTimeout(() => {
      window.location.href = '/login';
    }, 3000);
  } catch (err) {
    let errorMsg = err.message;
    // 处理特定错误
    if (err.message === 'Username already exists') {
      errorMsg = '❌ 用户名已存在，请换一个试试';
    }
    setRegisterMessage(errorMsg, 'error');
  } finally {
    setLoading(false);
  }
}

/** 重置表单 */
function resetForm() {
  if (regUsernameEl) regUsernameEl.value = '';
  if (regPasswordEl) regPasswordEl.value = '';
  if (regConfirmEl) regConfirmEl.value = '';
  clearMessage();
}


// ============================================================================
// Event Listeners
// ============================================================================

// 注册按钮
registerBtn?.addEventListener('click', doRegister);

// 跳转登录
goLoginBtn?.addEventListener('click', () => {
  window.location.href = '/login';
});

// 密码切换
bindPasswordToggle();

// 实时验证（可选，提升用户体验）
regUsernameEl?.addEventListener('input', () => {
  clearMessage();
});

regPasswordEl?.addEventListener('input', () => {
  clearMessage();
  // 实时提示密码强度
  const password = regPasswordEl.value;
  if (password && password.length < 6) {
    setRegisterMessage('⚠️ 密码长度至少 6 位', 'warning');
  } else if (password && password.length >= 6) {
    clearMessage();
  }
});

regConfirmEl?.addEventListener('input', () => {
  clearMessage();
  const password = regPasswordEl.value;
  const confirm = regConfirmEl.value;
  if (confirm && password !== confirm) {
    setRegisterMessage('⚠️ 两次密码输入不一致', 'warning');
  } else if (confirm && password === confirm) {
    setRegisterMessage('✓ 密码匹配', 'success');
  } else {
    clearMessage();
  }
});

// 回车键提交注册
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  if ([regUsernameEl, regPasswordEl, regConfirmEl].includes(document.activeElement)) {
    event.preventDefault();
    doRegister();
  }
});

// 页面卸载前清理定时器
let timeoutId = null;
window.addEventListener('beforeunload', () => {
  if (timeoutId) clearTimeout(timeoutId);
});