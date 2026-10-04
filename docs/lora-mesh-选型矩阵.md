# W95-05 · LoRa mesh 固件层选型对照表

**任务**：汇总已授粉/已勘察 LoRa mesh 全栈做选型矩阵 + 天线云台 LoRa433 遥控推荐链路
**工单**：第三十四期扩轮卷95 · W95-05【评估】
**数据来源**：本轮克隆实测（D:\wo34-recon）+ 仓内既有授粉报告（Batch3-lora-radio、reticulum-mesh、授粉轮扩轮 2026-09-07）

---

## 1. 选型矩阵（≥6 项）

| 项目 | 许可 | 活跃度（核验日） | 协议/频段 | ESP32 适配 | 形态 | 与本仓关系 |
|---|---|---|---|---|---|---|
| meshtastic/firmware | GPL-3.0 | 2026-09-07 push | 自有 mesh（LoRa 433/868/915…Region 表） | 全系（ESP32/S3/C3…） | 完整 mesh 网络栈 | **正主**；哨兵可作外挂传感模块 |
| zjs81/meshcore-open | MIT | 已授粉（Batch3） | MeshCore 协议客户端 | 客户端侧 | 协议栈/客户端 | 协议参照；MIT 可融合 |
| pe1hvh/meshcore-gui | MIT | 2026-09-06 push | MeshCore（串口/BLE） | 主机侧 | 桌面/无头运维台 | 形态参照（W95-03） |
| luciobaiocchi/heard | Apache-2.0 | 2026-08-08 | 极简轮询+中继（LoRa） | ESP32+GPS+e-ink | 群组安全 mesh | **FITL 模拟器方法论首选**（W95-02） |
| hermes-gadget/SigurdOS-tdeck | GPL-3.0 | Beta testing | MeshCore（T-Deck 单机） | ESP32-S3+SX1262 | 单设备消息固件 | host 单测/fuzz 组织参照（W95-04） |
| markqvist/Reticulum | Reticulum License（NOASSERTION，含 AI 训练禁令条款） | 已授粉（reticulum 报告） | 加密 mesh（LoRa/包电台/WiFi） | 有（RNode） | 抗毁网络栈 | **只读谨慎**：禁令条款宽，数据流落 AI 管线有合规风险 |
| MeshTNC / lora-mesh / EasySkyMesh | 待核（本轮未克隆） | 待核 | 待核 | 待核 | 待核 | 下轮补勘察 |

注：EasySkyMesh 前轮判「暂缓」；MeshTNC/lora-mesh 在仓内报告无许可记录，**不进入推荐链路**。

## 2. 天线云台 LoRa433 遥控推荐链路

目标：云台控制指令低时延下行 + 哨兵观测上行，433MHz，无蜂窝依赖。

**推荐（三层组合）**：
1. **链路层**：自研 LoRaCanary 帧（已有 A/B 回滚 + 自检）保持控制信道极简；
   不直接上 meshtastic（其 mesh 路由对「点对点遥控」是过度设计，且 GPL 固件独立件
   与云台控制代码耦合不利）。
2. **组网层（可选升级）**：若未来多云台/多哨兵，接 **meshtastic 作为承载网**
   （哨兵/云台控制器作为其 Serial/Telemetry 外挂模块），GPL 义务留在固件独立仓。
3. **运维层**：lumo 面板 + meshcore-gui 形态的 headless 观测入口（W95-03 借鉴点 2）。

**不推荐**：Reticulum 作控制链路（许可禁令条款与 AI 管线冲突，见 reticulum 授粉报告）；
MeshCore 闭源固件作控制底座（不可审计）。

**与 Reticulum 的层位关系**：Reticulum 属「网络/传输层」候选（与 meshtastic 同层竞争），
本仓 LoRaCanary 属「链路/帧层」，lumo/ELN 属「应用层」——三层不冲突，
选型时按「控制信道自研、承载网可选 meshtastic、传输层排除 Reticulum」执行。

## 3. 433MHz 合规提醒（承接 W95-01）

- 中国 433 ISM 限功率/占空比；控制信道建议 ≤10dBm + 低占空比心跳。
- 发射侧上线前做功率/占空比实测记录（借鉴 SigurdOS release-evidence 做法）。

## 4. 执行清单

- [x] ≥6 项矩阵（7 行，含待核标注）
- [x] 天线云台推荐链路 + Reticulum 层位关系
- [ ] （下轮）MeshTNC / lora-mesh / EasySkyMesh 补勘察与许可核验
