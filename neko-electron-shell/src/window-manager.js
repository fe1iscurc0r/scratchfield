/**
 * window-manager.js
 * 多窗口管理模块 —— 负责创建和管理 Pet / Chat / Subtitle / AgentHUD 窗口
 *
 * 设计原则：
 * - Pet 窗口是主窗口，持有 WebSocket 连接，承载模型渲染
 * - Chat / Subtitle / AgentHUD 是卫星窗口，通过 IPC 从主进程获取数据
 * - 常规窗口（插件管理等）由 Pet 窗口的 window.open 自然产生
 */

const { BrowserWindow, screen, app, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const { JUKEBOX_CHANNELS, COMPACT_CHAT_BALL_CHANNELS, SUBTITLE_CHANNELS } = require('./ipc-channels');
const { applyX11InputShape } = require('./main/linux-x11-input-shape');
const {
  SUBTITLE_WINDOW_EDGE_INSET,
  SUBTITLE_WINDOW_MIN_WIDTH,
  SUBTITLE_WINDOW_MIN_HEIGHT,
} = require('./subtitle-window-constants');
const { getWorkAreaWindowInitialBounds } = require('./main/window-bounds-utils');
const {
  isWaylandSetShapePatchVerified,
  shouldAllowUnverifiedWaylandSetShape,
} = require('./main/wayland-input-region-backend');

// ===== 窗口引用 =====
let petWindow = null;
let chatWindow = null;
let subtitleWindow = null;
let subtitleSettingsWindow = null;
let agentHudWindow = null;
let jukeboxWindow = null;
// compact 悬浮最小化球（#1595 之前模型旁的常驻悬浮入口）已停用 —— buildDesktopCompactBallScreenRect
// 恒返回 null，compact 态不会主动 SHOW 球。
//
// 现在 Win32/macOS 毛线球折叠（compact 对话条左侧毛绒球按钮 → minimized）会复用同一个
// compactChatBallWindow 作为 opacity-0 chat carrier 之上的独立球窗口；Linux 不走该
// 外部球路径，chat BrowserWindow 自身保留为 88x88 折叠球。

let compactChatBallWindow = null;
let compactChatBallTemporarilyHidden = false;
let compactChatBallMacInputPollTimer = null;
let compactChatBallMacInputIgnored = null;
let compactChatBallReadyListener = null;
// main.js 注册的「清掉拖动起始尺寸缓存」回调。缓存（compactChatBallDragSizes）属于 main 模块，
// 但球的 show/hide 生命周期由本模块掌管，且 full-surface 切换隐藏、兼容模式 destroy+recreate
// 等内部路径不经过 main 的 teardown wrapper —— 在 showCompactChatBallWindow 里回调它，保证每次
// 球会话起点都清缓存（new session start），下次拖动按真实折叠尺寸重新快照。见 main.js 注册处。
let compactChatBallDragSizesResetListener = null;
function setCompactChatBallDragSizesReset(fn) {
  compactChatBallDragSizesResetListener = (typeof fn === 'function') ? fn : null;
}

function setCompactChatBallReadyListener(listener) {
  compactChatBallReadyListener = (typeof listener === 'function') ? listener : null;
}

function notifyCompactChatBallReady(reason, ballWin) {
  if (typeof compactChatBallReadyListener !== 'function') return;
  try { compactChatBallReadyListener(reason || 'compact-ball-ready', ballWin || compactChatBallWindow); } catch (_) {}
}

const COMPACT_CHAT_BALL_ANCHOR_SIZE = 88;
const COMPACT_CHAT_BALL_VISUAL_SIZE = 58;
const COMPACT_CHAT_BALL_WINDOW_SIZE = COMPACT_CHAT_BALL_VISUAL_SIZE;
const COMPACT_CHAT_BALL_VISUAL_OFFSET_X = 0;
const COMPACT_CHAT_BALL_VISUAL_OFFSET_Y = 0;
const COMPACT_CHAT_BALL_ANCHOR_OFFSET_Y = COMPACT_CHAT_BALL_ANCHOR_SIZE - COMPACT_CHAT_BALL_VISUAL_SIZE;
const SUBTITLE_SETTINGS_WINDOW_WIDTH = 300;
const SUBTITLE_SETTINGS_WINDOW_HEIGHT = 188;
const SUBTITLE_SETTINGS_WINDOW_GAP = 8;
const SUBTITLE_SETTINGS_WINDOW_RADIUS = 8;
const SUBTITLE_SETTINGS_PANEL_BLUR_RECHECK_MS = 120;

// ===== 应用退出状态 =====
let appQuitInProgress = false;
app.on('before-quit', () => {
  appQuitInProgress = true;
});

function isAppQuitInProgress() {
  return appQuitInProgress || app.isQuiting || app.isQuitting;
}

// ===== 全局置顶协调器（由 main.js 在启动时通过 setTopCoordinator 注入）=====
// 设计原因：window-manager 不直接读取 main.js 的 isGlobalAlwaysOnTop（避免循环依赖），
// 所有 setAlwaysOnTop 决策统一走 coordinator.applyTo(win, classification)。
let _topCoordinator = null;
function setTopCoordinator(coord) {
  _topCoordinator = coord;
}

function isAltF4Input(input) {
  return !!(input && input.alt && (input.key === 'F4' || input.code === 'F4'));
}

function protectWindowFromAltF4(win, name, log = console.log, options = {}) {
  if (!win || win.isDestroyed() || win._nekoAltF4Protected) return;
  win._nekoAltF4Protected = true;

  win.webContents.on('before-input-event', (event, input) => {
    if (!isAltF4Input(input)) return;
    event.preventDefault();
    log(`[WindowManager] 已阻止 ${name} 窗口 Alt+F4`);
  });

  win.on('close', (event) => {
    if (win._forceClose || isAppQuitInProgress() || options.allowClose?.()) return;
    event.preventDefault();
    if (options.hideOnClose && !win.isDestroyed()) win.hide();
    log(`[WindowManager] 已阻止 ${name} 窗口关闭`);
  });
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

function applyFullWindowX11InputShape(win, log = console.log, label = 'window') {
  if (!isLinuxX11Runtime()) return;
  if (!win || win.isDestroyed()) return;
  try {
    win.setIgnoreMouseEvents(false);
  } catch (_) {}
  const bounds = win.getBounds();
  const rects = [{ x: 0, y: 0, width: bounds.width, height: bounds.height }];
  applyX11InputShape(win, rects, {
    log,
    scaleFactor: getWindowScaleFactor(win),
    allowNativeFallback: true,
  }).catch((error) => {
    try { log(`[WindowManager] ${label} X11 input shape failed:`, error && (error.message || error)); } catch (_) {}
  });
}

// ===== 配置 =====
const WINDOW_DEFAULTS = {
  pet: {
    // Pet 窗口覆盖主屏工作区（与原 mainWindow 行为一致）
    transparent: true,
    frame: false,
    thickFrame: false, // Windows: 必须配合 transparent 使用，否则 DWM 厚边框导致白色背景
    // alwaysOnTop 由 coordinator 在创建后统一管理（跟随全局开关）
    skipTaskbar: true,
    resizable: false,
    fullscreenable: false,
    hasShadow: false,
  },
  chat: {
    width: 400,
    height: 560,
    transparent: true,
    frame: false,
    // alwaysOnTop 由 coordinator 管理
    skipTaskbar: true, // 跟随 Pet 窗口，非窗口模式下隐藏任务栏图标
    resizable: true,
    fullscreenable: false,
    hasShadow: false,
  },
  subtitle: {
    width: 600,
    height: 68,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    // alwaysOnTop 由 coordinator 管理
    skipTaskbar: true,
    // 透明无框窗口使用 JS/main 进程 resize；开启系统 native resize 会和自定义边界抢输入，
    // 上/左边界尤其容易抖动或退化成窗口移动。
    resizable: false,
    fullscreenable: false,
    hasShadow: false,
    minWidth: SUBTITLE_WINDOW_MIN_WIDTH,
    minHeight: SUBTITLE_WINDOW_MIN_HEIGHT,
  },
  agentHud: {
    width: 320,
    height: 400,
    transparent: true,
    frame: false,
    // alwaysOnTop 由 coordinator 管理
    skipTaskbar: true,
    resizable: true,
    fullscreenable: false,
    hasShadow: false,
    minWidth: 240,
    minHeight: 200,
  },
  subtitleSettings: {
    width: SUBTITLE_SETTINGS_WINDOW_WIDTH,
    height: SUBTITLE_SETTINGS_WINDOW_HEIGHT,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    show: false,
    skipTaskbar: true,
    resizable: false,
    fullscreenable: false,
    hasShadow: false,
    // alwaysOnTop 由 coordinator 管理
  },
};

/**
 * 获取 preload 脚本路径
 * @param {string} name - preload 文件名（不含扩展名）
 * @param {boolean} isPackaged - app.isPackaged
 * @returns {string} 绝对路径
 */
function getPreloadPath(name, isPackaged) {
  if (isPackaged) {
    // 打包后优先查找 asar 内
    const asarPath = path.join(process.resourcesPath, 'app.asar', 'src', `${name}.js`);
    if (fs.existsSync(asarPath)) return asarPath;
    return path.join(__dirname, `${name}.js`);
  }
  return path.join(__dirname, `${name}.js`);
}

function shouldAttachSameOriginChildPreload(parentWin, childUrl) {
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

function installNavigationShortcutGuard(win, label, log = console.log) {
  if (!win || !win.webContents) return;

  if (win._nekoNavigationShortcutGuardState) {
    win._nekoNavigationShortcutGuardState.label = label;
    win._nekoNavigationShortcutGuardState.log = log;
    return;
  }

  win._nekoNavigationShortcutGuardState = { label, log };

  win.webContents.on('before-input-event', (event, input) => {
    if (input.type && input.type !== 'keyDown') return;

    const isCtrlOrCmd = input.control || input.meta;
    const key = String(input.key || '').toLowerCase();
    const code = String(input.code || '');
    const isReloadShortcut =
      key === 'f5' ||
      code === 'F5' ||
      (isCtrlOrCmd && key === 'r') ||
      (isCtrlOrCmd && code === 'KeyR');
    const isZoomShortcut = isCtrlOrCmd && ['+', '-', '=', '0'].includes(input.key);

    if (win._nekoAllowNavigationShortcutCapture && (isReloadShortcut || isZoomShortcut)) {
      return;
    }

    if (isReloadShortcut) {
      event.preventDefault();
      const state = win._nekoNavigationShortcutGuardState || {};
      const guardLabel = state.label || label;
      const guardLog = state.log || log;
      guardLog(`[WindowManager] 已阻止 ${guardLabel} 刷新快捷键:`, input.key || input.code);
      return;
    }

    if (isZoomShortcut) {
      event.preventDefault();
      const state = win._nekoNavigationShortcutGuardState || {};
      const guardLabel = state.label || label;
      const guardLog = state.log || log;
      guardLog(`[WindowManager] 已阻止 ${guardLabel} 缩放快捷键:`, input.key || input.code);
    }
  });
}

/**
 * 获取主屏边界（用于 Pet 窗口全屏覆盖）
 * 与 main.js 的 getAllDisplaysBounds / getFullscreenDisplayBounds 行为保持一致。
 */
function getAllDisplaysBounds() {
  const displays = screen.getAllDisplays();
  if (displays.length === 0) {
    return { x: 1, y: 1, width: 1919, height: 1079 };
  }

  // 屏幕内 off-by-one：继续破坏“起点贴齐 + size 等于 display”的完美全屏覆盖判定，
  // 以延续对 DWM/Chromium fullscreen-borderless / occlusion 优化副作用的规避。
  // 这些副作用包括后台浏览器视频暂停、第三方播放器卡顿等；当前屏幕内方案是否
  // 与旧 extend-by-1 在所有 GPU 驱动 / Windows 版本上等价，仍需按复现场景验证。
  // 不再使用 extend-by-1 越界方案；部分 Windows/Electron 环境会在创建期把越界透明窗口夹到 workArea。
  // 右/底贴齐 display，左/上各留 1px；若创建期仍被夹到 workArea，创建后的 bounds repair 会修回目标高度。
  const primary = screen.getPrimaryDisplay();
  const b = primary.bounds;
  return {
    x: b.x + 1,
    y: b.y + 1,
    width: Math.max(1, b.width - 1),
    height: Math.max(1, b.height - 1),
  };
}

function boundsExactlyEqual(a, b) {
  return !!(a && b &&
    a.x === b.x &&
    a.y === b.y &&
    a.width === b.width &&
    a.height === b.height);
}

function schedulePetBoundsRepair(win, targetBounds, log = console.log) {
  if (!win || !targetBounds) return;
  const attempts = [0, 50, 500, 1500];
  for (const delay of attempts) {
    setTimeout(() => {
      if (!win || win.isDestroyed()) return;
      const before = win.getBounds();
      if (boundsExactlyEqual(before, targetBounds)) return;
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
 * 创建 Pet 窗口
 * @param {string} url - 后端 URL（如 http://localhost:48911/）
 * @param {object} options - { isPackaged, isStreamerMode, log }
 * @returns {BrowserWindow}
 */
function createPetWindow(url, options = {}) {
  const { isPackaged = false, isStreamerMode = false, log = console.log } = options;
  // [multi-display-persist] 重启后角色模型回到上次所在屏（该屏已断开则回退主屏）。
  const bounds = getPetStartupBounds();
  const preloadPath = getPreloadPath('preload-pet', isPackaged);

  log('[WindowManager] 创建 Pet 窗口, bounds:', JSON.stringify(bounds));

  const winOptions = {
    ...WINDOW_DEFAULTS.pet,
    backgroundColor: '#00000000', // 显式透明背景色
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    // Linux Pet is a fullscreen transparent window. Keep it unmapped until the
    // lifecycle layer has installed initial passthrough, otherwise startup can
    // briefly expose a fullscreen input target over the desktop.
    show: process.platform === 'linux' ? false : undefined,
    skipTaskbar: isStreamerMode ? false : true,
    webPreferences: {
      preload: preloadPath,
      sandbox: false,
      contextIsolation: false,
      nodeIntegration: false,
      enableRemoteModule: false,
      webSecurity: true,
      allowRunningInsecureContent: false,
      backgroundThrottling: false, // Pet 窗口几乎从不持有焦点，必须禁止后台节流
      autoplayPolicy: 'no-user-gesture-required', // 主动搭话时自动播放 TTS 音频
      zoomFactor: 1.0,
    },
  };

  // macOS: 非 streamer 模式使用 panel 类型
  if (process.platform === 'darwin' && !isStreamerMode) {
    winOptions.type = 'panel';
  }

  // Linux transparent Pet windows stay focusable on both X11 and Wayland.
  // Several compositors route real button events to the window underneath when
  // a transparent Electron top-level is non-focusable; setShape/XShape still
  // controls passthrough for transparent areas.
  if (process.platform === 'linux') {
    winOptions.focusable = true;
  }

  petWindow = new BrowserWindow(winOptions);
  const createdBounds = petWindow.getBounds();
  if (!boundsExactlyEqual(createdBounds, bounds)) {
    log('[PetBoundsRepair] created bounds clamped', JSON.stringify({
      target: bounds,
      actual: createdBounds,
      resizable: petWindow.isResizable ? petWindow.isResizable() : null,
    }));
  }
  schedulePetBoundsRepair(petWindow, bounds, log);

  // 通过 coordinator 统一设置 alwaysOnTop（跟随全局开关）
  // 多窗口模式下用 floating（不用 screen-saver，后者会导致 Windows DWM 干扰视频 overlay）
  _topCoordinator?.applyTo(petWindow, { kind: 'pet', defaultLevel: 'floating' });

  // 禁用缩放
  petWindow.webContents.setZoomLevel(0);
  petWindow.webContents.setZoomFactor(1.0);

  // Linux 下 Pet 穿透由原生 input region 接管：
  // - Wayland: patched setShape -> wl_surface_set_input_region
  // - X11: X ShapeInput helper
  // 因此 Linux Pet 不能以整窗 ignoreMouse 启动，否则与其它窗口交互后
  // renderer 可能收不到恢复事件，模型会卡在点击穿透。
  if (process.platform !== 'linux') {
    petWindow.setIgnoreMouseEvents(true);
  }

  // 加载 Pet 页面（完整 index.html）
  petWindow.loadURL(url);

  protectWindowFromAltF4(petWindow, 'Pet', log);
  installNavigationShortcutGuard(petWindow, 'Pet', log);

  // zoom 防护
  petWindow.webContents.on('zoom-changed', (event) => {
    event.preventDefault();
    petWindow.webContents.setZoomLevel(0);
    petWindow.webContents.setZoomFactor(1.0);
  });

  petWindow.on('closed', () => {
    petWindow = null;
  });

  // [multi-display-persist] 记录 Pet 所在屏（move/resize 防抖保存），供下次启动恢复。
  // 拖拽期/修复期的瞬时尺寸不影响：findSavedDisplay 用中心点判屏，落点屏即正确屏。
  enablePositionPersistence(petWindow, 'pet');

  log('[WindowManager] Pet 窗口已创建');
  return petWindow;
}

/**
 * 创建 Chat 窗口
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createChatWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-chat', isPackaged);

  // 默认位置：主屏右下角
  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const cfg = WINDOW_DEFAULTS.chat;

  log('[WindowManager] 创建 Chat 窗口');

  // 初始位置：左下角（与 index.html 里 chat-container 的 left:20px; bottom:70px 对齐）
  chatWindow = new BrowserWindow({
    ...cfg,
    x: wa.x + 20,
    y: wa.y + wa.height - cfg.height - 70,
    width: cfg.width,
    height: cfg.height,
    show: false, // 延迟显示，等页面加载完再 show，避免闪烁
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: false, // Chat 窗口保留：preload 需替换页面 window.WebSocket 代理（架构约束）
      webSecurity: true,
      sandbox: false, // preload-chat.js require 相对模块（ipc-channels/preload-common），不能开 sandbox
      zoomFactor: 1.0,
      backgroundThrottling: false, // 焦点在 Pet 窗口时 Chat 不应被节流
    },
  });

  _topCoordinator?.applyTo(chatWindow, { kind: 'chat', defaultLevel: 'floating' });
  protectWindowFromAltF4(chatWindow, 'Chat', log, { hideOnClose: true });

  // 页面加载完后再显示
  chatWindow.once('ready-to-show', () => {
    if (chatWindow && !chatWindow.isDestroyed()) chatWindow.show();
  });

  // 加载 Chat 页面
  const chatUrl = new URL('/chat', baseUrl).href;
  chatWindow.loadURL(chatUrl);

  installNavigationShortcutGuard(chatWindow, 'Chat', log);

  chatWindow.on('closed', () => {
    chatWindow = null;
  });

  // Chat 窗口不参与位置持久化（折叠/展开频繁改大小，持久化会导致启动异常）
  log('[WindowManager] Chat 窗口已创建');
  return chatWindow;
}

/**
 * 创建 Subtitle 窗口
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createSubtitleWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-subtitle', isPackaged);

  // 默认位置：主屏底部居中
  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const cfg = WINDOW_DEFAULTS.subtitle;

  log('[WindowManager] 创建 Subtitle 窗口');

  const savedPos2 = loadWindowPositions();
  const subPos = savedPos2.subtitle;
  const subtitlePanelWidth = subPos ? subPos.width : cfg.width;
  const subtitlePanelHeight = subPos ? subPos.height : cfg.height;

  subtitleWindow = new BrowserWindow({
    ...cfg,
    x: subPos ? subPos.x - SUBTITLE_WINDOW_EDGE_INSET : wa.x + Math.round((wa.width - cfg.width) / 2) - SUBTITLE_WINDOW_EDGE_INSET,
    y: subPos ? subPos.y - SUBTITLE_WINDOW_EDGE_INSET : wa.y + wa.height - cfg.height - 100 - SUBTITLE_WINDOW_EDGE_INSET,
    width: subtitlePanelWidth + SUBTITLE_WINDOW_EDGE_INSET * 2,
    height: subtitlePanelHeight + SUBTITLE_WINDOW_EDGE_INSET * 2,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      sandbox: false, // preload-subtitle.js require 相对模块（ipc-channels/preload-common），不能开 sandbox
      zoomFactor: 1.0,
      backgroundThrottling: false, // 置顶子窗口不应被后台节流
    },
  });
  subtitleWindow._nekoSubtitlePanelBounds = {
    width: subtitlePanelWidth,
    height: subtitlePanelHeight,
  };

  _topCoordinator?.applyTo(subtitleWindow, { kind: 'subtitle', defaultLevel: 'floating' });
  protectWindowFromAltF4(subtitleWindow, 'Subtitle', log, { hideOnClose: true });

  // 加载 Subtitle 页面
  const subtitleUrl = new URL('/subtitle', baseUrl).href;
  subtitleWindow.loadURL(subtitleUrl);

  installNavigationShortcutGuard(subtitleWindow, 'Subtitle', log);

  subtitleWindow.on('closed', () => {
    hideSubtitleSettingsWindow();
    subtitleWindow = null;
  });
  subtitleWindow.on('hide', () => {
    if (subtitleWindow && subtitleWindow._nekoPreserveSubtitleSettingsOnHide) {
      subtitleWindow._nekoPreserveSubtitleSettingsOnHide = false;
    }
  });

  enablePositionPersistence(subtitleWindow, 'subtitle');
  log('[WindowManager] Subtitle 窗口已创建');
  return subtitleWindow;
}

function normalizeSubtitleSettingsAnchor(anchor) {
  if (!anchor || typeof anchor !== 'object') return null;
  const x = Math.round(Number(anchor.screenX));
  const y = Math.round(Number(anchor.screenY));
  const width = Math.round(Number(anchor.width));
  const height = Math.round(Number(anchor.height));
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return { x, y, width, height };
}

function getSubtitleSettingsBounds(anchor) {
  const normalizedAnchor = normalizeSubtitleSettingsAnchor(anchor);
  const referenceBounds = normalizedAnchor || (subtitleWindow && !subtitleWindow.isDestroyed()
    ? subtitleWindow.getBounds()
    : null);
  const display = referenceBounds
    ? screen.getDisplayMatching(referenceBounds)
    : screen.getPrimaryDisplay();
  const wa = display.workArea;
  const width = SUBTITLE_SETTINGS_WINDOW_WIDTH;
  const height = SUBTITLE_SETTINGS_WINDOW_HEIGHT;
  const anchorX = normalizedAnchor ? normalizedAnchor.x : (referenceBounds ? referenceBounds.x : wa.x + Math.round((wa.width - width) / 2));
  const anchorY = normalizedAnchor ? normalizedAnchor.y : (referenceBounds ? referenceBounds.y : wa.y + wa.height - height - 100);
  const anchorWidth = normalizedAnchor ? normalizedAnchor.width : (referenceBounds ? referenceBounds.width : width);
  const anchorHeight = normalizedAnchor ? normalizedAnchor.height : (referenceBounds ? referenceBounds.height : 0);
  const belowY = anchorY + anchorHeight + SUBTITLE_SETTINGS_WINDOW_GAP;
  const preferredY = anchorY - height - SUBTITLE_SETTINGS_WINDOW_GAP;
  const y = preferredY >= wa.y
    ? preferredY
    : Math.min(wa.y + wa.height - height, Math.max(wa.y, belowY));
  const x = Math.min(
    wa.x + wa.width - width,
    Math.max(wa.x, anchorX + anchorWidth - width - 4)
  );
  return { x, y, width, height };
}

function sendSubtitleSettingsState(state) {
  if (!subtitleSettingsWindow || subtitleSettingsWindow.isDestroyed()) return;
  try {
    subtitleSettingsWindow.webContents.send(SUBTITLE_CHANNELS.STATE_SYNC, state || {});
  } catch (_) {}
}

function buildRoundedRectShapeRects(width, height, radius) {
  const w = Math.max(0, Math.round(Number(width) || 0));
  const h = Math.max(0, Math.round(Number(height) || 0));
  const r = Math.max(0, Math.min(Math.round(Number(radius) || 0), Math.floor(Math.min(w, h) / 2)));
  if (!w || !h) return [];
  if (!r) return [{ x: 0, y: 0, width: w, height: h }];

  const rects = [];
  for (let y = 0; y < h; y += 1) {
    let inset = 0;
    if (y < r) {
      const dy = r - y - 0.5;
      inset = Math.ceil(r - Math.sqrt(Math.max(0, r * r - dy * dy)));
    } else if (y >= h - r) {
      const dy = y - (h - r) + 0.5;
      inset = Math.ceil(r - Math.sqrt(Math.max(0, r * r - dy * dy)));
    }
    const rowWidth = w - inset * 2;
    if (rowWidth > 0) {
      rects.push({ x: inset, y, width: rowWidth, height: 1 });
    }
  }
  return rects;
}

function applySubtitleSettingsWindowRoundedShape(win) {
  if (!win || win.isDestroyed() || typeof win.setShape !== 'function') return;
  try {
    const bounds = win.getBounds();
    win.setShape(buildRoundedRectShapeRects(
      bounds.width,
      bounds.height,
      SUBTITLE_SETTINGS_WINDOW_RADIUS,
    ));
  } catch (_) {}
}

function isPointInsideBounds(point, bounds, padding = 0) {
  if (!point || !bounds) return false;
  const x = Math.round(Number(point.x));
  const y = Math.round(Number(point.y));
  const left = Math.round(Number(bounds.x)) - padding;
  const top = Math.round(Number(bounds.y)) - padding;
  const right = Math.round(Number(bounds.x) + Number(bounds.width)) + padding;
  const bottom = Math.round(Number(bounds.y) + Number(bounds.height)) + padding;
  if (!Number.isFinite(x) || !Number.isFinite(y) ||
      !Number.isFinite(left) || !Number.isFinite(top) ||
      !Number.isFinite(right) || !Number.isFinite(bottom)) {
    return false;
  }
  return x >= left && x <= right && y >= top && y <= bottom;
}

function isCursorInsideSubtitleSettingsWindow(win) {
  if (!win || win.isDestroyed()) return false;
  try {
    return isPointInsideBounds(screen.getCursorScreenPoint(), win.getBounds(), 2);
  } catch (_) {
    return false;
  }
}

function isCursorInsideSubtitlePanel() {
  if (!subtitleWindow || subtitleWindow.isDestroyed()) return false;
  try {
    const bounds = subtitleWindow.getBounds();
    const panelBounds = subtitleWindow._nekoSubtitlePanelBounds || {};
    const width = Math.max(0, Math.round(Number(panelBounds.width) || bounds.width - SUBTITLE_WINDOW_EDGE_INSET * 2));
    const height = Math.max(0, Math.round(Number(panelBounds.height) || bounds.height - SUBTITLE_WINDOW_EDGE_INSET * 2));
    return isPointInsideBounds(screen.getCursorScreenPoint(), {
      x: bounds.x + SUBTITLE_WINDOW_EDGE_INSET,
      y: bounds.y + SUBTITLE_WINDOW_EDGE_INSET,
      width,
      height,
    }, 2);
  } catch (_) {
    return false;
  }
}

function clearSubtitleSettingsOutsideCloseAfterPanelBlur(win) {
  if (!win || !win._nekoSubtitleSettingsPanelBlurTimer) return;
  clearTimeout(win._nekoSubtitleSettingsPanelBlurTimer);
  win._nekoSubtitleSettingsPanelBlurTimer = null;
}

function scheduleSubtitleSettingsOutsideCloseAfterPanelBlur(win) {
  if (!win || win.isDestroyed()) return;
  clearSubtitleSettingsOutsideCloseAfterPanelBlur(win);
  const timer = setTimeout(() => {
    if (win._nekoSubtitleSettingsPanelBlurTimer === timer) {
      win._nekoSubtitleSettingsPanelBlurTimer = null;
    }
    if (subtitleSettingsWindow !== win || win.isDestroyed()) return;
    try {
      if (!win.isVisible()) return;
    } catch (_) {}
    if (isCursorInsideSubtitleSettingsWindow(win)) {
      try { win.focus(); } catch (_) {}
      return;
    }
    if (isCursorInsideSubtitlePanel()) {
      scheduleSubtitleSettingsOutsideCloseAfterPanelBlur(win);
      return;
    }
    hideSubtitleSettingsWindow('outside-blur');
  }, SUBTITLE_SETTINGS_PANEL_BLUR_RECHECK_MS);
  win._nekoSubtitleSettingsPanelBlurTimer = timer;
}

function installSubtitleSettingsOutsideClose(win) {
  if (!win || win.isDestroyed() || win._nekoSubtitleSettingsOutsideCloseInstalled) return;
  win._nekoSubtitleSettingsOutsideCloseInstalled = true;
  win.on('blur', () => {
    setTimeout(() => {
      if (subtitleSettingsWindow !== win || win.isDestroyed()) return;
      try {
        if (!win.isVisible()) return;
      } catch (_) {}
      if (isCursorInsideSubtitleSettingsWindow(win)) {
        try { win.focus(); } catch (_) {}
        return;
      }
      if (isCursorInsideSubtitlePanel()) {
        scheduleSubtitleSettingsOutsideCloseAfterPanelBlur(win);
        return;
      }
      hideSubtitleSettingsWindow('outside-blur');
    }, 0);
  });
}

function showFocusedSubtitleSettingsWindow(win) {
  if (!win || win.isDestroyed()) return;
  try {
    win.show();
    win.focus();
  } catch (_) {
    try { win.showInactive(); } catch (__) {}
  }
}

function createSubtitleSettingsWindow(baseUrl, payload = {}, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-subtitle', isPackaged);
  const bounds = getSubtitleSettingsBounds(payload && payload.anchor);
  const cfg = WINDOW_DEFAULTS.subtitleSettings;

  subtitleSettingsWindow = new BrowserWindow({
    ...cfg,
    ...bounds,
    parent: subtitleWindow && !subtitleWindow.isDestroyed() ? subtitleWindow : undefined,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      sandbox: false, // preload-subtitle.js require 相对模块（ipc-channels/preload-common），不能开 sandbox
      zoomFactor: 1.0,
      backgroundThrottling: false,
    },
  });

  applySubtitleSettingsWindowRoundedShape(subtitleSettingsWindow);
  installSubtitleSettingsOutsideClose(subtitleSettingsWindow);
  _topCoordinator?.applyTo(subtitleSettingsWindow, { kind: 'subtitle-settings', defaultLevel: 'floating' });
  protectWindowFromAltF4(subtitleSettingsWindow, 'SubtitleSettings', log, { hideOnClose: true });
  subtitleSettingsWindow.loadURL(new URL('/static/subtitle-settings.html', baseUrl).href);
  installNavigationShortcutGuard(subtitleSettingsWindow, 'SubtitleSettings', log);
  subtitleSettingsWindow.once('ready-to-show', () => {
    applySubtitleSettingsWindowRoundedShape(subtitleSettingsWindow);
    sendSubtitleSettingsState(payload && payload.state);
    showFocusedSubtitleSettingsWindow(subtitleSettingsWindow);
  });
  subtitleSettingsWindow.on('closed', () => {
    subtitleSettingsWindow = null;
  });
  log('[WindowManager] Subtitle 设置窗口已创建');
  return subtitleSettingsWindow;
}

function showSubtitleSettingsWindow(baseUrl, payload = {}, options = {}) {
  if (subtitleSettingsWindow && !subtitleSettingsWindow.isDestroyed()) {
    subtitleSettingsWindow.setBounds(getSubtitleSettingsBounds(payload && payload.anchor));
    applySubtitleSettingsWindowRoundedShape(subtitleSettingsWindow);
    if (payload && payload.state) {
      sendSubtitleSettingsState(payload.state);
    }
    showFocusedSubtitleSettingsWindow(subtitleSettingsWindow);
    return subtitleSettingsWindow;
  }
  return createSubtitleSettingsWindow(baseUrl, payload, options);
}

function notifySubtitleSettingsWindowClosed(reason) {
  const sub = subtitleWindow;
  if (!sub || sub.isDestroyed() || !sub.webContents) return;
  try {
    sub.webContents.send(SUBTITLE_CHANNELS.CLOSE_SETTINGS, {
      reason: reason || 'closed',
      panelState: reason === 'outside-blur' ? 'clean' : 'controls',
    });
  } catch (_) {}
}

function hideSubtitleSettingsWindow(reason) {
  const win = subtitleSettingsWindow;
  subtitleSettingsWindow = null;
  if (win && !win.isDestroyed()) {
    clearSubtitleSettingsOutsideCloseAfterPanelBlur(win);
    notifySubtitleSettingsWindowClosed(reason);
    try { win.hide(); } catch (_) {}
    try { win.destroy(); } catch (_) {}
  }
}

/**
 * 创建 AgentHUD 窗口
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createAgentHudWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-agenthud', isPackaged);

  // 默认位置：主屏左下角
  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const cfg = WINDOW_DEFAULTS.agentHud;

  log('[WindowManager] 创建 AgentHUD 窗口');

  const savedPos3 = loadWindowPositions();
  const hudPos = savedPos3.agentHud;

  agentHudWindow = new BrowserWindow({
    ...cfg,
    x: hudPos ? hudPos.x : wa.x + 20,
    y: hudPos ? hudPos.y : wa.y + wa.height - cfg.height - 20,
    width: hudPos ? hudPos.width : cfg.width,
    height: hudPos ? hudPos.height : cfg.height,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: true,
      sandbox: false, // preload-agenthud.js require 相对模块（ipc-channels/preload-common），不能开 sandbox
      zoomFactor: 1.0,
      backgroundThrottling: false, // 置顶子窗口不应被后台节流
    },
  });

  try {
    agentHudWindow.setIgnoreMouseEvents(false);
  } catch (_) {}

  _topCoordinator?.applyTo(agentHudWindow, { kind: 'agentHud', defaultLevel: 'floating' });
  protectWindowFromAltF4(agentHudWindow, 'AgentHUD', log, { hideOnClose: true });

  const refreshAgentHudInputShape = () => {
    applyFullWindowX11InputShape(agentHudWindow, log, 'AgentHUD');
  };
  if (isLinuxX11Runtime()) {
    agentHudWindow.once('ready-to-show', refreshAgentHudInputShape);
    agentHudWindow.on('show', refreshAgentHudInputShape);
    agentHudWindow.on('resize', refreshAgentHudInputShape);
    agentHudWindow.webContents.once('did-finish-load', () => {
      setTimeout(refreshAgentHudInputShape, 50);
    });
  }

  // 加载 AgentHUD 页面
  const hudUrl = new URL('/agenthud', baseUrl).href;
  agentHudWindow.loadURL(hudUrl);

  installNavigationShortcutGuard(agentHudWindow, 'AgentHUD', log);

  agentHudWindow.on('closed', () => {
    agentHudWindow = null;
  });

  enablePositionPersistence(agentHudWindow, 'agentHud');
  log('[WindowManager] AgentHUD 窗口已创建');
  return agentHudWindow;
}

/**
 * 创建所有应用窗口
 * @param {string} url - 后端 URL
 * @param {object} options - { isPackaged, isStreamerMode, log }
 * @returns {{ pet, chat, subtitle, agentHud }}
 */
function createAllWindows(url, options = {}) {
  const { log = console.log, autoCreateReactChat = true } = options;
  log('[WindowManager] 创建窗口, URL:', url);

  // 检查 URL 是否是 http(s)——只有这类 URL 才需要创建卫星窗口（Chat 要拼 /chat 子路径）
  // 非 http(s)（比如 about:blank、非法字符串）只建 Pet，不建卫星，避免后续 new URL('/chat', bad) 抛异常
  let baseUrlIsHttp = false;
  try {
    const u = new URL(url);
    baseUrlIsHttp = u.protocol === 'http:' || u.protocol === 'https:';
  } catch (_) { /* baseUrlIsHttp stays false */ }

  // 只先创建 Pet 窗口并加载——避免多个透明窗口并行创建 / loadURL
  // 抢占 DWM 合成层和主进程事件循环导致鼠标卡死
  const pet = createPetWindow(url, options);

  const result = { pet, chat: null, subtitle: null, agentHud: null, toast: null };

  if (!baseUrlIsHttp) {
    log('[WindowManager] URL 不是 http/https，跳过卫星窗口创建:', url);
    return result;
  }

  if (!autoCreateReactChat) {
    log('[WindowManager] React Chat 自动创建已由主进程存储闸门接管');
    return result;
  }

  // Chat 延迟到 Pet 页面加载完成后再创建+加载，
  // 避免多个透明窗口并行创建抢占 DWM 合成层和主进程事件循环
  // Toast 窗口不再启动时创建，改为按需创建/销毁（ensureToastWindow）
  const SATELLITE_LOAD_TIMEOUT = 15000;
  let satellitesCreated = false;

  const createSatellites = () => {
    if (satellitesCreated) return;
    satellitesCreated = true;
    log('[WindowManager] Pet 加载完成，开始创建卫星窗口');

    // Chat 窗口创建 + loadURL
    const chat = createReactChatWindow(url, options);
    result.chat = chat;
    if (chat && !chat.isDestroyed() && chat._deferredUrl) {
      log('[WindowManager] 开始加载 Chat 页面');
      chat.loadURL(chat._deferredUrl);

      // Chat preload 加载后通知 Pet 重新发送 WS READY
      // 解决竞态：Pet 的 WS READY 可能在 Chat preload 注册 IPC 监听前到达并丢失
      chat.webContents.once('dom-ready', () => {
        if (pet && !pet.isDestroyed()) {
          pet.webContents.send('neko:ws-trigger-ready-recheck');
        }
      });
    }
  };

  pet.webContents.once('did-finish-load', createSatellites);
  setTimeout(createSatellites, SATELLITE_LOAD_TIMEOUT); // 超时保护

  // Subtitle 和 AgentHUD 不默认创建，由开关/系统按需触发
  return result;
}

/**
 * 按需显示 Subtitle 窗口
 */
function showSubtitleWindow(url, options = {}) {
  if (subtitleWindow && !subtitleWindow.isDestroyed()) {
    subtitleWindow.show();
    return subtitleWindow;
  }
  return createSubtitleWindow(url, options);
}

function hideSubtitleWindow() {
  if (subtitleWindow && !subtitleWindow.isDestroyed()) {
    subtitleWindow._nekoPreserveSubtitleSettingsOnHide = false;
    hideSubtitleSettingsWindow();
    subtitleWindow.hide();
  }
}

/**
 * 按需显示 AgentHUD 窗口（首次调用时创建，之后 show/hide）
 */
function showAgentHudWindow(url, options = {}) {
  if (agentHudWindow && !agentHudWindow.isDestroyed()) {
    agentHudWindow.show();
    return agentHudWindow;
  }
  return createAgentHudWindow(url, options);
}

/**
 * 隐藏 AgentHUD 窗口
 */
function hideAgentHudWindow() {
  if (agentHudWindow && !agentHudWindow.isDestroyed()) {
    agentHudWindow.hide();
  }
}

// ===== Jukebox 窗口 =====

const JUKEBOX_DEFAULTS = {
  width: 560,
  height: 520,
  frame: false,
  transparent: false,
  backgroundColor: '#87CEEB',
  // alwaysOnTop 由 coordinator 管理
  skipTaskbar: false,
  resizable: true,
  fullscreenable: false,
  hasShadow: true,
  minWidth: 420,
  minHeight: 360,
};

/**
 * 创建 Jukebox 窗口
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createJukeboxWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-jukebox', isPackaged);

  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;

  log('[WindowManager] 创建 Jukebox 窗口');

  const savedPos = loadWindowPositions();
  const jbPos = savedPos.jukebox;

  jukeboxWindow = new BrowserWindow({
    ...JUKEBOX_DEFAULTS,
    x: jbPos ? jbPos.x : wa.x + wa.width - JUKEBOX_DEFAULTS.width - 40,
    y: jbPos ? jbPos.y : wa.y + wa.height - JUKEBOX_DEFAULTS.height - 40,
    width: jbPos ? jbPos.width : JUKEBOX_DEFAULTS.width,
    height: jbPos ? jbPos.height : JUKEBOX_DEFAULTS.height,
    show: false,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: false,
      sandbox: false,
      webSecurity: false,
      zoomFactor: 1.0,
      backgroundThrottling: false, // 置顶子窗口不应被后台节流
    },
  });
  try {
    jukeboxWindow.setBackgroundColor(JUKEBOX_DEFAULTS.backgroundColor);
  } catch (_) {}

  _topCoordinator?.applyTo(jukeboxWindow, { kind: 'jukebox', defaultLevel: 'floating' });
  protectWindowFromAltF4(jukeboxWindow, 'Jukebox', log, { hideOnClose: true });

  jukeboxWindow.once('ready-to-show', () => {
    if (jukeboxWindow && !jukeboxWindow.isDestroyed()) jukeboxWindow.show();
  });

  jukeboxWindow.on('hide', () => {
    saveWindowPositions();
  });

  jukeboxWindow.on('close', () => {
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send(JUKEBOX_CHANNELS.VMD_STOP, { skipIdleRestore: false });
    }
  });

  jukeboxWindow.on('closed', () => {
    jukeboxWindow = null;
  });

  // 子窗口打开行为（管理器等通过 window.open 打开的窗口）
  jukeboxWindow.webContents.setWindowOpenHandler((details) => {
    log('[WindowManager] Jukebox 子窗口打开请求:', details.url);
    // 特例：/jukebox/manager（"管理器"）显式声明 jukeboxWindow 为 parent，建立 Win32
    // owner-child 关系。OS 会自动维持 manager 永远浮在 jukebox 之上（owned window
    // is always above its owner in z-order），无需任何周期 reassertion。
    // Electron 子窗口默认 parent 是 null（不会自动以 opener 为 parent），所以这里必须
    // 显式指定，否则 owner-child 语义从未建立 → 用户激活 jukebox 时 manager 会落到下面。
    // 安全性：jukebox（transparent: false）+ manager（transparent: false）都是非透明
    // 窗口，owner-child 不会触发 Pet 那种 transparent panel 的 DWM 白屏问题。
    const isJukeboxManager = details.url.includes('jukebox/manager');
    return {
      action: 'allow',
      overrideBrowserWindowOptions: {
        frame: false,
        transparent: false,
        // alwaysOnTop 由 main.js 的 browser-window-created 钩子统一处理（跟随全局开关）
        focusable: true,
        skipTaskbar: false,
        hasShadow: true,
        // EXPERIMENT(issue #1709): 临时打开 manager 原生 resize，验证当前 Electron/Windows
        // 是否仍会触发历史上的 WS_THICKFRAME 隐形热区和"一拖就变大"问题。该提交是测试点，
        // 结果需人工回报后再决定保留、回滚或改自定义 resize。
        ...(isJukeboxManager ? {
          parent: jukeboxWindow,
          resizable: true,
          minWidth: 420,
          minHeight: 360,
        } : {}),
        webPreferences: {
          sandbox: false,
          contextIsolation: false,
          nodeIntegration: false,
          webSecurity: false,
          // manager 需要 preload 提供 window.nekoJukeboxWindow 做窗口拖动的 IPC 桥接；
          // setWindowOpenHandler 的 webPreferences 是整体替换而非合并，不会从父窗口继承 preload。
          ...(isJukeboxManager ? { preload: preloadPath } : {}),
        }
      }
    };
  });

  jukeboxWindow.webContents.on('did-create-window', (childWindow, details) => {
    const childUrl = details?.url || '';
    log('[WindowManager] Jukebox 子窗口已创建:', childUrl);
    installNavigationShortcutGuard(childWindow, 'Jukebox child', log);
    const isJukeboxManager = childUrl.includes('jukebox/manager');
    if (!isJukeboxManager) {
      // 非 manager 子窗口：解除父子关系（如有），避免被父窗口最小化等行为牵连
      try {
        const parent = childWindow.getParentWindow();
        if (parent) childWindow.setParentWindow(null);
      } catch (err) { log('[WindowManager] 解除子窗口父子关系失败:', err); }
    } else {
      log('[WindowManager] jukebox/manager 已通过 setWindowOpenHandler 的 parent 选项'
        + '建立 owner-child（OS 自动维持 manager > jukebox）');
    }
    // alwaysOnTop 由 main.js 的 browser-window-created 钩子统一处理（跟随全局开关）
    childWindow.once('ready-to-show', () => {
      try {
        childWindow.show();
        childWindow.focus();
      } catch (err) {}
    });
  });

  const jukeboxUrl = new URL('/jukebox', baseUrl).href;
  jukeboxWindow.loadURL(jukeboxUrl);

  installNavigationShortcutGuard(jukeboxWindow, 'Jukebox', log);

  enablePositionPersistence(jukeboxWindow, 'jukebox');
  log('[WindowManager] Jukebox 窗口已创建');
  return jukeboxWindow;
}

/**
 * 按需显示/创建 Jukebox 窗口
 */
function toggleJukeboxWindow(baseUrl, options = {}) {
  if (jukeboxWindow && !jukeboxWindow.isDestroyed()) {
    if (jukeboxWindow.isVisible()) {
      jukeboxWindow.hide();
    } else {
      jukeboxWindow.show();
      jukeboxWindow.focus();
    }
    return jukeboxWindow;
  }
  return createJukeboxWindow(baseUrl, options);
}

function getJukeboxWindow() {
  return jukeboxWindow;
}

// ===== Toast 窗口 =====

let toastWindow = null;

/**
 * 创建 Toast 窗口（全屏透明覆盖层，加载后端 /toast 页面）
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createToastWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-toast', isPackaged);
  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const isWayland = isLinuxWaylandRuntime();
  const isX11 = process.platform === 'linux' && !isWayland;

  log('[WindowManager] 创建 Toast 窗口');

  // 全屏透明覆盖层（所有平台统一）。
  // Wayland 穿透由 setShape([1x1]) 控制 — 不缩小窗口，
  // 否则后端 /toast 页面的绝对定位（右上角）会错位。
  const toastX = wa.x;
  const toastY = wa.y;
  const toastW = wa.width;
  const toastH = wa.height;

  toastWindow = new BrowserWindow({
    x: toastX,
    y: toastY,
    width: toastW,
    height: toastH,
    transparent: true,
    frame: false,
    thickFrame: false,
    backgroundColor: '#00000000',
    // Toast 是通知层，独立于全局置顶开关：始终保持 screen-saver（不由 coordinator 管理）
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    fullscreenable: false,
    focusable: false,
    hasShadow: false,
    show: isX11 ? false : undefined,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webSecurity: false,
      zoomFactor: 1.0,
      backgroundThrottling: false,
    },
  });

  // Toast 是通知层，独立于全局置顶开关。
  // 非 Wayland：screen-saver 级别在 Pet 窗口（floating）之上。
  // 不使用 { forward: true }：forward 模式会让 DWM 将 Toast 保留在 hit-test 链中，
  // 导致下层 Pet/Chat 窗口切换 setIgnoreMouseEvents 时 DWM 重建开销增大 → 光标闪烁。
  // Wayland：floating 级与 Pet/Chat 同层，避免遮挡；穿透由 setShape 接管。
  toastWindow.setAlwaysOnTop(true, isWayland ? 'floating' : 'screen-saver');
  const toastWindowRef = toastWindow;
  const applyLinuxX11ToastPassthrough = async (reason) => {
    if (!isX11 || !toastWindowRef || toastWindowRef.isDestroyed() || toastWindow !== toastWindowRef) return false;
    try {
      toastWindowRef.setIgnoreMouseEvents(true);
    } catch (error) {
      log('[WindowManager] X11 Toast Electron passthrough failed:', error && error.message ? error.message : error);
    }
    try {
      const display = screen.getDisplayMatching(toastWindowRef.getBounds());
      const scaleFactor = display && Number.isFinite(display.scaleFactor) ? display.scaleFactor : 1;
      const ok = await applyX11InputShape(toastWindowRef, [], {
        log,
        scaleFactor,
        allowNativeFallback: true,
      });
      if (ok) log(`[WindowManager] X11 Toast ShapeInput passthrough (${reason || 'init'})`);
      return ok;
    } catch (error) {
      log('[WindowManager] X11 Toast ShapeInput passthrough failed:', error && error.message ? error.message : error);
      return false;
    }
  };
  const scheduleLinuxX11ToastPassthrough = (reason) => {
    if (!isX11) return;
    [0, 16, 50, 120, 300, 700, 1500, 3000, 6000].forEach((delay) => {
      const timer = setTimeout(() => {
        applyLinuxX11ToastPassthrough(`${reason || 'show'}:${delay}`).catch(() => {});
      }, delay);
      try { timer.unref(); } catch (_) {}
    });
  };
  const showLinuxX11Toast = (reason) => {
    if (!isX11 || !toastWindowRef || toastWindowRef.isDestroyed() || toastWindow !== toastWindowRef) return;
    if (!toastWindowRef.isVisible()) {
      try {
        if (typeof toastWindowRef.showInactive === 'function') toastWindowRef.showInactive();
        else toastWindowRef.show();
        log(`[WindowManager] X11 Toast 显示 (${reason || 'show'})`);
      } catch (error) {
        log('[WindowManager] X11 Toast show failed:', error && error.message ? error.message : error);
      }
    }
    scheduleLinuxX11ToastPassthrough(reason || 'after-show');
  };
  if (isWayland) {
    toastWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
  } else if (isX11) {
    applyLinuxX11ToastPassthrough('before-show').then((ok) => {
      if (ok) showLinuxX11Toast('x11-shape-input-ready');
      else log('[WindowManager] X11 Toast 保持隐藏，等待原生穿透可用');
    }).catch((error) => {
      log('[WindowManager] X11 Toast initial ShapeInput failed:', error && error.message ? error.message : error);
    });
  } else {
    toastWindow.setIgnoreMouseEvents(true);
  }

  const toastUrl = new URL('/toast', baseUrl).href;
  toastWindow.loadURL(toastUrl);
  if (isX11) {
    toastWindow.webContents.once('did-finish-load', () => {
      applyLinuxX11ToastPassthrough('did-finish-load').then((ok) => {
        if (ok) showLinuxX11Toast('x11-shape-input-ready:did-finish-load');
      }).catch(() => {});
    });
  }

  toastWindow.on('closed', () => {
    toastWindow = null;
  });

  log('[WindowManager] Toast 窗口已创建');
  return toastWindow;
}

/**
 * 获取 Toast 窗口引用
 */
function getToastWindow() {
  return toastWindow;
}

// Toast 按需创建：并发调用共享同一个 Promise，did-finish-load 后才 resolve
let _toastReadyPromise = null;

/**
 * 按需获取 Toast 窗口（不存在则创建，等待页面加载完成）
 * 并发调用返回同一个 Promise，不会重复创建。
 * @param {string} baseUrl - 后端 URL
 * @param {object} options - { isPackaged, log }
 * @returns {Promise<BrowserWindow>}
 */
function ensureToastWindow(baseUrl, options = {}) {
  // 已存在且未销毁 → 直接返回
  if (toastWindow && !toastWindow.isDestroyed()) {
    return Promise.resolve(toastWindow);
  }
  // 正在创建中 → 返回同一个 Promise
  if (_toastReadyPromise) return _toastReadyPromise;

  const { log = console.log } = options;
  _toastReadyPromise = new Promise((resolve) => {
    const tw = createToastWindow(baseUrl, options);
    tw.webContents.once('did-finish-load', () => {
      log('[WindowManager] Toast 窗口加载完成');
      _toastReadyPromise = null;
      resolve(tw);
    });
    // 超时保护：3s 后无论如何 resolve（防止 /toast 加载卡死）
    setTimeout(() => {
      if (_toastReadyPromise) {
        log('[WindowManager] Toast 窗口加载超时，强制就绪');
        _toastReadyPromise = null;
        resolve(tw);
      }
    }, 3000);
  });
  return _toastReadyPromise;
}

/**
 * 销毁 Toast 窗口，释放资源
 */
function destroyToastWindow() {
  if (toastWindow && !toastWindow.isDestroyed()) {
    toastWindow.destroy();
  }
  toastWindow = null;
  _toastReadyPromise = null;
}

/**
 * 销毁所有应用窗口
 */
function destroyAllWindows() {
  // [compact-ball-removed] compactChatBallWindow 现恒为 null（球已停用），保留在销毁名单里无害
  [petWindow, chatWindow, subtitleWindow, subtitleSettingsWindow, agentHudWindow, reactChatWindow, fullChatWindow, compactChatBallWindow, jukeboxWindow, toastWindow].forEach((win) => {
    if (win && !win.isDestroyed()) {
      win._forceClose = true;
      win.destroy();
    }
  });
  petWindow = null;
  chatWindow = null;
  subtitleWindow = null;
  subtitleSettingsWindow = null;
  agentHudWindow = null;
  reactChatWindow = null;
  fullChatWindow = null;
  compactChatBallWindow = null;
  jukeboxWindow = null;
  toastWindow = null;
}

/**
 * 获取窗口引用
 */
function getWindows() {
  return {
    pet: petWindow,
    chat: reactChatWindow || chatWindow,
    // full（完整聊天窗口）独立窗口 —— 独立 key，不与 'chat'（compact）混用，避免破坏
    // top-coordinator / window-host-ipc 等按 ``win === managed.chat`` 的身份判定。
    // WS 入站路由对 full 的覆盖见 ipc-router（'chat' 路由同时投 fullChat）。
    fullChat: fullChatWindow,
    compactChatBall: compactChatBallWindow, // [compact-ball-removed] 恒为 null（球已停用）

    subtitle: subtitleWindow,
    subtitleSettings: subtitleSettingsWindow,
    agentHud: agentHudWindow,
    jukebox: jukeboxWindow,
  };
}

/**
 * 获取 Pet 窗口（兼容原 mainWindow 引用）
 */
function getPetWindow() {
  return petWindow;
}

// ===== 窗口位置持久化 =====

const POSITIONS_FILE = 'window_positions.json';

// full 聊天窗口「记忆尺寸」的下限基准：小于此视为折叠球态残留尺寸（88px），
// 既用于保存时拒绝把球尺寸写进磁盘，也用于 computeFullChatBounds 恢复时判断是否有有效记忆。
const FULL_CHAT_MIN_REMEMBERED_SIZE = 200;

// 把「记忆门槛」按窗口有效最小尺寸逐轴收敛：computeFullChatBounds 在小屏/竖屏/远程桌面
// 工作区会把 full 的有效下限压到 200 以下（min(360, wa-40)），那样合法 full 尺寸也可能 < 200。
// 若仍用固定 200 当门槛，这类合法尺寸会在保存阶段被当球态跳过、恢复阶段被当残留回退默认，
// 几何记忆失效。故门槛取 min(200, 有效最小尺寸)：正常屏恒为 200（行为不变），小屏跟随下限放低，
// 而 88px 球恒小于任何屏的有效 full 下限，仍能被正确识别为球态。
function getFullChatRememberedFloor(minWidth, minHeight) {
  const w = Math.round(Number(minWidth) || 0);
  const h = Math.round(Number(minHeight) || 0);
  return {
    width: Math.min(FULL_CHAT_MIN_REMEMBERED_SIZE, w > 0 ? w : FULL_CHAT_MIN_REMEMBERED_SIZE),
    height: Math.min(FULL_CHAT_MIN_REMEMBERED_SIZE, h > 0 ? h : FULL_CHAT_MIN_REMEMBERED_SIZE),
  };
}

function getPositionsPath() {
  return path.join(app.getPath('userData'), POSITIONS_FILE);
}

/**
 * 保存所有卫星窗口的位置和大小
 */
function saveWindowPositions() {
  // [multi-display-persist] 先读已有记录再增量更新（merge），不要用空对象重写。
  // 启动时各窗口创建有先后：reactChat 要等 Pet did-finish-load（通常 >500ms）才建，
  // 而 Pet 一创建就挂持久化，其 bounds-repair 会在 ~500ms 触发一次保存——若此刻用空对象
  // 重写，reactChat 尚不存在会被跳过，等于把它上次的所在屏记录抹掉，导致 reactChat 启动
  // 恢复永远回退主屏。merge 让暂不存在的窗口保留旧记录，也顺带修了“窗口临时销毁丢记录”。
  const positions = loadWindowPositions();
  const windows = { pet: petWindow, reactChat: reactChatWindow, fullChat: fullChatWindow, chat: chatWindow, subtitle: subtitleWindow, agentHud: agentHudWindow, jukebox: jukeboxWindow };

  for (const [name, win] of Object.entries(windows)) {
    if (win && !win.isDestroyed()) {
      if (name === 'reactChat' && (win._nekoFullSurfaceSwitchVisualParked || reactChatPositionPersistenceResumeTimer)) {
        // 切 full 时的 1x1 park 只是兼容模式临时 carrier，不能写入位置文件。
        continue;
      }
      try {
        const bounds = win.getBounds();
        // full 折叠成 88px 球时也会触发 resize/move → 走到这里。若把球尺寸写进 fullChat
        // 记录，下次启动 computeFullChatBounds 见 width/height < 阈值会当折叠残留回退默认，
        // 用户拉过的 full 尺寸就丢了。球态时改存折叠瞬间暂存的真实展开 bounds
        // （_nekoFullChatExpandedBounds，由 window-control-ipc COLLAPSE 挂上）；没有暂存就
        // 保留磁盘里已有的真实记录，绝不让球尺寸覆盖。
        if (name === 'fullChat') {
          // 门槛按窗口有效最小尺寸逐轴收敛（小屏的合法 full 可能 < 200，不能当球态丢弃）。
          const floor = getFullChatRememberedFloor(
            win._nekoFullMinSize && win._nekoFullMinSize.width,
            win._nekoFullMinSize && win._nekoFullMinSize.height
          );
          if (bounds.width < floor.width || bounds.height < floor.height) {
            const stashed = win._nekoFullChatExpandedBounds;
            if (
              stashed
              && Number(stashed.width) >= floor.width
              && Number(stashed.height) >= floor.height
            ) {
              positions[name] = { x: stashed.x, y: stashed.y, width: stashed.width, height: stashed.height };
            }
            // 否则保留 positions[name] 的旧值（不覆盖），跳过本窗口。
            continue;
          }
        }
        if (name === 'subtitle') {
          const panelBounds = win._nekoSubtitlePanelBounds;
          const panelWidth = Math.round(Number(panelBounds && panelBounds.width));
          const panelHeight = Math.round(Number(panelBounds && panelBounds.height));
          if (
            Number.isFinite(panelWidth) && panelWidth > 0 &&
            Number.isFinite(panelHeight) && panelHeight > 0
          ) {
            positions[name] = {
              x: bounds.x + SUBTITLE_WINDOW_EDGE_INSET,
              y: bounds.y + SUBTITLE_WINDOW_EDGE_INSET,
              width: panelWidth,
              height: panelHeight,
            };
            continue;
          }
        }
        positions[name] = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
      } catch (e) { /* ignore */ }
    }
  }

  try {
    fs.writeFileSync(getPositionsPath(), JSON.stringify(positions, null, 2), 'utf-8');
  } catch (e) { /* ignore */ }
}

/**
 * 加载保存的窗口位置
 * @returns {object} { chat: {x,y,w,h}, subtitle: {...}, agentHud: {...} }
 */
function loadWindowPositions() {
  try {
    const filePath = getPositionsPath();
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    }
  } catch (e) { /* ignore */ }
  return {};
}

/**
 * 为窗口设置位置保存（拖拽/resize 后自动保存）
 * 返回 pause/resume 函数用于在拖拽/resize 期间暂停事件监听，
 * 避免高频 move/resize 事件反复创建/清理 debounce timer。
 */
function enablePositionPersistence(win, name) {
  if (!win) return { pause() {}, resume() {} };
  let saveTimer = null;
  let paused = false;
  const debouncedSave = () => {
    if (paused) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveWindowPositions, 500);
  };
  win.on('move', debouncedSave);
  win.on('resize', debouncedSave);
  return {
    pause() { paused = true; if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; } },
    resume() { paused = false; debouncedSave(); },
  };
}

// [multi-display-persist] 重启后让 Pet / 对话框各自回到上次所在屏。
/**
 * 校验一份 saved bounds 的中心点是否落在某个"当前已连接"的显示器内：
 * 是则返回该 display，否则返回 null（典型：保存时所在屏已被拔掉，坐标已离屏）。
 * 既用于把窗口恢复到上次所在屏，也避免恢复到离屏的幽灵坐标。
 */
function findSavedDisplay(savedBounds) {
  if (!savedBounds) return null;
  const x = Number(savedBounds.x);
  const y = Number(savedBounds.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  const cx = x + (Number(savedBounds.width) || 0) / 2;
  const cy = y + (Number(savedBounds.height) || 0) / 2;
  let disp = null;
  try {
    disp = screen.getDisplayNearestPoint({ x: Math.round(cx), y: Math.round(cy) });
  } catch (_) { return null; }
  const b = disp && disp.bounds;
  if (!b) return null;
  // getDisplayNearestPoint 即使点离屏也会返回“最近”的 display；要求中心点真的落在该
  // display 矩形内，否则视为保存时所在屏已断开，交由调用方回退默认（主屏）。
  if (cx >= b.x && cx < b.x + b.width && cy >= b.y && cy < b.y + b.height) return disp;
  return null;
}

/**
 * Pet 窗口启动 bounds：若上次记录的所在屏仍连接，则在该屏全屏（屏幕内 off-by-one）；
 * 否则回退主屏（getAllDisplaysBounds）。实现“重启后角色模型回到上次所在屏”。
 */
function getPetStartupBounds() {
  const disp = findSavedDisplay(loadWindowPositions().pet);
  if (disp && disp.bounds) {
    const b = disp.bounds;
    // 与 getAllDisplaysBounds / getFullscreenDisplayBounds 一致的屏幕内 off-by-one。
    return {
      x: b.x + 1,
      y: b.y + 1,
      width: Math.max(1, b.width - 1),
      height: Math.max(1, b.height - 1),
    };
  }
  return getAllDisplaysBounds();
}

// ===== React Chat 窗口 =====

let reactChatWindow = null;
let reactChatAutoShowSuppressed = false;
let reactChatRestoreAfterSuppress = false;
let reactChatUserClosed = false;
let reactChatPositionPersistence = null;
let reactChatPositionPersistenceWindow = null;
let reactChatPositionPersistenceResumeTimer = null;

const REACT_CHAT_FULL_SWITCH_PARK_SIZE = 1;
const REACT_CHAT_FULL_SWITCH_REVEAL_DELAY_MS = 180;
const REACT_CHAT_FULL_SWITCH_POSITION_RESUME_DELAY_MS = 320;
const REACT_CHAT_FULL_SWITCH_BOUNDS_REASSERT_DELAYS_MS = [0, 40, 160];

// full（完整聊天窗口）独立窗口引用 —— 与 compact（reactChatWindow）绝对隔离。
// 见文件下方「Full Chat 窗口」区块。
let fullChatWindow = null;

function isLinuxWaylandRuntime() {
  if (process.platform !== 'linux') return false;
  if (process.env.NEKO_FORCE_X11 === '1') return false;
  // forceX11（--ozone-platform=x11）下走 XWayland/X11，不视为 Wayland
  if (process.argv.some((arg) => arg.indexOf('ozone-platform=x11') >= 0)) return false;
  // 必须看真实 session type；"argv 里没有 x11" 不等于 "Wayland session"
  // —— X11 session 默认也不会传 ozone-platform=x11，会被误判。
  return process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY;
}

const REACT_CHAT_DEFAULTS = {
  width: 440,   // 400 内容 + 20*2 阴影留白
  height: 600,  // 560 内容 + 20*2 阴影留白
  transparent: true,
  frame: false,
  thickFrame: false, // Windows: 必须配合 transparent 使用
  backgroundColor: '#00000000', // 显式透明背景色，防止圆角外出现黑色矩形
  // alwaysOnTop 由 coordinator 管理
  skipTaskbar: true,
  resizable: false, // Windows 下 transparent + resizable 会导致白色背景，用 JS 手动 resize
  fullscreenable: false,
  hasShadow: false,
  show: false,
};

// React Chat 子窗口处理（mini-game / 同源弹窗）：setWindowOpenHandler 决定 frame/preload/z，
// did-create-window 装导航守卫 + mini-game(soccer_demo/badminton_demo 等)的 maximize/demote。
// compact(reactChat) 与 full 独立窗口共用 —— full 复用同一聊天 UI，缺这套会让从 full 开
// mini-game/弹窗退化成无 preload-child、无 maximize/demote 的默认子窗（只在 full surface 退化）。
function installReactChatChildWindowHandlers(win, { isPackaged = false, log = console.log } = {}) {
  // mini-game 类（soccer_demo/badminton_demo 等）：frame:false 无边框 + 不 alwaysOnTop + 启动 maximize + 加载完 demote。
  const NORMAL_FRAMED_REACT_PATTERNS = ['/soccer_demo', '/badminton_demo'];
  // pathname 精确匹配（不被 query/hash 里的子串误命中）。
  const _safePathnameOf = (url) => {
    if (!url) return '';
    try { return new URL(url).pathname; } catch (_) { return ''; }
  };
  const isNormalFramedReactChild = (url) => {
    const p = _safePathnameOf(url);
    if (!p) return false;
    return NORMAL_FRAMED_REACT_PATTERNS.some((pat) => p === pat || p.startsWith(pat + '/'));
  };
  const isDeferredNavigationReactChild = (url) => !url || url === 'about:blank';

  win.webContents.setWindowOpenHandler((details) => {
    log('[WindowManager] React Chat 子窗口打开请求:', details.url);
    const normalFramed = isNormalFramedReactChild(details.url);
    const deferredNavigation = isDeferredNavigationReactChild(details.url);
    const normalFramedOptions = normalFramed
      ? getWorkAreaWindowInitialBounds(screen, win)
      : {};
    const childWebPreferences = {
      nodeIntegration: false,
      contextIsolation: false,
      sandbox: false,
      webSecurity: false,
      zoomFactor: 1.0,
      backgroundThrottling: false,
    };
    if (shouldAttachSameOriginChildPreload(win, details.url)) {
      childWebPreferences.preload = getPreloadPath('preload-child', isPackaged);
    }
    return {
      action: 'allow',
      overrideBrowserWindowOptions: {
        ...normalFramedOptions,
        frame: false,  // 全部子窗口都用 frame:false 自绘 chrome；mini-game 也不例外
        transparent: false,
        focusable: true,
        show: normalFramed || deferredNavigation ? false : undefined,
        skipTaskbar: false,
        resizable: true,
        fullscreenable: normalFramed ? true : false,
        hasShadow: true,
        alwaysOnTop: normalFramed ? false : undefined,
        webPreferences: childWebPreferences,
      },
    };
  });

  // mini-game accept 走 window.open('','_blank') 占 user-gesture 再注入真实 URL，故 details.url
  // 初次是 ''/about:blank，mini-game 分类要延后到第一次真实 navigation 才能正确 maximize/demote。
  win.webContents.on('did-create-window', (childWindow, details) => {
    const initialUrl = details?.url || '';
    const deferredNavigation = isDeferredNavigationReactChild(initialUrl);
    log('[WindowManager] React Chat 子窗口已创建:', initialUrl);
    installNavigationShortcutGuard(childWindow, 'React Chat child', log);

    let activated = false;
    let demoted = false;
    let shown = false;
    const showDeferredChildIfNotMiniGamePlaceholder = () => {
      setTimeout(() => {
        if (activated || childWindow.isDestroyed() || childWindow.isVisible()) return;
        const showChild = () => {
          if (activated || childWindow.isDestroyed() || childWindow.isVisible()) return;
          try { childWindow.show(); } catch (e) { log('[WindowManager] deferred child show 失败:', e); }
        };
        const inspectScript = `(() => {
          try {
            return {
              href: String(window.location && window.location.href || ''),
              title: String(document.title || ''),
              bodyText: String(document.body && document.body.innerText || '').slice(0, 256),
            };
          } catch (_) {
            return null;
          }
        })()`;
        try {
          childWindow.webContents.executeJavaScript(inspectScript, true).then((info) => {
            if (activated || childWindow.isDestroyed() || childWindow.isVisible()) return;
            const text = `${info && info.title ? info.title : ''}\n${info && info.bodyText ? info.bodyText : ''}`;
            const href = info && info.href ? info.href : '';
            if ((href === 'about:blank' || !href) && /Loading\s+mini-game/i.test(text)) return;
            showChild();
          }).catch(showChild);
        } catch (_) {
          showChild();
        }
      }, 0);
    };
    const activateMiniGameMode = () => {
      if (activated || childWindow.isDestroyed()) return;
      activated = true;
      log('[WindowManager] mini-game 模式激活');
      // 让全局 applyTopOn 周期重断言跳过本窗口（否则会被翻回 alwaysOnTop:true 撤销 demote）。
      try { childWindow._nekoForceNotTopMost = true; } catch (_) {}
      const applyMiniGameMinimumSize = () => {
        const targetBounds = getWorkAreaWindowInitialBounds(screen, win);
        try {
          childWindow.setMinimumSize(targetBounds.minWidth, targetBounds.minHeight);
        } catch (e) { log('[WindowManager] mini-game minimum size 失败:', e); }
      };
      const applyMiniGameBounds = () => {
        if (childWindow.isDestroyed()) return;
        try {
          const targetBounds = getWorkAreaWindowInitialBounds(screen, win);
          childWindow.setBounds({
            x: targetBounds.x,
            y: targetBounds.y,
            width: targetBounds.width,
            height: targetBounds.height,
          });
        } catch (e) { log('[WindowManager] mini-game bounds 失败:', e); }
      };
      const clearMiniGameTopMost = () => {
        if (childWindow.isDestroyed()) return;
        try {
          if (childWindow.isAlwaysOnTop()) childWindow.setAlwaysOnTop(false);
        } catch (e) {
          try { childWindow.setAlwaysOnTop(false); } catch (_) {}
        }
      };
      const doMaximize = () => {
        if (childWindow.isDestroyed()) return;
        try {
          if (!childWindow.isMaximized()) {
            applyMiniGameBounds();
            childWindow.maximize();
          }
        } catch (e) { log('[WindowManager] mini-game maximize 失败:', e); }
      };
      applyMiniGameMinimumSize();
      applyMiniGameBounds();
      if (!childWindow.isVisible()) {
        childWindow.once('ready-to-show', applyMiniGameBounds);
      }
      setTimeout(applyMiniGameBounds, 300);
      const showMiniGame = () => {
        if (shown || childWindow.isDestroyed()) return;
        shown = true;
        clearMiniGameTopMost();
        doMaximize();
        try {
          childWindow.show();
          childWindow.focus();
          demote();
        } catch (e) { log('[WindowManager] mini-game show 失败:', e); }
      };
      const demote = () => {
        if (demoted || childWindow.isDestroyed()) return;
        demoted = true;
        clearMiniGameTopMost();
        try { win.moveTop(); } catch (e) { /* ignore */ }
        try { raiseCompactChatBallWindow(); } catch (e) { /* ignore */ } // [compact-ball-removed] no-op
      };
      childWindow.once('ready-to-show', showMiniGame);
      childWindow.webContents.once('did-finish-load', showMiniGame);
      setTimeout(showMiniGame, 300);
      childWindow.webContents.once('did-finish-load', demote);
      setTimeout(demote, 600);
    };

    if (isNormalFramedReactChild(initialUrl)) {
      activateMiniGameMode();
      return;
    }
    const onNav = (_event, navUrl) => {
      if (isNormalFramedReactChild(navUrl)) {
        try { childWindow.webContents.removeListener('did-navigate', onNav); } catch (_) {}
        activateMiniGameMode();
      }
    };
    childWindow.webContents.on('did-navigate', onNav);
    if (deferredNavigation) {
      showDeferredChildIfNotMiniGamePlaceholder();
    }
  });
}

/**
 * 创建 React 版 Chat 窗口
 * 加载后端 /chat 页面（复用 N.E.K.O. 的 React Chat 组件，不维护独立代码）
 * @param {string} baseUrl - 后端 URL（如 http://localhost:48911/）
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createReactChatWindow(baseUrl, options = {}) {
  const { isPackaged = false, log = console.log } = options;

  const preloadPath = getPreloadPath('preload-chat-react', isPackaged);
  const primary = screen.getPrimaryDisplay();
  // [multi-display-persist] 重启后让对话框回到上次所在屏：用记录的 reactChat 所在屏
  // 工作区，否则回退主屏。只恢复“屏幕”，不恢复尺寸 —— compact/expanded 的屏内精确位置
  // 由渲染端各自的 localStorage 还原（恢复尺寸会触发旧版 chat 注明的“启动异常”）。
  const savedReactChatDisplay = findSavedDisplay(loadWindowPositions().reactChat);
  const wa = savedReactChatDisplay ? savedReactChatDisplay.workArea : primary.workArea;
  const allowUnverifiedWaylandSetShape = shouldAllowUnverifiedWaylandSetShape({
    allowUnverifiedWaylandSetShape: isPackaged !== true,
  }, process.env);
  const useWaylandWorkAreaCarrier = isLinuxWaylandRuntime()
    && (isWaylandSetShapePatchVerified({ process }) || allowUnverifiedWaylandSetShape);
  const reactChatInitialBounds = useWaylandWorkAreaCarrier
    ? {
        x: wa.x,
        y: wa.y,
        width: Math.max(1, Math.round(Number(wa.width) || REACT_CHAT_DEFAULTS.width)),
        height: Math.max(1, Math.round(Number(wa.height) || REACT_CHAT_DEFAULTS.height)),
      }
    : {
        x: wa.x,
        y: wa.y + wa.height - 600 - 50,
      };

  log('[WindowManager] 创建 React Chat 窗口', JSON.stringify({
    wayland: isLinuxWaylandRuntime(),
    waylandWorkAreaCarrier: useWaylandWorkAreaCarrier,
    allowUnverifiedWaylandSetShape,
  }));

  reactChatWindow = new BrowserWindow({
    ...REACT_CHAT_DEFAULTS,
    ...reactChatInitialBounds,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: false, // preload 注入的全局 stub 必须对页面 JS 可见
      sandbox: false,
      webSecurity: false,
      zoomFactor: 1.0,
      backgroundThrottling: false, // 焦点在 Pet 窗口时 Chat 不应被节流
    },
  });
  const createdReactChatWindow = reactChatWindow;

  _topCoordinator?.applyTo(reactChatWindow, { kind: 'reactChat', defaultLevel: 'floating' });
  // compact 态下独立缩小球必须始终浮于 reactChat 对话框之上才点得动。用户点击 / 激活
  // 对话框时，OS 会把它顶到同级 topmost 带最前（盖住球），且这条路径不经过渲染侧 relayout，
  // 球不会被重新 moveTop。这里在对话框获焦后补一次球 moveTop 兜底 —— 仅 compact 态有球时
  // 生效（raiseCompactChatBallWindow 内部判可见性），moveTop 不改焦点。
  //
  // 为何只兜对话框、不兜 Pet：Windows 下 Pet/对话框/球同为 screen-saver 同级，点击 Pet
  // 确会让 Pet moveTop 越过球；但 Pet 是全屏透明 + 仅模型区可交互的 input-shape 窗口
  // （setIgnoreMouseEvents(true)+forward / X11 shape），球落在模型区之外 —— Pet 即便 z 在球
  // 之上也透明（球仍可见）且在球处 click-through（点击穿透到下层的球）。真正会抢走球点击的
  // 只有对话框那块不透明可交互的 surface，故只需对话框获焦兜底，给 Pet 加兜底纯属无效 + 抖动。
  reactChatWindow.on('focus', () => {
    raiseCompactChatBallWindow(); // [compact-ball-removed] 球已停用，raise 内部判可见性后即 no-op
  });
  protectWindowFromAltF4(reactChatWindow, 'React Chat', log, { hideOnClose: true });
  reactChatWindow.setMinimumSize(320, 280);
  installNavigationShortcutGuard(reactChatWindow, 'React Chat', log);

  // Linux 下 ready-to-show 在透明窗口 + 并发创建场景（尤其 startup 时和 Pet 同时加载）
  // 不可靠，可能延迟极久或不触发 —— 用 did-finish-load 兜底，isVisible() 保护避免重复 show。
  const _showReactChatOnce = (trigger) => {
    if (reactChatWindow !== createdReactChatWindow) return;
    // 对称于 full 的 _nekoWantHidden：用户在 compact 还没加载完（isVisible() 仍 false）时就把托盘
    // 切到 full，showFullChatWindow 的「可见才 hide」是 no-op，但此处 pending 的 ready-to-show/
    // did-finish-load 仍会 show() → full+compact 同时可见。据此旗标早退，避免双聊天窗口。
    if (createdReactChatWindow._nekoWantHidden) {
      log(`[WindowManager] React Chat 显示被抑制（已切到 full）(${trigger})`);
      return;
    }
    if (reactChatUserClosed) {
      log(`[WindowManager] React Chat 显示被用户关闭状态抑制 (${trigger})`);
      return;
    }
    if (reactChatAutoShowSuppressed) {
      reactChatRestoreAfterSuppress = true;
      log(`[WindowManager] React Chat 显示被抑制 (${trigger})`);
      return;
    }
    if (!createdReactChatWindow.isDestroyed() && !createdReactChatWindow.isVisible()) {
      log(`[WindowManager] React Chat 显示 (${trigger})`);
      createdReactChatWindow.show();
    }
  };
  reactChatWindow.once('ready-to-show', () => _showReactChatOnce('ready-to-show'));
  reactChatWindow.webContents.once('did-finish-load', () => _showReactChatOnce('did-finish-load'));

  // React Chat 子窗口（mini-game / 同源弹窗）处理 —— 与 full 独立窗口共用同一套（见
  // installReactChatChildWindowHandlers）。
  installReactChatChildWindowHandlers(reactChatWindow, { isPackaged, log });
  reactChatWindow.on('closed', () => {
    hideCompactChatBallWindow(); // [compact-ball-removed] 兜底销毁历史遗留球窗口（球已停用）
    if (reactChatWindow === createdReactChatWindow) {
      clearReactChatPositionPersistenceForWindow(createdReactChatWindow);
      reactChatWindow = null;
    }
  });

  // [multi-display-persist] 记录对话框所在屏（move/resize 防抖保存），供下次启动恢复。
  // 仅用于判定“屏幕”，不在创建时回填尺寸，故不会触发旧版 chat 注明的折叠/展开启动异常。
  reactChatPositionPersistence = enablePositionPersistence(createdReactChatWindow, 'reactChat');
  reactChatPositionPersistenceWindow = createdReactChatWindow;

  // 延迟加载：不立即 loadURL，由 createAllWindows 在 Pet did-finish-load 后触发
  // 用 try/catch 包一下 new URL —— 万一 baseUrl 是非法字符串（比如用户手动改 core_config.txt 塞了乱七八糟的值）
  // 不能让 URL 构造异常把整个进程崩掉
  try {
    reactChatWindow._deferredUrl = new URL('/chat', baseUrl).href;
  } catch (e) {
    log('[WindowManager] chat URL 构造失败, baseUrl=' + baseUrl + ': ' + e.message + ' —— 跳过加载');
    reactChatWindow._deferredUrl = null;
  }

  log('[WindowManager] React Chat 窗口已创建');
  return reactChatWindow;
}

/**
 * 获取 React Chat 窗口引用
 */
function getReactChatWindow() {
  return reactChatWindow;
}

function clearReactChatPositionPersistenceForWindow(win) {
  if (!win || reactChatPositionPersistenceWindow !== win) return;
  if (reactChatPositionPersistenceResumeTimer) {
    clearTimeout(reactChatPositionPersistenceResumeTimer);
    reactChatPositionPersistenceResumeTimer = null;
  }
  reactChatPositionPersistence = null;
  reactChatPositionPersistenceWindow = null;
}

function isWindowsCompatibilityModeActive() {
  if (process.platform !== 'win32') return false;
  return process.env.NEKO_COMPATIBILITY_MODE === '1'
    || process.argv.includes('--disable-gpu-compositing')
    || process.argv.includes('--disable-direct-composition');
}

function pauseReactChatPositionPersistenceForFullSurfaceSwitch() {
  if (reactChatPositionPersistenceResumeTimer) {
    clearTimeout(reactChatPositionPersistenceResumeTimer);
    reactChatPositionPersistenceResumeTimer = null;
  }
  try { reactChatPositionPersistence?.pause?.(); } catch (_) {}
}

function resumeReactChatPositionPersistenceAfterFullSurfaceSwitch(delayMs) {
  if (!reactChatPositionPersistence) return;
  if (reactChatPositionPersistenceResumeTimer) {
    clearTimeout(reactChatPositionPersistenceResumeTimer);
  }
  const delay = Math.max(0, Math.round(Number(delayMs) || 0));
  reactChatPositionPersistenceResumeTimer = setTimeout(() => {
    reactChatPositionPersistenceResumeTimer = null;
    try {
      if (reactChatWindow && !reactChatWindow.isDestroyed()) {
        const b = reactChatWindow.getBounds();
        if (b.width <= REACT_CHAT_FULL_SWITCH_PARK_SIZE && b.height <= REACT_CHAT_FULL_SWITCH_PARK_SIZE) {
          // renderer 还没把 compact 布局撑回真实尺寸时继续等待，避免保存 1x1 park 尺寸。
          resumeReactChatPositionPersistenceAfterFullSurfaceSwitch(REACT_CHAT_FULL_SWITCH_POSITION_RESUME_DELAY_MS);
          return;
        }
      }
    } catch (_) {}
    try { reactChatPositionPersistence?.resume?.(); } catch (_) {}
  }, delay);
  try { reactChatPositionPersistenceResumeTimer.unref?.(); } catch (_) {}
}

function invalidateReactChatWindowSurface() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  try {
    if (reactChatWindow.webContents && !reactChatWindow.webContents.isDestroyed()) {
      reactChatWindow.webContents.invalidate();
      return true;
    }
  } catch (_) {}
  return false;
}

function normalizeReactChatFullSwitchBounds(bounds) {
  if (!bounds) return null;
  const x = Number(bounds.x);
  const y = Number(bounds.y);
  const width = Number(bounds.width);
  const height = Number(bounds.height);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return null;
  if (width <= REACT_CHAT_FULL_SWITCH_PARK_SIZE || height <= REACT_CHAT_FULL_SWITCH_PARK_SIZE) return null;
  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.max(1, Math.round(width)),
    height: Math.max(1, Math.round(height)),
  };
}

function setReactChatFullSwitchTinyShape() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  if (typeof reactChatWindow.setShape !== 'function') return false;
  try {
    reactChatWindow.setShape([{
      x: 0,
      y: 0,
      width: REACT_CHAT_FULL_SWITCH_PARK_SIZE,
      height: REACT_CHAT_FULL_SWITCH_PARK_SIZE,
    }]);
    reactChatWindow._nekoFullSurfaceSwitchShapeClipped = true;
    return true;
  } catch (_) {
    return false;
  }
}

function scheduleReactChatFullSwitchTinyShapeReassert() {
  if (!isWindowsCompatibilityModeActive()) return;
  [0, 40, 160].forEach((delay) => {
    const timer = setTimeout(() => {
      if (!reactChatWindow || reactChatWindow.isDestroyed()) return;
      if (!reactChatWindow._nekoWantHidden) return;
      if (!reactChatWindow._nekoFullSurfaceSwitchShapeClipped) return;
      setReactChatFullSwitchTinyShape();
      invalidateReactChatWindowSurface();
    }, delay);
    try { timer.unref?.(); } catch (_) {}
  });
}

function clipReactChatInputForFullSurfaceSwitch() {
  if (!isWindowsCompatibilityModeActive()) return false;
  // 兼容模式下 Win32 透明无边框窗口 hide 后可能留下旧输入区域；
  // 先把命中区域裁到 1x1，避免 compact 残留挡住 full 或下层窗口。
  return setReactChatFullSwitchTinyShape();
}

function restoreReactChatInputShapeAfterFullSurfaceSwitch() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  if (!reactChatWindow._nekoFullSurfaceSwitchShapeClipped) return false;
  if (typeof reactChatWindow.setShape !== 'function') {
    reactChatWindow._nekoFullSurfaceSwitchShapeClipped = false;
    return false;
  }
  try {
    const b = reactChatWindow.getBounds();
    reactChatWindow.setShape([{
      x: 0,
      y: 0,
      width: Math.max(1, Math.round(b.width || 1)),
      height: Math.max(1, Math.round(b.height || 1)),
    }]);
    reactChatWindow._nekoFullSurfaceSwitchShapeClipped = false;
    return true;
  } catch (_) {
    return false;
  }
}

function clearReactChatInputShapeAfterFullSurfaceSwitch() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  if (!reactChatWindow._nekoFullSurfaceSwitchShapeClipped) return false;
  if (typeof reactChatWindow.setShape !== 'function') {
    reactChatWindow._nekoFullSurfaceSwitchShapeClipped = false;
    return false;
  }
  try {
    // parked 状态当前 bounds 是 1x1，不能按当前 bounds 恢复；清空临时 shape，
    // 交给 compact 渲染端在 relayout 后重新提交真实命中区域。
    reactChatWindow.setShape([]);
    reactChatWindow._nekoFullSurfaceSwitchShapeClipped = false;
    return true;
  } catch (_) {
    return false;
  }
}

