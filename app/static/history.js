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

let historyRows = [];
let selectedHistoryRow = null;
let currentExportFormat = 'txt';

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDateTime(raw) {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return String(raw || '未知时间');
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function renderWordHighlight(words) {
  if (!detailWords) return;
  detailWords.innerHTML = Array.isArray(words) && words.length
    ? words.map((w) => `<span class="word ${w.label_id === 1 ? 'aigt' : 'hwt'}" title="${escapeHtml(w.label)}">${escapeHtml(w.token)}</span>`).join(' ')
    : '暂无结果';
}

function renderSentences(sentences) {
  if (!detailSentences) return;
  detailSentences.innerHTML = Array.isArray(sentences) && sentences.length
    ? sentences.map((s) => `
      <div class="sentence-item ${s.label === 'AIGT' ? 'aigt' : 'hwt'}">
        <div><strong>句子 ${s.index + 1}</strong> | ${escapeHtml(s.label)} | ${escapeHtml(s.confidence)}</div>
        <div>${escapeHtml(s.text)}</div>
      </div>
    `).join('')
    : '<div class="muted">暂无结果</div>';
}

function updateHistoryList(rows) {
  if (!historyList) return;
  historyList.innerHTML = rows.map((row) => `
    <div class="history-thumb" data-id="${row.id}">
      <div class="history-thumb-time">${formatDateTime(row.created_at)}</div>
      <div class="history-thumb-text">${escapeHtml((row.input_text || '').slice(0, 100))}${(row.input_text || '').length > 100 ? '...' : ''}</div>
    </div>
  `).join('');
}

function selectHistory(id) {
  selectedHistoryRow = historyRows.find((item) => item.id === id) || null;
  if (!selectedHistoryRow) {
    detailPanel?.classList.add('hidden');
    detailEmpty.textContent = '请选择一条记录';
    return;
  }
  detailPanel?.classList.remove('hidden');
  detailEmpty.textContent = '';
  detailTime.textContent = formatDateTime(selectedHistoryRow.created_at);
  detailInput.textContent = selectedHistoryRow.input_text || '';
  renderWordHighlight(selectedHistoryRow.result?.words || []);
  renderSentences(selectedHistoryRow.result?.sentences || []);
  exportHistoryBtn.disabled = false;
}

function toggleSidebar() {
  if (!historyShell) return;
  historyShell.classList.toggle('sidebar-collapsed');
}

function toggleExportMenu() {
  if (!exportHistoryMenu || !exportHistoryBtn || exportHistoryBtn.disabled) return;
  exportHistoryMenu.classList.toggle('hidden');
}

function closeExportMenu() {
  exportHistoryMenu?.classList.add('hidden');
}

function exportHistory(format) {
  if (!selectedHistoryRow) return;
  const row = selectedHistoryRow;
  const timeTag = formatDateTime(row.created_at).replace(/[^0-9]/g, '_');
  const baseName = `history_result_${row.id}_${timeTag}`;
  const payload = {
    type: 'history',
    record_id: row.id,
    created_at: row.created_at,
    input_text: row.input_text || '',
    result: row.result || {},
    exported_at: new Date().toISOString(),
  };

  if (format === 'json') {
    downloadTextFile(`${baseName}.json`, `${JSON.stringify(payload, null, 2)}\n`, 'application/json;charset=utf-8');
  } else {
    const words = Array.isArray(payload.result.words) ? payload.result.words : [];
    const sentences = Array.isArray(payload.result.sentences) ? payload.result.sentences : [];
    const content = [
      'AI 文本检测历史记录',
      `记录 ID：${payload.record_id}`,
      `导出时间：${formatDateTime(payload.exported_at)}`,
      '',
      '原始文本',
      payload.input_text || '暂无内容',
      '',
      '单词级结果',
      '序号\t单词\t标签',
      ...words.map((item, index) => `${index + 1}. ${item.token}\t${item.label || (item.label_id === 1 ? 'AIGT' : 'HWT')}`),
      '',
      '句子级结果',
      '序号\t标签\t置信度\t文本',
      ...sentences.map((item, index) => `${index + 1}. ${item.label}\t${item.confidence ?? '-'}\t${item.text}`),
    ].join('\n');
    downloadTextFile(`${baseName}.txt`, content, 'text/plain;charset=utf-8');
  }
  closeExportMenu();
}

function downloadTextFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

historyList?.addEventListener('click', (event) => {
  const item = event.target.closest('.history-thumb');
  if (!item) return;
  const id = Number(item.dataset.id);
  selectHistory(id);
  historyList.querySelectorAll('.history-thumb').forEach((node) => node.classList.toggle('active', Number(node.dataset.id) === id));
});

exportHistoryBtn?.addEventListener('click', toggleExportMenu);
exportHistoryTxtBtn?.addEventListener('click', () => exportHistory('txt'));
exportHistoryJsonBtn?.addEventListener('click', () => exportHistory('json'));

document.addEventListener('click', (event) => {
  if (!exportHistoryMenu?.contains(event.target) && event.target !== exportHistoryBtn) {
    closeExportMenu();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeExportMenu();
  }
});

globalThis.loadHistory = function () {
  api('/api/history', 'GET', null, true)
    .then((rows) => {
      historyRows = rows;
      if (!rows || !rows.length) {
        historyList.innerHTML = '<div class="muted">暂无记录</div>';
        detailPanel?.classList.add('hidden');
        return;
      }
      updateHistoryList(rows);
      selectHistory(rows[0].id);
    })
    .catch((err) => {
      historyList.innerHTML = `<div class="muted">加载失败：${escapeHtml(err.message)}</div>`;
    });
};

loadHistory();
