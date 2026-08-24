<script setup lang="ts">
import type { AgentEngine, AgentSettings, CharacterTemplate } from '@/api/core'
import type { AgentContact } from '@/utils/session'
import { Button, InputText, Select } from 'primevue'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import API from '@/api/core'
import back from '@/assets/icons/back.png'
import AgentSettingsDialog from '@/components/AgentSettingsDialog.vue'
import { useTravel } from '@/travel/composables/useTravel'
import { agentContacts, loadAgentContacts, nextAgentNumber, openAgentTab, tabs } from '@/utils/session'

const backIcon = back
const router = useRouter()

const collapsed = ref(false)
const adding = ref(false)
const createDialogVisible = ref(false)
const createName = ref('')
const createCharacterTemplate = ref('')
const createEngine = ref<AgentEngine>('openclaw')
const createError = ref('')
const characterTemplates = ref<CharacterTemplate[]>([])
const engineOptions: Array<{ label: string, value: AgentEngine, description: string }> = [
  { label: 'OpenClaw', value: 'openclaw', description: '适合浏览器、网页探索和复杂工具链。' },
  { label: 'scratchpad Core', value: 'lumo-core', description: '使用 scratchpad 现有后端能力，后续会提炼成按干员隔离的独立运行时。' },
]

// 右键菜单
const contextMenu = ref<{ show: boolean, x: number, y: number, agentId: string, agentName: string }>({
  show: false,
  x: 0,
  y: 0,
  agentId: '',
  agentName: '',
})

const settingsVisible = ref(false)
const selectedAgent = ref<AgentContact | null>(null)
const { activeSessionByAgentId, viewTravelForAgent } = useTravel()
const exploringIds = computed(() => new Set(Object.keys(activeSessionByAgentId.value)))

function handleClick(agent: { id: string, name: string, running: boolean, created_at?: number, builtin?: boolean }) {
  openAgentTab(agent)
}

function openTravelContext(agentId: string) {
  const session = viewTravelForAgent(agentId)
  if (!session)
    return
  router.push('/forum/quota')
}

function handleContextMenu(e: MouseEvent, agent: { id: string, name: string, builtin?: boolean }) {
  if (agent.builtin)
    return
  e.preventDefault()
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, agentId: agent.id, agentName: agent.name }
}

function closeContextMenu() {
  contextMenu.value.show = false
}

function openSettings(agent: { id: string, name: string, running: boolean, created_at?: number, builtin?: boolean, engine?: AgentEngine, characterTemplate?: string }) {
  selectedAgent.value = { ...agent }
  settingsVisible.value = true
}

function openSettingsFromMenu() {
  const contact = agentContacts.value.find(item => item.id === contextMenu.value.agentId)
  closeContextMenu()
  if (contact) {
    openSettings(contact)
  }
}

async function handleSettingsUpdated(settings: AgentSettings) {
  const contact = agentContacts.value.find(item => item.id === settings.id)
  const oldName = contact?.name || selectedAgent.value?.name

  if (contact) {
    contact.name = settings.name
    contact.engine = settings.engine
    contact.characterTemplate = settings.characterTemplate
  }

  if (selectedAgent.value?.id === settings.id) {
    selectedAgent.value = {
      ...selectedAgent.value,
      name: settings.name,
      engine: settings.engine,
      characterTemplate: settings.characterTemplate,
    }
  }

  const tab = tabs.value.find(item => item.instanceId === settings.id)
  if (tab) {
    tab.name = settings.name
    tab.engine = settings.engine
    tab.characterTemplate = settings.characterTemplate
    if (oldName && oldName !== settings.name) {
      for (const msg of tab.messages) {
        if (msg.sender === oldName)
          msg.sender = settings.name
      }
    }
  }

  await loadAgentContacts()
  settingsVisible.value = false
}

async function deleteAgent(agentId?: string) {
  const id = agentId || contextMenu.value.agentId
  if (!id)
    return
  closeContextMenu()
  try {
    await API.deleteAgent(id)
    // 从 tabs 中移除对应 tab
    const idx = tabs.value.findIndex(t => t.instanceId === id)
    if (idx >= 0)
      tabs.value.splice(idx, 1)
    await loadAgentContacts()
  }
  catch { /* ignore */ }
}

async function addAgent() {
  createError.value = ''
  createName.value = `干员${nextAgentNumber()}`
  if (!characterTemplates.value.length) {
    try {
      const res = await API.listCharacterTemplates()
      characterTemplates.value = res.characters || []
    }
    catch { /* ignore */ }
  }
  createCharacterTemplate.value = characterTemplates.value.find(item => item.active)?.name || characterTemplates.value[0]?.name || ''
  createEngine.value = 'openclaw'
  createDialogVisible.value = true
}

async function confirmAddAgent() {
  if (adding.value)
    return
  const name = createName.value.trim()
  if (!name) {
    createError.value = '请输入干员名称'
    return
  }
  if (!createCharacterTemplate.value) {
    createError.value = '请选择角色模板'
    return
  }

  adding.value = true
  createError.value = ''
  try {
    await API.createAgent(name, createCharacterTemplate.value, createEngine.value)
    createDialogVisible.value = false
    await loadAgentContacts()
  }
  catch (e: any) {
    createError.value = e?.response?.data?.detail || e?.message || '创建干员失败'
  }
  finally {
    adding.value = false
  }
}

