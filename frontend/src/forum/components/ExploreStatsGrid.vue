<!-- 本次探索统计三卡（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
defineProps<{
  findings: number
  sources: number
  social: number
}>()
</script>

<template>
  <div class="stats-block">
    <div class="stats-label">本次探索</div>
    <div class="stats-grid">
      <div class="stat-card">
        <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
        <span class="stat-num">{{ findings }}</span>
        <span class="stat-name">发现</span>
      </div>
      <div class="stat-card">
        <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        <span class="stat-num">{{ sources }}</span>
        <span class="stat-name">来源</span>
      </div>
      <div class="stat-card">
        <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
        <span class="stat-num">{{ social }}</span>
        <span class="stat-name">互动</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stats-block {
  width: 100%;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 14px 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.stat-icon {
  width: 18px;
  height: 18px;
  color: rgba(212, 175, 55, 0.6);
}

.stat-num {
  font-size: 20px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.88);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.stat-name {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}
</style>
