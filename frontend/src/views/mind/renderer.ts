// 记忆云海 3D 渲染引擎（卷190-B5：从 MindView.vue 整块搬出，零语义改动）。
// 全部绘制状态私在工厂闭包内；壳只通过 RendererApi 交互，
// 需要壳侧响应的两处（选中节点 / 统计刷新）走 callbacks 回调。
import type { Ref } from 'vue'

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
  /** 壳侧聚焦簇（图例点击）→ 写入引擎 focusType */
  setFocusType: (t: string | null) => void
  /** 读取引擎侧 focusType（引擎内部可能改动） */
  getFocusType: () => string | null
  /** 当前是否处于近景（selected 非空） */
  isNearView: () => boolean
  /** 当前节点数（壳 computed 用） */
  getNodeCount: () => number
  /** 当前聚焦簇（供 chatQuery 后聚焦） */
  focusTopByWeight: () => string | null
  /** 类型 → 稳定配色（图例色点用；与画布共用同一 cmap，颜色必然一致） */
  colorOf: (t: string) => string
}

interface Quintuple {
  subject: string
  subjectType: string
  predicate: string
  object: string
  objectType: string
  /** with_degree=true 时后端回填的实体连接数（卷148 度数下沉） */
  degree?: number
}

interface SeaNode {
  id: string
  type: string
  weight: number
  px: number
  py: number
  pz: number
  vx: number
  vz: number
  swayA: number
  swayF: number
  swayAmp: number
  swayAx: number
  swayFx: number
  swayAmpX: number
  /** 所属类型扇区下标（-1 = 未分派） */
  typeIndex: number
  /** 入场分级：到这个时刻才渐显（毫秒，相对 t0） */
  revealAt: number
}

interface SeaLink {
  src: SeaNode
  tgt: SeaNode
  relation: string
}

interface Particle {
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  size: number
  alpha: number
  hue: number
  layer: number
}

interface Ray {
  x: number
  z: number
  radius: number
  phase: number
  freq: number
  swayAmp: number
  alpha: number
}

interface FlowDot {
  link: SeaLink
  t: number
  speed: number
  size: number
}

interface Plankton {
  x: number
  y: number
  z: number
  pa: number
  pf1: number
  pf2: number
  pa2: number
  pf3: number
  amp1: number
  amp2: number
  amp3: number
  size: number
  hue: number
  life: number
  maxLife: number
  trail: { x: number, y: number, z: number }[]
}

