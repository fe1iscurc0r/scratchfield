# 工单 217 · 嘉立创 EDA 插件双向适配——AI 画板生态打通（parasite-export 接收端 + knowledge-base 对接 + apirun 盘点）

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户要求对嘉立创 EDA 的 AI 插件生态做**双向适配**。沈遥初勘实况：已有资产比想象厚——自研扩展四件套（parasite-export/project-describe/export-design-report fork/iBOM fork）+ easyeda-agent 对照评估（上游 MIT 可借）+ skills 两件（schematic-autodraw/clearance-fix）。但**双向适配有一处断链**：parasite-export 的推送端（POST 8765/ingest）已写好，**云服接收端从未建**。本单补断链+盘点。

## 现有资产盘点（初勘实证）

| 资产 | 方向 | 状态 |
|---|---|---|
| parasite-export（自研 .eext） | EDA→scratchpad（推送文档源码） | ✅ 扩展侧完成，默认推 `127.0.0.1:8765/ingest`；**接收端不存在** |
| project-describe（自研 .eext） | EDA→任意 LLM（生成项目描述） | ✅ DeepSeek 直连，key 存本机 |
| eext-knowledge-base（官方插件） | EDA←本地模型（RAG 问答） | 🔍 已勘察（支持 ollama 源），**未接云服知识库** |
| eext-kipida-integration（官方） | EDA↔KiCad 互操作 | 🔍 仅列入审计清单，未盘 |
| easyeda-agent（上游 338★ MIT） | EDA←AI 全流程（typed action + daemon 60832） | 📄 对照评估完成，判定"借鉴不迁入" |
| skills：schematic-autodraw / clearance-fix | AI→EDA（typed action 画图/修间距） | ✅ skill 落地 |
| apirun | 未知 | ❓ 初勘未命中，任务三专查 |

## 任务一（P0）：parasite-export 接收端落地——双向适配的第一条实链

EDA→云服方向现在只有"发送方"没有"接收方"。补齐：

1. 在 apiserver 新增路由 `POST /api/eda/ingest`（对齐扩展默认可配 URL）：
   - 接收 `{meta: {project, page, doc_type}, source: ".esch/.epcb 文档 JSON 源码"}` 信封
   - 校验 + 落盘 `<user_data>/eda_ingest/<ts>_<project>.json`，幂等（同内容 hash 跳过）
   - 发布 EventBus 事件 `lumo.eda.document_ingested`（复用 v2 总线 topics 规范），消费者后续再挂（寄生参数提取/RAG 入库都从这条事件分流）
2. 鉴权：静态 token（环境变量 `EDA_INGEST_TOKEN`，扩展配置里同 token）——不裸奔
3. 端到端测试：curl 模拟扩展推送 → 落盘验证 → 事件可查（`/debug/dump/bus/events`）
4. 更新 `docs/easyeda-custom-extensions.md`：parasite-export 的管线地址从 127.0.0.1 改云服地址的配置说明

## 任务二（P1）：knowledge-base 插件对接云服知识库（EDA←scratchpad 方向）

体检报告已认定：eext-knowledge-base 支持 ollama 等 OpenAI 兼容源。反向链（EDA 内查 scratchpad 知识库）：

1. 盘点该插件支持的配置面（模型源/embedding 接口/上下文注入点），产出对接卡 `docs/eda-knowledge-base-integration.md`
2. 评估两条路：
   - A：把 apiserver 的知识检索（lightrag_graph / 现有 RAG）暴露成 OpenAI 兼容 `/v1/chat/completions` 端点，插件直连
   - B：改用自家 project-describe 同款模式，fork knowledge-base 加自定义源
3. 给三选一结论：A / B / 暂不对接（理由），**只出结论+设计，不 fork 官方插件**（同 ROS 线"接口先行"定调）

## 任务三（P1）：apirun + 官方插件生态完整盘点

用户点名 "apirun 或其他插件"，初勘仓内零命中——需要外部查证：

1. web_search + 嘉立创扩展市场实测：确认 "APIRun"（或近似名 apirun/API-Run/接口调试类插件）是什么、是否存在、许可、干什么
   - 若存在且开放：出半页调研卡（功能/许可/与自家管线关系）
   - 若查无此插件：在报告里明确写"查无"，并列出扩展市场内**实际存在**的 AI/API 类插件清单作为替代面
2. 官方 AI 系插件逐个三行列表（eext-ai-device-standardization / eext-datasheet-helper / eext-filter-designer 等已勘察过的 + 新发现的）：功能 / 许可 / 双向适配价值（高/中/低/无）
3. 全部落 `docs/eda-plugin-ecosystem-2026-10.md`

## 验收
- [ ] 任务一：`/api/eda/ingest` 落地，curl 端到端测试通过（推送→落盘→事件可见），token 鉴权生效；easyeda-custom-extensions.md 同步更新
- [ ] 任务二：knowledge-base 对接卡含配置面盘点 + A/B/暂不三选一结论 + 设计（不 fork）
- [ ] 任务三：apirun 查证结论明确（存在→调研卡 / 查无→替代清单）；官方插件生态表齐
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
