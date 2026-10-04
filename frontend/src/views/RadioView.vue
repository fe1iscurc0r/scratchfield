<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import API from '@/api/core'
import EmptyState from '@/components/EmptyState.vue'
import SentinelPanel from '@/components/SentinelPanel.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import SpectrumPanel from '@/components/SpectrumPanel.vue'
import { feedback } from '@/utils/feedback'

// ── 状态 ──
const freqMhz = ref(7.074)
const mode = ref('USB')
const ptt = ref<'TX' | 'RX'>('RX')
const mock = ref(true)
const sUnit = ref(0)
const sDb = ref(-127)
// 卷150：电台在线状态（refreshStatus 成功/失败驱动；初始 connecting 骨架）
const rigStatus = ref<'connecting' | 'online' | 'offline'>('connecting')

const MODES = ['LSB', 'USB', 'AM', 'CW', 'RTTY', 'FM', 'WFM', 'CW-R', 'RTTY-R']

// ── 步进档位（调谐轮用）──
const STEP_OPTIONS = [
  { label: '100 Hz', khz: 0.1 },
  { label: '500 Hz', khz: 0.5 },
  { label: '1 kHz', khz: 1 },
  { label: '5 kHz', khz: 5 },
  { label: '10 kHz', khz: 10 },
]
const stepIdx = ref(2) // 默认 1 kHz
const currentStep = computed(() => STEP_OPTIONS[stepIdx.value]!)

// ── 频段表 ──
// IC-705 业余频段常用呼叫频点。⚠️ 与后端 AMATEUR_BANDS 白名单交叉校验：
//   apiserver/routes/radio.py AMATEUR_BANDS = (1.8~30MHz, 50~54MHz, 144~148MHz)
//   凡越界项标 inWhitelist:false，点击时前置拦截并提示，避免撞后端 422。
// TODO(后端): 70cm(430~440MHz)/6m 之外的 IC-705 支持段（如 1.25m）后端尚无白名单，
//   如后续要放开，需同步扩 apiserver/routes/radio.py 的 AMATEUR_BANDS。
interface Band { name: string, mhz: number, modes: string[], inWhitelist: boolean }
const BANDS: Band[] = [
  { name: '160m', mhz: 1.840, modes: ['LSB', 'CW'], inWhitelist: true },
  { name: '80m', mhz: 3.573, modes: ['LSB', 'CW'], inWhitelist: true },
  { name: '60m', mhz: 5.357, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '40m', mhz: 7.074, modes: ['LSB', 'CW'], inWhitelist: true },
  { name: '30m', mhz: 10.136, modes: ['CW', 'RTTY'], inWhitelist: true },
  { name: '20m', mhz: 14.074, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '17m', mhz: 18.100, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '15m', mhz: 21.074, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '12m', mhz: 24.915, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '10m', mhz: 28.074, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '6m', mhz: 50.313, modes: ['USB', 'CW'], inWhitelist: true },
  { name: '2m', mhz: 144.174, modes: ['USB', 'FM'], inWhitelist: true },
  { name: '70cm', mhz: 430.500, modes: ['FM', 'USB'], inWhitelist: false },
]
const activeBand = computed(() => BANDS.find(b => Math.abs(b.mhz - freqMhz.value) < 0.0005)?.name ?? '')

// ── 发射区：TX 超时保护（防猫扑键盘）──
const TX_TIMEOUT_MS = 10 * 60 * 1000
const txElapsed = ref(0)
let txTimer: ReturnType<typeof setInterval> | null = null

// ── 记忆区：VFO A/B + MEM 通道（localStorage 持久化）──
interface MemChannel { freq: number, mode: string, note: string }
const MEM_KEY = 'lumo.radio.mem'
const vfo = ref<'A' | 'B'>('A')
const vfoStore = ref<Record<'A' | 'B', { freq: number, mode: string }>>({
  A: { freq: 7.074, mode: 'USB' },
  B: { freq: 14.074, mode: 'USB' },
})
const memChannels = ref<Record<string, MemChannel>>({})
const memSlot = ref(1)

