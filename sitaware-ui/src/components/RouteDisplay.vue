<script setup lang="ts">
// F-06 路径规划可视化：起点/终点（地址或坐标）→ 后端避风险规划 → 地图绘制主/替代/风险段。
import { reactive, ref } from 'vue'
import { useSitaware } from '@/stores/sitaware'
import { api } from '@/api/client'

const store = useSitaware()
const loading = ref(false)
const form = reactive({ start: '广州天河', end: '琶洲', avoid: true })

async function geocodeOrCoords(text: string): Promise<[number, number] | null> {
  const m = text.match(/(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)/)
  if (m) return [parseFloat(m[2]), parseFloat(m[1])] // [lat,lng]
  const r = await api.geocode({ text })
  if (r?.ok) return [r.lat, r.lng]
  return null
}

async function plan() {
  loading.value = true
  try {
    const s = await geocodeOrCoords(form.start)
    const e = await geocodeOrCoords(form.end)
    if (!s || !e) return
    await store.planRoute({
      start_lng: s[1], start_lat: s[0],
      end_lng: e[1], end_lat: e[0],
      avoid_risk: form.avoid, profile: 'foot',
    })
  } finally {
    loading.value = false
  }
}

const r = () => store.routePayload
function fmtDist(m: number | null): string {
  if (m == null) return '—'
  return m >= 1000 ? (m / 1000).toFixed(1) + ' km' : Math.round(m) + ' m'
}
function fmtDur(s: number | null): string {
  if (s == null) return '—'
  const min = Math.round(s / 60)
  return min >= 60 ? `${Math.floor(min / 60)}h${min % 60}m` : `${min}m`
}
</script>

<template>
  <div class="col" style="gap:10px">
    <strong>{{ $t('route.title') }}</strong>
    <input v-model="form.start" :placeholder="$t('route.start') + ' (地址/经纬度)'" />
    <input v-model="form.end" :placeholder="$t('route.end') + ' (地址/经纬度)'" />
    <label class="row" style="gap:6px">
      <input type="checkbox" v-model="form.avoid" /> {{ $t('route.avoid') }}
    </label>
    <button class="primary" @click="plan" :disabled="loading">{{ loading ? '…' : $t('route.plan') }}</button>

    <div v-if="r()" class="col" style="border:1px solid var(--border);border-radius:8px;padding:8px">
      <div class="row" style="gap:10px">
        <span>🛣 {{ fmtDist(r().primary.distance_m) }}</span>
        <span>⏱ {{ fmtDur(r().primary.duration_s) }}</span>
      </div>
      <div class="muted" style="font-size:12px">
        {{ $t('route.source') }}: {{ r().primary.source }}
        <span v-if="r().primary.source === 'fallback_line'"> · {{ $t('route.fallback') }}</span>
      </div>
      <div v-for="(w, i) in r().warnings" :key="i" class="badge sev-high" style="margin-top:4px;white-space:normal">{{ w }}</div>
      <div v-if="r().risk_segments.length" class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">
        <span class="badge sev-critical" v-for="(seg, i) in r().risk_segments" :key="i">{{ $t('route.risk') }}: {{ seg.title }}</span>
      </div>
      <div v-if="r().alternatives.length" class="muted" style="font-size:12px;margin-top:6px">{{ $t('route.alt') }}: {{ r().alternatives.length }}</div>
    </div>
  </div>
</template>
