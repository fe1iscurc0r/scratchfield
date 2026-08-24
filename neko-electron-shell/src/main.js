const { app, Tray, Menu, screen, BrowserWindow, session, desktopCapturer, dialog, globalShortcut, ipcMain, powerMonitor, powerSaveBlocker, shell, nativeImage } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { spawn, spawnSync } = require('child_process');
const http = require('node:http');
const https = require('node:https');
const { SUPPORTED_LANGUAGES, trayMenuLocales } = require('./main/tray-menu-locales');
const { createHotkeyWindowDataUrlBuilder } = require('./main/hotkey-window-data-url');
const { createPortSettingsDataUrlBuilder } = require('./main/port-settings-window-data-url');
const { createWindowControlIpc } = require('./main/window-control-ipc');
const { createLoadingWindowDataUrlBuilder } = require('./main/loading-window-data-url');
const { registerScreenCaptureIpc } = require('./main/screen-capture-ipc');
const { registerActivitySignalIpc } = require('./main/activity-signal-ipc');
const { createExitRetentionPrompt } = require('./main/exit-retention');
const { createStorageGate } = require('./main/storage-gate');
const { createTopCoordinator } = require('./main/top-coordinator');
const { createBackendRuntime } = require('./main/backend-runtime');
const { createHotkeyManager } = require('./main/hotkey-manager');
const { createPetWindowLifecycle } = require('./main/pet-window-lifecycle');
const { createPowerSaveBlockerService } = require('./main/power-save-blocker-service');
const { createTrayMenuController } = require('./main/tray-menu');
const { createWindowHostIpc } = require('./main/window-host-ipc');
const { applyX11InputShape } = require('./main/linux-x11-input-shape');
const { createSystemCursorVisibilityService } = require('./system-cursor-visibility-service');
const { isTrustedSender } = require('./main/utils/trust-guard');
const {
  collectSwitchValues,
  mergeCommaSeparatedSwitchValues,
  stripSwitches,
} = require('./main/argv-switches');
const {
  getWaylandSetShapePatchStatus,
  shouldAutoFallbackToX11ForWayland,
} = require('./main/wayland-input-region-backend');

const nekoUserDataDirOverride = String(process.env.NEKO_USER_DATA_DIR || '').trim();
if (nekoUserDataDirOverride) {
  app.setPath('userData', path.resolve(nekoUserDataDirOverride));
}

// ===== 单实例锁 =====
// 防止多次双击运行文件导致同时启动多个应用
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  // 如果没有获得锁，说明已有一个实例在运行，直接退出
  console.log('检测到已有 N.E.K.O. 实例正在运行，退出当前实例');
  app.quit();
} else {
  // 当第二个实例启动时，聚焦到已存在的窗口
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    console.log('检测到第二个实例尝试启动，聚焦到现有窗口');
    if (mainWindow) {
      if (mainWindow.isMinimized()) {
        mainWindow.restore();
      }
      mainWindow.show();
      mainWindow.focus();
    } else if (loadingWindow) {
      if (loadingWindow.isMinimized()) {
        loadingWindow.restore();
      }
      loadingWindow.show();
      loadingWindow.focus();
    }
  });
}

// ===== 日志系统 =====
const logFilePath = path.join(app.getPath('userData'), 'neko-electron-debug.log');

// 启动时轮转：日志超 50 MB 就归档为 .old 再新开，避免累积到 GB 级
const LOG_MAX_BYTES = 50 * 1024 * 1024;
let _logRotatedFromBytes = 0;
try {
  const stat = fs.existsSync(logFilePath) ? fs.statSync(logFilePath) : null;
  if (stat && stat.size > LOG_MAX_BYTES) {
    const oldPath = logFilePath + '.old';
    try { if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath); } catch (_) { /* 旧的归档删不掉就算，下一步 rename 也可能失败 */ }
    fs.renameSync(logFilePath, oldPath);
    _logRotatedFromBytes = stat.size;
  }
} catch (e) {
  // 失败通常是文件被别的进程锁住（不该发生，我们有单实例锁）。退化为继续追加。
  console.warn('[log rotate] 失败，继续追加写入旧文件:', e.message);
}

const logStream = fs.createWriteStream(logFilePath, { flags: 'a' });
logStream.on('error', () => {}); // 防止 write-after-end 变成未捕获异常
let consoleOutputDisabled = false;
const originalConsole = {
  log: console.log.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
};

function disableConsoleOutput(reason) {
  if (consoleOutputDisabled) return;
  consoleOutputDisabled = true;
  const timestamp = new Date().toISOString();
  try {
    if (!logStream.writableEnded) {
      logStream.write(`[${timestamp}] 控制台输出已禁用: ${reason}\n`);
    }
  } catch (_) {}
}

function safeConsoleWrite(method, args) {
  if (consoleOutputDisabled) return;
  try {
    originalConsole[method](...args);
  } catch (err) {
    disableConsoleOutput(err && err.message ? err.message : `console.${method} failed`);
  }
}

console.log = (...args) => safeConsoleWrite('log', args);
console.warn = (...args) => safeConsoleWrite('warn', args);
console.error = (...args) => safeConsoleWrite('error', args);

for (const stream of [process.stdout, process.stderr]) {
  try {
    stream.on('error', (err) => {
      disableConsoleOutput(err && err.message ? err.message : 'stdio error');
    });
  } catch (_) {}
}

function log(...args) {
  const timestamp = new Date().toISOString();
  const message = `[${timestamp}] ${args.join(' ')}\n`;
  if (!consoleOutputDisabled) {
    try {
      console.log(...args);
    } catch (err) {
      disableConsoleOutput(err && err.message ? err.message : 'console write failed');
    }
  }
  try {
    if (!logStream.writableEnded) {
      logStream.write(message);
    }
  } catch (_) {}
}

// 启动时记录基本信息
log('='.repeat(80));
log('N.E.K.O. 启动 - 版本:', app.getVersion());
log('是否打包:', app.isPackaged);
log('当前目录 (cwd):', process.cwd());
log('__dirname:', __dirname);
log('app.getAppPath():', app.getAppPath());
log('process.resourcesPath:', process.resourcesPath);
log('app.getPath("userData"):', app.getPath('userData'));
log('日志文件位置:', logFilePath);
if (_logRotatedFromBytes > 0) {
  log(`[log rotate] 上次日志达 ${(_logRotatedFromBytes / 1024 / 1024).toFixed(1)} MB（>${LOG_MAX_BYTES / 1024 / 1024} MB 阈值），已归档为 ${logFilePath}.old`);
}
log('='.repeat(80));

// ⭐ 强制 Node.js/Electron 使用 UTF-8 编码
process.env.PYTHONIOENCODING = 'utf-8';
process.env.PYTHONUTF8 = '1';
if (process.platform === 'win32') {
  // Windows 下强制使用 UTF-8
  process.env.CHCP = '65001'; // Windows 代码页 65001 = UTF-8
}

// app.commandLine.appendSwitch('disable-direct-composition');

// ===== Windows 高性能 GPU 提示 =====
// 提示系统优先为本应用分配高性能 GPU（独显）。
// 这是偏好提示而非强制，实际结果仍受系统图形设置和驱动策略影响。
if (process.platform === 'win32') {
  app.commandLine.appendSwitch('force_high_performance_gpu');
  log('Windows: 已启用高性能 GPU 偏好提示');
}

// ===== core_config.txt 路径策略 =====
// 打包后 process.resourcesPath 在 macOS、Linux AppImage、Windows Program Files 等情况下
// 是只读/受保护的；因此把打包附带的 core_config.txt 当作"默认值"只读使用，真实用户配置
// 保存在 app.getPath('userData') 下。读取时优先用户覆盖，回退打包默认。
function getBundledConfigPath() {
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  return path.join(basePath, 'core_config.txt');
}

function getUserConfigPath() {
  return path.join(app.getPath('userData'), 'core_config.txt');
}

// 返回 { config, source } 其中 source ∈ 'user' | 'bundled' | 'none'
function readCoreConfigRaw() {
  const userPath = getUserConfigPath();
  if (fs.existsSync(userPath)) {
    try {
      return { config: JSON.parse(fs.readFileSync(userPath, 'utf-8')), source: 'user' };
    } catch (e) {
      console.warn('用户 core_config 解析失败，将回退打包默认:', e.message);
    }
  }
  const bundledPath = getBundledConfigPath();
  if (fs.existsSync(bundledPath)) {
    try {
      return { config: JSON.parse(fs.readFileSync(bundledPath, 'utf-8')), source: 'bundled' };
    } catch (e) {
      console.warn('打包 core_config 解析失败:', e.message);
    }
  }
  return { config: null, source: 'none' };
}

function normalizeStartupConfig(config) {
  const next = { ...(config || {}) };
  if (typeof next.compatibilityMode === 'undefined') {
    next.compatibilityMode = false;
  }
  if (typeof next.linuxForceX11 === 'undefined') {
    next.linuxForceX11 = true;
  }
  return next;
}

const LINUX_COMPATIBILITY_SWITCHES = ['ignore-gpu-blocklist', 'disable-gpu-sandbox'];
const LINUX_COMPATIBILITY_STRIP_SWITCHES = ['ignore-gpu-blocklist', 'disable-gpu-sandbox'];
const LINUX_COMPATIBILITY_RELAUNCH_MARKER = 'neko-linux-compatibility-flags-applied';
const LINUX_X11_RELAUNCH_MARKER = 'neko-linux-x11-flags-applied';
const LINUX_X11_REQUIRED_DISABLE_FEATURES = ['VaapiVideoDecoder', 'VaapiVideoEncoder'];
const LINUX_X11_SWITCH_ARGS = [
  '--ozone-platform=x11',
  '--disable-accelerated-video-decode',
  '--disable-accelerated-video-encode',
  `--${LINUX_X11_RELAUNCH_MARKER}`,
];
const LINUX_X11_STRIP_SWITCHES = [
  'ozone-platform',
  'disable-gpu',
  'disable-gpu-compositing',
  'disable-accelerated-video-decode',
  'disable-accelerated-video-encode',
  'disable-features',
  LINUX_X11_RELAUNCH_MARKER,
];
const LINUX_X11_STRIP_VALUE_SWITCHES = ['ozone-platform', 'disable-features'];
let linuxX11StartupFlagsSkippedInDev = false;

function hasProcessSwitch(name) {
  const prefix = `--${name}`;
  return process.argv.some((arg) => arg === prefix || arg.startsWith(`${prefix}=`));
}

function hasProcessSwitchValue(name, value) {
  return process.argv.some((arg, index) => {
    if (arg === `--${name}=${value}`) return true;
    if (arg === `--${name}` && process.argv[index + 1] === value) return true;
    return false;
  });
}

function getLinuxX11DisableFeaturesValue() {
  return mergeCommaSeparatedSwitchValues(
    collectSwitchValues(process.argv, 'disable-features'),
    LINUX_X11_REQUIRED_DISABLE_FEATURES,
  );
}

function getProcessDisableFeaturesSet() {
  return new Set(mergeCommaSeparatedSwitchValues(
    collectSwitchValues(process.argv, 'disable-features'),
    [],
  ).split(',').filter(Boolean));
}

function appendLinuxCompatibilityCommandLineSwitches() {
  for (const name of LINUX_COMPATIBILITY_SWITCHES) {
    app.commandLine.appendSwitch(name);
  }
}

function appendLinuxX11CommandLineSwitches() {
  app.commandLine.appendSwitch('ozone-platform', 'x11');
  app.commandLine.appendSwitch('disable-accelerated-video-decode');
  app.commandLine.appendSwitch('disable-accelerated-video-encode');
  app.commandLine.appendSwitch('disable-features', getLinuxX11DisableFeaturesValue());
}

function buildLinuxCompatibilityRelaunchArgs(enabled) {
  const names = [...LINUX_COMPATIBILITY_STRIP_SWITCHES, LINUX_COMPATIBILITY_RELAUNCH_MARKER];
  const args = stripSwitches(process.argv.slice(1), names);
  if (enabled) {
    args.push(...LINUX_COMPATIBILITY_SWITCHES.map((name) => `--${name}`));
    args.push(`--${LINUX_COMPATIBILITY_RELAUNCH_MARKER}`);
  }
  return args;
}

function buildLinuxX11RelaunchArgs() {
  const args = stripSwitches(process.argv.slice(1), LINUX_X11_STRIP_SWITCHES, LINUX_X11_STRIP_VALUE_SWITCHES);
  args.push(...LINUX_X11_SWITCH_ARGS);
  const disableFeatures = getLinuxX11DisableFeaturesValue();
  if (disableFeatures) args.push(`--disable-features=${disableFeatures}`);
  return args;
}

function shouldUseLinuxX11ForCurrentProcess(config) {
  if (process.platform !== 'linux') return false;
  if (process.env.NEKO_FORCE_X11 === '1') return true;
  if (hasProcessSwitchValue('ozone-platform', 'x11')) return true;
  if (linuxX11StartupFlagsSkippedInDev) return false;
  if (shouldAutoFallbackToX11ForWayland({
    process,
    allowUnverifiedWaylandSetShape: app.isPackaged !== true,
  })) return true;
  return config?.linuxForceX11 === true;
}

function relaunchApp(reason, args, options = {}) {
  if (!app.isPackaged) {
    log(`[dev] ${reason}: 未打包环境跳过 app.relaunch()，继续当前进程（Electron/Chromium 启动参数为 best-effort）`);
    return false;
  }
  if (Array.isArray(args)) {
    app.relaunch({ args });
  } else {
    app.relaunch();
  }
  if (options.immediateExit) {
    app.exit(0);
  } else {
    requestAppQuit(reason);
  }
  return true;
}

function ensureLinuxCompatibilityStartupFlags(config) {
  if (process.platform !== 'linux' || config?.compatibilityMode !== true) return false;
  if (hasProcessSwitch(LINUX_COMPATIBILITY_RELAUNCH_MARKER)) return false;
  const missing = LINUX_COMPATIBILITY_SWITCHES.filter((name) => !hasProcessSwitch(name));
  if (missing.length === 0) return false;
  const relaunchArgs = buildLinuxCompatibilityRelaunchArgs(true);
  log('Linux 兼容模式需要启动参数，正在 relaunch:', missing.join(', '));
  log('Linux 兼容模式 relaunch 参数:', relaunchArgs.filter((arg) => arg.startsWith('--')).join(' '));
  return relaunchApp('linux compatibility startup flags', relaunchArgs, { immediateExit: true });
}

function ensureLinuxX11StartupFlags(config) {
  if (process.platform !== 'linux') return false;
  const forceX11FromEnv = process.env.NEKO_FORCE_X11 === '1';
  const autoFallbackToX11 = !forceX11FromEnv && config?.linuxForceX11 !== true
    && shouldAutoFallbackToX11ForWayland({
      process,
      allowUnverifiedWaylandSetShape: app.isPackaged !== true,
    });
  const forceX11 = config?.linuxForceX11 === true || forceX11FromEnv || autoFallbackToX11;
  if (!forceX11) return false;

  const hasX11Ozone = hasProcessSwitchValue('ozone-platform', 'x11');
  const missing = [];
  if (!hasX11Ozone) missing.push('ozone-platform=x11');
  if (hasProcessSwitch('disable-gpu')) missing.push('remove-disable-gpu');
  if (hasProcessSwitch('disable-gpu-compositing')) missing.push('remove-disable-gpu-compositing');
  for (const name of [
    'disable-accelerated-video-decode',
    'disable-accelerated-video-encode',
  ]) {
    if (!hasProcessSwitch(name)) missing.push(name);
  }
  const disabledFeatures = getProcessDisableFeaturesSet();
  for (const feature of LINUX_X11_REQUIRED_DISABLE_FEATURES) {
    if (!disabledFeatures.has(feature)) missing.push(`disable-features:${feature}`);
  }
  if (!hasProcessSwitch(LINUX_X11_RELAUNCH_MARKER)) missing.push(LINUX_X11_RELAUNCH_MARKER);
  if (missing.length === 0) {
    process.env.NEKO_FORCE_X11 = '1';
    return false;
  }

  const relaunchArgs = buildLinuxX11RelaunchArgs();
  if (autoFallbackToX11) {
    const patchStatus = getWaylandSetShapePatchStatus({ process });
    log('Linux Wayland setShape patch 未验证，自动降级到 X11/XWayland:', JSON.stringify({
      reason: patchStatus.reason,
      electronVersion: patchStatus.electronVersion,
      compositor: patchStatus.compositor,
      execSha256: patchStatus.execSha256,
    }));
  }
  log('Linux X11 模式需要初始启动参数，正在 relaunch:', missing.join(', '));
  log('Linux X11 relaunch 参数:', relaunchArgs.filter((arg) => arg.startsWith('--')).join(' '));
  if (app.isPackaged || forceX11FromEnv || autoFallbackToX11) {
    process.env.NEKO_FORCE_X11 = '1';
  }
  const relaunched = relaunchApp('linux x11 startup flags', relaunchArgs, { immediateExit: true });
  if (!relaunched && !forceX11FromEnv && !autoFallbackToX11 && !hasX11Ozone) {
    linuxX11StartupFlagsSkippedInDev = true;
    log('[dev] Linux X11 初始 argv 未实际应用，本次按当前 Wayland/X11 运行态继续');
  }
  return relaunched;
}

const startupConfig = (() => {
  try {
    return normalizeStartupConfig(readCoreConfigRaw().config);
  } catch (e) {
    console.warn('启动配置读取失败:', e.message);
    return normalizeStartupConfig(null);
  }
})();

ensureLinuxCompatibilityStartupFlags(startupConfig);
ensureLinuxX11StartupFlags(startupConfig);

// ===== GPU 缓存修复（解决跨屏幕时 GPU cache creation failed 错误） =====
// 设置 GPU 缓存路径到用户数据目录，避免权限问题
app.commandLine.appendSwitch('gpu-cache-path', path.join(app.getPath('userData'), 'gpu-cache'));
// 禁用 GPU shader 磁盘缓存（如果仍有问题）
// app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');

app.commandLine.appendSwitch('calculate-native-win-occlusion', 'false');

// ===== 媒体自动播放 =====
// TTS / realtime audio is rendered from the Pet window, while the user gesture
// can originate from global hotkeys or the separate Chat window. Set the
// Chromium policy globally so every BrowserWindow can play response audio.
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

// ===== 图形兼容模式 =====
// Windows：沿用旧兼容模式，避免透明窗口覆盖后台视频时触发白屏。
// Linux：用于虚拟 GPU / 驱动黑名单 / GPU sandbox 初始化失败的环境；
// 这些开关必须出现在初始 argv 中，因此由 ensureLinuxCompatibilityStartupFlags() relaunch 注入。
process.env.NEKO_COMPATIBILITY_MODE = startupConfig.compatibilityMode === true ? '1' : '0';
if (startupConfig.compatibilityMode === true) {
  if (process.platform === 'win32') {
    app.commandLine.appendSwitch('disable-gpu-compositing');
    app.commandLine.appendSwitch('disable-direct-composition');
    log('Windows: 兼容模式已启用（禁用 GPU 合成 + DirectComposition）');
  } else if (process.platform === 'linux') {
    appendLinuxCompatibilityCommandLineSwitches();
    log('Linux: 兼容模式已启用（绕过 GPU 黑名单 + 禁用 GPU sandbox）');
  }
}

// ===== Linux 透明窗口支持 =====
// enable-transparent-visuals: 透明窗口前置（X11 需要 ARGB visual；Wayland 有 compositor 处理）
// 强力穿透模式：只负责强制 X11/XWayland，以绕过 Wayland 下置顶/AOT 限制。
if (process.platform === 'linux') {
  app.commandLine.appendSwitch('enable-transparent-visuals');

  // Wayland 原生穿透支持（通过 patched Electron 的 setShape → wl_surface_set_input_region）
  // 如果用户明确要求 X11，则强制 X11
  const forceX11 = shouldUseLinuxX11ForCurrentProcess(startupConfig);

  if (forceX11) {
    process.env.NEKO_FORCE_X11 = '1';
    appendLinuxX11CommandLineSwitches();
    console.log('Linux: 强力穿透模式已启用（X11）');
    log('Linux: X11 模式已禁用 VAAPI 视频加速并保留 WebGL/GPU 渲染');
  } else {
    const patchStatus = getWaylandSetShapePatchStatus({ process });
    console.log('Linux: 使用 Wayland 原生穿透支持（patched Electron）');
    log('Linux: Wayland setShape patch 状态:', JSON.stringify({
      verified: patchStatus.verified,
      forced: patchStatus.forced,
      disabled: patchStatus.disabled,
      reason: patchStatus.reason,
      electronVersion: patchStatus.electronVersion,
      compositor: patchStatus.compositor,
      execSha256: patchStatus.execSha256,
    }));
  }

  log('Linux: 透明窗口支持已初始化');
}

const feedbackModule = require('./feedback');
const windowManager = require('./window-manager');
const { isLinuxWaylandRuntime } = windowManager;
const ipcRouter = require('./ipc-router');
const avatarToolCursorService = require('./avatar-tool-cursor-service');
const tutorialGlobalOverlayService = require('./tutorial-global-overlay-service');
const { createAutostartService } = require('./autostart-service');

// ===== 安全：全局导航白名单 =====
// 所有窗口已统一为 nodeIntegration:false + contextIsolation:true（见 window-manager.js /
// feedback.js / hotkey-manager.js 的 webPreferences），不再存在 nodeIntegration RCE 链。
// 导航白名单作为纵深防御保留：所有 webContents 只允许导航到本机来源
// （127.0.0.1/localhost）或 data:/about:/file: 等安全 scheme，外部链接由各自的
// 窗口守卫（installNavigationShortcutGuard）改用系统浏览器打开。
const NAVIGATION_ALLOWED_HOSTS = new Set(['127.0.0.1', 'localhost', '::1']);
function isNavigationAllowed(url) {
  try {
    if (!url) return true;
    if (url.startsWith('data:') || url.startsWith('about:') || url.startsWith('blob:')) return true;
    const u = new URL(url);
    if (u.protocol === 'file:' || u.protocol === 'devtools:') return true;
    // 挽留窗自定义动作 scheme，由其自己的 will-navigate 监听拦截处理
    if (u.protocol === 'neko-exit-retention:') return true;
    if (u.protocol === 'http:' || u.protocol === 'https:') {
      return NAVIGATION_ALLOWED_HOSTS.has(u.hostname.toLowerCase());
    }
    return false;
  } catch (_) {
    return false;
  }
}

app.on('web-contents-created', (_event, contents) => {
  contents.on('will-navigate', (event, url) => {
    if (!isNavigationAllowed(url)) {
      try { log('[安全] 拦截非白名单导航:', url); } catch (_) {}
      event.preventDefault();
    }
  });
});

