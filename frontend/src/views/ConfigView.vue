<script setup lang="ts">
/**
 * 设置页壳（卷181-D：ConfigView 拆分为「壳 + 四子页」）。
 *
 * 壳职责：tab 切换（含子路由可寻址 /config/<tab>）+ 设置内搜索（跨 tab 扫描）+ agent 入口。
 * 业务内容分到 src/views/config/{ModelTab,MemoryTab,AudioTab}.vue + 通知（NotificationSettingsPanel）。
 */
import { Button, InputText } from 'primevue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import DomainSwitcher from '@/components/DomainSwitcher.vue'
import NotificationSettingsPanel from '@/components/NotificationSettingsPanel.vue'
import AudioTab from '@/views/config/AudioTab.vue'
import MemoryTab from '@/views/config/MemoryTab.vue'
import ModelTab from '@/views/config/ModelTab.vue'
import ToolHealthTab from '@/views/config/ToolHealthTab.vue'

// ── Tab 切换（卷181-A：子路由可寻址 /config/<tab>）──
// 'terminal' key 正名为 'audio'（label「音画配置」与 key 的命名漂移一并修掉）；
// 旧链接 ?tab=terminal 由下方重定向兼容。
type TabKey = 'model' | 'memory' | 'audio' | 'notifications' | 'agent' | 'tools'
const TAB_KEYS: TabKey[] = ['model', 'memory', 'audio', 'notifications', 'agent', 'tools']
const route = useRoute()
const router = useRouter()

function resolveTab(): TabKey {
  const raw = String(route.params.tab || route.query.tab || '')
  const mapped = raw === 'terminal' ? 'audio' : raw // 旧 key 兼容（正名前的存量链接）
  return (TAB_KEYS as string[]).includes(mapped) ? (mapped as TabKey) : 'audio'
}

const activeTab = ref<TabKey>(resolveTab())

// 切换即写 URL —— 子页可直达/可分享/可被命令面板索引
watch(activeTab, (t) => {
  if (String(route.params.tab || '') !== t) {
    void router.replace({ path: `/config/${t}` })
  }
})

onMounted(() => {
  // 存量 ?tab=xxx 链接 → 规范化为子路由（含 ?tab=terminal → /config/audio）
  if (route.query.tab || !route.params.tab) {
    void router.replace({ path: `/config/${activeTab.value}` })
  }
})

const tabs: { key: TabKey, label: string }[] = [
  { key: 'model', label: '模型连接' },
  { key: 'memory', label: '记忆连接' },
  { key: 'audio', label: '音画配置' },
  { key: 'notifications', label: '通知设置' },
  { key: 'agent', label: '干员设置' },
  { key: 'tools', label: '工具健康' },
]

// ── 设置内搜索（卷181-B）──
// 实现方式：ConfigItem 携带 data-search-text（name+description+searchKeys 小写拼接），
// 搜索时跨 tab 扫描（v-show 隐藏的 tab 仍在 DOM，天然可搜），当前 tab 内 v-show 过滤，
// 跨 tab 命中以结果列表呈现（标注所属 tab），点击跳子页并高亮。零新增依赖。
const searchQuery = ref('')
interface SearchHit { tab: TabKey, label: string }
const searchHits = ref<SearchHit[]>([])
const searchActive = computed(() => searchQuery.value.trim().length > 0)
let highlightTimer: ReturnType<typeof setTimeout> | null = null

function collectSearchItems(): SearchHit[] {
  const out: SearchHit[] = []
  const seen = new Set<string>()
  for (const tab of TAB_KEYS) {
    const container = document.querySelector(`[data-config-tab="${tab}"]`)
    if (!container)
      continue
    container.querySelectorAll<HTMLElement>('[data-config-item]').forEach((el) => {
      const label = el.querySelector('.font-bold')?.textContent?.trim() || '(未命名项)'
      const text = (el.dataset.searchText || '').toLowerCase()
      const key = `${tab}:${label}`
      if (!seen.has(key))
        out.push({ tab, label })
      // 供 filterCurrentTab 使用：把命中文本挂到元素上
      el.dataset.searchMatch = text
      seen.add(key)
    })
  }
  return out
}

