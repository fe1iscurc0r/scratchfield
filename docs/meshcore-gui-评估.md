# W95-03 · pe1hvh/meshcore-gui 勘察（MeshCore 生态桌面侧）

**上游**：pe1hvh/meshcore-gui（26★ · MIT · 2026-09-06 活跃）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\meshcore-gui，depth-1）+ README/模块结构阅读
**工单**：第三十四期扩轮卷95 · W95-03【评估】

---

## 1. 项目定位

MeshCore mesh 网络的**桌面全功能平台**：Monitor / message / archive / automate / publish，
「no cloud, no broker, just LoRa」。经 USB serial 或 BLE 直连 MeshCore 固件设备，
可 headless 跑在 Raspberry Pi 上（服务形态），跨 Linux/macOS/Windows。
定位是 MeshCore 生态的**客户端/运维台**——与已授粉的 meshcore-open（协议栈侧）互补：
一个管「设备里跑什么」，一个管「桌面上看什么/发什么」。

## 2. 架构拆解（模块实测）

```
meshcore_gui/
├── api/       # 对外 HTTP/WS API（headless 服务形态的入口）
├── ble/       # BLE 传输适配（Linux D-Bus 策略单独文档化）
├── core/      # MeshCore 协议客户端（帧解析/会话/联系人）
├── gui/       # 桌面 UI（Tk 系）
├── services/  # 后台服务（归档/发布/自动化任务）
└── static/    # Web 前端静态资源（headless 形态的 Web UI）
tools/ install_scripts/ docs/
```

要点：
- **传输抽象**：USB serial 与 BLE 统一为传输接口，上层协议客户端无感切换；
  BLE 在 Linux 的 D-Bus 权限坑被单独写成安装文档（工程成熟度信号）。
- **双形态**：桌面 GUI 与 headless+Web 静态前端共用同一 services/core 层——
  「一套核心，两种皮」，与本仓 lumo（Electron+Web）形态同构。
- **archive/publish/automate**：消息归档、对外发布、规则自动化三件套，
  是「观测数据沉淀」的完整参照。

## 3. 与本仓对照

| 维度 | 本仓 | meshcore-gui |
|---|---|---|
| LoRa 接入 | 哨兵 NDJSON + LoRaCanary 帧（自研协议） | MeshCore 串口/BLE 协议客户端 |
| 桌面形态 | lumo Electron（频谱/ELN/电台面板） | Tk 桌面 + headless Web 双形态 |
| 数据沉淀 | ELN/知识库（科研向） | 消息 archive/publish（运维向） |
| 自动化 | 无 | services 规则自动化 |

## 4. 可落地借鉴点（≥3）

1. **传输抽象层**：本仓若接 LoRa 网关/设备（串口或 BLE），照其「传输接口 +
   协议客户端分层」做设备接入层，避免协议代码与串口代码纠缠。
2. **headless + 静态前端分离**：lumo 的频谱/LoRa 面板可复用「Python 服务 +
   静态 Web」形态做无桌面环境（树莓派/天选7 无头）下的观测入口。
3. **archive/publish 三件套**：LoRa 观测数据（哨兵 NDJSON / LoRaCanary 事件）
   入库 ELN 时借鉴其归档 schema 与发布钩子设计（变化触发 + 周期快照）。
4. **BLE 权限坑文档化**：Linux D-Bus 策略这类平台坑写成安装文档的做法，
   值得本仓 firmware/LoRa 接入文档沿用。

## 5. 许可与接入判定

- **MIT**：可直接借鉴/融合（保留版权声明）。
- MeshCore **固件侧闭源**（source-available 受限）：本仓不做固件融合；
  meshcore-gui 的价值在「协议客户端 + 桌面形态」参考，若未来要对接 MeshCore
  设备，按其串口协议自研客户端（MIT 代码可作起点）。
- 接入判定：**生态补件**——与 meshcore-open 组合即「协议栈 + 客户端」完整参照，
  本仓短期不接入，长期作为 LoRa 运维台形态候选。

## 6. 执行清单

- [x] 克隆 + 结构/许可核验
- [x] 借鉴点 4 条 + 生态补件接入判定
- [ ] （后续工单）LoRa 观测数据 archive schema 设计（对齐 ELN）
