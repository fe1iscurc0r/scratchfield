'use strict';

const { isTrustedSender } = require('./utils/trust-guard');

const {
  SUBTITLE_WINDOW_EDGE_INSET,
  SUBTITLE_PANEL_MIN_WIDTH,
  SUBTITLE_PANEL_MIN_HEIGHT,
  SUBTITLE_WINDOW_MIN_WIDTH,
  SUBTITLE_WINDOW_MIN_HEIGHT,
} = require('../subtitle-window-constants');
const { getLinuxInputRegionBackend } = require('./wayland-input-region-backend');

function createWindowControlIpc(context) {
  const {
    BrowserWindow,
    allowUnverifiedWaylandSetShape,
    ipcMain,
    log,
    screen,
    WINDOW_CONTROL_CHANNELS,
    PET_CHANNELS,
    applyTopOn,
    getMainWindow,
    isLinuxWaylandRuntime,
    windowManager,
  } = context;

  function getMainWindowRef() {
    return getMainWindow();
  }

  // full 独立窗口的有效最小尺寸。期望下限是 360×360，但在小屏/竖屏/远程桌面工作区可能放不下——
  // 那样 setMinimumSize 会把窗口撑得超出工作区、控件够不到。createFullChatWindow 在创建时把
  // 「工作区适配后的下限」存到 win._nekoFullMinSize，这里优先读它，缺失才回退 360（与创建侧一致）。
  function fullChatMinSize(win) {
    const m = win && win._nekoFullMinSize;
    const w = m && Number.isFinite(Number(m.width)) ? Math.round(Number(m.width)) : 360;
    const h = m && Number.isFinite(Number(m.height)) ? Math.round(Number(m.height)) : 360;
    return { width: w, height: h };
  }

function shouldUseNativeIgnoreMouse(win) {
  if (!win || win.isDestroyed()) return false;

  // Wayland 下 setIgnoreMouseEvents 对所有窗口都不生效，
  // 穿透统一由 setShape 方案接管（Pet 在 preload-pet.js，Toast 在主进程 IPC 回退）。
  if (isLinuxWaylandRuntime()) return false;

  return true;
}

function canUseSetShape(win) {
  return getInputRegionBackend(win).canUseSetShape === true;
}

function getInputRegionBackend(win) {
  return getLinuxInputRegionBackend({
    win,
    isLinuxWaylandRuntime,
    allowUnverifiedWaylandSetShape,
    process,
  });
}

// ===== 全局快捷键配置 =====
ipcMain.handle('lanlan:pointer-snapshot', (event) => {
  if (!isTrustedSender(event)) {
    return { cursor: null, bounds: null };
  }
  const cursor = screen.getCursorScreenPoint();
  if (!getMainWindowRef() || getMainWindowRef().isDestroyed()) {
    return { cursor, bounds: null };
  }
  try {
    const bounds = getMainWindowRef().getBounds();
    return { cursor, bounds };
  } catch (err) {
    log('获取窗口坐标失败:', err.message);
    return { cursor, bounds: null };
  }
});

// ===== 通用窗口控制（任意窗口均可使用）=====
ipcMain.handle(WINDOW_CONTROL_CHANNELS.GET_BOUNDS, (event) => {
  if (!isTrustedSender(event)) return null;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return null;
  return win.getBounds();
});

ipcMain.handle(WINDOW_CONTROL_CHANNELS.GET_WORKAREA, (event) => {
  if (!isTrustedSender(event)) return null;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return screen.getPrimaryDisplay().workArea;
  const display = screen.getDisplayMatching(win.getBounds());
  return display.workArea;
});

function getPetBottomExpandedWorkArea(display) {
  if (!display || !display.workArea || !display.bounds) {
    return display && display.workArea ? { ...display.workArea } : null;
  }
  const workArea = display.workArea;
  const bounds = display.bounds;
  const bottom = Math.max(workArea.y + workArea.height, bounds.y + bounds.height);
  return {
    ...workArea,
    height: Math.max(1, bottom - workArea.y),
  };
}

function isLinuxSubtitleWindow(win) {
  if (process.platform !== 'linux' || !win || win.isDestroyed() || !win.webContents) return false;
  try {
    const url = String(win.webContents.getURL ? win.webContents.getURL() : '');
    return /(?:^|\/)subtitle(?:[?#]|$)/.test(url);
  } catch (_) {
    return false;
  }
}

function isSubtitleWindow(win) {
  if (!win || win.isDestroyed() || !win.webContents) return false;
  try {
    const url = String(win.webContents.getURL ? win.webContents.getURL() : '');
    return /(?:^|\/)subtitle(?:[?#]|$)/.test(url);
  } catch (_) {
    return false;
  }
}

function normalizeSubtitlePanelBounds(bounds) {
  const width = Math.round(Number(bounds && bounds.width));
  const height = Math.round(Number(bounds && bounds.height));
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }
  return {
    width: Math.max(SUBTITLE_PANEL_MIN_WIDTH, width),
    height: Math.max(SUBTITLE_PANEL_MIN_HEIGHT, height),
  };
}

function sameWindowBounds(a, b) {
  return !!(a && b &&
    Math.round(Number(a.x)) === Math.round(Number(b.x)) &&
    Math.round(Number(a.y)) === Math.round(Number(b.y)) &&
    Math.round(Number(a.width)) === Math.round(Number(b.width)) &&
    Math.round(Number(a.height)) === Math.round(Number(b.height)));
}

function getActualBoundsOffset(actualBounds, requestedBounds) {
  if (!actualBounds || !requestedBounds) return null;
  const actualX = Number(actualBounds.x);
  const actualY = Number(actualBounds.y);
  const requestedX = Number(requestedBounds.x);
  const requestedY = Number(requestedBounds.y);
  if (!Number.isFinite(actualX) || !Number.isFinite(actualY) ||
      !Number.isFinite(requestedX) || !Number.isFinite(requestedY)) {
    return null;
  }
  return {
    x: Math.round(actualX - requestedX),
    y: Math.round(actualY - requestedY),
  };
}

function attachDragStopBoundsMetadata(bounds, metadata) {
  if (!bounds || !metadata) return bounds;
  return {
    ...bounds,
    ...metadata,
  };
}

function clampLinuxSubtitleDragY(win, y, cursorPoint) {
  if (!isLinuxSubtitleWindow(win)) return y;
  const bounds = win.getBounds();
  const display = screen.getDisplayNearestPoint(cursorPoint);
  const wa = display && display.workArea ? display.workArea : screen.getPrimaryDisplay().workArea;
  const maxY = wa.y + wa.height - bounds.height;
  return Math.min(y, maxY);
}

// ===== 窗口位置/尺寸控制 =====
ipcMain.on(WINDOW_CONTROL_CHANNELS.SET_POSITION, (event, { x, y } = {}) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed() && Number.isFinite(x) && Number.isFinite(y)) {
    // 用 setBounds 替代 setPosition —— Windows transparent 窗口 setPosition 会导致尺寸漂移
    const bounds = win.getBounds();
    win.setBounds({ x: Math.round(x), y: Math.round(y), width: bounds.width, height: bounds.height });
  }
});

// Wayland 拖动：渲染进程发送坐标差值（因为主进程无法读取全局光标坐标）
ipcMain.on('neko:win-set-position-delta', (event, { dx, dy } = {}) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed() && Number.isFinite(dx) && Number.isFinite(dy)) {
    const bounds = win.getBounds();
    win.setBounds({ x: bounds.x + Math.round(dx), y: bounds.y + Math.round(dy), width: bounds.width, height: bounds.height });
  }
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.SET_SIZE, (event, { w, h, panelBounds } = {}) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return;
  const subtitleWindow = isSubtitleWindow(win);
  if (subtitleWindow) {
    cancelBounceBack(win);
    const normalizedPanelBounds = normalizeSubtitlePanelBounds(panelBounds);
    if (normalizedPanelBounds) {
      win._nekoSubtitlePanelBounds = normalizedPanelBounds;
    }
  }
  // 用 setBounds 替代 setSize —— Windows 上 transparent 窗口的 setSize 缩小方向可能不生效
  const bounds = win.getBounds();
  const width = Number(w);
  const height = Number(h);
  const nextBounds = {
    x: bounds.x,
    y: bounds.y,
    width: Math.round(Number.isFinite(width) && width > 0 ? width : bounds.width),
    height: Math.round(Number.isFinite(height) && height > 0 ? height : bounds.height),
  };
  if (sameWindowBounds(bounds, nextBounds)) return;
  win.setBounds(nextBounds);
  if (subtitleWindow) {
    refreshSubtitleWaylandInputShape(win);
  }
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.SET_BOUNDS, (event, { x, y, w, h } = {}) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return;
  const subtitleWindow = isSubtitleWindow(win);
  if (subtitleWindow) {
    cancelBounceBack(win);
  }
  const bounds = win.getBounds();
  const nextX = Number(x);
  const nextY = Number(y);
  const nextW = Number(w);
  const nextH = Number(h);
  const nextBounds = {
    x: Math.round(Number.isFinite(nextX) ? nextX : bounds.x),
    y: Math.round(Number.isFinite(nextY) ? nextY : bounds.y),
    width: Math.round(Number.isFinite(nextW) && nextW > 0 ? nextW : bounds.width),
    height: Math.round(Number.isFinite(nextH) && nextH > 0 ? nextH : bounds.height),
  };
  if (sameWindowBounds(bounds, nextBounds)) return;
  win.setBounds(nextBounds);
  if (subtitleWindow && (nextBounds.width !== bounds.width || nextBounds.height !== bounds.height)) {
    updateSubtitlePanelBoundsFromWindow(win);
    refreshSubtitleWaylandInputShape(win);
  }
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.SET_RESIZABLE, (event, { resizable, minWidth, minHeight } = {}) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed()) {
    win.setResizable(!!resizable);
    // 折叠态设 minWidth/minHeight 为 0 允许缩到呼吸球大小
    if (!resizable) {
      const nextMinWidth = Math.max(50, Math.round(Number(minWidth) || 50));
      const nextMinHeight = Math.max(50, Math.round(Number(minHeight) || 50));
      win.setMinimumSize(nextMinWidth, nextMinHeight);
    } else if (win._nekoFullChat) {
      // full 独立窗口保留自己的下限（工作区适配后的 ≤360×360），不被压回 compact 的 320×280 ——
      // 否则 full 复用同一套 collapse/expand IPC，走过一次折叠/展开后下限丢失，/chat_full 的 inset
      // 布局在过小尺寸下被压坏。
      const m = fullChatMinSize(win);
      win.setMinimumSize(m.width, m.height);
    } else {
      win.setMinimumSize(320, 280);
    }
  }
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT, (event) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return;
  if (isLinuxWaylandRuntime()) {
    const raiseWaylandWindow = (target, kind) => {
      if (!target || target.isDestroyed()) return;
      try {
        if (typeof target.isVisible === 'function' && !target.isVisible()) return;
        if (typeof target.isMinimized === 'function' && target.isMinimized()) return;
      } catch (_) {}
      try {
        if (typeof applyTopOn === 'function') {
          applyTopOn(target, { kind, defaultLevel: 'floating' });
        } else {
          target.setAlwaysOnTop(true, 'floating');
        }
      } catch (_) {}
      try { target.moveTop(); } catch (_) {}
    };
    let windows = null;
    try {
      windows = windowManager && typeof windowManager.getWindows === 'function'
        ? windowManager.getWindows()
        : null;
    } catch (_) {
      windows = null;
    }
    const pet = (windows && windows.pet) || getMainWindowRef();
    const chat = windows && windows.chat;
    const fullChat = windows && windows.fullChat;
    const compactChatBall = windows && windows.compactChatBall;
    const senderIsManagedSurface = win === pet
      || win === chat
      || win === fullChat
      || win === compactChatBall;
    if (senderIsManagedSurface) {
      // Keep the desktop companions grouped above other apps. Pet is raised
      // first and Chat second, so the input surface remains usable above the
      // transparent model window.
      raiseWaylandWindow(pet, 'pet');
      raiseWaylandWindow(chat, 'reactChat');
      raiseWaylandWindow(fullChat, 'reactChat');
      raiseWaylandWindow(compactChatBall, 'reactChat');
      return;
    }
    raiseWaylandWindow(win, null);
    return;
  }
  try { win.moveTop(); } catch (_) {}
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.HIDE, (event) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win && !win.isDestroyed()) {
    win.hide();
  }
});

