# meshtastic_sdr 评估（W71-02）

> 上游：crankylinuxuser/meshtastic_sdr（GitLab，79★，Python）｜ <https://gitlab.com/crankylinuxuser/meshtastic_sdr>
> 许可：GPL（GNU Radio 生态，仅参考设计）

## 1. 项目定位

用 **GNU Radio 流图**实现的全双工 Meshtastic LoRa 收发栈（RX+TX），把 LoRa 调制解调从硬件
SX127x/SX126x 芯片「软件化」到 SDR（如 RTL-SDR / HackRF / ADALM-PLUTO）。

## 2. 架构拆解

- **GNU Radio 流图**：RF 前端 → 采样 → 软件 LoRa 解调/调制 → Meshtastic 帧封装。
- **全双工 RX+TX**：软收发一体，替代「硬件 LoRa 芯片」的角色。
- **与 Meshtastic 协议对接**：输出/输入 Meshtastic 帧，可直接接入现有 Meshtastic 网络。

## 3. 与本仓对照

| 维度 | meshtastic_sdr | 本仓 |
|---|---|---|
| LoRa PHY | 软件（SDR） | 硬件 SX1278（LoRaCanary/elrs）|
| 灵活性 | 参数可软件重配 | 受芯片寄存器约束 |
| 成本/功耗 | SDR 前端 + 主机 | MCU + LoRa 芯片（低功耗）|

**可行性结论（验收项）**：SDR 软件 LoRa 在「灵活实验/协议逆向/网关汇聚」场景可行；但**替代硬件
LoRa 在端侧不现实**（SDR 功耗/体积/成本远高于 SX127x），定位为「软件化验证 + 网关侧」，非端侧替换。

## 4. 可落地借鉴点（≥3）

1. **软件 LoRa PHY 作协议验证床**：用 GNU Radio 软解调逆向/验证 LoRa 参数（SF/BW/CR）与帧格式，
   为 LoRaCanary 物理层调参提供可快速迭代的软件环境（不烧真机）。
2. **SDR Meshtastic 网关**：多频段/多 SF 同时接收的软网关，可做 LoRa mesh 的汇聚/监听节点。
3. **「软 PHY 参数化」设计**：把 LoRa 调制参数做成软件可重配，借鉴到射频前端的参数抽象层。

## 5. 许可裁定

GPL——**只参考设计不融合**；软解调流程/流图结构可参考，代码不并入。

## 6. 结论

可借鉴（验证/网关级）。建议：立项「SDR 软件 LoRa 验证台」用于 LoRaCanary 链路调试与协议分析；
端侧仍走硬件 LoRa。
