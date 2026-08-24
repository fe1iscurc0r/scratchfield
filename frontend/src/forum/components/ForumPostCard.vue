<script setup lang="ts">
import type { ForumPost } from '../types'

defineProps<{ post: ForumPost }>()
defineEmits<{ click: [id: string] }>()

function formatTime(iso: string): string {
  const d = new Date(iso)
  const month = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${h}:${m}`
}

function visibilityLabel(status?: string) {
  return status === 'hidden' ? '隐藏' : '可见'
}
</script>

<template>
  <div class="post-card cursor-pointer transition" @click="$emit('click', post.id)">
    <div class="flex gap-3 p-3">
      <!-- Cover image (first image if any) -->
      <div v-if="post.images?.length" class="cover shrink-0 w-20 h-20 rounded overflow-hidden">
        <img :src="post.images[0]" class="w-full h-full object-cover" alt="">
      </div>

      <!-- Text content -->
      <div class="flex flex-col gap-1 min-w-0 flex-1">
        <div class="flex items-center gap-1.5">
          <span v-if="post.pinned" class="pin-badge">置顶</span>
          <span
            v-for="board in post.boards || []"
            :key="board.id"
            class="board-badge"
          >
            {{ board.name }}
          </span>
          <span
            v-if="post.visibilityStatus"
            class="visibility-badge"
            :class="{ hidden: post.visibilityStatus === 'hidden' }"
          >
            {{ visibilityLabel(post.visibilityStatus) }}
          </span>
          <div class="text-white/90 font-bold text-sm line-clamp-1">
            {{ post.title }}
          </div>
        </div>
        <div class="text-white/45 text-xs line-clamp-2 leading-relaxed">
          {{ post.content }}
        </div>
        <div class="text-white/30 text-xs mt-auto flex items-center gap-1">
          {{ post.author.name }}
          <span v-if="post.author.level" class="text-white/20">Lv.{{ post.author.level }}</span>
          <span>· {{ formatTime(post.createdAt) }}</span>
        </div>
      </div>
    </div>

    <!-- Interaction bar -->
    <div class="flex items-center gap-5 px-3 py-2 border-t border-white/6 text-white/35 text-xs">
      <span class="flex items-center gap-1">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
        {{ post.viewCount }}
      </span>
      <span class="flex items-center gap-1">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
        {{ post.commentsCount }}
      </span>
      <span class="flex items-center gap-1">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
        {{ post.likesCount }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.post-card {
  background: rgba(20, 20, 20, 0.5);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  backdrop-filter: blur(8px);
}
.post-card:hover {
  background: rgba(30, 30, 30, 0.7);
  border-color: rgba(212, 175, 55, 0.2);
}

.pin-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  background: rgba(212, 175, 55, 0.15);
  color: #d4af37;
  border: 1px solid rgba(212, 175, 55, 0.25);
  flex-shrink: 0;
}

.board-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 999px;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.62);
  border: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.visibility-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 5px;
  border-radius: 999px;
  font-size: 10px;
  background: rgba(74, 222, 128, 0.1);
  color: rgba(134, 239, 172, 0.9);
  border: 1px solid rgba(74, 222, 128, 0.18);
  flex-shrink: 0;
}

.visibility-badge.hidden {
  background: rgba(248, 113, 113, 0.1);
  color: rgba(252, 165, 165, 0.92);
  border-color: rgba(248, 113, 113, 0.18);
}

.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
