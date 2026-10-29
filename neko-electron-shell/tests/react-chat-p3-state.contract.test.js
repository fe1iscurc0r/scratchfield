// React Chat B 组状态门面契约（WO-278 P3 产物）。
//
// 为什么需要它：非隔离臂里 preload 和页面共享 window，getter 有没有装、装在哪一臂，
// 表现和旧写法一样；只有隔离臂能测出差异。这里的静态契约保证：
//   1) B 组页面全局不再由 preload 直写 window（隔离后写了也到不了页面）；
//   2) 每次状态变化都经 publishPageState —— 共享臂才回写 window，隔离臂只更新真源；
//   3) 页面 shim 只在 isolated 臂装 getter（共享臂装了会顶掉 preload 的后续赋值），
//      且 getter 必须每次现取（静态快照会让页面读到旧值）；
//   4) 一次性静态值 __NEKO_DESKTOP_RUNTIME__ 直接 expose，早于所有页面脚本（app-state.js）；
//   5) 历史拖拽/指针穿透/工具轮盘这些页面零引用的全局保持 preload 内部，不进门面。
// 运行：node --test tests/react-chat-p3-state.contract.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const preload = fs.readFileSync(path.join(__dirname, '..', 'src', 'preload-chat-react.js'), 'utf8');
const pageShim = fs.readFileSync(
  path.join(ROOT, 'NEKO', 'N.E.K.O', 'static', 'app', 'electron-page-bridge.js'),
  'utf8',
);

const LIVE_GLOBALS = [
  '__nekoDesktopCompactLayout',
  '__nekoDesktopAvatarBounds',
  '__nekoDesktopCompactBallScreenRect',
  '__nekoDesktopCompactExternalBall',
  '__nekoInjectedConfig',
];
const PRELOAD_ONLY_GLOBALS = [
  '__nekoDesktopCompactHistoryDragState',
  '__nekoDesktopCompactHistoryPointerPassthrough',
  '__nekoDesktopCompactToolWheelDragActive',
  '__nekoDesktopCompactToolFanOpenSolid',
];

test('B 组页面全局不再由 preload 直写 window', () => {
  for (const name of LIVE_GLOBALS) {
    assert.doesNotMatch(
      preload,
      new RegExp(`window\\.${name}\\b`),
      `${name} 必须走 publishPageState / pageState，preload 内部也不许再读 window（隔离臂读到的是另一份）`,
    );
  }
  // 门面名单与实现必须一一对应，避免以后新增状态忘了登记。
  const registry = preload.match(/var PAGE_STATE_NAMES = \{([\s\S]*?)\};/);
  assert.ok(registry, '缺少 PAGE_STATE_NAMES 注册表');
  const registered = (registry[1].match(/'(__neko[A-Za-z0-9_]+)'/g) || []).map((s) => s.slice(1, -1));
  assert.deepStrictEqual(registered.sort(), [...LIVE_GLOBALS].sort());
});

test('共享臂回写 window，隔离臂只更新真源，且 nekoChatState 暴露 isolated + get', () => {
  assert.match(preload, /var pageStateWritesWindow = !process\.contextIsolated;/);
  assert.match(
    preload,
    /function publishPageState\(slot, value\) \{\s*pageState\[slot\] = value;\s*if \(pageStateWritesWindow\) window\[PAGE_STATE_NAMES\[slot\]\] = value;\s*\}/,
  );
  assert.match(preload, /exposeToPage\('nekoChatState', \{\s*isolated: !pageStateWritesWindow,/);
  assert.match(preload, /get: function \(name\) \{\s*var slot = PAGE_STATE_SLOTS\[name\];\s*return slot \? pageState\[slot\] : undefined;\s*\}/);
  // 状态发布必须发生在真源上：任何 publishPageState 都应该写 slot，而不是 window。
  const publishCalls = (preload.match(/publishPageState\('/g) || []).length;
  assert.ok(publishCalls >= 8, `publishPageState 调用点过少（${publishCalls}），漏改会丢状态`);
});

test('一次性静态值 __NEKO_DESKTOP_RUNTIME__ 直接 expose（早于 app-state.js 的解析期读取）', () => {
  assert.match(preload, /exposeToPage\('__NEKO_DESKTOP_RUNTIME__', Object\.freeze\(\{/);
  assert.doesNotMatch(preload, /window\.__NEKO_DESKTOP_RUNTIME__\s*=/);
});

test('页面 shim 只在 isolated 臂装 getter，且每次现取（不许缓存成快照）', () => {
  assert.match(pageShim, /var chatState = global\.nekoChatState;/);
  assert.match(pageShim, /chatState\.isolated === true/);
  for (const name of LIVE_GLOBALS) {
    assert.ok(pageShim.includes(`'${name}'`), `页面 shim 漏装 ${name}`);
  }
  assert.match(pageShim, /get: function \(\) \{ return chatState\.get\(name\); \}/);
  // 静态快照（安装时取一次）是本任务破坏对照要抓的错误写法，这里提前钉死。
  assert.doesNotMatch(pageShim, /var cached = chatState\.get\(name\);/);
  // getter 定义不能影响共享臂：共享臂 preload 直写 window，页面若装 getter 会吞掉后续赋值。
  const installBlock = pageShim.slice(pageShim.indexOf('var chatState = global.nekoChatState;'));
  assert.ok(installBlock.indexOf('Object.defineProperty') < installBlock.indexOf("if (!toastBridge"));
});

test('页面零引用的历史/指针/工具轮盘全局保持 preload 内部', () => {
  for (const name of PRELOAD_ONLY_GLOBALS) {
    assert.ok(
      preload.includes(`window.${name}`),
      `${name} 仍应在 preload 世界维护（页面不读，暂不需要过桥）`,
    );
    assert.ok(!pageShim.includes(name), `${name} 不应被页面 shim 暴露`);
    assert.ok(!preload.includes(`'${name}'`), `${name} 不应进 PAGE_STATE_NAMES`);
  }
});
