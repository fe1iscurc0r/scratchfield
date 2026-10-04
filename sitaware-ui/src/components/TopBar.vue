<script setup lang="ts">
// F-08 首页/仪表盘要素：品牌 + 核心指标卡 + 城市选择器 + 语言切换 + 实时状态 + 快捷操作。
import { useSitaware } from '@/stores/sitaware'
import { setLang } from '@/i18n'
import { computed } from 'vue'

const store = useSitaware()
const cities = ['guangzhou', 'shenzhen', 'beijing', 'shanghai', 'chengdu']
const lang = computed(() => (store as any) && (window as any))

function toggleLang() {
  const cur = (window as any).__sitaware_locale || 'zh'
  const next = cur === 'zh' ? 'en' : 'zh'
  ;(window as any).__sitaware_locale = next
  setLang(next)
}
</script>

<template>
  <div class="topbar">
    <div class="brand">{{ $t('app.title') }} <small>{{ $t('app.subtitle') }}</small></div>

    <div class="metric-cards">
      <div class="metric">
        <div class="v">{{ store.metrics?.events_total ?? '—' }}</div>
        <div class="k">{{ $t('metrics.total') }}</div>
      </div>
      <div class="metric">
        <div class="v">{{ store.metrics?.events_today ?? '—' }}</div>
        <div class="k">{{ $t('metrics.today') }}</div>
      </div>
      <div class="metric">
        <div class="v" style="color:var(--crit)">{{ store.metrics?.high_risk_today ?? '—' }}</div>
        <div class="k">{{ $t('metrics.highRisk') }}</div>
      </div>
      <div class="metric">
        <div class="v" :class="'risk-' + (store.metrics?.risk_level ?? 'low')">{{ $t('severity.' + (store.metrics?.risk_level ?? 'low')) }}</div>
        <div class="k">{{ $t('metrics.riskLevel') }}</div>
      </div>
    </div>

    <div class="spacer"></div>

    <div class="row" style="gap:6px">
      <button class="ghost" @click="store.setTab('query')">💬 {{ $t('nav.query') }}</button>
      <button class="ghost" @click="store.setTab('route')">🧭 {{ $t('nav.route') }}</button>
      <button class="ghost" @click="store.setTab('alerts')">🔔 {{ $t('nav.alerts') }}</button>
    </div>

    <select :value="store.city" @change="store.setCity(($event.target as HTMLSelectElement).value)">
      <option v-for="c in cities" :key="c" :value="c">{{ $t('city.' + c) }}</option>
    </select>
    <button class="ghost" @click="toggleLang">🌐</button>
    <span class="row" style="gap:5px">
      <span class="live-dot" :class="{ off: !store.connected }"></span>
      <span class="muted" style="font-size:12px">{{ store.connected ? $t('status.online') : $t('status.offline') }}</span>
    </span>
  </div>
</template>