// 硬性限制：originalUrl 是 nodeIntegration 窗口的主加载来源，只允许 loopback；
// 非 loopback（含用户自定义远程 URL）一律拒绝并回退到本机默认后端
function sanitizeOriginalUrl(url, fallbackUrl) {
  try {
    if (url) {
      const u = new URL(url);
      if ((u.protocol === 'http:' || u.protocol === 'https:') && NAVIGATION_ALLOWED_HOSTS.has(u.hostname.toLowerCase())) {
        return url;
      }
      try { log('[安全] originalUrl 非 loopback，已拒绝:', url); } catch (_) {}
    }
  } catch (_) {
    try { log('[安全] originalUrl 解析失败，已拒绝:', url); } catch (_) {}
  }
  return fallbackUrl || '';
}
// 旧 compact 常驻球已停用；minimized 态毛线球仍复用 COMPACT_CHAT_BALL_CHANNELS
// 作为独立球窗口管线。SHOW/HIDE 可兜底旧入口，CLICK/RESTORE_* 是当前折叠恢复主链路。
const { WINDOW_CONTROL_CHANNELS, AUTOSTART_CHANNELS, TOAST_CHANNELS, JUKEBOX_CHANNELS, SUBTITLE_CHANNELS, PET_CHANNELS, CHAT_ACTION_CHANNELS, WS_PROXY_CHANNELS, TUTORIAL_OVERLAY_CHANNELS, COMPACT_CHAT_BALL_CHANNELS } = require('./ipc-channels');
const systemCursorVisibilityService = createSystemCursorVisibilityService({
  app,
  platform: process.platform,
  spawn,
  log,
  shouldDeferRestore: () => avatarToolCursorService.isNativeCursorHideActive(),
});
const powerSaveBlockerService = createPowerSaveBlockerService({
  powerSaveBlocker,
  log,
});

ipcRouter.setupIPCRouter({
  getWindows: () => windowManager.getWindows(),
  log,
});

const avatarBoundsSyncSubscribers = new Map();
const avatarBoundsSyncSubscriberCloseCleanup = new Set();
let latestAvatarBoundsSyncPayload = null;
let latestAvatarBoundsSyncPayloadKnown = false;

function hasAvatarBoundsSyncSubscribers() {
  return avatarBoundsSyncSubscribers.size > 0;
}

function cloneAvatarBoundsSyncPayload(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const cloned = { ...payload };
  if (payload.bounds && typeof payload.bounds === 'object') {
    cloned.bounds = { ...payload.bounds };
  }
  if (payload.display && typeof payload.display === 'object') {
    cloned.display = { ...payload.display };
    if (payload.display.bounds && typeof payload.display.bounds === 'object') {
      cloned.display.bounds = { ...payload.display.bounds };
    }
    if (payload.display.workArea && typeof payload.display.workArea === 'object') {
      cloned.display.workArea = { ...payload.display.workArea };
    }
  }
  return cloned;
}

function sendLatestAvatarBoundsSyncToSubscriber(win) {
  if (!latestAvatarBoundsSyncPayloadKnown || !win || win.isDestroyed() || !win.webContents) return;
  try {
    win.webContents.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC, cloneAvatarBoundsSyncPayload(latestAvatarBoundsSyncPayload));
  } catch (_) {}
}

function notifyAvatarBoundsSyncSubscriptionState() {
  const pet = windowManager.getPetWindow();
  if (!pet || pet.isDestroyed() || !pet.webContents) return;
  try {
    pet.webContents.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC_SUBSCRIPTION, {
      active: hasAvatarBoundsSyncSubscribers(),
    });
  } catch (_) {}
}

let tray;
let mainWindow; // 兼容引用，指向 petWindow（逐步迁移中）
let loadingWindow; // 加载窗口
let exitRetentionWindow; // 退出挽留确认窗口
let exitRetentionConfirmPromise = null;
let loadingWindowCloseIsInternal = false;
let loadingWindowStatus = {
  title: '',
  detail: '',
};
let isMobileMode = false;
let isStreamerMode = false; // 窗口模式状态
let isGlobalAlwaysOnTop = true; // 全局置顶开关
let originalUrl = '';
let wsProxySessionEpoch = 0;

ipcMain.on(WS_PROXY_CHANNELS.NEXT_SESSION_EPOCH, (event) => {
  wsProxySessionEpoch += 1;
  event.returnValue = wsProxySessionEpoch;
});

const {
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
} = createTopCoordinator({
  app,
  BrowserWindow,
  getGlobalAlwaysOnTop: () => isGlobalAlwaysOnTop,
  getLoadingWindow: () => loadingWindow,
  getMainWindow: () => mainWindow,
  log,
  process,
  windowManager,
});

// ===== N.E.K.O 后端发现状态 =====
const NEKO_DEFAULT_PORTS = {
  MAIN_SERVER_PORT: 48911,
  MEMORY_SERVER_PORT: 48912,
  TOOL_SERVER_PORT: 48915,
  USER_PLUGIN_SERVER_PORT: 48916,
  OPENFANG_PORT: 50051,
};
// 当前生效端口映射（由 port_plan 事件或健康扫描更新）
let nekoActivePorts = { ...NEKO_DEFAULT_PORTS };
// 自定义 URL 覆盖（客户端侧，优先于端口配置）
let customUrlOverrides = {
  MAIN_SERVER_URL: null,
  MEMORY_SERVER_URL: null,
  TOOL_SERVER_URL: null,
  USER_PLUGIN_SERVER_URL: null,
};
/**
 * 解析指定服务器的有效 URL。优先级：自定义 URL > 自定义端口 > 默认端口
 */
function resolveServerUrl(serverKey) {
  const urlKey = serverKey + '_URL';
  if (customUrlOverrides[urlKey]) {
    let url = customUrlOverrides[urlKey];
    if (serverKey === 'MAIN_SERVER' && !url.endsWith('/')) url += '/';
    return url;
  }
  const portKey = serverKey + '_PORT';
  const port = nekoActivePorts[portKey] || NEKO_DEFAULT_PORTS[portKey];
  return `http://localhost:${port}/`;
}

/**
 * 探测一个 URL 是否可达（HEAD 请求 + 短超时）。
 * 用于"自定义服务器地址"保存后，主动告诉用户目标地址是否在线，
 * 避免点"重新加载"后 Pet 透明窗口加载失败看起来像程序崩了。
 * @param {string} url
 * @param {number} timeoutMs
 * @returns {Promise<{ok: true, statusCode: number}>}
 */
function probeUrlReachable(url, timeoutMs = 3000) {
  return new Promise((resolve, reject) => {
    let urlObj;
    try { urlObj = new URL(url); } catch (e) { return reject(new Error('URL 格式非法')); }
    const mod = urlObj.protocol === 'https:' ? https : http;
    const req = mod.request({
      method: 'HEAD',
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === 'https:' ? 443 : 80),
      path: urlObj.pathname || '/',
      timeout: timeoutMs,
    }, (res) => {
      res.resume();
      resolve({ ok: true, statusCode: res.statusCode });
    });
    req.on('error', (err) => reject(err));
    req.on('timeout', () => { req.destroy(new Error('连接超时')); });
    req.end();
  });
}
// ===== 存储启动闸门（桌面端只观察，不参与迁移决策） =====
const getLoadingDataURL = createLoadingWindowDataUrlBuilder({
  fs,
  getApp: () => app,
  getCurrentLanguage: () => currentLanguage,
  getLoadingWindowStatus: () => loadingWindowStatus,
  loadingText,
  log,
  path,
});

const {
  bindWindowDisplayRecovery,
  boundsApproximatelyEqual,
  canUseSetShape,
  getInputRegionBackend,
  getFullscreenDisplayBounds,
  getPetBottomExpandedWorkArea,
  shouldUseNativeIgnoreMouse,
} = createWindowControlIpc({
  BrowserWindow,
  allowUnverifiedWaylandSetShape: app.isPackaged !== true,
  ipcMain,
  log,
  screen,
  WINDOW_CONTROL_CHANNELS,
  PET_CHANNELS,
  applyTopOn,
  getMainWindow: () => mainWindow,
  isLinuxWaylandRuntime,
  windowManager,
});

const {
  _ignoreStateByWindow,
  _lastShapeByWindow,
  _lastShapeMetaByWindow,
  applyWindowShape,
  getEffectiveWindowShapeRects,
  getNativeWindowShapeRects,
  setWindowIgnoreMouseEvents,
} = createWindowHostIpc({
  BrowserWindow,
  applyTopOn,
  canUseSetShape,
  getInputRegionBackend,
  getFullscreenDisplayBounds,
  getMainWindow: () => mainWindow,
  getPetBottomExpandedWorkArea,
  ipcMain,
  log,
  resetToastIdleTimer: _resetToastIdleTimer,
  screen,
  shouldUseNativeIgnoreMouse,
  windowManager,
});

const {
  attachStorageGateToPetWindow,
  ensureReactChatWindow,
  guardStorageStartupGate,
  isStorageMaintenanceProtectionActive,
  maybeCreateStartupReactChat,
  setReloadPetAfterMaintenanceReady,
  startStorageGatePolling,
  stopStorageGatePolling,
} = createStorageGate({
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
  getMainWindow: () => mainWindow,
  getOriginalUrl: () => originalUrl,
  // #1：启动时恢复上次选择的聊天窗口形态（compact/full）。thunk 运行时才读 appConfig，安全。
  getInitialChatSurfaceMode: () => (appConfig && appConfig.chatSurfaceMode === 'full') ? 'full' : 'compact',
  // 球态下托盘 force-show 走真正的恢复（等价点球）。函数声明被 hoist，thunk 运行时才调用，安全。
  restoreReactChatFromBall: () => restoreReactChatFromBallProgrammatic(),
  isReactChatSelfMinimizedBallActive: () => isReactChatSelfMinimizedBallActive(),
});

// 托盘「打开对话框」在毛线球态走 route-through-restore 时置位（见 restoreReactChatFromBallProgrammatic）。
// 普通点球不置位，仍走球自身「bounce 完 + RESTORE_ACK」的自隐握手。
let pendingProgrammaticBallRestore = false;
// 拖动毛线球期间缓存「球 + 载体对话框」的初始尺寸。DRAG_MOVE 每帧复用它做 setBounds，
// 不再每帧 getBounds() 回读尺寸 —— 高 DPI 下 logical↔physical 取整往返每帧 +1px，回喂会
// 累积漂移，球与载体逐帧不断变大（用户报「拖动时窗口自动扩大且透明」的真因）。
// 等价于 window-control-ipc.js 拖拽里「dragBounds 只在起始读一次」的做法。DRAG_END 清空。
let compactChatBallDragSizes = null;
// 收掉毛线球的统一出口：任何「结束一次球会话」的路径都必须清掉 DRAG_MOVE 起始缓存的拖动尺寸。
// 否则下次球态会跳过首帧 getBounds() 快照、复用上一会话被高 DPI 取整 / 载体化的陈旧尺寸，
// 第一帧拖动就把旧尺寸写回新球 + 载体（用户报「拖动时窗口逐帧变大」的复发路径）。除 HIDE IPC
// 外，hide-all / 直接恢复 / 程序化恢复 / 关闭对话框 / Linux 折叠接管等多条路径都直接 hide 球 ——
// 全部走这里兜住，避免漏一条就让缓存跨会话泄漏。先清缓存再 hide：即便 hide 抛错缓存也已清掉。
function teardownCompactChatBallWindow() {
  compactChatBallDragSizes = null;
  windowManager.hideCompactChatBallWindow();
}
// window-manager 自身的球 show/hide（full-surface 切换隐藏、兼容模式 destroy+recreate、内部
// 复用 showInactive 等）不经过上面的 main 层 teardown wrapper。把「清拖动缓存」注册成 show 时
// 的回调，让所有球会话起点（无论由谁触发 show）都重置缓存，作为跨模块兜底，根除 window-manager
// 直接 hide / recreate 后下次球态复用陈旧尺寸。见 window-manager.showCompactChatBallWindow。
if (typeof windowManager.setCompactChatBallDragSizesReset === 'function') {
  windowManager.setCompactChatBallDragSizesReset(() => { compactChatBallDragSizes = null; });
}
var compactChatRestoreStateBySender = new Map();
var compactChatRestoreActiveSessionTime = Number.NaN;
function parseCompactChatRestoreSessionTimestamp(sessionValue) {
  if (typeof sessionValue !== 'string') return Number.NaN;
  var m = /^(\d+)-/.exec(sessionValue);
  if (!m) return Number.NaN;
  var v = Number(m[1]);
  return Number.isFinite(v) ? v : Number.NaN;
}
function getCompactChatRestoreStateForSender(senderId) {
  if (!Number.isFinite(senderId)) return null;
  var existing = compactChatRestoreStateBySender.get(senderId);
  if (!existing) {
    existing = {
      session: null,
      sessionTime: Number.NaN,
      sequence: 0,
      lastRestoreAction: 'none',
      lastRestoreSeenAt: 0,
    };
    compactChatRestoreStateBySender.set(senderId, existing);
  }
  return existing;
}
function setCompactChatRestoreSequenceState(senderState, incomingSeq) {
  if (!senderState || !Number.isFinite(incomingSeq)) return;
  if (!Number.isFinite(senderState.sequence) || incomingSeq > senderState.sequence) {
    senderState.sequence = incomingSeq;
  }
  senderState.lastRestoreSeenAt = Date.now();
}
function shouldIgnoreCompactChatRestorePayload(incomingSession, incomingSessionTime, senderState) {
  if (Number.isFinite(incomingSessionTime) && Number.isFinite(compactChatRestoreActiveSessionTime)
    && incomingSessionTime < compactChatRestoreActiveSessionTime) {
    return true;
  }
  if (!incomingSession || !senderState || !senderState.session) return false;
  if (!Number.isFinite(incomingSessionTime) || !Number.isFinite(senderState.sessionTime)) {
    return senderState.session !== incomingSession;
  }
  if (incomingSessionTime < senderState.sessionTime) return true;
  return false;
}
function isCompactChatCarrierHidden(chatWin) {
  if (!chatWin || chatWin.isDestroyed()) return true;
  try {
    if (typeof chatWin.isVisible === 'function' && !chatWin.isVisible()) return true;
    var opacity = Number(chatWin.getOpacity());
    if (Number.isFinite(opacity) && opacity <= 0.01) return true;
  } catch (_) {}
  return false;
}
let reactChatSelfMinimizedBallState = {
  active: false,
  webContentsId: null,
  screenRect: null,
  updatedAt: 0,
};
let compactChatTemporaryHiddenWebContents = null;
let compactChatTemporaryUnhideDeferredUntilHideAllRestore = false;

function sendCompactChatBallTemporarilyHiddenStateToPet(reason) {
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  if (!pet || pet.isDestroyed() || !pet.webContents) return;
  try {
    pet.webContents.send(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, {
      minimized: false,
      reason: reason || 'temporary-hidden',
      screenRect: null,
      timestamp: Date.now()
    });
  } catch (_) {}
}

