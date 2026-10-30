#!/usr/bin/env node
/**
 * pet 窗「活体验证」脚本 —— 不需要人手动拖鼠标。
 *
 * 背景：WO-278 翻 contextIsolation 之前，一直以「拖拽手感只能真机点」为由不推进。
 * 但真正需要人手的只有**主观手感**，功能层面完全可以机械验证：
 *   - 模型有没有加载（WebGL / pixi / currentModel）
 *   - 拖拽后模型位移是否精确等于输入位移
 *   - 拖拽态标志（`_isDraggingModel` / `interaction.isDragging`）有没有正确置位与复位
 *   - 页面有没有抛异常
 *
 * 做法：连 Electron 的 CDP（`--remote-debugging-port=9222`），用
 * `Input.dispatchMouseEvent` 发真实输入事件（页面收到的是真 pointer 事件，不是合成调用），
 * 再从页面读可观测状态做前后对比。
 *
 * 用法：
 *   node scripts/pet-live-verify.mjs list             列出所有 target
 *   node scripts/pet-live-verify.mjs probe            读模型态 + 诊断快照
 *   node scripts/pet-live-verify.mjs drag <dx> <dy>   模拟拖拽并打印前后对比
 *   node scripts/pet-live-verify.mjs verify           断言式验证（失败退出码 1）
 *   node scripts/pet-live-verify.mjs eval "<js>"      在 pet 窗里求值
 *
 * 前置：
 *   NEKO 主服务（48911）与 electron 都要在跑，且 electron 带 `--remote-debugging-port=9222`。
 *   ⚠️ **不要带 `--disable-gpu --disable-software-rasterizer`**：那会掐掉 WebGL，
 *      Live2D 模型加载不出来（`currentModel` 为 null），拖拽也就无从谈起。
 *
 * 端口：默认 9222，可用 `CDP_PORT=9333` 覆盖。
 *
 * 边界（如实登记）：
 *   - 验的是**功能**，不是手感（跟手度、惯性、边缘吸附这些只能人看）；
 *   - 非隔离窗里 preload 的顶层函数**不挂 window**（CommonJS 模块作用域），
 *     所以不能从页面直接调 `pageApi`/helper —— 只能观测页面侧对象与状态。
 */

import process from 'node:process';

const PORT = process.env.CDP_PORT || '9222';
const BASE = `http://127.0.0.1:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function listTargets() {
  const res = await fetch(`${BASE}/json/list`);
  if (!res.ok) throw new Error(`CDP 不可达: ${BASE}/json/list → HTTP ${res.status}`);
  return res.json();
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener('open', () => resolve());
      this.ws.addEventListener('error', () => reject(new Error('CDP WebSocket 连接失败')));
    });
    this.ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      const slot = msg.id && this.pending.get(msg.id);
      if (!slot) return;
      this.pending.delete(msg.id);
      if (msg.error) slot.reject(new Error(JSON.stringify(msg.error)));
      else slot.resolve(msg.result);
    });
  }

  send(method, params = {}, timeoutMs = 20000) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`CDP 超时: ${method}`));
      }, timeoutMs);
    });
  }

  async eval(expression) {
    const r = await this.send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true, userGesture: true,
    });
    if (r.exceptionDetails) {
      throw new Error('页面内异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 400));
    }
    return r.result.value;
  }

  close() { try { this.ws.close(); } catch (_) {} }
}

/**
 * 认 pet 窗不能靠 url 或标题：pet 窗就是 `http://localhost:48911/`，
 * 标题是 N.E.K.O 的页面标题，和 chat 窗只差路径。唯一可靠判据是「页面里有没有模型管理器」。
 */
const IS_PET = `!!(window.live2dManager || window.mmdManager || window.vrmManager || window.avatarPortrait || window.DragHelpers)`;

async function pickPet(targets) {
  const pages = targets.filter((t) => t.type === 'page');
  const hits = [];
  for (const t of pages) {
    let cdp;
    try {
      cdp = new Cdp(t.webSocketDebuggerUrl);
      await cdp.ready;
      if (await cdp.eval(IS_PET)) hits.push(t);
    } catch (_) { /* 连不上就跳过 */ } finally { if (cdp) cdp.close(); }
  }
  if (!hits.length) return null;
  return hits[0];
}

