/**
 * mind 视图 · 绘制原语簇（工单209 任务二第二批）。
 * 自 renderer.ts 搬出；函数体原样（已 S 化），S: MindState 首参传递共享状态。
 */
import type { MindState } from './state'
import type { ProjFn, SeaLink } from './types'
import { FLOOR_Y, SURFACE_H } from './constants'
import { LOD_FAR, lodLevel } from './visibility'

/** 绘制簇需要的视图配置（renderer 的 cfg 的形状子集） */
export interface DrawCfg {
  hScale: number
  sway: number
  fontSize: number
  nodeSize: number
}

/** 束流聚合：同一对簇的边数 → 束宽 */
interface Bundle {
  a: number
  b: number
  count: number
}

export function drawFloor(S: MindState, proj: ProjFn) {
  if (!S.cx)
    return
  const gridN = 10
  const gridS = 30
  const half = gridN * gridS
  S.cx.strokeStyle = 'rgba(30,60,120,0.18)'
  S.cx.lineWidth = 0.7
  for (let i = -gridN; i <= gridN; i++) {
    const p1 = proj(i * gridS, FLOOR_Y, -half)
    const p2 = proj(i * gridS, FLOOR_Y, half)
    const p3 = proj(-half, FLOOR_Y, i * gridS)
    const p4 = proj(half, FLOOR_Y, i * gridS)
    S.cx.beginPath()
    S.cx.moveTo(p1.sx, p1.sy)
    S.cx.lineTo(p2.sx, p2.sy)
    S.cx.stroke()
    S.cx.beginPath()
    S.cx.moveTo(p3.sx, p3.sy)
    S.cx.lineTo(p4.sx, p4.sy)
    S.cx.stroke()
  }
}

export function drawSurface(S: MindState, cfg: DrawCfg, proj: ProjFn) {
  if (!S.cx)
    return
  const surfY = SURFACE_H * cfg.hScale
  const half = 300
  const corners = [[-half, surfY, -half], [half, surfY, -half], [half, surfY, half], [-half, surfY, half]] as const
  const pc = corners.map(c => proj(c[0], c[1], c[2]))
  S.cx.beginPath()
  S.cx.moveTo(pc[0]!.sx, pc[0]!.sy)
  for (let i = 1; i < 4; i++)
    S.cx.lineTo(pc[i]!.sx, pc[i]!.sy)
  S.cx.closePath()
  S.cx.fillStyle = 'rgba(20,80,180,0.06)'
  S.cx.fill()
  S.cx.strokeStyle = 'rgba(40,100,200,0.15)'
  S.cx.lineWidth = 1
  S.cx.stroke()
  S.cx.strokeStyle = 'rgba(50,120,220,0.08)'
  S.cx.lineWidth = 0.5
  const now = (performance.now() - S.t0) * 0.0005
  for (let i = 0; i < 6; i++) {
    const off = (i / 6 - 0.5) * half * 1.8
    const p1 = proj(-half, surfY, off + Math.sin(now + i) * 10)
    const p2 = proj(half, surfY, off + Math.sin(now + i + 2) * 10)
    S.cx.beginPath()
    S.cx.moveTo(p1.sx, p1.sy)
    S.cx.lineTo(p2.sx, p2.sy)
    S.cx.stroke()
  }
}

