import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { app, BrowserWindow, screen, shell } from 'electron'
import { calcExpandPosition as calcExpandPositionPure } from './expandPosition'
import {
  BALL_SIZE,
  checkGeometryInvariants,
  clampFullHeight,
  COMPACT_HEIGHT,
  computeFloatingGeometry,
  EXPANDED_WIDTH,
  FitHeightTrendGuard,
  INITIAL_FULL_HEIGHT,
  isSizeWithinTolerance,
} from './floatingStateMachine'
import { fitBoundsWithinWorkArea, ManualMaximizeController, rectanglesEqual } from './windowState'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

let mainWindow: BrowserWindow | null = null
const manualMaximizeController = new ManualMaximizeController()

// 悬浮球模式状态
export type FloatingState = 'classic' | 'ball' | 'compact' | 'full'
let floatingState: FloatingState = 'classic'
let classicBounds: Electron.Rectangle | null = null // 经典模式下记住窗口位置
let ballPosition: { x: number, y: number } | null = null // 球态位置

// 尺寸常量唯一真源在 ./floatingStateMachine.ts（本模块按需 import，不再重复定义）。

// ── ★ 卷149：期望尺寸守卫 ────────────────────────────────────
// 悬浮态下窗口尺寸只应由状态机决定。任何偏离（原生 resize / Electron 平台缺陷 /
// 约束矛盾导致的强制撑大）都在 resize 事件里被检测并强制纠正。
let expectedBounds: Electron.Rectangle | null = null
/** 允许的舍入误差（px）；超过即判定偏离 */
const SIZE_TOLERANCE = 1
/** 拖拽中：主进程侧冻结尺寸变更（渲染层不可信，此处双保险） */
let isDraggingFloating = false
/** 守卫正在纠正中：避免 setBounds 触发的 resize 递归 */
let isCorrecting = false
/** 动画进行中：动画本身会连续 setBounds，此时不做偏离纠正 */
let isAnimating = false
/** full 态 fitHeight 反馈环趋势守卫（主进程侧权威判定） */
const fitTrendGuard = new FitHeightTrendGuard(5)

// 窗口渐变动画参数
const ANIM_DURATION_MS = 160
const ANIM_FPS = 60
const ANIM_FRAMES = Math.round(ANIM_DURATION_MS / (1000 / ANIM_FPS))

// 当前动画取消句柄，防止并发动画竞争
let cancelCurrentAnimation: (() => void) | null = null

/**
 * 唯一入口：应用某状态的尺寸约束并断言不变式。
 *
 * ★ 所有 setMinimumSize / setResizable 调用都必须经此函数，
 *   不得再散落各处 —— 这正是卷149 膨胀 bug 的根因（约束来源不唯一）。
 */
function applyFloatingConstraints(
  win: BrowserWindow,
  state: FloatingState,
  fullHeight?: number,
): void {
  const current = win.getBounds()
  const geometry = computeFloatingGeometry(state, fullHeight ?? current.height, {
    width: current.width,
    height: current.height,
  })

  const violations = checkGeometryInvariants(geometry)
  if (violations.length > 0) {
    // 不变式被破坏时 Windows 会强制放大窗口 —— 这是必须暴露的异常信号
    console.warn(`[floating] 几何不变式违规（state=${state}）: ${violations.join('; ')}`)
  }

  win.setMinimumSize(geometry.minWidth, geometry.minHeight)
  win.setResizable(geometry.resizable)
}

/** 设定期望尺寸（守卫的比对基准）+ 触发一次透明窗重绘（缓解扩大区域黑块） */
function commitExpectedBounds(win: BrowserWindow, bounds: Electron.Rectangle): void {
  expectedBounds = { ...bounds }
  invalidateTransparentSurface(win)
}

/**
 * 透明窗黑块缓解。
 *
 * 透明窗扩大时，新增区域若未被 GPU 合成层重绘会露出黑底
 * （这正是"增大区域被黑块填充"的观感来源）。
 * webContents.invalidate() 强制整窗重绘，把新区域的合成结果补上。
 *
 * ★ 延后一个 tick：调用方通常在 setBounds **之前**更新期望尺寸，
 *   若立即重绘，画的还是旧尺寸的合成结果 —— 必须等 setBounds 生效。
 */