function loadMem() {
  try {
    const raw = localStorage.getItem(MEM_KEY)
    if (raw)
      memChannels.value = JSON.parse(raw)
  }
  catch {
    memChannels.value = {} // 存储损坏时静默归零，不阻断面板
  }
}
function saveMem() {
  try {
    localStorage.setItem(MEM_KEY, JSON.stringify(memChannels.value))
  }
  catch (e: any) {
    feedback.warn('记忆通道保存失败', e.message)
  }
}
const memList = computed(() => Object.entries(memChannels.value)
  .map(([slot, ch]) => ({ slot: +slot, ...ch }))
  .sort((a, b) => a.slot - b.slot))

// ── 记日志弹窗 ──
const logVisible = ref(false)
const logForm = ref({ callsign: '', rst_sent: '59', rst_rcvd: '59', remarks: '' })
const logging = ref(false)

// ── QSL 卡债角标 ──
const qslDebts = ref(0)
const qslLoading = ref(false)

// ── 滤波器 / AGC ──
// TODO(后端): /api/radio/* 目前只有 status/frequency/mode/ptt/log/qsl-debts/spectrum-ws，
//   无滤波器宽度与 AGC 设置端点。此处仅做本地 UI 状态，未对接后端（禁止自造 API）。
//   后端补齐后，把 setFilter/setAgc 接到真实端点即可。
const filterWidth = ref<'wide' | 'mid' | 'narrow'>('mid')
const agcSpeed = ref<'fast' | 'slow'>('fast')
const FILTER_LABELS: Record<string, string> = { wide: '宽', mid: '中', narrow: '窄' }
const AGC_LABELS: Record<string, string> = { fast: '快', slow: '慢' }

function setFilter(w: 'wide' | 'mid' | 'narrow') {
  filterWidth.value = w
  feedback.warn(`滤波器 ${FILTER_LABELS[w]}（本地）`, '后端 /api/radio/* 暂无该字段，待补')
}
function setAgc(s: 'fast' | 'slow') {
  agcSpeed.value = s
  feedback.warn(`AGC ${AGC_LABELS[s]}（本地）`, '后端 /api/radio/* 暂无该字段，待补')
}

// ── 频谱右键：标记干扰源 → GRAG 五元组 ──
const markVisible = ref(false)
const markForm = ref({ freq: 0, label: '', kind: 'interference' as 'interference' | 'signal' })
const marking = ref(false)

function openMark(mhz: number) {
  markForm.value = { freq: +mhz.toFixed(6), label: '', kind: 'interference' }
  markVisible.value = true
}
async function submitMark() {
  marking.value = true
  try {
    // 走 GRAG 五元组接口（用户-标记-类型-频率），打通哨兵网格闭环
    await API.instance.post('/memory/quintuples', {
      subject: '用户',
      subject_type: 'Person',
      predicate: markForm.value.kind === 'interference' ? '标记干扰源' : '标记信号',
      object: `${markForm.value.freq} MHz${markForm.value.label ? ` (${markForm.value.label})` : ''}`,
      object_type: 'RadioFrequency',
    })
    feedback.success('已写入记忆')
    markVisible.value = false
  }
  catch (e: any) {
    feedback.error('写入记忆失败', e?.response?.data?.detail || e.message)
  }
  finally {
    marking.value = false
  }
}

// ── API 调用 ──
async function refreshStatus() {
  try {
    const res: any = await API.instance.get('/api/radio/status')
    freqMhz.value = res.freqMhz
    mode.value = res.mode
    ptt.value = res.ptt === 'TX' ? 'TX' : 'RX'
    mock.value = res.mock
    sUnit.value = res.s_unit ?? 0
    sDb.value = res.s_db ?? -127
    rigStatus.value = 'online'
  }
  catch (e: any) {
    rigStatus.value = 'offline'
    feedback.error('读取电台状态失败', e?.response?.data?.detail || e.message)
  }
}

async function refreshDebts() {
  qslLoading.value = true
  try {
    const res: any = await API.instance.get('/api/radio/qsl-debts', { params: { direction: 'owed' } })
    qslDebts.value = res.count
  }
  catch {
    qslDebts.value = 0
  }
  finally {
    qslLoading.value = false
  }
}

