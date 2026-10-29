/**
 * WO-278 P2-E · 点歌台（Jukebox）双端联跑
 *
 * 与 `preload-page-global.contract.test.js` 的分工：
 *   - 那个是**静态**契约（数处数、查键名有没有写）；
 *   - 这个是**运行时**验证：同一个 vm 上下文里同时载入
 *       真 preload-pet.js（`process.contextIsolated = true`）
 *       + 真页面桥 pet-host-bridge.js
 *       + 假 Jukebox
 *     然后真的触发 IPC handler，看页面侧方法有没有被调到、参数对不对。
 *
 * 为什么必须两端一起跑：只测一边证明不了「键名对得上」。
 * preload 写 `Jukebox.stopVMD`、页面写 `jukebox.stopVMD`，两边各自单测都能过，
 * 合起来是永久 undefined —— 这正是迁移最容易犯、也最难在静态断言里发现的错。
 *
 * 边界（如实登记）：vm 里没有真正的 contextBridge 隔离边界，
 * 它验证的是**契约与调用链**，不是 Chromium 的序列化规则。
 * 序列化这一层只能真机验（petWindow 目前仍是 contextIsolation:false，尚未启用）。
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PRELOAD = path.resolve(__dirname, '..', 'src', 'preload-pet.js');
const PAGE_BRIDGE = path.resolve(
  __dirname, '..', '..', 'NEKO', 'N.E.K.O', 'static', 'app', 'pet-host-bridge.js');
const IPC_CHANNELS = path.resolve(__dirname, '..', 'src', 'ipc-channels.js');

const CH = require(IPC_CHANNELS).JUKEBOX_CHANNELS;

/**
 * 造一个「隔离态的 pet 窗」并载入两端。
 * @param {object|null} jukebox 假 Jukebox；传 null 表示页面还没建出实例
 */
