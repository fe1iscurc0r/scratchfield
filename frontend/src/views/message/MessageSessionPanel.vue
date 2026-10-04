<!-- 对话历史面板（卷190-B3：从 MessageView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { formatRelativeTime } from '@/utils/session'

defineProps<{
  open: boolean
  sessions: Array<{
    sessionId: string
    createdAt: string
    lastActiveAt: string
    conversationRounds: number
    temporary: boolean
  }>
  loading: boolean
  currentSessionId: string | null
}>()

const emit = defineEmits<{
  close: []
  switch: [id: string]
  delete: [id: string]
}>()
</script>

<template>
  <Transition name="slide-up">
    <div v-if="open" class="session-panel">
      <div class="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <span class="text-white/70 text-sm font-bold">对话历史</span>
        <button
          class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
          @click="emit('close')"
        >
          关闭
        </button>
      </div>
      <div class="overflow-y-auto max-h-48">
        <div v-if="loading" class="text-white/40 text-xs text-center py-4">
          加载中...
        </div>
        <div v-else-if="sessions.length === 0" class="text-white/40 text-xs text-center py-4">
          暂无历史对话
        </div>
        <div
          v-for="s in sessions" :key="s.sessionId"
          class="session-item"
          :class="{ 'bg-white/10': s.sessionId === currentSessionId }"
          @click="emit('switch', s.sessionId)"
        >
          <div class="flex-1 min-w-0">
            <div class="text-white/80 text-sm truncate">
              {{ s.sessionId.slice(0, 8) }}...
            </div>
            <div class="text-white/40 text-xs">
              {{ formatRelativeTime(s.lastActiveAt) }} · {{ s.conversationRounds }} 轮对话
            </div>
          </div>
          <button
            class="text-white/30 hover:text-red-400 bg-transparent border-none cursor-pointer text-xs shrink-0 ml-2"
            title="删除"
            @click.stop="emit('delete', s.sessionId)"
          >
            x
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.session-panel {
  position: absolute;
  left: var(--nav-back-width);
  right: 0;
  bottom: 5rem;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  backdrop-filter: blur(12px);
  z-index: 10;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
