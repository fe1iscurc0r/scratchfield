<script setup lang="ts">
/**
 * 打标复核弹层（卷164 · 工单 C2）。
 *
 * 点「待复核」徽章后弹出：显示判决书喂料摘要 + Von 各选项概率条形图，
 * 用户一键确认/改选，确认后标签落库、置信度改记 `1.0(人工)`。
 *
 * 面向**非技术用户**：文案说「AI 自动分类」「AI 的判断依据」，
 * 不暴露 systemone / 推理 等术语。
 */
import type { Paper, TagConfidence, TagResult } from '@/api/core'
import { Button, Dialog } from 'primevue'
import { computed, ref, watch } from 'vue'
import API from '@/api/core'
import { feedback } from '@/utils/feedback'

const props = defineProps<{
  visible: boolean
  paper: Paper | null
  /** 要高亮的标签键（从徽章点击进来时指定）。 */
  focusKey?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'confirmed', paper: Paper): void
}>()

/** Dialog 的 visible 双向绑定（避免直接改 prop）。 */
const dialogVisible = computed({
  get: () => props.visible,
  set: (v: boolean) => emit('update:visible', v),
})

/** 选中的待确认问题键。 */
const activeKey = ref('')
const saving = ref(false)
/** 用户改选的值（默认取 AI 原值）。 */
const picked = ref<string | boolean | number>('')

const confidence = computed<TagConfidence | null>(() => {
  const raw = props.paper?.tag_confidence
  if (!raw)
    return null
  try {
    return JSON.parse(raw) as TagConfidence
  }
  catch {
    return null
  }
})

/** 需要复核的问题（低置信优先，其次全部问题的可复核项）。 */
const reviewKeys = computed<string[]>(() => {
  const c = confidence.value
  if (!c)
    return []
  const low = Object.keys(c.low_confidence ?? {})
  if (low.length)
    return low
  return Object.keys(c.questions ?? {})
})

const activeResult = computed<TagResult | null>(() => {
  const c = confidence.value
  if (!c || !activeKey.value)
    return null
  return c.questions?.[activeKey.value] ?? c.low_confidence?.[activeKey.value] ?? null
})

/** 概率条形图数据（按概率降序）。 */
const bars = computed(() => {
  const r = activeResult.value
  if (!r)
    return []
  const probs = r.probs ?? {}
  const entries = Object.entries(probs)
  if (!entries.length && typeof r.value === 'string')
    entries.push([r.value, r.confidence])
  return entries
    .map(([name, p]) => ({ name, pct: Math.round(p * 100), raw: p }))
    .sort((a, b) => b.raw - a.raw)
})

/** 候选项（choice 类型：用 probs 的键；boolean 用 是/否）。 */
const options = computed<Array<string | boolean>>(() => {
  const r = activeResult.value
  if (!r)
    return []
  if (typeof r.value === 'boolean')
    return [true, false]
  const fromProbs = Object.keys(r.probs ?? {})
  if (fromProbs.length)
    return fromProbs
  return typeof r.value === 'string' ? [r.value] : []
})

/** 喂料摘要：从 notes 里取规则抽取的元数据 + 正文前几行。 */
const feedExcerpt = computed(() => {
  const p = props.paper
  if (!p)
    return ''
  const pieces: string[] = []
  if (p.case_no)
    pieces.push(`案号：${p.case_no}`)
  if (p.notes)
    pieces.push(p.notes)
  if (p.abstract)
    pieces.push(`正文摘要：${p.abstract.slice(0, 300)}…`)
  return pieces.join('\n')
})

watch(() => props.visible, (v) => {
  if (v) {
    const c = confidence.value
    const low = c ? Object.keys(c.low_confidence ?? {}) : []
    activeKey.value = props.focusKey && reviewKeys.value.includes(props.focusKey)
      ? props.focusKey
      : (low[0] ?? reviewKeys.value[0] ?? '')
    syncPicked()
  }
})

watch(activeKey, syncPicked)

function syncPicked() {
  const r = activeResult.value
  picked.value = r ? r.value : ''
}

function close() {
  emit('update:visible', false)
}

