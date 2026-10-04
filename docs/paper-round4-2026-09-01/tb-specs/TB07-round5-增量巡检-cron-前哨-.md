# TB07 round5 增量巡检（cron 前哨）

> 批次：第十三期 · 专项工单
> 组装：沈遥（Hermes）2026-09-01

【SPEC】巡检 arXiv 增量：跑 fetch_arxiv.py，确认是否已有 round5 新论文；有则触发新一批（路径 A），无则输出"无新增"报告并保持待命。

【验收】输出增量结果（新增 N 篇 / 0 新增）+ 是否有下一批原料。

【工单】① cd ~/research/papers && python3 fetch_arxiv.py ② 对比 processed_ids ③ 输出增量结论。
