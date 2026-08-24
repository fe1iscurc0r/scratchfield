/**
 * preload-common.js
 * 共享 preload 工具函数 —— 各窗口 preload 按需调用
 *
 * 解决问题：暗色模式、electronShell、toast 覆盖在多个 preload 中重复且实现不一致
 */

const { ipcRenderer, contextBridge } = require('electron');
const { AUTOSTART_CHANNELS, CHAT_ACTION_CHANNELS, TUTORIAL_OVERLAY_CHANNELS, MUSIC_CHANNELS } = require('./ipc-channels');
const AUTOSTART_STATUS_CHANGED_EVENT_NAME = 'neko:autostart-status-changed';
let autostartStatusListenerInstalled = false;

function installWindowFunctionBridge(name, bridge) {
  if (typeof bridge !== 'function') return null;
  try {
    Object.defineProperty(bridge, '__nekoDesktopBridge', {
      value: true,
      enumerable: false,
      configurable: false,
    });
  } catch (_) { /* ignore */ }

  try {
    Object.defineProperty(window, name, {
      configurable: true,
      enumerable: true,
      get: function() {
        return bridge;
      },
      set: function(value) {
        // N.E.K.O web scripts still assign the same legacy window functions.
        // In the desktop shell those names are transport bridges, so late page
        // writes are intentionally absorbed instead of replacing the IPC path.
        if (value && value.__nekoDesktopBridge) return;
      },
    });
  } catch (e) {
    // 兜底：defineProperty 仅在 name 已是 window 上的不可配置属性时才会抛错——
    // 这几个 toast 函数名都是网页用 window.x = fn 普通赋值创建的（可配置可写），
    // 实际不可达。万一触发，降级为普通赋值会丢失防覆盖保护，故不静默，打一条 warn。
    console.warn('[preload-common] installWindowFunctionBridge defineProperty 失败，降级为普通赋值（防覆盖保护失效）:', name, e);
    window[name] = bridge;
  }
  return bridge;
}

/**
 * 安装暗色模式支持：window.nekoDarkMode API + toggle-dark-mode 监听
 */
function setupDarkMode() {
  const applyDarkModeToDocument = (isDark) => {
    try {
      if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
        document.documentElement.classList.remove('dark');
      }
      localStorage.setItem('neko-dark-mode', isDark ? 'true' : 'false');
      window.dispatchEvent(new CustomEvent('neko-theme-changed', { detail: { darkMode: isDark } }));
    } catch (e) { /* ignore */ }
  };

  const bridge = {
    get: () => ipcRenderer.invoke('get-dark-mode'),
    set: (enabled) => ipcRenderer.invoke('set-dark-mode', enabled),
    toggle: async () => {
      const current = await ipcRenderer.invoke('get-dark-mode');
      return ipcRenderer.invoke('set-dark-mode', !current);
    },
  };

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoDarkMode', bridge);
  } else {
    window.nekoDarkMode = bridge;
  }

  try {
    Promise.resolve(bridge.get())
      .then((isDark) => {
        if (typeof isDark === 'boolean') {
          applyDarkModeToDocument(isDark);
        }
      })
      .catch(() => {});
  } catch (e) { /* ignore */ }

  ipcRenderer.on('toggle-dark-mode', (event, isDark) => {
    applyDarkModeToDocument(isDark);
  });
}

/**
 * 安装外部链接 API：window.electronShell.openExternal
 */
function setupElectronShell() {
  const bridge = {
    openExternal: (url) => ipcRenderer.invoke('open-external-url', url),
  };

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('electronShell', bridge);
    return bridge;
  }

  window.electronShell = bridge;
  return bridge;
}

/**
 * 安装通用宿主能力桥接。
 * 业务校验仍由 N.E.K.O 后端完成；这里仅负责系统目录选择、打开路径和关闭当前窗口。
 */
