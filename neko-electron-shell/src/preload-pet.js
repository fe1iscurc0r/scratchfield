/**
 * preload-pet.js
 * Pet 窗口的 preload 脚本
 *
 * 职责：
 * 1. 鼠标穿透逻辑（hitTest）—— 与原 preload.js 基本一致
 * 2. window.electronScreen / electronDesktopCapturer API
 * 3. WebSocket 消息桥接 → 收到后端消息后通过 IPC 转发给主进程
 * 4. 监听来自其他窗口的 IPC 消息（如 Chat 发来的用户输入）
 */

const { ipcRenderer } = require('electron');

// ===== IPC 通道常量（统一来源）=====
const { WS_CHANNELS, CHAT_CHANNELS, CHAT_ACTION_CHANNELS, AGENT_CHANNELS, WS_PROXY_CHANNELS, JUKEBOX_CHANNELS, WINDOW_CONTROL_CHANNELS, SUBTITLE_CHANNELS, PET_CHANNELS } = require('./ipc-channels');
const { setupDarkMode, setupElectronShell, setupHostCapabilityBridge, setupTutorialOverlayBridge, setupTutorialLoadingOverlayBridge, setupGoodbyeChatComposerHiddenBridge, setupVoiceConfigSwitchingBridge, setupMusicPlayerBridge, setupAutostartBridge, setupToastOverride, setupVoiceToastOverride, setupSettingsSync, setupActivitySignalBridge } = require('./preload-common');

const _debugLinuxInput = process.env.NEKO_DEBUG_LINUX_INPUT === '1' || process.env.NEKO_DEBUG_WAYLAND_SHAPE === '1';
function debugLinuxInput(message) {
  if (!_debugLinuxInput) return;
  try { ipcRenderer.send('neko:debug-log', message); } catch (_) {}
}

// Wayland 检测（preload 级别）：必须与主进程 isLinuxWaylandRuntime() 逻辑一致
// —— 真实 session type 由 XDG_SESSION_TYPE / WAYLAND_DISPLAY 判定，
// 不能用 "argv 里没 ozone-platform=x11" 作为 Wayland 的充分条件。
const _isWaylandPreload = process.platform === 'linux' &&
  process.env.NEKO_FORCE_X11 !== '1' &&
  !process.argv.some(function(a) { return a.indexOf('ozone-platform=x11') >= 0; }) &&
  (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
const _isLinuxX11Preload = process.platform === 'linux' && !_isWaylandPreload;
const _isCompatibilityModePreload = process.env.NEKO_COMPATIBILITY_MODE === '1' ||
  process.argv.some(function(a) {
    return a === '--disable-gpu-compositing' || a === '--disable-direct-composition';
  });
const _disableNativeReturnBallDrag = _isWaylandPreload ||
  (process.platform === 'win32' && _isCompatibilityModePreload);
window.__NEKO_DESKTOP_RUNTIME__ = Object.freeze({
  platform: process.platform,
  compatibilityMode: _isCompatibilityModePreload,
  disableNativeReturnBallDrag: _disableNativeReturnBallDrag,
  isLinux: process.platform === 'linux',
  isLinuxX11: _isLinuxX11Preload,
  isWayland: _isWaylandPreload
});

if (process.platform === 'linux') {
  window.addEventListener('neko:main-ui-hidden-by-model-manager-changed', function(event) {
    var hidden = !!(event && event.detail && event.detail.hidden);
    ipcRenderer.send('neko:model-manager-main-ui-hidden', { hidden: hidden });
  });
}

// ===== 穿透逻辑（手动切换 + 节流，减轻 DWM 压力）=====

let lastIgnoreState = null;
let isCtrlPressed = false;
let _transitionFrozen = false;
let _frozenTimer = null;
let _yuiGuidePluginDashboardSkipBypassActive = false;
let _yuiGuideTutorialInputBypassActive = false;
let _yuiGuideTutorialInputBypassExpiryTimer = null;
let _yuiGuidePetInputResetGeneration = 0;
let _yuiGuidePetInputResetTimers = [];
let _yuiGuideTutorialLifecycleGeneration = 0;
let _yuiGuideTutorialLifecycleGenerationlessActive = false;
let _forceWaylandPetShapeRefresh = null;
let _lastSwitchTime = 0;
let _pendingTimeout = null;
const _MIN_SWITCH_INTERVAL = 100; // ms，开启穿透的最小间隔
let _lastHitResult = false;       // 上次 hitTest 结果，用于滞后判定
const _HYSTERESIS_PX = 10;        // 滞后区像素，防止模型边缘 true↔false 振荡（施密特触发器）
const _YUI_GUIDE_INPUT_BYPASS_EXPIRY_MS = 5000;
const _YUI_GUIDE_INPUT_BYPASS_RECHECK_MS = 1000;
const _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE = 58;
const _IDLE_CHAT_MINIMIZED_CARRIER_SIZE = 88;
const _IDLE_CHAT_MINIMIZED_BALL_DOWN_OFFSET = 14;
let _idleChatMinimizedState = {
  minimized: false,
  screenRect: null,
  timestamp: 0
};
let _petWindowScreenBounds = null;
let _petWindowScreenBoundsInFlight = false;
const _LINUX_X11_STALE_DRAG_MS = 8000;
const _LINUX_X11_INPUT_REGION_GRID = 96;
const _LINUX_X11_MODEL_SHAPE_GRID = 24;
const _LINUX_X11_MODEL_SHAPE_BANDS = 14;
const _LINUX_X11_BOUNDS_REFRESH_MS = 900;
const _LINUX_X11_REGION_REFRESH_MS = 1000;
const _LINUX_X11_MOUSE_POLL_MS = 24;
const _LINUX_X11_SYNTHETIC_MOVE_MS = 24;
const _LINUX_X11_BOUNDING_REGION_GRID = 128;
const DESKTOP_FULL_WINDOW_SURFACE_SELECTORS = [
  '#storage-location-overlay:not([hidden])',
  '.storage-location-overlay:not([hidden])',
  '.character-personality-overlay:not([hidden])',
  '#crop-overlay',
  '.crop-overlay',
  '#react-chat-window-overlay:not([hidden])',
  '.chat-export-preview-backdrop:not([hidden])',
  '.touch-config-overlay',
  '.modal-overlay',
  '.dialog-overlay',
  '.neko-dialog-overlay',
  '#prominent-notice-overlay',
  '.yui-guide-overlay',
  '.yui-guide-stage',
  '.driver-overlay',
  '.driver-popover',
  '.avatar-tool-manager-overlay'
];
const DESKTOP_FLOATING_INTERACTIVE_SURFACE_SELECTORS = [
  '#chat-avatar-preview-popup:not([hidden])',
  '#subtitle-display:not(.hidden)',
  '#subtitle-settings-panel:not(.hidden)',
  '#agent-task-hud',
  '.chat-export-preview-panel:not([hidden])',
  '.touch-config-window',
  '.modal-dialog',
  '.neko-dialog',
  '.dialog-modal',
  '.live2d-popup',
  '.vrm-popup',
  '.mmd-popup',
  '[id^="live2d-popup-"]',
  '[id^="vrm-popup-"]',
  '[id^="mmd-popup-"]',
  '[id^="pngtuber-popup-"]',
  '[id$="-floating-buttons"]',
  '[id$="-lock-icon"]',
  '[id$="-return-button-container"]',
  '.jukebox-container.open',
  '.jukebox-sam-panel',
  '.profiler-panel',
  '.mmd-debug-panel',
  '[data-neko-sidepanel]'
];
let _x11ModelDragSeenAt = 0;
let _x11ModelDragLastPointerActivityAt = 0;
let _x11LastInputRegionHash = '';
let _x11LastBoundingRegionHash = '';
let _x11InputRegionSentOnce = false;
let _x11LastInputRegions = [];
let _x11InputRegionReportTimer = null;
let _x11InputRegionReportDueAt = 0;
let _x11InputRegionPendingForce = false;
let _x11InputRegionPendingBoundsRefresh = false;
let _x11LastInputRegionMetaHash = '';
let _x11InputRegionReportInterval = null;
let _x11InputRegionObserver = null;
let _x11InputRegionBoundsRefreshedAt = 0;
let _x11InputRegionReporterStarted = false;
let _x11Live2DModelLoadHookTimer = null;
let _x11ModelDragInputExpanded = false;
let _x11LastSyntheticMoveAt = 0;
let _x11LastSyntheticMoveKey = '';
let _mousePollerInFlight = false;
let _x11LastNativePointerActivityAt = 0;
let _x11ModelPointerButtonsDown = false;
let _nativeMouseThroughPendingPoint = null;
let _nativeMouseThroughTimer = null;
let _nativeMouseThroughFrame = null;
let _nativeMouseThroughLastRunAt = 0;
const _NATIVE_MOUSE_THROUGH_COALESCE_MS = 24;
const _MODEL_PRECISE_HIT_TEST_INTERVAL_MS = 96;
const _MODEL_PRECISE_HIT_TEST_REUSE_PX = 14;
const _modelPreciseHitCache = {
  vrm: { at: 0, x: 0, y: 0, hit: false },
  mmd: { at: 0, x: 0, y: 0, hit: false }
};

window.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey) isCtrlPressed = true;
});
window.addEventListener('keyup', (e) => {
  if (!e.ctrlKey && !e.metaKey) isCtrlPressed = false;
});
window.addEventListener('blur', () => { isCtrlPressed = false; });

ipcRenderer.on('navigation-start', () => {
  if (_isWaylandPreload || _isLinuxX11Preload) return;
  ipcRenderer.send('set-ignore-mouse-events', false);
  lastIgnoreState = false;
});
ipcRenderer.on('page-fully-loaded', () => {
  if (_isWaylandPreload || _isLinuxX11Preload) return;
  ipcRenderer.send('set-ignore-mouse-events', false);
  lastIgnoreState = false;
});

// Storage location overlay is owned by the web app. The desktop side only needs
// a best-effort phase signal so it can protect satellite windows during shutdown.
let _lastStorageLocationPhase = '';
let _storageLocationRootObserver = null;
let _storageLocationOverlayObserver = null;

function detectStorageLocationPhase() {
  try {
    var overlay = document.getElementById('storage-location-overlay');
    if (!overlay || overlay.hidden) return 'hidden';
    var views = overlay.querySelectorAll('.storage-location-view');
    for (var i = 0; i < views.length; i += 1) {
      var view = views[i];
      if (!view || view.hidden) continue;
      if (view.querySelector('.storage-location-progress')) return 'maintenance';
      if (view.querySelector('.storage-location-error-text')) return 'error';
      if (view.querySelector('.storage-location-loader')) return 'loading';
      return 'selection_required';
    }
  } catch (e) {}
  return 'unknown';
}

function reportStorageLocationPhase(reason) {
  var phase = detectStorageLocationPhase();
  if (phase === _lastStorageLocationPhase) return;
  _lastStorageLocationPhase = phase;
  try {
    ipcRenderer.send('neko:storage-location-phase', { phase: phase, reason: reason || 'mutation' });
  } catch (e) {}
}

function observeStorageLocationOverlay() {
  var overlay = document.getElementById('storage-location-overlay');
  if (!overlay || _storageLocationOverlayObserver) return !!overlay;

  _storageLocationOverlayObserver = new MutationObserver(function () {
    reportStorageLocationPhase('mutation');
  });
  _storageLocationOverlayObserver.observe(overlay, {
    attributes: true,
    attributeFilter: ['hidden', 'class'],
    childList: true,
    subtree: true,
  });
  reportStorageLocationPhase('overlay-ready');
  return true;
}

function setupStorageLocationPhaseObserver() {
  try {
    reportStorageLocationPhase('initial');
    if (observeStorageLocationOverlay()) return;
    _storageLocationRootObserver = new MutationObserver(function () {
      reportStorageLocationPhase('mutation');
      if (observeStorageLocationOverlay() && _storageLocationRootObserver) {
        _storageLocationRootObserver.disconnect();
        _storageLocationRootObserver = null;
      }
    });
    _storageLocationRootObserver.observe(document.documentElement || document.body, {
      childList: true,
      subtree: true,
    });
  } catch (e) {}
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', setupStorageLocationPhaseObserver, { once: true });
} else {
  setupStorageLocationPhaseObserver();
}

function scheduleModelDragRecovery(reason, buttons) {
  if (_isLinuxX11Preload && buttons === 0) _x11ModelPointerButtonsDown = false;
  setTimeout(() => { recoverStaleModelDrag(reason, buttons); }, 0);
  if (_isLinuxX11Preload && buttons === 0) {
    setTimeout(() => { recoverStaleModelDrag(reason + '-settled', 0); }, 180);
  }
}

function updateX11ModelPointerFromEvent(event) {
  if (!_isLinuxX11Preload || !event) return;
  if (Number.isFinite(event.buttons)) {
    _x11ModelPointerButtonsDown = event.buttons > 0;
  }
}

function setupMouseThroughLogic() {
  window.addEventListener('mousemove', (event) => {
    if (_isLinuxX11Preload && event && event.isTrusted) _x11LastNativePointerActivityAt = Date.now();
    updateX11ModelPointerFromEvent(event);
    recoverStaleModelDrag('mousemove-buttons-zero', event.buttons);
    if (_isLinuxX11Preload) {
      if (event && event.isTrusted) {
        scheduleNativeMouseThroughPosition(event.clientX, event.clientY);
      }
      return;
    }
    if (event && event.isTrusted === false) {
      handleMousePosition(event.clientX, event.clientY);
    } else {
      scheduleNativeMouseThroughPosition(event.clientX, event.clientY);
    }
  });
  window.addEventListener('pointermove', (event) => {
    if (_isLinuxX11Preload && event && event.isTrusted) _x11LastNativePointerActivityAt = Date.now();
    updateX11ModelPointerFromEvent(event);
    recoverStaleModelDrag('pointermove-buttons-zero', event.buttons);
  }, { passive: true });
  var x11DragRecoveryCapture = _isLinuxX11Preload ? true : undefined;
  window.addEventListener('pointerup', () => {
    scheduleModelDragRecovery('pointerup', 0);
  }, x11DragRecoveryCapture);
  window.addEventListener('mouseup', () => {
    scheduleModelDragRecovery('mouseup', 0);
  }, x11DragRecoveryCapture);
  if (_isLinuxX11Preload) {
    window.addEventListener('pointerdown', (event) => {
      updateX11ModelPointerFromEvent(event);
      if (!event || event.button === 0) _x11ModelPointerButtonsDown = true;
    }, true);
    window.addEventListener('mousedown', (event) => {
      updateX11ModelPointerFromEvent(event);
      if (!event || event.button === 0) _x11ModelPointerButtonsDown = true;
    }, true);
    window.addEventListener('pointercancel', () => {
      scheduleModelDragRecovery('pointercancel', 0);
    }, true);
    document.addEventListener('pointerup', () => {
      scheduleModelDragRecovery('document-pointerup', 0);
    }, true);
    document.addEventListener('mouseup', () => {
      scheduleModelDragRecovery('document-mouseup', 0);
    }, true);
  }
  window.addEventListener('blur', () => {
    recoverStaleModelDrag('window-blur', 0);
  });
}

function scheduleNativeMouseThroughPosition(x, y) {
  if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return;
  _nativeMouseThroughPendingPoint = { x: Number(x), y: Number(y) };
  if (_nativeMouseThroughTimer || _nativeMouseThroughFrame) return;

  var now = typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
  var delay = Math.max(0, _NATIVE_MOUSE_THROUGH_COALESCE_MS - (now - _nativeMouseThroughLastRunAt));
  var scheduleFrame = function() {
    if (typeof window.requestAnimationFrame === 'function') {
      _nativeMouseThroughFrame = window.requestAnimationFrame(flushNativeMouseThroughPosition);
    } else {
      _nativeMouseThroughTimer = setTimeout(flushNativeMouseThroughPosition, 0);
    }
  };

  if (delay > 0) {
    _nativeMouseThroughTimer = setTimeout(function() {
      _nativeMouseThroughTimer = null;
      scheduleFrame();
    }, delay);
  } else {
    scheduleFrame();
  }
}

function flushNativeMouseThroughPosition() {
  _nativeMouseThroughTimer = null;
  _nativeMouseThroughFrame = null;
  var point = _nativeMouseThroughPendingPoint;
  _nativeMouseThroughPendingPoint = null;
  if (!point) return;
  _nativeMouseThroughLastRunAt = typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
  handleMousePosition(point.x, point.y);
}

function isBlankPage() {
  return window.location.href === 'about:blank';
}

function isHomePage() {
  return window.location.pathname === '/' || window.location.pathname === '/index.html';
}

function isModelBackgroundElement(el) {
  return el === document.body ||
    el.tagName === 'HTML' ||
    el.id === 'live2d-container' || el.id === 'live2d-canvas' ||
    el.classList.contains('live2d-container') || el.classList.contains('live2d') ||
    el.hasAttribute('data-live2d') ||
    el.id === 'vrm-canvas' || el.id === 'vrm-container' ||
    el.classList.contains('vrm-container') || el.hasAttribute('data-vrm') ||
    el.id === 'mmd-canvas' || el.id === 'mmd-container' ||
    el.classList.contains('mmd-container') || el.hasAttribute('data-mmd');
}

function isYuiGuideResidualOverlayElement(el) {
  try {
    if (!_yuiGuideTutorialInputBypassActive || !el || el.nodeType !== 1) return false;
    return !!(el.closest && el.closest('.yui-guide-overlay, .yui-guide-stage, .driver-overlay, .driver-popover'));
  } catch (_) {
    return false;
  }
}

function shouldSkipYuiGuideResidualShapeElement(el) {
  try {
    if (!_yuiGuideTutorialInputBypassActive || !el || el.nodeType !== 1) return false;
    if (el.id === 'neko-tutorial-skip-btn') return false;
    if (el.closest && el.closest('#neko-tutorial-skip-btn')) return false;
    return !!(el.closest && el.closest('.yui-guide-overlay, .yui-guide-stage, .driver-overlay, .driver-popover'));
  } catch (_) {
    return false;
  }
}

function isPointWithinVisibleTutorialSkipButton(x, y) {
  try {
    var button = document.getElementById('neko-tutorial-skip-btn');
    if (!button || !button.isConnected) return false;
    var style = window.getComputedStyle(button);
    if (
      style.display === 'none' ||
      style.visibility === 'hidden' ||
      style.pointerEvents === 'none' ||
      parseFloat(style.opacity || '1') === 0
    ) {
      return false;
    }
    var rect = button.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    var hitPadding = 8;
    return x >= rect.left - hitPadding &&
      x <= rect.right + hitPadding &&
      y >= rect.top - hitPadding &&
      y <= rect.bottom + hitPadding;
  } catch (_) {
    return false;
  }
}

function getActiveModelType() {
  var configuredType = (window.lanlan_config && window.lanlan_config.model_type) || 'live2d';

  if (configuredType === 'mmd') return 'mmd';
  if (configuredType === 'vrm') return 'vrm';

  if (configuredType === 'live3d') {
    // 优先读 sub_type 配置，避免 paused-but-not-disposed 的旧 manager 干扰判断
    var subType = (window.lanlan_config && window.lanlan_config.live3d_sub_type) || '';
    if (subType === 'mmd') return 'mmd';
    if (subType === 'vrm') return 'vrm';
    // fallback: 配置缺失时仍按实例探测
    if (window.mmdManager && window.mmdManager.currentModel) return 'mmd';
    if (window.vrmManager && window.vrmManager.currentModel) return 'vrm';
    return 'live3d';
  }

  return 'live2d';
}

function getManagerLockState(manager) {
  if (!manager) return false;
  if (typeof manager.isLocked !== 'undefined') return !!manager.isLocked;
  if (manager.interaction && typeof manager.interaction.isLocked !== 'undefined') {
    return !!manager.interaction.isLocked;
  }
  return false;
}

function isCurrentModelLocked() {
  try {
    var modelType = getActiveModelType();
    if (modelType === 'mmd') return getManagerLockState(window.mmdManager);
    if (modelType === 'vrm') return getManagerLockState(window.vrmManager);
    if (modelType === 'live2d') return getManagerLockState(window.live2dManager);
  } catch (e) {}
  return false;
}

function isManagerInGoodbyeMode(manager) {
  return !!(manager && manager._goodbyeClicked);
}

function isCurrentModelInGoodbyeMode() {
  try {
    var modelType = getActiveModelType();
    if (modelType === 'mmd' && window.mmdManager) return isManagerInGoodbyeMode(window.mmdManager);
    if (modelType === 'vrm' && window.vrmManager) return isManagerInGoodbyeMode(window.vrmManager);
    if (modelType === 'live2d' && window.live2dManager) return isManagerInGoodbyeMode(window.live2dManager);
  } catch (_) {}

  return isManagerInGoodbyeMode(window.live2dManager) ||
    isManagerInGoodbyeMode(window.vrmManager) ||
    isManagerInGoodbyeMode(window.mmdManager);
}

function isGoodbyeReturnBallElement(element) {
  return !!(element && typeof element.closest === 'function' && element.closest(
    '#live2d-return-button-container, #vrm-return-button-container, #mmd-return-button-container, ' +
    '#live2d-btn-return, #vrm-btn-return, #mmd-btn-return, ' +
    '.live2d-return-btn, .vrm-return-btn, .mmd-return-btn'
  ));
}

const RETURN_BALL_DRAG_ARM_MS = 1500;
let returnBallPrimaryDragArmedUntil = 0;

function armReturnBallPrimaryDrag(event) {
  if (!event || !isGoodbyeReturnBallElement(event.target)) return;
  returnBallPrimaryDragArmedUntil = Date.now() + RETURN_BALL_DRAG_ARM_MS;
}

function blockNonPrimaryReturnBallMouseEvent(event) {
  if (!event) return;
  if (event.button === 0) {
    armReturnBallPrimaryDrag(event);
    return;
  }
  if (!isGoodbyeReturnBallElement(event.target)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}

function blockReturnBallContextMenu(event) {
  if (!isGoodbyeReturnBallElement(event.target)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}

// 返回球拖动只允许左键；右键/中键在捕获阶段阻断，避免宿主窗口拖动层接手。
window.addEventListener('pointerdown', blockNonPrimaryReturnBallMouseEvent, true);
window.addEventListener('mousedown', blockNonPrimaryReturnBallMouseEvent, true);
window.addEventListener('touchstart', armReturnBallPrimaryDrag, true);
window.addEventListener('auxclick', blockNonPrimaryReturnBallMouseEvent, true);
window.addEventListener('contextmenu', blockReturnBallContextMenu, true);

function isPointOverGoodbyeInteractiveElement(x, y) {
  try {
    if (isPointWithinDesktopAvatarToolCompactZone(x, y)) return true;
  } catch (_) {}

  var el = document.elementFromPoint(x, y);
  if (!el) return false;
  if (isGoodbyeReturnBallElement(el)) return true;
  return !isModelBackgroundElement(el);
}

/**
 * 检测当前模型是否处于拖拽状态。
 * 模型交互层（live2d/vrm/mmd-interaction.js）只设局部 isDragging 标志，
 * 不会写入 DragHelpers.isDragging，因此 handleMousePosition 的已有检查不够。
 * 拖拽期间必须跳过 hitTest，否则鼠标移出包围盒 → setIgnoreState(true) → mouseup 丢失 → 拖拽卡死。
 */
function isModelDragging() {
  try {
    var mt = getActiveModelType();
    if (mt === 'live2d' && window.live2dManager) {
      if (window.live2dManager._isDraggingModel) return true;
    }
    if (mt === 'vrm' && window.vrmManager && window.vrmManager.interaction) {
      if (window.vrmManager.interaction.isDragging) return true;
    }
    if (mt === 'mmd' && window.mmdManager && window.mmdManager.interaction) {
      if (window.mmdManager.interaction.isDragging) return true;
    }
  } catch (_) {}
  return false;
}

function resetModelDraggingState(reason) {
  try {
    if (window.live2dManager) {
      window.live2dManager._isDraggingModel = false;
      var live2dModel = window.live2dManager.getCurrentModel && window.live2dManager.getCurrentModel();
      if (live2dModel) live2dModel.dragging = false;
    }
    if (window.vrmManager && window.vrmManager.interaction) {
      window.vrmManager.interaction.isDragging = false;
    }
    if (window.mmdManager && window.mmdManager.interaction) {
      window.mmdManager.interaction.isDragging = false;
    }
    if (window.DragHelpers && typeof window.DragHelpers.restoreButtonPointerEvents === 'function') {
      window.DragHelpers.restoreButtonPointerEvents();
    }
    if (document.body) document.body.classList.remove('neko-model-dragging');
    var canvas = document.getElementById('live2d-canvas')
      || document.getElementById('vrm-canvas')
      || document.getElementById('mmd-canvas');
    if (canvas) canvas.style.cursor = '';
    _x11ModelDragSeenAt = 0;
    _x11ModelDragLastPointerActivityAt = 0;
    _x11ModelDragInputExpanded = false;
    _x11ModelPointerButtonsDown = false;
    if (_isLinuxX11Preload) {
      try { ipcRenderer.send('neko:debug-log', '[x11-input] reset stale model drag: ' + (reason || 'unknown')); } catch (_) {}
      refreshPetInputRegionsSoon();
    }
  } catch (_) {}
}

function isExplicitDragReleaseReason(reason) {
  return /(?:pointerup|mouseup|pointercancel|window-blur|document-)/.test(String(reason || ''));
}

function normalizeIdleChatMinimizedScreenRect(rect) {
  if (!rect || typeof rect !== 'object') return null;
  var left = Number(rect.left);
  var top = Number(rect.top);
  var width = Number(rect.width);
  var height = Number(rect.height);
  if (!Number.isFinite(left) || !Number.isFinite(top) || !Number.isFinite(width) || !Number.isFinite(height)) return null;
  if (width <= 0 || height <= 0) return null;
  return {
    left: Math.round(left),
    top: Math.round(top),
    width: Math.round(width),
    height: Math.round(height),
    right: Math.round(left + width),
    bottom: Math.round(top + height)
  };
}

function buildIdleChatMinimizedBallInputShapeRects() {
  var size = _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE;
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

function isScreenPointInIdleChatMinimizedBallInputShape(sx, sy, rect) {
  if (!rect) return false;
  var boundsWidth = Math.max(1, Number(rect.width) || _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE);
  var boundsHeight = Math.max(1, Number(rect.height) || _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE);
  var visualWidth = Math.min(boundsWidth, _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE);
  var visualHeight = Math.min(boundsHeight, _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE);
  var offsetX = Math.max(0, (boundsWidth - visualWidth) / 2);
  var offsetY = Math.max(0, (boundsHeight - visualHeight) / 2);
  if (boundsWidth >= _IDLE_CHAT_MINIMIZED_CARRIER_SIZE && boundsHeight >= _IDLE_CHAT_MINIMIZED_CARRIER_SIZE) {
    offsetY += _IDLE_CHAT_MINIMIZED_BALL_DOWN_OFFSET;
  }
  var scaleX = visualWidth / _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE;
  var scaleY = visualHeight / _IDLE_CHAT_MINIMIZED_INPUT_SHAPE_SIZE;
  var localX = Number(sx) - Number(rect.left) - offsetX;
  var localY = Number(sy) - Number(rect.top) - offsetY;
  if (!Number.isFinite(localX) || !Number.isFinite(localY)) return false;
  return buildIdleChatMinimizedBallInputShapeRects().some(function(shape) {
    var left = shape.x * scaleX;
    var top = shape.y * scaleY;
    var right = left + shape.width * scaleX;
    var bottom = top + shape.height * scaleY;
    return localX >= left && localX < right && localY >= top && localY < bottom;
  });
}

function normalizePetWindowScreenBounds(bounds) {
  if (!bounds || typeof bounds !== 'object') return null;
  var x = Number(bounds.x);
  var y = Number(bounds.y);
  var width = Number(bounds.width);
  var height = Number(bounds.height);
  if (!Number.isFinite(x) || !Number.isFinite(y) ||
      !Number.isFinite(width) || !Number.isFinite(height) ||
      width <= 0 || height <= 0) {
    return null;
  }
  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.round(width),
    height: Math.round(height)
  };
}

function refreshPetWindowScreenBounds() {
  if (_petWindowScreenBoundsInFlight) return;
  _petWindowScreenBoundsInFlight = true;
  try {
    ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS).then(function(bounds) {
      _petWindowScreenBoundsInFlight = false;
      var normalized = normalizePetWindowScreenBounds(bounds);
      if (normalized) _petWindowScreenBounds = normalized;
    }).catch(function() {
      _petWindowScreenBoundsInFlight = false;
    });
  } catch (_) {
    _petWindowScreenBoundsInFlight = false;
  }
}

function getPetWindowScreenOrigin() {
  if (_petWindowScreenBounds &&
      Number.isFinite(Number(_petWindowScreenBounds.x)) &&
      Number.isFinite(Number(_petWindowScreenBounds.y))) {
    return { x: Number(_petWindowScreenBounds.x), y: Number(_petWindowScreenBounds.y) };
  }
  return {
    x: Number(window.screenX) || 0,
    y: Number(window.screenY) || 0
  };
}

function isPointOverIdleChatMinimizedBall(clientX, clientY) {
  if (!_idleChatMinimizedState.minimized || !_idleChatMinimizedState.screenRect) return false;
  var rect = _idleChatMinimizedState.screenRect;
  var origin = getPetWindowScreenOrigin();
  var sx = Math.round(origin.x + Number(clientX));
  var sy = Math.round(origin.y + Number(clientY));
  return isScreenPointInIdleChatMinimizedBallInputShape(sx, sy, rect);
}

function recoverStaleModelDrag(reason, buttons) {
  if (!_isLinuxX11Preload) return false;
  var dragging = isModelDragging();
  if (!dragging) {
    _x11ModelDragSeenAt = 0;
    _x11ModelDragLastPointerActivityAt = 0;
    if (_x11ModelDragInputExpanded) {
      _x11ModelDragInputExpanded = false;
      refreshPetInputRegionsSoon();
    }
    return false;
  }

  var now = Date.now();
  if (!_x11ModelDragSeenAt) _x11ModelDragSeenAt = now;
  if (buttons && buttons > 0) {
    _x11ModelPointerButtonsDown = true;
    _x11ModelDragLastPointerActivityAt = now;
    return false;
  }

  if (buttons === 0 && (isExplicitDragReleaseReason(reason) || now - _x11ModelDragSeenAt > 120)) {
    _x11ModelPointerButtonsDown = false;
    resetModelDraggingState(reason || 'buttons-released');
    return true;
  }

  var lastActivity = _x11ModelDragLastPointerActivityAt || _x11ModelDragSeenAt;
  if (now - lastActivity > _LINUX_X11_STALE_DRAG_MS) {
    resetModelDraggingState(reason || 'timeout');
    return true;
  }
  return false;
}

function dispatchSyntheticPointerMove(point) {
  if (!point) return;
  var pointerButtons = Number.isFinite(Number(point.buttons)) ? Number(point.buttons) : 0;
  if (_isLinuxX11Preload) {
    var now = Date.now();
    var moveKey = Math.round(point.x) + ',' + Math.round(point.y) + ',' + pointerButtons;
    if (moveKey === _x11LastSyntheticMoveKey || now - _x11LastSyntheticMoveAt < _LINUX_X11_SYNTHETIC_MOVE_MS) {
      return;
    }
    _x11LastSyntheticMoveKey = moveKey;
    _x11LastSyntheticMoveAt = now;
  }
  var pointerEventInit = {
    view: window, bubbles: true, cancelable: true,
    clientX: point.x, clientY: point.y, screenX: point.screenX, screenY: point.screenY,
    pointerId: 1, pointerType: 'mouse', isPrimary: true,
    buttons: pointerButtons,
    ctrlKey: isCtrlPressed, metaKey: isCtrlPressed
  };
  var mouseEventInit = {
    view: window, bubbles: true, cancelable: true,
    clientX: point.x, clientY: point.y, screenX: point.screenX, screenY: point.screenY,
    buttons: pointerButtons
  };
  window.dispatchEvent(new PointerEvent('pointermove', pointerEventInit));
  window.dispatchEvent(new MouseEvent('mousemove', mouseEventInit));
  if (document && document !== window) {
    document.dispatchEvent(new PointerEvent('pointermove', Object.assign({}, pointerEventInit, { bubbles: false })));
    document.dispatchEvent(new MouseEvent('mousemove', Object.assign({}, mouseEventInit, { bubbles: false })));
  }
}

function dispatchSyntheticPointerRelease(point) {
  if (!point) return;
  var pointerEventInit = {
    view: window, bubbles: true, cancelable: true,
    clientX: point.x, clientY: point.y, screenX: point.screenX, screenY: point.screenY,
    pointerId: 1, pointerType: 'mouse', isPrimary: true,
    button: 0, buttons: 0,
    ctrlKey: isCtrlPressed, metaKey: isCtrlPressed
  };
  var mouseEventInit = {
    view: window, bubbles: true, cancelable: true,
    clientX: point.x, clientY: point.y, screenX: point.screenX, screenY: point.screenY,
    button: 0, buttons: 0
  };
  window.dispatchEvent(new PointerEvent('pointerup', pointerEventInit));
  window.dispatchEvent(new MouseEvent('mouseup', mouseEventInit));
  if (document && document !== window) {
    document.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, pointerEventInit, { bubbles: false })));
    document.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, mouseEventInit, { bubbles: false })));
  }
}

