const { isTrustedSender } = require('./utils/trust-guard');

function createHotkeyManager(context) {
  const {
    BrowserWindow,
    NEKO_DEFAULT_PORTS,
    TOAST_CHANNELS,
    app,
    createHotkeyWindowDataUrlBuilder,
    createPortSettingsDataUrlBuilder,
    fs,
    getAppConfig,
    getCurrentLanguage,
    getCustomUrlOverrides,
    getIcon,
    getMainWindow,
    getOriginalUrl,
    globalShortcut,
    guardStorageStartupGate,
    ipcMain,
    log,
    onRestoreAllUI,
    path,
    probeUrlReachable,
    resolveServerUrl,
    saveConfig,
    screen,
    setWindowIgnoreMouseEvents,
    setOriginalUrl,
    sendToToastWindow,
    t,
    trayMenuLocales,
  } = context;

  let hotkeyWindow = null;
  let portSettingsWindow = null;
  let lastTutorialProbeTs = 0;
  let lastTutorialProbeResult = false;

  function ensureAppConfig() {
    return getAppConfig();
  }

  // full/compact 互斥：聊天快捷键应作用于当前活跃的聊天 surface。
  // preload 字节一致、DOM id 相同，同一段折叠/展开/聚焦脚本对两者都生效。
  // 优先级：可见的 full 窗口 > 持久化为 full 的 full 窗口 > compact。
  function resolveActiveChatWindow(wm) {
    const cfg = (typeof getAppConfig === 'function') ? getAppConfig() : null;
    const surfaceIsFull = !!(cfg && cfg.chatSurfaceMode === 'full');
    const fullW = (typeof wm.getFullChatWindow === 'function') ? wm.getFullChatWindow() : null;
    const fullUsable = !!(fullW && !fullW.isDestroyed());
    const fullVisible = fullUsable && fullW.isVisible();
    if (fullVisible || (surfaceIsFull && fullUsable)) return fullW;
    return wm.getReactChatWindow();
  }

  const customUrlOverrides = new Proxy({}, {
    get(_target, prop) {
      return getCustomUrlOverrides()[prop];
    },
    set(_target, prop, value) {
      getCustomUrlOverrides()[prop] = value;
      return true;
    },
    ownKeys() {
      return Reflect.ownKeys(getCustomUrlOverrides());
    },
    getOwnPropertyDescriptor() {
      return { enumerable: true, configurable: true };
    },
  });

const getHotkeyDataURL = createHotkeyWindowDataUrlBuilder({
  getCurrentHotkeys: () => currentHotkeys,
  getCurrentLanguage: () => getCurrentLanguage(),
  getDefaultHotkeys: () => DEFAULT_HOTKEYS,
  getHotkeysEnabled: () => hotkeysEnabled,
  getTrayMenuLocales: () => trayMenuLocales,
});
const getPortSettingsDataURL = createPortSettingsDataUrlBuilder({
  getAppConfig: () => getAppConfig(),
  getCurrentLanguage: () => getCurrentLanguage(),
  getDefaultPorts: () => NEKO_DEFAULT_PORTS,
  getTrayMenuLocales: () => trayMenuLocales,
});

const DEFAULT_HOTKEYS = {
  toggleVoiceSession: 'F2',
  toggleScreenShare: 'F3',
  triggerScreenshot: 'F4',
  toggleMute: 'F5',
  toggleReactChatWindow: 'F6',
  focusReactChatInput: 'F7',
  selectGalgameChoiceA: '',
  selectGalgameChoiceB: '',
  selectGalgameChoiceC: '',
  toggleAllUI: 'F8'
};
let currentHotkeys = { ...DEFAULT_HOTKEYS };
let hotkeysEnabled = true; // 快捷键启用状态
let tutorialHotkeysSuppressed = false; // 教程运行期间临时抑制全局快捷键动作
let uiHiddenSnapshot = null; // 一键隐藏全部界面时的可见性快照；为 null 表示未处于隐藏状态

// 把消息模板里的 {hotkey} 占位符替换为当前实际绑定的键位
function formatHotkeyMessage(tmpl, actionName, fallback) {
  const key = (currentHotkeys && currentHotkeys[actionName]) || fallback || '';
  if (typeof tmpl !== 'string') return '';
  return tmpl.replace(/\{hotkey\}/g, key);
}

function isWindowsCompatibilityModeActive() {
  if (process.platform !== 'win32') return false;
  return process.env.NEKO_COMPATIBILITY_MODE === '1'
    || process.argv.includes('--disable-gpu-compositing')
    || process.argv.includes('--disable-direct-composition');
}

function setTutorialHotkeysSuppressed(active, reason = '') {
  const next = !!active;
  if (tutorialHotkeysSuppressed === next) return tutorialHotkeysSuppressed;
  tutorialHotkeysSuppressed = next;
  if (!next) {
    lastTutorialProbeTs = 0;
    lastTutorialProbeResult = false;
  }
  log(next ? '教程进行中，已临时抑制全局快捷键' : '教程已结束，已恢复全局快捷键动作', reason || '');
  return tutorialHotkeysSuppressed;
}

const TUTORIAL_HOTKEY_PROBE_SCRIPT = `
  (function(){
    try {
      // test-harness fingerprint, not used in logic
      var marker = '__nekoHotkeyTutorialProbe';
      if (window.isInTutorial === true) return true;
      if (window.universalTutorialManager && window.universalTutorialManager.isTutorialRunning === true) return true;
      if (typeof window.isNekoShortcutBlockedByTutorial === 'function'
          && window.isNekoShortcutBlockedByTutorial()) return true;
      if (window.YuiGuideCommon
          && typeof window.YuiGuideCommon.isNekoShortcutBlockedByTutorial === 'function'
          && window.YuiGuideCommon.isNekoShortcutBlockedByTutorial()) return true;
      var body = document && document.body;
      var root = document && document.documentElement;
      var hasClass = function (node, className) {
        return !!(node && node.classList && node.classList.contains(className));
      };
      return hasClass(body, 'yui-guide-home-ui-suppressed')
        || hasClass(body, 'yui-guide-input-shield-active')
        || hasClass(body, 'yui-guide-standalone-input-shield-active')
        || hasClass(body, 'yui-guide-chat-buttons-disabled')
        || hasClass(body, 'yui-guide-compact-chat-fixed')
        || hasClass(body, 'yui-taking-over')
        || hasClass(body, 'yui-guide-home-driver-hidden')
        || (function () {
          if (typeof document.querySelectorAll !== 'function') return false;
          var selectors = ['.yui-guide-overlay', '.yui-guide-stage', '.driver-overlay', '.driver-popover'];
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
          return false;
        })()
        || hasClass(root, 'yui-guide-plugin-dashboard-running')
        || hasClass(body, 'yui-guide-plugin-dashboard-running');
    } catch (_) {
      return false;
    }
  })();
`;
const TUTORIAL_HOTKEY_PROBE_TIMEOUT_MS = 300;
const TUTORIAL_HOTKEY_PROBE_TTL_MS = 150;

function collectTutorialHotkeyProbeWindows() {
  const windows = [];
  const seen = new Set();
  const add = (win) => {
    if (!win || typeof win.isDestroyed !== 'function' || win.isDestroyed() || !win.webContents) return;
    if (seen.has(win)) return;
    seen.add(win);
    windows.push(win);
  };

  add(getMainWindow && getMainWindow());
  try {
    const wm = require('../window-manager');
    if (wm && typeof wm.getPetWindow === 'function') add(wm.getPetWindow());
    if (wm && typeof wm.getReactChatWindow === 'function') add(wm.getReactChatWindow());
    if (wm && typeof wm.getFullChatWindow === 'function') add(wm.getFullChatWindow());
  } catch (_) {}
  return windows;
}

async function isTutorialActiveInRenderer(win) {
  if (!win || win.isDestroyed() || !win.webContents || typeof win.webContents.executeJavaScript !== 'function') {
    return false;
  }
  try {
    if (typeof win.webContents.isLoading === 'function' && win.webContents.isLoading()) {
      return false;
    }
  } catch (_) {}
  try {
    const probePromise = win.webContents.executeJavaScript(TUTORIAL_HOTKEY_PROBE_SCRIPT);
    let timeoutHandle;
    const timeoutPromise = new Promise((_, reject) => {
      timeoutHandle = setTimeout(() => reject(new Error('Tutorial hotkey probe timed out')), TUTORIAL_HOTKEY_PROBE_TIMEOUT_MS);
    });
    const result = await Promise.race([probePromise, timeoutPromise]);
    clearTimeout(timeoutHandle);
    return Boolean(result);
  } catch (_) {
    return false;
  }
}

async function shouldSuppressHotkeyForTutorial() {
  if (tutorialHotkeysSuppressed) return true;
  const now = Date.now();
  if (now - lastTutorialProbeTs < TUTORIAL_HOTKEY_PROBE_TTL_MS) {
    return lastTutorialProbeResult;
  }
  const windows = collectTutorialHotkeyProbeWindows();
  const activeByWindow = await Promise.all(windows.map((win) => isTutorialActiveInRenderer(win)));
  const shouldSuppress = activeByWindow.includes(true);
  lastTutorialProbeTs = now;
  lastTutorialProbeResult = shouldSuppress;
  return shouldSuppress;
}

async function runHotkeyAction(actionName, callback) {
  if (await shouldSuppressHotkeyForTutorial()) {
    log('快捷键忽略：教程进行中:', actionName);
    return;
  }
  callback();
}

function isRendererReady(win) {
  if (!win || win.isDestroyed() || !win.webContents) return false;
  try {
    const url = win.webContents.getURL();
    return !!url && !win.webContents.isLoading();
  } catch (e) {
    return false;
  }
}

function requestScreenshotFromReactChatWindow(win, fallback) {
  if (!win || win.isDestroyed() || !win.webContents) return false;
  const runFallback = typeof fallback === 'function' ? fallback : () => {};
  try {
    if (!win.isVisible()) {
      win.show();
    }
    try { win.focus(); } catch (e) { /* ignore */ }
    const script = `
      (function(){
        try {
          if (window.appButtons && typeof window.appButtons.captureScreenshotToPendingList === 'function') {
            window.appButtons.captureScreenshotToPendingList();
            return true;
          }
        } catch (e) {
          try { console.warn('[Hotkey] React Chat screenshot failed:', e); } catch (_) {}
        }
        return false;
      })();
    `;
    const executeWithFallback = () => {
      try {
        win.webContents.executeJavaScript(script)
          .then((handled) => {
            if (!handled) runFallback();
          })
          .catch(() => runFallback());
      } catch (e) {
        runFallback();
      }
    };
    if (!isRendererReady(win)) {
      try {
        let settled = false;
        let finishHandler;
        let failHandler;
        const settle = (handler) => {
          if (settled) return;
          settled = true;
          try {
            if (typeof win.webContents.removeListener === 'function') {
              win.webContents.removeListener('did-finish-load', finishHandler);
              win.webContents.removeListener('did-fail-load', failHandler);
            }
          } catch (e) { /* ignore */ }
          handler();
        };
        finishHandler = () => settle(executeWithFallback);
        failHandler = () => settle(runFallback);
        win.webContents.once('did-finish-load', finishHandler);
        win.webContents.once('did-fail-load', failHandler);
      } catch (e) {
        return false;
      }
      return true;
    }
    executeWithFallback();
    return true;
  } catch (e) {
    log('React Chat 截图快捷键失败:', e.message);
    return false;
  }
}

// 捕获当前 UI 可见性快照（仅记录"当时可见"的窗口，后续恢复时只还原这些）
function captureUISnapshot() {
  const wm = require('../window-manager');
  const getVisible = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed() || !w.isVisible()) return false;
      // opacity 0 的窗口不计入 reactChat（=「真正可见的展开对话框」）：毛线球折叠时对话框
      // carrier 被 dim 成 opacity 0 但仍 isVisible()=true（Win32）。它由下面 reactChatDimmed
      // 单独记一位 —— 既要 hide-all 一并把它藏掉（否则 setOpacity(0) 不移除 hit-testing，残留的
      // 88px carrier 在球被藏后仍吞点击），又要 restore-all 把它回填到 opacity 0（回到隐身
      // carrier 态，而非被 showWithFadeIn 拉回 1 露出 88px 对话框）。
      // Linux setOpacity no-op → getOpacity 恒 1 → carrier 落在 reactChat（可见）而非
      // reactChatDimmed，与 Linux「折叠后对话框仍可见」的降级现状一致，行为不变。
      // 兼容模式下 dim 用 setShape(1x1) 而非 setOpacity(0)，getOpacity 仍为 1，
      // 但窗口实际被裁到 1x1 不可见——用 _nekoCompatDimmedByShape 标记识别。
      if (w._nekoCompatDimmedByShape) return false;
      const op = typeof w.getOpacity === 'function' ? w.getOpacity() : 1;
      return op > 0.01;
    } catch (e) { return false; }
  };
  // 球态对话框 carrier：visible 但 opacity≤0.01（或兼容模式下 shape-dimmed）。单独记一位，原因见上。
  const getDimmedCarrier = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed() || !w.isVisible()) return false;
      if (w._nekoCompatDimmedByShape) return true;
      const op = typeof w.getOpacity === 'function' ? w.getOpacity() : 1;
      return op <= 0.01;
    } catch (e) { return false; }
  };
  const ballVisible = getVisible(() => (wm.getWindows ? wm.getWindows().compactChatBall : null)) ||
    !!(typeof wm.isCompactChatBallTemporarilyHidden === 'function' && wm.isCompactChatBallTemporarilyHidden());
  return {
    pet: getVisible(wm.getPetWindow),
    reactChat: getVisible(wm.getReactChatWindow),
    // full 独立聊天窗口：切到 full 态后按 F8 也要一起藏/还原，否则 full 留在前台、hide-all 语义被打穿。
    fullChat: getVisible(wm.getFullChatWindow),
    // 球态的 opacity-0 对话框 carrier（与 reactChat 互斥）。hide 时一并藏掉移除 hit-testing，
    // restore 时回填 opacity 0 回到隐身 carrier。
    // 必须 gate 在「独立球确实可见」：否则正常 show 路径（ensureReactChatWindow 先 setOpacity(0)
    // 再 50ms 淡入）的瞬时 opacity-0 会被误判为 carrier —— F8 恰落在该淡入窗口期且无球时，
    // restore 会走 showDimmedCarrier 把 chat 留在 opacity-0 click-through，又没有球可点。
    reactChatDimmed: ballVisible && getDimmedCarrier(wm.getReactChatWindow),
    // minimized 态的独立毛线球窗口也算可见 UI，hide-all 要一起藏（否则别的都藏了球还在）
    compactChatBall: ballVisible,
    subtitle: getVisible(wm.getSubtitleWindow),
    subtitleSettings: getVisible(() => (wm.getWindows ? wm.getWindows().subtitleSettings : null)),
    agentHud: getVisible(wm.getAgentHudWindow),
    jukebox: getVisible(wm.getJukeboxWindow)
  };
}

