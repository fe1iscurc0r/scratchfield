<script setup lang="ts">
// F-03 时间轴与历史回放：密度直方图 + 滑块（仅显示该时刻之前事件）+ 播放。
import { computed, ref, onBeforeUnmount } from 'vue'
import { useSitaware } from '@/stores/sitaware'

const store = useSitaware()
const playing = ref(false)
const idx = ref<number>(0)
let timer: any = null

const N = 60

const bounds = computed(() => {
  const ts = store.events.map((e) => new Date((e.properties.reported_at as string) || 0).getTime()).filter((t) => !isNaN(t))
  if (!ts.length) return null
  return { min: Math.min(...ts), max: Math.max(...ts) }
})

const density = computed<number[]>(() => {
  const b = bounds.value
  if (!b) return []
  const out = new Array(N).fill(0)
  const span = Math.max(1, b.max - b.min)
  for (const e of store.events) {
    const t = new Date((e.properties.reported_at as string) || 0).getTime()
    if (isNaN(t)) continue
    const i = Math.min(N - 1, Math.floor(((t - b.min) / span) * (N - 1)))
    out[i]++
  }
  return out
})
const maxDensity = computed(() => Math.max(1, ...density.value))

const cursorTs = computed(() => {
  const b = bounds.value
  if (!b) return null
  if (idx.value >= N - 1) return null
  return b.min + (idx.value / (N - 1)) * (b.max - b.min)
})

function onSlide() {
  store.timeCursor = cursorTs.value
}
function togglePlay() {
  playing.value = !playing.value
  if (playing.value) {
    if (idx.value >= N - 1) idx.value = 0
    timer = setInterval(() => {
      if (idx.value >= N - 1) { playing.value = false; clearInterval(timer); return }
      idx.value++
      store.timeCursor = cursorTs.value
    }, 250)
  } else if (timer) {
    clearInterval(timer)
  }
}
function reset() {
  idx.value = N - 1
  store.timeCursor = null
  playing.value = false
  if (timer) clearInterval(timer)
}
onBeforeUnmount(() => timer && clearInterval(timer))

const label = computed(() => {
  const t = cursorTs.value
  return t ? new Date(t).toLocaleString() : $t('time.all')
})
</script>

<template>
  <div class="timebar panel" style="border-top:1px solid var(--border)">
    <div class="row" style="padding:8px 12px;gap:12px;width:100%">
      <button class="ghost" @click="togglePlay">{{ playing ? $t('time.pause') : $t('time.play') }}</button>
      <button class="ghost" @click="reset">{{ $t('time.all') }}</button>
      <div class="muted" style="font-size:12px;min-width:150px">{{ label }}</div>
      <div style="flex:1;display:flex;align-items:flex-end;gap:1px;height:34px">
        <div
          v-for="(d, i) in density"
          :key="i"
          :style="{ flex: 1, height: (d / maxDensity * 100) + '%', background: i <= idx ? 'var(--accent)' : 'var(--border)', borderRadius: '2px 2px 0 0' }"
          :title="d + ''"
        ></div>
      </div>
      <input type="range" min="0" :max="N - 1" v-model.number="idx" @input="onSlide" style="width:160px" />
    </div>
  </div>
</template>
