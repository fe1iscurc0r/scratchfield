/**
 * WO-278 · Pet 窗「页面全局」耦合的契约闸
 *
 * 为什么需要这个测试：
 *   preload-pet.js 跑在隔离世界，读不到页面的 `window.mmdManager` 这类全局（JS 全局不跨世界）。
 *   P1 已经把所有「数据/函数类」全局改成经 `pageApi(name)` 从页面注册面取值，
 *   P2-A 迁了模型态（`modelType` / `clearModelDragging`），
 *   P2-E 迁了点歌台（`Jukebox.*`，21 处裸读 → 6 处非隔离回落）。
 *   但这些成果此前**没有任何测试守着** —— 谁将来在新代码里顺手写一句
 *   `window.live2dManager.pauseRendering()`，隔离态下会静默失效，现有测试全绿。
 *
 * 本测试守四件事：
 *   1. 已登记的页面全局读取处数**只能减不能增**（棘轮）；
 *   2. 出现**未登记**的页面全局读取 → 直接失败，必须在下面登记并说明归属；
 *   3. 已迁移的域，残留只允许出现在 `process.contextIsolated` 的回落分支上
 *      （否则等于"迁移了但留下裸读"，隔离态照样静默失效）；
 *   4. 已迁移的域，页面注册面必须真的注册了对应成员 —— 只改 preload 不改页面，
 *      等于把调用改成永远拿 undefined，比不改更糟。
 *
 * 边界（照 WO-278 路线文档）：
 *   - DOM 标准 API 不在统计范围（contextIsolation 只分离 JS 全局，不分离 DOM）；
 *   - `window.X = ...` 赋值视为「preload 主动暴露给页面」，不是读取，豁免；
 *   - 域 A（模型态）、B（测量）、C（渲染控制）、D（视线）、E（点歌台）均已迁移；
 *     剩下的 `interaction` / `currentModel` / `getCurrentModel` 直接决定点击穿透区域，
 *     裸读处数如实登记在 RAW_READ_RATCHET 里，作为推进起点。
 *   - 已迁移域登记在 MIGRATED_FALLBACK：残留只允许是 `process.contextIsolated`
 *     回落那一处，且页面注册面必须真的注册了对应键（漏改一边 = 隔离态永久 undefined）。
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const PRELOAD = path.resolve(__dirname, '..', 'src', 'preload-pet.js');
const PAGE_BRIDGE = path.resolve(
  __dirname, '..', '..', 'NEKO', 'N.E.K.O', 'static', 'app', 'pet-host-bridge.js');
const COEXIST_FALLBACK = 'process.contextIsolated';

/**
 * 已登记的「页面全局裸读」处数上限 —— **只能减，不能增**。
 *
 * 每一处都是「隔离态下会读到 undefined」的位置，属于 P2 待迁移面。
 * 数字来自 2026-10-29 的实测统计（剥离注释 + 排除字符串字面量）。
 */
const RAW_READ_RATCHET = {
  // 三个管理器的成员访问已**全部**迁完（域 A/B/C/D/E/F，2026-10-30）。
  // 剩下这点是仅有的两处例外，都是**写穿**而不是读，过不了桥，只能登记：
  //   - petModelRaw()            非隔离回落取一次实例，之后一律用动态成员名访问；
  //   - hookLive2DModelLoaded / hookLive2DInputRegionLoaded
  //     给 manager 打补丁（mgr.onModelLoaded = …），Linux X11 / Wayland 专用。
  mmdManager: 1,
  vrmManager: 1,
  live2dManager: 3,
  // ── P1 已迁，这 5 处是**非隔离回落**（petDragHelpersBusy / petDragHelpersRestore）──
  DragHelpers: 5,
};

/**
 * 已迁移的域：剩下的 `window.X` 只允许是**非隔离回落**（`process.contextIsolated` 分支）。
 *
 * 数量必须精确 —— 多一处说明有人又写了裸读，少一处说明回落分支被删了
 * （删了会让非隔离模式直接坏掉，petWindow 现在正是非隔离）。
 */
