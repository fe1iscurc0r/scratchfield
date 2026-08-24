const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { TUTORIAL_OVERLAY_CHANNELS } = require('./ipc-channels');

let appRef = null;
let BrowserWindowRef = null;
let screenRef = null;
let ipcMainRef = null;
let logRef = console.log;
let getBaseUrlRef = null;
let overlayWindows = new Map();
let loadingWindows = new Map();
let localOverlayAssetDataUrlCache = new Map();
let activeRunId = '';
let activeSequence = -1;
let activeState = null;
let loadingRunId = '';
let loadingSequence = -1;
let loadingState = null;
let initialized = false;
const closedRunIds = new Set();
const closedLoadingRunIds = new Set();
const TUTORIAL_OVERLAY_Z_ORDER_REASSERT_MS = 120;
let zOrderReassertTimer = null;

function rememberClosedRunId(runId) {
  if (!runId) return;
  closedRunIds.add(runId);
  if (closedRunIds.size > 32) {
    const first = closedRunIds.values().next().value;
    closedRunIds.delete(first);
  }
}

function rememberClosedLoadingRunId(runId) {
  if (!runId) return;
  closedLoadingRunIds.add(runId);
  if (closedLoadingRunIds.size > 32) {
    const first = closedLoadingRunIds.values().next().value;
    closedLoadingRunIds.delete(first);
  }
}

function log(...args) {
  try {
    if (typeof logRef === 'function') logRef('[TutorialOverlay]', ...args);
  } catch (_) {}
}

