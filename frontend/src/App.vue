<script lang="ts">
// 模块级标记，HMR 重挂载时不会重置
</script>

<script setup lang="ts">
import type { FloatingState } from '@/electron.d'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import BackendDebugDialog from '@/components/BackendDebugDialog.vue'
import BackendErrorDialog from '@/components/BackendErrorDialog.vue'
import CommandPalette from '@/components/CommandPalette.vue'
import LoginDialog from '@/components/LoginDialog.vue'
import SplashScreen from '@/components/SplashScreen.vue'
import TitleBar from '@/components/TitleBar.vue'
import UpdateDialog from '@/components/UpdateDialog.vue'
import WindowResizeHandles from '@/components/WindowResizeHandles.vue'
import { useAppSplash } from '@/composables/useAppSplash'
import { playBgm, playClickEffect, stopBgm } from '@/composables/useAudio'
import { isLoggedIn } from '@/composables/useAuth'
import { useAuthDialogs } from '@/composables/useAuthDialogs'
import { useBackendOverlay } from '@/composables/useBackendOverlay'
import { useBackground } from '@/composables/useBackground'
import { useGlobalHotkeys } from '@/composables/useGlobalHotkeys'
import { useLive2dSource } from '@/composables/useLive2dSource'
import { useLive2dStage } from '@/composables/useLive2dStage'
import { useParallax } from '@/composables/useParallax'
import { connectRealtimeUi, disconnectRealtimeUi } from '@/composables/useRealtimeUi'
import { useStartupProgress } from '@/composables/useStartupProgress'
import { startToolPolling, stopToolPolling } from '@/composables/useToolStatus'
import { checkForUpdate, showUpdateDialog, updateInfo } from '@/composables/useVersionCheck'
import { isMac, useWindowChrome } from '@/composables/useWindowChrome'
import { backendConnected, CONFIG } from '@/utils/config'
import { clearExpression } from '@/utils/live2dController'
import { destroyParallax, initParallax } from '@/utils/parallax'
import { proactiveNotifier } from '@/utils/session'
import FloatingView from '@/views/FloatingView.vue'

// 窗口 chrome 族已抽至 @/composables/useWindowChrome（工单204 任务三步骤①）：
// isElectron / isMac 为模块常量（上方 import），isMaximized / showResizeHandles / titleBarPadding
// 依赖 isFloatingMode（floating 族，L189 定义）→ 在其后调用。
// Live2D 启动源链已抽至 @/composables/useLive2dSource（工单204 任务三步骤③）：
// 缓存键 / 默认源 / 源归一 / 启动缓存读写 / 角色模板源解析 共 12 符号，零参数。
const { persistStartupLive2dSource, activeLive2dSource, effectiveLive2dSource } = useLive2dSource()

const toast = useToast()

const currentRoute = useRoute()
// KnowledgeView 使用紧凑布局（无大 padding），因为内部已有自己的分栏布局。
// 原先这里还有一项 isForumRoute（currentRoute.path.startsWith('/forum')）——
// 随论坛下线，main.ts 里 /forum 与 /forum/:pathMatch(.*)* 都成了 redirect:'/'，
// vue-router 在解析期就把目标改写成 '/'，该 computed **恒为 false**（连带模板上的
// v-show 恒真）。按「不留恒假守卫」清掉；若论坛复活需连同本文件一起恢复，
// tests/navTargetIntegrity.test.ts 有一条测试会在复活时失败并提醒。
const isCompactRoute = computed(() => currentRoute.path.startsWith('/knowledge'))

// ── 自定义背景 ──
const { activeBackground, getActiveBackgroundUrl } = useBackground()
const hasCustomBg = computed(() => !!activeBackground.value)
const customBgUrl = computed(() => getActiveBackgroundUrl())

// ─── 悬浮球模式状态 ──────────────────────────
const floatingState = ref<FloatingState>('classic')
const isFloatingMode = computed(() => floatingState.value !== 'classic')

// 窗口 chrome（步骤①）：浮动模式态由 floating 族持有，作参数注入
const { showResizeHandles, titleBarPadding } = useWindowChrome(isFloatingMode)

let unsubStateChange: (() => void) | undefined

// ─── 伪3D 视差 ────────────────────────────
const { tx: lightTx, ty: lightTy } = useParallax({ translateX: 40, translateY: 30, invert: true })

