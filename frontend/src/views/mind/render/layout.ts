/**
 * mind 视图 · 分区布局（扇区划分 / 圆盘半径 / 簇内目标点）。
 * 自 views/mind/renderer.ts 拆出（工单209 任务二）。
 *
 * **纯移动**：`nodes` 传参；`buildSectors` 原本重赋值闭包的 `sectors` → 改为返回新数组；
 * `typeSectorTarget` 需要的 `sectors` 由调用方传入（renderer 仍是状态所有者）。
 */
import type { SeaNode } from './types'

export interface Sector {
  type: string
  color: string
  angle: number
  count: number
  radius: number
  cx: number
  cz: number
}

// 分区圆盘半径随节点数增长——避免 500 节点还挤在 R=120 的盘里
export function layoutRadius(nodes: SeaNode[]): number {
  return 140 + Math.sqrt(nodes.length) * 22
}

export function buildSectors(nodes: SeaNode[], tc: (t: string) => string): Sector[] {
  const byType = new Map<string, number>()
  for (const n of nodes)
    byType.set(n.type, (byType.get(n.type) || 0) + 1)

  // 实体多的类型排前面，扇区角度 ∝ 该类型实体数
  const sorted = [...byType.entries()].sort((a, b) => b[1] - a[1])
  const total = nodes.length || 1
  const R = layoutRadius(nodes)

  const sectors: Sector[] = []
  let acc = -Math.PI / 2 // 12 点方向起画
  for (const [type, count] of sorted) {
    const span = (count / total) * Math.PI * 2
    const angle = acc + span / 2
    const cr = R * 0.62 // 簇心沿扇区中轴外推
    sectors.push({
      type,
      color: tc(type),
      angle,
      count,
      radius: Math.max(42, Math.sqrt(count) * 22),
      cx: Math.cos(angle) * cr,
      cz: Math.sin(angle) * cr,
    })
    acc += span
  }

  const idx = new Map(sectors.map((sc, k) => [sc.type, k]))
  for (const n of nodes)
    n.typeIndex = idx.get(n.type) ?? -1
  return sectors
}

// 簇内目标点：黄金角螺旋（比随机撒点均匀，不会抱团打架）
export function typeSectorTarget(n: SeaNode, ordinal: number, sectors: Sector[]) {
  const sc = sectors[n.typeIndex]
  if (!sc)
    return { x: 0, z: 0 }
  const k = Math.max(1, sc.count)
  const t = (ordinal + 0.5) / k
  const rr = sc.radius * Math.sqrt(t)
  const a = ordinal * 2.399963 // 黄金角
  return {
    x: sc.cx + Math.cos(a) * rr,
    z: sc.cz + Math.sin(a) * rr,
  }
}
