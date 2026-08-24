/**
 * ipc-router.js
 * IPC 消息路由模块 —— 主进程作为消息总线，在窗口间转发消息
 *
 * 架构：
 *   Pet 窗口 (持有 WebSocket) ──→ 主进程 ──→ Chat / Subtitle / AgentHUD
 *   Chat 窗口 (用户输入)      ──→ 主进程 ──→ Pet 窗口 (发送到 WebSocket)
 *   AgentHUD (agent 控制)     ──→ 主进程 ──→ Pet 窗口
 */

const { BrowserWindow, ipcMain } = require('electron');
const {
  WS_CHANNELS, CHAT_CHANNELS, CHAT_ACTION_CHANNELS, AGENT_CHANNELS, GLOBAL_CHANNELS, WS_PROXY_CHANNELS,
  SETTINGS_CHANNELS, JUKEBOX_CHANNELS, MUSIC_CHANNELS,
} = require('./ipc-channels');

// 窗口引用获取函数（由 setup 时注入）
let _getWindows = null;
let _log = console.log;
let _initialized = false;

// ===== 声明式路由表 =====
// 每条路由：收到 channel 消息后，转发给 targets 列出的窗口
const ROUTES = [
  // Pet → 卫星窗口（WebSocket 消息分发）
  { channel: WS_CHANNELS.TRANSCRIPT,   targets: ['chat', 'subtitle'] },
  { channel: WS_CHANNELS.SPEECH,       targets: ['chat'] },
  { channel: WS_CHANNELS.STATUS,       targets: ['chat'] },
  { channel: WS_CHANNELS.AGENT_UPDATE, targets: ['agentHud'] },
  { channel: WS_CHANNELS.CHAT_MESSAGE, targets: ['chat'] },
  // Chat → Pet（用户输入）
  { channel: CHAT_CHANNELS.SEND_TEXT,      targets: ['pet'] },
  { channel: CHAT_CHANNELS.SEND_AUDIO,     targets: ['pet'] },
  { channel: CHAT_CHANNELS.START_SESSION,  targets: ['pet'] },
  { channel: CHAT_CHANNELS.END_SESSION,    targets: ['pet'] },
  { channel: CHAT_CHANNELS.SCREENSHOT,     targets: ['pet'] },
  { channel: CHAT_CHANNELS.REQUEST_SCREENSHOT, targets: ['pet'] },
  { channel: CHAT_CHANNELS.SCREENSHOT_RESULT,  targets: ['chat'] },
  // Chat → Pet（功能触发）
  { channel: CHAT_ACTION_CHANNELS.AVATAR_PREVIEW, targets: ['pet'] },
  { channel: CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT, targets: ['chat'] },
  { channel: CHAT_ACTION_CHANNELS.JUKEBOX_TOGGLE, targets: ['pet'] },
  { channel: CHAT_ACTION_CHANNELS.CONFIG_REQUEST, targets: ['pet'] },
  { channel: CHAT_ACTION_CHANNELS.CONFIG_RESULT, targets: ['chat'] },
  { channel: CHAT_ACTION_CHANNELS.AVATAR_TOOL_STATE, targets: ['pet'] },
  { channel: CHAT_ACTION_CHANNELS.AVATAR_TOOL_POINTER, targets: ['pet'] },
  { channel: CHAT_ACTION_CHANNELS.VOICE_CONFIG_SWITCHING, targets: ['pet', 'chat'] },
  { channel: CHAT_ACTION_CHANNELS.GOODBYE_CHAT_COMPOSER_HIDDEN, targets: ['pet', 'chat'] },
  // AgentHUD → Pet
  { channel: AGENT_CHANNELS.TOGGLE, targets: ['pet'] },
  // WebSocket 代理通道
  { channel: WS_PROXY_CHANNELS.CONNECTING,  targets: ['chat'] },
  { channel: WS_PROXY_CHANNELS.READY,       targets: ['chat'] },
  { channel: WS_PROXY_CHANNELS.RAW_MESSAGE, targets: ['chat'] },
  { channel: WS_PROXY_CHANNELS.RAW_SEND,    targets: ['pet'] },
  { channel: WS_PROXY_CHANNELS.CLOSED,      targets: ['chat'] },
  // 设置同步：REQUEST 仅 chat→pet
  { channel: SETTINGS_CHANNELS.REQUEST, targets: ['pet'] },
  // Jukebox → Pet（VMD 动画控制）
  { channel: JUKEBOX_CHANNELS.VMD_PLAY,   targets: ['pet'] },
  { channel: JUKEBOX_CHANNELS.VMD_STOP,   targets: ['pet'] },
  { channel: JUKEBOX_CHANNELS.VMD_PAUSE,  targets: ['pet'] },
  { channel: JUKEBOX_CHANNELS.VMD_RESUME, targets: ['pet'] },
];

