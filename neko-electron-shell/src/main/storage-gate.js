'use strict';

const { CHAT_SURFACE_CHANNELS } = require('../ipc-channels');
const { isTrustedSender } = require('./utils/trust-guard');

function createStorageGate(context) {
  const {
    BrowserWindow,
    app,
    dialog,
    http,
    https,
    ipcMain,
    log,
    requestAppQuit,
    resolveServerUrl,
    shell,
    windowManager,
    getMainWindow,
    getOriginalUrl,
    // #1：启动恢复上次选择的聊天窗口形态（compact/full）。main.js 注入，缺失时默认 compact。
    getInitialChatSurfaceMode,
    // 球态下 force-show 走真正的恢复（等价点球）。main.js 注入，缺失时回退常规 show。
    restoreReactChatFromBall,
    // Linux 不创建外部 compactChatBallWindow，React Chat 自身会保留为 88x88 毛线球。
    isReactChatSelfMinimizedBallActive,
  } = context;

const STORAGE_GATE_POLL_MS = 1000;
const STORAGE_GATE_READY_POLL_MS = 3000;
const STORAGE_GATE_REQUEST_TIMEOUT_MS = 2500;
const REACT_CHAT_FULL_SWITCH_REVEAL_DELAY_MS = Number(windowManager?.REACT_CHAT_FULL_SWITCH_REVEAL_DELAY_MS) || 180;
let storageStartupSnapshot = {
  state: 'unknown',
  ready: false,
  source: 'init',
  status: '',
  blockingReason: '',
  updatedAt: 0,
};
let storageGatePollTimer = null;
let storageGatePollInFlight = false;
let storageGatePollingEnabled = false;
let startupReactChatCreated = false;
let petReadyForStartupSatellites = false;
let storageMaintenanceProtectionActive = false;
let storageMaintenanceSatelliteSnapshot = null;
let reloadPetAfterMaintenanceReady = false;

function requestJsonFromBackend(pathname, timeoutMs = STORAGE_GATE_REQUEST_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let urlObj;
    try {
      urlObj = new URL(pathname, getOriginalUrl() || resolveServerUrl('MAIN_SERVER'));
    } catch (e) {
      reject(e);
      return;
    }

    const client = urlObj.protocol === 'https:' ? https : http;
    const req = client.request({
      method: 'GET',
      hostname: urlObj.hostname,
      port: urlObj.port ? Number(urlObj.port) : undefined,
      path: `${urlObj.pathname || '/'}${urlObj.search || ''}`,
      timeout: timeoutMs,
      headers: { Accept: 'application/json' },
    }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        body += chunk;
        if (body.length > 1024 * 1024) {
          req.destroy(new Error('Response too large'));
        }
      });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(body ? JSON.parse(body) : {});
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('timeout', () => req.destroy(new Error('Request timeout')));
    req.on('error', (err) => reject(err));
    req.end();
  });
}

function deriveStorageGateState(payload) {
  const storage = payload && typeof payload.storage === 'object' && payload.storage
    ? payload.storage
    : {};
  const status = String(payload?.lifecycle_state || payload?.status || '').trim();
  const blockingReason = String(storage.blocking_reason || payload?.blocking_reason || '').trim();
  const selectionRequired = !!storage.selection_required || blockingReason === 'selection_required';
  const migrationPending = !!storage.migration_pending || blockingReason === 'migration_pending';
  const recoveryRequired = !!storage.recovery_required || blockingReason === 'recovery_required';

  if (payload?.ready === true && !selectionRequired && !migrationPending && !recoveryRequired) {
    return { state: 'ready', ready: true, status, blockingReason: '' };
  }
  if (migrationPending || status === 'maintenance') {
    return { state: 'maintenance', ready: false, status, blockingReason: blockingReason || 'migration_pending' };
  }
  if (recoveryRequired || status === 'recovery_required') {
    return { state: 'recovery_required', ready: false, status, blockingReason: blockingReason || 'recovery_required' };
  }
  if (selectionRequired || status === 'selection_required' || status === 'migration_required') {
    return { state: 'selection_required', ready: false, status, blockingReason: blockingReason || 'selection_required' };
  }
  if (status === 'starting') {
    return { state: 'checking', ready: false, status, blockingReason: '' };
  }
  return { state: 'checking', ready: false, status, blockingReason };
}