// ===== 折叠 / 展开（原子操作 —— 解决 Windows 透明窗口 setBounds 不生效问题）=====
const COLLAPSED_ICON_SIZE = 88; // 给放大的 yarn ball 保留点击余量
// 回弹动画取消句柄，供 COLLAPSE/EXPAND 在 setBounds 前终止正在运行的回弹
// （定义提前到此处，因为 COLLAPSE/EXPAND handler 闭包中引用）
const _bounceState = new Map();  // winId → { cancelled }

function getExpandedWindowResizable() {
  return process.platform !== 'win32';
}

// 展开落地验证 —— Windows 透明无框窗口 setBounds 可能因 DWM 异步合成
// 而延迟落地，同步 getBounds() 不可靠（会读到尚未生效的目标值）。
// 用递增 delay 的异步多次验证，并在失败时升级补救策略。
function ensureExpanded(win, targetBounds, attempt = 0) {
  const DELAYS = [50, 150, 350];
  if (attempt >= DELAYS.length || !win || win.isDestroyed()) return;
  setTimeout(() => {
    if (win.isDestroyed()) return;
    const actual = win.getBounds();
    // 容忍 ≤2px 误差（DWM 整数舍入）
    if (actual.width  >= targetBounds.width  - 2 &&
        actual.height >= targetBounds.height - 2) return;

    // 约束到工作区（沿用 bounceBackToWorkArea 的多屏判定）
    const cursor = screen.getCursorScreenPoint();
    const wa = screen.getDisplayNearestPoint(cursor).workArea;
    const cx = Math.max(wa.x + BOUNCE_MARGIN,
      Math.min(actual.x,
        wa.x + wa.width - targetBounds.width - BOUNCE_MARGIN));
    // 左下角对齐：保持底边位置不变，向上展开
    const cy = Math.max(wa.y + BOUNCE_MARGIN,
      Math.min(actual.y + actual.height - targetBounds.height,
        wa.y + wa.height - targetBounds.height - BOUNCE_MARGIN));
    const retry = { x: cx, y: cy,
      width: targetBounds.width, height: targetBounds.height };

    if (attempt === 0) {
      win.setBounds(retry);
    } else if (attempt === 1) {
      // 先 setContentSize 绕过 frame-metrics 缓存
      win.setContentSize(targetBounds.width, targetBounds.height);
      win.setBounds(retry);
    } else {
      // setResizable 切换强制 DWM 丢弃缓存的窗口样式
      if (process.platform === 'win32') {
        win.setResizable(true);
        win.setBounds(retry);
        win.setResizable(false);
      } else {
        win.setResizable(false);
        win.setBounds(retry);
        win.setResizable(true);
      }
      // full 独立窗口保留自己的下限（见 SET_RESIZABLE），不被展开重试路径打回 compact 的 320×280。
      if (win._nekoFullChat) {
        const m = fullChatMinSize(win);
        win.setMinimumSize(m.width, m.height);
      } else {
        win.setMinimumSize(320, 280);
      }
    }
    ensureExpanded(win, targetBounds, attempt + 1);
  }, DELAYS[attempt]);
}

ipcMain.handle(WINDOW_CONTROL_CHANNELS.COLLAPSE, (event, targetBounds) => {
  if (!isTrustedSender(event)) return null;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return null;

  // 取消该窗口正在运行的回弹动画（用户拖窗口到边缘后立即点折叠时可能还在回弹）
  const bounceState = _bounceState.get(win.id);
  if (bounceState) bounceState.cancelled = true;

  const bounds = win.getBounds();

  // full 独立窗口：暂存折叠前的真实尺寸，供 saveWindowPositions 在球态时回退使用。
  // full 的几何持久化（window-manager enablePositionPersistence）靠 resize 事件存盘，
  // 折叠成 88px 球时那次 resize 会把球尺寸写进 fullChat 磁盘记录，重启时被当折叠残留
  // 回退默认 → 用户拉过的 full 尺寸丢失。这里把真实尺寸挂到窗口对象，让保存逻辑用它
  // 而非球尺寸。仅在确为展开态（非二次折叠）时记录。
  if (win._nekoFullChat && bounds.width > COLLAPSED_ICON_SIZE && bounds.height > COLLAPSED_ICON_SIZE) {
    win._nekoFullChatExpandedBounds = { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height };
  }

  // 允许缩小到图标大小
  win.setMinimumSize(COLLAPSED_ICON_SIZE, COLLAPSED_ICON_SIZE);

  // 左下角对齐：折叠后窗口的左下角与原对话框的左下角重合
  const targetX = targetBounds && Number(targetBounds.x);
  const targetY = targetBounds && Number(targetBounds.y);
  const newX = Number.isFinite(targetX) ? Math.round(targetX) : bounds.x;
  const newY = Number.isFinite(targetY) ? Math.round(targetY) : bounds.y + bounds.height - COLLAPSED_ICON_SIZE;
  const newBounds = { x: newX, y: newY, width: COLLAPSED_ICON_SIZE, height: COLLAPSED_ICON_SIZE };

  // 直接 setBounds，不 hide/show（避免折叠动画跳变）
  // 原注释称 Windows 透明窗口缩小方向 setBounds 不生效需要 hide→show，
  // 但该结论需要在当前场景下重新验证。
  win.setBounds(newBounds);

  return bounds; // 返回折叠前尺寸供渲染进程保存
});

