'use strict';

const { isTrustedSender } = require('./utils/trust-guard');

function registerScreenCaptureIpc(context) {
  const { BrowserWindow, desktopCapturer, ipcMain, log, shell, screen, windowManager } = context;
  const isLinuxWaylandRuntime = typeof context.isLinuxWaylandRuntime === 'function'
    ? context.isLinuxWaylandRuntime
    : () => process.platform === 'linux'
      && (process.env.XDG_SESSION_TYPE === 'wayland' || !!process.env.WAYLAND_DISPLAY);
  const selectedScreenSourceIds = new Map();
  const screenSourceDisplayIds = new Map();
  let lastSelectedScreenSourceId = null;

  // ===== 截图清晰度 =====
  // 截图先在前端全分辨率裁剪/标注，"截图后立即置顶显示的画面"就是这张图 —— 它不发后端、
  // 只在屏幕上预览。此前统一 toJPEG(80) 会肉眼可见地发糊，故预览链路改用无损 PNG（toDataURL）。
  // 发猫娘的 720p / JPEG 压缩仍在下游 pipeline 单独做，这里只管"所见即所得"地清晰。
  //
  // 【关键清晰度坑】desktopCapturer.getSources 会把缩略图无条件缩放到 thumbnailSize：
  // 当 thumbnailSize 比源大时它会“放大插值”。此前对所有屏幕源硬编码请求 4K(3840x2160)，
  // 于是一块 1080p 屏会被插值放大到 2160p（糊），再被 toDataURL 无损地把“放大后的糊像素”
  // 原样存进 PNG，前端预览再缩回 1080p 显示 —— 净效果就是“每一步都无损，却整体发虚”。
  // 修复：屏幕源一律按其所在显示器的物理像素（size × scaleFactor）抓取，做到 1:1 原生采样、
  // 永不放大。窗口源仍维持 1080p 上限（窗口无法廉价拿到原生像素尺寸，且多窗口高分捕获会卡主线程）。
  const WINDOW_THUMBNAIL_SIZE = { width: 1920, height: 1080 };

  function encodeThumbnail(thumbnail) {
    // 无损 PNG data URL —— 预览不发后端，优先清晰度
    return thumbnail.toDataURL();
  }

  // 某个显示器的物理像素尺寸（DIP 尺寸 × 系统缩放）。拿不到时返回 null。
  function physicalSizeForDisplayId(displayId) {
    try {
      if (displayId != null && screen && typeof screen.getAllDisplays === 'function') {
        const d = screen.getAllDisplays().find((x) => String(x.id) === String(displayId));
        if (d && d.size) {
          const sf = d.scaleFactor || 1;
          const w = Math.round(d.size.width * sf);
          const h = Math.round(d.size.height * sf);
          if (w > 0 && h > 0) return { width: w, height: h };
        }
      }
    } catch (_) { /* 退回兜底 */ }
    return null;
  }

  // 拿不到目标屏 display_id（Electron 允许 screen 源的 display_id 为空）时的兜底尺寸。
  // 取所有显示器里【最小】的物理分辨率（逐分量 min）—— 保证请求尺寸不大于任何一块屏，
  // desktopCapturer 于是永远不会放大插值（混合分辨率多屏下若用最大尺寸，会把较小的屏放大成糊，
  // 正是本次要修的发虚，Codex P2）。代价：更大的屏会被降采样（清晰但像素更少），但这强过插值放大。
  // 单显示器时该值就是它自己的物理尺寸 = 精确 1:1。
  function fallbackPhysicalScreenSize() {
    let w = 0, h = 0;
    try {
      if (screen && typeof screen.getAllDisplays === 'function') {
        for (const d of screen.getAllDisplays()) {
          const sf = (d && d.scaleFactor) || 1;
          const dw = d && d.size ? Math.round(d.size.width * sf) : 0;
          const dh = d && d.size ? Math.round(d.size.height * sf) : 0;
          if (dw > 0 && (w === 0 || dw < w)) w = dw;
          if (dh > 0 && (h === 0 || dh < h)) h = dh;
        }
      }
    } catch (_) { /* 退回 1080p */ }
    if (w < 1 || h < 1) return { width: 1920, height: 1080 };
    return { width: w, height: h };
  }

  // 按目标屏物理分辨率原生采样一个 screen 源（两遍枚举）：
  //   1) 用 1x1 探针缩略图极廉价地枚举一次，定位源并拿到它的 display_id；
  //   2) 按该屏物理像素尺寸再枚举一次 —— thumbnailSize == 源尺寸 ⇒ 不放大不缩小 = 1:1。
  // allowPrimaryFallback：wantSourceId 找不到时是否退回主屏（多屏歧义场景由调用方决定）。
  async function getScreenSourceNative(wantSourceId, allowPrimaryFallback) {
    const probe = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1, height: 1 },
    });
    rememberScreenSourceDisplayIds(probe);
    let probed = wantSourceId ? probe.find((s) => s.id === wantSourceId) : null;
    if (!probed && allowPrimaryFallback) probed = pickPrimaryScreenSource(probe);
    if (!probed) return null;

    const phys = physicalSizeForDisplayId(probed.display_id) || fallbackPhysicalScreenSize();
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: phys,
    });
    rememberScreenSourceDisplayIds(sources);
    return sources.find((s) => s.id === probed.id) || null;
  }

  // 在 screen 源里挑主显示器对应的那个；挑不到就退回第一个。
  function pickPrimaryScreenSource(sources) {
    if (!sources || !sources.length) return null;
    try {
      if (screen && typeof screen.getPrimaryDisplay === 'function') {
        const primaryId = String(screen.getPrimaryDisplay().id);
        const matched = sources.find((s) => String(s.display_id) === primaryId);
        if (matched) return matched;
      }
    } catch (_) { /* 退回首个 */ }
    return sources[0];
  }

  function rememberScreenSourceDisplayIds(sources) {
    if (!Array.isArray(sources)) return;
    for (const source of sources) {
      if (!source || typeof source.id !== 'string' || !source.id.startsWith('screen:')) continue;
      if (source.display_id == null) continue;
      screenSourceDisplayIds.set(source.id, String(source.display_id));
    }
  }

  function getRememberedDisplayIdForSourceId(sourceId) {
    if (!sourceId || typeof sourceId !== 'string') return null;
    return screenSourceDisplayIds.get(sourceId) || null;
  }

  function getDisplayIdForWindow(win) {
    try {
      if (!win || typeof win.getBounds !== 'function'
        || !screen || typeof screen.getDisplayMatching !== 'function') {
        return null;
      }
      const bounds = win.getBounds();
      if (!bounds || !Number.isFinite(Number(bounds.x)) || !Number.isFinite(Number(bounds.y))) {
        return null;
      }
      const display = screen.getDisplayMatching(bounds);
      if (display && display.id != null) return String(display.id);
    } catch (_) { /* fall through */ }
    return null;
  }

  function getCaptureAnchorWindow(senderWin) {
    const candidates = [];
    try {
      if (windowManager && typeof windowManager.getPetWindow === 'function') {
        candidates.push(windowManager.getPetWindow());
      }
    } catch (_) { /* fall through */ }
    try {
      if (windowManager && typeof windowManager.getWindows === 'function') {
        const windows = windowManager.getWindows();
        if (windows && windows.pet) candidates.push(windows.pet);
      }
    } catch (_) { /* fall through */ }
    candidates.push(senderWin);

    for (const win of candidates) {
      try {
        if (win && typeof win.isDestroyed === 'function' && win.isDestroyed()) continue;
      } catch (_) {
        continue;
      }
      if (win) return win;
    }
    return null;
  }

  async function getScreenSourceNativeForDisplayId(displayId) {
    const probe = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: { width: 1, height: 1 },
    });
    rememberScreenSourceDisplayIds(probe);
    let probed = displayId != null
      ? probe.find((s) => String(s.display_id) === String(displayId))
      : null;
    if (!probed && probe.length === 1) probed = probe[0];
    if (!probed) return null;

    const phys = physicalSizeForDisplayId(probed.display_id) || fallbackPhysicalScreenSize();
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: phys,
    });
    rememberScreenSourceDisplayIds(sources);
    return sources.find((s) => s.id === probed.id) || null;
  }

  async function getScreenSourceSinglePassForWithoutNeko(wantSourceId, displayId, allowPrimaryFallback) {
    // Wayland 下 desktopCapturer.getSources 可能走 xdg-desktop-portal，每调用一次都可能弹
    // "共享屏幕"确认框。隐藏 NEKO 重拍优先保证一次操作只触发一次系统请求，因此这里不用
    // getScreenSourceNative 的两遍探针策略。若用户已从下拉列表选过源，优先使用枚举列表里缓存的
    // sourceId -> display_id 契约来保留目标屏原生尺寸；拿不到时才按 Pet 窗口 display / 最小物理
    // 尺寸做单次枚举，避免为追求精确尺寸再触发第二次 portal。
    const targetDisplayId = getRememberedDisplayIdForSourceId(wantSourceId) || displayId;
    const phys = physicalSizeForDisplayId(targetDisplayId) || fallbackPhysicalScreenSize();
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: phys,
    });
    rememberScreenSourceDisplayIds(sources);
    if (!sources || !sources.length) return null;

    if (wantSourceId) {
      const matchedSource = sources.find((s) => s.id === wantSourceId);
      if (matchedSource) return matchedSource;
      if (!allowPrimaryFallback) return null;
    }

    if (displayId != null) {
      const matchedDisplay = sources.find((s) => String(s.display_id) === String(displayId));
      if (matchedDisplay) return matchedDisplay;
    }

    if (sources.length === 1) return sources[0];
    if (allowPrimaryFallback) return pickPrimaryScreenSource(sources);
    return null;
  }

  function rememberSelectedSource(webContents, sourceId) {
    const normalized = (sourceId && typeof sourceId === 'string') ? sourceId : null;
    if (normalized) {
      selectedScreenSourceIds.set(webContents.id, normalized);
      lastSelectedScreenSourceId = normalized;
    } else {
      selectedScreenSourceIds.delete(webContents.id);
      lastSelectedScreenSourceId = null;
    }
    webContents.once('destroyed', () => {
      selectedScreenSourceIds.delete(webContents.id);
    });
  }

