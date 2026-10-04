# 授粉报告 Batch-1B：graphify + claw-code

> 日期：2026-08-22 晚 | 模式：API 直读 | 许可：graphify Apache-2.0 / claw-code MIT

## 一、Graphify-Labs/graphify（109k★, Apache-2.0）— 代码库→知识图谱

### 架构：Claude Code skill + Python 库

```
detect() → extract() → build() → cluster() → analyze helpers → report.generate() → export.to_*()
```

每阶段独立模块，纯 dict + NetworkX 图通信，无共享状态，副作用只在 `graphify-out/`。

### 模块职责表（源码实读，签名即文档）

| 模块 | 入口 | 输入→输出 |
|------|------|----------|
| detect.py | detect(root) | 目录→扫描摘要（files 分类/总数/词数） |
| extract.py | extract(paths, root=...) | 文件路径列表→{nodes, edges} |
| build.py | build(extractions) | 提取 dict→nx.Graph |
| cluster.py | cluster(G) | 图→社区划分 {community_id: [node_id...]} |
| analyze.py | god_nodes / surprising_connections / suggest_questions / find_import_cycles / graph_diff | 图→分析结果 |
| report.py | generate(...) | 图+分析→GRAPH_REPORT.md |
| export.py | to_json/to_html/to_obsidian/to_svg/to_graphml/to_canvas/to_cypher | 图→多种格式 |
| wiki.py | to_wiki(...) | 图→每社区一篇 markdown + index |
| ingest.py | ingest(url) | URL→语料文件 |
| cache.py | check_semantic_cache / save_semantic_cache | 文件→缓存节点/边 |
| security.py | validate_url / safe_fetch / validate_graph_path / sanitize_label | 校验/防注入 |
| validate.py | validate_extraction | 提取 dict→schema 错误列表 |
| serve.py | serve() / serve_http() | 图文件→**MCP stdio/HTTP server** |
| watch.py | watch(path, debounce=3.0) | 目录→变更重建 |
| benchmark.py | run_benchmark() | 图文件→token 对比 |

### 核心机制（值得抄）

1. **签名即文档**：`tests/test_architecture_doc.py` 导入每个符号名——**架构表无法漂移**（文档=代码=测试三方锁定）
2. **MCP serve**：图直接暴露为 MCP server（stdio/HTTP）——graphify 图谱可被任意 agent 工具化
3. **安全层**：validate_url/safe_fetch/sanitize_label 全有（防 URL 注入/路径穿越）
4. **Obsidian 导出**：图谱→Obsidian vault（知识库直接消费）

### 授粉建议（Lumo 知识库方向，高价值）

- Lumo 代码/文献库加 **detect→extract→build→cluster** 管线：把 scratchpad 知识库变成可查询图谱
- 直接抄 **MCP serve**：图谱 → MCP server → Lumo 可调
- 抄 **安全层**：现有 mcpserver 的 URL 校验可对齐 graphify 的 validate_url
- **建议 clone 完整评估**（Python 库不大，~109k★ 但代码可读）——授粉落点 `mcpserver/material_science/` 旁

## 二、ultraworkers/claw-code（195k★, MIT）— Discord 人机协奏

### 哲学：humans set direction; claws perform the labor

- 人类接口 = **Discord 频道**（手机发一句，走开，claws 干活）
- 通知路由**推出 agent 上下文窗口**（agent 不背通知负担）
- 三件套：OmX(工作流层) + claws(并行 agent) + 协调循环

### 核心机制（值得抄）

1. **notification routing 出窗口**：告警/通知不占用 agent 上下文（对照我们的 cron 分流——思路一致！微信限流那次就是"推送路由"问题）
2. **方向/执行分离**：人类给方向、agent 执行劳动（我们已经在做：用户定方向+Trae 写码+实验田维护者 SPEC）
3. **并行 claws + 失败恢复循环**：多 agent 并行 + 相互 review + 自动重试

### 授粉建议

- **cron 分流体系**抄 notification-routing 思路：所有推送路由到"低上下文通道"（QQ/本地），agent 窗口只留任务（**我们微信分流已落地，这就是同款**）
- 失败恢复循环：cron 任务失败→自动重试队列（现有蜜罐 cron 可加）
- 不引入 Discord（我们用微信/QQ）

## 三、对照总结

| 维度 | graphify | claw-code | 落点 |
|------|----------|-----------|------|
| 知识图谱 | detect→export 全管线 ⭐ | - | Lumo 知识库 |
| MCP 化 | serve() 直接暴露 ⭐ | - | mcpserver |
| 人机协作 | - | 方向/执行分离 | 已在做 |
| 通知路由 | - | 推出上下文窗口 ⭐ | cron 分流已落地 |

## 四、本批授粉行动项（按价值排序）

1. **graphify clone 评估** → Lumo 知识图谱管线（最高价值，落 mcpserver/material_science/ 旁）
2. **openclaw session-lineage** → NEKO 会话血统（~200 行）
3. **context_compressor 升级** → 抄 branch-summarization
4. **claw-code 失败重试队列** → 蜜罐 cron 增强（低优先级）
