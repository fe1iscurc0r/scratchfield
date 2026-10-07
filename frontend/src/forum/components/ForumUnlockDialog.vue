<script setup lang="ts">
import Dialog from 'primevue/dialog'
import { computed, ref, watch } from 'vue'

/**
 * 解锁进度弹窗 —— 自 `ForumSidebarRight.vue` 拆出（工单204 任务三）。
 *
 * props：`unlockPercent`（入口按钮与弹窗共用，故由父组件传入）、`userId`（换用户时重置内部状态）。
 * 可见性走 `v-model:visible`。其余状态/常量/computed 全部自治。
 */
const props = defineProps<{ unlockPercent: number, userId?: string, profile?: any }>()
const visible = defineModel<boolean>('visible', { required: true })

const activeEchoIndex = ref(0)
const probeStatus = ref('剧情档案静默中，尚未捕获任何可写回的碎片。')
const pulseActive = ref(false)
interface UnlockMilestone {
  threshold: number
  label: string
  title: string
  description: string
}

const unlockMilestones: UnlockMilestone[] = [
  {
    threshold: 0,
    label: '序章',
    title: '零号扉页',
    description: '刚接入剧情网络，所有线索仍处于封印状态。',
  },
  {
    threshold: 25,
    label: '25%',
    title: '第一碎片',
    description: '开始识别角色背景与最初的支线入口。',
  },
  {
    threshold: 50,
    label: '50%',
    title: '交错回廊',
    description: '可读取多条剧情走向，并解锁隐藏的互动回声。',
  },
  {
    threshold: 75,
    label: '75%',
    title: '深层回路',
    description: '主线与侧线互相缠绕，新的伏笔会开始反向显形。',
  },
  {
    threshold: 100,
    label: '100%',
    title: '终局回响',
    description: '剧情档案完全开启，所有章节与彩蛋全部可追溯。',
  },
]

const echoLibrary: string[] = [
  '剧情板块像一扇锁住的门，真正的钥匙可能藏在一篇看似普通的帖子里。',
  '有些节点不会直接告诉你“已解锁”，它们只会在第二次回看时忽然成立。',
  '当剧情进度仍是 0% 时，最值得注意的往往不是答案，而是反复出现的同一个名字。',
  '你尚未留下任何剧情足迹，但论坛已经开始为你保留第一条回声。',
]

const probeMessages: string[] = [
  '正在比对剧情板块与已读痕迹……仍未发现可归档节点。',
  '正在扫描角色关系网……当前没有可确认的剧情分叉。',
  '正在回放最近的阅读轨迹……封印层保持静默。',
  '正在尝试解译隐藏文本……仍需更多剧情模式浏览记录。',
]
const currentMilestone = computed<UnlockMilestone>(() => {
  let result: UnlockMilestone = unlockMilestones[0]!
  for (const milestone of unlockMilestones) {
    if (props.unlockPercent >= milestone.threshold)
      result = milestone
  }
  return result
})

const nextMilestone = computed(() => {
  return unlockMilestones.find(item => item.threshold > props.unlockPercent) ?? null
})

const currentEcho = computed(() => echoLibrary[activeEchoIndex.value % echoLibrary.length] ?? '')

const intrigueScore = computed(() => {
  const stats = props.profile?.stats
  if (!stats)
    return 0
  return Math.min(100, stats.posts * 4 + stats.replies * 2 + stats.likes + stats.friends * 6)
})

function cycleEcho() {
  activeEchoIndex.value = (activeEchoIndex.value + 1) % echoLibrary.length
}

function runProbe() {
  probeStatus.value = probeMessages[Math.floor(Math.random() * probeMessages.length)] ?? ''
  pulseTimeline()
}

function pulseTimeline() {
  pulseActive.value = false
  requestAnimationFrame(() => {
    pulseActive.value = true
    window.setTimeout(() => {
      pulseActive.value = false
    }, 1100)
  })
}

