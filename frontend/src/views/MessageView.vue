<script lang="ts">
import type { ChatTab } from '@/utils/session'
import { useEventListener } from '@vueuse/core'
import { computed, nextTick, onBeforeUnmount, onMounted, useTemplateRef, watch } from 'vue'
import AgentContacts from '@/components/AgentContacts.vue'
import BoxContainer from '@/components/BoxContainer.vue'
import MessageItem from '@/components/MessageItem.vue'
import { toolMessage } from '@/composables/useToolStatus'
import { CONFIG } from '@/utils/config'
import { live2dState } from '@/utils/live2dController'
import { activeTabId, CURRENT_SESSION_ID, getActiveTab, isAgentLoading, newSession, tabs } from '@/utils/session'
import { isPlaying } from '@/utils/tts'
import { setMessageViewExpanded } from '@/utils/uiState'
import { useChatTabs } from './message/composables/useChatTabs'
import { useComposer } from './message/composables/useComposer'
import { useMessageFileUpload } from './message/composables/useMessageFileUpload'
import { useSendDispatcher } from './message/composables/useSendDispatcher'
import { useSessionHistory } from './message/composables/useSessionHistory'
import { useTravelBanner } from './message/composables/useTravelBanner'
import { useVoiceInput } from './message/composables/useVoiceInput'
import MessageComposerDock from './message/MessageComposerDock.vue'
import MessageRawHistoryDialog from './message/MessageRawHistoryDialog.vue'
import MessageSessionPanel from './message/MessageSessionPanel.vue'
import MessageTabBar from './message/MessageTabBar.vue'
import MessageTravelBanners from './message/MessageTravelBanners.vue'

// 兼容红线：原 MessageView.vue 在此导出 chatStream，外部（命令面板等）直接 import 使用。
// 拆分后实体搬进 message/composables/useChatStream.ts，此处保留同名转发。
export { chatStream } from './message/composables/useChatStream'
</script>

<script setup lang="ts">
const input = defineModel<string>({ default: '' })
const normalContainerRef = useTemplateRef('normalContainerRef')
const expandedContainerRef = useTemplateRef('expandedContainerRef')

// ── 输入区（尺寸测量/放大布局/TTS 开关）──
const {
  isExpanded,
  expandedStyle,
  expandedInputStyle,
  resizeComposer,
  updateExpandedLayout,
  scrollToBottom,
  scrollToBottomIfPinned,
  toggleExpanded,
  toggleTTS,
} = useComposer({ normalContainerRef, expandedContainerRef })

// ── 探索横幅与原始记录 ──
const {
  activeAgentTravel,
  completedAgentTravel,
  sendingTravelInstruction,
  rawTravelHistoryVisible,
  rawTravelHistoryLoading,
  rawTravelHistoryError,
  loadingCompletedTravelReport,
  completedTravelReport,
  activeAgentTravelMeta,
  rawTravelHistoryTimeline,
  openRawTravelHistory,
} = useTravelBanner()

// ── 发送分发（sendMessage / 干员双通道流）──
const { pushSystemMessage, dispatchToActiveTab, sendMessage, sendTravelInstruction } = useSendDispatcher({
  input,
  scrollToBottom,
  scrollToBottomIfPinned,
  activeAgentTravel,
})

// ── Tab 管理 ──
const { renamingTabId, renameValue, closeTab, startRename, finishRename } = useChatTabs(() => {
  nextTick().then(scrollToBottom)
})

// ── 会话历史 ──
const {
  showHistory,
  sessions,
  loadingSessions,
  toggleHistory,
  handleSwitchSession,
  handleDeleteSession,
  handleNewSession,
} = useSessionHistory(() => {
  nextTick().then(scrollToBottom)
})

// ── 文件上传 ──
const { triggerUpload, handleFileUpload } = useMessageFileUpload({ pushSystemMessage, dispatchToActiveTab })

// ── 语音输入 ──
const { isRecording, toggleVoiceInput, stopVoiceInput } = useVoiceInput({ pushSystemMessage, dispatchToActiveTab })

