# W73-01 RuView WiFi-CSI 感知评估

> 上游：github.com/ruvnet/RuView · MIT · 92K★ · Rust/TS/C · 2026-09-02 活跃

## 1. 项目定位

用普通 WiFi 信号做**实时空间智能与生命体征监测**：隔墙检测人体、测量呼吸/心率、追踪移动、监测房间——无摄像头、无穿戴，纯物理（WiFi CSI）。原生接入 Home Assistant / Apple Home / Google Home / Alexa。

## 2. 架构拆解

- **WiFi CSI 采集**：商品 WiFi 网卡/路由器信号 → CSI 特征。
- **感知算法**：DensePose 姿态估计 + 呼吸/心率提取 + 存在检测。
- **形态**：ESP32 固件 + Web 面板，无摄像头。
- **集成**：HA-DISCO MQTT publisher、HAP-1.1 bridge 等四大智能家居生态。

## 3. 与本仓对照

| 维度 | RuView | 本仓 |
|---|---|---|
| 感知 | WiFi CSI 空间/体征 | mcpserver/rf_brain + TESLA 电磁侧信道 + ESP32-S3 主控 |
| 形态 | ESP32 固件 + Web | rf_brain 模块 |

## 4. 可落地借鉴点（≥3）

1. **WiFi CSI 存在检测算法**：把「现有 ESP32 变 RF 传感器阵列」的可行性验证——用普通 WiFi 信号而非专用雷达做存在/体征检测，可复用其 CSI 特征提取。
2. **ESP32 固件侧的 CSI 采集**：固件如何从 WiFi 芯片抓 CSI 流，是我们 ESP32-S3 电磁侧信道的直接参考。
3. **智能家居生态接入范式**（MQTT publisher / HAP bridge）：rf_brain 的感知输出可用同样方式接入 HA/Apple 生态。

## 5. 许可裁定 + 结论

- **许可**：MIT → 可借鉴代码。
- **硬件复用路径**：我们的 ESP32-S3 主控可复用其「WiFi CSI → 存在/体征」思路，但需真机验证（标「待真机」）。**结论：参考为主**，WiFi CSI 采集 + 存在检测算法值得借鉴，与现有电磁侧信道互补。