const MIGRATED_FALLBACK = {
  // 域 A：模型态（P2-A）
  modelType: 0,
  // 域 E：点歌台（P2-E，2026-10-29）
  // petJukeboxPresent / ModelType / State / Has / Call 五处回落
  Jukebox: 6,
  // 截图域：头像捕获（P2-D，2026-10-29）
  // petAvatarPortraitCapture 一处回落
  avatarPortrait: 1,
};

/** 各迁移域在页面注册面上必须存在的成员（键名 = pageApi 的参数）。 */
const REQUIRED_PAGE_KEYS = {
  Jukebox: [
    'Jukebox.present', 'Jukebox.getModelType', 'Jukebox.state',
    'Jukebox.playVRMA', 'Jukebox.playVMD', 'Jukebox.stopVMD', 'Jukebox.togglePause',
  ],
  avatarPortrait: ['avatarPortrait.capture'],
  // 域 C：三个管理器 × pause/resume/reset（纯命令，2026-10-30 迁移）
  // 顺序 model:<kind>:<op>，与 preload 的拼法一致 —— 反了就是永久 undefined
  modelOps: [
    'model:mmd:pauseRendering', 'model:vrm:pauseRendering', 'model:live2d:pauseRendering',
    'model:mmd:resumeRendering', 'model:vrm:resumeRendering', 'model:live2d:resumeRendering',
    'model:mmd:resetModelPosition', 'model:vrm:resetModelPosition', 'model:live2d:resetModelPosition',
  ],
  // 域 B：测量（2026-10-30）—— 回纯数字矩形快照，不是 bounds 实例
  modelBounds: ['bounds:mmd', 'bounds:vrm', 'bounds:live2d'],
  // 域 D：视线跟随（2026-10-30）—— 回调名两路不对称，键名必须与 preload 逐字一致
  modelGaze: ['gaze:mmd', 'gaze:vrm'],
  // 域 F：穿透判定（2026-10-30）—— 直接决定「鼠标算不算点在模型上」
  modelProbe: [
    'modelLocked', 'modelGoodbye',
    'present:mmd', 'present:vrm',
    'screenBounds:mmd', 'screenBounds:vrm',
    'hit:mmd', 'hit:vrm',
    'localBounds:live2d', 'hitAreas:live2d',
  ],
};

/**
 * 待迁域**按成员**的访问清单 —— 2026-10-30 起**三张表都空了**。
 *
 * 空表不是"没用了"，而是最严格的一档：谁再写一句 `window.mmdManager.foo`，
 * 立刻报「新增未登记成员」。域 B（测量）/ C（渲染控制）/ D（视线）/ F（穿透判定）
 * 已全部迁到页面注册面，因此这里只剩注释，不再有登记项。
 */
const PENDING_MEMBERS = {
  mmdManager: [],
  vrmManager: [],
  live2dManager: [],
};

/** contextIsolation 不分离 DOM，这些照常可用，不计入。 */
const DOM_STANDARD = new Set([
  'addEventListener', 'removeEventListener', 'dispatchEvent',
  'innerWidth', 'innerHeight', 'outerWidth', 'outerHeight',
  'devicePixelRatio', 'requestAnimationFrame', 'cancelAnimationFrame',
  'setTimeout', 'clearTimeout', 'setInterval', 'clearInterval',
  'getComputedStyle', 'location', 'scrollX', 'scrollY', 'screenX', 'screenY',
  'document', 'navigator', 'performance', 'localStorage', 'sessionStorage',
  'matchMedia', 'postMessage', 'getSelection',
  'WebSocket', 'fetch', 'screen',
]);

function readSource() {
  assert.ok(fs.existsSync(PRELOAD), `找不到 ${PRELOAD}`);
  return fs.readFileSync(PRELOAD, 'utf8');
}