ipcMain.handle(WINDOW_CONTROL_CHANNELS.EXPAND, (event, savedBounds) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return;
  const expandOptions = savedBounds && typeof savedBounds === 'object' && savedBounds.bounds
    ? savedBounds
    : null;
  const targetBounds = expandOptions ? expandOptions.bounds : savedBounds;
  const skipEnsureExpanded = !!(expandOptions && expandOptions.skipEnsureExpanded);
  if (
    !targetBounds
    || !Number.isFinite(Number(targetBounds.width))
    || !Number.isFinite(Number(targetBounds.height))
    || Number(targetBounds.width) <= 0
    || Number(targetBounds.height) <= 0
  ) {
    log('EXPAND 忽略无效 savedBounds:', JSON.stringify(targetBounds || null));
    return;
  }

  // 取消该窗口正在运行的回弹动画。
  // 触发路径：用户点击折叠球展开 → mousedown 触发 DRAG_START → mouseup 触发 DRAG_STOP
  // → DRAG_STOP 调用 bounceBackToWorkArea（若球贴近工作区边缘则启动 200ms 动画）
  // → ~48ms 后 EXPAND IPC 到达。如果不取消，回弹动画会持续以折叠尺寸覆写展开后的 setBounds。
  const bounceState = _bounceState.get(win.id);
  if (bounceState) bounceState.cancelled = true;

  // 展开回真实尺寸：清掉折叠时暂存的展开 bounds，之后由正常 resize 持久化接管。
  if (win._nekoFullChat) win._nekoFullChatExpandedBounds = null;

  // 先读取折叠态的真实坐标（用户可能拖拽过）。
  const current = win.getBounds();

  // 左下角对齐：展开后对话框的左下角与当前折叠图标的左下角重合。
  // 毛线球恢复路径展开后，再由渲染进程的 desktop compact（stored surface = 球位置）把
  // 对话条精确锚到球处，所以这里只需一个合理的初始 bounds。
  const expandedWidth = Math.round(Number(targetBounds.width));
  const expandedHeight = Math.round(Number(targetBounds.height));
  const b = {
    x: current.x,
    y: current.y + current.height - expandedHeight,
    width: expandedWidth,
    height: expandedHeight,
  };

  // 先 setBounds 再 setMinimumSize，避免 setMinimumSize 在折叠窗口上
  // 触发隐式 resize（撑到 320x280）产生额外 SetWindowPos。
  win.setBounds(b);
  // full 独立窗口保留自己的下限（见 SET_RESIZABLE），不被 EXPAND 路径打回 compact 的 320×280。
  if (win._nekoFullChat) {
    const m = fullChatMinSize(win);
    win.setMinimumSize(m.width, m.height);
  } else {
    win.setMinimumSize(320, 280);
  }
  win.setResizable(getExpandedWindowResizable());
  log('[WindowControl][expand] applied bounds/resizable:', JSON.stringify({
    platform: process.platform,
    bounds: b,
    resizable: getExpandedWindowResizable(),
    skipEnsureExpanded
  }));

  // 异步多次验证 + 升级补救（替代之前的同步兜底，因为同步 getBounds()
  // 在透明无框窗口上可能读到 DWM 尚未提交的目标值，使条件判断失效）。
  // 毛线球恢复路径随后会由 renderer 的 desktop compact relayout 接管自然窗口 bounds；
  // 若继续按旧展开大窗尺寸重试，会在揭示后与 compact bounds 来回覆盖，表现为闪烁。
  if (!skipEnsureExpanded) ensureExpanded(win, b);
});

// ===== 边界回弹（拖拽/resize 结束后将窗口约束到工作区内）=====
const BOUNCE_DURATION = 200; // 回弹动画时长 ms
const BOUNCE_MARGIN = 8;     // 距离工作区边缘的最小间距 px

function cancelBounceBack(win) {
  if (!win || win.isDestroyed()) return;
  const state = _bounceState.get(win.id);
  if (state) {
    state.cancelled = true;
    _bounceState.delete(win.id);
  }
}

function clampWindowToWorkAreaImmediate(win, point) {
  if (!win || win.isDestroyed()) return;
  const bounds = win.getBounds();
  const cursor = normalizeResizeCursorPoint(point);
  const display = cursor ? screen.getDisplayNearestPoint(cursor) : screen.getDisplayMatching(bounds);
  const wa = display.workArea;
  let tx = bounds.x;
  let ty = bounds.y;
  let tw = Math.min(bounds.width, wa.width - BOUNCE_MARGIN * 2);
  let th = Math.min(bounds.height, wa.height - BOUNCE_MARGIN * 2);
  const [winMinW, winMinH] = win.getMinimumSize();
  if (bounds.width >= winMinW) tw = Math.max(tw, winMinW || SUBTITLE_WINDOW_MIN_WIDTH);
  if (bounds.height >= winMinH) th = Math.max(th, winMinH || SUBTITLE_WINDOW_MIN_HEIGHT);
  tx = Math.max(wa.x + BOUNCE_MARGIN, Math.min(tx, wa.x + wa.width - tw - BOUNCE_MARGIN));
  ty = Math.max(wa.y + BOUNCE_MARGIN, Math.min(ty, wa.y + wa.height - th - BOUNCE_MARGIN));
  tx = tx | 0; ty = ty | 0; tw = tw | 0; th = th | 0;
  if (tx !== bounds.x || ty !== bounds.y || tw !== bounds.width || th !== bounds.height) {
    win.setBounds({ x: tx, y: ty, width: tw, height: th });
  }
}