ipcMain.handle('get-desktop-sources', async (event, options = {}) => {
  if (!isTrustedSender(event)) return [];
  try {
    const types = options.types || ['window', 'screen'];
    const thumbnailSize = options.thumbnailSize || { width: 150, height: 150 };

    const sources = await desktopCapturer.getSources({
      types: types,
      thumbnailSize: thumbnailSize
    });
    rememberScreenSourceDisplayIds(sources);

    // 转换为可序列化的格式（NativeImage 不能直接序列化）
    return sources.map(source => ({
      id: source.id,
      name: source.name,
      // 将缩略图转换为 data URL
      thumbnail: source.thumbnail ? source.thumbnail.toDataURL() : null,
      // 应用图标（如果有的话）
      appIcon: source.appIcon ? source.appIcon.toDataURL() : null,
      // 显示 ID（对于屏幕源）
      display_id: source.display_id
    }));
  } catch (err) {
    log('get-desktop-sources 错误:', err.message);
    return [];
  }
});

// ===== 渲染器选中的屏幕/窗口源 ID 镜像 =====
// 用户在下拉菜单中选择屏幕源后，由渲染器通过 set-selected-screen-source IPC 同步到这里。
// setDisplayMediaRequestHandler 的回调会优先使用此 ID 对应的源，避免 getDisplayMedia 兜底时
// 硬编码返回首个 screen 源，导致用户选择被忽略（聊天框截图按钮即使在 getUserMedia(chromeMediaSourceId)
// 失败后回退也能截到正确的源）。
ipcMain.handle('set-selected-screen-source', async (event, sourceId) => {
  if (!isTrustedSender(event)) return { success: false };
  rememberSelectedSource(event.sender, sourceId);
  return { success: true };
});

