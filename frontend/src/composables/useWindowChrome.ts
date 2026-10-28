import type { Ref } from 'vue'
import { computed } from 'vue'
import { useElectron } from './useElectron'

// 环境常量（模块级）：App.vue 的 live2d 源归一链在 setup 极早期就要用 isElectron，
// 且二者在整个生命周期内不会变 —— 模块常量与 useAuth.ts 的模块级导出同款风格。
export const isElectron = !!window.electronAPI
// macOS hiddenInset 标题栏 28px，Windows/Linux 自绘标题栏 32px
export const isMac = window.electronAPI?.platform === 'darwin'

/**
 * 窗口 chrome（工单204 任务三 · App.vue 抽取步骤①）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md：window/floating 族 5 符号
 * （isElectron / isMac / isMaximized / showResizeHandles / titleBarPadding）零内部耦合，
 * 是抽取风险最低的一族。
 *
 * 外部依赖：`isFloatingMode`（浮动模式态，App.vue 的 floating 族持有）——按依赖图约定作参数注入，
 * 不把路由/浮动逻辑拖进本 composable。
 */
export function useWindowChrome(isFloatingMode: Ref<boolean>) {
  const { isMaximized } = useElectron()

  // Electron 窗口、非浮动模式、非最大化时才显示四角 resize 手柄
  const showResizeHandles = computed(() => isElectron && !isFloatingMode.value && !isMaximized.value)

  // macOS hiddenInset title bar is 28px, Windows/Linux custom title bar is 32px
  const titleBarPadding = isElectron ? (isMac ? '28px' : '32px') : '0px'

  return { isMaximized, showResizeHandles, titleBarPadding }
}