function forwardPolledCursorFollow(point, options) {
  if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') return;
  var shouldDispatchSyntheticMove = !options || options.syntheticMove !== false;
  if (shouldDispatchSyntheticMove) {
    dispatchSyntheticPointerMove(point);
  }

  try {
    var gazeEvt = { type: 'pointermove', clientX: point.x, clientY: point.y };
    if (window.vrmManager && window.vrmManager._cursorFollow && window.vrmManager._cursorFollow._onPointerMove) {
      window.vrmManager._cursorFollow._onPointerMove(gazeEvt);
    }
    if (window.mmdManager && window.mmdManager.cursorFollow && window.mmdManager.cursorFollow._pointerMoveHandler) {
      window.mmdManager.cursorFollow._pointerMoveHandler(gazeEvt);
    }
  } catch (e) {}
}

function handleMousePosition(x, y) {
  if (isBlankPage()) { setIgnoreState(true, true); return; }
  if (!isHomePage()) { setIgnoreState(false); return; }

  // mini-game 进行中（body.neko-game-active 由 Xiao8 端 game_window_state_change=opened
  // 添加，closed 时移除）：DOM 容器已 display:none 但 JS 侧 model state 还活着，
  // 下面 checkHitTest 会用 model 旧 bbox 误判 onModel → 阻止穿透到 mini-game 窗口。
  // 与文件顶部 isBlankPage 同型——DOM 不在场就该单向 latch 进穿透态。
  if (document.body && document.body.classList.contains('neko-game-active')) {
    setIgnoreState(true, true);
    return;
  }

  // 拖拽期间跳过 elementFromPoint（同步 layout 查询），保持当前穿透状态
  if (window.DragHelpers && window.DragHelpers.isDragging) return;
  if (isModelDragging()) return;

  if (isCurrentModelInGoodbyeMode()) {
    _lastHitResult = false;
    if (desktopAvatarToolState.active) {
      resetDesktopAvatarToolRangeState();
      desktopAvatarToolPressState = null;
      clearDesktopAvatarToolNativeCursor();
    }
    setIgnoreState(!isPointOverGoodbyeInteractiveElement(x, y), true);
    return;
  }

  // 最小化聊天球是独立窗口。球态下 Pet 若因模型命中切成整窗不穿透，会盖住球的拖动事件。
  // 退出后的小猫/返回球模式已在上面优先处理，避免小猫和毛球重叠时无法拖动小猫。
  if (isPointOverIdleChatMinimizedBall(x, y)) {
    setIgnoreState(true, true);
    return;
  }

  if (getVisibleX11FullWindowSurfaceReason()) { setIgnoreState(false); return; }

  if (desktopAvatarToolState.active) {
    if (shouldCaptureDesktopAvatarToolFullWindowInput()) {
      setIgnoreState(false);
      return;
    }
    if (isPointWithinDesktopAvatarToolCompactZone(x, y) || getDesktopAvatarRangeHit(x, y)) {
      setIgnoreState(false);
    } else {
      setIgnoreState(true);
    }
    return;
  }

  var el = document.elementFromPoint(x, y);
  if (!el) { setIgnoreState(true); return; }
  if (isYuiGuideResidualOverlayElement(el)) { setIgnoreState(true, true); return; }

  if (!isModelBackgroundElement(el)) { setIgnoreState(false); return; }
  if (isCurrentModelLocked()) { setIgnoreState(true, true); return; }

  // hitTest + 滞后判定（施密特触发器）：
  // 已在模型上时用扩大边界检测，防止边缘 1px 振荡触发反复 DWM 重建
  var margin = _lastHitResult ? _HYSTERESIS_PX : 0;
  var onModel = checkHitTest(x, y, margin);
  _lastHitResult = onModel;

  if (onModel) {
    setIgnoreState(false);
  } else {
    setIgnoreState(true);
  }
}

function isPointInScreenBoundsRect(bounds, x, y, margin) {
  if (!bounds) return false;
  var m = margin || 0;
  return x >= bounds.minX - m && x <= bounds.maxX + m &&
    y >= bounds.minY - m && y <= bounds.maxY + m;
}

function isPointInScreenBoundsEllipse(bounds, x, y, margin) {
  if (!bounds) return false;
  var m = margin || 0;
  var cx = (bounds.minX + bounds.maxX) / 2;
  var cy = (bounds.minY + bounds.maxY) / 2;
  var rx = (bounds.maxX - bounds.minX) / 2 * 0.6 + m;
  var ry = (bounds.maxY - bounds.minY) / 2 * 0.95 + m;
  var nx = rx > 0 ? (x - cx) / rx : 0;
  var ny = ry > 0 ? (y - cy) / ry : 0;
  return (nx * nx + ny * ny) <= 1;
}

function maybePreciseModelHitTest(kind, interaction, x, y) {
  if (!interaction || typeof interaction._hitTestModel !== 'function') return false;

  var cache = _modelPreciseHitCache[kind];
  if (!cache) return false;

  var now = typeof performance !== 'undefined' && typeof performance.now === 'function' ? performance.now() : Date.now();
  var dx = x - cache.x;
  var dy = y - cache.y;
  var closeToCachedPoint = (dx * dx + dy * dy) <= (_MODEL_PRECISE_HIT_TEST_REUSE_PX * _MODEL_PRECISE_HIT_TEST_REUSE_PX);
  if (closeToCachedPoint && (now - cache.at) < _MODEL_PRECISE_HIT_TEST_INTERVAL_MS) {
    return cache.hit;
  }

  var hit = false;
  try {
    hit = !!interaction._hitTestModel(x, y);
  } catch (e) {
    hit = false;
  }
  cache.at = now;
  cache.x = x;
  cache.y = y;
  cache.hit = hit;
  return hit;
}

function checkVRMHitTest(x, y, margin) {
  try {
    if (isCurrentModelInGoodbyeMode()) return false;
    if (window.vrmManager && window.vrmManager.currentModel) {
      var interaction = window.vrmManager.interaction;
      if (!interaction) return false;
      if (typeof interaction.updateModelBoundsCache === 'function') interaction.updateModelBoundsCache();
      if (interaction._cachedScreenBounds) {
        var sb = interaction._cachedScreenBounds;
        if (isPointInScreenBoundsEllipse(sb, x, y, margin)) return true;
        if (isPointInScreenBoundsRect(sb, x, y, (margin || 0) + 12)) {
          return maybePreciseModelHitTest('vrm', interaction, x, y);
        }
        return false;
      }
      return maybePreciseModelHitTest('vrm', interaction, x, y);
    }
    return false;
  } catch (e) {
    return false;
  }
}

function checkMMDHitTest(x, y, margin) {
  try {
    if (isCurrentModelInGoodbyeMode()) return false;
    if (!window.mmdManager || !window.mmdManager.currentModel) return false;

    var interaction = window.mmdManager.interaction;
    if (!interaction) return false;

    if (typeof interaction.updateModelBoundsCache === 'function') {
      interaction.updateModelBoundsCache();
    } else if (typeof interaction.updateScreenBounds === 'function') {
      interaction.updateScreenBounds();
    }

    if (interaction._cachedScreenBounds) {
      var sb = interaction._cachedScreenBounds;
      if (isPointInScreenBoundsEllipse(sb, x, y, margin)) return true;
      if (isPointInScreenBoundsRect(sb, x, y, (margin || 0) + 12)) {
        return maybePreciseModelHitTest('mmd', interaction, x, y);
      }
      return false;
    }

    return maybePreciseModelHitTest('mmd', interaction, x, y);
  } catch (e) {
    return false;
  }
}

function checkLive2DHitTest(x, y, margin) {
  try {
    if (isCurrentModelInGoodbyeMode()) return false;
    if (!window.live2dManager) return false;

    var model = window.live2dManager.getCurrentModel();
    if (!model) return false;

    // 窗口坐标方案：canvas (0,0) = viewport (0,0)，无偏移，x/y 直接可用
    var bounds = model.getBounds();
    var m = margin || 0;
    if (x < bounds.x - m || x > bounds.x + bounds.width + m ||
        y < bounds.y - m || y > bounds.y + bounds.height + m) {
      return false;
    }

    try {
      if (typeof model.hitTest === 'function') {
        var hitAreas = model.hitTest(x, y);
        if (hitAreas && hitAreas.length > 0) return true;
      }
    } catch (e) {}

    var cx = bounds.x + bounds.width / 2;
    var cy = bounds.y + bounds.height / 2;
    var rx = bounds.width * 0.3 + m;
    var ry = bounds.height * 0.45 + m;
    var nx = (x - cx) / rx;
    var ny = (y - cy) / ry;
    return (nx * nx + ny * ny) <= 1;
  } catch (e) {
    return false;
  }
}

function checkHitTest(x, y, margin) {
  try {
    var modelType = getActiveModelType();

    if (modelType === 'mmd') return checkMMDHitTest(x, y, margin);
    if (modelType === 'vrm') return checkVRMHitTest(x, y, margin);
    if (modelType === 'live2d') return checkLive2DHitTest(x, y, margin);

    return false;
  } catch (e) {
    return false;
  }
}

function clampInputRegionRect(r) {
  if (!r) return null;
  var x = Math.max(0, Math.floor(r.x));
  var y = Math.max(0, Math.floor(r.y));
  var right = Math.min(window.innerWidth, Math.ceil(r.x + r.width));
  var bottom = Math.min(window.innerHeight, Math.ceil(r.y + r.height));
  if (right <= x || bottom <= y) return null;
  return { x: x, y: y, width: right - x, height: bottom - y };
}

function snapInputRegionRect(r, grid) {
  if (!r) return null;
  var g = Math.max(1, grid || _LINUX_X11_INPUT_REGION_GRID);
  var x = Math.floor(r.x / g) * g;
  var y = Math.floor(r.y / g) * g;
  var right = Math.ceil((r.x + r.width) / g) * g;
  var bottom = Math.ceil((r.y + r.height) / g) * g;
  return clampInputRegionRect({
    x: x,
    y: y,
    width: right - x,
    height: bottom - y
  });
}

function inputRegionsHash(rects) {
  if (!Array.isArray(rects) || rects.length === 0) return 'empty';
  return rects.map(function(r) {
    return [r.x, r.y, r.width, r.height].join(',');
  }).join(';');
}

function getFullWindowInputRegion() {
  return [{
    x: 0,
    y: 0,
    width: Math.max(1, Math.round(window.innerWidth || 1)),
    height: Math.max(1, Math.round(window.innerHeight || 1))
  }];
}

function getOnePixelPassthroughRegion() {
  return [{
    x: Math.max(0, Math.round((window.innerWidth || 1) - 1)),
    y: Math.max(0, Math.round((window.innerHeight || 1) - 1)),
    width: 1,
    height: 1
  }];
}

function isPointInInputRegions(point, rects) {
  if (!point || !Array.isArray(rects)) return false;
  return rects.some(function(r) {
    return r &&
      point.x >= r.x && point.x < r.x + r.width &&
      point.y >= r.y && point.y < r.y + r.height;
  });
}

function mergeInputRegionRects(rects, gap) {
  if (!Array.isArray(rects) || rects.length <= 1) return Array.isArray(rects) ? rects : [];
  var mergeGap = Math.max(0, gap || 0);
  var merged = rects.slice();
  var changed = true;
  while (changed) {
    changed = false;
    for (var i = 0; i < merged.length; i += 1) {
      for (var j = i + 1; j < merged.length; j += 1) {
        var a = merged[i];
        var b = merged[j];
        if (!a || !b) continue;
        var touches = a.x - mergeGap <= b.x + b.width &&
          b.x - mergeGap <= a.x + a.width &&
          a.y - mergeGap <= b.y + b.height &&
          b.y - mergeGap <= a.y + a.height;
        if (!touches) continue;
        var left = Math.min(a.x, b.x);
        var top = Math.min(a.y, b.y);
        var right = Math.max(a.x + a.width, b.x + b.width);
        var bottom = Math.max(a.y + a.height, b.y + b.height);
        merged[i] = { x: left, y: top, width: right - left, height: bottom - top };
        merged.splice(j, 1);
        changed = true;
        break;
      }
      if (changed) break;
    }
  }
  return merged;
}

function getVisibleX11FullWindowSurfaceReason() {
  try {
    if (!document || !document.body) return '';
    var bodyFullWindowClasses = [
      'storage-location-modal-open',
      'yui-taking-over',
      'yui-guide-home-ui-suppressed',
      'yui-guide-home-driver-hidden',
      'neko-agent-hud-dragging',
      'jukebox-dragging',
      'jukebox-resizing',
      'sam-panel-dragging'
    ];
    for (var c = 0; c < bodyFullWindowClasses.length; c += 1) {
      if (document.body.classList.contains(bodyFullWindowClasses[c])) {
        if (_yuiGuideTutorialInputBypassActive && isYuiGuideFullWindowSurfaceReason('body:' + bodyFullWindowClasses[c])) {
          continue;
        }
        return 'body:' + bodyFullWindowClasses[c];
      }
    }

    var selectors = DESKTOP_FULL_WINDOW_SURFACE_SELECTORS;
    for (var s = 0; s < selectors.length; s += 1) {
      var nodes = document.querySelectorAll(selectors[s]);
      for (var i = 0; i < nodes.length; i += 1) {
        var el = nodes[i];
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) continue;
        var r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        if (_yuiGuideTutorialInputBypassActive && isYuiGuideFullWindowSurfaceReason('selector:' + selectors[s])) {
          continue;
        }
        return 'selector:' + selectors[s];
      }
    }
  } catch (_) {}
  return '';
}

function isYuiGuideFullWindowSurfaceReason(reason) {
  return /(?:yui-taking-over|yui-guide-home-ui-suppressed|yui-guide-home-driver-hidden|\.yui-guide-overlay|\.yui-guide-stage|\.driver-overlay|\.driver-popover)/.test(String(reason || ''));
}

function hasVisibleYuiGuideResidualOverlaySurface() {
  try {
    if (!document || !document.body) return false;
    if (
      document.body.classList.contains('yui-taking-over') ||
      document.body.classList.contains('yui-guide-home-ui-suppressed') ||
      document.body.classList.contains('yui-guide-home-driver-hidden')
    ) {
      return true;
    }
    var selectors = [
      '.yui-guide-overlay',
      '.yui-guide-stage',
      '.driver-overlay',
      '.driver-popover'
    ];
    for (var i = 0; i < selectors.length; i += 1) {
      var nodes = document.querySelectorAll(selectors[i]);
      for (var j = 0; j < nodes.length; j += 1) {
        var el = nodes[j];
        var style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) continue;
        var rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          return true;
        }
      }
    }
  } catch (_) {}
  return false;
}

function hasVisibleX11FullWindowSurface() {
  return !!getVisibleX11FullWindowSurfaceReason();
}

function getX11InputRegionMode(fullWindowInputReason) {
  if (fullWindowInputReason) return 'full-window-surface';
  return 'normal';
}

function getX11InputRegionMetaHash(fullWindowInputReason, inputMode) {
  return String(fullWindowInputReason || '') + '|' + String(inputMode || 'normal');
}

function addEllipseInputRegions(rects, bounds, options) {
  if (!rects || !bounds) return;
  var rxFactor = options && Number.isFinite(options.rxFactor) ? options.rxFactor : 0.62;
  var ryFactor = options && Number.isFinite(options.ryFactor) ? options.ryFactor : 0.96;
  var extraPad = options && Number.isFinite(options.extraPad) ? options.extraPad : 18;
  var bands = Math.max(6, Math.min(24, (options && options.bands) || _LINUX_X11_MODEL_SHAPE_BANDS));
  var cx = (bounds.left + bounds.right) / 2;
  var cy = (bounds.top + bounds.bottom) / 2;
  var rx = Math.max(1, (bounds.right - bounds.left) / 2 * rxFactor);
  var ry = Math.max(1, (bounds.bottom - bounds.top) / 2 * ryFactor);
  var bandHeight = Math.max(_LINUX_X11_MODEL_SHAPE_GRID, (ry * 2) / bands);

  for (var i = 0; i < bands; i += 1) {
    var y1 = cy - ry + i * bandHeight;
    var y2 = i === bands - 1 ? cy + ry : y1 + bandHeight;
    var sampleY = (y1 + y2) / 2;
    var ny = (sampleY - cy) / ry;
    if (Math.abs(ny) > 1) continue;
    var halfWidth = rx * Math.sqrt(Math.max(0, 1 - ny * ny));
    var rect = clampInputRegionRect({
      x: cx - halfWidth - extraPad,
      y: y1 - extraPad,
      width: halfWidth * 2 + extraPad * 2,
      height: (y2 - y1) + extraPad * 2
    });
    if (rect) rects.push(rect);
  }
}

function getVisibleElementInputRect(el, pad) {
  try {
    if (!el) return null;
    var style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return null;
    var r = el.getBoundingClientRect();
    if (!r || r.width <= 0 || r.height <= 0) return null;
    var p = pad || 0;
    return clampInputRegionRect({
      x: r.left - p,
      y: r.top - p,
      width: r.width + p * 2,
      height: r.height + p * 2
    });
  } catch (_) {
    return null;
  }
}

function getModelInputBounds(forceBoundsRefresh) {
  try {
    var modelType = getActiveModelType();
    if (modelType === 'live2d' && window.live2dManager) {
      var model = window.live2dManager.getCurrentModel && window.live2dManager.getCurrentModel();
      if (!model || !model.getBounds) return null;
      var b = model.getBounds();
      if (!b || b.width <= 0 || b.height <= 0) return null;
      return {
        left: b.x,
        top: b.y,
        right: b.x + b.width,
        bottom: b.y + b.height,
        modelType: modelType
      };
    }
    if (modelType === 'vrm' && window.vrmManager && window.vrmManager.interaction) {
      var vrm = window.vrmManager.interaction;
      if ((forceBoundsRefresh || !vrm._cachedScreenBounds) && typeof vrm.updateModelBoundsCache === 'function') {
        vrm.updateModelBoundsCache();
      }
      var sb = vrm._cachedScreenBounds;
      if (!sb) return null;
      return {
        left: sb.minX,
        top: sb.minY,
        right: sb.maxX,
        bottom: sb.maxY,
        modelType: modelType
      };
    }
    if (modelType === 'mmd' && window.mmdManager && window.mmdManager.interaction) {
      var mmd = window.mmdManager.interaction;
      if (forceBoundsRefresh || !mmd._cachedScreenBounds) {
        if (typeof mmd.updateModelBoundsCache === 'function') mmd.updateModelBoundsCache();
        else if (typeof mmd.updateScreenBounds === 'function') mmd.updateScreenBounds();
      }
      var sb2 = mmd._cachedScreenBounds;
      if (!sb2) return null;
      return {
        left: sb2.minX,
        top: sb2.minY,
        right: sb2.maxX,
        bottom: sb2.maxY,
        modelType: modelType
      };
    }
  } catch (_) {}
  return null;
}

function appendModelInputRegions(rects, forceBoundsRefresh) {
  var bounds = getModelInputBounds(forceBoundsRefresh);
  if (!bounds || bounds.right <= bounds.left || bounds.bottom <= bounds.top) return;

  addEllipseInputRegions(rects, bounds, {
    rxFactor: bounds.modelType === 'live2d' ? 0.6 : 0.62,
    ryFactor: bounds.modelType === 'live2d' ? 0.9 : 0.96,
    extraPad: 20
  });
}

function appendModelBoundingRegions(rects, bounds) {
  if (!rects || !bounds || bounds.right <= bounds.left || bounds.bottom <= bounds.top) return;
  var pad = bounds.modelType === 'live2d' ? 72 : 96;
  var snapped = snapInputRegionRect({
    x: bounds.left - pad,
    y: bounds.top - pad,
    width: (bounds.right - bounds.left) + pad * 2,
    height: (bounds.bottom - bounds.top) + pad * 2
  }, _LINUX_X11_BOUNDING_REGION_GRID);
  if (snapped) rects.push(snapped);
}

function collectPetInputRegions(forceBoundsRefresh) {
  if (hasVisibleX11FullWindowSurface()) {
    return getFullWindowInputRegion();
  }
  var rects = [];
  appendModelInputRegions(rects, forceBoundsRefresh);
  var selectors = DESKTOP_FLOATING_INTERACTIVE_SURFACE_SELECTORS.concat([
    '#live2d-lock-icon',
    '#vrm-lock-icon',
    '#mmd-lock-icon',
    '#live2d-floating-buttons',
    '#vrm-floating-buttons',
    '#mmd-floating-buttons',
    '#pngtuber-floating-buttons',
    '#live2d-return-button-container',
    '#vrm-return-button-container',
    '#mmd-return-button-container',
    '#neko-tutorial-skip-btn',
    '#pngtuber-return-button-container',
    '[id$="-floating-buttons"]',
    '[id$="-lock-icon"]',
    '[id$="-return-button-container"]'
  ]).join(', ');
  try {
    document.querySelectorAll(selectors).forEach(function(el) {
      var rect = getVisibleElementInputRect(el, 24);
      if (rect) rects.push(rect);
    });
  } catch (_) {}
  return rects;
}

function collectPetBoundingRegions(forceBoundsRefresh, inputRects) {
  if (hasVisibleX11FullWindowSurface()) {
    return getFullWindowInputRegion();
  }

  var rects = [];
  var bounds = getModelInputBounds(forceBoundsRefresh);
  appendModelBoundingRegions(rects, bounds);

  if (Array.isArray(inputRects)) {
    inputRects.forEach(function(r) {
      var expanded = snapInputRegionRect({
        x: r.x - 36,
        y: r.y - 36,
        width: r.width + 72,
        height: r.height + 72
      }, _LINUX_X11_BOUNDING_REGION_GRID);
      if (expanded) rects.push(expanded);
    });
  }

  rects = mergeInputRegionRects(rects, _LINUX_X11_BOUNDING_REGION_GRID);
  return rects.length ? rects : getOnePixelPassthroughRegion();
}

function reportPetInputRegions(force, forceBoundsRefresh) {
  if (!_isLinuxX11Preload) return;
  try {
    var now = Date.now();
    var shouldRefreshBounds = forceBoundsRefresh === true ||
      !_x11InputRegionBoundsRefreshedAt ||
      now - _x11InputRegionBoundsRefreshedAt >= _LINUX_X11_BOUNDS_REFRESH_MS;
    if (shouldRefreshBounds) _x11InputRegionBoundsRefreshedAt = now;
    var fullWindowInputReason = getVisibleX11FullWindowSurfaceReason();
    var inputMode = getX11InputRegionMode(fullWindowInputReason);
    var metaHash = getX11InputRegionMetaHash(fullWindowInputReason, inputMode);
    var rects = collectPetInputRegions(shouldRefreshBounds);
    var boundingRects = collectPetBoundingRegions(shouldRefreshBounds, rects);
    var hash = inputRegionsHash(rects);
    var boundingHash = inputRegionsHash(boundingRects);
    if (!force &&
        _x11InputRegionSentOnce &&
        hash === _x11LastInputRegionHash &&
        boundingHash === _x11LastBoundingRegionHash &&
        metaHash === _x11LastInputRegionMetaHash) {
      return;
    }
    _x11InputRegionSentOnce = true;
    _x11LastInputRegionHash = hash;
    _x11LastBoundingRegionHash = boundingHash;
    _x11LastInputRegionMetaHash = metaHash;
    _x11LastInputRegions = rects;
    ipcRenderer.send('neko:pet-input-regions', {
      inputRects: rects,
      boundingRects: boundingRects,
      inputMode: inputMode,
      fullWindowInputReason: fullWindowInputReason || null,
      forceApply: force === true
    });
  } catch (_) {}
}

function schedulePetInputRegionReport(delayMs, force, forceBoundsRefresh) {
  if (!_isLinuxX11Preload) return;
  _x11InputRegionPendingForce = _x11InputRegionPendingForce || force === true;
  _x11InputRegionPendingBoundsRefresh = _x11InputRegionPendingBoundsRefresh || forceBoundsRefresh === true;
  var delay = Math.max(0, delayMs || 0);
  var dueAt = Date.now() + delay;
  if (_x11InputRegionReportTimer && _x11InputRegionReportDueAt <= dueAt) return;
  if (_x11InputRegionReportTimer) clearTimeout(_x11InputRegionReportTimer);
  _x11InputRegionReportDueAt = dueAt;
  _x11InputRegionReportTimer = setTimeout(function() {
    var pendingForce = _x11InputRegionPendingForce;
    var pendingBoundsRefresh = _x11InputRegionPendingBoundsRefresh;
    _x11InputRegionReportTimer = null;
    _x11InputRegionReportDueAt = 0;
    _x11InputRegionPendingForce = false;
    _x11InputRegionPendingBoundsRefresh = false;
    reportPetInputRegions(pendingForce, pendingBoundsRefresh);
  }, delay);
}

