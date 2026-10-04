<!-- 消息 Tab 栏（卷190-B3：从 MessageView.vue 纯搬移；原文件 normal/expanded 双份模板逐字相同，收敛为单组件双挂载） -->
<script setup lang="ts">
import type { ChatTab } from '@/utils/session'
import { ref } from 'vue'

const props = defineProps<{
  tabs: ChatTab[]
  activeTabId: string
  renamingTabId: string | null
  /** collapse = 常规容器内（显示"放大"按钮）；expand = 放大覆盖层内（显示"缩小"按钮） */
  variant: 'collapse' | 'expand'
}>()

const emit = defineEmits<{
  switch: [tab: ChatTab]
  startRename: [tab: ChatTab]
  closeTab: [tab: ChatTab]
  finishRename: [tab: ChatTab]
  toggleExpanded: []
}>()

const renameValue = defineModel<string>('renameValue', { required: true })

const renameInputRef = ref<HTMLInputElement | null>(null)
defineExpose({ renameInputRef })
</script>

<template>
  <div class="message-header px-1 pt-3 pb-2">
    <div class="tab-row">
      <button
        v-for="tab in props.tabs" :key="tab.id"
        class="tab-btn" :class="{ active: tab.id === activeTabId }"
        @click="emit('switch', tab)"
        @dblclick="emit('startRename', tab)"
      >
        <input
          v-if="renamingTabId === tab.id"
          ref="renameInputRef"
          v-model="renameValue"
          class="tab-rename-input"
          @blur="emit('finishRename', tab)"
          @keydown.enter="emit('finishRename', tab)"
          @click.stop
        >
        <template v-else>
          {{ tab.name }}
          <span v-if="tab.type === 'agent'" class="tab-close" @click.stop="emit('closeTab', tab)">×</span>
        </template>
        <span v-if="tab.unread && tab.id !== activeTabId" class="badge">{{ tab.unread }}</span>
      </button>
    </div>
    <div class="window-actions">
      <button
        v-if="variant === 'collapse'"
        class="window-btn"
        title="放大对话窗口"
        @click="emit('toggleExpanded')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 3h6v6" />
          <path d="M9 21H3v-6" />
          <path d="M21 3l-7 7" />
          <path d="M3 21l7-7" />
        </svg>
      </button>
      <button
        v-else
        class="window-btn"
        title="缩小对话窗口"
        @click="emit('toggleExpanded')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 10 21 3" />
          <path d="M21 10V3h-7" />
          <path d="M3 14l7 7" />
          <path d="M3 21h7v-7" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.message-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tab-row {
  display: flex;
  gap: 0.25rem;
  flex: 1;
  min-width: 0;
}

.window-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}

.window-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  transition: all 0.2s ease;
}

.window-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.95);
  border-color: rgba(255, 255, 255, 0.22);
}

/* ── Tab 栏（与 ConfigView 完全一致） ── */
.tab-btn {
  flex: 1;
  position: relative;
  padding: 0.5rem 0;
  font-size: 0.875rem;
  font-weight: 600;
  text-align: center;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
}

.tab-btn.active {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.9);
}

.tab-close {
  font-size: 0.7rem;
  opacity: 0;
  margin-left: 2px;
  transition: opacity 0.15s;
}

.tab-btn:hover .tab-close {
  opacity: 0.6;
}

.tab-close:hover {
  opacity: 1 !important;
  color: #e74c3c;
}

.tab-rename-input {
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.4);
  color: white;
  outline: none;
  width: 60px;
  font-size: inherit;
  font-weight: inherit;
  text-align: center;
}

.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #e74c3c;
  color: white;
  font-size: 10px;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
