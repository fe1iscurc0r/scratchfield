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

## 工单与报告的归档路径

历史工单与报告**只移不改**（是台账）：

- 历史工单卷（`TRAE_WORKORDER_PROMPT_AGENT_1*.md`、`BATCH-WORKORDERS-*.md`）与
  历史法学贡献工单（`LAW_WORKORDER_CONTRIB_L*.md`）→ `workorders/archive/`
- 执行报告（`EXEC-REPORT-*.md`、阶段报告）→ `docs/exec-reports/`
- 根目录只保留**最新 3 卷**工单 + **最新 1 卷**法学贡献工单；
  `LAW_WORKORDER_CONTRIB_L<n>.md` 的命名规则不变——法学贡献者按卷号在
  `workorders/archive/` 里找历史版本。

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

## 文件长度（卷190 闸门）

单文件（`.py` / `.ts` / `.vue`）**超过 800 行**即触发报警：

```bash
python scripts/check_file_size.py           # 报警（不阻塞）
python scripts/check_file_size.py --strict  # CI 闸门：新增超限 → exit 1
```

- 存量巨石在 `scripts/file_size_baseline.json` **红名单**里豁免；**新文件或新膨胀一律报出来**。
- 新增文件超过 800 行时，请在 PR 描述里说明理由（按领域拆不开？确有必要的生成代码？）。
- 拆分完成后跑 `--update-baseline` **收窄**名单——不要为了过闸门而加宽。

## 协议

本项目主体为 AGPL-3.0。入站组件保留其原始许可（Apache 2.0 / MIT）。请勿提交 GPL 不兼容的代码。第三方依赖的引入需要明确标注许可和来源。

## 审核

所有 PR 需要至少一位维护者审查。审查流程：
1. 铁锚：代码审查（语法/逻辑/安全）
2. 实验田维护者：结构化审计（一致性/兼容性）
3. 维护者：最终合并决定