// 换用户 → 重置本组件内部状态（原在父组件的 watch 里，unlockPercent 那项留父组件）
// 打开时触发一次脉冲动画（原在父组件 openUnlockDialog 内调用，随组件搬）
watch(() => visible.value, (v) => {
  if (v) pulseTimeline()
})

watch(() => props.userId, () => {
  activeEchoIndex.value = 0
  probeStatus.value = '剧情档案静默中，尚未捕获任何可写回的碎片。'
})
</script>

<template>
    <Dialog
      v-model:visible="visible"
      modal
      header="剧情解锁档案"
      class="unlock-dialog"
      :style="{ width: 'min(720px, 92vw)' }"
    >
      <div class="unlock-dialog-body" :class="{ pulsing: pulseActive }">
        <section class="unlock-hero">
          <div class="unlock-hero-copy">
            <div class="unlock-kicker">Unlock Archive</div>
            <h3>{{ currentMilestone.title }}</h3>
            <p>{{ currentMilestone.description }}</p>
          </div>
          <div class="unlock-hero-percent">
            <span>{{ unlockPercent }}%</span>
            <small>剧情解锁率</small>
          </div>
        </section>

        <section class="unlock-progress-panel">
          <div class="unlock-progress-head">
            <span>剧情封印进度</span>
            <span>{{ unlockPercent }} / 100</span>
          </div>
          <div class="unlock-progress-track">
            <div class="unlock-progress-fill" :style="{ width: `${unlockPercent}%` }" />
            <div class="unlock-progress-sheen" />
          </div>
          <div class="unlock-progress-foot">
            <span>当前档案：{{ currentMilestone.label }}</span>
            <span v-if="nextMilestone">下一阶段：{{ nextMilestone.title }}</span>
            <span v-else>全部章节已显影</span>
          </div>
        </section>

        <section class="unlock-milestones">
          <article
            v-for="milestone in unlockMilestones"
            :key="milestone.threshold"
            class="milestone-card"
            :class="{
              reached: unlockPercent >= milestone.threshold,
              current: currentMilestone.threshold === milestone.threshold,
            }"
          >
            <div class="milestone-badge">{{ milestone.label }}</div>
            <div class="milestone-title">{{ milestone.title }}</div>
            <div class="milestone-desc">{{ milestone.description }}</div>
          </article>
        </section>

        <section class="unlock-side-grid">
          <article class="insight-card">
            <div class="card-title">线索回声</div>
            <p>{{ currentEcho }}</p>
            <button class="mini-action-btn" @click="cycleEcho">
              切换线索
            </button>
          </article>

          <article class="insight-card accent">
            <div class="card-title">解码探针</div>
            <p>{{ probeStatus }}</p>
            <button class="mini-action-btn" @click="runProbe">
              模拟解码
            </button>
          </article>
        </section>

        <section class="unlock-side-grid compact">
          <article class="status-card">
            <span class="status-name">剧情潜势</span>
            <span class="status-value">{{ intrigueScore }}%</span>
            <small>按发帖、回帖、互动热度估算你接近剧情线索的概率。</small>
          </article>
          <article class="status-card">
            <span class="status-name">下一步建议</span>
            <span class="status-value">{{ unlockPercent === 0 ? '切到剧情模式' : '继续推进主线' }}</span>
            <small>多浏览剧情板块帖子，未来这里会逐步汇总已解锁章节。</small>
          </article>
        </section>
      </div>
    </Dialog>
</template>

<style scoped>
.unlock-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.unlock-dialog-body.pulsing .unlock-hero,
.unlock-dialog-body.pulsing .unlock-progress-panel {
  box-shadow: 0 0 0 1px rgba(212, 175, 55, 0.18), 0 0 24px rgba(212, 175, 55, 0.12);
}

.unlock-hero,
.unlock-progress-panel,
.insight-card,
.status-card,
.milestone-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  border-radius: 14px;
}

.unlock-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  background:
    radial-gradient(circle at top right, rgba(212, 175, 55, 0.16), transparent 36%),
    rgba(255, 255, 255, 0.03);
}

.unlock-kicker {
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(212, 175, 55, 0.7);
  margin-bottom: 6px;
}

