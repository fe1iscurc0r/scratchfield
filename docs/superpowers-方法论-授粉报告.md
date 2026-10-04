# WO-02: superpowers 方法论授粉报告

> 日期：2026-08-22 晚 | 委托：实验田维护者自做 | 状态：✅ 完成
> 输入：obra/superpowers（MIT，275k★）| 模式：只读分析，不 clone 进主仓

## 一、superpowers 体系解剖（源码实读）

### 1. 三层技能结构（14 个 SKILL.md）

| 层 | 技能 | 职责 |
|----|------|------|
| **Bootstrap 层** | using-superpowers | 会话启动即加载，强制"1% 可能适用就必须调用"规则 |
| **流程层** | brainstorming → writing-plans → executing-plans → dispatching-parallel-agents → verification-before-completion → finishing-a-development-branch | 端到端开发流程：创意→计划→执行→验证→收尾 |
| **工程层** | test-driven-development / systematic-debugging / requesting-code-review / receiving-code-review / using-git-worktrees / writing-skills / subagent-driven-development | 单点工程技能 |

### 2. 核心机制（可直接借鉴）

**① 渐进式披露（Progressive Disclosure）**
- frontmatter `description` 是唯一触发入口，正文按需展开（"Use when..." 模式）
- 触发后才加载全文，不占上下文

**② 硬门控（HARD-GATE）** — brainstorming/SKILL.md
```
Do NOT ... write any code ... until you have told your human partner
what you intend and they have approved it.
This applies to EVERY task on EVERY path — the ceremony scales with the task;
the approval gate never does.
```
- 批准门永不关闭，只是仪式随任务规模伸缩 —— **与用户"说设想立即收手"偏好同构**（实验田维护者/用户工作流可套）

**③ 强制触发（"1% 规则"）** — using-superpowers/SKILL.md
```
If you think there is even a 1% chance a skill might apply to what you are doing,
you ABSOLUTELY MUST invoke the skill.
```
- 触发是义务不是选项，消除"忘记用技能"

**④ 技能即代码（Skills are code, not prose）** — AGENTS.md:95
- 技能修改必须经过 eval 验证（Drill 框架：真实 tmux 会话跑 Claude Code/Codex/Gemini CLI，LLM 判分）
- 行为塑造内容的高变更门槛

**⑤ 领域隔离** — AGENTS.md:56
- 通用技能进 core；特定领域（预测市场/游戏/组合管理）独立插件
- "对完全不同的项目还有用吗？没有就单独发布"

### 3. 触发链路（bootstrap 关键）

```
会话启动 → using-superpowers 加载（CLAUDE.md/AGENTS.md 注入）
→ "Let's build X" 自动触发 brainstorming
→ 批准后 writing-plans（计划给"零上下文+坏品味+讨厌测试的初级工程师"看）
→ executing-plans + subagent-driven-development 并行执行
→ verification-before-completion → finishing-a-development-branch
```

## 二、与 scratchpad skills/ 现状对照

| 维度 | superpowers | scratchpad（186 skills） | 差距 |
|------|------------|--------------------------|------|
| 技能数量 | 14（精） | 186（广） | 反向——scratchpad 重领域轻流程 |
| 流程层 | ✅ 完整闭环 | ❌ 无 brainstorming/writing-plans 等价物 | **最大缺口** |
| 触发机制 | 强制 1% 规则 + bootstrap | 被动按需加载 | 缺"自动触发" |
| 门控 | HARD-GATE 批准门 | 无强制门 | 缺 |
| 评估 | Drill eval 框架 | 无 | 缺 |
| 分层 | 三层清晰 | 扁平 | 缺 meta 层 |

## 三、授粉建议（给 scratchpad skills/ 重构）

1. **补流程层 3 件套**（最高优先级）：
   - `brainstorming`（改造成"需求收敛"：用户说设想→先问意图→出设计→等批准，对应实验田维护者职责）
   - `writing-plans`（改造：SPEC → 分块任务，喂 Trae 的工单格式可直接套用）
   - `verification-before-completion`（验收门：工单验收 grep/assert 已有基础，补"完成前验证"仪式）

2. **bootstrap 触发**：仿 using-superpowers 写一个 `skill-bootstrap`，注入 AGENTS.md，声明"1% 规则"

3. **技能即代码理念**：新技能/改技能时附"行为验收"（一个可执行的自测用例），照 superpowers-evals 简化版

4. **领域隔离**：现有 186 skills 按"通用/科研/Lumo 专用"打标签，专用技能移出 core 列表（暂不物理搬迁）

## 四、硬约束检查

- ✅ 未 clone 进主仓（/tmp 临时读）
- ✅ 报告进 docs/
- ✅ 引用行号：using-superpowers/SKILL.md L12-18（1%规则）、brainstorming/SKILL.md L13-17（HARD-GATE）、AGENTS.md L95-108（技能即代码+评估）
