const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const {
  applyX11InputShape,
  queryX11PointerButtons,
} = require('./main/linux-x11-input-shape');

const OVERLAY_CHANNEL = 'neko:avatar-tool-cursor-overlay-state';
const POLL_INTERVAL_MS = 16;
const OVERLAY_RAISE_INTERVAL_MS = 250;
const NATIVE_CURSOR_REHIDE_INTERVAL_MS = 500;
const OVERLAY_X11_PASSTHROUGH_REAPPLY_DELAYS = [0, 40, 160, 500, 1200];
const X11_POINTER_DIVERGENCE_FALLBACK_PX = 96;

let electronApp = null;
let BrowserWindowRef = null;
let screenRef = null;
let log = console.log;
let getBaseUrl = () => '';
let getGlobalPointerContext = null;
let onStateRefresh = null;
let shouldSuppressNativeCursorRestore = () => false;

let overlayWindows = new Map();
let activeState = null;
let pollTimer = null;
let lastSentKey = '';
let lastStateRefreshKey = '';
let nativeCursorHidden = false;
let nativeCursorHideInFlight = false;
let nativeCursorRestoreRequired = false;
let nativeCursorRestoreGeneration = 0;
let nativeCursorDisplayIds = [];
let nativeCursorRehideTimer = null;
let platformRestoreRegistered = false;
let linuxCursorHelperUnavailableLogged = false;
let mouseButtonTracker = null;
let mouseButtonTrackerBuffer = '';
let mouseButtonTrackerStopping = false;
let mouseButtonTrackerUnavailableLogged = false;
let mouseButtonTrackerGeneration = 0;
let globalLeftMouseDown = false;
let outsideClickVisualToolId = null;
let outsideClickVisualVariant = null;
let outsideClickVisualResetTimer = null;
let lastOverlayRaiseAt = 0;
let x11PointerProbeInFlight = false;
let lastX11CursorPoint = null;
let lastX11CursorPointAt = 0;

function debugLog(...args) {
  try {
    log('[AvatarToolCursor]', ...args);
  } catch (_) {}
}

function configure(options = {}) {
  electronApp = options.app || electronApp;
  BrowserWindowRef = options.BrowserWindow || BrowserWindowRef;
  screenRef = options.screen || screenRef;
  log = options.log || log;
  getBaseUrl = typeof options.getBaseUrl === 'function' ? options.getBaseUrl : getBaseUrl;
  getGlobalPointerContext = typeof options.getGlobalPointerContext === 'function'
    ? options.getGlobalPointerContext
    : getGlobalPointerContext;
  onStateRefresh = typeof options.onStateRefresh === 'function'
    ? options.onStateRefresh
    : onStateRefresh;
  shouldSuppressNativeCursorRestore = typeof options.shouldSuppressNativeCursorRestore === 'function'
    ? options.shouldSuppressNativeCursorRestore
    : shouldSuppressNativeCursorRestore;
  if (electronApp && !platformRestoreRegistered) {
    platformRestoreRegistered = true;
    electronApp.on('before-quit', stop);
    electronApp.on('will-quit', stop);
    electronApp.on('quit', stop);
  }

  if (screenRef && typeof screenRef.on === 'function') {
    screenRef.on('display-added', handleDisplayChanged);
    screenRef.on('display-removed', handleDisplayChanged);
    screenRef.on('display-metrics-changed', handleDisplayChanged);
  }

  process.once('exit', () => {
    restoreNativeCursorSync();
  });
  process.once('SIGINT', () => {
    stop();
    process.exit(130);
  });
  process.once('SIGTERM', () => {
    stop();
    process.exit(143);
  });
}

function normalizeVariant(value) {
  return value === 'secondary' || value === 'tertiary' ? value : 'primary';
}

function isToolId(value) {
  return value === 'lollipop' || value === 'fist' || value === 'hammer';
}

function resolveImagePaths(tool, variant) {
  const resolvedVariant = normalizeVariant(variant);
  return {
    iconImagePath: resolvedVariant === 'tertiary' && tool.iconImagePathAlt2
      ? tool.iconImagePathAlt2
      : resolvedVariant === 'secondary' && tool.iconImagePathAlt
        ? tool.iconImagePathAlt
        : tool.iconImagePath,
    cursorImagePath: resolvedVariant === 'tertiary' && tool.cursorImagePathAlt2
      ? tool.cursorImagePathAlt2
      : resolvedVariant === 'secondary' && tool.cursorImagePathAlt
        ? tool.cursorImagePathAlt
        : resolvedVariant === 'tertiary' && tool.cursorImagePathAlt
          ? tool.cursorImagePathAlt
          : tool.cursorImagePath,
  };
}

function normalizeImageKind(value) {
  return value === 'icon' || value === 'hidden' ? value : 'cursor';
}

function getDefaultVisualMetrics(toolId, imageKind) {
  if (imageKind === 'icon') {
    if (toolId === 'lollipop') return { width: 74, height: 108, scale: 1 };
    if (toolId === 'fist') return { width: 100, height: 102, scale: 1 };
    if (toolId === 'hammer') return { width: 136, height: 130, scale: 1 };
  }
  if (toolId === 'lollipop') return { width: 74, height: 108, scale: 0.56 };
  if (toolId === 'fist') return { width: 78, height: 80, scale: 0.56 };
  if (toolId === 'hammer') return { width: 100, height: 96, scale: 0.52 };
  return { width: 0, height: 0, scale: 1 };
}

function normalizePositiveNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : fallback;
}

function normalizeBoolean(value) {
  return value === true;
}