function bootPetIsolated(jukebox) {
  const handlers = new Map();   // channel -> handler
  const exposed = Object.create(null);
  const sent = [];

  const doc = {
    addEventListener() {}, removeEventListener() {},
    createElement: () => ({ style: {}, appendChild() {}, addEventListener() {}, remove() {} }),
    body: { appendChild() {}, style: {}, classList: { add() {}, remove() {} } },
    documentElement: { style: {}, classList: { add() {}, remove() {}, toggle() {} } },
    readyState: 'complete',
    querySelector: () => null, querySelectorAll: () => [],
    getElementById: () => null, createTextNode: () => ({}),
    head: { appendChild() {} },
  };

  const win = new Proxy({}, {
    get(t, prop) {
      if (prop in t) return t[prop];
      if (prop === 'document') return doc;
      if (prop === 'location') return { href: 'http://127.0.0.1:48911/', origin: 'http://127.0.0.1:48911', search: '' };
      if (prop === 'navigator') return { userAgent: 'node', platform: 'win32', language: 'zh-CN' };
      if (prop === 'addEventListener' || prop === 'removeEventListener' || prop === 'dispatchEvent') return () => {};
      if (prop === 'getComputedStyle') return () => ({ getPropertyValue: () => '' });
      if (prop === 'matchMedia') return () => ({ matches: false, addEventListener() {} });
      if (prop === 'requestAnimationFrame') return (fn) => setTimeout(fn, 0);
      if (prop === 'WebSocket') return function WebSocketStub() {};
      if (prop === 'innerWidth' || prop === 'innerHeight') return 800;
      return undefined;
    },
    set(t, prop, v) { t[prop] = v; return true; },
    has() { return true; },
  });
  if (jukebox) win.Jukebox = jukebox;

  const stub = (name) => new Proxy(function () {}, {
    get: (t, p) => (p === 'then' ? undefined
      : (p === Symbol.toPrimitive ? () => name : stub(name + '.' + String(p)))),
    apply: () => stub(name + '()'),
    construct: () => stub('new ' + name),
  });

  const ctx = {
    console: { log() {}, warn() {}, error() {}, info() {}, debug() {} },
    process: {
      contextIsolated: true,
      platform: 'win32', argv: [], env: {},
      versions: { electron: '41.0.0', node: '20.0.0' },
      on() {}, once() {},
    },
    window: win, document: doc,
    navigator: { userAgent: 'node', platform: 'win32', language: 'zh-CN' },
    location: { href: 'http://127.0.0.1:48911/', origin: 'http://127.0.0.1:48911', search: '' },
    require(id) {
      if (id === 'electron') {
        return {
          ipcRenderer: {
            on(ch, fn) { handlers.set(ch, fn); },
            send(ch, ...a) { sent.push([ch, a]); },
            invoke: async () => undefined,
            removeListener() {}, removeAllListeners() {},
          },
          contextBridge: {
            // 真实世界里页面看到的是代理；这里直接同引用（vm 无隔离边界）
            exposeInMainWorld(key, api) { exposed[key] = api; win[key] = api; },
            exposeInIsolatedWorld() {},
          },
          webFrame: { executeJavaScript() {}, insertCSS() {} },
          shell: { openExternal() {} },
          clipboard: { readText: () => '', writeText() {} },
          nativeImage: { createFromDataURL: () => ({}) },
          screen: { getPrimaryDisplay: () => ({ scaleFactor: 1, size: { width: 0, height: 0 } }) },
          desktopCapturer: { getSources: async () => [] },
        };
      }
      if (id === './ipc-channels') return require(IPC_CHANNELS);
      if (id === 'node:fs' || id === 'fs') return { existsSync: () => false, readFileSync: () => '' };
      if (id === 'node:path' || id === 'path') return path;
      return stub('require(' + id + ')');
    },
    setTimeout, clearTimeout,
    setInterval: () => 0, clearInterval: () => {},   // 不让保活定时器挂住测试进程
    Buffer, URL, TextEncoder, TextDecoder,
    fetch: async () => ({ ok: true, json: async () => ({}) }),
    AbortController, structuredClone,
    Promise, Math, JSON, Date, RegExp, Error, Array, Object, String, Number, Boolean,
  };
  ctx.globalThis = ctx;

  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(PRELOAD, 'utf8'), ctx, { filename: PRELOAD });

  // 页面侧：真 bridge（它自己调 window.nekoPetHost.register）
  assert.ok(exposed.nekoPetHost, 'preload 必须把 nekoPetHost 暴露给页面');
  vm.runInContext(fs.readFileSync(PAGE_BRIDGE, 'utf8'), ctx, { filename: PAGE_BRIDGE });

  return {
    ctx, win, handlers, exposed,
    diag: () => exposed.nekoPetDiagnostics.snapshot(),
    fire: (channel, payload) => handlers.get(channel)(null, payload),
    called: (jukeboxObj) => jukeboxObj.calls,
  };
}

/** 一个会记录调用的假 Jukebox。方法里断言 `this` 指向自己（验证闭包没丢 this）。 */
function makeJukebox(modelType, state) {
  const jb = {
    calls: [],
    State: Object.assign({ isVMDPlaying: false, isPaused: false }, state),
    getModelType() { jb.calls.push(['getModelType', undefined, this === jb]); return modelType; },
    playVMD(p) { jb.calls.push(['playVMD', p, this === jb]); },
    playVRMA(p) { jb.calls.push(['playVRMA', p, this === jb]); },
    stopVMD(skip) { jb.calls.push(['stopVMD', skip, this === jb]); },
    togglePause() { jb.calls.push(['togglePause', undefined, this === jb]); },
  };
  return jb;
}

test('页面注册面在隔离态下真的被 preload 认到（不是只写了键名）', () => {
  const jb = makeJukebox('live2d');
  const { diag } = bootPetIsolated(jb);
  const snap = diag();
  assert.strictEqual(snap.hostRegistered, true, 'nekoPetHost.register 没被调用到');
  // 迁移成功的话，这些键不该出现在 miss 里
  const misses = snap.misses || {};
  for (const k of ['Jukebox.present', 'Jukebox.getModelType', 'Jukebox.state']) {
    assert.strictEqual(misses[k], undefined, `${k} 被记成 miss，说明两端键名对不上`);
  }
  // 诊断探针本身也要可用：翻 contextIsolation 开关时靠它判断"桥断"还是"模型没加载"
  assert.strictEqual(snap.calls.jukebox.present, true);
  assert.strictEqual(snap.calls.jukebox.modelType, 'live2d');
});