// 根据快照隐藏当时可见的所有 UI 窗口（toast 不在隐藏集合内）
function applyHideAllUI(snapshot) {
  const wm = require('../window-manager');
  const isCompat = isWindowsCompatibilityModeActive();

  // 兼容模式 CSS 淡出 + setShape 物理隔离（避免 setOpacity 触发 DWM 合成层损坏）。
  // 非兼容模式照旧走 fadeOutAndHide（setOpacity 动画）。
  const hide = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed() || !w.isVisible()) return;
      if (isCompat && typeof w.setShape === 'function') {
        compatFadeOutThenShapeHide(w);
        return;
      }
      fadeOutAndHide(w, 200);
    } catch (e) { /* ignore */ }
  };
  // dim carrier（球态 opacity-0 / setShape(1x1) 对话框）：本就不可见，无需淡出。
  // 非兼容模式直接 hide() 移除 hit-testing，opacity 保持 0（restore 时回填 opacity 0）。
  // 兼容模式下 carrier 已被 setShape(1x1) 裁到不可见，不能调 w.hide() —— hide/show
  // 在 transparent:true + disable-gpu-compositing 窗口上会触发 DWM 合成层损坏，
  // 导致同进程的其他透明窗口（包括毛线球）纹理丢失变白。改用 shapeHideNow 做物理隔离，
  // 仅追加 setIgnoreMouseEvents(true) 禁用 hit-testing。
  const hideDimmedCarrier = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed() || !w.isVisible()) return;
      if (isCompat) {
        shapeHideNow(w);
      } else {
        w.hide();
      }
    } catch (e) { /* ignore */ }
  };
  if (snapshot.pet) hide(wm.getPetWindow);
  if (snapshot.reactChat) hide(wm.getReactChatWindow);
  else if (snapshot.reactChatDimmed) hideDimmedCarrier(wm.getReactChatWindow);
  if (snapshot.fullChat) hide(wm.getFullChatWindow);
  if (snapshot.compactChatBall) hide(() => (wm.getWindows ? wm.getWindows().compactChatBall : null));
  if (snapshot.subtitleSettings) hide(() => (wm.getWindows ? wm.getWindows().subtitleSettings : null));
  if (snapshot.subtitle) {
    try {
      const subtitle = wm.getSubtitleWindow();
      if (subtitle && !subtitle.isDestroyed()) {
        subtitle._nekoPreserveSubtitleSettingsOnHide = true;
      }
    } catch (e) { /* ignore */ }
    hide(wm.getSubtitleWindow);
  }
  if (snapshot.agentHud) hide(wm.getAgentHudWindow);
  if (snapshot.jukebox) hide(wm.getJukeboxWindow);
}

