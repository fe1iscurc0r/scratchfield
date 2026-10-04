<script setup lang="ts">
import type { GraphSummary, MemoryStats, Quintuple } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, Select, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref, watch } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import EmptyState from '@/components/EmptyState.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import { cloudUser, isLoggedIn } from '@/composables/useAuth'
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

// ══════════════════════════════════════════════════════════
// 记忆浏览（卷148 任务C）——配置之外的记忆管理面
// ══════════════════════════════════════════════════════════

const browseTab = ref<'table' | 'timeline' | 'trust'>('table')

// ── 分页 + 过滤 + 搜索（走任务A 新参数） ──
const PAGE_SIZE = 20
const pageOffset = ref(0)
const pageRows = ref<Quintuple[]>([])
const pageTotal = ref(0)
const pageLoading = ref(false)
const pageError = ref('')
const filterType = ref('')
const browseQuery = ref('')
const orderBy = ref<'degree' | 'time'>('degree')

const typeOptions = ref<Array<{ label: string, value: string }>>([])
const summary = ref<GraphSummary | null>(null)

const pageIndex = computed(() => Math.floor(pageOffset.value / PAGE_SIZE) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil(pageTotal.value / PAGE_SIZE)))
const canPrev = computed(() => pageOffset.value > 0)
const canNext = computed(() => pageOffset.value + PAGE_SIZE < pageTotal.value)

async function loadTypeOptions() {
  try {
    const s = await API.getGraphSummary(10)
    summary.value = s
    typeOptions.value = [
      { label: '全部类型', value: '' },
      ...s.subject_types.slice(0, 30).map(t => ({ label: `${t.type} (${t.count})`, value: t.type })),
    ]
  }
  catch {
    // 后端未升级时退化为「全部类型」
    typeOptions.value = [{ label: '全部类型', value: '' }]
  }
}

async function loadPage() {
  pageLoading.value = true
  pageError.value = ''
  try {
    const res = await API.getQuintuples({
      offset: pageOffset.value,
      limit: PAGE_SIZE,
      entityType: filterType.value || undefined,
      q: browseQuery.value.trim() || undefined,
      orderBy: orderBy.value,
      withDegree: true,
    })
    pageRows.value = res.quintuples ?? []
    pageTotal.value = res.total ?? pageRows.value.length
  }
  catch (e: any) {
    pageError.value = e.message || '加载失败'
    pageRows.value = []
    pageTotal.value = 0
  }
  finally {
    pageLoading.value = false
  }
}

function applyFilter() {
  pageOffset.value = 0
  loadPage()
}

function gotoPage(delta: number) {
  const next = pageOffset.value + delta * PAGE_SIZE
  if (next < 0)
    return
  pageOffset.value = next
  loadPage()
}

// ── 时间线：按 time 排序取最近一批，做「陆墨最近记住的东西」回放 ──
const timelineRows = ref<Quintuple[]>([])
const timelineLoading = ref(false)

async function loadTimeline() {
  timelineLoading.value = true
  try {
    const res = await API.getQuintuples({ offset: 0, limit: 50, orderBy: 'time', withDegree: true })
    timelineRows.value = res.quintuples ?? []
  }
  catch {
    timelineRows.value = []
  }
  finally {
    timelineLoading.value = false
  }
}

// ── 信任面板：「它记住了我什么」 ──
const topEntities = computed(() => summary.value?.top_entities ?? [])
const topPredicates = computed(() => summary.value?.predicate_distribution ?? [])

// 删除能力探测：后端目前无 delete 端点（已核实 summer_memory 无 delete_quintuples
// 实现、apiserver/routes/extensions.py 只有 GET /memory/quintuples），故只读 + TODO。
const DELETE_SUPPORTED = false

function onDelete(_row: Quintuple) {
  // TODO(后端·报沈遥): 需要 DELETE /memory/quintuples（按 subject/predicate/object 三元定位）
  // 与 summer_memory/reversible.py 的 forget_entity / _apply_inverse 打通后再接真实删除。
}

// 切换 tab 时按需拉数据（避免进页面就打三个请求）
watch(browseTab, (t) => {
  if (t === 'timeline' && timelineRows.value.length === 0)
    loadTimeline()
})

