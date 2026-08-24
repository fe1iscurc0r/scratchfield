<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useLink } from 'vue-router'
import API from '@/api/core'
import brain from '@/assets/icons/brain.png'
import chip from '@/assets/icons/chip.png'
import knowledgeIcon from '@/assets/icons/chip.png'
import market from '@/assets/icons/market.svg'
import naga from '@/assets/icons/naga.png'
import toolkit from '@/assets/icons/toolkit.png'
import ArkButton from '@/components/ArkButton.vue'
import { useParallax } from '@/composables/useParallax'
import { CONFIG } from '@/utils/config'

const { height } = useWindowSize()
const scale = computed(() => height.value / 720)

const { rx, ry, tx, ty } = useParallax({ rotateX: 5, rotateY: 4, translateX: 15, translateY: 10, invertRotate: true })

function enterFloatingMode() {
  CONFIG.value.floating.enabled = true
  window.electronAPI?.floating.enter()
}

// ── 本地应用启动（NEKO / HamLog） ──
const toast = useToast()
const launching = ref('')
const appStatus = ref({
  neko: { running: false, detail: '' },
  hamlog: { running: false, detail: '' },
})

async function refreshAppStatus() {
  try {
    appStatus.value = await API.getAppsLaunchStatus()
  }
  catch { /* 后端未就绪时保持上次状态 */ }
}

let statusTimer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  refreshAppStatus()
  statusTimer = setInterval(refreshAppStatus, 20000)
})
onUnmounted(() => {
  if (statusTimer)
    clearInterval(statusTimer)
})

async function launchLocalApp(app: 'neko' | 'hamlog') {
  if (launching.value)
    return
  launching.value = app
  try {
    const res = await API.launchLocalApp(app)
    toast.add({
      severity: res.status === 'success' ? 'success' : 'error',
      summary: app === 'neko' ? 'NEKO' : 'HamLog',
      detail: res.message,
      life: 6000,
    })
    refreshAppStatus()
  }
  catch (e: any) {
    toast.add({
      severity: 'error',
      summary: '启动失败',
      detail: e?.response?.data?.detail || e.message,
      life: 6000,
    })
  }
  finally {
    launching.value = ''
  }
}
</script>

<template>
  <div class="flex flex-col items-start justify-center px-1/16">
    <!-- 固定宽度：四行等宽对齐，不再由内容撑出长短不一的空块 -->
    <div
      class="grid w-130 grid-rows-4 gap-3 *:gap-3 will-change-transform select-none" :style="{
        transformOrigin: 'left',
        transform: `perspective(1000px) rotateX(${rx}deg) rotateY(${8 + ry}deg) translate(${tx}px, ${ty}px) scale(${scale})`,
      }"
    >
      <div class="relative size-full">
        <div class="absolute -left-12 right-1/2 top-2 bottom-2">
          <ArkButton class="size-full bg-#f00! z-1" disabled>
            <div class="size-full">
              陆墨
            </div>
          </ArkButton>
        </div>
        <ArkButton class="size-full" :icon="naga" @click="useLink({ to: '/chat' }).navigate">
          <div class="size-full flex items-center justify-end mr-3em text-3xl">
            对话
          </div>
        </ArkButton>
      </div>
      <div class="grid grid-cols-3">
        <ArkButton size="md" :icon="brain" title="记忆<br>云海" @click="useLink({ to: '/mind' }).navigate" />
        <ArkButton size="md" :icon="knowledgeIcon" title="知识库<br>MatChat" @click="useLink({ to: '/knowledge' }).navigate" />
        <ArkButton size="md" :icon="toolkit" title="技能<br>工坊" @click="useLink({ to: '/skill' }).navigate" />
      </div>
      <!-- 悬浮按钮收回格内（原先 absolute 外凸会遮挡 Live2D） -->
      <div class="grid grid-cols-2 min-w-0">
        <ArkButton size="md" class="min-w-0" title="悬浮<br>球" @click="enterFloatingMode" />
        <ArkButton size="md" class="min-w-0" :icon="chip" title="终端<br>设置" @click="useLink({ to: '/config' }).navigate" />
      </div>
      <div class="grid grid-cols-3">
        <ArkButton size="md" class="market-btn" :icon="market" title="枢机<br>集市" @click="useLink({ to: '/market' }).navigate" />
        <ArkButton size="md" :disabled="launching === 'hamlog'" @click="launchLocalApp('hamlog')">
          <div class="px-2 py-2.5 flex items-center gap-1.5 whitespace-nowrap">
            <span class="app-dot" :class="appStatus.hamlog.running ? 'app-dot-on' : 'app-dot-off'" />
            HamLog
          </div>
        </ArkButton>
        <ArkButton size="md" :disabled="launching === 'neko'" @click="launchLocalApp('neko')">
          <div class="px-2 py-2.5 flex items-center gap-1.5 whitespace-nowrap">
            <span class="app-dot" :class="appStatus.neko.running ? 'app-dot-on' : 'app-dot-off'" />
            NEKO
          </div>
        </ArkButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 本地应用状态点：绿=运行中，灰=未运行 */
.app-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.app-dot-on {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.8);
}

.app-dot-off {
  background: rgba(0, 0, 0, 0.25);
}
</style>
