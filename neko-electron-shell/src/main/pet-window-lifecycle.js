const { applyX11InputShape } = require('./linux-x11-input-shape');
const { getWorkAreaWindowInitialBounds } = require('./window-bounds-utils');

const MANAGER_SETTINGS_POPUP_PATHS = new Set([
  '/character_card_manager',
  '/model_manager',
]);
const PLUGIN_DASHBOARD_WINDOW_NAME = 'neko_plugin_dashboard';
const PLUGIN_DASHBOARD_POPUP_PATHS = new Set([
  '/api/agent/user_plugin/dashboard',
]);

function getChildPathname(childUrl) {
  try {
    return new URL(childUrl, 'http://neko.local').pathname;
  } catch (_) {
    return '';
  }
}

function isManagerSettingsPopupUrl(childUrl) {
  return MANAGER_SETTINGS_POPUP_PATHS.has(getChildPathname(childUrl));
}

function matchesPopupPath(pathname, paths) {
  if (!pathname) return false;
  for (const path of paths) {
    if (pathname === path || pathname.startsWith(path + '/')) return true;
  }
  return false;
}

function isPluginDashboardPopup(details) {
  if (!details) return false;
  if (details.frameName === PLUGIN_DASHBOARD_WINDOW_NAME) return true;
  if (details.windowName === PLUGIN_DASHBOARD_WINDOW_NAME) return true;
  return matchesPopupPath(getChildPathname(details.url), PLUGIN_DASHBOARD_POPUP_PATHS);
}

function getWindowFeatureNumber(features, name) {
  if (!features || !name) return null;
  const pattern = new RegExp('(?:^|,)\\s*' + name + '\\s*=\\s*(-?\\d+)', 'i');
  const match = String(features).match(pattern);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function clampWindowSize(value, min, max, fallback) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function getManagerPopupInitialBounds(screen, features) {
  const fallback = { x: 80, y: 60, width: 1000, height: 800 };
  try {
    const workArea = screen.getPrimaryDisplay().workArea;
    const maxWidth = Math.max(720, workArea.width - 80);
    const maxHeight = Math.max(560, workArea.height - 80);
    const defaultWidth = Math.min(1000, maxWidth);
    const defaultHeight = Math.min(800, maxHeight);
    const width = clampWindowSize(getWindowFeatureNumber(features, 'width'), 720, maxWidth, defaultWidth);
    const height = clampWindowSize(getWindowFeatureNumber(features, 'height'), 560, maxHeight, defaultHeight);
    const requestedX = getWindowFeatureNumber(features, 'left');
    const requestedY = getWindowFeatureNumber(features, 'top');
    return {
      x: Number.isFinite(requestedX) ? requestedX : workArea.x + Math.max(0, Math.floor((workArea.width - width) / 2)),
      y: Number.isFinite(requestedY) ? requestedY : workArea.y + Math.max(0, Math.floor((workArea.height - height) / 2)),
      width,
      height,
    };
  } catch (_) {
    return fallback;
  }
}

function getOpenClawGuideInitialBounds(screen, features) {
  const fallback = { x: 80, y: 60, width: 1280, height: 900, minWidth: 760, minHeight: 560 };
  try {
    const workArea = screen.getPrimaryDisplay().workArea;
    const maxWidth = Math.max(760, workArea.width - 80);
    const maxHeight = Math.max(560, workArea.height - 80);
    const defaultWidth = Math.min(1280, maxWidth);
    const defaultHeight = Math.min(900, maxHeight);
    const width = clampWindowSize(getWindowFeatureNumber(features, 'width'), 760, maxWidth, defaultWidth);
    const height = clampWindowSize(getWindowFeatureNumber(features, 'height'), 560, maxHeight, defaultHeight);
    const requestedX = getWindowFeatureNumber(features, 'left');
    const requestedY = getWindowFeatureNumber(features, 'top');
    const maxX = workArea.x + Math.max(0, workArea.width - width);
    const maxY = workArea.y + Math.max(0, workArea.height - height);
    const centeredX = workArea.x + Math.max(0, Math.floor((workArea.width - width) / 2));
    const centeredY = workArea.y + Math.max(0, Math.floor((workArea.height - height) / 2));
    return {
      x: clampWindowSize(requestedX, workArea.x, maxX, centeredX),
      y: clampWindowSize(requestedY, workArea.y, maxY, centeredY),
      width,
      height,
      minWidth: 760,
      minHeight: 560,
    };
  } catch (_) {
    return fallback;
  }
}

function createPetWindowLifecycle(context) {
  const {
    BrowserWindow,
    _ignoreStateByWindow,
    _lastShapeByWindow,
    _lastShapeMetaByWindow,
    app,
    applyTopOn,
    bindWindowDisplayRecovery,
    boundsApproximatelyEqual,
    dialog,
    ensureMarkDirtyHooked,
    fs,
    getAppConfig,
    getChildWindowTopLevel,
    getFullscreenDisplayBounds,
    getInputRegionBackend,
    getIcon,
    getEffectiveWindowShapeRects,
    getNativeWindowShapeRects,
    getIsGlobalAlwaysOnTop,
    getIsStreamerMode,
    getLoadingWindow,
    getManagedTopLevel,
    isLinuxWaylandRuntime,
    isNormalFramedPopup,
    isWindowedToolPopup,
    isStorageMaintenanceProtectionActive,
    log,
    mainDirname,
    markZOrderDirty,
    path,
    process,
    screen,
    setMainWindow,
    setReloadPetAfterMaintenanceReady,
    shouldUseNativeIgnoreMouse,
    windowManager,
  } = context;

  let childWindowCount = 0;
  let browserWindowCreatedHookInstalled = false;

  function isLinuxXwaylandRuntime() {
    return process.platform === 'linux' &&
      !isLinuxWaylandRuntime() &&
      (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
  }

  function isLinuxX11Runtime() {
    return process.platform === 'linux' && !isLinuxWaylandRuntime();
  }

  function getWindowScaleFactor(win) {
    try {
      const display = screen.getDisplayMatching(win.getBounds());
      return display && Number.isFinite(display.scaleFactor) ? display.scaleFactor : 1;
    } catch (_) {
      return 1;
    }
  }

  function applyInitialX11PetPassthrough(petWin) {
    if (!isLinuxX11Runtime() || !petWin || petWin.isDestroyed()) return Promise.resolve(false);
    let loggedReady = false;
    let resolved = false;
    let resolveReady = null;
    const readyPromise = new Promise((resolve) => {
      resolveReady = resolve;
    });
    const apply = () => {
      if (!petWin || petWin.isDestroyed() || petWin._nekoX11InputShapeAuthorityReady) return;
      applyX11InputShape(petWin, [], {
        log,
        scaleFactor: getWindowScaleFactor(petWin),
        allowNativeFallback: !isLinuxXwaylandRuntime(),
      }).then((ok) => {
        if (ok && !loggedReady) {
          loggedReady = true;
          log('[setShape-init] X11 Pet starts with empty ShapeInput passthrough');
          if (!resolved) {
            resolved = true;
            resolveReady(true);
          }
        }
      }).catch((error) => {
        log('[setShape-init] X11 initial ShapeInput passthrough failed:', error.message || error);
      });
    };
    [0, 20, 80, 160, 320, 640, 1200, 2200, 3600].forEach((delay) => {
      setTimeout(apply, delay);
    });
    setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolveReady(false);
      }
    }, 5000);
    return readyPromise;
  }

  function reassertX11PetPassthroughAfterShow(petWin, reason, options = {}) {
    if (!isLinuxX11Runtime() || !petWin || petWin.isDestroyed()) return;
    const useNativeIgnore = options.useNativeIgnore !== false;
    if (useNativeIgnore) {
      try {
        petWin.setIgnoreMouseEvents(true, { forward: true });
        _ignoreStateByWindow.set(petWin.id, true);
        log(`[setShape-init] X11 Pet native passthrough reasserted after show (${reason || 'show'})`);
      } catch (error) {
        log('[setShape-init] X11 native passthrough reassert failed:', error && error.message ? error.message : error);
      }
    } else {
      log(`[setShape-init] X11 Pet ShapeInput passthrough reasserted after show (${reason || 'show'})`);
    }
    const applyPassthrough = () => {
      if (!petWin || petWin.isDestroyed() || petWin._nekoX11InputShapeAuthorityReady) return;
      applyX11InputShape(petWin, [], {
        log,
        scaleFactor: getWindowScaleFactor(petWin),
        allowNativeFallback: !isLinuxXwaylandRuntime(),
      }).catch((error) => {
        log('[setShape-init] X11 post-show ShapeInput passthrough failed:', error.message || error);
      });
    };
    applyPassthrough();
    [8, 16, 32, 50, 80, 120, 180, 240, 520, 900, 1600, 2600, 3800].forEach((delay) => {
      setTimeout(applyPassthrough, delay);
    });
  }

