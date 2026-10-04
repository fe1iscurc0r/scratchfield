<script setup lang="ts">
import type { Paper, TagConfidence } from '@/api/core'
import { Button, ConfirmDialog, Dialog, Divider, InputText, Select, Textarea } from 'primevue'
import { onMounted, onUnmounted, provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import EmptyState from '@/components/EmptyState.vue'
import ResearchFlowBar from '@/components/ResearchFlowBar.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import TagBadge from '@/components/TagBadge.vue'
import TagReviewDialog from '@/components/TagReviewDialog.vue'
import { createResearchFlow, RESEARCH_FLOW_KEY } from '@/composables/useResearchFlow'
import { feedback } from '@/utils/feedback'

const router = useRouter()

// 科研工作流上下文（卷147）：本视图作为四件套一环，provide 共享单例
const flow = createResearchFlow()
provide(RESEARCH_FLOW_KEY, flow)

/**
 * 「引用建实验」：把选中文献的 citation 带上，跳到 ELN 新建记录。
 * 后端 papers↔ELN 关联已有（PUT /api/papers/{id}/experiments），
 * 这里先跳转预填，等 ELN 侧建好记录后再回写 linked_experiments。
 */
function citeToEln(p: Paper) {
  const citation = p.doi
    ? `${p.title} (DOI: ${p.doi})`
    : p.year
      ? `${p.title} (${p.year})`
      : p.title
  flow.citeToEln(citation, p.id)
  router.push('/eln')
}

// ── 列表状态 ──
const papers = ref<Paper[]>([])
const total = ref(0)
const query = ref('')
const tagFilter = ref('')
const loading = ref(false)
const loadError = ref('')

// ── 详情状态 ──
const selected = ref<Paper | null>(null)
const notesDraft = ref('')
const tagsDraft = ref('')
const experimentsDraft = ref('')
const saving = ref(false)

// ── 弹窗状态 ──
const showCreate = ref(false)
const newTitle = ref('')
const showImport = ref(false)
const importMode = ref<'json' | 'doi'>('json')
const jsonText = ref('')
const doiText = ref('')

// ── 删除确认（卷150 任务D：破坏性操作统一 ConfirmDialog，列出影响范围） ──
const confirmDeleteVisible = ref(false)
const pendingDelete = ref<Paper | null>(null)

function askRemovePaper() {
  if (!selected.value)
    return
  pendingDelete.value = selected.value
  confirmDeleteVisible.value = true
}

async function doRemovePaper() {
  const p = pendingDelete.value
  if (!p)
    return
  confirmDeleteVisible.value = false
  try {
    await API.deletePaper(p.id)
    if (selected.value?.id === p.id)
      selected.value = null
    feedback.success('已删除')
    await loadPapers()
  }
  catch (e: any) {
    feedback.error('删除失败', errorDetail(e))
  }
  finally {
    pendingDelete.value = null
  }
}

function errorDetail(e: any): string {
  return e?.response?.data?.detail || e?.message || '未知错误'
}

async function loadPapers() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await API.listPapers({
      q: query.value.trim() || undefined,
      tag: tagFilter.value.trim() || undefined,
    })
    papers.value = res.papers
    total.value = res.total
  }
  catch (e: any) {
    loadError.value = errorDetail(e)
    feedback.error('加载失败', errorDetail(e))
  }
  finally {
    loading.value = false
  }
}

async function selectPaper(p: Paper) {
  try {
    const res = await API.getPaper(p.id)
    selected.value = res.paper
    notesDraft.value = res.paper.notes ?? ''
    tagsDraft.value = (res.paper.tags ?? []).join(', ')
    experimentsDraft.value = (res.paper.linkedExperiments ?? []).join(', ')
  }
  catch (e: any) {
    feedback.error('读取文献失败', errorDetail(e))
  }
}

function splitCsv(text: string): string[] {
  return text.split(/[,，]/).map(s => s.trim()).filter(Boolean)
}

async function saveDetails() {
  if (!selected.value)
    return
  saving.value = true
  try {
    const id = selected.value.id
    const tags = splitCsv(tagsDraft.value)
    const experimentIds = splitCsv(experimentsDraft.value)
    const res = await API.updatePaper(id, { notes: notesDraft.value, tags })
    selected.value = res.paper
    await API.linkPaperExperiments(id, experimentIds)
    feedback.success('已保存')
    await loadPapers()
  }
  catch (e: any) {
    feedback.error('保存失败', errorDetail(e))
  }
  finally {
    saving.value = false
  }
}

