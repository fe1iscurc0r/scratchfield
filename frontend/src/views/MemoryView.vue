<script setup lang="ts">
import type { MemoryStats } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, Select, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { isLoggedIn, cloudUser } from '@/composables/useAuth'
import { CONFIG } from '@/utils/config'

const accordionValue = useStorage('accordion-memory', [])

const memoryStats = ref<MemoryStats>()
const testResult = ref<{
  severity: 'success' | 'error'
  message: string
}>()

const isCloudMode = computed(() => isLoggedIn.value)

const similarityPercent = computed({
  get() {
    return CONFIG.value.grag.similarity_threshold * 100
  },
  set(value: number) {
    CONFIG.value.grag.similarity_threshold = value / 100
  },
})

const ASR_PROVIDERS = {
  qwen: '通义千问',
  openai: 'OpenAI',
  local: 'FunASR',
}

const TTS_VOICES = {
  Cherry: '默认',
}

async function testConnection() {
  testResult.value = undefined
  try {
    const res = await API.getMemoryStats()
    const stats = res.memoryStats ?? res
    if (stats.enabled === false) {
      testResult.value = {
        severity: 'error',
        message: `未启用: ${stats.message || '请先启用知识图谱'}`,
      }
    }
    else {
      memoryStats.value = stats
      testResult.value = {
        severity: 'success',
        message: `连接成功：已加载 ${stats.totalQuintuples ?? 0} 个五元组`,
      }
    }
  }
  catch (error: any) {
    testResult.value = {
      severity: 'error',
      message: `连接失败: ${error.message}`,
    }
  }
}

