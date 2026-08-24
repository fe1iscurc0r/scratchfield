/**
 * preload-toast.js
 * Toast 窗口的 preload 脚本
 *
 * 职责：通过 contextBridge 暴露 IPC 监听 API，让 toast.html 页面
 * 能接收主进程转发的 toast 消息，并控制鼠标穿透状态。
 */

const { ipcRenderer, contextBridge } = require('electron');
const { TOAST_CHANNELS } = require('./ipc-channels');

contextBridge.exposeInMainWorld('nekoToastAPI', {
  onShowStatusToast: (callback) => {
    ipcRenderer.on(TOAST_CHANNELS.STATUS, (event, data) => callback(data));
  },
  onShowVoicePreparing: (callback) => {
    ipcRenderer.on(TOAST_CHANNELS.VOICE_PREPARING, (event, data) => callback(data));
  },
  onHideVoicePreparing: (callback) => {
    ipcRenderer.on(TOAST_CHANNELS.VOICE_HIDE_PREPARING, () => callback());
  },
  onShowReadyToSpeak: (callback) => {
    ipcRenderer.on(TOAST_CHANNELS.VOICE_READY, (event, data) => callback(data));
  },
  onShowProminentNotice: (callback) => {
    ipcRenderer.on(TOAST_CHANNELS.PROMINENT, (event, data) => callback(data));
  },
  // prominent notice 显示时需要取消鼠标穿透，关闭后恢复
  setMouseThrough: (ignore) => {
    ipcRenderer.send('set-ignore-mouse-events', ignore);
  },
});

console.log('[Preload-Toast] 初始化完成');
