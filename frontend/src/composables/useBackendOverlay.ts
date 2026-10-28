import { useEventListener } from '@vueuse/core'
import { onMounted, ref } from 'vue'

/**
 * 后端日志浮层（工单204 任务三 · App.vue 抽取步骤②）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md 的 backend-overlay 族。
 * ⚠️ 与依赖图原分组的偏差：`onPaletteAction` / `onPaletteNavigate` 实际依赖
 * `paletteOpen`（useGlobalHotkeys 返回值）+ `router`，语义上是**命令面板**集成而非后端浮层，
 * 故留在 App.vue，不进本 composable。
 *
 * 语义保持：原 App.vue 不退订 `backend.onError`（Electron 桥随应用存活），此处同样不退订。
 */
export function useBackendOverlay() {
  const backendDebugVisible = ref(false)
  const backendErrorVisible = ref(false)
  const backendErrorLogs = ref('')

  // Ctrl+Shift+U 切换后端调试浮层
  useEventListener(window, 'keydown', (event) => {
    if (!event.ctrlKey || !event.shiftKey || event.key.toLowerCase() !== 'u') {
      return
    }
    event.preventDefault()
    backendDebugVisible.value = !backendDebugVisible.value
  })

  // 监听后端启动失败（Electron preload 桥；浏览器下无 electronAPI 自然跳过）
  onMounted(() => {
    const api = window.electronAPI
    if (!api?.backend)
      return
    api.backend.onError((payload) => {
      backendErrorLogs.value = payload.logs
      backendErrorVisible.value = true
    })
  })

  return { backendDebugVisible, backendErrorVisible, backendErrorLogs }
}
