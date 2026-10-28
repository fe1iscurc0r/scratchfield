/**
 * ws-adapter.js 的纯 node 测试（WO-278 §2）。
 *
 * 不加载页面、不起 Electron：造一个假 window + 假 bridge 句柄，
 * 把"页面依赖的两处语义"逐条钉住：
 *   1. `sock.readyState` 必须是**活值**（跟着 open/close 变，不是快照）
 *   2. `sock.onopen = fn` 赋值必须生效（桥工厂本身不支持，靠适配器补）
 * 另外验证：无 bridge 时退化成原生 WebSocket。
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

/** 造一个假 window：带 WebSocket 与可选 bridge。 */
function makeWindow(withBridge) {
  const win = {};
  win.WebSocket = function FakeNativeWebSocket(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    this.send = (d) => this.sent.push(d);
    this.close = () => {
      this.readyState = 3;
    };
  };

  if (withBridge) {
    // 假 bridge 句柄：只有函数，没有活属性（正是 contextBridge 过桥后的样子）
    let state = 0;
    const listeners = Object.create(null);
    const fire = (type, event) => (listeners[type] || []).forEach((fn) => fn(event));
    win._bridgeHandle = {
      sent: [],
      send(d) {
        this.sent.push(d);
      },
      close() {
        state = 3;
        fire('close', { type: 'close', code: 1000, reason: 'local' });
      },
      getReadyState() {
        return state;
      },
      addEventListener(type, fn) {
        if (!listeners[type]) listeners[type] = [];
        listeners[type].push(fn);
      },
      removeEventListener(type, fn) {
        listeners[type] = (listeners[type] || []).filter((f) => f !== fn);
      },
      // 测试用：模拟主进程推来的事件
      _fire(type, event) {
        if (type === 'open') state = 1;
        if (type === 'close') state = 3;
        fire(type, event || { type });
      },
    };
    win.nekoWebSocket = {
      create() {
        return win._bridgeHandle;
      },
    };
  }
  return win;
}

/** 用假 window 加载适配器（每次重新求值，避免模块级状态串味）。 */
function loadAdapter(win) {
  const file = path.join(__dirname, '../../static/app/ws-adapter.js');
  const code = require('node:fs').readFileSync(file, 'utf8');
  // 适配器是 IIFE，参数是 `typeof window !== 'undefined' ? window : globalThis`
  const fn = new Function('window', 'globalThis', 'module', code);
  const moduleShim = { exports: {} };
  fn(win, win, moduleShim);
  return moduleShim.exports.createWebSocket;
}

test('没有 bridge 时退化成原生 WebSocket', () => {
  const win = makeWindow(false);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  assert.ok(sock instanceof win.WebSocket, '应返回原生实例');
});

test('有 bridge 时返回适配器，readyState 是活值（不是快照）', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  assert.strictEqual(sock.readyState, 0, '初始 CONNECTING');
  win._bridgeHandle._fire('open');
  assert.strictEqual(sock.readyState, 1, 'open 之后必须变 OPEN —— 快照实现会失败在这里');
  win._bridgeHandle._fire('close', { type: 'close', code: 1006 });
  assert.strictEqual(sock.readyState, 3, 'close 之后必须变 CLOSED');
});

test('`sock.onopen = fn` 赋值生效（桥工厂本身不支持赋值语义）', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  let hits = 0;
  sock.onopen = () => (hits += 1);
  win._bridgeHandle._fire('open');
  assert.strictEqual(hits, 1);
  assert.strictEqual(typeof sock.onopen, 'function', 'onopen 应能读回已赋的函数');
});

test('onmessage / onclose 同样生效，且能拿到事件对象', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  const got = [];
  sock.onmessage = (e) => got.push(['message', e.data]);
  sock.onclose = (e) => got.push(['close', e.code]);
  win._bridgeHandle._fire('open');
  // 桥送的是 Pet 的 `event.data` 原始字符串（见 preload-pet.js 的 RAW_MESSAGE send），
  // close 才是 { code, reason } 对象。夹具按真实形状给。
  win._bridgeHandle._fire('message', 'hello');
  win._bridgeHandle._fire('close', { code: 1001 });
  assert.deepStrictEqual(got, [
    ['message', 'hello'],
    ['close', 1001],
  ]);
});

test('addEventListener 与 onX 同时挂时两个都触发，顺序是 onX 在前', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  const order = [];
  sock.onopen = () => order.push('on');
  sock.addEventListener('open', () => order.push('listener'));
  win._bridgeHandle._fire('open');
  assert.deepStrictEqual(order, ['on', 'listener']);
});

test('removeEventListener 生效', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  let n = 0;
  const fn = () => (n += 1);
  sock.addEventListener('message', fn);
  sock.removeEventListener('message', fn);
  win._bridgeHandle._fire('open');
  win._bridgeHandle._fire('message', { type: 'message', data: 'x' });
  assert.strictEqual(n, 0);
});

test('send 走 handle；close 之后 readyState 立刻 CLOSED', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  win._bridgeHandle._fire('open');
  sock.send('payload');
  assert.deepStrictEqual(win._bridgeHandle.sent, ['payload']);
  sock.close(1000, 'bye');
  assert.strictEqual(sock.readyState, 3);
  sock.close(1000, 'again'); // 幂等：不重复触发
});

test('常量挂在实例上（页面可能用 sock.OPEN）', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  assert.strictEqual(sock.CONNECTING, 0);
  assert.strictEqual(sock.OPEN, 1);
  assert.strictEqual(sock.CLOSING, 2);
  assert.strictEqual(sock.CLOSED, 3);
});

test('监听器抛错不影响其它监听器，也不破坏 readyState', () => {
  const win = makeWindow(true);
  const create = loadAdapter(win);
  const sock = create('ws://x');
  const seen = [];
  sock.onopen = () => {
    throw new Error('boom');
  };
  sock.addEventListener('open', () => seen.push('second'));
  win._bridgeHandle._fire('open');
  assert.deepStrictEqual(seen, ['second']);
  assert.strictEqual(sock.readyState, 1);
});

console.log('ws-adapter tests passed');
