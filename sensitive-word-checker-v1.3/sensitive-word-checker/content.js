/**
 * Sensitive Word Checker — Content Script v1.3
 * Web pages ONLY. PDF is handled entirely in popup.js via fetch+parse.
 *
 * Key fixes carried from v1.2:
 *  - Ascending single-pass highlight (no previousSibling, no DOM corruption)
 *  - try/catch around all respond() calls (no silent hangs)
 *  - Duplicate-injection guard
 *  - SPA URL-change observer
 */

if (window.__swcInjected) {
  // Already active — skip re-init
} else {
  window.__swcInjected = true;
  main();
}

function main() {

  let panel    = null;
  let navIndex = 0;

  // ── Message listener ──────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
    try {
      if (msg.action === 'scan') {
        const results = performScan(msg.words || [], msg.settings || {});
        respond({ ok: true, results });
      } else if (msg.action === 'scrollToMatch') {
        jumpTo(msg.index); respond({ ok: true });
      } else if (msg.action === 'clear') {
        clearAll(); respond({ ok: true });
      } else {
        respond({ ok: false, error: 'unknown action' });
      }
    } catch (err) {
      console.error('[SWC content]', err);
      respond({ ok: false, error: String(err) });
    }
    return true;
  });

  // ── Scan ──────────────────────────────────────────────────────────────
  function performScan(words, settings) {
    clearAll();
    const ctxLen = Number(settings.contextLength) || 50;
    const noCase = !settings.caseSensitive;
    const color  = settings.highlightColor || '#e94560';

    const matches = scanDom(words, noCase, ctxLen);
    applyHighlights(matches, color);
    showPanel(matches.length, color);

    const map = new Map();
    matches.forEach(m => {
      if (!map.has(m.originalWord)) map.set(m.originalWord, { word: m.originalWord, matches: [] });
      map.get(m.originalWord).matches.push(m);
    });
    return [...map.values()];
  }

  // ── DOM scan ──────────────────────────────────────────────────────────
  const SKIP = new Set(['script','style','noscript','iframe','textarea','svg','canvas','code','pre']);

  function scanDom(words, noCase, ctxLen) {
    if (!document.body) return [];
    const textNodes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const tag = node.parentElement?.tagName?.toLowerCase();
        if (SKIP.has(tag)) return NodeFilter.FILTER_REJECT;
        if (node.parentElement?.closest('.swc-panel, mark.swc-highlight'))
          return NodeFilter.FILTER_REJECT;
        return node.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }
    });
    let n; while ((n = walker.nextNode())) textNodes.push(n);

    const results = [];
    words.forEach(word => {
      if (!word?.trim()) return;
      let re;
      try { re = new RegExp(escapeRe(word), noCase ? 'gi' : 'g'); } catch { return; }
      textNodes.forEach(node => {
        const text = node.textContent;
        re.lastIndex = 0;
        let m;
        while ((m = re.exec(text)) !== null) {
          const s = m.index, e = s + m[0].length;
          results.push({
            word: m[0], originalWord: word,
            contextBefore: text.slice(Math.max(0, s - ctxLen), s),
            contextAfter:  text.slice(e, Math.min(text.length, e + ctxLen)),
            textNode: node, startOffset: s, endOffset: e,
            index: results.length, location: getLocation(node),
          });
        }
      });
    });
    return results;
  }

  // ── Highlight (ascending single-pass, one replaceChild per node) ──────
  function applyHighlights(matches, color) {
    const byNode = new Map();
    matches.forEach(m => {
      if (!m.textNode) return;
      if (!byNode.has(m.textNode)) byNode.set(m.textNode, []);
      byNode.get(m.textNode).push(m);
    });

    byNode.forEach((nodeMatches, textNode) => {
      if (!textNode.parentNode) return;
      nodeMatches.sort((a, b) => a.startOffset - b.startOffset);

      const text   = textNode.textContent;
      const frag   = document.createDocumentFragment();
      let   cursor = 0;

      nodeMatches.forEach(match => {
        const s = match.startOffset, e = match.endOffset;
        if (s < cursor || e > text.length || s >= e) return;
        if (s > cursor) frag.appendChild(document.createTextNode(text.slice(cursor, s)));

        const mark = document.createElement('mark');
        mark.className = 'swc-highlight';
        mark.dataset.matchIndex = String(match.index);
        mark.textContent = text.slice(s, e);
        applyMarkStyle(mark, color);
        mark.addEventListener('click', () => focusMatch(match.index));
        frag.appendChild(mark);
        cursor = e;
      });

      if (cursor < text.length) frag.appendChild(document.createTextNode(text.slice(cursor)));
      textNode.parentNode.replaceChild(frag, textNode);
    });
  }

  function applyMarkStyle(el, color) {
    el.style.cssText = `
      background:${hexRgba(color, 0.30)}!important;
      color:${color}!important;
      border-bottom:2px solid ${color}!important;
      border-radius:2px!important;
      padding:0 1px!important;
      cursor:pointer!important;
      font-weight:bold!important;
      font-style:inherit!important;
      text-decoration:none!important;
    `;
    el.title = `敏感词：${el.textContent}`;
  }

  // ── Navigation ────────────────────────────────────────────────────────
  function jumpTo(index) {
    const el = document.querySelector(`.swc-highlight[data-match-index="${index}"]`);
    if (!el) return;
    const all = [...document.querySelectorAll('.swc-highlight')];
    navIndex = all.indexOf(el);
    updateCounter(navIndex, all.length);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    flash(el);
  }

  function focusMatch(index) { jumpTo(index); }

  function navigate(dir) {
    const all = [...document.querySelectorAll('.swc-highlight')];
    if (!all.length) return;
    navIndex = ((navIndex + dir) + all.length) % all.length;
    updateCounter(navIndex, all.length);
    all[navIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
    flash(all[navIndex]);
  }

  function updateCounter(i, total) {
    const el = document.getElementById('swcNavCount');
    if (el) el.textContent = `${i + 1}/${total}`;
  }

  function flash(el) {
    el.classList.add('swc-focused');
    setTimeout(() => el.classList.remove('swc-focused'), 900);
  }

  // ── Clear ─────────────────────────────────────────────────────────────
  function clearAll() {
    document.querySelectorAll('mark.swc-highlight').forEach(mark => {
      const p = mark.parentNode; if (!p) return;
      p.replaceChild(document.createTextNode(mark.textContent), mark);
      p.normalize();
    });
    panel?.remove(); panel = null; navIndex = 0;
  }

  // ── Floating panel ────────────────────────────────────────────────────
  function showPanel(count, color) {
    panel?.remove();
    panel = document.createElement('div');
    panel.className = 'swc-panel';

    if (count === 0) {
      panel.innerHTML = `
        <div class="swc-panel-header" style="border-left:3px solid #2ecc71">
          <span style="color:#2ecc71">✅ 未发现敏感词</span>
          <button class="swc-close-btn">✕</button>
        </div>`;
    } else {
      panel.innerHTML = `
        <div class="swc-panel-header" style="border-left:3px solid ${color}">
          <span style="color:${color}">⚠️ 发现 <b>${count}</b> 处敏感词</span>
          <div style="display:flex;gap:6px;align-items:center">
            <button class="swc-nav-btn" id="swcPrev">↑</button>
            <span class="swc-nav-count" id="swcNavCount">1/${count}</span>
            <button class="swc-nav-btn" id="swcNext">↓</button>
            <button class="swc-close-btn">✕</button>
          </div>
        </div>`;
      requestAnimationFrame(() => {
        document.getElementById('swcPrev')?.addEventListener('click', () => navigate(-1));
        document.getElementById('swcNext')?.addEventListener('click', () => navigate(+1));
        const first = document.querySelector('.swc-highlight');
        if (first) { first.scrollIntoView({ behavior: 'smooth', block: 'center' }); flash(first); }
      });
    }

    panel.querySelector('.swc-close-btn').addEventListener('click', clearAll);
    document.body.appendChild(panel);
    makeDraggable(panel);
  }

  function makeDraggable(el) {
    let drag = false, ox = 0, oy = 0;
    const hdr = el.querySelector('.swc-panel-header');
    if (!hdr) return;
    hdr.style.cursor = 'grab';
    hdr.addEventListener('mousedown', e => {
      if (e.target.tagName === 'BUTTON') return;
      drag = true;
      const r = el.getBoundingClientRect();
      ox = e.clientX - r.left; oy = e.clientY - r.top;
      hdr.style.cursor = 'grabbing'; e.preventDefault();
    });
    document.addEventListener('mousemove', e => {
      if (!drag) return;
      el.style.left = `${e.clientX - ox}px`; el.style.top = `${e.clientY - oy}px`;
      el.style.right = el.style.bottom = 'auto';
    });
    document.addEventListener('mouseup', () => { drag = false; hdr.style.cursor = 'grab'; });
  }

  // ── SPA observer ──────────────────────────────────────────────────────
  let lastHref = location.href;
  new MutationObserver(() => {
    if (location.href !== lastHref) { lastHref = location.href; clearAll(); }
  }).observe(document.body, { childList: true, subtree: true });

  // ── Helpers ───────────────────────────────────────────────────────────
  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function hexRgba(hex, a) {
    const r = parseInt(hex.slice(1,3), 16);
    const g = parseInt(hex.slice(3,5), 16);
    const b = parseInt(hex.slice(5,7), 16);
    return `rgba(${r},${g},${b},${a})`;
  }

  function getLocation(node) {
    let el = node?.parentElement;
    while (el && el !== document.body) {
      if (/^H[1-6]$/.test(el.tagName)) return `标题：${el.textContent.trim().slice(0, 30)}`;
      if (el.tagName === 'NAV' || el.getAttribute('role') === 'navigation') return '导航';
      if (el.tagName === 'FOOTER') return '页脚';
      if (el.tagName === 'HEADER') return '页头';
      if (el.tagName === 'ARTICLE' || el.tagName === 'MAIN') return '正文';
      el = el.parentElement;
    }
    return '正文';
  }

} // end main()
