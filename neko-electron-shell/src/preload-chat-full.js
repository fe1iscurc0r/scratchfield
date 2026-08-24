/**
 * preload-chat-react.js
 * Chat 独立窗口的 preload 脚本
 *
 * 设计原则：Electron 只做加载器，所有 UI 逻辑由 N.E.K.O. 后端页面处理。
 * 此 preload 只负责三件事：
 *   1. WebSocket → IPC 代理（页面看到的 WS 实际走 Pet 窗口的连接）
 *   2. 窗口管理（drag/resize/collapse → 主进程 WINDOW_CONTROL_CHANNELS）
 *   3. Toast / 暗色模式 / 外部链接
 *
 * 不注入任何 stub（appButtons、appState、lanlan_config 等全由页面自己的 app-*.js 提供）。
 */

const { ipcRenderer } = require('electron');
const { WINDOW_CONTROL_CHANNELS, WS_PROXY_CHANNELS, CHAT_CHANNELS, CHAT_ACTION_CHANNELS, JUKEBOX_CHANNELS, SUBTITLE_CHANNELS, PET_CHANNELS } = require('./ipc-channels');
const { setupToastOverride, suppressVoiceToast, setupDarkMode, setupElectronShell, setupHostCapabilityBridge, setupGoodbyeChatComposerHiddenBridge, setupVoiceConfigSwitchingBridge, setupMusicPlayerBridge, setupSettingsSync, syncSubtitleToggleFromWindow } = require('./preload-common');

