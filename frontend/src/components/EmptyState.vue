<script setup lang="ts">
/**
 * 统一空态组件（卷150 任务B）——图标 + 一句话 + 引导按钮。
 *
 * 对接约定（替换各视图现有裸 v-if 空文案）：
 *   <EmptyState
 *     icon="📭"                          ← 或省略走默认图标
 *     title="还没有文献"
 *     description="从 DOI 导入第一批文献开始"
 *     action-label="导入文献"
 *     @action="onImport"
 *   />
 * 三种语义由父组件通过 props 表达：
 *   - 空数据（无内容）：title + 引导按钮
 *   - 加载中：请改用 SkeletonCard（本组件不管加载态）
 *   - 错误：error 模式（红色调 + 重试按钮）
 */
const props = withDefaults(defineProps<{
  title: string
  description?: string
  /** emoji 或单字符图标（保持轻量，不引图标库） */
  icon?: string
  actionLabel?: string
  /** 错误态：红色调，actionLabel 默认「重试」 */
  error?: boolean
}>(), {
  description: '',
  icon: '',
  actionLabel: '',
  error: false,
})

const emit = defineEmits<{ (e: 'action'): void }>()

function onAction() {
  emit('action')
}

// 暴露给模板使用（eslint no-unused-vars 会拦纯 props 声明式使用之外的场景）
void props
</script>

<template>
  <div class="empty-state" :class="{ error }" data-testid="empty-state">
    <div class="es-icon">{{ icon || (error ? '⚠' : '◎') }}</div>
    <div class="es-title">{{ title }}</div>
    <div v-if="description" class="es-desc">{{ description }}</div>
    <button
      v-if="actionLabel || error"
      class="es-action"
      data-testid="empty-state-action"
      @click="onAction"
    >
      {{ actionLabel || '重试' }}
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--lumo-space-2);
  padding: var(--lumo-space-6) var(--lumo-space-4);
  min-height: 160px;
  color: var(--lumo-text-faint);
  text-align: center;
}

.es-icon {
  font-size: 28px;
  line-height: 1;
  opacity: 0.75;
}

.es-title {
  font-size: 15px;
  color: var(--lumo-text-dim);
}

.es-desc {
  font-size: 13px;
  max-width: 40em;
}

.es-action {
  margin-top: var(--lumo-space-2);
  padding: var(--lumo-space-2) var(--lumo-space-4);
  border: 1px solid var(--lumo-primary-dim);
  border-radius: var(--lumo-radius-md);
  background: var(--lumo-primary-tint);
  color: var(--lumo-primary);
  font-size: 13px;
  font-family: var(--lumo-font-ui);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.es-action:hover {
  background: var(--lumo-primary);
  color: #fff;
}

/* 错误态 */
.empty-state.error .es-icon {
  color: var(--lumo-danger);
}

.empty-state.error .es-title {
  color: var(--lumo-text);
}

.empty-state.error .es-action {
  border-color: var(--lumo-danger);
  background: transparent;
  color: var(--lumo-danger);
}

.empty-state.error .es-action:hover {
  background: var(--lumo-danger);
  color: #fff;
}
</style>
