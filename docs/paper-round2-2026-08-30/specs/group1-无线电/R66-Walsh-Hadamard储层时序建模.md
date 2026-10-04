# R66 Walsh-Hadamard 储层→嵌入式时序建模

> 来源分组：group1-无线电（第四批）

【SPEC】ESP32/LoRa 增加 Walsh-Hadamard 储层时序建模：无乘法正交算子，LoRa 信道状态预测/干扰检测轻量前端。验收=方案 + 原型。
【工单】①读 round3 digest-g1b Hadamard RC 授粉点 ②设计储层 ③实现 ④评估。
【提示词】你是嵌入式时序 AI。读 /home/ubuntu/research/papers/round3/digests/digest-g1b-2026-08-31.md 中 Walsh-Hadamard 储层（2608.28295）授粉点（无乘法器、结构正交、50× 加速、4 数量级内存缩减），为 ESP32/LoRa 实现时序建模前端：Walsh-Hadamard 正交算子做信道状态预测/干扰检测特征提取。输出方案 + numpy 原型。验收：预测精度较基线 ≥80%，无乘法指令（加法/移位实现）。推 trae/agent-r66 分支。
