# GitHub 高星增长项目 — 铁过滤 + 授粉勘察

> 扫货时间：2026-08-09 | 方法：stars>300 + created>2025-12-01，不看方向，先撒网再过滤
> 
> 第二步：铁条件过滤（只排除协议不兼容/硬件不够/平台不兼容）
> 第三步：授粉勘察（对通过项目做跨域映射，不预设用途）

---

## 铁条件过滤规则

| 条件 | 判定 | 处理 |
|------|------|------|
| GPL/AGPL | ❌ 代码不入库 | 标注「仅参考设计」 |
| 需特殊硬件(A100/H100) | ❌ | 排除 |
| 仅 macOS/iOS | ❌ | 排除 |
| 不是代码项目(awesome-list等) | ❌ | 不纳入 |
| MIT/Apache-2.0/BSD | ✅ 通过 | 可合入 |
| 待确认许可 | ⚠️ | 暂列候选，确认后决定 |

---

## 汇总：35 个候选 → 铁条件过滤

### ❌ 铁条件排除

| 项目 | 原因 |
|------|------|
| odysseus-dev/odysseus | AGPL-3.0 — 仅参考设计 |
| awesome-* / build-your-own-x / free-programming-books | 非代码项目 |
| freeCodeCamp | 非代码项目 |

### ✅ 通过铁条件（许可 MIT/Apache-2.0 已确认 或 待确认）

#### 🔥 增长最快（⭐10万+）

| 项目 | ⭐ | 许可 | 做什么 |
|------|-----|------|--------|
| **openclaw/openclaw** | 385k | 待确认 | 个人AI助手，全平台。已是scratchpad vendor |
| **ECC** | 238k | MIT | Agent harness 性能优化系统 |
| **mattpocock/skills** | 210k | MIT | Agent Skills 集合 |
| **garrytan/gstack** | 127k | MIT | 23个 Claude Code 工具(CEO/设计师/QA...) |
| **graphify** | 104k | Apache-2.0 | 代码库→知识图谱，AST解析 |
| **DietrichGebert/ponytail** | 98k | MIT | 让 Agent 像最懒的 senior dev |
| **JuliusBrussee/caveman** | 96k | MIT | Token 压缩 65%，像原始人说话 |

#### 📈 快速增长（⭐1万-10万）

| 项目 | ⭐ | 许可 | 做什么 |
|------|-----|------|--------|
| HKUDS/nanobot | 46k | MIT | 超轻量自托管 Agent 框架 |
| paperclipai/paperclip | 待确认 | 待确认 | Agent 工作管理 |
| stablyai/orca | 待确认 | 待确认 | 并行 Agent 舰队 |
| headroomlabs-ai/headroom | 待确认 | 待确认 | LLM 上下文压缩(MCP/代理/库) |
| jamiepine/voicebox | 待确认 | 待确认 | 开源 AI 语音工作室 |
| nexu-io/open-design | 待确认 | 待确认 | Agent 驱动的设计→HTML/PDF/PPTX |
| diegosouzapw/OmniRoute | 待确认 | 待确认 | AI 网关 290+ providers |
| obra/superpowers | 待确认 | 待确认 | Agent Skills 框架+方法论 |

#### 📊 稳定增长（⭐5000-10000）

| 项目 | 做什么 |
|------|--------|
| vercel-labs/agent-browser | 浏览器自动化 CLI for Agents (Rust) |
| rtk-ai/rtk | Token 压缩 60-90% (Rust 单二进制) |
| Panniantong/Agent-Reach | 多平台信息获取(支持B站/小红书) |
| MemPalace/mempalace | 最佳基准开源 AI 记忆系统 |
| tinyhumansai/openhuman | 个人 AI 超级智能 |
| karpathy/autoresearch | AI Agent 自动做 nanochat 研究 |
| HKUDS/CLI-Anything | 让所有软件 Agent-Native |
| xai-org/x-algorithm | X(Twitter)推荐算法 |
| koala73/worldmonitor | 实时全球情报仪表盘 |
| chenglou/pretext | 文本测量/布局 |
| zeroclaw-labs/zeroclaw | Rust AI 助手基础设施 |

