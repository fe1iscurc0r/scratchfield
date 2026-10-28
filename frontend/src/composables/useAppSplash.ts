import type { Ref } from 'vue'
import { ref } from 'vue'
import { isLoggedIn } from '@/composables/useAuth'

/**
 * 启动闪屏族（工单204 任务三 · App.vue 抽取步骤⑤）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md 的 splash 族。
 * 本处拥有 **5 个导出符号 + 1 个内部变量**：`splashVisible` / `showMainContent` / `titlePhaseDone` /
 * `onSplashDismiss` / `onTitleDone`，以及内部 `_splashDismissed`（原 App.vue 的 `let`，
 * 只参与两个 ref 的初始值并在 `onSplashDismiss` 里置位；非响应式，故不导出）。
 *
 * 两处对依赖图原表的校正：
 * 1. 原表把 `enterMainContent` 同时记作 splash 族的第 6 个符号**和**本步骤的外部依赖 —— 自相矛盾。
 *    定案：`enterMainContent` 留在 App.vue（18 依赖的编排汇聚点），本处只作参数接收。
 *    真正的第 6 个符号是 `onTitleDone`（原表将它归入「未归类」，但它唯一职责就是置位 splash 的
 *    `titlePhaseDone`，且由模板 `<SplashScreen @title-done>` 触发 ⇒ 属 splash）。
 * 2. 原表只列了 `enterMainContent` 一个外部依赖；实测 `onSplashDismiss` 的「未登录」分支还要
 *    `showLoginDialog`（步骤④ `useAuthDialogs` 的返回值）⇒ 参数表为
 *    `{ showLoginDialog, enterMainContent }`。
 *
 * 语义保持（只搬迁，未清理；两者在原 App.vue 里就是「只写不读」）：
 * - `titlePhaseDone`：全文件仅出现 2 处（本声明 + `onTitleDone` 赋值），模板与脚本均无读取方，
 *   疑似残留自「开机语音在标题出现时播放」那段逻辑迁入 SplashScreen 之后。
 * - `_splashDismissed`：置 `true` 之后无人再读；且它是 setup 作用域内的 `let`，跨组件实例本就不保留。
 * 是否删除属单独的清理决策，本步骤不改变任何行为。
 */

export interface AppSplashDeps {
  /** 登录弹窗可见性（来自 @/composables/useAuthDialogs，步骤④）：splash 退场时未登录则拉起它 */
  showLoginDialog: Ref<boolean>
  /** 进入主内容的编排点（必须留在 App.vue：18 依赖汇聚） */
  enterMainContent: () => void
}

/**
 * 须在 setup() 内**同步**调用，且调用点必须早于 `onModelReady`（后者读取 `splashVisible`）。
 */
export function useAppSplash({ showLoginDialog, enterMainContent }: AppSplashDeps) {
  // ─── 启动界面状态 ───────────────────────────
  let _splashDismissed = false
  const splashVisible = ref(!_splashDismissed)
  const showMainContent = ref(_splashDismissed)
  const titlePhaseDone = ref(false)

  function onTitleDone() {
    titlePhaseDone.value = true
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

  return {
    splashVisible,
    showMainContent,
    // 原代码中只写不读（见文件头说明）；保留以维持 API 完整，App.vue 未解构
    titlePhaseDone,
    onSplashDismiss,
    onTitleDone,
  }
}
