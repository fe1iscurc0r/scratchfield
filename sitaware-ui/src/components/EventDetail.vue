<script setup lang="ts">
// F-02 事件详情弹窗：完整字段 + 原始链接 + 标记已验证/不可信。
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()

function fmt(s: string): string {
  if (!s) return '—'
  return new Date(s).toLocaleString()
}
</script>

<template>
  <div v-if="store.selectedEvent" class="modal-mask" @click.self="store.select(null)">
    <div class="modal">
      <div class="row" style="justify-content:space-between">
        <h3>{{ store.selectedEvent.properties.title || '(无标题)' }}</h3>
        <button class="ghost" @click="store.select(null)">✕</button>
      </div>
      <div class="row" style="gap:8px;margin-bottom:8px">
        <span class="badge" :class="'sev-' + store.selectedEvent.properties.severity">{{ $t('severity.' + store.selectedEvent.properties.severity) }}</span>
        <span class="muted">{{ $t('type.' + store.selectedEvent.properties.event_type) }}</span>
        <span class="muted">{{ $t('source.' + store.selectedEvent.properties.source) }}</span>
        <span class="muted">conf {{ store.selectedEvent.properties.confidence }}</span>
      </div>
      <p>{{ store.selectedEvent.properties.description }}</p>
      <div class="muted" style="font-size:12px">
        <div>📍 {{ store.selectedEvent.geometry.coordinates }}</div>
        <div>🕒 {{ fmt(store.selectedEvent.properties.reported_at) }}</div>
        <div>⏰ {{ fmt(store.selectedEvent.properties.expires_at) }}</div>
        <div>🏷 {{ (store.selectedEvent.properties.tags || []).join(', ') }}</div>
        <div v-if="store.selectedEvent.properties.llm_summary">🤖 {{ store.selectedEvent.properties.llm_summary }}</div>
      </div>
      <div style="margin-top:8px" v-if="store.selectedEvent.properties.raw_refs?.length">
        <div class="muted" style="font-size:12px">{{ $t('event.rawRefs') }}:</div>
        <a v-for="r in store.selectedEvent.properties.raw_refs" :key="r" :href="r" target="_blank" style="display:block;font-size:12px;word-break:break-all">{{ r }}</a>
      </div>
      <div class="row" style="margin-top:12px;gap:8px">
        <button class="primary" @click="store.selectedEvent.properties.is_verified = true">{{ $t('event.verify') }}</button>
        <button class="danger" @click="store.selectedEvent.properties.is_verified = false">{{ $t('event.untrust') }}</button>
        <button class="ghost" @click="store.select(null)">{{ $t('common.close') }}</button>
      </div>
    </div>
  </div>
</template>