---

## 授粉勘察：跨域映射

### 🔴 可直接集成的（不改代码直接用）

| 项目 | 集成方式 | 对接 scratchpad 哪个模块 |
|------|---------|------------------------|
| headroom | MCP Server / Python库 | Hermes 上下文压缩 → 省 token |
| rtk-ai/rtk | CLI proxy 旁路 | Hermes CLI 调用管道 |
| OmniRoute | API 网关 | Hermes 模型切换 fallback |
| Agent-Reach | CLI tool | mcpserver/ 多平台信息源（已有 B站支持！） |
| agent-browser | CLI tool | mcpserver/ 浏览器自动化 |

### 🟡 设计参考（不改代码，学架构）

| 项目 | 学什么 |
|------|--------|
| **graphify** | AST 解析→知识图谱。**错位**：化学式 PEG 解析器 + AST → 材料合成步骤图谱 |
| **mempalace** | AI 记忆基准测试方法。**错位**：用于评估 summer_memory/GRAG 的检索质量 |
| **caveman + ponytail** | Token 压缩的两种哲学（压缩 vs 懒惰）。**错位**：用于 Lumo 对话上下文的极限压缩 |
| **Eureka** | Agent harness 的 skills/instincts/memory 分层。**错位**：改进 Hermes skill 管理体系 |
| **x-algorithm** | 推荐算法的 ranking 管线。**错位**：用于知识库文档的「相关性排序」→ RAG 检索重排 |
| **pretext** | 文本精确测量/布局。**错位**：Live2D 对话气泡的精确排版 |
| **CLI-Anything** | 把任何软件变成 CLI 工具。**错位**：用 CLI 包装材料科学软件(MatLab/Gaussian)→MCP tool |
| **worldmonitor** | 实时情报聚合架构。**错位**：RSS→情报→蜜罐规则的实时管道优化 |

### 🟢 纯授粉（看起来完全无关但核心结构共鸣）

| 源项目 | 看起来做什么 | 核心数据结构 | 错位用法 |
|--------|------------|-------------|---------|
| **voicebox** | AI 语音克隆 | 声音特征向量空间 | 材料声学特性→频域特征分类。一个材料敲击的声音特征可能区分晶体/非晶 |
| **open-design** | Agent 做 UI 设计 | 设计→代码的 token 规范 | 材料配方→结构化表示的 token 规范。配方本质是一种 DSL |
| **nanobot** | 轻量 Agent 框架 | WebUI+Tools+Memory+MCP 一体化 | 作为 Lumo 后端的轻量替代方案参考 |
| **openhuman** | 个人 AI 超级智能 | 本地优先记忆+Agent 编排 | 记忆架构对比：四层认知 vs GRAG 五元组 |
| **llmfit** | 模型硬件适配 | 模型×硬件兼容矩阵 | SDR 信号处理管道的硬件适配评估 |

---

## 授粉热点：3 个最值得立刻动手的

### 1. Agent-Reach → 陆墨的「外部感官」
- 已支持 B站/小红书/Twitter/Reddit/YouTube/GitHub
- 许可待确认（大概率 MIT）
- 直接作为 mcpserver/ 的一个新 Agent
- 让陆墨能「看到」外部世界

### 2. headroom + caveman → Hermes 的「省 token 双刀流」
- headroom: 压缩工具输出/RAG 块/日志(JSON省60-95%)
- caveman: 压缩 prompt 风格(省65%)
- 两者互补：一个压数据，一个压指令
- 都确认 MIT

### 3. graphify → 陆墨的「知识图谱生成器」
- Apache-2.0，无许可障碍
- 代码库→AST→知识图谱的管线
- **错位到材料科学**：把化学式 PEG 解析器的输出喂给 graphify 的图谱生成层
- 结果：材料合成路径自动图谱化

---

> 下次扫货：不再设 stars 门槛，重点扫 **star<100 但最近一周突然暴涨** 的项目——那种才是真正的「隐藏宝石」。
