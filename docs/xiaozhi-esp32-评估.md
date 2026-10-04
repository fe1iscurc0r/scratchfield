# W68-01 xiaozhi-esp32 评估（MCP 聊天机器人）

> 上游：github.com/78/xiaozhi-esp32 · MIT · 29548★ · C++ · 2026-09-02 活跃
> 落点：docs/xiaozhi-esp32-评估.md · 勘察/评估

## 1. 项目定位

小智 AI 聊天机器人：作为**语音交互入口**，借助 Qwen/DeepSeek 等大模型，通过 **MCP 协议**实现多终端控制。ESP32 端侧跑离线唤醒 + 语音采集/播放，云端跑 ASR/LLM/TTS，MCP 作为「设备控制 + 云端能力扩展」的统一协议。

## 2. 架构拆解

- **固件栈**：ESP-IDF v6.0+，171 变体（ESP32 / C3 / C5 / C6 / S3 / P4），ESP-SR 2.4.7 离线唤醒（可自定义唤醒词）。
- **通信**：双 transport —— WebSocket 与 MQTT+UDP；MQTT/BluFi 加密封装迁移到 PSA Crypto。
- **音频**：Opus 流式（流式 ASR+LLM+TTS 与 Realtime 端到端语音模型），AEC 硬件支持全双工。
- **MCP 分层**：设备侧 MCP（Speaker/LED/Servo/GPIO 等外设控制）+ 云端 MCP（智能家居/PC 桌面/知识检索/邮件等）。
- **其它**：扬声器识别（3D-Speaker）、OLED/LCD 表情、摄像头视觉输入、电池/电源管理、39 语言。

## 3. 与本仓对照

| 维度 | xiaozhi-esp32 | 本仓 |
|---|---|---|
| 形态 | ESP32 语音聊天机器人 | NEKO 桌宠 + ESP32-S3 端侧 |
| MCP | 设备侧 + 云端双层 MCP | voice-MCP 封装（docs/voice-mcp-*） |
| 语音 | 流式 Opus + AEC 全双工 | voice 栈 |
| 维护 | 171 变体、C++ 大工程 | 轻量定制 |

## 4. 可落地借鉴点（≥3）

1. **设备侧 MCP 分层**：把 GPIO/外设抽象为 MCP tool、端侧作为 MCP server 供 LLM 调用——我们的 voice-MCP 可参考「设备侧 MCP + 云端 MCP」双层设计，把外设控制与云端能力解耦。
2. **双 transport + PSA Crypto**：WebSocket 与 MQTT/UDP 双通道 + 加密迁移到 PSA Crypto，对我们 ESP32-S3 语音链路的传输选型与加密有直接参考。
3. **Opus 流式音频流水线**：流式 ASR+LLM+TTS + AEC 全双工，可作为 voice-MCP 音频链路的对照基线。

## 5. 许可裁定 + 结论

- **许可**：MIT → 可借鉴代码。
- **复用 vs 参考结论**：**参考为主，不建议整体迁入**。171 变体的 C++ 大工程维护成本高，与本仓轻量定制定位不符；但「设备侧/云端 MCP 双层」「双 transport」「Opus 流式」三点设计值得抽取到我们的 ESP32-S3 语音助手。是否迁入：否（借鉴设计，不抄代码）。
