<script setup lang="ts">
import Dialog from 'primevue/dialog'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useForumProfile } from '../useAgentProfile'
import ForumStatsPanel from './ForumStatsPanel.vue'
import ForumUnlockDialog from './ForumUnlockDialog.vue'

const router = useRouter()
const { profile, load } = useForumProfile()

const unlockDialogVisible = ref(false)
const unlockPercent = ref(0)

watch(() => profile.value?.userId, () => {
  unlockPercent.value = 0
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


function openUnlockDialog() {
  unlockDialogVisible.value = true
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

      <ForumStatsPanel :profile="profile" />
    </template>

    <div v-else class="text-white/20 text-xs text-center py-4">
      加载中...
    </div>

    <ForumUnlockDialog
      v-model:visible="unlockDialogVisible"
      :unlock-percent="unlockPercent"
      :user-id="profile?.userId"
      :profile="profile"
    />
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

}
</style>
