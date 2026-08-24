# 授粉报告 Batch-4：冷门填坑 + 热门跟风（9 项）

> 日期 2026-08-22 深夜 | 模式：API 直读 | 策略：冷门挖真金，热门跟风

## 一、冷门填坑（低星高价值）

### 1. cozodb/cozo（4092★, MPL-2.0）— 关系+图+向量三合一数据库 ⭐⭐⭐
- **定位**：事务性、关系-图-向量混合数据库（Datalog 查询语言），嵌入/分布式双模式
- **为什么是坑**：NEKO 记忆层现在是 SQLite+FTS+向量**三套分家**；cozo 一个库全装——关系记忆、知识图谱、向量检索统一查询
- **授粉建议**：记忆层 MaaS 的候选存储（替换三套分家）；MPL-2.0 注意（不是 AGPL 兼容，需独立进程桥接）
- **落点**：NEKO 记忆层 Phase6（远期）

### 2. DSheirer/sdrtrunk（2164★, GPL-3.0）— Java 多协议解码器 ⭐⭐⭐
- **定位**：跨平台多协议数字信号解码（P25/P25P1/P25P2/DMR/AMBE 等），sdrtrunk 是 rf_brain 工单里的"JVM 子进程桥"方案
- **为什么是坑**：rf_brain 要的多协议解码，sdrtrunk 全有且成熟（Gradle 构建、nightly CI、真机验证）
- **授粉建议**：HW-04 的 sdrtrunk 桥接（JVM 子进程）——比自写解码器省 10 倍工
- **落点**：rf_brain Phase6 直接桥接

### 3. meshtastic/meshtastic（2119★, GPL-3.0）— LoRa mesh 全栈文档 ⭐⭐⭐
- **定位**：Meshtastic 项目官网+文档（LoRa mesh 通信的行业标准实现）
- **为什么是坑**：HW-01 MeshRadio 的对标——Meshtastic 有完整协议/固件/App/社区，我们自研 mesh 应该先吃透它的协议设计
- **授粉建议**：读 Meshtastic 协议文档 → 对照 MeshRadio 设计（复用路由/加密思路）
- **落点**：HW-01 参考（文档级）

### 4. sgoudelis/ground-station（4710★, GPL-3.0）— 浏览器卫星地面站 ⭐⭐
- **定位**：浏览器端卫星地面站套件（接收/解码/可视化）
- **授粉建议**：与 rf_brain 的"频谱可视化"可互通；GPL 注意（可独立部署参考）
- **落点**：rf_brain 可视化参考

### 5. chdb-io/chdb（2872★, Apache-2.0）— 进程内 OLAP 引擎 ⭐⭐
- **定位**：ClickHouse 的嵌入式版（Python pip 直接 import，SQL 查询 CSV/Parquet）
- **授粉建议**：duckdb 的备选/互补（chDB 更偏 OLAP 聚合，duckdb 更偏分析）；Lumo 工作台可双引擎
- **落点**：Lumo duckdb 工作台互补（低优先）

## 二、热门跟风（高星直接可用）

### 6. mattpocock/skills（229k★, MIT）— 真实工程师 skills ⭐⭐⭐
- **定位**：TypeScript 大佬 Matt Pocock 的实战 skills 集
- **授粉建议**：与 superpowers/agent-skills 对照——挑缺失的工程技能补 scratchpad skills/（先看目录再定）
- **落点**：skills/ 增强（低优先，已有两个方法论参考）

### 7. garrytan/gstack（129k★, MIT）— Garry Tan 的 Claude Code 配置 ⭐⭐⭐
- **定位**：Garry Tan（Y Combinator CEO）的完整 Claude Code 设置：23 个 Opus 代理 + 工作流
- **为什么是热点**：Karpathy 访谈引爆（"一个人像 20 人团队一样发货"）
- **授粉建议**：读它的 agent 编排模式 → 对照我们的 delegate_task 用法（多代理并行+审查链）
- **落点**：Hermes agent 编排参考

### 8. Egonex-AI/Understand-Anything（80k★, MIT）— 代码库知识图谱 ⭐⭐
- **定位**：代码库/知识库→交互式知识图谱（Claude Code/Codex/Cursor 通用）
- **与 graphify 对照**：竞品！我们已装 graphify（原生 Hermes 支持）；Understand-Anything 更偏"交互式问答"
- **授粉建议**：不重复装；读它的查询交互模式，graphify 缺"ask questions"交互可借鉴
- **落点**：graphify 增强参考

### 9. headroomlabs-ai/headroom（67k★, Apache-2.0）— 上下文压缩层 ⭐⭐
- **定位**："The context compression layer for AI agents"——压缩工具输出/日志/文件/RAG 块
- **与我们的关系**：**已有等效**！scratchpad context_compressor.py + headroom skill 已存在（记忆里有 headroom-context-compression skill）
- **授粉建议**：对照 headroom 实现 → 补 context_compressor 的缺口（如结构化日志压缩）
- **落点**：context_compressor 增强（低优先）

## 三、行动优先级

| 优先级 | 项目 | 动作 |
|--------|------|------|
| P0 | sdrtrunk | HW-04 桥接（省 10 倍工） |
| P0 | meshtastic 文档 | HW-01 协议参考 |
| P1 | cozo | NEKO 记忆层 MaaS 存储候选 |
| P1 | gstack | agent 编排模式参考 |
| P2 | 其余 | 按需 |

## 四、结论

- **冷门挖到 3 个真金**：cozo（记忆存储升级）、sdrtrunk（射频解码现成）、meshtastic（mesh 协议参考）
- **热门跟风 2 个值得**：gstack（多代理编排）、mattpocock/skills（工程技能）
- headroom / Understand-Anything 是**竞品已有等效**——不重复，只补缺口