function unbindCompactChatTemporaryHiddenWebContents() {
  const wc = compactChatTemporaryHiddenWebContents;
  if (!wc) return;
  try { wc.removeListener('destroyed', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
  try { wc.removeListener('did-navigate', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
  try { wc.removeListener('render-process-gone', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
  compactChatTemporaryHiddenWebContents = null;
}

function clearCompactChatTemporaryHiddenFromSenderLifecycle(reason) {
  unbindCompactChatTemporaryHiddenWebContents();
  if (isHideAllUIHiddenActive()) {
    compactChatTemporaryUnhideDeferredUntilHideAllRestore = true;
    sendCompactChatBallTemporarilyHiddenStateToPet(reason || 'temporary-hidden-sender-gone-hide-all');
    return;
  }
  compactChatTemporaryUnhideDeferredUntilHideAllRestore = false;
  try { windowManager.setCompactChatBallTemporarilyHidden(false); } catch (_) {}
  if (process.platform === 'linux' && isReactChatSelfMinimizedBallTracked()) {
    try { windowManager.setReactChatSelfMinimizedBallTemporarilyHidden(false); } catch (_) {}
    if (isReactChatSelfMinimizedBallActive()) {
      sendReactChatSelfMinimizedBallStateToPet(reason || 'temporary-hidden-sender-gone');
    } else {
      sendCompactChatBallTemporarilyHiddenStateToPet(reason || 'temporary-hidden-sender-gone');
    }
    return;
  }
  sendCompactChatBallMinimizedStateToPet(reason || 'temporary-hidden-sender-gone');
}

function isHideAllUIHiddenActive() {
  try {
    return !!(typeof hotkeyManager.isUIHidden === 'function' && hotkeyManager.isUIHidden());
  } catch (_) {
    return false;
  }
}

function clearCompactChatDeferredTemporaryUnhideAfterHideAllRestore() {
  if (!compactChatTemporaryUnhideDeferredUntilHideAllRestore) return false;
  compactChatTemporaryUnhideDeferredUntilHideAllRestore = false;
  try { windowManager.setCompactChatBallTemporarilyHidden(false); } catch (_) {}
  if (process.platform === 'linux' && isReactChatSelfMinimizedBallTracked()) {
    try { windowManager.setReactChatSelfMinimizedBallTemporarilyHidden(false); } catch (_) {}
  }
  return true;
}

function handleCompactChatTemporaryHiddenSenderGone() {
  clearCompactChatTemporaryHiddenFromSenderLifecycle('temporary-hidden-sender-gone');
}

function bindCompactChatTemporaryHiddenWebContents(wc) {
  if (!wc || compactChatTemporaryHiddenWebContents === wc) return;
  unbindCompactChatTemporaryHiddenWebContents();
  compactChatTemporaryHiddenWebContents = wc;
  try { wc.once('destroyed', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
  try { wc.once('did-navigate', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
  try { wc.once('render-process-gone', handleCompactChatTemporaryHiddenSenderGone); } catch (_) {}
}

function isExternalCompactChatBallActive() {
  try {
    const ball = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
    return !!(ball && !ball.isDestroyed() && ball.isVisible());
  } catch (_) {
    return false;
  }
}

function isReactChatSelfMinimizedBallTracked() {
  if (process.platform !== 'linux') return false;
  if (!reactChatSelfMinimizedBallState.active) return false;
  if (isExternalCompactChatBallActive()) return false;
  const chat = windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null;
  if (!chat || chat.isDestroyed() || !chat.webContents) return false;
  return reactChatSelfMinimizedBallState.webContentsId === chat.webContents.id;
}

function isReactChatSelfMinimizedBallActive() {
  if (!isReactChatSelfMinimizedBallTracked()) return false;
  const chat = windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null;
  if (!chat || chat.isDestroyed()) return false;
  try {
    return chat.isVisible();
  } catch (_) {
    return false;
  }
}

function isAnyCompactChatBallActiveForProgrammaticRestore() {
  return isExternalCompactChatBallActive() || isReactChatSelfMinimizedBallActive();
}

function getCompactChatBallVisualMetrics(bounds) {
  // 独立球窗口有透明动画余量；拖拽/恢复锚点必须按可见球矩形计算。
  let raw = null;
  try {
    raw = typeof windowManager.getCompactChatBallVisualOffset === 'function'
      ? windowManager.getCompactChatBallVisualOffset()
      : null;
  } catch (_) {
    raw = null;
  }
  const width = Math.max(1, Math.round(Number(bounds && bounds.width) || 1));
  const height = Math.max(1, Math.round(Number(bounds && bounds.height) || 1));
  const size = Math.max(1, Math.round(Number(raw && raw.size) || Math.min(width, height)));
  const offsetX = Math.max(0, Math.round(Number(raw && raw.x) || 0));
  const offsetY = Math.max(0, Math.round(Number(raw && raw.y) || 0));
  const anchorSize = Math.max(size, Math.round(Number(raw && raw.anchorSize) || Math.max(width, height)));
  const anchorOffsetY = Math.max(
    0,
    Math.round(Number(raw && raw.anchorOffsetY) || Math.max(0, height - size - offsetY))
  );
  return { offsetX, offsetY, anchorOffsetY, size, anchorSize };
}

function getCompactChatBallAnchorBounds(ballWin) {
  if (!ballWin || ballWin.isDestroyed()) return null;
  try {
    const bounds = ballWin.getBounds();
    const visualMetrics = getCompactChatBallVisualMetrics(bounds);
    return {
      x: Math.round(bounds.x + visualMetrics.offsetX),
      y: Math.round(bounds.y + visualMetrics.offsetY - visualMetrics.anchorOffsetY),
      width: visualMetrics.anchorSize,
      height: visualMetrics.anchorSize,
    };
  } catch (_) {
    return null;
  }
}

function normalizeCompactChatScreenRect(rect) {
  if (!rect || typeof rect !== 'object') return null;
  const left = Math.round(Number(rect.left));
  const top = Math.round(Number(rect.top));
  const width = Math.round(Number(rect.width));
  const height = Math.round(Number(rect.height));
  if (![left, top, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  return {
    left,
    top,
    width,
    height,
    right: Math.round(Number.isFinite(Number(rect.right)) ? Number(rect.right) : left + width),
    bottom: Math.round(Number.isFinite(Number(rect.bottom)) ? Number(rect.bottom) : top + height),
  };
}

function getReactChatSelfMinimizedBallScreenRect() {
  if (!isReactChatSelfMinimizedBallActive()) return null;
  const stored = normalizeCompactChatScreenRect(reactChatSelfMinimizedBallState.screenRect);
  if (stored) return stored;
  const chat = windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null;
  if (!chat || chat.isDestroyed()) return null;
  try {
    const bounds = chat.getBounds();
    return normalizeCompactChatScreenRect({
      left: bounds.x,
      top: bounds.y,
      width: bounds.width,
      height: bounds.height,
    });
  } catch (_) {
    return null;
  }
}

function sendReactChatSelfMinimizedBallStateToPet(reason) {
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  if (!pet || pet.isDestroyed() || !pet.webContents) return;
  const screenRect = getReactChatSelfMinimizedBallScreenRect();
  try {
    pet.webContents.send(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, {
      minimized: !!screenRect,
      reason: reason || '',
      screenRect,
      timestamp: Date.now()
    });
  } catch (_) {}
}

function sendCompactChatBallMinimizedStateToPet(reason, ballWin = null) {
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  if (!pet || pet.isDestroyed() || !pet.webContents) return;
  const ball = ballWin || (windowManager.getWindows ? windowManager.getWindows().compactChatBall : null);
  let visible = false;
  let screenRect = null;
  try {
    visible = !!(ball && !ball.isDestroyed() && ball.isVisible());
    if (visible) {
      const bounds = ball.getBounds();
      const metrics = getCompactChatBallVisualMetrics(bounds);
      const left = Math.round(bounds.x + metrics.offsetX);
      const top = Math.round(bounds.y + metrics.offsetY);
      screenRect = {
        left,
        top,
        width: metrics.size,
        height: metrics.size,
        right: left + metrics.size,
        bottom: top + metrics.size
      };
    }
  } catch (_) {
    visible = false;
    screenRect = null;
  }
  try {
    pet.webContents.send(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, {
      minimized: visible,
      reason: reason || '',
      screenRect,
      timestamp: Date.now()
    });
  } catch (_) {}
}

function isCompactChatBallTemporaryHideRequested() {
  try {
    return !!(
      typeof windowManager.isCompactChatBallTemporaryHideRequested === 'function'
      && windowManager.isCompactChatBallTemporaryHideRequested()
    );
  } catch (_) {
    return false;
  }
}

function sendCompactChatBallEffectiveStateToPet(reason, ballWin = null) {
  if (isCompactChatBallTemporaryHideRequested()) {
    sendCompactChatBallTemporarilyHiddenStateToPet(reason || 'temporary-hidden');
    return;
  }
  if (process.platform === 'linux' && isReactChatSelfMinimizedBallActive()) {
    sendReactChatSelfMinimizedBallStateToPet(reason || '');
    return;
  }
  sendCompactChatBallMinimizedStateToPet(reason || '', ballWin);
}

function refreshCompactChatBallMinimizedStateAfterHideAllRestore() {
  clearCompactChatDeferredTemporaryUnhideAfterHideAllRestore();
  sendCompactChatBallEffectiveStateToPet('hide-all-restore');
}

function activateCompactChatBallFromMain() {
  const chat = windowManager.getReactChatWindow();
  if (!chat || chat.isDestroyed() || !chat.webContents) {
    log('[CompactChatBall] click ignored: react chat window unavailable');
    return false;
  }
  // CLICK 只转发给 reactChat preload，**不**在这里 hide ball / restore opacity。
  // 外部球路径下，preload 的 doExpand 在 chatWin 隐性（opacity=0）状态下用 stored surface（球位置）把
  // surface 定位好，再派 RESTORE_COMPLETE → main restore chatWin opacity 揭示对话框。
  // 独立球的 hide 与揭示解耦：球弹完 bounce 动画后自行 HIDE，但**仅在收到 RESTORE_ACK
  // 确认 restore 真的发生后**才隐藏（见 RESTORE_COMPLETE handler 与 preload-compact-chat-ball.js）。
  // 弹跳期再点球不再被特殊拦截：chat 侧 CLICK handler 在非 minimized 时已是 no-op（不会
  // 误折叠），球保持可点 —— 万一这次 CLICK 因 renderer 正在 reload 被丢弃，用户还能再点重试。
  try {
    log('[CompactChatBall] click forwarded to react chat (deferred opacity restore)');
    const ball = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
    chat.webContents.send(COMPACT_CHAT_BALL_CHANNELS.CLICK, {
      anchorBounds: getCompactChatBallAnchorBounds(ball),
    });
    return true;
  } catch (e) {
    log('[CompactChatBall] click forwarding failed:', e && e.message ? e.message : e);
    return false;
  }
}

// #179-1 托盘「打开对话框」force-show route-through-restore：
// 球态下对话框是 opacity-0 carrier（isVisible()=true 骗过 ensureReactChatWindow 的 !isVisible
// 判断），且单纯 setOpacity(1) 只会露出 88px 折叠球壳而非可用对话框。这里走「等价点球」的
// 真正恢复：转发 CLICK → chat preload 的 doExpand 在球位置展开对话框。区别于真实点球：没有
// pointer 事件 → 球不播 bounce、也不会靠「bounce 完 + RESTORE_ACK」自隐，所以置
// pendingProgrammaticBallRestore，让 RESTORE_COMPLETE handler 在确认 restore 后直接销毁球。
// 返回是否成功转发（chat 不可用时 false，调用方据此回退常规 show）。
function routeProgrammaticBallRestore() {
  // 就绪态：转发 CLICK 走真正恢复。置 flag 让 RESTORE_COMPLETE handler 在确认 restore 后销毁球；
  // 转发失败（chat 不可用）撤回 flag，避免误挂在下一次无关的 RESTORE_COMPLETE 上。
  pendingProgrammaticBallRestore = true;
  const routed = activateCompactChatBallFromMain();
  if (!routed) pendingProgrammaticBallRestore = false;
  return routed;
}

function restoreReactChatFromBallProgrammatic() {
  // [#180-review] 程序化恢复（托盘 force-show）不像真实点球能「再点重试」。
  const chat = windowManager.getReactChatWindow();
  if (!chat || chat.isDestroyed() || !chat.webContents) {
    return false;
  }
  let ready = false;
  try {
    const url = chat.webContents.getURL();
    ready = !!url && !chat.webContents.isLoading();
  } catch (_) { /* ignore */ }
  if (ready) {
    return routeProgrammaticBallRestore();
  }
  // [#180-review] renderer 正在 reload：此刻 send CLICK 会被丢弃（ipcRenderer.on(CLICK) 尚未注册），
  // doExpand 不跑、对话框不恢复。但**不能返回 false 落到 storage-gate 的常规 show fallback** ——
  // 球态对话框是 opacity-0 carrier、isVisible()===true，会骗过那条 !isVisible() 判断，fallback 退化成
  // 「只 focus 隐身 88px carrier」的 no-op（注释见 storage-gate force-show 分支）。改挂一次性
  // did-finish-load：renderer 就绪后（CLICK handler 已注册）再走真正恢复；返回 true 让 storage-gate
  // 别走 no-op fallback（独立球此间仍显示/可手动点，作视觉兜底，不会两头落空）。
  log('[CompactChatBall] renderer reloading; defer programmatic restore to did-finish-load');
  chat.webContents.once('did-finish-load', () => {
    // 球态已变（用户已手动点球恢复 / 关闭）→ 放弃，避免误置 pendingProgrammaticBallRestore 残留、
    // 污染下一次无关的折叠/恢复握手。
    if (!isAnyCompactChatBallActiveForProgrammaticRestore()) {
      log('[CompactChatBall] deferred programmatic restore aborted: ball no longer active');
      return;
    }
    const c = windowManager.getReactChatWindow();
    if (!c || c.isDestroyed() || !c.webContents) return;
    routeProgrammaticBallRestore();
  });
  return true;
}

function requestCompactKittenCompanionFromMain() {
  const chat = windowManager.getReactChatWindow();
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  let requested = false;
  try {
    if (chat && !chat.isDestroyed() && chat.webContents) {
      chat.webContents.send(COMPACT_CHAT_BALL_CHANNELS.REQUEST_COMPANION);
      requested = true;
    } else {
      log('[ExitRetention] compact kitten companion chat request skipped: react chat window unavailable');
    }
  } catch (e) {
    log('[ExitRetention] compact kitten companion chat request failed:', e && e.message ? e.message : e);
  }

  try {
    if (pet && !pet.isDestroyed() && pet.webContents) {
      pet.webContents.send(PET_CHANNELS.REQUEST_IDLE_RETURN_COMPANION);
      requested = true;
    } else {
      log('[ExitRetention] compact kitten companion pet request skipped: pet window unavailable');
    }
  } catch (e) {
    log('[ExitRetention] compact kitten companion pet request failed:', e && e.message ? e.message : e);
  }

  // 保险（修「先缩成毛球、再变小猫」卡死）：变成小猫会关闭会抢焦的挽留对话框、并让 pet 切到陪伴
  // 形态（pet/carrier 与球同为 screen-saver 级，形态切换会重排 z）。若此刻处于独立毛线球态，这些
  // 扰动可能让球失焦/掉层 → 点了没反应。这里仅在球确实活跃可见时初次 + 多次延迟重断言球的顶层
  // 与可交互，节奏对齐 F8 还原的 showBall，覆盖挽留窗口关闭 + pet 形态切换的焦点/z 扰动窗口期。
  // 必须用 isVisible() 守卫，不能无条件调 reassert：win32 隐藏球是 destroy（非球态 compactChatBall
  // 为 null），但 mac/Linux 的 hideCompactChatBallWindow 是 hide()、球实例仍存活（isVisible=false）——
  // 无条件 reassert 会被其内部「不可见则 showInactive」复活成一个本该隐藏的旧球（非毛球态点变成
  // 小猫时尤甚）。只有球当前可见（= 真正的独立毛线球态）才需要、也才安全地重断言。
  const reassertBallTop = () => {
    try {
      const ball = typeof windowManager.getWindows === 'function'
        ? windowManager.getWindows().compactChatBall : null;
      if (!ball || ball.isDestroyed() || !ball.isVisible()) return;
      if (typeof windowManager.reassertCompactChatBallTopForRestore === 'function') {
        windowManager.reassertCompactChatBallTopForRestore();
      }
    } catch (_) { /* ignore */ }
  };
  reassertBallTop();
  // 初次立即断言后，再在 ~120/300/500ms 各补一次：pet 切陪伴形态、挽留窗口关闭引起的 z/焦点
  // 重排并非同一帧完成，单次断言易被随后的扰动盖过。这三个时间点与 F8 还原的 showBall 同值，
  // 经验上足以覆盖该扰动窗口期（首帧 + 短/中/长三档兜底），无需精确——多断言几次只是 no-op。
  [120, 300, 500].forEach((ms) => {
    const to = setTimeout(reassertBallTop, ms);
    try { to.unref(); } catch (_) { /* ignore */ }
  });

  log('[ExitRetention] compact kitten companion requested:', requested);
  return requested;
}

const { confirmTrayExitWithRetention } = createExitRetentionPrompt({
  BrowserWindow,
  app,
  beginExitRetentionShutdown: (reason) => cleanupResources(reason, { destroyWindows: false, closeLogStream: false }),
  fs,
  getAppConfig: () => appConfig || getConfig(),
  getCurrentLanguage: () => currentLanguage,
  getMainWindow: () => mainWindow,
  getOriginalUrl: () => originalUrl,
  log,
  normalizeSupportedLanguage,
  path,
  requestCompactKittenCompanion: requestCompactKittenCompanionFromMain,
  t,
  tForLanguage,
});

const screenCaptureIpc = registerScreenCaptureIpc({
  BrowserWindow,
  desktopCapturer,
  ipcMain,
  log,
  shell,
  screen,
  isLinuxWaylandRuntime,
  windowManager,
});

// 跨平台活动信号 IPC（NEKO issue #1023）：背景 5s 采样 powerMonitor /
// get-windows / os.cpus() / nvidia-smi，preload-pet.js 通过
// neko:read-activity-signal 拉取缓存快照，再由 static/app-activity-signal.js
// 心跳上报到 NEKO 后端 /api/activity_signal。
registerActivitySignalIpc({ ipcMain, powerMonitor, log });

const hotkeyManager = createHotkeyManager({
  BrowserWindow,
  NEKO_DEFAULT_PORTS,
  TOAST_CHANNELS,
  app,
  createHotkeyWindowDataUrlBuilder,
  createPortSettingsDataUrlBuilder,
  fs,
  getAppConfig: () => appConfig || getConfig(),
  getCurrentLanguage: () => currentLanguage,
  getCustomUrlOverrides: () => customUrlOverrides,
  getIcon,
  getMainWindow: () => mainWindow,
  getOriginalUrl: () => originalUrl,
  globalShortcut,
  guardStorageStartupGate,
  ipcMain,
  log,
  onRestoreAllUI: refreshCompactChatBallMinimizedStateAfterHideAllRestore,
  path,
  probeUrlReachable,
  resolveServerUrl,
  saveConfig,
  screen,
  setWindowIgnoreMouseEvents,
  setOriginalUrl: (next) => { originalUrl = sanitizeOriginalUrl(next, originalUrl); },
  sendToToastWindow: _sendToToastWindow,
  t,
  trayMenuLocales,
});

if (typeof windowManager.setCompactChatBallReadyListener === 'function') {
  windowManager.setCompactChatBallReadyListener((reason) => {
    sendCompactChatBallEffectiveStateToPet(reason || 'compact-ball-ready');
  });
}

const {
  areHotkeysEnabled,
  createHotkeyWindow,
  createPortSettingsWindow,
  getPortSettingsWindow,
  initHotkeyIPC,
  loadHotkeyConfig,
  pushDarkModeToHotkeyWindow: _pushDarkModeToHotkeyWindow,
  registerGlobalHotkeys,
  setTutorialHotkeysSuppressed,
} = hotkeyManager;

async function applyProxySettings(useSystemProxy) {
  try {
    if (useSystemProxy) {
      // 使用系统代理
      await session.defaultSession.setProxy({ mode: 'system' });
      log('已启用系统代理');
    } else {
      // 不使用代理，直连 - 使用 proxyRules 更可靠
      await session.defaultSession.setProxy({
        proxyRules: 'direct://',
        proxyBypassRules: ''
      });
      log('已禁用系统代理（直连模式）');
    }

    // full 独立窗口走独立分区 session，代理同步配置，避免 full 页面加载/网络走与 compact 不同的链路。
    try {
      const fullSess = session.fromPartition(windowManager.FULL_CHAT_PARTITION);
      await fullSess.setProxy(useSystemProxy
        ? { mode: 'system' }
        : { proxyRules: 'direct://', proxyBypassRules: '' });
    } catch (_) { /* 分区 session 尚未初始化等 —— full 创建时仍走默认，忽略 */ }

    // 验证代理设置
    const proxyInfo = await session.defaultSession.resolveProxy('https://www.baidu.com');
    log('当前代理解析结果:', proxyInfo);
  } catch (err) {
    log('设置代理失败:', err.message);
  }
}

ipcMain.on('neko:show-subtitle', () => {
  log('[Main] 收到显示 Subtitle 请求');
  if (guardStorageStartupGate('showSubtitle')) return;
  windowManager.showSubtitleWindow(originalUrl, { isPackaged: app.isPackaged, log });
});

ipcMain.on('neko:hide-subtitle', () => {
  log('[Main] 收到隐藏 Subtitle 请求');
  windowManager.hideSubtitleWindow();
  if (typeof windowManager.hideSubtitleSettingsWindow === 'function') {
    windowManager.hideSubtitleSettingsWindow();
  }
});

ipcMain.on(SUBTITLE_CHANNELS.OPEN_SETTINGS, (event, data) => {
  if (guardStorageStartupGate('showSubtitleSettings')) return;
  if (typeof windowManager.showSubtitleSettingsWindow === 'function') {
    windowManager.showSubtitleSettingsWindow(originalUrl, data || {}, { isPackaged: app.isPackaged, log });
  }
});

ipcMain.on(SUBTITLE_CHANNELS.CLOSE_SETTINGS, () => {
  if (typeof windowManager.hideSubtitleSettingsWindow === 'function') {
    windowManager.hideSubtitleSettingsWindow();
  }
});

ipcMain.on(SUBTITLE_CHANNELS.SETTINGS_WINDOW_UPDATE, (event, data) => {
  if (typeof windowManager.sendSubtitleSettingsState === 'function') {
    windowManager.sendSubtitleSettingsState(data || {});
  }
});

// ===== Subtitle 窗口设置变更 → 转发到 Pet 窗口 =====
ipcMain.on(SUBTITLE_CHANNELS.SETTINGS_CHANGE, (event, data) => {
  const windows = windowManager.getWindows();
  const pet = windows.pet;
  if (pet && !pet.isDestroyed()) {
    pet.webContents.send(SUBTITLE_CHANNELS.SETTINGS_CHANGE, data);
  }
  if (data && data.type === 'toggle') {
    const chat = windows.chat;
    const fullChat = windows.fullChat;
    if (chat && !chat.isDestroyed()) {
      chat.webContents.send(SUBTITLE_CHANNELS.SETTINGS_CHANGE, data);
    }
    if (fullChat && !fullChat.isDestroyed()) {
      fullChat.webContents.send(SUBTITLE_CHANNELS.SETTINGS_CHANGE, data);
    }
  }
});

// Pet → Subtitle：状态同步
ipcMain.on(SUBTITLE_CHANNELS.STATE_SYNC, (event, data) => {
  const sub = windowManager.getWindows().subtitle;
  if (sub && !sub.isDestroyed()) {
    sub.webContents.send(SUBTITLE_CHANNELS.STATE_SYNC, data);
  }
  if (typeof windowManager.sendSubtitleSettingsState === 'function') {
    windowManager.sendSubtitleSettingsState(data);
  }
});

// ===== AgentHUD 按需显示/隐藏 =====
ipcMain.on('neko:show-agent-hud', () => {
  log('[Main] 收到显示 AgentHUD 请求');
  if (guardStorageStartupGate('showAgentHUD')) return;
  windowManager.showAgentHudWindow(originalUrl, { isPackaged: app.isPackaged, log });
});

ipcMain.on('neko:hide-agent-hud', () => {
  log('[Main] 收到隐藏 AgentHUD 请求');
  windowManager.hideAgentHudWindow();
});

// ===== React Chat 窗口 =====

const linuxModelManagerHiddenSenders = new Set();
const linuxModelManagerHiddenSenderCleanup = new Map();

function applyLinuxModelManagerHiddenState() {
  const hidden = linuxModelManagerHiddenSenders.size > 0;
  log('[Main] Linux Model Manager main UI hidden state:', hidden);
  if (typeof windowManager.setReactChatAutoShowSuppressed === 'function') {
    windowManager.setReactChatAutoShowSuppressed(hidden);
  }
  if (hidden) {
    avatarToolCursorService.stop();
  }
}

function releaseLinuxModelManagerHiddenSender(senderId, sender) {
  const cleanup = linuxModelManagerHiddenSenderCleanup.get(senderId);
  linuxModelManagerHiddenSenderCleanup.delete(senderId);
  if (sender && cleanup) {
    try { sender.removeListener('destroyed', cleanup); } catch (_) {}
  }
  return linuxModelManagerHiddenSenders.delete(senderId);
}

ipcMain.on('neko:create-react-chat', () => {
  log('[Main] 收到创建 React Chat 窗口请求');
  if (guardStorageStartupGate('createReactChat')) return;
  ensureReactChatWindow({ focus: true, reason: 'ipc' });
});

function hideReactChatFromMain({ userClosed = false, reason = 'manual' } = {}) {
  avatarToolCursorService.stop();
  if (userClosed && typeof windowManager.setReactChatUserClosed === 'function') {
    windowManager.setReactChatUserClosed(true);
  }
  teardownCompactChatBallWindow(); // 关闭对话框时一并收掉毛线球（球态下唯一可视入口）+ 清拖动缓存
  const win = windowManager.getReactChatWindow();
  if (win && !win.isDestroyed()) {
    // 复位球态可能残留的 setIgnoreMouseEvents(true)（dimReactChatForMinimize 在 Win32 设的 pass-through）：
    // 球态下从托盘「关闭对话框」走本路径退出，不经 restoreReactChatVisibilityFromMinimize 复位 →
    // 下次打开对话框会停在 click-through 不可交互。无条件复位（非球态本就 false，幂等）。
    try { win.setIgnoreMouseEvents(false); } catch (_) {}
    // 复位兼容模式 shape-dim 残留：球态下关闭不走 restore，_nekoCompatDimmedByShape 和 1x1 shape
    // 残留在窗口上，下次 tray 重新 show 同一窗口时会以 1x1 裁剪打开。清除 shape 并重置标记。
    if (win._nekoCompatDimmedByShape) {
      try { if (typeof win.setShape === 'function') win.setShape([]); } catch (_) {}
      win._nekoCompatDimmedByShape = false;
    }
    log('[Main] 隐藏 React Chat 窗口:', reason);
    win.hide();
  }
}

ipcMain.on('neko:hide-react-chat', (event) => {
  // 按发送方路由：full 独立窗口的关闭按钮（preload 0 改、复用同一 IPC）应隐藏 full 自己，
  // 否则只隐藏 compact、full 关不掉、按钮看着像坏了。
  try {
    const sender = event && event.sender ? BrowserWindow.fromWebContents(event.sender) : null;
    const full = windowManager.getFullChatWindow ? windowManager.getFullChatWindow() : null;
    if (sender && full && !full.isDestroyed() && sender === full) {
      if (typeof windowManager.hideFullChatWindow === 'function') windowManager.hideFullChatWindow();
      return;
    }
  } catch (_) { /* ignore，回退默认隐藏 compact */ }
  hideReactChatFromMain({ userClosed: true, reason: 'ipc' });
});

const pendingTutorialOverlayRelays = {
  chat: [],
  pet: [],
};
const pendingTutorialOverlayRelayFlushTimers = {
  chat: null,
  pet: null,
};
const TUTORIAL_OVERLAY_RELAY_FLUSH_RETRY_MS = 250;
let activeTutorialHotkeySuppressionRunId = '';
let activeTutorialHotkeySuppressionGeneration = 0;
const closedTutorialHotkeySuppressionRunIds = new Set();
let activeTutorialSystemCursorRunId = '';
let activeTutorialSystemCursorGeneration = 0;
let activeTutorialSystemCursorGenerationless = false;
const closedTutorialSystemCursorRunIds = new Set();

function rememberClosedTutorialHotkeyRunId(runId) {
  if (!runId) return;
  closedTutorialHotkeySuppressionRunIds.add(runId);
  if (closedTutorialHotkeySuppressionRunIds.size > 32) {
    const oldest = closedTutorialHotkeySuppressionRunIds.values().next().value;
    closedTutorialHotkeySuppressionRunIds.delete(oldest);
  }
}

function rememberClosedTutorialSystemCursorRunId(runId) {
  if (!runId) return;
  closedTutorialSystemCursorRunIds.add(runId);
  if (closedTutorialSystemCursorRunIds.size > 32) {
    const oldest = closedTutorialSystemCursorRunIds.values().next().value;
    closedTutorialSystemCursorRunIds.delete(oldest);
  }
}

function getTutorialLifecycleGeneration(payload) {
  const value = payload && (
    payload.lifecycleGeneration
    || payload.tutorialGeneration
    || payload.generation
  );
  const generation = Number(value);
  return Number.isFinite(generation) && generation > 0 ? Math.floor(generation) : 0;
}

function isTutorialLifecycleStartAction(action) {
  return action === 'yui_guide_tutorial_lifecycle_started'
    || action === 'yui_guide_tutorial_started'
    || action === 'avatar_floating_guide_started';
}

function clearTutorialHotkeySuppression(reason) {
  rememberClosedTutorialHotkeyRunId(activeTutorialHotkeySuppressionRunId);
  activeTutorialHotkeySuppressionRunId = '';
  activeTutorialHotkeySuppressionGeneration = 0;
  setTutorialHotkeysSuppressed(false, reason);
}

function clearTutorialSystemCursor(reason) {
  rememberClosedTutorialSystemCursorRunId(activeTutorialSystemCursorRunId);
  activeTutorialSystemCursorRunId = '';
  activeTutorialSystemCursorGeneration = 0;
  activeTutorialSystemCursorGenerationless = false;
  systemCursorVisibilityService.setHidden(false, reason);
}

function isTrustedTutorialRelaySender(event) {
  let senderWin = null;
  try {
    senderWin = event && event.sender ? BrowserWindow.fromWebContents(event.sender) : null;
  } catch (_) {}
  if (!senderWin || senderWin.isDestroyed()) return false;
  let senderUrl = '';
  try {
    senderUrl = senderWin.webContents && typeof senderWin.webContents.getURL === 'function'
      ? senderWin.webContents.getURL()
      : '';
  } catch (_) {}
  try {
    if (new URL(senderUrl).origin !== new URL(originalUrl).origin) return false;
  } catch (_) {
    return false;
  }

  const candidates = [
    typeof windowManager.getPetWindow === 'function' ? windowManager.getPetWindow() : null,
    typeof windowManager.getReactChatWindow === 'function' ? windowManager.getReactChatWindow() : null,
    typeof windowManager.getFullChatWindow === 'function' ? windowManager.getFullChatWindow() : null,
  ];
  return candidates.some(win => win && !win.isDestroyed() && win === senderWin);
}

function isCurrentTutorialSystemCursorRelay(runId, generation) {
  if (runId) {
    if (!activeTutorialSystemCursorRunId || runId !== activeTutorialSystemCursorRunId) {
      return false;
    }
    if (generation && activeTutorialSystemCursorGeneration && generation !== activeTutorialSystemCursorGeneration) {
      return false;
    }
    return true;
  }
  if (generation) {
    return !!activeTutorialSystemCursorGeneration && generation === activeTutorialSystemCursorGeneration;
  }
  return activeTutorialSystemCursorGenerationless && activeTutorialSystemCursorGeneration === 1;
}

function schedulePendingTutorialOverlayRelayFlush(label, getWindow) {
  const queue = pendingTutorialOverlayRelays[label];
  if (!queue || queue.length === 0 || pendingTutorialOverlayRelayFlushTimers[label]) return;
  pendingTutorialOverlayRelayFlushTimers[label] = setTimeout(() => {
    pendingTutorialOverlayRelayFlushTimers[label] = null;
    if (!queue || queue.length === 0) return;
    flushPendingTutorialOverlayRelays(label, getWindow);
    if (queue.length > 0) {
      schedulePendingTutorialOverlayRelayFlush(label, getWindow);
    }
  }, TUTORIAL_OVERLAY_RELAY_FLUSH_RETRY_MS);
  try { pendingTutorialOverlayRelayFlushTimers[label].unref(); } catch (_) {}
}

function clearPendingTutorialOverlayRelays() {
  pendingTutorialOverlayRelays.chat.splice(0);
  pendingTutorialOverlayRelays.pet.splice(0);
  Object.keys(pendingTutorialOverlayRelayFlushTimers).forEach((label) => {
    const timer = pendingTutorialOverlayRelayFlushTimers[label];
    if (!timer) return;
    clearTimeout(timer);
    try { timer.unref(); } catch (_) {}
    pendingTutorialOverlayRelayFlushTimers[label] = null;
  });
}

function flushPendingTutorialOverlayRelays(label, getWindow) {
  const queue = pendingTutorialOverlayRelays[label];
  if (!queue || queue.length === 0) return;
  const win = getWindow();
  if (!win || win.isDestroyed() || !win.webContents) return;
  const batch = queue.splice(0);
  batch.forEach((payload) => relayTutorialOverlayMessageToWindow(win, payload, label, getWindow));
}

function queueTutorialOverlayRelay(label, payload, getWindow) {
  const queue = pendingTutorialOverlayRelays[label];
  if (!queue) return false;
  queue.push(payload || {});
  if (queue.length > 80) queue.splice(0, queue.length - 80);
  const win = getWindow();
  if (!win || win.isDestroyed() || !win.webContents) {
    schedulePendingTutorialOverlayRelayFlush(label, getWindow);
    return true;
  }
  if (win && !win.isDestroyed() && win.webContents && typeof win.webContents.once === 'function') {
    try {
      win.webContents.once('did-finish-load', () => flushPendingTutorialOverlayRelays(label, getWindow));
    } catch (_) {}
  }
  return true;
}

function relayTutorialOverlayMessageToWindow(win, payload, label, getWindow) {
  if (!win || win.isDestroyed() || !win.webContents) {
    schedulePendingTutorialOverlayRelayFlush(label, getWindow || (() => null));
    return queueTutorialOverlayRelay(label, payload, getWindow || (() => null));
  }
  try {
    if (typeof win.webContents.isLoading === 'function' && win.webContents.isLoading()) {
      return queueTutorialOverlayRelay(label, payload, getWindow || (() => win));
    }
  } catch (_) {}
  try {
    win.webContents.send(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_PAGE, payload || {});
    return true;
  } catch (error) {
    log('[Main] 教程消息转发失败: ' + label + ': ' + (error && error.message ? error.message : error));
    return false;
  }
}

function syncTutorialHotkeySuppressionFromOverlayRelay(payload) {
  const detail = payload && typeof payload === 'object' ? payload : {};
  const action = detail.action;
  const runId = String(detail.tutorialRunId || '');
  const generation = getTutorialLifecycleGeneration(detail);
  if (action === 'yui_guide_tutorial_lifecycle_ended') {
    if (generation && activeTutorialHotkeySuppressionGeneration && generation !== activeTutorialHotkeySuppressionGeneration) {
      return;
    }
    if (runId && activeTutorialHotkeySuppressionRunId && runId !== activeTutorialHotkeySuppressionRunId) {
      return;
    }
    clearTutorialHotkeySuppression('tutorial-lifecycle-ended');
    return;
  }
  if (isTutorialLifecycleStartAction(action)) {
    if (runId && closedTutorialHotkeySuppressionRunIds.has(runId)) {
      return;
    }
    if (generation && activeTutorialHotkeySuppressionGeneration && generation < activeTutorialHotkeySuppressionGeneration) {
      return;
    }
    if (activeTutorialHotkeySuppressionRunId && runId && runId !== activeTutorialHotkeySuppressionRunId) {
      rememberClosedTutorialHotkeyRunId(activeTutorialHotkeySuppressionRunId);
    }
    activeTutorialHotkeySuppressionRunId = runId || activeTutorialHotkeySuppressionRunId;
    activeTutorialHotkeySuppressionGeneration = generation || activeTutorialHotkeySuppressionGeneration || 1;
    setTutorialHotkeysSuppressed(true, 'tutorial-lifecycle-started');
  }
}

function syncTutorialSystemCursorFromOverlayRelay(event, payload) {
  if (!isTrustedTutorialRelaySender(event)) {
    return;
  }
  const detail = payload && typeof payload === 'object' ? payload : {};
  const action = detail.action;
  const runId = String(detail.tutorialRunId || '');
  const generation = getTutorialLifecycleGeneration(detail);
  if (isTutorialLifecycleStartAction(action)) {
    if (runId && closedTutorialSystemCursorRunIds.has(runId)) {
      return;
    }
    if (generation && activeTutorialSystemCursorGeneration && generation < activeTutorialSystemCursorGeneration) {
      return;
    }
    if (activeTutorialSystemCursorRunId && runId && runId !== activeTutorialSystemCursorRunId) {
      clearTutorialSystemCursor('tutorial-lifecycle-replaced');
    }
    activeTutorialSystemCursorRunId = runId || activeTutorialSystemCursorRunId;
    activeTutorialSystemCursorGeneration = !runId && !generation
      ? 1
      : generation || activeTutorialSystemCursorGeneration || 1;
    activeTutorialSystemCursorGenerationless = !runId && !generation;
    return;
  }
  if (action === 'yui_guide_system_cursor_visibility') {
    if (!isCurrentTutorialSystemCursorRelay(runId, generation)) {
      return;
    }
    log('[SystemCursor] tutorial relay hidden=' + String(detail.hidden === true) + ' reason=' + String(detail.reason || 'tutorial'));
    systemCursorVisibilityService.setHidden(detail.hidden === true, detail.reason || 'tutorial');
    return;
  }
  if (action === 'yui_guide_tutorial_lifecycle_ended') {
    if (generation && activeTutorialSystemCursorGeneration && generation !== activeTutorialSystemCursorGeneration) {
      return;
    }
    if (runId && activeTutorialSystemCursorRunId && runId !== activeTutorialSystemCursorRunId) {
      return;
    }
    log('[SystemCursor] tutorial lifecycle ended restore reason=' + String(detail.reason || 'tutorial-lifecycle-ended'));
    clearTutorialSystemCursor(detail.reason || 'tutorial-lifecycle-ended');
  }
}

ipcMain.on(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_CHAT, (_event, payload) => {
  syncTutorialHotkeySuppressionFromOverlayRelay(payload);
  syncTutorialSystemCursorFromOverlayRelay(_event, payload);
  relayTutorialOverlayMessageToWindow(
    windowManager.getReactChatWindow(),
    payload,
    'chat',
    () => windowManager.getReactChatWindow()
  );
});

ipcMain.on(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_PET, (_event, payload) => {
  syncTutorialHotkeySuppressionFromOverlayRelay(payload);
  syncTutorialSystemCursorFromOverlayRelay(_event, payload);
  relayTutorialOverlayMessageToWindow(
    windowManager.getPetWindow(),
    payload,
    'pet',
    () => windowManager.getPetWindow()
  );
});

// COMPACT_CHAT_BALL_CHANNELS：
// - SHOW/HIDE/RAISE 旧路径 —— compact 态模型旁的悬浮入口已停用（buildDesktopCompactBallScreenRect
//   恒返回 null），SHOW 不会主动触发；HIDE/RAISE 保留作 no-op 兜底。
// - COLLAPSE_TAKEOVER 新路径 —— Win32 minimized 态毛线球折叠为独立窗口。原子地：
//   (1) showCompactChatBallWindow 在 payload.bounds 出现独立球窗口（在 chatWin 之上）；
//   (2) dimReactChatForMinimize 把对话框 setOpacity(0) 透明化（保持 visible —— 这样
//       DRAG_MOVE 中 setBounds 在 visible 透明窗口上完全可靠，避免 Win32 hidden
//       setBounds 不被 DWM 合成的隐患）。
//   Linux 不走该 takeover：setOpacity() 是 no-op，renderer 保留 chatWin 本体 88x88 折叠球。
// - CLICK 路径 —— 球点击触发恢复：restoreReactChatVisibility(opacity=1) + hide 球 + 转发
//   给 reactChat preload 触发 doExpand 把对话框 setBounds 回展开尺寸。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.SHOW, (_event, payload) => {
  if (typeof windowManager.isReactChatUserClosed === 'function'
    && windowManager.isReactChatUserClosed()) {
    log('[CompactChatBall] show ignored: react chat was closed by user');
    return;
  }
  const bounds = payload && payload.bounds;
  windowManager.showCompactChatBallWindow(originalUrl, bounds, {
    isPackaged: app.isPackaged,
    log,
  });
});

ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.HIDE, (event) => {
  const expectedBall = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
  const senderWin = BrowserWindow.fromWebContents(event.sender);
  if (expectedBall && !expectedBall.isDestroyed() && expectedBall.isVisible()) {
    // 允许两个合法 sender：球窗口自身（maybeHideBall 握手）和 chat 窗口
    // （hideDesktopCompactBallWindow 折叠清理）。chat 窗口 ID != 球窗口 ID 时
    // 会导致 HIDE 被拒绝、球无法被正确清理。
    const chatWin = windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null;
    const isBallSender = senderWin && senderWin === expectedBall;
    const isChatSender = senderWin && chatWin && senderWin === chatWin;
    if (!isBallSender && !isChatSender) return;
  }
  teardownCompactChatBallWindow(); // 球会话结束：清拖动尺寸缓存，下次球态按真实折叠尺寸重新缓存
  sendCompactChatBallMinimizedStateToPet('ball-hide');
});

ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.SET_TEMPORARY_HIDDEN, (event, payload = {}) => {
  const chatWin = windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null;
  const senderWin = event && event.sender ? BrowserWindow.fromWebContents(event.sender) : null;
  if (!chatWin || chatWin.isDestroyed() || senderWin !== chatWin) return;
  const hidden = !!(payload && payload.hidden === true);
  if (hidden) {
    compactChatTemporaryUnhideDeferredUntilHideAllRestore = false;
    bindCompactChatTemporaryHiddenWebContents(event.sender);
  } else {
    unbindCompactChatTemporaryHiddenWebContents();
  }
  const hideAllActive = isHideAllUIHiddenActive();
  if (!hidden && hideAllActive) {
    compactChatTemporaryUnhideDeferredUntilHideAllRestore = true;
    sendCompactChatBallTemporarilyHiddenStateToPet('temporary-hidden-hide-all');
    return;
  }
  compactChatTemporaryUnhideDeferredUntilHideAllRestore = false;
  windowManager.setCompactChatBallTemporarilyHidden(hidden);
  if (process.platform === 'linux' && isReactChatSelfMinimizedBallTracked()) {
    windowManager.setReactChatSelfMinimizedBallTemporarilyHidden(hidden);
  }
  if (hidden) {
    sendCompactChatBallTemporarilyHiddenStateToPet('temporary-hidden');
  } else {
    sendCompactChatBallEffectiveStateToPet('temporary-hidden-cleared');
  }
});

ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.RAISE, () => {
  windowManager.raiseCompactChatBallWindow();
});

ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.CLICK, () => {
  activateCompactChatBallFromMain();
});

// 折叠预热 —— preload-chat-react.js 在 collapseNativeForReactMinimized 入口派发。
// 立刻把对话框窗口隐藏（setOpacity(0) / 兼容模式 setShape 1x1）让它在 W.collapse
// 物理 setBounds 之前就不可见，避免用户看到 chatWin 从展开尺寸/位置跳到球目标位置的瞬移视觉。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.PRE_COLLAPSE_DIM, (_event, payload = {}) => {
  const payloadObj = payload && typeof payload === 'object' ? payload : {};
  const incomingRestoreSeq = Number(payloadObj.__compactChatRestoreSeq);
  const incomingSession = payloadObj && typeof payloadObj.__compactChatRestoreSession === 'string'
    ? payloadObj.__compactChatRestoreSession
    : '';
  const incomingSessionTime = parseCompactChatRestoreSessionTimestamp(incomingSession);
  const senderId = _event && _event.sender && Number.isFinite(_event.sender.id) ? _event.sender.id : null;
  if (senderId === null) return;
  {
    const currentChatWin = windowManager.getReactChatWindow();
    const senderWin = _event && _event.sender ? BrowserWindow.fromWebContents(_event.sender) : null;
    if (!currentChatWin || currentChatWin.isDestroyed() || senderWin !== currentChatWin) {
      return;
    }
    var senderState = getCompactChatRestoreStateForSender(senderId);
    if (shouldIgnoreCompactChatRestorePayload(incomingSession, incomingSessionTime, senderState)) {
      return;
    }
    if (incomingSession && senderState.session !== incomingSession) {
      senderState.session = incomingSession;
      senderState.sessionTime = incomingSessionTime;
      senderState.sequence = 0;
      senderState.lastRestoreAction = 'none';
    }
    if (senderState.lastRestoreAction === 'collapse' && isCompactChatCarrierHidden(currentChatWin)) {
      setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
      return;
    }
    if (Number.isFinite(incomingRestoreSeq) && incomingRestoreSeq <= senderState.sequence) {
      setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
      return;
    }
    if (Number.isFinite(incomingSessionTime)) {
      compactChatRestoreActiveSessionTime = incomingSessionTime;
    }
    setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
    senderState.lastRestoreAction = 'collapse';
  }
  try {
    windowManager.dimReactChatForMinimize();
  } catch (_) {}
});

// 毛线球恢复揭示 —— preload doExpand 在隐性状态下把 surface 定位到球位置后派发，
// 这里 restore chatWin opacity 让对话框可见，并给独立球回一个 RESTORE_ACK。
// 独立球的 hide 仍由球自己在弹完 bounce 动画后发 HIDE，但**只有收到这个 ACK（确认 restore
// 真的发生）才隐藏**：否则（如 CLICK 因 renderer 正在 reload 被丢弃、restore 没跑）球会
// 一直留着且可点，避免「球消失 + 对话框仍 opacity 0」的两头落空。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.RESTORE_COMPLETE, (_event, payload = {}) => {
  const restorePayload = payload && typeof payload === 'object' ? payload : {};
  const incomingRestoreSeq = Number(restorePayload.__compactChatRestoreSeq);
  const incomingSession = restorePayload && typeof restorePayload.__compactChatRestoreSession === 'string'
    ? restorePayload.__compactChatRestoreSession
    : '';
  const incomingSessionTime = parseCompactChatRestoreSessionTimestamp(incomingSession);
  const senderId = _event && _event.sender && Number.isFinite(_event.sender.id) ? _event.sender.id : null;
  if (senderId === null) return;
  {
    const currentChatWin = windowManager.getReactChatWindow();
    const senderWin = _event && _event.sender ? BrowserWindow.fromWebContents(_event.sender) : null;
    if (!currentChatWin || currentChatWin.isDestroyed() || senderWin !== currentChatWin) {
      return;
    }
    var senderState = getCompactChatRestoreStateForSender(senderId);
    if (shouldIgnoreCompactChatRestorePayload(incomingSession, incomingSessionTime, senderState)) {
      return;
    }
    if (incomingSession && senderState.session !== incomingSession) {
      senderState.session = incomingSession;
      senderState.sessionTime = incomingSessionTime;
      senderState.sequence = 0;
      senderState.lastRestoreAction = 'none';
    }
    var isCarrierHiddenBeforeRestore = isCompactChatCarrierHidden(currentChatWin);
    if (senderState.lastRestoreAction === 'restore' && !isCarrierHiddenBeforeRestore) {
      setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
      return;
    }
    if (Number.isFinite(incomingSessionTime)) {
      compactChatRestoreActiveSessionTime = incomingSessionTime;
    }
    if (Number.isFinite(incomingRestoreSeq)) {
      if (incomingRestoreSeq <= senderState.sequence) {
        setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
        return;
      }
    }
    setCompactChatRestoreSequenceState(senderState, incomingRestoreSeq);
    senderState.lastRestoreAction = 'restore';
  }
  const shouldHideBallAfterRestore = restorePayload.hideBall === true;
  // 竞态防护：点球后 preload 有 ~140ms 延迟才派 RESTORE_COMPLETE。若这期间用户从托盘/关闭
  // IPC 把对话框关了（hideReactChatFromMain 置 userClosed + hide 球 + hide 对话框），这条
  // 迟到的 RESTORE_COMPLETE 不应再把刚关的对话框 restore 出来。userClosed 时直接跳过。
  try {
    if (typeof windowManager.isReactChatUserClosed === 'function'
      && windowManager.isReactChatUserClosed()) {
      pendingProgrammaticBallRestore = false;
      return;
    }
  } catch (_) {}

  // 竞态防护（hideBall 路径）：直接恢复在 preload 有 bounds+surface 两段异步等待。
  // 若此期间 renderer 重载/替换，或窗口被关闭，旧 RESTORE_COMPLETE 不应再执行
  // restoreReactChatVisibilityFromMinimize（会亮出空 carrier）或 hideCompactChatBallWindow
  // （会销毁新创建的独立球）。
  // - senderWin 校验覆盖跨 renderer 旧 IPC（与 HIDE channel 一致）
  // - 同一 renderer 内用户重新折叠时，preload 取消守卫（eMinimized）已拦截、不发 RESTORE_COMPLETE
  if (shouldHideBallAfterRestore) {
    const chatWin = windowManager.getReactChatWindow();
    if (!chatWin || chatWin.isDestroyed()) {
      pendingProgrammaticBallRestore = false;
      return;
    }
    const senderWin = BrowserWindow.fromWebContents(_event.sender);
    if (!senderWin || senderWin !== chatWin) {
      pendingProgrammaticBallRestore = false;
      return;
    }
  }

  // #179-2 复活竞态：点球后 ~140ms 揭示延迟内按了 F8 hide-all。preload 侧 restore 其实已完成
  // （eMinimized=false、对话框已展开），但 hide-all 要求一切隐藏 —— 不能把对话框 setOpacity(1)+
  // show 复活出来。处理：opacity 回 1 但保持隐藏（keepHidden，下次 F8 还原时才显示）、确定性销毁
  // 球，并把 hide-all 快照从「球 + dim carrier」折叠成「正常对话框 + 无球」（见 hotkey-manager
  // 的 foldBallRestoreIntoHideAllSnapshot），让还原后状态与 preload 一致、不卡死。
  let hideAllActive = false;
  try {
    hideAllActive = typeof hotkeyManager.isUIHidden === 'function' && hotkeyManager.isUIHidden();
  } catch (_) {}
  if (hideAllActive) {
    try { windowManager.restoreReactChatVisibilityFromMinimize({ keepHidden: true }); } catch (_) {}
    try { teardownCompactChatBallWindow(); } catch (_) {}
    sendCompactChatBallMinimizedStateToPet('ball-restore-hide-all');
    try {
      if (typeof hotkeyManager.foldBallRestoreIntoHideAllSnapshot === 'function') {
        hotkeyManager.foldBallRestoreIntoHideAllSnapshot();
      }
    } catch (_) {}
    pendingProgrammaticBallRestore = false;
    return;
  }

  try {
    windowManager.restoreReactChatVisibilityFromMinimize();
  } catch (_) {}

  if (shouldHideBallAfterRestore) {
    pendingProgrammaticBallRestore = false;
    try { teardownCompactChatBallWindow(); } catch (_) {}
    sendCompactChatBallMinimizedStateToPet('ball-direct-restore');
    return;
  }

  sendCompactChatBallMinimizedStateToPet('ball-restore-complete');

  // #179-1 托盘 route-through-restore：程序化恢复没有真实点击 → 球不会播 bounce、也不会靠
  // 「bounce 完 + RESTORE_ACK」自隐。这里在确认 restore 真发生（走到本行）后直接销毁球。
  // 普通点球 pendingProgrammaticBallRestore 为 false，仍走下面 RESTORE_ACK 让球自隐，行为不变。
  if (pendingProgrammaticBallRestore) {
    pendingProgrammaticBallRestore = false;
    try { teardownCompactChatBallWindow(); } catch (_) {}
    sendCompactChatBallMinimizedStateToPet('ball-programmatic-restore');
    return;
  }

  try {
    const ball = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
    if (ball && !ball.isDestroyed() && ball.webContents) {
      ball.webContents.send(COMPACT_CHAT_BALL_CHANNELS.RESTORE_ACK);
    }
  } catch (_) {}
});

// 球被拖动 —— 仅外部球窗口路径由 preload-compact-chat-ball.js 在 pointermove 中派发。
// chatWin 保持 visible + opacity 0 状态，setBounds 在 visible 透明窗口上完全可靠
// （SetWindowPos + DWM 合成层正常更新），所以这里同步移动两个窗口，CLICK 路径直接
// 用 chatWin current bounds 做 W.expand 左下角对齐，全部自动对齐到球当前位置。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.DRAG_MOVE, (event, payload) => {
  const x = Math.round(Number(payload && payload.x));
  const y = Math.round(Number(payload && payload.y));
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  // 顺序很关键：先 chatWin setBounds、再 ball setBounds + moveTop。
  // 原因：Win32 透明无框窗口的 SetWindowPos 偶发会改变 z-order（即便 Electron 期望
  // SWP_NOZORDER），如果先 ball 后 chat，chat 的 setBounds 可能把它顶到 ball 之上 ——
  // ball 接收不到 pointer 事件，用户报「拖着拖着球动不了」。
  // 改成：chat 先 setBounds → 再 ball setBounds → ball.moveTop()，ball 始终是最后
  // 一个 SetWindowPos + 强制 moveTop，保证 z-order 在 chat 之上接收 pointer 事件。
  const ballWin = BrowserWindow.fromWebContents(event.sender);
  // 只信任真正的独立球窗口发来的 DRAG_MOVE —— 否则其他 renderer 误发/滥发同通道也能
  // 篡改对话框/球的位置与层级，污染拖动链路。
  const expectedBall = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
  if (!ballWin || ballWin.isDestroyed() || !expectedBall || ballWin !== expectedBall) return;
  // chatWin 先同步（visible，兼容模式 setShape 1x1 / 非兼容模式 opacity 0，setBounds 可靠）
  const chatWin = windowManager.getReactChatWindow();
  // 拖动起始帧缓存两窗口尺寸；之后每帧只用缓存尺寸 setBounds，绝不回读 getBounds 的尺寸，
  // 杜绝高 DPI 取整往返累积导致的逐帧变大。
  if (!compactChatBallDragSizes) {
    const liveBall = ballWin.getBounds();
    const liveChat = (chatWin && !chatWin.isDestroyed()) ? chatWin.getBounds() : null;
    compactChatBallDragSizes = {
      ballWidth: liveBall.width,
      ballHeight: liveBall.height,
      chatWidth: liveChat ? liveChat.width : null,
      chatHeight: liveChat ? liveChat.height : null,
    };
  }
  const dragSizes = compactChatBallDragSizes;
  const ballAnchor = ballWin.getBounds();
  // 视觉度量用「位置实读 + 尺寸取缓存」，避免度量随尺寸一起漂移
  const visualMetrics = getCompactChatBallVisualMetrics({
    x: ballAnchor.x, y: ballAnchor.y, width: dragSizes.ballWidth, height: dragSizes.ballHeight,
  });
  // +3：chatWin/surface 在球右 3px（球比对话条左 3px，与折叠落点 surface.left-3 配对，维持视觉对齐不漂移）。
  const chatX = x + visualMetrics.offsetX + 3;
  const chatY = y + visualMetrics.offsetY - visualMetrics.anchorOffsetY;
  if (chatWin && !chatWin.isDestroyed() && dragSizes.chatWidth && dragSizes.chatHeight) {
    try {
      chatWin.setBounds({ x: chatX, y: chatY, width: dragSizes.chatWidth, height: dragSizes.chatHeight });
      if (typeof windowManager.ensureReactChatMinimizedCarrierMousePassthrough === 'function') {
        windowManager.ensureReactChatMinimizedCarrierMousePassthrough();
      }
      // setBounds 会清掉兼容模式 setShape([1x1]) 隐性裁剪 → 全尺寸透明载体显形，必须立即重打。
      if (typeof windowManager.reassertReactChatMinimizedCarrierDim === 'function') {
        windowManager.reassertReactChatMinimizedCarrierDim();
      }
    } catch (_) {}
  }
  // ball 后同步 + moveTop 强制 z-order 顶部
  try {
    ballWin.setBounds({ x, y, width: dragSizes.ballWidth, height: dragSizes.ballHeight });
    ballWin.moveTop();
  } catch (_) {}
  // 拖动中每帧把球的新 screenRect 同步给 Pet。DRAG_MOVE 每次 pointermove 都改球 bounds，
  // 但 Pet 的全局鼠标轮询(startMousePoller)只跳过 Pet 自身模型拖动、不跳过独立球窗口的拖动 ——
  // 若只靠 DRAG_END 兜底，拖动期间 Pet 一直拿拖动前的 stale rect 判定：光标随球移入模型区后
  // isPointOverIdleChatMinimizedBall 判不出「在球上」，Pet 切回非穿透抢走后续拖动事件，
  // 球拖到模型上就卡住。这里每帧刷新让命中判定跟住球的真实位置。
  sendCompactChatBallMinimizedStateToPet('ball-drag-move', ballWin);
});

