<template>
  <!-- 音画 Tab：TTS/音频输出配置。
       占位实现（2026-10-04 展示仓补齐）：原始拆分文件（卷181）未随工单提交，
       此处按 ConfigView 既有表单模式恢复最小可用版；完整版待上游补交后替换。 -->
  <ConfigGroup value="audio-0" header="音画配置">
    <ConfigItem name="TTS 引擎" description="语音合成引擎选择">
      <select v-model="ttsEngine" class="cfg-select">
        <option value="edge">Edge TTS（在线，免密钥）</option>
        <option value="kokoro">Kokoro（本地，离线）</option>
        <option value="off">关闭语音</option>
      </select>
    </ConfigItem>
    <ConfigItem name="自动朗读" description="收到回复后自动朗读">
      <input v-model="autoSpeak" type="checkbox" />
    </ConfigItem>
    <ConfigItem name="音量" description="语音输出音量（0-100）">
      <input v-model.number="volume" type="range" min="0" max="100" class="cfg-range" />
      <span>{{ volume }}</span>
    </ConfigItem>
  </ConfigGroup>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'

const ttsEngine = ref('edge')
const autoSpeak = ref(false)
const volume = ref(80)
</script>

<style scoped>
.cfg-select {
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--p-border-color, #ccc);
  background: transparent;
  color: inherit;
}
.cfg-range {
  vertical-align: middle;
  margin-right: 8px;
}
</style>
