/**
 * ipc-channels.js
 * IPC 通道常量 —— 单一来源，所有文件统一 require 此模块
 */

// Pet → 其他窗口（WebSocket 消息分发）
const WS_CHANNELS = {
  TRANSCRIPT: 'neko:ws-transcript',
  SPEECH: 'neko:ws-speech',
  STATUS: 'neko:ws-status',
  AGENT_UPDATE: 'neko:ws-agent-update',
  CHAT_MESSAGE: 'neko:ws-chat-message',
};

// Chat → Pet（用户输入转发到 WebSocket）
const CHAT_CHANNELS = {
  SEND_TEXT: 'neko:chat-send-text',
  SEND_AUDIO: 'neko:chat-send-audio',
  START_SESSION: 'neko:chat-start-session',
  END_SESSION: 'neko:chat-end-session',
  SCREENSHOT: 'neko:chat-screenshot',
  REQUEST_SCREENSHOT: 'neko:chat-request-screenshot',
  SCREENSHOT_RESULT: 'neko:chat-screenshot-result',
};

// Chat → Pet（功能触发）
const CHAT_ACTION_CHANNELS = {
  AVATAR_PREVIEW: 'neko:chat-avatar-preview',
  AVATAR_PREVIEW_RESULT: 'neko:chat-avatar-preview-result',
  JUKEBOX_TOGGLE: 'neko:chat-jukebox-toggle',
  CONFIG_REQUEST: 'neko:chat-config-request',
  CONFIG_RESULT: 'neko:chat-config-result',
  AVATAR_TOOL_STATE: 'neko:chat-avatar-tool-state',
  AVATAR_TOOL_POINTER: 'neko:chat-avatar-tool-pointer',
  VOICE_CONFIG_SWITCHING: 'neko:voice-config-switching',
  GOODBYE_CHAT_COMPOSER_HIDDEN: 'neko:goodbye-chat-composer-hidden',
};

