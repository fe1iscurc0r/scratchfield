# EDA 插件 agent 可驱动性矩阵（工单218 任务一）

> 日期：2026-10-08 ｜ 基础：`docs/HW-06B-report.md`（30 仓清单，GitHub API 实拉）+ 本仓 skills/扩展实存
> 驱动模式定义（工单给出）：**M1 零改动**（已有 CLI/API 面）/ **M2 薄桥**（加触发面，agent 指令=人点菜单）/
> **M3 重构**（拆 headless 核心 + UI 壳）/ **不可驱动**（纯 GUI/在线服务）。
> 改造成本为行数级估算（未实装）；许可沿用 HW-06B 结论（全部开源/Apache 系）。

---

## 0. 一页结论

- **第一批改造 2 个**：⭐ **① eext-simulation-with-ngspice（M2 桥）** + ⭐ **② easyeda-pcb-router（M1 直接挂 MCP tool）**——SPEC 级拆解见 §3，本单不实施；
- M2 桥统一标准：**走 easyeda-agent connector 的 60832 daemon（B 路线）**，见 `pro-api-0414-delta.md` §3；
- 与自家 skills 的取舍：`eext-generate-schematic-from-netlist` 与 `skills/easyeda-schematic-autodraw` **同域并留**（一个是上游参考实现、一个是自家 typed 版）。

## 1. 30 仓可驱动性矩阵

### 1.1 独立可跑（无需 EDA 客户端）

| 仓 | 功能 | 模式 | 改造成本 | 双向价值 |
|---|---|---|---|---|
| **easyeda-pcb-router** | Freerouting CLI 封装（网表→自动布线） | **M1（已是）** | ~0（挂 MCP tool 的 manifest + 沙箱声明，百行内） | ⭐⭐⭐ 自动布线闭环（agent 出网表→布线→DRC 回读） |
| easyeda-simulation-engine | NGspice+SimulIDE 本地引擎 | **M1（倾向）** | 低（同上模式） | ⭐⭐ 仿真无 GUI 依赖（ngspice 桥的地基） |
| easyeda-documents | 文档站 | 不驱动 | — | — |
| easyeda-std-i18n | i18n 库 | 不驱动 | — | — |

### 1.2 编辑器内扩展（需客户端 + 外部交互开关）

| 仓 | 功能 | 模式 | 改造成本 | 双向价值 |
|---|---|---|---|---|
| **eext-simulation-with-ngspice** | 编辑器内 ngspice 仿真（原理图→网表→仿真→波形） | **M2** | 中（加触发面+结果 POST，~200-400 行） | ⭐⭐⭐ 仿真结果回传 rf_brain/寄生链 |
| eext-freerouting-intergration | 编辑器内 Freerouting 集成 | M2 | 中 | ⭐（与 pcb-router 功能重叠——见 §2.4 上游关系） |
| eext-chat-with-ai-kimi | AI 问答+元件查询+**网表解析** | **M3** | 高（拆网表解析为 headless 库，~500+ 行） | ⭐⭐ 寄生链 Phase2 连线对账的参考实现 |
| eext-generate-schematic-from-netlist | 网表→原理图 | M2/M3 | 中 | ⭐⭐ 与 schematic-autdraw 同域（§2.3） |
| eext-export-design-archive | 批量导出工程压缩包 | M2 | 低（菜单→触发面，~100 行） | ⭐（ parasite-export 已覆盖单文档推送） |
| eext-export-design-report | PCB 统计报告（已 fork） | M2 | 低 | ⭐（fork 版已加寄生参数估算） |
| eext-interactive-html-bom | iBOM（已 fork） | M2 | 低 | ⭐ |
| eext-batch-place-components | 批量放件 | M2 | 低 | ⭐（autodraw skill 部分覆盖） |
| eext-update-components-attributes | 批量改属性 | M2 | 低 | ⭐ |
| eext-delete-all-components | 清空元件 | M2 | 低 | ⭐ |
| eext-api-test-tool / eext-api-debug-tool | API 调试面板 | 不可驱动（人工调试器） | — | —（开发期工具） |
| eext-easyeda-api-agent | NL→eda.* 调用（DeepSeek 后端） | 不可驱动（与自家 agent 定位重叠） | — | 参考（NL→API 的映射思路） |
| eext-ai-library-builder / eext-ai-symbol-builder | AI 建库/符号 | M3 | 高 | ⭐（材料线符号生成可借） |
| eext-extension-demo | 五合一案例 | — | — | 参考 |
| eext-plm-integration-demo | PLM 对接参考 | — | — | 参考 |
| eext-external-tool-integration-demo | **外部工具集成**（与寄生链通道B 同构） | 参考 | — | ⭐（M2 桥的官方范式） |
| eext-coil-creator / eext-graffiti-silkscreen / eext-generate-silkscreen / eext-note-tools / eext-qrcode-generator | 小工具群 | M2 | 各低 | —（无双向诉求） |
| eext-pcb-price-calculator | 计价 | M2 | 低 | — |
| eext-pcb-render-with-blender | Blender 渲染 | M2/M3 | 中 | — |
| eext-simulation-with-simulide | SimulIDE 仿真 | M2 | 中 | ⭐ |
| easyeda-api-skill | 官方 AI 编程 SKILL（API 定义） | **M1（资产）** | 0 | ⭐⭐（可直接喂自家 agent 工具目录） |
| pro-api-sdk | 扩展开发 SDK | —（地基） | — | ⭐⭐（四件套的地基） |