function syncX11DragInputRegion() {
  if (!_isLinuxX11Preload) return;
  var dragging = isModelDragging();
  if (dragging && _x11ModelPointerButtonsDown) {
    return;
  }
  if (_x11ModelDragInputExpanded) {
    _x11ModelDragInputExpanded = false;
    schedulePetInputRegionReport(0, true, true);
  }
}

function isNekoIdleReturnBallDragActiveForInputRegion() {
  try {
    var nodes = document.querySelectorAll(
      '#live2d-return-button-container, #vrm-return-button-container, #mmd-return-button-container'
    );
    for (var i = 0; i < nodes.length; i += 1) {
      var state = nodes[i] && nodes[i].getAttribute && nodes[i].getAttribute('data-dragging');
      if (state === 'pending' || state === 'true') return true;
    }
  } catch (_) {}
  return false;
}

var _x11IdleCat1MotionInputRegionSuspended = false;
var _x11IdleCat1MotionInputRegionTimer = null;

function isNekoIdleReturnContainerNode(node) {
  try {
    if (!node || node.nodeType !== 1) return false;
    if (node.matches && node.matches('#live2d-return-button-container, #vrm-return-button-container, #mmd-return-button-container')) {
      return true;
    }
    return !!(node.closest && node.closest('#live2d-return-button-container, #vrm-return-button-container, #mmd-return-button-container'));
  } catch (_) {
    return false;
  }
}

function shouldSkipIdleCat1MotionInputRegionMutations(mutations) {
  if (!_x11IdleCat1MotionInputRegionSuspended) return false;
  if (!mutations || !mutations.length) return false;
  for (var i = 0; i < mutations.length; i += 1) {
    var mutation = mutations[i];
    if (!mutation || !isNekoIdleReturnContainerNode(mutation.target)) return false;
    if (mutation.type === 'attributes') {
      var attr = mutation.attributeName || '';
      if (attr !== 'style' && attr !== 'class' && attr !== 'hidden') return false;
    } else if (mutation.type !== 'childList') {
      return false;
    }
  }
  return true;
}

function applyIdleCat1MotionInputRegionState(active) {
  if (!_isLinuxX11Preload) return;
  var nextActive = !!active;
  _x11IdleCat1MotionInputRegionSuspended = nextActive;
  if (_x11IdleCat1MotionInputRegionTimer) {
    clearTimeout(_x11IdleCat1MotionInputRegionTimer);
    _x11IdleCat1MotionInputRegionTimer = null;
  }
  if (nextActive) {
    _x11IdleCat1MotionInputRegionTimer = setTimeout(function() {
      _x11IdleCat1MotionInputRegionTimer = null;
      if (!_x11IdleCat1MotionInputRegionSuspended) return;
      _x11IdleCat1MotionInputRegionSuspended = false;
      refreshPetInputRegionsSoon();
    }, 4000);
    return;
  }
  refreshPetInputRegionsSoon();
}

function refreshPetInputRegionsSoon() {
  schedulePetInputRegionReport(16, true, true);
  setTimeout(function() { schedulePetInputRegionReport(0, true, true); }, 180);
  setTimeout(function() { schedulePetInputRegionReport(0, true, true); }, 650);
}

function hookLive2DInputRegionLoaded() {
  if (!_isLinuxX11Preload) return false;
  var mgr = window.live2dManager;
  if (!mgr || typeof mgr !== 'object') return false;
  if (mgr.onModelLoaded && mgr.onModelLoaded._nekoX11InputRegionHooked) return true;
  var previous = typeof mgr.onModelLoaded === 'function' ? mgr.onModelLoaded : null;
  var wrapped = function(model, modelPath) {
    if (previous) {
      try { previous.call(this, model, modelPath); } catch (_) {}
    }
    refreshPetInputRegionsSoon();
  };
  wrapped._nekoX11InputRegionHooked = true;
  mgr.onModelLoaded = wrapped;
  return true;
}

function startPetInputRegionReporter() {
  if (!_isLinuxX11Preload || _x11InputRegionReporterStarted) return;
  _x11InputRegionReporterStarted = true;
  reportPetInputRegions(true, true);
  setTimeout(function() { schedulePetInputRegionReport(0, true, true); }, 80);
  setTimeout(function() { schedulePetInputRegionReport(0, true, true); }, 350);
  if (_x11InputRegionReportInterval) clearInterval(_x11InputRegionReportInterval);
  _x11InputRegionReportInterval = setInterval(function() {
    reportPetInputRegions(false, false);
  }, _LINUX_X11_REGION_REFRESH_MS);
  window.addEventListener('resize', refreshPetInputRegionsSoon);
  window.addEventListener('electron-display-changed', refreshPetInputRegionsSoon);
  window.addEventListener('live2d-model-ready', refreshPetInputRegionsSoon);
  window.addEventListener('live2d-floating-buttons-ready', refreshPetInputRegionsSoon);
  window.addEventListener('vrm-model-loaded', refreshPetInputRegionsSoon);
  window.addEventListener('mmd-model-loaded', refreshPetInputRegionsSoon);
  window.addEventListener('neko-agent-hud-drag-state', function(event) {
    var dragging = !!(event && event.detail && event.detail.dragging);
    schedulePetInputRegionReport(0, true, dragging);
    if (!dragging) refreshPetInputRegionsSoon();
  });
  window.addEventListener('neko:idle-cat1-motion-input-region-state', function(event) {
    var active = !!(event && event.detail && event.detail.active);
    applyIdleCat1MotionInputRegionState(active);
  });
  window.addEventListener('pointerdown', function() {
    setTimeout(syncX11DragInputRegion, 0);
    schedulePetInputRegionReport(0, true, false);
  }, true);
  window.addEventListener('pointermove', syncX11DragInputRegion, { passive: true, capture: true });
  window.addEventListener('pointerup', function() {
    setTimeout(syncX11DragInputRegion, 0);
    schedulePetInputRegionReport(0, true, false);
  }, true);
  window.addEventListener('mouseup', function() {
    setTimeout(syncX11DragInputRegion, 0);
    schedulePetInputRegionReport(0, true, false);
  }, true);
  document.addEventListener('mouseup', function() {
    setTimeout(syncX11DragInputRegion, 0);
    schedulePetInputRegionReport(0, true, false);
  }, true);
  window.addEventListener('pointercancel', function() {
    _x11ModelDragInputExpanded = false;
    refreshPetInputRegionsSoon();
  }, true);
  window.addEventListener('blur', function() {
    _x11ModelDragInputExpanded = false;
    refreshPetInputRegionsSoon();
  });

  hookLive2DInputRegionLoaded();
  var hookAttempts = 0;
  if (_x11Live2DModelLoadHookTimer) clearInterval(_x11Live2DModelLoadHookTimer);
  _x11Live2DModelLoadHookTimer = setInterval(function() {
    hookAttempts += 1;
    hookLive2DInputRegionLoaded();
    if (hookAttempts >= 50) {
      clearInterval(_x11Live2DModelLoadHookTimer);
      _x11Live2DModelLoadHookTimer = null;
    }
  }, 100);

  try {
    _x11InputRegionObserver = new MutationObserver(function(mutations) {
      if (isNekoIdleReturnBallDragActiveForInputRegion()) return;
      if (shouldSkipIdleCat1MotionInputRegionMutations(mutations)) return;
      schedulePetInputRegionReport(160, false, false);
    });
    _x11InputRegionObserver.observe(document.body || document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['style', 'class', 'hidden']
    });
  } catch (_) {}
}

// ===== 桌面端 Chat 道具光标 / Avatar interaction 桥接 =====
// Chat 窗口负责选择道具与窗口内视觉；Pet 窗口负责桌面人物命中、空白区反馈和
// Wayland 道具模式下的临时整窗输入接管。
const DESKTOP_AVATAR_TOOL_RANGE_PADDING = 48;
const DESKTOP_AVATAR_TOOL_COMPACT_SELECTOR = [
  '.composer-bottom-tools',
  '.composer-tool-menu',
  '.composer-icon-popover',
  '.composer-tool-btn',
  '.composer-icon-button',
  '.send-button-circle',
  '.window-topbar-actions',
  '.topbar-action-btn',
  '.message-action-button',
  '#live2d-floating-buttons',
  '#vrm-floating-buttons',
  '#mmd-floating-buttons',
  '#pngtuber-floating-buttons',
  '#live2d-return-button-container',
  '#vrm-return-button-container',
  '#mmd-return-button-container',
  '#pngtuber-return-button-container',
  '#live2d-lock-icon',
  '#vrm-lock-icon',
  '#mmd-lock-icon',
  '#pngtuber-lock-icon',
  '.live2d-floating-btn',
  '.vrm-floating-btn',
  '.mmd-floating-btn',
  '.pngtuber-floating-btn',
  '.live2d-trigger-btn',
  '.vrm-trigger-btn',
  '.mmd-trigger-btn',
  '.pngtuber-trigger-btn',
  '.live2d-return-btn',
  '.vrm-return-btn',
  '.mmd-return-btn',
  '.pngtuber-return-btn',
  '.live2d-popup',
  '.vrm-popup',
  '.mmd-popup',
  '.pngtuber-popup',
  '[id^="live2d-popup-"]',
  '[id^="vrm-popup-"]',
  '[id^="mmd-popup-"]',
  '[id^="pngtuber-popup-"]',
  '[id$="-floating-buttons"]',
  '[id$="-lock-icon"]',
  '[id$="-return-button-container"]',
  '[data-neko-sidepanel]',
].join(', ');

let desktopAvatarToolState = {
  active: false,
  toolId: null,
  tool: null,
  textContext: '',
};
let desktopAvatarToolRangeState = {
  x: 0,
  y: 0,
  screenX: null,
  screenY: null,
  withinAvatarRange: false,
  overCompactZone: false,
  overChatWindow: false,
  outsideViewport: false,
  avatarRangeHit: null,
};
let desktopAvatarToolBoundsCache = { expiresAt: 0, entries: [] };
let desktopAvatarToolHammerPhase = 'idle';
let desktopAvatarToolHammerTimeoutIds = [];
let desktopAvatarToolHammerEffectNodes = [];
let desktopAvatarToolFloatingId = 0;
let desktopAvatarToolBurstHistory = Object.create(null);
let desktopAvatarToolCursorKey = '';
let desktopAvatarToolPublishedCursorKey = '';
let desktopAvatarToolInlineCursorElement = null;
let desktopAvatarToolInlineCursorKey = '';
let desktopAvatarToolAvatarRangeVariants = {
  lollipop: 'primary',
  fist: 'primary',
  hammer: 'primary',
};
let desktopAvatarToolOutsideRangeVariants = {
  lollipop: 'primary',
  fist: 'primary',
  hammer: 'primary',
};
let desktopAvatarToolPressState = null;
let desktopAvatarToolOutsideHammerResetTimeout = null;
const DESKTOP_AVATAR_TOOL_CLICK_MOVE_THRESHOLD = 6;
const DESKTOP_AVATAR_TOOL_SOUND_PATHS = {
  lollipopBite: '/static/sounds/avatar-tools/lollipop-bite.mp3',
  coinDrop: '/static/sounds/avatar-tools/coin-drop.mp3',
  hammerSmall: '/static/sounds/avatar-tools/hammer-small.mp3',
  hammerBig: '/static/sounds/avatar-tools/hammer-big.mp3',
};

function isDesktopAvatarToolId(value) {
  return value === 'lollipop' || value === 'fist' || value === 'hammer';
}

function normalizeDesktopCursorVariant(value) {
  return value === 'secondary' || value === 'tertiary' ? value : 'primary';
}

function normalizeDesktopAvatarToolDescriptor(tool, fallbackToolId) {
  if (!tool || typeof tool !== 'object') return null;
  var toolId = isDesktopAvatarToolId(tool.id) ? tool.id : fallbackToolId;
  if (!isDesktopAvatarToolId(toolId)) return null;

  var iconImagePath = String(tool.iconImagePath || '');
  var cursorImagePath = String(tool.cursorImagePath || '');
  if (!iconImagePath || !cursorImagePath) return null;

  return {
    id: toolId,
    label: String(tool.label || ''),
    iconImagePath: iconImagePath,
    iconImagePathAlt: tool.iconImagePathAlt ? String(tool.iconImagePathAlt) : '',
    iconImagePathAlt2: tool.iconImagePathAlt2 ? String(tool.iconImagePathAlt2) : '',
    cursorImagePath: cursorImagePath,
    cursorImagePathAlt: tool.cursorImagePathAlt ? String(tool.cursorImagePathAlt) : '',
    cursorImagePathAlt2: tool.cursorImagePathAlt2 ? String(tool.cursorImagePathAlt2) : '',
    cursorHotspotX: Number.isFinite(Number(tool.cursorHotspotX)) ? Number(tool.cursorHotspotX) : 18,
    cursorHotspotY: Number.isFinite(Number(tool.cursorHotspotY)) ? Number(tool.cursorHotspotY) : 18,
    cursorNaturalWidth: Number.isFinite(Number(tool.cursorNaturalWidth)) && Number(tool.cursorNaturalWidth) > 0 ? Number(tool.cursorNaturalWidth) : 0,
    cursorNaturalHeight: Number.isFinite(Number(tool.cursorNaturalHeight)) && Number(tool.cursorNaturalHeight) > 0 ? Number(tool.cursorNaturalHeight) : 0,
    menuIconScale: Number.isFinite(Number(tool.menuIconScale)) ? Number(tool.menuIconScale) : 1,
  };
}

function resolveDesktopAvatarToolImagePaths(tool, variant) {
  var resolvedVariant = normalizeDesktopCursorVariant(variant);
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

function playDesktopAvatarToolSound(soundPath) {
  if (typeof Audio === 'undefined') return;
  try {
    var audio = new Audio(soundPath);
    audio.preload = 'auto';
    audio.volume = 0.9;
    var playPromise = audio.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(function() {});
    }
  } catch (_) {}
}

function resetDesktopAvatarToolVariants(toolId, avatarRangeVariant, outsideRangeVariant) {
  if (!isDesktopAvatarToolId(toolId)) return;
  desktopAvatarToolAvatarRangeVariants[toolId] = normalizeDesktopCursorVariant(avatarRangeVariant);
  desktopAvatarToolOutsideRangeVariants[toolId] = normalizeDesktopCursorVariant(outsideRangeVariant);
}

function clearDesktopAvatarToolOutsideHammerResetTimer(shouldResetToPrimary, shouldPublish) {
  if (desktopAvatarToolOutsideHammerResetTimeout) {
    window.clearTimeout(desktopAvatarToolOutsideHammerResetTimeout);
    desktopAvatarToolOutsideHammerResetTimeout = null;
  }
  if (shouldResetToPrimary !== false) {
    desktopAvatarToolOutsideRangeVariants.hammer = 'primary';
    if (shouldPublish !== false) {
      publishDesktopAvatarToolCursorState(false);
    }
  }
}

function clearDesktopAvatarToolHammerAnimation(shouldPublish) {
  desktopAvatarToolHammerTimeoutIds.forEach(function(timeoutId) { window.clearTimeout(timeoutId); });
  desktopAvatarToolHammerTimeoutIds = [];
  desktopAvatarToolHammerEffectNodes.forEach(function(node) {
    if (node && node.parentNode) {
      node.parentNode.removeChild(node);
    }
  });
  desktopAvatarToolHammerEffectNodes = [];
  desktopAvatarToolHammerPhase = 'idle';
  if (shouldPublish !== false) {
    publishDesktopAvatarToolCursorState(false);
  }
}

function clearDesktopAvatarToolBoundsCache() {
  desktopAvatarToolBoundsCache = { expiresAt: 0, entries: [] };
}

function ensureDesktopAvatarToolStyle() {
  var style = document.getElementById('neko-desktop-avatar-tool-cursor-style');
  if (!style) {
    style = document.createElement('style');
    style.id = 'neko-desktop-avatar-tool-cursor-style';
    style.textContent = [
      'html.neko-desktop-avatar-tool-cursor-active,',
      'html.neko-desktop-avatar-tool-cursor-active *,',
      'html.neko-desktop-avatar-tool-cursor-active *::before,',
      'html.neko-desktop-avatar-tool-cursor-active *::after { cursor: var(--neko-desktop-avatar-tool-cursor, auto) !important; }',
      '.neko-desktop-avatar-tool-inline-cursor {',
      '  position: fixed; left: 0; top: 0; z-index: 2147483600;',
      '  pointer-events: none; user-select: none; -webkit-user-drag: none;',
      '  object-fit: contain; transform-origin: 0 0;',
      '}',
      '.neko-desktop-lollipop-heart, .neko-desktop-fist-drop, .neko-desktop-hammer-impact {',
      '  position: fixed; left: 0; top: 0; z-index: 2147483599;',
      '  pointer-events: none; user-select: none;',
      '}',
      '.neko-desktop-lollipop-heart {',
      '  color: rgba(255,126,168,0.92); font-size: 22px; line-height: 1;',
      '  text-shadow: 0 2px 10px rgba(255,112,155,0.32);',
      '  animation: neko-desktop-heart-rise 1200ms ease-out forwards;',
      '}',
      '@keyframes neko-desktop-heart-rise {',
      '  0% { opacity: 0; transform: translate3d(0,10px,0) scale(0.7); }',
      '  15% { opacity: 1; }',
      '  100% { opacity: 0; transform: translate3d(var(--dx,0px),-120px,0) scale(1.12); }',
      '}',
      '.neko-desktop-fist-drop img {',
      '  display: block; width: 30px; height: 30px; object-fit: contain;',
      '  animation: neko-desktop-fist-drop 920ms ease-out forwards;',
      '}',
      '@keyframes neko-desktop-fist-drop {',
      '  0% { opacity: 1; transform: translate3d(0,0,0) rotate(0deg) scale(0.72); }',
      '  100% { opacity: 0; transform: translate3d(var(--dx,0px),var(--dy,-90px),0) rotate(var(--rot,160deg)) scale(0.9); }',
      '}',
      '.neko-desktop-hammer-impact {',
      '  width: 136px; height: 130px;',
      '  transform-origin: 60px 118px;',
      '  filter: drop-shadow(0 13px 22px rgba(22,34,58,0.3));',
      '  animation: neko-desktop-hammer-impact-cycle 640ms linear forwards;',
      '}',
      '.neko-desktop-hammer-impact.is-easter-egg {',
      '  filter: drop-shadow(0 0 18px rgba(255,194,92,0.55)) drop-shadow(0 13px 22px rgba(22,34,58,0.3));',
      '}',
      '.neko-desktop-hammer-impact img {',
      '  position: absolute; inset: 0; display: block; width: 100%; height: 100%;',
      '  object-fit: contain; pointer-events: none; user-select: none;',
      '}',
      '.neko-desktop-hammer-impact-secondary {',
      '  opacity: 0; transform-origin: 80.19px 68px;',
      '  transform: translate3d(19.62px,-9.01px,0) rotate(34.258deg) scale(0.999333);',
      '}',
      '.neko-desktop-hammer-impact.is-impact .neko-desktop-hammer-impact-primary { opacity: 0; }',
      '.neko-desktop-hammer-impact.is-impact .neko-desktop-hammer-impact-secondary { opacity: 1; }',
      '@keyframes neko-desktop-hammer-impact-cycle {',
      '  0% { opacity: 1; transform: rotate(0deg) scale(1); }',
      '  52% { transform: translate3d(18px,-12px,0) rotate(42deg) scale(1); }',
      '  66% { transform: translate3d(-22px,10px,0) rotate(-86deg) scale(1); }',
      '  81% { transform: translate3d(-20px,9px,0) rotate(-82deg) scale(1); }',
      '  90% { transform: translate3d(-14px,3px,0) rotate(-58deg) scale(1); }',
      '  96% { opacity: 1; transform: translate3d(-6px,-1px,0) rotate(-18deg) scale(1); }',
      '  100% { opacity: 0; transform: rotate(0deg) scale(0.94); }',
      '}',
    ].join('\n');
    (document.head || document.documentElement).appendChild(style);
  }
}

function getDesktopAvatarToolEffectiveVariant() {
  var toolId = desktopAvatarToolState.toolId;
  if (!isDesktopAvatarToolId(toolId)) return 'primary';
  var withinAvatarRange = desktopAvatarToolRangeState.withinAvatarRange
    && !desktopAvatarToolRangeState.overCompactZone
    && !desktopAvatarToolRangeState.overChatWindow
    && !desktopAvatarToolRangeState.outsideViewport;
  var avatarRangeVariant = desktopAvatarToolAvatarRangeVariants[toolId] || 'primary';
  var outsideRangeVariant = desktopAvatarToolOutsideRangeVariants[toolId] || 'primary';
  if (toolId === 'lollipop') {
    return avatarRangeVariant;
  }
  if (toolId === 'hammer') {
    return withinAvatarRange ? 'primary' : outsideRangeVariant;
  }
  return withinAvatarRange ? avatarRangeVariant : outsideRangeVariant;
}

function getDesktopAvatarToolImageKind() {
  var toolId = desktopAvatarToolState.toolId;
  var withinAvatarRange = desktopAvatarToolRangeState.withinAvatarRange
    && !desktopAvatarToolRangeState.overCompactZone
    && !desktopAvatarToolRangeState.overChatWindow
    && !desktopAvatarToolRangeState.outsideViewport;
  if (!withinAvatarRange) return 'cursor';
  if (toolId === 'lollipop') return 'cursor';
  if (toolId === 'hammer' && desktopAvatarToolHammerPhase !== 'idle') return 'hidden';
  return 'icon';
}

function getDesktopAvatarToolOverlayMetrics(toolId, imageKind) {
  if (imageKind === 'icon') {
    if (toolId === 'lollipop') return { displayWidth: 74, displayHeight: 108, scale: 1 };
    if (toolId === 'fist') return { displayWidth: 100, displayHeight: 102, scale: 1 };
    if (toolId === 'hammer') return { displayWidth: 136, displayHeight: 130, scale: 1 };
  }
  if (toolId === 'lollipop') return { displayWidth: 74, displayHeight: 108, scale: 0.56 };
  if (toolId === 'fist') return { displayWidth: 78, displayHeight: 80, scale: 0.56 };
  if (toolId === 'hammer') return { displayWidth: 100, displayHeight: 96, scale: 0.52 };
  return { displayWidth: 0, displayHeight: 0, scale: 1 };
}

function shouldUseDesktopAvatarToolInlineCursor() {
  return _isWaylandPreload;
}

function ensureDesktopAvatarToolInlineCursorElement() {
  if (desktopAvatarToolInlineCursorElement && desktopAvatarToolInlineCursorElement.isConnected) {
    return desktopAvatarToolInlineCursorElement;
  }
  ensureDesktopAvatarToolStyle();
  var image = document.createElement('img');
  image.className = 'neko-desktop-avatar-tool-inline-cursor';
  image.hidden = true;
  image.draggable = false;
  image.alt = '';
  (document.body || document.documentElement).appendChild(image);
  desktopAvatarToolInlineCursorElement = image;
  desktopAvatarToolInlineCursorKey = '';
  return image;
}

function clearDesktopAvatarToolInlineCursor() {
  desktopAvatarToolInlineCursorKey = '';
  var image = desktopAvatarToolInlineCursorElement;
  if (!image) return;
  image.hidden = true;
  image.style.transform = 'translate3d(-9999px, -9999px, 0)';
}

function updateDesktopAvatarToolInlineCursor(force) {
  if (
    !shouldUseDesktopAvatarToolInlineCursor()
    || !desktopAvatarToolState.active
    || !desktopAvatarToolState.tool
    || desktopAvatarToolRangeState.overChatWindow
  ) {
    clearDesktopAvatarToolInlineCursor();
    return;
  }

  var tool = desktopAvatarToolState.tool;
  var toolId = desktopAvatarToolState.toolId;
  var imageKind = getDesktopAvatarToolImageKind();
  if (imageKind === 'hidden') {
    clearDesktopAvatarToolInlineCursor();
    return;
  }
  var x = Number(desktopAvatarToolRangeState.x);
  var y = Number(desktopAvatarToolRangeState.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    clearDesktopAvatarToolInlineCursor();
    return;
  }

  var variant = getDesktopAvatarToolEffectiveVariant();
  var imagePaths = resolveDesktopAvatarToolImagePaths(tool, variant);
  var imagePath = imageKind === 'icon' ? imagePaths.iconImagePath : imagePaths.cursorImagePath;
  if (!imagePath) {
    clearDesktopAvatarToolInlineCursor();
    return;
  }
  var metrics = getDesktopAvatarToolOverlayMetrics(toolId, imageKind);
  var displayWidth = Number(metrics.displayWidth);
  var displayHeight = Number(metrics.displayHeight);
  var scale = Number(metrics.scale);
  var safeScale = Number.isFinite(scale) && scale > 0 ? scale : 1;
  var naturalWidth = Number.isFinite(Number(tool.cursorNaturalWidth)) && Number(tool.cursorNaturalWidth) > 0
    ? Number(tool.cursorNaturalWidth)
    : displayWidth;
  var naturalHeight = Number.isFinite(Number(tool.cursorNaturalHeight)) && Number(tool.cursorNaturalHeight) > 0
    ? Number(tool.cursorNaturalHeight)
    : displayHeight;
  var displayRatioX = Number.isFinite(naturalWidth) && naturalWidth > 0
    && Number.isFinite(displayWidth) && displayWidth > 0
      ? displayWidth / naturalWidth
      : 1;
  var displayRatioY = Number.isFinite(naturalHeight) && naturalHeight > 0
    && Number.isFinite(displayHeight) && displayHeight > 0
      ? displayHeight / naturalHeight
      : 1;
  var hotspotX = (Number.isFinite(Number(tool.cursorHotspotX)) ? Number(tool.cursorHotspotX) : 18) * displayRatioX * safeScale;
  var hotspotY = (Number.isFinite(Number(tool.cursorHotspotY)) ? Number(tool.cursorHotspotY) : 18) * displayRatioY * safeScale;
  var left = Math.round(x - hotspotX);
  var top = Math.round(y - hotspotY);
  var key = [
    Math.round(x),
    Math.round(y),
    imagePath,
    displayWidth,
    displayHeight,
    safeScale,
    left,
    top,
  ].join('|');
  if (!force && desktopAvatarToolInlineCursorKey === key) return;
  desktopAvatarToolInlineCursorKey = key;

  var image = ensureDesktopAvatarToolInlineCursorElement();
  if (image.getAttribute('src') !== imagePath) image.src = imagePath;
  if (Number.isFinite(displayWidth) && displayWidth > 0) {
    image.style.width = Math.round(displayWidth) + 'px';
  } else {
    image.style.removeProperty('width');
  }
  if (Number.isFinite(displayHeight) && displayHeight > 0) {
    image.style.height = Math.round(displayHeight) + 'px';
  } else {
    image.style.removeProperty('height');
  }
  image.hidden = false;
  image.style.transform = 'translate3d(' + left + 'px, ' + top + 'px, 0) scale(' + safeScale + ')';
}

function getDesktopAvatarToolScreenPoint(point, clientX, clientY) {
  var screenX = point && Number(point.screenX);
  var screenY = point && Number(point.screenY);
  if (!_isWaylandPreload && Number.isFinite(screenX) && Number.isFinite(screenY)) {
    return { screenX: screenX, screenY: screenY };
  }
  var origin = getPetWindowScreenOrigin();
  return {
    screenX: Number(origin.x) + Number(clientX || 0),
    screenY: Number(origin.y) + Number(clientY || 0),
  };
}

function normalizeDesktopAvatarToolScreenPoint(detail) {
  if (!detail || typeof detail !== 'object') return null;
  var nestedPoint = detail.cursorScreenPoint && typeof detail.cursorScreenPoint === 'object'
    ? detail.cursorScreenPoint
    : null;
  var screenX = Number.isFinite(Number(detail.cursorScreenX))
    ? Number(detail.cursorScreenX)
    : Number.isFinite(Number(detail.screenX))
      ? Number(detail.screenX)
      : nestedPoint && Number.isFinite(Number(nestedPoint.x))
        ? Number(nestedPoint.x)
        : NaN;
  var screenY = Number.isFinite(Number(detail.cursorScreenY))
    ? Number(detail.cursorScreenY)
    : Number.isFinite(Number(detail.screenY))
      ? Number(detail.screenY)
      : nestedPoint && Number.isFinite(Number(nestedPoint.y))
        ? Number(nestedPoint.y)
        : NaN;
  if (!Number.isFinite(screenX) || !Number.isFinite(screenY)) return null;
  return { screenX: screenX, screenY: screenY };
}

function normalizeDesktopAvatarToolInitialPoint(detail) {
  var screenPoint = normalizeDesktopAvatarToolScreenPoint(detail);
  if (!screenPoint) return null;
  var origin = getPetWindowScreenOrigin();
  return {
    x: screenPoint.screenX - Number(origin.x || 0),
    y: screenPoint.screenY - Number(origin.y || 0),
    screenX: screenPoint.screenX,
    screenY: screenPoint.screenY,
    overChatWindow: detail.overChatWindow === true,
  };
}

