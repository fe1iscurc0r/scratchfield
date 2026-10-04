import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

// 单元测试配置：仅收集 tests/unit/（与 node:test 的 tests/*.test.ts 分离，避免双跑冲突）
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json-summary'],
      include: ['src/components/ArkButton.vue', 'src/components/Markdown.vue', 'src/components/MessageItem.vue'],
    },
  },
})