// ===== 主进程直接截图 IPC =====
// 用 desktopCapturer 请求高分辨率缩略图 —— 对选中的源做一次性快照，
// 完全绕开 getUserMedia / getDisplayMedia 那条 Chromium 管线（该管线在
// Electron 41 / Windows 11 + useSystemPicker:true 场景下，对 WINDOW 源
// 常返回整个屏幕而非窗口本身，导致聊天框截图永远截主屏）。
ipcMain.handle('capture-source-as-dataurl', async (event, sourceId) => {
  if (!isTrustedSender(event)) {
    return { success: false, error: 'Untrusted sender' };
  }
  try {
    if (!sourceId || typeof sourceId !== 'string') {
      return { success: false, error: 'Invalid sourceId' };
    }

    // 窗口源：1080p 上限单遍枚举。屏幕源（screen: 前缀，或无前缀的脏值兜底当屏幕处理）：
    // 走原生物理分辨率两遍采样，避免被放大插值糊掉（见顶部清晰度坑注释）。
    let source;
    if (sourceId.startsWith('window:')) {
      const sources = await desktopCapturer.getSources({
        types: ['window'],
        thumbnailSize: WINDOW_THUMBNAIL_SIZE,
      });
      source = sources.find(s => s.id === sourceId);
    } else {
      // 这里是渲染器明确选中的源，必须精确命中 —— 不做主屏兜底（那是 without-neko 的语义）。
      const wantId = sourceId.startsWith('screen:') ? sourceId : null;
      source = await getScreenSourceNative(wantId, /* allowPrimaryFallback */ false);
    }
    if (!source) {
      return { success: false, error: 'Source not found' };
    }
    if (!source.thumbnail || source.thumbnail.isEmpty()) {
      return { success: false, error: 'Thumbnail is empty' };
    }

    // 无损 PNG —— 这张图会被前端置顶预览并在其上裁剪/标注，发后端的 720p 压缩在下游单独做
    const dataUrl = encodeThumbnail(source.thumbnail);
    const size = source.thumbnail.getSize();
    return { success: true, dataUrl, width: size.width, height: size.height };
  } catch (e) {
    try { log('capture-source-as-dataurl 错误:', e && e.message); } catch (_) { }
    return { success: false, error: (e && e.message) || 'unknown error' };
  }
});

