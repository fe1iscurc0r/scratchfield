<!-- 剩余配额仪表（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  quotaRemaining: number
  quotaPercent: number
  effectiveDailyBudget: number
  effectiveUsedToday: number
  realCredits: number
}>()

// SVG 圆环
const RING_R = 58
const RING_C = 2 * Math.PI * RING_R
const ringOffset = computed(() => RING_C * (1 - props.quotaPercent / 100))
</script>

<template>
  <div class="quota-block">
    <div class="gauge-wrap">
      <svg class="gauge-svg" viewBox="0 0 136 136">
        <circle class="gauge-track" cx="68" cy="68" :r="RING_R" />
        <circle
          class="gauge-fill"
          :class="{ low: quotaPercent < 20 }"
          cx="68" cy="68" :r="RING_R"
          :stroke-dasharray="RING_C"
          :stroke-dashoffset="ringOffset"
        />
      </svg>
      <div class="gauge-center">
        <span class="gauge-num">{{ quotaRemaining }}</span>
        <span class="gauge-sub">剩余积分</span>
      </div>
    </div>
    <div class="quota-meta">
      <div class="meta-row">
        <span class="meta-label">每日配额</span>
        <span class="meta-val">{{ effectiveDailyBudget }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">今日已用</span>
        <span class="meta-val">{{ effectiveUsedToday }}</span>
      </div>
      <div class="meta-row">
        <span class="meta-label">账户余额</span>
        <span class="meta-val accent">{{ realCredits }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 剩余流量 ── */
.quota-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.gauge-wrap {
  position: relative;
  width: 140px;
  height: 140px;
}

.gauge-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.gauge-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.06);
  stroke-width: 10;
}

.gauge-fill {
  fill: none;
  stroke: rgba(212, 175, 55, 0.85);
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s ease;
}

.gauge-fill.low {
  stroke: rgba(200, 80, 60, 0.85);
}

.gauge-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.gauge-num {
  font-size: 32px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.92);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.gauge-sub {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  margin-top: 4px;
}

.quota-meta {
  display: flex;
  gap: 20px;
  justify-content: center;
}

.meta-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.meta-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.meta-val {
  font-size: 14px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.75);
  font-variant-numeric: tabular-nums;
}

.meta-val.accent {
  color: rgba(212, 175, 55, 0.9);
}
</style>
