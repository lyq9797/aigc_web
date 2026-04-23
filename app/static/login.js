const loginBtn = document.getElementById('loginBtn');
const goRegisterBtn = document.getElementById('goRegisterBtn');
const usernameEl = document.getElementById('username');
const passwordEl = document.getElementById('password');
const togglePasswordBtn = document.getElementById('togglePasswordBtn');
const msgEl = document.getElementById('msg');

if (Auth.token) {
  window.location.href = '/detect';
}

function setMessage(text, level = 'normal') {
  const color = level === 'error' ? '#b13f00' : level === 'success' ? '#0a7f6f' : '#5f6c75';
  msgEl.style.color = color;
  msgEl.textContent = text;
}

function validateLoginInput() {
  const username = usernameEl.value.trim();
  const password = passwordEl.value;
  if (!username) {
    usernameEl.focus();
    throw new Error('请输入用户名');
  }
  if (!password) {
    passwordEl.focus();
    throw new Error('请输入密码');
  }
  return { username, password };
}

async function doLogin() {
  try {
    setMessage('登录中...');
    const { username, password } = validateLoginInput();
    const res = await api('/api/login', 'POST', { username, password }, false);
    Auth.set(res.token, res.username);
    setMessage('登录成功，正在跳转...', 'success');
    window.location.href = '/detect';
  } catch (err) {
    setMessage(err.message === 'Invalid username or password' ? '用户名或密码不正确' : err.message, 'error');
  }
}

function togglePasswordVisibility() {
  const isHidden = passwordEl.type === 'password';
  passwordEl.type = isHidden ? 'text' : 'password';
  togglePasswordBtn.setAttribute('aria-pressed', String(isHidden));
  togglePasswordBtn.title = isHidden ? '隐藏密码' : '显示密码';
}

togglePasswordBtn?.addEventListener('click', togglePasswordVisibility);
loginBtn.addEventListener('click', doLogin);
goRegisterBtn.addEventListener('click', () => {
  window.location.href = '/register';
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  if (document.activeElement === usernameEl || document.activeElement === passwordEl) {
    event.preventDefault();
    doLogin();
  }
});
