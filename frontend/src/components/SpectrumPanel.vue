<script setup lang="ts">
/**
 * SDR 实时频谱 · 瀑布图（Y-04 v3）
 *
 * 渲染核心移植自 gbozo/no-sdr（MIT）：spectrumTraceRenderer / waterfallRenderer，
 * 许可与来源见各文件头及 NOTICE。坐标轴刻度为本项目 spectrumAxis.ts 自适应阶梯。
 *
 * 相对 v2 的修复与新增：
 *  - 纵轴刻度自适应量程且不再溢出到瀑布区（旧实现固定 10dB 步进导致重叠）；
 *  - 横轴阶梯覆盖 Hz→MHz，kHz 级窄跨度不再整条空白；
 *  - 瀑布图持有帧历史缓冲，缩放/resize 后整幅重绘，不再出现透明空白；
 *  - 缩放视口改为频带分数 [0,1]，单边谱（声卡 rfft）不再把 VFO 错当中心；
 *  - 新增：滚轮缩放 / 拖拽框选放大 / Shift 拖拽平移 / 双击复位 / PNG 导出；
 *  - 新增：显示平滑(EMA)、峰值保持(带衰减)、逐 bin 滚动最小值噪声底线、信号柱状填充、gamma。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useSpectrumStream } from '@/composables/useSpectrumStream'
import { dbTicks, formatFreqTick, formatRbw, formatSpan, freqTicks } from '@/utils/spectrumAxis'
import { SpectrumTraceRenderer, xToBinF } from '@/utils/spectrumTraceRenderer'
import { WaterfallRenderer } from '@/utils/waterfallRenderer'

const props = defineProps<{ freqMhz?: number, mode?: string }>()

const emit = defineEmits<{ (e: 'tune', freqMhz: number): void, (e: 'mark', freqMhz: number): void }>()

const { latest, connected, degraded, connect, disconnect } = useSpectrumStream()

const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)

// 帧重绘脏标记（声明前置：下方 watch/事件回调在源码序上早于其余渲染状态）
let dirty = true

// 右键菜单状态（声明前置：onMouseDown 内引用）
const ctxMenu = ref<{ x: number, y: number, mhz: number } | null>(null)

// ── 布局常量（左纵轴 / 右时间轴 / 顶部留白 / 底横轴） ──
const AXIS_LEFT = 56
const AXIS_RIGHT = 44
const AXIS_TOP = 14
const AXIS_BOTTOM = 22
const SPECTRUM_H = 160
const WATERFALL_H_OPTIONS = [120, 200, 320] as const
const waterfallH = ref<number>(200)
const TOTAL_H = computed(() => AXIS_TOP + SPECTRUM_H + waterfallH.value + AXIS_BOTTOM)

// ── 显示状态 ──
const colormapName = ref<'classic' | 'blackgold' | 'military'>('classic')
const gamma = ref(1)
const wfInvert = ref(false)
const dbFloor = ref(-120)
const dbCeiling = ref(0)
const autoFloor = ref(false)
const smoothing = ref(0)
const showPeakHold = ref(false)
const showNoiseFloor = ref(false)
const signalFill = ref(false)
const freeze = ref(false)
const zoomLabel = ref('')
const cursorInfo = ref('')
const freqInput = ref('')

// ── 解调带宽叠加（OpenWebRX 频道叠加 / no-sdr 调谐指示语义） ──
// 各模式典型带宽仅作显示默认，可手动改；非电台真实滤波器设置
const MODE_BANDWIDTH_HZ: Record<string, number> = {
  'CW': 500,
  'CW-R': 500,
  'RTTY': 500,
  'RTTY-R': 500,
  'LSB': 2700,
  'USB': 2700,
  'AM': 9000,
  'FM': 12_500,
  'WFM': 200_000,
}
const showBandwidth = ref(true)
const bandwidthHz = ref(2700)
watch(() => props.mode, (m) => {
  if (m && MODE_BANDWIDTH_HZ[m] !== undefined)
    bandwidthHz.value = MODE_BANDWIDTH_HZ[m]
}, { immediate: true })
watch([showBandwidth, bandwidthHz], () => { dirty = true })

// ── 色图预设（stop 与 v2 一致） ──
const COLORMAP_STOPS: Record<string, Array<[number, [number, number, number]]>> = {
  classic: [
    [0.0, [8, 8, 32]],
    [0.35, [0, 90, 180]],
    [0.6, [0, 200, 120]],
    [0.8, [230, 230, 40]],
    [1.0, [255, 60, 40]],
  ],
  blackgold: [
    [0.0, [0, 0, 0]],
    [0.4, [40, 30, 10]],
    [0.7, [180, 120, 30]],
    [0.9, [240, 200, 80]],
    [1.0, [255, 255, 200]],
  ],
  military: [
    [0.0, [0, 12, 0]],
    [0.4, [0, 70, 20]],
    [0.7, [60, 140, 40]],
    [0.9, [150, 200, 80]],
    [1.0, [230, 255, 140]],
  ],
}

function buildPalette(): Uint8Array {
  const stops = COLORMAP_STOPS[colormapName.value] ?? COLORMAP_STOPS.classic!
  const lut = new Uint8Array(256 * 3)
  for (let i = 0; i < 256; i++) {
    const t = i / 255
    let r = 0
    let g = 0
    let b = 0
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
    lut[i * 3] = r
    lut[i * 3 + 1] = g
    lut[i * 3 + 2] = b
  }
  return lut
}

// ── 渲染器（移植自 no-sdr，MIT） ──
let palette = buildPalette()
const traceRenderer = new SpectrumTraceRenderer()
const waterfallRenderer = new WaterfallRenderer(palette, dbFloor.value, dbCeiling.value)

// ── 频带与缩放视口（分数 [0,1]，对单边谱同样成立） ──
let extentF0 = 0
let extentF1 = 0
let zoomStart = 0
let zoomEnd = 1

// ── 帧历史（瀑布图的数据源，缩放/resize 后据此整幅重绘） ──
const wfFrames: Float32Array[] = []
const frameTimes: number[] = []

let rafId: number | null = null
let plotW = 0
let dpr = 1
let lastPixelDb: Float32Array | null = null
let hoverX = -1

// 交互：拖拽框选放大 / Shift 拖拽平移 / 双击复位
const selection = ref<{ x0: number, x1: number } | null>(null)
let dragStartX = -1
let panning = false
let panStartX = 0
let panStartZoom: [number, number] = [0, 1]

function spectrumRect() {
  return {
    x: AXIS_LEFT,
    y: AXIS_TOP,
    w: plotW,
    h: SPECTRUM_H,
    wfY: AXIS_TOP + SPECTRUM_H,
    wfH: waterfallH.value,
  }
}

function extent(frame: NonNullable<typeof latest.value>): [number, number] {
  const f = frame.freq_hz
  if (f.length < 2)
    return [0, 1]
  return [f[0]!, f.at(-1)!]
}

function fracToHz(frac: number): number {
  return extentF0 + Math.max(0, Math.min(1, frac)) * (extentF1 - extentF0)
}

function hzToFrac(hz: number): number {
  if (extentF1 <= extentF0)
    return 0
  return Math.max(0, Math.min(1, (hz - extentF0) / (extentF1 - extentF0)))
}

function setZoom(a: number, b: number): void {
  const lo = Math.max(0, Math.min(a, b))
  const hi = Math.min(1, Math.max(a, b))
  if (hi - lo < 0.005)
    return
  zoomStart = lo
  zoomEnd = hi
  traceRenderer.setView(zoomStart, zoomEnd)
  waterfallRenderer.setView(zoomStart, zoomEnd)
  dirty = true
}

function resetZoom(): void {
  setZoom(0, 1)
}

// ── 布局 / 高分屏 ──
function resize(): void {
  const canvas = canvasRef.value
  const container = containerRef.value
  if (!canvas || !container)
    return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  const cssW = Math.max(container.clientWidth, 320)
  canvas.style.width = `${cssW}px`
  canvas.style.height = `${TOTAL_H.value}px`
  const bw = Math.round(cssW * dpr)
  const bh = Math.round(TOTAL_H.value * dpr)
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw
    canvas.height = bh
  }
  plotW = bw / dpr - AXIS_LEFT - AXIS_RIGHT
  dirty = true
}

function syncRenderers(): void {
  palette = buildPalette()
  traceRenderer.setRange(dbFloor.value, dbCeiling.value)
  traceRenderer.setAccentColor('#4f8cff')
  traceRenderer.setView(zoomStart, zoomEnd)
  waterfallRenderer.setPalette(palette)
  waterfallRenderer.setRange(dbFloor.value, dbCeiling.value)
  waterfallRenderer.setGamma(gamma.value)
  waterfallRenderer.setInvert(wfInvert.value)
  waterfallRenderer.setView(zoomStart, zoomEnd)
}

// ── 主绘制 ──
function draw(): void {
  const canvas = canvasRef.value
  if (!canvas || plotW <= 0)
    return
  const ctx = canvas.getContext('2d')
  if (!ctx)
    return
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr)

  const rect = spectrumRect()
  const frame = latest.value

  // 频谱区底色（瀑布区由渲染器自持离屏表面，本帧只需 blit，不可在此 clear）
  ctx.fillStyle = '#0b0b16'
  ctx.fillRect(rect.x, rect.y, rect.w, rect.h)

  if (!frame) {
    drawEmptyHint(ctx, rect)
    drawAxisFrame(ctx, rect, null)
    return
  }

  // 网格 + 纵轴刻度（自适应量程，不再重叠）
  ctx.font = '10px ui-monospace, monospace'
  ctx.lineWidth = 1
  const ticks = dbTicks(dbFloor.value, dbCeiling.value, rect.h, 18)
  for (const t of ticks) {
    const y = rect.y + (1 - t.ratio) * rect.h
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.beginPath()
    ctx.moveTo(rect.x, Math.round(y) + 0.5)
    ctx.lineTo(rect.x + rect.w, Math.round(y) + 0.5)
    ctx.stroke()
    ctx.fillStyle = 'rgba(255,255,255,0.55)'
    ctx.textAlign = 'right'
    ctx.fillText(`${t.db}`, rect.x - 6, Math.round(y) + 3)
  }
  ctx.fillStyle = 'rgba(255,255,255,0.4)'
  ctx.textAlign = 'left'
  ctx.fillText('dB', 6, rect.y + 8)

  // 轨迹（移植渲染器）：返回像素级 dB 供读数/峰值标注复用
  const dbArr = Float32Array.from(frame.spectrum_db)
  lastPixelDb = traceRenderer.draw(ctx, rect.x, rect.y, rect.w, rect.h, dbArr)

  // 峰值标注（限制在频谱区内，不再溢出）
  if (lastPixelDb) {
    let px = 0
    let pv = -Infinity
    for (let x = 0; x < lastPixelDb.length; x++) {
      if (lastPixelDb[x]! > pv) {
        pv = lastPixelDb[x]!
        px = x
      }
    }
    const py = rect.y + (1 - Math.max(0, Math.min(1, (pv - dbFloor.value) / Math.max(1e-6, dbCeiling.value - dbFloor.value)))) * rect.h
    ctx.fillStyle = '#ffd166'
    ctx.beginPath()
    ctx.moveTo(rect.x + px, py - 8)
    ctx.lineTo(rect.x + px - 4, py)
    ctx.lineTo(rect.x + px + 4, py)
    ctx.closePath()
    ctx.fill()
    const binF = xToBinF(px, rect.w, dbArr.length, zoomStart, zoomEnd)
    const f = frame.freq_hz[Math.max(0, Math.min(frame.freq_hz.length - 1, Math.round(binF)))]! / 1e6
    const label = `${f.toFixed(4)} MHz · ${pv.toFixed(0)} dB`
    ctx.font = '10px ui-monospace, monospace'
    ctx.textAlign = px > rect.w - 150 ? 'right' : 'left'
    const tx = rect.x + px + (px > rect.w - 150 ? -7 : 7)
    ctx.fillStyle = 'rgba(255,209,102,0.9)'
    ctx.fillText(label, tx, Math.max(rect.y + 10, py - 6))
  }

  // 瀑布图（渲染器自持离屏表面：每帧追行，面板只 blit，避免被轨迹层的 clear 抹掉）
  if (!freeze.value && wfFrames.length > 0)
    waterfallRenderer.drawRow(rect.w, rect.wfH, wfFrames.at(-1)!)
  waterfallRenderer.blit(ctx, rect.x, rect.wfY)

  // 解调带宽矩形（在 VFO 竖线之下，先画）
  drawBandwidth(ctx, rect)

  // VFO 调谐线（按频带分数映射，单边谱不再错位）
  drawVfo(ctx, rect, frame)

  // 框选放大预览
  if (selection.value) {
    const x0 = Math.min(selection.value.x0, selection.value.x1)
    const x1 = Math.max(selection.value.x0, selection.value.x1)
    ctx.fillStyle = 'rgba(79,140,255,0.18)'
    ctx.fillRect(rect.x + x0, rect.y, x1 - x0, rect.h + rect.wfH)
    ctx.strokeStyle = 'rgba(79,140,255,0.8)'
    ctx.lineWidth = 1
    ctx.strokeRect(rect.x + x0 + 0.5, rect.y + 0.5, x1 - x0, rect.h + rect.wfH - 1)
  }

  drawAxisFrame(ctx, rect, frame)
  drawTimeAxis(ctx, rect)
}

function drawEmptyHint(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof spectrumRect>): void {
  ctx.fillStyle = 'rgba(255,255,255,0.4)'
  ctx.font = '12px ui-sans-serif, system-ui'
  ctx.textAlign = 'center'
  ctx.fillText(connected.value ? '等待频谱数据…' : '频谱服务未连接，重连中…', rect.x + rect.w / 2, rect.y + rect.h / 2)
}

/** 解调带宽矩形：中心半透明带 + 两侧边缘线，跨频谱与瀑布，裁剪在绘图区内。 */
function drawBandwidth(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof spectrumRect>): void {
  if (!showBandwidth.value || props.freqMhz === undefined || extentF1 <= extentF0)
    return
  const viewFrac = (hzToFrac(props.freqMhz * 1e6) - zoomStart) / (zoomEnd - zoomStart)
  const cx = rect.x + viewFrac * rect.w
  const halfPx = (bandwidthHz.value / 2) / (extentF1 - extentF0) / (zoomEnd - zoomStart) * rect.w
  const totalH = rect.h + rect.wfH
  if (cx + halfPx < rect.x || cx - halfPx > rect.x + rect.w)
    return
  ctx.save()
  ctx.beginPath()
  ctx.rect(rect.x, rect.y, rect.w, totalH)
  ctx.clip()
  ctx.fillStyle = 'rgba(79,140,255,0.15)'
  ctx.fillRect(cx - halfPx, rect.y, halfPx * 2, totalH)
  ctx.strokeStyle = 'rgba(255,252,98,0.4)'
  ctx.lineWidth = 0.8
  ctx.beginPath()
  for (const ex of [cx - halfPx, cx + halfPx]) {
    ctx.moveTo(ex, rect.y)
    ctx.lineTo(ex, rect.y + totalH)
  }
  ctx.stroke()
  ctx.restore()
}