function normalizeDesktopAvatarToolForwardedPointer(payload) {
  if (!payload || typeof payload !== 'object') return null;
  var point = normalizeDesktopAvatarToolInitialPoint(payload);
  if (!point) return null;
  var rawType = typeof payload.type === 'string' ? payload.type : '';
  var type = rawType === 'pointerdown' ? 'down'
    : rawType === 'pointerup' ? 'up'
      : rawType === 'pointercancel' ? 'cancel'
        : rawType;
  if (type !== 'down' && type !== 'up' && type !== 'move' && type !== 'cancel') {
    type = 'move';
  }
  var button = Number(payload.button);
  var buttons = Number(payload.buttons);
  return {
    type: type,
    button: Number.isFinite(button) ? button : 0,
    buttons: Number.isFinite(buttons) ? buttons : 0,
    clientX: point.x,
    clientY: point.y,
    screenX: point.screenX,
    screenY: point.screenY,
    overChatWindow: payload.overChatWindow === true,
  };
}

function handleDesktopAvatarToolForwardedPointer(payload) {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) return;
  var event = normalizeDesktopAvatarToolForwardedPointer(payload);
  if (!event) return;
  if (event.type === 'down') {
    handleDesktopAvatarToolPointerDown(event);
  } else if (event.type === 'up') {
    handleDesktopAvatarToolPointerUp(event);
  } else if (event.type === 'cancel') {
    handleDesktopAvatarToolPointerCancel();
  } else {
    handleDesktopAvatarToolPointerMove(event);
  }
}

function publishDesktopAvatarToolCursorState(force) {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) {
    clearDesktopAvatarToolInlineCursor();
    if (desktopAvatarToolPublishedCursorKey !== 'inactive' || force) {
      ipcRenderer.send(PET_CHANNELS.AVATAR_TOOL_CURSOR_STATE, {
        active: false,
        toolId: null,
        tool: null,
        timestamp: Date.now(),
      });
      desktopAvatarToolPublishedCursorKey = 'inactive';
    }
    return;
  }

  var toolId = desktopAvatarToolState.toolId;
  var variant = getDesktopAvatarToolEffectiveVariant();
  var imageKind = getDesktopAvatarToolImageKind();
  var metrics = getDesktopAvatarToolOverlayMetrics(toolId, imageKind);
  var withinAvatarRange = desktopAvatarToolRangeState.withinAvatarRange
    && !desktopAvatarToolRangeState.overCompactZone
    && !desktopAvatarToolRangeState.overChatWindow
    && !desktopAvatarToolRangeState.outsideViewport;
  var screenX = Number(desktopAvatarToolRangeState.screenX);
  var screenY = Number(desktopAvatarToolRangeState.screenY);
  var clientX = Number(desktopAvatarToolRangeState.x);
  var clientY = Number(desktopAvatarToolRangeState.y);
  var hasScreenPoint = Number.isFinite(screenX) && Number.isFinite(screenY);
  var hasClientPoint = Number.isFinite(clientX) && Number.isFinite(clientY);
  var key = [
    toolId,
    variant,
    imageKind,
    withinAvatarRange,
    desktopAvatarToolRangeState.overCompactZone,
    desktopAvatarToolRangeState.overChatWindow,
    desktopAvatarToolRangeState.outsideViewport,
    hasScreenPoint ? Math.round(screenX) : 'no-screen-x',
    hasScreenPoint ? Math.round(screenY) : 'no-screen-y',
    hasClientPoint ? Math.round(clientX) : 'no-client-x',
    hasClientPoint ? Math.round(clientY) : 'no-client-y',
    metrics.displayWidth,
    metrics.displayHeight,
    metrics.scale,
  ].join('|');
  updateDesktopAvatarToolInlineCursor(force);
  if (!force && desktopAvatarToolPublishedCursorKey === key) return;
  desktopAvatarToolPublishedCursorKey = key;

  var payload = {
    active: true,
    toolId: toolId,
    variant: variant,
    avatarRangeVariant: desktopAvatarToolAvatarRangeVariants[toolId] || 'primary',
    outsideRangeVariant: desktopAvatarToolOutsideRangeVariants[toolId] || 'primary',
    imageKind: imageKind,
    visible: imageKind !== 'hidden',
    withinAvatarRange: withinAvatarRange,
    overCompactZone: !!desktopAvatarToolRangeState.overCompactZone,
    overChatWindow: !!desktopAvatarToolRangeState.overChatWindow,
    outsideViewport: !!desktopAvatarToolRangeState.outsideViewport,
    tool: desktopAvatarToolState.tool,
    textContext: desktopAvatarToolState.textContext,
    displayWidth: metrics.displayWidth,
    displayHeight: metrics.displayHeight,
    scale: metrics.scale,
    timestamp: Date.now(),
  };
  if (hasScreenPoint) {
    payload.screenX = screenX;
    payload.screenY = screenY;
  }
  if (hasClientPoint) {
    payload.cursorClientX = clientX;
    payload.cursorClientY = clientY;
  }
  ipcRenderer.send(PET_CHANNELS.AVATAR_TOOL_CURSOR_STATE, payload);
}

function clearDesktopAvatarToolNativeCursor() {
  desktopAvatarToolCursorKey = '';
  var root = document.documentElement;
  // 工具活跃时不移除 CSS cursor:none，退出时 pet 窗口销毁自然恢复
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) {
    root.classList.remove('neko-desktop-avatar-tool-cursor-active');
    root.style.removeProperty('--neko-desktop-avatar-tool-cursor');
  }
  publishDesktopAvatarToolCursorState(false);
}

function applyDesktopAvatarToolNativeCursor() {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) {
    clearDesktopAvatarToolNativeCursor();
    return;
  }

  var tool = desktopAvatarToolState.tool;
  var variant = getDesktopAvatarToolEffectiveVariant();
  var hotspotX = Number.isFinite(Number(tool.cursorHotspotX)) ? Number(tool.cursorHotspotX) : 18;
  var hotspotY = Number.isFinite(Number(tool.cursorHotspotY)) ? Number(tool.cursorHotspotY) : 18;
  var cursorKey = [tool.id, variant, 'none', hotspotX, hotspotY].join('|');

  ensureDesktopAvatarToolStyle();
  var root = document.documentElement;
  if (desktopAvatarToolCursorKey !== cursorKey) {
    root.style.setProperty('--neko-desktop-avatar-tool-cursor', 'none');
    desktopAvatarToolCursorKey = cursorKey;
  }
  root.classList.add('neko-desktop-avatar-tool-cursor-active');
  publishDesktopAvatarToolCursorState(false);
}

function resetDesktopAvatarToolRangeState(extra) {
  desktopAvatarToolRangeState = Object.assign({
    x: 0,
    y: 0,
    screenX: null,
    screenY: null,
    withinAvatarRange: false,
    overCompactZone: false,
    overChatWindow: false,
    outsideViewport: false,
    avatarRangeHit: null,
  }, extra || {});
}

function getDesktopAvatarToolFullWindowInputReason() {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) return '';
  return 'avatar-tool:' + String(desktopAvatarToolState.toolId || desktopAvatarToolState.tool.id || 'unknown');
}

function shouldCaptureDesktopAvatarToolFullWindowInput() {
  return _isWaylandPreload && !!getDesktopAvatarToolFullWindowInputReason();
}

function setDesktopAvatarToolIgnoreState(ignore, immediate) {
  setIgnoreState(shouldCaptureDesktopAvatarToolFullWindowInput() ? false : ignore, immediate);
}

function isDesktopElementVisible(elementId) {
  var element = document.getElementById(elementId);
  if (!element) return false;
  var computedStyle = window.getComputedStyle(element);
  return computedStyle.display !== 'none'
    && computedStyle.visibility !== 'hidden'
    && computedStyle.opacity !== '0'
    && element.getClientRects().length > 0;
}

function normalizeDesktopAvatarBounds(rawBounds) {
  if (!rawBounds || typeof rawBounds !== 'object') return null;
  var left = Number(rawBounds.left);
  var right = Number(rawBounds.right);
  var top = Number(rawBounds.top);
  var bottom = Number(rawBounds.bottom);

  if (!Number.isFinite(left) && Number.isFinite(rawBounds.x) && Number.isFinite(rawBounds.width)) {
    left = Number(rawBounds.x);
    right = left + Number(rawBounds.width);
  }
  if (!Number.isFinite(top) && Number.isFinite(rawBounds.y) && Number.isFinite(rawBounds.height)) {
    top = Number(rawBounds.y);
    bottom = top + Number(rawBounds.height);
  }
  if (!Number.isFinite(left) || !Number.isFinite(right) || !Number.isFinite(top) || !Number.isFinite(bottom)) {
    return null;
  }

  var width = right - left;
  var height = bottom - top;
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return null;
  }

  return {
    left: left,
    right: right,
    top: top,
    bottom: bottom,
    width: width,
    height: height,
    centerX: Number.isFinite(Number(rawBounds.centerX)) ? Number(rawBounds.centerX) : left + width / 2,
    centerY: Number.isFinite(Number(rawBounds.centerY)) ? Number(rawBounds.centerY) : top + height / 2,
  };
}

function getDesktopAvatarBoundsFromInteraction(interaction) {
  if (!interaction) return null;
  try {
    if (typeof interaction.updateModelBoundsCache === 'function') {
      interaction.updateModelBoundsCache();
    } else if (typeof interaction.updateScreenBounds === 'function') {
      interaction.updateScreenBounds();
    }
  } catch (_) {}

  var bounds = interaction._cachedScreenBounds;
  if (!bounds) return null;
  return normalizeDesktopAvatarBounds({
    left: bounds.minX,
    right: bounds.maxX,
    top: bounds.minY,
    bottom: bounds.maxY,
  });
}

function getDesktopAvatarBoundsEntries(options) {
  var bypassCache = !!(options && options.bypassCache);
  var now = performance.now();
  if (isCurrentModelInGoodbyeMode()) {
    desktopAvatarToolBoundsCache = {
      expiresAt: now + 80,
      entries: [],
    };
    return [];
  }
  if (!bypassCache && desktopAvatarToolBoundsCache.expiresAt > now) {
    return desktopAvatarToolBoundsCache.entries;
  }

  var entries = [];
  try {
    if (window.mmdManager && window.mmdManager.currentModel && isDesktopElementVisible('mmd-container')) {
      var mmdBounds = typeof window.mmdManager.getModelScreenBounds === 'function'
        ? normalizeDesktopAvatarBounds(window.mmdManager.getModelScreenBounds())
        : getDesktopAvatarBoundsFromInteraction(window.mmdManager.interaction);
      if (mmdBounds) entries.push({ type: 'mmd', bounds: mmdBounds });
    }
  } catch (_) {}
  try {
    if (window.vrmManager && window.vrmManager.currentModel && isDesktopElementVisible('vrm-container')) {
      var vrmBounds = typeof window.vrmManager.getModelScreenBounds === 'function'
        ? normalizeDesktopAvatarBounds(window.vrmManager.getModelScreenBounds())
        : getDesktopAvatarBoundsFromInteraction(window.vrmManager.interaction);
      if (vrmBounds) entries.push({ type: 'vrm', bounds: vrmBounds });
    }
  } catch (_) {}
  try {
    if (window.live2dManager && isDesktopElementVisible('live2d-container')) {
      var live2dBounds = null;
      if (typeof window.live2dManager.getModelScreenBounds === 'function') {
        live2dBounds = normalizeDesktopAvatarBounds(window.live2dManager.getModelScreenBounds());
      } else if (typeof window.live2dManager.getCurrentModel === 'function') {
        var model = window.live2dManager.getCurrentModel();
        live2dBounds = model && typeof model.getBounds === 'function'
          ? normalizeDesktopAvatarBounds(model.getBounds())
          : null;
      }
      if (live2dBounds) entries.push({ type: 'live2d', bounds: live2dBounds });
    }
  } catch (_) {}

  desktopAvatarToolBoundsCache = {
    expiresAt: now + 80,
    entries: entries,
  };
  return entries;
}

function pickDesktopAvatarBoundsEntry(options) {
  var entries = getDesktopAvatarBoundsEntries(options);
  if (!entries || entries.length === 0) return null;

  var activeType = getActiveModelType();
  for (var i = 0; i < entries.length; i += 1) {
    if (entries[i] && entries[i].type === activeType) return entries[i];
  }
  return entries[0] || null;
}

async function getSpatialAudioSourceBounds() {
  try {
    var entry = pickDesktopAvatarBoundsEntry();
    if (!entry || !entry.bounds) return null;

    var windowBounds = await ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS);
    if (!windowBounds || !Number.isFinite(Number(windowBounds.x)) || !Number.isFinite(Number(windowBounds.y))) {
      return null;
    }

    var b = entry.bounds;
    return {
      type: entry.type || getActiveModelType(),
      x: Number(windowBounds.x) + b.left,
      y: Number(windowBounds.y) + b.top,
      width: b.width,
      height: b.height,
      centerX: Number(windowBounds.x) + b.centerX,
      centerY: Number(windowBounds.y) + b.centerY,
    };
  } catch (_) {
    return null;
  }
}

var desktopCompactChatBoundsSnapshot = '';
var desktopCompactChatBoundsInFlight = false;
var desktopCompactChatBoundsDirty = false;
var desktopCompactChatBoundsLastSentAt = 0;
var desktopCompactChatBoundsSyncActive = false;
var desktopCompactChatBoundsTimer = 0;
var desktopCompactChatBoundsTimerIsAnimationFrame = false;
var desktopCompactChatBoundsBurstUntil = 0;
var desktopCompactChatBoundsObserveUntil = 0;
var desktopCompactChatBoundsInteractionActive = false;
var desktopCompactChatBoundsModelDragActive = false;
var desktopCompactChatBoundsSyncEpoch = 0;
var DESKTOP_COMPACT_CHAT_BOUNDS_BURST_SAMPLE_MS = 33;
var DESKTOP_COMPACT_CHAT_BOUNDS_BURST_MS = 800;
var DESKTOP_COMPACT_CHAT_BOUNDS_MODEL_DRAG_SAMPLE_MS = 16;
var DESKTOP_COMPACT_CHAT_BOUNDS_OBSERVE_SAMPLE_MS = 160;
var DESKTOP_COMPACT_CHAT_BOUNDS_OBSERVE_MS = 1500;
var DESKTOP_COMPACT_CHAT_BOUNDS_STABLE_SAMPLE_MS = 500;
var DESKTOP_COMPACT_CHAT_BOUNDS_KEEPALIVE_MS = 1000;
var DESKTOP_COMPACT_CHAT_BOUNDS_EPSILON_PX = 1;

async function getDesktopCompactChatAvatarScreenBounds(options) {
  try {
    var opts = options || {};
    var entry = opts.forceFresh
      ? pickDesktopAvatarBoundsEntry({ bypassCache: true })
      : pickDesktopAvatarBoundsEntry();
    if (!entry || !entry.bounds) return null;

    var windowBounds = await ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS);
    if (!windowBounds || !Number.isFinite(Number(windowBounds.x)) || !Number.isFinite(Number(windowBounds.y))) {
      return null;
    }

    var b = entry.bounds;
    var left = Number(windowBounds.x) + b.left;
    var top = Number(windowBounds.y) + b.top;
    return {
      type: entry.type || getActiveModelType(),
      bounds: {
        left: left,
        top: top,
        right: left + b.width,
        bottom: top + b.height,
        width: b.width,
        height: b.height,
        centerX: Number(windowBounds.x) + b.centerX,
        centerY: Number(windowBounds.y) + b.centerY,
      },
      timestamp: Date.now(),
    };
  } catch (_) {
    return null;
  }
}

function quantizeDesktopCompactChatBoundsValue(value) {
  var number = Number(value);
  if (!Number.isFinite(number)) return 0;
  var step = Math.max(1, DESKTOP_COMPACT_CHAT_BOUNDS_EPSILON_PX);
  return Math.round(number / step) * step;
}

function getDesktopCompactChatBoundsSnapshot(payload) {
  if (!payload || !payload.bounds) return '';
  return [
    quantizeDesktopCompactChatBoundsValue(payload.bounds.left),
    quantizeDesktopCompactChatBoundsValue(payload.bounds.top),
    quantizeDesktopCompactChatBoundsValue(payload.bounds.width),
    quantizeDesktopCompactChatBoundsValue(payload.bounds.height),
    payload.type || ''
  ].join(':');
}

function isDesktopCompactChatBoundsBurstActive() {
  return Date.now() < desktopCompactChatBoundsBurstUntil;
}

function isDesktopCompactChatBoundsModelDragActive() {
  return desktopCompactChatBoundsModelDragActive || isModelDragging();
}

function getDesktopCompactChatBoundsSyncDelay() {
  var now = Date.now();
  if (isDesktopCompactChatBoundsModelDragActive()) return DESKTOP_COMPACT_CHAT_BOUNDS_MODEL_DRAG_SAMPLE_MS;
  if (desktopCompactChatBoundsInteractionActive) return DESKTOP_COMPACT_CHAT_BOUNDS_BURST_SAMPLE_MS;
  if (now < desktopCompactChatBoundsBurstUntil) return DESKTOP_COMPACT_CHAT_BOUNDS_BURST_SAMPLE_MS;
  if (now < desktopCompactChatBoundsObserveUntil) return DESKTOP_COMPACT_CHAT_BOUNDS_OBSERVE_SAMPLE_MS;
  return DESKTOP_COMPACT_CHAT_BOUNDS_STABLE_SAMPLE_MS;
}

function clearDesktopCompactChatBoundsSyncTimer() {
  if (!desktopCompactChatBoundsTimer) return;
  if (desktopCompactChatBoundsTimerIsAnimationFrame && typeof window.cancelAnimationFrame === 'function') {
    window.cancelAnimationFrame(desktopCompactChatBoundsTimer);
  } else {
    window.clearTimeout(desktopCompactChatBoundsTimer);
  }
  desktopCompactChatBoundsTimer = 0;
  desktopCompactChatBoundsTimerIsAnimationFrame = false;
}

function sendDesktopCompactChatAvatarBoundsSync(options) {
  if (!desktopCompactChatBoundsSyncActive) return;
  var opts = options || {};
  if (desktopCompactChatBoundsInFlight) {
    if (opts.forceFresh) desktopCompactChatBoundsDirty = true;
    return;
  }
  desktopCompactChatBoundsInFlight = true;
  var syncEpoch = desktopCompactChatBoundsSyncEpoch;
  var forceFresh = !!opts.forceFresh || isDesktopCompactChatBoundsModelDragActive() || isDesktopCompactChatBoundsBurstActive();
  getDesktopCompactChatAvatarScreenBounds({ forceFresh: forceFresh }).then(function(payload) {
    if (syncEpoch !== desktopCompactChatBoundsSyncEpoch) return;
    desktopCompactChatBoundsInFlight = false;
    if (!desktopCompactChatBoundsSyncActive) return;
    var snapshot = getDesktopCompactChatBoundsSnapshot(payload);
    var now = Date.now();
    if (!(snapshot === desktopCompactChatBoundsSnapshot && now - desktopCompactChatBoundsLastSentAt < DESKTOP_COMPACT_CHAT_BOUNDS_KEEPALIVE_MS)) {
      desktopCompactChatBoundsSnapshot = snapshot;
      desktopCompactChatBoundsLastSentAt = now;
      ipcRenderer.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC, payload || null);
    }
    if (desktopCompactChatBoundsDirty && desktopCompactChatBoundsSyncActive) {
      desktopCompactChatBoundsDirty = false;
      triggerDesktopCompactChatAvatarBoundsSync('dirty');
    }
  }).catch(function() {
    if (syncEpoch !== desktopCompactChatBoundsSyncEpoch) return;
    desktopCompactChatBoundsInFlight = false;
    if (desktopCompactChatBoundsDirty && desktopCompactChatBoundsSyncActive) {
      desktopCompactChatBoundsDirty = false;
      triggerDesktopCompactChatAvatarBoundsSync('dirty-error');
    }
  });
}

function scheduleDesktopCompactChatAvatarBoundsSync(delayMs, options) {
  if (!desktopCompactChatBoundsSyncActive || desktopCompactChatBoundsTimer) return;
  var opts = options || {};
  var delay = Number.isFinite(Number(delayMs))
    ? Math.max(0, Math.round(Number(delayMs)))
    : getDesktopCompactChatBoundsSyncDelay();
  var framePaced = typeof window.requestAnimationFrame === 'function' && (
    !!opts.framePaced || (
      isDesktopCompactChatBoundsModelDragActive()
      && delay <= DESKTOP_COMPACT_CHAT_BOUNDS_MODEL_DRAG_SAMPLE_MS
    )
  );
  if (framePaced) {
    desktopCompactChatBoundsTimerIsAnimationFrame = true;
    desktopCompactChatBoundsTimer = window.requestAnimationFrame(function() {
      desktopCompactChatBoundsTimer = 0;
      desktopCompactChatBoundsTimerIsAnimationFrame = false;
      sendDesktopCompactChatAvatarBoundsSync();
      scheduleDesktopCompactChatAvatarBoundsSync();
    });
    return;
  }
  desktopCompactChatBoundsTimerIsAnimationFrame = false;
  desktopCompactChatBoundsTimer = window.setTimeout(function() {
    desktopCompactChatBoundsTimer = 0;
    desktopCompactChatBoundsTimerIsAnimationFrame = false;
    sendDesktopCompactChatAvatarBoundsSync();
    scheduleDesktopCompactChatAvatarBoundsSync();
  }, delay);
}

function triggerDesktopCompactChatAvatarBoundsSync(reason, options) {
  if (!desktopCompactChatBoundsSyncActive) return;
  var opts = options || {};
  var modelDrag = !!opts.modelDrag || isDesktopCompactChatBoundsModelDragActive();
  if (modelDrag && desktopCompactChatBoundsTimer) {
    if (desktopCompactChatBoundsInFlight) desktopCompactChatBoundsDirty = true;
    return;
  }
  var now = Date.now();
  desktopCompactChatBoundsBurstUntil = Math.max(
    desktopCompactChatBoundsBurstUntil,
    now + DESKTOP_COMPACT_CHAT_BOUNDS_BURST_MS
  );
  desktopCompactChatBoundsObserveUntil = Math.max(
    desktopCompactChatBoundsObserveUntil,
    desktopCompactChatBoundsBurstUntil + DESKTOP_COMPACT_CHAT_BOUNDS_OBSERVE_MS
  );
  clearDesktopCompactChatBoundsSyncTimer();
  sendDesktopCompactChatAvatarBoundsSync({ forceFresh: true, reason: reason || '' });
  if (modelDrag) {
    scheduleDesktopCompactChatAvatarBoundsSync(DESKTOP_COMPACT_CHAT_BOUNDS_MODEL_DRAG_SAMPLE_MS, { framePaced: true });
    return;
  }
  scheduleDesktopCompactChatAvatarBoundsSync(DESKTOP_COMPACT_CHAT_BOUNDS_BURST_SAMPLE_MS);
}

function setDesktopCompactChatBoundsInteractionActive(active) {
  var nextActive = !!active;
  if (desktopCompactChatBoundsInteractionActive === nextActive) return;
  desktopCompactChatBoundsInteractionActive = nextActive;
  if (!desktopCompactChatBoundsSyncActive) return;
  if (nextActive) {
    clearDesktopCompactChatBoundsSyncTimer();
    sendDesktopCompactChatAvatarBoundsSync({ forceFresh: true, reason: 'interaction-start' });
    scheduleDesktopCompactChatAvatarBoundsSync(DESKTOP_COMPACT_CHAT_BOUNDS_BURST_SAMPLE_MS);
    return;
  }
  triggerDesktopCompactChatAvatarBoundsSync('interaction-stop');
}

function setDesktopCompactChatBoundsModelDragActive(active) {
  var nextActive = !!active;
  if (desktopCompactChatBoundsModelDragActive === nextActive) return;
  desktopCompactChatBoundsModelDragActive = nextActive;
  if (!desktopCompactChatBoundsSyncActive) return;
  if (nextActive) {
    clearDesktopCompactChatBoundsSyncTimer();
    sendDesktopCompactChatAvatarBoundsSync({ forceFresh: true, reason: 'model-drag-start' });
    scheduleDesktopCompactChatAvatarBoundsSync(DESKTOP_COMPACT_CHAT_BOUNDS_MODEL_DRAG_SAMPLE_MS, { framePaced: true });
    return;
  }
  triggerDesktopCompactChatAvatarBoundsSync('model-drag-stop');
}

function setDesktopCompactChatBoundsSyncActive(active) {
  var nextActive = !!active;
  if (desktopCompactChatBoundsSyncActive === nextActive) return;
  desktopCompactChatBoundsSyncActive = nextActive;
  if (!nextActive) {
    desktopCompactChatBoundsSyncEpoch += 1;
    desktopCompactChatBoundsInFlight = false;
    clearDesktopCompactChatBoundsSyncTimer();
    desktopCompactChatBoundsSnapshot = '';
    desktopCompactChatBoundsDirty = false;
    desktopCompactChatBoundsLastSentAt = 0;
    desktopCompactChatBoundsBurstUntil = 0;
    desktopCompactChatBoundsObserveUntil = 0;
    desktopCompactChatBoundsInteractionActive = false;
    desktopCompactChatBoundsModelDragActive = false;
    ipcRenderer.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC, null);
    return;
  }
  triggerDesktopCompactChatAvatarBoundsSync('subscription-active');
}

ipcRenderer.on(PET_CHANNELS.AVATAR_BOUNDS_SYNC_SUBSCRIPTION, function(_event, payload) {
  setDesktopCompactChatBoundsSyncActive(!!(payload && payload.active));
});
window.addEventListener('resize', function() {
  triggerDesktopCompactChatAvatarBoundsSync('resize');
});
window.addEventListener('electron-display-changed', function() {
  triggerDesktopCompactChatAvatarBoundsSync('display-changed');
});
window.addEventListener('pointermove', function() {
  var dragging = isModelDragging();
  setDesktopCompactChatBoundsModelDragActive(dragging);
  if (dragging) triggerDesktopCompactChatAvatarBoundsSync('model-drag-move', { modelDrag: true });
}, { passive: true, capture: true });
window.addEventListener('pointerup', function() {
  setDesktopCompactChatBoundsModelDragActive(false);
}, true);
window.addEventListener('pointercancel', function() {
  setDesktopCompactChatBoundsModelDragActive(false);
}, true);
window.addEventListener('blur', function() {
  setDesktopCompactChatBoundsModelDragActive(false);
});

ipcRenderer.on(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, function (_event, payload) {
  try {
    refreshPetWindowScreenBounds();
    var detail = payload && typeof payload === 'object' ? payload : {};
    _idleChatMinimizedState = {
      minimized: !!detail.minimized,
      screenRect: detail.minimized ? normalizeIdleChatMinimizedScreenRect(detail.screenRect) : null,
      timestamp: Number(detail.timestamp) || Date.now()
    };
    window.dispatchEvent(new CustomEvent('neko:idle-chat-minimized-state', {
      detail: {
        minimized: _idleChatMinimizedState.minimized,
        reason: typeof detail.reason === 'string' ? detail.reason : '',
        screenRect: _idleChatMinimizedState.screenRect,
        timestamp: _idleChatMinimizedState.timestamp
      }
    }));
  } catch (e) {}
});

ipcRenderer.on(PET_CHANNELS.REQUEST_IDLE_RETURN_COMPANION, function () {
  try {
    window.dispatchEvent(new CustomEvent('live2d-goodbye-click', {
      detail: {
        source: 'exit-retention-stay',
        reason: 'exit-retention-stay',
      },
    }));
  } catch (e) {}
});

function isPointInsideDesktopAvatarBounds(bounds, clientX, clientY) {
  if (
    clientX < bounds.left - DESKTOP_AVATAR_TOOL_RANGE_PADDING
    || clientX > bounds.right + DESKTOP_AVATAR_TOOL_RANGE_PADDING
    || clientY < bounds.top - DESKTOP_AVATAR_TOOL_RANGE_PADDING
    || clientY > bounds.bottom + DESKTOP_AVATAR_TOOL_RANGE_PADDING
  ) {
    return false;
  }

  var centerX = typeof bounds.centerX === 'number' ? bounds.centerX : (bounds.left + bounds.right) / 2;
  var centerY = typeof bounds.centerY === 'number' ? bounds.centerY : (bounds.top + bounds.bottom) / 2;
  var radiusX = bounds.width * 0.3 + DESKTOP_AVATAR_TOOL_RANGE_PADDING;
  var radiusY = bounds.height * 0.475 + DESKTOP_AVATAR_TOOL_RANGE_PADDING;
  if (radiusX <= 0 || radiusY <= 0) return false;

  var normalizedX = (clientX - centerX) / radiusX;
  var normalizedY = (clientY - centerY) / radiusY;
  return normalizedX * normalizedX + normalizedY * normalizedY <= 1;
}

function classifyDesktopAvatarTouchZone(bounds, clientX, clientY) {
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return 'body';
  var relativeX = Math.min(Math.max((clientX - bounds.left) / bounds.width, 0), 1);
  var relativeY = Math.min(Math.max((clientY - bounds.top) / bounds.height, 0), 1);
  if (relativeY <= 0.24 && (relativeX <= 0.24 || relativeX >= 0.76)) return 'ear';
  if (relativeY <= 0.34) return 'head';
  if (relativeY <= 0.62) return 'face';
  return 'body';
}

