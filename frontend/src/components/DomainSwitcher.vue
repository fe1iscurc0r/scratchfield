<script setup lang="ts">
/**
 * 领域切换器（卷162 · 工单 B2）。
 *
 * 放在 PanelView 顶栏，用于在多个领域包之间切换。切换后：
 *  - 写入 localStorage（domainPacks.setActiveDomain 持久化）
 *  - ElnView 等消费 currentElnFields 的页面自动跟随新领域字段渲染
 *  - 领域专属路由已由 registerDomainRoutes() 在启动时注册好
 *
 * 零回归保证：只有一个领域包时**不渲染任何 DOM**（v-if），
 * 故 default 单包部署下 PanelView 页面与改造前完全一致。
 */
import { computed, onMounted } from 'vue'
import {
  activeDomain,
  currentPack,
  domainPacks,
  domainsError,
  fetchDomainPacks,
  setActiveDomain,
} from '@/utils/domainPacks'

/** 只有 ≥2 个领域包时才显示切换器 —— 保证 default 单包下零页面变化。 */
const visible = computed(() => domainPacks.value.length > 1)

function onChange(e: Event) {
  const name = (e.target as HTMLSelectElement).value
  setActiveDomain(name)
}

onMounted(() => {
  // PanelView 是首页，通常最先挂载；此处兜底拉取，路由注册那条链路失败也能显示。
  if (!domainPacks.value.length && !domainsError.value)
    fetchDomainPacks()
})
</script>

<template>
  <div v-if="visible" class="fixed top-3 right-4 z-40 flex items-center gap-2">
    <span class="text-xs text-white/40">领域</span>
    <select
      :value="activeDomain"
      class="px-2 py-1 rounded-lg bg-white/5 border border-white/10 text-white/80 text-xs outline-none cursor-pointer"
      :title="currentPack?.description || ''"
      @change="onChange"
    >
      <option v-for="p in domainPacks" :key="p.name" :value="p.name">
        {{ p.label }}
      </option>
    </select>
    <span v-if="currentPack" class="text-xs text-white/30">{{ currentPack.label }}</span>
  </div>
</template>
