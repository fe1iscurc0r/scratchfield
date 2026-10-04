# agent-78 评估报告 + 执行清单（GitLab 2 + awesome 8 + HF 模型 5 = 15 项）

> 智能体 78 · 勘察/评估 · 15 项（W77-01~15）

## GitLab 侧（W77-01~02）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W77-01 | mistborn | Shell | 自托管私有云平台 + WebUI | ⚠️ 参考级：自托管服务管理，离主线 |
| W77-02 | ase | Python | 原子模拟环境（DFT/MD/结构优化） | ✅ 借鉴：原子模拟库，对接陆墨材料线 |

## awesome 清单侧（W77-03~10）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W77-03 | TempestSDR | 待核 | TEMPEST 电磁侧信道重建显示器 | ✅ 借鉴：侧信道重建，对照 ESP32 侧信道勘察（安全类只写防御） |
| W77-04 | btlejack | 待核 | BLE 嗅探/劫持/干扰瑞士军刀 | ✅ 借鉴：BLE 分析，安全类只写防御 |
| W77-05 | LAF | 待核 | LoRaWAN 报文审计/构造/破解 | ✅ 借鉴：LoRaWAN 报文解析，安全类只写防御 |
| W77-06 | dji_droneid | 待核 | 被动解码 DJI DroneID | ✅ 借鉴：被动无人机 ID 监测，对接射频感知 |
| W77-07 | iridium-toolkit/JAERO/dumpvdl2 | 待核 | 铱星/Inmarsat ACARS/VDL2 解码 | ✅ 借鉴：卫星/航空数据链解码，对照 rf_brain 解调链 |
| W77-08 | sdrtrunk | 待核 | 集群对讲（P25/DMR 等）解码 | ✅ 借鉴：集群协议解码，对照 rf_brain decoders |
| W77-09 | dsame/FruityMesh/disaster-radio | 待核 | 应急解码 + BLE mesh + 灾备 | ✅ 借鉴：应急通信 mesh，对照 LoRaCanary |
| W77-10 | MatSciBERT | 待核 | 材料文献挖掘 | ✅ 借鉴：材料文献挖掘，对接陆墨 |

## HF 模型侧（W77-11~15）

| 编号 | 项目 | 许可 | 定位 | 借鉴点 / 结论 |
|---|---|---|---|---|
| W77-11 | Qwen3-Embedding-0.6B | 待核 | 统一 embedding 主干 | ✅ 借鉴：0.6B embedding 主干，对照 rag 检索引擎 |
| W77-12 | chronos-bolt-tiny | 待核 | 时序预测 | ✅ 借鉴：时序预测，对接 rf_brain 频谱时序 |
| W77-13 | Agents-A1-4B | 待核 | 本地 agent 推理模型 | ✅ 借鉴：本地 agent 模型，对照 K40 端上推理 |
| W77-14 | Kokoro-82M + faster-whisper-tiny | 待核 | 端上 TTS/ASR | ✅ 借鉴：端上 TTS/ASR，对照 voice-MCP |
| W77-15 | ECAPA 声纹 + GT4SD 化学 T5 | 待核 | 声纹识别 + 化学预测 | ✅ 借鉴：声纹 + 化学预测，对照陆墨/声纹 |

## 执行清单

- **完成**：15/15 逐项评估。
- **许可**：多数待核（未逐一实拉 license）。
- **安全类**：W77-03/04/05（侧信道/BLE/LoRaWAN）只写防御。
- **高价值**：sdrtrunk（集群解码）、Qwen3-Embedding（embedding 主干）、Kokoro/faster-whisper（端上 TTS/ASR）三点最可落地。