function parkReactChatVisualForFullSurfaceSwitch() {
  if (!isWindowsCompatibilityModeActive()) return false;
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  let bounds;
  try {
    bounds = reactChatWindow.getBounds();
  } catch (_) {
    return false;
  }
  const restoreBounds = normalizeReactChatFullSwitchBounds(bounds);
  if (restoreBounds) {
    reactChatWindow._nekoFullSurfaceSwitchRestoreBounds = restoreBounds;
  }
  pauseReactChatPositionPersistenceForFullSurfaceSwitch();
  clipReactChatInputForFullSurfaceSwitch();
  try { reactChatWindow.setMinimumSize(REACT_CHAT_FULL_SWITCH_PARK_SIZE, REACT_CHAT_FULL_SWITCH_PARK_SIZE); } catch (_) {}
  try { reactChatWindow.setOpacity(0); } catch (_) {}
  invalidateReactChatWindowSurface();
  try {
    // 兼容模式下 DWM 可能保留透明无框窗口的旧可视 backing surface。
    // hide 前先把 carrier 缩到 1x1，避免切回 compact 时旧白底大矩形被重新揭示。
    reactChatWindow.setBounds({
      x: Math.round(Number(bounds.x) || 0),
      y: Math.round(Number(bounds.y) || 0),
      width: REACT_CHAT_FULL_SWITCH_PARK_SIZE,
      height: REACT_CHAT_FULL_SWITCH_PARK_SIZE,
    });
    reactChatWindow._nekoFullSurfaceSwitchVisualParked = true;
    scheduleReactChatFullSwitchTinyShapeReassert();
    return true;
  } catch (_) {
    resumeReactChatPositionPersistenceAfterFullSurfaceSwitch(REACT_CHAT_FULL_SWITCH_POSITION_RESUME_DELAY_MS);
    return false;
  }
}