// compact 悬浮最小化球（#1595 之前模型旁的常驻悬浮入口）已停用：SHOW/HIDE/RAISE 仍保留
// 给旧代码做 no-op 兜底，但 buildDesktopCompactBallScreenRect 恒返回 null，不会主动发 SHOW。
//
// minimized 态下 Win32「毛线球折叠为独立窗口」走 COLLAPSE_TAKEOVER：
//   preload-chat-react.js 的 collapseNativeForReactMinimized 末尾派 COLLAPSE_TAKEOVER →
//   主进程同步 showCompactChatBallWindow(bounds) + dimReactChatForMinimize()。
// 外部球点击的回路仍走 CLICK：主进程转发给 reactChat preload 触发 doExpand，
// preload 完成定位后发 RESTORE_COMPLETE，主进程再恢复 opacity / ack 球窗口。
// Linux 不走 external ball takeover：setOpacity() 是 no-op，chat BrowserWindow 自身保留
// 为 88x88 折叠球，拖动/点击直接使用当前窗口 bounds。
const COMPACT_CHAT_BALL_CHANNELS = {
  SHOW: 'neko:compact-chat-ball-show',
  HIDE: 'neko:compact-chat-ball-hide',
  CLICK: 'neko:compact-chat-ball-click',
  REQUEST_COMPANION: 'neko:compact-chat-ball-request-companion',
  // 仅把已显示的独立缩小球重新 moveTop 到对话框之上（不改 bounds / 不抢焦）。
  // 与 SHOW 分开：SHOW 的位置去重可保留，但 raise 不应被去重挡掉。
  RAISE: 'neko:compact-chat-ball-raise',
  // Win32「毛线球折叠为独立窗口」专用通道。preload-chat-react.js → main：
  //   payload = { bounds: { x, y, width, height } }
  // main 收到后原子地：(1) showCompactChatBallWindow 在 bounds 处出现，
  // (2) dimReactChatForMinimize 透明化对话框窗口。两个 BrowserWindow 切换。
  COLLAPSE_TAKEOVER: 'neko:compact-chat-ball-collapse-takeover',
  // 球被拖动时由 preload-compact-chat-ball.js 派发。main 同时移动球窗口与
  // Win32/mac opacity carrier reactChatWindow，让下次 doExpand 的 W.expand 左下角对齐到球
  // 当前位置（不依赖球初始位置）。payload = { x, y }（屏幕坐标，球左上角）
  DRAG_MOVE: 'neko:compact-chat-ball-drag-move',
  // 球拖动结束（真实拖动的 pointerup）由 preload-compact-chat-ball.js 派发。
  // main 把球窗口与同步的 reactChatWindow 夹回光标所在屏幕的工作区内，
  // 避免球被甩出屏幕外、唯一的恢复入口够不着。
  DRAG_END: 'neko:compact-chat-ball-drag-end',
  // collapseNativeForReactMinimized 入口立刻派发，让 main 给 chatWin setOpacity(0)
  // —— 在 W.collapse 之前让 chatWin 整窗透明，避免用户看到 chatWin 从展开位置/尺寸
  // 跳到球目标位置/88x88 的物理位移。球窗口在 COLLAPSE_TAKEOVER 时出现替代。
  PRE_COLLAPSE_DIM: 'neko:compact-chat-ball-pre-collapse-dim',
  // 毛线球恢复揭示完成时派发：preload 在 chatWin 隐性（opacity=0）状态下用 stored
  // surface 把对话条定位到球位置后，发此通道让 main restore chatWin opacity 揭示对话框。
  // 也用于折叠中止时回滚 PRE_COLLAPSE_DIM 的透明态（避免对话框「隐身锁死」）。
  // 独立球的 hide 不在此处，由球弹完 bounce 动画后自行发 HIDE，与揭示解耦。
  RESTORE_COMPLETE: 'neko:compact-chat-ball-restore-complete',
  // main → 球：收到 RESTORE_COMPLETE（restore 真的发生了）后回给球的确认。
  // 球只有同时「弹完 bounce 动画」+「收到此 ACK」才自行 HIDE —— 若 CLICK 因 renderer
  // 正在 reload 被丢弃、restore 没跑，球收不到 ACK 就一直留着且可点，避免两头落空。
  RESTORE_ACK: 'neko:compact-chat-ball-restore-ack',
  // 兼容模式 F8 恢复时球 reload 的就绪信号：preload 在 appear 动画结束后通知主进程
  // 内容（含 background-image）已渲染就绪，主进程收到后清除 setShape 裁剪让球可见。
  APPEAR_DONE: 'neko:ball-restore-appear-done',
  SET_TEMPORARY_HIDDEN: 'neko:compact-chat-ball-set-temporary-hidden',
};

// AgentHUD → Pet（Agent 控制）
const AGENT_CHANNELS = {
  TOGGLE: 'neko:agent-toggle',
};

// 主进程 → 所有窗口（全局广播）
const GLOBAL_CHANNELS = {
  DISPLAY_CHANGED: 'neko:display-changed',
  THEME_CHANGED: 'neko:theme-changed',
};

// WebSocket 代理通道（Chat 窗口不建立真实连接，通过 Pet 中转）
const WS_PROXY_CHANNELS = {
  NEXT_SESSION_EPOCH: 'neko:ws-next-session-epoch',
  CONNECTING: 'neko:ws-connecting',
  READY: 'neko:ws-ready',
  RAW_MESSAGE: 'neko:ws-raw-message',
  RAW_SEND: 'neko:ws-raw-send',
  CLOSED: 'neko:ws-closed',
};

// 通用窗口控制（任意窗口均可使用，handler 通过 event.sender 识别来源窗口）
const WINDOW_CONTROL_CHANNELS = {
  GET_BOUNDS: 'neko:win-get-bounds',
  GET_WORKAREA: 'neko:win-get-workarea',
  SET_POSITION: 'neko:win-set-position',
  SET_SIZE: 'neko:win-set-size',
  SET_BOUNDS: 'neko:win-set-bounds',
  SET_RESIZABLE: 'neko:win-set-resizable',
  BRING_TO_FRONT: 'neko:win-bring-to-front',
  HIDE: 'neko:win-hide',
  COLLAPSE: 'neko:win-collapse',
  EXPAND: 'neko:win-expand',
  DRAG_START: 'neko:win-drag-start',
  DRAG_ANCHOR_MOVE: 'neko:win-drag-anchor-move',
  DRAG_STOP: 'neko:win-drag-stop',
  DRAG_STOP_AND_GET_BOUNDS: 'neko:win-drag-stop-and-get-bounds',
  DRAG_REVEAL_AFTER_RENDERER_READY: 'neko:win-drag-reveal-after-renderer-ready',
  RESIZE_START: 'neko:win-resize-start',
  RESIZE_MOVE: 'neko:win-resize-move',
  RESIZE_STOP: 'neko:win-resize-stop',
};

