<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  title?: string
  subtitle?: string
  icon?: string
  disabled?: boolean
  size?: 'lg' | 'md'
}>(), { size: 'lg' })

// md：紧凑尺寸，字号与右侧图标留位同步缩小，用于需要缩短的按钮行
const md = computed(() => props.size === 'md')
</script>

<template>
  <button
    class="border-none text-black shadow bg-white bg-op-90 backdrop-blur-md transition relative"
    :disabled="disabled" :class="disabled ? 'brightness-60' : 'hover:brightness-105 hover:bg-op-100'"
  >
    <img v-if="icon" :src="icon" class="absolute top-1/2 -translate-y-1/2" :class="md ? 'w-12 right-2 pl-1' : 'w-16 right-4 pl-2'">
    <div class="flex font-bold font-serif lh-none" :class="md ? 'text-2xl' : 'text-3xl'">
      <slot>
        <div class="flex flex-col gap-2 justify-center" :class="md ? 'px-2 py-2.5 pr-4em' : 'px-2 py-4 pr-5em'">
          <div class="whitespace-nowrap" v-html="title" />
          <div v-if="subtitle" class="text-base c-gray-800 op-40 font-sans lh-none">
            {{ subtitle }}
          </div>
        </div>
      </slot>
    </div>
  </button>
</template>
