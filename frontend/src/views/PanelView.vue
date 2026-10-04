<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import Popover from 'primevue/popover'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useLink, useRouter } from 'vue-router'
import API from '@/api/core'
import brainIcon from '@/assets/icons/brain.png'
import chip from '@/assets/icons/chip.png'
import market from '@/assets/icons/market.svg'
import naga from '@/assets/icons/naga.png'
import toolkit from '@/assets/icons/toolkit.png'
import ArkButton from '@/components/ArkButton.vue'
import DomainSwitcher from '@/components/DomainSwitcher.vue'
import { useParallax } from '@/composables/useParallax'
import { CONFIG } from '@/utils/config'
import { feedback } from '@/utils/feedback'

const { height } = useWindowSize()
const scale = computed(() => height.value / 720)

const { rx, ry, tx, ty } = useParallax({ rotateX: 5, rotateY: 4, translateX: 15, translateY: 10, invertRotate: true })

function enterFloatingMode() {
  CONFIG.value.floating.enabled = true
  window.electronAPI?.floating.enter()
}

// ── 本地应用启动（NEKO / HamLog） ──
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
    if (res.status === 'success')
      feedback.success(app === 'neko' ? 'NEKO 已启动' : 'HamLog 已启动', res.message)
    else
      feedback.error(app === 'neko' ? 'NEKO' : 'HamLog', res.message)
    refreshAppStatus()
  }
  catch (e: any) {
    feedback.error('启动失败', e?.response?.data?.detail || e.message)
  }
  finally {
    launching.value = ''
  }
}

// ── 导航收纳（11-01）：「知识▸」「射频大脑▸」单击直达 + 二级 Popover ──
interface NavMenuItem {
  key: string
  label: string
  icon: string
  to?: string
  action?: () => void
  statusKey?: 'hamlog'
  disabled?: () => boolean
}

// 内嵌 SVG 菜单图标：stroke 继承 currentColor，hover 变色免费
function menuIcon(paths: string) {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
}

