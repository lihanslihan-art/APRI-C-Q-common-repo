const DEFAULT_WORDS = [
  { word: '机密',              enabled: true, isDefault: true },
  { word: '保密',              enabled: true, isDefault: true },
  { word: '内部资料',          enabled: true, isDefault: true },
  { word: '绝密',              enabled: true, isDefault: true },
  { word: '涉密',              enabled: true, isDefault: true },
  { word: '不得外传',          enabled: true, isDefault: true },
  { word: '严禁转发',          enabled: true, isDefault: true },
  { word: 'confidential',      enabled: true, isDefault: true },
  { word: 'top secret',        enabled: true, isDefault: true },
  { word: 'internal only',     enabled: true, isDefault: true },
  { word: 'do not distribute', enabled: true, isDefault: true },
  { word: 'restricted',        enabled: true, isDefault: true },
];

let currentWords = [];
let settings = {
  autoScan: false, caseSensitive: false,
  contextLength: 50, highlightColor: '#e94560',
};

// ── Boot ──────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadData();
  initUI();
  await detectAndShowMode();
});

// ── Storage ───────────────────────────────────────────────────────────────
async function loadData() {
  const data = await chrome.storage.local.get(['words', 'settings']);
  currentWords = data.words || JSON.parse(JSON.stringify(DEFAULT_WORDS));
  settings = { ...settings, ...(data.settings || {}) };
}
const saveWords    = () => chrome.storage.local.set({ words: currentWords });
const saveSettings = () => chrome.storage.local.set({ settings });

// ── Mode detection ────────────────────────────────────────────────────────
async function detectAndShowMode() {
  const tab = await getActiveTab();
  if (!tab) return;

  const url = tab.url || '';
  const urlEl = document.getElementById('currentUrl');
  try { urlEl.textContent = new URL(url).hostname || url; urlEl.title = url; }
  catch { urlEl.textContent = url.slice(0, 40); }

  const isPdf = isPdfUrl(url);
  const modeEl = document.getElementById('scanMode');
  const pdfNotice = document.getElementById('pdfNotice');

  if (isPdf) {
    modeEl.innerHTML = '<span class="mode-badge pdf">📄 PDF 模式</span>';
    pdfNotice.style.display = 'block';
  } else {
    modeEl.innerHTML = '<span class="mode-badge web">🌐 网页模式</span>';
    pdfNotice.style.display = 'none';
  }
}