/** 当前活跃 tab 的 messages（用于模板渲染） */
const activeMessages = computed(() => getActiveTab().messages)

/** 当前活跃 tab 是否正在加载干员历史 */
const agentLoadingActive = computed(() => {
  const tab = getActiveTab()
  return tab.type === 'agent' && tab.instanceId ? isAgentLoading(tab.instanceId) : false
})

/** 发送（dock 的 send 事件） */
function handleTabSwitch(tab: ChatTab) {
  activeTabId.value = tab.id
}

// TTS 播放状态驱动嘴部动画：开始播放→talking，结束→idle
watch(isPlaying, (playing) => {
  live2dState.value = playing ? 'talking' : 'idle'
})

watch(input, () => {
  nextTick(() => {
    resizeComposer()
    if (isExpanded.value)
      updateExpandedLayout()
  })
})

watch(isExpanded, (value) => {
  setMessageViewExpanded(value)
})

// ── 命令面板 / Ctrl+N 动作对接（卷150：new-chat 直达新会话） ──
function onQuickAction(e: Event) {
  const kind = (e as CustomEvent<{ kind: string }>).detail?.kind
  if (kind === 'new-chat')
    newSession()
}
window.addEventListener('lumo:quick-action', onQuickAction)
onBeforeUnmount(() => window.removeEventListener('lumo:quick-action', onQuickAction))

onMounted(async () => {
  const { loadCurrentSession } = await import('@/utils/session')
  loadCurrentSession()
  scrollToBottom()
  nextTick(resizeComposer)
})

onBeforeUnmount(() => {
  setMessageViewExpanded(false)
  // 录音中离开路由也要释放麦克风（stop → onstop 内已停所有音轨）
  stopVoiceInput()
})

useEventListener('token', scrollToBottomIfPinned)
useEventListener(window, 'resize', () => {
  if (isExpanded.value)
    updateExpandedLayout()
})
</script>

