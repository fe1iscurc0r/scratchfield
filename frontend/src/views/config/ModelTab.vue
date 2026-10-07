<script setup lang="ts">
/**
 * 模型连接设置页（卷181-D：从 ConfigView 巨石搬移，纯搬移不重构逻辑）。
 *
 * 状态来源：CONFIG（@/utils/config 全局 ref）+ useAuth（云端网关判定）；
 * 原先定义在 ConfigView 的 PROVIDER_OPTIONS/MODEL_OPTIONS/API_FORMAT_OPTIONS/
 * ASR_PROVIDERS/TTS_VOICES/useCloudGateway/llmUsesGateway/gatewayBusy/
 * toggleOpenClawGateway/onProviderChange/modelPricingMap/selectedModelPricing/
 * loadModelPricing/accordionModel 随块搬入本组件（这些符号只服务本块）。
 */
import type { ModelPricing } from '@/api/business'
import { useStorage } from '@vueuse/core'
import { Accordion, Divider, InputNumber, InputText, Select, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import { getModels } from '@/api/business'
import API from '@/api/core'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { cloudUser, isLoggedIn } from '@/composables/useAuth'
import { CONFIG } from '@/utils/config'
import { feedback } from '@/utils/feedback'

const accordionModel = useStorage('accordion-config-model', [])

const MODEL_OPTIONS = [
  { label: 'Default', value: 'default' },
  { label: 'DeepSeek V3.2', value: 'deepseek-v3.2' },
  { label: 'Kimi K2.5', value: 'kimi-k2.5' },
  { label: 'GPT-5', value: 'gpt-5' },
  { label: 'Claude Sonnet 4.5', value: 'claude-sonnet-4-5' },
]

const PROVIDER_OPTIONS = [
  { label: '自动识别', value: 'auto', apiFormat: 'openai', baseUrl: '' },
  { label: 'DeepSeek', value: 'deepseek', apiFormat: 'openai', baseUrl: 'https://api.deepseek.com/v1' },
  { label: 'OpenAI 兼容', value: 'openai', apiFormat: 'openai', baseUrl: 'https://api.openai.com/v1' },
  { label: 'OpenRouter', value: 'openrouter', apiFormat: 'openai', baseUrl: 'https://openrouter.ai/api/v1' },
  { label: 'Anthropic', value: 'anthropic', apiFormat: 'anthropic', baseUrl: 'https://api.anthropic.com' },
  { label: 'Gemini', value: 'gemini', apiFormat: 'openai', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { label: '自定义', value: 'custom', apiFormat: 'openai', baseUrl: '' },
]

const API_FORMAT_OPTIONS = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic 原生', value: 'anthropic' },
]

// 模型 Tab 常量（原 MemoryView）
const ASR_PROVIDERS = {
  qwen: '通义千问',
  openai: 'OpenAI',
  local: 'FunASR',
}

const TTS_VOICES = {
  Cherry: '默认',
}

const useCloudGateway = computed({
  get() {
    return CONFIG.value.api.use_gateway
  },
  set(value: boolean) {
    CONFIG.value.api.use_gateway = value
  },
})

const llmUsesGateway = computed(() => isLoggedIn.value && CONFIG.value.api.use_gateway)

// ── 项目网关（OpenClaw Gateway）启停 ──
// 开关变更 → 调后端启停接口；后端同步 enabled，CONFIG 侧同步更新后随全局防抖落盘；busy 期间禁用开关防止重复点击
const gatewayBusy = ref(false)

async function toggleOpenClawGateway(value: boolean) {
  if (gatewayBusy.value)
    return
  gatewayBusy.value = true
  try {
    const res = value ? await API.openclawGatewayStart() : await API.openclawGatewayStop()
    CONFIG.value.openclaw.enabled = res.running
    if (res.success)
      feedback.success('项目网关已更新')
    else
      feedback.error('项目网关', res.message)
  }
  catch (e: any) {
    CONFIG.value.openclaw.enabled = !value // 回滚开关显示
    feedback.error('项目网关', e?.response?.data?.detail || e.message)
  }
  finally {
    gatewayBusy.value = false
  }
}

function onProviderChange(value: string) {
  const provider = PROVIDER_OPTIONS.find(item => item.value === value)
  CONFIG.value.api.provider = value
  if (!provider)
    return
  CONFIG.value.api.api_format = provider.apiFormat
  if (provider.baseUrl)
    CONFIG.value.api.base_url = provider.baseUrl
}

// ── 模型定价（登录后从服务端拉取） ──
const modelPricingMap = ref<Record<string, ModelPricing>>({})

const selectedModelPricing = computed(() => {
  const model = CONFIG.value.api.model || 'default'
  return modelPricingMap.value[model] ?? modelPricingMap.value[model.toLowerCase()] ?? null
})

async function loadModelPricing() {
  if (!isLoggedIn.value)
    return
  try {
    const res = await getModels()
    const map: Record<string, ModelPricing> = {}
    for (const m of res.data ?? []) {
      if (m.id)
        map[m.id] = m
    }
    modelPricingMap.value = map
  }
  catch {
    // 定价获取失败不影响使用
  }
}

onMounted(() => {
  // 以网关进程实际状态校准开关显示（后端被手动杀过网关进程时避免开关失真）
  API.openclawGatewayStatus()
    .then((res) => {
      CONFIG.value.openclaw.enabled = res.running
    })
    .catch(() => {})
  loadModelPricing()
})
</script>

<template>
  <Accordion :value="accordionModel" class="pb-8" multiple>
    <!-- 大语言模型 -->
    <ConfigGroup value="llm" header="大语言模型">
      <div class="grid gap-4">
        <ConfigItem name="使用 scratchpad Model 网关" description="登录后可通过网关调用模型；关闭后使用下方自定义供应商配置">
          <div class="flex items-center gap-3">
            <ToggleSwitch v-model="useCloudGateway" :disabled="!isLoggedIn" />
            <span v-if="isLoggedIn" class="gateway-state" :class="{ active: llmUsesGateway }">
              {{ llmUsesGateway ? '网关已启用' : '使用本地配置' }}
            </span>
            <span v-else class="gateway-state">未登录，使用本地配置</span>
          </div>
        </ConfigItem>
        <ConfigItem name="项目网关（OpenClaw）" description="本地 OpenClaw Gateway（端口 20789）。启用干员引擎/技能托管时需要；与上方云端 Model 网关无关">
          <ToggleSwitch :model-value="CONFIG.openclaw.enabled" :disabled="gatewayBusy" @update:model-value="(v: boolean) => toggleOpenClawGateway(v)" />
        </ConfigItem>
        <ConfigItem name="模型供应商" description="决定 API 格式与 LiteLLM 路由前缀">
          <Select
            v-model="CONFIG.api.provider"
            :options="PROVIDER_OPTIONS"
            option-label="label"
            option-value="value"
            @update:model-value="onProviderChange"
          />
        </ConfigItem>
        <ConfigItem name="API 格式" description="OpenAI 兼容接口或 Anthropic 原生 Messages API">
          <Select
            v-model="CONFIG.api.api_format"
            :options="API_FORMAT_OPTIONS"
            option-label="label"
            option-value="value"
            :disabled="CONFIG.api.provider === 'anthropic'"
          />
        </ConfigItem>
        <ConfigItem name="模型名称" description="用于对话的大语言模型">
          <div class="flex items-center gap-3">
            <Select
              v-model="CONFIG.api.model"
              editable
              filter
              :options="MODEL_OPTIONS"
              option-label="label"
              option-value="value"
              placeholder="选择或输入模型名"
            />
            <span v-if="selectedModelPricing" class="model-pricing">
              <span title="输入价格">↑{{ selectedModelPricing.inputPrice ?? '-' }}</span>
              <span class="text-white/15">/</span>
              <span title="输出价格">↓{{ selectedModelPricing.outputPrice ?? '-' }}</span>
            </span>
          </div>
        </ConfigItem>
        <ConfigItem name="API 地址" description="大语言模型的 API 地址">
          <div class="grid gap-1">
            <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录 ({{ cloudUser?.username }})，启用时优先走 scratchpad Model 网关；下方配置作备用，可随时改</span>
            <InputText v-model="CONFIG.api.base_url" placeholder="https://api.example.com/v1" />
          </div>
        </ConfigItem>
        <ConfigItem name="API 密钥" description="大语言模型的 API 密钥">
          <div class="grid gap-1">
            <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录 ({{ cloudUser?.username }})，启用时优先走网关；下方密钥可随时修改，或关闭上方网关开关强制使用本地密钥</span>
            <InputText v-model="CONFIG.api.api_key" type="password" />
          </div>
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="最大令牌数" description="单次对话的最大长度限制">
          <InputNumber v-model="CONFIG.api.max_tokens" show-buttons />
        </ConfigItem>
        <ConfigItem name="历史轮数" description="使用最近几轮对话内容作为上下文">
          <InputNumber v-model="CONFIG.api.max_history_rounds" show-buttons />
        </ConfigItem>
        <ConfigItem name="加载天数" description="从最近几天的日志文件中加载历史对话">
          <InputNumber v-model="CONFIG.api.context_load_days" show-buttons />
        </ConfigItem>
      </div>
    </ConfigGroup>

    <!-- 电脑控制模型 -->
    <ConfigGroup value="control">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>电脑控制模型</span>
          <label class="flex items-center gap-4">
            启用
            <ToggleSwitch v-model="CONFIG.computer_control.enabled" size="small" @click.stop />
          </label>
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="控制模型" description="用于电脑控制任务的主要模型">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.computer_control.model" />
        </ConfigItem>
        <ConfigItem name="控制模型 API 地址" description="控制模型的 API 地址">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.computer_control.model_url" />
        </ConfigItem>
        <ConfigItem name="控制模型 API 密钥" description="控制模型的 API 密钥">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，无需输入</span>
          <InputText v-else v-model="CONFIG.computer_control.api_key" />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="定位模型" description="用于元素定位和坐标识别的模型">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.computer_control.grounding_model" />
        </ConfigItem>
        <ConfigItem name="定位模型 API 地址" description="定位模型的 API 地址">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.computer_control.grounding_url" />
        </ConfigItem>
        <ConfigItem name="定位模型 API 密钥" description="定位模型的 API 密钥">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，无需输入</span>
          <InputText v-else v-model="CONFIG.computer_control.grounding_api_key" />
        </ConfigItem>
      </div>
    </ConfigGroup>

    <!-- 语音识别模型 -->
    <ConfigGroup value="asr">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>语音识别模型</span>
          <label class="flex items-center gap-4">
            启用
            <ToggleSwitch v-model="CONFIG.voice_realtime.enabled" size="small" @click.stop />
          </label>
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="模型名称" description="用于语音识别的模型">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.voice_realtime.asr_model" />
        </ConfigItem>
        <template v-if="!llmUsesGateway">
          <ConfigItem name="模型提供者" description="语音识别模型的提供者">
            <Select v-model="CONFIG.voice_realtime.provider" :options="Object.keys(ASR_PROVIDERS)">
              <template #option="{ option }">
                {{ ASR_PROVIDERS[option as keyof typeof ASR_PROVIDERS] }}
              </template>
              <template #value="{ value }">
                {{ ASR_PROVIDERS[value as keyof typeof ASR_PROVIDERS] }}
              </template>
            </Select>
          </ConfigItem>
          <ConfigItem name="API 密钥" description="语音识别模型的 API 密钥">
            <InputText v-model="CONFIG.voice_realtime.api_key" />
          </ConfigItem>
        </template>
        <ConfigItem v-else name="API 密钥">
          <span class="authed-hint">&#10003; 已登录，无需输入</span>
        </ConfigItem>
      </div>
    </ConfigGroup>

    <!-- 语音合成模型 -->
    <ConfigGroup value="tts">
      <template #header>
        <div class="w-full flex justify-between items-center -my-1.5">
          <span>语音合成模型</span>
          <label class="flex items-center gap-4">
            启用
            <ToggleSwitch v-model="CONFIG.system.voice_enabled" size="small" @click.stop />
          </label>
        </div>
      </template>
      <div class="grid gap-4">
        <ConfigItem name="模型名称" description="用于语音合成的模型">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.voice_realtime.tts_model" />
        </ConfigItem>
        <ConfigItem name="声线" description="语音合成模型的声线">
          <Select v-model="CONFIG.tts.default_voice" :options="Object.keys(TTS_VOICES)">
            <template #option="{ option }">
              {{ TTS_VOICES[option as keyof typeof TTS_VOICES] }}
            </template>
            <template #value="{ value }">
              {{ TTS_VOICES[value as keyof typeof TTS_VOICES] }}
            </template>
          </Select>
        </ConfigItem>
        <template v-if="!llmUsesGateway">
          <ConfigItem name="服务端口" description="用于语音合成的本地服务端口">
            <InputNumber v-model="CONFIG.tts.port" :min="1000" :max="65535" show-buttons />
          </ConfigItem>
          <ConfigItem name="API 密钥" description="语音合成模型的 API 密钥">
            <InputText v-model="CONFIG.tts.api_key" />
          </ConfigItem>
        </template>
        <ConfigItem v-else name="API 密钥">
          <span class="authed-hint">&#10003; 已登录，无需输入</span>
        </ConfigItem>
      </div>
    </ConfigGroup>

    <!-- 嵌入模型 -->
    <ConfigGroup value="embedding" header="嵌入模型">
      <div class="grid gap-4">
        <ConfigItem name="模型名称" description="用于向量嵌入的模型">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.embedding.model" />
        </ConfigItem>
        <ConfigItem name="API 地址" description="嵌入模型的 API 地址（留空使用主模型地址）">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，使用 scratchpad Model 网关</span>
          <InputText v-else v-model="CONFIG.embedding.api_base" />
        </ConfigItem>
        <ConfigItem name="API 密钥" description="嵌入模型的 API 密钥（留空使用主模型密钥）">
          <span v-if="llmUsesGateway" class="authed-hint">&#10003; 已登录，无需输入</span>
          <InputText v-else v-model="CONFIG.embedding.api_key" type="password" />
        </ConfigItem>
      </div>
    </ConfigGroup>
  </Accordion>
</template>

<style scoped>
.authed-hint {
  color: #4ade80;
  font-size: 0.875rem;
  font-weight: 500;
}

.gateway-state {
  color: rgba(255, 255, 255, 0.48);
  font-size: 0.8rem;
  white-space: nowrap;
}

.gateway-state.active {
  color: #4ade80;
  font-weight: 500;
}

.model-pricing {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
