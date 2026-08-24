<script setup lang="ts">
import type { ForumPostDetail } from './types'
import ScrollPanel from 'primevue/scrollpanel'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Markdown from '@/components/Markdown.vue'
import { fetchPost, likePost } from './api'
import ForumCommentItem from './components/ForumCommentItem.vue'
import ForumImagePreview from './components/ForumImagePreview.vue'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'

const route = useRoute()
const router = useRouter()

const post = ref<ForumPostDetail | null>(null)
const previewSrc = ref<string | null>(null)

onMounted(async () => {
  const id = route.params.id as string
  post.value = await fetchPost(id)
})

function goBack() {
  router.push('/forum')
}

async function toggleLike() {
  if (!post.value)
    return
  const res = await likePost(post.value.id)
  post.value.likesCount = res.likes
  post.value.liked = res.liked
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <template v-if="true">
    <!-- Left sidebar (read-only on detail) -->
    <ForumSidebarLeft :total-posts="0" :total-comments="post?.commentList.length ?? 0" />

    <!-- Main content -->
    <div class="main-col flex-1 min-w-0 min-h-0 self-stretch">
      <ScrollPanel
        class="size-full"
        :pt="{
          barY: { class: 'w-2! rounded! bg-#373737! transition!' },
        }"
      >
        <div class="p-4">
          <!-- Back button -->
          <button class="back-link flex items-center gap-1 border-none bg-transparent cursor-pointer text-xs mb-4 p-0" @click="goBack">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            返回列表
          </button>

          <template v-if="post">
            <!-- Author info -->
            <div class="flex items-center gap-2 mb-3">
              <div class="avatar w-9 h-9 rounded-full flex items-center justify-center text-sm">
                {{ post.author.name.charAt(0) }}
              </div>
              <div>
                <div class="text-white/80 text-sm font-bold">{{ post.author.name }} <span class="text-white/25 text-xs font-normal">Lv.{{ post.author.level }}</span></div>
                <div class="text-white/30 text-xs">{{ formatTime(post.createdAt) }}</div>
              </div>
            </div>

            <!-- Title -->
            <h2 class="text-white/95 text-lg font-bold mt-0 mb-4">
              {{ post.title }}
            </h2>

            <div v-if="post.boards?.length || post.visibilityStatus || post.moderationStatus" class="post-meta-badges">
              <span
                v-for="board in post.boards || []"
                :key="board.id"
                class="board-badge"
              >
                {{ board.name }}
              </span>
              <span
                v-if="post.visibilityStatus"
                class="status-badge"
                :class="{ hidden: post.visibilityStatus === 'hidden' }"
              >
                {{ post.visibilityStatus === 'hidden' ? '隐藏' : '可见' }}
              </span>
              <span v-if="post.moderationStatus" class="status-badge moderation">
                审核：{{ post.moderationStatus }}
              </span>
            </div>

            <!-- Markdown content -->
            <div class="markdown-body text-white/70 text-sm leading-relaxed">
              <Markdown :source="post.content" />
            </div>

            <!-- Image grid -->
            <div v-if="post.images?.length" class="grid grid-cols-3 gap-2 mt-4">
              <img
                v-for="(img, i) in post.images"
                :key="i"
                :src="img"
                class="w-full aspect-square object-cover rounded cursor-pointer hover:brightness-110 transition"
                @click="previewSrc = img"
              >
            </div>

            <!-- Interaction bar -->
            <div class="flex items-center gap-6 py-3 mt-4 border-t border-b border-white/8 text-white/40 text-xs">
              <span class="flex items-center gap-1">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
                {{ post.viewCount }}
              </span>
              <span class="flex items-center gap-1">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                {{ post.commentList.length }}
              </span>
              <button
                class="like-btn flex items-center gap-1 border-none bg-transparent cursor-pointer p-0 transition"
                :class="post.liked ? 'liked' : ''"
                @click="toggleLike"
              >
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
                {{ post.likesCount }}
              </button>
            </div>

            <!-- Comments section -->
            <div class="mt-4">
              <div class="text-white/50 text-xs mb-3 tracking-widest">
                评论 ({{ post.commentList.length }})
              </div>
              <div class="flex flex-col gap-1">
                <ForumCommentItem
                  v-for="comment in post.commentList"
                  :key="comment.id"
                  :comment="comment"
                  :is-post-owner="true"
                  @preview-image="previewSrc = $event"
                />
              </div>
              <div v-if="!post.commentList.length" class="text-white/20 text-xs text-center py-4">
                暂无评论
              </div>
            </div>
          </template>

          <div v-else class="text-white/30 text-sm text-center py-8">
            加载中...
          </div>
        </div>
      </ScrollPanel>
    </div>

    <!-- Right sidebar -->
    <ForumSidebarRight />

    <!-- Image lightbox -->
    <ForumImagePreview :src="previewSrc" @close="previewSrc = null" />
  </template>
</template>

<style scoped>
.main-col {
  background: rgba(20, 20, 20, 0.5);
  border-radius: 8px;
}

.avatar {
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border: 1px solid rgba(212, 175, 55, 0.3);
}

.back-link {
  color: rgba(255, 255, 255, 0.4);
  transition: color 0.2s;
}
.back-link:hover {
  color: rgba(255, 255, 255, 0.7);
}

.like-btn {
  color: rgba(255, 255, 255, 0.4);
}
.like-btn:hover {
  color: rgba(255, 255, 255, 0.6);
}
.like-btn.liked {
  color: #d4af37;
}
.like-btn.liked svg {
  fill: #d4af37;
}

.post-meta-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: -8px 0 14px;
}

.board-badge,
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 1.2;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.64);
}

.status-badge.hidden {
  background: rgba(248, 113, 113, 0.1);
  color: rgba(252, 165, 165, 0.92);
  border-color: rgba(248, 113, 113, 0.18);
}

.status-badge.moderation {
  background: rgba(212, 175, 55, 0.1);
  color: rgba(212, 175, 55, 0.92);
  border-color: rgba(212, 175, 55, 0.18);
}

.markdown-body :deep(h2) {
  color: rgba(255, 255, 255, 0.85);
  font-size: 1rem;
  margin: 1.2em 0 0.6em;
}
.markdown-body :deep(h3) {
  color: rgba(255, 255, 255, 0.8);
  font-size: 0.9rem;
  margin: 1em 0 0.5em;
}
.markdown-body :deep(h4) {
  color: rgba(255, 255, 255, 0.75);
  font-size: 0.85rem;
  margin: 0.8em 0 0.4em;
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
  font-size: 0.85rem;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  text-align: left;
}
.markdown-body :deep(th) {
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.7);
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.markdown-body :deep(li) {
  margin: 0.25em 0;
}
.markdown-body :deep(strong) {
  color: rgba(255, 255, 255, 0.85);
}
.markdown-body :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 0.15em 0.4em;
  border-radius: 3px;
  font-size: 0.9em;
}
</style>
