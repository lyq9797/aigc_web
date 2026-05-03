// ============================================================================
// DOM Elements
// ============================================================================

const currentUserEl = document.getElementById('currentUser');
const logoutBtn = document.getElementById('logoutBtn');
const goHistoryBtn = document.getElementById('goHistoryBtn');
const fileInput = document.getElementById('fileInput');
const fileSelectBtn = document.getElementById('fileSelectBtn');
const selectedFileName = document.getElementById('selectedFileName');
const fileInfo = document.getElementById('fileInfo');
const sampleBtn = document.getElementById('sampleBtn');
const clearBtn = document.getElementById('clearBtn');
const detectBtn = document.getElementById('detectBtn');
const exportDetectBtn = document.getElementById('exportDetectBtn');
const inputText = document.getElementById('inputText');
const exportDetectMenu = document.getElementById('exportDetectMenu');
const exportDetectTxtBtn = document.getElementById('exportDetectTxtBtn');
const exportDetectJsonBtn = document.getElementById('exportDetectJsonBtn');
const detectMsg = document.getElementById('detectMsg');
const wordHighlightContent = document.getElementById('wordHighlightContent');
const sentenceList = document.getElementById('sentenceList');


// ============================================================================
// Module State
// ============================================================================

let currentDetectResult = null;      // 当前检测结果
let currentDetectTime = null;        // 当前检测时间
let currentExportFormat = 'txt';     // 当前导出格式
let isDetecting = false;             // 是否正在检测中


// ============================================================================
// Date/Time Utilities
// ============================================================================

