# Agent Skills 互通规范（Hermes ↔ Anthropic）

> 目的：让本仓库的 `skills/`（Hermes Skills-first 体系）可被外部 Agent（Claude Code / Codex / Cursor 等遵循 Anthropic Agent Skills 规范的工具）正确读取。
> 日期：2026-08-09
> 结论：我们的 SKILL.md 结构已是 Anthropic 规范的超集，无需迁移，加此映射文档即可互通。

---

## 一、为什么需要这份文档

Anthropic Agent Skills 已成为基础设施（与 MCP 并列）。外部 Agent 读取 skill 时，通常只认 `SKILL.md` 的 frontmatter 里的 `name` + `description`。我们的 `SKILL.md` 除了这两个字段，还带了 `license / compatibility / metadata` 等扩展字段——这些**不会破坏**外部读取，但做一个显式映射文档，能让外部 Agent 明确知道如何消费。

---

## 二、字段映射表

| Anthropic 规范 | Hermes（本仓库 SKILL.md） | 说明 |
|---------------|--------------------------|------|
| `name` | `name` | **一致**，直接可用 |
| `description` | `description` | **一致**，直接可用 |
| `allowed-tools` | `allowed-tools` | **一致**，可选 |
| *(无)* | `license` | 我们的扩展，提供给合规检查 |
| *(无)* | `compatibility` | 我们的扩展，运行时/依赖约束 |
| *(无)* | `metadata.version` | 我们的扩展，版本管理 |
| *(无)* | `metadata.skill-author` | 我们的扩展，溯源 |

**结论**：外部 Agent 只需读取 `name` 和 `description` 即可正常使用本仓库的 skill；其余字段是额外信息，可忽略或按需消费。

---

## 三、外部 Agent 接入指引

### 1. 定位 skill

每个 skill 是一个目录，入口文件为 `SKILL.md`（frontmatter + 正文）：

```
skills/<skill-name>/
├── SKILL.md          # 入口（frontmatter + 使用说明）
├── references/       # 可选：参考文档
└── assets/           # 可选：模板/示例
```

### 2. 读取规则

- 读 `SKILL.md` 的 frontmatter，取 `name` + `description` 判断是否适用于当前任务
- 若适用，通读正文（Overview / Quick Start / 边界）
- 需要细节时再读 `references/*.md`（不要一次性全读）

### 3. 工具权限

若 frontmatter 含 `allowed-tools`，说明该 skill 限定可用的工具集（如 `Read Write Edit Bash`）。外部 Agent 应尊重该白名单，不要越权调用 skill 未声明的工具。

---

## 四、多语言混合（我们的差异化）

普通 Anthropic skill 通常限定单一语言执行。本仓库的 skill **支持 Python / Bash / 多语言混合**，这是与 Anthropic 规范的差异点，也是我们的优势：

```text
- 单 skill 内可同时出现 Python 脚本 + shell 命令 + 可选 JS
- 通过 frontmatter 的 `allowed-tools` 表达语言/工具边界
```

外部 Agent 消费时，应容纳这种混合形态，而非假设单一语言。

---

## 五、如需严格互通（可选适配层）

若未来要求外部 Agent 严格按 Anthropic 规范消费，可加一个轻量适配脚本，把扩展字段折叠进 Anthropic 期望的最小 frontmatter：

```python
# 伪代码：仅保留 Anthropic 认可的字段
def to_anthropic(skill_md: dict) -> dict:
    return {
        "name": skill_md["name"],
        "description": skill_md["description"],
        "allowed-tools": skill_md.get("allowed-tools"),
    }
```

**注意**：我们的 `description` 已足够自描述（含域、能力、依赖），外部 Agent 无需额外字段即可决定是否调用。

---

## 六、元记录

- **关联**：`docs/GitHub-Trending-August-2026-Exec-Report.md`（agent-skills 对比章节）
- **原则**：不迁移到 Anthropic 规范，保持自主；多语言混合是差异化优势
- **状态**：映射文档即交付，无需改动任何现有 SKILL.md