function getDisplayBounds(displayId = null) {
  const displays = screen.getAllDisplays();
  let targetDisplay;

  if (displayId !== null) {
    // 查找指定 ID 的屏幕
    targetDisplay = displays.find(d => d.id === displayId);
  }

  if (!targetDisplay) {
    // 默认使用主屏幕
    targetDisplay = screen.getPrimaryDisplay();
  }

  log('getDisplayBounds() - 目标屏幕 ID:', targetDisplay.id, '缩放:', targetDisplay.scaleFactor);
  log('getDisplayBounds() - 边界:', JSON.stringify(targetDisplay.bounds));

  return targetDisplay.bounds;
}

// 保留旧函数名以兼容，但行为改为只返回主屏幕。
// 与 getFullscreenDisplayBounds 一致：屏幕内 off-by-one，右/底贴齐 display。
function getAllDisplaysBounds() {
  return getFullscreenDisplayBounds({ bounds: getDisplayBounds(null) });
}

function schedulePetBoundsRepair(win, targetBounds) {
  if (!win || !targetBounds) return;
  const attempts = [0, 50, 500, 1500];
  for (const delay of attempts) {
    setTimeout(() => {
      if (!win || win.isDestroyed()) return;
      const before = win.getBounds();
      if (boundsApproximatelyEqual(before, targetBounds, 0)) return;
      try {
        win.setBounds(targetBounds);
      } catch (error) {
        log('[PetBoundsRepair] setBounds failed:', error && error.message ? error.message : error);
        return;
      }
      const after = win.getBounds();
      log('[PetBoundsRepair] reassert', JSON.stringify({
        delay,
        target: targetBounds,
        before,
        after,
      }));
    }, delay);
  }
}

/**
 * 设置 Pet 窗口的子窗口行为和生命周期钩子
 * 从原 createWindow 中提取的逻辑，用于多窗口模式
 */
