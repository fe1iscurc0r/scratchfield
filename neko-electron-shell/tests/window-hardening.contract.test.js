// 窗口安全基线契约测试（WO-270 T2/T3 产物）。
//
// 为什么是「契约测试」而不是功能测试：P0-10/P0-11 的完整修复要把 8124 行的
// preload-chat-react.js 迁到 contextBridge，那是独立工程；本文件先把**已经收敛到的
// 基线钉住**，并保证它不会悄悄反弹：
//   1) 任何窗口都不许再打开 nodeIntegration；
//   2) 每个 contextIsolation:false / webSecurity:false 都必须落在白名单窗口里，且带同行注释；
//   3) window.open 子窗口不许无差别发放 webSecurity:false 特权（同源判定是唯一豁免）；
//   4) 已隔离的窗口的 preload 不许再直接写 window.*。
// 运行：npm test（= node --test "tests/*.test.js"）。
//   注意别写成 `node --test tests/`：Windows 下会把目录当模块解析并报
//   Cannot find module '...\tests'，glob 形式才走得通。
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const SRC_DIR = path.resolve(__dirname, '..', 'src');

// 白名单：key = 文件相对 src/ 的路径，value = { 窗口变量名: 该窗口允许为 false 的开关 }
// 每加一项都必须在 docs/WO-270-p0-frontend-electron.md 里给出理由；不加理由的豁免视为回归。
const CHILD_WINDOW_LABEL = '(window.open 子窗口)';

// 文件级豁免：这些文件的 BrowserWindow 不是 `X = new BrowserWindow(` 形式（反推不出窗口名），
// 只能整文件登记。新增前必须先在源码那一行写清理由。
const FILE_LEVEL_ISOLATION_EXCEPTIONS = {
  'avatar-tool-cursor-service.js': '光标捕获 overlay：preload 只做 DOM 注入，触发链路未做运行期验证',
  'tutorial-global-overlay-service.js': '教程 overlay（全局光效 + 加载覆盖层）：同上',
};

const ISOLATION_EXCEPTIONS = {
  'window-manager.js': {
    petWindow: ['contextIsolation'],            // preload-pet.js 直写 14 处 window.*（无 contextBridge），页面按全局读
  },
  'main/pet-window-lifecycle.js': {
    mainWindow: ['contextIsolation'],           // 同一份 preload-pet.js（createWindow 里先攒 windowOptions 再 new）
    petWindow: ['contextIsolation'],
  },
};

// 反向棘轮靠「白名单里没有名字」实现：toastWindow / jukeboxWindow / subtitleWindow 等
// 已是 contextIsolation:true，谁改回 false 就撞上 test 2 的「未登记的不隔离窗口」。
// 白名单里不留它们的名字，也不许新增。

// webSecurity:false 的豁免窗口：这些页面在运行期需要跨源能力（或本机后端可配置为远程 URL），
// 静态证据不足以直接翻，留作 P0-10/P0-11 的后续项，逐窗口验证后再摘。
const WEBCSECURITY_EXCEPTIONS = {
  'window-manager.js': [
    'jukeboxWindow',            // 点歌台会从白名单外部 https 源取素材
    'toastWindow',
    'reactChatWindow',
    'fullChatWindow',
    'compactChatBallWindow',    // 页面是 data: URL（origin=null），素材要从 baseUrl 的 /static/ 取
  ],
};

const CHILD_WEBSECURITY_EXPRESSION = '!childIsSameOriginLocal';

function readSource(rel) {
  const file = path.join(SRC_DIR, rel);
  if (!fs.existsSync(file)) return null;
  return fs.readFileSync(file, 'utf8');
}

function listSourceFiles() {
  const out = [];
  const walk = (dir, prefix) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) walk(path.join(dir, entry.name), rel);
      else if (entry.isFile() && entry.name.endsWith('.js')) out.push(rel);
    }
  };
  walk(SRC_DIR, '');
  return out;
}

