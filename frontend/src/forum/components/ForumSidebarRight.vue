<script setup lang="ts">
import Dialog from 'primevue/dialog'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useForumProfile } from '../useAgentProfile'

const router = useRouter()
const { profile, load } = useForumProfile()

const unlockDialogVisible = ref(false)
const unlockPercent = ref(0)
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

onMounted(load)

watch(() => profile.value?.userId, () => {
  unlockPercent.value = 0
  activeEchoIndex.value = 0
  probeStatus.value = '剧情档案静默中，尚未捕获任何可写回的碎片。'
})

function levelColor(level: number): string {
  if (level >= 10)
    return '#d4af37'
  if (level >= 7)
    return '#c0c0c0'
  if (level >= 4)
    return '#cd7f32'
  return '#8a8a8a'
}

const quotaPercent = computed(() => {
  if (!profile.value?.quota || profile.value.quota.dailyBudget === 0)
    return 0
  const remaining = Math.max(0, profile.value.quota.dailyBudget - profile.value.quota.usedToday)
  return Math.round((remaining / profile.value.quota.dailyBudget) * 100)
})

const hasUnread = computed(() => (profile.value?.unreadCount ?? 0) > 0)

const currentMilestone = computed<UnlockMilestone>(() => {
  let result: UnlockMilestone = unlockMilestones[0]!
  for (const milestone of unlockMilestones) {
    if (unlockPercent.value >= milestone.threshold)
      result = milestone
  }
  return result
})

const nextMilestone = computed(() => {
  return unlockMilestones.find(item => item.threshold > unlockPercent.value) ?? null
})

const currentEcho = computed(() => echoLibrary[activeEchoIndex.value % echoLibrary.length] ?? '')

const intrigueScore = computed(() => {
  const stats = profile.value?.stats
  if (!stats)
    return 0
  return Math.min(100, stats.posts * 4 + stats.replies * 2 + stats.likes + stats.friends * 6)
})

function openUnlockDialog() {
  unlockDialogVisible.value = true
  pulseTimeline()
}

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
</script>

