# 贡献指南

感谢你对陆墨 Lumo 的关注！

## 范围

本项目是个人主导的开源项目。接受以下类型的贡献：
- Bug 修复
- 文档改进
- MCP Agent / Skill 适配器
- 材料科学知识库补充

## 流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/your-feature`
3. 提交更改：`git commit -m "feat(module): what you did"`
4. 推送到 Fork：`git push origin feat/your-feature`
5. 创建 Pull Request 到 `master` 分支

## 提交规范

使用约定式提交：

```
feat(scope): 描述
fix(scope): 描述
docs(scope): 描述
chore(scope): 描述
refactor(scope): 描述
test(scope): 描述
```

scope 示例：`adapters` `mcpserver` `frontend` `apiserver` `skills` `docs`

## 代码风格

- Python：遵循 ruff 规则
- TypeScript/Vue：遵循 ESLint + Prettier
- 提交前跑 `python -m ruff check .` 和 `npm run lint`

## 协议

本项目主体为 AGPL-3.0。入站组件保留其原始许可（Apache 2.0 / MIT）。请勿提交 GPL 不兼容的代码。第三方依赖的引入需要明确标注许可和来源。

## 审核

所有 PR 需要至少一位维护者审查。审查流程：
1. 铁锚：代码审查（语法/逻辑/安全）
2. 沈遥：结构化审计（一致性/兼容性）
3. 维护者：最终合并决定
