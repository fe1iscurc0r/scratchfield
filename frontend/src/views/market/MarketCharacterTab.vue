<!-- 角色注册 tab（卷190-B2：从 MarketView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useCharacterCards } from './composables/useCharacterCards'
import { initDragScroll } from './composables/useDragScroll'

const props = defineProps<{
  activeTab: string
}>()

const {
  expandedCard,
  characters,
  loadRegisteredCharacters,
  computeAllCardWidths,
  setCardRef,
  toggleCard,
  onSectionClick,
  applyCharacter,
  customChar,
  customReady,
  fileInputRef,
  triggerFileInput,
  onFileChange,
  applyCustomCharacter,
} = useCharacterCards()

const characterSectionRef = ref<HTMLElement | null>(null)

onMounted(() => {
  if (characterSectionRef.value)
    initDragScroll(characterSectionRef.value)
  loadRegisteredCharacters()
})

// 标签可见时执行卡片宽度计算
watch(() => props.activeTab, (tab) => {
  if (tab === 'memory-skin') {
    nextTick(computeAllCardWidths)
  }
})
</script>

<template>
  <section ref="characterSectionRef" class="character-section" @click="onSectionClick">
    <div class="character-grid">
      <div
        v-for="char in characters"
        :key="char.id"
        :ref="(el: any) => setCardRef(char.id, el)"
        class="char-card"
        :class="{ expanded: expandedCard === char.id }"
        @click.stop="toggleCard(char.id)"
      >
        <img
          :src="char.portraitUrl"
          :alt="char.name"
          class="char-portrait-img"
        >
        <!-- 底部渐变遮罩 -->
        <div class="char-portrait-gradient" />
        <!-- 收缩态角色名 -->
        <div class="char-name-tag">
          {{ char.name }}
        </div>
        <!-- 展开态简介面板：绝对定位覆盖在卡片底部 -->
        <div class="char-desc-panel">
          <h3 class="char-desc-title">
            {{ char.name }}
          </h3>
          <p class="char-desc-text">
            {{ char.bio }}
          </p>
          <button
            type="button"
            class="char-apply-btn"
            @click.stop="applyCharacter(char.name)"
          >
            录入角色
          </button>
        </div>
      </div>

      <!-- 自定义角色卡 -->
      <div
        :ref="(el: any) => setCardRef('custom', el)"
        class="char-card custom-card"
        :class="{ expanded: expandedCard === 'custom' }"
        @click.stop="toggleCard('custom')"
      >
        <!-- 收缩态：+ 图标 + 文字 -->
        <div v-if="expandedCard !== 'custom'" class="custom-collapsed">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          <span class="custom-label">自定义角色</span>
        </div>
        <!-- 展开态：表单 -->
        <div v-else class="custom-form" @click.stop>
          <label class="custom-field">
            <span class="custom-field-label">角色名称</span>
            <input
              v-model="customChar.name"
              type="text"
              class="custom-input"
              placeholder="输入角色名称"
            >
          </label>
          <div class="custom-field">
            <span class="custom-field-label">L2D 模型</span>
            <input
              ref="fileInputRef"
              type="file"
              webkitdirectory
              directory
              multiple
              style="display:none"
              @change="onFileChange"
            >
            <button type="button" class="custom-file-btn" @click="triggerFileInput">
              {{ customChar.modelFiles.length ? `${customChar.modelFiles.length} 个模型资源文件` : '选择 Live2D 模型目录' }}
            </button>
            <span v-if="customChar.modelPath" class="custom-file-hint">
              {{ customChar.modelPath }}
            </span>
          </div>
          <label class="custom-field custom-field-grow">
            <span class="custom-field-label">系统提示词</span>
            <textarea
              v-model="customChar.prompt"
              class="custom-textarea"
              placeholder="输入系统提示词"
            />
          </label>
          <button
            type="button"
            class="char-apply-btn"
            :class="{ disabled: !customReady }"
            :disabled="!customReady || customChar.uploading"
            @click.stop="customReady && applyCustomCharacter()"
          >
            {{ customChar.uploading ? '录入中...' : '录入角色' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* ── 角色注册 ── */
.character-section {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 16px 24px;
  display: flex;
  align-items: stretch;
  min-height: 0;
  cursor: grab;
  user-select: none;
}

.character-section::-webkit-scrollbar {
  height: 4px;
}

.character-section::-webkit-scrollbar-track {
  background: transparent;
}

.character-section::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.25);
  border-radius: 2px;
}

.character-grid {
  display: flex;
  gap: 16px;
  height: 100%;
  align-items: stretch;
}