test('VMD_PLAY：live2d 模型走 playVMD，且 this 仍指向 Jukebox', () => {
  const jb = makeJukebox('live2d');
  const { fire } = bootPetIsolated(jb);
  fire(CH.VMD_PLAY, { vmdPath: '/models/a.vmd' });
  assert.deepStrictEqual(jb.calls, [['getModelType', undefined, true], ['playVMD', '/models/a.vmd', true]]);
});

test('VMD_PLAY：vrm 模型走 playVRMA', () => {
  const jb = makeJukebox('vrm');
  const { fire } = bootPetIsolated(jb);
  fire(CH.VMD_PLAY, { vmdPath: '/models/b.vmd' });
  assert.deepStrictEqual(jb.calls.map((c) => c[0]), ['getModelType', 'playVRMA']);
  assert.strictEqual(jb.calls[1][1], '/models/b.vmd');
});

test('VMD_PLAY：缺 vmdPath 时提前返回，一次方法都不调', () => {
  const jb = makeJukebox('live2d');
  const { fire } = bootPetIsolated(jb);
  fire(CH.VMD_PLAY, {});
  assert.deepStrictEqual(jb.calls, [], '没有 vmdPath 不该碰 Jukebox');
});

test('VMD_STOP：skipIdleRestore 原样透传', () => {
  const jb = makeJukebox('live2d');
  const { fire } = bootPetIsolated(jb);
  fire(CH.VMD_STOP, { skipIdleRestore: true });
  assert.deepStrictEqual(jb.calls, [['stopVMD', true, true]]);
  jb.calls.length = 0;
  fire(CH.VMD_STOP, undefined);
  assert.deepStrictEqual(jb.calls, [['stopVMD', undefined, true]]);
});

test('VMD_PAUSE / VMD_RESUME：按 State 快照决定是否 togglePause', () => {
  const playing = makeJukebox('live2d', { isVMDPlaying: true, isPaused: false });
  let env = bootPetIsolated(playing);
  env.fire(CH.VMD_PAUSE, undefined);
  assert.deepStrictEqual(playing.calls.map((c) => c[0]), ['togglePause'], '播放中才暂停');
  playing.calls.length = 0;
  env.fire(CH.VMD_RESUME, undefined);
  assert.deepStrictEqual(playing.calls, [], '未暂停时 RESUME 不该动');

  const paused = makeJukebox('live2d', { isVMDPlaying: true, isPaused: true });
  env = bootPetIsolated(paused);
  env.fire(CH.VMD_PAUSE, undefined);
  assert.deepStrictEqual(paused.calls, [], '已暂停时 PAUSE 不该再 toggle');
  paused.calls.length = 0;
  env.fire(CH.VMD_RESUME, undefined);
  assert.deepStrictEqual(paused.calls.map((c) => c[0]), ['togglePause'], '暂停中才恢复');
});

test('页面还没有 Jukebox 实例时：不抛错、不调任何方法、记 miss', () => {
  const { fire, diag } = bootPetIsolated(null);
  assert.doesNotThrow(() => fire(CH.VMD_PLAY, { vmdPath: '/x.vmd' }));
  assert.doesNotThrow(() => fire(CH.VMD_STOP, { skipIdleRestore: false }));
  assert.doesNotThrow(() => fire(CH.VMD_PAUSE, undefined));
  assert.doesNotThrow(() => fire(CH.VMD_RESUME, undefined));
  assert.strictEqual(diag().misses['Jukebox.present'], 1, '实例缺失应记成 miss（观测层要能看到）');
});

test('State 是每次都取快照：页面改了状态，下一次触发就按新值判断', () => {
  const jb = makeJukebox('live2d', { isVMDPlaying: false, isPaused: false });
  const { fire } = bootPetIsolated(jb);

  fire(CH.VMD_PAUSE, undefined);
  assert.deepStrictEqual(jb.calls, [], '未播放时不暂停');

  jb.State.isVMDPlaying = true;   // 页面侧状态变了
  fire(CH.VMD_PAUSE, undefined);
  assert.deepStrictEqual(jb.calls.map((c) => c[0]), ['togglePause'], '必须读到最新状态，不能是注册时快照');
});
