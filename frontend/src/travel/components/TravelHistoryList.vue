<script setup lang="ts">
import type { TravelSession } from '@/travel/types'
import { formatDate, formatMinutes, statusLabel } from '@/travel/composables/useTravel'

defineProps<{ sessions: TravelSession[] }>()
defineEmits<{ select: [session: TravelSession] }>()
</script>

<template>
  <div class="flex flex-col gap-2">
    <div class="text-white/40 text-xs">
      探索记录
    </div>
    <div v-if="!sessions.length" class="flex items-center justify-center min-h-20 rounded-lg border border-white/6 bg-white/2 text-white/25 text-sm">
      暂无探索记录
    </div>
    <div v-else class="flex flex-col gap-1.5 max-h-60 overflow-y-auto">
      <button
        v-for="session in sessions.slice(0, 10)"
        :key="session.sessionId"
        class="flex items-center justify-between px-3 py-2 rounded-lg bg-white/3 hover:bg-white/6 transition border-none cursor-pointer text-left w-full"
        @click="$emit('select', session)"
      >
        <div class="flex flex-col gap-0.5 min-w-0">
          <div class="text-white/60 text-xs truncate">
            {{ formatDate(session.createdAt) }}
            <span class="text-white/30 ml-2">{{ formatMinutes(session.elapsedMinutes) }}</span>
          </div>
          <div class="text-white/30 text-[10px]">
            {{ session.discoveries?.length ?? 0 }} 个发现
          </div>
          <div v-if="session.agentName" class="text-white/25 text-[10px] truncate">
            执行干员：{{ session.agentName }}
          </div>
        </div>
        <span
          class="text-[10px] px-1.5 py-0.5 rounded shrink-0"
          :class="{
            'bg-green-500/10 text-green-400/60': session.status === 'completed',
            'bg-red-500/10 text-red-400/60': session.status === 'failed',
            'bg-yellow-500/10 text-yellow-400/60': session.status === 'cancelled',
            'bg-blue-500/10 text-blue-400/60': session.status === 'running',
            'bg-orange-500/10 text-orange-300/70': session.status === 'interrupted',
          }"
        >
          {{ statusLabel[session.status] || session.status }}
        </span>
      </button>
    </div>
  </div>
</template>
