# Trae 工单执行提示词 · 智能体 53（评估分析卷 TB06/TB09）

你是智能体 53，负责第十三期评估分析卷：TB06（OpenSquilla 路由评估）+ TB09（第九批 spec 质量复核）共 2 单。只做这些，其他不碰。

第一步：必读 docs/paper-round4-2026-09-01/tb-specs/ 下 TB06、TB09 各自 spec。

**TB06**：评估 OpenSquilla（github.com/opensquilla/opensquilla）SquillaRouter 四通道冷启动路由（准入过滤/需求构造/风险定价/能力匹配 + LightGBM），对论文流水线 digest/授粉环节做成本优化设计。clone 后读 src/opensquilla/engine/router_decision.py + router_tiers.py + route_plan.py，输出评估报告 docs/opensquilla-评估-2026-09-01.md（拆解 + ≥3 可落地借鉴点）。

**TB09**：对第九批 599 份 spec 复核：查 R/A/K 线是否仍有泛词误分（rf/signal/训练等）、desc 空档、编号连续性；输出待修正清单（0 则确认达标）。

**避坑铁律**：只写分析/防御，不写攻击代码；不引新依赖；中文输出；推 trae/agent-53 分支。

**重要单**：TB06 优先（OpenSquilla 是 TokenRhythm 自家开源 harness，直接关系成本优化）。

---

**交付**：2 单处理完毕，推 trae/agent-53 分支，给出执行清单。阻塞不硬做，写清原因返回。
