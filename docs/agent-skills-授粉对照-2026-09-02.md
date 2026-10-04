# agent-skills 授粉对照落地 · 2026-09-02

> 实验田维护者 · addyosmani/agent-skills（91.7k★ MIT）对照 scratchpad 自有 skills 的差距分析
> 来源：fusion/agent-skills-src.tar.gz（25 个生产级 skill 目录）
> 方法：只读对照，不照抄；挑最值钱的 3 处授粉，其余列观察

## 对照表：agent-skills vs 自有

| agent-skills | 自有对应 | 差距判定 |
|---|---|---|
| spec-driven-development | writing-plans / plan | ⚡ 缺 **Phase 0 能力图分解** + **门控工作流** + **稳定模块 ID** |
| source-driven-development | codebase-design / domain-modeling | ⚡ 缺"以源码为唯一事实源"的纪律化流程 |
| context-engineering | headroom / context_compressor | ⚡ 缺**上下文五层分层**（Rules→Docs→Memory→Models→Tokens） |
| test-driven-development | test-driven-development | ✅ 已有 |
| code-review-and-quality | requesting-code-review | ✅ 已有 |
| debugging-and-error-recovery | diagnosing-bugs / systematic-debugging | ✅ 已有 |
| constraint-driven-development | defensive-engineering | 🔶 部分重叠，可借鉴门控写法 |
| doubt-driven-development | （无） | 🆕 新概念：把"不确定"显式编码成决策门 |
| documentation-and-adrs | writing-great-skills | 🔶 缺 ADR 纪律（另见 mattpocock 授粉） |
| security-and-hardening | requesting-code-review 安全门 | 🔶 部分重叠 |

## 授粉点 1：Phase 0 能力图分解（spec-driven 最值钱）

**问题**：自有 writing-plans 直接写实现计划，但**一个需求捆绑多个独立可测能力**时没有先分解——导致计划庞大、难以单独验证、改动互相纠缠。

**agent-skills 做法**（Phase 0，只在多能力请求时激活）：
```markdown
# Capability Map: [Initiative Name]
| Module id | Responsibility | Depends on |
|---|---|---|
| identity | Accounts, sessions, SSO | — |
| billing | Plans, invoices, payments | identity |
| notifications | Email/webhook fan-out | identity |
| reporting | Usage dashboards | billing, notifications |

Build order: identity → billing, notifications → reporting
```

**关键纪律**：
1. **稳定模块 ID**（kebab-case，中途不重命名）——spec/plan/命令都用 ID 选择工作，不靠猜
2. **依赖方向无环**——两模块互相依赖 = 合并成一个模块
3. **能力图小而可审**——模块表 + 构建顺序，不是项目计划
4. **可裁剪**——一个能力可被砍掉/替换而不重写其他需求

**落地动作**：writing-plans 补 Phase 0 章节，多能力请求先出能力图再写计划。

## 授粉点 2：上下文工程五层分层（context-engineering）

**问题**：自有 headroom 做上下文压缩（省 token），但缺**分层组织**——哪些放 Rules、哪些放 Docs、哪些进 Memory，没有明确层级，上下文混乱。

**agent-skills 分层**（从持久到易失）：
| Level | 载体 | 内容 |
|---|---|---|
| 1 | Rules Files（AGENTS.md/CLAUDE.md） | 技术栈、命令、不可违反约束 |
| 2 | Docs | 设计文档、API 参考（按需读取） |
| 3 | Memory | 跨会话持久事实 |
| 4 | Models | 任务相关模型/工具 |
| 5 | Tokens | 当前对话的即时信息（最易失） |

**落地动作**：headroom 压缩时按层级保序——先砍 Level 5（对话噪声）、再压缩 Level 4/3，**Level 1 Rules 永不压缩**（违反即系统行为漂移）。

## 授粉点 3：doubt-driven-development（新概念）

**agent-skills 原创**：把"工程师不确定"显式编码成决策门——不知道的事写成 TODO 决策点，不让 agent 假装知道；在关键分叉处强制列出"我知道 X / 我不知道 Y / 我需要问 Z"。

**落地动作**：writing-plans 增加"未知清单"章节——计划里必须显式写"假设/未知/需确认"，不能只写"实现步骤"。

## 对照验证

- ✅ 自有 skills 已覆盖 TDD/代码评审/调试三块，不重复授粉
- ⚡ 三处增量授粉（能力图/上下文分层/未知清单）都是纯文档级，零代码改动，落地成本低
- 完整 25 目录清单见 fusion/agent-skills-src.tar.gz，需要时解压细读