// 根据快照恢复之前可见的窗口
function applyRestoreAllUI(snapshot) {
  const wm = require('../window-manager');
  const isCompat = isWindowsCompatibilityModeActive();
  // 还原一律不抢焦（inactive）：全屏 pet 被 show() 抢焦会 raise 到 screen-saver 同级 z 顶盖住
  // 毛线球。还原 UI 不需要焦点。球能收「按下」不靠应用前台，而靠 showBall 里给球 setFocusable(true)
  // 让球自身可激活（见 window-manager.reassertCompactChatBallTopForRestore）。
  const show = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed()) return;
      // 兼容模式 fade-out 进行中（200ms CSS 动画未结束）：取消 pending shapeHideNow，
      // 恢复 CSS opacity，不走 _nekoF8CompatShapeHidden 分支（flag 尚未设置）。
      if (w._nekoF8FadeOutTimer) {
        clearTimeout(w._nekoF8FadeOutTimer);
        delete w._nekoF8FadeOutTimer;
        restoreWindowMouseEvents(w);
        if (isCompat) compatFadeIn(w);
        return;
      }
      if (w._nekoF8CompatShapeHidden) {
        // 兼容模式恢复：先 setShape([]) 恢复尺寸 + invalidate，再 CSS 淡入
        try { if (typeof w.setShape === 'function') w.setShape([]); } catch (e) { /* ignore */ }
        w._nekoF8CompatShapeHidden = false;
        restoreWindowMouseEvents(w);
        try {
          if (w.webContents && !w.webContents.isDestroyed()) w.webContents.invalidate();
        } catch (e) { /* ignore */ }
        if (isCompat) compatFadeIn(w);
        return;
      }
      if (!w.isVisible()) showWithFadeIn(w, 200, true);
    } catch (e) { /* ignore */ }
  };
  // dim carrier 回填：非兼容模式 setOpacity(0) + showInactive（回到隐身 carrier 态），不淡入到 1
  // —— 否则会在球后/旁露出 88px 对话框。兼容模式用 setShape(1x1) 恢复 dim 状态，避免
  // setOpacity 触发 DWM bug。并幂等兜底 setIgnoreMouseEvents(true)：球态 carrier
  // 不吃鼠标，点击穿透到球（球可点不再依赖 z-order）—— dim 时已设，这里防御性再设一次。
  // 退出球态由 window-manager 的 restoreReactChatVisibilityFromMinimize 复位成可接收。
  const showDimmedCarrier = (fn) => {
    try {
      const w = typeof fn === 'function' ? fn() : null;
      if (!w || w.isDestroyed()) return;
      // 兼容模式 fade-out 进行中：取消 pending shapeHideNow，恢复 carrier dim 态。
      if (w._nekoF8FadeOutTimer) {
        clearTimeout(w._nekoF8FadeOutTimer);
        delete w._nekoF8FadeOutTimer;
        try { w.setIgnoreMouseEvents(true); } catch (e) { /* ignore */ }
        // CSS 正在 fade-out，注入脚本把 opacity 拉回 0 回到隐身 carrier 态
        if (isCompat) {
          try {
            const wc = w.webContents;
            if (wc && !wc.isDestroyed()) {
              wc.executeJavaScript('document.documentElement.style.opacity="0";document.documentElement.style.transition="";').catch(() => {});
            }
          } catch (_) {}
        }
        return;
      }
      // 兼容模式 shape-hidden：shapeHideNow 后 isVisible() 仍为 true，
      // 需要走独立分支恢复 dimmed 态（setShape 1x1 + invalidate + setIgnoreMouseEvents）。
      if (w._nekoF8CompatShapeHidden) {
        w._nekoF8CompatShapeHidden = false;
        try {
          if (w._nekoCompatDimmedByShape && typeof w.setShape === 'function') {
            w.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
          }
        } catch (e) { /* ignore */ }
        try { w.setIgnoreMouseEvents(true); } catch (e) { /* ignore */ }
        try {
          if (w.webContents && !w.webContents.isDestroyed()) w.webContents.invalidate();
        } catch (e) { /* ignore */ }
        return;
      }
      if (!w.isVisible()) {
        if (w._nekoCompatDimmedByShape) {
          try {
            if (typeof w.setShape === 'function') {
              w.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
            }
          } catch (e) { /* ignore */ }
        } else {
          try { w.setOpacity(0); } catch (e) { /* ignore */ }
        }
        if (process.platform === 'win32') {
          try { w.setIgnoreMouseEvents(true); } catch (e) { /* ignore */ }
        }
        try { w.showInactive(); } catch (e) { try { w.show(); } catch (e2) { /* ignore */ } }
      }
    } catch (e) { /* ignore */ }
  };
  // 毛线球还原：球要可交互需同时满足两点 ——
  //   (1) 球能收「按下」：球 focusable:false 时点击的第一个 WM_LBUTTONDOWN 被 Windows 吞去激活
  //       下层窗口、球只收到「抬起」→ pointerdown 不触发、拖/点全失效（实测 F8 还原后 hover/up 到
  //       球但无 down）。reassertCompactChatBallTopForRestore 里 setFocusable(true) 让球自身可激活、
  //       直接收 down。
  //   (2) z 在最上：pet/carrier 同为 screen-saver 级，还原期 show 会重排 z。reassert 走
  //       _topCoordinator.applyTo（setAlwaysOnTop screen-saver 重断言 + setIgnoreMouseEvents(false)
  //       + moveTop）把球钉到同级顶。初次 + 多次延迟断言覆盖还原期各窗口的 z 扰动。
  const showBall = (fn) => {
    // 兼容模式下球被 setShape(1x1) 隐藏后恢复时，传 recreateBaseUrl 让 window-manager
    // 销毁旧球 + showCompactChatBallWindow 重建，避免 setShape([]) 后 background-image
    // 纹理丢失导致白球。
    const recreateOpts = isCompat ? {
      recreateBaseUrl: typeof getOriginalUrl === 'function' ? getOriginalUrl() : undefined,
      isPackaged: typeof app !== 'undefined' && app.isPackaged,
    } : undefined;
    const reassert = () => {
      try {
        if (typeof wm.reassertCompactChatBallTopForRestore === 'function') {
          wm.reassertCompactChatBallTopForRestore(recreateOpts);
          return;
        }
        // fallback（理论不走）：window-manager 未导出时退回本地最小置顶
        const w = typeof fn === 'function' ? fn() : null;
        if (!w || w.isDestroyed()) return;
        try { w.setOpacity(1); } catch (e) { /* ignore */ }
        try { w.setIgnoreMouseEvents(false); } catch (e) { /* ignore */ }
        if (!w.isVisible()) { try { w.showInactive(); } catch (e) { /* ignore */ } }
        try { w.moveTop(); } catch (e) { /* ignore */ }
      } catch (e) { /* ignore */ }
    };
    reassert();
    [120, 300, 500].forEach((ms) => {
      const to = setTimeout(reassert, ms);
      try { to.unref(); } catch (e) { /* ignore */ }
    });
  };
  if (snapshot.pet) show(wm.getPetWindow);
  if (snapshot.reactChat) show(wm.getReactChatWindow);
  else if (snapshot.reactChatDimmed) showDimmedCarrier(wm.getReactChatWindow);
  if (snapshot.fullChat) show(wm.getFullChatWindow);
  if (snapshot.compactChatBall) showBall(() => (wm.getWindows ? wm.getWindows().compactChatBall : null));
  if (snapshot.subtitle) show(wm.getSubtitleWindow);
  if (snapshot.subtitleSettings) show(() => (wm.getWindows ? wm.getWindows().subtitleSettings : null));
  if (snapshot.agentHud) show(wm.getAgentHudWindow);
  if (snapshot.jukebox) show(wm.getJukeboxWindow);
}

