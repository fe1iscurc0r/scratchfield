/**
 * ws-adapter.js
 * 页面侧的 WebSocket 适配器（WO-278 §2 的一部分）。
 *
 * 解决什么问题
 * ------------
 * Electron 侧启用 `contextIsolation: true` 后，preload 不能再写 `window.WebSocket = WSProxy`
 * （contextBridge 顶替不了全局构造器）。只能改成暴露工厂：
 *
 *     window.nekoWebSocket.create(url)  →  { send, close, addEventListener, removeEventListener, getReadyState }
 *
 * 但工厂返回的是**普通对象**，跟原生 WebSocket 有两处语义差异，页面里用得很多：
 *   1. `sock.readyState` —— 桥过来的属性是**快照**，不会跟着状态变（页面用了 32 处）
 *   2. `sock.onopen = fn` —— **赋值语义过不了桥**，写了也不生效（页面用了 4 处）
 *
 * 本适配器把这两处差异**在页面里补回来**：内部用事件驱动维护 `readyState`，
 * 并把 `onX = fn` 映射成 `addEventListener`。于是页面那 1 + 4 + 32 处调用**一行都不用改**，
 * 只需把建连接的那一处换成 `__nekoCreateWebSocket(url)`。
 *
 * 没有 `window.nekoWebSocket`（浏览器直开 / 未隔离窗口）时，直接返回原生 WebSocket。
 */
(function (global) {
  'use strict';

  var CONNECTING = 0;
  var OPEN = 1;
  var CLOSING = 2;
  var CLOSED = 3;

  var EVENT_TYPES = ['open', 'message', 'close', 'error'];

  /**
   * @param {string} url
   * @param {string|string[]} [protocols]
   * @returns {WebSocket|object} 原生 WebSocket，或语义对齐的适配器
   */
  function createWebSocket(url, protocols) {
    var bridge = global.nekoWebSocket;
    if (!bridge || typeof bridge.create !== 'function') {
      return new global.WebSocket(url, protocols);
    }

    var handle = bridge.create(url, protocols);
    var listeners = Object.create(null);
    var handlers = Object.create(null);
    var readyState =
      typeof handle.getReadyState === 'function' ? handle.getReadyState() : CONNECTING;

    var adapter = {
      url: url,
      protocols: protocols,
      CONNECTING: CONNECTING,
      OPEN: OPEN,
      CLOSING: CLOSING,
      CLOSED: CLOSED,

      send: function (data) {
        // 状态判断交给 handle（它才是权威），这里只做转调
        handle.send(data);
      },

      close: function (code, reason) {
        if (readyState === CLOSED) return;
        readyState = CLOSING;
        handle.close(code, reason);
      },

      addEventListener: function (type, fn) {
        if (typeof fn !== 'function') return;
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(fn);
      },

      removeEventListener: function (type, fn) {
        var list = listeners[type];
        if (!list) return;
        listeners[type] = list.filter(function (f) {
          return f !== fn;
        });
      },

      /** 兼容 `sock.readyState` 的读法（原生是属性，这里是真的活值，不是快照）。 */
      getReadyState: function () {
        return readyState;
      },
    };

    Object.defineProperty(adapter, 'readyState', {
      get: function () {
        return readyState;
      },
      enumerable: true,
      configurable: true,
    });

    function emit(type, event) {
      // 先 onX 再 addEventListener（与原生顺序一致），任一抛错不影响其它
      var own = handlers[type];
      if (typeof own === 'function') {
        try {
          own.call(adapter, event);
        } catch (_) {}
      }
      var list = listeners[type];
      if (!list || !list.length) return;
      list.slice().forEach(function (fn) {
        try {
          fn.call(adapter, event);
        } catch (_) {}
      });
    }

    /**
     * 桥只传纯 payload（contextBridge 克隆掉 Event 实例的字段），
     * 页面世界的事件对象必须在这里重建，否则 e.data / e.code 全是 undefined。
     */
    function makePageEvent(type, payload) {
      var Ctor = type === 'message'
        ? global.MessageEvent
        : (type === 'close' ? global.CloseEvent : global.Event);
      try {
        if (typeof Ctor === 'function') {
          if (type === 'message') return new Ctor('message', { data: payload });
          if (type === 'close') {
            return new Ctor('close', {
              code: payload && payload.code,
              reason: payload && payload.reason,
            });
          }
          return new Ctor(type);
        }
      } catch (_) {}
      var ev = { type: type, target: adapter, currentTarget: adapter };
      if (type === 'message') ev.data = payload;
      if (type === 'close') {
        ev.code = payload && payload.code;
        ev.reason = payload && payload.reason;
      }
      return ev;
    }

    EVENT_TYPES.forEach(function (type) {
      Object.defineProperty(adapter, 'on' + type, {
        get: function () {
          return handlers[type] || null;
        },
        set: function (fn) {
          handlers[type] = typeof fn === 'function' ? fn : null;
        },
        enumerable: true,
        configurable: true,
      });

      handle.addEventListener(type, function (payload) {
        if (type === 'open') readyState = OPEN;
        else if (type === 'close') readyState = CLOSED;
        emit(type, makePageEvent(type, payload));
      });
    });

    return adapter;
  }

  global.__nekoCreateWebSocket = createWebSocket;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { createWebSocket: createWebSocket };
  }
})(typeof window !== 'undefined' ? window : globalThis);
