<script setup lang="ts">
/**
 * 法学领域视图（卷162 · 工单 C 前端侧；卷163 扩展判例导入）。
 *
 * 视图内容全部由 `domains/law/pack.yaml` 驱动（字段 / 来源预设），
 * 页面本身不含法学专属硬编码 —— 换成另一个领域包，只要在
 * `views/domains/<name>/IndexView.vue` 放同名文件即可复用。
 *
 * 路由：`/law`（由 domainPacks.registerDomainRoutes 在启动时注册）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import API from '@/api/core'
import { domainPacks, setActiveDomain } from '@/utils/domainPacks'
import { feedback } from '@/utils/feedback'

const router = useRouter()

/** 本视图对应的领域包名（与目录名一致）。 */
const PACK_NAME = 'law'

const pack = computed(() => domainPacks.value.find(p => p.name === PACK_NAME))

const fields = computed(() => pack.value?.eln?.form_fields ?? pack.value?.eln?.fields ?? [])
const presets = computed(() => pack.value?.source_presets ?? [])

// ── 卷163：判例导入 ──
const selectedSource = ref('pkulaw')
const pickedFiles = ref<File[]>([])
const importing = ref(false)
const lastResult = ref<{ imported: number, queued: number, inserted: Array<{ case_no: string, court: string }>, queuedItems: Array<{ filename: string, error: string }>, tagged: number, lowConfidence: number } | null>(null)

// ── 卷164：AI 打标 ──
/** 导入后自动 AI 分类（默认开）。 */
const autoTag = ref(true)
/** Von 状态徽章。 */
const von = ref<{ alive: boolean, enabled: boolean, message: string, breaker: string } | null>(null)
/** 待分类数量。 */
const pending = ref(0)
const taggingBatch = ref(false)

async function refreshVon() {
  try {
    const [st, pv] = await Promise.all([
      API.getVonStatus(),
      API.getLawTagPendingPreview().catch(() => null),
    ])
    von.value = { alive: st.alive, enabled: st.enabled, message: st.message, breaker: st.breaker }
    if (pv)
      pending.value = pv.pending
  }
  catch {
    von.value = null
  }
}

async function runBatchTag() {
  if (taggingBatch.value || !von.value?.alive)
    return
  taggingBatch.value = true
  try {
    const res = await API.tagLawPending()
    if (res.von_available) {
      feedback.success(`已分类 ${res.processed} 条判例`)
    }
    else {
      feedback.warn(res.message ?? 'AI 分类服务离线')
    }
    await refreshVon()
  }
  catch (e: any) {
    feedback.error('批量分类失败', e?.message ?? String(e))
  }
  finally {
    taggingBatch.value = false
  }
}

onMounted(refreshVon)

const currentLicenseNote = computed(
  () => presets.value.find(p => p.key === selectedSource.value)?.license_note ?? '',
)

function onFilesChange(e: Event) {
  const input = e.target as HTMLInputElement
  pickedFiles.value = Array.from(input.files ?? [])
}

async function importCases() {
  if (!pickedFiles.value.length) {
    feedback.warn('请先选择判例文件（.docx / .pdf / .xlsx）')
    return
  }
  importing.value = true
  lastResult.value = null
  try {
    const res = await API.importLawCases(
      pickedFiles.value,
      selectedSource.value,
      currentLicenseNote.value,
      autoTag.value,
    )
    lastResult.value = {
      imported: res.imported,
      queued: res.queued_count,
      inserted: res.inserted,
      queuedItems: res.queued,
      tagged: (res.tagging?.tagged ?? 0),
      lowConfidence: (res.tagging?.low_confidence ?? 0),
    }
    feedback.success(`导入完成：成功 ${res.imported} 条，待补录 ${res.queued_count} 条`)
    await refreshVon()
  }
  catch (e: any) {
    feedback.error('导入失败', e?.message ?? String(e))
  }
  finally {
    importing.value = false
  }
}

