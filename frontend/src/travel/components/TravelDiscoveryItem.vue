<script setup lang="ts">
import type { TravelDiscovery } from '@/travel/types'

defineProps<{
  discovery: TravelDiscovery
  clickable?: boolean
}>()
</script>

<template>
  <component
    :is="clickable ? 'a' : 'div'"
    :href="clickable ? discovery.url : undefined"
    :target="clickable ? '_blank' : undefined"
    class="flex items-start gap-2 px-2 py-1.5 rounded bg-white/3 text-xs no-underline"
    :class="clickable ? 'hover:bg-white/6 transition' : ''"
  >
    <span class="text-#d4af37 shrink-0">*</span>
    <div class="min-w-0">
      <div class="text-white/70 truncate">{{ discovery.title }}</div>
      <div class="text-white/30 truncate">{{ discovery.summary }}</div>
      <div v-if="discovery.tags.length" class="flex gap-1 mt-0.5">
        <span v-for="tag in discovery.tags" :key="tag" class="text-#d4af37/40 text-[10px]">#{{ tag }}</span>
      </div>
    </div>
  </component>
</template>
