/**
 * pet-host-bridge.js 的单测（纯 node，不需要 Electron）
 *
 * 被测文件是浏览器脚本（IIFE + window），这里用 vm 造一个假 window 跑它，
 * 然后直接调用它注册给 preload 的 getter，验证**每个名字返回什么**。
 * 这能覆盖「值 vs 函数」「DragHelpers 拆分」「未知名返回 undefined」三条契约。
 */
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const SRC = path.resolve(__dirname, '..', '..',
  'NEKO', 'N.E.K.O', 'static', 'app', 'pet-host-bridge.js');

function loadBridge() {
  const source = fs.readFileSync(SRC, 'utf8');
  let registered = null;
  const win = {
    nekoPetHost: {
      register(fn) { registered = fn; return true; },
    },
    lanlan_config: { model_type: 'vrm', scale: 2 },
    appState: { ready: true },
    pageConfigReady: true,
    nekoSubtitleShared: { on: true },
    appButtons: { close: true },
    _agentTaskMap: { task1: 'running' },
    master_name: '主人',
    master_profile_name: '主人P',
    master_nickname: '昵称',
    master_display_name: '显示名',
    t: (k) => 'T:' + k,
    safeT: (k) => 'S:' + k,
    captureProactiveChatScreenshot: async () => ({ dataUrl: 'x' }),
    captureScreenshotDataUrl: async () => 'y',
    resetToDefaultModel: async () => 'z',
    subtitleBridge: { push() {} },
    DragHelpers: {
      isDragging: true,
      restoreButtonPointerEvents() { win.__restored = true; },
    },
  };
  const ctx = vm.createContext({
    window: win,
    console: { log() {}, warn() {} },
  });
  vm.runInContext(source, ctx);
  assert.ok(registered, 'pet-host-bridge 必须调用 nekoPetHost.register()');
  return { get: registered, win };
}

test('注册面是一个函数（preload 逐次调用取值，不是快照）', () => {
  const { get } = loadBridge();
  assert.strictEqual(typeof get, 'function');
});

test('数据类：每次取值拿到当前值（改页面全局后立刻反映）', () => {
  const { get, win } = loadBridge();
  assert.strictEqual(get('lanlan_config').model_type, 'vrm');
  win.lanlan_config = { model_type: 'mmd' };
  assert.strictEqual(get('lanlan_config').model_type, 'mmd', '必须是惰性取值，不能是注册时的快照');
  assert.strictEqual(get('pageConfigReady'), true);
  assert.strictEqual(get('master_name'), '主人');
});

test('函数类：返回函数本身，调用后能拿到页面侧结果', () => {
  const { get } = loadBridge();
  const t = get('t');
  assert.strictEqual(typeof t, 'function');
  assert.strictEqual(t('k'), 'T:k');
  assert.strictEqual(typeof get('captureProactiveChatScreenshot'), 'function');
});

test('DragHelpers 拆成两个入口：值是值、函数是函数', () => {
  const { get, win } = loadBridge();
  assert.strictEqual(get('DragHelpers.isDragging'), true);
  win.DragHelpers.isDragging = false;
  assert.strictEqual(get('DragHelpers.isDragging'), false, 'isDragging 也必须是惰性取值');

  const restore = get('DragHelpers.restoreButtonPointerEvents');
  assert.strictEqual(typeof restore, 'function', '必须返回函数本身（过桥后成为可调用代理）');
  restore();
  assert.strictEqual(win.__restored, true, '调用后页面侧副作用要真的发生');
});

test('DragHelpers 不存在时返回 undefined（不抛错）', () => {
  const { get, win } = loadBridge();
  delete win.DragHelpers;
  assert.strictEqual(get('DragHelpers.isDragging'), undefined);
  assert.strictEqual(get('DragHelpers.restoreButtonPointerEvents'), undefined);
});

test('未知名字返回 undefined（preload 侧据此记 miss）', () => {
  const { get } = loadBridge();
  assert.strictEqual(get('mmdManager'), undefined, '实例类不在注册面里（P2 才做）');
  assert.strictEqual(get('不存在的东西'), undefined);
});

test('模型态（域 A）：类型探测 / 拖拽读 / 拖拽复位', () => {
  const { get, win } = loadBridge();

  // 类型探测：按实例兜底
  assert.strictEqual(get('modelType'), undefined, '没有任何 manager 时应返回 undefined');
  win.mmdManager = { currentModel: {} };
  assert.strictEqual(get('modelType'), 'mmd');
  delete win.mmdManager;
  win.vrmManager = { currentModel: {}, interaction: { isDragging: true } };
  assert.strictEqual(get('modelType'), 'vrm');

  // 拖拽读：按模型类型分入口，且是惰性（改了就变）
  assert.strictEqual(get('modelDragging:vrm'), true);
  win.vrmManager.interaction.isDragging = false;
  assert.strictEqual(get('modelDragging:vrm'), false);

  // 拖拽复位：三个 manager 都要被清，且 live2d 还要清 model.dragging
  // 注意：getCurrentModel 必须返回**同一个**对象，否则每次调用都是新对象，
  // 断言「model.dragging 被清掉」会永远假通过。
  const live2dModel = { dragging: true };
  win.live2dManager = {
    _isDraggingModel: true,
    getCurrentModel: () => live2dModel,
  };
  win.vrmManager.interaction.isDragging = true;
  win.mmdManager = { interaction: { isDragging: true } };
  // clearModelDragging 是「动作型」能力：取一次就执行，返回值是执行结果（boolean）
  const cleared = get('clearModelDragging');
  assert.strictEqual(cleared, true);
  assert.strictEqual(win.live2dManager._isDraggingModel, false);
  assert.strictEqual(live2dModel.dragging, false, 'live2d 的 model.dragging 也要清');
  assert.strictEqual(win.vrmManager.interaction.isDragging, false);
  assert.strictEqual(win.mmdManager.interaction.isDragging, false);
});
