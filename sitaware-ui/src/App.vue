<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { useSitaware } from '@/stores/sitaware'
import TopBar from './components/TopBar.vue'
import EventPanel from './components/EventPanel.vue'
import MapCanvas from './components/MapCanvas.vue'
import TimeAxis from './components/TimeAxis.vue'
import EventDetail from './components/EventDetail.vue'
import AlertManager from './components/AlertManager.vue'
import NLQueryPanel from './components/NLQueryPanel.vue'
import RouteDisplay from './components/RouteDisplay.vue'
import ExportShare from './components/ExportShare.vue'

const store = useSitaware()
const TABS = [
  { key: 'alerts', label: 'nav.alerts' },
  { key: 'query', label: 'nav.query' },
  { key: 'route', label: 'nav.route' },
  { key: 'export', label: 'nav.export' },
]

const fab = reactive({ text: '' })
async function fabAsk() {
  const q = fab.text.trim()
  if (!q) return
  await store.ask(q)
  fab.text = ''
  store.setTab('query')
}

onMounted(async () => {
  await store.loadAll()
  store.startStream()
  // 处理分享链接（F-07）：#view=...
  const m = location.hash.match(/view=([^&]+)/)
  if (m) {
    try {
      const v = JSON.parse(decodeURIComponent(m[1]))
      if (v.city) store.setCity(v.city)
      if (v.f) Object.assign(store.filters, v.f)
      if (v.t) store.timeCursor = v.t
    } catch { /* ignore */ }
  }
})
</script>

<template>
  <div class="app-shell">
    <TopBar />

    <div class="left-panel">
      <EventPanel />
    </div>

    <MapCanvas>
      <template #fab>
        <div class="fab-query">
          <div class="query-input">
            <input v-model="fab.text" :placeholder="$t('query.placeholder')" @keyup.enter="fabAsk" />
            <button class="primary" @click="fabAsk">↑</button>
          </div>
        </div>
      </template>
    </MapCanvas>

    <div class="right-panel panel">
      <div class="tabs">
        <button
          v-for="t in TABS"
          :key="t.key"
          :class="{ active: store.activeTab === t.key }"
          @click="store.setTab(t.key)"
        >{{ $t(t.label) }}</button>
      </div>
      <div class="panel-body">
        <AlertManager v-if="store.activeTab === 'alerts'" />
        <NLQueryPanel v-else-if="store.activeTab === 'query'" />
        <RouteDisplay v-else-if="store.activeTab === 'route'" />
        <ExportShare v-else-if="store.activeTab === 'export'" />
      </div>
    </div>

    <TimeAxis />

    <EventDetail />
  </div>
</template>