// Win32/mac 毛线球折叠 —— preload-chat-react.js 收到 chat-surface-mode-change(minimized) 后派发，
// 主进程原子完成：显示独立球 + 隐性化对话框。reactChatUserClosed 状态下不响应（用户主动
// 关了对话框就不该被反手开成球，让球也不出现保持隐藏一致性）。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.COLLAPSE_TAKEOVER, (_event, payload) => {
  if (typeof windowManager.isReactChatUserClosed === 'function'
    && windowManager.isReactChatUserClosed()) {
    log('[CompactChatBall] collapse-takeover ignored: react chat was closed by user');
    // preload 折叠时已派 PRE_COLLAPSE_DIM 把对话框设为 opacity 0；这里中止接管要回滚透明，
    // 但用户刚把对话框关了 —— 用 keepHidden 只复位 opacity、不重新 show（否则会把刚关的窗口又显示出来）。
    try { windowManager.restoreReactChatVisibilityFromMinimize({ keepHidden: true }); } catch (_) {}
    return;
  }
  if (process.platform === 'linux') {
    // Linux uses the chat BrowserWindow itself as the collapsed yarn ball. The
    // external opacity-carrier takeover is Win32-only because setOpacity() is a
    // no-op on Linux and would leave the expanded dialog visible under the ball.
    log('[CompactChatBall] collapse-takeover ignored on Linux: using native collapsed chat window');
    try { teardownCompactChatBallWindow(); } catch (_) {}
    return;
  }
  const bounds = payload && payload.bounds;
  if (!bounds) {
    log('[CompactChatBall] collapse-takeover ignored: missing bounds');
    try { windowManager.restoreReactChatVisibilityFromMinimize(); } catch (_) {}
    return;
  }
  // 先 dim 对话框（兼容模式下 setShape 裁到 1x1，非兼容模式 setOpacity(0)），再创建独立球 ——
  // 避免两帧内 W.collapse 缩出的 88x88 DOM 球和独立球窗口同时可见（两个毛线球）。
  // dim 失败时仍尝试创建球：球是恢复入口，没有球 = 死锁。
  var dimOk = false;
  try { dimOk = windowManager.dimReactChatForMinimize(); } catch (_) {}
  const ballWin = windowManager.showCompactChatBallWindow(originalUrl, bounds, {
    isPackaged: app.isPackaged,
    log,
  });
  if (ballWin) {
    if (!dimOk) {
      // dim 没生效（窗口异常）但球开起来了 —— 再试一次 dim 防两个球同时可见
      try { windowManager.dimReactChatForMinimize(); } catch (_) {}
    }
    sendCompactChatBallEffectiveStateToPet(
      isCompactChatBallTemporaryHideRequested() ? 'collapse-takeover-temporary-hidden' : 'collapse-takeover',
      ballWin,
    );
  } else {
    log('[CompactChatBall] collapse-takeover: showCompactChatBallWindow returned null, ball not created');
    // 球没开起来 → 没有可视入口，对话框还停在 PRE_COLLAPSE_DIM 的透明态，回滚避免隐身锁死。
    try { windowManager.restoreReactChatVisibilityFromMinimize(); } catch (_) {}
  }
});

