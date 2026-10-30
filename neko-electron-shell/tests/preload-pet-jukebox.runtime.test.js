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
const CHAT = require(IPC_CHANNELS).CHAT_ACTION_CHANNELS;

/**
 * 造一个「隔离态的 pet 窗」并载入两端。
 * @param {object|null} jukebox 假 Jukebox；传 null 表示页面还没建出实例
 */
function bootPetIsolated(jukebox, opts = {}) {
  const isolated = opts.isolated !== false;
  const handlers = new Map();   // channel -> handler
  const exposed = Object.create(null);
  const sent = [];
  // DOMContentLoaded 里有一整块初始化（多窗口标志、字幕转发入口），原来 harness 是
  // 空实现的 addEventListener，等于这块从来没跑过。这里记下 handler 供用例手动触发。
  const docListeners = Object.create(null);

  const doc = {
    addEventListener(type, fn) { (docListeners[type] = docListeners[type] || []).push(fn); },
    removeEventListener() {},
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
  if (opts.avatarPortrait) win.avatarPortrait = opts.avatarPortrait;
  if (opts.models) {
    for (const k of ['mmd', 'vrm', 'live2d']) {
      if (opts.models[k]) win[k + 'Manager'] = opts.models[k];
    }
  }

  const stub = (name) => new Proxy(function () {}, {
    get: (t, p) => (p === 'then' ? undefined
      : (p === Symbol.toPrimitive ? () => name : stub(name + '.' + String(p)))),
    apply: () => stub(name + '()'),
    construct: () => stub('new ' + name),
  });

  const ctx = {
    console: { log() {}, warn() {}, error() {}, info() {}, debug() {} },
    process: {
      contextIsolated: isolated,
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
            // 真实世界里页面看到的是代理；这里直接同引用（vm 无隔离边界）。
            // 重复 expose 在 Electron 里会抛错，harness 照样抛 —— 否则 exposeToPage
            // 的幂等保护写了也测不出来。
            exposeInMainWorld(key, api) {
              if (Object.prototype.hasOwnProperty.call(exposed, key)) {
                throw new Error('Cannot bind an API on top of an existing property: ' + key);
              }
              exposed[key] = api;
              win[key] = api;
            },
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
  // exposeToPage 两条路径：隔离态走 contextBridge，非隔离态直接挂 window —— 两边都要验
  if (isolated) {
    assert.ok(exposed.nekoPetHost, '隔离态必须经 contextBridge 暴露 nekoPetHost');
  } else {
    assert.ok(win.nekoPetHost, '非隔离态应直接挂到 window.nekoPetHost');
  }
  if (isolated) {
    // 非隔离模式下故意**不**载桥：如果 pageApi 的隔离短路失效（错走了桥），
    // 这里会立刻拿不到 Jukebox，而不是被桥悄悄兜住。
    vm.runInContext(fs.readFileSync(PAGE_BRIDGE, 'utf8'), ctx, { filename: PAGE_BRIDGE });
  }

  return {
    ctx, win, handlers, exposed, sent,
    // 隔离态在 exposed（contextBridge），非隔离态在 window 上 —— 两种都要能取
    diag: () => (exposed.nekoPetDiagnostics || win.nekoPetDiagnostics).snapshot(),
    fire: (channel, payload) => handlers.get(channel)(null, payload),
    fireDoc: (type) => (docListeners[type] || []).forEach((fn) => fn({ type })),
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

// ───────────────────────────────────────────────────────────────────────────
// 非隔离模式：petWindow **现在**就是这个模式（`contextIsolation: false`）。
// 上面 8 条证明"迁移后隔离模式能通"，下面这批证明"迁移没改变今天的实际行为"。
// 这一组刻意不载页面桥，若 pageApi 的隔离短路写错（走了桥），这里必然拿不到 Jukebox。
// ───────────────────────────────────────────────────────────────────────────

test('非隔离模式：VMD_PLAY 直接调真对象（不经桥），vrm 走 playVRMA', () => {
  const jb = makeJukebox('vrm');
  const { fire } = bootPetIsolated(jb, { isolated: false });
  fire(CH.VMD_PLAY, { vmdPath: '/models/c.vmd' });
  assert.deepStrictEqual(jb.calls.map((c) => c[0]), ['getModelType', 'playVRMA']);
  assert.strictEqual(jb.calls[1][1], '/models/c.vmd');
  assert.strictEqual(jb.calls[1][2], true, '非隔离也必须保持 this 指向 Jukebox');
});

test('非隔离模式：VMD_STOP / PAUSE / RESUME 与隔离模式判定一致', () => {
  const jb = makeJukebox('live2d', { isVMDPlaying: true, isPaused: false });
  const { fire } = bootPetIsolated(jb, { isolated: false });

  fire(CH.VMD_STOP, { skipIdleRestore: false });
  assert.deepStrictEqual(jb.calls, [['stopVMD', false, true]]);
  jb.calls.length = 0;

  fire(CH.VMD_PAUSE, undefined);
  assert.deepStrictEqual(jb.calls.map((c) => c[0]), ['togglePause']);

  jb.calls.length = 0;
  jb.State.isPaused = true;
  fire(CH.VMD_RESUME, undefined);
  assert.deepStrictEqual(jb.calls.map((c) => c[0]), ['togglePause'], '暂停中才恢复');
});

test('非隔离模式：没有 Jukebox 时不抛错、不记 miss（miss 只属隔离态）', () => {
  const { fire, diag } = bootPetIsolated(null, { isolated: false });
  assert.doesNotThrow(() => fire(CH.VMD_PLAY, { vmdPath: '/x.vmd' }));
  assert.doesNotThrow(() => fire(CH.VMD_PAUSE, undefined));
  const snap = diag();
  assert.strictEqual(snap.isolated, false, '快照要如实反映运行模式');
  assert.strictEqual(Object.keys(snap.misses || {}).length, 0, '非隔离不该产生 miss');
});

// ───────────────────────────────────────────────────────────────────────────
// 截图域（P2-D）：头像捕获。两条分支都要验 —— 隔离态走桥、非隔离态直调。
// 关键语义：能力缺失（error 文案）与捕获返回空（dataUrl:null）**不能混**，
// 所以 helper 用 Promise / null 区分，而不是统一成 null。
// ───────────────────────────────────────────────────────────────────────────

function makeAvatarPortrait(result) {
  const ap = { calls: [] };
  ap.capture = function (opts) {
    ap.calls.push([opts, this === ap]);
    return Promise.resolve(result);
  };
  return ap;
}

/** 等异步 handler 跑完（handler 是 async IIFE，没有返回 promise） */
const flush = () => new Promise((r) => setTimeout(r, 20));

test('头像捕获（隔离态）：经桥调用页面 capture，参数与结果原样回传', async () => {
  const ap = makeAvatarPortrait({ dataUrl: 'data:image/png;base64,AAA', modelType: 'mmd' });
  const { fire, sent } = bootPetIsolated(null, { avatarPortrait: ap });
  fire(CHAT.AVATAR_PREVIEW, undefined);
  await flush();

  assert.strictEqual(ap.calls.length, 1, '页面 capture 必须被调用一次');
  const [opts, thisOk] = ap.calls[0];
  assert.strictEqual(opts.width, 320);
  assert.strictEqual(opts.includeDataUrl, true);
  assert.strictEqual(thisOk, true, '闭包必须保住 this（裸传方法会丢）');

  const out = sent.filter(([ch]) => ch === CHAT.AVATAR_PREVIEW_RESULT);
  assert.strictEqual(out.length, 1);
  // 注意：载荷对象是在 vm 里造的，跨 realm 的 deepStrictEqual 会因原型不同而失败，
  // 所以这里分字段断言，而不是整对象比。
  const payload = out[0][1][0];
  assert.strictEqual(payload.dataUrl, 'data:image/png;base64,AAA');
  assert.strictEqual(payload.modelType, 'mmd');
});

test('头像捕获（隔离态）：页面没有 avatarPortrait → 回「能力缺失」而不是空结果', async () => {
  const { fire, sent } = bootPetIsolated(null);
  fire(CHAT.AVATAR_PREVIEW, undefined);
  await flush();
  const out = sent.filter(([ch]) => ch === CHAT.AVATAR_PREVIEW_RESULT);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0][1][0].error, 'Avatar capture not available');
  assert.strictEqual(out[0][1][0].dataUrl, undefined, '能力缺失不应带 dataUrl 字段');
});

test('头像捕获（非隔离态）：直调真对象，不经桥，this 仍正确', async () => {
  const ap = makeAvatarPortrait({ dataUrl: 'data:image/png;base64,BBB' });
  const { fire, sent } = bootPetIsolated(null, { isolated: false, avatarPortrait: ap });
  fire(CHAT.AVATAR_PREVIEW, undefined);
  await flush();

  assert.strictEqual(ap.calls.length, 1);
  assert.strictEqual(ap.calls[0][1], true);
  const payload = sent.filter(([ch]) => ch === CHAT.AVATAR_PREVIEW_RESULT)[0][1][0];
  assert.strictEqual(payload.dataUrl, 'data:image/png;base64,BBB');
  assert.strictEqual(payload.modelType, 'live2d', 'modelType 缺省时回落 live2d（与迁移前一致）');
});

test('头像捕获（非隔离态）：没有实例 → 能力缺失文案', async () => {
  const { fire, sent } = bootPetIsolated(null, { isolated: false });
  fire(CHAT.AVATAR_PREVIEW, undefined);
  await flush();
  const out = sent.filter(([ch]) => ch === CHAT.AVATAR_PREVIEW_RESULT);
  assert.strictEqual(out[0][1][0].error, 'Avatar capture not available');
});

// ───────────────────────────────────────────────────────────────────────────
// 域 C（渲染控制 / 复位）：三个管理器同名成员，纯命令、不读状态。
// 这批复用同一对 helper（petModelHas / petModelCall），所以只需验一组即可覆盖语义。
// ───────────────────────────────────────────────────────────────────────────

function makeManager(opNames) {
  const m = { calls: [] };
  for (const op of opNames) {
    m[op] = function () { m.calls.push([op, this === m]); };
  }
  return m;
}

test('域 C（隔离态）：经桥调用页面的 pause/resume/reset，且 this 正确', () => {
  const l2d = makeManager(['pauseRendering', 'resumeRendering', 'resetModelPosition']);
  const { ctx } = bootPetIsolated(null, { models: { live2d: l2d } });

  assert.strictEqual(ctx.petModelHas('live2d', 'pauseRendering'), true);
  assert.strictEqual(ctx.petModelCall('live2d', 'pauseRendering'), true);
  assert.strictEqual(ctx.petModelCall('live2d', 'resumeRendering'), true);
  assert.strictEqual(ctx.petModelCall('live2d', 'resetModelPosition'), true);
  assert.deepStrictEqual(l2d.calls.map((c) => c[0]),
    ['pauseRendering', 'resumeRendering', 'resetModelPosition']);
  assert.ok(l2d.calls.every((c) => c[1] === true), '闭包必须保住 this');
});

test('域 C（隔离态）：管理器不存在时 has=false、call=false，且不抛错', () => {
  const { ctx } = bootPetIsolated(null, { models: {} });
  assert.strictEqual(ctx.petModelHas('mmd', 'pauseRendering'), false);
  assert.strictEqual(ctx.petModelCall('mmd', 'pauseRendering'), false);
  assert.doesNotThrow(() => ctx.petModelCall('vrm', 'resetModelPosition'));
});

test('域 C（非隔离态）：直调真对象，不经桥', () => {
  const mmd = makeManager(['pauseRendering']);
  const { ctx } = bootPetIsolated(null, { isolated: false, models: { mmd } });
  assert.strictEqual(ctx.petModelHas('mmd', 'pauseRendering'), true);
  assert.strictEqual(ctx.petModelCall('mmd', 'pauseRendering'), true);
  assert.deepStrictEqual(mmd.calls, [['pauseRendering', true]]);
  // 没有的 manager 仍然安全
  assert.strictEqual(ctx.petModelCall('live2d', 'pauseRendering'), false);
});

// ───────────────────────────────────────────────────────────────────────────
// 域 B：测量（2026-10-30）
//
// 这一域最容易被「看起来通了」骗过去的地方是**形状**：
// 页面侧 getModelScreenBounds 回的原生 bounds 各管理器各不相同
// （left/right 一套、x/y/width/height 一套、minX/maxX 一套），
// 过桥克隆后原型 getter 全丢 ⇒ preload 拿到的可能是个空对象，
// 于是「量不到框」而不是「报错」，表现为模型点不中、拖不动。
// 所以这里既验数值，也验两套归一化函数（边读法 / xy 读法）都能用同一份快照。
// ───────────────────────────────────────────────────────────────────────────

function assertRect(actual, expect, label) {
  assert.ok(actual && typeof actual === 'object', `${label}: 期望矩形，实得 ${actual}`);
  for (const k of ['left', 'top', 'right', 'bottom', 'width', 'height', 'centerX', 'centerY']) {
    assert.strictEqual(actual[k], expect[k], `${label}.${k}`);
  }
}

const RECT_10_20_110_220 = {
  left: 10, top: 20, right: 110, bottom: 220,
  width: 100, height: 200, centerX: 60, centerY: 120,
};

test('域 B（隔离态）：经桥取 mmd 框，归一化成同一套纯数字', () => {
  const mmd = {
    currentModel: {},
    getModelScreenBounds() { return { left: 10, top: 20, right: 110, bottom: 220 }; },
  };
  const { ctx } = bootPetIsolated(null, { models: { mmd } });
  assertRect(ctx.petModelBounds('mmd'), RECT_10_20_110_220, 'mmd');
});

test('域 B（隔离态）：只有 x/y/width/height 的来源也要能算出四边', () => {
  const vrm = {
    currentModel: {},
    getModelScreenBounds() { return { x: 10, y: 20, width: 100, height: 200 }; },
  };
  const { ctx } = bootPetIsolated(null, { models: { vrm } });
  assertRect(ctx.petModelBounds('vrm'), RECT_10_20_110_220, 'vrm');
});

test('域 B（隔离态）：getModelScreenBounds 缺席时退到 interaction 缓存，且先刷缓存', () => {
  let refreshed = 0;
  const mmd = {
    currentModel: {},
    interaction: {
      _cachedScreenBounds: { minX: 10, minY: 20, maxX: 110, maxY: 220 },
      updateModelBoundsCache() { refreshed += 1; },
    },
  };
  const { ctx } = bootPetIsolated(null, { models: { mmd } });
  assertRect(ctx.petModelBounds('mmd'), RECT_10_20_110_220, 'mmd.interaction');
  assert.strictEqual(refreshed, 1, '退到 interaction 前必须先刷一次缓存（否则拿到上一帧的框）');
});

test('域 B（隔离态）：live2d 退到 getCurrentModel().getBounds()', () => {
  const live2d = {
    getCurrentModel() { return { getBounds() { return { x: 10, y: 20, width: 100, height: 200 }; } }; },
  };
  const { ctx } = bootPetIsolated(null, { models: { live2d } });
  assertRect(ctx.petModelBounds('live2d'), RECT_10_20_110_220, 'live2d.getBounds');
});

test('域 B（隔离态）：没有管理器 / 没有模型时回 null，不抛错', () => {
  const { ctx, diag } = bootPetIsolated(null, { models: { mmd: { currentModel: null } } });
  assert.strictEqual(ctx.petModelBounds('mmd'), null, '没有 currentModel 就没有框');
  assert.strictEqual(ctx.petModelBounds('vrm'), null, '管理器不存在');
  assert.strictEqual(
    ctx.petModelBounds('live2d'), null,
    'live2d 管理器的框也应该是 null（getCurrentModel 不存在）');
  assert.ok((diag().misses['bounds:vrm'] || 0) >= 1, '能力缺失要记 miss —— 观测层要能看到');
});

test('域 B：退化框（零宽/零高）当「量不到」，不能把输入区域压成细缝', () => {
  const mmd = {
    currentModel: {},
    getModelScreenBounds() { return { left: 10, top: 10, right: 10, bottom: 200 }; },
  };
  const { ctx } = bootPetIsolated(null, { models: { mmd } });
  assert.strictEqual(ctx.petModelBounds('mmd'), null);
});

test('域 B（非隔离态）：直读真对象，结果与隔离态逐字段一致', () => {
  const mmd = {
    currentModel: {},
    getModelScreenBounds() { return { left: 10, top: 20, right: 110, bottom: 220 }; },
  };
  const { ctx } = bootPetIsolated(null, { isolated: false, models: { mmd } });
  assertRect(ctx.petModelBounds('mmd'), RECT_10_20_110_220, 'mmd(non-isolated)');
});

test('域 B：诊断探针拿到的就是生产路径的框（不是另一套实现）', () => {
  const mmd = {
    currentModel: {},
    getModelScreenBounds() { return { left: 10, top: 20, right: 110, bottom: 220 }; },
  };
  const { diag } = bootPetIsolated(null, { models: { mmd } });
  assertRect(diag().calls.bounds.mmd, RECT_10_20_110_220, 'diag.calls.bounds.mmd');
});

// ───────────────────────────────────────────────────────────────────────────
// 域 D：视线跟随（2026-10-30）
//
// 两个跟随器的回调名**不对称**（vrm `_cursorFollow._onPointerMove`、
// mmd `cursorFollow._pointerMoveHandler`），把两路写成一样是这域唯一的坑，
// 而且写错了不会报错，只会「模型不看你」。
// ───────────────────────────────────────────────────────────────────────────

test('域 D（隔离态）：vrm 视线走 _cursorFollow._onPointerMove，this 与事件形状都对', () => {
  const seen = [];
  const follow = {
    _onPointerMove(evt) { seen.push([evt, this === follow]); },
  };
  const { ctx } = bootPetIsolated(null, { models: { vrm: { _cursorFollow: follow } } });
  assert.strictEqual(ctx.petModelGaze('vrm', 33, 44), true);
  assert.strictEqual(seen.length, 1);
  assert.strictEqual(seen[0][1], true, '闭包必须保住 this');
  assert.strictEqual(seen[0][0].type, 'pointermove');
  assert.strictEqual(seen[0][0].clientX, 33);
  assert.strictEqual(seen[0][0].clientY, 44);
});

test('域 D（隔离态）：mmd 视线走 cursorFollow._pointerMoveHandler（与 vrm 不同名）', () => {
  const seen = [];
  const follow = {
    _pointerMoveHandler(evt) { seen.push([evt, this === follow]); },
  };
  const { ctx } = bootPetIsolated(null, { models: { mmd: { cursorFollow: follow } } });
  assert.strictEqual(ctx.petModelGaze('mmd', 5, 6), true);
  assert.strictEqual(seen.length, 1);
  assert.strictEqual(seen[0][1], true);
  assert.strictEqual(seen[0][0].clientX, 5);
});

test('域 D（隔离态）：交叉写错名字必须拿不到能力（这正是本域要防的错）', () => {
  // 只有 vrm 形状的跟随器塞给 mmd ⇒ mmd 侧必须回 false，而不是静默调错东西
  const { ctx } = bootPetIsolated(null, { models: { mmd: { _cursorFollow: { _onPointerMove() {} } } } });
  assert.strictEqual(ctx.petModelGaze('mmd', 1, 2), false);
  assert.strictEqual(ctx.petModelGazeAvailable('mmd'), false);
});

test('域 D（非隔离态）：直调真对象，不经桥', () => {
  const seen = [];
  const follow = { _onPointerMove(evt) { seen.push(evt.clientX); } };
  const { ctx } = bootPetIsolated(null, { isolated: false, models: { vrm: { _cursorFollow: follow } } });
  assert.strictEqual(ctx.petModelGaze('vrm', 7, 8), true);
  assert.deepStrictEqual(seen, [7]);
});

test('域 D：诊断探针只报能力有无，不真调（不能在冒烟时拽走眼珠）', () => {
  const follow = { _onPointerMove() { throw new Error('探针不该真调'); } };
  const { diag } = bootPetIsolated(null, { models: { vrm: { _cursorFollow: follow } } });
  assert.strictEqual(diag().probes['gaze:vrm'], true);
  assert.strictEqual(diag().probes['gaze:mmd'], false);
});

// ───────────────────────────────────────────────────────────────────────────
// 域 F：穿透判定（interaction / currentModel / getCurrentModel，2026-10-30）
//
// 这是 P2 最后一块，也是最危险的一块：它决定「鼠标落在窗口上算不算点中模型」。
// 写错的后果不是报错，而是**整个窗口点不中 / 点哪儿都中**。
//
// 这里直接打 checkHitTest()（顶层函数），链路是完整的：
//   getActiveModelType → checkMMDHitTest/checkLive2DHitTest
//   → petModelPresent/petModelScreenBounds/petModelPreciseHit/petModelLocalBounds/petModelHitAreas
//   → pageApi → 真 pet-host-bridge.js → 假管理器
// 所以它同时验证「键名对得上」和「判定结果对」。
// ───────────────────────────────────────────────────────────────────────────

/** 造一个 mmd/vrm 形状的假管理器：currentModel + interaction(_cachedScreenBounds/_hitTestModel)。 */
function makeInteractionManager(rect, opts = {}) {
  const state = { refreshed: 0, hits: [] };
  const I = {
    _cachedScreenBounds: rect
      ? { minX: rect.left, minY: rect.top, maxX: rect.right, maxY: rect.bottom }
      : null,
    updateModelBoundsCache() { state.refreshed += 1; },
    _hitTestModel(x, y) {
      state.hits.push([x, y]);
      return opts.alwaysHit !== false;
    },
  };
  const manager = { currentModel: opts.noModel ? null : {}, interaction: I };
  return { manager, state, I };
}

test('域 F（隔离态 mmd）：椭圆外但矩形内 → 走精确命中；远点直接 false', () => {
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 });
  const { ctx, win } = bootPetIsolated(null, { models: { mmd: manager } });
  win.lanlan_config = { model_type: 'mmd' };

  // 椭圆中心：必然命中（椭圆判据），不该调用 _hitTestModel
  assert.strictEqual(ctx.checkHitTest(200, 250, 0), true, '椭圆内应命中');
  assert.deepStrictEqual(state.hits, [], '椭圆内不该走精确命中（那是热路径上的额外开销）');

  // 矩形内、椭圆外（dx=95 > rx=60）→ 交给 _hitTestModel
  assert.strictEqual(ctx.checkHitTest(295, 250, 0), true, '矩形内应走精确命中');
  assert.deepStrictEqual(state.hits, [[295, 250]]);

  // 远在框外（矩形 +12 都不覆盖）→ false，且不再调精确命中
  assert.strictEqual(ctx.checkHitTest(900, 900, 0), false);
  assert.strictEqual(state.hits.length, 1);
});

test('域 F（隔离态 mmd）：精确命中回 false 时整条链也是 false（不能把矩形内一律当命中）', () => {
  const { manager } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 }, { alwaysHit: false });
  const { ctx, win } = bootPetIsolated(null, { models: { mmd: manager } });
  win.lanlan_config = { model_type: 'mmd' };
  assert.strictEqual(ctx.checkHitTest(295, 250, 0), false);
});