// ===== "隐藏NEKO" 再截图 — 主进程原子化：全部 NEKO 窗口 hide → 等合成 → 抓屏 → show =====
// 为什么必须在主进程做完整闭环：
//   1) 渲染器里用 setTimeout 等合成，Pet 窗口 hide 后 renderer 会被 backgroundThrottling
//      拖慢，定时器动辄秒级延迟；
//   2) IPC 往返 + 渲染器恢复顺序如果出错，用户会看到卫星窗口还在/已经回来、Pet 已经
//      开始重绘等各种时序错位；
//   3) Pet 窗口自身（承载 Live2D + crop overlay）必须一起 hide 掉才算"真的把 NEKO 拿掉"，
//      单纯 CSS visibility:hidden 覆盖不到 WebGL 合成层（有缓存 backbuffer 的历史截帧还
//      可能被 Windows DWM 捕到）。
// 流程：
//   a. 记下所有当前可见的 BrowserWindow id；
//   b. 统一 hide()；
//   c. setImmediate + 300ms 两帧等待；
//   d. desktopCapturer.getSources 抓图；
//   e. 按相反顺序 show（Pet 最后回来并夺回焦点，其他 showInactive）。
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// Main-process IPC handlers run on Electron's single JS thread, so lease
// mutations are atomic between await points. If this state is ever shared across
// workers or native concurrent callers, serialize access or pass lease state
// explicitly instead.
let pendingStandaloneHide = null;
const atomicHiddenWindowCounts = new Map();
const atomicDeferredRestoreIds = new Set();

