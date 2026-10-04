# 升级项目组 2-2：无线电/射频线（R49-R52）— SPEC·工单·提示词合集

> 生成：2026-08-31 · 实验田维护者 · 来源：二次授粉（44 digest + 日报 + 交叉审查）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可直接丢给执行 AI
> 优先级：P0=立即 / P1=1-2 周

---

## R49 Agentic 主动学习频谱异常筛选
【SPEC】rf_brain 增加 Agentic 主动学习管线：隔离森林→频谱嵌入向量排序候选，多模态 LLM 评审异常，低 SNR 高效筛选。验收=原型 + 候选筛选效率对比。
【工单】①读 digest-g6-2b Agentic 主动学习授粉点 ②设计隔离森林频谱嵌入 ③实现筛选管线 ④对比全量扫描。
【提示词】你是频谱异常检测 AI。读 digest-g6-2b-2026-08-30.md Agentic 主动学习授粉点（隔离森林排序→LLM agent 迭代评审→共识过滤），为 rf_brain 实现低 SNR 频谱异常候选筛选：隔离森林对频谱嵌入向量排序 → 规则评审 → 输出候选列表供 Agent 深度分析。输出 mcpserver/rf_brain/spectrum_anomaly_agentic.py + 测试。验收：合成异常注入下候选命中率 ≥80%，筛选量较全量扫描降 ≥10×。

## R50 APC-RLNC Mesh 弹性路由（P0）
【SPEC】LoRaCanary 增加分层网络编码弹性路由：承接 SPEC-20 v1.6 弱链路增强（EWMA 分组 + XOR 冗余），APC-RLNC 分层编码到 Mesh。验收=方案 + 原型 + 与单跳对比。
【工单】①读 digest-g8-3a APC-RLNC 授粉点 ②结合 v1.6 link_reliability.py 现状 ③设计分层编码 ④原型模拟。
【提示词】你是网络编码 AI。读 digest-g8-3a-2026-08-30.md APC-RLNC 授粉点 + 现有 tools/link_reliability.py（SPEC-20 v1.6 已验 EWMA+XOR），为 LoRaCanary 设计 Mesh 弹性路由：APC-RLNC 分层网络编码（按链路质量分组编码冗余），断电重同步。输出方案 docs/loracanary-rlnc-mesh-方案.md + numpy 原型。验收：弱链路（PER 30%）下交付率较无编码提升 ≥50%，不破坏 v1/v1.5 帧兼容。

## R51 计算型射频前传
【SPEC】ESP32-S3 增加计算型射频前传原型：波域权重映射 → 可调滤波器组替代部分基带计算，极低功耗异常检测。验收=方案 + 原型。
【工单】①读 digest-g8-3b 波域权重授粉点 ②设计滤波器组映射 ③实现 ④评估功耗。
【提示词】你是嵌入式射频 AI。读 digest-g8-3b-2026-08-30.md 波域权重映射授粉点（超表面思想→可调滤波器组替代基带计算），为 ESP32+LoRa 设计计算型射频前传：原始 ADC 数据→轻量特征映射→模拟域/前端线性分类→极低功耗异常检测。输出方案 + numpy 原型（模拟滤波器组分类 vs 全基带 FFT 分类）。验收：分类精度损失 ≤10%，计算量/功耗估算降 ≥3×。

## R52 IDSD 深度展开替代 CFAR（P0）
【SPEC】rf_brain 增加深度展开信号分解：IDSD 无窄带假设自适应分量迭代提取，替代固定阈值 CFAR；Nesterov 加速。验收=模块 + 对比测试。
【工单】①读 digest-g8-3b IDSD 授粉点 ②设计深度展开结构 ③实现 ④与 CFAR 对比。
【提示词】你是信号分解 AI。读 digest-g8-3b-2026-08-30.md IDSD 授粉点（无窄带假设+自适应分量迭代提取替代固定阈值 CFAR），为 rf_brain 实现深度展开信号分解：迭代软阈值展开网络分离信号/干扰分量，Nesterov 加速收敛。输出 mcpserver/rf_brain/deep_unfold_decompose.py + 测试。验收：合成干扰场景分量分离精度较 CFAR 提升 ≥20%，ESP32 毫秒级窗口可行（参数量 <100K）。