test('域 F（隔离态 mmd）：没有 currentModel 时一律不命中 —— 哪怕缓存框还在', () => {
  // 这是最容易被迁移弄丢的一条：旧代码的前置守卫是 `!currentModel → false`。
  // 模型卸掉后 interaction 的缓存框可能还留着，若只按框判就会「点空白也命中」。
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 }, { noModel: true });
  const { ctx, win } = bootPetIsolated(null, { models: { mmd: manager } });
  win.lanlan_config = { model_type: 'mmd' };
  // 直接钉住「存在性」这一层：端到端断言会被后面两道守卫兜住，
  // 单独删掉 present 判断时端到端仍然 false —— 那样这条用例就失去了意义。
  assert.strictEqual(ctx.petModelPresent('mmd'), false, '没有模型时 present 必须为 false');
  assert.strictEqual(ctx.petModelPresent('live2d'), false, 'live2d 管理器不存在也是 false');
  assert.strictEqual(ctx.petModelScreenBounds('mmd', true), null, '没有模型就不该交出框');
  assert.strictEqual(ctx.checkHitTest(200, 250, 0), false, '没有模型就必须 false');
  assert.deepStrictEqual(state.hits, []);
});

test('域 F（隔离态）：present / screenBounds / 精确命中 三个能力各自可单独判', () => {
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 });
  const { ctx } = bootPetIsolated(null, { models: { mmd: manager } });

  assert.strictEqual(ctx.petModelPresent('mmd'), true);
  assert.strictEqual(ctx.petModelPresent('vrm'), false, '没装 vrm 管理器');

  const sb = ctx.petModelScreenBounds('mmd', true);
  assert.strictEqual(sb.minX, 100);
  assert.strictEqual(sb.maxY, 400);

  assert.strictEqual(ctx.petModelPreciseHit('mmd', 5, 6), true);
  assert.deepStrictEqual(state.hits, [[5, 6]]);
  assert.strictEqual(ctx.petModelPreciseHit('vrm', 5, 6), false, '没有 vrm 能力时精确命中必须是 false');
});