function drawVfo(
  ctx: CanvasRenderingContext2D,
  rect: ReturnType<typeof spectrumRect>,
  frame: NonNullable<typeof latest.value>,
): void {
  if (props.freqMhz === undefined)
    return
  const hz = props.freqMhz * 1e6
  const frac = hzToFrac(hz)
  const viewFrac = (frac - zoomStart) / (zoomEnd - zoomStart)
  const totalH = rect.h + rect.wfH
  ctx.setLineDash([3, 3])
  ctx.lineWidth = 1.2
  ctx.strokeStyle = '#ffd166'
  if (viewFrac >= 0 && viewFrac <= 1) {
    const x = rect.x + viewFrac * rect.w
    ctx.beginPath()
    ctx.moveTo(x, rect.y)
    ctx.lineTo(x, rect.y + totalH)
    ctx.stroke()
    ctx.setLineDash([])
    ctx.fillStyle = '#ffd166'
    ctx.font = '10px ui-monospace, monospace'
    // 标签放在频谱区底部，避开顶部的峰值标注
    ctx.textAlign = viewFrac > 0.85 ? 'right' : 'left'
    ctx.fillText(`VFO ${props.freqMhz.toFixed(4)}`, x + (viewFrac > 0.85 ? -5 : 5), rect.y + rect.h - 4)
  }
  else {
    // 视口外：在边缘画箭头提示方向
    const x = viewFrac < 0 ? rect.x + 6 : rect.x + rect.w - 6
    ctx.beginPath()
    ctx.moveTo(x, rect.y + totalH / 2 - 5)
    ctx.lineTo(viewFrac < 0 ? x - 5 : x + 5, rect.y + totalH / 2)
    ctx.lineTo(x, rect.y + totalH / 2 + 5)
    ctx.stroke()
  }
  ctx.setLineDash([])
  void frame
}

