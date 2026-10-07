<script setup lang="ts">
import { Dialog } from 'primevue'

/**
 * 技能工坊说明弹窗 —— 自 `SkillView.vue` 拆出（工单204 任务三）。
 *
 * 纯展示组件：可见性由父组件通过 `v-model:visible` 控制；
 * 触发按钮（`.skill-help-btn`）与主视图布局仍在父组件。
 */
const visible = defineModel<boolean>('visible', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="技能工坊说明"
    :style="{ width: 'min(720px, 92vw)' }"
  >
    <div class="skill-help">
      <section>
        <h4>通用 MCP</h4>
        <p>MCP 可以理解为“外接工具服务”，比如搜索、抓取、系统能力之类的接口。这里管理全局可用的 MCP，启用后陆墨和多个干员都可以共用。</p>
      </section>
      <section>
        <h4>通用 Skill</h4>
        <p>Skill 可以理解为“能力模板 / 做事方法”，它决定模型在特定任务里该怎么组织步骤和使用工具。这里管理全局可用的 Skill，启用后陆墨和多个干员都可以共用。</p>
      </section>
      <section>
        <h4>添加方式</h4>
        <p>点击“添加 MCP”或“添加 Skill”后，可以在弹窗里切换“从 Hub 下载”或“自定义导入”。当前 Skill 下载源支持腾讯 SkillHub 和 ClawHub。</p>
      </section>
    </div>
  </Dialog>
</template>

<style scoped>
.skill-help {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.84rem;
  line-height: 1.7;
}

.skill-help h4 {
  margin: 0 0 0.25rem;
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.9rem;
  font-weight: 700;
}

.skill-help p {
  margin: 0;
}
</style>