// ===== 1. WebSocket → IPC 代理 =====
// chat.html 加载了 app-websocket.js，它会 new WebSocket(url)。
// 在页面脚本运行前替换 window.WebSocket，使其通过 Pet 窗口的 WS 中转，
// 不建立自己的连接。
//
// 关键设计：IPC 监听注册在 preload 全局作用域（而非 WSProxy 构造函数内），
// 解决竞态问题——Pet 的 WS READY / greeting RAW_MESSAGE 可能在页面 JS
// 执行 new WebSocket() 之前到达。缓冲区暂存这些早到的消息，
// WSProxy 构造时一次性重放。
(function setupWSProxy() {
  const _Real = window.WebSocket;

  // ---- 修复辅助：排空 realistic queue（跨模式切换时防止气泡乱序）----
  // app-chat.js 的 realistic 模式会把待显示的句子放入 _realisticGeminiQueue，
  // 并用 async processRealisticQueue 延时逐个创建 bubble。
  // 若用户在 queue 未排空时切换到 merge mode，新一轮 isNewMessage 走 merge 分支
  // 不会清理 queue，残留的 async 循环会在新 bubble 之后创建旧 bubble，导致顺序错误。
  // 此函数同步排空 queue：立即创建所有待排队 bubble，并使 async 循环的版本号失效。
  function _flushRealisticQueue() {
    var queue = window._realisticGeminiQueue;
    if (!Array.isArray(queue) || queue.length === 0) return;

    // 立即同步创建所有待排队的 bubble
    if (typeof window.createGeminiBubble === 'function') {
      for (var i = 0; i < queue.length; i++) {
        try { window.createGeminiBubble(queue[i]); } catch (_) {}
      }
    }
    window._realisticGeminiQueue = [];

    // 使正在运行的 processRealisticQueue async 循环失效（它通过 version 检查退出）
    window._realisticGeminiVersion = (window._realisticGeminiVersion || 0) + 1;
    // 重置并发锁，让下次 processRealisticQueue 可以正常启动
    window._isProcessingRealisticQueue = false;
  }

  // ---- 全局 IPC 消息缓冲（WSProxy 构造前到达的消息不丢失）----
  var _wsProxy = null;
  var _petSessionEpoch = null;
  var _petGeneration = null;
  var _wsBuffer = { ready: false, readyData: null, messages: [], closed: null };

  function _readSessionEpoch(data) {
    var epoch = data && typeof data.sessionEpoch === 'number' ? data.sessionEpoch : null;
    return Number.isFinite(epoch) ? epoch : null;
  }
  function _readGeneration(data) {
    var generation = data && typeof data.generation === 'number' ? data.generation : null;
    return Number.isFinite(generation) ? generation : null;
  }
  function _isStalePetLifecycle(data) {
    var epoch = _readSessionEpoch(data);
    var generation = _readGeneration(data);
    if (epoch !== null && _petSessionEpoch !== null) {
      if (epoch < _petSessionEpoch) return true;
      if (epoch > _petSessionEpoch) return false;
    }
    return generation !== null && _petGeneration !== null && generation < _petGeneration;
  }
  function _rememberPetLifecycle(data) {
    var epoch = _readSessionEpoch(data);
    var generation = _readGeneration(data);
    if (epoch !== null) {
      if (_petSessionEpoch !== null && epoch < _petSessionEpoch) {
        return { sessionEpoch: epoch, generation: generation };
      }
      if (_petSessionEpoch === null || epoch > _petSessionEpoch) {
        _petSessionEpoch = epoch;
        _petGeneration = null;
      }
    }
    if (generation !== null && (_petGeneration === null || generation > _petGeneration)) {
      _petGeneration = generation;
    }
    return { sessionEpoch: epoch, generation: generation };
  }

  ipcRenderer.on(WS_PROXY_CHANNELS.CONNECTING, function (_event, data) {
    if (_isStalePetLifecycle(data)) return;
    var lifecycle = _rememberPetLifecycle(data);
    if (lifecycle.generation === null) return;
    if (_wsBuffer.ready && _isStalePetLifecycle(_wsBuffer.readyData)) {
      _wsBuffer.ready = false;
      _wsBuffer.readyData = null;
      _wsBuffer.messages = [];
    }
    if (_wsBuffer.closed && _isStalePetLifecycle(_wsBuffer.closed)) {
      _wsBuffer.closed = null;
    }
    if (_wsProxy) {
      _wsProxy._handleConnecting(data);
    }
  });
  ipcRenderer.on(WS_PROXY_CHANNELS.READY, function (_event, data) {
    if (_isStalePetLifecycle(data)) return;
    _rememberPetLifecycle(data);
    if (_wsProxy) {
      _wsProxy._handleReady(data);
    } else {
      _wsBuffer.ready = true;
      _wsBuffer.readyData = data || null;
      _wsBuffer.closed = null;
      _wsBuffer.messages = [];
    }
  });
  ipcRenderer.on(WS_PROXY_CHANNELS.RAW_MESSAGE, function (_event, rawData) {
    // ---- 修复：新一轮消息到达时，立即排空上一轮的 realistic queue ----
    // 当 merge mode 在上一轮 realistic queue 尚未排空时被开启，
    // 新一轮 isNewMessage=true 走 merge 分支不会清理 queue，
    // 导致 queue 中残留的旧气泡在新气泡之后创建，排序倒置。
    // 在消息抵达页面 JS 之前拦截并排空，保证 bubble 顺序正确。
    try {
      if (typeof rawData === 'string') {
        var parsed = JSON.parse(rawData);
        if (parsed && parsed.type === 'gemini_response' && parsed.isNewMessage) {
          _flushRealisticQueue();
        }
      }
    } catch (_e) { /* ignore parse errors */ }

    if (_wsProxy) {
      _wsProxy._handleRawMessage(rawData);
    } else if (_wsBuffer.ready) {
      _wsBuffer.messages.push(rawData);
    }
  });
  ipcRenderer.on(WS_PROXY_CHANNELS.CLOSED, function (_event, data) {
    if (_isStalePetLifecycle(data)) return;
    if (_wsProxy) {
      _wsProxy._handleClosed(data);
    } else {
      _wsBuffer.ready = false;
      _wsBuffer.readyData = null;
      _wsBuffer.closed = data;
      _wsBuffer.messages = [];
    }
  });

  // ---- WSProxy 构造函数 ----
  function WSProxy(url, protocols) {
    this.url = url;
    this.readyState = _Real.CONNECTING;
    this._onopen = null;
    this._onmessage = null;
    this._onclose = null;
    this._onerror = null;
    this._evts = {};
    // 仅在 constructor 真的安排了 setTimeout(0) 派发 READY 时（即"页面构造时
    // _wsBuffer.ready 已经为 true"的首构造场景）才打开缓冲。这是修 chat.html
    // 首次 greeting 文字丢失的目标场景：READY 早到→构造→setTimeout 派发之前
    // 的空窗里 IPC RAW_MESSAGE 进来。
    //
    // 不在所有 CONNECTING 阶段缓冲——reconnect / 角色切换路径下，page 主动
    // 重建 WSProxy 时 _wsBuffer.ready 是 false，新代 ws 还没 OPEN，此时跨代
    // 残留的 RAW_MESSAGE（pet 那边没装 active-socket gate）若被缓冲、等新代
    // READY 到了 drain，就会把上一代的尾巴泄漏进新会话（Codex P1 指出）。
    // 这种 CONNECTING 仍按原行为丢，保留跨代过滤。
    this._pendingMessages = [];
    this._readyPending = false;
    this._closePending = false;
    this._closePendingSessionEpoch = null;
    this._closePendingGeneration = null;
    this._petSessionEpoch = _petSessionEpoch;
    this._petGeneration = _petGeneration;
    _wsProxy = this;

    // 用 setTimeout(0) 派发 'open' 是为了让页面 JS 的 onopen/onmessage handler 先设好。
    if (_wsBuffer.ready) {
      // pre-constructor 到达的消息按原顺序作为 _pendingMessages 起点。
      this._pendingMessages = _wsBuffer.messages.slice();
      this._readyPending = true;
      var readyData = _wsBuffer.readyData;
      _wsBuffer.ready = false;
      _wsBuffer.readyData = null;
      _wsBuffer.messages = [];
      var self = this;
      setTimeout(function () { self._handleReady(readyData); }, 0);
    } else if (_wsBuffer.closed) {
      var closedData = _wsBuffer.closed;
      _wsBuffer.closed = null;
      var self = this;
      this._closePending = true;
      this._closePendingSessionEpoch = _readSessionEpoch(closedData);
      this._closePendingGeneration = _readGeneration(closedData);
      setTimeout(function () { self._handleClosed(closedData); }, 0);
    }
  }

  // ---- IPC 事件处理方法 ----
  WSProxy.prototype._isStaleLifecycle = function (data) {
    var epoch = _readSessionEpoch(data);
    var generation = _readGeneration(data);
    if (epoch !== null && this._petSessionEpoch !== null) {
      if (epoch < this._petSessionEpoch) return true;
      if (epoch > this._petSessionEpoch) return false;
    }
    return generation !== null && this._petGeneration !== null && generation < this._petGeneration;
  };
  WSProxy.prototype._adoptLifecycle = function (data) {
    if (_isStalePetLifecycle(data)) {
      return { sessionEpoch: _readSessionEpoch(data), generation: _readGeneration(data) };
    }
    var lifecycle = _rememberPetLifecycle(data);
    var epoch = lifecycle.sessionEpoch;
    var generation = lifecycle.generation;
    if (epoch !== null) {
      if (this._petSessionEpoch === null || epoch > this._petSessionEpoch) {
        this._petSessionEpoch = epoch;
        this._petGeneration = null;
      }
    }
    if (generation !== null && (this._petGeneration === null || generation > this._petGeneration)) {
      this._petGeneration = generation;
    }
    return lifecycle;
  };
  WSProxy.prototype._cancelOlderClose = function (lifecycle) {
    if (!this._closePending) return;
    var epoch = lifecycle && lifecycle.sessionEpoch;
    var generation = lifecycle && lifecycle.generation;
    var newerEpoch = epoch !== null && this._closePendingSessionEpoch !== null && epoch > this._closePendingSessionEpoch;
    var sameEpoch = epoch === this._closePendingSessionEpoch || epoch === null || this._closePendingSessionEpoch === null;
    var newerGeneration = sameEpoch && generation !== null && this._closePendingGeneration !== null && generation > this._closePendingGeneration;
    if (newerEpoch || newerGeneration) {
      this._closePending = false;
      this._closePendingSessionEpoch = null;
      this._closePendingGeneration = null;
    }
  };
  WSProxy.prototype._handleConnecting = function (data) {
    if (this._isStaleLifecycle(data) || _isStalePetLifecycle(data)) return;
    var lifecycle = this._adoptLifecycle(data);
    this._cancelOlderClose(lifecycle);
  };
  WSProxy.prototype._handleReady = function (data) {
    if (this._isStaleLifecycle(data) || _isStalePetLifecycle(data)) return;
    var lifecycle = this._adoptLifecycle(data);
    this._cancelOlderClose(lifecycle);
    if (this.readyState === _Real.OPEN) return; // 已 OPEN，忽略冗余 READY（recheck 场景）
    // close 已经先到的情况下不能再翻回 OPEN（否则页面会看到 close-then-open 的反序）。
    // 顺手清掉暂存——proxy 不会再有机会把它们送出去。
    if (this.readyState === _Real.CLOSED || this._closePending) {
      this._pendingMessages = [];
      this._readyPending = false;
      return;
    }
    this.readyState = _Real.OPEN;
    this._readyPending = false;
    this._fire('open', new Event('open'));
    // 'open' 派发完再 drain，保证页面 onopen 先于 onmessage 跑到。drain 是同步循环，
    // 期间不会有新 IPC 事件挤进来（Electron IPC 是 task 级，不是 microtask）。
    // 但 page 的 onopen / 早期 onmessage handler 可能同步 close() 把 readyState 翻
    // CLOSED——drain 时走 _handleRawMessage 让 per-item readyState gate 生效，
    // 避免 close 事件之后还继续派 message 造成反序。
    var pending = this._pendingMessages;
    this._pendingMessages = [];
    for (var i = 0; i < pending.length; i++) {
      this._handleRawMessage(pending[i]);
    }
  };
  WSProxy.prototype._handleRawMessage = function (rawData) {
    if (this.readyState === _Real.OPEN) {
      this._fire('message', new MessageEvent('message', { data: rawData }));
    } else if (this.readyState === _Real.CONNECTING && this._readyPending) {
      // 仅在 constructor 已安排 setTimeout(0) 派发 READY 的窗口里缓冲——首构造场景。
      // reconnect / 切角色路径下 _readyPending 始终为 false，跨代残留按原行为丢。
      this._pendingMessages.push(rawData);
    }
    // 其它 CONNECTING / CLOSED：丢弃（与原行为一致）。
  };
  WSProxy.prototype._handleClosed = function (data) {
    if (this._isStaleLifecycle(data) || _isStalePetLifecycle(data)) return;
    if (this.readyState === _Real.CLOSED) {
      this._pendingMessages = [];
      return;
    }
    if (this.readyState === _Real.CONNECTING) {
      var self = this;
      this._adoptLifecycle(data);
      this._closePending = true;
      this._closePendingSessionEpoch = _readSessionEpoch(data);
      this._closePendingGeneration = _readGeneration(data);
      setTimeout(function () {
        if (!self._closePending || self._isStaleLifecycle(data) || _isStalePetLifecycle(data)) return;
        self._finishClosed(data);
      }, 0);
      return;
    }
    if (this.readyState !== _Real.OPEN) {
      this._pendingMessages = [];
      return;
    }
    this._finishClosed(data);
  };
  WSProxy.prototype._finishClosed = function (data) {
    this.readyState = _Real.CLOSED;
    this._readyPending = false;
    this._closePending = false;
    this._closePendingSessionEpoch = null;
    this._closePendingGeneration = null;
    // 之前还没派发出去的暂存消息一并丢弃。
    this._pendingMessages = [];
    this._fire('close', new CloseEvent('close', { code: (data && data.code) || 1006, reason: (data && data.reason) || '' }));
  };

  // ---- 原有方法 ----
  WSProxy.prototype.send = function (data) {
    if (this.readyState !== _Real.OPEN) return;
    ipcRenderer.send(WS_PROXY_CHANNELS.RAW_SEND, data);
  };
  WSProxy.prototype.close = function (code, reason) {
    this.readyState = _Real.CLOSED;
    this._closePending = false;
    this._closePendingSessionEpoch = null;
    this._closePendingGeneration = null;
    // 翻 CLOSED 同时清掉暂存——之后即使 IPC CLOSED 再到达走 _handleClosed 早返回，
    // 也不会让 _pendingMessages 跟着 proxy 实例一直留在内存里。
    this._pendingMessages = [];
    this._fire('close', new CloseEvent('close', { code: code || 1000, reason: reason || '' }));
  };
  WSProxy.prototype.addEventListener = function (type, fn) {
    if (!this._evts[type]) this._evts[type] = [];
    this._evts[type].push(fn);
  };
  WSProxy.prototype.removeEventListener = function (type, fn) {
    if (!this._evts[type]) return;
    this._evts[type] = this._evts[type].filter(function (f) { return f !== fn; });
  };
  WSProxy.prototype._fire = function (type, event) {
    var handler = this['_on' + type];
    if (typeof handler === 'function') try { handler(event); } catch (e) {}
    var list = this._evts[type] || [];
    for (var i = 0; i < list.length; i++) try { list[i](event); } catch (e) {}
  };
  Object.defineProperty(WSProxy.prototype, 'onopen', { get() { return this._onopen; }, set(v) { this._onopen = v; } });
  Object.defineProperty(WSProxy.prototype, 'onmessage', { get() { return this._onmessage; }, set(v) { this._onmessage = v; } });
  Object.defineProperty(WSProxy.prototype, 'onclose', { get() { return this._onclose; }, set(v) { this._onclose = v; } });
  Object.defineProperty(WSProxy.prototype, 'onerror', { get() { return this._onerror; }, set(v) { this._onerror = v; } });
  WSProxy.CONNECTING = _Real.CONNECTING;
  WSProxy.OPEN = _Real.OPEN;
  WSProxy.CLOSING = _Real.CLOSING;
  WSProxy.CLOSED = _Real.CLOSED;
  WSProxy.prototype.CONNECTING = _Real.CONNECTING;
  WSProxy.prototype.OPEN = _Real.OPEN;
  WSProxy.prototype.CLOSING = _Real.CLOSING;
  WSProxy.prototype.CLOSED = _Real.CLOSED;
  window.WebSocket = WSProxy;
})();

// ===== 2. 窗口管理 =====
// chat.html 原有的内联 JS 检测 window.nekoChatWindow 来决定是否启用独立窗口模式
window.nekoChatWindow = {
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setSize: (w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, { w, h }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  setResizable: (v) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_RESIZABLE, { resizable: v }),
  bringToFront: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT),
  dragStart: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, {}),
  dragStop: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP),
  resizeStart: (direction, options) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_START, {
    direction: direction || 'se',
    minWidth: options && options.minWidth,
    minHeight: options && options.minHeight,
  }),
  resizeStop: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_STOP),
  collapse: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.COLLAPSE),
  expand: (savedBounds) => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.EXPAND, savedBounds),
  enableInteraction: () => ipcRenderer.send('set-ignore-mouse-events', false),
};

