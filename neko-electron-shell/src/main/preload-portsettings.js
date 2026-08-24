/**
 * preload-portsettings.js
 * PortSettings 窗口的 preload 脚本 —— contextBridge 白名单
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nekoPortSettings', {
  savePortConfig: (payload) => ipcRenderer.invoke('save-port-config', payload),
  restartApp: () => ipcRenderer.invoke('restart-app'),
  // 监听主进程异步推送的"自定义 URL 连通性探测"结果
  onProbeResult: (callback) => {
    const handler = (_event, payload) => { try { callback(payload); } catch (_) {} };
    ipcRenderer.on('port-config-probe-result', handler);
    return () => { try { ipcRenderer.removeListener('port-config-probe-result', handler); } catch (_) {} };
  },
  // 暗色模式监听
  onDarkModeToggle: (callback) => {
    const handler = (_event, enabled) => { try { callback(enabled); } catch (_) {} };
    ipcRenderer.on('toggle-dark-mode', handler);
    return () => { try { ipcRenderer.removeListener('toggle-dark-mode', handler); } catch (_) {} };
  },
});

console.log('[Preload-PortSettings] 初始化完成');