function updateStorageStartupSnapshot(next, source) {
  const prev = storageStartupSnapshot;
  const wasMaintenanceProtected = storageMaintenanceProtectionActive;
  storageStartupSnapshot = {
    ...prev,
    ...next,
    source,
    updatedAt: Date.now(),
  };
  if (
    prev.state !== storageStartupSnapshot.state
    || prev.ready !== storageStartupSnapshot.ready
    || prev.blockingReason !== storageStartupSnapshot.blockingReason
  ) {
    log('[StorageGate] state:', storageStartupSnapshot.state,
      'ready:', storageStartupSnapshot.ready,
      'reason:', storageStartupSnapshot.blockingReason || '-',
      'source:', source);
  }

  if (storageStartupSnapshot.state === 'maintenance'
      || storageStartupSnapshot.blockingReason === 'migration_pending') {
    enterStorageMaintenanceProtection(source);
  } else if (storageStartupSnapshot.ready === true) {
    exitStorageMaintenanceProtection(source, { wasActive: wasMaintenanceProtected });
  }
}

async function refreshStorageStartupSnapshot() {
  const preferStorageStatus = storageMaintenanceProtectionActive
    || storageStartupSnapshot.state === 'maintenance'
    || storageStartupSnapshot.blockingReason === 'migration_pending';

  if (preferStorageStatus) {
    try {
      const payload = await requestJsonFromBackend('/api/storage/location/status');
      updateStorageStartupSnapshot(deriveStorageGateState(payload), 'storage/location/status');
    } catch (storageErr) {
      try {
        const payload = await requestJsonFromBackend('/api/system/status');
        updateStorageStartupSnapshot(deriveStorageGateState(payload), 'system/status');
      } catch (systemErr) {
        updateStorageStartupSnapshot({
          state: 'backend_unreachable',
          ready: false,
          status: '',
          blockingReason: '',
          lastError: `${storageErr.message}; ${systemErr.message}`,
        }, 'probe_error');
      }
    }
    return storageStartupSnapshot;
  }

  try {
    const payload = await requestJsonFromBackend('/api/system/status');
    updateStorageStartupSnapshot(deriveStorageGateState(payload), 'system/status');
  } catch (systemErr) {
    try {
      const payload = await requestJsonFromBackend('/api/storage/location/status');
      updateStorageStartupSnapshot(deriveStorageGateState(payload), 'storage/location/status');
    } catch (storageErr) {
      updateStorageStartupSnapshot({
        state: 'backend_unreachable',
        ready: false,
        status: '',
        blockingReason: '',
        lastError: `${systemErr.message}; ${storageErr.message}`,
      }, 'probe_error');
    }
  }
  return storageStartupSnapshot;
}

function isStorageStartupBlocked() {
  return storageStartupSnapshot.ready !== true;
}

function isStorageMaintenanceProtectionActive() {
  return storageMaintenanceProtectionActive;
}

function getSatelliteVisibilitySnapshot() {
  const getVisible = (fn) => {
    try {
      const win = typeof fn === 'function' ? fn() : null;
      return !!(win && !win.isDestroyed() && win.isVisible());
    } catch (e) {
      return false;
    }
  };
  return {
    reactChat: getVisible(windowManager.getReactChatWindow),
    // full 独立聊天窗口也是受管聊天 surface —— 维护期一并收口，否则后端进维护时 compact 被收、
    // full 还留在前台，两态行为分叉。
    fullChat: getVisible(windowManager.getFullChatWindow),
    subtitle: getVisible(windowManager.getSubtitleWindow),
    agentHud: getVisible(windowManager.getAgentHudWindow),
    jukebox: getVisible(windowManager.getJukeboxWindow),
  };
}