test('域 F（隔离态 live2d）：localBounds 与 hitAreas 分开取，互不牵连', () => {
  const live2d = {
    getCurrentModel() {
      return {
        getBounds() { return { x: 100, y: 100, width: 200, height: 300 }; },
        hitTest() { return ['head', 'body']; },
      };
    },
  };
  const { ctx } = bootPetIsolated(null, { models: { live2d } });
  const b = ctx.petModelLocalBounds('live2d');
  assert.strictEqual(b.x, 100);
  assert.strictEqual(b.width, 200);
  assert.strictEqual(b.right, 300, 'right 必须由 x+width 算出来（命中判定要用）');
  assert.deepStrictEqual(Array.from(ctx.petModelHitAreas('live2d', 1, 2)), ['head', 'body']);
});

test('域 F（隔离态 mmd）：告别态短路，连框都不量', () => {
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 });
  manager._goodbyeClicked = true;
  const { ctx, win } = bootPetIsolated(null, { models: { mmd: manager } });
  win.lanlan_config = { model_type: 'mmd' };
  assert.strictEqual(ctx.checkHitTest(200, 250, 0), false);
  assert.strictEqual(state.refreshed, 0, '告别态不该再刷包围盒');
});

test('域 F（隔离态 live2d）：hitTest 有结果即命中，空结果退回椭圆近似', () => {
  const hitTestCalls = [];
  const live2d = {
    getCurrentModel() {
      return {
        getBounds() { return { x: 100, y: 100, width: 200, height: 300 }; },
        hitTest(x, y) { hitTestCalls.push([x, y]); return y < 200 ? ['head'] : []; },
      };
    },
  };
  const { ctx, win } = bootPetIsolated(null, { models: { live2d } });
  win.lanlan_config = { model_type: 'live2d' };

  assert.strictEqual(ctx.checkHitTest(200, 150, 0), true, 'hitTest 返回区域名 → 命中');
  // 同一 x，y 落到下半部：hitTest 回空 → 椭圆判据（cx=200,cy=250,rx=60,ry=135）
  assert.strictEqual(ctx.checkHitTest(200, 390, 0), false, '空结果 + 椭圆外 → 不命中');
  assert.deepStrictEqual(hitTestCalls, [[200, 150], [200, 390]]);

  // 框外直接 false，不该调 hitTest
  assert.strictEqual(ctx.checkHitTest(1000, 1000, 0), false);
  assert.strictEqual(hitTestCalls.length, 2);
});

