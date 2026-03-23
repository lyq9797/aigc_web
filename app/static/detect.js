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

function updateExportState() {
  if (exportDetectBtn) {
    exportDetectBtn.disabled = !currentDetectResult;
  }
}

function renderWordHighlight(words) {
  if (!wordHighlightContent) return;
  if (!words || !words.length) {
    wordHighlightContent.textContent = '暂无结果';
    return;
  }
  wordHighlightContent.innerHTML = words
    .map((word) => `<span class="word ${word.label_id === 1 ? 'aigt' : 'hwt'}" title="${word.label}">${escapeHtml(word.token)}</span>`)
    .join(' ');
}

function renderSentences(sentences) {
  if (!sentenceList) return;
  if (!sentences || !sentences.length) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  sentenceList.innerHTML = sentences
    .map((sentence) => {
      const cls = sentence.label === 'AIGT' ? 'aigt' : 'hwt';
      return `<div class="sentence-item ${cls}"><div><strong>句子 ${sentence.index + 1}</strong> | ${sentence.label}</div><div>${escapeHtml(sentence.text)}</div></div>`;
    })
    .join('');
}

async function doDetect() {
  try {
    detectMsg.style.color = '#5f6c75';
    detectMsg.textContent = '检测中，请稍候...';
    const text = inputText.value.trim();
    const res = await api('/api/detect', 'POST', { text }, true);
    currentDetectResult = res.result;
    currentDetectTime = new Date();
    renderWordHighlight(currentDetectResult.words || []);
    renderSentences(currentDetectResult.sentences || []);
    detectMsg.style.color = '#0a7f6f';
    detectMsg.textContent = '检测完成';
    updateExportState();
  } catch (err) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = err.message;
  }
}

function openDetectExportMenu() {
  if (!exportDetectMenu || exportDetectBtn.disabled) {
    return;
  }
  exportDetectMenu.classList.toggle('hidden');
}

function chooseDetectExportFormat(format) {
  currentExportFormat = format;
  exportDetectMenu?.classList.add('hidden');
  exportDetectResult();
}

function exportDetectResult() {
  if (!currentDetectResult) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = '请先完成检测后再导出';
    return;
  }
  const filenameBase = `detect_result_${formatExportFileTime(currentDetectTime)}`;
  const payload = {
    type: 'detect',
    exported_at: new Date().toISOString(),
    exported_at_local: formatExportDateTime(new Date()),
    input_text: inputText.value,
    result: currentDetectResult,
  };
  if (currentExportFormat === 'json') {
    downloadTextFile(`${filenameBase}.json`, `${JSON.stringify(payload, null, 2)}\n`, 'application/json;charset=utf-8');
    return;
  }
  const prettyText = [
    'AI 文本检测结果',
    `导出时间：${payload.exported_at_local}`,
    '',
    '原始文本',
    payload.input_text || '暂无内容',
    '',
    '单词级结果',
    '序号\t单词\t标签',
    ...Array.isArray(currentDetectResult.words) ? currentDetectResult.words.map((word, index) => `${index + 1}. ${word.token}\t${word.label || (word.label_id === 1 ? 'AIGT' : 'HWT')}`) : ['暂无结果'],
    '',
    '句子级结果',
    '序号\t标签\t置信度\t文本',
    ...Array.isArray(currentDetectResult.sentences) ? currentDetectResult.sentences.map((sentence, index) => `${index + 1}. ${sentence.label}\t${sentence.confidence ?? '-'}\t${sentence.text}`) : ['暂无结果'],
  ].join('\n');
  downloadTextFile(`${filenameBase}.txt`, prettyText, 'text/plain;charset=utf-8');
}

fileSelectBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) return;
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
    const errMsg = err && err.message ? err.message : '文件读取失败';
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = errMsg;
    selectedFileName.textContent = '';
    selectedFileName.classList.remove('visible');
    fileInfo.textContent = '支持 .txt、.doc、.docx 文件';
  }
});

detectBtn?.addEventListener('click', doDetect);
exportDetectBtn?.addEventListener('click', openDetectExportMenu);
exportDetectTxtBtn?.addEventListener('click', () => chooseDetectExportFormat('txt'));
exportDetectJsonBtn?.addEventListener('click', () => chooseDetectExportFormat('json'));

document.addEventListener('click', (event) => {
  if (!exportDetectMenu || !exportDetectBtn) return;
  if (exportDetectMenu.classList.contains('hidden')) return;
  if (event.target !== exportDetectMenu && !exportDetectMenu.contains(event.target) && event.target !== exportDetectBtn) {
    exportDetectMenu.classList.add('hidden');
  }
});
