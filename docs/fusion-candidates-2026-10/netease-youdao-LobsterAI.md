# 融合候选：netease-youdao/LobsterAI

> **优先级 P2（参考级）** ｜ 采集：2026-10-08 GitHub API 实测 ｜ ✅ 无既有报告（已查重）

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `netease-youdao/LobsterAI` |
| ★ | **6088**（工单初勘 6087） |
| 许可 | **MIT** ✓ |
| 语言 / 体积 | TypeScript / 105 MB |
| 最近 push | **2026-10-08**（当天活跃） |
| 自述 | "Open-source, desktop-grade AI agent that gets real work done — data analysis, slides,
  docs, video & web research. **Built on OpenClaw**; runs tools on your…" |
| topics | `agent` / `ai-assistant` / `autonomous-agents` / `cross-platform` / `copilot` |

## 1. 架构一句话（**描述级**）

网易有道的**桌面级生产力 agent**：数据分析 / 幻灯片 / 文档 / 视频 / 网页研究，
**底层构建在 OpenClaw 之上**，工具在本地执行。

## 2. ⭐ 最大发现：它 built on OpenClaw

`Built on OpenClaw` —— 这意味着它**和我们走同一条执行层路**（我们的 `agentserver/openclaw/*`
三件套 4k+ 行也是围绕 OpenClaw）。所以它是**同技术栈的中文大厂参考**，
比异构项目（airi 的单体、cognee 的平台）**更容易横向对照**。

| 维度 | LobsterAI | 陆墨现状 |
|---|---|---|
| 执行层 | OpenClaw | `agentserver/openclaw/{openclaw_client,instance_manager,embedded_runtime}` |
| 形态 | 桌面级**生产力套件**（5 类产出物） | 能力总线 + 多壳（NEKO 桌宠 / Electron） |
| 多 agent | （工单点名：借其**多 agent 会话管理 UI 模式**） | `frontend` 的 Message/Mind 视图 + 会话管理 |
| 产出物 | 数据分析/PPT/文档/视频/研究 | 我们有 `agentserver` 旅行会话、材料线、论文线 |

**差距的本质**：它把 agent 做成**"交付产出物"的产品**，我们把 agent 做成**"能力总线"**。

## 3. 可借用的具体设计（非代码）

1. ⭐ **多 agent 会话管理的 UI 模式**（工单指定落点）：
   一个任务派给多个 agent 时，会话列表 / 进度 / 产出物预览怎么组织 ——
   可直接对照我们 `MessageView` / `MindView` 的信息架构。
2. **产出物（artifact）为中心的组织方式**：它按"最终交付什么"（PPT/表/文档）组织界面，
   我们目前按"用了哪个工具"组织 —— 这是个**产品视角的启发**。
3. **同栈实现差异**：既然都基于 OpenClaw，可对标它的 `instance_manager` 侧
   看**实例生命周期**有没有更简洁的做法（与我们 1518 行那份做横向比较）。
4. **中文桌面 agent 的交互惯例**（大厂产品化的措辞 / 授权提示 / 失败引导）。

## 4. 许可与边界

- **MIT** ✓。**只借设计**（本批统一口径）。
- ⚠️ 体积 105 MB，**不 clone**；需要细看时用 API 读指定路径。

## 5. 融合优先级与下一步

**P2（参考级）** —— 结构同栈（都基于 OpenClaw）使对照成本低，但**它不是能力来源而是产品形态参考**。
**下一步（若选中）**：开 SPEC 时优先做**两处横向对照**：
① 多 agent 会话 UI 的信息架构 vs 我们的 Message/Mind；
② OpenClaw 实例生命周期实现 vs 我们 `instance_manager`（看有没有可收敛的复杂度）。