function restoreWindowIds(hiddenIds) {
  let restored = 0;
  if (!Array.isArray(hiddenIds)) return restored;
  for (const id of hiddenIds) {
    const w = BrowserWindow.fromId(id);
    if (!w || w.isDestroyed()) continue;
    try {
      w.showInactive();
      restored += 1;
    } catch (e) { /* ignore */ }
  }
  return restored;
}

function getStandaloneHiddenWindowIds() {
  return pendingStandaloneHide ? Array.from(pendingStandaloneHide.counts.keys()) : [];
}

function retainAtomicHiddenWindowIds(hiddenIds) {
  if (!Array.isArray(hiddenIds)) return;
  for (const id of hiddenIds) {
    atomicHiddenWindowCounts.set(id, (atomicHiddenWindowCounts.get(id) || 0) + 1);
  }
}

function releaseAtomicHiddenWindowIds(hiddenIds) {
  if (!Array.isArray(hiddenIds)) return;
  const idsToRestore = [];
  for (const id of hiddenIds) {
    const count = atomicHiddenWindowCounts.get(id) || 0;
    if (count > 1) {
      atomicHiddenWindowCounts.set(id, count - 1);
    } else {
      atomicHiddenWindowCounts.delete(id);
      if (atomicDeferredRestoreIds.has(id)) {
        atomicDeferredRestoreIds.delete(id);
        idsToRestore.push(id);
      }
    }
  }
  restoreWindowIds(idsToRestore);
}

function isAtomicHiddenWindowId(id) {
  return atomicHiddenWindowCounts.has(id);
}

function collectRestoreIdsOutsideAtomicGuard(hiddenIds) {
  const idsToRestore = [];
  if (!Array.isArray(hiddenIds)) return idsToRestore;
  for (const id of hiddenIds) {
    if (isAtomicHiddenWindowId(id)) {
      atomicDeferredRestoreIds.add(id);
    } else {
      idsToRestore.push(id);
    }
  }
  return idsToRestore;
}

function armStandaloneHideLease(hiddenIds) {
  const nextIds = Array.from(new Set(Array.isArray(hiddenIds) ? hiddenIds : []));
  if (nextIds.length === 0) return [];
  if (!pendingStandaloneHide) pendingStandaloneHide = { counts: new Map() };
  for (const id of nextIds) {
    pendingStandaloneHide.counts.set(id, (pendingStandaloneHide.counts.get(id) || 0) + 1);
  }
  return nextIds;
}

function releaseStandaloneHideLease(hiddenIds) {
  if (!Array.isArray(hiddenIds)) return [];
  if (!pendingStandaloneHide) return collectRestoreIdsOutsideAtomicGuard(hiddenIds);
  const idsToRestore = [];
  for (const id of hiddenIds) {
    const count = pendingStandaloneHide.counts.get(id) || 0;
    if (count > 1) {
      pendingStandaloneHide.counts.set(id, count - 1);
    } else if (count === 1) {
      pendingStandaloneHide.counts.delete(id);
      idsToRestore.push(id);
    }
  }
  if (pendingStandaloneHide.counts.size === 0) pendingStandaloneHide = null;
  return collectRestoreIdsOutsideAtomicGuard(idsToRestore);
}

