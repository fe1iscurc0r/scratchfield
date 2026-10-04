<script setup lang="ts">
import type { FlowStep } from '@/composables/useResearchFlow'
/**
 * 科研工作流条（卷147）
 *
 * 把 ElnView / PapersView / DataView 从三个孤岛串成一条流水线：
 *   📚文献 → 🧪实验 → 📊数据 → 📈模型/报告
 *
 * 职责：
 *  - 高亮当前步骤（active prop）
 *  - 显示上下文徽章（正在引用的文献 / 待挂的图 / 聚焦的记录）
 *  - 点击步骤跳路由（携带已累积的 payload）
 *
 * 用法：在三个视图模板顶部放 `<ResearchFlowBar active="papers" />`。
 * payload 通过 useResearchFlow() 的 provide/inject 上下文跨视图延续，
 * 组件本身不负责 provide（由视图 provide，见各视图脚本）。
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useResearchFlow } from '@/composables/useResearchFlow'

const props = defineProps<{
  /** 当前所在步骤 */
  active: FlowStep
  /** 可选：当前视图内的聚焦对象描述（如「paper#42」），优先于上下文徽章 */
  badge?: string
}>()

const router = useRouter()
const flow = useResearchFlow()

const STEPS: Array<{ key: FlowStep, icon: string, label: string, route: string }> = [
  { key: 'papers', icon: '📚', label: '文献', route: '/papers' },
  { key: 'eln', icon: '🧪', label: '实验', route: '/eln' },
  { key: 'data', icon: '📊', label: '数据', route: '/data' },
  { key: 'model', icon: '📈', label: '模型/报告', route: '/eln' },
]

/** 上下文徽章：把待传递的 payload 显式展示出来，让用户知道"手上有什么" */
const ctxBadge = computed(() => {
  if (props.badge)
    return props.badge
  if (!flow)
    return ''
  if (flow.pendingCitation.value)
    return `正在引用: ${flow.pendingCitation.value}`
  if (flow.pendingAttachment.value)
    return `待挂图: ${flow.pendingAttachment.value}`
  if (flow.focusedRecordId.value)
    return `聚焦记录: ${flow.focusedRecordId.value}`
  return ''
})

function go(step: typeof STEPS[number]) {
  if (!flow)
    return
  flow.step.value = step.key
  if (props.active !== step.key)
    router.push(step.route)
}
</script>

<template>
  <div class="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2 flex flex-wrap items-center gap-2">
    <!-- 四步导航 -->
    <div class="flex items-center gap-1">
      <template v-for="(s, i) in STEPS" :key="s.key">
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors"
          :class="active === s.key
            ? 'bg-#4f8cff text-white'
            : 'text-white/60 hover:bg-white/10'"
          :title="`跳到${s.label}`"
          @click="go(s)"
        >
          <span>{{ s.icon }}</span>
          <span>{{ s.label }}</span>
        </button>
        <span v-if="i < STEPS.length - 1" class="text-white/20 text-xs select-none">›</span>
      </template>
    </div>

    <!-- 上下文徽章 -->
    <div v-if="ctxBadge" class="ml-auto flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-#4f8cff/15 text-#4f8cff border border-#4f8cff/30">
      <span class="w-1.5 h-1.5 rounded-full bg-#4f8cff" />
      <span class="font-mono">{{ ctxBadge }}</span>
    </div>
  </div>
</template>
