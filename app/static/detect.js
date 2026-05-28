/**
 * AI 文本检测系统 - 检测页面核心逻辑 (Detect Page Logic)
 * 
 * 【安全检测全局说明】
 * 1. 本文件包含文件上传、文本检测与结果渲染逻辑，需严格防范 XSS、CSRF 及恶意文件上传攻击。
 * 2. 前端文件校验仅为辅助，真正的文件类型与内容安全校验（如 Magic Number 检查、防病毒扫描）必须在后端完成。
 */
(function (AppUtils) {
  'use strict';

  // 校验公共模块是否加载
  if (!AppUtils || !AppUtils.api) {
    console.error('AppUtils 未加载，请确保 common.js 在 detect.js 之前引入');
    return;
  }

  const { Auth, api, escapeHtml, requireLogin } = AppUtils;

  /* ==========================================
   * 1. 常量与配置 (Constants & Configuration)
   * ========================================== */
  const CONFIG = {
    API_PATHS: {
      EXTRACT_TEXT: '/api/extract-text',
      DETECT: '/api/detect',
    },
    ROUTES: {
      LOGIN: '/login',
      HISTORY: '/history',
    },
    UI_COLORS: {
      SUCCESS: '#0a7f6f',
      ERROR: '#b13f00',
      INFO: '#5f6c75',
    },
    FILE_UPLOAD: {
      // 【安全说明】前端扩展名白名单仅用于提升 UX，后端必须校验 Magic Number 和 MIME 类型
      ALLOWED_EXTENSIONS: ['.txt', '.doc', '.docx'],
      MAX_SIZE_MB: 10, 
    },
    SAMPLE_TEXT: 'Running May Be Socially Contagious. They have also suggested that people may share and reinforce one another\'s political beliefs, religious views, or sexual identities. That question is at the heart of an important new study of exercise behavior, one of the first to use so-called big data culled from a large-scale, global social network of workout routines. The researchers focused on running, because so many of the network participants were runners. And what they found suggests that whether and how much we exercise can depend to a surprising extent on our responses to other people\'s training. The results also offer some practical advice for the runners among us, suggesting that if you wish to improve your performance, you might want to become virtual friends with people who are just a little bit slower than you are. "I am an atheist, but one of my friends is an agnostic," says Eric Anderson, a research Using data from surveys and postings on social media, scientists have reported that obesity, anxiety, weight loss and certain behaviors, including exercise routines, may be shared and intensified among friends.',
  };

  /* ==========================================
   * 2. 状态与 DOM 缓存 (State & DOM Cache)
   * ========================================== */
  
  /** 集中管理页面运行时状态 */
  const state = {
    currentResult: null,
    inputText: '',
    detectTime: null,
    exportFormat: 'txt',
  };

  /** 缓存所有需要频繁访问的 DOM 元素 */
  const el = {
    currentUser: document.getElementById('currentUser'),
    logoutBtn: document.getElementById('logoutBtn'),
    goHistoryBtn: document.getElementById('goHistoryBtn'),
    fileInput: document.getElementById('fileInput'),
    fileSelectBtn: document.getElementById('fileSelectBtn'),
    selectedFileName: document.getElementById('selectedFileName'),
    fileInfo: document.getElementById('fileInfo'),
    sampleBtn: document.getElementById('sampleBtn'),
    clearBtn: document.getElementById('clearBtn'),
    detectBtn: document.getElementById('detectBtn'),
    exportDetectBtn: document.getElementById('exportDetectBtn'),
    inputText: document.getElementById('inputText'),
    exportDetectMenu: document.getElementById('exportDetectMenu'),
    exportDetectTxtBtn: document.getElementById('exportDetectTxtBtn'),
    exportDetectJsonBtn: document.getElementById('exportDetectJsonBtn'),
    detectMsg: document.getElementById('detectMsg'),
    wordHighlightContent: document.getElementById('wordHighlightContent'),
    sentenceList: document.getElementById('sentenceList'),
  };

  /* ==========================================
   * 3. 工具函数 (Utilities)
   * ========================================== */

  /** 统一获取错误信息，兼容自定义 Error 对象和原生 Error */
  function getErrorMessage(err, fallback = '操作失败') {
    if (typeof err === 'string') return err;
    if (err && typeof err.message === 'string') return err.message;
    return fallback;
  }

  /** 安全地更新提示消息 */
  function setMessage(element, message, type = 'info') {
    if (!element) return;
    // 【安全说明】使用 textContent 防止 XSS
    element.textContent = message;
    element.style.color = CONFIG.UI_COLORS[type.toUpperCase()] || CONFIG.UI_COLORS.INFO;
  }

  /** 日期格式化：YYYY-MM-DD HH:mm:ss */
  function formatDateTime(date = new Date()) {
    const d = date instanceof Date ? date : new Date(date);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  /** 日期格式化：YYYYMMDD_HHmmss (用于文件名) */
  function formatFileTime(date = new Date()) {
    const d = date instanceof Date ? date : new Date(date);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
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

  /* ==========================================
   * 4. 导出功能逻辑 (Export Logic)
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
    return {
      type: 'detect',
      exported_at: new Date().toISOString(),
      exported_at_local: formatDateTime(),
      input_text: state.inputText,
      result: sanitizeExportResult(state.currentResult),
    };
  }

  function buildExportText() {
    const data = buildExportData();
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
    if (el.exportDetectBtn) {
      el.exportDetectBtn.disabled = !state.currentResult;
    }
  }

  function toggleExportMenu(forceHide = false) {
    if (!el.exportDetectMenu) return;
    const isHidden = forceHide ? true : el.exportDetectMenu.classList.toggle('hidden');
    el.exportDetectMenu.setAttribute('aria-hidden', String(isHidden));
  }

  function handleExport(format) {
    if (!state.currentResult) {
      setMessage(el.detectMsg, '请先完成检测后再导出', 'error');
      return;
    }
    
    const timeTag = formatFileTime(state.detectTime || new Date());
    const baseName = `detect_result_${timeTag}`;
    toggleExportMenu(true);

    if (format === 'json') {
      downloadTextFile(`${baseName}.json`, JSON.stringify(buildExportData(), null, 2) + '\n', 'application/json;charset=utf-8');
    } else {
      downloadTextFile(`${baseName}.txt`, buildExportText(), 'text/plain;charset=utf-8');
    }
  }

  /* ==========================================
   * 5. UI 渲染 (UI Rendering)
   * ========================================== */

  function renderWordHighlight(words) {
    if (!words || !words.length) {
      if (el.wordHighlightContent) el.wordHighlightContent.textContent = '暂无结果';
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

    if (el.wordHighlightContent) el.wordHighlightContent.innerHTML = html;
  }

  function renderSentences(sentences) {
    if (!sentences || !sentences.length) {
      if (el.sentenceList) el.sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
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
          <div class="sentence-meta">
            <strong class="sentence-meta-index">句子 ${(s.index ?? 0) + 1}</strong>
            <span class="sentence-meta-label">标签: ${safeLabel}</span>
            <span class="sentence-meta-confidence">置信度: ${safeConfidence}</span>
          </div>
          <div>${safeText}</div>
        </div>
      `;
    }).join('');

    if (el.sentenceList) el.sentenceList.innerHTML = html;
  }

  /* ==========================================
   * 6. 核心业务逻辑 (Core Business Logic)
   * ========================================== */

  async function handleFileUpload() {
    const file = el.fileInput?.files?.[0];
    if (!file) return;

    // 【安全说明】前端文件校验（扩展名与大小），作为后端校验的辅助防线
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!CONFIG.FILE_UPLOAD.ALLOWED_EXTENSIONS.includes(ext)) {
      setMessage(el.detectMsg, `不支持的文件格式，仅支持 ${CONFIG.FILE_UPLOAD.ALLOWED_EXTENSIONS.join(', ')}`, 'error');
      el.fileInput.value = '';
      return;
    }

    if (file.size > CONFIG.FILE_UPLOAD.MAX_SIZE_MB * 1024 * 1024) {
      setMessage(el.detectMsg, `文件过大，最大支持 ${CONFIG.FILE_UPLOAD.MAX_SIZE_MB}MB`, 'error');
      el.fileInput.value = '';
      return;
    }

    if (el.selectedFileName) {
      el.selectedFileName.textContent = file.name;
      el.selectedFileName.classList.add('visible');
    }

    try {
      setMessage(el.detectMsg, '正在读取文件，请稍候...', 'info');
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await api(CONFIG.API_PATHS.EXTRACT_TEXT, 'POST', formData, true);
      
      if (el.inputText) el.inputText.value = res.text || '';
      if (el.selectedFileName) el.selectedFileName.textContent = res.filename || file.name;
      if (el.fileInfo) el.fileInfo.textContent = `已加载，共 ${res.length || (res.text || '').length} 字符`;
      
      setMessage(el.detectMsg, '文件内容已载入，可直接开始检测', 'success');
    } catch (err) {
      setMessage(el.detectMsg, getErrorMessage(err, '文件读取失败'), 'error');
      if (el.selectedFileName) {
        el.selectedFileName.textContent = '';
        el.selectedFileName.classList.remove('visible');
      }
      if (el.fileInfo) el.fileInfo.textContent = `支持 ${CONFIG.FILE_UPLOAD.ALLOWED_EXTENSIONS.join('、')} 文件`;
    } finally {
      if (el.fileInput) el.fileInput.value = '';
    }
  }

  async function doDetect() {
    const text = el.inputText?.value.trim();
    if (!text) {
      setMessage(el.detectMsg, '请输入待检测文本', 'error');
      return;
    }

    try {
      setMessage(el.detectMsg, '检测中，请稍候...', 'info');
      const res = await api(CONFIG.API_PATHS.DETECT, 'POST', { text }, true);
      
      state.currentResult = res.result || null;
      state.inputText = text;
      state.detectTime = new Date();
      
      renderWordHighlight(res.result?.words || []);
      renderSentences(res.result?.sentences || []);
      updateExportBtnState();
      
      setMessage(el.detectMsg, '检测完成', 'success');
    } catch (err) {
      const errMsg = getErrorMessage(err, '请求失败');
      setMessage(el.detectMsg, errMsg, 'error');
      
      // 若 Token 失效，自动登出
      if (errMsg.includes('请先登录') || errMsg.includes('会话已过期')) {
        Auth.clear();
        window.location.href = CONFIG.ROUTES.LOGIN;
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
    el.goHistoryBtn?.addEventListener('click', () => {
      window.location.href = CONFIG.ROUTES.HISTORY;
    });

    // 文件上传
    el.fileSelectBtn?.addEventListener('click', () => el.fileInput?.click());
    el.fileInput?.addEventListener('change', handleFileUpload);

    // 文本操作
    el.sampleBtn?.addEventListener('click', () => {
      if (el.inputText) el.inputText.value = CONFIG.SAMPLE_TEXT;
    });
    
    el.clearBtn?.addEventListener('click', () => {
      if (el.inputText) el.inputText.value = '';
      state.currentResult = null;
      state.inputText = '';
      state.detectTime = null;
      
      if (el.wordHighlightContent) el.wordHighlightContent.textContent = '暂无结果';
      if (el.sentenceList) el.sentenceList.innerHTML = '';
      if (el.detectMsg) el.detectMsg.textContent = '';
      
      if (el.selectedFileName) {
        el.selectedFileName.textContent = '';
        el.selectedFileName.classList.remove('visible');
      }
      if (el.fileInfo) el.fileInfo.textContent = `支持 ${CONFIG.FILE_UPLOAD.ALLOWED_EXTENSIONS.join('、')} 文件`;
      
      updateExportBtnState();
    });

    // 检测与导出
    el.detectBtn?.addEventListener('click', doDetect);
    
    el.exportDetectBtn?.addEventListener('click', () => {
      if (!el.exportDetectBtn.disabled) toggleExportMenu();
    });
    el.exportDetectTxtBtn?.addEventListener('click', () => handleExport('txt'));
    el.exportDetectJsonBtn?.addEventListener('click', () => handleExport('json'));

    // 全局点击关闭导出菜单
    document.addEventListener('click', (event) => {
      if (!el.exportDetectMenu || el.exportDetectMenu.classList.contains('hidden')) return;
      
      const target = event.target;
      if (target === el.exportDetectMenu || 
          (target instanceof Node && (el.exportDetectMenu.contains(target) || el.exportDetectBtn?.contains(target)))) {
        return;
      }
      toggleExportMenu(true);
    });

    // ESC 键关闭导出菜单 (无障碍支持)
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && el.exportDetectMenu && !el.exportDetectMenu.classList.contains('hidden')) {
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
  }

  // 启动应用
  init();

})(window.AppUtils);
// ============================================
// 补充说明：detect.js 前端逻辑维护
// 提交日期标识：2026.3.2
// 脚本执行时间：2026-05-28 13:16:28
// ============================================

// ============================================
// 补充说明：detect.js 前端逻辑维护
// 提交日期标识：2026.3.3
// 脚本执行时间：2026-05-28 13:17:05
// ============================================

// ============================================
// 补充说明：detect.js 前端逻辑维护
// 提交日期标识：2026.3.6
// 脚本执行时间：2026-05-28 13:17:41
// ============================================

// ============================================
// 补充说明：detect.js 前端逻辑维护
// 提交日期标识：2026.3.7
// 脚本执行时间：2026-05-28 13:18:16
// ============================================