function normalizePayloadCursorScreenPoint(detail) {
  const source = detail && typeof detail === 'object' ? detail : {};
  const nestedPoint = source.cursorScreenPoint && typeof source.cursorScreenPoint === 'object'
    ? source.cursorScreenPoint
    : null;
  const xSource = Number.isFinite(Number(source.cursorScreenX))
    ? source.cursorScreenX
    : Number.isFinite(Number(source.screenX))
      ? source.screenX
      : nestedPoint && Number.isFinite(Number(nestedPoint.x))
        ? nestedPoint.x
        : null;
  const ySource = Number.isFinite(Number(source.cursorScreenY))
    ? source.cursorScreenY
    : Number.isFinite(Number(source.screenY))
      ? source.screenY
      : nestedPoint && Number.isFinite(Number(nestedPoint.y))
        ? nestedPoint.y
        : null;
  const x = Number(xSource);
  const y = Number(ySource);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function shouldUseNativeCursorHide() {
  // Linux desktops can hand cursor ownership to the window under the pointer.
  // Keep tool visuals in the overlay/CSS layer there instead of fighting the WM.
  return process.platform !== 'linux';
}

function isNativeCursorHideActive() {
  return !!((activeState && shouldUseNativeCursorHide()) || nativeCursorHidden || nativeCursorHideInFlight);
}

function isLinuxXwaylandRuntime() {
  return process.platform === 'linux'
    && !!process.env.DISPLAY
    && (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
}

function isNativeWaylandRuntime() {
  return process.platform === 'linux'
    && process.env.NEKO_FORCE_X11 !== '1'
    && (!!process.env.WAYLAND_DISPLAY || process.env.XDG_SESSION_TYPE === 'wayland')
    && !process.argv.some((arg) => String(arg || '').includes('ozone-platform=x11'));
}

function shouldUseOverlayX11InputShape() {
  return process.platform === 'linux' && !!process.env.DISPLAY;
}

function shouldUseX11CursorPointProbe() {
  return process.platform === 'linux'
    && !!process.env.DISPLAY;
}

function cloneBounds(bounds) {
  const source = bounds || {};
  return {
    x: Number.isFinite(Number(source.x)) ? Math.round(Number(source.x)) : 0,
    y: Number.isFinite(Number(source.y)) ? Math.round(Number(source.y)) : 0,
    width: Number.isFinite(Number(source.width)) ? Math.max(1, Math.round(Number(source.width))) : 1,
    height: Number.isFinite(Number(source.height)) ? Math.max(1, Math.round(Number(source.height))) : 1,
  };
}

function boundsEqual(a, b) {
  const left = cloneBounds(a);
  const right = cloneBounds(b);
  return left.x === right.x
    && left.y === right.y
    && left.width === right.width
    && left.height === right.height;
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getOverlayTitle(displayId) {
  return 'N.E.K.O Avatar Tool Cursor Overlay ' + String(displayId || 'fallback');
}

function toAbsoluteAssetUrl(assetPath) {
  const value = String(assetPath || '').trim();
  if (!value) return '';
  if (/^(?:https?:|file:|data:|blob:)/i.test(value)) return value;
  try {
    return new URL(value, getBaseUrl() || 'http://localhost:48911/').href;
  } catch (_) {
    return value;
  }
}

function normalizeState(payload) {
  const detail = payload && typeof payload === 'object' ? payload : {};
  if (detail.active !== true) return null;

  const tool = detail.tool && typeof detail.tool === 'object' ? detail.tool : null;
  const toolId = isToolId(detail.toolId) ? detail.toolId : (tool && isToolId(tool.id) ? tool.id : null);
  if (!tool || !toolId) return null;

  const variant = normalizeVariant(detail.variant || detail.avatarRangeVariant || detail.outsideRangeVariant);
  const imageKind = normalizeImageKind(detail.imageKind);
  const visible = detail.visible === false || imageKind === 'hidden' ? false : true;
  const imagePaths = resolveImagePaths(tool, variant);
  const imagePath = imageKind === 'icon' ? imagePaths.iconImagePath : imagePaths.cursorImagePath;
  const imageUrl = visible ? toAbsoluteAssetUrl(imagePath) : '';
  if (visible && !imageUrl) return null;
  const metrics = getDefaultVisualMetrics(toolId, imageKind);

  return {
    active: true,
    toolId,
    tool,
    variant,
    imageKind,
    visible,
    imageUrl,
    hotspotX: Number.isFinite(Number(tool.cursorHotspotX)) ? Number(tool.cursorHotspotX) : 18,
    hotspotY: Number.isFinite(Number(tool.cursorHotspotY)) ? Number(tool.cursorHotspotY) : 18,
    naturalWidth: normalizePositiveNumber(tool.cursorNaturalWidth, metrics.width),
    naturalHeight: normalizePositiveNumber(tool.cursorNaturalHeight, metrics.height),
    displayWidth: normalizePositiveNumber(detail.displayWidth, metrics.width),
    displayHeight: normalizePositiveNumber(detail.displayHeight, metrics.height),
    scale: normalizePositiveNumber(detail.scale, metrics.scale),
    withinAvatarRange: normalizeBoolean(detail.withinAvatarRange),
    overCompactZone: normalizeBoolean(detail.overCompactZone),
    overChatWindow: normalizeBoolean(detail.overChatWindow),
    outsideViewport: normalizeBoolean(detail.outsideViewport),
    insideHostWindow: normalizeBoolean(detail.insideHostWindow),
    cursorScreenPoint: normalizePayloadCursorScreenPoint(detail),
  };
}

function setState(payload) {
  const nextState = normalizeState(payload);
  if (!nextState) {
    stop();
    return;
  }

  if (!activeState || activeState.toolId !== nextState.toolId) {
    clearOutsideClickVisualState(false);
  }
  activeState = nextState;
  if (shouldUseNativeCursorHide()) {
    hideNativeCursor();
    startNativeCursorRehideTimer();
  } else {
    stopNativeCursorRehideTimer();
    restoreNativeCursor();
  }
  if (isNativeWaylandRuntime()) {
    // Native Wayland compositors can still route pointer ownership to a
    // transparent always-on-top BrowserWindow. Keep the visual cursor in an
    // existing renderer window instead of creating another native surface.
    destroyOverlayWindow();
    startPoller();
    stopMouseButtonTracker();
    lastSentKey = '';
    return;
  }
  ensureOverlayWindow();
  startMouseButtonTracker();
  startPoller();
  sendOverlayState(true);
}

function stop() {
  activeState = null;
  lastSentKey = '';
  lastStateRefreshKey = '';
  clearOutsideClickVisualState(false);
  stopPoller();
  stopMouseButtonTracker();
  sendOverlayInactive();
  destroyOverlayWindow();
  stopNativeCursorRehideTimer();
  restoreNativeCursor();
}

function getVirtualBounds() {
  if (!screenRef || typeof screenRef.getAllDisplays !== 'function') {
    return { x: 0, y: 0, width: 1, height: 1 };
  }
  const displays = screenRef.getAllDisplays();
  if (!displays || displays.length === 0) {
    return { x: 0, y: 0, width: 1, height: 1 };
  }
  const minX = Math.min(...displays.map((display) => display.bounds.x));
  const minY = Math.min(...displays.map((display) => display.bounds.y));
  const maxX = Math.max(...displays.map((display) => display.bounds.x + display.bounds.width));
  const maxY = Math.max(...displays.map((display) => display.bounds.y + display.bounds.height));
  return {
    x: minX,
    y: minY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
  };
}

function getOverlayDisplays() {
  if (!screenRef || typeof screenRef.getAllDisplays !== 'function') {
    return [{ id: 'fallback', bounds: getVirtualBounds() }];
  }
  const displays = screenRef.getAllDisplays();
  if (!displays || displays.length === 0) {
    return [{ id: 'fallback', bounds: getVirtualBounds() }];
  }
  return displays.map((display, index) => ({
    id: String(display.id == null ? index : display.id),
    bounds: display.bounds || { x: 0, y: 0, width: 1, height: 1 },
    scaleFactor: normalizePositiveNumber(display.scaleFactor, 1),
  }));
}

function getDisplayForPoint(point) {
  const displays = getOverlayDisplays();
  if (!point || !Number.isFinite(Number(point.x)) || !Number.isFinite(Number(point.y))) {
    return displays[0] || null;
  }
  const x = Number(point.x);
  const y = Number(point.y);
  for (const display of displays) {
    const bounds = display.bounds;
    if (
      x >= bounds.x
      && x < bounds.x + bounds.width
      && y >= bounds.y
      && y < bounds.y + bounds.height
    ) {
      return display;
    }
  }
  if (screenRef && typeof screenRef.getDisplayNearestPoint === 'function') {
    try {
      const nearest = screenRef.getDisplayNearestPoint({ x, y });
      if (nearest) {
        const nearestId = String(nearest.id == null ? '' : nearest.id);
        return displays.find(display => display.id === nearestId) || {
          id: nearestId || 'nearest',
          bounds: nearest.bounds || displays[0].bounds,
        };
      }
    } catch (_) {}
  }
  return displays[0] || null;
}

function getOverlayHtml(title = 'N.E.K.O Avatar Tool Cursor Overlay') {
  return [
    '<!doctype html>',
    '<html>',
    '<head>',
    '<meta charset="utf-8">',
    '<title>' + escapeHtml(title) + '</title>',
    '<style>',
    'html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: transparent; pointer-events: none; cursor: none !important; }',
    'html *, body * { cursor: none !important; }',
    '#cursor-image { position: fixed; left: 0; top: 0; pointer-events: none; user-select: none; -webkit-user-drag: none; will-change: transform; transform-origin: 0 0; cursor: none !important; }',
    '</style>',
    '</head>',
    '<body>',
    '<img id="cursor-image" hidden draggable="false" alt="">',
    '</body>',
    '</html>',
  ].join('');
}

function setOverlayPointerPassthrough(win) {
  if (!win || (typeof win.isDestroyed === 'function' && win.isDestroyed())) return;
  try {
    win.setIgnoreMouseEvents(true);
  } catch (_) {}
}

function getOverlayWindowScaleFactor(win) {
  try {
    if (!screenRef || typeof screenRef.getDisplayMatching !== 'function') return 1;
    const display = screenRef.getDisplayMatching(win.getBounds());
    return display && Number.isFinite(display.scaleFactor) ? display.scaleFactor : 1;
  } catch (_) {
    return 1;
  }
}

function clearOverlayX11PassthroughTimers(entry) {
  if (!entry || !Array.isArray(entry.x11PassthroughTimers)) return;
  entry.x11PassthroughTimers.forEach((timer) => clearTimeout(timer));
  entry.x11PassthroughTimers = [];
}

function scheduleOverlayX11Passthrough(entry, reason) {
  if (!shouldUseOverlayX11InputShape()) return;
  if (!entry || !entry.window || entry.window.isDestroyed()) return;

  clearOverlayX11PassthroughTimers(entry);
  const token = (entry.x11PassthroughToken || 0) + 1;
  entry.x11PassthroughToken = token;
  entry.x11PassthroughTimers = [];

  const applyPassthrough = () => {
    if (!entry || entry.x11PassthroughToken !== token) return;
    const win = entry.window;
    if (!win || win.isDestroyed()) return;
    applyX11InputShape(win, [], {
      log,
      scaleFactor: getOverlayWindowScaleFactor(win),
      allowNativeFallback: !isLinuxXwaylandRuntime(),
    }).then((ok) => {
      if (ok && entry.x11PassthroughToken === token) {
        entry.x11PassthroughReady = true;
      }
    }).catch((error) => {
      debugLog('X11 overlay passthrough failed:', reason || 'apply', error && error.message ? error.message : error);
    });
  };

  OVERLAY_X11_PASSTHROUGH_REAPPLY_DELAYS.forEach((delay) => {
    const timer = setTimeout(applyPassthrough, delay);
    entry.x11PassthroughTimers.push(timer);
    try { timer.unref(); } catch (_) {}
  });
}

function showOverlayWindow(entry, reason) {
  if (!entry || !entry.window || entry.window.isDestroyed()) return;
  if (entry.shown === true) return;
  const win = entry.window;
  try {
    setOverlayPointerPassthrough(win);
    if (typeof win.showInactive === 'function') {
      win.showInactive();
    } else {
      win.show();
    }
    entry.shown = true;
    setOverlayPointerPassthrough(win);
    scheduleOverlayX11Passthrough(entry, reason || 'show');
  } catch (_) {}
}

function createOverlayWindowForDisplay(display) {
  const bounds = cloneBounds(display.bounds || { x: 0, y: 0, width: 1, height: 1 });
  const title = getOverlayTitle(display.id);
  const overlay = new BrowserWindowRef({
    ...bounds,
    title,
    transparent: true,
    frame: false,
    thickFrame: false,
    backgroundColor: '#00000000',
    hasShadow: false,
    skipTaskbar: true,
    focusable: false,
    resizable: false,
    movable: false,
    fullscreenable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload-avatar-tool-cursor-overlay.js'),
      nodeIntegration: false,
      contextIsolation: false,
      sandbox: false,
      backgroundThrottling: false,
    },
  });

  const entry = {
    id: display.id,
    bounds,
    window: overlay,
    ready: false,
    shown: false,
    lastKey: '',
    x11PassthroughReady: false,
    x11PassthroughTimers: [],
    x11PassthroughToken: 0,
  };

  try {
    setOverlayPointerPassthrough(overlay);
    overlay.setAlwaysOnTop(true, 'screen-saver');
  } catch (_) {}

  overlay.webContents.once('did-finish-load', () => {
    entry.ready = true;
    showOverlayWindow(entry, 'load');
    sendOverlayState(true);
  });
  overlay.on('closed', () => {
    clearOverlayX11PassthroughTimers(entry);
    entry.x11PassthroughToken += 1;
    overlayWindows.delete(display.id);
  });

  overlay.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(getOverlayHtml(title)));
  return entry;
}

function ensureOverlayWindow() {
  if (!BrowserWindowRef || !screenRef) return null;

  const displays = getOverlayDisplays();
  const activeDisplayIds = new Set(displays.map(display => display.id));
  for (const [displayId, entry] of overlayWindows.entries()) {
    if (activeDisplayIds.has(displayId)) continue;
    try {
      if (entry.window && !entry.window.isDestroyed()) entry.window.destroy();
    } catch (_) {}
    overlayWindows.delete(displayId);
  }

  displays.forEach((display) => {
    let entry = overlayWindows.get(display.id);
    if (!entry || !entry.window || entry.window.isDestroyed()) {
      entry = createOverlayWindowForDisplay(display);
      overlayWindows.set(display.id, entry);
      return;
    }
    const nextBounds = cloneBounds(display.bounds);
    if (!boundsEqual(entry.bounds, nextBounds)) {
      entry.bounds = nextBounds;
      try {
        entry.window.setBounds(nextBounds);
        setOverlayPointerPassthrough(entry.window);
        entry.window.setAlwaysOnTop(true, 'screen-saver');
        scheduleOverlayX11Passthrough(entry, 'bounds');
      } catch (_) {}
    }
    if (entry.ready) {
      showOverlayWindow(entry, 'ensure');
    }
  });

  return overlayWindows;
}

function raiseOverlayWindows(force = false) {
  if (!force) return;
  if (process.platform === 'linux') return;
  const now = Date.now();
  if (now - lastOverlayRaiseAt < OVERLAY_RAISE_INTERVAL_MS) return;
  lastOverlayRaiseAt = now;

  for (const entry of overlayWindows.values()) {
    try {
      if (!entry.window || entry.window.isDestroyed()) continue;
      setOverlayPointerPassthrough(entry.window);
      entry.window.setAlwaysOnTop(true, 'screen-saver');
      entry.window.moveTop();
      setOverlayPointerPassthrough(entry.window);
    } catch (_) {}
  }
}

function destroyOverlayWindow() {
  for (const entry of overlayWindows.values()) {
    clearOverlayX11PassthroughTimers(entry);
    entry.x11PassthroughToken += 1;
    try {
      if (entry.window && !entry.window.isDestroyed()) entry.window.destroy();
    } catch (_) {}
  }
  overlayWindows = new Map();
}

function normalizeCursorPoint(point) {
  if (!point) return null;
  const x = Number(point.x);
  const y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function distanceBetweenPoints(a, b) {
  if (!a || !b) return Number.POSITIVE_INFINITY;
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function getPhysicalDisplayBounds(display) {
  if (!display || !display.bounds) return null;
  const scaleFactor = normalizePositiveNumber(display.scaleFactor, 1);
  const bounds = display.bounds;
  return {
    x: bounds.x * scaleFactor,
    y: bounds.y * scaleFactor,
    width: bounds.width * scaleFactor,
    height: bounds.height * scaleFactor,
    scaleFactor,
  };
}

function isPointInBounds(point, bounds) {
  if (!point || !bounds) return false;
  return point.x >= bounds.x
    && point.x < bounds.x + bounds.width
    && point.y >= bounds.y
    && point.y < bounds.y + bounds.height;
}

function convertPhysicalPointToDisplayPoint(point, display) {
  const physicalBounds = getPhysicalDisplayBounds(display);
  if (!physicalBounds || !isPointInBounds(point, physicalBounds)) return null;
  const scaleFactor = physicalBounds.scaleFactor;
  const bounds = display.bounds;
  return {
    x: bounds.x + ((point.x - physicalBounds.x) / scaleFactor),
    y: bounds.y + ((point.y - physicalBounds.y) / scaleFactor),
  };
}

function normalizeX11CursorPoint(point, electronPoint) {
  const rawPoint = normalizeCursorPoint(point);
  if (!rawPoint) return null;
  if (!electronPoint) return rawPoint;

  const displays = getOverlayDisplays();
  const candidates = [rawPoint];
  displays.forEach((display) => {
    const converted = convertPhysicalPointToDisplayPoint(rawPoint, display);
    if (converted) candidates.push(converted);
  });

  const closest = candidates.reduce((best, candidate) => (
    distanceBetweenPoints(candidate, electronPoint) < distanceBetweenPoints(best, electronPoint)
      ? candidate
      : best
  ), candidates[0]);

  // On XWayland, Electron's cursor point can freeze at the last X surface
  // coordinate once the pointer leaves app windows. Keep X11 as the global
  // source there instead of snapping the overlay back to the stale Electron
  // point.
  if (isLinuxXwaylandRuntime()) return closest;

  return distanceBetweenPoints(closest, electronPoint) <= X11_POINTER_DIVERGENCE_FALLBACK_PX
    ? closest
    : electronPoint;
}

function pollX11CursorPoint() {
  if (!shouldUseX11CursorPointProbe() || x11PointerProbeInFlight) return;
  x11PointerProbeInFlight = true;
  queryX11PointerButtons(log, {
    readyTimeoutMs: 16,
    timeoutMs: 16,
  }).then((point) => {
    const normalized = normalizeCursorPoint(point);
    if (normalized) {
      lastX11CursorPoint = normalized;
      lastX11CursorPointAt = Date.now();
    }
  }).catch(() => {
    // Electron's cursor point remains the fallback when the X11 helper is busy.
  }).finally(() => {
    x11PointerProbeInFlight = false;
  });
}

function getRecentX11CursorPoint() {
  if (!shouldUseX11CursorPointProbe()) return null;
  if (!lastX11CursorPoint || Date.now() - lastX11CursorPointAt > 80) return null;
  return lastX11CursorPoint;
}

function getOverlayCursorScreenPoint() {
  const electronPoint = normalizeCursorPoint(screenRef && screenRef.getCursorScreenPoint
    ? screenRef.getCursorScreenPoint()
    : null);
  pollX11CursorPoint();
  const x11Point = getRecentX11CursorPoint();
  if (x11Point) {
    return normalizeX11CursorPoint(x11Point, electronPoint);
  }
  return electronPoint || { x: 0, y: 0 };
}

function buildStateRefreshKey(state) {
  if (!state) return 'inactive';
  const point = normalizeCursorPoint(state.cursorScreenPoint);
  return [
    state.active === true ? 'active' : 'inactive',
    state.toolId || '',
    state.variant || '',
    state.imageKind || '',
    state.visible === false ? 'hidden' : 'visible',
    normalizeBoolean(state.withinAvatarRange),
    normalizeBoolean(state.overCompactZone),
    normalizeBoolean(state.overChatWindow),
    normalizeBoolean(state.outsideViewport),
    normalizeBoolean(state.insideHostWindow),
    point ? Math.round(point.x) : 'no-x',
    point ? Math.round(point.y) : 'no-y',
    state.displayWidth || '',
    state.displayHeight || '',
    state.scale || '',
  ].join('|');
}

function notifyStateRefresh(force) {
  if (!isNativeWaylandRuntime() || typeof onStateRefresh !== 'function') return;
  const key = buildStateRefreshKey(activeState);
  if (!force && key === lastStateRefreshKey) return;
  lastStateRefreshKey = key;
  try {
    onStateRefresh(activeState ? { ...activeState } : null);
  } catch (_) {}
}

function getRendererCursorScreenPoint() {
  if (isNativeWaylandRuntime()) {
    return normalizeCursorPoint(screenRef && screenRef.getCursorScreenPoint
      ? screenRef.getCursorScreenPoint()
      : null);
  }
  return normalizeCursorPoint(getOverlayCursorScreenPoint());
}

function refreshActivePolledState() {
  if (!activeState || !screenRef || typeof screenRef.getCursorScreenPoint !== 'function') return activeState;
  const point = getRendererCursorScreenPoint();
  if (!point) return activeState;
  let nextState = {
    ...activeState,
    cursorScreenPoint: point,
    screenX: point.x,
    screenY: point.y,
    cursorScreenX: point.x,
    cursorScreenY: point.y,
  };
  if (typeof getGlobalPointerContext === 'function') {
    try {
      const context = getGlobalPointerContext(point);
      if (context && typeof context === 'object') {
        nextState = {
          ...nextState,
          overChatWindow: normalizeBoolean(context.overChatWindow),
          insideHostWindow: normalizeBoolean(context.insideHostWindow),
        };
      }
    } catch (_) {}
  }
  activeState = nextState;
  notifyStateRefresh(false);
  return activeState;
}

function startPoller() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    refreshActivePolledState();
    if (!isNativeWaylandRuntime()) {
      sendOverlayState(false);
    }
  }, POLL_INTERVAL_MS);
  try { pollTimer.unref(); } catch (_) {}
}

