// 记忆云海 3D 渲染引擎（卷190-B5：从 MindView.vue 整块搬出，零语义改动）。
// 全部绘制状态私在工厂闭包内；壳只通过 RendererApi 交互，
// 需要壳侧响应的两处（选中节点 / 统计刷新）走 callbacks 回调。
import type { Ref } from 'vue'
import type { Quintuple } from './render/types'
import { SURFACE_H } from './render/constants'
import {
  initFlow,
  initParticles,
  initPlankton,
  initRays,
  simFlow,
  simParticles,
  simPlankton,
} from './render/effects'
import { findNode as findNodeImpl, setupEvents } from './render/interaction'
import { buildSectors, typeSectorTarget } from './render/layout'
import { createQuadTree } from './render/quadtree'
import { draw as drawPass } from './render/render_pass'
import { buildSeaData } from './render/sea_data'
import { createMindState } from './render/state'

export interface GraphSummaryHub {
  id: string
  degree: number
}

export interface NodeInfo {
  id: string
  type: string
  weight: number
  outCount: number
  inCount: number
  relations: string[]
}

export interface RendererDeps {
  /** 画布元素 ref（壳持有） */
  canvasRef: Ref<HTMLCanvasElement | undefined>
  /** 图聚合摘要（壳加载后写入，引擎读 top_entities 保 hub） */
  graphSummary: Ref<{ top_entities?: GraphSummaryHub[] } | null>
  /** 节点数变化时通知壳（壳据此刷图例/统计） */
  onNodeCountChange: (count: number, quintupleCount: number, sectorCount: number, types: string[], typeCounts: Record<string, number>) => void
  /** 引擎内选中节点时通知壳（点扇区标题清除选中会传 null） */
  onSelect: (info: NodeInfo | null) => void
  /** 引擎内部改动聚焦簇时通知壳（点扇区标题/点空白 → 图例高亮同步） */
  onFocusChange: (t: string | null) => void
}

export interface RendererApi {
  /** 装配事件监听 + ResizeObserver（原 setupEvents + onMounted 的画布部分） */
  setup: () => void
  /** 释放 rAF 与 observer（原 onUnmounted） */
  dispose: () => void
  /** 数据变更后重建场景（原 buildSeaData） */
  buildSeaData: (quints: Quintuple[]) => void
  /** 数据加载完成后启动动画（原 watch(loading)） */
  start: () => void
  /** 壳侧聚焦簇（图例点击）→ 写入引擎 S.focusType */
  setFocusType: (t: string | null) => void
  /** 读取引擎侧 S.focusType（引擎内部可能改动） */
  getFocusType: () => string | null
  /** 当前是否处于近景（S.selected 非空） */
  isNearView: () => boolean
  /** 当前节点数（壳 computed 用） */
  getNodeCount: () => number
  /** 当前聚焦簇（供 chatQuery 后聚焦） */
  focusTopByWeight: () => string | null
  /** 类型 → 稳定配色（图例色点用；与画布共用同一 S.cmap，颜色必然一致） */
  colorOf: (t: string) => string
}

