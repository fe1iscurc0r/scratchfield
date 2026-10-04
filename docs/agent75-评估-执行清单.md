# agent-75 评估报告 + 执行清单（GH 活跃/HF Spaces/Trending 12 项）

> 智能体 75 · 勘察/评估 · 12 项（W74-01~12）
> 纪律：评估报告含定位 + 架构拆解 + 与本仓对照 + ≥3 借鉴点 + 许可裁定；同类合并 + 逐条验收。

## 逐项评估（表）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W74-01 | colibri（MoE 流式推理） | Apache-2.0 | 纯 C 零依赖，MoE 专家流式从磁盘加载 | ✅ 借鉴：端侧 MoE 流式加载降内存；与本仓边缘 LLM 同向 |
| W74-02 | scientific-agent-skills | MIT | 165 科研 skills + 100+ 数据库 | ✅ 借鉴：科研 skill 目录可补 skills/；材料/化学垂直 |
| W74-03 | anydoc（文档转 Markdown） | MIT | Word/PPT/Excel/PDF→干净 Markdown（Rust） | ✅ 借鉴：文档转换，对接 web_extract/知识库入库 |
| W74-04 | mempalace（记忆 benchmark） | MIT | 号称最强开源 AI 记忆 | ✅ 借鉴：记忆评测集对照 W62-03；不重复造轮子 |
| W74-05 | zvec（进程内向量库） | Apache-2.0 | 轻量极速进程内向量库（C++） | ✅ 借鉴：本地向量检索，对照 rag 检索引擎 |
| W74-06 | ESP32-Bit-Pirate/trail-mate/sdroxide | MIT/AGPL/GPL | 协议万用表 + 手持 LoRa 态势 + Rust SDR | ⚠️ 参考：AGPL/GPL 只参考设计；ESP32-Bit-Pirate 可借鉴 |
| W74-07 | HF-Radio（互联网电台） | HF Space | ACE-Step 社区电台 | ⚠️ 低价值，参考级 |
| W74-08 | open-materials-challenge + materials MCP | HF Space | 电池材料 leaderboard + Materials Project MCP | ✅ 借鉴：材料 MCP tool 目录，对接陆墨 |
| W74-09 | computer/jupyter/fish-agent 三件 | HF Space | computer-use / Jupyter / 语音 agent | ✅ 借鉴：三类 agent 应用范式，对照 NEKO |
| W74-10 | sherpa-onnx（离线语音） | C++ | 全链路 ASR/TTS/说话人，嵌入式可跑 | ✅ 借鉴：ESP32-S3 离线语音链路，对照 voice-MCP |
| W74-11 | ponytail/ECC/openhuman 三件 | MIT/MIT/GPL | 代码削减哲学 + harness 优化 + 本地记忆 | ✅ 借鉴：ponytail「代码量削减」哲学；openhuman GPL 只参考 |
| W74-12 | ktransformers/agentgateway/timesfm | Apache-2.0/Rust/Apache | 异构推理 + MCP/A2A 网关 + 时序基础模型 | ✅ 借鉴：MCP/A2A 双协议网关 + 时序模型，对接工具链 |

## 执行清单

- **完成**：12/12 逐项评估。
- **许可**：MIT/Apache 可借鉴；AGPL/GPL（W74-06 sdroxide、W74-11 openhuman）只参考设计。
- **高价值**：colibri（端侧 MoE）、sherpa-onnx（离线语音）、ktransformers（异构推理）三点最可落地。
