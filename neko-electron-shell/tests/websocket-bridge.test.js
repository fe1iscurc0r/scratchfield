/**
 * websocket-bridge.js 的纯 node 单测（WO-278 §2.5 的降险件）。
 *
 * 不接 Electron、不起窗口：用一个假 ipc 驱动状态机，把**三条必须保持的语义**钉住：
 *   1) CONNECTING 的代理不吃上一轮遗留的 CLOSED（否则会造出僵尸代理）
 *   2) 非 OPEN 的 send 静默丢弃
 *   3) close() 是本地动作（不发 IPC）
 *
 * 这三条任意一条被改坏，页面侧就会出现"看起来连上了其实没连"或"3 秒后自动重连死循环"。
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { createWebSocketBridge } = require('../src/websocket-bridge');

const CH = {
  READY: 'neko:ws-ready',
  RAW_MESSAGE: 'neko:ws-raw-message',
  RAW_SEND: 'neko:ws-raw-send',
  CLOSED: 'neko:ws-closed',
};

/** 假的 ipcRenderer：记录 send，按 channel 存 handler，支持 removeListener。 */
function makeFakeIpc() {
  const handlers = Object.create(null);
  const sent = [];
  return {
    sent,
    handlers,
    send(channel, data) {
      sent.push({ channel, data });
    },
    on(channel, fn) {
      if (!handlers[channel]) handlers[channel] = [];
      handlers[channel].push(fn);
    },
    removeListener(channel, fn) {
      const list = handlers[channel];
      if (!list) return;
      handlers[channel] = list.filter((f) => f !== fn);
    },
    /** 模拟主进程 → 渲染进程的事件 */
    emit(channel, data) {
      (handlers[channel] || []).forEach((fn) => fn({}, data));
    },
    listenerCount(channel) {
      return (handlers[channel] || []).length;
    },
  };
}

function makeBridge() {
  const ipc = makeFakeIpc();
  const bridge = createWebSocketBridge({ ipc, channels: CH });
  return { ipc, bridge };
}

test('初始状态是 CONNECTING，且 send 被静默丢弃', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  assert.strictEqual(sock.getReadyState(), bridge.CONNECTING);
  sock.send('hello');
  assert.deepStrictEqual(ipc.sent, [], 'CONNECTING 时不得发 RAW_SEND');
});

test('READY 后进入 OPEN 并派 open 事件（addEventListener）', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  const seen = [];
  sock.addEventListener('open', () => seen.push('open'));
  ipc.emit(CH.READY);
  assert.strictEqual(sock.getReadyState(), bridge.OPEN);
  assert.deepStrictEqual(seen, ['open']);
});

test('重复 READY 不重复派 open（Pet 重连会晚到一条）', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  let opens = 0;
  sock.addEventListener('open', () => (opens += 1));
  ipc.emit(CH.READY);
  ipc.emit(CH.READY);
  assert.strictEqual(opens, 1, '重复 READY 只应派一次 open');
  assert.strictEqual(sock.getReadyState(), bridge.OPEN);
});

test('【回归守卫】CONNECTING 时收到 CLOSED 不得派 close（僵尸代理根因）', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  let closes = 0;
  sock.addEventListener('close', () => (closes += 1));
  // 上一轮真 WS 的 CLOSED 晚到，此时新代理还在 CONNECTING
  ipc.emit(CH.CLOSED, { code: 1006, reason: 'stale' });
  assert.strictEqual(closes, 0, 'CONNECTING 不该吃 CLOSED，否则页面会排 stale auto-reconnect');
  assert.strictEqual(sock.getReadyState(), bridge.CONNECTING);
});

test('OPEN 后 CLOSED 派 close（带 code/reason），并进入 CLOSED', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  const events = [];
  sock.addEventListener('close', (payload) => events.push({ code: payload.code, reason: payload.reason }));
  ipc.emit(CH.READY);
  ipc.emit(CH.CLOSED, { code: 1001, reason: 'going away' });
  assert.deepStrictEqual(events, [{ code: 1001, reason: 'going away' }]);
  assert.strictEqual(sock.getReadyState(), bridge.CLOSED);
});