function drawAxisFrame(
  ctx: CanvasRenderingContext2D,
  rect: ReturnType<typeof spectrumRect>,
  frame: NonNullable<typeof latest.value> | null,
): void {
  // 分隔线
  ctx.strokeStyle = 'rgba(255,255,255,0.18)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(rect.x, rect.y + rect.h + 0.5)
  ctx.lineTo(rect.x + rect.w, rect.y + rect.h + 0.5)
  ctx.stroke()

  // 横轴刻度：可见频段自适应阶梯（kHz 级跨度也有刻度）
  if (!frame || frame.freq_hz.length < 2)
    return
  const [f0, f1] = extent(frame)
  const viewLo = fracToHz(zoomStart)
  const viewHi = fracToHz(zoomEnd)
  const ticks = freqTicks(viewLo, viewHi, rect.w, 64)
  if (ticks.length === 0)
    return
  const stepHz = ticks.length >= 2 ? (ticks[1]!.hz - ticks[0]!.hz) : (viewHi - viewLo)
  ctx.font = '10px ui-monospace, monospace'
  ctx.textAlign = 'center'
  for (const t of ticks) {
    const x = rect.x + t.ratio * rect.w
    ctx.strokeStyle = 'rgba(255,255,255,0.35)'
    ctx.beginPath()
    ctx.moveTo(x, rect.y + rect.h + rect.wfH)
    ctx.lineTo(x, rect.y + rect.h + rect.wfH + 4)
    ctx.stroke()
    ctx.fillStyle = 'rgba(255,255,255,0.7)'
    ctx.fillText(formatFreqTick(t.hz, stepHz), x, rect.y + rect.h + rect.wfH + 15)
  }
  ctx.fillStyle = 'rgba(255,255,255,0.45)'
  ctx.textAlign = 'right'
  ctx.fillText('MHz', rect.x + rect.w, rect.y + rect.h + rect.wfH + 15)
  void f0
  void f1
}

