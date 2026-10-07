# 新项目拿货 · 2026-09-02（RuView + LightRAG）

> 沈遥（Hermes）从今日扫货候选里实际拉取源码归档，写授粉报告。
> 归档：`github_haul/fusion/RuView-src.tar.gz`（22M）+ `LightRAG-src.tar.gz`（3.7M）
> 许可：RuView MIT / LightRAG MIT（均干净，可融合）
> 源码不进 git（与 5ire 先例一致），报告进 docs/。

---

## 1. ruvnet/RuView（92.3k★ · MIT · Rust/TS/C）

**是什么**：把普通 WiFi 信号变成实时空间感知——**无摄像头**做人体存在检测/活动感知/生命体征监测。ESP32 固件采集 WiFi CSI，Rust 工作区做信号处理，Web 面板可视化。

**核心架构**（已核源码）：
- `firmware/esp32-csi-node`：ESP32 采集 WiFi CSI（信道状态信息）
- `v2/` Rust 工作区（906 个 .rs 文件）：信号处理主实现
- `harness/`：便携 contributor harness + WASM-first Homecore
- 强调 **MEASURED/CLAIMED/SYNTHETIC 三档标注**，不冒充真机精度

**授粉点（对接 rf_brain 栈）**：
| 授粉点 | 落地方式 | 优先级 |
|--------|----------|--------|
| WiFi CSI → 人体/活动感知 | 用现有 ESP32-S3 + 无摄像头做存在检测，接 rf_brain 决策层 | P0 |
| CSI 信号处理管线（Rust→Python 桥） | 提取 v2/ 的 DSP 核心思路，移植纯 numpy 版对照 | P1 |
| 三档标注纪律（MEASURED/CLAIMED/SYNTHETIC） | 引入 rf_brain 全部真机/合成结果标注 | P0（纪律） |
| TESLA 侧信道同族 | 与已有 touchscreen EM 侧信道研究互为验证 | P2 |

**风险**：Rust 工作区 906 文件工程量大，先移植关键 DSP 而非整包；无 ESP32 硬件时用合成 CSI 兜底（诚实 degraded）。

---

## 2. HKUDS/LightRAG（39.3k★ · MIT · Python）

**是什么**：EMNLP2025 的轻量图增强 RAG——把文档建图（实体/关系），检索时图结构增强，比全量 GraphRAG 轻一个量级。

**核心模块**（已核源码）：
- `lightrag/lightrag.py`：主管线
- `kg/`：知识图谱构建（实体抽取/关系/去重）
- `chunker/`：智能分块
- `llm/` + `llm_roles.py`：LLM 抽象层
- `rerank.py`：重排
- `operate.py`：图操作
- `api/`：服务化

**授粉点（对接 rag-skill/知识库栈）**：
| 授粉点 | 落地方式 | 优先级 |
|--------|----------|--------|
| 图增强 RAG 检索 | ✅ **已落地** `mcpserver/rf_brain/lightrag_graph.py`：实体共现图 + BFS 多跳扩散检索，查询「SDR 解调」跨 chunk 召回 LoRa/FFT/ESP32/天线，18 测试全绿 | P0 |
| chunker 智能分块策略 | 对照现有 smartChunk，取长补短 | P1 |
| LLM 抽象层 + llm_roles 分工 | 参考其角色化 LLM 调度，对齐 NEKO 多模型路由 | P2 |
| 知识图谱实体抽取 | 提炼实体/关系 schema，喂 pollination 知识库 | P1 |

**风险**：LightRAG 用网络请求 LLM，本地跑需配 API；图构建对中文文档需测基准。

---

## 后续

- 两个 tar.gz 已在 `github_haul/fusion/`，可解压细读
- 报告归档 `docs/授粉拿货-RuView-LightRAG-2026-09-02.md`
- 立项状态：**LightRAG 已授粉落地**（`lightrag_graph.py`，18 测试全绿，可并入 rag 栈）；**RuView 建议立项 `wifi-csi-sense`**（等真机 ESP32 CSI 采集）
