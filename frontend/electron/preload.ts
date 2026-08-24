/**
 * Electron preload 脚本
 *
 * 安全模型（-defense in depth- 三道防线）：
 *   1) contextIsolation: true  —— 渲染进程的 JS 上下文与 preload 隔离，渲染层拿不到 require/process 等 Node 对象。
 *   2) nodeIntegration: false —— 渲染层无法直接 require Electron 模块。
 *   3) IPC 通道白名单（IPC_WHITELIST）—— 即便渲染层通过 contextBridge 拿到了 ipcRenderer 包装对象，
 *      每次调用仍会校验 channel 名是否在白名单内，防止“任意通道调用”攻击。
 *
 * 暴露原则：只通过 contextBridge.exposeInMainWorld('electronAPI', ...) 暴露最小必要 API，
 * 所有方法内部均经过白名单校验后再转发到 ipcRenderer，渲染层永远拿不到原始 ipcRenderer。
 */
import { contextBridge, ipcRenderer as _ipcRenderer } from 'electron'

// Security: Explicit whitelist of IPC channels accessible from the renderer.
// Only channels listed here can be called via the preload bridge.
// contextIsolation: true + contextBridge.exposeInMainWorld already restrict
// renderer access to these APIs; the whitelist adds defense-in-depth by
// validating every channel name at call time.
//
// 【白名单维护规范】新增主进程 ipcMain.handle / ipcMain.on 通道后，必须同步把 channel 名加到这里，
// 否则渲染层调用会被 validate() 直接抛错。channel 名一律使用 `模块:动作` 小写命名。
const IPC_WHITELIST = new Set<string>([
  'window:minimize', 'window:maximize', 'window:close', 'window:isMaximized',
  'window:getBounds', 'window:setBounds', 'app:quit', 'context-menu:show',
  'window:maximized',
  'updater:download', 'updater:install', 'updater:update-available', 'updater:update-downloaded',
  'floating:enter', 'floating:exit', 'floating:expand', 'floating:expandToFull',
  'floating:collapse', 'floating:collapseToCompact', 'floating:getState',
  'floating:pin', 'floating:fitHeight', 'floating:setPosition',
  'floating:stateChanged', 'floating:windowBlur',
  'capture:getSources', 'capture:captureWindow', 'capture:openScreenSettings',
  'backend:getLogs', 'backend:progress', 'backend:log', 'backend:error',
  'backgrounds:scan',
  'autoLaunch:get', 'autoLaunch:set',
  'safe-storage:encrypt', 'safe-storage:decrypt',
  'patcher:getStatus', 'patcher:checkUpdate', 'patcher:reset', 'patcher:isOfficial',
  'patcher:revokeTrust', 'patcher:getTrustedSources',
  'patcher:applied', 'patcher:unofficial-source', 'patcher:progress', 'patcher:error',
  'matchat:attach', 'matchat:detach', 'matchat:setBounds', 'matchat:reload',
  'matchat:openExternal', 'matchat:clearStorage', 'matchat:extractLastQA',
  'matchat:openDevTools', 'matchat:url-change', 'matchat:load-error',
])

/**
 * 创建一个带白名单校验的 ipcRenderer 包装对象。
 * 每个方法（send/invoke/on/removeListener）调用前都会执行 validate(channel)，
 * 不在白名单的通道会立即抛错，阻止渲染层“试探”未授权通道。
 */
function createWhitelistedIpc() {
  // 通道校验：白名单命中才放行，否则抛错。这是第三道安全防线的关键执行点。
  const validate = (channel: string): void => {
    if (!IPC_WHITELIST.has(channel)) {
      throw new Error(`[preload] IPC channel "${channel}" is not whitelisted`)
    }
  }

  return {
    // 单向发送（fire-and-forget），主进程不会回执
    send: (channel: string, ...args: unknown[]) => {
      validate(channel)
      return _ipcRenderer.send(channel, ...args)
    },
    // 双向调用（Promise），主进程通过 ipcMain.handle 回执
    invoke: (channel: string, ...args: unknown[]) => {
      validate(channel)
      return _ipcRenderer.invoke(channel, ...args)
    },
    // 监听主进程推送事件。注意：返回的是原始 ipcRenderer 以便链式 removeListener，
    // 调用方需配对使用 on/removeListener，否则会泄漏监听器。
    // listener 类型用 any[] 而非 unknown[]，因为 Electron 的 IpcRendererEvent 类型
    // 不能赋值给 unknown——这是 Electron 类型定义的已知限制。
    on: (channel: string, listener: (...args: any[]) => void) => {
      validate(channel)
      return _ipcRenderer.on(channel, listener)
    },
    // 注销监听器，channel 同样需过白名单（防止用合法 on 注册后用非法名注销绕过统计）
    removeListener: (channel: string, listener: (...args: any[]) => void) => {
      validate(channel)
      return _ipcRenderer.removeListener(channel, listener)
    },
  }
}