function invalidateTransparentSurface(win: BrowserWindow): void {
  if (win.isDestroyed())
    return
  setTimeout(() => {
    if (!win.isDestroyed())
      win.webContents.invalidate()
  }, 0)
}

/** 把约束与期望同步到"当前实际尺寸"（用于动画被打断时收敛状态） */
function syncConstraintsToCurrentBounds(win: BrowserWindow): void {
  const current = win.getBounds()
  applyFloatingConstraints(win, floatingState, current.height)
  commitExpectedBounds(win, current)
}

/**
 * 强制把窗口尺寸拉回期望值。
 * 拖拽结束、或 resize 事件检测到偏离时调用。
 */
function enforceExpectedBounds(win: BrowserWindow): void {
  if (!expectedBounds || floatingState === 'classic' || isCorrecting)
    return

  const actual = win.getBounds()
  if (isSizeWithinTolerance(actual, expectedBounds, SIZE_TOLERANCE))
    return

  isCorrecting = true
  try {
    console.warn(
      `[floating] 检测到尺寸偏离：实际 ${actual.width}x${actual.height}`
      + ` ≠ 期望 ${expectedBounds.width}x${expectedBounds.height}，已强制纠正`,
    )
    win.setBounds({
      x: actual.x,
      y: actual.y,
      width: expectedBounds.width,
      height: expectedBounds.height,
    })
    invalidateTransparentSurface(win)
  }
  finally {
    // 让本次 setBounds 触发的 resize 事件先跑完再解锁
    setTimeout(() => {
      isCorrecting = false
    }, 0)
  }
}

/** 安装期望尺寸守卫（createWindow 时调用一次） */
function installFloatingResizeGuard(win: BrowserWindow): void {
  win.on('resize', () => {
    if (isCorrecting || isAnimating || isDraggingFloating)
      return
    if (floatingState === 'classic')
      return // 经典态允许自由缩放
    enforceExpectedBounds(win)
  })
}

/**
 * 分步动画过渡窗口尺寸和位置
 * 自动取消上一个未完成的动画，避免并发竞争
 *
 * ★ 卷149 修复：取消路径必须收敛状态。
 *   旧实现在取消时只 clearInterval，**不调用 onDone** —— 于是动画起始时设的
 *   minimumSize / 期望尺寸就停在中间态，与真实 bounds 撕裂（这正是膨胀的成因之一）。
 *   现在取消时统一走 syncConstraintsToCurrentBounds()，以实际尺寸为准对齐约束。
 */
function animateBounds(
  win: BrowserWindow,
  from: Electron.Rectangle,
  to: Electron.Rectangle,
  onDone?: () => void,
): void {
  // 取消上一个动画（其 onCancel 会收敛约束，避免状态撕裂）
  cancelCurrentAnimation?.()

  // ★ 动画期间的最小约束取"起止尺寸的较小值"。
  //   若直接套用目标态约束（如 full 的 minWidth=420），而当前窗口只有 100 宽，
  //   Windows 会在动画开始前就把窗口弹到 420 —— 视觉跳变 + 一步"变大"。
  win.setMinimumSize(
    Math.min(from.width, to.width),
    Math.min(from.height, to.height),
  )

  isAnimating = true
  let frame = 0
  const interval = setInterval(() => {
    frame++
    // easeOutCubic: 快起慢停
    const t = frame / ANIM_FRAMES
    const ease = 1 - (1 - t) ** 3

    const x = Math.round(from.x + (to.x - from.x) * ease)
    const y = Math.round(from.y + (to.y - from.y) * ease)
    const w = Math.round(from.width + (to.width - from.width) * ease)
    const h = Math.round(from.height + (to.height - from.height) * ease)

    win.setBounds({ x, y, width: w, height: h })

    if (frame >= ANIM_FRAMES) {
      clearInterval(interval)
      cancelCurrentAnimation = null
      // ★ 顺序要紧：先把"期望尺寸"切到目标值，再落定最终 bounds。
      //   否则若 resize 事件即时派发，守卫会拿旧期望值误判偏离、把窗口纠正回去。
      commitExpectedBounds(win, to)
      win.setBounds(to)
      isAnimating = false
      onDone?.()
    }
  }, 1000 / ANIM_FPS)

  cancelCurrentAnimation = () => {
    clearInterval(interval)
    cancelCurrentAnimation = null
    isAnimating = false
    // ★ 动画被打断：以当前实际尺寸为准同步约束与期望，防止状态撕裂
    syncConstraintsToCurrentBounds(win)
  }
}