function setupHostCapabilityBridge() {
  const existingBridge = !process.contextIsolated && window.nekoHost && typeof window.nekoHost === 'object'
    ? window.nekoHost
    : null;
  const bridge = existingBridge
    ? window.nekoHost
    : {};

  bridge.pickDirectory = (options = {}) => {
    const startPath = typeof options === 'string' ? options : options.startPath;
    const title = typeof options === 'object' && options ? options.title : '';
    return ipcRenderer.invoke('neko:host:pick-directory', {
      startPath: String(startPath || ''),
      title: String(title || ''),
    });
  };

  bridge.openPath = (options = {}) => {
    const targetPath = typeof options === 'string' ? options : options.path;
    return ipcRenderer.invoke('neko:host:open-path', {
      path: String(targetPath || ''),
    });
  };

  bridge.closeWindow = () => ipcRenderer.invoke('neko:host:close-window');

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoHost', bridge);
    return bridge;
  }

  window.nekoHost = bridge;
  return bridge;
}

function setupTutorialOverlayBridge() {
  const existingBridge = !process.contextIsolated && window.nekoTutorialOverlay && typeof window.nekoTutorialOverlay === 'object'
    ? window.nekoTutorialOverlay
    : null;
  const bridge = existingBridge || {};

  bridge.isAvailable = () => true;
  bridge.getCapabilities = () => ({
    petalTransition: true,
  });
  bridge.begin = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.BEGIN, payload);
  bridge.update = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.UPDATE, payload);
  bridge.clear = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.CLEAR, payload);
  bridge.relayToChat = (payload = {}) => ipcRenderer.send(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_CHAT, payload);
  bridge.relayToPet = (payload = {}) => ipcRenderer.send(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_PET, payload);
  bridge.getWindowMetricsSync = () => {
    try {
      return ipcRenderer.sendSync(TUTORIAL_OVERLAY_CHANNELS.GET_WINDOW_METRICS_SYNC);
    } catch (_) {
      return null;
    }
  };

  ipcRenderer.on(TUTORIAL_OVERLAY_CHANNELS.RELAY_TO_PAGE, (_event, payload) => {
    try {
      window.dispatchEvent(new CustomEvent('neko:tutorial-overlay-relay', { detail: payload || {} }));
    } catch (_) {}
    try {
      window.postMessage({ __nekoTutorialOverlayRelay: true, payload: payload || {} }, '*');
    } catch (_) {}
  });

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoTutorialOverlay', bridge);
    return bridge;
  }

  window.nekoTutorialOverlay = bridge;
  return bridge;
}

function setupTutorialLoadingOverlayBridge() {
  const existingBridge = !process.contextIsolated && window.nekoTutorialLoadingOverlay && typeof window.nekoTutorialLoadingOverlay === 'object'
    ? window.nekoTutorialLoadingOverlay
    : null;
  const bridge = existingBridge || {};

  bridge.isAvailable = () => true;
  bridge.begin = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.LOADING_BEGIN, payload);
  bridge.update = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.LOADING_UPDATE, payload);
  bridge.clear = (payload = {}) => ipcRenderer.invoke(TUTORIAL_OVERLAY_CHANNELS.LOADING_CLEAR, payload);

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoTutorialLoadingOverlay', bridge);
    return bridge;
  }

  window.nekoTutorialLoadingOverlay = bridge;
  return bridge;
}

/**
 * 安装音色切换状态桥接。
 * BrowserWindow 拆分后 BroadcastChannel 仍可用，但 IPC 兜底能避免窗口隔离导致 Chat 漏掉准备态。
 */
function setupVoiceConfigSwitchingBridge() {
  const channel = CHAT_ACTION_CHANNELS.VOICE_CONFIG_SWITCHING;
  const bridge = {
    send: (payload = {}) => {
      const data = Object.assign({}, payload, {
        action: payload.action || 'voice_config_switching',
        type: payload.type || 'voice_config_switching',
        timestamp: payload.timestamp || Date.now(),
      });
      ipcRenderer.send(channel, data);
    },
  };

  ipcRenderer.on(channel, (_event, payload) => {
    try {
      window.dispatchEvent(new CustomEvent('neko:electron-voice-config-switching', {
        detail: payload || {},
      }));
    } catch (_) {
      // 桥接事件失败时保留 BroadcastChannel 路径
    }
  });

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoElectronVoiceConfigSwitching', bridge);
    return bridge;
  }

  window.nekoElectronVoiceConfigSwitching = bridge;
  return bridge;
}

