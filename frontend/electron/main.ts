import { readFileSync, unlinkSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { domainToUnicode, fileURLToPath, pathToFileURL } from 'node:url'
import { app, BrowserWindow, desktopCapturer, ipcMain, Menu, nativeTheme, net, protocol, safeStorage, session, shell, systemPreferences } from 'electron'
import * as http from 'node:http'
import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { getBackendLogs, startBackend, stopBackend } from './modules/backend'
import { registerHotkeys, unregisterHotkeys } from './modules/hotkeys'
import { createMenu } from './modules/menu'
import { createTray, destroyTray } from './modules/tray'
import { downloadUpdate, installUpdate, setupAutoUpdater } from './modules/updater'
import {
  collapseFloatingWindow,
  collapseFullToCompact,
  createWindow,
  enterFloatingMode,
  exitFloatingMode,
  expandCompactToFull,
  expandFloatingWindow,
  getFloatingState,
  getMainWindow,
  isMainWindowMaximized,
  setFloatingHeight,
  setWindowPosition,
  showMainWindow,
  toggleMainWindowMaximize,
  usesManualMainWindowMaximize,
} from './modules/window'
import { notifyGeometryChanged, registerMatchatIpc } from './modules/matchat'
import { closeSplashWindow, createSplashWindow } from './modules/splash'

let isQuitting = false
let cryptoServer: http.Server | null = null

// 防止 EPIPE 导致 Electron 崩溃（后端进程 stdout 管道断开时会触发）
process.stdout?.on('error', () => {})
process.stderr?.on('error', () => {})

// 统一 userData 目录为 'lumo'，避免开发模式(package.json name)与打包模式(productName '陆墨')路径不一致
// 必须在 requestSingleInstanceLock() 之前设置，否则锁文件会创建在旧路径，导致单例机制失效与 Error code 5
app.setPath('userData', join(app.getPath('appData'), 'lumo'))

// ── 单例锁：防止多实例运行 ──
// 注意：lumo.ps1 用 taskkill /F 强杀 Electron 时 before-quit 钩子不执行，
// SingletonLock 文件可能残留且被 OS 句柄占用，下次启动报 Error code 5 (Access denied)。
// 此时 requestSingleInstanceLock() 返回 false 但并非真有实例在运行。
// 处理策略：尝试清理锁文件后重试一次；若仍失败，不退出，继续运行（仅失去单例保护）。
let gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  console.warn('[Singleton] Lock acquisition failed, attempting cleanup...')
  try {
    const userDataDir = app.getPath('userData')
    for (const name of ['SingletonLock', 'SingletonCookie', 'SingletonSocket']) {
      try {
        unlinkSync(join(userDataDir, name))
      }
      catch {}
    }
    gotTheLock = app.requestSingleInstanceLock()
  }
  catch {}
}
if (!gotTheLock) {
  // 锁获取仍失败：可能是残留锁文件被 OS 句柄占用（taskkill /F 后常见），
  // 不退出，继续运行。仅失去单例保护，不影响功能。
  console.warn('[Singleton] Lock still unavailable after cleanup, continuing without singleton protection.')
}


// ── 自定义协议：lumo-char:// 用于加载 characters 目录下的角色资源 ──
// 打包模式：extraResources/characters；开发模式：项目根/characters
const CHARACTERS_DIR = app.isPackaged
  ? resolve(process.resourcesPath, 'characters')
  : resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'characters')
// ── 自定义协议：lumo-bg:// 用于加载 premium-assets/backgrounds 目录下的背景图片 ──
const BACKGROUNDS_DIR = app.isPackaged
  ? resolve(process.resourcesPath, 'premium-assets', 'backgrounds')
  : resolve(dirname(fileURLToPath(import.meta.url)), '..', 'premium-assets', 'backgrounds')
