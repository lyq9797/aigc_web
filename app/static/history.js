/**
 * AI 文本检测系统 - 历史记录页面核心逻辑 (History Page Logic)
 * 
 * 【安全检测全局说明】
 * 1. 本文件包含历史数据渲染与导出逻辑，需严格防范 DOM 型 XSS 与数据泄露。
 * 2. 所有来自后端的动态数据（包括 ID、标签、置信度、文本）在插入 DOM 前必须经过严格转义。
 */
(function (AppUtils) {
  'use strict';

  // 校验公共模块是否加载
  if (!AppUtils || !AppUtils.api) {
    console.error('AppUtils 未加载，请确保 common.js 在 history.js 之前引入');
    return;
  }

  const { Auth, api, escapeHtml, requireLogin } = AppUtils;

  /* ==========================================
   * 1. 常量与配置 (Constants & Configuration)
   * ========================================== */
  const CONFIG = {
    API_PATHS: {
      HISTORY: '/api/history',
    },
    ROUTES: {
      LOGIN: '/login',
      DETECT: '/detect',
    },
  };

  /* ==========================================
   * 2. 状态与 DOM 缓存 (State & DOM Cache)
   * ========================================== */
  
  /** 集中管理页面运行时状态 */
  const state = {
    rows: [],
    selectedId: null,
    selectedRow: null,
    exportFormat: 'txt',
  };

  /** 缓存所有需要频繁访问的 DOM 元素 */
  const el = {
    currentUser: document.getElementById('currentUser'),
    logoutBtn: document.getElementById('logoutBtn'),
    goDetectBtn: document.getElementById('goDetectBtn'),
    clearHistoryBtn: document.getElementById('clearHistoryBtn'),
    sidebarToggleBtn: document.getElementById('sidebarToggleBtn'),
    historyShell: document.getElementById('historyShell'),
    historyList: document.getElementById('historyList'),
    detailEmpty: document.getElementById('detailEmpty'),
    detailPanel: document.getElementById('detailPanel'),
    detailTime: document.getElementById('detailTime'),
    detailInput: document.getElementById('detailInput'),
    detailWords: document.getElementById('detailWords'),
    detailSentences: document.getElementById('detailSentences'),
    exportHistoryBtn: document.getElementById('exportHistoryBtn'),
    exportHistoryMenu: document.getElementById('exportHistoryMenu'),
    exportHistoryTxtBtn: document.getElementById('exportHistoryTxtBtn'),
    exportHistoryJsonBtn: document.getElementById('exportHistoryJsonBtn'),
  };

  /* ==========================================
   * 3. 工具函数 (Utilities)
   * ========================================== */

  /** 统一获取错误信息 */
  function getErrorMessage(err, fallback = '操作失败') {
    if (typeof err === 'string') return err;
    if (err && typeof err.message === 'string') return err.message;
    return fallback;
  }

  /** 触发浏览器文件下载 */
  function downloadTextFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  /** 解析日期字符串，兼容后端返回的各种格式 */
  function parseDate(raw) {
    if (!raw) return new Date();
    const text = String(raw).replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1');
    const dt = new Date(text);
    return Number.isNaN(dt.getTime()) ? new Date() : dt;
  }

  /** 日期格式化：YYYY-MM-DD HH:mm */
  function formatDateTime(raw) {
    const d = parseDate(raw);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  /** 日期格式化：YYYYMMDD_HHmmss (用于文件名) */
  function formatFileTime(raw) {
    const d = parseDate(raw);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  }

  /** 提取时间部分 HH:mm */
  function formatClock(raw) {
    const d = parseDate(raw);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }

  /** 提取日期部分 YYYY-MM-DD */
  function formatDay(raw) {
    const d = parseDate(raw);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  /* ==========================================
   * 4. UI 渲染 (UI Rendering)
   * ========================================== */

  function renderWordHighlight(words) {
    if (!el.detailWords) return;
    if (!words || !words.length) {
      el.detailWords.textContent = '暂无结果';
      return;
    }

    const html = words.map((w) => {
      const isAi = Number(w.label_id) === 1 || String(w.label || '').toUpperCase() === 'AIGT';
      const cls = isAi ? 'aigt' : 'hwt';
      const label = isAi ? 'AIGT' : 'HWT';
      const confidence = w.confidence ?? '-';
      
      // 【安全检测核心】对 title 属性内的动态数据进行转义，防止 HTML 属性注入 (Attribute Injection)
      const safeTitle = `${escapeHtml(label)} | 置信度 ${escapeHtml(String(confidence))}`;
      const safeToken = escapeHtml(String(w.token ?? ''));
      
      return `<span class="word ${cls}" title="${safeTitle}">${safeToken}</span>`;
    }).join(' ');

    el.detailWords.innerHTML = html;
  }

  function renderSentences(sentences) {
    if (!el.detailSentences) return;
    if (!sentences || !sentences.length) {
      el.detailSentences.innerHTML = '<div class="muted">暂无结果</div>';
      return;
    }

    const html = sentences.map((s) => {
      const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
      // 【安全检测核心】对标签和置信度进行转义，防止存储型 XSS 通过后端数据回显攻击
      const safeLabel = escapeHtml(String(s.label ?? ''));
      const safeConfidence = escapeHtml(String(s.confidence ?? '-'));
      const safeText = escapeHtml(String(s.text ?? ''));
      
      return `
        <div class="sentence-item ${cls}">
          <div><strong>句子 ${(s.index ?? 0) + 1}</strong> | 标签: ${safeLabel} | 置信度: ${safeConfidence}</div>
          <div>${safeText}</div>
        </div>
      `;
    }).join('');

    el.detailSentences.innerHTML = html;
  }

  /** 按时间对历史记录进行分组 */
  function classifyByTime(rows) {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const oneDay = 24 * 60 * 60 * 1000;

    const groups = { today: [], week: [], older: [] };

    rows.forEach((row) => {
      const dt = parseDate(row.created_at);
      const itemStart = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate()).getTime();
      const dayDiff = Math.floor((todayStart - itemStart) / oneDay);

      if (dayDiff <= 0) groups.today.push(row);
      else if (dayDiff <= 7) groups.week.push(row);
      else groups.older.push(row);
    });

    return groups;
  }

  function renderGroup(title, rows) {
    if (!rows.length) {
      return `
        <section class="history-group">
          <h4 class="history-group-title">${escapeHtml(title)}</h4>
          <div class="muted">暂无记录</div>
        </section>
      `;
    }

    const items = rows.map((r) => {
      const rawText = String(r.input_text || '');
      const preview = rawText.slice(0, 48);
      const hasMore = rawText.length > 48;
      
      // 【安全说明】对 data-id 进行转义，防止恶意 ID 导致属性注入
      const safeId = escapeHtml(String(r.id)); 
      
      return `
        <article class="history-thumb" data-id="${safeId}" tabindex="0" role="button" aria-label="查看记录 ${safeId}">
          <div class="history-thumb-time">${escapeHtml(formatClock(r.created_at))}</div>
          <div class="history-thumb-text">${escapeHtml(preview)}${hasMore ? '...' : ''}</div>
          <div class="history-thumb-date muted">${escapeHtml(formatDay(r.created_at))}</div>
        </article>
      `;
    }).join('');

    return `
      <section class="history-group">
        <h4 class="history-group-title">${escapeHtml(title)}</h4>
        <div class="history-thumb-list">${items}</div>
      </section>
    `;
  }

  function renderSidebarGroups(rows) {
    if (!el.historyList) return;
    const groups = classifyByTime(rows);
    el.historyList.innerHTML = [
      renderGroup('今日', groups.today),
      renderGroup('7天内', groups.week),
      renderGroup('更久', groups.older),
    ].join('');
  }

  /* ==========================================
   * 5. 导出功能逻辑 (Export Logic)
   * ========================================== */

  /** 清理导出数据，移除敏感或不必要的字段 */
  function sanitizeExportResult(result) {
    if (!result) return {};
    const words = Array.isArray(result.words)
      ? result.words.map((word) => ({ ...word, confidence: undefined }))
      : [];
    return { ...result, words, sentences: result.sentences || [] };
  }

  function buildExportData() {
    if (!state.selectedRow) return null;

    return {
      type: 'history',
      record_id: state.selectedRow.id,
      created_at: state.selectedRow.created_at,
      created_at_local: formatDateTime(state.selectedRow.created_at),
      input_text: state.selectedRow.input_text || '',
      result: sanitizeExportResult(state.selectedRow.result || {}),
      exported_at: new Date().toISOString(),
      exported_at_local: formatDateTime(new Date()),
    };
  }

  function buildExportText() {
    const data = buildExportData();
    if (!data) return '';

    const words = data.result?.words || [];
    const sentences = data.result?.sentences || [];

    const wordLines = words.length
      ? words.map((w, i) => {
          const isAi = Number(w.label_id) === 1 || String(w.label || '').toUpperCase() === 'AIGT';
          return `${i + 1}. ${String(w.token ?? '')}\t${isAi ? 'AIGT' : 'HWT'}`;
        }).join('\n')
      : '暂无结果';

    const sentenceLines = sentences.length
      ? sentences.map((s, i) => `${i + 1}. ${s.label}\t${s.confidence ?? '-'}\t${String(s.text ?? '')}`).join('\n')
      : '暂无结果';

    return [
      'AI 文本检测结果',
      `记录ID：${data.record_id}`,
      `原始时间：${data.created_at_local}`,
      `导出时间：${data.exported_at_local}`,
      '',
      '原始文本',
      data.input_text || '暂无内容',
      '',
      '单词级结果',
      '序号\t单词\t标签',
      wordLines,
      '',
      '句子级结果',
      '序号\t标签\t置信度\t文本',
      sentenceLines,
      '',
    ].join('\n');
  }

  function updateExportBtnState() {
    if (el.exportHistoryBtn) {
      el.exportHistoryBtn.disabled = !state.selectedRow;
    }
  }

  function toggleExportMenu(forceHide = false) {
    if (!el.exportHistoryMenu) return;
    const isHidden = forceHide ? true : el.exportHistoryMenu.classList.toggle('hidden');
    el.exportHistoryMenu.setAttribute('aria-hidden', String(isHidden));
  }

  function handleExport(format) {
    if (!state.selectedRow) return;
    
    const timeTag = formatFileTime(state.selectedRow.created_at || new Date());
    const baseName = `history_result_${state.selectedRow.id}_${timeTag}`;
    toggleExportMenu(true);

    if (format === 'json') {
      downloadTextFile(`${baseName}.json`, JSON.stringify(buildExportData(), null, 2) + '\n', 'application/json;charset=utf-8');
    } else {
      downloadTextFile(`${baseName}.txt`, buildExportText(), 'text/plain;charset=utf-8');
    }
  }

  /* ==========================================
   * 6. 核心业务逻辑 (Core Business Logic)
   * ========================================== */

  function showDetailsById(itemId) {
    const row = state.rows.find((item) => Number(item.id) === Number(itemId));
    if (!row) return;

    state.selectedId = Number(row.id);
    state.selectedRow = row;

    if (el.detailTime) el.detailTime.textContent = `时间：${formatDateTime(row.created_at)}`;
    // 【安全说明】使用 textContent 渲染原始文本，免疫 XSS
    if (el.detailInput) el.detailInput.textContent = String(row.input_text || '');

    const result = row.result || {};
    renderWordHighlight(result.words || []);
    renderSentences(result.sentences || []);

    el.detailEmpty?.classList.add('hidden');
    el.detailPanel?.classList.remove('hidden');
    updateExportBtnState();

    // 更新侧边栏激活状态
    el.historyList?.querySelectorAll('.history-thumb').forEach((thumb) => {
      const isActive = Number(thumb.dataset.id) === state.selectedId;
      thumb.classList.toggle('active', isActive);
      thumb.setAttribute('aria-selected', String(isActive));
    });
  }

  async function loadHistory() {
    try {
      if (el.historyList) el.historyList.innerHTML = '<div class="muted">加载中...</div>';
      
      state.rows = await api(CONFIG.API_PATHS.HISTORY, 'GET', null, true);
      state.selectedId = null;
      state.selectedRow = null;

      if (!state.rows.length) {
        if (el.historyList) el.historyList.innerHTML = '<div class="muted">暂无历史记录</div>';
        if (el.detailEmpty) {
          el.detailEmpty.textContent = '暂无历史记录';
          el.detailEmpty.classList.remove('hidden');
        }
        el.detailPanel?.classList.add('hidden');
        updateExportBtnState();
        return;
      }

      if (el.detailEmpty) {
        el.detailEmpty.textContent = '点击左侧任意历史缩略查看详情';
        el.detailEmpty.classList.remove('hidden');
      }
      el.detailPanel?.classList.add('hidden');
      updateExportBtnState();

      renderSidebarGroups(state.rows);
      showDetailsById(state.rows[0].id);
    } catch (err) {
      const errMsg = getErrorMessage(err, '请求失败');
      if (el.historyList) {
        // 【安全说明】使用 escapeHtml 处理错误信息，防止反射型 XSS
        el.historyList.innerHTML = `<div class="muted">加载失败: ${escapeHtml(errMsg)}</div>`;
      }
      
      // 若 Token 失效，自动登出
      if (errMsg.includes('请先登录') || errMsg.includes('会话已过期')) {
        Auth.clear();
        window.location.href = CONFIG.ROUTES.LOGIN;
      }
    }
  }

  async function clearHistory() {
    try {
      await api(CONFIG.API_PATHS.HISTORY, 'DELETE', null, true);
      await loadHistory();
    } catch (err) {
      const errMsg = getErrorMessage(err, '请求失败');
      if (el.historyList) {
        el.historyList.innerHTML = `<div class="muted">清除失败: ${escapeHtml(errMsg)}</div>`;
      }
    }
  }

  /* ==========================================
   * 7. 事件绑定与初始化 (Event Binding & Init)
   * ========================================== */

  function bindEvents() {
    // 导航与认证
    el.logoutBtn?.addEventListener('click', () => {
      Auth.clear();
      window.location.href = CONFIG.ROUTES.LOGIN;
    });
    el.goDetectBtn?.addEventListener('click', () => {
      window.location.href = CONFIG.ROUTES.DETECT;
    });

    // 历史记录列表点击 (事件委托)
    el.historyList?.addEventListener('click', (event) => {
      const item = event.target.closest('.history-thumb[data-id]');
      if (item) showDetailsById(item.dataset.id);
    });

    // 侧边栏折叠
    if (el.sidebarToggleBtn && el.historyShell) {
      el.sidebarToggleBtn.addEventListener('click', () => {
        const isCollapsed = el.historyShell.classList.toggle('sidebar-collapsed');
        el.sidebarToggleBtn.textContent = isCollapsed ? '展开边栏' : '收起边栏';
        el.sidebarToggleBtn.setAttribute('aria-expanded', String(!isCollapsed));
      });
    }

    // 清空历史
    el.clearHistoryBtn?.addEventListener('click', clearHistory);

    // 导出菜单交互
    el.exportHistoryBtn?.addEventListener('click', () => {
      if (!el.exportHistoryBtn.disabled) toggleExportMenu();
    });
    el.exportHistoryTxtBtn?.addEventListener('click', () => handleExport('txt'));
    el.exportHistoryJsonBtn?.addEventListener('click', () => handleExport('json'));

    // 全局点击关闭导出菜单 (已合并原代码中重复的监听器)
    document.addEventListener('click', (event) => {
      if (!el.exportHistoryMenu || el.exportHistoryMenu.classList.contains('hidden')) return;
      
      const target = event.target;
      if (target === el.exportHistoryMenu || 
          (target instanceof Node && (el.exportHistoryMenu.contains(target) || el.exportHistoryBtn?.contains(target)))) {
        return;
      }
      toggleExportMenu(true);
    });

    // ESC 键关闭导出菜单 (无障碍支持)
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && el.exportHistoryMenu && !el.exportHistoryMenu.classList.contains('hidden')) {
        toggleExportMenu(true);
      }
    });
  }

  function init() {
    // 【安全检测注释】前端路由守卫仅用于提升 UX，真正的鉴权必须在后端 API 网关层完成
    if (!requireLogin()) {
      throw new Error('未登录，拦截跳转');
    }

    // 挂载用户信息（假设 mountUserInfo 已在 common.js 中处理，此处直接渲染）
    if (el.currentUser) {
      el.currentUser.textContent = `当前用户: ${Auth.username || '未知用户'}`;
    }

    bindEvents();
    updateExportBtnState();
    loadHistory();
  }

  // 启动应用
  init();

})(window.AppUtils);
// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.3.2
// 脚本执行时间：2026-05-28 13:16:33
// ============================================

// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.3.3
// 脚本执行时间：2026-05-28 13:17:10
// ============================================

// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.3.6
// 脚本执行时间：2026-05-28 13:17:46
// ============================================

// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.3.7
// 脚本执行时间：2026-05-28 13:18:21
// ============================================

// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.4.17
// 脚本执行时间：2026-05-28 13:40:33
// ============================================

// ============================================
// 补充说明：history.js 前端逻辑维护
// 提交日期标识：2026.4.20
// 脚本执行时间：2026-05-28 13:41:38
// ============================================
