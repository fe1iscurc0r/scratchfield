function createTopCoordinator(context) {
  const {
    app,
    BrowserWindow,
    getGlobalAlwaysOnTop,
    getLoadingWindow,
    getMainWindow,
    log,
    process,
    windowManager,
  } = context;

// ===== Z-Order 层级策略 =====
// 卡面编辑器：从角色卡 / 模型管理器内部打开，需要覆盖父级管理器
// 卫星窗口（chat / subtitle / agentHUD）+ pet：screen-saver 级（Windows）但周期重断言顺序更早
// 其他弹出窗（api_key / voice_clone / character_card_manager / model_manager 等）：floating 级，与 Pet 同级
// 注：card_maker（卡面编辑器）是从 character_card_manager / model_manager 内部弹出的二级窗口，
// 显式给它 owner-child（parent: parentWin），同时保留更高 top level，避免被父级管理器遮挡。
// character_card_manager / model_manager 本身不再进入本列表，否则 Electron 会表现成资源管理
// 全屏弹窗，压过前端 window.open 传入的 API-like 尺寸。
const FULLSCREEN_POPUP_PATTERNS = ['/card_maker'];
// mini-game (soccer/badminton 等) 子窗口需要“无边框最大化但不置顶”语义：保留 ``frame:false``
// 自绘 chrome（与 pet/chat 视觉一致），启动时 maximize（占工作区但保留任务栏，
// 不进入 OS 全屏），不 alwaysOnTop（让用户可以切走、让 Pet/chat 上浮），加载完成
// 后显式触发一次 Pet/chat moveTop 让猫娘和 chat 浮在 mini-game 上方。
// 与 FULLSCREEN_POPUP_PATTERNS（card_maker 二级弹窗）
// 不同：那条仍 alwaysOnTop。
const NORMAL_FRAMED_POPUP_PATTERNS = ['/soccer_demo', '/badminton_demo'];
const WINDOWED_TOOL_POPUP_PATTERNS = ['/api/agent/openclaw/guide'];

// pathname 精确匹配：避免 URL 的 query/hash 里只要含 mini-game 路径片段就被
// 误认成 mini-game（例如 ``?next=/soccer_demo`` 这种深链）—— CodeRabbit Minor 指出。
function _safePathnameOf(url) {
  if (!url) return '';
  try { return new URL(url).pathname; } catch (_) { return ''; }
}

function isNormalFramedPopup(url) {
  const p = _safePathnameOf(url);
  if (!p) return false;
  return NORMAL_FRAMED_POPUP_PATTERNS.some(
    (pat) => p === pat || p.startsWith(pat + '/'),
  );
}

function isWindowedToolPopup(url) {
  const p = _safePathnameOf(url);
  if (!p) return false;
  return WINDOWED_TOOL_POPUP_PATTERNS.some(
    (pat) => p === pat || p.startsWith(pat + '/'),
  );
}
// Jukebox 子窗口（"管理器"）：rank 3，在 jukebox 之上、角色管理 之下
const JUKEBOX_MANAGER_PATTERNS = ['jukebox/manager'];

/**
 * 根据子窗口 URL 判断其 alwaysOnTop 等级
 * @param {string} url - 子窗口 URL
 * @returns {{ alwaysOnTop: boolean, level: string|undefined }}
 */
function getChildWindowTopLevel(url) {
  if (isWindowedToolPopup(url)) {
    return { alwaysOnTop: false, level: undefined };
  }
  if (FULLSCREEN_POPUP_PATTERNS.some(p => url.includes(p))) {
    return { alwaysOnTop: true, level: 'screen-saver' };
  }
  // 未匹配 FULLSCREEN 的弹出窗（chara_manager / api_key / voice_clone / hotkey /
  // portSettings / feedback 等）：与 Pet 同级（Windows 下 screen-saver）。
  // 历史上这里返回 'floating' 是基于 "Pet 也是 floating" 的假设 —— 旧注释提到
  // "保持 floating 避免被 pet 透明层遮挡导致 DWM 白屏"。自从 Pet 为对抗全屏游戏
  // 升到 screen-saver 后，该假设倒置：级差变成 Pet > 弹窗，反而让 Pet 的透明
  // 全屏覆盖层盖住弹窗，触发 DWM 合成层卡住（弹窗白屏需点一下才渲染）+ 第三方
  // screen-saver 应用能把 floating 级 N.E.K.O 弹窗压过去。修复方案：弹窗与 Pet
  // 同级，OS 自然把新弹窗放到 topmost 带顶部盖住 Pet，不再触发 DWM 遮挡白屏。
  return { alwaysOnTop: true, level: getManagedTopLevel() };
}

/**
 * 计算窗口在 N.E.K.O 内部 Z-order 层级体系中的 rank（0~6，越大越高）。
 *   0 = Pet（模型）
 *   1 = chat / reactChat / subtitle（对话框 / 字幕）
 *   2 = jukebox / agentHud（点歌台 / HUD）
 *   3 = /jukebox/manager（管理器，jukebox 子窗口）
 *   4 = card_maker + 设置类（hotkey/portSettings/feedback，靠 _nekoKind 标记）
 *   5 = Toast（鼠标悬浮文本描述）
 *   null = 不参与 rank 排序（如 loadingWindow、未识别窗口）
 *
 * 用途：周期 reassertion 按 rank 升序 moveTop，结果稳定于"低 rank 在底、高 rank 在顶"，
 * 消除多个 topmost 窗口轮流 moveTop 时的相互抢占抖动。
 *
 * @param {BrowserWindow} win
 * @returns {number|null}
 */
function getWindowZRank(win) {
  if (!win || win.isDestroyed()) return null;
  if (win === getLoadingWindow()) return null;

  // 5 - Toast
  try {
    const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
    if (toast && win === toast) return 5;
  } catch (e) { /* ignore */ }

  // 读 URL 一次，多个分支复用
  let url = '';
  try { url = win.webContents?.getURL?.() || ''; } catch (e) { /* ignore */ }

  // 4 - 设置类（hotkey/portSettings/feedback 用 data:/about: URL，URL 匹配不可靠，靠创建期 tagging）
  if (win._nekoKind === 'settings') return 4;

  // 4 - 卡面编辑器（二级管理弹窗）
  if (url && FULLSCREEN_POPUP_PATTERNS.some(p => url.includes(p))) return 4;

  // 3 - Jukebox 子窗口 /jukebox/manager
  if (url && JUKEBOX_MANAGER_PATTERNS.some(p => url.includes(p))) return 3;

  if (win._nekoKind === 'pluginDashboard') return 4;

  // 2 / 1 / 0 - 受管窗口按身份判定
  try {
    const managed = windowManager.getWindows();
    if (win === managed.subtitleSettings) return 4;
    if (win === managed.jukebox || win === managed.agentHud) return 2;
    if (win === managed.fullChat) return 1;
    if (win === managed.chat || win === managed.subtitle) return 1;
  } catch (e) { /* ignore */ }
  if (win === getMainWindow()) return 0;

  // 其他（未识别窗口）不参与 rank 排序
  return null;
}

function inferManagedWindowKind(win) {
  if (!win || win.isDestroyed()) return null;
  try {
    const managed = windowManager.getWindows();
    if (win === managed.pet) return 'pet';
    if (win === managed.chat) return 'reactChat';
    if (win === managed.compactChatBall) return 'reactChat';
    if (win === managed.subtitle) return 'subtitle';
    if (win === managed.agentHud) return 'agentHud';
    if (win === managed.jukebox) return 'jukebox';
  } catch (e) { /* ignore */ }
  if (win === getMainWindow()) return 'pet';
  return null;
}

function normalizeManagedWindowKind(kind) {
  return kind === 'chat' ? 'reactChat' : kind;
}

/**
 * 判断 Windows 下需要 moveTop + 二次 setAlwaysOnTop 作为 DWM Z-order 兜底的窗口
 * （Chromium 对这类窗口的内部状态缓存会短路重复调用，需强制重发 SetWindowPos）。
 * 包含 Pet / Chat（transparent+frameless）以及用户反馈易被全屏游戏压下的
 * Jukebox / AgentHud。
 */
function needsDwmBump(win) {
  if (process.platform !== 'win32') return false;
  try {
    if (!win || win.isDestroyed()) return false;
    if (win === getMainWindow()) return true; // Pet
    const managed = windowManager.getWindows();
    if (win === managed.chat) return true; // ReactChat / Chat
    if (win === managed.jukebox) return true; // Jukebox（易被全屏游戏压下）
    if (win === managed.agentHud) return true; // AgentHud（易被全屏游戏压下）
    return false;
  } catch {
    return false;
  }
}

/**
 * 判断窗口是否为"闪烁敏感的 transparent 窗口" —— reassertion 中**完全跳过**它们的
 * moveTop，避免合成层重建造成用户可见的闪烁。包含：
 *   · Pet（transparent + 全屏覆盖）：承载 Live2D 模型像素
 *   · chat / reactChat（transparent + frameless）：对话气泡内容
 *   · agentHud（transparent + frameless）：HUD 内容
 *   · toast（transparent + 全屏覆盖）：通知层 —— 虽然本身内容多透明不闪，但对它
 *     moveTop 会让其他 topmost 窗口（尤其 chat）被动下降一位 → DWM 通知那些
 *     被影响的 transparent 窗口重建合成层 → chat 等窗口发生可见闪烁。
 *
 * 这些 transparent 窗口 alwaysOnTop 标志在创建时已设并保持；它们的相对 Z-order 由
 * 更高 rank 的 non-transparent 窗口 moveTop 时自动被动下降处理。Toast 的 screen-saver
 * 级最顶由创建时的 setAlwaysOnTop + 通知显示路径的显式 moveTop 共同维持，不需要周期
 * 兜底（取消 tick 里的 moveTop(toast) 是根治 chat 闪烁的关键）。
 *
 * non-transparent 窗口（jukebox / 管理弹窗 / hotkey/portSettings/feedback / subtitle）
 * 的 moveTop 不闪，正常参与 reassertion。
 */
function isTransparentWindow(win) {
  if (!win || win.isDestroyed()) return false;
  if (win === getMainWindow()) return true; // Pet
  try {
    const managed = windowManager.getWindows();
    if (win === managed.chat || win === managed.agentHud) return true;
  } catch (e) { /* ignore */ }
  try {
    const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
    if (toast && win === toast) return true;
  } catch (e) { /* ignore */ }
  return false;
}

/**
 * Pet / 受管卫星窗口在当前平台应使用的 alwaysOnTop level。
 * Windows 下用 'screen-saver' —— Electron 暴露的最高级别，能对抗无边框全屏游戏
 * 在帧循环中反复调用 SetWindowPos(HWND_TOPMOST) 造成的 Z-order 抢占。
 * macOS / Linux 用 'floating' —— 避免叠加在系统菜单 / Dock 之上。
 *
 * 历史注记：window-manager.js 旧注释曾提到 'screen-saver' 会干扰 Windows DWM 视频
 * overlay 合成，实际测试下该冲突极少重现，换来的全屏游戏覆盖能力收益更大。若后续
 * 发现 Live2D 渲染异常可退回 'floating' 或引入用户配置细分。
 */
function getManagedTopLevel(kind) {
  if (process.platform === 'win32') return 'screen-saver';
  if (process.platform === 'darwin' && kind === 'reactChat') {
    return 'modal-panel';
  }
  return 'floating';
}

/**
 * 针对单个窗口应用当前全局置顶状态。
 * - Toast 永远 screen-saver（独立于全局开关）
 * - FULLSCREEN_POPUP_PATTERNS（card_maker）：screen-saver
 *   二级弹窗必须 >= Pet 级别；周期重断言里在 Pet 之后 moveTop 保证浮于 Pet 上
 * - 其他弹出窗（api_key/voice_clone/chara_manager/hotkey/portSettings/feedback 等）：
 *   走 getManagedTopLevel() —— Windows 下 screen-saver，与 Pet 同级，防止 Pet 的透明
 *   全屏覆盖层挡住 DWM 合成造成白屏 + 防止被第三方 screen-saver 应用压过去
 * - Pet / 受管卫星窗口（kind 指定）：Windows 下一律 screen-saver
 * - 其他未识别窗口：沿用 defaultLevel（默认 floating）
 * - Windows 兜底：先 false 再 true 绕过 Chromium state cache；对 Pet/ReactChat 再补一次
 *
 * @param {BrowserWindow} win
 * @param {{kind?: string, defaultLevel?: string}} classification
 */
function applyTopOn(win, classification = {}) {
  if (!win || win.isDestroyed()) return;
  if (win === getLoadingWindow()) return;

  // Toast：永远 screen-saver，独立于全局开关
  try {
    const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
    if (toast && win === toast) {
      try { win.setAlwaysOnTop(true, 'screen-saver'); } catch (e) { /* ignore */ }
      return;
    }
  } catch (e) { /* ignore */ }

  // mini-game (soccer_demo 等 normal-framed) 窗口显式不参与 alwaysOnTop 体系。
  //
  // 关键：必须用窗口对象上的 ``_nekoForceNotTopMost`` 标记，而不是 ``getURL()``。
  // CR Major 指出：``app.on('browser-window-created')`` 钩子里的
  // ``setImmediate(firstApply)`` 可能在 ``loadURL`` 还没产生 ``did-navigate`` 之前
  // 就跑，那时 ``win.webContents.getURL()`` 仍是空串，``isNormalFramedPopup('')``
  // 返回 false → mini-game 会先被当成普通弹窗 ``setAlwaysOnTop(true,...)``，等
  // ``did-create-window`` 后续修正回去——这刚好把这条 PR 想避免的"立即全局重断
  // 言"带回来。改成读 ``did-create-window`` 时预存的 boolean 标记，URL 时序无关。
  if (win._nekoForceNotTopMost === true) {
    try {
      if (win.isAlwaysOnTop()) win.setAlwaysOnTop(false);
    } catch (e) { /* ignore */ }
    return;
  }

  // 系统托盘菜单打开时，Pet 需要暂时退出置顶窗口带，避免盖住系统原生菜单。
  if (win === getMainWindow() && isSystemMenuOcclusionGuardActive()) {
    demotePetForSystemMenu();
    return;
  }

  // 分类决定 level
  let level;
  let forceNonTop = false;
  const managedKind = normalizeManagedWindowKind(classification.kind || inferManagedWindowKind(win));
  if (managedKind) {
    // 受管窗口（pet/chat/subtitle/agentHud/jukebox/reactChat）
    // 统一走 getManagedTopLevel(kind) —— Windows 下为 'screen-saver'，对抗全屏游戏抢占；
    // macOS 下 React Chat 高于 Pet，避免紧凑聊天框被模型窗口压住。
    // 忽略 window-manager 传入的 defaultLevel='floating'，保持 main.js 为唯一策略所有者
    level = getManagedTopLevel(managedKind);
  } else {
    // 未指定 kind（弹出子窗口 / 未识别窗口），按 URL 分类
    const url = (() => {
      try { return win.webContents?.getURL?.() || ''; } catch { return ''; }
    })();
    const c = getChildWindowTopLevel(url);
    if (c.alwaysOnTop === false) {
      forceNonTop = true;
    } else if (c.alwaysOnTop && c.level) {
      level = c.level;
    } else {
      // getChildWindowTopLevel 当前对所有 URL 都返回 alwaysOnTop:true + level，
      // 此分支仅作为兜底（如未来改签名才可能走到）
      level = c.level || classification.defaultLevel || getManagedTopLevel();
    }
  }

  // **幂等 + 最小副作用**：仅当窗口当前 alwaysOnTop 状态与期望不一致时才调用
  // setAlwaysOnTop，且不再做 false→true toggle、也不主动 moveTop。
  // 原因：setAlwaysOnTop(true, level) 等同 SetWindowPos(HWND_TOPMOST) —— 默认会把
  // 窗口塞到 topmost 带顶部，挤已有 topmost 窗口（如 chat）下降一位 → DWM 重建那些
  // 被挤窗口的合成层 → chat 等 transparent 窗口闪烁。每次 chara_manager / jukebox /
  // manager 等 non-transparent 弹窗经 browser-window-created 路径触发 applyTopOn 时，
  // 都会让 chat 闪一次。改为幂等后，新窗口创建时 OS 已自然把它放到 topmost 带顶
  // （因为它刚激活），applyTopOn 检测到状态已正确就不再发 SetWindowPos。
  // moveTop 也去除：reassertion timer 在需要重排时会调，applyTopOn 不重复操作。
  const wantsTop = forceNonTop ? false : getGlobalAlwaysOnTop();
  let currentlyTop = false;
  try { currentlyTop = !!win.isAlwaysOnTop(); } catch (e) { /* ignore */ }

  log(`[applyTopOn] winId=${win.id} wantsTop=${wantsTop} currentlyTop=${currentlyTop} level=${level}`);
  try {
    if (wantsTop && !currentlyTop) {
      win.setAlwaysOnTop(true, level);
      _zOrderDirty = true;
      log(`[applyTopOn] setAlwaysOnTop(true,'${level}') called → isAlwaysOnTop()=${win.isAlwaysOnTop()}`);
    } else if (!wantsTop && currentlyTop) {
      win.setAlwaysOnTop(false);
      _zOrderDirty = true;
      log(`[applyTopOn] setAlwaysOnTop(false) called → isAlwaysOnTop()=${win.isAlwaysOnTop()}`);
    } else {
      log(`[applyTopOn] no-op (state already consistent)`);
    }
  } catch (e) {
    log(`[applyTopOn] ERROR: ${e.message}`);
  }
}

// ===== 全屏游戏兼容：周期性 Z-order 重断言 =====
// 无边框全屏游戏常在帧循环里反复 SetForegroundWindow + HWND_TOPMOST 抢占 Z-order，
// 即便我们的 WS_EX_TOPMOST 标志仍在，实际 Z-order 也会被压下。
//
// 两档强度：
//   轻量模式（app 前景）：win.setAlwaysOnTop(true, level) + moveTop()
//     · Chromium 对 setAlwaysOnTop(true, X) 在 state 已 true 时会短路不调 SetWindowPos，
//       此模式主要靠 moveTop(SetWindowPos(HWND_TOP)) 在 topmost 带内重排 —— 对一般窗口
//       的 Z-order 维持足够，且不闪烁。
//   强力模式（app 失焦，典型即全屏游戏抢焦）：先 setAlwaysOnTop(false) 再
//     setAlwaysOnTop(true, level) 再 moveTop()。
//     · 先 false 绕过 Chromium state cache，强制真实调用 SetWindowPos(HWND_NOTOPMOST)，
//     · 再 true 调用 SetWindowPos(HWND_TOPMOST) 把窗口重新踢进 topmost 带 ——
//       能对抗那种每帧 HWND_TOPMOST 抢占的激进游戏，把我们的窗口硬塞回顶层。
//     · 代价：transparent 窗口（Pet/Chat/AgentHud）会有一次合成层重建抖动，但用户
//       此时在看游戏，抖动不可见，权衡合理。
//
// 独占全屏（DirectX exclusive fullscreen）是 OS 内核级限制，任何 Electron API 都
// 无法覆盖 —— 客观边界，需引导用户在游戏里改用「无边框 / 窗口化全屏」。
// 定时器使用 unref() 避免阻塞进程退出。
let _topReassertTimer = null;
const TOP_REASSERT_INTERVAL_MS = 2000;
// dirty-flag 门控：仅当 Z-order 可能变化时才执行完整 rank-sorted 重排
// 静态空闲场景下整 tick 只 moveTop(toast)，避免对 transparent 窗口造成无谓的 DWM 合成层重建闪烁
// 触发源：applyTopOn 成功 / browser-window-created / 受管窗口 show/focus/blur / 应用 focus/blur
// 强力模式（app 失焦）跳过门控，对游戏抢占强制每 tick 重排
let _zOrderDirty = true; // 启动时 dirty，第一 tick 必定执行

/**
 * 给窗口注册 show/focus/blur/closed 监听，事件触发时置 _zOrderDirty。
 * 用 win._nekoMarkDirtyHooked 标记避免重复注册。
 * 在 browser-window-created 钩子和 startTopReassertion 启动时分别调用，
 * 覆盖钩子注册前已创建的受管窗口（Pet / chat / subtitle / agentHud / jukebox）。
 */
function ensureMarkDirtyHooked(win) {
  if (!win || win.isDestroyed()) return;
  if (win === getLoadingWindow()) return;
  if (win._nekoMarkDirtyHooked) return;
  win._nekoMarkDirtyHooked = true;
  const markDirty = () => { _zOrderDirty = true; };
  try {
    win.on('show', markDirty);
    win.on('focus', markDirty);
    win.on('blur', markDirty);
    win.on('closed', markDirty);
  } catch (e) { /* ignore */ }
}

function reassertTopOn(win, opts = {}) {
  if (!win || win.isDestroyed()) return;
  if (win === getLoadingWindow()) return;
  try {
    if (!win.isVisible() || win.isMinimized()) return;
    // 仅对当前处于置顶状态的窗口做重断言（禁用态窗口跳过）
    if (!win.isAlwaysOnTop()) return;
  } catch (e) { return; }

  const forceToggle = !!opts.forceToggle;

  // Toast 独立 screen-saver，单独路径（调用方在主循环里保证 Toast 最后重断言）
  const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
  if (toast && win === toast) {
    try {
      if (forceToggle) win.setAlwaysOnTop(false);
      win.setAlwaysOnTop(true, 'screen-saver');
    } catch (e) { /* ignore */ }
    try { win.moveTop(); } catch (e) { /* ignore */ }
    return;
  }

  // Pet / 受管卫星窗口：使用平台最高级（Windows 下 screen-saver）
  // 弹出子窗口：沿用当前 level；无法反向推导其 kind，但 moveTop 对任何 topmost 窗口都有效
  try {
    const level = getManagedTopLevel();
    const aotBefore = (() => { try { return win.isAlwaysOnTop(); } catch(e) { return 'err'; } })();
    log(`[reassertTopOn] winId=${win.id} forceToggle=${forceToggle} level=${level} aotBefore=${aotBefore}`);
    if (forceToggle) {
      try { win.setAlwaysOnTop(false); } catch (e) { /* ignore */ }
    }
    win.setAlwaysOnTop(true, level);
    const aotAfter = (() => { try { return win.isAlwaysOnTop(); } catch(e) { return 'err'; } })();
    log(`[reassertTopOn] after setAlwaysOnTop(true,'${level}') → isAlwaysOnTop=${aotAfter}`);
    win.moveTop();
    log(`[reassertTopOn] moveTop() called`);
  } catch (e) { log(`[reassertTopOn] ERROR: ${e.message}`); }
}

// Pet 游戏模式 watcher 状态变量（必须在 startTopReassertion 之前声明）
let _petGameModeTimer = null;
let _petAppBlurAt = 0;
let _petGameModeWatcherInstalled = false;
let _systemMenuOcclusionGuardDepth = 0;
const PET_GAME_GRACE_PERIOD_MS = 3000;       // 应用失焦 3s 后才开始 moveTop
const PET_GAME_REASSERT_INTERVAL_MS = 1500;  // 之后每 1.5s 一次

function isSystemMenuOcclusionGuardActive() {
  return _systemMenuOcclusionGuardDepth > 0;
}

function demotePetForSystemMenu() {
  if (process.platform !== 'win32') return;
  const mainWindow = getMainWindow();
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    if (mainWindow.isAlwaysOnTop()) {
      mainWindow.setAlwaysOnTop(false);
      _zOrderDirty = true;
    }
  } catch (e) {
    log('系统菜单保护降级 Pet 失败:', e.message);
  }
}

