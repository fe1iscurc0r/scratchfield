<script setup lang="ts">
import type { McpService, SkillCatalogItem } from '@/api/core'
import { Dialog } from 'primevue'
import { computed, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import EmptyState from '@/components/EmptyState.vue'
import McpAddDialog from '@/components/McpAddDialog.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import SkillAddDialog from '@/components/SkillAddDialog.vue'
import { feedback } from '@/utils/feedback'

const mcpServices = ref<McpService[]>([])
const mcpLoading = ref(true)
const showMcpDialog = ref(false)
const editingMcp = ref<{
  name: string
  displayName: string
  description: string
  config: Record<string, any>
  scope: 'public'
} | null>(null)

const publicMcpServices = computed(() => mcpServices.value.filter(service => service.scope === 'public'))
const mcpEnabledCount = computed(() => publicMcpServices.value.filter(service => service.enabled).length)
const mcpTotalCount = computed(() => publicMcpServices.value.length)

async function loadMcpServices() {
  mcpLoading.value = true
  try {
    const res = await API.getMcpServices()
    mcpServices.value = (res.services ?? []).filter(service => service.scope === 'public')
  }
  catch {
    mcpServices.value = []
  }
  finally {
    mcpLoading.value = false
  }
}

// ---- 装配策略（按族白名单 / 按 tier 关闭；agent 级开关在各服务行） ----
interface AssemblyVocabItem { key: string; label: string; desc: string }
const showAssembly = ref(false)
const assemblyLoading = ref(false)
const assemblyPolicy = ref<Record<string, any>>({})
const assemblyVocab = ref<{ families: AssemblyVocabItem[], tiers: AssemblyVocabItem[] }>({ families: [], tiers: [] })
const assemblyAgents = ref<{ name: string, enabled: boolean, disabled_reason?: string }[]>([])

const familyWhitelist = computed(() => assemblyPolicy.value.enabled_families as string[] | undefined)
const disabledTiers = computed(() => assemblyPolicy.value.disable_tiers as string[] | undefined)

/** 白名单缺省 = 全启用；全部勾选等价于「不限」，写回时用 null 清除。 */
function familyOn(key: string): boolean {
  return !familyWhitelist.value || familyWhitelist.value.includes(key)
}
function tierOff(key: string): boolean {
  return !!disabledTiers.value?.includes(key)
}
const assemblySummary = computed(() => {
  const total = assemblyAgents.value.length
  if (!total)
    return ''
  const off = assemblyAgents.value.filter(a => !a.enabled).length
  return off === 0 ? `全部 ${total} 项启用` : `关闭 ${off} / ${total} 项`
})

async function loadAssembly() {
  assemblyLoading.value = true
  try {
    const res = await API.getMcpAssembly()
    assemblyPolicy.value = res.policy ?? {}
    assemblyVocab.value = res.vocabulary ?? { families: [], tiers: [] }
    assemblyAgents.value = res.agents ?? []
  }
  catch {
    assemblyPolicy.value = {}
  }
  finally {
    assemblyLoading.value = false
  }
}

async function toggleFamily(key: string) {
  const all = assemblyVocab.value.families.map(f => f.key)
  const cur = familyWhitelist.value ? [...familyWhitelist.value] : all
  const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
  const body = next.length === all.length ? { enabled_families: null } : { enabled_families: next }
  try {
    await API.updateMcpAssembly(body)
    await loadAssembly()
    await loadMcpServices()
  }
  catch (e: any) {
    feedback.error(e?.response?.data?.detail || '更新装配策略失败')
  }
}

async function toggleTier(key: string) {
  const cur = disabledTiers.value ? [...disabledTiers.value] : []
  const next = cur.includes(key) ? cur.filter(k => k !== key) : [...cur, key]
  try {
    await API.updateMcpAssembly({ disable_tiers: next })
    await loadAssembly()
    await loadMcpServices()
  }
  catch (e: any) {
    feedback.error(e?.response?.data?.detail || '更新装配策略失败')
  }
}

function openAddMcp() {
  editingMcp.value = null
  showMcpDialog.value = true
}

function openEditMcp(service: McpService) {
  if (service.source === 'builtin')
    return
  editingMcp.value = {
    name: service.name,
    displayName: service.displayName || service.name,
    description: service.description || '',
    config: service.config || {},
    scope: 'public',
  }
  showMcpDialog.value = true
}

async function onMcpConfirm(data:
  | { mode: 'hub', name: string, source: string }
  | { mode: 'cache', name: string, displayName: string, description: string, config: Record<string, any> }
  | { mode: 'custom', name: string, displayName: string, description: string, config: Record<string, any>, scope: 'public' | 'private' }) {
  try {
    if (data.mode === 'hub') {
      await API.installHubMcp({
        name: data.name,
        scope: 'public',
        source: data.source,
      })
    }
    else if (data.mode === 'cache') {
      await API.importMcpConfig({
        name: data.name,
        config: data.config,
        displayName: data.displayName,
        description: data.description,
        scope: 'public',
      })
    }
    else if (editingMcp.value) {
      await API.updateMcpService(data.name, {
        config: data.config,
        displayName: data.displayName,
        description: data.description,
      })
    }
    else {
      await API.importMcpConfig({
        name: data.name,
        config: data.config,
        displayName: data.displayName,
        description: data.description,
        scope: 'public',
      })
    }
    showMcpDialog.value = false
    feedback.success('已保存')
    await loadMcpServices()
  }
  catch (error: any) {
    feedback.error('操作失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}

async function toggleMcpEnabled(service: McpService) {
  if (service.source === 'builtin')
    return
  const nextValue = !service.enabled
  service.enabled = nextValue
  try {
    await API.updateMcpService(service.name, { enabled: nextValue })
  }
  catch {
    service.enabled = !nextValue
  }
}

async function deleteMcp(service: McpService) {
  if (service.source === 'builtin')
    return
  try {
    await API.deleteMcpService(service.name)
    feedback.success('已删除')
    await loadMcpServices()
  }
  catch (error: any) {
    feedback.error('删除失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}

const skillCatalogLoading = ref(true)
const localCacheSkills = ref<SkillCatalogItem[]>([])
const publicSkills = ref<SkillCatalogItem[]>([])
const showSkillDialog = ref(false)

async function loadSkillCatalog() {
  skillCatalogLoading.value = true
  try {
    const res = await API.getSkillCatalog()
    localCacheSkills.value = res.catalog.localCache.skills || []
    publicSkills.value = res.catalog.publicSkills.skills || []
  }
  catch {
    localCacheSkills.value = []
    publicSkills.value = []
  }
  finally {
    skillCatalogLoading.value = false
  }
}

function openSkillDialog() {
  showSkillDialog.value = true
}

async function onSkillConfirm(data:
  | { mode: 'hub', name: string, source: string }
  | { mode: 'cache', name: string, sourceScope: 'cache' | 'public' | 'private', sourceAgentId?: string }
  | { mode: 'custom', name: string, content: string, scope: 'cache' | 'public' | 'private', agentId?: string }) {
  try {
    if (data.mode === 'hub') {
      await API.installHubSkill({
        name: data.name,
        scope: 'public',
        source: data.source,
      })
    }
    else if (data.mode === 'cache') {
      await API.cloneSkill({
        name: data.name,
        sourceScope: data.sourceScope,
        sourceAgentId: data.sourceAgentId,
        targetScope: 'public',
      })
    }
    else {
      await API.importScopedSkill(data)
    }
    showSkillDialog.value = false
    feedback.success('已导入')
    await loadSkillCatalog()
  }
  catch (error: any) {
    feedback.error('导入失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}

async function deleteScopedSkill(skill: SkillCatalogItem) {
  const scope = skill.scope === 'public' ? 'public' : 'cache'
  try {
    await API.deleteSkill(skill.name, scope)
    feedback.success('已删除')
    await loadSkillCatalog()
  }
  catch (error: any) {
    feedback.error('删除失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}

const helpVisible = ref(false)
const activeLibraryTab = ref<'mcp' | 'skill'>('mcp')

const installedSkills = computed(() => {
  const merged = [...publicSkills.value, ...localCacheSkills.value]
  return merged.sort((a, b) => {
    const score = (skill: SkillCatalogItem) => {
      if (skill.source === 'naga-public')
        return 0
      if (skill.source === 'naga-cache')
        return 1
      if (skill.source === 'openclaw-local')
        return 2
      return 3
    }
    const diff = score(a) - score(b)
    if (diff !== 0)
      return diff
    return a.name.localeCompare(b.name, 'zh-Hans-CN')
  })
})

void loadMcpServices()
void loadAssembly()
void loadSkillCatalog()
</script>

<template>
  <BoxContainer class="text-sm">
    <div class="skill-header">
      <div class="skill-header-main">
        <h1 class="skill-title">
          技能工坊
        </h1>
        <button
          type="button"
          class="skill-help-btn"
          aria-label="查看技能工坊说明"
          title="查看技能工坊说明"
          @click="helpVisible = true"
        >
          ?
        </button>
      </div>
      <div class="skill-subtitle">
        在这里管理全局 MCP、Skill，以及按名称快速安装模板。
      </div>
    </div>

    <div class="workshop-grid">
      <section class="workshop-section workshop-section-wide">
        <div class="library-tabs">
          <button
            type="button"
            class="library-tab"
            :class="{ active: activeLibraryTab === 'mcp' }"
            @click="activeLibraryTab = 'mcp'"
          >
            MCP
          </button>
          <button
            type="button"
            class="library-tab"
            :class="{ active: activeLibraryTab === 'skill' }"
            @click="activeLibraryTab = 'skill'"
          >
            Skill
          </button>
        </div>
      </section>

      <section v-if="activeLibraryTab === 'mcp'" class="workshop-section workshop-section-wide">
        <div class="section-head">
          <div>
            <div class="section-title">MCP</div>
            <div class="section-meta">
              通用 MCP。这里管理全局可用的 MCP 服务。已启用 {{ mcpEnabledCount }} / {{ mcpTotalCount }}。
            </div>
          </div>
          <button class="add-btn add-btn-compact" @click="openAddMcp">
            添加 MCP
          </button>
        </div>

        <!-- 装配策略面板：按族白名单 / 按 tier 关闭；agent 级开关在各服务行 -->
        <div class="assembly-panel">
          <button class="assembly-head" @click="showAssembly = !showAssembly">
            <span class="assembly-title">装配策略</span>
            <span v-if="assemblySummary" class="assembly-summary">{{ assemblySummary }}</span>
            <svg
              class="assembly-caret" :class="{ open: showAssembly }"
              xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            ><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <div v-if="showAssembly" class="assembly-body">
            <div class="assembly-group">
              <div class="assembly-label">按族启用（白名单；全亮 = 不限）</div>
              <div class="assembly-chips">
                <button
                  v-for="f in assemblyVocab.families"
                  :key="f.key"
                  class="assembly-chip"
                  :class="{ on: familyOn(f.key) }"
                  :title="f.desc"
                  @click="toggleFamily(f.key)"
                >
                  {{ f.label }}
                </button>
              </div>
            </div>
            <div class="assembly-group">
              <div class="assembly-label">按 tier 关闭</div>
              <div class="assembly-chips">
                <button
                  v-for="t in assemblyVocab.tiers"
                  :key="t.key"
                  class="assembly-chip tier"
                  :class="{ off: tierOff(t.key) }"
                  :title="t.desc"
                  @click="toggleTier(t.key)"
                >
                  {{ t.label }}
                </button>
              </div>
            </div>
            <div class="assembly-note">
              服务行的开关是按 agent 的显式开关，优先于上述策略；offensive 能力另有入口环境变量闸门（默认关）。
            </div>
          </div>
        </div>

        <SkeletonCard v-if="mcpLoading" :rows="5" />
        <template v-else>
          <div
            v-for="service in publicMcpServices"
            :key="service.name"
            class="mcp-item min-w-0"
            :class="{ 'mcp-disabled': !service.enabled }"
          >
            <div class="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                <button
                  class="mcp-toggle"
                  :class="{ 'mcp-toggle-on': service.enabled, 'mcp-toggle-builtin': service.source === 'builtin' }"
                  :title="service.source === 'builtin' ? '内置服务（前端开关写入装配策略）' : (service.enabled ? '点击禁用' : '点击启用')"
                  @click="toggleMcpEnabled(service)"
                >
                  <span class="mcp-toggle-dot" />
                </button>
                <div class="min-w-0 flex-1 overflow-hidden">
                  <div class="flex items-center gap-1.5">
                    <span class="font-bold text-sm text-white truncate">{{ service.displayName }}</span>
                    <span v-if="service.source === 'builtin'" class="mcp-badge builtin">内置</span>
                    <span v-else class="mcp-badge external">通用</span>
                    <span
                      v-if="service.requirements?.missing?.length"
                      class="mcp-badge req-missing"
                      :title="'缺依赖：' + service.requirements.missing.join('、')"
                    >缺 {{ service.requirements.missing.length }} 项</span>
                    <span
                      v-if="service.requirements?.optional_missing?.length"
                      class="mcp-badge req-optional"
                      :title="'缺软依赖（功能降级但可用）：' + service.requirements.optional_missing.join('、')"
                    >降 {{ service.requirements.optional_missing.length }} 项</span>
                  </div>
                  <div v-if="service.description" class="text-xs op-40 truncate mt-0.5">
                    {{ service.description }}
                  </div>
                </div>
            </div>
            <div v-if="service.source !== 'builtin'" class="flex items-center gap-1 shrink-0 ml-2">
              <button class="mcp-action-btn" title="编辑" @click="openEditMcp(service)">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
              </button>
              <button class="mcp-action-btn mcp-action-delete" title="删除" @click="deleteMcp(service)">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" /><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" /></svg>
              </button>
            </div>
          </div>
          <EmptyState
            v-if="publicMcpServices.length === 0"
            icon="🔌"
            title="还没有 MCP"
            description="添加一个 MCP 服务，把外部工具接进陆墨"
            action-label="添加 MCP"
            @action="openAddMcp"
          />
        </template>
      </section>

      <section v-else class="workshop-section workshop-section-wide">
        <div class="section-head">
          <div>
            <div class="section-title">Skill</div>
            <div class="section-meta">
              通用 Skill。这里管理全局可用的 Skill。启用后，陆墨和多个干员都可以共用。
            </div>
          </div>
          <div class="section-actions">
            <button class="add-btn add-btn-compact" @click="openSkillDialog()">
              添加 Skill
            </button>
          </div>
        </div>

        <SkeletonCard v-if="skillCatalogLoading" :rows="5" />
        <template v-else>
          <div
            v-for="skill in installedSkills"
            :key="`${skill.source}:${skill.name}`"
            class="skill-item min-w-0"
          >
            <div class="flex-1 min-w-0 overflow-hidden">
              <div class="flex items-center gap-2">
                <div class="font-bold text-sm text-white truncate">{{ skill.name }}</div>
              </div>
              <div class="text-xs op-50 truncate">
                {{ skill.description || '暂无描述' }}
              </div>
            </div>
            <button class="skill-action-btn skill-action-delete" title="删除 Skill" @click="deleteScopedSkill(skill)">
              删除
            </button>
          </div>
          <EmptyState
            icon="🛠"
            title="还没有安装技能"
            description="从市场安装，或添加本地 SKILL.md"
            action-label="去市场看看"
            @action="$router.push('/market')"
          />
        </template>
      </section>
    </div>

    <McpAddDialog
      :visible="showMcpDialog"
      :edit-data="editingMcp"
      fixed-scope="public"
      hub-enabled
      title="添加通用 MCP"
      @confirm="onMcpConfirm"
      @cancel="showMcpDialog = false"
    />
    <SkillAddDialog
      :visible="showSkillDialog"
      fixed-scope="public"
      hub-enabled
      title="添加 Skill"
      @confirm="onSkillConfirm"
      @cancel="showSkillDialog = false"
    />

    <Dialog
      v-model:visible="helpVisible"
      modal
      header="技能工坊说明"
      :style="{ width: 'min(720px, 92vw)' }"
    >
      <div class="skill-help">
        <section>
          <h4>通用 MCP</h4>
          <p>MCP 可以理解为“外接工具服务”，比如搜索、抓取、系统能力之类的接口。这里管理全局可用的 MCP，启用后陆墨和多个干员都可以共用。</p>
        </section>
        <section>
          <h4>通用 Skill</h4>
          <p>Skill 可以理解为“能力模板 / 做事方法”，它决定模型在特定任务里该怎么组织步骤和使用工具。这里管理全局可用的 Skill，启用后陆墨和多个干员都可以共用。</p>
        </section>
        <section>
          <h4>添加方式</h4>
          <p>点击“添加 MCP”或“添加 Skill”后，可以在弹窗里切换“从 Hub 下载”或“自定义导入”。当前 Skill 下载源支持腾讯 SkillHub 和 ClawHub。</p>
        </section>
      </div>
    </Dialog>
  </BoxContainer>
</template>

<style scoped>
.skill-header {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-bottom: 1rem;
}

.skill-header-main {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.skill-title {
  margin: 0;
  color: rgba(255, 255, 255, 0.92);
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.skill-subtitle {
  color: rgba(255, 255, 255, 0.42);
  font-size: 0.76rem;
  line-height: 1.55;
}

.workshop-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  padding-bottom: 2rem;
}

.workshop-section {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-width: 0;
  padding: 0.9rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.workshop-section-wide {
  grid-column: 1 / -1;
}

.library-tabs {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  align-self: flex-start;
}

.library-tab {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.48);
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.45rem 0.9rem;
  border-radius: 999px;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.library-tab.active {
  background: rgba(212, 175, 55, 0.14);
  color: rgba(248, 222, 159, 0.96);
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.section-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.94rem;
  font-weight: 700;
  line-height: 1.3;
}

.section-meta {
  margin-top: 0.2rem;
  color: rgba(255, 255, 255, 0.42);
  font-size: 0.74rem;
  line-height: 1.45;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-shrink: 0;
}

.skill-help-btn {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.28);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(212, 175, 55, 0.88);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.skill-help-btn:hover {
  border-color: rgba(212, 175, 55, 0.52);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(248, 222, 159, 0.96);
}

.skill-help {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.84rem;
  line-height: 1.7;
}

.skill-help h4 {
  margin: 0 0 0.25rem;
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.9rem;
  font-weight: 700;
}

.skill-help p {
  margin: 0;
}

.mcp-summary {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.35);
  padding: 0 0.25rem;
}

.mcp-item {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.mcp-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.mcp-item.mcp-disabled {
  opacity: 0.45;
}

.mcp-toggle {
  position: relative;
  width: 28px;
  height: 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.15);
  border: none;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  padding: 0;
}

.mcp-toggle-on {
  background: rgba(212, 175, 55, 0.7);
}

.mcp-toggle-builtin {
  opacity: 0.5;
  cursor: default;
}

.mcp-toggle-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  transition: transform 0.2s;
}

.mcp-toggle-on .mcp-toggle-dot {
  transform: translateX(12px);
}

.mcp-badge {
  font-size: 0.6rem;
  padding: 0 0.3rem;
  border-radius: 3px;
  line-height: 1.4;
  font-weight: 600;
  flex-shrink: 0;
}

.mcp-badge.builtin {
  color: rgba(74, 222, 128, 0.8);
  background: rgba(74, 222, 128, 0.1);
}

.mcp-badge.external {
  color: rgba(96, 165, 250, 0.8);
  background: rgba(96, 165, 250, 0.1);
}

/* 依赖预检（requires）缺项徽标：暖色警示，hover 见 title 明细 */
.mcp-badge.req-missing {
  color: rgba(251, 146, 60, 0.9);
  background: rgba(251, 146, 60, 0.12);
  cursor: help;
}

/* 软依赖缺失（degraded）：功能降级但可用，用中性灰与必须缺失区分 */
.mcp-badge.req-optional {
  color: rgba(148, 163, 184, 0.9);
  background: rgba(148, 163, 184, 0.14);
  cursor: help;
}

/* 装配策略面板：族白名单 + tier 关闭 */
.assembly-panel {
  margin-bottom: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.03);
}

.assembly-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.assembly-title {
  font-weight: 600;
  font-size: 13px;
}

.assembly-summary {
  font-size: 12px;
  opacity: 0.55;
}

.assembly-caret {
  margin-left: auto;
  transition: transform 0.15s ease;
  opacity: 0.6;
}

.assembly-caret.open {
  transform: rotate(180deg);
}

.assembly-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 12px 12px;
}

.assembly-label {
  font-size: 12px;
  opacity: 0.55;
  margin-bottom: 6px;
}

.assembly-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.assembly-chip {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: none;
  color: inherit;
  font-size: 12px;
  opacity: 0.5;
  cursor: pointer;
  transition: all 0.12s ease;
}

.assembly-chip:hover {
  opacity: 0.8;
}

/* 族白名单：亮 = 启用 */
.assembly-chip.on {
  opacity: 1;
  border-color: rgba(129, 199, 132, 0.55);
  background: rgba(129, 199, 132, 0.12);
}

/* tier：暗红 = 已关闭 */
.assembly-chip.tier.off {
  opacity: 1;
  border-color: rgba(239, 108, 108, 0.55);
  background: rgba(239, 108, 108, 0.12);
}

.assembly-note {
  font-size: 11px;
  opacity: 0.45;
  line-height: 1.5;
}

.mcp-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.mcp-action-btn:hover {
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.08);
}

.mcp-action-delete:hover {
  color: #e85d5d;
  background: rgba(232, 93, 93, 0.1);
}

.skill-item,
.hub-card {
  display: flex;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.skill-item:hover,
.hub-card:hover {
  background: rgba(255, 255, 255, 0.08);
}

.skill-placeholder,
.hub-endpoint-card {
  padding: 0.75rem 0.85rem;
  border-radius: 8px;
  border: 1px dashed rgba(212, 175, 55, 0.28);
  background: rgba(212, 175, 55, 0.04);
  font-size: 0.76rem;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.6;
}

.hub-endpoint-title {
  font-weight: 700;
  color: rgba(255, 255, 255, 0.82);
  margin-bottom: 0.35rem;
}

.hub-endpoint-line code {
  font-size: 0.72rem;
}

.hub-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
}

.hub-card {
  flex-direction: column;
  align-items: stretch;
  gap: 0.7rem;
}

.hub-card-title {
  font-size: 0.9rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
}

.hub-note {
  font-size: 0.74rem;
  color: rgba(255, 255, 255, 0.45);
  line-height: 1.55;
}

.hub-feedback {
  padding: 0.6rem 0.7rem;
  border-radius: 8px;
  font-size: 0.74rem;
  line-height: 1.5;
}

.hub-feedback.success {
  color: rgba(74, 222, 128, 0.95);
  background: rgba(74, 222, 128, 0.08);
}

.hub-feedback.error {
  color: rgba(255, 141, 141, 0.95);
  background: rgba(255, 141, 141, 0.08);
}

.skill-action-btn {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.46);
  font-size: 0.74rem;
  cursor: pointer;
  transition: color 0.15s ease;
}

.skill-action-delete:hover {
  color: #ff8d8d;
}

.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px dashed rgba(212, 175, 55, 0.35);
  border-radius: 8px;
  background: transparent;
  color: rgba(212, 175, 55, 0.76);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.add-btn:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.7);
  color: rgba(212, 175, 55, 1);
  background: rgba(212, 175, 55, 0.06);
}

.add-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.add-btn-compact {
  width: auto;
  min-width: 96px;
  padding-inline: 0.9rem;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .workshop-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .section-head {
    flex-direction: column;
  }

  .section-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .hub-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
