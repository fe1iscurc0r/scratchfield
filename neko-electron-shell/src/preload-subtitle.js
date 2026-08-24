/**
 * preload-subtitle.js
 * Subtitle 窗口的 preload 脚本
 *
 * 职责：
 * 1. 监听主进程转发的字幕文本与设置状态
 * 2. 提供独立字幕窗口的拖拽/缩放桥接
 * 3. 暗色模式与外链能力支持
 */

const { ipcRenderer } = require('electron');

const { WS_CHANNELS, WINDOW_CONTROL_CHANNELS, SUBTITLE_CHANNELS, PET_CHANNELS } = require('./ipc-channels');
const { setupDarkMode, setupElectronShell } = require('./preload-common');

// ===== 监听转写消息 =====
ipcRenderer.on(WS_CHANNELS.TRANSCRIPT, (event, data) => {
  window.__nekoSubtitleLatestTranscript = data;
  window.dispatchEvent(new CustomEvent('neko-ws-transcript', { detail: data }));
});

// ===== 监听状态同步（Pet → Subtitle）=====
ipcRenderer.on(SUBTITLE_CHANNELS.STATE_SYNC, (event, data) => {
  window.__nekoSubtitleLatestState = data;
  window.dispatchEvent(new CustomEvent('neko-subtitle-state-sync', { detail: data }));
});

ipcRenderer.on(SUBTITLE_CHANNELS.CLOSE_SETTINGS, (event, data) => {
  window.dispatchEvent(new CustomEvent('neko-subtitle-settings-closed', { detail: data || {} }));
});

ipcRenderer.on(PET_CHANNELS.AVATAR_BOUNDS_SYNC, (event, data) => {
  window.__nekoLatestAvatarBounds = data || null;
  window.dispatchEvent(new CustomEvent('neko-avatar-bounds-sync', { detail: data || null }));
});

// ===== 共享功能（暗色模式含 localStorage 持久化 + 事件派发、外部链接）=====
setupDarkMode();
setupElectronShell();

// ===== 窗口控制 =====
window.nekoSubtitle = {
  enableInteraction: () => ipcRenderer.send('set-ignore-mouse-events', false),
  disableInteraction: () => ipcRenderer.send('set-ignore-mouse-events', true, { forward: true }),
  getCursorPoint: () => ipcRenderer.invoke('get-cursor-point'),
  // 窗口移动和缩放（使用通用窗口控制通道）
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  resizeStart: (direction, options) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_START, {
    direction,
    minWidth: options && options.minWidth,
    minHeight: options && options.minHeight,
    cursor: options && options.cursor,
  }),
  resizeMove: (point) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_MOVE, {
    x: point && point.x,
    y: point && point.y,
  }),
  resizeStop: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_STOP),
  setSize: (w, h, options) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, {
    w,
    h,
    panelBounds: options && options.panelBounds,
  }),
  // 拖拽委托给主进程（避免 renderer 侧 setPosition 高频调用导致 Windows 透明窗口尺寸漂移）
  dragStart: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START),
  dragStop: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP),
  openSettings: (payload) => ipcRenderer.send(SUBTITLE_CHANNELS.OPEN_SETTINGS, payload || {}),
  closeSettings: () => ipcRenderer.send(SUBTITLE_CHANNELS.CLOSE_SETTINGS),
  updateSettingsWindow: (state) => ipcRenderer.send(SUBTITLE_CHANNELS.SETTINGS_WINDOW_UPDATE, state || {}),
  subscribeAvatarBounds: (active) => ipcRenderer.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC_SUBSCRIPTION, { active: !!active }),
  onAvatarBounds: (handler) => {
    if (typeof handler !== 'function') return () => {};
    const listener = (event) => handler(event.detail || null);
    window.addEventListener('neko-avatar-bounds-sync', listener);
    if (window.__nekoLatestAvatarBounds) {
      handler(window.__nekoLatestAvatarBounds);
    }
    return () => window.removeEventListener('neko-avatar-bounds-sync', listener);
  },
  // 设置变更 → 转发到 Pet 窗口
  changeSettings: (data) => ipcRenderer.send(SUBTITLE_CHANNELS.SETTINGS_CHANGE, data),
};

console.log('[Preload-Subtitle] 初始化完成');
