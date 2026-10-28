/**
 * websocket-bridge.js
 * contextBridge 版 WebSocket 代理工厂（WO-278 §2 的降险件）。
 *
 * 为什么有这个文件
 * ----------------
 * 现在的 `preload-chat.js` / `-chat-full` / `-chat-react` 都是 `window.WebSocket = WSProxy`
 * —— **构造器替换**。而 contextBridge **顶替不了页面已有的全局构造器**，
 * 所以这三扇窗永远开不了 contextIsolation。
 *
 * 出路是让**页面**主动从 bridge 取一个工厂：`const s = window.nekoWebSocket.create(url)`。
 * 但桥有个硬约束：**只能传函数与纯数据**（结构化克隆），所以不能把 `WSProxy` 类直接搬过去。
 * 本模块就是"能被桥过去的那个形态"：一个纯函数，返回**只含函数的普通对象**。
 *
 * 三个必须保持的语义（都是从现有 WSProxy 抄的，改错会回归线上事故）
 * ---------------------------------------------------------------
 * 1. **CONNECTING 状态不吃 CLOSED**：切档案时刚 new 出来的代理，不该吃上一轮真 WS
 *    遗留的 CLOSED —— 否则页面 onclose 会排一个 stale auto-reconnect，
 *    3s 后造出永远停在 CONNECTING 的**僵尸代理**（源注释里明确记过这个坑）。
 * 2. **非 OPEN 状态 `send` 静默丢弃**：与原生 WebSocket 一致（原生会抛，但这里沿用旧行为，
 *    因为页面已有大量 `if (readyState === OPEN) send()` 的调用，改成抛反而会炸）。
 * 3. **`close()` 是本地动作**：不发 IPC，直接置 CLOSED 并派 close 事件。
 *
 * 为什么依赖注入
 * --------------
 * 不 `require('electron')` ⇒ 纯 node 可单测（`tests/websocket-bridge.test.js`）。
 * 真实 preload 里传 `{ ipc: ipcRenderer, channels: WS_PROXY_CHANNELS }` 即可。
 */

'use strict';

const CONNECTING = 0;
const OPEN = 1;
const CLOSING = 2;
const CLOSED = 3;

/**
 * ⚠️ 回调参数必须是**纯数据**，不能是 Event 实例。
 *
 * contextBridge 只做结构化克隆：preload 世界造的 `MessageEvent` / `CloseEvent`
 * 过桥后只剩 `{isTrusted}`，`data` / `code` / `reason` 全部丢失
 * （真 Electron 实测：页面收到的 message/close 事件只有 `isTrusted`）。
 * 所以这里只派 payload，页面世界的事件对象由 ws-adapter.js 那边重建。
 */

/**
 * @param {object} deps
 * @param {{ send: Function, on: Function, removeListener: Function }} deps.ipc
 *        Electron 的 ipcRenderer（或单测里的假货）。
 * @param {{ READY: string, RAW_MESSAGE: string, RAW_SEND: string, CLOSED: string }} deps.channels
 * @param {(msg: string) => void} [deps.log]
 */
function createWebSocketBridge(deps) {
  const ipc = deps.ipc;
  const channels = deps.channels;
  const log = typeof deps.log === 'function' ? deps.log : function () {};

  if (!ipc || typeof ipc.send !== 'function' || typeof ipc.on !== 'function') {
    throw new TypeError('createWebSocketBridge: ipc 至少需要 send / on');
  }
  if (!channels || !channels.READY || !channels.RAW_MESSAGE || !channels.RAW_SEND || !channels.CLOSED) {
    throw new TypeError('createWebSocketBridge: channels 缺少 READY/RAW_MESSAGE/RAW_SEND/CLOSED');
  }

  /**
   * 建一个代理实例。返回的对象**只含函数与常量**，可以直接塞进 exposeInMainWorld。
   *
   * ⚠️ 页面必须用 `addEventListener`，不能写 `sock.onopen = fn` ——
   * 赋值语义过不了桥（写进去的只是快照对象的属性，preload 收不到）。
   */
  function create(url, protocols) {
    const listeners = Object.create(null);
    let readyState = CONNECTING;
    let disposed = false;

    function fire(type, payload) {
      const list = listeners[type];
      if (!list || !list.length) return;
      // 拷贝一份再遍历：回调里 removeEventListener 是常见写法
      list.slice().forEach(function (fn) {
        try {
          fn(payload);
        } catch (err) {
          log('[WS Bridge] listener error (' + type + '): ' + (err && err.message));
        }
      });
    }

    const onReady = function () {
      if (disposed || readyState === OPEN) {
        // 重复 READY（Pet 真 WS 重连时会晚到一条）不改状态、不重复派事件
        log('[WS Bridge] spurious READY ignored, state=' + readyState);
        return;
      }
      readyState = OPEN;
      fire('open');
    };

    const onMessage = function (_event, data) {
      if (disposed || readyState !== OPEN) return; // 语义 2：非 OPEN 丢弃
      fire('message', data);
    };

    const onClosed = function (_event, data) {
      // 语义 1：CONNECTING 的代理不吃上一轮遗留的 CLOSED，否则会造僵尸代理
      if (disposed || readyState !== OPEN) return;
      readyState = CLOSED;
      const code = (data && data.code) || 1006;
      const reason = (data && data.reason) || '';
      fire('close', { code: code, reason: reason });
      cleanup();
    };

    function cleanup() {
      disposed = true;
      if (typeof ipc.removeListener === 'function') {
        ipc.removeListener(channels.READY, onReady);
        ipc.removeListener(channels.RAW_MESSAGE, onMessage);
        ipc.removeListener(channels.CLOSED, onClosed);
      }
    }

    ipc.on(channels.READY, onReady);
    ipc.on(channels.RAW_MESSAGE, onMessage);
    ipc.on(channels.CLOSED, onClosed);

    return {
      url: url,
      protocols: protocols,
      CONNECTING: CONNECTING,
      OPEN: OPEN,
      CLOSING: CLOSING,
      CLOSED: CLOSED,
      send: function (data) {
        if (readyState !== OPEN) return; // 语义 2
        ipc.send(channels.RAW_SEND, data);
      },
      close: function (code, reason) {
        if (readyState === CLOSED) return;
        readyState = CLOSED; // 语义 3：本地动作
        fire('close', { code: code || 1000, reason: reason || '' });
        cleanup();
      },
      addEventListener: function (type, fn) {
        if (typeof fn !== 'function') return;
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(fn);
      },
      removeEventListener: function (type, fn) {
        const list = listeners[type];
        if (!list) return;
        listeners[type] = list.filter(function (f) {
          return f !== fn;
        });
      },
      /** 页面用它替代 `sock.readyState`（属性过桥会变成死值）。 */
      getReadyState: function () {
        return readyState;
      },
    };
  }

  return {
    create: create,
    CONNECTING: CONNECTING,
    OPEN: OPEN,
    CLOSING: CLOSING,
    CLOSED: CLOSED,
  };
}

module.exports = {
  createWebSocketBridge: createWebSocketBridge,
  CONNECTING: CONNECTING,
  OPEN: OPEN,
  CLOSING: CLOSING,
  CLOSED: CLOSED,
};
