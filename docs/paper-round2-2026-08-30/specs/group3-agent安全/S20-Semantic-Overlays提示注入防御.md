# S20 Semantic Overlays 提示注入防御

> 来源分组：group3-agent安全（第三批）

【SPEC】NEKO 增加 Semantic Overlays 提示注入防御：token 标注层缓解注入。验收=方案 + 原型。
【工单】①读 digest-g1-3 2608.23873 条目 ②设计标注层 ③原型 ④评估。
【提示词】你是注入防御 AI。读 digest-g1-3-2026-08-30.md 中 2608.23873v1（Semantic Overlays: Mitigating Prompt Injection with Annotated Tokens），为 NEKO 实现 token 标注层防御：输入 token 标注来源/信任级别，注入内容降权。输出方案 + 原型（标注过滤管线）。验收：注入攻击成功率下降 ≥50%，正常指令通过率 ≥95%。推 trae/agent-s20 分支。
