<script setup lang="ts">
// F-05 自然语言查询面板：提问 → 后端 LLM/统计回答 → 可点击引用事件 + 地图动作 + 本地处理标识。
import { ref } from 'vue'
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()
const text = ref('')
const loading = ref(false)

async function ask() {
  const q = text.value.trim()
  if (!q) return
  loading.value = true
  try {
    await store.ask(q)
  } finally {
    loading.value = false
  }
}

function startVoice() {
  // Web Speech API（可选）
  const SR: any = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
  if (!SR) return
  const rec = new SR()
  rec.lang = 'zh-CN'
  rec.onresult = (e: any) => { text.value = e.results[0][0].transcript; ask() }
  rec.start()
}
function flyTo(feature: any) {
  if (!feature?.geometry?.coordinates) return
  store.select(feature.id)
}
</script>

<template>
  <div class="col" style="gap:10px">
    <strong>{{ $t('nav.query') }}</strong>
    <div class="query-input" style="border-radius:10px">
      <input v-model="text" :placeholder="$t('query.placeholder')" @keyup.enter="ask" />
      <button class="ghost" @click="startVoice" title="🎤">🎤</button>
      <button class="primary" @click="ask" :disabled="loading">{{ loading ? '…' : $t('query.ask') }}</button>
    </div>

    <div v-if="store.queryHistory.length === 0" class="muted">{{ $t('query.history') }}: —</div>
    <div v-for="(h, i) in store.queryHistory" :key="i" class="event-item">
      <div class="t">Q: {{ h.text }}</div>
      <div style="margin:6px 0">{{ h.res.answer }}</div>
      <div class="row" style="gap:6px;flex-wrap:wrap">
        <span v-if="!h.res.llm_source" class="badge sev-low">🔒 {{ $t('query.local') }}</span>
        <span v-else class="badge">☁️ {{ h.res.llm_source }}</span>
        <span v-if="h.res.risk_level" class="badge" :class="'sev-' + h.res.risk_level">{{ $t('metrics.riskLevel') }}: {{ $t('severity.' + h.res.risk_level) }}</span>
      </div>
      <div v-if="h.res.map_action" class="muted" style="font-size:12px;margin-top:4px">📍 {{ h.res.map_action.label }}</div>
      <div v-if="h.res.cited_events?.length" class="muted" style="font-size:12px;margin-top:4px">{{ $t('query.cited') }}:</div>
      <div class="row" style="gap:6px;flex-wrap:wrap;margin-top:4px">
        <span
          v-for="c in h.res.cited_events"
          :key="c.id"
          class="badge"
          style="cursor:pointer"
          @click="flyTo(c)"
        >{{ c.properties.title || c.id.slice(0, 8) }}</span>
      </div>
    </div>
  </div>
</template>
