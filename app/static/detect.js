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

let currentDetectResult = null;
let currentDetectTime = null;
let currentExportFormat = 'txt';

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

function renderWordHighlight(words) {
  if (!wordHighlightContent) return;
  if (!words || !words.length) {
    wordHighlightContent.textContent = '暂无结果';
    return;
  }
  wordHighlightContent.innerHTML = words
    .map((w) => {
      const cls = w.label_id === 1 ? 'aigt' : 'hwt';
      return `<span class="word ${cls}" title="${escapeHtml(w.label)}">${escapeHtml(w.token)}</span>`;
    })
    .join(' ');
}

function renderSentences(sentences) {
  if (!sentenceList) return;
  if (!sentences || !sentences.length) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  sentenceList.innerHTML = sentences
    .map((s) => {
      const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
      return `
        <div class="sentence-item ${cls}">
          <div><strong>句子 ${s.index + 1}</strong> | 标签: ${escapeHtml(s.label)} | 置信度: ${escapeHtml(s.confidence)}</div>
          <div>${escapeHtml(s.text)}</div>
        </div>
      `;
    })
    .join('');
}

function buildExportData() {
  return {
    type: 'detect',
    exported_at: new Date().toISOString(),
    exported_at_local: formatExportDateTime(new Date()),
    input_text: inputText.value || '',
    result: currentDetectResult || {},
  };
}

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

function updateExportState() {
  if (!exportDetectBtn) return;
  exportDetectBtn.disabled = !currentDetectResult;
}

async function detectFileContent() {
  if (!fileInput?.files?.[0]) return;
  const file = fileInput.files[0];
  selectedFileName.textContent = file.name;
  selectedFileName.classList.add('visible');
  try {
    detectMsg.style.color = '#5f6c75';
    detectMsg.textContent = '正在读取文件，请稍候...';
    const formData = new FormData();
    formData.append('file', file);
    const res = await api('/api/extract-text', 'POST', formData, true);
    inputText.value = res.text || '';
    selectedFileName.textContent = res.filename || file.name;
    fileInfo.textContent = `已加载，共 ${res.length || inputText.value.length} 字符`;
    detectMsg.style.color = '#0a7f6f';
    detectMsg.textContent = '文件内容已载入，可直接开始检测';
  } catch (err) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = err.message || '文件读取失败';
    selectedFileName.textContent = '';
    selectedFileName.classList.remove('visible');
    fileInfo.textContent = '支持 .txt、.doc、.docx 文件';
  }
}

function toggleExportMenu() {
  if (!exportDetectMenu || !exportDetectBtn || exportDetectBtn.disabled) return;
  const isHidden = exportDetectMenu.classList.toggle('hidden');
  exportDetectMenu.setAttribute('aria-hidden', String(isHidden));
}

function closeExportMenu() {
  if (!exportDetectMenu) return;
  exportDetectMenu.classList.add('hidden');
  exportDetectMenu.setAttribute('aria-hidden', 'true');
}

function exportDetectResult(format) {
  if (!currentDetectResult) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = '请先完成检测后再导出';
    return;
  }
  currentExportFormat = format;
  closeExportMenu();
  const baseName = `detect_result_${formatExportFileTime(currentDetectTime || new Date())}`;

  if (format === 'json') {
    downloadTextFile(`${baseName}.json`, `${JSON.stringify(buildExportData(), null, 2)}\n`, 'application/json;charset=utf-8');
    return;
  }
  downloadTextFile(`${baseName}.txt`, buildExportText(), 'text/plain;charset=utf-8');
}

function renderDetection(words, sentences) {
  renderWordHighlight(words);
  renderSentences(sentences);
  currentDetectResult = { words, sentences };
  currentDetectTime = new Date();
  updateExportState();
}

async function detectText() {
  try {
    detectMsg.style.color = '#5f6c75';
    detectMsg.textContent = '检测中，请稍候...';
    const text = inputText.value.trim();
    if (!text) {
      throw new Error('请输入文本内容');
    }
    const res = await api('/api/detect', 'POST', { text }, true);
    renderDetection(res.result.words || [], res.result.sentences || []);
    detectMsg.style.color = '#0a7f6f';
    detectMsg.textContent = '检测完成';
  } catch (err) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = err.message;
  }
}

fileSelectBtn?.addEventListener('click', () => fileInput.click());
fileInput?.addEventListener('change', detectFileContent);
detectBtn?.addEventListener('click', detectText);
exportDetectBtn?.addEventListener('click', toggleExportMenu);
exportDetectTxtBtn?.addEventListener('click', () => exportDetectResult('txt'));
exportDetectJsonBtn?.addEventListener('click', () => exportDetectResult('json'));

document.addEventListener('click', (event) => {
  if (!exportDetectMenu || !exportDetectBtn) return;
  if (exportDetectMenu.classList.contains('hidden')) return;
  const target = event.target;
  if (target !== exportDetectMenu && !exportDetectMenu.contains(target) && target !== exportDetectBtn) {
    closeExportMenu();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeExportMenu();
  }
});
