<!-- 节点信息面板（卷190-B5：从 MindView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
defineProps<{
  node: {
    id: string
    type: string
    weight: number
    outCount: number
    inCount: number
    relations: string[]
  } | null | undefined
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <div
    v-if="node"
    class="absolute top-3 right-3 bg-[rgba(6,12,24,0.92)] border border-[rgba(50,90,160,0.4)] rounded-lg px-4 py-3 backdrop-blur-sm text-[11px] min-w-[200px] max-w-[300px]"
  >
    <div class="flex justify-between items-start">
      <h4 class="text-[#5580bb] text-[13px] font-bold">
        {{ node.id }}
      </h4>
      <button class="text-white/30 hover:text-white/60 text-xs ml-2" @click="emit('close')">
        ✕
      </button>
    </div>
    <div class="mt-1 text-[#6688aa]">
      Type: <span class="text-[#aaccff]">{{ node.type }}</span>
    </div>
    <div class="text-[#6688aa]">
      Weight: <span class="text-[#7bf] text-sm">{{ node.weight }}</span>
    </div>
    <div class="text-[#6688aa]">
      Out: <span class="text-[#aaccff]">{{ node.outCount }}</span>
      &middot; In: <span class="text-[#aaccff]">{{ node.inCount }}</span>
    </div>
    <hr class="border-[#152030] my-1.5">
    <div class="max-h-[150px] overflow-y-auto text-[9px] text-[#6688aa]">
      <div v-for="(r, i) in node.relations" :key="i" class="my-0.5">
        {{ r }}
      </div>
    </div>
  </div>
</template>