const AUTOSTART_CHANNELS = {
  GET_STATUS: 'neko:autostart:get-status',
  ENABLE: 'neko:autostart:enable',
  DISABLE: 'neko:autostart:disable',
  CHANGED: 'neko:autostart:changed',
};

// Toast 通知（主进程 → Toast 窗口）
const TOAST_CHANNELS = {
  STATUS: 'neko:toast-status',
  VOICE_PREPARING: 'neko:toast-voice-preparing',
  VOICE_HIDE_PREPARING: 'neko:toast-voice-hide-preparing',
  VOICE_READY: 'neko:toast-voice-ready',
  PROMINENT: 'neko:toast-prominent',
};

// 主进程（托盘）→ Chat 窗口：切换聊天 surface 形态（full 完整窗口 / compact 悬浮条）。
// payload = 'full' | 'compact'。preload-chat-react.js 收到后调 setReactChatSurfaceMode(mode)，
// 由 host shim 让 React 切到对应 surface。compact 默认值已由 host 的 getDefaultChatSurfaceMode
// 处理（Electron 默认 compact），此通道只负责用户主动切换。
const CHAT_SURFACE_CHANNELS = {
  SET_MODE: 'neko:chat-set-surface-mode',
  RESTORE_COMPACT_SURFACE: 'neko:chat-restore-compact-surface',
};

// 设置同步（Pet ↔ Chat，开关变量以 Pet 侧为准）
const SETTINGS_CHANNELS = {
  SYNC: 'neko:settings-sync',           // Pet → Chat（设置变更广播）
  REQUEST: 'neko:settings-request',      // Chat → Pet（请求当前设置快照）
};

// Pet 渲染管线信号（主进程 → Pet 渲染进程）
// 用户正在拖拽/调整 Pet 窗口大小时，Pet 内部的 Live2D / VRM / MMD 渲染循环
// 应暂停或降频，将渲染时间片让给 DWM 合成，避免拖拽/resize 卡顿。
const PET_CHANNELS = {
  INTERACTION_STATE: 'neko:pet-interaction-state', // { interacting: boolean, kind: 'drag'|'resize' }
  AVATAR_TOOL_CURSOR_STATE: 'neko:pet-avatar-tool-cursor-state',
  AVATAR_BOUNDS_SYNC: 'neko:pet-avatar-bounds-sync',
  AVATAR_BOUNDS_SYNC_SUBSCRIPTION: 'neko:pet-avatar-bounds-sync-subscription',
  IDLE_CHAT_MINIMIZED_STATE: 'neko:pet-idle-chat-minimized-state',
  IDLE_CAT_COMPANION_LAYER: 'neko:pet-idle-cat-companion-layer',
  REQUEST_IDLE_RETURN_COMPANION: 'neko:pet-request-idle-return-companion',
};

const TUTORIAL_OVERLAY_CHANNELS = {
  BEGIN: 'neko:tutorial-overlay:begin',
  UPDATE: 'neko:tutorial-overlay:update',
  CLEAR: 'neko:tutorial-overlay:clear',
  LOADING_BEGIN: 'neko:tutorial-loading-overlay:begin',
  LOADING_UPDATE: 'neko:tutorial-loading-overlay:update',
  LOADING_CLEAR: 'neko:tutorial-loading-overlay:clear',
  GET_WINDOW_METRICS_SYNC: 'neko:tutorial-overlay:get-window-metrics-sync',
  RELAY_TO_CHAT: 'neko:tutorial-overlay:relay-to-chat',
  RELAY_TO_PET: 'neko:tutorial-overlay:relay-to-pet',
  RELAY_TO_PAGE: 'neko:tutorial-overlay:relay-to-page',
};