function normalizeNumber(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function hasCursorPoint(cursor) {
  return !!(
    cursor
    && Object.prototype.hasOwnProperty.call(cursor, 'x')
    && Object.prototype.hasOwnProperty.call(cursor, 'y')
    && Number.isFinite(Number(cursor.x))
    && Number.isFinite(Number(cursor.y))
  );
}

function getOverlayDisplays() {
  if (!screenRef || typeof screenRef.getAllDisplays !== 'function') {
    return [{ id: 'default', bounds: { x: 0, y: 0, width: 1, height: 1 } }];
  }
  const displays = screenRef.getAllDisplays();
  if (!Array.isArray(displays) || displays.length === 0) {
    return [{ id: 'default', bounds: { x: 0, y: 0, width: 1, height: 1 } }];
  }
  return displays.map((display, index) => ({
    id: String(display.id == null ? index : display.id),
    bounds: display.bounds || { x: 0, y: 0, width: 1, height: 1 },
  }));
}

function getDisplayForRect(rect) {
  const displays = getOverlayDisplays();
  const centerX = normalizeNumber(rect && rect.x, 0) + normalizeNumber(rect && rect.width, 0) / 2;
  const centerY = normalizeNumber(rect && rect.y, 0) + normalizeNumber(rect && rect.height, 0) / 2;
  for (const display of displays) {
    const bounds = display.bounds;
    if (
      centerX >= bounds.x
      && centerX < bounds.x + bounds.width
      && centerY >= bounds.y
      && centerY < bounds.y + bounds.height
    ) {
      return display;
    }
  }
  if (screenRef && typeof screenRef.getDisplayNearestPoint === 'function') {
    try {
      const nearest = screenRef.getDisplayNearestPoint({ x: centerX, y: centerY });
      const nearestId = String(nearest && nearest.id);
      return displays.find(display => display.id === nearestId) || displays[0];
    } catch (_) {}
  }
  return displays[0];
}

function getDisplayForPoint(point) {
  return getDisplayForRect({ x: point && point.x, y: point && point.y, width: 1, height: 1 });
}

function resolveStaticUrl(assetPath) {
  const raw = String(assetPath || '').trim();
  if (!raw) return '';
  if (/^(?:https?:|file:|data:)/i.test(raw)) return raw;
  const baseUrl = typeof getBaseUrlRef === 'function' ? String(getBaseUrlRef() || '') : '';
  if (baseUrl) {
    try {
      return new URL(raw, baseUrl).toString();
    } catch (_) {}
  }
  if (appRef && appRef.isPackaged) {
    const assetFilePath = path.join(process.resourcesPath, raw.replace(/^\/+/, ''));
    return pathToFileURL(assetFilePath).toString();
  }
  return raw;
}

function resolveLocalOverlayAssetPath(assetName) {
  const safeName = String(assetName || '').replace(/[\\/]+/g, '').trim();
  if (!safeName) return null;
  let basePath = path.join(__dirname, '..');
  if (appRef && appRef.isPackaged && process.resourcesPath) {
    basePath = process.resourcesPath;
  } else if (path.basename(__dirname) === 'main' && path.basename(path.dirname(__dirname)) === '.webpack') {
    basePath = path.join(__dirname, '..', '..');
  }
  return path.join(basePath, safeName);
}

function resolveLocalOverlayAssetUrl(assetName) {
  const assetPath = resolveLocalOverlayAssetPath(assetName);
  return assetPath ? pathToFileURL(assetPath).toString() : '';
}

async function resolveLocalOverlayAssetDataUrl(assetName, mimeType) {
  const assetPath = resolveLocalOverlayAssetPath(assetName);
  if (!assetPath) return '';
  const normalizedMimeType = String(mimeType || 'application/octet-stream');
  const cacheKey = assetPath + '|' + normalizedMimeType;
  if (localOverlayAssetDataUrlCache.has(cacheKey)) {
    return localOverlayAssetDataUrlCache.get(cacheKey);
  }
  const pendingRead = fs.promises.readFile(assetPath)
    .then((buffer) => {
      const dataUrl = 'data:' + normalizedMimeType + ';base64,' + buffer.toString('base64');
      localOverlayAssetDataUrlCache.set(cacheKey, dataUrl);
      return dataUrl;
    })
    .catch((error) => {
      localOverlayAssetDataUrlCache.delete(cacheKey);
      log('加载本地 loading 资源失败，回退 file URL:', assetName, error && error.message ? error.message : error);
      return resolveLocalOverlayAssetUrl(assetName);
    });
  localOverlayAssetDataUrlCache.set(cacheKey, pendingRead);
  return pendingRead;
}

function getLoadingOverlayHtml() {
  return [
    '<!doctype html>',
    '<html><head><meta charset="utf-8"><style>',
    'html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent;pointer-events:none;}',
    '#stage{position:fixed;inset:0;overflow:hidden;pointer-events:none;}',
    '.tutorial-loading{position:fixed;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;pointer-events:none;background:rgba(255,255,255,0);}',
    '.tutorial-loading-stage{width:min(60vw,460px);min-width:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:min(0.9vw,7px);}',
    '.tutorial-loading-cat{width:min(30vw,220px);max-width:60%;height:auto;object-fit:contain;transform:scaleX(-1);}',
    '.tutorial-loading-wave{width:min(52vw,390px);max-width:92%;height:auto;object-fit:contain;transform:translateY(-40px);}',
    '</style></head><body><div id="stage"></div></body></html>',
  ].join('');
}

function getOverlayHtml() {
  return [
    '<!doctype html>',
    '<html><head><meta charset="utf-8"><style>',
    'html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent;pointer-events:none;}',
    '#stage{position:fixed;inset:0;overflow:hidden;pointer-events:none;}',
    '.spotlight{position:fixed;box-sizing:border-box;pointer-events:none;opacity:0;transition:left 180ms ease,top 180ms ease,width 180ms ease,height 180ms ease,opacity 140ms ease;background:transparent;overflow:visible;isolation:isolate;}',
    '.spotlight.is-visible{opacity:1;}',
    '.spotlight.is-circle{border:0;box-shadow:none;background:transparent;}',
    '.spotlight.is-circle-contained{background:transparent center/contain no-repeat;}',
    '.spotlight-chrome,.spotlight-ear-left,.spotlight-ear-right,.spotlight-paw,.spotlight-circle-skin{position:absolute;pointer-events:none;background-position:center;background-repeat:no-repeat;background-size:contain;}',
    '.spotlight-chrome{inset:3px;border-radius:inherit;background:linear-gradient(180deg,rgba(84,133,255,.09),rgba(89,211,255,.03));box-shadow:0 0 0 1px rgba(214,243,255,.72),0 0 18px rgba(104,194,255,.56),0 0 34px rgba(87,136,255,.26),inset 0 0 16px rgba(131,214,255,.16);}',
    '.spotlight-chrome:before{content:"";position:absolute;inset:0;padding:2px;border-radius:inherit;--corner:min(34%,138px);--gap:min(68%,144px);background:linear-gradient(rgba(39,89,228,.98),rgba(39,89,228,.98)) top center/calc(100% - var(--gap)) 2px no-repeat,linear-gradient(rgba(39,89,228,.98),rgba(39,89,228,.98)) bottom center/calc(100% - var(--gap)) 2px no-repeat,linear-gradient(90deg,rgba(39,89,228,.98),rgba(39,89,228,.98)) left center/2px calc(100% - var(--gap)) no-repeat,linear-gradient(90deg,rgba(39,89,228,.98),rgba(39,89,228,.98)) right center/2px calc(100% - var(--gap)) no-repeat,radial-gradient(circle at top left,rgba(235,249,255,.98) 0,rgba(186,231,255,.98) 13%,rgba(76,137,255,.95) 52%,rgba(39,89,228,.98) 96%,transparent 100%) top left/var(--corner) var(--corner) no-repeat,radial-gradient(circle at top right,rgba(235,249,255,.98) 0,rgba(186,231,255,.98) 13%,rgba(76,137,255,.95) 52%,rgba(39,89,228,.98) 96%,transparent 100%) top right/var(--corner) var(--corner) no-repeat,radial-gradient(circle at bottom right,rgba(235,249,255,.98) 0,rgba(186,231,255,.98) 13%,rgba(76,137,255,.95) 52%,rgba(39,89,228,.98) 96%,transparent 100%) bottom right/var(--corner) var(--corner) no-repeat,radial-gradient(circle at bottom left,rgba(235,249,255,.98) 0,rgba(186,231,255,.98) 13%,rgba(76,137,255,.95) 52%,rgba(39,89,228,.98) 96%,transparent 100%) bottom left/var(--corner) var(--corner) no-repeat;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;}',
    '.spotlight-sweep{position:absolute;inset:8px;border-radius:inherit;overflow:hidden;pointer-events:none;z-index:4;}',
    '.spotlight-sweep:before{content:"";position:absolute;top:-22%;bottom:-22%;left:-48%;width:34%;background:linear-gradient(108deg,transparent 0 10%,rgba(255,255,255,.58) 45%,rgba(125,225,255,.26) 58%,transparent 100%);filter:blur(.2px);opacity:0;transform:translateX(0) skewX(-12deg);animation:spotlight-sweep 2.4s ease-in-out infinite;}',
    '@keyframes spotlight-sweep{0%,28%{opacity:0;transform:translateX(0) skewX(-12deg)}45%{opacity:.85}74%,100%{opacity:0;transform:translateX(360%) skewX(-12deg)}}',
    '.spotlight-ear-left{top:-29px;left:2px;width:94.5px;height:40.5px;background-image:var(--left-ear-url);}.spotlight-ear-right{top:-30px;right:2px;width:94.5px;height:40.5px;background-image:var(--right-ear-url);}.spotlight-paw{right:-18px;bottom:-11px;width:51px;height:51px;background-image:var(--paw-url);filter:drop-shadow(0 0 8px rgba(119,211,255,.58));}',
    '.spotlight-circle-skin{display:none;inset:-19px -18px -17px -18px;background-image:var(--circle-url);}',
    '.spotlight.is-circle .spotlight-chrome,.spotlight.is-circle .spotlight-sweep,.spotlight.is-circle .spotlight-ear-left,.spotlight.is-circle .spotlight-ear-right,.spotlight.is-circle .spotlight-paw{display:none;}',
    '.spotlight.is-circle-image .spotlight-circle-skin{display:block;}',
    '.spotlight.is-plain-circle .spotlight-circle-skin{display:none;}',
    '.spotlight.is-plain-circle .spotlight-chrome{display:block;inset:0;border-radius:inherit;background:rgba(255,255,255,.02);box-shadow:0 0 0 2px rgba(39,89,228,.96),0 0 0 6px rgba(39,89,228,.14),0 0 26px rgba(39,89,228,.34);}',
    '.spotlight.is-plain-circle .spotlight-chrome:before{display:none;}',
    '.cursor{position:fixed;left:0;top:0;width:46px;height:46px;margin-left:-20px;margin-top:-18px;opacity:0;will-change:transform;transition:transform 480ms cubic-bezier(.22,1,.36,1),opacity 140ms ease;}',
    '.cursor-visual{position:absolute;inset:0;background:transparent center/contain no-repeat;filter:drop-shadow(0 10px 20px rgba(48,82,128,.22)) drop-shadow(0 2px 8px rgba(240,139,84,.22));transform-origin:center center;will-change:transform;}',
    '.cursor.is-visible{opacity:1;}',
    '.cursor.is-clicking .cursor-visual{animation:cursor-click 420ms ease;}',
    '.cursor.is-wobbling .cursor-visual{animation:cursor-wobble 700ms ease;}',
    '@keyframes cursor-click{0%,100%{transform:scale(1)}45%{transform:scale(.88)}}',
    '@keyframes cursor-wobble{0%,100%{transform:rotate(0deg)}25%{transform:rotate(-5deg)}55%{transform:rotate(4deg)}}',
    '.petal-layer{position:fixed;inset:0;opacity:0;transition:opacity 180ms ease;overflow:hidden;pointer-events:none;}',
    '.petal-layer.is-active{opacity:1;}',
    '.petal-layer.is-exiting{opacity:0;}',
    '.petal-layer img{position:absolute;left:0;top:0;width:100%;height:100%;object-fit:cover;opacity:var(--petal-opacity,.92);transform-origin:var(--petal-origin-x,50%) var(--petal-origin-y,50%);animation:petal-sweep var(--petal-duration,2600ms) ease-out both;}',
    '@keyframes petal-sweep{0%{opacity:0;transform:scale(.96) rotate(-1deg)}12%{opacity:var(--petal-opacity,.92)}100%{opacity:0;transform:scale(1.06) rotate(1deg)}}',
    '.avatar-stand-in{position:fixed;z-index:8;pointer-events:none;opacity:0;transition:opacity 180ms ease;object-fit:contain;max-width:min(42vw,420px);max-height:72vh;width:min(42vw,420px);height:auto;filter:drop-shadow(0 18px 28px rgba(31,43,66,.22)) drop-shadow(0 2px 10px rgba(92,151,255,.18));}',
    '.avatar-stand-in.is-visible{opacity:1;}',
    '.avatar-stand-in-bottom-right{right:0;bottom:0;}',
    '.avatar-stand-in-top-right-border{right:0;top:0;}',
    '.avatar-stand-in-top-left-border{left:0;top:0;}',
    '.avatar-stand-in-top-left-flipped{left:min(3vw,24px);top:0;transform:scaleY(-1);transform-origin:top center;}',
    '.avatar-stand-in-middle-left{left:0;top:50%;width:min(38vw,380px);max-height:82vh;transform:translateY(-50%);}',
    '</style></head><body><div id="stage"></div><div id="cursor" class="cursor"><div class="cursor-visual"></div></div>',
    '</body></html>',
  ].join('');
}

function createOverlayWindowForDisplay(display) {
  const bounds = display.bounds || { x: 0, y: 0, width: 1, height: 1 };
  const overlay = new BrowserWindowRef({
    ...bounds,
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
      preload: path.join(__dirname, 'preload-tutorial-global-overlay.js'),
      nodeIntegration: false,
      contextIsolation: false,
      sandbox: false,
      backgroundThrottling: false,
    },
  });
  const entry = { id: display.id, bounds, window: overlay, ready: false, lastKey: '' };
  try {
    overlay.setIgnoreMouseEvents(true);
    overlay.setAlwaysOnTop(true, 'screen-saver');
  } catch (_) {}
  overlay.webContents.once('did-finish-load', () => {
    entry.ready = true;
    try { overlay.showInactive(); } catch (_) {}
    syncOverlayEntryBounds(entry);
    liftOverlayWindowsToFront();
    sendState(true);
  });
  overlay.on('closed', () => {
    if (overlayWindows.get(display.id) === entry) {
      overlayWindows.delete(display.id);
    }
  });
  overlay.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(getOverlayHtml()));
  return entry;
}