function stopPoller() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

function clearOutsideClickVisualState(shouldSend) {
  if (outsideClickVisualResetTimer) {
    clearTimeout(outsideClickVisualResetTimer);
    outsideClickVisualResetTimer = null;
  }
  outsideClickVisualToolId = null;
  outsideClickVisualVariant = null;
  if (shouldSend) {
    sendOverlayState(true);
  }
}

function canUseOutsideClickVisual(state) {
  return !!state
    && state.active === true
    && state.visible !== false
    && state.withinAvatarRange !== true
    && state.overCompactZone !== true
    && state.overChatWindow !== true
    && state.insideHostWindow !== true
    && (state.toolId === 'fist' || state.toolId === 'hammer');
}

function refreshActiveGlobalPointerContext() {
  if (!activeState || typeof getGlobalPointerContext !== 'function') return activeState;
  try {
    const context = getGlobalPointerContext(activeState.cursorScreenPoint || getOverlayCursorScreenPoint());
    if (!context || typeof context !== 'object') return activeState;
    const nextState = {
      ...activeState,
      overChatWindow: normalizeBoolean(context.overChatWindow),
      insideHostWindow: normalizeBoolean(context.insideHostWindow),
    };
    if (
      nextState.overChatWindow !== activeState.overChatWindow
      || nextState.insideHostWindow !== activeState.insideHostWindow
    ) {
      activeState = nextState;
    }
  } catch (_) {}
  return activeState;
}

