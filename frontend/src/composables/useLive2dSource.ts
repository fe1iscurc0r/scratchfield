import { computed, ref, watch } from 'vue'
import API from '@/api/core'
import { backendConnected, CONFIG } from '@/utils/config'
import { activeTabId, agentContacts, tabs } from '@/utils/session'
import { isElectron } from './useWindowChrome'

/**
 * Live2D 启动源链（工单204 任务三 · App.vue 抽取步骤③）
 *
 * 依据依赖图 docs/app-vue-state-graph-2026-10-07.md 的 live2d 族「源缓存链」12 符号：
 * LIVE2D_SOURCE_CACHE_KEY / DEFAULT_STARTUP_LIVE2D_SOURCE / normalizeRuntimeLive2dSource /
 * readCachedStartupLive2dSource / persistStartupLive2dSource / startupLive2dSource /
 * activeLive2dSource / activeAgentCharacterTemplate / resolvedLive2dSource /
 * effectiveLive2dSource / characterModelMap / loadCharacterModelMap。
 *
 * ⚠️ 与依赖图分组的一处校正：`isElectron` 在步骤①已升级为 useWindowChrome 的**模块常量**
 * （非响应式状态、全程不变），直接 import 比"作参数注入"更贴合代码现实 ⇒ 本 composable **零参数**。
 *
 * 留归 App.vue 不动的：`enterMainContent`（18 依赖的编排汇聚点）。
 * 本文件头原记「`live2dRenderKey` 属渲染/舞台族边界、其 watch 仍留在 App.vue」——
 * 已于步骤⑥ 连同该 watch 一并迁入 `@/composables/useLive2dStage`（此处更正以避免过期注释）。
 */
export function useLive2dSource() {
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

  // ⚠️ 声明顺序：`startupLive2dSource` 必须先于引用它的 `persistStartupLive2dSource`
  // （原 App.vue 里两者顺序相反，靠函数声明提升"碰巧"能跑，但触发
  //  eslint `ts/no-use-before-define`）。此处只是把声明提前，逻辑零改动。
  const startupLive2dSource = ref(readCachedStartupLive2dSource())

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

  const activeLive2dSource = ref(startupLive2dSource.value)
  const characterModelMap = ref<Record<string, string>>({})
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

  // 生效源变化 → 同步当前活跃源（启动缓存回写用）
  watch(effectiveLive2dSource, (source) => {
    activeLive2dSource.value = source || DEFAULT_STARTUP_LIVE2D_SOURCE
  }, { immediate: true })

  // 后端连上才有角色模板表可查
  watch(backendConnected, (connected) => {
    if (connected) {
      void loadCharacterModelMap()
    }
  }, { immediate: true })

  return {
    LIVE2D_SOURCE_CACHE_KEY,
    DEFAULT_STARTUP_LIVE2D_SOURCE,
    normalizeRuntimeLive2dSource,
    readCachedStartupLive2dSource,
    persistStartupLive2dSource,
    startupLive2dSource,
    activeLive2dSource,
    characterModelMap,
    activeAgentCharacterTemplate,
    resolvedLive2dSource,
    effectiveLive2dSource,
    loadCharacterModelMap,
  }
}
