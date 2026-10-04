// Tab 管理域：重命名 / 关闭 / 切换时清未读+懒加载（卷190-B3：从 MessageView.vue setup 纯搬移）
import type { ChatTab } from '@/utils/session'
import { nextTick, ref, watch } from 'vue'
import API from '@/api/core'
import { activeTabId, agentContacts, isAgentLoading, loadAgentMessages, tabs } from '@/utils/session'

export function useChatTabs(onTabSwitched: () => void) {
  const renamingTabId = ref<string | null>(null)
  const renameValue = ref('')
  const renameInputRef = ref<HTMLInputElement | null>(null)

  /** 关闭 tab（不杀进程，只从 tabs 移除） */
  function closeTab(tab: ChatTab) {
    const idx = tabs.value.findIndex(t => t.id === tab.id)
    if (idx > 0) {
      tabs.value.splice(idx, 1)
    }
    if (activeTabId.value === tab.id) {
      activeTabId.value = 'lumo'
    }
  }

  function startRename(tab: ChatTab) {
    if (tab.type !== 'agent' || !tab.instanceId)
      return
    renamingTabId.value = tab.id
    renameValue.value = tab.name
    nextTick(() => renameInputRef.value?.focus())
  }

  function finishRename(tab: ChatTab) {
    if (tab.type !== 'agent' || !tab.instanceId) {
      renamingTabId.value = null
      return
    }
    const newName = renameValue.value.trim()
    if (newName && newName !== tab.name) {
      const oldName = tab.name
      tab.name = newName
      // 同步消息中的 sender
      for (const msg of tab.messages) {
        if (msg.sender === oldName)
          msg.sender = newName
      }
      // 同步到后端 + 通讯录
      API.renameAgent(tab.instanceId, newName).then(() => {
        const contact = agentContacts.value.find(a => a.id === tab.instanceId)
        if (contact)
          contact.name = newName
      }).catch(() => {})
    }
    renamingTabId.value = null
  }

  // 切换 tab 时清除未读 + 懒加载历史
  watch(activeTabId, async (id) => {
    const tab = tabs.value.find(t => t.id === id)
    if (tab) {
      tab.unread = 0
      // 切换到干员 tab 时强制触发一次后端历史/唤醒，避免只命中本地缓存导致进程未拉起
      if (tab.type === 'agent' && tab.instanceId && !isAgentLoading(tab.instanceId)) {
        await loadAgentMessages(tab, { forceRefresh: true })
        onTabSwitched()
      }
    }
  })

  return {
    renamingTabId,
    renameValue,
    renameInputRef,
    closeTab,
    startRename,
    finishRename,
  }
}
