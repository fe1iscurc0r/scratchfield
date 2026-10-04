<script setup lang="ts">
import { onMounted, ref } from 'vue'
import API from '@/api/core'
import BackButton from '@/components/BackButton.vue'
import { feedback } from '@/utils/feedback'

// ── 录音 ──
const recording = ref(false)
const transcribing = ref(false)
let mediaRecorder: MediaRecorder | null = null
const chunks: Blob[] = []

// ── 转写与草稿 ──
const text = ref('')
const draft = ref('')
const provider = ref<'asr' | 'mock' | ''>('')
const title = ref('')
const drafts = ref<Array<{ draftId: string, modified: string }>>([])

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder = new MediaRecorder(stream)
    chunks.length = 0
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0)
        chunks.push(e.data)
    }
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      await uploadRecording()
    }
    mediaRecorder.start()
    recording.value = true
  }
  catch (e: any) {
    feedback.error('无法访问麦克风', e?.message || String(e))
  }
}

function stopRecording() {
  recording.value = false
  mediaRecorder?.stop()
}

async function uploadRecording() {
  const blob = new Blob(chunks, { type: 'audio/webm' })
  const fd = new FormData()
  fd.append('audio', blob, 'recording.webm')
  transcribing.value = true
  try {
    const res: any = await API.instance.post('/api/voice-eln/transcribe', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    text.value = res.text
    draft.value = res.draft
    provider.value = res.provider
    feedback.success('转写完成', `ASR 来源：${res.provider === 'asr' ? '在线转写' : 'Mock（未配置 ASR）'}`)
  }
  catch (e: any) {
    feedback.error('转写失败', e?.response?.data?.detail || e.message)
  }
  finally {
    transcribing.value = false
  }
}

async function reSegment() {
  try {
    const res: any = await API.instance.post('/api/voice-eln/segment', { text: text.value })
    draft.value = res.draft
    feedback.success('已重新分段')
  }
  catch (e: any) {
    feedback.error('分段失败', e?.response?.data?.detail || e.message)
  }
}

async function saveDraft() {
  try {
    await API.instance.post('/api/voice-eln/save', { title: title.value, markdown: draft.value })
    feedback.success('草稿已保存')
    refreshDrafts()
  }
  catch (e: any) {
    feedback.error('保存失败', e?.response?.data?.detail || e.message)
  }
}

async function refreshDrafts() {
  try {
    const res: any = await API.instance.get('/api/voice-eln/drafts')
    drafts.value = res.drafts
  }
  catch {
    drafts.value = []
  }
}

onMounted(refreshDrafts)
</script>

<template>
  <div class="flex flex-col gap-5 px-8 py-6 h-full overflow-auto">
    <div class="flex items-center gap-3">
      <BackButton />
      <div class="text-sm opacity-70 flex items-center gap-2">
        语音实验记录
        <span v-if="provider" class="px-1.5 py-0.5 rounded text-xs" :class="provider === 'asr' ? 'bg-#22c55e/20 text-#22c55e' : 'bg-#f59e0b/20 text-#f59e0b'">
          {{ provider === 'asr' ? '在线 ASR' : 'Mock ASR' }}
        </span>
      </div>
    </div>

    <!-- 录音控制 -->
    <div class="flex items-center gap-3">
      <button
        class="px-6 py-3 rounded-full text-lg font-bold transition-colors"
        :class="recording ? 'bg-#ef4444 text-white' : 'bg-#4f8cff text-white'"
        :disabled="transcribing"
        @click="recording ? stopRecording() : startRecording()"
      >
        {{ transcribing ? '转写中…' : recording ? '■ 停止' : '● 开始录音' }}
      </button>
      <span class="text-xs opacity-60">边说边记：目的 / 操作 / 结果 / 备注 会按关键词自动分段</span>
    </div>

    <!-- 转写预览（可编辑） -->
    <div class="flex flex-col gap-1">
      <label class="text-sm opacity-70">转写文本（可编辑）</label>
      <textarea
        v-model="text"
        rows="4"
        class="w-full px-3 py-2 rounded-lg bg-black/30 border border-white/15 font-mono text-sm resize-y"
        placeholder="录音结束后在此显示转写文本…"
      />
      <div class="flex justify-end">
        <button
          class="px-3 py-1.5 rounded-lg border border-white/15 hover:bg-white/10 text-sm"
          :disabled="!text"
          @click="reSegment"
        >
          重新分段
        </button>
      </div>
    </div>

    <!-- ELN 草稿预览 -->
    <div class="flex flex-col gap-1">
      <label class="text-sm opacity-70">ELN 草稿预览</label>
      <textarea
        v-model="draft"
        rows="12"
        class="w-full px-3 py-2 rounded-lg bg-black/30 border border-white/15 font-mono text-sm resize-y"
        placeholder="草稿在此生成，可编辑后保存…"
      />
    </div>

    <!-- 保存 -->
    <div class="flex items-center gap-3">
      <input
        v-model="title"
        class="px-3 py-2 rounded-lg bg-black/30 border border-white/15 flex-1"
        placeholder="草稿标题（可选）"
      >
      <button
        class="px-5 py-2 rounded-lg bg-#4f8cff text-white"
        :disabled="!draft"
        @click="saveDraft"
      >
        保存草稿
      </button>
    </div>

    <!-- 已存草稿列表 -->
    <div v-if="drafts.length" class="flex flex-col gap-1">
      <label class="text-sm opacity-70">已保存草稿（{{ drafts.length }}）</label>
      <div
        v-for="d in drafts"
        :key="d.draftId"
        class="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-sm flex justify-between"
      >
        <span class="font-mono">{{ d.draftId }}</span>
        <span class="opacity-60">{{ d.modified }}</span>
      </div>
    </div>
  </div>
</template>
