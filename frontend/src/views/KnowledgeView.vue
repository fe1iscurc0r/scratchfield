<script setup lang="ts">
/**
 * 知识库 · MatChat 内嵌页
 *
 * 页面结构（左右分栏）：
 *   左侧 = Electron BrowserView 的“占位区”（DOM 里只是一个空 div，真正的 MatChat 页面由主进程
 *          的 BrowserView 盖在它上面）；Web 环境下显示降级提示。
 *   右侧 = 本地知识库面板（搜索 / 列表 / 删除 / QA 确认编辑区）。
 *
 * 核心流程：
 *   1) onMounted 时 attach BrowserView，并监听窗口/分栏变化驱动 setBounds
 *   2) 用户在 MatChat 对话后，点击“保存当前问答”→ extractLastQA 提取 → doIngest 入库 RAG
 *   3) 悬浮态切换时自动 detach/attach（悬浮态窗口太窄放不下 MatChat）
 */
import { useRouter } from 'vue-router'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useToast } from 'primevue/usetoast'
import API from '@/api/core'
import backIcon from '@/assets/icons/back.png'
import brainIcon from '@/assets/icons/brain.png'

// 保存流程的状态机：idle→extracting→saving→success/error
type SaveStatus = 'idle' | 'extracting' | 'saving' | 'success' | 'error'

// 知识库文档元信息（与后端 ragList 返回结构一致）
interface DocMeta {
  docId: string
  title: string
  tags: string[]
  source?: string
  chunkCount: number
  createdAt: string
  preview: string
}

// 一对问答（从 MatChat DOM 提取的最小单元）
interface QaPair {
  q: string
  a: string
}

const toast = useToast()
const router = useRouter()
// 是否在 Electron 桌面端（决定 BrowserView 能否使用）
const isElectron = !!window.electronAPI
// 给模板暴露全局 window 的引用，避免被当成 this.window 的 TS 误报
const WIN = window as any

// ===== refs =====
const placeholder = ref<HTMLDivElement | null>(null) // 左侧占位 div 的引用，用于测量真实尺寸
const searchKw = ref('') // 搜索关键字
const filterSource = ref<string>('') // 来源筛选
const docs = ref<DocMeta[]>([]) // 知识库文档列表
const totalDocs = ref(0) // 文档总数
const loading = ref(false) // 列表加载中
const editableQ = ref('') // 确认编辑区的问题（可手动改）
const editableA = ref('') // 确认编辑区的回答（可手动改）
const saveStatus = ref<SaveStatus>('idle') // 保存流程状态
const saveError = ref<string | null>(null) // 保存失败的错误信息
const lastDocId = ref<string | null>(null) // 最近一次入库成功的 docId
const splitterRatio = ref(0.58) // 左右分栏比例（左侧占比）
const placeholderWidth = ref(0) // 占位 div 实测宽（调试/扩展用）
const placeholderHeight = ref(0) // 占位 div 实测高
const currentUrl = ref<string>('https://ai.matchat.cn/chat') // MatChat 当前 URL
const isWebEnv = !isElectron // Web 环境标志（控制降级提示）

// 【响应式窗口尺寸】window.innerWidth/Height 本身不是 Vue 响应式数据，
// 直接在 computed/watch 里读它无法触发依赖收集。这里用 ref 镜像，在 resize 时同步更新，
// 使 scheduleBoundsUpdate 能正确响应窗口缩放。
const winW = ref(window.innerWidth)
const winH = ref(window.innerHeight)

// ===== 悬浮态自动卸载（悬浮态宽度不够 MatChat 用） =====
let unsubFloating: (() => void) | null = null
let unsubUrl: (() => void) | null = null
let unsubLoadError: (() => void) | null = null
let floating = false // 当前是否处于悬浮态

// ===== BV bounds 计算 =====
// 直接从 placeholder div 的 getBoundingClientRect() 获取精确位置，
// 不再用固定常量估算，彻底解决适配问题。
function getBoundsFromPlaceholder() {
  if (!placeholder.value)
    return null
  const rect = placeholder.value.getBoundingClientRect()
  // getBoundingClientRect 返回相对于 viewport 的坐标，
  // 在 Electron 中与 BrowserView bounds 坐标系一致（都相对于主窗口左上角）
  return {
    x: Math.round(rect.left),
    y: Math.round(rect.top),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
  }
}