/**
 * 根据球的位置计算面板展开的位置
 * 水平方向：始终从球位置向右展开（球在面板左侧），超出屏幕时左移面板
 * 垂直方向：面板顶部与球顶部对齐，空间不足时上移面板
 */
function calcExpandPosition(ballX: number, ballY: number, targetHeight: number): { x: number, y: number } {
  const display = screen.getPrimaryDisplay()
  const { width: screenW, height: screenH } = display.workAreaSize
  // 纯几何部分已抽到 ./expandPosition.ts（无 Electron 依赖，可单测）
  return calcExpandPositionPure(ballX, ballY, targetHeight, screenW, screenH)
}

export function createWindow(): BrowserWindow {
  // Windows: 使用 .ico 确保任务栏图标清晰
  const isWin = process.platform === 'win32'
  const baseDir = app.isPackaged ? process.resourcesPath : app.getAppPath()
  const iconFile = isWin ? 'icon.ico' : 'icon.png'
  const iconPath = join(baseDir, 'build', iconFile)

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    // Electron 不支持 Windows 透明窗口的原生最大化，改由自定义按钮模拟。
    maximizable: !isWin,
    resizable: true,
    hasShadow: true,
    transparent: true,
    show: false,
    icon: iconPath,
    webPreferences: {
      preload: join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      webgl: true,
    },
  })
  manualMaximizeController.reset()

  // ★ 卷149：安装期望尺寸守卫（悬浮态下任何尺寸偏离都会被纠正）
  installFloatingResizeGuard(mainWindow)

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  // Open external links in browser
  // 仅放行 http/https 协议，拒绝 file://、javascript: 及任意自定义协议，
  // 避免 shell.openExternal 被恶意页面利用启动本地可执行文件或危险协议处理器。
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const parsed = new URL(url)
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        shell.openExternal(url)
      }
    }
    catch {
      // 非法 URL 直接忽略，不调用 openExternal
    }
    return { action: 'deny' }
  })

  // Load the app
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  }
  else {
    // 打包模式：通过 lumo-app:// 协议加载，支持热补丁覆盖
    mainWindow.loadURL('lumo-app://dist/index.html')
  }

  return mainWindow
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

export function usesManualMainWindowMaximize(): boolean {
  return process.platform === 'win32'
}

export function isMainWindowMaximized(): boolean {
  const win = mainWindow
  if (!win || floatingState !== 'classic')
    return false

  return usesManualMainWindowMaximize()
    ? manualMaximizeController.isMaximized()
    : win.isMaximized()
}

function setBoundsIfChanged(win: BrowserWindow, bounds: Electron.Rectangle): void {
  if (!rectanglesEqual(win.getBounds(), bounds)) {
    win.setBounds(bounds)
  }
}

function sendMaximizedState(win: BrowserWindow, maximized: boolean): void {
  win.webContents.send('window:maximized', maximized)
}

export function toggleMainWindowMaximize(): void {
  const win = mainWindow
  if (!win || floatingState !== 'classic')
    return

  if (!usesManualMainWindowMaximize()) {
    if (win.isMaximized())
      win.unmaximize()
    else
      win.maximize()
    return
  }

  if (manualMaximizeController.isMaximized()) {
    const restoreBounds = manualMaximizeController.restore(win.getBounds())
    const display = screen.getDisplayMatching(restoreBounds)
    const visibleBounds = fitBoundsWithinWorkArea(restoreBounds, display.workArea)

    win.setMovable(true)
    win.setResizable(true)
    setBoundsIfChanged(win, visibleBounds)
    sendMaximizedState(win, false)
    return
  }

  if (win.isMinimized())
    win.restore()

  const currentBounds = win.getBounds()
  const display = screen.getDisplayMatching(currentBounds)
  const maximizedBounds = manualMaximizeController.maximize(currentBounds, display.workArea)

  setBoundsIfChanged(win, maximizedBounds)
  win.setResizable(false)
  win.setMovable(false)
  sendMaximizedState(win, true)
}

