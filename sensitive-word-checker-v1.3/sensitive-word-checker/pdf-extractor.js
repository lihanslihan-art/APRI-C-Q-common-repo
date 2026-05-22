/**
 * Minimal PDF Text Extractor
 * Works entirely in the extension popup context (no content script needed).
 *
 * Handles:
 *  - FlateDecode compressed content streams  (most modern PDFs)
 *  - Uncompressed content streams
 *  - Text operators: Tj, TJ, ', "
 *  - Literal strings (parentheses): (hello)
 *  - Hex strings: <0048656C6C6F>
 *  - UTF-16BE with BOM (\xFE\xFF)
 *  - PDFDocEncoding / Latin-1
 *
 * Limitations (acceptable for sensitive-word checking):
 *  - Encrypted PDFs → shows error
 *  - Custom glyph-mapped fonts → some characters may appear as ?
 *  - Very complex PostScript-heavy PDFs may yield partial text
 */

const PdfExtractor = (() => {

  // ── Public API ────────────────────────────────────────────────────────
  async function extractFromUrl(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    const buf  = await resp.arrayBuffer();
    return extractFromBuffer(buf);
  }

  async function extractFromBuffer(buffer) {
    const bytes = new Uint8Array(buffer);

    // Check PDF signature
    const header = bytesToLatin1(bytes, 0, Math.min(5, bytes.length));
    if (!header.startsWith('%PDF')) throw new Error('不是有效的 PDF 文件');

    // Check for encryption
    const fullStr = bytesToLatin1(bytes, 0, Math.min(bytes.length, 4096));
    if (/\/Encrypt\b/.test(fullStr)) throw new Error('PDF 已加密，无法提取文字');

    const pageTexts = await extractAllStreams(bytes);
    return pageTexts.join('\n').replace(/\s+/g, ' ').trim();
  }

  // ── Stream extraction ─────────────────────────────────────────────────
  async function extractAllStreams(bytes) {
    const results = [];
    let i = 0;

    // Find every "stream\n" or "stream\r\n" occurrence
    while (i < bytes.length - 16) {
      // Look for 's','t','r','e','a','m'
      if (bytes[i] !== 115 || !matchSeq(bytes, i, 'stream')) { i++; continue; }

      // Data starts after the newline(s) following 'stream'
      let dataStart = i + 6;
      if (bytes[dataStart] === 13) dataStart++;   // \r
      if (bytes[dataStart] === 10) dataStart++;   // \n

      // Find matching 'endstream'
      const dataEnd = findKeyword(bytes, dataStart, 'endstream');
      if (dataEnd === -1) { i++; continue; }

      // Read the object dictionary that precedes this stream
      // Look backward up to 2 KB for the opening <<
      const lookbackStart = Math.max(0, i - 2048);
      const dictBytes     = bytes.slice(lookbackStart, i);
      const dictStr       = bytesToLatin1(dictBytes, 0, dictBytes.length);

      // Skip image XObjects and embedded files — they contain no text
      if (/\/Subtype\s*\/Image\b/.test(dictStr))  { i = dataEnd + 9; continue; }
      if (/\/Type\s*\/XObject\b/.test(dictStr) &&
          /\/Subtype\s*\/Image\b/.test(dictStr))  { i = dataEnd + 9; continue; }

      const isFlate = /\/Filter\s*\/FlateDecode\b/.test(dictStr) ||
                      /\/Filter\s*\[([^\]]*\/FlateDecode[^\]]*)\]/.test(dictStr);

      const streamData = bytes.slice(dataStart, dataEnd);
      let contentStr = '';

      if (isFlate) {
        try {
          const decompressed = await inflate(streamData);
          contentStr = bytesToLatin1(decompressed, 0, decompressed.length);
        } catch { /* skip undecompressable stream */ }
      } else {
        contentStr = bytesToLatin1(streamData, 0, streamData.length);
      }

      if (contentStr) {
        const text = extractTextFromContentStream(contentStr);
        if (text.trim().length > 1) results.push(text);
      }

      i = dataEnd + 9; // skip 'endstream'
    }

    return results;
  }

  // ── Content stream text extraction ────────────────────────────────────
  function extractTextFromContentStream(content) {
    const parts = [];

    // Tj  →  (string) Tj
    forEachMatch(content, /\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*Tj\b/g, m => {
      parts.push(decodeLiteralString(m[1]), ' ');
    });

    // TJ  →  [(string | <hex> | num) ...] TJ
    forEachMatch(content, /\[([^\]]*)\]\s*TJ\b/g, m => {
      parts.push(parseTJArray(m[1]), ' ');
    });

    // ' operator  →  (string)'
    forEachMatch(content, /\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*'/g, m => {
      parts.push('\n', decodeLiteralString(m[1]));
    });

    // " operator  →  aw ac (string)"
    forEachMatch(content, /\(([^)\\]*(?:\\.[^)\\]*)*)\)\s*"/g, m => {
      parts.push('\n', decodeLiteralString(m[1]));
    });

    // Hex literal Tj  →  <hex> Tj
    forEachMatch(content, /<([0-9a-fA-F]+)>\s*Tj\b/g, m => {
      parts.push(decodeHexString(m[1]), ' ');
    });

    return parts.join('');
  }

  // ── String decoders ───────────────────────────────────────────────────
  function decodeLiteralString(raw) {
    // Unescape PDF escape sequences
    let str = raw
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '\r')
      .replace(/\\t/g, '\t')
      .replace(/\\b/g, '\b')
      .replace(/\\f/g, '\f')
      .replace(/\\\(/g, '(')
      .replace(/\\\)/g, ')')
      .replace(/\\\\/g, '\\')
      .replace(/\\([0-7]{1,3})/g, (_, oct) => String.fromCharCode(parseInt(oct, 8)));

    // UTF-16BE BOM: \xFE\xFF
    if (str.charCodeAt(0) === 0xFE && str.charCodeAt(1) === 0xFF) {
      return utf16BeToStr(str, 2);
    }
    return cleanLatin1(str);
  }

  function decodeHexString(hex) {
    if (hex.length % 2 !== 0) hex += '0';
    const bytes = [];
    for (let i = 0; i < hex.length; i += 2) {
      bytes.push(parseInt(hex.substr(i, 2), 16));
    }
    // UTF-16BE BOM
    if (bytes.length >= 2 && bytes[0] === 0xFE && bytes[1] === 0xFF) {
      let str = '';
      for (let i = 2; i + 1 < bytes.length; i += 2) {
        str += String.fromCharCode((bytes[i] << 8) | bytes[i + 1]);
      }
      return str;
    }
    return cleanLatin1(bytes.map(b => String.fromCharCode(b)).join(''));
  }

  function parseTJArray(content) {
    const parts = [];
    // Literal strings
    forEachMatch(content, /\(([^)\\]*(?:\\.[^)\\]*)*)\)/g, m => {
      parts.push(decodeLiteralString(m[1]));
    });
    // Hex strings
    forEachMatch(content, /<([0-9a-fA-F]*)>/g, m => {
      if (m[1]) parts.push(decodeHexString(m[1]));
    });
    return parts.join('');
  }

  function utf16BeToStr(raw, startIdx = 0) {
    let str = '';
    for (let i = startIdx; i + 1 < raw.length; i += 2) {
      const code = (raw.charCodeAt(i) << 8) | raw.charCodeAt(i + 1);
      str += String.fromCharCode(code);
    }
    return str;
  }

  function cleanLatin1(str) {
    // Replace control chars (except whitespace) with space; keep printable Latin-1+
    return str.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, ' ');
  }

  // ── Decompression ─────────────────────────────────────────────────────
  async function inflate(data) {
    // PDFs use zlib-wrapped deflate; try 'deflate' (zlib) first then 'deflate-raw'
    const formats = ['deflate', 'deflate-raw'];
    for (const fmt of formats) {
      try {
        const ds     = new DecompressionStream(fmt);
        const writer = ds.writable.getWriter();
        writer.write(data);
        writer.close();

        const chunks = [];
        let   total  = 0;
        const reader = ds.readable.getReader();
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          chunks.push(value);
          total += value.length;
        }
        const out = new Uint8Array(total);
        let off = 0;
        for (const c of chunks) { out.set(c, off); off += c.length; }
        return out;
      } catch { /* try next format */ }
    }
    throw new Error('decompress failed');
  }

  // ── Utilities ─────────────────────────────────────────────────────────
  function matchSeq(bytes, pos, str) {
    for (let j = 0; j < str.length; j++) {
      if (bytes[pos + j] !== str.charCodeAt(j)) return false;
    }
    return true;
  }

  function findKeyword(bytes, start, kw) {
    const first = kw.charCodeAt(0);
    for (let i = start; i < bytes.length - kw.length; i++) {
      if (bytes[i] === first && matchSeq(bytes, i, kw)) return i;
    }
    return -1;
  }

  function bytesToLatin1(bytes, start, end) {
    // Build in chunks to avoid call-stack limits on large buffers
    const CHUNK = 32768;
    let str = '';
    for (let i = start; i < end; i += CHUNK) {
      str += String.fromCharCode(...bytes.subarray(i, Math.min(i + CHUNK, end)));
    }
    return str;
  }

  function forEachMatch(str, regex, cb) {
    let m;
    regex.lastIndex = 0;
    while ((m = regex.exec(str)) !== null) cb(m);
  }

  // ── Exports ───────────────────────────────────────────────────────────
  return { extractFromUrl, extractFromBuffer };
})();
