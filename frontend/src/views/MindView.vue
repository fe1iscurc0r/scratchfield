<script setup lang="ts">
import type { NodeInfo, RendererApi } from './mind/renderer'
import type { GraphSummary } from '@/api/core'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import { useMindChat } from './mind/composables/useMindChat'
import { useMindData } from './mind/composables/useMindData'
import MindHelpDialog from './mind/MindHelpDialog.vue'
import MindLegend from './mind/MindLegend.vue'
import MindNodeInfo from './mind/MindNodeInfo.vue'
import { createMindRenderer } from './mind/renderer'

// ── 引擎（渲染细节全在 mind/renderer.ts）──
const canvasRef = ref<HTMLCanvasElement>()
const graphSummary = ref<GraphSummary | null>(null)
const rendererRef = ref<RendererApi | null>(null)

const showInfo = ref(false)
const infoNode = ref<NodeInfo>()
const helpVisible = ref(false)

// ── 数据域 ──
const {
  loading,
  errorMsg,
  searchQuery,
  nodeCount,
  quintupleCount,
  totalQuintuples,
  loadData,
  search,
} = useMindData({ renderer: rendererRef, graphSummary })

// ── 图例 / 分区概览（引擎通过回调推送）──
const legendTypes = ref<string[]>([])
const typeCounts = ref<Record<string, number>>({})
const focusTypeRef = ref<string | null>(null)
const sectorCount = ref(0)

function onNodeCountChange(_count: number, _quints: number, sectors: number, types: string[], counts: Record<string, number>) {
  legendTypes.value = types
  typeCounts.value = counts
  sectorCount.value = sectors
}

/** 引擎内部改动焦点（点扇区标题/点节点）→ 同步到图例高亮 */
function syncFocusFromCanvas(t: string | null) {
  if (focusTypeRef.value !== t)
    focusTypeRef.value = t
}

function onSelect(info: NodeInfo | null) {
  infoNode.value = info ?? undefined
  showInfo.value = !!info
  if (info)
    syncFocusFromCanvas(info.type)
}

rendererRef.value = createMindRenderer({
  canvasRef,
  graphSummary,
  onNodeCountChange,
  onSelect,
  onFocusChange: (t: string | null) => syncFocusFromCanvas(t),
})

const renderer = rendererRef.value

// ── 聊天探索域 ──
const { chatMode, chatInput, chatQuery } = useMindChat({
  searchQuery,
  runSearch: search,
  focusTopByWeight: () => renderer.focusTopByWeight(),
  syncFocus: (t) => {
    renderer.setFocusType(t)
    syncFocusFromCanvas(t)
  },
})

// 图例点击聚焦：写引擎 + 本地镜像
function pickType(t: string) {
  const next = focusTypeRef.value === t ? null : t
  renderer.setFocusType(next)
  focusTypeRef.value = next
}

function closeInfo() {
  showInfo.value = false
  renderer.setFocusType(null)
  focusTypeRef.value = null
}

// LOD 当前档位文案
const lodLabel = computed(() => {
  if (renderer.isNearView())
    return '近景 · 1-hop 邻域'
  if (focusTypeRef.value)
    return `中景 · ${focusTypeRef.value}`
  return '远景 · hub 骨架'
})

// n>150 时提示已切 BH；否则提示精确模式
const hubThresholdHint = computed(() => {
  if (nodeCount.value === 0)
    return ''
  return nodeCount.value > 150
    ? `BH 四叉树 (n=${nodeCount.value})`
    : `精确 O(n²) (n=${nodeCount.value})`
})

onMounted(async () => {
  renderer.setup()
  await loadData()
  if (!errorMsg.value)
    renderer.start()
})

onUnmounted(() => {
  renderer.dispose()
})

// 数据加载完成后重启动画
watch(loading, (isLoading) => {
  if (!isLoading && !errorMsg.value && nodeCount.value > 0)
    renderer.start()
})
</script>

