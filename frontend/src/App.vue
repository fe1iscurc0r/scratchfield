<script lang="ts">
// 模块级标记，HMR 重挂载时不会重置
</script>

<script setup lang="ts">
import type { FloatingState } from '@/electron.d'
import { useEventListener, useWindowSize } from '@vueuse/core'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, defineAsyncComponent, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ACCESS_TOKEN, authExpired, setAuthExpiredSuppressed } from '@/api'
import API from '@/api/core'
import AppSidebar from '@/components/AppSidebar.vue'
import BackendDebugDialog from '@/components/BackendDebugDialog.vue'
import BackendErrorDialog from '@/components/BackendErrorDialog.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import LoginDialog from '@/components/LoginDialog.vue'
import SplashScreen from '@/components/SplashScreen.vue'
import TitleBar from '@/components/TitleBar.vue'
import UpdateDialog from '@/components/UpdateDialog.vue'
import WindowResizeHandles from '@/components/WindowResizeHandles.vue'
import { playBgm, playClickEffect, stopBgm } from '@/composables/useAudio'
import { cloudUser, isLoggedIn, sessionRestored, useAuth } from '@/composables/useAuth'
import { useBackground } from '@/composables/useBackground'
import { useElectron } from '@/composables/useElectron'
import { useGlobalHotkeys } from '@/composables/useGlobalHotkeys'
import { useParallax } from '@/composables/useParallax'
import { connectRealtimeUi, disconnectRealtimeUi } from '@/composables/useRealtimeUi'
import { useStartupProgress } from '@/composables/useStartupProgress'
import { startToolPolling, stopToolPolling } from '@/composables/useToolStatus'
import { checkForUpdate, showUpdateDialog, updateInfo } from '@/composables/useVersionCheck'
import { backendConnected, CONFIG } from '@/utils/config'
import { clearExpression, setExpression } from '@/utils/live2dController'
import { ensureLive2dCoreLoaded } from '@/utils/live2dCoreLoader'
import { destroyParallax, initParallax } from '@/utils/parallax'
import { activeTabId, agentContacts, proactiveNotifier, tabs } from '@/utils/session'
import { messageViewExpanded } from '@/utils/uiState'
import FloatingView from '@/views/FloatingView.vue'

// Live2D 链（pixi.js + pixi-live2d-display，数百 KB）改异步组件，
// 首屏入口 chunk 不再打包 WebGL 栈，按需加载。
// 顺序硬约束：pixi-live2d-display 在**模块顶层**就有
// `if (!window.Live2DCubismCore) throw new Error('Could not find Cubism 4 runtime...')`，
// 所以核心库必须在 import 之前注入，否则整个 vendor-pixi chunk 一被 import 就抛错，
// 异步组件永远挂载不上 —— 表现就是 Live2D 主体消失（只剩背景光斑）。
const Live2dModel = defineAsyncComponent(async () => {
  await ensureLive2dCoreLoaded()
  return import('@/components/Live2dModel.vue')
})

let _splashDismissed = false

const isElectron = !!window.electronAPI
const { isMaximized } = useElectron()
const isMac = window.electronAPI?.platform === 'darwin'
const LIVE2D_SOURCE_CACHE_KEY = 'lumo-startup-live2d-source'
const DEFAULT_STARTUP_LIVE2D_SOURCE = isElectron
  ? 'lumo-char://娜杰日达/NagaTest2/NagaTest2.model3.json'
  : './models/naga-test/naga-test.model3.json'

