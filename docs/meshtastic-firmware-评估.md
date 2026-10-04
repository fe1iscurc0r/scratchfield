# W95-01 · Meshtastic firmware 勘察（LoRa mesh 固件层正主）

**上游**：meshtastic/firmware（8268★ · GPL-3.0 · 2026-09-07 活跃）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\meshtastic-firmware，depth-1）+ README/目录结构/源码布局阅读
**工单**：第三十四期扩轮卷95 · W95-01【评估】

---

## 1. 项目定位

LoRa mesh 开源固件的第一把交椅：面向长距离、低功耗、去中心化通信的官方设备固件，
支持文本消息、位置共享、遥测 over mesh。硬件面覆盖 ESP32 全系 + SX1262/SX1278/LLCC68
等射频前端，**含 EU_433 等地区表**，433MHz 业余/ISM 频段可直接用。
生态上配套官方 App（Android/iOS）、Python CLI、protobuf 配置协议，是「固件-配置-应用」
三层齐全的参照系。09-06 缺口「MeshCore 闭源、开源替代仍缺」的正解即此——它一直开源且最活跃。

## 2. 架构拆解（源码布局，depth-1 实测）

```
src/
├── mesh/          # 核心：MeshService / RadioInterface / 路由与中继（Router 系列）
├── modules/       # 插件式消息模块（TextMessage/Position/Telemetry/Serial…自注册）
├── concurrency/   # OSThread 协作式调度器（非抢占，单循环跑线程表）
├── protobufs/     # nanopb 生成的消息/配置 schema（meshtastic/*.pb.*）
├── gps/ graphics/ input/ motion/ power/ security/ serialization/
├── nimble/        # BLE 协议栈适配
├── mqtt/          # 公网桥接（mesh ↔ MQTT）
├── platform/      # HAL 抽象（esp32/nrf52/linux 模拟器…）
└── watchdog/ memory/ detect/ buzz/
variants/ boards/  # 板级定义（variant.h 集中引脚/射频参数/Region）
zephyr/            # Zephyr RTOS 新后端（与 Arduino/IDF 并存）
```

要点：
- **协作调度**：全部业务跑在 OSThread 链表上，单主循环轮转，中断只做最小采集——
  对 LoRa 收发时序与睡眠窗口的控制非常友好。
- **配置即协议**：设备配置与消息全部 protobuf 化（nanopb），版本化 schema + 代码生成，
  上位机与固件解耦。
- **板级收敛**：variant.h 一个文件收敛引脚/射频功率/Region，新板=新 variant，不动核心。

## 3. 与本仓对照

| 维度 | 本仓（firmware/ 哨兵子工程 + loracanary） | meshtastic |
|---|---|---|
| 定位 | 单点频谱哨兵（433.92 OOK 采集）+ LoRaCanary 帧原型 | 完整 mesh 网络栈 |
| 射频 | SX1278 OOK 脉冲/PWM 分类 | SX126x/127x LoRa 调制 + 信道管理 |
| 调度 | 裸 loop + DIO1 中断 | OSThread 协作表 |
| 配置 | platformio 宏硬编码 | protobuf schema + variant 表 |
| 组网 | 无（单点/网关雏形） | 多跳路由 + 中继 + MQTT 桥 |

结论：本仓是「传感器节点」形态，meshtastic 是「网络」形态；二者不竞争，
本仓哨兵可作为 meshtastic 网络里的**外挂传感模块**（Serial/Telemetry module 形态）接入。

## 4. 可落地借鉴点（≥3）

1. **OSThread 协作调度表**：把哨兵固件当前的「loop + 中断标志」重构为线程表
   （OOK 采集线程 / LoRa 发送线程 / 睡眠决策线程 / 心跳线程），统一时序与功耗窗口；
   实现量小（~200 行 C++），可直接进 firmware/tests 主机单测。
2. **variant 板级表**：为 SX1278 / SX1262 / LR21-433 三套硬件建 variant 头，
   收敛 platformio 宏与引脚硬编码；新板接入零核心改动。
3. **配置/消息 schema 版本化**：loracanary 帧当前手写 C++ 编解码，借鉴其
   「schema 与代码分离 + 生成器」思路（可继续用轻量 CBOR/手写，但引入 schema 版本号
   与字段表单一事实源），为后续与 meshtastic/MeshCore 互通留口。
4. **modules 自注册插件链**：网关侧协议处理器（OOK 解码器/LoRaCanary/未来 FT8 上报）
   改为自注册链表，新增协议不动分发主干。

## 5. 许可裁定

- **GPL-3.0**。裁定：**独立件，不并入主仓**（主仓 AGPL-3.0 虽可吞，但固件独立仓更干净，
  且避免把 GPL 义务带进桌面/服务端代码）。
- 集成路径（如需真机组网）：独立子仓/子模块引用 + 串口/BLE 协议对接；
  或仅参考设计自研（当前哨兵体量小，**推荐参考设计**，借鉴点 1/2 均为设计级）。
- 代码级复制：不允许进主仓；若未来做「meshtastic 外挂模块」，该模块仓独立 GPL-3.0。

## 6. 433MHz 频段使用要点

- 中国 433MHz 属 ISM（433.05–434.79MHz），限发射功率与占空比；meshtastic 的
  Region 表（EU_433 等）给出功率/占空比/信道参数参照，**不得照搬 US 区参数**。
- 业余频段（430–440MHz 部分）与 ISM 重叠区需按操作证/呼号规则使用；
  本仓哨兵为接收为主（OOK 采集），发射侧（LoRaCanary）上线前需功率合规核查。
- meshtastic 的「区域锁 + 用户可覆盖」设计可借鉴：默认合规区域，专家模式显式解锁。

## 7. 执行清单

- [x] 克隆 + 结构/许可核验
- [x] 借鉴点 4 条 + 融合判定 + 433 要点
- [ ] （后续工单）OSThread 化哨兵调度原型（建议落 firmware/ 主机单测）
- [ ] （后续工单）variant 表三板型收敛
