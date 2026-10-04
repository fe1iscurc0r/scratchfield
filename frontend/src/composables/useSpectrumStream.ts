import { ref } from 'vue'

// ── 类型 ──
export interface SpectrumFrame {
  type: 'spectrum'
  center_freq_hz: number
  center_freq_mhz: number
  sample_rate: number
  fft_size: number
  cols: number
  freq_hz: number[]
  spectrum_db: number[]
  source: string
  degraded: boolean
  timestamp: number
}

// ── 模块级状态（与 useRealtimeUi 同构：单连接 + 重连） ──
let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let manuallyClosed = false

const latest = ref<SpectrumFrame | null>(null)
const connected = ref(false)
const degraded = ref(false)

// HMR 兜底：模块重载时先清理旧连接
if (import.meta.hot) {
  import.meta.hot.accept(() => {
    disconnectSpectrumStream()
  })
}

function buildWebSocketUrl() {
  const endpoint = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
  const url = new URL(endpoint)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/api/radio/spectrum/ws'
  url.search = ''
  url.hash = ''
  return url.toString()
}

function clearReconnectTimer() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect() {
  if (manuallyClosed || reconnectTimer)
    return
  const delay = Math.min(1000 * 2 ** reconnectAttempts, 10000)
  reconnectAttempts += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectSpectrumStream()
  }, delay)
}

function handleMessage(event: MessageEvent<string>) {
  try {
    const frame: SpectrumFrame = JSON.parse(event.data)
    if (frame?.type !== 'spectrum' || !Array.isArray(frame.spectrum_db))
      return
    latest.value = frame
    degraded.value = frame.degraded === true
  }
  catch (error) {
    console.debug('[SpectrumStream] 忽略无法解析的帧', error)
  }
}

export function connectSpectrumStream() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING))
    return

  manuallyClosed = false
  clearReconnectTimer()

  const ws = new WebSocket(buildWebSocketUrl())
  socket = ws

  ws.addEventListener('open', () => {
    reconnectAttempts = 0
    connected.value = true
  })

  ws.addEventListener('message', handleMessage)

  ws.addEventListener('close', () => {
    connected.value = false
    if (socket === ws)
      socket = null
    scheduleReconnect()
  })

  ws.addEventListener('error', () => {
    ws.close()
  })
}

export function disconnectSpectrumStream() {
  manuallyClosed = true
  clearReconnectTimer()
  reconnectAttempts = 0
  connected.value = false
  if (socket) {
    socket.close()
    socket = null
  }
}

export function useSpectrumStream() {
  return {
    latest,
    connected,
    degraded,
    connect: connectSpectrumStream,
    disconnect: disconnectSpectrumStream,
  }
}