function drawTimeAxis(ctx: CanvasRenderingContext2D, rect: ReturnType<typeof spectrumRect>): void {
  const secPerRow = avgFrameIntervalSec()
  ctx.fillStyle = 'rgba(255,255,255,0.5)'
  ctx.font = '9px ui-monospace, monospace'
  ctx.textAlign = 'left'
  const rightX = rect.x + rect.w + 4
  // 瀑布 1 帧 = 1 像素行，标签每 22px 一个，避免叠成竖线
  const stepPx = 22
  for (let py = rect.wfH - 1; py >= 0; py -= stepPx) {
    const age = (rect.wfH - 1 - py) * secPerRow
    const y = rect.wfY + py
    ctx.fillText(age < 1 ? '现在' : `-${Math.round(age)}s`, rightX, y + 3)
  }
}

function avgFrameIntervalSec(): number {
  if (frameTimes.length < 2)
    return 0.3
  let sum = 0
  for (let i = 1; i < frameTimes.length; i++) sum += frameTimes[i]! - frameTimes[i - 1]!
  return Math.max(0.03, (sum / (frameTimes.length - 1)) / 1000)
}

function loop(): void {
  if (dirty)
    draw()
  rafId = requestAnimationFrame(loop)
}

// ── 数据接入 ──
watch(latest, (frame) => {
  if (!frame)
    return
  const now = performance.now()
  frameTimes.push(now)
  if (frameTimes.length > 20)
    frameTimes.shift()

  // 换频 → 复位缩放（频带变了，旧视口无意义）
  const [f0, f1] = extent(frame)
  if (extentF1 - extentF0 > 0 && (Math.abs(f0 - extentF0) > 1 || Math.abs(f1 - extentF1) > 1)) {
    extentF0 = f0
    extentF1 = f1
    resetZoom()
  }
  else {
    extentF0 = f0
    extentF1 = f1
  }

  const arr = Float32Array.from(frame.spectrum_db)
  wfFrames.push(arr)
  const maxRows = Math.max(WATERFALL_H_OPTIONS[0]!, waterfallH.value + 40)
  while (wfFrames.length > maxRows)
    wfFrames.shift()

  if (autoFloor.value) {
    const sorted = [...frame.spectrum_db].filter(Number.isFinite).sort((a, b) => a - b)
    if (sorted.length > 0) {
      const p20 = sorted[Math.floor(sorted.length * 0.2)] ?? -120
      dbFloor.value = Math.max(-140, Math.min(-20, Math.round(p20 - 5)))
    }
  }

  waterfallRenderer.setPalette(palette)
  dirty = true
})