function getLoadingWindowOptions(bounds) {
  const options = {
    ...bounds,
    title: 'N.E.K.O Tutorial Loading Overlay',
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
      preload: path.join(__dirname, 'preload-tutorial-loading-overlay.js'),
      nodeIntegration: false,
      contextIsolation: false,
      sandbox: false,
      backgroundThrottling: false,
    },
  };
  if (process.platform === 'darwin') {
    options.transparent = true;
    options.vibrancy = 'selection';
    options.visualEffectState = 'active';
  } else if (process.platform === 'win32') {
    options.backgroundMaterial = 'mica';
  } else {
    options.transparent = true;
  }
  return options;
}

function createLoadingWindowForDisplay(display) {
  const bounds = display.bounds || { x: 0, y: 0, width: 1, height: 1 };
  const overlay = new BrowserWindowRef(getLoadingWindowOptions(bounds));
  const entry = { id: display.id, bounds, window: overlay, ready: false, lastKey: '' };
  try {
    overlay.setIgnoreMouseEvents(true);
    overlay.setAlwaysOnTop(true, 'screen-saver');
  } catch (_) {}
  overlay.webContents.once('did-finish-load', () => {
    entry.ready = true;
    try { overlay.showInactive(); } catch (_) {}
    syncOverlayEntryBounds(entry);
    liftOverlayWindowsToFront();
    sendLoadingState(true);
  });
  overlay.on('closed', () => {
    if (loadingWindows.get(display.id) === entry) {
      loadingWindows.delete(display.id);
    }
  });
  overlay.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(getLoadingOverlayHtml()));
  return entry;
}

