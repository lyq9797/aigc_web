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
let currentDetectInputText = '';
let currentDetectTime = null;

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
  return {
    type: 'detect',
    exported_at: new Date().toISOString(),
    exported_at_local: formatExportDateTime(new Date()),
    input_text: currentDetectInputText,
    result: sanitizeExportResult(currentDetectResult),
  };
}

function buildExportText() {
  const data = buildExportData();
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

function exportDetectResult() {
  if (!currentDetectResult) {
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = '请先完成检测后再导出';
    return;
  }
  const timeTag = formatExportFileTime(currentDetectTime || new Date());
  const filenameBase = `detect_result_${timeTag}`;
  if (exportDetectMenu) {
    exportDetectMenu.classList.add('hidden');
    exportDetectMenu.setAttribute('aria-hidden', 'true');
  }
  if (currentExportFormat === 'json') {
    const filename = `${filenameBase}.json`;
    downloadTextFile(filename, `${JSON.stringify(buildExportData(), null, 2)}\n`, 'application/json;charset=utf-8');
    return;
  }

  const filename = `${filenameBase}.txt`;
  downloadTextFile(filename, buildExportText(), 'text/plain;charset=utf-8');
}

let currentExportFormat = 'txt';

function openDetectExportMenu() {
  if (!exportDetectMenu || exportDetectBtn.disabled) {
    return;
  }
  const isHidden = exportDetectMenu.classList.toggle('hidden');
  exportDetectMenu.setAttribute('aria-hidden', String(isHidden));
}

function chooseDetectExportFormat(format) {
  currentExportFormat = format;
  exportDetectMenu?.classList.add('hidden');
  exportDetectMenu?.setAttribute('aria-hidden', 'true');
  exportDetectResult();
}

if (exportDetectBtn) {
  exportDetectBtn.addEventListener('click', openDetectExportMenu);
  updateDetectExportState();
}

if (exportDetectTxtBtn) {
  exportDetectTxtBtn.addEventListener('click', () => chooseDetectExportFormat('txt'));
}

if (exportDetectJsonBtn) {
  exportDetectJsonBtn.addEventListener('click', () => chooseDetectExportFormat('json'));
}

document.addEventListener('click', (event) => {
  if (!exportDetectMenu || !exportDetectBtn) {
    return;
  }
  if (exportDetectMenu.classList.contains('hidden')) {
    return;
  }
  const target = event.target;
  if (target === exportDetectMenu) {
    exportDetectMenu.classList.add('hidden');
    exportDetectMenu.setAttribute('aria-hidden', 'true');
    return;
  }
  if (target instanceof Node && (exportDetectMenu.contains(target) || exportDetectBtn.contains(target))) {
    return;
  }
  exportDetectMenu.classList.add('hidden');
  exportDetectMenu.setAttribute('aria-hidden', 'true');
});

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !exportDetectMenu) {
    return;
  }
  if (exportDetectMenu.classList.contains('hidden')) {
    return;
  }
  exportDetectMenu.classList.add('hidden');
  exportDetectMenu.setAttribute('aria-hidden', 'true');
});

function updateDetectExportState() {
  if (!exportDetectBtn) {
    return;
  }
  exportDetectBtn.disabled = !currentDetectResult;
}

if (!requireLogin()) {
  throw new Error('未登录');
}

mountUserInfo(currentUserEl);

logoutBtn.addEventListener('click', () => {
  Auth.clear();
  window.location.href = '/login';
});

goHistoryBtn.addEventListener('click', () => {
  window.location.href = '/history';
});

fileSelectBtn.addEventListener('click', () => {
  fileInput.click();
});

fileInput.addEventListener('change', async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) {
    return;
  }

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
    const errMsg = typeof err === 'string'
      ? err
      : (err && typeof err.message === 'string' ? err.message : '文件读取失败');
    detectMsg.style.color = '#b13f00';
    detectMsg.textContent = errMsg;
    selectedFileName.textContent = '';
    selectedFileName.classList.remove('visible');
    fileInfo.textContent = '支持 .txt、.doc、.docx文件';
  } finally {
    fileInput.value = '';
  }
});

