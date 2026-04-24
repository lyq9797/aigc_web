const registerBtn = document.getElementById('registerBtn');
const goLoginBtn = document.getElementById('goLoginBtn');
const regUsernameEl = document.getElementById('regUsername');
const regPasswordEl = document.getElementById('regPassword');
const regConfirmEl = document.getElementById('regConfirmPassword');
const regMsgEl = document.getElementById('regMsg');

if (Auth.token) {
  window.location.href = '/detect';
}

function setRegisterMessage(text, style = 'normal') {
  regMsgEl.style.color = style === 'error' ? '#b13f00' : style === 'success' ? '#0a7f6f' : '#5f6c75';
  regMsgEl.textContent = text;
}

function validateRegisterFields() {
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
    throw new Error('两次密码输入不一致');
  }
  if (password.length < 6) {
    throw new Error('密码长度至少 6 位');
  }
  return { username, password };
}

async function doRegister() {
  try {
    setRegisterMessage('注册中...');
    const { username, password } = validateRegisterFields();
    await api('/api/register', 'POST', { username, password }, false);
    setRegisterMessage('注册成功，3 秒后跳转到登录页...', 'success');
    setTimeout(() => {
      window.location.href = '/login';
    }, 3000);
  } catch (err) {
    setRegisterMessage(err.message, 'error');
  }
}

registerBtn.addEventListener('click', doRegister);
goLoginBtn.addEventListener('click', () => {
  window.location.href = '/login';
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  if ([regUsernameEl, regPasswordEl, regConfirmEl].includes(document.activeElement)) {
    event.preventDefault();
    doRegister();
  }
});