async function setFreq(target: number) {
  const t = +target.toFixed(6)
  if (t <= 0)
    return
  try {
    const res: any = await API.instance.post('/api/radio/frequency', { freq_mhz: t })
    freqMhz.value = res.freqMhz
  }
  catch (e: any) {
    feedback.error('设置频率失败', e?.response?.data?.detail || e.message)
  }
}

function stepFrequency(khz: number) {
  setFreq(freqMhz.value + khz / 1000)
}

// 调谐轮（SDR 风格）：主步进 / Shift 微调 (1/10) / Ctrl 粗调 (×10)
function wheelTune(e: WheelEvent) {
  const dir = e.deltaY > 0 ? -1 : 1
  let mult = 1
  if (e.shiftKey)
    mult = 0.1
  else if (e.ctrlKey)
    mult = 10
  stepFrequency(dir * currentStep.value.khz * mult)
}

// 拖拽调谐（SDR# 风格）：横向拖拽按步进换频
let dragLastX: number | null = null
function dragStart(e: MouseEvent) {
  dragLastX = e.clientX
}
function dragMove(e: MouseEvent) {
  if (dragLastX === null)
    return
  const dx = e.clientX - dragLastX
  const perPx = Math.max(1, e.shiftKey ? 1 : 8) // 每 8px 一个步进
  if (Math.abs(dx) < perPx)
    return
  const ticks = Math.trunc(dx / perPx)
  dragLastX += ticks * perPx
  stepFrequency(ticks * currentStep.value.khz)
}
function dragEnd() {
  dragLastX = null
}

function jumpBand(b: Band) {
  if (!b.inWhitelist) {
    feedback.warn(`${b.name} 不在后端白名单`, '后端 AMATEUR_BANDS 仅放开 1.8~30 / 50~54 / 144~148 MHz，该频段需先扩白名单')
    return
  }
  setFreq(b.mhz)
}

function tuneToFreq(mhz: number) {
  setFreq(mhz)
}

async function setMode(m: string) {
  try {
    const res: any = await API.instance.post('/api/radio/mode', { mode: m })
    mode.value = res.mode
  }
  catch (e: any) {
    feedback.error('切换模式失败', e?.response?.data?.detail || e.message)
  }
}

async function togglePtt() {
  const next = ptt.value === 'TX' ? 'RX' : 'TX'
  try {
    const res: any = await API.instance.post('/api/radio/ptt', { state: next })
    ptt.value = res.state === 'TX' ? 'TX' : 'RX'
    if (ptt.value === 'TX')
      startTxTimer()
    else
      stopTxTimer()
  }
  catch (e: any) {
    feedback.error('PTT 控制失败', e?.response?.data?.detail || e.message)
  }
}

