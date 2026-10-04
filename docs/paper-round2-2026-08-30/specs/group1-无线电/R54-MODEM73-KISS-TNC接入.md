# R54 MODEM73 KISS TNC 软件调制解调器（日报）

> 来源分组：group1-无线电（第二批）

【SPEC】IC-705 数字模式新通道：MODEM73（OFDM/ROBUST/MFSK，任意 2400Hz 电台+声卡）接入 radio_suite，Hamlib/rigctl PTT 集成。验收=接入方案 + 可运行链路。
【工单】①查 MODEM73 仓库（RFnexus/modem73）②设计 radio_suite 接入 ③实现 KISS TNC 桥 ④实测。
【提示词】你是无线电软件 AI。接入 MODEM73 KISS TNC：查 github.com/RFnexus/modem73（开源软件调制解调器，任意 2400Hz 带宽电台+声卡，OFDM/ROBUST/MFSK，支持 Hamlib/rigctl），为 radio_suite 设计接入方案：声卡 I/Q → MODEM73 解调 → KISS 帧 → APRS/数据上报。输出方案 + 桥接脚本。验收：方案含 IC-705 音频接线/rigctl 配置；桥接脚本可跑通模拟音频。推 trae/agent-r54 分支。