/**
 * Install a desktop IPC fallback for goodbye-mode composer visibility. Full chat
 * uses its own Electron partition, so web BroadcastChannel messages are not a
 * reliable cross-window transport there.
 */
function setupGoodbyeChatComposerHiddenBridge() {
  const channel = CHAT_ACTION_CHANNELS.GOODBYE_CHAT_COMPOSER_HIDDEN;
  const bridge = {
    send: (payload = {}) => {
      const hidden = payload.hidden === undefined ? undefined : !!payload.hidden;
      const data = Object.assign({}, payload, {
        action: payload.action || 'goodbye_chat_composer_hidden',
        type: payload.type || payload.action || 'goodbye_chat_composer_hidden',
        timestamp: payload.timestamp || Date.now(),
      });
      if (hidden !== undefined) {
        data.hidden = hidden;
      }
      ipcRenderer.send(channel, data);
    },
  };

  ipcRenderer.on(channel, (_event, payload) => {
    try {
      window.dispatchEvent(new CustomEvent('neko:electron-goodbye-chat-composer-hidden', {
        detail: payload || {},
      }));
    } catch (_) {
      // Keep the BroadcastChannel path as a best-effort fallback.
    }
  });

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoElectronGoodbyeChatComposerHidden', bridge);
    return bridge;
  }

  window.nekoElectronGoodbyeChatComposerHidden = bridge;
  return bridge;
}

/**
 * Install a desktop IPC transport for cross-window music player coordination.
 * Compact and full chat run in isolated Electron partitions, so web
 * BroadcastChannel cannot keep a single visible player / single audio owner in
 * sync across them. The main process relays each event to every other window
 * (sender-aware). The payload is opaque here — music_ui.js owns the protocol.
 */
function setupMusicPlayerBridge() {
  const channel = MUSIC_CHANNELS.BRIDGE;
  const bridge = {
    // 与 setupGoodbyeChatComposerHiddenBridge / setupVoiceConfigSwitchingBridge
    // 一致：payload 都是可克隆的纯数据，send 不做防御包装。IPC 与 BroadcastChannel
    // 的取舍在渲染进程 music_ui.js 决定，只在本桥存在时才路由到这里。
    send: (message = {}) => {
      ipcRenderer.send(channel, message);
    },
  };

  ipcRenderer.on(channel, (_event, payload) => {
    try {
      window.dispatchEvent(new CustomEvent('neko:electron-music-bridge', {
        detail: payload ?? {},
      }));
    } catch (_) {
      // Ignore dispatch failures in non-browser contexts.
    }
  });

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoElectronMusicBridge', bridge);
    return bridge;
  }

  window.nekoElectronMusicBridge = bridge;
  return bridge;
}

function createAutostartBridge() {
  return {
    getStatus: () => ipcRenderer.invoke(AUTOSTART_CHANNELS.GET_STATUS),
    enable: () => ipcRenderer.invoke(AUTOSTART_CHANNELS.ENABLE),
    disable: () => ipcRenderer.invoke(AUTOSTART_CHANNELS.DISABLE),
  };
}

/**
 * 安装自启动桥接：window.nekoAutostart
 * 统一对接主进程 getStatus/enable/disable，供前端 provider 直接复用。
 */
function setupAutostartBridge() {
  const bridge = createAutostartBridge();

  if (!autostartStatusListenerInstalled) {
    autostartStatusListenerInstalled = true;
    ipcRenderer.on(AUTOSTART_CHANNELS.CHANGED, (event, status) => {
      try {
        window.dispatchEvent(new CustomEvent(AUTOSTART_STATUS_CHANGED_EVENT_NAME, {
          detail: status,
        }));
      } catch (_) {
        // Ignore dispatch failures in non-browser contexts.
      }
    });
  }

  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoAutostart', bridge);
    return bridge;
  }

  if (
    window.nekoAutostart
    && typeof window.nekoAutostart.getStatus === 'function'
    && typeof window.nekoAutostart.enable === 'function'
    && typeof window.nekoAutostart.disable === 'function'
  ) {
    return window.nekoAutostart;
  }

  window.nekoAutostart = bridge;
  return bridge;
}