onMounted(() => {
  testConnection()
})
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" class="pb-8" multiple>
      <!-- 大语言模型 -->
      <ConfigGroup value="llm" header="大语言模型">
        <div class="grid gap-4">
          <ConfigItem name="模型名称" description="用于对话的大语言模型">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
            <InputText v-else v-model="CONFIG.api.model" />
          </ConfigItem>
          <ConfigItem name="API 地址" description="大语言模型的 API 地址">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆 ({{ cloudUser?.username }})，使用 scratchpad Model 网关</span>
            <InputText v-else v-model="CONFIG.api.base_url" />
          </ConfigItem>
          <ConfigItem name="API 密钥" description="大语言模型的 API 密钥">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆 ({{ cloudUser?.username }})，无需输入</span>
            <InputText v-else v-model="CONFIG.api.api_key" type="password" />
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

      <!-- 云端记忆服务 / Neo4j（含知识图谱选项） -->
      <ConfigGroup value="neo4j">
        <template #header>
          <div class="w-full flex justify-between items-center -my-1.5">
            <span>{{ isCloudMode ? '云端记忆服务' : 'Neo4j 数据库' }}</span>
            <span v-if="isCloudMode" class="text-xs text-green-400 flex items-center gap-1">
              <span class="inline-block w-2 h-2 rounded-full bg-green-400" />
              已登录
            </span>
          </div>
        </template>
        <div class="grid gap-4">
          <!-- 云端模式：显示连接状态 -->
          <template v-if="isCloudMode">
            <ConfigItem name="服务状态" description="夏园 云端记忆微服务">
              <div class="text-xs text-white/70">
                <div>用户: {{ cloudUser?.username }}</div>
                <div class="mt-1 text-white/40">
                  云端记忆服务已连接
                </div>
              </div>
            </ConfigItem>
            <ConfigItem
              v-if="memoryStats"
              name="五元组数量"
              description="云端存储的记忆五元组总数"
            >
              <span class="text-white/70">{{ memoryStats.totalQuintuples ?? 0 }}</span>
            </ConfigItem>
          </template>
          <!-- 本地模式：显示 Neo4j 配置 -->
          <template v-else>
            <ConfigItem name="连接地址" description="Neo4j 数据库连接 URI">
              <InputText v-model="CONFIG.grag.neo4j_uri" placeholder="neo4j://127.0.0.1:7687" />
            </ConfigItem>
            <ConfigItem name="用户名" description="Neo4j 数据库用户名">
              <InputText v-model="CONFIG.grag.neo4j_user" placeholder="neo4j" />
            </ConfigItem>
            <ConfigItem name="密码" description="Neo4j 数据库密码">
              <InputText v-model="CONFIG.grag.neo4j_password" placeholder="••••••••" />
            </ConfigItem>
          </template>
          <Divider class="m-1!" />
          <!-- 知识图谱选项（原独立分组，现合并至此） -->
          <ConfigItem name="知识图谱">
            <label class="flex items-center gap-4">
              启用
              <ToggleSwitch v-model="CONFIG.grag.enabled" size="small" />
            </label>
          </ConfigItem>
          <ConfigItem name="自动提取" description="自动从对话中提取五元组知识">
            <ToggleSwitch v-model="CONFIG.grag.auto_extract" />
          </ConfigItem>
          <ConfigItem name="上下文长度" description="最近对话窗口大小">
            <InputNumber v-model="CONFIG.grag.context_length" :min="1" :max="20" show-buttons />
          </ConfigItem>
          <ConfigItem name="相似度阈值" description="RAG 知识检索匹配阈值">
            <InputNumber v-model="similarityPercent" :min="0" :max="100" suffix="%" show-buttons />
          </ConfigItem>
          <Divider class="m-1!" />
          <div class="flex flex-row-reverse justify-between gap-4">
            <Button
              :label="testResult ? (isCloudMode ? '检查连接' : '测试连接') : '测试中...'"
              size="small"
              :disabled="!testResult"
              @click="testConnection"
            />
            <Message
              v-if="testResult" :pt="{ content: { class: 'p-2.5!' } }"
              :severity="testResult.severity"
            >
              {{ testResult.message }}
            </Message>
          </div>
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
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
            <InputText v-else v-model="CONFIG.computer_control.model" />
          </ConfigItem>
          <ConfigItem name="控制模型 API 地址" description="控制模型的 API 地址">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，使用 scratchpad Model 网关</span>
            <InputText v-else v-model="CONFIG.computer_control.model_url" />
          </ConfigItem>
          <ConfigItem name="控制模型 API 密钥" description="控制模型的 API 密钥">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需输入</span>
            <InputText v-else v-model="CONFIG.computer_control.api_key" />
          </ConfigItem>
          <Divider class="m-1!" />
          <ConfigItem name="定位模型" description="用于元素定位和坐标识别的模型">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
            <InputText v-else v-model="CONFIG.computer_control.grounding_model" />
          </ConfigItem>
          <ConfigItem name="定位模型 API 地址" description="定位模型的 API 地址">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，使用 scratchpad Model 网关</span>
            <InputText v-else v-model="CONFIG.computer_control.grounding_url" />
          </ConfigItem>
          <ConfigItem name="定位模型 API 密钥" description="定位模型的 API 密钥">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需输入</span>
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
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
            <InputText v-else v-model="CONFIG.voice_realtime.asr_model" />
          </ConfigItem>
          <template v-if="!isLoggedIn">
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
            <span class="authed-hint">&#10003; 已登陆，无需输入</span>
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
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
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
          <template v-if="!isLoggedIn">
            <ConfigItem name="服务端口" description="用于语音合成的本地服务端口">
              <InputNumber v-model="CONFIG.tts.port" :min="1000" :max="65535" show-buttons />
            </ConfigItem>
            <ConfigItem name="API 密钥" description="语音合成模型的 API 密钥">
              <InputText v-model="CONFIG.tts.api_key" />
            </ConfigItem>
          </template>
          <ConfigItem v-else name="API 密钥">
            <span class="authed-hint">&#10003; 已登陆，无需输入</span>
          </ConfigItem>
        </div>
      </ConfigGroup>

      <!-- 嵌入模型 -->
      <ConfigGroup value="embedding" header="嵌入模型">
        <div class="grid gap-4">
          <ConfigItem name="模型名称" description="用于向量嵌入的模型">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需填写</span>
            <InputText v-else v-model="CONFIG.embedding.model" />
          </ConfigItem>
          <ConfigItem name="API 地址" description="嵌入模型的 API 地址（留空使用主模型地址）">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，使用 scratchpad Model 网关</span>
            <InputText v-else v-model="CONFIG.embedding.api_base" />
          </ConfigItem>
          <ConfigItem name="API 密钥" description="嵌入模型的 API 密钥（留空使用主模型密钥）">
            <span v-if="isLoggedIn" class="authed-hint">&#10003; 已登陆，无需输入</span>
            <InputText v-else v-model="CONFIG.embedding.api_key" type="password" />
          </ConfigItem>
        </div>
      </ConfigGroup>
    </Accordion>
  </BoxContainer>
</template>

<style scoped>
.authed-hint {
  color: #4ade80;
  font-size: 0.875rem;
  font-weight: 500;
}
</style>