function restorePetAfterSystemMenu() {
  if (process.platform !== 'win32') return;
  if (!getGlobalAlwaysOnTop()) return;
  const mainWindow = getMainWindow();
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    if (!mainWindow.isAlwaysOnTop()) {
      mainWindow.setAlwaysOnTop(true, getManagedTopLevel('pet'));
      _zOrderDirty = true;
    }
  } catch (e) {
    log('系统菜单保护恢复 Pet 置顶失败:', e.message);
  }
}

function beginSystemMenuOcclusionGuard() {
  if (process.platform !== 'win32') return;
  _systemMenuOcclusionGuardDepth += 1;
  if (_systemMenuOcclusionGuardDepth > 1) return;
  demotePetForSystemMenu();
}

function endSystemMenuOcclusionGuard() {
  if (process.platform !== 'win32') return;
  _systemMenuOcclusionGuardDepth = Math.max(0, _systemMenuOcclusionGuardDepth - 1);
  if (_systemMenuOcclusionGuardDepth > 0) return;
  restorePetAfterSystemMenu();
}

function startTopReassertion() {
  // **全窗口周期 reassertion 已被禁用** — 多轮反馈反复证明：任何对 chat/chara_manager/
  // jukebox/manager 等的 moveTop 都会让其重叠窗口被动 Z-order 变化引发 DWM 重组合闪烁。
  // 现状：窗口层级靠（1）创建时一次性幂等 applyTopOn（2）OS 激活机制（3）jukebox/manager
  // 的 owner-child 关系维持。
  //
  // **但 Pet 在全屏游戏下的抗抢占需要单独保留**——见 startPetGameModeWatcher。
  if (!getGlobalAlwaysOnTop()) return;
  if (process.platform !== 'win32') return;
  log('全窗口周期 reassertion 已禁用（防闪烁）；Pet 游戏模式 watcher 单独管理 Pet 抗抢占');
  startPetGameModeWatcher();
}