protocol.registerSchemesAsPrivileged([
  { scheme: 'lumo-char', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
  { scheme: 'lumo-bg', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
  { scheme: 'lumo-app', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
])

app.on('second-instance', () => {
  showMainWindow()
})

app.whenReady().then(async () => {
  // ── 早期 splash 窗口：立即显示进度条，避免用户在 vite/Electron 启动期间看到空窗 ──
  // 主窗口 ready-to-show 后由 closeSplashWindow() 关闭，SplashScreen.vue 接管真实进度
  createSplashWindow()

  // MIME 映射（音频/视频等二进制媒体文件需要通过 fs.readFile 读取以兼容 asar）
  const MEDIA_MIME: Record<string, string> = {
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    ogg: 'audio/ogg',
    m4a: 'audio/mp4',
    flac: 'audio/flac',
    aac: 'audio/aac',
    webm: 'audio/webm',
    mp4: 'video/mp4',
    mkv: 'video/x-matroska',
  }
  const FILE_MIME: Record<string, string> = {
    ...MEDIA_MIME,
    json: 'application/json; charset=utf-8',
    txt: 'text/plain; charset=utf-8',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    moc3: 'application/octet-stream',
  }

  function resolveCustomProtocolPath(requestUrl: string, baseDir: string): string | null {
    try {
      const url = new URL(requestUrl)
      const host = domainToUnicode(url.hostname || '')
      const pathname = decodeURIComponent(url.pathname).replace(/^\/+/, '')
      const relativePath = [host, pathname].filter(Boolean).join('/')
      const filePath = resolve(baseDir, relativePath)
      if (!filePath.startsWith(baseDir)) {
        return null
      }
      return filePath
    }
    catch {
      return null
    }
  }

  function serveLocalFile(filePath: string, notFoundMessage = 'Not Found'): Response {
    try {
      const data = readFileSync(filePath)
      const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
      const mime = FILE_MIME[ext] || 'application/octet-stream'
      return new Response(data, {
        headers: {
          'Content-Type': mime,
          'Content-Length': data.length.toString(),
          'Cache-Control': 'no-cache',
        },
      })
    }
    catch {
      return new Response(notFoundMessage, { status: 404 })
    }
  }

  // lumo-app://路径 → 加载 dist/ 目录文件
  // 仅打包模式生效，开发模式走 Vite dev server
  const appDistDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
  protocol.handle('lumo-app', (request) => {
    const rawPath = decodeURIComponent(new URL(request.url).pathname).replace(/^\/+/, '')
    const relativePath = rawPath.startsWith('dist/') ? rawPath.slice(5) : rawPath

    const basePath = resolve(appDistDir, relativePath)
    if (!basePath.startsWith(appDistDir)) {
      return new Response('Forbidden', { status: 403 })
    }

    // 音频/视频文件通过 fs.readFileSync 读取（Node fs 天然兼容 asar），
    // 避免 net.fetch(file://) 在 asar 内对媒体文件不兼容的问题。
    // 注意：此处使用 readFileSync 而非 async readFile，因为构建工具（Rollup/Rolldown）
    // 的 tree-shaking 会将 async handler 中的 await readFile 分支整体移除，
    // 导致打包后音频无 Content-Type/Content-Length 头，播放约 6 秒后卡死。
    const ext = basePath.split('.').pop()?.toLowerCase() ?? ''
    const mime = MEDIA_MIME[ext]
    if (mime) {
      try {
        const data = readFileSync(basePath)
        return new Response(data, {
          headers: { 'Content-Type': mime, 'Content-Length': data.length.toString() },
        })
      }
      catch {
        return new Response('Not Found', { status: 404 })
      }
    }

    return net.fetch(pathToFileURL(basePath).toString())
  })

  // lumo-char://角色名/文件名 → characters/角色名/文件名
  protocol.handle('lumo-char', (request) => {
    const filePath = resolveCustomProtocolPath(request.url, CHARACTERS_DIR)
    if (!filePath) {
      return new Response('Forbidden', { status: 403 })
    }
    return serveLocalFile(filePath, 'Character Asset Not Found')
  })

  // lumo-bg://文件名 → premium-assets/backgrounds/文件名
  protocol.handle('lumo-bg', (request) => {
    const filePath = resolveCustomProtocolPath(request.url, BACKGROUNDS_DIR)
    if (!filePath) {
      return new Response('Forbidden', { status: 403 })
    }
    return serveLocalFile(filePath, 'Background Asset Not Found')
  })

  // 强制暗色主题（确保原生菜单等 UI 为深色）
  nativeTheme.themeSource = 'dark'

  // Create menu
  createMenu()

  // 先注册所有 IPC handler，确保窗口创建后渲染进程立即可用
  registerMatchatIpc()

  // Create main window
  const win = createWindow()

  // 主窗口准备好显示后，关闭早期 splash 窗口，由 SplashScreen.vue 接管真实进度
  win.once('ready-to-show', () => {
    closeSplashWindow()
  })

  // 兜底 1：主窗口加载失败（如 vite dev server 未启动）时关闭 splash，避免 splash 永久卡在 90%
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.error(`[Main] main window load failed: ${errorCode} ${errorDescription}`)
    closeSplashWindow()
  })

  // 兜底 2：30 秒后若主窗口仍未 ready-to-show（极端情况），强制关闭 splash 避免永久卡住
  setTimeout(() => {
    if (!win.isDestroyed() && !win.isVisible()) {
      console.warn('[Splash] main window ready-to-show timeout, force closing splash')
      closeSplashWindow()
    }
  }, 30000)

  // Create system tray
  createTray()

  // Register global hotkeys
  registerHotkeys()

  // Setup auto-updater (checks GitHub Releases for new versions)
  void setupAutoUpdater(win)

  // --- IPC Handlers ---

  // Window controls
  ipcMain.on('window:minimize', () => getMainWindow()?.minimize())
  ipcMain.on('window:maximize', () => toggleMainWindowMaximize())
  ipcMain.on('window:close', () => {
    const state = getFloatingState()
    if (state === 'compact' || state === 'full') {
      // 悬浮球展开态：收起为球态
      collapseFloatingWindow()
    }
    else if (state === 'classic') {
      // 经典模式：关闭窗口 → 自动进入悬浮球
      enterFloatingMode()
    }
    else {
      // 已经是球态，隐藏到托盘
      getMainWindow()?.hide()
    }
  })

  ipcMain.handle('window:isMaximized', () => isMainWindowMaximized())
  ipcMain.handle('window:getBounds', () => getMainWindow()?.getBounds() ?? { x: 0, y: 0, width: 1280, height: 800 })
  ipcMain.on('window:setBounds', (_event, bounds: { x?: number, y?: number, width?: number, height?: number }) => {
    const win = getMainWindow()
    if (!win || isMainWindowMaximized())
      return
    const current = win.getBounds()
    const next = {
      x: bounds.x ?? current.x,
      y: bounds.y ?? current.y,
      width: Math.max(800, bounds.width ?? current.width),
      height: Math.max(600, bounds.height ?? current.height),
    }
    win.setBounds(next)
  })

  // 悬浮球模式控制
  ipcMain.handle('floating:enter', () => {
    enterFloatingMode()
  })
  ipcMain.handle('floating:exit', () => {
    exitFloatingMode()
  })
  ipcMain.handle('floating:expand', (_event, toFull?: boolean) => {
    expandFloatingWindow(toFull ?? false)
  })
  ipcMain.handle('floating:expandToFull', () => {
    expandCompactToFull()
  })
  ipcMain.handle('floating:collapse', () => {
    collapseFloatingWindow()
  })
  ipcMain.handle('floating:collapseToCompact', () => {
    collapseFullToCompact()
  })
  ipcMain.handle('floating:getState', () => getFloatingState())
  ipcMain.on('floating:pin', (_event, pinned: boolean) => {
    const w = getMainWindow()
    if (w) {
      // 固定时显示任务栏图标，取消固定时隐藏（悬浮球模式下 alwaysOnTop 始终为 true）
      w.setSkipTaskbar(!pinned)
    }
  })
  ipcMain.on('floating:setPosition', (_event, x: number, y: number) => {
    setWindowPosition(x, y)
  })
  ipcMain.on('floating:fitHeight', (_event, height: number) => {
    setFloatingHeight(height)
  })

  // Update controls
  ipcMain.on('updater:download', () => downloadUpdate())
  ipcMain.on('updater:install', () => installUpdate())

  // App quit
  // 注意：不预设 isQuitting=true，让 before-quit 走 cookie flush 流程
  // （否则 before-quit 会直接放行，跳过 MatChat 登录态落盘）
  ipcMain.on('app:quit', () => {
    app.quit()
  })

  // 悬浮球右键菜单
  ipcMain.on('context-menu:show', () => {
    const menu = Menu.buildFromTemplate([
      {
        label: '打开主界面',
        click: () => exitFloatingMode(),
      },
      {
        label: '隐藏到托盘',
        click: () => getMainWindow()?.hide(),
      },
      { type: 'separator' },
      {
        label: '退出应用',
        // 不预设 isQuitting=true，让 before-quit 走 cookie flush 流程
        click: () => {
          app.quit()
        },
      },
    ])
    menu.popup()
  })

  // 窗口截屏功能
  ipcMain.handle('capture:getSources', async () => {
    // macOS 需要屏幕录制权限
    if (process.platform === 'darwin') {
      const status = systemPreferences.getMediaAccessStatus('screen')
      if (status !== 'granted') {
        return { permission: status }
      }
    }

    try {
      const sources = await desktopCapturer.getSources({
        types: ['window', 'screen'],
        thumbnailSize: { width: 320, height: 180 },
        fetchWindowIcons: true,
      })
      return sources.map(s => ({
        id: s.id,
        name: s.name,
        thumbnail: s.thumbnail.toDataURL(),
        appIcon: s.appIcon?.toDataURL() || null,
      }))
    }
    catch {
      // desktopCapturer 可能因权限问题抛出异常
      return { permission: 'denied' }
    }
  })

  ipcMain.handle('capture:captureWindow', async (_event, sourceId: string) => {
    const sources = await desktopCapturer.getSources({
      types: ['window', 'screen'],
      thumbnailSize: { width: 1920, height: 1080 },
    })
    const target = sources.find(s => s.id === sourceId)
    if (!target)
      return null
    return target.thumbnail.toDataURL()
  })

  // 打开 macOS 屏幕录制权限设置
  ipcMain.handle('capture:openScreenSettings', async () => {
    if (process.platform === 'darwin') {
      await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture')
    }
  })

  // 扫描背景图片文件夹
  ipcMain.handle('backgrounds:scan', async () => {
    try {
      const files = await readdir(BACKGROUNDS_DIR)
      const imageExts = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']
      return files.filter(f => imageExts.some(ext => f.toLowerCase().endsWith(ext)))
    }
    catch {
      return []
    }
  })

  // 开机自启动
  ipcMain.handle('autoLaunch:get', () => {
    return app.getLoginItemSettings().openAtLogin
  })
  ipcMain.handle('autoLaunch:set', (_event, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: enabled })
  })
  ipcMain.handle('backend:getLogs', () => getBackendLogs())

  // ── SafeStorage 加密桥接（陆墨定制：安全封坑期） ──
  ipcMain.handle('safe-storage:encrypt', (_event, plaintext: string): string => {
    const encrypted = safeStorage.encryptString(plaintext)
    return encrypted.toString('base64')
  })

  ipcMain.handle('safe-storage:decrypt', (_event, base64Ciphertext: string): string => {
    const encrypted = Buffer.from(base64Ciphertext, 'base64')
    return safeStorage.decryptString(encrypted)
  })

  // SafeStorage HTTP 桥接：供后端 Python 调用（带 nonce 认证）
  const bridgeToken = safeStorage.encryptString(
    JSON.stringify({ session: crypto.randomUUID(), ts: Date.now() })
  ).toString('base64')

  cryptoServer = http.createServer(async (req, res) => {
    const clientToken = req.headers['x-crypto-token']
    if (!clientToken || clientToken !== bridgeToken) {
      res.writeHead(403, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'forbidden' }))
      return
    }

    if (req.method === 'POST' && req.url === '/crypto/encrypt') {
      let body = ''
      req.on('data', chunk => body += chunk)
      req.on('end', () => {
        try {
          const { plaintext } = JSON.parse(body)
          const encrypted = safeStorage.encryptString(plaintext)
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ ciphertext: encrypted.toString('base64') }))
        } catch {
          res.writeHead(500)
          res.end(JSON.stringify({ error: 'encrypt failed' }))
        }
      })
    } else if (req.method === 'POST' && req.url === '/crypto/decrypt') {
      let body = ''
      req.on('data', chunk => body += chunk)
      req.on('end', () => {
        try {
          const { ciphertext } = JSON.parse(body)
          const plaintext = safeStorage.decryptString(Buffer.from(ciphertext, 'base64'))
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ plaintext }))
        } catch {
          res.writeHead(500)
          res.end(JSON.stringify({ error: 'decrypt failed' }))
        }
      })
    } else {
      res.writeHead(404)
      res.end()
    }
  })

  cryptoServer.listen(0, '127.0.0.1', () => {
    if (!cryptoServer) return
    const port = (cryptoServer.address() as any).port
    console.log(`[SafeStorage] Crypto bridge listening on 127.0.0.1:${port}`)
    const portFile = join(app.getPath('userData'), '.safe_storage_port')
    // 写端口文件可能因上次强杀残留句柄占用而 EPERM，用 try/catch 保护避免未捕获异常弹框
    try {
      writeFileSync(portFile, `${port}|${bridgeToken}`)
    }
    catch (err) {
      console.warn(`[SafeStorage] Failed to write port file (non-fatal):`, err)
    }
  })

  // Minimize to tray on close instead of quitting
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      win.hide()
    }
  })

  // MatChat BrowserView 几何同步
  win.on('maximize', () => {
    if (!usesManualMainWindowMaximize())
      win.webContents.send('window:maximized', true)
    notifyGeometryChanged()
  })
  win.on('unmaximize', () => {
    if (!usesManualMainWindowMaximize())
      win.webContents.send('window:maximized', false)
    notifyGeometryChanged()
  })
  win.on('resize', notifyGeometryChanged)
  win.on('move', notifyGeometryChanged)

  // 悬浮球展开态失焦时自动收起（由渲染进程控制是否启用）
  win.on('blur', () => {
    win.webContents.send('floating:windowBlur')
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
    else {
      showMainWindow()
    }
  })

  // Start backend services
  startBackend()
})