function filterCurrentTab() {
  const q = searchQuery.value.trim().toLowerCase()
  for (const tab of TAB_KEYS) {
    const container = document.querySelector(`[data-config-tab="${tab}"]`)
    if (!container)
      continue
    const isCurrent = tab === activeTab.value
    container.querySelectorAll<HTMLElement>('[data-config-item]').forEach((el) => {
      if (!isCurrent || !q) {
        el.style.display = ''
        return
      }
      el.style.display = (el.dataset.searchMatch || '').includes(q) ? '' : 'none'
    })
  }
}

function runSearch() {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) {
    searchHits.value = []
    filterCurrentTab()
    return
  }
  collectSearchItems()
  const hits: SearchHit[] = []
  for (const tab of TAB_KEYS) {
    const container = document.querySelector(`[data-config-tab="${tab}"]`)
    if (!container)
      continue
    container.querySelectorAll<HTMLElement>('[data-config-item]').forEach((el) => {
      if ((el.dataset.searchMatch || '').includes(q)) {
        const label = el.querySelector('.font-bold')?.textContent?.trim() || '(未命名项)'
        if (!hits.some(h => h.tab === tab && h.label === label))
          hits.push({ tab, label })
      }
    })
  }
  searchHits.value = hits
  filterCurrentTab()
}

const TAB_LABELS: Record<TabKey, string> = {
  model: '模型连接',
  memory: '记忆连接',
  audio: '音画配置',
  notifications: '通知设置',
  agent: '干员设置',
  tools: '工具健康',
}

function clearSearch() {
  searchQuery.value = ''
  searchHits.value = []
  filterCurrentTab()
}

/** 点击命中：切到所属子页 + 滚动定位 + 临时高亮 */
async function gotoHit(hit: SearchHit) {
  activeTab.value = hit.tab
  await nextTick()
  const container = document.querySelector(`[data-config-tab="${hit.tab}"]`)
  const target = Array.from(container?.querySelectorAll<HTMLElement>('[data-config-item]') ?? [])
    .find(el => (el.querySelector('.font-bold')?.textContent?.trim() || '') === hit.label)
  if (!target)
    return
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target.classList.add('config-item-highlight')
  if (highlightTimer)
    clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => target.classList.remove('config-item-highlight'), 2000)
}

watch(searchQuery, () => runSearch())

/** 干员设置入口（卷181-C）：通讯录在聊天页（MessageView 内的 AgentContacts） */
function gotoAgentContacts() {
  void router.push('/chat')
}
</script>