// 球拖动结束 —— preload-compact-chat-ball.js 在真实拖动的 pointerup 派发。把球（及同步的
// 对话框窗口）夹回光标所在屏幕的工作区内，避免被甩到屏幕外导致唯一的恢复入口够不着。
ipcMain.on(COMPACT_CHAT_BALL_CHANNELS.DRAG_END, (event) => {
  const ballWin = BrowserWindow.fromWebContents(event.sender);
  const expectedBall = windowManager.getWindows ? windowManager.getWindows().compactChatBall : null;
  if (!ballWin || ballWin.isDestroyed() || !expectedBall || ballWin !== expectedBall) return;
  const dragSizes = compactChatBallDragSizes; // 用拖动起始缓存尺寸做最终夹取，避免回读已漂移尺寸
  // 不在 DRAG_END 清缓存：球态拖动时窗口 resize 会瞬时丢指针捕获 → 派生 pointercancel→DRAG_END，
  // 若此处清掉，下一帧 DRAG_MOVE 会按已被 DPI 取整 +1 的 live 尺寸重新缓存 → 逐次累积变大。
  // 缓存随「球会话」存活，球隐藏(HIDE)时才清，下次折叠按真实折叠尺寸重新缓存。
  try {
    const b = ballWin.getBounds();
    const ballW = dragSizes && dragSizes.ballWidth ? dragSizes.ballWidth : b.width;
    const ballH = dragSizes && dragSizes.ballHeight ? dragSizes.ballHeight : b.height;
    const visualMetrics = getCompactChatBallVisualMetrics({ x: b.x, y: b.y, width: ballW, height: ballH });
    const visualLeft = b.x + visualMetrics.offsetX;
    const visualTop = b.y + visualMetrics.offsetY;
    const display = screen.getDisplayNearestPoint({
      x: Math.round(visualLeft + visualMetrics.size / 2),
      y: Math.round(visualTop + visualMetrics.size / 2),
    });
    const wa = display.workArea;
    const margin = 8;
    const clampedVisualLeft = Math.max(
      wa.x + margin,
      Math.min(visualLeft, wa.x + wa.width - visualMetrics.size - margin)
    );
    const clampedVisualTop = Math.max(
      wa.y + margin,
      Math.min(visualTop, wa.y + wa.height - visualMetrics.size - margin)
    );
    const cx = clampedVisualLeft - visualMetrics.offsetX;
    const cy = clampedVisualTop - visualMetrics.offsetY;
    if (cx === b.x && cy === b.y) {
      if (typeof windowManager.ensureReactChatMinimizedCarrierMousePassthrough === 'function') {
        windowManager.ensureReactChatMinimizedCarrierMousePassthrough();
      }
      sendCompactChatBallMinimizedStateToPet('ball-drag-end', ballWin);
      return; // 已在工作区内，无需夹取
    }
    const chatWin = windowManager.getReactChatWindow();
    if (chatWin && !chatWin.isDestroyed()) {
      const cb = chatWin.getBounds();
      chatWin.setBounds({
        x: clampedVisualLeft + 3, // +3：chatWin 在球右 3px（与折叠落点对齐，维持球比对话条左 3px）
        y: cy + visualMetrics.offsetY - visualMetrics.anchorOffsetY,
        width: dragSizes && dragSizes.chatWidth ? dragSizes.chatWidth : cb.width,
        height: dragSizes && dragSizes.chatHeight ? dragSizes.chatHeight : cb.height
      });
      if (typeof windowManager.ensureReactChatMinimizedCarrierMousePassthrough === 'function') {
        windowManager.ensureReactChatMinimizedCarrierMousePassthrough();
      }
      // 同 DRAG_MOVE：夹回工作区的 setBounds 也会清掉兼容模式 1x1 裁剪，必须重打防止载体显形。
      if (typeof windowManager.reassertReactChatMinimizedCarrierDim === 'function') {
        windowManager.reassertReactChatMinimizedCarrierDim();
      }
    }
    ballWin.setBounds({ x: cx, y: cy, width: ballW, height: ballH });
    ballWin.moveTop();
    sendCompactChatBallMinimizedStateToPet('ball-drag-end', ballWin);
  } catch (_) {}
});

ipcMain.on('neko:model-manager-main-ui-hidden', (event, payload) => {
  if (process.platform !== 'linux') return;
  const hidden = !!(payload && payload.hidden);
  const senderId = event && event.sender ? event.sender.id : 0;
  if (hidden) {
    linuxModelManagerHiddenSenders.add(senderId);
    if (event && event.sender && !linuxModelManagerHiddenSenderCleanup.has(senderId)) {
      const cleanup = () => {
        linuxModelManagerHiddenSenderCleanup.delete(senderId);
        if (linuxModelManagerHiddenSenders.delete(senderId)) {
          applyLinuxModelManagerHiddenState();
        }
      };
      linuxModelManagerHiddenSenderCleanup.set(senderId, cleanup);
      event.sender.once('destroyed', cleanup);
    }
  } else {
    releaseLinuxModelManagerHiddenSender(senderId, event && event.sender);
  }
  applyLinuxModelManagerHiddenState();
});

// 工具状态由 pet 窗口独立追踪（通过 AVATAR_TOOL_CURSOR_STATE 上报），
// 此处不再直接注入 chat 窗口的状态，因为 chat 窗口内没有 avatar 区域，
// 其 withinAvatarRange/variant 在桌面端不可靠，会导致道具在静置时
// 错误显示为"判定外"形态（对应 web 端 #1203 fix 的 timer 问题）。
ipcMain.on(CHAT_ACTION_CHANNELS.AVATAR_TOOL_STATE, () => {});

function pointInWindowBounds(point, win) {
  if (!point || !win || win.isDestroyed() || !win.isVisible()) return false;
  try {
    const bounds = win.getBounds();
    return point.x >= bounds.x
      && point.x < bounds.x + bounds.width
      && point.y >= bounds.y
      && point.y < bounds.y + bounds.height;
  } catch (_) {
    return false;
  }
}

function pointInWindowInputRects(point, win, rects) {
  if (!point || !win || win.isDestroyed() || !Array.isArray(rects)) return false;
  try {
    const bounds = win.getBounds();
    const localX = point.x - bounds.x;
    const localY = point.y - bounds.y;
    return rects.some((rect) => (
      rect
      && Number.isFinite(rect.x)
      && Number.isFinite(rect.y)
      && Number.isFinite(rect.width)
      && Number.isFinite(rect.height)
      && rect.width > 0
      && rect.height > 0
      && localX >= rect.x
      && localX < rect.x + rect.width
      && localY >= rect.y
      && localY < rect.y + rect.height
    ));
  } catch (_) {
    return false;
  }
}

function isReactChatWindowForInputRegion(win) {
  try {
    const reactChat = typeof windowManager.getReactChatWindow === 'function'
      ? windowManager.getReactChatWindow()
      : null;
    const fullReactChat = typeof windowManager.getFullChatWindow === 'function'
      ? windowManager.getFullChatWindow()
      : null;
    return !!(win && (
      (reactChat && reactChat.id === win.id)
      || (fullReactChat && fullReactChat.id === win.id)
    ));
  } catch (_) {
    return false;
  }
}

function isFullReactChatWindowForInputRegion(win) {
  try {
    const windows = windowManager.getWindows ? windowManager.getWindows() : {};
    const fullChat = windows && windows.fullChat;
    const fullReactChat = typeof windowManager.getFullChatWindow === 'function'
      ? windowManager.getFullChatWindow()
      : null;
    return !!(win && (
      (fullChat && fullChat.id === win.id)
      || (fullReactChat && fullReactChat.id === win.id)
    ));
  } catch (_) {
    return false;
  }
}

function pointInWaylandWindowShape(point, win) {
  if (!point || !win || win.isDestroyed()) return null;
  try {
    if (!_lastShapeByWindow || !_lastShapeMetaByWindow || typeof getNativeWindowShapeRects !== 'function') {
      return null;
    }
    const requestedRects = _lastShapeByWindow.get(win.id);
    if (!Array.isArray(requestedRects)) return null;
    const meta = _lastShapeMetaByWindow.get(win.id) || {};
    const shapeRects = getNativeWindowShapeRects(win, requestedRects, meta);
    if (!Array.isArray(shapeRects) || shapeRects.length === 0) return false;
    return pointInWindowInputRects(point, win, shapeRects);
  } catch (_) {
    return null;
  }
}

function pointInWindowEffectiveInputRegion(point, win) {
  if (!pointInWindowBounds(point, win)) return false;
  try {
    if (_ignoreStateByWindow && _ignoreStateByWindow.get(win.id) === true) return false;
  } catch (_) {}
  if (process.platform !== 'linux') return true;
  if (isLinuxWaylandRuntime()) {
    const shapeHit = pointInWaylandWindowShape(point, win);
    if (shapeHit !== null) return shapeHit;
    if (isFullReactChatWindowForInputRegion(win)) return true;
    if (isReactChatWindowForInputRegion(win)) return false;
    return true;
  }
  try {
    const rects = win._nekoEffectiveInputRegionRects;
    if (!Array.isArray(rects)) return true;
    return pointInWindowInputRects(point, win, rects);
  } catch (_) {
    return true;
  }
}

function pushUniqueWindow(list, seen, win) {
  try {
    if (!win || win.isDestroyed() || seen.has(win.id)) return;
    seen.add(win.id);
    list.push(win);
  } catch (_) {}
}

function getAvatarToolGlobalPointerContext(point) {
  const context = { insideHostWindow: false, overChatWindow: false };
  try {
    const windows = windowManager.getWindows ? windowManager.getWindows() : {};
    const compactChat = windows && windows.chat;
    const fullChat = windows && windows.fullChat;
    const reactChat = typeof windowManager.getReactChatWindow === 'function'
      ? windowManager.getReactChatWindow()
      : null;
    const fullReactChat = typeof windowManager.getFullChatWindow === 'function'
      ? windowManager.getFullChatWindow()
      : null;
    const chatWindows = [];
    const seen = new Set();
    pushUniqueWindow(chatWindows, seen, fullChat);
    pushUniqueWindow(chatWindows, seen, compactChat);
    pushUniqueWindow(chatWindows, seen, reactChat);
    pushUniqueWindow(chatWindows, seen, fullReactChat);
    const visibleChatWindows = chatWindows.filter((win) => (
      !(typeof windowManager.isReactChatMinimizedCarrierWindow === 'function'
        && windowManager.isReactChatMinimizedCarrierWindow(win))
    ));
    const overChatWindow = visibleChatWindows.some((win) => pointInWindowEffectiveInputRegion(point, win));
    const managedWindows = [
      ...visibleChatWindows,
      windows && windows.subtitle,
      windows && windows.agentHud,
      windows && windows.jukebox,
      typeof windowManager.getToastWindow === 'function' ? windowManager.getToastWindow() : null,
    ];
    context.overChatWindow = overChatWindow;
    context.insideHostWindow = managedWindows.some((win) => pointInWindowEffectiveInputRegion(point, win));
  } catch (_) {}
  return context;
}