// 登录弹窗 / CAS 会话失效弹窗族已抽至 @/composables/useAuthDialogs（工单204 任务三步骤④）：
// 7 符号 = showLoginDialog / authExpiredVisible / openLoginDialog / onAuthExpiredRelogin /
//          onAuthExpiredDismiss / onLoginSuccess / onLoginSkip。
// 此处解构 6 个（openLoginDialog 由该 composable provide 给子组件，App.vue 自身不引用）。
// enterMainContent 是函数声明（提升），故可在此提前传引用；它必须留在 App.vue（18 依赖的编排汇聚点）。
// ⚠️ 顺序不变量（③ ≺ ⑥、④ ≺ ⑤ ≺ ⑥）：④ 必须先于 ⑤（⑤ 的 onSplashDismiss 需要 showLoginDialog）；
//    ⑤ 必须先于 ⑥（⑥ 内部的 onModelReady 读取 splashVisible）；③ 必须先于 ⑥（⑥ 消费源链返回值）。
//    步骤⑤ 曾把该调用点从原 L160 前移至此；步骤⑥ 又新增了「⑤ ≺ ⑥」这一约束。
const {
  showLoginDialog,
  authExpiredVisible,
  onAuthExpiredRelogin,
  onAuthExpiredDismiss,
  onLoginSuccess,
  onLoginSkip,
} = useAuthDialogs({ toast, enterMainContent })

// ─── 启动界面状态 ───────────────────────────
const { progress, phase, isReady: _isReady, stallHint, startProgress, notifyModelReady, cleanup } = useStartupProgress()
// 启动闪屏族已抽至 @/composables/useAppSplash（工单204 任务三步骤⑤）：
// 拥有 5 导出符号 = splashVisible / showMainContent / titlePhaseDone / onSplashDismiss / onTitleDone
//              + 内部 _splashDismissed（原 let，只参与 ref 初始值与 onSplashDismiss 置位，不导出）。
// 此处解构 4 个；titlePhaseDone（原代码里只写不读）未解构，留在 composable 内保持原语义。
const { splashVisible, showMainContent, onSplashDismiss, onTitleDone } = useAppSplash({ showLoginDialog, enterMainContent })

// Live2D 渲染舞台族已抽至 @/composables/useLive2dStage（工单204 任务三步骤⑥，本任务最后一项）：
// 拥有 20 符号 = Live2dModel（异步组件；含 Cubism 核心须在 import 前注入的加载顺序硬约束）/
//   width / height / scale（useWindowSize）/ live2dRenderKey / modelReady /
//   live2dTransform / live2dTransformOrigin / live2dTransition / initialPositionSet /
//   onModelReady / live2dShouldShow / isChatPeekMode / PEEK_EXPRESSION / applyPeekExpression /
//   live2dPeekShellStyle / live2dModelX / live2dModelY / live2dCombinedTransform /
//   live2dCombinedTransition / live2dPeekShellTransition，外加随族迁入的两个 watch。
// 此处解构 18 个（isChatPeekMode / PEEK_EXPRESSION / applyPeekExpression 为族内私有，App.vue 零引用）。
// ⚠️ 顺序不变量（③ ≺ ⑥、④ ≺ ⑤ ≺ ⑥）：⑥ 读取 ⑤ 的 splashVisible / showMainContent，
//    故必须晚于 ⑤ 调用；⑥ 内部的 onModelReady 亦读取 splashVisible，这取代了步骤⑤ 原先
//    「splashVisible 必须早于 onModelReady 声明」的表述。⑤ ≺ ⑥ 同时保证 isChatPeekMode 的
//    immediate watch 在依赖就绪后才注册（启动时命中守卫直接 return，与原行为一致）。
// 写穿透（与 ⑤ 同型）：下方 enterMainContent（函数声明，提升）会写本族的 live2dTransition /
//    live2dTransform / live2dTransformOrigin / initialPositionSet。
const {
  Live2dModel,
  width,
  height,
  scale,
  live2dRenderKey,
  modelReady,
  live2dTransform,
  live2dTransformOrigin,
  live2dTransition,
  initialPositionSet,
  onModelReady,
  live2dShouldShow,
  live2dPeekShellStyle,
  live2dModelX,
  live2dModelY,
  live2dCombinedTransform,
  live2dCombinedTransition,
  live2dPeekShellTransition,
} = useLive2dStage({
  splashVisible,
  showMainContent,
  currentRoute,
  isFloatingMode,
  effectiveLive2dSource,
  activeLive2dSource,
  persistStartupLive2dSource,
  notifyModelReady,
})

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

proactiveNotifier.value = (source, content) => {
  toast.add({
    severity: 'info',
    summary: source,
    detail: content,
    life: 5000,
  })
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
    initialPositionSet.value = false
  }, 1500)
}

// 后端日志浮层（步骤②）：状态 + Ctrl+Shift+U 监听 + onError 订阅，见 composables/useBackendOverlay
const { backendDebugVisible, backendErrorVisible, backendErrorLogs } = useBackendOverlay()

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
      <!-- Live2D 层：启动时 z-10（在 SplashScreen 遮罩之间），之后降到 z:0（body 背景之上、主内容之下） -->
      <!-- 不能用负 z-index：body/#app 有实色背景（--lumo-bg），负 z-index 元素会沉到根背景之下被完全遮挡 -->
      <!-- 必须 pointer-events-none：本层 absolute + size-full，而 .grid-container 是 static，命中测试顺序上
           画布压在所有视图内容之上，会吞掉按钮点击（如 ELN 顶栏「返回」）；模型追踪走 window 级监听，穿透不影响 -->
      <div
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
