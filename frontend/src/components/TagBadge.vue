<script setup lang="ts">
/**
 * AI 标签徽章（卷164 · 工单 C1/D2）——**通用组件**。
 *
 * 展示一条 AI 打标结果：`案由徽章 + 置信度小数`（如「合同纠纷 0.87」）。
 * 置信 < 阈值时显示黄色「待复核」样式，可点击触发复核弹层。
 *
 * 设计为**领域无关**：default 包（材料科研）将来的论文打标直接复用，
 * 只需传入不同的 `tag`（格式统一为 `键:值`）与 confidence。
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  /** 标签值，如「合同纠纷」。 */
  label: string
  /** 置信度（0–1）；省略则只显示标签（人工标签可传 1）。 */
  confidence?: number
  /** 低置信阈值（低于则显示「待复核」黄色样式）。 */
  threshold?: number
  /** 是否人工确认（显示「人工」角标，不看阈值）。 */
  human?: boolean
  /** 是否可点击（有待复核内容时置 true）。 */
  clickable?: boolean
}>(), {
  confidence: undefined,
  threshold: 0.6,
  human: false,
  clickable: false,
})

const emit = defineEmits<{ (e: 'review'): void }>()

/** 是否低置信（待复核）。人工确认项恒不算低置信。 */
const isLow = computed(
  () => !props.human && props.confidence !== undefined && props.confidence < props.threshold,
)

const confidenceText = computed(() =>
  props.confidence === undefined ? '' : props.confidence.toFixed(2),
)

function onClick() {
  if (props.clickable && isLow.value)
    emit('review')
}
</script>

<template>
  <span
    class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs whitespace-nowrap transition-colors"
    :class="[
      human
        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
        : isLow
          ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
          : 'bg-sky-500/15 text-sky-300 border border-sky-500/30',
      clickable && isLow ? 'cursor-pointer hover:bg-amber-500/25' : '',
    ]"
    :title="human
      ? `${label}（人工确认）`
      : isLow
        ? `${label} 置信 ${confidenceText}，低于 ${threshold}，待人工复核`
        : `${label} 置信 ${confidenceText}`"
    @click="onClick"
  >
    <span>{{ label }}</span>
    <span v-if="confidenceText" class="opacity-70 font-mono">{{ confidenceText }}</span>
    <span
      v-if="human"
      class="px-1 rounded-sm bg-emerald-500/25 text-[10px] leading-4"
    >人工</span>
    <span
      v-else-if="isLow"
      class="px-1 rounded-sm bg-amber-500/25 text-[10px] leading-4"
    >待复核</span>
  </span>
</template>