// Subtitle 窗口设置（Subtitle ↔ Pet，翻译设置变更与状态同步）
const SUBTITLE_CHANNELS = {
  SETTINGS_CHANGE: 'neko:subtitle-settings-change',   // Subtitle → Pet：设置变更
  STATE_SYNC: 'neko:subtitle-state-sync',              // Pet → Subtitle：状态同步
  OPEN_SETTINGS: 'neko:subtitle-open-settings',        // Subtitle → Main：打开独立设置层
  CLOSE_SETTINGS: 'neko:subtitle-close-settings',      // Subtitle → Main：关闭独立设置层
  SETTINGS_WINDOW_UPDATE: 'neko:subtitle-settings-window-update', // Subtitle → Main：刷新独立设置层
};

// 跨窗口音乐播放器协调（compact ↔ full ↔ pet，sender-aware relay）。
// compact 与 full 聊天窗处于隔离的 Electron partition（persist:neko-full-chat），
// 浏览器 BroadcastChannel/localStorage 不跨 partition，无法保证「一次只有一个
// 播放器 owner + 当前可见聊天窗镜像显示」。沿用 goodbye composer 同样的
// 「partition 隔离 → 改走主进程 IPC」做法（见 GOODBYE_CHAT_COMPOSER_HIDDEN）：
// 主进程把任一窗口发来的协调事件转发给除发送者外的所有窗口。payload 对主进程
// 透明，语义（coord / bar_state / bar_ctrl / surface_state 等）全在渲染进程的
// music_ui.js 里解释。
const MUSIC_CHANNELS = {
  BRIDGE: 'neko:music-player-bridge',
};

// Jukebox 独立窗口（Jukebox ↔ Pet，VMD 动画控制通过 Pet 中转）
const JUKEBOX_CHANNELS = {
  TOGGLE: 'neko:jukebox-toggle',           // 任意窗口 → 主进程：打开/切换 Jukebox 窗口
  VMD_PLAY: 'neko:jukebox-vmd-play',       // Jukebox → Pet：播放 VMD 动画
  VMD_STOP: 'neko:jukebox-vmd-stop',       // Jukebox → Pet：停止 VMD 动画
  VMD_PAUSE: 'neko:jukebox-vmd-pause',     // Jukebox → Pet：暂停 VMD 动画
  VMD_RESUME: 'neko:jukebox-vmd-resume',   // Jukebox → Pet：恢复 VMD 动画
  CLOSED: 'neko:jukebox-closed',           // 主进程 → Pet/Chat：Jukebox 窗口已关闭
};

// F8 一键隐藏/恢复：兼容模式下 CSS 淡入淡出动画通道（主进程 ↔ 渲染进程）
// 时序拆分流：主进程不碰 setOpacity（触发 DWM bug），改由渲染进程 CSS transition
// 负责视觉效果，动画结束后主进程再做物理隔离（setShape 1x1 / 清除裁剪）。
const F8_FADE_CHANNELS = {
  // 主进程 → 渲染进程：开始淡出（CSS opacity 1→0），动画结束后回复 FADE_OUT_DONE
  FADE_OUT: 'neko:f8-fade-out',
  // 渲染进程 → 主进程：淡出动画结束，可以执行 setShape 物理隔离
  FADE_OUT_DONE: 'neko:f8-fade-out-done',
  // 主进程 → 渲染进程：开始淡入（CSS opacity 0→1），窗口已 setShape([]) 恢复尺寸
  FADE_IN: 'neko:f8-fade-in',
};

module.exports = {
  WS_CHANNELS,
  CHAT_CHANNELS,
  CHAT_ACTION_CHANNELS,
  COMPACT_CHAT_BALL_CHANNELS,
  AGENT_CHANNELS,
  GLOBAL_CHANNELS,
  WS_PROXY_CHANNELS,
  WINDOW_CONTROL_CHANNELS,
  AUTOSTART_CHANNELS,
  TOAST_CHANNELS,
  CHAT_SURFACE_CHANNELS,
  SETTINGS_CHANNELS,
  PET_CHANNELS,
  TUTORIAL_OVERLAY_CHANNELS,
  JUKEBOX_CHANNELS,
  SUBTITLE_CHANNELS,
  F8_FADE_CHANNELS,
  MUSIC_CHANNELS,
};