function applyReactChatFullSwitchRestoreBounds() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  const bounds = normalizeReactChatFullSwitchBounds(reactChatWindow._nekoFullSurfaceSwitchRestoreBounds);
  if (!bounds) return false;
  try {
    reactChatWindow.setBounds(bounds);
    invalidateReactChatWindowSurface();
    return true;
  } catch (_) {
    return false;
  }
}

function scheduleReactChatFullSwitchRestoreBoundsReassert() {
  if (!isWindowsCompatibilityModeActive()) return;
  REACT_CHAT_FULL_SWITCH_BOUNDS_REASSERT_DELAYS_MS.forEach((delay) => {
    const timer = setTimeout(() => {
      if (!reactChatWindow || reactChatWindow.isDestroyed()) return;
      if (!reactChatWindow._nekoFullSurfaceSwitchRestoreBounds) return;
      applyReactChatFullSwitchRestoreBounds();
    }, delay);
    try { timer.unref?.(); } catch (_) {}
  });
}

function restoreReactChatVisualAfterFullSurfaceSwitch() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  const wasParked = !!reactChatWindow._nekoFullSurfaceSwitchVisualParked;
  reactChatWindow._nekoFullSurfaceSwitchVisualParked = false;
  if (wasParked) {
    clearReactChatInputShapeAfterFullSurfaceSwitch();
    applyReactChatFullSwitchRestoreBounds();
    scheduleReactChatFullSwitchRestoreBoundsReassert();
  } else {
    restoreReactChatInputShapeAfterFullSurfaceSwitch();
  }
  if (wasParked) {
    invalidateReactChatWindowSurface();
    resumeReactChatPositionPersistenceAfterFullSurfaceSwitch(REACT_CHAT_FULL_SWITCH_POSITION_RESUME_DELAY_MS);
  }
  return wasParked;
}

