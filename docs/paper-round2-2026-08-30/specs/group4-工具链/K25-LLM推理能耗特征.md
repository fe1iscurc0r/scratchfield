# K25 LLM 推理能耗特征→端侧预算

> 来源分组：group4-工具链（第四批）

【SPEC】NEKO 评估推理能耗特征：请求/token 能耗量化，端侧推理预算。验收=评估报告。
【工单】①读 round3 digest-g7 能耗授粉点 ②分析能耗模型 ③评估 NEKO 适配 ④出报告。
【提示词】你是能耗建模 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g7-2026-08-31.md 中 LLM 推理能耗（2608.28044）授粉点（请求/token 能耗特征），评估 NEKO 端侧推理的能耗预算模型。输出 docs/llm-inference-energy-评估.md。验收：含能耗模型 + 预算建议。推 trae/agent-k25 分支。
