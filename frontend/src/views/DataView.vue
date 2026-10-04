<script setup lang="ts">
/**
 * 实验数据工具台（V-02）
 *
 * 功能：拖拽/选择数据文件（TGA/DSC/XRD，CSV/TXT，分隔符自动探测）→
 * 预览表头 → 设置参数（x/y 列、类型、DSC 质量、XRD 平滑）→ 生成科研风 PNG →
 * 图入库 ELN（新建记录或追加附件）。
 * 数据来源：apiserver /api/data-tools/*。
 *
 * 卷147 增量：接入科研工作流条，并把「入库 ELN」从参数表单里的隐式字段
 * 提升为主流程一等入口（QuickAttach 面板 + 一键挂到指定记录）。
 * 卷150 增量：toast → feedback 三级 API；解析中骨架屏（消除白屏冻结）。
 */
import { onMounted, provide, ref, watch } from 'vue'
import API from '@/api/core'
import ResearchFlowBar from '@/components/ResearchFlowBar.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import { createResearchFlow, RESEARCH_FLOW_KEY } from '@/composables/useResearchFlow'
import { feedback } from '@/utils/feedback'

// 科研工作流上下文（卷147）
const flow = createResearchFlow()
provide(RESEARCH_FLOW_KEY, flow)

type DataType = 'tga' | 'dsc' | 'xrd' | 'raman'
const DATA_TYPE_LABELS: Record<DataType, string> = {
  tga: 'TGA 热重',
  dsc: 'DSC 差热',
  xrd: 'XRD 衍射',
  raman: 'Raman 拉曼',
}

const file = ref<File | null>(null)
const fileUrl = ref('')
const loading = ref(false)
const plotting = ref(false)

// 解析预览
const parsed = ref<{
  filename: string
  delimiter: string
  columns: string[]
  numericColumns: string[]
  rowCount: number
  preview: Record<string, string | number | null>[]
} | null>(null)

// 绘图参数
const dataType = ref<DataType>('tga')
const xCol = ref('')
const yCol = ref('')
const title = ref('')
const massMg = ref<number | null>(null)
const smoothWindow = ref<number>(0)
const topic = ref('')
const recordId = ref('')

// 绘图结果
const result = ref<{ attachment: string, recordId: string | null, imageUrl: string } | null>(null)

const API_ORIGIN = 'http://localhost:8000'

async function selectFile(f: File | null) {
  if (!f)
    return
  file.value = f
  fileUrl.value = URL.createObjectURL(f)
  parsed.value = null
  result.value = null
  xCol.value = ''
  yCol.value = ''
  await parseFile(f)
}

async function parseFile(f: File) {
  loading.value = true
  try {
    const res = await API.dataToolsParse(f)
    parsed.value = res
    xCol.value = res.numericColumns[0] ?? res.columns[0] ?? ''
    yCol.value = res.numericColumns[1] ?? res.numericColumns[0] ?? ''
    feedback.success(`解析成功 · 分隔符 ${JSON.stringify(res.delimiter)} · ${res.rowCount} 行`)
  }
  catch (e: any) {
    feedback.error('解析失败', String(e?.message || e))
  }
  finally {
    loading.value = false
  }
}

async function useSample(type: DataType) {
  const res = await API.dataToolsSamples()
  const content = res.samples[type].content
  const f = new File([content], `${type}_sample.csv`, { type: 'text/csv' })
  dataType.value = type
  await selectFile(f)
}

function onDrop(e: DragEvent) {
  const f = e.dataTransfer?.files?.[0]
  if (f)
    selectFile(f)
}

