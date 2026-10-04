<script setup lang="ts">
// F-01 地图底板：Leaflet + OSM 瓦片 + 标注/热力/电台图层；F-06 路线也在本层绘制。
import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet.heat'
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()
const mapEl = ref<HTMLElement | null>(null)
let map: any = null
let cluster: any = null
let heatLayer: any = null
let hamLayer: any = null
let routeGroup: any = null

const SEV_COLOR: Record<string, string> = {
  low: '#38bdf8', medium: '#eab308', high: '#f97316', critical: '#ef4444',
}

function sevColor(s: string): string {
  return SEV_COLOR[s] || '#38bdf8'
}

function buildCluster() {
  if (cluster) map.removeLayer(cluster)
  const Lany = L as any
  cluster = Lany.markerClusterGroup({ maxClusterRadius: 42, showCoverageOnHover: false })
  for (const f of store.visibleEvents) {
    const [lng, lat] = (f.geometry.coordinates as number[]) || []
    if (lng == null || lat == null) continue
    const p = f.properties
    const m = L.circleMarker([lat, lng], {
      radius: 7,
      color: sevColor(p.severity),
      fillColor: sevColor(p.severity),
      fillOpacity: 0.85,
      weight: 2,
    })
    m.bindPopup(
      `<b>${p.title || ''}</b><br/>` +
      `<span style="color:#8b97a5">${p.severity} · ${p.source} · ${p.event_type}</span><br/>` +
      `${p.description || ''}`,
    )
    m.on('click', () => store.select(f.id))
    cluster.addLayer(m)
  }
  map.addLayer(cluster)
}

function buildHeat() {
  const Lany = L as any
  if (heatLayer) map.removeLayer(heatLayer)
  const pts: any[] = []
  for (const f of store.visibleEvents) {
    const [lng, lat] = (f.geometry.coordinates as number[]) || []
    if (lng == null || lat == null) continue
    const w = { low: 0.3, medium: 0.55, high: 0.8, critical: 1 }[f.properties.severity] || 0.4
    pts.push([lat, lng, w])
  }
  heatLayer = Lany.heatLayer(pts, { radius: 26, blur: 18, maxZoom: 16, minOpacity: 0.25 })
  if (store.layers.heat) map.addLayer(heatLayer)
}

function buildHam() {
  if (hamLayer) map.removeLayer(hamLayer)
  hamLayer = L.layerGroup()
  for (const s of store.hamStations) {
    const [lng, lat] = (s.geometry.coordinates as number[]) || []
    if (lng == null || lat == null) continue
    const p = s.properties
    const m = L.circleMarker([lat, lng], {
      radius: 5, color: '#2dd4bf', fillColor: '#2dd4bf', fillOpacity: 0.9, weight: 2,
    })
    m.bindPopup(`<b>${p.call}</b><br/>${p.mode || ''} ${p.freq_mhz ? p.freq_mhz + ' MHz' : ''}<br/>${p.comment || ''}`)
    hamLayer.addLayer(m)
  }
  if (store.layers.ham) map.addLayer(hamLayer)
}

function buildRoute() {
  if (routeGroup) { map.removeLayer(routeGroup); routeGroup = null }
  const r = store.routePayload
  if (!r || !r.primary || !r.primary.geometry) return
  routeGroup = L.layerGroup()
  const toLatLngs = (coords: any[]) => coords.map((c: any) => [c[1], c[0]])
  const drawLine = (geom: any, color: string, dash: string | undefined, weight: number) => {
    if (!geom || !geom.coordinates) return
    L.polyline(toLatLngs(geom.coordinates), { color, weight, dashArray: dash, opacity: 0.9 })
      .addTo(routeGroup)
  }
  // 主路线
  drawLine(r.primary.geometry, '#3da9fc', undefined, 5)
  // 替代路线
  for (const a of r.alternatives || []) drawLine(a.geometry, '#94a3b8', '6 8', 3)
  // 风险段落（红色高亮）
  for (const seg of r.risk_segments || []) {
    if (seg.at) L.circleMarker([seg.at[1], seg.at[0]], { radius: 8, color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.9, weight: 2 }).addTo(routeGroup)
  }
  // 起终点
  if (r.start) L.marker([r.start[1], r.start[0]]).addTo(routeGroup).bindPopup('A')
  if (r.end) L.marker([r.end[1], r.end[0]]).addTo(routeGroup).bindPopup('B')
  map.addLayer(routeGroup)
  if (r.primary.geometry.coordinates?.length) {
    const c = r.primary.geometry.coordinates[0]
    map.setView([c[1], c[0]], 13)
  }
}

function rebuildAll() {
  if (!map) return
  buildCluster()
  buildHeat()
  buildHam()
  buildRoute()
}

function flyToEvent() {
  const e = store.selectedEvent
  if (!e) return
  const [lng, lat] = (e.geometry.coordinates as number[]) || []
  if (lng == null || lat == null) return
  map.setView([lat, lng], 14)
}

onMounted(() => {
  const [lat, lng] = store.cityCenter
  map = L.map(mapEl.value!, { center: [lat, lng], zoom: 12, zoomControl: true })
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap',
  }).addTo(map)
  rebuildAll()
})

onBeforeUnmount(() => { if (map) map.remove() })

watch(() => store.visibleEvents, rebuildAll, { deep: true })
watch(() => store.layers.heat, (on) => { if (heatLayer) { on ? map.addLayer(heatLayer) : map.removeLayer(heatLayer) } })
watch(() => store.layers.ham, (on) => { if (hamLayer) { on ? map.addLayer(hamLayer) : map.removeLayer(hamLayer) } })
watch(() => store.layers.events, (on) => { if (cluster) { on ? map.addLayer(cluster) : map.removeLayer(cluster) } })
watch(() => store.selectedId, flyToEvent)
watch(() => store.routePayload, buildRoute)
watch(() => store.city, () => { const [lat, lng] = store.cityCenter; map?.setView([lat, lng], 12) })

const legend = computed(() => Object.entries(SEV_COLOR))
</script>

<template>
  <div class="map-area">
    <div id="map" ref="mapEl"></div>
    <div class="layer-toggle">
      <label><input type="checkbox" v-model="store.layers.events" /> {{ $t('layers.events') }}</label>
      <label><input type="checkbox" v-model="store.layers.heat" /> {{ $t('layers.heat') }}</label>
      <label><input type="checkbox" v-model="store.layers.ham" /> {{ $t('layers.ham') }}</label>
      <div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">
        <span v-for="[k, c] in legend" :key="k" class="row" style="gap:3px">
          <span class="dot" :style="{ background: c }"></span>
          <span class="muted" style="font-size:11px">{{ $t('severity.' + k) }}</span>
        </span>
      </div>
    </div>
    <slot name="fab" />
  </div>
</template>
