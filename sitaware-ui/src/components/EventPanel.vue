<script setup lang="ts">
// F-02 事件列表面板 + 筛选器。点击事件 → store.select（地图飞至并打开详情）。
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()

const TYPES = ['protest', 'accident', 'weather', 'signal', 'hazard', 'custom']
const SEVS = ['low', 'medium', 'high', 'critical']
const SRCS = ['news', 'rss', 'ham_radio', 'sensor', 'user', 'weather']

function fmtTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function reset() {
  store.filters.event_type = ''
  store.filters.severity = ''
  store.filters.source = ''
  store.filters.q = ''
  store.timeCursor = null
}
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <span>{{ $t('nav.events') }} ({{ store.visibleEvents.length }})</span>
      <button class="ghost" @click="reset">{{ $t('filters.reset') }}</button>
    </div>
    <div class="panel-body">
      <div class="col" style="margin-bottom:10px">
        <input v-model="store.filters.q" :placeholder="$t('filters.search')" />
        <div class="row" style="flex-wrap:wrap">
          <select v-model="store.filters.event_type">
            <option value="">{{ $t('filters.all') }} · {{ $t('filters.type') }}</option>
            <option v-for="t in TYPES" :key="t" :value="t">{{ $t('type.' + t) }}</option>
          </select>
          <select v-model="store.filters.severity">
            <option value="">{{ $t('filters.all') }} · {{ $t('filters.severity') }}</option>
            <option v-for="s in SEVS" :key="s" :value="s">{{ $t('severity.' + s) }}</option>
          </select>
          <select v-model="store.filters.source">
            <option value="">{{ $t('filters.all') }} · {{ $t('filters.source') }}</option>
            <option v-for="s in SRCS" :key="s" :value="s">{{ $t('source.' + s) }}</option>
          </select>
        </div>
      </div>

      <div v-if="store.visibleEvents.length === 0" class="muted">{{ $t('common.empty') }}</div>
      <div
        v-for="f in store.visibleEvents"
        :key="f.id"
        class="event-item"
        :class="{ active: f.id === store.selectedId }"
        @click="store.select(f.id)"
      >
        <div class="row" style="justify-content:space-between">
          <span class="t">{{ f.properties.title || '(无标题)' }}</span>
          <span class="badge" :class="'sev-' + f.properties.severity">{{ $t('severity.' + f.properties.severity) }}</span>
        </div>
        <div class="m">{{ $t('type.' + f.properties.event_type) }} · {{ $t('source.' + f.properties.source) }} · {{ fmtTime(f.properties.reported_at) }}</div>
      </div>
    </div>
  </div>
</template>
