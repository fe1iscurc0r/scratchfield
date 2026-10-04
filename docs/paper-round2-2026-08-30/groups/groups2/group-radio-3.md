# 升级项目组 2-3：无线电/日报线（R53-R54）+ 材料线（M23）+ Agent 线（A22/A23/A26）

> 生成：2026-08-31 · 实验田维护者 · 来源：二次授粉（论文 digest + 日报 + 交叉审查）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可直接丢给执行 AI
> 优先级：P1=1-2 周 / P2=观察

---

## R53 ExpressLRS 接收机授粉（日报）
【SPEC】勘察 OpenRX/ExpressLRS 超远距离 LoRa 链路设计（100km+ @1W，ESP32-C3+SX1281/LR1121）对 LoRaCanary 的借鉴。验收=勘察报告。
【工单】①查 OpenRX 仓库（OpenDrone-hw/OpenRX）②分析 ELRS 4.0 链路机制 ③出借鉴建议。
【提示词】你是射频勘察 AI。勘察 ExpressLRS 超远距离 LoRa 链路：查 github.com/OpenDrone-hw/OpenRX（ESP32-C3 + SX1281/LR1121 开源接收机），分析 ELRS 4.0 的 100km+ 链路技术（扩频因子/占空比/频偏估计），输出 docs/elrs-openrx-勘察.md，标注对 LoRaCanary 433MHz 链路的可借鉴点（≥3 条）。验收：含链路预算分析 + 借鉴建议清单。

## R54 MODEM73 KISS TNC 软件调制解调器（日报）
【SPEC】IC-705 数字模式新通道：MODEM73（OFDM/ROBUST/MFSK，任意 2400Hz 电台+声卡）接入 radio_suite，Hamlib/rigctl PTT 集成。验收=接入方案 + 可运行链路。
【工单】①查 MODEM73 仓库（RFnexus/modem73）②设计 radio_suite 接入 ③实现 KISS TNC 桥 ④实测。
【提示词】你是无线电软件 AI。接入 MODEM73 KISS TNC：查 github.com/RFnexus/modem73（开源软件调制解调器，任意 2400Hz 带宽电台+声卡，OFDM/ROBUST/MFSK，支持 Hamlib/rigctl），为 radio_suite 设计接入方案：声卡 I/Q → MODEM73 解调 → KISS 帧 → APRS/数据上报。输出方案 + 桥接脚本。验收：方案含 IC-705 音频接线/rigctl 配置；桥接脚本可跑通模拟音频。

## M23 SF-Cluster 能量景观导航
【SPEC】陆墨增加能量景观导航工具：SF-Cluster 挫折模式感知 MSA 采样，识别生物质/水凝胶体系亚稳态与挫折区域，指导合成参数搜索。验收=工具 + 案例。
【工单】①读 digest-g7-1 SF-Cluster 授粉点 ②设计 MSA 采样策略 ③实现 ④案例验证。
【提示词】你是材料采样 AI。读 digest-g7-1-2026-08-30.md SF-Cluster 授粉点（挫折模式感知 MSA 采样识别能量景观亚稳态），为陆墨实现能量景观导航：聚类采样识别挫折区域（局部极小/能量壁垒），输出合成参数搜索建议。输出 tools/energy_landscape_nav.py + 测试。验收：二维势能面案例能定位 ≥3 个亚稳态，搜索效率较随机采样提升（步数降 ≥2×）。

## A22 UC-PSRO 通信退化鲁棒性
【SPEC】NEKO 多 Agent 增加通信退化课程训练：通信 dropout 下协作鲁棒性（35%→62% 参考）。验收=方案 + 原型。
【工单】①读 digest-g2-4 UC-PSRO 授粉点 ②设计通信退化课程 ③原型 ④评估。
【提示词】你是多 Agent 协作 AI。读 digest-g2-4-2026-08-30.md UC-PSRO 授粉点（通信 dropout 课程下任务完成率 35%→62%），为 NEKO 多 Agent 设计通信退化鲁棒训练：通信带宽/丢包渐进退化课程，Agent 学习降级协作策略。输出方案 + 最小原型（消息丢包模拟）。验收：丢包 50% 时任务成功率较无课程提升 ≥20%。

## A23 传感器不确定性注入
【SPEC】rf_brain/NEKO 增加传感器不确定性注入框架：物理参数 nuisance→代理模型→解析边缘化，Agent 数字孪生不确定性传递。验收=框架 + 演示。
【工单】①读 digest-g6-1 beam surrogate 授粉点 ②设计不确定性注入 ③实现 ④演示。
【提示词】你是不确定性建模 AI。读 digest-g6-1-2026-08-30.md CMB beam surrogate 授粉点（beam 参数当 nuisance→代理模型降维→解析边缘化=传感器不确定性注入标准流程），为 rf_brain 实现：将频谱感知传感器参数（增益/噪声底/频偏）作为 nuisance 量，代理模型降维 + 边缘化，输出带不确定性的感知结果。输出 mcpserver/rf_brain/uncertainty_inject.py + 测试。验收：演示用例输出含置信区间的频谱感知结果。

## A26 DreamLedger 通信可靠性追踪
【SPEC】NEKO/LoRa 网关增加信用文件机制：Agent 间消息可信度记账，MQTT-SN 可靠性追踪。验收=方案 + 原型。
【工单】①读 digest-gx-4b DreamLedger 授粉点 ②设计信用文件 ③实现 ④评估。
【提示词】你是可靠性追踪 AI。读 digest-gx-4b-2026-08-30.md DreamLedger 授粉点（信用文件→Agent 通信可靠性追踪），为 LoRa 网关/NEKO 实现消息信用记账：每条消息按确认/超时记账，节点可信度滚动更新，低可信节点消息降级处理。输出 tools/message_ledger.py + 测试。验收：模拟丢包节点信用分正确下降，重路由决策生效。