function hideStorageMaintenanceSatellites() {
  const hide = (fn) => {
    try {
      const win = typeof fn === 'function' ? fn() : null;
      if (win && !win.isDestroyed() && win.isVisible()) win.hide();
    } catch (e) { /* ignore */ }
  };
  hide(windowManager.getReactChatWindow);
  // full 用 hideFullChatWindow（会置 _nekoWantHidden）而非裸 hide()：维护若在 full 创建后、
  // ready-to-show 前开始，裸 hide() 是 no-op（窗口还 show:false），随后 pending 的
  // ready-to-show 仍会把 full 显示出来；_nekoWantHidden 让那个延迟回调早退。
  if (typeof windowManager.hideFullChatWindow === 'function') {
    try { windowManager.hideFullChatWindow(); } catch (e) { /* ignore */ }
  } else {
    hide(windowManager.getFullChatWindow);
  }
  hide(windowManager.getSubtitleWindow);
  hide(windowManager.getAgentHudWindow);
  hide(windowManager.getJukeboxWindow);
}

function restoreStorageMaintenanceSatellites(snapshot) {
  if (!snapshot) return;
  const show = (fn, shouldShow) => {
    if (!shouldShow) return;
    try {
      const win = typeof fn === 'function' ? fn() : null;
      if (win && !win.isDestroyed() && !win.isVisible()) win.show();
    } catch (e) { /* ignore */ }
  };
  show(windowManager.getReactChatWindow, snapshot.reactChat);
  // full 与 compact 互斥可见，快照里至多一个为 true，直接各自 show 即可。
  show(windowManager.getFullChatWindow, snapshot.fullChat);
  show(windowManager.getSubtitleWindow, snapshot.subtitle);
  show(windowManager.getAgentHudWindow, snapshot.agentHud);
  show(windowManager.getJukeboxWindow, snapshot.jukebox);
}

function enterStorageMaintenanceProtection(source) {
  if (storageMaintenanceProtectionActive) return;
  storageMaintenanceProtectionActive = true;
  storageMaintenanceSatelliteSnapshot = getSatelliteVisibilitySnapshot();
  log('[StorageGate] 进入维护保护模式, source:', source,
    'snapshot:', JSON.stringify(storageMaintenanceSatelliteSnapshot));
  hideStorageMaintenanceSatellites();
  if (getMainWindow() && !getMainWindow().isDestroyed()) {
    try {
      if (getMainWindow().isMinimized()) getMainWindow().restore();
      if (!getMainWindow().isVisible()) getMainWindow().show();
    } catch (e) { /* ignore */ }
  }
}

function exitStorageMaintenanceProtection(source, { wasActive = storageMaintenanceProtectionActive } = {}) {
  if (!wasActive && !storageMaintenanceProtectionActive) return;
  const snapshot = storageMaintenanceSatelliteSnapshot;
  storageMaintenanceProtectionActive = false;
  storageMaintenanceSatelliteSnapshot = null;
  log('[StorageGate] 退出维护保护模式, source:', source,
    'reloadPet:', reloadPetAfterMaintenanceReady);

  if (reloadPetAfterMaintenanceReady && getMainWindow() && !getMainWindow().isDestroyed()) {
    reloadPetAfterMaintenanceReady = false;
    try {
      log('[StorageGate] 维护保护结束，重新加载 Pet 页面');
      getMainWindow().loadURL(getOriginalUrl());
    } catch (e) {
      log('[StorageGate] Pet reload 失败:', e.message);
    }
  }
  restoreStorageMaintenanceSatellites(snapshot);
}

function focusPetForStorageGate(actionName) {
  log('[StorageGate] 阻止卫星窗口动作:', actionName,
    'state:', storageStartupSnapshot.state,
    'reason:', storageStartupSnapshot.blockingReason || '-');
  if (getMainWindow() && !getMainWindow().isDestroyed()) {
    try {
      if (getMainWindow().isMinimized()) getMainWindow().restore();
      if (!getMainWindow().isVisible()) getMainWindow().show();
      getMainWindow().focus();
    } catch (e) {
      log('[StorageGate] 聚焦 Pet 失败:', e.message);
    }
  }
}

function guardStorageStartupGate(actionName) {
  if (!isStorageStartupBlocked()) return false;
  focusPetForStorageGate(actionName);
  return true;
}

