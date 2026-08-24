function createTrayMenuController(context) {
  const {
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
    getAppConfig,
    getIsGlobalAlwaysOnTop,
    getIsMobileMode,
    getIsStreamerMode,
    getLoadingWindow,
    getMainWindow,
    getOriginalUrl,
    getPreventSystemSleepStatus,
    getTray,
    guardStorageStartupGate,
    http,
    ipcRouter,
    log,
    process,
    reloadAndShow,
    relaunchApp,
    requestAppQuit,
    saveConfig,
    setIsGlobalAlwaysOnTop,
    setIsMobileMode,
    setPreventSystemSleepEnabled,
    setIsStreamerMode,
    shell,
    https,
    startTopReassertion,
    stopPetGameModeWatcher,
    stopTopReassertion,
    t,
    updateTrayMenuSoon,
    windowManager,
  } = context;

  let togglingGlobalTop = false;
  let windowsTrayPopupMenu = null;
  let windowsTrayPopupHookedTray = null;

  // 托盘 radio 当前选中的聊天窗口形态。从持久化配置初始化（#1：重启记住上次选的 full/compact），
  // 缺省 compact。仅跟踪「用户上次通过托盘选的」形态用于 checked 态，不与渲染进程其它途径
  // （折叠球、热键等）的 mode 变化做双向同步——那是 stage ② 之外的范畴。启动时若为 full，
  // 由 storage-gate 的 maybeCreateStartupReactChat 负责实际打开 full 独立窗口。
  let chatSurfaceMode = (() => {
    try {
      const c = typeof getAppConfig === 'function' ? getAppConfig() : null;
      return c && c.chatSurfaceMode === 'full' ? 'full' : 'compact';
    } catch (_) {
      return 'compact';
    }
  })();

  function ensureAppConfig() {
    return getAppConfig();
  }

  function getTrayPopupPosition(bounds) {
    if (!bounds) return null;
    const x = Number(bounds.x);
    const y = Number(bounds.y);
    const width = Number(bounds.width);
    const height = Number(bounds.height);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return {
      x: Math.round(x + (Number.isFinite(width) ? width / 2 : 0)),
      y: Math.round(y + (Number.isFinite(height) ? height / 2 : 0)),
    };
  }

  function showWindowsTrayMenuWithGuard(_event, bounds) {
    const tray = getTray();
    const menu = windowsTrayPopupMenu;
    if (!tray || typeof tray.popUpContextMenu !== 'function') return;
    if (!menu) return;
    if (typeof beginSystemMenuOcclusionGuard !== 'function') return;
    if (typeof endSystemMenuOcclusionGuard !== 'function') return;

    beginSystemMenuOcclusionGuard();
    let restored = false;
    const restore = () => {
      if (restored) return;
      restored = true;
      endSystemMenuOcclusionGuard();
    };

    try {
      menu.once('menu-will-close', restore);
      const position = getTrayPopupPosition(bounds);
      if (position) {
        tray.popUpContextMenu(menu, position);
      } else {
        tray.popUpContextMenu(menu);
      }
    } catch (e) {
      restore();
      log('显示托盘菜单失败:', e.message);
    }
  }

  function installWindowsTrayPopup(menu) {
    const tray = getTray();
    if (!tray || process.platform !== 'win32') return false;
    if (!menu || typeof menu.once !== 'function') return false;
    if (typeof tray.popUpContextMenu !== 'function') return false;
    if (typeof beginSystemMenuOcclusionGuard !== 'function') return false;
    if (typeof endSystemMenuOcclusionGuard !== 'function') return false;
    if (typeof tray.on !== 'function') return false;

    windowsTrayPopupMenu = menu;
    if (windowsTrayPopupHookedTray !== tray) {
      tray.on('right-click', showWindowsTrayMenuWithGuard);
      windowsTrayPopupHookedTray = tray;
    }

    if (typeof tray.setContextMenu === 'function') {
      tray.setContextMenu(null);
    }
    return true;
  }

  function setChatSurfaceModeFromTray(mode) {
    if (mode !== 'full' && mode !== 'compact') return;
    chatSurfaceMode = mode;
    // #1：持久化选择，重启后恢复（storage-gate 启动时据此决定开 full 还是 compact）。
    try {
      const cfg = getAppConfig();
      if (cfg && cfg.chatSurfaceMode !== mode) {
        cfg.chatSurfaceMode = mode;
        saveConfig(cfg);
      }
    } catch (e) {
      log('持久化聊天窗口形态失败:', e.message);
    }
    // 与「打开对话框」一致先过 storage gate：存储未就绪/维护期不直接拉起聊天卫星窗口
    // （否则会在后端存储就绪前打开 /chat_full 或强建 compact）。形态选择已持久化，刷新菜单即可，
    // 窗口待存储就绪后由用户再次操作 / 启动恢复拉起。
    if (guardStorageStartupGate('traySetChatSurfaceMode')) {
      updateTrayMenu();
      return;
    }
    // full/compact 是两个互斥的独立窗口（part B）：full 走 fullChatWindow（加载 /chat_full、
    // preload-chat-full.js，与 compact 绝对隔离），compact 走 reactChatWindow。不再给共用的
    // reactChat 发 SET_MODE（共用窗口里切 full 会被 preload listener 同步拉回 compact）。
    try {
      if (mode === 'full') {
        windowManager.showFullChatWindow(getOriginalUrl(), { log });
        log('切换聊天窗口形态: full（独立完整窗口）');
      } else {
        // compact：先隐藏 full 独立窗口，再用可靠的 ensureReactChatWindow(forceShow) 路径揭示
        // compact —— 直接 reactChatWindow.show() 在它处于 dim/毛线球 carrier/userClosed 态时
        // 不会真正现身（曾导致切回 compact 对话框消失、需手动「打开对话框」）。
        if (typeof windowManager.hideFullChatWindow === 'function') windowManager.hideFullChatWindow();
        ensureReactChatWindow({ focus: true, forceShow: true, reason: 'tray-compact' });
        log('切换聊天窗口形态: compact（紧凑悬浮条）');
      }
    } catch (e) {
      log('切换聊天窗口形态时出错:', e.message);
    }
    updateTrayMenu();
  }

function applyGlobalAlwaysOnTop(enabled) {
  // 注意：此函数假定调用方已将 getIsGlobalAlwaysOnTop() 置为最新值。
  // 对所有现存窗口遍历并委托给 applyTopOn（内部会读取 getIsGlobalAlwaysOnTop() 与 URL 分类）。
  const managedWindows = windowManager.getWindows();
  const toast = windowManager.getToastWindow ? windowManager.getToastWindow() : null;
  const loadingWindow = getLoadingWindow ? getLoadingWindow() : null;

  for (const win of BrowserWindow.getAllWindows()) {
    if (!win || win.isDestroyed() || win === loadingWindow) continue;

    // Toast 独立于全局开关（始终 screen-saver）
    if (toast && win === toast) {
      try { win.setAlwaysOnTop(true, 'screen-saver'); } catch (e) { /* ignore */ }
      continue;
    }

    // Pet / 卫星窗口：传 kind 让 applyTopOn 使用默认 level='floating'
    if (win === getMainWindow()) {
      applyTopOn(win, { kind: 'pet', defaultLevel: 'floating' });
    } else if (win === managedWindows.chat) {
      applyTopOn(win, { kind: 'chat', defaultLevel: 'floating' });
    } else if (win === managedWindows.fullChat) {
      // full（完整聊天窗口）是与 compact 各自独立的窗口实例，这里只是复用 compact 同一套受管
      // 顶层策略（kind 'chat' → reactChat 的 level），两窗口本身并不归一。
      applyTopOn(win, { kind: 'chat', defaultLevel: 'floating' });
    } else if (win === managedWindows.subtitle) {
      applyTopOn(win, { kind: 'subtitle', defaultLevel: 'floating' });
    } else if (win === managedWindows.agentHud) {
      applyTopOn(win, { kind: 'agentHud', defaultLevel: 'floating' });
    } else if (win === managedWindows.jukebox) {
      applyTopOn(win, { kind: 'jukebox', defaultLevel: 'floating' });
    } else {
      // 弹出子窗口 / hotkey / portSettings / feedback 等：按 URL 分类
      applyTopOn(win);
    }
  }
}

function closeChatWindowFromTray() {
  try {
    log('用户点击关闭对话框');
    // 对偶性：「关闭对话框」要关掉当前在显示的聊天窗口。full 开着时一并隐藏 full 独立窗口。
    // 用 hideFullChatWindow（置 _nekoWantHidden）而非裸 hide()：若 /chat_full 还在加载（窗口
    // 尚 show:false），裸 hide() 是 no-op，随后 pending 的 ready-to-show 仍会把 full 显示出来。
    try {
      if (typeof windowManager.hideFullChatWindow === 'function') windowManager.hideFullChatWindow();
    } catch (e) {
      log('关闭 full 独立窗口时出错:', e.message);
    }
    if (typeof hideReactChatFromMain === 'function') {
      hideReactChatFromMain({ userClosed: true, reason: 'tray' });
    }
  } catch (e) {
    log('关闭对话框时出错:', e.message);
  }
}

function updateTrayMenu() {
  ensureAppConfig();
  const autostartStatus = autostartService.getStatus();
  const preventSystemSleepStatus = typeof getPreventSystemSleepStatus === 'function'
    ? (getPreventSystemSleepStatus() || {})
    : {};

  const menuTemplate = [
    // ===== 常用操作 =====
    {
      label: t('resetModelPosition'),
      click: () => {
        try {
          log('用户点击复位模型位置');
          if (getMainWindow() && !getMainWindow().isDestroyed()) {
            getMainWindow().webContents.send('reset-model-position');
          }
        } catch (e) {
          log('复位模型位置时出错:', e.message);
        }
      }
    },
    {
      label: t('reload'),
      click: () => reloadAndShow(getOriginalUrl())
    },
    {
      label: t('openChatWindow'),
      click: () => {
        if (guardStorageStartupGate('trayOpenChatWindow')) return;
        // 对偶性：「打开对话框」按当前选定形态打开 —— full 则开独立完整窗口，否则开 compact。
        if (chatSurfaceMode === 'full') {
          windowManager.showFullChatWindow(getOriginalUrl(), { log });
        } else {
          ensureReactChatWindow({ focus: true, reason: 'tray', forceShow: true });
        }
      }
    },
    {
      label: t('closeChatWindow'),
      click: closeChatWindowFromTray
    },
    {
      label: t('chatSurfaceMode'),
      submenu: [
        {
          label: t('chatSurfaceCompact'),
          type: 'radio',
          checked: chatSurfaceMode === 'compact',
          click: () => setChatSurfaceModeFromTray('compact')
        },
        {
          label: t('chatSurfaceFull'),
          type: 'radio',
          checked: chatSurfaceMode === 'full',
          click: () => setChatSurfaceModeFromTray('full')
        }
      ]
    },

    { type: 'separator' },

    // ===== 显示设置（二级菜单） =====
    {
      label: t('displaySettings'),
      submenu: [
        {
          label: t('globalAlwaysOnTop'),
          type: 'checkbox',
          checked: getIsGlobalAlwaysOnTop(),
          click: (menuItem) => {
            // 快速连点防护：忙位生效期间忽略新的点击
            if (togglingGlobalTop) {
              log('全局置顶切换忙，忽略本次点击');
              return;
            }
            togglingGlobalTop = true;
            const prev = getIsGlobalAlwaysOnTop();
            const next = !!menuItem.checked;
            // 顺序：先改内存态 → 应用到窗口 → 成功后才落盘；失败时回滚
            setIsGlobalAlwaysOnTop(next);
            try {
              applyGlobalAlwaysOnTop(next);
              // 联动 Z-order 重断言 timer + Pet 游戏模式 watcher 的启停
              if (next) {
                startTopReassertion();  // 内部会启动 Pet 游戏模式 watcher
              } else {
                stopTopReassertion();
                stopPetGameModeWatcher();
              }
              getAppConfig().globalAlwaysOnTop = next;
              saveConfig(getAppConfig());
              log('全局置顶设置已保存:', next);
            } catch (e) {
              log('切换全局置顶失败，回滚到:', prev, '错误:', e.message);
              setIsGlobalAlwaysOnTop(prev);
              try { applyGlobalAlwaysOnTop(prev); } catch (e2) { log('回滚也失败:', e2.message); }
              // timer 状态也回滚
              if (prev) {
                startTopReassertion();
              } else {
                stopTopReassertion();
                stopPetGameModeWatcher();
              }
            } finally {
              togglingGlobalTop = false;
              updateTrayMenu();
            }
          }
        },
        {
          label: getIsMobileMode() ? t('switchToDesktop') : t('switchToMobile'),
          click: () => {
            setIsMobileMode(!getIsMobileMode());
            if (getIsMobileMode()) {
              reloadAndShow('about:blank');
              if (getMainWindow() && !getMainWindow().isDestroyed()) {
                getMainWindow().minimize();
                getMainWindow().hide();
              }
            } else {
              reloadAndShow(getOriginalUrl());
            }
            setTimeout(() => updateTrayMenu(), 100);
          }
        },
        {
          label: t('streamerMode'),
          type: 'checkbox',
          checked: getIsStreamerMode(),
          click: (menuItem) => {
            try {
              setIsStreamerMode(!!menuItem.checked);
              getAppConfig().streamerMode = getIsStreamerMode();
              saveConfig(getAppConfig());
              log('窗口模式设置已保存:', getIsStreamerMode());
              reloadAndShow(getOriginalUrl());
            } catch (e) {
              log('切换窗口模式时出错:', e.message);
            }
            setTimeout(() => updateTrayMenu(), 100);
          }
        },
        {
          label: t('darkMode'),
          type: 'checkbox',
          checked: !!getAppConfig().darkMode,
          click: (menuItem) => {
            try {
              getAppConfig().darkMode = !!menuItem.checked;
              saveConfig(getAppConfig());
              log('暗色模式设置已保存:', getAppConfig().darkMode);
              ipcRouter.broadcastGlobal('toggle-dark-mode', getAppConfig().darkMode);
              _pushDarkModeToHotkeyWindow(getAppConfig().darkMode);
            } catch (e) {
              log('切换暗色模式时出错:', e.message);
            }
            updateTrayMenu();
          }
        }
      ]
    },

    // ===== 高级设置（二级菜单） =====
    {
      label: t('advancedSettings'),
      submenu: [
        {
          label: t('hotkeySettings'),
          click: () => {
            createHotkeyWindow();
          }
        },
        {
          label: t('resetToDefaultModel'),
          click: () => {
            try {
              log('用户点击恢复默认模型');
              if (getMainWindow() && !getMainWindow().isDestroyed()) {
                getMainWindow().webContents.send('reset-to-default-model');
              } else {
                log('恢复默认模型失败：getMainWindow() 不可用');
              }
            } catch (e) {
              log('恢复默认模型时出错:', e.message);
            }
          }
        },
        {
          label: t('autoLaunch'),
          type: 'checkbox',
          checked: autostartStatus.enabled === true,
          enabled: autostartStatus.supported !== false,
          click: (menuItem) => {
            try {
              const shouldEnable = !!menuItem.checked;
              const result = applyAutostartPreference(shouldEnable);
              if (result.enabled !== shouldEnable) {
                throw new Error(result.error || 'autostart_toggle_failed');
              }
            } catch (e) {
              log('切换开机自启动时出错:', e.message);
              if (e.message === 'autostart_requires_approval') {
                void dialog.showMessageBox({
                  type: 'info',
                  buttons: [t('autostartDialogOk')],
                  title: t('autostartApprovalTitle'),
                  message: t('autostartApprovalMessage'),
                  detail: t('autostartApprovalDetail')
                });
              } else if (e.message === 'autostart_service_not_found') {
                void dialog.showMessageBox({
                  type: 'error',
                  buttons: [t('autostartDialogOk')],
                  title: t('autostartServiceNotFoundTitle'),
                  message: t('autostartServiceNotFoundMessage'),
                  detail: t('autostartServiceNotFoundDetail')
                });
              } else {
                void dialog.showMessageBox({
                  type: 'error',
                  buttons: [t('autostartDialogOk')],
                  title: t('autostartFailedTitle'),
                  message: t('autostartFailedMessage'),
                  detail: `${t('autostartFailedDetailPrefix')}${e.message}`
                });
              }
            }
          }
        },
        {
          label: t('preventSystemSleep'),
          type: 'checkbox',
          checked: preventSystemSleepStatus.active === true,
          enabled: preventSystemSleepStatus.supported !== false,
          click: (menuItem) => {
            const cfg = ensureAppConfig();
            const previous = cfg.preventSystemSleep === true;
            const next = !!menuItem.checked;
            try {
              const result = setPreventSystemSleepEnabled(next, 'tray');
              if (result && result.ok === false) {
                throw new Error(result.error || 'prevent_sleep_toggle_failed');
              }
              cfg.preventSystemSleep = next;
              saveConfig(cfg);
              log('防睡眠设置已保存:', next);
            } catch (e) {
              cfg.preventSystemSleep = previous;
              try { setPreventSystemSleepEnabled(previous, 'tray rollback'); } catch (_) {}
              log('切换防睡眠时出错:', e && e.message ? e.message : e);
            }
            updateTrayMenu();
          }
        },
        {
          label: t('disableProxy'),
          type: 'checkbox',
          checked: !getAppConfig().useSystemProxy,
          click: async (menuItem) => {
            try {
              getAppConfig().useSystemProxy = !menuItem.checked;
              saveConfig(getAppConfig());
              log('系统代理设置已保存:', getAppConfig().useSystemProxy);
              await applyProxySettings(!!getAppConfig().useSystemProxy);
              const isDirect = !getAppConfig().useSystemProxy;
              try {
                const postData = JSON.stringify({ direct: isDirect });
                const url = new URL('/api/config/set_proxy_mode', getOriginalUrl() || 'http://localhost:48911');
                const client = url.protocol === 'https:' ? https : http;
                await new Promise((resolve) => {
                  const req = client.request(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(postData) },
                    timeout: 3000
                  }, (res) => {
                    let data = '';
                    res.on('data', chunk => data += chunk);
                    res.on('end', () => {
                      log('后端代理模式切换结果:', data);
                      resolve();
                    });
                  });
                  req.on('error', (err) => {
                    log('通知后端切换代理模式失败（后端可能未运行）:', err.message);
                    resolve();
                  });
                  req.write(postData);
                  req.end();
                });
              } catch (e) {
                log('通知后端代理模式切换异常:', e.message);
              }
            } catch (e) {
              log('切换系统代理时出错:', e.message);
            }
            updateTrayMenu();
          }
        },
        ...((process.platform === 'win32' || process.platform === 'linux') ? [{
          label: t('compatibilityMode'),
          type: 'checkbox',
          checked: getAppConfig().compatibilityMode === true,
          click: async (menuItem) => {
            getAppConfig().compatibilityMode = !!menuItem.checked;
            saveConfig(getAppConfig());
            log('兼容模式设置已保存:', getAppConfig().compatibilityMode);
            const result = await dialog.showMessageBox({
              type: 'warning',
              buttons: [t('portRestartNow'), t('later')],
              defaultId: 0,
              title: 'N.E.K.O.',
              message: t('restartRequired'),
            });
            if (result.response === 0) {
              const relaunchArgs = process.platform === 'linux'
                ? buildLinuxCompatibilityRelaunchArgs(getAppConfig().compatibilityMode === true)
                : undefined;
              relaunchApp('compatibility mode relaunch', relaunchArgs);
            }
            updateTrayMenu();
          }
        }] : []),
        ...(process.platform === 'linux' ? [{
          label: t('linuxForceX11'),
          type: 'checkbox',
          checked: getAppConfig().linuxForceX11 === true,
          click: async (menuItem) => {
            getAppConfig().linuxForceX11 = !!menuItem.checked;
            saveConfig(getAppConfig());
            const msg = menuItem.checked ? t('linuxForceX11Warning') : t('linuxForceX11OffWarning');
            const result = await dialog.showMessageBox({
              type: 'warning',
              buttons: [t('portRestartNow'), t('later')],
              defaultId: 0,
              title: 'N.E.K.O.',
              message: msg,
            });
            if (result.response === 0) {
              relaunchApp('linux force x11 relaunch', buildLinuxCompatibilityRelaunchArgs(getAppConfig().compatibilityMode === true));
            }
            updateTrayMenu();
          }
        }] : []),
        ...(process.platform === 'linux' ? [{
          label: t('linuxUseNativeNotify'),
          type: 'checkbox',
          checked: getAppConfig().linuxUseNativeNotify !== false,
          toolTip: t('linuxUseNativeNotifyTip'),
          click: (menuItem) => {
            getAppConfig().linuxUseNativeNotify = !!menuItem.checked;
            saveConfig(getAppConfig());
            log('Linux 系统通知模式:', menuItem.checked ? '开启' : '关闭');
            updateTrayMenu();
          }
        }] : []),
        {
          label: t('portSettings'),
          click: () => {
            createPortSettingsWindow();
          }
        }
      ]
    },

    { type: 'separator' },

    // ===== DevTools（调试用）=====
    {
      label: 'DevTools',
      submenu: [
        {
          label: 'Pet Window',
          click: () => {
            try {
              if (getMainWindow() && !getMainWindow().isDestroyed()) getMainWindow().webContents.openDevTools({ mode: 'detach' });
            } catch (e) { log('打开 Pet DevTools 失败:', e.message); }
          }
        },
        {
          label: 'Chat Window',
          click: () => {
            try {
              const wins = windowManager.getWindows();
              const chatWin = (wins.fullChat && !wins.fullChat.isDestroyed() && wins.fullChat.isVisible())
                ? wins.fullChat
                : wins.chat;
              if (chatWin && !chatWin.isDestroyed()) chatWin.webContents.openDevTools({ mode: 'detach' });
            } catch (e) { log('打开 Chat DevTools 失败:', e.message); }
          }
        },
        {
          label: 'Subtitle Window',
          click: () => {
            try {
              const wins = windowManager.getWindows();
              if (wins.subtitle && !wins.subtitle.isDestroyed()) wins.subtitle.webContents.openDevTools({ mode: 'detach' });
            } catch (e) { log('打开 Subtitle DevTools 失败:', e.message); }
          }
        },
      ]
    },

    { type: 'separator' },

    // ===== 底部操作 =====
    {
      label: t('uploadLogs'),
      click: () => feedbackModule.createFeedbackWindow()
    },
    {
      label: t('exit'),
      click: async () => {
        log('用户通过托盘菜单请求退出');
        const confirmed = await confirmTrayExitWithRetention();
        if (!confirmed) return;
        requestAppQuit('tray menu exit');
      }
    }
  ];

  const menu = Menu.buildFromTemplate(menuTemplate);
  if (!installWindowsTrayPopup(menu)) {
    getTray().setContextMenu(menu);
  }
}

  return {
    applyGlobalAlwaysOnTop,
    updateTrayMenu,
  };
}

module.exports = {
  createTrayMenuController,
};
