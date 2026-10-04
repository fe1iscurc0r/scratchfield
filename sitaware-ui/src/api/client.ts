// 类型化 API 客户端。所有请求走 VITE_API_BASE（默认 `/api`，由 vite 代理到 :18000）。
import type {
  FeatureCollection, AlertRule, QueryResult, RoutePayload, Metrics, Feature, SummaryResult,
} from './types'

const BASE: string = (import.meta.env.VITE_API_BASE as string) || '/api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!r.ok) throw new Error(`${path} -> HTTP ${r.status}`)
  return (await r.json()) as T
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) q.set(k, String(v))
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const api = {
  listEvents(params: Record<string, string | number | undefined> = {}) {
    return req<FeatureCollection>(`/events${qs(params)}`)
  },
  getEvent(id: string) { return req<Feature>(`/events/${id}`) },
  createEvent(body: any) {
    return req<Feature>('/events', { method: 'POST', body: JSON.stringify(body) })
  },
  summary(body: { time_window_hours?: number; region?: number[] | null }) {
    return req<SummaryResult>('/situation/summary', { method: 'POST', body: JSON.stringify(body) })
  },
  query(body: { text: string }) {
    return req<QueryResult>('/situation/query', { method: 'POST', body: JSON.stringify(body) })
  },
  geocode(body: { text: string }) {
    return req<any>('/geocode', { method: 'POST', body: JSON.stringify(body) })
  },
  route(params: Record<string, string | number | boolean | undefined>) {
    return req<RoutePayload>(`/route${qs(params)}`)
  },
  listAlerts() { return req<AlertRule[]>('/alerts') },
  createAlert(body: any) { return req<AlertRule>('/alerts', { method: 'POST', body: JSON.stringify(body) }) },
  deleteAlert(id: string) { return req<{ ok: boolean }>(`/alerts/${id}`, { method: 'DELETE' }) },
  hamStations() { return req<FeatureCollection>('/ham/stations') },
  metrics() { return req<Metrics>('/metrics') },
}

/** 建立 SSE 连接，返回 EventSource（调用方负责 close）。 */
export function streamEvents(
  onMessage: (data: any) => void,
  onError?: (e: any) => void,
): EventSource {
  const es = new EventSource(BASE + '/events/stream')
  es.addEventListener('event', (e: any) => {
    try { onMessage(JSON.parse(e.data)) } catch { /* ignore malformed */ }
  })
  es.addEventListener('ready', () => { /* handshake */ })
  es.onerror = (e: any) => { onError?.(e) }
  return es
}
