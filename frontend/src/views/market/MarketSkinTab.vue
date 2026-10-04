<!-- 界面背景 tab（卷190-B2：从 MarketView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { cloudUser } from '@/composables/useAuth'
import { useBackground } from '@/composables/useBackground'
import { useBackgroundMarket } from './composables/useBackgroundMarket'
import { initVerticalDragScroll } from './composables/useDragScroll'

const props = defineProps<{
  activeTab: string
}>()

const { backgroundList, activeBackground, isOwned, isActive, purchase, apply, resetToDefault, getBackgroundUrl, loadBackgrounds } = useBackground()
const { bgConfirmTarget, bgPurchasing, handleBgAction, confirmPurchase, cancelPurchase, handleResetBg, confirmBgItem } = useBackgroundMarket({
  backgroundList,
  isOwned,
  isActive,
  purchase,
  apply,
  resetToDefault,
})

const skinGridRef = ref<HTMLElement | null>(null)

onMounted(() => {
  loadBackgrounds()
  nextTick(() => {
    if (skinGridRef.value)
      initVerticalDragScroll(skinGridRef.value)
  })
})

watch(() => props.activeTab, (tab) => {
  if (tab === 'skin') {
    nextTick(() => {
      if (skinGridRef.value)
        initVerticalDragScroll(skinGridRef.value)
    })
  }
})
</script>

<template>
  <section class="skin-section">
    <!-- 顶部信息栏：积分余额 + 重置按钮 -->
    <div class="skin-toolbar">
      <div class="skin-balance">
        <span class="balance-icon">◆</span>
        <span class="balance-num">{{ cloudUser?.points ?? '--' }}</span>
        <span class="balance-label">积分</span>
      </div>
      <button
        type="button"
        class="skin-reset-btn"
        :class="{ disabled: !activeBackground }"
        :disabled="!activeBackground"
        @click="handleResetBg"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
          <path d="M3 3v5h5" />
        </svg>
        恢复默认
      </button>
    </div>

    <!-- 背景卡片网格（3列，垂直滚动 + 拖动） -->
    <div ref="skinGridRef" class="skin-grid">
      <div
        v-for="bg in backgroundList"
        :key="bg.id"
        class="skin-card"
        :class="{ active: isActive(bg.id), owned: isOwned(bg.id) }"
        @click="handleBgAction(bg.id)"
      >
        <div class="skin-thumb">
          <img :src="getBackgroundUrl(bg.id)" :alt="bg.name" class="skin-thumb-img" @error="($event.target as HTMLImageElement).style.display = 'none'">
          <div class="skin-thumb-placeholder">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
          </div>
          <!-- 状态角标 -->
          <div v-if="isActive(bg.id)" class="skin-badge active-badge">使用中</div>
          <div v-else-if="isOwned(bg.id)" class="skin-badge owned-badge">已拥有</div>
        </div>
        <div class="skin-info">
          <div class="skin-name">{{ bg.name }}</div>
          <div class="skin-price-row">
            <template v-if="isActive(bg.id)">
              <span class="skin-status-text active-text">当前背景</span>
            </template>
            <template v-else-if="isOwned(bg.id)">
              <span class="skin-status-text owned-text">已拥有</span>
            </template>
            <template v-else>
              <span class="skin-price">
                <span class="price-icon">◆</span>
                {{ bg.price }}
              </span>
            </template>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="backgroundList.length === 0" class="skin-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
        <span>将图片放入 premium-assets/backgrounds 文件夹</span>
      </div>
    </div>

    <!-- 兑换确认弹窗 -->
    <Teleport to="body">
      <Transition name="popup-fade">
        <div v-if="bgConfirmTarget" class="bg-confirm-overlay" @click.self="cancelPurchase">
          <div class="bg-confirm-card">
            <h3 class="bg-confirm-title">确认兑换</h3>
            <div v-if="confirmBgItem" class="bg-confirm-body">
              <div class="bg-confirm-name">{{ confirmBgItem.name }}</div>
              <div class="bg-confirm-price">
                <span class="price-icon">◆</span>
                <span class="bg-confirm-price-num">{{ confirmBgItem.price }}</span>
                <span class="bg-confirm-price-label">积分</span>
              </div>
              <div class="bg-confirm-balance">
                当前余额：{{ cloudUser?.points ?? 0 }} 积分
              </div>
            </div>
            <div class="bg-confirm-actions">
              <button
                type="button"
                class="bg-confirm-btn primary"
                :disabled="bgPurchasing"
                @click="confirmPurchase"
              >
                {{ bgPurchasing ? '兑换中...' : '确认兑换' }}
              </button>
              <button type="button" class="bg-confirm-btn secondary" @click="cancelPurchase">
                取消
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<style scoped>
/* ── 界面背景 ── */
.skin-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.skin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.skin-toolbar-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.7);
  letter-spacing: 0.04em;
}

