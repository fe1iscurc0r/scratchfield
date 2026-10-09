# 融合候选：NanmiCoder/cc-haha

> **优先级 P2（参考级）** ｜ 采集：2026-10-08 GitHub API 实测 ｜ ✅ 无既有报告（已查重）

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `NanmiCoder/cc-haha` |
| ★ | **14904**（工单初勘 14899） |
| 许可 | **MIT** ✓（README 徽章 + LICENSE 双确认） |
| 语言 / 体积 | TypeScript / 170 MB |
| 最近 push | 2026-10-05 |
| 自述 | "Local-first cross-platform desktop workspace for Claude Code / agents：
  multi-agent, **Git worktrees**, code diffs, **skill marketplace**, multi-model, Computer…" |
| topics | `coding-agent` / `claude-code` / `computer-use` / `anthropic` |

## 1. 架构一句话（**描述级**）

**本地优先的跨平台桌面工作区**，为 Claude Code 一类 agent 提供图形外壳：
多 agent、Git worktree 隔离、代码 diff、**技能市场**、多模型、computer use。

## 2. 与自家对应模块的差距 / 落点

工单落点是"对 **openclaw 桌面化线**的参考"。补充实测到的一层：

| 维度 | cc-haha | 陆墨现状 |
|---|---|---|
| 形态 | 桌面**工作区**（面向编码 agent） | NEKO 桌宠壳 + `frontend`（面向陪伴/科研） |
| 隔离 | ⭐ **Git worktrees** 做多 agent 隔离 | 我们用 `git worktree` 做**测试基线对照**（工具层），**不是产品特性** |
| 技能 | ⭐ **skill marketplace** | 我们有 `mcpserver` 工具面 + skill 加载器（`skill_manager`），**无市场** |
| 模型 | multi-model | `llm_router` + provider 切换（已有） |
| 截屏/操作 | computer use | `agentic_loop` 有 openclaw / browser 执行器 |

**差距的本质**：它把**编码 agent 的工程约束**（隔离、diff、技能安装）做成了产品；
我们的对应能力散在工具层（worktree 是脚本、技能是文件加载）。

## 3. 可借用的具体设计（非代码）

1. ⭐ **Git worktree 作为产品级隔离**：多 agent 并行时每个 agent 一个 worktree ——
   我们目前是"单工作区 + 大堆未提交改动"（记忆里明确记着这个痛点），
   这条**直接对应我们的真问题**，值得优先看它怎么处理 worktree 的创建/回收/合并。
2. ⭐ **skill marketplace 的安装与信任模型**：我们有 `skill_manager` + 市场端点
   （`extensions_parts/market.py`）—— 可对标它的**安装/更新/权限提示**流程。
3. **代码 diff 的呈现方式**：agent 改完代码后给用户看什么（hunk 级 / 文件级 / 影响面）。
4. **多模型切换的产品化**：与 `llm_router` 的差异（尤其失败回退的用户可见性）。

## 4. 许可与边界

- **MIT** ✓。**只借设计**（本批统一口径）。
- ⚠️ 体积 170 MB，**不 clone**。

## 5. 融合优先级与下一步

**P2（参考级）** —— 它的**隔离 / 市场 / diff**三件事正好命中我们的工程痛点，
但**不是同一产品形态**（编码工作区 vs 伴侣 + 总线）。
**下一步（若选中）**：优先做 **worktree 隔离** 的源码级复核
（这一条与我们"工作区常年脏"的真问题最直接相关）。