function bounceBackToWorkArea(win) {
  if (!win || win.isDestroyed()) return;

  // 取消同一窗口上一次未完成的回弹动画
  cancelBounceBack(win);

  const bounds = win.getBounds();
  // 用光标所在显示器作为目标，而非窗口面积重叠 ——
  // 这样拖到副屏松手时，窗口会留在光标所在的屏幕上
  const cursor = screen.getCursorScreenPoint();
  const display = screen.getDisplayNearestPoint(cursor);
  const wa = display.workArea;

  // full 独立窗口：回弹「只管内容、阴影出界无所谓」。窗口含一圈 ~30px 阴影留白（见
  // window-manager createFullChatWindow），允许窗口过冲工作区边缘这么多，使**内容**（窗口内缩
  // 阴影留白后）能贴到屏边才回弹，而不是阴影边一碰边就把内容拉回老远。其它窗口 overhang=0 不变。
  const overhang = (win._nekoFullChat && Number.isFinite(Number(win._nekoFullChatShadowMargin)))
    ? Math.max(0, Math.round(Number(win._nekoFullChatShadowMargin)))
    : 0;

  // 计算目标位置：将窗口完全约束在工作区 + margin 范围内
  let tx = bounds.x, ty = bounds.y;
  let tw = bounds.width, th = bounds.height;

  // 尺寸不能超过工作区（减去两侧 margin；full 允许阴影过冲，放宽 overhang）
  tw = Math.min(tw, wa.width - BOUNCE_MARGIN * 2 + overhang * 2);
  th = Math.min(th, wa.height - BOUNCE_MARGIN * 2 + overhang * 2);
  // 使用窗口自身的 minWidth/minHeight（字幕窗口为 200x40，Chat/AgentHud 为 320x280+）
  // 仅在非折叠态（窗口尺寸 >= 最小值）时强制最小尺寸，
  // 避免折叠态小窗口（56x56）被放大
  const [winMinW, winMinH] = win.getMinimumSize();
  const effectiveMinW = winMinW || RESIZE_MIN_W;
  const effectiveMinH = winMinH || RESIZE_MIN_H;
  if (bounds.width >= effectiveMinW) tw = Math.max(tw, effectiveMinW);
  if (bounds.height >= effectiveMinH) th = Math.max(th, effectiveMinH);

  // 位置约束：左/右、上/下边界不超出（full 允许窗口过冲 overhang，让阴影出界、内容到边才回弹）
  tx = Math.max(wa.x + BOUNCE_MARGIN - overhang, Math.min(tx, wa.x + wa.width - tw - BOUNCE_MARGIN + overhang));
  ty = Math.max(wa.y + BOUNCE_MARGIN - overhang, Math.min(ty, wa.y + wa.height - th - BOUNCE_MARGIN + overhang));

  tx = tx | 0; ty = ty | 0; tw = tw | 0; th = th | 0;

  // 如果无需移动则跳过
  if (tx === bounds.x && ty === bounds.y && tw === bounds.width && th === bounds.height) {
    _bounceState.delete(win.id);
    return;
  }

  // ease-out 缓动动画
  const sx = bounds.x, sy = bounds.y, sw = bounds.width, sh = bounds.height;
  const start = Date.now();
  const state = { cancelled: false };
  _bounceState.set(win.id, state);

  const animate = () => {
    if (state.cancelled || !win || win.isDestroyed()) {
      _bounceState.delete(win.id);
      return;
    }
    const elapsed = Date.now() - start;
    const t = Math.min(elapsed / BOUNCE_DURATION, 1);
    // ease-out cubic: 1 - (1-t)^3
    const ease = 1 - Math.pow(1 - t, 3);

    const cx = (sx + (tx - sx) * ease) | 0;
    const cy = (sy + (ty - sy) * ease) | 0;
    const cw = (sw + (tw - sw) * ease) | 0;
    const ch = (sh + (th - sh) * ease) | 0;

    win.setBounds({ x: cx, y: cy, width: cw, height: ch });

    if (t < 1) {
      setTimeout(animate, BOUNCE_ANIM_INTERVAL);
    } else {
      _bounceState.delete(win.id);
    }
  };
  animate();
}

// ===== 主进程辅助拖拽（解决渲染进程 screenX 坐标反馈环漂移）=====
// 拖拽逻辑完全在主进程执行：用 screen.getCursorScreenPoint() 读取光标位置，
// 避免 Chromium 在 SetWindowPos 后合成 mousemove 时 screenX 偏移。
// 使用递归 setTimeout 替代 setInterval，防止透明窗口 setBounds 耗时 > 间隔时回调堆积。
// 自适应轮询：基于 setBounds 实际耗时动态调整间隔，高端机保持高帧率，低端机自动降频避免卡顿。
const _dragState = new Map();  // webContentsId → { timer, cancelled }
const _returnBallDragRevealOpacity = new Map();
const _returnBallDragRestoreBounds = new Map();
const _displayAdjustTimers = new Map();
const _displayBroadcastTimers = new Map();
const _displayAdjustCooldownUntil = new Map();
const _displayAdjustSuppressLogState = new Map();
const _lastDisplayStateByWindow = new Map();
const _lastBroadcastDisplayStateByWindow = new Map();
const _displayRecoveryHandlersByWindow = new Map();
const DRAG_POLL_INTERVAL = 8;        // 拖拽基准间隔 ~120fps
const SHRINK_DRAG_POLL_INTERVAL = 16; // return-ball shrink 拖拽只需要跟随 60fps，减少透明窗口 setBounds 压力
const RESIZE_POLL_INTERVAL = 16;     // resize 基准间隔 ~60fps
const POLL_INTERVAL_CAP = 32;        // 自适应间隔上限 ~30fps，低于此值用户会感知卡顿
const BOUNCE_ANIM_INTERVAL = 16;     // 回弹动画固定 ~60fps（无需更高帧率）
const DISPLAY_ADJUST_DEBOUNCE_MS = 96;
const DISPLAY_ADJUST_POST_DRAG_COOLDOWN_MS = 650;
const DISPLAY_ADJUST_SUPPRESSION_LOG_INTERVAL_MS = 250;
const RENDERER_SCREEN_POINT_DIVERGENCE_FALLBACK_PX = 96;
const RETURN_BALL_SHRINK_VIEWPORT_SIZE = 160;

function getFullscreenDisplayBounds(display) {
  if (!display || !display.bounds) return null;
  // 屏幕内 off-by-one：继续破坏“起点贴齐 + size 等于 display”的完美全屏覆盖判定，
  // 以延续对 DWM/Chromium fullscreen-borderless / occlusion 优化副作用的规避。
  // 这些副作用包括后台浏览器视频暂停、第三方播放器卡顿等；当前屏幕内方案是否
  // 与旧 extend-by-1 在所有 GPU 驱动 / Windows 版本上等价，仍需按复现场景验证。
  // 不再使用 extend-by-1 越界方案；部分 Windows/Electron 环境会在创建期把越界透明窗口夹到 workArea。
  // 右/底贴齐 display，左/上各留 1px；若创建期仍被夹到 workArea，创建后的 bounds repair 会修回目标高度。
  return {
    x: display.bounds.x + 1,
    y: display.bounds.y + 1,
    width: Math.max(1, display.bounds.width - 1),
    height: Math.max(1, display.bounds.height - 1),
  };
}

function getDisplayTargetBoundsMetadata(actualBounds) {
  if (!actualBounds) return null;
  const display = screen.getDisplayMatching(actualBounds);
  const requestedBounds = getFullscreenDisplayBounds(display);
  if (!requestedBounds) return null;
  return {
    requestedBounds,
    actualBoundsOffset: getActualBoundsOffset(actualBounds, requestedBounds),
  };
}

function cloneBounds(bounds) {
  if (!bounds) return null;
  return {
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
  };
}

function isReturnBallShrinkViewport(bounds) {
  if (!bounds) return false;
  const width = Math.round(Number(bounds.width));
  const height = Math.round(Number(bounds.height));
  if (!Number.isFinite(width) || !Number.isFinite(height)) return false;
  return Math.abs(width - RETURN_BALL_SHRINK_VIEWPORT_SIZE) <= 2
    && Math.abs(height - RETURN_BALL_SHRINK_VIEWPORT_SIZE) <= 2;
}

function buildReturnBallDragStopResult(finalBounds, metadata, wasShrinkDrag, requestedBounds) {
  const bounds = attachDragStopBoundsMetadata(cloneBounds(finalBounds), metadata);
  if (!bounds) return null;
  return {
    ...bounds,
    wasShrinkDrag: !!wasShrinkDrag,
    actualBounds: cloneBounds(finalBounds),
    requestedBounds: cloneBounds(requestedBounds || finalBounds),
  };
}

function buildDisplayState(displayLike, windowBounds = null) {
  if (!displayLike) return null;
  const displayId = displayLike.id != null ? displayLike.id : displayLike.displayId;
  const displayBounds = displayLike.bounds || displayLike.displayBounds;
  if (displayId == null || !displayBounds) return null;
  return {
    displayId,
    scaleFactor: displayLike.scaleFactor,
    displayBounds: cloneBounds(displayBounds),
    fullscreenBounds: getFullscreenDisplayBounds({ bounds: displayBounds }),
    windowBounds: cloneBounds(windowBounds),
  };
}

function hasDisplayStateChanged(previousState, nextState) {
  if (!previousState || !nextState) return true;
  return previousState.displayId !== nextState.displayId ||
    previousState.scaleFactor !== nextState.scaleFactor ||
    !boundsApproximatelyEqual(previousState.displayBounds, nextState.displayBounds, 0);
}

function setLastDisplayState(win, nextState) {
  if (!win || win.isDestroyed() || !nextState) return;
  const previousState = _lastDisplayStateByWindow.get(win.id) || null;
  _lastDisplayStateByWindow.set(win.id, {
    displayId: nextState.displayId,
    scaleFactor: nextState.scaleFactor,
    displayBounds: cloneBounds(nextState.displayBounds),
    fullscreenBounds: cloneBounds(nextState.fullscreenBounds) ||
      cloneBounds(previousState && previousState.fullscreenBounds),
    windowBounds: cloneBounds(nextState.windowBounds) ||
      cloneBounds(previousState && previousState.windowBounds),
  });
}

function setLastBroadcastDisplayState(win, nextState) {
  if (!win || win.isDestroyed() || !nextState) return;
  _lastBroadcastDisplayStateByWindow.set(win.id, {
    displayId: nextState.displayId,
    scaleFactor: nextState.scaleFactor,
    displayBounds: cloneBounds(nextState.displayBounds),
  });
}

