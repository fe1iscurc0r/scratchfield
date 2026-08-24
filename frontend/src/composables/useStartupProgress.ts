import { ref, watch } from 'vue'
import API from '@/api/core'
import { backendConnected } from '@/utils/config'
import { preloadAllViews } from '@/utils/viewPreloader'

/** 将 promise 限制在 ms 毫秒内完成，超时则 resolve(undefined) 而非 reject */
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T | undefined> {
  return Promise.race([
    promise,
    new Promise<undefined>((resolve) => {
      setTimeout(() => {
        console.warn(`[Startup] ${label} 超时 (${ms}ms)，跳过`)
        resolve(undefined)
      }, ms)
    }),
  ])
}

export function useStartupProgress() {
  const progress = ref(0)
  const phase = ref<string>('初始化...')
  const isReady = ref(false)
  const stallHint = ref(false)

  let targetProgress = 0
  let rafId = 0
  let modelReady = false
  let postConnectStarted = false
  let unsubProgress: (() => void) | undefined
  let lastProgressValue = 0
  let lastProgressChangeTime = Date.now()

  // 停滞检测：进度 3 秒无变化 → 显示提示
  function checkStall() {
    const now = Date.now()
    if (progress.value !== lastProgressValue) {
      lastProgressValue = progress.value
      lastProgressChangeTime = now
      stallHint.value = false
    }
    else if (!stallHint.value && now - lastProgressChangeTime >= 3000 && progress.value < 100) {
      stallHint.value = true
      console.warn(`[Startup] 进度停滞在 ${progress.value.toFixed(1)}%，已超过 3 秒`)
    }
  }

  // requestAnimationFrame 驱动的丝滑插值
  function animateProgress() {
    const diff = targetProgress - progress.value
    if (diff > 0.5) {
      // 比例追赶 + 最低速度，避免接近目标时卡顿
      progress.value = Math.min(progress.value + Math.max(diff * 0.12, 0.5), targetProgress)
    }
    else if (diff > 0) {
      progress.value = targetProgress
    }

    if (progress.value >= 100) {
      progress.value = 100
      isReady.value = true
    }

    checkStall()

    if (!isReady.value || progress.value < 100) {
      rafId = requestAnimationFrame(animateProgress)
    }
  }

  function setTarget(value: number, newPhase: string) {
    if (value > targetProgress) {
      console.log(`[Startup] 进度 ${targetProgress.toFixed(0)}% → ${value.toFixed(0)}%  阶段: ${newPhase}`)
      targetProgress = value
      phase.value = newPhase
    }
  }

  // 外部通知：Live2D 模型加载完成
  function notifyModelReady() {
    modelReady = true
    console.log('[Startup] Live2D 模型就绪')
    setTarget(25, '等待后端...')
  }

  async function runPostConnect() {
    // 幂等守卫：防止 watcher + 健康轮询重复触发
    if (postConnectStarted)
      return
    postConnectStarted = true

    // 全局安全超时：无论什么原因，15 秒后强制完成启动
    const safetyTimer = setTimeout(() => {
      console.warn('[Startup] runPostConnect 全局超时 (15s)，强制完成启动')
      setTarget(100, '准备就绪')
    }, 15000)

    try {
      // 取消后端进度监听
      unsubProgress?.()
      unsubProgress = undefined

      // 阶段 25→50：后端已连接
      console.log('[Startup] 后端已连接，开始后连接任务')
      setTarget(50, '加载资源...')

      // 视图预加载改为后台异步执行，不阻塞启动流程（让 Live2D 优先显示）
      console.log('[Startup] 在后台异步预加载视图组件...')
      preloadAllViews((loaded, total) => {
        console.log(`[Startup] 后台预加载视图 ${loaded}/${total}`)
      }).catch(() => {
        console.warn('[Startup] 后台视图预加载失败，不影响启动')
      })

      // 阶段 50→80：获取会话（5 秒超时）
      setTarget(80, '获取会话...')
      console.log('[Startup] 获取会话列表...')
      try {
        await withTimeout(API.getSessions(), 5000, 'getSessions')
        console.log('[Startup] 会话获取完成')
      }
      catch {
        console.warn('[Startup] 会话获取失败，不阻塞启动')
      }
      setTarget(95, '准备就绪...')

      console.log('[Startup] 所有启动任务完成，进入主界面')

      // 阶段 95→100：完成
      setTimeout(() => setTarget(100, '准备就绪'), 200)
    }
    finally {
      clearTimeout(safetyTimer)
    }
  }

  async function startProgress() {
    // 阶段 0→10：初始化
    setTarget(10, modelReady ? '连接后端...' : '加载模型...')
    rafId = requestAnimationFrame(animateProgress)

    // 监听后端进度信号（Electron 环境）
    const api = window.electronAPI
    if (api?.backend) {
      unsubProgress = api.backend.onProgress((payload) => {
        // 后端 percent 0~50 映射到前端 10~50 区间
        const mapped = 10 + (payload.percent / 50) * 40
        setTarget(Math.min(mapped, 50), payload.phase)
      })
    }

    // 如果后端已连接（HMR/重复挂载），直接推进
    if (backendConnected.value) {
      runPostConnect()
      return
    }

    // 监听后端连接（由 config.ts connectBackend 触发）
    const stopWatch = watch(backendConnected, (connected) => {
      if (!connected)
        return
      stopWatch()
      runPostConnect()
    })
  }

  function cleanup() {
    if (rafId)
      cancelAnimationFrame(rafId)
    unsubProgress?.()
  }

  return {
    progress,
    phase,
    isReady,
    stallHint,
    startProgress,
    notifyModelReady,
    cleanup,
  }
}