async function createPaper() {
  const title = newTitle.value.trim()
  if (!title)
    return
  try {
    const res = await API.createPaper({ title })
    showCreate.value = false
    newTitle.value = ''
    feedback.success('已创建')
    await loadPapers()
    await selectPaper(res.paper)
  }
  catch (e: any) {
    feedback.error('创建失败', errorDetail(e))
  }
}

async function importJson() {
  let items: Array<Record<string, unknown>>
  try {
    const parsed = JSON.parse(jsonText.value)
    if (!Array.isArray(parsed))
      throw new Error('请输入 JSON 数组')
    items = parsed
  }
  catch (e: any) {
    feedback.error('JSON 解析失败', e.message)
    return
  }
  try {
    const res = await API.importPapers(items)
    feedback.success(`导入 ${res.imported} 条${res.skipped.length ? `，跳过 ${res.skipped.length} 条` : ''}`)
    jsonText.value = ''
    showImport.value = false
    await loadPapers()
  }
  catch (e: any) {
    feedback.error('导入失败', errorDetail(e))
  }
}

async function importDoi() {
  const doi = doiText.value.trim()
  if (!doi)
    return
  try {
    const res = await API.importDoi(doi)
    if (res.success && res.paper) {
      feedback.success('DOI 导入成功')
      doiText.value = ''
      showImport.value = false
      await loadPapers()
      await selectPaper(res.paper)
    }
    else {
      feedback.warn('拉取失败，可手动补全', res.error ?? 'crossref 不可达')
    }
  }
  catch (e: any) {
    feedback.error('导入失败', errorDetail(e))
  }
}

// ── 命令面板 / Ctrl+K 动作对接（卷150：doi-import 直达导入弹窗） ──
function onQuickAction(e: Event) {
  const kind = (e as CustomEvent<{ kind: string }>).detail?.kind
  if (kind === 'doi-import') {
    importMode.value = 'doi'
    showImport.value = true
  }
}
window.addEventListener('lumo:quick-action', onQuickAction)
onUnmounted(() => window.removeEventListener('lumo:quick-action', onQuickAction))

// ── 卷163：来源徽章（判例/法规的来源标识 → 中文标签） ──
const SOURCE_LABELS: Record<string, string> = {
  pkulaw: '北大法宝',
  wkinfo: '威科先行',
  flk: '国家法规库',
  manual: '手动录入',
}
function sourceLabel(p: Paper): string {
  const s = p.source ?? ''
  if (!s)
    return ''
  return SOURCE_LABELS[s] ?? s
}

// ── 卷164：AI 标签（Von 打标） ──

/** Von 后端状态（离线则按钮置灰）。 */
const vonStatus = ref<{ alive: boolean, enabled: boolean, message: string } | null>(null)
/** 待打标数量。 */
const tagPending = ref(0)
/** 复核弹层。 */
const showReview = ref(false)
const reviewPaper = ref<Paper | null>(null)
const reviewKey = ref<string | undefined>(undefined)
/** 批量打标进度。 */
const tagging = ref(false)
const tagProgress = ref({ done: 0, total: 0 })

/** 解析 tag_confidence，取出 accepted 的标签项。 */
function parsedTags(p: Paper): Array<{ key: string, label: string, confidence: number, human: boolean, low: boolean }> {
  const raw = p.tag_confidence
  if (!raw)
    return []
  let conf: TagConfidence | null = null
  try {
    conf = JSON.parse(raw) as TagConfidence
  }
  catch {
    return []
  }
  if (!conf?.questions)
    return []
  const threshold = conf.threshold ?? 0.6
  const out: Array<{ key: string, label: string, confidence: number, human: boolean, low: boolean }> = []
  for (const [key, r] of Object.entries(conf.questions)) {
    if (!r || !r.accepted)
      continue
    const human = r.source === '人工'
    out.push({
      key,
      label: typeof r.value === 'boolean' ? (r.value ? '是' : '否') : String(r.value),
      confidence: r.confidence,
      human,
      low: !human && r.confidence < threshold,
    })
  }
  return out
}

/** 是否有待复核项。 */
function hasPendingReview(p: Paper): boolean {
  return parsedTags(p).some(t => t.low)
    || Boolean(p.tag_confidence && safeLowCount(p) > 0)
}

function safeLowCount(p: Paper): number {
  try {
    const c = JSON.parse(p.tag_confidence ?? '{}') as TagConfidence
    return Object.keys(c.low_confidence ?? {}).length
  }
  catch {
    return 0
  }
}

