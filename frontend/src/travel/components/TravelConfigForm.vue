<script setup lang="ts">
import { Button, InputNumber, Select, Textarea, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref, watch } from 'vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { CONFIG } from '@/utils/config'
import { parseQqBindingTarget } from '@/utils/qqNotification'
import { agentContacts, loadAgentContacts } from '@/utils/session'

const props = withDefaults(defineProps<{ loading: boolean, buttonLabel?: string }>(), {
  buttonLabel: '出发！',
})
const emit = defineEmits<{
  start: [params: {
    agentId?: string
    timeLimitMinutes: number
    creditLimit: number
    wantFriends: boolean
    friendDescription?: string
    goalPrompt?: string
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }]
}>()

const timeLimit = ref(300)
const creditLimit = ref(1000)
const wantFriends = ref(true)
const friendDescription = ref('')
const goalPrompt = ref('追踪 AI、技术与互联网的最新热点，优先关注仍在持续发酵的话题和一手来源')
const selectedAgentId = ref('')
const browserVisible = ref(false)
const browserKeepOpen = ref(false)
const openclawAgents = computed(() => agentContacts.value.filter(agent => (agent.engine || 'openclaw') === 'openclaw'))
const feishuDeliverTarget = computed(() => {
  const settings = CONFIG.value.notifications.feishu
  const hasApp = !!CONFIG.value.openclaw.feishu.app_id.trim() && !!CONFIG.value.openclaw.feishu.app_secret.trim()
  if (!settings.enabled || !CONFIG.value.openclaw.feishu.enabled || !hasApp)
    return ''
  return settings.recipient_type === 'chat_id'
    ? settings.recipient_chat_id.trim()
    : settings.recipient_open_id.trim()
})
const qqBinding = computed(() => parseQqBindingTarget(CONFIG.value.notifications.qq.binding_target))
const qqVerificationReady = computed(() => {
  const settings = CONFIG.value.notifications.qq
  return settings.binding_verified && settings.binding_verified_email === qqBinding.value.normalizedEmail
})
const qqNotificationReady = computed(() => {
  const settings = CONFIG.value.notifications.qq
  return settings.enabled
    && qqBinding.value.isValid
    && qqVerificationReady.value
})
const travelNotificationSummary = computed(() => {
  const lines: string[] = []
  if (feishuDeliverTarget.value) {
    const reportMode = CONFIG.value.notifications.feishu.deliver_full_report ? '完整报告' : '完成摘要'
    lines.push(`飞书通知已启用，将回传${reportMode}到 ${CONFIG.value.notifications.feishu.recipient_type}: ${feishuDeliverTarget.value}`)
  }
  if (CONFIG.value.notifications.qq.enabled) {
    if (qqNotificationReady.value) {
      lines.push(`QQ 通知已启用，探索完成后会通过 Undefined QQ机器人 @${qqBinding.value.normalizedQq}`)
    }
    else if (qqBinding.value.isEmpty) {
      lines.push('QQ 通知已启用，但 QQ 号 / QQ 邮箱还没填，当前不会生效')
    }
    else if (!qqBinding.value.isValid) {
      lines.push(`QQ 通知已启用，但 ${qqBinding.value.errorMessage}`)
    }
    else if (!qqVerificationReady.value) {
      lines.push(`QQ 通知已启用，但邮箱验证码还没填；将按 ${qqBinding.value.normalizedEmail} 验证`)
    }
    else {
      lines.push('QQ 通知已启用，但当前绑定信息还不完整')
    }
  }
  if (lines.length === 0) {
    lines.push('未配置外部通知，探索结果会保存在应用内')
  }
  return lines
})

watch(openclawAgents, (agents) => {
  if (!selectedAgentId.value && agents.length > 0) {
    selectedAgentId.value = agents[0]!.id
  }
  if (selectedAgentId.value && !agents.some(agent => agent.id === selectedAgentId.value)) {
    selectedAgentId.value = agents[0]?.id || ''
  }
}, { immediate: true })

onMounted(() => {
  void loadAgentContacts()
})