function setReloadPetAfterMaintenanceReady(shouldReload) {
  reloadPetAfterMaintenanceReady = shouldReload === true;
}

function requestPetWsReadyRecheck(trigger) {
  const pet = windowManager.getPetWindow();
  if (!pet || pet.isDestroyed()) return;
  try {
    log('[StorageGate] 请求 Pet 补发 WS READY:', trigger);
    pet.webContents.send('neko:ws-trigger-ready-recheck');
  } catch (e) {
    log('[StorageGate] 请求 WS READY 复查失败:', e.message);
  }
}

function armReactChatWsReadyRecheck(win, trigger) {
  if (!win || win.isDestroyed()) return;
  win.webContents.once('dom-ready', () => {
    requestPetWsReadyRecheck(trigger);
  });
}

// 是否处于「毛线球折叠」态：独立球窗口存在且可见。球只在 minimized-ball 态出现（COLLAPSE_TAKEOVER
// 显示、恢复时隐藏/销毁），所以它是球态的可靠信号。此时对话框是 opacity-0 carrier。
function isCompactChatBallActive() {
  try {
    const ball = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
    return !!(ball && !ball.isDestroyed() && ball.isVisible());
  } catch (e) {
    return false;
  }
}

function isAnyCompactChatBallActive() {
  if (isCompactChatBallActive()) return true;
  try {
    return typeof isReactChatSelfMinimizedBallActive === 'function'
      && isReactChatSelfMinimizedBallActive();
  } catch (e) {
    return false;
  }
}

