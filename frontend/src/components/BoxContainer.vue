<script setup lang="ts">
import ScrollPanel from 'primevue/scrollpanel'
import { useTemplateRef } from 'vue'
import back from '@/assets/icons/back.png'
import { useParallax } from '@/composables/useParallax'

const _props = withDefaults(defineProps<{ parallax?: boolean, boxClass?: string, noScroll?: boolean, hideBack?: boolean }>(), { parallax: true, boxClass: 'w-3/5', noScroll: false, hideBack: false })
const { transform: boxTransform } = useParallax({ rotateX: 3, rotateY: 3, translateX: 12, translateY: 8, invertRotate: true })

const scrollPanelRef = useTemplateRef<{
  scrollTop: (scrollTop: number) => void
}>('scrollPanelRef')

const boxRef = useTemplateRef<HTMLElement>('boxRef')

defineExpose({
  scrollToBottom() {
    scrollPanelRef.value?.scrollTop(Infinity)
  },
  // 距离底部不足阈值像素视为「锚在底部」——流式输出时供父组件决定是否跟随滚动。
  // 找不到滚动容器时返回 true（保持旧的强制滚动行为）。
  isNearBottom(threshold = 96): boolean {
    const content = boxRef.value?.querySelector<HTMLElement>('.p-scrollpanel-content')
    if (!content)
      return true
    return content.scrollHeight - content.scrollTop - content.clientHeight <= threshold
  },
})
</script>

<template>
  <div
    ref="boxRef"
    class="flex min-h-0"
    :class="{ 'will-change-transform': parallax }"
    :style="parallax ? { transform: boxTransform } : undefined"
  >
    <div v-if="!hideBack" class="back-btn flex items-center cursor-pointer shrink-0 mr-3" @click="$router.back">
      <img :src="back" class="w-[var(--nav-back-width)]" alt="">
    </div>
    <div class="box flex flex-col min-h-0 min-w-0 overflow-hidden" :class="boxClass">
      <!-- header slot：固定在滚动区域上方，不随内容滚动 -->
      <slot name="header" />
      <template v-if="noScroll">
        <div class="p-4 w-full flex flex-col min-h-0">
          <slot />
        </div>
      </template>
      <ScrollPanel
        v-else
        ref="scrollPanelRef"
        class="size-full"
        :pt="{
          barY: {
            class: 'w-2! rounded! bg-#373737! transition!',
          },
        }"
      >
        <div class="p-4 w-full min-w-0 overflow-hidden">
          <slot />
        </div>
      </ScrollPanel>
    </div>
  </div>
</template>

<style scoped>
.back-btn {
  transition: filter 0.2s ease;
}
.back-btn:hover {
  filter: brightness(1.35);
}
::-webkit-scrollbar {
  background-color: transparent;
  width: 6px;
}
::-webkit-scrollbar-thumb {
  background-color: #fff3;
  border-radius: 3px;
  height: 20%;
}
</style>