watch([dbFloor, dbCeiling], () => {
  traceRenderer.setRange(dbFloor.value, dbCeiling.value)
  waterfallRenderer.setRange(dbFloor.value, dbCeiling.value)
  dirty = true
})

watch([colormapName, gamma, wfInvert, waterfallH], () => {
  syncRenderers()
  // 配色/量程变化 → 从帧历史整幅重绘瀑布（不再出现空白或残留旧配色）
  redrawWaterfallAll()
  dirty = true
})

watch([smoothing], () => {
  traceRenderer.setSmoothing(smoothing.value)
  dirty = true
})

watch(showPeakHold, (v) => {
  traceRenderer.setPeakHold(v)
  dirty = true
})

watch(showNoiseFloor, (v) => {
  traceRenderer.setNoiseFloor(v)
  dirty = true
})

watch(signalFill, (v) => {
  traceRenderer.setSignalFill(v)
  dirty = true
})

function redrawWaterfallAll(): void {
  waterfallRenderer.renderAll(plotW, waterfallH.value, wfFrames)
  dirty = true
}

// ── 交互 ──
function cssX(e: MouseEvent): number {
  const canvas = canvasRef.value
  if (!canvas)
    return 0
  return e.clientX - canvas.getBoundingClientRect().left - AXIS_LEFT
}

function inPlot(x: number): boolean {
  return x >= 0 && x <= plotW
}