function liftOverlayWindowsToFront() {
  for (const entry of [...overlayWindows.values(), ...loadingWindows.values()]) {
    const win = entry && entry.window;
    if (!win || win.isDestroyed()) continue;
    try {
      if (!win.isAlwaysOnTop()) {
        win.setAlwaysOnTop(true, 'screen-saver');
      }
    } catch (_) {}
    try { win.moveTop(); } catch (_) {}
  }
}

function startZOrderReassertion() {
  if (zOrderReassertTimer) return;
  zOrderReassertTimer = setInterval(() => {
    if (!hasActiveOverlayWindows()) {
      stopZOrderReassertion();
      return;
    }
    liftOverlayWindowsToFront();
  }, TUTORIAL_OVERLAY_Z_ORDER_REASSERT_MS);
  try { zOrderReassertTimer.unref(); } catch (_) {}
}

function stopZOrderReassertion() {
  if (!zOrderReassertTimer) return;
  clearInterval(zOrderReassertTimer);
  zOrderReassertTimer = null;
}

function hasActiveOverlayWindows() {
  return !!activeRunId || !!(loadingRunId && loadingState);
}

function stopZOrderReassertionIfIdle() {
  if (!hasActiveOverlayWindows()) {
    stopZOrderReassertion();
  }
}

function syncOverlayEntryBounds(entry) {
  if (!entry || !entry.window || entry.window.isDestroyed()) {
    return entry && entry.bounds ? entry.bounds : { x: 0, y: 0, width: 1, height: 1 };
  }
  try {
    const actualBounds = entry.window.getBounds();
    if (
      actualBounds
      && Number.isFinite(actualBounds.x)
      && Number.isFinite(actualBounds.y)
      && Number.isFinite(actualBounds.width)
      && Number.isFinite(actualBounds.height)
      && actualBounds.width > 0
      && actualBounds.height > 0
    ) {
      entry.bounds = actualBounds;
    }
  } catch (_) {}
  return entry.bounds || { x: 0, y: 0, width: 1, height: 1 };
}