function getAvatarToolPayloadScreenPoint(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const nestedPoint = payload.cursorScreenPoint && typeof payload.cursorScreenPoint === 'object'
    ? payload.cursorScreenPoint
    : null;
  const xSource = Number.isFinite(Number(payload.cursorScreenX))
    ? payload.cursorScreenX
    : Number.isFinite(Number(payload.screenX))
      ? payload.screenX
      : nestedPoint && Number.isFinite(Number(nestedPoint.x))
        ? nestedPoint.x
        : null;
  const ySource = Number.isFinite(Number(payload.cursorScreenY))
    ? payload.cursorScreenY
    : Number.isFinite(Number(payload.screenY))
      ? payload.screenY
      : nestedPoint && Number.isFinite(Number(nestedPoint.y))
        ? nestedPoint.y
        : null;
  const x = Number(xSource);
  const y = Number(ySource);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

function getAvatarToolPayloadClientScreenPoint(payload, sender) {
  if (!payload || typeof payload !== 'object' || !sender) return null;
  const clientX = Number(payload.cursorClientX);
  const clientY = Number(payload.cursorClientY);
  if (!Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
  try {
    const win = BrowserWindow.fromWebContents(sender);
    if (!win || win.isDestroyed()) return null;
    const bounds = win.getBounds();
    const x = Number(bounds.x) + clientX;
    const y = Number(bounds.y) + clientY;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { x, y };
  } catch (_) {
    return null;
  }
}

function sendAvatarToolCursorStateToChatWindows(payload) {
  try {
    const windows = windowManager.getWindows ? windowManager.getWindows() : {};
    const targets = [];
    const seen = new Set();
    pushUniqueWindow(targets, seen, windows && windows.chat);
    pushUniqueWindow(targets, seen, windows && windows.fullChat);
    pushUniqueWindow(
      targets,
      seen,
      typeof windowManager.getReactChatWindow === 'function' ? windowManager.getReactChatWindow() : null,
    );
    pushUniqueWindow(
      targets,
      seen,
      typeof windowManager.getFullChatWindow === 'function' ? windowManager.getFullChatWindow() : null,
    );
    for (const win of targets) {
      try {
        if (!win || win.isDestroyed() || !win.webContents || win.webContents.isDestroyed()) continue;
        win.webContents.send(PET_CHANNELS.AVATAR_TOOL_CURSOR_STATE, buildAvatarToolCursorPayloadForChatWindow(payload, win));
      } catch (_) {}
    }
  } catch (_) {}
}

function buildAvatarToolCursorPayloadForChatWindow(payload, win) {
  if (!payload || typeof payload !== 'object') return payload;
  const cursor = getAvatarToolPayloadScreenPoint(payload);
  if (!cursor) return payload;
  return {
    ...payload,
    overChatWindow: pointInWindowEffectiveInputRegion(cursor, win),
  };
}

function sendAvatarToolPolledPointerToPet(payload) {
  try {
    if (!payload || typeof payload !== 'object' || payload.active !== true) return;
    const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
    if (!pet || pet.isDestroyed() || !pet.webContents || pet.webContents.isDestroyed()) return;
    const cursor = getAvatarToolPayloadScreenPoint(payload);
    if (!cursor) return;
    const context = getAvatarToolGlobalPointerContext(cursor);
    pet.webContents.send(CHAT_ACTION_CHANNELS.AVATAR_TOOL_POINTER, {
      ...payload,
      type: 'move',
      overChatWindow: context.overChatWindow,
      insideHostWindow: context.insideHostWindow,
      screenX: cursor.x,
      screenY: cursor.y,
      cursorScreenX: cursor.x,
      cursorScreenY: cursor.y,
      timestamp: Date.now(),
    });
  } catch (_) {}
}

function publishAvatarToolPolledCursorState(payload) {
  sendAvatarToolCursorStateToChatWindows(payload);
  sendAvatarToolPolledPointerToPet(payload);
}

ipcMain.on(PET_CHANNELS.AVATAR_TOOL_CURSOR_STATE, (event, payload) => {
  let nextPayload = payload;
  try {
    if (payload && typeof payload === 'object') {
      nextPayload = { ...payload };
      const payloadScreenPoint = getAvatarToolPayloadScreenPoint(nextPayload);
      const clientScreenPoint = payloadScreenPoint
        ? null
        : getAvatarToolPayloadClientScreenPoint(nextPayload, event && event.sender);
      const normalizedScreenPoint = payloadScreenPoint || clientScreenPoint;
      if (normalizedScreenPoint) {
        nextPayload.screenX = normalizedScreenPoint.x;
        nextPayload.screenY = normalizedScreenPoint.y;
        nextPayload.cursorScreenX = normalizedScreenPoint.x;
        nextPayload.cursorScreenY = normalizedScreenPoint.y;
      }
      const cursor = normalizedScreenPoint || screen.getCursorScreenPoint();
      const context = getAvatarToolGlobalPointerContext(cursor);
      nextPayload.overChatWindow = context.overChatWindow;
      nextPayload.insideHostWindow = context.insideHostWindow;
    }
  } catch (_) {}
  if (isLinuxWaylandRuntime()) {
    sendAvatarToolCursorStateToChatWindows(nextPayload);
  }
  avatarToolCursorService.setState(nextPayload);
});

ipcMain.on(PET_CHANNELS.AVATAR_BOUNDS_SYNC, (_event, payload) => {
  let nextPayload = payload && typeof payload === 'object' ? { ...payload } : null;
  const bounds = nextPayload && nextPayload.bounds;
  if (bounds && Number.isFinite(Number(bounds.centerX)) && Number.isFinite(Number(bounds.centerY))) {
    try {
      const display = screen.getDisplayNearestPoint({
        x: Math.round(Number(bounds.centerX)),
        y: Math.round(Number(bounds.centerY)),
      });
      if (display) {
        nextPayload.display = {
          id: display.id,
          bounds: { ...display.bounds },
          workArea: { ...display.workArea },
          scaleFactor: display.scaleFactor,
        };
      }
    } catch (_) {}
  }
  latestAvatarBoundsSyncPayload = cloneAvatarBoundsSyncPayload(nextPayload);
  latestAvatarBoundsSyncPayloadKnown = true;

  if (!(typeof windowManager.isReactChatUserClosed === 'function'
    && windowManager.isReactChatUserClosed())) {
    const chat = windowManager.getReactChatWindow();
    if (chat && !chat.isDestroyed() && chat.webContents) {
      try {
        chat.webContents.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC, nextPayload);
      } catch (_) {}
    }
  }

  const subtitle = windowManager.getSubtitleWindow();
  if (subtitle && !subtitle.isDestroyed() && subtitle.webContents) {
    try {
      subtitle.webContents.send(PET_CHANNELS.AVATAR_BOUNDS_SYNC, nextPayload);
    } catch (_) {}
  }
});

ipcMain.on(PET_CHANNELS.AVATAR_BOUNDS_SYNC_SUBSCRIPTION, (_event, payload) => {
  const senderWin = BrowserWindow.fromWebContents(_event.sender);
  if (senderWin && !senderWin.isDestroyed()) {
    if (payload && payload.active) {
      avatarBoundsSyncSubscribers.set(senderWin.id, true);
      sendLatestAvatarBoundsSyncToSubscriber(senderWin);
      if (!avatarBoundsSyncSubscriberCloseCleanup.has(senderWin.id)) {
        avatarBoundsSyncSubscriberCloseCleanup.add(senderWin.id);
        senderWin.once('closed', () => {
          avatarBoundsSyncSubscribers.delete(senderWin.id);
          avatarBoundsSyncSubscriberCloseCleanup.delete(senderWin.id);
          notifyAvatarBoundsSyncSubscriptionState();
        });
      }
    } else {
      avatarBoundsSyncSubscribers.delete(senderWin.id);
    }
  }
  notifyAvatarBoundsSyncSubscriptionState();
});

ipcMain.on(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, (event, payload) => {
  let suppressForwardForTemporaryHide = false;
  const wasLinuxSelfMinimizedBallTracked = isReactChatSelfMinimizedBallTracked();
  try {
    const senderWin = BrowserWindow.fromWebContents(event.sender);
    const chat = windowManager.getReactChatWindow();
    if (senderWin && chat && !chat.isDestroyed() && senderWin.id === chat.id) {
      const rendererMinimized = !!(payload && typeof payload === 'object' && payload.minimized);
      const temporaryHideRequested = typeof windowManager.isCompactChatBallTemporaryHideRequested === 'function'
        && windowManager.isCompactChatBallTemporaryHideRequested();
      const minimized = process.platform === 'linux' && rendererMinimized;
      reactChatSelfMinimizedBallState = {
        active: minimized,
        webContentsId: chat.webContents ? chat.webContents.id : null,
        screenRect: minimized ? normalizeCompactChatScreenRect(payload && payload.screenRect) : null,
        updatedAt: Date.now(),
      };
      if (rendererMinimized && temporaryHideRequested) {
        if (process.platform === 'linux') {
          try { windowManager.setReactChatSelfMinimizedBallTemporarilyHidden(true); } catch (_) {}
        }
        sendCompactChatBallTemporarilyHiddenStateToPet(
          process.platform === 'linux'
            ? 'temporary-hidden-linux-self-minimized'
            : 'temporary-hidden-renderer-minimized'
        );
        suppressForwardForTemporaryHide = true;
      } else if (process.platform === 'linux' && !minimized && wasLinuxSelfMinimizedBallTracked) {
        try { windowManager.setReactChatSelfMinimizedBallTemporarilyHidden(false); } catch (_) {}
      }
    }
  } catch (_) {}
  if (suppressForwardForTemporaryHide) return;
  const pet = windowManager.getPetWindow();
  if (!pet || pet.isDestroyed() || !pet.webContents) return;
  try {
    pet.webContents.send(PET_CHANNELS.IDLE_CHAT_MINIMIZED_STATE, payload && typeof payload === 'object' ? payload : {});
  } catch (_) {}
});

// ===== Idle CAT1 伙伴窗口层级 =====
let idleCatCompanionLayerActive = false;
let idleCatCompanionLayerSourceWebContents = null;
let idleCatCompanionLayerSourceCleanup = null;
// companion 只需要越过聊天框(rank 1)，更高层窗口必须保持在 Pet 之上。
const IDLE_CAT_COMPANION_PROTECTED_MIN_RANK = 2;
const IDLE_CAT_COMPANION_UNRANKED_POPUP_RANK = 4;

function isUsableVisibleWindow(win) {
  if (!win || win.isDestroyed()) return false;
  try {
    return win.isVisible() && !win.isMinimized();
  } catch (_) {
    return false;
  }
}

function getIdleCatCompanionProtectedRank(win) {
  if (!win || win.isDestroyed()) return null;
  if (typeof getWindowZRank === 'function') {
    const rank = getWindowZRank(win);
    if (Number.isFinite(rank) && rank >= IDLE_CAT_COMPANION_PROTECTED_MIN_RANK) {
      return rank;
    }
    if (Number.isFinite(rank)) return null;
  }
  if (win === loadingWindow) return null;
  // This raise happens only on the inactive -> active edge. Keep visible
  // topmost popups above Pet without reintroducing periodic moveTop flicker.
  try {
    if (win.isAlwaysOnTop && win.isAlwaysOnTop() && win._nekoForceNotTopMost !== true) {
      return IDLE_CAT_COMPANION_UNRANKED_POPUP_RANK;
    }
  } catch (_) {}
  return null;
}

function getIdleCatCompanionProtectedOrder(win) {
  if (!win || win.isDestroyed()) return 100;
  try {
    const managed = windowManager.getWindows ? windowManager.getWindows() : {};
    if (win === managed.jukebox) return 20;
    if (win === managed.agentHud) return 21;
  } catch (_) {}
  if (win._nekoKind === 'pluginDashboard') return 35;
  if (win._nekoKind === 'settings') return 40;
  try {
    const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
    if (toast && win === toast) return 50;
  } catch (_) {}
  return 100;
}

function collectIdleCatCompanionProtectedWindows(excludedWin) {
  const windows = BrowserWindow.getAllWindows ? BrowserWindow.getAllWindows() : [];
  return windows
    .map((win, index) => ({
      win,
      index,
      rank: win && win !== excludedWin && isUsableVisibleWindow(win)
        ? getIdleCatCompanionProtectedRank(win)
        : null,
      order: getIdleCatCompanionProtectedOrder(win),
    }))
    .filter(item => item.win && Number.isFinite(item.rank))
    .sort((a, b) => (a.rank - b.rank) || (a.order - b.order) || (a.index - b.index));
}

function raiseIdleCatCompanionProtectedWindows(protectedWindows) {
  for (const item of protectedWindows || []) {
    const win = item && item.win;
    if (!isUsableVisibleWindow(win)) continue;
    try {
      win.moveTop();
    } catch (error) {
      log('[IdleCatCompanionLayer] protected moveTop failed:', error && error.message ? error.message : error);
    }
  }
}

function raisePetForIdleCatCompanion(reason) {
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  if (!isUsableVisibleWindow(pet)) return false;
  const protectedWindows = collectIdleCatCompanionProtectedWindows(pet);
  try {
    pet.moveTop();
    raiseIdleCatCompanionProtectedWindows(protectedWindows);
    return true;
  } catch (error) {
    log('[IdleCatCompanionLayer] pet moveTop failed:', error && error.message ? error.message : error);
    return false;
  }
}

function shouldRaisePetForIdleCatCompanionActiveRequest(reason, wasActive) {
  if (!wasActive) return true;
  // Geometry follow requests can arrive after compact chat relayout raises chat.
  // Heartbeats remain keepalives and must not recreate the old moveTop loop.
  return /(?:^|[-_:])follow(?:$|[-_:])/.test(String(reason || '').toLowerCase());
}

function restoreReactChatLayerAfterIdleCatCompanion(reason) {
  const fullChat = windowManager.getFullChatWindow ? windowManager.getFullChatWindow() : null;
  const chat = isUsableVisibleWindow(fullChat)
    ? fullChat
    : (windowManager.getReactChatWindow ? windowManager.getReactChatWindow() : null);
  if (!isUsableVisibleWindow(chat)) return false;
  const protectedWindows = collectIdleCatCompanionProtectedWindows(chat);
  try {
    chat.moveTop();
    raiseIdleCatCompanionProtectedWindows(protectedWindows);
    return true;
  } catch (error) {
    log('[IdleCatCompanionLayer] react chat moveTop failed:', error && error.message ? error.message : error);
    return false;
  }
}

function detachIdleCatCompanionLayerSource() {
  if (typeof idleCatCompanionLayerSourceCleanup === 'function') {
    idleCatCompanionLayerSourceCleanup();
  }
  idleCatCompanionLayerSourceCleanup = null;
  idleCatCompanionLayerSourceWebContents = null;
}

function clearIdleCatCompanionLayer(reason) {
  const wasActive = idleCatCompanionLayerActive;
  idleCatCompanionLayerActive = false;
  detachIdleCatCompanionLayerSource();
  if (!wasActive) return;
  restoreReactChatLayerAfterIdleCatCompanion(reason || 'inactive');
  log('[IdleCatCompanionLayer] inactive:', reason || 'inactive');
}

function bindIdleCatCompanionLayerSource(webContents) {
  if (!webContents || webContents.isDestroyed()) return;
  if (idleCatCompanionLayerSourceWebContents === webContents) return;
  detachIdleCatCompanionLayerSource();
  const clearFromSource = (reason) => {
    clearIdleCatCompanionLayer(reason);
  };
  const onDestroyed = () => clearFromSource('source-destroyed');
  const onRenderGone = () => clearFromSource('source-render-gone');
  const onDidStartNavigation = (_event, _url, isInPlace, isMainFrame) => {
    if (isMainFrame && !isInPlace) clearFromSource('source-navigation');
  };
  webContents.once('destroyed', onDestroyed);
  webContents.once('render-process-gone', onRenderGone);
  webContents.on('did-start-navigation', onDidStartNavigation);
  idleCatCompanionLayerSourceWebContents = webContents;
  idleCatCompanionLayerSourceCleanup = () => {
    try { webContents.removeListener('destroyed', onDestroyed); } catch (_) {}
    try { webContents.removeListener('render-process-gone', onRenderGone); } catch (_) {}
    try { webContents.removeListener('did-start-navigation', onDidStartNavigation); } catch (_) {}
  };
}

ipcMain.on(PET_CHANNELS.IDLE_CAT_COMPANION_LAYER, (event, payload) => {
  const pet = windowManager.getPetWindow ? windowManager.getPetWindow() : mainWindow;
  const senderWin = BrowserWindow.fromWebContents(event.sender);
  if (pet && senderWin && senderWin !== pet) return;

  const active = !!(payload && payload.active);
  const reason = (payload && payload.reason) || 'state-change';
  if (active) {
    const wasActive = idleCatCompanionLayerActive;
    if (!wasActive) {
      log('[IdleCatCompanionLayer] active:', reason);
    }
    idleCatCompanionLayerActive = true;
    bindIdleCatCompanionLayerSource(event.sender);
    if (shouldRaisePetForIdleCatCompanionActiveRequest(reason, wasActive)) {
      raisePetForIdleCatCompanion(reason);
    }
    return;
  }

  clearIdleCatCompanionLayer(reason);
});

// ===== Jukebox 独立窗口 =====
ipcMain.on(JUKEBOX_CHANNELS.TOGGLE, () => {
  log('[Main] 收到 Jukebox 切换请求');
  if (guardStorageStartupGate('toggleJukebox')) return;
  windowManager.toggleJukeboxWindow(originalUrl, { isPackaged: app.isPackaged, log });
});

// 暗色模式查询
ipcMain.handle('neko:get-dark-mode', async () => {
  if (!appConfig) appConfig = getConfig();
  return !!appConfig.darkMode;
});

// 语言查询（等待语言初始化完成，最多 5 秒）
ipcMain.handle('neko:get-language', async () => {
  await Promise.race([languageReady, new Promise(r => setTimeout(r, 5000))]);
  return currentLanguage || 'en';
});

// ===== Toast 转发（按需创建/销毁 Toast 窗口）=====
// Toast 窗口不再启动时常驻，首条消息时创建，空闲 10s 后销毁。

let _toastIdleTimer = null;
const TOAST_IDLE_MS = 10000; // 无消息后销毁延迟

function _resetToastIdleTimer() {
  if (_toastIdleTimer) clearTimeout(_toastIdleTimer);
  _toastIdleTimer = setTimeout(() => {
    _toastIdleTimer = null;
    log('[Toast] 空闲超时，销毁 Toast 窗口');
    windowManager.destroyToastWindow();
  }, TOAST_IDLE_MS);
}

function _sendInlineToast(channel, data) {
  const petWin = windowManager.getPetWindow();
  if (!petWin || petWin.isDestroyed()) return false;
  petWin.webContents.send('neko:inline-toast', { channel, data });
  return true;
}

async function _sendToToastWindow(channel, data) {
  // Linux: 可选使用系统通知管线（高级设置中控制）
  if (process.platform === 'linux' && appConfig?.linuxUseNativeNotify === true) {
    const { Notification } = require('electron');
    if (Notification.isSupported()) {
      const message = (data && data.message) || '';
      if (message) {
        const n = new Notification({ title: 'N.E.K.O.', body: message, silent: true });
        n.show();
      }
    }
    return;
  }

  // Linux 桌面非阻塞提示走 Pet 窗口内联渲染，避免语音准备/状态短提示
  // 反复创建全屏透明 Toast BrowserWindow 并触发 X11 ShapeInput 重算。
  // 重要通知仍走独立 Toast 窗口，保留可交互 prominent notice 链路。
  if (process.platform === 'linux' && channel !== TOAST_CHANNELS.PROMINENT) {
    if (_sendInlineToast(channel, data)) return;
  }

  // Wayland: 在 Pet 窗口内渲染 Toast，不创建独立窗口。
  // 独立全屏 BrowserWindow 在 Wayland 下创建时会阻塞合成器数秒。
  if (isLinuxWaylandRuntime()) {
    _sendInlineToast(channel, data);
    return;
  }

  try {
    const tw = await windowManager.ensureToastWindow(originalUrl, { isPackaged: app.isPackaged, log });
    if (tw && !tw.isDestroyed()) {
      tw.webContents.send(channel, data);
      // Toast 通知层必须显式显示。ensureToastWindow 在空闲 10s 后会销毁并按需重建 Toast；
      // 新建窗口在 Windows/Mac（show: isX11 ? false : undefined，见 createToastWindow）可能
      // 处于未映射状态 → banner 不现身。对未 visible 的 Toast 调 showInactive() 显式映射且不抢焦点。
      // （实测：仅此一行即可让 banner 在语音会话全程稳定可见；曾试加 moveTop() 抗 Pet 游戏
      //  模式 watcher 抢顶，实测不需要、已去除——别再加回来。）
      //
      // 仅限非 Linux：X11 Toast 由 createToastWindow 故意 show:false 隐藏，待 applyX11InputShape
      // 成功后才由 showLinuxX11Toast 显示；这里抢先 show 会绕过该 guard，让未设输入形状的全屏透明窗
      // 拦截桌面点击。Wayland 与非 prominent Linux 已在上方提前 return，此处 linux 仅剩 X11 prominent，
      // 故 !== 'linux' 即精确排除。
      if (process.platform !== 'linux') {
        try { if (!tw.isVisible()) tw.showInactive(); } catch (_) { /* ignore */ }
      }
    }
    // Prominent notice 需要用户交互，不启动空闲计时器（由 setMouseThrough 信号恢复）
    if (channel !== TOAST_CHANNELS.PROMINENT) {
      _resetToastIdleTimer();
    }
  } catch (e) {
    log('[Toast] 发送失败:', e.message);
  }
}

// Status toast（来自 preload-common setupToastOverride）
ipcMain.on('neko:show-toast', (event, { message, duration, important, i18nKey }) => {
  let displayMessage = message;
  if (i18nKey) {
    const translated = t(i18nKey);
    if (translated !== i18nKey) displayMessage = translated;
  }
  // important 类型走 prominent notice
  if (important) {
    _sendToToastWindow(TOAST_CHANNELS.PROMINENT, { message: displayMessage });
  } else {
    _sendToToastWindow(TOAST_CHANNELS.STATUS, { message: displayMessage, duration: duration || 4000 });
  }
});

// Voice preparing toast（来自 preload-common setupVoiceToastOverride）
ipcMain.on(TOAST_CHANNELS.VOICE_PREPARING, (event, data) => {
  _sendToToastWindow(TOAST_CHANNELS.VOICE_PREPARING, data);
});

ipcMain.on(TOAST_CHANNELS.VOICE_HIDE_PREPARING, () => {
  const tw = windowManager.getToastWindow();
  if (tw && !tw.isDestroyed()) {
    tw.webContents.send(TOAST_CHANNELS.VOICE_HIDE_PREPARING, {});
    _resetToastIdleTimer();
    return;
  }
  // Hide 是清理信号，不能为了隐藏提示而按需创建 Toast 窗口。
  _sendInlineToast(TOAST_CHANNELS.VOICE_HIDE_PREPARING, {});
});

ipcMain.on(TOAST_CHANNELS.VOICE_READY, (event, data) => {
  _sendToToastWindow(TOAST_CHANNELS.VOICE_READY, data);
});

ipcMain.on(TOAST_CHANNELS.PROMINENT, (event, data) => {
  _sendToToastWindow(TOAST_CHANNELS.PROMINENT, data);
});

function reloadAndShow(url) {
  // 多窗口模式：销毁所有窗口后重新创建
  if (_toastIdleTimer) { clearTimeout(_toastIdleTimer); _toastIdleTimer = null; }
  avatarToolCursorService.stop();
  clearPendingTutorialOverlayRelays();
  clearTutorialHotkeySuppression('tutorial-forced-reload');
  clearTutorialSystemCursor('tutorial-forced-reload');
  tutorialGlobalOverlayService.stop();
  windowManager.destroyAllWindows();
  mainWindow = null;

  const windows = windowManager.createAllWindows(url, {
    isPackaged: app.isPackaged,
    isStreamerMode,
    log,
    autoCreateReactChat: false,
  });
  mainWindow = windows.pet;

  // 重新设置 IPC 路由（如果需要）
  ipcRouter.setupIPCRouter({
    getWindows: () => windowManager.getWindows(),
    log,
  });

  setupPetWindowBehavior(mainWindow);
  if (/^https?:/i.test(url || '')) {
    attachStorageGateToPetWindow(mainWindow);
  } else {
    stopStorageGatePolling();
  }
}

let appConfig = null;

function getConfig() {
  const defaultConfig = { apiBaseUrl: 'http://localhost:48911/', autoLaunch: false, useSystemProxy: false, streamerMode: false, darkMode: false, globalAlwaysOnTop: true, preventSystemSleep: false, compatibilityMode: false, linuxForceX11: true, linuxUseNativeNotify: false };
  const userPath = getUserConfigPath();
  const bundledPath = getBundledConfigPath();

  log('getConfig() - userPath:', userPath);
  log('getConfig() - bundledPath:', bundledPath);

  const { config, source } = readCoreConfigRaw();
  log('getConfig() - 读取来源:', source);

  if (!config) {
    // 既无用户配置也无打包默认，写一份默认到 userData
    log('未找到任何 core_config，写入默认配置到 userData');
    try {
      fs.mkdirSync(path.dirname(userPath), { recursive: true });
      fs.writeFileSync(userPath, JSON.stringify(defaultConfig, null, 2), 'utf-8');
      log('默认配置文件创建成功:', userPath);
    } catch (err) {
      log('创建配置文件失败:', err.message);
    }
    return defaultConfig;
  }

  // 兼容旧配置
  if (typeof config.autoLaunch === 'undefined') {
    config.autoLaunch = false;
  }
  if (typeof config.useSystemProxy === 'undefined') {
    config.useSystemProxy = false;
  }
  if (typeof config.streamerMode === 'undefined') {
    config.streamerMode = false;
  }
  if (typeof config.darkMode === 'undefined') {
    config.darkMode = false;
  }
  if (typeof config.customUrls === 'undefined') {
    config.customUrls = null;
  }
  if (typeof config.customPorts === 'undefined') {
    config.customPorts = null;
  }
  if (typeof config.globalAlwaysOnTop === 'undefined') {
    config.globalAlwaysOnTop = true;
  }
  if (typeof config.preventSystemSleep === 'undefined') {
    config.preventSystemSleep = false;
  }
  if (typeof config.compatibilityMode === 'undefined') {
    config.compatibilityMode = false;
  }
  if (typeof config.linuxForceX11 === 'undefined') {
    config.linuxForceX11 = true;
  }
  log('配置文件读取成功:', JSON.stringify(config));
  return config;
}

function saveConfig(cfg) {
  try {
    const cfgPath = getUserConfigPath();
    fs.mkdirSync(path.dirname(cfgPath), { recursive: true });
    fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2), 'utf-8');
    log('配置已保存:', cfgPath, JSON.stringify(cfg));
  } catch (err) {
    log('保存配置失败:', err.message);
  }
}

const autostartService = createAutostartService({
  app,
  log,
  getConfig: () => appConfig || getConfig(),
  saveConfig: (nextConfig) => {
    // 打包后 process.resourcesPath 在 macOS、Linux AppImage、Windows Program Files 等情况下
    // 是只读/受保护的；真实用户配置保存在 app.getPath('userData') 下。
    const cfgPath = path.join(app.getPath('userData'), 'core_config.txt');
    fs.mkdirSync(path.dirname(cfgPath), { recursive: true });
    fs.writeFileSync(cfgPath, JSON.stringify(nextConfig, null, 2), 'utf-8');
    appConfig = nextConfig;
    log('配置已保存 (autostart):', cfgPath, JSON.stringify(nextConfig));
    return nextConfig;
  },
  isPackaged: app.isPackaged,
});

function buildAutostartStatusPayload(status) {
  const payload = {
    ok: status.ok === true,
    supported: status.supported !== false,
    enabled: status.enabled === true,
    authoritative: status.authoritative === true,
    provider: String(status.provider || 'neko-pc'),
    mechanism: String(status.mechanism || ''),
    platform: String(status.platform || process.platform),
    requires_approval: status.requires_approval === true,
    service_not_found: status.service_not_found === true,
  };
  if (status.error != null) payload.error = String(status.error);
  if (status.error_code != null) payload.error_code = String(status.error_code);
  return payload;
}

function broadcastAutostartStatusChanged(status) {
  if (!status || typeof status !== 'object') {
    return;
  }

  try {
    ipcRouter.broadcastGlobal(AUTOSTART_CHANNELS.CHANGED, buildAutostartStatusPayload(status));
  } catch (error) {
    log('autostart - 广播状态变更失败:', error.message);
  }
}

function applyAutostartPreference(enabled) {
  const result = enabled ? autostartService.enable() : autostartService.disable();
  if (tray) {
    updateTrayMenu();
  }
  broadcastAutostartStatusChanged(result);
  return result;
}

// ===== 暗色模式 IPC 处理器 =====
ipcMain.handle('get-dark-mode', () => {
  if (!appConfig) appConfig = getConfig();
  return !!appConfig.darkMode;
});

ipcMain.handle('set-dark-mode', (event, enabled) => {
  if (!appConfig) appConfig = getConfig();
  appConfig.darkMode = !!enabled;
  saveConfig(appConfig);
  log('暗色模式 IPC 设置:', appConfig.darkMode);
  updateTrayMenu();
  // 广播给所有窗口（包括卫星窗口）
  ipcRouter.broadcastGlobal('toggle-dark-mode', appConfig.darkMode);
  _pushDarkModeToHotkeyWindow(appConfig.darkMode);
  return appConfig.darkMode;
});

