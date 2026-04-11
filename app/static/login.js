const loginBtn = document.getElementById('loginBtn');
const goRegisterBtn = document.getElementById('goRegisterBtn');
const usernameEl = document.getElementById('username');
const passwordEl = document.getElementById('password');
const togglePasswordBtn = document.getElementById('togglePasswordBtn');
const msgEl = document.getElementById('msg');

if (Auth.token) {
  window.location.href = '/detect';
}

function setMessage(text, type = 'normal') {
  msgEl.style.color = type === 'error' ? '#b13f00' : '#0a7f6f';
  msgEl.textContent = text;
}

function validateForm() {
  const username = usernameEl.value.trim();
  const password = passwordEl.value;
  if (!username || !password) {
    throw new Error('用户名和密码不能为空');
  }
  return { username, password };
}

async function doLogin() {
  try {
    setMessage('登录中...');
    const { username, password } = validateForm();
    const res = await api('/api/login', 'POST', { username, password }, false);
    Auth.set(res.token, res.username);
    setMessage('登录成功，正在跳转...', 'success');
    window.location.href = '/detect';
  } catch (err) {
    setMessage(err.message === 'Invalid username or password' ? '用户名或密码不正确' : err.message, 'error');
  }
}

togglePasswordBtn?.addEventListener('click', () => {
  const hidden = passwordEl.type === 'password';
  passwordEl.type = hidden ? 'text' : 'password';
  togglePasswordBtn.setAttribute('aria-pressed', String(hidden));
});

loginBtn.addEventListener('click', doLogin);
goRegisterBtn.addEventListener('click', () => {
  window.location.href = '/register';
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    if (document.activeElement === usernameEl || document.activeElement === passwordEl) {
      doLogin();
    }
  }
});
