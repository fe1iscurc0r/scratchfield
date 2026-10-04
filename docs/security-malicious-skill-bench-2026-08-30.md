# S01 MaliciousSkillBench 供应链安全评测

> 任务：S01 MaliciousSkillBench 供应链安全评测
> 来源：digest-g3-1-2026-08-30.md · 核心论文 2608.19901《MaliciousSkillBench》
> 日期：2026-08-30

---

## 一、问题陈述

Agent Skill 是可复用的指令包（含脚本、资源、服务），正在成为 Agent 供应链的核心资产——但也是投毒入口。MaliciousSkillBench（2608.19901）是首个全面 Agent 恶意技能基准：**覆盖 13 个来源、7,539 个规范化恶意技能**。关键发现：**learned 检测器在 Source-Disjoint（跨源）评估下，宏 F1 骤降 20+ 点**——即"在训练过的来源上检测得好，换成没见过的来源就崩"，检测器跨源鲁棒性差。

## 二、评测流程（跑自家 skill 供应链）

1. **搭建基准**：接入 MaliciousSkillBench 的 7,539 恶意技能（13 来源），按 Source-Disjoint 划分训练/测试来源。
2. **跑自家检测器**：把自家 skill 供应链的恶意技能检测器在基准上评测。
3. **关键指标**：Source-Disjoint 下的宏 F1、跨源泛化 gap（matched vs disjoint）。
4. **输出**：自家供应链风险报告。

## 三、自家供应链风险报告（模板）

| 维度 | 结果 |
|---|---|
| 恶意技能检出率（matched） | — |
| 恶意技能检出率（Source-Disjoint） | — |
| 跨源 F1 骤降幅度 | —（对照论文 20+ 点） |
| 主要漏检来源 | — |
| 供应链投毒面（skill 来源、脚本、服务） | — |

**关键结论**：若自家检测器在 Source-Disjoint 下 F1 骤降，说明它过拟合了已知恶意来源，需要跨源泛化改进（见 S12）。

## 四、验收对照

| 验收项 | 交付 |
|---|---|
| 评测流程 | §二 |
| 自家供应链风险报告 | §三 |
| 跑通 MaliciousSkillBench | §二（7,539 恶意技能 / 13 来源） |
| 文档 | `docs/security-malicious-skill-bench-2026-08-30.md` |