// 触发 bounds 更新（rAF 节流，避免高频 resize/setter 抖动）
let raf = 0
function scheduleBoundsUpdate() {
  if (raf)
    cancelAnimationFrame(raf)
  raf = requestAnimationFrame(() => {
    raf = 0
    const bounds = getBoundsFromPlaceholder()
    if (bounds && bounds.width > 0 && bounds.height > 0)
      window.electronAPI?.matchat.setBounds(bounds)
  })
}

// 分栏比例变化 或 窗口尺寸变化 → 重算并下发 bounds
watch([splitterRatio, winW, winH], scheduleBoundsUpdate)

// resize 监听器的注销函数（在 onMounted 内赋值，onBeforeUnmount 内调用）
let cleanupResize: (() => void) | null = null

// ===== 生命周期 =====
onMounted(async () => {
  loadDocs()
  if (!isElectron)
    return

  // 监听 URL 变化（顶栏显示当前地址）
  unsubUrl = window.electronAPI!.matchat.onUrlChange((u) => {
    currentUrl.value = u
  })
  unsubLoadError = window.electronAPI!.matchat.onLoadError((err) => {
    toast.add({ severity: 'warn', summary: 'MatChat 加载失败', detail: String(err).slice(0, 120), life: 5000 })
  })

  // 悬浮态自动 detach BrowserView（悬浮态没有空间）
  unsubFloating = window.electronAPI!.floating.onStateChange(async (state) => {
    const wasFloating = floating
    floating = state !== 'classic'
    if (floating && !wasFloating) {
      // 进入悬浮态：摘除 BrowserView
      try { await window.electronAPI!.matchat.detach() }
      catch (_) { /* noop */ }
      toast.add({
        severity: 'info',
        summary: '已切换到悬浮态',
        detail: 'MatChat 内嵌已临时收起，请展开主窗口后恢复',
        life: 5000,
      })
    }
    else if (!floating && wasFloating && router.currentRoute.value.path === '/knowledge') {
      // 退出悬浮态且回到本页：重新 attach
      try {
        await nextTick()
        const bounds = getBoundsFromPlaceholder()
        if (bounds)
          await window.electronAPI!.matchat.attach(bounds)
      }
      catch (_) { /* noop */ }
    }
  })

  const st = await window.electronAPI!.floating.getState()
  floating = st !== 'classic'
  if (floating)
    return

  await nextTick()
  // 如果 placeholder 有真实尺寸（组件渲染后），优先用 placeholder 宽度驱动 bounds 逻辑
  const measurePlaceholder = () => {
    if (placeholder.value) {
      const rect = placeholder.value.getBoundingClientRect()
      placeholderWidth.value = rect.width
      placeholderHeight.value = rect.height
    }
  }
  measurePlaceholder()
  // 【修复】统一的 resize 处理：同步响应式窗口尺寸 + 测量占位 div + 下发新 bounds。
  // 旧版只注册了 measurePlaceholder（不触发 setBounds），且 onBeforeUnmount 误删 scheduleBoundsUpdate，
  // 导致窗口缩放时 BrowserView 尺寸不更新 + measurePlaceholder 监听器泄漏。现统一为 onResize 一处注册/注销。
  const onResize = () => {
    winW.value = window.innerWidth
    winH.value = window.innerHeight
    measurePlaceholder()
    scheduleBoundsUpdate()
  }
  window.addEventListener('resize', onResize)
  // 把注销函数挂到 onBeforeUnmount 能访问到的闭包变量上
  cleanupResize = () => window.removeEventListener('resize', onResize)
  try {
    const bounds = getBoundsFromPlaceholder()
    if (bounds)
      await window.electronAPI!.matchat.attach(bounds)
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: 'MatChat 内嵌初始化失败', detail: String(e?.message || e), life: 6000 })
  }
})

onBeforeUnmount(async () => {
  // 解绑所有 IPC 事件监听
  unsubFloating?.()
  unsubUrl?.()
  unsubLoadError?.()
  // 取消可能挂起的 rAF
  if (raf)
    cancelAnimationFrame(raf)
  // 【修复】注销 resize 监听器（旧版移除了一个从未注册的函数，导致 measurePlaceholder 泄漏）
  cleanupResize?.()
  cleanupResize = null
  // 离开页面且非悬浮态时摘除 BrowserView
  if (isElectron && !floating) {
    try {
      await window.electronAPI!.matchat.detach()
    }
    catch (_) { /* noop */ }
  }
})