<template>
  <BoxContainer class="text-sm" no-scroll>
    <div class="text-white flex flex-col flex-1 min-h-0">
      <!-- Header -->
      <div class="flex items-center gap-3 mb-3 shrink-0">
        <div class="mind-header-main">
          <h2 class="text-lg font-bold">
            记忆云海
          </h2>
          <button
            type="button"
            class="mind-help-btn"
            aria-label="查看记忆云海说明"
            title="查看记忆云海说明"
            @click="helpVisible = true"
          >
            ?
          </button>
        </div>
        <div class="flex-1 flex items-center gap-2">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索关键词..."
            class="flex-1 bg-white/10 border border-white/20 rounded px-3 py-1.5 text-sm text-white placeholder-white/40 outline-none focus:border-white/40"
            @keyup.enter="search"
          >
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="search"
          >
            搜索
          </button>
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="searchQuery = ''; loadData()"
          >
            刷新
          </button>
        </div>
      </div>

      <!-- 双模式（AGENTiGraph）：聊天框直连图谱——说一句话就聚焦子图 -->
      <div class="flex items-center gap-2 mb-2 shrink-0">
        <button
          class="px-2.5 py-1 rounded text-xs transition shrink-0"
          :class="chatMode ? 'bg-[#2a4a7a] text-white' : 'bg-white/10 hover:bg-white/20 text-white/70'"
          :title="chatMode ? '关闭聊天探索模式' : '切到聊天探索模式：用自然语言直接驱动图谱'"
          @click="chatMode = !chatMode"
        >
          {{ chatMode ? '💬 聊天探索' : '🔍 仅搜索' }}
        </button>
        <input
          v-model="chatInput"
          type="text"
          :placeholder="chatMode ? '比如：看看木质素相关记忆' : '搜索关键词...'"
          class="flex-1 bg-white/10 border border-white/20 rounded px-3 py-1.5 text-xs text-white placeholder-white/40 outline-none focus:border-white/40"
          @keyup.enter="chatMode ? chatQuery() : search()"
        >
        <button
          class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-xs transition shrink-0"
          @click="chatMode ? chatQuery() : search()"
        >
          {{ chatMode ? '问一句' : '搜索' }}
        </button>
      </div>

      <!-- Stats -->
      <div class="flex gap-4 text-xs text-white/50 mb-2 shrink-0 items-center flex-wrap">
        <span>五元组: {{ quintupleCount }}<span v-if="totalQuintuples > quintupleCount" class="text-white/30"> / {{ totalQuintuples }}</span></span>
        <span>实体: {{ nodeCount }}</span>
        <span v-if="sectorCount > 0">分区: {{ sectorCount }}</span>
        <span class="text-[#7bf]">{{ lodLabel }}</span>
        <span v-if="hubThresholdHint" class="text-white/30">{{ hubThresholdHint }}</span>
      </div>

      <!-- 3D Canvas：在限定高度内占满剩余空间 -->
      <div class="flex-1 relative min-h-[360px] rounded-lg overflow-hidden">
        <!-- Loading overlay -->
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-[#030810] z-10">
          <span class="text-[#3366aa] text-base tracking-widest">Loading...</span>
        </div>
        <!-- Error -->
        <div v-else-if="errorMsg" class="absolute inset-0 flex items-center justify-center bg-[#030810]">
          <span class="text-red-400">{{ errorMsg }}</span>
        </div>
        <!-- Empty state -->
        <div
          v-else-if="nodeCount === 0"
          class="absolute inset-0 flex flex-col items-center justify-center bg-[#030810] text-white/40"
        >
          <p>暂无五元组数据</p>
          <p class="text-xs mt-1">
            请先进行对话以生成知识图谱，或前往「角色连接」启用 GRAG
          </p>
        </div>

        <canvas ref="canvasRef" class="w-full h-full" style="cursor: grab" />

        <!-- Legend overlay -->
        <MindLegend
          v-if="!loading"
          :types="legendTypes"
          :counts="typeCounts"
          :focus-type="focusTypeRef"
          :color-of="renderer.colorOf"
          @pick="pickType"
        />

        <!-- Node info panel -->
        <MindNodeInfo
          v-if="showInfo"
          :node="infoNode"
          @close="closeInfo"
        />
      </div>

      <MindHelpDialog v-model:visible="helpVisible" />
    </div>
  </BoxContainer>
</template>

<style scoped>
.mind-header-main {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-shrink: 0;
}

.mind-help-btn {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.28);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(212, 175, 55, 0.88);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.mind-help-btn:hover {
  border-color: rgba(212, 175, 55, 0.52);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(248, 222, 159, 0.96);
}
</style>
