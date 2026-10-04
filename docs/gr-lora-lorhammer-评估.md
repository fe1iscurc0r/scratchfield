# gr-lora_sdr + lorhammer 评估（W71-08）

> 上游：martynvandijke/gr-lora_sdr（8★，Python）+ itk.fr/lorhammer（9★，Go）｜ <https://gitlab.com/itk.fr/lorhammer>
> 许可：gr-lora_sdr GPL-3.0（仅参考设计）；lorhammer 许可待核

## 1. 项目定位

- **gr-lora_sdr**：GNU Radio 全软件 LoRa 调制解调——PHY 层含前导同步、解扩、解调，软件化替代 SX127x。
- **lorhammer**：LoRaWAN 网络服务器压力测试工具，模拟大量节点上行压测服务器。

## 2. 架构拆解

- gr-lora_sdr：GNU Radio 流图 + Python 实现 LoRa PHY（chirp 解扩、SF 反解、CRC）。
- lorhammer：并发模拟端节点 → 打 LoRaWAN 服务器，测吞吐/丢包/时延。

## 3. 与本仓对照

| 维度 | gr-lora_sdr | 本仓 |
|---|---|---|
| LoRa PHY | 软件（可改参数） | 硬件 SX1278（LoRaCanary）|

**「软 PHY vs 硬 PHY」结论（验收项）**：软 PHY 胜在「可观察每个解调步骤（同步/解扩/CRC）」便于
调试与协议研究；硬 PHY 胜在「低功耗/低成本/端侧可用」。**软 PHY 作调试/验证台，硬 PHY 作产品端侧**。

## 4. 可落地借鉴点（≥3）

1. **软件 LoRa PHY 作链路调试台**：可单步观察同步/解扩/CRC，用于 LoRaCanary 帧丢失/误码的定位
   （对照硬件行为定位是 PHY 还是上层问题）。
2. **lorhammer 压测范式**：模拟大量节点上行的压测，可借鉴为 LoRa mesh 网关/服务器的容量验证工具。
3. **PHY 层「可观察性」设计**：软件 PHY 暴露每个解调阶段的中间量，借鉴到硬件 LoRa 的调试接口设计。

## 5. 许可裁定

gr-lora_sdr GPL-3.0——只参考设计；lorhammer 许可待核，未核前不融合。

## 6. 结论

设计参考级（验证台价值高）。建议：软 PHY 验证台用于 LoRaCanary 调试；硬 PHY 维持产品端侧。
