const registerBtn = document.getElementById('registerBtn');
const goLoginBtn = document.getElementById('goLoginBtn');
const regUsernameEl = document.getElementById('regUsername');
const regPasswordEl = document.getElementById('regPassword');
const regConfirmEl = document.getElementById('regConfirmPassword');
const regMsgEl = document.getElementById('regMsg');

if (Auth.token) {
  window.location.href = '/detect';
}

function setRegisterMessage(text, isError = false) {
  regMsgEl.style.color = isError ? '#b13f00' : '#0a7f6f';
  regMsgEl.textContent = text;
}

function validateRegisterInput() {
  const username = regUsernameEl.value.trim();
  const password = regPasswordEl.value;
  const confirm = regConfirmEl.value;
  if (!username || !password || !confirm) {
    throw new Error('请填写完整的注册信息');
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
    const { username, password } = validateRegisterInput();
    await api('/api/register', 'POST', { username, password }, false);
    setRegisterMessage('注册成功，3 秒后跳转到登录页...');
    setTimeout(() => {
      window.location.href = '/login';
    }, 3000);
  } catch (err) {
    setRegisterMessage(err.message, true);
  }
}

registerBtn.addEventListener('click', doRegister);
goLoginBtn.addEventListener('click', () => {
  window.location.href = '/login';
});
