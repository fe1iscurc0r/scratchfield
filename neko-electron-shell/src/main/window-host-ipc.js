'use strict';

const {
  applyX11InputShape,
  isX11InputShapeHelperReady,
  queryX11PointerButtons,
} = require('./linux-x11-input-shape');

function createWindowHostIpc(context) {
  const {
    BrowserWindow,
    applyTopOn,
    canUseSetShape,
    getInputRegionBackend,
    getFullscreenDisplayBounds,
    getMainWindow,
    getPetBottomExpandedWorkArea,
    ipcMain,
    log,
    resetToastIdleTimer,
    screen,
    shouldUseNativeIgnoreMouse,
    windowManager,
  } = context;

  const _lastShapeByWindow = new Map();
  const _lastShapeMetaByWindow = new Map();
  const _ignoreStateByWindow = new Map();
  const _petInputRegionsByWindow = new Map();
  const _x11ShapeActiveByWindow = new Set();
  const _x11ShapeCloseHookedByWindow = new Set();
  const _petInputRegionDebugHashByWindow = new Map();
  const _waylandPetShapeClipDebugHashByWindow = new Map();
  const _waylandSetShapeDebugHashByWindow = new Map();
  const _waylandReactChatShapeAuthorityByWindow = new Map();
  const _waylandReactChatShapeReapplySnapshotByWindow = new Map();
  const _waylandReactChatShapeCloseHookedByWindow = new Set();
  const _lastX11ShapeHashByWindow = new Map();
  const _x11ShapeApplyTokenByWindow = new Map();
  const _x11ShapeStateByWindow = new Map();
  const _x11ShapeEventHookedByWindow = new Set();
  const _x11ShapeReapplyTimersByWindow = new Map();
  const debugLinuxInput = process.env.NEKO_DEBUG_LINUX_INPUT === '1';
  const LINUX_PET_INPUT_POLL_MS = 24;
  const WAYLAND_REACT_CHAT_SHAPE_REAPPLY_MS = 16;
  const WAYLAND_REACT_CHAT_SHAPE_REAPPLY_LOG_MS = 5000;
  const WAYLAND_REACT_CHAT_SHAPE_RAISE_MS = 750;
  const WAYLAND_FALSE_ORIGIN_MIN_OFFSET_PX = 8;
  const X11_SHAPE_EVENT_REAPPLY_DELAYS = [0, 16, 80, 220, 520, 1200];
  const X11_SHAPE_NATIVE_IGNORE_REAPPLY_DELAYS = [16, 80, 180, 360];
  let linuxPetInputPollTimer = null;
  let linuxPetInputPollInFlight = false;

  function isLinuxX11Runtime() {
    return process.platform === 'linux' && !windowManager.isLinuxWaylandRuntime?.();
  }

  function isLinuxXwaylandRuntime() {
    return isLinuxX11Runtime() &&
      (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
  }

  function isXwaylandPetWindow(win) {
    return isLinuxX11Runtime() && isPetWindow(win) && isLinuxXwaylandRuntime();
  }

  function isSubtitleWindow(win) {
    if (!win || win.isDestroyed()) return false;
    const subtitleWindow = typeof windowManager.getSubtitleWindow === 'function'
      ? windowManager.getSubtitleWindow()
      : null;
    if (subtitleWindow && !subtitleWindow.isDestroyed() && subtitleWindow.id === win.id) {
      return true;
    }
    try {
      const url = String(win.webContents && win.webContents.getURL ? win.webContents.getURL() : '');
      return /(?:^|\/)subtitle(?:[?#]|$)/.test(url);
    } catch (_) {
      return false;
    }
  }

  function getWindowScaleFactor(win) {
    try {
      const display = screen.getDisplayMatching(win.getBounds());
      return display && Number.isFinite(display.scaleFactor) ? display.scaleFactor : 1;
    } catch (_) {
      return 1;
    }
  }

  function getXwaylandCursorScreenPoint(win) {
    const electronPoint = screen.getCursorScreenPoint();
    return {
      x: electronPoint.x,
      y: electronPoint.y,
      screenX: electronPoint.x,
      screenY: electronPoint.y,
      buttons: null,
      x11Pointer: null,
      x11Point: null,
    };
  }

  function isLinuxWaylandRuntime() {
    return process.platform === 'linux' && !!windowManager.isLinuxWaylandRuntime?.();
  }

  function normalizeShapeRects(rects) {
    return Array.isArray(rects) ? rects
      .filter(r => r && Number.isFinite(r.x) && Number.isFinite(r.y)
        && Number.isFinite(r.width) && Number.isFinite(r.height)
        && r.width > 0 && r.height > 0)
      .map(r => ({
        x: Math.max(0, Math.round(r.x)),
        y: Math.max(0, Math.round(r.y)),
        width: Math.max(1, Math.round(r.width)),
        height: Math.max(1, Math.round(r.height)),
      })) : [];
  }

  function normalizeScreenShapeRects(rects) {
    return Array.isArray(rects) ? rects
      .filter(r => r && Number.isFinite(r.x) && Number.isFinite(r.y)
        && Number.isFinite(r.width) && Number.isFinite(r.height)
        && r.width > 0 && r.height > 0)
      .map(r => ({
        x: Math.round(r.x),
        y: Math.round(r.y),
        width: Math.max(1, Math.round(r.width)),
        height: Math.max(1, Math.round(r.height)),
      })) : [];
  }

  function normalizeWindowBounds(bounds) {
    if (!bounds || typeof bounds !== 'object') return null;
    const x = Number(bounds.x);
    const y = Number(bounds.y);
    const width = Number(bounds.width);
    const height = Number(bounds.height);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) {
      return null;
    }
    if (width <= 0 || height <= 0) return null;
    return {
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(1, Math.round(width)),
      height: Math.max(1, Math.round(height)),
    };
  }

  function dedupeShapeRects(rects) {
    const out = [];
    const seen = new Set();
    for (const rect of normalizeShapeRects(rects)) {
      const key = `${rect.x}:${rect.y}:${rect.width}:${rect.height}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(rect);
    }
    return out;
  }

  function clipShapeRectToNativeBounds(rect, bounds) {
    if (!rect || !bounds) return null;
    const left = Math.max(0, Math.round(rect.x));
    const top = Math.max(0, Math.round(rect.y));
    const right = Math.min(Math.max(1, Math.round(bounds.width)), Math.round(rect.x + rect.width));
    const bottom = Math.min(Math.max(1, Math.round(bounds.height)), Math.round(rect.y + rect.height));
    if (right <= left || bottom <= top) return null;
    return {
      x: left,
      y: top,
      width: right - left,
      height: bottom - top,
    };
  }

  function projectShapeRectsWithOffset(rects, dx, dy, bounds) {
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) return [];
    if (Math.round(dx) === 0 && Math.round(dy) === 0) return [];
    return normalizeShapeRects(rects).map((rect) => clipShapeRectToNativeBounds({
      x: rect.x + Math.round(dx),
      y: rect.y + Math.round(dy),
      width: rect.width,
      height: rect.height,
    }, bounds)).filter(Boolean);
  }

  function normalizeWaylandShapeScaleFactor(value) {
    const scale = Number(value);
    if (!Number.isFinite(scale) || scale <= 1.05 || scale > 4) return null;
    return scale;
  }

  function getWaylandShapeScaleFactors(win, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const scales = [];
    const add = (value) => {
      const scale = normalizeWaylandShapeScaleFactor(value);
      if (!scale) return;
      if (scales.some((candidate) => Math.abs(candidate - scale) < 0.01)) return;
      scales.push(scale);
    };
    add(getWindowScaleFactor(win));
    add(safeMeta.devicePixelRatio);
    add(safeMeta.scaleFactor);
    if (safeMeta.viewport && typeof safeMeta.viewport === 'object') {
      add(safeMeta.viewport.devicePixelRatio);
    }
    return scales;
  }

  function projectShapeRectsWithScale(rects, scaleX, scaleY) {
    if (!Number.isFinite(scaleX) || !Number.isFinite(scaleY)) return [];
    if (scaleX <= 0 || scaleY <= 0) return [];
    if (Math.abs(scaleX - 1) <= 0.05 && Math.abs(scaleY - 1) <= 0.05) return [];
    return normalizeShapeRects(rects).map((rect) => {
      const left = Math.floor(rect.x * scaleX);
      const top = Math.floor(rect.y * scaleY);
      const right = Math.ceil((rect.x + rect.width) * scaleX);
      const bottom = Math.ceil((rect.y + rect.height) * scaleY);
      if (right <= left || bottom <= top) return null;
      return {
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      };
    }).filter(Boolean);
  }

  function projectWaylandScaledShapeRectsForNativeBounds(win, rects, meta = {}) {
    if (!isLinuxWaylandRuntime()) return [];
    const scales = getWaylandShapeScaleFactors(win, meta);
    if (!scales.length) return [];
    const baseRects = normalizeShapeRects(rects);
    const scaledRects = [];
    for (const scale of scales) {
      scaledRects.push(...projectShapeRectsWithScale(baseRects, scale, scale));
    }
    return scaledRects;
  }

  function getWaylandFalseOriginWorkAreaOffset(actual, declared) {
    if (!actual || !declared) return null;
    if (Math.abs(actual.x) > 2 || Math.abs(actual.y) > 2) return null;
    const dx = declared.width - actual.width;
    const dy = declared.height - actual.height;
    const offsetX = Math.max(0, Math.round(dx));
    const offsetY = Math.max(0, Math.round(dy));
    if (Math.max(offsetX, offsetY) < WAYLAND_FALSE_ORIGIN_MIN_OFFSET_PX) return null;
    return {
      dx: offsetX,
      dy: offsetY,
    };
  }

  function projectWaylandScreenShapeRectsForNativeBounds(win, meta = {}, source, mode) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    if (!isLinuxWaylandRuntime()) return [];
    if (source && safeMeta.source !== source) return [];
    if (mode && safeMeta.mode !== mode) return [];
    const screenRects = normalizeScreenShapeRects(safeMeta.screenRects);
    if (!screenRects.length) return [];
    let actual = null;
    try {
      actual = normalizeWindowBounds(win.getBounds());
    } catch (_) {
      actual = null;
    }
    if (!actual) return [];
    return screenRects.map((rect) => clipShapeRectToNativeBounds({
      x: rect.x - actual.x,
      y: rect.y - actual.y,
      width: rect.width,
      height: rect.height,
    }, actual)).filter(Boolean);
  }

  function projectWaylandReactChatScreenShapeRectsForNativeBounds(win, meta = {}) {
    if (!isReactChatWindow(win)) return [];
    return projectWaylandScreenShapeRectsForNativeBounds(
      win,
      meta,
      'react-chat-compact',
      'hit-region',
    );
  }

  function expandWaylandPetHitRegionShapeRectsForNativeBounds(win, rects, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const baseRects = normalizeShapeRects(rects);
    if (!isLinuxWaylandRuntime() || !isPetWindow(win)) return baseRects;
    if (safeMeta.source !== 'pet-wayland-model') return baseRects;
    if (safeMeta.mode !== 'hit-region') return baseRects;
    const candidates = baseRects.slice();
    candidates.push(...projectWaylandScreenShapeRectsForNativeBounds(
      win,
      safeMeta,
      'pet-wayland-model',
      'hit-region',
    ));
    candidates.push(...projectWaylandScaledShapeRectsForNativeBounds(win, candidates, safeMeta));
    return dedupeShapeRects(candidates);
  }

  function expandWaylandPetAvatarToolFullWindowShapeRectsForNativeBounds(win, rects, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const baseRects = normalizeShapeRects(rects);
    if (!isLinuxWaylandRuntime() || !isPetWindow(win)) return baseRects;
    if (safeMeta.source !== 'pet-wayland-avatar-tool') return baseRects;
    if (safeMeta.mode !== 'avatar-tool-full-window') return baseRects;
    let actual = null;
    try {
      actual = normalizeWindowBounds(win.getBounds());
    } catch (_) {
      actual = null;
    }
    if (!actual) return baseRects;
    const candidates = baseRects.slice();
    candidates.push({
      x: 0,
      y: 0,
      width: actual.width,
      height: actual.height,
    });
    candidates.push(...projectWaylandScreenShapeRectsForNativeBounds(
      win,
      safeMeta,
      'pet-wayland-avatar-tool',
      'avatar-tool-full-window',
    ));
    candidates.push(...projectWaylandScaledShapeRectsForNativeBounds(win, candidates, safeMeta));
    return dedupeShapeRects(candidates);
  }

  function expandWaylandPetFullWindowSurfaceShapeRectsForNativeBounds(win, rects, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const baseRects = normalizeShapeRects(rects);
    if (!isLinuxWaylandRuntime() || !isPetWindow(win)) return baseRects;
    if (safeMeta.source !== 'pet-wayland-full-window') return baseRects;
    if (safeMeta.mode !== 'full-window-surface') return baseRects;
    const candidates = baseRects.slice();
    candidates.push(...projectWaylandScreenShapeRectsForNativeBounds(
      win,
      safeMeta,
      'pet-wayland-full-window',
      'full-window-surface',
    ));
    candidates.push(...projectWaylandScaledShapeRectsForNativeBounds(win, candidates, safeMeta));
    return dedupeShapeRects(candidates);
  }

  function expandWaylandReactChatHitRegionShapeRectsForNativeBounds(win, rects, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const baseRects = normalizeShapeRects(rects);
    if (!isLinuxWaylandRuntime() || !isReactChatWindow(win)) return baseRects;
    if (safeMeta.source !== 'react-chat-compact') return baseRects;
    if (safeMeta.mode !== 'hit-region') return baseRects;
    const declared = normalizeWindowBounds(safeMeta.bounds);
    if (!declared) return baseRects;
    let actual = null;
    try {
      actual = normalizeWindowBounds(win.getBounds());
    } catch (_) {
      actual = null;
    }
    if (!actual) return baseRects;
    const candidates = baseRects.slice();
    const addScaledRects = (scaleX, scaleY) => {
      const shouldScale = Number.isFinite(scaleX) && Number.isFinite(scaleY)
        && scaleX > 0
        && scaleY > 0
        && (Math.abs(scaleX - 1) > 0.05 || Math.abs(scaleY - 1) > 0.05);
      if (!shouldScale) return;
      for (const rect of baseRects) {
        const left = Math.floor(rect.x * scaleX);
        const top = Math.floor(rect.y * scaleY);
        const right = Math.ceil((rect.x + rect.width) * scaleX);
        const bottom = Math.ceil((rect.y + rect.height) * scaleY);
        candidates.push({
          x: left,
          y: top,
          width: right - left,
          height: bottom - top,
        });
      }
    };
    const addProjectionScale = (scaleX, scaleY) => {
      if (!Number.isFinite(scaleX) || !Number.isFinite(scaleY)) return;
      if (scaleX <= 0 || scaleY <= 0) return;
      if (Math.abs(scaleX - 1) <= 0.05 && Math.abs(scaleY - 1) <= 0.05) return;
      addScaledRects(scaleX, scaleY);
    };
    if (declared.width > actual.width + 2 && declared.height > actual.height + 2) {
      addProjectionScale(actual.width / declared.width, actual.height / declared.height);
      addProjectionScale(declared.width / actual.width, declared.height / actual.height);
    }
    const falseOriginOffset = getWaylandFalseOriginWorkAreaOffset(actual, declared);
    if (falseOriginOffset) {
      candidates.push(...projectShapeRectsWithOffset(
        baseRects,
        falseOriginOffset.dx,
        falseOriginOffset.dy,
        actual,
      ));
    }
    candidates.push(...projectWaylandReactChatScreenShapeRectsForNativeBounds(win, safeMeta));
    candidates.push(...projectWaylandScaledShapeRectsForNativeBounds(win, candidates, safeMeta));
    return dedupeShapeRects(candidates);
  }

  function expandWaylandReactChatSelfBallShapeRectsForNativeBounds(win, rects, meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    const baseRects = normalizeShapeRects(rects);
    if (!isLinuxWaylandRuntime() || !isReactChatWindow(win)) return baseRects;
    if (safeMeta.source !== 'react-chat-compact') return baseRects;
    if (safeMeta.mode !== 'wayland-self-ball') return baseRects;
    const candidates = baseRects.slice();
    candidates.push(...projectWaylandScreenShapeRectsForNativeBounds(
      win,
      safeMeta,
      'react-chat-compact',
      'wayland-self-ball',
    ));
    candidates.push(...projectWaylandScaledShapeRectsForNativeBounds(win, candidates, safeMeta));
    return dedupeShapeRects(candidates);
  }

  function getNativeWindowShapeRects(win, rects, meta = {}) {
    let shapeRects = normalizeShapeRects(rects);
    shapeRects = expandWaylandReactChatHitRegionShapeRectsForNativeBounds(win, shapeRects, meta);
    shapeRects = expandWaylandReactChatSelfBallShapeRectsForNativeBounds(win, shapeRects, meta);
    shapeRects = expandWaylandPetHitRegionShapeRectsForNativeBounds(win, shapeRects, meta);
    shapeRects = expandWaylandPetAvatarToolFullWindowShapeRectsForNativeBounds(win, shapeRects, meta);
    shapeRects = expandWaylandPetFullWindowSurfaceShapeRectsForNativeBounds(win, shapeRects, meta);
    return getEffectiveWindowShapeRects(win, shapeRects, meta);
  }

  function summarizeShapeRects(rects) {
    return (Array.isArray(rects) ? rects : []).slice(0, 12).map((rect) => ({
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
    }));
  }

  function serializeShapeRectsForSnapshot(rects) {
    return normalizeShapeRects(rects)
      .map((rect) => `${rect.x}:${rect.y}:${rect.width}:${rect.height}`)
      .join('|');
  }

  function getWaylandReactChatShapeReapplySnapshot(win, shapeRects, meta = {}) {
    let bounds = null;
    try {
      bounds = normalizeWindowBounds(win.getBounds());
    } catch (_) {
      bounds = null;
    }
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    return [
      bounds ? `${bounds.x}:${bounds.y}:${bounds.width}:${bounds.height}` : 'no-bounds',
      safeMeta.source || '',
      safeMeta.reason || '',
      safeMeta.mode || '',
      safeMeta.snapshot || '',
      serializeShapeRectsForSnapshot(shapeRects),
    ].join(';');
  }

  function getShapePassthroughFallbackRect(win) {
    try {
      const bounds = win.getBounds();
      return [{
        x: Math.max(0, Math.round(Number(bounds.width) || 1) - 1),
        y: Math.max(0, Math.round(Number(bounds.height) || 1) - 1),
        width: 1,
        height: 1,
      }];
    } catch (_) {
      return [{ x: 0, y: 0, width: 1, height: 1 }];
    }
  }

  function shouldMaintainWaylandReactChatShapeAuthority(win, meta = {}) {
    if (!isLinuxWaylandRuntime() || !win || win.isDestroyed()) return false;
    if (!isReactChatWindow(win)) return false;
    if (!canUseSetShape(win)) return false;
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    if (safeMeta.source !== 'react-chat-compact') return false;
    if (safeMeta.reason === 'compact-clear') return false;
    return true;
  }

  function raiseWaylandReactChatShapeWindow(win, state, trigger = '') {
    if (!isLinuxWaylandRuntime() || !isReactChatWindow(win)) return;
    const now = Date.now();
    const forceRaise = trigger === 'apply' || trigger === 'focus-event' || trigger === 'blur-event';
    if (!forceRaise && state && now - state.lastRaiseAt < WAYLAND_REACT_CHAT_SHAPE_RAISE_MS) return;
    let usedTopPolicy = false;
    try {
      if (typeof applyTopOn === 'function') {
        applyTopOn(win, { kind: 'reactChat', defaultLevel: 'floating' });
        usedTopPolicy = true;
      }
    } catch (_) {}
    if (!usedTopPolicy) {
      try { win.setAlwaysOnTop(true, 'floating'); } catch (_) {}
    }
    try { win.moveTop(); } catch (_) {}
    if (state) state.lastRaiseAt = now;
  }

  function stopWaylandReactChatShapeAuthority(winOrId, reason = 'stop') {
    const winId = typeof winOrId === 'number' ? winOrId : (winOrId && winOrId.id);
    if (!winId) return;
    const state = _waylandReactChatShapeAuthorityByWindow.get(winId);
    if (!state) return;
    if (state.timer) clearInterval(state.timer);
    try {
      if (state.win && state.focusHandler) state.win.off('focus', state.focusHandler);
      if (state.win && state.blurHandler) state.win.off('blur', state.blurHandler);
    } catch (_) {}
    _waylandReactChatShapeAuthorityByWindow.delete(winId);
    _waylandReactChatShapeReapplySnapshotByWindow.delete(winId);
    if (debugLinuxInput) {
      log(`[react-chat-setShape-reapply] stop winId=${winId} reason=${reason}`);
    }
  }

  function reapplyWaylandReactChatShape(win, trigger = '') {
    if (!win || win.isDestroyed()) {
      stopWaylandReactChatShapeAuthority(win, 'destroyed');
      return;
    }
    const meta = _lastShapeMetaByWindow.get(win.id) || {};
    if (!shouldMaintainWaylandReactChatShapeAuthority(win, meta)) {
      stopWaylandReactChatShapeAuthority(win, 'shape-authority-disabled');
      return;
    }
    try {
      if (typeof win.isVisible === 'function' && !win.isVisible()) return;
    } catch (_) {
      return;
    }
    const rects = _lastShapeByWindow.get(win.id);
    const effectiveRects = getNativeWindowShapeRects(win, rects || [], meta);
    const shapeRects = effectiveRects.length ? effectiveRects : getShapePassthroughFallbackRect(win);
    const state = _waylandReactChatShapeAuthorityByWindow.get(win.id);
    const forceApply = trigger === 'apply' || trigger === 'focus-event' || trigger === 'blur-event';
    const snapshot = getWaylandReactChatShapeReapplySnapshot(win, shapeRects, meta);
    if (
      !forceApply
      && _ignoreStateByWindow.get(win.id) === false
      && _waylandReactChatShapeReapplySnapshotByWindow.get(win.id) === snapshot
    ) {
      raiseWaylandReactChatShapeWindow(win, state, trigger);
      return;
    }
    try {
      if (_ignoreStateByWindow.get(win.id) !== false) {
        win.setIgnoreMouseEvents(false);
        _ignoreStateByWindow.set(win.id, false);
      }
    } catch (_) {}
    try {
      win.setShape(shapeRects);
      _waylandReactChatShapeReapplySnapshotByWindow.set(win.id, snapshot);
      raiseWaylandReactChatShapeWindow(win, state, trigger);
      if (debugLinuxInput && state) {
        state.count += 1;
        const now = Date.now();
        if (trigger || now - state.lastLogAt >= WAYLAND_REACT_CHAT_SHAPE_REAPPLY_LOG_MS) {
          state.lastLogAt = now;
          log('[react-chat-setShape-reapply]',
            `trigger=${trigger || 'poll'}`,
            `winId=${win.id}`,
            `count=${state.count}`,
            `shapeCount=${shapeRects.length}`,
            `reason=${meta.reason || 'unknown'}`,
            `mode=${meta.mode || 'unknown'}`,
            `rects=${JSON.stringify(summarizeShapeRects(shapeRects))}`);
        }
      }
    } catch (error) {
      log('[react-chat-setShape-reapply] failed:', error && error.message ? error.message : error);
    }
  }

  function ensureWaylandReactChatShapeAuthority(win, meta = {}) {
    if (!shouldMaintainWaylandReactChatShapeAuthority(win, meta)) {
      stopWaylandReactChatShapeAuthority(win, 'shape-authority-disabled');
      return;
    }
    let state = _waylandReactChatShapeAuthorityByWindow.get(win.id);
    if (!state) {
      state = {
        timer: null,
        count: 0,
        lastLogAt: 0,
        lastRaiseAt: 0,
        win,
        focusHandler: null,
        blurHandler: null,
      };
      state.timer = setInterval(() => {
        reapplyWaylandReactChatShape(win);
      }, WAYLAND_REACT_CHAT_SHAPE_REAPPLY_MS);
      try { state.timer.unref(); } catch (_) {}
      state.focusHandler = () => {
        reapplyWaylandReactChatShape(win, 'focus-event');
      };
      state.blurHandler = () => {
        reapplyWaylandReactChatShape(win, 'blur-event');
      };
      try {
        win.on('focus', state.focusHandler);
        win.on('blur', state.blurHandler);
      } catch (_) {}
      _waylandReactChatShapeAuthorityByWindow.set(win.id, state);
      if (!_waylandReactChatShapeCloseHookedByWindow.has(win.id)) {
        _waylandReactChatShapeCloseHookedByWindow.add(win.id);
        try {
          win.once('closed', () => {
            stopWaylandReactChatShapeAuthority(win.id, 'closed');
            _lastShapeByWindow.delete(win.id);
            _lastShapeMetaByWindow.delete(win.id);
            _waylandSetShapeDebugHashByWindow.delete(win.id);
            _waylandReactChatShapeReapplySnapshotByWindow.delete(win.id);
            _waylandReactChatShapeCloseHookedByWindow.delete(win.id);
          });
        } catch (_) {
          _waylandReactChatShapeCloseHookedByWindow.delete(win.id);
        }
      }
    }
    reapplyWaylandReactChatShape(win, 'apply');
  }

  function makePetPassthroughShapeRect(win) {
    try {
      const b = win.getBounds();
      return [{
        x: Math.max(0, Math.round(b.width) - 1),
        y: Math.max(0, Math.round(b.height) - 1),
        width: 1,
        height: 1,
      }];
    } catch (_) {
      return [{ x: 0, y: 0, width: 1, height: 1 }];
    }
  }

  function subtractWindowShapeRect(rect, cutout) {
    if (!rect || !cutout) return rect ? [rect] : [];
    const ax1 = rect.x;
    const ay1 = rect.y;
    const ax2 = rect.x + rect.width;
    const ay2 = rect.y + rect.height;
    const bx1 = cutout.x;
    const by1 = cutout.y;
    const bx2 = cutout.x + cutout.width;
    const by2 = cutout.y + cutout.height;
    const ix1 = Math.max(ax1, bx1);
    const iy1 = Math.max(ay1, by1);
    const ix2 = Math.min(ax2, bx2);
    const iy2 = Math.min(ay2, by2);
    if (ix1 >= ix2 || iy1 >= iy2) return [rect];
    return [
      { x: ax1, y: ay1, width: ax2 - ax1, height: iy1 - ay1 },
      { x: ax1, y: iy2, width: ax2 - ax1, height: ay2 - iy2 },
      { x: ax1, y: iy1, width: ix1 - ax1, height: iy2 - iy1 },
      { x: ix2, y: iy1, width: ax2 - ix2, height: iy2 - iy1 },
    ].filter((part) => part.width > 0 && part.height > 0)
      .map((part) => ({
        x: Math.round(part.x),
        y: Math.round(part.y),
        width: Math.max(1, Math.round(part.width)),
        height: Math.max(1, Math.round(part.height)),
      }));
  }

  function getWaylandPetShapeOcclusionWindows(petWin) {
    const windows = (() => {
      try {
        return windowManager.getWindows && windowManager.getWindows();
      } catch (_) {
        return null;
      }
    })();
    const candidates = [
      windows && windows.chat,
      windows && windows.fullChat,
      windows && windows.compactChatBall,
      typeof windowManager.getReactChatWindow === 'function' ? windowManager.getReactChatWindow() : null,
      typeof windowManager.getFullChatWindow === 'function' ? windowManager.getFullChatWindow() : null,
    ];
    const seen = new Set();
    return candidates.filter((target) => {
      if (!target || target === petWin || target.isDestroyed()) return false;
      if (seen.has(target.id)) return false;
      seen.add(target.id);
      try {
        if (!target.isVisible() || (typeof target.isMinimized === 'function' && target.isMinimized())) {
          return false;
        }
      } catch (_) {
        return false;
      }
      return true;
    });
  }

  function isWaylandAvatarToolPetShapeMeta(meta = {}) {
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    return safeMeta.source === 'pet-wayland-avatar-tool'
      && safeMeta.mode === 'avatar-tool-full-window';
  }

  function getWaylandPetShapeOcclusionCutouts(petWin, target, petBounds, pad, ownerMeta = {}) {
    let targetBounds = null;
    try { targetBounds = normalizeWindowBounds(target.getBounds()); } catch (_) { targetBounds = null; }
    if (!targetBounds) return [];

    if (isReactChatWindow(target)) {
      const avatarToolOwner = isWaylandAvatarToolPetShapeMeta(ownerMeta);
      const meta = _lastShapeMetaByWindow.get(target.id) || {};
      const compactShapeRegion = meta
        && meta.source === 'react-chat-compact'
        && (meta.mode === 'hit-region' || meta.mode === 'wayland-self-ball')
        && meta.reason !== 'compact-clear';
      if (compactShapeRegion) {
        const shapeRects = getNativeWindowShapeRects(target, _lastShapeByWindow.get(target.id) || [], meta);
        if (shapeRects.length) {
          return shapeRects.map((rect) => ({
            x: targetBounds.x + rect.x - petBounds.x - pad,
            y: targetBounds.y + rect.y - petBounds.y - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
          }));
        }
        if (meta.mode === 'wayland-self-ball') return [];
        if (avatarToolOwner) return [];
        const fullCarrier = targetBounds.width >= petBounds.width - pad * 2
          && targetBounds.height >= petBounds.height - pad * 2;
        if (fullCarrier) return [];
      }
      if (avatarToolOwner) return [];
    }

    return [{
      x: targetBounds.x - petBounds.x - pad,
      y: targetBounds.y - petBounds.y - pad,
      width: targetBounds.width + pad * 2,
      height: targetBounds.height + pad * 2,
    }];
  }

  function shouldPreserveWaylandPetCropOverlayShape(win, meta = {}) {
    if (!isLinuxWaylandRuntime() || !isPetWindow(win)) return false;
    const safeMeta = meta && typeof meta === 'object' ? meta : {};
    if (safeMeta.source !== 'pet-wayland-full-window') return false;
    if (safeMeta.mode !== 'full-window-surface') return false;
    // IPC contract with preload-pet.js:
    // getVisibleX11FullWindowSurfaceReason() formats entries from
    // DESKTOP_FULL_WINDOW_SURFACE_SELECTORS as "selector:<selector>".
    // Keep these crop-overlay selectors paired with that list.
    return safeMeta.reason === 'selector:#crop-overlay'
      || safeMeta.reason === 'selector:.crop-overlay';
  }

  function clipWaylandPetShapeAroundManagedWindows(win, rects, meta = {}) {
    if (!isLinuxWaylandRuntime() || !isPetWindow(win)) return rects;
    const originalRects = Array.isArray(rects) ? rects : [];
    if (shouldPreserveWaylandPetCropOverlayShape(win, meta)) {
      return originalRects.length ? originalRects : makePetPassthroughShapeRect(win);
    }
    const petBounds = (() => {
      try { return win.getBounds(); } catch (_) { return null; }
    })();
    if (!petBounds || petBounds.width <= 0 || petBounds.height <= 0) {
      return originalRects.length ? originalRects : makePetPassthroughShapeRect(win);
    }

    const occlusionWindows = getWaylandPetShapeOcclusionWindows(win);
    if (!occlusionWindows.length) {
      return originalRects.length ? originalRects : makePetPassthroughShapeRect(win);
    }

    const PAD = isWaylandAvatarToolPetShapeMeta(meta) ? 0 : 4;
    let clipped = originalRects.slice();
    let clipCount = 0;
    for (const target of occlusionWindows) {
      const cutouts = getWaylandPetShapeOcclusionCutouts(win, target, petBounds, PAD, meta);
      if (!cutouts.length) continue;
      let next = clipped;
      for (const cutout of cutouts) {
        const partsForCutout = [];
        for (const rect of next) {
          const parts = subtractWindowShapeRect(rect, cutout);
          for (const part of parts) partsForCutout.push(part);
        }
        next = partsForCutout;
        if (!next.length) break;
      }
      if (next.length !== clipped.length || hashInputRegions(next, 1) !== hashInputRegions(clipped, 1)) {
        clipCount += 1;
      }
      clipped = next;
      if (!clipped.length) break;
    }

    if (!clipped.length) clipped = makePetPassthroughShapeRect(win);
    if (clipCount > 0) {
      const debugHash = `${hashInputRegions(originalRects, 1)}=>${hashInputRegions(clipped, 1)}`;
      if (_waylandPetShapeClipDebugHashByWindow.get(win.id) !== debugHash) {
        _waylandPetShapeClipDebugHashByWindow.set(win.id, debugHash);
        log(`[Wayland-setShape] Pet shape clipped around ${clipCount} managed window(s): ${originalRects.length} -> ${clipped.length}`);
      }
    }
    return clipped;
  }

  function getEffectiveWindowShapeRects(win, rects, meta = {}) {
    const safeRects = normalizeShapeRects(rects);
    return clipWaylandPetShapeAroundManagedWindows(win, safeRects, meta);
  }

  function applyWindowShape(win, rects, meta = {}) {
    if (!win || win.isDestroyed()) return;
    if (!canUseSetShape(win)) return;
    const requestedRects = normalizeShapeRects(rects);
    _lastShapeByWindow.set(win.id, requestedRects);
    _lastShapeMetaByWindow.set(win.id, meta && typeof meta === 'object' ? meta : {});
    try {
      const safeRects = getNativeWindowShapeRects(win, requestedRects, meta);
      try {
        if (_ignoreStateByWindow.get(win.id) !== false) {
          win.setIgnoreMouseEvents(false);
          _ignoreStateByWindow.set(win.id, false);
        }
      } catch (_) {}
      win.setShape(safeRects);
      if (shouldMaintainWaylandReactChatShapeAuthority(win, meta)) {
        ensureWaylandReactChatShapeAuthority(win, meta);
      } else {
        stopWaylandReactChatShapeAuthority(win, 'shape-authority-disabled');
      }
      if (debugLinuxInput) {
        const debugHash = JSON.stringify({
          count: safeRects.length,
          bounds: (() => { try { return win.getBounds(); } catch (_) { return null; } })(),
          meta: {
            source: meta && meta.source,
            reason: meta && meta.reason,
            mode: meta && meta.mode,
          },
          rects: summarizeShapeRects(safeRects),
        });
        if (_waylandSetShapeDebugHashByWindow.get(win.id) !== debugHash) {
          _waylandSetShapeDebugHashByWindow.set(win.id, debugHash);
          log('[setShape] applied', safeRects.length, 'rects', JSON.stringify({
            winId: win.id,
            source: meta && meta.source,
            reason: meta && meta.reason,
            mode: meta && meta.mode,
            rects: summarizeShapeRects(safeRects),
          }));
        } else {
          log('[setShape] applied', safeRects.length, 'rects', `winId=${win.id}`, 'repeat');
        }
      } else {
        log('[setShape] applied', safeRects.length, 'rects');
      }
      return safeRects;
    } catch (e) {
      log('[setShape] failed:', e.message);
    }
    return [];
  }

  function setWindowIgnoreMouseEvents(win, ignore, options = {}, source = 'ipc') {
    if (!win || win.isDestroyed()) return;
    const winId = win.id;
    const isX11Pet = isLinuxX11Runtime() && isPetWindow(win);
    const isX11ShapeActive = isX11Pet && _x11ShapeActiveByWindow.has(winId);
    const forceCompactCarrierPassthrough = typeof windowManager.isReactChatMinimizedCarrierWindow === 'function'
      && windowManager.isReactChatMinimizedCarrierWindow(win);
    // 球态透明 carrier 不允许 renderer 恢复命中，否则整块透明聊天窗会挡住桌面。
    const requestedIgnore = forceCompactCarrierPassthrough ? true : ignore;
    const effectiveIgnore = isX11ShapeActive ? false : requestedIgnore;
    const toastWindow = windowManager.getToastWindow();
    const isToast = toastWindow && win.id === toastWindow.id;
    const isX11Toast = isLinuxX11Runtime() && isToast;
    const isSubtitle = isSubtitleWindow(win);
    if (forceCompactCarrierPassthrough) {
      win.setIgnoreMouseEvents(true);
      return;
    }
    if (_ignoreStateByWindow.get(winId) === effectiveIgnore && !isX11Toast) return;
    _ignoreStateByWindow.set(winId, effectiveIgnore);
    try { win._nekoIgnoreMouseEvents = effectiveIgnore; } catch (_) {}
    if (debugLinuxInput && process.platform === 'linux') {
      try {
        log('[ignore-mouse]', JSON.stringify({
          source,
          winId,
          title: win.getTitle(),
          ignore: effectiveIgnore,
          requestedIgnore: ignore,
          x11ShapeActive: isX11ShapeActive,
          bounds: win.getBounds(),
        }));
      } catch (_) {}
    }
    if (toastWindow && win.id === toastWindow.id && effectiveIgnore === true) {
      resetToastIdleTimer();
    }
    if (isX11Toast) {
      try {
        win.setIgnoreMouseEvents(effectiveIgnore);
      } catch (error) {
        log('x11 toast native ignore update failed:', error.message || error);
      }
      const rects = effectiveIgnore
        ? []
        : (() => {
            const b = win.getBounds();
            return [{ x: 0, y: 0, width: b.width, height: b.height }];
          })();
      applyX11InputShape(win, rects, {
        log,
        scaleFactor: getWindowScaleFactor(win),
        allowNativeFallback: true,
      }).catch((error) => {
        log('x11 toast input shape update failed:', error.message || error);
      });
      return;
    }
    if (isX11ShapeActive) {
      // X11 Pet passthrough is controlled by the native ShapeInput region.
      // Do not call Electron's setIgnoreMouseEvents here: on X11 it rewrites
      // the input shape back to the full window and defeats the XShape region.
      return;
    } else if (shouldUseNativeIgnoreMouse(win)) {
      // 尊重调用方的 forward 选择；聊天框空白穿透不能在主进程被重新补成 forward。
      win.setIgnoreMouseEvents(effectiveIgnore, options);
    } else {
      if ((isToast || isSubtitle) && canUseSetShape(win)) {
        if (effectiveIgnore) {
          win.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
        } else {
          const b = win.getBounds();
          win.setShape([{ x: 0, y: 0, width: b.width, height: b.height }]);
        }
      }
    }
  }

  function sanitizeInputRegions(rects) {
    if (!Array.isArray(rects)) return [];
    return rects
      .filter(r => r && Number.isFinite(r.x) && Number.isFinite(r.y)
        && Number.isFinite(r.width) && Number.isFinite(r.height)
        && r.width > 0 && r.height > 0)
      .slice(0, 32)
      .map(r => ({
        x: Math.round(r.x),
        y: Math.round(r.y),
        width: Math.max(1, Math.round(r.width)),
        height: Math.max(1, Math.round(r.height)),
      }));
  }

  function normalizePetRegionPayload(payload) {
    if (Array.isArray(payload)) {
      return {
        inputRects: sanitizeInputRegions(payload),
        boundingRects: null,
        forceApply: false,
        inputMode: 'normal',
        fullWindowInputReason: '',
      };
    }
    if (!payload || typeof payload !== 'object') {
      return {
        inputRects: [],
        boundingRects: null,
        forceApply: false,
        inputMode: 'normal',
        fullWindowInputReason: '',
      };
    }
    const inputRects = sanitizeInputRegions(payload.inputRects || payload.rects);
    const boundingRects = Array.isArray(payload.boundingRects)
      ? sanitizeInputRegions(payload.boundingRects)
      : null;
    return {
      inputRects,
      boundingRects,
      forceApply: payload.forceApply === true,
      inputMode: normalizePetInputMode(payload.inputMode),
      fullWindowInputReason: typeof payload.fullWindowInputReason === 'string'
        ? payload.fullWindowInputReason
        : '',
    };
  }

  function normalizePetInputMode(value) {
    if (value === 'model-drag' || value === 'full-window-surface') return value;
    return 'normal';
  }

  function hashInputRegions(rects, scaleFactor) {
    const parts = Array.isArray(rects) ? rects.map((r) => (
      `${r.x},${r.y},${r.width},${r.height}`
    )) : [];
    return `${scaleFactor || 1}:${parts.join(';')}`;
  }

  function pointInWindow(point, win) {
    if (!point || !win || win.isDestroyed() || !win.isVisible()) return false;
    const b = win.getBounds();
    return point.x >= b.x && point.x < b.x + b.width
      && point.y >= b.y && point.y < b.y + b.height;
  }

  function pointInWindowRects(point, win, rects) {
    if (!point || !win || win.isDestroyed() || !Array.isArray(rects)) return false;
    const b = win.getBounds();
    const localX = point.x - b.x;
    const localY = point.y - b.y;
    return rects.some((r) => (
      r
      && Number.isFinite(r.x)
      && Number.isFinite(r.y)
      && Number.isFinite(r.width)
      && Number.isFinite(r.height)
      && r.width > 0
      && r.height > 0
      && localX >= r.x
      && localX < r.x + r.width
      && localY >= r.y
      && localY < r.y + r.height
    ));
  }

  function isPointInWindowEffectiveInputRegion(point, win) {
    if (!pointInWindow(point, win)) return false;
    if (!isLinuxX11Runtime() || !isX11InputShapeWindow(win)) return true;
    const rects = win._nekoEffectiveInputRegionRects;
    if (!Array.isArray(rects)) return true;
    return pointInWindowRects(point, win, rects);
  }

  function isPointInReactChatWaylandShape(point, win) {
    if (!isLinuxWaylandRuntime() || !isReactChatWindow(win)) return false;
    try {
      const meta = _lastShapeMetaByWindow.get(win.id) || {};
      const rects = getNativeWindowShapeRects(win, _lastShapeByWindow.get(win.id) || [], meta);
      if (!Array.isArray(rects) || rects.length === 0) return false;
      return pointInWindowRects(point, win, rects);
    } catch (_) {
      return false;
    }
  }

  function isPointInChatWindowForCursor(point, chatWin, sourceWin) {
    if (!chatWin || chatWin === sourceWin || chatWin.isDestroyed()) return false;
    try {
      if (!chatWin.isVisible()) return false;
    } catch (_) {
      return false;
    }
    if (_ignoreStateByWindow.get(chatWin.id) === true) return false;
    if (
      typeof windowManager.isReactChatMinimizedCarrierWindow === 'function'
      && windowManager.isReactChatMinimizedCarrierWindow(chatWin)
    ) {
      return false;
    }
    if (isLinuxWaylandRuntime() && isReactChatWindow(chatWin)) {
      return isPointInReactChatWaylandShape(point, chatWin);
    }
    return isPointInWindowEffectiveInputRegion(point, chatWin);
  }

  function isFullWindowInputRegion(win, rects) {
    if (!win || win.isDestroyed() || !Array.isArray(rects) || rects.length !== 1) return false;
    try {
      const b = win.getBounds();
      const r = rects[0];
      if (!r || b.width <= 0 || b.height <= 0) return false;
      return r.x <= 2 && r.y <= 2 &&
        r.width >= b.width - 4 &&
        r.height >= b.height - 4;
    } catch (_) {
      return false;
    }
  }

  function getStablePetInputFallback(win, fallbackBoundingRects = null) {
    const previous = win && !win.isDestroyed() ? _petInputRegionsByWindow.get(win.id) : null;
    const stableRects = previous && Array.isArray(previous.stableRects)
      ? previous.stableRects
      : (previous && previous.inputMode === 'normal' && Array.isArray(previous.rects) &&
          !isFullWindowInputRegion(win, previous.rects)
        ? previous.rects
        : []);
    const stableBoundingRects = previous && Array.isArray(previous.stableBoundingRects)
      ? previous.stableBoundingRects
      : (previous && previous.inputMode === 'normal' && Array.isArray(previous.boundingRects)
        ? previous.boundingRects
        : fallbackBoundingRects);
    return {
      inputRects: stableRects,
      boundingRects: stableBoundingRects,
    };
  }

  function sanitizePetInputPolicy(win, inputRects, boundingRects, payload) {
    if (!isLinuxX11Runtime() || !isPetWindow(win)) {
      return { inputRects, boundingRects, guarded: false };
    }
    if (!isFullWindowInputRegion(win, inputRects)) {
      return { inputRects, boundingRects, guarded: false };
    }
    if (payload && payload.fullWindowInputReason) {
      return { inputRects, boundingRects, guarded: false };
    }

    const fallback = getStablePetInputFallback(win, boundingRects);
    return {
      inputRects: fallback.inputRects,
      boundingRects: fallback.boundingRects,
      guarded: true,
    };
  }

  function clearX11ShapeReapplyTimers(winId) {
    const timers = _x11ShapeReapplyTimersByWindow.get(winId);
    if (Array.isArray(timers)) {
      timers.forEach((timer) => clearTimeout(timer));
    }
    _x11ShapeReapplyTimersByWindow.delete(winId);
  }

  function notifyX11InputShapeActive(win, active) {
    if (!win || win.isDestroyed()) return;
    try {
      if (win.webContents && !win.webContents.isDestroyed()) {
        win.webContents.send('neko:x11-input-shape-active', !!active);
      }
    } catch (_) {}
  }

  function clearX11ShapeAuthorityState(winId) {
    clearX11ShapeReapplyTimers(winId);
    _x11ShapeStateByWindow.delete(winId);
    _lastX11ShapeHashByWindow.delete(winId);
    _x11ShapeApplyTokenByWindow.delete(winId);
    _x11ShapeActiveByWindow.delete(winId);
    const win = BrowserWindow.fromId(winId);
    if (win) {
      try { win._nekoX11InputShapeAuthorityReady = false; } catch (_) {}
      try { delete win._nekoEffectiveInputRegionRects; } catch (_) {}
      try { delete win._nekoEffectiveInputRegionUpdatedAt; } catch (_) {}
      notifyX11InputShapeActive(win, false);
    }
  }

  function reapplyCurrentX11Shape(win, reason) {
    if (!win || win.isDestroyed()) return;
    const state = _x11ShapeStateByWindow.get(win.id);
    if (!state || !_x11ShapeActiveByWindow.has(win.id)) return;
    const applyToken = state.applyToken;
    if (_x11ShapeApplyTokenByWindow.get(win.id) !== applyToken) return;
    applyX11InputShape(win, state.inputRects, {
      log,
      scaleFactor: state.scaleFactor,
      boundingRects: state.boundingRects,
      allowNativeFallback: !isLinuxXwaylandRuntime(),
    }).then((ok) => {
      if (!ok) {
        if (_x11ShapeApplyTokenByWindow.get(win.id) === applyToken) {
            clearX11ShapeAuthorityState(win.id);
        }
        return;
      }
      if (debugLinuxInput) {
        try { log('[x11-input-shape] authority reapply', reason || 'event'); } catch (_) {}
      }
    }).catch((error) => {
      log('x11 shape authority reapply failed:', error.message || error);
      if (_x11ShapeApplyTokenByWindow.get(win.id) === applyToken) {
        clearX11ShapeAuthorityState(win.id);
      }
    });
  }

  function scheduleX11CurrentShapeReapply(win, reason, delays = X11_SHAPE_EVENT_REAPPLY_DELAYS) {
    if (!win || win.isDestroyed()) return;
    clearX11ShapeReapplyTimers(win.id);
    const timers = delays.map((delay) => {
      const timer = setTimeout(() => {
        reapplyCurrentX11Shape(win, `${reason || 'event'}:${delay}`);
      }, delay);
      try { timer.unref(); } catch (_) {}
      return timer;
    });
    _x11ShapeReapplyTimersByWindow.set(win.id, timers);
  }

  function hookX11ShapeAuthorityReapply(win) {
    if (!win || win.isDestroyed() || _x11ShapeEventHookedByWindow.has(win.id)) return;
    _x11ShapeEventHookedByWindow.add(win.id);
    const schedule = (reason) => {
      scheduleX11CurrentShapeReapply(win, reason, X11_SHAPE_EVENT_REAPPLY_DELAYS);
    };
    const onMove = () => schedule('window-move');
    const onResize = () => schedule('window-resize');
    const onShow = () => schedule('window-show');
    const onRestore = () => schedule('window-restore');
    const onFocus = () => schedule('window-focus');
    const onBlur = () => schedule('window-blur');
    win.on('move', onMove);
    win.on('resize', onResize);
    win.on('show', onShow);
    win.on('restore', onRestore);
    win.on('focus', onFocus);
    win.on('blur', onBlur);
    win.once('closed', () => {
      win.off('move', onMove);
      win.off('resize', onResize);
      win.off('show', onShow);
      win.off('restore', onRestore);
      win.off('focus', onFocus);
      win.off('blur', onBlur);
      _x11ShapeEventHookedByWindow.delete(win.id);
      clearX11ShapeAuthorityState(win.id);
    });
  }

  function storeX11ShapeAuthorityState(win, inputRects, boundingRects, scaleFactor, applyToken, shapeHash) {
    if (!win || win.isDestroyed()) return;
    _x11ShapeStateByWindow.set(win.id, {
      inputRects,
      boundingRects,
      scaleFactor,
      applyToken,
      shapeHash,
    });
    try { win._nekoX11InputShapeAuthorityReady = true; } catch (_) {}
    try { win._nekoEffectiveInputRegionRects = Array.isArray(inputRects) ? inputRects : []; } catch (_) {}
    try { win._nekoEffectiveInputRegionUpdatedAt = Date.now(); } catch (_) {}
    notifyX11InputShapeActive(win, true);
    hookX11ShapeAuthorityReapply(win);
  }

  function isSatelliteInputIgnored(satellite) {
    if (!satellite || satellite.isDestroyed()) return true;
    if (_ignoreStateByWindow.get(satellite.id) === true) return true;
    try {
      const toastWindow = typeof windowManager.getToastWindow === 'function'
        ? windowManager.getToastWindow()
        : null;
      if (toastWindow && !toastWindow.isDestroyed() && satellite.id === toastWindow.id) {
        return true;
      }
    } catch (_) {}
    return false;
  }

  function isPointOverSatelliteWindow(point, petWin) {
    try {
      const windows = windowManager.getWindows();
      const satellites = [
        windows && windows.chat,
        windows && windows.fullChat, // full 独立聊天窗口：与 compact 同为受管聊天 surface，pet 鼠标应让位
        windows && windows.subtitle,
        windows && windows.subtitleSettings,
        windows && windows.agentHud,
        windows && windows.jukebox,
        typeof windowManager.getReactChatWindow === 'function' ? windowManager.getReactChatWindow() : null,
        typeof windowManager.getFullChatWindow === 'function' ? windowManager.getFullChatWindow() : null,
        typeof windowManager.getToastWindow === 'function' ? windowManager.getToastWindow() : null,
      ];
      return satellites.some((satellite) => {
        if (!satellite || satellite === petWin || satellite.isDestroyed()) return false;
        if (isSatelliteInputIgnored(satellite)) return false;
        return isPointInWindowEffectiveInputRegion(point, satellite);
      });
    } catch (_) {
      return false;
    }
  }

  function isPetWindow(win) {
    try {
      const windows = windowManager.getWindows && windowManager.getWindows();
      return !!(windows && windows.pet && win && windows.pet.id === win.id);
    } catch (_) {
      return false;
    }
  }

  function isReactChatWindow(win) {
    try {
      const reactChat = typeof windowManager.getReactChatWindow === 'function'
        ? windowManager.getReactChatWindow()
        : null;
      return !!(reactChat && win && reactChat.id === win.id);
    } catch (_) {
      return false;
    }
  }

  function isX11InputShapeWindow(win) {
    return isPetWindow(win) || isReactChatWindow(win);
  }

  function isPointInPetInputRegions(point, petWin, rects) {
    if (!point || !petWin || petWin.isDestroyed()) return false;
    const b = petWin.getBounds();
    const localX = point.x - b.x;
    const localY = point.y - b.y;
    return rects.some((r) => (
      localX >= r.x && localX < r.x + r.width
      && localY >= r.y && localY < r.y + r.height
    ));
  }

  function shouldStoreStablePetInputRegion(payload, inputRects, guarded) {
    if (guarded) return false;
    if (!payload || payload.fullWindowInputReason) return false;
    if (payload.inputMode !== 'normal') return false;
    return Array.isArray(inputRects);
  }

  async function applyX11WindowInputShape(win, safeRects, options = {}) {
    if (!isLinuxX11Runtime() || !isX11InputShapeWindow(win)) return false;
    const forceApply = options.forceApply === true;
    const scaleFactor = getWindowScaleFactor(win);
    const nativeBoundingRects = null;
    const inputShapeHash = hashInputRegions(safeRects, scaleFactor);
    const boundingShapeHash = 'none';
    const shapeHash = `${inputShapeHash}|bounding:${boundingShapeHash}`;
    if (_x11ShapeActiveByWindow.has(win.id) && !isX11InputShapeHelperReady()) {
      clearX11ShapeAuthorityState(win.id);
    }
    if (!forceApply && _x11ShapeActiveByWindow.has(win.id) && _lastX11ShapeHashByWindow.get(win.id) === shapeHash) {
      return true;
    }
    const applyToken = (_x11ShapeApplyTokenByWindow.get(win.id) || 0) + 1;
    _x11ShapeApplyTokenByWindow.set(win.id, applyToken);
    if (shouldUseNativeIgnoreMouse(win) && isPetWindow(win)) startLinuxPetInputPoller();
    let clearedNativeIgnore = false;
    const ok = await applyX11InputShape(win, safeRects, {
      log,
      scaleFactor,
      boundingRects: nativeBoundingRects,
      allowNativeFallback: !isLinuxXwaylandRuntime(),
      beforeWrite: () => {
        if (win.isDestroyed()) return false;
        if (_x11ShapeApplyTokenByWindow.get(win.id) !== applyToken) return false;
        if (shouldUseNativeIgnoreMouse(win) && _ignoreStateByWindow.get(win.id) === true) {
          // Clear Electron's startup passthrough so the X11 window can receive
          // input inside ShapeInput. Electron may rewrite ShapeInput while doing
          // this, so successful writes schedule native re-application below.
          win.setIgnoreMouseEvents(false);
          clearedNativeIgnore = true;
        }
        _ignoreStateByWindow.set(win.id, false);
        return true;
      },
    });
    if (!win || win.isDestroyed() || _x11ShapeApplyTokenByWindow.get(win.id) !== applyToken) {
      return false;
    }
    if (ok) {
      _x11ShapeActiveByWindow.add(win.id);
      _lastX11ShapeHashByWindow.set(win.id, shapeHash);
      _ignoreStateByWindow.set(win.id, false);
      storeX11ShapeAuthorityState(win, safeRects, nativeBoundingRects, scaleFactor, applyToken, shapeHash);
      if (clearedNativeIgnore) {
        scheduleX11CurrentShapeReapply(win, 'native-ignore-clear', X11_SHAPE_NATIVE_IGNORE_REAPPLY_DELAYS);
      }
      if (!_x11ShapeCloseHookedByWindow.has(win.id)) {
        _x11ShapeCloseHookedByWindow.add(win.id);
        win.once('closed', () => {
          _x11ShapeCloseHookedByWindow.delete(win.id);
          _petInputRegionDebugHashByWindow.delete(win.id);
          _petInputRegionsByWindow.delete(win.id);
          try { delete win._nekoEffectiveInputRegionRects; } catch (_) {}
          try { delete win._nekoEffectiveInputRegionUpdatedAt; } catch (_) {}
          clearX11ShapeAuthorityState(win.id);
        });
      }
      return true;
    }
    clearX11ShapeAuthorityState(win.id);
    if (shouldUseNativeIgnoreMouse(win)) {
      if (isPetWindow(win)) {
        win.setIgnoreMouseEvents(true, { forward: true });
        _ignoreStateByWindow.set(win.id, true);
      } else {
        win.setIgnoreMouseEvents(false);
        _ignoreStateByWindow.set(win.id, false);
      }
    }
    return false;
  }

  function startLinuxPetInputPoller() {
    if (linuxPetInputPollTimer || process.platform !== 'linux') return;
    linuxPetInputPollTimer = setInterval(() => {
      if (linuxPetInputPollInFlight) return;
      linuxPetInputPollInFlight = true;
      (async () => {
        for (const [winId, state] of _petInputRegionsByWindow.entries()) {
          const win = BrowserWindow.fromId(winId);
          if (!win || win.isDestroyed()) {
            _petInputRegionsByWindow.delete(winId);
            _x11ShapeCloseHookedByWindow.delete(winId);
            _petInputRegionDebugHashByWindow.delete(winId);
            clearX11ShapeAuthorityState(winId);
            continue;
          }
          if (isLinuxX11Runtime() && isX11InputShapeWindow(win) && _x11ShapeActiveByWindow.has(win.id)) {
            if (isX11InputShapeHelperReady()) {
              continue;
            }
            clearX11ShapeAuthorityState(win.id);
          }
          if (!shouldUseNativeIgnoreMouse(win)) continue;
          if (isLinuxX11Runtime() && isReactChatWindow(win)) {
            setWindowIgnoreMouseEvents(win, false, {}, 'linux-input-poll:x11-react-chat');
            continue;
          }
          if (!win.isVisible()) {
            setWindowIgnoreMouseEvents(win, true, { forward: true }, 'linux-input-poll');
            continue;
          }
          const point = getXwaylandCursorScreenPoint(win);
          const overSatellite = isPointOverSatelliteWindow(point, win);
          const overPetRegion = isPointInPetInputRegions(point, win, state.rects || []);
          const shouldIgnore = overSatellite || !overPetRegion;
          try {
            setWindowIgnoreMouseEvents(win, shouldIgnore, shouldIgnore ? { forward: true } : {}, 'linux-input-poll');
          } catch (e) {
            log('linux pet input poll failed:', e.message);
          }
        }
      })().catch((error) => {
        log('linux pet input poll failed:', error.message || error);
      }).finally(() => {
        linuxPetInputPollInFlight = false;
      });
    }, LINUX_PET_INPUT_POLL_MS);
    try { linuxPetInputPollTimer.unref(); } catch (_) {}
  }

  ipcMain.on('neko:pet-set-shape', (event, rects, meta = {}) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win || win.isDestroyed()) return;
    const requestedRects = normalizeShapeRects(rects);
    applyWindowShape(win, requestedRects, meta);
  });

  async function applyPetInputRegionsForWindow(win, rects, source = 'ipc') {
    if (process.platform !== 'linux') return;
    if (!win || win.isDestroyed()) return;
    let payload = normalizePetRegionPayload(rects);
    if (isLinuxX11Runtime() && isPetWindow(win) && payload.inputMode === 'model-drag') {
      const fallback = getStablePetInputFallback(win, payload.boundingRects);
      payload = {
        ...payload,
        inputRects: fallback.inputRects,
        boundingRects: fallback.boundingRects,
        forceApply: true,
        inputMode: 'normal',
        fullWindowInputReason: '',
      };
      source = `${source}:model-drag-native-grab`;
    }
    const policy = sanitizePetInputPolicy(win, payload.inputRects, payload.boundingRects, payload);
    const safeRects = policy.inputRects;
    const boundingRects = policy.boundingRects;
    const forceApply = payload.forceApply === true;
    const previousState = _petInputRegionsByWindow.get(win.id) || {};
    const storeStable = shouldStoreStablePetInputRegion(payload, safeRects, policy.guarded);
    const stableRects = storeStable
      ? safeRects
      : (Array.isArray(previousState.stableRects) ? previousState.stableRects : []);
    const stableBoundingRects = storeStable
      ? boundingRects
      : (Array.isArray(previousState.stableBoundingRects) ? previousState.stableBoundingRects : null);
    const effectiveInputMode = policy.guarded ? 'normal' : payload.inputMode;
    const effectiveFullWindowInputReason = policy.guarded ? '' : payload.fullWindowInputReason;
    _petInputRegionsByWindow.set(win.id, {
      rects: safeRects,
      boundingRects,
      updatedAt: Date.now(),
      inputMode: effectiveInputMode,
      fullWindowInputReason: effectiveFullWindowInputReason,
      guarded: policy.guarded === true,
      stableRects,
      stableBoundingRects,
    });
    if (debugLinuxInput) {
      try {
        const debugHash = `${hashInputRegions(safeRects, 1)}|bounding:${Array.isArray(boundingRects) ? hashInputRegions(boundingRects, 1) : 'none'}|mode:${effectiveInputMode}|reason:${effectiveFullWindowInputReason}|guarded:${policy.guarded ? '1' : '0'}`;
        if (_petInputRegionDebugHashByWindow.get(win.id) !== debugHash) {
          _petInputRegionDebugHashByWindow.set(win.id, debugHash);
          log('[pet-input-regions]', JSON.stringify({
            source,
            winId: win.id,
            rectCount: safeRects.length,
            firstRect: safeRects[0] || null,
            boundingRectCount: Array.isArray(boundingRects) ? boundingRects.length : null,
            firstBoundingRect: Array.isArray(boundingRects) ? (boundingRects[0] || null) : null,
            inputMode: effectiveInputMode,
            fullWindowInputReason: effectiveFullWindowInputReason || null,
            guarded: policy.guarded === true,
            bounds: win.getBounds(),
          }));
        }
      } catch (_) {}
    }
    if (isLinuxX11Runtime() && isX11InputShapeWindow(win)) {
      await applyX11WindowInputShape(win, safeRects, {
        boundingRects,
        forceApply,
        source,
      });
      return;
    }
    if (!shouldUseNativeIgnoreMouse(win)) return;
    startLinuxPetInputPoller();
  }

  async function applyPetInputRegions(event, rects) {
    const win = BrowserWindow.fromWebContents(event.sender);
    return applyPetInputRegionsForWindow(win, rects, 'ipc');
  }

  ipcMain.on('neko:pet-input-regions', (event, rects) => {
    applyPetInputRegions(event, rects).catch((error) => {
      log('pet input regions update failed:', error.message || error);
    });
  });

  ipcMain.on('neko:has-set-shape', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    try {
      event.returnValue = canUseSetShape(win);
    } catch (e) {
      event.returnValue = false;
    }
  });

  ipcMain.on('neko:input-region-backend', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    try {
      const backend = typeof getInputRegionBackend === 'function'
        ? getInputRegionBackend(win)
        : { backend: 'unknown', canUseSetShape: canUseSetShape(win) };
      const patch = backend && backend.patchStatus ? backend.patchStatus : {};
      event.returnValue = {
        backend: backend && backend.backend ? backend.backend : 'unknown',
        canUseSetShape: !!(backend && backend.canUseSetShape),
        hasSetShapeMethod: !!(backend && backend.hasSetShapeMethod),
        patch: {
          verified: !!patch.verified,
          forced: !!patch.forced,
          disabled: !!patch.disabled,
          reason: patch.reason || '',
          electronVersion: patch.electronVersion || '',
          expectedElectronVersion: patch.expectedElectronVersion || '',
          compositor: patch.compositor || 'unknown',
        },
      };
    } catch (e) {
      event.returnValue = {
        backend: 'unknown',
        canUseSetShape: false,
        hasSetShapeMethod: false,
        patch: {
          verified: false,
          forced: false,
          disabled: false,
          reason: e && e.message ? e.message : 'backend-detect-failed',
          electronVersion: '',
          expectedElectronVersion: '',
          compositor: 'unknown',
        },
      };
    }
  });

  ipcMain.on('neko:x11-input-shape-active', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    try {
      const active = !!(win && !win.isDestroyed() && _x11ShapeActiveByWindow.has(win.id) && isX11InputShapeHelperReady());
      if (!active && win && !win.isDestroyed() && _x11ShapeActiveByWindow.has(win.id)) {
        clearX11ShapeAuthorityState(win.id);
      }
      event.returnValue = active;
    } catch (e) {
      event.returnValue = false;
    }
  });

  ipcMain.on('neko:debug-log', (event, message) => {
    try { log('[renderer-debug]', message); } catch (e) { /* ignore */ }
  });

  ipcMain.on('set-ignore-mouse-events', (event, ignore, options = {}) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win || win.isDestroyed()) return;
    try {
      setWindowIgnoreMouseEvents(win, ignore, options, 'renderer-ipc');
    } catch (e) {
      log('set-ignore-mouse-events failed:', e.message);
    }
  });

  // 提供鼠标坐标查询服务（解决 forward 失效问题）
  ipcMain.handle('get-cursor-point', async (event, options = {}) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win || win.isDestroyed()) return null;

    let point = screen.getCursorScreenPoint();
    let x11PointerState = null;
    const includeButtons = !!(options && options.includeButtons);
    const shouldQueryX11Pointer = includeButtons && (isXwaylandPetWindow(win) || isLinuxX11Runtime());
    if (shouldQueryX11Pointer) {
      try {
        x11PointerState = await queryX11PointerButtons(log, {
          readyTimeoutMs: 120,
          timeoutMs: 80,
        });
      } catch (_) {
        x11PointerState = null;
      }
    }
    if (!win || win.isDestroyed()) return null;
    const bounds = win.getBounds();
    const managedWindows = windowManager.getWindows();
    const chatWindows = [
      managedWindows && managedWindows.fullChat,
      managedWindows && managedWindows.chat,
      typeof windowManager.getFullChatWindow === 'function' ? windowManager.getFullChatWindow() : null,
      typeof windowManager.getReactChatWindow === 'function' ? windowManager.getReactChatWindow() : null,
    ];
    let overChatWindow = false;
    const seenChatWindows = new Set();
    for (const chatWindow of chatWindows) {
      if (!chatWindow || seenChatWindows.has(chatWindow.id)) continue;
      seenChatWindows.add(chatWindow.id);
      if (isPointInChatWindowForCursor(point, chatWindow, win)) {
        overChatWindow = true;
        break;
      }
    }

    return {
      x: point.x - bounds.x,
      y: point.y - bounds.y,
      screenX: point.x,
      screenY: point.y,
      overChatWindow,
      buttons: x11PointerState ? x11PointerState.buttons : null,
      x11Pointer: x11PointerState
        ? { x: x11PointerState.x, y: x11PointerState.y, mask: x11PointerState.mask }
        : null
    };
  });

  // 获取所有屏幕的边界信息（用于边缘检测）
  ipcMain.handle('get-all-displays', () => {
    const displays = screen.getAllDisplays();
    const mainWindow = getMainWindow();
    const windowBounds = mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : { x: 0, y: 0 };

    return displays.map(display => ({
      id: display.id,
      x: display.bounds.x - windowBounds.x,
      y: display.bounds.y - windowBounds.y,
      width: display.bounds.width,
      height: display.bounds.height,
      screenX: display.bounds.x,
      screenY: display.bounds.y,
      scaleFactor: display.scaleFactor
    }));
  });

  ipcMain.handle('get-primary-display-info', () => {
    const primary = screen.getPrimaryDisplay();
    return {
      id: primary.id,
      bounds: { ...primary.bounds },
      workArea: getPetBottomExpandedWorkArea(primary),
      scaleFactor: primary.scaleFactor
    };
  });

  ipcMain.handle('get-current-display', () => {
    const mainWindow = getMainWindow();
    if (!mainWindow || mainWindow.isDestroyed()) return null;

    const windowBounds = mainWindow.getBounds();
    const currentDisplay = screen.getDisplayMatching(windowBounds);

    return {
      id: currentDisplay.id,
      x: 0,
      y: 0,
      width: currentDisplay.bounds.width,
      height: currentDisplay.bounds.height,
      screenX: currentDisplay.bounds.x,
      screenY: currentDisplay.bounds.y,
      scaleFactor: currentDisplay.scaleFactor,
      workArea: getPetBottomExpandedWorkArea(currentDisplay)
    };
  });

  ipcMain.handle('move-window-to-display', async (event, screenX, screenY) => {
    const mainWindow = getMainWindow();
    if (!mainWindow || mainWindow.isDestroyed()) return { success: false, error: 'Window not found' };

    try {
      const displays = screen.getAllDisplays();
      const currentBounds = mainWindow.getBounds();
      let targetDisplay = null;
      for (const display of displays) {
        const b = display.bounds;
        if (screenX >= b.x && screenX < b.x + b.width &&
          screenY >= b.y && screenY < b.y + b.height) {
          targetDisplay = display;
          break;
        }
      }

      if (!targetDisplay) {
        log('move-window-to-display: 未找到包含点的屏幕, screenX=', screenX, 'screenY=', screenY);
        return { success: false, error: 'No display found at the given point' };
      }

      const currentDisplay = screen.getDisplayMatching(currentBounds);
      if (currentDisplay.id === targetDisplay.id) {
        return { success: true, sameDisplay: true };
      }

      log('move-window-to-display: 从屏幕', currentDisplay.id, '切换到屏幕', targetDisplay.id);
      log('  当前屏幕边界:', JSON.stringify(currentDisplay.bounds), '缩放:', currentDisplay.scaleFactor);
      log('  目标屏幕边界:', JSON.stringify(targetDisplay.bounds), '缩放:', targetDisplay.scaleFactor);

      const scaleRatio = targetDisplay.scaleFactor / currentDisplay.scaleFactor;
      const newBounds = getFullscreenDisplayBounds(targetDisplay);
      mainWindow.setBounds(newBounds);
      log('move-window-to-display: 窗口已移动到新边界:', JSON.stringify(newBounds));

      setTimeout(() => {
        const currentMainWindow = getMainWindow();
        if (currentMainWindow && !currentMainWindow.isDestroyed()) {
          currentMainWindow.webContents.send('display-changed', {
            displayId: targetDisplay.id,
            bounds: targetDisplay.bounds,
            scaleFactor: targetDisplay.scaleFactor,
            scaleRatio: scaleRatio,
            previousScaleFactor: currentDisplay.scaleFactor
          });
        }
      }, 32);

      return {
        success: true,
        displayId: targetDisplay.id,
        bounds: targetDisplay.bounds,
        scaleFactor: targetDisplay.scaleFactor,
        scaleRatio: scaleRatio
      };
    } catch (err) {
      log('move-window-to-display 错误:', err.message);
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('is-point-on-screen', (event, x, y) => {
    const mainWindow = getMainWindow();
    const windowBounds = mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : { x: 0, y: 0 };
    const screenX = x + windowBounds.x;
    const screenY = y + windowBounds.y;

    for (const display of screen.getAllDisplays()) {
      const b = display.bounds;
      if (screenX >= b.x && screenX < b.x + b.width &&
        screenY >= b.y && screenY < b.y + b.height) {
        return true;
      }
    }
    return false;
  });

  ipcMain.handle('clamp-to-screen', (event, x, y, elementWidth = 0, elementHeight = 0) => {
    const mainWindow = getMainWindow();
    const windowBounds = mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : { x: 0, y: 0 };
    const screenX = x + windowBounds.x;
    const screenY = y + windowBounds.y;

    for (const display of screen.getAllDisplays()) {
      const b = display.bounds;
      if (screenX >= b.x && screenX < b.x + b.width &&
        screenY >= b.y && screenY < b.y + b.height) {
        return { x, y, clamped: false };
      }
    }

    let nearestX = screenX, nearestY = screenY;
    let minDistance = Infinity;
    for (const display of screen.getAllDisplays()) {
      const b = display.bounds;
      const clampedX = Math.max(b.x, Math.min(screenX, b.x + b.width - 1));
      const clampedY = Math.max(b.y, Math.min(screenY, b.y + b.height - 1));
      const distance = Math.sqrt((screenX - clampedX) ** 2 + (screenY - clampedY) ** 2);
      if (distance < minDistance) {
        minDistance = distance;
        nearestX = clampedX;
        nearestY = clampedY;
      }
    }

    return {
      x: nearestX - windowBounds.x,
      y: nearestY - windowBounds.y,
      clamped: true
    };
  });

  return {
    _ignoreStateByWindow,
    _lastShapeByWindow,
    _lastShapeMetaByWindow,
    applyWindowShape,
    getEffectiveWindowShapeRects,
    getNativeWindowShapeRects,
    setWindowIgnoreMouseEvents,
  };
}

module.exports = {
  createWindowHostIpc,
};