function boundsApproximatelyEqual(a, b, tolerance = 1) {
  if (!a || !b) return false;
  return Math.abs(a.x - b.x) <= tolerance &&
    Math.abs(a.y - b.y) <= tolerance &&
    Math.abs(a.width - b.width) <= tolerance &&
    Math.abs(a.height - b.height) <= tolerance;
}

function getTrustedCursorScreenPoint(payload) {
  const electronPoint = screen.getCursorScreenPoint();
  const sx = Number(payload && payload.sx);
  const sy = Number(payload && payload.sy);
  if (!Number.isFinite(sx) || !Number.isFinite(sy)) return electronPoint;
  const rendererPoint = { x: sx, y: sy };
  const distance = Math.hypot(rendererPoint.x - electronPoint.x, rendererPoint.y - electronPoint.y);
  return distance <= RENDERER_SCREEN_POINT_DIVERGENCE_FALLBACK_PX ? rendererPoint : electronPoint;
}

function getDragStateForWindow(win) {
  if (!win || win.isDestroyed() || !win.webContents || win.webContents.isDestroyed()) return null;
  return _dragState.get(win.webContents.id) || null;
}

function normalizeReturnBallRevealOpacity(value) {
  const opacity = Number(value);
  return Number.isFinite(opacity) && opacity > 0.05 ? opacity : 1;
}

function shouldDisableNativeReturnBallDrag() {
  return process.platform === 'win32' && (
    process.env.NEKO_COMPATIBILITY_MODE === '1' ||
    process.argv.includes('--disable-gpu-compositing') ||
    process.argv.includes('--disable-direct-composition')
  );
}

function setDisplayAdjustCooldown(win, durationMs, reason) {
  if (!win || win.isDestroyed()) return;
  const until = Date.now() + durationMs;
  _displayAdjustCooldownUntil.set(win.id, until);
  if (reason) {
    log(`${reason}，挂起屏幕 metrics 自动纠正 ${durationMs}ms`);
  }
}

function getDisplayAdjustSuppressionReason(win, eventType) {
  if (eventType !== 'display-metrics-changed' || !win || win.isDestroyed()) return '';
  const dragState = getDragStateForWindow(win);
  if (dragState && dragState.suspendAutoDisplayAdjust) {
    return 'drag-active';
  }
  const cooldownUntil = _displayAdjustCooldownUntil.get(win.id) || 0;
  if (cooldownUntil > Date.now()) {
    return 'cooldown';
  }
  if (cooldownUntil) {
    _displayAdjustCooldownUntil.delete(win.id);
  }
  return '';
}

function maybeLogSuppressedDisplayAdjust(win, logTag, reason, display, changedMetrics) {
  if (!win || win.isDestroyed()) return;
  const now = Date.now();
  const signature = `${reason}:${display && display.id ? display.id : 'unknown'}:${Array.isArray(changedMetrics) ? changedMetrics.join(',') : ''}`;
  const prev = _displayAdjustSuppressLogState.get(win.id);
  if (prev && prev.signature === signature &&
      now - prev.at < DISPLAY_ADJUST_SUPPRESSION_LOG_INTERVAL_MS) {
    return;
  }
  _displayAdjustSuppressLogState.set(win.id, { signature, at: now });
  log(`${logTag} 屏幕 metrics 变化已抑制(${reason})`, JSON.stringify({
    displayId: display && display.id,
    changedMetrics: Array.isArray(changedMetrics) ? changedMetrics : [],
  }));
}

function scheduleDisplayChangedBroadcast(win, payload, delayMs = 32, force = false) {
  if (!win || win.isDestroyed() || !payload) return false;
  const nextState = buildDisplayState(payload);
  const previousState = _lastBroadcastDisplayStateByWindow.get(win.id) || null;
  if (!force && nextState && previousState && !hasDisplayStateChanged(previousState, nextState)) {
    return false;
  }
  if (nextState) {
    setLastBroadcastDisplayState(win, nextState);
  }

  const prevTimer = _displayBroadcastTimers.get(win.id);
  if (prevTimer) clearTimeout(prevTimer);

  const timer = setTimeout(() => {
    _displayBroadcastTimers.delete(win.id);
    if (!win || win.isDestroyed()) return;
    win.webContents.send('display-changed', payload);
  }, delayMs);

  _displayBroadcastTimers.set(win.id, timer);
  return true;
}

function scheduleWindowDisplayAdjust(win, options = {}) {
  if (!win || win.isDestroyed()) return;
  const {
    eventType = 'display-metrics-changed',
    display = null,
    changedMetrics = null,
    logTag = '[DisplayAdjust]',
    adjustLogLabel = '屏幕配置变化，调整窗口:',
  } = options;

  const suppressionReason = getDisplayAdjustSuppressionReason(win, eventType);
  if (suppressionReason) {
    maybeLogSuppressedDisplayAdjust(win, logTag, suppressionReason, display, changedMetrics);
    return;
  }

  const prevTimer = _displayAdjustTimers.get(win.id);
  if (prevTimer) clearTimeout(prevTimer);

  const timer = setTimeout(() => {
    _displayAdjustTimers.delete(win.id);
    if (!win || win.isDestroyed()) return;

    const windowBounds = win.getBounds();
    const currentDisplay = screen.getDisplayMatching(windowBounds);
    if (!currentDisplay) return;

    const newBounds = getFullscreenDisplayBounds(currentDisplay);
    if (!newBounds) return;

    const currentState = buildDisplayState(currentDisplay, windowBounds);
    const previousState = _lastDisplayStateByWindow.get(win.id) || null;
    const windowNeedsRealign = !boundsApproximatelyEqual(windowBounds, newBounds);
    const shouldHandleMetrics = eventType !== 'display-metrics-changed' ||
      windowNeedsRealign ||
      hasDisplayStateChanged(previousState, currentState);

    if (!shouldHandleMetrics) {
      return;
    }

    let appliedWindowBounds = windowBounds;
    if (windowNeedsRealign) {
      log(adjustLogLabel, JSON.stringify(newBounds));
      win.setBounds(newBounds);
      appliedWindowBounds = win.getBounds();
    }

    setLastDisplayState(win, buildDisplayState(currentDisplay, appliedWindowBounds));
    scheduleDisplayChangedBroadcast(win, {
      displayId: currentDisplay.id,
      bounds: currentDisplay.bounds,
      scaleFactor: currentDisplay.scaleFactor,
    }, 32, windowNeedsRealign);
  }, DISPLAY_ADJUST_DEBOUNCE_MS);

  _displayAdjustTimers.set(win.id, timer);
}

function unbindWindowDisplayRecovery(winId) {
  const binding = _displayRecoveryHandlersByWindow.get(winId);
  if (!binding) return;

  screen.removeListener('display-added', binding.onDisplayAdded);
  screen.removeListener('display-removed', binding.onDisplayRemoved);
  screen.removeListener('display-metrics-changed', binding.onDisplayMetricsChanged);
  if (binding.win && !binding.win.isDestroyed()) {
    binding.win.removeListener('closed', binding.cleanup);
  }

  const adjustTimer = _displayAdjustTimers.get(winId);
  if (adjustTimer) {
    clearTimeout(adjustTimer);
    _displayAdjustTimers.delete(winId);
  }
  const broadcastTimer = _displayBroadcastTimers.get(winId);
  if (broadcastTimer) {
    clearTimeout(broadcastTimer);
    _displayBroadcastTimers.delete(winId);
  }
  _displayAdjustCooldownUntil.delete(winId);
  _displayAdjustSuppressLogState.delete(winId);
  _lastDisplayStateByWindow.delete(winId);
  _lastBroadcastDisplayStateByWindow.delete(winId);
  _displayRecoveryHandlersByWindow.delete(winId);
}

