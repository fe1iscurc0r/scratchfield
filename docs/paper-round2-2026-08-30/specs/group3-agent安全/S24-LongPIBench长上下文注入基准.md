# S24 LongPIBench 长上下文注入基准

> 来源分组：group3-agent安全（第四批）

【SPEC】安全评测建立长上下文提示注入基准：LongPIBench 4 场景数千-数万 token，验证现有防御被高估。验收=基准 + 评测。
【工单】①读 round3 digest-g3 LongPIBench 授粉点 ②设计基准场景 ③实现 ④评测 NEKO。
【提示词】你是注入评测 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g3-2026-08-31.md 中 LongPIBench（2608.28411）授粉点（长上下文注入：简单启发式即可绕过 SOTA 防御），为 NEKO 建立长上下文注入基准：构造数千-token 场景评估现有防御真实成功率。输出 docs/longpi-bench-方案.md + 评测脚本。验收：≥4 场景 + 防御真实成功率报告。推 trae/agent-s24 分支。