function destroyReactChatWindowForFullSurfaceSwitchCore() {
  const win = reactChatWindow;
  if (!win || win.isDestroyed()) return false;
  if (!win._nekoWantHidden && !win._nekoFullSurfaceSwitchVisualParked) return false;
  try { hideCompactChatBallWindow(); } catch (_) {}
  clearReactChatPositionPersistenceForWindow(win);
  try {
    win._nekoFullSurfaceSwitchVisualParked = false;
    win._nekoFullSurfaceSwitchShapeClipped = false;
    win._nekoFullSurfaceSwitchRecreating = true;
    // 兼容模式下旧透明无框 carrier 的 DWM 表面可能已经污染；
    // 切回 compact 时直接丢弃旧 BrowserWindow，避免复用白屏/空白 backing surface。
    win.destroy();
  } catch (_) {
    return false;
  }
  if (reactChatWindow === win) reactChatWindow = null;
  return true;
}

function destroyReactChatWindowForFullSurfaceSwitch() {
  if (!isWindowsCompatibilityModeActive()) return false;
  return destroyReactChatWindowForFullSurfaceSwitchCore();
}

function hideReactChatForFullSurfaceSwitch() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  reactChatWindow._nekoWantHidden = true;
  try { hideCompactChatBallWindow(); } catch (_) {}
  if (!isWindowsCompatibilityModeActive()) {
    // 非兼容模式没有 1x1 park 需求；直接丢弃 compact carrier，
    // 避免原生 hide 失败时留下贴屏且不可交互的透明无框窗口。
    if (destroyReactChatWindowForFullSurfaceSwitchCore()) return true;
    try { reactChatWindow.hide(); } catch (_) {}
    return true;
  }
  // 切到 full 时 compact 可能正处于透明 carrier/折叠残留态。
  // 先改成穿透再隐藏，避免 Windows 透明无边框窗口短暂保留命中区域挡住下层窗口。
  try { reactChatWindow.setIgnoreMouseEvents(true, { forward: true }); } catch (_) {}
  clipReactChatInputForFullSurfaceSwitch();
  parkReactChatVisualForFullSurfaceSwitch();
  if (reactChatWindow.isVisible()) {
    try { reactChatWindow.hide(); } catch (_) {}
  }
  if (reactChatWindow.isVisible()) {
    try { reactChatWindow.setOpacity(0); } catch (_) {}
  }
  return true;
}

