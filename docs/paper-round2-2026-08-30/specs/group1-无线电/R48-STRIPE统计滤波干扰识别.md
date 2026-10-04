# R48 STRIPE 统计滤波干扰识别

> 来源分组：group1-无线电（第二批）

【SPEC】rf_brain 增加 STRIPE 式统计滤波干扰识别：子带阈值+时域累积，FPGA 2377 LUT 约束映射嵌入式可行。验收=模块 + 对比测试。
【工单】①读 digest-g6-1 STRIPE 授粉点 ②设计子带统计滤波 ③实现 ④与现有 CFAR 对比。
【提示词】你是干扰识别 AI。读 digest-g6-1-2026-08-30.md STRIPE 授粉点（子带阈值+时域累积自动干扰识别，FPGA 2377 LUT），为 rf_brain 实现统计滤波干扰识别模块：子带能量阈值 + 时域累积去毛刺，输出干扰频段/时段标记。输出 mcpserver/rf_brain/rfi_statistical.py + 测试。验收：合成干扰场景识别率 ≥85%，误报率 ≤5%，资源估算适配 ESP32 级硬件。推 trae/agent-r48 分支。
