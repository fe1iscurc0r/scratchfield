<script setup lang="ts">
/**
 * 全局侧边栏（卷150 任务A）——工作态导航，常驻左侧、可折叠为图标条。
 *
 * 对接约定（挂载点：App.vue 经典模式分支，与 TitleBar 同级）：
 *   <AppSidebar v-if="!isFloatingMode" />
 *   — 悬浮球模式不渲染（工单边界）
 *   — 折叠状态经 localStorage('lumo-sidebar-collapsed') 持久化
 *   — 当前项高亮 = route.path 精确匹配（utils/navigation.ts 为唯一真源）
 *
 * 样式遵守 Lumo 设计系统 v1（style.css CSS 变量），不引主题系统。
 */
import { useStorage } from '@vueuse/core'
import { computed, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAV_GROUPS } from '@/utils/navigation'

const router = useRouter()
const route = useRoute()

/** 折叠状态持久化（验收：折叠/展开状态持久化 localStorage） */
const collapsed = useStorage('lumo-sidebar-collapsed', false)

/**
 * 折叠态写入全局 CSS 变量 —— 主内容区（App.vue）引用同一变量让位：
 *   padding-left: var(--lumo-sidebar-w)
 * 组件卸载（悬浮球模式）时置 0。
 */
const SIDEBAR_W = '176px'
const SIDEBAR_W_COLLAPSED = '52px'

watch(collapsed, (c) => {
  document.documentElement.style.setProperty('--lumo-sidebar-w', c ? SIDEBAR_W_COLLAPSED : SIDEBAR_W)
}, { immediate: true })

const currentPath = computed(() => route.path)

function go(to: string) {
  router.push(to)
}

function toggle() {
  collapsed.value = !collapsed.value
}

/** 卸载（悬浮球模式）时清零让位变量，主内容回满宽 */
onBeforeUnmount(() => {
  document.documentElement.style.setProperty('--lumo-sidebar-w', '0px')
})
</script>

<template>
  <nav
    class="app-sidebar"
    :class="{ collapsed }"
    aria-label="全局导航"
    :data-collapsed="collapsed"
  >
    <button
      class="sb-toggle"
      :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
      :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
      @click="toggle"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15 18l-6-6 6-6" />
      </svg>
    </button>

    <div class="sb-scroll">
      <div v-for="group in NAV_GROUPS" :key="group.key" class="sb-group">
        <div v-if="!collapsed" class="sb-group-label">{{ group.label }}</div>
        <button
          v-for="item in group.items"
          :key="item.to"
          class="sb-item"
          :class="{ active: currentPath === item.to }"
          :title="collapsed ? item.label : undefined"
          :data-nav-to="item.to"
          @click="go(item.to)"
        >
          <!-- eslint-disable-next-line vue/no-v-html —— 内嵌 SVG（navigation.ts 常量表，非用户输入） -->
          <span class="sb-icon" v-html="item.icon" />
          <span v-if="!collapsed" class="sb-label">{{ item.label }}</span>
          <span v-else class="sb-label sb-label-mini">{{ item.label.slice(0, 1) }}</span>
        </button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.app-sidebar {
  position: fixed;
  top: 32px; /* TitleBar 高度 */
  left: 0;
  bottom: 0;
  width: 176px;
  display: flex;
  flex-direction: column;
  z-index: 900;
  background: rgba(13, 17, 23, 0.92);
  border-right: 1px solid var(--lumo-border);
  backdrop-filter: blur(8px);
  transition: width 0.18s ease;
}

.app-sidebar.collapsed {
  width: 52px;
}

.sb-toggle {
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--lumo-text-faint);
  cursor: pointer;
  transition: color 0.15s, background-color 0.15s;
}

.sb-toggle:hover {
  color: var(--lumo-text);
  background: rgba(255, 255, 255, 0.04);
}

.app-sidebar.collapsed .sb-toggle :deep(svg) {
  transform: rotate(180deg);
}

.sb-scroll {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--lumo-space-2) var(--lumo-space-1);
}

.sb-group {
  margin-bottom: var(--lumo-space-4);
}

.sb-group-label {
  padding: 0 var(--lumo-space-2);
  margin-bottom: var(--lumo-space-1);
  font-size: 11px;
  line-height: 1.6;
  color: var(--lumo-text-faint);
  letter-spacing: 0.08em;
  user-select: none;
  white-space: nowrap;
}

.sb-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--lumo-space-2);
  padding: var(--lumo-space-2);
  border: none;
  border-radius: var(--lumo-radius-md);
  background: transparent;
  color: var(--lumo-text-dim);
  font-size: 13px;
  font-family: var(--lumo-font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.12s, color 0.12s;
}

.sb-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--lumo-text);
}

.sb-item.active {
  background: var(--lumo-primary-tint);
  color: var(--lumo-primary);
}

.sb-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.sb-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.sb-label-mini {
  font-size: 10px;
  color: var(--lumo-text-faint);
  display: none;
}

/* 折叠态：仅图标（hover 时浮出 tooltip 走 title 属性） */
.app-sidebar.collapsed .sb-item {
  justify-content: center;
  padding: var(--lumo-space-2) 0;
}

/* 滚动条细化 */
.sb-scroll::-webkit-scrollbar {
  width: 4px;
}

.sb-scroll::-webkit-scrollbar-thumb {
  background: var(--lumo-border);
  border-radius: 2px;
}
</style>
