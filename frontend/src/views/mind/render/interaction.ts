/**
 * mind 视图 · 交互簇（工单209 任务二第二批）：命中检测/选中/事件绑定。
 * 自 renderer.ts 搬出；S: MindState 传递共享状态，deps 回调经 S.cb。
 */
import type { MindState } from './state'
import type { ProjFn, SeaNode } from './types'
import { pickSector } from './primitives'
import { syncFocusFromCanvas } from './visibility'

export interface InteractCfg {
  nodeSize: number
}

export interface InteractDeps {
  findNode: (sx: number, sy: number) => SeaNode | null
  proj: ProjFn
}

export function findNode(S: MindState, cfg: InteractCfg, proj: ProjFn, sx: number, sy: number): SeaNode | null {
  let best: SeaNode | null = null
  let bestD = 900
  for (const n of S.nodes) {
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

export function selectNode(S: MindState, n: SeaNode) {
  S.selected = n
  // 选中即把该节点所属簇设为焦点：退出 near 后仍留在 mid，不会一下弹回大杂烩
  S.focusType = n.type
  syncFocusFromCanvas(S)
  let outC = 0
  let inC = 0
  const rels: string[] = []
  for (const l of S.links) {
    if (l.src === n) {
      outC++
      rels.push(`${n.id} → ${l.relation} → ${l.tgt.id}`)
    }
    if (l.tgt === n) {
      inC++
      rels.push(`${l.src.id} → ${l.relation} → ${n.id}`)
    }
  }
  S.cb.onSelect({ id: n.id, type: n.type, weight: n.weight, outCount: outC, inCount: inC, relations: rels })
}

export function setupEvents(S: MindState, cv: HTMLCanvasElement, cfg: InteractCfg, deps: InteractDeps) {
  cv.addEventListener('contextmenu', e => e.preventDefault())

  cv.addEventListener('mousedown', (e) => {
    e.preventDefault()
    const rect0 = cv.getBoundingClientRect()
    // 先试扇区标题：命中则切焦点簇（mid 模式）
    if (e.button === 0 && !e.shiftKey) {
      const st = pickSector(S, deps.proj, e.clientX - rect0.left, e.clientY - rect0.top)
      if (st) {
        S.focusType = S.focusType === st ? null : st
        syncFocusFromCanvas(S)
        S.selected = null
        S.cb.onSelect(null)
        return
      }
    }
    const n = deps.findNode(e.clientX - rect0.left, e.clientY - rect0.top)
    if (e.button === 1 || (e.button === 0 && e.shiftKey) || e.button === 2) {
      S.panning = true
      S.rsx = e.clientX
      S.rsy = e.clientY
      S.panOX = S.panX
      S.panOY = S.panY
      cv.style.cursor = 'move'
    }
    else if (n) {
      S.dragging = n
      S.dragMoved = false
      S.prevMX = e.clientX
      S.prevMY = e.clientY
      cv.style.cursor = 'grabbing'
    }
    else {
      S.rotating = true
      S.rsx = e.clientX
      S.rsy = e.clientY
      S.rst = S.camT
      S.rsp = S.camP
      S.selected = null
      // 点空白 → 退出焦点簇，回到远景骨架
      S.focusType = null
      syncFocusFromCanvas(S)
      S.cb.onSelect(null)
      cv.style.cursor = 'grabbing'
    }
  })

  cv.addEventListener('mousemove', (e) => {
    const rect = cv.getBoundingClientRect()
    if (S.dragging) {
      const dp = deps.proj(S.dragging.px, S.dragging.py, S.dragging.pz)
      const scale = dp.d / 700
      const dx = e.clientX - S.prevMX
      const dy = e.clientY - S.prevMY
      if (Math.abs(dx) + Math.abs(dy) > 2)
        S.dragMoved = true
      const ct = Math.cos(S.camT)
      const st = Math.sin(S.camT)
      const cp = Math.cos(S.camP)
      const sp = Math.sin(S.camP)
      S.dragging.px += dx * scale * ct - dy * scale * sp * st
      S.dragging.pz += dx * scale * st + dy * scale * sp * ct
      S.dragging.py -= dy * scale * cp
      S.prevMX = e.clientX
      S.prevMY = e.clientY
    }
    else if (S.panning) {
      S.panX = S.panOX + (e.clientX - S.rsx)
      S.panY = S.panOY + (e.clientY - S.rsy)
    }
    else if (S.rotating) {
      S.camT = S.rst - (e.clientX - S.rsx) * 0.005
      S.camP = S.rsp - (e.clientY - S.rsy) * 0.005
    }
    else {
      S.hovered = deps.findNode(e.clientX - rect.left, e.clientY - rect.top)
      cv.style.cursor = S.hovered ? 'pointer' : 'grab'
    }
  })

  cv.addEventListener('mouseup', () => {
    if (S.dragging) {
      if (!S.dragMoved)
        selectNode(S, S.dragging)
      S.dragging = null
    }
    S.rotating = false
    S.panning = false
    cv.style.cursor = 'grab'
  })

  cv.addEventListener('mouseleave', () => {
    S.rotating = false
    S.panning = false
    S.dragging = null
    S.hovered = null
  })

  cv.addEventListener('wheel', (e) => {
    e.preventDefault()
    S.camD *= e.deltaY > 0 ? 1.07 : 0.93
    S.camD = Math.max(80, Math.min(3000, S.camD))
  }, { passive: false })

  // Touch support
  let td = 0
  let tpan = false
  cv.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      const rect = cv.getBoundingClientRect()
      const t0 = e.touches[0]!
      const n = deps.findNode(t0.clientX - rect.left, t0.clientY - rect.top)
      if (n) {
        S.dragging = n
        S.dragMoved = false
        S.prevMX = t0.clientX
        S.prevMY = t0.clientY
      }
      else {
        S.rotating = true
        S.rsx = t0.clientX
        S.rsy = t0.clientY
        S.rst = S.camT
        S.rsp = S.camP
      }
    }
    else if (e.touches.length === 2) {
      const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
      const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
      td = Math.sqrt(dx * dx + dy * dy)
    }
    else if (e.touches.length === 3) {
      tpan = true
      S.rsx = e.touches[0]!.clientX
      S.rsy = e.touches[0]!.clientY
      S.panOX = S.panX
      S.panOY = S.panY
    }
  }, { passive: true })

  cv.addEventListener('touchmove', (e) => {
    e.preventDefault()
    if (S.dragging && e.touches.length === 1) {
      const t0 = e.touches[0]!
      const dp = deps.proj(S.dragging.px, S.dragging.py, S.dragging.pz)
      const scale = dp.d / 700
      const dx = t0.clientX - S.prevMX
      const dy = t0.clientY - S.prevMY
      if (Math.abs(dx) + Math.abs(dy) > 2)
        S.dragMoved = true
      const ct = Math.cos(S.camT)
      const st = Math.sin(S.camT)
      const cp = Math.cos(S.camP)
      const sp = Math.sin(S.camP)
      S.dragging.px += dx * scale * ct - dy * scale * sp * st
      S.dragging.pz += dx * scale * st + dy * scale * sp * ct
      S.dragging.py -= dy * scale * cp
      S.prevMX = t0.clientX
      S.prevMY = t0.clientY
    }
    else if (e.touches.length === 1 && S.rotating) {
      S.camT = S.rst - (e.touches[0]!.clientX - S.rsx) * 0.005
      S.camP = S.rsp - (e.touches[0]!.clientY - S.rsy) * 0.005
    }
    else if (e.touches.length === 2) {
      const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
      const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
      const nd = Math.sqrt(dx * dx + dy * dy)
      S.camD *= td / nd
      S.camD = Math.max(80, Math.min(3000, S.camD))
      td = nd
    }
    else if (e.touches.length === 3 && tpan) {
      S.panX = S.panOX + (e.touches[0]!.clientX - S.rsx)
      S.panY = S.panOY + (e.touches[0]!.clientY - S.rsy)
    }
  }, { passive: false })

  cv.addEventListener('touchend', () => {
    if (S.dragging && !S.dragMoved)
      selectNode(S, S.dragging)
    S.rotating = false
    S.dragging = null
    tpan = false
  })
}