function markZOrderDirty() {
  _zOrderDirty = true;
}

// ===== Pet 游戏模式 watcher（仅对 Pet 周期 moveTop，对抗全屏游戏抢占）=====
//
// 这是与全窗口 reassertion 解耦的独立机制，专门解决"Pet 在全屏游戏下被抢占顶置"问题。
// 设计原则：
//   · 只对 Pet（mainWindow）做 moveTop，不去 reassert chat/chara_manager/jukebox 等
//     —— 不破坏 owner-child 关系，不破坏 dirty-flag 静默状态；
//   · 仅在应用整体失焦持续超过宽限期后才执行 —— 用户切换窗口的瞬间不动作，避免影响
//     正常窗口切换的体验；
//   · 仅 moveTop 不做 setAlwaysOnTop toggle —— 减少 SetWindowPos 调用次数；
//   · 间隔 1.5s —— 平衡"Pet 在游戏中浮现频率"和"普通外部应用场景的视觉影响"。
//
// 代价：长时间失焦时（> 宽限期）每 1.5s 一次的 Pet moveTop 会让其他 topmost 窗口
// （chat / chara_manager / jukebox / agentHud / Toast）被动 Z-order 下降一位 → 它们
// 的合成层重建。但用户在游戏全屏下看不到这些窗口；普通外部应用场景下用户也很少注视
// N.E.K.O 仍可见的边缘部分。这是为换 Pet 游戏抗抢占必须付的代价。
// （状态变量已在 startTopReassertion 之前声明）

