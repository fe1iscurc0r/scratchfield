import { appendAgentMessage, CURRENT_SESSION_ID, proactiveNotifier } from '@/utils/session'

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let manuallyClosed = false

// HMR 兜底：模块重载时先清理旧连接
if (import.meta.hot) {
  import.meta.hot.accept(() => {
    disconnectRealtimeUi()
  })
}

function buildWebSocketUrl() {
  const endpoint = import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin
  const url = new URL(endpoint)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = '/ws'
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
    connectRealtimeUi()
  }, delay)
}

async function handleMessage(event: MessageEvent<string>) {
  try {
    const payload = JSON.parse(event.data)
    if (payload?.type !== 'proactive_message' || !payload.content)
      return

    const source = payload.source || 'ProactiveVision'
    const sessionId = typeof payload.session_id === 'string' ? payload.session_id : ''

    if (sessionId && !CURRENT_SESSION_ID.value)
      CURRENT_SESSION_ID.value = sessionId

    appendAgentMessage({
      role: 'assistant',
      content: payload.content,
      sender: source,
    })

    proactiveNotifier.value?.(source, payload.content)
  }
  catch (error) {
    console.debug('[RealtimeUI] 忽略无法解析的消息', error)
  }
}

export function connectRealtimeUi() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING))
    return

  manuallyClosed = false
  clearReconnectTimer()

  const ws = new WebSocket(buildWebSocketUrl())
  socket = ws

  ws.addEventListener('open', () => {
    reconnectAttempts = 0
  })

  ws.addEventListener('message', handleMessage)

  ws.addEventListener('close', () => {
    if (socket === ws)
      socket = null
    scheduleReconnect()
  })

  ws.addEventListener('error', () => {
    ws.close()
  })
}

export function disconnectRealtimeUi() {
  manuallyClosed = true
  clearReconnectTimer()
  reconnectAttempts = 0
  if (socket) {
    socket.close()
    socket = null
  }
}
