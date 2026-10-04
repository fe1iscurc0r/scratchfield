<script setup lang="ts">
import type { MatchResult } from '@/utils/commandScore'
/**
 * 命令面板（卷150 任务A）——Ctrl+K 唤起，模糊搜索直达任意视图 + 常用动作。
 *
 * 对接约定：
 *   父组件（App.vue）持有 open 状态并响应 Ctrl+K：
 *     <CommandPalette v-model:open="paletteOpen" @navigate="onPaletteNavigate" />
 *   - 动作类条目（new-eln / new-chat / doi-import）经 @action 事件上抛，
 *     由父组件路由到目标视图后触发（命令面板不自持业务逻辑）
 *   - 自研无依赖（utils/commandScore.ts），符合工单"自研或轻量库"选项
 *   - Esc / 失焦 / 选中后关闭；↑↓ 选择、Enter 确认
 */
import { computed, nextTick, ref, watch } from 'vue'
import { fuzzyMatch, isConfidentTopHit } from '@/utils/commandScore'
import { commandCandidates } from '@/utils/navigation'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'navigate', to: string): void
  (e: 'action', kind: 'new-eln' | 'new-chat' | 'doi-import'): void
}>()

const query = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const activeIndex = ref(0)

const candidates = commandCandidates()

const results = computed<MatchResult<typeof candidates[number]>[]>(() => {
  return fuzzyMatch(query.value, candidates).slice(0, 12)
})

/** 双键直达：唯一高分命中时自动聚焦第一项（验收：输入"eln"两键直达） */
const confident = computed(() => isConfidentTopHit(results.value))

watch(() => props.open, async (open) => {
  if (open) {
    query.value = ''
    activeIndex.value = 0
    await nextTick()
    inputRef.value?.focus()
  }
})

watch(results, () => {
  activeIndex.value = 0
})

function close() {
  emit('update:open', false)
}

function pick(item: typeof candidates[number]) {
  if (item.action) {
    emit('action', item.action)
  }
  else {
    emit('navigate', item.to)
  }
  close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, results.value.length - 1)
  }
  else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  }
  else if (e.key === 'Enter') {
    e.preventDefault()
    const hit = results.value[activeIndex.value]
    if (hit)
      pick(hit.item)
  }
  else if (e.key === 'Escape') {
    e.preventDefault()
    close()
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="cp-fade">
      <div
        v-if="open"
        class="cp-backdrop"
        data-testid="command-palette"
        @click.self="close"
      >
        <div class="cp-panel" role="dialog" aria-label="命令面板">
          <div class="cp-input-row">
            <svg class="cp-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              ref="inputRef"
              v-model="query"
              class="cp-input"
              type="text"
              placeholder="搜索视图或动作…（如 eln / 记忆 / 新建）"
              data-testid="command-palette-input"
              @keydown="onKeydown"
            >
            <kbd class="cp-kbd">Esc</kbd>
          </div>

          <div v-if="results.length === 0" class="cp-empty">
            没有匹配「{{ query }}」的条目
          </div>

          <ul v-else class="cp-list" data-testid="command-palette-list">
            <li
              v-for="(r, i) in results"
              :key="r.item.to"
              class="cp-item"
              :class="{ active: i === activeIndex, confident: i === 0 && confident }"
              :data-cp-label="r.item.label"
              @mouseenter="activeIndex = i"
              @click="pick(r.item)"
            >
              <!-- eslint-disable-next-line vue/no-v-html —— 常量表 SVG（非用户输入） -->
              <span class="cp-icon" v-html="r.item.icon" />
              <span class="cp-label">{{ r.item.label }}</span>
              <span v-if="r.item.action" class="cp-badge">动作</span>
              <svg v-if="i === 0 && confident" class="cp-enter-hint" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M7 17L17 7" />
                <path d="M8 7h9v9" />
              </svg>
            </li>
          </ul>

          <div class="cp-footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
            <span><kbd>Enter</kbd> 确认</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cp-backdrop {
  position: fixed;
  inset: 0;
  z-index: 11000;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 16vh;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(2px);
}

.cp-panel {
  width: min(560px, 86vw);
  display: flex;
  flex-direction: column;
  border-radius: var(--lumo-radius-lg);
  background: var(--lumo-bg-elev);
  border: 1px solid var(--lumo-border-strong);
  box-shadow: var(--lumo-shadow-2);
  overflow: hidden;
}

.cp-input-row {
  display: flex;
  align-items: center;
  gap: var(--lumo-space-2);
  padding: var(--lumo-space-3) var(--lumo-space-4);
  border-bottom: 1px solid var(--lumo-border);
}

.cp-search-icon {
  color: var(--lumo-text-faint);
  flex-shrink: 0;
}

.cp-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--lumo-text);
  font-size: 15px;
  font-family: var(--lumo-font-ui);
}

.cp-input::placeholder {
  color: var(--lumo-text-faint);
}

.cp-kbd,
.cp-footer kbd {
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--lumo-border);
  background: var(--lumo-bg-inset);
  color: var(--lumo-text-dim);
  font-size: 11px;
  font-family: var(--lumo-font-mono);
}

.cp-list {
  margin: 0;
  padding: var(--lumo-space-2);
  list-style: none;
  max-height: 46vh;
  overflow-y: auto;
}

.cp-item {
  display: flex;
  align-items: center;
  gap: var(--lumo-space-3);
  padding: var(--lumo-space-2) var(--lumo-space-3);
  border-radius: var(--lumo-radius-md);
  color: var(--lumo-text-dim);
  cursor: pointer;
}

.cp-item:hover,
.cp-item.active {
  background: rgba(255, 255, 255, 0.06);
  color: var(--lumo-text);
}

.cp-item.confident {
  background: var(--lumo-primary-tint);
  color: var(--lumo-primary);
}

.cp-icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.cp-label {
  flex: 1;
  font-size: 14px;
}

.cp-badge {
  padding: 0 6px;
  border-radius: 999px;
  border: 1px solid var(--lumo-border);
  font-size: 10px;
  color: var(--lumo-text-faint);
}

.cp-enter-hint {
  color: currentColor;
  opacity: 0.7;
  flex-shrink: 0;
}

.cp-empty {
  padding: var(--lumo-space-6) var(--lumo-space-4);
  text-align: center;
  color: var(--lumo-text-faint);
  font-size: 13px;
}

.cp-footer {
  display: flex;
  gap: var(--lumo-space-4);
  padding: var(--lumo-space-2) var(--lumo-space-4);
  border-top: 1px solid var(--lumo-border);
  color: var(--lumo-text-faint);
  font-size: 11px;
}

.cp-fade-enter-active,
.cp-fade-leave-active {
  transition: opacity 0.12s ease;
}

.cp-fade-enter-from,
.cp-fade-leave-to {
  opacity: 0;
}
</style>