/** 格式化导出时间（显示用） */
function formatExportDateTime(date) {
  const value = date instanceof Date ? date : new Date();
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  const h = String(value.getHours()).padStart(2, '0');
  const min = String(value.getMinutes()).padStart(2, '0');
  const s = String(value.getSeconds()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}:${s}`;
}

/** 格式化文件名时间戳 */
function formatExportFileTime(date) {
  const value = date instanceof Date ? date : new Date();
  const y = value.getFullYear();
  const m = String(value.getMonth() + 1).padStart(2, '0');
  const d = String(value.getDate()).padStart(2, '0');
  const h = String(value.getHours()).padStart(2, '0');
  const min = String(value.getMinutes()).padStart(2, '0');
  const s = String(value.getSeconds()).padStart(2, '0');
  return `${y}${m}${d}_${h}${min}${s}`;
}


// ============================================================================
// UI Helpers
// ============================================================================

/** 设置检测消息 */
function setDetectMessage(text, type = 'normal') {
  if (!detectMsg) return;
  detectMsg.textContent = text;
  const colors = { error: '#b13f00', success: '#0a7f6f', warning: '#e67e22', normal: '#5f6c75' };
  detectMsg.style.color = colors[type] || colors.normal;
}

/** 显示加载状态 */
function setLoading(loading) {
  isDetecting = loading;
  if (detectBtn) {
    detectBtn.disabled = loading;
    detectBtn.textContent = loading ? '检测中...' : '开始检测';
  }
}

/** 加载示例文本 */
function loadSampleText() {
  const sample = "人工智能技术正在快速发展，深度学习模型在自然语言处理领域取得了显著成果。然而，AI生成的内容检测仍然是一个具有挑战性的问题。研究人员正在开发更精确的检测方法来识别机器生成的文本。";
  if (inputText) {
    inputText.value = sample;
    setDetectMessage('示例文本已加载', 'success');
  }
}

/** 清除输入内容 */
function clearInputText() {
  if (inputText) {
    inputText.value = '';
    setDetectMessage('已清除', 'normal');
  }
  // 清空检测结果
  if (wordHighlightContent) {
    wordHighlightContent.innerHTML = '<div class="muted">暂无结果</div>';
  }
  if (sentenceList) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
  }
  currentDetectResult = null;
  updateExportState();
}


// ============================================================================
// File Export Utilities
// ============================================================================

/** 下载文本文件 */
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
  setDetectMessage(`已导出: ${filename}`, 'success');
}


// ============================================================================
// Rendering Functions
// ============================================================================

/** 渲染词级高亮 */
function renderWordHighlight(words) {
  if (!wordHighlightContent) return;
  if (!words || !words.length) {
    wordHighlightContent.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  wordHighlightContent.innerHTML = words
    .map((w) => {
      const cls = w.label_id === 1 ? 'aigt' : 'hwt';
      const label = w.label === 'AIGT' ? 'AI生成' : '人类写作';
      return `<span class="word ${cls}" title="${escapeHtml(label)}">${escapeHtml(w.token)}</span>`;
    })
    .join(' ');
}

/** 渲染句子级结果 */
function renderSentences(sentences) {
  if (!sentenceList) return;
  if (!sentences || !sentences.length) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  sentenceList.innerHTML = sentences
    .map((s) => {
      const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
      const confidencePercent = s.confidence ? (s.confidence * 100).toFixed(1) : '?';
      return `
        <div class="sentence-item ${cls}">
          <div class="sentence-header">
            <strong>句子 ${s.index + 1}</strong>
            <span class="sentence-label">标签: ${escapeHtml(s.label)}</span>
            <span class="sentence-confidence">置信度: ${confidencePercent}%</span>
          </div>
          <div class="sentence-text">${escapeHtml(s.text)}</div>
        </div>
      `;
    })
    .join('');
}

/** 渲染摘要信息 */
function renderSummary(summary) {
  if (!summary) return;
  const info = [];
  if (summary.processing_time_ms) info.push(`耗时 ${summary.processing_time_ms}ms`);
  if (summary.word_model) info.push(`词模型: ${summary.word_model}`);
  if (summary.sentence_model) info.push(`句模型: ${summary.sentence_model}`);
  if (info.length) {
    console.log('检测摘要:', info.join(' | '));
  }
}

/** 构建导出数据对象 */
function buildExportData() {
  return {
    type: 'detect',
    exported_at: new Date().toISOString(),
    exported_at_local: formatExportDateTime(new Date()),
    input_text: inputText?.value || '',
    result: currentDetectResult || {},
  };
}

/** 构建导出文本内容 */
function buildExportText() {
  const data = buildExportData();
  const words = Array.isArray(data.result.words) ? data.result.words : [];
  const sentences = Array.isArray(data.result.sentences) ? data.result.sentences : [];

  const wordLines = words.length
    ? words.map((word, index) => `${index + 1}. ${word.token}\t${word.label || (word.label_id === 1 ? 'AIGT' : 'HWT')}`).join('\n')
    : '暂无结果';

  const sentenceLines = sentences.length
    ? sentences.map((sentence, index) => `${index + 1}. ${sentence.label}\t${sentence.confidence ?? '-'}\t${sentence.text}`).join('\n')
    : '暂无结果';

  return [
    '=' .repeat(50),
    'AI 文本检测结果',
    '=' .repeat(50),
    `导出时间：${data.exported_at_local}`,
    '',
    '【原始文本】',
    data.input_text || '暂无内容',
    '',
    '【单词级结果】',
    '序号\t单词\t标签',
    wordLines,
    '',
    '【句子级结果】',
    '序号\t标签\t置信度\t文本',
    sentenceLines,
    '',
    '=' .repeat(50),
  ].join('\n');
}

/** 更新导出按钮状态 */
function updateExportState() {
  if (!exportDetectBtn) return;
  exportDetectBtn.disabled = !currentDetectResult;
}

/** 统一渲染检测结果 */
function renderDetection(words, sentences, summary = null) {
  renderWordHighlight(words);
  renderSentences(sentences);
  renderSummary(summary);
  currentDetectResult = { words, sentences, summary };
  currentDetectTime = new Date();
  updateExportState();
}


// ============================================================================
// File Processing
// ============================================================================

/** 从文件读取并载入文本 */
async function detectFileContent() {
  if (!fileInput?.files?.[0]) return;
  const file = fileInput.files[0];
  
  // 文件大小校验 (10MB)
  if (file.size > 10 * 1024 * 1024) {
    setDetectMessage('文件过大，请上传小于10MB的文件', 'error');
    return;
  }
  
  selectedFileName.textContent = file.name;
  selectedFileName.classList.add('visible');
  
  try {
    setDetectMessage('正在读取文件，请稍候...', 'normal');
    const formData = new FormData();
    formData.append('file', file);
    const res = await api('/api/extract-text', 'POST', formData, true);
    
    inputText.value = res.text || '';
    selectedFileName.textContent = res.filename || file.name;
    fileInfo.textContent = `已加载，共 ${res.length || inputText.value.length} 字符`;
    setDetectMessage('文件内容已载入，可直接开始检测', 'success');
  } catch (err) {
    setDetectMessage(err.message || '文件读取失败', 'error');
    selectedFileName.textContent = '';
    selectedFileName.classList.remove('visible');
    fileInfo.textContent = '支持 .txt、.doc、.docx 文件';
  }
}


// ============================================================================
// Export Menu
// ============================================================================

/** 切换导出菜单显隐 */
function toggleExportMenu() {
  if (!exportDetectMenu || !exportDetectBtn || exportDetectBtn.disabled) return;
  const isHidden = exportDetectMenu.classList.toggle('hidden');
  exportDetectMenu.setAttribute('aria-hidden', String(isHidden));
}

/** 关闭导出菜单 */
function closeExportMenu() {
  if (!exportDetectMenu) return;
  exportDetectMenu.classList.add('hidden');
  exportDetectMenu.setAttribute('aria-hidden', 'true');
}

/** 导出检测结果 */
function exportDetectResult(format) {
  if (!currentDetectResult) {
    setDetectMessage('请先完成检测后再导出', 'warning');
    return;
  }
  currentExportFormat = format;
  closeExportMenu();
  const baseName = `detect_result_${formatExportFileTime(currentDetectTime || new Date())}`;

  if (format === 'json') {
    downloadTextFile(`${baseName}.json`, JSON.stringify(buildExportData(), null, 2), 'application/json;charset=utf-8');
  } else {
    downloadTextFile(`${baseName}.txt`, buildExportText(), 'text/plain;charset=utf-8');
  }
}


// ============================================================================
// Text Detection
// ============================================================================

/** 执行文本检测 */
async function detectText() {
  if (isDetecting) {
    setDetectMessage('请等待上一次检测完成', 'warning');
    return;
  }
  
  try {
    setLoading(true);
    setDetectMessage('检测中，请稍候...', 'normal');
    
    const text = inputText.value.trim();
    if (!text) {
      throw new Error('请输入文本内容');
    }
    if (text.length > 10000) {
      throw new Error('文本长度超过限制（最大10000字符）');
    }
    
    const res = await api('/api/detect', 'POST', { text }, true);
    renderDetection(res.result.words || [], res.result.sentences || [], res.result.summary);
    setDetectMessage('检测完成', 'success');
  } catch (err) {
    setDetectMessage(err.message, 'error');
  } finally {
    setLoading(false);
  }
}


// ============================================================================
// Event Listeners
// ============================================================================

// 文件选择
fileSelectBtn?.addEventListener('click', () => fileInput.click());
fileInput?.addEventListener('change', detectFileContent);

// 检测相关
detectBtn?.addEventListener('click', detectText);
sampleBtn?.addEventListener('click', loadSampleText);
clearBtn?.addEventListener('click', clearInputText);

// 导出相关
exportDetectBtn?.addEventListener('click', toggleExportMenu);
exportDetectTxtBtn?.addEventListener('click', () => exportDetectResult('txt'));
exportDetectJsonBtn?.addEventListener('click', () => exportDetectResult('json'));

// 退出登录
logoutBtn?.addEventListener('click', () => {
  Auth.clear();
  window.location.href = '/login';
});

// 跳转历史
goHistoryBtn?.addEventListener('click', () => {
  window.location.href = '/history';
});

// 点击页面其他位置关闭导出菜单
document.addEventListener('click', (event) => {
  if (!exportDetectMenu || !exportDetectBtn) return;
  if (exportDetectMenu.classList.contains('hidden')) return;
  const target = event.target;
  if (target !== exportDetectMenu && !exportDetectMenu.contains(target) && target !== exportDetectBtn) {
    closeExportMenu();
  }
});

// ESC键关闭导出菜单
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeExportMenu();
  }
});

// Ctrl+Enter 快捷检测
inputText?.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    detectText();
  }
});


// ============================================================================
// Initialization
// ============================================================================

/** 页面初始化 */
function init() {
  // 检查登录状态
  if (!Auth.token) {
    window.location.href = '/login';
    return;
  }
  
  // 显示用户信息
  if (currentUserEl) {
    currentUserEl.textContent = `当前用户: ${Auth.username}`;
  }
  
  // 恢复草稿
  const draft = localStorage.getItem('aigc_detect_draft');
  if (draft && inputText && !inputText.value) {
    inputText.value = draft;
  }
  
  // 保存草稿
  inputText?.addEventListener('input', () => {
    localStorage.setItem('aigc_detect_draft', inputText.value);
  });
}

init();