/** 模型包围盒（视口 CSS px）——拖拽起点得从盒子里挑，不能只取中心。 */
const CENTER = `(() => {
  const pick = (label, fn) => { try { const b = fn(); if (b && isFinite(b.left)) return { modelType: label, rect: [b.left, b.top, b.right, b.bottom] }; } catch (e) {} return null; };
  const hit = pick('live2d', () => window.live2dManager && window.live2dManager.getModelScreenBounds())
    || pick('mmd', () => window.mmdManager && window.mmdManager.getModelScreenBounds())
    || pick('vrm', () => window.vrmManager && window.vrmManager.getModelScreenBounds());
  const out = hit ? { modelType: hit.modelType, rect: hit.rect, source: 'getModelScreenBounds' }
    : { modelType: null, rect: [0, 0, innerWidth, innerHeight], source: 'viewport(fallback)' };
  const [l, t, r, b] = out.rect;
  out.center = [ (l + r) / 2, (t + b) / 2 ];
  out.viewport = [innerWidth, innerHeight];
  return out;
})()`;

/** 可观测状态指纹：位置 + 拖拽态。 */
const STATE = `(() => {
  const out = {};
  const safe = (k, fn) => { try { out[k] = fn(); } catch (e) { out[k] = 'err:' + (e && e.message); } };
  safe('draggingHelpers', () => (window.DragHelpers ? Boolean(window.DragHelpers.isDragging) : null));
  safe('live2dDraggingFlag', () => (window.live2dManager ? Boolean(window.live2dManager._isDraggingModel) : null));
  safe('live2dPos', () => {
    const m = window.live2dManager && window.live2dManager.getCurrentModel && window.live2dManager.getCurrentModel();
    return m ? { x: m.x, y: m.y } : null;
  });
  safe('vrmDragging', () => (window.vrmManager && window.vrmManager.interaction ? Boolean(window.vrmManager.interaction.isDragging) : null));
  safe('mmdDragging', () => (window.mmdManager && window.mmdManager.interaction ? Boolean(window.mmdManager.interaction.isDragging) : null));
  return out;
})()`;

/** 复位模型位置：优先页面全局 resetToDefaultModel，其次 live2dManager.resetModelPosition。 */
const RESET = `(() => {
  const tried = [];
  try { if (typeof window.resetToDefaultModel === 'function') { window.resetToDefaultModel(); tried.push('resetToDefaultModel'); } } catch (e) {}
  try {
    for (const [k, m] of [['live2d', window.live2dManager], ['vrm', window.vrmManager], ['mmd', window.mmdManager]]) {
      if (m && typeof m.resetModelPosition === 'function') { m.resetModelPosition(); tried.push(k + '.resetModelPosition'); }
    }
  } catch (e) {}
  return tried;
})()`;

const DIAG = `(() => {
  const out = { hasDiagnostics: !!window.nekoPetDiagnostics };
  try { if (out.hasDiagnostics) out.snapshot = window.nekoPetDiagnostics.snapshot(); } catch (e) { out.error = String(e && e.message); }
  return out;
})()`;

const ENV = `(() => {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
  return {
    webgl: !!gl,
    modelLoaded: !!(window.live2dManager && window.live2dManager.getCurrentModel && window.live2dManager.getCurrentModel()),
    modelType: (window.nekoPetDiagnostics ? undefined : undefined) || (
      window.live2dManager && window.live2dManager.getCurrentModel ? 'live2d'
      : window.vrmManager && window.vrmManager.currentModel ? 'vrm'
      : window.mmdManager && window.mmdManager.currentModel ? 'mmd' : null),
  };
})()`;

async function withPet(fn) {
  const targets = await listTargets();
  const pet = await pickPet(targets);
  if (!pet) throw new Error('找不到 pet 窗（页面里没有任何模型管理器）。当前 targets: ' + targets.map((t) => t.url).join(', '));
  const cdp = new Cdp(pet.webSocketDebuggerUrl);
  await cdp.ready;
  try {
    await cdp.send('Runtime.enable');
    return await fn(cdp, pet);
  } finally { cdp.close(); }
}

