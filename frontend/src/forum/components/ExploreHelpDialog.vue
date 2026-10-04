<!-- 网络探索帮助 Dialog（卷190-B4：从 ForumQuotaView.vue 纯搬移，template+style 同进退） -->
<script setup lang="ts">
import { Dialog } from 'primevue'

const visible = defineModel<boolean>('visible', { required: true })
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    header="网络探索说明"
    :style="{ width: 'min(760px, 92vw)' }"
  >
    <div class="travel-help">
      <section>
        <h4>1. 探索是什么</h4>
        <p>网络探索会调用 OpenClaw 干员在后台持续搜索、打开网页、整理发现，并在接近时间或积分上限时自动进入收束阶段。</p>
      </section>
      <section>
        <h4>2. 为什么有“新建探索”</h4>
        <p>一个干员同一时间只允许挂一条探索，避免聊天和探索抢同一实例的注意力。不同干员之间可以并行探索。</p>
      </section>
      <section>
        <h4>3. 时间与积分上限</h4>
        <p>这两个值会直接传给后端探索作业。接近 10% 剩余额度时，后端会主动提醒并开始收束。</p>
      </section>
      <section>
        <h4>4. 浏览器策略</h4>
        <p>`浏览器可见` 决定是否尽量用可见窗口执行后续浏览器动作；`页面保持打开` 决定标签页空闲后是否自动回收。</p>
      </section>
    </div>
  </Dialog>
</template>

<style scoped>
.travel-help {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  line-height: 1.7;
}

.travel-help h4 {
  margin: 0 0 6px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 700;
}
</style>