test('域 F（隔离态 live2d）：模型没有 hitTest 时仍能靠椭圆判据命中', () => {
  const live2d = {
    getCurrentModel() {
      return { getBounds() { return { x: 100, y: 100, width: 200, height: 300 }; } };
    },
  };
  const { ctx, win } = bootPetIsolated(null, { models: { live2d } });
  win.lanlan_config = { model_type: 'live2d' };
  assert.strictEqual(ctx.checkHitTest(200, 250, 0), true, '命中区域缺失应退回椭圆近似，不能一律 false');
});

test('域 F：forceBoundsRefresh 语义 —— false 用缓存、true 才重算', () => {
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 });
  const { ctx, win } = bootPetIsolated(null, { models: { vrm: manager } });
  win.lanlan_config = { model_type: 'vrm' };

  const cold = ctx.getModelInputBounds(false);
  assert.strictEqual(state.refreshed, 0, '有缓存且不强制 → 不该重算');
  assert.strictEqual(cold.left, 100);
  assert.strictEqual(cold.right, 300);

  ctx.getModelInputBounds(true);
  assert.strictEqual(state.refreshed, 1, '强制刷新必须真的重算');
});

test('域 F（非隔离态）：同一组用例结果与隔离态逐条一致', () => {
  const { manager, state } = makeInteractionManager({ left: 100, top: 100, right: 300, bottom: 400 });
  const { ctx, win } = bootPetIsolated(null, { isolated: false, models: { mmd: manager } });
  win.lanlan_config = { model_type: 'mmd' };

  assert.strictEqual(ctx.checkHitTest(200, 250, 0), true);
  assert.deepStrictEqual(state.hits, [], '非隔离下椭圆内也不该走精确命中');
  assert.strictEqual(ctx.checkHitTest(295, 250, 0), true);
  assert.strictEqual(ctx.checkHitTest(900, 900, 0), false);

  manager.currentModel = null;
  assert.strictEqual(ctx.checkHitTest(200, 250, 0), false, '没有模型同样必须 false');
});