async function syncFlk() {
  importing.value = true
  try {
    const res: any = await API.importLawFlk()
    feedback.success(res?.message ?? '法规同步完成')
  }
  catch (e: any) {
    feedback.error('法规同步失败', e?.message ?? String(e))
  }
  finally {
    importing.value = false
  }
}

function enterEln() {
  // 切到该领域后进 ELN，表单即按本领域字段渲染
  setActiveDomain(PACK_NAME)
  router.push('/eln')
}
</script>

<template>
  <div class="flex flex-col gap-5 px-8 py-6 h-full overflow-auto">
    <div class="flex items-center gap-3">
      <button
        class="px-3 py-2 rounded-lg bg-white/5 text-white/60 text-sm hover:bg-white/10 hover:text-white/90 transition-colors"
        @click="router.push('/')"
      >
        返回
      </button>
      <div>
        <h1 class="text-xl font-semibold text-white/90">{{ pack?.label || '法学' }}</h1>
        <p class="text-sm text-white/40 mt-1">{{ pack?.description || '法学判例与法规工作流' }}</p>
      </div>
    </div>

    <div v-if="!pack" class="text-sm text-white/40">
      领域包未加载（后端 /api/domains 不可用）。请确认 apiserver 已启动。
    </div>

    <template v-else>
      <!-- 卷164：AI 自动分类服务状态 -->
      <section class="p-4 rounded-xl bg-white/5 border border-white/10">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 class="text-base font-medium text-white/90 mb-1">AI 自动分类</h2>
            <p class="text-sm text-white/40">
              判决书入库后自动识别案由、审理程序、是否指导性案例、争议焦点，人工只复核低置信项。
            </p>
          </div>
          <span
            v-if="von"
            class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm shrink-0"
            :class="von.alive
              ? 'bg-emerald-500/15 text-emerald-300'
              : 'bg-amber-500/15 text-amber-300'"
            :title="von.message"
          >
            <span class="w-2 h-2 rounded-full" :class="von.alive ? 'bg-emerald-400' : 'bg-amber-400'" />
            {{ von.alive ? '服务在线' : '服务离线' }}
          </span>
        </div>

        <div v-if="von && !von.alive" class="mt-3 text-xs text-white/40">
          离线时打标按钮置灰；启动 <code class="font-mono">von serve</code> 后可用
          （部署步骤见 <code class="font-mono">docs/von-部署-2026-09-27.md</code>）。
        </div>

        <div class="mt-4 flex flex-wrap items-center gap-3">
          <label class="flex items-center gap-2 text-sm text-white/70 cursor-pointer">
            <input v-model="autoTag" type="checkbox" class="accent-#4f8cff">
            导入后自动分类
          </label>
          <button
            class="px-4 py-2 rounded-lg bg-white/5 text-white/70 text-sm hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
            :disabled="!von?.alive || taggingBatch || pending === 0"
            :title="von?.alive ? '对未分类判例批量执行 AI 分类' : '启动 von serve 后可用'"
            @click="runBatchTag"
          >
            {{ taggingBatch ? '分类中…' : `批量分类${pending ? `（${pending} 条待处理）` : ''}` }}
          </button>
        </div>
      </section>

      <!-- 卷163：判例入库 -->
      <section class="p-4 rounded-xl bg-white/5 border border-white/10">
        <h2 class="text-base font-medium text-white/90 mb-3">判例入库</h2>
        <p class="text-sm text-white/40 mb-3">
          上传本地导出的判决书文件（.docx / .pdf / .xlsx），自动抽取案号、法院、审理程序、裁判日期、案由、当事人。
          Excel 按一行一案处理。单文件失败不阻断整批，失败项进入待补录队列。
        </p>

        <div class="flex flex-wrap items-center gap-3 mb-3">
          <label class="text-sm text-white/60">来源</label>
          <select
            v-model="selectedSource"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white/80"
          >
            <option v-for="p in presets" :key="p.key" :value="p.key">{{ p.label }}</option>
            <option value="manual">手动录入</option>
          </select>
          <span v-if="currentLicenseNote" class="text-xs text-white/30">{{ currentLicenseNote }}</span>
        </div>

        <input
          type="file"
          multiple
          accept=".docx,.pdf,.xlsx"
          class="block text-sm text-white/60 mb-3"
          @change="onFilesChange"
        >
        <div class="flex flex-wrap gap-2">
          <button
            class="px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90 transition-opacity disabled:opacity-40"
            :disabled="importing"
            @click="importCases"
          >
            {{ importing ? '导入中…' : `导入 ${pickedFiles.length || ''} 个文件` }}
          </button>
          <button
            class="px-4 py-2 rounded-lg bg-white/5 text-white/70 text-sm hover:bg-white/10 disabled:opacity-40"
            :disabled="importing"
            @click="syncFlk"
          >
            同步官方法规（低频）
          </button>
        </div>

        <div v-if="lastResult" class="mt-4 text-sm">
          <div class="text-white/70 mb-2">
            成功 <span class="text-green-400">{{ lastResult.imported }}</span> 条，
            待补录 <span class="text-amber-400">{{ lastResult.queued }}</span> 条
            <span v-if="lastResult.tagged || lastResult.lowConfidence" class="ml-2 text-white/50">
              · AI 已分类 {{ lastResult.tagged }} 条
              <span v-if="lastResult.lowConfidence" class="text-amber-400">
                ，待复核 {{ lastResult.lowConfidence }} 条
              </span>
            </span>
          </div>
          <ul v-if="lastResult.inserted.length" class="flex flex-col gap-1">
            <li v-for="(it, i) in lastResult.inserted" :key="i" class="text-white/60">
              <span class="font-mono text-#4f8cff">{{ it.case_no }}</span>
              <span class="ml-2 text-white/40">{{ it.court }}</span>
            </li>
          </ul>
          <ul v-if="lastResult.queuedItems.length" class="mt-2 flex flex-col gap-1">
            <li v-for="(q, i) in lastResult.queuedItems" :key="i" class="text-amber-400/80">
              {{ q.filename }}：{{ q.error }}
            </li>
          </ul>
        </div>
      </section>

      <section class="p-4 rounded-xl bg-white/5 border border-white/10">
        <h2 class="text-base font-medium text-white/90 mb-3">案例笔记字段</h2>
        <div class="grid grid-cols-2 lg:grid-cols-3 gap-2">
          <div
            v-for="f in fields"
            :key="f.key"
            class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-white/70"
          >
            {{ f.label }}
            <span class="text-xs text-white/30 ml-1">{{ f.type }}</span>
          </div>
        </div>
        <button
          class="mt-4 px-4 py-2 rounded-lg bg-#4f8cff text-white text-sm hover:opacity-90 transition-opacity"
          @click="enterEln"
        >
          进入案例笔记
        </button>
      </section>

      <section class="p-4 rounded-xl bg-white/5 border border-white/10">
        <h2 class="text-base font-medium text-white/90 mb-3">数据来源与授权</h2>
        <ul class="flex flex-col gap-2">
          <li
            v-for="p in presets"
            :key="p.key"
            class="flex items-start gap-2 text-sm text-white/70"
          >
            <span class="shrink-0 text-#4f8cff">·</span>
            <span>
              <span class="text-white/90">{{ p.label }}</span>
              <span v-if="p.license_note" class="text-white/40 ml-2 text-xs">{{ p.license_note }}</span>
            </span>
          </li>
        </ul>
      </section>

      <section class="p-4 rounded-xl bg-white/5 border border-white/10">
        <h2 class="text-base font-medium text-white/90 mb-3">判例 / 法规主键</h2>
        <div class="flex gap-2">
          <span
            v-for="k in pack.papers.id_fields"
            :key="k"
            class="px-2 py-1 rounded-md bg-#4f8cff/15 text-#4f8cff text-xs font-mono"
          >
            {{ k }}
          </span>
        </div>
      </section>
    </template>
  </div>
</template>
