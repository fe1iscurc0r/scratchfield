"""graphify — 代码/文献知识图谱适配包（GraphRAG，Lumo P2）。

上游 https://github.com/Graphify-Labs/graphify （Apache-2.0）：
代码/文档/PDF → 可查询知识图谱，边带 EXTRACTED/INFERRED 置信标签。

本包两层设计：
- engine.py：零依赖图谱引擎——离线生成（Python AST + Markdown 标题）
  + TF-IDF 向量检索 + RRF 融合 + 引用溯源（source_file/source_location）。
  graph.json schema 对齐上游 worked/mixed-corpus/graph.json，
  上游 CLI 产出的 graph.json 可直接 graphify_import 进来查。
- adapter.py：GraphifyBridge（agent-manifest.json entryPoint），
  scan_and_register_mcp_agents 自动注册，handle_handoff 分发 6 个工具。
"""