function setupPetWindowBehavior(petWin) {
  if (!petWin) return;
  let petShowDeferredForNativePassthrough = false;
  let petShownByLifecycle = false;
  const showPetWindow = (reason) => {
    if (!petWin || petWin.isDestroyed() || petShownByLifecycle) return;
    try {
      if (!petWin.isVisible()) {
        if (isLinuxX11Runtime() && typeof petWin.showInactive === 'function') {
          petWin.showInactive();
        } else {
          petWin.show();
        }
        reassertX11PetPassthroughAfterShow(petWin, reason, {
          useNativeIgnore: reason !== 'x11-shape-input-ready',
        });
        log(`[PetWindow] show (${reason || 'ready'})`);
      }
      petShownByLifecycle = true;
    } catch (error) {
      log('[PetWindow] show failed:', error && error.message ? error.message : error);
    }
  };

  const getWaylandPetStartupPassthroughShape = () => {
    try {
      const b = petWin.getBounds();
      return [{
        x: Math.max(0, Math.round(Number(b.width) || 1) - 1),
        y: Math.max(0, Math.round(Number(b.height) || 1) - 1),
        width: 1,
        height: 1,
      }];
    } catch (_) {
      return [{ x: 0, y: 0, width: 1, height: 1 }];
    }
  };

  // Pet 窗口加载失败兜底：Pet 是 transparent:true 的全屏透明窗口，
  // loadURL 失败时页面无内容可渲染，看起来就像"窗口消失了"。
  // 这里捕获 did-fail-load 给用户可见的错误对话框，方便排查 URL 配置问题。
  try {
    petWin.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      if (!isMainFrame) return;          // 忽略子资源失败
      if (errorCode === -3) return;       // ERR_ABORTED：导航被主动替换，正常情况
      log('Pet 窗口加载失败:', errorCode, errorDescription, validatedURL);
      if (isStorageMaintenanceProtectionActive()) {
        setReloadPetAfterMaintenanceReady(true);
        log('Pet 窗口加载失败处于存储维护保护模式，暂不弹通用错误:', errorDescription, validatedURL);
        try {
          if (petWin.isMinimized()) petWin.restore();
          if (!petWin.isVisible()) petWin.show();
        } catch (e) { /* ignore */ }
        return;
      }
      try {
        dialog.showErrorBox(
          'Pet 窗口加载失败',
          `无法加载: ${validatedURL}\n错误码: ${errorCode} (${errorDescription})\n\n常见原因:\n• 该 URL 上没有 NEKO 后端在运行\n• 自定义端口改了但后端没重启（请用"重启应用"而非"重新加载"）\n• 自定义 URL 拼写错误 / 服务器未启动\n• 防火墙/代理拦截\n\n请到托盘菜单 → 端口设置 检查配置；如果只是想换后端端口，记得用"自定义端口"+"重启应用"而不是"自定义 URL"。`
        );
      } catch (e) { /* ignore */ }
    });
  } catch (e) { /* ignore */ }

  // 为任意窗口注册 window.open 拦截 + 子窗口初始化逻辑
  // 递归调用：孙窗口（如 chara_manager → model_manager）也走同样的配置
  function resolveChildPreloadPath() {
    if (app.isPackaged) {
      const asarPath = path.join(process.resourcesPath, 'app.asar', 'src', 'preload-child.js');
      if (fs.existsSync(asarPath)) return asarPath;
    }
    return path.join(mainDirname, 'preload-child.js');
  }

  function shouldAttachChildHostPreload(parentWin, childUrl) {
    try {
      const parentUrl = parentWin && !parentWin.isDestroyed()
        ? parentWin.webContents.getURL()
        : '';
      if (!parentUrl || !childUrl) return false;
      const parentOrigin = new URL(parentUrl).origin;
      const parsedChildUrl = new URL(childUrl, parentUrl);
      return (
        parsedChildUrl.origin === parentOrigin
        && (parsedChildUrl.protocol === 'http:' || parsedChildUrl.protocol === 'https:')
      );
    } catch (_) {
      return false;
    }
  }

  function setupChildWindowHandlers(parentWin) {
    // 子窗口打开行为
    // alwaysOnTop: true —— 窗口一出生就在 pet overlay 之上，避免 DWM 跳过首绘导致白屏
    // 非全屏弹窗在 did-create-window 中延迟降级
    parentWin.webContents.setWindowOpenHandler((details) => {
      log('窗口打开请求:', details.url);
      const childWebPreferences = {
        sandbox: false,
        contextIsolation: true,
        nodeIntegration: false,
        enableRemoteModule: false,
        webSecurity: true,
        allowRunningInsecureContent: false,
        backgroundThrottling: false, // 置顶子窗口不应被后台节流
      };
      if (shouldAttachChildHostPreload(parentWin, details.url)) {
        childWebPreferences.preload = resolveChildPreloadPath();
      }
      const normalFramed = isNormalFramedPopup(details.url);
      // 卡面编辑器（/card_maker）从 character_card_manager / model_manager 打开，
      // 与 jukebox/manager 同理：显式声明 opener 为 parent，建立 Win32 owner-child
      // 关系。OS 会自动维持 card_maker 永远浮在打开它的窗口（角色卡设置）之上，
      // 无需周期 reassertion。Electron 默认 parent=null，不会自动以 opener 为
      // parent → 不显式指定就会出现"卡面编辑被角色卡设置遮挡"的问题。
      // 两侧都是 transparent:false 的非透明窗口，owner-child 不触发 DWM 白屏。
      const isCardMaker = details.url.includes('/card_maker');
      const isOpenClawGuide = isWindowedToolPopup(details.url);
      const managerPopupOptions = isManagerSettingsPopupUrl(details.url)
        ? {
            ...getManagerPopupInitialBounds(screen, details.features),
            minWidth: 720,
            minHeight: 560,
          }
        : {};
      const openClawGuidePopupOptions = isOpenClawGuide
        ? getOpenClawGuideInitialBounds(screen, details.features)
        : {};
      const normalFramedPopupOptions = normalFramed
        ? getWorkAreaWindowInitialBounds(screen, parentWin)
        : {};
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          ...managerPopupOptions,
          ...openClawGuidePopupOptions,
          ...normalFramedPopupOptions,
          icon: getIcon(),
          // 全部子窗口都走 frame:false 自绘 chrome（与现有 pet / chat 视觉一致）。
          // mini-game 也保持无边框，仅在 maximize 后占工作区即可，无需标题栏。
          frame: false,
          transparent: false,
          show: (normalFramed || isOpenClawGuide) ? false : undefined,
          // mini-game 类窗口不 alwaysOnTop，让 Pet/chat 等 topmost 窗口加载完成后
          // 自然浮在它上方；其它子窗口走置顶策略避免被 Pet overlay 遮挡导致
          // DWM 跳过首绘白屏。
          alwaysOnTop: (normalFramed || isOpenClawGuide) ? false : true,
          focusable: true,
          skipTaskbar: false,
          ...(isCardMaker ? { parent: parentWin } : {}),
          webPreferences: childWebPreferences
        }
      };
    });

    // 子窗口创建后的处理
    parentWin.webContents.on('did-create-window', (childWindow, details) => {
      log('新窗口已创建:', details?.url || '');
      windowManager.installNavigationShortcutGuard(childWindow, 'Pet child', log);
      try { childWindow.setIcon(getIcon()); } catch (err) { log('设置子窗口icon失败:', err); }
      const childUrl = details?.url || '';
      if (isPluginDashboardPopup(details)) {
        childWindow._nekoKind = 'pluginDashboard';
      } else if (isManagerSettingsPopupUrl(childUrl)) {
        childWindow._nekoKind = 'settings';
      }
      const isCardMaker = childUrl.includes('/card_maker');
      const isOpenClawGuide = isWindowedToolPopup(childUrl);
      try {
        // card_maker 显式保留 owner-child 关系（owner = 打开它的角色卡设置 /
        // 模型管理窗口），由 OS 自动维持 card_maker > parent 的 Z-order；
        // 其他子窗口解除继承的父子关系，避免被父窗口最小化等行为牵连。
        if (!isCardMaker) {
          const parent = childWindow.getParentWindow();
          if (parent) childWindow.setParentWindow(null);
        }
      } catch (err) { log('解除子窗口父子关系失败:', err); }
      const normalFramed = isNormalFramedPopup(childUrl);
      // 把分类结果同步挂到窗口对象上，让 applyTopOn 在 ``browser-window-created``
      // 钩子的 ``setImmediate(firstApply)`` 阶段（URL 可能还空）也能直接读到
      // 正确分类，避免短暂被误判成普通弹窗 setAlwaysOnTop(true)。CR Major 指出。
      childWindow._nekoForceNotTopMost = normalFramed || isOpenClawGuide;
      const topLevel = getChildWindowTopLevel(childUrl);

      // 普通设置弹窗：与 Pet 同级（Windows 下 screen-saver），由 getChildWindowTopLevel
      // 统一决策 —— 低于 Pet 会触发 DWM 白屏 + 被第三方 topmost 应用压过。
      // mini-game 类（normalFramed）显式不置顶，跳过两条 setAlwaysOnTop 路径。
      if (normalFramed || isOpenClawGuide) {
        try { childWindow.setAlwaysOnTop(false); } catch (err) {}
      } else if (topLevel.alwaysOnTop) {
        try { childWindow.setAlwaysOnTop(true, topLevel.level); } catch (err) {}
      } else if (topLevel.alwaysOnTop === false) {
        try { childWindow.setAlwaysOnTop(false); } catch (err) {}
      } else {
        try { childWindow.setAlwaysOnTop(true, getManagedTopLevel()); } catch (err) {}
      }

      // ready-to-show + did-finish-load + 超时兜底：正常情况等首次绘制完再显示（无白屏），
      // 在 macOS / Linux 上当 Pet + AgentHUD 等多个 transparent 窗口并发加载时，
      // 新子窗口的 ``ready-to-show`` 偶发不触发或延迟极久 —— 表现为开 NekoClaw + 插件
      // 后从选项里点出来的 api_key / memory_browser 等子窗口完全纯白、合成层从未推到 OS。
      // 与 window-manager.js 里 reactChat 同思路，三路同时绑定取最早触发的：
      //   1) ``ready-to-show``  —— 首帧准备就绪信号（最理想，无闪烁）
      //   2) ``did-finish-load`` —— DOMContentLoaded + onload 完成，对 transparent 并发场景兜底
      //   3) 1500ms 超时         —— 极端竞态下硬触发，宁可有一帧白也别永久白屏
      // ``shown`` 标志保证只执行一次；后续触发的事件直接 no-op。
      let shown = false;
      let demoted = false;
      const demote = () => {
        if (!shown || demoted || childWindow.isDestroyed()) return;
        demoted = true;
        try {
          if (childWindow.isAlwaysOnTop()) childWindow.setAlwaysOnTop(false);
        } catch (e) {
          try { childWindow.setAlwaysOnTop(false); } catch (_) {}
        }
        // 让父窗（Pet/chat）拿回焦点 + 触发 reassertion tick 把 topmost 全部
        // 重新 moveTop 一遍，soccer/badminton 落到普通层。
        try { parentWin.moveTop(); } catch (e) { /* ignore */ }
        markZOrderDirty();
      };
      const scheduleDemote = () => {
        setTimeout(demote, 0);
      };
      const doShow = () => {
        if (shown || childWindow.isDestroyed()) return;
        shown = true;
        try {
          if (normalFramed) {
            try {
              if (!childWindow.isMaximized()) childWindow.maximize();
            } catch (e) { log('maximize 失败:', e); }
          }
          childWindow.show();
          childWindow.focus();
          // mini-game 不调 moveTop —— show 时给焦点是可以的，但抢 z-order 会
          // 把它推到 topmost 带的边缘，反而让 Pet/chat 等 alwaysOnTop 窗口看起
          // 来跟它"打架"。让它老实呆在普通层。
          if (!normalFramed) {
            try { childWindow.moveTop(); } catch (e) { /* ignore */ }
          }
          if (normalFramed) scheduleDemote();
        } catch (err) { log('显示/聚焦子窗口失败:', err); }
      };

      // mini-game 加载完成后显式下沉 z-order：让猫娘 Pet 和 chat 等 alwaysOnTop
      // 窗口浮在 mini-game 上方。show 时 OS 通常给 mini-game 焦点，焦点窗口短
      // 暂在视觉上"上来"；did-finish-load 之后我们主动 setAlwaysOnTop(false)
      // 幂等再触发一次 reassertion（_zOrderDirty=true 让下一 tick 把 Pet/chat
      // 重新 moveTop），这样用户感知是"游戏页加载完，猫娘和 chat 自然浮在上面"。
      if (normalFramed) {
        childWindow.webContents.once('did-finish-load', scheduleDemote);
        // ready-to-show 兜底（与 voice_clone 同思路，防 Chromium 偶发不发火）
        setTimeout(demote, 600);
      }
      childWindow.once('ready-to-show', doShow);
      // ``did-finish-load`` 兜底：覆盖 macOS / Linux 多 transparent 窗口并发场景
      // 下 ``ready-to-show`` 不触发的情况（NekoClaw + 插件开启时 AgentHUD 与 Pet
      // 并发加载会复现）。``shown`` 守卫保证只 show 一次，不会和 ``ready-to-show``
      // 重复 focus/maximize。
      childWindow.webContents.once('did-finish-load', doShow);
      // 极端竞态下两个事件都不来时的最终兜底。voice_clone / mini-game 仍保留原
      // 300ms 短兜底（这两类历史上 ``ready-to-show`` 最不稳定，早点强制 show 体感
      // 更好），其他窗口给 1500ms —— 留出 ``ready-to-show`` / ``did-finish-load`` 的
      // 正常窗口期，超时才硬触发避免永久白屏。
      if (normalFramed || isOpenClawGuide || childUrl.includes('voice_clone')) {
        setTimeout(doShow, 300);
      } else {
        setTimeout(doShow, 1500);
      }

      // 递归：让子窗口也能正确打开孙窗口（如 chara_manager → model_manager）
      setupChildWindowHandlers(childWindow);
    });
  }

  setupChildWindowHandlers(petWin);

  // 全局子窗口置顶管理
  if (!browserWindowCreatedHookInstalled) {
    browserWindowCreatedHookInstalled = true;
    app.on('browser-window-created', (event, win) => {
      try {
        // 新窗口创建：标记 Z-order dirty，下次 reassertion tick 会执行完整 rank-sorted 重排
        markZOrderDirty();

        windowManager.installNavigationShortcutGuard(win, 'BrowserWindow', log);

        if (win === getLoadingWindow()) return;

        // 所有窗口（含受管 Pet/Chat/Subtitle/AgentHud/Jukebox）都注册 show/focus/blur/closed
        // 监听器置 dirty —— 这些事件都改变 Z-order，需要 reassertion 重排
        ensureMarkDirtyHooked(win);

        // 忽略我们自己管理的窗口（Pet/Chat/Subtitle/AgentHud/Jukebox）后续逻辑
        // 用动态查询而不是静态 Set（避免时序问题）
        const currentWindows = windowManager.getWindows();
        const isManaged = Object.values(currentWindows).some(w => w === win);
        if (isManaged) return;

        log('browser-window-created 子窗口:', win.getTitle());
        childWindowCount += 1;

        try { win.setIcon(getIcon()); } catch (err) {}

        // 统一走 applyTopOn 应用当前全局置顶状态
        // - URL 尚未确定时先用 setImmediate 跑一次（适用于 data:/ about: URL 的 hotkey/portSettings 窗口）
        // - 页面导航完成后再跑一次，按 URL 分类精细化（例如 card_maker → screen-saver）
        const firstApply = () => {
          if (!win.isDestroyed()) applyTopOn(win);
        };
        setImmediate(firstApply);
        win.webContents.once('did-navigate', firstApply);

        win.on('closed', () => {
          try {
            if (childWindowCount > 0) childWindowCount -= 1;
          } catch (err) {}
          markZOrderDirty();
        });
      } catch (err) {
        log('browser-window-created 钩子异常:', err);
      }
    });
  }

  // 缓存清除后加载页面
  petWin.webContents.session.clearCache().then(() => {
    // Pet 窗口已经在 window-manager 中加载了 URL，这里不需要重复加载
  });

  // 初始穿透（preload 接管后续切换）
  const _inputRegionBackend = typeof getInputRegionBackend === 'function'
    ? getInputRegionBackend(petWin)
    : null;
  const _hasSetShape = !!(_inputRegionBackend && _inputRegionBackend.canUseSetShape);
  let _reapplyShape = null; // hoisted so pet focus/blur handlers can call it
  log(`[setShape-init] hasSetShape=${_hasSetShape} backend=${_inputRegionBackend && _inputRegionBackend.backend ? _inputRegionBackend.backend : 'unknown'} isLinuxWaylandRuntime=${isLinuxWaylandRuntime()} platform=${process.platform} WAYLAND_DISPLAY=${process.env.WAYLAND_DISPLAY || ''} XDG_SESSION_TYPE=${process.env.XDG_SESSION_TYPE || ''}`);
  if (_hasSetShape) {
    // Patched Electron with setShape support — use Wayland input-region passthrough.
    // On X11, setShape affects the visible shape as well, so X11 uses native
    // setIgnoreMouseEvents polling instead.
    // Chromium resets wl_surface_set_input_region to full-window bounds ~40ms after
    // every xdg_toplevel.configure event. KDE Plasma fires configure at 60fps during
    // focus transition animations — poll at 16ms (one frame) to always win the race.
    log('[setShape-init] setShape available — enabling input-region passthrough with polling');
    petShowDeferredForNativePassthrough = true;
    try {
      const startupPassthroughShape = getWaylandPetStartupPassthroughShape();
      _lastShapeByWindow.set(petWin.id, []);
      if (_lastShapeMetaByWindow && typeof _lastShapeMetaByWindow.set === 'function') {
        _lastShapeMetaByWindow.set(petWin.id, {
          source: 'pet-wayland-startup',
          reason: 'startup-passthrough',
          mode: 'passthrough',
          wayland: true,
        });
      }
      petWin.setIgnoreMouseEvents(false);
      _ignoreStateByWindow.set(petWin.id, false);
      petWin.setShape(startupPassthroughShape);
      log('[setShape-init] Wayland Pet starts hidden with 1px input-region passthrough');
    } catch (error) {
      log('[setShape-init] Wayland initial passthrough failed:', error && error.message ? error.message : error);
    }
    showPetWindow('wayland-setShape-initial-passthrough');
    if (getIsGlobalAlwaysOnTop()) {
      try {
        petWin.setAlwaysOnTop(true, 'floating');
        log(`[AOT-init] setAlwaysOnTop(true,'floating') called → isAlwaysOnTop()=${petWin.isAlwaysOnTop()}`);
      } catch (e) {
        log(`[AOT-init] setAlwaysOnTop ERROR: ${e.message}`);
      }
    } else {
      log('[AOT-init] Skipping setAlwaysOnTop — getIsGlobalAlwaysOnTop()=false');
    }

    let _shapeApplyCount = 0;
    let _shapeLastLogTime = 0;

    _reapplyShape = (trigger) => {
      if (!petWin || petWin.isDestroyed()) return;
      const rects = _lastShapeByWindow.get(petWin.id);
      if (rects !== undefined) {
        try {
          const meta = _lastShapeMetaByWindow && typeof _lastShapeMetaByWindow.get === 'function'
            ? _lastShapeMetaByWindow.get(petWin.id)
            : {};
          const effectiveRects = typeof getNativeWindowShapeRects === 'function'
            ? getNativeWindowShapeRects(petWin, rects, meta)
            : (typeof getEffectiveWindowShapeRects === 'function'
                ? getEffectiveWindowShapeRects(petWin, rects)
                : rects);
          const shapeRects = Array.isArray(effectiveRects) ? effectiveRects : [];
          try {
            petWin.setIgnoreMouseEvents(false);
            _ignoreStateByWindow.set(petWin.id, false);
          } catch (_) {}
          if (shapeRects.length === 0) {
            const b = petWin.getBounds();
            petWin.setShape([{
              x: Math.max(0, Math.round(b.width) - 1),
              y: Math.max(0, Math.round(b.height) - 1),
              width: 1,
              height: 1,
            }]);
          } else {
            petWin.setShape(shapeRects);
          }
          _shapeApplyCount++;
          // Log every 5s from polling, but always log on explicit trigger
          const now = Date.now();
          if (trigger || now - _shapeLastLogTime > 5000) {
            log(`[setShape-reapply] trigger=${trigger || 'poll'} count=${_shapeApplyCount} rects=${JSON.stringify(shapeRects)}`);
            _shapeLastLogTime = now;
          }
        } catch (e) {
          log(`[setShape-reapply] ERROR trigger=${trigger || 'poll'}: ${e.message}`);
        }
      } else {
        const now = Date.now();
        if (trigger || now - _shapeLastLogTime > 5000) {
          log(`[setShape-reapply] trigger=${trigger || 'poll'} NO rects stored yet`);
          _shapeLastLogTime = now;
        }
      }
    };

    // Poll at ~one frame (16ms) to keep up with per-frame configure resets during
    // compositor focus animations (KDE Plasma can fire configure at 60fps).
    const _shapePollingInterval = setInterval(() => _reapplyShape(null), 16);

    // Also re-apply immediately on app-level focus transitions, which is when
    // Wayland compositors burst configure events hardest.
    const _reapplyOnFocus = (win) => {
      log(`[setShape] app browser-window-focus/blur fired winId=${win ? win.id : '?'} — re-applying shape immediately`);
      _reapplyShape('focus-event');
    };
    const _reapplyOnBlur = (win) => {
      log(`[setShape] app browser-window-blur fired winId=${win ? win.id : '?'} — re-applying shape immediately`);
      _reapplyShape('blur-event');
    };
    app.on('browser-window-focus', _reapplyOnFocus);
    app.on('browser-window-blur', _reapplyOnBlur);

    petWin.once('closed', () => {
      clearInterval(_shapePollingInterval);
      app.off('browser-window-focus', _reapplyOnFocus);
      app.off('browser-window-blur', _reapplyOnBlur);
    });
  } else if (shouldUseNativeIgnoreMouse(petWin)) {
    const managedPetWindow = (() => {
      try {
        const windows = windowManager && typeof windowManager.getWindows === 'function'
          ? windowManager.getWindows()
          : null;
        return !!(windows && windows.pet && windows.pet.id === petWin.id);
      } catch (_) {
        return false;
      }
    })();
    if (managedPetWindow) {
      // Keep the fullscreen X11 Pet hidden until native ShapeInput has a
      // passthrough region. Native ignore is only the fallback when ShapeInput
      // cannot be installed in time.
      petShowDeferredForNativePassthrough = true;
      const initialPassthrough = applyInitialX11PetPassthrough(petWin);
      initialPassthrough.then((ok) => {
        showPetWindow(ok ? 'x11-shape-input-ready' : 'x11-native-ignore-timeout');
      }).catch(() => {});
      log('[setShape-init] managed X11 Pet stays hidden until ShapeInput passthrough is ready');
    } else {
      petWin.setIgnoreMouseEvents(true, process.platform === 'linux' ? { forward: true } : undefined);
      _ignoreStateByWindow.set(petWin.id, true);
    }
  } else {
    // Wayland without setShape patch — no native passthrough available.
    if (process.platform === 'linux' && isLinuxWaylandRuntime()) {
      petShowDeferredForNativePassthrough = true;
      const patch = _inputRegionBackend && _inputRegionBackend.patchStatus ? _inputRegionBackend.patchStatus : {};
      log('[setShape-init] Wayland native input region unavailable; keeping fullscreen Pet hidden to avoid blocking desktop:', JSON.stringify({
        backend: _inputRegionBackend && _inputRegionBackend.backend,
        hasSetShapeMethod: !!(_inputRegionBackend && _inputRegionBackend.hasSetShapeMethod),
        reason: patch.reason || '',
        electronVersion: patch.electronVersion || '',
        compositor: patch.compositor || 'unknown',
        execSha256: patch.execSha256 || null,
      }));
    } else {
      log('[setShape-init] No setShape, no native ignore-mouse — limited passthrough');
      if (getIsGlobalAlwaysOnTop()) {
        petWin.setAlwaysOnTop(true, 'floating');
      }
    }
  }

  // 焦点事件
  petWin.on('focus', () => {
    const aot = (() => { try { return petWin.isAlwaysOnTop(); } catch(e) { return 'err'; } })();
    log(`[pet-focus] Pet 窗口获得焦点 — isAlwaysOnTop=${aot}`);
    if (_reapplyShape) _reapplyShape('pet-win-focus');
    if (!petWin.isDestroyed()) {
      petWin.webContents.send('window-focus');
      try {
        petWin.webContents.setZoomLevel(0);
        petWin.webContents.setZoomFactor(1.0);
      } catch (e) {}
    }
  });

  petWin.on('blur', () => {
    const aot = (() => { try { return petWin.isAlwaysOnTop(); } catch(e) { return 'err'; } })();
    log(`[pet-blur] Pet 窗口失去焦点 — isAlwaysOnTop=${aot}`);
    if (_reapplyShape) _reapplyShape('pet-win-blur');
  });

  // 导航事件
  petWin.webContents.on('did-start-navigation', (event, url) => {
    log('页面开始导航:', url);
    if (!petWin.isDestroyed()) {
      const isX11Pet = process.platform === 'linux' && !isLinuxWaylandRuntime();
      if (!isX11Pet && shouldUseNativeIgnoreMouse(petWin)) petWin.setIgnoreMouseEvents(false);
      if (!isX11Pet) {
        _ignoreStateByWindow.set(petWin.id, false);
      }
    }
  });

  petWin.webContents.on('did-navigate-in-page', (event, url) => {
    log('页内导航 (SPA):', url);
    if (!petWin.isDestroyed()) {
      const isX11Pet = process.platform === 'linux' && !isLinuxWaylandRuntime();
      if (!isX11Pet && shouldUseNativeIgnoreMouse(petWin)) petWin.setIgnoreMouseEvents(false);
      if (!isX11Pet) {
        _ignoreStateByWindow.set(petWin.id, false);
      }
      petWin.webContents.send('navigation-start');
    }
  });

  petWin.webContents.on('did-finish-load', () => {
    const currentUrl = petWin.webContents.getURL();
    log('页面加载完成:', currentUrl);
    try {
      petWin.webContents.setZoomLevel(0);
      petWin.webContents.setZoomFactor(1.0);
    } catch (e) {}

    if (currentUrl === 'about:blank') {
      if (!petWin.isDestroyed()) {
        const shouldIgnore = shouldUseNativeIgnoreMouse(petWin);
        const isX11Pet = process.platform === 'linux' && !isLinuxWaylandRuntime();
        if (!isX11Pet) petWin.setIgnoreMouseEvents(shouldIgnore, process.platform === 'linux' && shouldIgnore ? { forward: true } : undefined);
        if (!isX11Pet) {
          _ignoreStateByWindow.set(petWin.id, shouldIgnore);
        }
      }
      return;
    }

    if (!petWin.isDestroyed()) {
      const isX11Pet = process.platform === 'linux' && !isLinuxWaylandRuntime();
      if (!isX11Pet && shouldUseNativeIgnoreMouse(petWin)) petWin.setIgnoreMouseEvents(false);
      if (!isX11Pet) {
        _ignoreStateByWindow.set(petWin.id, false);
      }
      setTimeout(() => {
        if (!petWin.isDestroyed()) {
          petWin.webContents.send('page-fully-loaded');
          if (getAppConfig() && getAppConfig().darkMode) {
            petWin.webContents.send('toggle-dark-mode', true);
          }
        }
      }, 150);
    }
  });

  if (!petShowDeferredForNativePassthrough) {
    showPetWindow('setup-complete');
  }

  bindWindowDisplayRecovery(petWin, {
    logTag: '[PetWindow]',
    adjustLogLabel: '屏幕配置变化，调整窗口:',
  });
}