function ensureReactChatWindow({ focus = false, reason = 'manual', forceShow = false } = {}) {
  if (forceShow && typeof windowManager.setReactChatUserClosed === 'function') {
    windowManager.setReactChatUserClosed(false);
  }
  let win = windowManager.getReactChatWindow();
  if (!forceShow
    && typeof windowManager.isReactChatUserClosed === 'function'
    && windowManager.isReactChatUserClosed()) {
    log('[StorageGate] React Chat 显示被用户关闭状态抑制:', reason);
    return win && !win.isDestroyed() ? win : null;
  }
  const wasFullSurfaceHidden = !!(win && !win.isDestroyed() && win._nekoWantHidden);
  if (wasFullSurfaceHidden
    && typeof windowManager.destroyReactChatWindowForFullSurfaceSwitch === 'function'
    && windowManager.destroyReactChatWindowForFullSurfaceSwitch()) {
    win = null;
  }
  // 揭示 compact 即解除「已切到 full」的抑制旗标（与 showFullChatWindow 置位对称）：
  // 否则切到 full 再切回 compact 时，残留旗标会让后续 pending auto-show 被错误早退。
  if (win && !win.isDestroyed()) win._nekoWantHidden = false;
  if (!win || win.isDestroyed()) {
    log('[StorageGate] 创建 React Chat:', reason);
    win = windowManager.createReactChatWindow(getOriginalUrl(), {
      isPackaged: app.isPackaged,
      log,
    });
    if (win && !win.isDestroyed() && win._deferredUrl) {
      armReactChatWsReadyRecheck(win, `ensure:${reason}`);
      win.loadURL(win._deferredUrl);
    }
    return win;
  }

  if (process.platform === 'linux'
    && typeof windowManager.isReactChatAutoShowSuppressed === 'function'
    && windowManager.isReactChatAutoShowSuppressed()) {
    log('[StorageGate] React Chat 显示被模型管理隐藏状态抑制:', reason);
    return win;
  }

  // #179-1 force-show（托盘「打开对话框」）命中毛线球态：外部球路径下对话框是
  // opacity-0 carrier；Linux self-ball 路径下 React Chat 自身是可见 88x88 折叠球。
  // 两者都会骗过下面的 !isVisible() 判断 → 只 focus 折叠窗口、对话框不揭示。
  // 这里改走「等价点球」的真正恢复（收球 + doExpand/直接恢复到 compact）。
  // 仅 forceShow 路径拦截，其余调用方（F6/focus 热键自走 preload）不受影响。
  if (forceShow && isAnyCompactChatBallActive()) {
    log('[StorageGate] force-show 命中毛线球态 → 走真正的恢复（等价点球）:', reason);
    let routed = false;
    if (typeof restoreReactChatFromBall === 'function') {
      try {
        routed = restoreReactChatFromBall();
      } catch (e) {
        log('[StorageGate] 球态恢复失败，回退常规 show:', e.message);
      }
    }
    if (routed) {
      if (focus) {
        try { win.focus(); } catch (e) { /* ignore */ }
      }
      return win;
    }
    // 路由失败（恢复函数缺失 / chat 不可用）→ 落到下面常规 show 兜底。
  }

  let compactRevealDelay = 50;
  let wasVisualParked = false;
  if (typeof windowManager.restoreReactChatVisualAfterFullSurfaceSwitch === 'function') {
    wasVisualParked = windowManager.restoreReactChatVisualAfterFullSurfaceSwitch();
    if (wasVisualParked) compactRevealDelay = REACT_CHAT_FULL_SWITCH_REVEAL_DELAY_MS;
  } else if (typeof windowManager.restoreReactChatInputShapeAfterFullSurfaceSwitch === 'function') {
    windowManager.restoreReactChatInputShapeAfterFullSurfaceSwitch();
  }
  const requestCompactSurfaceRestore = () => {
    if (!wasVisualParked) return;
    [0, 40, 120, 260].forEach((delay) => {
      const timer = setTimeout(() => {
        if (!win || win.isDestroyed()) return;
        try {
          if (win.webContents && !win.webContents.isDestroyed()) {
            win.webContents.send(CHAT_SURFACE_CHANNELS.RESTORE_COMPACT_SURFACE, { reason });
          }
        } catch (e) { /* ignore */ }
      }, delay);
      try { timer.unref(); } catch (e) { /* ignore */ }
    });
  };
  const revealCompactChatWindow = () => {
    setTimeout(() => {
      if (win && !win.isDestroyed()) {
        try {
          if (win.webContents && !win.webContents.isDestroyed()) win.webContents.invalidate();
        } catch (e) { /* ignore */ }
        win.setOpacity(1);
      }
    }, compactRevealDelay);
  };
  if (wasFullSurfaceHidden && win.isVisible()) {
    try { win.setIgnoreMouseEvents(false); } catch (e) { /* ignore */ }
    if (compactRevealDelay > 50) {
      try { win.setOpacity(0); } catch (e) { /* ignore */ }
      requestCompactSurfaceRestore();
      revealCompactChatWindow();
    } else {
      try { win.setOpacity(1); } catch (e) { /* ignore */ }
    }
  }

  if (!win.isVisible()) {
    win.setOpacity(0);
    win.show();
    // 兜底复位球态可能残留的 pass-through（setIgnoreMouseEvents(true)）：任何路径重新显示对话框
    // 都确保它可接收鼠标，避免「球态下关闭再打开后对话框 click-through 不可交互」。
    try { win.setIgnoreMouseEvents(false); } catch (e) { /* ignore */ }
    if (focus) {
      try { win.focus(); } catch (e) { /* ignore */ }
    }
    if (process.platform === 'darwin') {
      win.setAlwaysOnTop(true, 'floating');
    }
    requestCompactSurfaceRestore();
    revealCompactChatWindow();
    requestPetWsReadyRecheck(`show:${reason}`);
  } else if (focus) {
    try { win.focus(); } catch (e) { /* ignore */ }
    requestPetWsReadyRecheck(`focus:${reason}`);
  }
  return win;
}