sampleBtn.addEventListener('click', () => {
  inputText.value = 'Running May Be Socially Contagious. They have also suggested that people may share and reinforce one another\'s political beliefs, religious views, or sexual identities. That question is at the heart of an important new study of exercise behavior, one of the first to use so-called big data culled from a large-scale, global social network of workout routines. The researchers focused on running, because so many of the network participants were runners. And what they found suggests that whether and how much we exercise can depend to a surprising extent on our responses to other people\'s training. The results also offer some practical advice for the runners among us, suggesting that if you wish to improve your performance, you might want to become virtual friends with people who are just a little bit slower than you are. "I am an atheist, but one of my friends is an agnostic," says Eric Anderson, a research Using data from surveys and postings on social media, scientists have reported that obesity, anxiety, weight loss and certain behaviors, including exercise routines, may be shared and intensified among friends.';
});

clearBtn.addEventListener('click', () => {
  inputText.value = '';
  currentDetectResult = null;
  currentDetectInputText = '';
  currentDetectTime = null;
  wordHighlightContent.textContent = '暂无结果';
  sentenceList.innerHTML = '';
  detectMsg.textContent = '';
  selectedFileName.textContent = '';
  selectedFileName.classList.remove('visible');
  fileInfo.textContent = '支持 .txt、.doc、.docx文件';
  updateDetectExportState();
});

function renderWordHighlight(words) {
  if (!words || !words.length) {
    wordHighlightContent.textContent = '暂无结果';
    return;
  }
  wordHighlightContent.innerHTML = words
    .map((w) => {
      const isAi = Number(w.label_id) === 1 || String(w.label || '').toUpperCase() === 'AIGT';
      const cls = isAi ? 'aigt' : 'hwt';
      const label = isAi ? 'AIGT' : 'HWT';
      const confidence = w.confidence ?? '-';
      return `<span class="word ${cls}" title="${label} | 置信度 ${confidence}">${escapeHtml(String(w.token ?? ''))}</span>`;
    })
    .join(' ');
}

function renderSentences(sentences) {
  if (!sentences || !sentences.length) {
    sentenceList.innerHTML = '<div class="muted">暂无结果</div>';
    return;
  }

  sentenceList.innerHTML = sentences
    .map((s) => {
      const cls = s.label === 'AIGT' ? 'aigt' : 'hwt';
      return `
        <div class="sentence-item ${cls}">
          <div class="sentence-meta">
            <strong class="sentence-meta-index">句子 ${s.index + 1}</strong>
            <span class="sentence-meta-label">标签: ${s.label}</span>
            <span class="sentence-meta-confidence">置信度: ${s.confidence}</span>
          </div>
          <div>${escapeHtml(s.text)}</div>
        </div>
      `;
    })
    .join('');
}

async function doDetect() {
  try {
    detectMsg.style.color = '#5f6c75';
    detectMsg.textContent = '检测中，请稍候...';

    const text = inputText.value.trim();
    if (!text) {
      detectMsg.style.color = '#b13f00';
      detectMsg.textContent = '请输入待检测文本';
      return;
    }

    const res = await api('/api/detect', 'POST', { text }, true);
    currentDetectResult = res.result || null;
    currentDetectInputText = text;
    currentDetectTime = new Date();
    renderWordHighlight(res.result.words || []);
    renderSentences(res.result.sentences || []);
    updateDetectExportState();

    detectMsg.style.color = '#0a7f6f';
    detectMsg.textContent = '检测完成';
  } catch (err) {
    detectMsg.style.color = '#b13f00';
    const errMsg = typeof err === 'string'
      ? err
      : (err && typeof err.message === 'string' ? err.message : '请求失败');
    detectMsg.textContent = errMsg;
    if (String(errMsg).includes('请先登录')) {
      Auth.clear();
      window.location.href = '/login';
    }
  }
}

detectBtn.addEventListener('click', doDetect);

updateDetectExportState();