onMounted(async () => {
  testConnection()
  await loadTypeOptions()
  await loadPage()
})
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" class="pb-8" multiple>
      <!-- 记忆浏览（卷148 任务C：配置之外的记忆管理面） -->
      <ConfigGroup value="browse">
        <template #header>
          <div class="w-full flex justify-between items-center -my-1.5">
            <span>记忆浏览</span>
            <span v-if="pageTotal > 0" class="text-xs text-white/40">共 {{ pageTotal }} 条</span>
          </div>
        </template>

        <!-- 三个子页签 -->
        <div class="flex gap-1.5 mb-3">
          <button
            v-for="tab in ([
              { k: 'table', label: '五元组表格' },
              { k: 'timeline', label: '时间线' },
              { k: 'trust', label: '它记住了我什么' },
            ] as const)"
            :key="tab.k"
            type="button"
            class="px-2.5 py-1 rounded text-xs transition"
            :class="browseTab === tab.k ? 'bg-[#2a4a7a] text-white' : 'bg-white/5 hover:bg-white/10 text-white/60'"
            @click="browseTab = tab.k"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- ① 五元组表格 -->
        <template v-if="browseTab === 'table'">
          <div class="flex gap-2 mb-2 flex-wrap">
            <Select
              v-model="filterType"
              :options="typeOptions"
              option-label="label"
              option-value="value"
              class="!w-44"
              @change="applyFilter"
            />
            <Select
              v-model="orderBy"
              :options="[
                { label: '按度数', value: 'degree' },
                { label: '按时间', value: 'time' },
              ]"
              option-label="label"
              option-value="value"
              class="!w-32"
              @change="applyFilter"
            />
            <InputText v-model="browseQuery" placeholder="搜索关键词..." class="flex-1 min-w-40" @keyup.enter="applyFilter" />
            <Button label="查询" size="small" @click="applyFilter" />
          </div>

          <!-- 卷150：错误态走统一 EmptyState（带重试），加载中走骨架 -->
          <EmptyState
            v-if="pageError"
            error
            title="记忆加载失败"
            :description="pageError"
            action-label="重试"
            @action="loadPage"
          />
          <div v-else-if="pageLoading" class="rounded border border-white/10">
            <SkeletonCard variant="list" :rows="8" />
          </div>
          <EmptyState
            v-else-if="pageTotal === 0"
            icon="🧠"
            title="还没有记忆"
            description="对话产生的五元组会自动沉淀到这里"
          />

          <div v-else class="overflow-x-auto rounded border border-white/10">
            <table class="w-full text-xs">
              <thead>
                <tr class="bg-white/5 text-white/50">
                  <th class="text-left px-2 py-1.5 font-medium">主体</th>
                  <th class="text-left px-2 py-1.5 font-medium">主体类型</th>
                  <th class="text-left px-2 py-1.5 font-medium">关系</th>
                  <th class="text-left px-2 py-1.5 font-medium">客体</th>
                  <th class="text-left px-2 py-1.5 font-medium">客体类型</th>
                  <th class="text-right px-2 py-1.5 font-medium">度数</th>
                  <th class="text-right px-2 py-1.5 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(r, i) in pageRows"
                  :key="i"
                  class="border-t border-white/5 hover:bg-white/5 transition"
                >
                  <td class="px-2 py-1.5 text-white/85">{{ r.subject }}</td>
                  <td class="px-2 py-1.5 text-white/45">{{ r.subjectType }}</td>
                  <td class="px-2 py-1.5 text-[#7fb3e8]">{{ r.predicate }}</td>
                  <td class="px-2 py-1.5 text-white/85">{{ r.object }}</td>
                  <td class="px-2 py-1.5 text-white/45">{{ r.objectType }}</td>
                  <td class="px-2 py-1.5 text-right text-white/50">{{ r.degree ?? '-' }}</td>
                  <td class="px-2 py-1.5 text-right">
                    <button
                      type="button"
                      class="text-white/25 cursor-not-allowed"
                      :title="DELETE_SUPPORTED ? '删除这条记忆' : '后端暂无删除接口（TODO·报沈遥）：需要 DELETE /memory/quintuples'"
                      :disabled="!DELETE_SUPPORTED"
                      @click="onDelete(r)"
                    >
                      删除
                    </button>
                  </td>
                </tr>
                <tr v-if="!pageLoading && pageRows.length === 0">
                  <td colspan="7" class="px-2 py-6 text-center text-white/35">
                    {{ pageError ? '加载失败' : '没有匹配的记忆' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="flex items-center justify-between mt-2 text-xs text-white/50">
            <span>{{ pageLoading ? '加载中...' : `第 ${pageIndex} / ${pageCount} 页` }}</span>
            <div class="flex gap-1.5">
              <Button label="上一页" size="small" severity="secondary" :disabled="!canPrev || pageLoading" @click="gotoPage(-1)" />
              <Button label="下一页" size="small" severity="secondary" :disabled="!canNext || pageLoading" @click="gotoPage(1)" />
            </div>
          </div>
        </template>

        <!-- ② 时间线 -->
        <template v-else-if="browseTab === 'timeline'">
          <div v-if="timelineLoading" class="text-xs text-white/40 py-4 text-center">
            加载中...
          </div>
          <div v-else-if="timelineRows.length === 0" class="text-xs text-white/40 py-4 text-center">
            暂无按时间排序的记忆（后端 order_by=time 返回空）
          </div>
          <ol v-else class="relative border-l border-white/10 ml-2 pl-4">
            <li v-for="(r, i) in timelineRows" :key="i" class="mb-3 last:mb-0">
              <span class="absolute -left-[3px] mt-1.5 inline-block w-1.5 h-1.5 rounded-full bg-[#4fc3f7]" />
              <div class="text-xs text-white/80">
                <span class="text-white/95">{{ r.subject }}</span>
                <span class="text-[#7fb3e8] mx-1">{{ r.predicate }}</span>
                <span class="text-white/95">{{ r.object }}</span>
              </div>
              <div class="text-[10px] text-white/35 mt-0.5">
                {{ r.subjectType }} → {{ r.objectType }}
              </div>
            </li>
          </ol>
        </template>

        <!-- ③ 它记住了我什么（信任面板） -->
        <template v-else>
          <div class="grid grid-cols-2 gap-3 mb-3 text-center">
            <div class="rounded border border-white/10 bg-white/5 py-2">
              <div class="text-lg font-bold text-white/90">{{ pageTotal || summary?.total_quintuples || 0 }}</div>
              <div class="text-[10px] text-white/40 mt-0.5">记忆五元组</div>
            </div>
            <div class="rounded border border-white/10 bg-white/5 py-2">
              <div class="text-lg font-bold text-white/90">{{ summary?.total_entities ?? 0 }}</div>
              <div class="text-[10px] text-white/40 mt-0.5">关联实体</div>
            </div>
          </div>

          <div class="text-xs text-white/50 mb-1.5">最常出现的实体（连接最多）</div>
          <div class="flex flex-wrap gap-1.5 mb-3">
            <span
              v-for="e in topEntities"
              :key="e.id"
              class="px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-[11px] text-white/70"
              :title="`类型 ${e.type} · 度数 ${e.degree}`"
            >
              {{ e.id }}<span class="text-white/30 ml-1">{{ e.degree }}</span>
            </span>
            <span v-if="topEntities.length === 0" class="text-[11px] text-white/30">
              暂无数据
            </span>
          </div>

          <div class="text-xs text-white/50 mb-1.5">它最常建立的关系</div>
          <div class="space-y-1">
            <div
              v-for="p in topPredicates.slice(0, 8)"
              :key="p.predicate"
              class="flex items-center gap-2 text-[11px]"
            >
              <span class="text-white/70 w-24 truncate">{{ p.predicate }}</span>
              <div class="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                <div
                  class="h-full rounded-full bg-[#4fc3f7]/60"
                  :style="{ width: `${Math.max(2, (p.count / (topPredicates[0]?.count || 1)) * 100)}%` }"
                />
              </div>
              <span class="text-white/35 w-8 text-right">{{ p.count }}</span>
            </div>
            <div v-if="topPredicates.length === 0" class="text-[11px] text-white/30">
              暂无数据
            </div>
          </div>

          <Divider class="m-2!" />
          <p class="text-[10px] text-white/30 leading-relaxed">
            这份面板展示的是长期记忆里最突出的实体与关系。记忆的删除能力仍在建设中
            （后端暂无 DELETE 接口，见「五元组表格」中的删除按钮提示）。
          </p>
        </template>
      </ConfigGroup>

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