app.on('before-quit', (event) => {
  // isQuitting 已为 true 表示已在退出流程中（第二次 before-quit），直接放行让 app 真正退出
  if (isQuitting)
    return
  // 第一次 before-quit：阻止立即退出，先把 MatChat 持久化分区的 cookie 落盘
  event.preventDefault()
  isQuitting = true
  void (async () => {
    // 确保 MatChat 持久化分区（persist:matchat）的 cookie 写入磁盘。
    // Electron 的 persist: partition 默认会异步写盘，但 app 退出前若不显式 flush，
    // cookie 可能仍停留在内存缓冲区，导致下次启动时登录态丢失、需要重新登录 MatChat。
    try {
      await Promise.race([
        session.fromPartition('persist:matchat').cookies.flushStore(),
        new Promise(resolve => setTimeout(resolve, 2000)),
      ])
    }
    catch {
      // flush 失败不阻塞退出
    }
    // 关闭 SafeStorage 加密桥接服务器并清理端口文件
    try {
      if (cryptoServer) {
        cryptoServer.close()
      }
      const portFile = join(app.getPath('userData'), '.safe_storage_port')
      try {
        unlinkSync(portFile)
      }
      catch {}
    }
    catch {}
    // 重新触发退出流程：这次 isQuitting=true，before-quit 不再 preventDefault，app 正常退出
    app.quit()
  })()
})

app.on('will-quit', () => {
  unregisterHotkeys()
  destroyTray()
  stopBackend()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