.skin-reset-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(248, 250, 252, 0.6);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.skin-reset-btn:hover:not(.disabled) {
  border-color: rgba(212, 175, 55, 0.4);
  color: rgba(212, 175, 55, 0.9);
  background: rgba(212, 175, 55, 0.08);
}

.skin-reset-btn.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.skin-grid {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 20px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-content: start;
  cursor: grab;
  user-select: none;
}

.skin-grid::-webkit-scrollbar {
  width: 5px;
}

.skin-grid::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 3px;
}

.skin-grid::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.3);
  border-radius: 3px;
}

.skin-grid::-webkit-scrollbar-thumb:hover {
  background: rgba(212, 175, 55, 0.5);
}

.skin-card {
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.1);
  cursor: pointer;
  transition: all 0.25s ease;
}

.skin-card:hover {
  border-color: rgba(212, 175, 55, 0.4);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3), 0 0 12px rgba(212, 175, 55, 0.08);
  transform: translateY(-2px);
}

.skin-card.active {
  border-color: rgba(212, 175, 55, 0.6);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.15);
}

.skin-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: rgba(15, 17, 21, 0.8);
}

.skin-thumb-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.skin-thumb-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(148, 163, 184, 0.2);
}

.skin-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  z-index: 2;
}

.active-badge {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.95), rgba(180, 140, 30, 0.9));
  color: #1a1206;
}

.skin-info {
  padding: 8px 10px;
}

.skin-name {
  font-size: 12px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.9);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.03em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skin-price-row {
  margin-top: 2px;
  display: flex;
  align-items: center;
}

.skin-status-text {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.active-text {
  color: rgba(212, 175, 55, 0.85);
}

.owned-text {
  color: rgba(148, 163, 184, 0.5);
}

.skin-price {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(234, 179, 8, 0.9);
}

.skin-price .price-icon {
  font-size: 9px;
}

.skin-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: rgba(148, 163, 184, 0.35);
  font-size: 12px;
  text-align: center;
}

.skin-balance {
  display: flex;
  align-items: center;
  gap: 5px;
}

.balance-icon {
  font-size: 12px;
  color: rgba(212, 175, 55, 0.9);
}

.balance-num {
  font-size: 16px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.9);
  font-variant-numeric: tabular-nums;
}

.balance-label {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.5);
}

.skin-card.owned {
  border-color: rgba(148, 163, 184, 0.2);
}

.owned-badge {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(248, 250, 252, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

/* ── 兑换确认弹窗 ── */
.bg-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.bg-confirm-card {
  width: 320px;
  padding: 24px;
  border: 1px solid rgba(212, 175, 55, 0.35);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.4), 0 0 20px rgba(212, 175, 55, 0.08);
}

.bg-confirm-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.95);
  text-align: center;
  font-family: 'Noto Serif SC', serif;
}

.bg-confirm-body {
  text-align: center;
}

.bg-confirm-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.95);
  font-family: 'Noto Serif SC', serif;
}

.bg-confirm-price {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 14px;
}

.bg-confirm-price .price-icon {
  font-size: 12px;
  color: rgba(234, 179, 8, 0.85);
}

.bg-confirm-price-num {
  font-size: 22px;
  font-weight: 800;
  color: rgba(234, 179, 8, 0.95);
  font-variant-numeric: tabular-nums;
}

.bg-confirm-price-label {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.5);
}

.bg-confirm-balance {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.45);
  margin-top: 6px;
}

.bg-confirm-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.bg-confirm-btn {
  flex: 1;
  padding: 8px 0;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.bg-confirm-btn.primary {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.9), rgba(180, 140, 30, 0.85));
  color: #1a1206;
}

.bg-confirm-btn.primary:hover {
  filter: brightness(1.1);
}

.bg-confirm-btn.primary:disabled {
  opacity: 0.5;
  cursor: wait;
}

.bg-confirm-btn.secondary {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.5);
}

.bg-confirm-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.1);
}

.popup-fade-enter-active,
.popup-fade-leave-active {
  transition: opacity 0.2s ease;
}

.popup-fade-enter-from,
.popup-fade-leave-to {
  opacity: 0;
}
</style>