// 初始加载
loadAgentContacts()
void API.listCharacterTemplates().then((res) => {
  characterTemplates.value = res.characters || []
}).catch(() => {})
</script>

<template>
  <div class="contacts-drawer" :class="{ collapsed }">
    <!-- 顶部栏：返回按钮 + 折叠按钮 -->
    <div class="top-bar">
      <img :src="backIcon" class="back-btn" alt="返回" @click="$router.back()">
      <button class="toggle-btn" :title="collapsed ? '展开通讯录' : '收起通讯录'" @click="collapsed = !collapsed">
        <svg
          xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
        >
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
    </div>

    <!-- 角色列表（box 样式边框） -->
    <div v-show="!collapsed" class="contacts-body box">
      <div class="contacts-header">
        <span>干员通讯录</span>
        <button class="header-refresh-btn" title="刷新干员通讯录" @click.stop="loadAgentContacts">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5" />
          </svg>
        </button>
      </div>

      <div class="contacts-items">
        <div
          v-for="agent in agentContacts" :key="agent.id"
          class="contact-item"
          @click="handleClick(agent)"
          @contextmenu="handleContextMenu($event, agent)"
        >
          <div class="contact-avatar">
            {{ agent.name.charAt(0) }}
          </div>
          <div class="contact-name">
            {{ agent.name }}
          </div>
          <button
            v-if="exploringIds.has(agent.id)"
            class="travel-badge"
            title="查看该干员的探索上下文"
            @click.stop="openTravelContext(agent.id)"
          >
            探索中
          </button>
          <div v-if="agent.builtin" class="builtin-badge">
            默认
          </div>
          <div class="engine-badge" :class="agent.engine === 'lumo-core' ? 'engine-core' : 'engine-openclaw'">
            {{ agent.engine === 'lumo-core' ? 'NC' : 'OC' }}
          </div>
          <div v-if="agent.running" class="running-dot" title="运行中" />
          <button class="settings-icon" title="干员设置" @click.stop="openSettings(agent)">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 8.92 4.6H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.36.48.82.82 1.42 1H21a2 2 0 1 1 0 4h-.18a1.65 1.65 0 0 0-1.42 1Z" /></svg>
          </button>
          <button v-if="!agent.builtin" class="delete-icon" title="删除干员" @click.stop="deleteAgent(agent.id)">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
          </button>
        </div>

        <div v-if="agentContacts.length === 0" class="empty-hint">
          暂无干员
        </div>
      </div>

      <!-- 底部添加按钮 -->
      <button class="add-btn" :disabled="adding" @click="addAgent">
        + 新建干员
      </button>
    </div>

    <!-- 右键菜单 -->
    <Teleport to="body">
      <div
        v-if="contextMenu.show"
        class="ctx-menu"
        :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }"
      >
        <div class="ctx-item" @click="openSettingsFromMenu">
          设置
        </div>
        <div class="ctx-item ctx-danger" @click="deleteAgent()">
          删除
        </div>
      </div>
      <div v-if="contextMenu.show" class="ctx-overlay" @click="closeContextMenu" />
    </Teleport>

    <Teleport to="body">
      <Transition name="dialog-fade">
        <div v-if="createDialogVisible" class="dialog-overlay" @click.self="createDialogVisible = false">
          <div class="dialog-card">
            <h2 class="dialog-title">
              新建干员
            </h2>
            <div class="dialog-form">
              <label class="dialog-label">干员名称</label>
              <InputText v-model="createName" class="dialog-input" placeholder="例如：干员7" />

              <label class="dialog-label">人格模板</label>
              <Select
                v-model="createCharacterTemplate"
                :options="characterTemplates"
                option-label="name"
                option-value="name"
                class="dialog-input"
                placeholder="选择一个 characters 模板"
                append-to="body"
                :pt="{ overlay: { class: 'agent-select-overlay' } }"
              />
              <div v-if="createCharacterTemplate" class="dialog-hint">
                {{ characterTemplates.find(item => item.name === createCharacterTemplate)?.bio || '该模板将初始化写入干员的 IDENTITY.md。' }}
              </div>
              <div v-else class="dialog-hint">
                创建后会把选中的角色模板写入该干员的 IDENTITY.md，后天发展仍保留在该干员自己的实例目录。
              </div>

              <label class="dialog-label">干员引擎</label>
              <Select
                v-model="createEngine"
                :options="engineOptions"
                option-label="label"
                option-value="value"
                class="dialog-input"
                placeholder="选择干员引擎"
                append-to="body"
                :pt="{ overlay: { class: 'agent-select-overlay' } }"
              />
              <div class="dialog-hint">
                {{ engineOptions.find(item => item.value === createEngine)?.description }}
              </div>

              <div v-if="createError" class="dialog-error">
                {{ createError }}
              </div>
            </div>
            <div class="dialog-actions">
              <Button label="取消" text @click="createDialogVisible = false" />
              <Button label="创建干员" :loading="adding" @click="confirmAddAgent" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <AgentSettingsDialog
      :visible="settingsVisible"
      :agent="selectedAgent"
      @close="settingsVisible = false; selectedAgent = null"
      @updated="handleSettingsUpdated"
    />
  </div>