function normalizeRuntimeLive2dSource(source?: string | null): string {
  // 兼容旧版本缓存的 naga-char:// 协议名（已更名为 lumo-char://）
  const trimmed = (source?.trim() ?? '').replace(/^naga-char:\/\//, 'lumo-char://')
  if (!trimmed) {
    return ''
  }
  if (trimmed.startsWith('lumo-char://')) {
    if (isElectron) {
      // Electron：由主进程自定义协议直接读本地 characters 目录
      return trimmed
    }
    // 浏览器（非 Electron）：无自定义协议可解析，lumo-char:// 原样传给
    // pixi 会加载失败（Live2D 消失的根因）。转换为后端静态挂载
    // /characters/<角色>/<路径>（api_server.py 已挂载该目录，实测 200）。
    const rest = trimmed.slice('lumo-char://'.length)
    if (!rest) {
      return ''
    }
    const backendOrigin = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
    return `${backendOrigin}/characters/${encodeURI(rest)}`
  }
  try {
    const url = new URL(trimmed)
    const isLocalCharactersUrl = (url.protocol === 'http:' || url.protocol === 'https:')
      && ['localhost', '127.0.0.1'].includes(url.hostname)
      && url.pathname.startsWith('/characters/')
    if (!isLocalCharactersUrl) {
      return trimmed
    }
    // 仅 Electron 才做 http→lumo-char 归一（主进程协议读本地目录）；
    // 浏览器下必须保留 http URL 直接走后端静态挂载，否则无法加载。
    if (!isElectron) {
      return trimmed
    }
    const match = url.pathname.match(/^\/characters\/([^/]+)\/(.+)$/)
    if (!match) {
      return trimmed
    }
    const characterName = decodeURIComponent(match[1] ?? '')
    const modelPath = decodeURIComponent(match[2] ?? '')
    if (!characterName || !modelPath) {
      return trimmed
    }
    return `lumo-char://${characterName}/${modelPath}`
  }
  catch {
    return trimmed
  }
}

function readCachedStartupLive2dSource(): string {
  try {
    return normalizeRuntimeLive2dSource(localStorage.getItem(LIVE2D_SOURCE_CACHE_KEY)) || DEFAULT_STARTUP_LIVE2D_SOURCE
  }
  catch {
    return DEFAULT_STARTUP_LIVE2D_SOURCE
  }
}

function persistStartupLive2dSource(source?: string | null) {
  const normalized = normalizeRuntimeLive2dSource(source) || DEFAULT_STARTUP_LIVE2D_SOURCE
  startupLive2dSource.value = normalized
  try {
    localStorage.setItem(LIVE2D_SOURCE_CACHE_KEY, normalized)
  }
  catch {
    // ignore storage errors
  }
}

const showResizeHandles = computed(() => isElectron && !isFloatingMode.value && !isMaximized.value)
// macOS hiddenInset title bar is 28px, Windows/Linux custom title bar is 32px
const titleBarPadding = isElectron ? (isMac ? '28px' : '32px') : '0px'

const toast = useToast()

const currentRoute = useRoute()
const isForumRoute = computed(() => currentRoute.path.startsWith('/forum'))
// KnowledgeView 也使用紧凑布局（无大 padding），因为内部已有自己的分栏布局
const isCompactRoute = computed(() => isForumRoute.value || currentRoute.path.startsWith('/knowledge'))

// ── 自定义背景 ──
const { activeBackground, getActiveBackgroundUrl } = useBackground()
const hasCustomBg = computed(() => !!activeBackground.value)
const customBgUrl = computed(() => getActiveBackgroundUrl())

const { width, height } = useWindowSize()
const scale = computed(() => height.value / (10000 - CONFIG.value.web_live2d.model.size))
const characterModelMap = ref<Record<string, string>>({})
const live2dRenderKey = ref(0)
const startupLive2dSource = ref(readCachedStartupLive2dSource())
const activeLive2dSource = ref(startupLive2dSource.value)
const activeAgentCharacterTemplate = computed(() => {
  const tab = tabs.value.find(item => item.id === activeTabId.value)
  if (!tab || tab.type !== 'agent' || !tab.instanceId)
    return ''
  return agentContacts.value.find(item => item.id === tab.instanceId)?.characterTemplate || tab.characterTemplate || ''
})
const resolvedLive2dSource = computed(() => {
  const template = activeAgentCharacterTemplate.value
  if (template && characterModelMap.value[template]) {
    return normalizeRuntimeLive2dSource(characterModelMap.value[template])
  }
  return normalizeRuntimeLive2dSource(CONFIG.value.web_live2d.model.source)
})
const effectiveLive2dSource = computed(() => {
  if (backendConnected.value) {
    return resolvedLive2dSource.value || startupLive2dSource.value || DEFAULT_STARTUP_LIVE2D_SOURCE
  }
  return startupLive2dSource.value || DEFAULT_STARTUP_LIVE2D_SOURCE
})

async function loadCharacterModelMap() {
  try {
    const res = await API.listCharacterTemplates()
    characterModelMap.value = Object.fromEntries(
      (res.characters || [])
        .filter(item => item.name && item.live2dModelUrl)
        .map(item => [item.name, normalizeRuntimeLive2dSource(item.live2dModelUrl!)]),
    )
  }
  catch {
    characterModelMap.value = {}
  }
}

// ─── 悬浮球模式状态 ──────────────────────────
const floatingState = ref<FloatingState>('classic')
const isFloatingMode = computed(() => floatingState.value !== 'classic')

let unsubStateChange: (() => void) | undefined

// ─── 伪3D 视差 ────────────────────────────
const { tx: lightTx, ty: lightTy } = useParallax({ translateX: 40, translateY: 30, invert: true })

// ─── 启动界面状态 ───────────────────────────
const { progress, phase, isReady: _isReady, stallHint, startProgress, notifyModelReady, cleanup } = useStartupProgress()
const splashVisible = ref(!_splashDismissed)
const showMainContent = ref(_splashDismissed)
const modelReady = ref(false)
const titlePhaseDone = ref(false)

// 悬浮球模式下停止 BGM，退出悬浮球时恢复
watch(isFloatingMode, (floating) => {
  if (floating) {
    stopBgm()
  }
  else if (showMainContent.value) {
    playBgm('8.日常的小曲.mp3')
  }
})

// 窗口模式变化时通知后端（ProactiveVision只在悬浮球模式运行）
watch(floatingState, async (mode) => {
  try {
    await fetch('http://127.0.0.1:8001/proactive_vision/window_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
  }
  catch {
    // 忽略错误（后端可能未启动或不支持此功能）
  }
})

// Live2D 居中/过渡控制
const live2dTransform = ref('')
const live2dTransformOrigin = ref('')
const live2dTransition = ref(false)
const backendDebugVisible = ref(false)

// 记录首次 model-ready 是否已处理（避免 watch 重复触发时反复设置 transform）
let initialPositionSet = false

function onModelReady(pos: { faceX: number, faceY: number }) {
  if (!modelReady.value) {
    modelReady.value = true
    notifyModelReady()
  }

  persistStartupLive2dSource(activeLive2dSource.value)

  // splash 阶段：将 Live2D 面部居中到矩形框中央
  if (splashVisible.value && !initialPositionSet) {
    initialPositionSet = true
    // frame-mask 中心: left 50%, top 38% (见 SplashScreen.vue --frame-y)
    const cx = window.innerWidth * 0.5
    const cy = window.innerHeight * 0.38
    // 以面部为缩放原点，保证 scale 后面部仍居中
    live2dTransformOrigin.value = `${pos.faceX}px ${pos.faceY}px`
    live2dTransform.value = `translate(${cx - pos.faceX}px, ${cy - pos.faceY}px) scale(2.2)`
    // 开屏闭眼 + 身体静止
    setExpression({ ParamEyeLOpen: 0, ParamEyeROpen: 0, ParamBodyAngleX: 0, ParamAngleZ: 0 })
  }

  if (isChatPeekMode.value) {
    applyPeekExpression()
  }
}

// 模型加载完成后即显示（不等标题动画）
const live2dShouldShow = computed(() => {
  return modelReady.value
})

function onTitleDone() {
  titlePhaseDone.value = true
}

// ─── 登录弹窗状态 ───────────────────────────
const showLoginDialog = ref(false)

// ─── 后端错误弹窗状态 ──────────────────────────
const backendErrorVisible = ref(false)
const backendErrorLogs = ref('')

const isChatPeekMode = computed(() => {
  return showMainContent.value
    && !splashVisible.value
    && currentRoute.path.startsWith('/chat')
    && messageViewExpanded.value
    && !isFloatingMode.value
})

const PEEK_EXPRESSION = {
  ParamBodyAngleX: -18,
  ParamAngleZ: -14,
  ParamAngleX: 8,
  ParamEyeLOpen: 0,
  ParamEyeROpen: 1,
} as const

function applyPeekExpression() {
  setExpression({ ...PEEK_EXPRESSION })
}

const live2dPeekShellStyle = computed(() => {
  if (!isChatPeekMode.value) {
    return {
      transform: undefined,
      transformOrigin: undefined,
    }
  }
  return {
    transform: 'translate3d(-234px, -1.6vh, 0) rotate(-4deg) scale(1.05)',
    transformOrigin: '24% 72%',
  }
})

const live2dModelX = computed(() => {
  if (!isChatPeekMode.value) {
    return CONFIG.value.web_live2d.model.x
  }
  return Math.min(CONFIG.value.web_live2d.model.x, -0.17)
})

const live2dModelY = computed(() => {
  if (!isChatPeekMode.value) {
    return CONFIG.value.web_live2d.model.y
  }
  return CONFIG.value.web_live2d.model.y - 0.15
})

const live2dCombinedTransform = computed(() => {
  return live2dTransform.value
})

const live2dCombinedTransition = computed(() => {
  if (live2dTransition.value) {
    return 'transform 1.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.8s ease'
  }
  return 'opacity 0.35s ease'
})

const live2dPeekShellTransition = computed(() => {
  if (isChatPeekMode.value) {
    return 'transform 2.3s cubic-bezier(0.16, 0.84, 0.24, 1) 0.36s'
  }
  return 'transform 0.52s cubic-bezier(0.4, 0, 0.2, 1)'
})

// ─── CAS 会话失效弹窗 ──────────────────────────
const authExpiredVisible = ref(false)
const { logout: doLogout, skipLogin } = useAuth()

watch(authExpired, (expired) => {
  if (expired && !authExpiredVisible.value) {
    authExpiredVisible.value = true
  }
})

function onAuthExpiredRelogin() {
  authExpiredVisible.value = false
  authExpired.value = false
  // 抑制在途请求的 401 再次触发弹窗，直到登录成功
  setAuthExpiredSuppressed(true)
  ACCESS_TOKEN.value = ''
  doLogout()
  showLoginDialog.value = true
}

function onAuthExpiredDismiss() {
  authExpiredVisible.value = false
  authExpired.value = false
}

function openLoginDialog() {
  showLoginDialog.value = true
}

// 提供给子组件使用
provide('openLoginDialog', openLoginDialog)
proactiveNotifier.value = (source, content) => {
  toast.add({
    severity: 'info',
    summary: source,
    detail: content,
    life: 5000,
  })
}

function onSplashDismiss() {
  _splashDismissed = true
  // 开机语音已在 SplashScreen 标题出现时播放，此处不再播放
  // 已登录 → 直接进入主界面；未登录 → 显示登录弹窗
  if (isLoggedIn.value) {
    enterMainContent()
  }
  else {
    showLoginDialog.value = true
  }
}

function onLoginSuccess() {
  showLoginDialog.value = false
  setAuthExpiredSuppressed(false)
  toast.add({ severity: 'success', summary: '欢迎回来', detail: cloudUser.value?.username, life: 3000 })
  enterMainContent()
}

function onLoginSkip() {
  skipLogin()
  showLoginDialog.value = false
  setAuthExpiredSuppressed(false)
  enterMainContent()
}

function enterMainContent() {
  // 切换为日常 BGM（淡入淡出）
  playBgm('8.日常的小曲.mp3')
  // 启用过渡动画
  live2dTransition.value = true
  // 回到正常位置
  live2dTransform.value = ''
  live2dTransformOrigin.value = ''
  // 触发 SplashScreen 淡出
  splashVisible.value = false
  // 睁眼（平滑过渡）
  clearExpression()

  setTimeout(() => {
    showMainContent.value = true
  }, 200)

  setTimeout(() => {
    live2dTransition.value = false
    initialPositionSet = false
  }, 1500)
}

// ─── 会话自动恢复提示 ─────────────────────────
watch(sessionRestored, (restored) => {
  if (restored) {
    toast.add({ severity: 'info', summary: '已恢复登录状态', detail: cloudUser.value?.username, life: 3000 })
    // 如果登录弹窗已显示（splash 结束时 fetchMe 尚未完成），自动关闭并进入主界面
    if (showLoginDialog.value) {
      showLoginDialog.value = false
      setAuthExpiredSuppressed(false)
      enterMainContent()
    }
  }
})

watch(effectiveLive2dSource, (source) => {
  activeLive2dSource.value = source || DEFAULT_STARTUP_LIVE2D_SOURCE
}, { immediate: true })

// 仅在 effectiveLive2dSource 真正变化时才重新挂载 Live2dModel（销毁旧 PIXI.Application + 创建新 WebGL context）。
// 不再把 backendConnected / activeTabId / activeAgentCharacterTemplate 放进 watch：
//   - backendConnected 在后端断连重连时会 true/false 来回切换，会导致 Live2D 频繁重挂载，反复创建 WebGL context，
//     旧 context 来不及释放时会耗尽浏览器 WebGL context 配额（通常 16 个），表现为"Live2D 加载不出来"。
//   - activeTabId / activeAgentCharacterTemplate 的变化已经会通过 effectiveLive2dSource 这个 computed 反映出来，
//     这里再列一次属于重复触发。
watch(effectiveLive2dSource, () => {
  live2dRenderKey.value += 1
})

watch(backendConnected, (connected) => {
  if (connected) {
    void loadCharacterModelMap()
  }
}, { immediate: true })

watch(isChatPeekMode, (peeking) => {
  if (!showMainContent.value || splashVisible.value) {
    return
  }
  if (peeking) {
    applyPeekExpression()
    return
  }
  clearExpression()
}, { immediate: true })

useEventListener(window, 'keydown', (event) => {
  if (!event.ctrlKey || !event.shiftKey || event.key.toLowerCase() !== 'u') {
    return
  }
  event.preventDefault()
  backendDebugVisible.value = !backendDebugVisible.value
})

// ─── 卷150：全局快捷键层 + 命令面板 + 侧边栏（配置表驱动，见 composables/useGlobalHotkeys） ───
const router = useRouter()
const { paletteOpen } = useGlobalHotkeys({
  router,
  isFloating: isFloatingMode,
  onAction(kind) {
    // 上下文感知动作：先路由到目标视图，再触发该视图的新建流程。
    // 视图内部的新建函数未全局暴露，这里采用"路由 + 派发自定义事件"对接：
    // 目标视图 onMounted 监听 'lumo:quick-action' 即可响应该一次性动作（懒对接，不强耦合）。
    switch (kind) {
      case 'new-eln':
        router.push('/eln')
        window.dispatchEvent(new CustomEvent('lumo:quick-action', { detail: { kind } }))
        break
      case 'doi-import':
        router.push('/papers')
        window.dispatchEvent(new CustomEvent('lumo:quick-action', { detail: { kind } }))
        break
      case 'new-chat':
      default:
        router.push('/chat')
        window.dispatchEvent(new CustomEvent('lumo:quick-action', { detail: { kind } }))
        break
    }
  },
})

function onPaletteNavigate(to: string) {
  router.push(to)
}

function onPaletteAction(kind: 'new-eln' | 'new-chat' | 'doi-import') {
  // 命令面板的动作条目与快捷键共用同一处理
  paletteOpen.value = false
  switch (kind) {
    case 'new-eln':
      router.push('/eln')
      break
    case 'doi-import':
      router.push('/papers')
      break
    case 'new-chat':
    default:
      router.push('/chat')
      break
  }
  window.dispatchEvent(new CustomEvent('lumo:quick-action', { detail: { kind } }))
}

// ─── 全局轮询：登录后启动，登出后停止（积分刷新 + 心跳检测）───
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn && backendConnected.value) {
    startToolPolling()
  }
  else {
    stopToolPolling()
  }
}, { immediate: true })

