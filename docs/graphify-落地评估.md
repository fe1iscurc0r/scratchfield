# graphify 落地评估（合并版：授粉实测 + W-03 落地实现）

> 本文件由两版合并：① 2026-08-22 晚「授粉 Batch-1B 深化」实测记录（官方 skill 验证）；
> ② 2026-08-23「补写版」（W-03 工单落地实现与验收）。两版信息互补，统一收编。

---

## 第一部分：上游是什么

- 仓库：https://github.com/Graphify-Labs/graphify （Apache-2.0，GitHub Trending 常客，工单记 109k★）
- 定位：把代码库、文档、SQL schema、配置、PDF 乃至截图/音视频，映射成**可查询的知识图谱**。
- 形态：`pip install graphifyy`（注意双 y），主打 Claude Code/Cursor 的 `/graphify` skill；CLI 亦有 `query/path/explain` 子命令。
- 技术栈：tree-sitter AST + Claude（概念抽取）+ NetworkX + Leiden 社区检测（graspologic）+ vis.js 可视化。
- 产物：`graphify-out/` 下 `graph.json`（持久图谱，可事后查询不重读源库）、`GRAPH_REPORT.md`、`graph.html`、Obsidian 兼容笔记、`cache/`。
- 关键设计：每条边带置信标签 **EXTRACTED（AST 直接证据）/ INFERRED / AMBIGUOUS**，杜绝黑盒边。

### graph.json schema（对齐上游 worked/mixed-corpus/graph.json 实测）

```json
{
  "nodes": [{"id": "analyze", "label": "analyze.py", "file_type": "code",
             "source_file": "raw/analyze.py", "source_location": "L1",
             "community": 1}],
  "links": [{"relation": "contains", "confidence": "EXTRACTED",
             "source_file": "raw/analyze.py", "source_location": "L6",
             "weight": 1.0, "source": "analyze", "target": "analyze_main"}]
}
```

---

## 第二部分：授粉实测记录（2026-08-22 晚，真实跑通）

> 状态：✅ **已装进 Hermes skills，真实管线验证通过** —— 从"授粉参考"升级为"直接可用"。

| 步骤 | 结果 |
|------|------|
| clone + pip install | ✅ 22M 小仓，秒装 |
| `graphify install --platform hermes` | ✅ 官方支持，装到 `~/.hermes/skills/graphify/` |
| 完整管线（48 py 测试集） | ✅ 1797 节点 / 3593 边 / 104 社区，秒级 |
| cluster-only 报告生成 | ✅ GRAPH_REPORT.md + graph.html + graph.json |
| explain 查询 | ✅ extract() 节点：22 连接、来源行号、社区归属 |

**关键事实**：graphify 官方 `install` 命令列出的平台里**包含 hermes**（还有 trae/trae-cn/codebuddy/kiro/pi/devin/antigravity）——这是给 Hermes Agent 定制的官方 skill。

### 能力确认（对应 Batch-1B 报告）

1. **detect→extract→build→cluster 全管线** ✅（实测）
2. **MCP serve**：serve.py 提供 stdio/HTTP MCP server（图→任意 agent 工具化）
3. **explain/path/diagnose** 查询工具 ✅（实测 explain）
4. **跨 repo 合并**：merge-graphs 支持多仓联合图
5. **导出**：JSON/HTML/SVG/GraphML/Obsidian/Neo4j/Cypher/FalkorDB
6. **多模态**：代码/文档/论文/图片/视频（whisper 转录）
7. **增量更新**：--update 只重建变更文件

### 与现有栈的整合点

| 场景 | 用法 | 落点 |
|------|------|------|
| Lumo 知识库图谱化 | `/graphify scratchpad-knowledge/` → 可查询图谱 | 科研知识库导航 |
| mcpserver 工具化 | serve.py MCP server → Lumo/NEKO 可调 | 图谱查询工具 |
| 代码库审计 | `/graphify rf_brain/` → god node/社区发现 | 架构体检 |
| Obsidian 导出 | --obsidian → 知识库 vault | 笔记互链 |
| 跨仓合并 | merge-graphs 多仓 | 多项目联合图谱 |