export function showMainWindow(): void {
  const win = mainWindow
  if (!win)
    return

  if (win.isMinimized())
    win.restore()

  if (floatingState === 'classic' && usesManualMainWindowMaximize() && manualMaximizeController.isMaximized()) {
    const referenceBounds = manualMaximizeController.getRestoreBounds() ?? win.getBounds()
    const display = screen.getDisplayMatching(referenceBounds)
    setBoundsIfChanged(win, display.workArea)
  }
  else {
    const bounds = win.getBounds()
    const display = screen.getDisplayMatching(bounds)
    setBoundsIfChanged(win, fitBoundsWithinWorkArea(bounds, display.workArea))
  }

  win.show()
  win.moveTop()
  win.focus()
}

export function getFloatingState(): FloatingState {
  return floatingState
}

/**
 * 进入悬浮球模式：将窗口缩小为球态
 */
export function enterFloatingMode(): void {
  const win = mainWindow
  if (!win)
    return

  // 记住经典模式的窗口位置
  classicBounds = win.getBounds()
  floatingState = 'ball'

  // 计算球态初始位置（屏幕右下角偏移）
  if (!ballPosition) {
    const display = screen.getPrimaryDisplay()
    const { width, height } = display.workAreaSize
    ballPosition = {
      x: width - BALL_SIZE - 40,
      y: height - BALL_SIZE - 40,
    }
  }

  win.setAlwaysOnTop(true, 'modal-panel')
  win.setSkipTaskbar(true)
  win.setHasShadow(false)

  const ballBounds = {
    x: ballPosition.x,
    y: ballPosition.y,
    width: BALL_SIZE,
    height: BALL_SIZE,
  }
  // 约束与期望统一经状态机，不再手写 setMinimumSize / setResizable
  applyFloatingConstraints(win, 'ball')
  commitExpectedBounds(win, ballBounds)
  win.setBounds(ballBounds)

  win.webContents.send('floating:stateChanged', floatingState)
}

/**
 * 退出悬浮球模式：恢复经典窗口
 */
export function exitFloatingMode(): void {
  const win = mainWindow
  if (!win)
    return

  floatingState = 'classic'

  const restoreToManualMaximized = usesManualMainWindowMaximize()
    && manualMaximizeController.isMaximized()

  win.setAlwaysOnTop(false)
  win.setSkipTaskbar(false)
  win.setResizable(!restoreToManualMaximized)
  win.setMovable(!restoreToManualMaximized)
  win.setHasShadow(true)
  const classicGeometry = computeFloatingGeometry('classic')
  win.setMinimumSize(classicGeometry.minWidth, classicGeometry.minHeight)

  // 退出悬浮态：清除期望尺寸与拖拽/环检测状态（经典态允许用户自由缩放，不参与偏离纠正）
  expectedBounds = null
  isDraggingFloating = false
  isAnimating = false
  fitTrendGuard.reset()

  if (restoreToManualMaximized) {
    const referenceBounds = manualMaximizeController.getRestoreBounds() ?? classicBounds ?? win.getBounds()
    const display = screen.getDisplayMatching(referenceBounds)
    win.setBounds(display.workArea)
  }
  else if (classicBounds) {
    win.setBounds(classicBounds)
  }
  else {
    win.setBounds({ width: 1280, height: 800 })
    win.center()
  }

  win.webContents.send('floating:stateChanged', floatingState)
}

/**
 * 球态 -> 紧凑态或完整态（带动画）
 * toFull=true 时直接展开到完整尺寸（有消息历史时），否则展开到紧凑尺寸
 * 始终从球位置向右展开，球保持在面板左侧
 */
