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
let selectedHistoryId = null;
let selectedHistoryRow = null;

if (!requireLogin()) {
  throw new Error('未登录');
}

mountUserInfo(currentUserEl);

if (logoutBtn) {
  logoutBtn.addEventListener('click', () => {
    Auth.clear();
    window.location.href = '/login';
  });
}

if (goDetectBtn) {
  goDetectBtn.addEventListener('click', () => {
    window.location.href = '/detect';
  });
}

function renderWordHighlight(words) {
  if (!detailWords) {
    return;
  }
  if (!words || !words.length) {
    detailWords.textContent = '暂无结果';
    return;
  }
  detailWords.innerHTML = words
    .map((w) => {
      const cls = w.label_id === 1 ? 'aigt' : 'hwt';
      return `<span class="word ${cls}" title="${w.label} | 置信度 ${w.confidence}">${escapeHtml(w.token)}</span>`;
    })
    .join(' ');
}

function renderSentences(sentences) {
  if (!detailSentences) {
    return;
  }
  if (!sentences || !sentences.length) {
    detailSentences.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }

  detailSentences.innerHTML = sentences
    .map((s) => {
      const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
      return `
        <div class="sentence-item ${cls}">
          <div><strong>句子 ${s.index + 1}</strong> | 标签: ${s.label} | 置信度: ${s.confidence}</div>
          <div>${escapeHtml(s.text)}</div>
        </div>
      `;
    })
    .join('');
}

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

function sanitizeExportResult(result) {
  const words = Array.isArray(result?.words)
    ? result.words.map((word) => ({
      ...word,
      confidence: undefined,
    }))
    : [];
  const sentences = Array.isArray(result?.sentences) ? result.sentences : [];

  return {
    ...result,
    words,
    sentences,
  };
}

function buildExportData() {
  if (!selectedHistoryRow) {
    return null;
  }

  return {
    type: 'history',
    record_id: selectedHistoryRow.id,
    created_at: selectedHistoryRow.created_at,
    created_at_local: formatDateTime(selectedHistoryRow.created_at),
    input_text: selectedHistoryRow.input_text || '',
    result: sanitizeExportResult(selectedHistoryRow.result || {}),
    exported_at: new Date().toISOString(),
    exported_at_local: formatExportDateTime(new Date()),
  };
}