function ensureOverlayWindows() {
  if (!BrowserWindowRef || !screenRef) return;
  const displays = getOverlayDisplays();
  const activeIds = new Set(displays.map(display => display.id));
  for (const [displayId, entry] of overlayWindows.entries()) {
    if (activeIds.has(displayId)) continue;
    try { if (entry.window && !entry.window.isDestroyed()) entry.window.destroy(); } catch (_) {}
    overlayWindows.delete(displayId);
  }
  displays.forEach((display) => {
    let entry = overlayWindows.get(display.id);
    if (!entry || !entry.window || entry.window.isDestroyed()) {
      entry = createOverlayWindowForDisplay(display);
      overlayWindows.set(display.id, entry);
      return;
    }
    entry.bounds = display.bounds;
    try {
      entry.window.setBounds(display.bounds);
      entry.window.setIgnoreMouseEvents(true);
      entry.window.setAlwaysOnTop(true, 'screen-saver');
      entry.window.moveTop();
    } catch (_) {}
    syncOverlayEntryBounds(entry);
  });
}

function ensureLoadingWindows() {
  if (!BrowserWindowRef || !screenRef) return;
  const displays = getOverlayDisplays();
  const activeIds = new Set(displays.map(display => display.id));
  for (const [displayId, entry] of loadingWindows.entries()) {
    if (activeIds.has(displayId)) continue;
    try { if (entry.window && !entry.window.isDestroyed()) entry.window.destroy(); } catch (_) {}
    loadingWindows.delete(displayId);
  }
  displays.forEach((display) => {
    let entry = loadingWindows.get(display.id);
    if (!entry || !entry.window || entry.window.isDestroyed()) {
      entry = createLoadingWindowForDisplay(display);
      loadingWindows.set(display.id, entry);
      return;
    }
    entry.bounds = display.bounds;
    try {
      entry.window.setBounds(display.bounds);
      entry.window.setIgnoreMouseEvents(true);
      entry.window.setAlwaysOnTop(true, 'screen-saver');
      entry.window.moveTop();
    } catch (_) {}
    syncOverlayEntryBounds(entry);
  });
}

function localizeRect(rect, displayBounds) {
  return {
    ...rect,
    x: Math.round(normalizeNumber(rect.x, 0) - displayBounds.x),
    y: Math.round(normalizeNumber(rect.y, 0) - displayBounds.y),
    width: Math.max(1, Math.round(normalizeNumber(rect.width, 1))),
    height: Math.max(1, Math.round(normalizeNumber(rect.height, 1))),
  };
}

function getAvatarStandInDisplay(source) {
  if (!source || !source.avatarStandIn) return null;
  if (Array.isArray(source.spotlights) && source.spotlights.length > 0) {
    return getDisplayForRect(source.spotlights[0]);
  }
  if (source.cursor && hasCursorPoint(source.cursor)) {
    return getDisplayForPoint(source.cursor);
  }
  return getOverlayDisplays()[0];
}

function buildDisplayState(display) {
  const bounds = display.bounds || { x: 0, y: 0, width: 1, height: 1 };
  const source = activeState || {};
  const spotlights = Array.isArray(source.spotlights)
    ? source.spotlights
      .filter(rect => getDisplayForRect(rect).id === display.id)
      .map(rect => localizeRect(rect, bounds))
    : [];
  let cursor = null;
  if (source.cursor && (source.cursor.visible !== false || hasCursorPoint(source.cursor))) {
    const cursorDisplay = getDisplayForPoint(source.cursor);
    if (cursorDisplay && cursorDisplay.id === display.id) {
      cursor = {
        ...source.cursor,
        x: Math.round(normalizeNumber(source.cursor.x, 0) - bounds.x),
        y: Math.round(normalizeNumber(source.cursor.y, 0) - bounds.y),
      };
    }
  }
  const petal = source.petal ? {
    ...source.petal,
    originX: Math.round(normalizeNumber(source.petal.originX, bounds.x + bounds.width / 2) - bounds.x),
    originY: Math.round(normalizeNumber(source.petal.originY, bounds.y + bounds.height / 2) - bounds.y),
  } : null;
  const avatarStandInDisplay = getAvatarStandInDisplay(source);
  return {
    active: !!activeRunId,
    sequence: activeSequence,
    spotlights,
    cursor,
    petal,
    avatarStandIn: avatarStandInDisplay && avatarStandInDisplay.id === display.id ? (source.avatarStandIn || null) : null,
    assets: source.assets || {},
  };
}

function sendInactive() {
  for (const entry of overlayWindows.values()) {
    if (!entry.window || entry.window.isDestroyed() || !entry.ready) continue;
    entry.lastKey = 'inactive';
    try { entry.window.webContents.send('neko:tutorial-overlay-state', { active: false }); } catch (_) {}
  }
}

function destroyOverlayWindows() {
  for (const entry of overlayWindows.values()) {
    try { if (entry.window && !entry.window.isDestroyed()) entry.window.destroy(); } catch (_) {}
  }
  overlayWindows.clear();
}