### 限制

- **社区命名需 LLM backend**：无 API key 时保持 "Community N" 占位（可设 GOOGLE_API_KEY 或 --backend）
- 大仓首次建图耗时（48 文件秒级，千文件级需分钟）
- GraphRAG-ready JSON 但 RAG 检索链路（bge-small-zh）需自己接

---

## 第三部分：W-03 落地实现评估（2026-08-23）

> W-03 工单引用本文件作为输入；开工时经全仓检索确认原始评估不存在，
> 故先补写（第二部分已找回原始实测，两版合并）。本文按上游 README
> （raw.githubusercontent.com，2026-08-23 抓取）+ 本次落地实现记录评估。

### 评估结论（为什么这么落地）

| 维度 | 上游能力 | 缺口 | 本仓对策 |
| --- | --- | --- | --- |
| 图谱生成 | tree-sitter 多语言 + Claude 概念抽取（PDF/图片/多模态） | 生成强依赖 Claude Code + API key，非确定性，CI/测试不可复现 | 内置**确定性零依赖管线**（Python ast + Markdown 标题/链接），测试可离线跑；上游产出可 `graphify_import` 进来查 |
| 存储 | graph.json 单文件持久化 | — | 直接沿用同 schema 同位置（`<语料>/graphify-out/graph.json`） |
| 查询 | CLI 三件套 query/path/explain | 无向量检索（上游自称 no vector store），无 citation 结构 | **TF-IDF 稀疏向量余弦 + 关键词两路 RRF 融合**（k=60 对齐仓内 hybrid_search 惯例）；每条命中带 `citation = source_file:source_location` |
| MCP | `--mcp` 起 stdio server | 与本仓 manifest 注册体系不同构 | 封装 `GraphifyBridge`（agent-manifest.json entryPoint），走 `scan_and_register_mcp_agents` 进 MCP_REGISTRY |

**融合层级：内嵌（mcpserver/）**——与 haul 决策一致。不 vendor 整个上游（Python 包
`graphifyy` 依赖链重且核心走 LLM），只对齐其**数据契约**（graph.json schema），
保证上游/本仓产物互认。

### 落地物

```
mcpserver/adapters/graphify/
├── agent-manifest.json   # name=graphify, agentType=mcp, license=Apache-2.0（硬约束）
├── engine.py             # 生成管线 + TF-IDF/RRF 查询 + 引用溯源（纯标准库）
└── adapter.py            # GraphifyBridge：handle_handoff 分发 6 工具
tests/test_graphify_adapter.py
```

工具面：`graphify_build`（建图）/ `graphify_import`（导上游图）/ `graphify_query`
（提问，含 citation）/ `graphify_path` / `graphify_explain` / `graphify_status`。

### 验收记录（2026-08-23）

- `pytest tests/test_graphify_adapter.py` → **16 passed**（生成 schema/幂等、
  提问 citation 递归断言 + `'"citation"'` grep 口径、markdown 引用、上游图导入、
  path/explain、注册链路、unified_call 全链路、fail-fast 分支）。
- mcpserver 相关回归（test_mcp_adapters + hamlog + paper_miner + llm4decompile +
  test_config_and_tools）→ **108 passed**，新 manifest 未引发注册冲突。
- grep 口径：`"citation"` 字段存在于 query/path/explain 三个工具的全部返回结构。

---

## 第四部分：后续可做（不在本单范围）

1. dense 向量：把 TF-IDF 稀疏路替换/叠加 NEKO memory `_embeddings` 的稠密向量（需跨包依赖评审）。
2. 多语言 AST：tree-sitter 接 JS/TS/Rust（上游已覆盖，可考虑 vendor 其 AST 层）。
3. 图谱可视化：直接复用上游 `graph.html` 模板。
4. 建议下一步：`/graphify ~/scratchpad` 建全库图谱（或先建 rf_brain/NEKO 子库）——官方 skill 已就位，随时可用。