watch(backendConnected, (connected) => {
  if (connected) {
    connectRealtimeUi()
    if (isLoggedIn.value) {
      startToolPolling()
    }
  }
  else {
    disconnectRealtimeUi()
  }
}, { immediate: true })

onMounted(() => {
  initParallax()
  startProgress()

  // 启动 BGM（非悬浮球模式时播放）
  if (!isFloatingMode.value) {
    playBgm('9.快乐的小曲.mp3')
  }

  // 全局点击音效
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    if (target.closest('button, a, [role="button"], .p-button, .p-toggleswitch, .clickable')) {
      playClickEffect()
    }
  })

  // 悬浮球模式监听
  const api = window.electronAPI
  if (api) {
    api.floating.getState().then((state) => {
      floatingState.value = state
    })
    unsubStateChange = api.floating.onStateChange((state) => {
      floatingState.value = state
    })

    // 后端连接成功后，根据持久化配置自动恢复悬浮球模式
    const stopConfigWatch = watch(backendConnected, (connected) => {
      if (connected && CONFIG.value.floating.enabled) {
        api.floating.enter()
      }
      if (connected)
        stopConfigWatch()
    })
  }

  // 后端连接成功后检查版本更新
  const stopVersionWatch = watch(backendConnected, (connected) => {
    if (!connected)
      return
    stopVersionWatch()
    void checkForUpdate().catch((error) => {
      console.warn('[VersionCheck] Startup check failed:', error)
    })
  })

  // 监听后端启动失败
  if (api?.backend) {
    api.backend.onError((payload) => {
      backendErrorLogs.value = payload.logs
      backendErrorVisible.value = true
    })
  }
})