async function refreshVon() {
  try {
    const [st, pv] = await Promise.all([
      API.getVonStatus(),
      API.getLawTagPendingPreview().catch(() => null),
    ])
    vonStatus.value = { alive: st.alive, enabled: st.enabled, message: st.message }
    if (pv)
      tagPending.value = pv.pending
  }
  catch {
    // Von 端点不可用（非 law 领域）→ 不显示打标相关 UI
    vonStatus.value = null
    tagPending.value = 0
  }
}

/** 批量打标（分批以支持取消）。 */
async function runBatchTag() {
  if (tagging.value || !vonStatus.value?.alive)
    return
  tagging.value = true
  tagProgress.value = { done: 0, total: tagPending.value }
  try {
    // 后端 tag-pending 一次性处理；进度条按返回结果更新
    const res = await API.tagLawPending()
    if (res.von_available) {
      tagProgress.value.done = res.processed
      feedback.success(`已处理 ${res.processed} 条判例`)
    }
    else {
      feedback.error(res.message ?? 'AI 服务离线')
    }
    await loadPapers()
    await refreshVon()
  }
  catch (e: unknown) {
    feedback.error(`打标失败：${(e as Error)?.message ?? e}`)
  }
  finally {
    tagging.value = false
  }
}

function cancelTagging() {
  tagging.value = false
  feedback.warn('已取消打标')
}

function openReview(p: Paper, key?: string) {
  reviewPaper.value = p
  reviewKey.value = key
  showReview.value = true
}

async function onReviewConfirmed(updated: Paper) {
  const idx = papers.value.findIndex(x => x.id === updated.id)
  if (idx >= 0)
    papers.value[idx] = { ...papers.value[idx], ...updated }
  if (selected.value?.id === updated.id)
    selected.value = { ...selected.value, ...updated }
  await refreshVon()
}

onMounted(() => {
  loadPapers()
  refreshVon()
})
</script>

