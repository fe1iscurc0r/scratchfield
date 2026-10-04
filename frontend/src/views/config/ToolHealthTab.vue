<script setup lang="ts">
/**
 * 工具健康（卷189-B1）：只读的调用画像 + 熔断状态。
 *
 * 数据源：GET /tools/stats（P50/P95/失败率）+ GET /tools/circuit（熔断中工具）。
 * 刻意只做表格，不引图表库（工单要求）。
 */
import type { ToolCircuitState, ToolStats } from '@/api/core'
import { Button, Message, Select } from 'primevue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import API from '@/api/core'
import ConfigGroup from '@/components/ConfigGroup.vue'

const windowKey = ref<'1d' | '7d' | '30d'>('7d')
const stats = ref<Record<string, ToolStats>>({})
const circuits = ref<Record<string, ToolCircuitState>>({})
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const windowOptions = [
  { label: '近 24 小时', value: '1d' },
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
]

/** 按调用量降序；失败率高者提前（便于一眼看到问题工具）。 */
const rows = computed(() =>
  Object.entries(stats.value)
    .map(([tool, s]) => ({ tool, ...s }))
    .sort((a, b) => b.calls - a.calls),
)

const circuitRows = computed(() => Object.values(circuits.value))

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`
}

function fmtMs(v: number) {
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${v.toFixed(0)}ms`
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [s, c] = await Promise.all([
      API.getToolStats(windowKey.value),
      API.getToolCircuit(),
    ])
    stats.value = s.stats ?? {}
    circuits.value = c.circuits ?? {}
  }
  catch (e: any) {
    error.value = e?.message || '读取工具画像失败'
  }
  finally {
    loading.value = false
  }
}

onMounted(() => {
  void refresh()
  timer = setInterval(() => void refresh(), 30000) // 30s 自动刷新
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="tool-health">
    <ConfigGroup value="tool-health" header="工具健康">
      <div class="toolbar">
        <Select
          v-model="windowKey"
          :options="windowOptions"
          option-label="label"
          option-value="value"
          size="small"
          @change="refresh"
        />
        <Button
          label="刷新"
          size="small"
          severity="secondary"
          :loading="loading"
          @click="refresh"
        />
      </div>

      <Message v-if="error" severity="error" :closable="false" class="mb">
        {{ error }}
      </Message>

      <template v-if="circuitRows.length">
        <div class="section-title">
          熔断中（{{ circuitRows.length }}）
        </div>
        <table class="th-table">
          <thead>
            <tr>
              <th>工具</th><th>状态</th><th>样本</th><th>失败率</th><th>最近错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in circuitRows" :key="c.tool">
              <td class="mono">{{ c.tool }}</td>
              <td>
                <span :class="['badge', c.state === 'open' ? 'bad' : 'warn']">
                  {{ c.state }}
                </span>
              </td>
              <td>{{ c.samples }}</td>
              <td>{{ pct(c.fail_rate) }}</td>
              <td class="err">{{ c.last_error || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <div class="section-title">
        调用画像（{{ rows.length }} 个工具）
      </div>
      <p v-if="!rows.length" class="empty">
        暂无调用记录。工具被调用后这里会显示 调用数 / 延迟 / 失败率。
      </p>
      <table v-else class="th-table">
        <thead>
          <tr>
            <th>工具</th><th>调用</th><th>P50</th><th>P95</th><th>失败率</th><th>最近错误</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.tool">
            <td class="mono">{{ r.tool }}</td>
            <td>{{ r.calls }}</td>
            <td>{{ fmtMs(r.p50_ms) }}</td>
            <td>{{ fmtMs(r.p95_ms) }}</td>
            <td :class="{ 'err': r.error_rate > 0.2 }">{{ pct(r.error_rate) }}</td>
            <td class="err">{{ r.last_error || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </ConfigGroup>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.mb { margin-bottom: 12px; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 14px 0 8px;
  opacity: 0.85;
}
.empty {
  font-size: 13px;
  opacity: 0.6;
  margin: 4px 0;
}
.th-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.th-table th {
  text-align: left;
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--surface-border, rgba(128, 128, 128, 0.25));
  opacity: 0.75;
}
.th-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--surface-border, rgba(128, 128, 128, 0.12));
}
.mono { font-family: var(--font-mono, monospace); }
.err { color: var(--red-500, #e5484d); }
.badge {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.badge.bad { background: rgba(229, 72, 77, 0.15); color: var(--red-500, #e5484d); }
.badge.warn { background: rgba(245, 165, 36, 0.15); color: var(--yellow-600, #d97706); }
</style>
