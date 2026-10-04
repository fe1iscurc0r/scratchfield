# A35 ReCache 工具 Agent KV 复用

> 来源分组：group3-agent安全（第五批）

【SPEC】NEKO/推理 增加/评估：ReCache 工具 Agent KV 复用。来源论文 2608.19662。验收=原型 + 测试；内存降 ≥50%，速度提升。
【工单】①读 round2 digest 中 2608.19662 对应条目 ②分析机制 ③设计/实现 ④评估。
【提示词】你是NEKO/推理方向 AI。读 /home/ubuntu/research/papers/round2/digests/ 中论文 2608.19662 相关条目（或语料 arxiv_corpus.jsonl 中 2608.19662），为 NEKO 实现 ReCache 工具增强 KV cache 复用（92% 内存降）。输出按 spec 验收。推 trae/agent-a35 分支。