.unlock-hero h3 {
  margin: 0 0 6px;
  font-size: 22px;
  color: rgba(255, 255, 255, 0.92);
  font-family: 'Noto Serif SC', serif;
}

.unlock-hero p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.56);
}

.unlock-hero-percent {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  min-width: 100px;
}

.unlock-hero-percent span {
  font-size: 34px;
  font-weight: 800;
  color: #f3db8c;
  line-height: 1;
}

.unlock-hero-percent small {
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
}

.unlock-progress-panel {
  padding: 16px 18px;
}

.unlock-progress-head,
.unlock-progress-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
}

.unlock-progress-track {
  position: relative;
  height: 12px;
  margin: 10px 0 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
}

.unlock-progress-fill {
  position: relative;
  z-index: 1;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(212, 175, 55, 0.7), rgba(242, 212, 120, 0.95));
  transition: width 0.55s ease;
}

.unlock-progress-sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 0%, rgba(255, 255, 255, 0.16) 45%, transparent 100%);
  transform: translateX(-100%);
  animation: sheen-pass 3.6s linear infinite;
}

.unlock-milestones {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.milestone-card {
  padding: 12px;
  min-height: 132px;
  opacity: 0.58;
  transition: all 0.18s ease;
}

.milestone-card.reached,
.milestone-card.current {
  opacity: 1;
  border-color: rgba(212, 175, 55, 0.2);
}

.milestone-card.current {
  background:
    radial-gradient(circle at top right, rgba(212, 175, 55, 0.14), transparent 46%),
    rgba(255, 255, 255, 0.04);
}

.milestone-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.56);
  font-size: 10px;
  margin-bottom: 10px;
}

.milestone-card.current .milestone-badge,
.milestone-card.reached .milestone-badge {
  background: rgba(212, 175, 55, 0.14);
  color: #f3db8c;
}

.milestone-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 6px;
}

.milestone-desc {
  color: rgba(255, 255, 255, 0.48);
  font-size: 11px;
  line-height: 1.55;
}

.unlock-side-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.unlock-side-grid.compact .status-card {
  min-height: 120px;
}

.insight-card,
.status-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

.insight-card.accent {
  background:
    radial-gradient(circle at top right, rgba(212, 175, 55, 0.1), transparent 40%),
    rgba(255, 255, 255, 0.03);
}

.card-title,
.status-name {
  color: rgba(212, 175, 55, 0.78);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.insight-card p,
.status-card small {
  margin: 0;
  color: rgba(255, 255, 255, 0.58);
  font-size: 12px;
  line-height: 1.65;
}

.status-value {
  color: rgba(255, 255, 255, 0.9);
  font-size: 18px;
  font-weight: 700;
}

.mini-action-btn {
  align-self: flex-start;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.24);
  background: rgba(212, 175, 55, 0.08);
  color: #f3db8c;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
}

.mini-action-btn:hover {
  background: rgba(212, 175, 55, 0.16);
  border-color: rgba(212, 175, 55, 0.36);
}

:deep(.unlock-dialog.p-dialog) {
  border: 1px solid rgba(212, 175, 55, 0.14);
  border-radius: 18px;
  background:
    radial-gradient(circle at top right, rgba(212, 175, 55, 0.08), transparent 30%),
    rgba(17, 17, 17, 0.96);
  color: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(18px);
}

:deep(.unlock-dialog .p-dialog-header) {
  background: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding: 18px 20px 12px;
  color: rgba(255, 255, 255, 0.92);
  font-family: 'Noto Serif SC', serif;
}

:deep(.unlock-dialog .p-dialog-content) {
  background: transparent;
  padding: 0 20px 20px;
}

:deep(.unlock-dialog .p-dialog-header-icon) {
  color: rgba(255, 255, 255, 0.58);
}

@keyframes sheen-pass {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

@media (max-width: 900px) {
  .unlock-milestones {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .unlock-side-grid {
    grid-template-columns: 1fr;
  }

  .unlock-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .unlock-hero-percent {
    align-items: flex-start;
  }
</style>