/** 拖拽是否已"抓住"：任一拖拽标志被置位即算。 */
function isGripped(state) {
  return state.live2dDraggingFlag === true || state.draggingHelpers === true
    || state.vrmDragging === true || state.mmdDragging === true;
}

/**
 * 在包围盒里枚举候选抓取点。
 * Live2D 模型有大量透明边缘，"包围盒正中"很可能落在透明像素上 —— 那时鼠标事件
 * 根本不进拖拽逻辑，位移恒为 0。这是**假阴性**（把好代码判成坏的），
 * 所以必须用"抓住"标志确认，而不是指望第一个点就中。
 */
function gripCandidates(rect, viewport) {
  const [l, t, r, b] = rect;
  const [vw, vh] = viewport;
  const w = r - l, h = b - t;
  const fracs = [[0.5, 0.5], [0.5, 0.42], [0.5, 0.58], [0.42, 0.5], [0.58, 0.5], [0.5, 0.3], [0.5, 0.7]];
  const out = [];
  for (const [fx, fy] of fracs) {
    const x = Math.round(l + w * fx), y = Math.round(t + h * fy);
    if (x > 0 && y > 0 && x < vw && y < vh) out.push([x, y]);
  }
  return out;
}

async function doDrag(cdp, dx, dy) {
  const before = await cdp.eval(STATE);
  const { rect, modelType, source, viewport } = await cdp.eval(CENTER);
  const [vw, vh] = viewport || [Infinity, Infinity];

  const tried = [];
  let start = null;
  for (const [x, y] of gripCandidates(rect, viewport)) {
    tried.push([x, y]);
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0 });
    await sleep(50);
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
    await sleep(80);
    if (isGripped(await cdp.eval(STATE))) { start = [x, y]; break; }
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
    await sleep(60);
  }

  if (!start) {
    throw new Error(`试了 ${tried.length} 个候选点都没抓住模型（包围盒 ${rect.map((n) => Math.round(n)).join(',')}，`
      + `视口 ${vw}×${vh}）—— 模型可能整体在屏幕外，或不在可拖状态`);
  }
  const [x0, y0] = start;

  const STEPS = 16;
  for (let i = 1; i <= STEPS; i++) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x: x0 + (dx * i) / STEPS, y: y0 + (dy * i) / STEPS, button: 'left', buttons: 1,
    });
    await sleep(16);
  }
  await sleep(80);
  const during = await cdp.eval(STATE);
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x0 + dx, y: y0 + dy, button: 'left', buttons: 0, clickCount: 1 });
  await sleep(250);
  const after = await cdp.eval(STATE);

  return { modelType, source, grip: start, gripCandidatesTried: tried.length, rect, from: start, delta: [dx, dy], before, during, after };
}

function posDelta(before, after) {
  const a = before.live2dPos, b = after.live2dPos;
  if (!a || !b || typeof a.x !== 'number' || typeof b.x !== 'number') return null;
  return { dx: b.x - a.x, dy: b.y - a.y };
}