// 当前是否处于一键隐藏（F8 hide-all）状态。main 的 RESTORE_COMPLETE handler 据此判断
// 「点球恢复落在 hide-all 活跃期」的复活竞态。
function isUIHidden() {
  return !!uiHiddenSnapshot;
}

// 复活竞态折叠：点球后 ~140ms 揭示延迟内按了 F8，迟到的 RESTORE_COMPLETE 在主进程被
// 拦下（对话框 opacity 回 1 但保持隐藏、球被销毁）。此时 preload 侧 restore 其实已完成
// （eMinimized=false、对话框已展开），与快照里记录的「球 + dim carrier」错配。把快照改成
// 「正常对话框 + 无球」，让 F8 还原时直接显示展开的对话框、不再唤球，状态与 preload 一致，
// 避免还原后点球（eMinimized=false）变 no-op 卡死。
function foldBallRestoreIntoHideAllSnapshot() {
  if (!uiHiddenSnapshot) return;
  uiHiddenSnapshot.reactChat = true;
  uiHiddenSnapshot.reactChatDimmed = false;
  uiHiddenSnapshot.compactChatBall = false;
}

// ===== 兼容模式 CSS 淡入淡出（不碰 setOpacity，避免 DWM 合成层损坏） =====
// 球窗口走 IPC 通道（preload 有专用 handler），其余窗口走 executeJavaScript 注入 CSS。

const F8_FADE_DURATION = 200;

// CSS 淡出脚本：给 documentElement 加 transition + 设 opacity:0，transitionend 后
// 调用回调函数名（由主进程通过 ipcRenderer.send 回传 FADE_OUT_DONE）。
const COMPAT_FADE_OUT_SCRIPT = `
(function(){
  var el = document.documentElement;
  if (!el) { try { require('electron').ipcRenderer.send('neko:f8-fade-out-done'); } catch(_) {} return; }
  el.style.transition = 'opacity ${F8_FADE_DURATION}ms ease-out';
  el.style.opacity = '0';
  var done = false;
  function finish(e) {
    if (e && e.propertyName !== 'opacity') return;
    if (done) return;
    done = true;
    el.removeEventListener('transitionend', finish);
    el.style.transition = '';
    try { require('electron').ipcRenderer.send('neko:f8-fade-out-done'); } catch(_) {}
  }
  el.addEventListener('transitionend', finish);
  setTimeout(finish, ${F8_FADE_DURATION + 30});
})();
`;

