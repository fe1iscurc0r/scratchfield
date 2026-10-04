# Skill 分发管线勘察（参考 TanStack/cli）

> K02 ｜ 生成 2026-08-30 ｜ 勘察对象：`TanStack/cli`（MIT，v0.61.0）· 本地 `skills/`（195 个 skill）
> 目标：把「Agent Skills 安装机制」固化为 scratchpad 的 skill 分发管线（方案 + 原型）。

## 1. TanStack/cli 的 skill 模型（勘察结论）

TanStack 把「skill」定义为 **agent 面向的、可机器读取的能力说明**，不是代码插件。三条关键资产：

| 资产 | 作用 |
|------|------|
| `SKILL.md`（各 skill 目录） | 单 skill 的正文 + YAML frontmatter（name/description/license/metadata.version） |
| `skill_spec.md`（仓库根） | **权威规格**：Domain 表、Skill Inventory（type/domain/failure modes）、Tension、Composition |
| 仓库根 `AGENTS.md` / `CLAUDE.md` | agent 入口的快速参考与命令清单 |

其 skill 分发/安装靠的是「**声明式配置 + 目录约定 + 机器可读发现命令**」，而非中心化的安装器：

1. **安装协议**：skill 落在 agent 约定目录，由 agent 自行加载——
   - `.agents/index.md`（跨 agent 新标准）
   - `.claude/settings.local.json`（Claude Code）
   - `.cursor/mcp.json`（Cursor MCP 入口）
   - 仓库根 `AGENTS.md`（对所有 agent 生效的指引）
2. **版本管理**：`@tanstack/cli` 整体版本 + `tanstack pin-versions`；`skill_spec.md` 里每个 failure mode 都带 `Source`（issue # 或源码文件路径），把「为什么有这条」钉在版本历史里。
3. **发现机制**：CLI 提供 `--json` 机器可读输出（`libraries` / `doc` / `search-docs` / `ecosystem` / `--list-add-ons` / `--addon-details`），agent 先 preflight 发现、再选兼容项，避免「猜一个看似合理的默认」。

## 2. 本地 skill 目录现状（scratchpad）

- `skills/<name>/SKILL.md` 扁平目录，共 **195 个** skill。
- frontmatter 已具备：`name` / `description` / `license` / `metadata.version`（如 `citation-management` v2.0, MIT）。
- **缺口**：无统一 INDEX（等价 TanStack 的 `skill_spec.md`）、无版本/许可聚合视图、无「安装到 agent 目录」的协议工具。
- 与 TanStack 的映射：本仓 `skills/` ≈ TanStack 的 skill 集合；本仓缺 `skill_spec.md` 式的**权威索引**与 `.agents/` 式的**安装落点**。

## 3. 分发管线设计（方案）

### 3.1 安装协议

- 单一事实源：`skills/`（保持现状，一个 skill 一个目录 + `SKILL.md`）。
- 生成物：`skills/INDEX.md`（人读）+ `skills/index.json`（机器读），由原型脚本 `index` 子命令生成。
- 安装落点：`install <skill> --to <dir>` 把 skill 目录**复制/软链**到 agent 约定目录（如 `.agents/skills/<name>/`、`.claude/skills/<name>/`）。默认拒绝覆盖已有同名 skill，除非 `--force`。

### 3.2 版本管理

- 版本来源：frontmatter `metadata.version`（缺失时回退 `version`，再缺则记 `unknown` 并告警）。
- `index.json` 每项带 `version` 与 `license`，形成可审计的版本/许可清单。
- `check` 子命令做**许可与必填字段门禁**：缺 `name`/`description`/`license` 的 skill 标 `FAIL`（非阻断，仅报告），呼应 TanStack「failure mode 带 Source、不静默」。

### 3.3 本地 skill 目录集成

- 与 TanStack 对齐：`index` 产出的 `skill_spec` 式索引 = 本仓的「权威规格」；`.agents/index.md` 可选落点由 `install` 生成。
- 兼容现有 `skills/` 布局，不迁移不重构；只增不改。

## 4. 原型脚本

`scripts/skill_distribution.py`（stdlib，无第三方依赖），三个子命令：

```bash
python scripts/skill_distribution.py index            # 生成 skills/INDEX.md + index.json
python scripts/skill_distribution.py check            # frontmatter 门禁 + 许可/版本聚合
python scripts/skill_distribution.py install aeon astropy --to .agents/skills --link   # 安装到 agent 目录
```

## 5. 验收对照

- [x] 勘察 TanStack/cli 的 skill 安装/分发设计（`skill_spec.md` / `.agents` / `.claude` / `.cursor` / 版本 pinning）。
- [x] 安装协议 / 版本管理 / 本地 skill 目录集成三节方案。
- [x] 原型脚本（index / check / install）可运行。
