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
 *   - **实例不整体注册**：mmdManager / vrmManager / live2dManager / Jukebox / avatarPortrait
 *     过桥会丢原型方法，必须按成员拆成函数。P2-A 拆了模型态（域 A），
 *     P2-E 拆了点歌台（域 E，见文件末尾 `Jukebox.*`）。
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

  // ---- 域 B 用到的纯数字矩形快照 ----
  // 为什么必须自己归一化：原始的 bounds 常是类实例（PIXI Bounds / THREE 的包围盒），
  // 过桥会被结构化克隆，原型上的 getter 全丢 ⇒ preload 拿到的是个空对象。
  // 所以这里就地摊平成纯数字，并把 left/right/top/bottom 与 x/y/width/height **都给全**
  // —— preload 侧两个调用点用的归一化函数不同（一个读 left/right，一个读 x/y/width），
  // 给全了才能共用同一份快照而结果不变。
  function numOrNull(v) {
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  function rectOf(raw) {
    if (!raw || typeof raw !== 'object') return null;
    var left = numOrNull(raw.left);
    if (left === null) left = numOrNull(raw.x);
    if (left === null) left = numOrNull(raw.minX);
    var top = numOrNull(raw.top);
    if (top === null) top = numOrNull(raw.y);
    if (top === null) top = numOrNull(raw.minY);
    var right = numOrNull(raw.right);
    if (right === null) right = numOrNull(raw.maxX);
    var bottom = numOrNull(raw.bottom);
    if (bottom === null) bottom = numOrNull(raw.maxY);
    var width = numOrNull(raw.width);
    var height = numOrNull(raw.height);

    if (right === null && left !== null && width !== null) right = left + width;
    if (bottom === null && top !== null && height !== null) bottom = top + height;
    if (left === null && right !== null && width !== null) left = right - width;
    if (top === null && bottom !== null && height !== null) top = bottom - height;
    if (left === null || top === null || right === null || bottom === null) return null;
    if (!(right > left) || !(bottom > top)) return null;

    var centerX = numOrNull(raw.centerX);
    var centerY = numOrNull(raw.centerY);
    return {
      // 边读法（normalizeDesktopAvatarBounds / interaction 缓存）
      left: left, top: top, right: right, bottom: bottom,
      // 角点读法（normalizeShapeLocalBoundsToRect 优先读 x/y；live2d 的 getBounds 也只给这套）
      x: left, y: top,
      width: right - left, height: bottom - top,
      centerX: centerX === null ? (left + right) / 2 : centerX,
      centerY: centerY === null ? (top + bottom) / 2 : centerY,
    };
  }

  /** 读 interaction 缓存里的屏幕框（先刷缓存，与 preload 原来的顺序一致）。 */
  function interactionRect(I) {
    if (!I) return null;
    try {
      if (typeof I.updateModelBoundsCache === 'function') I.updateModelBoundsCache();
      else if (typeof I.updateScreenBounds === 'function') I.updateScreenBounds();
    } catch (_) { /* 刷不动就用旧缓存 */ }
    var sb = I._cachedScreenBounds;
    if (!sb) return null;
    return rectOf({ left: sb.minX, right: sb.maxX, top: sb.minY, bottom: sb.maxY });
  }

  /**
   * 管理器包围盒：先问 getModelScreenBounds，拿不到再退到 interaction 缓存。
   * mmd / vrm 要求 currentModel 在场（没有模型就没有框）；
   * live2d 没有 getModelScreenBounds 时退到 getCurrentModel().getBounds()。
   */
  function boundsOf(kind) {
    var M = kind === 'mmd' ? window.mmdManager
      : kind === 'vrm' ? window.vrmManager
      : window.live2dManager;
    if (!M) return undefined;
    if (kind !== 'live2d' && !M.currentModel) return undefined;

    var rect = null;
    if (typeof M.getModelScreenBounds === 'function') {
      try { rect = rectOf(M.getModelScreenBounds()); } catch (_) { rect = null; }
    }
    if (rect) return rect;

    if (kind === 'live2d') {
      // ⚠️ 与迁移前的一处细微差异：原来 getDesktopAvatarBoundsEntries 在
      // `getModelScreenBounds` 存在但返回空时**不**回退（else-if），
      // 而 getModelRect 会回退。这里统一成「回退」，两处共用一份实现。
      try {
        var model = typeof M.getCurrentModel === 'function' ? M.getCurrentModel() : null;
        return model && typeof model.getBounds === 'function' ? rectOf(model.getBounds()) : null;
      } catch (_) {
        return null;
      }
    }
    return interactionRect(M.interaction);
  }

  function managerOf(kind) {
    return kind === 'mmd' ? window.mmdManager
      : kind === 'vrm' ? window.vrmManager
      : window.live2dManager;
  }

  /**
   * 管理器在不在、有没有当前模型。
   * 返回 null 表示「管理器不在」—— 调用方要能区分它和「在但没模型」之外的情况，
   * 所以不折叠成 false。
   */
  function managerPresent(kind) {
    var M = managerOf(kind);
    if (!M) return null;
    if (kind === 'live2d') return true;
    return Boolean(M.currentModel);
  }

  /** 锁定态：先看 manager.isLocked，再看 interaction.isLocked（与迁移前同序）。 */
  function managerLocked(kind) {
    var M = managerOf(kind);
    if (!M) return null;
    if (typeof M.isLocked !== 'undefined') return Boolean(M.isLocked);
    if (M.interaction && typeof M.interaction.isLocked !== 'undefined') return Boolean(M.interaction.isLocked);
    return false;
  }

  function managerGoodbye(kind) {
    var M = managerOf(kind);
    return M ? Boolean(M._goodbyeClicked) : null;
  }

  /** interaction 的屏幕框点击区域（hit test 用），先按需刷缓存。 */
  function screenBoundsOf(kind) {
    var M = managerOf(kind);
    if (!M || (kind !== 'live2d' && !M.currentModel)) return undefined;
    var I = M.interaction;
    if (!I) return undefined;
    return function (force) {
      try {
        if (force || !I._cachedScreenBounds) {
          if (typeof I.updateModelBoundsCache === 'function') I.updateModelBoundsCache();
          else if (typeof I.updateScreenBounds === 'function') I.updateScreenBounds();
        }
      } catch (_) { /* 刷不动就用旧缓存 */ }
      var sb = I._cachedScreenBounds;
      if (!sb) return null;
      return { minX: Number(sb.minX), minY: Number(sb.minY), maxX: Number(sb.maxX), maxY: Number(sb.maxY) };
    };
  }

  /** interaction 的精确命中（穿透明细区域用）。 */
  function preciseHitOf(kind) {
    var M = managerOf(kind);
    if (!M || !M.currentModel) return undefined;
    var I = M.interaction;
    if (!I || typeof I._hitTestModel !== 'function') return undefined;
    return function (x, y) {
      try { return Boolean(I._hitTestModel(x, y)); } catch (_) { return false; }
    };
  }

  /** live2d 模型的本地包围盒（canvas 原点 = 视口原点，可直接当窗口坐标用）。 */
  function live2dModelBounds() {
    var M = window.live2dManager;
    if (!M || typeof M.getCurrentModel !== 'function') return null;
    var model = M.getCurrentModel();
    if (!model || typeof model.getBounds !== 'function') return null;
    try { return rectOf(model.getBounds()); } catch (_) { return null; }
  }

  /** live2d 的 hitTest（命中区域名数组）。命中逻辑留在 preload，这里只交数据。 */
  function live2dHitAreas(x, y) {
    var M = window.live2dManager;
    if (!M || typeof M.getCurrentModel !== 'function') return null;
    var model = M.getCurrentModel();
    if (!model || typeof model.hitTest !== 'function') return null;
    try {
      var areas = model.hitTest(x, y);
      return areas && typeof areas.length === 'number' ? Array.prototype.slice.call(areas) : null;
    } catch (_) { return null; }
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
    // ---- 域 C：渲染控制 / 复位（三个管理器同名成员）----
    // ⚠️ 键名顺序 = `model:<kind>:<op>`，必须与 preload 的拼法逐字一致；
    //    写反成 `model:<op>:<kind>` 时两边「各自都有那个键」，静态检查抓不到，
    //    只有双端联跑测试能发现（本轮就是这么抓到的）。
    // 方法一律回闭包：裸传 `M.pauseRendering` 过桥会丢 this。
    // 能力不存在时返回 undefined（preload 侧据此当"没有"，与原 typeof 检查等价）。
    'model:mmd:pauseRendering': function () {
      var M = window.mmdManager;
      if (!M || typeof M.pauseRendering !== 'function') return undefined;
      return function () { return M.pauseRendering(); };
    },
    'model:vrm:pauseRendering': function () {
      var M = window.vrmManager;
      if (!M || typeof M.pauseRendering !== 'function') return undefined;
      return function () { return M.pauseRendering(); };
    },
    'model:live2d:pauseRendering': function () {
      var M = window.live2dManager;
      if (!M || typeof M.pauseRendering !== 'function') return undefined;
      return function () { return M.pauseRendering(); };
    },
    'model:mmd:resumeRendering': function () {
      var M = window.mmdManager;
      if (!M || typeof M.resumeRendering !== 'function') return undefined;
      return function () { return M.resumeRendering(); };
    },
    'model:vrm:resumeRendering': function () {
      var M = window.vrmManager;
      if (!M || typeof M.resumeRendering !== 'function') return undefined;
      return function () { return M.resumeRendering(); };
    },
    'model:live2d:resumeRendering': function () {
      var M = window.live2dManager;
      if (!M || typeof M.resumeRendering !== 'function') return undefined;
      return function () { return M.resumeRendering(); };
    },
    'model:mmd:resetModelPosition': function () {
      var M = window.mmdManager;
      if (!M || typeof M.resetModelPosition !== 'function') return undefined;
      return function () { return M.resetModelPosition(); };
    },
    'model:vrm:resetModelPosition': function () {
      var M = window.vrmManager;
      if (!M || typeof M.resetModelPosition !== 'function') return undefined;
      return function () { return M.resetModelPosition(); };
    },
    'model:live2d:resetModelPosition': function () {
      var M = window.live2dManager;
      if (!M || typeof M.resetModelPosition !== 'function') return undefined;
      return function () { return M.resetModelPosition(); };
    },
    // ---- 域 B：测量（模型包围盒，2026-10-30 迁移）----
    // 返回纯数字矩形快照；undefined = 页面没有这个能力，null = 有管理器但当前量不到框。
    // preload 侧 `petModelBounds()` 只做真值判断，两者都当「没有」。
    'bounds:mmd': function () { return boundsOf('mmd'); },
    'bounds:vrm': function () { return boundsOf('vrm'); },
    'bounds:live2d': function () { return boundsOf('live2d'); },

    // ---- 域 D：视线跟随（2026-10-30 迁移）----
    // 两个跟随器的回调名**不对称**（vrm 是下划线私有 `_cursorFollow._onPointerMove`，
    // mmd 是 `cursorFollow._pointerMoveHandler`），照抄不得。
    // 回闭包而不是回回调本身：过桥后 this 会丢，闭包在页面世界内执行。
    'gaze:vrm': function () {
      var F = window.vrmManager && window.vrmManager._cursorFollow;
      if (!F || typeof F._onPointerMove !== 'function') return undefined;
      return function (x, y) {
        F._onPointerMove({ type: 'pointermove', clientX: x, clientY: y });
        return true;
      };
    },
    'gaze:mmd': function () {
      var F = window.mmdManager && window.mmdManager.cursorFollow;
      if (!F || typeof F._pointerMoveHandler !== 'function') return undefined;
      return function (x, y) {
        F._pointerMoveHandler({ type: 'pointermove', clientX: x, clientY: y });
        return true;
      };
    },
    // ---- 域 F：穿透判定（interaction / currentModel / getCurrentModel，2026-10-30 迁移）----
    // 这批直接决定「鼠标落在窗口上算不算点中模型」，也是迁移风险最高的一批，
    // 所以每一项都只交**数据**（布尔/数字/数组），几何判断留在 preload 里可单测。
    'modelLocked': function () {
      return { mmd: managerLocked('mmd'), vrm: managerLocked('vrm'), live2d: managerLocked('live2d') };
    },
    'modelGoodbye': function () {
      return { mmd: managerGoodbye('mmd'), vrm: managerGoodbye('vrm'), live2d: managerGoodbye('live2d') };
    },
    'present:mmd': function () { return managerPresent('mmd'); },
    'present:vrm': function () { return managerPresent('vrm'); },
    'screenBounds:mmd': function () { return screenBoundsOf('mmd'); },
    'screenBounds:vrm': function () { return screenBoundsOf('vrm'); },
    'hit:mmd': function () { return preciseHitOf('mmd'); },
    'hit:vrm': function () { return preciseHitOf('vrm'); },
    'localBounds:live2d': function () { return live2dModelBounds(); },
    'hitAreas:live2d': function () {
      // 只在模型真的有 hitTest 时才回闭包；否则 undefined = 能力缺失，
      // preload 会退回椭圆近似（与迁移前 `typeof model.hitTest === 'function'` 等价）。
      var M = window.live2dManager;
      var model = M && typeof M.getCurrentModel === 'function' ? M.getCurrentModel() : null;
      if (!model || typeof model.hitTest !== 'function') return undefined;
      return function (x, y) { return live2dHitAreas(x, y); };
    },
    // ---- 截图域：头像捕获 ----
    // avatarPortrait 是实例，裸传方法过桥会丢 this；闭包在页面世界内执行。
    'avatarPortrait.capture': function () {
      var A = window.avatarPortrait;
      if (!A || typeof A.capture !== 'function') return undefined;
      return function (options) { return A.capture(options); };
    },
    // ---- 域 E：点歌台（Jukebox）----
    // 方法一律返回**闭包**而不是 `J.playVMD` 本身：裸传函数引用过桥后 this 会丢，
    // 闭包在页面世界内执行，this 仍指向 Jukebox。
    'Jukebox.present': function () {
      return window.Jukebox ? true : undefined;
    },
    'Jukebox.getModelType': function () {
      var J = window.Jukebox;
      if (!J || typeof J.getModelType !== 'function') return undefined;
      return function () { return J.getModelType(); };
    },
    'Jukebox.state': function () {
      var S = window.Jukebox && window.Jukebox.State;
      if (!S) return undefined;
      // 只回布尔快照：对象过桥会被克隆，直接回 State 反而容易读到陈旧值
      return { isVMDPlaying: Boolean(S.isVMDPlaying), isPaused: Boolean(S.isPaused) };
    },
    'Jukebox.playVRMA': function () {
      var J = window.Jukebox;
      if (!J || typeof J.playVRMA !== 'function') return undefined;
      return function (path) { return J.playVRMA(path); };
    },
    'Jukebox.playVMD': function () {
      var J = window.Jukebox;
      if (!J || typeof J.playVMD !== 'function') return undefined;
      return function (path) { return J.playVMD(path); };
    },
    'Jukebox.stopVMD': function () {
      var J = window.Jukebox;
      if (!J || typeof J.stopVMD !== 'function') return undefined;
      return function (skipIdleRestore) { return J.stopVMD(skipIdleRestore); };
    },
    'Jukebox.togglePause': function () {
      var J = window.Jukebox;
      if (!J || typeof J.togglePause !== 'function') return undefined;
      return function () { return J.togglePause(); };
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
