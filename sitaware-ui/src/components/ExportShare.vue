<script setup lang="ts">
// F-07 数据导出与分享：GeoJSON / CSV / Markdown 报告下载 + 免登录只读分享链接。
import { ref } from 'vue'
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()
const copied = ref(false)

function download(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function exportGeoJSON() {
  const fc = { type: 'FeatureCollection', features: store.visibleEvents }
  download('sitaware-events.geojson', JSON.stringify(fc, null, 2), 'application/geo+json')
}
function exportCSV() {
  const rows = [['id', 'title', 'type', 'severity', 'source', 'lng', 'lat', 'reported_at', 'confidence']]
  for (const f of store.visibleEvents) {
    const p = f.properties
    rows.push([f.id, p.title, p.event_type, p.severity, p.source,
      f.geometry.coordinates?.[0], f.geometry.coordinates?.[1], p.reported_at, p.confidence])
  }
  const csv = rows.map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  download('sitaware-events.csv', '﻿' + csv, 'text/csv')
}
function exportMarkdown() {
  const m = store.metrics
  let md = `# 态势感知报告\n\n- 事件总数：${m?.events_total ?? '?'} · 今日：${m?.events_today ?? '?'} · 高危：${m?.high_risk_today ?? '?'}\n- 风险等级：${m?.risk_level ?? '?'}\n\n`
  md += `| 标题 | 类型 | 严重度 | 来源 | 坐标 | 时间 |\n|---|---|---|---|---|---|\n`
  for (const f of store.visibleEvents.slice(0, 100)) {
    const p = f.properties
    md += `| ${p.title} | ${p.event_type} | ${p.severity} | ${p.source} | ${f.geometry.coordinates} | ${p.reported_at} |\n`
  }
  download('sitaware-report.md', md, 'text/markdown')
}
async function shareLink() {
  const state = {
    city: store.city,
    f: store.filters,
    t: store.timeCursor,
    c: store.cityCenter,
  }
  const url = `${location.origin}${location.pathname}#view=${encodeURIComponent(JSON.stringify(state))}`
  try { await navigator.clipboard.writeText(url); copied.value = true; setTimeout(() => (copied.value = false), 1500) } catch { /* ignore */ }
}
</script>

<template>
  <div class="col" style="gap:10px">
    <strong>{{ $t('export.title') }}</strong>
    <button class="primary" @click="exportGeoJSON">{{ $t('export.geojson') }}</button>
    <button class="primary" @click="exportCSV">{{ $t('export.csv') }}</button>
    <button class="primary" @click="exportMarkdown">{{ $t('export.markdown') }}</button>
    <button class="ghost" @click="shareLink">{{ copied ? $t('export.copied') : $t('export.share') }}</button>
    <div class="muted" style="font-size:12px">{{ store.visibleEvents.length }} {{ $t('status.events') }}</div>
  </div>
</template>