const ipcRenderer = createWhitelistedIpc()

/**
 * 通过 navigator.userAgentData / platform / userAgent 综合判定操作系统。
 * 优先用 userAgentData.platform（现代浏览器 API），退化到 navigator.platform，再到 userAgent 字符串匹配。
 * 返回值与 process.platform 保持一致命名（darwin/win32/linux），便于业务层跨平台分支。
 */
function detectPlatform(): 'darwin' | 'win32' | 'linux' | 'unknown' {
  const uaDataPlatform = (navigator as Navigator & { userAgentData?: { platform?: string } }).userAgentData?.platform
  const parts = [
    uaDataPlatform,
    navigator.platform,
    navigator.userAgent,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()

  if (parts.includes('mac'))
    return 'darwin'
  if (parts.includes('win'))
    return 'win32'
  if (parts.includes('linux'))
    return 'linux'
  return 'unknown'
}

/**
 * 暴露给渲染层的 electronAPI 对象。
 * 每个命名空间对应一类功能，内部全部走 ipcRenderer 包装对象（带白名单校验）。
 * 事件监听类方法（onXxx）统一返回一个 unsubscribe 函数，调用方在 onBeforeUnmount 中调用即可解绑，避免内存泄漏。
 */
const electronAPI = {
  // ── 窗口控制 ──
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  getBounds: () => ipcRenderer.invoke('window:getBounds') as Promise<{ x: number, y: number, width: number, height: number }>,
  setBounds: (bounds: { x?: number, y?: number, width?: number, height?: number }) => ipcRenderer.send('window:setBounds', bounds),
  quit: () => ipcRenderer.send('app:quit'),
  showContextMenu: () => ipcRenderer.send('context-menu:show'),

  // ── 窗口状态事件 ──
  onMaximized: (callback: (maximized: boolean) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, maximized: boolean) => callback(maximized)
    ipcRenderer.on('window:maximized', handler)
    return () => ipcRenderer.removeListener('window:maximized', handler)
  },

  // ── 自动更新 ──
  downloadUpdate: () => ipcRenderer.send('updater:download'),
  installUpdate: () => ipcRenderer.send('updater:install'),

  onUpdateAvailable: (callback: (info: { version: string, releaseNotes: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, info: { version: string, releaseNotes: string }) => callback(info)
    ipcRenderer.on('updater:update-available', handler)
    return () => ipcRenderer.removeListener('updater:update-available', handler)
  },
  onUpdateDownloaded: (callback: () => void) => {
    const handler = () => callback()
    ipcRenderer.on('updater:update-downloaded', handler)
    return () => ipcRenderer.removeListener('updater:update-downloaded', handler)
  },

  // ── 悬浮球模式控制（classic=经典窗口 / ball=悬浮球 / compact=紧凑 / full=全屏展开）──
  floating: {
    enter: () => ipcRenderer.invoke('floating:enter'),
    exit: () => ipcRenderer.invoke('floating:exit'),
    expand: (toFull?: boolean) => ipcRenderer.invoke('floating:expand', toFull),
    expandToFull: () => ipcRenderer.invoke('floating:expandToFull'),
    collapse: () => ipcRenderer.invoke('floating:collapse'),
    collapseToCompact: () => ipcRenderer.invoke('floating:collapseToCompact'),
    getState: () => ipcRenderer.invoke('floating:getState') as Promise<'classic' | 'ball' | 'compact' | 'full'>,
    pin: (value: boolean) => ipcRenderer.send('floating:pin', value),
    fitHeight: (height: number) => ipcRenderer.send('floating:fitHeight', height),
    setPosition: (x: number, y: number) => ipcRenderer.send('floating:setPosition', x, y),
    // 悬浮态变化推送，KnowledgeView 据此自动 detach/attach BrowserView
    onStateChange: (callback: (state: 'classic' | 'ball' | 'compact' | 'full') => void) => {
      const handler = (_event: Electron.IpcRendererEvent, state: 'classic' | 'ball' | 'compact' | 'full') => callback(state)
      ipcRenderer.on('floating:stateChanged', handler)
      return () => ipcRenderer.removeListener('floating:stateChanged', handler)
    },
    onWindowBlur: (callback: () => void) => {
      const handler = () => callback()
      ipcRenderer.on('floating:windowBlur', handler)
      return () => ipcRenderer.removeListener('floating:windowBlur', handler)
    },
  },

  // ── 窗口截屏功能 ──
  capture: {
    getSources: () => ipcRenderer.invoke('capture:getSources') as Promise<
      | { permission: string }
      | Array<{ id: string, name: string, thumbnail: string, appIcon: string | null }>
    >,
    captureWindow: (sourceId: string) => ipcRenderer.invoke('capture:captureWindow', sourceId) as Promise<string | null>,
    openScreenSettings: () => ipcRenderer.invoke('capture:openScreenSettings') as Promise<void>,
  },

  // ── 后端进程通信（启动进度/日志/错误推送）──
  backend: {
    getLogs: () => ipcRenderer.invoke('backend:getLogs') as Promise<string>,
    onProgress: (callback: (payload: { percent: number, phase: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, payload: { percent: number, phase: string }) => callback(payload)
      ipcRenderer.on('backend:progress', handler)
      return () => ipcRenderer.removeListener('backend:progress', handler)
    },
    onLog: (callback: (payload: { line: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, payload: { line: string }) => callback(payload)
      ipcRenderer.on('backend:log', handler)
      return () => ipcRenderer.removeListener('backend:log', handler)
    },
    onError: (callback: (payload: { code: number, logs: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, payload: { code: number, logs: string }) => callback(payload)
      ipcRenderer.on('backend:error', handler)
      return () => ipcRenderer.removeListener('backend:error', handler)
    },
  },

  // ── 背景图片扫描 ──
  backgrounds: {
    scan: () => ipcRenderer.invoke('backgrounds:scan') as Promise<string[]>,
  },

  // ── 开机自启动 ──
  autoLaunch: {
    get: () => ipcRenderer.invoke('autoLaunch:get') as Promise<boolean>,
    set: (enabled: boolean) => ipcRenderer.invoke('autoLaunch:set', enabled) as Promise<void>,
  },

  // ── SafeStorage 加密/解密（陆墨定制：安全封坑期）──
  // 用 Electron safeStorage 把敏感字符串加解密，密钥由 OS keychain 管理
  safeStorage: {
    encrypt: (plaintext: string) => ipcRenderer.invoke('safe-storage:encrypt', plaintext) as Promise<string>,
    decrypt: (base64Ciphertext: string) => ipcRenderer.invoke('safe-storage:decrypt', base64Ciphertext) as Promise<string>,
  },

  // ── 热补丁系统（运行时下发前端/后端补丁）──
  patcher: {
    getStatus: () => ipcRenderer.invoke('patcher:getStatus') as Promise<{
      patchVersion: string | null
      appliedAt: string | null
      source: string | null
      official: boolean
      patchDir: string
      fileCount: number
    }>,
    checkUpdate: (serverUrl: string) => ipcRenderer.invoke('patcher:checkUpdate', serverUrl) as Promise<{
      updated: boolean
      version?: string
      frontendChanged: boolean
      backendChanged: boolean
      source?: string
    }>,
    reset: () => ipcRenderer.invoke('patcher:reset') as Promise<{ success: boolean, error?: string }>,
    isOfficial: (url: string) => ipcRenderer.invoke('patcher:isOfficial', url) as Promise<boolean>,
    revokeTrust: (url: string) => ipcRenderer.invoke('patcher:revokeTrust', url) as Promise<{ success: boolean }>,
    getTrustedSources: () => ipcRenderer.invoke('patcher:getTrustedSources') as Promise<string[]>,
    /** 补丁应用完成 */
    onApplied: (callback: (info: { version: string, frontendChanged: boolean, backendChanged: boolean, official: boolean, source: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: any) => callback(info)
      ipcRenderer.on('patcher:applied', handler)
      return () => ipcRenderer.removeListener('patcher:applied', handler)
    },
    /** 非官方来源警告 */
    onUnofficialSource: (callback: (info: { url: string, status: string, message: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: any) => callback(info)
      ipcRenderer.on('patcher:unofficial-source', handler)
      return () => ipcRenderer.removeListener('patcher:unofficial-source', handler)
    },
    /** 下载进度 */
    onProgress: (callback: (info: { percent: number, file: string }) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, info: any) => callback(info)
      ipcRenderer.on('patcher:progress', handler)
      return () => ipcRenderer.removeListener('patcher:progress', handler)
    },
    /** 错误通知 */
    onError: (callback: (message: string) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, msg: string) => callback(msg)
      ipcRenderer.on('patcher:error', handler)
      return () => ipcRenderer.removeListener('patcher:error', handler)
    },
  },

  // ── MatChat 内嵌知识库（BrowserView 嵌入主窗口）──
  matchat: {
    /** 把 BrowserView 挂到主窗口并设置初始 bounds */
    attach: (rect: { x: number; y: number; width: number; height: number }) =>
      ipcRenderer.invoke('matchat:attach', rect) as Promise<boolean>,
    /** 从主窗口摘除 BrowserView（不销毁，便于重新 attach） */
    detach: () => ipcRenderer.invoke('matchat:detach') as Promise<boolean>,
    /** 更新 BrowserView 的 bounds（单向发送，高频调用走 send 避免 invoke 往返开销） */
    setBounds: (rect: { x: number; y: number; width: number; height: number }) =>
      ipcRenderer.send('matchat:setBounds', rect),
    /** 重新加载 MatChat 页面 */
    reload: () => ipcRenderer.invoke('matchat:reload') as Promise<boolean>,
    /** 用系统默认浏览器打开 MatChat */
    openExternal: () => ipcRenderer.invoke('matchat:openExternal') as Promise<boolean>,
    /** 清除 MatChat 的持久化存储（cookies/localStorage/indexedDB/cache），用于切账号 */
    clearStorage: () => ipcRenderer.invoke('matchat:clearStorage') as Promise<boolean>,
    /** 从当前 MatChat 页面 DOM 提取最近 N 轮问答对 */
    extractLastQA: (pairs?: number) =>
      ipcRenderer.invoke('matchat:extractLastQA', pairs ?? 1) as Promise<
        | { ok: true; data: Array<{ q: string; a: string }> | { __debug: true; totalCandidates: number; candidates: Array<{ tag: string; class: string; dataRole: string | null; childCount: number; count: number; textPreview: string }> } }
        | { ok: false; error: string }
      >,
    /** 打开 BrowserView 的 DevTools（调试 DOM selector 用） */
    openDevTools: () => ipcRenderer.send('matchat:openDevTools'),
    /** 监听 MatChat 页面导航 URL 变化 */
    onUrlChange: (cb: (url: string) => void) => {
      const handler = (_e: Electron.IpcRendererEvent, url: string) => cb(url)
      ipcRenderer.on('matchat:url-change', handler)
      return () => ipcRenderer.removeListener('matchat:url-change', handler)
    },
    /** 监听 MatChat 页面加载失败 */
    onLoadError: (cb: (err: string) => void) => {
      const handler = (_e: Electron.IpcRendererEvent, err: string) => cb(err)
      ipcRenderer.on('matchat:load-error', handler)
      return () => ipcRenderer.removeListener('matchat:load-error', handler)
    },
  },

  // ── 平台信息（darwin/win32/linux/unknown），供 UI 做 OS 分支 ──
  platform: detectPlatform(),
}

// 通过 contextBridge 把 electronAPI 注入渲染进程的 window，隔离环境下渲染层只能看到此对象
contextBridge.exposeInMainWorld('electronAPI', electronAPI)
