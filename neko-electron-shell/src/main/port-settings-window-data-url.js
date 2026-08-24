'use strict';

const { safeScriptJson } = require('./html-escape');

function createPortSettingsDataUrlBuilder(context) {
  const {
    getAppConfig,
    getCurrentLanguage,
    getDefaultPorts,
    getTrayMenuLocales,
  } = context;

function getPortSettingsHTML() {
  const NEKO_DEFAULT_PORTS = getDefaultPorts();
  const appConfig = getAppConfig();
  const trayMenuLocales = getTrayMenuLocales();
  const currentLanguage = getCurrentLanguage();

  const currentPorts = {
    MAIN_SERVER_PORT: NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT,
    MEMORY_SERVER_PORT: NEKO_DEFAULT_PORTS.MEMORY_SERVER_PORT,
    TOOL_SERVER_PORT: NEKO_DEFAULT_PORTS.TOOL_SERVER_PORT,
    USER_PLUGIN_SERVER_PORT: NEKO_DEFAULT_PORTS.USER_PLUGIN_SERVER_PORT,
  };
  const defaults = { ...currentPorts };
  const portsJson = safeScriptJson(currentPorts);
  const defaultsJson = safeScriptJson(defaults);
  const currentUrls = appConfig?.customUrls || {};
  const urlsJson = safeScriptJson(currentUrls);

  const texts = trayMenuLocales[currentLanguage] || trayMenuLocales['en'];
  const i18nJson = safeScriptJson({
    portSaveSuccess: texts.portSaveSuccess,
    portSaveFailed: texts.portSaveFailed,
    portInvalid: texts.portInvalid,
    portDuplicate: texts.portDuplicate,
    portResetSuccess: texts.portResetSuccess,
    portRestartNow: texts.portRestartNow,
    portRestartMsg: texts.portRestartMsg,
    urlToggleText: texts.urlToggleText,
    urlSectionTitle: texts.urlSectionTitle,
    urlTip: texts.urlTip,
    portUrlUnreachable: texts.portUrlUnreachable,
  });

  return `<!DOCTYPE html>
<html lang="${currentLanguage}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${texts.portWindowTitle} - N.E.K.O.</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        *:focus { outline: none !important; }
        html, body {
            width: 100%; height: 100%; overflow: hidden;
            background: transparent;
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
        }
        .window-container {
            width: 100%; height: 100%;
            display: flex; flex-direction: column;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            border-radius: 12px; overflow: hidden;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }
        .title-bar {
            display: flex; align-items: center; justify-content: space-between;
            height: 40px; padding: 0 12px;
            background: rgba(0, 0, 0, 0.3);
            -webkit-app-region: drag; user-select: none;
        }
        .title-bar-text { font-size: 0.9rem; color: #aaa; font-weight: 500; }
        .title-bar-close {
            -webkit-app-region: no-drag;
            width: 28px; height: 28px; border: none;
            background: transparent; color: #888;
            font-size: 18px; cursor: pointer; border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.15s ease;
        }
        .title-bar-close:hover { background: rgba(255, 80, 80, 0.8); color: #fff; }
        .content {
            flex: 1; padding: 20px 24px 24px 24px;
            color: #e0e0e0; display: flex; flex-direction: column;
            overflow: hidden; min-height: 0;
        }
        .content-scroll {
            flex: 1; overflow-y: auto; min-height: 0;
        }
        .content-scroll::-webkit-scrollbar { width: 6px; }
        .content-scroll::-webkit-scrollbar-track { background: transparent; }
        .content-scroll::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.15); border-radius: 3px;
        }
        .content-scroll::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.3); }
        h2 { margin-bottom: 6px; font-size: 1.4rem; color: #fff; font-weight: 600; }
        .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 16px; }
        .tips {
            background: rgba(79, 140, 255, 0.08);
            border: 1px solid rgba(79, 140, 255, 0.2);
            border-radius: 8px; padding: 10px 14px; margin-bottom: 16px;
            font-size: 0.8rem; color: #aaa; line-height: 1.4;
        }
        .tips strong { color: #4f8cff; }
        .port-list { display: flex; flex-direction: column; gap: 12px; }
        .port-item {
            display: flex; align-items: center; justify-content: space-between;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px; padding: 12px 16px;
            transition: all 0.2s ease;
        }
        .port-item:hover {
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(79, 140, 255, 0.3);
        }
        .port-info { flex: 1; }
        .port-name { font-size: 0.95rem; font-weight: 500; color: #fff; margin-bottom: 2px; }
        .port-desc { font-size: 0.8rem; color: #888; }
        .port-input {
            width: 120px; padding: 8px 12px; border-radius: 6px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            background: rgba(0, 0, 0, 0.3); color: #fff;
            font-size: 0.95rem; font-family: 'Consolas', 'Monaco', monospace;
            text-align: center; transition: all 0.2s ease;
        }
        .port-input:hover { border-color: rgba(79, 140, 255, 0.5); }
        .port-input:focus {
            border-color: #4f8cff; background: rgba(79, 140, 255, 0.1);
            box-shadow: 0 0 0 3px rgba(79, 140, 255, 0.2) !important;
        }
        .port-input.error {
            border-color: #ff6b6b; background: rgba(255, 107, 107, 0.1);
        }
        .port-input::-webkit-inner-spin-button,
        .port-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
        .port-input { -moz-appearance: textfield; }
        .btn-row {
            display: flex; justify-content: flex-end; gap: 10px;
            margin-top: 16px; padding-top: 16px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
        }
        .btn {
            padding: 10px 20px; border-radius: 6px; border: none;
            font-size: 0.9rem; font-weight: 500; cursor: pointer;
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: linear-gradient(135deg, #4f8cff 0%, #3a6fd8 100%); color: #fff;
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #6ba0ff 0%, #4f8cff 100%);
            transform: translateY(-1px); box-shadow: 0 4px 12px rgba(79, 140, 255, 0.3);
        }
        .btn-primary:active { transform: translateY(0); }
        .btn-secondary {
            background: rgba(255, 255, 255, 0.08); color: #ccc;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }
        .btn-reset { background: transparent; color: #888; padding: 10px 14px; }
        .btn-reset:hover { color: #ff6b6b; }
        .status {
            padding: 10px 14px; border-radius: 6px; margin-top: 12px;
            display: none; font-size: 0.85rem;
        }
        .status.success {
            background: rgba(40, 167, 69, 0.15); color: #5cb85c;
            border: 1px solid rgba(40, 167, 69, 0.3); display: block;
        }
        .status.error {
            background: rgba(220, 53, 69, 0.15); color: #ff6b6b;
            border: 1px solid rgba(220, 53, 69, 0.3); display: block;
            white-space: pre-wrap; line-height: 1.45;
            scroll-margin: 20px;
        }
        .status.warning {
            background: rgba(255, 193, 7, 0.12); color: #ffc107;
            border: 1px solid rgba(255, 193, 7, 0.35); display: block;
            white-space: pre-wrap; line-height: 1.45;
            scroll-margin: 20px;
        }
        .status.warning.flash { animation: statusFlashWarn 1.6s ease-out 2; }
        .status.error.flash { animation: statusFlashError 1.6s ease-out 2; }
        @keyframes statusFlashWarn {
            0%, 100% {
                background: rgba(255, 193, 7, 0.12);
                box-shadow: 0 0 0 0 rgba(255, 193, 7, 0);
            }
            30% {
                background: rgba(255, 193, 7, 0.32);
                box-shadow: 0 0 0 4px rgba(255, 193, 7, 0.45);
            }
        }
        @keyframes statusFlashError {
            0%, 100% {
                background: rgba(220, 53, 69, 0.15);
                box-shadow: 0 0 0 0 rgba(220, 53, 69, 0);
            }
            30% {
                background: rgba(220, 53, 69, 0.35);
                box-shadow: 0 0 0 4px rgba(220, 53, 69, 0.5);
            }
        }
        .restart-area {
            display: none; margin-top: 12px; padding: 14px 16px;
            background: rgba(79, 140, 255, 0.08);
            border: 1px solid rgba(79, 140, 255, 0.25);
            border-radius: 10px;
            text-align: center;
        }
        .restart-area.visible { display: block; }
        .restart-msg { font-size: 0.85rem; color: #aaa; margin-bottom: 10px; line-height: 1.4; }
        .btn-restart {
            padding: 10px 28px; border-radius: 6px; border: none;
            font-size: 0.9rem; font-weight: 500; cursor: pointer;
            background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); color: #fff;
            transition: all 0.2s ease;
        }
        .btn-restart:hover {
            background: linear-gradient(135deg, #ffb74d 0%, #ff9800 100%);
            transform: translateY(-1px); box-shadow: 0 4px 12px rgba(255, 152, 0, 0.3);
        }
        .btn-restart:active { transform: translateY(0); }
        .url-toggle-row {
            display: flex; align-items: center; justify-content: center;
            margin-top: 14px; cursor: pointer; user-select: none;
            padding: 6px 0; opacity: 0.5; transition: opacity 0.2s;
        }
        .url-toggle-row:hover { opacity: 1; }
        .url-toggle-row .triangle {
            display: inline-block; width: 0; height: 0;
            border-left: 6px solid transparent; border-right: 6px solid transparent;
            border-top: 8px solid #4f8cff;
            transition: transform 0.3s ease; margin-right: 8px;
        }
        .url-toggle-row.expanded .triangle { transform: rotate(180deg); }
        .url-toggle-row .toggle-text { font-size: 0.75rem; color: #666; }
        .url-section {
            max-height: 0; overflow: hidden;
            transition: max-height 0.4s ease, opacity 0.3s ease; opacity: 0;
        }
        .url-section.visible { max-height: 800px; opacity: 1; margin-top: 12px; }
        .url-section-title {
            font-size: 0.85rem; color: #aaa; margin-bottom: 8px;
            display: flex; align-items: center; gap: 6px;
        }
        .url-item {
            display: flex; align-items: center; justify-content: space-between;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px; padding: 10px 14px; margin-bottom: 8px;
            transition: all 0.2s ease;
        }
        .url-item:hover {
            background: rgba(255, 255, 255, 0.06);
            border-color: rgba(79, 140, 255, 0.3);
        }
        .url-item .port-info { flex: 1; min-width: 0; }
        .url-item .port-name { font-size: 0.85rem; }
        .url-input {
            width: 220px; padding: 7px 10px; border-radius: 6px;
            border: 2px solid rgba(255, 255, 255, 0.1);
            background: rgba(0, 0, 0, 0.3); color: #fff;
            font-size: 0.8rem; font-family: 'Consolas', 'Monaco', monospace;
            transition: all 0.2s ease;
        }
        .url-input:hover { border-color: rgba(79, 140, 255, 0.5); }
        .url-input:focus {
            border-color: #4f8cff; background: rgba(79, 140, 255, 0.1);
            box-shadow: 0 0 0 3px rgba(79, 140, 255, 0.2) !important;
        }
        .url-input::placeholder { color: #555; font-style: italic; }
    </style>
</head>
<body>
    <div class="window-container">
        <div class="title-bar">
            <span class="title-bar-text">\u{1F50C} ${texts.portWindowTitle}</span>
            <button class="title-bar-close" id="btn-close" title="Close">\u2715</button>
        </div>
        <div class="content">
            <div class="content-scroll">
            <h2>${texts.portTitle}</h2>
            <p class="subtitle">${texts.portSubtitle}</p>
            <div class="tips">
                <strong>\u{1F4A1}</strong> ${texts.portTip}
            </div>
            <div class="port-list">
                <div class="port-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F310} ${texts.portMainServer}</div>
                        <div class="port-desc">${texts.portMainServerDesc}</div>
                    </div>
                    <input type="number" class="port-input" data-port="MAIN_SERVER_PORT" min="1" max="65535" step="1">
                </div>
                <div class="port-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F9E0} ${texts.portMemoryServer}</div>
                        <div class="port-desc">${texts.portMemoryServerDesc}</div>
                    </div>
                    <input type="number" class="port-input" data-port="MEMORY_SERVER_PORT" min="1" max="65535" step="1">
                </div>
                <div class="port-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F6E0}\u{FE0F} ${texts.portToolServer}</div>
                        <div class="port-desc">${texts.portToolServerDesc}</div>
                    </div>
                    <input type="number" class="port-input" data-port="TOOL_SERVER_PORT" min="1" max="65535" step="1">
                </div>
                <div class="port-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F9E9} ${texts.portPluginServer}</div>
                        <div class="port-desc">${texts.portPluginServerDesc}</div>
                    </div>
                    <input type="number" class="port-input" data-port="USER_PLUGIN_SERVER_PORT" min="1" max="65535" step="1">
                </div>
            </div>
            <div class="url-toggle-row" id="url-toggle">
                <span class="triangle"></span>
                <span class="toggle-text">${texts.urlToggleText}</span>
            </div>
            <div class="url-section" id="url-section">
                <div class="url-section-title">
                    \u{1F517} ${texts.urlSectionTitle}
                </div>
                <div class="tips" style="margin-bottom: 10px;">
                    ${texts.urlTip}
                </div>
                <div class="url-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F310} ${texts.portMainServer}</div>
                    </div>
                    <input type="text" class="url-input" data-url="MAIN_SERVER_URL" placeholder="https://x.x.x.x:xxxx">
                </div>
                <div class="url-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F9E0} ${texts.portMemoryServer}</div>
                    </div>
                    <input type="text" class="url-input" data-url="MEMORY_SERVER_URL" placeholder="https://x.x.x.x:xxxx">
                </div>
                <div class="url-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F6E0}\u{FE0F} ${texts.portToolServer}</div>
                    </div>
                    <input type="text" class="url-input" data-url="TOOL_SERVER_URL" placeholder="https://x.x.x.x:xxxx">
                </div>
                <div class="url-item">
                    <div class="port-info">
                        <div class="port-name">\u{1F9E9} ${texts.portPluginServer}</div>
                    </div>
                    <input type="text" class="url-input" data-url="USER_PLUGIN_SERVER_URL" placeholder="https://x.x.x.x:xxxx">
                </div>
            </div>
            <div id="status" class="status"></div>
            <div id="restart-area" class="restart-area">
                <div class="restart-msg">${texts.portRestartMsg}</div>
                <button class="btn-restart" id="btn-restart">${texts.portRestartNow}</button>
            </div>
            </div>
            <div class="btn-row">
                <button class="btn btn-reset" id="btn-reset">${texts.portResetDefault}</button>
                <button class="btn btn-secondary" id="btn-cancel">${texts.portCancel}</button>
                <button class="btn btn-primary" id="btn-save">${texts.portSave}</button>
            </div>
        </div>
    </div>
    <script>
        // contextIsolation:true 下页面无法 require('electron')，改用 preload 注入的 nekoPortSettings 桥
        const ipcRenderer = window.nekoPortSettings;

        const DEFAULT_PORTS = ${defaultsJson};
        let currentPorts = ${portsJson};
        let currentUrls = ${urlsJson};
        const i18n = ${i18nJson};

        document.addEventListener('DOMContentLoaded', () => {
            document.querySelectorAll('.port-input').forEach(input => {
                const key = input.dataset.port;
                if (currentPorts[key]) input.value = currentPorts[key];
            });

            // 加载已保存的自定义 URL
            document.querySelectorAll('.url-input').forEach(input => {
                const key = input.dataset.url;
                if (currentUrls[key]) input.value = currentUrls[key];
            });

            document.getElementById('btn-close').addEventListener('click', () => window.close());
            document.getElementById('btn-cancel').addEventListener('click', () => window.close());

            // URL 区域展开/收起
            document.getElementById('url-toggle').addEventListener('click', () => {
                document.getElementById('url-toggle').classList.toggle('expanded');
                document.getElementById('url-section').classList.toggle('visible');
            });

            document.getElementById('btn-reset').addEventListener('click', async () => {
                // 1) 先把 UI 填回默认值
                currentPorts = { ...DEFAULT_PORTS };
                document.querySelectorAll('.port-input').forEach(input => {
                    input.value = DEFAULT_PORTS[input.dataset.port];
                    input.classList.remove('error');
                });
                currentUrls = {};
                document.querySelectorAll('.url-input').forEach(input => {
                    input.value = '';
                });

                // 2) 立即持久化到磁盘 —— 避免"恢复默认后忘点保存就重新加载"的 UX 陷阱
                if (!ipcRenderer) { showStatus('success', i18n.portResetSuccess); return; }
                try {
                    const result = await ipcRenderer.savePortConfig({
                        ports: { ...DEFAULT_PORTS },
                        urls: {},
                    });
                    if (result && result.success) {
                        showStatus('success', i18n.portResetSuccess);
                        document.getElementById('restart-area').classList.add('visible');
                    } else {
                        showStatus('error', (result && result.error) || i18n.portSaveFailed);
                    }
                } catch (err) { showStatus('error', err.message); }
            });

            document.getElementById('btn-save').addEventListener('click', async () => {
                if (!ipcRenderer) { showStatus('error', 'IPC not available'); return; }

                const ports = {};
                let valid = true;
                document.querySelectorAll('.port-input').forEach(input => {
                    const val = parseInt(input.value, 10);
                    if (!Number.isInteger(val) || val < 1 || val > 65535) {
                        input.classList.add('error');
                        valid = false;
                    } else {
                        input.classList.remove('error');
                        ports[input.dataset.port] = val;
                    }
                });

                if (!valid) { showStatus('error', i18n.portInvalid); return; }

                const values = Object.values(ports);
                if (new Set(values).size !== values.length) {
                    showStatus('error', i18n.portDuplicate);
                    return;
                }

                // 收集自定义 URL（不做验证）
                const urls = {};
                document.querySelectorAll('.url-input').forEach(input => {
                    const val = input.value.trim();
                    if (val) urls[input.dataset.url] = val;
                });

                try {
                    const result = await ipcRenderer.savePortConfig({ ports, urls });
                    if (result.success) {
                        showStatus('success', i18n.portSaveSuccess);
                        document.getElementById('restart-area').classList.add('visible');
                    } else {
                        showStatus('error', result.error || i18n.portSaveFailed);
                    }
                } catch (err) { showStatus('error', err.message); }
            });

            document.getElementById('btn-restart').addEventListener('click', async () => {
                if (!ipcRenderer) return;
                try { await ipcRenderer.restartApp(); } catch (_) {}
            });
        });

        let _hideStatusTimer = null;
        function showStatus(type, message) {
            const el = document.getElementById('status');
            if (!el) return;
            el.className = 'status ' + type;
            el.textContent = message;
            if (_hideStatusTimer) { clearTimeout(_hideStatusTimer); _hideStatusTimer = null; }
            if (type === 'success') {
                _hideStatusTimer = setTimeout(() => { el.style.display = 'none'; }, 3000);
                return;
            }
            // error / warning：确保用户看到 —— 滚进视口 + 闪烁动画
            try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) { el.scrollIntoView(); }
            // 先移除再加 class，保证每次触发都重跑动画（同步 reflow 切断 batching）
            el.classList.remove('flash');
            void el.offsetWidth;
            el.classList.add('flash');
        }

        // 监听主进程异步送回的"自定义 URL 连通性探测"结果
        if (ipcRenderer) {
            ipcRenderer.onProbeResult((payload) => {
                if (!payload || payload.ok !== false) return;
                const tpl = i18n.portUrlUnreachable || '自定义 URL {url} 无法访问：{error}';
                const msg = tpl.replace('{url}', payload.url || '').replace('{error}', payload.error || '');
                showStatus('warning', msg);
            });
        }
    </script>
</body>
</html>`;
}

function getPortSettingsDataURL() {
  return `data:text/html;charset=utf-8,${encodeURIComponent(getPortSettingsHTML())}`;
}


  return getPortSettingsDataURL;
}

module.exports = {
  createPortSettingsDataUrlBuilder,
};
