import type { MindState } from './state'
/**
 * mind 视图 · 可见性/LOD 簇（工单209 任务二第二批）。
 */
import type { SeaNode } from './types'

export const LOD_FAR = 'far'
export const LOD_MID = 'mid'
export const LOD_NEAR = 'near'
export const HUB_TOPN = 50

export function syncFocusFromCanvas(S: MindState): void {
  S.cb.onFocusChange(S.focusType)
}

export function lodLevel(S: MindState): string {
  if (S.selected)
    return LOD_NEAR
  if (S.focusType)
    return LOD_MID
  return LOD_FAR
}

export function hubSet(S: MindState): Set<SeaNode> {
  const sorted = [...S.nodes].sort((a, b) => b.weight - a.weight)
  return new Set(sorted.slice(0, HUB_TOPN))
}

export function neighborhood(S: MindState, n: SeaNode): Set<SeaNode> {
  const s = new Set<SeaNode>([n])
  for (const l of S.links) {
    if (l.src === n)
      s.add(l.tgt)
    if (l.tgt === n)
      s.add(l.src)
  }
  return s
}

export function visibility(S: MindState): Map<SeaNode, number> {
  const vis = new Map<SeaNode, number>()
  const lv = lodLevel(S)

  if (lv === LOD_FAR) {
    const hubs = hubSet(S)
    for (const n of S.nodes)
      vis.set(n, hubs.has(n) ? 1 : 0.22)
    return vis
  }

  if (lv === LOD_MID) {
    for (const n of S.nodes)
      vis.set(n, n.type === S.focusType ? 1 : 0.3)
    return vis
  }

  const focus = S.selected!
  const nb = neighborhood(S, focus)
  for (const n of S.nodes) {
    if (n === focus)
      vis.set(n, 1)
    else if (nb.has(n))
      vis.set(n, 0.95)
    else if (n.type === focus.type)
      vis.set(n, 0.5)
    else
      vis.set(n, 0.12)
  }
  return vis
}
