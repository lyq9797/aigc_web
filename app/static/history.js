// ============================================================================
// DOM Elements
// ============================================================================

const currentUserEl = document.getElementById('currentUser');
const logoutBtn = document.getElementById('logoutBtn');
const goDetectBtn = document.getElementById('goDetectBtn');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
const historyShell = document.getElementById('historyShell');
const historyList = document.getElementById('historyList');
const detailEmpty = document.getElementById('detailEmpty');
const detailPanel = document.getElementById('detailPanel');
const detailTime = document.getElementById('detailTime');
const detailInput = document.getElementById('detailInput');
const detailWords = document.getElementById('detailWords');
const detailSentences = document.getElementById('detailSentences');
const exportHistoryBtn = document.getElementById('exportHistoryBtn');
const exportHistoryMenu = document.getElementById('exportHistoryMenu');
const exportHistoryTxtBtn = document.getElementById('exportHistoryTxtBtn');
const exportHistoryJsonBtn = document.getElementById('exportHistoryJsonBtn');


// ============================================================================
// Module State
// ============================================================================

let historyRows = [];                // 历史记录列表
let selectedHistoryRow = null;       // 当前选中的记录
let currentHistoryExportFormat = 'txt';  // 当前导出格式
let isLoading = false;               // 加载状态


// ============================================================================
// Utility Functions
// ============================================================================

/** 转义HTML特殊字符 */
function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 解析日期字符串 */
function parseDate(raw) {
  const dt = new Date(raw);
  return Number.isNaN(dt.getTime()) ? new Date() : dt;
}

/** 格式化日期时间（显示用） */
function formatDateTime(raw) {
  const dt = parseDate(raw);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
}

/** 显示提示消息 */
function showMessage(message, type = 'info') {
  console.log(`[${type}] ${message}`);
  // 可以扩展为页面内提示
}


// ============================================================================
// Rendering Functions
// ============================================================================

/** 渲染单条历史记录缩略图 */
function renderHistoryItem(row) {
  const switchWord = Number(row.result?.summary?.switch_word_index || 0) + 1;
  const switchSentence = Number(row.result?.summary?.switch_sentence_index || 0) + 1;
  const textPreview = (row.input_text || '').slice(0, 100);
  const hasMore = (row.input_text || '').length > 100;
  
  return `
    <div class="history-thumb" data-id="${row.id}">
      <div class="history-thumb-time">📅 ${formatDateTime(row.created_at)}</div>
      <div class="history-thumb-switch">🔄 切换词位: ${switchWord} | 切换句位: ${switchSentence}</div>
      <div class="history-thumb-text">${escapeHtml(textPreview)}${hasMore ? '...' : ''}</div>
    </div>
  `;
}

/** 更新历史记录列表 */
function updateHistoryList(rows) {
  if (!historyList) return;
  
  if (!rows || rows.length === 0) {
    historyList.innerHTML = '<div class="muted">📭 暂无检测记录</div>';
    return;
  }
  
  historyList.innerHTML = rows.map(renderHistoryItem).join('');
}

/** 渲染详情面板 */
function renderDetail(row) {
  if (!row) {
    detailPanel?.classList.add('hidden');
    if (detailEmpty) detailEmpty.textContent = '✨ 请选择一条记录查看详情';
    return;
  }
  
  detailPanel?.classList.remove('hidden');
  if (detailEmpty) detailEmpty.textContent = '';
  if (detailTime) detailTime.textContent = `📅 ${formatDateTime(row.created_at)}`;
  if (detailInput) detailInput.textContent = row.input_text || '(无文本内容)';
  
  renderWords(row.result?.words || []);
  renderSentences(row.result?.sentences || []);
  updateExportState();
}

/** 渲染词级高亮 */
function renderWords(words) {
  if (!detailWords) return;
  
  if (!Array.isArray(words) || words.length === 0) {
    detailWords.innerHTML = '<div class="muted">暂无词级结果</div>';
    return;
  }
  
  detailWords.innerHTML = words
    .map((word) => {
      const cls = word.label_id === 1 ? 'aigt' : 'hwt';
      const label = word.label === 'AIGT' ? '🤖 AI生成' : '✍️ 人类写作';
      return `<span class="word ${cls}" title="${escapeHtml(label)}">${escapeHtml(word.token)}</span>`;
    })
    .join(' ');
}

