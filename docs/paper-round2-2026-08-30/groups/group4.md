# 升级项目组 4：工具链/基础设施 — SPEC·工单·提示词合集（K01-K11 + I01-I10）

> 生成：2026-08-30 · 来源：5648 篇论文全量精读 Round2
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可丢给执行 AI
> 优先级：P0=立即 / P1=1-2周 / P2=观察

---

## K01 ZotPilot 文献管理 MCP
【SPEC】ZotPilot（文献管理 MCP）接入材料文献库；验收=MCP 封装+注册+测试。
【工单】①勘察 ZotPilot 仓库（许可核实）②封装 MCP（搜索/导入/标注）③注册 agent-manifest④测试。
【提示词】你是 MCP 封装 AI。封装 ZotPilot 文献管理：先 gh api 核实许可（无 LICENSE 暂缓），按 mcpserver/ 现有风格封装（manifest.json + Python class + 单测），支持文献搜索/批量导入/方向标注。验收：pytest 全过 + manifest 注册 + 许可标注。

## K02 TanStack/cli Skill 分发管线
【SPEC】Agent Skills 安装机制→skill 分发管线；验收=方案+原型。
【工单】①勘察 TanStack/cli②设计分发管线③原型。
【提示词】你是工具链 AI。勘察 Agent Skills 安装机制：参考 TanStack/cli 的 skill 安装/分发设计，输出 docs/skill-distribution-勘察.md：安装协议/版本管理/本地 skill 目录集成。验收：方案 + 原型脚本。

## K03 digest 流水线升级（评价表自动化）
【SPEC】逐篇评价表自动化生成（Round2 经验固化）；验收=脚本+试跑。
【工单】①梳理 Round2 经验②写评价表生成脚本③试跑。
【提示词】你是流水线 AI。把 Round2 经验写成自动评价表脚本：输入 digest 文件→输出逐篇评价表（内容+可利用度）。参考 /home/ubuntu/research/papers/round2/ 现有 digest 格式。验收：脚本可跑 + 输出示例。

## K04 超时重试策略固化
【SPEC】把"≤100 篇/块 + 两次调用"固化为流水线参数；验收=参数文档+验证。
【工单】①总结超时规律②更新 paper-digest-pipeline skill③验证。
【提示词】你是流水线运维 AI。固化超时策略：总结本次 44 块经验（>150 篇超时、≤100 篇成功率 100%、子代理预处理浪费），更新 ~/.hermes/skills/research/paper-digest-pipeline/SKILL.md 的分块参数与子代理纪律章节。验收：skill 已更新 + 变更摘要。

## K05 授粉点格式统一模板
【SPEC】44 份 digest 授粉点格式异构→统一模板；验收=模板+迁移。
【工单】①分析异构格式②定模板③迁移工具。
【提示词】你是文档工程 AI。统一授粉点格式：分析 /home/ubuntu/research/papers/round2/digests/ 44 份的授粉点格式差异，定义统一模板（来源|流向|用途|优先级），写迁移脚本。验收：模板文档 + 迁移脚本 + 样例。

## K06 论文池增量自动 digest
【SPEC】每日增量 cron 补全量 digest 轮（不只周度摘要）；验收=cron 更新+试跑。
【工单】①看现有 cron（ad17cd9d341f）②补 digest 环节③试跑。
【提示词】你是 cron 运维 AI。更新论文流水线 cron：现有 ad17cd9d341f 每天 2:00 只做趋势摘要，补上"新论文≥N 篇时触发 digest"逻辑（参考 paper-digest-pipeline skill 分块模式）。验收：prompt 更新 + 触发条件明确。

## K07 授粉矩阵 → MatChat 索引
【SPEC】117 项授粉矩阵进知识库 MatChat 索引；验收=索引入库。
【工单】①格式化矩阵②入库③验证查询。
【提示词】你是知识库 AI。把 UPGRADE-PROJECTS-2026-08-30.md 的 117 项授粉矩阵结构化（编号/线/来源/落点/优先级/状态），导入知识库 MatChat 可查询。验收：入库 + 3 个查询示例。

## K08 符号回归工具链 → ELN 分析模块
【SPEC】NestyNet/RUPF 符号回归工具链集成 ELN 分析；验收=模块+案例。
【工单】①选工具②封装③ELN 集成案例。
【提示词】你是科研工具 AI。集成符号回归到 ELN：把符号回归（NestyNet 风格/物理引导）封装为 ELN 分析模块，输入实验数据输出经验方程+不确定度。验收：模块 + 生物质数据案例。

## K09 频谱事件缓存 MCP 注册
【SPEC】R01 的频谱事件缓存模块注册为 MCP 工具；验收=manifest 注册+查询测试。
【工单】①接 R01 模块②agent-manifest 注册③测试。
【提示词】你是 MCP 集成 AI。把频谱事件缓存注册为 mcpserver 工具（spectrum_events.current_interferers/recent_events），照 agent-manifest.json 模式。验收：manifest 注册 + 查询测试通过。

## K10 三线授粉合并 backlog
【SPEC】论文/扫货/round10 授粉合并统一 backlog；验收=合并文档+去重。
【工单】①盘点三线②合并去重③定优先级。
【提示词】你是授粉管理 AI。合并三线授粉：论文轮（weekly_pollination）+ 扫货（POLLINATION-*）+ round10（OTA-ELM），去重合并成统一 backlog 文档。验收：合并表 + 去重说明。

