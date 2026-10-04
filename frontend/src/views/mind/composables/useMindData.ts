import type { Ref } from 'vue'
import type { RendererApi } from '../renderer'
// 记忆云海数据域（卷190-B5：从 MindView.vue setup 纯搬移）。
// 只负责「取数 + 落到引擎」，渲染细节全部在 renderer.ts。
import type { GraphSummary } from '@/api/core'
import { ref } from 'vue'
import API from '@/api/core'

const GRAPH_PAGE_SIZE = 500

export interface MindDataDeps {
  renderer: Ref<RendererApi | null>
  graphSummary: Ref<GraphSummary | null>
}

export function useMindData(deps: MindDataDeps) {
  const { renderer, graphSummary } = deps

  const loading = ref(true)
  const errorMsg = ref('')
  const searchQuery = ref('')
  const nodeCount = ref(0)
  const quintupleCount = ref(0)
  const totalQuintuples = ref(0)

  /** 图聚合摘要（卷148 新增端点）：给骨架/分区/束宽用，不拉全量 */
  async function loadSummary() {
    try {
      graphSummary.value = await API.getGraphSummary(20)
    }
    catch {
      // 后端未升级时不报错：骨架退化为「按本页度数自算」
      graphSummary.value = null
    }
  }

  async function loadData() {
    loading.value = true
    errorMsg.value = ''
    renderer.value?.setFocusType(null)
    try {
      // 走分页端点：后端负责截断/计数，前端拿一屏上限
      const [res] = await Promise.all([
        API.getQuintuples({ offset: 0, limit: GRAPH_PAGE_SIZE, orderBy: 'degree', withDegree: true }),
        loadSummary(),
      ])
      const quints = res.quintuples ?? []
      totalQuintuples.value = res.total ?? quints.length
      if (quints.length > 0) {
        renderer.value?.buildSeaData(quints)
      }
      else {
        renderer.value?.buildSeaData([])
      }
      quintupleCount.value = quints.length
    }
    catch (e: any) {
      errorMsg.value = e.message || '加载失败'
    }
    finally {
      loading.value = false
    }
  }

  async function search() {
    if (!searchQuery.value.trim()) {
      await loadData()
      return
    }
    loading.value = true
    errorMsg.value = ''
    try {
      // 服务端搜索（q 参数），而非拉全量再前端过滤
      const res = await API.getQuintuples({
        offset: 0,
        limit: GRAPH_PAGE_SIZE,
        q: searchQuery.value.trim(),
        orderBy: 'degree',
        withDegree: true,
      })
      const quints = res.quintuples ?? []
      totalQuintuples.value = res.total ?? quints.length
      if (quints.length > 0) {
        renderer.value?.buildSeaData(quints)
      }
      else {
        renderer.value?.buildSeaData([])
      }
      quintupleCount.value = quints.length
    }
    catch (e: any) {
      errorMsg.value = e.message || '搜索失败'
    }
    finally {
      loading.value = false
    }
  }

  return {
    loading,
    errorMsg,
    searchQuery,
    nodeCount,
    quintupleCount,
    totalQuintuples,
    loadSummary,
    loadData,
    search,
  }
}
