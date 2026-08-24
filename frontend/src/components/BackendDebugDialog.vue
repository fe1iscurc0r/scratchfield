<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { computed, onUnmounted, ref, watch } from 'vue'
import API from '@/api/core'

const props = defineProps<{
  visible: boolean
  logs: string
}>()

defineEmits<{ 'update:visible': [value: boolean] }>()

const loading = ref(false)
const flushingTelemetry = ref(false)
const lastError = ref('')
const updatedAt = ref('')
const snapshot = ref<Record<string, any>>({})
const backendLogger = ref('')
const telemetryActionMessage = ref('')

let refreshTimer: ReturnType<typeof setInterval> | null = null
let stopBackendLogListener: (() => void) | null = null

function summarize(label: string, payload: any) {
  if (!payload) {
    return `${label}: 未获取`
  }
  if (typeof payload !== 'object') {
    return `${label}: ${String(payload)}`
  }
  const status = payload.status ?? payload.summary?.overall ?? payload.health?.status ?? payload.success
  if (typeof status === 'boolean') {
    return `${label}: ${status ? '正常' : '异常'}`
  }
  return `${label}: ${status ?? '已返回'}`
}

function formatPayload(payload: any) {
  if (payload == null) {
    return '未获取到数据'
  }
  if (typeof payload === 'string') {
    return payload
  }
  try {
    return JSON.stringify(payload, null, 2)
  }
  catch {
    return String(payload)
  }
}

async function refreshDashboard() {
  loading.value = true
  lastError.value = ''

  const results = await Promise.allSettled([
    API.health(),
    API.systemInfo(),
    API.getToolStatus(),
    API.getOpenclawTasks(),
    API.agentServerHealth(),
    API.agentServerFullHealth(),
    API.agentServerOpenclawHealth(),
    API.getTelemetryStatus(),
  ])

  const labels = [
    'apiHealth',
    'systemInfo',
    'toolStatus',
    'openclawTasks',
    'agentHealth',
    'agentFullHealth',
    'agentOpenclawHealth',
    'telemetryStatus',
  ] as const

  const nextSnapshot: Record<string, any> = {}
  const errors: string[] = []

  results.forEach((result, index) => {
    const key = labels[index]!
    if (result.status === 'fulfilled') {
      nextSnapshot[key] = result.value
      return
    }
    const message = result.reason?.message || String(result.reason)
    nextSnapshot[key] = { error: message }
    errors.push(`${key}: ${message}`)
  })

  snapshot.value = nextSnapshot
  updatedAt.value = new Date().toLocaleString()
  lastError.value = errors.join('\n')
  loading.value = false
}

async function flushTelemetryNow() {
  flushingTelemetry.value = true
  telemetryActionMessage.value = ''
  try {
    const result = await API.flushTelemetry()
    telemetryActionMessage.value = `上传结果: ${formatPayload(result.result)}`
  }
  catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    telemetryActionMessage.value = `上传失败: ${message}`
  }
  finally {
    flushingTelemetry.value = false
    await refreshDashboard()
  }
}

async function refreshBackendLogger() {
  if (!window.electronAPI?.backend?.getLogs) {
    backendLogger.value = '当前环境不支持 Electron 后端日志查看'
    return
  }

  try {
    const logs = await window.electronAPI.backend.getLogs()
    backendLogger.value = logs.trim() || '暂无'
  }
  catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    backendLogger.value = `读取后端日志失败: ${message}`
  }
}