function destroyLoadingWindows() {
  for (const entry of loadingWindows.values()) {
    try { if (entry.window && !entry.window.isDestroyed()) entry.window.destroy(); } catch (_) {}
  }
  loadingWindows.clear();
}

function sendState(force = false) {
  if (!activeRunId || !activeState) {
    sendInactive();
    return;
  }
  ensureOverlayWindows();
  liftOverlayWindowsToFront();
  for (const entry of overlayWindows.values()) {
    if (!entry.window || entry.window.isDestroyed() || !entry.ready) continue;
    const display = { id: entry.id, bounds: syncOverlayEntryBounds(entry) };
    const state = buildDisplayState(display);
    const key = JSON.stringify(state);
    if (!force && entry.lastKey === key) continue;
    entry.lastKey = key;
    try { entry.window.webContents.send('neko:tutorial-overlay-state', state); } catch (_) {}
  }
}

function buildLoadingState() {
  return {
    active: !!loadingRunId,
    sequence: loadingSequence,
    loading: loadingState,
    spotlights: [],
    cursor: null,
    petal: null,
    avatarStandIn: null,
    assets: {},
  };
}

function sendLoadingState(force = false) {
  if (!loadingRunId || !loadingState) {
    destroyLoadingWindows();
    stopZOrderReassertionIfIdle();
    return;
  }
  ensureLoadingWindows();
  liftOverlayWindowsToFront();
  for (const entry of loadingWindows.values()) {
    if (!entry.window || entry.window.isDestroyed() || !entry.ready) continue;
    const state = buildLoadingState();
    const key = JSON.stringify(state);
    if (!force && entry.lastKey === key) continue;
    entry.lastKey = key;
    try { entry.window.webContents.send('neko:tutorial-loading-overlay-state', state); } catch (_) {}
  }
}

function acceptEnvelope(payload) {
  const runId = String(payload && payload.tutorialRunId || '');
  if (!runId) return false;
  if (closedRunIds.has(runId)) return false;
  const sequence = Math.floor(normalizeNumber(payload && payload.sequence, 0));
  if (!activeRunId) {
    activeRunId = runId;
    activeSequence = -1;
    activeState = { spotlights: [], cursor: null, petal: null, avatarStandIn: null, assets: {} };
  } else if (activeRunId !== runId) {
    return false;
  }
  if (sequence <= activeSequence) {
    return false;
  }
  activeSequence = sequence;
  return true;
}

function acceptLoadingEnvelope(payload) {
  const runId = String(payload && payload.tutorialRunId || '');
  if (!runId) return false;
  if (closedLoadingRunIds.has(runId)) return false;
  const sequence = Math.floor(normalizeNumber(payload && payload.sequence, 0));
  if (!loadingRunId) {
    loadingRunId = runId;
    loadingSequence = -1;
    loadingState = null;
  } else if (loadingRunId !== runId) {
    return false;
  }
  if (sequence <= loadingSequence) {
    return false;
  }
  loadingSequence = sequence;
  return true;
}

function sanitizeSpotlights(data) {
  return Array.isArray(data && data.spotlights)
    ? data.spotlights
      .filter(rect => rect && normalizeNumber(rect.width, 0) > 0 && normalizeNumber(rect.height, 0) > 0)
      .map(rect => ({
        id: String(rect.id || ''),
        kind: String(rect.kind || 'primary'),
        shape: rect.shape === 'circle' ? 'circle' : 'rounded-rect',
        variant: normalizeSpotlightVariant(rect),
        x: normalizeNumber(rect.x, 0),
        y: normalizeNumber(rect.y, 0),
        width: Math.max(1, normalizeNumber(rect.width, 1)),
        height: Math.max(1, normalizeNumber(rect.height, 1)),
        radius: normalizeNumber(rect.radius, rect.shape === 'circle' ? 999 : 24),
      }))
    : null;
}

function normalizeSpotlightVariant(rect) {
  if (!rect || rect.shape !== 'circle') return '';
  const variant = String(rect.variant || '').trim();
  if (variant === 'plain-circle' || variant === 'circle-contained') {
    return variant;
  }
  return 'circle-image';
}

function sanitizeCursor(data) {
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'cursor')) {
    return undefined;
  }
  if (!data.cursor) {
    return null;
  }
  if (data.cursor.visible === false) {
    return hasCursorPoint(data.cursor) ? {
      visible: false,
      x: normalizeNumber(data.cursor.x, 0),
      y: normalizeNumber(data.cursor.y, 0),
      durationMs: 0,
      effect: '',
    } : null;
  }
  return {
    visible: true,
    x: normalizeNumber(data.cursor.x, 0),
    y: normalizeNumber(data.cursor.y, 0),
    durationMs: Math.max(0, normalizeNumber(data.cursor.durationMs, 0)),
    effect: String(data.cursor.effect || ''),
  };
}

