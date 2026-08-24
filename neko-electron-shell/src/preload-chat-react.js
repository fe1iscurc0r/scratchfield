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
// [compact-ball-removed] COMPACT_CHAT_BALL_CHANNELS：compact 悬浮球已停用，整套清理时移除其使用与解构。
const { WINDOW_CONTROL_CHANNELS, WS_PROXY_CHANNELS, CHAT_CHANNELS, CHAT_ACTION_CHANNELS, JUKEBOX_CHANNELS, PET_CHANNELS, COMPACT_CHAT_BALL_CHANNELS, CHAT_SURFACE_CHANNELS, SUBTITLE_CHANNELS } = require('./ipc-channels');
const { setupToastOverride, suppressVoiceToast, setupDarkMode, setupElectronShell, setupHostCapabilityBridge, setupTutorialOverlayBridge, setupTutorialLoadingOverlayBridge, setupGoodbyeChatComposerHiddenBridge, setupVoiceConfigSwitchingBridge, setupMusicPlayerBridge, setupSettingsSync, syncSubtitleToggleFromWindow } = require('./preload-common');
const desktopCompactLayoutTools = require('./desktop-compact-layout');

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
function setCompactChatBallTemporarilyHidden(hidden) {
  ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.SET_TEMPORARY_HIDDEN, { hidden: !!hidden });
}

window.nekoChatWindow = {
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
  getWorkArea: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_WORKAREA),
  setPosition: (x, y) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_POSITION, { x, y }),
  setSize: (w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_SIZE, { w, h }),
  setBounds: (x, y, w, h) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, { x, y, w, h }),
  setResizable: (v, options) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.SET_RESIZABLE, Object.assign({
    resizable: v
  }, options || {})),
  bringToFront: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT),
  dragStart: (payload) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, payload || {}),
  dragStop: (payload) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_STOP, payload || {}),
  dragStopAndGetBounds: (payload) => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.DRAG_STOP_AND_GET_BOUNDS, payload || {}),
  resizeStart: (direction, options) => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_START, {
    direction: direction || 'se',
    minWidth: options && options.minWidth,
    minHeight: options && options.minHeight,
  }),
  resizeStop: () => ipcRenderer.send(WINDOW_CONTROL_CHANNELS.RESIZE_STOP),
  collapse: (targetBounds) => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.COLLAPSE, targetBounds || null),
  expand: (savedBounds) => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.EXPAND, savedBounds),
  enableInteraction: () => ipcRenderer.send('set-ignore-mouse-events', false),
  setCompactChatBallTemporarilyHidden,
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
setupTutorialOverlayBridge();
setupTutorialLoadingOverlayBridge();
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
  if (typeof window.__nekoGetAvatarToolClientScreenPoint === 'function') {
    try {
      var compactPoint = window.__nekoGetAvatarToolClientScreenPoint(x, y);
      var compactScreenX = normalizeAvatarToolFiniteNumber(compactPoint && compactPoint.screenX);
      var compactScreenY = normalizeAvatarToolFiniteNumber(compactPoint && compactPoint.screenY);
      if (compactScreenX !== null && compactScreenY !== null) {
        return { cursorScreenX: compactScreenX, cursorScreenY: compactScreenY };
      }
    } catch (_) {}
  }
  var layoutBounds = window.__nekoDesktopCompactLayout && window.__nekoDesktopCompactLayout.windowBounds;
  var layoutX = normalizeAvatarToolFiniteNumber(layoutBounds && layoutBounds.x);
  var layoutY = normalizeAvatarToolFiniteNumber(layoutBounds && layoutBounds.y);
  if (layoutX !== null && layoutY !== null) {
    return { cursorScreenX: layoutX + x, cursorScreenY: layoutY + y };
  }
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
  if (typeof window.__nekoGetAvatarToolScreenClientPoint === 'function') {
    try {
      var compactPoint = window.__nekoGetAvatarToolScreenClientPoint(x, y);
      var compactClientX = normalizeAvatarToolFiniteNumber(compactPoint && compactPoint.clientX);
      var compactClientY = normalizeAvatarToolFiniteNumber(compactPoint && compactPoint.clientY);
      if (compactClientX !== null && compactClientY !== null) {
        return { clientX: compactClientX, clientY: compactClientY };
      }
    } catch (_) {}
  }
  var layoutBounds = window.__nekoDesktopCompactLayout && window.__nekoDesktopCompactLayout.windowBounds;
  var layoutX = normalizeAvatarToolFiniteNumber(layoutBounds && layoutBounds.x);
  var layoutY = normalizeAvatarToolFiniteNumber(layoutBounds && layoutBounds.y);
  if (layoutX !== null && layoutY !== null) {
    return { clientX: x - layoutX, clientY: y - layoutY };
  }
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
window.__NEKO_DESKTOP_RUNTIME__ = Object.freeze({
  platform: process.platform,
  isLinux: process.platform === 'linux',
  isLinuxX11: process.platform === 'linux' && !_isNativeWayland,
  isWayland: _isNativeWayland
});
// Linux cannot use the Win32 opacity carrier path: Electron setOpacity() is a
// no-op there. Keep the chat BrowserWindow itself as the minimized yarn ball so
// dragging/click restore use the real current window bounds on both X11 and
// native Wayland.
var _useExternalMinimizedBallWindow = process.platform !== 'linux';

// ===== DOM 拦截：app-react-chat-window.js 的页面内 drag/resize → BrowserWindow 操作 =====
var reactChatDomInterceptorsInitialized = false;
function setupReactChatDomInterceptors() {
  if (reactChatDomInterceptorsInitialized) return;
  reactChatDomInterceptorsInitialized = true;
  var W = window.nekoChatWindow;
  var WIN_SIZE = 88;   // 折叠窗口物理尺寸（给放大的 yarn ball 保留点击余量）
  var BALL_SIZE = 58;  // 72px 缩小 20%
  var BALL_DOWN_OFFSET = 14;
  var MINIMIZED_BALL_ICON_SRC = '/static/assets/neko-idle/chat-minimized-yarn-ball-116.png';
  var MINIMIZED_BALL_ICON_SRCSET = '/static/assets/neko-idle/chat-minimized-yarn-ball-116.png 1x, /static/assets/neko-idle/chat-minimized-yarn-ball-232.png 2x';
  var DESKTOP_COMPACT_MINIMIZE_BALL_SELECTOR = '.compact-chat-minimize-ball';
  var DESKTOP_COMPACT_MINIMIZE_BUTTON_RECT_STALE_MS = 2000;

  function isCarrierWindowCollapsed(bounds) {
    var w = Number(bounds && bounds.width);
    var h = Number(bounds && bounds.height);
    return Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0 && w <= WIN_SIZE + 2 && h <= WIN_SIZE + 2;
  }

  function recoverCompactMinimizedStateFromWindowBounds(payload, options) {
    options = options || {};
    eMinimized = true;
    var shell = document.getElementById('react-chat-window-shell');
    if (shell) {
      ensureBallIcon();
      shell.classList.add('neko-e-collapsed');
    }
    var payloadAnchor = normalizeCollapsedBounds(payload && payload.anchorBounds);
    if (payloadAnchor) {
      _ballAnchorBoundsBeforeExpand = payloadAnchor;
      if (_isNativeWayland && !_useExternalMinimizedBallWindow) {
        setDesktopCompactWaylandSelfBallAnchorBounds(payloadAnchor, null, 'self-ball-wayland-recover');
      }
    }
    eSavedBounds = loadExpandBounds();
    setReactChatSurfaceMode('minimized');

    if (!options.restore || !_useExternalMinimizedBallWindow) {
      if (options.silentRestore) return Promise.resolve(false);
      emitCompactChatRestoreComplete();
      return Promise.resolve(false);
    }

    return restoreCompactDesktopFromMinimized({
      skipBallHide: true,
      anchorBounds: payloadAnchor
    }).then(function (restored) {
      if (restored === true || restored === 'queued' || restored === 'canceled') {
        return true;
      }
      emitCompactChatRestoreComplete();
      return false;
    }).catch(function () {
      emitCompactChatRestoreComplete();
      return false;
    });
  }

  // ---- 折叠/展开状态 ----
  var eMinimized = false;
  var eSavedBounds = null;
  var eBusy = false;
  var activeAnimationCleanup = null;
  var ePendingChatSurfaceMode = null;
  var eCompactChatRestoreSequence = 0;
  var eCompactChatRestoreSession = (
    Number.isFinite(Date.now())
      ? Date.now()
      : Math.round(Math.random() * 1000000)
  ) + '-' + Math.round(Math.random() * 1000000000);
  var eSurfaceTransitionState = 'idle';
  var eSurfaceTransitionSeq = 0;
  var eSurfaceActionLockUntil = 0;
  var eHiddenByClose = false;
  var idleDockSavedSurfaceMode = null;

  function getCurrentSelfBallAnchorBounds() {
    if (_useExternalMinimizedBallWindow || !eMinimized) return Promise.resolve(null);
    if (_isNativeWayland) {
      var waylandSelfBallAnchor = getDesktopCompactWaylandSelfBallAnchorBounds();
      if (waylandSelfBallAnchor) return Promise.resolve(waylandSelfBallAnchor);
    }
    if (typeof W.getBounds !== 'function') return Promise.resolve(null);
    return W.getBounds().then(function (bounds) {
      return normalizeCollapsedBounds(bounds);
    }).catch(function () {
      return null;
    });
  }

  var E_SAVED_BOUNDS_KEY = 'neko.reactChatWindow.electronSavedBounds';
  var EXPAND_MIN_W = 320;
  var EXPAND_MIN_H = 280;
  var GALGAME_EXPAND_MIN_H = 385;
  // 附件预览（截图 / 导入图片）单卡 90px + 间距，需要的下限和 galgame slot 同级。
  var ATTACHMENTS_EXPAND_MIN_H = 385;
  // galgame + 附件并存的极端情况：两份预算（slot ~110 + 卡片 ~110）叠加。
  // 与 chat.html 的 MIN_H_GALGAME_ATTACHMENTS 保持一致。
  var GALGAME_ATTACHMENTS_EXPAND_MIN_H = 495;
  var COMPACT_SURFACE_POSITION_STORAGE_KEY = 'neko.reactChatWindow.compactSurfacePosition';
  var DESKTOP_COMPACT_SURFACE_POSITION_KEY = 'neko.reactChatWindow.desktopCompactSurfacePosition';
  var DESKTOP_COMPACT_FALLBACK_WORKAREA_WIDTH = 680;
  var DESKTOP_COMPACT_SURFACE_MAX_WIDTH = 430;
  var DESKTOP_COMPACT_TUTORIAL_FIXED_SURFACE_WIDTH = 400;
  var DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH = 720;
  // 与渲染器 react-neko-chat 的 COMPACT_SURFACE_RESIZE_MIN_WIDTH 保持一致：
  // 用户可把 compact surface 拖到 180，读回持久化宽度时的下限必须对齐，否则 180–279
  // 区间的存量宽度会被夹回 280（#214 旧硬编码下限），重启/恢复就复位。
  var DESKTOP_COMPACT_SURFACE_RESIZE_MIN_WIDTH = 180;
  var DESKTOP_COMPACT_SURFACE_DEFAULT_HEIGHT = 58;
  var DESKTOP_COMPACT_SURFACE_PAD_X = 16;
  var DESKTOP_COMPACT_SURFACE_AVATAR_VERTICAL_RATIO = 0.8;
  // DESKTOP_COMPACT_BALL_{GAP,VERTICAL_RATIO,VIEWPORT_PAD} 已随悬浮球移除而删除
  // （见 buildDesktopCompactBallScreenRect）。
  var DESKTOP_COMPACT_NATIVE_PAD = 8;
  var DESKTOP_COMPACT_SHAPE_SLOP = 3;
  var DESKTOP_COMPACT_X11_NATIVE_REGION_MIN_MS = 96;
  var DESKTOP_COMPACT_HISTORY_DRAG_STALE_MS = 15000;
  var DESKTOP_COMPACT_HISTORY_DRAG_RESTORE_MS = 180;
  var DESKTOP_COMPACT_TOOL_WHEEL_DRAG_STALE_MS = 5000;
  var DESKTOP_COMPACT_TOOL_FAN_VISIBLE_RETRY_MAX = 12;
  var DESKTOP_COMPACT_TOOL_FAN_LAYOUT_RETRY_MAX = 12;
  var DESKTOP_COMPACT_TOOL_FAN_VISIBLE_OPACITY_MIN = 0.01;
  var DESKTOP_COMPACT_HISTORY_AVATAR_RANGE_PADDING = 100;
  var DESKTOP_COMPACT_POINTER_PASSTHROUGH_POLL_MS = 16;
  var DESKTOP_COMPACT_POINTER_HIT_GUARD_PX = 8;
  var DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_X = 10;
  var DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_TOP = 2;
  var DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_BOTTOM = 28;
  var DESKTOP_COMPACT_HISTORY_RESIZE_ISOLATION_HIT_PAD = 24;
  var DESKTOP_COMPACT_HISTORY_RESIZE_ENVELOPE_CHUNK_PX = 220;
  var DESKTOP_COMPACT_HISTORY_RESIZE_SOFT_STALE_MS = 1200;
  var DESKTOP_COMPACT_HISTORY_RESIZE_HARD_WATCHDOG_MS = 10000;
  var DESKTOP_COMPACT_SURFACE_POINTER_RAISE_MIN_MS = 180;
  var DESKTOP_COMPACT_WAYLAND_BALL_CLICK_MAX_MS = 180;
  var DESKTOP_COMPACT_WAYLAND_BALL_CLICK_FALLBACK_MS = 520;
  var DESKTOP_COMPACT_WAYLAND_BALL_DRAG_BOUNDS_DELTA = 3;
  var DESKTOP_COMPACT_WAYLAND_BALL_RESTORE_RETRY_DELAYS = [80, 180, 360, 620];
  var DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_SIZE = 44;
  var DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_MOVE_PX = 5;
  var desktopCompactAvatarPayload = null;
  var desktopCompactWindowActive = false;
  var desktopCompactWindowSavePending = false;
  var desktopCompactWindowRelayoutQueued = false;
  var desktopCompactRelayoutFrame = 0;
  var desktopCompactLayout = null;
  var desktopCompactWindowSnapshot = '';
  var desktopCompactPendingWindowBounds = null;
  var desktopCompactBoundsVerificationTimers = [];
  var desktopCompactBoundsVerificationSnapshot = '';
  var desktopCompactBoundsVerificationCompletedSnapshot = '';
  var desktopCompactAvatarBoundsSubscribed = null;
  var desktopCompactSurfaceDragPrimeActive = false;
  var desktopCompactSurfaceDragPrimePointerId = null;
  var desktopCompactSurfaceDragPrimeCleanup = null;
  var desktopCompactSurfaceDragActive = false;
  var desktopCompactSurfaceDragTarget = null;
  var desktopCompactSurfaceDragSettledTarget = null;
  var desktopCompactSurfaceDragSettledWorkArea = null;
  // [multi-display-independence] 拖动 compact 气泡跨屏时，主进程随 DRAG_ANCHOR_MOVE
  // 附带“光标目标屏”的工作区；getDesktopCompactWorkArea 在拖拽期用它作为布局基准，
  // 否则 clampScreenRectToWorkArea 会把 surface 橡皮筋拉回窗口原屏，气泡过不到别的屏。
  var desktopCompactSurfaceDragWorkArea = null;
  var desktopCompactSurfaceResizeActive = false;
  var desktopCompactSurfaceResizeTarget = null;
  var desktopCompactSurfaceResizeSide = null;
  var desktopCompactSurfaceResizeStartTarget = null;
  var desktopCompactSurfaceResizeStartWindowBounds = null;
  var desktopCompactSurfaceResizeCarrierBounds = null;
  var desktopCompactSurfaceResizePassiveCarrierBounds = null;
  var desktopCompactSurfaceResizePassiveCarrierWorkArea = null;
  var desktopCompactSurfaceResizeKeepCarrierOnCommit = false;
  // 本次 resize 是否真的改变过宽度（即收到过 'move'）。纯点击 resize 手柄只会发
  // 'start'+'end'、不发 'move'；此时不应把"按下瞬间量到的 frame 顶/宽度"落库为
  // surface 位置——否则会污染存储位置，随后一次 relayout 把无边框窗口按存储顶 +
  // 内边距重新定位，导致界面整体下移。仅在真正拖动过才提交保存。
  var desktopCompactSurfaceResizeMoved = false;
  // 起拖时锁定的 surface 锚点（surfaceUnion）顶，屏幕坐标。宽度 resize 不应改变竖直位置，
  // 但 React 送来的 resize 目标 top 量自 .compact-chat-surface-frame，与布局所用的 surface
  // 锚点（input/shell）相差一个固定渲染偏移，且该偏移每次提交后随实测反馈逐步累积 →
  // 整窗每拖一次净漂几像素下移。这里在 'start' 钉死锚点 top，整个拖动 + 提交都用它覆盖
  // React 的 frame 顶，使竖直位置零漂移。
  var desktopCompactSurfaceResizeAnchorTopScreen = null;
  var desktopCompactNativeRegionSnapshot = '';
  var desktopCompactBallWindowSnapshot = ''; // [compact-ball-removed] 死变量：球已停用，恒为 ''。
  // 球的 anchor bounds —— CLICK handler 在调 doExpand 前用 W.getBounds() 抓取 chatWin
  // 当前 bounds（=DRAG_MOVE 同步过的球最终位置）。doExpand 用它反推出「surface 应当出现
  // 的屏幕位置」写进 stored surface，让 desktop compact 自然算法把对话条锚到球的位置。
  var _ballAnchorBoundsBeforeExpand = null;
  // 折叠瞬间记录的「surface 左上角 − 球 88px anchor 左上角」差量。折叠落点已改为毛线球
  // 按钮中心（buildDesktopCompactCollapseTargetFromRect），不再满足旧的「球左下角 = surface
  // 左下角」关系；恢复端若仍按旧关系逆变换，按钮中心相对 surface 左下角的固定偏差会每轮
  // 折叠↔展开累积一次（实测每轮下移 ~2px、左移 ~6px 无限漂移）。球被拖动时 anchor 与
  // surface 同步平移、差量不变，所以恢复端用 anchor+差量还原是与折叠严格互逆的。
  // 差量缺失（exit-retention 重启后等）时退回旧的左下角近似公式。
  var _minimizedBallSurfaceRestoreDelta = null;
  // 折叠瞬间保存的 layout 镜像 —— doExpand 时只取其中的 surface 尺寸（width/height）来反推
  // stored surface 的目标矩形（top 需要 surface 高度）。
  //   surface: { left, top, width, height }  —— surface 在 chatWin 内的 client offset
  //   windowBounds: { width, height }        —— layout 算的 chatWin 完整 size（含透明 buffer）
  var _lastLayoutForRestore = null;
  var desktopCompactMinimizeButtonScreenRect = null;
  var desktopCompactMinimizeButtonScreenRectTimestamp = 0;
  var desktopCompactPageLayoutSnapshot = '';
  var desktopCompactInteractionGeometrySummary = '';
  var desktopCompactTransientGeometrySummary = '';
  var desktopCompactNativeRegionLastSentAt = 0;
  var desktopCompactNativeRegionPendingTimer = 0;
  var desktopCompactNativeRegionPendingRects = null;
  var desktopCompactNativeRegionPendingSnapshot = '';
  var desktopCompactNativeRegionPendingBounds = null;
  var desktopCompactNativeRegionPendingReason = '';
  var desktopCompactNativeRegionPendingMode = '';
  var desktopCompactNativeRegionPendingScreenRects = null;
  var desktopCompactHistoryPointerPassthrough = false;
  var desktopCompactHistoryPointerPassthroughPollTimer = 0;
  var desktopCompactHistoryPointerPassthroughPollInFlight = false;
  var desktopCompactHistoryHoverActive = false;
  var desktopCompactHistoryHoverPollTimer = 0;
  var desktopCompactHistoryHoverPollInFlight = false;
  var desktopCompactHistoryDragState = null;
  var desktopCompactHistoryDragSnapshot = '';
  var desktopCompactHistoryDragCarrierBounds = null;
  var desktopCompactHistoryResizeCarrierBounds = null;
  var desktopCompactHistoryResizePassiveCarrierBounds = null;
  var desktopCompactHistoryResizePassiveCarrierWorkArea = null;
  var desktopCompactHistoryResizeActive = false;
  var desktopCompactHistoryResizeCommitPending = false;
  var desktopCompactHistoryResizeKeepCarrierOnCommit = false;
  var desktopCompactHistoryResizeCommitTimer = 0;
  var historyResizeIsolation = null;
  var desktopCompactHistoryDragClearTimer = 0;
  var desktopCompactHistoryDragRestoreActive = false;
  var desktopCompactHistoryDragRestoreTimer = 0;
  var desktopCompactToolWheelDragActive = false;
  var desktopCompactToolWheelDragClearTimer = 0;
  var desktopCompactLastPointerRaiseAt = 0;
  var desktopCompactAvatarBoundsOnlySnapshot = '';
  var desktopCompactWaylandSelfBallAnchorBounds = null;
  var desktopCompactWaylandSelfBallCarrierBounds = null;
  var desktopCompactWaylandSelfBallBlurCleanup = null;
  // While the tool wheel is open the page asks us to keep the whole surface
  // solid, so mouse-wheel scrolling responds across the entire circle rather
  // than only over the icon buttons. Released when the wheel closes.
  var desktopCompactToolFanOpenSolid = false;
  var desktopCompactToolFanVisibleRetryFrame = 0;
  var desktopCompactToolFanVisibleRetryCount = 0;
  var desktopCompactToolFanLayoutRetryCount = 0;
  var desktopCompactHistoryPassiveReserveRect = null;
  var desktopCompactTutorialFixedLayoutActive = false;
  var desktopCompactTutorialFixedSurfaceSize = null;
  var desktopCompactTutorialFixedLayoutRunId = '';
  var desktopCompactTutorialFixedLayoutTimestamp = 0;
  var desktopCompactSurfaceDragCancelForTutorial = null;
  var desktopCompactSurfaceDragCleanupForTutorial = null;
  window.__nekoDesktopCompactHistoryPointerPassthrough = false;
  window.__nekoDesktopCompactHistoryDragState = null;
  var nekoForceInteractive = !!window.__nekoForceInteractive;

  function isSurfaceTransitionInProgress() {
    return eSurfaceTransitionState !== 'idle';
  }

  var SURFACE_ACTION_LOCK_MS = 520;

  function isSurfaceActionBlocked() {
    return isSurfaceTransitionInProgress() || eBusy;
  }

  function isSurfaceActionLocked() {
    return desktopCompactTutorialFixedLayoutActive || isSurfaceActionBlocked() || Date.now() < eSurfaceActionLockUntil;
  }
  var eSurfaceActionLockTimer = 0;

  function isCompactSurfaceActionEventTarget(target) {
    if (!target) return false;
    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) return false;
    var node = target.nodeType === 3 ? target.parentNode : target;
    for (var i = 0; node && i < 14; i += 1, node = node.parentElement) {
      if (!node) break;
      if (node === shell || shell.contains(node)) return true;
      if (node === document) break;
      if (node.closest && node.closest('#reactChatWindowMinimizeButton')) return true;
      if (node.closest && node.closest('#reactChatWindowDragHandle')) return true;
      if (node.closest && node.closest('#reactChatWindowCloseButton')) return true;
    }
    return false;
  }

  function shouldBlockSurfaceActionEvent(event) {
    if (!event || !isSurfaceActionLocked()) return false;
    if (_isNativeWayland && isWaylandSelfBallClickTarget(event.target || event.srcElement)) return false;
    return isCompactSurfaceActionEventTarget(event.target || event.srcElement);
  }

  function isDesktopCompactSurfacePointerRaiseTarget(target) {
    if (isCompactSurfaceActionEventTarget(target)) return true;
    var node = target && target.nodeType === 3 ? target.parentNode : target;
    return !!(node && node.closest && node.closest('[data-compact-geometry-owner="surface"]'));
  }

  function maybeRaiseDesktopCompactSurfaceForPointer(event) {
    if (!event || getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) return;
    if (!isDesktopCompactSurfacePointerRaiseTarget(event.target || event.srcElement)) return;
    var now = Date.now();
    if (now - desktopCompactLastPointerRaiseAt < DESKTOP_COMPACT_SURFACE_POINTER_RAISE_MIN_MS) return;
    desktopCompactLastPointerRaiseAt = now;
    if (typeof W.bringToFront === 'function') {
      W.bringToFront();
    }
  }

  function clearDesktopCompactSurfaceDragPrime() {
    var cleanup = desktopCompactSurfaceDragPrimeCleanup;
    desktopCompactSurfaceDragPrimeCleanup = null;
    if (cleanup) cleanup();
    desktopCompactSurfaceDragPrimeActive = false;
    desktopCompactSurfaceDragPrimePointerId = null;
  }

  function beginSurfaceTransition(label) {
    eSurfaceTransitionSeq += 1;
    eSurfaceTransitionState = label || 'busy';
    return eSurfaceTransitionSeq;
  }

  function endSurfaceTransition(token) {
    if (token !== eSurfaceTransitionSeq) return;
    if (!isSurfaceTransitionInProgress()) return;
    eSurfaceTransitionState = 'idle';
    eSurfaceActionLockUntil = Date.now() + SURFACE_ACTION_LOCK_MS;
    if (eSurfaceActionLockTimer) {
      clearTimeout(eSurfaceActionLockTimer);
    }
    eSurfaceActionLockTimer = window.setTimeout(function () {
      if (!isSurfaceActionLocked()) {
        flushPendingChatSurfaceMode();
      }
    }, SURFACE_ACTION_LOCK_MS + 8);
    schedulePendingWaylandSelfBallClickRestore('transition-end');
  }

  Object.defineProperty(window, '__nekoForceInteractive', {
    get: function () { return nekoForceInteractive; },
    set: function (v) {
      var next = !!v;
      if (nekoForceInteractive === next) return;
      nekoForceInteractive = next;
      if (next) {
        setDesktopCompactHistoryPointerPassthrough(false);
      }
      if (desktopCompactLayout) {
        applyDesktopCompactNativeRegion(desktopCompactLayout);
        syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
      } else {
        scheduleDesktopCompactRelayout();
      }
    },
    configurable: true
  });
  var desktopCompactInputRegionBackend = null;
  try { desktopCompactInputRegionBackend = ipcRenderer.sendSync('neko:input-region-backend'); } catch (_) {}
  var desktopCompactHasSetShape = !!(desktopCompactInputRegionBackend && desktopCompactInputRegionBackend.canUseSetShape);
  if (!desktopCompactInputRegionBackend) {
    try { desktopCompactHasSetShape = !!ipcRenderer.sendSync('neko:has-set-shape'); } catch (_) {}
  }
  var desktopCompactUseX11InputShape = process.platform === 'linux' && !_isNativeWayland && !desktopCompactHasSetShape;
  var desktopCompactCanApplyNativeInputRegion = desktopCompactHasSetShape || desktopCompactUseX11InputShape;
  var desktopCompactX11InputShapeActive = false;
  if (desktopCompactUseX11InputShape) {
    try { desktopCompactX11InputShapeActive = !!ipcRenderer.sendSync('neko:x11-input-shape-active'); } catch (_) {}
  }
  var desktopCompactUsesNativeInputRegion = desktopCompactHasSetShape || (desktopCompactUseX11InputShape && desktopCompactX11InputShapeActive);
  try {
    ipcRenderer.send('neko:debug-log', '[preload-chat] input-region-backend=' + JSON.stringify({
      wayland: _isNativeWayland,
      backend: desktopCompactInputRegionBackend && desktopCompactInputRegionBackend.backend,
      canUseSetShape: desktopCompactHasSetShape,
      patch: desktopCompactInputRegionBackend && desktopCompactInputRegionBackend.patch
    }));
  } catch (_) {}

  function getDesktopCompactHistoryResizeIsolationMode() {
    if (_isNativeWayland) return 'unsupported-wayland';
    if (desktopCompactCanApplyNativeInputRegion) return 'native-region';
    return 'pointer-passthrough';
  }

  function updateDesktopCompactNativeInputRegionActive(active) {
    if (!desktopCompactUseX11InputShape) return;
    desktopCompactX11InputShapeActive = !!active;
    desktopCompactUsesNativeInputRegion = desktopCompactHasSetShape || (desktopCompactUseX11InputShape && desktopCompactX11InputShapeActive);
  }

  function applyDesktopCompactX11InputShapeActive(active) {
    if (!desktopCompactUseX11InputShape) return;
    updateDesktopCompactNativeInputRegionActive(active);
    if (desktopCompactUsesNativeInputRegion) {
      setDesktopCompactHistoryPointerPassthrough(false);
    } else {
      desktopCompactNativeRegionSnapshot = '';
    }
    if (desktopCompactLayout) {
      if (desktopCompactUsesNativeInputRegion) {
        applyDesktopCompactNativeRegion(desktopCompactLayout);
      }
      syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
    }
  }

  ipcRenderer.on('neko:x11-input-shape-active', function (_event, active) {
    applyDesktopCompactX11InputShapeActive(active);
  });

  function isReactChatWindowHidden() {
    return !!(eHiddenByClose || document.hidden);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      eHiddenByClose = true;
      clearDesktopCompactLayout();
      clearDesktopCompactNativeRegion();
      hideDesktopCompactBallWindow(); // [compact-ball-removed] no-op 兜底（球已停用）
      setDesktopCompactAvatarBoundsSubscription(false);
      return;
    }
    eHiddenByClose = false;
    var mode = getCurrentReactChatSurfaceMode();
    setDesktopCompactAvatarBoundsSubscription(mode === 'compact' || mode === 'minimized');
    if (mode === 'compact' && !eMinimized) {
      scheduleDesktopCompactRelayout();
    }
  });

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

  function normalizeCollapsedBounds(bounds) {
    if (!bounds) return null;
    var width = Math.round(Number(bounds.width) || 0);
    var height = Math.round(Number(bounds.height) || 0);
    var x = Math.round(Number(bounds.x) || 0);
    var y = Math.round(Number(bounds.y) || 0);
    if (!Number.isFinite(width) || !Number.isFinite(height) || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    if (width <= 0 || height <= 0) return null;
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

  function clamp(value, min, max) {
    if (max < min) return min;
    return Math.max(min, Math.min(value, max));
  }

  function normalizeRect(raw) {
    if (!raw) return null;
    var left = Number(raw.left);
    var top = Number(raw.top);
    var width = Number(raw.width);
    var height = Number(raw.height);
    if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) return null;
    if (width <= 0 || height <= 0) return null;
    return {
      left: left,
      top: top,
      width: width,
      height: height,
      right: Number.isFinite(Number(raw.right)) ? Number(raw.right) : left + width,
      bottom: Number.isFinite(Number(raw.bottom)) ? Number(raw.bottom) : top + height,
      centerX: Number.isFinite(Number(raw.centerX)) ? Number(raw.centerX) : left + width / 2,
      centerY: Number.isFinite(Number(raw.centerY)) ? Number(raw.centerY) : top + height / 2
    };
  }

  function normalizeClientPoint(raw) {
    if (!raw) return null;
    var clientX = Number(raw.clientX);
    var clientY = Number(raw.clientY);
    if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
    return { clientX: clientX, clientY: clientY };
  }

  function normalizeWindowBounds(raw) {
    if (!raw) return null;
    var x = Number(raw.x);
    var y = Number(raw.y);
    var width = Number(raw.width);
    var height = Number(raw.height);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return null;
    if (width <= 0 || height <= 0) return null;
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(1, Math.round(width)),
      height: Math.max(1, Math.round(height))
    };
  }

  function normalizeDesktopCompactWaylandSelfBallAnchorBounds(raw) {
    if (!raw) return null;
    var x = Number.isFinite(Number(raw.x)) ? Number(raw.x) : Number(raw.left);
    var y = Number.isFinite(Number(raw.y)) ? Number(raw.y) : Number(raw.top);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: WIN_SIZE,
      height: WIN_SIZE
    };
  }

  function getDesktopCompactWaylandSelfBallAnchorBounds() {
    var anchor = normalizeDesktopCompactWaylandSelfBallAnchorBounds(desktopCompactWaylandSelfBallAnchorBounds);
    return anchor ? {
      x: anchor.x,
      y: anchor.y,
      width: anchor.width,
      height: anchor.height
    } : null;
  }

  function buildDesktopCompactWaylandSelfBallScreenRect(anchorBounds) {
    var anchor = normalizeDesktopCompactWaylandSelfBallAnchorBounds(anchorBounds);
    if (!anchor) return null;
    return {
      x: anchor.x,
      y: anchor.y,
      left: anchor.x,
      top: anchor.y,
      width: anchor.width,
      height: anchor.height,
      right: anchor.x + anchor.width,
      bottom: anchor.y + anchor.height,
      centerX: anchor.x + anchor.width / 2,
      centerY: anchor.y + anchor.height / 2
    };
  }

  function getDesktopCompactWaylandSelfBallCarrierBounds(fallbackBounds) {
    var normalized = normalizeWindowBounds(fallbackBounds)
      || normalizeWindowBounds(desktopCompactWaylandSelfBallCarrierBounds)
      || getDesktopCompactRendererWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds)
      || normalizeWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds);
    if (normalized) return normalized;
    return normalizeWindowBounds({
      x: 0,
      y: 0,
      width: Number(window.innerWidth) || WIN_SIZE,
      height: Number(window.innerHeight) || WIN_SIZE
    });
  }

  function buildDesktopCompactWaylandSelfBallLocalRect(anchorBounds, carrierBounds) {
    var anchor = normalizeDesktopCompactWaylandSelfBallAnchorBounds(anchorBounds);
    var carrier = getDesktopCompactWaylandSelfBallCarrierBounds(carrierBounds);
    if (!anchor || !carrier) return null;
    var viewportWidth = Math.max(1, Math.round(Number(window.innerWidth) || carrier.width || anchor.width));
    var viewportHeight = Math.max(1, Math.round(Number(window.innerHeight) || carrier.height || anchor.height));
    var localX = Math.round(anchor.x - carrier.x);
    var localY = Math.round(anchor.y - carrier.y);
    return {
      x: clamp(localX, 0, Math.max(0, viewportWidth - anchor.width)),
      y: clamp(localY, 0, Math.max(0, viewportHeight - anchor.height)),
      width: anchor.width,
      height: anchor.height
    };
  }

  function applyDesktopCompactWaylandSelfBallCssVars(anchorBounds, carrierBounds) {
    var anchor = normalizeDesktopCompactWaylandSelfBallAnchorBounds(anchorBounds);
    var shell = document.getElementById('react-chat-window-shell');
    var targets = [document.documentElement, shell].filter(Boolean);
    var props = [
      '--neko-wayland-self-ball-left',
      '--neko-wayland-self-ball-top',
      '--neko-wayland-self-ball-width',
      '--neko-wayland-self-ball-height',
      '--neko-wayland-self-ball-handle-left',
      '--neko-wayland-self-ball-handle-top'
    ];
    if (!anchor) {
      if (shell) shell.classList.remove('neko-e-wayland-self-ball-carrier');
      targets.forEach(function (target) {
        props.forEach(function (prop) { target.style.removeProperty(prop); });
      });
      return null;
    }
    var local = buildDesktopCompactWaylandSelfBallLocalRect(anchor, carrierBounds);
    if (!local) return null;
    var handleLeft = local.x + Math.round((local.width - BALL_SIZE) / 2);
    var handleTop = local.y + Math.round((local.height - BALL_SIZE) / 2);
    if (shell) shell.classList.add('neko-e-wayland-self-ball-carrier');
    targets.forEach(function (target) {
      target.style.setProperty('--neko-wayland-self-ball-left', local.x + 'px');
      target.style.setProperty('--neko-wayland-self-ball-top', local.y + 'px');
      target.style.setProperty('--neko-wayland-self-ball-width', local.width + 'px');
      target.style.setProperty('--neko-wayland-self-ball-height', local.height + 'px');
      target.style.setProperty('--neko-wayland-self-ball-handle-left', handleLeft + 'px');
      target.style.setProperty('--neko-wayland-self-ball-handle-top', handleTop + 'px');
    });
    return local;
  }

  function setDesktopCompactWaylandSelfBallAnchorBounds(anchorBounds, carrierBounds, reason) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland) return null;
    var anchor = normalizeDesktopCompactWaylandSelfBallAnchorBounds(anchorBounds);
    if (!anchor) return null;
    var carrier = getDesktopCompactWaylandSelfBallCarrierBounds(carrierBounds);
    desktopCompactWaylandSelfBallAnchorBounds = anchor;
    desktopCompactWaylandSelfBallCarrierBounds = carrier;
    window.__nekoDesktopCompactBallScreenRect = buildDesktopCompactWaylandSelfBallScreenRect(anchor);
    applyDesktopCompactWaylandSelfBallCssVars(anchor, carrier);
    sendDesktopCompactWaylandSelfBallShape(reason || 'self-ball-anchor', anchor, carrier);
    setDesktopCompactHistoryPointerPassthrough(false);
    ipcRenderer.send('set-ignore-mouse-events', false);
    return getDesktopCompactWaylandSelfBallAnchorBounds();
  }

  function clearDesktopCompactWaylandSelfBallAnchor() {
    desktopCompactWaylandSelfBallAnchorBounds = null;
    desktopCompactWaylandSelfBallCarrierBounds = null;
    applyDesktopCompactWaylandSelfBallCssVars(null);
    window.__nekoDesktopCompactBallScreenRect = null;
  }

  function sameWindowBounds(a, b) {
    var left = normalizeWindowBounds(a);
    var right = normalizeWindowBounds(b);
    var tolerance = 2;
    return !!(
      left
      && right
      && Math.abs(left.x - right.x) <= tolerance
      && Math.abs(left.y - right.y) <= tolerance
      && Math.abs(left.width - right.width) <= tolerance
      && Math.abs(left.height - right.height) <= tolerance
    );
  }

  function containsWindowBounds(outerBounds, innerBounds) {
    var outer = normalizeWindowBounds(outerBounds);
    var inner = normalizeWindowBounds(innerBounds);
    var tolerance = 2;
    if (!outer || !inner) return false;
    return (
      inner.x >= outer.x - tolerance
      && inner.y >= outer.y - tolerance
      && inner.x + inner.width <= outer.x + outer.width + tolerance
      && inner.y + inner.height <= outer.y + outer.height + tolerance
    );
  }

  function serializeWindowBoundsForSnapshot(bounds) {
    var normalized = normalizeWindowBounds(bounds);
    if (!normalized) return '';
    return [normalized.x, normalized.y, normalized.width, normalized.height].join(':');
  }

  function clearDesktopCompactBoundsVerification() {
    if (desktopCompactBoundsVerificationTimers.length) {
      desktopCompactBoundsVerificationTimers.forEach(function (timer) {
        window.clearTimeout(timer);
      });
      desktopCompactBoundsVerificationTimers = [];
    }
    desktopCompactBoundsVerificationSnapshot = '';
    desktopCompactBoundsVerificationCompletedSnapshot = '';
  }

  function removeDesktopCompactBoundsVerificationTimer(timer) {
    desktopCompactBoundsVerificationTimers = desktopCompactBoundsVerificationTimers.filter(function (item) {
      return item !== timer;
    });
  }

  function scheduleDesktopCompactBoundsVerification(targetBounds) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return;
    var targetSnapshot = serializeWindowBoundsForSnapshot(target);
    if (!targetSnapshot) return;
    if (desktopCompactBoundsVerificationCompletedSnapshot === targetSnapshot) return;
    if (desktopCompactBoundsVerificationSnapshot === targetSnapshot && desktopCompactBoundsVerificationTimers.length) return;
    clearDesktopCompactBoundsVerification();
    desktopCompactBoundsVerificationSnapshot = targetSnapshot;
    [64, 180, 420].forEach(function (delay) {
      var timer = window.setTimeout(function () {
        removeDesktopCompactBoundsVerificationTimer(timer);
        if (desktopCompactBoundsVerificationSnapshot !== targetSnapshot) return;
        if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') {
          clearDesktopCompactBoundsVerification();
          return;
        }
        W.getBounds().then(function (bounds) {
          if (desktopCompactBoundsVerificationSnapshot !== targetSnapshot) return;
          if (sameWindowBounds(bounds, target)) {
            desktopCompactPendingWindowBounds = null;
            clearDesktopCompactBoundsVerification();
            desktopCompactBoundsVerificationCompletedSnapshot = targetSnapshot;
            if (historyResizeIsolation && historyResizeIsolation.phase === 'settling') {
              desktopCompactWindowSnapshot = '';
              scheduleDesktopCompactRelayout();
            }
            return;
          }
          desktopCompactWindowSnapshot = '';
          desktopCompactPendingWindowBounds = target;
          if (!desktopCompactBoundsVerificationTimers.length) {
            desktopCompactBoundsVerificationCompletedSnapshot = targetSnapshot;
          }
          scheduleDesktopCompactRelayout();
        }).catch(function () {
          if (desktopCompactBoundsVerificationSnapshot !== targetSnapshot) return;
          desktopCompactWindowSnapshot = '';
          desktopCompactPendingWindowBounds = target;
          if (!desktopCompactBoundsVerificationTimers.length) {
            desktopCompactBoundsVerificationCompletedSnapshot = targetSnapshot;
          }
          scheduleDesktopCompactRelayout();
        });
      }, delay);
      desktopCompactBoundsVerificationTimers.push(timer);
    });
  }

  function waitForDesktopCompactBoundsBeforeReveal(targetBounds, options) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return Promise.resolve(false);
    var opts = options || {};
    var timeoutMs = Math.max(80, Math.round(Number(opts.timeoutMs) || 260));
    var intervalMs = Math.max(24, Math.round(Number(opts.intervalMs) || 40));
    var startedAt = Date.now();
    var targetSnapshot = serializeWindowBoundsForSnapshot(target);
    clearDesktopCompactBoundsVerification();

    return new Promise(function (resolve) {
      function finish(ok) {
        if (ok) {
          desktopCompactPendingWindowBounds = null;
          desktopCompactBoundsVerificationCompletedSnapshot = targetSnapshot;
        }
        resolve(!!ok);
      }

      function check() {
        if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') {
          finish(false);
          return;
        }
        W.getBounds().then(function (bounds) {
          if (sameWindowBounds(bounds, target)) {
            finish(true);
            return;
          }
          desktopCompactWindowSnapshot = '';
          desktopCompactPendingWindowBounds = target;
          W.setResizable(false);
          W.setBounds(target.x, target.y, target.width, target.height);
          if (Date.now() - startedAt >= timeoutMs) {
            finish(false);
            return;
          }
          window.setTimeout(check, intervalMs);
        }).catch(function () {
          desktopCompactWindowSnapshot = '';
          desktopCompactPendingWindowBounds = target;
          if (Date.now() - startedAt >= timeoutMs) {
            finish(false);
            return;
          }
          window.setTimeout(check, intervalMs);
        });
      }

      check();
    });
  }

  function getDesktopCompactRevealWindowBounds() {
    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    return layout && layout.windowBounds ? normalizeWindowBounds(layout.windowBounds) : null;
  }

  function waitForDesktopCompactRevealBoundsBeforeReveal(options) {
    var opts = options || {};
    var layoutTimeoutMs = Math.max(80, Math.round(Number(opts.layoutTimeoutMs) || 220));
    var intervalMs = Math.max(24, Math.round(Number(opts.intervalMs) || 40));
    var startedAt = Date.now();
    return new Promise(function (resolve) {
      function check() {
        if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') {
          resolve(false);
          return;
        }
        var target = getDesktopCompactRevealWindowBounds();
        if (target) {
          waitForDesktopCompactBoundsBeforeReveal(target, opts).then(resolve);
          return;
        }
        if (Date.now() - startedAt >= layoutTimeoutMs) {
          resolve(false);
          return;
        }
        window.setTimeout(check, intervalMs);
      }

      check();
    });
  }

  function makeScreenRect(left, top, width, height) {
    var l = Math.round(Number(left) || 0);
    var t = Math.round(Number(top) || 0);
    var w = Math.max(1, Math.round(Number(width) || 0));
    var h = Math.max(1, Math.round(Number(height) || 0));
    return {
      left: l,
      top: t,
      width: w,
      height: h,
      right: l + w,
      bottom: t + h,
      centerX: l + w / 2,
      centerY: t + h / 2
    };
  }

  function clampDesktopCompactSurfaceLiveDragRect(rect, area) {
    var normalized = normalizeRect(rect);
    var localDragWorkArea = normalizeWindowBounds(area);
    if (!normalized || !localDragWorkArea) return normalized;
    var inset = DESKTOP_COMPACT_NATIVE_PAD;
    var minLeft = localDragWorkArea.x + inset;
    var maxLeft = localDragWorkArea.x + Math.max(0, localDragWorkArea.width - normalized.width - inset);
    var minTop = localDragWorkArea.y + inset;
    var maxTop = localDragWorkArea.y + Math.max(0, localDragWorkArea.height - normalized.height - inset);
    var left = clamp(Math.round(normalized.left), minLeft, Math.max(minLeft, maxLeft));
    var top = clamp(Math.round(normalized.top), minTop, Math.max(minTop, maxTop));
    return makeScreenRect(left, top, normalized.width, normalized.height);
  }

  function unionScreenRects(rects) {
    var valid = (rects || []).filter(Boolean);
    if (!valid.length) return null;
    var left = valid.reduce(function (min, rect) { return Math.min(min, rect.left); }, valid[0].left);
    var top = valid.reduce(function (min, rect) { return Math.min(min, rect.top); }, valid[0].top);
    var right = valid.reduce(function (max, rect) { return Math.max(max, rect.right); }, valid[0].right);
    var bottom = valid.reduce(function (max, rect) { return Math.max(max, rect.bottom); }, valid[0].bottom);
    return makeScreenRect(left, top, right - left, bottom - top);
  }

  function getCurrentReactChatSurfaceMode() {
    var host = getReactChatHost();
    if (host && typeof host.getChatSurfaceMode === 'function') {
      try { return host.getChatSurfaceMode(); } catch (_) {}
    }
    var shell = document.getElementById('react-chat-window-shell');
    return shell ? shell.getAttribute('data-chat-surface-mode') || '' : '';
  }

  function getExpandedReactChatResizable() {
    return process.platform !== 'win32';
  }

  function setExpandedReactChatResizable() {
    if (process.platform === 'win32') {
      W.setResizable(false, { minWidth: EXPAND_MIN_W, minHeight: EXPAND_MIN_H });
      return;
    }
    W.setResizable(getExpandedReactChatResizable());
  }


  function setDesktopCompactAvatarBoundsSubscription(active) {
    var nextActive = !!active;
    if (desktopCompactAvatarBoundsSubscribed === nextActive) return;
    desktopCompactAvatarBoundsSubscribed = nextActive;
    ipcRenderer.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC_SUBSCRIPTION, { active: nextActive });
  }

  function applyDesktopCompactAvatarBoundsOnly(payload) {
    var avatar = normalizeRect(payload && payload.bounds);
    var bounds = getDesktopCompactRendererWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds);
    var localAvatar = avatar && bounds ? {
      left: avatar.left - bounds.x,
      top: avatar.top - bounds.y,
      right: avatar.right - bounds.x,
      bottom: avatar.bottom - bounds.y,
      width: avatar.width,
      height: avatar.height,
      centerX: avatar.centerX - bounds.x,
      centerY: avatar.centerY - bounds.y
    } : null;
    var snapshot = JSON.stringify(localAvatar || null);
    if (snapshot === desktopCompactAvatarBoundsOnlySnapshot) return;
    desktopCompactAvatarBoundsOnlySnapshot = snapshot;
    window.__nekoDesktopAvatarBounds = localAvatar;
    window.dispatchEvent(new CustomEvent('neko:desktop-avatar-bounds-change', { detail: localAvatar }));
  }

  function shouldApplyDesktopCompactAvatarBoundsOnly() {
    return !!(
      desktopCompactUseX11InputShape
      && desktopCompactWindowActive
      && desktopCompactLayout
      && desktopCompactLayout.windowBounds
      && (desktopCompactLayout.surfaceScreenRect || desktopCompactLayout.surface)
      && !desktopCompactSurfaceDragActive
      && !desktopCompactSurfaceResizeActive
      && !desktopCompactHistoryDragState
      && !desktopCompactHistoryDragRestoreActive
    );
  }

  var electronChatMinimizedStateTimer = 0;

  function normalizeElectronChatMinimizedScreenRect(rect) {
    var normalized = normalizeRect(rect);
    if (!normalized) return null;
    return {
      left: Math.round(normalized.left),
      top: Math.round(normalized.top),
      width: Math.round(normalized.width),
      height: Math.round(normalized.height),
      right: Math.round(normalized.left + normalized.width),
      bottom: Math.round(normalized.top + normalized.height),
      centerX: Math.round(normalized.left + normalized.width / 2),
      centerY: Math.round(normalized.top + normalized.height / 2)
    };
  }

  function getElectronChatMinimizedScreenRect() {
    return normalizeElectronChatMinimizedScreenRect(window.__nekoDesktopCompactBallScreenRect)
      || normalizeElectronChatMinimizedScreenRect(desktopCompactLayout && desktopCompactLayout.ballScreenRect);
  }

  function sendElectronChatMinimizedState(reason) {
    var surfaceMode = getCurrentReactChatSurfaceMode();
    var minimized = surfaceMode === 'minimized' || eMinimized;
    var screenRect = minimized ? getElectronChatMinimizedScreenRect() : null;

    function send(screenBounds) {
      ipcRenderer.send(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, {
        minimized: minimized,
        reason: reason || '',
        screenRect: minimized ? normalizeElectronChatMinimizedScreenRect(screenBounds) : null,
        timestamp: Date.now()
      });
    }

    if (screenRect || !minimized) {
      send(screenRect);
      return;
    }

    W.getBounds().then(function (bounds) {
      var normalized = normalizeWindowBounds(bounds);
      send(normalized ? {
        left: normalized.x,
        top: normalized.y,
        width: normalized.width,
        height: normalized.height
      } : null);
    }).catch(function () {
      send(null);
    });
  }

  function scheduleElectronChatMinimizedState(reason) {
    if (electronChatMinimizedStateTimer) {
      window.clearTimeout(electronChatMinimizedStateTimer);
    }
    electronChatMinimizedStateTimer = window.setTimeout(function () {
      electronChatMinimizedStateTimer = 0;
      sendElectronChatMinimizedState(reason);
    }, 0);
  }

  var selfWindowMinimizedBallStateTimer = 0;

  function scheduleSelfWindowMinimizedBallState(reason) {
    if (_useExternalMinimizedBallWindow || !eMinimized) return;
    if (selfWindowMinimizedBallStateTimer) return;
    selfWindowMinimizedBallStateTimer = window.setTimeout(function () {
      selfWindowMinimizedBallStateTimer = 0;
      scheduleElectronChatMinimizedState(reason || 'self-ball-drag-move');
    }, 48);
  }

  function scheduleSelfWindowMinimizedBallSettledState(reason) {
    if (_useExternalMinimizedBallWindow || !eMinimized) return;
    if (selfWindowMinimizedBallStateTimer) {
      window.clearTimeout(selfWindowMinimizedBallStateTimer);
      selfWindowMinimizedBallStateTimer = 0;
    }
    [0, 80, 260].forEach(function (delay) {
      window.setTimeout(function () {
        if (_useExternalMinimizedBallWindow || !eMinimized) return;
        scheduleElectronChatMinimizedState(reason || 'self-ball-drag-stop');
      }, delay);
    });
  }

  function getDesktopCompactWorkArea(workArea, avatarPayload) {
    var display = avatarPayload && avatarPayload.display;
    var avatarArea = (display && display.workArea) || (display && display.bounds) || null;
    // [multi-display-independence] compact 态对话框与角色模型跨屏独立：
    // - 拖动气泡跨屏期间，以“光标目标屏”工作区为基准，让 surface 能离开原屏
    //   （见 desktopCompactSurfaceDragWorkArea 说明），否则 clamp 会把它拉回。
    // - 平时以“对话框窗口自身当前所在屏”(workArea) 为基准，而非 avatar 所在屏：
    //   角色跨屏不会拖着对话框走，展开态拖到别的屏、折叠后也留在那块屏。
    // 仅当对话框自身 workArea 缺失时，才回退到 avatar 所在屏。
    if (desktopCompactSurfaceDragActive && desktopCompactSurfaceDragWorkArea) {
      return desktopCompactSurfaceDragWorkArea;
    }
    if (desktopCompactSurfaceDragSettledTarget && desktopCompactSurfaceDragSettledWorkArea) {
      return desktopCompactSurfaceDragSettledWorkArea;
    }
    return workArea || avatarArea || {};
  }

  function getDesktopCompactX11StableCarrierBounds(area) {
    if (!desktopCompactUseX11InputShape) return null;
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    if (areaWidth <= 0 || areaHeight <= 0) return null;
    return {
      x: areaX,
      y: areaY,
      width: areaWidth,
      height: areaHeight
    };
  }

  function getDesktopCompactWaylandStableCarrierBounds(area) {
    if (!_isNativeWayland || !desktopCompactHasSetShape) return null;
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    if (areaWidth <= 0 || areaHeight <= 0) return null;
    return {
      x: areaX,
      y: areaY,
      width: areaWidth,
      height: areaHeight
    };
  }

  function convertPageRectToScreenRect(rect, windowBounds) {
    var normalized = normalizeRect(rect);
    if (!normalized || !windowBounds) return null;
    return makeScreenRect(
      Math.round(Number(windowBounds.x) || 0) + normalized.left,
      Math.round(Number(windowBounds.y) || 0) + normalized.top,
      normalized.width,
      normalized.height
    );
  }

  function convertScreenRectToPageRect(rect, windowBounds) {
    var normalized = normalizeRect(rect);
    if (!normalized || !windowBounds) return null;
    return {
      left: normalized.left - windowBounds.x,
      top: normalized.top - windowBounds.y,
      width: normalized.width,
      height: normalized.height
    };
  }

  function getDesktopCompactLayoutSurfaceScreenRect(layout, windowBounds) {
    var explicitSurface = normalizeRect(layout && layout.surfaceScreenRect);
    if (explicitSurface) return explicitSurface;
    return convertPageRectToScreenRect(layout && layout.surface, windowBounds || (layout && layout.windowBounds));
  }

  function sameDesktopCompactWindowSize(a, b) {
    var left = normalizeWindowBounds(a);
    var right = normalizeWindowBounds(b);
    return !!(
      left
      && right
      && left.width === right.width
      && left.height === right.height
    );
  }

  function getDesktopCompactClientCoordinateWindowBounds(fallbackBounds) {
    var fallback = normalizeWindowBounds(fallbackBounds);
    var rendererBounds = getDesktopCompactRendererWindowBounds(fallback);
    if (!rendererBounds) return fallback;
    var candidates = [
      desktopCompactPendingWindowBounds,
      desktopCompactLayout && desktopCompactLayout.windowBounds,
      window.__nekoDesktopCompactLayout && window.__nekoDesktopCompactLayout.windowBounds,
      fallback
    ];
    for (var i = 0; i < candidates.length; i += 1) {
      var candidate = normalizeWindowBounds(candidates[i]);
      if (candidate && sameDesktopCompactWindowSize(candidate, rendererBounds)) {
        return {
          x: candidate.x,
          y: candidate.y,
          width: rendererBounds.width,
          height: rendererBounds.height
        };
      }
    }
    return rendererBounds;
  }

  window.__nekoGetAvatarToolClientScreenPoint = function(clientX, clientY) {
    var x = Number(clientX);
    var y = Number(clientY);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    var bounds = getDesktopCompactClientCoordinateWindowBounds(layout && layout.windowBounds);
    if (!bounds || !Number.isFinite(Number(bounds.x)) || !Number.isFinite(Number(bounds.y))) return null;
    return {
      screenX: Number(bounds.x) + x,
      screenY: Number(bounds.y) + y,
    };
  };

  window.__nekoGetAvatarToolScreenClientPoint = function(screenX, screenY) {
    var x = Number(screenX);
    var y = Number(screenY);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    var bounds = getDesktopCompactClientCoordinateWindowBounds(layout && layout.windowBounds);
    if (!bounds || !Number.isFinite(Number(bounds.x)) || !Number.isFinite(Number(bounds.y))) return null;
    return {
      clientX: x - Number(bounds.x),
      clientY: y - Number(bounds.y),
    };
  };

  function getDesktopCompactPageGeometry() {
    try {
      if (typeof window.__nekoGetCompactInteractionGeometry === 'function') {
        return window.__nekoGetCompactInteractionGeometry();
      }
    } catch (_) {}
    return window.__nekoCompactInteractionGeometry || null;
  }

  function getDesktopCompactGeometryScreenItems(windowBounds) {
    var geometry = getDesktopCompactPageGeometry();
    if (!geometry || !Array.isArray(geometry.surfaceItems)) return [];
    return desktopCompactLayoutTools.normalizeDesktopCompactSurfaceItems(geometry.surfaceItems, windowBounds);
  }

  function serializeDesktopCompactScreenRect(rect) {
    var normalized = normalizeRect(rect);
    if (!normalized) return '';
    return [
      Math.round(normalized.left),
      Math.round(normalized.top),
      Math.round(normalized.width),
      Math.round(normalized.height)
    ].join(',');
  }

  function serializeDesktopCompactScreenRects(rects) {
    return (Array.isArray(rects) ? rects : [])
      .map(serializeDesktopCompactScreenRect)
      .filter(Boolean)
      .sort()
      .join('|');
  }

  function getDesktopCompactStableExtraNativeRects(items) {
    return (Array.isArray(items) ? items : []).filter(function (item) {
      if (!item || !item.nativeScreenRect) return false;
      if (item.kind !== 'toolFan') return true;
      return desktopCompactLayoutTools.isDesktopCompactStableToolFanItem(item);
    }).map(function (item) {
      return item.nativeScreenRect;
    }).filter(Boolean);
  }

  function getDesktopCompactStableExtraHitRects(items) {
    return (Array.isArray(items) ? items : []).filter(function (item) {
      return desktopCompactLayoutTools.shouldIncludeDesktopCompactExtraHitItem(item);
    }).map(function (item) {
      return item.hitScreenRect;
    }).filter(Boolean);
  }

  function getDesktopCompactGeometrySummaryWindowBounds() {
    return getDesktopCompactRendererWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds)
      || normalizeWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds);
  }

  function isDesktopCompactGeometrySummaryTransientItem(item) {
    if (!item) return false;
    return item.kind === 'toolFan'
      || item.kind === 'history'
      || item.kind === 'musicPlayer'
      || item.kind === 'historyHandle';
  }

  function buildDesktopCompactInteractionGeometrySummary(geometry) {
    if (!geometry) return '';
    var windowBounds = getDesktopCompactGeometrySummaryWindowBounds();
    var measuredItems = desktopCompactLayoutTools.normalizeDesktopCompactSurfaceItems(geometry.surfaceItems || [], windowBounds || {});
    // Floating extras are still part of the real compact layout, but their
    // visibility/animation changes must not dirty this generic relayout
    // fingerprint. Otherwise opening the tool fan/history stack or fading the
    // music strip can trigger async native repositioning of the stable chat bar.
    var summaryItems = measuredItems.filter(function (item) {
      return !isDesktopCompactGeometrySummaryTransientItem(item);
    });
    var classified = desktopCompactLayoutTools.classifyDesktopCompactItems(summaryItems);
    var baseSurface = unionScreenRects(classified.baseAnchorVisualRects)
      || unionScreenRects(classified.baseAnchorNativeRects)
      || convertPageRectToScreenRect(geometry.baseSurfaceRect, windowBounds || {});
    var stableExtraNativeRects = getDesktopCompactStableExtraNativeRects(classified.extraItems);
    var stableExtraHitRects = getDesktopCompactStableExtraHitRects(classified.extraItems);
    var ballRect = convertPageRectToScreenRect(geometry.ballRect, windowBounds || {});
    var externalBall = normalizeRect(geometry.externalBall);
    return [
      'mode=' + (geometry.mode || ''),
      'state=' + (geometry.compactChatState || ''),
      'base=' + serializeDesktopCompactScreenRect(baseSurface),
      'baseHit=' + serializeDesktopCompactScreenRects(classified.baseHitRects),
      'extraNative=' + serializeDesktopCompactScreenRects(stableExtraNativeRects),
      'extraHit=' + serializeDesktopCompactScreenRects(stableExtraHitRects),
      'ball=' + serializeDesktopCompactScreenRect(ballRect),
      'externalBall=' + serializeDesktopCompactScreenRect(externalBall),
      'choice=' + (geometry.compactChoicePlacement || '')
    ].join(';');
  }

  function buildDesktopCompactTransientGeometrySummary(geometry, windowBounds) {
    if (!geometry) return '';
    var measuredItems = desktopCompactLayoutTools.normalizeDesktopCompactSurfaceItems(
      geometry.surfaceItems || [],
      windowBounds || {}
    );
    var transientItems = measuredItems.filter(function (item) {
      return isDesktopCompactGeometrySummaryTransientItem(item);
    });
    return [
      'transientNative=' + serializeDesktopCompactScreenRects(transientItems.map(function (item) {
        return item.nativeScreenRect;
      })),
      'transientHit=' + serializeDesktopCompactScreenRects(transientItems.map(function (item) {
        return item.hitScreenRect;
      })),
      'transientMeta=' + transientItems.map(function (item) {
        return [
          item.id || '',
          item.kind || '',
          item.hitRegionKind || '',
          item.interactive === false ? '0' : '1'
        ].join(',');
      }).sort().join('|')
    ].join(';');
  }

  function shouldScheduleDesktopCompactRelayoutForGeometryChange(detail) {
    if (desktopCompactSurfaceDragActive) {
      return false;
    }
    if (desktopCompactSurfaceResizeActive || desktopCompactHistoryDragState || isDesktopCompactHistoryResizeActive()) {
      return true;
    }
    var geometry = detail || getDesktopCompactPageGeometry();
    var windowBounds = getDesktopCompactGeometrySummaryWindowBounds();
    var nextTransientSummary = buildDesktopCompactTransientGeometrySummary(geometry, windowBounds);
    var nextSummary = buildDesktopCompactInteractionGeometrySummary(geometry);
    if (nextSummary === desktopCompactInteractionGeometrySummary && nextTransientSummary === desktopCompactTransientGeometrySummary) {
      return false;
    }
    desktopCompactInteractionGeometrySummary = nextSummary;
    desktopCompactTransientGeometrySummary = nextTransientSummary;
    return true;
  }

  function getDesktopCompactBaseSurfaceElement() {
    return document.querySelector(
      '[data-compact-geometry-owner="surface"][data-compact-geometry-item="input"], '
      + '[data-compact-geometry-owner="surface"][data-compact-geometry-item="capsule"]'
    );
  }

  function getDesktopCompactSurfaceShellElement() {
    return document.querySelector('.compact-chat-surface-shell');
  }

  function getDesktopCompactMeasuredSurfaceScreenRect(windowBounds) {
    var baseElement = getDesktopCompactSurfaceShellElement()
      || getDesktopCompactBaseSurfaceElement();
    if (!baseElement || typeof baseElement.getBoundingClientRect !== 'function') return null;
    return convertPageRectToScreenRect(baseElement.getBoundingClientRect(), windowBounds || {});
  }

  function isDesktopCompactHistoryDragPhase(phase) {
    return phase === 'dragging' || phase === 'returning' || phase === 'sending';
  }

  function normalizeDesktopCompactHistoryDragStatePayload(payload) {
    if (!payload || payload.active !== true || payload.needsDesktopBounds !== true) return null;
    var sessionId = typeof payload.sessionId === 'string' && payload.sessionId ? payload.sessionId : null;
    var phase = isDesktopCompactHistoryDragPhase(payload.phase) ? payload.phase : null;
    var dragType = payload.dragType === 'image' || payload.dragType === 'bubble' ? payload.dragType : null;
    var pointerClient = normalizeClientPoint(payload.pointerClient);
    var dragVisualRect = normalizeRect(payload.dragVisualRect);
    var dragHitRect = normalizeRect(payload.dragHitRect);
    if (!sessionId || !phase || !dragType || !pointerClient || !dragVisualRect || !dragHitRect) return null;
    var connectionVisualRect = payload.connectionVisualRect ? normalizeRect(payload.connectionVisualRect) : null;
    var timestamp = Number(payload.timestamp);
    if (!Number.isFinite(timestamp)) timestamp = Date.now();
    return {
      active: true,
      sessionId: sessionId,
      seq: Number.isFinite(Number(payload.seq)) ? Math.max(0, Math.round(Number(payload.seq))) : 0,
      phase: phase,
      dragType: dragType,
      pointerClient: pointerClient,
      dragVisualRect: dragVisualRect,
      connectionVisualRect: connectionVisualRect,
      dragHitRect: dragHitRect,
      overTarget: !!payload.overTarget,
      reducedMotion: !!payload.reducedMotion,
      timestamp: timestamp
    };
  }

  function serializeDesktopCompactHistoryDragState(state) {
    if (!state) return '';
    return JSON.stringify({
      sessionId: state.sessionId,
      seq: state.seq,
      phase: state.phase,
      dragType: state.dragType,
      dragVisualRect: state.dragVisualRect,
      connectionVisualRect: state.connectionVisualRect,
      dragHitRect: state.dragHitRect,
      overTarget: state.overTarget,
      reducedMotion: state.reducedMotion
    });
  }

  function isPointInsideDesktopCompactAvatarRange(bounds, point) {
    var avatar = normalizeRect(bounds);
    var cursor = normalizeClientPoint(point);
    if (!avatar || !cursor) return null;
    var pad = DESKTOP_COMPACT_HISTORY_AVATAR_RANGE_PADDING;
    if (
      cursor.clientX < avatar.left - pad
      || cursor.clientX > avatar.right + pad
      || cursor.clientY < avatar.top - pad
      || cursor.clientY > avatar.bottom + pad
    ) {
      return false;
    }
    var centerX = Number.isFinite(Number(avatar.centerX)) ? avatar.centerX : avatar.left + avatar.width / 2;
    var centerY = Number.isFinite(Number(avatar.centerY)) ? avatar.centerY : avatar.top + avatar.height / 2;
    var radiusX = avatar.width * 0.3 + pad;
    var radiusY = avatar.height * 0.475 + pad;
    if (radiusX <= 0 || radiusY <= 0) return false;
    var normalizedX = (cursor.clientX - centerX) / radiusX;
    var normalizedY = (cursor.clientY - centerY) / radiusY;
    return normalizedX * normalizedX + normalizedY * normalizedY <= 1;
  }

  function getDesktopCompactHistoryDragOverAvatar(state) {
    if (!state || !state.pointerClient) return null;
    return isPointInsideDesktopCompactAvatarRange(window.__nekoDesktopAvatarBounds, state.pointerClient);
  }

  function dispatchDesktopCompactHistoryDragDropTargetState(state) {
    var detail = state ? {
      active: true,
      sessionId: state.sessionId,
      seq: state.seq,
      desktopOverAvatar: state.desktopOverAvatar,
      timestamp: Date.now()
    } : {
      active: false,
      timestamp: Date.now()
    };
    try {
      window.dispatchEvent(new CustomEvent('neko:compact-history-drag-desktop-target-change', { detail: detail }));
    } catch (_) {}
  }

  function refreshDesktopCompactHistoryDragDropTargetState() {
    if (!desktopCompactHistoryDragState) return;
    var desktopOverAvatar = getDesktopCompactHistoryDragOverAvatar(desktopCompactHistoryDragState);
    if (desktopCompactHistoryDragState.desktopOverAvatar === desktopOverAvatar) return;
    desktopCompactHistoryDragState = Object.assign({}, desktopCompactHistoryDragState, {
      desktopOverAvatar: desktopOverAvatar
    });
    desktopCompactHistoryDragSnapshot = serializeDesktopCompactHistoryDragState(desktopCompactHistoryDragState);
    window.__nekoDesktopCompactHistoryDragState = desktopCompactHistoryDragState;
    dispatchDesktopCompactHistoryDragDropTargetState(desktopCompactHistoryDragState);
  }

  function unionDesktopCompactWindowBounds(a, b) {
    var first = normalizeWindowBounds(a);
    var second = normalizeWindowBounds(b);
    if (!first) return second;
    if (!second) return first;
    var left = Math.min(first.x, second.x);
    var top = Math.min(first.y, second.y);
    var right = Math.max(first.x + first.width, second.x + second.width);
    var bottom = Math.max(first.y + first.height, second.y + second.height);
    return {
      x: Math.round(left),
      y: Math.round(top),
      width: Math.max(1, Math.round(right - left)),
      height: Math.max(1, Math.round(bottom - top))
    };
  }

  function clampDesktopCompactWindowBoundsToArea(bounds, area) {
    var target = normalizeWindowBounds(bounds);
    var workArea = normalizeWindowBounds(area);
    if (!target || !workArea) return target;
    var left = Math.max(workArea.x, target.x);
    var top = Math.max(workArea.y, target.y);
    var right = Math.min(workArea.x + workArea.width, target.x + target.width);
    var bottom = Math.min(workArea.y + workArea.height, target.y + target.height);
    if (right <= left || bottom <= top) return workArea;
    return {
      x: Math.round(left),
      y: Math.round(top),
      width: Math.max(1, Math.round(right - left)),
      height: Math.max(1, Math.round(bottom - top))
    };
  }

  function isDesktopCompactScreenRectInsideWindowBounds(rect, bounds, inset) {
    var normalized = normalizeRect(rect);
    var windowBounds = normalizeWindowBounds(bounds);
    if (!normalized || !windowBounds) return false;
    var pad = Math.max(0, Math.round(Number(inset) || 0));
    return normalized.left >= windowBounds.x + pad
      && normalized.top >= windowBounds.y + pad
      && normalized.right <= windowBounds.x + windowBounds.width - pad
      && normalized.bottom <= windowBounds.y + windowBounds.height - pad;
  }

  function buildDesktopCompactHistoryDragCarrierWindowBounds(targetBounds, currentBounds, area) {
    var target = normalizeWindowBounds(targetBounds);
    if (!desktopCompactHistoryDragState || !target) return target;
    var current = normalizeWindowBounds(currentBounds);
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    var carrier = normalizeWindowBounds(desktopCompactHistoryDragCarrierBounds)
      || unionDesktopCompactWindowBounds(current, workAreaBounds)
      || current
      || target;
    carrier = unionDesktopCompactWindowBounds(carrier, current);
    carrier = unionDesktopCompactWindowBounds(carrier, target);
    carrier = clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
    desktopCompactHistoryDragCarrierBounds = carrier;
    return carrier;
  }

  function buildDesktopCompactHistoryDragRestoreWindowBounds(targetBounds) {
    var target = normalizeWindowBounds(targetBounds);
    return normalizeWindowBounds(desktopCompactHistoryDragCarrierBounds) || target;
  }

  function buildDesktopCompactSurfaceDragCarrierWindowBounds(targetBounds, currentBounds, area) {
    var target = normalizeWindowBounds(targetBounds);
    if (!_isNativeWayland || !(desktopCompactSurfaceDragPrimeActive || desktopCompactSurfaceDragActive) || !target) return target;
    var current = normalizeWindowBounds(currentBounds);
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    return normalizeWindowBounds(workAreaBounds)
      || unionDesktopCompactWindowBounds(current, target)
      || current
      || target;
  }

  function isDesktopCompactHistoryResizeActive() {
    if (historyResizeIsolation && historyResizeIsolation.phase === 'active') return true;
    if (desktopCompactHistoryResizeCommitPending) return false;
    if (desktopCompactHistoryResizeActive) return true;
    return !!document.querySelector(
      '.compact-export-history-anchor[data-compact-export-history-resizing="true"]'
    );
  }

  function isDesktopCompactHistoryResizeIsolating() {
    return !!(
      historyResizeIsolation
      && (historyResizeIsolation.phase === 'active' || historyResizeIsolation.phase === 'settling')
    );
  }

  function isDesktopCompactHistoryResizeSettling() {
    return !!(
      desktopCompactHistoryResizeCommitPending
      || (historyResizeIsolation && historyResizeIsolation.phase === 'settling')
    );
  }

  function clearDesktopCompactHistoryResizeIsolation() {
    if (historyResizeIsolation && historyResizeIsolation.watchdogTimer) {
      window.clearTimeout(historyResizeIsolation.watchdogTimer);
    }
    historyResizeIsolation = null;
  }

  function completeDesktopCompactHistoryResizeIsolation() {
    if (!historyResizeIsolation || historyResizeIsolation.phase !== 'settling') return;
    clearDesktopCompactHistoryResizeIsolation();
    desktopCompactHistoryResizeActive = false;
    desktopCompactHistoryResizeCommitPending = false;
    desktopCompactHistoryResizeKeepCarrierOnCommit = false;
    desktopCompactHistoryResizeCarrierBounds = null;
    if (desktopCompactHistoryResizeCommitTimer) {
      window.clearTimeout(desktopCompactHistoryResizeCommitTimer);
      desktopCompactHistoryResizeCommitTimer = 0;
    }
    desktopCompactWindowSnapshot = '';
    scheduleDesktopCompactRelayout();
  }

  function resetDesktopCompactHistoryResizeIsolation() {
    clearDesktopCompactHistoryResizeIsolation();
    desktopCompactHistoryResizeActive = false;
    desktopCompactHistoryResizeCommitPending = false;
    desktopCompactHistoryResizeKeepCarrierOnCommit = false;
    desktopCompactHistoryResizeCarrierBounds = null;
    if (desktopCompactHistoryResizeCommitTimer) {
      window.clearTimeout(desktopCompactHistoryResizeCommitTimer);
      desktopCompactHistoryResizeCommitTimer = 0;
    }
    desktopCompactWindowSnapshot = '';
    scheduleDesktopCompactRelayout();
  }

  function armDesktopCompactHistoryResizeIsolationWatchdog() {
    if (!historyResizeIsolation) return;
    if (historyResizeIsolation.watchdogTimer) {
      window.clearTimeout(historyResizeIsolation.watchdogTimer);
      historyResizeIsolation.watchdogTimer = 0;
    }
    historyResizeIsolation.watchdogTimer = window.setTimeout(function () {
      if (!historyResizeIsolation) return;
      var elapsed = Date.now() - historyResizeIsolation.startedAt;
      if (elapsed >= DESKTOP_COMPACT_HISTORY_RESIZE_HARD_WATCHDOG_MS) {
        resetDesktopCompactHistoryResizeIsolation();
        return;
      }
      desktopCompactWindowSnapshot = '';
      if (desktopCompactLayout) {
        applyDesktopCompactNativeRegion(desktopCompactLayout);
        syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
      }
      scheduleDesktopCompactRelayout();
      armDesktopCompactHistoryResizeIsolationWatchdog();
    }, DESKTOP_COMPACT_HISTORY_RESIZE_SOFT_STALE_MS);
  }

  function buildDesktopCompactHistoryResizeMaxEnvelopeWindowBounds(targetBounds, currentBounds, area) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return target;
    var current = normalizeWindowBounds(currentBounds);
    var carrier = unionDesktopCompactWindowBounds(current || target, target);
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    if (!workAreaBounds) return carrier;
    var left = Math.max(workAreaBounds.x, carrier.x);
    var right = Math.min(workAreaBounds.x + workAreaBounds.width, carrier.x + carrier.width);
    var bottom = Math.min(
      workAreaBounds.y + workAreaBounds.height,
      Math.max(carrier.y + carrier.height, target.y + target.height)
    );
    var envelopeTop = Math.min(carrier.y, target.y - DESKTOP_COMPACT_HISTORY_RESIZE_ENVELOPE_CHUNK_PX);
    envelopeTop = Math.max(workAreaBounds.y, envelopeTop);
    carrier = {
      x: left,
      y: envelopeTop,
      width: Math.max(1, right - left),
      height: Math.max(1, bottom - envelopeTop)
    };
    return clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
  }

  function startDesktopCompactHistoryResizeIsolation(startBounds, workArea) {
    clearDesktopCompactHistoryResizeIsolation();
    var mode = getDesktopCompactHistoryResizeIsolationMode();
    var frozenWindow = getDesktopCompactRendererWindowBounds(startBounds) || normalizeWindowBounds(startBounds);
    var frozenSurface = normalizeRect(desktopCompactLayout && desktopCompactLayout.surfaceScreenRect)
      || normalizeRect(desktopCompactLayout && desktopCompactLayout.surface);
    historyResizeIsolation = {
      phase: 'active',
      mode: mode,
      frozenScreenRect: frozenSurface,
      frozenWindowBounds: frozenWindow,
      maxEnvelopeBounds: null,
      conservativeHitRects: [],
      startedAt: Date.now(),
      watchdogTimer: 0
    };
    if (mode !== 'unsupported-wayland') {
      historyResizeIsolation.maxEnvelopeBounds = normalizeWindowBounds(desktopCompactHistoryResizePassiveCarrierBounds)
        || normalizeWindowBounds(desktopCompactHistoryResizeCarrierBounds)
        || null;
    }
    armDesktopCompactHistoryResizeIsolationWatchdog();
  }

  function settleDesktopCompactHistoryResizeIsolation() {
    if (!historyResizeIsolation) return;
    historyResizeIsolation.phase = 'settling';
    armDesktopCompactHistoryResizeIsolationWatchdog();
  }

  function buildDesktopCompactHistoryResizeConservativeHitRects(hitRects, resizeRects) {
    if (!isDesktopCompactHistoryResizeIsolating()) return [];
    var candidates = (Array.isArray(resizeRects) && resizeRects.length ? resizeRects : hitRects) || [];
    var conservative = candidates.map(function (rect) {
      return inflateDesktopCompactRect(rect, DESKTOP_COMPACT_HISTORY_RESIZE_ISOLATION_HIT_PAD);
    }).filter(Boolean);
    if (historyResizeIsolation) historyResizeIsolation.conservativeHitRects = conservative;
    return conservative;
  }

  function buildDesktopCompactHistoryResizeCarrierWindowBounds(targetBounds, currentBounds, area) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return target;
    if (historyResizeIsolation && historyResizeIsolation.mode === 'unsupported-wayland') {
      desktopCompactHistoryResizeCarrierBounds = null;
      return target;
    }
    var current = normalizeWindowBounds(currentBounds);
    if (historyResizeIsolation && historyResizeIsolation.phase === 'active' && current && containsWindowBounds(current, target)) {
      desktopCompactHistoryResizeCarrierBounds = current;
      return current;
    }
    if (historyResizeIsolation && historyResizeIsolation.phase === 'active') {
      var maxEnvelope = normalizeWindowBounds(historyResizeIsolation.maxEnvelopeBounds)
        || buildDesktopCompactHistoryResizeMaxEnvelopeWindowBounds(target, currentBounds, area);
      if (!containsWindowBounds(maxEnvelope, target)) {
        maxEnvelope = buildDesktopCompactHistoryResizeMaxEnvelopeWindowBounds(target, maxEnvelope, area);
      }
      var areaXMax = Math.round(Number(area && area.x) || 0);
      var areaYMax = Math.round(Number(area && area.y) || 0);
      var areaWidthMax = Math.round(Number(area && area.width) || 0);
      var areaHeightMax = Math.round(Number(area && area.height) || 0);
      var maxWorkAreaBounds = areaWidthMax > 0 && areaHeightMax > 0
        ? { x: areaXMax, y: areaYMax, width: areaWidthMax, height: areaHeightMax }
        : null;
      maxEnvelope = clampDesktopCompactWindowBoundsToArea(maxEnvelope, maxWorkAreaBounds);
      historyResizeIsolation.maxEnvelopeBounds = maxEnvelope;
      desktopCompactHistoryResizeCarrierBounds = maxEnvelope;
      return maxEnvelope;
    }
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    var lockedCarrier = normalizeWindowBounds(desktopCompactHistoryResizeCarrierBounds);
    if (lockedCarrier) {
      var expandedCarrier = unionDesktopCompactWindowBounds(lockedCarrier, target);
      expandedCarrier = clampDesktopCompactWindowBoundsToArea(expandedCarrier, workAreaBounds);
      desktopCompactHistoryResizeCarrierBounds = expandedCarrier;
      return expandedCarrier;
    }
    var carrier = current || target;
    carrier = unionDesktopCompactWindowBounds(carrier, target);
    carrier = clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
    desktopCompactHistoryResizeCarrierBounds = carrier;
    return carrier;
  }

  function buildDesktopCompactHistoryResizePassiveCarrierWindowBounds(targetBounds, currentBounds, area, resizeRects) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return target;
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    var passiveCarrier = normalizeWindowBounds(desktopCompactHistoryResizePassiveCarrierBounds);
    var passiveWorkArea = normalizeWindowBounds(desktopCompactHistoryResizePassiveCarrierWorkArea);
    var shouldTrackPassiveCarrier = !desktopCompactSurfaceDragActive;
    if (!Array.isArray(resizeRects) || !resizeRects.length || _isNativeWayland) {
      if (!shouldTrackPassiveCarrier || _isNativeWayland || (passiveCarrier && workAreaBounds && !sameWindowBounds(passiveWorkArea, workAreaBounds))) {
        passiveCarrier = null;
        desktopCompactHistoryResizePassiveCarrierBounds = null;
        desktopCompactHistoryResizePassiveCarrierWorkArea = null;
      }
      if (passiveCarrier) {
        // Do not shrink the carrier just because the resize hover band is gone.
        // Closing history removes that band before the animation finishes; if
        // the BrowserWindow follows it, the whole chat jumps. The cost is a
        // larger transparent carrier until the work area changes or the window
        // is rebuilt, while input regions still come from the real hit rects.
        var stableCarrier = unionDesktopCompactWindowBounds(passiveCarrier, target);
        stableCarrier = clampDesktopCompactWindowBoundsToArea(stableCarrier, workAreaBounds);
        desktopCompactHistoryResizePassiveCarrierBounds = stableCarrier;
        desktopCompactHistoryResizePassiveCarrierWorkArea = workAreaBounds;
        return stableCarrier;
      }
      return target;
    }
    var current = shouldTrackPassiveCarrier ? normalizeWindowBounds(currentBounds) : null;
    if (!shouldTrackPassiveCarrier || (passiveCarrier && workAreaBounds && !sameWindowBounds(passiveWorkArea, workAreaBounds))) {
      passiveCarrier = null;
      desktopCompactHistoryResizePassiveCarrierBounds = null;
      desktopCompactHistoryResizePassiveCarrierWorkArea = null;
    }
    var carrier = passiveCarrier || current || target;
    carrier = unionDesktopCompactWindowBounds(carrier, target);
    if (workAreaBounds) {
      var bottom = Math.min(
        workAreaBounds.y + workAreaBounds.height,
        Math.max(carrier.y + carrier.height, target.y + target.height)
      );
      // This intentionally spends vertical transparent space up to the workarea
      // top. It is the stable envelope history resize needs; making it hug the
      // panel more tightly caused the native window to resize mid-gesture.
      carrier = {
        x: Math.max(workAreaBounds.x, carrier.x),
        y: workAreaBounds.y,
        width: Math.max(1, Math.min(workAreaBounds.x + workAreaBounds.width, carrier.x + carrier.width) - Math.max(workAreaBounds.x, carrier.x)),
        height: Math.max(1, bottom - workAreaBounds.y)
      };
      carrier = clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
    }
    if (!shouldTrackPassiveCarrier) return carrier;
    desktopCompactHistoryResizePassiveCarrierBounds = carrier;
    desktopCompactHistoryResizePassiveCarrierWorkArea = workAreaBounds;
    return carrier;
  }

  function buildDesktopCompactSurfaceResizeCarrierWindowBounds(targetBounds, currentBounds, area) {
    var target = normalizeWindowBounds(targetBounds);
    if (!desktopCompactSurfaceResizeActive || !target) return target;
    var current = normalizeWindowBounds(currentBounds);
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    var carrier = normalizeWindowBounds(desktopCompactSurfaceResizeCarrierBounds)
      || normalizeWindowBounds(desktopCompactSurfaceResizePassiveCarrierBounds)
      || current
      || target;
    carrier = unionDesktopCompactWindowBounds(carrier, current);
    carrier = unionDesktopCompactWindowBounds(carrier, target);
    carrier = clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
    carrier = lockDesktopCompactSurfaceResizeCarrierVerticalBounds(carrier);
    desktopCompactSurfaceResizeCarrierBounds = carrier;
    return carrier;
  }

  function buildDesktopCompactSurfaceResizeRestoreWindowBounds(targetBounds) {
    var target = normalizeWindowBounds(targetBounds);
    return normalizeWindowBounds(desktopCompactSurfaceResizeCarrierBounds) || target;
  }

  function buildDesktopCompactSurfaceResizePassiveCarrierWindowBounds(targetBounds, currentBounds, area, surfaceRect) {
    var target = normalizeWindowBounds(targetBounds);
    if (!target) return target;
    var surface = normalizeRect(surfaceRect);
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var workAreaBounds = areaWidth > 0 && areaHeight > 0
      ? { x: areaX, y: areaY, width: areaWidth, height: areaHeight }
      : null;
    var passiveCarrier = normalizeWindowBounds(desktopCompactSurfaceResizePassiveCarrierBounds);
    var passiveWorkArea = normalizeWindowBounds(desktopCompactSurfaceResizePassiveCarrierWorkArea);
    var shouldTrackPassiveCarrier = !desktopCompactSurfaceDragActive;
    if (!shouldTrackPassiveCarrier || (passiveCarrier && workAreaBounds && !sameWindowBounds(passiveWorkArea, workAreaBounds))) {
      passiveCarrier = null;
      desktopCompactSurfaceResizePassiveCarrierBounds = null;
      desktopCompactSurfaceResizePassiveCarrierWorkArea = null;
    }
    if (!surface) return passiveCarrier || target;
    var resizeMinLeft = workAreaBounds
      ? areaX + DESKTOP_COMPACT_SURFACE_PAD_X
      : surface.right - DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH;
    var resizeMaxRight = workAreaBounds
      ? areaX + areaWidth - DESKTOP_COMPACT_SURFACE_PAD_X
      : surface.left + DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH;
    var resizeLeft = Math.min(
      surface.left,
      Math.max(resizeMinLeft, surface.right - DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH)
    );
    var resizeRight = Math.max(
      surface.right,
      Math.min(resizeMaxRight, surface.left + DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH)
    );
    var resizeReachRect = makeScreenRect(
      resizeLeft,
      surface.top,
      Math.max(surface.width, resizeRight - resizeLeft),
      surface.height
    );
    var resizeReachBounds = desktopCompactLayoutTools.buildDesktopCompactWindowBoundsForUnion(
      resizeReachRect,
      workAreaBounds,
      DESKTOP_COMPACT_NATIVE_PAD
    );
    var carrier = passiveCarrier || target;
    carrier = unionDesktopCompactWindowBounds(carrier, target);
    carrier = unionDesktopCompactWindowBounds(carrier, resizeReachBounds);
    carrier = clampDesktopCompactWindowBoundsToArea(carrier, workAreaBounds);
    carrier = lockDesktopCompactSurfaceResizeCarrierVerticalBounds(carrier);
    if (!shouldTrackPassiveCarrier) return carrier;
    desktopCompactSurfaceResizePassiveCarrierBounds = carrier;
    desktopCompactSurfaceResizePassiveCarrierWorkArea = workAreaBounds;
    return carrier;
  }

  function lockDesktopCompactSurfaceResizeCarrierVerticalBounds(bounds) {
    var target = normalizeWindowBounds(bounds);
    var start = normalizeWindowBounds(desktopCompactSurfaceResizeStartWindowBounds);
    if (!desktopCompactSurfaceResizeActive || !target || !start) return target;
    return {
      x: target.x,
      y: start.y,
      width: target.width,
      height: start.height
    };
  }


  function dispatchDesktopCompactHistoryDragRebase(fromBounds, toBounds) {
    var state = desktopCompactHistoryDragState;
    var from = normalizeWindowBounds(fromBounds);
    var to = normalizeWindowBounds(toBounds);
    if (!state || !from || !to) return;
    var deltaX = from.x - to.x;
    var deltaY = from.y - to.y;
    if (!deltaX && !deltaY) return;
    try {
      window.dispatchEvent(new CustomEvent('neko:compact-history-drag-rebase', {
        detail: {
          sessionId: state.sessionId,
          deltaX: deltaX,
          deltaY: deltaY,
          windowBounds: {
            x: to.x,
            y: to.y,
            width: to.width,
            height: to.height
          }
        }
      }));
    } catch (_) {}
  }

  function clearDesktopCompactHistoryDragClearTimer() {
    if (!desktopCompactHistoryDragClearTimer) return;
    window.clearTimeout(desktopCompactHistoryDragClearTimer);
    desktopCompactHistoryDragClearTimer = 0;
  }

  function clearDesktopCompactHistoryDragRestoreTimer() {
    if (!desktopCompactHistoryDragRestoreTimer) return;
    window.clearTimeout(desktopCompactHistoryDragRestoreTimer);
    desktopCompactHistoryDragRestoreTimer = 0;
  }

  function clearDesktopCompactHistoryDragRestoreState() {
    clearDesktopCompactHistoryDragRestoreTimer();
    desktopCompactHistoryDragRestoreActive = false;
  }

  function scheduleDesktopCompactHistoryDragRestore() {
    var carrier = normalizeWindowBounds(desktopCompactHistoryDragCarrierBounds);
    if (!carrier) return false;
    clearDesktopCompactHistoryDragRestoreTimer();
    desktopCompactHistoryDragRestoreActive = true;
    setDesktopCompactHistoryPointerPassthrough(true);
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    scheduleDesktopCompactRelayout();
    desktopCompactHistoryDragRestoreTimer = window.setTimeout(function () {
      desktopCompactHistoryDragRestoreTimer = 0;
      desktopCompactHistoryDragRestoreActive = false;
      syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
    }, DESKTOP_COMPACT_HISTORY_DRAG_RESTORE_MS);
    return true;
  }

  function clearDesktopCompactHistoryDragState() {
    clearDesktopCompactHistoryDragClearTimer();
    if (!desktopCompactHistoryDragState && !desktopCompactHistoryDragSnapshot) return false;
    var clearedState = desktopCompactHistoryDragState;
    desktopCompactHistoryDragState = null;
    desktopCompactHistoryDragSnapshot = '';
    window.__nekoDesktopCompactHistoryDragState = null;
    dispatchDesktopCompactHistoryDragDropTargetState(null);
    if (!clearedState || (clearedState.phase !== 'returning' && clearedState.phase !== 'sending')) {
      clearDesktopCompactHistoryDragRestoreState();
      desktopCompactHistoryDragCarrierBounds = null;
      setDesktopCompactHistoryPointerPassthrough(false);
    } else if (!scheduleDesktopCompactHistoryDragRestore()) {
      desktopCompactHistoryDragCarrierBounds = null;
      setDesktopCompactHistoryPointerPassthrough(false);
    }
    return true;
  }

  function scheduleDesktopCompactHistoryDragStaleClear() {
    clearDesktopCompactHistoryDragClearTimer();
    if (!desktopCompactHistoryDragState) return;
    var startedAt = Number(desktopCompactHistoryDragState.timestamp) || Date.now();
    var delay = Math.max(250, DESKTOP_COMPACT_HISTORY_DRAG_STALE_MS - (Date.now() - startedAt));
    desktopCompactHistoryDragClearTimer = window.setTimeout(function () {
      desktopCompactHistoryDragClearTimer = 0;
      if (!desktopCompactHistoryDragState) return;
      if (Date.now() - (Number(desktopCompactHistoryDragState.timestamp) || 0) < DESKTOP_COMPACT_HISTORY_DRAG_STALE_MS) {
        scheduleDesktopCompactHistoryDragStaleClear();
        return;
      }
      if (clearDesktopCompactHistoryDragState()) {
        desktopCompactWindowSnapshot = '';
        desktopCompactPendingWindowBounds = null;
        scheduleDesktopCompactRelayout();
      }
    }, delay);
  }

  function getDesktopCompactHistoryDragScreenRects(windowBounds) {
    var state = desktopCompactHistoryDragState;
    if (!state) return { nativeRects: [], hitRects: [] };
    if (Date.now() - (Number(state.timestamp) || 0) >= DESKTOP_COMPACT_HISTORY_DRAG_STALE_MS) {
      clearDesktopCompactHistoryDragState();
      return { nativeRects: [], hitRects: [] };
    }
    var dragVisualRect = convertPageRectToScreenRect(state.dragVisualRect, windowBounds);
    var connectionVisualRect = clampDesktopCompactHistoryConnectionScreenRect(
      convertPageRectToScreenRect(state.connectionVisualRect, windowBounds),
      dragVisualRect
    );
    var nativeRects = [
      dragVisualRect,
      connectionVisualRect
    ].filter(Boolean);
    var hitRects = [
      convertPageRectToScreenRect(state.dragHitRect, windowBounds)
    ].filter(Boolean);
    return { nativeRects: nativeRects, hitRects: hitRects };
  }

  function clampDesktopCompactHistoryConnectionScreenRect(connectionRect, dragVisualRect) {
    var connection = normalizeRect(connectionRect);
    var drag = normalizeRect(dragVisualRect);
    if (!connection || !drag) return null;
    var left = Math.max(connection.left, drag.left);
    var top = Math.max(connection.top, drag.top);
    var right = connection.right;
    var bottom = connection.bottom;
    if (right <= left || bottom <= top) return null;
    return makeScreenRect(left, top, right - left, bottom - top);
  }

  function applyDesktopCompactHistoryDragStatePayload(payload) {
    var nextState = normalizeDesktopCompactHistoryDragStatePayload(payload);
    if (
      nextState
      && (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden())
    ) {
      nextState = null;
    }
    if (nextState) {
      nextState.desktopOverAvatar = getDesktopCompactHistoryDragOverAvatar(nextState);
    }
    var nextSnapshot = serializeDesktopCompactHistoryDragState(nextState);
    if (!nextState) {
      if (clearDesktopCompactHistoryDragState()) {
        desktopCompactWindowSnapshot = '';
        desktopCompactPendingWindowBounds = null;
        scheduleDesktopCompactRelayout();
      }
      return;
    }
    if (nextSnapshot === desktopCompactHistoryDragSnapshot) {
      clearDesktopCompactHistoryDragRestoreState();
      desktopCompactHistoryDragState = nextState;
      window.__nekoDesktopCompactHistoryDragState = nextState;
      dispatchDesktopCompactHistoryDragDropTargetState(nextState);
      scheduleDesktopCompactHistoryDragStaleClear();
      return;
    }
    clearDesktopCompactHistoryDragRestoreState();
    desktopCompactHistoryDragState = nextState;
    desktopCompactHistoryDragSnapshot = nextSnapshot;
    window.__nekoDesktopCompactHistoryDragState = nextState;
    dispatchDesktopCompactHistoryDragDropTargetState(nextState);
    setDesktopCompactHistoryPointerPassthrough(false);
    scheduleDesktopCompactHistoryDragStaleClear();
    scheduleDesktopCompactRelayout();
  }

  function getDesktopCompactSurfaceHeight() {
    var baseElement = getDesktopCompactSurfaceShellElement()
      || getDesktopCompactBaseSurfaceElement();
    if (baseElement && typeof baseElement.getBoundingClientRect === 'function') {
      var rect = baseElement.getBoundingClientRect();
      if (rect && rect.height > 0) return rect.height;
    }
    return DESKTOP_COMPACT_SURFACE_DEFAULT_HEIGHT;
  }

  function hasDesktopCompactHistoryHandleItem(items) {
    return (Array.isArray(items) ? items : []).some(function (item) {
      return item && item.kind === 'historyHandle';
    });
  }

  function getDesktopCompactHistorySlotHeightFallback(surfaceRect, area) {
    var values = [];
    try {
      var computed = window.getComputedStyle(document.documentElement);
      values.push(Number.parseFloat(computed.getPropertyValue('--compact-history-slot-height')));
      values.push(Number.parseFloat(computed.getPropertyValue('--compact-export-history-region-height')));
    } catch (_) {}
    try {
      values.push(Number.parseFloat(window.localStorage.getItem('neko.reactChatWindow.compactHistorySlotHeight') || ''));
    } catch (_) {}
    var surfaceWidth = Number(surfaceRect && surfaceRect.width);
    var areaHeight = Number(area && area.height);
    values.push(Number.isFinite(surfaceWidth) && surfaceWidth > 0 ? surfaceWidth * 0.9 : NaN);
    values.push(Number.isFinite(areaHeight) && areaHeight > 0 ? areaHeight * 0.36 : NaN);
    for (var i = 0; i < values.length; i += 1) {
      var value = Math.round(Number(values[i]));
      if (Number.isFinite(value) && value >= 120) return value;
    }
    return 320;
  }

  function buildDesktopCompactHistoryPassiveReserveRect(surfaceRect, measuredItems, area) {
    var surface = normalizeRect(surfaceRect);
    if (!surface || !hasDesktopCompactHistoryHandleItem(measuredItems)) return null;
    var measuredHistory = unionScreenRects((Array.isArray(measuredItems) ? measuredItems : [])
      .filter(function (item) { return item && item.kind === 'history' && item.nativeScreenRect; })
      .map(function (item) { return item.nativeScreenRect; }));
    var reserve = desktopCompactLayoutTools.buildDesktopCompactHistoryPassiveReserveRect({
      surfaceRect: surface,
      measuredHistoryRect: measuredHistory,
      cachedReserveRect: desktopCompactHistoryPassiveReserveRect,
      fallbackHeight: getDesktopCompactHistorySlotHeightFallback(surface, area),
      defaultGap: 6,
      workArea: area
    });
    desktopCompactHistoryPassiveReserveRect = reserve;
    return reserve;
  }

  function normalizeDesktopCompactStoredSurfacePosition(raw, area, surfaceWidth, surfaceHeight) {
    if (!raw) return null;
    var left = Number(raw.left);
    var top = Number(raw.top);
    if (!Number.isFinite(left) || !Number.isFinite(top)) return null;
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var maxLeft = areaWidth > 0 ? areaX + areaWidth - surfaceWidth - DESKTOP_COMPACT_NATIVE_PAD : left;
    var maxTop = areaHeight > 0 ? areaY + areaHeight - surfaceHeight - DESKTOP_COMPACT_NATIVE_PAD : top;
    return makeScreenRect(
      clamp(Math.round(left), areaX + DESKTOP_COMPACT_NATIVE_PAD, maxLeft),
      clamp(Math.round(top), areaY + DESKTOP_COMPACT_NATIVE_PAD, maxTop),
      surfaceWidth,
      surfaceHeight
    );
  }

  function loadDesktopCompactSurfacePosition(area, surfaceWidth, surfaceHeight) {
    try {
      var raw = window.localStorage.getItem(DESKTOP_COMPACT_SURFACE_POSITION_KEY);
      if (!raw) return null;
      return normalizeDesktopCompactStoredSurfacePosition(
        JSON.parse(raw),
        area,
        surfaceWidth,
        surfaceHeight
      );
    } catch (_) {
      return null;
    }
  }

  function hasDesktopCompactSurfacePosition() {
    try {
      return !!window.localStorage.getItem(DESKTOP_COMPACT_SURFACE_POSITION_KEY);
    } catch (_) {
      return false;
    }
  }

  function saveDesktopCompactSurfacePosition(rect) {
    if (desktopCompactTutorialFixedLayoutActive) return;
    var normalized = normalizeRect(rect);
    if (!normalized) return;
    try {
      window.localStorage.setItem(DESKTOP_COMPACT_SURFACE_POSITION_KEY, JSON.stringify({
        left: Math.round(normalized.left),
        top: Math.round(normalized.top)
      }));
    } catch (_) {}
  }

  function saveDesktopCompactSurfaceWidth(width) {
    if (desktopCompactTutorialFixedLayoutActive) return;
    var nextWidth = Math.round(Number(width) || 0);
    if (!Number.isFinite(nextWidth) || nextWidth <= 0) return;
    try {
      var raw = window.localStorage.getItem(COMPACT_SURFACE_POSITION_STORAGE_KEY);
      var payload = raw ? JSON.parse(raw) : {};
      if (!payload || typeof payload !== 'object') payload = {};
      payload.width = nextWidth;
      window.localStorage.setItem(COMPACT_SURFACE_POSITION_STORAGE_KEY, JSON.stringify(payload));
    } catch (_) {}
  }

  // saveDesktopCompactSurfaceWidth 写进 COMPACT_SURFACE_POSITION_STORAGE_KEY 的用户拉伸宽度，
  // 在 #208 之前从来没人读回。重启/刷新后第一帧 surface 走 DOM 默认 CSS 宽，
  // loadDesktopCompactStoredSurfaceForAnchor 只用「量到的默认宽」+ 存的 {left,top} 拼 rect，
  // 宽度因而每次重启都复位。这里把持久化宽度读回（缺失/损坏时返回 null），
  // 让冷启动恢复路径优先用它。
  function loadDesktopCompactSurfaceWidth() {
    try {
      var raw = window.localStorage.getItem(COMPACT_SURFACE_POSITION_STORAGE_KEY);
      if (!raw) return null;
      var payload = JSON.parse(raw);
      var width = Math.round(Number(payload && payload.width) || 0);
      if (!Number.isFinite(width) || width <= 0) return null;
      return width;
    } catch (_) {
      return null;
    }
  }

  // 持久化宽度可能来自更宽的显示器/更早的会话，重启时夹到当前工作区与缩放上限内，
  // 既保住用户拉过的宽度，又不让 surface 溢出当前屏。下限对齐渲染器的拖拽下限
  // DESKTOP_COMPACT_SURFACE_RESIZE_MIN_WIDTH（180），与用户实际能拖到的最窄宽度一致。
  function clampDesktopCompactSurfaceWidth(width, area) {
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var ceiling = Math.min(
      DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH,
      (areaWidth || DESKTOP_COMPACT_FALLBACK_WORKAREA_WIDTH) - DESKTOP_COMPACT_SURFACE_PAD_X * 2
    );
    return clamp(
      Math.round(Number(width) || 0),
      DESKTOP_COMPACT_SURFACE_RESIZE_MIN_WIDTH,
      Math.max(DESKTOP_COMPACT_SURFACE_RESIZE_MIN_WIDTH, ceiling)
    );
  }

  function getDesktopCompactFallbackSurfaceWidth(area) {
    var areaWidth = Math.round(Number(area && area.width) || 0);
    return Math.min(
      DESKTOP_COMPACT_SURFACE_MAX_WIDTH,
      Math.max(280, (areaWidth || DESKTOP_COMPACT_FALLBACK_WORKAREA_WIDTH) - DESKTOP_COMPACT_SURFACE_PAD_X * 2)
    );
  }

  function loadDesktopCompactStoredSurfaceForAnchor(area, anchorSurface) {
    var anchor = normalizeRect(anchorSurface);
    // 优先用持久化宽度：冷启动时 anchor 是 DOM 默认宽，用它会把用户拉过的宽度复位。
    // 持久化宽度与 {left,top} 总是成对保存（拖拽/缩放结束），有存的宽就一定有存的位，
    // 不存在「读到宽却没位」导致拼不出 rect 的情况；缺失时回退原 anchor/fallback。
    var storedWidth = loadDesktopCompactSurfaceWidth();
    var surfaceWidth = storedWidth
      ? clampDesktopCompactSurfaceWidth(storedWidth, area)
      : (anchor ? anchor.width : getDesktopCompactFallbackSurfaceWidth(area));
    var surfaceHeight = anchor ? anchor.height : getDesktopCompactSurfaceHeight();
    return loadDesktopCompactSurfacePosition(area, surfaceWidth, surfaceHeight);
  }

  function buildDefaultDesktopCompactSurfaceScreenRect(area, anchorSurface, fallbackSurface) {
    if (hasDesktopCompactSurfacePosition()) return null;
    var anchor = normalizeRect(anchorSurface) || normalizeRect(fallbackSurface);
    if (!anchor) return null;
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var surfaceWidth = Math.round(Number(anchor.width) || 0);
    var surfaceHeight = Math.round(Number(anchor.height) || 0);
    if (surfaceWidth <= 0 || surfaceHeight <= 0) return null;
    var top = areaHeight > 0
      ? areaY + areaHeight - surfaceHeight - DESKTOP_COMPACT_NATIVE_PAD
      : anchor.top;
    return normalizeDesktopCompactStoredSurfacePosition(
      { left: anchor.left, top: top },
      area,
      surfaceWidth,
      surfaceHeight
    );
  }

  function buildFallbackSurfaceScreenRect(area, avatarPayload) {
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var surfaceWidth = getDesktopCompactFallbackSurfaceWidth(area);
    var surfaceHeight = getDesktopCompactSurfaceHeight();
    var avatar = normalizeRect(avatarPayload && avatarPayload.bounds);
    var left;
    var top;
    if (avatar) {
      left = avatar.left + avatar.width / 2 - surfaceWidth / 2;
      top = avatar.top + avatar.height * DESKTOP_COMPACT_SURFACE_AVATAR_VERTICAL_RATIO - surfaceHeight / 2;
    } else {
      // 没有模型 bounds 时的降级兜底（设计文档：「没有模型 bounds 时才使用 fallback，并视为降级路径」）。
      // 仅在 stored + measured surface 都缺失时才会走到——典型是 exit retention 强制折叠后展开，
      // 而此刻 pet 已停止同步 avatar bounds。把默认 compact surface 放在工作区水平居中、垂直偏下，
      // 保证还原始终有一个非空可见的 surface union，不会因 null-union 抛错回退 doExpand 还原旧大窗。
      if (areaWidth <= 0 || areaHeight <= 0) return null;
      left = areaX + (areaWidth - surfaceWidth) / 2;
      top = areaY + areaHeight * DESKTOP_COMPACT_SURFACE_AVATAR_VERTICAL_RATIO - surfaceHeight / 2;
    }
    var maxLeft = areaWidth > 0 ? areaX + areaWidth - surfaceWidth - DESKTOP_COMPACT_SURFACE_PAD_X : left;
    var maxTop = areaHeight > 0 ? areaY + areaHeight - surfaceHeight - DESKTOP_COMPACT_SURFACE_PAD_X : top;
    return makeScreenRect(
      clamp(Math.round(left), areaX + DESKTOP_COMPACT_SURFACE_PAD_X, maxLeft),
      clamp(Math.round(top), areaY + DESKTOP_COMPACT_SURFACE_PAD_X, maxTop),
      surfaceWidth,
      surfaceHeight
    );
  }

  function captureDesktopCompactTutorialFixedSurfaceSize(anchorSurface) {
    var anchor = normalizeRect(anchorSurface);
    var height = anchor ? anchor.height : getDesktopCompactSurfaceHeight();
    desktopCompactTutorialFixedSurfaceSize = {
      width: DESKTOP_COMPACT_TUTORIAL_FIXED_SURFACE_WIDTH,
      height: Math.max(1, Math.round(Number(height) || 1))
    };
    return desktopCompactTutorialFixedSurfaceSize;
  }

  function buildDesktopCompactTutorialFixedSurface(area, anchorSurface) {
    var anchor = normalizeRect(anchorSurface);
    var fixedSize = desktopCompactTutorialFixedSurfaceSize
      || captureDesktopCompactTutorialFixedSurfaceSize(anchor);
    return desktopCompactLayoutTools.buildDesktopCompactTutorialFixedSurfaceRect({
      workArea: area,
      anchorSurface: anchor,
      surfaceWidth: fixedSize && fixedSize.width,
      surfaceHeight: fixedSize && fixedSize.height,
      fallbackWidth: getDesktopCompactFallbackSurfaceWidth(area)
    });
  }

  function getDesktopCompactMeasuredBaseSurfaceScreenRect(bounds) {
    var measuredSurface = getDesktopCompactMeasuredSurfaceScreenRect(bounds || {});
    if (measuredSurface) return measuredSurface;
    var measuredItems = getDesktopCompactGeometryScreenItems(bounds || {});
    var classifiedItems = desktopCompactLayoutTools.classifyDesktopCompactItems(measuredItems);
    return unionScreenRects(classifiedItems.baseAnchorVisualRects)
      || unionScreenRects(classifiedItems.baseAnchorNativeRects);
  }

  function buildDesktopCompactHistoryResizeHoverScreenRects(items) {
    return desktopCompactLayoutTools.buildDesktopCompactHistoryResizeHoverRects(items, {
      padX: DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_X,
      padTop: DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_TOP,
      padBottom: DESKTOP_COMPACT_HISTORY_RESIZE_HOVER_PAD_BOTTOM
    });
  }

  function buildDesktopCompactBallScreenRect(_avatarPayload, _area) {
    // [compact-ball-removed] 总开关：compact 态不再有模型旁的悬浮最小化球（对齐 N.E.K.O#1595：
    // web 侧已把该球 display:none、geometry.ballRect 恒为 null）。桌面壳的球是一套独立的原生实现：
    // 不读 renderer 的 ballRect，而是据 avatarPayload 自行算位置 → 开 compactChatBallWindow 原生窗口，
    // 所以 web 侧的删除影响不到这里。让 ballScreenRect 恒为 null，使 showDesktopCompactBallWindow 走
    // HIDE 分支、永不发 SHOW，原生球窗口不再创建（已存在的会被 HIDE 销毁）。
    // getDesktopCompactBallCollapseTarget 随之返回 null，最小化收起动画落点回退到 W.collapse 默认值。
    // compact 态的最小化入口呈现方式留待后续单独设计。
    //
    // ===== 后续整套清理清单（grep `[compact-ball-removed]` 可定位全部）=====
    // 当确定不再需要原生球时，连同调用点一并删除以下死代码：
    //   preload-chat-react.js：本函数、showDesktopCompactBallWindow / raiseDesktopCompactBallWindow /
    //     hideDesktopCompactBallWindow / getDesktopCompactBallCollapseTarget、变量
    //     desktopCompactBallWindowSnapshot，以及它们的调用点（grep 函数名）。
    //   window-manager.js：compactChatBallWindow 引用、normalizeCompactChatBallBounds /
    //     buildCompactChatBallDataUrl / showCompactChatBallWindow / raiseCompactChatBallWindow /
    //     hideCompactChatBallWindow、reactChatWindow focus/closed 与 mini-game demote 里的 raise/hide 调用、
    //     destroyAllWindows / getWindows 里的登记、module.exports 三个导出。
    //   main.js：COMPACT_CHAT_BALL_CHANNELS 的 SHOW/HIDE/RAISE/CLICK 四个 ipcMain.on 处理器、
    //     neko:hide-react-chat 里的 hideCompactChatBallWindow 调用、require 解构里的 COMPACT_CHAT_BALL_CHANNELS。
    //   ipc-channels.js：COMPACT_CHAT_BALL_CHANNELS 定义与导出。
    //   preload-compact-chat-ball.js：整个文件（连同 window-manager 里对它的 getPreloadPath 引用）。
    return null;
  }

  function buildDesktopCompactWindowLayout(bounds, workArea, avatarPayload, options) {
    var opts = options || {};
    var area = getDesktopCompactWorkArea(workArea, avatarPayload);
    var currentWindowBounds = bounds || {};
    var measuredItems = opts.storedSurfaceOnly ? [] : getDesktopCompactGeometryScreenItems(currentWindowBounds);
    var classifiedItems = desktopCompactLayoutTools.classifyDesktopCompactItems(measuredItems);
    var baseRects = classifiedItems.baseAnchorNativeRects;
    var settledSurface = normalizeRect(desktopCompactSurfaceDragSettledTarget);
    var activeSurface = desktopCompactSurfaceResizeActive
      ? normalizeRect(desktopCompactSurfaceResizeTarget)
      : (desktopCompactSurfaceDragActive ? normalizeRect(desktopCompactSurfaceDragTarget) : settledSurface);
    var measuredSurface = opts.storedSurfaceOnly ? null : getDesktopCompactMeasuredSurfaceScreenRect(currentWindowBounds);
    var actualSurfaceUnion = measuredSurface || unionScreenRects(baseRects);
    // storedSurfaceOnly（毛线球直接恢复）没有 DOM 可量，actualSurfaceUnion 为 null，
    // loadDesktopCompactStoredSurfaceForAnchor 会退回 getDesktopCompactFallbackSurfaceWidth
    // 默认宽 → 每次点球展开都把用户拉过的宽度复位。opts.storedSurfaceSize 传入折叠瞬间抓到的
    // 真实 surface 宽高（_lastLayoutForRestore），用它把刚存的 {left,top} 还原成完整 rect，
    // 保住拉伸宽度（缺失时仍退回原 anchor/fallback 逻辑）。
    var storedSurfaceSizeHint = opts.storedSurfaceSize
      && Number(opts.storedSurfaceSize.width) > 0
      && Number(opts.storedSurfaceSize.height) > 0
      ? opts.storedSurfaceSize
      : null;
    var persistedSurface = (desktopCompactSurfaceResizeActive || desktopCompactSurfaceDragActive || settledSurface)
      ? activeSurface
      : (storedSurfaceSizeHint
          ? (loadDesktopCompactSurfacePosition(
              area,
              Math.round(Number(storedSurfaceSizeHint.width)),
              Math.round(Number(storedSurfaceSizeHint.height))
            ) || loadDesktopCompactStoredSurfaceForAnchor(area, actualSurfaceUnion))
          : loadDesktopCompactStoredSurfaceForAnchor(area, actualSurfaceUnion));
    var fallbackSurface = buildFallbackSurfaceScreenRect(area, avatarPayload);
    var tutorialFixedSurface = desktopCompactTutorialFixedLayoutActive
      && !desktopCompactSurfaceResizeActive
      && !desktopCompactSurfaceDragActive
      ? buildDesktopCompactTutorialFixedSurface(area, actualSurfaceUnion || persistedSurface)
      : null;
    var defaultSurface = (!tutorialFixedSurface
      && !persistedSurface
      && !desktopCompactSurfaceResizeActive
      && !desktopCompactSurfaceDragActive)
      ? buildDefaultDesktopCompactSurfaceScreenRect(area, actualSurfaceUnion, fallbackSurface)
      : null;
    var fixedMeasuredItems = tutorialFixedSurface
      ? desktopCompactLayoutTools.replaceDesktopCompactMeasuredBaseItemsWithSurface(measuredItems, tutorialFixedSurface, actualSurfaceUnion)
      : measuredItems;
    var fixedMeasuredSurface = tutorialFixedSurface ? tutorialFixedSurface : measuredSurface;
    var storedSurface = tutorialFixedSurface || persistedSurface || defaultSurface;
    var measuredOrStoredSurface = fixedMeasuredSurface
      || actualSurfaceUnion
      || storedSurface
      || fallbackSurface;
    var historyPassiveReserveRect = buildDesktopCompactHistoryPassiveReserveRect(
      measuredOrStoredSurface,
      fixedMeasuredItems,
      area
    );
    var layoutRects = desktopCompactLayoutTools.buildDesktopCompactLayoutRects({
      measuredItems: fixedMeasuredItems,
      measuredSurface: fixedMeasuredSurface,
      storedSurface: storedSurface,
      fallbackSurface: fallbackSurface,
      historyPassiveReserveRect: historyPassiveReserveRect,
      workArea: area,
      pad: DESKTOP_COMPACT_NATIVE_PAD,
      compactChoicePlacement: desktopCompactLayout && desktopCompactLayout.compactChoicePlacement
    });
    var surfaceUnion = layoutRects.surfaceUnion;
    var nativeRects = layoutRects.nativeRects;
    var hitRects = layoutRects.hitRects;
    var historyPassthroughRects = layoutRects.historyPassthroughRects || [];
    var historyResizeHoverRects = buildDesktopCompactHistoryResizeHoverScreenRects(layoutRects.extraItems);
    // History drag payload rects are renderer client-space. During left/top
    // expansion the pending native target can move before the renderer origin
    // has actually rebased, so convert drag rects with the live renderer bounds.
    var historyDragWindowBounds = desktopCompactHistoryDragState
      ? getDesktopCompactRendererWindowBounds(currentWindowBounds)
      : currentWindowBounds;
    var historyDragRects = getDesktopCompactHistoryDragScreenRects(historyDragWindowBounds);
    var includeHistoryDragRectsInNativeBounds = !(
      desktopCompactHistoryDragState
      && historyDragRects.nativeRects.length
      && historyDragRects.nativeRects.concat(historyDragRects.hitRects).every(function (rect) {
        return isDesktopCompactScreenRectInsideWindowBounds(rect, currentWindowBounds, DESKTOP_COMPACT_NATIVE_PAD);
      })
    );
    if (historyDragRects.nativeRects.length) {
      if (includeHistoryDragRectsInNativeBounds) {
        nativeRects = nativeRects.concat(historyDragRects.nativeRects);
      }
    }
    if (historyDragRects.hitRects.length) {
      hitRects = hitRects.concat(historyDragRects.hitRects);
    }
    if (isDesktopCompactHistoryResizeIsolating()) {
      var conservativeHistoryResizeHitRects = buildDesktopCompactHistoryResizeConservativeHitRects(
        hitRects,
        historyResizeHoverRects
      );
      if (conservativeHistoryResizeHitRects.length) {
        hitRects = hitRects.concat(conservativeHistoryResizeHitRects);
      }
    }
    var compactChoicePlacement = layoutRects.compactChoicePlacement;
    var pad = DESKTOP_COMPACT_NATIVE_PAD;
    var areaX = Math.round(Number(area && area.x) || 0);
    var areaY = Math.round(Number(area && area.y) || 0);
    var areaWidth = Math.round(Number(area && area.width) || 0);
    var areaHeight = Math.round(Number(area && area.height) || 0);
    var resizeReserveRect = null;
    if (
      desktopCompactSurfaceResizeActive
      && desktopCompactSurfaceResizeSide === 'left'
      && activeSurface
      && surfaceUnion
    ) {
      var resizeStartSurface = normalizeRect(desktopCompactSurfaceResizeStartTarget) || activeSurface;
      if (activeSurface.width <= resizeStartSurface.width) {
        resizeReserveRect = resizeStartSurface;
      } else {
        var resizeMaxLeft = areaWidth > 0
          ? areaX + DESKTOP_COMPACT_SURFACE_PAD_X
          : activeSurface.right - DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH;
        var resizeReserveWidth = Math.max(
          surfaceUnion.width,
          Math.min(
            DESKTOP_COMPACT_SURFACE_RESIZE_MAX_WIDTH,
            Math.max(surfaceUnion.width, activeSurface.right - resizeMaxLeft)
          )
        );
        resizeReserveRect = makeScreenRect(
          activeSurface.right - resizeReserveWidth,
          surfaceUnion.top,
          resizeReserveWidth,
          surfaceUnion.height
        );
      }
    }
    var carrierHitRects = desktopCompactLayoutTools.buildDesktopCompactCarrierHitRects(
      hitRects,
      layoutRects.extraItems
    );
    var carrierReserveRects = layoutRects.carrierReserveRects || [];
    var windowUnionRects = [surfaceUnion].concat(nativeRects).concat(carrierHitRects).concat(carrierReserveRects);
    if (layoutRects.toolFanReserveRect) windowUnionRects.push(layoutRects.toolFanReserveRect);
    if (resizeReserveRect) windowUnionRects.push(resizeReserveRect);
    var union = unionScreenRects(windowUnionRects) || surfaceUnion;
    // 防御：union 经上方 fallbackSurface 兜底后理论恒非空；万一工作区也缺失导致 fallback 仍空，
    // 这里再兜一个工作区派生的可见矩形，绝不让 union 为 null 触发下面 union.left 的 TypeError
    // （历史上该崩溃会被 restoreCompactDesktopFromMinimized 的 catch 吞掉、回退 doExpand 还原旧大窗，
    // 表现为折叠态展开后对话框消失 / 变 full）。
    if (!union) {
      union = makeScreenRect(
        areaX + DESKTOP_COMPACT_SURFACE_PAD_X,
        areaY + DESKTOP_COMPACT_SURFACE_PAD_X,
        getDesktopCompactFallbackSurfaceWidth(area),
        getDesktopCompactSurfaceHeight()
      );
    }
    if (!surfaceUnion) surfaceUnion = union;
    // 只有首帧尚未收到 renderer 几何时，才把可见 surface 当作临时命中区。
    // 一旦 renderer 已上报 visual-only shell/input 与真实 inputControl，就不能再把透明外壳
    // 兜底成 native/hit，否则展开聊天框会在角色附近形成看不见的鼠标拦截区。
    if (!layoutRects.hasMeasuredItems) {
      if (!nativeRects.length) nativeRects = [union];
      if (!hitRects.length) hitRects = [union];
    }
    var windowBounds = desktopCompactLayoutTools.buildDesktopCompactWindowBoundsForUnion(union, area, pad);
    var x = windowBounds ? windowBounds.x : union.left - pad;
    var y = windowBounds ? windowBounds.y : union.top - pad;
    var width = windowBounds ? windowBounds.width : union.width + pad * 2;
    var height = windowBounds ? windowBounds.height : union.height + pad * 2;
    if ((desktopCompactSurfaceResizeActive || desktopCompactSurfaceDragActive) && !activeSurface) {
      var currentY = Number(currentWindowBounds && currentWindowBounds.y);
      var currentHeight = Number(currentWindowBounds && currentWindowBounds.height);
      if (Number.isFinite(currentY)) y = currentY;
      if (Number.isFinite(currentHeight) && currentHeight > 0) {
        height = Math.max(height, currentHeight);
      }
    }
    // The base compact surface is already clamped before native bounds are
    // unioned. History, preview, tool fan, and choices are extra islands; they
    // may enlarge the carrier, but workArea clipping must not push the
    // saved/base surface.
    windowBounds = {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(1, Math.round(width)),
      height: Math.max(1, Math.round(height))
    };
    var surfaceResizeWindowBounds = windowBounds;
    var waylandStableCarrierBounds = getDesktopCompactWaylandStableCarrierBounds(area);
    if (desktopCompactHistoryDragState) {
      windowBounds = buildDesktopCompactHistoryDragCarrierWindowBounds(windowBounds, currentWindowBounds, area);
    } else if (desktopCompactSurfaceResizeActive) {
      windowBounds = buildDesktopCompactSurfaceResizeCarrierWindowBounds(windowBounds, currentWindowBounds, area);
    } else if (isDesktopCompactHistoryResizeActive()) {
      windowBounds = buildDesktopCompactHistoryResizeCarrierWindowBounds(windowBounds, currentWindowBounds, area);
    } else if (_isNativeWayland && (desktopCompactSurfaceDragPrimeActive || desktopCompactSurfaceDragActive)) {
      windowBounds = buildDesktopCompactSurfaceDragCarrierWindowBounds(windowBounds, currentWindowBounds, area);
    } else if (desktopCompactHistoryDragCarrierBounds) {
      windowBounds = buildDesktopCompactHistoryDragRestoreWindowBounds(windowBounds);
    } else if (desktopCompactSurfaceResizeCarrierBounds) {
      windowBounds = buildDesktopCompactSurfaceResizeRestoreWindowBounds(windowBounds);
    } else {
      desktopCompactHistoryResizeCarrierBounds = null;
      var historyResizePassiveWindowBounds = buildDesktopCompactHistoryResizePassiveCarrierWindowBounds(
        windowBounds,
        currentWindowBounds,
        area,
        historyResizeHoverRects
      );
      var surfaceResizePassiveWindowBounds = buildDesktopCompactSurfaceResizePassiveCarrierWindowBounds(
        surfaceResizeWindowBounds,
        currentWindowBounds,
        area,
        surfaceUnion
      );
      windowBounds = unionDesktopCompactWindowBounds(historyResizePassiveWindowBounds, surfaceResizePassiveWindowBounds);
      // 工具轮盘开合不得改变载体窗口尺寸。打开轮盘时 renderer 会把历史面板顶部的
      // resize 悬停手柄从命中集移除 → historyResizeHoverRects 变空 → 上面的 history
      // passive carrier 不再为历史 resize 预留上方空间 → 载体窗口从全高缩回贴合内容；
      // 关轮盘手柄恢复又长回全高。每次开/关都整窗 resize，肉眼即聊天界面闪跳 / 向上跳。
      // 载体是透明窗口，轮盘打开期间维持其当前（更大）bounds 不收缩即可消抖，且不影响
      // 任何可见内容或命中（hit/native 区另行计算，轮盘自身命中由 toolFan 路径处理）。
      if (desktopCompactToolFanOpenSolid) {
        var preFanCarrierBounds = normalizeWindowBounds(currentWindowBounds);
        if (preFanCarrierBounds) {
          windowBounds = unionDesktopCompactWindowBounds(windowBounds, preFanCarrierBounds) || windowBounds;
        }
      }
    }
    windowBounds = getDesktopCompactX11StableCarrierBounds(area) || waylandStableCarrierBounds || windowBounds;
    var avatar = normalizeRect(avatarPayload && avatarPayload.bounds);
    var localAvatar = avatar ? {
      left: avatar.left - windowBounds.x,
      top: avatar.top - windowBounds.y,
      right: avatar.right - windowBounds.x,
      bottom: avatar.bottom - windowBounds.y,
      width: avatar.width,
      height: avatar.height,
      centerX: avatar.centerX - windowBounds.x,
      centerY: avatar.centerY - windowBounds.y
    } : null;
    var ballScreenRect = buildDesktopCompactBallScreenRect(avatarPayload, area);
    return {
      avatarBounds: localAvatar,
      workArea: {
        x: areaX,
        y: areaY,
        width: areaWidth,
        height: areaHeight
      },
      windowBounds: windowBounds,
      surfaceResizeWindowBounds: surfaceResizeWindowBounds,
      surfaceScreenRect: surfaceUnion,
      surface: convertScreenRectToPageRect(surfaceUnion, windowBounds),
      ballScreenRect: ballScreenRect,
      compactChoicePlacement: compactChoicePlacement,
      nativeScreenRects: nativeRects,
      hitScreenRects: hitRects,
      historyPassthroughScreenRects: historyPassthroughRects,
      historyResizeHoverScreenRects: historyResizeHoverRects,
      nativeRects: nativeRects.map(function (rect) {
        return convertScreenRectToPageRect(rect, windowBounds);
      }).filter(Boolean),
      hitRects: hitRects.map(function (rect) {
        return convertScreenRectToPageRect(rect, windowBounds);
      }).filter(Boolean),
      historyPassthroughRects: historyPassthroughRects.map(function (rect) {
        return convertScreenRectToPageRect(rect, windowBounds);
      }).filter(Boolean),
      historyResizeHoverRects: historyResizeHoverRects.map(function (rect) {
        return convertScreenRectToPageRect(rect, windowBounds);
      }).filter(Boolean)
    };
  }

  function rebaseDesktopCompactLayoutToWindowBounds(layout, windowBounds) {
    var targetBounds = normalizeWindowBounds(windowBounds);
    if (!layout || !targetBounds) return layout;
    return Object.assign({}, layout, {
      windowBounds: targetBounds,
      surface: convertScreenRectToPageRect(layout.surfaceScreenRect, targetBounds),
      nativeRects: (layout.nativeScreenRects || []).map(function (rect) {
        return convertScreenRectToPageRect(rect, targetBounds);
      }).filter(Boolean),
      hitRects: (layout.hitScreenRects || []).map(function (rect) {
        return convertScreenRectToPageRect(rect, targetBounds);
      }).filter(Boolean),
      historyPassthroughRects: (layout.historyPassthroughScreenRects || []).map(function (rect) {
        return convertScreenRectToPageRect(rect, targetBounds);
      }).filter(Boolean),
      historyResizeHoverRects: (layout.historyResizeHoverScreenRects || []).map(function (rect) {
        return convertScreenRectToPageRect(rect, targetBounds);
      }).filter(Boolean)
    });
  }

  function getDesktopCompactRendererWindowBounds(fallbackBounds) {
    var fallback = normalizeWindowBounds(fallbackBounds);
    var x = Math.round(Number(window.screenX));
    var y = Math.round(Number(window.screenY));
    var width = Math.round(Number(window.innerWidth));
    var height = Math.round(Number(window.innerHeight));
    if (
      !Number.isFinite(x)
      || !Number.isFinite(y)
      || !Number.isFinite(width)
      || !Number.isFinite(height)
      || width <= 0
      || height <= 0
    ) {
      return fallback;
    }
    return {
      x: x,
      y: y,
      width: width,
      height: height
    };
  }

  function syncDesktopCompactLayoutToRendererBounds() {
    if (!desktopCompactLayout || getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized) return;
    if (desktopCompactSurfaceDragActive) return;
    if (desktopCompactSurfaceResizeActive) return;
    if (isDesktopCompactHistoryResizeIsolating()) return;
    if (isDesktopCompactHistoryResizeActive()) return;
    if (desktopCompactHistoryResizeCarrierBounds) return;
    var rendererBounds = getDesktopCompactRendererWindowBounds(desktopCompactLayout.windowBounds);
    if (!rendererBounds || sameWindowBounds(rendererBounds, desktopCompactLayout.windowBounds)) return;
    var pageLayout = rebaseDesktopCompactLayoutToWindowBounds(desktopCompactLayout, rendererBounds);
    applyDesktopCompactLayoutToPage(pageLayout);
    applyDesktopCompactNativeRegion(pageLayout);
    syncDesktopCompactHistoryPointerPassthroughWithCursor(pageLayout);
  }

  function applyDesktopCompactSurfaceCssVars(layout) {
    var surface = normalizeRect(layout && layout.surface);
    var rawWorkArea = layout && layout.workArea;
    var workArea = rawWorkArea ? {
      width: Math.round(Number(rawWorkArea.width) || 0),
      height: Math.round(Number(rawWorkArea.height) || 0)
    } : null;
    var targets = [
      document.documentElement,
      document.getElementById('react-chat-window-shell'),
      document.querySelector('.compact-chat-surface-shell')
    ].filter(Boolean);
    var props = [
      '--compact-surface-left',
      '--compact-surface-top',
      '--compact-surface-width',
      '--compact-surface-height',
      '--desktop-compact-surface-left',
      '--desktop-compact-surface-top',
      '--desktop-compact-surface-width',
      '--desktop-compact-surface-height'
    ];
    if (!surface) {
      targets.forEach(function (target) {
        props.forEach(function (prop) { target.style.removeProperty(prop); });
        target.style.removeProperty('--compact-desktop-workarea-width');
        target.style.removeProperty('--compact-desktop-workarea-height');
      });
      return;
    }
    targets.forEach(function (target) {
      target.style.setProperty('--compact-surface-left', Math.round(surface.left) + 'px');
      target.style.setProperty('--compact-surface-top', Math.round(surface.top) + 'px');
      target.style.setProperty('--compact-surface-width', Math.round(surface.width) + 'px');
      target.style.setProperty('--compact-surface-height', Math.round(surface.height) + 'px');
      target.style.setProperty('--desktop-compact-surface-left', Math.round(surface.left) + 'px');
      target.style.setProperty('--desktop-compact-surface-top', Math.round(surface.top) + 'px');
      target.style.setProperty('--desktop-compact-surface-width', Math.round(surface.width) + 'px');
      target.style.setProperty('--desktop-compact-surface-height', Math.round(surface.height) + 'px');
      if (workArea) {
        target.style.setProperty('--compact-desktop-workarea-width', Math.round(workArea.width) + 'px');
        target.style.setProperty('--compact-desktop-workarea-height', Math.round(workArea.height) + 'px');
      }
    });
  }

  function clearDesktopCompactLayout() {
    clearDesktopCompactSurfaceDragPrime();
    clearDesktopCompactHistoryDragState();
    clearDesktopCompactBoundsVerification();
    clearDesktopCompactHistoryResizeIsolation();
    desktopCompactLayout = null;
    desktopCompactPageLayoutSnapshot = '';
    desktopCompactInteractionGeometrySummary = '';
    desktopCompactTransientGeometrySummary = '';
    desktopCompactPendingWindowBounds = null;
    applyDesktopCompactSurfaceCssVars(null);
    window.__nekoDesktopCompactLayout = null;
    window.__nekoDesktopAvatarBounds = null;
    desktopCompactAvatarBoundsOnlySnapshot = '';
    window.__nekoDesktopCompactExternalBall = false;
    window.__nekoDesktopCompactBallScreenRect = null;
    setDesktopCompactHistoryPointerPassthrough(false);
    stopDesktopCompactHistoryHoverPoll();
    setDesktopCompactHistoryHoverActive(false);
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    window.dispatchEvent(new CustomEvent('neko:desktop-compact-layout-change', { detail: null }));
    window.dispatchEvent(new CustomEvent('neko:desktop-avatar-bounds-change', { detail: null }));
  }

  function applyDesktopCompactLayoutToPage(layout) {
    if (!layout) {
      clearDesktopCompactLayout();
      return;
    }
    desktopCompactLayout = layout;
    var nextAvatarBounds = layout.avatarBounds || null;
    var nextCompactLayout = {
      surface: layout.surface,
      surfaceScreenRect: layout.surfaceScreenRect || null,
      ball: layout.ballScreenRect || null,
      windowBounds: layout.windowBounds || null,
      workArea: layout.workArea || null,
      compactChoicePlacement: layout.compactChoicePlacement || null,
      dragging: !!desktopCompactSurfaceDragActive
    };
    var snapshot = JSON.stringify({
      avatarBounds: nextAvatarBounds,
      compactLayout: nextCompactLayout
    });
    if (snapshot === desktopCompactPageLayoutSnapshot) {
      applyDesktopCompactSurfaceCssVars(nextCompactLayout);
      syncDesktopCompactHistoryHoverWithCursor(layout);
      return;
    }
    desktopCompactPageLayoutSnapshot = snapshot;
    window.__nekoDesktopAvatarBounds = nextAvatarBounds;
    window.__nekoDesktopCompactLayout = nextCompactLayout;
    applyDesktopCompactSurfaceCssVars(nextCompactLayout);
    window.__nekoDesktopCompactExternalBall = true;
    window.__nekoDesktopCompactBallScreenRect = layout.ballScreenRect || null;
    window.dispatchEvent(new CustomEvent('neko:desktop-avatar-bounds-change', { detail: window.__nekoDesktopAvatarBounds }));
    window.dispatchEvent(new CustomEvent('neko:desktop-compact-layout-change', { detail: window.__nekoDesktopCompactLayout }));
    syncDesktopCompactHistoryHoverWithCursor(layout);
    if (desktopCompactSurfaceDragSettledTarget && !desktopCompactSurfaceDragActive) {
      desktopCompactSurfaceDragSettledTarget = null;
      desktopCompactSurfaceDragSettledWorkArea = null;
    }
    refreshDesktopCompactHistoryDragDropTargetState();
  }

  function normalizeDesktopCompactShapeRects(rects, slop) {
    var grow = Math.max(0, Math.round(Number(slop) || 0));
    return (Array.isArray(rects) ? rects : []).map(function (rect) {
      var normalized = normalizeRect(rect);
      if (!normalized) return null;
      return {
        x: Math.max(0, Math.round(normalized.left) - grow),
        y: Math.max(0, Math.round(normalized.top) - grow),
        width: Math.max(1, Math.round(normalized.width) + grow * 2),
        height: Math.max(1, Math.round(normalized.height) + grow * 2)
      };
    }).filter(Boolean);
  }

  function serializeShapeRects(rects) {
    return (rects || []).map(function (rect) {
      return [rect.x, rect.y, rect.width, rect.height].map(function (n) {
        return Math.round(Number(n) || 0);
      }).join(',');
    }).join('|');
  }

  function buildDesktopCompactFullWindowShapeRects(bounds) {
    var normalizedBounds = normalizeWindowBounds(bounds);
    var width = normalizedBounds
      ? normalizedBounds.width
      : Math.max(1, Math.round(Number(window.innerWidth) || 1));
    var height = normalizedBounds
      ? normalizedBounds.height
      : Math.max(1, Math.round(Number(window.innerHeight) || 1));
    return [{ x: 0, y: 0, width: width, height: height }];
  }

  function getDesktopCompactFullWindowShapeSnapshot(bounds) {
    return 'wayland-full-window:' + serializeShapeRects(buildDesktopCompactFullWindowShapeRects(bounds));
  }

  function getDesktopCompactWaylandSelfBallShapeSnapshot(anchorBounds, carrierBounds) {
    var rect = buildDesktopCompactWaylandSelfBallLocalRect(anchorBounds, carrierBounds);
    return rect ? 'wayland-self-ball:' + serializeShapeRects([rect]) : '';
  }

  function sendDesktopCompactWaylandSelfBallShape(reason, anchorBounds, carrierBounds) {
    if (!desktopCompactHasSetShape || !_isNativeWayland) return;
    var rect = buildDesktopCompactWaylandSelfBallLocalRect(anchorBounds, carrierBounds);
    if (!rect) return;
    var carrier = getDesktopCompactWaylandSelfBallCarrierBounds(carrierBounds);
    var snapshot = getDesktopCompactWaylandSelfBallShapeSnapshot(anchorBounds, carrier);
    desktopCompactNativeRegionSnapshot = snapshot;
    desktopCompactNativeRegionLastSentAt = Date.now();
    ipcRenderer.send('neko:pet-set-shape', [rect], buildDesktopCompactSetShapeMeta(
      reason || 'wayland-self-ball',
      'wayland-self-ball',
      carrier,
      snapshot,
      [buildDesktopCompactWaylandSelfBallScreenRect(anchorBounds)].filter(Boolean)
    ));
  }

  function sendDesktopCompactWaylandFullWindowShape(reason, bounds) {
    if (!desktopCompactHasSetShape || !_isNativeWayland) return;
    var rects = buildDesktopCompactFullWindowShapeRects(bounds);
    desktopCompactNativeRegionSnapshot = getDesktopCompactFullWindowShapeSnapshot(bounds);
    desktopCompactNativeRegionLastSentAt = Date.now();
    ipcRenderer.send('neko:pet-set-shape', rects, buildDesktopCompactSetShapeMeta(
      reason || 'wayland-full-window',
      'wayland-full-window',
      bounds,
      desktopCompactNativeRegionSnapshot,
      []
    ));
  }

  function sendDesktopCompactFullWindowSetShape(reason, bounds) {
    if (!desktopCompactHasSetShape) return;
    var rects = buildDesktopCompactFullWindowShapeRects(bounds);
    sendDesktopCompactNativeRegionRects(
      rects,
      getDesktopCompactFullWindowShapeSnapshot(bounds),
      bounds,
      reason || 'full-window-setShape',
      'full-window-surface',
      []
    );
  }

  function getDesktopCompactNativeRegionReason() {
    if (desktopCompactToolWheelDragActive || window.__nekoForceInteractive) return 'force-interactive';
    if (desktopCompactSurfaceDragPrimeActive) return 'surface-drag-prime';
    if (desktopCompactSurfaceDragActive) return 'surface-drag-active';
    if (desktopCompactToolFanOpenSolid) return 'tool-fan-open';
    return 'compact-hit-region';
  }

  function buildDesktopCompactSetShapeMeta(reason, mode, bounds, snapshot, screenRects) {
    var normalizedBounds = normalizeWindowBounds(bounds);
    return {
      source: 'react-chat-compact',
      reason: String(reason || 'compact-hit-region'),
      mode: String(mode || 'hit-region'),
      snapshot: snapshot ? String(snapshot).slice(0, 160) : '',
      wayland: !!_isNativeWayland,
      surfaceMode: getCurrentReactChatSurfaceMode(),
      minimized: !!eMinimized,
      forceInteractive: !!window.__nekoForceInteractive,
      toolWheelDragActive: !!desktopCompactToolWheelDragActive,
      surfaceDragActive: !!desktopCompactSurfaceDragActive,
      devicePixelRatio: Number(window.devicePixelRatio) || 1,
      bounds: normalizedBounds,
      screenRects: Array.isArray(screenRects) ? screenRects.slice(0, 24) : []
    };
  }

  function sendDesktopCompactNativeRegionRects(rects, snapshot, bounds, reason, mode, screenRects) {
    desktopCompactNativeRegionSnapshot = snapshot || serializeShapeRects(rects);
    desktopCompactNativeRegionLastSentAt = Date.now();
    if (desktopCompactHasSetShape) {
      ipcRenderer.send('neko:pet-set-shape', rects, buildDesktopCompactSetShapeMeta(
        reason || getDesktopCompactNativeRegionReason(),
        mode || 'hit-region',
        bounds,
        desktopCompactNativeRegionSnapshot,
        screenRects
      ));
    } else {
      ipcRenderer.send('neko:pet-input-regions', rects);
    }
  }

  function clearDesktopCompactPendingNativeRegion() {
    if (desktopCompactNativeRegionPendingTimer) {
      window.clearTimeout(desktopCompactNativeRegionPendingTimer);
      desktopCompactNativeRegionPendingTimer = 0;
    }
    desktopCompactNativeRegionPendingRects = null;
    desktopCompactNativeRegionPendingSnapshot = '';
    desktopCompactNativeRegionPendingBounds = null;
    desktopCompactNativeRegionPendingReason = '';
    desktopCompactNativeRegionPendingMode = '';
    desktopCompactNativeRegionPendingScreenRects = null;
  }

  function flushDesktopCompactPendingNativeRegion() {
    desktopCompactNativeRegionPendingTimer = 0;
    var rects = desktopCompactNativeRegionPendingRects;
    var snapshot = desktopCompactNativeRegionPendingSnapshot;
    var bounds = desktopCompactNativeRegionPendingBounds;
    var reason = desktopCompactNativeRegionPendingReason;
    var mode = desktopCompactNativeRegionPendingMode;
    var screenRects = desktopCompactNativeRegionPendingScreenRects;
    desktopCompactNativeRegionPendingRects = null;
    desktopCompactNativeRegionPendingSnapshot = '';
    desktopCompactNativeRegionPendingBounds = null;
    desktopCompactNativeRegionPendingReason = '';
    desktopCompactNativeRegionPendingMode = '';
    desktopCompactNativeRegionPendingScreenRects = null;
    // 节流窗口内可能已进入 tool-wheel 拖拽 / forceInteractive：此时全窗口区已直发，
    // pending 里的窄命中区是陈旧的，发出去会把交互中的窗口大半切成穿透，必须丢弃。
    if (!shouldThrottleDesktopCompactNativeRegion()) return;
    if (!rects || !snapshot || snapshot === desktopCompactNativeRegionSnapshot) return;
    sendDesktopCompactNativeRegionRects(rects, snapshot, bounds, reason, mode, screenRects);
  }

  function shouldThrottleDesktopCompactNativeRegion() {
    return !!(
      desktopCompactUseX11InputShape
      && !desktopCompactToolWheelDragActive
      && !window.__nekoForceInteractive
    );
  }

  function isPointInDesktopCompactRect(x, y, rect) {
    var normalized = normalizeRect(rect);
    if (!normalized) return false;
    return x >= normalized.left
      && x < normalized.right
      && y >= normalized.top
      && y < normalized.bottom;
  }

  function isPointInDesktopCompactRects(x, y, rects) {
    return (Array.isArray(rects) ? rects : []).some(function (rect) {
      return isPointInDesktopCompactRect(x, y, rect);
    });
  }

  function inflateDesktopCompactRect(rect, padding) {
    var normalized = normalizeRect(rect);
    if (!normalized) return null;
    var grow = Math.max(0, Math.round(Number(padding) || 0));
    return {
      left: normalized.left - grow,
      top: normalized.top - grow,
      width: normalized.width + grow * 2,
      height: normalized.height + grow * 2,
      right: normalized.right + grow,
      bottom: normalized.bottom + grow
    };
  }

  function isPointInDesktopCompactGuardedHitRects(layout, x, y) {
    var hitRects = layout && layout.hitRects;
    if (!Array.isArray(hitRects) || !hitRects.length) return false;
    return hitRects.some(function (rect) {
      return isPointInDesktopCompactRect(x, y, inflateDesktopCompactRect(rect, DESKTOP_COMPACT_POINTER_HIT_GUARD_PX));
    });
  }

  function hasDesktopCompactHistoryResizeHoverTarget(layout) {
    var resizeRects = layout && layout.historyResizeHoverRects;
    return Array.isArray(resizeRects) && resizeRects.length > 0;
  }

  function shouldTrackDesktopCompactHistoryHover(layout) {
    var targetLayout = layout || desktopCompactLayout;
    return !!(
      targetLayout
      && getCurrentReactChatSurfaceMode() === 'compact'
      && !eMinimized
      && !isReactChatWindowHidden()
      && hasDesktopCompactHistoryResizeHoverTarget(targetLayout)
    );
  }

  function setDesktopCompactHistoryHoverActive(active) {
    var nextActive = !!active;
    if (desktopCompactHistoryHoverActive === nextActive) return;
    desktopCompactHistoryHoverActive = nextActive;
    if (nextActive) {
      document.documentElement.setAttribute('data-neko-desktop-compact-history-hover', 'true');
    } else {
      document.documentElement.removeAttribute('data-neko-desktop-compact-history-hover');
    }
  }

  function syncDesktopCompactHistoryHoverFromPoint(x, y, layout) {
    var targetLayout = layout || desktopCompactLayout;
    if (!shouldTrackDesktopCompactHistoryHover(targetLayout)) {
      setDesktopCompactHistoryHoverActive(false);
      return;
    }
    var px = Number(x);
    var py = Number(y);
    setDesktopCompactHistoryHoverActive(
      Number.isFinite(px)
      && Number.isFinite(py)
      && isPointInDesktopCompactRects(px, py, targetLayout.historyResizeHoverRects || [])
    );
  }

  function syncDesktopCompactHistoryHoverFromScreenPoint(point, layout) {
    var pagePoint = convertDesktopCompactScreenPointToPagePoint(point, layout);
    if (!pagePoint) {
      setDesktopCompactHistoryHoverActive(false);
      return;
    }
    syncDesktopCompactHistoryHoverFromPoint(pagePoint.x, pagePoint.y, layout);
  }

  function stopDesktopCompactHistoryHoverPoll() {
    if (!desktopCompactHistoryHoverPollTimer) return;
    window.clearInterval(desktopCompactHistoryHoverPollTimer);
    desktopCompactHistoryHoverPollTimer = 0;
  }

  function pollDesktopCompactHistoryHover() {
    var targetLayout = desktopCompactLayout;
    if (!shouldTrackDesktopCompactHistoryHover(targetLayout)) {
      stopDesktopCompactHistoryHoverPoll();
      setDesktopCompactHistoryHoverActive(false);
      return;
    }
    if (desktopCompactHistoryHoverPollInFlight) return;
    desktopCompactHistoryHoverPollInFlight = true;
    ipcRenderer.invoke('get-cursor-point').then(function (point) {
      syncDesktopCompactHistoryHoverFromScreenPoint(point, targetLayout);
    }).catch(function () {
      setDesktopCompactHistoryHoverActive(false);
    }).finally(function () {
      desktopCompactHistoryHoverPollInFlight = false;
    });
  }

  function syncDesktopCompactHistoryHoverWithCursor(layout) {
    if (!shouldTrackDesktopCompactHistoryHover(layout)) {
      stopDesktopCompactHistoryHoverPoll();
      setDesktopCompactHistoryHoverActive(false);
      return;
    }
    if (!desktopCompactUsesNativeInputRegion) {
      stopDesktopCompactHistoryHoverPoll();
      pollDesktopCompactHistoryHover();
      return;
    }
    if (!desktopCompactHistoryHoverPollTimer) {
      desktopCompactHistoryHoverPollTimer = window.setInterval(
        pollDesktopCompactHistoryHover,
        DESKTOP_COMPACT_POINTER_PASSTHROUGH_POLL_MS
      );
    }
    pollDesktopCompactHistoryHover();
  }

  function isPointInsideDesktopCompactWindow(layout, x, y) {
    var bounds = normalizeWindowBounds(layout && layout.windowBounds);
    if (!bounds) return false;
    return x >= 0
      && y >= 0
      && x < bounds.width
      && y < bounds.height;
  }

  // Window-relative (page) rect of the open tool-wheel circle, or null. Used to
  // keep just the wheel solid while it is open — scoped to the circle, not the
  // whole window, so the reserve margins / desktop behind stay click-through.
  function hasDesktopCompactToolFanVisibleItem(fanEl) {
    if (!fanEl || typeof fanEl.querySelectorAll !== 'function') return false;
    var items = fanEl.querySelectorAll('.compact-input-tool-item');
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      if (!item || typeof item.getBoundingClientRect !== 'function') continue;
      var itemRect = item.getBoundingClientRect();
      if (!(Number(itemRect.width) > 0 && Number(itemRect.height) > 0)) continue;
      var style = window.getComputedStyle ? window.getComputedStyle(item) : null;
      if (style && (style.display === 'none' || style.visibility === 'hidden')) continue;
      var opacity = style ? Number(style.opacity) : 1;
      if (!Number.isFinite(opacity)) opacity = 1;
      if (opacity > DESKTOP_COMPACT_TOOL_FAN_VISIBLE_OPACITY_MIN) return true;
    }
    return false;
  }

  function clearDesktopCompactToolFanVisibleRegionRetry() {
    if (desktopCompactToolFanVisibleRetryFrame) {
      window.cancelAnimationFrame(desktopCompactToolFanVisibleRetryFrame);
      desktopCompactToolFanVisibleRetryFrame = 0;
    }
    desktopCompactToolFanVisibleRetryCount = 0;
    desktopCompactToolFanLayoutRetryCount = 0;
  }

  function scheduleDesktopCompactToolFanVisibleRegionRetry() {
    if (!desktopCompactToolFanOpenSolid) return;
    if (desktopCompactToolFanVisibleRetryFrame) return;
    if (desktopCompactToolFanVisibleRetryCount >= DESKTOP_COMPACT_TOOL_FAN_VISIBLE_RETRY_MAX) return;
    desktopCompactToolFanVisibleRetryFrame = window.requestAnimationFrame(function () {
      desktopCompactToolFanVisibleRetryFrame = 0;
      if (!desktopCompactToolFanOpenSolid) {
        desktopCompactToolFanVisibleRetryCount = 0;
        return;
      }
      if (desktopCompactLayout) {
        desktopCompactToolFanLayoutRetryCount = 0;
        desktopCompactToolFanVisibleRetryCount += 1;
        applyDesktopCompactNativeRegion(desktopCompactLayout);
        syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
      } else {
        desktopCompactToolFanLayoutRetryCount += 1;
        scheduleDesktopCompactRelayout();
        if (desktopCompactToolFanLayoutRetryCount < DESKTOP_COMPACT_TOOL_FAN_LAYOUT_RETRY_MAX) {
          scheduleDesktopCompactToolFanVisibleRegionRetry();
        }
      }
    });
  }

  function getDesktopCompactToolFanOpenClientRect() {
    var fanEl = document.querySelector('.compact-input-tool-fan[data-compact-input-tool-fan-open="true"]');
    if (!fanEl || typeof fanEl.getBoundingClientRect !== 'function') {
      scheduleDesktopCompactToolFanVisibleRegionRetry();
      return null;
    }
    var r = fanEl.getBoundingClientRect();
    if (!(Number(r.width) > 0 && Number(r.height) > 0)) {
      scheduleDesktopCompactToolFanVisibleRegionRetry();
      return null;
    }
    var fanStyle = window.getComputedStyle ? window.getComputedStyle(fanEl) : null;
    var fanOpacity = fanStyle ? Number(fanStyle.opacity) : 1;
    if (!Number.isFinite(fanOpacity)) fanOpacity = 1;
    if (fanStyle && (fanStyle.display === 'none' || fanStyle.visibility === 'hidden' || fanOpacity <= DESKTOP_COMPACT_TOOL_FAN_VISIBLE_OPACITY_MIN)) {
      scheduleDesktopCompactToolFanVisibleRegionRetry();
      return null;
    }
    if (!hasDesktopCompactToolFanVisibleItem(fanEl)) {
      scheduleDesktopCompactToolFanVisibleRegionRetry();
      return null;
    }
    desktopCompactToolFanVisibleRetryCount = 0;
    desktopCompactToolFanLayoutRetryCount = 0;
    return { left: r.left, top: r.top, width: r.width, height: r.height, right: r.right, bottom: r.bottom };
  }

  function shouldPassThroughDesktopCompactPoint(layout, x, y) {
    if (window.__nekoForceInteractive) return false;
    if (desktopCompactUsesNativeInputRegion) return false;
    if (eMinimized || getCurrentReactChatSurfaceMode() !== 'compact') return false;
    if (desktopCompactHistoryDragState) return false;
    if (desktopCompactToolWheelDragActive) return false;
    if (desktopCompactToolFanOpenSolid) {
      var fanRect = getDesktopCompactToolFanOpenClientRect();
      // Solid only inside the wheel circle; outside it (reserve/desktop) keeps
      // passing clicks through.
      if (fanRect && isPointInDesktopCompactRect(x, y, fanRect)) return false;
    }
    var targetLayout = layout || desktopCompactLayout;
    if (!targetLayout) return false;
    var nativeRects = (targetLayout.nativeRects || []).concat(targetLayout.historyPassthroughRects || []);
    if (isPointInDesktopCompactRects(x, y, targetLayout.hitRects || [])) return false;
    // Native ignore is a whole-window switch on Windows/macOS/X11. Keep a small
    // guard band around real hit regions solid so a fast click that starts from
    // nearby transparent history space does not land while the window is still
    // in passthrough mode. Far transparent space still passes through.
    if (isPointInDesktopCompactGuardedHitRects(targetLayout, x, y)) return false;
    return isPointInsideDesktopCompactWindow(targetLayout, x, y)
      || isPointInDesktopCompactRects(x, y, nativeRects);
  }

  function convertDesktopCompactScreenPointToPagePoint(point, layout) {
    var targetLayout = layout || desktopCompactLayout;
    var bounds = normalizeWindowBounds(targetLayout && targetLayout.windowBounds);
    if (!point) return null;
    var screenX = Number(point.screenX);
    var screenY = Number(point.screenY);
    if (bounds && Number.isFinite(screenX) && Number.isFinite(screenY)) {
      return {
        x: screenX - bounds.x,
        y: screenY - bounds.y
      };
    }
    var x = Number(point.x);
    var y = Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {
      x: x,
      y: y
    };
  }

  function setDesktopCompactHistoryPointerPassthrough(enabled) {
    var nextEnabled = !!enabled && !desktopCompactUsesNativeInputRegion;
    if (desktopCompactHistoryPointerPassthrough === nextEnabled) {
      if (nextEnabled) startDesktopCompactHistoryPointerPassthroughPoll();
      return;
    }
    desktopCompactHistoryPointerPassthrough = nextEnabled;
    window.__nekoDesktopCompactHistoryPointerPassthrough = nextEnabled;
    if (nextEnabled) {
      // 空白区穿透时不要继续转发 mousemove，否则聊天窗口会和下层控件反复争抢 cursor。
      ipcRenderer.send('set-ignore-mouse-events', true);
      startDesktopCompactHistoryPointerPassthroughPoll();
    } else {
      stopDesktopCompactHistoryPointerPassthroughPoll();
      ipcRenderer.send('set-ignore-mouse-events', false);
    }
  }

  function stopDesktopCompactHistoryPointerPassthroughPoll() {
    if (!desktopCompactHistoryPointerPassthroughPollTimer) return;
    window.clearInterval(desktopCompactHistoryPointerPassthroughPollTimer);
    desktopCompactHistoryPointerPassthroughPollTimer = 0;
  }

  function pollDesktopCompactHistoryPointerPassthrough() {
    if (!desktopCompactHistoryPointerPassthrough || desktopCompactUsesNativeInputRegion) {
      stopDesktopCompactHistoryPointerPassthroughPoll();
      return;
    }
    if (desktopCompactHistoryPointerPassthroughPollInFlight) return;
    desktopCompactHistoryPointerPassthroughPollInFlight = true;
    ipcRenderer.invoke('get-cursor-point').then(function (point) {
      if (!desktopCompactHistoryPointerPassthrough) return;
      if (!point) {
        setDesktopCompactHistoryPointerPassthrough(false);
        return;
      }
      syncDesktopCompactHistoryPointerPassthroughFromScreenPoint(point, desktopCompactLayout);
    }).catch(function () {
      setDesktopCompactHistoryPointerPassthrough(false);
    }).finally(function () {
      desktopCompactHistoryPointerPassthroughPollInFlight = false;
    });
  }

  function startDesktopCompactHistoryPointerPassthroughPoll() {
    if (desktopCompactUsesNativeInputRegion || desktopCompactHistoryPointerPassthroughPollTimer) return;
    desktopCompactHistoryPointerPassthroughPollTimer = window.setInterval(
      pollDesktopCompactHistoryPointerPassthrough,
      DESKTOP_COMPACT_POINTER_PASSTHROUGH_POLL_MS
    );
    pollDesktopCompactHistoryPointerPassthrough();
  }

  function clearDesktopCompactToolWheelDragTimer() {
    if (!desktopCompactToolWheelDragClearTimer) return;
    window.clearTimeout(desktopCompactToolWheelDragClearTimer);
    desktopCompactToolWheelDragClearTimer = 0;
  }

  function applyDesktopCompactToolWheelDragState(active) {
    var nextActive = !!active;
    clearDesktopCompactToolWheelDragTimer();
    if (nextActive) {
      desktopCompactToolWheelDragClearTimer = window.setTimeout(function () {
        desktopCompactToolWheelDragClearTimer = 0;
        applyDesktopCompactToolWheelDragState(false);
      }, DESKTOP_COMPACT_TOOL_WHEEL_DRAG_STALE_MS);
    }
    if (desktopCompactToolWheelDragActive === nextActive) return;
    desktopCompactToolWheelDragActive = nextActive;
    window.__nekoDesktopCompactToolWheelDragActive = nextActive;
    if (nextActive) {
      setDesktopCompactHistoryPointerPassthrough(false);
    }
    if (desktopCompactLayout) {
      applyDesktopCompactNativeRegion(desktopCompactLayout);
      syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
    } else {
      scheduleDesktopCompactRelayout();
    }
  }

  function applyDesktopCompactToolFanOpenState(open) {
    var nextOpen = !!open;
    if (desktopCompactToolFanOpenSolid === nextOpen) return;
    desktopCompactToolFanOpenSolid = nextOpen;
    window.__nekoDesktopCompactToolFanOpenSolid = nextOpen;
    clearDesktopCompactToolFanVisibleRegionRetry();
    desktopCompactInteractionGeometrySummary = '';
    desktopCompactWindowSnapshot = '';
    if (nextOpen) {
      setDesktopCompactHistoryPointerPassthrough(false);
      scheduleDesktopCompactToolFanVisibleRegionRetry();
    }
    if (desktopCompactLayout) {
      applyDesktopCompactNativeRegion(desktopCompactLayout);
      syncDesktopCompactHistoryPointerPassthroughWithCursor(desktopCompactLayout);
    }
    scheduleDesktopCompactRelayout();
  }

  function syncDesktopCompactHistoryPointerPassthroughFromPoint(x, y, layout) {
    syncDesktopCompactHistoryHoverFromPoint(x, y, layout);
    if (desktopCompactHistoryDragRestoreActive) {
      setDesktopCompactHistoryPointerPassthrough(true);
      return;
    }
    var px = Number(x);
    var py = Number(y);
    if (!Number.isFinite(px) || !Number.isFinite(py)) {
      setDesktopCompactHistoryPointerPassthrough(false);
      return;
    }
    setDesktopCompactHistoryPointerPassthrough(
      shouldPassThroughDesktopCompactPoint(layout, px, py)
    );
  }

  function syncDesktopCompactHistoryPointerPassthroughFromScreenPoint(point, layout) {
    if (desktopCompactHistoryDragRestoreActive) {
      setDesktopCompactHistoryPointerPassthrough(true);
      return;
    }
    var pagePoint = convertDesktopCompactScreenPointToPagePoint(point, layout);
    if (!pagePoint) {
      setDesktopCompactHistoryPointerPassthrough(false);
      return;
    }
    syncDesktopCompactHistoryPointerPassthroughFromPoint(pagePoint.x, pagePoint.y, layout);
  }

  function syncDesktopCompactHistoryPointerPassthroughWithCursor(layout) {
    if (desktopCompactHistoryDragRestoreActive) {
      setDesktopCompactHistoryPointerPassthrough(true);
      return;
    }
    if (desktopCompactUsesNativeInputRegion) {
      setDesktopCompactHistoryPointerPassthrough(false);
      return;
    }
    var targetLayout = layout || desktopCompactLayout;
    if (!targetLayout) {
      setDesktopCompactHistoryPointerPassthrough(false);
      return;
    }
    ipcRenderer.invoke('get-cursor-point').then(function (point) {
      if (!point) {
        setDesktopCompactHistoryPointerPassthrough(false);
        return;
      }
      syncDesktopCompactHistoryPointerPassthroughFromScreenPoint(point, targetLayout);
    }).catch(function () {
      setDesktopCompactHistoryPointerPassthrough(false);
    });
  }

  function applyDesktopCompactNativeRegion(layout) {
    if (!desktopCompactCanApplyNativeInputRegion) return;
    var bounds = normalizeWindowBounds(layout && layout.windowBounds);
    var rects;
    var screenRects = [];
    var useFullWindowWaylandShape = !!(
      _isNativeWayland
      && bounds
      && (
        desktopCompactToolWheelDragActive
        || window.__nekoForceInteractive
        || desktopCompactSurfaceDragPrimeActive
        || desktopCompactSurfaceDragActive
      )
    );
    if ((
      desktopCompactToolWheelDragActive
      || window.__nekoForceInteractive
      || (_isNativeWayland && desktopCompactSurfaceDragPrimeActive)
      || (_isNativeWayland && desktopCompactSurfaceDragActive)
    ) && bounds) {
      rects = [{ x: 0, y: 0, width: bounds.width, height: bounds.height }];
      screenRects = [];
    } else {
      rects = normalizeDesktopCompactShapeRects(layout && layout.hitRects, DESKTOP_COMPACT_SHAPE_SLOP);
      screenRects = normalizeDesktopCompactShapeRects(layout && layout.hitScreenRects, DESKTOP_COMPACT_SHAPE_SLOP);
      if (desktopCompactToolFanOpenSolid) {
        var fanRect = getDesktopCompactToolFanOpenClientRect();
        if (fanRect) {
          rects = rects.concat(normalizeDesktopCompactShapeRects([fanRect], DESKTOP_COMPACT_SHAPE_SLOP));
          var fanScreenRect = convertPageRectToScreenRect(fanRect, bounds);
          if (fanScreenRect) {
            screenRects = screenRects.concat(normalizeDesktopCompactShapeRects([fanScreenRect], DESKTOP_COMPACT_SHAPE_SLOP));
          }
        }
      }
    }
    if (!rects.length) rects = [{ x: 0, y: 0, width: 1, height: 1 }];
    var snapshot = useFullWindowWaylandShape
      ? getDesktopCompactFullWindowShapeSnapshot(bounds)
      : serializeShapeRects(rects) + (_isNativeWayland ? '|screen:' + serializeShapeRects(screenRects || []) : '');
    if (snapshot === desktopCompactNativeRegionSnapshot) {
      // 布局已回到上次发送的状态：丢弃节流期挂起的中间态，否则 timer 稍后会把
      // 瞬态命中区（如快速开合的 choice）盖到已正确的区域上。
      clearDesktopCompactPendingNativeRegion();
      return;
    }
    if (shouldThrottleDesktopCompactNativeRegion()) {
      var now = Date.now();
      var elapsed = now - desktopCompactNativeRegionLastSentAt;
      if (desktopCompactNativeRegionLastSentAt && elapsed < DESKTOP_COMPACT_X11_NATIVE_REGION_MIN_MS) {
        desktopCompactNativeRegionPendingRects = rects;
        desktopCompactNativeRegionPendingSnapshot = snapshot;
        desktopCompactNativeRegionPendingBounds = bounds;
        desktopCompactNativeRegionPendingReason = getDesktopCompactNativeRegionReason();
        desktopCompactNativeRegionPendingMode = useFullWindowWaylandShape ? 'wayland-full-window' : 'hit-region';
        desktopCompactNativeRegionPendingScreenRects = screenRects;
        if (!desktopCompactNativeRegionPendingTimer) {
          desktopCompactNativeRegionPendingTimer = window.setTimeout(
            flushDesktopCompactPendingNativeRegion,
            Math.max(16, DESKTOP_COMPACT_X11_NATIVE_REGION_MIN_MS - elapsed)
          );
        }
        return;
      }
      clearDesktopCompactPendingNativeRegion();
    }
    sendDesktopCompactNativeRegionRects(
      rects,
      snapshot,
      bounds,
      getDesktopCompactNativeRegionReason(),
      useFullWindowWaylandShape ? 'wayland-full-window' : 'hit-region',
      screenRects
    );
  }

  function sendDesktopCompactFullWindowInputRegion(reason, bounds) {
    if (!desktopCompactUseX11InputShape) return;
    var normalizedBounds = normalizeWindowBounds(bounds);
    var width = normalizedBounds
      ? normalizedBounds.width
      : Math.max(1, Math.round(Number(window.innerWidth) || 1));
    var height = normalizedBounds
      ? normalizedBounds.height
      : Math.max(1, Math.round(Number(window.innerHeight) || 1));
    ipcRenderer.send('neko:pet-input-regions', {
      inputRects: [{ x: 0, y: 0, width: width, height: height }],
      inputMode: 'normal',
      fullWindowInputReason: reason || 'compact-clear'
    });
  }

  function clearDesktopCompactNativeRegion(fullWindowBounds) {
    desktopCompactNativeRegionSnapshot = '';
    clearDesktopCompactPendingNativeRegion();
    clearDesktopCompactSurfaceDragPrime();
    clearDesktopCompactWaylandSelfBallAnchor();
    clearDesktopCompactHistoryDragRestoreState();
    desktopCompactHistoryDragCarrierBounds = null;
    clearDesktopCompactHistoryResizeIsolation();
    desktopCompactHistoryResizeCarrierBounds = null;
    desktopCompactHistoryResizePassiveCarrierBounds = null;
    desktopCompactHistoryResizePassiveCarrierWorkArea = null;
    desktopCompactHistoryResizeActive = false;
    desktopCompactHistoryResizeCommitPending = false;
    desktopCompactHistoryResizeKeepCarrierOnCommit = false;
    if (desktopCompactHistoryResizeCommitTimer) {
      window.clearTimeout(desktopCompactHistoryResizeCommitTimer);
      desktopCompactHistoryResizeCommitTimer = 0;
    }
    desktopCompactSurfaceResizeCarrierBounds = null;
    desktopCompactSurfaceResizePassiveCarrierBounds = null;
    desktopCompactSurfaceResizePassiveCarrierWorkArea = null;
    desktopCompactSurfaceResizeKeepCarrierOnCommit = false;
    clearDesktopCompactToolWheelDragTimer();
    desktopCompactToolWheelDragActive = false;
    window.__nekoDesktopCompactToolWheelDragActive = false;
    desktopCompactToolFanOpenSolid = false;
    window.__nekoDesktopCompactToolFanOpenSolid = false;
    clearDesktopCompactToolFanVisibleRegionRetry();
    stopDesktopCompactHistoryHoverPoll();
    setDesktopCompactHistoryHoverActive(false);
    if (desktopCompactHasSetShape) {
      if (_isNativeWayland) {
        sendDesktopCompactWaylandFullWindowShape('compact-clear', fullWindowBounds);
      } else {
        ipcRenderer.send('neko:pet-set-shape', []);
      }
    } else if (desktopCompactUseX11InputShape) {
      sendDesktopCompactFullWindowInputRegion('compact-clear', fullWindowBounds);
    }
    setDesktopCompactHistoryPointerPassthrough(false);
    ipcRenderer.send('set-ignore-mouse-events', false);
  }

  // 返回 true 表示本次确实重发了 SHOW（球位置变化，主进程会随之 moveTop）；返回 false
  // 表示位置去重命中（未发 SHOW）或球被隐藏。调用方据此判断是否需要补一次 raise。
  function showDesktopCompactBallWindow(layout) {
    // [compact-ball-removed] 死代码：ballScreenRect 恒为 null（见 buildDesktopCompactBallScreenRect），
    // 故本函数实际只会走下面的 HIDE 分支，永不发 SHOW。
    var rect = layout && layout.ballScreenRect;
    if (!rect) {
      desktopCompactBallWindowSnapshot = '';
      ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE);
      return false;
    }
    var snapshot = [rect.left, rect.top, rect.width, rect.height].map(function (n) {
      return Math.round(Number(n) || 0);
    }).join(':');
    if (snapshot === desktopCompactBallWindowSnapshot) return false;
    desktopCompactBallWindowSnapshot = snapshot;
    ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.SHOW, {
      bounds: {
        x: Math.round(rect.left),
        y: Math.round(rect.top),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });
    return true;
  }

  // 把已显示的独立缩小球重新顶到对话框之上。compact relayout 会反复对对话框 bringToFront，
  // 而 showDesktopCompactBallWindow 的位置去重会抑制球的 SHOW 重发 —— raise 走独立通道，
  // 不被位置去重挡掉，保证球始终浮在对话框上方、可点击。球未显示时不发（主进程也会判可见性）。
  function raiseDesktopCompactBallWindow() {
    // [compact-ball-removed] 死代码：球永不显示，desktopCompactBallWindowSnapshot 恒为 ''，提前 return。
    if (!desktopCompactBallWindowSnapshot) return;
    ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.RAISE);
  }

  function hideDesktopCompactBallWindow() {
    // [compact-ball-removed] 现为 no-op 兜底：球已不再创建，这里仍发 HIDE 以销毁任何历史遗留的球窗口。
    desktopCompactBallWindowSnapshot = '';
    ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE);
  }

  function getDesktopCompactMinimizeButtonFromTarget(target) {
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest(DESKTOP_COMPACT_MINIMIZE_BALL_SELECTOR);
  }

  function getDesktopCompactMinimizeButtonScreenRect(button) {
    var target = button || document.querySelector(DESKTOP_COMPACT_MINIMIZE_BALL_SELECTOR);
    if (!target || typeof target.getBoundingClientRect !== 'function') return null;
    var windowBounds = getDesktopCompactRendererWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds)
      || normalizeWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds);
    if (!windowBounds) return null;
    return convertPageRectToScreenRect(target.getBoundingClientRect(), windowBounds);
  }

  function clearDesktopCompactMinimizeButtonScreenRect() {
    desktopCompactMinimizeButtonScreenRect = null;
    desktopCompactMinimizeButtonScreenRectTimestamp = 0;
  }

  function rememberDesktopCompactMinimizeButtonScreenRect(button) {
    if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) {
      return null;
    }
    var rect = getDesktopCompactMinimizeButtonScreenRect(button);
    if (!rect) return null;
    desktopCompactMinimizeButtonScreenRect = rect;
    desktopCompactMinimizeButtonScreenRectTimestamp = Date.now();
    return rect;
  }

  function getCachedDesktopCompactMinimizeButtonScreenRect() {
    if (!desktopCompactMinimizeButtonScreenRect) return null;
    if (Date.now() - desktopCompactMinimizeButtonScreenRectTimestamp > DESKTOP_COMPACT_MINIMIZE_BUTTON_RECT_STALE_MS) {
      clearDesktopCompactMinimizeButtonScreenRect();
      return null;
    }
    return normalizeRect(desktopCompactMinimizeButtonScreenRect);
  }

  function buildDesktopCompactCollapseTargetFromRect(rect) {
    var normalized = normalizeRect(rect);
    if (!normalized) return null;
    var centerX = normalized.left + normalized.width / 2;
    var centerY = normalized.top + normalized.height / 2;
    return {
      x: Math.round(centerX - WIN_SIZE / 2),
      y: Math.round(centerY - WIN_SIZE / 2 - BALL_DOWN_OFFSET),
      externalBallAnchorX: Math.round(centerX - BALL_SIZE / 2),
      externalBallAnchorY: Math.round(centerY - BALL_SIZE / 2 - (WIN_SIZE - BALL_SIZE))
    };
  }

  function shouldUseDesktopCompactBallCollapseTarget() {
    return desktopCompactWindowActive || !!getCachedDesktopCompactMinimizeButtonScreenRect();
  }

  function getDesktopCompactBallCollapseTarget() {
    // 优先使用缓存的点击时按钮位置：React 在 compactCollapsing 重渲染后
    // 按钮 viewport 位置会变化，live DOM 查询拿到的是重渲染后的错误位置。
    var rect = getCachedDesktopCompactMinimizeButtonScreenRect()
      || getDesktopCompactMinimizeButtonScreenRect()
      || (desktopCompactLayout && desktopCompactLayout.ballScreenRect);
    var target = buildDesktopCompactCollapseTargetFromRect(rect);
    clearDesktopCompactMinimizeButtonScreenRect();
    return target;
  }

  function activateDesktopCompactWindow() {
    if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') return;
    if (
      !desktopCompactWindowActive
      && !desktopCompactAvatarPayload
      && !hasDesktopCompactSurfacePosition()
      && !desktopCompactTutorialFixedLayoutActive
    ) {
      desktopCompactWindowRelayoutQueued = true;
      return;
    }
    if (desktopCompactWindowSavePending) {
      desktopCompactWindowRelayoutQueued = true;
      return;
    }
    desktopCompactWindowSavePending = true;
    desktopCompactWindowRelayoutQueued = false;
    Promise.all([
      W.getBounds().catch(function () { return null; }),
      W.getWorkArea().catch(function () { return null; })
    ]).then(function (values) {
      var actualBounds = normalizeWindowBounds(values[0]);
      var workArea = values[1];
      var pageBounds = getDesktopCompactRendererWindowBounds(actualBounds);
      var activeHistoryDrag = !!desktopCompactHistoryDragState;
      var activeHistoryResize = isDesktopCompactHistoryResizeActive();
      var activeHistoryGeometry = activeHistoryDrag || activeHistoryResize;
      var settlingHistoryResize = isDesktopCompactHistoryResizeSettling();
      var bounds = activeHistoryGeometry
        ? (pageBounds || actualBounds || desktopCompactPendingWindowBounds)
        : (desktopCompactPendingWindowBounds || actualBounds);
      desktopCompactWindowSavePending = false;
      if (!bounds || eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') return;
      if (desktopCompactPendingWindowBounds && sameWindowBounds(actualBounds, desktopCompactPendingWindowBounds)) {
        desktopCompactPendingWindowBounds = null;
        bounds = actualBounds;
      } else if (activeHistoryGeometry && actualBounds) {
        bounds = pageBounds || actualBounds;
      }
      if (!desktopCompactWindowActive && bounds.width > WIN_SIZE + 2 && bounds.height > WIN_SIZE + 2) {
        saveExpandBounds(bounds);
      }
      var layout = buildDesktopCompactWindowLayout(bounds, workArea, desktopCompactAvatarPayload);
      var target = layout.windowBounds;
      var snapshot = [
        target.x,
        target.y,
        target.width,
        target.height,
        layout.surface && Math.round(layout.surface.left),
        layout.surface && Math.round(layout.surface.top),
        layout.surface && Math.round(layout.surface.width)
      ].join(':');
      // 复检（Bug C 防竞态）：collapse→minimized 期间 collapseNativeForReactMinimized 会同步
      // 置 eMinimized=true / 模式已切走。本回调是 compact 阶段排队、在收起动画窗口期才 resolve
      // 的在途 relayout —— 在真正 setBounds 撑窗 + 显示/上浮球之前再判一次，立即放弃，避免把
      // 已塌成折叠尺寸的对话框撑回原尺寸、重现独立缩小球。
      if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') return;
      desktopCompactWindowActive = true;
      var pageLayout = layout;
      var keepHistoryResizeCarrierBounds = !!(
        settlingHistoryResize
        && target
        && (
          desktopCompactHistoryResizeKeepCarrierOnCommit
          || containsWindowBounds(pageBounds, target)
          || containsWindowBounds(actualBounds, target)
        )
      );
      if (
        pageBounds
        && target
        && !desktopCompactUseX11InputShape
        && !desktopCompactSurfaceResizeActive
        && !activeHistoryResize
        && (!settlingHistoryResize || keepHistoryResizeCarrierBounds)
        && !desktopCompactSurfaceDragActive
        && !sameWindowBounds(pageBounds, target)
      ) {
        pageLayout = rebaseDesktopCompactLayoutToWindowBounds(layout, pageBounds);
      }
      var windowBoundsChanged = snapshot !== desktopCompactWindowSnapshot;
      var nativeComparisonBounds = desktopCompactUseX11InputShape && pageBounds ? pageBounds : actualBounds;
      var nativeTarget = keepHistoryResizeCarrierBounds
        ? (actualBounds || pageBounds || target)
        : target;
      var nativeWindowBoundsChanged = !nativeComparisonBounds || !sameWindowBounds(nativeComparisonBounds, nativeTarget);
      var deferHistoryResizePageApply = !!(isDesktopCompactHistoryResizeIsolating() && nativeWindowBoundsChanged);
      if (windowBoundsChanged || nativeWindowBoundsChanged) {
        desktopCompactWindowSnapshot = snapshot;
        desktopCompactPendingWindowBounds = nativeWindowBoundsChanged ? nativeTarget : null;
        dispatchDesktopCompactHistoryDragRebase(pageBounds || actualBounds, target);
        if (nativeWindowBoundsChanged) {
          W.setResizable(false);
          W.setBounds(nativeTarget.x, nativeTarget.y, nativeTarget.width, nativeTarget.height);
          scheduleDesktopCompactBoundsVerification(nativeTarget);
          if (deferHistoryResizePageApply) {
            applyDesktopCompactLayoutToPage(pageLayout);
            applyDesktopCompactNativeRegion(pageLayout);
            syncDesktopCompactHistoryPointerPassthroughWithCursor(pageLayout);
          }
        } else {
          clearDesktopCompactBoundsVerification();
        }
      }
      if (!deferHistoryResizePageApply) {
        applyDesktopCompactLayoutToPage(pageLayout);
        applyDesktopCompactNativeRegion(pageLayout);
        syncDesktopCompactHistoryPointerPassthroughWithCursor(pageLayout);
        if (historyResizeIsolation && historyResizeIsolation.phase === 'settling') {
          completeDesktopCompactHistoryResizeIsolation();
        }
      }
      var ballMoved = showDesktopCompactBallWindow(layout); // [compact-ball-removed] 恒返回 false（球已停用）
      // 仅当对话框窗口或独立球的位置真正变化（典型即模型/拖拽移动、进入 compact、resize）时，
      // 才重排 z-order：先把对话框顶到模型之上（沿用原 bringToFront 语义，拖动模型时模型会抢顶），
      // 紧接着把独立球重新顶到对话框之上（SHOW 的位置去重会抑制球的重发，这里用 raise 通道补上）。
      // 静止态 / keepalive（窗口与球都未动）不触碰 z-order，避免对话框/球这类透明窗口被反复
      // moveTop 触发 DWM 合成层重建而 1Hz 抖动（见 top-coordinator.js 透明窗口闪烁注记）。
      if ((nativeWindowBoundsChanged || ballMoved) && !activeHistoryResize && !settlingHistoryResize) {
        if (typeof W.bringToFront === 'function') {
          W.bringToFront();
        }
        raiseDesktopCompactBallWindow(); // [compact-ball-removed] no-op（球已停用）
      }
      if (desktopCompactWindowRelayoutQueued) {
        desktopCompactWindowRelayoutQueued = false;
        scheduleDesktopCompactRelayout();
      }
    }).catch(function () {
      desktopCompactWindowSavePending = false;
      if (desktopCompactWindowRelayoutQueued) {
        desktopCompactWindowRelayoutQueued = false;
        scheduleDesktopCompactRelayout();
      }
    });
  }

  function scheduleDesktopCompactRelayout(reason) {
    if (desktopCompactRelayoutFrame) {
      return;
    }
    desktopCompactRelayoutFrame = window.requestAnimationFrame(function () {
      desktopCompactRelayoutFrame = 0;
      if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) return;
      activateDesktopCompactWindow();
    });
  }

  function clearDesktopCompactSurfaceDragForTutorialRuntime() {
    document.documentElement.classList.remove('neko-dragging');
    clearDesktopCompactSurfaceDragPrime();
    desktopCompactSurfaceDragActive = false;
    desktopCompactSurfaceDragTarget = null;
    desktopCompactSurfaceDragWorkArea = null;
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
  }

  function cancelDesktopCompactSurfaceDragForTutorial(reason) {
    var cancelDrag = desktopCompactSurfaceDragCancelForTutorial;
    var cleanupDrag = desktopCompactSurfaceDragCleanupForTutorial;
    desktopCompactSurfaceDragCancelForTutorial = null;
    if (typeof cancelDrag === 'function') {
      cancelDrag(reason || 'tutorial-fixed-layout');
      return;
    }
    desktopCompactSurfaceDragCleanupForTutorial = null;
    if (!desktopCompactSurfaceDragActive) return;
    if (typeof cleanupDrag === 'function') {
      cleanupDrag(reason || 'tutorial-fixed-layout');
    }
    clearDesktopCompactSurfaceDragForTutorialRuntime();
    if (typeof W.dragStop === 'function') {
      try {
        var stopped = W.dragStop({ skipBounceBack: true });
        if (stopped && typeof stopped.catch === 'function') stopped.catch(function () {});
      } catch (_) {}
    }
    scheduleDesktopCompactRelayout(reason || 'tutorial-fixed-layout');
  }

  function clearPendingChatSurfaceModeForTutorialFixedLayout() {
    ePendingChatSurfaceMode = null;
  }

  function readTutorialCompactChatFixedLayoutRunId(detail) {
    return detail && detail.tutorialRunId != null && detail.tutorialRunId !== ''
      ? String(detail.tutorialRunId)
      : '';
  }

  function readTutorialCompactChatFixedLayoutTimestamp(detail) {
    var timestamp = Number(detail && detail.timestamp);
    return Number.isFinite(timestamp) ? timestamp : 0;
  }

  function handleTutorialCompactChatFixedLayoutRelay(detail) {
    if (!detail || typeof detail !== 'object') return;
    var fixed = false;
    var runId = readTutorialCompactChatFixedLayoutRunId(detail);
    var relayTimestamp = readTutorialCompactChatFixedLayoutTimestamp(detail);
    if (detail.action === 'yui_guide_set_compact_chat_fixed_layout') {
      fixed = detail.fixed === true;
    } else if (detail.action !== 'yui_guide_tutorial_lifecycle_ended') {
      return;
    }
    // Repeated fixed=true relays still cancel any in-flight drag before the idempotent state return.
    if (fixed) {
      cancelDesktopCompactSurfaceDragForTutorial('tutorial-compact-chat-fixed-layout');
    }
    if (!fixed && runId && desktopCompactTutorialFixedLayoutRunId && runId !== desktopCompactTutorialFixedLayoutRunId) return;
    if (fixed && runId && desktopCompactTutorialFixedLayoutActive && runId !== desktopCompactTutorialFixedLayoutRunId) {
      if (relayTimestamp && (!desktopCompactTutorialFixedLayoutTimestamp || relayTimestamp >= desktopCompactTutorialFixedLayoutTimestamp)) {
        desktopCompactTutorialFixedLayoutRunId = runId;
        desktopCompactTutorialFixedLayoutTimestamp = relayTimestamp;
      }
    }
    if (desktopCompactTutorialFixedLayoutActive === fixed) return;
    var wasTutorialFixed = desktopCompactTutorialFixedLayoutActive;
    desktopCompactTutorialFixedLayoutActive = fixed;
    desktopCompactTutorialFixedLayoutRunId = fixed ? runId : '';
    desktopCompactTutorialFixedLayoutTimestamp = fixed ? relayTimestamp : 0;
    desktopCompactTutorialFixedSurfaceSize = fixed
      ? captureDesktopCompactTutorialFixedSurfaceSize(desktopCompactLayout && desktopCompactLayout.surfaceScreenRect)
      : null;
    desktopCompactWindowSnapshot = '';
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    if (!fixed && wasTutorialFixed) {
      clearPendingChatSurfaceModeForTutorialFixedLayout();
    }
    scheduleDesktopCompactRelayout('tutorial-compact-chat-fixed-layout');
  }

  window.addEventListener('neko:tutorial-overlay-relay', function (event) {
    handleTutorialCompactChatFixedLayoutRelay(event && event.detail);
  });

  function restoreDesktopCompactWindowIfNeeded() {
    var restoredWindowBounds = null;
    if (desktopCompactWindowActive) {
      var target = loadExpandBounds();
      if (target && !eMinimized && !eBusy) {
        setExpandedReactChatResizable();
        W.setBounds(target.x, target.y, target.width, target.height);
        restoredWindowBounds = target;
      }
    }
    desktopCompactWindowActive = false;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    desktopCompactSurfaceResizeActive = false;
    desktopCompactSurfaceResizeTarget = null;
    clearDesktopCompactSurfaceDragPrime();
    desktopCompactSurfaceDragActive = false;
    desktopCompactSurfaceDragTarget = null;
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    desktopCompactSurfaceDragWorkArea = null;
    if (desktopCompactRelayoutFrame) {
      window.cancelAnimationFrame(desktopCompactRelayoutFrame);
      desktopCompactRelayoutFrame = 0;
    }
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    clearDesktopCompactLayout();
    clearDesktopCompactNativeRegion(restoredWindowBounds);
    hideDesktopCompactBallWindow(); // [compact-ball-removed] no-op 兜底（球已停用）
  }

  function markDesktopCompactWindowRestored() {
    setExpandedReactChatResizable();
    desktopCompactWindowActive = false;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    desktopCompactSurfaceResizeActive = false;
    if (desktopCompactRelayoutFrame) {
      window.cancelAnimationFrame(desktopCompactRelayoutFrame);
      desktopCompactRelayoutFrame = 0;
    }
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    clearDesktopCompactLayout();
    clearDesktopCompactNativeRegion();
    hideDesktopCompactBallWindow(); // [compact-ball-removed] no-op 兜底（球已停用）
  }

  // ---- CSS 注入 ----
  var style = document.createElement('style');
  style.textContent = [
    // On Wayland, ensure the drag handle has the native drag region marker so
    // xdg_toplevel.move is triggered when we skip preventDefault below.
    // Note: Chromium overrides CSS cursor on -webkit-app-region:drag elements;
    // cursor is instead managed via JS mouseenter/mouseleave on html below.
    (_isNativeWayland ? '#react-chat-window-drag-handle, #react-chat-window-drag-handle * { -webkit-app-region: drag; cursor: grab !important; } #reactChatWindowCloseButton, #reactChatWindowCloseButton *, #reactChatWindowMinimizeButton, #reactChatWindowMinimizeButton *, [data-compact-drag-surface="true"], [data-compact-drag-surface="true"] *, [data-compact-no-drag="true"], [data-compact-no-drag="true"] * { -webkit-app-region: no-drag; }' : '#react-chat-window-drag-handle { cursor: grab; }'),
    'html.neko-dragging, html.neko-dragging * { cursor: grabbing !important; }',
    'html.neko-resizing, html.neko-resizing * { cursor: nwse-resize !important; }',
    'html[data-neko-desktop-compact-history-hover="true"] .compact-export-history-anchor .compact-export-history-resize-bar::after {',
    '  opacity: 0.55;',
    '}',
    'html.neko-avatar-tool-native-cursor-hidden,',
    'html.neko-avatar-tool-native-cursor-hidden *,',
    'html.neko-avatar-tool-native-cursor-hidden *::before,',
    'html.neko-avatar-tool-native-cursor-hidden *::after { cursor: none !important; }',
    '.neko-avatar-tool-visual-cursor { position: fixed; left: 0; top: 0; z-index: 2147483600; pointer-events: none; user-select: none; -webkit-user-drag: none; object-fit: contain; transform-origin: 0 0; will-change: transform; }',

    // 动画期间：shell 必须保持 inset:0 填满视口（和最终态一致，消除末帧跳变）。
    // chat.html 对 .is-collapsing/.is-expanding 设了 inset:auto!important (1,1,0)，
    // 用 :not(._) 提升到 (1,3,0) 覆盖之。
    // border:none 清除液态玻璃边框，确保动画期间干净。
    '#react-chat-window-shell.neko-e-animating.is-collapsing:not(._),',
    '#react-chat-window-shell.neko-e-animating.is-expanding:not(._) {',
    '  position: fixed !important;',
    '  inset: 20px !important;',
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
    //       drag-handle 作为可见的 yarn ball 居中显示。
    '#react-chat-window-shell.neko-e-collapsed:not(._):not(._):not(._) {',
    '  width: 100% !important; height: 100% !important;',
    '  max-width: none !important; max-height: none !important;',
    // 关掉 chat.html 里 body.galgame-mode-enabled #shell { min-height:320px !important }。
    // 折叠态 shell 必须严格贴折叠视口，否则 min-height:320 撑高 shell，flex 居中的
    // drag-handle ball 被推到窗口边界外 → 视觉消失 + 没法点。
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
    '#react-chat-window-shell.neko-e-collapsed.neko-e-wayland-self-ball-carrier:not(._):not(._):not(._) {',
    '  display: block !important;',
    '  cursor: default;',
    '}',
    // body 自身的 galgame-mode / composer-has-attachments min-height（chat.html
    // body.galgame-mode-enabled / body.composer-has-attachments 规则）也得关：
    // 折叠到小尺寸时 body min-height:385 会撑出滚动条 + 影响 100vh 定位。
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
    // drag-handle 变成可见的 yarn ball
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle {',
    '  position: relative !important;',
    '  left: auto !important; top: auto !important;',
    '  right: auto !important; bottom: auto !important;',
    '  margin: 0 !important;',
    '  width: ' + BALL_SIZE + 'px; height: ' + BALL_SIZE + 'px; cursor: pointer;',
    '  border-radius: 50%;',
    '  border: none !important;',
    '  outline: none !important;',
    '  background: transparent;',
    '  box-shadow: none;',
    '  animation: none;',
    '  will-change: auto;',
    '  display: flex; align-items: center; justify-content: center;',
    '  flex-shrink: 0;',
    '  transform: translateY(' + BALL_DOWN_OFFSET + 'px);',
    '  -webkit-tap-highlight-color: transparent;',
    '}',
    '#react-chat-window-shell.neko-e-collapsed.neko-e-wayland-self-ball-carrier #react-chat-window-drag-handle {',
    '  position: absolute !important;',
    '  left: var(--neko-wayland-self-ball-handle-left, ' + Math.round((WIN_SIZE - BALL_SIZE) / 2) + 'px) !important;',
    '  top: var(--neko-wayland-self-ball-handle-top, ' + Math.round((WIN_SIZE - BALL_SIZE) / 2) + 'px) !important;',
    '  right: auto !important; bottom: auto !important;',
    '}',
    '#react-chat-window-shell.neko-e-collapsed.neko-e-wayland-self-ball-carrier #react-chat-window-drag-handle,',
    '#react-chat-window-shell.neko-e-collapsed.neko-e-wayland-self-ball-carrier #react-chat-window-drag-handle * {',
    '  -webkit-app-region: no-drag;',
    '}',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle:hover,',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle:focus,',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle:active {',
    '  background: transparent;',
    '  border: none !important;',
    '  outline: none !important;',
    '}',
    '[data-theme="dark"] #react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle {',
    '  background: transparent;',
    '}',
    // 悬浮球图标：折叠态显示（填满 drag handle）
    '#react-chat-window-shell .neko-e-ball-icon { display: none; }',
    '#react-chat-window-shell.neko-e-collapsed .neko-e-ball-icon {',
    '  display: block; width: 100%; height: 100%;',
    '  object-fit: contain;',
    '  image-rendering: auto !important;',
    '  pointer-events: none; user-select: none;',
    '  -webkit-user-drag: none;',
    '  outline: none !important;',
    '}',
    '#react-chat-window-shell .neko-e-ball-click-target { display: none; }',
    '#react-chat-window-shell.neko-e-collapsed #react-chat-window-drag-handle .neko-e-ball-click-target {',
    '  display: block;',
    '  position: absolute;',
    '  left: 50%; top: 50%;',
    '  width: ' + DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_SIZE + 'px;',
    '  height: ' + DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_SIZE + 'px;',
    '  padding: 0; margin: 0;',
    '  transform: translate(-50%, -50%);',
    '  border: 0;',
    '  border-radius: 50%;',
    '  background: transparent;',
    '  box-shadow: none;',
    '  cursor: pointer;',
    '  user-select: none;',
    '  -webkit-user-drag: none;',
    '  -webkit-app-region: no-drag;',
    '  -webkit-tap-highlight-color: transparent;',
    '  z-index: 2;',
    '}',
    '#react-chat-window-shell.neko-e-collapsed.neko-e-wayland-self-ball-carrier #react-chat-window-drag-handle .neko-e-ball-click-target {',
    '  width: 100%;',
    '  height: 100%;',
    '}',
    // 折叠动画期间的球覆盖层（固定在视口左下角，不跟随 shell scale）
    '.neko-e-ball-overlay {',
    '  position: fixed; z-index: 99999;',
    '  pointer-events: none;',
    '  image-rendering: auto !important;',
    '}',
  ].join('\n');
  document.head.appendChild(style);

  // ---- 确保悬浮球图标存在 ----
  function clearWaylandSelfBallClickTargetBlurHandler() {
    if (!desktopCompactWaylandSelfBallBlurCleanup) return;
    try { desktopCompactWaylandSelfBallBlurCleanup(); } catch (_) {}
    desktopCompactWaylandSelfBallBlurCleanup = null;
  }

  function ensureBallIcon() {
    var handle = document.getElementById('react-chat-window-drag-handle');
    if (!handle) return;
    if (!handle.querySelector('.neko-e-ball-icon')) {
      var icon = document.createElement('img');
      icon.className = 'neko-e-ball-icon';
      icon.src = MINIMIZED_BALL_ICON_SRC;
      icon.srcset = MINIMIZED_BALL_ICON_SRCSET;
      icon.alt = '';
      icon.draggable = false;
      handle.appendChild(icon);
    }
    var clickTarget = handle.querySelector('.neko-e-ball-click-target');
    if (_useExternalMinimizedBallWindow || !_isNativeWayland) {
      clearWaylandSelfBallClickTargetBlurHandler();
      if (clickTarget && clickTarget.parentNode) {
        clickTarget.parentNode.removeChild(clickTarget);
      }
      return;
    }
    if (!clickTarget) {
      clearWaylandSelfBallClickTargetBlurHandler();
      clickTarget = document.createElement('span');
      clickTarget.className = 'neko-e-ball-click-target';
      clickTarget.setAttribute('aria-hidden', 'true');
      clickTarget.setAttribute('data-wayland-self-ball-click-target', 'true');
      clickTarget.setAttribute('data-compact-no-drag', 'true');
      handle.appendChild(clickTarget);
    }
    if (clickTarget.__nekoWaylandSelfBallClickBound) {
      return;
    }
    clickTarget.__nekoWaylandSelfBallClickBound = true;
    var pointerStart = null;
    var restoredFromPointerAt = 0;
    var draggedFromPointerAt = 0;
    var isSameWaylandSelfBallPointer = function (event, start) {
      if (!event || !start || start.pointerId === null) return true;
      return Number(event.pointerId) === start.pointerId;
    };
    var releaseWaylandSelfBallPointerCapture = function (event, start) {
      if (!event || !start || start.pointerId === null) return;
      if (typeof clickTarget.releasePointerCapture !== 'function') return;
      try { clickTarget.releasePointerCapture(start.pointerId); } catch (_) {}
    };
    var updateWaylandSelfBallVirtualDrag = function (event, start, reason) {
      if (!start || !start.anchor) return null;
      var dx = event.clientX - start.x;
      var dy = event.clientY - start.y;
      var moved = Math.hypot(dx, dy) > DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_MOVE_PX;
      if (!moved && !start.moved) return null;
      start.moved = true;
      document.documentElement.classList.add('neko-dragging');
      return setDesktopCompactWaylandSelfBallAnchorBounds({
        x: start.anchor.x + dx,
        y: start.anchor.y + dy
      }, null, reason || 'self-ball-wayland-virtual-drag');
    };
    var restoreWaylandSelfBallPointerShape = function (start, reason) {
      var anchor = getDesktopCompactWaylandSelfBallAnchorBounds()
        || (start && start.anchor);
      if (!anchor) return;
      sendDesktopCompactWaylandSelfBallShape(
        reason || 'self-ball-wayland-virtual-drag-release',
        anchor,
        (start && start.carrier) || desktopCompactWaylandSelfBallCarrierBounds
      );
    };
    clickTarget.addEventListener('pointerdown', function (event) {
      if (event.button !== undefined && event.button !== 0) return;
      var pointerId = Number(event.pointerId);
      pointerStart = {
        x: event.clientX,
        y: event.clientY,
        pointerId: Number.isFinite(pointerId) ? pointerId : null,
        anchor: getDesktopCompactWaylandSelfBallAnchorBounds(),
        carrier: getDesktopCompactWaylandSelfBallCarrierBounds(),
        moved: false
      };
      sendDesktopCompactWaylandFullWindowShape('self-ball-wayland-virtual-drag-prime', pointerStart.carrier);
      if (pointerStart.pointerId !== null && typeof clickTarget.setPointerCapture === 'function') {
        try { clickTarget.setPointerCapture(pointerStart.pointerId); } catch (_) {}
      }
      event.stopPropagation();
      event.preventDefault();
    }, true);
    clickTarget.addEventListener('pointermove', function (event) {
      var start = pointerStart;
      if (!start || !isSameWaylandSelfBallPointer(event, start)) return;
      var updatedAnchor = updateWaylandSelfBallVirtualDrag(event, start, 'self-ball-wayland-virtual-drag-move');
      if (updatedAnchor) {
        scheduleSelfWindowMinimizedBallState('self-ball-wayland-virtual-drag-move');
      }
      event.stopPropagation();
      event.preventDefault();
    }, true);
    clickTarget.addEventListener('pointerup', function (event) {
      if (event.button !== undefined && event.button !== 0) return;
      var start = pointerStart;
      if (start && !isSameWaylandSelfBallPointer(event, start)) return;
      pointerStart = null;
      releaseWaylandSelfBallPointerCapture(event, start);
      document.documentElement.classList.remove('neko-dragging');
      event.stopPropagation();
      event.preventDefault();
      if (!start) return;
      var dx = event.clientX - start.x;
      var dy = event.clientY - start.y;
      if (Math.hypot(dx, dy) > DESKTOP_COMPACT_WAYLAND_BALL_CLICK_TARGET_MOVE_PX || start.moved) {
        if (start.anchor) {
          updateWaylandSelfBallVirtualDrag(event, start, 'self-ball-wayland-virtual-drag-stop');
          scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-virtual-drag-stop');
        }
        draggedFromPointerAt = Date.now();
        return;
      }
      restoreWaylandSelfBallPointerShape(start, 'self-ball-wayland-virtual-drag-click-release');
      if (restoreWaylandSelfBallFromClick('self-ball-click-target-pointerup')) {
        restoredFromPointerAt = Date.now();
      }
    }, true);
    clickTarget.addEventListener('pointercancel', function (event) {
      var start = pointerStart;
      pointerStart = null;
      releaseWaylandSelfBallPointerCapture(event, start);
      document.documentElement.classList.remove('neko-dragging');
      if (start && start.anchor && start.moved) {
        draggedFromPointerAt = Date.now();
        scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-virtual-drag-cancel');
      }
      restoreWaylandSelfBallPointerShape(start, 'self-ball-wayland-virtual-drag-cancel');
      event.stopPropagation();
    }, true);
    var onWaylandSelfBallBlur = function () {
      var start = pointerStart;
      if (!start) return;
      pointerStart = null;
      document.documentElement.classList.remove('neko-dragging');
      if (start.anchor && start.moved) {
        draggedFromPointerAt = Date.now();
        scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-virtual-drag-blur');
      }
      restoreWaylandSelfBallPointerShape(start, 'self-ball-wayland-virtual-drag-blur');
    };
    window.addEventListener('blur', onWaylandSelfBallBlur);
    desktopCompactWaylandSelfBallBlurCleanup = function () {
      window.removeEventListener('blur', onWaylandSelfBallBlur);
    };
    clickTarget.addEventListener('click', function (event) {
      event.stopPropagation();
      event.preventDefault();
      if (Date.now() - restoredFromPointerAt < 400) return;
      if (Date.now() - draggedFromPointerAt < 400) return;
      restoreWaylandSelfBallFromClick('self-ball-click-target-click');
    }, true);
  }

  function clearReactCompactShellVisibilityGuards(shell) {
    if (!shell) return false;
    shell.style.removeProperty('opacity');
    var ballIconInShell = shell.querySelector('.neko-e-ball-icon');
    if (ballIconInShell) ballIconInShell.style.opacity = '';
    return true;
  }

  function applyReactCollapsedSelfBallNativeRegion() {
    if (_useExternalMinimizedBallWindow) return;
    if (_isNativeWayland) {
      desktopCompactNativeRegionSnapshot = '';
      clearDesktopCompactPendingNativeRegion();
      if (desktopCompactHasSetShape) {
        var waylandSelfBallAnchor = getDesktopCompactWaylandSelfBallAnchorBounds();
        if (waylandSelfBallAnchor) {
          sendDesktopCompactWaylandSelfBallShape(
            'self-ball-collapsed',
            waylandSelfBallAnchor,
            desktopCompactWaylandSelfBallCarrierBounds
          );
        } else {
          sendDesktopCompactWaylandFullWindowShape('self-ball-collapsed');
        }
      }
      setDesktopCompactHistoryPointerPassthrough(false);
      ipcRenderer.send('set-ignore-mouse-events', false);
      return;
    }
    if (!desktopCompactCanApplyNativeInputRegion) return;
    desktopCompactNativeRegionSnapshot = '';
    clearDesktopCompactPendingNativeRegion();
    if (desktopCompactHasSetShape) {
      sendDesktopCompactFullWindowSetShape('self-ball-collapsed');
    } else if (desktopCompactUseX11InputShape) {
      sendDesktopCompactFullWindowInputRegion('self-ball-collapsed');
    }
    setDesktopCompactHistoryPointerPassthrough(false);
    ipcRenderer.send('set-ignore-mouse-events', false);
  }

  function prepareReactCollapsedShell(shell) {
    if (!shell) return false;
    ensureBallIcon();
    shell.classList.add('neko-e-collapsed');
    shell.classList.remove('is-collapsing', 'is-expanding', 'is-minimized', 'neko-e-animating');
    clearReactCompactShellVisibilityGuards(shell);
    shell.style.removeProperty('transform');
    shell.style.removeProperty('transform-origin');
    applyReactCollapsedSelfBallNativeRegion();
    return true;
  }

  function freezeDesktopCompactForCollapse() {
    eMinimized = true;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    if (desktopCompactRelayoutFrame) {
      window.cancelAnimationFrame(desktopCompactRelayoutFrame);
      desktopCompactRelayoutFrame = 0;
    }
    hideDesktopCompactBallWindow(); // [compact-ball-removed] no-op 兜底（球已停用）
  }

  function finishDesktopCompactCollapse() {
    desktopCompactWindowActive = false;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    clearDesktopCompactLayout();
    clearDesktopCompactNativeRegion();
  }

  function resetDesktopCompactRestoreState() {
    desktopCompactWindowActive = false;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    desktopCompactSurfaceResizeActive = false;
    desktopCompactSurfaceResizeTarget = null;
    desktopCompactSurfaceResizeSide = null;
    desktopCompactSurfaceResizeStartTarget = null;
    desktopCompactSurfaceDragActive = false;
    desktopCompactSurfaceDragTarget = null;
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    desktopCompactSurfaceDragWorkArea = null;
    if (desktopCompactRelayoutFrame) {
      window.cancelAnimationFrame(desktopCompactRelayoutFrame);
      desktopCompactRelayoutFrame = 0;
    }
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    clearDesktopCompactLayout();
    clearDesktopCompactNativeRegion();
  }

  function prepareReactCompactShellAfterDirectRestore(shell, options) {
    if (!shell) return false;
    shell.classList.remove('neko-e-collapsed', 'is-collapsing', 'is-expanding', 'is-minimized', 'neko-e-animating');
    if (!(options && options.keepHidden)) {
      clearReactCompactShellVisibilityGuards(shell);
    }
    shell.style.removeProperty('transform');
    shell.style.removeProperty('transform-origin');
    return true;
  }

  function hideReactCollapsedShellBeforeDirectRestore(shell) {
    if (!shell) return false;
    shell.style.opacity = '0';
    var ballIconInShell = shell.querySelector('.neko-e-ball-icon');
    if (ballIconInShell) ballIconInShell.style.opacity = '0';
    return true;
  }

  function waitForDirectRestoreQuietFrame() {
    return new Promise(function (resolve) {
      window.requestAnimationFrame(function () {
        window.setTimeout(resolve, 32);
      });
    });
  }

  function buildDesktopCompactDirectRestoreLayout(bounds, workArea, surfaceSize) {
    return buildDesktopCompactWindowLayout(bounds, workArea, desktopCompactAvatarPayload, {
      storedSurfaceOnly: true,
      storedSurfaceSize: surfaceSize || null
    });
  }

  // 折叠前抓取 compact 对话条 surface 在屏幕上的真实位置 —— 这才是用户视觉看到的对话条。
  // 直接用 win.getBounds() 的 windowBounds 在 desktop compact 模式下是窗口覆盖的大区域
  // （avatar 周边一大圈），surface 只是其中一小块。必须在 W.collapse 前抓：collapse 后
  // layout 已 freeze/重置，从 __nekoDesktopCompactLayout 读不到了。
  function captureDesktopCompactSurfaceScreenRectBeforeCollapse() {
    try {
      var layoutForBall = window.__nekoDesktopCompactLayout;
      if (layoutForBall && layoutForBall.surfaceScreenRect) {
        var ssr = layoutForBall.surfaceScreenRect;
        var sLeft = Number(ssr.left);
        var sTop = Number(ssr.top);
        var sWidth = Number(ssr.width);
        var sHeight = Number(ssr.height);
        if (Number.isFinite(sLeft) && Number.isFinite(sTop) && Number.isFinite(sWidth) && Number.isFinite(sHeight) && sWidth > 0 && sHeight > 0) {
          return {
            x: Math.round(sLeft),
            y: Math.round(sTop),
            width: Math.round(sWidth),
            height: Math.round(sHeight)
          };
        }
      }
    } catch (_) {}
    return null;
  }

  // 对偶记录：carrier 锚点（W.collapse 实际落点，目标缺失时主进程用折叠前 bounds 做左下角
  // 对齐）相对折叠前 surface 的差量。每条会设 eMinimized 的折叠路径（毛线球
  // collapseNativeForReactMinimized / idleDockCollapse）都必须在 W.collapse resolve 后调用，
  // 把差量绑定到「当前这次折叠」—— 否则上一轮折叠的差量会泄漏给下一轮不同路径/不同
  // surface 几何的恢复（Codex P2）。现场信息不足时记 null，恢复端退回近似公式。
  function recordMinimizedBallSurfaceRestoreDelta(surfaceScreenRect, collapseTargetBounds, preCollapseBounds) {
    var carrierAnchor = collapseTargetBounds || (preCollapseBounds ? {
      x: preCollapseBounds.x,
      y: preCollapseBounds.y + preCollapseBounds.height - WIN_SIZE
    } : null);
    _minimizedBallSurfaceRestoreDelta = (surfaceScreenRect && carrierAnchor
      && Number.isFinite(Number(carrierAnchor.x))
      && Number.isFinite(Number(carrierAnchor.y)))
      ? {
          dx: Math.round(surfaceScreenRect.x - Number(carrierAnchor.x)),
          dy: Math.round(surfaceScreenRect.y - Number(carrierAnchor.y))
        }
      : null;
  }

  // 毛线球 88px anchor → stored surface 的统一逆变换（直接恢复与 doExpand 共用，保持两条
  // 恢复路径对偶）。优先用折叠瞬间记录的实测差量 _minimizedBallSurfaceRestoreDelta —— 它与
  // 按钮中心折叠落点严格互逆，surface 高度变化（galgame/附件 385/495px）也不影响精度；
  // 差量缺失时退回旧的「球左下角 = surface 左下角」近似（anchor.y + WIN_SIZE - surfaceH）。
  function buildDesktopCompactSurfaceRectFromMinimizedBallAnchor(anchor) {
    var anchorX = Number(anchor && anchor.x);
    var anchorY = Number(anchor && anchor.y);
    if (!Number.isFinite(anchorX) || !Number.isFinite(anchorY)) return null;
    var sfH = (_lastLayoutForRestore && _lastLayoutForRestore.surface && Number(_lastLayoutForRestore.surface.height))
      || DESKTOP_COMPACT_SURFACE_DEFAULT_HEIGHT;
    var sfW = (_lastLayoutForRestore && _lastLayoutForRestore.surface && Number(_lastLayoutForRestore.surface.width)) || 430;
    var delta = _minimizedBallSurfaceRestoreDelta;
    return {
      left: Math.round(delta ? anchorX + delta.dx : anchorX),
      top: Math.round(delta ? anchorY + delta.dy : anchorY + WIN_SIZE - sfH),
      width: Math.round(sfW),
      height: Math.round(sfH)
    };
  }

  function markDesktopCompactDirectRestoreApplied(layout, skipBallHide) {
    if (!layout || !layout.windowBounds) return false;
    var target = layout.windowBounds;
    desktopCompactWindowActive = true;
    desktopCompactWindowSnapshot = [
      target.x,
      target.y,
      target.width,
      target.height,
      layout.surface && Math.round(layout.surface.left),
      layout.surface && Math.round(layout.surface.top),
      layout.surface && Math.round(layout.surface.width)
    ].join(':');
    desktopCompactPendingWindowBounds = target;
    W.setResizable(false);
    W.setBounds(target.x, target.y, target.width, target.height);
    applyDesktopCompactLayoutToPage(layout);
    applyDesktopCompactNativeRegion(layout);
    syncDesktopCompactHistoryPointerPassthroughWithCursor(layout);
    // [compact-ball-removed] showDesktopCompactBallWindow 现仅发 HIDE（球已停用，ballScreenRect 恒 null）。
    // 但毛线球 CLICK 直接恢复（skipBallHide）下，这条提前的 HIDE 会在揭示完成前就销毁正在 bounce 的
    // 独立球（Win32 上 HIDE = destroy），让 skipBallHide「球弹完 bounce + RESTORE_ACK 自隐」失效、
    // 球过早消失 → 球与对话框揭示之间出现空白（Codex P2）。skipBallHide 时跳过这条 HIDE，让球存活到
    // RESTORE_COMPLETE→RESTORE_ACK 由球自隐，覆盖揭示间隙（用户已许可球与对话框短暂重叠）。
    if (!skipBallHide) {
      showDesktopCompactBallWindow(layout);
    }
    if (typeof W.bringToFront === 'function') {
      W.bringToFront();
    }
    raiseDesktopCompactBallWindow(); // [compact-ball-removed] no-op（球已停用）
    return true;
  }

  // 揭示前等 surface 的「屏幕位置」连续稳定若干帧再 opacity→1。根因：恢复时窗口 setBounds 与
  // surface 变量 rebase 都异步落定，若在它们还在动时就揭示，Win32 层窗口会在 opacity 翻 1 那刻
  // 顶出「仍在移动中」的中转帧 = 输入框瞬移。量屏幕坐标(window.screenX/Y + 视口偏移)：窗口移动
  // 或变量切换都能覆盖。超时仍揭示，绝不卡死。
  function waitForDesktopCompactSurfaceStableBeforeReveal(opts) {
    var o = opts || {};
    var needStable = Math.max(2, Math.round(Number(o.stableFrames) || 2));
    var maxFrames = Math.max(needStable + 1, Math.round(Number(o.maxFrames) || 30));
    return new Promise(function (resolve) {
      var last = null;
      var stable = 0;
      var frames = 0;
      function readSurfaceScreenRect() {
        var surface = document.querySelector('.compact-chat-surface-shell');
        if (!surface) return null;
        var r = surface.getBoundingClientRect();
        if (!r || !(r.width > 0)) return null;
        var wx = (typeof window.screenX === 'number') ? window.screenX : 0;
        var wy = (typeof window.screenY === 'number') ? window.screenY : 0;
        return {
          left: Math.round(wx + r.left),
          top: Math.round(wy + r.top),
          width: Math.round(r.width),
          height: Math.round(r.height)
        };
      }
      function step() {
        if (eMinimized || isReactChatWindowHidden() || getCurrentReactChatSurfaceMode() !== 'compact') {
          resolve(false);
          return;
        }
        var cur = readSurfaceScreenRect();
        if (cur && last
          && cur.left === last.left && cur.top === last.top
          && cur.width === last.width && cur.height === last.height) {
          stable += 1;
        } else {
          stable = cur ? 1 : 0;
        }
        last = cur;
        frames += 1;
        if (stable >= needStable) { resolve(true); return; }
        if (frames >= maxFrames) { resolve(false); return; }
        window.requestAnimationFrame(step);
      }
      window.requestAnimationFrame(step);
    });
  }

  function restoreCompactDesktopFromMinimized(options) {
    // skipBallHide：毛线球 CLICK 路径专用 —— 不在揭示时强制 HIDE 球，改由球自身
    // 「bounce 完 + RESTORE_ACK」握手自隐（maybeHideBall），与原 doExpand 球路径的并发
    // bounce 行为一致；非球路径（F6/focus）默认 false，仍直接 HIDE 收掉可能残留的球。
    var skipBallHide = !!(options && options.skipBallHide);
    var restoreAnchorBounds = normalizeCollapsedBounds(options && options.anchorBounds)
      || getDesktopCompactWaylandSelfBallAnchorBounds();
    if (isSurfaceActionLocked()) {
      requestChatSurfaceMode('compact');
      return Promise.resolve('queued');
    }
    if (!eMinimized) return Promise.resolve(false);
    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) return Promise.resolve(false);
    var transitionToken = beginSurfaceTransition('restoring');
    eBusy = true;
    eHiddenByClose = false;
    setDesktopCompactAvatarBoundsSubscription(true);
    resetDesktopCompactRestoreState();
    hideReactCollapsedShellBeforeDirectRestore(shell);
    return Promise.all([
      W.getBounds().catch(function () { return null; }),
      W.getWorkArea().catch(function () { return null; })
    ]).then(function (values) {
      var actualBounds = normalizeWindowBounds(values[0]);
      var workArea = values[1];
      var shouldTrustPayloadAnchor = !!restoreAnchorBounds
        && (process.platform === 'darwin' || !_useExternalMinimizedBallWindow);
      var anchorBoundsForRestore = shouldTrustPayloadAnchor ? restoreAnchorBounds : actualBounds;
      // 球态时 Win32 的 chatWin 会被 DRAG_MOVE 同步到球当前位置（WIN_SIZE 折叠 bounds）。macOS
      // 上 opacity-0 carrier 的 setBounds 可能滞后/不跟随可见球，因此毛线球 CLICK 直接恢复必须
      // 优先信任 main 从独立球窗口读取的 anchorBounds；Windows 继续使用 actualBounds，避免改变
      // 既有的 carrier/可见球 3px 视觉微调。
      // （F6/toggle/focus）走 buildDesktopCompactDirectRestoreLayout(storedSurfaceOnly)，读的是
      // stale 的 stored surface（拖动不更新它）→ 拖了球再按 F6 会落回拖动前的位置。这里用
      // anchorBoundsForRestore（=球当前 anchor）经折叠差量逆变换刷新 stored surface（与点球
      // 恢复 doExpand 同一套推导），让直接恢复落回折叠前的精确位置（球被拖过则跟随平移）。
      // eMinimized 必经 collapseNativeForReactMinimized，actualBounds 一定是球的同步位置；
      // macOS 则由 payload anchor 纠偏。
      var restoreSurfaceSize = null;
      if (anchorBoundsForRestore && _lastLayoutForRestore && _lastLayoutForRestore.surface) {
        var restoredSurfaceRect = buildDesktopCompactSurfaceRectFromMinimizedBallAnchor(anchorBoundsForRestore);
        if (restoredSurfaceRect) {
          saveDesktopCompactSurfacePosition(restoredSurfaceRect);
        }
        // 折叠瞬间抓到的真实 surface 宽高 —— 传给 storedSurfaceOnly 布局还原用户拉过的宽度，
        // 否则直接恢复会退回 fallback 默认宽，每次点球展开都把宽度复位（本次修复的核心）。
        if (Number(_lastLayoutForRestore.surface.width) > 0 && Number(_lastLayoutForRestore.surface.height) > 0) {
          restoreSurfaceSize = {
            width: _lastLayoutForRestore.surface.width,
            height: _lastLayoutForRestore.surface.height
          };
        }
      }
      var layout = buildDesktopCompactDirectRestoreLayout(anchorBoundsForRestore, workArea, restoreSurfaceSize);
      if (!layout || !layout.windowBounds) throw new Error('compact direct restore layout unavailable');
      return waitForDirectRestoreQuietFrame().then(function () {
        markDesktopCompactDirectRestoreApplied(layout, skipBallHide);
        // eMinimized 先清除：waitForDesktopCompactBoundsBeforeReveal 和
        // waitForDesktopCompactSurfaceStableBeforeReveal 的首行 guard 都检查
        // eMinimized，保持 true 会让它们立即 resolve(false) 跳过实际等待。
        // eBusy 保持 true 到外层 .then 统一释放，配合 transition lock（'restoring'）
        // 挡住 collapseNativeForReactMinimized 重入（其 guard isSurfaceActionBlocked()
        // 同时检查 transition 态与 eBusy）。
        eMinimized = false;
        setReactChatSurfaceMode('compact', { force: true });
        scheduleElectronChatMinimizedState('direct-restore');
        prepareReactCompactShellAfterDirectRestore(shell, {
          keepHidden: !_useExternalMinimizedBallWindow
        });
        clearExpandBounds();
        idleDockSavedSurfaceMode = null;
        // 经非毛线球路径（F6/toggle、focus 热键）直接恢复时，chatWin 仍停在折叠时
        // PRE_COLLAPSE_DIM 设的 opacity 0，且独立球还显示着。这里复位 opacity（RESTORE_COMPLETE
        // → main setOpacity(1)，幂等）并在 direct restore 场景收掉独立球，否则恢复出的对话框隐身 + 球残留。
        // 毛线球 CLICK 路径（skipBallHide）则不强制 HIDE：RESTORE_COMPLETE → main 回 RESTORE_ACK，
        // 球弹完 bounce 收到 ACK 后自隐，保留并发 bounce 体验、不打断动画。
        return waitForDesktopCompactBoundsBeforeReveal(layout.windowBounds, {
          timeoutMs: 1200,
          intervalMs: 32
        }).then(function (boundsReady) {
          if (!boundsReady) {
            throw new Error('compact direct restore bounds did not settle before reveal');
          }
          // 窗口 bounds 已到位，但 surface 变量 rebase 可能正好此刻才落定 → 再等屏幕位置稳定
          // 若干帧才揭示，确保 opacity 翻 1 那刻层窗口缓冲已是最终位置、无中转帧瞬移。
          return waitForDesktopCompactSurfaceStableBeforeReveal({ stableFrames: 2, maxFrames: 30 }).then(function () {
            // 揭示等待（bounds + 屏幕位置稳定）这段空窗里 eMinimized 已提前清掉，但 eBusy
            // 与 transition lock（'restoring'）保持到外层 .then 统一释放，期间
            // react-chat-window:chat-surface-mode-change 等外部 minimize 请求会被
            // requestChatSurfaceMode 排队、不会重入 collapseNativeForReactMinimized()。
            // 这里仍重验「取消态」（恢复期间窗口被隐藏，如 F8 hide-all）；注意不能用
            // 稳定检查的返回值判断，因为它在「慢但合法」的 maxFrames 超时时也 resolve
            // false，那种情况仍需正常揭示，否则会把慢速恢复误卡在 opacity 0 = 对话框隐身。
            // 返回 'canceled'（truthy 哨兵）而非 false，与 catch 分支的「可恢复失败」(return false)
            // 区分：caller 把 false 当布局失败 → 回退 doExpand，但取消场景回退会把刚重新最小化的态
            // 又强行展开撤销（Codex P2）。'canceled' 让 caller 不回退、保留最小化态。
            if (eMinimized || isReactChatWindowHidden()) {
              eBusy = false;
              endSurfaceTransition(transitionToken);
              return 'canceled';
            }
            // #2 展开方向性 reveal 已改由 App.tsx 的 compactExpanding state 驱动（监听 minimized→compact），
            // 不再在此用 classList 加类（会被 React 重渲染覆盖 → 偶发"展开销毁闪一下"）。
            try {
              sendDesktopCompactWaylandFullWindowShape('direct-restore-reveal', layout.windowBounds);
              if (skipBallHide) {
                emitCompactChatRestoreComplete();
              } else {
                emitCompactChatRestoreComplete({
                  hideBall: true,
                  reason: 'direct-restore'
                });
              }
            } catch (_) {}
            window.requestAnimationFrame(function () {
              scheduleDesktopCompactRelayout();
            });
            return true;
          });
        });
      });
    }).then(function (restored) {
      eBusy = false;
      endSurfaceTransition(transitionToken);
      flushPendingChatSurfaceMode();
      return restored;
    }).catch(function (err) {
      console.warn('[Preload-Chat][compact-restore] direct restore failed:', err);
      eBusy = false;
      eMinimized = true;
      prepareReactCollapsedShell(shell);
      setReactChatSurfaceMode('minimized', { force: true });
      endSurfaceTransition(transitionToken);
      flushPendingChatSurfaceMode();
      return false;
    });
  }

  function restoreCompactDesktopFromMinimizedOrExpand(options, onRestored) {
    if (typeof options === 'function') {
      onRestored = options;
      options = {};
    }
    options = options || {};
    if (isSurfaceActionLocked()) {
      requestChatSurfaceMode('compact');
      return false;
    }
    if (!eMinimized) return false;
    restoreCompactDesktopFromMinimized(options).then(function (restored) {
      if (restored === true) {
        if (typeof onRestored === 'function') onRestored();
        return;
      }
      // 'canceled'：揭示期间被重新折叠，最小化态应保留，不回退展开（Codex P2）。
      if (restored === 'canceled' || restored === 'queued') return;
      var fallbackAnchor = normalizeCollapsedBounds(options.anchorBounds);
      if (fallbackAnchor) {
        _ballAnchorBoundsBeforeExpand = fallbackAnchor;
        doExpand({ suppressOnfinishRelayout: true });
      } else {
        doExpand();
      }
    });
    return true;
  }

  function restoreIdleDockSurfaceModeIfNeeded() {
    var mode = idleDockSavedSurfaceMode;
    idleDockSavedSurfaceMode = null;
    if (!mode || getCurrentReactChatSurfaceMode() !== 'minimized' || isSurfaceActionLocked()) return;
    setReactChatSurfaceMode(mode);
  }

  function getReactChatHost() {
    return window.reactChatWindowHost || null;
  }

  function setReactChatSurfaceMode(mode, options) {
    options = options || {};
    if (mode === 'full') mode = 'compact';
    if (!options.force && isSurfaceActionBlocked()) {
      return false;
    }
    var host = getReactChatHost();
    if (!host || typeof host.setChatSurfaceMode !== 'function') return false;
    try {
      host.setChatSurfaceMode(mode);
      return true;
    } catch (err) {
      console.warn('[Preload-Chat] setChatSurfaceMode failed:', err);
      return false;
    }
  }

  function requestChatSurfaceMode(mode) {
    if (mode === 'full') mode = 'compact';
    if (mode !== 'compact' && mode !== 'minimized') return;
    if (isSurfaceActionLocked()) {
      if (ePendingChatSurfaceMode !== mode) {
        ePendingChatSurfaceMode = mode;
      }
      return;
    }
    if (mode === 'compact' && !eMinimized) return;
    if (mode === 'minimized' && eMinimized) return;
    if (ePendingChatSurfaceMode === mode) {
      return;
    }
    ePendingChatSurfaceMode = mode;
    flushPendingChatSurfaceMode();
  }

  var pendingWaylandSelfBallClickRestore = null;

  function clearPendingWaylandSelfBallClickRestore() {
    if (!pendingWaylandSelfBallClickRestore) return;
    if (pendingWaylandSelfBallClickRestore.timer) {
      window.clearTimeout(pendingWaylandSelfBallClickRestore.timer);
    }
    pendingWaylandSelfBallClickRestore = null;
  }

  function restoreWaylandSelfBallFromClick(reason) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland || !eMinimized) {
      clearPendingWaylandSelfBallClickRestore();
      return false;
    }
    requestCompactInputState();
    if (isSurfaceActionLocked()) {
      requestChatSurfaceMode('compact');
      queueWaylandSelfBallClickRestore(reason || 'locked');
      return true;
    }
    clearPendingWaylandSelfBallClickRestore();
    var expandWithCurrentBallAnchor = function (anchorBounds) {
      _ballAnchorBoundsBeforeExpand = normalizeCollapsedBounds(anchorBounds) || _ballAnchorBoundsBeforeExpand;
      doExpand({ suppressOnfinishRelayout: true });
    };
    getCurrentSelfBallAnchorBounds().then(function (anchorBounds) {
      if (anchorBounds) _ballAnchorBoundsBeforeExpand = anchorBounds;
      return restoreCompactDesktopFromMinimized({
        anchorBounds: anchorBounds
      }).then(function (restored) {
        if (restored === true || restored === 'queued' || restored === 'canceled') return;
        expandWithCurrentBallAnchor(anchorBounds);
      });
    }).catch(function () {
      expandWithCurrentBallAnchor(null);
    });
    setTimeout(function () {
      focusComposerInputFromHotkey({ retry: true });
    }, 260);
    setTimeout(function () {
      focusComposerInputFromHotkey({ retry: false });
    }, 760);
    return true;
  }

  function restoreWaylandSelfBallFromProgrammaticRequest(reason) {
    return restoreWaylandSelfBallFromClick(reason);
  }

  function isWaylandSelfBallEventTarget(target) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland || !eMinimized) return false;
    var shell = document.getElementById('react-chat-window-shell');
    var handle = document.getElementById('react-chat-window-drag-handle');
    var node = target && target.nodeType === 3 ? target.parentNode : target;
    return !!(shell && handle && shell.classList.contains('neko-e-collapsed') &&
      node && (node === handle || (handle.contains && handle.contains(node))));
  }

  function isWaylandSelfBallClickTarget(target) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland || !eMinimized) return false;
    var shell = document.getElementById('react-chat-window-shell');
    var handle = document.getElementById('react-chat-window-drag-handle');
    var node = target && target.nodeType === 3 ? target.parentNode : target;
    var clickTarget = node && node.closest ? node.closest('.neko-e-ball-click-target') : null;
    return !!(shell && handle && shell.classList.contains('neko-e-collapsed') &&
      clickTarget && handle.contains && handle.contains(clickTarget));
  }

  function queueWaylandSelfBallRestoreFromBlockedEvent(event) {
    if (!event || event.type === 'dblclick') return false;
    if (!isWaylandSelfBallEventTarget(event.target || event.srcElement)) return false;
    return restoreWaylandSelfBallFromClick('self-ball-blocked-' + event.type);
  }

  function queueWaylandSelfBallClickRestore(reason) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland || !eMinimized) return;
    if (!pendingWaylandSelfBallClickRestore) {
      pendingWaylandSelfBallClickRestore = {
        attempts: 0,
        reason: reason || 'pending',
        timer: 0
      };
    } else {
      pendingWaylandSelfBallClickRestore.reason = reason || pendingWaylandSelfBallClickRestore.reason;
    }
    schedulePendingWaylandSelfBallClickRestore(reason);
  }

  function schedulePendingWaylandSelfBallClickRestore(reason) {
    if (_useExternalMinimizedBallWindow || !_isNativeWayland || !eMinimized) {
      clearPendingWaylandSelfBallClickRestore();
      return;
    }
    if (!pendingWaylandSelfBallClickRestore) return;
    pendingWaylandSelfBallClickRestore.reason = reason || pendingWaylandSelfBallClickRestore.reason;
    if (pendingWaylandSelfBallClickRestore.timer) return;
    var delay = DESKTOP_COMPACT_WAYLAND_BALL_RESTORE_RETRY_DELAYS[
      Math.min(
        pendingWaylandSelfBallClickRestore.attempts,
        DESKTOP_COMPACT_WAYLAND_BALL_RESTORE_RETRY_DELAYS.length - 1
      )
    ];
    pendingWaylandSelfBallClickRestore.timer = window.setTimeout(function () {
      if (!pendingWaylandSelfBallClickRestore) return;
      pendingWaylandSelfBallClickRestore.timer = 0;
      pendingWaylandSelfBallClickRestore.attempts += 1;
      if (!_useExternalMinimizedBallWindow && _isNativeWayland && eMinimized) {
        restoreWaylandSelfBallFromProgrammaticRequest(pendingWaylandSelfBallClickRestore.reason || 'retry');
      } else {
        clearPendingWaylandSelfBallClickRestore();
      }
    }, delay);
  }

  function emitCompactChatRestoreComplete(payload) {
    clearReactCompactShellVisibilityGuards(document.getElementById('react-chat-window-shell'));
    var safePayload = {};
    if (payload && typeof payload === 'object') {
      var payloadKey;
      for (payloadKey in payload) {
        safePayload[payloadKey] = payload[payloadKey];
      }
    }
    eCompactChatRestoreSequence += 1;
    safePayload.__compactChatRestoreSession = eCompactChatRestoreSession;
    safePayload.__compactChatRestoreSeq = eCompactChatRestoreSequence;
    try {
      ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.RESTORE_COMPLETE, safePayload);
    } catch (_) {}
    return eCompactChatRestoreSequence;
  }

  function emitCompactChatPreCollapseSeq() {
    try {
      eCompactChatRestoreSequence += 1;
      ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.PRE_COLLAPSE_DIM, {
        __compactChatRestoreSession: eCompactChatRestoreSession,
        __compactChatRestoreSeq: eCompactChatRestoreSequence
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  function flushPendingChatSurfaceMode() {
    if (isSurfaceActionLocked() || !ePendingChatSurfaceMode) return;
    var targetMode = ePendingChatSurfaceMode;
    ePendingChatSurfaceMode = null;
    if (targetMode === 'minimized') {
      if (!eMinimized) {
        collapseNativeForReactMinimized();
      }
      return;
    }
    if (targetMode === 'compact' && eMinimized) {
      getCurrentSelfBallAnchorBounds().then(function (anchorBounds) {
        if (!eMinimized) return;
        restoreCompactDesktopFromMinimizedOrExpand({
          anchorBounds: anchorBounds
        });
      }).catch(function () {
        restoreCompactDesktopFromMinimizedOrExpand();
      });
    }
  }

  function buildLegacyFullBallBounds(bounds) {
    var normalized = normalizeWindowBounds(bounds);
    if (!normalized) return null;
    return {
      x: Math.round(normalized.x - 3),
      y: Math.round(normalized.y + normalized.height - WIN_SIZE + 4),
      width: WIN_SIZE,
      height: WIN_SIZE
    };
  }

  function cleanupLegacyFullCollapseVisual(shell, overlay, anim, ballAnim) {
    if (anim) {
      try { anim.cancel(); } catch (_) {}
    }
    if (ballAnim) {
      try { ballAnim.cancel(); } catch (_) {}
    }
    if (overlay && overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
    if (shell) {
      shell.classList.remove('is-collapsing', 'neko-e-animating');
      shell.style.removeProperty('transform-origin');
      shell.style.removeProperty('transform');
    }
  }

  function collapseLegacyFullForMinimize() {
    if (isSurfaceActionBlocked() || eMinimized) return;

    // Full collapse does not have a compact surface snapshot; never let the
    // next ball restore consume geometry left by a previous compact collapse.
    _ballAnchorBoundsBeforeExpand = null;
    _minimizedBallSurfaceRestoreDelta = null;
    _lastLayoutForRestore = null;

    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) {
      setReactChatSurfaceMode('minimized', { force: true });
      return;
    }

    var rect = shell.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      setReactChatSurfaceMode('minimized', { force: true });
      return;
    }

    var transitionToken = beginSurfaceTransition('legacy-full-collapsing');
    eBusy = true;
    eHiddenByClose = false;
    ePendingChatSurfaceMode = null;
    hideDesktopCompactBallWindow();
    setDesktopCompactAvatarBoundsSubscription(true);

    if (activeAnimationCleanup) {
      activeAnimationCleanup();
      activeAnimationCleanup = null;
    }

    var sx = BALL_SIZE / rect.width;
    var sy = BALL_SIZE / rect.height;
    var ballPad = (WIN_SIZE - BALL_SIZE) / 2;
    var overlay = document.createElement('img');
    overlay.className = 'neko-e-ball-overlay';
    overlay.src = MINIMIZED_BALL_ICON_SRC;
    overlay.srcset = MINIMIZED_BALL_ICON_SRCSET;
    overlay.draggable = false;
    overlay.style.width = BALL_SIZE + 'px';
    overlay.style.height = BALL_SIZE + 'px';
    overlay.style.imageRendering = 'auto';
    overlay.style.left = (rect.left + ballPad) + 'px';
    overlay.style.top = (rect.top + rect.height - WIN_SIZE + ballPad) + 'px';
    document.body.appendChild(overlay);

    shell.style.transformOrigin = '0% 100%';
    shell.classList.add('is-collapsing', 'neko-e-animating');

    var anim = shell.animate([
      { transform: 'scale(1)', opacity: 1, offset: 0 },
      { transform: 'scale(' + sx + ',' + sy + ')', opacity: 0, offset: 1 }
    ], {
      duration: 600,
      easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
      fill: 'forwards'
    });

    var ballAnim = overlay.animate([
      { opacity: 0, offset: 0 },
      { opacity: 0, offset: 0.67 },
      { opacity: 1, offset: 0.78 },
      { opacity: 1, offset: 1 }
    ], {
      duration: 600,
      easing: 'linear',
      fill: 'forwards'
    });

    var canceled = false;
    var visualDone = false;
    var nativeStarted = false;
    var nativePromise = null;
    var visualTimer = 0;
    var nativeTimer = 0;
    var fallbackTimer = 0;
    var preBoundsPromise = W.getBounds().catch(function () { return null; });

    function startNativeCollapse() {
      if (nativeStarted) return nativePromise;
      nativeStarted = true;
      if (shell) {
        shell.style.setProperty('opacity', '0', 'important');
      }
      nativePromise = preBoundsPromise.then(function (preBounds) {
        return W.collapse().then(function (savedBounds) {
          return savedBounds || preBounds;
        });
      });
      return nativePromise;
    }

    function finishVisual() {
      if (visualDone) return;
      visualDone = true;
      window.clearTimeout(visualTimer);
      window.clearTimeout(nativeTimer);
      startNativeCollapse().then(function (savedBounds) {
        if (canceled) return;

        if (savedBounds) {
          eSavedBounds = savedBounds;
          saveExpandBounds(savedBounds);
        }

        eMinimized = true;
        setReactChatSurfaceMode('minimized', { force: true });
        if (_useExternalMinimizedBallWindow && shell) {
          shell.style.setProperty('opacity', '0', 'important');
        }
        scheduleElectronChatMinimizedState('legacy-full-collapse');

        if (_useExternalMinimizedBallWindow) {
          var ballBounds = buildLegacyFullBallBounds(savedBounds);
          if (ballBounds) {
            try {
              ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.COLLAPSE_TAKEOVER, {
                bounds: ballBounds
              });
            } catch (_) {}
          }
          fallbackTimer = window.setTimeout(function () {
            if (!eMinimized) return;
            prepareReactCollapsedShell(shell);
          }, 800);
          activeAnimationCleanup = function () {
            window.clearTimeout(fallbackTimer);
          };
        } else {
          prepareReactCollapsedShell(shell);
          if (shell) shell.style.removeProperty('opacity');
          try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE); } catch (_) {}
          activeAnimationCleanup = null;
        }

        cleanupLegacyFullCollapseVisual(shell, overlay, anim, ballAnim);
        eBusy = false;
        flushPendingChatSurfaceMode();
        endSurfaceTransition(transitionToken);
      }).catch(function (err) {
        console.warn('[Preload-Chat][legacy-full-collapse] native collapse failed:', err);
        cleanupLegacyFullCollapseVisual(shell, overlay, anim, ballAnim);
        if (shell) shell.style.removeProperty('opacity');
        eMinimized = false;
        eBusy = false;
        activeAnimationCleanup = null;
        flushPendingChatSurfaceMode();
        endSurfaceTransition(transitionToken);
      });
    }

    anim.onfinish = finishVisual;
    nativeTimer = window.setTimeout(startNativeCollapse, 360);
    visualTimer = window.setTimeout(finishVisual, 680);
    activeAnimationCleanup = function () {
      canceled = true;
      window.clearTimeout(visualTimer);
      window.clearTimeout(nativeTimer);
      window.clearTimeout(fallbackTimer);
      cleanupLegacyFullCollapseVisual(shell, overlay, anim, ballAnim);
      if (shell) shell.style.removeProperty('opacity');
    };
  }

  function collapseNativeForReactMinimized() {
    if (isSurfaceActionBlocked() || eMinimized) {
      return;
    }
    var transitionToken = beginSurfaceTransition('collapsing');
    eBusy = true;
    hideDesktopCompactBallWindow();
    // [external-ball 路径] 立即用 DOM opacity:0 遮住整个 shell。覆盖两个闪帧窗口：
    // 1) React 收到 mode=minimized 后重渲染可能短暂显示 minimized 球组件
    // 2) PRE_COLLAPSE_DIM (async IPC setOpacity(0)) 生效前的 1-2 帧
    // 在 W.collapse resolve 后、prepareReactCollapsedShell 之前移除（见下方），
    // 此时 BrowserWindow 已 opacity 0 且球图标 CSS 尚未添加，移除不会闪帧。
    // Linux 本体球路径不设遮罩：setOpacity 是 no-op、无 PRE_COLLAPSE_DIM 透明
    // carrier，窗口收缩期间保持可见，遮罩会让用户既看不到 chat 也看不到球。
    var collapseShell = document.getElementById('react-chat-window-shell');
    if (_useExternalMinimizedBallWindow && collapseShell) {
      collapseShell.style.setProperty('opacity', '0', 'important');
    }
    // 新一次折叠周期开始 —— 清除上次的球 anchor 与逆变换差量。
    _ballAnchorBoundsBeforeExpand = null;
    _minimizedBallSurfaceRestoreDelta = null;
    // 缓存「当前这次折叠」的 surface 尺寸，给随后 doExpand 反推 stored surface 用（top
    // 反推需要 surface 高度）。**每次折叠都刷新**：compact surface 高度并非恒定（开启
    // galgame / 附件等会变成 385/495px），只在首次缓存会让后续展开用过期高度算 ballSurfaceTop，
    // 导致还原后对话条底边与球对不齐。所以这里始终取最新值。
    if (window.__nekoDesktopCompactLayout && window.__nekoDesktopCompactLayout.surface) {
      var freezeLayoutSurface = window.__nekoDesktopCompactLayout.surface;
      var freezeLayoutWB = window.__nekoDesktopCompactLayout.windowBounds || {};
      _lastLayoutForRestore = {
        surface: {
          left: Number(freezeLayoutSurface.left),
          top: Number(freezeLayoutSurface.top),
          width: Number(freezeLayoutSurface.width),
          height: Number(freezeLayoutSurface.height)
        },
        windowBounds: {
          width: Number(freezeLayoutWB.width) || 1100,
          height: Number(freezeLayoutWB.height) || 900
        }
      };
    }
    // Win32 uses an opacity-0 carrier plus an external yarn-ball BrowserWindow:
    // setBounds on a visible transparent frameless window is more reliable than
    // hidden-window bounds there. Linux cannot use that because setOpacity() is
    // a no-op; on Linux the chat BrowserWindow itself remains as the collapsed
    // 88x88 yarn ball, so drag/click restore always read the real ball bounds.
    var sentPreCollapseDim = false;
    if (_useExternalMinimizedBallWindow) {
      sentPreCollapseDim = emitCompactChatPreCollapseSeq();
    }

    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) {
      // 已经派过 PRE_COLLAPSE_DIM 时才需要回滚透明，否则 Linux 本体球路径没有窗口透明态。
      if (sentPreCollapseDim) {
        emitCompactChatRestoreComplete();
      }
      eBusy = false;
      endSurfaceTransition(transitionToken);
      return;
    }

    // Bug C 防竞态：确认 shell 存在、确实要收起之后，同步封死 compact 视图 —— 立刻置
    // eMinimized=true 并取消在途 relayout（清 savePending/relayoutQueued、cancel relayout rAF）。
    // 这样 compact 阶段排队的异步回调（activateDesktopCompactWindow 的 .then / AVATAR_BOUNDS_SYNC /
    // scheduleDesktopCompactRelayout 的 rAF）在收起动画窗口期 resolve 时，其 eMinimized / mode 守卫
    // 立即生效并放弃，不会把已塌成折叠尺寸的对话框 setBounds 撑回、也不会重新 showDesktopCompactBallWindow
    // 重现独立球。务必放在 !shell 早退之后：shell 缺失时直接 abort（仅复位 eBusy），不留下
    // “窗口没收起、状态却已最小化”的错配（否则后续 relayout 会因 eMinimized 全部跳过，卡死到刷新）。
    // 若下方 W.collapse 失败，其 .catch 会把 eMinimized 回滚为 false。
    freezeDesktopCompactForCollapse();
    // [external-ball 路径] prepareReactCollapsedShell 延迟到 W.collapse resolve 后执行
    // （见下方）。在此之前 BrowserWindow 可能仍是 opacity 1（PRE_COLLAPSE_DIM 尚未生效），
    // 添加 .neko-e-collapsed 会让球图标在 1 帧内闪现。W.collapse resolve 时
    // BrowserWindow 已被 PRE_COLLAPSE_DIM 设为 opacity 0，此时添加才安全。
    // Linux X11 本体球路径维持收缩前切换：窗口全程可见，须在 W.collapse 前换成球图标，
    // 否则收缩期间显示的是被裁剪的 compact 内容。Native Wayland 不再调用 W.collapse，
    // 而是在下方把毛球画到透明 carrier 内的虚拟锚点上。
    if (!_useExternalMinimizedBallWindow && !_isNativeWayland) {
      prepareReactCollapsedShell(shell);
    }

    var preservedExpandBounds = desktopCompactWindowActive ? loadExpandBounds() : null;
    var compactBallCollapseTarget = shouldUseDesktopCompactBallCollapseTarget()
      ? getDesktopCompactBallCollapseTarget()
      : null;
    var externalBallCollapseTarget = null;
    if (_useExternalMinimizedBallWindow && compactBallCollapseTarget) {
      var externalTargetX = Number(compactBallCollapseTarget.externalBallAnchorX);
      var externalTargetY = Number(compactBallCollapseTarget.externalBallAnchorY);
      if (Number.isFinite(externalTargetX) && Number.isFinite(externalTargetY)) {
        externalBallCollapseTarget = {
          x: Math.round(externalTargetX),
          y: Math.round(externalTargetY)
        };
      }
    }
    // 折叠前抓取 compact 对话条 surface 在屏幕上的真实位置 —— 这才是用户视觉看到的对话条，
    // 用它的左下角作为球锚点（windowBounds 左下角会跑到屏幕左下而不是对话条旁），
    // 同时作为恢复差量的基准。
    var surfaceScreenRectBeforeCollapse = captureDesktopCompactSurfaceScreenRectBeforeCollapse();
    // 球的目标左上角 = surface 左下角往上 WIN_SIZE 像素 → 球左下角 = surface 左下角
    var surfaceCollapseTargetBounds = surfaceScreenRectBeforeCollapse ? {
      x: surfaceScreenRectBeforeCollapse.x,
      y: surfaceScreenRectBeforeCollapse.y + surfaceScreenRectBeforeCollapse.height - WIN_SIZE
    } : null;
    // 按钮位置来自真实点击/缓存，优先作为折叠目标；缺失时回退到 surface 左下角，保持上游
    // 通过 visible surface 修正 desktop compact 大窗口 bounds 偏移的行为。
    var collapseTargetBounds = externalBallCollapseTarget || compactBallCollapseTarget || surfaceCollapseTargetBounds;
    if (_isNativeWayland && !_useExternalMinimizedBallWindow) {
      var waylandSelfBallCollapseTarget = normalizeDesktopCompactWaylandSelfBallAnchorBounds(collapseTargetBounds || surfaceCollapseTargetBounds);
      return W.getBounds().catch(function () {
        return null;
      }).then(function (currentBounds) {
        var carrierBounds = getDesktopCompactWaylandSelfBallCarrierBounds(currentBounds);
        if (!waylandSelfBallCollapseTarget && carrierBounds) {
          waylandSelfBallCollapseTarget = normalizeDesktopCompactWaylandSelfBallAnchorBounds({
            x: carrierBounds.x,
            y: carrierBounds.y + carrierBounds.height - WIN_SIZE
          });
        }
        if (!waylandSelfBallCollapseTarget) {
          throw new Error('native Wayland self-ball collapse target unavailable');
        }
        if (carrierBounds) {
          if (preservedExpandBounds) {
            eSavedBounds = preservedExpandBounds;
          } else {
            saveExpandBounds(carrierBounds);
          }
        }
        finishDesktopCompactCollapse();
        setDesktopCompactWaylandSelfBallAnchorBounds(
          waylandSelfBallCollapseTarget,
          carrierBounds,
          'self-ball-wayland-collapsed'
        );
        prepareReactCollapsedShell(shell);
        if (collapseShell) clearReactCompactShellVisibilityGuards(collapseShell);
        eMinimized = true;
        eBusy = false;
        scheduleElectronChatMinimizedState('compact-collapse');
        recordMinimizedBallSurfaceRestoreDelta(
          surfaceScreenRectBeforeCollapse,
          waylandSelfBallCollapseTarget,
          carrierBounds
        );
        try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE); } catch (_) {}
        flushPendingChatSurfaceMode();
        endSurfaceTransition(transitionToken);
        return carrierBounds || waylandSelfBallCollapseTarget;
      }).catch(function (err) {
        console.warn('[Preload-Chat][collapse] native Wayland virtual ball collapse failed:', err);
        shell.classList.remove('neko-e-collapsed', 'neko-e-wayland-self-ball-carrier');
        clearDesktopCompactWaylandSelfBallAnchor();
        if (collapseShell) clearReactCompactShellVisibilityGuards(collapseShell);
        eMinimized = false;
        eBusy = false;
        scheduleElectronChatMinimizedState('compact-collapse-failed');
        flushPendingChatSurfaceMode();
        endSurfaceTransition(transitionToken);
        return false;
      });
    }
    W.collapse(collapseTargetBounds).then(function (bounds) {
      // 外部球路径（Win32/mac）：BrowserWindow setOpacity(0) + setBounds
      // 可能尚未上屏渲染，此时 prepareReactCollapsedShell（添加 .neko-e-collapsed
      // → 球图标出现在 viewport left:0;top:0）会让球在旧窗口位置闪现一帧。
      // 外部球窗口负责视觉，页面回退球图标不需要在折叠时立即显示，
      // 所以外部球路径跳过 prepareReactCollapsedShell，仅做 class 清理。
      // Linux 本体球路径：BrowserWindow 自身就是球，需要 prepareReactCollapsedShell。
      if (_useExternalMinimizedBallWindow) {
        // 仅清理动画 class，不添加 .neko-e-collapsed（不显示回退球图标）
        if (shell) {
          shell.classList.remove('is-collapsing', 'is-expanding', 'is-minimized', 'neko-e-animating');
          shell.style.removeProperty('transform');
          shell.style.removeProperty('transform-origin');
        }
        // DOM opacity:0 保护层保持，BrowserWindow 已被 PRE_COLLAPSE_DIM 设为 opacity 0，
        // 双层保护确保无闪帧。restoreCompactDesktopFromMinimizedOrExpand 恢复时会移除
        // DOM opacity 并清理 .neko-e-collapsed。
        // 安全回退：如果 COLLAPSE_TAKEOVER 在主进程侧失败（如 showCompactChatBallWindow
        // 返回 null），主进程会调用 restoreReactChatVisibilityFromMinimize 恢复
        // BrowserWindow opacity=1，但不会通知 preload 移除 DOM opacity:0 或添加
        // 回退球图标。此时用户看到的是空白不可交互页面。延迟 800ms 后补加
        // prepareReactCollapsedShell 作为回退入口——此时 W.collapse 已将窗口缩至
        // 88×88，球图标 centered 在小视口内不会在旧大窗口位置闪帧；正常路径下
        // BrowserWindow 保持 opacity 0 所以回退球不可见。
        if (collapseShell && _useExternalMinimizedBallWindow) {
          if (activeAnimationCleanup) {
            activeAnimationCleanup();
            activeAnimationCleanup = null;
          }
          var _fallbackSeq = eSurfaceTransitionSeq;
          var _fallbackTimer = setTimeout(function () {
            if (_fallbackSeq !== eSurfaceTransitionSeq) return; // 新 transition 已启动，放弃旧回退
            if (!eMinimized) return; // 已恢复，无需回退
            prepareReactCollapsedShell(shell);
          }, 800);
          activeAnimationCleanup = function () {
            clearTimeout(_fallbackTimer);
          };
        }
      } else {
        prepareReactCollapsedShell(shell);
        if (collapseShell) clearReactCompactShellVisibilityGuards(collapseShell);
        sendDesktopCompactWaylandFullWindowShape('self-ball-collapsed-bounds', bounds);
      }
      if (bounds) {
        if (preservedExpandBounds) {
          eSavedBounds = preservedExpandBounds;
        } else {
          eSavedBounds = bounds;
          saveExpandBounds(bounds);
        }
      }
      finishDesktopCompactCollapse();
      eMinimized = true;
      eBusy = false;
      scheduleElectronChatMinimizedState('compact-collapse');
      // 恢复差量绑定到本次折叠 —— 恢复端（restoreCompactDesktopFromMinimized / doExpand）用
      // anchor+差量做与本次折叠严格互逆的还原，根除按钮中心折叠落点与旧「球左下角 = surface
      // 左下角」反推之间的每轮固定漂移。
      recordMinimizedBallSurfaceRestoreDelta(surfaceScreenRectBeforeCollapse, collapseTargetBounds, bounds);
      // 毛线球折叠：W.collapse 已把对话框窗口 setBounds 到 (bounds.x, bounds.y +
      // bounds.height - WIN_SIZE, WIN_SIZE, WIN_SIZE)（主进程 window-control-ipc.js
      // 的左下角对齐）。在同坐标 SHOW 独立球窗口让它覆盖对话框，然后 hide 对话框
      // —— 完成「对话框消失、球独立存在」的两窗口切换。
      //
      // 球的位置严格对齐对话框折叠后的位置 = 折叠前对话框 bounds 的左下角。这样：
      //   - 折叠时视觉上 = 对话框收缩到左下角后被球替换（位置无跳变）
      //   - 展开时 doExpand 内 W.expand 用同样的左下角对齐还原 bounds
      // bounds 缺失时（W.collapse 解析失败）退回 preservedExpandBounds 当原始几何参考。
      // 优先使用按钮/缓存的 88px anchor；缺失时使用 surface 屏幕坐标（真正的对话条 visible
      // 位置），fallback 到 windowBounds。
      // surfaceScreenRectBeforeCollapse 是折叠前抓取的 —— W.collapse 之后 layout 已经
      // freeze/重置，不能再从 __nekoDesktopCompactLayout 读到。
      var compactBallAnchorTarget = externalBallCollapseTarget || compactBallCollapseTarget;
      var ballAnchorBounds = compactBallAnchorTarget ? {
        x: Math.round(Number(compactBallAnchorTarget.x) || 0),
        y: Math.round(Number(compactBallAnchorTarget.y) || 0),
        width: WIN_SIZE,
        height: WIN_SIZE
      } : (surfaceScreenRectBeforeCollapse || bounds || preservedExpandBounds);
      if (_useExternalMinimizedBallWindow && ballAnchorBounds) {
        var ballBounds = externalBallCollapseTarget ? {
            // 外部球窗口本身是 58px，可视球位于 anchor 的左上角；collapse target 则是 88px
            // carrier。按钮目标使用独立的 external anchor，并让 hidden carrier 同步到同一位置，
            // 避免直接恢复从 W.getBounds() 读到旧的 88px target。
            x: Math.round(Number(ballAnchorBounds.x) || 0),
            y: Math.round(Number(ballAnchorBounds.y) || 0),
            width: WIN_SIZE,
            height: WIN_SIZE
          } : {
            // 球落点视觉微调（与输入框里 minimize 球对齐）：x 比对话条左 3px、y 比"球底对齐对话条底"再下 4px。
            // 数值在此调（x offset 越大越右、负数偏左；y 加项越大越下）；chatWin 仍落对话条自然位
            // （恢复读 chatWin → 回原位无漂移），X 拖动/夹取侧 chatWin=球+3 维持（main.js DRAG_MOVE/DRAG_END）。
            x: Math.round((Number(ballAnchorBounds.x) || 0) - 3),
            y: Math.round((Number(ballAnchorBounds.y) || 0) + (Number(ballAnchorBounds.height) || 0) - WIN_SIZE + 4),
            width: WIN_SIZE,
            height: WIN_SIZE
          };
        try {
          ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.COLLAPSE_TAKEOVER, {
            bounds: ballBounds
          });
        } catch (err) {
          console.warn('[Preload-Chat][collapse] COLLAPSE_TAKEOVER failed:', err);
        }
      } else if (!_useExternalMinimizedBallWindow) {
        try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE); } catch (_) {}
      }
      flushPendingChatSurfaceMode();
      endSurfaceTransition(transitionToken);
    }).catch(function (err) {
      console.warn('[Preload-Chat][collapse] native collapse failed:', err);
      // Linux 本体球路径在 W.collapse 前已加 .neko-e-collapsed，这里回滚；
      // external 路径此时尚未添加，remove 是幂等 no-op。
      shell.classList.remove('neko-e-collapsed');
      // 回滚入口设的 DOM opacity:0（仅 external 路径设过），让 shell 恢复可见
      if (collapseShell) clearReactCompactShellVisibilityGuards(collapseShell);
      eMinimized = false;
      eBusy = false;
      scheduleElectronChatMinimizedState('compact-collapse-failed');
      // W.collapse 失败 → 没有 COLLAPSE_TAKEOVER。仅发过 PRE_COLLAPSE_DIM 的外部球路径
      // 需要回滚 chatWin opacity；Linux 本体球路径没有窗口透明态，不应额外发恢复回执。
      if (sentPreCollapseDim) {
        emitCompactChatRestoreComplete();
      }
      flushPendingChatSurfaceMode();
      endSurfaceTransition(transitionToken);
    });
  }

  // ---- 展开：物理放大窗口 → 左下角定点放大 ----
  // 展开态最小允许尺寸（与主进程 RESIZE_MIN_W / RESIZE_MIN_H 保持一致）
  // options.suppressOnfinishRelayout: true 时 anim.onfinish 不调
  //   scheduleDesktopCompactRelayout —— 用于毛线球恢复路径，保持对话框留在球位置而
  //   不被 activateDesktopCompactWindow 用 avatar payload 重算 layout 拉回 avatar 旁。
  function doExpand(options) {
    options = options || {};
    var suppressOnfinishRelayout = !!options.suppressOnfinishRelayout;
    // 毛线球恢复路径下，调用方（球 CLICK）此刻已让 chatWin 处于 opacity 0 + ignoreMouseEvents(true)
    // 的隐性 carrier 态、独立球还显示着。下面任一「无法真正展开」的早退若直接 return，会留下
    // 「对话框透明穿透 + 残留球」的死状态（球可点但点了没反应、对话框整窗不接收鼠标）。除 eBusy
    // （动画并发保护，揭示会打断动画，必须原样早退）外，其余异常早退都补发一次 RESTORE_COMPLETE
    // 兜底：main 幂等复位 chatWin opacity/命中 + 回收残留球。普通（非球）展开路径走到这些分支时
    // chatWin 本就可见、无球，RESTORE_COMPLETE 幂等无副作用。
    if (isSurfaceActionLocked()) {
      requestChatSurfaceMode('compact');
      return;
    }
    if (!eMinimized) {
      emitCompactChatRestoreComplete();
      flushPendingChatSurfaceMode();
      return;
    }
    var targetBounds = loadExpandBounds();
    if (!targetBounds) {
      emitCompactChatRestoreComplete();
      flushPendingChatSurfaceMode();
      return;
    }
    eSavedBounds = targetBounds;
    var transitionToken = beginSurfaceTransition('expanding');
    eBusy = true;
    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) {
      eBusy = false;
      endSurfaceTransition(transitionToken);
      emitCompactChatRestoreComplete();
      flushPendingChatSurfaceMode();
      return;
    }
    // 毛线球恢复路径（suppressOnfinishRelayout=true）：**只写 stored surface（球位置）**，
    // 不再用 explicitOverride 把窗口冻结在非自然位置。
    // 旧做法（explicitOverride + 冻结 activate）的问题：窗口被钉在 padded 大窗的非自然位置，
    // 而 desktopCompactLayout（拖拽 startSurface、relayout 都读它）与实际窗口/CSS 偏移容易
    // 不一致 → 「拖动输入框时框和光标差一个固定 offset」，且冻结窗口与 surface 拖拽（要移动
    // 整窗）本质冲突。
    // 新做法：把球左下角反推出的 surface 屏幕位置写进 stored surface（localStorage）。它在
    // buildDesktopCompactLayoutRects 里优先级最高（> measured DOM > avatar fallback），于是
    // activateDesktopCompactWindow 用 desktop compact 自然算法把窗口摆到「围着球 surface」的
    // 自然 bounds、surface 落在球位置，全程 layout 与实际窗口一致 → 定位 / 拖拽 / relayout 都对。
    // 反推走 buildDesktopCompactSurfaceRectFromMinimizedBallAnchor：优先折叠差量精确逆变换，
    // 差量缺失时退回「球左下角 = surface 左下角」近似。
    if (suppressOnfinishRelayout && _ballAnchorBoundsBeforeExpand) {
      var restoredSurfaceRectForExpand = buildDesktopCompactSurfaceRectFromMinimizedBallAnchor(_ballAnchorBoundsBeforeExpand);
      if (restoredSurfaceRectForExpand) {
        saveDesktopCompactSurfacePosition(restoredSurfaceRectForExpand);
      }
    }

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

    var expandPayload = suppressOnfinishRelayout
      ? { bounds: eSavedBounds, skipEnsureExpanded: true }
      : eSavedBounds;
    W.expand(expandPayload).then(function () {
      setReactChatSurfaceMode('compact', { force: true });

    if (suppressOnfinishRelayout) {
        // ===== 毛线球恢复：隐性定位 →（尽快）并发揭示 =====
        // chatWin 折叠时已被 PRE_COLLAPSE_DIM 设 opacity 0，下面整段定位用户都看不见。
        // eMinimized=false 让 activateDesktopCompactWindow 能跑（之前被 eMinimized 守卫挡住），
        // activate 用 stored surface（球位置，优先级最高）自然算出窗口 bounds + 把 surface 的
        // CSS 偏移钉到球位置。等 surface 落位（约 1xx ms，**不**再等满球 bounce 时长）后就揭示，
        // 让对话框尽快出现、与球的 bounce 动画并发，中间无空白等待（用户反馈：球动画不应拖慢
        // 输入框出现）。独立球的 hide 不再绑在这里 —— 球在自己窗口里弹完 bounce 动画后自行
        // 发 HIDE（见 preload-compact-chat-ball.js），与对话框揭示解耦、互不影响。
        // 揭示前留足帧数（activate 落位 + setBounds 经 DWM 提交）以根除「屏幕下方闪一下」。
        eMinimized = false;
        scheduleElectronChatMinimizedState('ball-restore');
        clearExpandBounds();
        idleDockSavedSurfaceMode = null;
        shell.classList.remove('is-expanding', 'neko-e-animating');
        shell.style.transformOrigin = '';
        shell.style.transform = 'none';
        if (ballIconInShell) ballIconInShell.style.opacity = '';
        shell.style.opacity = ''; // shell 不透明，但 chatWin window opacity 仍是 0，用户看不见
        activateDesktopCompactWindow(); // 隐性定位（自然 bounds + surface 钉到球位置）
        var BALL_RESTORE_REVEAL_MS = 140; // 留够 activate 落位 + DWM 提交，又足够快（并发）
        window.setTimeout(function () {
          activateDesktopCompactWindow(); // 再定位一次，防首帧 activate 异步竞态
          waitForDesktopCompactRevealBoundsBeforeReveal({ layoutTimeoutMs: 240, timeoutMs: 300, intervalMs: 32 }).then(function (boundsOk) {
            requestAnimationFrame(function () { requestAnimationFrame(function () {
              eBusy = false;
              // surface 已落在球位置、shell 已不透明 —— 揭示 chatWin（main restore opacity）
              emitCompactChatRestoreComplete();
              endSurfaceTransition(transitionToken);
              flushPendingChatSurfaceMode();
            }); });
          });
        }, BALL_RESTORE_REVEAL_MS);
        return;
      }

      // 3. 窗口已展开，启动左下角放大动画（普通展开路径，非毛线球）
      shell.style.opacity = '';

      // 普通（非毛线球）路径退出 minimized 时也复位 chatWin opacity：若之前走过毛线球折叠的
      // PRE_COLLAPSE_DIM（把 chatWin 设成 opacity 0），而这次是经非球路径展开（不会派下方
      // 那条 RESTORE_COMPLETE），否则对话框会停在 opacity 0「隐身」。RESTORE_COMPLETE → main
      // setOpacity(1) 是幂等的，窗口本就可见时无副作用，所以无回归风险。
      emitCompactChatRestoreComplete();

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
      overlay.src = MINIMIZED_BALL_ICON_SRC;
      overlay.srcset = MINIMIZED_BALL_ICON_SRCSET;
      overlay.draggable = false;
      overlay.style.width = BALL_SIZE + 'px';
      overlay.style.height = BALL_SIZE + 'px';
      overlay.style.imageRendering = 'auto';
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
        // 普通展开路径（毛线球恢复路径已在上方 W.expand .then() 提前 return，不会走到这里）。
        scheduleDesktopCompactRelayout();
        idleDockSavedSurfaceMode = null;
        eBusy = false;
        endSurfaceTransition(transitionToken);
        flushPendingChatSurfaceMode();
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
    }).catch(function () {
      if (shell && shell.parentNode) {
        prepareReactCollapsedShell(shell);
      }
      emitCompactChatRestoreComplete();
      eBusy = false;
      endSurfaceTransition(transitionToken);
      flushPendingChatSurfaceMode();
    });
    }, 32); });
  }

  window.nekoChatWindow.isCollapsed = function () {
    return !!eMinimized;
  };

  window.nekoChatWindow.idleDockCollapse = function () {
    if (isSurfaceActionLocked()) return Promise.resolve(false);
    if (eMinimized) {
      var waylandSelfBallAnchor = getDesktopCompactWaylandSelfBallAnchorBounds();
      if (waylandSelfBallAnchor) return Promise.resolve(waylandSelfBallAnchor);
      return W.getBounds();
    }

    var shell = document.getElementById('react-chat-window-shell');
    if (!shell) return Promise.resolve(false);

    eBusy = true;
    var currentSurfaceMode = getCurrentReactChatSurfaceMode();
    if (currentSurfaceMode && currentSurfaceMode !== 'minimized') {
      idleDockSavedSurfaceMode = currentSurfaceMode;
      if (currentSurfaceMode === 'compact') {
        rememberDesktopCompactMinimizeButtonScreenRect();
      }
      setReactChatSurfaceMode('minimized', { force: true });
      shell = document.getElementById('react-chat-window-shell') || shell;
    }
    freezeDesktopCompactForCollapse();
    if (!_isNativeWayland || _useExternalMinimizedBallWindow) {
      prepareReactCollapsedShell(shell);
    }

    // 新一次折叠周期开始 —— 与 collapseNativeForReactMinimized 对偶：清掉上一轮（可能来自
    // 毛线球路径、不同 surface 几何）的恢复差量，W.collapse 落点确定后再记录本次的。
    // idle-dock 从 compact 折叠后 idleDockExpand 同样走 restoreCompactDesktopFromMinimized，
    // 不记录会让恢复端拿陈旧差量算错位置（Codex P2）。
    _minimizedBallSurfaceRestoreDelta = null;
    var idleDockSurfaceRectBeforeCollapse = captureDesktopCompactSurfaceScreenRectBeforeCollapse();
    var preservedExpandBounds = desktopCompactWindowActive ? loadExpandBounds() : null;
    var compactBallCollapseTarget = shouldUseDesktopCompactBallCollapseTarget()
      ? getDesktopCompactBallCollapseTarget()
      : null;
    var idleDockSurfaceCollapseTarget = idleDockSurfaceRectBeforeCollapse ? {
      x: idleDockSurfaceRectBeforeCollapse.x,
      y: idleDockSurfaceRectBeforeCollapse.y + idleDockSurfaceRectBeforeCollapse.height - WIN_SIZE
    } : null;
    var idleDockCollapseTarget = compactBallCollapseTarget || idleDockSurfaceCollapseTarget;
    return W.getBounds()
      .then(function (bounds) {
        if (!preservedExpandBounds) saveExpandBounds(bounds);
        if (_isNativeWayland && !_useExternalMinimizedBallWindow) {
          var waylandIdleDockTarget = normalizeDesktopCompactWaylandSelfBallAnchorBounds(idleDockCollapseTarget);
          if (!waylandIdleDockTarget) {
            waylandIdleDockTarget = normalizeDesktopCompactWaylandSelfBallAnchorBounds({
              x: bounds.x,
              y: bounds.y + bounds.height - WIN_SIZE
            });
          }
          if (!waylandIdleDockTarget) throw new Error('native Wayland idle dock target unavailable');
          if (preservedExpandBounds) {
            eSavedBounds = preservedExpandBounds;
          } else {
            saveExpandBounds(bounds);
          }
          finishDesktopCompactCollapse();
          setDesktopCompactWaylandSelfBallAnchorBounds(
            waylandIdleDockTarget,
            bounds,
            'self-ball-wayland-idle-dock'
          );
          prepareReactCollapsedShell(shell);
          eMinimized = true;
          eBusy = false;
          scheduleElectronChatMinimizedState('idle-dock-collapse');
          recordMinimizedBallSurfaceRestoreDelta(idleDockSurfaceRectBeforeCollapse, waylandIdleDockTarget, bounds);
          try { ipcRenderer.send(COMPACT_CHAT_BALL_CHANNELS.HIDE); } catch (_) {}
          return waylandIdleDockTarget;
        }
        return W.collapse(idleDockCollapseTarget).then(function (saved) {
          if (preservedExpandBounds) {
            eSavedBounds = preservedExpandBounds;
          } else {
            saveExpandBounds(saved || bounds);
          }
          finishDesktopCompactCollapse();
          eMinimized = true;
          eBusy = false;
          recordMinimizedBallSurfaceRestoreDelta(idleDockSurfaceRectBeforeCollapse, idleDockCollapseTarget, bounds);
          return W.getBounds();
        });
      })
      .catch(function (error) {
        shell.classList.remove('neko-e-collapsed', 'neko-e-wayland-self-ball-carrier');
        clearDesktopCompactWaylandSelfBallAnchor();
        eMinimized = false;
        eBusy = false;
        restoreIdleDockSurfaceModeIfNeeded();
        throw error;
      });
  };

  window.nekoChatWindow.idleDockExpand = function (savedBounds) {
    if (isSurfaceActionLocked()) return Promise.resolve(false);
    var target = normalizeExpandBounds(savedBounds) || loadExpandBounds();
    if (!target) return Promise.resolve(false);
    var shell = document.getElementById('react-chat-window-shell');
    if (eMinimized && idleDockSavedSurfaceMode === 'compact') {
      if (!shell) return Promise.resolve(false);
      return restoreCompactDesktopFromMinimized().then(function (restored) {
        if (restored === true) {
          restoreIdleDockSurfaceModeIfNeeded();
          return W.getBounds();
        }
        // 'canceled'：揭示期间被重新折叠，最小化态应保留，不要再 legacy-expand 强行展开
        // 把它撤销（Codex P2）。直接返回当前 bounds，不动 idle-dock surface mode 跟踪。
        if (restored === 'canceled' || restored === 'queued') return W.getBounds();
        return expandIdleDockWithLegacyBounds(target, shell);
      });
    }
    if (!eMinimized) {
      W.setBounds(target.x, target.y, target.width, target.height);
      restoreIdleDockSurfaceModeIfNeeded();
      return Promise.resolve(target);
    }

    if (!shell) return Promise.resolve(false);

    return expandIdleDockWithLegacyBounds(target, shell);
  };

  function expandIdleDockWithLegacyBounds(target, shell) {
    eBusy = true;
    eSavedBounds = target;
    shell.classList.remove('neko-e-collapsed', 'is-collapsing', 'is-expanding', 'neko-e-animating');
    clearReactCompactShellVisibilityGuards(shell);
    shell.style.transformOrigin = '';

    return W.expand(target).then(function () {
      W.setBounds(target.x, target.y, target.width, target.height);
      eMinimized = false;
      scheduleElectronChatMinimizedState('legacy-expand');
      clearExpandBounds();
      eBusy = false;
      restoreIdleDockSurfaceModeIfNeeded();
      return W.getBounds();
    }).catch(function (error) {
      eBusy = false;
      throw error;
    });
  }

  window.nekoChatWindow.idleDockCommitCollapsedBounds = function (bounds) {
    if (eBusy) return Promise.resolve(false);
    var target = normalizeCollapsedBounds(bounds);
    var shell = document.getElementById('react-chat-window-shell');
    if (shell) {
      ensureBallIcon();
      shell.classList.remove('is-collapsing', 'is-expanding', 'neko-e-animating');
      shell.classList.add('neko-e-collapsed');
      clearReactCompactShellVisibilityGuards(shell);
      shell.style.transformOrigin = '';
    }
    eMinimized = true;
    if (target) {
      W.setBounds(target.x, target.y, target.width, target.height);
    }
    scheduleElectronChatMinimizedState('idle-dock-commit');
    return W.getBounds();
  };

  function requestCompactInputState() {
    // compact 默认是胶囊态（没有 textarea），只有切到 input 态才会渲染输入框。
    var host = getReactChatHost();
    if (!host || typeof host.setCompactChatState !== 'function') return;
    try { host.setCompactChatState('input'); } catch (_) {}
  }

  function focusComposerInputElement(input) {
    if (!input || input.disabled || input.readOnly) return false;
    input.focus({ preventScroll: true });
    if (typeof input.setSelectionRange === 'function') {
      var len = input.value ? input.value.length : 0;
      input.setSelectionRange(len, len);
    }
    return true;
  }

  function findComposerInput() {
    return document.querySelector('#react-chat-window-shell textarea.composer-input, #react-chat-window-root textarea.composer-input, textarea.composer-input');
  }

  function scheduleComposerInputFocusRetry() {
    window.requestAnimationFrame(function () {
      setTimeout(function () { focusComposerInputFromHotkey({ retry: false }); }, 0);
    });
  }

  function focusComposerInputFromHotkey(options) {
    var retry = !options || options.retry !== false;
    requestCompactInputState();
    var input = findComposerInput();
    if (!input) {
      if (retry) {
        scheduleComposerInputFocusRetry();
        return true;
      }
      return false;
    }
    return focusComposerInputElement(input);
  }

  window.__nekoFocusReactChatInputFromHotkey = function () {
    if (eMinimized) {
      if (isSurfaceActionLocked()) {
        return true;
      }
      restoreCompactDesktopFromMinimized().then(function (restored) {
        if (restored === true) {
          // restoreCompactDesktopFromMinimized 成功路径不经 doExpand，若此前走过毛线球折叠的
          // PRE_COLLAPSE_DIM（chatWin opacity 0），这里必须复位 opacity，否则 focus 热键在球态
          // 恢复出的对话框是「有焦点但 opacity 0 隐身」。RESTORE_COMPLETE → main setOpacity(1)
          // 幂等、窗口本可见时无副作用。（doExpand fallback 路径已在其普通展开分支复位。）
          emitCompactChatRestoreComplete();
          focusComposerInputFromHotkey();
          return;
        }
        // 'canceled'：揭示期间被重新折叠，最小化态应保留。绝不能发 RESTORE_COMPLETE（会把刚
        // 最小化的 carrier 揭示出来），也不 doExpand。直接放弃这次 focus（窗口已最小化）（Codex P2）。
        if (restored === 'queued' || restored === 'canceled') return;
        doExpand();
        setTimeout(function () { focusComposerInputFromHotkey(); }, 680);
      });
      return true;
    }
    if (eBusy) {
      setTimeout(function () { focusComposerInputFromHotkey(); }, 180);
      return true;
    }
    return focusComposerInputFromHotkey();
  };

  var TUTORIAL_EXPAND_BUSY_POLL_MS = 80;
  var TUTORIAL_EXPAND_BUSY_TIMEOUT_MS = 1800;

  function scheduleTutorialExpandAfterBusy() {
    var startedAt = Date.now();
    function checkTutorialExpandAfterBusy() {
      // W.collapse keeps eBusy true during collapse animation; wait before expanding.
      if (eMinimized && !eBusy) {
        doExpand();
        return;
      }
      if (!eBusy || Date.now() - startedAt >= TUTORIAL_EXPAND_BUSY_TIMEOUT_MS) {
        if (eMinimized) doExpand();
        return;
      }
      setTimeout(checkTutorialExpandAfterBusy, TUTORIAL_EXPAND_BUSY_POLL_MS);
    }
    setTimeout(checkTutorialExpandAfterBusy, TUTORIAL_EXPAND_BUSY_POLL_MS);
  }

  window.nekoChatWindow.ensureExpandedForTutorial = function () {
    if (eMinimized) {
      doExpand();
      return true;
    }
    if (eBusy) {
      scheduleTutorialExpandAfterBusy();
      return true;
    }
    return false;
  };

  // Core compact surface-drag start. The main process drives the move by
  // polling the OS cursor, so this path is used for real mouse mousedown
  // gestures on the page-declared drag surface.
  //
  // A finite (screenX, screenY) is forwarded as the grab anchor — used by the
  // page mousedown path, where the event coords equal the cursor. Omit them
  // undefined) to let the main process read the live cursor as the anchor: the
  // live-cursor fallback keeps the drag anchored to the mouse and stays a clean
  // no-op for touch/pen whose contact does not move the OS cursor (delta from a
  // stationary cursor is ~0). Forwarding the page's finger coordinate instead
  // would jump the window by (cursor − finger) on the first poll.
  function startDesktopCompactSurfaceDragAtScreen(screenX, screenY) {
    if (desktopCompactSurfaceDragActive) return;

    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    var layoutBounds = layout && layout.windowBounds;
    var layoutSurface = normalizeRect(layout && layout.surface);
    if (!layoutBounds || !layoutSurface) return;

    var startSurface = getDesktopCompactLayoutSurfaceScreenRect(layout, layoutBounds);
    if (!startSurface) return;

    var dragSurfaceLocally = !!desktopCompactUseX11InputShape;
    var dragWindowDirectly = false;
    var dragOffsetX = Number.isFinite(screenX) ? screenX - startSurface.left : startSurface.width / 2;
    var dragOffsetY = Number.isFinite(screenY) ? screenY - startSurface.top : startSurface.height / 2;
    var localDragWorkArea = normalizeWindowBounds(layout && layout.workArea);
    var clampLocalDragTarget = function (target) {
      return clampDesktopCompactSurfaceLiveDragRect(target, localDragWorkArea);
    };
    var updateLocalDragTarget = function (event) {
      if (!dragSurfaceLocally || !event) return;
      var sx = Number(event.screenX);
      var sy = Number(event.screenY);
      if (!Number.isFinite(sx) || !Number.isFinite(sy)) return;
      var target = clampLocalDragTarget(makeScreenRect(
        sx - dragOffsetX,
        sy - dragOffsetY,
        startSurface.width,
        startSurface.height
      ));
      if (!target) return;
      desktopCompactSurfaceDragTarget = target;
      desktopCompactWindowSnapshot = '';
      scheduleDesktopCompactRelayout();
    };
    clearDesktopCompactSurfaceDragPrime();
    desktopCompactSurfaceDragActive = true;
    desktopCompactSurfaceDragTarget = startSurface;
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    desktopCompactSurfaceDragWorkArea = null;
    document.documentElement.classList.add('neko-dragging');
    var dragPayload = {
      keepVisible: true,
      minVisible: 80,
      anchorClampMode: 'inside-workarea',
      anchorWorkAreaInset: DESKTOP_COMPACT_NATIVE_PAD,
      anchorWorkAreaTopInset: DESKTOP_COMPACT_NATIVE_PAD,
      anchorRect: {
        left: startSurface.left,
        top: startSurface.top,
        width: startSurface.width,
        height: startSurface.height
      }
    };
    if (!dragWindowDirectly) {
      dragPayload.anchorDrag = true;
    }
    // Only forward a grab anchor when it is a real cursor point; otherwise the
    // main process falls back to the live OS cursor (see comment above).
    if (Number.isFinite(screenX) && Number.isFinite(screenY)) {
      dragPayload.sx = screenX;
      dragPayload.sy = screenY;
    }
    if (!dragSurfaceLocally) {
      W.dragStart(dragPayload);
    }
    if (dragSurfaceLocally || !dragWindowDirectly) {
      desktopCompactWindowSnapshot = '';
      scheduleDesktopCompactRelayout();
    }
    var finished = false;
    var trackMove = function (event) {
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      updateLocalDragTarget(event);
    };
    desktopCompactSurfaceDragCleanupForTutorial = function (reason) {
      document.documentElement.classList.remove('neko-dragging');
      document.removeEventListener('mousemove', trackMove);
      document.removeEventListener('mouseup', finishDrag);
      document.removeEventListener('pointerup', finishDrag);
      document.removeEventListener('pointercancel', finishDrag);
      window.removeEventListener('blur', finishDrag);
    };
    var finishDrag = function () {
      if (finished) return;
      finished = true;
      desktopCompactSurfaceDragCancelForTutorial = null;
      var cleanupDrag = desktopCompactSurfaceDragCleanupForTutorial;
      desktopCompactSurfaceDragCleanupForTutorial = null;
      if (typeof cleanupDrag === 'function') cleanupDrag('finish');
      var releasedSurface = normalizeRect(desktopCompactSurfaceDragTarget);
      if ((dragSurfaceLocally || !dragWindowDirectly) && releasedSurface) {
        saveDesktopCompactSurfacePosition(releasedSurface);
        saveDesktopCompactSurfaceWidth(releasedSurface.width);
        desktopCompactSurfaceDragSettledTarget = releasedSurface;
        desktopCompactSurfaceDragSettledWorkArea = desktopCompactSurfaceDragWorkArea || null;
      }
      clearDesktopCompactSurfaceDragPrime();
      desktopCompactSurfaceDragActive = false;
      desktopCompactSurfaceDragTarget = null;
      desktopCompactSurfaceDragWorkArea = null;
      desktopCompactWindowSnapshot = '';
      desktopCompactPendingWindowBounds = null;
      if (dragSurfaceLocally || !dragWindowDirectly) {
        scheduleDesktopCompactRelayout();
      }
      var finish = dragSurfaceLocally
        ? Promise.resolve({
          anchorRect: releasedSurface,
          bounds: desktopCompactLayout && desktopCompactLayout.windowBounds
        })
        : (typeof W.dragStopAndGetBounds === 'function'
        ? W.dragStopAndGetBounds({ skipBounceBack: true, returnAnchorRect: true })
        : Promise.resolve(null).then(function () {
          W.dragStop({ skipBounceBack: true });
          return W.getBounds();
        }));
      finish.catch(function () { return null; }).then(function (result) {
        var returnedAnchor = normalizeRect(result && result.anchorRect);
        var bounds = result && result.bounds ? result.bounds : result;
        var savedSurface = returnedAnchor || getDesktopCompactMeasuredBaseSurfaceScreenRect(bounds);
        if (savedSurface) {
          saveDesktopCompactSurfacePosition(savedSurface);
          saveDesktopCompactSurfaceWidth(savedSurface.width);
        }
        desktopCompactWindowSnapshot = '';
        desktopCompactPendingWindowBounds = null;
        scheduleDesktopCompactRelayout();
      });
    };
    desktopCompactSurfaceDragCancelForTutorial = function (reason) {
      if (finished) return;
      finished = true;
      desktopCompactSurfaceDragCancelForTutorial = null;
      var cleanupDrag = desktopCompactSurfaceDragCleanupForTutorial;
      desktopCompactSurfaceDragCleanupForTutorial = null;
      if (typeof cleanupDrag === 'function') cleanupDrag(reason || 'tutorial-fixed-layout');
      clearDesktopCompactSurfaceDragForTutorialRuntime();
      if (!dragSurfaceLocally && typeof W.dragStop === 'function') {
        try {
          var stopped = W.dragStop({ skipBounceBack: true });
          if (stopped && typeof stopped.catch === 'function') stopped.catch(function () {});
        } catch (_) {}
      }
      scheduleDesktopCompactRelayout(reason || 'tutorial-fixed-layout');
    };

    document.addEventListener('mousemove', trackMove);
    document.addEventListener('mouseup', finishDrag);
    // Keep pointer release as a defensive stop signal in addition to mouseup.
    // finishDrag is idempotent, so duplicate mouse/pointer releases are harmless.
    document.addEventListener('pointerup', finishDrag);
    document.addEventListener('pointercancel', finishDrag);
    window.addEventListener('blur', finishDrag);
  }

  function ensureDesktopCompactMeasuredFallbackLayout(layout) {
    var existingLayout = layout || desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    var existingBounds = normalizeWindowBounds(existingLayout && existingLayout.windowBounds);
    var fallbackBounds = existingBounds || getDesktopCompactRendererWindowBounds(existingBounds);
    var fallbackSurfaceScreenRect = getDesktopCompactMeasuredSurfaceScreenRect(fallbackBounds || {});
    var fallbackSurface = convertScreenRectToPageRect(fallbackSurfaceScreenRect, fallbackBounds);
    if (!fallbackBounds || !fallbackSurface) return existingLayout;
    var nextLayout = Object.assign({}, existingLayout || {}, {
      windowBounds: fallbackBounds,
      surface: fallbackSurface,
      surfaceScreenRect: fallbackSurfaceScreenRect || null,
      workArea: existingLayout && existingLayout.workArea ? existingLayout.workArea : null
    });
    desktopCompactLayout = nextLayout;
    window.__nekoDesktopCompactLayout = Object.assign({}, window.__nekoDesktopCompactLayout || {}, {
      windowBounds: nextLayout.windowBounds,
      surface: nextLayout.surface,
      surfaceScreenRect: nextLayout.surfaceScreenRect || null,
      workArea: nextLayout.workArea || null,
      compactChoicePlacement: nextLayout.compactChoicePlacement || null,
      dragging: !!desktopCompactSurfaceDragActive
    });
    return nextLayout;
  }

  function startDesktopCompactSurfaceRendererDrag(detail) {
    if (desktopCompactSurfaceDragActive) return;

    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    var layoutBounds = normalizeWindowBounds(layout && layout.windowBounds);
    var layoutSurface = normalizeRect(layout && layout.surface);
    if (!layoutBounds || !layoutSurface) {
      layout = ensureDesktopCompactMeasuredFallbackLayout(layout);
      layoutBounds = normalizeWindowBounds(layout && layout.windowBounds);
      layoutSurface = normalizeRect(layout && layout.surface);
    }
    if (!layoutBounds || !layoutSurface) return;

    var startClientX = Number(detail && detail.clientX);
    var startClientY = Number(detail && detail.clientY);
    if (!Number.isFinite(startClientX) || !Number.isFinite(startClientY)) return;
    var initialClientX = Number(detail && detail.currentClientX);
    var initialClientY = Number(detail && detail.currentClientY);
    var hasInitialClientPoint = Number.isFinite(initialClientX) && Number.isFinite(initialClientY);
    var pointerId = Number(detail && detail.pointerId);
    var hasPointerId = Number.isFinite(pointerId);
    var startClientBounds = getDesktopCompactClientCoordinateWindowBounds(layoutBounds) || layoutBounds;
    var startSurface = getDesktopCompactLayoutSurfaceScreenRect(layout, startClientBounds);
    if (!startSurface) return;
    var dragOffsetX = Math.round(Number(startClientBounds.x) || 0) + startClientX - startSurface.left;
    var dragOffsetY = Math.round(Number(startClientBounds.y) || 0) + startClientY - startSurface.top;
    var rendererDragSurface = startSurface;
    var lastClientBounds = startClientBounds;
    var localDragWorkArea = normalizeWindowBounds(layout && layout.workArea);
    var clampRendererDragTarget = function (target) {
      return clampDesktopCompactSurfaceLiveDragRect(target, localDragWorkArea);
    };
    var applyRendererDragTarget = function (target) {
      if (!target) return;
      rendererDragSurface = target;
      desktopCompactSurfaceDragTarget = rendererDragSurface;
      desktopCompactWindowSnapshot = '';
      scheduleDesktopCompactRelayout();
    };
    var updateRendererDragTargetFromClientPoint = function (clientX, clientY) {
      if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return false;
      var currentClientBounds = getDesktopCompactClientCoordinateWindowBounds(
        desktopCompactLayout && desktopCompactLayout.windowBounds
      ) || lastClientBounds;
      if (!currentClientBounds) return false;
      lastClientBounds = currentClientBounds;
      applyRendererDragTarget(clampRendererDragTarget(makeScreenRect(
        Math.round(Number(currentClientBounds.x) || 0) + clientX - dragOffsetX,
        Math.round(Number(currentClientBounds.y) || 0) + clientY - dragOffsetY,
        rendererDragSurface.width,
        rendererDragSurface.height
      )));
      return true;
    };

    clearDesktopCompactSurfaceDragPrime();
    desktopCompactSurfaceDragActive = true;
    desktopCompactSurfaceDragTarget = startSurface;
    desktopCompactSurfaceDragSettledTarget = null;
    desktopCompactSurfaceDragSettledWorkArea = null;
    desktopCompactSurfaceDragWorkArea = localDragWorkArea || null;
    document.documentElement.classList.add('neko-dragging');
    desktopCompactWindowSnapshot = '';
    applyDesktopCompactNativeRegion(desktopCompactLayout);
    if (hasInitialClientPoint) {
      updateRendererDragTargetFromClientPoint(initialClientX, initialClientY);
    }
    scheduleDesktopCompactRelayout();

    var finished = false;
    var handlePointerMove = function (event) {
      if (hasPointerId && event.pointerId !== pointerId) return;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      updateRendererDragTargetFromClientPoint(Number(event.clientX), Number(event.clientY));
    };
    desktopCompactSurfaceDragCleanupForTutorial = function (reason) {
      document.documentElement.classList.remove('neko-dragging');
      document.removeEventListener('pointermove', handlePointerMove, true);
      document.removeEventListener('pointerup', finishRendererDrag, true);
      document.removeEventListener('pointercancel', finishRendererDrag, true);
      window.removeEventListener('blur', finishRendererDrag);
    };
    var finishRendererDrag = function (event) {
      if (finished) return;
      if (event && hasPointerId && event.pointerId !== pointerId) return;
      finished = true;
      desktopCompactSurfaceDragCancelForTutorial = null;
      var cleanupDrag = desktopCompactSurfaceDragCleanupForTutorial;
      desktopCompactSurfaceDragCleanupForTutorial = null;
      if (typeof cleanupDrag === 'function') cleanupDrag('finish');
      var releasedSurface = normalizeRect(desktopCompactSurfaceDragTarget);
      if (releasedSurface) {
        saveDesktopCompactSurfacePosition(releasedSurface);
        saveDesktopCompactSurfaceWidth(releasedSurface.width);
        desktopCompactSurfaceDragSettledTarget = releasedSurface;
        desktopCompactSurfaceDragSettledWorkArea = desktopCompactSurfaceDragWorkArea || null;
      }
      clearDesktopCompactSurfaceDragPrime();
      desktopCompactSurfaceDragActive = false;
      desktopCompactSurfaceDragTarget = null;
      desktopCompactSurfaceDragWorkArea = null;
      desktopCompactWindowSnapshot = '';
      desktopCompactPendingWindowBounds = null;
      scheduleDesktopCompactRelayout();
    };
    desktopCompactSurfaceDragCancelForTutorial = function (reason) {
      if (finished) return;
      finished = true;
      desktopCompactSurfaceDragCancelForTutorial = null;
      var cleanupDrag = desktopCompactSurfaceDragCleanupForTutorial;
      desktopCompactSurfaceDragCleanupForTutorial = null;
      if (typeof cleanupDrag === 'function') cleanupDrag(reason || 'tutorial-fixed-layout');
      clearDesktopCompactSurfaceDragForTutorialRuntime();
      scheduleDesktopCompactRelayout(reason || 'tutorial-fixed-layout');
    };

    document.addEventListener('pointermove', handlePointerMove, true);
    document.addEventListener('pointerup', finishRendererDrag, true);
    document.addEventListener('pointercancel', finishRendererDrag, true);
    window.addEventListener('blur', finishRendererDrag);
  }

  function startDesktopCompactSurfaceDragPrime(detail) {
    if (!_isNativeWayland) return;
    if (isSurfaceActionLocked()) return;
    if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) return;
    if (desktopCompactSurfaceDragActive) return;
    var layout = desktopCompactLayout || window.__nekoDesktopCompactLayout || null;
    if (!layout || !layout.windowBounds || !layout.surface) {
      layout = ensureDesktopCompactMeasuredFallbackLayout(layout);
    }
    if (!layout || !layout.windowBounds) return;
    clearDesktopCompactSurfaceDragPrime();
    var pointerId = Number(detail && detail.pointerId);
    desktopCompactSurfaceDragPrimePointerId = Number.isFinite(pointerId) ? pointerId : null;
    desktopCompactSurfaceDragPrimeActive = true;
    var finishPrime = function (event) {
      if (
        event
        && desktopCompactSurfaceDragPrimePointerId !== null
        && Number(event.pointerId) !== desktopCompactSurfaceDragPrimePointerId
      ) {
        return;
      }
      clearDesktopCompactSurfaceDragPrime();
      if (!desktopCompactSurfaceDragActive) {
        applyDesktopCompactNativeRegion(desktopCompactLayout || window.__nekoDesktopCompactLayout || null);
      }
    };
    document.addEventListener('pointerup', finishPrime, true);
    document.addEventListener('pointercancel', finishPrime, true);
    window.addEventListener('blur', finishPrime);
    desktopCompactSurfaceDragPrimeCleanup = function () {
      document.removeEventListener('pointerup', finishPrime, true);
      document.removeEventListener('pointercancel', finishPrime, true);
      window.removeEventListener('blur', finishPrime);
    };
    applyDesktopCompactNativeRegion(layout);
  }

  function beginDesktopCompactSurfaceDrag(e) {
    if (desktopCompactSurfaceDragActive) {
      e.stopImmediatePropagation();
      e.preventDefault();
      return;
    }
    e.stopImmediatePropagation();
    e.preventDefault();
    startDesktopCompactSurfaceDragAtScreen(e.screenX, e.screenY);
  }

  function isDesktopCompactDragSurfaceTarget(target) {
    if (!target || !target.closest) return false;
    if (target.closest('[data-compact-no-drag="true"]')) return false;
    return !!target.closest('[data-compact-drag-surface="true"]');
  }

  document.addEventListener('mousedown', function (e) {
    if (e.button !== 0) return;
    if (!isDesktopCompactDragSurfaceTarget(e.target) || getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized) return;
    maybeRaiseDesktopCompactSurfaceForPointer(e);
    if (isSurfaceActionLocked()) return;
    if (_isNativeWayland) return;
    beginDesktopCompactSurfaceDrag(e);
  }, { capture: true });

  document.addEventListener('pointerdown', function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    maybeRaiseDesktopCompactSurfaceForPointer(e);
  }, { capture: true });

  window.addEventListener('neko:compact-surface-drag-prime', function (event) {
    var detail = event && event.detail ? event.detail : {};
    startDesktopCompactSurfaceDragPrime(detail);
  });

  window.addEventListener('neko:compact-surface-drag-prime-end', function (event) {
    var detail = event && event.detail ? event.detail : {};
    if (
      desktopCompactSurfaceDragPrimePointerId !== null
      && Number(detail && detail.pointerId) !== desktopCompactSurfaceDragPrimePointerId
    ) {
      return;
    }
    clearDesktopCompactSurfaceDragPrime();
    if (!desktopCompactSurfaceDragActive) {
      applyDesktopCompactNativeRegion(desktopCompactLayout || window.__nekoDesktopCompactLayout || null);
    }
  });

  // React 侧「按住拖动 compact surface」手势：真实控件都是 no-drag，上面的 mousedown
  // 命中判定不会自动起拖，所以由 React 检测到拖动意图后派发该事件。Wayland 下主进程
  // getCursorScreenPoint 可能不连续，不能稳定驱动 anchorDrag；这里改用 renderer client delta。
  window.addEventListener('neko:compact-surface-drag-grab', function (event) {
    if (isSurfaceActionLocked()) return;
    if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) return;
    if (desktopCompactSurfaceDragActive) return;
    var detail = event && event.detail ? event.detail : {};
    if (_isNativeWayland) {
      startDesktopCompactSurfaceRendererDrag(detail);
      return;
    }
    if (!Number.isFinite(detail.screenX) || !Number.isFinite(detail.screenY)) return;
    startDesktopCompactSurfaceDragAtScreen(detail.screenX, detail.screenY);
  });

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
      if (_isNativeWayland && isWaylandSelfBallClickTarget(e.target || e.srcElement)) return;
      if (isSurfaceActionLocked()) {
        if (_isNativeWayland && eMinimized) {
          restoreWaylandSelfBallFromClick('self-ball-wayland-mousedown-locked');
        }
        e.stopImmediatePropagation();
        e.preventDefault();
        return;
      }
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
        var startTime = Date.now();
        var clickFallbackTimer = 0;
        var pointerActive = true;
        var startBoundsPromise = typeof W.getBounds === 'function'
          ? W.getBounds().catch(function () { return null; })
          : Promise.resolve(null);
        var onMoveW = null;
        var onUpW = null;
        var onCancelW = null;
        var clearWaylandBallClickFallback = function () {
          if (!clickFallbackTimer) return;
          window.clearTimeout(clickFallbackTimer);
          clickFallbackTimer = 0;
        };
        var cleanupWaylandBallTracking = function () {
          clearWaylandBallClickFallback();
          if (onMoveW) document.removeEventListener('mousemove', onMoveW);
          if (onUpW) document.removeEventListener('mouseup', onUpW);
          if (onMoveW) document.removeEventListener('pointermove', onMoveW);
          if (onUpW) document.removeEventListener('pointerup', onUpW);
          if (onCancelW) document.removeEventListener('pointercancel', onCancelW);
          if (onCancelW) window.removeEventListener('blur', onCancelW);
        };
        var boundsChangedEnough = function (before, after) {
          if (!before || !after) return false;
          return Math.abs(Number(after.x) - Number(before.x)) > DESKTOP_COMPACT_WAYLAND_BALL_DRAG_BOUNDS_DELTA
            || Math.abs(Number(after.y) - Number(before.y)) > DESKTOP_COMPACT_WAYLAND_BALL_DRAG_BOUNDS_DELTA
            || Math.abs(Number(after.width) - Number(before.width)) > DESKTOP_COMPACT_WAYLAND_BALL_DRAG_BOUNDS_DELTA
            || Math.abs(Number(after.height) - Number(before.height)) > DESKTOP_COMPACT_WAYLAND_BALL_DRAG_BOUNDS_DELTA;
        };
        var runWaylandBallClickFallback = function () {
          clickFallbackTimer = 0;
          if (pointerActive) return;
          cleanupWaylandBallTracking();
          if (!eMinimized || moved) return;
          if (isSurfaceActionLocked()) {
            queueWaylandSelfBallClickRestore('self-ball-wayland-click-fallback-locked');
            return;
          }
          startBoundsPromise.then(function (startBounds) {
            if (!eMinimized || moved) return null;
            if (isSurfaceActionLocked()) {
              queueWaylandSelfBallClickRestore('self-ball-wayland-click-fallback-locked');
              return null;
            }
            return (typeof W.getBounds === 'function' ? W.getBounds() : Promise.resolve(null)).then(function (currentBounds) {
              if (!eMinimized || moved) return;
              if (isSurfaceActionLocked()) {
                queueWaylandSelfBallClickRestore('self-ball-wayland-click-fallback-locked');
                return;
              }
              if (boundsChangedEnough(startBounds, currentBounds)) {
                scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-drag-stop');
                return;
              }
              restoreWaylandSelfBallFromClick('self-ball-wayland-click-fallback');
            });
          }).catch(function () {
            if (eMinimized && !moved) {
              restoreWaylandSelfBallFromClick('self-ball-wayland-click-fallback-error');
            }
          });
        };
        onMoveW = (ev) => {
          if (!moved && (Math.abs(ev.screenX - startX) > 3 || Math.abs(ev.screenY - startY) > 3)) {
            moved = true;
            clearWaylandBallClickFallback();
          }
        };
        onUpW = () => {
          pointerActive = false;
          cleanupWaylandBallTracking();
          if (isSurfaceActionLocked()) {
            if (eMinimized) {
              if (!moved) {
                queueWaylandSelfBallClickRestore('self-ball-wayland-click-up-locked');
              } else {
                scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-drag-stop');
              }
            }
            return;
          }
          // During xdg_toplevel.move the compositor intercepts pointer events, so
          // mousemove does not fire and moved stays false even after a real drag.
          // Keep the click window short: a quick tap restores, while press/drag
          // keeps the native Wayland move interaction in control.
          if (eMinimized && !moved && (Date.now() - startTime) < DESKTOP_COMPACT_WAYLAND_BALL_CLICK_MAX_MS) {
            restoreWaylandSelfBallFromClick('self-ball-wayland-click-up');
          } else if (eMinimized) {
            scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-drag-stop');
          }
        };
        onCancelW = () => {
          pointerActive = false;
          cleanupWaylandBallTracking();
          if (eMinimized) {
            startBoundsPromise.then(function (startBounds) {
              return (typeof W.getBounds === 'function' ? W.getBounds() : Promise.resolve(null)).then(function (currentBounds) {
                if (!eMinimized) return;
                if (boundsChangedEnough(startBounds, currentBounds) || moved) {
                  scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-drag-stop');
                }
              });
            }).catch(function () {
              if (eMinimized) scheduleSelfWindowMinimizedBallSettledState('self-ball-wayland-drag-stop');
            });
          }
        };
        document.addEventListener('mousemove', onMoveW);
        document.addEventListener('mouseup', onUpW);
        document.addEventListener('pointermove', onMoveW);
        document.addEventListener('pointerup', onUpW);
        document.addEventListener('pointercancel', onCancelW);
        window.addEventListener('blur', onCancelW);
        clickFallbackTimer = window.setTimeout(runWaylandBallClickFallback, DESKTOP_COMPACT_WAYLAND_BALL_CLICK_FALLBACK_MS);
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
        if (eMinimized) {
          scheduleSelfWindowMinimizedBallState('self-ball-drag-move');
        }
      };
      var onUp = () => {
        document.documentElement.classList.remove('neko-dragging');
        W.dragStop();
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        if (isSurfaceActionLocked()) {
          if (eMinimized) {
            scheduleSelfWindowMinimizedBallSettledState('self-ball-drag-stop');
          }
          return;
        }
        // 折叠态 + 未拖拽 → 点击展开
        if (eMinimized && !moved) {
          restoreCompactDesktopFromMinimizedOrExpand();
        } else if (eMinimized) {
          scheduleSelfWindowMinimizedBallSettledState('self-ball-drag-stop');
        }
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }, { capture: true });

    // On Wayland, Chromium ignores CSS cursor on -webkit-app-region:drag elements.
    // Set the cursor on the html element (which is not subject to that override)
    // when hovering over the drag handle.
    if (_isNativeWayland && dragHandle) {
      var _isNoDragTarget = (target) => {
        return !!(target && target.closest && target.closest('#reactChatWindowCloseButton, #reactChatWindowMinimizeButton'));
      };
      dragHandle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        if (_isNoDragTarget(e.target)) return;
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
      eHiddenByClose = true;
      hideDesktopCompactBallWindow(); // [compact-ball-removed] no-op 兜底（球已停用）
      setDesktopCompactAvatarBoundsSubscription(false);
      ipcRenderer.send('neko:hide-react-chat');
    }, { capture: true });
  }

  // compact 模式下，最小化按钮也由 preload 统一挡流：连点时不让 page 先发第二条
  // 切换信号，再让 preload 按当前最小化态发起 compact/minimized 切换。
  // full 模式也必须先由 preload 捕获：页面原生处理会先卸载 full DOM，
  // 导致后续原生折叠只能缩一个空壳，看起来没有收起动画。
  var minimizeBtn = document.getElementById('reactChatWindowMinimizeButton');
  if (minimizeBtn) {
    minimizeBtn.addEventListener('pointerdown', (e) => {
      if (!isSurfaceActionLocked()) return;
      e.stopImmediatePropagation();
      e.preventDefault();
    }, { capture: true });

    minimizeBtn.addEventListener('click', (e) => {
      var currentMode = getCurrentReactChatSurfaceMode();
      var shell = document.getElementById('react-chat-window-shell');
      var shellCollapsed = shell && shell.classList.contains('neko-e-collapsed');
      var isCompactMode = currentMode === 'compact';
      var isCompactLike = isCompactMode || currentMode === 'minimized' || eMinimized || shellCollapsed;
      if (currentMode === 'full' && !eMinimized && !shellCollapsed) {
        e.stopImmediatePropagation();
        e.preventDefault();
        if (isSurfaceActionLocked()) {
          return;
        }
        collapseLegacyFullForMinimize();
        return;
      }
      if (isCompactLike) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
      if (isSurfaceActionLocked()) {
        e.stopImmediatePropagation();
        e.preventDefault();
        return;
      }
      if (eMinimized) {
        eMinimized = true;
        requestChatSurfaceMode('compact');
        return;
      }
      if (!isCompactLike) {
        return;
      }
      requestChatSurfaceMode('minimized');
    }, { capture: true });
  }


  document.addEventListener('pointerdown', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    queueWaylandSelfBallRestoreFromBlockedEvent(e);
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('pointerup', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    queueWaylandSelfBallRestoreFromBlockedEvent(e);
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('mousedown', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    queueWaylandSelfBallRestoreFromBlockedEvent(e);
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('mouseup', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    queueWaylandSelfBallRestoreFromBlockedEvent(e);
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('click', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    queueWaylandSelfBallRestoreFromBlockedEvent(e);
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('dblclick', (e) => {
    if (!shouldBlockSurfaceActionEvent(e)) return;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  document.addEventListener('click', function (event) {
    if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized || isReactChatWindowHidden()) return;
    var button = getDesktopCompactMinimizeButtonFromTarget(event.target);
    if (!button) return;
    rememberDesktopCompactMinimizeButtonScreenRect(button);
  }, true);

  window.addEventListener('react-chat-window:chat-surface-mode-change', (event) => {
    var detail = event && event.detail ? event.detail : {};
    var mode = detail.mode || '';
    var sourceWasLegacyFull = mode === 'full';
    // Desktop compact only switches compact ↔ minimized; legacy full is hosted elsewhere.
    if (mode === 'full') mode = 'compact';
    eHiddenByClose = false;
    if (mode !== 'minimized') {
      clearDesktopCompactMinimizeButtonScreenRect();
    }
    if (isSurfaceActionLocked()) {
      requestChatSurfaceMode(mode);
      return;
    }
    if (mode === 'compact') {
      if (eMinimized) {
        requestChatSurfaceMode('compact');
        return;
      }
      if (sourceWasLegacyFull) {
        // 旧版页面 bundle 的 getChatSurfaceMode() 可能仍上报 'full'。activateDesktopCompactWindow()
        // 内部会重新读取 getCurrentReactChatSurfaceMode()，若 host 仍是 'full' 会直接早退，导致事件
        // 被记成 compact、但 compact 窗口布局 / native 命中区从未激活。这里先把 host 推到 compact，
        // 确保后续读到的模式是 compact。新版 host 已经是 compact 时该调用是 no-op。
        setReactChatSurfaceMode('compact');
      }
      desktopCompactWindowActive = false;
      clearDesktopCompactLayout();
      desktopCompactWindowSnapshot = '';
      setDesktopCompactAvatarBoundsSubscription(true);
      activateDesktopCompactWindow();
      return;
    }
    if (mode === 'minimized') {
      setDesktopCompactAvatarBoundsSubscription(true);
      requestChatSurfaceMode('minimized');
      return;
    }
    setDesktopCompactAvatarBoundsSubscription(false);
    if (eMinimized) {
      requestChatSurfaceMode('compact');
    }
  });

  window.addEventListener('react-chat-window:compact-chat-state-change', function () {
    scheduleDesktopCompactRelayout();
  });

  window.addEventListener('resize', function () {
    if (desktopCompactSurfaceDragActive) return;
    if (desktopCompactUseX11InputShape && getCurrentReactChatSurfaceMode() !== 'compact') {
      sendDesktopCompactFullWindowInputRegion('expanded-resize');
    }
    syncDesktopCompactLayoutToRendererBounds();
    scheduleDesktopCompactRelayout();
  }, true);

  window.addEventListener('neko:compact-surface-resize-request', function (event) {
    var detail = event && event.detail ? event.detail : {};
    var phase = detail.phase;
    var side = detail.side === 'left' ? 'left' : 'right';
    var target = normalizeRect(detail.screenRect);
    if (phase === 'start') {
      // 钉死竖直锚点：用当前已提交布局的 surfaceUnion 顶（layout.surfaceScreenRect.top），
      // 它正是窗口/存储定位所依据的基准；不用 React frame 顶（含偏移、会漂移）。
      var committedSurface = desktopCompactLayout && desktopCompactLayout.surfaceScreenRect;
      desktopCompactSurfaceResizeAnchorTopScreen = (committedSurface && Number.isFinite(Number(committedSurface.top)))
        ? Math.round(Number(committedSurface.top))
        : (target && Number.isFinite(Number(target.top)) ? Math.round(Number(target.top)) : null);
    }
    // 宽度 resize 期间把每个目标的 top 覆盖为锁定锚点：surface 竖直不动，仅宽度/左缘随拖拽变化。
    if (target && Number.isFinite(Number(desktopCompactSurfaceResizeAnchorTopScreen))) {
      target = normalizeRect({
        left: target.left,
        top: desktopCompactSurfaceResizeAnchorTopScreen,
        width: target.width,
        height: target.height
      }) || target;
    }
    if (target) {
      desktopCompactSurfaceResizeTarget = target;
    }
    if (phase === 'start' || phase === 'move') {
      desktopCompactSurfaceResizeActive = true;
      desktopCompactSurfaceResizeSide = side;
      if (phase === 'start' && target) {
        desktopCompactSurfaceResizeMoved = false;
        desktopCompactSurfaceResizeKeepCarrierOnCommit = false;
        desktopCompactSurfaceResizeStartTarget = target;
        desktopCompactSurfaceResizeStartWindowBounds = normalizeWindowBounds(desktopCompactLayout && desktopCompactLayout.windowBounds)
          || getDesktopCompactRendererWindowBounds(null);
      }
      if (phase === 'move') desktopCompactSurfaceResizeMoved = true;
      if (target && phase !== 'start') scheduleDesktopCompactRelayout();
      return;
    }
    if (phase === 'end') {
      var resizeDidMove = desktopCompactSurfaceResizeMoved;
      desktopCompactSurfaceResizeMoved = false;
      desktopCompactSurfaceResizeKeepCarrierOnCommit = detail.keepCarrier === true;
      Promise.resolve(W.getBounds()).then(function (bounds) {
        // 纯点击（没有真正拖动改变宽度）不落库：避免把按下瞬间量到的位置写入存储，
        // 继而在下一次 relayout 时令无边框窗口按该存储位置 + 内边距重新定位、整体下移。
        if (!resizeDidMove) return;
        // desktopCompactSurfaceResizeTarget 的 top 已在收事件时被钉死为起拖锚点
        // （见上方 phase 处理与 layout-change handler），所以这里保存的就是稳定锚点
        // top，竖直零漂移。
        var savedSurface = normalizeRect(desktopCompactSurfaceResizeTarget)
          || getDesktopCompactMeasuredBaseSurfaceScreenRect(bounds);
        if (savedSurface) {
          saveDesktopCompactSurfacePosition(savedSurface);
          saveDesktopCompactSurfaceWidth(savedSurface.width);
        }
      }).catch(function () {}).then(function () {
        var releasedResizeCarrier = normalizeWindowBounds(desktopCompactSurfaceResizeCarrierBounds);
        var passiveResizeCarrier = normalizeWindowBounds(desktopCompactSurfaceResizePassiveCarrierBounds);
        desktopCompactSurfaceResizeActive = false;
        desktopCompactSurfaceResizeTarget = null;
        desktopCompactSurfaceResizeSide = null;
        desktopCompactSurfaceResizeStartTarget = null;
        desktopCompactSurfaceResizeStartWindowBounds = null;
        desktopCompactSurfaceResizeAnchorTopScreen = null;
        desktopCompactSurfaceResizeCarrierBounds = null;
        var keepCarrier = desktopCompactSurfaceResizeKeepCarrierOnCommit;
        desktopCompactSurfaceResizeKeepCarrierOnCommit = false;
        if (!keepCarrier && releasedResizeCarrier && passiveResizeCarrier && !sameWindowBounds(releasedResizeCarrier, passiveResizeCarrier)) {
          desktopCompactWindowSnapshot = '';
          scheduleDesktopCompactRelayout();
        }
      });
    }
  }, true);

  window.addEventListener('neko:compact-history-resize-request', function (event) {
    var detail = event && event.detail ? event.detail : {};
    var phase = detail.phase;
    if (phase === 'start') {
      if (desktopCompactHistoryResizeCommitTimer) {
        window.clearTimeout(desktopCompactHistoryResizeCommitTimer);
        desktopCompactHistoryResizeCommitTimer = 0;
      }
      desktopCompactHistoryResizeActive = true;
      desktopCompactHistoryResizeCommitPending = false;
      desktopCompactHistoryResizeKeepCarrierOnCommit = false;
      startDesktopCompactHistoryResizeIsolation(
        desktopCompactLayout && desktopCompactLayout.windowBounds,
        desktopCompactLayout && desktopCompactLayout.workArea
      );
      desktopCompactHistoryResizeCarrierBounds = historyResizeIsolation && historyResizeIsolation.mode !== 'unsupported-wayland'
        ? normalizeWindowBounds(desktopCompactHistoryResizePassiveCarrierBounds)
        : null;
      desktopCompactWindowSnapshot = '';
      scheduleDesktopCompactRelayout();
      return;
    }
    if (phase === 'end' || phase === 'cancel') {
      if (desktopCompactHistoryResizeCommitTimer) {
        window.clearTimeout(desktopCompactHistoryResizeCommitTimer);
        desktopCompactHistoryResizeCommitTimer = 0;
      }
      desktopCompactHistoryResizeActive = false;
      desktopCompactHistoryResizeCommitPending = true;
      desktopCompactHistoryResizeKeepCarrierOnCommit = detail.keepCarrier === true;
      settleDesktopCompactHistoryResizeIsolation();
      desktopCompactHistoryResizeCarrierBounds = null;
      desktopCompactWindowSnapshot = '';
      desktopCompactHistoryResizeCommitTimer = window.setTimeout(function () {
        if (historyResizeIsolation && historyResizeIsolation.phase === 'settling') {
          resetDesktopCompactHistoryResizeIsolation();
          return;
        }
        desktopCompactHistoryResizeCommitPending = false;
        desktopCompactHistoryResizeKeepCarrierOnCommit = false;
        desktopCompactHistoryResizeCommitTimer = 0;
        desktopCompactWindowSnapshot = '';
        scheduleDesktopCompactRelayout();
      }, 520);
      scheduleDesktopCompactRelayout();
    }
  }, true);

  ipcRenderer.on(WINDOW_CONTROL_CHANNELS.DRAG_ANCHOR_MOVE, function (_event, payload) {
    if (!desktopCompactSurfaceDragActive) return;
    var target = normalizeRect(payload && payload.anchorRect);
    if (!target) return;
    desktopCompactSurfaceDragTarget = target;
    // 主进程随拖拽附带“光标目标屏”工作区，使气泡能被拖到别的屏（跨屏独立）。
    if (payload && payload.workArea) {
      desktopCompactSurfaceDragWorkArea = payload.workArea;
    }
    desktopCompactWindowSnapshot = '';
    scheduleDesktopCompactRelayout();
  });

  window.addEventListener('neko:compact-surface-layout-change', function (event) {
    if (!desktopCompactSurfaceResizeActive) return;
    var detail = event && event.detail ? event.detail : {};
    var target = normalizeRect(detail.screenRect);
    if (!target) return;
    // 与 resize-request 同源：宽度 resize 期间这条 layout-change 也只能改宽度/左缘，
    // 竖直锚点必须保持钉死，否则它会用 React frame 顶覆盖掉 pin，令拖动中 surfaceUnion
    // 瞬间下移一个渲染偏移（界面"向下闪一下"）。
    if (Number.isFinite(Number(desktopCompactSurfaceResizeAnchorTopScreen))) {
      target = normalizeRect({
        left: target.left,
        top: desktopCompactSurfaceResizeAnchorTopScreen,
        width: target.width,
        height: target.height
      }) || target;
    }
    desktopCompactSurfaceResizeTarget = target;
    scheduleDesktopCompactRelayout();
  }, true);

  window.addEventListener('neko:compact-interaction-geometry-change', function (event) {
    if (shouldScheduleDesktopCompactRelayoutForGeometryChange(event && event.detail)) {
      scheduleDesktopCompactRelayout('geometry-change');
    }
  });

  window.addEventListener('neko:compact-tool-wheel-drag-state-change', function (event) {
    var detail = event && event.detail ? event.detail : {};
    applyDesktopCompactToolWheelDragState(detail.active === true);
  }, true);

  window.addEventListener('neko:compact-tool-fan-open-state-change', function (event) {
    var detail = event && event.detail ? event.detail : {};
    applyDesktopCompactToolFanOpenState(detail.open === true);
  }, true);

  window.addEventListener('neko:compact-history-drag-state-change', function (event) {
    applyDesktopCompactHistoryDragStatePayload(event && event.detail);
  }, true);

  window.addEventListener('mousemove', function (event) {
    syncDesktopCompactHistoryPointerPassthroughFromPoint(event.clientX, event.clientY);
  }, true);

  window.addEventListener('mouseup', function () {
    if (!desktopCompactToolWheelDragActive) return;
    applyDesktopCompactToolWheelDragState(false);
  }, true);

  window.addEventListener('pointerup', function () {
    if (!desktopCompactToolWheelDragActive) return;
    applyDesktopCompactToolWheelDragState(false);
  }, true);

  window.addEventListener('pointercancel', function () {
    if (!desktopCompactToolWheelDragActive) return;
    applyDesktopCompactToolWheelDragState(false);
  }, true);

  ipcRenderer.on(PET_CHANNELS.AVATAR_BOUNDS_SYNC, function (_event, payload) {
    desktopCompactAvatarPayload = payload && typeof payload === 'object' ? payload : null;
    if (getCurrentReactChatSurfaceMode() === 'compact' && !eMinimized && !isReactChatWindowHidden()) {
      if (desktopCompactSurfaceDragActive) return;
      if (shouldApplyDesktopCompactAvatarBoundsOnly()) {
        applyDesktopCompactAvatarBoundsOnly(desktopCompactAvatarPayload);
        return;
      }
      activateDesktopCompactWindow();
    }
  });

  ipcRenderer.on(COMPACT_CHAT_BALL_CHANNELS.REQUEST_COMPANION, function () {
    if (isSurfaceActionLocked()) return;
    if (getCurrentReactChatSurfaceMode() !== 'minimized') {
      setReactChatSurfaceMode('minimized');
    }
    scheduleElectronChatMinimizedState('exit-retention-stay');
    window.setTimeout(function () {
      scheduleElectronChatMinimizedState('exit-retention-stay');
    }, 520);
  });

  // 独立球点击经主进程转发到此（CLICK 通道现在只有毛线球在发，旧 #1595 悬浮球已废）。
  // 毛线球折叠路径 —— mode=minimized + eMinimized=true。chatWin 已被 DRAG_MOVE 同步到球
  // 当前位置（opacity 0，球还显示着）。先抓 chatWin 当前 bounds 作为「球 anchor」给
  // doExpand 经折叠差量逆变换反推 stored surface，doExpand 在 chatWin 隐性状态
  // 下定位好 surface 后派 RESTORE_COMPLETE → main restore chatWin opacity 揭示对话框。
  ipcRenderer.on(COMPACT_CHAT_BALL_CHANNELS.CLICK, function (_event, payload) {
    if (isSurfaceActionLocked()) {
      if (eMinimized) {
        requestChatSurfaceMode('compact');
      }
      return;
    }
    if (eMinimized) {
      // 平台分支（#194 Win32 防闪帧 ＋ #192 Linux self-ball/anchorBounds 合并）：
      //
      // Win32/mac（_useExternalMinimizedBallWindow=true，opacity carrier 可用）→ 优先「直接恢复」：
      // 先算最终 compact 窗口 bounds 直接 setBounds 到位、再用 storedSurfaceOnly 把 surface 钉到球位，
      // 全程无 doExpand 的「先 expand 成 440×600 旧大窗再 activate 拉回」中转。那个临时大窗会让
      // activate 把球位 surface 换算成相对临时窗口的视口坐标（左下 0,542）、React 首帧渲染在左下
      // 下一帧才归位 → Win32 层窗口顶出旧合成缓冲 =「输入框从左下闪一帧」。直接恢复根除闪帧。
      // skipBallHide：保留球自身 bounce + RESTORE_ACK 自隐握手，不强制 HIDE 打断 bounce。
      // 直接恢复失败再回退 doExpand。
      //
      // Linux（self-ball，#192：setOpacity() no-op，已改为 React 窗口本体当 88×88 球）→ 优先
      // 用当前 88×88 窗口 bounds 直接恢复；若布局不可用再回退 #192 的 doExpand 路径。
      //
      // 两端的 doExpand 回退都优先用球 CLICK payload 带来的 anchorBounds（#192，避免恢复时丢失球
      // 当前位置），没有再回退读 W.getBounds()。
      var expandWithPayloadAnchor = function () {
        var payloadAnchor = normalizeCollapsedBounds(payload && payload.anchorBounds);
        if (payloadAnchor) {
          _ballAnchorBoundsBeforeExpand = payloadAnchor;
          doExpand({ suppressOnfinishRelayout: true });
          return;
        }
        W.getBounds().then(function (b) {
          if (b && Number.isFinite(b.x) && Number.isFinite(b.y) && Number.isFinite(b.width) && Number.isFinite(b.height)) {
            _ballAnchorBoundsBeforeExpand = { x: b.x, y: b.y, width: b.width, height: b.height };
          } else {
            _ballAnchorBoundsBeforeExpand = null;
          }
          doExpand({ suppressOnfinishRelayout: true });
        }).catch(function () {
          _ballAnchorBoundsBeforeExpand = null;
          doExpand({ suppressOnfinishRelayout: true });
        });
      };
      if (_useExternalMinimizedBallWindow) {
        restoreCompactDesktopFromMinimized({
          skipBallHide: true,
          anchorBounds: payload && payload.anchorBounds
        }).then(function (restored) {
          // true=成功揭示；'queued'/'canceled'=揭示期间被重新折叠或并发抢占（保留最小化态）——两者都不回退 doExpand。
          if (restored === true || restored === 'queued' || restored === 'canceled') return;
          // 直接恢复失败（布局不可用等，restored===false）→ 回退 doExpand。
          expandWithPayloadAnchor();
        });
      } else {
        expandWithPayloadAnchor();
      }
      return;
    }
    // 不 eMinimized 时收到 CLICK：bounce 进行中的二次点击在球侧 pointerdown 已被
    // neko-ball-bouncing 守卫挡掉、根本不会派 CLICK 到这里，所以走到这一步几乎必然是
    // 「上次恢复未闭环 —— RESTORE_COMPLETE/RESTORE_ACK 丢失，球残留可点但 chat 已退出
    // minimized」的卡死态：用户点了残留球，旧代码在此 no-op（注释「双击=no-op」），球永远
    // 点不动。改为补发一次 RESTORE_COMPLETE 兜底：main 幂等复位 chatWin opacity/命中并回 ACK，
    // 残留球收到 ACK + 这次点击重播的 bounce 结束后自行 HIDE，把「点了没反应」救活。
    // （CLICK 通道仅毛线球在发、compact 态无球不会触发，故无条件补发无回归风险。）
    W.getBounds().then(function (bounds) {
      if (!isCarrierWindowCollapsed(bounds)) {
        emitCompactChatRestoreComplete();
        return;
      }
      recoverCompactMinimizedStateFromWindowBounds(payload, {
        restore: true,
      });
    }).catch(function () {
      emitCompactChatRestoreComplete();
    });
  });

  // 托盘 radio「聊天窗口形态：紧凑 / 完整」→ main → 此处。只负责让 React 切 surface 形态。
  // 原生窗口 bounds（compact 小悬浮条 / full 大窗口）由 stage ② b 负责，这里不动。
  ipcRenderer.on(CHAT_SURFACE_CHANNELS.SET_MODE, function (_event, mode) {
    if (mode !== 'full' && mode !== 'compact') return;
    if (isSurfaceActionLocked()) return;
    requestChatSurfaceMode(mode);
  });

  function forceDesktopCompactSurfaceRestoreRelayout() {
    eHiddenByClose = false;
    eMinimized = false;
    setReactChatSurfaceMode('compact', { force: true });
    desktopCompactWindowActive = false;
    desktopCompactWindowSavePending = false;
    desktopCompactWindowRelayoutQueued = false;
    desktopCompactWindowSnapshot = '';
    desktopCompactPendingWindowBounds = null;
    clearDesktopCompactBoundsVerification();
    setDesktopCompactAvatarBoundsSubscription(true);
    [0, 16, 50, 120, 260].forEach(function (delay) {
      window.setTimeout(function () {
        if (document.hidden) return;
        eHiddenByClose = false;
        if (getCurrentReactChatSurfaceMode() !== 'compact' || eMinimized) return;
        desktopCompactWindowSnapshot = '';
        scheduleDesktopCompactRelayout();
      }, delay);
    });
  }

  ipcRenderer.on(CHAT_SURFACE_CHANNELS.RESTORE_COMPACT_SURFACE, function () {
    // full 独立窗口切回 compact 时，主进程可能刚把透明 carrier 从 1x1 park 恢复。
    // 这里主动唤醒 compact 布局，避免只依赖 visibilitychange 而卡在不可见尺寸。
    forceDesktopCompactSurfaceRestoreRelayout();
  });

  requestAnimationFrame(function () {
    var mode = getCurrentReactChatSurfaceMode();
    setDesktopCompactAvatarBoundsSubscription(mode === 'compact' || mode === 'minimized');
    if (mode === 'compact' && !eMinimized && !isReactChatWindowHidden()) {
      activateDesktopCompactWindow();
    }
  });

  // 页面在折叠态刷新时，渲染进程状态会丢失，但 BrowserWindow 仍可能保持折叠尺寸。
  // 主动恢复折叠状态和上次展开尺寸，避免用户点击后把折叠尺寸当成目标尺寸继续“展开一点点”。
  requestAnimationFrame(function () {
    var retries = 0;
    var tryRecover = function () {
      W.getBounds().then(function (bounds) {
        if (!bounds) return;
        if (isCarrierWindowCollapsed(bounds)) {
          recoverCompactMinimizedStateFromWindowBounds(null, {
            restore: false,
            silentRestore: true,
          });
          return;
        }
        if (retries < 2) {
          retries += 1;
          window.setTimeout(tryRecover, 80);
        }
      }).catch(function () {
        if (retries < 2) {
          retries += 1;
          window.setTimeout(tryRecover, 80);
        }
      });
    };
    tryRecover();
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
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupReactChatDomInterceptors, { once: true });
} else {
  setupReactChatDomInterceptors();
}