function bindWindowDisplayRecovery(win, options = {}) {
  if (!win || win.isDestroyed()) return;
  const {
    logTag = '[DisplayAdjust]',
    adjustLogLabel = '屏幕配置变化，调整窗口:',
  } = options;

  unbindWindowDisplayRecovery(win.id);

  const onDisplayAdded = (_event, display) => {
    scheduleWindowDisplayAdjust(win, {
      eventType: 'display-added',
      display,
      logTag,
      adjustLogLabel,
    });
  };
  const onDisplayRemoved = (_event, display) => {
    scheduleWindowDisplayAdjust(win, {
      eventType: 'display-removed',
      display,
      logTag,
      adjustLogLabel,
    });
  };
  const onDisplayMetricsChanged = (_event, display, changedMetrics) => {
    scheduleWindowDisplayAdjust(win, {
      eventType: 'display-metrics-changed',
      display,
      changedMetrics,
      logTag,
      adjustLogLabel,
    });
  };
  const cleanup = () => {
    unbindWindowDisplayRecovery(win.id);
  };

  _displayRecoveryHandlersByWindow.set(win.id, {
    win,
    onDisplayAdded,
    onDisplayRemoved,
    onDisplayMetricsChanged,
    cleanup,
  });

  screen.on('display-added', onDisplayAdded);
  screen.on('display-removed', onDisplayRemoved);
  screen.on('display-metrics-changed', onDisplayMetricsChanged);
  win.on('closed', cleanup);

  const initialBounds = win.getBounds();
  const initialDisplay = screen.getDisplayMatching(initialBounds);
  if (initialDisplay) {
    const initialState = buildDisplayState(initialDisplay, initialBounds);
    setLastDisplayState(win, initialState);
    setLastBroadcastDisplayState(win, initialState);
  }
}

// 通知发起交互的窗口暂停/恢复其渲染主循环（Live2D / VRM / MMD 等）
// 只通知发起方自己：拖 Jukebox 不会波及 Pet 渲染，反之亦然。
// Pet 窗口的 preload 监听该通道；其他窗口没有 listener 时自然忽略，无副作用。
function broadcastInteractionState(win, interacting, kind) {
  if (!win || win.isDestroyed() || !win.webContents || win.webContents.isDestroyed()) return;
  try {
    win.webContents.send(PET_CHANNELS.INTERACTION_STATE, { interacting: !!interacting, kind });
  } catch (_) { /* 窗口销毁竞态：忽略 */ }
}

function stopWindowDrag(event, payload) {
  const id = event.sender.id;
  const state = _dragState.get(id);
  const win = BrowserWindow.fromWebContents(event.sender);
  let wasShrinkDrag = false;
  let finalBounds = (win && !win.isDestroyed()) ? win.getBounds() : null;
  let finalAnchorRect = null;
  let displayChangedByDrag = false;
  let targetDisplay = null;
  let dragStopBoundsMetadata = null;
  let requestedBounds = null;

  if (!state) {
    return { win, wasShrinkDrag, finalBounds, finalAnchorRect, displayChangedByDrag, targetDisplay, dragStopBoundsMetadata, requestedBounds };
  }

  state.cancelled = true;
  clearTimeout(state.timer);
  wasShrinkDrag = !!state.originalBounds;
  const stopCursor = getTrustedCursorScreenPoint(payload);
  state.stopScreenPoint = { ...stopCursor };
  finalAnchorRect = state.lastAnchorRect || null;

  if (state.originalBounds && win && !win.isDestroyed()) {
    targetDisplay = screen.getDisplayNearestPoint(stopCursor);
    displayChangedByDrag = !!targetDisplay && (
      targetDisplay.id !== state.startDisplayId ||
      targetDisplay.scaleFactor !== state.startDisplayScaleFactor ||
      !boundsApproximatelyEqual(targetDisplay.bounds, state.startDisplayBounds, 0)
    );

    const restoreBounds = displayChangedByDrag && targetDisplay
      ? getFullscreenDisplayBounds(targetDisplay)
      : { ...state.originalBounds };
    requestedBounds = restoreBounds;

    if (displayChangedByDrag) {
      setDisplayAdjustCooldown(win, DISPLAY_ADJUST_POST_DRAG_COOLDOWN_MS, '[ReturnBall] 跨屏拖拽完成');
    }

    try {
      const currentOpacity = win.getOpacity();
      _returnBallDragRevealOpacity.set(id, normalizeReturnBallRevealOpacity(currentOpacity));
      win.setOpacity(0);
    } catch (_) {
      _returnBallDragRevealOpacity.delete(id);
    }

    _returnBallDragRestoreBounds.set(id, cloneBounds(restoreBounds));
    win.setBounds(restoreBounds);
    finalBounds = win.getBounds();
    dragStopBoundsMetadata = getDisplayTargetBoundsMetadata(finalBounds);
    const finalDisplay = targetDisplay || screen.getDisplayMatching(finalBounds);
    if (finalDisplay) {
      setLastDisplayState(win, buildDisplayState(finalDisplay, finalBounds));
    }

    if (displayChangedByDrag && targetDisplay) {
      const previousScaleFactor = Number.isFinite(state.startDisplayScaleFactor)
        ? state.startDisplayScaleFactor
        : targetDisplay.scaleFactor;
      const scaleRatio = previousScaleFactor
        ? targetDisplay.scaleFactor / previousScaleFactor
        : 1;
      log('[ReturnBall] 跨屏拖拽完成，权威切换窗口:', JSON.stringify(finalBounds));
      scheduleDisplayChangedBroadcast(win, {
        displayId: targetDisplay.id,
        bounds: targetDisplay.bounds,
        scaleFactor: targetDisplay.scaleFactor,
        scaleRatio,
        previousScaleFactor,
        source: 'return-ball-drag',
      });
    }
    // macOS 恢复 setVisibleOnAllWorkspaces
    if (process.platform === 'darwin') {
      try { win.setVisibleOnAllWorkspaces(false); } catch (_) {}
    }
  } else if (win && !win.isDestroyed()) {
    finalBounds = win.getBounds();
  }

  _dragState.delete(id);
  return { win, wasShrinkDrag, finalBounds, finalAnchorRect, displayChangedByDrag, targetDisplay, dragStopBoundsMetadata, requestedBounds };
}