const sections = computed(() => [
  {
    title: summarize('API Server', snapshot.value.apiHealth),
    body: formatPayload(snapshot.value.apiHealth),
  },
  {
    title: summarize('System Info', snapshot.value.systemInfo),
    body: formatPayload(snapshot.value.systemInfo),
  },
  {
    title: summarize('Tool Status', snapshot.value.toolStatus),
    body: formatPayload(snapshot.value.toolStatus),
  },
  {
    title: summarize('Agent Server', snapshot.value.agentHealth),
    body: formatPayload(snapshot.value.agentHealth),
  },
  {
    title: summarize('Agent Full Health', snapshot.value.agentFullHealth),
    body: formatPayload(snapshot.value.agentFullHealth),
  },
  {
    title: summarize('Agent OpenClaw', snapshot.value.agentOpenclawHealth),
    body: formatPayload(snapshot.value.agentOpenclawHealth),
  },
  {
    title: summarize('Telemetry', snapshot.value.telemetryStatus?.telemetry ?? snapshot.value.telemetryStatus),
    body: formatPayload(snapshot.value.telemetryStatus),
  },
  {
    title: summarize('OpenClaw Tasks', snapshot.value.openclawTasks),
    body: formatPayload(snapshot.value.openclawTasks),
  },
  {
    title: '后端 Logger',
    body: backendLogger.value.trim() || '暂无',
  },
  {
    title: '最近的后端错误日志',
    body: props.logs?.trim() || '暂无',
  },
])

function stopRefreshTimer() {
  if (refreshTimer !== null) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

function stopBackendLogStream() {
  if (stopBackendLogListener) {
    stopBackendLogListener()
    stopBackendLogListener = null
  }
}

watch(() => props.visible, (visible) => {
  stopRefreshTimer()
  stopBackendLogStream()
  if (!visible) {
    return
  }
  void refreshDashboard()
  void refreshBackendLogger()
  if (window.electronAPI?.backend?.onLog) {
    stopBackendLogListener = window.electronAPI.backend.onLog(({ line }) => {
      backendLogger.value = backendLogger.value.trim()
        ? `${backendLogger.value}\n${line}`
        : line
    })
  }
  refreshTimer = setInterval(() => {
    void refreshDashboard()
    void refreshBackendLogger()
  }, 5000)
}, { immediate: true })

onUnmounted(() => {
  stopRefreshTimer()
  stopBackendLogStream()
})
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    maximizable
    header="后端调试看板"
    :style="{ width: 'min(1100px, 92vw)' }"
    @update:visible="$emit('update:visible', $event)"
  >
    <div class="debug-toolbar">
      <div class="debug-meta">
        <div class="debug-meta-title">
          Ctrl+Shift+U
        </div>
        <div class="debug-meta-text">
          最近刷新：{{ updatedAt || '未刷新' }}
        </div>
      </div>
      <Button
        label="立即刷新"
        icon="pi pi-refresh"
        size="small"
        :loading="loading"
        @click="refreshDashboard"
      />
      <Button
        label="立即上传埋点"
        icon="pi pi-upload"
        size="small"
        severity="secondary"
        :loading="flushingTelemetry"
        @click="flushTelemetryNow"
      />
    </div>

    <div v-if="lastError" class="debug-error">
      {{ lastError }}
    </div>

    <div v-if="telemetryActionMessage" class="debug-info">
      {{ telemetryActionMessage }}
    </div>

    <div class="debug-grid">
      <section v-for="section in sections" :key="section.title" class="debug-card">
        <div class="debug-card-title">
          {{ section.title }}
        </div>
        <pre class="debug-card-body">{{ section.body }}</pre>
      </section>
    </div>
  </Dialog>
</template>

<style scoped>
.debug-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.debug-meta-title {
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
}

.debug-meta-text {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
}

.debug-error {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(160, 32, 32, 0.2);
  color: rgba(255, 210, 210, 0.92);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}

.debug-info {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(44, 80, 140, 0.22);
  color: rgba(220, 235, 255, 0.92);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
}

.debug-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.debug-card {
  min-width: 0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.debug-card-title {
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.debug-card-body {
  margin: 0;
  padding: 12px;
  max-height: 260px;
  overflow: auto;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.74);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace;
}

@media (max-width: 900px) {
  .debug-grid {
    grid-template-columns: 1fr;
  }
}
</style>