function onMouseDown(e: MouseEvent): void {
  ctxMenu.value = null
  const x = cssX(e)
  if (!inPlot(x))
    return
  if (e.shiftKey) {
    panning = true
    panStartX = x
    panStartZoom = [zoomStart, zoomEnd]
  }
  else {
    dragStartX = x
    selection.value = { x0: x, x1: x }
  }
}

function onMouseMove(e: MouseEvent): void {
  const x = cssX(e)
  if (!inPlot(x)) {
    cursorInfo.value = ''
    return
  }
  hoverX = x
  updateCursorReadout()

  if (panning) {
    const dx = x - panStartX
    const span = zoomEnd - zoomStart
    const shift = -(dx / plotW) * span
    let ns = panStartZoom[0] + shift
    let ne = panStartZoom[1] + shift
    if (ns < 0) {
      ne -= ns
      ns = 0
    }
    if (ne > 1) {
      ns -= ne - 1
      ne = 1
    }
    setZoom(ns, ne)
    return
  }
  if (dragStartX >= 0 && selection.value) {
    selection.value = { x0: dragStartX, x1: x }
    dirty = true
  }
}

function onMouseUp(e: MouseEvent): void {
  const x = cssX(e)
  if (panning) {
    panning = false
    return
  }
  if (dragStartX < 0 || !selection.value)
    return
  const x0 = dragStartX
  dragStartX = -1
  selection.value = null
  if (Math.abs(x - x0) > 8) {
    // 拖拽框选 → 放大到该频段（GQRX/SDR# 语义）
    const a = hzToClipFrac(fracOfPixel(x0))
    const b = hzToClipFrac(fracOfPixel(x))
    setZoom(a, b)
  }
  else if (inPlot(x)) {
    // 单击 → 调谐
    const hz = fracToHz(fracOfPixel(x))
    emit('tune', +(hz / 1e6).toFixed(6))
  }
  dirty = true
}

function fracOfPixel(x: number): number {
  return Math.max(0, Math.min(1, x / plotW))
}

/** 像素分数 → 频带分数（把视口内分数映射回全带分数） */
function hzToClipFrac(viewFrac: number): number {
  return zoomStart + viewFrac * (zoomEnd - zoomStart)
}

function onWheel(e: WheelEvent): void {
  const x = cssX(e)
  if (!inPlot(x))
    return
  e.preventDefault()
  const anchor = hzToClipFrac(fracOfPixel(x))
  const factor = e.deltaY > 0 ? 1.25 : 0.8
  const span = Math.max(0.005, Math.min(1, (zoomEnd - zoomStart) * factor))
  const a = anchor - (anchor - zoomStart) * (span / (zoomEnd - zoomStart))
  setZoom(a, a + span)
}

function onDblClick(): void {
  resetZoom()
}

// ── 右键菜单：标记干扰源 / 标记信号 → RadioView 写 GRAG 五元组（卷146 语义，v3 移植） ──
function onContextMenu(e: MouseEvent): void {
  const x = cssX(e)
  if (!inPlot(x))
    return
  e.preventDefault()
  const hz = fracToHz(fracOfPixel(x))
  ctxMenu.value = {
    x: e.clientX,
    y: e.clientY,
    mhz: +(hz / 1e6).toFixed(6),
  }
}

function markFromMenu(): void {
  if (!ctxMenu.value)
    return
  emit('mark', ctxMenu.value.mhz)
  ctxMenu.value = null
}

function onMouseLeave(): void {
  cursorInfo.value = ''
  hoverX = -1
  if (selection.value) {
    selection.value = null
    dragStartX = -1
    dirty = true
  }
}

function updateCursorReadout(): void {
  const frame = latest.value
  if (!frame || frame.freq_hz.length < 2 || hoverX < 0 || plotW <= 0) {
    cursorInfo.value = ''
    return
  }
  const bins = frame.spectrum_db.length
  const binF = xToBinF(hoverX, plotW, bins, zoomStart, zoomEnd)
  const idx = Math.max(0, Math.min(bins - 1, Math.round(binF)))
  const f = fracToHz(fracOfPixel(hoverX)) / 1e6
  const db = frame.spectrum_db[idx] ?? dbFloor.value
  cursorInfo.value = `${f.toFixed(4)} MHz · ${db.toFixed(1)} dB`
}

function tuneFromInput(): void {
  const mhz = Number.parseFloat(freqInput.value)
  if (Number.isFinite(mhz) && mhz > 0)
    emit('tune', mhz)
  freqInput.value = ''
}

function exportPng(): void {
  const canvas = canvasRef.value
  if (!canvas)
    return
  canvas.toBlob((blob) => {
    if (!blob)
      return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `spectrum-${new Date().toISOString().replace(/[:.]/g, '-')}.png`
    a.click()
    URL.revokeObjectURL(url)
  }, 'image/png')
}

