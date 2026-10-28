import type { ToastServiceMethods } from 'primevue/toastservice'
import { provide, ref, watch } from 'vue'
import { ACCESS_TOKEN, authExpired, setAuthExpiredSuppressed } from '@/api'
import { cloudUser, sessionRestored, useAuth } from '@/composables/useAuth'

/**
 * 登录弹窗 + CAS 会话失效弹窗族（工单204 任务三 · App.vue 抽取步骤④）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md 的 auth 族（7 符号）：
 * `showLoginDialog` / `authExpiredVisible` / `openLoginDialog` / `onAuthExpiredRelogin` /
 * `onAuthExpiredDismiss` / `onLoginSuccess` / `onLoginSkip`。
 *
 * 外部依赖作参数传入（不反向 import App.vue）：
 * - `toast`：App.vue 的 `useToast()` 实例。模板里还有 `<Toast />` 组件，实例必须由 App.vue 持有。
 * - `enterMainContent`：进入主内容的**编排汇聚点**（自身依赖 18 个符号），依赖图定案必须留在 App.vue。
 *   它在 App.vue 中是函数声明（提升），故本处可以安全地提前持有其引用。
 *
 * 留在 App.vue 的相邻符号（不属本 composable）：`onSplashDismiss` / `enterMainContent`（splash 族，步骤⑤）、
 * `proactiveNotifier` 赋值（非 auth 语义，只是恰好相邻）。
 *
 * 行为保持说明：`useAuth()` 的首次调用会触发一次 `fetchMe()`（模块级 `_initFetched` 守卫）。
 * 抽取后该调用从 setup 中段提前到前段，但结果经网络异步落地（`await coreApi.authMe()`），
 * setup 内的可观察顺序不变。
 */

export interface AuthDialogsDeps {
  /** App.vue 的 useToast() 实例（模板 <Toast /> 的宿主，故由调用方持有） */
  toast: ToastServiceMethods
  /** 进入主内容的编排点（必须留在 App.vue：18 依赖汇聚） */
  enterMainContent: () => void
}

/**
 * 须在 setup() 内**同步**调用：内部 `provide('openLoginDialog', ...)` 依赖组件实例上下文。
 */
export function useAuthDialogs({ toast, enterMainContent }: AuthDialogsDeps) {
  // ─── 登录弹窗状态 ───────────────────────────
  const showLoginDialog = ref(false)

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

  return {
    showLoginDialog,
    authExpiredVisible,
    // 已 provide 给子组件；App.vue 自身不引用它，返回值保留为完整 API
    openLoginDialog,
    onAuthExpiredRelogin,
    onAuthExpiredDismiss,
    onLoginSuccess,
    onLoginSkip,
  }
}
