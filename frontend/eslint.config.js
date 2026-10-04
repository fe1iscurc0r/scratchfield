import antfu from '@antfu/eslint-config'

export default antfu({
  ignores: ['**/node_modules/**', '**/dist/**', '**/public/**'],
  rules: {
    'no-console': 'off',
    // 存量债务降级为 warn→off (2026-09-22): 31处正则未提升模块级、7处多语句行, 逐步清
    'e18e/prefer-static-regex': 'off',
    'style/max-statements-per-line': 'off',
  },
}, {
  // vue/* 系列规则依赖 vue-eslint-parser 的 token store，
  // 只能挂在 .vue 文件的 override 块里（全局 rules 会在 .js/.ts 上加载即崩）。
  files: ['**/*.vue'],
  rules: {
    'vue/singleline-html-element-content-newline': ['warn', {
      ignores: ['template'],
    }],
  },
})