</template>

<style scoped>
.contacts-drawer {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 170px;
  min-width: 170px;
  transition: width 0.2s ease, min-width 0.2s ease;
  user-select: none;
  margin-right: 8px;
}

.contacts-drawer.collapsed {
  width: 40px;
  min-width: 40px;
}

/* 顶部栏：返回+折叠 */
.top-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-shrink: 0;
}

.back-btn {
  width: var(--nav-back-width, 28px);
  cursor: pointer;
  transition: filter 0.2s ease;
  flex-shrink: 0;
}

.back-btn:hover {
  filter: brightness(1.35);
}

/* 圆形折叠按钮 */
.toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-bottom: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.45);
  cursor: pointer;
  transition: color 0.2s, background 0.2s, border-color 0.2s;
  flex-shrink: 0;
}

.toggle-btn:hover {
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.3);
}

/* 列表区域用 .box 九宫格边框 */
.contacts-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

.contacts-header {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.5px;
}

.header-refresh-btn {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.header-refresh-btn:hover {
  border-color: rgba(212, 175, 55, 0.32);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(212, 175, 55, 0.86);
}

.contacts-items {
  flex: 1;
  overflow-y: auto;
  padding: 2px 4px;
}

/* 每个角色行 */
.contact-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 6px;
  margin: 2px 0;
  border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}

.contact-item:hover {
  background: rgba(255, 255, 255, 0.07);
  border-color: rgba(255, 255, 255, 0.12);
}

.contact-avatar {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.7);
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

.contact-name {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.engine-badge {
  padding: 1px 5px;
  border-radius: 999px;
  font-size: 9px;
  line-height: 1.4;
  font-weight: 700;
  flex-shrink: 0;
}

.travel-badge {
  margin-left: auto;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(66, 185, 131, 0.14);
  color: rgba(163, 230, 187, 0.9);
  font-size: 10px;
  letter-spacing: 0.02em;
}

.builtin-badge {
  padding: 1px 5px;
  border-radius: 999px;
  font-size: 9px;
  line-height: 1.4;
  font-weight: 700;
  flex-shrink: 0;
  color: rgba(212, 175, 55, 0.95);
  background: rgba(212, 175, 55, 0.12);
}

.engine-openclaw {
  color: rgba(96, 165, 250, 0.95);
  background: rgba(96, 165, 250, 0.12);
}

.engine-core {
  color: rgba(74, 222, 128, 0.95);
  background: rgba(74, 222, 128, 0.12);
}

.running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4ade80;
  flex-shrink: 0;
}

.settings-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.25);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
  flex-shrink: 0;
}

.contact-item:hover .settings-icon {
  opacity: 1;
}

.settings-icon:hover {
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.1);
}

.delete-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.25);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
  flex-shrink: 0;
}

.contact-item:hover .delete-icon {
  opacity: 1;
}

.delete-icon:hover {
  color: #e74c3c;
  background: rgba(231, 76, 60, 0.12);
}

.empty-hint {
  color: rgba(255, 255, 255, 0.25);
  font-size: 11px;
  text-align: center;
  padding: 16px 0;
}

.add-btn {
  margin: 4px 8px 6px;
  padding: 5px 0;
  border: 1px dashed rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  background: transparent;
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}

.add-btn:hover:not(:disabled) {
  color: rgba(255, 255, 255, 0.7);
  border-color: rgba(255, 255, 255, 0.3);
}

.add-btn:disabled {
  opacity: 0.4;
  cursor: wait;
}

/* 右键菜单 */
.ctx-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
}

.ctx-menu {
  position: fixed;
  z-index: 1000;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  padding: 4px;
  backdrop-filter: blur(12px);
  min-width: 100px;
}

.ctx-item {
  padding: 6px 12px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}

.ctx-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.ctx-danger:hover {
  color: #e74c3c;
}

.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(6px);
}

.dialog-card {
  width: min(440px, calc(100vw - 32px));
  padding: 20px 22px;
  border: 1px solid rgba(212, 175, 55, 0.45);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 60px rgba(0, 0, 0, 0.5), 0 0 40px rgba(212, 175, 55, 0.1);
}

.dialog-title {
  margin: 0 0 14px;
  font-size: 18px;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.92);
  text-align: center;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dialog-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
}

.dialog-input {
  width: 100%;
}

.dialog-hint {
  font-size: 12px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.42);
}

.dialog-error {
  font-size: 12px;
  color: #e85d5d;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.18s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

:global(.agent-select-overlay) {
  z-index: 10050 !important;
}

/* 滚动条 */
.contacts-items::-webkit-scrollbar {
  width: 3px;
}

.contacts-items::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
}
</style>
