const Auth = {
  get token() {
    return localStorage.getItem('aigc_token') || '';
  },
  get username() {
    return localStorage.getItem('aigc_user') || '';
  },
  set(token, username) {
    localStorage.setItem('aigc_token', token);
    localStorage.setItem('aigc_user', username);
  },
  clear() {
    localStorage.removeItem('aigc_token');
    localStorage.removeItem('aigc_user');
  },
};

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function api(path, method = 'GET', body = null, needAuth = false) {
  const headers = {};
  if (needAuth) {
    if (!Auth.token) {
      throw new Error('请先登录');
    }
    headers.Authorization = `Bearer ${Auth.token}`;
  }

  let requestBody = null;
  if (body instanceof FormData) {
    requestBody = body;
  } else if (body !== null && body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestBody = JSON.stringify(body);
  }

  const resp = await fetch(path, {
    method,
    headers,
    body: requestBody,
  });

  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const error = new Error(data.detail || '请求失败');
    error.detail = data.detail;
    throw error;
  }
  return data;
}

function requireLogin() {
  if (!Auth.token) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

function mountUserInfo(elUser, onLogout) {
  if (elUser) {
    elUser.textContent = `当前用户: ${Auth.username || '未知用户'}`;
  }
  if (typeof onLogout === 'function') {
    onLogout();
  }
}
