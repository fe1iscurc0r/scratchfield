<script setup lang="ts">
import type { McpService, SkillCatalogItem } from '@/api/core'
import { Dialog } from 'primevue'
import { computed, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import EmptyState from '@/components/EmptyState.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import SkillHelpDialog from '@/views/skill/SkillHelpDialog.vue'
import SkillMcpSection from '@/views/skill/SkillMcpSection.vue'
import SkillSection from '@/views/skill/SkillSection.vue'
import { feedback } from '@/utils/feedback'


const helpVisible = ref(false)
const activeLibraryTab = ref<'mcp' | 'skill'>('mcp')

</script>

<template>
  <BoxContainer class="text-sm">
    <div class="skill-header">
      <div class="skill-header-main">
        <h1 class="skill-title">
          技能工坊
        </h1>
        <button
          type="button"
          class="skill-help-btn"
          aria-label="查看技能工坊说明"
          title="查看技能工坊说明"
          @click="helpVisible = true"
        >
          ?
        </button>
      </div>
      <div class="skill-subtitle">
        在这里管理全局 MCP、Skill，以及按名称快速安装模板。
      </div>
    </div>

    <div class="workshop-grid">
      <section class="workshop-section workshop-section-wide">
        <div class="library-tabs">
          <button
            type="button"
            class="library-tab"
            :class="{ active: activeLibraryTab === 'mcp' }"
            @click="activeLibraryTab = 'mcp'"
          >
            MCP
          </button>
          <button
            type="button"
            class="library-tab"
            :class="{ active: activeLibraryTab === 'skill' }"
            @click="activeLibraryTab = 'skill'"
          >
            Skill
          </button>
        </div>
      </section>

    <SkillMcpSection v-if="activeLibraryTab === 'mcp'" />

      <SkillSection v-else />
    </div>


    <SkillHelpDialog v-model:visible="helpVisible" />
  </BoxContainer>
</template>

<style scoped>
.skill-header {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-bottom: 1rem;
}

.skill-header-main {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.skill-title {
  margin: 0;
  color: rgba(255, 255, 255, 0.92);
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.skill-subtitle {
  color: rgba(255, 255, 255, 0.42);
  font-size: 0.76rem;
  line-height: 1.55;
}

.workshop-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  padding-bottom: 2rem;
}

.workshop-section {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-width: 0;
  padding: 0.9rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.workshop-section-wide {
  grid-column: 1 / -1;
}

.library-tabs {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  align-self: flex-start;
}

.library-tab {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.48);
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.45rem 0.9rem;
  border-radius: 999px;
  cursor: pointer;
  transition: background-color 0.18s ease, color 0.18s ease;
}

.library-tab.active {
  background: rgba(212, 175, 55, 0.14);
  color: rgba(248, 222, 159, 0.96);
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.section-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.94rem;
  font-weight: 700;
  line-height: 1.3;
}

.section-meta {
  margin-top: 0.2rem;
  color: rgba(255, 255, 255, 0.42);
  font-size: 0.74rem;
  line-height: 1.45;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  flex-shrink: 0;
}

.skill-help-btn {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.28);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(212, 175, 55, 0.88);
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.skill-help-btn:hover {
  border-color: rgba(212, 175, 55, 0.52);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(248, 222, 159, 0.96);
}



.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: 1px dashed rgba(212, 175, 55, 0.35);
  border-radius: 8px;
  background: transparent;
  color: rgba(212, 175, 55, 0.76);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.add-btn:hover:not(:disabled) {
  border-color: rgba(212, 175, 55, 0.7);
  color: rgba(212, 175, 55, 1);
  background: rgba(212, 175, 55, 0.06);
}

.add-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.add-btn-compact {
  width: auto;
  min-width: 96px;
  padding-inline: 0.9rem;
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .workshop-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .section-head {
    flex-direction: column;
  }

  .section-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .hub-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