// ===== 单独的 hide/restore IPC（供渲染器 fallback 路径使用）=====
// 为什么单独暴露：atomic 路径在 selectedSourceId 失效时会失败，此时渲染器还会落到
// getDisplayMedia / pyautogui 的 fallback，MediaStream 抓的是整块屏幕，卫星窗口也在
// 画面里。此时需要"只 hide 不抓图"让渲染器自己完成抓帧。
ipcMain.handle('hide-neko-windows', async (event) => {
  if (!isTrustedSender(event)) {
    return { success: false, hiddenIds: [], error: 'Untrusted sender' };
  }
  try {
    const senderWin = BrowserWindow.fromWebContents(event.sender);
    const senderId = senderWin ? senderWin.id : -1;
    const hiddenIds = [];
    for (const w of BrowserWindow.getAllWindows()) {
      if (!w || w.isDestroyed() || !w.isVisible()) continue;
      // sender（Pet）不 hide —— renderer 还要继续跑，Pet 一旦 hide 就会被
      // backgroundThrottling 拖慢到秒级，MediaStream 抓帧会错位。
      // Pet 的 DOM 已经由渲染器 visibility:hidden 处理。
      if (w.id === senderId) continue;
      try {
        hiddenIds.push(w.id);
        w.hide();
      } catch (e) { /* ignore */ }
    }
    const leasedIds = armStandaloneHideLease(hiddenIds);
    return { success: true, hiddenIds: leasedIds };
  } catch (e) {
    return { success: false, hiddenIds: [], error: (e && e.message) || 'unknown' };
  }
});

ipcMain.handle('restore-neko-windows', async (event, hiddenIds) => {
  if (!isTrustedSender(event)) {
    return { success: false };
  }
  try {
    if (!Array.isArray(hiddenIds)) return { success: false };
    restoreWindowIds(releaseStandaloneHideLease(hiddenIds));
    return { success: true };
  } catch (e) {
    return { success: false, error: (e && e.message) || 'unknown' };
  }
});

