// 悬浮窗聊天域：输入/快捷技能/发送/截屏/文件上传/会话历史（卷190-B1：从 FloatingView.vue 纯搬移）
import type { CaptureSource, FloatingState } from '@/electron.d'
import { nextTick, ref } from 'vue'
import API from '@/api/core'
import { CONFIG } from '@/utils/config'
import {
  CURRENT_SESSION_ID,
  MESSAGES,
  newSession,
  newTemporarySession,
  switchSession,
} from '@/utils/session'
import { chatStream } from '@/views/MessageView.vue'

interface ChatDeps {
  floatingState: { readonly value: FloatingState }
  inputRef: { readonly value: HTMLInputElement | null }
  scrollPanelRef: { readonly value: { scrollTop: (v: number) => void } | null }
  fileInputRef: { readonly value: HTMLInputElement | null }
  showCapturePanel: { value: boolean }
  showHistory: { value: boolean }
  fitWindowHeight: () => void
  setupResizeObserver: () => void
}

export function useFloatingChat(deps: ChatDeps) {
  const { floatingState, inputRef, scrollPanelRef, fileInputRef, showCapturePanel, showHistory, fitWindowHeight, setupResizeObserver } = deps

  const input = ref('')

  // 聊天功能
  function scrollToBottom() {
    scrollPanelRef.value?.scrollTop(Infinity)
  }

  // 快捷技能按钮定义（name 对应 skills/ 目录下的技能名称）
  const QUICK_SKILLS = [
    { label: '帮我翻译', name: 'translate' },
    { label: '帮我概括', name: 'summarize' },
    { label: '真假鉴别', name: 'verify-authenticity' },
    { label: '帮我想想', name: 'solve' },
  ]

  // 当前选中的技能索引，-1 表示未选中
  const activeSkillIndex = ref(-1)

  function handleQuickSkill(index: number) {
    // 切换选中状态：再次点击取消选中
    activeSkillIndex.value = activeSkillIndex.value === index ? -1 : index
    nextTick(() => {
      inputRef.value?.focus()
    })
  }

  // 窗口截屏功能（showCapturePanel 由壳声明：fitWindowHeight 高度拟合需要读取）
  const captureSources = ref<CaptureSource[]>([])
  const loadingCapture = ref(false)
  const capturePermissionDenied = ref(false)
  const pendingImages = ref<string[]>([]) // 待发送的截图 dataURL 列表

  async function handleCapture() {
    if (showCapturePanel.value) {
      closeCapturePanel()
      return
    }
    // 如果是紧凑态，先展开到完整态
    if (floatingState.value === 'compact') {
      window.electronAPI?.floating.expandToFull()
    }
    loadingCapture.value = true
    showCapturePanel.value = true
    capturePermissionDenied.value = false
    try {
      const result = await window.electronAPI?.capture.getSources()
      if (result && 'permission' in result) {
        // macOS 屏幕录制权限未授予
        capturePermissionDenied.value = true
        captureSources.value = []
      }
      else {
        const sources = (result as Array<{ id: string, name: string, thumbnail: string, appIcon: string | null }>) ?? []
        captureSources.value = sources.filter(s => !s.name.includes('scratchpad'))
      }
    }
    catch {
      captureSources.value = []
    }
    loadingCapture.value = false
    await nextTick()
    fitWindowHeight()
  }

  async function closeCapturePanel() {
    showCapturePanel.value = false
    await nextTick()
    await nextTick()
    fitWindowHeight()
  }

  function openScreenSettings() {
    window.electronAPI?.capture.openScreenSettings()
  }

  async function selectCaptureSource(source: CaptureSource) {
    showCapturePanel.value = false
    // 以高分辨率重新截取选中窗口，追加到待发送列表
    const imageData = await window.electronAPI?.capture.captureWindow(source.id)
    if (!imageData)
      return
    pendingImages.value.push(imageData)
    await nextTick()
    inputRef.value?.focus()
    fitWindowHeight()
  }

  function removePendingImage(index: number) {
    pendingImages.value.splice(index, 1)
    nextTick().then(fitWindowHeight)
  }

  function sendMessage() {
    if (!input.value.trim() && pendingImages.value.length === 0)
      return

    // 如果当前是紧凑态，先请求扩展到完整态
    if (floatingState.value === 'compact') {
      window.electronAPI?.floating.expandToFull()
    }

    // 如果选中了技能，通过 skill 参数传给后端，由后端注入完整指令
    let skillName: string | undefined
    if (activeSkillIndex.value >= 0) {
      skillName = QUICK_SKILLS[activeSkillIndex.value]?.name
      activeSkillIndex.value = -1
    }

    const images = pendingImages.value.length > 0 ? [...pendingImages.value] : undefined
    chatStream(input.value || '请分析这些截图中的内容', { skill: skillName, images })
    input.value = ''
    pendingImages.value = []
    nextTick().then(scrollToBottom)
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      sendMessage()
    }
  }

  // 文件上传
  let suppressBlur = false // 文件选择器打开期间抑制失焦收缩

  function triggerFileUpload() {
    suppressBlur = true
    // 用户取消文件选择器时 change 事件可能不触发，通过 focus 兜底恢复
    const onFocus = () => {
      setTimeout(() => {
        suppressBlur = false
      }, 300)
      window.removeEventListener('focus', onFocus)
    }
    window.addEventListener('focus', onFocus)
    fileInputRef.value?.click()
  }

  async function handleFileUpload(event: Event) {
    suppressBlur = false
    const target = event.target as HTMLInputElement
    const file = target.files?.[0]
    if (!file)
      return

    // 如果是紧凑态，先展开到完整态
    if (floatingState.value === 'compact') {
      window.electronAPI?.floating.expandToFull()
    }

    const ext = file.name.split('.').pop()?.toLowerCase()
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
    const parseableExts = ['docx', 'xlsx', 'txt', 'csv', 'md']

    if (ext && imageExts.includes(ext)) {
      // 图片文件：读取为 dataURL 加入 pendingImages，走 VLM
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === 'string') {
          pendingImages.value.push(reader.result)
          nextTick().then(() => {
            inputRef.value?.focus()
            fitWindowHeight()
          })
        }
      }
      reader.readAsDataURL(file)
    }
    else if (ext && parseableExts.includes(ext)) {
      // 可解析文件：解析后发送内容到对话
      MESSAGES.value.push({ role: 'system', content: `正在解析文件: ${file.name}...` })
      try {
        const result = await API.parseDocument(file)
        const msg = MESSAGES.value.at(-1)!
        const truncNote = result.truncated ? '（内容过长，已截断）' : ''
        msg.content = `文件解析完成: ${file.name}${truncNote}`
        chatStream(`以下是文件「${file.name}」的内容：\n\n${result.content}\n\n请分析这个文件的内容。`)
        nextTick().then(scrollToBottom)
      }
      catch (err: any) {
        const msg = MESSAGES.value.at(-1)!
        msg.content = `文件解析失败: ${err?.response?.data?.detail || err.message}`
      }
    }
    else {
      // 其他格式：二进制上传
      MESSAGES.value.push({ role: 'system', content: `正在上传文件: ${file.name}...` })
      try {
        const result = await API.uploadDocument(file)
        const msg = MESSAGES.value.at(-1)!
        msg.content = `文件上传成功: ${file.name}`
        if (result.filePath) {
          chatStream(`请分析我刚上传的文件「${file.name}」，文件完整路径: ${result.filePath}`)
        }
      }
      catch (err: any) {
        const msg = MESSAGES.value.at(-1)!
        msg.content = `文件上传失败: ${err.message}`
      }
    }
    target.value = ''
  }

  async function handleNewSession() {
    newSession()
    await nextTick()
    await nextTick()
    fitWindowHeight()
  }

  async function handleNewTemporarySession() {
    newTemporarySession()
    await nextTick()
    await nextTick()
    fitWindowHeight()
  }

  // ─── 会话历史 ──────────────────────────
  const sessions = ref<Array<{
    sessionId: string
    createdAt: string
    lastActiveAt: string
    conversationRounds: number
    temporary: boolean
  }>>([])
  const loadingSessions = ref(false)

  async function fetchSessions() {
    loadingSessions.value = true
    try {
      const res = await API.getSessions()
      sessions.value = res.sessions ?? []
    }
    catch {
      sessions.value = []
    }
    loadingSessions.value = false
    // 会话列表加载完成后刷新窗口高度（列表条目数量影响面板高度）
    await nextTick()
    fitWindowHeight()
  }

  // showHistory 由壳声明（fitWindowHeight 读取）；此处记录是否因打开历史面板而从紧凑态展开
  let _expandedForHistory = false

  function toggleHistory() {
    if (!showHistory.value) {
      // 打开历史面板
      if (floatingState.value === 'compact') {
        _expandedForHistory = true
        window.electronAPI?.floating.expandToFull()
      }
      showHistory.value = true
      fetchSessions() // fetchSessions 内部加载完成后统一调用 fitWindowHeight
    }
    else {
      closeHistory()
    }
  }

  // 关闭历史面板，通过 fitHeight 自适应窗口高度
  async function closeHistory() {
    showHistory.value = false
    _expandedForHistory = false
    await nextTick()
    await nextTick()
    fitWindowHeight()
  }

  async function handleSwitchSession(id: string) {
    await switchSession(id)
    showHistory.value = false
    // 等待 Vue 渲染完消息 DOM 后再计算高度
    await nextTick()
    await nextTick()
    scrollToBottom()
    setupResizeObserver()
    fitWindowHeight()
  }

  async function handleDeleteSession(id: string) {
    try {
      await API.deleteSession(id)
      sessions.value = sessions.value.filter(s => s.sessionId !== id)
      if (CURRENT_SESSION_ID.value === id) {
        newSession()
      }
      await nextTick()
      fitWindowHeight()
    }
    catch { /* ignore */ }
  }

  return {
    input,
    scrollToBottom,
    /** 供壳的失焦收缩判断读取（文件选择器打开期间抑制收缩） */
    getSuppressBlur: () => suppressBlur,
    QUICK_SKILLS,
    activeSkillIndex,
    handleQuickSkill,
    // 截屏
    showCapturePanel,
    captureSources,
    loadingCapture,
    capturePermissionDenied,
    pendingImages,
    handleCapture,
    closeCapturePanel,
    openScreenSettings,
    selectCaptureSource,
    removePendingImage,
    // 发送/键盘
    sendMessage,
    handleKeydown,
    // 文件上传
    triggerFileUpload,
    handleFileUpload,
    // 会话
    handleNewSession,
    handleNewTemporarySession,
    sessions,
    loadingSessions,
    showHistory,
    toggleHistory,
    closeHistory,
    handleSwitchSession,
    handleDeleteSession,
  }
}

// CONFIG 由壳消费（标题栏 ai_name），此处 re-export 保持引用路径集中
export { CONFIG }
