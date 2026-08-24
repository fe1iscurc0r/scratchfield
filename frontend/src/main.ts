import './utils/storageMigration'
import { definePreset } from '@primeuix/themes'
import Lara from '@primeuix/themes/lara'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { createApp } from 'vue'

import { createRouter, createWebHashHistory } from 'vue-router'
import { initTelemetry } from '@/utils/telemetry'
import App from './App.vue'
import './style.css'
import 'virtual:uno.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: () => import('@/views/PanelView.vue') },
    { path: '/chat', component: () => import('@/views/MessageView.vue') },
    { path: '/model', component: () => import('@/views/TravelView.vue') },
    // 论坛功能已下线（后端 /forum/api/* 不再提供），入口统一重定向回首页；src/forum/ 保留待复活
    { path: '/forum', redirect: '/' },
    { path: '/forum/:pathMatch(.*)*', redirect: '/' },
    { path: '/memory', component: () => import('@/views/MemoryView.vue') },
    { path: '/knowledge', component: () => import('@/views/KnowledgeView.vue') },
    { path: '/mind', component: () => import('@/views/MindView.vue') },
    { path: '/skill', component: () => import('@/views/SkillView.vue') },
    { path: '/config', component: () => import('@/views/ConfigView.vue') },
    { path: '/market', component: () => import('@/views/MarketView.vue') },
    { path: '/float', component: () => import('@/views/FloatingView.vue') },
  ],
})

initTelemetry(router)

createApp(App)
  .use(PrimeVue, {
    theme: {
      preset: definePreset(Lara),
      options: {
        darkModeSelector: '.p-dark',
      },
    },
  })
  .use(ToastService)
  .use(router)
  .mount('#app')
