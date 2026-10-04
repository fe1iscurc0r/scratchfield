<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  name: string
  description?: string
  layout?: 'row' | 'column'
  /** 卷181-B：搜索额外命中词（用户会搜但 label 里没有的词，如「推送」之于通知项） */
  searchKeys?: string[]
}>(), {
  layout: 'row',
  searchKeys: () => [],
})

// data-search-text：设置内搜索的匹配源（小写拼接；DOM 层过滤，零侵入既有 30+ 个 ConfigItem 调用点）
const searchText = computed(() =>
  [props.name, props.description ?? '', ...props.searchKeys].join(' ').toLowerCase(),
)
</script>

<template>
  <label
    :class="layout === 'row' ? 'grid grid-cols-2' : 'flex flex-col'"
    data-config-item
    :data-search-text="searchText"
  >
    <div class="flex flex-col justify-center gap-1">
      <div class="font-bold">{{ name }}</div>
      <div v-if="description" class="text-sm text-gray-500">{{ description }}</div>
    </div>
    <div class="flex flex-col justify-center">
      <slot />
    </div>
  </label>
</template>
