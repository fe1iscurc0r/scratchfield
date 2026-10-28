# GitHub 扫货日报 · 2026-10-12

> 范围：MCP / Live2D 桌宠 / 知识图谱·RAG / 材料科研 / 桌面 AI 助手 / 语音 六维度
> 许可口径：2026-09-14（仅 MIT / BSD / Apache-2.0 / ISC；copyleft 全系排除；PolyForm-NC 标 NC 仅参考）
> 过滤：archived / 无 LICENSE / BSL（source-available）/ 本地已引用（已融合/已登记/已授粉）
> 模式：Discovery-only（**不执行** clone / pull / tar）
> 本日相对 2026-10-11 增量：**新发现 5 项**（含 1 项 10-11 已评估不在候选清单内）+ **排除/已授粉复核 6 项**

---

## 一、本日新发现候选清单（15 项以内）

### MCP 工具层（4 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 33525 | MIT | github/github-mcp-server ⚠️已引用 | MCP · 官方 | GitHub 官方 MCP（API/issue/PR/repo 操作全套）。价值：scratchpad 已有 gh tool 适配，但官方版协议更标准、权限更细；替代/对照自家维护版能省适配成本 |
| 28044 | MIT | PrefectHQ/fastmcp ⚠️已引用 | MCP · 框架 | Pythonic MCP server/client 框架（官方推荐）。价值：scratchpad 当前手写 MCP server 类，若改用 fastmcp 装饰器风格可减一半样板（**预检**：纯库，集成路径短，可作 `mcpserver/` 模板升级） |
| 13 | MIT | mufeng05/ida-auto-mcp | MCP · 逆向 | 无头 IDA Pro MCP（idalib 多 binary 自动分析）。价值：与 ghidra-mcp-接入SPEC 平行，IDA Pro 路径补全（**预检**：⚠️ 无 LICENSE 文件，README 未声明许可，**暂缓**） |
| 13 | MIT | karmine05/agentic-detector | MCP · 安全监测 | osquery 扩展：统一表 `agentic_software` 探测 MCP server / AI agent CLI / 网络 socket。价值：蜜罐反制层「找自家暴露面」配套——发现本机跑了哪些 MCP/agent 进程，给 Hermes 三层部署做资产盘点 |

### Live2D 桌宠 / AI 伴侣（2 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 13 | MIT | moonrailgun/vtubeleaf | 桌宠 · 会议头像 | 本地 Live2D 会议头像（VTuberLeaf），本地推理 + 浏览器开会场景。价值：**轻量 Live2D 驱动+面部追踪**最小实现，可作为 NEKO 「Webcam 追踪 → Live2D 表情」参考 |
| 811 | MIT | AkagawaTsurunaki/ZerolanLiveRobot | 桌宠 · 全栈 | AI VTuber 全栈：LLM + ASR + TTS + OCR + CV + Live2D 整合。价值：与 NEKO 同位素，**关注其多模态集成架构**（OCR 桥接屏幕、CV 桥接摄像头，TTS 与 ASR 闭环） |

### 知识图谱 / RAG / 代码理解（3 项，全部「本地已授粉」，仅作状态确认）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 状态 |
|---|---|---|---|---|
| 125566 | Apache-2.0 | Graphify-Labs/graphify | 融合参考 · 代码KG | **本地已融合**（mcpserver/adapters/graphify 已落地，schema 对齐上游）— 持续同步上游新特性 |
| 31652 | Apache-2.0 | getzep/graphiti | 融合参考 · 时序KG | **本地已授粉**（docs/workorders/prompts/TRAE_WORKORDER_PROMPT_AGENT_{72,73} 引用，mod/references/graphiti 收档）— 已开工单，未拉包 |
| 99744 | Apache-2.0 | thedotmack/claude-mem | 融合参考 · 持久记忆 | **本地已授粉**（claude-mem-授粉报告.md 完整勘察报告）— 走授粉勘察通道 |

