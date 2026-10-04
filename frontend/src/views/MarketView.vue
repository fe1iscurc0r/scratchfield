<!-- 枢机集市壳（卷190-B2：4 个 tab 拆至 market/ 子组件自治，通用拖动与域逻辑拆至 market/composables/*；纯搬移，行为零变化） -->
<script setup lang="ts">
import { h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MarketAlbumTab from './market/MarketAlbumTab.vue'
import MarketCharacterTab from './market/MarketCharacterTab.vue'
import MarketRechargeTab from './market/MarketRechargeTab.vue'
import MarketSkinTab from './market/MarketSkinTab.vue'

const router = useRouter()
const route = useRoute()

const tabs = [
  { id: 'album', label: '音之巷' },
  { id: 'memory-skin', label: '角色注册' },
  { id: 'skin', label: '界面背景' },
  { id: 'recharge', label: '模型充值' },
] as const

const svgIcon = (...paths: string[]) => h('svg', { 'viewBox': '0 0 24 24', 'fill': 'none', 'stroke': 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'class': 'tab-icon-svg' }, paths.map(d => h('path', { d })))

const tabIcons: Record<string, { render: () => ReturnType<typeof h> }> = {
  'album': { render: () => svgIcon('M9 18V5l12-2v13', 'M9 18a3 3 0 1 0 6 0 9 9 0 0 0 6 0') },
  'skin': { render: () => svgIcon('M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z', 'M21 15l-5-5L5 21') },
  'memory-skin': { render: () => svgIcon('M2 10c3 0 5 2 8 0s5-2 8 0', 'M2 14c3 0 5 2 8 0s5-2 8 0') },
  'recharge': { render: () => svgIcon('M12 2L3 9l4 12h10l4-12-9-7z') },
}

type TabId = typeof tabs[number]['id']
const initTab = route.query.tab as string | undefined
const activeTab = ref<TabId>(
  tabs.some(t => t.id === initTab) ? initTab as TabId : 'skin',
)
</script>

<template>
  <div class="market-page">
    <!-- 顶部栏：返回 + 标题 -->
    <header class="market-header">
      <div class="header-left">
        <button type="button" class="back-btn" title="返回" @click="router.back">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <h1 class="market-title">
          枢机集市
        </h1>
      </div>
    </header>

    <!-- 标签导航 -->
    <nav class="market-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <component :is="tabIcons[tab.id]" />
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </nav>

    <!-- 内容区（4 个 tab 自治组件） -->
    <main class="market-content">
      <MarketAlbumTab v-show="activeTab === 'album'" :active-tab="activeTab" />
      <MarketCharacterTab v-show="activeTab === 'memory-skin'" :active-tab="activeTab" />
      <MarketSkinTab v-show="activeTab === 'skin'" :active-tab="activeTab" />
      <MarketRechargeTab v-show="activeTab === 'recharge'" :active-tab="activeTab" />
    </main>
  </div>
</template>

<style scoped>
/* ── 面板容器：窗口宽度 × 3/4 高度，垂直居中 ── */
.market-page {
  position: fixed;
  top: 12.5vh;         /* (100 - 75) / 2 = 12.5 → 垂直居中 */
  left: 0;
  right: 0;
  height: 75vh;
  z-index: 200;
  display: flex;
  flex-direction: column;
  background: rgba(15, 17, 21, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 16px;
  border: 1px solid rgba(212, 175, 55, 0.3);
  overflow: hidden;
  /* 不设自定义 animation，由 Vue Router Transition (slide-in / slide-out) 接管 */
}

.market-page::before {
  content: '';
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(251, 191, 36, 0.9) 50%,
    transparent 100%
  );
  z-index: 1;
  pointer-events: none;
}

/* ── 顶部 Header ── */
.market-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px 8px;
  background: rgba(20, 22, 28, 0.5);
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  flex-shrink: 0;
  min-height: 48px;
  position: relative;
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(248, 250, 252, 0.75);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.13);
  border-color: rgba(212, 175, 55, 0.45);
  color: #fff;
}

.market-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
}

/* ── Tab 栏 ── */
.market-tabs {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  width: 100%;
  flex-shrink: 0;
  background: rgba(12, 14, 18, 0.8);
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  min-height: 56px;
}

.tab-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 8px 4px 10px;
  border: none;
  border-radius: 0;
  border-right: 1px solid rgba(148, 163, 184, 0.1);
  background: transparent;
  color: rgba(248, 250, 252, 0.45);
  font-size: 11px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
  white-space: nowrap;
  position: relative;
  overflow: hidden;
}

.tab-btn:last-child {
  border-right: none;
}

.tab-btn:hover {
  color: rgba(248, 250, 252, 0.85);
  background: rgba(255, 255, 255, 0.05);
}

.tab-btn.active {
  color: rgba(251, 191, 36, 0.98);
  background: rgba(251, 191, 36, 0.08);
}

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 10%,
    rgba(251, 191, 36, 0.9) 50%,
    transparent 90%
  );
  border-radius: 1px 1px 0 0;
}

.tab-btn.active .tab-icon-svg {
  color: rgba(251, 191, 36, 0.98);
}

.tab-icon-svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: inherit;
}

.tab-label {
  white-space: nowrap;
  line-height: 1;
}

/* ── 内容区 ── */
.market-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
</style>