// 找到某行所属的窗口：向上找最近的 `xxx = new BrowserWindow(`；
// 若先撞上 setWindowOpenHandler(，说明这行属于子窗口配置块（不是任何顶层窗口）。
// 向上找不到时再向下找 —— Pet 这类窗口是「先攒 winOptions 字面量，几十行后才 new」，
// 配置行的上方根本没有创建语句（window-manager.js:368 / pet-window-lifecycle.js:905）。
function enclosingWindowName(lines, lineIndex) {
  for (let i = lineIndex; i >= 0 && i > lineIndex - 200; i -= 1) {
    const created = /([A-Za-z0-9_$]+)\s*=\s*new BrowserWindow\(/.exec(lines[i]);
    if (created) return created[1];
    if (lines[i].includes('setWindowOpenHandler(')) return CHILD_WINDOW_LABEL;
  }
  for (let i = lineIndex + 1; i < lines.length && i < lineIndex + 120; i += 1) {
    const created = /([A-Za-z0-9_$]+)\s*=\s*new BrowserWindow\(/.exec(lines[i]);
    if (created) return created[1];
  }
  return null;
}

// 把行内注释切掉再匹配，免得注释里提到的 `webSecurity:false` 被当成代码。
// 规则：第一个「前面不是冒号」的 // 视为注释起点（避开 http:// 这类字符串）。
function stripLineComment(line) {
  const trimmed = line.trim();
  if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return '';
  for (let i = 0; i < line.length - 1; i += 1) {
    if (line[i] === '/' && line[i + 1] === '/' && line[i - 1] !== ':') return line.slice(0, i);
  }
  return line;
}

function flagLines(source, flag, wantValue) {
  const lines = source.split(/\r?\n/);
  const hits = [];
  lines.forEach((line, index) => {
    const code = stripLineComment(line);
    const re = new RegExp(`\\b${flag}\\s*:\\s*${wantValue}\\b`);
    if (re.test(code)) hits.push({ line, index, number: index + 1 });
  });
  return hits;
}

// 注释里提到的 `webSecurity:false` 不是代码：整块断言前先按行剥注释。
function stripComments(block) {
  return block.split(/\r?\n/).map(stripLineComment).join('\n');
}

// 从 fromIndex 起找到第一个 `webPreferences:`，按大括号配对截出整个对象字面量。
// 若写成 `webPreferences: someVar,`（React Chat 子窗就是把字面量提到上面的
// `const childWebPreferences = {...}`），则先在 fromIndex 之后解析该声明再截块，
// 否则会一路匹配到函数体后面的无关大括号，把子窗口配置读错。
function firstWebPreferencesBlock(source, fromIndex) {
  const start = source.indexOf('webPreferences', fromIndex);
  if (start < 0) return null;
  const afterColon = source.slice(source.indexOf(':', start) + 1);
  const indirect = /^\s*([A-Za-z0-9_$]+)\s*[,)]/.exec(afterColon);
  let valuePos = source.indexOf(':', start) + 1;
  if (indirect) {
    const decl = new RegExp(`(?:const|let|var)\\s+${indirect[1]}\\s*=\\s*\\{`)
      .exec(source.slice(fromIndex));
    if (!decl) return null;
    valuePos = fromIndex + decl.index + decl[0].length - 1;
  }
  const brace = source.indexOf('{', valuePos);
  if (brace < 0) return null;
  let depth = 0;
  for (let i = brace; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(brace, i + 1);
    }
  }
  return null;
}

test('所有窗口都不允许 nodeIntegration:true', () => {
  const offenders = [];
  for (const rel of listSourceFiles()) {
    const source = readSource(rel);
    if (!source) continue;
    for (const hit of flagLines(source, 'nodeIntegration', 'true')) {
      offenders.push(`${rel}:${hit.number}: ${hit.line.trim()}`);
    }
  }
  assert.deepStrictEqual(offenders, [], `nodeIntegration 必须全站关闭：\n${offenders.join('\n')}`);
});