function setReactChatUserClosed(closed) {
  reactChatUserClosed = !!closed;
  if (reactChatUserClosed) {
    reactChatRestoreAfterSuppress = false;
  }
}

function isReactChatUserClosed() {
  return reactChatUserClosed;
}

// ===== Full Chat 窗口（独立大窗口，与 compact 绝对隔离）=====
//
// full（完整聊天窗口）是与 compact（reactChatWindow）彻底隔离的独立窗口，0 回退、
// 原样 copy、不抽象不复用。设计要点：
//   · 加载后端 /chat_full —— 该路由让 chat.html 注入 data-initial-chat-surface-mode="full"，
//     host 的 readInitialChatSurfaceMode() 据此初始即 full（优先于 electron-chat-window
//     默认 compact 与 localStorage）。
//   · preload 用 preload-chat-full.js —— b718b611(2026-05-30) 的对话框 preload 原样 copy，
//     无 compact/毛线球/surface-mode listener，永不被同步拉回 compact → 纯净 full。
//   · 独立 session 分区 FULL_CHAT_PARTITION：full 与 compact 同源（都 load localhost），
//     默认分区会共享 localStorage —— 二者都用 E_SAVED_BOUNDS_KEY
//     ('neko.reactChatWindow.electronSavedBounds') 存窗口几何，会互相覆盖（full 大窗口被
//     compact 小尺寸带回，违反 0 回退）。独立分区隔离 localStorage 根治。
//     WS 走 IPC 代理（preload 替换 window.WebSocket → ipc 中转 Pet 连接，非浏览器
//     WebSocket），不依赖 session/cookie，故分区对 WS/历史无影响。
//   · WS 入站（RAW_MESSAGE/READY 等）由 ipc-router 的 'chat' 路由同时投给 fullChat（见
//     ipc-router）；历史初次重发靠下方 dom-ready 触发 Pet 重发 READY。
//   · 窗口管理（drag/resize/collapse/expand）走 WINDOW_CONTROL_CHANNELS，主进程 handler
//     均按 event.sender 作用于发送窗口本身（「任意窗口均可使用」），full 自动正确。
const FULL_CHAT_PARTITION = 'persist:neko-full-chat';

