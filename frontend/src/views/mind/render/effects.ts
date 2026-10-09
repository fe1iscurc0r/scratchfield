/**
 * mind 视图 · 环境特效层（粒子 / 光柱 / 流动粒子 / 浮游）。
 * 自 views/mind/renderer.ts 拆出（工单209 任务二）。
 *
 * **纯移动**：函数体逐字节搬运，仅把原闭包变量改为显式参数 ——
 * 读取型（cx/rays/cfg/t0/links）→ 同名参数；初始化型（particles/rays/flowParts/plankton）
 * 原本**重新赋值**闭包变量，这里改为**返回新数组**，由调用方接住赋值，语义等价。
 */
import type { FlowDot, Particle, Plankton, ProjFn, Ray, SeaLink } from './types'
import { FLOOR_Y, SURFACE_H } from './constants'

/** 本模块只读取 cfg.hScale */
export interface EffectsCfg {
  hScale: number
}

// ── Particle system ──
export function initParticles(): Particle[] {
  const particles: Particle[] = []
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
  return particles
}

export function simParticles(particles: Particle[], cfg: EffectsCfg): void {
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

export function drawParticles(
  cx: CanvasRenderingContext2D | null,
  particles: Particle[],
  proj: ProjFn,
): void {
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
export function initRays(): Ray[] {
  const rays: Ray[] = []
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
  return rays
}

export function drawRays(
  cx: CanvasRenderingContext2D | null,
  rays: Ray[],
  cfg: EffectsCfg,
  t0: number,
  proj: ProjFn,
): void {
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
export function initFlow(links: SeaLink[]): FlowDot[] {
  const flowParts: FlowDot[] = []
  for (const l of links) {
    if (Math.random() < 0.35)
      flowParts.push({ link: l, t: Math.random(), speed: 0.0008 + Math.random() * 0.0012, size: 0.5 + Math.random() * 0.5 })
  }
  return flowParts
}

export function simFlow(flowParts: FlowDot[]): void {
  for (const f of flowParts) {
    f.t += f.speed
    if (f.t > 1)
      f.t -= 1
  }
}

export function drawFlow(
  cx: CanvasRenderingContext2D | null,
  flowParts: FlowDot[],
  t0: number,
  proj: ProjFn,
): void {
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
export function spawnPlankton(): Plankton {
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

export function initPlankton(): Plankton[] {
  const plankton: Plankton[] = []
  for (let i = 0; i < 10; i++) {
    const p = spawnPlankton()
    p.life = Math.floor(Math.random() * p.maxLife)
    plankton.push(p)
  }
  return plankton
}

export function simPlankton(plankton: Plankton[], cfg: EffectsCfg, t0: number): void {
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

export function drawPlankton(
  cx: CanvasRenderingContext2D | null,
  plankton: Plankton[],
  proj: ProjFn,
): void {
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