function startTxTimer() {
  txElapsed.value = 0
  stopTxTimer()
  txTimer = setInterval(() => {
    txElapsed.value += 1000
    if (txElapsed.value >= TX_TIMEOUT_MS) {
      stopTxTimer()
      // 超时自动回 RX（防猫扑键盘长时间占用发射）
      API.instance.post('/api/radio/ptt', { state: 'RX' })
        .then(() => {
          ptt.value = 'RX'
          feedback.warn('TX 超时保护触发', '已连续发射 10 分钟，自动回 RX')
        })
        .catch(() => {})
    }
  }, 1000)
}
function stopTxTimer() {
  if (txTimer) {
    clearInterval(txTimer)
    txTimer = null
  }
  txElapsed.value = 0
}
const txElapsedText = computed(() => {
  const s = Math.floor(txElapsed.value / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})

// PTT 空格键映射（焦点在面板内且不在输入框时才触发）
const panelRef = ref<HTMLElement | null>(null)
function onKeydown(e: KeyboardEvent) {
  if (e.code !== 'Space' || e.repeat)
    return
  const el = e.target as HTMLElement | null
  const tag = el?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select' || el?.isContentEditable)
    return
  if (!panelRef.value?.contains(el))
    return
  e.preventDefault()
  togglePtt()
}

// ── VFO / MEM ──
function switchVfo(target: 'A' | 'B') {
  // 切 VFO 前先把当前值存回当前 VFO
  vfoStore.value[vfo.value] = { freq: freqMhz.value, mode: mode.value }
  vfo.value = target
  const st = vfoStore.value[target]
  setFreq(st.freq)
  if (st.mode !== mode.value)
    setMode(st.mode)
}
function storeMem() {
  memChannels.value[String(memSlot.value)] = {
    freq: freqMhz.value,
    mode: mode.value,
    note: '',
  }
  saveMem()
  feedback.success(`已存入 MEM-${memSlot.value}`)
}
function recallMem(slot: number) {
  const ch = memChannels.value[String(slot)]
  if (!ch)
    return
  setFreq(ch.freq)
  if (ch.mode !== mode.value)
    setMode(ch.mode)
}
function deleteMem(slot: number) {
  delete memChannels.value[String(slot)]
  saveMem()
}

// ── 记日志 ──
function openLog() {
  logForm.value = { callsign: '', rst_sent: '59', rst_rcvd: '59', remarks: '' }
  logVisible.value = true
}

async function submitLog() {
  if (!logForm.value.callsign.trim()) {
    feedback.warn('请填写对方呼号')
    return
  }
  logging.value = true
  try {
    const res: any = await API.instance.post('/api/radio/log', {
      callsign: logForm.value.callsign,
      rst_sent: logForm.value.rst_sent,
      rst_rcvd: logForm.value.rst_rcvd,
      remarks: logForm.value.remarks,
      freq_mhz: freqMhz.value,
      mode: mode.value,
    })
    feedback.success(`已写入 HamLog：${res.callsign}`)
    logVisible.value = false
    refreshDebts()
  }
  catch (e: any) {
    feedback.error('写入日志失败', e?.response?.data?.detail || e.message)
  }
  finally {
    logging.value = false
  }
}

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  loadMem()
  refreshStatus()
  refreshDebts()
  timer = setInterval(refreshStatus, 3000)
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  if (timer)
    clearInterval(timer)
  stopTxTimer()
  window.removeEventListener('keydown', onKeydown)
})

defineExpose({ onKeydown })
</script>