<template>
  <BoxContainer class="text-sm">
    <div class="flex flex-col h-full gap-2 p-2">
      <!-- 科研工作流条（卷147）：文献 → 实验 → 数据 → 模型 -->
      <ResearchFlowBar active="papers" />
      <div class="flex flex-1 min-h-0 gap-4">
        <!-- 左：列表 -->
        <div class="flex w-2/5 min-w-70 flex-col gap-3">
          <div class="flex gap-2">
            <InputText
              v-model="query"
              placeholder="搜索标题 / 作者 / 标签 / DOI…"
              class="flex-1"
              @keyup.enter="loadPapers"
            />
            <Button label="搜索" size="small" @click="loadPapers" />
          </div>
          <div class="flex items-center gap-2">
            <InputText v-model="tagFilter" placeholder="按标签过滤" class="flex-1" @keyup.enter="loadPapers" />
            <Button label="新建" size="small" severity="secondary" @click="showCreate = true" />
            <Button label="导入" size="small" severity="secondary" @click="showImport = true" />
          </div>
          <div class="text-xs text-white/50">共 {{ total }} 条</div>

          <!-- 卷164：AI 自动分类（Von）状态 + 批量打标 -->
          <div v-if="vonStatus" class="flex flex-col gap-1.5 rounded-lg border border-white/10 bg-white/5 p-2">
            <div class="flex items-center gap-2 text-xs">
              <span
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded"
                :class="vonStatus.alive
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-amber-500/15 text-amber-300'"
                :title="vonStatus.message"
              >
                <span class="w-1.5 h-1.5 rounded-full" :class="vonStatus.alive ? 'bg-emerald-400' : 'bg-amber-400'" />
                {{ vonStatus.alive ? 'AI 分类服务在线' : 'AI 分类服务离线' }}
              </span>
              <span v-if="tagPending > 0" class="text-white/40">{{ tagPending }} 条待分类</span>
            </div>
            <div class="flex items-center gap-2">
              <Button
                label="AI 自动分类"
                size="small"
                :disabled="!vonStatus.alive || tagPending === 0 || tagging"
                :title="vonStatus.alive ? '对未分类判例执行 AI 自动分类' : '启动 von serve 后可用'"
                @click="runBatchTag"
              />
              <Button
                v-if="tagging"
                label="取消"
                size="small"
                severity="secondary"
                text
                @click="cancelTagging"
              />
            </div>
            <!-- 进度条 -->
            <div v-if="tagging" class="flex items-center gap-2">
              <div class="flex-1 h-1.5 rounded bg-white/10 overflow-hidden">
                <div
                  class="h-full bg-sky-500/60 transition-all"
                  :style="{ width: `${tagProgress.total ? Math.round(tagProgress.done / tagProgress.total * 100) : 30}%` }"
                />
              </div>
              <span class="text-xs text-white/50">
                {{ tagProgress.done }}/{{ tagProgress.total || '…' }}
              </span>
            </div>
            <div v-else-if="!vonStatus.alive" class="text-xs text-white/35">
              启动 von serve 后可用（见 docs/von-部署-2026-09-27.md）
            </div>
          </div>

          <div class="flex flex-1 flex-col gap-2 overflow-y-auto pr-1">
            <!-- 卷150：加载骨架 / 错误态 / 空态（替换裸 Message） -->
            <SkeletonCard v-if="loading" variant="list" :rows="6" />
            <EmptyState
              v-else-if="loadError"
              error
              title="文献列表加载失败"
              :description="loadError"
              action-label="重试"
              @action="loadPapers"
            />
            <EmptyState
              v-else-if="papers.length === 0"
              icon="📚"
              title="还没有文献"
              description="从 DOI 导入第一批文献，或粘贴 JSON 批量导入"
              action-label="DOI 导入"
              @action="importMode = 'doi'; showImport = true"
            />
            <div
              v-for="p in papers"
              :key="p.id"
              class="cursor-pointer rounded-lg border border-white/10 bg-white/5 p-3 transition hover:bg-white/10"
              :class="{ 'border-primary-400! bg-primary-500/15!': selected?.id === p.id }"
              @click="selectPaper(p)"
            >
              <div class="font-medium text-white/90">{{ p.title }}</div>
              <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-white/50">
                <span v-if="p.year">{{ p.year }}</span>
                <span v-if="p.journal" class="truncate">{{ p.journal }}</span>
                <span v-if="p.doi" class="truncate text-white/40">{{ p.doi }}</span>
                <!-- 卷163：来源徽章（law 包判例/法规带来源标识与版权说明） -->
                <span
                  v-if="sourceLabel(p)"
                  class="rounded bg-#4f8cff/15 px-1.5 py-0.5 text-xs text-#4f8cff"
                  :title="p.license_note || ''"
                >
                  {{ sourceLabel(p) }}
                </span>
                <span v-if="p.case_no" class="truncate font-mono text-white/40">{{ p.case_no }}</span>
              </div>
              <!-- 卷164：AI 标签列（案由徽章 + 置信度；低置信显示「待复核」） -->
              <div v-if="parsedTags(p).length || hasPendingReview(p)" class="mt-1 flex flex-wrap items-center gap-1">
                <TagBadge
                  v-for="t in parsedTags(p)"
                  :key="t.key"
                  :label="t.label"
                  :confidence="t.confidence"
                  :human="t.human"
                  :clickable="t.low"
                  @review="openReview(p, t.key)"
                />
                <TagBadge
                  v-if="hasPendingReview(p) && !parsedTags(p).some(t => t.low)"
                  label="待复核"
                  :confidence="0"
                  clickable
                  @review="openReview(p)"
                />
              </div>
              <!-- 非 AI 标签（人工手填的普通标签）仍以原样式展示 -->
              <div v-if="(p.tags ?? []).length" class="mt-1 flex flex-wrap gap-1">
                <span v-for="t in p.tags" :key="t" class="rounded bg-white/10 px-1.5 py-0.5 text-xs text-white/60">{{ t }}</span>
              </div>
              <!-- 引用建实验（卷147 · Papers → ELN 通道） -->
              <div class="mt-2 flex gap-1.5">
                <Button
                  label="引用建实验"
                  size="small"
                  severity="secondary"
                  text
                  class="!px-2 !py-0.5 !text-xs"
                  title="带上本文引用跳到实验记录本新建记录"
                  @click.stop="citeToEln(p)"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- 右：详情 -->
        <div class="flex flex-1 flex-col gap-3 overflow-y-auto rounded-lg border border-white/10 bg-white/5 p-4">
          <template v-if="selected">
            <div class="text-lg font-semibold text-white/90">{{ selected.title }}</div>
            <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-white/70">
              <div><span class="text-white/40">DOI：</span>{{ selected.doi || '—' }}</div>
              <div><span class="text-white/40">期刊：</span>{{ selected.journal || '—' }}</div>
              <div><span class="text-white/40">年份：</span>{{ selected.year || '—' }}</div>
              <div><span class="text-white/40">作者：</span>{{ (selected.authors ?? []).join(', ') || '—' }}</div>
            </div>

            <div v-if="selected.abstract" class="text-sm leading-relaxed text-white/60">
              <div class="mb-1 text-white/40">摘要</div>
              {{ selected.abstract }}
            </div>

            <!-- 科研工作流：文献 → 实验（卷147） -->
            <div class="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] p-2">
              <Button
                label="📚 引用建实验"
                size="small"
                title="带上本文引用跳到实验记录本新建记录，citation 自动预填"
                @click="citeToEln(selected)"
              />
              <span class="text-xs text-white/40">跳转后实验记录本会自动预填引用；保存记录时会回写本文的「关联实验」。</span>
            </div>

            <Divider class="m-1!" />

            <div class="grid gap-3">
              <div>
                <div class="mb-1 text-white/40">标签（逗号分隔）</div>
                <InputText v-model="tagsDraft" class="w-full" placeholder="如：碳化, 综述" />
              </div>
              <div>
                <div class="mb-1 text-white/40">笔记</div>
                <Textarea v-model="notesDraft" class="w-full" rows="4" placeholder="阅读笔记…" />
              </div>
              <div>
                <div class="mb-1 text-white/40">关联实验 ID（逗号分隔，与 ELN 打通）</div>
                <InputText v-model="experimentsDraft" class="w-full" placeholder="如：exp-001, exp-002" />
              </div>
              <div class="flex gap-2">
                <Button label="保存" size="small" :loading="saving" @click="saveDetails" />
                <Button label="删除" size="small" severity="danger" text @click="askRemovePaper" />
              </div>
            </div>
          </template>
          <EmptyState
            v-else
            icon="📄"
            title="未选择文献"
            description="从左侧选择一篇文献查看详情与笔记"
          />
        </div>
      </div>

      <!-- 新建弹窗 -->
      <Dialog v-model:visible="showCreate" header="新建文献" modal :style="{ width: '420px' }">
        <div class="grid gap-3">
          <InputText v-model="newTitle" placeholder="标题（必填）" @keyup.enter="createPaper" />
          <Button label="创建" size="small" @click="createPaper" />
        </div>
      </Dialog>

      <!-- 导入弹窗 -->
      <Dialog v-model:visible="showImport" header="导入文献" modal :style="{ width: '560px' }">
        <div class="grid gap-3">
          <Select v-model="importMode" :options="['json', 'doi']" class="w-40">
            <template #value="{ value }">
              {{ value === 'json' ? '粘贴 JSON' : 'DOI 导入' }}
            </template>
            <template #option="{ option }">
              {{ option === 'json' ? '粘贴 JSON（云服流水线产物）' : 'DOI 导入（crossref）' }}
            </template>
          </Select>

          <template v-if="importMode === 'json'">
            <Textarea
              v-model="jsonText"
              rows="8"
              placeholder="[{&quot;title&quot;: &quot;论文标题&quot;, &quot;doi&quot;: &quot;10.x/xx&quot;, &quot;abstract&quot;: &quot;…&quot;, &quot;md&quot;: &quot;# …&quot;}]"
            />
            <Button label="批量导入" size="small" @click="importJson" />
          </template>
          <template v-else>
            <InputText v-model="doiText" placeholder="10.1038/xxxx" @keyup.enter="importDoi" />
            <div class="text-xs text-white/50">crossref 拉取失败时可关闭弹窗、手动「新建」补全。</div>
            <Button label="DOI 导入" size="small" @click="importDoi" />
          </template>
        </div>
      </Dialog>

      <!-- 删除确认（卷150 任务D：列出影响范围） -->
      <ConfirmDialog v-model:visible="confirmDeleteVisible" @confirm="doRemovePaper">
        <template #message>
          确认删除文献《{{ pendingDelete?.title }}》？
          <br>将同时解除与 <b>{{ (pendingDelete?.linkedExperiments ?? []).length }}</b> 条实验记录的关联，不可恢复。
        </template>
      </ConfirmDialog>

      <!-- 卷164：AI 分类复核弹层 -->
      <TagReviewDialog
        v-model:visible="showReview"
        :paper="reviewPaper"
        :focus-key="reviewKey"
        @confirmed="onReviewConfirmed"
      />
    </div>
  </BoxContainer>
</template>
