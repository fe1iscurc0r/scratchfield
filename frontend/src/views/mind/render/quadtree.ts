/**
 * mind 视图 · Barnes-Hut 四叉树（n>150 自动切换，O(n²) → O(n log n)）。
 * 自 views/mind/renderer.ts 拆出（工单209 任务二）。
 *
 * **纯移动**：7 个内部函数逐字节搬运、**零改动** —— 原本闭包在 createMindRenderer 内，
 * 这里改为闭包在 `createQuadTree(nodes, cfg)` 工厂内（同样的闭包语义与调用序）。
 */
import type { SeaNode } from './types'

export interface QuadtreeCfg {
  /** 本模块只读取 cfg.spread */
  spread: number
}

export interface QuadNode {
  x: number
  z: number
  half: number
  mass: number
  cx: number
  cz: number
  body: number // 单体叶子 → nodes 下标；已细分 → -1
  nw: QuadNode | null
  ne: QuadNode | null
  sw: QuadNode | null
  se: QuadNode | null
}

export interface QuadTreeApi {
  build: () => QuadNode | null
  repel: (root: QuadNode | null, i: number, alpha: number) => void
}

export function createQuadTree(nodes: SeaNode[], cfg: QuadtreeCfg): QuadTreeApi {
// ── Barnes-Hut 四叉树（任务B-6：n>150 自动切换，O(n²) → O(n log n)） ──

  function quadCreate(x: number, z: number, half: number): QuadNode {
    return { x, z, half, mass: 0, cx: 0, cz: 0, body: -1, nw: null, ne: null, sw: null, se: null }
  }

  function quadSubdivide(q: QuadNode) {
    if (q.nw)
      return
    const h = q.half / 2
    q.nw = quadCreate(q.x - h, q.z - h, h)
    q.ne = quadCreate(q.x + h, q.z - h, h)
    q.sw = quadCreate(q.x - h, q.z + h, h)
    q.se = quadCreate(q.x + h, q.z + h, h)
  }

  function quadChildOf(q: QuadNode, px: number, pz: number): QuadNode {
    if (px < q.x)
      return pz < q.z ? q.nw! : q.sw!
    return pz < q.z ? q.ne! : q.se!
  }

  function quadInsert(q: QuadNode, i: number, depth: number) {
    const n = nodes[i]!
    // 空叶子 → 直接放
    if (q.mass === 0 && q.nw === null) {
      q.body = i
      q.mass = 1
      q.cx = n.px
      q.cz = n.pz
      return
    }
    if (depth > 14)
      return
    // 已占用叶子 → 下沉
    if (q.body !== -1) {
      const old = q.body
      q.body = -1
      quadSubdivide(q)
      quadInsert(quadChildOf(q, nodes[old]!.px, nodes[old]!.pz), old, depth + 1)
      q.mass = 0
    }
    else {
      quadSubdivide(q)
    }
    quadInsert(quadChildOf(q, n.px, n.pz), i, depth + 1)
    quadAccumulate(q)
  }

  // 自底向上重算质心与质量
  function quadAccumulate(q: QuadNode) {
    if (q.body !== -1)
      return
    let m = 0
    let sx = 0
    let sz = 0
    for (const c of [q.nw, q.ne, q.sw, q.se]) {
      if (!c || c.mass === 0)
        continue
      m += c.mass
      sx += c.cx * c.mass
      sz += c.cz * c.mass
    }
    q.mass = m
    q.cx = m > 0 ? sx / m : q.x
    q.cz = m > 0 ? sz / m : q.z
  }

  function quadBuild(): QuadNode | null {
    if (nodes.length === 0)
      return null
    let minX = Infinity
    let maxX = -Infinity
    let minZ = Infinity
    let maxZ = -Infinity
    for (const n of nodes) {
      if (n.px < minX)
        minX = n.px
      if (n.px > maxX)
        maxX = n.px
      if (n.pz < minZ)
        minZ = n.pz
      if (n.pz > maxZ)
        maxZ = n.pz
    }
    const root = quadCreate(
      (minX + maxX) / 2,
      (minZ + maxZ) / 2,
      Math.max(1, Math.max(maxX - minX, maxZ - minZ) / 2 + 1),
    )
    for (let i = 0; i < nodes.length; i++)
      quadInsert(root, i, 0)
    return root
  }

  // θ=0.9 是 BH 的经典折中：越大越快越糙
  const BH_THETA = 0.9
  const BH_THETA2 = BH_THETA * BH_THETA

  function quadRepel(q: QuadNode | null, i: number, alpha: number) {
    if (!q || q.mass === 0)
      return
    const n = nodes[i]!
    if (q.body === i) // 自己斥自己没意义
      return
    const dx = q.cx - n.px
    const dz = q.cz - n.pz
    let d2 = dx * dx + dz * dz
    if (d2 < 4)
      d2 = 4
    const d = Math.sqrt(d2)
    const f = cfg.spread * alpha / d2
    const isLeaf = q.body !== -1
    const s = (q.half * 2) / d
    if (isLeaf || s * s < BH_THETA2) {
      // 单体，或"够远"→ 整块当单体
      n.vx -= dx / d * f
      n.vz -= dz / d * f
      return
    }
    quadRepel(q.nw, i, alpha)
    quadRepel(q.ne, i, alpha)
    quadRepel(q.sw, i, alpha)
    quadRepel(q.se, i, alpha)
  }

  return { build: quadBuild, repel: quadRepel }
}
