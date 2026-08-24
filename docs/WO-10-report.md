# WO-10 验收报告：CLI-Anything vs codebase-memory-mcp 对比

日期：2026-08-22 ｜ 结论先行：**推荐 CLI-Anything 优先接入（已完成 80%），codebase-memory-mcp 列为可选增强，不二选一淘汰，但封装工单先开给 CLI-Anything。**

## 1. 最小示例验证（均在本机真实跑通）

**CLI-Anything（Apache-2.0）**
- 本地适配器 `mcpserver/agent_cli_anything`（目录查询：list_cli_tools / search_capabilities）pytest 14/14 通过（0.17s），纯离线，数据源为上游 registry.json。
- 上游形态：`pip install cli-anything-hub` + 100+ 面向 Agent 的 GUI 应用 CLI harness（GIMP/Blender/OBS/qgis…），Python ≥3.10 + click。

**codebase-memory-mcp（MIT）**
- 下载 v0.10.8 Windows 版（zip 38MB，解压后二进制 283MB），未运行其 `install`（避免改写 agent 配置），直接用 `cli` 子命令手动验证：
  - `index_repository --repo-path research/planner --mode fast` → 35 节点 / 83 边，耗时 9.9s（含临时 daemon 启动）
  - `search_graph --query "plan"` → 正确返回 `PlannerExecutor.plan`（planner.py:84-94）与 `PlanResult`，BM25 + 结构加权
- 15 个 MCP 工具（search_graph/trace_path/query_graph Cypher/get_architecture/ADR 管理…），声明支持 43 种 agent 客户端（含 TRAE、Hermes、OpenClaw）。

## 2. 四维对比

| 维度 | CLI-Anything | codebase-memory-mcp | 结论 |
|---|---|---|---|
| 稳定性 | 声明 2461 测试；本地实测适配器 14/14；harness 质量依赖各 app 社区贡献，单体参差 | 本机端到端索引+查询无报错；声明 6768 测试 + SLSA 3 + VirusTotal 出厂扫描 | codebase-memory-mcp 工程质量更硬，CLI-Anything 上游 harness 良莠不齐 |
| 依赖体积 | 轻量：Python 包 + registry JSON（clone 65MB 主要为文档/资产；运行时按需装单个 harness） | 重：Windows 二进制 283MB（zip 38MB），源码 clone 1.3GB（含 vendored tree-sitter 全语法树） | CLI-Anything 显著更轻 |
| 维护活跃度 | ★47.9k，最近推送 2026-08-21（昨天），77 open issues | ★39.8k，最近推送 2026-08-22（今天），476 open issues（多为功能请求，队列较长） | 双方都极活跃；CLI-Anything issue 健康度更好 |
| 与 scratchpad mcp_manager 兼容性 | **已兼容**：mcp_manager 走进程内 handle_handoff 路由，agent_cli_anything 已注册，零额外工作 | 需新增 stdio 桥：mcp_manager 不直接支持外部 MCP server，需经 mcporter_bridge 或 CBM 自带 install 写入客户端配置，属中等改造 | CLI-Anything 完胜（已落地） |

## 3. 推荐与接入方案

**推荐：CLI-Anything**（方向请你最终拍板）。

理由：两者解决的是不同问题（CLI-Anything = "让 agent 能操作 GUI 软件"；CBM = "让 agent 少读文件理解代码库"），不是同位竞品。但按"给 Hermes/N.E.K.O. 补 MCP 工具"的目标：
1. CLI-Anything 适配器已在仓库里且测试全绿，剩余工作只是能力扩展（把 catalog 查询升级为实际调用 cli-hub 装好的 harness）。
2. CBM 283MB 二进制 + stdio 桥改造，收益（代码检索省 token）对 scratchpad 这种 Python 单体仓不如对大型多语言仓明显。

CBM 保留为可选：若后续 agent 需要跨仓代码结构问答，走 `mcporter_bridge` 注册或在云服用其 `install`（官方支持 TRAE/Hermes/OpenClaw 配置写入）。二进制已验证可跑，随时可启用。

## 4. 环境产物

- `github_haul/CLI-Anything/`（去 .git 参考副本，65MB）
- `github_haul/codebase-memory-mcp/`（去 .git，1.3GB——若嫌大可删，保留 docs/llms.txt 与 README 即可）
- CBM Windows 二进制在系统临时目录 /tmp/cbm/，未做全局安装，不影响现有 agent 配置