// ===== 安全发送工具 =====

/**
 * 安全地向窗口发送消息（窗口可能已关闭）
 */
function safeSend(win, channel, data) {
  if (win && !win.isDestroyed()) {
    try {
      win.webContents.send(channel, data);
    } catch (e) {
      // 窗口正在关闭过程中，忽略
    }
  }
}

function getWindowsSnapshot() {
  if (typeof _getWindows !== 'function') {
    return {};
  }
  try {
    return _getWindows() || {};
  } catch (e) {
    try {
      _log('[IPCRouter] 获取窗口引用失败:', e.message);
    } catch (_) {
      // ignore logging failures
    }
    return {};
  }
}

function normalizeFiniteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function enrichAvatarToolStatePayload(event, data) {
  if (!data || typeof data !== 'object' || data.active !== true) return data;
  const payload = { ...data };

  const screenX = normalizeFiniteNumber(payload.cursorScreenX ?? payload.screenX);
  const screenY = normalizeFiniteNumber(payload.cursorScreenY ?? payload.screenY);
  if (screenX !== null && screenY !== null) {
    payload.cursorScreenX = screenX;
    payload.cursorScreenY = screenY;
    return payload;
  }

  const clientX = normalizeFiniteNumber(payload.cursorClientX);
  const clientY = normalizeFiniteNumber(payload.cursorClientY);
  if (clientX !== null && clientY !== null) {
    try {
      const senderWin = event && event.sender ? BrowserWindow.fromWebContents(event.sender) : null;
      if (senderWin && !senderWin.isDestroyed()) {
        const bounds = senderWin.getBounds();
        if (bounds && Number.isFinite(Number(bounds.x)) && Number.isFinite(Number(bounds.y))) {
          payload.cursorScreenX = Number(bounds.x) + clientX;
          payload.cursorScreenY = Number(bounds.y) + clientY;
          return payload;
        }
      }
    } catch (_) {}
  }
  return data;
}

/**
 * 向所有窗口广播
 */
function broadcastToAll(channel, data) {
  const windows = getWindowsSnapshot();
  Object.values(windows).forEach((win) => safeSend(win, channel, data));
}

// ===== 路由设置 =====

/**
 * 初始化 IPC 消息路由
 * @param {object} options
 * @param {Function} options.getWindows - 返回 { pet, chat, subtitle, agentHud }
 * @param {Function} options.log - 日志函数
 */