const COMPAT_FADE_IN_SCRIPT = `
(function(){
  var el = document.documentElement;
  if (!el) return;
  el.style.transition = 'opacity ${F8_FADE_DURATION}ms ease-in';
  el.style.opacity = '1';
  var done = false;
  function finish(e) {
    if (e && e.propertyName !== 'opacity') return;
    if (done) return;
    done = true;
    el.removeEventListener('transitionend', finish);
    el.style.transition = '';
  }
  el.addEventListener('transitionend', finish);
  setTimeout(finish, ${F8_FADE_DURATION + 30});
})();
`;

  // 兼容模式淡出 → setShape 物理隔离。球窗口走 IPC 通道，其余走 executeJavaScript。
  // FADE_OUT_DONE 回调触发物理隔离（见 initF8FadeIpc）。
  function compatFadeOutThenShapeHide(win) {
    if (!win || win.isDestroyed()) return;
    try {
      // 球窗口（58x58）太小，淡出效果不明显且兼容模式下 CSS transition 可能触发
      // background-image 纹理异常，直接瞬间 setShape 隔离。
      const isBall = _isCompactChatBallWindow(win);
      if (isBall) {
        shapeHideNow(win);
        return;
      }
      const wc = win.webContents;
      if (!wc || wc.isDestroyed()) {
        // webContents 不可用，直接物理隔离
        shapeHideNow(win);
        return;
      }
      // 其余窗口走 executeJavaScript CSS 淡出，脚本内自带 FADE_OUT_DONE 回复
      wc.executeJavaScript(COMPAT_FADE_OUT_SCRIPT).catch(() => {
        // executeJavaScript 失败（页面未加载等），直接物理隔离
        shapeHideNow(win);
      });
      // 保底：CSS 动画可能不触发 transitionend（窗口被提前 hide、display:none 等），
      // 超时后强制物理隔离。IPC/executeJavaScript 路径会先到，此为兜底。
      const timer = setTimeout(() => { shapeHideNow(win); }, F8_FADE_DURATION + 80);
      try { timer.unref(); } catch (_) {}
      // FADE_OUT_DONE 回调里会清理此 timer
      win._nekoF8FadeOutTimer = timer;
    } catch (_) {
      shapeHideNow(win);
    }
  }

  // Pet 窗口在 Windows 上初始就是 setIgnoreMouseEvents(true)，由 preload 按模型区域
  // 动态切换。F8 restore 时不能一刀切 false（否则全屏 Pet 吞桌面鼠标），需要回填 true，
  // 并通知 preload 立刻按当前鼠标位置重算，避免 native 状态与 lastIgnoreState 缓存错位。
  function _isPetWindow(w) {
    try {
      const wm = require('../window-manager');
      const pet = wm.getPetWindow();
      return !!(w && pet && !w.isDestroyed() && !pet.isDestroyed() && w.id === pet.id);
    } catch (_) { return false; }
  }

  function restoreWindowMouseEvents(win) {
    if (_isPetWindow(win)) {
      try {
        if (typeof setWindowIgnoreMouseEvents === 'function') {
          setWindowIgnoreMouseEvents(win, true, {}, 'f8-restore-pet');
        } else {
          win.setIgnoreMouseEvents(true);
        }
      } catch (e) { /* ignore */ }
      try {
        if (win.webContents && !win.webContents.isDestroyed()) {
          win.webContents.send('neko:f8-restore-sync-mouse-through');
        }
      } catch (e) { /* ignore */ }
      return;
    }
    try {
      if (typeof setWindowIgnoreMouseEvents === 'function') {
        setWindowIgnoreMouseEvents(win, false, {}, 'f8-restore-ui');
      } else {
        win.setIgnoreMouseEvents(false);
      }
    } catch (e) { /* ignore */ }
  }

  // 立即执行 setShape 物理隔离（幂等：重复调用无害）
  function shapeHideNow(win) {
    if (!win || win.isDestroyed()) return;
    if (win._nekoF8CompatShapeHidden) return; // 已隔离，跳过
    try {
      if (typeof win.setShape === 'function') {
        win.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
      }
    } catch (_) {}
    win._nekoF8CompatShapeHidden = true;
    try {
      if (typeof setWindowIgnoreMouseEvents === 'function') {
        setWindowIgnoreMouseEvents(win, true, {}, 'f8-shape-hide');
      } else {
        win.setIgnoreMouseEvents(true);
      }
    } catch (_) {}
    // 清理保底 timer
    if (win._nekoF8FadeOutTimer) {
      clearTimeout(win._nekoF8FadeOutTimer);
      delete win._nekoF8FadeOutTimer;
    }
  }

  // 兼容模式淡入：窗口已 setShape([]) 恢复尺寸但 CSS opacity 仍为 0。
  // 球窗口不走 CSS 淡入（太小、且兼容模式下 texture 可能异常），由 reassert 侧发 ball-reappear。
  function compatFadeIn(win) {
    if (!win || win.isDestroyed()) return;
    if (_isCompactChatBallWindow(win)) return;
    try {
      const wc = win.webContents;
      if (!wc || wc.isDestroyed()) return;
      wc.executeJavaScript(COMPAT_FADE_IN_SCRIPT).catch(() => { /* ignore */ });
    } catch (_) {}
  }

// 判断窗口是否为独立毛线球窗口
function _isCompactChatBallWindow(win) {
  try {
    const wm = require('../window-manager');
    const ball = wm && wm.getWindows ? wm.getWindows().compactChatBall : null;
    return !!(win && ball && !win.isDestroyed() && !ball.isDestroyed() && win.id === ball.id);
  } catch (_) {
    return false;
  }
}

// 注册 FADE_OUT_DONE 全局 IPC 监听（由 initHotkeyIPC 调用）
function _initF8FadeIpc() {
  ipcMain.on('neko:f8-fade-out-done', (event) => {
    try {
      const win = BrowserWindow.fromWebContents(event.sender);
      if (!win || win.isDestroyed()) return;
      // 窗口已被 restore 恢复（timer 被清、shape 非 hidden）→ 忽略过时的 fade-out 完成信号
      if (!win._nekoF8FadeOutTimer && !win._nekoF8CompatShapeHidden) return;
      shapeHideNow(win);
    } catch (_) {}
  });
}

// 简易不透明度补间：以 ~60fps 步进驱动 BrowserWindow.setOpacity
// 解决 hide()/show() 的硬切感 + 透明窗口恢复时贴旧合成缓冲导致的闪帧
const _opacityAnimToken = new WeakMap();

function _animateOpacity(win, from, to, duration, onDone, token = Symbol('opacity-animation')) {
  if (!win || win.isDestroyed()) { if (onDone) onDone(); return; }
  _opacityAnimToken.set(win, token);
  const startTs = Date.now();
  try { win.setOpacity(from); } catch (e) { /* ignore */ }
  const tick = () => {
    if (!win || win.isDestroyed()) { if (onDone) onDone(); return; }
    if (_opacityAnimToken.get(win) !== token) return;
    const elapsed = Date.now() - startTs;
    const t = Math.min(1, elapsed / Math.max(1, duration));
    const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
    const v = from + (to - from) * eased;
    try { win.setOpacity(v); } catch (e) { /* ignore */ }
    if (t < 1) {
      setTimeout(tick, 16);
    } else {
      try { win.setOpacity(to); } catch (e) { /* ignore */ }
      if (_opacityAnimToken.get(win) === token) {
        _opacityAnimToken.delete(win);
        if (onDone) onDone();
      }
    }
  };
  setTimeout(tick, 16);
}

function fadeOutAndHide(win, duration = 200) {
  if (!win || win.isDestroyed()) return;
  let curOpacity = 1;
  try { curOpacity = typeof win.getOpacity === 'function' ? win.getOpacity() : 1; } catch (e) { /* ignore */ }
  _animateOpacity(win, curOpacity, 0, duration, () => {
    if (!win || win.isDestroyed()) return;
    try { win.hide(); } catch (e) { /* ignore */ }
    // hide 后把 opacity 还原为 1，避免干扰别处走原生 show() 的路径
    try { win.setOpacity(1); } catch (e) { /* ignore */ }
  });
}

// inactive=true 用 showInactive 而非 show：hide-all 还原时不抢焦。否则全屏 pet（与
// 毛线球同为 screen-saver 级）被 show() 抢焦会 raise 到同级 z 顶，盖住刚 moveTop 的球，
// 点击落到全屏 pet 上、球收不到 → 球态 F8 还原后「球无法点/拖」。还原 UI 不需要焦点，
// 一律 inactive 即可消除这个抢焦 raise 扰动。
function showWithFadeIn(win, duration = 200, inactive = false) {
  if (!win || win.isDestroyed()) return;
  const token = Symbol('opacity-animation');
  _opacityAnimToken.set(win, token);
  try { win.setOpacity(0); } catch (e) { /* ignore */ }
  try {
    if (inactive) win.showInactive(); else win.show();
  } catch (e) {
    try { win.show(); } catch (e2) { /* ignore */ }
  }
  // 延后一帧再淡入，给渲染进程一点时间画出新帧，避免"先贴旧缓冲→再画新帧"的闪烁
  setTimeout(() => {
    if (!win || win.isDestroyed()) return;
    if (_opacityAnimToken.get(win) !== token) return;
    _animateOpacity(win, 0, 1, duration, undefined, token);
  }, 32);
}

