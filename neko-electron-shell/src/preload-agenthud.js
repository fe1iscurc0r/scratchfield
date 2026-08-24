/**
 * preload-agenthud.js
 * AgentHUD 窗口的 preload 脚本
 *
 * 职责：
 * 1. 监听主进程转发的 agent_update 消息
 * 2. 暴露 agent toggle 接口给前端
 * 3. 暗色模式支持
 */

const { ipcRenderer } = require('electron');

const { WS_CHANNELS, AGENT_CHANNELS } = require('./ipc-channels');
const { setupDarkMode, setupElectronShell } = require('./preload-common');

// ===== 监听 Agent 任务更新 =====
ipcRenderer.on(WS_CHANNELS.AGENT_UPDATE, (event, data) => {
  window.dispatchEvent(new CustomEvent('neko-ws-agent-update', { detail: data }));
});

// ===== Agent 控制接口 =====
window.nekoAgent = {
  /**
   * 切换 agent 能力开关
   * @param {string} capability - 能力名称（如 'keyboard', 'browser', 'user_plugin'）
   * @param {boolean} enabled - 是否启用
   */
  toggle: (capability, enabled) => {
    ipcRenderer.send(AGENT_CHANNELS.TOGGLE, { capability, enabled });
  },
};

// ===== 共享功能（暗色模式含 toggle()、外部链接）=====
setupDarkMode();
setupElectronShell();

console.log('[Preload-AgentHUD] 初始化完成');