// ── 派生信息 ──
const spanInfo = computed(() => {
  const f = latest.value
  if (!f || f.freq_hz.length < 2)
    return ''
  const viewLo = fracToHz(zoomStart)
  const viewHi = fracToHz(zoomEnd)
  const spanHz = viewHi - viewLo
  const bins = f.spectrum_db.length
  const fullSpanHz = f.freq_hz.at(-1)! - f.freq_hz[0]!
  const viewBins = Math.max(1, Math.round(bins * (zoomEnd - zoomStart)))
  const rbwHz = spanHz / viewBins
  const parts = [`跨度 ${formatSpan(spanHz)}`, `RBW ${formatRbw(rbwHz)}`]
  if (traceRenderer.isZoomed)
    parts.push(`全带 ${formatSpan(fullSpanHz)}`)
  return parts.join(' · ')
})

watch(spanInfo, () => { /* 触发一次重绘以刷新缩放标签 */ dirty = true })
watch(zoomLabel, () => { dirty = true })

let ro: ResizeObserver | null = null
let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  syncRenderers()
  resize()
  ro = new ResizeObserver(() => {
    const wasEmpty = wfFrames.length === 0
    resize()
    // resize 会清空画布 → 从帧历史整幅重绘瀑布（修复旧实现 resize 后瀑布消失）
    if (!wasEmpty)
      redrawWaterfallAll()
    dirty = true
  })
  if (containerRef.value)
    ro.observe(containerRef.value)
  window.addEventListener('resize', resize)
  connect()
  rafId = requestAnimationFrame(loop)
  timer = setInterval(() => {
    // 缩放状态徽章
    zoomLabel.value = traceRenderer.isZoomed
      ? `缩放 ${((zoomEnd - zoomStart) * 100).toFixed(0)}%`
      : ''
  }, 500)
})

onUnmounted(() => {
  disconnect()
  ro?.disconnect()
  window.removeEventListener('resize', resize)
  if (timer)
    clearInterval(timer)
  if (rafId !== null)
    cancelAnimationFrame(rafId)
})
</script>

