<template>
  <!-- 模型 Tab：API 配置（模型源/密钥/网关）。
       占位实现（2026-10-04 展示仓补齐）：原始拆分文件（卷181）未随工单提交，
       此处按 ConfigView 既有表单模式恢复最小可用版；完整版待上游补交后替换。 -->
  <ConfigGroup value="model-0" header="模型服务">
    <ConfigItem name="API Base URL" description="模型服务地址（留空用默认）">
      <input v-model="apiBase" class="cfg-input" placeholder="https://api.example.com/v1" />
    </ConfigItem>
    <ConfigItem name="API Key" description="模型服务密钥（仅本地保存）">
      <input v-model="apiKey" type="password" class="cfg-input" placeholder="sk-..." />
    </ConfigItem>
    <ConfigItem name="默认模型" description="对话主模型名">
      <input v-model="defaultModel" class="cfg-input" placeholder="glm-4.7" />
    </ConfigItem>
  </ConfigGroup>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'

const apiBase = ref('')
const apiKey = ref('')
const defaultModel = ref('')
</script>

<style scoped>
.cfg-input {
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--p-border-color, #ccc);
  background: transparent;
  color: inherit;
}
</style>
