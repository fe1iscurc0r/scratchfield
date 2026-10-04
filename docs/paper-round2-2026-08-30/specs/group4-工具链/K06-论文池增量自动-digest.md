# K06 论文池增量自动 digest

> 来源分组：group4-工具链

【SPEC】每日增量 cron 补全量 digest 轮（不只周度摘要）；验收=cron 更新+试跑。
【工单】①看现有 cron（ad17cd9d341f）②补 digest 环节③试跑。
【提示词】你是 cron 运维 AI。更新论文流水线 cron：现有 ad17cd9d341f 每天 2:00 只做趋势摘要，补上"新论文≥N 篇时触发 digest"逻辑（参考 paper-digest-pipeline skill 分块模式）。验收：prompt 更新 + 触发条件明确。