function scheduleOutsideHammerVisualReset() {
  if (outsideClickVisualResetTimer) {
    clearTimeout(outsideClickVisualResetTimer);
  }
  outsideClickVisualResetTimer = setTimeout(() => {
    outsideClickVisualResetTimer = null;
    if (outsideClickVisualToolId === 'hammer') {
      outsideClickVisualToolId = null;
      outsideClickVisualVariant = null;
      sendOverlayState(true);
    }
  }, 220);
  try { outsideClickVisualResetTimer.unref(); } catch (_) {}
}

function handleGlobalLeftMouseChange(isDown) {
  if (globalLeftMouseDown === isDown) return;
  globalLeftMouseDown = isDown;

  if (!activeState) {
    clearOutsideClickVisualState(false);
    return;
  }

  if (isDown) {
    const currentState = refreshActiveGlobalPointerContext();
    if (!canUseOutsideClickVisual(currentState)) return;
    if (currentState.toolId === 'fist') {
      outsideClickVisualToolId = 'fist';
      outsideClickVisualVariant = 'secondary';
      sendOverlayState(true);
      return;
    }
    if (currentState.toolId === 'hammer') {
      outsideClickVisualToolId = 'hammer';
      outsideClickVisualVariant = 'secondary';
      sendOverlayState(true);
      scheduleOutsideHammerVisualReset();
    }
    return;
  }

  if (outsideClickVisualToolId === 'fist') {
    clearOutsideClickVisualState(true);
  }
}