const TOL = 2; // CSS px 容差（pixelRatio 与取整）

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  if (!cmd || cmd === 'help' || cmd === '--help') {
    console.log(`
pet 窗活体验证（需 electron 带 --remote-debugging-port=9222）

  list              列出 CDP targets
  probe             模型态 + 诊断快照
  drag <dx> <dy>    模拟拖拽，打印 before/during/after
  verify            断言式验证（失败退出码 1）
  eval "<js>"       在 pet 窗求值

⚠️ electron 启动时不要带 --disable-gpu / --disable-software-rasterizer，否则 WebGL 被掐、模型加载不出来。
`);
    return 0;
  }

  const targets = await listTargets();
  if (cmd === 'list') {
    targets.forEach((t) => console.log(`${String(t.type).padEnd(10)} ${(t.title || '').slice(0, 38).padEnd(40)} ${t.url.slice(0, 88)}`));
    return 0;
  }

  return withPet(async (cdp, pet) => {
    if (cmd === 'eval') {
      const v = await cdp.eval(rest.join(' '));
      console.log(JSON.stringify(v, null, 2));
      return 0;
    }

    if (cmd === 'probe') {
      const env = await cdp.eval(ENV);
      const center = await cdp.eval(CENTER);
      const state = await cdp.eval(STATE);
      const diag = await cdp.eval(DIAG);
      console.log(JSON.stringify({ url: pet.url, env, center, state, diag }, null, 2));
      return 0;
    }

    if (cmd === 'drag') {
      const r = await doDrag(cdp, Number(rest[0] || 160), Number(rest[1] || 90));
      const d = posDelta(r.before, r.after);
      console.log(JSON.stringify({ ...r, observedDelta: d }, null, 2));
      return 0;
    }

    if (cmd === 'verify') {
      const env = await cdp.eval(ENV);
      const diag = await cdp.eval(DIAG);
      const problems = [];

      if (!env?.webgl) problems.push('WebGL 不可用 —— electron 大概率带了 --disable-gpu（模型不会加载）');
      if (!env?.modelLoaded) problems.push('模型未加载（currentModel 为空）—— 拖拽无从验证');
      if (!diag?.hasDiagnostics) problems.push('页面没有 nekoPetDiagnostics —— preload 的诊断层没挂上');

      let drag = null;
      let resetTried = [];
      if (!problems.length) {
        // 先复位：上一次验证会把模型拖出视口，不复位的话起点在窗外，位移必然是 0
        resetTried = await cdp.eval(RESET);
        // 复位会重建模型（resetToDefaultModel 是异步的），期间 canvas 不可命中：
        // 只等 450ms 时实测位移恒为 0，会被误判成「拖拽坏了」。等到中心连续两次读数一致。
        for (let i = 0; i < 15; i++) {
          await sleep(200);
          const a = await cdp.eval(CENTER);
          await sleep(120);
          const b = await cdp.eval(CENTER);
          const same = JSON.stringify(a.center) === JSON.stringify(b.center);
          const [cx, cy] = b.center;
          if (same && cx > 0 && cy > 0 && cx < b.viewport[0] && cy < b.viewport[1]) break;
        }
        try {
          drag = await doDrag(cdp, 120, 60);
        } catch (e) {
          problems.push(e.message);
        }
      }
      if (drag) {
        const d = posDelta(drag.before, drag.after);
        if (!d) problems.push('读不到模型坐标，无法判定位移');
        else {
          if (Math.abs(d.dx - 120) > TOL) problems.push(`水平位移 ${d.dx.toFixed(1)} 与输入 120 偏差 >${TOL}px`);
          if (Math.abs(d.dy - 60) > TOL) problems.push(`垂直位移 ${d.dy.toFixed(1)} 与输入 60 偏差 >${TOL}px`);
        }
        const draggingSeen = drag.during.live2dDraggingFlag === true
          || drag.during.draggingHelpers === true
          || drag.during.vrmDragging === true
          || drag.during.mmdDragging === true;
        if (!draggingSeen) problems.push('拖拽过程中没有任何「正在拖拽」标志被置位（drag 态没传下去）');
        const stillDragging = drag.after.live2dDraggingFlag === true || drag.after.draggingHelpers === true;
        if (stillDragging) problems.push('松手后拖拽标志仍为 true（卡在拖拽态）');
      }

      console.log(JSON.stringify({
        url: pet.url,
        resetTried,
        env,
        diagnostics: diag?.snapshot
          ? { isolated: diag.snapshot.isolated, hostRegistered: diag.snapshot.hostRegistered, misses: diag.snapshot.misses }
          : null,
        drag: drag ? { delta: drag.delta, grip: drag.grip, gripCandidatesTried: drag.gripCandidatesTried, observedDelta: posDelta(drag.before, drag.after), during: drag.during, after: drag.after } : null,
        problems,
        verdict: problems.length ? 'FAIL' : 'PASS',
      }, null, 2));
      return problems.length ? 1 : 0;
    }

    console.error('未知命令: ' + cmd);
    return 1;
  });
}

main().then((code) => process.exit(code || 0)).catch((e) => {
  console.error('失败:', e.message);
  process.exit(1);
});