function focusReactChatInputInWindow(win, delayMs = 0) {
  if (!win || win.isDestroyed()) return;
  const focusScript = `
    (function(){
      try {
        if (typeof window.__nekoFocusReactChatInputFromHotkey === 'function') {
          return window.__nekoFocusReactChatInputFromHotkey();
        }
        var input = document.querySelector('#react-chat-window-shell textarea.composer-input, #react-chat-window-root textarea.composer-input, textarea.composer-input');
        if (!input || input.disabled || input.readOnly) return false;
        input.focus({ preventScroll: true });
        if (typeof input.setSelectionRange === 'function') {
          var len = input.value ? input.value.length : 0;
          input.setSelectionRange(len, len);
        }
        return true;
      } catch (e) {
        return false;
      }
    })();
  `;
  const runFocus = () => {
    if (!win || win.isDestroyed()) return;
    win.webContents.executeJavaScript(focusScript).catch(() => { /* ignore */ });
  };
  if (delayMs > 0) {
    setTimeout(runFocus, delayMs);
  } else {
    runFocus();
  }
}

function selectReactChatGalgameOptionInWindow(win, optionIndex) {
  if (!win || win.isDestroyed()) return;
  const index = Number.isInteger(optionIndex) ? optionIndex : 0;
  const selectScript = `
    (function(){
      try {
        var shell = document.getElementById('react-chat-window-shell');
        if (shell && shell.classList.contains('neko-e-collapsed')) return false;
        var slot = document.querySelector('.composer-galgame-slot:not(.composer-choice-slot).is-open');
        if (!slot) return false;
        var buttons = Array.prototype.slice.call(slot.querySelectorAll('.composer-galgame-option:not(.is-placeholder)'));
        var button = buttons[${index}];
        if (!button || button.disabled || button.getAttribute('aria-hidden') === 'true') return false;
        button.click();
        return true;
      } catch (e) {
        return false;
      }
    })();
  `;
  win.webContents.executeJavaScript(selectScript).catch(() => { /* ignore */ });
}

function triggerGalgameChoiceHotkey(actionName, optionIndex) {
  log('快捷键触发:', actionName);
  if (guardStorageStartupGate(actionName)) return;
  if (uiHiddenSnapshot) {
    log(actionName + ' 忽略：UI 处于隐藏状态');
    return;
  }
  try {
    const wm = require('../window-manager');
    const w = wm.getReactChatWindow();
    if (!w || w.isDestroyed() || !w.isVisible()) return;

    let ready = false;
    try {
      const url = w.webContents.getURL();
      ready = !!url && !w.webContents.isLoading();
    } catch (e) { /* ignore */ }
    if (!ready) return;

    selectReactChatGalgameOptionInWindow(w, optionIndex);
  } catch (err) {
    log(actionName + ' 失败:', err.message);
  }
}

// ===== 系统代理控制 =====
// 应用代理设置（根据配置决定是否使用系统代理）

// ===== 快捷键配置管理 =====
function getHotkeyConfigPath() {
  // 存储在用户数据目录 (Windows: %APPDATA%\n-e-k-o\)
  return path.join(app.getPath('userData'), 'hotkey_config.json');
}

function normalizeLoadedHotkeys(rawHotkeys) {
  const storedHotkeys = rawHotkeys && typeof rawHotkeys === 'object' ? rawHotkeys : {};
  const hasFocusChatInput = Object.prototype.hasOwnProperty.call(storedHotkeys, 'focusReactChatInput');
  const nextHotkeys = { ...DEFAULT_HOTKEYS, ...storedHotkeys };

  // 旧版本默认把“隐藏全部界面”放在 F7。新增 F7 输入框聚焦后，
  // 如果旧配置没有新动作且仍停留在旧默认值，就迁移到新的 F8 默认值。
  if (!hasFocusChatInput && storedHotkeys.toggleAllUI === 'F7') {
    nextHotkeys.toggleAllUI = DEFAULT_HOTKEYS.toggleAllUI;
  }

  return nextHotkeys;
}

function loadHotkeyConfig() {
  const cfgPath = getHotkeyConfigPath();
  try {
    if (fs.existsSync(cfgPath)) {
      const content = fs.readFileSync(cfgPath, 'utf-8');
      const config = JSON.parse(content);
      // 兼容新旧两种格式：新格式 { enabled, hotkeys }，旧格式直接是 keybindings 平铺
      if (config && typeof config === 'object' && config.hotkeys && typeof config.hotkeys === 'object') {
        currentHotkeys = normalizeLoadedHotkeys(config.hotkeys);
        if (typeof config.enabled === 'boolean') hotkeysEnabled = config.enabled;
      } else {
        currentHotkeys = normalizeLoadedHotkeys(config);
      }
      log('快捷键配置已加载:', JSON.stringify(currentHotkeys), 'enabled:', hotkeysEnabled);
    } else {
      currentHotkeys = { ...DEFAULT_HOTKEYS };
      log('使用默认快捷键配置');
    }
  } catch (err) {
    log('加载快捷键配置失败:', err.message);
    currentHotkeys = { ...DEFAULT_HOTKEYS };
  }
  return currentHotkeys;
}

function persistHotkeyConfigToDisk() {
  const cfgPath = getHotkeyConfigPath();
  const payload = { enabled: hotkeysEnabled, hotkeys: currentHotkeys };
  fs.writeFileSync(cfgPath, JSON.stringify(payload, null, 2), 'utf-8');
}

function saveHotkeyConfig(config) {
  try {
    currentHotkeys = { ...config };
    persistHotkeyConfigToDisk();
    log('快捷键配置已保存:', JSON.stringify(config));
    return { success: true };
  } catch (err) {
    log('保存快捷键配置失败:', err.message);
    return { success: false, error: err.message };
  }
}

function saveHotkeyEnabledState() {
  try {
    persistHotkeyConfigToDisk();
    log('快捷键启用状态已保存:', hotkeysEnabled);
  } catch (err) {
    log('保存快捷键启用状态失败:', err.message);
  }
}