function getOutsideClickVisualVariant(state) {
  if (!outsideClickVisualToolId || !outsideClickVisualVariant) return null;
  if (!canUseOutsideClickVisual(state)) return null;
  if (state.toolId !== outsideClickVisualToolId) return null;
  return outsideClickVisualVariant;
}

function buildOverlayVisualState(state) {
  if (!state) return null;
  const visualVariant = getOutsideClickVisualVariant(state) || state.variant;
  if (visualVariant === state.variant) return state;

  const imagePaths = resolveImagePaths(state.tool, visualVariant);
  const imagePath = state.imageKind === 'icon' ? imagePaths.iconImagePath : imagePaths.cursorImagePath;
  const imageUrl = state.visible === false ? '' : toAbsoluteAssetUrl(imagePath);
  if (state.visible !== false && !imageUrl) return state;
  return {
    ...state,
    variant: visualVariant,
    imageUrl,
  };
}

function sendOverlayInactive() {
  for (const entry of overlayWindows.values()) {
    if (!entry.window || entry.window.isDestroyed() || !entry.ready) continue;
    entry.lastKey = 'inactive';
    try {
      entry.window.webContents.send(OVERLAY_CHANNEL, { active: false });
    } catch (_) {}
  }
}

function sendOverlayState(force) {
  if (!activeState || !screenRef) return;
  ensureOverlayWindow();
  if (overlayWindows.size === 0) return;
  raiseOverlayWindows(!!force);

  const visualState = buildOverlayVisualState(activeState);
  if (!visualState) return;

  const point = visualState.cursorScreenPoint || getOverlayCursorScreenPoint();
  const activeDisplay = getDisplayForPoint(point);
  if (!activeDisplay) return;

  for (const entry of overlayWindows.values()) {
    if (!entry.window || entry.window.isDestroyed() || !entry.ready) continue;
    const isCursorDisplay = entry.id === activeDisplay.id;
    const bounds = entry.bounds || activeDisplay.bounds || getVirtualBounds();
    const x = point.x - bounds.x;
    const y = point.y - bounds.y;
    const key = isCursorDisplay && visualState.visible !== false
      ? [
        Math.round(x),
        Math.round(y),
        visualState.toolId,
        visualState.variant,
        visualState.imageKind,
        visualState.visible,
        visualState.imageUrl,
        visualState.hotspotX,
        visualState.hotspotY,
        visualState.naturalWidth,
        visualState.naturalHeight,
        visualState.displayWidth,
        visualState.displayHeight,
        visualState.scale,
      ].join('|')
      : 'inactive';
    if (!force && entry.lastKey === key) continue;
    entry.lastKey = key;

    try {
      if (!isCursorDisplay || visualState.visible === false) {
        entry.window.webContents.send(OVERLAY_CHANNEL, { active: false });
      } else {
        entry.window.webContents.send(OVERLAY_CHANNEL, {
          active: true,
          x,
          y,
          imageUrl: visualState.imageUrl,
          hotspotX: visualState.hotspotX,
          hotspotY: visualState.hotspotY,
          naturalWidth: visualState.naturalWidth,
          naturalHeight: visualState.naturalHeight,
          displayWidth: visualState.displayWidth,
          displayHeight: visualState.displayHeight,
          scale: visualState.scale,
        });
      }
    } catch (_) {}
  }

  lastSentKey = Array.from(overlayWindows.values())
    .map(entry => entry.id + ':' + entry.lastKey)
    .join(';');
}