/* ── 角色卡：高度恒定，只变宽度，内部全部绝对定位 ── */
.char-card {
  position: relative;
  height: 100%;
  width: var(--collapsed-w, 130px);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.15);
  cursor: pointer;
  transition:
    width 0.5s cubic-bezier(0.33, 1, 0.68, 1),
    background 0.3s,
    border-color 0.3s,
    box-shadow 0.3s;
  flex-shrink: 0;
}

.char-card:hover {
  border-color: rgba(212, 175, 55, 0.4);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.4),
    0 0 12px rgba(212, 175, 55, 0.1);
}

.char-card.expanded {
  width: var(--expanded-w, 300px);
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}

.char-portrait-img {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  height: 100%;
  width: auto;
  z-index: 0;
}

/* 立绘底部渐变遮罩 */
.char-portrait-gradient {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 80px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
  pointer-events: none;
  z-index: 1;
}

/* 收缩态角色名：绝对定位在底部 */
.char-name-tag {
  position: absolute;
  bottom: 10px;
  left: 10px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.8);
  z-index: 2;
  transition: opacity 0.3s;
}

.char-card.expanded .char-name-tag {
  opacity: 0;
}

/*
 * 展开态简介面板：绝对定位覆盖在卡片底部
 * 不占据任何布局空间，立绘区域高度始终不变
 */
.char-desc-panel {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 3;
  padding: 10px 12px 12px;
  background: linear-gradient(transparent, rgba(10, 12, 16, 0.92) 25%);
  display: flex;
  flex-direction: column;
  opacity: 0;
  transform: translateY(100%);
  transition:
    opacity 0.4s ease,
    transform 0.5s cubic-bezier(0.33, 1, 0.68, 1);
  pointer-events: none;
}

.char-card.expanded .char-desc-panel {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.char-desc-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 700;
  color: rgba(251, 191, 36, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
}

.char-desc-text {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(203, 213, 225, 0.85);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── "录入角色"按钮 ── */
.char-apply-btn {
  margin-top: 8px;
  padding: 4px 14px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(251, 191, 36, 0.95);
  background: transparent;
  border: 1px solid rgba(251, 191, 36, 0.5);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.04em;
  align-self: center;
  flex-shrink: 0;
}

.char-apply-btn:hover {
  background: rgba(251, 191, 36, 0.12);
  border-color: rgba(251, 191, 36, 0.8);
}

.char-apply-btn.disabled {
  color: rgba(148, 163, 184, 0.45);
  border-color: rgba(148, 163, 184, 0.2);
  cursor: not-allowed;
}

.char-apply-btn.disabled:hover {
  background: transparent;
  border-color: rgba(148, 163, 184, 0.2);
}

/* ── 自定义角色卡 ── */
.custom-card {
  background: rgba(22, 26, 35, 0.95);
}

.custom-card.expanded {
  background: rgba(22, 26, 35, 0.95) !important;
  border-color: rgba(148, 163, 184, 0.15) !important;
  box-shadow: none !important;
}

.custom-collapsed {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: rgba(248, 250, 252, 0.45);
  transition: color 0.2s;
}

.custom-card:hover .custom-collapsed {
  color: rgba(251, 191, 36, 0.8);
}

.custom-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

.custom-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 12px;
  height: 100%;
  overflow-y: auto;
}

.custom-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.custom-field-grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.custom-field-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(251, 191, 36, 0.85);
  letter-spacing: 0.03em;
}

.custom-input {
  padding: 6px 8px;
  font-size: 12px;
  color: rgba(248, 250, 252, 0.9);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  outline: none;
  transition: border-color 0.2s;
}

.custom-input:focus {
  border-color: rgba(251, 191, 36, 0.5);
}

.custom-file-btn {
  padding: 6px 8px;
  font-size: 11px;
  color: rgba(248, 250, 252, 0.7);
  background: rgba(255, 255, 255, 0.06);
  border: 1px dashed rgba(148, 163, 184, 0.25);
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-file-btn:hover {
  border-color: rgba(251, 191, 36, 0.45);
  background: rgba(255, 255, 255, 0.08);
}

.custom-file-hint {
  color: rgba(248, 250, 252, 0.44);
  font-size: 10px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.custom-textarea {
  flex: 1;
  min-height: 60px;
  padding: 6px 8px;
  font-size: 12px;
  color: rgba(248, 250, 252, 0.9);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  outline: none;
  resize: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.custom-textarea:focus {
  border-color: rgba(251, 191, 36, 0.5);
}
</style>