function maybeCreateStartupReactChat() {
  if (startupReactChatCreated) return;
  if (!petReadyForStartupSatellites) return;
  if (isStorageStartupBlocked()) return;
  startupReactChatCreated = true;
  // #1：恢复上次选择的聊天窗口形态。若上次是 full，**只创建 full 独立窗口**，compact 留待用户
  // 切回时由 ensureReactChatWindow 懒建 —— 不能在这里先建 compact 再 hide，因为 compact 的
  // 显示是异步的（ready-to-show / did-finish-load 才 show），同步 hide 之后它又会把自己显示
  // 出来，导致 full + compact 两个输入框同时出现。
  const initialMode = typeof getInitialChatSurfaceMode === 'function'
    ? getInitialChatSurfaceMode() : 'compact';
  if (initialMode === 'full' && typeof windowManager.showFullChatWindow === 'function') {
    log('[StorageGate] 启动恢复聊天窗口形态: full（仅创建 full 独立窗口，compact 懒建）');
    try {
      windowManager.showFullChatWindow(getOriginalUrl(), { log });
      return;
    } catch (e) {
      log('[StorageGate] 启动创建 full 失败，回退 compact:', e.message);
    }
  }
  ensureReactChatWindow({ focus: false, reason: 'storage_ready_startup' });
}

function startStorageGatePolling() {
  storageGatePollingEnabled = true;
  if (storageGatePollTimer) {
    clearTimeout(storageGatePollTimer);
    storageGatePollTimer = null;
  }

  const tick = async () => {
    if (!storageGatePollingEnabled) return;
    if (storageGatePollInFlight) return;
    storageGatePollInFlight = true;
    try {
      await refreshStorageStartupSnapshot();
      maybeCreateStartupReactChat();
    } catch (e) {
      log('[StorageGate] 刷新状态异常:', e.message);
    } finally {
      storageGatePollInFlight = false;
    }

    if (!storageGatePollingEnabled) return;
    const nextInterval = storageStartupSnapshot.ready
      ? STORAGE_GATE_READY_POLL_MS
      : STORAGE_GATE_POLL_MS;
    storageGatePollTimer = setTimeout(tick, nextInterval);
    try { storageGatePollTimer.unref(); } catch (e) { /* ignore */ }
  };

  tick();
}

function stopStorageGatePolling() {
  storageGatePollingEnabled = false;
  if (storageGatePollTimer) {
    clearTimeout(storageGatePollTimer);
    storageGatePollTimer = null;
  }
  storageGatePollInFlight = false;
}

function attachStorageGateToPetWindow(petWindow) {
  startupReactChatCreated = false;
  petReadyForStartupSatellites = false;
  reloadPetAfterMaintenanceReady = false;
  updateStorageStartupSnapshot({
    state: 'checking',
    ready: false,
    status: '',
    blockingReason: '',
  }, 'pet_created');

  const markPetReady = (trigger) => {
    if (petReadyForStartupSatellites) return;
    petReadyForStartupSatellites = true;
    log('[StorageGate] Pet 已可承载卫星窗口放行检查:', trigger);
    maybeCreateStartupReactChat();
  };

  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.webContents.once('did-finish-load', () => markPetReady('did-finish-load'));
    const fallbackTimer = setTimeout(() => markPetReady('timeout'), 15000);
    try { fallbackTimer.unref(); } catch (e) { /* ignore */ }
  }

  startStorageGatePolling();
}

ipcMain.on('neko:storage-location-phase', (_event, payload = {}) => {
  const phase = String(payload.phase || '').trim();
  if (phase !== 'maintenance') return;

  log('[StorageGate] Pet 页面进入存储维护态, reason:', payload.reason || '-');
  updateStorageStartupSnapshot({
    state: 'maintenance',
    ready: false,
    status: 'maintenance',
    blockingReason: 'migration_pending',
    lastError: '',
  }, 'pet_storage_phase');
  startStorageGatePolling();
});