export function createMindRenderer(deps: RendererDeps): RendererApi {
  const { canvasRef, graphSummary } = deps

  // 工单209 第二批：34 个闭包 let 收敛为状态对象（语义等价：属性访问 vs 闭包捕获）
  const S = createMindState()

  const BARNES_HUT_THRESHOLD = 150
  // 可视化一屏上限：后端分页后前端不再无脑吃全量
  const WEIGHT_MAX = 10
  const COLORS = [
    '#4fc3f7',
    '#81c784',
    '#ffb74d',
    '#e57373',
    '#ba68c8',
    '#4dd0e1',
    '#aed581',
    '#ff8a65',
    '#f06292',
    '#9575cd',
    '#26c6da',
    '#dce775',
    '#ffa726',
    '#ef5350',
    '#ab47bc',
  ]

  const cfg = {
    hScale: 1.0,
    spread: 100,
    fontSize: 9,
    sway: 1.0,
    nodeSize: 5,
    particlesOn: true,
    raysOn: true,
    flowOn: true,
    planktonOn: true,
  }

  function tc(t: string): string {
    t = t || '?'
    if (!S.cmap[t])
      S.cmap[t] = COLORS[S.cidx++ % COLORS.length]!
    return S.cmap[t]!
  }

  function proj(x: number, y: number, z: number) {
    const ct = Math.cos(S.camT)
    const st = Math.sin(S.camT)
    const cp = Math.cos(S.camP)
    const sp = Math.sin(S.camP)
    const rx = ct * x + st * z
    const ry = y
    const rz = -st * x + ct * z
    const ry2 = cp * ry - sp * rz
    let rz2 = sp * ry + cp * rz
    rz2 += S.camD
    if (rz2 < 30)
      rz2 = 30
    const s = 700 / rz2
    return { sx: S.W / 2 + S.panX + rx * s, sy: S.H / 2 + S.panY - ry2 * s, s, d: rz2 }
  }

  function initPositions() {
    S.sectors = buildSectors(S.nodes, tc)
    const ord = new Map<string, number>()
    for (const n of S.nodes) {
      const k = ord.get(n.type) || 0
      ord.set(n.type, k + 1)
      const tgt = typeSectorTarget(n, k, S.sectors)
      // 入场：从簇心附近绽开（工单 B-4 分级入场的基础）
      n.px = tgt.x * (0.25 + Math.random() * 0.6)
      n.pz = tgt.z * (0.25 + Math.random() * 0.6)
      n.py = Math.min(n.weight, WEIGHT_MAX) / WEIGHT_MAX * SURFACE_H * cfg.hScale
      n.vx = 0
      n.vz = 0
      n.swayA = Math.random() * Math.PI * 2
      n.swayF = 0.3 + Math.random() * 0.4
      n.swayAmp = 1.5 + Math.random() * 2
      n.swayAx = Math.random() * Math.PI * 2
      n.swayFx = 0.2 + Math.random() * 0.3
      n.swayAmpX = 0.5 + Math.random()
      // 分级入场（工单 B-4）：骨架（高度量 hub）先出，
      // 簇内容再按扇区顺序渐进填充（每簇间隔 90ms，簇内每节点 4ms）
      n.revealAt = n.weight >= WEIGHT_MAX * 0.6
        ? 0
        : (n.typeIndex + 1) * 90 + k * 4
    }
  }

  function simulate() {
    const alpha = 0.22
    const fric = 0.88
    const bh = S.nodes.length > BARNES_HUT_THRESHOLD

    if (bh) {
      const qt = createQuadTree(S.nodes, cfg)
      const root = qt.build()
      if (root) {
        for (let i = 0; i < S.nodes.length; i++)
          qt.repel(root, i, alpha)
      }
    }
    else {
    // 小图仍走精确 O(n²)，与旧版结果一致
      for (let i = 0; i < S.nodes.length; i++) {
        for (let j = i + 1; j < S.nodes.length; j++) {
          const dx = S.nodes[j]!.px - S.nodes[i]!.px
          const dz = S.nodes[j]!.pz - S.nodes[i]!.pz
          let d2 = dx * dx + dz * dz
          if (d2 < 4)
            d2 = 4
          const d = Math.sqrt(d2)
          const f = cfg.spread * alpha / d2
          S.nodes[i]!.vx -= dx / d * f
          S.nodes[i]!.vz -= dz / d * f
          S.nodes[j]!.vx += dx / d * f
          S.nodes[j]!.vz += dz / d * f
        }
      }
    }

    for (const l of S.links) {
      const dx = l.tgt.px - l.src.px
      const dz = l.tgt.pz - l.src.pz
      const d = Math.sqrt(dx * dx + dz * dz) || 1
      const f = (d - 80) * 0.004 * alpha
      l.src.vx += dx / d * f
      l.src.vz += dz / d * f
      l.tgt.vx -= dx / d * f
      l.tgt.vz -= dz / d * f
    }

    // 分区锚定：把节点拉向本簇螺旋目标点
    // （替代原来那个 -0.0003 中心回拉——正是它让所有节点收敛后挤死在地面层）
    const seen = new Map<string, number>()
    for (const n of S.nodes) {
      if (!S.sectors[n.typeIndex])
        continue
      const k = seen.get(n.type) || 0
      seen.set(n.type, k + 1)
      const tgt = typeSectorTarget(n, k, S.sectors)
      n.vx += (tgt.x - n.px) * 0.004
      n.vz += (tgt.z - n.pz) * 0.004
    }

    // 异簇互斥：簇心之间的软壁垒，防止扇区摊平重叠
    for (let a = 0; a < S.sectors.length; a++) {
      for (let b = a + 1; b < S.sectors.length; b++) {
        const A = S.sectors[a]!
        const B = S.sectors[b]!
        const dx = B.cx - A.cx
        const dz = B.cz - A.cz
        const d = Math.sqrt(dx * dx + dz * dz) || 1
        const want = A.radius + B.radius + 24
        if (d >= want)
          continue
        const push = (want - d) * 0.06
        A.cx -= dx / d * push
        A.cz -= dz / d * push
        B.cx += dx / d * push
        B.cz += dz / d * push
      }
    }

    const now = (performance.now() - S.t0) * 0.001
    for (const n of S.nodes) {
      if (n === S.dragging) {
        n.vx = 0
        n.vz = 0
        continue
      }
      n.vx *= fric
      n.vz *= fric
      n.px += n.vx
      n.pz += n.vz
      const baseY = Math.min(n.weight, WEIGHT_MAX) / WEIGHT_MAX * SURFACE_H * cfg.hScale
      const sway = Math.sin(now * n.swayF + n.swayA) * n.swayAmp * cfg.sway
      n.py += (baseY + sway - n.py) * 0.06
      n.px += Math.sin(now * n.swayFx + n.swayAx) * n.swayAmpX * 0.03 * cfg.sway
      n.pz += Math.cos(now * n.swayFx + n.swayAx + 1) * n.swayAmpX * 0.03 * cfg.sway
    }
  }

  // ── Drawing ──

  // 点击外环标题 → 切焦点簇（工单 B-1/B-3 的 mid 模式入口）

  // 焦点簇：点扇区标题 / 点图例 / 聊天搜索命中后设置

  /** 引擎内部焦点变动 → 通知壳同步图例高亮 */

  // 每节点可见度 0..1，驱动 alpha / 字号 / 边丢弃

  // hex → rgba（簇色是 #rrggbb 或 COLORS 里的 hex）

  // 簇底盘（"星云团"）+ 常驻外环标题（工单 B-1）

  // ── 分层边捆绑 HEB（任务B-2，Holten 2006） ──
  // 跨区边走"节点 → 本簇心 → 中点 → 目标簇心 → 目标节点"的折线样条，
  // 于是同一对簇之间的所有边在公共段重叠成一束"光流"；同区边走直线（本就不乱）。

  // 束流聚合：同一对簇的边数 → 束宽

  // 远景：只画束，不画单边——这是"从一坨线变成一束光"的关键

  function loop() {
    simulate()
    if (cfg.particlesOn)
      simParticles(S.particles, cfg)
    if (cfg.flowOn)
      simFlow(S.flowParts)
    if (cfg.planktonOn)
      simPlankton(S.plankton, cfg, S.t0)
    drawPass(S, { tc, proj, cfg })
    S.animId = requestAnimationFrame(loop)
  }

  // ── Hit test ──

  function resize() {
    const cv = canvasRef.value
    if (!cv)
      return
    const container = cv.parentElement
    if (!container)
      return
    S.dpr = devicePixelRatio || 1
    S.W = container.clientWidth
    S.H = container.clientHeight
    cv.width = S.W * S.dpr
    cv.height = S.H * S.dpr
    cv.style.width = `${S.W}px`
    cv.style.height = `${S.H}px`
    S.cx = cv.getContext('2d')
    if (S.cx)
      S.cx.setTransform(S.dpr, 0, 0, S.dpr, 0, 0)
  }

  // ── 对外 API（原壳侧 onMounted/onUnmounted/watch 的画布部分收敛于此）──

  function setup(): void {
    S.t0 = performance.now()
    resize()

    const cv = canvasRef.value
    if (!cv)
      return
    setupEvents(S, cv, cfg, { findNode: (sx, sy) => findNodeImpl(S, cfg, proj, sx, sy), proj })
    if (cv.parentElement) {
      S._resizeObserver = new ResizeObserver(() => resize())
      S._resizeObserver.observe(cv.parentElement)
    }
  }

  function dispose(): void {
    if (S.animId)
      cancelAnimationFrame(S.animId)
    if (S._resizeObserver)
      S._resizeObserver.disconnect()
  }

  function start(): void {
    if (S.animId)
      cancelAnimationFrame(S.animId)
    S.animId = requestAnimationFrame(loop)
  }

  function setFocusType(t: string | null): void {
    S.focusType = t
  }

  function getFocusType(): string | null {
    return S.focusType
  }

  function isNearView(): boolean {
    return !!S.selected
  }

  function getNodeCount(): number {
    return S.nodes.length
  }

  function focusTopByWeight(): string | null {
    const top = [...S.nodes].sort((a, b) => b.weight - a.weight)[0]
    S.focusType = top?.type ?? null
    return S.focusType
  }

  return {
    setup,
    dispose,
    buildSeaData: (quints: Quintuple[]) => {
      buildSeaData(S, quints, tc, graphSummary)
      initPositions()
      S.particles = initParticles()
      S.rays = initRays()
      S.flowParts = initFlow(S.links)
      S.plankton = initPlankton()
    },
    start,
    setFocusType,
    getFocusType,
    isNearView,
    getNodeCount,
    focusTopByWeight,
    colorOf: tc,
  }
}
