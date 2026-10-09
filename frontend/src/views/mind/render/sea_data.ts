import type { Ref } from 'vue'
import type { GraphSummaryHub } from '../renderer'
import type { MindState } from './state'
/**
 * mind 视图 · 数据构建（工单209 任务二第二批）。
 * buildSeaData：五元组 → 节点/连线/颜色表（分页 + hub 权重）。
 */
import type { Quintuple, SeaNode } from './types'
import { GRAPH_PAGE_SIZE, WEIGHT_MAX } from './constants'

export function buildSeaData(
  S: MindState,
  quints: Quintuple[],
  tc: (t: string) => string,
  graphSummary: Ref<{ top_entities?: GraphSummaryHub[] } | null>,
) {
  const degreeMap = new Map<string, number>()
  const nodeMap = new Map<string, { type: string }>()

  for (const q of quints) {
    if (!nodeMap.has(q.subject))
      nodeMap.set(q.subject, { type: q.subjectType })
    if (!nodeMap.has(q.object))
      nodeMap.set(q.object, { type: q.objectType })
    degreeMap.set(q.subject, (degreeMap.get(q.subject) || 0) + 1)
    degreeMap.set(q.object, (degreeMap.get(q.object) || 0) + 1)
  }

  // 度数下沉（工单 A-3）：后端已算好 degree 就直接用。
  // 分页后本页只有部分边，自算度数会把 hub 算小。
  for (const q of quints) {
    if (q.degree === undefined)
      continue
    if ((degreeMap.get(q.subject) ?? 0) < q.degree)
      degreeMap.set(q.subject, q.degree)
    if ((degreeMap.get(q.object) ?? 0) < q.degree)
      degreeMap.set(q.object, q.degree)
  }

  // 超一屏上限才截断；同时强制保留 summary.top_entities 里的 hub
  let selectedIds: Set<string>
  if (nodeMap.size > GRAPH_PAGE_SIZE) {
    const sorted = [...degreeMap.entries()].sort((a, b) => b[1] - a[1])
    selectedIds = new Set(sorted.slice(0, GRAPH_PAGE_SIZE).map(e => e[0]))
  }
  else {
    selectedIds = new Set(nodeMap.keys())
  }
  for (const hub of graphSummary.value?.top_entities ?? []) {
    if (selectedIds.has(hub.id) || !nodeMap.has(hub.id))
      continue
    degreeMap.set(hub.id, Math.max(degreeMap.get(hub.id) ?? 0, hub.degree))
    selectedIds.add(hub.id)
  }

  // Reset color map
  S.cmap = {}
  S.cidx = 0

  const maxDegree = Math.max(...[...degreeMap.values()], 1)
  S.nodes = []
  const nm = new Map<string, SeaNode>()
  for (const id of selectedIds) {
    const info = nodeMap.get(id)!
    const degree = degreeMap.get(id) || 1
    const weight = Math.round((degree / maxDegree) * WEIGHT_MAX * 10) / 10
    const n: SeaNode = {
      id,
      type: info.type,
      weight: Math.max(0.3, weight),
      px: 0,
      py: 0,
      pz: 0,
      vx: 0,
      vz: 0,
      swayA: 0,
      swayF: 0,
      swayAmp: 0,
      swayAx: 0,
      swayFx: 0,
      swayAmpX: 0,
      typeIndex: -1,
      revealAt: 0,
    }
    S.nodes.push(n)
    nm.set(id, n)
    tc(info.type)
  }

  S.links = []
  for (const q of quints) {
    const src = nm.get(q.subject)
    const tgt = nm.get(q.object)
    if (src && tgt)
      S.links.push({ src, tgt, relation: q.predicate })
  }

  const _types = [...new Set(S.nodes.map(n => n.type))]
  const _counts: Record<string, number> = {}
  for (const n of S.nodes)
    _counts[n.type] = (_counts[n.type] || 0) + 1
  S.cb.onNodeCountChange(S.nodes.length, quints.length, S.sectors.length, _types, _counts)

  // init* 系列由调用方（renderer）在 buildSeaData 返回后执行——闭包函数不跨模块
}
