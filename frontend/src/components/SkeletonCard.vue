<script setup lang="ts">
/**
 * 统一骨架屏（卷150 任务B）——加载中占位，替代"白屏冻结"。
 *
 * 对接约定：
 *   <SkeletonCard v-if="loading" :rows="3" />   ← 列表加载
 *   <SkeletonCard v-if="loading" variant="image" /> ← 图表/大块区域
 *   <div v-else-if="error"><EmptyState error ... /></div>
 *   <div v-else>…真实内容…</div>
 *
 * 纯 CSS 动画（无 JS 定时器），rows 控制行数。
 */
withDefaults(defineProps<{
  /** 骨架行数（text 变体） */
  rows?: number
  /**
   * 变体：
   * - text：标题行 + 若干正文行（列表默认）
   * - image：大块矩形（图表/封面/上传等待）
   * - list：多行带圆形头像（会话/评论）
   */
  variant?: 'text' | 'image' | 'list'
}>(), {
  rows: 3,
  variant: 'text',
})
</script>

<template>
  <div class="skeleton-card" :data-variant="variant" data-testid="skeleton-card" aria-hidden="true">
    <template v-if="variant === 'image'">
      <div class="sk sk-image" />
      <div class="sk sk-line" style="width: 45%" />
    </template>

    <template v-else-if="variant === 'list'">
      <div v-for="i in rows" :key="i" class="sk-row">
        <div class="sk sk-avatar" />
        <div class="sk-col">
          <div class="sk sk-line" :style="{ width: `${40 + ((i * 17) % 45)}%` }" />
          <div class="sk sk-line sk-line-sm" :style="{ width: `${25 + ((i * 29) % 50)}%` }" />
        </div>
      </div>
    </template>

    <template v-else>
      <div class="sk sk-line" style="width: 60%; height: 16px" />
      <div
        v-for="i in rows"
        :key="i"
        class="sk sk-line"
        :style="{ width: `${88 - ((i * 13) % 35)}%` }"
      />
    </template>
  </div>
</template>

<style scoped>
.skeleton-card {
  display: flex;
  flex-direction: column;
  gap: var(--lumo-space-2);
  padding: var(--lumo-space-3);
  width: 100%;
}

.sk {
  position: relative;
  overflow: hidden;
  border-radius: var(--lumo-radius-sm);
  background: var(--lumo-bg-inset);
}

.sk::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.05),
    transparent
  );
  animation: sk-shimmer 1.4s ease-in-out infinite;
}

@keyframes sk-shimmer {
  100% {
    transform: translateX(100%);
  }
}

.sk-line {
  height: 12px;
}

.sk-line-sm {
  height: 10px;
}

.sk-image {
  width: 100%;
  aspect-ratio: 16 / 9;
}

.sk-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sk-row {
  display: flex;
  align-items: center;
  gap: var(--lumo-space-2);
}

.sk-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--lumo-space-1);
}
</style>
