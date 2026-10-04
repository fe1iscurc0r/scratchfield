import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    // 拆分第三方依赖为独立 chunk：应用代码改动时 vendor/leaflet 可被浏览器长缓存
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules')) {
            if (id.includes('leaflet')) return 'leaflet'
            return 'vendor'
          }
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期把 /api 代理到 FastAPI 后端（默认 :18000），免 CORS
      '/api': { target: 'http://localhost:18000', changeOrigin: true },
    },
  },
})