test('contextIsolation:false 只允许出现在白名单窗口，且必须带同行说明', () => {
  const violations = [];
  let allowed = 0;
  // 扫**整个 src**：以前只遍历白名单里的文件，于是未登记文件里新开一个
  // contextIsolation:false 的窗口不会被任何断言看见（真实缺口）。
  for (const rel of listSourceFiles()) {
    const source = readSource(rel);
    if (!source) continue;
    for (const hit of flagLines(source, 'contextIsolation', 'false')) {
      const win = enclosingWindowName(source.split(/\r?\n/), hit.index);
      const windowLevel = win && ISOLATION_EXCEPTIONS[rel]?.[win]?.includes('contextIsolation');
      const fileLevel = !win && Boolean(FILE_LEVEL_ISOLATION_EXCEPTIONS[rel]);
      if (!windowLevel && !fileLevel) {
        violations.push(`${rel}:${hit.number} 窗口=${win || '(未识别)'} => ${hit.line.trim()}`);
        continue;
      }
      // 豁免必须自带解释：同一行（或紧邻上一行）要有注释
      const lines = source.split(/\r?\n/);
      const commentOnLine = hit.line.includes('//');
      const commentAbove = /^\s*(\/\/|\*|\/\*)/.test(lines[hit.index - 1] || '');
      assert.ok(commentOnLine || commentAbove,
        `${rel}:${hit.number} 的 contextIsolation:false 缺同行注释（豁免必须写清原因）`);
      allowed += 1;
    }
  }
  assert.deepStrictEqual(violations, [], `出现未登记的不隔离窗口：\n${violations.join('\n')}`);
  // 精确棘轮：多一处（新开豁免）或少一处（迁移完成）都必须回来改这个常量，
  // 否则契约会悄悄和代码脱钩。当前 5 处 = pet 2 处 + overlay 3 处。
  const EXPECTED_FALSE_COUNT = 5;
  assert.strictEqual(allowed, EXPECTED_FALSE_COUNT,
    `contextIsolation:false 的登记数应为 ${EXPECTED_FALSE_COUNT}，实得 ${allowed}——`
    + '新增豁免请在源码同行写清理由并同步本契约；迁移完成则下调这个常量');
});

