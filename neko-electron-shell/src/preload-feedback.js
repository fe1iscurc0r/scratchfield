/**
 * preload-feedback.js
 * Feedback 窗口的 preload 脚本 —— contextBridge 白名单
 *
 * contextIsolation:true 后页面无法直接 require('electron')，
 * 这里通过 contextBridge 暴露最小化的反馈提交能力（zip 打包 / 上传 / 关闭窗口）。
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nekoFeedback', {
  /**
   * 打包 logs 目录，返回 { zipPath, hasLogs, logCount }
   */
  zipLogs: () => ipcRenderer.invoke('zip-logs'),
  /**
   * 上传日志包与反馈内容
   * @param {string} zipPath - 受管临时目录内的反馈 zip 路径
   * @param {string} feedback - 反馈文本
   */
  uploadLogsAndFeedback: (zipPath, feedback) => ipcRenderer.invoke('upload-logs-and-feedback', zipPath, feedback),
  /**
   * 关闭反馈窗口
   */
  closeWindow: () => ipcRenderer.send('close-feedback-window'),
});

console.log('[Preload-Feedback] 初始化完成');