## 2. 五个重点目标深评

### 2.1 eext-simulation-with-ngspice —— 第一批 ①（M2）

- 现状：编辑器内原理图→网表→ngspice→波形面板（人用 GUI）。
- 双向价值：**仿真结果回传 rf_brain/寄生链**——RF 链路的"S 参数/瞬态"是寄生参数提取的验证闭环缺的那一环。
- 改造：M2 桥（daemon typed action）+ 结果 POST `/api/eda/simresult`（可复用 ingest 的鉴权/落盘模式）。

### 2.2 easyeda-pcb-router —— 第一批 ②（M1）

- 现状：**独立 CLI**（Freerouting：输入 DSN 网表 → 输出布线后网表），无需 EDA 客户端 → 天然 M1。
- 双向价值：**自动布线闭环**（agent 出网表 → pcb-router 布线 → 结果回读 DRC）。
- 改造：不碰它本体，只在 mcpserver 挂 tool（manifest + 沙箱声明 + 输入输出契约），工作量在**契约面**不在代码。

### 2.3 eext-generate-schematic-from-netlist vs skills/easyeda-schematic-autodraw —— 同域取舍

- 上游：网表→原理图（通用）；
- 自家 autodraw：typed action、面向"AI 生成网表→自动放件连线"（HW-06B §2 已对上 `getDocumentSource` 链）。
- **结论：并留**——上游是参考实现（布局/连线算法可读源码），自家是产品化路径；
  autodraw 吸收上游算法思想即可，**不需要二选一**。等 autodraw 稳定后上游降级为纯参考。

### 2.4 eext-freerouting-intergration 与 easyeda-pcb-router 的上游关系

- 两者都包 **Freerouting**（开源 Java 自动布线器）：
  `easyeda-pcb-router` = 独立 CLI 封装（无客户端）；`eext-freerouting-intergration` = 编辑器内集成（导出 DSN→调 Freerouting→回导）。
- **关系：同一引擎的两种宿主形态，不是上下游**。agent 场景选 **CLI 版**（无人值守）；编辑器内版本留给人工。
- ⭐ 避坑（工单点名的"双抱佛脚"）：**只抱 CLI 一条线**，M2 桥不为 freerouting-intergration 单独做。

### 2.5 eext-chat-with-ai-kimi 的网表解析（M3）

- 网表解析/电路分析在其 UI 内 → 需 M3 拆 headless 核心。
- **结论：延后**——寄生链 Phase2 的连线对账可先用自家 `read_schematic.py`（HW-06 已通 .esch 解析）；
  kimi 的解析逻辑作为**源码级参考**读一遍即可，不值得 500+ 行重构（除非其解析覆盖面显著更广——待 Phase2 实测）。

## 3. 第一批 2 个的 SPEC 级拆解（不实施）

### SPEC-A：ngspice 仿真桥（eext-simulation-with-ngspice → M2）

```
1. 触发面：easyeda-agent connector 注册 typed action "simulation.run"
   入参 {analysis: "ac"|"tran"|"dc", netlist?: str, params: dict}
2. 执行：扩展内走既有 ngspice 调用链（不重写仿真逻辑）
3. 结果回传：POST /api/eda/simresult（X-EDA-Token 鉴权，复用 ingest 模式）
   信封 {meta:{project, analysis}, raw: "<ngspice 输出>", parsed: {...}}
   → 落盘 eda_simresult/ + EventBus 事件 lumo.eda.simulation_result
4. 消费：rf_brain 订阅（S 参数/增益 → 寄生链验证）；前端仿真面板拉取
5. 验收：原理图页触发 ac 分析 → 云服收到结果 → bus events 可查
```

### SPEC-B：pcb-router MCP 工具（easyeda-pcb-router → M1）

```
1. mcpserver 挂 tool "pcb_auto_route"（manifest：domain=radio，tier=material 级）
   入参 {dsn_path} 出参 {status, routed_dsn_path, stats}
2. 沙箱：Freerouting JVM 可执行（依赖声明 + 健康检查提示安装，同 ROS 线纪律）
3. 闭环：agent 出网表（schematic autodraw / netlist 工具）→ auto_route → DRC 回读
4. 验收：合成 DSN 跑通布线 → stats 返回（过孔数/布通率）
```

（两份 SPEC 均为工单授权的"拆解不实施"。）
