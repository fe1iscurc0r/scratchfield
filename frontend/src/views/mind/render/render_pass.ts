/**
 * mind 视图 · 帧绘制编排（工单209 任务二第二批）：draw() 单函数搬出。
 * 依赖：primitives/effects 各模块 + tc/proj/cfg 由 renderer 经参数传入。
 */
import type { MindState } from './state'
import type { ProjFn, ProjResult, SeaLink, SeaNode } from './types'
import { FLOOR_Y } from './constants'
import { drawFlow, drawParticles, drawPlankton, drawRays } from './effects'
import { bundledWaypoints, drawBundles, drawCompass, drawFloor, drawNodeGlow, drawSectors, drawSurface } from './primitives'
import { LOD_FAR, LOD_NEAR, lodLevel, visibility } from './visibility'

export interface DrawDeps {
  tc: (t: string) => string
  proj: ProjFn
  cfg: { hScale: number, sway: number, fontSize: number, nodeSize: number, raysOn: boolean, particlesOn: boolean, flowOn: boolean, planktonOn: boolean }
}

export function draw(S: MindState, d: DrawDeps) {
  if (!S.cx)
    return
  const bg = S.cx.createLinearGradient(0, 0, 0, S.H)
  bg.addColorStop(0, '#0a1525')
  bg.addColorStop(0.3, '#06101c')
  bg.addColorStop(0.7, '#040a14')
  bg.addColorStop(1, '#020608')
  S.cx.fillStyle = bg
  S.cx.fillRect(0, 0, S.W, S.H)

  drawFloor(S, d.proj)
  drawSurface(S, d.cfg, d.proj)
  if (d.cfg.raysOn)
    drawRays(S.cx, S.rays, d.cfg, S.t0, d.proj)
  if (d.cfg.particlesOn)
    drawParticles(S.cx, S.particles, d.proj)
  if (d.cfg.planktonOn)
    drawPlankton(S.cx, S.plankton, d.proj)

  const lv = lodLevel(S)
  const vis = visibility(S)

  // 簇底盘在最下层；远景再叠捆绑束
  drawSectors(S, d.cfg, d.proj)
  if (lv === LOD_FAR)
    drawBundles(S, d.proj)

  // 收集 item（远→近排序）
  interface LinkItem { t: 'L', p1: ProjResult, p2: ProjResult, l: SeaLink, d: number, w: number }
  interface NodeItem { t: 'N', p: ProjResult, n: SeaNode, d: number, w: number }
  const items: Array<LinkItem | NodeItem> = []

  for (const l of S.links) {
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
    const p1 = d.proj(l.src.px, l.src.py, l.src.pz)
    const p2 = d.proj(l.tgt.px, l.tgt.py, l.tgt.pz)
    items.push({ t: 'L', p1, p2, l, d: (p1.d + p2.d) / 2, w })
  }

  for (const n of S.nodes) {
    const w = vis.get(n) ?? 1
    if (w < 0.1)
      continue
    const p = d.proj(n.px, n.py, n.pz)
    items.push({ t: 'N', p, n, d: p.d, w })
  }
  items.sort((a, b) => b.d - a.d)

  const focusScale = lv === LOD_NEAR ? 1.8 : 1
  // 入场分级：未到自己的 revealAt 时 alpha 渐隐
  const elapsed = performance.now() - S.t0
  const revealOf = (n: SeaNode) => Math.max(0, Math.min(1, (elapsed - n.revealAt) / 500))

  for (const it of items) {
    if (it.t === 'L') {
      const { p1, p2, l, w } = it
      const rv = Math.min(revealOf(l.src), revealOf(l.tgt))
      if (rv <= 0)
        continue
      const fog = Math.min(1, Math.max(0.05, 300 / ((p1.d + p2.d) / 2))) * w * rv

      // 跨区边走 HEB 样条，同区边直线
      const wps = bundledWaypoints(S, l)
      S.cx.beginPath()
      S.cx.moveTo(p1.sx, p1.sy)
      if (wps.length > 0) {
        const pts = wps.map((wp) => {
          const pp = d.proj(wp.x, wp.y, wp.z)
          return { sx: pp.sx, sy: pp.sy }
        })
        // 起点 → 各途经点 → 终点，用二次贝塞尔串成平滑样条
        let cur = pts[0]!
        S.cx.lineTo((p1.sx + cur.sx) / 2, (p1.sy + cur.sy) / 2)
        for (let k = 0; k < pts.length; k++) {
          const nxt = pts[k + 1] ?? { sx: p2.sx, sy: p2.sy }
          S.cx.quadraticCurveTo(cur.sx, cur.sy, (cur.sx + nxt.sx) / 2, (cur.sy + nxt.sy) / 2)
          cur = nxt
        }
        S.cx.lineTo(p2.sx, p2.sy)
      }
      else {
        S.cx.lineTo(p2.sx, p2.sy)
      }
      S.cx.strokeStyle = `rgba(70,120,200,${fog * 0.34})`
      S.cx.lineWidth = Math.max(0.3, 1.1 * Math.min(p1.s, p2.s) * w)
      S.cx.stroke()

      // 箭头
      const ang = Math.atan2(p2.sy - p1.sy, p2.sx - p1.sx)
      const tr = d.cfg.nodeSize * p2.s + 2
      const ax = p2.sx - Math.cos(ang) * tr
      const ay = p2.sy - Math.sin(ang) * tr
      const az = Math.max(2, 4 * p2.s)
      S.cx.beginPath()
      S.cx.moveTo(ax, ay)
      S.cx.lineTo(ax - Math.cos(ang - 0.35) * az, ay - Math.sin(ang - 0.35) * az)
      S.cx.lineTo(ax - Math.cos(ang + 0.35) * az, ay - Math.sin(ang + 0.35) * az)
      S.cx.closePath()
      S.cx.fillStyle = `rgba(60,100,180,${fog * 0.45})`
      S.cx.fill()

      // 关系名：远景画必糊，只在 mid/near 且够近时画
      if (lv !== LOD_FAR && d.cfg.fontSize > 0 && Math.min(p1.s, p2.s) > 0.6 && w > 0.5) {
        const mx = (p1.sx + p2.sx) / 2
        const my = (p1.sy + p2.sy) / 2
        const ef = Math.max(5, d.cfg.fontSize * Math.min(p1.s, p2.s) * 0.9)
        S.cx.font = `${ef}px sans-serif`
        S.cx.fillStyle = `rgba(80,130,200,${fog * 0.45})`
        S.cx.textAlign = 'center'
        S.cx.textBaseline = 'middle'
        S.cx.fillText(l.relation, mx, my)
      }
    }
    else {
      const { p, n, w } = it
      const rv = revealOf(n)
      if (rv <= 0)
        continue
      const r = d.cfg.nodeSize * p.s * (n === S.selected ? focusScale : 1)
      const col = d.tc(n.type)
      const fog = Math.min(1, Math.max(0.15, 350 / p.d)) * w * rv
      const isH = n === S.hovered
      const isS = n === S.selected

      // 垂向锚线
      const pfloor = d.proj(n.px, FLOOR_Y, n.pz)
      S.cx.beginPath()
      S.cx.moveTo(p.sx, p.sy)
      S.cx.lineTo(pfloor.sx, pfloor.sy)
      S.cx.strokeStyle = `rgba(60,100,180,${fog * 0.08})`
      S.cx.lineWidth = 0.5
      S.cx.setLineDash([2, 4])
      S.cx.stroke()
      S.cx.setLineDash([])

      drawNodeGlow(S, p.sx, p.sy, r, col, fog, isH || isS)

      if (isS) {
        S.cx.beginPath()
        S.cx.arc(p.sx, p.sy, r + 3 * p.s, 0, Math.PI * 2)
        S.cx.strokeStyle = `${col}88`
        S.cx.lineWidth = 1.2
        S.cx.stroke()
      }

      // 标签分级：远景只标 hub，中/近景标出可见节点
      const wantLabel = lv === LOD_FAR ? w >= 1 : w >= 0.5
      if (d.cfg.fontSize > 0 && r > 2 && wantLabel) {
        const lf = Math.max(6, d.cfg.fontSize * p.s * 0.95)
        S.cx.font = `bold ${lf}px sans-serif`
        S.cx.fillStyle = `rgba(190,210,255,${fog * 0.8})`
        S.cx.textAlign = 'center'
        S.cx.textBaseline = 'top'
        S.cx.fillText(n.id, p.sx, p.sy + r + 2)
      }
    }
  }

  if (d.cfg.flowOn)
    drawFlow(S.cx, S.flowParts, S.t0, d.proj)

  if (S.hovered) {
    const hp = d.proj(S.hovered.px, S.hovered.py, S.hovered.pz)
    const hr = d.cfg.nodeSize * hp.s
    const txt = `${S.hovered.id} [${S.hovered.type}] w=${S.hovered.weight}`
    S.cx.font = '11px sans-serif'
    const tw = S.cx.measureText(txt).width
    const bx = hp.sx - tw / 2 - 7
    const by = hp.sy - hr - 26
    S.cx.fillStyle = 'rgba(4,8,16,0.92)'
    S.cx.strokeStyle = 'rgba(50,90,160,0.5)'
    S.cx.lineWidth = 1
    S.cx.beginPath()
    S.cx.roundRect(bx, by, tw + 14, 22, 4)
    S.cx.fill()
    S.cx.stroke()
    S.cx.fillStyle = '#aaccee'
    S.cx.textAlign = 'center'
    S.cx.textBaseline = 'middle'
    S.cx.fillText(txt, hp.sx, by + 11)
  }

  drawCompass(S)
}