export function pickSector(S: MindState, proj: ProjFn, sx: number, sy: number): string | null {
  let best: string | null = null
  let bestD = 3600 // 60px 命中半径
  for (const sc of S.sectors) {
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

export function drawCompass(S: MindState) {
  if (!S.cx)
    return
  const ox = S.W - 70
  const oy = S.H - 70
  const len = 40
  const ct = Math.cos(S.camT)
  const st = Math.sin(S.camT)
  const cp = Math.cos(S.camP)
  const sp = Math.sin(S.camP)
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
  S.cx.beginPath()
  S.cx.arc(ox, oy, 52, 0, Math.PI * 2)
  S.cx.fillStyle = 'rgba(6,12,24,0.7)'
  S.cx.fill()
  S.cx.strokeStyle = 'rgba(50,90,160,0.3)'
  S.cx.lineWidth = 1
  S.cx.stroke()
  for (const a of axes) {
    const p = projAxis(a.x, a.y, a.z)
    S.cx.beginPath()
    S.cx.moveTo(ox, oy)
    S.cx.lineTo(p.sx, p.sy)
    S.cx.strokeStyle = a.color
    S.cx.lineWidth = 2
    S.cx.stroke()
    const ang = Math.atan2(p.sy - oy, p.sx - ox)
    S.cx.beginPath()
    S.cx.moveTo(p.sx, p.sy)
    S.cx.lineTo(p.sx - Math.cos(ang - 0.4) * 8, p.sy - Math.sin(ang - 0.4) * 8)
    S.cx.lineTo(p.sx - Math.cos(ang + 0.4) * 8, p.sy - Math.sin(ang + 0.4) * 8)
    S.cx.closePath()
    S.cx.fillStyle = a.color
    S.cx.fill()
    const lx = p.sx + Math.cos(ang) * 12
    const ly = p.sy + Math.sin(ang) * 12
    S.cx.font = 'bold 9px sans-serif'
    S.cx.fillStyle = a.color
    S.cx.textAlign = 'center'
    S.cx.textBaseline = 'middle'
    S.cx.fillText(a.label, lx, ly)
  }
}

export function drawNodeGlow(S: MindState, sx: number, sy: number, r: number, col: string, fog: number, isHov: boolean) {
  if (!S.cx)
    return
  if (r > 2) {
    const gr = r * 4
    const gg = S.cx.createRadialGradient(sx, sy, r * 0.3, sx, sy, gr)
    gg.addColorStop(0, `${col}40`)
    gg.addColorStop(0.3, `${col}18`)
    gg.addColorStop(0.7, `${col}08`)
    gg.addColorStop(1, 'transparent')
    S.cx.beginPath()
    S.cx.arc(sx, sy, gr, 0, Math.PI * 2)
    S.cx.fillStyle = gg
    S.cx.fill()
  }
  S.cx.beginPath()
  S.cx.arc(sx, sy, Math.max(1.5, r), 0, Math.PI * 2)
  S.cx.globalAlpha = Math.max(0.3, fog)
  S.cx.fillStyle = isHov ? '#fff' : col
  S.cx.fill()
  if (r > 3) {
    const hx = sx - r * 0.28
    const hy = sy - r * 0.28
    const hr = r * 0.38
    const ig = S.cx.createRadialGradient(hx, hy, 0, hx, hy, hr)
    ig.addColorStop(0, `rgba(255,255,255,${isHov ? 0.6 : 0.3 * fog})`)
    ig.addColorStop(1, 'transparent')
    S.cx.beginPath()
    S.cx.arc(hx, hy, hr, 0, Math.PI * 2)
    S.cx.fillStyle = ig
    S.cx.fill()
  }
  S.cx.globalAlpha = 1
}

export function hexA(hex: string, a: number): string {
  if (hex.startsWith('rgba') || hex.startsWith('rgb('))
    return hex
  const h = hex.replace('#', '')
  const r = Number.parseInt(h.slice(0, 2), 16)
  const g = Number.parseInt(h.slice(2, 4), 16)
  const b = Number.parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${Math.max(0, Math.min(1, a))})`
}

export function drawSectors(S: MindState, cfg: DrawCfg, proj: ProjFn) {
  if (!S.cx || S.sectors.length === 0)
    return
  const lv = lodLevel(S)

  for (const sc of S.sectors) {
    const isFocus = sc.type === S.focusType || S.selected?.type === sc.type
    // 星云底盘
    const p = proj(sc.cx, SURFACE_H * 0.35, sc.cz)
    const rr = sc.radius * p.s
    if (rr > 2) {
      const a = isFocus ? 0.2 : 0.08
      const g = S.cx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, rr)
      g.addColorStop(0, hexA(sc.color, a))
      g.addColorStop(0.65, hexA(sc.color, a * 0.4))
      g.addColorStop(1, 'transparent')
      S.cx.beginPath()
      S.cx.arc(p.sx, p.sy, rr, 0, Math.PI * 2)
      S.cx.fillStyle = g
      S.cx.fill()
    }

    // 外环标题：沿扇区中轴往外推
    const outerR = Math.hypot(sc.cx, sc.cz) + sc.radius + 70
    const tp = proj(Math.cos(sc.angle) * outerR, SURFACE_H * 0.5, Math.sin(sc.angle) * outerR)
    if (cfg.fontSize > 0 && p.s > 0.22) {
      const fs = Math.max(9, 12 * p.s)
      const label = `${sc.type} (${sc.count})`
      S.cx.font = `600 ${fs}px sans-serif`
      S.cx.textAlign = 'center'
      S.cx.textBaseline = 'middle'
      S.cx.fillStyle = hexA(sc.color, isFocus ? 0.95 : lv === LOD_FAR ? 0.6 : 0.3)
      S.cx.fillText(label, tp.sx, tp.sy)
      if (isFocus) {
        const tw = S.cx.measureText(label).width
        S.cx.beginPath()
        S.cx.moveTo(tp.sx - tw / 2, tp.sy + fs * 0.8)
        S.cx.lineTo(tp.sx + tw / 2, tp.sy + fs * 0.8)
        S.cx.strokeStyle = hexA(sc.color, 0.5)
        S.cx.lineWidth = 1
        S.cx.stroke()
      }
    }
  }
}

export function bundledWaypoints(S: MindState, l: SeaLink) {
  const a = S.sectors[l.src.typeIndex]
  const b = S.sectors[l.tgt.typeIndex]
  if (!a || !b || a === b)
    return [] as Array<{ x: number, y: number, z: number }>
  return [
    { x: a.cx, y: SURFACE_H * 0.42, z: a.cz },
    { x: (a.cx + b.cx) / 2, y: SURFACE_H * 0.62, z: (a.cz + b.cz) / 2 },
    { x: b.cx, y: SURFACE_H * 0.42, z: b.cz },
  ]
}

export function buildBundles(S: MindState): Bundle[] {
  const m = new Map<string, Bundle>()
  for (const l of S.links) {
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

export function drawBundles(S: MindState, proj: ProjFn) {
  if (!S.cx || S.sectors.length === 0)
    return
  for (const bd of buildBundles(S)) {
    const A = S.sectors[bd.a]
    const B = S.sectors[bd.b]
    if (!A || !B)
      continue
    const p1 = proj(A.cx, SURFACE_H * 0.42, A.cz)
    const p2 = proj(B.cx, SURFACE_H * 0.42, B.cz)
    const mid = proj((A.cx + B.cx) / 2, SURFACE_H * 0.62, (A.cz + B.cz) / 2)
    // 束宽 ∝ 边数（sqrt 压缩，防一条巨束糊满屏）
    const w = Math.max(0.6, Math.sqrt(bd.count) * 0.9 * ((p1.s + p2.s) / 2))
    const fog = Math.min(1, Math.max(0.08, 300 / ((p1.d + p2.d) / 2)))
    S.cx.beginPath()
    S.cx.moveTo(p1.sx, p1.sy)
    S.cx.quadraticCurveTo(mid.sx, mid.sy, p2.sx, p2.sy)
    S.cx.strokeStyle = `rgba(90,150,230,${fog * 0.3})`
    S.cx.lineWidth = w
    S.cx.stroke()
    S.cx.beginPath()
    S.cx.moveTo(p1.sx, p1.sy)
    S.cx.quadraticCurveTo(mid.sx, mid.sy, p2.sx, p2.sy)
    S.cx.strokeStyle = `rgba(150,200,255,${fog * 0.22})`
    S.cx.lineWidth = Math.max(0.4, w * 0.3)
    S.cx.stroke()
  }
}