export function createMindRenderer(deps: RendererDeps): RendererApi {
  const { canvasRef, graphSummary, onNodeCountChange, onSelect, onFocusChange } = deps

  const BARNES_HUT_THRESHOLD = 150
  // 可视化一屏上限：后端分页后前端不再无脑吃全量
  const GRAPH_PAGE_SIZE = 500
  const FLOOR_Y = 0
  const SURFACE_H = 200
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

  let W = 0
  let H = 0
  let dpr = 1
  let cx: CanvasRenderingContext2D | null = null
  let animId = 0
  let t0 = 0

  let nodes: SeaNode[] = []
  let links: SeaLink[] = []
  let particles: Particle[] = []
  let rays: Ray[] = []
  let flowParts: FlowDot[] = []
  let plankton: Plankton[] = []

  let cmap: Record<string, string> = {}
  let cidx = 0
  let camT = 0.5
  let camP = 0.45
  let camD = 550
  let panX = 0
  let panY = 0

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

  let rotating = false
  let panning = false
  let rsx = 0
  let rsy = 0
  let rst = 0
  let rsp = 0
  let panOX = 0
  let panOY = 0
  let dragging: SeaNode | null = null
  let dragMoved = false
  let prevMX = 0
  let prevMY = 0
  let hovered: SeaNode | null = null
  let selected: SeaNode | null = null

  function tc(t: string): string {
    t = t || '?'
    if (!cmap[t])
      cmap[t] = COLORS[cidx++ % COLORS.length]!
    return cmap[t]!
  }

  function proj(x: number, y: number, z: number) {
    const ct = Math.cos(camT)
    const st = Math.sin(camT)
    const cp = Math.cos(camP)
    const sp = Math.sin(camP)
    const rx = ct * x + st * z
    const ry = y
    const rz = -st * x + ct * z
    const ry2 = cp * ry - sp * rz
    let rz2 = sp * ry + cp * rz
    rz2 += camD
    if (rz2 < 30)
      rz2 = 30
    const s = 700 / rz2
    return { sx: W / 2 + panX + rx * s, sy: H / 2 + panY - ry2 * s, s, d: rz2 }
  }

  // ── Particle system ──
  function initParticles() {
    particles = []
    for (let i = 0; i < 40; i++) {
      particles.push({
        x: (Math.random() - 0.5) * 500,
        y: Math.random() * SURFACE_H * 0.2,
        z: (Math.random() - 0.5) * 500,
        vx: (Math.random() - 0.5) * 0.08,
        vy: 0.01 + Math.random() * 0.03,
        vz: (Math.random() - 0.5) * 0.08,
        size: 0.4 + Math.random() * 0.6,
        alpha: 0.08 + Math.random() * 0.12,
        hue: 200 + Math.random() * 20,
        layer: 0,
      })
    }
    for (let i = 0; i < 60; i++) {
      const big = Math.random() < 0.08
      particles.push({
        x: (Math.random() - 0.5) * 500,
        y: SURFACE_H * 0.1 + Math.random() * SURFACE_H * 0.8,
        z: (Math.random() - 0.5) * 500,
        vx: (Math.random() - 0.5) * 0.12,
        vy: big ? 0.3 + Math.random() * 0.3 : 0.06 + Math.random() * 0.18,
        vz: (Math.random() - 0.5) * 0.12,
        size: big ? 1.8 + Math.random() * 1.5 : 0.5 + Math.random() * 1.2,
        alpha: big ? 0.35 + Math.random() * 0.2 : 0.12 + Math.random() * 0.25,
        hue: 190 + Math.random() * 40,
        layer: 1,
      })
    }
    for (let i = 0; i < 25; i++) {
      particles.push({
        x: (Math.random() - 0.5) * 400,
        y: SURFACE_H * 0.75 + Math.random() * SURFACE_H * 0.3,
        z: (Math.random() - 0.5) * 400,
        vx: (Math.random() - 0.5) * 0.06,
        vy: 0.03 + Math.random() * 0.08,
        vz: (Math.random() - 0.5) * 0.06,
        size: 1 + Math.random() * 2,
        alpha: 0.2 + Math.random() * 0.3,
        hue: 185 + Math.random() * 30,
        layer: 2,
      })
    }
  }

  function simParticles() {
    const surfY = SURFACE_H * cfg.hScale
    for (const p of particles) {
      p.x += p.vx
      p.y += p.vy
      p.z += p.vz
      if (p.layer === 0) {
        if (p.y > surfY * 0.25) {
          p.y = 0
          p.x = (Math.random() - 0.5) * 500
          p.z = (Math.random() - 0.5) * 500
        }
      }
      else if (p.layer === 1) {
        if (p.y > surfY + 15) {
          p.y = surfY * 0.05
          p.x = (Math.random() - 0.5) * 500
          p.z = (Math.random() - 0.5) * 500
        }
      }
      else {
        if (p.y > surfY + 30) {
          p.y = surfY * 0.7
          p.x = (Math.random() - 0.5) * 400
          p.z = (Math.random() - 0.5) * 400
        }
      }
      if (p.x > 260)
        p.x = -260
      if (p.x < -260)
        p.x = 260
      if (p.z > 260)
        p.z = -260
      if (p.z < -260)
        p.z = 260
    }
  }

  function drawParticles() {
    if (!cx)
      return
    for (const p of particles) {
      const pp = proj(p.x, p.y, p.z)
      if (pp.d < 50)
        continue
      const fog = Math.min(1, Math.max(0.05, 250 / pp.d))
      const sz = Math.max(0.4, p.size * pp.s)
      const brightMul = p.layer === 2 ? 1.6 : 1
      cx.globalAlpha = p.alpha * fog * brightMul
      cx.fillStyle = `hsl(${p.hue},60%,${p.layer === 2 ? '78' : '65'}%)`
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
      cx.fill()
      if (sz > 0.8) {
        const gr = sz * (p.layer === 2 ? 4 : 2.5)
        const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, gr)
        gg.addColorStop(0, `hsla(${p.hue},70%,75%,${p.alpha * fog * 0.3 * brightMul})`)
        gg.addColorStop(1, 'transparent')
        cx.beginPath()
        cx.arc(pp.sx, pp.sy, gr, 0, Math.PI * 2)
        cx.fillStyle = gg
        cx.fill()
      }
    }
    cx.globalAlpha = 1
  }

  // ── God Rays ──
  function initRays() {
    rays = []
    for (let i = 0; i < 3; i++) {
      rays.push({
        x: (Math.random() - 0.5) * 200,
        z: (Math.random() - 0.5) * 200,
        radius: 18 + Math.random() * 22,
        phase: Math.random() * Math.PI * 2,
        freq: 0.12 + Math.random() * 0.08,
        swayAmp: 25 + Math.random() * 15,
        alpha: 0.018 + Math.random() * 0.012,
      })
    }
  }

  function drawRays() {
    if (!cx)
      return
    const now = (performance.now() - t0) * 0.001
    const surfY = SURFACE_H * cfg.hScale
    const slices = 14
    const prev = cx.globalCompositeOperation
    cx.globalCompositeOperation = 'lighter'
    for (const r of rays) {
      const sway = Math.sin(now * r.freq + r.phase) * r.swayAmp
      const bx = r.x + sway
      for (let s = 0; s < slices; s++) {
        const t = s / (slices - 1)
        const y = surfY * (1 - t)
        const rad = r.radius * (1 - t * 0.3) * (1 + Math.sin(now * 0.5 + s) * 0.08)
        const pp = proj(bx, y, r.z)
        if (pp.d < 40)
          continue
        const screenR = Math.max(2, rad * pp.s)
        const intensity = r.alpha * (1 - t * 0.85)
        const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, screenR)
        gg.addColorStop(0, `rgba(100,180,255,${intensity})`)
        gg.addColorStop(0.4, `rgba(70,150,240,${intensity * 0.5})`)
        gg.addColorStop(1, 'rgba(50,120,200,0)')
        cx.beginPath()
        cx.arc(pp.sx, pp.sy, screenR, 0, Math.PI * 2)
        cx.fillStyle = gg
        cx.fill()
      }
    }
    cx.globalCompositeOperation = prev
  }

  // ── Flow particles ──
  function initFlow() {
    flowParts = []
    for (const l of links) {
      if (Math.random() < 0.35)
        flowParts.push({ link: l, t: Math.random(), speed: 0.0008 + Math.random() * 0.0012, size: 0.5 + Math.random() * 0.5 })
    }
  }

  function simFlow() {
    for (const f of flowParts) {
      f.t += f.speed
      if (f.t > 1)
        f.t -= 1
    }
  }

  function drawFlow() {
    if (!cx)
      return
    const now = (performance.now() - t0) * 0.001
    for (const f of flowParts) {
      const s = f.link.src
      const tg = f.link.tgt
      const fx = s.px + (tg.px - s.px) * f.t
      const fy = s.py + (tg.py - s.py) * f.t
      const fz = s.pz + (tg.pz - s.pz) * f.t
      const pp = proj(fx, fy, fz)
      if (pp.d < 50)
        continue
      const fog = Math.min(1, Math.max(0.1, 250 / pp.d))
      const sz = Math.max(0.4, f.size * pp.s)
      const flicker = 0.7 + 0.3 * Math.sin(now * 6 + f.t * 20)
      cx.globalAlpha = 0.5 * fog * flicker
      cx.fillStyle = 'rgba(255,210,100,1)'
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
      cx.fill()
      const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, sz * 3)
      gg.addColorStop(0, `rgba(255,200,80,${0.35 * fog * flicker})`)
      gg.addColorStop(0.5, `rgba(255,170,50,${0.1 * fog * flicker})`)
      gg.addColorStop(1, 'transparent')
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz * 3, 0, Math.PI * 2)
      cx.fillStyle = gg
      cx.fill()
    }
    cx.globalAlpha = 1
  }

  // ── Plankton ──
  function spawnPlankton(): Plankton {
    return {
      x: (Math.random() - 0.5) * 350,
      y: SURFACE_H * 0.1 + Math.random() * SURFACE_H * 0.8,
      z: (Math.random() - 0.5) * 350,
      pa: Math.random() * Math.PI * 2,
      pf1: 0.4 + Math.random() * 0.5,
      pf2: 0.7 + Math.random() * 0.6,
      pa2: Math.random() * Math.PI * 2,
      pf3: 0.3 + Math.random() * 0.3,
      amp1: 0.5 + Math.random() * 0.6,
      amp2: 0.3 + Math.random() * 0.4,
      amp3: 0.2 + Math.random() * 0.3,
      size: 0.4 + Math.random() * 0.5,
      hue: 160 + Math.random() * 50,
      life: 0,
      maxLife: 300 + Math.floor(Math.random() * 400),
      trail: [],
    }
  }

  function initPlankton() {
    plankton = []
    for (let i = 0; i < 10; i++) {
      const p = spawnPlankton()
      p.life = Math.floor(Math.random() * p.maxLife)
      plankton.push(p)
    }
  }

  function simPlankton() {
    const now = (performance.now() - t0) * 0.001
    const surfY = SURFACE_H * cfg.hScale
    for (let i = 0; i < plankton.length; i++) {
      const p = plankton[i]!
      p.life++
      if (p.life > p.maxLife) {
        plankton[i] = spawnPlankton()
        continue
      }
      p.x += Math.sin(now * p.pf1 + p.pa) * p.amp1 * 0.12 + Math.cos(now * p.pf3 + p.pa2) * p.amp3 * 0.06
      p.y += Math.sin(now * p.pf2 + p.pa + 1) * p.amp2 * 0.05
      p.z += Math.cos(now * p.pf1 + p.pa + 2) * p.amp1 * 0.10 + Math.sin(now * p.pf3 + p.pa2 + 1) * p.amp3 * 0.05
      if (p.y < FLOOR_Y + 5)
        p.y = FLOOR_Y + 5
      if (p.y > surfY - 5)
        p.y = surfY - 5
      if (p.x > 180)
        p.x = -180
      if (p.x < -180)
        p.x = 180
      if (p.z > 180)
        p.z = -180
      if (p.z < -180)
        p.z = 180
      p.trail.push({ x: p.x, y: p.y, z: p.z })
      if (p.trail.length > 35)
        p.trail.shift()
    }
  }

  function drawPlankton() {
    if (!cx)
      return
    for (const p of plankton) {
      const lifeRatio = p.life / p.maxLife
      let fade = 1
      if (lifeRatio < 0.15)
        fade = lifeRatio / 0.15
      else if (lifeRatio > 0.8)
        fade = 1 - (lifeRatio - 0.8) / 0.2
      if (fade < 0.01)
        continue
      for (let i = 0; i < p.trail.length - 1; i++) {
        const t = p.trail[i]!
        const pp = proj(t.x, t.y, t.z)
        if (pp.d < 50)
          continue
        const fog = Math.min(1, Math.max(0.05, 250 / pp.d))
        const a = (i / p.trail.length) * 0.18 * fog * fade
        const sz = Math.max(0.2, p.size * 0.4 * pp.s)
        cx.globalAlpha = a
        cx.fillStyle = `hsl(${p.hue},80%,70%)`
        cx.beginPath()
        cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
        cx.fill()
      }
      const pp = proj(p.x, p.y, p.z)
      if (pp.d < 50)
        continue
      const fog = Math.min(1, Math.max(0.1, 250 / pp.d))
      const sz = Math.max(0.3, p.size * pp.s)
      cx.globalAlpha = 0.5 * fog * fade
      cx.fillStyle = `hsl(${p.hue},80%,72%)`
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
      cx.fill()
      if (sz > 0.4) {
        const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, sz * 3)
        gg.addColorStop(0, `hsla(${p.hue},90%,75%,${0.2 * fog * fade})`)
        gg.addColorStop(1, 'transparent')
        cx.beginPath()
        cx.arc(pp.sx, pp.sy, sz * 3, 0, Math.PI * 2)
        cx.fillStyle = gg
        cx.fill()
      }
    }
    cx.globalAlpha = 1
  }

  interface Sector {
    type: string
    color: string
    angle: number
    count: number
    radius: number
    cx: number
    cz: number
  }

  // 分区圆盘半径随节点数增长——避免 500 节点还挤在 R=120 的盘里
  function layoutRadius(): number {
    return 140 + Math.sqrt(nodes.length) * 22
  }

  let sectors: Sector[] = []

  function buildSectors() {
    const byType = new Map<string, number>()
    for (const n of nodes)
      byType.set(n.type, (byType.get(n.type) || 0) + 1)

    // 实体多的类型排前面，扇区角度 ∝ 该类型实体数
    const sorted = [...byType.entries()].sort((a, b) => b[1] - a[1])
    const total = nodes.length || 1
    const R = layoutRadius()

    sectors = []
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
  }

  // 簇内目标点：黄金角螺旋（比随机撒点均匀，不会抱团打架）
  function typeSectorTarget(n: SeaNode, ordinal: number) {
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

  // ── Barnes-Hut 四叉树（任务B-6：n>150 自动切换，O(n²) → O(n log n)） ──
  interface QuadNode {
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

  function initPositions() {
    buildSectors()
    const ord = new Map<string, number>()
    for (const n of nodes) {
      const k = ord.get(n.type) || 0
      ord.set(n.type, k + 1)
      const tgt = typeSectorTarget(n, k)
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
    const bh = nodes.length > BARNES_HUT_THRESHOLD

    if (bh) {
      const root = quadBuild()
      if (root) {
        for (let i = 0; i < nodes.length; i++)
          quadRepel(root, i, alpha)
      }
    }
    else {
    // 小图仍走精确 O(n²)，与旧版结果一致
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j]!.px - nodes[i]!.px
          const dz = nodes[j]!.pz - nodes[i]!.pz
          let d2 = dx * dx + dz * dz
          if (d2 < 4)
            d2 = 4
          const d = Math.sqrt(d2)
          const f = cfg.spread * alpha / d2
          nodes[i]!.vx -= dx / d * f
          nodes[i]!.vz -= dz / d * f
          nodes[j]!.vx += dx / d * f
          nodes[j]!.vz += dz / d * f
        }
      }
    }

    for (const l of links) {
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
    for (const n of nodes) {
      if (!sectors[n.typeIndex])
        continue
      const k = seen.get(n.type) || 0
      seen.set(n.type, k + 1)
      const tgt = typeSectorTarget(n, k)
      n.vx += (tgt.x - n.px) * 0.004
      n.vz += (tgt.z - n.pz) * 0.004
    }

    // 异簇互斥：簇心之间的软壁垒，防止扇区摊平重叠
    for (let a = 0; a < sectors.length; a++) {
      for (let b = a + 1; b < sectors.length; b++) {
        const A = sectors[a]!
        const B = sectors[b]!
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

    const now = (performance.now() - t0) * 0.001
    for (const n of nodes) {
      if (n === dragging) {
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
  function drawFloor() {
    if (!cx)
      return
    const gridN = 10
    const gridS = 30
    const half = gridN * gridS
    cx.strokeStyle = 'rgba(30,60,120,0.18)'
    cx.lineWidth = 0.7
    for (let i = -gridN; i <= gridN; i++) {
      const p1 = proj(i * gridS, FLOOR_Y, -half)
      const p2 = proj(i * gridS, FLOOR_Y, half)
      const p3 = proj(-half, FLOOR_Y, i * gridS)
      const p4 = proj(half, FLOOR_Y, i * gridS)
      cx.beginPath()
      cx.moveTo(p1.sx, p1.sy)
      cx.lineTo(p2.sx, p2.sy)
      cx.stroke()
      cx.beginPath()
      cx.moveTo(p3.sx, p3.sy)
      cx.lineTo(p4.sx, p4.sy)
      cx.stroke()
    }
  }

  function drawSurface() {
    if (!cx)
      return
    const surfY = SURFACE_H * cfg.hScale
    const half = 300
    const corners = [[-half, surfY, -half], [half, surfY, -half], [half, surfY, half], [-half, surfY, half]] as const
    const pc = corners.map(c => proj(c[0], c[1], c[2]))
    cx.beginPath()
    cx.moveTo(pc[0]!.sx, pc[0]!.sy)
    for (let i = 1; i < 4; i++)
      cx.lineTo(pc[i]!.sx, pc[i]!.sy)
    cx.closePath()
    cx.fillStyle = 'rgba(20,80,180,0.06)'
    cx.fill()
    cx.strokeStyle = 'rgba(40,100,200,0.15)'
    cx.lineWidth = 1
    cx.stroke()
    cx.strokeStyle = 'rgba(50,120,220,0.08)'
    cx.lineWidth = 0.5
    const now = (performance.now() - t0) * 0.0005
    for (let i = 0; i < 6; i++) {
      const off = (i / 6 - 0.5) * half * 1.8
      const p1 = proj(-half, surfY, off + Math.sin(now + i) * 10)
      const p2 = proj(half, surfY, off + Math.sin(now + i + 2) * 10)
      cx.beginPath()
      cx.moveTo(p1.sx, p1.sy)
      cx.lineTo(p2.sx, p2.sy)
      cx.stroke()
    }
  }

  // 点击外环标题 → 切焦点簇（工单 B-1/B-3 的 mid 模式入口）
  function pickSector(sx: number, sy: number): string | null {
    let best: string | null = null
    let bestD = 3600 // 60px 命中半径
    for (const sc of sectors) {
      const outerR = Math.hypot(sc.cx, sc.cz) + sc.radius + 70
      const p = proj(Math.cos(sc.angle) * outerR, SURFACE_H * 0.5, Math.sin(sc.angle) * outerR)
      const d2 = (p.sx - sx) ** 2 + (p.sy - sy) ** 2
      if (d2 < bestD) {
        best = sc.type
        bestD = d2
      }
    }
    return best
  }

  function drawCompass() {
    if (!cx)
      return
    const ox = W - 70
    const oy = H - 70
    const len = 40
    const ct = Math.cos(camT)
    const st = Math.sin(camT)
    const cp = Math.cos(camP)
    const sp = Math.sin(camP)
    function projAxis(x: number, y: number, z: number) {
      const rx = ct * x + st * z
      const ry2 = cp * y - sp * (-st * x + ct * z)
      return { sx: ox + rx * len, sy: oy - ry2 * len }
    }
    const axes = [
      { x: 1, y: 0, z: 0, label: 'X', color: '#e05555' },
      { x: 0, y: 1, z: 0, label: 'Y', color: '#55cc55' },
      { x: 0, y: 0, z: 1, label: 'Z', color: '#5577ee' },
    ]
    cx.beginPath()
    cx.arc(ox, oy, 52, 0, Math.PI * 2)
    cx.fillStyle = 'rgba(6,12,24,0.7)'
    cx.fill()
    cx.strokeStyle = 'rgba(50,90,160,0.3)'
    cx.lineWidth = 1
    cx.stroke()
    for (const a of axes) {
      const p = projAxis(a.x, a.y, a.z)
      cx.beginPath()
      cx.moveTo(ox, oy)
      cx.lineTo(p.sx, p.sy)
      cx.strokeStyle = a.color
      cx.lineWidth = 2
      cx.stroke()
      const ang = Math.atan2(p.sy - oy, p.sx - ox)
      cx.beginPath()
      cx.moveTo(p.sx, p.sy)
      cx.lineTo(p.sx - Math.cos(ang - 0.4) * 8, p.sy - Math.sin(ang - 0.4) * 8)
      cx.lineTo(p.sx - Math.cos(ang + 0.4) * 8, p.sy - Math.sin(ang + 0.4) * 8)
      cx.closePath()
      cx.fillStyle = a.color
      cx.fill()
      const lx = p.sx + Math.cos(ang) * 12
      const ly = p.sy + Math.sin(ang) * 12
      cx.font = 'bold 9px sans-serif'
      cx.fillStyle = a.color
      cx.textAlign = 'center'
      cx.textBaseline = 'middle'
      cx.fillText(a.label, lx, ly)
    }
  }

  function drawNodeGlow(sx: number, sy: number, r: number, col: string, fog: number, isHov: boolean) {
    if (!cx)
      return
    if (r > 2) {
      const gr = r * 4
      const gg = cx.createRadialGradient(sx, sy, r * 0.3, sx, sy, gr)
      gg.addColorStop(0, `${col}40`)
      gg.addColorStop(0.3, `${col}18`)
      gg.addColorStop(0.7, `${col}08`)
      gg.addColorStop(1, 'transparent')
      cx.beginPath()
      cx.arc(sx, sy, gr, 0, Math.PI * 2)
      cx.fillStyle = gg
      cx.fill()
    }
    cx.beginPath()
    cx.arc(sx, sy, Math.max(1.5, r), 0, Math.PI * 2)
    cx.globalAlpha = Math.max(0.3, fog)
    cx.fillStyle = isHov ? '#fff' : col
    cx.fill()
    if (r > 3) {
      const hx = sx - r * 0.28
      const hy = sy - r * 0.28
      const hr = r * 0.38
      const ig = cx.createRadialGradient(hx, hy, 0, hx, hy, hr)
      ig.addColorStop(0, `rgba(255,255,255,${isHov ? 0.6 : 0.3 * fog})`)
      ig.addColorStop(1, 'transparent')
      cx.beginPath()
      cx.arc(hx, hy, hr, 0, Math.PI * 2)
      cx.fillStyle = ig
      cx.fill()
    }
    cx.globalAlpha = 1
  }

  const LOD_FAR = 'far'
  const LOD_MID = 'mid'
  const LOD_NEAR = 'near'

  // 焦点簇：点扇区标题 / 点图例 / 聊天搜索命中后设置
  let focusType: string | null = null

  /** 引擎内部焦点变动 → 通知壳同步图例高亮 */
  function syncFocusFromCanvas(): void {
    onFocusChange(focusType)
  }

  function lodLevel(): string {
    if (selected)
      return LOD_NEAR
    if (focusType)
      return LOD_MID
    return LOD_FAR
  }

  const HUB_TOPN = 50

  function hubSet(): Set<SeaNode> {
    const sorted = [...nodes].sort((a, b) => b.weight - a.weight)
    return new Set(sorted.slice(0, HUB_TOPN))
  }

  function neighborhood(n: SeaNode): Set<SeaNode> {
    const s = new Set<SeaNode>([n])
    for (const l of links) {
      if (l.src === n)
        s.add(l.tgt)
      if (l.tgt === n)
        s.add(l.src)
    }
    return s
  }

  // 每节点可见度 0..1，驱动 alpha / 字号 / 边丢弃
  function visibility(): Map<SeaNode, number> {
    const vis = new Map<SeaNode, number>()
    const lv = lodLevel()

    if (lv === LOD_FAR) {
      const hubs = hubSet()
      for (const n of nodes)
        vis.set(n, hubs.has(n) ? 1 : 0.22)
      return vis
    }

    if (lv === LOD_MID) {
      for (const n of nodes)
        vis.set(n, n.type === focusType ? 1 : 0.3)
      return vis
    }

    const focus = selected!
    const nb = neighborhood(focus)
    for (const n of nodes) {
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

  // hex → rgba（簇色是 #rrggbb 或 COLORS 里的 hex）
  function hexA(hex: string, a: number): string {
    if (hex.startsWith('rgba') || hex.startsWith('rgb('))
      return hex
    const h = hex.replace('#', '')
    const r = Number.parseInt(h.slice(0, 2), 16)
    const g = Number.parseInt(h.slice(2, 4), 16)
    const b = Number.parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`
  }

  // 簇底盘（"星云团"）+ 常驻外环标题（工单 B-1）
  function drawSectors() {
    if (!cx || sectors.length === 0)
      return
    const lv = lodLevel()

    for (const sc of sectors) {
      const isFocus = sc.type === focusType || selected?.type === sc.type
      // 星云底盘
      const p = proj(sc.cx, SURFACE_H * 0.35, sc.cz)
      const rr = sc.radius * p.s
      if (rr > 2) {
        const a = isFocus ? 0.2 : 0.08
        const g = cx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, rr)
        g.addColorStop(0, hexA(sc.color, a))
        g.addColorStop(0.65, hexA(sc.color, a * 0.4))
        g.addColorStop(1, 'transparent')
        cx.beginPath()
        cx.arc(p.sx, p.sy, rr, 0, Math.PI * 2)
        cx.fillStyle = g
        cx.fill()
      }

      // 外环标题：沿扇区中轴往外推
      const outerR = Math.hypot(sc.cx, sc.cz) + sc.radius + 70
      const tp = proj(Math.cos(sc.angle) * outerR, SURFACE_H * 0.5, Math.sin(sc.angle) * outerR)
      if (cfg.fontSize > 0 && p.s > 0.22) {
        const fs = Math.max(9, 12 * p.s)
        const label = `${sc.type} (${sc.count})`
        cx.font = `600 ${fs}px sans-serif`
        cx.textAlign = 'center'
        cx.textBaseline = 'middle'
        cx.fillStyle = hexA(sc.color, isFocus ? 0.95 : lv === LOD_FAR ? 0.6 : 0.3)
        cx.fillText(label, tp.sx, tp.sy)
        if (isFocus) {
          const tw = cx.measureText(label).width
          cx.beginPath()
          cx.moveTo(tp.sx - tw / 2, tp.sy + fs * 0.8)
          cx.lineTo(tp.sx + tw / 2, tp.sy + fs * 0.8)
          cx.strokeStyle = hexA(sc.color, 0.5)
          cx.lineWidth = 1
          cx.stroke()
        }
      }
    }
  }

  // ── 分层边捆绑 HEB（任务B-2，Holten 2006） ──
  // 跨区边走"节点 → 本簇心 → 中点 → 目标簇心 → 目标节点"的折线样条，
  // 于是同一对簇之间的所有边在公共段重叠成一束"光流"；同区边走直线（本就不乱）。
  function bundledWaypoints(l: SeaLink) {
    const a = sectors[l.src.typeIndex]
    const b = sectors[l.tgt.typeIndex]
    if (!a || !b || a === b)
      return [] as Array<{ x: number, y: number, z: number }>
    return [
      { x: a.cx, y: SURFACE_H * 0.42, z: a.cz },
      { x: (a.cx + b.cx) / 2, y: SURFACE_H * 0.62, z: (a.cz + b.cz) / 2 },
      { x: b.cx, y: SURFACE_H * 0.42, z: b.cz },
    ]
  }

  // 束流聚合：同一对簇的边数 → 束宽
  interface Bundle {
    a: number
    b: number
    count: number
  }

  function buildBundles(): Bundle[] {
    const m = new Map<string, Bundle>()
    for (const l of links) {
      const ai = l.src.typeIndex
      const bi = l.tgt.typeIndex
      if (ai < 0 || bi < 0 || ai === bi)
        continue
      const key = ai < bi ? `${ai}:${bi}` : `${bi}:${ai}`
      let bd = m.get(key)
      if (!bd) {
        bd = { a: Math.min(ai, bi), b: Math.max(ai, bi), count: 0 }
        m.set(key, bd)
      }
      bd.count++
    }
    return [...m.values()].sort((p, q) => q.count - p.count)
  }

  // 远景：只画束，不画单边——这是"从一坨线变成一束光"的关键
  function drawBundles() {
    if (!cx || sectors.length === 0)
      return
    for (const bd of buildBundles()) {
      const A = sectors[bd.a]
      const B = sectors[bd.b]
      if (!A || !B)
        continue
      const p1 = proj(A.cx, SURFACE_H * 0.42, A.cz)
      const p2 = proj(B.cx, SURFACE_H * 0.42, B.cz)
      const mid = proj((A.cx + B.cx) / 2, SURFACE_H * 0.62, (A.cz + B.cz) / 2)
      // 束宽 ∝ 边数（sqrt 压缩，防一条巨束糊满屏）
      const w = Math.max(0.6, Math.sqrt(bd.count) * 0.9 * ((p1.s + p2.s) / 2))
      const fog = Math.min(1, Math.max(0.08, 300 / ((p1.d + p2.d) / 2)))
      cx.beginPath()
      cx.moveTo(p1.sx, p1.sy)
      cx.quadraticCurveTo(mid.sx, mid.sy, p2.sx, p2.sy)
      cx.strokeStyle = `rgba(90,150,230,${fog * 0.3})`
      cx.lineWidth = w
      cx.stroke()
      cx.beginPath()
      cx.moveTo(p1.sx, p1.sy)
      cx.quadraticCurveTo(mid.sx, mid.sy, p2.sx, p2.sy)
      cx.strokeStyle = `rgba(150,200,255,${fog * 0.22})`
      cx.lineWidth = Math.max(0.4, w * 0.3)
      cx.stroke()
    }
  }

  function draw() {
    if (!cx)
      return
    const bg = cx.createLinearGradient(0, 0, 0, H)
    bg.addColorStop(0, '#0a1525')
    bg.addColorStop(0.3, '#06101c')
    bg.addColorStop(0.7, '#040a14')
    bg.addColorStop(1, '#020608')
    cx.fillStyle = bg
    cx.fillRect(0, 0, W, H)

    drawFloor()
    drawSurface()
    if (cfg.raysOn)
      drawRays()
    if (cfg.particlesOn)
      drawParticles()
    if (cfg.planktonOn)
      drawPlankton()

    const lv = lodLevel()
    const vis = visibility()

    // 簇底盘在最下层；远景再叠捆绑束
    drawSectors()
    if (lv === LOD_FAR)
      drawBundles()

    // 收集 item（远→近排序）
    interface LinkItem { t: 'L', p1: ReturnType<typeof proj>, p2: ReturnType<typeof proj>, l: SeaLink, d: number, w: number }
    interface NodeItem { t: 'N', p: ReturnType<typeof proj>, n: SeaNode, d: number, w: number }
    const items: Array<LinkItem | NodeItem> = []

    for (const l of links) {
      const va = vis.get(l.src) ?? 1
      const vb = vis.get(l.tgt) ?? 1
      const w = Math.min(va, vb)
      // 远景：只画 hub 之间的边（细线，作为束流之外的骨架）
      if (lv === LOD_FAR) {
        if (va < 1 || vb < 1)
          continue
      }
      else if (w <= 0.12) {
      // 中/近景：压暗的边直接丢，否则还是一坨
        continue
      }
      const p1 = proj(l.src.px, l.src.py, l.src.pz)
      const p2 = proj(l.tgt.px, l.tgt.py, l.tgt.pz)
      items.push({ t: 'L', p1, p2, l, d: (p1.d + p2.d) / 2, w })
    }

    for (const n of nodes) {
      const w = vis.get(n) ?? 1
      if (w < 0.1)
        continue
      const p = proj(n.px, n.py, n.pz)
      items.push({ t: 'N', p, n, d: p.d, w })
    }
    items.sort((a, b) => b.d - a.d)

    const focusScale = lv === LOD_NEAR ? 1.8 : 1
    // 入场分级：未到自己的 revealAt 时 alpha 渐隐
    const elapsed = performance.now() - t0
    const revealOf = (n: SeaNode) => Math.max(0, Math.min(1, (elapsed - n.revealAt) / 500))

    for (const it of items) {
      if (it.t === 'L') {
        const { p1, p2, l, w } = it
        const rv = Math.min(revealOf(l.src), revealOf(l.tgt))
        if (rv <= 0)
          continue
        const fog = Math.min(1, Math.max(0.05, 300 / ((p1.d + p2.d) / 2))) * w * rv

        // 跨区边走 HEB 样条，同区边直线
        const wps = bundledWaypoints(l)
        cx.beginPath()
        cx.moveTo(p1.sx, p1.sy)
        if (wps.length > 0) {
          const pts = wps.map((wp) => {
            const pp = proj(wp.x, wp.y, wp.z)
            return { sx: pp.sx, sy: pp.sy }
          })
          // 起点 → 各途经点 → 终点，用二次贝塞尔串成平滑样条
          let cur = pts[0]!
          cx.lineTo((p1.sx + cur.sx) / 2, (p1.sy + cur.sy) / 2)
          for (let k = 0; k < pts.length; k++) {
            const nxt = pts[k + 1] ?? { sx: p2.sx, sy: p2.sy }
            cx.quadraticCurveTo(cur.sx, cur.sy, (cur.sx + nxt.sx) / 2, (cur.sy + nxt.sy) / 2)
            cur = nxt
          }
          cx.lineTo(p2.sx, p2.sy)
        }
        else {
          cx.lineTo(p2.sx, p2.sy)
        }
        cx.strokeStyle = `rgba(70,120,200,${fog * 0.34})`
        cx.lineWidth = Math.max(0.3, 1.1 * Math.min(p1.s, p2.s) * w)
        cx.stroke()

        // 箭头
        const ang = Math.atan2(p2.sy - p1.sy, p2.sx - p1.sx)
        const tr = cfg.nodeSize * p2.s + 2
        const ax = p2.sx - Math.cos(ang) * tr
        const ay = p2.sy - Math.sin(ang) * tr
        const az = Math.max(2, 4 * p2.s)
        cx.beginPath()
        cx.moveTo(ax, ay)
        cx.lineTo(ax - Math.cos(ang - 0.35) * az, ay - Math.sin(ang - 0.35) * az)
        cx.lineTo(ax - Math.cos(ang + 0.35) * az, ay - Math.sin(ang + 0.35) * az)
        cx.closePath()
        cx.fillStyle = `rgba(60,100,180,${fog * 0.45})`
        cx.fill()

        // 关系名：远景画必糊，只在 mid/near 且够近时画
        if (lv !== LOD_FAR && cfg.fontSize > 0 && Math.min(p1.s, p2.s) > 0.6 && w > 0.5) {
          const mx = (p1.sx + p2.sx) / 2
          const my = (p1.sy + p2.sy) / 2
          const ef = Math.max(5, cfg.fontSize * Math.min(p1.s, p2.s) * 0.9)
          cx.font = `${ef}px sans-serif`
          cx.fillStyle = `rgba(80,130,200,${fog * 0.45})`
          cx.textAlign = 'center'
          cx.textBaseline = 'middle'
          cx.fillText(l.relation, mx, my)
        }
      }
      else {
        const { p, n, w } = it
        const rv = revealOf(n)
        if (rv <= 0)
          continue
        const r = cfg.nodeSize * p.s * (n === selected ? focusScale : 1)
        const col = tc(n.type)
        const fog = Math.min(1, Math.max(0.15, 350 / p.d)) * w * rv
        const isH = n === hovered
        const isS = n === selected

        // 垂向锚线
        const pfloor = proj(n.px, FLOOR_Y, n.pz)
        cx.beginPath()
        cx.moveTo(p.sx, p.sy)
        cx.lineTo(pfloor.sx, pfloor.sy)
        cx.strokeStyle = `rgba(60,100,180,${fog * 0.08})`
        cx.lineWidth = 0.5
        cx.setLineDash([2, 4])
        cx.stroke()
        cx.setLineDash([])

        drawNodeGlow(p.sx, p.sy, r, col, fog, isH || isS)

        if (isS) {
          cx.beginPath()
          cx.arc(p.sx, p.sy, r + 3 * p.s, 0, Math.PI * 2)
          cx.strokeStyle = `${col}88`
          cx.lineWidth = 1.2
          cx.stroke()
        }

        // 标签分级：远景只标 hub，中/近景标出可见节点
        const wantLabel = lv === LOD_FAR ? w >= 1 : w >= 0.5
        if (cfg.fontSize > 0 && r > 2 && wantLabel) {
          const lf = Math.max(6, cfg.fontSize * p.s * 0.95)
          cx.font = `bold ${lf}px sans-serif`
          cx.fillStyle = `rgba(190,210,255,${fog * 0.8})`
          cx.textAlign = 'center'
          cx.textBaseline = 'top'
          cx.fillText(n.id, p.sx, p.sy + r + 2)
        }
      }
    }

    if (cfg.flowOn)
      drawFlow()

    if (hovered) {
      const hp = proj(hovered.px, hovered.py, hovered.pz)
      const hr = cfg.nodeSize * hp.s
      const txt = `${hovered.id} [${hovered.type}] w=${hovered.weight}`
      cx.font = '11px sans-serif'
      const tw = cx.measureText(txt).width
      const bx = hp.sx - tw / 2 - 7
      const by = hp.sy - hr - 26
      cx.fillStyle = 'rgba(4,8,16,0.92)'
      cx.strokeStyle = 'rgba(50,90,160,0.5)'
      cx.lineWidth = 1
      cx.beginPath()
      cx.roundRect(bx, by, tw + 14, 22, 4)
      cx.fill()
      cx.stroke()
      cx.fillStyle = '#aaccee'
      cx.textAlign = 'center'
      cx.textBaseline = 'middle'
      cx.fillText(txt, hp.sx, by + 11)
    }

    drawCompass()
  }
  function loop() {
    simulate()
    if (cfg.particlesOn)
      simParticles()
    if (cfg.flowOn)
      simFlow()
    if (cfg.planktonOn)
      simPlankton()
    draw()
    animId = requestAnimationFrame(loop)
  }

  // ── Hit test ──
  function findNode(sx: number, sy: number): SeaNode | null {
    let best: SeaNode | null = null
    let bestD = 900
    for (const n of nodes) {
      const p = proj(n.px, n.py, n.pz)
      const r = cfg.nodeSize * p.s + 5
      const d2 = (p.sx - sx) ** 2 + (p.sy - sy) ** 2
      if (d2 < r * r && d2 < bestD) {
        best = n
        bestD = d2
      }
    }
    return best
  }

  function selectNode(n: SeaNode) {
    selected = n
    // 选中即把该节点所属簇设为焦点：退出 near 后仍留在 mid，不会一下弹回大杂烩
    focusType = n.type
    syncFocusFromCanvas()
    let outC = 0
    let inC = 0
    const rels: string[] = []
    for (const l of links) {
      if (l.src === n) {
        outC++
        rels.push(`${n.id} → ${l.relation} → ${l.tgt.id}`)
      }
      if (l.tgt === n) {
        inC++
        rels.push(`${l.src.id} → ${l.relation} → ${n.id}`)
      }
    }
    onSelect({ id: n.id, type: n.type, weight: n.weight, outCount: outC, inCount: inC, relations: rels })
  }

  function buildSeaData(quints: Quintuple[]) {
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
    cmap = {}
    cidx = 0

    const maxDegree = Math.max(...[...degreeMap.values()], 1)
    nodes = []
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
      nodes.push(n)
      nm.set(id, n)
      tc(info.type)
    }

    links = []
    for (const q of quints) {
      const src = nm.get(q.subject)
      const tgt = nm.get(q.object)
      if (src && tgt)
        links.push({ src, tgt, relation: q.predicate })
    }

    const _types = [...new Set(nodes.map(n => n.type))]
    const _counts: Record<string, number> = {}
    for (const n of nodes)
      _counts[n.type] = (_counts[n.type] || 0) + 1
    onNodeCountChange(nodes.length, quints.length, sectors.length, _types, _counts)

    initPositions()
    initParticles()
    initRays()
    initFlow()
    initPlankton()
  }

  function resize() {
    const cv = canvasRef.value
    if (!cv)
      return
    const container = cv.parentElement
    if (!container)
      return
    dpr = devicePixelRatio || 1
    W = container.clientWidth
    H = container.clientHeight
    cv.width = W * dpr
    cv.height = H * dpr
    cv.style.width = `${W}px`
    cv.style.height = `${H}px`
    cx = cv.getContext('2d')
    if (cx)
      cx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  function setupEvents() {
    const cv = canvasRef.value
    if (!cv)
      return

    cv.addEventListener('contextmenu', e => e.preventDefault())

    cv.addEventListener('mousedown', (e) => {
      e.preventDefault()
      const rect0 = cv.getBoundingClientRect()
      // 先试扇区标题：命中则切焦点簇（mid 模式）
      if (e.button === 0 && !e.shiftKey) {
        const st = pickSector(e.clientX - rect0.left, e.clientY - rect0.top)
        if (st) {
          focusType = focusType === st ? null : st
          syncFocusFromCanvas()
          selected = null
          onSelect(null)
          return
        }
      }
      const n = findNode(e.clientX - rect0.left, e.clientY - rect0.top)
      if (e.button === 1 || (e.button === 0 && e.shiftKey) || e.button === 2) {
        panning = true
        rsx = e.clientX
        rsy = e.clientY
        panOX = panX
        panOY = panY
        cv.style.cursor = 'move'
      }
      else if (n) {
        dragging = n
        dragMoved = false
        prevMX = e.clientX
        prevMY = e.clientY
        cv.style.cursor = 'grabbing'
      }
      else {
        rotating = true
        rsx = e.clientX
        rsy = e.clientY
        rst = camT
        rsp = camP
        selected = null
        // 点空白 → 退出焦点簇，回到远景骨架
        focusType = null
        syncFocusFromCanvas()
        onSelect(null)
        cv.style.cursor = 'grabbing'
      }
    })

    cv.addEventListener('mousemove', (e) => {
      const rect = cv.getBoundingClientRect()
      if (dragging) {
        const dp = proj(dragging.px, dragging.py, dragging.pz)
        const scale = dp.d / 700
        const dx = e.clientX - prevMX
        const dy = e.clientY - prevMY
        if (Math.abs(dx) + Math.abs(dy) > 2)
          dragMoved = true
        const ct = Math.cos(camT)
        const st = Math.sin(camT)
        const cp = Math.cos(camP)
        const sp = Math.sin(camP)
        dragging.px += dx * scale * ct - dy * scale * sp * st
        dragging.pz += dx * scale * st + dy * scale * sp * ct
        dragging.py -= dy * scale * cp
        prevMX = e.clientX
        prevMY = e.clientY
      }
      else if (panning) {
        panX = panOX + (e.clientX - rsx)
        panY = panOY + (e.clientY - rsy)
      }
      else if (rotating) {
        camT = rst - (e.clientX - rsx) * 0.005
        camP = rsp - (e.clientY - rsy) * 0.005
      }
      else {
        hovered = findNode(e.clientX - rect.left, e.clientY - rect.top)
        cv.style.cursor = hovered ? 'pointer' : 'grab'
      }
    })

    cv.addEventListener('mouseup', () => {
      if (dragging) {
        if (!dragMoved)
          selectNode(dragging)
        dragging = null
      }
      rotating = false
      panning = false
      cv.style.cursor = 'grab'
    })

    cv.addEventListener('mouseleave', () => {
      rotating = false
      panning = false
      dragging = null
      hovered = null
    })

    cv.addEventListener('wheel', (e) => {
      e.preventDefault()
      camD *= e.deltaY > 0 ? 1.07 : 0.93
      camD = Math.max(80, Math.min(3000, camD))
    }, { passive: false })

    // Touch support
    let td = 0
    let tpan = false
    cv.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        const rect = cv.getBoundingClientRect()
        const t0 = e.touches[0]!
        const n = findNode(t0.clientX - rect.left, t0.clientY - rect.top)
        if (n) {
          dragging = n
          dragMoved = false
          prevMX = t0.clientX
          prevMY = t0.clientY
        }
        else {
          rotating = true
          rsx = t0.clientX
          rsy = t0.clientY
          rst = camT
          rsp = camP
        }
      }
      else if (e.touches.length === 2) {
        const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
        const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
        td = Math.sqrt(dx * dx + dy * dy)
      }
      else if (e.touches.length === 3) {
        tpan = true
        rsx = e.touches[0]!.clientX
        rsy = e.touches[0]!.clientY
        panOX = panX
        panOY = panY
      }
    }, { passive: true })

    cv.addEventListener('touchmove', (e) => {
      e.preventDefault()
      if (dragging && e.touches.length === 1) {
        const t0 = e.touches[0]!
        const dp = proj(dragging.px, dragging.py, dragging.pz)
        const scale = dp.d / 700
        const dx = t0.clientX - prevMX
        const dy = t0.clientY - prevMY
        if (Math.abs(dx) + Math.abs(dy) > 2)
          dragMoved = true
        const ct = Math.cos(camT)
        const st = Math.sin(camT)
        const cp = Math.cos(camP)
        const sp = Math.sin(camP)
        dragging.px += dx * scale * ct - dy * scale * sp * st
        dragging.pz += dx * scale * st + dy * scale * sp * ct
        dragging.py -= dy * scale * cp
        prevMX = t0.clientX
        prevMY = t0.clientY
      }
      else if (e.touches.length === 1 && rotating) {
        camT = rst - (e.touches[0]!.clientX - rsx) * 0.005
        camP = rsp - (e.touches[0]!.clientY - rsy) * 0.005
      }
      else if (e.touches.length === 2) {
        const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
        const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
        const nd = Math.sqrt(dx * dx + dy * dy)
        camD *= td / nd
        camD = Math.max(80, Math.min(3000, camD))
        td = nd
      }
      else if (e.touches.length === 3 && tpan) {
        panX = panOX + (e.touches[0]!.clientX - rsx)
        panY = panOY + (e.touches[0]!.clientY - rsy)
      }
    }, { passive: false })

    cv.addEventListener('touchend', () => {
      if (dragging && !dragMoved)
        selectNode(dragging)
      rotating = false
      dragging = null
      tpan = false
    })
  }

  // ── 对外 API（原壳侧 onMounted/onUnmounted/watch 的画布部分收敛于此）──
  let _resizeObserver: ResizeObserver | null = null

  function setup(): void {
    t0 = performance.now()
    resize()
    setupEvents()

    const cv = canvasRef.value
    if (cv?.parentElement) {
      _resizeObserver = new ResizeObserver(() => resize())
      _resizeObserver.observe(cv.parentElement)
    }
  }

  function dispose(): void {
    if (animId)
      cancelAnimationFrame(animId)
    if (_resizeObserver)
      _resizeObserver.disconnect()
  }

  function start(): void {
    if (animId)
      cancelAnimationFrame(animId)
    animId = requestAnimationFrame(loop)
  }

  function setFocusType(t: string | null): void {
    focusType = t
  }

  function getFocusType(): string | null {
    return focusType
  }

  function isNearView(): boolean {
    return !!selected
  }

  function getNodeCount(): number {
    return nodes.length
  }

  function focusTopByWeight(): string | null {
    const top = [...nodes].sort((a, b) => b.weight - a.weight)[0]
    focusType = top?.type ?? null
    return focusType
  }

  return {
    setup,
    dispose,
    buildSeaData,
    start,
    setFocusType,
    getFocusType,
    isNearView,
    getNodeCount,
    focusTopByWeight,
    colorOf: tc,
  }
}
