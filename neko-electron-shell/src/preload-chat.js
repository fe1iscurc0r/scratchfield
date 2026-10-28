/**
 * preload-chat.js
 * Chat 独立窗口的 preload 脚本
 *
 * Chat 窗口不建立真实 WebSocket 连接，所有通信通过 Pet 窗口中转：
 *   send: Chat → IPC(ws-raw-send) → 主进程 → Pet → 真实 WebSocket → 后端
 *   recv: 后端 → 真实 WebSocket → Pet → IPC(ws-raw-message) → 主进程 → Chat
 *
 * WO-278 装配后不再替换页面全局构造器（contextBridge 也顶替不了它）：
 * preload 只暴露 `nekoWebSocket` 工厂，页面由 /static/app/ws-adapter.js 调用并补回原生语义。
 */

const { ipcRenderer, contextBridge } = require('electron');
const { WS_PROXY_CHANNELS, WINDOW_CONTROL_CHANNELS } = require('./ipc-channels');
const { createWebSocketBridge } = require('./websocket-bridge');
const { setupDarkMode, setupElectronShell, setupHostCapabilityBridge, setupGoodbyeChatComposerHiddenBridge, setupVoiceConfigSwitchingBridge, setupMusicPlayerBridge, setupToastOverride, suppressVoiceToast, setupNativeDrag, setupSettingsSync } = require('./preload-common');

// 隔离走 contextBridge，非隔离直接挂 window（与 preload-jukebox.js 同构）
function exposeToPage(name, value) {
  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld(name, value);
  } else {
    window[name] = value;
  }
}

// ===== WebSocket 桥（必须在所有页面 JS 加载前就位）=====
exposeToPage('nekoWebSocket', createWebSocketBridge({
  ipc: ipcRenderer,
  channels: WS_PROXY_CHANNELS,
}));

// ===== 共享功能（暗色模式、外部链接、Toast、原生拖拽、设置同步）=====
setupDarkMode();
setupElectronShell();
setupHostCapabilityBridge();
setupGoodbyeChatComposerHiddenBridge();
setupVoiceConfigSwitchingBridge();
setupMusicPlayerBridge();
setupToastOverride();
suppressVoiceToast();
setupSettingsSync({ role: 'chat' });
setupNativeDrag(
  ['#chat-header', '#text-input-area'],
  [
    '#toggle-chat-btn',
    '#text-input-area textarea',
    '#text-input-area input',
    '#text-input-area button',
    '#text-input-area a',
    '#text-input-area [contenteditable]',
    '#text-input-area select',
    '#neko-resize-handle',
  ]
);

// ===== 独立窗口标志 =====
exposeToPage('__NEKO_STANDALONE_CHAT__', true);

// ===== 窗口控制 API =====
exposeToPage('nekoChatWindow', {
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setSize: (w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, { w, h }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  setResizable: (v) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_RESIZABLE, { resizable: v }),
  dragStart: (sx, sy) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, { sx, sy }),
  dragStop:  () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP),
});

console.log('[Preload-Chat] 初始化完成');