test('域 F（非隔离态 live2d）：直读模型对象，判定与隔离态一致', () => {
  const live2d = {
    getCurrentModel() {
      return {
        getBounds() { return { x: 100, y: 100, width: 200, height: 300 }; },
        hitTest() { return ['head']; },
      };
    },
  };
  const { ctx, win } = bootPetIsolated(null, { isolated: false, models: { live2d } });
  win.lanlan_config = { model_type: 'live2d' };
  assert.strictEqual(ctx.checkHitTest(200, 150, 0), true);
  assert.strictEqual(ctx.checkHitTest(1000, 1000, 0), false);
});

// ───────────────────────────────────────────────────────────────────────────
// P3：页面侧 API 的「写」方向（2026-10-30）
//
// P2 清的是 preload 对页面的**读**；P3 清的是 preload 往页面**写**。
// 写不干净就翻不了 contextIsolation：直写的全局隔离后页面根本看不见。
// 这批从 14 处压到 2 个名字（window.WebSocket / __nekoPetInteracting__），
// 它们的残留原因写在 window-hardening.contract.test.js 的白名单里。
// ───────────────────────────────────────────────────────────────────────────

const PAGE_APIS = [
  '__NEKO_DESKTOP_RUNTIME__', '__NEKO_MULTI_WINDOW__', '__NEKO_DISABLE_NATIVE_RETURN_BALL_DRAG__',
  '__nekoJukeboxToggle', '__forwardSubtitleRenderStateToWindow',
  'nekoSubtitleWindow', 'nekoAgentHud', 'nekoPetDrag', 'nekoSpatialAudio',
  'electronScreen', 'electronDesktopCapturer',
];

