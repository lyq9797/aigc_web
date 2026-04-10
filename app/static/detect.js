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

function formatExportFileTime(date) {
  const value = date instanceof Date ? date : new Date();
  const pad = (v) => String(v).padStart(2, '0');
  return `${value.getFullYear()}${pad(value.getMonth() + 1)}${pad(value.getDate())}_${pad(value.getHours())}${pad(value.getMinutes())}${pad(value.getSeconds())}`;
}

function downloadFile(name, data, mimeType) {
  const blob = new Blob([data], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function updateExportButtonState() {
  if (exportDetectBtn) {
    exportDetectBtn.disabled = !currentDetectResult;
  }
}

function renderWords(words) {
  if (!wordHighlightContent) return;
  if (!Array.isArray(words) || words.length === 0) {
    wordHighlightContent.textContent = '暂无结果';
    return;
  }
  wordHighlightContent.innerHTML = words
    .map((word) => `<span class="word ${word.label_id === 1 ? 'aigt' : 'hwt'}" title="${word.label}">${escapeHtml(word.token)}</span>`)
    .join(' ');
}

function renderSentenceList(sentences) {
  if (!sentenceList) return;
  if (!Array.isArray(sentences) || sentences.length === 0) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }
  sentenceList.innerHTML = sentences
    .map((sentence) => `
      <div class="sentence-item ${sentence.label === 'AIGT' ? 'aigt' : 'hwt'}">
        <div><strong>句子 ${sentence.index + 1}</strong> | ${escapeHtml(sentence.label)}</div>
        <div>${escapeHtml(sentence.text)}</div>
      </div>
    `)
    .join('');
}

async function detectText() {
  try {
    detectMsg.style.color = '#5f6c75';
    detectMsg.textContent = '检测中...';
    const text = inputText.value.trim();
    if (!text) {
      throw new Error('请输入文本内容');
    }
    const res = await api('/api/detect', 'POST', { text }, true);
    currentDetectResult = res.result;
    currentDetectTime = new Date();
    renderWords(currentDetectResult.words || []);
    renderSentenceList(currentDetectResult.sentences || []);
    detectMsg.style.color = '#0a7f6f';
    detectMsg.textContent = '检测完成';
    updateExportButtonState();
  } catch (err) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = err.message;
  }
}

function closeExportMenu() {
  if (!exportDetectMenu) return;
  exportDetectMenu.classList.add('hidden');
}

function openExportMenu() {
  if (!exportDetectMenu || !exportDetectBtn || exportDetectBtn.disabled) return;
  exportDetectMenu.classList.toggle('hidden');
}

function exportResult(format) {
  if (!currentDetectResult) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = '请先完成检测后再导出';
    return;
  }
  currentExportFormat = format;
  closeExportMenu();
  const fileTime = formatExportFileTime(currentDetectTime || new Date());
  const fileNameBase = `detect_result_${fileTime}`;
  const payload = {
    type: 'detect',
    exported_at: new Date().toISOString(),
    input_text: inputText.value,
    result: currentDetectResult,
  };

  if (format === 'json') {
    downloadFile(`${fileNameBase}.json`, `${JSON.stringify(payload, null, 2)}\n`, 'application/json;charset=utf-8');
    return;
  }

  const wordLines = Array.isArray(currentDetectResult.words)
    ? currentDetectResult.words.map((word, index) => `${index + 1}. ${word.token}\t${word.label || (word.label_id === 1 ? 'AIGT' : 'HWT')}`)
    : ['暂无结果'];
  const sentenceLines = Array.isArray(currentDetectResult.sentences)
    ? currentDetectResult.sentences.map((sentence, index) => `${index + 1}. ${sentence.label}\t${sentence.confidence ?? '-'}\t${sentence.text}`)
    : ['暂无结果'];

  const content = [
    'AI 文本检测结果',
    `导出时间：${formatExportDateTime(currentDetectTime || new Date())}`,
    '',
    '原始文本',
    inputText.value || '暂无内容',
    '',
    '单词级结果',
    '序号\t单词\t标签',
    ...wordLines,
    '',
    '句子级结果',
    '序号\t标签\t置信度\t文本',
    ...sentenceLines,
  ].join('\n');

  downloadFile(`${fileNameBase}.txt`, content, 'text/plain;charset=utf-8');
}

fileSelectBtn?.addEventListener('click', () => fileInput.click());
fileInput?.addEventListener('change', async () => {
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
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = err.message || '文件读取失败';
    selectedFileName.textContent = '';
    selectedFileName.classList.remove('visible');
    fileInfo.textContent = '支持 .txt、.doc、.docx 文件';
  }
});

detectBtn?.addEventListener('click', detectText);
exportDetectBtn?.addEventListener('click', openExportMenu);
exportDetectTxtBtn?.addEventListener('click', () => exportResult('txt'));
exportDetectJsonBtn?.addEventListener('click', () => exportResult('json'));

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