/** 渲染句子级结果 */
function renderSentences(sentences) {
  if (!detailSentences) return;
  
  if (!Array.isArray(sentences) || sentences.length === 0) {
    detailSentences.innerHTML = '<div class="muted">暂无句子级结果</div>';
    return;
  }
  
  detailSentences.innerHTML = sentences
    .map((sentence) => {
      const cls = sentence.label === 'AIGT' ? 'aigt' : 'hwt';
      const labelIcon = sentence.label === 'AIGT' ? '🤖' : '✍️';
      const confidence = sentence.confidence ? (sentence.confidence * 100).toFixed(1) : '?';
      
      return `
        <div class="sentence-item ${cls}">
          <div class="sentence-header">
            <strong>📝 句子 ${sentence.index + 1}</strong>
            <span class="sentence-label">${labelIcon} ${escapeHtml(sentence.label)}</span>
            <span class="sentence-confidence">📊 置信度: ${confidence}%</span>
          </div>
          <div class="sentence-text">${escapeHtml(sentence.text)}</div>
        </div>
      `;
    })
    .join('');
}

/** 更新导出按钮状态 */
function updateExportState() {
  if (!exportHistoryBtn) return;
  exportHistoryBtn.disabled = !selectedHistoryRow;
  if (exportHistoryBtn.disabled) {
    exportHistoryBtn.title = '请先选择一条记录';
  } else {
    exportHistoryBtn.title = '导出检测结果';
  }
}


// ============================================================================
// UI Interaction
// ============================================================================

/** 切换侧边栏折叠状态 */
function toggleSidebar() {
  if (!historyShell) return;
  historyShell.classList.toggle('sidebar-collapsed');
  const isCollapsed = historyShell.classList.contains('sidebar-collapsed');
  if (sidebarToggleBtn) {
    sidebarToggleBtn.textContent = isCollapsed ? '展开边栏' : '收起边栏';
    sidebarToggleBtn.setAttribute('aria-expanded', String(!isCollapsed));
  }
}

/** 切换导出菜单显隐 */
function toggleExportMenu() {
  if (!exportHistoryMenu || exportHistoryBtn.disabled) return;
  const isHidden = exportHistoryMenu.classList.contains('hidden');
  exportHistoryMenu.classList.toggle('hidden');
  exportHistoryMenu.setAttribute('aria-hidden', String(!isHidden));
}

/** 关闭导出菜单 */
function closeExportMenu() {
  if (!exportHistoryMenu) return;
  exportHistoryMenu.classList.add('hidden');
  exportHistoryMenu.setAttribute('aria-hidden', 'true');
}

/** 导出历史记录 */
function exportHistory(format) {
  if (!selectedHistoryRow) {
    showMessage('请先选择要导出的记录', 'warning');
    return;
  }
  
  const row = selectedHistoryRow;
  const created = formatDateTime(row.created_at).replace(/[^0-9]/g, '_');
  const filenameBase = `history_result_${row.id}_${created}`;
  const payload = {
    type: 'history',
    record_id: row.id,
    created_at: row.created_at,
    input_text: row.input_text || '',
    result: row.result || {},
    exported_at: new Date().toISOString(),
    exported_at_local: formatDateTime(new Date()),
  };

  if (format === 'json') {
    downloadTextFile(`${filenameBase}.json`, JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
  } else {
    const words = Array.isArray(payload.result.words) ? payload.result.words : [];
    const sentences = Array.isArray(payload.result.sentences) ? payload.result.sentences : [];
    
    const content = [
      '=' .repeat(60),
      '🤖 AI 文本检测历史记录',
      '=' .repeat(60),
      `📋 记录 ID：${payload.record_id}`,
      `📅 创建时间：${formatDateTime(payload.created_at)}`,
      `⏱️ 导出时间：${formatDateTime(payload.exported_at)}`,
      '',
      '【原始文本】',
      payload.input_text || '暂无内容',
      '',
      '【单词级结果】',
      '序号\t单词\t标签',
      ...words.map((item, index) => `${index + 1}. ${item.token}\t${item.label || (item.label_id === 1 ? 'AIGT' : 'HWT')}`),
      '',
      '【句子级结果】',
      '序号\t标签\t置信度\t文本',
      ...sentences.map((item, index) => `${index + 1}. ${item.label}\t${item.confidence ?? '-'}\t${item.text}`),
      '',
      '=' .repeat(60),
    ].join('\n');
    
    downloadTextFile(`${filenameBase}.txt`, content, 'text/plain;charset=utf-8');
  }
  
  closeExportMenu();
  showMessage(`已导出记录 #${row.id}`, 'success');
}

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
}

