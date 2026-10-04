<!-- 簇图例（卷190-B5：从 MindView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
defineProps<{
  types: string[]
  counts: Record<string, number>
  focusType: string | null
  colorOf: (t: string) => string
}>()

const emit = defineEmits<{
  pick: [t: string]
}>()
</script>

<template>
  <div
    v-if="types.length > 0"
    class="absolute bottom-3 left-3 bg-[rgba(6,12,24,0.88)] border border-[rgba(50,90,160,0.3)] rounded-lg px-3 py-2 backdrop-blur-sm text-[10px] max-h-[45%] overflow-y-auto max-w-[190px]"
  >
    <div class="text-white/35 mb-1">
      簇（点击聚焦）
    </div>
    <div
      v-for="t in types"
      :key="t"
      class="flex items-center gap-1.5 my-0.5 cursor-pointer hover:bg-white/5 rounded px-1 -mx-1 transition"
      :class="{ 'bg-white/10': focusType === t }"
      @click="emit('pick', t)"
    >
      <span class="inline-block w-2.5 h-2.5 rounded-full shrink-0" :style="{ background: colorOf(t) }" />
      <span class="text-white/60 truncate">{{ t }}</span>
      <span class="text-white/30 ml-auto pl-2 shrink-0">{{ counts[t] || 0 }}</span>
    </div>
  </div>
</template>
