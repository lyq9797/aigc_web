const registerBtn = document.getElementById('registerBtn');
const goLoginBtn = document.getElementById('goLoginBtn');
const regUsernameEl = document.getElementById('regUsername');
const regPasswordEl = document.getElementById('regPassword');
const regConfirmEl = document.getElementById('regConfirmPassword');
const regMsgEl = document.getElementById('regMsg');

if (Auth.token) {
  window.location.href = '/detect';
}

function setRegisterStatus(text, level = 'normal') {
  const color = level === 'error' ? '#b13f00' : level === 'success' ? '#0a7f6f' : '#5f6c75';
  regMsgEl.style.color = color;
  regMsgEl.textContent = text;
}

function validateRegisterForm() {
  const username = regUsernameEl.value.trim();
  const password = regPasswordEl.value;
  const confirm = regConfirmEl.value;
  if (!username) {
    regUsernameEl.focus();
    throw new Error('请输入用户名');
  }
  if (!password) {
    regPasswordEl.focus();
    throw new Error('请输入密码');
  }
  if (!confirm) {
    regConfirmEl.focus();
    throw new Error('请确认密码');
  }
  if (password !== confirm) {
    throw new Error('两次密码不一致');
  }
  if (password.length < 6) {
    throw new Error('密码长度至少 6 位');
  }
  return { username, password };
}

async function doRegister() {
  try {
    setRegisterStatus('注册中...');
    const { username, password } = validateRegisterForm();
    await api('/api/register', 'POST', { username, password }, false);
    setRegisterStatus('注册成功，3 秒后跳转到登录页...', 'success');
    setTimeout(() => {
      window.location.href = '/login';
    }, 3000);
  } catch (err) {
    setRegisterStatus(err.message, 'error');
  }
}

registerBtn.addEventListener('click', doRegister);
goLoginBtn.addEventListener('click', () => {
  window.location.href = '/login';
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (document.activeElement === regPasswordEl || document.activeElement === regConfirmEl || document.activeElement === regUsernameEl)) {
    event.preventDefault();
    doRegister();
  }
});