function handleDisplayChanged() {
  if (!activeState) return;
  ensureOverlayWindow();
  for (const entry of overlayWindows.values()) {
    entry.lastKey = '';
  }
  sendOverlayState(true);
  if (nativeCursorHidden && process.platform === 'darwin') {
    restoreNativeCursor();
    hideNativeCursor(true);
  }
}

function getPowershellExecutable() {
  if (process.env.SystemRoot) {
    return path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  }
  return 'powershell.exe';
}

function getWindowsCursorScript(action) {
  if (action === 'restore') {
    return [
      '$ErrorActionPreference = "SilentlyContinue"',
      'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; public static class NekoCursorRestore { [DllImport("user32.dll", SetLastError=true)] public static extern bool SystemParametersInfo(uint action, uint param, IntPtr value, uint flags); }\'',
      '[NekoCursorRestore]::SystemParametersInfo(0x0057, 0, [IntPtr]::Zero, 0) | Out-Null',
    ].join('; ');
  }

  return [
    '$ErrorActionPreference = "Stop"',
    'Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @\'',
    'using System;',
    'using System.Drawing;',
    'using System.Drawing.Imaging;',
    'using System.Runtime.InteropServices;',
    'public static class NekoCursorHide {',
    '  [StructLayout(LayoutKind.Sequential)] public struct ICONINFO { public bool fIcon; public int xHotspot; public int yHotspot; public IntPtr hbmMask; public IntPtr hbmColor; }',
    '  [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr CreateIconIndirect(ref ICONINFO icon);',
    '  [DllImport("user32.dll", SetLastError=true)] public static extern bool SetSystemCursor(IntPtr cursor, uint id);',
    '  [DllImport("gdi32.dll", SetLastError=true)] public static extern bool DeleteObject(IntPtr obj);',
    '  static IntPtr CreateBlankCursor() {',
    '    using (Bitmap bitmap = new Bitmap(1, 1, PixelFormat.Format32bppArgb)) {',
    '      IntPtr hbm = bitmap.GetHbitmap(Color.FromArgb(0, 0, 0, 0));',
    '      ICONINFO info = new ICONINFO();',
    '      info.fIcon = false; info.xHotspot = 0; info.yHotspot = 0; info.hbmMask = hbm; info.hbmColor = hbm;',
    '      IntPtr cursor = CreateIconIndirect(ref info);',
    '      DeleteObject(hbm);',
    '      return cursor;',
    '    }',
    '  }',
    '  public static void Hide() {',
    '    uint[] ids = new uint[] { 32512, 32513, 32514, 32515, 32516, 32640, 32641, 32642, 32643, 32644, 32645, 32646, 32648, 32649, 32650, 32651, 32671, 32672 };',
    '    foreach (uint id in ids) { SetSystemCursor(CreateBlankCursor(), id); }',
    '  }',
    '}',
    '\'@',
    '[NekoCursorHide]::Hide()',
  ].join('\n');
}

function getMacDisplayIds() {
  if (!screenRef || typeof screenRef.getAllDisplays !== 'function') return [];
  const ids = screenRef.getAllDisplays()
    .map((display) => Number(display.id))
    .filter((id) => Number.isFinite(id) && id > 0);
  return ids.length > 0 ? ids : [0];
}

function getMacCursorScript(action, displayIds) {
  const fn = action === 'restore' ? 'CGDisplayShowCursor' : 'CGDisplayHideCursor';
  const ids = (displayIds && displayIds.length ? displayIds : getMacDisplayIds())
    .map((id) => Math.trunc(id))
    .filter((id) => Number.isFinite(id));
  const list = ids.length ? ids : [0];
  return 'ObjC.import("CoreGraphics"); [' + list.join(',') + '].forEach(function(id) { $.'
    + fn + '(id || $.CGMainDisplayID()); });';
}

function getLinuxPythonExecutable() {
  const candidates = ['python3', 'python'];
  for (const candidate of candidates) {
    const result = spawnSync(candidate, ['--version'], { stdio: 'ignore', timeout: 1000 });
    if (result.status === 0) return candidate;
  }
  return '';
}

function getLinuxCursorScript(action) {
  const fn = action === 'restore' ? 'XFixesShowCursor' : 'XFixesHideCursor';
  return [
    'import ctypes, os, sys',
    'display_name = os.environ.get("DISPLAY")',
    'if not display_name:',
    '    sys.exit(2)',
    'x11 = ctypes.CDLL("libX11.so.6")',
    'xfixes = ctypes.CDLL("libXfixes.so.3")',
    'x11.XOpenDisplay.argtypes = [ctypes.c_char_p]',
    'x11.XOpenDisplay.restype = ctypes.c_void_p',
    'x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]',
    'x11.XDefaultRootWindow.restype = ctypes.c_ulong',
    'x11.XFlush.argtypes = [ctypes.c_void_p]',
    'x11.XCloseDisplay.argtypes = [ctypes.c_void_p]',
    'display = x11.XOpenDisplay(display_name.encode())',
    'if not display:',
    '    sys.exit(3)',
    'root = x11.XDefaultRootWindow(display)',
    'cursor_fn = getattr(xfixes, "' + fn + '")',
    'cursor_fn.argtypes = [ctypes.c_void_p, ctypes.c_ulong]',
    'cursor_fn(display, root)',
    'x11.XFlush(display)',
    'x11.XCloseDisplay(display)',
  ].join('\n');
}