// ===== 端口设置 IPC 处理器 =====
ipcMain.handle('save-port-config', async (event, data) => {
  if (!isTrustedSender(event)) {
    return { success: false, error: 'Untrusted sender' };
  }
  try {
    // 兼容新旧参数格式：新格式 { ports, urls }，旧格式直接传 ports 对象
    let ports, urls;
    if (data && data.ports) {
      ports = data.ports;
      urls = data.urls || {};
    } else {
      ports = data;
      urls = {};
    }

    for (const [key, val] of Object.entries(ports)) {
      if (!Number.isInteger(val) || val < 1 || val > 65535) {
        return { success: false, error: `Invalid port: ${key} = ${val}` };
      }
    }
    const values = Object.values(ports);
    if (new Set(values).size !== values.length) {
      return { success: false, error: 'Duplicate ports' };
    }

    if (!appConfig) appConfig = getConfig();
    appConfig.customPorts = {
      MAIN_SERVER_PORT: ports.MAIN_SERVER_PORT,
      MEMORY_SERVER_PORT: ports.MEMORY_SERVER_PORT,
      TOOL_SERVER_PORT: ports.TOOL_SERVER_PORT,
      USER_PLUGIN_SERVER_PORT: ports.USER_PLUGIN_SERVER_PORT,
    };

    // 保存自定义 URL（做语法校验：必须是 http:// 或 https:// 开头的合法 URL）
    const cleanUrls = {};
    let hasCustomUrl = false;
    for (const key of ['MAIN_SERVER_URL', 'MEMORY_SERVER_URL', 'TOOL_SERVER_URL', 'USER_PLUGIN_SERVER_URL']) {
      if (urls[key] && typeof urls[key] === 'string' && urls[key].trim().length > 0) {
        const val = urls[key].trim();
        let parsed;
        try { parsed = new URL(val); } catch (_) {
          return { success: false, error: `URL 格式非法: ${key} = ${val}` };
        }
        if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
          return { success: false, error: `URL 协议必须是 http:// 或 https://: ${key} = ${val}` };
        }
        cleanUrls[key] = val;
        hasCustomUrl = true;
      } else {
        cleanUrls[key] = null;
      }
    }
    appConfig.customUrls = hasCustomUrl ? cleanUrls : null;

    // apiBaseUrl 优先级：自定义 URL > 自定义端口
    if (cleanUrls.MAIN_SERVER_URL) {
      let url = cleanUrls.MAIN_SERVER_URL;
      if (!url.endsWith('/')) url += '/';
      appConfig.apiBaseUrl = url;
    } else {
      appConfig.apiBaseUrl = `http://localhost:${ports.MAIN_SERVER_PORT}/`;
    }

    // 更新运行时自定义 URL 覆盖状态
    for (const key of Object.keys(customUrlOverrides)) {
      customUrlOverrides[key] = (appConfig.customUrls && appConfig.customUrls[key]) || null;
    }

    saveConfig(appConfig);

    // 同步更新运行时 originalUrl，使后续 reloadAndShow / 新开子窗口立即生效
    // customUrlOverrides 已在上方更新完，resolveServerUrl 会按正确优先级返回
    // 注：端口改动仍需 restart-app，后端无法热切换端口
    originalUrl = sanitizeOriginalUrl(resolveServerUrl('MAIN_SERVER'), `http://127.0.0.1:${nekoActivePorts.MAIN_SERVER_PORT}/`);
    log('originalUrl 已刷新:', originalUrl);

    // 自定义 URL 主动探测：不通时通过 IPC 把结果送回端口设置窗口，
    // 由窗口自己的 #status 状态条展示（不再弹系统对话框），渲染端会滚动+高亮
    if (hasCustomUrl && cleanUrls.MAIN_SERVER_URL) {
      const probeSender = event && event.sender;
      probeUrlReachable(originalUrl, 3000).then(
        (r) => log('自定义 URL 连通性检测 OK:', originalUrl, 'status=', r.statusCode),
        (err) => {
          log('自定义 URL 连通性检测失败:', originalUrl, err.message || err);
          try {
            if (probeSender && !probeSender.isDestroyed()) {
              probeSender.send('port-config-probe-result', {
                ok: false,
                url: originalUrl,
                error: err.message || String(err),
              });
            }
          } catch (e) { /* ignore */ }
        }
      );
    }

    // 同时写入 userData 目录，供 Python 后端读取（开发模式下 Python 未由 Electron 启动时的回退）
    try {
      const portConfigPath = path.join(app.getPath('userData'), 'port_config.json');
      fs.writeFileSync(portConfigPath, JSON.stringify(appConfig.customPorts, null, 2), 'utf-8');
      log('端口配置已写入 userData:', portConfigPath);
    } catch (e) {
      log('写入 port_config.json 失败:', e.message);
    }
    log('端口配置已保存:', JSON.stringify(appConfig.customPorts));
    if (hasCustomUrl) log('自定义 URL 已保存:', JSON.stringify(cleanUrls));

    return { success: true };
  } catch (err) {
    log('保存端口配置失败:', err.message);
    return { success: false, error: err.message };
  }
});

ipcMain.handle('restart-app', (event) => {
  if (!isTrustedSender(event)) {
    log('拒绝来自不可信来源的重启请求');
    return;
  }
  log('用户通过端口设置窗口请求重启应用');
  // dev 模式（npm start / electron-forge）下 app.relaunch() 不可靠：
  // 只会重启 electron.exe 自己，外层 forge 包装不会跟着重起，新进程启不来。
  // 而 dev 下 Python 后端是外部手动启动的，根本无需 Electron 侧重启。
  // 所以 dev 下降级为 reloadAndShow（销毁前端重建），仍能让新端口/URL 生效。
  // Production 打包版（app.isPackaged === true）维持原语义不变。
  if (!app.isPackaged) {
    log('[dev] restart-app 降级为窗口重载（reloadAndShow），跳过 app.relaunch()');
    try {
      reloadAndShow(originalUrl);
    } catch (e) {
      log('[dev] reloadAndShow 失败:', e.message);
    }
    return;
  }
  const relaunchArgs = process.platform === 'linux'
    ? buildLinuxCompatibilityRelaunchArgs(appConfig?.compatibilityMode === true)
    : undefined;
  relaunchApp('restart app', relaunchArgs);
});

// ===== 屏幕捕获源选择 IPC 处理器 =====
// 用于获取可共享的屏幕/窗口列表
ipcMain.handle(AUTOSTART_CHANNELS.GET_STATUS, () => {
  return autostartService.getStatus();
});

ipcMain.handle(AUTOSTART_CHANNELS.ENABLE, () => {
  return applyAutostartPreference(true);
});

ipcMain.handle(AUTOSTART_CHANNELS.DISABLE, () => {
  return applyAutostartPreference(false);
});

// ===== 托盘菜单本地化 =====
// 支持的语言

// 当前语言（默认英文）
let currentLanguage = 'en';
let _languageReadyResolve;
const languageReady = new Promise(resolve => { _languageReadyResolve = resolve; });

// 获取系统语言
function getSystemLanguage() {
  const locale = app.getLocale();
  log('getSystemLanguage() - 系统语言:', locale);

  return normalizeSupportedLanguage(locale);
}

function normalizeSupportedLanguage(language) {
  const locale = String(language || '').trim();

  // 检查是否支持
  if (SUPPORTED_LANGUAGES.includes(locale)) {
    return locale;
  }

  // 检查语言前缀
  const langCode = locale.split('-')[0];
  if (langCode === 'zh') {
    // 繁体中文地区
    if (locale === 'zh-TW' || locale === 'zh-HK' || locale === 'zh-Hant') {
      return 'zh-TW';
    }
    return 'zh-CN';
  }
  if (langCode === 'en') {
    return 'en';
  }
  if (langCode === 'ja') {
    return 'ja';
  }
  if (langCode === 'ko') {
    return 'ko';
  }
  if (langCode === 'ru') {
    return 'ru';
  }
  if (langCode === 'es') {
    return 'es';
  }
  if (langCode === 'pt') {
    return 'pt';
  }

  // 默认英文
  return 'en';
}

function requestBackendJson(pathname, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    let urlObj;
    try {
      urlObj = new URL(pathname, appConfig?.apiBaseUrl || 'http://localhost:48911/');
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
      let data = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        data += chunk;
        if (data.length > 1024 * 1024) {
          req.destroy(new Error('Response too large'));
        }
      });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        try {
          resolve(data ? JSON.parse(data) : {});
        } catch (e) {
          reject(e);
        }
      });
    });

    req.on('timeout', () => req.destroy(new Error('Timeout')));
    req.on('error', reject);
    req.end();
  });
}

// 从后端已有配置接口获取语言，保持和网页端 i18n 初始化同源。
async function fetchLanguageConfig() {
  try {
    const steamPayload = await requestBackendJson('/api/config/steam_language');
    if (steamPayload && steamPayload.success && steamPayload.i18n_language) {
      const steamLanguage = normalizeSupportedLanguage(steamPayload.i18n_language);
      log('fetchLanguageConfig() - 使用 Steam 语言设置:', steamLanguage);
      return steamLanguage;
    }
  } catch (err) {
    log('fetchLanguageConfig() - 获取 Steam 语言配置失败:', err.message);
  }

  try {
    const userPayload = await requestBackendJson('/api/config/user_language');
    if (userPayload && userPayload.success && userPayload.language) {
      const userLanguage = normalizeSupportedLanguage(userPayload.language);
      log('fetchLanguageConfig() - 使用用户语言设置:', userLanguage);
      return userLanguage;
    }
  } catch (err) {
    log('fetchLanguageConfig() - 获取用户语言配置失败:', err.message);
  }

  return null;
}

// 初始化语言设置
async function initializeLanguage() {
  try {
    // 先尝试从后端获取和网页端一致的语言设置
    const serverLanguage = await fetchLanguageConfig();
    if (serverLanguage) {
      currentLanguage = serverLanguage;
      log('initializeLanguage() - 使用服务器语言设置:', currentLanguage);
      return;
    }

    // 后端不可用或未返回有效语言时，使用 Electron 系统语言兜底。
    currentLanguage = getSystemLanguage();
    log('initializeLanguage() - 使用系统语言:', currentLanguage);
  } finally {
    _languageReadyResolve(currentLanguage);
  }
}

// 获取本地化文本
function t(key) {
  return tForLanguage(key, currentLanguage);
}

function tForLanguage(key, language = currentLanguage) {
  const normalizedLanguage = normalizeSupportedLanguage(language);
  const texts = trayMenuLocales[normalizedLanguage] || trayMenuLocales['en'];
  return texts[key] || trayMenuLocales['en'][key] || key;
}


function loadingText(key) {
  const en = trayMenuLocales['en'] || {};
  return en[key] || key;
}

function getIcon() {
  const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
  const platform = process.platform;
  let iconPath;

  if (platform === 'darwin') {
    // macOS 使用 .icns 或 .png
    const icnsPath = path.join(basePath, 'icon.icns');
    const pngPath = path.join(basePath, 'icon.png');
    if (fs.existsSync(icnsPath)) {
      iconPath = icnsPath;
    } else if (fs.existsSync(pngPath)) {
      iconPath = pngPath;
    } else {
      // 如果没有找到 macOS 格式的图标，尝试使用 build 目录下的
      const buildIcnsPath = path.join(basePath, 'build', 'icon.icns');
      if (fs.existsSync(buildIcnsPath)) {
        iconPath = buildIcnsPath;
      } else {
        iconPath = path.join(basePath, 'icon.ico'); // 最后的回退
      }
    }
  } else if (platform === 'win32') {
    // Windows 使用 .ico
    iconPath = path.join(basePath, 'icon.ico');
  } else {
    // Linux 使用 .png
    const pngPath = path.join(basePath, 'icon.png');
    iconPath = fs.existsSync(pngPath) ? pngPath : path.join(basePath, 'icon.ico');
  }

  log('getIcon() - platform:', platform, '- iconPath:', iconPath, '- 存在:', fs.existsSync(iconPath));
  return iconPath;
}

function getAppResourceBasePath() {
  return app.isPackaged ? process.resourcesPath : process.cwd();
}

function getLauncherBannerSize() {
  const fallback = { width: 900, height: 768 };
  try {
    const bannerPath = path.join(getAppResourceBasePath(), 'launcher_banner.png');
    if (!fs.existsSync(bannerPath)) return fallback;
    const image = nativeImage.createFromPath(bannerPath);
    if (!image || image.isEmpty()) return fallback;
    const size = image.getSize();
    if (
      size &&
      Number.isFinite(size.width) &&
      Number.isFinite(size.height) &&
      size.width > 0 &&
      size.height > 0
    ) {
      return {
        width: Math.round(size.width),
        height: Math.round(size.height),
      };
    }
  } catch (error) {
    log('[LoadingWindow] launcher banner size probe failed:', error && error.message ? error.message : error);
  }
  return fallback;
}

function writeLoadingWindowHtml(ratio) {
  if (!getLoadingDataURL || typeof getLoadingDataURL.getHTML !== 'function') return null;
  try {
    const runtimeDir = path.join(app.getPath('userData'), 'runtime');
    fs.mkdirSync(runtimeDir, { recursive: true });
    const htmlPath = path.join(runtimeDir, 'loading-window.html');
    fs.writeFileSync(htmlPath, getLoadingDataURL.getHTML(ratio, { assetMode: 'file' }), 'utf8');
    return htmlPath;
  } catch (error) {
    log('[LoadingWindow] write local loading HTML failed:', error && error.message ? error.message : error);
    return null;
  }
}

// 创建加载窗口
function createLoadingWindow() {
  loadingWindowStatus = {
    title: loadingText('loadingStartingTitle'),
    detail: loadingText('loadingStartingDetail'),
  };
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const bannerSize = getLauncherBannerSize();
  const baseWidth = bannerSize.width;
  const baseHeight = bannerSize.height;

  // 根据工作区大小计算缩放比例（留 10% 边距，且不超过 1.0 防止放大），再按当前设计整体缩小 30%。
  const ratio = Math.min(width * 0.9 / baseWidth, height * 0.9 / baseHeight, 1.0) * 0.56;
  const windowWidth = Math.floor(baseWidth * ratio);
  const windowHeight = Math.floor(baseHeight * ratio);

  loadingWindow = new BrowserWindow({
    title: loadingText('loadingDocumentTitle'),
    width: windowWidth,
    height: windowHeight,
    x: Math.floor((width - windowWidth) / 2),
    y: Math.floor((height - windowHeight) / 2),
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    movable: true,
    show: false,
    icon: getIcon(),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: false
    }
  });

  const loadingWindowRef = loadingWindow;
  const isLinuxX11LoadingWindow = () => (
    process.platform === 'linux' &&
    !windowManager.isLinuxWaylandRuntime() &&
    loadingWindow === loadingWindowRef &&
    loadingWindowRef &&
    !loadingWindowRef.isDestroyed()
  );
  const getLoadingWindowScaleFactor = () => {
    try {
      const display = screen.getDisplayMatching(loadingWindowRef.getBounds());
      return display && Number.isFinite(display.scaleFactor) ? display.scaleFactor : 1;
    } catch (_) {
      return 1;
    }
  };
  const applyLinuxX11LoadingPassthrough = async (reason) => {
    if (!isLinuxX11LoadingWindow()) return false;
    try {
      loadingWindowRef.setIgnoreMouseEvents(true, { forward: true });
      log(`[LoadingWindow] Linux X11 mouse passthrough (${reason || 'init'})`);
    } catch (error) {
      log('[LoadingWindow] Linux X11 passthrough failed:', error && error.message ? error.message : error);
    }
    try {
      const ok = await applyX11InputShape(loadingWindowRef, [], {
        log,
        scaleFactor: getLoadingWindowScaleFactor(),
        allowNativeFallback: true,
      });
      if (ok) {
        log(`[LoadingWindow] Linux X11 ShapeInput passthrough (${reason || 'init'})`);
      }
      return ok;
    } catch (error) {
      log('[LoadingWindow] Linux X11 ShapeInput passthrough failed:', error && error.message ? error.message : error);
      return false;
    }
  };
  const scheduleLinuxX11LoadingPassthrough = (reason) => {
    if (!isLinuxX11LoadingWindow()) return;
    [0, 16, 50, 120, 300, 700, 1500].forEach((delay) => {
      const timer = setTimeout(() => {
        applyLinuxX11LoadingPassthrough(`${reason || 'show'}:${delay}`).catch(() => {});
      }, delay);
      try { timer.unref(); } catch (_) {}
    });
  };
  const showLoadingWindow = (reason) => {
    if (!loadingWindowRef || loadingWindowRef.isDestroyed() || loadingWindow !== loadingWindowRef) return;
    if (!loadingWindowRef.isVisible()) {
      try {
        if (isLinuxX11LoadingWindow() && typeof loadingWindowRef.showInactive === 'function') {
          loadingWindowRef.showInactive();
        } else {
          loadingWindowRef.show();
        }
        log(`[LoadingWindow] shown (${reason || 'show'})`);
      } catch (error) {
        log('[LoadingWindow] show failed:', error && error.message ? error.message : error);
      }
    }
    if (isLinuxX11LoadingWindow()) {
      scheduleLinuxX11LoadingPassthrough(reason || 'after-show');
    }
  };
  const isLinuxX11Loading = isLinuxX11LoadingWindow();
  let x11LoadingShown = false;
  const showLinuxX11LoadingOnce = (reason) => {
    if (x11LoadingShown) return;
    x11LoadingShown = true;
    showLoadingWindow(reason);
  };
  const initialX11LoadingPassthrough = isLinuxX11Loading
    ? applyLinuxX11LoadingPassthrough('before-show')
    : Promise.resolve(false);

  // 启动图较大时避免把图片塞进 data: URL，改用本地 HTML 直接引用资源文件。
  const loadingHtmlPath = writeLoadingWindowHtml(ratio);
  if (loadingHtmlPath) {
    loadingWindowRef.loadFile(loadingHtmlPath).catch((error) => {
      log('[LoadingWindow] load local loading HTML failed:', error && error.message ? error.message : error);
      if (!loadingWindowRef.isDestroyed()) {
        loadingWindowRef.loadURL(getLoadingDataURL(ratio));
      }
    });
  } else {
    loadingWindowRef.loadURL(getLoadingDataURL(ratio));
  }
  if (isLinuxX11Loading) {
    initialX11LoadingPassthrough.then((ok) => {
      if (ok) {
        showLinuxX11LoadingOnce('x11-shape-input-ready');
      } else {
        log('[LoadingWindow] Linux X11 loading window kept hidden until native passthrough is available');
      }
    }).catch((error) => {
      log('[LoadingWindow] Linux X11 initial ShapeInput passthrough failed:', error && error.message ? error.message : error);
    });
    loadingWindowRef.webContents.once('did-finish-load', () => {
      applyLinuxX11LoadingPassthrough('did-finish-load').then((ok) => {
        if (ok) showLinuxX11LoadingOnce('x11-shape-input-ready:did-finish-load');
      }).catch(() => {});
    });
  } else {
    showLoadingWindow('normal');
  }
  loadingWindow.setAlwaysOnTop(true, process.platform === 'darwin' ? 'floating' : 'screen-saver');
  loadingWindow.on('close', () => {
    if (loadingWindowCloseIsInternal) return;
    log('用户关闭启动加载窗口，退出应用');
    requestAppQuit('loading window close');
  });
  loadingWindow.on('closed', () => {
    loadingWindow = null;
  });
}

function updateLoadingWindowStatus(next = {}) {
  loadingWindowStatus = {
    ...loadingWindowStatus,
    ...next,
  };

  if (!loadingWindow || loadingWindow.isDestroyed()) return;
  const payload = {
    title: String(loadingWindowStatus.title || ''),
    detail: String(loadingWindowStatus.detail || ''),
  };
  try {
    loadingWindow.webContents.executeJavaScript(
      `window.__nekoSetLoadingStatus && window.__nekoSetLoadingStatus(${JSON.stringify(payload)})`,
    ).catch(() => {});
  } catch (e) { /* ignore */ }
}

function closeLoadingWindow() {
  if (loadingWindow && !loadingWindow.isDestroyed()) {
    loadingWindowCloseIsInternal = true;
    loadingWindow.close();
    loadingWindowCloseIsInternal = false;
    loadingWindow = null;
  }
}

let backendRuntime = null;

function cleanupResources(reason = 'unknown', options = {}) {
  try {
    clearPendingTutorialOverlayRelays();
    clearTutorialHotkeySuppression('tutorial-forced-cleanup');
    clearTutorialSystemCursor('tutorial-forced-cleanup');
    tutorialGlobalOverlayService.stop();
  } catch (_) {}
  try {
    powerSaveBlockerService.stop(`cleanup:${reason}`);
  } catch (_) {}
  if (backendRuntime?.cleanupResources) {
    return backendRuntime.cleanupResources(reason, options);
  }
}

function requestAppQuit(reason = 'unknown') {
  if (backendRuntime?.requestAppQuit) {
    return backendRuntime.requestAppQuit(reason);
  }
  app.quit();
}

function isAppQuitRequested() {
  return backendRuntime?.isAppQuitRequested?.() === true;
}

backendRuntime = createBackendRuntime({
  NEKO_DEFAULT_PORTS,
  app,
  console,
  fs,
  getAppConfig: () => appConfig,
  getNekoActivePorts: () => nekoActivePorts,
  getOriginalUrl: () => originalUrl,
  http,
  https,
  loadingText,
  log,
  logStream,
  path,
  process,
  reloadAndShow,
  resolveServerUrl,
  setNekoActivePorts: (next) => { nekoActivePorts = next; },
  setOriginalUrl: (next) => { originalUrl = sanitizeOriginalUrl(next, originalUrl); },
  spawn,
  spawnSync,
  stopPetGameModeWatcher,
  stopStorageGatePolling,
  stopTopReassertion,
  updateLoadingWindowStatus,
  windowManager,
});

const {
  createBackendReadyPromise,
  restartPythonServiceAndReload,
  scanForExistingBackend,
  startDevParentExitWatchdog,
  startOpenFangProcess,
  startPythonProcess,
  waitForServerReady,
} = backendRuntime;

// 获取指定屏幕或主屏幕的边界（不再覆盖所有屏幕）
const petWindowLifecycle = createPetWindowLifecycle({
  BrowserWindow,
  _ignoreStateByWindow,
  _lastShapeByWindow,
  _lastShapeMetaByWindow,
  app,
  applyTopOn,
  bindWindowDisplayRecovery,
  boundsApproximatelyEqual,
  dialog,
  ensureMarkDirtyHooked,
  fs,
  getAppConfig: () => appConfig,
  getChildWindowTopLevel,
  getFullscreenDisplayBounds,
  getInputRegionBackend,
  getIcon,
  getEffectiveWindowShapeRects,
  getNativeWindowShapeRects,
  getIsGlobalAlwaysOnTop: () => isGlobalAlwaysOnTop,
  getIsStreamerMode: () => isStreamerMode,
  getLoadingWindow: () => loadingWindow,
  getManagedTopLevel,
  isLinuxWaylandRuntime,
  isNormalFramedPopup,
  isWindowedToolPopup,
  isStorageMaintenanceProtectionActive,
  log,
  mainDirname: __dirname,
  markZOrderDirty,
  path,
  process,
  screen,
  setMainWindow: (win) => { mainWindow = win; },
  setReloadPetAfterMaintenanceReady,
  shouldUseNativeIgnoreMouse,
  windowManager,
});

const {
  createWindow,
  getAllDisplaysBounds,
  getDisplayBounds,
  schedulePetBoundsRepair,
  setupPetWindowBehavior,
} = petWindowLifecycle;