ipcMain.handle('capture-source-without-neko', async (event, sourceId) => {
  if (!isTrustedSender(event)) {
    return { success: false, error: 'Untrusted sender' };
  }
  // sourceId 缺省（用户从没在下拉里选过源、初始截图走的是 getDisplayMedia）也要能干活：
  // 优先按 Pet 窗口所在 display 抓屏；如果拿不到 Pet 再退回 IPC sender。否则渲染器只能退回 visibility:hidden
  // fallback，盖不住 WebGL 立绘，表现为"隐藏NEKO 画面刷新了但立绘还在"。
  // 多显示器 + 无预选源时，Pet 所在 display 是最接近截图裁剪覆盖层的可靠信号。
  // 只认 screen:/window: 前缀；非空但非法（无前缀的脏值）一律归一成 null，
  // 当成"没选源"走 Pet 所在屏幕的原生采样路径 —— 否则会落进 ['window','screen']
  // 分支、缩略图被降到 1080p，回退拿到的预览反而糊了，且高分枚举窗口又会卡主线程
  // （CodeRabbit）。
  const rawSourceId = (sourceId && typeof sourceId === 'string') ? sourceId : null;
  const wantSourceId = (rawSourceId && (rawSourceId.startsWith('screen:') || rawSourceId.startsWith('window:')))
    ? rawSourceId : null;

  const senderWin = BrowserWindow.fromWebContents(event.sender);
  const senderId = senderWin ? senderWin.id : -1;
  const captureAnchorWin = getCaptureAnchorWindow(senderWin);
  const captureDisplayId = getDisplayIdForWindow(captureAnchorWin);

  // 1. 记下当前可见窗口并全部 hide（含 sender/Pet 自身）
  const atomicStandaloneHiddenIds = getStandaloneHiddenWindowIds();
  retainAtomicHiddenWindowIds(atomicStandaloneHiddenIds);
  const hiddenWins = [];
  for (const w of BrowserWindow.getAllWindows()) {
    if (!w || w.isDestroyed() || !w.isVisible()) continue;
    try {
      hiddenWins.push({ id: w.id, isSender: w.id === senderId });
      w.hide();
    } catch (e) {
      try { log('capture-without-neko: hide 失败', w.id, e && e.message); } catch (_) { }
    }
  }

  let result;
  try {
    // 2. 等 DWM / 系统合成器把 hide 反映到实际桌面像素（两帧以上 + 余量）
    await sleep(350);

    // 3. desktopCapturer 抓图（复用 capture-source-as-dataurl 的清晰度策略）
    //    窗口源：只枚举 window，1080p；其余（指定屏幕 / 缺省 / 脏值归一后的 null）：
    //    走 getScreenSourceNative 按目标屏物理分辨率原生采样（不放大插值，见顶部清晰度坑注释）。
    const isWindowRequest = !!wantSourceId && wantSourceId.startsWith('window:');
    let source;
    const isWayland = isLinuxWaylandRuntime();
    if (isWindowRequest) {
      const sources = await desktopCapturer.getSources({
        types: ['window'],
        thumbnailSize: WINDOW_THUMBNAIL_SIZE,
      });
      source = sources.find((s) => s.id === wantSourceId) || null;
    } else if (isWayland) {
      // Wayland portal 会把每次 screen source 枚举都变成系统共享请求。
      // 隐藏 NEKO 重拍如果沿用普通高清两遍采样，会出现连续弹窗；这里改为单次枚举。
      let singleDisplay = true;
      try { singleDisplay = !screen || !screen.getAllDisplays || screen.getAllDisplays().length <= 1; }
      catch (_) { singleDisplay = true; }
      source = await getScreenSourceSinglePassForWithoutNeko(
        wantSourceId,
        captureDisplayId,
        !!wantSourceId || singleDisplay,
      );
    } else if (wantSourceId) {
      source = await getScreenSourceNative(wantSourceId, /* allowPrimaryFallback */ true);
    } else {
      source = await getScreenSourceNativeForDisplayId(captureDisplayId);
      if (!source) {
        // 最后保留旧的单屏兜底；多屏且无法映射 display_id 时仍不盲抓主屏，避免换屏。
        let singleDisplay = true;
        try { singleDisplay = !screen || !screen.getAllDisplays || screen.getAllDisplays().length <= 1; }
        catch (_) { singleDisplay = true; }
        source = await getScreenSourceNative(null, singleDisplay);
      }
    }
    if (!source || !source.thumbnail || source.thumbnail.isEmpty()) {
      result = { success: false, error: 'Source not found or thumbnail empty' };
    } else {
      const size = source.thumbnail.getSize();
      result = {
        success: true,
        dataUrl: encodeThumbnail(source.thumbnail),
        width: size.width,
        height: size.height,
      };
    }
  } catch (e) {
    try { log('capture-source-without-neko 抓图错误:', e && e.message); } catch (_) { }
    result = { success: false, error: (e && e.message) || 'unknown' };
  } finally {
    // 4. 恢复窗口；Pet（sender）最后并抢回焦点，其他窗口 showInactive 避免抢焦点。
    //    反向顺序——先恢复小的，后回来大的 Pet。
    for (const entry of hiddenWins) {
      if (entry.isSender) continue;
      const w = BrowserWindow.fromId(entry.id);
      if (!w || w.isDestroyed()) continue;
      try { w.showInactive(); } catch (e) { /* ignore */ }
    }
    const senderEntry = hiddenWins.find((e) => e.isSender);
    if (senderEntry) {
      const w = BrowserWindow.fromId(senderEntry.id);
      if (w && !w.isDestroyed()) {
        try { w.show(); } catch (e) { /* ignore */ }
      }
    }
    releaseAtomicHiddenWindowIds(atomicStandaloneHiddenIds);
  }
  return result;
});

// ===== 前端请求用系统浏览器打开外部链接 =====
ipcMain.handle('open-external-url', async (event, url) => {
  if (!isTrustedSender(event)) {
    return { success: false, error: 'Untrusted sender' };
  }
  try {
    if (typeof url !== 'string' || (!url.startsWith('http://') && !url.startsWith('https://'))) {
      return { success: false, error: 'Invalid URL' };
    }
    await shell.openExternal(url);
    log('已用系统浏览器打开:', url);
    return { success: true };
  } catch (err) {
    log('shell.openExternal 失败:', err.message);
    return { success: false, error: err.message };
  }
});


  return {
    getSelectedScreenSourceId: (webContentsId) => {
      if (webContentsId && selectedScreenSourceIds.has(webContentsId)) {
        return selectedScreenSourceIds.get(webContentsId);
      }
      return lastSelectedScreenSourceId;
    },
  };
}

module.exports = {
  registerScreenCaptureIpc,
};