// full 默认几何：所在屏工作区 50% 宽 × 80% 高（钳合理范围），居中。
// full 与 compact 各自独立记忆位置/尺寸（key 'fullChat'）。
function computeFullChatBounds() {
  // full shell 现以 30px inset 充满窗口（见 chat.html），所以**缩放窗口内容会跟着变大**——
  // 缩放有意义，尺寸要持久化。窗口默认 = 内容(430×860) + 阴影留白(30/边) = 490×920。
  // 阴影留白恒为 30px inset（与窗口尺寸无关），故任意尺寸下阴影都有处可落、不会截断。
  const FULL_SHADOW_MARGIN = 30;
  const DEFAULT_W = 430 + FULL_SHADOW_MARGIN * 2;  // 490
  const DEFAULT_H = 860 + FULL_SHADOW_MARGIN * 2;  // 920
  const savedBounds = loadWindowPositions().fullChat;
  const savedDisplay = findSavedDisplay(savedBounds);
  const primary = screen.getPrimaryDisplay();
  const wa = savedDisplay ? savedDisplay.workArea : primary.workArea;

  // full 的期望原生下限 = 360×360（/chat_full 的 inset 布局再小会被压坏）。但小屏/竖屏/远程桌面
  // 工作区可能放不下 360：那样 setMinimumSize(360) 会把窗口撑得超出工作区、控件够不到。故**有效下限
  // 钳到工作区**（≤ wa-40），并把它同时用作下面尺寸钳制的地板 + 存给 window-control-ipc 复用，
  // 保证创建/展开/SET_RESIZABLE 三处下限一致、永远塞得进工作区。
  const FULL_MIN_W = 360;
  const FULL_MIN_H = 360;
  const minWidth = Math.max(1, Math.min(FULL_MIN_W, wa.width - 40));
  const minHeight = Math.max(1, Math.min(FULL_MIN_H, wa.height - 40));

  // 记忆门槛按有效下限逐轴收敛（小屏的合法 full 可能 < 200，不能当折叠残留丢弃）：
  // 与 saveWindowPositions 的球态守卫共用同一规则，保存/恢复门槛对齐。88px 球恒小于任何屏的
  // 有效 full 下限，仍被正确识别为球态、回退默认。
  const rememberedFloor = getFullChatRememberedFloor(minWidth, minHeight);
  const hasRemembered = !!(
    savedBounds
    && Number(savedBounds.width) >= rememberedFloor.width
    && Number(savedBounds.height) >= rememberedFloor.height
  );

  // 尺寸：优先恢复缩放后的记忆尺寸，否则默认。**钳到工作区**，地板用上面的有效下限——不再用会
  // 反超工作区的 Math.max(560,…) 抬升：小屏/竖屏/远程桌面工作区可能比默认矮，那样会把窗口顶出屏外。
  let width = hasRemembered ? Math.round(Number(savedBounds.width)) : DEFAULT_W;
  let height = hasRemembered ? Math.round(Number(savedBounds.height)) : DEFAULT_H;
  width = Math.max(minWidth, Math.min(width, wa.width - 40));
  height = Math.max(minHeight, Math.min(height, wa.height - 40));

  // 位置：仅在记忆尺寸有效时复用 x/y —— 否则在 full 折叠成 88px 球态退出时，会把那组球坐标
  // 套到恢复出的默认大窗口上（窗口贴到球当时位置而非上次正常 full 位置）。无记忆则居中。
  let x, y;
  if (
    savedDisplay && hasRemembered
    && Number.isFinite(Number(savedBounds.x)) && Number.isFinite(Number(savedBounds.y))
  ) {
    x = Math.max(wa.x, Math.min(Math.round(Number(savedBounds.x)), wa.x + wa.width - width));
    y = Math.max(wa.y, Math.min(Math.round(Number(savedBounds.y)), wa.y + wa.height - height));
  } else {
    x = Math.round(wa.x + (wa.width - width) / 2);
    y = Math.round(wa.y + (wa.height - height) / 2);
  }
  return { x, y, width, height, minWidth, minHeight };
}

/**
 * 创建 full 独立聊天窗口（按需懒创建，加载 /chat_full）。
 * @param {string} baseUrl - 后端 URL（如 http://localhost:48911/）
 * @param {object} options - { isPackaged, log }
 * @returns {BrowserWindow}
 */
function createFullChatWindow(baseUrl, options = {}) {
  // 托盘路径可能不传 isPackaged —— 默认取 app.isPackaged，保证打包后 preload 路径正确解析。
  const { isPackaged = app.isPackaged, log = console.log } = options;
  const preloadPath = getPreloadPath('preload-chat-full', isPackaged);
  const b = computeFullChatBounds();

  log('[WindowManager] 创建 Full Chat 独立窗口');

  fullChatWindow = new BrowserWindow({
    ...REACT_CHAT_DEFAULTS,
    x: b.x,
    y: b.y,
    width: b.width,
    height: b.height,
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: false, // preload 注入的全局 stub 必须对页面 JS 可见
      sandbox: false,
      webSecurity: false,
      zoomFactor: 1.0,
      backgroundThrottling: false,
      partition: FULL_CHAT_PARTITION, // 与 compact 隔离 localStorage（几何 key 不互相覆盖）
    },
  });

  // 标记 full 窗口 + 阴影留白量，供 window-control-ipc 的回弹逻辑识别：full 的回弹「只管内容、
  // 让阴影出界无所谓」，允许窗口（含 30px 阴影留白）过冲工作区边缘这么多，内容到屏边才回弹
  // （否则窗口的阴影边一碰边就回弹 → 内容离屏边老远就被拉回）。折叠/展开仍按窗口算（含阴影）。
  fullChatWindow._nekoFullChat = true;
  fullChatWindow._nekoFullChatShadowMargin = 30;
  // 取消 pending auto-show 守卫：用户选 full 后、/chat_full 还没加载完就切回 compact 时，
  // hideFullChatWindow() 此刻是 no-op（窗口还 show:false），但稍后的 ready-to-show/did-finish-load
  // 回调仍会 show()，造成 full+compact 同时可见。下方 _showFullChatOnce 据此旗标早退。
  fullChatWindow._nekoWantHidden = false;

  // full 复用同一聊天 UI，需装与 compact 相同的子窗口处理（mini-game / 同源弹窗的 frame/preload/
  // maximize/demote），否则从 full 接 mini-game 邀请或开弹窗会退化成无管理的默认子窗。
  installReactChatChildWindowHandlers(fullChatWindow, { isPackaged, log });

  // 初始 alwaysOnTop：复用 reactChat 的受管顶层策略（win32 screen-saver / mac modal-panel）。
  // 注：top-coordinator 的周期重断言 / 防闪 / DWM-bump 走 ``win === managed.chat`` 身份判定，
  // 尚未纳入 fullChat —— 全屏游戏 z 抢占等边角场景留待实测迭代（首屏弹出与置顶已由此满足）。
  _topCoordinator?.applyTo(fullChatWindow, { kind: 'reactChat', defaultLevel: 'floating' });
  protectWindowFromAltF4(fullChatWindow, 'Full Chat', log, { hideOnClose: true });
  // 有效原生下限来自 computeFullChatBounds（已钳到工作区，≤360×360）——小屏/竖屏/远程桌面工作区
  // 放不下 360 时取更小值，避免 setMinimumSize 把窗口撑出工作区、控件够不到。存到窗口供
  // window-control-ipc 的 collapse/expand/SET_RESIZABLE 复用同一下限（三处一致）。
  const _fullMinW = Number.isFinite(Number(b.minWidth)) ? Math.round(Number(b.minWidth)) : 360;
  const _fullMinH = Number.isFinite(Number(b.minHeight)) ? Math.round(Number(b.minHeight)) : 360;
  fullChatWindow._nekoFullMinSize = { width: _fullMinW, height: _fullMinH };
  fullChatWindow.setMinimumSize(_fullMinW, _fullMinH);
  installNavigationShortcutGuard(fullChatWindow, 'Full Chat', log);

  const _showFullChatOnce = (trigger) => {
    if (fullChatWindow && fullChatWindow._nekoWantHidden) {
      log(`[WindowManager] Full Chat 显示被抑制（已切回 compact）(${trigger})`);
      return;
    }
    if (fullChatWindow && !fullChatWindow.isDestroyed() && !fullChatWindow.isVisible()) {
      log(`[WindowManager] Full Chat 显示 (${trigger})`);
      fullChatWindow.show();
    }
  };
  fullChatWindow.once('ready-to-show', () => _showFullChatOnce('ready-to-show'));
  fullChatWindow.webContents.once('did-finish-load', () => _showFullChatOnce('did-finish-load'));

  // full 是第二个聊天窗口：WS READY/历史的初次重发靠 Pet 在「chat 窗口就绪」时重发触发。
  // reactChat 在 createSatellites 里对自己做过一次；full 后创建，需自己再触发一次，让 Pet
  // 重发 READY/历史，经 ipc-router 的 'chat' 路由（已扩投 fullChat）抵达 full 窗口。
  fullChatWindow.webContents.once('dom-ready', () => {
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('neko:ws-trigger-ready-recheck');
    }
  });

  fullChatWindow.on('closed', () => {
    fullChatWindow = null;
  });

  // [multi-display-persist] 记录 full 窗口所在屏（独立 key 'fullChat'），下次启动恢复所在屏。
  enablePositionPersistence(fullChatWindow, 'fullChat');

  let fullUrl = null;
  try {
    fullUrl = new URL('/chat_full', baseUrl).href;
  } catch (e) {
    log('[WindowManager] full chat URL 构造失败, baseUrl=' + baseUrl + ': ' + e.message + ' —— 跳过加载');
  }
  if (fullUrl) {
    log('[WindowManager] 开始加载 Full Chat 页面 (/chat_full)');
    fullChatWindow.loadURL(fullUrl);
  }

  log('[WindowManager] Full Chat 窗口已创建');
  return fullChatWindow;
}

function getFullChatWindow() {
  return fullChatWindow;
}

/**
 * 托盘切「完整」：懒创建并显示 full 独立窗口，隐藏 compact（reactChat）。互斥。
 */
function showFullChatWindow(baseUrl, options = {}) {
  if (!fullChatWindow || fullChatWindow.isDestroyed()) {
    createFullChatWindow(baseUrl, options);
  } else if (!fullChatWindow.isVisible()) {
    fullChatWindow.show();
  } else {
    fullChatWindow.focus();
  }
  // 清除「想隐藏」旗标：允许 pending 的 ready-to-show 正常揭示（见 createFullChatWindow）。
  if (fullChatWindow && !fullChatWindow.isDestroyed()) fullChatWindow._nekoWantHidden = false;
  // 隐藏 compact 对话框（两态互斥，只显示一个聊天窗口）+ 清掉可能残留的毛线球独立窗口，
  // 避免切到 full 时屏上还挂着 compact 的折叠球。置 _nekoWantHidden：即便 compact 此刻还没
  // 加载完（isVisible()=false、hide() 是 no-op），也让其 pending 的 ready-to-show/did-finish-load
  // 回调早退，避免「切到 full 后 compact 又被 show 出来」造成双聊天窗口（与 full 侧对称）。
  hideReactChatForFullSurfaceSwitch();
  return fullChatWindow;
}

/**
 * 托盘切「紧凑」时隐藏 full 独立窗口。
 * 注意：显示 compact 不在这里做 —— 直接 reactChatWindow.show() 在它处于
 * 「被 hide / 毛线球 opacity-0 carrier / userClosed」等态时不会真正现身（曾导致切回
 * compact 对话框消失）。调用方（tray-menu）走可靠的 ensureReactChatWindow(forceShow)
 * 路径来揭示 compact。
 */
function hideFullChatWindow() {
  if (fullChatWindow && !fullChatWindow.isDestroyed()) {
    // 置「想隐藏」旗标：即便此刻窗口还没 show 完（pending ready-to-show），也让那个延迟回调早退，
    // 避免切回 compact 后 full 又被 show 出来造成双窗口。
    fullChatWindow._nekoWantHidden = true;
    if (fullChatWindow.isVisible()) {
      try { fullChatWindow.hide(); } catch (_) {}
    }
  }
}

// [compact-ball-removed] 死代码：原生球窗口的 bounds 归一化。球已停用（renderer 不再发 SHOW），
// 仅 hideCompactChatBallWindow 仍作兜底被调用。现在 minimized 毛线球仍复用该窗口管线。
function normalizeCompactChatBallBounds(bounds) {
  if (!bounds) return null;
  const x = Math.round(Number(bounds.x ?? bounds.left));
  const y = Math.round(Number(bounds.y ?? bounds.top));
  const width = Math.max(1, Math.round(Number(bounds.width) || COMPACT_CHAT_BALL_ANCHOR_SIZE));
  const height = Math.max(1, Math.round(Number(bounds.height) || COMPACT_CHAT_BALL_ANCHOR_SIZE));
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) return null;
  return { x, y, width, height };
}

function compactChatBallAnchorToWindowBounds(anchorBounds) {
  const normalized = normalizeCompactChatBallBounds(anchorBounds);
  if (!normalized) return null;
  return {
    x: normalized.x,
    y: normalized.y + COMPACT_CHAT_BALL_ANCHOR_OFFSET_Y,
    width: COMPACT_CHAT_BALL_WINDOW_SIZE,
    height: COMPACT_CHAT_BALL_WINDOW_SIZE,
  };
}

function getCompactChatBallVisualOffset() {
  return {
    x: COMPACT_CHAT_BALL_VISUAL_OFFSET_X,
    y: COMPACT_CHAT_BALL_VISUAL_OFFSET_Y,
    anchorOffsetY: COMPACT_CHAT_BALL_ANCHOR_OFFSET_Y,
    size: COMPACT_CHAT_BALL_VISUAL_SIZE,
    windowSize: COMPACT_CHAT_BALL_WINDOW_SIZE,
    anchorSize: COMPACT_CHAT_BALL_ANCHOR_SIZE,
  };
}

function buildCompactChatBallInputShapeRects() {
  const size = COMPACT_CHAT_BALL_VISUAL_SIZE;
  return [
    { x: 14, y: 0, width: size - 28, height: 5 },
    { x: 8, y: 5, width: size - 16, height: 7 },
    { x: 4, y: 12, width: size - 8, height: 9 },
    { x: 1, y: 21, width: size - 2, height: 17 },
    { x: 4, y: 38, width: size - 8, height: 8 },
    { x: 8, y: 46, width: size - 10, height: 6 },
    { x: 14, y: 52, width: size - 22, height: 4 },
    { x: 43, y: 50, width: size - 43, height: size - 50 },
  ];
}

