/**
 * pet-host-bridge.js —— Pet 窗给 preload 的注册面（WO-278 P1）
 *
 * 背景：`contextIsolation: true` 之后，preload 读不到页面的 JS 全局
 * （`window.lanlan_config` / `window.t` / `window.DragHelpers` …）。
 * 但 contextBridge 是**双向**的：页面可以把一个 getter 交给 preload，
 * preload 每次调用它就能拿到**当前**的值。
 *
 * 约定：
 *   - preload 侧 `pageApi(name)` 在隔离时会调 `host(name)`；
 *   - 返回 `undefined` 表示"页面没有这个能力"（preload 会记一次 miss）；
 *   - **实例**（mmdManager / vrmManager / live2dManager / Jukebox / avatarPortrait）**不在这里注册**：
 *     对象过桥会丢原型方法，必须按成员拆成函数（P2）。
 *
 * 加载顺序：本文件必须在 `index.html` 里尽早加载（getter 内是惰性取值，
 * 注册时被取用的对象还不存在也没关系）。
 */
(function () {
  'use strict';

  var host = window.nekoPetHost;
  if (!host || typeof host.register !== 'function') {
    // 非 Electron 环境（浏览器直开）或旧 preload：什么都不用做
    return;
  }

  // 每个名字一个惰性取值函数：preload 调用时**才**去读，保证拿到最新值
  var GETTERS = {
    // ---- 数据 / 配置 ----
    lanlan_config: function () { return window.lanlan_config; },
    appState: function () { return window.appState; },
    pageConfigReady: function () { return window.pageConfigReady; },
    nekoSubtitleShared: function () { return window.nekoSubtitleShared; },
    appButtons: function () { return window.appButtons; },
    _agentTaskMap: function () { return window._agentTaskMap; },
    master_name: function () { return window.master_name; },
    master_profile_name: function () { return window.master_profile_name; },
    master_nickname: function () { return window.master_nickname; },
    master_display_name: function () { return window.master_display_name; },

    // ---- 函数 / 工具 ----
    t: function () { return window.t; },
    safeT: function () { return window.safeT; },
    captureProactiveChatScreenshot: function () { return window.captureProactiveChatScreenshot; },
    captureScreenshotDataUrl: function () { return window.captureScreenshotDataUrl; },
    resetToDefaultModel: function () { return window.resetToDefaultModel; },
    subtitleBridge: function () { return window.subtitleBridge; },

    // ---- 模型态（域 A）----
    // 实例不能整体过桥，所以只把「用得到的判断/复位」做成函数。
    modelType: function () {
      if (window.mmdManager && window.mmdManager.currentModel) return 'mmd';
      if (window.vrmManager && window.vrmManager.currentModel) return 'vrm';
      return undefined;
    },
    'modelDragging:live2d': function () {
      return Boolean(window.live2dManager && window.live2dManager._isDraggingModel);
    },
    'modelDragging:vrm': function () {
      return Boolean(window.vrmManager && window.vrmManager.interaction
        && window.vrmManager.interaction.isDragging);
    },
    'modelDragging:mmd': function () {
      return Boolean(window.mmdManager && window.mmdManager.interaction
        && window.mmdManager.interaction.isDragging);
    },
    // 动作型：preload 侧取一次就执行（pageApi 的取值本身就是调用），
    // 返回值表示是否清到了任何 manager。
    clearModelDragging: function () {
      var touched = false;
      if (window.live2dManager) {
        window.live2dManager._isDraggingModel = false;
        var model = window.live2dManager.getCurrentModel && window.live2dManager.getCurrentModel();
        if (model) model.dragging = false;
        touched = true;
      }
      if (window.vrmManager && window.vrmManager.interaction) {
        window.vrmManager.interaction.isDragging = false;
        touched = true;
      }
      if (window.mmdManager && window.mmdManager.interaction) {
        window.mmdManager.interaction.isDragging = false;
        touched = true;
      }
      return touched;
    },

    // DragHelpers 是命名空间对象（一个布尔 + 若干方法）。**不能整体传**：
    // 对象过桥会被克隆，getter 与方法都会丢。所以拆成「值」和「函数」两个入口。
    'DragHelpers.isDragging': function () {
      return window.DragHelpers ? Boolean(window.DragHelpers.isDragging) : undefined;
    },
    'DragHelpers.restoreButtonPointerEvents': function () {
      var D = window.DragHelpers;
      if (!D || typeof D.restoreButtonPointerEvents !== 'function') return undefined;
      return D.restoreButtonPointerEvents;   // 返回函数本身，过桥成为可调用代理
    },
  };

  host.register(function (name) {
    var getter = GETTERS[name];
    if (typeof getter !== 'function') return undefined;
    try {
      return getter();
    } catch (err) {
      console.warn('[pet-host-bridge] 取值失败:', name, err);
      return undefined;
    }
  });

  console.log('[pet-host-bridge] 已注册', Object.keys(GETTERS).length, '项能力给 preload');
})();
