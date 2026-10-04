<script setup lang="ts">
import type { SentinelEnvSample, SentinelNode, SentinelOccupation, SentinelScanBin } from '@/api/domains/sentinel'
/**
 * SentinelPanel —— 哨兵网格频谱面板（卷187 C）。
 *
 * 与 SpectrumPanel 并列使用，复用其 canvas 绘制模式（LUT 色阶 + 瀑布
 * 逐行滚动），但数据源不同：本面板消费 `/sentinel/*` 的**节点回传**数据，
 * 而 SpectrumPanel 消费本地 SDR 实时流。
 *
 * 数据源两模式：
 *   - live  : WebSocket `lumo.sentinel.scan` 实时推送（≤2s 刷新）
 *   - replay: REST `/sentinel/spectrum` 按时间窗回放（可拖时间轴）
 *
 * 组成：节点选择 + 状态灯 / 瀑布图（时间×频率，色阶=RSSI）/
 *      占用事件框选 / 环境副栏迷你趋势线。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import coreApi from '@/api/core'

const { getSentinelNodes, getSentinelSpectrum, getSentinelEnv, getSentinelOccupations }
  = coreApi

// ── 布局常量 ──
const AXIS_LEFT = 56
const AXIS_RIGHT = 44
const AXIS_TOP = 14
const AXIS_BOTTOM = 22
const WATERFALL_H = 200
const ENV_H = 56
const TOTAL_H = AXIS_TOP + WATERFALL_H + ENV_H + AXIS_BOTTOM

// ── 状态 ──
const nodes = ref<SentinelNode[]>([])
const selected = ref<string>('')
const mode = ref<'live' | 'replay'>('live')
const connected = ref(false)
const lastError = ref('')
const dbFloor = ref(-120)
const dbCeiling = ref(-40)
const windowMin = ref(15) // replay 时间窗（分钟）
const windowEnd = ref(Date.now() / 1000) // replay 右端
const occupied = ref<SentinelOccupation[]>([])
const envSeries = ref<SentinelEnvSample[]>([])
const sampleCount = ref(0)

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const hoverInfo = ref('')

// ── 色阶（与 SpectrumPanel 同款 LUT 思路）──
const COLORMAP_STOPS: Array<[number, [number, number, number]]> = [
  [0.0, [8, 12, 32]],
  [0.25, [24, 68, 128]],
  [0.5, [24, 152, 132]],
  [0.7, [188, 196, 60]],
  [0.85, [232, 120, 40]],
  [1.0, [240, 60, 60]],
]

const palette = buildPalette()

function buildPalette(): Uint8Array {
  const stops = COLORMAP_STOPS
  const lut = new Uint8Array(256 * 3)
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let r = 0; let g = 0; let b = 0
    for (let s = 0; s < stops.length; s++) {
      const [t0, c0] = stops[s]!
      const c1 = stops[s + 1]?.[1] ?? c0
      if (t >= t0) {
        const t1 = stops[s + 1]?.[0] ?? 1
        const f = t1 === t0 ? 0 : Math.min(1, (t - t0) / (t1 - t0))
        r = Math.round(c0[0] + (c1[0] - c0[0]) * f)
        g = Math.round(c0[1] + (c1[1] - c0[1]) * f)
        b = Math.round(c0[2] + (c1[2] - c0[2]) * f)
      }
    }
    lut[i * 3] = r; lut[i * 3 + 1] = g; lut[i * 3 + 2] = b
  }
  return lut
}

function colorFor(dbm: number): [number, number, number] {
  const t = (dbm - dbFloor.value) / Math.max(1, dbCeiling.value - dbFloor.value)
  const i = Math.max(0, Math.min(255, Math.round(t * 255)))
  return [palette[i * 3]!, palette[i * 3 + 1]!, palette[i * 3 + 2]!]
}

// ── 频点网格（所有节点的 freq_mhz 并集，升序）──
const freqGrid = ref<number[]>([])
const selectedNode = computed(() => nodes.value.find(n => n.node_id === selected.value) ?? null)
const selectedOnline = computed(() => selectedNode.value?.online ?? false)

// ── 瀑布位图缓冲（每行 = 一帧，列 = 频点）──
let wfRows: Uint8Array[] = []
const WF_MAX_ROWS = 240

function ensureGrid(rows: SentinelScanBin[]) {
  if (rows.length === 0)
    return
  const set = new Set<number>()
  for (const r of rows)
    set.add(Math.round(r.freq_mhz * 100) / 100)
  const grid = Array.from(set).sort((a, b) => a - b)
  if (grid.length !== freqGrid.value.length)
    freqGrid.value = grid
}

function pushRow(samples: SentinelScanBin[]) {
  if (freqGrid.value.length === 0)
    ensureGrid(samples)
  const w = freqGrid.value.length
  if (w === 0)
    return
  const row = new Uint8Array(w * 3).fill(0)
  const index = new Map<number, number>()
  freqGrid.value.forEach((f, i) => index.set(f, i))
  for (const s of samples) {
    const i = index.get(Math.round(s.freq_mhz * 100) / 100)
    if (i === undefined)
      continue
    const [r, g, b] = colorFor(s.rssi_dbm)
    row[i * 3] = r; row[i * 3 + 1] = g; row[i * 3 + 2] = b
  }
  wfRows.unshift(row)
  if (wfRows.length > WF_MAX_ROWS)
    wfRows.length = WF_MAX_ROWS
  sampleCount.value++
}

function resetRows() {
  wfRows = []
  freqGrid.value = []
  sampleCount.value = 0
}

// ── 绘制 ──
function draw() {
  const cv = canvasRef.value
  if (!cv)
    return
  const ctx = cv.getContext('2d')
  if (!ctx)
    return
  const W = cv.width
  const H = cv.height
  ctx.clearRect(0, 0, W, H)

  const plotW = Math.max(1, W - AXIS_LEFT - AXIS_RIGHT)
  const wfX = AXIS_LEFT
  const wfY = AXIS_TOP
  const wfH = WATERFALL_H

  // 瀑布：逐行铺像素
  const grid = freqGrid.value
  if (grid.length > 0 && wfRows.length > 0) {
    const cellW = plotW / grid.length
    const rowH = Math.max(1, wfH / Math.max(1, wfRows.length))
    for (let r = 0; r < wfRows.length; r++) {
      const row = wfRows[r]!
      const y = wfY + r * rowH
      for (let c = 0; c < grid.length; c++) {
        const cr = row[c * 3]!
        const cg = row[c * 3 + 1]!
        const cb = row[c * 3 + 2]!
        if (cr === 0 && cg === 0 && cb === 0)
          continue
        ctx.fillStyle = `rgb(${cr},${cg},${cb})`
        ctx.fillRect(wfX + c * cellW, y, Math.ceil(cellW), Math.ceil(rowH))
      }
    }
  }
  else {
    ctx.fillStyle = '#0b1020'
    ctx.fillRect(wfX, wfY, plotW, wfH)
    ctx.fillStyle = 'rgba(200,210,230,0.55)'
    ctx.font = '12px sans-serif'
    ctx.fillText(mode.value === 'live' ? '等待节点数据…' : '该时间窗无数据', wfX + 12, wfY + 22)
  }

  // 频率轴
  ctx.strokeStyle = 'rgba(160,175,200,0.35)'
  ctx.strokeRect(wfX, wfY, plotW, wfH)
  ctx.fillStyle = 'rgba(200,210,230,0.8)'
  ctx.font = '11px monospace'
  if (grid.length > 1) {
    const nTicks = Math.min(6, grid.length)
    for (let i = 0; i < nTicks; i++) {
      const idx = Math.round((i / (nTicks - 1)) * (grid.length - 1))
      const f = grid[idx]!
      const x = wfX + (idx / (grid.length - 1)) * plotW
      ctx.fillText(`${f.toFixed(1)}`, x - 14, wfY + wfH + 14)
    }
    ctx.fillText('MHz', wfX + plotW - 22, wfY + wfH + 14)
  }

  // 占用事件：按频点在瀑布上画竖框 + 时长标注
  const occ = occupied.value.filter(o => !selected.value || o.node_id === selected.value)
  for (const o of occ) {
    const idx = grid.findIndex(f => Math.abs(f - o.freq_mhz) <= 0.15)
    if (idx < 0)
      continue
    const x = wfX + (idx / Math.max(1, grid.length - 1)) * plotW
    ctx.strokeStyle = 'rgba(255,96,96,0.85)'
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 3])
    ctx.strokeRect(x - 5, wfY + 2, 10, wfH - 4)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(255,120,120,0.95)'
    ctx.font = '10px monospace'
    ctx.fillText(`${o.duration_s.toFixed(0)}s`, x - 10, wfY - 3)
  }

  // 环境副栏：三条迷你趋势线
  drawEnvStrip(ctx, wfX, wfY + wfH + 18, plotW)

  // 左侧 RSSI 色标
  for (let y = 0; y < wfH; y += 2) {
    const dbm = dbCeiling.value - (y / wfH) * (dbCeiling.value - dbFloor.value)
    const [r, g, b] = colorFor(dbm)
    ctx.fillStyle = `rgb(${r},${g},${b})`
    ctx.fillRect(8, wfY + y, 8, 2)
  }
  ctx.fillStyle = 'rgba(200,210,230,0.8)'
  ctx.font = '10px monospace'
  ctx.fillText(`${dbCeiling.value}`, 18, wfY + 10)
  ctx.fillText(`${dbFloor.value}`, 18, wfY + wfH)
  ctx.save()
  ctx.translate(14, wfY + wfH / 2)
  ctx.rotate(-Math.PI / 2)
  ctx.fillText('dBm', -12, 0)
  ctx.restore()
}

function drawEnvStrip(ctx: CanvasRenderingContext2D, x: number, y: number, w: number) {
  const series = envSeries.value
  ctx.fillStyle = '#0b1020'
  ctx.fillRect(x, y, w, ENV_H - 10)
  ctx.strokeStyle = 'rgba(160,175,200,0.3)'
  ctx.strokeRect(x, y, w, ENV_H - 10)
  if (series.length < 2) {
    ctx.fillStyle = 'rgba(200,210,230,0.5)'
    ctx.font = '11px sans-serif'
    ctx.fillText('环境数据不足', x + 8, y + 22)
    return
  }
  const t0 = series[0]!.ts
  const t1 = series.at(-1)!.ts
  const span = Math.max(1, t1 - t0)
  const px = (ts: number) => x + ((ts - t0) / span) * w

  const drawLine = (get: (s: SentinelEnvSample) => number | null, color: string, lo: number, hi: number) => {
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.beginPath()
    let started = false
    for (const s of series) {
      const v = get(s)
      if (v === null || v === undefined)
        continue
      const yy = y + (ENV_H - 14) - ((v - lo) / Math.max(1e-6, hi - lo)) * (ENV_H - 18)
      if (!started) { ctx.moveTo(px(s.ts), yy); started = true }
      else { ctx.lineTo(px(s.ts), yy) }
    }
    ctx.stroke()
  }
  drawLine(s => s.temp_c, '#ffb35c', 0, 50) // 温度
  drawLine(s => s.hum_pct, '#5cc8ff', 0, 100) // 湿度
  drawLine(s => s.bat_mv, '#7dff9b', 3000, 4200) // 电池
  const last = series.at(-1)!
  ctx.fillStyle = 'rgba(200,210,230,0.85)'
  ctx.font = '10px monospace'
  ctx.fillText(
    `T ${last.temp_c?.toFixed(1) ?? '--'}°C  H ${last.hum_pct?.toFixed(0) ?? '--'}%  `
    + `P ${last.pres_hpa?.toFixed(1) ?? '--'}hPa  Bat ${last.bat_mv ?? '--'}mV`,
    x + 6,
    y + ENV_H - 14,
  )
}

// ── 数据加载 ──
async function loadNodes() {
  try {
    const r = await getSentinelNodes()
    nodes.value = r.nodes
    if (!selected.value && r.nodes.length > 0)
      selected.value = r.nodes[0]!.node_id
    connected.value = true
    lastError.value = ''
  }
  catch (e: any) {
    connected.value = false
    lastError.value = String(e?.message ?? e)
  }
}

async function loadReplay() {
  if (mode.value !== 'replay')
    return
  const to = windowEnd.value
  const from = to - windowMin.value * 60
  try {
    const r = await getSentinelSpectrum({
      from,
      to,
      node: selected.value || undefined,
      limit: 5000,
    })
    resetRows()
    ensureGrid(r.rows)
    // 按时间分组逐帧推入（新→旧展示）
    const byTs = new Map<number, SentinelScanBin[]>()
    for (const row of r.rows) {
      const k = Math.round(row.ts * 10) / 10
      if (!byTs.has(k))
        byTs.set(k, [])
      byTs.get(k)!.push(row)
    }
    const keys = Array.from(byTs.keys()).sort((a, b) => a - b)
    for (const k of keys)
      pushRow(byTs.get(k)!)
    const env = await getSentinelEnv({ node: selected.value || undefined, hours: windowMin.value / 60 })
    envSeries.value = env.rows.slice(-120)
    const occ = await getSentinelOccupations({ node: selected.value || undefined, hours: windowMin.value / 60 })
    occupied.value = occ.rows
  }
  catch (e: any) {
    lastError.value = String(e?.message ?? e)
  }
}

async function loadLive() {
  // live 模式拉取最近 60s 作为瀑布初始底图 + 环境/占用
  const to = Date.now() / 1000
  try {
    const r = await getSentinelSpectrum({ from: to - 60, to, node: selected.value || undefined, limit: 2000 })
    resetRows()
    ensureGrid(r.rows)
    const byTs = new Map<number, SentinelScanBin[]>()
    for (const row of r.rows) {
      const k = Math.round(row.ts * 10) / 10
      if (!byTs.has(k))
        byTs.set(k, [])
      byTs.get(k)!.push(row)
    }
    for (const k of Array.from(byTs.keys()).sort((a, b) => a - b))
      pushRow(byTs.get(k)!)
    const env = await getSentinelEnv({ node: selected.value || undefined, hours: 1 })
    envSeries.value = env.rows.slice(-120)
    const occ = await getSentinelOccupations({ node: selected.value || undefined, hours: 1 })
    occupied.value = occ.rows
  }
  catch (e: any) {
    lastError.value = String(e?.message ?? e)
  }
}

// ── 轮询（live ≤2s 刷新，满足验收项 4）──
let pollTimer: ReturnType<typeof setInterval> | null = null
let envTick = 0

function startPoll() {
  stopPoll()
  pollTimer = setInterval(async () => {
    if (mode.value === 'live') {
      await loadLive()
      envTick++
      if (envTick % 10 === 0)
        await loadNodes()
    }
    else {
      await loadReplay()
    }
    draw()
  }, 1500)
}

function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// ── 交互 ──
function onHover(ev: MouseEvent) {
  const cv = canvasRef.value
  if (!cv || freqGrid.value.length === 0) { hoverInfo.value = ''; return }
  const rect = cv.getBoundingClientRect()
  const x = ev.clientX - rect.left
  const plotW = cv.width - AXIS_LEFT - AXIS_RIGHT
  const frac = (x - AXIS_LEFT) / Math.max(1, plotW)
  if (frac < 0 || frac > 1) { hoverInfo.value = ''; return }
  const idx = Math.round(frac * (freqGrid.value.length - 1))
  const f = freqGrid.value[Math.max(0, Math.min(freqGrid.value.length - 1, idx))]!
  hoverInfo.value = `${f.toFixed(2)} MHz`
}

function resize() {
  const cv = canvasRef.value
  const box = containerRef.value
  if (!cv || !box)
    return
  const dpr = window.devicePixelRatio || 1
  cv.width = box.clientWidth
  cv.height = TOTAL_H
  cv.style.width = `${box.clientWidth}px`
  cv.style.height = `${TOTAL_H}px`
  cv.getContext('2d')?.scale(1, 1)
  void dpr
  draw()
}

function onResize() { resize() }

onMounted(async () => {
  await loadNodes()
  await loadLive()
  resize()
  startPoll()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  stopPoll()
  window.removeEventListener('resize', onResize)
})

watch(selected, async () => {
  if (mode.value === 'live')
    await loadLive()
  else await loadReplay()
  draw()
})

watch(mode, async (m) => {
  if (m === 'replay')
    await loadReplay()
  else await loadLive()
  draw()
})
</script>

<template>
  <div ref="containerRef" class="sentinel-panel">
    <div class="sp-bar">
      <span class="sp-title">哨兵网格</span>

      <select v-model="selected" class="sp-select">
        <option v-for="n in nodes" :key="n.node_id" :value="n.node_id">
          {{ n.node_id }}（{{ n.frames }} 帧）
        </option>
      </select>

      <span class="sp-lamp" :class="{ on: selectedOnline }" />
      <span class="sp-lamp-text">{{ selectedOnline ? '在线' : '离线' }}</span>

      <div class="sp-modes">
        <button :class="{ active: mode === 'live' }" @click="mode = 'live'">实时</button>
        <button :class="{ active: mode === 'replay' }" @click="mode = 'replay'">回放</button>
      </div>

      <template v-if="mode === 'replay'">
        <label class="sp-window">
          窗口
          <input v-model.number="windowMin" type="number" min="1" max="720" step="1" style="width:56px"> 分钟
        </label>
      </template>

      <span class="sp-legend">
        <i style="background:#ffb35c" /> 温度
        <i style="background:#5cc8ff" /> 湿度
        <i style="background:#7dff9b" /> 电池
      </span>
      <span class="sp-stat">{{ sampleCount }} 帧 · {{ freqGrid.length }} 频点</span>
      <span v-if="hoverInfo" class="sp-hover">{{ hoverInfo }}</span>
      <span v-if="!connected" class="sp-err">未连接</span>
      <span v-else-if="lastError" class="sp-err">{{ lastError }}</span>
    </div>

    <canvas
      ref="canvasRef"
      class="sp-canvas"
      @mousemove="onHover"
      @mouseleave="hoverInfo = ''"
    />

    <div v-if="occupied.length" class="sp-occ">
      占用事件：<span v-for="(o, i) in occupied.slice(0, 6)" :key="i" class="sp-occ-item">
        {{ o.node_id }}@{{ o.freq_mhz.toFixed(2) }}MHz {{ o.duration_s.toFixed(0) }}s
        <b>{{ o.peak_dbm.toFixed(0) }}dBm</b>
      </span>
    </div>
  </div>
</template>

<style scoped>
.sentinel-panel {
  background: #0b1020;
  border: 1px solid rgba(120, 140, 180, 0.25);
  border-radius: 8px;
  padding: 8px;
  color: #cbd5e8;
  font-family: ui-sans-serif, system-ui, sans-serif;
}
.sp-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 2px 4px 8px;
  font-size: 12px;
}
.sp-title { font-weight: 600; letter-spacing: 0.5px; }
.sp-select {
  background: #111a30; color: #cbd5e8; border: 1px solid rgba(120,140,180,0.35);
  border-radius: 4px; padding: 2px 6px; font-size: 12px;
}
.sp-lamp {
  width: 9px; height: 9px; border-radius: 50%;
  background: #4b5563; display: inline-block;
}
.sp-lamp.on { background: #34d399; box-shadow: 0 0 6px #34d39999; }
.sp-lamp-text { font-size: 11px; opacity: 0.85; }
.sp-modes button {
  background: #111a30; color: #cbd5e8; border: 1px solid rgba(120,140,180,0.35);
  border-radius: 4px; padding: 2px 8px; font-size: 12px; cursor: pointer;
}
.sp-modes button.active { background: #1d3557; border-color: #4d7ea8; color: #fff; }
.sp-window { font-size: 11px; opacity: 0.9; }
.sp-window input {
  background: #111a30; color: #cbd5e8; border: 1px solid rgba(120,140,180,0.35);
  border-radius: 4px; padding: 1px 4px;
}
.sp-legend i {
  display: inline-block; width: 8px; height: 8px; border-radius: 2px;
  margin: 0 3px 0 6px; vertical-align: middle;
}
.sp-stat { margin-left: auto; font-family: monospace; opacity: 0.75; }
.sp-hover { font-family: monospace; color: #ffd479; }
.sp-err { color: #ff9b9b; font-family: monospace; }
.sp-canvas { display: block; width: 100%; border-radius: 4px; cursor: crosshair; }
.sp-occ {
  margin-top: 6px; font-size: 11px; color: #ff9b9b; font-family: monospace;
  display: flex; gap: 10px; flex-wrap: wrap;
}
.sp-occ-item b { color: #ffd479; }
</style>
