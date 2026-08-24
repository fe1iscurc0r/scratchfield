<script setup lang="ts">
import type { ForumPost } from './types'
import ScrollPanel from 'primevue/scrollpanel'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ACCESS_TOKEN } from '@/api'
import { fetchPosts } from './api'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'
import { useForumProfile } from './useAgentProfile'

const router = useRouter()
const { profile, load } = useForumProfile()
const posts = ref<ForumPost[]>([])
const loading = ref(true)

onMounted(async () => {
  if (!ACCESS_TOKEN.value) {
    loading.value = false
    return
  }
  try {
    await load()
    const authorId = profile.value?.userId ?? null
    const res = await fetchPosts('latest', 1, 50, 'desc', null, null, authorId)
    posts.value = res.items
  }
  catch {
    // ignore
  }
  loading.value = false
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`
}

function viewPost(id: string) {
  router.push(`/forum/${id}`)
}
</script>

<template>
  <template v-if="true">
    <ForumSidebarLeft
      :total-posts="posts.length"
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
          <h2 class="text-white/90 text-base font-bold mt-0 mb-4">我的发帖</h2>

          <template v-if="!loading">
            <div class="flex flex-col gap-2">
              <div
                v-for="item in posts"
                :key="item.id"
                class="activity-row"
                @click="viewPost(item.id)"
              >
                <div class="flex items-center gap-1.5 mb-1">
                  <svg class="w-3.5 h-3.5 text-#d4af37/50 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
                  <span v-if="item.pinned" class="text-#d4af37/70 text-[10px]">[置顶]</span>
                  <span class="text-white/80 text-sm font-bold truncate">{{ item.title }}</span>
                </div>
                <div class="flex items-center gap-3 text-white/25 text-xs pl-5">
                  <span>{{ formatDate(item.createdAt) }}</span>
                  <span class="flex items-center gap-0.5">
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
                    {{ item.likesCount }}
                  </span>
                  <span class="flex items-center gap-0.5">
                    <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                    {{ item.commentsCount }}
                  </span>
                </div>
              </div>
            </div>
            <div v-if="!posts.length" class="text-white/20 text-xs text-center py-4">
              暂无发帖记录
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
.activity-row {
  padding: 12px 16px;
  border-radius: 6px;
  background: rgba(20, 20, 20, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.15s;
}
.activity-row:hover {
  background: rgba(30, 30, 30, 0.7);
  border-color: rgba(212, 175, 55, 0.2);
}
</style>
