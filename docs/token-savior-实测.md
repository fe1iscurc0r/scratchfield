# token-savior 实测报告（W99-02 · 本地真实数字）

> 2026-09-08 · 上游：Mibayy/token-savior（MIT，★1145，Python MCP server，53 工具）
> 安装：`pip install token-savior==1.0.0`（含 tiktoken 依赖）

## 一、实测方法

用 token-savior 的核心能力（ProjectIndexer 结构索引）对**真实代码**做压缩前/后 token 对比：
- 语料：`mcpserver/rf_brain/decoders`（15 个源文件、3720 行、175 函数）
- 编码器：cl100k_base（tiktoken，OpenAI 通用编码）
- 压缩产物：结构索引（文件名 + 函数/类签名清单）

## 二、真实数字

| 指标 | 值 |
|------|-----|
| 文件数 | 15 |
| 原始 tokens | **45,303** |
| 结构索引 tokens | **960** |
| 压缩比 | **2.1%**（约 47× 缩减） |

复现：`python tools/token_savior_measure.py [目录]`

## 三、诚实边界（重要）

- 压缩产物是**结构索引**（函数/类/符号签名），**丢失实现体语义**——适合「代码导航 / 变更摘要 / 符号级补丁理解」，**不适合**「全文语义理解 / 逐行审查」。
- 本测为**本地离线测量**（tiktoken 计数），未经网关 E2E（Hermes 实际调用 MCP 工具、端到端 token 对比）——网关链路待真机验证。

## 四、注册

- 已按 mcpserver 外部服务模板登记 `token-savior` 条目（`external_services.example.json`，`_disabled: true` 默认禁用）。
- 启用：pip install token-savior==1.0.0 后置 `_disabled` 为 false，合入 `~/.mcporter/config.json`。

## 五、结论

**有条件接入**：结构级压缩收益真实（2.1%），但适用场景窄（导航/摘要，非全文理解）。
- 接入条件：仅用于「代码库导航 / 变更摘要」工具位，不作为主对话上下文压缩；
- 网关 E2E 实测（Hermes 调用链路）列为待办，在真机环境补测后定终态；
- 与现有工具无冲突（本仓无同功能结构索引工具）。

---
*实测：fe1iscurc0r · 2026-09-08*