function onStart() {
  const deliverChannel = feishuDeliverTarget.value ? 'feishu' : undefined
  const deliverTo = feishuDeliverTarget.value || undefined
  emit('start', {
    agentId: selectedAgentId.value || undefined,
    timeLimitMinutes: timeLimit.value,
    creditLimit: creditLimit.value,
    wantFriends: wantFriends.value,
    friendDescription: friendDescription.value || undefined,
    goalPrompt: goalPrompt.value || undefined,
    deliverFullReport: deliverChannel ? CONFIG.value.notifications.feishu.deliver_full_report : false,
    deliverChannel,
    deliverTo,
    browserVisible: browserVisible.value,
    browserKeepOpen: browserKeepOpen.value,
    browserIdleTimeoutSeconds: 300,
  })
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="text-white/60 text-xs pl-1">
      探索干员
    </div>
    <Select
      v-model="selectedAgentId"
      :options="openclawAgents"
      option-label="name"
      option-value="id"
      placeholder="选择一个通讯录中的干员"
      :disabled="!openclawAgents.length"
    />
    <div v-if="!openclawAgents.length" class="text-xs text-white/30 pl-1">
      需要先创建一个 OpenClaw 干员，探索才会使用该干员的人格模板和实例记忆。
    </div>
  </div>

  <div class="border-t border-white/8 my-1" />

  <div class="flex flex-col gap-2">
    <div class="text-white/60 text-xs pl-1">
      探索方向
    </div>
    <Textarea
      v-model="goalPrompt"
      rows="4"
      class="resize-none"
      placeholder="告诉 OpenClaw 你想让它重点探索的方向，例如：最新 AI 产品、海外开发者热点、前沿论文、设计趋势等"
    />
  </div>

  <div class="border-t border-white/8 my-1" />

  <!-- 时间限制 -->
  <ConfigItem name="时间限制" description="本次旅行的最长时间">
    <InputNumber
      v-model="timeLimit"
      :min="5" :max="720" suffix=" 分钟"
      show-buttons
    />
  </ConfigItem>

  <!-- 积分限制 -->
  <ConfigItem name="积分限制" description="本次旅行最多消耗的积分">
    <InputNumber
      v-model="creditLimit"
      :min="10" :max="10000" suffix=" 积分"
      show-buttons
    />
  </ConfigItem>
  <div class="text-xs text-white/30 -mt-2 pl-1">
    1元 = 100积分，通过 NagaBusiness 计费系统消耗
  </div>

  <div class="border-t border-white/8 my-1" />

  <!-- 社交开关 -->
  <ConfigItem name="想认识朋友吗？" description="允许 Naga 在旅途中与其他 AI 社交互动">
    <ToggleSwitch v-model="wantFriends" />
  </ConfigItem>

  <!-- 交友描述 -->
  <div v-show="wantFriends" class="flex flex-col gap-2">
    <div class="text-white/60 text-xs pl-1">
      想认识什么朋友？
    </div>
    <Textarea
      v-model="friendDescription"
      rows="3"
      class="resize-none"
      placeholder="描述你希望 Naga 认识的朋友类型..."
    />
  </div>

  <div class="border-t border-white/8 my-1" />

  <div class="flex flex-col gap-2">
    <div class="text-white/60 text-xs pl-1">
      浏览器策略
    </div>
    <ConfigItem name="浏览器可见" description="关闭时默认无头运行；打开后会尝试用可见窗口执行后续浏览器动作">
      <ToggleSwitch v-model="browserVisible" />
    </ConfigItem>
    <ConfigItem name="页面保持打开" description="关闭时，页面空闲 300 秒会自动关闭；打开后不会自动回收标签页">
      <ToggleSwitch v-model="browserKeepOpen" />
    </ConfigItem>
  </div>

  <div class="border-t border-white/8 my-1" />

  <div class="flex flex-col gap-2">
    <div class="text-white/60 text-xs pl-1">
      通知回传
    </div>
    <div class="text-xs text-white/40 pl-1 leading-6">
      <div v-for="line in travelNotificationSummary" :key="line">
        {{ line }}
      </div>
    </div>
  </div>

  <!-- 出发按钮 -->
  <div class="flex justify-center mt-2">
    <Button
      :label="props.buttonLabel"
      class="px-8!"
      :loading="loading"
      :disabled="!openclawAgents.length || !selectedAgentId"
      @click="onStart"
    />
  </div>
</template>