/** 清空所有历史记录 */
async function clearAllHistory() {
  if (!confirm('⚠️ 确定要清空所有历史记录吗？此操作不可恢复！')) return;
  
  try {
    isLoading = true;
    if (clearHistoryBtn) {
      clearHistoryBtn.textContent = '清空中...';
      clearHistoryBtn.disabled = true;
    }
    
    const result = await api('/api/history', 'DELETE', null, true);
    showMessage(`已清空 ${result.deleted} 条记录`, 'success');
    
    // 刷新列表
    await loadHistory();
  } catch (error) {
    showMessage(error.message, 'error');
  } finally {
    isLoading = false;
    if (clearHistoryBtn) {
      clearHistoryBtn.textContent = '清除历史记录';
      clearHistoryBtn.disabled = false;
    }
  }
}


// ============================================================================
// Event Listeners
// ============================================================================

/** 历史记录列表点击事件 */
historyList?.addEventListener('click', (event) => {
  const item = event.target.closest('.history-thumb');
  if (!item) return;
  
  const id = Number(item.dataset.id);
  const found = historyRows.find((row) => row.id === id);
  if (!found) return;
  
  selectedHistoryRow = found;
  renderDetail(selectedHistoryRow);
  
  // 高亮选中项
  historyList.querySelectorAll('.history-thumb').forEach((node) => {
    node.classList.toggle('active', Number(node.dataset.id) === id);
  });
});

// 导出相关
exportHistoryBtn?.addEventListener('click', toggleExportMenu);
exportHistoryTxtBtn?.addEventListener('click', () => exportHistory('txt'));
exportHistoryJsonBtn?.addEventListener('click', () => exportHistory('json'));

// 侧边栏折叠
sidebarToggleBtn?.addEventListener('click', toggleSidebar);

// 清空历史
clearHistoryBtn?.addEventListener('click', clearAllHistory);

// 退出登录
logoutBtn?.addEventListener('click', () => {
  Auth.clear();
  window.location.href = '/login';
});

// 跳转检测页
goDetectBtn?.addEventListener('click', () => {
  window.location.href = '/detect';
});

// 点击其他位置关闭导出菜单
document.addEventListener('click', (event) => {
  if (!exportHistoryMenu || !exportHistoryBtn) return;
  if (exportHistoryMenu.classList.contains('hidden')) return;
  
  const target = event.target;
  if (target !== exportHistoryBtn && !exportHistoryMenu.contains(target)) {
    closeExportMenu();
  }
});

// ESC键关闭导出菜单
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeExportMenu();
  }
});


// ============================================================================
// Data Loading
// ============================================================================

/** 加载历史记录 */
async function loadHistory() {
  // 检查登录状态
  if (!Auth.token) {
    window.location.href = '/login';
    return;
  }
  
  // 显示用户信息
  if (currentUserEl) {
    currentUserEl.textContent = `👤 ${Auth.username}`;
  }
  
  try {
    isLoading = true;
    if (historyList) {
      historyList.innerHTML = '<div class="muted">⏳ 加载中...</div>';
    }
    
    const rows = await api('/api/history', 'GET', null, true);
    historyRows = rows || [];
    
    updateHistoryList(historyRows);
    
    if (historyRows.length > 0) {
      selectedHistoryRow = historyRows[0];
      renderDetail(selectedHistoryRow);
      // 高亮第一条
      const firstItem = historyList?.querySelector('.history-thumb');
      firstItem?.classList.add('active');
    } else {
      detailPanel?.classList.add('hidden');
      if (detailEmpty) detailEmpty.textContent = '📭 暂无检测记录，先去检测页面吧';
    }
  } catch (error) {
    console.error('加载历史失败:', error);
    if (historyList) {
      historyList.innerHTML = `<div class="muted">❌ 加载失败：${escapeHtml(error.message)}</div>`;
    }
  } finally {
    isLoading = false;
  }
}

// 启动
loadHistory();