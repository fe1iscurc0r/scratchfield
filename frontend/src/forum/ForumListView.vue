<script setup lang="ts">
import type { ForumBoard, ForumFeedMode, ForumPost, SortMode, TimeOrder } from './types'
import ScrollPanel from 'primevue/scrollpanel'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ACCESS_TOKEN } from '@/api'
import { sessionRestored } from '@/composables/useAuth'
import { backendConnected } from '@/utils/config'
import { fetchPosts } from './api'
import ForumPostCard from './components/ForumPostCard.vue'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'

const router = useRouter()
const sortMode = ref<SortMode>('all')
const timeOrder = ref<TimeOrder>('desc')
const yearMonth = ref<string | null>(null)
const feedMode = ref<ForumFeedMode>('casual')
const posts = ref<ForumPost[]>([])
const visiblePosts = ref<ForumPost[]>([])
const totalComments = ref(0)
const loadingPosts = ref(false)
const postsError = ref('')
let currentLoadId = 0

const emptyStateText = computed(() => (
  feedMode.value === 'casual'
    ? '日常吹水模式下暂无帖子'
    : '暂无帖子'
))

function formatForumError(e: any) {
  const detail = e?.response?.data?.detail
  if (e?.response?.status === 401) {
    return '登录状态已失效，请重新登录scratchpad 网络'
  }
  if (detail?.error === 'upstream_non_json_response') {
    return `社区服务暂不可用：上游返回 ${detail.statusCode || detail.status_code}，类型 ${detail.contentType || detail.content_type || 'unknown'}`
  }
  if (typeof detail === 'string' && detail.trim()) {
    return `加载失败: ${detail}`
  }
  if (detail?.message) {
    return `加载失败: ${detail.message}`
  }
  return `加载失败: ${e?.message || 'unknown error'}`
}

function isStoryBoard(board?: ForumBoard | null): boolean {
  if (!board) {
    return false
  }
  const slug = String(board.slug || '').trim().toLowerCase()
  const name = String(board.name || '').trim()
  return slug === 'story' || name.includes('剧情')
}

function isStoryPost(post: ForumPost): boolean {
  return (post.boards || []).some(board => isStoryBoard(board))
}

function mixStoryPosts(sourcePosts: ForumPost[]): ForumPost[] {
  const normalPosts: ForumPost[] = []
  const storyPosts: ForumPost[] = []

  for (const post of sourcePosts) {
    if (isStoryPost(post)) {
      storyPosts.push(post)
    }
    else {
      normalPosts.push(post)
    }
  }

  const mixedPosts = [...normalPosts]
  for (const post of storyPosts) {
    const insertAt = Math.floor(Math.random() * (mixedPosts.length + 1))
    mixedPosts.splice(insertAt, 0, post)
  }
  return mixedPosts
}

function updateVisiblePosts() {
  const nextPosts = feedMode.value === 'story'
    ? mixStoryPosts(posts.value)
    : posts.value.filter(post => !isStoryPost(post))

  visiblePosts.value = nextPosts
  totalComments.value = nextPosts.reduce((sum, post) => sum + post.commentsCount, 0)
}

async function loadPosts() {
  const loadId = ++currentLoadId
  if (!backendConnected.value) {
    return
  }

  loadingPosts.value = true

  if (!ACCESS_TOKEN.value) {
    postsError.value = '请先登录后使用scratchpad 网络'
    posts.value = []
    visiblePosts.value = []
    totalComments.value = 0
    loadingPosts.value = false
    return
  }

  if (!sessionRestored.value) {
    await new Promise<void>((resolve) => {
      const stop = watch(sessionRestored, (ready) => {
        if (ready) {
          stop()
          resolve()
        }
      })
      setTimeout(() => {
        stop()
        resolve()
      }, 5000)
    })
  }

  if (!ACCESS_TOKEN.value) {
    postsError.value = '请先登录后使用scratchpad 网络'
    posts.value = []
    visiblePosts.value = []
    totalComments.value = 0
    loadingPosts.value = false
    return
  }

  try {
    if (!posts.value.length) {
      postsError.value = ''
    }

    let res
    try {
      res = await fetchPosts(sortMode.value, 1, 20, timeOrder.value, yearMonth.value)
    }
    catch (e: any) {
      const status = e?.response?.status
      if (status === 500 || status === 503) {
        await new Promise(resolve => setTimeout(resolve, 600))
        res = await fetchPosts(sortMode.value, 1, 20, timeOrder.value, yearMonth.value)
      }
      else {
        throw e
      }
    }

    if (loadId !== currentLoadId) {
      return
    }

    posts.value = res.items
    updateVisiblePosts()
    postsError.value = ''
  }
  catch (e: any) {
    if (loadId !== currentLoadId) {
      return
    }
    if (!posts.value.length) {
      postsError.value = formatForumError(e)
    }
  }
  finally {
    if (loadId === currentLoadId) {
      loadingPosts.value = false
    }
  }
}

watch([sortMode, timeOrder, yearMonth], () => {
  void loadPosts()
})

watch(feedMode, () => {
  updateVisiblePosts()
})

watch([backendConnected, ACCESS_TOKEN], ([connected, token]) => {
  if (connected && token) {
    void loadPosts()
  }
})

onMounted(() => {
  if (backendConnected.value && ACCESS_TOKEN.value) {
    void loadPosts()
  }
})

function openPost(id: string) {
  router.push(`/forum/${id}`)
}
</script>

<template>
  <template v-if="true">
    <div class="left-rail flex flex-col gap-2 shrink-0 self-stretch">
      <button class="forum-home-btn" @click="router.push('/')">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        <span>返回主页</span>
      </button>

      <ForumSidebarLeft
        v-model:sort="sortMode"
        v-model:time-order="timeOrder"
        v-model:year-month="yearMonth"
        v-model:feed-mode="feedMode"
        :total-posts="visiblePosts.length"
        :total-comments="totalComments"
        show-feed-mode-switcher
        hide-back-button
      />
    </div>

    <div class="main-col flex-1 min-w-0 min-h-0 self-stretch">
      <ScrollPanel
        class="size-full"
        :pt="{
          barY: { class: 'w-2! rounded! bg-#373737! transition!' },
        }"
      >
        <div class="flex flex-col gap-3 p-2">
          <ForumPostCard
            v-for="post in visiblePosts"
            :key="post.id"
            :post="post"
            @click="openPost"
          />

          <div v-if="postsError" class="text-red-300/80 text-sm text-center py-8">
            {{ postsError }}
          </div>

          <div v-else-if="loadingPosts" class="text-white/30 text-sm text-center py-8">
            加载中...
          </div>

          <div v-else-if="!visiblePosts.length" class="text-white/30 text-sm text-center py-8">
            {{ emptyStateText }}
          </div>
        </div>
      </ScrollPanel>
    </div>

    <ForumSidebarRight />
  </template>
</template>

<style scoped>
.left-rail {
  width: 10rem;
}

.forum-home-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(212, 175, 55, 0.24);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.12), rgba(212, 175, 55, 0.04)),
    rgba(20, 20, 20, 0.56);
  color: rgba(243, 219, 140, 0.96);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition: all 0.18s ease;
}

.forum-home-btn:hover {
  border-color: rgba(212, 175, 55, 0.4);
  background:
    linear-gradient(180deg, rgba(212, 175, 55, 0.18), rgba(212, 175, 55, 0.06)),
    rgba(30, 30, 30, 0.7);
  color: #f7e2a0;
  transform: translateY(-1px);
}

.main-col {
  background: rgba(20, 20, 20, 0.5);
  border-radius: 8px;
}
</style>