// ===== 知识库列表 =====
/** 拉取本地知识库文档列表（带关键字 + 来源过滤） */
async function loadDocs() {
  loading.value = true
  try {
    const r = await API.ragList({
      keyword: searchKw.value || undefined,
      source: filterSource.value || undefined,
      limit: 100,
      offset: 0,
    })
    docs.value = (r.documents as any[]) || []
    totalDocs.value = r.total || 0
  }
  catch (e: any) {
    toast.add({
      severity: 'error',
      summary: '加载本地知识库失败',
      detail: String(e?.message || e).slice(0, 150),
      life: 6000,
    })
    docs.value = []
  }
  finally {
    loading.value = false
  }
}

// 搜索关键字防抖（300ms），避免每次按键都打后端
let searchTimer = 0
watch(searchKw, () => {
  if (searchTimer)
    clearTimeout(searchTimer)
  searchTimer = window.setTimeout(loadDocs, 300)
})
// 来源切换立即重查
watch(filterSource, loadDocs)

// ===== 一键提取 + 入库 =====
/**
 * 从 MatChat 提取最近 N 轮问答并入库。
 * 流程：extractLastQA → 展示到最后一条到确认区 → 直接 doIngest 入库（用户可在确认区改后再存）
 * @param pairs 要提取的问答对数量
 */
async function extractAndSave(pairs: number = 1) {
  if (!isElectron) {
    toast.add({ severity: 'warn', summary: '仅桌面端可用', detail: '当前为 Web 环境，MatChat 内嵌需在桌面端使用', life: 4000 })
    return
  }
  saveStatus.value = 'extracting'
  saveError.value = null
  try {
    const res = await window.electronAPI!.matchat.extractLastQA(pairs)
    if (!res.ok) {
      saveStatus.value = 'error'
      saveError.value = `提取失败：${res.error || '未知错误'}`
      return
    }
    // 调试模式：提取脚本返回了 DOM 候选信息而非 QA 对
    if (res.data && !Array.isArray(res.data) && res.data.__debug) {
      console.error('[MatChat QA 提取] 所有策略失败，DOM 候选信息：', res.data)
      saveStatus.value = 'error'
      saveError.value = `未识别到问答对（所有提取策略失败）。已打印 DOM 调试信息到控制台（F12 查看），共 ${res.data.totalCandidates} 个候选元素`
      return
    }
    const arr: QaPair[] = Array.isArray(res.data) ? res.data : []
    if (!arr.length) {
      saveStatus.value = 'error'
      saveError.value = '未识别到问答对，请确认左侧已有完成的对话'
      return
    }
    // 把最后一条展示到确认区（用户可手动编辑后再点“确认入库”）
    const last = arr[arr.length - 1]!
    editableQ.value = last.q
    editableA.value = last.a
    // 直接提交入库（用户可手动点击确认编辑区再次修改后提交）
    await doIngest(last)
  }
  catch (e: any) {
    saveStatus.value = 'error'
    saveError.value = String(e?.message || e)
  }
}

/**
 * 把一对 Q/A 写入 RAG 知识库。
 * - 标题取问题前 48 字（超长截断加省略号）
 * - content 拼成 `Q: ...\n\nA: ...` 纯文本
 * - tags 标注来源与入库日期，便于后续过滤
 */
async function doIngest(pair: QaPair) {
  if (!pair.q?.trim() || !pair.a?.trim()) {
    saveStatus.value = 'error'
    saveError.value = 'Q / A 不能为空'
    return
  }
  saveStatus.value = 'saving'
  saveError.value = null
  const q = pair.q.trim()
  const a = pair.a.trim()
  const title = q.length > 48 ? q.slice(0, 48) + '…' : q
  const content = `Q: ${q}\n\nA: ${a}\n`
  const today = new Date().toISOString().slice(0, 10)
  const tags = ['来源:MatChat', `入库:${today}`]
  try {
    const r = await API.ragIngestText({
      title,
      content,
      tags,
      source: 'matchat',
      metadata: {
        original_q: q,
        original_a_len: a.length,
        qa_pair: true,
      },
    })
    if (!r.success) {
      saveStatus.value = 'error'
      saveError.value = r.error || '入库失败'
      return
    }
    saveStatus.value = 'success'
    lastDocId.value = r.docId || r.doc?.docId || null
    toast.add({
      severity: 'success',
      summary: '已保存到知识库',
      detail: title,
      life: 3000,
    })
    // 刷新列表，让新文档出现
    await loadDocs()
  }
  catch (e: any) {
    saveStatus.value = 'error'
    saveError.value = String(e?.response?.data?.detail || e?.message || e)
  }
}

