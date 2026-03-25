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

function formatDateTime(raw) {
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    return String(raw || '未知时间');
  }
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')} ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function updateExportButtonState() {
  if (exportHistoryBtn) {
    exportHistoryBtn.disabled = !selectedHistoryRow;
  }
}

function renderWords(words) {
  if (!detailWords) return;
  if (!words || !words.length) {
    detailWords.textContent = '暂无结果';
    return;
  }
  detailWords.innerHTML = words
    .map((w) => `<span class="word ${w.label_id === 1 ? 'aigt' : 'hwt'}" title="${escapeHtml(w.label)}">${escapeHtml(w.token)}</span>`)
    .join(' ');
}

function renderSentences(sentences) {
  if (!detailSentences) return;
  if (!sentences || !sentences.length) {
    detailSentences.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  detailSentences.innerHTML = sentences
    .map((s) => `
      <div class="sentence-item ${s.label === 'AIGT' ? 'aigt' : 'hwt'}">
        <div><strong>句子 ${s.index + 1}</strong> | ${escapeHtml(s.label)} | ${escapeHtml(s.confidence)}</div>
        <div>${escapeHtml(s.text)}</div>
      </div>
    `)
    .join('');
}

function updateHistoryList(rows) {
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
    detailEmpty.textContent = '请选择一条历史记录';
    return;
  }
  detailPanel?.classList.remove('hidden');
  detailEmpty.textContent = '';
  detailTime.textContent = formatDateTime(selectedHistoryRow.created_at);
  detailInput.textContent = selectedHistoryRow.input_text || '';
  renderWords(selectedHistoryRow.result?.words || []);
  renderSentences(selectedHistoryRow.result?.sentences || []);
  updateExportButtonState();
}

function bindHistoryEvents() {
  historyList.addEventListener('click', (event) => {
    const row = event.target.closest('.history-thumb');
    if (!row) return;
    const id = Number(row.dataset.id);
    selectHistory(id);
    document.querySelectorAll('.history-thumb').forEach((item) => item.classList.toggle('active', Number(item.dataset.id) === id));
  });
  exportHistoryBtn?.addEventListener('click', () => {
    if (!selectedHistoryRow) return;
    exportHistory(selectedHistoryRow, currentExportFormat);
  });
  exportHistoryTxtBtn?.addEventListener('click', () => { currentExportFormat = 'txt'; exportHistory(selectedHistoryRow, currentExportFormat); });
  exportHistoryJsonBtn?.addEventListener('click', () => { currentExportFormat = 'json'; exportHistory(selectedHistoryRow, currentExportFormat); });
}

function exportHistory(row, format) {
  if (!row) return;
  const baseName = `history_result_${row.id}_${formatDateTime(row.created_at).replace(/[^0-9]/g, '_')}`;
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
    return;
  }
  const words = Array.isArray(payload.result.words) ? payload.result.words : [];
  const sentences = Array.isArray(payload.result.sentences) ? payload.result.sentences : [];
  const body = [
    'AI 文本检测历史记录',
    `ID：${payload.record_id}`,
    `创建时间：${formatDateTime(payload.created_at)}`,
    '',
    '原始文本',
    payload.input_text || '暂无内容',
    '',
    '单词级结果',
    '序号\t单词\t标签',
    ...words.map((word, index) => `${index + 1}. ${word.token}\t${word.label || (word.label_id === 1 ? 'AIGT' : 'HWT')}`),
    '',
    '句子级结果',
    '序号\t标签\t置信度\t文本',
    ...sentences.map((sentence, index) => `${index + 1}. ${sentence.label}\t${sentence.confidence ?? '-'}\t${sentence.text}`),
  ].join('\n');
  downloadTextFile(`${baseName}.txt`, body, 'text/plain;charset=utf-8');
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

function loadHistory() {
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
}

bindHistoryEvents();
loadHistory();
