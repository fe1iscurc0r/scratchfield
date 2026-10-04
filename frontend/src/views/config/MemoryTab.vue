<script setup lang="ts">
/**
 * 记忆连接设置页（卷181-D：从 ConfigView 巨石搬移，纯搬移不重构逻辑）。
 *
 * 状态来源：CONFIG（@/utils/config 全局 ref）+ useAuth（云端模式判定）；
 * 原先定义在 ConfigView 的 memoryStats/testResult/isCloudMode/similarityPercent/
 * testConnection/accordionMemory 随块搬入本组件（这些符号只服务本块）。
 */
import type { MemoryStats } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import API from '@/api/core'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { cloudUser, isLoggedIn } from '@/composables/useAuth'
import { CONFIG } from '@/utils/config'

const accordionMemory = useStorage('accordion-config-memory', [])
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

// 搬移自带首测（原 ConfigView onMounted 会无条件调用 testConnection）
onMounted(() => {
  testConnection()
})
</script>

<template>
  <Accordion :value="accordionMemory" class="pb-8" multiple>
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
        <!-- 云端模式 -->
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
            :search-keys="['五元组', 'quintuple', '记忆数量']"
          >
            <span class="text-white/70">{{ memoryStats.totalQuintuples ?? 0 }}</span>
          </ConfigItem>
        </template>
        <!-- 本地模式 -->
        <template v-else>
          <ConfigItem name="连接地址" description="Neo4j 数据库连接 URI" :search-keys="['neo4j', '数据库地址', 'uri']">
            <InputText v-model="CONFIG.grag.neo4j_uri" placeholder="neo4j://127.0.0.1:7687" />
          </ConfigItem>
          <ConfigItem name="用户名" description="Neo4j 数据库用户名" :search-keys="['neo4j', '账号']">
            <InputText v-model="CONFIG.grag.neo4j_user" placeholder="neo4j" />
          </ConfigItem>
          <ConfigItem name="密码" description="Neo4j 数据库密码" :search-keys="['neo4j', '口令']">
            <InputText v-model="CONFIG.grag.neo4j_password" placeholder="••••••••" />
          </ConfigItem>
        </template>
        <Divider class="m-1!" />
        <ConfigItem name="知识图谱" :search-keys="['图谱', 'graph', '知识']">
          <label class="flex items-center gap-4">
            启用
            <ToggleSwitch v-model="CONFIG.grag.enabled" size="small" />
          </label>
        </ConfigItem>
        <ConfigItem name="自动提取" description="自动从对话中提取五元组知识" :search-keys="['提取', '自动', '五元组']">
          <ToggleSwitch v-model="CONFIG.grag.auto_extract" />
        </ConfigItem>
        <ConfigItem name="上下文长度" description="最近对话窗口大小" :search-keys="['上下文', '窗口', 'context']">
          <InputNumber v-model="CONFIG.grag.context_length" :min="1" :max="20" show-buttons />
        </ConfigItem>
        <ConfigItem name="相似度阈值" description="RAG 知识检索匹配阈值" :search-keys="['相似度', '阈值', 'rag', '匹配']">
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
  </Accordion>
</template>