// ===== 全局快捷键注册 =====
function registerGlobalHotkeys() {
  // 先注销所有已注册的快捷键
  globalShortcut.unregisterAll();

  const hotkeyActions = {
    toggleVoiceSession: () => {
      log('快捷键触发: toggleVoiceSession');
      if (getMainWindow() && !getMainWindow().isDestroyed()) {
        getMainWindow().webContents.executeJavaScript('window.toggleVoiceSession && window.toggleVoiceSession()');
      }
    },
    toggleScreenShare: () => {
      log('快捷键触发: toggleScreenShare');
      if (getMainWindow() && !getMainWindow().isDestroyed()) {
        getMainWindow().webContents.executeJavaScript('window.toggleScreenShare && window.toggleScreenShare()');
      }
    },
    triggerScreenshot: () => {
      log('快捷键触发: triggerScreenshot');
      const runLegacyScreenshot = () => {
        if (getMainWindow() && !getMainWindow().isDestroyed()) {
          getMainWindow().webContents.executeJavaScript('window.triggerScreenshot && window.triggerScreenshot()');
        }
      };
      if (uiHiddenSnapshot) {
        log('triggerScreenshot 使用 legacy 路径：UI 处于隐藏状态');
        runLegacyScreenshot();
        return;
      }
      if (guardStorageStartupGate('hotkeyTriggerScreenshot')) {
        log('triggerScreenshot 使用 legacy 路径：存储启动门禁阻止 React Chat 路由');
        runLegacyScreenshot();
        return;
      }
      try {
        const wm = require('../window-manager');
        if (process.platform === 'linux'
          && typeof wm.isReactChatAutoShowSuppressed === 'function'
          && wm.isReactChatAutoShowSuppressed()) {
          log('triggerScreenshot 使用 legacy 路径：模型管理隐藏状态');
          runLegacyScreenshot();
          return;
        }
        if (typeof wm.setReactChatUserClosed === 'function') {
          wm.setReactChatUserClosed(false);
        }
        const chatWindow = resolveActiveChatWindow(wm);
        if (requestScreenshotFromReactChatWindow(chatWindow, runLegacyScreenshot)) return;
      } catch (err) {
        log('React Chat 截图快捷键路由失败:', err.message);
      }
      runLegacyScreenshot();
    },
    toggleMute: () => {
      log('快捷键触发: toggleMute');
      if (getMainWindow() && !getMainWindow().isDestroyed()) {
        getMainWindow().webContents.executeJavaScript('window.toggleMicMute && window.toggleMicMute()');
      }
    },
    toggleReactChatWindow: () => {
      log('快捷键触发: toggleReactChatWindow');
      if (guardStorageStartupGate('hotkeyToggleReactChat')) return;
      // 若当前处于一键隐藏状态，F6 不应把对话框单独唤出 —— 用户已明确"藏好全部界面"
      if (uiHiddenSnapshot) {
        log('toggleReactChatWindow 忽略：UI 处于隐藏状态');
        return;
      }
      try {
        const wm = require('../window-manager');
        if (process.platform === 'linux'
          && typeof wm.isReactChatAutoShowSuppressed === 'function'
          && wm.isReactChatAutoShowSuppressed()) {
          log('toggleReactChatWindow 忽略：模型管理隐藏状态');
          return;
        }
        if (typeof wm.setReactChatUserClosed === 'function') {
          wm.setReactChatUserClosed(false);
        }
        const w = resolveActiveChatWindow(wm);
        if (!w || w.isDestroyed()) return;
        // 检查渲染进程是否已就位：延迟加载模式下窗口对象可能已创建但 URL 还没 load
        // 此时直接模拟点击会落在空 DOM 上悄无声息地失败 —— 回退到 show+focus 保底
        let ready = false;
        try {
          const url = w.webContents.getURL();
          ready = !!url && !w.webContents.isLoading();
        } catch (e) { /* ignore */ }
        if (!ready) {
          if (!w.isVisible()) {
            w.show();
            try { w.focus(); } catch (e) { /* ignore */ }
          }
          return;
        }
        // F6 行为：在展开/折叠之间切换（折叠后仍留下 drag-handle 悬浮球），而不是隐藏整个窗口
        //   - 若窗口被彻底隐藏（用户手动关闭过），先显示再确保展开
        //   - 否则直接模拟点击左下角折叠/展开按钮（preload 里的 doCollapse/doExpand）
        const clickMinimize = `
          (function(){
            try { document.getElementById('reactChatWindowMinimizeButton')?.click(); } catch (e) {}
          })();
        `;
        if (!w.isVisible()) {
          w.show();
          try { w.focus(); } catch (e) { /* ignore */ }
          // 如果当前恰好是折叠态，再点一次展开
          w.webContents.executeJavaScript(`
            (function(){
              try {
                var shell = document.getElementById('react-chat-window-shell');
                if (shell && shell.classList.contains('neko-e-collapsed')) {
                  document.getElementById('reactChatWindowMinimizeButton')?.click();
                }
              } catch (e) {}
            })();
          `).catch(() => { /* ignore */ });
        } else {
          w.webContents.executeJavaScript(clickMinimize).catch(() => { /* ignore */ });
        }
      } catch (err) {
        log('toggleReactChatWindow 失败:', err.message);
      }
    },
    focusReactChatInput: () => {
      log('快捷键触发: focusReactChatInput');
      if (guardStorageStartupGate('hotkeyFocusReactChatInput')) return;
      if (uiHiddenSnapshot) {
        log('focusReactChatInput 忽略：UI 处于隐藏状态');
        return;
      }
      try {
        const wm = require('../window-manager');
        if (process.platform === 'linux'
          && typeof wm.isReactChatAutoShowSuppressed === 'function'
          && wm.isReactChatAutoShowSuppressed()) {
          log('focusReactChatInput 忽略：模型管理隐藏状态');
          return;
        }
        if (typeof wm.setReactChatUserClosed === 'function') {
          wm.setReactChatUserClosed(false);
        }
        const w = resolveActiveChatWindow(wm);
        if (!w || w.isDestroyed()) return;

        let ready = false;
        try {
          const url = w.webContents.getURL();
          ready = !!url && !w.webContents.isLoading();
        } catch (e) { /* ignore */ }

        if (!w.isVisible()) {
          w.show();
          try { w.focus(); } catch (e) { /* ignore */ }
          if (!ready) {
            try { w.webContents.once('did-finish-load', () => focusReactChatInputInWindow(w, 120)); } catch (e) { /* ignore */ }
            return;
          }
          if (ready) focusReactChatInputInWindow(w, 120);
          return;
        }

        try { w.focus(); } catch (e) { /* ignore */ }
        if (!ready) {
          try { w.webContents.once('did-finish-load', () => focusReactChatInputInWindow(w, 120)); } catch (e) { /* ignore */ }
          return;
        }
        if (ready) focusReactChatInputInWindow(w);
      } catch (err) {
        log('focusReactChatInput 失败:', err.message);
      }
    },
    selectGalgameChoiceA: () => {
      triggerGalgameChoiceHotkey('hotkeySelectGalgameChoiceA', 0);
    },
    selectGalgameChoiceB: () => {
      triggerGalgameChoiceHotkey('hotkeySelectGalgameChoiceB', 1);
    },
    selectGalgameChoiceC: () => {
      triggerGalgameChoiceHotkey('hotkeySelectGalgameChoiceC', 2);
    },
    toggleAllUI: () => {
      log('快捷键触发: toggleAllUI');
      try {
        if (uiHiddenSnapshot) {
          // 当前已隐藏 —— 恢复
          applyRestoreAllUI(uiHiddenSnapshot);
          uiHiddenSnapshot = null;
          try {
            if (typeof onRestoreAllUI === 'function') onRestoreAllUI();
          } catch (e) {
            log('toggleAllUI restore callback failed:', e.message);
          }
          // 恢复后弹一下提示
          try {
            const texts = trayMenuLocales[getCurrentLanguage()] || trayMenuLocales['en'];
            const message = (texts && texts.uiRestoredHint) || 'UI restored';
            sendToToastWindow(TOAST_CHANNELS.STATUS, { message, duration: 2000 });
          } catch (e) {
            log('toggleAllUI restore toast 发送失败:', e.message);
          }
        } else {
          // 捕获并隐藏
          const snapshot = captureUISnapshot();
          const anyVisible = Object.values(snapshot).some(Boolean);
          if (!anyVisible) {
            // 没有任何可见窗口，什么都不做
            return;
          }
          applyHideAllUI(snapshot);
          uiHiddenSnapshot = snapshot;
          // 展示右上角 toast 提示如何恢复
          try {
            const texts = trayMenuLocales[getCurrentLanguage()] || trayMenuLocales['en'];
            const tmpl = texts && texts.uiHiddenHint
              ? texts.uiHiddenHint
              : 'UI hidden — press {hotkey} to restore';
            const message = formatHotkeyMessage(tmpl, 'toggleAllUI', 'F8');
            sendToToastWindow(TOAST_CHANNELS.STATUS, { message, duration: 2000 });
          } catch (e) {
            log('toggleAllUI toast 发送失败:', e.message);
          }
        }
      } catch (err) {
        log('toggleAllUI 失败:', err.message);
      }
    }
  };

  // 注册每个快捷键
  for (const [action, shortcut] of Object.entries(currentHotkeys)) {
    if (shortcut && hotkeyActions[action]) {
      try {
        const success = globalShortcut.register(shortcut, () => runHotkeyAction(action, hotkeyActions[action]));
        if (success) {
          log(`快捷键已注册: ${shortcut} -> ${action}`);
        } else {
          log(`快捷键注册失败: ${shortcut} -> ${action}`);
        }
      } catch (err) {
        log(`快捷键注册异常: ${shortcut} -> ${action}:`, err.message);
      }
    }
  }
}