ipcMain.handle('neko:host:pick-directory', async (event, payload = {}) => {
  if (!isTrustedSender(event)) {
    return { cancelled: true, error: 'Untrusted sender' };
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  const startPath = String(payload.startPath || '').trim();
  const options = {
    title: String(payload.title || '').trim() || '选择文件夹',
    properties: ['openDirectory', 'createDirectory'],
  };
  if (startPath) {
    options.defaultPath = startPath;
  }

  try {
    const result = senderWindow && !senderWindow.isDestroyed()
      ? await dialog.showOpenDialog(senderWindow, options)
      : await dialog.showOpenDialog(options);
    if (result.canceled || !result.filePaths || !result.filePaths[0]) {
      return { cancelled: true };
    }
    return {
      cancelled: false,
      selected_root: result.filePaths[0],
    };
  } catch (e) {
    log('[StorageLocation] 原生目录选择器失败:', e.message);
    throw e;
  }
});

ipcMain.handle('neko:host:open-path', async (event, payload = {}) => {
  if (!isTrustedSender(event)) {
    return { ok: false, error: 'Untrusted sender' };
  }
  const targetPath = String(payload.path || '').trim();
  if (!targetPath) {
    return {
      ok: false,
      error: 'Path is required.',
    };
  }

  try {
    const errorMessage = await shell.openPath(targetPath);
    if (errorMessage) {
      return {
        ok: false,
        error: errorMessage,
      };
    }
    return { ok: true };
  } catch (e) {
    log('[HostCapability] 打开路径失败:', e.message);
    return {
      ok: false,
      error: e.message,
    };
  }
});

ipcMain.handle('neko:host:close-window', async (event) => {
  if (!isTrustedSender(event)) {
    return { ok: false, error: 'Untrusted sender' };
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (!senderWindow || senderWindow.isDestroyed()) {
    return { ok: false, error: 'Window is not available.' };
  }

  try {
    if (senderWindow === getMainWindow()) {
      log('[HostCapability] Pet 主窗口请求关闭，退出应用');
      requestAppQuit('host close pet window');
      return { ok: true, action: 'quit_app' };
    }

    senderWindow.close();
    return { ok: true, action: 'close_window' };
  } catch (e) {
    log('[HostCapability] 关闭窗口失败:', e.message);
    return { ok: false, error: e.message };
  }
});

// 最小化当前窗口
ipcMain.handle('neko:host:minimize-window', async (event) => {
  if (!isTrustedSender(event)) {
    return { ok: false };
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (!senderWindow || senderWindow.isDestroyed()) {
    return { ok: false };
  }
  try {
    senderWindow.minimize();
    return { ok: true };
  } catch (e) {
    log('[HostCapability] 最小化窗口失败:', e.message);
    return { ok: false, error: e.message };
  }
});

// 恢复并聚焦当前窗口
ipcMain.handle('neko:host:restore-window', async (event) => {
  if (!isTrustedSender(event)) {
    return { ok: false };
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (!senderWindow || senderWindow.isDestroyed()) {
    return { ok: false };
  }
  try {
    if (senderWindow.isMinimized()) {
      senderWindow.restore();
    }
    senderWindow.show();
    senderWindow.focus();
    return { ok: true };
  } catch (e) {
    log('[HostCapability] 恢复窗口失败:', e.message);
    return { ok: false, error: e.message };
  }
});

// 最大化/恢复当前窗口
ipcMain.handle('neko:host:maximize-window', async (event) => {
  if (!isTrustedSender(event)) {
    return { ok: false, isMaximized: false };
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (!senderWindow || senderWindow.isDestroyed()) {
    return { ok: false, isMaximized: false };
  }
  try {
    if (senderWindow.isMaximized()) {
      senderWindow.unmaximize();
      return { ok: true, isMaximized: false };
    } else {
      senderWindow.maximize();
      return { ok: true, isMaximized: true };
    }
  } catch (e) {
    log('[HostCapability] 最大化/恢复窗口失败:', e.message);
    return { ok: false, isMaximized: false };
  }
});

// 查询窗口是否处于最大化状态
ipcMain.handle('neko:host:is-maximized', async (event) => {
  if (!isTrustedSender(event)) {
    return false;
  }
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  if (!senderWindow || senderWindow.isDestroyed()) {
    return false;
  }
  try {
    return senderWindow.isMaximized();
  } catch (e) {
    return false;
  }
});

  return {
    attachStorageGateToPetWindow,
    ensureReactChatWindow,
    guardStorageStartupGate,
    isStorageMaintenanceProtectionActive,
    maybeCreateStartupReactChat,
    setReloadPetAfterMaintenanceReady,
    startStorageGatePolling,
    stopStorageGatePolling,
  };
}

module.exports = {
  createStorageGate,
};
