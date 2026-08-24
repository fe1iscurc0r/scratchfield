'use strict';

/**
 * trust-guard.js
 *
 *  Sender URL 信任校验：只允许受信任的来源调用 IPC handler。
 *  白名单协议：
 *  - data:   → 内嵌设置页面（feedback/port/hotkey）
 *  - file:   → 本地静态文件
 *  - http:   → localhost 回环（后端服务默认监听 localhost）
 *  - https:  → localhost 回环（SSL 开发环境）
 */
function isTrustedSender(event) {
  try {
    const frame = event.senderFrame;
    if (!frame || typeof frame.url !== 'string') return false;
    const parsed = new URL(frame.url);

    // 内嵌 data URL 允许（feedback/port/hotkey 设置页）
    if (parsed.protocol === 'data:') return true;
    // 本地 file 协议允许
    if (parsed.protocol === 'file:') return true;
    // localhost HTTP/HTTPS 回环允许（后端服务只监听本地）
    if ((parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
        (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '[::1]')) {
      return true;
    }
    // 其他来源拒绝
    return false;
  } catch {
    // 解析失败 → 拒绝
    return false;
  }
}

module.exports = {
  isTrustedSender,
};