// ===== 快捷键管理窗口 =====
function _pushDarkModeToHotkeyWindow(enabled) {
  try {
    if (hotkeyWindow && !hotkeyWindow.isDestroyed()) {
      hotkeyWindow.webContents.send('toggle-dark-mode', !!enabled);
    }
  } catch (e) { /* ignore */ }
}

// ===== 端口设置窗口 =====
function createPortSettingsWindow() {
  if (portSettingsWindow && !portSettingsWindow.isDestroyed()) {
    portSettingsWindow.focus();
    return;
  }

  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const windowWidth = 500;
  const windowHeight = 680;

  portSettingsWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: Math.floor((width - windowWidth) / 2),
    y: Math.floor((height - windowHeight) / 2),
    frame: false,
    transparent: false,
    resizable: false,
    icon: getIcon(),
    title: t('portWindowTitle') + ' - N.E.K.O.',
    webPreferences: {
      preload: path.join(__dirname, 'preload-portsettings.js'),
      sandbox: false, // preload 注入 contextBridge，需关闭 sandbox 以加载相对模块路径
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    }
  });
  // 标记为"设置类"窗口（getWindowZRank 据此归入 rank 4；URL 是 data: 无法靠 URL 匹配）
  portSettingsWindow._nekoKind = 'settings';

  portSettingsWindow.loadURL(getPortSettingsDataURL());

  portSettingsWindow.on('closed', () => {
    portSettingsWindow = null;
  });

  portSettingsWindow.show();
}

function createHotkeyWindow() {
  // 如果窗口已存在，聚焦它
  if (hotkeyWindow && !hotkeyWindow.isDestroyed()) {
    hotkeyWindow.focus();
    return;
  }

  // 打开设置窗口时暂时禁用全局快捷键（避免录入时误触发）
  globalShortcut.unregisterAll();
  log('快捷键设置窗口打开，已暂停全局快捷键');

  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const windowWidth = 480;
  const windowHeight = 640;

  hotkeyWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    x: Math.floor((width - windowWidth) / 2),
    y: Math.floor((height - windowHeight) / 2),
    frame: false,
    transparent: false,
    resizable: false,
    icon: getIcon(),
    title: t('hotkeyWindowTitle') + ' - N.E.K.O.',
    webPreferences: {
      preload: path.join(__dirname, 'preload-hotkey.js'),
      sandbox: false, // preload 注入 contextBridge，需关闭 sandbox 以加载相对模块路径
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    }
  });
  // 标记为"设置类"窗口（getWindowZRank 据此归入 rank 4；URL 是 data: 无法靠 URL 匹配）
  hotkeyWindow._nekoKind = 'settings';

  // 使用 Data URL 加载内嵌 HTML
  hotkeyWindow.loadURL(getHotkeyDataURL(getOriginalUrl(), !!(getAppConfig() && getAppConfig().darkMode)));

  hotkeyWindow.on('closed', () => {
    hotkeyWindow = null;
    // 窗口关闭时，如果快捷键功能已启用，重新注册快捷键
    if (hotkeysEnabled) {
      registerGlobalHotkeys();
      log('快捷键设置窗口关闭，已恢复全局快捷键');
    }
  });

  hotkeyWindow.show();
}

// 初始化快捷键 IPC 处理器
function initHotkeyIPC() {
  _initF8FadeIpc();
  ipcMain.on('hotkey-recording-state', (event, isRecording) => {
    try {
      if (!hotkeyWindow || hotkeyWindow.isDestroyed()) return;
      if (event.sender !== hotkeyWindow.webContents) return;
      hotkeyWindow._nekoAllowNavigationShortcutCapture = !!isRecording;
    } catch (err) {
      log('更新快捷键录入状态失败:', err.message);
    }
  });

  // 获取快捷键配置
  ipcMain.handle('get-hotkey-config', () => {
    return currentHotkeys;
  });

  // 保存快捷键配置（设置窗口打开期间不注册快捷键）
  ipcMain.handle('save-hotkey-config', (event, config) => {
    if (!isTrustedSender(event)) {
      return { ok: false, error: 'Untrusted sender' };
    }
    const result = saveHotkeyConfig(config);
    // 注意：设置窗口打开期间不注册快捷键，关闭窗口时会自动恢复
    return result;
  });

  // 获取快捷键启用状态
  ipcMain.handle('get-hotkeys-enabled', (event) => {
    if (!isTrustedSender(event)) {
      return false;
    }
    return hotkeysEnabled;
  });

  // 切换快捷键启用状态
  ipcMain.handle('toggle-hotkeys-enabled', (event, enabled) => {
    if (!isTrustedSender(event)) {
      return false;
    }
    hotkeysEnabled = enabled;
    saveHotkeyEnabledState();
    if (enabled) {
      // 如果设置窗口已关闭，则注册快捷键
      if (!hotkeyWindow || hotkeyWindow.isDestroyed()) {
        registerGlobalHotkeys();
      }
      log('快捷键功能已启用');
    } else {
      globalShortcut.unregisterAll();
      log('快捷键功能已禁用');
    }
    return { success: true, enabled: hotkeysEnabled };
  });
}

  return {
    areHotkeysEnabled: () => hotkeysEnabled,
    createHotkeyWindow,
    createPortSettingsWindow,
    foldBallRestoreIntoHideAllSnapshot,
    getPortSettingsWindow: () => portSettingsWindow,
    initHotkeyIPC,
    isUIHidden,
    isTutorialHotkeysSuppressed: () => tutorialHotkeysSuppressed,
    loadHotkeyConfig,
    pushDarkModeToHotkeyWindow: _pushDarkModeToHotkeyWindow,
    registerGlobalHotkeys,
    setTutorialHotkeysSuppressed,
  };
}

module.exports = {
  createHotkeyManager,
};