test('P3（隔离态）：11 个页面 API 全部能过桥，且形态对', () => {
  const { win, fireDoc } = bootPetIsolated(null);
  // 有一个（字幕转发入口）是在 DOMContentLoaded 里建的：必须真的触发那一块才算数，
  // 否则「用例通过」只是因为它压根没跑。
  fireDoc('DOMContentLoaded');
  for (const name of PAGE_APIS) {
    assert.notStrictEqual(typeof win[name], 'undefined', `${name} 没有暴露给页面（隔离后页面拿不到）`);
  }
  assert.strictEqual(win.__NEKO_MULTI_WINDOW__, true);
  assert.strictEqual(typeof win.__NEKO_DESKTOP_RUNTIME__, 'object');
  assert.strictEqual(typeof win.__NEKO_DESKTOP_RUNTIME__.isLinuxX11, 'boolean', '冻结对象也要能读字段');
  for (const name of ['nekoSubtitleWindow', 'nekoAgentHud', 'nekoPetDrag', 'nekoSpatialAudio',
    'electronScreen', 'electronDesktopCapturer']) {
    assert.strictEqual(typeof win[name], 'object', `${name} 应是对象`);
  }
  assert.strictEqual(typeof win.nekoPetDrag.getBounds, 'function');
  assert.strictEqual(typeof win.electronDesktopCapturer.captureSourceAsDataUrl, 'function');
  assert.strictEqual(typeof win.__forwardSubtitleRenderStateToWindow, 'function',
    '字幕转发入口没暴露 —— 隔离后字幕状态再也推不回主进程');
});

