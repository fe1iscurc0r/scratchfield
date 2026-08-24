<script setup lang="ts">
import type { ForumConnection, FriendRequest } from './types'
import ScrollPanel from 'primevue/scrollpanel'
import { onMounted, ref } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import { acceptFriendRequest, declineFriendRequest, fetchConnections, fetchFriendRequests } from './api'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'

const connections = ref<ForumConnection[]>([])
const pendingRequests = ref<FriendRequest[]>([])
const loading = ref(true)

onMounted(async () => {
  if (!ACCESS_TOKEN.value) {
    loading.value = false
    return
  }
  try {
    const [connRes, reqRes] = await Promise.all([
      fetchConnections(),
      fetchFriendRequests('pending', 'received'),
    ])
    connections.value = connRes.items
    pendingRequests.value = reqRes.items
  }
  catch {
    // ignore
  }
  loading.value = false
})

async function handleAccept(id: string) {
  try {
    await acceptFriendRequest(id)
    pendingRequests.value = pendingRequests.value.filter(r => r.id !== id)
    // Refresh connections
    const res = await fetchConnections()
    connections.value = res.items
  }
  catch {
    // ignore
  }
}

async function handleDecline(id: string) {
  try {
    await declineFriendRequest(id)
    pendingRequests.value = pendingRequests.value.filter(r => r.id !== id)
  }
  catch {
    // ignore
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <template v-if="true">
    <ForumSidebarLeft
      :total-posts="0"
      :total-comments="0"
      back-label="返回网络"
      back-to="/forum"
      hide-filters
    />

    <div class="main-col flex-1 min-w-0 min-h-0 self-stretch">
      <ScrollPanel
        class="size-full"
        :pt="{ barY: { class: 'w-2! rounded! bg-#373737! transition!' } }"
      >
        <div class="p-4">
          <h2 class="text-white/90 text-base font-bold mt-0 mb-4">好友</h2>

          <template v-if="!loading">
            <!-- Pending requests -->
            <template v-if="pendingRequests.length">
              <div class="text-white/30 text-xs mb-2 tracking-widest">待处理请求 ({{ pendingRequests.length }})</div>
              <div class="flex flex-col gap-2 mb-4">
                <div
                  v-for="req in pendingRequests"
                  :key="req.id"
                  class="friend-row"
                >
                  <div class="flex items-center gap-2 flex-1 min-w-0">
                    <div class="avatar w-8 h-8 rounded-full flex items-center justify-center text-xs shrink-0">
                      {{ req.fromUser.name.charAt(0) }}
                    </div>
                    <div class="min-w-0">
                      <div class="text-white/80 text-sm font-bold truncate">{{ req.fromUser.name }}</div>
                      <div class="text-white/25 text-[10px]">{{ formatDate(req.createdAt) }}</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-1.5 shrink-0">
                    <button class="action-btn accept" @click="handleAccept(req.id)">接受</button>
                    <button class="action-btn decline" @click="handleDecline(req.id)">拒绝</button>
                  </div>
                </div>
              </div>
            </template>

            <!-- Friends list -->
            <div class="text-white/30 text-xs mb-2 tracking-widest">好友列表 ({{ connections.length }})</div>
            <div class="flex flex-col gap-2">
              <div
                v-for="conn in connections"
                :key="conn.connectionId"
                class="friend-row"
              >
                <div class="flex items-center gap-2 flex-1 min-w-0">
                  <div v-if="conn.friend.avatar" class="w-8 h-8 rounded-full overflow-hidden shrink-0 border border-#d4af37/30">
                    <img :src="conn.friend.avatar" class="w-full h-full object-cover" alt="">
                  </div>
                  <div v-else class="avatar w-8 h-8 rounded-full flex items-center justify-center text-xs shrink-0">
                    {{ conn.friend.name.charAt(0) }}
                  </div>
                  <div class="min-w-0">
                    <div class="text-white/80 text-sm font-bold truncate">
                      {{ conn.friend.name }}
                      <span v-if="conn.friend.level" class="text-white/25 text-xs font-normal">Lv.{{ conn.friend.level }}</span>
                    </div>
                    <div v-if="conn.friend.bio" class="text-white/30 text-[10px] truncate">{{ conn.friend.bio }}</div>
                  </div>
                </div>
                <div class="text-white/15 text-[10px] shrink-0">{{ formatDate(conn.createdAt) }}</div>
              </div>
            </div>
            <div v-if="!connections.length" class="text-white/20 text-xs text-center py-4">
              暂无好友
            </div>
          </template>
          <div v-else class="text-white/30 text-sm text-center py-8">加载中...</div>
        </div>
      </ScrollPanel>
    </div>

    <ForumSidebarRight />
  </template>
</template>

<style scoped>
.main-col {
  background: rgba(20, 20, 20, 0.5);
  border-radius: 8px;
}
.friend-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 6px;
  background: rgba(20, 20, 20, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: all 0.15s;
}
.friend-row:hover {
  background: rgba(30, 30, 30, 0.7);
  border-color: rgba(255, 255, 255, 0.1);
}
.avatar {
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border: 1px solid rgba(212, 175, 55, 0.3);
}
.action-btn {
  border: none;
  cursor: pointer;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  transition: all 0.2s;
}
.action-btn.accept {
  background: rgba(74, 222, 128, 0.1);
  color: #4ade80;
  border: 1px solid rgba(74, 222, 128, 0.25);
}
.action-btn.accept:hover {
  background: rgba(74, 222, 128, 0.2);
}
.action-btn.decline {
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.action-btn.decline:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
