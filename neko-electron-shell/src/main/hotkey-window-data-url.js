'use strict';

const { escapeHtml, safeScriptJson } = require('./html-escape');

function createHotkeyWindowDataUrlBuilder(context) {
  const {
    getCurrentHotkeys,
    getCurrentLanguage,
    getDefaultHotkeys,
    getHotkeysEnabled,
    getTrayMenuLocales,
  } = context;

function getHotkeyHTML(baseUrl, isDark) {
  const currentHotkeys = getCurrentHotkeys();
  const DEFAULT_HOTKEYS = getDefaultHotkeys();
  const trayMenuLocales = getTrayMenuLocales();
  const currentLanguage = getCurrentLanguage();
  const hotkeysEnabled = getHotkeysEnabled();

  const configJson = safeScriptJson(currentHotkeys);
  const defaultJson = safeScriptJson(DEFAULT_HOTKEYS);

  // 获取当前语言的本地化文本
  const texts = trayMenuLocales[currentLanguage] || trayMenuLocales['en'];
  const i18nJson = safeScriptJson({
    hotkeyPressKey: texts.hotkeyPressKey,
    hotkeyResetSuccess: texts.hotkeyResetSuccess,
    hotkeySaveSuccess: texts.hotkeySaveSuccess,
    hotkeySaveFailed: texts.hotkeySaveFailed,
    hotkeyEnableHotkeys: texts.hotkeyEnableHotkeys,
    hotkeyDisableHotkeys: texts.hotkeyDisableHotkeys,
    hotkeyEnabled: texts.hotkeyEnabled,
    hotkeyDisabled: texts.hotkeyDisabled
  });

  // 字体资源（取自主应用静态服务器）—— baseUrl 缺省时回退到系统字体栈
  let fontBase = '';
  try {
    fontBase = typeof baseUrl === 'string' && baseUrl ? new URL(baseUrl).toString().replace(/\/$/, '') : '';
  } catch (e) {
    fontBase = '';
  }
  const fontFaceBlock = fontBase ? `
        @font-face {
          font-family: 'Comic Neue';
          src: url('${fontBase}/static/fonts/ComicNeue-Regular.ttf') format('truetype');
          font-weight: 400; font-style: normal; font-display: swap;
        }
        @font-face {
          font-family: 'Comic Neue';
          src: url('${fontBase}/static/fonts/ComicNeue-Bold.ttf') format('truetype');
          font-weight: 700; font-style: normal; font-display: swap;
        }` : '';
  const themeAttr = isDark ? 'dark' : 'light';

  return `<!DOCTYPE html>
<html lang="${escapeHtml(currentLanguage)}" data-theme="${themeAttr}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${escapeHtml(texts.hotkeyWindowTitle)} - N.E.K.O.</title>
    <style>
        ${fontFaceBlock}
        * { margin: 0; padding: 0; box-sizing: border-box; }
        button:focus-visible,
        .hotkey-input:focus-visible,
        [role="button"]:focus-visible {
          outline: 2px solid var(--hk-accent);
          outline-offset: 2px;
          box-shadow: 0 0 0 4px var(--hk-accent-soft);
        }
        html { color-scheme: light dark; }
        :root {
          --hk-bg: rgba(255, 255, 255, 0.82);
          --hk-bg-solid: #f7fafc;
          --hk-surface: rgba(255, 255, 255, 0.65);
          --hk-surface-hover: rgba(255, 255, 255, 0.85);
          --hk-border: rgba(23, 167, 255, 0.15);
          --hk-border-strong: rgba(23, 167, 255, 0.35);
          --hk-text: #1f2329;
          --hk-text-soft: #4a5568;
          --hk-text-muted: #8892a0;
          --hk-accent: #17A7FF;
          --hk-accent-soft: rgba(75, 212, 253, 0.18);
          --hk-gradient: linear-gradient(to right, #4BD4FD, #17A7FF);
          --hk-tips-bg: rgba(75, 212, 253, 0.12);
          --hk-input-bg: rgba(255, 255, 255, 0.9);
          --hk-shadow: 0 10px 30px rgba(23, 167, 255, 0.12), 0 2px 6px rgba(0, 0, 0, 0.06);
          --hk-danger: #ff6b6b;
          --hk-danger-bg: rgba(255, 107, 107, 0.12);
          --hk-success: #3cb371;
          --hk-success-bg: rgba(60, 179, 113, 0.14);
          --hk-title-bar-bg: linear-gradient(to right, #4BD4FD, #17A7FF);
          --hk-title-bar-text: #ffffff;
          --hk-scrollbar-thumb: rgba(23, 167, 255, 0.35);
          --hk-scrollbar-thumb-hover: rgba(23, 167, 255, 0.55);
        }
        [data-theme="dark"] {
          --hk-bg: rgba(30, 30, 30, 0.88);
          --hk-bg-solid: #1a1d21;
          --hk-surface: rgba(255, 255, 255, 0.04);
          --hk-surface-hover: rgba(255, 255, 255, 0.08);
          --hk-border: rgba(255, 255, 255, 0.08);
          --hk-border-strong: rgba(75, 212, 253, 0.4);
          --hk-text: #f0f0f0;
          --hk-text-soft: #c7cdd4;
          --hk-text-muted: #8892a0;
          --hk-accent: #3a9fd8;
          --hk-accent-soft: rgba(75, 212, 253, 0.12);
          --hk-gradient: linear-gradient(to right, #3a9fd8, #1d7cbf);
          --hk-tips-bg: rgba(75, 212, 253, 0.08);
          --hk-input-bg: rgba(0, 0, 0, 0.35);
          --hk-shadow: 0 12px 36px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.3);
          --hk-danger: #ff6b6b;
          --hk-danger-bg: rgba(255, 107, 107, 0.15);
          --hk-success: #5cb85c;
          --hk-success-bg: rgba(92, 184, 92, 0.15);
          --hk-title-bar-bg: linear-gradient(to right, #2a5ea8, #1d4b8a);
          --hk-title-bar-text: #f5f7fa;
          --hk-scrollbar-thumb: rgba(75, 212, 253, 0.3);
          --hk-scrollbar-thumb-hover: rgba(75, 212, 253, 0.5);
        }
        @media (prefers-color-scheme: dark) {
          :root:not([data-theme="light"]) {
            --hk-bg: rgba(30, 30, 30, 0.88);
            --hk-bg-solid: #1a1d21;
            --hk-surface: rgba(255, 255, 255, 0.04);
            --hk-surface-hover: rgba(255, 255, 255, 0.08);
            --hk-border: rgba(255, 255, 255, 0.08);
            --hk-border-strong: rgba(75, 212, 253, 0.4);
            --hk-text: #f0f0f0;
            --hk-text-soft: #c7cdd4;
            --hk-text-muted: #8892a0;
            --hk-accent: #3a9fd8;
            --hk-accent-soft: rgba(75, 212, 253, 0.12);
            --hk-gradient: linear-gradient(to right, #3a9fd8, #1d7cbf);
            --hk-tips-bg: rgba(75, 212, 253, 0.08);
            --hk-input-bg: rgba(0, 0, 0, 0.35);
            --hk-shadow: 0 12px 36px rgba(0, 0, 0, 0.4), 0 2px 8px rgba(0, 0, 0, 0.3);
            --hk-danger: #ff6b6b;
            --hk-danger-bg: rgba(255, 107, 107, 0.15);
            --hk-success: #5cb85c;
            --hk-success-bg: rgba(92, 184, 92, 0.15);
            --hk-title-bar-bg: linear-gradient(to right, #2a5ea8, #1d4b8a);
            --hk-title-bar-text: #f5f7fa;
            --hk-scrollbar-thumb: rgba(75, 212, 253, 0.3);
            --hk-scrollbar-thumb-hover: rgba(75, 212, 253, 0.5);
          }
        }
        html.theme-transitioning,
        html.theme-transitioning * {
          transition: background 250ms ease, background-color 250ms ease,
                      color 250ms ease, border-color 250ms ease,
                      box-shadow 250ms ease !important;
        }
        @media (prefers-reduced-motion: reduce) {
          html.theme-transitioning,
          html.theme-transitioning * { transition: none !important; }
        }
        html, body {
            width: 100%; height: 100%; overflow: hidden;
            background: transparent;
            font-family: 'Comic Neue', 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
        }
        .window-container {
            width: 100%; height: 100%;
            display: flex; flex-direction: column;
            background: var(--hk-bg);
            backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            border-radius: 12px; overflow: hidden;
            box-shadow: var(--hk-shadow);
            color: var(--hk-text);
        }
        .title-bar {
            display: flex; align-items: center; justify-content: space-between;
            height: 44px; padding: 0 14px;
            background: var(--hk-title-bar-bg);
            color: var(--hk-title-bar-text);
            -webkit-app-region: drag; user-select: none;
        }
        .title-bar-text { font-size: 0.95rem; font-weight: 600; letter-spacing: 0.2px; }
        .title-bar-close {
            -webkit-app-region: no-drag;
            width: 28px; height: 28px; border: none;
            background: rgba(255, 255, 255, 0.18); color: var(--hk-title-bar-text);
            font-size: 16px; cursor: pointer; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            transition: all 0.18s ease;
        }
        .title-bar-close:hover { background: rgba(255, 255, 255, 0.35); transform: scale(1.05); }
        .content {
            flex: 1; min-height: 0;
            padding: 18px 22px 20px 22px;
            color: var(--hk-text);
            display: flex; flex-direction: column; overflow: hidden;
        }
        h2 { margin-bottom: 4px; font-size: 1.3rem; color: var(--hk-text); font-weight: 700; }
        .subtitle { color: var(--hk-text-muted); font-size: 0.85rem; margin-bottom: 14px; }
        .tips {
            background: var(--hk-tips-bg);
            border: 1px solid var(--hk-border);
            border-radius: 10px; padding: 10px 14px; margin-bottom: 14px;
            font-size: 0.8rem; color: var(--hk-text-soft); line-height: 1.5;
        }
        .tips strong { color: var(--hk-accent); }
        .hotkey-list {
            display: flex; flex-direction: column; gap: 10px;
            flex: 1; min-height: 0;
            overflow-y: auto;
            padding-right: 6px; margin-right: -6px;
        }
        .hotkey-list::-webkit-scrollbar { width: 6px; }
        .hotkey-list::-webkit-scrollbar-track { background: transparent; }
        .hotkey-list::-webkit-scrollbar-thumb {
            background: var(--hk-scrollbar-thumb); border-radius: 3px;
        }
        .hotkey-list::-webkit-scrollbar-thumb:hover { background: var(--hk-scrollbar-thumb-hover); }
        .hotkey-item {
            display: flex; align-items: center; justify-content: space-between;
            background: var(--hk-surface);
            border: 1px solid var(--hk-border);
            border-radius: 14px; padding: 12px 16px;
            transition: all 0.2s ease;
        }
        .hotkey-item:hover {
            background: var(--hk-surface-hover);
            border-color: var(--hk-border-strong);
            transform: translateY(-1px);
        }
        .hotkey-info { flex: 1; min-width: 0; }
        .hotkey-name { font-size: 0.95rem; font-weight: 600; color: var(--hk-text); margin-bottom: 2px; }
        .hotkey-desc { font-size: 0.78rem; color: var(--hk-text-muted); }
        .hotkey-control {
            display: flex; align-items: center; gap: 8px;
            flex: 0 0 auto;
        }
        .hotkey-input {
            width: 120px; padding: 8px 14px; border-radius: 50px;
            border: 2px solid var(--hk-border);
            background: var(--hk-input-bg); color: var(--hk-text);
            font-size: 0.88rem; font-family: 'Consolas', 'Monaco', monospace;
            font-weight: 600;
            text-align: center; cursor: pointer;
            transition: all 0.2s ease; text-transform: uppercase;
        }
        .hotkey-input:hover { border-color: var(--hk-border-strong); }
        .hotkey-input:focus {
            border-color: var(--hk-accent); background: var(--hk-accent-soft);
            box-shadow: 0 0 0 3px var(--hk-accent-soft);
        }
        .hotkey-input.recording {
            border-color: var(--hk-danger); background: var(--hk-danger-bg);
            color: var(--hk-danger);
            animation: pulse 1s infinite;
        }
        @keyframes pulse {
            0%, 100% { box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.2); }
            50% { box-shadow: 0 0 0 6px rgba(255, 107, 107, 0.1); }
        }
        .hotkey-input::placeholder { color: var(--hk-text-muted); text-transform: none; font-weight: 400; }
        .hotkey-clear {
            width: 30px; height: 30px; border-radius: 50%;
            border: 1px solid var(--hk-border);
            background: var(--hk-surface); color: var(--hk-text-muted);
            display: inline-flex; align-items: center; justify-content: center;
            font-size: 0.85rem; font-weight: 700; line-height: 1;
            cursor: pointer; transition: all 0.2s ease;
        }
        .hotkey-clear:hover {
            border-color: var(--hk-danger);
            background: var(--hk-danger-bg);
            color: var(--hk-danger);
        }
        .hotkey-clear:disabled {
            opacity: 0.42;
            cursor: default;
            border-color: var(--hk-border);
            background: var(--hk-surface);
            color: var(--hk-text-muted);
        }
        .btn-row {
            display: flex; justify-content: flex-end; gap: 10px;
            margin-top: 14px; padding-top: 14px;
            border-top: 1px solid var(--hk-border);
        }
        .btn {
            padding: 10px 20px; border-radius: 24px; border: none;
            font-size: 0.9rem; font-weight: 600; cursor: pointer;
            font-family: inherit;
            transition: all 0.2s ease;
        }
        .btn-primary {
            background: var(--hk-gradient); color: #ffffff;
            box-shadow: 0 4px 12px rgba(23, 167, 255, 0.25);
        }
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 18px rgba(23, 167, 255, 0.4);
        }
        .btn-primary:active { transform: translateY(0); }
        .btn-secondary {
            background: var(--hk-surface); color: var(--hk-text-soft);
            border: 1px solid var(--hk-border);
        }
        .btn-secondary:hover { background: var(--hk-surface-hover); color: var(--hk-text); }
        .btn-reset { background: transparent; color: var(--hk-text-muted); padding: 10px 14px; }
        .btn-reset:hover { color: var(--hk-danger); }
        .btn-toggle {
            background: var(--hk-surface); color: var(--hk-text-soft);
            border: 1px solid var(--hk-border);
        }
        .btn-toggle:hover { background: var(--hk-surface-hover); color: var(--hk-text); }
        .btn-toggle.enabled {
            background: var(--hk-success-bg); color: var(--hk-success);
            border-color: var(--hk-success);
        }
        .btn-toggle.disabled {
            background: var(--hk-danger-bg); color: var(--hk-danger);
            border-color: var(--hk-danger);
        }
        .toggle-row {
            display: flex; justify-content: space-between; align-items: center;
            margin-top: 12px; padding: 12px 16px;
            background: var(--hk-surface);
            border: 1px solid var(--hk-border);
            border-radius: 14px;
        }
        .toggle-label { font-size: 0.9rem; color: var(--hk-text-soft); font-weight: 500; }
        .status {
            padding: 10px 14px; border-radius: 10px; margin-top: 10px;
            display: none; font-size: 0.85rem; font-weight: 500;
        }
        .status.success {
            background: var(--hk-success-bg); color: var(--hk-success);
            border: 1px solid var(--hk-success); display: block;
        }
        .status.error {
            background: var(--hk-danger-bg); color: var(--hk-danger);
            border: 1px solid var(--hk-danger); display: block;
        }
    </style>
</head>
<body>
    <div class="window-container">
        <div class="title-bar">
            <span class="title-bar-text">${texts.hotkeyWindowTitle}</span>
            <button class="title-bar-close" id="btn-close" title="Close">✕</button>
        </div>
        <div class="content">
            <h2>${texts.hotkeyGlobalHotkeys}</h2>
            <p class="subtitle">${texts.hotkeySubtitle}</p>
            <div class="tips">
                ${texts.hotkeyTip}
            </div>
            <div class="hotkey-list">
                <div class="hotkey-item">
                    <div class="hotkey-info">
                        <div class="hotkey-name">${texts.hotkeyVoiceSession}</div>
                        <div class="hotkey-desc">${texts.hotkeyVoiceSessionDesc}</div>
                    </div>
                    <div class="hotkey-control">
                        <input type="text" class="hotkey-input" data-action="toggleVoiceSession" readonly placeholder="${texts.hotkeyClickToSet}">
                        <button type="button" class="hotkey-clear" data-clear-action="toggleVoiceSession" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                    </div>
                </div>
                <div class="hotkey-item">
                    <div class="hotkey-info">
                        <div class="hotkey-name">${texts.hotkeyScreenShare}</div>
                        <div class="hotkey-desc">${texts.hotkeyScreenShareDesc}</div>
                    </div>
                    <div class="hotkey-control">
                        <input type="text" class="hotkey-input" data-action="toggleScreenShare" readonly placeholder="${texts.hotkeyClickToSet}">
                        <button type="button" class="hotkey-clear" data-clear-action="toggleScreenShare" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                    </div>
                </div>
                <div class="hotkey-item">
                    <div class="hotkey-info">
                        <div class="hotkey-name">${texts.hotkeyScreenshot}</div>
                        <div class="hotkey-desc">${texts.hotkeyScreenshotDesc}</div>
                    </div>
                    <div class="hotkey-control">
                        <input type="text" class="hotkey-input" data-action="triggerScreenshot" readonly placeholder="${texts.hotkeyClickToSet}">
                        <button type="button" class="hotkey-clear" data-clear-action="triggerScreenshot" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                    </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyMute}</div>
                    <div class="hotkey-desc">${texts.hotkeyMuteDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="toggleMute" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="toggleMute" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyToggleChat}</div>
                    <div class="hotkey-desc">${texts.hotkeyToggleChatDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="toggleReactChatWindow" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="toggleReactChatWindow" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyFocusChatInput}</div>
                    <div class="hotkey-desc">${texts.hotkeyFocusChatInputDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="focusReactChatInput" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="focusReactChatInput" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyGalgameChoiceA}</div>
                    <div class="hotkey-desc">${texts.hotkeyGalgameChoiceADesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="selectGalgameChoiceA" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="selectGalgameChoiceA" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyGalgameChoiceB}</div>
                    <div class="hotkey-desc">${texts.hotkeyGalgameChoiceBDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="selectGalgameChoiceB" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="selectGalgameChoiceB" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyGalgameChoiceC}</div>
                    <div class="hotkey-desc">${texts.hotkeyGalgameChoiceCDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="selectGalgameChoiceC" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="selectGalgameChoiceC" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
                <div class="hotkey-item">
                  <div class="hotkey-info">
                    <div class="hotkey-name">${texts.hotkeyToggleAllUI}</div>
                    <div class="hotkey-desc">${texts.hotkeyToggleAllUIDesc}</div>
                  </div>
                  <div class="hotkey-control">
                    <input type="text" class="hotkey-input" data-action="toggleAllUI" readonly placeholder="${texts.hotkeyClickToSet}">
                    <button type="button" class="hotkey-clear" data-clear-action="toggleAllUI" title="${texts.hotkeyClearShortcut}" aria-label="${texts.hotkeyClearShortcut}">X</button>
                  </div>
                </div>
            </div>
            <div class="toggle-row">
                <span class="toggle-label">${texts.hotkeyGlobalHotkeys}</span>
                <button class="btn btn-toggle enabled" id="btn-toggle">${texts.hotkeyDisableHotkeys}</button>
            </div>
            <div id="status" class="status"></div>
            <div class="btn-row">
                <button class="btn btn-reset" id="btn-reset">${texts.hotkeyResetDefault}</button>
                <button class="btn btn-secondary" id="btn-cancel">${texts.hotkeyCancel}</button>
                <button class="btn btn-primary" id="btn-save">${texts.hotkeySave}</button>
            </div>
        </div>
    </div>
    <script>
        let ipcRenderer;
        try { ipcRenderer = require('electron').ipcRenderer; } catch (e) { /* ignore */ }
        
        const DEFAULT_HOTKEYS = ${defaultJson};
        let currentHotkeys = ${configJson};
        const i18n = ${i18nJson};
        let recordingInput = null;
        let hotkeysEnabled = ${hotkeysEnabled};

        // 响应主进程广播的暗色模式切换
        try {
          if (ipcRenderer) {
            ipcRenderer.on('toggle-dark-mode', (_e, enabled) => {
              const root = document.documentElement;
              root.classList.add('theme-transitioning');
              root.setAttribute('data-theme', enabled ? 'dark' : 'light');
              setTimeout(() => root.classList.remove('theme-transitioning'), 300);
            });
          }
        } catch (e) { /* ignore */ }

        document.addEventListener('DOMContentLoaded', () => {
            updateInputValues();
            initInputs();
            initButtons();
        });

        function updateInputValues() {
            document.querySelectorAll('.hotkey-input').forEach(input => {
                const action = input.dataset.action;
                input.value = currentHotkeys[action] || '';
            });
            updateClearButtons();
        }

        function updateClearButtons() {
            document.querySelectorAll('.hotkey-clear').forEach(button => {
                const action = button.dataset.clearAction;
                button.disabled = !currentHotkeys[action];
            });
        }

        function initInputs() {
            document.querySelectorAll('.hotkey-input').forEach(input => {
                input.addEventListener('focus', () => startRecording(input));
                input.addEventListener('blur', () => stopRecording(input));
                input.addEventListener('keydown', (e) => {
                    e.preventDefault(); e.stopPropagation();
                    if (recordingInput !== input) return;
                    const key = parseKeyEvent(e);
                    if (key) {
                        input.value = key;
                        currentHotkeys[input.dataset.action] = key;
                        updateClearButtons();
                        stopRecording(input); input.blur();
                    }
                });
            });
        }

        function startRecording(input) {
            recordingInput = input;
            input.classList.add('recording');
            input.value = i18n.hotkeyPressKey;
            try { if (ipcRenderer) ipcRenderer.send('hotkey-recording-state', true); } catch (e) { /* ignore */ }
        }

        function stopRecording(input) {
            if (recordingInput === input) recordingInput = null;
            input.classList.remove('recording');
            try { if (ipcRenderer) ipcRenderer.send('hotkey-recording-state', false); } catch (e) { /* ignore */ }
            if (input.value === i18n.hotkeyPressKey) {
                input.value = currentHotkeys[input.dataset.action] || '';
            }
        }

        function parseKeyEvent(e) {
            const parts = [];
            if (e.ctrlKey) parts.push('Ctrl');
            if (e.altKey) parts.push('Alt');
            if (e.shiftKey) parts.push('Shift');
            if (e.metaKey) parts.push('Meta');
            let key = e.key;
            if (['Control', 'Alt', 'Shift', 'Meta'].includes(key)) return null;
            const keyMap = { ' ': 'Space', 'ArrowUp': 'Up', 'ArrowDown': 'Down', 'ArrowLeft': 'Left', 'ArrowRight': 'Right', 'Escape': 'Esc' };
            key = keyMap[key] || key;
            if (/^F\\d{1,2}$/.test(key)) parts.push(key);
            else if (/^[a-zA-Z]$/.test(key)) parts.push(key.toUpperCase());
            else if (/^[0-9]$/.test(key)) parts.push(key);
            else if (key.length === 1 || ['Space', 'Tab', 'Enter', 'Backspace', 'Delete', 'Home', 'End', 'PageUp', 'PageDown', 'Up', 'Down', 'Left', 'Right', 'Esc'].includes(key)) parts.push(key);
            else return null;
            return parts.join('+');
        }

        function initButtons() {
            document.getElementById('btn-close').addEventListener('click', () => window.close());
            document.getElementById('btn-cancel').addEventListener('click', () => window.close());
            document.querySelectorAll('.hotkey-clear').forEach(button => {
                button.addEventListener('click', () => {
                    const action = button.dataset.clearAction;
                    const input = document.querySelector('.hotkey-input[data-action="' + action + '"]');
                    currentHotkeys[action] = '';
                    if (input) {
                        input.value = '';
                        input.blur();
                    }
                    updateClearButtons();
                });
            });
            document.getElementById('btn-reset').addEventListener('click', () => {
                currentHotkeys = { ...DEFAULT_HOTKEYS };
                updateInputValues();
                showStatus('success', i18n.hotkeyResetSuccess);
            });
            document.getElementById('btn-save').addEventListener('click', async () => {
                if (!ipcRenderer) {
                    showStatus('error', 'IPC not available');
                    return;
                }
                try {
                    const result = await ipcRenderer.invoke('save-hotkey-config', currentHotkeys);
                    if (result.success) {
                        showStatus('success', i18n.hotkeySaveSuccess);
                    } else {
                        showStatus('error', result.error || i18n.hotkeySaveFailed);
                    }
                } catch (err) { showStatus('error', err.message); }
            });
            
            // 启用/禁用快捷键按钮
            const toggleBtn = document.getElementById('btn-toggle');
            updateToggleButton();
            toggleBtn.addEventListener('click', async () => {
                if (!ipcRenderer) return;
                try {
                    const result = await ipcRenderer.invoke('toggle-hotkeys-enabled', !hotkeysEnabled);
                    if (result.success) {
                        hotkeysEnabled = result.enabled;
                        updateToggleButton();
                        showStatus('success', hotkeysEnabled ? i18n.hotkeyEnabled : i18n.hotkeyDisabled);
                    }
                } catch (err) { showStatus('error', err.message); }
            });
        }
        
        function updateToggleButton() {
            const toggleBtn = document.getElementById('btn-toggle');
            if (hotkeysEnabled) {
                toggleBtn.textContent = i18n.hotkeyDisableHotkeys;
                toggleBtn.className = 'btn btn-toggle enabled';
            } else {
                toggleBtn.textContent = i18n.hotkeyEnableHotkeys;
                toggleBtn.className = 'btn btn-toggle disabled';
            }
        }

        function showStatus(type, message) {
            const statusEl = document.getElementById('status');
            statusEl.className = 'status ' + type;
            statusEl.textContent = message;
            if (type === 'success') setTimeout(() => { statusEl.style.display = 'none'; }, 2000);
        }
    </script>
</body>
</html>`;
}

function getHotkeyDataURL(baseUrl, isDark) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(getHotkeyHTML(baseUrl, isDark))}`;
}

// 向 hotkeyWindow 单点推送暗色模式变更（ipcRouter.broadcastGlobal 仅覆盖托管窗口）

  return getHotkeyDataURL;
}

module.exports = {
  createHotkeyWindowDataUrlBuilder,
};