onUnmounted(() => {
  proactiveNotifier.value = null
  destroyParallax()
  cleanup()
  stopToolPolling()
  disconnectRealtimeUi()
  unsubStateChange?.()
})
</script>

<template>
  <!-- 悬浮球模式 -->
  <FloatingView v-if="isFloatingMode" />

  <!-- 经典模式 -->
  <template v-else>
    <TitleBar />
    <!-- 卷150：全局侧边栏（可折叠，localStorage 持久化；悬浮球模式上方 v-if 已排除） -->
    <AppSidebar />
    <WindowResizeHandles :visible="showResizeHandles" :title-bar-height="isMac ? 28 : 32" />
    <Toast position="top-center" />
    <!-- 卷150：命令面板（Ctrl+K 唤起，Teleport 到 body） -->
    <CommandPalette
      v-model:open="paletteOpen"
      data-testid="command-palette-mount"
      @navigate="onPaletteNavigate"
      @action="onPaletteAction"
    />
    <div class="h-full sunflower" :style="{ paddingTop: titleBarPadding, paddingLeft: 'var(--lumo-sidebar-w, 0px)' }">
      <!-- 自定义背景层：在向日葵边框之下 -->
      <div
        v-if="hasCustomBg"
        class="custom-bg-layer"
        :style="{ backgroundImage: `url(${customBgUrl})` }"
      />
      <!-- Live2D 层：启动时 z-10（在 SplashScreen 遮罩之间），之后降到 z:0（body 背景之上、主内容之下）；论坛页隐藏 -->
      <!-- 不能用负 z-index：body/#app 有实色背景（--lumo-bg），负 z-index 元素会沉到根背景之下被完全遮挡 -->
      <!-- 必须 pointer-events-none：本层 absolute + size-full，而 .grid-container 是 static，命中测试顺序上
           画布压在所有视图内容之上，会吞掉按钮点击（如 ELN 顶栏「返回」）；模型追踪走 window 级监听，穿透不影响 -->
      <div
        v-show="!isForumRoute"
        class="absolute top-0 left-0 size-full pointer-events-none"
        :class="splashVisible ? 'z-10' : ''"
        :style="{
          zIndex: splashVisible ? undefined : 0,
          transform: live2dCombinedTransform || undefined,
          transformOrigin: live2dTransformOrigin || undefined,
          transition: live2dCombinedTransition,
          opacity: splashVisible ? (live2dShouldShow ? 1 : 0) : 1,
        }"
      >
        <img src="/assets/light.png" alt="" class="absolute right-0 bottom-0 w-80vw h-60vw op-40 -z-1 will-change-transform" :style="{ transform: `translate(${lightTx}px, ${lightTy}px)` }">
        <div
          class="absolute inset-0"
          :style="{
            transform: live2dPeekShellStyle.transform,
            transformOrigin: live2dPeekShellStyle.transformOrigin,
            transition: live2dPeekShellTransition,
          }"
        >
          <Live2dModel
            :key="live2dRenderKey"
            :source="effectiveLive2dSource"
            :x="live2dModelX"
            :y="live2dModelY"
            :width="width" :height="height"
            :scale="scale" :ssaa="CONFIG.web_live2d.ssaa"
            @model-ready="onModelReady"
          />
        </div>
      </div>

      <!-- 主内容区域 -->
      <Transition name="fade">
        <div v-if="showMainContent" class="h-full grid-container pointer-events-none" :class="isCompactRoute ? 'px-2 py-2' : 'px-1/8 py-1/12'">
          <RouterView v-slot="{ Component, route }">
            <Transition :name="route.path === '/' ? 'slide-out' : 'slide-in'">
              <component
                :is="Component"
                :key="route.fullPath"
                class="grid-item size-full pointer-events-auto"
              />
            </Transition>
          </RouterView>
        </div>
      </Transition>

      <!-- 启动界面遮罩（Transition 在父级控制淡出动画） -->
      <Transition name="splash-fade">
        <SplashScreen
          v-if="splashVisible"
          :progress="progress"
          :phase="phase"
          :model-ready="modelReady"
          :stall-hint="stallHint"
          :live2d-visible="live2dShouldShow"
          @dismiss="onSplashDismiss"
          @title-done="onTitleDone"
        />
      </Transition>

      <!-- 登录弹窗（在 SplashScreen 之上） -->
      <LoginDialog
        :visible="showLoginDialog"
        @success="onLoginSuccess"
        @skip="onLoginSkip"
      />

      <!-- 版本更新弹窗 -->
      <UpdateDialog
        :visible="showUpdateDialog"
        :info="updateInfo"
      />

      <!-- 后端启动失败弹窗 -->
      <BackendErrorDialog
        :visible="backendErrorVisible"
        :logs="backendErrorLogs"
        @update:visible="backendErrorVisible = $event"
      />

      <BackendDebugDialog
        :visible="backendDebugVisible"
        :logs="backendErrorLogs"
        @update:visible="backendDebugVisible = $event"
      />

      <!-- CAS 会话失效弹窗 -->
      <Teleport to="body">
        <Transition name="fade">
          <div v-if="authExpiredVisible" class="auth-expired-overlay">
            <div class="auth-expired-card">
              <div class="auth-expired-icon">
                &#x26A0;
              </div>
              <h3 class="auth-expired-title">
                账号验证失效
              </h3>
              <p class="auth-expired-desc">
                服务器账号资源验证失效，可能是网络波动或账号已在其他设备登录。是否重新登录？
              </p>
              <div class="auth-expired-actions">
                <button class="auth-expired-btn primary" @click="onAuthExpiredRelogin">
                  重新登录
                </button>
                <button class="auth-expired-btn secondary" @click="onAuthExpiredDismiss">
                  暂时忽略
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </Teleport>
    </div>
  </template>