<template>
  <div class="flex flex-col gap-8 relative">
    <div class="flex min-h-0 grow">
      <!-- 左侧通讯录抽屉 -->
      <AgentContacts />

      <!-- 主内容区 -->
      <BoxContainer v-show="!isExpanded" ref="normalContainerRef" class="w-full grow" hide-back>
        <template #header>
          <MessageTabBar
            v-model:rename-value="renameValue"
            :tabs="tabs"
            :active-tab-id="activeTabId"
            :renaming-tab-id="renamingTabId"
            variant="collapse"
            @switch="handleTabSwitch"
            @start-rename="startRename"
            @close-tab="closeTab"
            @finish-rename="finishRename"
            @toggle-expanded="toggleExpanded"
          />
        </template>

        <!-- 干员加载中：转圈圈 -->
        <div v-if="agentLoadingActive" class="agent-loading-overlay">
          <div class="agent-loading-spinner" />
          <div class="agent-loading-text">干员加载中</div>
        </div>

        <!-- 消息列表（当前活跃 tab） -->
        <div v-else class="grid gap-4 pb-8">
          <MessageTravelBanners
            :active-agent-travel="activeAgentTravel"
            :completed-agent-travel="completedAgentTravel"
            :active-agent-travel-meta="activeAgentTravelMeta"
            :loading-completed-travel-report="loadingCompletedTravelReport"
            :completed-travel-report="completedTravelReport"
            @open-raw-history="openRawTravelHistory"
          />
          <MessageItem
            v-for="item, index in activeMessages" :key="index"
            :role="item.role" :content="item.content"
            :reasoning="item.reasoning" :sender="item.sender"
            :generating="item.generating" :status="item.status"
            :tool-events="item.toolEvents"
            :class="(item.generating && index === activeMessages.length - 1) || 'border-b'"
          />
        </div>
      </BoxContainer>

      <Teleport to="body">
        <div v-if="isExpanded" class="expanded-chat-overlay" :style="expandedStyle">
          <BoxContainer
            ref="expandedContainerRef"
            class="message-shell size-full"
            box-class="w-full h-full"
            :parallax="false"
            hide-back
          >
            <template #header>
              <MessageTabBar
                v-model:rename-value="renameValue"
                :tabs="tabs"
                :active-tab-id="activeTabId"
                :renaming-tab-id="renamingTabId"
                variant="expand"
                @switch="handleTabSwitch"
                @start-rename="startRename"
                @close-tab="closeTab"
                @finish-rename="finishRename"
                @toggle-expanded="toggleExpanded"
              />
            </template>

            <div v-if="agentLoadingActive" class="agent-loading-overlay">
              <div class="agent-loading-spinner" />
              <div class="agent-loading-text">干员加载中</div>
            </div>

            <div v-else class="grid gap-4 pb-8">
              <MessageTravelBanners
                :active-agent-travel="activeAgentTravel"
                :completed-agent-travel="completedAgentTravel"
                :active-agent-travel-meta="activeAgentTravelMeta"
                :loading-completed-travel-report="loadingCompletedTravelReport"
                :completed-travel-report="completedTravelReport"
                @open-raw-history="openRawTravelHistory"
              />
              <MessageItem
                v-for="item, index in activeMessages" :key="`expanded-${index}`"
                :role="item.role" :content="item.content"
                :reasoning="item.reasoning" :sender="item.sender"
                :generating="item.generating" :status="item.status"
                :tool-events="item.toolEvents"
                :class="(item.generating && index === activeMessages.length - 1) || 'border-b'"
              />
            </div>
          </BoxContainer>
        </div>
      </Teleport>
    </div>

    <!-- Session History Panel（仅在陆墨 tab 可见） -->
    <MessageSessionPanel
      :open="showHistory && activeTabId === 'lumo' && !isExpanded"
      :sessions="sessions"
      :loading="loadingSessions"
      :current-session-id="CURRENT_SESSION_ID"
      @close="showHistory = false"
      @switch="handleSwitchSession"
      @delete="handleDeleteSession"
    />

    <div v-if="toolMessage && !isExpanded" class="mx-[var(--nav-back-width)] text-white/50 text-xs px-2 py-1">
      {{ toolMessage }}
    </div>

    <MessageComposerDock
      v-model="input"
      :active-tab-id="activeTabId"
      :active-tab-name="getActiveTab().name"
      :show-history="showHistory"
      :is-recording="isRecording"
      :tts-enabled="CONFIG.system.voice_enabled"
      :sending-travel-instruction="sendingTravelInstruction"
      :has-active-travel="!!activeAgentTravel"
      :voice-realtime-enabled="CONFIG.voice_realtime.enabled"
      :is-expanded="isExpanded"
      :expanded-input-style="expandedInputStyle"
      @send="sendMessage"
      @new-session="handleNewSession"
      @toggle-history="toggleHistory"
      @voice-toggle="toggleVoiceInput"
      @tts-toggle="toggleTTS"
      @upload="triggerUpload"
      @travel-instruction="sendTravelInstruction"
      @file-change="handleFileUpload"
    />

    <MessageRawHistoryDialog
      v-model:visible="rawTravelHistoryVisible"
      :loading="rawTravelHistoryLoading"
      :error="rawTravelHistoryError"
      :timeline="rawTravelHistoryTimeline"
      :total-count="rawTravelHistoryError ? 0 : rawTravelHistoryTimeline.length || 0"
    />
  </div>
</template>

<style scoped>
.expanded-chat-overlay {
  position: fixed;
  z-index: 80;
}

.expanded-chat-overlay :deep(.box) {
  width: 100%;
  height: 100%;
}

.agent-loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  min-height: 200px;
}

.agent-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: agent-spin 0.8s linear infinite;
}

.agent-loading-text {
  color: rgba(255, 255, 255, 0.5);
  font-size: 14px;
}

@keyframes agent-spin {
  to { transform: rotate(360deg); }
}
</style>