// 多窗口模式标志
window.__NEKO_MULTI_WINDOW__ = true;

// ===== 屏幕捕获源 API（与 Pet 窗口的 preload.js / preload-pet.js 对齐）=====
// 独立 Chat 窗口原本没有此 API，导致 captureScreenshotToPendingList 走不到
// 主进程直截路径，只能落回流路径 / pyautogui —— 都不认选中源，总是截主屏。
window.electronDesktopCapturer = {
  getSources: (options = {}) => ipcRenderer.invoke('get-desktop-sources', options),
  setSelectedSource: (sourceId) => ipcRenderer.invoke('set-selected-screen-source', sourceId || null),
  captureSourceAsDataUrl: (sourceId) => ipcRenderer.invoke('capture-source-as-dataurl', sourceId),
  captureSourceWithoutNeko: (sourceId) => ipcRenderer.invoke('capture-source-without-neko', sourceId),
  hideNekoWindows: () => ipcRenderer.invoke('hide-neko-windows'),
  restoreNekoWindows: (hiddenIds) => ipcRenderer.invoke('restore-neko-windows', hiddenIds),
};

// ===== 截图代理（多窗口模式下让 Pet 窗口代为全屏截图裁剪）=====
window.nekoScreenshotProxy = {
  request: () => ipcRenderer.send(CHAT_CHANNELS.REQUEST_SCREENSHOT)
};
ipcRenderer.on(CHAT_CHANNELS.SCREENSHOT_RESULT, (event, result) => {
  window.dispatchEvent(new CustomEvent('neko:screenshot-result', { detail: result || {} }));
});

window.nekoSubtitleWindow = {
  setEnabled: (enabled) => ipcRenderer.send(SUBTITLE_CHANNELS.SETTINGS_CHANGE, {
    type: 'toggle',
    value: !!enabled,
  }),
  show: () => ipcRenderer.send('neko:show-subtitle'),
  hide: () => ipcRenderer.send('neko:hide-subtitle'),
};

// ===== 3. Toast / 暗色模式 / 外部链接 / 设置同步 =====
setupToastOverride();
suppressVoiceToast();
setupDarkMode();
setupElectronShell();
setupHostCapabilityBridge();
setupGoodbyeChatComposerHiddenBridge();
setupVoiceConfigSwitchingBridge();
setupMusicPlayerBridge();
setupSettingsSync({ role: 'chat' });

ipcRenderer.on(SUBTITLE_CHANNELS.SETTINGS_CHANGE, function (_event, data) {
  if (!data || data.type !== 'toggle') return;
  syncSubtitleToggleFromWindow(data.value);
});

// ===== Jukebox 独立窗口：直接发给主进程 =====
window.__nekoJukeboxToggle = function() {
  ipcRenderer.send(JUKEBOX_CHANNELS.TOGGLE);
};

function forwardAvatarToolStateToPet(detail) {
  var payload = detail && typeof detail === 'object' ? detail : {
    active: false,
    toolId: null,
    tool: null,
    timestamp: Date.now(),
  };
  payload = enrichAvatarToolStateWithRecentPointer(payload);
  if (payload && payload.active === true) {
    payload = Object.assign({}, payload, { overChatWindow: true });
  }
  latestAvatarToolStatePayload = payload && payload.active === true ? Object.assign({}, payload) : null;
  if (!latestAvatarToolStatePayload) {
    cancelAvatarToolPointerForwardFrame();
    clearAvatarToolVisualCursor();
  }
  setAvatarToolNativeCursorSuppressed(payload.active === true);
  if (payload.active === true) {
    requestAvatarToolVisualCursorLayerRaise('avatar-tool-state');
  }
  ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_TOOL_STATE, payload);
}

var latestAvatarToolPointer = null;
var latestAvatarToolPointerEvent = null;
var latestAvatarToolStatePayload = null;
var avatarToolPointerForwardFrame = 0;
var avatarToolVisualCursorElement = null;
var avatarToolVisualCursorKey = '';
var avatarToolVisualCursorRaiseAt = 0;
var AVATAR_TOOL_VISUAL_CHAT_HIT_SELECTOR = [
  '.compact-chat-surface-frame',
  '.compact-chat-drag-handle',
  '.compact-chat-resize-handle',
  '.compact-input-tool-fan',
  '.compact-input-tool-item',
  '.avatar-tool-quickbar',
  '.composer-icon-popover',
  '.composer-icon-button',
  '.composer-tool-menu',
  '.composer-tool-btn',
  '.composer-bottom-tools',
  '.composer-choice-layer[data-choice-layer-open="true"]',
  '.composer-galgame-option',
  '.compact-export-history-anchor',
  '.chat-export-preview-panel',
  '.chat-export-preview-backdrop',
  '#react-chat-window-header-actions',
  '.window-topbar-actions',
  '.topbar-action-btn',
  '.react-chat-resize-edge',
  '.chat-window.chat-surface-mode-full',
  '.app-shell.chat-surface-mode-full',
  '.chat-body:not(.chat-body-compact-surface)',
  '.message-list-shell',
  '.message-list',
  '.composer-panel:not(.chat-surface-mode-compact)',
  '.composer-input-shell',
  '.composer-input',
  '.send-button-circle',
].join(', ');

function normalizeAvatarToolFiniteNumber(value) {
  var number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function normalizeAvatarToolPayloadScreenPoint(payload) {
  if (!payload || typeof payload !== 'object') return null;
  var screenX = normalizeAvatarToolFiniteNumber(payload.cursorScreenX);
  var screenY = normalizeAvatarToolFiniteNumber(payload.cursorScreenY);
  if (screenX !== null && screenY !== null) return { cursorScreenX: screenX, cursorScreenY: screenY };
  return null;
}

function getAvatarToolClientScreenPoint(clientX, clientY) {
  var x = normalizeAvatarToolFiniteNumber(clientX);
  var y = normalizeAvatarToolFiniteNumber(clientY);
  if (x === null || y === null) return null;
  var originX = normalizeAvatarToolFiniteNumber(window.screenX);
  var originY = normalizeAvatarToolFiniteNumber(window.screenY);
  if (originX !== null && originY !== null) {
    return { cursorScreenX: originX + x, cursorScreenY: originY + y };
  }
  return null;
}

function rememberAvatarToolPointer(event) {
  if (!event) return;
  var clientX = normalizeAvatarToolFiniteNumber(event.clientX);
  var clientY = normalizeAvatarToolFiniteNumber(event.clientY);
  if (clientX === null || clientY === null) return;
  latestAvatarToolPointer = Object.assign({
    cursorClientX: clientX,
    cursorClientY: clientY,
    timestamp: Date.now(),
  }, getAvatarToolClientScreenPoint(clientX, clientY) || {});
  latestAvatarToolPointerEvent = {};
  var button = normalizeAvatarToolFiniteNumber(event.button);
  var buttons = normalizeAvatarToolFiniteNumber(event.buttons);
  if (button !== null) latestAvatarToolPointerEvent.button = button;
  if (buttons !== null) latestAvatarToolPointerEvent.buttons = buttons;
  scheduleAvatarToolPointerForward(event);
}

function enrichAvatarToolStateWithRecentPointer(payload) {
  if (!payload || typeof payload !== 'object' || payload.active !== true) return payload;
  var clientX = normalizeAvatarToolFiniteNumber(payload.cursorClientX);
  var clientY = normalizeAvatarToolFiniteNumber(payload.cursorClientY);
  var hasPayloadClientPoint = clientX !== null && clientY !== null;
  if (!hasPayloadClientPoint) {
    if (!latestAvatarToolPointer || Date.now() - latestAvatarToolPointer.timestamp > 2500) return payload;
    clientX = latestAvatarToolPointer.cursorClientX;
    clientY = latestAvatarToolPointer.cursorClientY;
  }
  var screenPoint = getAvatarToolClientScreenPoint(clientX, clientY)
    || (hasPayloadClientPoint ? normalizeAvatarToolPayloadScreenPoint(payload) : normalizeAvatarToolPayloadScreenPoint(latestAvatarToolPointer));
  return Object.assign({}, payload, {
    cursorClientX: clientX,
    cursorClientY: clientY,
  }, screenPoint || {});
}

function normalizeAvatarToolPointerForwardType(event) {
  var type = event && typeof event.type === 'string' ? event.type : '';
  if (type === 'pointerdown') return 'down';
  if (type === 'pointerup') return 'up';
  if (type === 'pointercancel') return 'cancel';
  if (type === 'pointermove') return 'move';
  return null;
}

function cancelAvatarToolPointerForwardFrame() {
  if (!avatarToolPointerForwardFrame) return;
  if (typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(avatarToolPointerForwardFrame);
  }
  window.clearTimeout(avatarToolPointerForwardFrame);
  avatarToolPointerForwardFrame = 0;
}

function buildAvatarToolPointerForwardPayload(type, event) {
  if (!latestAvatarToolStatePayload || latestAvatarToolStatePayload.active !== true) return null;
  if (!latestAvatarToolPointer) return null;
  var payload = Object.assign({}, latestAvatarToolStatePayload, latestAvatarToolPointer, {
    overChatWindow: true,
    type: type,
    timestamp: Date.now(),
  });
  var button = normalizeAvatarToolFiniteNumber(event && event.button);
  var buttons = normalizeAvatarToolFiniteNumber(event && event.buttons);
  if (button !== null) payload.button = button;
  if (buttons !== null) payload.buttons = buttons;
  return payload;
}

function sendAvatarToolPointerForward(type, event) {
  var payload = buildAvatarToolPointerForwardPayload(type, event);
  if (!payload) return;
  ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_TOOL_POINTER, payload);
}

