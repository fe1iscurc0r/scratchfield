<script setup lang="ts">
import type { ElnRecord, ElnRecordInput } from '@/api/core'
import type { ElnFieldSchema } from '@/utils/domainPacks'
/**
 * ELN 实验记录本（V-01）
 *
 * 功能：列表卡片 + 新建弹窗 + 详情编辑 + 导出 Markdown + 搜索。
 * 数据来源：apiserver /api/eln/*（Obsidian vault 中的 Markdown 记录）。
 *
 * 卷147 增量：接入科研工作流条 ——
 *  - 从 PapersView 带 citation 跳来时自动开新建弹窗并预填 references
 *  - 保存新建记录后，若来源是文献，回写 papers.linked_experiments（闭合成环）
 *  - 详情加「送预测」按钮（ELN → 材料模型 CLI）
 *
 * 卷162 增量：表单字段改为消费领域包 schema（GET /api/domains），不再写死 ——
 *  - default 包渲染与改造前完全一致（字段顺序/label/控件类型/CSS 类逐项对齐）
 *  - law 包自动渲染法学字段（当事人/案由/争议焦点/裁判要旨/法条依据/关联判例）
 */
import { computed, onMounted, onUnmounted, provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import API from '@/api/core'
import EmptyState from '@/components/EmptyState.vue'
import ResearchFlowBar from '@/components/ResearchFlowBar.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import { clearPending, createResearchFlow, RESEARCH_FLOW_KEY } from '@/composables/useResearchFlow'
import { currentElnFields, fetchDomainPacks } from '@/utils/domainPacks'
import { feedback } from '@/utils/feedback'

const router = useRouter()

// 科研工作流上下文（卷147）
const flow = createResearchFlow()
provide(RESEARCH_FLOW_KEY, flow)

const records = ref<ElnRecord[]>([])
const loading = ref(false)
const searchKw = ref('')
const showCreate = ref(false)
const showEdit = ref(false)
const editingId = ref<string | null>(null)

/**
 * 后端不可用时的兜底字段 —— 与改造前 ElnView 手写表单逐字段一致。
 * 保证领域包机制挂掉时页面仍与改造前行为相同。
 */
const FALLBACK_FIELDS: ElnFieldSchema[] = [
  { key: 'topic', type: 'text', label: '课题 *', required: true },
  { key: 'date', type: 'date', label: '日期', required: false },
  { key: 'status', type: 'text', label: '状态', required: false },
  { key: 'purpose', type: 'textarea', label: '目的', required: false },
  { key: 'reagents', type: 'textarea', label: '药品与用量', required: false },
  { key: 'conditions', type: 'textarea', label: '条件', required: false },
  { key: 'results', type: 'textarea', label: '结果', required: false },
  { key: 'conclusion', type: 'textarea', label: '结论', required: false },
  { key: 'references', type: 'textarea', label: '关联文献', required: false },
]

/**
 * 表单字段 schema（卷162）。来自当前领域包；后端不可用时为空，
 * 此时回退到与改造前一致的内置字段顺序（见 FALLBACK_FIELDS）。
 */
const formFields = computed<ElnFieldSchema[]>(() =>
  currentElnFields.value.length ? currentElnFields.value : FALLBACK_FIELDS,
)

/**
 * 生成空白表单。
 *
 * 基础键集与改造前一致（保证 ElnRecordInput 契约与后端模型必填字段不缺失）；
 * 领域包声明的额外字段（如 law 的 parties/cause_of_action）在此按 schema 补空串，
 * 使表单能正确双向绑定这些新字段。
 */
function blankForm(): ElnRecordInput {
  const base: any = {
    date: new Date().toISOString().slice(0, 10),
    topic: '',
    status: '进行中',
    purpose: '',
    reagents: '',
    conditions: '',
    results: '',
    attachments: [],
    conclusion: '',
    references: '',
  }
  for (const f of formFields.value) {
    if (!(f.key in base))
      base[f.key] = f.type === 'list' ? [] : ''
  }
  return base
}
const form = ref<ElnRecordInput>(blankForm())

/**
 * 表单取值的响应式视图。`form` 仍是唯一数据源（保持 ElnRecordInput 契约），
 * 这里只做字段级的读写代理，供 v-for 绑定。
 */
function fieldValue(key: string): any {
  return (form.value as any)[key] ?? ''
}
function setFieldValue(key: string, value: any) {
  ;(form.value as any)[key] = value
}

/** 文本域/多值字段用换行拼接，单行文本原样。 */
function isTextarea(f: ElnFieldSchema): boolean {
  return f.type === 'textarea' || f.type === 'list'
}

async function loadRecords() {
  loading.value = true
  try {
    const res = await API.elnList(searchKw.value || undefined)
    records.value = res.records
  }
  catch (e: any) {
    feedback.error('加载失败', String(e?.message || e))
  }
  finally {
    loading.value = false
  }
}

function openCreate() {
  form.value = blankForm()
  // 若从 PapersView 带引用跳来，预填 references（卷147 · Papers → ELN）
  if (flow.pendingCitation.value) {
    form.value.references = flow.pendingCitation.value
    feedback.success('已预填文献引用')
  }
  showCreate.value = true
}

function openEdit(record: ElnRecord) {
  editingId.value = record.id
  const { id: _id, ...rest } = record
  form.value = { ...rest }
  showEdit.value = true
}

/**
 * 按 schema 校验必填字段（卷162）。
 *
 * 改造前只校验 `topic` 非空；default 包的 schema 里只有 `topic` 标了
 * required，故行为与改造前一致。其它领域包可声明各自的必填字段。
 */
function validateForm(): boolean {
  for (const f of formFields.value) {
    if (!f.required)
      continue
    const v = fieldValue(f.key)
    const empty = Array.isArray(v) ? v.length === 0 : !String(v ?? '').trim()
    if (empty) {
      // label 常带装饰性 «*»，提示语里去掉
      feedback.warn(`${f.label.replace(/\s*\*+\s*$/, '')}不能为空`)
      return false
    }
  }
  return true
}

async function submitCreate() {
  if (!validateForm())
    return
  try {
    const res = await API.elnCreate(form.value)
    // 闭环回写：来源文献 → linked_experiments（后端 PUT /api/papers/{id}/experiments 已存在）
    const srcPaper = flow.sourcePaperId.value
    if (srcPaper != null) {
      try {
        const paper = await API.getPaper(srcPaper)
        const linked = new Set(paper.paper.linkedExperiments ?? [])
        linked.add(res.record.id)
        await API.linkPaperExperiments(srcPaper, [...linked])
        feedback.success(`已创建并回写 paper#${srcPaper}`)
      }
      catch (e: any) {
        feedback.warn('记录已创建，但回写文献关联失败', String(e?.message || e))
      }
    }
    else {
      feedback.success('已创建')
    }
    clearPending()
    flow.sourcePaperId.value = null
    showCreate.value = false
    await loadRecords()
  }
  catch (e: any) {
    feedback.error('创建失败', String(e?.message || e))
  }
}

/**
 * 「送预测」（卷147 · ELN → 模型预测）
 *
 * 后端现状（已 grep 确认）：无 HTTP 端点暴露材料模型预测，能力在
 * scripts/materials_model/predict.py（CLI，支持 --temp/--time 等特征入参，
 * 输出 JSON 含 predictions[{target,value,unit,interval}] 不确定区间）。
 *
 * 按工单「后端缺失的接口先 grep 确认，缺了标记 TODO 上报维护者，禁止自造」：
 * 此处不伪造 HTTP 调用，改为引导用户走 CLI，并把当前记录特征导出为提示。
 * TODO(后端): 需新增 POST /api/materials/predict（入参：ELN 记录 id 或特征矩阵；
 *   出参：predict.py 的 JSON 结构），届时把本函数换成真实调用。
 */
const predictVisible = ref(false)
const predictRecord = ref<ElnRecord | null>(null)

function openPredict(record: ElnRecord) {
  predictRecord.value = record
  predictVisible.value = true
}

/** 把当前记录拼成 predict.py 的 `--temp/--time` 入参提示（尽力而为，字段名靠关键词识别） */
function predictHint(record: ElnRecord): string {
  const hay = `${record.conditions} ${record.reagents}`
  const temp = /(\d{3,4})\s*(?:°|摄氏)?C/i.exec(hay)?.[1]
  const time = /(\d{1,4})\s*(?:min|分钟)/i.exec(hay)?.[1]
  const args: string[] = []
  if (temp)
    args.push(`--temp ${temp}`)
  if (time)
    args.push(`--time ${time}`)
  return `python scripts/materials_model/predict.py ${args.join(' ')}`.trim()
}

async function copyHint() {
  if (!predictRecord.value)
    return
  const cmd = predictHint(predictRecord.value)
  try {
    await navigator.clipboard.writeText(cmd)
    feedback.success('命令已复制')
  }
  catch {
    feedback.warn('剪贴板不可用，请手动复制', cmd)
  }
}

async function exportForPredict() {
  if (!predictRecord.value)
    return
  try {
    const res = await API.elnExport(predictRecord.value.id)
    const blob = new Blob([res.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `predict-input-${predictRecord.value.id}.md`
    a.click()
    URL.revokeObjectURL(url)
    feedback.success('特征已导出')
  }
  catch (e: any) {
    feedback.error('导出失败', String(e?.message || e))
  }
}

async function submitEdit() {
  if (!editingId.value) {
    feedback.warn('缺少记录 ID')
    return
  }
  if (!validateForm())
    return
  try {
    await API.elnUpdate(editingId.value, form.value)
    feedback.success('已保存')
    showEdit.value = false
    await loadRecords()
  }
  catch (e: any) {
    feedback.error('保存失败', String(e?.message || e))
  }
}

async function exportRecord(record: ElnRecord) {
  try {
    const res = await API.elnExport(record.id)
    const blob = new Blob([res.markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.filename
    a.click()
    URL.revokeObjectURL(url)
    feedback.success('已导出')
  }
  catch (e: any) {
    feedback.error('导出失败', String(e?.message || e))
  }
}

// ── 命令面板 / Ctrl+N 动作对接（卷150：new-eln 直达新建弹窗） ──
function onQuickAction(e: Event) {
  const kind = (e as CustomEvent<{ kind: string }>).detail?.kind
  if (kind === 'new-eln') {
    openCreate()
  }
}
window.addEventListener('lumo:quick-action', onQuickAction)
onUnmounted(() => window.removeEventListener('lumo:quick-action', onQuickAction))

onMounted(async () => {
  // 卷162：先拿领域包 schema 再渲染表单；失败时 formFields 回退内置字段，
  // 不影响记录加载（降级设计）。
  if (!currentElnFields.value.length)
    await fetchDomainPacks()
  await loadRecords()
})
</script>

<template>
  <div class="flex flex-col gap-5 px-8 py-6 h-full overflow-auto">
    <!-- 科研工作流条（卷147）：文献 → 实验 → 数据 → 模型 -->
    <ResearchFlowBar active="eln" />

    <!-- 顶部标题 + 操作 -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <button
          class="px-3 py-2 rounded-lg bg-white/5 text-white/60 text-sm hover:bg-white/10 hover:text-white/90 transition-colors flex items-center gap-1.5"
          title="返回首页"
          @click="router.push('/')"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5" /><path d="M12 19l-7-7 7-7" /></svg>
          返回
        </button>
        <div>
          <h1 class="text-xl font-semibold text-white/90">ELN 实验记录本</h1>
          <p class="text-sm text-white/40 mt-1">Obsidian vault 实验记录 · 共 {{ records.length }} 条</p>
        </div>
      </div>
      <button
        class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90 transition-opacity"
        @click="openCreate"
      >
        + 新建记录
      </button>
    </div>

    <!-- 搜索 -->
    <input
      v-model="searchKw"
      type="text"
      placeholder="搜索课题 / 内容…"
      class="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none focus:border-#4f8cff/60"
      @keyup.enter="loadRecords"
    >

    <!-- 记录卡片列表 -->
    <div v-if="loading" class="text-white/40 text-sm">加载中…</div>
    <SkeletonCard v-if="loading" variant="list" :rows="6" />
    <EmptyState
      v-else-if="records.length === 0"
      icon="📓"
      title="还没有实验记录"
      description="记录今天的合成 / 表征参数，或从文献页「引用建实验」带引用过来"
      action-label="新建记录"
      @action="openCreate"
    />
    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div
        v-for="rec in records"
        :key="rec.id"
        class="p-4 rounded-xl bg-white/5 border border-white/10 flex flex-col gap-2"
      >
        <div class="flex items-start justify-between gap-2">
          <h2 class="text-base font-medium text-white/90 break-all">{{ rec.topic }}</h2>
          <span class="shrink-0 text-xs px-2 py-0.5 rounded-full bg-#4f8cff/15 text-#4f8cff">
            {{ rec.status }}
          </span>
        </div>
        <div class="text-xs text-white/40">{{ rec.date || '未填日期' }}</div>
        <p class="text-sm text-white/60 line-clamp-2">{{ rec.purpose }}</p>
        <div class="flex items-center gap-2 mt-2">
          <button
            class="px-3 py-1 text-xs rounded-md bg-white/10 text-white/80 hover:bg-white/15 transition-colors"
            @click="openEdit(rec)"
          >
            编辑
          </button>
          <button
            class="px-3 py-1 text-xs rounded-md bg-white/10 text-white/80 hover:bg-white/15 transition-colors"
            @click="exportRecord(rec)"
          >
            导出
          </button>
          <!-- ELN → 模型预测（卷147） -->
          <button
            class="px-3 py-1 text-xs rounded-md bg-#4f8cff/20 text-#4f8cff hover:bg-#4f8cff/30 transition-colors"
            title="导出特征并送材料模型预测（当前走后端 CLI，HTTP 端点待补）"
            @click="openPredict(rec)"
          >
            📈 送预测
          </button>
        </div>
      </div>
    </div>

    <!-- 新建弹窗 -->
    <div v-if="showCreate" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div class="w-full max-w-2xl max-h-[85vh] overflow-auto rounded-2xl bg-#1a1a1f border border-white/10 p-6 flex flex-col gap-3">
        <h2 class="text-lg font-semibold text-white/90">新建实验记录</h2>
        <!-- 卷162：字段由领域包 schema 驱动（default 包渲染与改造前逐项一致） -->
        <template v-for="f in formFields" :key="f.key">
          <label class="text-sm text-white/60">{{ f.label }}</label>
          <textarea
            v-if="isTextarea(f)"
            :value="fieldValue(f.key)"
            rows="2"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none"
            @input="setFieldValue(f.key, ($event.target as HTMLTextAreaElement).value)"
          />
          <input
            v-else
            :value="fieldValue(f.key)"
            :type="f.type === 'date' ? 'date' : 'text'"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none"
            @input="setFieldValue(f.key, ($event.target as HTMLInputElement).value)"
          >
        </template>
        <div class="flex justify-end gap-2 mt-2">
          <button class="px-4 py-2 rounded-lg bg-white/10 text-white/70 text-sm hover:bg-white/15" @click="showCreate = false">取消</button>
          <button class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90" @click="submitCreate">保存</button>
        </div>
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="showEdit" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div class="w-full max-w-2xl max-h-[85vh] overflow-auto rounded-2xl bg-#1a1a1f border border-white/10 p-6 flex flex-col gap-3">
        <h2 class="text-lg font-semibold text-white/90">编辑实验记录</h2>
        <template v-for="f in formFields" :key="f.key">
          <label class="text-sm text-white/60">{{ f.label }}</label>
          <textarea
            v-if="isTextarea(f)"
            :value="fieldValue(f.key)"
            rows="2"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none"
            @input="setFieldValue(f.key, ($event.target as HTMLTextAreaElement).value)"
          />
          <input
            v-else
            :value="fieldValue(f.key)"
            :type="f.type === 'date' ? 'date' : 'text'"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none"
            @input="setFieldValue(f.key, ($event.target as HTMLInputElement).value)"
          >
        </template>
        <div class="flex justify-end gap-2 mt-2">
          <button class="px-4 py-2 rounded-lg bg-white/10 text-white/70 text-sm hover:bg-white/15" @click="showEdit = false">取消</button>
          <button class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90" @click="submitEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 送预测弹窗（卷147 · ELN → 材料模型） -->
    <div v-if="predictVisible && predictRecord" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" @click.self="predictVisible = false">
      <div class="w-full max-w-xl rounded-2xl bg-#1a1a1f border border-white/10 p-6 flex flex-col gap-3">
        <h2 class="text-lg font-semibold text-white/90">📈 送材料模型预测</h2>
        <div class="text-xs text-white/50">
          记录 <span class="font-mono text-white/80">{{ predictRecord.id }}</span> · {{ predictRecord.topic }}
        </div>

        <div class="rounded-lg border border-#f59e0b/40 bg-#f59e0b/10 p-3 text-xs text-#f59e0b flex flex-col gap-1">
          <div class="font-medium">后端尚未暴露 HTTP 预测端点</div>
          <div class="opacity-80">
            能力位于 <span class="font-mono">scripts/materials_model/predict.py</span>（CLI）。
            按工单要求不自造 API，此处提供两条落地路径：
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <div class="text-sm text-white/70">① 命令行预测（特征已从「条件」字段尽力提取）</div>
          <div class="flex items-center gap-2">
            <code class="flex-1 px-3 py-2 rounded-lg bg-black/40 border border-white/10 text-xs font-mono text-#22c55e break-all">{{ predictHint(predictRecord) }}</code>
            <button class="px-3 py-2 rounded-lg bg-white/10 text-white/80 text-xs hover:bg-white/15 shrink-0" @click="copyHint">复制</button>
          </div>
          <div class="text-xs text-white/40">
            输出 JSON 含 predictions[].interval（随机森林 10%~90% 分位不确定区间）。
            可用 <span class="font-mono">--data &lt;导出文件&gt;</span> 指向真实 ELN 数据。
          </div>

          <div class="text-sm text-white/70 mt-1">② 导出本记录特征为文件，供 --data 入参</div>
          <button class="self-start px-3 py-2 rounded-lg bg-white/10 text-white/80 text-xs hover:bg-white/15" @click="exportForPredict">
            导出特征 Markdown
          </button>
        </div>

        <div class="text-xs text-white/30 border-t border-white/10 pt-2">
          TODO(后端·上报维护者): 新增 POST /api/materials/predict，入参记录 id 或特征矩阵，
          出参 predict.py 的 JSON 结构；届时此处换成真实调用并把区间直接回显。
        </div>

        <div class="flex justify-end">
          <button class="px-4 py-2 rounded-lg bg-white/10 text-white/70 text-sm hover:bg-white/15" @click="predictVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>
