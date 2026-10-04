// 记忆云海聊天探索域（卷190-B5：从 MindView.vue setup 纯搬移）。
// 双模式（工单 B-5 / AGENTiGraph）：说一句自然语言 → 剔动词助词得实体词 → 服务端 q 搜索 → 子图聚焦。
import type { Ref } from 'vue'
import { ref } from 'vue'

export interface MindChatDeps {
  /** 写入搜索框（chatQuery 会把抽出的实体词回填） */
  searchQuery: Ref<string>
  /** 跑一次搜索（由数据层提供） */
  runSearch: () => Promise<void>
  /** 引擎：取度数最高的簇设为焦点 */
  focusTopByWeight: () => string | null
  /** 焦点回写到壳（同步图例高亮） */
  syncFocus: (t: string | null) => void
}

export function useMindChat(deps: MindChatDeps) {
  const { searchQuery, runSearch, focusTopByWeight, syncFocus } = deps

  const chatMode = ref(false)
  const chatInput = ref('')

  function extractEntityTerm(raw: string): string {
    const cleaned = raw
      .replace(/[看一下寻找查展示显帮我请把的了呢吗啊关于记忆有什么哪些是和与]/g, ' ')
      .replace(/[^\p{L}\p{N}]+/gu, ' ')
      .trim()
    return cleaned || raw
  }

  async function chatQuery() {
    const raw = chatInput.value.trim()
    if (!raw)
      return
    const term = extractEntityTerm(raw)
    searchQuery.value = term
    chatMode.value = true
    await runSearch()
    // 子图聚焦：命中结果里度数最高的那个簇自动成为焦点
    const top = focusTopByWeight()
    syncFocus(top)
  }

  return {
    chatMode,
    chatInput,
    extractEntityTerm,
    chatQuery,
  }
}
