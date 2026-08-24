<script setup lang="ts">
import type { TravelSession } from '@/travel/types'
import { Button } from 'primevue'
import { formatDate, statusLabel } from '@/travel/composables/useTravel'
import TravelDiscoveryItem from './TravelDiscoveryItem.vue'

const props = defineProps<{ session: TravelSession }>()
defineEmits<{ newTravel: [] }>()

function notificationLabel(key: string) {
  if (key === 'feishu')
    return '飞书通知'
  if (key === 'qq')
    return 'QQ 通知'
  return key
}

function notificationStatusLabel(status: string) {
  if (status === 'delivered_full_report')
    return '已通过完整报告回传'
  if (status === 'delivered_summary')
    return '已发送完成摘要'
  if (status === 'accepted')
    return '已被通知服务接受'
  if (status === 'skipped:incomplete_config')
    return '已启用但配置不完整，未发送'
  if (status === 'skipped:invalid_qq')
    return 'QQ 绑定信息格式不正确，未发送'
  if (status.startsWith('accepted:'))
    return `已被通知服务接受（${status.slice('accepted:'.length)}）`
  if (status.startsWith('skipped:unsupported_provider:'))
    return `当前提供方未实装（${status.slice('skipped:unsupported_provider:'.length)}）`
  if (status.startsWith('failed:'))
    return `发送失败：${status.slice('failed:'.length)}`
  return status
}
</script>

<template>
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2 text-white/80 text-base font-bold">
      <span
        class="inline-block w-2 h-2 rounded-full"
        :class="session.status === 'completed'
          ? 'bg-blue-400'
          : session.status === 'interrupted'
            ? 'bg-orange-300'
            : 'bg-red-400'"
      />
      {{ statusLabel[session.status] || session.status }}
    </div>
    <span class="text-white/30 text-xs">{{ formatDate(session.completedAt) }}</span>
  </div>

  <!-- 总结 -->
  <div v-if="session.goalPrompt" class="text-white/35 text-[11px] bg-white/2 rounded-lg p-3">
    <div>探索方向：{{ session.goalPrompt }}</div>
    <div v-if="session.agentName" class="mt-1">
      执行干员：{{ session.agentName }}
    </div>
  </div>

  <div v-if="session.summary" class="text-white/60 text-xs leading-relaxed bg-white/3 rounded-lg p-3">
    {{ session.summary }}
  </div>

  <div
    v-if="session.forumPostStatus || session.fullReportDeliveryStatus || Object.keys(props.session.notificationDeliveryStatuses || {}).length"
    class="grid grid-cols-1 gap-2 text-[11px] text-white/45 bg-white/2 rounded-lg p-3"
  >
    <div v-if="session.forumPostStatus">
      论坛精华帖：{{ session.forumPostStatus }}<span v-if="session.forumPostId">（{{ session.forumPostId }}）</span>
    </div>
    <div v-if="session.fullReportDeliveryStatus">
      完整报告回传：{{ session.fullReportDeliveryStatus }}
    </div>
    <div
      v-for="(status, key) in props.session.notificationDeliveryStatuses || {}"
      :key="key"
    >
      {{ notificationLabel(String(key)) }}：{{ notificationStatusLabel(String(status)) }}
    </div>
  </div>

  <!-- 错误信息 -->
  <div v-if="session.error" class="text-red-400/70 text-xs bg-red-500/5 rounded-lg p-3">
    {{ session.error }}
  </div>

  <!-- 发现列表 -->
  <div v-if="session.discoveries.length" class="flex flex-col gap-2">
    <div class="text-white/40 text-xs">
      发现 ({{ session.discoveries.length }})
    </div>
    <div class="flex flex-col gap-1.5 max-h-60 overflow-y-auto">
      <TravelDiscoveryItem
        v-for="(d, i) in session.discoveries"
        :key="i"
        :discovery="d"
        clickable
      />
    </div>
  </div>

  <!-- 社交互动 -->
  <div v-if="session.socialInteractions.length" class="flex flex-col gap-2">
    <div class="text-white/40 text-xs">
      社交互动 ({{ session.socialInteractions.length }})
    </div>
    <div class="flex flex-col gap-1.5">
      <div
        v-for="(s, i) in session.socialInteractions"
        :key="i"
        class="flex items-center gap-2 px-2 py-1.5 rounded bg-white/3 text-xs"
      >
        <span class="text-white/30 shrink-0">{{ s.type === 'post_created' ? '发帖' : s.type === 'reply_sent' ? '回复' : '好友' }}</span>
        <span class="text-white/50 truncate">{{ s.contentPreview }}</span>
      </div>
    </div>
  </div>

  <div class="border-t border-white/8 my-1" />

  <!-- 返回设置 -->
  <div class="flex justify-center">
    <Button
      label="新建探索"
      outlined
      class="px-6!"
      @click="$emit('newTravel')"
    />
  </div>
</template>
