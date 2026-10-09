/**
 * mind 渲染器 · 内部类型（自 views/mind/renderer.ts 拆出，工单209 任务二）。
 * **纯移动**：接口定义逐字节搬运，仅补 `export`（模块化必需）与去掉一级缩进。
 */

export interface Quintuple {
  subject: string
  subjectType: string
  predicate: string
  object: string
  objectType: string
  /** with_degree=true 时后端回填的实体连接数（卷148 度数下沉） */
  degree?: number
}

export interface SeaNode {
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

export interface SeaLink {
  src: SeaNode
  tgt: SeaNode
  relation: string
}

export interface Particle {
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

export interface Ray {
  x: number
  z: number
  radius: number
  phase: number
  freq: number
  swayAmp: number
  alpha: number
}

export interface FlowDot {
  link: SeaLink
  t: number
  speed: number
  size: number
}

export interface Plankton {
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

/** 投影函数（renderer 内的 proj，绘制类函数按需接收） */
export interface ProjResult {
  sx: number
  sy: number
  s: number
  d: number
}

export type ProjFn = (x: number, y: number, z: number) => ProjResult