/** 剥离块注释与行注释，行数保持不变（便于报行号）。 */
function stripComments(source) {
  const noBlock = source.replace(/\/\*[\s\S]*?\*\//g, (m) => '\n'.repeat((m.match(/\n/g) || []).length));
  return noBlock.split('\n').map((line) => {
    const i = line.indexOf('//');
    return i >= 0 ? line.slice(0, i) : line;
  });
}

/** 该位置是否落在字符串字面量里（避免把 'window.mmdManager 未就绪' 这类日志算成读取）。 */
function insideString(line, pos) {
  const pre = line.slice(0, pos).replace(/\\\\./g, '');
  return pre.split('\'').length % 2 === 0 || pre.split('"').length % 2 === 0;
}

/**
 * 抽 `window.<name>` 的出现，区分「读」与「写」。
 * 写 = 紧跟 `=`（且不是 ==/===/=>），视为 preload 主动暴露，豁免。
 */
function collectAccess(lines) {
  const reads = new Map();   // name -> [lineNo]
  const writes = new Map();  // name -> [lineNo]

  lines.forEach((line, idx) => {
    const re = /\bwindow\.([A-Za-z_$][\w$]*)/g;
    let m;
    while ((m = re.exec(line)) !== null) {
      const name = m[1];
      if (DOM_STANDARD.has(name)) continue;
      if (insideString(line, m.index)) continue;

      const rest = line.slice(m.index + m[0].length);
      const isAssign = /^\s*=(?![=>])/.test(rest);
      const target = isAssign ? writes : reads;
      if (!target.has(name)) target.set(name, []);
      target.get(name).push(idx + 1);
    }
  });

  return { reads, writes };
}

/**
 * 抽 `window.<manager>.<member>` 的成员名集合。
 * 注意与 `collectAccess` 的区别：那条统计的是「读了哪个页面全局」，
 * 这条统计的是「读了这个全局的哪个成员」—— 迁移是按成员做的。
 */
function collectMembers(lines) {
  const out = new Map();
  for (const name of Object.keys(PENDING_MEMBERS)) {
    const re = new RegExp('\\bwindow\\.' + name + '\\b\\s*\\.\\s*([A-Za-z_$][\\w$]*)', 'g');
    const found = new Set();
    lines.forEach((line) => {
      let m;
      while ((m = re.exec(line)) !== null) {
        if (insideString(line, m.index)) continue;
        found.add(m[1]);
      }
    });
    out.set(name, found);
  }
  return out;
}

test('页面全局裸读处数只能减少，不能新增', () => {
  const { reads } = collectAccess(stripComments(readSource()));
  const over = [];

  for (const [name, cap] of Object.entries(RAW_READ_RATCHET)) {
    const actual = (reads.get(name) || []).length;
    if (actual > cap) over.push(`${name}: 登记 ${cap}，实得 ${actual}（行 ${reads.get(name).join(', ')}）`);
  }

  assert.deepStrictEqual(over, [],
    '存在超出棘轮的页面全局裸读。隔离态下这些读取会拿到 undefined：\n' + over.join('\n') +
    '\n修法：改成 pageApi(\'<名字>\')，由页面侧通过 window.nekoPetHost.register 提供；' +
    '若确实必须新增，先在本文件 RAW_READ_RATCHET 里登记并写明归属域。');

  // 反向：棘轮只降不升——若某名字已经降到 0，提醒把登记项删掉
  const stale = Object.entries(RAW_READ_RATCHET)
    .filter(([name]) => (reads.get(name) || []).length === 0);
  assert.deepStrictEqual(stale.map(([n]) => n), [],
    `这些名字已无裸读，请从 RAW_READ_RATCHET 删除：${stale.map(([n]) => n).join(', ')}`);
});

test('未登记的页面全局读取必须为 0', () => {
  const lines = stripComments(readSource());
  const { reads, writes } = collectAccess(lines);

  // preload 自己 `window.X = ...` 建过的 → 自建自读，豁免
  const selfBuilt = new Set(writes.keys());

  const unregistered = [];
  for (const [name, lineNos] of reads) {
    if (RAW_READ_RATCHET[name] !== undefined) continue;
    if (MIGRATED_FALLBACK[name] !== undefined) continue;  // 由下一条用例按回落规则严查
    if (selfBuilt.has(name)) continue;
    unregistered.push(`${name}: ${lineNos.length} 处（行 ${lineNos.slice(0, 6).join(', ')}）`);
  }

  assert.deepStrictEqual(unregistered, [],
    '发现未登记的页面全局读取。它们要么走 pageApi，要么是 preload 自建（需先 `window.X = ...`）：\n'
    + unregistered.join('\n'));
});

test('已迁移的域：残留只允许在非隔离回落分支，且数量精确', () => {
  const lines = stripComments(readSource());
  const { reads } = collectAccess(lines);
  const problems = [];

  for (const [name, expected] of Object.entries(MIGRATED_FALLBACK)) {
    const lineNos = reads.get(name) || [];
    if (lineNos.length !== expected) {
      problems.push(`${name}: 登记 ${expected} 处，实得 ${lineNos.length} 处（行 ${lineNos.join(', ') || '无'}）`);
    }
    // 每处都必须与 process.contextIsolated 同行，否则就是"迁了一半"
    const escaped = lineNos.filter((n) => !lines[n - 1].includes(COEXIST_FALLBACK));
    if (escaped.length) {
      problems.push(`${name}: 行 ${escaped.join(', ')} 不在 ${COEXIST_FALLBACK} 回落分支里`
        + ` ——「${COEXIST_FALLBACK} ? … : window.${name}」或 if 同行的写法才算回落`);
    }
  }

  assert.deepStrictEqual(problems, [],
    '已迁移域的残留不合规：\n' + problems.join('\n') +
    '\n迁移后应只剩「非隔离回落」那一处；新增裸读请改成 pageApi(\'<键名>\')。');
});

test('已迁移的域：页面注册面必须真的注册了对应成员', () => {
  assert.ok(fs.existsSync(PAGE_BRIDGE), `找不到页面注册面 ${PAGE_BRIDGE}`);
  const src = fs.readFileSync(PAGE_BRIDGE, 'utf8');
  const missing = [];

  for (const [domain, keys] of Object.entries(REQUIRED_PAGE_KEYS)) {
    const absent = keys.filter((k) => !src.includes(`'${k}'`));
    if (absent.length) missing.push(`${domain}: 缺少 ${absent.join(', ')}`);
  }

  assert.deepStrictEqual(missing, [],
    'preload 已改成走 pageApi，但页面侧没有注册这些键 —— 隔离态下会永远拿到 undefined，'
    + '比不改更糟：\n' + missing.join('\n') +
    '\n修法：在 pet-host-bridge.js 的 GETTERS 里补上（实例方法要返回闭包，别裸传函数引用）。');
});

test('待迁域的成员面必须与 PENDING_MEMBERS 完全一致（新增成员要登记）', () => {
  const actual = collectMembers(stripComments(readSource()));
  const problems = [];

  for (const [name, registered] of Object.entries(PENDING_MEMBERS)) {
    const seen = actual.get(name) || new Set();
    const extra = [...seen].filter((m) => !registered.includes(m));
    const gone = registered.filter((m) => !seen.has(m));
    if (extra.length) {
      problems.push(`${name}: 新增未登记成员 ${extra.join(', ')}（隔离态下会读到 undefined；`
        + '若刚迁完某个成员，请从 PENDING_MEMBERS 删掉它）');
    }
    if (gone.length) {
      problems.push(`${name}: 登记的成员 ${gone.join(', ')} 已不再被访问 —— 迁完了就删登记，别让表腐烂`);
    }
  }

  assert.deepStrictEqual(problems, [], problems.join('\n'));
});

test('pageApi 是唯一出口：取值必须经它，不许直接 return window.X', () => {
  const source = readSource();
  // pageApi 定义本身允许读 window[name]（非隔离回落）
  const apiDef = /function\s+pageApi\s*\([^)]*\)\s*\{[\s\S]*?\n\}/.exec(source);
  assert.ok(apiDef, 'preload-pet.js 里找不到 pageApi() 定义——P1 的取值入口被删了？');

  const body = apiDef[0];
  assert.ok(/window\[name\]/.test(body),
    'pageApi 的非隔离回落分支应当读 window[name]（否则非隔离模式直接坏掉）');
  assert.ok(/petHost/.test(body),
    'pageApi 的隔离分支应当经 petHost（页面注册面）取值');
  assert.ok(/misses/.test(body) || /petDiag/.test(body),
    'pageApi 应当记录 miss（否则观测层失效，无法判断哪些名字还没注册）');
});
