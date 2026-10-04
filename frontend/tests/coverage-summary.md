# 前端测试覆盖小结（W100-03 + 优化轮 · 2026-09-08）

## 测试运行方式

- 纯函数/Electron 逻辑：`npm run test` = `node --test --experimental-strip-types tests/*.test.ts`
- 组件挂载级：`npm run test:unit` = `vitest run`（vitest 4 + jsdom + @vue/test-utils，
  仅收集 tests/unit/，与 node:test 分离避免双跑冲突）；覆盖率 `npm run test:unit:coverage`

## 结果

**node:test：36 测试全绿（9 文件）；vitest：14 测试全绿（3 文件）。**

vitest 组件覆盖率（v8，3 个核心组件）：

| 组件 | Stmts | Branch | Funcs | Lines |
|------|-------|--------|-------|-------|
| ArkButton.vue | 100% | 91.7% | 100% | 100% |
| MessageItem.vue | 73.0% | 49.1% | 50% | 72.2% |
| Markdown.vue | 53.3% | 0% | 50% | 53.3% |
| **All files** | **70.2%** | 53.6% | 58.3% | 69.1% |

## 覆盖边界（诚实标注）

- 组件层已升级为**挂载级覆盖**（真实渲染 + DOMPurify XSS 拦截断言）。
- 视图级（15 视图）仍无覆盖——渲染/交互靠构建期类型检查与手动验收兜底。

## 结论

纯函数 + Electron 逻辑 + 3 个核心组件挂载级三层覆盖；测试零回归全绿。