## K11 材料性能预测管线
【SPEC】主动学习闭环（M03 扩展）做实验指导管线；验收=管线+指导输出。
【工单】①接 M03 原型②加实验指导逻辑③试运行。
【提示词】你是实验设计 AI。搭材料性能预测管线：主动学习闭环预测→推荐下一组实验条件（温度/配比/时间）→更新模型。验收：管线可跑 + 一组推荐输出。

## I01 MPC 分布式量子路径（远期）
【SPEC】跟踪 MPC 分布式量子计算（近尺度不变开销）；验收=观察笔记。
【工单】①读 G4-3 digest②写观察③标触发条件。
【提示词】你是技术雷达 AI。写 MPC 分布式量子观察：读 digest-g4-3-2026-08-30.md 授粉点，记录分布式超导量子计算近尺度不变开销。验收：笔记含触发条件。

## I02 分布式超导量子工程路径
【SPEC】百万量子比特工程路径跟踪；验收=观察笔记。
【工单】①读 G4-3 digest②提炼路径③笔记。
【提示词】你是技术雷达 AI。写量子工程路径笔记：读 digest-g4-3-2026-08-30.md，提炼百万量子比特可信工程路径。验收：笔记 + 里程碑。

## I03 3D-IC 开源基准
【SPEC】评估 3D-IC 开源基准套件（chiplet/TSV/混合键合）；验收=勘察。
【工单】①读 GX-5b digest②评估基准③写勘察。
【提示词】你是 EDA AI。勘察 3D-IC 基准：读 digest-gx-5b-2026-08-30.md 授粉点 ③，评估首个 3D-IC 公开基准的可用性。验收：勘察报告 + 接入建议。

## I04 Redwood AI 加速器
【SPEC】评估 Redwood（2 周 tape-out AI 全流程）；验收=勘察。
【工单】①读 GX-5c digest②分析流程③写勘察。
【提示词】你是芯片设计 AI。勘察 Redwood：读 digest-gx-5c-2026-08-30.md 授粉点 ①，分析 AI 全流程加速器（2 周 tape-out）对硬件项目的启示。验收：勘察报告。

## I05 鞅论/信息几何统计工具
【SPEC】鞅论/信息几何统一框架（concentration+PAC-Bayes）→统计工具；验收=原型。
【工单】①读 G9 digest②实现统一不等式③原型。
【提示词】你是统计 AI。实现鞅论统一不等式工具：读 digest-g9-2026-08-30.md 授粉点，把 concentration inequality + PAC-Bayes + Ville 链式分解做成工具库。验收：numpy 实现 + 示例。

## I06 尾敏感因果检验
【SPEC】GFCM 尾敏感条件独立检验用于因果发现；验收=原型+测试。
【工单】①读 G9 digest②实现检验③测试。
【提示词】你是因果推断 AI。实现尾敏感条件独立检验：读 digest-g9-2026-08-30.md 授粉点 ②，实现混合类型尾敏感检验，用于材料/生物数据因果发现。验收：原型 + 基准测试。

## I07 OrbitALIF SNN 联邦学习
【SPEC】评估 OrbitALIF（SNN 卫星联邦学习去云）映射 ESP32 低功耗；验收=勘察。
【工单】①读 GX-4b digest②分析架构③评估。
【提示词】你是边缘 AI。勘察 OrbitALIF：读 digest-gx-4b-2026-08-30.md 授粉点 ①，评估 SNN 联邦学习去云架构用于 ESP32 传感网。验收：勘察 + 功耗对比。

## I08 NeuralNexus 开源机械臂
【SPEC】评估 NeuralNexus 开源 6-DOF 机械臂（STM32H743）作参考平台；验收=勘察。
【工单】①读 GX-3b digest②分析架构③写勘察。
【提示词】你是机器人 AI。勘察 NeuralNexus 机械臂：读 digest-gx-3b-2026-08-30.md 授粉点 ②，评估开源 6-DOF 机械臂（STM32H743+混合步进+Web Serial）作参考。验收：勘察报告 + 复现清单。

## I09 图灵机硬件原型（教学）
【SPEC】ESP32-CAM 光学读卡图灵机做教学/原型平台；验收=方案+原型。
【工单】①读 GX-4a digest②设计光学读卡③原型。
【提示词】你是硬件原型 AI。复现光学图灵机：读 digest-gx-4a-2026-08-30.md 授粉点 ②，用 ESP32-CAM 光学读卡+NEMA17 做嵌入式 Agent 执行引擎原型。验收：接线/代码方案 + 可行性验证。

## I10 MAPPO 集群编队调度
【SPEC】MAPPO+Stackelberg 协同用于 ESP32 集群编队；验收=方案+模拟。
【工单】①读 GX-4a digest②设计 MADRL 框架③模拟。
【提示词】你是多智能体控制 AI。设计 ESP32 集群编队调度：读 digest-gx-4a-2026-08-30.md 授粉点 ①，用 MAPPO+Stackelberg 博弈做分布式编队+无线资源调度。验收：方案 + 模拟计划。