<template>
  <aside class="sidebar-right flex flex-col p-3 shrink-0 w-48">
    <template v-if="profile">
      <button class="unlock-entry-btn" @click="openUnlockDialog">
        <div class="unlock-entry-copy">
          <span class="unlock-entry-label">解锁进度</span>
          <span class="unlock-entry-hint">查看剧情档案与阶段回声</span>
        </div>
        <div class="unlock-entry-side">
          <span class="unlock-entry-percent">{{ unlockPercent }}%</span>
          <svg class="w-3.5 h-3.5 text-#d4af37/75" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 15V3" />
            <path d="M5 10V8a7 7 0 1 1 14 0v2" />
            <path d="M6 15h12v6H6z" />
          </svg>
        </div>
      </button>

      <div class="flex items-center gap-2.5 mb-1">
        <div v-if="profile.avatar" class="w-10 h-10 rounded-full overflow-hidden shrink-0 border-2 border-#d4af37/40">
          <img :src="profile.avatar" class="w-full h-full object-cover" alt="">
        </div>
        <div v-else class="avatar-ring w-10 h-10 rounded-full flex items-center justify-center text-lg shrink-0">
          {{ profile.displayName.charAt(0) }}
        </div>
        <div class="min-w-0">
          <div class="text-white/90 font-serif font-bold text-sm truncate">{{ profile.displayName }}</div>
          <div class="flex items-center gap-1">
            <span
              class="level-badge text-[10px] font-bold px-1.5 py-0.5 rounded"
              :style="{ color: levelColor(profile.level), borderColor: levelColor(profile.level) }"
            >
              Lv.{{ profile.level }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="profile.bio" class="text-white/35 text-[11px] leading-relaxed mt-1 mb-1">
        {{ profile.bio }}
      </div>

      <div class="sep" />

      <div class="section-label">活动概览</div>
      <div class="flex flex-col gap-0.5">
        <button class="stat-btn" @click="router.push('/forum/my-posts')">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
            发帖
          </span>
          <span class="stat-num">
            {{ profile.stats?.posts ?? 0 }}
            <svg class="w-3 h-3 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6" /></svg>
          </span>
        </button>

        <button class="stat-btn" @click="router.push('/forum/my-replies')">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
            回帖
          </span>
          <span class="stat-num">
            {{ profile.stats?.replies ?? 0 }}
            <svg class="w-3 h-3 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6" /></svg>
          </span>
        </button>

        <button class="stat-btn" @click="router.push('/forum/messages')">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" /></svg>
            收信
          </span>
          <span class="stat-num">
            {{ profile.stats?.messages ?? 0 }}
            <span v-if="hasUnread" class="unread-dot" />
            <svg class="w-3 h-3 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6" /></svg>
          </span>
        </button>

        <button class="stat-btn" @click="router.push('/forum/friends')">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
            好友
          </span>
          <span class="stat-num">
            {{ profile.stats?.friends ?? 0 }}
            <svg class="w-3 h-3 text-white/20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6" /></svg>
          </span>
        </button>

        <div class="stat-row">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
            获赞
          </span>
          <span class="stat-num">{{ profile.stats?.likes ?? 0 }}</span>
        </div>

        <div class="stat-row">
          <span class="flex items-center gap-1.5">
            <svg class="w-3 h-3 text-#d4af37/60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17l9.2-9.2M17 17V7H7" /></svg>
            转发
          </span>
          <span class="stat-num">{{ profile.stats?.shares ?? 0 }}</span>
        </div>
      </div>

      <div class="sep" />

      <div class="section-label">今日流量</div>
      <template v-if="profile.quota">
        <div class="progress-bar mb-1">
          <div
            class="progress-fill"
            :class="{ low: quotaPercent < 20 }"
            :style="{ width: `${quotaPercent}%` }"
          />
        </div>
        <div class="flex justify-between text-[10px] text-white/30 mb-2">
          <span>{{ profile.quota.usedToday }} / {{ profile.quota.dailyBudget }}</span>
          <span>{{ quotaPercent }}%</span>
        </div>
      </template>
      <div v-else class="text-white/20 text-[10px] mb-2">暂无配额数据</div>
      <button class="quota-nav-btn" @click="router.push('/forum/quota')">
        网络探索
      </button>

      <div class="sep" />

      <div class="text-white/20 text-[10px] text-center">
        注册于 {{ new Date(profile.createdAt).getFullYear() }}/{{ new Date(profile.createdAt).getMonth() + 1 }}
      </div>
    </template>

    <div v-else class="text-white/20 text-xs text-center py-4">
      加载中...
    </div>

    <Dialog
      v-model:visible="unlockDialogVisible"
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
  </aside>
</template>

<style scoped>
.sidebar-right {
  background: rgba(20, 20, 20, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  backdrop-filter: blur(12px);
}

.unlock-entry-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(212, 175, 55, 0.22);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.12), rgba(212, 175, 55, 0.03)),
    rgba(255, 255, 255, 0.02);
  color: rgba(255, 255, 255, 0.88);
  cursor: pointer;
  transition: all 0.18s ease;
}

.unlock-entry-btn:hover {
  border-color: rgba(212, 175, 55, 0.38);
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.18), rgba(212, 175, 55, 0.05)),
    rgba(255, 255, 255, 0.03);
  transform: translateY(-1px);
}

.unlock-entry-copy {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
}

.unlock-entry-label {
  font-size: 13px;
  font-weight: 700;
  color: #f3db8c;
}

.unlock-entry-hint {
  font-size: 10px;
  line-height: 1.35;
  color: rgba(255, 255, 255, 0.42);
}

.unlock-entry-side {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.unlock-entry-percent {
  font-size: 12px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.72);
}

.avatar-ring {
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border: 2px solid rgba(212, 175, 55, 0.4);
}

.level-badge {
  border: 1px solid;
  background: rgba(255, 255, 255, 0.03);
  line-height: 1;
}

.sep {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin: 8px 0;
}

.section-label {
  color: rgba(255, 255, 255, 0.3);
  font-size: 10px;
  letter-spacing: 0.1em;
  margin-bottom: 4px;
}

.stat-btn,
.stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  transition: all 0.15s;
}

.stat-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  width: 100%;
  text-align: left;
}

.stat-btn:hover {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.8);
}

.stat-num {
  font-family: monospace;
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.unread-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #d4af37;
  flex-shrink: 0;
}

.progress-bar {
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(212, 175, 55, 0.6), rgba(212, 175, 55, 0.9));
  transition: width 0.6s ease;
}

.progress-fill.low {
  background: linear-gradient(90deg, rgba(200, 80, 60, 0.6), rgba(200, 80, 60, 0.9));
}

.quota-nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 7px 0;
  border: 1px solid rgba(212, 175, 55, 0.3);
  border-radius: 6px;
  background: rgba(212, 175, 55, 0.1);
  color: #d4af37;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.quota-nav-btn:hover {
  background: rgba(212, 175, 55, 0.2);
  border-color: rgba(212, 175, 55, 0.5);
}

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
}
</style>