function setupIPCRouter(options = {}) {
  if (typeof options.getWindows === 'function') {
    _getWindows = options.getWindows;
  }
  _log = options.log || console.log;

  if (_initialized) {
    _log('[IPCRouter] IPC 路由已存在，仅更新窗口引用');
    return;
  }
  _initialized = true;

  _log('[IPCRouter] 初始化 IPC 消息路由');

  // 「附件态」请求响应：用户在可见窗口里发起（截图 / 头像预览），结果是会进 composer 附件态的
  // 一次性数据，只该回给发起者=当前可见的聊天窗口。镜像到两窗口会让别处发起的截图串进隐藏窗口的
  // composer。注意：CONFIG_RESULT 不在此列 —— 它是 bootstrap 配置（猫娘名/主人信息等），full 在
  // 创建后、ready-to-show 前（尚不可见）就会请求，若按「可见」路由会跑去 compact 导致 full 拿不到
  // bootstrap 配置；配置是幂等的，走广播路径同发两窗口即可。
  const CHAT_REQUEST_RESPONSE_CHANNELS = new Set([
    CHAT_CHANNELS.SCREENSHOT_RESULT,
    CHAT_ACTION_CHANNELS.AVATAR_PREVIEW_RESULT,
  ]);
  const resolveVisibleChat = (windows) => {
    const fc = windows.fullChat;
    return (fc && !fc.isDestroyed() && fc.isVisible()) ? fc : windows.chat;
  };

  // 根据路由表批量注册 handler
  for (const route of ROUTES) {
    ipcMain.on(route.channel, (event, data) => {
      const windows = getWindowsSnapshot();
      const routedData = (
        route.channel === CHAT_ACTION_CHANNELS.AVATAR_TOOL_STATE
        || route.channel === CHAT_ACTION_CHANNELS.AVATAR_TOOL_POINTER
      )
        ? enrichAvatarToolStatePayload(event, data)
        : data;
      for (const target of route.targets) {
        if (target === 'chat') {
          if (CHAT_REQUEST_RESPONSE_CHANNELS.has(route.channel)) {
            // 请求态响应：只发当前可见的聊天窗口（发起者）。
            safeSend(resolveVisibleChat(windows), route.channel, routedData);
          } else {
            // 广播态（WS RAW_MESSAGE/READY/CONNECTING/CLOSED、transcript/speech/status/
            // chat_message、voice-config 切换等）：compact 与 full 两个聊天窗口都发，
            // 隐藏的那个也借此保持同步不 stale。fullChat 为 null 时 safeSend 自动 no-op。
            safeSend(windows.chat, route.channel, routedData);
            safeSend(windows.fullChat, route.channel, routedData);
          }
        } else {
          safeSend(windows[target], route.channel, routedData);
        }
      }
    });
  }

  // 设置同步（双向，sender-aware）：转发给除发送者以外的所有窗口
  ipcMain.on(SETTINGS_CHANNELS.SYNC, (event, data) => {
    const windows = getWindowsSnapshot();
    const senderId = event.sender.id;
    for (const win of Object.values(windows)) {
      if (win && !win.isDestroyed() && win.webContents.id !== senderId) {
        safeSend(win, SETTINGS_CHANNELS.SYNC, data);
      }
    }
  });

  // 跨窗口音乐播放器协调（sender-aware relay）：把任一聊天/Pet 窗口发来的协调
  // 事件转发给除发送者以外的所有窗口。compact / full 处于隔离 partition，
  // BroadcastChannel 不跨 partition，必须经主进程中转才能保证「一次只有一个
  // 播放器 owner」。payload 对主进程透明，语义全在渲染进程 music_ui.js 里解释。
  ipcMain.on(MUSIC_CHANNELS.BRIDGE, (event, data) => {
    const windows = getWindowsSnapshot();
    const senderId = event.sender.id;
    for (const win of Object.values(windows)) {
      if (win && !win.isDestroyed() && win.webContents.id !== senderId) {
        safeSend(win, MUSIC_CHANNELS.BRIDGE, data);
      }
    }
  });

  _log('[IPCRouter] IPC 消息路由已就绪 (' + ROUTES.length + ' 条路由 + settings-sync + music-bridge)');
}

/**
 * 发送全局广播（如主题切换、屏幕变化）
 */
function broadcastGlobal(channel, data) {
  broadcastToAll(channel, data);
}

module.exports = {
  setupIPCRouter,
  safeSend,
  broadcastGlobal,
  ROUTES,
};