/** 删除一篇文档及其全部分块（二次确认） */
async function deleteDoc(d: DocMeta) {
  if (!confirm(`删除「${d.title}」及其所有分块？此操作不可恢复。`))
    return
  try {
    const r = await API.ragDelete(d.docId)
    if (!r.success)
      throw new Error(r.error || '删除失败')
    toast.add({ severity: 'success', summary: '已删除', detail: d.title, life: 2000 })
    await loadDocs()
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: '删除失败', detail: String(e?.message || e), life: 4000 })
  }
}

/** 刷新 MatChat 页面 */
async function reloadPage() {
  if (!isElectron)
    return
  await window.electronAPI!.matchat.reload()
  toast.add({ severity: 'info', summary: '正在刷新 MatChat…', life: 2000 })
}

/** 清除 MatChat 登录态并刷新（用于切账号） */
async function clearAndRelogin() {
  if (!isElectron)
    return
  if (!confirm('将清除 MatChat 登录态并刷新页面，确定？'))
    return
  await window.electronAPI!.matchat.clearStorage()
  toast.add({ severity: 'info', summary: '已清除登录态', detail: '请重新登录', life: 3000 })
}

/** 返回上一页 */
function goBack() {
  router.back()
}

// 状态机 → 中文标签映射（顶栏 / 状态条显示）
const statusLabel = computed(() => ({
  idle: '等待操作',
  extracting: '正在从 MatChat 提取问答对…',
  saving: '正在写入本地知识库…',
  success: '保存成功',
  error: '出错',
}[saveStatus.value]))
</script>