</template>

<style scoped>
.sunflower {
  border-image-source: url('/assets/sunflower.9.png');
  border-image-slice: 50%;
  border-image-width: 10em;
}

.custom-bg-layer {
  position: absolute;
  inset: 0;
  z-index: auto;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  pointer-events: none;
}

.grid-container {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.grid-item {
  grid-column: 1;
  grid-row: 1;
  min-height: 0;
}

.slide-in-enter-from {
  transform: translateX(-100%);
}
.slide-in-leave-to {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-in-leave-active,
.slide-in-enter-active,
.slide-out-leave-active,
.slide-out-enter-active {
  transition: all 1s ease;
}

.slide-out-enter-from {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-out-leave-to {
  opacity: 0;
  transform: translateX(-100%);
}

/* 主内容淡入 */
.fade-enter-active {
  transition: opacity 0.8s ease;
}
.fade-enter-from {
  opacity: 0;
}

/* SplashScreen 淡出 */
.splash-fade-leave-active {
  transition: opacity 1s ease;
}
.splash-fade-leave-to {
  opacity: 0;
}
</style>

<style>
/* Teleport 到 body 的弹窗样式（不能 scoped） */
.auth-expired-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
}

.auth-expired-card {
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  padding: 32px;
  max-width: 380px;
  text-align: center;
}

.auth-expired-icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.auth-expired-title {
  color: #fff;
  font-size: 18px;
  margin: 0 0 12px;
}

.auth-expired-desc {
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 24px;
}

.auth-expired-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.auth-expired-btn {
  padding: 8px 24px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  transition: opacity 0.2s;
}

.auth-expired-btn:hover {
  opacity: 0.85;
}

.auth-expired-btn.primary {
  background: rgba(212, 175, 55, 0.9);
  color: #000;
}

.auth-expired-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
}
</style>