test('回调参数是纯数据（Event 实例过不了 contextBridge）', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  const seen = [];
  sock.addEventListener('message', (payload) => seen.push(['message', payload]));
  sock.addEventListener('close', (payload) => seen.push(['close', payload]));
  ipc.emit(CH.READY);
  ipc.emit(CH.RAW_MESSAGE, 'plain-string');
  ipc.emit(CH.CLOSED, { code: 1006, reason: 'lost' });
  assert.deepStrictEqual(seen, [
    ['message', 'plain-string'],
    ['close', { code: 1006, reason: 'lost' }],
  ]);
  assert.strictEqual(typeof seen[0][1], 'string', 'message 必须直接传 data，不能包 Event');
  assert.deepStrictEqual(Object.keys(seen[1][1]).sort(), ['code', 'reason']);
});

test('RAW_MESSAGE 只在 OPEN 时派 message', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  const got = [];
  sock.addEventListener('message', (payload) => got.push(payload));
  ipc.emit(CH.RAW_MESSAGE, 'too-early'); // CONNECTING：丢弃
  ipc.emit(CH.READY);
  ipc.emit(CH.RAW_MESSAGE, 'payload');
  assert.deepStrictEqual(got, ['payload']);
});

test('OPEN 时 send 走 RAW_SEND；close() 之后不再发', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  ipc.emit(CH.READY);
  sock.send('a');
  sock.close(1000, 'bye');
  sock.send('b');
  assert.deepStrictEqual(ipc.sent, [{ channel: CH.RAW_SEND, data: 'a' }]);
  assert.strictEqual(sock.getReadyState(), bridge.CLOSED);
});

test('close() 是本地动作：不发任何 IPC，但派 close', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  let closes = 0;
  sock.addEventListener('close', () => (closes += 1));
  sock.close(1000, 'local');
  assert.strictEqual(closes, 1);
  assert.deepStrictEqual(ipc.sent, [], 'close() 不该发 IPC');
});

test('removeEventListener 生效', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  let n = 0;
  const fn = () => (n += 1);
  sock.addEventListener('open', fn);
  sock.removeEventListener('open', fn);
  ipc.emit(CH.READY);
  assert.strictEqual(n, 0);
});

test('多实例状态互不干扰', () => {
  const { ipc, bridge } = makeBridge();
  const a = bridge.create('ws://a');
  const b = bridge.create('ws://b');
  a.addEventListener('close', () => {});
  ipc.emit(CH.READY); // 两个都会 OPEN（同一个 READY 广播）
  assert.strictEqual(a.getReadyState(), bridge.OPEN);
  assert.strictEqual(b.getReadyState(), bridge.OPEN);
  a.close(1000, 'only-a');
  assert.strictEqual(a.getReadyState(), bridge.CLOSED);
  assert.strictEqual(b.getReadyState(), bridge.OPEN, '关一个不该影响另一个');
});

test('CLOSED / close() 之后注销 IPC 监听（不泄漏）', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  assert.strictEqual(ipc.listenerCount(CH.READY), 1);
  ipc.emit(CH.READY);
  ipc.emit(CH.CLOSED, { code: 1006 });
  assert.strictEqual(ipc.listenerCount(CH.READY), 0, 'READY 监听应被注销');
  assert.strictEqual(ipc.listenerCount(CH.RAW_MESSAGE), 0);
  assert.strictEqual(ipc.listenerCount(CH.CLOSED), 0);
  void sock;
});

test('监听器抛错不影响其它监听器，也不打断状态机', () => {
  const { ipc, bridge } = makeBridge();
  const sock = bridge.create('ws://localhost/x');
  const calls = [];
  sock.addEventListener('open', () => {
    throw new Error('boom');
  });
  sock.addEventListener('open', () => calls.push('second'));
  assert.doesNotThrow(() => ipc.emit(CH.READY));
  assert.deepStrictEqual(calls, ['second']);
  assert.strictEqual(sock.getReadyState(), bridge.OPEN);
});