export function expandFloatingWindow(toFull: boolean = false): void {
  const win = mainWindow
  if (!win || floatingState !== 'ball')
    return

  // 记住球的位置
  const fromBounds = win.getBounds()
  ballPosition = { x: fromBounds.x, y: fromBounds.y }

  // 完整态先展开到最小高度，由渲染进程通过 fitHeight 根据实际内容动态调整
  const targetHeight = toFull ? INITIAL_FULL_HEIGHT : COMPACT_HEIGHT
  floatingState = toFull ? 'full' : 'compact'

  const { x: expandX, y: expandY } = calcExpandPosition(ballPosition.x, ballPosition.y, targetHeight)
  const toBounds = { x: expandX, y: expandY, width: EXPANDED_WIDTH, height: targetHeight }

  win.setHasShadow(true)
  // 进入新的展开会话：清空上一轮的 fit 趋势历史
  fitTrendGuard.reset()
  // 动画期间的约束由 animateBounds 按起止尺寸最小值统一设定（避免提前把窗口弹大）

  animateBounds(win, fromBounds, toBounds, () => {
    // ★ 卷149 关键修复：动画落定后，约束取该态的**最小允许值**
    //   （full 态 = MIN_FIT_HEIGHT = 100），而不是动画目标高度 targetHeight。
    //   旧实现锁成 (EXPANDED_WIDTH, targetHeight) 后，内容一旦收缩到 targetHeight 以下，
    //   便出现 minHeight > bounds —— Windows 会强制把窗口撑到 minimumSize，
    //   表现为"窗口越来越大"，且由此触发渲染层 re-measure 形成递增反馈环。
    applyFloatingConstraints(win, floatingState, targetHeight)
    win.webContents.send('floating:stateChanged', floatingState)
  })
}

/**
 * 紧凑态 -> 完整态（带动画）
 * 初始扩展到最小完整态高度，后续由渲染进程通过 fitHeight 动态调整
 */
export function expandCompactToFull(): void {
  const win = mainWindow
  if (!win || floatingState !== 'compact')
    return

  floatingState = 'full'

  // 先通知渲染进程切换到完整态模板，避免动画期间紧凑态模板被拉伸
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()
  const display = screen.getPrimaryDisplay()
  const { height: screenH } = display.workAreaSize

  // 优先向下扩展（保持顶部不动）
  let newY = fromBounds.y
  if (fromBounds.y + INITIAL_FULL_HEIGHT > screenH) {
    newY = screenH - INITIAL_FULL_HEIGHT
    if (newY < 0)
      newY = 0
  }

  const toBounds = {
    x: fromBounds.x,
    y: newY,
    width: EXPANDED_WIDTH,
    height: INITIAL_FULL_HEIGHT,
  }

  // 动画期间的约束由 animateBounds 按起止尺寸最小值统一设定
  animateBounds(win, fromBounds, toBounds, () => {
    applyFloatingConstraints(win, 'full', INITIAL_FULL_HEIGHT)
  })
}

/**
 * 完整态 -> 紧凑态（带动画）
 * 保持顶部位置不变，窗口高度收缩到紧凑态高度
 */
export function collapseFullToCompact(): void {
  const win = mainWindow
  if (!win || floatingState !== 'full')
    return

  floatingState = 'compact'

  // 先通知渲染进程切换到紧凑态模板
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()
  const toBounds = {
    x: fromBounds.x,
    y: fromBounds.y,
    width: EXPANDED_WIDTH,
    height: COMPACT_HEIGHT,
  }

  // 动画期间的约束由 animateBounds 按起止尺寸最小值统一设定
  animateBounds(win, fromBounds, toBounds, () => {
    applyFloatingConstraints(win, 'compact')
  })
}

/**
 * 紧凑态/完整态 -> 球态（带动画）
 * 球始终回到当前窗口左边缘的位置（球视觉上在面板左侧）
 */
export function collapseFloatingWindow(): void {
  const win = mainWindow
  if (!win || (floatingState !== 'compact' && floatingState !== 'full'))
    return

  floatingState = 'ball'

  // 先通知渲染进程切换视图，再开始窗口动画
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()

  // 球收缩到当前窗口的左边缘位置，垂直居中于面板顶部（球高 = compact高 = 100px）
  const targetX = fromBounds.x
  const targetY = fromBounds.y

  // 更新 ballPosition 为收缩后的实际位置
  ballPosition = { x: targetX, y: targetY }

  const toBounds = {
    x: targetX,
    y: targetY,
    width: BALL_SIZE,
    height: BALL_SIZE,
  }

  win.setHasShadow(false)
  // 动画期间的约束由 animateBounds 按起止尺寸最小值统一设定
  animateBounds(win, fromBounds, toBounds, () => {
    applyFloatingConstraints(win, 'ball')
  })
}

/**
 * 设置窗口位置（用于渲染进程手动拖拽）
 * 同时更新 ballPosition 以保持收缩时位置一致
 */
