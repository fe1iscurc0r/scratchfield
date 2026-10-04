# R70 AsymSpec 上下文非对称投机解码

> 来源分组：group1-无线电（第五批）

【SPEC】NEKO/推理 增加/评估：AsymSpec 上下文非对称投机解码。来源论文 2608.26004。验收=原型 + 测试；推理成本降 ≥20%，质量不降。
【工单】①读 round2 digest 中 2608.26004 对应条目 ②分析机制 ③设计/实现 ④评估。
【提示词】你是NEKO/推理方向 AI。读 /home/ubuntu/research/papers/round2/digests/ 中论文 2608.26004 相关条目（或语料 arxiv_corpus.jsonl 中 2608.26004），为 NEKO Agent 推理实现上下文非对称投机解码：不同上下文段用不同 draft 策略，降本不降质。输出按 spec 验收。推 trae/agent-r70 分支。
