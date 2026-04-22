// ==UserScript==
// @name         TikTok Studio Upload Helper LIGHT
// @namespace    http://tampermonkey.net/
// @version      2.2-light
// @description  Панель для TikTok Studio: разбор строки, вставка описания и загрузка видео через локальный bridge
// @author       FANTOM
// @match        https://www.tiktok.com/*
// @match        https://studio.tiktok.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const BRIDGE = 'http://127.0.0.1:8765';
    const TOKEN = '1224444';
    const PANEL_ID = 'tt-helper-light-panel';
    const LOG_PREFIX = '[TT Helper LIGHT]';
    const STORAGE_KEY = 'tt_helper_last_input';

    let parsed = { path: '', tags: '', date: '', caption: '' };

    // ---------- logging ----------
    function log() {
        const args = Array.prototype.slice.call(arguments);
        console.log.apply(console, [LOG_PREFIX].concat(args));
        const box = document.getElementById('tt-light-log');
        if (!box) return;
        const line = document.createElement('div');
        line.textContent = '[' + new Date().toLocaleTimeString() + '] ' +
            args.map(stringify).join(' ');
        box.appendChild(line);
        box.scrollTop = box.scrollHeight;
    }

    function stringify(x) {
        try {
            if (typeof x === 'string') return x;
            return JSON.stringify(x);
        } catch (e) {
            return String(x);
        }
    }

    // ---------- utils ----------
    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function sleep(ms) {
        return new Promise(function (r) { setTimeout(r, ms); });
    }

    function storageGet(key, fallback) {
        try {
            if (typeof GM_getValue === 'function') return GM_getValue(key, fallback);
        } catch (_) {}
        try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
    }

    function storageSet(key, value) {
        try {
            if (typeof GM_setValue === 'function') { GM_setValue(key, value); return; }
        } catch (_) {}
        try { localStorage.setItem(key, value); } catch (_) {}
    }

    // ---------- init ----------
    function shouldRun() {
        const h = location.href;
        return h.indexOf('tiktokstudio') !== -1 ||
               h.indexOf('studio.tiktok.com') !== -1 ||
               h.indexOf('/upload') !== -1;
    }

    function init() {
        if (!shouldRun()) return;
        if (document.getElementById(PANEL_ID)) return;
        if (!document.body) return;

        const panel = document.createElement('div');
        panel.id = PANEL_ID;
        panel.innerHTML =
'<style>' +
'#' + PANEL_ID + '{position:fixed;top:70px;right:12px;width:360px;max-height:85vh;overflow:auto;' +
'background:#18181b;color:#e5e7eb;border:1px solid #3f3f46;border-radius:12px;' +
'box-shadow:0 10px 30px rgba(0,0,0,.45);z-index:2147483647;' +
"font:13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}" +
'#' + PANEL_ID + ' *{box-sizing:border-box}' +
'#' + PANEL_ID + ' .hdr{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;background:#09090b;border-bottom:1px solid #3f3f46;cursor:move}' +
'#' + PANEL_ID + ' .ttl{font-weight:700;color:#fff}' +
'#' + PANEL_ID + ' .mini{background:none;border:none;color:#a1a1aa;cursor:pointer;font-size:14px;padding:0 4px}' +
'#' + PANEL_ID + ' .mini:hover{color:#fff}' +
'#' + PANEL_ID + ' .body{padding:12px;display:flex;flex-direction:column;gap:10px}' +
'#' + PANEL_ID + ' textarea{width:100%;min-height:88px;resize:vertical;background:#09090b;color:#e5e7eb;border:1px solid #3f3f46;border-radius:8px;padding:8px 10px;font:12px/1.5 Consolas,monospace}' +
'#' + PANEL_ID + ' button{border:none;border-radius:8px;padding:8px 10px;background:#27272a;color:#e5e7eb;cursor:pointer;font-size:12px;font-weight:600}' +
'#' + PANEL_ID + ' button:hover{background:#3f3f46}' +
'#' + PANEL_ID + ' button:disabled{opacity:.5;cursor:not-allowed}' +
'#' + PANEL_ID + ' .primary{background:#4f46e5;color:#fff}' +
'#' + PANEL_ID + ' .primary:hover{background:#4338ca}' +
'#' + PANEL_ID + ' .row{display:flex;gap:8px;flex-wrap:wrap}' +
'#' + PANEL_ID + ' .row button{flex:1 1 0;min-width:90px}' +
'#' + PANEL_ID + ' .box{background:#09090b;border:1px solid #3f3f46;border-radius:8px;padding:8px 10px}' +
'#' + PANEL_ID + ' .status{font-size:11px;line-height:1.5}' +
'#' + PANEL_ID + ' .ok{background:#14532d;color:#86efac}' +
'#' + PANEL_ID + ' .warn{background:#451a03;color:#fdba74}' +
'#' + PANEL_ID + ' .err{background:#450a0a;color:#fca5a5}' +
'#' + PANEL_ID + ' .info{background:#1e293b;color:#bfdbfe}' +
'#' + PANEL_ID + ' .parsed{display:none;font-size:11px;line-height:1.6}' +
'#' + PANEL_ID + ' .parsed.visible{display:block}' +
'#' + PANEL_ID + ' .log{max-height:110px;overflow:auto;font-size:10px;white-space:pre-wrap;word-break:break-word;color:#a1a1aa}' +
'#' + PANEL_ID + '.collapsed .body{display:none}' +
'</style>' +
'<div class="hdr"><div class="ttl">TT Helper LIGHT v2.2</div>' +
'<button class="mini" id="tt-light-toggle" title="Свернуть">—</button></div>' +
'<div class="body">' +
'  <div class="box status info" id="tt-light-bridge">Bridge: проверяется…</div>' +
'  <textarea id="tt-light-input" placeholder="D:\\Videos\\cat.mp4 | #cats #funny | 2026-04-25 18:30 | caption"></textarea>' +
'  <div class="box parsed" id="tt-light-parsed"></div>' +
'  <div class="row">' +
'    <button id="tt-light-parse">Разобрать</button>' +
'    <button id="tt-light-fill">Заполнить текст</button>' +
'  </div>' +
'  <div class="row">' +
'    <button id="tt-light-upload">Загрузить видео</button>' +
'    <button id="tt-light-all" class="primary">Сделать всё</button>' +
'  </div>' +
'  <div class="box status info" id="tt-light-status">Ожидание действия.</div>' +
'  <div class="box"><div class="log" id="tt-light-log"></div></div>' +
'</div>';

        document.body.appendChild(panel);
        log('script started, v2.2');

        // restore last input
        const saved = storageGet(STORAGE_KEY, '');
        if (saved) document.getElementById('tt-light-input').value = saved;

        document.getElementById('tt-light-parse').addEventListener('click', doParse);
        document.getElementById('tt-light-fill').addEventListener('click', doFill);
        document.getElementById('tt-light-upload').addEventListener('click', doUpload);
        document.getElementById('tt-light-all').addEventListener('click', doAll);
        document.getElementById('tt-light-toggle').addEventListener('click', toggleCollapse);
        document.getElementById('tt-light-input').addEventListener('input', function (e) {
            storageSet(STORAGE_KEY, e.target.value);
        });

        makeDraggable(panel, panel.querySelector('.hdr'));
        checkBridge();
    }

    function toggleCollapse() {
        const panel = document.getElementById(PANEL_ID);
        if (!panel) return;
        panel.classList.toggle('collapsed');
        const btn = document.getElementById('tt-light-toggle');
        if (btn) btn.textContent = panel.classList.contains('collapsed') ? '+' : '—';
    }

    function makeDraggable(panel, handle) {
        let ox = 0, oy = 0, dragging = false;
        handle.addEventListener('mousedown', function (e) {
            if (e.target.tagName === 'BUTTON') return;
            dragging = true;
            const rect = panel.getBoundingClientRect();
            ox = e.clientX - rect.left;
            oy = e.clientY - rect.top;
            e.preventDefault();
        });
        document.addEventListener('mousemove', function (e) {
            if (!dragging) return;
            panel.style.left = (e.clientX - ox) + 'px';
            panel.style.top = (e.clientY - oy) + 'px';
            panel.style.right = 'auto';
        });
        document.addEventListener('mouseup', function () { dragging = false; });
    }

    // ---------- status helpers ----------
    function setStatus(type, text) {
        const el = document.getElementById('tt-light-status');
        if (!el) return;
        el.textContent = text;
        el.className = 'box status ' + type;
    }

    function setBridge(type, text) {
        const el = document.getElementById('tt-light-bridge');
        if (!el) return;
        el.textContent = text;
        el.className = 'box status ' + type;
    }

    function setButtonsBusy(busy) {
        ['tt-light-parse', 'tt-light-fill', 'tt-light-upload', 'tt-light-all'].forEach(function (id) {
            const b = document.getElementById(id);
            if (b) b.disabled = busy;
        });
    }

    // ---------- bridge ----------
    function checkBridge() {
        GM_xmlhttpRequest({
            method: 'GET',
            url: BRIDGE + '/health',
            timeout: 5000,
            onload: function (r) {
                if (r.status === 200) {
                    setBridge('ok', 'Bridge: OK');
                    log('bridge ok');
                } else {
                    setBridge('err', 'Bridge: HTTP ' + r.status);
                }
            },
            onerror: function () { setBridge('err', 'Bridge: недоступен'); },
            ontimeout: function () { setBridge('err', 'Bridge: timeout'); }
        });
    }

    // ---------- parsing ----------
    function parseInputLine(line) {
        const out = { path: '', tags: '', date: '', caption: '' };
        if (/\bpath\s*=/.test(line)) {
            line.split(';').forEach(function (part) {
                const idx = part.indexOf('=');
                if (idx === -1) return;
                const k = part.slice(0, idx).trim().toLowerCase();
                const v = part.slice(idx + 1).trim();
                if (k in out) out[k] = v;
            });
            return out;
        }
        const parts = line.split('|').map(function (s) { return s.trim(); });
        out.path = parts[0] || '';
        out.tags = parts[1] || '';
        out.date = parts[2] || '';
        out.caption = parts[3] || '';
        return out;
    }

    function doParse() {
        const raw = (document.getElementById('tt-light-input').value || '').trim();
        if (!raw) {
            setStatus('err', 'Введи строку с данными.');
            return false;
        }
        parsed = parseInputLine(raw);
        renderParsed(parsed);
        setStatus('ok', 'Строка разобрана.');
        log('parsed', parsed);
        return true;
    }

    function renderParsed(p) {
        const el = document.getElementById('tt-light-parsed');
        if (!el) return;
        const v = function (x) { return x ? escapeHtml(x) : '(пусто)'; };
        el.innerHTML =
            '<b>path:</b> ' + v(p.path) + '<br>' +
            '<b>tags:</b> ' + v(p.tags) + '<br>' +
            '<b>date:</b> ' + v(p.date) + '<br>' +
            '<b>caption:</b> ' + v(p.caption);
        el.classList.add('visible');
    }

    // ---------- fill caption ----------
    function doFill() {
        if (!parsed.path && !parsed.tags && !parsed.date && !parsed.caption) {
            if (!doParse()) return;
        }
        const text = [parsed.caption, parsed.tags].filter(Boolean).join(' ');
        const captionField = findCaptionField();
        if (!captionField) {
            setStatus('warn', 'Поле описания не найдено.');
            log('caption field not found');
            return;
        }
        setFieldValue(captionField, text);
        log('caption filled');
        setStatus('ok', 'Текст вставлен.');
    }

    function findCaptionField() {
        const selectors = [
            'div[contenteditable="true"][data-testid*="caption"]',
            'div[contenteditable="true"][aria-label*="aption"]',
            'div[contenteditable="true"][aria-label*="писан"]',
            'div[contenteditable="true"][class*="caption"]',
            'div[contenteditable="true"][class*="Caption"]',
            'div[contenteditable="true"][class*="description"]',
            'div[contenteditable="true"][class*="DraftEditor"]',
            'textarea[placeholder*="escrib"]',
            'textarea[placeholder*="писан"]',
            'textarea',
            'div[contenteditable="true"]'
        ];
        for (let i = 0; i < selectors.length; i++) {
            const els = document.querySelectorAll(selectors[i]);
            for (let j = 0; j < els.length; j++) {
                const el = els[j];
                const r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 28) return el;
            }
        }
        return null;
    }

    function setFieldValue(el, value) {
        el.focus();
        if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
            const proto = Object.getPrototypeOf(el);
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            if (desc && desc.set) desc.set.call(el, value);
            else el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            // contenteditable — эмулируем вставку
            el.focus();
            try {
                document.execCommand('selectAll', false, null);
                document.execCommand('delete', false, null);
                document.execCommand('insertText', false, value);
            } catch (_) {
                el.textContent = value;
                el.dispatchEvent(new InputEvent('input', { bubbles: true, data: value }));
            }
        }
    }

    // ---------- upload ----------
    function doUpload() {
        if (!parsed.path) {
            if (!doParse()) return;
        }
        if (!parsed.path) {
            setStatus('err', 'Нужен путь к файлу.');
            return;
        }
        setStatus('info', 'Проверяю файл через bridge…');
        setButtonsBusy(true);
        GM_xmlhttpRequest({
            method: 'GET',
            url: BRIDGE + '/check?path=' + encodeURIComponent(parsed.path),
            headers: { 'X-Token': TOKEN },
            timeout: 10000,
            onload: function (r) {
                let data = {};
                try { data = JSON.parse(r.responseText); } catch (_) {}
                if (r.status !== 200 || !data.exists) {
                    setStatus('err', 'Файл не найден: ' + (data.error || 'bridge ' + r.status));
                    log('check failed', r.status, data);
                    setButtonsBusy(false);
                    return;
                }
                log('file size', data.size);
                waitForFileInput(0);
            },
            onerror: function () {
                setStatus('err', 'Bridge error.');
                setButtonsBusy(false);
            },
            ontimeout: function () {
                setStatus('err', 'Bridge timeout.');
                setButtonsBusy(false);
            }
        });
    }

    function waitForFileInput(attempt) {
        const input = findFileInput();
        if (input) {
            log('file input found');
            injectFile(parsed.path, input);
            return;
        }
        if (attempt >= 10) {
            setStatus('warn', 'input[type=file] не найден. Нажми «Выбрать видео» вручную.');
            setButtonsBusy(false);
            return;
        }
        setStatus('info', 'Ищу input[type=file]… попытка ' + (attempt + 1));
        setTimeout(function () { waitForFileInput(attempt + 1); }, 500);
    }

    function findFileInput() {
        const list = document.querySelectorAll('input[type="file"]');
        for (let i = 0; i < list.length; i++) {
            const accept = (list[i].accept || '').toLowerCase();
            if (accept.indexOf('video') !== -1 || accept === '') return list[i];
        }
        return list[0] || null;
    }

    function injectFile(path, input) {
        setStatus('info', 'Загружаю видео через bridge…');
        GM_xmlhttpRequest({
            method: 'GET',
            url: BRIDGE + '/file?path=' + encodeURIComponent(path),
            headers: { 'X-Token': TOKEN },
            responseType: 'blob',
            timeout: 600000,
            onprogress: function (ev) {
                if (ev && ev.total) {
                    const pct = Math.floor((ev.loaded / ev.total) * 100);
                    setStatus('info', 'Загружаю: ' + pct + '% (' +
                        Math.round(ev.loaded / 1024 / 1024) + '/' +
                        Math.round(ev.total / 1024 / 1024) + ' MB)');
                }
            },
            onload: function (r) {
                if (r.status !== 200 && r.status !== 206) {
                    setStatus('err', 'Bridge ответил ' + r.status);
                    setButtonsBusy(false);
                    return;
                }
                try {
                    const name = path.split(/[\\/]/).pop();
                    const file = new File([r.response], name, { type: r.response.type || 'video/mp4' });
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    input.files = dt.files;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    setStatus('ok', 'Видео передано в TikTok (' +
                        Math.round(file.size / 1024 / 1024) + ' MB).');
                    log('file injected', name, file.size);
                } catch (e) {
                    setStatus('err', 'Ошибка File/DataTransfer: ' + e.message);
                    log('inject error', e.message);
                } finally {
                    setButtonsBusy(false);
                }
            },
            onerror: function () {
                setStatus('err', 'Ошибка получения файла.');
                setButtonsBusy(false);
            },
            ontimeout: function () {
                setStatus('err', 'Timeout при загрузке файла.');
                setButtonsBusy(false);
            }
        });
    }

    // ---------- do all ----------
    async function doAll() {
        if (!doParse()) return;
        doFill();
        await sleep(300);
        doUpload();
    }

    // ---------- bootstrap ----------
    window.addEventListener('load', function () { setTimeout(init, 1200); });

    // SPA: TikTok меняет URL без перезагрузки — пере-инициализируем
    let lastHref = location.href;
    setInterval(function () {
        if (location.href !== lastHref) {
            lastHref = location.href;
            setTimeout(init, 1500);
        }
    }, 1000);
})();