ipcMain.on(WINDOW_CONTROL_CHANNELS.DRAG_START, (event, payload) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) {
    log('[Main] DRAG_START: window not found or destroyed');
    return;
  }
  const id = event.sender.id;
  const shrink = payload && payload.shrink;

  const rawStartBounds = win.getBounds();
  const pendingRestoreBounds = cloneBounds(_returnBallDragRestoreBounds.get(id));
  const hasPendingReturnBallRestore = !!(
    shrink &&
    pendingRestoreBounds &&
    isReturnBallShrinkViewport(rawStartBounds)
  );

  if (!hasPendingReturnBallRestore && _returnBallDragRevealOpacity.has(id)) {
    const restoreOpacity = _returnBallDragRevealOpacity.get(id);
    _returnBallDragRevealOpacity.delete(id);
    try { win.setOpacity(normalizeReturnBallRevealOpacity(restoreOpacity)); } catch (_) {}
  }
  if (!hasPendingReturnBallRestore) {
    _returnBallDragRestoreBounds.delete(id);
  }

  // 清理旧拖拽
  const old = _dragState.get(id);
  if (old) { old.cancelled = true; clearTimeout(old.timer); }

  // 优先使用 renderer 传入的 mousedown 屏幕坐标，回退到主进程读取
  const startCursor = getTrustedCursorScreenPoint(payload);
  const startBounds = hasPendingReturnBallRestore
    ? pendingRestoreBounds
    : rawStartBounds;
  // Pet 窗口拖拽模式：先缩小窗口，避免大窗口 setBounds 的垂直范围限制
  if (shrink && shouldDisableNativeReturnBallDrag()) {
    log('[ReturnBall] 兼容模式已禁用 native 缩窗拖拽');
    return;
  }
  const keepVisible = payload && payload.keepVisible;
  const anchorClampMode = payload && payload.anchorClampMode;
  const anchorWorkAreaInset = Math.max(0, Math.round(Number(payload && payload.anchorWorkAreaInset) || 0));
  const anchorWorkAreaTopInset = Math.max(0, Math.round(Number(payload && payload.anchorWorkAreaTopInset) || 0));
  const shrinkSize = RETURN_BALL_SHRINK_VIEWPORT_SIZE;
  if (shrink) {
    // 缩小到 return-ball 拖拽视口，以光标为中心偏移
    const sx = startCursor.x - (shrinkSize / 2) | 0;
    const sy = startCursor.y - (shrinkSize / 2) | 0;
    win.setBounds({ x: sx, y: sy, width: shrinkSize, height: shrinkSize });
    win.setBackgroundColor('#00000000');
    // macOS panel 窗口跨屏拖拽需要临时允许所有工作区可见
    if (process.platform === 'darwin') {
      try { win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true }); } catch (_) {}
    }
  }
  // 用缩放后的（或原始的）bounds 作为拖拽起始
  const dragBounds = win.getBounds();
  const rawAnchor = payload && payload.anchorRect;
  const anchorLeft = Number(rawAnchor && rawAnchor.left);
  const anchorTop = Number(rawAnchor && rawAnchor.top);
  const anchorWidth = Number(rawAnchor && rawAnchor.width);
  const anchorHeight = Number(rawAnchor && rawAnchor.height);
  const dragAnchor = (
    !shrink
    && Number.isFinite(anchorLeft)
    && Number.isFinite(anchorTop)
    && Number.isFinite(anchorWidth)
    && Number.isFinite(anchorHeight)
    && anchorWidth > 0
    && anchorHeight > 0
  ) ? {
    offsetX: Math.round(anchorLeft) - dragBounds.x,
    offsetY: Math.round(anchorTop) - dragBounds.y,
    width: Math.round(anchorWidth),
    height: Math.round(anchorHeight),
  } : null;
  const startDisplay = screen.getDisplayMatching(startBounds);
  // 缓存起始位置用于增量计算
  let lastX = dragBounds.x, lastY = dragBounds.y;
  const state = {
    timer: null,
    cancelled: false,
    originalBounds: null,
    startDisplayId: startDisplay ? startDisplay.id : null,
    startDisplayScaleFactor: startDisplay ? startDisplay.scaleFactor : null,
    startDisplayBounds: startDisplay && startDisplay.bounds ? { ...startDisplay.bounds } : null,
    stopScreenPoint: null,
    anchorDrag: !!(dragAnchor && payload && payload.anchorDrag),
    lastAnchorRect: dragAnchor ? {
      left: Math.round(anchorLeft),
      top: Math.round(anchorTop),
      width: Math.round(anchorWidth),
      height: Math.round(anchorHeight),
    } : null,
    suspendAutoDisplayAdjust: !!shrink,
  };

  if (shrink) {
    state.originalBounds = { ...startBounds };
  }
  const pollInterval = shrink ? SHRINK_DRAG_POLL_INTERVAL : DRAG_POLL_INTERVAL;

  const poll = () => {
    if (state.cancelled || !win || win.isDestroyed()) {
      _dragState.delete(id);
      return;
    }
    const cur = screen.getCursorScreenPoint();
    const nx = dragBounds.x + (cur.x - startCursor.x) | 0;
    const ny = clampLinuxSubtitleDragY(win, dragBounds.y + (cur.y - startCursor.y) | 0, cur);
    let tx = nx;
    let ty = ny;
    let anchorMoveRect = null;
    // [multi-display-independence] compact 气泡 anchorDrag：把“光标目标屏”工作区一并
    // 回传渲染端，让 compact 布局能把气泡定位到别的屏（否则被 clamp 拉回窗口原屏）。
    let anchorTargetWorkArea = null;
    if (!shrink && keepVisible) {
      const display = screen.getDisplayNearestPoint(cur);
      const wa = display && display.workArea;
      if (wa) {
        anchorTargetWorkArea = wa;
        const minVisible = Math.max(24, Math.min(96, Number(payload.minVisible) || 64));
        if (dragAnchor) {
          const anchorX = tx + dragAnchor.offsetX;
          const anchorY = ty + dragAnchor.offsetY;
          let clampedAnchorX;
          let clampedAnchorY;
          if (anchorClampMode === 'inside-workarea') {
            const minAnchorX = wa.x + anchorWorkAreaInset;
            const maxAnchorX = wa.x + Math.max(0, wa.width - dragAnchor.width - anchorWorkAreaInset);
            const minAnchorY = wa.y + anchorWorkAreaTopInset;
            const maxAnchorY = wa.y + Math.max(0, wa.height - dragAnchor.height - anchorWorkAreaInset);
            clampedAnchorX = Math.max(
              minAnchorX,
              Math.min(anchorX, Math.max(minAnchorX, maxAnchorX)),
            );
            clampedAnchorY = Math.max(
              minAnchorY,
              Math.min(anchorY, Math.max(minAnchorY, maxAnchorY)),
            );
          } else {
            const minVisibleX = Math.min(minVisible, dragAnchor.width);
            const minVisibleY = Math.min(minVisible, dragAnchor.height);
            clampedAnchorX = Math.max(
              wa.x - dragAnchor.width + minVisibleX,
              Math.min(anchorX, wa.x + wa.width - minVisibleX),
            );
            clampedAnchorY = Math.max(
              wa.y - dragAnchor.height + minVisibleY,
              Math.min(anchorY, wa.y + wa.height - minVisibleY),
            );
          }
          anchorMoveRect = {
            left: Math.round(clampedAnchorX),
            top: Math.round(clampedAnchorY),
            width: dragAnchor.width,
            height: dragAnchor.height,
          };
          state.lastAnchorRect = anchorMoveRect;
          tx = clampedAnchorX - dragAnchor.offsetX;
          ty = clampedAnchorY - dragAnchor.offsetY;
        } else {
          tx = Math.max(wa.x - dragBounds.width + minVisible, Math.min(tx, wa.x + wa.width - minVisible));
          ty = Math.max(wa.y - dragBounds.height + minVisible, Math.min(ty, wa.y + wa.height - minVisible));
        }
      }
    }
    if (state.anchorDrag && anchorMoveRect) {
      try {
        event.sender.send(WINDOW_CONTROL_CHANNELS.DRAG_ANCHOR_MOVE, {
          anchorRect: anchorMoveRect,
          workArea: anchorTargetWorkArea,
        });
      } catch (_) {}
      state.timer = setTimeout(poll, DRAG_POLL_INTERVAL);
      return;
    }
    // 亚像素过滤：光标未移动则跳过 setBounds，减少无效 DWM 重组合
    if (tx !== lastX || ty !== lastY) {
      lastX = tx;
      lastY = ty;
      const t0 = performance.now();
      if (shrink) {
        win.setBounds({ x: tx, y: ty, width: shrinkSize, height: shrinkSize });
      } else {
        // 拖拽仅改变位置，使用 setBounds 并显式固定尺寸，防止 Windows 透明窗口 setPosition 引起的尺寸漂移
        win.setBounds({ x: tx, y: ty, width: dragBounds.width, height: dragBounds.height });
      }
      // 自适应间隔：setBounds 耗时长时自动降频，保证不阻塞事件循环
      const elapsed = performance.now() - t0;
      const nextInterval = Math.min(POLL_INTERVAL_CAP, Math.max(pollInterval, elapsed * 1.5) | 0);
      state.timer = setTimeout(poll, nextInterval);
    } else {
      state.timer = setTimeout(poll, pollInterval);
    }
  };

  state.timer = setTimeout(poll, pollInterval);
  _dragState.set(id, state);
  // 通知发起方暂停渲染主循环，给 DWM setBounds 腾出时间片
  broadcastInteractionState(win, true, 'drag');
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.DRAG_STOP, (event, payload) => {
  if (!isTrustedSender(event)) return;
  const { win, wasShrinkDrag } = stopWindowDrag(event, payload);
  broadcastInteractionState(win, false, 'drag');
  // shrink 模式跳过 bounceBack（全屏 Pet 窗口回弹会覆盖拖拽结果）
  if (wasShrinkDrag) return;
  if (payload && payload.skipBounceBack) return;
  // 拖拽结束后检查边界并回弹
  bounceBackToWorkArea(win);
});

ipcMain.handle(WINDOW_CONTROL_CHANNELS.DRAG_STOP_AND_GET_BOUNDS, (event, payload) => {
  if (!isTrustedSender(event)) return null;
  const { win, wasShrinkDrag, finalBounds, finalAnchorRect, dragStopBoundsMetadata, requestedBounds } = stopWindowDrag(event, payload);
  broadcastInteractionState(win, false, 'drag');
  if (!win || win.isDestroyed()) return null;
  if (payload && payload.returnAnchorRect && finalAnchorRect) {
    return {
      bounds: buildReturnBallDragStopResult(finalBounds || win.getBounds(), dragStopBoundsMetadata, wasShrinkDrag, requestedBounds),
      anchorRect: finalAnchorRect,
    };
  }
  if (wasShrinkDrag) {
    return buildReturnBallDragStopResult(finalBounds || win.getBounds(), dragStopBoundsMetadata, wasShrinkDrag, requestedBounds);
  }
  if (payload && payload.skipBounceBack) {
    return buildReturnBallDragStopResult(finalBounds || win.getBounds(), dragStopBoundsMetadata, wasShrinkDrag, requestedBounds);
  }
  bounceBackToWorkArea(win);
  return buildReturnBallDragStopResult(win.getBounds(), null, wasShrinkDrag, requestedBounds);
});