### 材料科研 / 知识库（2 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 状态 |
|---|---|---|---|---|
| 100 | BSD-3 | chiang-yuan/llamp | 学术材料 · RAG | **本地已授粉**（10-04 日报已落 BSD-3 确认 + P0 标记，EMNLP'25 材料多模态 RAG）— 持续复推陆墨科研线 |
| 18 | MIT | blokhin/materials-informatics-tutorial | 学术材料 · 教程 | 快速入门材料信息学教程（短课程模板）。价值：可作为 lumo `research/tutorials/` 参考骨架，但量级小、价值一般 |

### 桌面 AI 助手 / 知识智能体（1 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 158 | Apache-2.0 | Alex8791-cyber/cognithor | 融合参考 · 本地Agent OS | 本地优先 Agent OS：19 LLM providers + 18 channels + 145 MCP tools + 6-tier memory + Agent Packs 市场。价值：**与 hermes-three-layer-deploy 同位素**，对照其「6 层记忆」设计能否启发 scratchpad 现有上下文压缩层与 memory-mcp 适配器的升级路径（**预检**：158⭐ + 2026-10-05 仍活跃，体量适中） |

### 语音 / 端侧 AI（1 项）

| ⭐ | 许可 | 项目 | 分类 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 19 | MIT | teamtee/LLM-ASR-Error-Correction（2026-06 最后 push，活性低） | Skill · ASR校正 | LLM 端到端 ASR 错误校正框架。价值：**低星但功能细颗粒**——可与 K2-FSA sherpa-onnx / FunASR 串联，给 Open-LLM-VTuber ASR 输出做后处理纠错（注意：最后 push 2026-06-05，**4 个月未维护，先评估活性再开工单**） |

### 🆕 关联度更高的旧发现复核（10-11 日报内未列但与 lumo 高度相关）

| ⭐ | 许可 | 项目 | 状态 | 备注 |
|---|---|---|---|---|
| 119 | MIT | inni918/warashi | **已授粉/已同步** | warashi-上游同步评估-2026-09-04 已落地长期记忆同步结论；spdx NOASSERTION 但 LICENSE 文件明文 MIT（**API 误报，已二次核实**） |
| 1381 | NONE | elevenyellow/handcrafted-persona-engine | **已深度评估** | NONE 无 LICENSE 但 handcrafted-RVC选型评估-2026-09-10 + TTS引擎蒸馏报告已完成；按「学习包只读设计」处理 |

---

## 二、本轮明确排除（备查）

| 项目 | 原因 |
|---|---|
| `memgraph/memgraph` | **BSL 1.1**（Business Source License，source-available 商业许可）— copyleft 全系排除扩展至 source-available 类，按 2026-09-14 口径**排除**。spdx 返回 NOASSERTION 必须读 LICENSE 原文（实测首行） |
| `rullerzhou-afk/clawd-on-desk` | **AGPL-3.0**（copyleft）— 已在 09-08 / 10-03 评估过，仅参考设计 |
| `SlimeBoyOwO/LingChat` | **AGPL-3.0**（copyleft）— 排除 |
| `Zao-chen/ZcChat` | **GPL-3.0**（copyleft）— 排除 |
| `Aftnos/AITTS` | **GPL-3.0** — 排除 |
| `DasterProkio/awesome-ai-companion` | **CC-BY-4.0**（不是软件许可），且是 awesome-list 非代码项目 — 不纳入 |
| `itallstartedwithaidea/advertising-hub` | MIT 但定位是数字营销（广告 14 平台 + 25 个 AI agent），**与 scratchpad 定位零关联** — 排除（仅说明已核验） |
| `mufeng05/ida-auto-mcp` | 无 LICENSE 文件（**暂缓**），与已有 ghidra-mcp-接入SPEC-2026-09-25 平行路径，建议先统一走 ghidra 路 |

---

## 三、Top 3 推荐