function canUseCompactChatBallNativeShape() {
  return process.platform !== 'darwin'
    && compactChatBallWindow
    && !compactChatBallWindow.isDestroyed()
    && typeof compactChatBallWindow.setShape === 'function';
}

function isPointInCompactChatBallInputShape(point, bounds) {
  if (!point || !bounds) return false;
  const localX = Math.round(Number(point.x) - Number(bounds.x));
  const localY = Math.round(Number(point.y) - Number(bounds.y));
  if (!Number.isFinite(localX) || !Number.isFinite(localY)) return false;
  return buildCompactChatBallInputShapeRects().some((rect) => (
    localX >= rect.x
    && localX < rect.x + rect.width
    && localY >= rect.y
    && localY < rect.y + rect.height
  ));
}

function setCompactChatBallMacInputIgnored(ignored) {
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return;
  const nextIgnored = !!ignored;
  if (compactChatBallMacInputIgnored === nextIgnored) return;
  compactChatBallMacInputIgnored = nextIgnored;
  try {
    if (nextIgnored) {
      compactChatBallWindow.setIgnoreMouseEvents(true, { forward: true });
    } else {
      compactChatBallWindow.setIgnoreMouseEvents(false);
    }
  } catch (_) {}
}

function stopCompactChatBallMacInputFallback() {
  if (compactChatBallMacInputPollTimer) {
    clearInterval(compactChatBallMacInputPollTimer);
    compactChatBallMacInputPollTimer = null;
  }
  compactChatBallMacInputIgnored = null;
}

function startCompactChatBallMacInputFallback() {
  if (process.platform !== 'darwin') return false;
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return false;
  if (compactChatBallMacInputPollTimer) return true;

  const update = () => {
    if (!compactChatBallWindow || compactChatBallWindow.isDestroyed() || !compactChatBallWindow.isVisible()) {
      stopCompactChatBallMacInputFallback();
      return;
    }
    try {
      const point = screen.getCursorScreenPoint();
      const bounds = compactChatBallWindow.getBounds();
      setCompactChatBallMacInputIgnored(!isPointInCompactChatBallInputShape(point, bounds));
    } catch (_) {}
  };

  compactChatBallMacInputPollTimer = setInterval(update, 32);
  try { compactChatBallMacInputPollTimer.unref(); } catch (_) {}
  update();
  return true;
}

function applyCompactChatBallInputShape() {
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return false;
  if (!canUseCompactChatBallNativeShape()) {
    return startCompactChatBallMacInputFallback();
  }
  try {
    // 裁掉贴图四角的透明输入区域，避免毛球靠近小猫时透明方角拦截 Pet 拖拽。
    // 右下角保留线尾区域，不回退到内切圆裁剪，避免再次切掉线尾。
    stopCompactChatBallMacInputFallback();
    compactChatBallWindow.setShape(buildCompactChatBallInputShapeRects());
    return true;
  } catch (_) {
    return false;
  }
}

function applyCompactChatBallTemporaryHiddenState() {
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return false;
  try {
    if (compactChatBallTemporarilyHidden) {
      const useShapeOnlyTemporaryHide = isWindowsCompatibilityModeActive();
      stopCompactChatBallMacInputFallback();
      try {
        if (canUseCompactChatBallNativeShape()) {
          compactChatBallWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
          compactChatBallWindow._nekoCat1PlayTempShapeHidden = true;
        }
      } catch (_) {}
      if (!useShapeOnlyTemporaryHide) {
        try { compactChatBallWindow.setOpacity(0); } catch (_) {}
      }
      try { compactChatBallWindow.setIgnoreMouseEvents(true, { forward: true }); } catch (_) {}
      return true;
    }

    if (compactChatBallWindow._nekoCat1PlayTempShapeHidden) {
      try {
        if (typeof compactChatBallWindow.setShape === 'function'
          && compactChatBallWindow._nekoF8CompatShapeHidden !== true) {
          compactChatBallWindow.setShape([]);
        }
      } catch (_) {}
      compactChatBallWindow._nekoCat1PlayTempShapeHidden = false;
    }
    if (compactChatBallWindow._nekoF8CompatShapeHidden === true) {
      return true;
    }
    if (!isWindowsCompatibilityModeActive()) {
      try { compactChatBallWindow.setOpacity(1); } catch (_) {}
    }
    try { compactChatBallWindow.setIgnoreMouseEvents(false); } catch (_) {}
    applyCompactChatBallInputShape();
    try { compactChatBallWindow.setSkipTaskbar(true); } catch (_) {}
    if (compactChatBallWindow.isVisible()) {
      try { compactChatBallWindow.moveTop(); } catch (_) {}
    }
    return true;
  } catch (_) {
    return false;
  }
}

function setCompactChatBallTemporarilyHidden(hidden) {
  compactChatBallTemporarilyHidden = !!hidden;
  return applyCompactChatBallTemporaryHiddenState();
}

function isCompactChatBallTemporarilyHidden() {
  return !!(
    compactChatBallTemporarilyHidden
    && compactChatBallWindow
    && !compactChatBallWindow.isDestroyed()
    && compactChatBallWindow.isVisible()
  );
}

function isCompactChatBallTemporaryHideRequested() {
  return !!compactChatBallTemporarilyHidden;
}

function setReactChatSelfMinimizedBallTemporarilyHidden(hidden) {
  if (process.platform !== 'linux') return false;
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  const nextHidden = !!hidden;
  reactChatWindow._nekoCat1PlaySelfMinimizedTempHidden = nextHidden;
  try {
    if (nextHidden) {
      try {
        if (typeof reactChatWindow.setShape === 'function') {
          reactChatWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
        }
      } catch (_) {}
      try { reactChatWindow.setIgnoreMouseEvents(true, { forward: true }); } catch (_) {}
      return true;
    }
    try {
      if (typeof reactChatWindow.setShape === 'function') {
        reactChatWindow.setShape([]);
      }
    } catch (_) {}
    try { reactChatWindow.setIgnoreMouseEvents(false); } catch (_) {}
    return true;
  } catch (_) {
    return false;
  }
}

