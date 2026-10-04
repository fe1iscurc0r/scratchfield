# W69-04 OpenKB 评估（开源 LLM 知识库）

> 上游：VectifyAI/OpenKB · Apache-2.0 · ~4385★ · 2026-04 · Python · 活跃
> 定位：开源 LLM 知识库（RAG 构建 + 查询）
> 结论：**参考为主**（Apache 可借鉴代码，但与本仓 repowiki/llm-wiki skill 重叠）

## 1. 项目定位与架构

OpenKB 是一个面向 LLM 的开源知识库框架，典型 RAG 栈：文档接入（多格式）→ 分块/chunking
→ 向量化（embedding）→ 存储 → 检索 → 生成。核心价值在「知识库构建管线」的工程化封装，
把散落的 RAG 组件（loader/splitter/embedder/vector-store/retriever）串成开箱即用的服务，
并提供查询接口（REST/API）供 Agent 调用。

## 2. 与本仓对照

| 维度 | OpenKB | 本仓 repowiki / llm-wiki skill / swarmvault |
|------|--------|--------------------------------------------|
| 知识库构建 | 通用文档→RAG 管线 | 已有知识库构建（repowiki） |
| skill 形态 | 服务/库 | llm-wiki 已 skill 化 |
| 查询接口 | REST | skill 内查询 |

本仓已有 repowiki（知识库构建）+ llm-wiki skill + swarmvault，OpenKB 与之高度重叠；差异在
OpenKB 的「通用文档（非代码）知识库」更完整（多格式、chunking 策略、元数据过滤）。

## 3. 可落地借鉴点（≥3）

1. **文档接入与 chunking 策略**：多格式 loader + 可配置 chunk 策略（按语义/按段落/重叠），本仓知识库可补「非代码文档」接入。
2. **元数据过滤检索**：检索时按来源/标签/时间过滤，是提高 RAG 准确率的低成本手段。
3. **查询接口分层**：把「构建」与「查询」分离成独立接口，供 Agent 只读查询（对齐 llm-wiki skill 的封装）。
4. **评估闭环**：知识库检索质量评估（命中/召回）内建，可借鉴为本仓 RAG 的评测基座。

## 4. 许可裁定与结论

- **许可**：Apache-2.0，**可借鉴代码**（宽松）。
- **结论**：**参考为主**。Apache 许可无障碍，但能力与本仓 repowiki/llm-wiki skill 重叠，接入价值有限；建议借鉴其「非代码文档接入 + chunking 策略 + 元数据过滤」补齐本仓知识库短板，而非整库引入。
