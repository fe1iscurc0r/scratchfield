import type { Sector } from './layout'
/**
 * mind 渲染器 · 共享状态对象（工单209 任务二第二批）。
 * 原 createMindRenderer 内 34 个闭包 let 收敛为一个可传递的状态对象；
 * 字段与初始值逐项对应原声明，语义零变化。
 */
import type { FlowDot, Particle, Plankton, Ray, SeaLink, SeaNode } from './types'

/** renderer deps 的回调挂载（工单209 第二批：模块经 S 取用） */
export interface MindCallbacks {
  onNodeCountChange: (shown: number, total: number, sectors: number, types: string[], counts: Record<string, number>) => void
  onFocusChange: (t: string | null) => void
  onSelect: (info: unknown) => void
}

export interface MindState {
  W: number
  H: number
  dpr: number
  cx: CanvasRenderingContext2D | null
  animId: number
  t0: number
  nodes: SeaNode[]
  links: SeaLink[]
  particles: Particle[]
  rays: Ray[]
  flowParts: FlowDot[]
  plankton: Plankton[]
  cmap: Record<string, string>
  cidx: number
  camT: number
  camP: number
  camD: number
  panX: number
  panY: number
  rotating: boolean
  panning: boolean
  rsx: number
  rsy: number
  rst: number
  rsp: number
  panOX: number
  panOY: number
  dragging: SeaNode | null
  dragMoved: boolean
  prevMX: number
  prevMY: number
  hovered: SeaNode | null
  selected: SeaNode | null
  sectors: Sector[]
  focusType: string | null
  _resizeObserver: ResizeObserver | null
  /** deps 回调（构造后由 renderer 注入；模块函数经 S 调用） */
  cb: MindCallbacks
}

export function createMindState(): MindState {
  return {
    W: 0,
    H: 0,
    dpr: 1,
    cx: null,
    animId: 0,
    t0: 0,
    nodes: [],
    links: [],
    particles: [],
    rays: [],
    flowParts: [],
    plankton: [],
    cmap: {},
    cidx: 0,
    camT: 0.5,
    camP: 0.45,
    camD: 550,
    panX: 0,
    panY: 0,
    rotating: false,
    panning: false,
    rsx: 0,
    rsy: 0,
    rst: 0,
    rsp: 0,
    panOX: 0,
    panOY: 0,
    dragging: null,
    dragMoved: false,
    prevMX: 0,
    prevMY: 0,
    hovered: null,
    selected: null,
    sectors: [],
    focusType: null,
    _resizeObserver: null,
    cb: { onNodeCountChange: () => {}, onFocusChange: () => {}, onSelect: () => {} },
  }
}
