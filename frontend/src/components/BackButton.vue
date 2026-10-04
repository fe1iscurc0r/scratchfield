<script setup lang="ts">
/**
 * 页头「返回」按钮
 *
 * 供无 BoxContainer 侧边箭头的独立面板页（ELN / 语音 ELN / 数据工具台 / 电台等）统一使用，
 * 样式沿用 ElnView 最初的那版页头返回按钮。
 *
 * 语义：优先回退历史上一条；若当前是本次会话的首个条目（冷启动深链直达），
 * history.state.back 为空，此时 back() 会空转甚至退出应用，故兜底跳首页。
 */
import { useRouter } from 'vue-router'

const props = withDefaults(defineProps<{ label?: string, homeTo?: string }>(), {
  label: '返回',
  homeTo: '/',
})

const router = useRouter()

function goBack() {
  const state = window.history.state as { back?: string | null } | null
  if (state?.back)
    router.back()
  else
    router.push(props.homeTo)
}
</script>

<template>
  <button
    type="button"
    class="shrink-0 whitespace-nowrap px-3 py-2 rounded-lg bg-white/5 text-white/60 text-sm hover:bg-white/10 hover:text-white/90 transition-colors flex items-center gap-1.5"
    :title="props.label"
    @click="goBack"
  >
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5" /><path d="M12 19l-7-7 7-7" /></svg>
    {{ props.label }}
  </button>
</template>