ipcMain.handle(WINDOW_CONTROL_CHANNELS.DRAG_REVEAL_AFTER_RENDERER_READY, (event) => {
  if (!isTrustedSender(event)) return false;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return false;
  const id = event.sender.id;
  const restoreBounds = _returnBallDragRestoreBounds.get(id);
  const restoreOpacity = _returnBallDragRevealOpacity.has(id)
    ? _returnBallDragRevealOpacity.get(id)
    : 1;
  try {
    const currentBounds = win.getBounds();
    if (restoreBounds && isReturnBallShrinkViewport(currentBounds)) {
      win.setBounds(restoreBounds);
      return false;
    }
    _returnBallDragRevealOpacity.delete(id);
    _returnBallDragRestoreBounds.delete(id);
    win.setOpacity(normalizeReturnBallRevealOpacity(restoreOpacity));
    return true;
  } catch (_) {
    return false;
  }
});

// ===== 主进程辅助调整大小（8 方向，递归 setTimeout 防回调堆积）=====
const _resizeState = new Map();
const RESIZE_MIN_W = 320;
const RESIZE_MIN_H = 280;

function updateSubtitlePanelBoundsFromWindow(win) {
  if (!isSubtitleWindow(win)) return;
  const bounds = win.getBounds();
  const panelBounds = normalizeSubtitlePanelBounds({
    width: bounds.width - SUBTITLE_WINDOW_EDGE_INSET * 2,
    height: bounds.height - SUBTITLE_WINDOW_EDGE_INSET * 2,
  });
  if (panelBounds) {
    win._nekoSubtitlePanelBounds = panelBounds;
  }
}

function refreshSubtitleWaylandInputShape(win) {
  if (!isSubtitleWindow(win) || !canUseSetShape(win)) return;
  if (win._nekoIgnoreMouseEvents === true) {
    win.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
    return;
  }
  const bounds = win.getBounds();
  win.setShape([{ x: 0, y: 0, width: bounds.width, height: bounds.height }]);
}

function normalizeResizeCursorPoint(point) {
  if (!point) return null;
  if (point.x == null || point.y == null) return null;
  const x = Math.round(Number(point.x));
  const y = Math.round(Number(point.y));
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function getResizeCursorPoint(state) {
  return state.lastCursor || screen.getCursorScreenPoint();
}

function applyWindowResizeFrame(win, state) {
  if (!win || win.isDestroyed() || !state || state.cancelled) return { changed: false, elapsed: 0 };
  const cur = getResizeCursorPoint(state);
  const dx = cur.x - state.startCursor.x;
  const dy = cur.y - state.startCursor.y;
  const startBounds = state.startBounds;

  let nx = startBounds.x, ny = startBounds.y;
  let nw = startBounds.width, nh = startBounds.height;

  if (state.moveE) nw = Math.max(state.minWidth, startBounds.width + dx);
  if (state.moveW) {
    nw = Math.max(state.minWidth, startBounds.width - dx);
    nx = startBounds.x + startBounds.width - nw;
  }
  if (state.moveS) nh = Math.max(state.minHeight, startBounds.height + dy);
  if (state.moveN) {
    nh = Math.max(state.minHeight, startBounds.height - dy);
    ny = startBounds.y + startBounds.height - nh;
  }

  nx = nx | 0; ny = ny | 0; nw = nw | 0; nh = nh | 0;

  if (nx === state.bounds.x && ny === state.bounds.y &&
      nw === state.bounds.width && nh === state.bounds.height) {
    return { changed: false, elapsed: 0 };
  }

  state.bounds = { x: nx, y: ny, width: nw, height: nh };
  const t0 = performance.now();
  win.setBounds(state.bounds);
  return {
    changed: true,
    elapsed: performance.now() - t0,
  };
}

ipcMain.on(WINDOW_CONTROL_CHANNELS.RESIZE_START, (event, payload) => {
  if (!isTrustedSender(event)) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win || win.isDestroyed()) return;
  const id = event.sender.id;
  cancelBounceBack(win);

  const old = _resizeState.get(id);
  if (old) { old.cancelled = true; clearTimeout(old.timer); }

  // direction 字符串由 n/s/e/w 组合，例如 'se', 'n', 'nw' 等；缺省为 'se'（向右下）
  const dir = (payload && payload.direction) || 'se';
  const moveN = dir.includes('n');
  const moveS = dir.includes('s');
  const moveW = dir.includes('w');
  const moveE = dir.includes('e');
  const defaultMinWidth = isSubtitleWindow(win) ? SUBTITLE_WINDOW_MIN_WIDTH : RESIZE_MIN_W;
  const defaultMinHeight = isSubtitleWindow(win) ? SUBTITLE_WINDOW_MIN_HEIGHT : RESIZE_MIN_H;
  const minWidth = Math.max(defaultMinWidth, Number(payload && payload.minWidth) || defaultMinWidth);
  const minHeight = Math.max(defaultMinHeight, Number(payload && payload.minHeight) || defaultMinHeight);

  const rendererStartCursor = normalizeResizeCursorPoint(payload && payload.cursor);
  const startCursor = rendererStartCursor || screen.getCursorScreenPoint();
  const startBounds = win.getBounds();
  const bounds = { x: startBounds.x, y: startBounds.y, width: startBounds.width, height: startBounds.height };
  const state = {
    timer: null,
    cancelled: false,
    startCursor,
    lastCursor: rendererStartCursor ? startCursor : null,
    startBounds,
    bounds,
    moveN,
    moveS,
    moveW,
    moveE,
    minWidth,
    minHeight,
  };

  const poll = () => {
    if (state.cancelled || !win || win.isDestroyed()) {
      _resizeState.delete(id);
      return;
    }
    const result = applyWindowResizeFrame(win, state);
    if (result.changed) {
      // 自适应间隔：setBounds 耗时长时自动降频，减少 DWM 重组合压力
      const nextInterval = Math.min(POLL_INTERVAL_CAP, Math.max(RESIZE_POLL_INTERVAL, result.elapsed * 1.5) | 0);
      state.timer = setTimeout(poll, nextInterval);
    } else {
      state.timer = setTimeout(poll, RESIZE_POLL_INTERVAL);
    }
  };

  state.timer = setTimeout(poll, RESIZE_POLL_INTERVAL);
  _resizeState.set(id, state);
  // 通知发起方暂停渲染主循环：resize 不能 shrink，全尺寸透明窗口 setBounds 最吃资源，
  // 渲染循环让出时间片对流畅度帮助最大
  broadcastInteractionState(win, true, 'resize');
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.RESIZE_MOVE, (event, payload) => {
  if (!isTrustedSender(event)) return;
  const id = event.sender.id;
  const state = _resizeState.get(id);
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!state || state.cancelled || !win || win.isDestroyed()) return;
  const cursor = normalizeResizeCursorPoint(payload);
  if (!cursor) return;
  state.lastCursor = cursor;
  applyWindowResizeFrame(win, state);
});

ipcMain.on(WINDOW_CONTROL_CHANNELS.RESIZE_STOP, (event) => {
  if (!isTrustedSender(event)) return;
  const id = event.sender.id;
  const state = _resizeState.get(id);
  const win = BrowserWindow.fromWebContents(event.sender);
  let resizeCursor = null;
  if (state) {
    clearTimeout(state.timer);
    applyWindowResizeFrame(win, state);
    resizeCursor = state.lastCursor || state.startCursor;
    state.cancelled = true;
    _resizeState.delete(id);
  }
  // 调整大小结束后检查边界并回弹
  broadcastInteractionState(win, false, 'resize');
  if (isSubtitleWindow(win)) {
    clampWindowToWorkAreaImmediate(win, resizeCursor);
    updateSubtitlePanelBoundsFromWindow(win);
    refreshSubtitleWaylandInputShape(win);
  } else {
    bounceBackToWorkArea(win);
  }
});

// ===== Subtitle 按需显示/隐藏 =====

  return {
    bindWindowDisplayRecovery,
    boundsApproximatelyEqual,
    canUseSetShape,
    getInputRegionBackend,
    getFullscreenDisplayBounds,
    getPetBottomExpandedWorkArea,
    shouldUseNativeIgnoreMouse,
  };
}

module.exports = {
  createWindowControlIpc,
};
