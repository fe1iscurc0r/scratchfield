// React Chat A 组 API 暴露契约（WO-278 P2 产物）。
//
// 为什么需要它：真 Electron 两臂里，**非隔离臂看不见这类回归**——非隔离时
// `window` 就是 preload 的世界，静态快照（exposeToPage(name, impl)）和活门面
// 表现完全一样。只有隔离臂能测出差异，而隔离臂依赖窗口装配。这里用静态契约把
// 「暴露方式」钉死，让错的写法在单测就红：
//   1) A 组全局一律走 exposeToPage / exposeLiveFacade，不许再直写 window.*；
//   2) nekoChatWindow 的门面必须是活门面（getter 取实现），且名单覆盖实现对象上
//      的所有方法（含 DOMContentLoaded 之后才补挂的 5 个）；
//   3) preload 内部不许再读 window.nekoChatWindow（隔离后读到的是页面那份门面）；
//   4) 屏幕点换算函数保持 preload 内部，不在 P2 暴露。
// 运行：node --test tests/react-chat-p2-api.contract.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const SRC = path.join(__dirname, '..', 'src');
const source = fs.readFileSync(path.join(SRC, 'preload-chat-react.js'), 'utf8');

const A_GROUP_GLOBALS = [
  'nekoChatWindow',
  'electronDesktopCapturer',
  'nekoScreenshotProxy',
  'nekoSubtitleWindow',
  '__nekoJukeboxToggle',
  '__nekoRequestConfigInjection',
  '__nekoRequestAvatarPreview',
  '__nekoFocusReactChatInputFromHotkey',
  '__NEKO_MULTI_WINDOW__',
];

function facadeNames() {
  const match = source.match(
    /exposeLiveFacade\('nekoChatWindow', \[([\s\S]*?)\], function \(\) \{ return nekoChatWindowImpl; \}\);/,
  );
  assert.ok(match, 'nekoChatWindow 必须由 exposeLiveFacade 暴露，且 getter 指向 nekoChatWindowImpl');
  return (match[1].match(/'([A-Za-z0-9_]+)'/g) || []).map((s) => s.slice(1, -1));
}

test('A 组全局一律过 exposeToPage / exposeLiveFacade，不再直写 window.*', () => {
  for (const name of A_GROUP_GLOBALS) {
    const direct = new RegExp('window\\.' + name.replace(/\W/g, '\\$&') + '\\s*=');
    assert.ok(!direct.test(source), 'window.' + name + ' = ... 会绕过 contextBridge');
    assert.ok(
      source.includes("exposeToPage('" + name + "'") || source.includes("exposeLiveFacade('" + name + "'"),
      name + ' 没有任何 exposeToPage/exposeLiveFacade 暴露点',
    );
  }
});

test('P1 的构造器替换没有被顺手改回来', () => {
  assert.ok(!/window\.WebSocket\s*=/.test(source), 'window.WebSocket 不许再被替换');
  assert.ok(source.includes("exposeToPage('nekoWebSocket'"), 'nekoWebSocket 桥必须仍在');
});

test('门面名单覆盖实现对象的全部方法（含晚挂的 5 个）', () => {
  const names = facadeNames();
  const literalStart = source.indexOf('var nekoChatWindowImpl = {');
  const exposureStart = source.indexOf("exposeLiveFacade('nekoChatWindow'");
  assert.ok(literalStart >= 0 && exposureStart > literalStart, '实现对象必须定义在暴露点之前');
  const implChunk = source.slice(literalStart, exposureStart);
  const literalMethods = [...implChunk.matchAll(/^ {2}([A-Za-z0-9_]+):/gm)].map((m) => m[1]);
  const lateMethods = [...source.matchAll(/nekoChatWindowImpl\.([A-Za-z0-9_]+) =/g)].map((m) => m[1]);
  const missing = [...literalMethods, ...lateMethods].filter((name) => !names.includes(name));
  assert.deepStrictEqual(missing, [], '这些方法页面拿不到（门面名单要预先预留）');
  // 晚挂的 5 个必须真的存在，否则上面这条会退化成空断言。
  assert.deepStrictEqual(
    ['isCollapsed', 'idleDockCollapse', 'idleDockExpand', 'idleDockCommitCollapsedBounds', 'ensureExpandedForTutorial']
      .filter((name) => !lateMethods.includes(name)),
    [],
  );
});

test('晚挂方法挂在实现对象上，不再挂到 window.nekoChatWindow', () => {
  assert.ok(!/window\.nekoChatWindow\.\w+\s*=/.test(source),
    '晚挂必须写 nekoChatWindowImpl.X，写 window.nekoChatWindow.X 在隔离态会静默失效');
  assert.ok(!/var W = window\.nekoChatWindow;/.test(source),
    'preload 内部要直接用 nekoChatWindowImpl，不要读页面那份门面');
  assert.ok(!/window\.nekoChatWindow\s*&&/.test(source),
    'preload 内部的 bringToFront 兜底也要走 nekoChatWindowImpl');
});

test('屏幕点换算函数保持 preload 内部（P2 不暴露）', () => {
  assert.ok(!source.includes("exposeToPage('__nekoGetAvatarToolClientScreenPoint'"));
  assert.ok(!source.includes("exposeToPage('__nekoGetAvatarToolScreenClientPoint'"));
});
