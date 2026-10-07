<script setup lang="ts">
import type { SkillCatalogItem } from '@/api/core'
import { computed, ref } from 'vue'
import API from '@/api/core'
import EmptyState from '@/components/EmptyState.vue'
import SkeletonCard from '@/components/SkeletonCard.vue'
import SkillAddDialog from '@/components/SkillAddDialog.vue'
import { feedback } from '@/utils/feedback'

/**
 * 通用 Skill 区（技能库列表）—— 自 `SkillView.vue` 拆出（工单204 任务三）。
 *
 * 自治组件：own state / own API 调用 / own 样式（scoped 不跨组件生效，样式随组件搬）。
 * 父组件用 `v-else`（与 MCP 区互斥）控制挂载。
 */
const skillCatalogLoading = ref(true)
const localCacheSkills = ref<SkillCatalogItem[]>([])
const publicSkills = ref<SkillCatalogItem[]>([])
const showSkillDialog = ref(false)

async function loadSkillCatalog() {
  skillCatalogLoading.value = true
  try {
    const res = await API.getSkillCatalog()
    localCacheSkills.value = res.catalog.localCache.skills || []
    publicSkills.value = res.catalog.publicSkills.skills || []
  }
  catch {
    localCacheSkills.value = []
    publicSkills.value = []
  }
  finally {
    skillCatalogLoading.value = false
  }
}

function openSkillDialog() {
  showSkillDialog.value = true
}

async function onSkillConfirm(data:
  | { mode: 'hub', name: string, source: string }
  | { mode: 'cache', name: string, sourceScope: 'cache' | 'public' | 'private', sourceAgentId?: string }
  | { mode: 'custom', name: string, content: string, scope: 'cache' | 'public' | 'private', agentId?: string }) {
  try {
    if (data.mode === 'hub') {
      await API.installHubSkill({
        name: data.name,
        scope: 'public',
        source: data.source,
      })
    }
    else if (data.mode === 'cache') {
      await API.cloneSkill({
        name: data.name,
        sourceScope: data.sourceScope,
        sourceAgentId: data.sourceAgentId,
        targetScope: 'public',
      })
    }
    else {
      await API.importScopedSkill(data)
    }
    showSkillDialog.value = false
    feedback.success('已导入')
    await loadSkillCatalog()
  }
  catch (error: any) {
    feedback.error('导入失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}

async function deleteScopedSkill(skill: SkillCatalogItem) {
  const scope = skill.scope === 'public' ? 'public' : 'cache'
  try {
    await API.deleteSkill(skill.name, scope)
    feedback.success('已删除')
    await loadSkillCatalog()
  }
  catch (error: any) {
    feedback.error('删除失败', error?.response?.data?.detail || error?.message || '未知错误')
  }
}


const installedSkills = computed(() => {
  const merged = [...publicSkills.value, ...localCacheSkills.value]
  return merged.sort((a, b) => {
    const score = (skill: SkillCatalogItem) => {
      if (skill.source === 'naga-public')
        return 0
      if (skill.source === 'naga-cache')
        return 1
      if (skill.source === 'openclaw-local')
        return 2
      return 3
    }
    const diff = score(a) - score(b)
    if (diff !== 0)
      return diff
    return a.name.localeCompare(b.name, 'zh-Hans-CN')
  })
})


void loadSkillCatalog()
</script>

<template>
  <section class="workshop-section workshop-section-wide">
        <div class="section-head">
          <div>
            <div class="section-title">Skill</div>
            <div class="section-meta">
              通用 Skill。这里管理全局可用的 Skill。启用后，陆墨和多个干员都可以共用。
            </div>
          </div>
          <div class="section-actions">
            <button class="add-btn add-btn-compact" @click="openSkillDialog()">
              添加 Skill
            </button>
          </div>
        </div>

        <SkeletonCard v-if="skillCatalogLoading" :rows="5" />
        <template v-else>
          <div
            v-for="skill in installedSkills"
            :key="`${skill.source}:${skill.name}`"
            class="skill-item min-w-0"
          >
            <div class="flex-1 min-w-0 overflow-hidden">
              <div class="flex items-center gap-2">
                <div class="font-bold text-sm text-white truncate">{{ skill.name }}</div>
              </div>
              <div class="text-xs op-50 truncate">
                {{ skill.description || '暂无描述' }}
              </div>
            </div>
            <button class="skill-action-btn skill-action-delete" title="删除 Skill" @click="deleteScopedSkill(skill)">
              删除
            </button>
          </div>
          <EmptyState
            icon="🛠"
            title="还没有安装技能"
            description="从市场安装，或添加本地 SKILL.md"
            action-label="去市场看看"
            @action="$router.push('/market')"
          />
        </template>
  </section>

    <SkillAddDialog
      :visible="showSkillDialog"
      fixed-scope="public"
      hub-enabled
      title="添加 Skill"
      @confirm="onSkillConfirm"
      @cancel="showSkillDialog = false"
    />
</template>

<style scoped>
/* 共享部分（scoped 不跨组件生效，故与父组件各留一份）：section-head 系列 + add-btn 系列 */
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

/* Skill 区专属 */
.skill-item,
.hub-card {
  display: flex;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.skill-item:hover,
.hub-card:hover {
  background: rgba(255, 255, 255, 0.08);
}

.skill-placeholder,
.hub-endpoint-card {
  padding: 0.75rem 0.85rem;
  border-radius: 8px;
  border: 1px dashed rgba(212, 175, 55, 0.28);
  background: rgba(212, 175, 55, 0.04);
  font-size: 0.76rem;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.6;
}

.hub-endpoint-title {
  font-weight: 700;
  color: rgba(255, 255, 255, 0.82);
  margin-bottom: 0.35rem;
}

.hub-endpoint-line code {
  font-size: 0.72rem;
}

.hub-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.85rem;
}

.hub-card {
  flex-direction: column;
  align-items: stretch;
  gap: 0.7rem;
}

.hub-card-title {
  font-size: 0.9rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
}

.hub-note {
  font-size: 0.74rem;
  color: rgba(255, 255, 255, 0.45);
  line-height: 1.55;
}

.hub-feedback {
  padding: 0.6rem 0.7rem;
  border-radius: 8px;
  font-size: 0.74rem;
  line-height: 1.5;
}

.hub-feedback.success {
  color: rgba(74, 222, 128, 0.95);
  background: rgba(74, 222, 128, 0.08);
}

.hub-feedback.error {
  color: rgba(255, 141, 141, 0.95);
  background: rgba(255, 141, 141, 0.08);
}

.skill-action-btn {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.46);
  font-size: 0.74rem;
  cursor: pointer;
  transition: color 0.15s ease;
}

.skill-action-delete:hover {
  color: #ff8d8d;
}
</style>
