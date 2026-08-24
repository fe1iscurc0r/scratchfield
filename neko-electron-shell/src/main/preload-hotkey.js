/**
 * preload-hotkey.js
 * Hotkey 窗口的 preload 脚本 —— contextBridge 白名单
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nekoHotkey', {
  getHotkeyConfig: () => ipcRenderer.invoke('get-hotkey-config'),
  saveHotkeyConfig: (config) => ipcRenderer.invoke('save-hotkey-config', config),
  getHotkeysEnabled: () => ipcRenderer.invoke('get-hotkeys-enabled'),
  toggleHotkeysEnabled: (enabled) => ipcRenderer.invoke('toggle-hotkeys-enabled', enabled),
  sendRecordingState: (isRecording) => ipcRenderer.send('hotkey-recording-state', isRecording),
  // 暗色模式监听
  onDarkModeToggle: (callback) => {
    const handler = (_event, enabled) => { try { callback(enabled); } catch (_) {} };
    ipcRenderer.on('toggle-dark-mode', handler);
    return () => { try { ipcRenderer.removeListener('toggle-dark-mode', handler); } catch (_) {} };
  },
});

console.log('[Preload-Hotkey] 初始化完成');