chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get(['words', 'settings']);
  if (!existing.words) {
    await chrome.storage.local.set({ words: [
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
    ]});
  }
  if (!existing.settings) {
    await chrome.storage.local.set({ settings: {
      autoScan: false, caseSensitive: false,
      contextLength: 50, highlightColor: '#e94560',
    }});
  }
});

// Auto-scan web pages only (PDF is handled in popup)
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  const { settings, words } = await chrome.storage.local.get(['settings','words']);
  if (!settings?.autoScan) return;
  const url = tab.url || '';
  if (/\.pdf(\?|$)/i.test(url)) return; // skip PDFs
  const enabled = (words || []).filter(w => w.enabled).map(w => w.word);
  if (!enabled.length) return;
  try { await chrome.tabs.sendMessage(tabId, { action: 'scan', words: enabled, settings }); }
  catch {}
});