async function generatePlot() {
  if (!file.value) {
    feedback.warn('请先选择数据文件')
    return
  }
  if (!xCol.value || !yCol.value) {
    feedback.warn('请选择 x / y 列')
    return
  }
  plotting.value = true
  try {
    const res = await API.dataToolsPlot({
      file: file.value,
      dataType: dataType.value,
      xCol: xCol.value,
      yCol: yCol.value,
      title: title.value || undefined,
      massMg: massMg.value ?? undefined,
      smoothWindow: smoothWindow.value,
      topic: topic.value || undefined,
      recordId: recordId.value || undefined,
    })
    const name = res.attachment.replace(/^attachments\//, '')
    result.value = {
      attachment: res.attachment,
      recordId: res.recordId,
      imageUrl: `${API_ORIGIN}/api/eln/attachments/${encodeURIComponent(name)}`,
    }
    feedback.success('已生成并入库')
  }
  catch (e: any) {
    feedback.error('绘图失败', String(e?.message || e))
  }
  finally {
    plotting.value = false
  }
}

watch(dataType, (t) => {
  if (t !== 'xrd')
    smoothWindow.value = 0
})

// ── 入库 ELN 前移入口（卷147 · Data → ELN）──
// 从 ELN 侧带记录 id 跳来时自动挂载；也可在此手动选择目标记录。
const elnRecords = ref<Array<{ id: string, topic: string }>>([])
const elnPickLoading = ref(false)

async function loadElnRecords() {
  elnPickLoading.value = true
  try {
    const res = await API.elnList()
    elnRecords.value = res.records.map(r => ({ id: r.id, topic: r.topic }))
  }
  catch {
    elnRecords.value = [] // ELN 不可用时静默降级为"新建记录"路径
  }
  finally {
    elnPickLoading.value = false
  }
}

/** 一键把已生成的图挂到当前选中的 ELN 记录（走既有 attachments 接口） */
async function attachResultToEln() {
  if (!result.value) {
    feedback.warn('请先生成图')
    return
  }
  if (!recordId.value) {
    feedback.warn('请先选择目标记录或填写记录 ID')
    return
  }
  try {
    const name = result.value.attachment.replace(/^attachments\//, '')
    const rec = await API.elnGet(recordId.value)
    const atts = new Set(rec.record.attachments ?? [])
    atts.add(`attachments/${name}`)
    await API.elnUpdate(recordId.value, { ...rec.record, attachments: [...atts] } as any)
    flow.attachToEln(recordId.value, name)
    feedback.success(`已挂到 ${recordId.value}`)
  }
  catch (e: any) {
    feedback.error('挂载失败', String(e?.message || e))
  }
}

onMounted(async () => {
  // 默认加载 TGA 样例，方便直接体验
  try {
    await useSample('tga')
  }
  catch { /* 忽略样例加载失败 */ }
  await loadElnRecords()
  // 从 ELN 带记录 id 跳来：自动选中目标记录
  if (flow.focusedRecordId.value)
    recordId.value = flow.focusedRecordId.value
})
</script>

<template>
  <div class="flex flex-col gap-5 px-8 py-6 h-full overflow-auto">
    <!-- 科研工作流条（卷147）：文献 → 实验 → 数据 → 模型 -->
    <ResearchFlowBar active="data" />

    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-semibold text-white/90">实验数据工具台</h1>
        <p class="text-sm text-white/40 mt-1">TGA / DSC / XRD 数据导入 · 预处理 · 科研风绘图 · 入库 ELN</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-for="(label, t) in DATA_TYPE_LABELS"
          :key="t"
          class="px-3 py-1.5 text-xs rounded-lg border transition-colors"
          :class="dataType === t ? 'bg-#4f8cff/20 border-#4f8cff/60 text-#4f8cff' : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10'"
          @click="useSample(t)"
        >
          载入{{ label }}样例
        </button>
      </div>
    </div>

    <!-- 数据源：拖拽 / 选择文件 -->
    <div
      class="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/20 bg-white/[0.03] p-8 text-center"
      @dragover.prevent
      @drop.prevent="onDrop"
    >
      <div class="text-sm text-white/70">{{ file ? `已选择：${file.name}` : '拖拽 CSV / TXT 到此处，或点击选择文件' }}</div>
      <label class="px-4 py-2 rounded-lg bg-white/10 text-white text-sm cursor-pointer hover:bg-white/15 transition-colors">
        选择文件
        <input type="file" accept=".csv,.txt,.tsv" class="hidden" @change="selectFile(($event.target as HTMLInputElement).files?.[0] ?? null)">
      </label>
      <div v-if="fileUrl" class="flex items-center gap-3 text-xs text-white/40">
        <span>已载入样例预览：</span>
        <img :src="fileUrl" alt="数据预览" class="hidden">
      </div>
    </div>

    <!-- 解析中骨架 / 表头预览（卷150：消除白屏冻结） -->
    <div v-if="loading" class="rounded-2xl bg-white/5 border border-white/10 p-4">
      <SkeletonCard variant="text" :rows="4" />
    </div>
    <div v-else-if="parsed" class="rounded-2xl bg-white/5 border border-white/10 p-4 flex flex-col gap-2">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium text-white/80">
          表头预览 · {{ parsed.filename }} · {{ parsed.rowCount }} 行
        </h2>
        <span class="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/50">
          分隔符 {{ JSON.stringify(parsed.delimiter) }}
        </span>
      </div>
      <div class="overflow-auto max-h-40 rounded-lg border border-white/10">
        <table class="w-full text-xs text-white/70">
          <thead class="bg-white/5 text-white/50">
            <tr>
              <th v-for="c in parsed.columns" :key="c" class="px-3 py-1.5 text-left font-normal whitespace-nowrap">{{ c }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in parsed.preview" :key="i" class="border-t border-white/5">
              <td v-for="c in parsed.columns" :key="c" class="px-3 py-1.5 whitespace-nowrap">{{ row[c] ?? row[(c as any)] ?? '' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 入库 ELN：主流程一等入口（卷147 前移） -->
    <div class="rounded-2xl border border-#4f8cff/30 bg-#4f8cff/[0.07] p-4 flex flex-col gap-3">
      <div class="flex items-center gap-2">
        <h2 class="text-sm font-medium text-#4f8cff">🧪 入库 ELN</h2>
        <span class="text-xs text-white/40">把上图挂到实验记录（已有记录选挂 / 没有则填课题自动新建）</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="flex flex-col gap-1 text-sm text-white/60 md:col-span-2">
          挂到已有记录
          <select v-model="recordId" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
            <option value="">（不挂已有记录）</option>
            <option v-for="r in elnRecords" :key="r.id" :value="r.id">
              {{ r.id }} · {{ r.topic }}
            </option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60">
          或新建记录课题
          <input v-model="topic" type="text" placeholder="填写则自动创建记录" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          :disabled="plotting"
          @click="generatePlot"
        >
          {{ plotting ? '生成中…' : '生成图并入 ELN' }}
        </button>
        <button
          class="px-4 py-2 rounded-lg bg-white/10 text-white/80 text-sm hover:bg-white/15 disabled:opacity-40"
          :disabled="!result"
          title="把已生成的图挂到上面选中的记录"
          @click="attachResultToEln"
        >
          一键挂到所选记录
        </button>
        <button
          class="px-3 py-2 rounded-lg bg-white/5 text-white/60 text-xs hover:bg-white/10"
          :disabled="elnPickLoading"
          @click="loadElnRecords"
        >
          {{ elnPickLoading ? '刷新中…' : '↻ 刷新记录列表' }}
        </button>
        <span v-if="result" class="text-xs text-#22c55e">已生成：{{ result.attachment.replace(/^attachments\//, '') }}</span>
        <span v-else class="text-xs text-white/30">尚未生成图</span>
      </div>
    </div>

    <!-- 参数设置 -->
    <div class="rounded-2xl bg-white/5 border border-white/10 p-4 flex flex-col gap-3">
      <h2 class="text-sm font-medium text-white/80">绘图参数</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <label class="flex flex-col gap-1 text-sm text-white/60">
          数据类型
          <select v-model="dataType" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
            <option v-for="(label, t) in DATA_TYPE_LABELS" :key="t" :value="t">{{ label }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60">
          X 列
          <select v-model="xCol" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
            <option v-for="c in parsed?.columns ?? []" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60">
          Y 列
          <select v-model="yCol" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
            <option v-for="c in parsed?.columns ?? []" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60 md:col-span-3">
          图表标题
          <input v-model="title" type="text" placeholder="留空自动生成" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
        <label v-if="dataType === 'dsc'" class="flex flex-col gap-1 text-sm text-white/60">
          样品质量 mg（DSC 归一化，可选）
          <input v-model.number="massMg" type="number" step="0.1" min="0" placeholder="留空为 min-max 归一化" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
        <label v-if="dataType === 'xrd'" class="flex flex-col gap-1 text-sm text-white/60">
          平滑窗口（XRD，奇数，0=不平滑）
          <input v-model.number="smoothWindow" type="number" step="1" min="0" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60">
          课题（新建 ELN 记录，可选）
          <input v-model="topic" type="text" placeholder="填写则自动创建实验记录" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
        <label class="flex flex-col gap-1 text-sm text-white/60">
          ELN 记录 ID（追加附件，可选）
          <input v-model="recordId" type="text" placeholder="填入则把图追加到该记录" class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-white text-sm outline-none">
        </label>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          :disabled="plotting"
          @click="generatePlot"
        >
          {{ plotting ? '生成中…' : '生成图并入 ELN' }}
        </button>
        <span class="text-xs text-white/40">图将保存到 vault experiments/attachments/，并写入 ELN 记录附件。</span>
      </div>
    </div>

    <!-- 结果 -->
    <div v-if="result" class="rounded-2xl bg-white/5 border border-white/10 p-4 flex flex-col gap-3">
      <h2 class="text-sm font-medium text-white/80">生成结果</h2>
      <img :src="result.imageUrl" alt="科研曲线图" class="max-w-full rounded-lg border border-white/10 bg-white">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/50">
        <span>附件：<span class="text-white/80">{{ result.attachment }}</span></span>
        <span v-if="result.recordId">ELN 记录：<span class="text-white/80">{{ result.recordId }}</span></span>
        <span v-else>未关联 ELN 记录</span>
      </div>
    </div>
  </div>
</template>