// ===== 原 createWindow 保留用于 reloadAndShow 兼容 =====
function createWindow(urlToLoad) {
  // 修复 preload 路径：打包后需要从正确的位置加载
  let preloadPath;
  if (app.isPackaged) {
    // 打包后，preload.js 在 resources 目录下
    preloadPath = path.join(process.resourcesPath, 'app.asar', 'src', 'preload.js');
    // 如果找不到，尝试其他可能的位置
    if (!fs.existsSync(preloadPath)) {
      preloadPath = path.join(mainDirname, 'preload.js');
    }
  } else {
    // 开发环境
    preloadPath = path.join(mainDirname, 'preload.js');
  }

  log('createWindow() - urlToLoad:', urlToLoad);
  log('createWindow() - mainDirname:', mainDirname);
  log('createWindow() - preloadPath:', preloadPath);
  log('createWindow() - preload文件是否存在:', fs.existsSync(preloadPath));
  log('createWindow() - 窗口模式:', getIsStreamerMode());

  // 获取主屏幕的边界（只覆盖当前屏幕，不再覆盖所有屏幕）
  const { x, y, width, height } = getAllDisplaysBounds();

  // 根据窗口模式调整窗口选项
  const windowOptions = {
    x, y, width, height,
    fullscreenable: false,
    fullscreen: false,
    resizable: false,
    transparent: true,
    skipTaskbar: getIsStreamerMode() ? false : true, // 窗口模式显示任务栏
    thickFrame: false,
    frame: false,
    focusable: true,
    alwaysOnTop: getIsGlobalAlwaysOnTop(),
    hasShadow: false,
    title: 'N.E.K.O.',
    webPreferences: {
      preload: preloadPath,
      sandbox: false,
      contextIsolation: false,
      nodeIntegration: false,
      enableRemoteModule: false,
      webSecurity: true,
      allowRunningInsecureContent: false,
      backgroundThrottling: false, // 关键：禁止页面后台运行时的 CPU 限制
      zoomFactor: 1.0, // 强制初始缩放为 1
      autoplayPolicy: 'no-user-gesture-required', // 允许主动搭话时自动播放 TTS 音频
    },
  };

  // 非窗口模式下使用 panel 类型（仅 macOS 支持 panel 类型）
  if (!getIsStreamerMode() && process.platform === 'darwin') {
    windowOptions.type = 'panel';
  }

  const mainWindow = new BrowserWindow(windowOptions);
  setMainWindow(mainWindow);
  schedulePetBoundsRepair(mainWindow, { x, y, width, height });

  // ⭐ 禁用缩放功能 - 桌宠应用不允许缩放
  // 1. 设置缩放级别为 0（即 100%）
  mainWindow.webContents.setZoomLevel(0);
  mainWindow.webContents.setZoomFactor(1.0);

  // 2. 阻止缩放快捷键（Ctrl++, Ctrl+-, Ctrl+0, Ctrl+鼠标滚轮）
  mainWindow.webContents.on('before-input-event', (event, input) => {
    // 检测 Ctrl/Cmd 组合键
    const isCtrlOrCmd = input.control || input.meta;
    if (isCtrlOrCmd) {
      // 阻止 Ctrl+Plus, Ctrl+Minus, Ctrl+0, Ctrl+=, Ctrl+NumpadAdd, Ctrl+NumpadSubtract
      const zoomKeys = ['=', '+', '-', '0', 'Equal', 'Minus', 'Digit0', 'NumpadAdd', 'NumpadSubtract', 'Numpad0'];
      if (zoomKeys.includes(input.key) || zoomKeys.includes(input.code)) {
        event.preventDefault();
        log('已阻止缩放快捷键:', input.key);
      }
    }
  });

  // 3. 监听缩放变化并立即重置
  mainWindow.webContents.on('zoom-changed', (event, zoomDirection) => {
    const currentZoom = mainWindow.webContents.getZoomLevel();
    if (currentZoom !== 0) {
      mainWindow.webContents.setZoomLevel(0);
      mainWindow.webContents.setZoomFactor(1.0);
    }
  });

  mainWindow.webContents.session.clearCache().then(() => {
    mainWindow.loadURL(urlToLoad);
  });

  // 默认忽略鼠标事件（穿透），由渲染进程根据需要动态控制
  // 鼠标位置追踪改用轮询方式实现（见 preload.js 中的 startMousePoller）
  const mainInitialIgnore = shouldUseNativeIgnoreMouse(mainWindow);
  mainWindow.setIgnoreMouseEvents(mainInitialIgnore, process.platform === 'linux' && mainInitialIgnore ? { forward: true } : undefined);
  _ignoreStateByWindow.set(mainWindow.id, mainInitialIgnore);

  // 由 applyTopOn 统一处理（跟随全局开关，启用时包含 Windows DWM 兜底）
  applyTopOn(mainWindow, { kind: 'pet', defaultLevel: 'floating' });

  // ⭐ 监听窗口焦点事件
  // 移除旧的强制重置逻辑，避免与 Preload 的精细控制冲突
  mainWindow.on('focus', () => {
    log('主窗口获得焦点');
    // 通知渲染进程窗口已聚焦，让渲染进程决定是否需要调整状态
    if (!mainWindow.isDestroyed()) {
      mainWindow.webContents.send('window-focus');
      // ⭐ 窗口获得焦点时也重置缩放（防止意外缩放）
      try {
        mainWindow.webContents.setZoomLevel(0);
        mainWindow.webContents.setZoomFactor(1.0);
      } catch (e) {
        // 忽略
      }
    }
  });

  // ⭐ 监听页面导航开始，在导航时取消鼠标事件忽略
  mainWindow.webContents.on('did-start-navigation', (event, url) => {
    log('页面开始导航:', url);
    if (!mainWindow.isDestroyed()) {
      if (shouldUseNativeIgnoreMouse(mainWindow)) mainWindow.setIgnoreMouseEvents(false);
      _ignoreStateByWindow.set(mainWindow.id, false);
    }
  });

  // ⭐ 监听页内导航 (SPA)，确保在路由切换时取消鼠标事件忽略
  mainWindow.webContents.on('did-navigate-in-page', (event, url) => {
    log('页内导航 (SPA):', url);
    if (!mainWindow.isDestroyed()) {
      if (shouldUseNativeIgnoreMouse(mainWindow)) mainWindow.setIgnoreMouseEvents(false);
      _ignoreStateByWindow.set(mainWindow.id, false);
      // 通知 preload 进入"导航安全模式"并在导航完成后重新应用正确的穿透状态
      mainWindow.webContents.send('navigation-start');
    }
  });

  // ⭐ 监听页面加载完成 - 延迟让渲染进程有机会接管控制权
  mainWindow.webContents.on('did-finish-load', () => {
    const currentUrl = mainWindow.webContents.getURL();
    log('页面加载完成:', currentUrl);

    // ⭐ 每次页面加载完成后重置缩放级别（防止缩放状态残留）
    try {
      mainWindow.webContents.setZoomLevel(0);
      mainWindow.webContents.setZoomFactor(1.0);
      log('页面加载完成，已重置缩放级别');
    } catch (e) {
      log('重置缩放级别失败:', e.message);
    }

    // 如果是 about:blank（手机模式），保持完全穿透
    if (currentUrl === 'about:blank') {
      log('检测到 about:blank 页面，保持完全穿透');
      if (!mainWindow.isDestroyed()) {
        const shouldIgnore = shouldUseNativeIgnoreMouse(mainWindow);
        mainWindow.setIgnoreMouseEvents(shouldIgnore, process.platform === 'linux' && shouldIgnore ? { forward: true } : undefined);
        _ignoreStateByWindow.set(mainWindow.id, shouldIgnore);
      }
      return;
    }

    log('暂时取消鼠标事件忽略');
    if (!mainWindow.isDestroyed()) {
      if (shouldUseNativeIgnoreMouse(mainWindow)) mainWindow.setIgnoreMouseEvents(false);
      _ignoreStateByWindow.set(mainWindow.id, false);
      // 延迟通知渲染进程可以接管控制权
      setTimeout(() => {
        if (!mainWindow.isDestroyed()) {
          log('通知渲染进程接管鼠标事件控制');
          mainWindow.webContents.send('page-fully-loaded');

          // 同步暗色模式状态到渲染进程
          if (getAppConfig() && getAppConfig().darkMode) {
            mainWindow.webContents.send('toggle-dark-mode', true);
          }
        }
      }, 150);
    }
  });

  mainWindow.show();

  bindWindowDisplayRecovery(mainWindow, {
    logTag: '[MainWindow]',
    adjustLogLabel: '屏幕配置变化，调整窗口到当前屏幕:',
  });
}

  return {
    createWindow,
    getAllDisplaysBounds,
    getDisplayBounds,
    schedulePetBoundsRepair,
    setupPetWindowBehavior,
  };
}

module.exports = {
  createPetWindowLifecycle,
};