export function setWindowPosition(x: number, y: number): void {
  const win = mainWindow
  if (!win)
    return
  const rx = Math.round(x)
  const ry = Math.round(y)
  if (floatingState !== 'classic') {
    // 打断动画：cancelCurrentAnimation 内部会 syncConstraintsToCurrentBounds，
    // 把尺寸约束与期望对齐到当前实际尺寸 —— 旧实现只 clearInterval，
    // 会把 minimumSize 留在动画起始态的 ball 尺寸上，与真实 bounds 撕裂。
    cancelCurrentAnimation?.()
  }
  win.setPosition(rx, ry)
  // 任何悬浮球相关状态拖拽时都同步位置（球态/展开态都需要）
  if (floatingState !== 'classic') {
    ballPosition = { x: rx, y: ry }
    // 期望尺寸的 x/y 同步跟随，否则松手后的偏离纠正会把窗口拉回旧位置
    if (expectedBounds)
      expectedBounds = { ...expectedBounds, x: rx, y: ry }
  }
}

/**
 * 拖拽状态通知（渲染层在 pointerdown / pointerup 时调用）。
 *
 * 渲染层已有 `isDraggingWindow` 自我约束，但按"渲染层不可信原则"，
 * 主进程必须**独立**冻结尺寸变更：拖拽期间任何 fitHeight / 偏离纠正都不应介入，
 * 否则与用户手势竞争造成抖动与状态撕裂。
 */
export function setFloatingDragging(dragging: boolean): void {
  isDraggingFloating = dragging

  const win = mainWindow
  if (!win)
    return

  if (dragging) {
    // 进入拖拽：先打断动画并以当前尺寸收敛约束，避免拖拽中约束与 bounds 不一致
    cancelCurrentAnimation?.()
    return
  }

  // 拖拽结束：清空 fit 趋势历史，并纠正拖拽期间可能被放行的尺寸偏离
  fitTrendGuard.reset()
  enforceExpectedBounds(win)
}

/**
 * 设置完整态窗口高度（由渲染进程根据内容高度调用）
 * 高度限制在 [MIN_FIT_HEIGHT, MAX_FULL_HEIGHT] 范围内
 * 高度变化 > 50px 时使用短动画过渡（如打开/关闭面板），小变化直接设置（流式消息逐行增长）
 */
export function setFloatingHeight(height: number): void {
  const win = mainWindow
  if (!win || floatingState !== 'full')
    return

  // ★ 主进程侧拖拽冻结（渲染层不可信，此处为双保险）：
  //   拖拽中尺寸由用户手势主导，任何 fitHeight 都不该介入。
  if (isDraggingFloating)
    return

  const clamped = clampFullHeight(height)

  // ★ 反馈环趋势守卫：连续递增达上限即判环并拒绝该次 fit。
  //   渲染层的"相同值"守卫挡不住递增环（变大→测量更大→再变大）。
  const verdict = fitTrendGuard.record(clamped)
  if (!verdict.accept) {
    console.warn(`[floating] ${verdict.reason}，本次 fitHeight(${clamped}) 已忽略`)
    return
  }

  const bounds = win.getBounds()

  if (bounds.height === clamped)
    return

  // 取消可能正在进行的高度动画，避免与新目标冲突
  cancelCurrentAnimation?.()

  const display = screen.getPrimaryDisplay()
  const { height: screenH } = display.workAreaSize

  // 保持顶部不动，向下扩展；超出屏幕时向上调整
  const base = win.getBounds()
  let newY = base.y
  if (base.y + clamped > screenH) {
    newY = screenH - clamped
    if (newY < 0)
      newY = 0
  }

  const toBounds = { x: base.x, y: newY, width: EXPANDED_WIDTH, height: clamped }
  const delta = Math.abs(clamped - base.height)

  if (delta > 50) {
    // 高度变化较大时使用动画过渡（如打开/关闭会话历史面板）
    // 动画期间的约束由 animateBounds 按起止尺寸最小值统一设定
    animateBounds(win, base, toBounds)
  }
  else {
    // 小变化直接设置（如流式消息逐行增长）
    applyFloatingConstraints(win, 'full', clamped)
    // ★ 顺序要紧：先更新期望尺寸，再 setBounds（理由同 animateBounds 结束分支）
    commitExpectedBounds(win, toBounds)
    win.setBounds(toBounds)
  }
}