function sanitizePetal(data, sequence) {
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'petal')) {
    return undefined;
  }
  return data.petal ? {
    id: String(data.petal.id || sequence || Date.now()),
    url: resolveStaticUrl(data.petal.url || '/static/assets/tutorial/petals/yui-guide-petal-transition.webp'),
    durationMs: Math.max(240, normalizeNumber(data.petal.durationMs, 2600)),
    originX: normalizeNumber(data.petal.originX, 0),
    originY: normalizeNumber(data.petal.originY, 0),
    finalOpacity: Math.max(0, Math.min(1, normalizeNumber(data.petal.finalOpacity, 0.92))),
  } : null;
}

function sanitizeAvatarStandIn(data) {
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'avatarStandIn')) {
    return undefined;
  }
  if (!data.avatarStandIn) {
    return null;
  }
  const url = resolveStaticUrl(data.avatarStandIn.url);
  if (!url) {
    return null;
  }
  return {
    visible: data.avatarStandIn.visible !== false,
    url,
    resource: String(data.avatarStandIn.resource || ''),
    position: String(data.avatarStandIn.position || ''),
    durationMs: Math.max(0, normalizeNumber(data.avatarStandIn.durationMs, 0)),
    refreshKey: String(data.avatarStandIn.refreshKey || data.avatarStandIn.refreshNonce || ''),
  };
}

async function createDefaultLoadingState() {
  const [loadCatUrl, loadingWaveUrl] = await Promise.all([
    resolveLocalOverlayAssetDataUrl('load_cat.gif', 'image/gif'),
    resolveLocalOverlayAssetDataUrl('loading_wave_with_icons.gif', 'image/gif'),
  ]);
  return {
    visible: true,
    loadCatUrl,
    loadingWaveUrl,
  };
}

async function restoreDefaultLoadingState() {
  const acceptedRunId = loadingRunId;
  const acceptedSequence = loadingSequence;
  const nextLoadingState = await createDefaultLoadingState();
  if (loadingRunId !== acceptedRunId || loadingSequence !== acceptedSequence) {
    return false;
  }
  loadingState = nextLoadingState;
  startZOrderReassertion();
  ensureLoadingWindows();
  sendLoadingState(true);
  return true;
}

async function sanitizeLoading(data) {
  if (!data || !Object.prototype.hasOwnProperty.call(data, 'loading')) {
    return undefined;
  }
  if (!data.loading || data.loading.visible === false) {
    return null;
  }
  return createDefaultLoadingState();
}

function sanitizeState(payload, previousState) {
  const data = payload && payload.payload && typeof payload.payload === 'object'
    ? payload.payload
    : {};
  const previous = previousState || {};
  const nextSpotlights = sanitizeSpotlights(data);
  const nextCursor = sanitizeCursor(data);
  const nextPetal = sanitizePetal(data, payload && payload.sequence);
  const nextAvatarStandIn = sanitizeAvatarStandIn(data);
  const assets = {
    circleHighlightUrl: resolveStaticUrl('/static/assets/tutorial/highlight/circle-highlight.png'),
    leftCatEarUrl: resolveStaticUrl('/static/assets/tutorial/highlight/left-cat-ear.png'),
    rightCatEarUrl: resolveStaticUrl('/static/assets/tutorial/highlight/right-cat-ear.png'),
    catPawUrl: resolveStaticUrl('/static/assets/tutorial/highlight/cat-paw.png'),
    defaultCursorUrl: resolveStaticUrl('/static/assets/tutorial/ghost-cursor/default-ghost-cursor.png'),
    clickCursorUrl: resolveStaticUrl('/static/assets/tutorial/ghost-cursor/click-ghost-cursor.png'),
  };
  return {
    spotlights: nextSpotlights == null ? (Array.isArray(previous.spotlights) ? previous.spotlights : []) : nextSpotlights,
    cursor: typeof nextCursor === 'undefined' ? (previous.cursor || null) : nextCursor,
    petal: typeof nextPetal === 'undefined' ? (previous.petal || null) : nextPetal,
    avatarStandIn: typeof nextAvatarStandIn === 'undefined' ? (previous.avatarStandIn || null) : nextAvatarStandIn,
    assets,
  };
}

async function sanitizeLoadingState(payload, previousState) {
  const data = payload && payload.payload && typeof payload.payload === 'object'
    ? payload.payload
    : {};
  const nextLoading = await sanitizeLoading(data);
  return typeof nextLoading === 'undefined'
    ? (previousState || null)
    : nextLoading;
}

function begin(payload) {
  const runId = String(payload && payload.tutorialRunId || '');
  if (!runId) {
    return { ok: false };
  }
  if (closedRunIds.has(runId)) {
    return { ok: false, stale: true };
  }
  if (activeRunId === runId) {
    startZOrderReassertion();
    ensureOverlayWindows();
    sendState(true);
    return { ok: true };
  }
  rememberClosedRunId(activeRunId);
  activeRunId = runId;
  activeSequence = -1;
  activeState = { spotlights: [], cursor: null, petal: null, avatarStandIn: null, assets: {} };
  startZOrderReassertion();
  ensureOverlayWindows();
  sendState(true);
  return { ok: true };
}

