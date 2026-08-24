/**
 * preload-chat.js
 * Chat 独立窗口的 preload 脚本
 *
 * 核心：替换 window.WebSocket 为 IPC 代理。
 * Chat 窗口不建立真实 WebSocket 连接，所有通信通过 Pet 窗口中转：
 *   send: Chat → IPC(ws-raw-send) → 主进程 → Pet → 真实 WebSocket → 后端
 *   recv: 后端 → 真实 WebSocket → Pet → IPC(ws-raw-message) → 主进程 → Chat
 */

const { ipcRenderer } = require('electron');
const { WS_PROXY_CHANNELS, WINDOW_CONTROL_CHANNELS } = require('./ipc-channels');
const { setupDarkMode, setupElectronShell, setupHostCapabilityBridge, setupGoodbyeChatComposerHiddenBridge, setupVoiceConfigSwitchingBridge, setupMusicPlayerBridge, setupToastOverride, suppressVoiceToast, setupNativeDrag, setupSettingsSync } = require('./preload-common');

// ===== WebSocket IPC 代理（必须在所有 JS 加载前安装）=====
(function() {
  const _Real = window.WebSocket;

  function WSProxy(url, protocols) {
    this.url = url;
    this.readyState = _Real.CONNECTING;
    this._onopen = null;
    this._onmessage = null;
    this._onclose = null;
    this._onerror = null;
    this._evts = {};

    var self = this;

    // Pet 窗口的真实 WebSocket 就绪 → 触发 onopen
    // 已 OPEN 情况下收到 READY（比如 dom-ready 后 ws-trigger-ready-recheck、
    // 或 Pet 真 WS reconnect 的 READY 晚于 CLOSED 到达）直接忽略：
    // 以前这里会主动 fire close→open "模拟重连"，但这会让 app-websocket.js 的 onclose
    // 错误地把它当成真断线、排队 auto-reconnect，3s 后造出永远停在 CONNECTING 的僵尸代理。
    // Pet 真 WS 如果真断线重连，会先走 CLOSED IPC 把代理置为 CLOSED，
    // 接下来的 READY 自然走下面的正常开启路径，不需要这里再模拟。
    ipcRenderer.on(WS_PROXY_CHANNELS.READY, function() {
      if (self.readyState === _Real.OPEN) {
        console.log('[WS Proxy] spurious READY on already-OPEN proxy, ignoring');
        return;
      }
      self.readyState = _Real.OPEN;
      self._fire('open', new Event('open'));
      console.log('[WS Proxy] Pet WebSocket ready, proxy OPEN');
    });

    // Pet 窗口的真实 WebSocket 关闭 → 通知前端
    // 只在代理当前 OPEN 时响应：CONNECTING 状态的新代理（例如切换档案时 handleCatgirlSwitch
    // 刚 new 出来的）不该吃下上一轮真 WS 生命周期遗留的 CLOSED 事件——
    // 否则会被误触发 close，进而让 app-websocket.js onclose 排一个 stale auto-reconnect，
    // 3s 后产出一个永远停在 CONNECTING 的僵尸代理，直接复现 "Start failed: WebSocket not connected"。
    ipcRenderer.on(WS_PROXY_CHANNELS.CLOSED, function(event, data) {
      if (self.readyState !== _Real.OPEN) return;
      self.readyState = _Real.CLOSED;
      var code = (data && data.code) || 1006;
      var reason = (data && data.reason) || '';
      self._fire('close', new CloseEvent('close', { code: code, reason: reason }));
      console.log('[WS Proxy] Pet WebSocket closed, code:', code);
    });

    // 监听 Pet 转发的后端消息
    ipcRenderer.on(WS_PROXY_CHANNELS.RAW_MESSAGE, function(event, rawData) {
      if (self.readyState !== _Real.OPEN) return;
      self._fire('message', new MessageEvent('message', { data: rawData }));
    });
  }

  WSProxy.prototype.send = function(data) {
    if (this.readyState !== _Real.OPEN) return;
    ipcRenderer.send(WS_PROXY_CHANNELS.RAW_SEND, data);
  };

  WSProxy.prototype.close = function(code, reason) {
    this.readyState = _Real.CLOSED;
    this._fire('close', new CloseEvent('close', { code: code || 1000, reason: reason || '' }));
  };

  WSProxy.prototype.addEventListener = function(type, fn) {
    if (!this._evts[type]) this._evts[type] = [];
    this._evts[type].push(fn);
  };

  WSProxy.prototype.removeEventListener = function(type, fn) {
    if (!this._evts[type]) return;
    this._evts[type] = this._evts[type].filter(function(f) { return f !== fn; });
  };

  WSProxy.prototype._fire = function(type, event) {
    var handler = this['_on' + type];
    if (typeof handler === 'function') try { handler(event); } catch(e) {}
    var list = this._evts[type] || [];
    for (var i = 0; i < list.length; i++) try { list[i](event); } catch(e) {}
  };

  Object.defineProperty(WSProxy.prototype, 'onopen', {
    get: function() { return this._onopen; }, set: function(v) { this._onopen = v; }
  });
  Object.defineProperty(WSProxy.prototype, 'onmessage', {
    get: function() { return this._onmessage; }, set: function(v) { this._onmessage = v; }
  });
  Object.defineProperty(WSProxy.prototype, 'onclose', {
    get: function() { return this._onclose; }, set: function(v) { this._onclose = v; }
  });
  Object.defineProperty(WSProxy.prototype, 'onerror', {
    get: function() { return this._onerror; }, set: function(v) { this._onerror = v; }
  });

  WSProxy.CONNECTING = _Real.CONNECTING;
  WSProxy.OPEN = _Real.OPEN;
  WSProxy.CLOSING = _Real.CLOSING;
  WSProxy.CLOSED = _Real.CLOSED;
  WSProxy.prototype.CONNECTING = _Real.CONNECTING;
  WSProxy.prototype.OPEN = _Real.OPEN;
  WSProxy.prototype.CLOSING = _Real.CLOSING;
  WSProxy.prototype.CLOSED = _Real.CLOSED;

  window.WebSocket = WSProxy;
  console.log('[Preload-Chat] WebSocket IPC 代理已安装');
})();

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
window.__NEKO_STANDALONE_CHAT__ = true;

// ===== 窗口控制 API =====
window.nekoChatWindow = {
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setSize: (w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, { w, h }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  setResizable: (v) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_RESIZABLE, { resizable: v }),
  dragStart: (sx, sy) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, { sx, sy }),
  dragStop:  () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP),
};

console.log('[Preload-Chat] 初始化完成');