<template>
  <div class="flex flex-col gap-2 w-full">
    <!-- 状态行：徽章 + 量程信息 + 光标读数（独立槽位，不再互相叠字） -->
    <div class="flex flex-wrap items-center gap-2 text-sm min-w-0">
      <span class="font-medium shrink-0">SDR 实时频谱 · 瀑布图</span>
      <span v-if="props.mode" class="px-1.5 py-0.5 rounded bg-#4f8cff/20 text-#4f8cff font-mono text-xs shrink-0">{{ props.mode }}</span>
      <span v-if="!connected" class="px-1.5 py-0.5 rounded bg-#ef4444/20 text-#ef4444 text-xs flex items-center gap-1 shrink-0">
        <span class="w-2 h-2 rounded-full bg-#ef4444 animate-pulse" /> 断连 · 重连中
      </span>
      <span v-else-if="degraded" class="px-1.5 py-0.5 rounded bg-#f59e0b/20 text-#f59e0b text-xs shrink-0">仿真数据（未接真机）</span>
      <span v-else class="px-1.5 py-0.5 rounded bg-#22c55e/20 text-#22c55e text-xs shrink-0">IC-705 直连</span>
      <span v-if="spanInfo" class="opacity-60 font-mono text-xs shrink-0">{{ spanInfo }}</span>
      <span v-if="zoomLabel" class="px-1.5 py-0.5 rounded bg-#a855f7/20 text-#a855f7 font-mono text-xs shrink-0">{{ zoomLabel }}</span>
      <span class="flex-1 min-w-2" />
      <span class="font-mono text-xs opacity-80 shrink-0 text-right">{{ cursorInfo || '悬停读数 · 拖拽框选放大 · Shift 拖拽平移 · 双击复位' }}</span>
    </div>

    <!-- 画布 -->
    <div ref="containerRef" class="w-full rounded-lg overflow-hidden border border-white/10 bg-#0b0b16">
      <canvas
        ref="canvasRef"
        class="block cursor-crosshair"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseLeave"
        @dblclick="onDblClick"
        @wheel="onWheel"
        @contextmenu="onContextMenu"
      />
    </div>

    <!-- 频谱右键菜单：标记干扰源 / 标记信号 → 写 GRAG 五元组 -->
    <Teleport to="body">
      <div
        v-if="ctxMenu"
        class="fixed z-[999] min-w-40 rounded-lg border border-white/15 bg-#1e1e2e shadow-xl py-1 text-sm"
        :style="{ left: `${ctxMenu.x}px`, top: `${ctxMenu.y}px` }"
        @click.stop
      >
        <div class="px-3 py-1 text-xs opacity-60 font-mono">{{ ctxMenu.mhz }} MHz</div>
        <button class="w-full text-left px-3 py-1.5 hover:bg-white/10" @click="markFromMenu">
          标记干扰源 → 记忆
        </button>
        <button class="w-full text-left px-3 py-1.5 hover:bg-white/10" @click="markFromMenu">
          标记信号 → 记忆
        </button>
      </div>
    </Teleport>

    <!-- 控制区：分组、可换行、不重叠 -->
    <div class="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
      <div class="flex items-center gap-1.5 shrink-0">
        <span class="opacity-50">频率 MHz</span>
        <input
          v-model="freqInput"
          type="number"
          step="0.001"
          class="w-24 bg-white/10 rounded px-2 py-0.5 font-mono"
          @keyup.enter="tuneFromInput"
          @blur="tuneFromInput"
        >
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <span class="opacity-50">配色</span>
        <select v-model="colormapName" class="bg-white/10 rounded px-1.5 py-0.5">
          <option value="classic">经典</option>
          <option value="blackgold">黑金</option>
          <option value="military">军绿</option>
        </select>
        <label class="flex items-center gap-1 cursor-pointer">
          <input v-model="wfInvert" type="checkbox" class="accent-blue-500">
          <span>反色</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer" title="gamma>1 压暗中间调、强信号更突出">
          <span class="opacity-50">γ</span>
          <input v-model.number="gamma" type="range" min="0.4" max="2.5" step="0.1" class="w-14">
          <span class="font-mono w-6">{{ gamma.toFixed(1) }}</span>
        </label>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <span class="opacity-50">量程</span>
        <label class="flex items-center gap-1" title="下限 dB">
          <input v-model.number="dbFloor" type="range" min="-140" max="-10" step="1" class="w-20">
          <span class="font-mono w-9">{{ dbFloor }}</span>
        </label>
        <label class="flex items-center gap-1" title="上限 dB">
          <input v-model.number="dbCeiling" type="range" min="-60" max="0" step="1" class="w-16">
          <span class="font-mono w-7">{{ dbCeiling }}</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer">
          <input v-model="autoFloor" type="checkbox" class="accent-blue-500">
          <span>AGC</span>
        </label>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <span class="opacity-50">轨迹</span>
        <label class="flex items-center gap-1 cursor-pointer" title="指数平滑，0=原始">
          <span class="opacity-50">平滑</span>
          <input v-model.number="smoothing" type="range" min="0" max="0.9" step="0.05" class="w-14">
          <span class="font-mono w-7">{{ smoothing.toFixed(2) }}</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer" title="峰值保持，0.4dB/帧衰减">
          <input v-model="showPeakHold" type="checkbox" class="accent-blue-500">
          <span>峰值</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer" title="滚动窗口逐 bin 最小值噪声底">
          <input v-model="showNoiseFloor" type="checkbox" class="accent-blue-500">
          <span>噪声底</span>
        </label>
        <label class="flex items-center gap-1 cursor-pointer">
          <input v-model="signalFill" type="checkbox" class="accent-blue-500">
          <span>柱状填充</span>
        </label>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <label class="flex items-center gap-1 cursor-pointer" title="按模式给出典型显示带宽，可手动改（非电台滤波器设置）">
          <input v-model="showBandwidth" type="checkbox" class="accent-blue-500">
          <span>带宽</span>
        </label>
        <select v-model.number="bandwidthHz" class="bg-white/10 rounded px-1.5 py-0.5" :disabled="!showBandwidth">
          <option :value="500">500 Hz</option>
          <option :value="2700">2.7 kHz</option>
          <option :value="9000">9 kHz</option>
          <option :value="12500">12.5 kHz</option>
          <option :value="200000">200 kHz</option>
        </select>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <label class="flex items-center gap-1 cursor-pointer">
          <input v-model="freeze" type="checkbox" class="accent-blue-500">
          <span>冻结</span>
        </label>
        <label class="flex items-center gap-1">
          <span class="opacity-50">瀑布</span>
          <select v-model.number="waterfallH" class="bg-white/10 rounded px-1.5 py-0.5">
            <option :value="WATERFALL_H_OPTIONS[0]">矮</option>
            <option :value="WATERFALL_H_OPTIONS[1]">中</option>
            <option :value="WATERFALL_H_OPTIONS[2]">高</option>
          </select>
        </label>
        <button class="px-2 py-0.5 rounded bg-white/10 hover:bg-white/20" title="导出当前画面 PNG" @click="exportPng">
          截图
        </button>
      </div>
    </div>
  </div>
</template>