function getDesktopAvatarRangeHit(clientX, clientY) {
  if (isCurrentModelInGoodbyeMode()) return null;
  var entries = getDesktopAvatarBoundsEntries();
  for (var i = 0; i < entries.length; i += 1) {
    var bounds = entries[i].bounds;
    if (isPointInsideDesktopAvatarBounds(bounds, clientX, clientY)) {
      return {
        bounds: bounds,
        touchZone: classifyDesktopAvatarTouchZone(bounds, clientX, clientY),
      };
    }
  }
  if (checkHitTest(clientX, clientY, 18)) {
    var closestBounds = null;
    var closestDistance = Infinity;
    for (var j = 0; j < entries.length; j += 1) {
      var entryBounds = entries[j].bounds;
      if (!entryBounds) continue;
      var centerX = typeof entryBounds.centerX === 'number' ? entryBounds.centerX : (entryBounds.left + entryBounds.right) / 2;
      var centerY = typeof entryBounds.centerY === 'number' ? entryBounds.centerY : (entryBounds.top + entryBounds.bottom) / 2;
      var dx = clientX - centerX;
      var dy = clientY - centerY;
      var distance = dx * dx + dy * dy;
      if (distance < closestDistance) {
        closestDistance = distance;
        closestBounds = entryBounds;
      }
    }
    return {
      bounds: closestBounds,
      touchZone: closestBounds ? classifyDesktopAvatarTouchZone(closestBounds, clientX, clientY) : 'body',
      fallbackHitTest: true,
    };
  }
  return null;
}

function isPointWithinDesktopAvatarToolCompactZone(clientX, clientY) {
  var elements = [];
  if (typeof document.elementsFromPoint === 'function') {
    elements = document.elementsFromPoint(clientX, clientY);
  } else if (typeof document.elementFromPoint === 'function') {
    var element = document.elementFromPoint(clientX, clientY);
    if (element) elements = [element];
  }
  return elements.some(function(element) {
    return element && typeof element.closest === 'function' && !!element.closest(DESKTOP_AVATAR_TOOL_COMPACT_SELECTOR);
  });
}

