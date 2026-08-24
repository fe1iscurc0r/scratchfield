/**
 * preload-child.js
 * 同源子窗口通用桥接。
 *
 * window.open 打开的子窗口使用 contextIsolation=true，因此共享宿主能力需要通过
 * contextBridge 暴露，而不是直接写入页面 window。
 */

const { ipcRenderer, contextBridge } = require('electron');
const {
  setupDarkMode,
  setupElectronShell,
  setupHostCapabilityBridge,
  setupVoiceConfigSwitchingBridge,
} = require('./preload-common');

setupDarkMode();
setupElectronShell();
setupHostCapabilityBridge();
setupVoiceConfigSwitchingBridge();

if (process.platform === 'linux') {
  const forwardModelManagerMainUiState = (hidden) => {
    ipcRenderer.send('neko:model-manager-main-ui-hidden', { hidden: !!hidden });
  };

  window.addEventListener('message', (event) => {
    if (event && event.origin && event.origin !== window.location.origin) return;
    const action = event && event.data && event.data.action;
    if (action === 'hide_main_ui') forwardModelManagerMainUiState(true);
    if (action === 'show_main_ui') forwardModelManagerMainUiState(false);
  });
}

// 窗口控制扩展：最小化、最大化/恢复
if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
  contextBridge.exposeInMainWorld('nekoWindowControl', {
    minimize: () => ipcRenderer.invoke('neko:host:minimize-window'),
    restore: () => ipcRenderer.invoke('neko:host:restore-window'),
    maximize: () => ipcRenderer.invoke('neko:host:maximize-window'),
    isMaximized: () => ipcRenderer.invoke('neko:host:is-maximized'),
  });
} else {
  window.nekoWindowControl = {
    minimize: () => ipcRenderer.invoke('neko:host:minimize-window'),
    restore: () => ipcRenderer.invoke('neko:host:restore-window'),
    maximize: () => ipcRenderer.invoke('neko:host:maximize-window'),
    isMaximized: () => ipcRenderer.invoke('neko:host:is-maximized'),
  };
}