function startPetGameModeWatcher() {
  if (_petGameModeTimer) return;
  if (process.platform !== 'win32') return;
  if (!getGlobalAlwaysOnTop()) return;

  // 监听应用整体 focus/blur，记录失焦开始时间
  // browser-window-blur 触发时检查 getFocusedWindow()，确认应用整体已无窗口 focused
  const onBlur = () => {
    setImmediate(() => {
      try {
        if (BrowserWindow.getFocusedWindow() === null) {
          if (_petAppBlurAt === 0) _petAppBlurAt = Date.now();
        }
      } catch (e) { /* ignore */ }
    });
  };
  const onFocus = () => { _petAppBlurAt = 0; };
  if (!_petGameModeWatcherInstalled) {
    app.on('browser-window-blur', onBlur);
    app.on('browser-window-focus', onFocus);
    _petGameModeWatcherInstalled = true;
  }

  _petGameModeTimer = setInterval(() => {
    try {
      if (!getGlobalAlwaysOnTop()) { stopPetGameModeWatcher(); return; }
      if (isSystemMenuOcclusionGuardActive()) return;
      // 仅在应用失焦时执行
      if (BrowserWindow.getFocusedWindow() !== null) return;
      // 失焦至少经过宽限期才开始（用户快速切窗口期间不动作）
      if (_petAppBlurAt === 0 || Date.now() - _petAppBlurAt < PET_GAME_GRACE_PERIOD_MS) return;
      // compact 毛线球可见时跳过 Pet moveTop：折叠后球(showInactive)+对话框(dim) → 无窗口聚焦 →
      // app 失焦 3s 后本 watcher 会周期顶 Pet，导致球这类 topmost 透明窗口被动掉层 + DWM 合成层重建
      // → 用户光标停在球上看到周期性闪烁（箭头/手抖）。球可见 = 用户在用 N.E.K.O（非全屏游戏场景），
      // 不需要 Pet 抗抢占，跳过即可消除球闪烁。（真在全屏游戏里一般不会同时挂着 compact 球。）
      try {
        const ball = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
        if (ball && !ball.isDestroyed() && ball.isVisible()) return;
      } catch (e) { /* ignore */ }
      // 仅对 Pet 做 moveTop，不影响其他窗口的 alwaysOnTop 状态
      const mainWindow = getMainWindow();
      if (mainWindow && !mainWindow.isDestroyed()
          && mainWindow.isVisible() && !mainWindow.isMinimized()) {
        try { mainWindow.moveTop(); } catch (e) { /* ignore */ }
      }
    } catch (e) { /* ignore */ }
  }, PET_GAME_REASSERT_INTERVAL_MS);
  try { _petGameModeTimer.unref(); } catch (e) { /* ignore */ }
  log('Pet 游戏模式 watcher 已启动（grace=' + PET_GAME_GRACE_PERIOD_MS
    + 'ms, interval=' + PET_GAME_REASSERT_INTERVAL_MS + 'ms）');
}

function stopPetGameModeWatcher() {
  if (_petGameModeTimer) {
    clearInterval(_petGameModeTimer);
    _petGameModeTimer = null;
    log('Pet 游戏模式 watcher 已停止');
  }
  _petAppBlurAt = 0;
}

function stopTopReassertion() {
  if (_topReassertTimer) {
    clearInterval(_topReassertTimer);
    _topReassertTimer = null;
    log('停止周期性 Z-order 重断言');
  }
}

  return {
    applyTopOn,
    beginSystemMenuOcclusionGuard,
    endSystemMenuOcclusionGuard,
    ensureMarkDirtyHooked,
    getChildWindowTopLevel,
    getWindowZRank,
    getManagedTopLevel,
    isNormalFramedPopup,
    isWindowedToolPopup,
    markZOrderDirty,
    startTopReassertion,
    stopPetGameModeWatcher,
    stopTopReassertion,
  };
}

module.exports = {
  createTopCoordinator,
};
