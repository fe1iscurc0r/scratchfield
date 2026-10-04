# R38 OTA-ELM 信号分类器（ESP32-S3）

> 来源分组：group1-无线电

【SPEC】OTA-ELM 零梯度轻量推理落 ESP32-S3+SX1278：PC numpy 伪逆训练→LUT 激活→节点推理；验收=训练骨架+定点化要点+勘察工单。
【工单】①numpy 伪逆训练最小验证（~50 行）②LUT 表生成③int8 定点化要点④勘察工单派 Trae。
【提示词】你是嵌入式 ML AI。实现 OTA-ELM 信号分类：读 /home/ubuntu/github_haul/POLLINATION-2026-08-29-round10.md，用 numpy 实现 ELM 训练（随机隐层投影+输出层伪逆闭式解），生成 LUT 激活表，输出 int8 定点化要点。验收：训练脚本可跑 + 合成信号分类准确率 + 定点化文档。
