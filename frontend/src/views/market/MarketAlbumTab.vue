<!-- 音之巷 tab（卷190-B2：从 MarketView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { initDragScroll } from './composables/useDragScroll'

// 专辑数据：仅保留沙之书，左上角角标为 NEW
const albumItems = [
  { id: 1, title: '沙之书', subtitle: '', daysLeft: 0, price: 0, image: '/assets/just.png', bannerLabel: 'NEW' as const },
]

const albumSection = ref<HTMLElement | null>(null)

onMounted(() => {
  if (albumSection.value)
    initDragScroll(albumSection.value)
})
</script>

<template>
  <section
    ref="albumSection"
    class="album-section"
  >
    <div class="album-grid">
      <div
        v-for="item in albumItems"
        :key="item.id"
        class="album-card"
      >
        <div class="card-illust">
          <img :src="item.image" :alt="item.title" class="card-img">
          <div class="card-illust-gradient" />
          <div class="card-watermark">scratchpad</div>
          <div class="card-banner">
            {{ item.bannerLabel ?? `剩余${item.daysLeft}天` }}
          </div>
        </div>
        <div class="card-info">
          <div class="card-title-main">{{ item.title }}</div>
          <div class="card-title-sub">{{ item.subtitle }}</div>
        </div>
        <div class="card-price-bar">
          <span class="price-icon">◆</span>
          <span class="price-num">{{ item.price }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.album-section {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 14px 16px;
  cursor: grab;
  user-select: none;
}

.album-section::-webkit-scrollbar {
  height: 4px;
}

.album-section::-webkit-scrollbar-track {
  background: transparent;
}

.album-section::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.25);
  border-radius: 2px;
}

.album-section::-webkit-scrollbar-thumb:hover {
  background: rgba(212, 175, 55, 0.45);
}

.album-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 12px;
  height: 100%;
  align-items: stretch;
  min-width: min-content;
}

/* ── 卡片 ── */
.album-card {
  position: relative;
  flex-shrink: 0;
  width: calc(75vh - 218px);
  min-width: 100px;
  height: 100%;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.12);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.album-card:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: rgba(251, 191, 36, 0.5);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.5),
    0 0 20px rgba(251, 191, 36, 0.18);
}

/* 图片区域 */
.card-illust {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.card-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* 底部渐变蒙版 */
.card-illust-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    transparent 50%,
    rgba(0, 0, 0, 0.75) 100%
  );
  pointer-events: none;
  z-index: 1;
}

/* 水印文字 */
.card-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-30deg);
  font-size: 18px;
  font-weight: 900;
  font-family: 'Noto Serif SC', serif;
  color: rgba(255, 255, 255, 0.12);
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
  z-index: 2;
  letter-spacing: 0.05em;
}

/* 剩余天数徽章 */
.card-banner {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 8px;
  background: linear-gradient(
    135deg,
    rgba(220, 38, 38, 0.92),
    rgba(234, 88, 12, 0.88)
  );
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  letter-spacing: 0.03em;
  z-index: 3;
  line-height: 1.4;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.4);
}

/* 卡片信息区 */
.card-info {
  padding: 8px 10px 6px;
  flex-shrink: 0;
}

.card-title-main {
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.95);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-title-sub {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.65);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 价格栏 */
.card-price-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 12px;
  background: linear-gradient(
    135deg,
    rgba(234, 179, 8, 0.95),
    rgba(217, 119, 6, 0.9)
  );
  flex-shrink: 0;
}

.price-icon {
  font-size: 11px;
  color: rgba(30, 41, 59, 0.85);
}

.price-num {
  font-size: 15px;
  font-weight: 800;
  color: #1e293b;
  letter-spacing: 0.02em;
}
</style>