const trayMenuController = createTrayMenuController({
  BrowserWindow,
  Menu,
  _pushDarkModeToHotkeyWindow,
  applyAutostartPreference,
  applyProxySettings,
  applyTopOn,
  autostartService,
  beginSystemMenuOcclusionGuard,
  buildLinuxCompatibilityRelaunchArgs,
  createHotkeyWindow,
  createPortSettingsWindow,
  dialog,
  ensureReactChatWindow,
  endSystemMenuOcclusionGuard,
  feedbackModule,
  confirmTrayExitWithRetention,
  hideReactChatFromMain,
  getAppConfig: () => appConfig || getConfig(),
  getIsGlobalAlwaysOnTop: () => isGlobalAlwaysOnTop,
  getIsMobileMode: () => isMobileMode,
  getPreventSystemSleepStatus: () => powerSaveBlockerService.getStatus(),
  getIsStreamerMode: () => isStreamerMode,
  getLoadingWindow: () => loadingWindow,
  getMainWindow: () => mainWindow,
  getOriginalUrl: () => originalUrl,
  getTray: () => tray,
  guardStorageStartupGate,
  http,
  ipcRouter,
  log,
  process,
  reloadAndShow,
  relaunchApp,
  requestAppQuit,
  saveConfig,
  setIsGlobalAlwaysOnTop: (next) => { isGlobalAlwaysOnTop = next; },
  setIsMobileMode: (next) => { isMobileMode = next; },
  setPreventSystemSleepEnabled: (enabled, reason) => powerSaveBlockerService.setEnabled(enabled, reason),
  setIsStreamerMode: (next) => { isStreamerMode = next; },
  shell,
  https,
  startTopReassertion,
  stopPetGameModeWatcher,
  stopTopReassertion,
  t,
  updateTrayMenuSoon: () => setTimeout(() => updateTrayMenu(), 100),
  windowManager,
});

const {
  applyGlobalAlwaysOnTop,
  updateTrayMenu,
} = trayMenuController;

app.setAppUserModelId('N.E.K.O.');

// 捕获未处理的错误
process.on('uncaughtException', (error) => {
  log('未捕获的异常:', error.message);
  log('堆栈:', error.stack);
});

process.on('unhandledRejection', (reason, promise) => {
  log('未处理的 Promise 拒绝:', reason);
});

app.whenReady().then(async () => {
  log('app.whenReady() - 应用已准备就绪');
  startDevParentExitWatchdog();
  avatarToolCursorService.configure({
    app,
    BrowserWindow,
    screen,
    log,
    getBaseUrl: () => originalUrl,
    getGlobalPointerContext: getAvatarToolGlobalPointerContext,
    onStateRefresh: publishAvatarToolPolledCursorState,
    shouldSuppressNativeCursorRestore: () => systemCursorVisibilityService.isHiddenRequested(),
  });
  tutorialGlobalOverlayService.configure({
    app,
    BrowserWindow,
    screen,
    ipcMain,
    log,
    getBaseUrl: () => originalUrl,
  });

  // ===== Linux 透明视觉初始化延迟 =====
  // Linux 上 --enable-transparent-visuals 需要时间初始化，
  // 过早创建窗口会导致透明效果不生效
  if (process.platform === 'linux') {
    log('Linux: 等待透明视觉效果初始化...');
    await new Promise(resolve => setTimeout(resolve, 1000));
    log('Linux: 透明视觉效果初始化完成');
  }

  // ===== macOS 麦克风权限 =====
  // macOS Catalina+ 要求 Electron 显式请求麦克风权限，
  // 否则 getUserMedia 返回的 stream 音频数据为全零（静音）。
  if (process.platform === 'darwin') {
    const { systemPreferences } = require('electron');
    const micStatus = systemPreferences.getMediaAccessStatus('microphone');
    log('麦克风权限状态:', micStatus);
    if (micStatus !== 'granted') {
      const granted = await systemPreferences.askForMediaAccess('microphone');
      log('麦克风权限请求结果:', granted);
    }
  }

  // ===== 自动授予媒体权限（麦克风/摄像头/屏幕共享/剪贴板） =====
  const allowedPermissions = [
    'media', 'mediaKeySystem', 'display-capture', 'screen-wake-lock', 'fileSystem',
    'clipboard-read', 'clipboard-sanitized-write',
  ];
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    if (allowedPermissions.includes(permission)) {
      log('自动授予权限:', permission);
      callback(true);
    } else {
      log('拒绝权限请求:', permission);
      callback(false);
    }
  });

  session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
    return allowedPermissions.includes(permission);
  });

  // ===== 下载管理（处理前端 <a> fallback 下载） =====
  session.defaultSession.on('will-download', (event, item, webContents) => {   
    const suggestedName = item.getFilename() || 'download';
    log('will-download 触发:', suggestedName, '大小:', item.getTotalBytes());  

    // 弹出另存为对话框
    const win = BrowserWindow.fromWebContents(webContents) || mainWindow;
    const savePath = dialog.showSaveDialogSync(win, {
      defaultPath: suggestedName,
    });

    if (savePath) {
      item.setSavePath(savePath);
    } else {
      item.cancel();
    }
  });

  // 初始化反馈窗口 IPC 处理器
  feedbackModule.initFeedbackIPC({
    getBackendUrl: () => originalUrl || resolveServerUrl('MAIN_SERVER'),
  });

  // 初始化快捷键 IPC 处理器
  initHotkeyIPC();

  // 加载并注册全局快捷键（仅当用户上次未禁用时）
  loadHotkeyConfig();
  if (areHotkeysEnabled()) {
    registerGlobalHotkeys();
  } else {
    log('快捷键已被禁用，跳过启动注册');
  }

  const chatDisplayMediaHandler = async (request, callback) => {
    try {
      // 同时枚举 window 和 screen，以便匹配用户从下拉菜单选中的任意类型源
      const sources = await desktopCapturer.getSources({ types: ['window', 'screen'] });
      let chosen = null;
      const selectedSourceId = screenCaptureIpc.getSelectedScreenSourceId(
        request?.webContents?.id || request?.frame?.top?.id || request?.frame?.id
      );
      if (selectedSourceId) {
        chosen = sources.find(s => s.id === selectedSourceId) || null;
      }
      if (!chosen) {
        // 回退：首块屏幕源；再不行随便挑一个
        chosen = sources.find(s => s.id.startsWith('screen:')) || sources[0] || null;
      }
      if (chosen) {
        callback({ video: chosen, audio: false });
      } else {
        callback({});
      }
    } catch (e) {
      try { log('setDisplayMediaRequestHandler 错误:', e && e.message); } catch (_) { }
      callback({});
    }
  };
  session.defaultSession.setDisplayMediaRequestHandler(chatDisplayMediaHandler, { useSystemPicker: true });

  // full 独立聊天窗口走独立 session 分区（FULL_CHAT_PARTITION，为隔离 electronSavedBounds 几何 key）。
  // 把聊天相关的会话级处理（权限自动授予 / 下载另存 / 屏幕共享源选择）同等应用到该分区，
  // 否则 full 与 compact 在权限、下载、屏幕捕获链路行为不一致（codex/coderabbit #183 指出）。
  try {
    const fullSess = session.fromPartition(windowManager.FULL_CHAT_PARTITION);
    fullSess.setPermissionRequestHandler((webContents, permission, callback) => {
      callback(allowedPermissions.includes(permission));
    });
    fullSess.setPermissionCheckHandler((webContents, permission) => allowedPermissions.includes(permission));
    fullSess.on('will-download', (event, item, webContents) => {
      const suggestedName = item.getFilename() || 'download';
      const win = BrowserWindow.fromWebContents(webContents) || mainWindow;
      const savePath = dialog.showSaveDialogSync(win, { defaultPath: suggestedName });
      if (savePath) item.setSavePath(savePath); else item.cancel();
    });
    fullSess.setDisplayMediaRequestHandler(chatDisplayMediaHandler, { useSystemPicker: true });
  } catch (e) {
    try { log('配置 full 分区 session 失败:', e && e.message); } catch (_) {}
  }

  appConfig = getConfig();
  // 安全：用户配置的 apiBaseUrl 只接受 loopback，远程地址拒绝
  originalUrl = sanitizeOriginalUrl(appConfig.apiBaseUrl, '');

  if (appConfig.preventSystemSleep === true) {
    const preventSleepResult = powerSaveBlockerService.start('startup');
    if (!preventSleepResult.ok) {
      log('防睡眠启动失败:', preventSleepResult.error || 'unknown');
      appConfig.preventSystemSleep = false;
      try { saveConfig(appConfig); } catch (_) {}
    }
  }

  // 应用自定义端口配置（如果已保存）
  if (appConfig.customPorts) {
    const cp = appConfig.customPorts;
    if (cp.MAIN_SERVER_PORT && Number.isInteger(cp.MAIN_SERVER_PORT) && cp.MAIN_SERVER_PORT >= 1 && cp.MAIN_SERVER_PORT <= 65535) {
      NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT = cp.MAIN_SERVER_PORT;
    }
    if (cp.MEMORY_SERVER_PORT && Number.isInteger(cp.MEMORY_SERVER_PORT) && cp.MEMORY_SERVER_PORT >= 1 && cp.MEMORY_SERVER_PORT <= 65535) {
      NEKO_DEFAULT_PORTS.MEMORY_SERVER_PORT = cp.MEMORY_SERVER_PORT;
    }
    if (cp.TOOL_SERVER_PORT && Number.isInteger(cp.TOOL_SERVER_PORT) && cp.TOOL_SERVER_PORT >= 1 && cp.TOOL_SERVER_PORT <= 65535) {
      NEKO_DEFAULT_PORTS.TOOL_SERVER_PORT = cp.TOOL_SERVER_PORT;
    }
    if (cp.USER_PLUGIN_SERVER_PORT && Number.isInteger(cp.USER_PLUGIN_SERVER_PORT) && cp.USER_PLUGIN_SERVER_PORT >= 1 && cp.USER_PLUGIN_SERVER_PORT <= 65535) {
      NEKO_DEFAULT_PORTS.USER_PLUGIN_SERVER_PORT = cp.USER_PLUGIN_SERVER_PORT;
    }
    nekoActivePorts = { ...NEKO_DEFAULT_PORTS };
    originalUrl = sanitizeOriginalUrl(resolveServerUrl('MAIN_SERVER'), `http://127.0.0.1:${NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT}/`);
    log('已应用自定义端口配置:', JSON.stringify(NEKO_DEFAULT_PORTS));

    // 同步写入 userData 目录，确保 Python 后端能读取
    try {
      const portConfigPath = path.join(app.getPath('userData'), 'port_config.json');
      fs.writeFileSync(portConfigPath, JSON.stringify(appConfig.customPorts, null, 2), 'utf-8');
    } catch (e) {
      log('启动时写入 port_config.json 失败:', e.message);
    }
  } else {
    // 没有自定义端口时，清理可能残留的 port_config.json
    try {
      const portConfigPath = path.join(app.getPath('userData'), 'port_config.json');
      if (fs.existsSync(portConfigPath)) {
        fs.unlinkSync(portConfigPath);
      }
    } catch (e) { /* ignore */ }
  }

  // 应用自定义 URL 覆盖（如果已保存）
  // startupUrlFallback：启动快速探测失败时记录，供 startMainWindow 之后自动打开端口设置提示用户
  let startupUrlFallback = null;
  if (appConfig.customUrls) {
    try {
      const cu = appConfig.customUrls;
      for (const key of ['MAIN_SERVER_URL', 'MEMORY_SERVER_URL', 'TOOL_SERVER_URL', 'USER_PLUGIN_SERVER_URL']) {
        if (cu[key] && typeof cu[key] === 'string' && cu[key].trim().length > 0) {
          customUrlOverrides[key] = cu[key].trim();
        }
      }

      // 启动快速探测：自定义主服务器 URL 不通时自动降级到本地地址，避免 Pet 卡加载。
      // 磁盘 customUrls 保持不变 —— 用户修好远端后下次启动会再次尝试；
      // 本次会话内只把 customUrlOverrides.MAIN_SERVER_URL 清掉，
      // 后续 useRemoteBackend 判断和 resolveServerUrl 都基于它，所以会自动走本地模式。
      if (customUrlOverrides.MAIN_SERVER_URL) {
        try {
          const r = await probeUrlReachable(customUrlOverrides.MAIN_SERVER_URL, 2000);
          log('启动探测自定义主服务器 URL OK:', customUrlOverrides.MAIN_SERVER_URL, 'status=', r.statusCode);
        } catch (probeErr) {
          const deadUrl = customUrlOverrides.MAIN_SERVER_URL;
          log('WARNING: 启动探测自定义 URL 失败，本次会话回退到本地地址:', deadUrl, probeErr.message || probeErr);
          startupUrlFallback = { url: deadUrl, error: probeErr.message || String(probeErr) };
          customUrlOverrides.MAIN_SERVER_URL = null;
        }
      }

      originalUrl = sanitizeOriginalUrl(resolveServerUrl('MAIN_SERVER'), `http://127.0.0.1:${NEKO_DEFAULT_PORTS.MAIN_SERVER_PORT}/`);
      log('已应用自定义 URL 覆盖:', JSON.stringify(customUrlOverrides));
    } catch (e) {
      log('WARNING: customUrls 格式异常，已忽略:', e.message);
      for (const key of Object.keys(customUrlOverrides)) customUrlOverrides[key] = null;
    }
  }

  // 初始化窗口模式状态
  isStreamerMode = !!appConfig.streamerMode;
  log('初始化窗口模式状态:', isStreamerMode);

  // 初始化全局置顶状态
  isGlobalAlwaysOnTop = appConfig.globalAlwaysOnTop !== false;
  log('初始化全局置顶状态:', isGlobalAlwaysOnTop);

  // 注入全局置顶 coordinator —— 必须在 createAllWindows 之前
  // window-manager 内部创建窗口时会通过此 coordinator 决定 alwaysOnTop 行为
  windowManager.setTopCoordinator({
    isEnabled: () => isGlobalAlwaysOnTop,
    applyTo: (win, classification) => applyTopOn(win, classification),
  });

  // 启用态下立即开启周期性 Z-order 重断言，兼容无边框全屏游戏
  if (isGlobalAlwaysOnTop) {
    startTopReassertion();
  }

  // 应用代理设置（默认关闭系统代理）
  try {
    await applyProxySettings(!!appConfig.useSystemProxy);
  } catch (e) {
    log('应用代理设置时出错:', e.message);
  }

  // 启动时校准自启动状态与本地配置，必要时修复路径或恢复注册
  try {
    const autostartStatus = autostartService.reconcile();
    log('自启动初始化结果:', JSON.stringify({
      ...buildAutostartStatusPayload(autostartStatus),
      system_status: autostartStatus.system_status,
    }));
    broadcastAutostartStatusChanged(autostartStatus);
  } catch (e) {
    log('初始化自启动状态时出错:', e.message);
  }

  // ⭐ 启动加载窗口（独立小窗）
  log('创建加载窗口');
  createLoadingWindow();

  let hasStartedMainWindow = false;
  const startMainWindow = (reason) => {
    if (hasStartedMainWindow) return;
    hasStartedMainWindow = true;
    if (reason) {
      log(reason);
    }
    log('关闭加载窗口');
    closeLoadingWindow();

    // ===== 多窗口模式 =====
    log('创建多窗口, URL:', originalUrl);
    const windows = windowManager.createAllWindows(originalUrl, {
      isPackaged: app.isPackaged,
      isStreamerMode,
      log,
      autoCreateReactChat: false,
    });

    // 兼容引用：mainWindow 指向 petWindow，保持现有 IPC handler 和 tray 逻辑不变
    mainWindow = windows.pet;

    // 设置 IPC 消息路由
    ipcRouter.setupIPCRouter({
      getWindows: () => windowManager.getWindows(),
      log,
    });

    // 设置 Pet 窗口的子窗口行为和生命周期钩子
    setupPetWindowBehavior(mainWindow);
    attachStorageGateToPetWindow(mainWindow);

    createTrayAfterActivation();

    // 启动快速探测失败 → 自动打开端口设置窗口并把警告推送进去，
    // 让用户立刻看到"保存的自定义 URL 不通，本次启动已回退到本地"。
    if (startupUrlFallback) {
      try {
        if (isStorageMaintenanceProtectionActive()) {
          log('存储维护保护模式下跳过自动打开端口设置窗口');
        } else {
          createPortSettingsWindow();
          const win = getPortSettingsWindow();
          if (win && !win.isDestroyed() && win.webContents) {
            const payload = {
              ok: false,
              url: startupUrlFallback.url,
              error: startupUrlFallback.error,
            };
            // did-finish-load 后脚本已注册好 ipcRenderer.on 监听器，再 send 就不会丢
            if (win.webContents.isLoading()) {
              win.webContents.once('did-finish-load', () => {
                try { win.webContents.send('port-config-probe-result', payload); } catch (_) {}
              });
            } else {
              try { win.webContents.send('port-config-probe-result', payload); } catch (_) {}
            }
          }
        }
      } catch (e) {
        log('自动打开端口设置窗口失败:', e.message);
      }
    }
  };

  // ===== 分支：是否进入"远程后端"模式 =====
  // 当 customUrls.MAIN_SERVER_URL 被显式设置时，用户选择把前端指向远程已部署的 NEKO 后端。
  // 这种情况下跳过所有本地后端启动（Python launcher + OpenFang）—— 本地资源留给远端用。
  // 这里看 customUrlOverrides（而不是 appConfig.customUrls），因为启动探测失败时已把
  // customUrlOverrides.MAIN_SERVER_URL 清为 null，自动降级到本地模式。
  const useRemoteBackend = !!customUrlOverrides.MAIN_SERVER_URL;

  if (useRemoteBackend) {
    log('[Remote Mode] customUrls.MAIN_SERVER_URL 已设置，跳过本地 Python/OpenFang 启动');
    log('[Remote Mode] 目标 URL:', originalUrl);

    // 直连远端：只做一次可达性检查；不通也照样建窗口，由 Pet 的 did-fail-load 兜底提示
    waitForServerReady(originalUrl, { timeout: 30000, interval: 500 })
      .then(() => {
        log('[Remote Mode] 远端后端就绪:', originalUrl);
        startMainWindow('Remote backend ready');
      })
      .catch((err) => {
        log('[Remote Mode] 远端后端检测失败，仍继续建窗口:', err.message);
        startMainWindow(`Remote backend check failed, proceeding: ${err.message}`);
      });
  } else {
    // ===== 本地模式：保持既有启动流程 =====

    // OpenFang：无论 Python 后端是否已存在，都尝试启动
    // OpenFang 是独立的 Agent 执行后端，不依赖 Python 后端状态
    startOpenFangProcess()
      .then((result) => {
        log('OpenFang startup result:', JSON.stringify(result));
      })
      .catch((err) => {
        log('OpenFang startup failed (non-critical):', err.message);
      });

    // ===== Step A：扫描默认端口，检查是否已有 N.E.K.O 后端 =====
    log('Step A: Scanning default ports for existing N.E.K.O backend...');
    const scan = await scanForExistingBackend();

    if (scan.found) {
      // MAIN + TOOL 命中即视为已有后端（memory 可选，见 scanForExistingBackend 注释）。
      // 直接复用现有后端，不再新拉起。wrapper 模式下 48912 不启动属设计性缺失。
      log('Step A: Existing N.E.K.O backend found on default ports, reusing.');
      if (!scan.services.MEMORY_SERVER_PORT) {
        log('Step A: memory_server port not responding (optional in wrapper mode, skipped)');
      }
      nekoActivePorts = { ...NEKO_DEFAULT_PORTS, ...scan.ports };
      originalUrl = sanitizeOriginalUrl(resolveServerUrl('MAIN_SERVER'), `http://127.0.0.1:${nekoActivePorts.MAIN_SERVER_PORT}/`);
      startMainWindow('Existing backend detected, attaching');
    } else {
      // ===== Step B：未发现有效后端，启动 launcher =====
      log('Step B: No complete N.E.K.O backend found, starting launcher...');

      // 创建 Promise，等待 startup_ready / attach_existing 事件解析
      const backendReadyPromise = createBackendReadyPromise();

      startPythonProcess()
        .then(() => {
          log('Python launcher process started (or completed)');
        })
        .catch((err) => {
          log('Python launcher process failed:', err.message);
        });

      // ===== Step C + D：等待 port_plan → startup_ready，再发起连接 =====
      // 并行竞争三种完成条件：
      // 1) backendReadyPromise（由 NEKO_EVENT startup_ready / attach_existing 触发）
      // 2) waitForServerReady(originalUrl)（兼容旧版 launcher）
      // 3) 总超时
      const legacyReady = waitForServerReady(originalUrl);
      const overallTimeout = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Overall backend startup timeout (90s)')), 90000),
      );

      Promise.race([backendReadyPromise, legacyReady, overallTimeout])
        .then(() => {
          // 此时 originalUrl 可能已被 port_plan/startup_ready 更新。
          log('Backend ready. Using URL:', originalUrl);
          // 最终确认：对（可能更新后的）URL 再做一次快速 HTTP 探测
          return waitForServerReady(originalUrl, { timeout: 15000, interval: 300 });
        })
        .then(() => {
          startMainWindow('Backend confirmed ready');
        })
        .catch((err) => {
          startMainWindow(`Backend startup uncertain, proceeding anyway: ${err.message}`);
        });
    }
  }

  app.on('window-all-closed', () => {
    if (isAppQuitRequested()) {
      return;
    }
    // 注册该事件本身就会接管 Electron 的默认退出行为。
    // N.E.K.O 有托盘菜单，因此普通关窗保持后台；真正退出走 requestAppQuit。
    log('所有窗口已关闭，保持托盘后台运行');
  });
});

async function createTrayAfterActivation() {
  await new Promise(r => setTimeout(r, 500));

  // 初始化语言设置（在创建托盘之前）
  await initializeLanguage();
  log('createTrayAfterActivation() - 语言初始化完成，当前语言:', currentLanguage);

  // 残缺的 icon.icns（如 build/icon.icns 只含 ic08 单条目）会让 macOS 的
  // nativeImage 在 Tray 构造时抛 "Failed to load image"，导致 tray 永远
  // 是 undefined、整个右键菜单消失。先按 getIcon() 的偏好试一次，失败
  // 就退到同目录下的 icon.png（系统状态栏渲染 16/32px PNG 比解析坏 icns
  // 更稳）；都失败才放弃。
  const primaryIconPath = getIcon();
  try {
    tray = new Tray(primaryIconPath);
  } catch (primaryErr) {
    log('createTrayAfterActivation() - 主图标加载失败，回退到 PNG:', primaryErr && primaryErr.message);
    const basePath = app.isPackaged ? process.resourcesPath : process.cwd();
    const pngFallback = path.join(basePath, 'icon.png');
    try {
      tray = new Tray(pngFallback);
      log('createTrayAfterActivation() - PNG 回退成功:', pngFallback);
    } catch (fallbackErr) {
      log('createTrayAfterActivation() - PNG 回退也失败，跳过托盘创建:', fallbackErr && fallbackErr.message);
      return;
    }
  }

  tray.setToolTip('N.E.K.O.');
  updateTrayMenu();
}

app.on('will-quit', () => {
  log('应用即将退出');
  try {
    globalShortcut.unregisterAll();
  } catch (e) {
    // 忽略卸载快捷键时的异常
  }
  cleanupResources('app will-quit');
});

const handleProcessSignal = (signal) => {
  try {
    log(`收到退出信号: ${signal}`);
  } catch (e) {
    // 忽略日志写入错误
  }
  if (backendRuntime?.markAppQuitRequested) backendRuntime.markAppQuitRequested();
  cleanupResources(`signal ${signal}`);
  process.exit(0);
};

process.on('SIGINT', handleProcessSignal);
process.on('SIGTERM', handleProcessSignal);
process.on('SIGHUP', handleProcessSignal);

process.on('exit', (code) => {
  cleanupResources(`process exit ${code}`);
});