function getWindowsMouseButtonScript() {
  return [
    '$ErrorActionPreference = "Stop"',
    'Add-Type -TypeDefinition @\'',
    'using System;',
    'using System.Runtime.InteropServices;',
    'public static class NekoMouseButtonState {',
    '  [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vKey);',
    '}',
    '\'@',
    '$last = -1',
    'while ($true) {',
    '  $state = [int]([NekoMouseButtonState]::GetAsyncKeyState(0x01))',
    '  $value = if (($state -band 0x8000) -ne 0) { 1 } else { 0 }',
    '  if ($value -ne $last) { [Console]::Out.WriteLine($value); [Console]::Out.Flush(); $last = $value }',
    '  Start-Sleep -Milliseconds 16',
    '}',
  ].join('\n');
}

function getMacMouseButtonScript() {
  return [
    'ObjC.import("CoreGraphics");',
    'ObjC.import("Foundation");',
    'var out = $.NSFileHandle.fileHandleWithStandardOutput;',
    'var enc = $.NSUTF8StringEncoding;',
    'var last = -1;',
    'while (true) {',
    '  var down = $.CGEventSourceButtonState(0, 0);',
    '  var value = down ? 1 : 0;',
    '  if (value !== last) {',
    '    out.writeData($.NSString.stringWithString(String(value) + "\\n").dataUsingEncoding(enc));',
    '    last = value;',
    '  }',
    '  $.NSThread.sleepForTimeInterval(0.016);',
    '}',
  ].join('\n');
}

function getLinuxMouseButtonScript() {
  return [
    'import ctypes, os, sys, time',
    'display_name = os.environ.get("DISPLAY")',
    'if not display_name:',
    '    sys.exit(2)',
    'x11 = ctypes.CDLL("libX11.so.6")',
    'x11.XOpenDisplay.argtypes = [ctypes.c_char_p]',
    'x11.XOpenDisplay.restype = ctypes.c_void_p',
    'x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]',
    'x11.XDefaultRootWindow.restype = ctypes.c_ulong',
    'x11.XQueryPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)]',
    'x11.XQueryPointer.restype = ctypes.c_int',
    'x11.XCloseDisplay.argtypes = [ctypes.c_void_p]',
    'display = x11.XOpenDisplay(display_name.encode())',
    'if not display:',
    '    sys.exit(3)',
    'root = x11.XDefaultRootWindow(display)',
    'root_return = ctypes.c_ulong()',
    'child_return = ctypes.c_ulong()',
    'root_x = ctypes.c_int()',
    'root_y = ctypes.c_int()',
    'win_x = ctypes.c_int()',
    'win_y = ctypes.c_int()',
    'mask = ctypes.c_uint()',
    'last = -1',
    'try:',
    '    while True:',
    '        ok = x11.XQueryPointer(display, root, ctypes.byref(root_return), ctypes.byref(child_return), ctypes.byref(root_x), ctypes.byref(root_y), ctypes.byref(win_x), ctypes.byref(win_y), ctypes.byref(mask))',
    '        value = 1 if ok and (mask.value & (1 << 8)) else 0',
    '        if value != last:',
    '            print(value, flush=True)',
    '            last = value',
    '        time.sleep(0.016)',
    'finally:',
    '    x11.XCloseDisplay(display)',
  ].join('\n');
}

function getMouseButtonTrackerCommand() {
  if (process.platform === 'win32') {
    return {
      command: getPowershellExecutable(),
      args: ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', getWindowsMouseButtonScript()],
      options: { windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] },
    };
  }
  if (process.platform === 'darwin') {
    return {
      command: 'osascript',
      args: ['-l', 'JavaScript', '-e', getMacMouseButtonScript()],
      options: { stdio: ['ignore', 'pipe', 'ignore'] },
    };
  }
  if (process.platform === 'linux') {
    const python = getLinuxPythonExecutable();
    if (!python) return null;
    return {
      command: python,
      args: ['-u', '-c', getLinuxMouseButtonScript()],
      options: { stdio: ['ignore', 'pipe', 'ignore'] },
    };
  }
  return null;
}

function parseMouseButtonTrackerData(data) {
  mouseButtonTrackerBuffer += String(data || '');
  const lines = mouseButtonTrackerBuffer.split(/\r?\n/);
  mouseButtonTrackerBuffer = lines.pop() || '';
  for (const line of lines) {
    const value = line.trim();
    if (value === '1') {
      handleGlobalLeftMouseChange(true);
    } else if (value === '0') {
      handleGlobalLeftMouseChange(false);
    }
  }
}

function startMouseButtonTracker() {
  if (mouseButtonTracker || mouseButtonTrackerUnavailableLogged) return;
  const command = getMouseButtonTrackerCommand();
  if (!command) {
    if (!mouseButtonTrackerUnavailableLogged) {
      mouseButtonTrackerUnavailableLogged = true;
      debugLog('Global mouse button tracker is unavailable on this platform/session; outside desktop click visual switching is disabled.');
    }
    return;
  }

  try {
    mouseButtonTrackerStopping = false;
    mouseButtonTrackerBuffer = '';
    const trackerGeneration = mouseButtonTrackerGeneration + 1;
    mouseButtonTrackerGeneration = trackerGeneration;
    const child = spawn(command.command, command.args, command.options);
    mouseButtonTracker = child;
    if (child.stdout) {
      child.stdout.setEncoding('utf8');
      child.stdout.on('data', parseMouseButtonTrackerData);
    }
    child.on('error', (error) => {
      if (trackerGeneration !== mouseButtonTrackerGeneration) return;
      if (!mouseButtonTrackerStopping) {
        mouseButtonTrackerUnavailableLogged = true;
        debugLog('Global mouse button tracker failed:', error.message);
      }
    });
    child.on('close', (code) => {
      if (trackerGeneration !== mouseButtonTrackerGeneration) return;
      mouseButtonTracker = null;
      mouseButtonTrackerBuffer = '';
      globalLeftMouseDown = false;
      clearOutsideClickVisualState(true);
      if (!mouseButtonTrackerStopping && code !== 0 && !mouseButtonTrackerUnavailableLogged) {
        mouseButtonTrackerUnavailableLogged = true;
        debugLog('Global mouse button tracker exited with code ' + code + '; outside desktop click visual switching is disabled.');
      }
      mouseButtonTrackerStopping = false;
    });
    try { child.unref(); } catch (_) {}
  } catch (error) {
    mouseButtonTracker = null;
    mouseButtonTrackerUnavailableLogged = true;
    debugLog('Global mouse button tracker failed:', error.message || error);
  }
}

