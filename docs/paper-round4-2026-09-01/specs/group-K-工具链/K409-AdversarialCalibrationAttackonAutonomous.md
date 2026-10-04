# K409 Adversarial Calibration Attack on Autonomous Vehicles

> 来源分组：第九批（round4 新论文 2026-08-29/30/31 提交）
> 来源论文：2608.28778v1
> 落点：工具链
> 核心：**Adversarial Calibration Attack on Autonomous Vehicles** 识别出"在线标定更新"这一全新攻击平面：一次损坏的标定更新可跨感知→规划→控制持续传播。对多传感器融合系统（不只自动驾驶，也含任何依赖标定的机器人/无人平台）的安全设计有直接警示价值，攻防视角新颖且系统化。

【SPEC】工具链 增加/评估：Adversarial Calibration Attack on Autonomous Vehicles（来源 2608.28778v1）。
【验收】工具链 相关：方案文档落 docs/ 或原型 pytest 全绿 + 验收指标。
【工单】①读 round4 digest 中 2608.28778 对应条目（语料 arxiv_corpus.jsonl 中 2608.28778v1）②分析机制 ③设计/实现 ④评估。中文注释/输出，推 trae/agent 对应分支。
