# TB06 OpenSquilla 路由评估（TokenRhythm harness）

> 批次：第十三期 · 专项工单
> 组装：沈遥（Hermes）2026-09-01

【SPEC】评估 OpenSquilla（github.com/opensquilla/opensquilla）的 SquillaRouter 四通道冷启动路由（准入过滤/需求构造/风险定价/能力匹配 + LightGBM），对论文流水线 digest/授粉环节做成本优化设计；输出评估报告。

【验收】报告含：路由机制拆解 + 对论文流水线的可落地借鉴点 ≥3 + 原型设计（可选）；纯分析不写攻击代码。

【工单】① clone opensquilla ② 读 src/opensquilla/engine/router_decision.py + router_tiers.py + route_plan.py ③ 拆解路由机制 ④ 输出评估报告 docs/opensquilla-评估-2026-09-01.md。