const knowledgeMenu: NavMenuItem[] = [
  { key: 'matchat', label: 'MatChat', to: '/knowledge', icon: menuIcon('<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>') },
  { key: 'eln', label: 'ELN', to: '/eln', icon: menuIcon('<path d="M10 2v7.5a2 2 0 0 1-.2.9L4.7 20.5a1 1 0 0 0 .9 1.5h12.8a1 1 0 0 0 .9-1.5L14.2 10.4a2 2 0 0 1-.2-.9V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>') },
  { key: 'voice-eln', label: '语音ELN', to: '/voice-eln', icon: menuIcon('<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/>') },
  { key: 'data', label: '数据', to: '/data', icon: menuIcon('<path d="M21 5c0 1.66-4 3-9 3S3 6.66 3 5s4-3 9-3 9 1.34 9 3z"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>') },
  { key: 'papers', label: '论文', to: '/papers', icon: menuIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>') },
]

// hamlog 迁入射频大脑二级菜单：launchLocalApp 调用与 launching/disabled 状态原样保留
const radioMenu: NavMenuItem[] = [
  { key: 'radio', label: '频谱', to: '/radio', icon: menuIcon('<path d="M4 20V10"/><path d="M9 20V4"/><path d="M14 20V13"/><path d="M19 20V7"/>') },
  { key: 'hamlog', label: '无线电日志', action: () => launchLocalApp('hamlog'), statusKey: 'hamlog', disabled: () => launching.value === 'hamlog', icon: menuIcon('<circle cx="12" cy="12" r="2"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M19.1 4.9C23 8.8 23 15.2 19.1 19.1"/>') },
]

// 更多▸（w100-01）：抽象二级视图统一收纳——思维旅行 /model、记忆视图 /memory
// （此前两视图路由存在于 main.ts 但首页无入口）
const moreMenu: NavMenuItem[] = [
  { key: 'travel', label: '思维旅行', to: '/model', icon: menuIcon('<circle cx="12" cy="12" r="9"/><path d="M12 3a15 15 0 0 1 0 18"/><path d="M3 12h18"/>') },
  { key: 'memory', label: '记忆视图', to: '/memory', icon: menuIcon('<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7v5l3 2"/>') },
]

const router = useRouter()
// 单一事实源：同时只允许开一个二级菜单
type NavMenuName = 'knowledge' | 'radio' | 'more'
const openMenu = ref<'' | NavMenuName>('')
const knowledgePop = ref<{ show: (e: Event) => void, hide: () => void } | null>(null)
const radioPop = ref<{ show: (e: Event) => void, hide: () => void } | null>(null)
const morePop = ref<{ show: (e: Event) => void, hide: () => void } | null>(null)

function toggleNav(name: NavMenuName, e: Event) {
  const refs: Record<NavMenuName, typeof knowledgePop> = {
    knowledge: knowledgePop,
    radio: radioPop,
    more: morePop,
  }
  const target = refs[name].value
  if (openMenu.value === name) {
    target?.hide()
    return
  }
  for (const [k, r] of Object.entries(refs)) {
    if (k !== name)
      r.value?.hide()
  }
  target?.show(e)
  openMenu.value = name
}

// dismissable 外点关闭、toggle 关闭、路由卸载统一经 @hide 收敛回 openMenu
function onNavHide(name: NavMenuName) {
  if (openMenu.value === name)
    openMenu.value = ''
}

function hideAllNav() {
  knowledgePop.value?.hide()
  radioPop.value?.hide()
  morePop.value?.hide()
}

function onNavItemClick(item: NavMenuItem) {
  hideAllNav()
  if (item.action)
    item.action()
  else if (item.to)
    router.push(item.to)
}

// 长按 500ms 展开二级菜单；命中后吞掉 pointerup 衍生的 click，单击直达不受影响
let lpTimer: ReturnType<typeof setTimeout> | null = null
// 监听器返回后 event.currentTarget 被 DOM 重置为 null，而 PrimeVue Popover.show()
// 同步读它定位并判定 isTargetClicked——必须在监听器栈内快照
let lpCtx: { currentTarget: HTMLElement } | null = null
const longPressFired = ref(false)

function pressStart(name: NavMenuName, e: PointerEvent) {
  pressEnd()
  longPressFired.value = false
  lpCtx = { currentTarget: e.currentTarget as HTMLElement }
  lpTimer = setTimeout(() => {
    lpTimer = null
    longPressFired.value = true
    toggleNav(name, lpCtx as unknown as Event)
  }, 500)
}

function pressEnd() {
  if (lpTimer) {
    clearTimeout(lpTimer)
    lpTimer = null
  }
}

function navClick(to: string) {
  if (longPressFired.value) {
    longPressFired.value = false
    return
  }
  hideAllNav()
  router.push(to)
}
</script>

<template>
  <div class="flex flex-col items-start justify-center px-1/16">
    <!-- 领域切换器（卷162）：仅当存在 ≥2 个领域包时渲染，default 单包下无任何 DOM -->
    <DomainSwitcher />
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
        <ArkButton size="md" :icon="brainIcon" title="记忆<br>云海" @click="useLink({ to: '/mind' }).navigate" />
        <ArkButton
          size="md" class="min-w-0" :icon="brainIcon"
          @pointerdown="pressStart('knowledge', $event)" @pointerup="pressEnd" @pointerleave="pressEnd" @pointercancel="pressEnd"
          @contextmenu.prevent @click="navClick('/knowledge')"
        >
          <div class="px-2 py-2.5 pr-4em">
            <div class="whitespace-nowrap">
              知识库<br>MatChat
            </div>
          </div>
          <span
            class="nav-badge" :class="{ 'is-open': openMenu === 'knowledge' }"
            @pointerdown.stop @click.stop="toggleNav('knowledge', $event)"
          >
            <svg viewBox="0 0 8 12" class="w-1.5 h-2"><path d="M2 1l4 5-4 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </span>
        </ArkButton>
        <ArkButton size="md" :icon="toolkit" title="技能<br>工坊" @click="useLink({ to: '/skill' }).navigate" />
      </div>
      <!-- 悬浮按钮收回格内（原先 absolute 外凸会遮挡 Live2D）；射频大脑插入悬浮球与终端设置之间，三键各 1/3 宽 -->
      <div class="grid grid-cols-3 min-w-0">
        <ArkButton size="md" class="min-w-0" title="悬浮<br>球" @click="enterFloatingMode" />
        <ArkButton
          size="md" class="min-w-0" :icon="brainIcon"
          @pointerdown="pressStart('radio', $event)" @pointerup="pressEnd" @pointerleave="pressEnd" @pointercancel="pressEnd"
          @contextmenu.prevent @click="navClick('/radio')"
        >
          <div class="px-2 py-2.5 pr-4em">
            <div class="whitespace-nowrap">
              射频<br>大脑
            </div>
          </div>
          <span
            class="nav-badge" :class="{ 'is-open': openMenu === 'radio' }"
            @pointerdown.stop @click.stop="toggleNav('radio', $event)"
          >
            <svg viewBox="0 0 8 12" class="w-1.5 h-2"><path d="M2 1l4 5-4 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </span>
        </ArkButton>
        <ArkButton size="md" class="min-w-0" :icon="chip" title="终端<br>设置" @click="useLink({ to: '/config' }).navigate" />
      </div>
      <!-- hamlog 已迁入射频大脑▸ 二级菜单：外设不再占格，NEKO 独立按钮与枢机集市对齐成两键；w100-01 补「更多▸」收纳抽象二级视图 -->
      <div class="grid grid-cols-3">
        <ArkButton size="md" class="market-btn" :icon="market" title="枢机<br>集市" @click="useLink({ to: '/market' }).navigate" />
        <ArkButton size="md" :disabled="launching === 'neko'" @click="launchLocalApp('neko')">
          <div class="px-2 py-2.5 flex items-center gap-1.5 whitespace-nowrap">
            <span class="app-dot" :class="appStatus.neko.running ? 'app-dot-on' : 'app-dot-off'" />
            NEKO
          </div>
        </ArkButton>
        <ArkButton
          size="md" class="min-w-0"
          @pointerdown="pressStart('more', $event)" @pointerup="pressEnd" @pointerleave="pressEnd" @pointercancel="pressEnd"
          @contextmenu.prevent @click="navClick('/model')"
        >
          <div class="px-2 py-2.5 pr-4em">
            <div class="whitespace-nowrap">
              更多
            </div>
          </div>
          <span
            class="nav-badge" :class="{ 'is-open': openMenu === 'more' }"
            @pointerdown.stop @click.stop="toggleNav('more', $event)"
          >
            <svg viewBox="0 0 8 12" class="w-1.5 h-2"><path d="M2 1l4 5-4 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" /></svg>
          </span>
        </ArkButton>
      </div>
    </div>

    <!-- 知识▸ 二级菜单：路由已全部存在于 main.ts，只复用不新增 -->
    <Popover ref="knowledgePop" append-to="body" :pt="{ root: { class: 'nav-pop' } }" @hide="onNavHide('knowledge')">
      <div class="w-52 flex flex-col gap-0.5 p-1.5">
        <button
          v-for="item in knowledgeMenu" :key="item.key" :disabled="item.disabled?.()"
          class="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-sans font-medium text-left text-black/80 cursor-pointer transition-colors hover:bg-black/5 hover:text-black active:bg-black/10 disabled:opacity-50 disabled:pointer-events-none"
          @click="onNavItemClick(item)"
        >
          <span class="nav-menu-icon w-4 h-4 shrink-0" v-html="item.icon" />
          <span class="flex-1 whitespace-nowrap">{{ item.label }}</span>
          <span v-if="item.statusKey" class="app-dot" :class="appStatus[item.statusKey].running ? 'app-dot-on' : 'app-dot-off'" />
        </button>
      </div>
    </Popover>

    <!-- 射频大脑▸ 二级菜单：hamlog 迁入，launching/disabled 状态照旧 -->
    <Popover ref="radioPop" append-to="body" :pt="{ root: { class: 'nav-pop' } }" @hide="onNavHide('radio')">
      <div class="w-52 flex flex-col gap-0.5 p-1.5">
        <button
          v-for="item in radioMenu" :key="item.key" :disabled="item.disabled?.()"
          class="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-sans font-medium text-left text-black/80 cursor-pointer transition-colors hover:bg-black/5 hover:text-black active:bg-black/10 disabled:opacity-50 disabled:pointer-events-none"
          @click="onNavItemClick(item)"
        >
          <span class="nav-menu-icon w-4 h-4 shrink-0" v-html="item.icon" />
          <span class="flex-1 whitespace-nowrap">{{ item.label }}</span>
          <span v-if="item.statusKey" class="app-dot" :class="appStatus[item.statusKey].running ? 'app-dot-on' : 'app-dot-off'" />
        </button>
      </div>
    </Popover>

    <!-- 更多▸ 二级菜单（w100-01）：抽象二级视图统一收纳 -->
    <Popover ref="morePop" append-to="body" :pt="{ root: { class: 'nav-pop' } }" @hide="onNavHide('more')">
      <div class="w-52 flex flex-col gap-0.5 p-1.5">
        <button
          v-for="item in moreMenu" :key="item.key" :disabled="item.disabled?.()"
          class="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm font-sans font-medium text-left text-black/80 cursor-pointer transition-colors hover:bg-black/5 hover:text-black active:bg-black/10 disabled:opacity-50 disabled:pointer-events-none"
          @click="onNavItemClick(item)"
        >
          <span class="nav-menu-icon w-4 h-4 shrink-0" v-html="item.icon" />
          <span class="flex-1 whitespace-nowrap">{{ item.label }}</span>
          <span v-if="item.statusKey" class="app-dot" :class="appStatus[item.statusKey].running ? 'app-dot-on' : 'app-dot-off'" />
        </button>
      </div>
    </Popover>
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

/* ▸ 触发器角标：叠在右侧彩色图标右下角，示意此按钮有二级菜单 */
.nav-badge {
  position: absolute;
  right: 4px;
  bottom: 6px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(0, 0, 0, 0.45);
  cursor: pointer;
  transition: transform 0.2s ease, color 0.2s ease;
}

.nav-badge svg {
  transition: transform 0.2s ease;
}

/* 小巧思：二级菜单展开时 ▸ 转 ▾，圆片微放大、颜色加深——旋转即状态 */
.nav-badge.is-open {
  transform: scale(1.15);
  color: rgba(0, 0, 0, 0.8);
}

.nav-badge.is-open svg {
  transform: rotate(90deg);
}

/* v-html 生成的 svg 是 inline，去掉基线空隙 */
.nav-menu-icon svg {
  display: block;
}

/* Popover teleport 到 body，scoped 特性匹配不到，须 :global */
:global(.nav-pop) {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}
</style>
