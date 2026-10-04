# S17 Wrong-Physics 后门

> 来源分组：group3-agent安全（第三批）

【SPEC】安全评测增加 Wrong-Physics 后门：神经 PDE 算子错误物理后门，标签一致检测不出。验收=基准 + 检测方案。
【工单】①读 digest-g1-2 2608.20439 条目 ②复现后门 ③设计检测 ④出基准。
【提示词】你是 AI4Science 安全 AI。读 digest-g1-2-2026-08-30.md 中 2608.20439v1（Wrong-Physics Backdoor：神经 PDE 算子错误物理后门，标签一致性不足以检测），为 rf_brain/陆墨的物理模型建立后门基准：构造错误物理后门样本 + 检测方法（物理一致性校验）。输出 docs/wrong-physics-backdoor-基准.md + 检测原型。验收：含后门构造 + ≥2 种检测方法。推 trae/agent-s17 分支。
