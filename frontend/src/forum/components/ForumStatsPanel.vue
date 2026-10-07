<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

/**
 * 侧栏统计面板（活动概览 + 今日流量 + 注册信息）—— 自 `ForumSidebarRight.vue` 拆出
 * （工单204 任务三）。
 *
 * 纯展示组件：数据由父组件经 `profile` 传入；两个派生量（quotaPercent / hasUnread）
 * 在组件内自算（原为父组件的 computed，依赖仅 profile）。
 */
const props = defineProps<{ profile: any }>()
const router = useRouter()

const quotaPercent = computed(() => {
  const q = props.profile?.quota
  if (!q || q.dailyBudget === 0) return 0
  const remaining = Math.max(0, q.dailyBudget - q.usedToday)
  return Math.round((remaining / q.dailyBudget) * 100)
})

const hasUnread = computed(() => (props.profile?.unreadCount ?? 0) > 0)
</script>

<template>
  <div>
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
  </div>
</template>

<style scoped>
/* .sep 与 .section-label 父组件别处也用 → 各留一份（scoped 不跨组件生效） */
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

</style>