test('P3（隔离态）：过桥后的函数真能调到 IPC，不是空壳', () => {
  const { win, sent } = bootPetIsolated(null);
  win.nekoAgentHud.show();
  win.nekoSubtitleWindow.hide();
  win.__nekoJukeboxToggle();
  const channels = sent.map((s) => s[0]);
  assert.ok(channels.includes('neko:show-agent-hud'), 'nekoAgentHud.show 没打到 IPC');
  assert.ok(channels.includes('neko:hide-subtitle'), 'nekoSubtitleWindow.hide 没打到 IPC');
  assert.ok(channels.includes(CH.TOGGLE), '__nekoJukeboxToggle 没打到 IPC');
});

test('P3（非隔离态）：同样是 window 上的同名对象，页面读法与迁 Isolation 前一致', () => {
  const { win, fireDoc } = bootPetIsolated(null, { isolated: false });
  fireDoc('DOMContentLoaded');
  for (const name of PAGE_APIS) {
    assert.notStrictEqual(typeof win[name], 'undefined', `${name} 在非隔离态也必须在 window 上`);
  }
  assert.strictEqual(typeof win.nekoPetDrag.start, 'function');
  assert.strictEqual(win.__NEKO_MULTI_WINDOW__, true);
});

test('P3：exposeToPage 幂等 —— 重复暴露不抛错，也不会把值改回去', () => {
  const { ctx, win } = bootPetIsolated(null);
  const before = win.nekoAgentHud;
  assert.doesNotThrow(() => ctx.exposeToPage('nekoAgentHud', { show() {}, hide() {} }),
    '重复暴露同一 key 必须被吃掉（Electron 的 contextBridge 会抛）');
  assert.strictEqual(win.nekoAgentHud, before, '重复暴露不该替换页面已拿到的 API');
});