test('jukebox 主窗与 manager 子窗已开隔离，webSecurity 仍按白名单登记且带说明', () => {
  const source = readSource('window-manager.js');
  const lines = source.split(/\r?\n/);
  assert.ok(/jukeboxWindow = new BrowserWindow\([\s\S]*?contextIsolation: true,/.test(source),
    'jukebox 主窗口应已 contextIsolation: true（P0-11）');
  const hits = flagLines(source, 'webSecurity', 'false');
  assert.ok(hits.length >= 5,
    `白名单按 5 个顶层窗口登记，实得 ${hits.length} 处——数量对不上说明契约与代码脱钩`);
  for (const hit of hits) {
    const win = enclosingWindowName(lines, hit.index);
    const allowedList = WEBCSECURITY_EXCEPTIONS['window-manager.js'];
    assert.ok(allowedList.includes(win),
      `src/window-manager.js:${hit.number} 的 webSecurity:false 属于未登记窗口 ${win}`);
    const commented = hit.line.includes('//') || /^\s*(\/\/|\*|\/\*)/.test(lines[hit.index - 1] || '');
    assert.ok(commented, `${hit.number} 的 webSecurity:false 缺同行注释（豁免必须写清原因）`);
  }
});

test('window.open 子窗口不得无差别发放 webSecurity:false', () => {
  const source = readSource('window-manager.js');
  const marker = 'setWindowOpenHandler(';
  const positions = [];
  for (let i = source.indexOf(marker); i >= 0; i = source.indexOf(marker, i + 1)) {
    positions.push(i);
  }
  assert.strictEqual(positions.length, 2,
    `预期 React Chat / Jukebox 两处子窗口处理器，实得 ${positions.length} —— 新增入口请同步更新契约`);
  positions.forEach((pos, i) => {
    const rawBlock = firstWebPreferencesBlock(source, pos);
    assert.ok(rawBlock, `第 ${i + 1} 处子窗口处理器里找不到 webPreferences`);
    const block = stripComments(rawBlock);
    assert.ok(!/\bwebSecurity\s*:\s*false\b/.test(block),
      `第 ${i + 1} 处子窗口处理器给所有 URL 发 webSecurity:false；应按同源判定收窄`);
    assert.ok(block.includes(`webSecurity: ${CHILD_WEBSECURITY_EXPRESSION}`),
      `第 ${i + 1} 处子窗口处理器应使用 webSecurity: ${CHILD_WEBSECURITY_EXPRESSION}`);
    // 同源判定必须先于豁免出现，否则等于把特权又发回所有 URL
    assert.ok(/const childIsSameOriginLocal = shouldAttachSameOriginChildPreload\(/.test(block)
      || /shouldAttachSameOriginChildPreload\(/.test(source.slice(pos, pos + 4000)),
      `第 ${i + 1} 处子窗口处理器的 ${CHILD_WEBSECURITY_EXPRESSION} 没有对应的同源判定来源`);
  });
});

test('已隔离窗口的 preload 不得再直接写 window.*', () => {
  const source = readSource('preload-jukebox.js');
  assert.ok(source, 'src/preload-jukebox.js 不存在');
  const direct = [];
  source.split(/\r?\n/).forEach((line, index) => {
    if (/^\s*window\.[A-Za-z0-9_$]+\s*=/.test(line) && !line.includes('exposeToPage')) {
      direct.push(`${index + 1}: ${line.trim()}`);
    }
  });
  assert.deepStrictEqual(direct, [],
    `jukebox 窗口已是 contextIsolation:true，直接写 window.* 页面读不到：\n${direct.join('\n')}`);
  assert.ok(/process\.contextIsolated/.test(source) && /contextBridge\.exposeInMainWorld/.test(source),
    'preload-jukebox.js 必须保留双模暴露（隔离走 contextBridge，非隔离走 window）');
});

test('compact chat ball 窗必须开 contextIsolation（WO-278 批 1）', () => {
  // 它过去是唯一一扇「因为 preload 要读页面写的内联全局」而开不了隔离的窗。
  // 现在开关改走 additionalArguments，页面与 preload 不再共享全局，隔离必须打开，
  // 谁改回 false 都会撞上「未登记的不隔离窗口」这条 —— 这里再单独钉一次，把原因留在案发现场。
  const source = readSource('window-manager.js');
  assert.ok(source, 'window-manager.js 必须存在');
  const lines = source.split(/\r?\n/);
  const hits = flagLines(source, 'contextIsolation', 'false').filter(
    (hit) => enclosingWindowName(lines, hit.index) === 'compactChatBallWindow',
  );
  assert.deepStrictEqual(hits, [], 'compactChatBallWindow 不允许 contextIsolation:false');
  const ballBlock = firstWebPreferencesBlock(source, source.indexOf('function showCompactChatBallWindow'));
  assert.ok(ballBlock, '没找到 compact chat ball 的 webPreferences');
  assert.match(ballBlock, /additionalArguments:\s*skipAppear\s*\?/, '必须用 additionalArguments 传 skipAppear');
});

test('同源子窗口必须开 contextIsolation（WO-278 批 2）', () => {
  // preload-child.js 是双模写法：隔离时 exposeInMainWorld，否则写 window.nekoWindowControl。
  // 既然桥那一半早就写好了，窗口就不能再停在 false 上 —— 否则页面能直接改写宿主能力对象。
  const source = readSource('window-manager.js');
  const lines = source.split(/\r?\n/);
  const hits = flagLines(source, 'contextIsolation', 'false').filter(
    (hit) => enclosingWindowName(lines, hit.index) === CHILD_WINDOW_LABEL,
  );
  assert.deepStrictEqual(hits, [], '同源子窗口不允许 contextIsolation:false');
  const block = source.slice(source.indexOf('const childWebPreferences = {'));
  assert.match(block.slice(0, 800), /contextIsolation:\s*true/, 'childWebPreferences 必须显式写 true');
});

// ---------------------------------------------------------------- 构造器替换边界 --
// WO-278 批 3 的实测结论：preload 里 `window.WebSocket = WSProxy` 这类**构造器替换**
// 是 contextBridge 的硬边界 —— `exposeInMainWorld` 只能新增命名空间属性，
// 顶替不了页面已有的全局构造器。所以这些窗一旦开隔离，页面的 `new WebSocket(...)`
// 会退回原生实现，WS 代理（Chat → IPC → 主进程 → Pet → 真 WS）就静默失效了。
//
// 这条测试不阻止将来改造，只要求：**改造前不许翻隔离**。要翻，必须先把页面侧改成
// 从 bridge 取工厂函数（如 `window.nekoChatWindow.WebSocketFactory`），再更新本表。
//
// 注：preload → 窗口 的映射**用约定表**，不用 enclosingWindowName 反推 ——
// 后者会把 `createReactChatWindow` 里的 preload 行归到前面的 `setWindowOpenHandler` 块，
// 误判成「子窗口用了 preload-chat-react」（实测踩过）。

const REPLACED_GLOBAL_CTORS = ['WebSocket', 'XMLHttpRequest', 'EventSource', 'Worker'];

const CTOR_PRELOAD_WINDOW = {
  'preload-chat-full': 'fullChatWindow',
  'preload-chat-react': 'reactChatWindow',
  'preload-pet': 'petWindow',
};

function isolatedWindowNames() {
  const source = readSource('window-manager.js');
  if (!source) return new Set();
  const lines = source.split(/\r?\n/);
  const names = new Set();
  for (const hit of flagLines(source, 'contextIsolation', 'true')) {
    const win = enclosingWindowName(lines, hit.index);
    if (win) names.add(win);
  }
  return names;
}

function preloadsReplacingGlobals() {
  const found = [];
  for (const rel of listSourceFiles()) {
    if (!rel.startsWith('preload-')) continue;
    const source = readSource(rel);
    if (!source) continue;
    const hits = REPLACED_GLOBAL_CTORS.filter((ctor) =>
      new RegExp(`window\\.${ctor}\\s*=(?!=)`).test(source),
    );
    if (hits.length) found.push({ rel, ctors: hits });
  }
  return found;
}

test('替换页面全局构造器的 preload，其窗口不得开 contextIsolation（WO-278 批 3）', () => {
  const replacing = preloadsReplacingGlobals();
  assert.ok(replacing.length > 0, '应当至少扫到一个构造器替换（preload-chat-full / -react / pet 等）');

  const isolated = isolatedWindowNames();
  const offenders = [];
  for (const { rel, ctors } of replacing) {
    const basename = rel.replace(/^.*\//, '').replace(/\.js$/, '');
    const win = CTOR_PRELOAD_WINDOW[basename];
    if (!win) continue; // 未登记的 preload 由人工判断，不在这里猜
    if (isolated.has(win)) {
      offenders.push(`${win} 用了 ${basename}.js（替换 ${ctors.join('/')}），却开了 contextIsolation:true`);
    }
  }
  assert.deepStrictEqual(
    offenders,
    [],
    `构造器替换类 preload 的窗口必须保持 contextIsolation:false，直到页面侧改走 bridge 工厂：\n${offenders.join('\n')}`,
  );
});

test('chatWindow 已改走 WS 桥并开 contextIsolation（WO-278 装配）', () => {
  // 装配后的正向约束：三件事必须同时成立，缺一条都会让聊天静默连不上或不安全。
  const wm = readSource('window-manager.js');
  const lines = wm.split(/\r?\n/);
  const chatFalse = flagLines(wm, 'contextIsolation', 'false').filter(
    (hit) => enclosingWindowName(lines, hit.index) === 'chatWindow',
  );
  assert.deepStrictEqual(chatFalse, [], 'chatWindow 不允许 contextIsolation:false');

  const preload = readSource('preload-chat.js');
  assert.ok(preload, 'src/preload-chat.js 不存在');
  assert.ok(!/window\.WebSocket\s*=(?!=)/.test(preload),
    'preload-chat.js 不得再替换页面全局 WebSocket（隔离后会被静默忽略）');
  assert.match(preload, /exposeToPage\(\s*['"]nekoWebSocket['"]/,
    'preload-chat.js 必须把 nekoWebSocket 交给 exposeToPage（隔离走 contextBridge）');
  assert.match(preload, /contextBridge\.exposeInMainWorld\(/,
    'preload-chat.js 必须有 contextBridge 暴露路径');
  assert.match(preload, /createWebSocketBridge\(/,
    'preload-chat.js 必须复用 websocket-bridge.js 的工厂');

  // 页面唯一建连点必须走适配器，且模板里适配器先于 app-websocket.js 加载
  const pageRoot = path.resolve(__dirname, '..', '..', 'NEKO', 'N.E.K.O');
  const pageWs = fs.readFileSync(path.join(pageRoot, 'static', 'app', 'app-websocket.js'), 'utf8');
  assert.match(pageWs, /window\.__nekoCreateWebSocket\s*\(/,
    'app-websocket.js 必须用 window.__nekoCreateWebSocket 建连');
  assert.strictEqual((pageWs.match(/new WebSocket\(/g) || []).length, 1,
    '原生 new WebSocket 只应保留在适配器缺失时的回退分支里');
  for (const tpl of ['chat.html', 'index.html']) {
    const html = fs.readFileSync(path.join(pageRoot, 'templates', tpl), 'utf8');
    const adapterAt = html.indexOf('/static/app/ws-adapter.js');
    const wsAt = html.indexOf('/static/app/app-websocket.js');
    assert.ok(adapterAt > 0 && wsAt > 0 && adapterAt < wsAt,
      `${tpl} 必须先加载 ws-adapter.js 再加载 app-websocket.js`);
  }
});

test('reactChatWindow / fullChatWindow 已改走 WS 桥并开 contextIsolation（WO-278 P1-c）', () => {
  const wm = readSource('window-manager.js');
  const lines = wm.split(/\r?\n/);
  for (const win of ['reactChatWindow', 'fullChatWindow']) {
    const still = flagLines(wm, 'contextIsolation', 'false').filter(
      (hit) => enclosingWindowName(lines, hit.index) === win,
    );
    assert.deepStrictEqual(still, [], `${win} 不允许 contextIsolation:false`);
  }

  for (const rel of ['preload-chat-react.js', 'preload-chat-full.js']) {
    const src = readSource(rel);
    assert.ok(src, `src/${rel} 不存在`);
    assert.ok(!/window\.WebSocket\s*=(?!=)/.test(src),
      `${rel} 不得再替换页面全局 WebSocket（隔离后会被静默忽略）`);
    assert.match(src, /exposeToPage\(\s*['"]nekoWebSocket['"]/,
      `${rel} 必须把 nekoWebSocket 交给 exposeToPage`);
    assert.match(src, /createPageSocket\(/, `${rel} 必须提供 createPageSocket 句柄工厂`);
  }
});

// ---------------------------------------------------------------- WO-278 P1（pet 注册面）--
// pet 窗仍是 contextIsolation:false，但 preload 侧的「页面全局」依赖已经开始收口：
// 数据/函数类 17 个名字必须走 pageApi()（隔离后经页面注册的 getter 取值），
// 实例类 5 个仍直接读 window.X —— 那是 P2，对象过桥会丢原型方法，不能机械替换。
const PET_BRIDGED_NAMES = [
  'lanlan_config', 'appState', 'pageConfigReady', 'nekoSubtitleShared', 'appButtons',
  '_agentTaskMap', 'master_name', 'master_profile_name', 'master_nickname', 'master_display_name',
  'DragHelpers', 'captureProactiveChatScreenshot', 'resetToDefaultModel',
  'captureScreenshotDataUrl', 'subtitleBridge', 'safeT', 't',
];
const PET_INSTANCE_PENDING = ['mmdManager', 'vrmManager', 'live2dManager', 'Jukebox', 'avatarPortrait'];

test('pet preload：数据/函数类全局必须走 pageApi，实例类留给 P2（WO-278 P1）', () => {
  const src = readSource('preload-pet.js');
  assert.ok(src, 'src/preload-pet.js 不存在');

  // 1) DragHelpers 的两个入口单独写，整体引用必须为 0
  assert.strictEqual((src.match(/pageApi\('DragHelpers'\)/g) || []).length, 0,
    'DragHelpers 不能整体过桥（对象会丢 getter/方法），要用 pageApi(\'DragHelpers.*\')') ,
  assert.match(src, /pageApi\('DragHelpers\.isDragging'\)/, '缺少 DragHelpers.isDragging 入口');
  assert.match(src, /pageApi\('DragHelpers\.restoreButtonPointerEvents'\)/,
    '缺少 DragHelpers.restoreButtonPointerEvents 入口');

  // 2) 除 DragHelpers 外的 16 个名字：不得再出现 `window.X` 直接读
  // 只算「真正的代码读取」：跳过同行注释、跳过字符串字面量（日志文案里会提到 window.X）
  const stringRanges = (line) => {
    const out = [];
    let i = 0;
    while (i < line.length) {
      const ch = line[i];
      if (ch === '"' || ch === "'" || ch === '`') {
        let j = i + 1;
        while (j < line.length) {
          if (line[j] === '\\') { j += 2; continue; }
          if (line[j] === ch) break;
          j += 1;
        }
        out.push([i, Math.min(j + 1, line.length)]);
        i = j + 1;
        continue;
      }
      i += 1;
    }
    return out;
  };

  const offenders = [];
  const lines = src.split(/\r?\n/);
  for (const name of PET_BRIDGED_NAMES.filter((n) => n !== 'DragHelpers')) {
    const re = new RegExp('\\bwindow\\.' + name + '\\b');
    lines.forEach((line, i) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('//') || trimmed.startsWith('*')) return;
      const m = re.exec(line);
      if (!m) return;
      if (stringRanges(line).some(([a, b]) => a <= m.index && m.index < b)) return; // 字符串里不算
      const after = line.slice(m.index + ('window.' + name).length);
      if (/^\s*=(?!=)/.test(after)) return;                                        // 写入不算
      offenders.push(`${i + 1}: ${trimmed.slice(0, 90)}`);
    });
  }
  assert.deepStrictEqual(offenders, [],
    `这些地方应改用 pageApi('名字')（隔离后 window.X 读不到）：\n${offenders.join('\n')}`);

  // 3) 实例类仍直接读 —— 断言"还没做"，避免有人以为 P1 已经覆盖
  for (const name of PET_INSTANCE_PENDING) {
    assert.match(src, new RegExp('\\bwindow\\.' + name + '\\b'),
      `${name} 属于 P2（按成员拆函数），本阶段应仍直接读 window，若已迁移请同步更新本契约`);
  }
});

test('pet 页面注册面存在且被 index.html 引入（WO-278 P1）', () => {
  const bridge = path.resolve(SRC_DIR, '..', '..', 'NEKO', 'N.E.K.O', 'static', 'app', 'pet-host-bridge.js');
  assert.ok(fs.existsSync(bridge), '缺少 static/app/pet-host-bridge.js');
  const page = fs.readFileSync(bridge, 'utf8');
  assert.match(page, /window\.nekoPetHost/, 'pet-host-bridge 必须从 window.nekoPetHost 取注册面');
  assert.match(page, /\.register\(/, 'pet-host-bridge 必须调用 register()');

  const tpl = path.resolve(SRC_DIR, '..', '..', 'NEKO', 'N.E.K.O', 'templates', 'index.html');
  const html = fs.readFileSync(tpl, 'utf8');
  assert.match(html, /pet-host-bridge\.js/, 'index.html 必须引入 pet-host-bridge.js');

  // 引入顺序：注册面必须在 app-websocket.js 之前（页面建连前就位）
  const idxBridge = html.indexOf('pet-host-bridge.js');
  const idxWs = html.indexOf('app-websocket.js');
  assert.ok(idxBridge >= 0 && idxWs >= 0 && idxBridge < idxWs,
    'pet-host-bridge.js 应早于 app-websocket.js 加载');
});
