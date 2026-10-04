import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, streamEvents } from '@/api/client'
import type { Feature, AlertRule, Metrics, QueryResult, RoutePayload } from '@/api/types'

const CITY_CENTER: Record<string, [number, number]> = {
  guangzhou: [23.1291, 113.2644],
  shenzhen: [22.5431, 114.0579],
  beijing: [39.9042, 116.4074],
  shanghai: [31.2304, 121.4737],
  chengdu: [30.5728, 104.0668],
}

export const useSitaware = defineStore('sitaware', () => {
  const events = ref<Feature[]>([])
  const metrics = ref<Metrics | null>(null)
  const alerts = ref<AlertRule[]>([])
  const hamStations = ref<Feature[]>([])
  const selectedId = ref<string | null>(null)
  const filters = ref({ event_type: '', severity: '', source: '', date_from: '', date_to: '', q: '' })
  const timeCursor = ref<number | null>(null) // 仅显示该时间戳之前的事件
  const city = ref<string>('guangzhou')
  const queryHistory = ref<{ text: string; res: QueryResult }[]>([])
  const routePayload = ref<RoutePayload | null>(null)
  const layers = ref({ events: true, heat: false, ham: true })
  const soundOn = ref<boolean>(true)
  const es = ref<EventSource | null>(null)
  const connected = ref<boolean>(false)
  const activeTab = ref<string>('alerts')
  const sharedView = ref<any>(null)

  const selectedEvent = computed<Feature | null>(
    () => events.value.find((e) => e.id === selectedId.value) || null,
  )
  const cityCenter = computed<[number, number]>(() => CITY_CENTER[city.value] || CITY_CENTER.guangzhou)

  // 时间轴 / 筛选后的可见事件
  const visibleEvents = computed<Feature[]>(() => {
    let list = events.value
    if (timeCursor.value) {
      list = list.filter((e) => new Date((e.properties.reported_at as string) || 0).getTime() <= timeCursor.value!)
    }
    const q = filters.value.q.trim().toLowerCase()
    if (q) {
      list = list.filter((e) => {
        const p = e.properties
        return (
          (p.title && String(p.title).toLowerCase().includes(q)) ||
          (p.description && String(p.description).toLowerCase().includes(q)) ||
          (p.tags && (p.tags as string[]).some((t) => t.toLowerCase().includes(q)))
        )
      })
    }
    return list
  })

  async function refreshEvents() {
    const f = filters.value
    const params: Record<string, string | undefined> = {}
    if (f.event_type) params.event_type = f.event_type
    if (f.severity) params.severity = f.severity
    if (f.source) params.source = f.source
    if (f.date_from) params.date_from = f.date_from
    if (f.date_to) params.date_to = f.date_to
    const fc = await api.listEvents(params)
    events.value = fc.features
  }
  async function loadMetrics() { metrics.value = await api.metrics() }
  async function loadAlerts() { alerts.value = await api.listAlerts() }
  async function loadHam() { const fc = await api.hamStations(); hamStations.value = fc.features }
  async function loadAll() {
    await Promise.all([refreshEvents(), loadMetrics(), loadAlerts(), loadHam()])
  }

  function startStream() {
    if (es.value) return
    es.value = streamEvents(
      (data) => {
        connected.value = true
        if (data.type === 'event' && data.feature) {
          const f = data.feature as Feature
          const idx = events.value.findIndex((e) => e.id === f.id)
          if (idx >= 0) events.value[idx] = f
          else events.value.unshift(f)
          loadMetrics()
        }
      },
      () => { connected.value = false },
    )
  }
  function stopStream() {
    es.value?.close()
    es.value = null
    connected.value = false
  }

  function select(id: string | null) { selectedId.value = id }
  function setCity(c: string) { city.value = c }
  function setTab(t: string) { activeTab.value = t }
  function applySharedView(v: any) { sharedView.value = v }

  async function createAlert(body: any) {
    const r = await api.createAlert(body)
    alerts.value.push(r)
    return r
  }
  async function deleteAlert(id: string) {
    await api.deleteAlert(id)
    alerts.value = alerts.value.filter((a) => a.id !== id)
  }
  async function ask(text: string) {
    const res = await api.query({ text })
    queryHistory.value.unshift({ text, res })
    return res
  }
  async function planRoute(params: Record<string, string | number | boolean | undefined>) {
    routePayload.value = await api.route(params)
    return routePayload.value
  }

  return {
    events, metrics, alerts, hamStations, selectedId, selectedEvent, filters, timeCursor,
    city, cityCenter, queryHistory, routePayload, layers, soundOn, connected, visibleEvents,
    activeTab, sharedView,
    refreshEvents, loadMetrics, loadAlerts, loadHam, loadAll,
    startStream, stopStream, select, setCity, setTab, applySharedView, createAlert, deleteAlert, ask, planRoute,
  }
})
