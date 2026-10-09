# EDA 插件生态盘点 2026-10（工单217 任务二 + 任务三）

> 日期：2026-10-08 ｜ 任务二：knowledge-base 对接卡（`eda-knowledge-base-integration` 段）；
> 任务三：apirun 查证 + 官方 AI 插件生态表（`eda-plugin-ecosystem-2026-10.md` 本体）。
> 素材：本仓文档实读 + 2026-10-08 web 实查（prodocs.lceda.cn / 扩展广场 jlc-ext.com 相关报道）。

---

## 任务二 · eext-knowledge-base 对接云服知识库（EDA←scratchpad 方向）

### 配置面盘点（体检报告 + 插件勘察口径）

eext-knowledge-base（官方插件）支持的配置面：**模型源**（OpenAI 兼容端点 + embedding 接口，
官方勘察确认支持 ollama 等本地源）/ **知识文件**（编辑器侧的文档集）/ **上下文注入点**
（IFrame 对话面板）。即：它是一个"**自带 RAG 的编辑器内问答**"，模型端可指到任意
OpenAI 兼容 `/v1/chat/completions`。

### 三选一结论：✅ **A（暴露 OpenAI 兼容端点），但暂缓实施**

**评估**：

| 路 | 内容 | 判定 |
|---|---|---|
| **A** | apiserver 把知识检索（lightrag_graph / RAG vault）包成 OpenAI 兼容 `/v1/chat/completions`，插件直连 | ✅ **架构正确**：零 fork、插件配置一次即可；且该端点**不止服务 EDA**——陆墨一切"只会说 OpenAI 协议"的客户端（含各类第三方工具）都能复用。工作量：一个带检索增强的 chat 端点（检索已有，包装层 ~100 行级） |
| B | fork knowledge-base 加自定义源 | ❌ 维护负担（跟官方版本漂移），且 A 已覆盖其需求 |
| 暂不对接 | — | 🟡 可接受（无急迫消费方），但 A 的复用面让它值得排进近期 |

**为什么"暂缓"**：A 的前置是**知识检索面稳定**（lightrag_graph / RAG vault 的检索质量先立住），
且 OpenAI 兼容端点一旦暴露就是**公共 API 契约**（鉴权/限流/版本都要跟上）——不宜在审计单里顺手做。

**✅ 2026-10-09 已落地**：`POST /v1/knowledge/chat/completions`（`apiserver/routes/knowledge_openai.py`，
工单217-A 后续执行）。检索复用 lumo_proxy 的多路召回（grag+向量+语义+化学四路），命中才注入
system（不污染）；检索失败降级纯转发（铁律5）；上游 401/402/429 人话分类（对齐工单221 口径）；
流式/非流式双支持；Bearer token 鉴权（LUMO_PROXY_TOKEN）。测试 6 passed。
**knowledge-base 插件接入配置**：模型源地址填 `http://<apiserver>:8000`，API key 填 LUMO_PROXY_TOKEN，
模型名任意（转发时替换为 config 真实模型）。

**与任务一的衔接**：`/api/eda/ingest`（本单落地）是 **EDA→scratchpad** 方向；A 是 **scratchpad→EDA**
方向。两条合起来才是"双向适配"——A 落地后，EDA 内问知识库，答的正是 parasite-export 推上来的
自家设计文档。

---

## 任务三 · apirun 查证 + 官方 AI 插件生态表

### ⭐ apirun 查证结论：**查无此插件；用户所指几乎确定是官方 `eext-run-api-gateway`（Run API Gateway）**

web 实查（2026-10-08，嘉立创官方文档 + 扩展广场生态报道）：

- 扩展市场/官方文档中**不存在**名为 "APIRun / apirun / API-Run" 的插件；
- 但官方有一个**功能完全对口**的插件：**`eext-run-api-gateway`（Run API Gateway，开源
  github.com/easyeda/eext-run-api-gateway）**——WebSocket API 网关桥接扩展，使 AI 编程工具
  （MCP/Agent）能调用 **LCEDA 99% 的功能**（eda.* 全 API），配官方 `easyeda-api-skill`
  （API 定义文件，120+ 类 62 枚举 70 接口）。端口 49620-49629 自动发现，Node.js 18+。

### run-api-gateway 半页调研卡

| 项 | 内容 |
|---|---|
| 是什么 | 官方 WebSocket 桥：外部 AI 工具发 JS 代码 → 扩展在 EDA 运行时执行（`new AsyncFunction('eda', code)`） |
| 许可 | 开源（官方仓库）；具体 SPDX 以仓库 LICENSE 为准（同 zenoh 教训：API 标签可能失真） |
| 与自家管线关系 | **与我们 easyeda-agent 线（daemon 60832）是同型竞品**：run-api-gateway 走"任意 JS 代码执行"，我们走 typed action（更安全、可审计）。**判定：并存**——run-api-gateway 适合"探索期任意操作"，typed action 适合"固化后的可靠操作"；生态里已有第三方 MCP（JLC_EDA-MCP 等）基于 run-api-gateway 构建 |
| 双向适配价值 | **中**：它是 AI→EDA 方向的官方标准答案；我们的 skills（autodraw/clearance-fix）已走自家 daemon，不依赖它 |

### 官方 AI 系插件生态表（实查 + 已勘察合并）

| 插件 | 功能 | 许可 | 双向适配价值 |
|---|---|---|---|
| **eext-run-api-gateway** | WebSocket 桥，AI 调 99% EDA 功能（见上卡） | 开源 | **中** |
| easyeda-api-skill | 官方 API 定义文件（供 AI 理解 LCEDA API） | 开源 | **高**（可直接喂自家 agent 的工具目录） |
| eext-knowledge-base | 编辑器内 RAG 问答（OpenAI 兼容源） | 官方 | **高**（任务二 A 方向） |
| eext-datasheet-helper | 数据手册助手（PDF→参数查询） | 官方 | 中（与材料线数据手册流互补） |
| eext-ai-device-standardization | AI 器件标准化 | 官方 | 低（暂无场景） |
| eext-filter-designer | 滤波器设计 | 官方 | 低 |
| eext-kipida-integration | KiCad 互操作 | 官方 | 中（若导入 KiCad 生态资产） |
| pro-api-sdk | 官方扩展开发 SDK（TypeScript） | 官方 | **高**（自家四件套的地基） |
| （训练营生态）jlc-ext.com 扩展广场 | AI 辅助开发插件持续上架（官方训练营 2026.7-8） | 各异 | 关注 |

### 自家资产 × 生态对位（总账）

| 方向 | 自家 | 生态位 |
|---|---|---|
| EDA→scratchpad | ✅ parasite-export → **`/api/eda/ingest`（本单落地）** | 无官方对应（自家独有） |
| scratchpad→EDA | skills（autodraw/clearance-fix，typed action）+ easyeda-agent daemon | 对位 run-api-gateway（并存策略） |
| EDA 内问答 | project-describe（DeepSeek 直连） | 对位 knowledge-base（A 方向对接） |

---

## 边界

- 任务二结论 A 的实施**不在本单**（审计级）；知识检索面质量先行；
- run-api-gateway 许可 SPDX 未逐字核（列"以仓库 LICENSE 为准"——zenoh 教训：先核再引）；
- 扩展广场条目为 2026-10-08 快照，生态在快速演化（训练营进行中）。