<template>
  <BoxContainer class="text-sm">
    <!-- 设置内搜索（卷181-B）：输入即跨 tab 过滤，命中分组显示所属 tab -->
    <div class="config-search mb-3 px-1">
      <div class="flex items-center gap-2">
        <InputText
          v-model="searchQuery"
          class="config-search-input"
          placeholder="搜索设置项（如：通知 / live2d / api）"
          data-testid="config-search"
        />
        <Button
          v-if="searchActive"
          label="清空"
          severity="secondary"
          text
          size="small"
          @click="clearSearch"
        />
      </div>
      <div v-if="searchActive" class="config-search-results" data-testid="config-search-results">
        <template v-if="searchHits.length">
          <div class="config-search-hint">命中 {{ searchHits.length }} 项（跨 {{ new Set(searchHits.map(h => h.tab)).size }} 个设置页）</div>
          <button
            v-for="hit in searchHits" :key="`${hit.tab}:${hit.label}`"
            class="config-search-hit"
            @click="gotoHit(hit)"
          >
            <span class="hit-label">{{ hit.label }}</span>
            <span class="hit-tab">{{ TAB_LABELS[hit.tab] }}</span>
          </button>
        </template>
        <div v-else class="config-search-empty" data-testid="config-search-empty">
          无匹配「{{ searchQuery }}」
        </div>
      </div>
    </div>

    <!-- Tab 栏 -->
    <div class="flex gap-1 mb-4 px-1">
      <button
        v-for="tab in tabs" :key="tab.key"
        class="tab-btn" :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 模型 Tab -->
    <div v-show="activeTab === 'model'" data-config-tab="model">
      <!-- 领域切换（卷186-B3）：ELN 表单字段 / 文献主键随领域包切换，复用 DomainSwitcher（消费 domainPacks.ts，不新造轮子） -->
      <ConfigGroup value="domain-pack" header="领域包">
        <ConfigItem
          name="领域切换"
          description="切换 ELN 表单字段与文献主键的领域包（材料科研 / 法学），详细说明见 domains/README.md"
          :search-keys="['领域', '领域包', 'domain', 'pack', '切换', 'ELN', '表单']"
        >
          <DomainSwitcher />
        </ConfigItem>
      </ConfigGroup>
      <ModelTab />
    </div>

    <!-- 记忆 Tab -->
    <div v-show="activeTab === 'memory'" data-config-tab="memory">
      <MemoryTab />
    </div>

    <!-- 音画 Tab -->
    <div v-show="activeTab === 'audio'" data-config-tab="audio">
      <AudioTab />
    </div>

    <!-- 通知 Tab -->
    <div v-show="activeTab === 'notifications'" data-config-tab="notifications">
      <NotificationSettingsPanel />
    </div>

    <!-- 工具健康（卷189-B）：只读调用画像 + 熔断状态 -->
    <div v-show="activeTab === 'tools'" data-config-tab="tools">
      <ToolHealthTab />
    </div>

    <!-- 干员设置入口（卷181-C）：AgentSettingsDialog 保留弹窗（内容强绑单个 agent 实例，
         与全局设置重叠低），此处提供统一入口 + 跳转 -->
    <div v-show="activeTab === 'agent'" data-config-tab="agent">
      <ConfigGroup value="agent-entry" header="干员设置">
        <div class="grid gap-4">
          <ConfigItem
            name="干员配置入口"
            description="每个干员的模型/人设/工具设置在其通讯录卡片上唤起（弹窗），设置页提供统一入口"
            :search-keys="['agent', 'ganyuan', '干员', '通讯录', '设置', 'agent 设置']"
          >
            <div class="flex items-center gap-3">
              <Button label="打开干员通讯录" size="small" @click="gotoAgentContacts" />
            </div>
          </ConfigItem>
          <ConfigItem
            name="内置干员说明"
            description="内置干员（builtin）的人设与工具面由能力清单管理，不可直接改；自定义干员可在此配置"
            :search-keys="['内置干员', 'builtin', '自定义干员']"
          >
            <span class="text-sm text-gray-500">—</span>
          </ConfigItem>
        </div>
      </ConfigGroup>
    </div>
  </BoxContainer>
</template>

<style scoped>
/* 设置内搜索（卷181-B） */
.config-search-input {
  width: 100%;
}
.config-search-results {
  margin-top: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.5rem;
  max-height: 16rem;
  overflow-y: auto;
  padding: 0.25rem;
}
.config-search-hint {
  font-size: 0.75rem;
  opacity: 0.65;
  padding: 0.25rem 0.5rem;
}
.config-search-hit {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
}
.config-search-hit:hover {
  background: rgba(79, 140, 255, 0.15);
}
.config-search-hit .hit-tab {
  font-size: 0.7rem;
  opacity: 0.6;
  white-space: nowrap;
}
.config-search-empty {
  padding: 0.5rem;
  font-size: 0.8125rem;
  opacity: 0.7;
}
/* 命中项临时高亮（gotoHit 后 2s 移除） */
:deep(.config-item-highlight) {
  outline: 2px solid #4f8cff;
  outline-offset: 2px;
  border-radius: 0.375rem;
  background: rgba(79, 140, 255, 0.08);
}

.tab-btn {
  flex: 1;
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
</style>