function isPdfUrl(url = '') {
  return /\.pdf(\?[^#]*)?($|#)/i.test(url) ||
    url.startsWith('chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai') ||
    url.includes('chrome://pdf');
}

// ── UI setup ──────────────────────────────────────────────────────────────
function initUI() {
  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn, .tab-panel').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });

  document.getElementById('btnScan').addEventListener('click', startScan);
  document.getElementById('btnClear').addEventListener('click', clearHighlights);
  document.getElementById('btnAddWord').addEventListener('click', addWord);
  document.getElementById('newWordInput').addEventListener('keydown', e => { if (e.key === 'Enter') addWord(); });
  document.getElementById('btnExport').addEventListener('click', exportWords);
  document.getElementById('btnImport').addEventListener('click', () => document.getElementById('importFile').click());
  document.getElementById('importFile').addEventListener('change', importWords);

  setupToggle('toggleAutoScan',      'autoScan');
  setupToggle('toggleCaseSensitive', 'caseSensitive');
  applyToggleState('toggleAutoScan',      settings.autoScan);
  applyToggleState('toggleCaseSensitive', settings.caseSensitive);

  const ctxSel = document.getElementById('contextLength');
  ctxSel.value = settings.contextLength;
  ctxSel.addEventListener('change', async () => { settings.contextLength = +ctxSel.value; await saveSettings(); });

  document.querySelectorAll('.color-dot').forEach(dot => {
    dot.classList.toggle('selected', dot.dataset.color === settings.highlightColor);
    dot.addEventListener('click', async () => {
      document.querySelectorAll('.color-dot').forEach(d => d.classList.remove('selected'));
      dot.classList.add('selected');
      settings.highlightColor = dot.dataset.color;
      await saveSettings();
    });
  });

  document.getElementById('btnResetWords').addEventListener('click', async () => {
    if (!confirm('恢复默认词库将保留自定义词，是否继续？')) return;
    const custom = currentWords.filter(w => !w.isDefault);
    currentWords = [...JSON.parse(JSON.stringify(DEFAULT_WORDS)), ...custom];
    await saveWords(); renderWordList();
  });
  document.getElementById('btnClearAll').addEventListener('click', async () => {
    if (!confirm('确定清空所有数据？此操作不可撤销。')) return;
    await chrome.storage.local.clear(); await loadData(); renderWordList();
  });

  renderWordList();
}

function setupToggle(id, key) {
  document.getElementById(id).addEventListener('click', async () => {
    settings[key] = !settings[key];
    applyToggleState(id, settings[key]);
    await saveSettings();
  });
}
function applyToggleState(id, val) {
  document.getElementById(id).classList.toggle('on', !!val);
}

// ── SCAN ENTRY POINT ──────────────────────────────────────────────────────
async function startScan() {
  const btn = document.getElementById('btnScan');
  btn.disabled = true;
  btn.textContent = '⏳ 扫描中...';

  const enabledWords = currentWords.filter(w => w.enabled).map(w => w.word);
  if (!enabledWords.length) {
    alert('词库为空，请先在「词库」标签添加敏感词！');
    btn.disabled = false; btn.innerHTML = '🔍 开始扫描'; return;
  }

  try {
    const tab = await getActiveTab();
    if (!tab) throw new Error('无法获取当前标签页');

    if (isPdfUrl(tab.url || '')) {
      await scanPdfTab(tab, enabledWords);
    } else {
      await scanWebTab(tab, enabledWords);
    }
  } catch (err) {
    console.error('[SWC]', err);
    alert(`扫描失败：${err.message}`);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔍 重新扫描';
  }
}

// ── PDF SCAN (popup-side, no content script) ──────────────────────────────
async function scanPdfTab(tab, words) {
  setProgress(true, '正在下载 PDF...', 10);

  let pdfText;
  try {
    pdfText = await PdfExtractor.extractFromUrl(tab.url);
  } catch (err) {
    setProgress(false);
    throw new Error(`PDF 解析失败：${err.message}`);
  }

  setProgress(true, '正在搜索敏感词...', 70);

  const ctxLen = settings.contextLength || 50;
  const noCase = !settings.caseSensitive;
  const results = searchText(pdfText, words, noCase, ctxLen, 'PDF 文档');

  setProgress(true, '完成', 100);
  await sleep(300);
  setProgress(false);

  displayResults(results, true /* isPdf */);
}

// ── WEB SCAN (via content script) ─────────────────────────────────────────
async function scanWebTab(tab, words) {
  const response = await sendScan(tab.id, words);
  if (response?.ok === false) {
    throw new Error(response.error || '内容脚本返回错误');
  }
  if (response?.results) {
    displayResults(response.results, false);
  }
}

async function sendScan(tabId, words) {
  const payload = { action: 'scan', words, settings };
  try {
    return await chrome.tabs.sendMessage(tabId, payload);
  } catch {
    await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
    await chrome.scripting.insertCSS({ target: { tabId }, files: ['content.css'] });
    await sleep(300);
    return await chrome.tabs.sendMessage(tabId, payload);
  }
}

// ── TEXT SEARCH (used for PDF) ────────────────────────────────────────────
function searchText(text, words, noCase, ctxLen, location) {
  const map = new Map();

  words.forEach(word => {
    if (!word?.trim()) return;
    let re;
    try { re = new RegExp(escapeRe(word), noCase ? 'gi' : 'g'); }
    catch { return; }

    let m, idx = 0;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      const s = m.index, e = s + m[0].length;
      const match = {
        word:          m[0],
        originalWord:  word,
        contextBefore: text.slice(Math.max(0, s - ctxLen), s),
        contextAfter:  text.slice(e, Math.min(text.length, e + ctxLen)),
        index:         idx++,
        location,
      };
      if (!map.has(word)) map.set(word, { word, matches: [] });
      map.get(word).matches.push(match);
    }
  });

  return [...map.values()];
}

// ── RESULTS DISPLAY ───────────────────────────────────────────────────────
function displayResults(results, isPdf) {
  const total = results.reduce((s, r) => s + r.matches.length, 0);

  document.getElementById('foundCount').textContent  = `${total} 处`;
  document.getElementById('foundCount').style.color  = total ? '#e94560' : '#2ecc71';
  document.getElementById('resultsCount').textContent = `${total} 处`;
  document.getElementById('resultsHeader').style.display = 'flex';

  const badge = document.getElementById('headerBadge');
  badge.textContent = total; badge.style.display = total > 0 ? 'inline-block' : 'none';

  // Update status via innerHTML only — do NOT separately reference statusDot
  // because innerHTML replaces it, making getElementById('statusDot') return
  // null on subsequent scans → "Cannot set properties of null (setting 'className')"
  if (total > 0) {
    document.getElementById('scanStatusText').innerHTML =
      '<span class="status-dot danger"></span>发现敏感词';
  } else {
    document.getElementById('scanStatusText').innerHTML =
      '<span class="status-dot active"></span>安全';
  }

  const list = document.getElementById('resultList');
  if (total === 0) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">✅</div>
      <p>未发现敏感词<br>当前${isPdf ? 'PDF' : '页面'}内容安全</p></div>`;
    return;
  }

  list.innerHTML = '';
  let gi = 1;
  results.forEach(({ matches }) => {
    matches.forEach(match => {
      const item = document.createElement('div');
      item.className = isPdf ? 'result-item pdf-item' : 'result-item';
      const ew = esc(match.word);
      item.innerHTML = `
        <div class="result-word">
          <span class="result-index">#${gi++}</span>「${ew}」
        </div>
        <div class="result-context">
          ...${esc(match.contextBefore)}<mark>${ew}</mark>${esc(match.contextAfter)}...
        </div>
        <div class="result-nav">
          <span class="result-location">${esc(match.location || '正文')}</span>
          ${isPdf ? '<span style="font-size:10px;color:#3498db">📄 PDF</span>'
                  : '<span style="font-size:10px;color:#555">点击定位 →</span>'}
        </div>`;

      if (!isPdf) {
        item.addEventListener('click', async () => {
          document.querySelectorAll('.result-item').forEach(el => {
            el.style.borderLeftColor = '#e94560'; el.style.background = '#1a1a2e';
          });
          item.style.borderLeftColor = '#fff'; item.style.background = '#1e1e35';
          try {
            const tab = await getActiveTab();
            await chrome.tabs.sendMessage(tab.id, { action: 'scrollToMatch', index: match.index });
          } catch {}
        });
      }

      list.appendChild(item);
    });
  });
}

async function clearHighlights() {
  try {
    const tab = await getActiveTab();
    if (tab && !isPdfUrl(tab.url || '')) {
      await chrome.tabs.sendMessage(tab.id, { action: 'clear' });
    }
  } catch {}

  document.getElementById('scanStatusText').innerHTML = '<span class="status-dot"></span>已清除';
  document.getElementById('foundCount').textContent = '—';
  document.getElementById('headerBadge').style.display = 'none';
  document.getElementById('resultsHeader').style.display = 'none';
  document.getElementById('resultList').innerHTML = `
    <div class="empty-state"><div class="empty-icon">📄</div>
    <p>点击「开始扫描」检查<br>当前页面中的敏感词</p></div>`;
}

// ── WORD LIST ─────────────────────────────────────────────────────────────
function renderWordList() {
  const list = document.getElementById('wordList');
  document.getElementById('wordCount').textContent = `${currentWords.length} 个`;
  if (!currentWords.length) {
    list.innerHTML = '<div class="word-count-info">词库为空，请添加敏感词</div>'; return;
  }
  list.innerHTML = '';
  currentWords.forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'word-item';
    div.innerHTML = `
      <div class="word-enabled ${item.enabled ? 'on' : ''}" data-i="${i}"></div>
      <span class="word-text">${esc(item.word)}</span>
      <span class="word-tag ${item.isDefault ? 'default' : 'custom'}">${item.isDefault ? '默认' : '自定义'}</span>
      <button class="btn-danger-sm" data-del="${i}">删除</button>`;
    div.querySelector('.word-enabled').addEventListener('click', async e => {
      const idx = +e.currentTarget.dataset.i;
      currentWords[idx].enabled = !currentWords[idx].enabled;
      e.currentTarget.classList.toggle('on'); await saveWords();
    });
    div.querySelector('[data-del]').addEventListener('click', async e => {
      currentWords.splice(+e.currentTarget.dataset.del, 1);
      await saveWords(); renderWordList();
    });
    list.appendChild(div);
  });
}

async function addWord() {
  const input = document.getElementById('newWordInput');
  const word = input.value.trim();
  if (!word) return;
  if (currentWords.some(w => w.word === word)) { alert('该词已存在！'); return; }
  currentWords.push({ word, enabled: true, isDefault: false });
  await saveWords(); renderWordList();
  input.value = ''; input.focus();
}

function exportWords() {
  const blob = new Blob([JSON.stringify(currentWords, null, 2)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(blob),
    download: `sensitive-words-${Date.now()}.json`
  });
  a.click(); URL.revokeObjectURL(a.href);
}

async function importWords(e) {
  const file = e.target.files[0]; if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    if (!Array.isArray(imported)) throw new Error();
    const valid = imported.filter(x => typeof x.word === 'string' && x.word.trim());
    valid.forEach(x => {
      if (!currentWords.some(w => w.word === x.word))
        currentWords.push({ word: x.word, enabled: x.enabled !== false, isDefault: false });
    });
    await saveWords(); renderWordList();
    alert(`成功导入 ${valid.length} 个词！`);
  } catch { alert('导入失败：文件格式不正确'); }
  e.target.value = '';
}

// ── HELPERS ───────────────────────────────────────────────────────────────
async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab || null;
}

function setProgress(show, label = '', pct = 0) {
  const wrap = document.getElementById('progressWrap');
  wrap.style.display = show ? 'block' : 'none';
  if (show) {
    document.getElementById('progressLabel').textContent = label;
    document.getElementById('progressFill').style.width = `${pct}%`;
  }
}

function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

function esc(s = '') {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
