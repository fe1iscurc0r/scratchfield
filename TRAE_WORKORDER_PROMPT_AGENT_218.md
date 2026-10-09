# 工单 218 · 嘉立创 EDA 插件生态深适配（二）——"人用插件"改造为智能体可驱动 + 底层双向适配扩面

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：工单 217 落了双向第一链（ingest 接收端）。用户追问两件事：①还有哪些插件可做双向适配或改嘉立创底层；②**能否把原本给人用的插件改造成智能体可驱动**。本单把 easyeda 组织 30 仓生态按"agent 可驱动性"重排，选出改造目标。

## 核心思路：插件的三种驱动模式

人的插件给 agent 用，有三档改法（成本递增）：

| 模式 | 改法 | 例子 |
|---|---|---|
| M1 零改动 | 插件有命令行/API 面，agent 直接调 | easyeda-pcb-router（Freerouting CLI，无需客户端） |
| M2 薄桥 | 给人用插件加一个 WebSocket/HTTP 触发面，agent 发指令=人点菜单 | ngspice 仿真插件、export-design-archive |
| M3 重构 | 人机面板拆成 headless 核心 + UI 壳，agent 用核心 | chat-with-ai-kimi 的网表解析 |

## 任务一（P0）：30 仓生态按"agent 可驱动性"重排

基于 HW-06B-report 已有清单（easyeda 组织 30 仓，全部 Apache-2.0/开源），产出 `docs/eda-agent-drivability-matrix.md`：

1. 每仓一行：`仓 | 本体功能 | 现在是 M1/M2/M3/不可驱动 | 改造成本(行数级估) | 双向价值`
2. 重点评估五个高价值目标：
   - **eext-simulation-with-ngspice**：仿真结果回传 rf_brain/寄生链——M2（加触发面+结果 POST）
   - **easyeda-pcb-router**（Freerouting CLI）：已是 M1——评估直接挂 mcpserver 做 tool（自动布线闭环）
   - **eext-generate-schematic-from-netlist**：网表→原理图，与 skills/easyeda-schematic-autodraw 同域——对照后定谁留谁并
   - **eext-chat-with-ai-kimi 的网表解析**：M3——拆 headless 核心，喂寄生链 Phase2 连线对账
   - **eext-freerouting-intergration**：与 easyeda-pcb-router 上游关系查清（避免双抱佛脚）
3. 结论：选出**第一批改造 2 个**（预计：ngspice 桥 + pcb-router MCP 工具），给 SPEC 级拆解但不实施

## 任务二（P1）：底层适配面盘点——pro-api 0.4.14 的 130 类里还藏着什么

已知 pro-api-types v0.4.14（Apache-2.0）有 130 类，本机 easyeda-agent CLI 索引只到 0.3.12（93 命名空间/742 方法）——**中间有版本差**。

1. 拉 @jlceda/pro-api-types v0.4.14 类型定义（npm 源码级盘点，不装运行时）：
   - diff 0.3.12 → 0.4.14：新增的命名空间/方法清单，标注哪些对双向适配有用（如事件订阅、批量操作、导出通道）
2. 特别盘 **sys_MessageBus**（消息总线）：若它支持订阅编辑器事件（文档切换/保存/选区变化），就能做"EDA 状态实时镜像到云服"——比手动 ingest 更高一层
3. 产出 `docs/pro-api-0414-delta.md`：新增面清单 + sys_MessageBus 事件订阅可行性 + 底层改造禁区（哪些是编辑器私有不可依赖）

## 任务三（P1）：M2 桥的参考实现选型

1. 对比三条 M2 桥技术路线，选一：
   - A：扩展内嵌 HTTP server（需"外部交互"开关，与 knowledge-base/mcad 同模式）
   - B：走 easyeda-agent connector 的 60832 daemon（typed action 注册，复用现有连接器）
   - C：寄生链通道B 的 POST-push 模式（agent 拉取，无实时性）
2. 评估维度：实时性/配置复杂度/与现有 skills 兼容/上游更新冲突风险
3. 结论写进任务一的 matrix（作为所有 M2 改造的统一桥标准）

## 验收
- [ ] 任务一：drivability-matrix 覆盖 30 仓全量 + 五重点仓深评 + 第一批 2 个 SPEC 级拆解（不实施）
- [ ] 任务二：pro-api-0414-delta 含版本 diff 清单 + sys_MessageBus 可行性结论 + 禁区标注
- [ ] 任务三：M2 桥三选一结论 + 统一桥标准
- [ ] 全程零运行时依赖引入（类型定义级盘点）；CI 绿
