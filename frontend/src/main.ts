import { definePreset } from '@primeuix/themes'
import Lara from '@primeuix/themes/lara'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import { registerDomainRoutes } from '@/utils/domainPacks'
import { initTelemetry } from '@/utils/telemetry'
import App from './App.vue'
import './utils/storageMigration'
import './style.css'
import 'virtual:uno.css'

const router = createRouter({
  history: createWebHashHistory(),
  // 卷162：核心路由保持静态（不受领域包影响），领域专属路由在启动时
  // 由 registerDomainRoutes() 从 GET /api/domains 动态注入。
  routes: [
    { path: '/', component: () => import('@/views/PanelView.vue') },
    { path: '/chat', component: () => import('@/views/MessageView.vue') },
    { path: '/model', component: () => import('@/views/TravelView.vue') },
    // 论坛功能已下线（后端 /forum/api/* 不再提供），入口统一重定向回首页；src/forum/ 保留待复活
    { path: '/forum', redirect: '/' },
    { path: '/forum/:pathMatch(.*)*', redirect: '/' },
    { path: '/memory', component: () => import('@/views/MemoryView.vue') },
    { path: '/knowledge', component: () => import('@/views/KnowledgeView.vue') },
    { path: '/papers', component: () => import('@/views/PapersView.vue') },
    { path: '/mind', component: () => import('@/views/MindView.vue') },
    { path: '/skill', component: () => import('@/views/SkillView.vue') },
    { path: '/eln', component: () => import('@/views/ElnView.vue') },
    { path: '/data', component: () => import('@/views/DataView.vue') },
    // 设置页子路由化（卷181-A）：/config/<tab> 可直达；无参等价旧行为（audio=原 terminal）
    // 旧链接 ?tab=terminal 由 ConfigView 内重定向到 /config/audio（兼容）
    // agent 子页（卷181-C）：干员设置入口页（AgentSettingsDialog 保留弹窗，此处提供统一入口）
    {
      path: '/config/:tab(model|memory|audio|notifications|agent|tools)?',
      component: () => import('@/views/ConfigView.vue'),
    },
    { path: '/market', component: () => import('@/views/MarketView.vue') },
    { path: '/float', component: () => import('@/views/FloatingView.vue') },
    { path: '/radio', component: () => import('@/views/RadioView.vue') },
    { path: '/voice-eln', component: () => import('@/views/VoiceElnView.vue') },
  ],
})

// 动态注册领域路由：失败时不阻塞应用启动（领域功能降级，核心路由照常可用）
registerDomainRoutes(router).catch((err) => {
  console.warn('[domains] 领域路由注册失败，已降级为仅核心路由', err)
})

initTelemetry(router)

createApp(App)
  .use(PrimeVue, {
    theme: {
      preset: definePreset(Lara, {
        semantic: {
          // Lumo 设计系统 v1 主色：质谱蓝（docs/lumo-design-system-v1.md）
          primary: {
            50: '#eef4ff',
            100: '#dbe7ff',
            200: '#b6cdff',
            300: '#8ab0ff',
            400: '#6696ff',
            500: '#4f8cff',
            600: '#3a6fe0',
            700: '#2d5bb5',
            800: '#24488f',
            900: '#1c386e',
            950: '#12264d',
          },
        },
      }),
      options: {
        darkModeSelector: '.p-dark',
      },
    },
  })
  .use(ToastService)
  .use(router)
  .mount('#app')
