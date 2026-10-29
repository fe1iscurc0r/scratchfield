/**
 * electron-page-bridge.js
 * 隔离窗口（contextIsolation:true）的页面侧接线（WO-278 装配步 2）。
 *
 * 背景：preload 里的 `installWindowFunctionBridge` / `setupSettingsSync` 写的是
 * **preload 自己的 JS 世界**，隔离后页面读不到。preload 于是只暴露原语：
 *   window.nekoPageToastBridge      { showStatusToast }
 *   window.nekoPageVoiceToastBridge { showVoicePreparingToast, hideVoicePreparingToast, ... }
 *   window.nekoPageSettingsSync     { role, keys, extraWindowKeys, onSync, broadcast, request }
 * 本文件在页面世界把这些原语接回页面全局（toast）与业务对象（设置同步）。
 *
 * 未隔离窗口 / 浏览器直开：这些全局不存在，本文件直接返回，preload 仍走旧路径。
 */
(function (global) {
  'use strict';

  var toastBridge = global.nekoPageToastBridge;
  var voiceToastBridge = global.nekoPageVoiceToastBridge;
  var settingsSync = global.nekoPageSettingsSync;

  // ==================== B 组页面状态（P3）====================
  // 隔离臂：preload 写的是自己的世界，页面只能经 getter 每次现取 —— 状态变了立刻读到新值。
  // 共享臂：preload 直接写页面 window，这里再装 getter 会顶掉后续赋值，所以只在 isolated 装。
  var chatState = global.nekoChatState;
  if (chatState && chatState.isolated === true && typeof chatState.get === 'function') {
    [
      '__nekoDesktopCompactLayout',
      '__nekoDesktopAvatarBounds',
      '__nekoDesktopCompactBallScreenRect',
      '__nekoDesktopCompactExternalBall',
      '__nekoInjectedConfig',
    ].forEach(function (name) {
      try {
        Object.defineProperty(global, name, {
          configurable: true,
          enumerable: true,
          get: function () { return chatState.get(name); },
        });
      } catch (_) { /* 页面先把该属性改成不可配置时放弃 */ }
    });
  }

  if (!toastBridge && !voiceToastBridge && !settingsSync) return;

  // ==================== Toast ====================

  function absorbPageFunction(name, impl) {
    try {
      Object.defineProperty(global, name, {
        configurable: true,
        enumerable: true,
        get: function () {
          return impl;
        },
        // 页面脚本常在加载后再赋值一次同名函数；隔离窗里宿主转发才是唯一出口，
        // 迟到赋值一律吸收，避免把 IPC 路径顶掉。
        set: function () {},
      });
    } catch (_) { /* 页面先把该属性改成不可配置时放弃；next tick 会再试 */ }
  }

  function installToastBridges() {
    if (toastBridge && typeof toastBridge.showStatusToast === 'function') {
      absorbPageFunction('showStatusToast', toastBridge.showStatusToast);
    }
    if (voiceToastBridge) {
      ['showVoicePreparingToast', 'hideVoicePreparingToast', 'showReadyToSpeakToast'].forEach(function (name) {
        if (typeof voiceToastBridge[name] === 'function') {
          absorbPageFunction(name, voiceToastBridge[name]);
        }
      });
    }
  }

  if (toastBridge || voiceToastBridge) {
    installToastBridges();
    [0, 100, 500, 1500, 3000].forEach(function (delay) {
      setTimeout(installToastBridges, delay);
    });
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', installToastBridges, { once: true });
    }
  }

  // ==================== 设置同步 ====================

  if (!settingsSync) return;

  var SYNCED_KEYS = Array.isArray(settingsSync.keys) ? settingsSync.keys : [];
  var EXTRA_WINDOW_KEYS = Array.isArray(settingsSync.extraWindowKeys) ? settingsSync.extraWindowKeys : [];
  var suppressed = false;

  function collectSnapshot() {
    var S = global.appState;
    if (!S) return null;
    var snap = {};
    for (var i = 0; i < SYNCED_KEYS.length; i += 1) {
      var k = SYNCED_KEYS[i];
      snap[k] = (k in S) ? S[k] : global[k];
    }
    return snap;
  }

  function broadcastSettings() {
    var snap = collectSnapshot();
    if (snap) settingsSync.broadcast(snap);
  }

  function applySnapshot(snapshot) {
    var S = global.appState;
    if (!S || !snapshot) return;

    suppressed = true;

    var changed = [];
    var keys = Object.keys(snapshot);
    for (var i = 0; i < keys.length; i += 1) {
      var k = keys[i];
      var v = snapshot[k];
      if (S[k] !== v) {
        S[k] = v;
        changed.push(k);
      }
    }

    if (changed.length === 0) {
      suppressed = false;
      return;
    }

    for (var j = 0; j < EXTRA_WINDOW_KEYS.length; j += 1) {
      var ek = EXTRA_WINDOW_KEYS[j];
      if (ek in snapshot) global[ek] = snapshot[ek];
    }

    if ('speakerVolume' in snapshot && S.speakerGainNode) {
      try {
        S.speakerGainNode.gain.setTargetAtTime(
          snapshot.speakerVolume / 100,
          S.speakerGainNode.context.currentTime, 0.05);
      } catch (_) { /* ignore */ }
    }

    if (global.subtitleBridge) {
      if ('subtitleEnabled' in snapshot && typeof global.subtitleBridge.setSubtitleEnabled === 'function') {
        global.subtitleBridge.setSubtitleEnabled(snapshot.subtitleEnabled);
      }
      if ('userLanguage' in snapshot && typeof global.subtitleBridge.setUserLanguage === 'function') {
        global.subtitleBridge.setUserLanguage(snapshot.userLanguage);
      }
    }

    var proactiveChanged = ['proactiveChatEnabled', 'proactiveVisionEnabled',
      'proactiveVisionChatEnabled', 'proactiveNewsChatEnabled',
      'proactiveVideoChatEnabled', 'proactivePersonalChatEnabled',
      'proactiveMusicEnabled', 'proactiveMemeEnabled', 'proactiveMiniGameInviteEnabled'
    ].some(function (pk) { return changed.indexOf(pk) !== -1; });
    if (proactiveChanged && global.appProactive) {
      if (S.proactiveChatEnabled && global.appProactive.scheduleProactiveChat) {
        global.appProactive.scheduleProactiveChat();
      } else if (!S.proactiveChatEnabled && global.appProactive.stopProactiveChatSchedule) {
        global.appProactive.stopProactiveChatSchedule();
      }
    }

    suppressed = false;
    console.log('[Page-Settings-Sync] 已同步', changed.length, '项:', changed.join(', '));
  }

  settingsSync.onSync(applySnapshot);

  function hookSaveNekoSettings() {
    var hookTimer = setInterval(function () {
      if (typeof global.saveNEKOSettings !== 'function') return;
      clearInterval(hookTimer);

      var original = global.saveNEKOSettings;

      function hookedSave() {
        original.apply(this, arguments);
        if (!suppressed) broadcastSettings();
      }

      global.saveNEKOSettings = hookedSave;
      if (global.appSettings && global.appSettings.saveSettings === original) {
        global.appSettings.saveSettings = hookedSave;
      }
      console.log('[Page-Settings-Sync] saveNEKOSettings 已 hook');
    }, 200);
    setTimeout(function () { clearInterval(hookTimer); }, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hookSaveNekoSettings, { once: true });
  } else {
    hookSaveNekoSettings();
  }

  // chat 角色在页面加载后拉一次初始快照（与 preload 旧实现同一时机：DOMContentLoaded + 1s）
  if (settingsSync.role === 'chat') {
    var requestSnapshot = function () {
      setTimeout(function () {
        settingsSync.request();
        console.log('[Page-Settings-Sync] 已请求初始设置快照');
      }, 1000);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', requestSnapshot, { once: true });
    } else {
      requestSnapshot();
    }
  }
})(typeof window !== 'undefined' ? window : globalThis);
