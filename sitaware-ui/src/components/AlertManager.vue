<script setup lang="ts">
// F-04 告警管理：规则 CRUD + 浏览器通知授权 + 提示音开关。
import { reactive, ref } from 'vue'
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()
const TYPES = ['protest', 'accident', 'weather', 'signal', 'hazard', 'custom']
const SEVS = ['low', 'medium', 'high', 'critical']
const notifPerm = ref<string>(typeof Notification !== 'undefined' ? Notification.permission : 'denied')

const form = reactive({
  name: '',
  center_lng: store.cityCenter[1],
  center_lat: store.cityCenter[0],
  radius_km: 2,
  min_severity: 'high' as const,
  event_types: [] as string[],
})

async function create() {
  await store.createAlert({
    name: form.name || '未命名规则',
    center_lng: Number(form.center_lng),
    center_lat: Number(form.center_lat),
    radius_km: Number(form.radius_km),
    min_severity: form.min_severity,
    event_types: form.event_types,
  })
  form.name = ''
}
function requestNotif() {
  if (typeof Notification === 'undefined') return
  Notification.requestPermission().then((p) => { notifPerm.value = p })
}
</script>

<template>
  <div class="col" style="gap:10px">
    <div class="row" style="justify-content:space-between">
      <strong>{{ $t('alert.title') }}</strong>
      <span class="row" style="gap:6px">
        <button class="ghost" @click="requestNotif">🔔 {{ notifPerm }}</button>
        <button class="ghost" :class="{ primary: store.soundOn }" @click="store.soundOn = !store.soundOn">🔊</button>
      </span>
    </div>

    <div class="col" style="border:1px solid var(--border);border-radius:8px;padding:8px">
      <input v-model="form.name" :placeholder="$t('alert.name')" />
      <div class="row">
        <input v-model.number="form.center_lng" type="number" step="0.0001" style="width:50%" />
        <input v-model.number="form.center_lat" type="number" step="0.0001" style="width:50%" />
      </div>
      <div class="row">
        <span class="muted" style="font-size:12px">{{ $t('alert.area') }}</span>
        <input v-model.number="form.radius_km" type="number" step="0.5" style="width:80px" />
        <span class="muted" style="font-size:12px">km</span>
      </div>
      <select v-model="form.min_severity">
        <option v-for="s in SEVS" :key="s" :value="s">{{ $t('severity.' + s) }}</option>
      </select>
      <div class="row" style="flex-wrap:wrap;gap:4px">
        <label v-for="t in TYPES" :key="t" class="badge" style="cursor:pointer">
          <input type="checkbox" :value="t" v-model="form.event_types" /> {{ $t('type.' + t) }}
        </label>
      </div>
      <button class="primary" @click="create">{{ $t('alert.create') }}</button>
    </div>

    <div v-if="store.alerts.length === 0" class="muted">{{ $t('alert.none') }}</div>
    <div v-for="a in store.alerts" :key="a.id" class="event-item">
      <div class="row" style="justify-content:space-between">
        <span class="t">{{ a.name }}</span>
        <button class="danger" @click="store.deleteAlert(a.id)">{{ $t('alert.delete') }}</button>
      </div>
      <div class="m">
        {{ a.center_lng }}, {{ a.center_lat }} · R={{ a.radius_km }}km ·
        ≥{{ $t('severity.' + a.min_severity) }} ·
        {{ (a.event_types || []).map((t) => $t('type.' + t)).join('/') || $t('filters.all') }}
      </div>
    </div>
  </div>
</template>