<template>
  <div ref="panelRef" class="flex flex-col items-center gap-4 px-6 py-5 h-full overflow-auto">
    <!-- 卷150：连接三态（骨架 / 离线空态 / 在线面板） -->
    <div v-if="rigStatus === 'connecting'" class="w-full max-w-5xl">
      <SkeletonCard variant="image" />
      <SkeletonCard variant="text" :rows="3" />
    </div>
    <EmptyState
      v-else-if="rigStatus === 'offline'"
      error
      title="电台未连接"
      description="后端 /api/radio/status 不可达——请确认 apiserver 已启动、IC-705 / SDR 已连接"
      action-label="重试连接"
      class="w-full max-w-5xl"
      @action="rigStatus = 'connecting'; refreshStatus()"
    />
    <template v-else>
      <!-- ══════════ 1. 状态区 ══════════ -->
      <div class="w-full max-w-5xl rounded-xl border border-white/10 bg-white/5 p-4 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div class="flex items-baseline gap-2 font-mono">
          <span class="text-5xl font-bold tracking-tight">{{ freqMhz.toFixed(3) }}</span>
          <span class="text-xl opacity-60">MHz</span>
          <span v-if="activeBand" class="ml-2 px-2 py-0.5 rounded bg-#4f8cff/20 text-#4f8cff text-sm">{{ activeBand }}</span>
        </div>

        <div class="flex items-center gap-2 text-sm">
          <span class="px-2 py-1 rounded bg-white/10 font-mono">{{ mode }}</span>
          <span class="px-2 py-1 rounded bg-white/10 text-xs">滤波 {{ FILTER_LABELS[filterWidth] }}</span>
          <span class="px-2 py-1 rounded bg-white/10 text-xs">AGC {{ AGC_LABELS[agcSpeed] }}</span>
        </div>

        <!-- S 表 -->
        <div class="flex items-center gap-3 font-mono text-sm">
          <span class="opacity-70">S 表</span>
          <div class="w-40 h-3 rounded bg-white/10 overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-#22c55e via-#eab308 to-#ef4444"
              :style="{ width: `${Math.min(100, Math.max(0, (sDb + 127) / 114 * 100))}%` }"
            />
          </div>
          <span class="font-bold">S{{ sUnit }}</span>
          <span class="opacity-60">{{ sDb }} dBm</span>
        </div>

        <!-- 电台状态灯（复用 SpectrumPanel 判定口径） -->
        <div class="flex items-center gap-2 text-xs ml-auto">
          <span v-if="mock" class="px-2 py-1 rounded bg-#f59e0b/20 text-#f59e0b flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-#f59e0b" /> Mock 串口
          </span>
          <span v-else class="px-2 py-1 rounded bg-#22c55e/20 text-#22c55e flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-#22c55e" /> CI-V 直连
          </span>
        </div>
      </div>

      <!-- 模式选择（操作员高频操作，置于状态区下方） -->
      <div class="w-full max-w-5xl flex flex-wrap gap-1.5 items-center">
        <span class="text-xs opacity-60 mr-1">模式</span>
        <button
          v-for="m in MODES"
          :key="m"
          class="px-3 py-1 rounded-lg text-sm transition-colors"
          :class="mode === m ? 'bg-#4f8cff text-white' : 'border border-white/15 hover:bg-white/10'"
          @click="setMode(m)"
        >
          {{ m }}
        </button>
      </div>

      <!-- ══════════ 2. 频段快捷键组 ══════════ -->
      <div class="w-full max-w-5xl">
        <div class="text-xs opacity-60 mb-1.5">频段快捷跳转</div>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="b in BANDS"
            :key="b.name"
            class="px-2.5 py-1.5 rounded-lg text-sm font-mono transition-colors border"
            :class="[
              activeBand === b.name ? 'bg-#4f8cff text-white border-#4f8cff' : 'border-white/15 hover:bg-white/10',
              b.inWhitelist ? '' : 'opacity-45 border-dashed',
            ]"
            :title="b.inWhitelist ? `${b.mhz} MHz` : '不在后端白名单，点击会提示'"
            @click="jumpBand(b)"
          >
            {{ b.name }}
          </button>
        </div>
      </div>

      <!-- ══════════ 3. 调谐区 ══════════ -->
      <div class="w-full max-w-5xl rounded-xl border border-white/10 bg-white/5 p-4 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-60 mr-1">步进</span>
          <button
            v-for="(s, i) in STEP_OPTIONS"
            :key="s.label"
            class="px-2.5 py-1 rounded-lg text-xs font-mono transition-colors"
            :class="stepIdx === i ? 'bg-#4f8cff text-white' : 'border border-white/15 hover:bg-white/10'"
            @click="stepIdx = i"
          >
            {{ s.label }}
          </button>
        </div>

        <!-- 调谐轮 -->
        <div
          class="flex items-center gap-2 select-none cursor-ns-resize rounded-lg border border-white/15 px-3 py-2 hover:bg-white/5"
          title="滚轮调谐 · Shift 微调(1/10) · Ctrl 粗调(×10) · 横向拖拽亦可"
          @wheel.prevent="wheelTune"
          @mousedown="dragStart"
          @mousemove="dragMove"
          @mouseup="dragEnd"
          @mouseleave="dragEnd"
        >
          <span class="text-lg">◎</span>
          <span class="text-xs opacity-70 font-mono">调谐轮 · {{ currentStep.label }}</span>
        </div>

        <div class="flex gap-1.5">
          <button class="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 font-mono text-sm" @click="stepFrequency(-currentStep.khz)">−</button>
          <button class="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 font-mono text-sm" @click="stepFrequency(currentStep.khz)">+</button>
        </div>
      </div>

      <!-- ══════════ 4. 发射区 ══════════ -->
      <div class="w-full max-w-5xl rounded-xl border border-white/10 bg-white/5 p-4 flex flex-wrap items-center gap-4">
        <button
          class="px-10 py-4 rounded-full text-xl font-bold transition-colors shadow-lg"
          :class="ptt === 'TX' ? 'bg-#ef4444 text-white ring-4 ring-#ef4444/30' : 'bg-#22c55e text-white'"
          @click="togglePtt"
        >
          PTT · {{ ptt }}
        </button>

        <div v-if="ptt === 'TX'" class="flex flex-col text-xs gap-0.5">
          <span class="text-#ef4444 font-mono font-bold">发射中 {{ txElapsedText }}</span>
          <span class="opacity-60">10 分钟自动回 RX（超时保护）</span>
        </div>
        <div v-else class="text-xs opacity-60">
          按住空格可快捷收发（焦点在面板内、非输入框时生效）
        </div>

        <div class="flex gap-1.5 ml-auto">
          <span class="text-xs opacity-60 self-center mr-1">滤波</span>
          <button
            v-for="w in (['wide', 'mid', 'narrow'] as const)"
            :key="w"
            class="px-3 py-1.5 rounded-lg text-xs transition-colors"
            :class="filterWidth === w ? 'bg-#4f8cff text-white' : 'border border-white/15 hover:bg-white/10'"
            @click="setFilter(w)"
          >
            {{ FILTER_LABELS[w] }}
          </button>
          <span class="text-xs opacity-60 self-center mx-1">AGC</span>
          <button
            v-for="s in (['fast', 'slow'] as const)"
            :key="s"
            class="px-3 py-1.5 rounded-lg text-xs transition-colors"
            :class="agcSpeed === s ? 'bg-#4f8cff text-white' : 'border border-white/15 hover:bg-white/10'"
            @click="setAgc(s)"
          >
            {{ AGC_LABELS[s] }}
          </button>
        </div>
      </div>

      <!-- ══════════ 5. 记忆区 ══════════ -->
      <div class="w-full max-w-5xl rounded-xl border border-white/10 bg-white/5 p-4 flex flex-col gap-3">
        <div class="flex flex-wrap items-center gap-3">
          <span class="text-xs opacity-60">VFO</span>
          <button
            v-for="v in (['A', 'B'] as const)"
            :key="v"
            class="px-4 py-1.5 rounded-lg font-mono text-sm transition-colors"
            :class="vfo === v ? 'bg-#4f8cff text-white' : 'border border-white/15 hover:bg-white/10'"
            @click="switchVfo(v)"
          >
            VFO {{ v }}
          </button>
          <button class="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 text-sm" @click="switchVfo(vfo === 'A' ? 'B' : 'A')">
            交换 A/B
          </button>

          <div class="flex items-center gap-2 ml-auto">
            <span class="text-xs opacity-60">通道号</span>
            <input v-model.number="memSlot" type="number" min="1" max="99" class="w-16 px-2 py-1 rounded bg-black/30 border border-white/15 font-mono text-sm">
            <button class="px-3 py-1.5 rounded-lg bg-#4f8cff text-white text-sm" @click="storeMem">存入</button>
          </div>
        </div>

        <div v-if="memList.length" class="flex flex-wrap gap-1.5">
          <div
            v-for="ch in memList"
            :key="ch.slot"
            class="group flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 cursor-pointer"
            @click="recallMem(ch.slot)"
          >
            <span class="font-mono text-xs text-#4f8cff">M{{ String(ch.slot).padStart(2, '0') }}</span>
            <span class="font-mono text-xs">{{ ch.freq.toFixed(3) }}</span>
            <span class="text-xs opacity-60">{{ ch.mode }}</span>
            <button class="text-xs opacity-0 group-hover:opacity-60 hover:text-#ef4444" title="删除该通道" @click.stop="deleteMem(ch.slot)">✕</button>
          </div>
        </div>
        <div v-else class="text-xs opacity-50">暂无记忆通道 · 输入通道号后点「存入」，数据保存在本地</div>
      </div>

      <!-- ══════════ QSL 卡债 + 记日志 ══════════ -->
      <div class="w-full max-w-5xl flex items-center gap-4 flex-wrap">
        <button class="px-5 py-2.5 rounded-lg border border-white/15 hover:bg-white/10 transition-colors" @click="openLog">
          记日志
        </button>
        <div class="text-sm opacity-70 flex items-center gap-2">
          通联完成一键进 HamLog · QSL 卡债
          <span
            class="inline-flex items-center justify-center min-w-6 h-6 px-1.5 rounded-full text-xs font-bold"
            :class="qslDebts > 0 ? 'bg-#ef4444 text-white' : 'bg-white/10'"
          >
            {{ qslLoading ? '…' : qslDebts }}
          </span>
        </div>
      </div>

      <!-- ══════════ SDR 频谱 / 瀑布图 ══════════ -->
      <div class="w-full max-w-5xl">
        <SpectrumPanel :freq-mhz="freqMhz" :mode="mode" @tune="tuneToFreq" @mark="openMark" />
      </div>

      <!-- ══════════ 哨兵网格（卷187：LoRaCanary 节点回传） ══════════ -->
      <div class="w-full max-w-5xl">
        <SentinelPanel />
      </div>

      <!-- 记日志弹窗 -->
      <div v-if="logVisible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="logVisible = false">
        <div class="w-96 rounded-xl bg-#1e1e2e border border-white/10 p-5 flex flex-col gap-3">
          <h3 class="text-lg font-semibold">通联完成 · 记日志</h3>
          <label class="flex flex-col gap-1 text-sm">
            对方呼号 *
            <input v-model="logForm.callsign" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15" placeholder="BG8ABC">
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="flex flex-col gap-1 text-sm">
              我发 RST
              <input v-model="logForm.rst_sent" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15">
            </label>
            <label class="flex flex-col gap-1 text-sm">
              对方 RST
              <input v-model="logForm.rst_rcvd" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15">
            </label>
          </div>
          <label class="flex flex-col gap-1 text-sm">
            备注
            <input v-model="logForm.remarks" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15" placeholder="可选">
          </label>
          <div class="text-xs opacity-60">
            频率 {{ freqMhz.toFixed(3) }} MHz · 模式 {{ mode }} 已自动预填
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button class="px-4 py-2 rounded-lg border border-white/15 hover:bg-white/10" :disabled="logging" @click="logVisible = false">
              取消
            </button>
            <button class="px-4 py-2 rounded-lg bg-#4f8cff text-white" :disabled="logging" @click="submitLog">
              {{ logging ? '写入中…' : '保存到 HamLog' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 频谱标记弹窗（→ GRAG 五元组） -->
      <div v-if="markVisible" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="markVisible = false">
        <div class="w-96 rounded-xl bg-#1e1e2e border border-white/10 p-5 flex flex-col gap-3">
          <h3 class="text-lg font-semibold">标记频谱 · 写入记忆</h3>
          <div class="text-xs opacity-60">将写入 GRAG 五元组：用户 — 标记 — 频率（打通哨兵网格闭环）</div>
          <div class="flex gap-2">
            <button
              class="px-3 py-1.5 rounded-lg text-sm flex-1 transition-colors"
              :class="markForm.kind === 'interference' ? 'bg-#ef4444 text-white' : 'border border-white/15 hover:bg-white/10'"
              @click="markForm.kind = 'interference'"
            >
              标记干扰源
            </button>
            <button
              class="px-3 py-1.5 rounded-lg text-sm flex-1 transition-colors"
              :class="markForm.kind === 'signal' ? 'bg-#22c55e text-white' : 'border border-white/15 hover:bg-white/10'"
              @click="markForm.kind = 'signal'"
            >
              标记信号
            </button>
          </div>
          <label class="flex flex-col gap-1 text-sm">
            频率 (MHz)
            <input v-model.number="markForm.freq" type="number" step="0.001" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15 font-mono">
          </label>
          <label class="flex flex-col gap-1 text-sm">
            备注
            <input v-model="markForm.label" class="px-3 py-2 rounded-lg bg-black/30 border border-white/15" placeholder="可选，如「宽带噪声」">
          </label>
          <div class="flex justify-end gap-2 pt-2">
            <button class="px-4 py-2 rounded-lg border border-white/15 hover:bg-white/10" :disabled="marking" @click="markVisible = false">取消</button>
            <button class="px-4 py-2 rounded-lg bg-#4f8cff text-white" :disabled="marking" @click="submitMark">
              {{ marking ? '写入中…' : '写入记忆' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
