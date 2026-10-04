<!-- 输入 dock（卷190-B3：从 MessageView.vue 纯搬移，template+style 同进退）。
     composerRef/fileInput 通过 defineExpose 暴露给壳（resizeComposer / triggerUpload 需触达）。 -->
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

defineProps<{
  activeTabId: string
  activeTabName: string
  showHistory: boolean
  isRecording: boolean
  ttsEnabled: boolean
  sendingTravelInstruction: boolean
  hasActiveTravel: boolean
  voiceRealtimeEnabled: boolean
  isExpanded: boolean
  expandedInputStyle: Record<string, string>
}>()

const emit = defineEmits<{
  send: []
  newSession: []
  toggleHistory: []
  voiceToggle: []
  ttsToggle: []
  upload: []
  travelInstruction: []
  fileChange: [e: Event]
}>()

const input = defineModel<string>({ default: '' })

const composerRef = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const inputDockRef = ref<HTMLElement | null>(null)

// 输入框自适应高度（纯 DOM 操作，dock 自治——壳不再需要触达 composerRef 做这件事）
function resizeComposer() {
  if (!composerRef.value) {
    return
  }
  composerRef.value.style.height = '0px'
  const nextHeight = Math.min(Math.max(composerRef.value.scrollHeight, 44), 160)
  composerRef.value.style.height = `${nextHeight}px`
}

watch(input, () => {
  nextTick(resizeComposer)
})

defineExpose({ composerRef, fileInput, inputDockRef, resizeComposer })

function isImeComposing(event: KeyboardEvent) {
  return event.isComposing || (event as any).keyCode === 229
}

function handleComposerEnter(event: KeyboardEvent) {
  if (isImeComposing(event) || event.shiftKey) {
    return
  }
  event.preventDefault()
  emit('send')
}
</script>

<template>
  <div
    ref="inputDockRef"
    :class="isExpanded ? 'expanded-input-dock' : 'mx-[var(--nav-back-width)]'"
    :style="isExpanded ? expandedInputStyle : undefined"
  >
    <div class="box flex items-center gap-2 min-w-0">
      <button
        v-if="activeTabId === 'lumo'"
        class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
        title="新建对话"
        @click="emit('newSession')"
      >
        +
      </button>
      <button
        v-if="activeTabId === 'lumo'"
        class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
        :class="{ 'text-white!': showHistory }"
        title="对话历史"
        @click="emit('toggleHistory')"
      >
        H
      </button>
      <span class="input-prefix shrink-0">&gt;</span>
      <textarea
        ref="composerRef"
        v-model="input"
        rows="1"
        class="composer-textarea flex-1 min-w-0 text-white bg-transparent border-none outline-none"
        :placeholder="activeTabId === 'lumo' ? 'Type a message...' : `发送给 ${activeTabName}...`"
        @keydown.enter.exact="handleComposerEnter"
        @input="resizeComposer"
      />
      <button
        v-if="voiceRealtimeEnabled"
        class="input-icon-btn shrink-0"
        :class="{ recording: isRecording }"
        :title="isRecording ? '停止录音' : '语音输入'"
        @click="emit('voiceToggle')"
      >
        <svg v-if="!isRecording" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" x2="12" y1="19" y2="22" /></svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
      </button>
      <button
        class="input-icon-btn shrink-0"
        :title="ttsEnabled ? '关闭语音播报' : '开启语音播报'"
        @click="emit('ttsToggle')"
      >
        <svg v-if="ttsEnabled" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.54 8.46a5 5 0 0 1 0 7.07" /></svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><line x1="22" y1="9" x2="16" y2="15" /><line x1="16" y1="9" x2="22" y2="15" /></svg>
      </button>
      <button
        class="input-icon-btn shrink-0"
        title="上传文件 (Word/Excel/文本)"
        @click="emit('upload')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M12 18v-6" /><path d="m9 15 3-3 3 3" /></svg>
      </button>
      <input
        ref="fileInput"
        type="file"
        accept=".docx,.xlsx,.txt,.csv,.md,.pdf,.png,.jpg,.jpeg"
        class="hidden"
        @change="emit('fileChange', $event)"
      >
      <button
        v-if="hasActiveTravel"
        class="input-icon-btn shrink-0"
        :disabled="!input?.trim() || sendingTravelInstruction"
        :title="sendingTravelInstruction ? '投喂中' : '将当前输入追加为探索指令'"
        @click="emit('travelInstruction')"
      >
        <span class="text-[11px] font-semibold">
          {{ sendingTravelInstruction ? '...' : '探' }}
        </span>
      </button>
      <button
        class="send-btn shrink-0"
        :disabled="!input?.trim()"
        title="发送消息"
        @click="emit('send')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 2 11 13" />
          <path d="m22 2-7 20-4-9-9-4Z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.expanded-input-dock {
  position: fixed;
  z-index: 81;
}

.composer-textarea {
  min-height: 44px;
  max-height: 160px;
  padding: 10px 0;
  line-height: 24px;
  resize: none;
  overflow-y: auto;
}

.composer-textarea::placeholder {
  color: rgba(255, 255, 255, 0.45);
}

.input-prefix {
  color: rgba(255, 255, 255, 0.42);
  font-size: 1rem;
  line-height: 1;
  padding-left: 0.15rem;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 999px;
  background: rgba(212, 175, 55, 0.22);
  color: rgba(255, 255, 255, 0.92);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  background: rgba(212, 175, 55, 0.34);
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.input-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.input-icon-btn:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.08);
}

.input-icon-btn.recording {
  color: #e85d5d;
  animation: recording-pulse 1.2s ease-in-out infinite;
}

@keyframes recording-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