async function confirm() {
  if (!props.paper || !activeKey.value || saving.value)
    return
  saving.value = true
  try {
    const res = await API.confirmLawTag(props.paper.id, activeKey.value, picked.value)
    feedback.success('已确认 AI 分类')
    emit('confirmed', res.paper)
    // 若还有其它待复核项则切下一个，否则关闭
    const rest = reviewKeys.value.filter(k => k !== activeKey.value)
    if (rest.length && rest[0]) {
      activeKey.value = rest[0]
    }
    else {
      close()
    }
  }
  catch (e: unknown) {
    feedback.error(`确认失败：${(e as Error)?.message ?? e}`)
  }
  finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="dialogVisible"
    modal
    header="复核 AI 分类"
    :style="{ width: '46rem' }"
  >
    <div v-if="!paper" class="text-white/50 text-sm">未选择判例</div>
    <div v-else class="flex flex-col gap-4">
      <!-- 待复核项切换 -->
      <div v-if="reviewKeys.length" class="flex flex-wrap gap-2">
        <button
          v-for="k in reviewKeys"
          :key="k"
          class="px-2 py-1 rounded text-xs border transition-colors"
          :class="k === activeKey
            ? 'bg-amber-500/20 text-amber-200 border-amber-500/40'
            : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10'"
          @click="activeKey = k"
        >
          {{ k }}
        </button>
      </div>

      <!-- AI 判断依据（喂料摘要） -->
      <div>
        <div class="text-xs text-white/40 mb-1">AI 的判断依据（判决书要点）</div>
        <pre class="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/30 border border-white/10 p-3 text-xs text-white/70">{{ feedExcerpt }}</pre>
      </div>

      <!-- 概率条形图 -->
      <div v-if="bars.length">
        <div class="text-xs text-white/40 mb-2">
          AI 的各选项判断概率（当前：{{ activeResult?.value }}）
        </div>
        <div class="flex flex-col gap-2">
          <div
            v-for="b in bars"
            :key="b.name"
            class="flex items-center gap-2 cursor-pointer group"
            @click="typeof picked === 'boolean' ? (picked = b.name === 'true') : (picked = b.name)"
          >
            <span
              class="w-24 shrink-0 text-xs truncate transition-colors"
              :class="String(picked) === b.name ? 'text-amber-200' : 'text-white/60 group-hover:text-white/90'"
            >{{ b.name }}</span>
            <div class="flex-1 h-4 rounded bg-white/5 overflow-hidden">
              <div
                class="h-full rounded transition-all"
                :class="String(picked) === b.name ? 'bg-amber-500/60' : 'bg-sky-500/40'"
                :style="{ width: `${b.pct}%` }"
              />
            </div>
            <span class="w-10 shrink-0 text-right font-mono text-xs text-white/50">{{ b.raw.toFixed(2) }}</span>
          </div>
        </div>
      </div>

      <!-- 改选（boolean 或无可选概率时） -->
      <div v-if="!bars.length && options.length">
        <div class="text-xs text-white/40 mb-2">请选择正确分类</div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="opt in options"
            :key="String(opt)"
            class="px-3 py-1 rounded text-sm border transition-colors"
            :class="picked === opt
              ? 'bg-amber-500/20 text-amber-200 border-amber-500/40'
              : 'bg-white/5 text-white/60 border-white/10 hover:bg-white/10'"
            @click="picked = opt"
          >
            {{ typeof opt === 'boolean' ? (opt ? '是' : '否') : opt }}
          </button>
        </div>
      </div>

      <!-- 布尔快捷改选（有条形图时也允许切） -->
      <div v-else-if="typeof activeResult?.value === 'boolean'" class="flex gap-2">
        <button
          class="px-3 py-1 rounded text-sm border"
          :class="picked === true ? 'bg-amber-500/20 text-amber-200 border-amber-500/40' : 'bg-white/5 text-white/60 border-white/10'"
          @click="picked = true"
        >
          是
        </button>
        <button
          class="px-3 py-1 rounded text-sm border"
          :class="picked === false ? 'bg-amber-500/20 text-amber-200 border-amber-500/40' : 'bg-white/5 text-white/60 border-white/10'"
          @click="picked = false"
        >
          否
        </button>
      </div>

      <div class="text-xs text-white/40">
        确认后将记为「人工」（置信 1.0），并从此待复核列表移除。
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <Button label="取消" text severity="secondary" @click="close" />
        <Button
          label="确认为该分类"
          :loading="saving"
          :disabled="!activeKey"
          @click="confirm"
        />
      </div>
    </template>
  </Dialog>
</template>