// 独立球窗口的硬编码 HTML/CSS。原 #1595 之前用于「compact 态模型旁悬浮入口」（已废），
// 现在用于「minimized 态毛线球折叠后的独立球」—— preload-compact-chat-ball.js 在
// button 上接 pointer 事件实现可拖 + 点击恢复。
function buildCompactChatBallDataUrl(baseUrl, skipAppear) {
  let bounceSpriteUrl = '/static/assets/neko-idle/chat-minimized-yarn-ball-window-bounce-1x.png';
  let bounceSpriteUrl2x = '/static/assets/neko-idle/chat-minimized-yarn-ball-window-bounce-2x.png';
  let appearSpriteUrl = '/static/assets/neko-idle/chat-minimized-yarn-ball-window-appear-1x.png';
  let appearSpriteUrl2x = '/static/assets/neko-idle/chat-minimized-yarn-ball-window-appear-2x.png';
  try {
    bounceSpriteUrl = new URL('/static/assets/neko-idle/chat-minimized-yarn-ball-window-bounce-1x.png', baseUrl).href;
    bounceSpriteUrl2x = new URL('/static/assets/neko-idle/chat-minimized-yarn-ball-window-bounce-2x.png', baseUrl).href;
    appearSpriteUrl = new URL('/static/assets/neko-idle/chat-minimized-yarn-ball-window-appear-1x.png', baseUrl).href;
    appearSpriteUrl2x = new URL('/static/assets/neko-idle/chat-minimized-yarn-ball-window-appear-2x.png', baseUrl).href;
  } catch (_) {}
  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {
  width: 100%;
  height: 100%;
  margin: 0;
  overflow: hidden;
  background: transparent;
  /* 拖动期间 pointer events 用 screenX/Y，防止浏览器把按住后的指针手势误解释为
     文本选择 / 触屏滚动 / 长按菜单等系统行为。 */
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
}
button {
  position: fixed;
  left: ${COMPACT_CHAT_BALL_VISUAL_OFFSET_X}px;
  top: ${COMPACT_CHAT_BALL_VISUAL_OFFSET_Y}px;
  width: ${COMPACT_CHAT_BALL_VISUAL_SIZE}px;
  height: ${COMPACT_CHAT_BALL_VISUAL_SIZE}px;
  padding: 0;
  border: 0;
  /* 不要 border-radius！背景图默认 background-clip: border-box，会被圆角裁成圆形 —— 这是个
     独立于 native setShape 的**第二层圆形遮罩**。毛线球贴图右下角拖着一条卷曲线尾，伸进方块
     四角、落在内切圆之外，圆角会把它切掉（静止终态就被切，与窗口尺寸/形状/动画无关）。
     #218 只删掉了 native setShape 的内切圆，漏了这层 CSS 圆 → 线尾照切。保持方角，让 58×58
     方窗内贴图四周本就 ~2px 的透明余量完整容纳线尾。 */
  border-radius: 0;
  background-color: transparent;
  background-image: -webkit-image-set(url("${bounceSpriteUrl}") 1x, url("${bounceSpriteUrl2x}") 2x);
  background-image: image-set(url("${bounceSpriteUrl}") 1x, url("${bounceSpriteUrl2x}") 2x);
  background-position: 0 0;
  background-repeat: no-repeat;
  image-rendering: auto;
  background-size: ${COMPACT_CHAT_BALL_VISUAL_SIZE * 36}px ${COMPACT_CHAT_BALL_VISUAL_SIZE}px;
  box-shadow: none;
  /* 页面加载完成前（DOMContentLoaded 添加动画 class 前）隐藏按钮，
     防止 showInactive 在 loadURL 完成前执行导致按钮以全尺寸闪现一帧。 */
  opacity: 0;
  outline: none;
  -webkit-tap-highlight-color: transparent;
  /* grab：未按下时提示「可拖」；按下时切到 grabbing 提示「拖动中」（虽然 OS 鼠标光标
     在 native 窗口拖动期间通常会被压制，这里至少在 hover/press 早期给出视觉反馈）。*/
  cursor: grab;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
}
button:active, button:focus, button:focus-visible {
  cursor: grabbing;
  border: 0;
  outline: none;
  box-shadow: none;
  background-color: transparent;
}
button:hover {
  background-color: transparent;
  outline: none;
}
/* Yarn ball bounce: pre-rendered sprite frames, no runtime PNG scale. */
@keyframes neko-ball-bounce-frames {
  from { background-position: 0 0; }
  to { background-position: -2030px 0; }
}
@keyframes neko-ball-bounce-opacity {
  0%   { opacity: 1; }
  80%  { opacity: 1; }
  100% { opacity: 0; }
}
button.neko-ball-bouncing {
  animation: neko-ball-bounce-frames 760ms steps(35, end) both, neko-ball-bounce-opacity 760ms cubic-bezier(0.33, 0.66, 0.4, 1) both;
}
/* 入场动画：固定 58×58 画布内播放预渲染放大帧，避免运行时缩放贴图。 */
@keyframes neko-ball-appear-frames {
  from { background-position: 0 0; }
  to { background-position: -1334px 0; }
}
button.neko-ball-appearing {
  background-image: -webkit-image-set(url("${appearSpriteUrl}") 1x, url("${appearSpriteUrl2x}") 2x);
  background-image: image-set(url("${appearSpriteUrl}") 1x, url("${appearSpriteUrl2x}") 2x);
  background-size: ${COMPACT_CHAT_BALL_VISUAL_SIZE * 24}px ${COMPACT_CHAT_BALL_VISUAL_SIZE}px;
  animation: neko-ball-appear-frames 380ms steps(23, end) both;
  opacity: 1;
}
</style>
</head>
<body>
<button type="button" data-compact-chat-ball aria-label="最小化聊天框"></button>
${skipAppear ? '<script>window.__nekoSkipAppear=true</script>' : ''}
</body>
</html>`;
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}

// [compact-ball-removed] 死代码：创建/更新原生球窗口。renderer 已不再发 SHOW，故不会被触达。
function showCompactChatBallWindow(baseUrl, bounds, options = {}) {
  const { isPackaged = false, log = console.log, compatRecreate = false } = options;
  if (reactChatUserClosed) {
    log('[WindowManager] Compact Chat Ball 显示被用户关闭状态抑制');
    return null;
  }
  const anchorBounds = normalizeCompactChatBallBounds(bounds);
  const windowBounds = compactChatBallAnchorToWindowBounds(anchorBounds);
  if (!anchorBounds || !windowBounds) return null;

  // 新一次球会话开始（含本模块内部复用 showInactive / 兼容模式 destroy+recreate / main 折叠接管）：
  // 清掉 main 侧 DRAG 起始尺寸缓存。所有 show 必经本函数，故这里是覆盖全部收/开球路径的兜底重置点，
  // 避免上次会话被 DPI 取整 / 载体化的陈旧尺寸在新会话首帧拖动时写回新球 + 载体。
  if (typeof compactChatBallDragSizesResetListener === 'function') {
    try { compactChatBallDragSizesResetListener(); } catch (_) {}
  }

  const creating = !compactChatBallWindow || compactChatBallWindow.isDestroyed();
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) {
    compactChatBallWindow = new BrowserWindow({
      x: windowBounds.x,
      y: windowBounds.y,
      width: windowBounds.width,
      height: windowBounds.height,
      transparent: true,
      frame: false,
      thickFrame: false,
      backgroundColor: '#00000000',
      skipTaskbar: true,
      resizable: false,
      fullscreenable: false,
      // focusable:true + closable:false —— 修「焦点在别的应用时首次点球被吞」：
      // 球若 focusable:false(WS_EX_NOACTIVATE)，当前台焦点在别的进程时，点球的第一个
      // pointerdown 会被 Windows 吞去激活下层窗口、球只收到 pointerup → 这次点击丢失、球
      // 「点不动」（renderer 收不到 down，preload-compact-chat-ball.js 的 endPointer 无配对
      // dragState 直接 return）。此前仅 F8 还原路径 reassertCompactChatBallTopForRestore 临时
      // setFocusable(true) 修过，日常「从别的应用切回来点球」同样中招却漏修。改为常驻
      // focusable:true，球可被点击激活、直接收下首次按下。原 focusable:false 的两个顾虑都已消解：
      //   ① Alt+F4 销毁球 → closable:false 挡掉（系统/Alt+F4 关不掉，程序 win.destroy() 不受
      //      closable 影响，正常 HIDE 仍 destroy）。注：旧注释提的 desktopCompactBallWindowSnapshot
      //      去重是已停用的悬浮球 SHOW 路径的事，新球走 COLLAPSE_TAKEOVER 每次直接重建，本不受影响。
      //   ② 抢焦：球 showInactive 出现时不抢焦，仅点击时短暂抢焦 → 紧接着展开对话框获焦，合理。
      focusable: true,
      closable: false,
      hasShadow: false,
      show: false,
      webPreferences: {
        preload: getPreloadPath('preload-compact-chat-ball', isPackaged),
        nodeIntegration: false,
        contextIsolation: false,
        sandbox: false,
        webSecurity: false,
        zoomFactor: 1.0,
        backgroundThrottling: false,
      },
    });
    _topCoordinator?.applyTo(compactChatBallWindow, { kind: 'reactChat', defaultLevel: 'floating' });
    const createdWindow = compactChatBallWindow;
    compactChatBallWindow.on('closed', () => {
      stopCompactChatBallMacInputFallback();
      if (compactChatBallWindow === createdWindow) {
        compactChatBallWindow = null;
      }
    });
    compactChatBallWindow.loadURL(buildCompactChatBallDataUrl(baseUrl, compatRecreate && isWindowsCompatibilityModeActive()));
    log('[WindowManager] Compact Chat Ball created:', JSON.stringify({
      platform: process.platform,
      winId: compactChatBallWindow.id,
      anchorBounds,
      windowBounds,
    }));

    // 兼容模式重建：transparent 窗口在软件合成下 showInactive 后会闪一帧白色。
    // 用 setShape(1x1) 把窗口裁到不可见，等 preload 的 APPEAR_DONE（appear 动画结束、
    // opacity:1 已设）后再 setShape([]) 揭示，避免白闪。
    if (compatRecreate && isWindowsCompatibilityModeActive()) {
      try {
        compactChatBallWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
        compactChatBallWindow._nekoF8CompatShapeHidden = true;
      } catch (_) {}
      const wc = compactChatBallWindow.webContents;
      if (wc && !wc.isDestroyed()) {
        const onAppearDone = (event) => {
          if (event.sender !== wc) return;
          try { ipcMain.removeListener(COMPACT_CHAT_BALL_CHANNELS.APPEAR_DONE, onAppearDone); } catch (_) {}
          try { wc.removeListener('render-process-gone', cleanup); } catch (_) {}
          if (compactChatBallWindow && !compactChatBallWindow.isDestroyed()) {
            compactChatBallWindow._nekoF8CompatShapeHidden = false;
            // 窗口内容已就绪（PNG 已解码、opacity:1 已设），一次性完成揭示：
            // showInactive → shape → skipTaskbar → moveTop
            compactChatBallWindow.setIgnoreMouseEvents(false);
            compactChatBallWindow.showInactive();
            applyCompactChatBallInputShape();
            compactChatBallWindow.moveTop();
            try { compactChatBallWindow.setSkipTaskbar(true); } catch (_) {}
            applyCompactChatBallTemporaryHiddenState();
            notifyCompactChatBallReady('compact-ball-appear-done', compactChatBallWindow);
          }
          log('[WindowManager] Compact Chat Ball compat recreate APPEAR_DONE, shape cleared');
        };
        const cleanup = () => {
          try { ipcMain.removeListener(COMPACT_CHAT_BALL_CHANNELS.APPEAR_DONE, onAppearDone); } catch (_) {}
          try { wc.removeListener('render-process-gone', cleanup); } catch (_) {}
        };
        ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.APPEAR_DONE, onAppearDone);
        wc.on('render-process-gone', cleanup);
        createdWindow.on('closed', cleanup);
      }
    }
  }

  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return null;
  try {
    _topCoordinator?.applyTo(compactChatBallWindow, { kind: 'reactChat', defaultLevel: 'floating' });
    const wasVisible = compactChatBallWindow.isVisible();
    compactChatBallWindow.setBounds(windowBounds);
    const _compatDeferShow = compatRecreate && isWindowsCompatibilityModeActive();
    // compatRecreate 路径：窗口从创建到 APPEAR_DONE 之间完全不 show，
    // 避免软件合成下任何形态的白闪。showInactive / shape / moveTop 都在 APPEAR_DONE 里做。
    if (!_compatDeferShow) {
      compactChatBallWindow.setIgnoreMouseEvents(false);
      if (!compactChatBallWindow.isVisible()) compactChatBallWindow.showInactive();
      applyCompactChatBallInputShape();
      try { compactChatBallWindow.setSkipTaskbar(true); } catch (_) {}
      compactChatBallWindow.moveTop();
    }
    applyCompactChatBallTemporaryHiddenState();
    // 窗口复用（macOS hide/show、非首次创建）：发 reappear 让 preload 重播入场动画。
    // 避免球以全尺寸无动画直接出现（视觉闪帧）。首次创建由 DOMContentLoaded 触发动画。
    if (!creating && !wasVisible && compactChatBallWindow.webContents) {
      try { compactChatBallWindow.webContents.send('neko:ball-reappear'); } catch (_) {}
    }
    if (creating || !wasVisible) {
      log('[WindowManager] Compact Chat Ball show:', JSON.stringify({
        platform: process.platform,
        winId: compactChatBallWindow.id,
        creating,
        visible: compactChatBallWindow.isVisible(),
        bounds: compactChatBallWindow.getBounds(),
        anchorBounds,
      }));
    }
  } catch (error) {
    log('[WindowManager] Compact Chat Ball 更新失败:', error);
  }
  return compactChatBallWindow;
}

// compact relayout 路径会反复对 reactChat 对话框 bringToFront(moveTop)，而对话框与球
// 同处 Windows screen-saver 同级 topmost 带 —— 对话框上浮就会盖住球。渲染侧 SHOW 按
// 位置去重，球位置不变时不会重发 SHOW，导致球的 moveTop 被抑制、稳态下永久被对话框盖住、
// 点不动。这里提供一条**不被去重挡掉**的 raise 通道：仅 moveTop（不动 bounds、不抢焦），
// 由渲染侧在对话框上浮后 / 主进程在对话框获焦后调用，保证 compact 态球始终浮于对话框之上。
// [compact-ball-removed] 死代码：球永不创建，compactChatBallWindow 恒为 null，提前 return。
function raiseCompactChatBallWindow() {
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) return;
  try {
    if (!compactChatBallWindow.isVisible()) return;
    compactChatBallWindow.moveTop();
  } catch (_) {}
}

// hide-all（F8）还原球态专用的完整重置顶 + 可激活化。F8 还原期多个窗口重新 show、z 会重排
// （pet/carrier 与球同为 screen-saver 级），仅 moveTop 易被压下去。这里复刻正常球态的可交互状态，做两件事：
//   - setFocusable(true)：幂等重断言球可激活（球已常驻 focusable:true，见函数内注释 / 创建处）。
//   - _topCoordinator.applyTo（setAlwaysOnTop screen-saver 重断言 = SetWindowPos HWND_TOPMOST）
//     + setIgnoreMouseEvents(false) + moveTop：把球真正钉到同级顶、确保接收鼠标。
// 配合 hotkey 侧初次 + 多次延迟调用，覆盖还原期各窗口 show 造成的 z 扰动窗口期。
function reassertCompactChatBallTopForRestore(opts) {
  if (!compactChatBallWindow || compactChatBallWindow.isDestroyed()) {
    return false;
  }
  try {
    if (compactChatBallWindow._nekoF8CompatShapeHidden && opts && opts.recreateBaseUrl) {
      const savedBounds = compactChatBallWindow.getBounds();

      // 销毁旧窗口（closed handler 会清空 compactChatBallWindow 引用）
      try { compactChatBallWindow.destroy(); } catch (_) {}
      compactChatBallWindow = null;

      const anchorBounds = {
        x: savedBounds.x,
        y: savedBounds.y - (COMPACT_CHAT_BALL_ANCHOR_OFFSET_Y || 30),
        width: COMPACT_CHAT_BALL_ANCHOR_SIZE || 88,
        height: COMPACT_CHAT_BALL_ANCHOR_SIZE || 88,
      };
      showCompactChatBallWindow(
        opts.recreateBaseUrl,
        anchorBounds,
        { isPackaged: opts.isPackaged, log: console.log, compatRecreate: true },
      );

      // _nekoF8CompatShapeHidden 由 APPEAR_DONE handler 清除。
      // 兼容模式下每次 reassert 都 destroy+recreate：setShape([]) 在软件合成下
      // 可能丢失 background-image 纹理，recreate 保证每次都是全新窗口。
      return !!compactChatBallWindow;
    }

    try { compactChatBallWindow.setFocusable(true); } catch (_) {}
    _topCoordinator?.applyTo(compactChatBallWindow, { kind: 'reactChat', defaultLevel: 'floating' });
    let wasShapeHidden = false;
    if (compactChatBallWindow._nekoF8CompatShapeHidden) {
      try {
        if (typeof compactChatBallWindow.setShape === 'function') {
          compactChatBallWindow.setShape([]);
        }
      } catch (_) {}
      compactChatBallWindow._nekoF8CompatShapeHidden = false;
      wasShapeHidden = true;
    }
    try { compactChatBallWindow.setIgnoreMouseEvents(false); } catch (_) {}
    applyCompactChatBallInputShape();
    const wasHidden = !compactChatBallWindow.isVisible();
    if (wasHidden) {
      try { compactChatBallWindow.showInactive(); } catch (_) {}
    }
    // showInactive 后重新断言 skipTaskbar，防止 focusable:true 窗口出现在任务栏
    try { compactChatBallWindow.setSkipTaskbar(true); } catch (_) {}
    compactChatBallWindow.moveTop();
    applyCompactChatBallTemporaryHiddenState();
    if (wasShapeHidden || wasHidden) {
      try {
        const wc = compactChatBallWindow.webContents;
        if (wc && !wc.isDestroyed()) {
          wc.invalidate();
          wc.send('neko:ball-reappear');
        }
      } catch (_) {}
    }
    return true;
  } catch (_) {
    return false;
  }
}

// [compact-ball-removed] 现为 no-op 兜底：球已停用，但保留以销毁任何历史遗留的球窗口。
function hideCompactChatBallWindow() {
  stopCompactChatBallMacInputFallback();
  if (compactChatBallWindow && !compactChatBallWindow.isDestroyed()) {
    const win = compactChatBallWindow;
    if (process.platform === 'win32') {
      compactChatBallWindow = null;
      try {
        // 本函数不收 log 参数、模块作用域也无 log 绑定 —— 原 log(...) 调用恒抛 ReferenceError
        // 被 catch 吞掉（destroy 仍会执行，但调试日志永远丢失）。改用 console.log 修掉这个哑日志。
        console.log('[WindowManager] Compact Chat Ball destroy on hide:', JSON.stringify({
          platform: process.platform,
          winId: win.id,
          bounds: win.getBounds(),
        }));
      } catch (_) {}
      win.destroy();
      return;
    }
    compactChatBallWindow.hide();
  }
}

function setReactChatAutoShowSuppressed(suppressed) {
  const nextSuppressed = !!suppressed;
  if (nextSuppressed) {
    reactChatAutoShowSuppressed = true;
    if (reactChatWindow && !reactChatWindow.isDestroyed() && reactChatWindow.isVisible()) {
      reactChatRestoreAfterSuppress = true;
      reactChatWindow.hide();
    }
    return;
  }

  reactChatAutoShowSuppressed = false;
  if (reactChatRestoreAfterSuppress) {
    reactChatRestoreAfterSuppress = false;
    if (!reactChatUserClosed && reactChatWindow && !reactChatWindow.isDestroyed() && !reactChatWindow.isVisible()) {
      reactChatWindow.show();
    }
  }
}

function isReactChatAutoShowSuppressed() {
  return reactChatAutoShowSuppressed;
}

function isCompactChatBallActive() {
  return !!(compactChatBallWindow && !compactChatBallWindow.isDestroyed() && compactChatBallWindow.isVisible());
}

function isReactChatMinimizedCarrierWindow(win) {
  return process.platform !== 'linux'
    && !!win
    && !win.isDestroyed()
    && !!reactChatWindow
    && !reactChatWindow.isDestroyed()
    && win.id === reactChatWindow.id
    && isCompactChatBallActive();
}

function ensureReactChatMinimizedCarrierMousePassthrough() {
  if (!isReactChatMinimizedCarrierWindow(reactChatWindow)) return false;
  try {
    // 球态下 chatWin 只是透明定位载体，必须整窗穿透，避免透明区域拦截桌面点击。
    reactChatWindow.setIgnoreMouseEvents(true);
    return true;
  } catch (_) {
    return false;
  }
}

// 球态拖动跟随时，DRAG_MOVE/DRAG_END 每帧用 setBounds 把透明载体 chatWin 跟到球位置。
// 兼容模式下载体靠 setShape([1x1]) 隐性（#205：setOpacity 在 disable-gpu-compositing 下失效）。
// 但 Win32 的窗口区域(SetWindowRgn)会随 setBounds 的 SetWindowPos 失效——1x1 裁剪被清掉后，
// 全尺寸透明载体随拖动显形，表现为「拖球时窗口自动扩大且透明」。因此每次跟随 setBounds 之后
// 必须重打 1x1 裁剪。非兼容模式用 setOpacity(0)，不受 setBounds 影响，故只在 setShape 隐性时放行。
function reassertReactChatMinimizedCarrierDim() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  if (process.platform === 'linux') return false;
  if (!reactChatWindow._nekoCompatDimmedByShape) return false;
  try {
    if (typeof reactChatWindow.setShape === 'function') {
      reactChatWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
    }
    return true;
  } catch (_) {
    return false;
  }
}

// ===== minimized 态独立球折叠：Win32 对话框窗口透明化 =====
// 设计取舍 —— 为什么不用 hide() 而用 setOpacity(0)：
//   1. Win32 透明无框窗口 hide 后 setBounds 不被 DWM 合成 —— SetWindowPos 改了
//      internal rect 但下次 show 时 OS 用 cached rect 渲染。导致拖球时同步 setBounds
//      chatWin 表面成功（getBounds 能读到目标值）但 show 后窗口实际不在目标位置 ——
//      W.expand 用 current bounds 做左下角对齐就错位。
//   2. setOpacity(0) 让 chatWin 视觉上完全消失但 visibility 保持 true。setBounds 在
//      visible 透明窗口上是 SetWindowPos + DWM 合成层正常更新，绝对可靠。
//   3. 球独立 BrowserWindow 用 moveTop 顶在 chatWin 之上 —— 用户的 pointer 事件落在
//      球上，不会穿到下面的 chatWin。chatWin 接收不到误触。
//
// 不修改 reactChatUserClosed / reactChatAutoShowSuppressed 任一标志 —— 这两个状态机
// 与「毛线球折叠」是独立路径，互不干扰。
//
function isWindowsCompatibilityModeActive() {
  if (process.platform !== 'win32') return false;
  return process.env.NEKO_COMPATIBILITY_MODE === '1'
    || process.argv.includes('--disable-gpu-compositing')
    || process.argv.includes('--disable-direct-composition');
}

// Linux 不走本路径：Electron setOpacity() 在 Linux 上是 no-op。Linux 由 renderer 保留
// chat BrowserWindow 自身作为 88x88 折叠球，不创建外部球、不透明化 carrier。
// 兼容模式下 setOpacity(0→1) 在 transparent:true + disable-gpu-compositing 窗口上
// 触发 Win32 DWM 层的 bug：SetLayeredWindowAttributes(LWA_ALPHA) 与 Chromium
// DirectComposition visual tree 冲突，setOpacity(1) 后窗口表面仍不可见（但
// 渲染器正常、可交互）。修复：兼容模式下不使用 setOpacity，改为 setShape
// 把可视区域裁到 1x1 像素——窗口留在原位，W.getBounds 读位置不受影响，用户看不到 1x1 像素。
// 注意：DRAG_MOVE/DRAG_END 跟随用的 setBounds 会清掉该 1x1 裁剪（Win32 窗口区域随 resize 失效），
// 拖动链路必须在每次 setBounds 后调 reassertReactChatMinimizedCarrierDim() 重打，否则载体显形。
// 正常模式照旧用 setOpacity(0)（不受 setBounds 影响）。
function dimReactChatForMinimize() {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  if (process.platform === 'linux') return true;
  try {
    if (isWindowsCompatibilityModeActive()) {
      try {
        if (typeof reactChatWindow.setShape === 'function') {
          reactChatWindow.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
          reactChatWindow._nekoCompatDimmedByShape = true;
        }
      } catch (_) {}
    } else {
      reactChatWindow.setOpacity(0);
    }
    try { reactChatWindow.setIgnoreMouseEvents(true); } catch (_) { /* ignore */ }
    return true;
  } catch (_) {
    return false;
  }
}

// opts.keepHidden: true 时只回滚 opacity、**不** show —— 用于「折叠因用户主动关闭对话框而
// 中止」的回滚：既要把 PRE_COLLAPSE_DIM 设的 opacity 0 复位（否则下次开窗是透明的），又不能
// 把用户刚关掉的窗口重新显示出来。
function restoreReactChatVisibilityFromMinimize(opts) {
  if (!reactChatWindow || reactChatWindow.isDestroyed()) return false;
  try {
    if (isWindowsCompatibilityModeActive()) {
      // setShape 只改裁剪区域，不碰透明度，不存在 setOpacity 切换瞬间的陈帧问题，无需 invalidate。
      // shape 裁剪必须无条件恢复——keepHidden 只阻止 show，但如果 shape 残留 1x1 裁剪，
      // 后续 F8 强制显示 / showWithFadeIn 等路径不会再调 restore，窗口会停留在不可见的 1x1 状态。
      if (reactChatWindow._nekoCompatDimmedByShape) {
        try {
          if (typeof reactChatWindow.setShape === 'function') {
            // setShape([]) 清除裁剪，窗口恢复为正常矩形。
            // 不用 setShape([{全尺寸矩形}])——后续 resize 超出该矩形会被裁掉。
            reactChatWindow.setShape([]);
          }
        } catch (_) {}
        reactChatWindow._nekoCompatDimmedByShape = false;
      }
    } else {
      reactChatWindow.setOpacity(1);
      try {
        if (process.platform === 'win32'
          && reactChatWindow.webContents
          && !reactChatWindow.webContents.isDestroyed()) {
          reactChatWindow.webContents.invalidate();
        }
      } catch (_) { /* ignore */ }
    }
    try { reactChatWindow.setIgnoreMouseEvents(false); } catch (_) { /* ignore */ }
    if (!(opts && opts.keepHidden) && !reactChatWindow.isVisible()) reactChatWindow.showInactive();
    return true;
  } catch (_) {
    return false;
  }
}

/**
 * 获取 Subtitle 窗口引用（可能为 null —— 按需惰性创建）
 */
function getSubtitleWindow() {
  return subtitleWindow;
}

/**
 * 获取 AgentHud 窗口引用（可能为 null —— 按需惰性创建）
 */
function getAgentHudWindow() {
  return agentHudWindow;
}

module.exports = {
  createPetWindow,
  createChatWindow,
  createSubtitleWindow,
  createAgentHudWindow,
  createReactChatWindow,
  // full（完整聊天窗口）独立窗口管线 —— 托盘「完整/紧凑」切换调用，与 compact 绝对隔离
  FULL_CHAT_PARTITION,
  createFullChatWindow,
  getFullChatWindow,
  showFullChatWindow,
  hideFullChatWindow,
  // minimized 态毛线球折叠的独立球窗口管线 —— main.js IPC handler 调用
  showCompactChatBallWindow,
  hideCompactChatBallWindow,
  setCompactChatBallTemporarilyHidden,
  isCompactChatBallTemporarilyHidden,
  isCompactChatBallTemporaryHideRequested,
  setReactChatSelfMinimizedBallTemporarilyHidden,
  setCompactChatBallDragSizesReset,
  setCompactChatBallReadyListener,
  raiseCompactChatBallWindow,
  reassertCompactChatBallTopForRestore,
  getCompactChatBallVisualOffset,
  isReactChatMinimizedCarrierWindow,
  ensureReactChatMinimizedCarrierMousePassthrough,
  reassertReactChatMinimizedCarrierDim,
  // minimized 态对话框窗口透明化（毛线球折叠/球点击恢复专用，setOpacity 而非 hide）
  dimReactChatForMinimize,
  restoreReactChatVisibilityFromMinimize,
  createJukeboxWindow,
  toggleJukeboxWindow,
  getJukeboxWindow,
  createToastWindow,
  ensureToastWindow,
  destroyToastWindow,
  createAllWindows,
  destroyAllWindows,
  getWindows,
  getPetWindow,
  getReactChatWindow,
  restoreReactChatInputShapeAfterFullSurfaceSwitch,
  restoreReactChatVisualAfterFullSurfaceSwitch,
  destroyReactChatWindowForFullSurfaceSwitch,
  setReactChatUserClosed,
  isReactChatUserClosed,
  setReactChatAutoShowSuppressed,
  isReactChatAutoShowSuppressed,
  getSubtitleWindow,
  showSubtitleSettingsWindow,
  hideSubtitleSettingsWindow,
  sendSubtitleSettingsState,
  getAgentHudWindow,
  getToastWindow,
  getAllDisplaysBounds,
  getPreloadPath,
  showSubtitleWindow,
  hideSubtitleWindow,
  showAgentHudWindow,
  hideAgentHudWindow,
  saveWindowPositions,
  loadWindowPositions,
  enablePositionPersistence,
  REACT_CHAT_FULL_SWITCH_REVEAL_DELAY_MS,
  installNavigationShortcutGuard,
  isLinuxWaylandRuntime,
  WINDOW_DEFAULTS,
  setTopCoordinator,
};