function scheduleAvatarToolPointerForward(event) {
  var type = normalizeAvatarToolPointerForwardType(event);
  if (!type || !latestAvatarToolStatePayload || latestAvatarToolStatePayload.active !== true) return;
  if (type !== 'move') {
    cancelAvatarToolPointerForwardFrame();
    sendAvatarToolPointerForward(type, event);
    return;
  }
  if (avatarToolPointerForwardFrame) return;
  var scheduleFrame = typeof window.requestAnimationFrame === 'function'
    ? window.requestAnimationFrame.bind(window)
    : function(callback) { return window.setTimeout(callback, 16); };
  avatarToolPointerForwardFrame = scheduleFrame(function() {
    avatarToolPointerForwardFrame = 0;
    sendAvatarToolPointerForward('move', latestAvatarToolPointerEvent);
  });
}

function setAvatarToolNativeCursorSuppressed(active) {
  var root = document.documentElement;
  if (!root || !root.classList) return;
  root.classList.toggle('neko-avatar-tool-native-cursor-hidden', active === true);
}

function requestAvatarToolVisualCursorLayerRaise(reason) {
  var now = Date.now();
  if (now - avatarToolVisualCursorRaiseAt < 500) return;
  avatarToolVisualCursorRaiseAt = now;
  try {
    if (window.nekoChatWindow && typeof window.nekoChatWindow.bringToFront === 'function') {
      window.nekoChatWindow.bringToFront({ reason: reason || 'avatar-tool-cursor' });
    }
  } catch (_) {}
}

function isAvatarToolVisualChatHitElement(element) {
  if (!element || element === document.body || element === document.documentElement) return false;
  if (element.closest && element.closest('.neko-avatar-tool-visual-cursor')) return false;
  var match = element.closest && element.closest(AVATAR_TOOL_VISUAL_CHAT_HIT_SELECTOR);
  if (!match) return false;
  try {
    var rect = match.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    var style = window.getComputedStyle ? window.getComputedStyle(match) : null;
    if (style && (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0)) {
      return false;
    }
  } catch (_) {}
  return true;
}

function shouldRenderAvatarToolVisualCursorInChat(clientX, clientY, payload) {
  var x = normalizeAvatarToolFiniteNumber(clientX);
  var y = normalizeAvatarToolFiniteNumber(clientY);
  if (x === null || y === null) return false;
  if (payload && Object.prototype.hasOwnProperty.call(payload, 'overChatWindow')) {
    return payload.overChatWindow === true;
  }
  if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) return false;
  var elements = [];
  try {
    if (typeof document.elementsFromPoint === 'function') {
      elements = document.elementsFromPoint(x, y);
    } else if (typeof document.elementFromPoint === 'function') {
      var element = document.elementFromPoint(x, y);
      if (element) elements = [element];
    }
  } catch (_) {
    elements = [];
  }
  return elements.some(isAvatarToolVisualChatHitElement);
}

function normalizeAvatarToolVariant(value) {
  return value === 'secondary' || value === 'tertiary' ? value : 'primary';
}

function normalizeAvatarToolImageKind(value) {
  return value === 'icon' || value === 'hidden' ? value : 'cursor';
}

function resolveAvatarToolVisualImagePaths(tool, variant) {
  var resolvedVariant = normalizeAvatarToolVariant(variant);
  return {
    iconImagePath: resolvedVariant === 'tertiary' && tool.iconImagePathAlt2
      ? tool.iconImagePathAlt2
      : resolvedVariant === 'secondary' && tool.iconImagePathAlt
        ? tool.iconImagePathAlt
        : tool.iconImagePath,
    cursorImagePath: resolvedVariant === 'tertiary' && tool.cursorImagePathAlt2
      ? tool.cursorImagePathAlt2
      : resolvedVariant === 'secondary' && tool.cursorImagePathAlt
        ? tool.cursorImagePathAlt
        : resolvedVariant === 'tertiary' && tool.cursorImagePathAlt
          ? tool.cursorImagePathAlt
          : tool.cursorImagePath,
  };
}

function getAvatarToolDefaultVisualMetrics(toolId, imageKind) {
  if (imageKind === 'icon') {
    if (toolId === 'lollipop') return { width: 74, height: 108, scale: 1 };
    if (toolId === 'fist') return { width: 100, height: 102, scale: 1 };
    if (toolId === 'hammer') return { width: 136, height: 130, scale: 1 };
  }
  if (toolId === 'lollipop') return { width: 74, height: 108, scale: 0.56 };
  if (toolId === 'fist') return { width: 78, height: 80, scale: 0.56 };
  if (toolId === 'hammer') return { width: 100, height: 96, scale: 0.52 };
  return { width: 0, height: 0, scale: 1 };
}

function normalizeAvatarToolPositiveNumber(value, fallback) {
  var number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

function getAvatarToolScreenPointFromPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  var nestedPoint = payload.cursorScreenPoint && typeof payload.cursorScreenPoint === 'object'
    ? payload.cursorScreenPoint
    : null;
  var screenX = normalizeAvatarToolFiniteNumber(payload.cursorScreenX);
  var screenY = normalizeAvatarToolFiniteNumber(payload.cursorScreenY);
  if (screenX === null) screenX = normalizeAvatarToolFiniteNumber(payload.screenX);
  if (screenY === null) screenY = normalizeAvatarToolFiniteNumber(payload.screenY);
  if (screenX === null) screenX = normalizeAvatarToolFiniteNumber(nestedPoint && nestedPoint.x);
  if (screenY === null) screenY = normalizeAvatarToolFiniteNumber(nestedPoint && nestedPoint.y);
  if (screenX === null || screenY === null) return null;
  return { screenX: screenX, screenY: screenY };
}

function getAvatarToolScreenClientPoint(screenX, screenY) {
  var x = normalizeAvatarToolFiniteNumber(screenX);
  var y = normalizeAvatarToolFiniteNumber(screenY);
  if (x === null || y === null) return null;
  var originX = normalizeAvatarToolFiniteNumber(window.screenX);
  var originY = normalizeAvatarToolFiniteNumber(window.screenY);
  if (originX !== null && originY !== null) {
    return { clientX: x - originX, clientY: y - originY };
  }
  return null;
}

function ensureAvatarToolVisualCursorElement() {
  if (avatarToolVisualCursorElement && avatarToolVisualCursorElement.isConnected) return avatarToolVisualCursorElement;
  if (!document || !document.createElement) return null;
  var image = document.createElement('img');
  image.className = 'neko-avatar-tool-visual-cursor';
  image.hidden = true;
  image.draggable = false;
  image.alt = '';
  var parent = document.body || document.documentElement;
  if (!parent) return null;
  parent.appendChild(image);
  avatarToolVisualCursorElement = image;
  return image;
}

function clearAvatarToolVisualCursor() {
  avatarToolVisualCursorKey = '';
  if (!avatarToolVisualCursorElement) return;
  avatarToolVisualCursorElement.hidden = true;
  avatarToolVisualCursorElement.style.transform = 'translate3d(-9999px, -9999px, 0)';
}