async function beginLoading(payload) {
  const runId = String(payload && payload.tutorialRunId || '');
  if (!runId) {
    return { ok: false };
  }
  if (closedLoadingRunIds.has(runId)) {
    return { ok: false, stale: true };
  }
  if (loadingRunId === runId) {
    if (!loadingState) {
      return await restoreDefaultLoadingState()
        ? { ok: true }
        : { ok: false, stale: true };
    }
    startZOrderReassertion();
    ensureLoadingWindows();
    sendLoadingState(true);
    return { ok: true };
  }
  rememberClosedLoadingRunId(loadingRunId);
  loadingRunId = runId;
  loadingSequence = -1;
  loadingState = null;
  return await restoreDefaultLoadingState()
    ? { ok: true }
    : { ok: false, stale: true };
}

function update(payload) {
  if (!acceptEnvelope(payload)) {
    return { ok: false, stale: true };
  }
  activeState = sanitizeState(payload, activeState);
  sendState(false);
  return { ok: true };
}

async function updateLoading(payload) {
  if (!acceptLoadingEnvelope(payload)) {
    return { ok: false, stale: true };
  }
  const acceptedRunId = loadingRunId;
  const acceptedSequence = loadingSequence;
  const nextLoadingState = await sanitizeLoadingState(payload, loadingState);
  if (loadingRunId !== acceptedRunId || loadingSequence !== acceptedSequence) {
    return { ok: false, stale: true };
  }
  loadingState = nextLoadingState;
  sendLoadingState(false);
  return { ok: true };
}

function clear(payload) {
  const runId = payload && payload.tutorialRunId ? String(payload.tutorialRunId) : '';
  if (runId && activeRunId && runId !== activeRunId) {
    return { ok: false, stale: true };
  }
  const closedRunId = activeRunId ? (runId || activeRunId) : '';
  rememberClosedRunId(closedRunId);
  activeRunId = '';
  activeSequence = -1;
  activeState = null;
  stopZOrderReassertionIfIdle();
  sendInactive();
  destroyOverlayWindows();
  return { ok: true };
}

function clearLoading(payload) {
  const runId = payload && payload.tutorialRunId ? String(payload.tutorialRunId) : '';
  if (runId && loadingRunId && runId !== loadingRunId) {
    return { ok: false, stale: true };
  }
  const closedRunId = loadingRunId ? (runId || loadingRunId) : '';
  rememberClosedLoadingRunId(closedRunId);
  loadingRunId = '';
  loadingSequence = -1;
  loadingState = null;
  destroyLoadingWindows();
  stopZOrderReassertionIfIdle();
  return { ok: true };
}

function getWindowMetrics(event) {
  const win = BrowserWindowRef && event && event.sender
    ? BrowserWindowRef.fromWebContents(event.sender)
    : null;
  if (!win || win.isDestroyed()) return null;
  let bounds = null;
  let contentBounds = null;
  let zoomFactor = 1;
  try { bounds = win.getBounds(); } catch (_) {}
  try { contentBounds = win.getContentBounds(); } catch (_) {}
  try { zoomFactor = win.webContents.getZoomFactor(); } catch (_) {}
  return {
    windowId: win.id,
    bounds,
    contentBounds: contentBounds || bounds,
    zoomFactor: Number.isFinite(zoomFactor) && zoomFactor > 0 ? zoomFactor : 1,
  };
}

function registerIpc() {
  if (initialized || !ipcMainRef) return;
  initialized = true;
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.BEGIN, (_event, payload) => begin(payload));
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.UPDATE, (_event, payload) => update(payload));
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.CLEAR, (_event, payload) => clear(payload));
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.LOADING_BEGIN, (_event, payload) => beginLoading(payload));
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.LOADING_UPDATE, (_event, payload) => updateLoading(payload));
  ipcMainRef.handle(TUTORIAL_OVERLAY_CHANNELS.LOADING_CLEAR, (_event, payload) => clearLoading(payload));
  ipcMainRef.on(TUTORIAL_OVERLAY_CHANNELS.GET_WINDOW_METRICS_SYNC, (event) => {
    event.returnValue = getWindowMetrics(event);
  });
}

function configure(options = {}) {
  appRef = options.app || appRef;
  BrowserWindowRef = options.BrowserWindow || BrowserWindowRef;
  screenRef = options.screen || screenRef;
  ipcMainRef = options.ipcMain || ipcMainRef;
  logRef = options.log || logRef;
  getBaseUrlRef = options.getBaseUrl || getBaseUrlRef;
  registerIpc();
  if (screenRef && typeof screenRef.on === 'function') {
    const refreshOverlayDisplays = () => {
      sendState(true);
      sendLoadingState(true);
    };
    screenRef.on('display-added', refreshOverlayDisplays);
    screenRef.on('display-removed', refreshOverlayDisplays);
    screenRef.on('display-metrics-changed', refreshOverlayDisplays);
  }
}

function stop() {
  clear({});
  clearLoading({});
  stopZOrderReassertion();
}
module.exports = {
  configure,
  stop,
  begin,
  update,
  clear,
  beginLoading,
  updateLoading,
  clearLoading,
  _private: {
    getWindowMetrics,
    sanitizeState,
    sanitizeLoadingState,
  },
};