/**
 * 安装 Toast 覆盖：将 showStatusToast 重定向到主进程全局 Toast 窗口
 */
function setupToastOverride() {
  installWindowFunctionBridge('showStatusToast', function(message, duration, options) {
    var important = options && options.important;
    var i18nKey = options && options.i18nKey;
    ipcRenderer.send('neko:show-toast', {
      message: String(message),
      duration: duration || 4000,
      important: !!important,
      i18nKey: i18nKey || '',
    });
  });
}

/**
 * 卫星窗口禁用 Voice Preparing Toast（只应在 Pet 主窗口显示）
 */
function suppressVoiceToast() {
  installWindowFunctionBridge('showVoicePreparingToast', function() {});
  installWindowFunctionBridge('hideVoicePreparingToast', function() {});
}

/**
 * 拦截 Voice Toast，重定向到独立 Toast 窗口
 * 和 showStatusToast 一样需要通过 IPC 转发到独立 toast 窗口，
 * 避免受 Pet 窗口样式/层级影响。
 */
function setupVoiceToastOverride() {
  const { TOAST_CHANNELS } = require('./ipc-channels');

  function installVoiceToastBridge() {
    installWindowFunctionBridge('showVoicePreparingToast', function(message) {
      ipcRenderer.send(TOAST_CHANNELS.VOICE_PREPARING, { message: String(message || '') });
    });
    installWindowFunctionBridge('hideVoicePreparingToast', function() {
      ipcRenderer.send(TOAST_CHANNELS.VOICE_HIDE_PREPARING);
    });
    installWindowFunctionBridge('showReadyToSpeakToast', function() {
      ipcRenderer.send(TOAST_CHANNELS.VOICE_READY, { message: '' });
    });
  }

  function refreshVoiceToastBridge() {
    [0, 100, 500, 1500, 3000].forEach((delay) => {
      setTimeout(installVoiceToastBridge, delay);
    });
  }

  installVoiceToastBridge();
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', refreshVoiceToastBridge, { once: true });
  } else {
    refreshVoiceToastBridge();
  }
  window.addEventListener('load', refreshVoiceToastBridge, { once: true });
}

/**
 * 注入 -webkit-app-region: drag CSS，让 OS 原生处理窗口拖拽
 * 零 IPC、零 JS 事件、零尺寸漂移
 * @param {string[]} dragSelectors  需要可拖拽的选择器
 * @param {string[]} noDragSelectors 排除拖拽的交互元素选择器
 */