function stopMouseButtonTracker() {
  globalLeftMouseDown = false;
  if (!mouseButtonTracker) {
    mouseButtonTrackerBuffer = '';
    return;
  }
  const child = mouseButtonTracker;
  mouseButtonTrackerGeneration += 1;
  mouseButtonTrackerStopping = true;
  try {
    child.kill();
  } catch (_) {}
  mouseButtonTracker = null;
  mouseButtonTrackerBuffer = '';
  mouseButtonTrackerStopping = false;
}

function startNativeCursorRehideTimer() {
  if (!shouldUseNativeCursorHide()) return;
  if (nativeCursorRehideTimer) return;
  nativeCursorRehideTimer = setInterval(() => {
    if (!activeState) {
      stopNativeCursorRehideTimer();
      return;
    }
    if (!shouldUseNativeCursorHide()) {
      stopNativeCursorRehideTimer();
      restoreNativeCursor();
      return;
    }
    rehideNativeCursor();
  }, NATIVE_CURSOR_REHIDE_INTERVAL_MS);
  try { nativeCursorRehideTimer.unref(); } catch (_) {}
}

function stopNativeCursorRehideTimer() {
  if (!nativeCursorRehideTimer) return;
  clearInterval(nativeCursorRehideTimer);
  nativeCursorRehideTimer = null;
}

function runNativeCursorCommand(action, sync, onAsyncSuccess) {
  const handleSuccess = typeof onAsyncSuccess === 'function' ? onAsyncSuccess : null;
  try {
    if (process.platform === 'win32') {
      const args = [
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-Command',
        getWindowsCursorScript(action),
      ];
      if (sync) {
        spawnSync(getPowershellExecutable(), args, { windowsHide: true, stdio: 'ignore', timeout: 3500 });
        return;
      }
      const child = spawn(getPowershellExecutable(), args, { windowsHide: true, stdio: 'ignore' });
      child.on('error', (error) => debugLog('Windows cursor command failed:', error.message));
      if (handleSuccess) {
        child.on('close', (code) => { if (code === 0) handleSuccess(); });
      }
      try { child.unref(); } catch (_) {}
      return;
    }

    if (process.platform === 'darwin') {
      if (action === 'hide') {
        nativeCursorDisplayIds = getMacDisplayIds();
      }
      const args = ['-l', 'JavaScript', '-e', getMacCursorScript(action, nativeCursorDisplayIds)];
      if (sync) {
        spawnSync('osascript', args, { stdio: 'ignore', timeout: 1500 });
        return;
      }
      const child = spawn('osascript', args, { stdio: 'ignore' });
      child.on('error', (error) => debugLog('macOS cursor command failed:', error.message));
      if (handleSuccess) {
        child.on('close', (code) => { if (code === 0) handleSuccess(); });
      }
      try { child.unref(); } catch (_) {}
      return;
    }

    if (process.platform === 'linux') {
      const python = getLinuxPythonExecutable();
      if (!python) {
        if (!linuxCursorHelperUnavailableLogged) {
          linuxCursorHelperUnavailableLogged = true;
          debugLog('Linux cursor hiding needs python3/python with X11 libraries; overlay remains visible without hiding the native cursor.');
        }
        return;
      }
      const args = ['-c', getLinuxCursorScript(action)];
      if (sync) {
        spawnSync(python, args, { stdio: 'ignore', timeout: 1500 });
        return;
      }
      const child = spawn(python, args, { stdio: 'ignore' });
      child.on('error', (error) => debugLog('Linux cursor command failed:', error.message));
      if (handleSuccess) {
        child.on('close', (code) => { if (code === 0) handleSuccess(); });
      }
      try { child.unref(); } catch (_) {}
    }
  } catch (error) {
    debugLog(action + ' native cursor failed:', error.message || error);
  }
}

function rehideNativeCursor() {
  if (process.platform === 'darwin' && (nativeCursorHidden || nativeCursorHideInFlight)) return;
  hideNativeCursor(true);
}

function hideNativeCursor(force = false) {
  if (!shouldUseNativeCursorHide()) return;
  if ((!force && nativeCursorHidden) || nativeCursorHideInFlight) return;
  nativeCursorHidden = true;
  nativeCursorHideInFlight = true;
  nativeCursorRestoreRequired = true;
  nativeCursorRestoreGeneration += 1;
  runNativeCursorCommand('hide', false);
  setTimeout(() => {
    nativeCursorHideInFlight = false;
  }, 350);
}

function restoreNativeCursor() {
  if (!nativeCursorHidden && !nativeCursorHideInFlight && !nativeCursorRestoreRequired) return;
  const shouldRestoreAfterHideSettles = nativeCursorHideInFlight;
  if (process.platform !== 'darwin' && shouldSuppressNativeCursorRestore()) {
    nativeCursorHidden = false;
    nativeCursorHideInFlight = false;
    nativeCursorRestoreRequired = true;
    return;
  }
  nativeCursorHidden = false;
  nativeCursorHideInFlight = false;
  const generation = nativeCursorRestoreGeneration;
  const onRestoreCompleted = () => {
    if (generation === nativeCursorRestoreGeneration) {
      nativeCursorRestoreRequired = false;
    }
  };
  if (shouldRestoreAfterHideSettles) {
    runNativeCursorCommand('restore', false);
    setTimeout(() => {
      if (generation !== nativeCursorRestoreGeneration || nativeCursorHidden) return;
      runNativeCursorCommand('restore', false, onRestoreCompleted);
    }, 900);
  } else {
    runNativeCursorCommand('restore', false, onRestoreCompleted);
  }
}

function restoreNativeCursorSync() {
  if (!nativeCursorHidden && !nativeCursorHideInFlight && !nativeCursorRestoreRequired) return;
  if (process.platform !== 'darwin' && shouldSuppressNativeCursorRestore()) {
    nativeCursorHidden = false;
    nativeCursorHideInFlight = false;
    nativeCursorRestoreRequired = false;
    return;
  }
  nativeCursorHidden = false;
  nativeCursorHideInFlight = false;
  nativeCursorRestoreRequired = false;
  nativeCursorRestoreGeneration += 1;
  runNativeCursorCommand('restore', true);
}

module.exports = {
  configure,
  setState,
  stop,
  isNativeCursorHideActive,
  _private: {
    normalizeState,
    toAbsoluteAssetUrl,
    getVirtualBounds,
  },
};