<template>
  <div class="knowledge-root h-full w-full flex flex-col text-#e6e6e6 overflow-hidden bg-[#0f1110]">
    <!-- 顶部工具栏：返回 / 标题 / 环境标识 / 操作按钮 -->
    <div class="h-14 flex items-center px-4 gap-3 border-b border-white/5 shrink-0 select-none">
      <button
        class="rounded-lg px-3 h-9 bg-white/5 hover:bg-white/10 flex items-center gap-2 text-sm"
        @click="goBack"
      >
        <img :src="backIcon" class="w-4 h-4 op-70" alt="">
        返回
      </button>
      <img :src="brainIcon" class="w-6 h-6 op-80 ml-2" alt="">
      <span class="font-serif text-xl tracking-wider">知识库 · MatChat</span>
      <!-- 环境标识：Web 环境红色提示不可用；桌面端绿色显示当前内嵌地址（去 query） -->
      <span
        class="text-xs px-2 py-0.5 rounded ml-2"
        :class="isElectron ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'"
      >
        {{ isWebEnv ? 'Web 环境：MatChat 内嵌不可用' : `内嵌会话：${(String(currentUrl || '').split('?')[0] || '').slice(0, 60)}` }}
      </span>

      <div class="ml-auto flex items-center gap-2 text-sm">
        <!-- 保存流程状态文字 -->
        <span class="text-xs op-50 mr-1">{{ statusLabel }}</span>
        <!-- 刷新 MatChat -->
        <button
          v-if="isElectron"
          class="rounded-lg px-3 h-9 bg-white/5 hover:bg-white/10"
          @click="reloadPage"
        >
          🔄 刷新
        </button>
        <!-- 用系统浏览器打开 MatChat -->
        <button
          v-if="isElectron"
          class="rounded-lg px-3 h-9 bg-white/5 hover:bg-white/10"
          @click="WIN.electronAPI?.matchat.openExternal()"
        >
          🌐 用系统浏览器
        </button>
        <!-- 保存当前 1 轮问答 -->
        <button
          class="rounded-lg px-3 h-9 bg-emerald-700 hover:bg-emerald-600 text-white"
          :class="{ '!bg-slate-500 cursor-wait': saveStatus === 'extracting' || saveStatus === 'saving' }"
          :disabled="saveStatus === 'extracting' || saveStatus === 'saving'"
          @click="extractAndSave(1)"
        >
          💾 保存当前问答
        </button>
        <!-- 保存最近 5 轮问答 -->
        <button
          class="rounded-lg px-3 h-9 bg-emerald-800 hover:bg-emerald-700 text-white"
          :disabled="saveStatus === 'extracting' || saveStatus === 'saving'"
          @click="extractAndSave(5)"
        >
          📚 保存最近 5 轮
        </button>
        <!-- 打开 DevTools 调试 DOM selector -->
        <button
          v-if="isElectron"
          class="rounded-lg px-2 h-9 bg-white/5 hover:bg-white/10 op-70"
          title="打开 DevTools 调试 DOM selector"
          @click="WIN.electronAPI?.matchat.openDevTools()"
        >
          🛠
        </button>
      </div>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="flex-1 flex min-h-0 w-full px-4 pb-4 pt-4 gap-3">
      <!-- 左：BrowserView 占位（不渲染真实 DOM，BV 盖在它之上） -->
      <div
        ref="placeholder"
        class="browser-view-placeholder relative rounded-xl overflow-hidden shrink-0 flex items-center justify-center text-sm text-white/30"
        :style="{
          width: `${Math.round(splitterRatio * 100)}%`,
          backgroundColor: isElectron ? '#1a1a1a' : '#111',
          minWidth: '360px',
        }"
      >
        <!-- Web 环境降级提示：BrowserView 不可用，引导用户开桌面端或新标签页 -->
        <template v-if="isWebEnv">
          <div class="text-center max-w-md p-8">
            <div class="text-3xl mb-4">🌐</div>
            <div class="text-lg font-serif mb-3 text-white/60">
              MatChat 内嵌仅桌面端可用
            </div>
            <div class="text-sm mb-6 text-white/40 leading-relaxed">
              当前为 Web 环境，无法加载 Electron BrowserView。
              <br />请启动桌面端客户端，或
            </div>
            <a
              href="https://ai.matchat.cn/chat"
              target="_blank"
              rel="noreferrer"
              class="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 text-white"
            >
              在新标签页打开 MatChat →
            </a>
          </div>
        </template>
      </div>

      <!-- splitter：可拖拽分栏条。mousedown 时全局监听 mousemove/mouseup，松开时解绑 -->
      <div
        class="w-1 rounded bg-white/8 hover:bg-white/20 cursor-col-resize shrink-0 select-none"
        @mousedown="(e: MouseEvent) => {
          e.preventDefault()
          const startX = e.clientX
          const startRatio = splitterRatio
          const cw = WIN.innerWidth
          // 拖动中：按位移量换算成比例增量，钳到 [0.35, 0.78] 防止过窄/过宽
          const move = (ev: MouseEvent) => {
            const deltaRatio = (ev.clientX - startX) / cw
            splitterRatio = Math.max(0.35, Math.min(0.78, startRatio + deltaRatio))
          }
          // 松开：解绑全局监听
          const up = () => {
            WIN.removeEventListener('mousemove', move)
            WIN.removeEventListener('mouseup', up)
          }
          WIN.addEventListener('mousemove', move)
          WIN.addEventListener('mouseup', up)
        }"
      />

      <!-- 右：本地知识库面板 -->
      <div class="flex-1 min-w-[320px] flex flex-col min-h-0 gap-3">
        <!-- 状态反馈条（保存流程进行中/成功/失败时显示） -->
        <div
          v-if="saveStatus !== 'idle'"
          class="rounded-xl p-3 text-sm"
          :class="{
            'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20': saveStatus === 'success',
            'bg-red-500/10 text-red-300 border border-red-500/20': saveStatus === 'error',
            'bg-white/5 text-white/70': saveStatus === 'extracting' || saveStatus === 'saving',
          }"
        >
          <div class="font-bold mb-1">{{ statusLabel }}</div>
          <div v-if="saveStatus === 'success' && lastDocId" class="text-xs op-80">
            docId：{{ lastDocId }}；请在下方列表查看，后续和陆墨对话时将自动被检索命中
          </div>
          <div v-if="saveStatus === 'error' && saveError" class="text-xs op-90 mt-1 break-all">
            {{ saveError }}
          </div>
        </div>

        <!-- 确认编辑区：提取后展示 Q/A，用户可修改后再入库 -->
        <div
          v-if="editableQ || editableA"
          class="rounded-xl p-3 bg-white/5 border border-white/5 flex flex-col gap-2"
        >
          <div class="text-xs op-50">确认后入库（可手动修改后再保存）：</div>
          <textarea
            v-model="editableQ"
            rows="2"
            class="rounded-lg bg-black/30 p-2 text-sm resize-none border border-white/5 focus:border-emerald-500/40 outline-none"
            placeholder="问题（Question）"
          />
          <textarea
            v-model="editableA"
            rows="5"
            class="rounded-lg bg-black/30 p-2 text-xs font-mono resize-none border border-white/5 focus:border-emerald-500/40 outline-none"
            placeholder="回答（Answer）"
          />
          <div class="flex gap-2 justify-end">
            <!-- 清空确认区并回到 idle -->
            <button
              class="px-3 py-1.5 rounded text-xs bg-white/5 hover:bg-white/10"
              @click="editableQ=''; editableA=''; saveStatus='idle'; saveError=null"
            >清空</button>
            <!-- 用编辑后的内容入库 -->
            <button
              class="px-3 py-1.5 rounded text-xs bg-emerald-700 hover:bg-emerald-600 text-white"
              @click="doIngest({ q: editableQ, a: editableA })"
            >💾 确认入库</button>
          </div>
        </div>

        <!-- 搜索/筛选 + 工具栏 -->
        <div class="flex gap-2 items-center flex-wrap">
          <input
            v-model="searchKw"
            placeholder="搜索知识库（标题或标签，回车生效）"
            class="flex-1 min-w-[200px] h-9 px-3 rounded-lg bg-black/30 text-sm border border-white/5 focus:border-emerald-500/40 outline-none"
            @keydown.enter="loadDocs"
          >
          <select
            v-model="filterSource"
            class="h-9 px-2 rounded-lg bg-black/30 text-sm border border-white/5"
          >
            <option value="">全部来源</option>
            <option value="matchat">MatChat</option>
            <option value="manual">手动导入</option>
            <option value="txt">txt 文件</option>
            <option value="pdf">PDF</option>
          </select>
          <button
            class="h-9 px-3 rounded-lg bg-white/5 hover:bg-white/10 text-sm"
            :disabled="loading"
            @click="loadDocs"
          >
            {{ loading ? '加载中…' : '🔍 查询' }}
          </button>
          <span
            class="ml-auto text-xs op-50"
            :class="totalDocs ? 'text-emerald-300 op-100' : ''"
          >
            共 {{ totalDocs }} 篇文档
          </span>
        </div>

        <!-- 文档列表（滚动区） -->
        <div class="flex-1 min-h-0 overflow-y-auto pr-1 flex flex-col gap-2">
          <div
            v-for="d in docs"
            :key="d.docId"
            class="rounded-xl p-3 bg-white/5 hover:bg-white/8 border border-white/5 transition"
          >
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-sm truncate flex-1" :title="d.title">
                {{ d.title }}
              </span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded"
                :class="d.source === 'matchat' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/10'"
              >
                {{ d.source || 'local' }}
              </span>
              <span class="text-[10px] op-50 shrink-0">{{ d.createdAt }}</span>
              <span class="text-[10px] op-50 shrink-0">×{{ d.chunkCount }}块</span>
            </div>
            <!-- 预览正文（3 行截断，whitespace-pre-wrap 保留换行） -->
            <div class="text-xs op-70 leading-relaxed line-clamp-3 whitespace-pre-wrap">
              {{ d.preview }}
            </div>
            <!-- 标签列表 -->
            <div v-if="d.tags?.length" class="mt-2 flex flex-wrap gap-1">
              <span
                v-for="t in d.tags"
                :key="t"
                class="text-[10px] px-1.5 py-0.5 rounded bg-white/8 op-70"
              >#{{ t }}</span>
            </div>
            <div class="mt-2 flex justify-end gap-2">
              <button
                class="text-xs px-2 py-1 rounded bg-red-500/10 text-red-300 hover:bg-red-500/20"
                @click="deleteDoc(d)"
              >删除</button>
            </div>
          </div>
          <!-- 空状态引导 -->
          <div
            v-if="!loading && !docs.length"
            class="text-center op-40 py-14 text-sm"
          >
            <div class="text-4xl mb-3">📭</div>
            <div>本地知识库还是空的。</div>
            <div class="mt-1">在左侧 MatChat 中提问后，点击顶部「💾 保存当前问答」即可入库。</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-root {
  /* KnowledgeView 整体非透明，避免 BrowserView 周围透明窗黑边闪烁 */
  min-height: 100%;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
