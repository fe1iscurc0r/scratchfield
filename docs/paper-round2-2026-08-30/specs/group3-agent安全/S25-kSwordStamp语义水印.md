# S25 k-SwordStamp 语义水印

> 来源分组：group3-agent安全（第四批）

【SPEC】rf_brain 评估语义水印：k-SwordStamp 子句级顺序鲁棒检测，对抗重排/改写/重分割。验收=评估报告 + 原型。
【工单】①读 round3 digest-g3 k-SwordStamp 授粉点 ②分析水印机制 ③评估频谱数据适配 ④原型。
【提示词】你是数据水印 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g3-2026-08-31.md 中 k-SwordStamp（2608.27666）授粉点（嵌入位移攻击 EDA：重排/改写/重分割语义水印，攻击成功率压至 10.8-39.7%），评估语义水印对频谱/传感数据完整性验证的适配。输出 docs/kswordstamp-评估.md + 最小原型。验收：含水印机制对比 + 频谱数据适配建议。推 trae/agent-s25 分支。