function applyAvatarToolVisualCursorState(payload) {
  if (!payload || typeof payload !== 'object' || payload.active !== true) {
    clearAvatarToolVisualCursor();
    return;
  }
  var tool = payload.tool && typeof payload.tool === 'object' ? payload.tool : null;
  var toolId = payload.toolId || (tool && tool.id);
  if (!tool || !toolId || payload.visible === false) {
    clearAvatarToolVisualCursor();
    return;
  }
  var imageKind = normalizeAvatarToolImageKind(payload.imageKind);
  if (imageKind === 'hidden') {
    clearAvatarToolVisualCursor();
    return;
  }
  var point = getAvatarToolScreenPointFromPayload(payload);
  var clientPoint = point ? getAvatarToolScreenClientPoint(point.screenX, point.screenY) : null;
  if (!clientPoint) {
    clearAvatarToolVisualCursor();
    return;
  }
  if (!shouldRenderAvatarToolVisualCursorInChat(clientPoint.clientX, clientPoint.clientY, payload)) {
    clearAvatarToolVisualCursor();
    return;
  }
  requestAvatarToolVisualCursorLayerRaise('avatar-tool-cursor');
  var variant = normalizeAvatarToolVariant(payload.variant || payload.avatarRangeVariant || payload.outsideRangeVariant);
  var imagePaths = resolveAvatarToolVisualImagePaths(tool, variant);
  var imagePath = imageKind === 'icon' ? imagePaths.iconImagePath : imagePaths.cursorImagePath;
  if (!imagePath) {
    clearAvatarToolVisualCursor();
    return;
  }
  var metrics = getAvatarToolDefaultVisualMetrics(toolId, imageKind);
  var displayWidth = normalizeAvatarToolPositiveNumber(payload.displayWidth, metrics.width);
  var displayHeight = normalizeAvatarToolPositiveNumber(payload.displayHeight, metrics.height);
  var naturalWidth = normalizeAvatarToolPositiveNumber(tool.cursorNaturalWidth, displayWidth);
  var naturalHeight = normalizeAvatarToolPositiveNumber(tool.cursorNaturalHeight, displayHeight);
  var safeScale = normalizeAvatarToolPositiveNumber(payload.scale, metrics.scale);
  var hotspotX = normalizeAvatarToolFiniteNumber(tool.cursorHotspotX);
  var hotspotY = normalizeAvatarToolFiniteNumber(tool.cursorHotspotY);
  var displayRatioX = naturalWidth > 0 ? displayWidth / naturalWidth : 1;
  var displayRatioY = naturalHeight > 0 ? displayHeight / naturalHeight : 1;
  var scaledHotspotX = (hotspotX === null ? 18 : hotspotX) * displayRatioX * safeScale;
  var scaledHotspotY = (hotspotY === null ? 18 : hotspotY) * displayRatioY * safeScale;
  var viewportWidth = Number(window.innerWidth) || 0;
  var viewportHeight = Number(window.innerHeight) || 0;
  var viewportPad = Math.max(displayWidth, displayHeight, 160);
  if (
    viewportWidth > 0
    && viewportHeight > 0
    && (
      clientPoint.clientX < -viewportPad
      || clientPoint.clientX > viewportWidth + viewportPad
      || clientPoint.clientY < -viewportPad
      || clientPoint.clientY > viewportHeight + viewportPad
    )
  ) {
    clearAvatarToolVisualCursor();
    return;
  }
  var left = Math.round(clientPoint.clientX - scaledHotspotX);
  var top = Math.round(clientPoint.clientY - scaledHotspotY);
  var key = [
    imagePath,
    left,
    top,
    displayWidth,
    displayHeight,
    safeScale,
  ].join('|');
  if (avatarToolVisualCursorKey === key) return;
  avatarToolVisualCursorKey = key;
  var image = ensureAvatarToolVisualCursorElement();
  if (!image) return;
  if (image.getAttribute('src') !== imagePath) image.setAttribute('src', imagePath);
  image.style.width = Math.round(displayWidth) + 'px';
  image.style.height = Math.round(displayHeight) + 'px';
  image.style.transform = 'translate3d(' + left + 'px, ' + top + 'px, 0) scale(' + safeScale + ')';
  image.hidden = false;
}

ipcRenderer.on(PET_CHANNELS.AVATAR_TOOL_CURSOR_STATE, function(_event, payload) {
  applyAvatarToolVisualCursorState(payload);
});

window.addEventListener('react-chat-window:avatar-tool-state', function(event) {
  forwardAvatarToolStateToPet(event && event.detail);
});

window.addEventListener('pointerdown', rememberAvatarToolPointer, true);
window.addEventListener('pointermove', rememberAvatarToolPointer, true);
window.addEventListener('pointerup', rememberAvatarToolPointer, true);
window.addEventListener('pointercancel', rememberAvatarToolPointer, true);
window.addEventListener('click', rememberAvatarToolPointer, true);

window.addEventListener('beforeunload', function() {
  forwardAvatarToolStateToPet({
    active: false,
    toolId: null,
    tool: null,
    timestamp: Date.now(),
  });
});

document.addEventListener('visibilitychange', function() {
  if (!document.hidden) return;
  forwardAvatarToolStateToPet({
    active: false,
    toolId: null,
    tool: null,
    timestamp: Date.now(),
  });
});

// ===== 4. 从 Pet 窗口获取初始配置（猫娘名字、主人信息）=====
// 多窗口模式下页面不自己请求 API（/chat 路径会被误解析为角色名），
// 而是等 preload 通过 IPC 从 Pet 窗口注入配置。
ipcRenderer.on(CHAT_ACTION_CHANNELS.CONFIG_RESULT, (_event, data) => {
  window.__nekoInjectedConfig = data || {};
  window.dispatchEvent(new CustomEvent('neko:config-injected', { detail: data }));
});
window.__nekoRequestConfigInjection = function() {
  ipcRenderer.send(CHAT_ACTION_CHANNELS.CONFIG_REQUEST);
};
window.__nekoRequestConfigInjection();

// ===== 5. 从 Pet 窗口获取初始头像 =====
ipcRenderer.on(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT, (_event, data) => {
  if (data && data.dataUrl && window.appChatAvatar && typeof window.appChatAvatar.setExternalAvatar === 'function') {
    window.appChatAvatar.setExternalAvatar(data.dataUrl, data.modelType || 'live2d');
  }
  // 通知页面 JS 头像结果（含失败情况），供 captureAvatarDirect 使用
  window.dispatchEvent(new CustomEvent('neko:avatar-preview-ipc-result', {
    detail: data && data.dataUrl ? { dataUrl: data.dataUrl, modelType: data.modelType || 'live2d' } : { error: (data && data.error) || 'no data' }
  }));
});

// 暴露给页面 JS：触发一次从 Pet 窗口的头像截取
window.__nekoRequestAvatarPreview = function() {
  ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW);
};

document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW);
  }, 500);
});

// On native Wayland: global cursor position and window repositioning via setBounds are
// both no-ops. Instead let -webkit-app-region:drag trigger xdg_toplevel.move natively.
var _isNativeWayland = process.platform === 'linux' &&
  process.env.NEKO_FORCE_X11 !== '1' &&
  (!!process.env.WAYLAND_DISPLAY || process.env.XDG_SESSION_TYPE === 'wayland') &&
  !process.argv.some(function(a) { return a.indexOf('ozone-platform=x11') >= 0; });
ipcRenderer.send('neko:debug-log', '[preload-chat] _isNativeWayland=' + _isNativeWayland);