function buildExportText() {
  const data = buildExportData();
  if (!data) {
    return '';
  }

  const words = Array.isArray(data.result?.words) ? data.result.words : [];
  const sentences = Array.isArray(data.result?.sentences) ? data.result.sentences : [];

  const wordLines = words.length
    ? words.map((word, index) => {
      const isAi = Number(word.label_id) === 1 || String(word.label || '').toUpperCase() === 'AIGT';
      const label = isAi ? 'AIGT' : 'HWT';
      return `${index + 1}. ${String(word.token ?? '')}\t${label}`;
    }).join('\n')
    : '暂无结果';

  const sentenceLines = sentences.length
    ? sentences.map((sentence, index) => {
      const confidence = sentence.confidence ?? '-';
      return `${index + 1}. ${sentence.label}\t${confidence}\t${String(sentence.text ?? '')}`;
    }).join('\n')
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

function exportHistoryResult() {
  if (!selectedHistoryRow) {
    return;
  }

  const timeTag = formatExportFileTime(new Date(selectedHistoryRow.created_at || Date.now()));
  if (currentHistoryExportFormat === 'json') {
    const filename = `history_result_${selectedHistoryRow.id}_${timeTag}.json`;
    downloadTextFile(filename, `${JSON.stringify(buildExportData(), null, 2)}\n`, 'application/json;charset=utf-8');
    return;
  }

  const filename = `history_result_${selectedHistoryRow.id}_${timeTag}.txt`;
  downloadTextFile(filename, buildExportText(), 'text/plain;charset=utf-8');
}

let currentHistoryExportFormat = 'txt';

function openHistoryExportMenu() {
  if (!exportHistoryMenu || exportHistoryBtn.disabled) {
    return;
  }
  const isHidden = exportHistoryMenu.classList.toggle('hidden');
  exportHistoryMenu.setAttribute('aria-hidden', String(isHidden));
}

function chooseHistoryExportFormat(format) {
  currentHistoryExportFormat = format;
  exportHistoryMenu?.classList.add('hidden');
  exportHistoryMenu?.setAttribute('aria-hidden', 'true');
  exportHistoryResult();
}

function updateHistoryExportState() {
  if (!exportHistoryBtn) {
    return;
  }
  exportHistoryBtn.disabled = !selectedHistoryRow;
}

function parseCreatedAt(raw) {
  const text = String(raw || '');
  const normalized = text.replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1');
  const dt = new Date(normalized);
  if (Number.isNaN(dt.getTime())) {
    return new Date();
  }
  return dt;
}

function formatDay(raw) {
  const dt = parseCreatedAt(raw);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, '0');
  const d = String(dt.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function formatClock(raw) {
  const dt = parseCreatedAt(raw);
  const h = String(dt.getHours()).padStart(2, '0');
  const m = String(dt.getMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

function formatDateTime(raw) {
  const dt = parseCreatedAt(raw);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, '0');
  const d = String(dt.getDate()).padStart(2, '0');
  const h = String(dt.getHours()).padStart(2, '0');
  const min = String(dt.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${d} ${h}:${min}`;
}

function classifyByTime(rows) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const oneDay = 24 * 60 * 60 * 1000;

  const groups = {
    today: [],
    week: [],
    older: [],
  };

  rows.forEach((row) => {
    const dt = parseCreatedAt(row.created_at);
    const itemStart = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const dayDiff = Math.floor((todayStart - itemStart) / oneDay);

    if (dayDiff <= 0) {
      groups.today.push(row);
    } else if (dayDiff <= 7) {
      groups.week.push(row);
    } else {
      groups.older.push(row);
    }
  });

  return groups;
}

function renderGroup(title, rows) {
  if (!rows.length) {
    return `
      <section class="history-group">
        <h4 class="history-group-title">${title}</h4>
        <div class="muted">暂无记录</div>
      </section>
    `;
  }

  const items = rows
    .map((r) => {
      const preview = String(r.input_text || '').slice(0, 48);
      return `
        <article class="history-thumb" data-id="${r.id}">
          <div class="history-thumb-time">${formatClock(r.created_at)}</div>
          <div class="history-thumb-text">${escapeHtml(preview)}${String(r.input_text || '').length > 48 ? '...' : ''}</div>
          <div class="history-thumb-date muted">${formatDay(r.created_at)}</div>
        </article>
      `;
    })
    .join('');

  return `
    <section class="history-group">
      <h4 class="history-group-title">${title}</h4>
      <div class="history-thumb-list">${items}</div>
    </section>
  `;
}

function renderSidebarGroups(rows) {
  if (!historyList) {
    return;
  }
  const groups = classifyByTime(rows);
  historyList.innerHTML = [
    renderGroup('今日', groups.today),
    renderGroup('7天内', groups.week),
    renderGroup('更久', groups.older),
  ].join('');
}

function showDetailsById(itemId) {
  const row = historyRows.find((item) => Number(item.id) === Number(itemId));
  if (!row) {
    return;
  }

  selectedHistoryId = Number(row.id);
  selectedHistoryRow = row;

  if (detailTime) {
    detailTime.textContent = `时间：${formatDateTime(row.created_at)}`;
  }
  if (detailInput) {
    detailInput.textContent = String(row.input_text || '');
  }

  const result = row.result || {};
  renderWordHighlight(result.words || []);
  renderSentences(result.sentences || []);

  detailEmpty?.classList.add('hidden');
  detailPanel?.classList.remove('hidden');
  updateHistoryExportState();

  historyList?.querySelectorAll('.history-thumb').forEach((el) => {
    const isActive = Number(el.dataset.id) === selectedHistoryId;
    el.classList.toggle('active', isActive);
  });
}

async function loadHistory() {
  try {
    if (historyList) {
      historyList.innerHTML = '<div class="muted">加载中...</div>';
    }
    historyRows = await api('/api/history', 'GET', null, true);
    selectedHistoryId = null;

    if (!historyRows.length) {
      if (historyList) {
        historyList.innerHTML = '<div class="muted">暂无历史记录</div>';
      }
      selectedHistoryRow = null;
      updateHistoryExportState();
      detailPanel?.classList.add('hidden');
      detailEmpty?.classList.remove('hidden');
      if (detailEmpty) {
        detailEmpty.textContent = '暂无历史记录';
      }
      return;
    }

    detailEmpty?.classList.remove('hidden');
    if (detailEmpty) {
      detailEmpty.textContent = '点击左侧任意历史缩略查看详情';
    }
    detailPanel?.classList.add('hidden');
    selectedHistoryRow = null;
    updateHistoryExportState();

    renderSidebarGroups(historyRows);

    showDetailsById(historyRows[0].id);
  } catch (err) {
    const errMsg = typeof err === 'string'
      ? err
      : (err && typeof err.message === 'string' ? err.message : '请求失败');
    if (historyList) {
      historyList.innerHTML = `<div class="muted">加载失败: ${escapeHtml(errMsg)}</div>`;
    }
    if (String(errMsg).includes('请先登录')) {
      Auth.clear();
      window.location.href = '/login';
    }
  }
}

if (historyList) {
  historyList.addEventListener('click', (event) => {
    const item = event.target.closest('.history-thumb[data-id]');
    if (!item) {
      return;
    }
    showDetailsById(item.dataset.id);
  });
}

document.addEventListener('click', (event) => {
  if (!exportHistoryMenu || !exportHistoryBtn) {
    return;
  }
  if (exportHistoryMenu.classList.contains('hidden')) {
    return;
  }
  const target = event.target;
  if (target === exportHistoryMenu) {
    exportHistoryMenu.classList.add('hidden');
    exportHistoryMenu.setAttribute('aria-hidden', 'true');
    return;
  }
  if (target instanceof Node && (exportHistoryMenu.contains(target) || exportHistoryBtn.contains(target))) {
    return;
  }
  exportHistoryMenu.classList.add('hidden');
  exportHistoryMenu.setAttribute('aria-hidden', 'true');
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !exportHistoryMenu) {
    return;
  }
  if (exportHistoryMenu.classList.contains('hidden')) {
    return;
  }
  exportHistoryMenu.classList.add('hidden');
  exportHistoryMenu.setAttribute('aria-hidden', 'true');
});

if (sidebarToggleBtn && historyShell) {
  sidebarToggleBtn.addEventListener('click', () => {
    historyShell.classList.toggle('sidebar-collapsed');
    sidebarToggleBtn.textContent = historyShell.classList.contains('sidebar-collapsed') ? '展开边栏' : '收起边栏';
  });
}

if (clearHistoryBtn) {
  clearHistoryBtn.addEventListener('click', async () => {
    try {
      await api('/api/history', 'DELETE', null, true);
      await loadHistory();
    } catch (err) {
      const errMsg = typeof err === 'string'
        ? err
        : (err && typeof err.message === 'string' ? err.message : '请求失败');
      if (historyList) {
        historyList.innerHTML = `<div class="muted">清除失败: ${escapeHtml(errMsg)}</div>`;
      }
    }
  });
}

if (exportHistoryBtn) {
  exportHistoryBtn.addEventListener('click', openHistoryExportMenu);
  updateHistoryExportState();
}

if (exportHistoryTxtBtn) {
  exportHistoryTxtBtn.addEventListener('click', () => chooseHistoryExportFormat('txt'));
}

if (exportHistoryJsonBtn) {
  exportHistoryJsonBtn.addEventListener('click', () => chooseHistoryExportFormat('json'));
}

document.addEventListener('click', (event) => {
  if (!exportHistoryMenu || !exportHistoryBtn) {
    return;
  }
  if (exportHistoryMenu.classList.contains('hidden')) {
    return;
  }
  const target = event.target;
  if (target instanceof Node && (exportHistoryMenu.contains(target) || exportHistoryBtn.contains(target))) {
    return;
  }
  exportHistoryMenu.classList.add('hidden');
});

loadHistory();