function setupNativeDrag(dragSelectors, noDragSelectors) {
  function inject() {
    const dragCSS = dragSelectors.map(s => `${s} { -webkit-app-region: drag; }`).join('\n');
    const noDragCSS = noDragSelectors.map(s => `${s} { -webkit-app-region: no-drag; }`).join('\n');
    const style = document.createElement('style');
    style.setAttribute('data-neko-native-drag', 'true');
    style.textContent = dragCSS + '\n' + noDragCSS;
    (document.head || document.documentElement).appendChild(style);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
}

/**
 * 安装双向设置同步（Pet ↔ Chat）
 *
 * 防回路设计：
 *   - 路由层 sender-aware：SYNC 不回传给发送者
 *   - _suppressed 标志：接收期间若副作用触发 saveNEKOSettings，hook 不再广播
 *   - 接收方只写内存（appState + window.*），不写 localStorage
 *     → 同源 localStorage 已由发送方的 saveNEKOSettings 写入，无需重复
 *
 * @param {{ role: 'pet' | 'chat' }} options
 *   - pet: 响应 REQUEST（初始同步）
 *   - chat: 发起 REQUEST（页面加载后拉一次快照）
 */
function setupSettingsSync(options) {
  var role = (options && options.role) || 'chat';
  var TAG = '[Settings-Sync/' + role + ']';

  var { SETTINGS_CHANNELS } = require('./ipc-channels');

  // 同步的 key（不含 renderQuality / targetFrameRate，chat 独占）
  var SYNCED_KEYS = [
    'proactiveChatEnabled', 'proactiveVisionEnabled',
    'proactiveVisionChatEnabled', 'proactiveNewsChatEnabled',
    'proactiveVideoChatEnabled', 'proactivePersonalChatEnabled',
    'proactiveMusicEnabled', 'proactiveMemeEnabled', 'proactiveMiniGameInviteEnabled',
    'proactiveChatInterval', 'proactiveVisionInterval',
    'mergeMessagesEnabled', 'focusModeEnabled', 'textGuardMaxLength',
    'avatarReactionBubbleEnabled', 'subtitleEnabled', 'userLanguage',
    'speakerVolume',
  ];

  // 不在 app-state.js defineProperty 绑定中、需要额外写 window.* 的 key
  var EXTRA_WINDOW_KEYS = ['textGuardMaxLength', 'subtitleEnabled', 'userLanguage', 'speakerVolume'];

  // 全局抑制标志：为 true 时 hook 不广播（防止接收期间副作用引发回路）
  var _suppressed = false;

  // ==================== 发送端 ====================

  function collectSnapshot() {
    var S = window.appState;
    if (!S) return null;
    var snap = {};
    for (var i = 0; i < SYNCED_KEYS.length; i++) {
      var k = SYNCED_KEYS[i];
      snap[k] = (k in S) ? S[k] : window[k];
    }
    return snap;
  }

  function broadcastSettings() {
    var snap = collectSnapshot();
    if (snap) ipcRenderer.send(SETTINGS_CHANNELS.SYNC, snap);
  }

  // 页面 JS 加载后 hook saveNEKOSettings + appSettings.saveSettings
  document.addEventListener('DOMContentLoaded', function() {
    var hookTimer = setInterval(function() {
      if (typeof window.saveNEKOSettings !== 'function') return;
      clearInterval(hookTimer);

      var _original = window.saveNEKOSettings;

      function hookedSave() {
        _original.apply(this, arguments);
        if (!_suppressed) {
          broadcastSettings();
        }
      }

      window.saveNEKOSettings = hookedSave;
      if (window.appSettings && window.appSettings.saveSettings === _original) {
        window.appSettings.saveSettings = hookedSave;
      }

      console.log(TAG, 'saveNEKOSettings 已 hook');
    }, 200);
    setTimeout(function() { clearInterval(hookTimer); }, 5000);
  });

  // ==================== 接收端 ====================
  // 只写内存，不写 localStorage（发送方的 saveNEKOSettings 已写入同源 localStorage）

  ipcRenderer.on(SETTINGS_CHANNELS.SYNC, function(_event, snapshot) {
    var S = window.appState;
    if (!S || !snapshot) return;

    // 抑制：接收期间若任何副作用触发 hookedSave，不再广播
    _suppressed = true;

    var changed = [];
    var keys = Object.keys(snapshot);
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var v = snapshot[k];
      if (S[k] !== v) { S[k] = v; changed.push(k); }
    }

    if (changed.length === 0) { _suppressed = false; return; }

    // 同步不在 defineProperty 绑定中的 window.* 变量
    for (var j = 0; j < EXTRA_WINDOW_KEYS.length; j++) {
      var ek = EXTRA_WINDOW_KEYS[j];
      if (ek in snapshot) window[ek] = snapshot[ek];
    }

    // --- 副作用（只更新运行时，不触发持久化）---

    // 扬声器音量 → GainNode
    if ('speakerVolume' in snapshot && S.speakerGainNode) {
      try {
        S.speakerGainNode.gain.setTargetAtTime(
          snapshot.speakerVolume / 100,
          S.speakerGainNode.context.currentTime, 0.05);
      } catch (_) {}
    }

    // 字幕 → subtitle.js 内部闭包
    if (window.subtitleBridge) {
      if ('subtitleEnabled' in snapshot && typeof window.subtitleBridge.setSubtitleEnabled === 'function') {
        window.subtitleBridge.setSubtitleEnabled(snapshot.subtitleEnabled);
      }
      if ('userLanguage' in snapshot && typeof window.subtitleBridge.setUserLanguage === 'function') {
        window.subtitleBridge.setUserLanguage(snapshot.userLanguage);
      }
    }

    // 主动搭话调度器
    var proactiveChanged = ['proactiveChatEnabled', 'proactiveVisionEnabled',
      'proactiveVisionChatEnabled', 'proactiveNewsChatEnabled',
      'proactiveVideoChatEnabled', 'proactivePersonalChatEnabled',
      'proactiveMusicEnabled', 'proactiveMemeEnabled', 'proactiveMiniGameInviteEnabled'
    ].some(function(pk) { return changed.indexOf(pk) !== -1; });
    if (proactiveChanged && window.appProactive) {
      if (S.proactiveChatEnabled && window.appProactive.scheduleProactiveChat) {
        window.appProactive.scheduleProactiveChat();
      } else if (!S.proactiveChatEnabled && window.appProactive.stopProactiveChatSchedule) {
        window.appProactive.stopProactiveChatSchedule();
      }
    }

    _suppressed = false;
    console.log(TAG, '已同步', changed.length, '项:', changed.join(', '));
  });

  // ==================== 初始同步 ====================

  if (role === 'chat') {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(function() {
        ipcRenderer.send(SETTINGS_CHANNELS.REQUEST);
        console.log(TAG, '已请求初始设置快照');
      }, 1000);
    });
  } else {
    ipcRenderer.on(SETTINGS_CHANNELS.REQUEST, function() {
      setTimeout(function() {
        broadcastSettings();
        console.log(TAG, '响应 REQUEST，已发送快照');
      }, 0);
    });
  }
}