// ===== DOM 拦截：app-react-chat-window.js 的页面内 drag/resize → BrowserWindow 操作 =====
document.addEventListener('DOMContentLoaded', () => {
  var W = window.nekoChatWindow;
  var WIN_SIZE = 84;   // 折叠窗口物理尺寸（留空间给 glow 呼吸灯完整显示）
  var BALL_SIZE = 56;  // 悬浮球视觉直径（比 web 版 50px 稍大，补偿窗口边界带来的视觉缩小）

  // ---- 折叠/展开状态 ----
  var eMinimized = false;
  var eSavedBounds = null;
  var eBusy = false;
  var E_SAVED_BOUNDS_KEY = 'neko.reactChatWindow.electronSavedBounds';
  var EXPAND_MIN_W = 320;
  var EXPAND_MIN_H = 280;
  var GALGAME_EXPAND_MIN_H = 385;
  // 附件预览（截图 / 导入图片）单卡 90px + 间距，需要的下限和 galgame slot 同级。
  var ATTACHMENTS_EXPAND_MIN_H = 385;
  // galgame + 附件并存的极端情况：两份预算（slot ~110 + 卡片 ~110）叠加。
  // 与 chat.html 的 MIN_H_GALGAME_ATTACHMENTS 保持一致。
  var GALGAME_ATTACHMENTS_EXPAND_MIN_H = 495;

  function getElectronResizeMinHeight() {
    if (!document.body) return EXPAND_MIN_H;
    var gal = document.body.classList.contains('galgame-mode-enabled');
    var att = document.body.classList.contains('composer-has-attachments');
    if (gal && att) return GALGAME_ATTACHMENTS_EXPAND_MIN_H;
    if (gal) return GALGAME_EXPAND_MIN_H;
    if (att) return ATTACHMENTS_EXPAND_MIN_H;
    return EXPAND_MIN_H;
  }

  function normalizeExpandBounds(bounds) {
    if (!bounds) return null;
    var width = Math.max(EXPAND_MIN_W, Math.round(Number(bounds.width) || 0));
    var height = Math.max(EXPAND_MIN_H, Math.round(Number(bounds.height) || 0));
    var x = Math.round(Number(bounds.x) || 0);
    var y = Math.round(Number(bounds.y) || 0);
    if (!Number.isFinite(width) || !Number.isFinite(height) || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x: x, y: y, width: width, height: height };
  }

  function saveExpandBounds(bounds) {
    var normalized = normalizeExpandBounds(bounds);
    if (!normalized) return null;
    eSavedBounds = normalized;
    try { window.localStorage.setItem(E_SAVED_BOUNDS_KEY, JSON.stringify(normalized)); } catch (_) {}
    return normalized;
  }

  function loadExpandBounds() {
    if (eSavedBounds) return normalizeExpandBounds(eSavedBounds);
    try {
      var raw = window.localStorage.getItem(E_SAVED_BOUNDS_KEY);
      if (raw) return normalizeExpandBounds(JSON.parse(raw));
    } catch (_) {}
    return normalizeExpandBounds({ x: 0, y: 0, width: 440, height: 600 });
  }

  function clearExpandBounds() {
    eSavedBounds = null;
    try { window.localStorage.removeItem(E_SAVED_BOUNDS_KEY); } catch (_) {}
  }

  // ---- CSS 注入 ----
  var style = document.createElement('style');
  style.textContent = [
    // On Wayland, ensure the drag handle has the native drag region marker so
    // xdg_toplevel.move is triggered when we skip preventDefault below.
    // Note: Chromium overrides CSS cursor on -webkit-app-region:drag elements;
    // cursor is instead managed via JS mouseenter/mouseleave on html below.
    (_isNativeWayland ? '#react-chat-window-drag-handle, #react-chat-window-drag-handle * { -webkit-app-region: drag; cursor: grab !important; } #reactChatWindowCloseButton, #reactChatWindowCloseButton *, #reactChatWindowMinimizeButton, #reactChatWindowMinimizeButton * { -webkit-app-region: no-drag; }' : '#react-chat-window-drag-handle { cursor: grab; }'),
    'html.neko-dragging, html.neko-dragging * { cursor: grabbing !important; }',
    'html.neko-resizing, html.neko-resizing * { cursor: nwse-resize !important; }',
    'html.neko-avatar-tool-native-cursor-hidden,',
    'html.neko-avatar-tool-native-cursor-hidden *,',
    'html.neko-avatar-tool-native-cursor-hidden *::before,',
    'html.neko-avatar-tool-native-cursor-hidden *::after { cursor: none !important; }',
    '.neko-avatar-tool-visual-cursor { position: fixed; left: 0; top: 0; z-index: 2147483600; pointer-events: none; user-select: none; -webkit-user-drag: none; object-fit: contain; transform-origin: 0 0; will-change: transform; }',

    // 动画期间：shell 的 inset 必须与 full 终态完全一致，否则动画结束移除 .is-expanding/
    // .is-collapsing 时盒子会从动画 inset 瞬间跳到终态 inset（每边差值）→ 末帧 size 跳变。
    // 终态 = chat.html 的 full gate（body.neko-electron-runtime #...[surface=full]...）= inset:30px，
    // 也与 window-manager 的 _nekoFullChatShadowMargin=30（30px 阴影留白）一致。
    // 二者改任一处都要同步这里（原写死 20px 与终态 30px 漂移，#1695 加玻璃边框后跳变变明显）。
    // chat.html 对 .is-collapsing/.is-expanding 设了 inset:auto!important (1,1,0)，
    // 用 :not(._) 提升到 (1,3,0) 覆盖之。
    // border:none 清除液态玻璃边框，确保动画期间干净。
    '#react-chat-window-shell.neko-e-animating.is-collapsing:not(._),',
    '#react-chat-window-shell.neko-e-animating.is-expanding:not(._) {',
    '  position: fixed !important;',
    '  inset: 30px !important;',
    '  width: auto !important; height: auto !important;',
    '  max-width: none !important; max-height: none !important;',
    '  border: none !important;',
    '  border-radius: 22px !important;',
    '  box-shadow: none !important;',
    '  pointer-events: none !important;',
    '}',

    // Electron 折叠态
    // chat.html 的液态玻璃（边框 / ::before 高光 / ::after 流光）选择器为
    //   :not(.is-minimized) 系列，specificity (0,1,1,0) ~ (0,1,3,0)。
    // 此处用 :not(._)×3 提升到 (0,1,4,0) 完整覆盖：border/box-shadow/background
    // 清除边框与阴影，content:none 关闭伪元素层，max-height:none 压制媒体查询。
    // N.E.K.O 侧无需感知 .neko-e-collapsed 的存在。
    //
    // 架构：shell 本身透明，铺满视口以捕获鼠标事件；
    //       drag-handle 作为可见的 50px 圆球居中显示；
    //       box-shadow 呼吸灯渲染在圆球上，向外扩散到透明区域 —— 视觉上环绕圆而非方框。
    '#react-chat-window-shell.neko-e-collapsed:not(._):not(._):not(._) {',
    '  width: 100% !important; height: 100% !important;',
    '  max-width: none !important; max-height: none !important;',
    // 关掉 chat.html 里 body.galgame-mode-enabled #shell { min-height:320px !important }。
    // 折叠态 shell 必须严格贴 84x84 视口，否则 min-height:320 撑高 shell，flex 居中的
    // drag-handle ball 被推到 y≈132，整个跑出 84x84 窗口边界 → 视觉消失 + 没法点。
    '  min-width: 0 !important; min-height: 0 !important;',
    '  left: 0 !important; top: 0 !important;',
    '  transform: none !important;',
    '  border: none !important;',
    '  border-radius: 0 !important;',
    '  background: transparent !important;',
    '  box-shadow: none !important;',
    '  overflow: visible !important;',
    '  cursor: pointer;',
    '  display: flex; align-items: center; justify-content: center;',
    '}',
    // body 自身的 galgame-mode / composer-has-attachments min-height（chat.html
    // body.galgame-mode-enabled / body.composer-has-attachments 规则）也得关：
    // 折叠到 84px 时 body min-height:385 会撑出滚动条 + 影响 100vh 定位。
    // 用 :has() 在折叠态生效；galgame、附件、两者并存三种情况都覆盖。
    'body.galgame-mode-enabled:has(#react-chat-window-shell.neko-e-collapsed),',
    'body.composer-has-attachments:has(#react-chat-window-shell.neko-e-collapsed) {',
    '  min-height: 0 !important;',
    '}',
    // 折叠态关闭液态玻璃伪元素层（静态高光 ::before + 流动光斑 ::after）
    '#react-chat-window-shell.neko-e-collapsed:not(._)::before,',
    '#react-chat-window-shell.neko-e-collapsed:not(._)::after {',
    '  content: none !important;',
    '}',
    // 折叠态隐藏内容区和操作按钮
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-root,',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-header-actions,',
    '#react-chat-window-shell.neko-e-collapsed .react-chat-resize-edge {',
    '  display: none !important;',
    '}',
    // drag-handle 变成可见的悬浮球
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle {',
    '  position: static !important;',
    '  width: 56px; height: 56px; cursor: pointer;',
    '  border-radius: 50%;',
    '  background: rgba(68,183,254,0.15);',
    '  box-shadow: 0 0 8px rgba(68,183,254,0.6);',
    '  animation: breathingGlow 2s ease-in-out infinite;',
    '  will-change: box-shadow;',
    '  display: flex; align-items: center; justify-content: center;',
    '  flex-shrink: 0;',
    '}',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle:hover {',
    '  background: rgba(68,183,254,0.25);',
    '}',
    '[data-theme="dark"] #react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle {',
    '  background: rgba(68,183,254,0.2);',
    '}',
    // 悬浮球图标：折叠态显示（填满 drag handle）
    '#react-chat-window-shell .neko-e-ball-icon { display: none; }',
    '#react-chat-window-shell.neko-e-collapsed .neko-e-ball-icon {',
    '  display: block; width: 100%; height: 100%;',
    '  object-fit: contain;',
    '  pointer-events: none; user-select: none;',
    '}',
    // 折叠动画期间的球覆盖层（固定在视口左下角，不跟随 shell scale）
    '.neko-e-ball-overlay {',
    '  position: fixed; z-index: 99999;',
    '  pointer-events: none;',
    '}',
  ].join('\n');
  document.head.appendChild(style);

  // ---- 确保悬浮球图标存在 ----
  function ensureBallIcon() {
    var handle = document.getElementById('react-chat-window-drag-handle');
    if (!handle || handle.querySelector('.neko-e-ball-icon')) return;
    var icon = document.createElement('img');
    icon.className = 'neko-e-ball-icon';
    // 折叠态使用带白晕的 _ball 版本（PR #1139 起，原 expand_icon_off.png 被清成
    // 无白晕的 header 版，球边缘会糊在 model 上）。
    icon.src = '/static/icons/expand_icon_off_ball.png';
    icon.alt = '';
    icon.draggable = false;
    handle.appendChild(icon);
  }

  // ---- 折叠：左下角定点缩放 → 物理缩小窗口 ----
  // chat.html 有 #shell:not(.is-collapsing){ transform:none!important }
  // 必须加 .is-collapsing 解除锁定，element.animate 才能生效。
  function doCollapse() {
    console.log('[Preload-Chat][collapse] doCollapse() entered, eBusy=', eBusy, 'eMinimized=', eMinimized);
    if (eBusy || eMinimized) {
      console.log('[Preload-Chat][collapse] early return (busy or already minimized)');
      return;
    }
    eBusy = true;

    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) {
      console.warn('[Preload-Chat][collapse] shell not found, abort');
      eBusy = false;
      return;
    }

    ensureBallIcon();

    var rect = shell.getBoundingClientRect();
    var sx = BALL_SIZE / rect.width;
    var sy = BALL_SIZE / rect.height;
    console.log('[Preload-Chat][collapse] start animate; shell rect=', rect, 'classes=', shell.className);

    // 1. .is-collapsing 解除 transform:none!important
    //    .neko-e-animating 强制 inset:0 + 填满视口（CSS 规则已处理，无需 inline 锁几何）
    shell.style.transformOrigin = '0% 100%';
    shell.classList.add('is-collapsing', 'neko-e-animating');

    // 3. element.animate 驱动缩放
    var anim = shell.animate([
      { transform: 'scale(1)', opacity: 1, offset: 0 },
      { transform: 'scale(' + sx + ',' + sy + ')', opacity: 0, offset: 1 }
    ], {
      duration: 600,
      easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
      fill: 'forwards',
    });

    // 4. 球覆盖层：独立于 shell（不被 shell opacity 影响），固定在左下角
    //    位置精确匹配缩窗后球在 84x84 窗口内居中的屏幕坐标，消除跳变
    var ballPad = (WIN_SIZE - BALL_SIZE) / 2;
    var overlay = document.createElement('img');
    overlay.className = 'neko-e-ball-overlay';
    overlay.src = '/static/icons/expand_icon_off_ball.png';
    overlay.draggable = false;
    overlay.style.width = BALL_SIZE + 'px';
    overlay.style.height = BALL_SIZE + 'px';
    overlay.style.left = (rect.left + ballPad) + 'px';
    overlay.style.top = (rect.top + rect.height - WIN_SIZE + ballPad) + 'px';
    document.body.appendChild(overlay);

    // 400ms 处开始、66ms 内快速渐显（offset 0.67 → 0.78）
    var ballAnim = overlay.animate([
      { opacity: 0, offset: 0 },
      { opacity: 0, offset: 0.67 },
      { opacity: 1, offset: 0.78 },
      { opacity: 1, offset: 1 }
    ], {
      duration: 600,
      easing: 'linear',
      fill: 'forwards',
    });

    // 5. 360ms（60%）时提前物理缩窗
    var resized = false;
    var collapsePromise = null;
    var collapseTimer = setTimeout(function () {
      resized = true;
      // 强制 opacity=0 防止 neko-e-collapsed 的 transform:none!important
      // 覆盖动画 fill:forwards 的缩放 transform 导致的闪烁
      shell.style.setProperty('opacity', '0', 'important');
      shell.classList.remove('is-collapsing');
      shell.classList.add('neko-e-collapsed');
      shell.style.transformOrigin = '';
      console.log('[Preload-Chat][collapse] @360ms classes=', shell.className, 'inlineStyle=', shell.style.cssText);
      // 故意不在这里 .catch —— 让 rejection 沿 collapsePromise 链向下游传播，
      // 由 anim.onfinish 的 else 分支（line 580）的 .catch 统一回滚状态。
      // 在这里吞掉错误会让上游误以为折叠成功，把 eMinimized 标成 true 但
      // BrowserWindow 实际未缩，下一次点击进入 expand 路径会失败。
      collapsePromise = W.collapse().then(function (saved) {
        console.log('[Preload-Chat][collapse] W.collapse IPC resolved, saved=', saved);
        saveExpandBounds(saved || rect);
        // 窗口已缩至 84x84，安全恢复 opacity
        if (shell.classList.contains('neko-e-animating')) {
          shell.style.removeProperty('opacity');
        }
      });
    }, 360);

    // 安全网：1500ms 后无论 anim.onfinish 是否触发，强制清掉 opacity:0!important。
    // Windows 透明窗口下 alpha=0 全幅会让窗口点击穿透，一旦 onfinish 因竞态被吞，
    // 用户就再也点不到对话框（看起来像消失了）。这条 timer 是兜底。
    setTimeout(function () {
      console.log('[Preload-Chat][collapse] @1500ms safety check; opacity=', shell.style.opacity, 'classes=', shell.className, 'eMinimized=', eMinimized, 'eBusy=', eBusy);
      if (shell.style.opacity === '0') {
        console.warn('[Preload-Chat][collapse] opacity stuck at 0, force-clearing');
        shell.style.removeProperty('opacity');
      }
    }, 1500);

    // 折叠 IPC 失败的回滚：BrowserWindow 实际尺寸未变，渲染层必须撤回
    // .neko-e-collapsed / opacity:0，并保持 eMinimized=false，否则下一次点击
    // 会以为已折叠而走 expand 路径，把状态彻底搞死。
    function rollbackCollapse(err) {
      console.error('[Preload-Chat][collapse] W.collapse IPC failed, rolling back:', err);
      shell.classList.remove('neko-e-collapsed', 'neko-e-animating', 'is-collapsing');
      shell.style.removeProperty('opacity');
      shell.style.transformOrigin = '';
      eMinimized = false;
      eBusy = false;
    }

    anim.onfinish = function () {
      console.log('[Preload-Chat][collapse] anim.onfinish fired');
      anim.cancel();
      ballAnim.cancel();
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      shell.classList.remove('neko-e-animating');
      shell.style.removeProperty('opacity');
      if (!resized) {
        // 兜底：setTimeout 未触发时走原路径
        // 必须清除定时器，否则延迟触发的 setTimeout 会二次调用 W.collapse()，
        // 用已折叠的 84x84 覆盖 eSavedBounds，导致展开时窗口大小错误
        clearTimeout(collapseTimer);
        shell.classList.remove('is-collapsing');
        shell.classList.add('neko-e-collapsed');
        shell.style.transformOrigin = '';
        W.collapse().then(function (saved) {
          saveExpandBounds(saved || rect);
          eMinimized = true;
          eBusy = false;
        }).catch(rollbackCollapse);
      } else {
        // 等待 collapse IPC 完成再解锁，确保 eSavedBounds 已就位
        (collapsePromise || Promise.resolve()).then(function () {
          eMinimized = true;
          eBusy = false;
        }).catch(rollbackCollapse);
      }
    };
  }

  // ---- 展开：物理放大窗口 → 左下角定点放大 ----
  // 展开态最小允许尺寸（与主进程 RESIZE_MIN_W / RESIZE_MIN_H 保持一致）
  function doExpand() {
    if (eBusy || !eMinimized) return;
    var targetBounds = loadExpandBounds();
    if (!targetBounds) return;
    eSavedBounds = targetBounds;
    eBusy = true;

    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) { eBusy = false; return; }

    // 保存用户上次调整的大小，用于动画结束后兜底校验
    var _expandTargetW = eSavedBounds.width;
    var _expandTargetH = eSavedBounds.height;

    var sx = BALL_SIZE / eSavedBounds.width;
    var sy = BALL_SIZE / eSavedBounds.height;

    // 1. 立即隐藏折叠球 + shell，加 .is-expanding 解除 transform 锁
    shell.style.opacity = '0';
    shell.classList.remove('neko-e-collapsed');
    var ballIconInShell = shell.querySelector('.neko-e-ball-icon');
    if (ballIconInShell) ballIconInShell.style.opacity = '0';
    shell.classList.add('is-expanding', 'neko-e-animating');
    shell.style.transformOrigin = '0% 100%';

    // 2. 等 compositor 提交「空白帧」后再发 IPC resize。
    //    rAF 后浏览器 paint（renderer main thread）；
    //    setTimeout(32) 等两个 vsync 让 compositor thread 把帧提交给 DWM，
    //    即使系统高负载 compositor 错过一个 vsync 也有余量。
    //    总延迟 ~48ms，体感无差别。
    requestAnimationFrame(function () { setTimeout(function () {

    W.expand(eSavedBounds).then(function () {
      // 3. 窗口已展开，启动左下角放大动画
      shell.style.opacity = '';

      var anim = shell.animate([
        { transform: 'scale(' + sx + ',' + sy + ')', borderRadius: '50%', opacity: 0, offset: 0 },
        { transform: 'scale(' + sx + ',' + sy + ')', borderRadius: '50%', opacity: 1, offset: 0.06 },
        { transform: 'scale(1)', borderRadius: '22px', opacity: 1, offset: 1 }
      ], {
        duration: 500,
        easing: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
        fill: 'forwards',
      });

      // 球覆盖层：固定在左下角，开始时可见，立即渐隐
      var overlay = document.createElement('img');
      overlay.className = 'neko-e-ball-overlay';
      overlay.src = '/static/icons/expand_icon_off_ball.png';
      overlay.draggable = false;
      overlay.style.width = BALL_SIZE + 'px';
      overlay.style.height = BALL_SIZE + 'px';
      overlay.style.left = '0px';
      overlay.style.bottom = '0px';
      document.body.appendChild(overlay);

      var ballAnim = overlay.animate([
        { opacity: 1, offset: 0 },
        { opacity: 0, offset: 0.3 },
        { opacity: 0, offset: 1 }
      ], {
        duration: 500,
        easing: 'linear',
        fill: 'forwards',
      });

      anim.onfinish = function () {
        shell.classList.remove('is-expanding', 'neko-e-animating');
        shell.style.transformOrigin = '';
        shell.style.transform = 'none';
        if (ballIconInShell) ballIconInShell.style.opacity = '';
        anim.cancel();
        ballAnim.cancel();
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        eMinimized = false;
        clearExpandBounds();
        eBusy = false;

        // 安全兜底：动画结束后验证窗口大小。
        // 如果 bounceBackToWorkArea 竞态导致展开后窗口大小低于最小值 (320×280)，
        // 恢复到用户上次调整的大小，左下角对齐（向上展开），并约束到工作区。
        W.getBounds().then(function (bounds) {
          if (bounds && (bounds.width < EXPAND_MIN_W || bounds.height < EXPAND_MIN_H)) {
            // 左下角对齐：保持底边位置不变，向上展开
            var bottomY = bounds.y + bounds.height;
            var newY = bottomY - _expandTargetH;
            // 先恢复大小（左下角方向），再约束到工作区
            W.getWorkArea().then(function (wa) {
              var margin = 8;
              var cx = Math.max(wa.x + margin, Math.min(bounds.x, wa.x + wa.width - _expandTargetW - margin));
              var cy = Math.max(wa.y + margin, Math.min(newY, wa.y + wa.height - _expandTargetH - margin));
              W.setBounds(cx, cy, _expandTargetW, _expandTargetH);
            });
          }
        });
      };
    }).catch(function () { eBusy = false; });
    }, 32); });
  }

  function focusComposerInputFromHotkey() {
    var input = document.querySelector('#react-chat-window-shell textarea.composer-input, #react-chat-window-root textarea.composer-input, textarea.composer-input');
    if (!input || input.disabled || input.readOnly) return false;
    input.focus({ preventScroll: true });
    if (typeof input.setSelectionRange === 'function') {
      var len = input.value ? input.value.length : 0;
      input.setSelectionRange(len, len);
    }
    return true;
  }

  window.__nekoFocusReactChatInputFromHotkey = function () {
    if (eMinimized) {
      doExpand();
      setTimeout(function () { focusComposerInputFromHotkey(); }, 680);
      return true;
    }
    if (eBusy) {
      setTimeout(function () { focusComposerInputFromHotkey(); }, 180);
      return true;
    }
    return focusComposerInputFromHotkey();
  };

  // ---- 拦截 drag handle（capture phase，先于 app-react-chat-window.js）----
  // 增加移动检测：折叠态下未移动视为点击 → 触发展开
  var dragHandle = document.getElementById('react-chat-window-drag-handle');
  if (dragHandle) {
    dragHandle.addEventListener('mousedown', (e) => {
      if (e.button !== 0) {
        e.stopImmediatePropagation();
        e.preventDefault();
        return;
      }
      var close = document.getElementById('reactChatWindowCloseButton');
      var minimize = document.getElementById('reactChatWindowMinimizeButton');
      if (close && close.contains(e.target)) return;
      if (minimize && minimize.contains(e.target)) return;
      e.stopImmediatePropagation();

      var startX = e.screenX;
      var startY = e.screenY;
      var moved = false;

      if (_isNativeWayland) {
        // On native Wayland: getBounds/setBounds for repositioning is a no-op, and
        // getCursorScreenPoint() returns stale data. Instead, let -webkit-app-region:drag
        // (injected in CSS above) trigger xdg_toplevel.move natively — do NOT call
        // preventDefault so the browser sees the mousedown on the drag region.
        // We only track movement for the expand-on-click detection.
        ipcRenderer.send('neko:debug-log', '[preload-chat] Wayland drag: using native xdg_toplevel.move');
        var startTime = Date.now();
        var onMoveW = (ev) => {
          if (!moved && (Math.abs(ev.screenX - startX) > 3 || Math.abs(ev.screenY - startY) > 3)) {
            moved = true;
          }
        };
        var onUpW = () => {
          document.removeEventListener('mousemove', onMoveW);
          document.removeEventListener('mouseup', onUpW);
          // During xdg_toplevel.move the compositor intercepts pointer events, so
          // mousemove does not fire and moved stays false even after a real drag.
          // Use a 300ms threshold: a genuine click releases quickly; a drag takes longer.
          if (eMinimized && !moved && (Date.now() - startTime) < 300) {
            doExpand();
          }
        };
        document.addEventListener('mousemove', onMoveW);
        document.addEventListener('mouseup', onUpW);
        return;
      }

      // Non-Wayland path (Windows/Mac/X11): custom polling drag via setBounds
      e.preventDefault();
      document.documentElement.classList.add('neko-dragging');
      W.dragStart();

      var onMove = (ev) => {
        if (!moved && (Math.abs(ev.screenX - startX) > 3 || Math.abs(ev.screenY - startY) > 3)) {
          moved = true;
        }
      };
      var onUp = () => {
        document.documentElement.classList.remove('neko-dragging');
        W.dragStop();
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        // 折叠态 + 未拖拽 → 点击展开
        if (eMinimized && !moved) {
          doExpand();
        }
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }, { capture: true });

    // On Wayland, Chromium ignores CSS cursor on -webkit-app-region:drag elements.
    // Set the cursor on the html element (which is not subject to that override)
    // when hovering over the drag handle.
    if (_isNativeWayland && dragHandle) {
      ipcRenderer.send('neko:debug-log', '[preload-chat] Registering Wayland cursor handlers on drag handle');
      dragHandle.addEventListener('mouseenter', () => {
        ipcRenderer.send('neko:debug-log', '[preload-chat] mouseenter on drag handle (fired!)');
      });
      dragHandle.addEventListener('mouseleave', () => {
        ipcRenderer.send('neko:debug-log', '[preload-chat] mouseleave on drag handle (fired!)');
      });
      var _isNoDragTarget = (target) => {
        return !!(target && target.closest && target.closest('#reactChatWindowCloseButton, #reactChatWindowMinimizeButton'));
      };
      dragHandle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        if (_isNoDragTarget(e.target)) return;
        ipcRenderer.send('neko:debug-log', '[preload-chat] mousedown on drag handle — grabbing');
        _setCursorAll('grabbing');
      });
      document.addEventListener('mouseup', () => {
        if (_cursorState === 'grabbing') _setCursorAll('');
      });

      // Fallback: document-level mousemove to catch cases where mouseenter doesn't fire
      var _cursorState = ''; // 'grab', 'grabbing', or ''
      var _setCursorAll = (cur) => {
        if (_cursorState === cur) return;
        _cursorState = cur;
        ipcRenderer.send('neko:debug-log', '[preload-chat] _setCursorAll: ' + cur);
        if (cur) {
          dragHandle.style.setProperty('cursor', cur, 'important');
          document.documentElement.style.setProperty('cursor', cur, 'important');
          dragHandle.querySelectorAll('*').forEach(el => {
            if (_isNoDragTarget(el)) return;
            el.style.setProperty('cursor', cur, 'important');
          });
        } else {
          dragHandle.style.removeProperty('cursor');
          document.documentElement.style.removeProperty('cursor');
          dragHandle.querySelectorAll('*').forEach(el => {
            if (_isNoDragTarget(el)) return;
            el.style.removeProperty('cursor');
          });
        }
      };
      document.addEventListener('mousemove', (e) => {
        if (_isNoDragTarget(e.target)) {
          _setCursorAll('');
          return;
        }
        var rect = dragHandle.getBoundingClientRect();
        var inside = e.clientX >= rect.left && e.clientX <= rect.right &&
                     e.clientY >= rect.top && e.clientY <= rect.bottom;
        if (inside && _cursorState !== 'grabbing') {
          _setCursorAll('grab');
        } else if (!inside && _cursorState) {
          _setCursorAll('');
        }
      });
    }
  }

  // 拦截 resize edges
  requestAnimationFrame(() => {
    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) return;
    shell.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return;
      var edge = e.target.closest('[data-resize-dir]');
      if (!edge) return;
      e.stopPropagation();
      e.preventDefault();
      document.documentElement.classList.add('neko-resizing');
      W.resizeStart(edge.dataset.resizeDir, { minHeight: getElectronResizeMinHeight() });
      var up = () => {
        document.documentElement.classList.remove('neko-resizing');
        W.resizeStop();
        document.removeEventListener('mouseup', up);
      };
      document.addEventListener('mouseup', up);
    }, { capture: true });
  });

  // 拦截 close → 隐藏窗口
  // 注意：必须 stopImmediatePropagation，否则 app-react-chat-window.js 在同一按钮上
  // 注册的 bubble-phase listener 会继续触发（stopPropagation 只阻断到其他元素的传播，
  // 不阻止同元素其他 listener），它的 closeWindow 会改 overlay.hidden 等 web 态。
  var closeBtn = document.getElementById('reactChatWindowCloseButton');
  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopImmediatePropagation(); e.preventDefault();
      forwardAvatarToolStateToPet({
        active: false,
        toolId: null,
        tool: null,
        timestamp: Date.now(),
      });
      ipcRenderer.send('neko:hide-react-chat');
    }, { capture: true });
  }

  // 拦截 minimize → 折叠/展开窗口
  // 必须 stopImmediatePropagation：否则 app-react-chat-window.js 的 toggleMinimized
  // 会在同次点击中并行运行，添加 .is-minimized 类 + inline left/top + 触发自己的
  // CSS transition，与本 preload 的 neko-e-collapsed + element.animate() 抢同一个
  // transform。竞态会把 anim.onfinish 吞掉，导致 line 512 设的 opacity:0!important
  // 永远不被清，整个 shell（透明窗口）alpha=0 → Windows 下点击穿透 → 用户看到
  // "对话框消失/全透明 + 无法点击"。
  var minimizeBtn = document.getElementById('reactChatWindowMinimizeButton');
  console.log('[Preload-Chat] minimize button found:', !!minimizeBtn);
  if (minimizeBtn) {
    minimizeBtn.addEventListener('click', (e) => {
      console.log('[Preload-Chat] minimize click fired (capture phase), eMinimized=', eMinimized);
      e.stopImmediatePropagation(); e.preventDefault();
      if (eMinimized) {
        doExpand();
      } else {
        doCollapse();
      }
    }, { capture: true });
  }

  // 页面在折叠态刷新时，渲染进程状态会丢失，但 BrowserWindow 仍可能保持 84x84。
  // 主动恢复折叠状态和上次展开尺寸，避免用户点击后把 84x84 当成目标尺寸继续“展开一点点”。
  requestAnimationFrame(function () {
    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) return;
    W.getBounds().then(function (bounds) {
      if (!bounds) return;
      if (bounds.width <= WIN_SIZE + 2 && bounds.height <= WIN_SIZE + 2) {
        ensureBallIcon();
        eMinimized = true;
        eSavedBounds = loadExpandBounds();
        shell.classList.add('neko-e-collapsed');
      }
    }).catch(function () {});
  });

  // 自动打开 React Chat（轮询等待 reactChatWindowHost 就绪，最多 3 秒）
  var _openAttempts = 0;
  function _tryAutoOpen() {
    if (window.reactChatWindowHost && typeof window.reactChatWindowHost.openWindow === 'function') {
      window.reactChatWindowHost.openWindow();
    } else if (++_openAttempts < 30) {
      setTimeout(_tryAutoOpen, 100);
    }
  }
  setTimeout(_tryAutoOpen, 200);
});

console.log('[Preload-Chat] 初始化完成（WSProxy + 窗口管理，无 stub）');