function updateDesktopAvatarToolCursorFromPoint(point) {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) {
    clearDesktopAvatarToolNativeCursor();
    return;
  }
  if (!point || typeof point !== 'object') return;

  var x = Number(point.x);
  var y = Number(point.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  var screenPoint = getDesktopAvatarToolScreenPoint(point, x, y);

  if (isPointWithinVisibleTutorialSkipButton(x, y)) {
    resetDesktopAvatarToolRangeState({
      x: x,
      y: y,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
      overTutorialSkipButton: true,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(false, true);
    return;
  }

  if (point && point.overChatWindow === true) {
    resetDesktopAvatarToolRangeState({
      x: x,
      y: y,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
      overChatWindow: true,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(true, true);
    return;
  }

  if (isCurrentModelInGoodbyeMode()) {
    resetDesktopAvatarToolRangeState({
      x: x,
      y: y,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(!isPointOverGoodbyeInteractiveElement(x, y), true);
    return;
  }

  var isOutside = x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight;
  if (isOutside) {
    resetDesktopAvatarToolRangeState({
      x: x,
      y: y,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
      outsideViewport: true,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(true, true);
    return;
  }

  var overCompactZone = isPointWithinDesktopAvatarToolCompactZone(x, y);
  var avatarRangeHit = overCompactZone ? null : getDesktopAvatarRangeHit(x, y);
  desktopAvatarToolRangeState = {
    x: x,
    y: y,
    screenX: screenPoint.screenX,
    screenY: screenPoint.screenY,
    withinAvatarRange: !!avatarRangeHit,
    overCompactZone: overCompactZone,
    overChatWindow: false,
    outsideViewport: false,
    avatarRangeHit: avatarRangeHit,
  };

  if (desktopAvatarToolPressState) {
    var dx = x - desktopAvatarToolPressState.startX;
    var dy = y - desktopAvatarToolPressState.startY;
    if ((dx * dx + dy * dy) > (DESKTOP_AVATAR_TOOL_CLICK_MOVE_THRESHOLD * DESKTOP_AVATAR_TOOL_CLICK_MOVE_THRESHOLD)) {
      desktopAvatarToolPressState.moved = true;
    }
    applyDesktopAvatarToolNativeCursor();
    if (lastIgnoreState !== false) {
      setDesktopAvatarToolIgnoreState(false, true);
    }
    return;
  }

  if (!avatarRangeHit) {
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(overCompactZone ? false : true, true);
    return;
  }

  applyDesktopAvatarToolNativeCursor();
  setDesktopAvatarToolIgnoreState(false, true);
}

function setDesktopAvatarToolState(payload) {
  var detail = payload && typeof payload === 'object' ? payload : {};
  var nextToolId = isDesktopAvatarToolId(detail.toolId) ? detail.toolId : (detail.tool && detail.tool.id);
  var nextTool = normalizeDesktopAvatarToolDescriptor(detail.tool, nextToolId);
  if (!detail.active || !nextTool) {
    desktopAvatarToolState = {
      active: false,
      toolId: null,
      tool: null,
      textContext: '',
    };
    clearDesktopAvatarToolHammerAnimation();
    clearDesktopAvatarToolOutsideHammerResetTimer(true);
    clearDesktopAvatarToolBoundsCache();
    resetDesktopAvatarToolRangeState();
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    forceWaylandPetShapeRefreshSoon();
    syncMouseThroughStateWithCursor();
    return;
  }

  var previousToolId = desktopAvatarToolState.toolId;
  desktopAvatarToolState = {
    active: true,
    toolId: nextTool.id,
    tool: nextTool,
    textContext: String(detail.textContext || '').trim(),
  };

  if (previousToolId !== nextTool.id) {
    resetDesktopAvatarToolVariants(nextTool.id, detail.avatarRangeVariant, detail.outsideRangeVariant);
    clearDesktopAvatarToolHammerAnimation(false);
    clearDesktopAvatarToolOutsideHammerResetTimer(true, false);
    desktopAvatarToolBurstHistory = Object.create(null);
  }

  ensureDesktopAvatarToolStyle();
  refreshPetWindowScreenBounds();
  forceWaylandPetShapeRefreshSoon();
  var initialPoint = normalizeDesktopAvatarToolInitialPoint(detail);
  if (initialPoint) {
    updateDesktopAvatarToolCursorFromPoint(initialPoint);
    return;
  }
  if (_isWaylandPreload) {
    setDesktopAvatarToolIgnoreState(false, true);
    ipcRenderer.invoke('get-cursor-point')
      .then(function(point) {
        if (!desktopAvatarToolState.active || desktopAvatarToolState.toolId !== nextTool.id) return;
        if (point) updateDesktopAvatarToolCursorFromPoint(point);
      })
      .catch(function() {});
    return;
  }
  ipcRenderer.invoke('get-cursor-point')
    .then(function(point) {
      if (point) updateDesktopAvatarToolCursorFromPoint(point);
    })
    .catch(function() {});
}

function createDesktopAvatarInteractionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'avatar-int-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
}

function recordDesktopAvatarToolBurst(key, windowMs) {
  var now = Date.now();
  var recent = (desktopAvatarToolBurstHistory[key] || []).filter(function(timestamp) {
    return now - timestamp <= windowMs;
  });
  recent.push(now);
  desktopAvatarToolBurstHistory[key] = recent;
  return recent.length;
}

function emitDesktopAvatarToolInteraction(toolId, actionId, clientX, clientY, options) {
  var payload = {
    interactionId: createDesktopAvatarInteractionId(),
    toolId: toolId,
    actionId: actionId,
    target: 'avatar',
    pointer: {
      clientX: clientX,
      clientY: clientY,
    },
    timestamp: Date.now(),
  };
  if (desktopAvatarToolState.textContext) {
    payload.textContext = desktopAvatarToolState.textContext;
  }
  if (options && options.intensity) {
    payload.intensity = options.intensity;
  }
  if (options && options.touchZone && toolId !== 'lollipop') {
    payload.touchZone = options.touchZone;
  }
  if (options && options.rewardDrop && toolId === 'fist') {
    payload.rewardDrop = true;
  }
  if (options && options.easterEgg && toolId === 'hammer') {
    payload.easterEgg = true;
  }

  if (window.appButtons && typeof window.appButtons.sendAvatarInteractionPayload === 'function') {
    window.appButtons.sendAvatarInteractionPayload(payload);
  } else {
    window.dispatchEvent(new CustomEvent('react-chat-window:avatar-interaction', { detail: payload }));
  }
}

function spawnDesktopLollipopHearts(clientX, clientY) {
  for (var i = 0; i < 3; i += 1) {
    var heart = document.createElement('span');
    heart.className = 'neko-desktop-lollipop-heart';
    heart.textContent = '♥';
    heart.style.left = Math.round(clientX - 8 + (i - 1) * 16) + 'px';
    heart.style.top = Math.round(clientY - 30 - i * 5) + 'px';
    heart.style.setProperty('--dx', Math.round((i - 1) * 28) + 'px');
    heart.dataset.floatingId = String(++desktopAvatarToolFloatingId);
    (document.body || document.documentElement).appendChild(heart);
    window.setTimeout(function(node) {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    }, 1300, heart);
  }
}

function spawnDesktopFistDrops(clientX, clientY) {
  for (var i = 0; i < 3; i += 1) {
    var drop = document.createElement('span');
    drop.className = 'neko-desktop-fist-drop';
    drop.style.left = Math.round(clientX - 8 + Math.random() * 20 - 10) + 'px';
    drop.style.top = Math.round(clientY - 24 + Math.random() * 14 - 7) + 'px';
    drop.style.setProperty('--dx', Math.round(Math.random() * 88 - 44) + 'px');
    drop.style.setProperty('--dy', Math.round(-70 - Math.random() * 56) + 'px');
    drop.style.setProperty('--rot', Math.round(-120 + Math.random() * 240) + 'deg');
    var image = document.createElement('img');
    image.src = '/static/icons/cat_moneny.png';
    image.alt = '';
    drop.appendChild(image);
    (document.body || document.documentElement).appendChild(drop);
    window.setTimeout(function(node) {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    }, 1000, drop);
  }
}

function spawnDesktopHammerImpact(clientX, clientY, shouldTriggerEasterEgg) {
  if (!desktopAvatarToolState.tool) return;
  ensureDesktopAvatarToolStyle();

  var primaryPaths = resolveDesktopAvatarToolImagePaths(desktopAvatarToolState.tool, 'primary');
  var secondaryPaths = resolveDesktopAvatarToolImagePaths(desktopAvatarToolState.tool, 'secondary');
  var effect = document.createElement('span');
  effect.className = 'neko-desktop-hammer-impact' + (shouldTriggerEasterEgg ? ' is-easter-egg' : '');
  effect.style.left = Math.round(clientX - 60) + 'px';
  effect.style.top = Math.round(clientY - 118) + 'px';

  var primaryImage = document.createElement('img');
  primaryImage.className = 'neko-desktop-hammer-impact-primary';
  primaryImage.src = primaryPaths.iconImagePath;
  primaryImage.alt = '';

  var secondaryImage = document.createElement('img');
  secondaryImage.className = 'neko-desktop-hammer-impact-secondary';
  secondaryImage.src = secondaryPaths.iconImagePath;
  secondaryImage.alt = '';

  effect.appendChild(primaryImage);
  effect.appendChild(secondaryImage);
  (document.body || document.documentElement).appendChild(effect);
  desktopAvatarToolHammerEffectNodes.push(effect);
  return effect;
}

function startDesktopHammerSwing(clientX, clientY, shouldTriggerEasterEgg) {
  clearDesktopAvatarToolHammerAnimation(false);
  desktopAvatarToolHammerPhase = 'windup';
  var effect = spawnDesktopHammerImpact(clientX, clientY, shouldTriggerEasterEgg);
  publishDesktopAvatarToolCursorState(true);
  desktopAvatarToolHammerTimeoutIds = [
    window.setTimeout(function() {
      desktopAvatarToolHammerPhase = 'swing';
      publishDesktopAvatarToolCursorState(false);
    }, 240),
    window.setTimeout(function() {
      desktopAvatarToolHammerPhase = 'impact';
      publishDesktopAvatarToolCursorState(false);
      if (effect && effect.isConnected) {
        effect.classList.add('is-impact');
      }
    }, 420),
    window.setTimeout(function() {
      desktopAvatarToolHammerPhase = 'recover';
      publishDesktopAvatarToolCursorState(false);
    }, 520),
    window.setTimeout(function() {
      desktopAvatarToolHammerPhase = 'idle';
      desktopAvatarToolHammerTimeoutIds = [];
      if (effect && effect.parentNode) {
        effect.parentNode.removeChild(effect);
      }
      desktopAvatarToolHammerEffectNodes = desktopAvatarToolHammerEffectNodes.filter(function(node) {
        return node !== effect;
      });
      publishDesktopAvatarToolCursorState(true);
    }, shouldTriggerEasterEgg ? 700 : 620),
  ];
}

function completeDesktopAvatarToolClick(toolId, avatarRangeHit, clientX, clientY) {
  if (!avatarRangeHit) return;

  if (toolId === 'lollipop') {
    var currentLollipopVariant = desktopAvatarToolAvatarRangeVariants.lollipop || 'primary';
    var lollipopActionId = currentLollipopVariant === 'primary'
      ? 'offer'
      : currentLollipopVariant === 'secondary'
        ? 'tease'
        : 'tap_soft';
    var lollipopTapCount = currentLollipopVariant === 'tertiary'
      ? recordDesktopAvatarToolBurst('lollipop:tap_soft', 1800)
      : 0;
    emitDesktopAvatarToolInteraction('lollipop', lollipopActionId, clientX, clientY, {
      intensity: currentLollipopVariant === 'tertiary'
        ? (lollipopTapCount >= 4 ? 'burst' : 'rapid')
        : 'normal',
    });
    playDesktopAvatarToolSound(DESKTOP_AVATAR_TOOL_SOUND_PATHS.lollipopBite);
    if (currentLollipopVariant === 'tertiary') {
      spawnDesktopLollipopHearts(clientX, clientY);
    } else {
      desktopAvatarToolAvatarRangeVariants.lollipop = currentLollipopVariant === 'primary' ? 'secondary' : 'tertiary';
    }
    applyDesktopAvatarToolNativeCursor();
    return;
  }

  if (toolId === 'fist') {
    var shouldSpawnRewardDrop = Math.random() < 0.25;
    var fistTapCount = recordDesktopAvatarToolBurst('fist:poke', 1400);
    desktopAvatarToolAvatarRangeVariants.fist = 'secondary';
    desktopAvatarToolOutsideRangeVariants.fist = 'secondary';
    emitDesktopAvatarToolInteraction('fist', 'poke', clientX, clientY, {
      intensity: fistTapCount >= 4 ? 'rapid' : 'normal',
      rewardDrop: shouldSpawnRewardDrop,
      touchZone: avatarRangeHit.touchZone,
    });
    if (shouldSpawnRewardDrop) {
      playDesktopAvatarToolSound(DESKTOP_AVATAR_TOOL_SOUND_PATHS.coinDrop);
      spawnDesktopFistDrops(clientX, clientY);
    }
    applyDesktopAvatarToolNativeCursor();
    return;
  }

  if (toolId === 'hammer') {
    if (desktopAvatarToolHammerPhase !== 'idle') return;
    var shouldTriggerEasterEgg = Math.random() < 0.05;
    var hammerBonkCount = recordDesktopAvatarToolBurst('hammer:bonk', 3200);
    emitDesktopAvatarToolInteraction('hammer', 'bonk', clientX, clientY, {
      intensity: shouldTriggerEasterEgg
        ? 'easter_egg'
        : hammerBonkCount >= 3
          ? 'burst'
          : hammerBonkCount >= 2
            ? 'rapid'
            : 'normal',
      easterEgg: shouldTriggerEasterEgg,
      touchZone: avatarRangeHit.touchZone,
    });
    playDesktopAvatarToolSound(
      shouldTriggerEasterEgg
        ? DESKTOP_AVATAR_TOOL_SOUND_PATHS.hammerBig
        : DESKTOP_AVATAR_TOOL_SOUND_PATHS.hammerSmall
    );
    startDesktopHammerSwing(clientX, clientY, shouldTriggerEasterEgg);
  }
}

function handleDesktopAvatarToolPointerDown(event) {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) return;
  if (event.button !== 0) return;

  var clientX = event.clientX;
  var clientY = event.clientY;
  var screenPoint = getDesktopAvatarToolScreenPoint(event, clientX, clientY);

  if (event.overChatWindow === true) {
    resetDesktopAvatarToolRangeState({
      x: clientX,
      y: clientY,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
      overChatWindow: true,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(true, true);
    return;
  }

  if (isCurrentModelInGoodbyeMode()) {
    resetDesktopAvatarToolRangeState({
      x: clientX,
      y: clientY,
      screenX: screenPoint.screenX,
      screenY: screenPoint.screenY,
    });
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(!isPointOverGoodbyeInteractiveElement(clientX, clientY), true);
    return;
  }

  var overCompactZone = isPointWithinDesktopAvatarToolCompactZone(clientX, clientY);
  var avatarRangeHit = overCompactZone ? null : getDesktopAvatarRangeHit(clientX, clientY);

  desktopAvatarToolRangeState = {
    x: clientX,
    y: clientY,
    screenX: screenPoint.screenX,
    screenY: screenPoint.screenY,
    withinAvatarRange: !!avatarRangeHit,
    overCompactZone: overCompactZone,
    overChatWindow: false,
    outsideViewport: false,
    avatarRangeHit: avatarRangeHit,
  };

  if (overCompactZone || !avatarRangeHit) {
    if (!overCompactZone && desktopAvatarToolState.toolId === 'fist') {
      desktopAvatarToolAvatarRangeVariants.fist = 'secondary';
      desktopAvatarToolOutsideRangeVariants.fist = 'secondary';
      publishDesktopAvatarToolCursorState(true);
    }
    if (!overCompactZone && desktopAvatarToolState.toolId === 'hammer') {
      clearDesktopAvatarToolOutsideHammerResetTimer(false);
      desktopAvatarToolOutsideRangeVariants.hammer = 'secondary';
      publishDesktopAvatarToolCursorState(true);
      desktopAvatarToolOutsideHammerResetTimeout = window.setTimeout(function() {
        desktopAvatarToolOutsideHammerResetTimeout = null;
        desktopAvatarToolOutsideRangeVariants.hammer = 'primary';
        publishDesktopAvatarToolCursorState(true);
      }, 220);
    }
    desktopAvatarToolPressState = null;
    clearDesktopAvatarToolNativeCursor();
    setDesktopAvatarToolIgnoreState(overCompactZone ? false : true, true);
    return;
  }

  desktopAvatarToolPressState = {
    toolId: desktopAvatarToolState.toolId,
    startX: clientX,
    startY: clientY,
    avatarRangeHit: avatarRangeHit,
    moved: false,
  };
  if (desktopAvatarToolState.toolId === 'fist') {
    desktopAvatarToolAvatarRangeVariants.fist = 'secondary';
    desktopAvatarToolOutsideRangeVariants.fist = 'secondary';
  }
  applyDesktopAvatarToolNativeCursor();
}

function handleDesktopAvatarToolPointerMove(event) {
  if (!desktopAvatarToolState.active || !desktopAvatarToolState.tool) return;
  if (event && event.isTrusted === false) return;
  updateDesktopAvatarToolCursorFromPoint({
    x: event.clientX,
    y: event.clientY,
    screenX: event.screenX,
    screenY: event.screenY,
    overChatWindow: event.overChatWindow === true,
  });
}

function handleDesktopAvatarToolPointerUp(event) {
  if (!desktopAvatarToolState.active) {
    desktopAvatarToolPressState = null;
    return;
  }

  if (desktopAvatarToolPressState) {
    var pressState = desktopAvatarToolPressState;
    desktopAvatarToolPressState = null;
    if (!pressState.moved && pressState.toolId === desktopAvatarToolState.toolId) {
      var endX = event && Number.isFinite(Number(event.clientX)) ? Number(event.clientX) : (desktopAvatarToolRangeState.x || pressState.startX);
      var endY = event && Number.isFinite(Number(event.clientY)) ? Number(event.clientY) : (desktopAvatarToolRangeState.y || pressState.startY);
      var releaseOverCompactZone = isPointWithinDesktopAvatarToolCompactZone(endX, endY);
      var releaseAvatarRangeHit = releaseOverCompactZone ? null : getDesktopAvatarRangeHit(endX, endY);
      completeDesktopAvatarToolClick(
        pressState.toolId,
        releaseAvatarRangeHit || pressState.avatarRangeHit,
        endX,
        endY
      );
    }
  }

  if (desktopAvatarToolState.toolId === 'fist') {
    desktopAvatarToolAvatarRangeVariants.fist = 'primary';
    desktopAvatarToolOutsideRangeVariants.fist = 'primary';
  }

  if (event && Number.isFinite(Number(event.clientX)) && Number.isFinite(Number(event.clientY))) {
    updateDesktopAvatarToolCursorFromPoint({
      x: event.clientX,
      y: event.clientY,
      screenX: event.screenX,
      screenY: event.screenY,
      overChatWindow: event.overChatWindow === true,
    });
  } else if (desktopAvatarToolRangeState.withinAvatarRange && !desktopAvatarToolRangeState.overCompactZone) {
    applyDesktopAvatarToolNativeCursor();
  } else {
    clearDesktopAvatarToolNativeCursor();
  }
}

function handleDesktopAvatarToolPointerCancel() {
  desktopAvatarToolPressState = null;
  if (desktopAvatarToolState.toolId === 'fist') {
    desktopAvatarToolAvatarRangeVariants.fist = 'primary';
    desktopAvatarToolOutsideRangeVariants.fist = 'primary';
  }
  if (desktopAvatarToolRangeState.withinAvatarRange && !desktopAvatarToolRangeState.overCompactZone) {
    applyDesktopAvatarToolNativeCursor();
  } else {
    clearDesktopAvatarToolNativeCursor();
  }
}

ipcRenderer.on(CHAT_ACTION_CHANNELS.AVATAR_TOOL_STATE, function(_event, payload) {
  setDesktopAvatarToolState(payload);
});

ipcRenderer.on(CHAT_ACTION_CHANNELS.AVATAR_TOOL_POINTER, function(_event, payload) {
  handleDesktopAvatarToolForwardedPointer(payload);
});

window.addEventListener('pointerdown', handleDesktopAvatarToolPointerDown, true);
window.addEventListener('pointermove', handleDesktopAvatarToolPointerMove, { passive: true, capture: true });
window.addEventListener('pointerup', handleDesktopAvatarToolPointerUp, true);
window.addEventListener('pointercancel', handleDesktopAvatarToolPointerCancel, true);
window.addEventListener('blur', handleDesktopAvatarToolPointerCancel);

// setIgnoreMouseEvents 节流：减少切换频率，缓解 DWM 视频黑屏
// - 取消穿透（进入模型）→ 立即执行（保证点击响应）
// - 开启穿透（离开模型）→ 150ms 节流
//
// ===== 已尝试但未能解决 DWM 黑屏的方案（记录供后续参考）=====
// 1. 纯 forward 模式 setIgnoreMouseEvents(true, {forward:true})：
//    DWM 不重建，但不会转发 mousedown/click，因此只能用于非模型区的被动 hover/cursor 跟踪；
//    模型交互仍必须在命中区切回 ignore=false。
// 2. 双向延迟（取消穿透也延迟 30ms/80ms）：
//    快速掠过不触发切换，但快速进入判定区（只进不出）仍黑屏
// 3. 基于鼠标速度的智能延迟（速度>阈值时延迟取消穿透）：
//    同上，问题不在进出切换而在单次 setIgnoreMouseEvents(false) 本身
// 根因：Windows DWM 对 setIgnoreMouseEvents(false) 的处理会触发
//       DirectComposition overlay 重建，与鼠标移动速度相关（快速时来不及平滑处理）
//       这是 Chromium/Electron 层面的限制，无法在 JS 侧完全解决

function setIgnoreState(ignore, immediate) {
  if (_yuiGuidePluginDashboardSkipBypassActive && ignore === true) return;
  if (_transitionFrozen) return;
  // 鼠标持续停留在交互元素上时，重复收到 ignore=false：
  // 即使状态未变，也必须取消 pending 的 ignore=true 定时器，
  // 否则旧定时器到期会强制切到穿透 → cursor 闪成箭头再切回 → 闪烁。
  if (!ignore && _pendingTimeout) {
    clearTimeout(_pendingTimeout);
    _pendingTimeout = null;
  }
  if (lastIgnoreState === ignore) return;

  if (immediate) {
    if (_pendingTimeout) {
      clearTimeout(_pendingTimeout);
      _pendingTimeout = null;
    }
    ipcRenderer.send('set-ignore-mouse-events', ignore);
    lastIgnoreState = ignore;
    _lastSwitchTime = Date.now();
    return;
  }

  // 取消穿透 → 立即执行
  if (ignore === false) {
    if (_pendingTimeout) { clearTimeout(_pendingTimeout); _pendingTimeout = null; }
    ipcRenderer.send('set-ignore-mouse-events', false);
    lastIgnoreState = false;
    _lastSwitchTime = Date.now();
    return;
  }

  // 开启穿透 → 节流
  var now = Date.now();
  var elapsed = now - _lastSwitchTime;
  if (elapsed < _MIN_SWITCH_INTERVAL) {
    if (!_pendingTimeout) {
      _pendingTimeout = setTimeout(function() {
        _pendingTimeout = null;
        if (lastIgnoreState !== true) {
          ipcRenderer.send('set-ignore-mouse-events', true);
          lastIgnoreState = true;
          _lastSwitchTime = Date.now();
        }
      }, _MIN_SWITCH_INTERVAL - elapsed);
    }
    return;
  }
  ipcRenderer.send('set-ignore-mouse-events', true);
  lastIgnoreState = true;
  _lastSwitchTime = now;
}

function freezeMouseThrough(durationMs) {
  _transitionFrozen = true;
  if (_frozenTimer) clearTimeout(_frozenTimer);
  _frozenTimer = setTimeout(() => { _transitionFrozen = false; _frozenTimer = null; }, durationMs);
}

// 显式解冻（用于 drag/resize 结束后立即恢复穿透切换，
// 不必等 freezeMouseThrough 预设的超时兜底）
function unfreezeMouseThrough() {
  _transitionFrozen = false;
  if (_frozenTimer) { clearTimeout(_frozenTimer); _frozenTimer = null; }
}

async function syncMouseThroughStateWithCursor() {
  try {
    var point = await ipcRenderer.invoke('get-cursor-point');
    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') return;
    if (isPointWithinVisibleTutorialSkipButton(point.x, point.y)) {
      setIgnoreState(false, true);
      return;
    }
    if (point.overChatWindow === true) {
      setIgnoreState(true, true);
      return;
    }
    handleMousePosition(point.x, point.y);
  } catch (e) {}
}

function resetYuiGuidePetInputState(reason) {
  var resetGeneration = ++_yuiGuidePetInputResetGeneration;
  clearYuiGuidePetInputResetTimers();
  _yuiGuidePluginDashboardSkipBypassActive = false;
  _yuiGuideTutorialInputBypassActive = true;
  scheduleYuiGuideTutorialInputBypassExpiry();
  unfreezeMouseThrough();
  if (_pendingTimeout) {
    clearTimeout(_pendingTimeout);
    _pendingTimeout = null;
  }

  try {
    if (document.body) {
      document.body.classList.remove(
        'yui-taking-over',
        'yui-guide-home-ui-suppressed',
        'yui-guide-home-driver-hidden'
      );
    }
  } catch (_) {}

  resetModelDraggingState(reason || 'yui-guide-ended');
  resetDesktopAvatarToolRangeState();
  desktopAvatarToolPressState = null;
  clearDesktopAvatarToolNativeCursor();
  clearDesktopAvatarToolBoundsCache();
  refreshPetInputRegionsSoon();
  schedulePetInputRegionReport(0, true, true);
  forceWaylandPetShapeRefreshSoon();

  setIgnoreState(true, true);
  [0, 50, 160, 320, 700].forEach(function(delay) {
    var timer = setTimeout(function() {
      if (resetGeneration !== _yuiGuidePetInputResetGeneration) return;
      lastIgnoreState = null;
      refreshPetInputRegionsSoon();
      schedulePetInputRegionReport(0, true, true);
      forceWaylandPetShapeRefreshSoon();
      syncMouseThroughStateWithCursor();
    }, delay);
    _yuiGuidePetInputResetTimers.push(timer);
  });
}

function forceWaylandPetShapeRefreshSoon() {
  try {
    if (typeof _forceWaylandPetShapeRefresh === 'function') {
      _forceWaylandPetShapeRefresh();
    }
  } catch (_) {}
}

function clearYuiGuidePetInputResetTimers() {
  for (var i = 0; i < _yuiGuidePetInputResetTimers.length; i += 1) {
    clearTimeout(_yuiGuidePetInputResetTimers[i]);
  }
  _yuiGuidePetInputResetTimers = [];
}

function scheduleYuiGuideTutorialInputBypassExpiry(delayMs) {
  if (_yuiGuideTutorialInputBypassExpiryTimer) {
    clearTimeout(_yuiGuideTutorialInputBypassExpiryTimer);
  }
  // The bypass only covers teardown after the tutorial overlay is removed.
  _yuiGuideTutorialInputBypassExpiryTimer = setTimeout(function() {
    _yuiGuideTutorialInputBypassExpiryTimer = null;
    if (hasVisibleYuiGuideResidualOverlaySurface()) {
      setIgnoreState(true, true);
      scheduleYuiGuideTutorialInputBypassExpiry(_YUI_GUIDE_INPUT_BYPASS_RECHECK_MS);
      return;
    }
    restoreYuiGuidePetInputTakeover();
  }, Number.isFinite(Number(delayMs)) ? Math.max(0, Number(delayMs)) : _YUI_GUIDE_INPUT_BYPASS_EXPIRY_MS);
}

function restoreYuiGuidePetInputTakeover() {
  _yuiGuidePetInputResetGeneration += 1;
  clearYuiGuidePetInputResetTimers();
  if (_yuiGuideTutorialInputBypassExpiryTimer) {
    clearTimeout(_yuiGuideTutorialInputBypassExpiryTimer);
    _yuiGuideTutorialInputBypassExpiryTimer = null;
  }
  _yuiGuideTutorialInputBypassActive = false;
  refreshPetInputRegionsSoon();
  schedulePetInputRegionReport(0, true, true);
  forceWaylandPetShapeRefreshSoon();
  lastIgnoreState = null;
  syncMouseThroughStateWithCursor();
}

function refreshYuiGuidePetInputAfterTutorialModelRestore() {
  _yuiGuidePetInputResetGeneration += 1;
  clearYuiGuidePetInputResetTimers();
  if (_yuiGuideTutorialInputBypassExpiryTimer) {
    clearTimeout(_yuiGuideTutorialInputBypassExpiryTimer);
    _yuiGuideTutorialInputBypassExpiryTimer = null;
  }
  _yuiGuideTutorialInputBypassActive = false;
  lastIgnoreState = null;
  refreshPetInputRegionsSoon();
  schedulePetInputRegionReport(0, true, true);
  forceWaylandPetShapeRefreshSoon();
  syncMouseThroughStateWithCursor();
}

function getYuiGuideTutorialLifecycleGeneration(detail) {
  var generation = detail && (detail.lifecycleGeneration || detail.tutorialGeneration || detail.generation);
  var number = Number(generation);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

function handleYuiGuideTutorialOverlayRelay(payload) {
  var detail = payload && typeof payload === 'object' ? payload : {};
  var relayGeneration = getYuiGuideTutorialLifecycleGeneration(detail);
  if (detail.action === 'yui_guide_tutorial_lifecycle_ended') {
    if (_yuiGuideTutorialLifecycleGeneration && relayGeneration !== _yuiGuideTutorialLifecycleGeneration) {
      if (!(relayGeneration === 0 && _yuiGuideTutorialLifecycleGenerationlessActive)) return;
    }
    _yuiGuideTutorialLifecycleGenerationlessActive = false;
    resetYuiGuidePetInputState(detail.reason || 'yui-guide-ended');
  } else if (detail.action === 'yui_guide_tutorial_input_restored') {
    if (_yuiGuideTutorialLifecycleGeneration && relayGeneration !== _yuiGuideTutorialLifecycleGeneration) {
      if (!(relayGeneration === 0 && _yuiGuideTutorialLifecycleGenerationlessActive)) return;
    }
    refreshYuiGuidePetInputAfterTutorialModelRestore();
  } else if (detail.action === 'yui_guide_tutorial_lifecycle_started' ||
      detail.action === 'yui_guide_tutorial_started' ||
      detail.action === 'avatar_floating_guide_started') {
    if (relayGeneration && relayGeneration < _yuiGuideTutorialLifecycleGeneration) return;
    _yuiGuideTutorialLifecycleGeneration = relayGeneration || (_yuiGuideTutorialLifecycleGeneration + 1);
    _yuiGuideTutorialLifecycleGenerationlessActive = relayGeneration === 0;
    restoreYuiGuidePetInputTakeover();
  }
}

function handleYuiGuideTutorialStartedEvent(event) {
  var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
  var relayGeneration = getYuiGuideTutorialLifecycleGeneration(detail);
  if (relayGeneration && relayGeneration < _yuiGuideTutorialLifecycleGeneration) return;
  _yuiGuideTutorialLifecycleGeneration = relayGeneration || (_yuiGuideTutorialLifecycleGeneration + 1);
  _yuiGuideTutorialLifecycleGenerationlessActive = relayGeneration === 0;
  restoreYuiGuidePetInputTakeover();
}

function isTrustedYuiGuideTutorialOverlayRelayOrigin(origin) {
  if (typeof origin !== 'string' || !origin) return false;
  if (origin === window.location.origin || origin === 'file://') return true;
  try {
    var parsed = new URL(origin);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:') &&
      (parsed.hostname === 'localhost' ||
        parsed.hostname === '127.0.0.1' ||
        parsed.hostname === '::1' ||
        parsed.hostname === '[::1]');
  } catch (_) {
    return false;
  }
}

function isTrustedYuiGuideTutorialOverlayRelayMessage(event) {
  return !!(event && isTrustedYuiGuideTutorialOverlayRelayOrigin(event.origin));
}

function startMousePoller() {
  setInterval(async () => {
    if (_mousePollerInFlight) return;
    if (isBlankPage()) return;
    if (!isHomePage()) return;
    // 拖拽期间跳过整个轮询：避免 IPC 往返 + 合成事件 + elementFromPoint 开销
    if (window.DragHelpers && window.DragHelpers.isDragging) return;
    var modelDraggingAtPollStart = isModelDragging();
    var returnBallDraggingAtPollStart = isNekoIdleReturnBallDragActiveForInputRegion();
    var draggingAtPollStart = modelDraggingAtPollStart || returnBallDraggingAtPollStart;
    if (modelDraggingAtPollStart && !_isLinuxX11Preload && !recoverStaleModelDrag('poller-timeout')) return;
    // popup 冻结期间跳过轮询：省掉 IPC 开销，让主进程空闲处理弹窗渲染
    if (_transitionFrozen) return;
    _mousePollerInFlight = true;
    try {
      var point = await ipcRenderer.invoke('get-cursor-point', {
        includeButtons: _isLinuxX11Preload && draggingAtPollStart,
      });
      if (point && typeof point.x === 'number' && typeof point.y === 'number') {
        if (_isLinuxX11Preload && draggingAtPollStart) {
          var pointerButtons = Number.isFinite(Number(point.buttons)) ? Number(point.buttons) : undefined;
          if (pointerButtons === 0) _x11ModelPointerButtonsDown = false;
          else if (pointerButtons > 0) _x11ModelPointerButtonsDown = true;
          if (modelDraggingAtPollStart && !recoverStaleModelDrag('poller-x11-buttons', pointerButtons)) return;
          if (returnBallDraggingAtPollStart && pointerButtons === 0) {
            dispatchSyntheticPointerRelease(point);
          }
        }
        var overChatWindow = point.overChatWindow === true;
        if (isCurrentModelInGoodbyeMode()) {
          if (overChatWindow) {
            setIgnoreState(true, true);
            if (_isLinuxX11Preload && returnBallDraggingAtPollStart) {
              forwardPolledCursorFollow(point);
            }
          } else {
            handleMousePosition(point.x, point.y);
          }
          return;
        }
        if (desktopAvatarToolState.active) {
          updateDesktopAvatarToolCursorFromPoint(point);
        }
        var isOutside = point.x < 0 || point.y < 0 || point.x > window.innerWidth || point.y > window.innerHeight;
        if (!isOutside && isPointWithinVisibleTutorialSkipButton(point.x, point.y)) {
          setIgnoreState(false, true);
          forwardPolledCursorFollow(point, { syntheticMove: false });
          return;
        }
        if (_isLinuxX11Preload && overChatWindow) {
          setIgnoreState(true, true);
          forwardPolledCursorFollow(point);
          return;
        }
        if (_isLinuxX11Preload) {
          if (isOutside) {
            setIgnoreState(true, true);
            forwardPolledCursorFollow(point);
          } else if (isPointInInputRegions(point, _x11LastInputRegions)) {
            handleMousePosition(point.x, point.y);
            var nativeEventAge = Date.now() - _x11LastNativePointerActivityAt;
            if (!_x11LastNativePointerActivityAt || nativeEventAge > _LINUX_X11_SYNTHETIC_MOVE_MS) {
              forwardPolledCursorFollow(point);
            } else {
              forwardPolledCursorFollow(point, { syntheticMove: false });
            }
          } else {
            setIgnoreState(true, true);
            forwardPolledCursorFollow(point, { syntheticMove: false });
          }
          return;
        }

        if (!isOutside && !overChatWindow && !_isLinuxX11Preload && lastIgnoreState === true) {
          handleMousePosition(point.x, point.y);
        }

        if (!overChatWindow && (_isLinuxX11Preload || lastIgnoreState === true || isOutside)) {
          forwardPolledCursorFollow(point);
        } else {
          forwardPolledCursorFollow(point, { syntheticMove: false });
        }
      }
    } catch (e) {
    } finally {
      _mousePollerInFlight = false;
    }
  }, _isLinuxX11Preload ? _LINUX_X11_MOUSE_POLL_MS : 50);
}

// ===== WebSocket Hook 桥接（零侵入：不改 xiao8 的任何 JS）=====
// 拦截 WebSocket 的 onmessage，解析后端消息并通过 IPC 转发给其他窗口
// 同时拦截 send，让其他窗口可以通过 IPC 向后端发消息

(function setupWebSocketHook() {
  const _OrigWebSocket = window.WebSocket;
  let _activeWs = null; // 当前活跃的 WebSocket 实例
  let _wsGeneration = 0;
  let _wsSessionEpoch = Date.now();
  try {
    var nextEpoch = ipcRenderer.sendSync(WS_PROXY_CHANNELS.NEXT_SESSION_EPOCH);
    if (typeof nextEpoch === 'number' && Number.isFinite(nextEpoch)) {
      _wsSessionEpoch = nextEpoch;
    }
  } catch (_) {}

  // --- 监听 Chat 窗口发来的 send 数据，注入到真实 WebSocket ---
  // 必须在 IIFE 顶层只注册一次：若放进 window.WebSocket wrapper 内，
  // 每次 new WebSocket（例如切换猫娘触发重连）都会追加一个 listener，
  // 所有 listener 共享 _activeWs 闭包，一条 IPC send 会被重复执行 N 次。
  ipcRenderer.on(WS_PROXY_CHANNELS.RAW_SEND, (event, rawData) => {
    if (!_activeWs || _activeWs.readyState !== _OrigWebSocket.OPEN) {
      // Chat 侧 WSProxy 已按 readyState 拦截绝大多数，这里能进来的是
      // Pet CLOSED → Chat 收到 CLOSED IPC 之间的几毫秒竞态，打个 warn 就够
      console.warn('[Pet] RAW_SEND dropped: ws not OPEN, state=', _activeWs && _activeWs.readyState);
      return;
    }
    try {
      _activeWs.send(rawData);
    } catch (e) {
      // readyState 检查到实际 send 之间可能已关闭，避免未捕获异常冒泡到 IPC 回调
      console.warn('[Pet] WS send failed:', e);
    }
  });

  window.WebSocket = function (...args) {
    const ws = new _OrigWebSocket(...args);
    const wsGeneration = ++_wsGeneration;
    _activeWs = ws;
    ipcRenderer.send(WS_PROXY_CHANNELS.CONNECTING, { sessionEpoch: _wsSessionEpoch, generation: wsGeneration });

    // --- 连接就绪时通知 Chat 窗口 ---
    ws.addEventListener('open', function () {
      if (_activeWs === ws) {
        ipcRenderer.send(WS_PROXY_CHANNELS.READY, { sessionEpoch: _wsSessionEpoch, generation: wsGeneration });
      }
    });

    // --- 连接关闭时通知 Chat 窗口（支持重连感知）---
    // 只有仍然是"当前活跃"的 WS close 才广播 CLOSED：
    // 切换档案时老 WS 的 close 事件可能在新 WS 已替换 _activeWs 之后才异步触发，
    // 此时这条 CLOSED 属于上一代连接生命周期的余波，广播出去会在 Chat 的新代理上
    // 误触发 close→onclose→排队 auto-reconnect → 3s 后僵尸代理，直接复现
    // "Start failed: WebSocket not connected"。
    ws.addEventListener('close', function (event) {
      var wasActive = (_activeWs === ws);
      if (wasActive) {
        _activeWs = null;
        ipcRenderer.send(WS_PROXY_CHANNELS.CLOSED, { code: event.code, reason: event.reason, sessionEpoch: _wsSessionEpoch, generation: wsGeneration });
      } else {
        console.log('[Pet] suppressed stale CLOSED for replaced ws, code:', event.code);
      }
    });

    // --- 用 addEventListener 无条件注册转发监听器，不依赖 onmessage setter ---
    _OrigWebSocket.prototype.addEventListener.call(ws, 'message', function (event) {
      try {
        if (typeof event.data === 'string') {
          const msg = JSON.parse(event.data);
          // 音频相关消息不转发给 Chat（音频在 Pet 窗口处理，不走 IPC）
          var skipRaw = msg.type === 'audio_chunk' || msg.type === 'cozy_audio' || msg.type === 'user_activity';
          if (!skipRaw) {
            console.log('[Pet] Forwarding WS message to chat, type:', msg.type);
            ipcRenderer.send(WS_PROXY_CHANNELS.RAW_MESSAGE, event.data);
          }
          // 结构化转发（给 Subtitle 等窗口）
          _forwardToIPC(msg);
        }
      } catch (e) { /* ignore */ }
    });
    console.log('[Pet] WebSocket message forwarding listener registered');

    // --- 保留 onmessage 属性代理，让原有代码正常运作 ---
    let _userOnMessage = null;
    Object.defineProperty(ws, 'onmessage', {
      get() { return _userOnMessage; },
      set(fn) { _userOnMessage = fn; }
    });
    // onmessage 仍需手动调度，因为 defineProperty 覆盖了 IDL attribute
    _OrigWebSocket.prototype.addEventListener.call(ws, 'message', function (event) {
      if (typeof _userOnMessage === 'function') {
        try { _userOnMessage(event); } catch (e) { console.error('[Pet] onmessage handler error:', e); }
      }
    });

    return ws;
  };
  // Chat 窗口 preload 加载后请求重新检查 WS 状态
  // 解决竞态：WS READY 可能在 Chat preload 注册 IPC 监听前已发送并丢失
  ipcRenderer.on('neko:ws-trigger-ready-recheck', () => {
    if (_activeWs && _activeWs.readyState === _OrigWebSocket.OPEN) {
      ipcRenderer.send(WS_PROXY_CHANNELS.READY, { sessionEpoch: _wsSessionEpoch, generation: _wsGeneration });
    }
  });

  // 保留原型链，让 instanceof 检查等正常工作
  window.WebSocket.prototype = _OrigWebSocket.prototype;
  window.WebSocket.CONNECTING = _OrigWebSocket.CONNECTING;
  window.WebSocket.OPEN = _OrigWebSocket.OPEN;
  window.WebSocket.CLOSING = _OrigWebSocket.CLOSING;
  window.WebSocket.CLOSED = _OrigWebSocket.CLOSED;

  // 解析后端消息并分发到对应 IPC 通道
  function _forwardToIPC(msg) {
    if (!msg || !msg.type) return;

    switch (msg.type) {
      case 'gemini_response':
        ipcRenderer.send(WS_CHANNELS.CHAT_MESSAGE, {
          text: msg.text, isNewMessage: msg.isNewMessage || false
        });
        break;
      case 'user_transcript':
        ipcRenderer.send(WS_CHANNELS.TRANSCRIPT, {
          transcript: msg.text, is_final: true
        });
        break;
      case 'status':
        var statusCode = null;
        try { var p = JSON.parse(msg.message); if (p && p.code) statusCode = p.code; } catch (_) {}
        ipcRenderer.send(WS_CHANNELS.STATUS, {
          code: statusCode || 'UNKNOWN', message: msg.message
        });
        break;
      case 'agent_status_update':
      case 'agent_task_update':
        // 延迟一点让 Pet 窗口的原有逻辑先处理完 _agentTaskMap
        setTimeout(function () {
          var tasks = window._agentTaskMap ? Array.from(window._agentTaskMap.values()) : [];
          ipcRenderer.send(WS_CHANNELS.AGENT_UPDATE, {
            tasks: tasks,
            running_count: tasks.filter(function (t) { return t.status === 'running'; }).length,
            queued_count: tasks.filter(function (t) { return t.status === 'queued'; }).length,
          });
        }, 50);
        break;
    }
  }

  // --- 反向通道：其他窗口通过 IPC → 注入到 WebSocket ---

  // 辅助：发送 stream_data 到 WebSocket（包含可选图片）
  function _sendStreamData(text, images) {
    var payload = { action: 'stream_data', data: text, input_type: 'text' };
    if (images && images.length > 0) {
      payload.images = images;
    }
    _activeWs.send(JSON.stringify(payload));
  }

  // Chat → Pet: 发送文本（可附带图片）
  ipcRenderer.on(CHAT_CHANNELS.SEND_TEXT, (event, data) => {
    console.log('[Pet] SEND_TEXT received, wsState:', _activeWs && _activeWs.readyState, 'data:', data);
    // 用户发起新对话，清除字幕窗口
    ipcRenderer.send(WS_CHANNELS.TRANSCRIPT, { transcript: '', is_final: true, translated: true });
    if (!_activeWs || _activeWs.readyState !== _OrigWebSocket.OPEN) {
      console.warn('[Pet] SEND_TEXT ignored: WebSocket not open');
      return;
    }
    var text = (data && data.text) || '';
    var images = (data && data.images) || []; // dataUrl 数组
    if (!text.trim() && images.length === 0) return;

    // 无文本但有图片时提供默认提示
    var sendText = text.trim() || (images.length > 0 ? '[图片]' : '');

    // 如果没有活跃文本会话，先开一个再发（appState 不存在时也需要先开会话）
    var S = window.appState;
    if (!S || !S.isTextSessionActive) {
      console.log('[Pet] Starting text session before sending, waiting for session_started...');
      var _pendingText = sendText;
      var _pendingImages = images;
      var _sessionHandler = null;
      var _sessionTimeout = null;

      _sessionHandler = _OrigWebSocket.prototype.addEventListener.call(_activeWs, 'message', function _onSessionStarted(evt) {
        try {
          var msg = JSON.parse(evt.data);
          if (msg.type === 'session_started') {
            // 移除监听器
            _OrigWebSocket.prototype.removeEventListener.call(_activeWs, 'message', _onSessionStarted);
            if (_sessionTimeout) { clearTimeout(_sessionTimeout); _sessionTimeout = null; }
            // 标记会话活跃
            if (window.appState) window.appState.isTextSessionActive = true;
            console.log('[Pet] session_started received, now sending stream_data:', _pendingText);
            _sendStreamData(_pendingText, _pendingImages);
          }
        } catch (e) { /* ignore */ }
      });

      // 超时保护：15秒后放弃
      _sessionTimeout = setTimeout(function () {
        console.warn('[Pet] session_started timeout after 15s, sending stream_data anyway');
        if (_activeWs && _activeWs.readyState === _OrigWebSocket.OPEN) {
          _sendStreamData(_pendingText, _pendingImages);
        }
      }, 15000);

      _activeWs.send(JSON.stringify({ action: 'start_session', input_type: 'text', new_session: false }));
    } else {
      console.log('[Pet] Sending stream_data directly (session active):', sendText);
      _sendStreamData(sendText, images);
    }
  });

  // Chat → Pet: 音频数据
  ipcRenderer.on(CHAT_CHANNELS.SEND_AUDIO, (event, data) => {
    if (!_activeWs || _activeWs.readyState !== _OrigWebSocket.OPEN) return;
    // 用户发起新对话（语音），清除字幕窗口
    ipcRenderer.send(WS_CHANNELS.TRANSCRIPT, { transcript: '', is_final: true, translated: true });
    if (data && data.data) {
      _activeWs.send(JSON.stringify({ action: 'stream_data', data: data.data, input_type: 'audio' }));
    }
  });

  // Chat → Pet: 开始会话
  ipcRenderer.on(CHAT_CHANNELS.START_SESSION, (event, data) => {
    if (!_activeWs || _activeWs.readyState !== _OrigWebSocket.OPEN) return;
    _activeWs.send(JSON.stringify({
      action: 'start_session',
      input_type: (data && data.input_type) || 'text',
      new_session: !!(data && data.new_session)
    }));
  });

  // Chat → Pet: 结束会话
  ipcRenderer.on(CHAT_CHANNELS.END_SESSION, () => {
    if (!_activeWs || _activeWs.readyState !== _OrigWebSocket.OPEN) return;
    _activeWs.send(JSON.stringify({ action: 'end_session' }));
  });

  // Chat → Pet: 截图（立即发送到 WS，旧通道保留兼容）
  ipcRenderer.on(CHAT_CHANNELS.SCREENSHOT, () => {
    (async function () {
      try {
        var dataUrl = typeof window.captureProactiveChatScreenshot === 'function'
          ? await window.captureProactiveChatScreenshot() : null;
        if (dataUrl && _activeWs && _activeWs.readyState === _OrigWebSocket.OPEN) {
          _activeWs.send(JSON.stringify({ action: 'screenshot_response', data: dataUrl }));
          ipcRenderer.send(WS_CHANNELS.CHAT_MESSAGE, { text: '📸 [截图已发送]', isNewMessage: true });
        }
      } catch (e) { console.warn('[WS Hook] Screenshot failed:', e); }
    })();
  });

  // Chat → Pet: 请求截图（捕获后返回 dataUrl 给 Chat，不直接发送到 WS）
  ipcRenderer.on(CHAT_CHANNELS.REQUEST_SCREENSHOT, () => {
    (async function () {
      try {
        var result = null;
        if (typeof window.captureScreenshotDataUrl === 'function') {
          result = await window.captureScreenshotDataUrl();
        } else if (typeof window.captureProactiveChatScreenshot === 'function') {
          result = { dataUrl: await window.captureProactiveChatScreenshot() };
        }
        var dataUrl = (result && result.dataUrl) ? result.dataUrl : null;
        ipcRenderer.send(CHAT_CHANNELS.SCREENSHOT_RESULT, { dataUrl: dataUrl });
      } catch (e) {
        if (e && e.message === 'SCREENSHOT_BUSY') {
          return;
        }
        console.warn('[WS Hook] Screenshot capture failed:', e);
        ipcRenderer.send(CHAT_CHANNELS.SCREENSHOT_RESULT, { dataUrl: null, error: e && e.message });
      }
    })();
  });

  // Chat → Pet: 当前头像预览（直接捕获画布，回传 dataUrl 给 Chat）
  ipcRenderer.on(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW, () => {
    (async function () {
      try {
        if (!window.avatarPortrait || typeof window.avatarPortrait.capture !== 'function') {
          ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT, { error: 'Avatar capture not available' });
          return;
        }
        var result = await window.avatarPortrait.capture({
          width: 320, height: 320, padding: 0.035,
          shape: 'rounded', radius: 40,
          background: 'rgba(255, 255, 255, 0.96)',
          includeDataUrl: true
        });
        var modelType = (result && result.modelType) || (window.lanlan_config && window.lanlan_config.model_type) || 'live2d';
        ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT, {
          dataUrl: result && result.dataUrl ? result.dataUrl : null,
          modelType: modelType
        });
      } catch (e) {
        console.warn('[WS Hook] Avatar capture failed:', e);
        ipcRenderer.send(CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT, { error: e && e.message ? e.message : String(e) });
      }
    })();
  });

  let chatConfigResultPending = false;
  function sendChatConfigResult() {
    chatConfigResultPending = false;
    var cfg = window.lanlan_config || {};
    ipcRenderer.send(CHAT_ACTION_CHANNELS.CONFIG_RESULT, {
      lanlan_name: cfg.lanlan_name || '',
      model_type: cfg.model_type || 'live2d',
      live3d_sub_type: cfg.live3d_sub_type || '',
      master_name: window.master_name || cfg.master_name || '',
      master_profile_name: window.master_profile_name || cfg.master_profile_name || '',
      master_nickname: window.master_nickname || cfg.master_nickname || '',
      master_display_name: window.master_display_name || cfg.master_display_name || '',
    });
  }

  // Chat → Pet: 配置请求（猫娘名字、主人信息）
  ipcRenderer.on(CHAT_ACTION_CHANNELS.CONFIG_REQUEST, () => {
    var cfg = window.lanlan_config || {};
    if (cfg.lanlan_name) {
      sendChatConfigResult();
      return;
    }
    if (chatConfigResultPending) {
      return;
    }
    chatConfigResultPending = true;
    if (window.pageConfigReady && typeof window.pageConfigReady.then === 'function') {
      window.pageConfigReady.then(sendChatConfigResult, sendChatConfigResult);
      return;
    }
    setTimeout(sendChatConfigResult, 300);
  });

  // Chat → Pet: 点歌台切换 → 转发给主进程打开独立窗口
  ipcRenderer.on(CHAT_ACTION_CHANNELS.JUKEBOX_TOGGLE, () => {
    ipcRenderer.send(JUKEBOX_CHANNELS.TOGGLE);
  });

  // Jukebox 独立窗口 → Pet: VMD/VRMA 动画控制（根据模型类型分发）
  ipcRenderer.on(JUKEBOX_CHANNELS.VMD_PLAY, (_event, data) => {
    if (!window.Jukebox || !data || !data.vmdPath) return;
    var modelType = typeof window.Jukebox.getModelType === 'function'
      ? window.Jukebox.getModelType() : 'live2d';
    if (modelType === 'vrm' && typeof window.Jukebox.playVRMA === 'function') {
      window.Jukebox.playVRMA(data.vmdPath);
    } else if (typeof window.Jukebox.playVMD === 'function') {
      window.Jukebox.playVMD(data.vmdPath);
    }
  });
  ipcRenderer.on(JUKEBOX_CHANNELS.VMD_STOP, (_event, data) => {
    if (window.Jukebox && typeof window.Jukebox.stopVMD === 'function') {
      window.Jukebox.stopVMD(data && data.skipIdleRestore);
    }
  });
  ipcRenderer.on(JUKEBOX_CHANNELS.VMD_PAUSE, () => {
    if (window.Jukebox && typeof window.Jukebox.togglePause === 'function') {
      // 仅在播放中时暂停
      if (window.Jukebox.State && window.Jukebox.State.isVMDPlaying && !window.Jukebox.State.isPaused) {
        window.Jukebox.togglePause();
      }
    }
  });
  ipcRenderer.on(JUKEBOX_CHANNELS.VMD_RESUME, () => {
    if (window.Jukebox && typeof window.Jukebox.togglePause === 'function') {
      // 仅在暂停时恢复
      if (window.Jukebox.State && window.Jukebox.State.isPaused) {
        window.Jukebox.togglePause();
      }
    }
  });

  // AgentHUD → Pet: Agent 开关
  ipcRenderer.on(AGENT_CHANNELS.TOGGLE, (event, data) => {
    if (data && data.capability) {
      fetch('/api/agent/toggle_flag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ flag: data.capability, enabled: !!data.enabled })
      }).catch(function (e) { console.warn('[WS Hook] Agent toggle failed:', e); });
    }
  });

  console.log('[Preload-Pet] WebSocket hook 桥接已初始化');
})();

// ===== 多窗口模式标志 =====
// Pet 窗口在 Electron 中运行时，隐藏已拆到独立窗口的 UI 元素
// 手机端（纯浏览器）不加载 preload，因此不会注入此标志，元素正常显示
window.__NEKO_MULTI_WINDOW__ = true;
// Linux 透明全屏 pet 窗口在 shrink/setBounds 往返时会触发合成器黑屏/错帧；
// Windows 兼容模式也沿用禁用策略，回落到页面内 return-ball 拖拽。
window.__NEKO_DISABLE_NATIVE_RETURN_BALL_DRAG__ = _disableNativeReturnBallDrag;

// Jukebox 独立窗口开关（供 Jukebox.js 在 Electron 模式下调用）
window.__nekoJukeboxToggle = function() {
  ipcRenderer.send(JUKEBOX_CHANNELS.TOGGLE);
};

// DOMContentLoaded 后隐藏已拆出的元素
document.addEventListener('DOMContentLoaded', () => {
  const chatContainer = document.getElementById('chat-container');
  if (chatContainer) chatContainer.style.display = 'none';
  // React Chat overlay 也隐藏（Chat 已拆为独立 BrowserWindow）
  const reactChatOverlay = document.getElementById('react-chat-window-overlay');
  if (reactChatOverlay) reactChatOverlay.style.display = 'none';
  const subtitleDisplay = document.getElementById('subtitle-display');
  if (subtitleDisplay) subtitleDisplay.style.display = 'none';

  var lastSubtitleForwarded = {
    text: null,
    enabled: null,
    visible: null,
    language: null,
    locale: null,
    opacity: null,
    bounds: null,
    locked: null,
    interactionPassthrough: null,
    danmakuMode: null,
    fontSize: null,
    colorScheme: null
  };

  function normalizeSubtitlePanelBounds(bounds) {
    var width = Math.round(Number(bounds && bounds.width));
    var height = Math.round(Number(bounds && bounds.height));
    return {
      width: Number.isFinite(width) && width > 0 ? width : 600,
      height: Number.isFinite(height) && height > 0 ? height : 68
    };
  }

  function sameSubtitlePanelBounds(a, b) {
    if (!a && !b) return true;
    if (!a || !b) return false;
    return a.width === b.width && a.height === b.height;
  }

  function forwardSubtitleRenderState(detail) {
    var state = detail && detail.state ? detail.state : detail;
    if (!state) return;

    var enabled = !!state.subtitleEnabled;
    var visible = enabled && !!state.visible;
    var transcript = typeof state.text === 'string' ? state.text : '';
    var language = state.userLanguage || localStorage.getItem('userLanguage') || 'en';
    var locale = state.uiLocale || localStorage.getItem('i18nextLng') || 'en-US';
    var opacity = typeof state.subtitleOpacity === 'number' ? state.subtitleOpacity : 95;
    var bounds = normalizeSubtitlePanelBounds(state.subtitlePanelBounds);
    var locked = !!state.subtitlePanelLocked || state.subtitleInteractionPassthrough === true;
    var interactionPassthrough = locked;
    var danmakuMode = !!state.subtitleDanmakuMode;
    var fontSize = state.subtitleFontSize || 26;
    var colorScheme = state.subtitleColorScheme || 'default';

    if (window.nekoSubtitleWindow) {
      if (visible) {
        window.nekoSubtitleWindow.show();
      } else {
        window.nekoSubtitleWindow.hide();
      }
    }

    if (lastSubtitleForwarded.text !== transcript) {
      ipcRenderer.send(WS_CHANNELS.TRANSCRIPT, {
        transcript: transcript,
        is_final: true,
        translated: true
      });
      lastSubtitleForwarded.text = transcript;
    }

    if (lastSubtitleForwarded.enabled !== enabled ||
        lastSubtitleForwarded.visible !== visible ||
        lastSubtitleForwarded.language !== language ||
        lastSubtitleForwarded.locale !== locale ||
        lastSubtitleForwarded.opacity !== opacity ||
        !sameSubtitlePanelBounds(lastSubtitleForwarded.bounds, bounds) ||
        lastSubtitleForwarded.locked !== locked ||
        lastSubtitleForwarded.interactionPassthrough !== interactionPassthrough ||
        lastSubtitleForwarded.danmakuMode !== danmakuMode ||
        lastSubtitleForwarded.fontSize !== fontSize ||
        lastSubtitleForwarded.colorScheme !== colorScheme) {
      ipcRenderer.send(SUBTITLE_CHANNELS.STATE_SYNC, {
        enabled: enabled,
        visible: visible,
        language: language,
        locale: locale,
        opacity: opacity,
        bounds: bounds,
        locked: locked,
        interactionPassthrough: interactionPassthrough,
        danmakuMode: danmakuMode,
        fontSize: fontSize,
        colorScheme: colorScheme
      });
      lastSubtitleForwarded.enabled = enabled;
      lastSubtitleForwarded.visible = visible;
      lastSubtitleForwarded.language = language;
      lastSubtitleForwarded.locale = locale;
      lastSubtitleForwarded.opacity = opacity;
      lastSubtitleForwarded.bounds = bounds;
      lastSubtitleForwarded.locked = locked;
      lastSubtitleForwarded.interactionPassthrough = interactionPassthrough;
      lastSubtitleForwarded.danmakuMode = danmakuMode;
      lastSubtitleForwarded.fontSize = fontSize;
      lastSubtitleForwarded.colorScheme = colorScheme;
    }
  }

  window.__forwardSubtitleRenderStateToWindow = forwardSubtitleRenderState;
  window.addEventListener('neko-subtitle-render-state', function(event) {
    forwardSubtitleRenderState(event.detail);
  });

  if (window.nekoSubtitleShared && typeof window.nekoSubtitleShared.getRenderState === 'function') {
    forwardSubtitleRenderState(window.nekoSubtitleShared.getRenderState());
  }

  console.log('[Preload-Pet] 多窗口模式初始化完成');
});

// ===== Subtitle 按需控制 API =====
window.nekoSubtitleWindow = {
  show: () => ipcRenderer.send('neko:show-subtitle'),
  hide: () => ipcRenderer.send('neko:hide-subtitle'),
};

// ===== Subtitle 窗口设置变更（从 Subtitle 窗口转发过来）=====
function readSubtitleEnabledForWindowSync(subtitleShared) {
  if (subtitleShared && typeof subtitleShared.getSettings === 'function') {
    try {
      var subtitleSettings = subtitleShared.getSettings();
      if (subtitleSettings && typeof subtitleSettings.subtitleEnabled !== 'undefined') {
        return !!subtitleSettings.subtitleEnabled;
      }
    } catch (_) {}
  }
  if (window.appState && Object.prototype.hasOwnProperty.call(window.appState, 'subtitleEnabled')) {
    return !!window.appState.subtitleEnabled;
  }
  return localStorage.getItem('subtitleEnabled') === 'true';
}

function subtitleSettingsUpdateOptions(source, data) {
  return {
    source: source,
    persist: !(data && data.transient === true)
  };
}

ipcRenderer.on(SUBTITLE_CHANNELS.SETTINGS_CHANGE, (event, data) => {
  if (!data || !data.type) return;
  var bridge = window.subtitleBridge;
  var subtitleShared = window.nekoSubtitleShared;
  if (!bridge && !(subtitleShared && typeof subtitleShared.updateSettings === 'function')) return;

  if (data.type === 'toggle') {
    var nextEnabled = !!data.value;
    if (bridge && typeof bridge.setSubtitleEnabled === 'function') {
      bridge.setSubtitleEnabled(nextEnabled);
    } else if (subtitleShared && typeof subtitleShared.updateSettings === 'function') {
      subtitleShared.updateSettings({ subtitleEnabled: nextEnabled }, {
        source: 'subtitle-window-toggle'
      });
    }
  } else if (data.type === 'language') {
    if (bridge) {
      bridge.setUserLanguage(data.value);
    }
  } else if (data.type === 'opacity' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings(
      { subtitleOpacity: data.value },
      subtitleSettingsUpdateOptions('subtitle-window-opacity', data)
    );
  } else if (data.type === 'bounds' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings(
      { subtitlePanelBounds: data.value },
      subtitleSettingsUpdateOptions('subtitle-window-bounds', data)
    );
  } else if (data.type === 'lock' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings(
      {
        subtitlePanelLocked: !!data.value,
        subtitleInteractionPassthrough: !!data.value
      },
      subtitleSettingsUpdateOptions('subtitle-window-lock', data)
    );
  } else if (data.type === 'interactionPassthrough' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings(
      {
        subtitlePanelLocked: data.value !== false,
        subtitleInteractionPassthrough: data.value !== false
      },
      subtitleSettingsUpdateOptions('subtitle-window-passthrough', data)
    );
  } else if (data.type === 'danmakuMode' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings({ subtitleDanmakuMode: !!data.value }, {
      source: 'subtitle-window-danmaku-mode'
    });
  } else if (data.type === 'fontSize' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings({ subtitleFontSize: data.value }, {
      source: 'subtitle-window-font-size'
    });
  } else if (data.type === 'colorScheme' && subtitleShared && typeof subtitleShared.updateSettings === 'function') {
    subtitleShared.updateSettings({ subtitleColorScheme: data.value }, {
      source: 'subtitle-window-color-scheme'
    });
  }

  if (window.__forwardSubtitleRenderStateToWindow) {
    if (subtitleShared && typeof subtitleShared.getRenderState === 'function') {
      window.__forwardSubtitleRenderStateToWindow(subtitleShared.getRenderState());
    } else {
      window.__forwardSubtitleRenderStateToWindow({
        subtitleEnabled: readSubtitleEnabledForWindowSync(subtitleShared),
        visible: false,
        text: '',
        userLanguage: localStorage.getItem('userLanguage') || 'en',
        uiLocale: localStorage.getItem('i18nextLng') || 'en-US',
        subtitleOpacity: 95,
        subtitlePanelBounds: { width: 600, height: 68 },
        subtitlePanelLocked: false,
        subtitleInteractionPassthrough: false,
        subtitleDanmakuMode: false,
        subtitleFontSize: 26
      });
    }
  }
});

// ===== AgentHUD 按需控制 API =====
window.nekoAgentHud = {
  show: () => ipcRenderer.send('neko:show-agent-hud'),
  hide: () => ipcRenderer.send('neko:hide-agent-hud'),
};

// ===== ReturnBall 返回球拖拽桥接（拖拽返回球 = 移动 Pet 窗口）=====
window.nekoPetDrag = {
  start: (sx, sy) => {
    if (_disableNativeReturnBallDrag) return false;
    if (Date.now() > returnBallPrimaryDragArmedUntil) return false;
    ipcRenderer.send(WINDOW_CONTROL_CHANNELS.DRAG_START, { shrink: true, sx, sy });
    return true;
  },
  stop: (sx, sy) => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.DRAG_STOP_AND_GET_BOUNDS, { sx, sy }),
  reveal: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.DRAG_REVEAL_AFTER_RENDERER_READY),
  getBounds: () => ipcRenderer.invoke(WINDOW_CONTROL_CHANNELS.GET_BOUNDS),
};

window.nekoSpatialAudio = {
  getSourceBounds: getSpatialAudioSourceBounds,
};

// ===== Host Capability 桥接 =====
// 只提供通用宿主能力；业务校验、保存和迁移决策仍由 NEKO 后端完成。
setupHostCapabilityBridge();
setupTutorialOverlayBridge();
setupTutorialLoadingOverlayBridge();
setupGoodbyeChatComposerHiddenBridge();
setupVoiceConfigSwitchingBridge();
setupMusicPlayerBridge();
setupAutostartBridge();

// ===== 跨平台活动信号桥（NEKO issue #1023） =====
// 暴露 window.nekoActivitySignal.read()，供 static/app-activity-signal.js
// 拉取 OS 信号 5s 心跳上报给后端 tracker。主进程缓存采样，invoke 即时返回。
// 没 NEKO（dev 直接打开 NEKO-PC 测试时）也安全 —— bridge 永远暴露，
// 但 NEKO 那边检测到 lanlan_name 缺失就 no-op。
setupActivitySignalBridge();

// ===== 交互状态联动：drag / resize 期间暂停 3D 渲染主循环 =====
// 主进程在 DRAG_START / RESIZE_START / 对应 STOP 时通过 PET_CHANNELS.INTERACTION_STATE
// 通知本窗口。暂停期间：
//   - Live2D / VRM / MMD 三类 manager 的 pauseRendering() 释放 GPU/CPU 时间片给 DWM 合成
//   - 冻结 setIgnoreMouseEvents 切换，避免 drag 期间穿透状态抖动叠加 DWM overlay 重建
// 收到 stop 后立即恢复；若收到重复的同向信号，内部接口各自幂等。
// 全局标志 window.__nekoPetInteracting__ 暴露给页面内其它动画循环作为可选提示。
window.__nekoPetInteracting__ = false;

function _applyInteractionState(interacting) {
  window.__nekoPetInteracting__ = !!interacting;
  setDesktopCompactChatBoundsInteractionActive(!!interacting);
  // 三类 manager 非必然同时存在：用户模型类型决定只加载其中之一。
  // 各自 pause/resume 都检查了内部状态，多次调用安全。
  try {
    if (interacting) {
      if (window.live2dManager && typeof window.live2dManager.pauseRendering === 'function') {
        window.live2dManager.pauseRendering();
      }
      if (window.vrmManager && typeof window.vrmManager.pauseRendering === 'function') {
        window.vrmManager.pauseRendering();
      }
      if (window.mmdManager && typeof window.mmdManager.pauseRendering === 'function') {
        window.mmdManager.pauseRendering();
      }
      // Fix 3：drag/resize 期间冻结穿透状态切换，避免 DWM overlay 重建
      freezeMouseThrough(60 * 1000); // 超时兜底：万一 stop 信号丢失，60s 后自动解冻
    } else {
      if (window.live2dManager && typeof window.live2dManager.resumeRendering === 'function') {
        window.live2dManager.resumeRendering();
      }
      if (window.vrmManager && typeof window.vrmManager.resumeRendering === 'function') {
        window.vrmManager.resumeRendering();
      }
      if (window.mmdManager && typeof window.mmdManager.resumeRendering === 'function') {
        window.mmdManager.resumeRendering();
      }
      unfreezeMouseThrough();
    }
  } catch (e) {
    console.warn('[Preload-Pet] INTERACTION_STATE 处理异常:', e);
  }
}

ipcRenderer.on(PET_CHANNELS.INTERACTION_STATE, (_event, payload) => {
  _applyInteractionState(payload && payload.interacting);
});

// ===== Toast / 暗色模式 / 外部链接（共享模块）=====
setupToastOverride();
setupVoiceToastOverride(); // voice toast 转发到独立 toast 窗口（多窗口方案，避免被 Pet 窗口裁掉）
setupElectronShell();
setupDarkMode();


// ===== 原有 API 注入 =====

// 多屏幕边缘检测 API
window.addEventListener('neko:idle-cat1-layer-request', function(event) {
  var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
  ipcRenderer.send(PET_CHANNELS.IDLE_CAT_COMPANION_LAYER, {
    active: !!detail.active,
    reason: detail.reason || '',
    targetKind: detail.targetKind || '',
    containerId: detail.containerId || '',
    timestamp: Date.now(),
  });
});

window.electronScreen = {
  getCursorPoint: () => ipcRenderer.invoke('get-cursor-point'),
  getAllDisplays: () => ipcRenderer.invoke('get-all-displays'),
  getCurrentDisplay: () => ipcRenderer.invoke('get-current-display'),
  // 主屏信息，屏幕坐标系（与 win:get-bounds 同坐标系），用于空间音频听者参考点
  getPrimaryDisplayInfo: () => ipcRenderer.invoke('get-primary-display-info'),
  isPointOnScreen: (x, y) => ipcRenderer.invoke('is-point-on-screen', x, y),
  clampToScreen: (x, y, w = 0, h = 0) => ipcRenderer.invoke('clamp-to-screen', x, y, w, h),
  moveWindowToDisplay: (screenX, screenY) => ipcRenderer.invoke('move-window-to-display', screenX, screenY),
};

// 屏幕捕获 API
window.electronDesktopCapturer = {
  getSources: (options = {}) => ipcRenderer.invoke('get-desktop-sources', options),
  // 将渲染器端选中的源 ID 同步到主进程，供 setDisplayMediaRequestHandler 使用
  setSelectedSource: (sourceId) => ipcRenderer.invoke('set-selected-screen-source', sourceId || null),
  // 主进程直接对某个源做一次性截图，返回 { success, dataUrl, width, height } 或 { success:false, error }
  captureSourceAsDataUrl: (sourceId) => ipcRenderer.invoke('capture-source-as-dataurl', sourceId),
  // "隐藏NEKO" 再截图：主进程原子化 hide 全部 NEKO 窗口 → 合成等待 → desktopCapturer
  // 抓指定源 → show 回来。渲染器只需提供 sourceId 等返回 { success, dataUrl, width, height }。
  captureSourceWithoutNeko: (sourceId) => ipcRenderer.invoke('capture-source-without-neko', sourceId),
  // 独立 hide/restore —— 用于 atomic 路径失败、渲染器要自己抓 MediaStream 帧时
  hideNekoWindows: () => ipcRenderer.invoke('hide-neko-windows'),
  restoreNekoWindows: (hiddenIds) => ipcRenderer.invoke('restore-neko-windows', hiddenIds),
};

// （electronShell 和 nekoDarkMode 已由 preload-common 统一提供）

// --- 复位模型位置 ---
ipcRenderer.on('reset-model-position', () => {
  console.log('[Preload-Pet] 收到复位模型位置消息');
  try {
    // model_type 为 'live3d' 时，VRM 和 MMD 都走这个值，需要看 live3d_sub_type 区分
    const modelType = (window.lanlan_config && window.lanlan_config.model_type || 'live2d').toLowerCase();
    const subType = (window.lanlan_config && window.lanlan_config.live3d_sub_type || '').toLowerCase();

    if ((modelType === 'vrm' || (modelType === 'live3d' && subType === 'vrm')) && window.vrmManager && typeof window.vrmManager.resetModelPosition === 'function') {
      window.vrmManager.resetModelPosition();
      console.log('[Preload-Pet] VRM 模型位置复位成功');
    } else if ((modelType === 'live3d' && subType !== 'vrm') && window.mmdManager && typeof window.mmdManager.resetModelPosition === 'function') {
      window.mmdManager.resetModelPosition();
      console.log('[Preload-Pet] MMD 模型位置复位成功');
    } else if (window.live2dManager && typeof window.live2dManager.resetModelPosition === 'function') {
      window.live2dManager.resetModelPosition();
      console.log('[Preload-Pet] Live2D 模型位置复位成功');
    } else {
      console.warn('[Preload-Pet] 没有可用的模型管理器来复位位置');
    }
  } catch (error) {
    console.error('[Preload-Pet] 复位模型位置时出错:', error);
  }
});

// --- 恢复默认模型（live2d/MMD/VRM -> 默认 Live2D） ---
// 由托盘"高级设置 → 恢复默认模型"菜单触发。renderer 侧的
// window.resetToDefaultModel（定义于 NEKO 的 static/app-interpage.js）
// 会持久化默认 Live2D 模型并触发 handleModelReload 完成热切换。
ipcRenderer.on('reset-to-default-model', () => {
  console.log('[Preload-Pet] 收到恢复默认模型消息');
  try {
    if (typeof window.resetToDefaultModel === 'function') {
      Promise.resolve(window.resetToDefaultModel()).catch((err) => {
        console.error('[Preload-Pet] 恢复默认模型失败:', err);
      });
    } else {
      console.warn('[Preload-Pet] window.resetToDefaultModel 未就绪，无法恢复默认模型');
    }
  } catch (error) {
    console.error('[Preload-Pet] 恢复默认模型时出错:', error);
  }
});

// （toggle-dark-mode 已由 preload-common setupDarkMode() 统一处理）

// --- 屏幕切换 ---
ipcRenderer.on('display-changed', (event, displayInfo) => {
  window.dispatchEvent(new CustomEvent('electron-display-changed', { detail: displayInfo }));
});

// ===== DOM Ready =====
// ===== Wayland: Pet 窗口内 Inline Toast =====
// 在 Pet 窗口右上角渲染通知，复用后端 index.css 的 #status-toast 样式，
// 避免创建独立 Toast BrowserWindow 阻塞 Wayland 合成器
function setupInlineToast() {
  // 复用页面已有的 #status-toast 元素（index.html 自带），或创建一个
  var statusToast = document.getElementById('status-toast');
  if (!statusToast) {
    statusToast = document.createElement('div');
    statusToast.id = 'status-toast';
    document.body.appendChild(statusToast);
  }

  var statusTimeout = null;
  var cleanupTimer = null;
  var preparingHideTimer = null;
  var readyToastTimer = null;
  var readyHideTimer = null;

  function applyInlineStatusToastFrame() {
    statusToast.style.position = 'fixed';
    statusToast.style.top = '20px';
    statusToast.style.right = '64px';
    statusToast.style.left = 'auto';
    statusToast.style.width = 'min(460px, calc(100vw - 128px))';
    statusToast.style.maxWidth = 'none';
    statusToast.style.minWidth = '0';
    statusToast.style.boxSizing = 'border-box';
    statusToast.style.overflowWrap = 'anywhere';
    statusToast.style.transformOrigin = 'top right';
    statusToast.style.zIndex = '99999';
  }

  applyInlineStatusToastFrame();

  function hideToast() {
    if (statusTimeout) { clearTimeout(statusTimeout); statusTimeout = null; }
    if (cleanupTimer) { clearTimeout(cleanupTimer); cleanupTimer = null; }
    statusToast.classList.remove('show');
    statusToast.classList.add('hide');
    cleanupTimer = setTimeout(function() {
      statusToast.textContent = '';
      cleanupTimer = null;
    }, 300);
  }

  function showToast(message, duration) {
    duration = duration || 4000;
    if (!message || !message.trim()) {
      hideToast();
      return;
    }

    if (statusTimeout) { clearTimeout(statusTimeout); statusTimeout = null; }
    if (cleanupTimer) { clearTimeout(cleanupTimer); cleanupTimer = null; }

    applyInlineStatusToastFrame();
    statusToast.textContent = message;
    statusToast.style.display = 'flex';
    statusToast.style.visibility = 'visible';
    statusToast.classList.remove('hide');
    setTimeout(function() { statusToast.classList.add('show'); }, 10);

    statusTimeout = setTimeout(function() {
      statusToast.classList.remove('show');
      statusToast.classList.add('hide');
      cleanupTimer = setTimeout(function() {
        statusToast.textContent = '';
        cleanupTimer = null;
      }, 300);
    }, duration);
  }

  function injectInlineVoiceToastAnimations() {
    if (document.querySelector('style[data-inline-voice-toast-animation]')) return;
    var style = document.createElement('style');
    style.setAttribute('data-inline-voice-toast-animation', 'true');
    style.textContent = [
      '@keyframes voiceToastFadeIn {',
      '  from { opacity: 0; transform: translateX(-50%) scale(0.8); }',
      '  to { opacity: 1; transform: translateX(-50%) scale(1); }',
      '}',
      '@keyframes spin { to { transform: rotate(360deg); } }',
    ].join('\n');
    document.head.appendChild(style);
  }

  function translateText(key, fallback) {
    try {
      if (typeof window.safeT === 'function') {
        var safeTranslated = window.safeT(key, fallback);
        if (typeof safeTranslated === 'string' && safeTranslated && safeTranslated !== key) {
          return safeTranslated;
        }
      }
      if (typeof window.t === 'function') {
        var translated = window.t(key, { defaultValue: fallback });
        if (typeof translated === 'string' && translated && translated !== key) {
          return translated;
        }
      }
    } catch (_) {}
    return fallback;
  }

  function ensureVoiceToastElement(id) {
    var toast = document.getElementById(id);
    if (!toast) {
      toast = document.createElement('div');
      toast.id = id;
      document.body.appendChild(toast);
    }
    return toast;
  }

  function applyVoiceToastFrame(toast, backgroundImage) {
    toast.style.cssText = [
      'position:fixed',
      'bottom:18%',
      'left:50%',
      'transform:translateX(-50%)',
      "background-image:url('/static/icons/" + backgroundImage + "')",
      'background-size:100% 100%',
      'background-position:center',
      'background-repeat:no-repeat',
      'background-color:transparent',
      'color:white',
      'padding:20px 32px',
      'border-radius:16px',
      'font-size:16px',
      'font-weight:600',
      'box-shadow:none',
      'z-index:10000',
      'display:flex',
      'align-items:center',
      'gap:12px',
      'animation:voiceToastFadeIn 0.3s ease',
      'pointer-events:none',
      'width:320px',
      'box-sizing:border-box',
      'justify-content:center',
    ].join(';');
    toast.style.display = 'flex';
    toast.style.visibility = 'visible';
  }

  function showInlineVoicePreparingToast(message) {
    injectInlineVoiceToastAnimations();
    hideInlineReadyToSpeakToast();
    clearPreparingToastTimers();
    var toast = ensureVoiceToastElement('voice-preparing-toast');
    applyVoiceToastFrame(toast, 'reminder_blue.png');
    toast.innerHTML = '';

    var spinner = document.createElement('div');
    spinner.style.cssText = 'width:20px;height:20px;border:3px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin 1s linear infinite;flex-shrink:0;';
    var span = document.createElement('span');
    span.textContent = message || '';
    toast.appendChild(spinner);
    toast.appendChild(span);
  }

  function clearPreparingToastTimers() {
    if (preparingHideTimer) { clearTimeout(preparingHideTimer); preparingHideTimer = null; }
  }

  function clearReadyToastTimers() {
    if (readyToastTimer) { clearTimeout(readyToastTimer); readyToastTimer = null; }
    if (readyHideTimer) { clearTimeout(readyHideTimer); readyHideTimer = null; }
  }

  function hideInlineReadyToSpeakToast() {
    var toast = document.getElementById('voice-ready-toast');
    if (toast) {
      clearReadyToastTimers();
      toast.style.display = 'none';
    }
  }

  function hideInlineVoicePreparingToast() {
    var toast = document.getElementById('voice-preparing-toast');
    if (toast) {
      clearPreparingToastTimers();
      toast.style.animation = 'voiceToastFadeIn 0.3s ease reverse';
      preparingHideTimer = setTimeout(function() {
        preparingHideTimer = null;
        toast.style.display = 'none';
      }, 300);
    }
  }

  function showInlineReadyToSpeakToast(message) {
    injectInlineVoiceToastAnimations();
    hideInlineVoicePreparingToast();
    clearReadyToastTimers();
    var toast = ensureVoiceToastElement('voice-ready-toast');
    applyVoiceToastFrame(toast, 'reminder_midori.png');
    toast.innerHTML = '';

    var img = document.createElement('img');
    img.src = '/static/icons/ready_to_talk.png';
    img.style.cssText = 'width:36px;height:36px;object-fit:contain;display:block;flex-shrink:0;';
    img.alt = 'ready';
    var span = document.createElement('span');
    span.style.cssText = 'display:flex;align-items:center;';
    span.textContent = message || translateText('app.readyToSpeak', '可以开始说话了！');
    toast.appendChild(img);
    toast.appendChild(span);

    readyToastTimer = setTimeout(function() {
      readyToastTimer = null;
      toast.style.animation = 'voiceToastFadeIn 0.3s ease reverse';
      readyHideTimer = setTimeout(function() {
        readyHideTimer = null;
        toast.style.display = 'none';
      }, 300);
    }, 2000);
  }

  ipcRenderer.on('neko:inline-toast', function(_event, payload) {
    var channel = payload && payload.channel;
    var data = payload && payload.data;
    var message = (data && data.message) || '';
    var duration = (data && data.duration) || 4000;
    if (channel === 'neko:toast-voice-preparing') {
      showInlineVoicePreparingToast(message);
      return;
    }
    if (channel === 'neko:toast-voice-hide-preparing') {
      hideInlineVoicePreparingToast();
      return;
    }
    if (channel === 'neko:toast-voice-ready') {
      showInlineReadyToSpeakToast(message);
      return;
    }
    if (message) showToast(message, duration);
  });

  console.log('[Linux-InlineToast] Inline toast renderer installed (using #status-toast style)');
}

// ===== Linux Wayland: setShape 穿透方案 =====
// 根治方案：合并所有可交互区域为一个矩形，裁剪到窗口边界内
// 纯事件驱动 + MutationObserver，不轮询，避免频繁 setShape 导致 Wayland 丢失点击
function setupLinuxShapePassthrough() {
  debugLinuxInput('[preload-pet] setupLinuxShapePassthrough started');
  var _lastShapeHash = null;
  var _shapeRefreshTimer = null;
  var _lastPetRaiseAt = 0;

  function clampRect(r) {
    var x = Math.max(0, r.x);
    var y = Math.max(0, r.y);
    var right = Math.min(window.innerWidth, r.x + r.width);
    var bottom = Math.min(window.innerHeight, r.y + r.height);
    var w = right - x;
    var h = bottom - y;
    if (w <= 0 || h <= 0) return null;
    return { x: Math.round(x), y: Math.round(y), width: Math.round(w), height: Math.round(h) };
  }

  function normalizeShapeLocalBoundsToRect(bounds) {
    if (!bounds || typeof bounds !== 'object') return null;
    var left = Number(bounds.x);
    var top = Number(bounds.y);
    if (!Number.isFinite(left)) left = Number(bounds.left);
    if (!Number.isFinite(top)) top = Number(bounds.top);
    if (!Number.isFinite(left)) left = Number(bounds.minX);
    if (!Number.isFinite(top)) top = Number(bounds.minY);
    var width = Number(bounds.width);
    var height = Number(bounds.height);
    if (!Number.isFinite(width)) {
      var right = Number(bounds.right);
      if (!Number.isFinite(right)) right = Number(bounds.maxX);
      if (Number.isFinite(right) && Number.isFinite(left)) width = right - left;
    }
    if (!Number.isFinite(height)) {
      var bottom = Number(bounds.bottom);
      if (!Number.isFinite(bottom)) bottom = Number(bounds.maxY);
      if (Number.isFinite(bottom) && Number.isFinite(top)) height = bottom - top;
    }
    if (!Number.isFinite(left) || !Number.isFinite(top) ||
        !Number.isFinite(width) || !Number.isFinite(height) ||
        width <= 0 || height <= 0) {
      return null;
    }
    return { x: left, y: top, width: width, height: height };
  }

  function getModelRectFromDesktopAvatarBounds(modelType) {
    try {
      var entry = pickDesktopAvatarBoundsEntry({ bypassCache: true });
      if (!entry || !entry.bounds) return null;
      if (modelType && entry.type && entry.type !== modelType) return null;
      return normalizeShapeLocalBoundsToRect(entry.bounds);
    } catch (_) {
      return null;
    }
  }

  var WAYLAND_PET_SHAPE_CHAT_EXCLUDE_SELECTOR = [
    '#react-chat-window-root',
    '#react-chat-window-shell',
    '#react-chat-window-overlay',
    '#chat-container',
    '[data-compact-geometry-owner]',
    '[data-compact-geometry-item]',
    '[data-compact-drag-surface]',
    '[data-compact-no-drag]',
    '.compact-chat-surface-shell',
    '.compact-chat-surface-frame',
    '.compact-export-history-anchor',
    '.compact-history-visibility-handle',
    '.compact-chat-minimize-ball',
    '.composer-input',
    '.composer-bottom-tools',
    '.chat-export-preview-backdrop',
    '.neko-e-ball-icon'
  ].join(', ');

  function isWaylandPetShapeExcludedElement(el) {
    try {
      return !!(el && el.closest && el.closest(WAYLAND_PET_SHAPE_CHAT_EXCLUDE_SELECTOR));
    } catch (_) {
      return false;
    }
  }

  function getIdleChatMinimizedLocalAvoidRect() {
    if (!_idleChatMinimizedState.minimized || !_idleChatMinimizedState.screenRect) return null;
    var rect = _idleChatMinimizedState.screenRect;
    var pad = 0;
    var origin = getPetWindowScreenOrigin();
    return clampRect({
      x: rect.left - origin.x - pad,
      y: rect.top - origin.y - pad,
      width: rect.width + pad * 2,
      height: rect.height + pad * 2
    });
  }

  function subtractRect(rect, cutout) {
    if (!rect || !cutout) return rect ? [rect] : [];
    var ax1 = rect.x;
    var ay1 = rect.y;
    var ax2 = rect.x + rect.width;
    var ay2 = rect.y + rect.height;
    var bx1 = cutout.x;
    var by1 = cutout.y;
    var bx2 = cutout.x + cutout.width;
    var by2 = cutout.y + cutout.height;
    var ix1 = Math.max(ax1, bx1);
    var iy1 = Math.max(ay1, by1);
    var ix2 = Math.min(ax2, bx2);
    var iy2 = Math.min(ay2, by2);
    if (ix1 >= ix2 || iy1 >= iy2) return [rect];
    var parts = [
      { x: ax1, y: ay1, width: ax2 - ax1, height: iy1 - ay1 },
      { x: ax1, y: iy2, width: ax2 - ax1, height: ay2 - iy2 },
      { x: ax1, y: iy1, width: ix1 - ax1, height: iy2 - iy1 },
      { x: ix2, y: iy1, width: ax2 - ix2, height: iy2 - iy1 }
    ];
    return parts.map(clampRect).filter(Boolean);
  }

  function subtractIdleChatMinimizedBallFromRects(rects) {
    var avoidRect = getIdleChatMinimizedLocalAvoidRect();
    if (!avoidRect) return rects;
    var next = [];
    for (var i = 0; i < rects.length; i++) {
      var parts = subtractRect(rects[i], avoidRect);
      for (var j = 0; j < parts.length; j++) next.push(parts[j]);
    }
    return next;
  }

  function getModelRect() {
    try {
      if (isCurrentModelInGoodbyeMode()) return null;
      var modelType = getActiveModelType();
      var avatarBoundsRect = getModelRectFromDesktopAvatarBounds(modelType);
      if (avatarBoundsRect) return avatarBoundsRect;
      if (modelType === 'live2d' && window.live2dManager) {
        if (typeof window.live2dManager.getModelScreenBounds === 'function') {
          var screenBounds = normalizeShapeLocalBoundsToRect(window.live2dManager.getModelScreenBounds());
          if (screenBounds) return screenBounds;
        }
        var model = window.live2dManager.getCurrentModel();
        if (!model) return null;
        var bounds = model.getBounds();
        var live2dRect = normalizeShapeLocalBoundsToRect(bounds);
        if (!live2dRect || live2dRect.width < 20) return null;
        return live2dRect;
      } else if (modelType === 'vrm' && window.vrmManager) {
        if (typeof window.vrmManager.getModelScreenBounds === 'function') {
          var vrmScreenBounds = normalizeShapeLocalBoundsToRect(window.vrmManager.getModelScreenBounds());
          if (vrmScreenBounds) return vrmScreenBounds;
        }
        if (!window.vrmManager.interaction) return null;
        if (typeof window.vrmManager.interaction.updateModelBoundsCache === 'function')
          window.vrmManager.interaction.updateModelBoundsCache();
        var sb = window.vrmManager.interaction._cachedScreenBounds;
        if (!sb) return null;
        return normalizeShapeLocalBoundsToRect({ left: sb.minX, top: sb.minY, right: sb.maxX, bottom: sb.maxY });
      } else if (modelType === 'mmd' && window.mmdManager) {
        if (typeof window.mmdManager.getModelScreenBounds === 'function') {
          var mmdScreenBounds = normalizeShapeLocalBoundsToRect(window.mmdManager.getModelScreenBounds());
          if (mmdScreenBounds) return mmdScreenBounds;
        }
        if (!window.mmdManager.interaction) return null;
        if (typeof window.mmdManager.interaction.updateModelBoundsCache === 'function')
          window.mmdManager.interaction.updateModelBoundsCache();
        var sb2 = window.mmdManager.interaction._cachedScreenBounds;
        if (!sb2) return null;
        return normalizeShapeLocalBoundsToRect({ left: sb2.minX, top: sb2.minY, right: sb2.maxX, bottom: sb2.maxY });
      }
      return null;
    } catch (e) { return null; }
  }

  function mergeOverlappingRects(rects) {
    if (rects.length <= 1) return rects;
    var MERGE_GAP = 20;
    var merged = rects.slice();
    var changed = true;
    while (changed) {
      changed = false;
      for (var i = 0; i < merged.length; i++) {
        for (var j = i + 1; j < merged.length; j++) {
          var a = merged[i], b = merged[j];
          if (a.x - MERGE_GAP <= b.x + b.width &&
              b.x - MERGE_GAP <= a.x + a.width &&
              a.y - MERGE_GAP <= b.y + b.height &&
              b.y - MERGE_GAP <= a.y + a.height) {
            merged[i] = {
              x: Math.min(a.x, b.x),
              y: Math.min(a.y, b.y),
              width: Math.max(a.x + a.width, b.x + b.width) - Math.min(a.x, b.x),
              height: Math.max(a.y + a.height, b.y + b.height) - Math.min(a.y, b.y)
            };
            merged.splice(j, 1);
            changed = true;
            break;
          }
        }
        if (changed) break;
      }
    }
    return merged;
  }

  function rectsHash(rects) {
    var parts = [];
    for (var i = 0; i < rects.length; i++) {
      var r = rects[i];
      parts.push(r.x + ',' + r.y + ',' + r.width + ',' + r.height);
    }
    return parts.join(';');
  }

  function maybeRaisePetWindow(reason) {
    var now = Date.now();
    if (now - _lastPetRaiseAt < 220) return;
    _lastPetRaiseAt = now;
    try {
      ipcRenderer.send(WINDOW_CONTROL_CHANNELS.BRING_TO_FRONT);
      debugLinuxInput('[preload-setShape] Pet bringToFront: ' + (reason || 'pointer'));
    } catch (_) {}
  }

  // 模型区域快照：Wayland setShape 使用窗口本地坐标。这里只做很小的网格吸振，
  // 避免把透明 bbox 周边扩成大块可滚轮区域。
  var _stableModelShapeRects = null;
  var GRID = 12;

  function normalizeWaylandModelRect(raw) {
    var local = normalizeShapeLocalBoundsToRect(raw);
    if (!local) return null;
    return clampRect(local);
  }

  function snapSmallRect(raw) {
    if (!raw) return null;
    var x = Math.floor(raw.x / GRID) * GRID;
    var y = Math.floor(raw.y / GRID) * GRID;
    var right = Math.ceil((raw.x + raw.width) / GRID) * GRID;
    var bottom = Math.ceil((raw.y + raw.height) / GRID) * GRID;
    return clampRect({ x: x, y: y, width: right - x, height: bottom - y });
  }

  function appendWaylandModelShapeRects(rects, raw, modelType) {
    var bounds = normalizeWaylandModelRect(raw);
    if (!bounds) return;
    var normalized = {
      left: bounds.x,
      top: bounds.y,
      right: bounds.x + bounds.width,
      bottom: bounds.y + bounds.height,
      modelType: modelType || getActiveModelType()
    };
    var before = rects.length;
    addEllipseInputRegions(rects, normalized, {
      rxFactor: normalized.modelType === 'live2d' ? 0.6 : 0.62,
      ryFactor: normalized.modelType === 'live2d' ? 0.9 : 0.96,
      extraPad: normalized.modelType === 'live2d' ? 10 : 14,
      bands: 12
    });
    for (var i = before; i < rects.length; i += 1) {
      rects[i] = snapSmallRect(rects[i]);
    }
  }

  // Max element size to include — anything larger is a container div, not a button
  var MAX_INTERACTIVE_SIZE = 400;

  function buildWaylandPetShapeScreenRects(rects) {
    var origin = getPetWindowScreenOrigin();
    return (Array.isArray(rects) ? rects : []).map(function(rect) {
      if (!rect) return null;
      return {
        x: Math.round(origin.x + Number(rect.x || 0)),
        y: Math.round(origin.y + Number(rect.y || 0)),
        width: Math.max(1, Math.round(Number(rect.width) || 1)),
        height: Math.max(1, Math.round(Number(rect.height) || 1))
      };
    }).filter(Boolean);
  }

  function buildWaylandPetWindowBoundsMeta() {
    var origin = getPetWindowScreenOrigin();
    return {
      x: Math.round(origin.x),
      y: Math.round(origin.y),
      width: Math.max(1, Math.round(window.innerWidth || 1)),
      height: Math.max(1, Math.round(window.innerHeight || 1))
    };
  }

  function buildWaylandPetSetShapeMeta(reason, rects) {
    return {
      source: 'pet-wayland-model',
      reason: reason || 'pet-hit-region',
      mode: 'hit-region',
      wayland: true,
      devicePixelRatio: Number(window.devicePixelRatio) || 1,
      bounds: buildWaylandPetWindowBoundsMeta(),
      screenRects: buildWaylandPetShapeScreenRects(rects)
    };
  }

  function buildWaylandPetFullWindowSetShapeMeta(reason, rects) {
    return {
      source: 'pet-wayland-full-window',
      reason: reason || 'full-window-surface',
      mode: 'full-window-surface',
      wayland: true,
      devicePixelRatio: Number(window.devicePixelRatio) || 1,
      bounds: buildWaylandPetWindowBoundsMeta(),
      screenRects: buildWaylandPetShapeScreenRects(rects)
    };
  }

  var _lastWaylandFullWindowInputReason = '';

  function syncWaylandFullWindowInputReason(reason) {
    var next = reason || '';
    if (next === _lastWaylandFullWindowInputReason) return;
    _lastWaylandFullWindowInputReason = next;
    refreshPetWindowScreenBounds();
    setTimeout(forceRefresh, 80);
    setTimeout(forceRefresh, 240);
  }

  function applyShape() {
    var rects = [];
    var avatarToolFullWindowReason = getDesktopAvatarToolFullWindowInputReason();
    if (avatarToolFullWindowReason) {
      rects = getFullWindowInputRegion();
      var avatarToolHash = 'full-window:' + avatarToolFullWindowReason + ':' + rectsHash(rects);
      if (avatarToolHash !== _lastShapeHash) {
        _lastShapeHash = avatarToolHash;
        var avatarToolOrigin = getPetWindowScreenOrigin();
        debugLinuxInput('[preload-setShape] Avatar tool full-window input surface: ' + avatarToolFullWindowReason);
        ipcRenderer.send('neko:pet-set-shape', rects, {
          source: 'pet-wayland-avatar-tool',
          reason: avatarToolFullWindowReason,
          mode: 'avatar-tool-full-window',
          wayland: true,
          devicePixelRatio: Number(window.devicePixelRatio) || 1,
          bounds: {
            x: Math.round(avatarToolOrigin.x),
            y: Math.round(avatarToolOrigin.y),
            width: Math.max(1, Math.round(window.innerWidth || 1)),
            height: Math.max(1, Math.round(window.innerHeight || 1))
          },
          screenRects: buildWaylandPetShapeScreenRects(rects)
        });
      }
      return;
    }

    var fullWindowInputReason = getVisibleX11FullWindowSurfaceReason();
    syncWaylandFullWindowInputReason(fullWindowInputReason);
    if (fullWindowInputReason) {
      rects = getFullWindowInputRegion();
      var fullHash = 'full-window:' + fullWindowInputReason + ':' + rectsHash(rects);
      if (fullHash !== _lastShapeHash) {
        _lastShapeHash = fullHash;
        debugLinuxInput('[preload-setShape] Full-window input surface: ' + fullWindowInputReason);
        ipcRenderer.send('neko:pet-set-shape', rects, buildWaylandPetFullWindowSetShapeMeta(fullWindowInputReason, rects));
      }
      return;
    }

    // Model area: ellipse bands aligned with hitTest, not a full padded bbox.
    var modelRaw = getModelRect();
    var modelShapeRects = [];
    appendWaylandModelShapeRects(modelShapeRects, modelRaw, getActiveModelType());
    modelShapeRects = modelShapeRects.filter(Boolean);
    if (modelShapeRects.length) {
      var modelHash = rectsHash(modelShapeRects);
      if (!_stableModelShapeRects || rectsHash(_stableModelShapeRects) !== modelHash) {
        _stableModelShapeRects = modelShapeRects;
      }
    } else if (isCurrentModelInGoodbyeMode()) {
      _stableModelShapeRects = null;
    }
    var modelRectsForShape = [];
    if (_stableModelShapeRects) {
      for (var mr = 0; mr < _stableModelShapeRects.length; mr += 1) {
        var modelClamped = clampRect(_stableModelShapeRects[mr]);
        if (modelClamped) modelRectsForShape.push(modelClamped);
      }
    }

    // Large floating panels need their whole surface clickable. The generic
    // button scan below intentionally skips wide containers, which is correct
    // for layout wrappers but wrong for draggable/croppable modal surfaces.
    try {
      document.querySelectorAll(DESKTOP_FLOATING_INTERACTIVE_SURFACE_SELECTORS.join(', ')).forEach(function(el) {
        if (isWaylandPetShapeExcludedElement(el)) return;
        var rect = getVisibleElementInputRect(el, 18);
        if (rect) rects.push(rect);
      });
    } catch (_) {}

    try {
      document.querySelectorAll(DESKTOP_AVATAR_TOOL_COMPACT_SELECTOR).forEach(function(el) {
        if (isWaylandPetShapeExcludedElement(el)) return;
        var priorityRect = getVisibleElementInputRect(el, 24);
        if (priorityRect) rects.push(priorityRect);
      });
    } catch (_) {}

    // UI elements — interactive controls + floating buttons near the model.
    // live2d-floating-btn: the 5 floating action buttons (mic/screen/agent/settings/goodbye)
    // live2d-popup: popup container — include entire bbox so all content inside is covered
    // live2d-settings-menu-item: 记忆浏览/创意工坊 navigation links inside settings popup
    // live2d-toggle-item: toggle rows (主动搭话/自主视觉) inside settings popup
    // live2d-trigger-btn: the small triangle trigger button next to mic/screen
    // [data-neko-sidepanel]: settings/animation/character side panel (position:fixed container)
    var selectors = 'button, input, select, textarea, a, [role="button"], [onclick], ' +
      '[class*="btn"], [class*="button"], [class*="popup"], [class*="slider"], [class*="icon"], ' +
      '[class*="live2d-floating-btn"], [class*="vrm-floating-btn"], [class*="mmd-floating-btn"], ' +
      '[class*="live2d-return-btn"], [class*="vrm-return-btn"], [class*="mmd-return-btn"], ' +
      '[class*="live2d-popup"], [class*="vrm-popup"], [class*="mmd-popup"], ' +
      '[class*="live2d-settings-menu-item"], [class*="live2d-toggle-item"], ' +
      '[class*="live2d-trigger-btn"], [class*="vrm-trigger-btn"], [class*="mmd-trigger-btn"], ' +
      '[data-neko-sidepanel]';
    var elements = document.querySelectorAll(selectors);
    var UI_PAD = 15;
    var skippedLarge = 0;
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (shouldSkipYuiGuideResidualShapeElement(el)) continue;
      if (isWaylandPetShapeExcludedElement(el)) continue;
      // Skip canvas (Live2D) — model area is handled separately above
      if (el.tagName === 'CANVAS') continue;
      var style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      if (parseFloat(style.opacity) === 0) continue;
      var r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      // Skip oversized elements — they're containers, not buttons
      // Exclude if BOTH dimensions are large (square containers) OR if width alone is huge (full-width toolbars)
      if ((r.width > MAX_INTERACTIVE_SIZE && r.height > MAX_INTERACTIVE_SIZE) || r.width > window.innerWidth * 0.5) {
        skippedLarge++;
        continue;
      }
      var clamped = clampRect({
        x: r.x - UI_PAD,
        y: r.y - UI_PAD,
        width: r.width + UI_PAD * 2,
        height: r.height + UI_PAD * 2
      });
      if (clamped) rects.push(clamped);
    }

    // Merge UI rects only. Model ellipse bands must stay split; merging them
    // recreates a large transparent bbox that catches wheel outside the model.
    rects = mergeOverlappingRects(rects);
    for (var modelIdx = 0; modelIdx < modelRectsForShape.length; modelIdx += 1) {
      rects.push(modelRectsForShape[modelIdx]);
    }
    rects = subtractIdleChatMinimizedBallFromRects(rects);

    // No interactive areas → minimal shape (full passthrough)
    if (rects.length === 0) {
      if (_lastShapeHash !== 'empty') {
        _lastShapeHash = 'empty';
        var bx = Math.max(0, window.innerWidth - 2);
        var by = Math.max(0, window.innerHeight - 2);
        var emptyRect = [{ x: bx, y: by, width: 1, height: 1 }];
        debugLinuxInput('[preload-setShape] No interactive areas -> passthrough rect ' + JSON.stringify(emptyRect) + ' innerW=' + window.innerWidth + ' innerH=' + window.innerHeight);
        ipcRenderer.send('neko:pet-set-shape', emptyRect, {
          source: 'pet-wayland-empty',
          reason: 'empty-hit-region',
          mode: 'passthrough',
          wayland: true
        });
      }
      return;
    }

    // Hash-based change detection — only send IPC when rects actually changed
    var hash = rectsHash(rects);
    if (hash === _lastShapeHash) return;
    _lastShapeHash = hash;

    // Diagnostic: log rect details so we can verify correct behavior
    var details = [];
    for (var d = 0; d < rects.length; d++) {
      var rr = rects[d];
      details.push(rr.x + ',' + rr.y + ' ' + rr.width + 'x' + rr.height);
    }
    debugLinuxInput('[preload-setShape] Sending ' + rects.length + ' rects (skippedLarge=' + skippedLarge + '): ' + details.join(' | ') + ' innerW=' + window.innerWidth + ' innerH=' + window.innerHeight);
    ipcRenderer.send('neko:pet-set-shape', rects, buildWaylandPetSetShapeMeta('pet-hit-region', rects));
  }

  // 防抖：多次触发合并为一次，避免连续 DOM 变化导致多次 setShape
  function scheduleShapeRefresh() {
    if (_shapeRefreshTimer) clearTimeout(_shapeRefreshTimer);
    _shapeRefreshTimer = setTimeout(function() {
      _shapeRefreshTimer = null;
      applyShape();
    }, 16);
  }

  function forceRefresh() {
    _lastShapeHash = null;
    scheduleShapeRefresh();
  }
  _forceWaylandPetShapeRefresh = forceRefresh;

  function refreshAfterModelReady() {
    forceRefresh();
    setTimeout(forceRefresh, 120);
    setTimeout(forceRefresh, 420);
  }

  function refreshAfterPointerBoundary() {
    maybeRaisePetWindow('pointer-boundary');
    scheduleShapeRefresh();
    setTimeout(scheduleShapeRefresh, 80);
    setTimeout(forceRefresh, 220);
  }

  function recoverModelDragAfterRelease(reason) {
    setTimeout(function() {
      if (isModelDragging()) {
        resetModelDraggingState(reason || 'wayland-release');
      }
      forceRefresh();
    }, 180);
  }

  // ---- 事件驱动刷新 ----

  // 模型加载
  function hookLive2DModelLoaded() {
    var mgr = window.live2dManager;
    if (!mgr || typeof mgr !== 'object') return false;
    if (mgr._nekoShapeHooked) return true;
    var previous = typeof mgr.onModelLoaded === 'function' ? mgr.onModelLoaded : null;
    mgr.onModelLoaded = function(model, modelPath) {
      if (previous) { try { previous.call(this, model, modelPath); } catch (_) {} }
      forceRefresh();
      setTimeout(forceRefresh, 200);
    };
    mgr._nekoShapeHooked = true;
    return true;
  }

  hookLive2DModelLoaded();
  window.addEventListener('live2d-model-ready', refreshAfterModelReady);
  window.addEventListener('vrm-model-loaded', refreshAfterModelReady);
  window.addEventListener('mmd-model-loaded', refreshAfterModelReady);
  window.addEventListener('live2d-floating-buttons-ready', refreshAfterModelReady);
  window.addEventListener('resize', function() { refreshPetWindowScreenBounds(); forceRefresh(); });
  window.addEventListener('electron-display-changed', function() { refreshPetWindowScreenBounds(); forceRefresh(); });
  window.addEventListener('neko:idle-chat-minimized-state', function() { refreshPetWindowScreenBounds(); forceRefresh(); });
  window.addEventListener('pointerdown', function(event) {
    refreshAfterPointerBoundary();
  }, true);
  window.addEventListener('pointerup', function() {
    recoverModelDragAfterRelease('wayland-pointerup');
    refreshAfterPointerBoundary();
  }, true);
  window.addEventListener('pointercancel', function() {
    recoverModelDragAfterRelease('wayland-pointercancel');
    refreshAfterPointerBoundary();
  }, true);
  window.addEventListener('mouseup', function() {
    recoverModelDragAfterRelease('wayland-mouseup');
    refreshAfterPointerBoundary();
  }, true);
  document.addEventListener('mouseup', function() {
    recoverModelDragAfterRelease('wayland-document-mouseup');
    refreshAfterPointerBoundary();
  }, true);
  window.addEventListener('blur', function() {
    recoverModelDragAfterRelease('wayland-blur');
    refreshAfterPointerBoundary();
  });

  if (window.pageConfigReady && typeof window.pageConfigReady.then === 'function') {
    window.pageConfigReady.finally(function() { hookLive2DModelLoaded(); refreshAfterModelReady(); });
  }

  var hookAttempts = 0;
  var hookTimer = setInterval(function() {
    hookAttempts += 1;
    if (hookLive2DModelLoaded() || hookAttempts >= 50) clearInterval(hookTimer);
  }, 100);

  // MutationObserver：检测 DOM 变化（面板出现/消失、按钮显隐）
  var observer = new MutationObserver(function() {
    scheduleShapeRefresh();
  });
  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class', 'hidden']
  });

  // 初始应用
  applyShape();
  // 延迟再算一次（等模型/按钮加载完）
  setTimeout(forceRefresh, 500);
  setTimeout(forceRefresh, 2000);
  setTimeout(forceRefresh, 5000);

  // 慢速定期刷新：捕捉模型拖拽等不触发 DOM 事件的位移变化
  // hash 检查会阻止无变化时的冗余 IPC
  setInterval(function() { applyShape(); }, 3000);
}

document.addEventListener('DOMContentLoaded', () => {
  refreshPetWindowScreenBounds();
  // Use setShape passthrough only when the patched Electron binary supports it
  // on native Wayland. X11 keeps the window visually intact and uses
  // setIgnoreMouseEvents polling instead.
  var isLinuxWayland = _isWaylandPreload;
  var inputRegionBackend = null;
  var hasSetShape = false;
  if (process.platform === 'linux') {
    try { inputRegionBackend = ipcRenderer.sendSync('neko:input-region-backend'); } catch(e) {}
    hasSetShape = !!(inputRegionBackend && inputRegionBackend.canUseSetShape);
    if (!inputRegionBackend) {
      try { hasSetShape = ipcRenderer.sendSync('neko:has-set-shape'); } catch(e) {}
    }
  }

  debugLinuxInput('[preload-pet] DOMContentLoaded isLinuxWayland=' + isLinuxWayland + ' hasSetShape=' + hasSetShape + ' backend=' + (inputRegionBackend && inputRegionBackend.backend ? inputRegionBackend.backend : 'unknown') + ' platform=' + process.platform);

  if (process.platform === 'linux') {
    setupInlineToast();
  }

  if (hasSetShape && isLinuxWayland) {
    debugLinuxInput('[preload-pet] Calling setupLinuxShapePassthrough (hasSetShape=true)');
    setupLinuxShapePassthrough();
  } else {
    setupMouseThroughLogic();
    startMousePoller();
    startPetInputRegionReporter();
    if (!_isLinuxX11Preload) {
      ipcRenderer.send('set-ignore-mouse-events', false);
      lastIgnoreState = false;
      syncMouseThroughStateWithCursor();
    }
  }

  function syncMouseThroughAfterF8Restore() {
    if (_isLinuxX11Preload) return;
    if (_pendingTimeout) {
      clearTimeout(_pendingTimeout);
      _pendingTimeout = null;
    }
    unfreezeMouseThrough();
    lastIgnoreState = null;
    syncMouseThroughStateWithCursor();
    [50, 160, 320].forEach(function(delay) {
      setTimeout(function() {
        lastIgnoreState = null;
        syncMouseThroughStateWithCursor();
      }, delay);
    });
  }

  ipcRenderer.on('neko:f8-restore-sync-mouse-through', syncMouseThroughAfterF8Restore);

  // ===== Popup 穿透冻结 =====
  var POPUP_GUARD_MS = 280;
  window.addEventListener('neko-popup-opening', () => {
    freezeMouseThrough(_isLinuxX11Preload ? 1200 : POPUP_GUARD_MS);
  });
  window.addEventListener('neko-popup-closed', () => {
    if (_frozenTimer) clearTimeout(_frozenTimer);
    _frozenTimer = setTimeout(() => {
      _transitionFrozen = false;
      _frozenTimer = null;
      syncMouseThroughStateWithCursor();
    }, POPUP_GUARD_MS);
  });
  window.addEventListener('neko-popup-transition-start', (e) => {
    freezeMouseThrough((e.detail && e.detail.duration) || POPUP_GUARD_MS);
  });
  window.addEventListener('neko:yui-guide:plugin-dashboard-skip-bypass', (e) => {
    var enabled = !!(e && e.detail && e.detail.enabled);
    _yuiGuidePluginDashboardSkipBypassActive = enabled;
    if (enabled) {
      unfreezeMouseThrough();
      if (_pendingTimeout) {
        clearTimeout(_pendingTimeout);
        _pendingTimeout = null;
      }
      ipcRenderer.send('set-ignore-mouse-events', false);
      lastIgnoreState = false;
      _lastSwitchTime = Date.now();
      return;
    }
    syncMouseThroughStateWithCursor();
  });
  window.addEventListener('neko:tutorial-overlay-relay', function(event) {
    handleYuiGuideTutorialOverlayRelay(event && event.detail);
  });
  window.addEventListener('message', function(event) {
    var data = event && event.data;
    if (!data || data.__nekoTutorialOverlayRelay !== true) return;
    if (!isTrustedYuiGuideTutorialOverlayRelayMessage(event)) return;
    handleYuiGuideTutorialOverlayRelay(data.payload || {});
  });
  window.addEventListener('neko:yui-guide:tutorial-lifecycle-ended', function(event) {
    var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
    handleYuiGuideTutorialOverlayRelay(Object.assign({}, detail, {
      action: 'yui_guide_tutorial_lifecycle_ended'
    }));
  });
  window.addEventListener('neko:yui-guide:tutorial-input-restored', function(event) {
    var detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
    handleYuiGuideTutorialOverlayRelay(Object.assign({}, detail, {
      action: 'yui_guide_tutorial_input_restored'
    }));
  });
  window.addEventListener('neko:tutorial-started', handleYuiGuideTutorialStartedEvent);
  window.addEventListener('neko:avatar-floating-guide-started', handleYuiGuideTutorialStartedEvent);

  console.log('[Preload-Pet] 初始化完成（手动穿透 + 150ms 节流）');

});

// ===== 设置双向同步（Pet ↔ Chat）=====
setupSettingsSync({ role: 'pet' });