### 🥇 Alex8791-cyber/cognithor（158⭐ Apache-2.0 · 融合参考 · 本地 Agent OS）

**为什么**：**与 hermes-three-layer-deploy 直接同位素**——「19 providers + 18 channels + 145 MCP tools + 6 层记忆 + Agent Packs 市场」的「Local-first Agent OS」定位，正是 scratchpad 想做的下一阶段形态。Apache-2.0 + 仍活跃（最近 push 2026-09-25）+ 中等体量（不至于大到难读）。可重点勘察其「6 层记忆」设计（工作记忆/情节记忆/语义记忆/程序记忆/情感记忆/元记忆）能否启发 scratchpad 当前 `apiserver/context_compressor` + `mcpserver/memory_*` 的分层升级，并对比其 MCP 工具市场（MCP Packs）与 scratchpad 现有 skill/mcp 注册机制。落点：`docs/pollination/reports/cognithor-授粉报告.md` 写一份勘察报告即可，不必整包吞并。

### 🥈 AkagawaTsurunaki/ZerolanLiveRobot（811⭐ MIT · 桌宠 · 全栈 VTuber）

**为什么**：**与 NEKO 形态最完整的同位素**——LLM + ASR + TTS + OCR + CV + Live2D 整合，811 星说明社区验证过。MIT + Python（可读） + 活跃维护（最近 2026-10-11）。重点提取：（1）OCR 桥接屏幕阅读场景（NEKO 也可以加屏幕 OCR 转 LLM 上下文）；（2）CV 桥接摄像头/视频流（人物 + 手势）；（3）TTS/ASR 闭环调度。价值高于 10-11 日报里 `JianguSheng/yuns-desktop-pet`（架构吻合度高，但仅 141⭐ 体量小、稳定性未知），ZerolanLiveRobot 走"已社区验证过的全栈参考"路径更稳。落点：与已授粉的 warashi + airi + moeru-ai/airi 组成「桌宠四件套」交叉对比。

### 🥉 karmine05/agentic-detector（13⭐ MIT · MCP · 安全监测）

**为什么**：**蜜罐反制层的关键缺口补全**——「本机跑了哪些 MCP server / AI agent CLI / 进程 / 网络 socket」盘点，是 hermes-three-layer-deploy 三大层（决策/执行/蜜罐）里"自反馈层"的事实基础。低星（13⭐）但垂直赛道细，**典型「未受 AI 红利」冷门优质**。osquery 跨平台扩展 + 单表建模 + Fleet-deployable，落点：直接做 MCP adapter 接入 Lumo Bus（`mcpserver/agentic-detector/`），与 N.E.K.O. 蜜罐反制层串成"对外诱捕 + 对内盘点"。MIT + 仍活跃（2026-09-08）= 立即可开工单。

---

## 四、状态变化备注（相对 10-11 日报）

**新增候选**（不在昨日清单）：zerolanLiveRobot(811)、vtubeleaf(13)、cognithor(158)、agentic-detector(13)、github-mcp-server(33525)、fastmcp(28044)、teamtee/LLM-ASR-Error-Correction(19)、blokhin/tutorial(18)。其中只有 cognithor + zerolanLiveRobot + agentic-detector 值得立即勘察；其余 5 项多为常识级或量级偏小。

**确认已授粉**（已在本地文档）：Graphify-Labs/graphiti、getzep/graphiti、thedotmack/claude-mem、chiang-yuan/llamp、inni918/warashi、elevenyellow/handcrafted-persona-engine — 持续跟踪上游同步即可，本轮不重复推荐。

**确认排除**（持卡）：clawd-on-desk(AGPL)、LingChat(AGPL)、ZcChat(GPL)、AITTS(GPL)、memgraph(BSL)、mufeng05/ida-auto-mcp(无LICENSE)。

---

## 守卫结论（待补）

```
FAIL=?  WARN=?  PASS=?
```

*报告落盘：/tmp/sweep_report.md*