/**
 * 安装跨平台活动信号桥：window.nekoActivitySignal.read()
 *
 * Renderer 调 ``.read()`` 拿一份当前 OS 信号快照（前台窗口标题/进程名、
 * 系统 idle 秒数、CPU 30s 平均、GPU 利用率），用来 POST 到 N.E.K.O
 * 后端的 ``/api/activity_signal``（见 NEKO 仓库 issue #1023 / PR #1477）。
 *
 * 实际信号采样在 main 进程的 ``src/main/activity-signal-ipc.js`` 里，
 * 这里只做 IPC 桥。主进程缓存最近一次采样，所以 invoke 总是即时返回。
 *
 * 桥缺席时（旧 NEKO-PC、纯浏览器 dev 跑）renderer 那边
 * ``static/app-activity-signal.js`` 会 log 一次后退出，后端 tracker 回落
 * 到本地 collector（远端部署下进降级模式）—— 与 PR #1015 文档的
 * fallback 一致。
 */
function setupActivitySignalBridge() {
  const bridge = {
    read: () => ipcRenderer.invoke('neko:read-activity-signal'),
  };
  if (process.contextIsolated && contextBridge && typeof contextBridge.exposeInMainWorld === 'function') {
    contextBridge.exposeInMainWorld('nekoActivitySignal', bridge);
    return bridge;
  }
  window.nekoActivitySignal = bridge;
  return bridge;
}

function syncSubtitleToggleFromWindow(enabled) {
  var nextEnabled = !!enabled;
  if (window.subtitleBridge && typeof window.subtitleBridge.setSubtitleEnabled === 'function') {
    window.subtitleBridge.setSubtitleEnabled(nextEnabled);
    return;
  }
  if (window.nekoSubtitleShared && typeof window.nekoSubtitleShared.updateSettings === 'function') {
    window.nekoSubtitleShared.updateSettings({ subtitleEnabled: nextEnabled }, {
      source: 'subtitle-window-toggle'
    });
  } else {
    if (window.appState) window.appState.subtitleEnabled = nextEnabled;
    try { localStorage.setItem('subtitleEnabled', String(nextEnabled)); } catch (_) {}
  }
  window.dispatchEvent(new CustomEvent('react-chat-window:set-view-props', {
    detail: { viewProps: { translateEnabled: nextEnabled } }
  }));
}
module.exports = {
  setupDarkMode,
  setupElectronShell,
  setupHostCapabilityBridge,
  setupTutorialOverlayBridge,
  setupTutorialLoadingOverlayBridge,
  setupVoiceConfigSwitchingBridge,
  setupGoodbyeChatComposerHiddenBridge,
  setupMusicPlayerBridge,
  setupAutostartBridge,
  setupToastOverride,
  suppressVoiceToast,
  setupVoiceToastOverride,
  setupNativeDrag,
  setupSettingsSync,
  setupActivitySignalBridge,
  syncSubtitleToggleFromWindow,
};
