# 融合候选：u14app/neo-chat

> **优先级 P3（参考级，产品形态最远）** ｜ 采集：2026-10-08 GitHub API + README 实读
> 承接：工单 209 任务三调研卡目录

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `u14app/neo-chat` |
| ★ | **1866**（工单初勘 1865） |
| 许可 | **MIT** ✓ |
| 语言 / 体积 | TypeScript / 10.9 MB |
| 最近 push | 2026-10-01 |
| 定位 | "A local-first AI chat workspace for models, agents, skills, plugins, search, RAG, voice, memory, and artifacts" |

## 1. 架构一句话

**local-first 聊天工作区**（自托管 Web 应用）：模型/agent/技能/插件/搜索/RAG/语音/记忆/工件
集成在一个工作台里；数据本地优先（浏览器存储起步，ZIP 备份，可选 WebDAV 端到端加密同步）。

## 2. 记忆数据格式

README 层面可见的：memory 是工作区的一个**功能槽位**（与 knowledge-base retrieval、
file attachments 并列），**没有独立的记忆格式约定**——记忆依附于工作区数据
（浏览器存储/ZIP 备份/加密同步）。⚠️ 与前两家（定义了明确 md 格式）不同，
**它不是记忆基础设施，是消费记忆的应用**。

## 3. 与 memory_maas + SPEC-05 的差距 / 可借用设计

对本仓记忆线的直接价值有限（形态不同：Web 工作台 vs 后端总线）。可借的点偏产品工程：

1. **local-first 数据分档**：浏览器本地 → ZIP 备份/恢复 → 可选 E2E 加密同步（WebDAV）——
   三档渐进的隐私姿态对陆墨"用户拥有数据"叙事有参考；
2. **备份排除凭证**（"Backups exclude credentials and external service data"）——
   备份边界的严谨定义；
3. **集成面的组织**：models/agents/skills/plugins 一个工作台——对照我们的
   前端（Message/Mind/Skill 视图）的导航信息架构。

## 4. 许可与边界

**MIT** ✓。README 实读；记忆实现细节未读源码（价值低，不值得深入）。
**不出融合 SPEC 的候选**——留档为"同类 local-first 产品扫描"记录。

---

# 附：Tencent/TencentDB-Agent-Memory —— 只看不融（工单点名注明，不出卡）

| 项 | 实测 |
|---|---|
| ★ | **27810**（全批最高） |
| 许可 | **NOASSERTION** ⚠️（无许可声明） |
| 定位 | "team-level memory hub：对话/文档/代码 → 四类可复用记忆资产" |
| 生态 | topics 含 `openclaw-plugin`（与我们 openclaw 线同生态） |

**不出卡原因（工单红线）**：NOASSERTION = 许可未声明 → 按仓内许可红线**只看不融、不引码**。
星数再高也不能进融合流程——许可缺失的代码引用是法律风险，不是工程问题。
若未来上游补充许可证，可重开调研。
