/**
 * preload-jukebox.js
 * Jukebox 独立窗口 preload —— 提供窗口控制 API 和 VMD 动画 IPC 桥接
 *
 * 职责：
 * - 标记独立模式（__NEKO_JUKEBOX_STANDALONE__）
 * - 提供窗口拖拽（-webkit-app-region: drag）
 * - 桥接 VMD 动画控制命令到 Pet 窗口
 * - 暗色模式 + 外部链接
 */

const { ipcRenderer } = require('electron');
const { JUKEBOX_CHANNELS, WINDOW_CONTROL_CHANNELS } = require('./ipc-channels');
const { setupDarkMode, setupElectronShell, setupNativeDrag } = require('./preload-common');

// ===== 独立模式标记 =====
window.__NEKO_JUKEBOX_STANDALONE__ = true;

// ===== 共享功能 =====
setupDarkMode();
setupElectronShell();

// ===== 窗口拖拽 =====
// 标题左侧使用原生拖拽；按钮区域不放在父级 drag 热区内，避免 Chromium 命中测试抖动。
setupNativeDrag(
  ['.jukebox-header-left, .jukebox-header-left *'],
  ['.jukebox-content', '.jukebox-controls-row', '.jukebox-notice',
   '.jukebox-calibration-section',
   '.jukebox-header-buttons', '.jukebox-header-buttons button',
   '.jukebox-settings', '.jukebox-minimize', '.jukebox-close']
);

// ===== 窗口控制 API =====
window.nekoJukeboxWindow = {
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setSize: (w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, { w, h }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  hide: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.HIDE),
};

// ===== Jukebox Bridge：VMD 动画 + 窗口拖拽（供 jukebox-standalone.js 使用） =====
// 独立窗口无法直接访问 Pet 窗口的 mmdManager，通过 IPC 将高级命令发送到 Pet 窗口执行。
// 同时把窗口拖拽/尺寸 API 一并挂在这里。拖拽走主进程接管，缩放仍由
// jukebox-standalone.js 通过 RAF 合并 setBounds 更新，避免引入额外 resize 接管路径。
window.nekoJukeboxBridge = {
  // ---- VMD 动画 ----
  /**
   * 播放 VMD 动画
   * @param {string} vmdPath - VMD 文件路径
   */
  playVMD: (vmdPath) => {
    ipcRenderer.send(JUKEBOX_CHANNELS.VMD_PLAY, { vmdPath });
  },

  /**
   * 停止 VMD 动画
   * @param {boolean} skipIdleRestore - 是否跳过恢复待机动画
   */
  stopVMD: (skipIdleRestore) => {
    ipcRenderer.send(JUKEBOX_CHANNELS.VMD_STOP, { skipIdleRestore: !!skipIdleRestore });
  },

  /**
   * 暂停 VMD 动画
   */
  pauseVMD: () => {
    ipcRenderer.send(JUKEBOX_CHANNELS.VMD_PAUSE);
  },

  /**
   * 恢复 VMD 动画
   */
  resumeVMD: () => {
    ipcRenderer.send(JUKEBOX_CHANNELS.VMD_RESUME);
  },

  // ---- 窗口控制（jukebox-standalone.js 的 createWindowController 会探测这些方法） ----
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  hide: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.HIDE),

  // ---- 原生拖拽（触发后主进程接管，8ms 轮询 setBounds） ----
  // Jukebox 非透明窗口，shrink: false —— 不需要 Pet 的 shrink trick
  dragStart: (sx, sy) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, { shrink: false, sx, sy }),
  dragStop: (sx, sy) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP, { sx, sy }),
};

// ===== 关闭行为：隐藏窗口而非销毁 =====
// Jukebox 关闭时通知主进程（由 window-manager 拦截 close 事件实现 hide）
