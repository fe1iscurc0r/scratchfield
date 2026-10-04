import process from 'node:process'
import vue from '@vitejs/plugin-vue'
import unocss from 'unocss/vite'
import { defineConfig } from 'vite'
import electron from 'vite-plugin-electron/simple'

const isWebOnly = !!process.env.WEB_ONLY

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    unocss(),
    !isWebOnly && electron({
      main: {
        entry: 'electron/main.ts',
        vite: {
          build: {
            rollupOptions: {
              // Keep native/electron-side deps as runtime externals.
              // This avoids Rolldown trying to bundle `electron-updater` internals
              // (e.g. its `lodash.isequal` import), which can fail on some installs.
              external: ['electron', 'electron-updater', 'lodash.isequal'],
            },
          },
        },
      },
      preload: {
        input: 'electron/preload.ts',
      },
    }),
  ],
  resolve: { alias: { '@': '/src' } },
  build: {
    // W100-06 落地：大件依赖拆独立 vendor chunk，主 chunk 体积下降（见 docs/前端体积体检）
    rollupOptions: {
      output: {
        // vite8(rolldown) 类型只收 ManualChunksFunction，用函数形式按依赖归类
        manualChunks(id: string) {
          if (!id.includes('node_modules'))
            return undefined
          if (id.includes('pixi.js') || id.includes('pixi-live2d'))
            return 'vendor-pixi'
          if (id.includes('primevue') || id.includes('primeuix'))
            return 'vendor-primevue'
          if (id.includes('markdown-it') || id.includes('highlight.js') || id.includes('dompurify'))
            return 'vendor-markdown'
          return 'vendor'
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  optimizeDeps: {
    include: [
      'primevue/accordion',
      'primevue/popover',
      'primevue/inputtext',
      'primevue/inputnumber',
      'primevue/select',
      'primevue/toggleswitch',
      'primevue/divider',
      'primevue/datatable',
      'primevue/column',
      '@vueuse/core',
    ],
  },
})
