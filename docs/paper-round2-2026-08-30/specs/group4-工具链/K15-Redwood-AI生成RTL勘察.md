# K15 Redwood AI 生成 RTL 勘察

> 来源分组：group4-工具链（第二批）

【SPEC】勘察 Redwood 全 AI 设计（规范→RTL→固件→内核两周 tape-out，3.4× 瓦特）对定制无线电 SoC 的启示。验收=勘察报告。
【工单】①查 Redwood 论文/项目（2608.26418v1）②分析 RTL 生成管线 ③出无线电 SoC 勘察。
【提示词】你是 EDA 勘察 AI。读 digest-gx-5c-2026-08-30.md Redwood 授粉点 + 论文 2608.26418v1（全 AI 设计：规范→RTL→固件→内核两周完成，生产级 EDA，3.4× 瓦特增益），勘察 AI 生成 RTL 对定制无线电 SoC/SDR 基带加速器的可行性。输出 docs/ai-generated-rtl-radio-勘察.md：管线拆解 + 无线电场景适配度 + 自建门槛评估。验收：含 3 条可落地借鉴点。推 trae/agent-k15 分支。
