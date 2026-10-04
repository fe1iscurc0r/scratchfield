# PF085 Agent 安全从记忆投毒升级为\"记忆/技能双注入 + 流治理\"

> 批次：第十四期 · 授粉专项批 [独立新立]
> 来源：日报趋势（2026-08-26）
> 源论文：(跨来源/趋势授粉)
> 落点：AAgent
> 授粉点：Agent 安全从记忆投毒升级为\"记忆/技能双注入 + 流治理\"：InjecMEM 证明只需一次交互即可定向污染记忆系统后续检索输出（retriever-agnostic anchor + gradient-searched 命令）；SkillBloat 把技能文件当作\"可信指令通道\"做 token 放大攻击（平均 5.4-10.1x 资源消耗）；AgentFlow 提出流策略语言（数据能流向哪些工具/边界）把 AgentDoj

【SPEC】AAgent 落地授粉：Agent 安全从记忆投毒升级为\"记忆/技能双注入 + 流治理\"。把论文机制/趋势迁移到 scratchpad 技术栈（SDR/ESP32/材料/Agent/NEKO），出方案或原型。
【验收】方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读源论文摘要（arxiv_corpus.jsonl 中对应 ID）②拆解可迁移机制 ③设计/实现落地 ④评估。中文注释/输出，推 trae/agent 对应分支。
