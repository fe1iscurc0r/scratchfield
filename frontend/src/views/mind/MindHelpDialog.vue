<!-- 记忆云海说明 Dialog（卷190-B5：从 MindView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import Dialog from 'primevue/dialog'

const visible = defineModel<boolean>('visible', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="记忆云海说明"
    :style="{ width: 'min(720px, 92vw)' }"
  >
    <div class="mind-help">
      <section>
        <h4>记忆云海是什么</h4>
        <p>记忆云海是一种三维的知识图谱，用来展示当前记忆中的实体、关系和五元组，帮助你从整体上理解长期记忆结构。</p>
      </section>
      <section>
        <h4>你能做什么</h4>
        <p>你可以搜索关键词、查看记忆规模，并通过图谱关系观察不同实体之间是怎么关联起来的。</p>
      </section>
      <section>
        <h4>高度与遗忘</h4>
        <p>调度频率越高的记忆会越靠上方，说明它被注入 AI 上下文的频率也更高；随着时间推移，这些记忆会逐渐变小，用来模拟遗忘过程。</p>
      </section>
      <section>
        <h4>分区与聚焦</h4>
        <p>实体按类型分成若干个扇区（簇），同类聚在一起。点与点之间的跨区连线会沿骨架走并在公共段捆绑成「束流」，所以一眼能看出“哪两个领域联系最密”。</p>
      </section>
      <section>
        <h4>三级视距</h4>
        <p><b>远景</b>：只画度数最高的 50 个 hub 和各簇轮廓；点图例或外环标题则进入<b>中景</b>（该簇展开）；再点具体节点进入<b>近景</b>（只留它的 1-hop 邻域）。点空白处逐级退出。</p>
      </section>
      <section>
        <h4>聊天探索</h4>
        <p>点「聊天探索」后直接说一句自然语言（如“看看木质素相关记忆”），系统会抽出关键词、拉出子图并自动聚焦到最相关的那个簇。</p>
      </section>
      <section>
        <h4>显示范围</h4>
        <p>服务端分页后，画面单次最多纳入 500 个实体（高度优先），并在实体数超过 150 时自动切到四叉树近似力导向。这不影响实际 LLM 调度。</p>
      </section>
    </div>
  </Dialog>
</template>

<style scoped>
.mind-help {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.84rem;
  line-height: 1.7;
}

.mind-help h4 {
  margin: 0 0 0.25rem;
  color: rgba(255, 255, 255, 0.9);
  font-size: 0.9rem;
  font-weight: 700;
}

.mind-help p {
  margin: 0;
}
</style>
