# W95-04 · Meshtastic 生态参考组快速勘察（硬件/固件/应用三层）

**上游**：
- Hydra-Designs/project-hydra-meshtastic-pcb（165★ · GPL-3.0）
- hermes-gadget/SigurdOS-tdeck（26★ · GPL-3.0 · Beta testing）
- xriss/monster-mesh（20★ · **无 LICENSE**）

**勘察方式**：GitHub 浅克隆（D:\wo34-recon\{project-hydra-meshtastic-pcb,sigurdos-tdeck,monster-mesh}）
**工单**：第三十四期扩轮卷95 · W95-04【评估·单报告三件】

---

## 1. 三件定位与层级

| 件 | 层级 | 定位 | 许可 |
|---|---|---|---|
| project-hydra | **硬件** | 1W（30dBm）LoRa PCB：Ebyte E22-900M30S + ESP32-WROOM-32U，兼容 meshtastic-diy-v1 target；KiCad 工程 + JLCPCB 下单指引 + iBom | GPL-3.0 |
| SigurdOS-tdeck | **固件** | LilyGo T-Deck（ESP32-S3 + SX1262 + 240×320 TFT 触屏 + 实体 QWERTY）独立离网 mesh 消息固件，基于 MeshCore 协议，与 MeshCore 中继互通 | GPL-3.0 |
| monster-mesh | **应用** | 树莓派 sdcard 镜像供给脚本 + Lua 应用（mesh 上传音）；QEMU 镜像制作另见 phantom-raspberry | **无 LICENSE → 只读不评** |

## 2. 各自借鉴点

### project-hydra（硬件只读参考，用户不做手搓 PCB）
1. **功率合规标注范式**：README 首条即「30dBm 请核查本地 ISM 法规」——本仓 LoRa 发射侧
   （LoRaCanary/天线云台）文档应沿用「参数 + 法规提示」成对出现的写法。
2. **可制造性三件套**（KiCad 工程 + iBom + 下单指引）：即便不自制板，也是评估第三方
   硬件可维护性的 checklist 参照。
3. **单 5V 输入 + 可切 3.3V 轨（GPS 省电）** 的电源设计思路，可作哨兵电池版供电方案参照。

### SigurdOS-tdeck（非手头硬件，设计参考）
1. **native host-side 测试套件**（`pio test -e native_test`，按模块分 test_battery/
   test_channel_validation/test_chat_config…）：比本仓 firmware/tests 更系统的
   「无硬件主机单测」组织方式——**最值得抄的组织结构**（GPL 只参考组织不抄代码）。
2. **fuzz/ 目录**：协议解析器 fuzz 目标独立成目录，本仓 loracanary 帧解析可加 fuzz target。
3. **release-evidence/ + CI 签名发布**：固件发布的可验证证据链，值得本仓固件发布流程参照。
4. 版本号「Git tag 优先 + 源码常量兜底」双源策略（src/hal/tdeck_pins.h SIGURDOS_VERSION）。

### monster-mesh（只读不评）
- 无 LICENSE：按工单铁律**只读索引、不评不借**。索引信息：树莓派 sdcard 供给 +
  Lua mesh 传音应用；其 QEMU 镜像脚本在 phantom-raspberry（另仓）。
- 若未来需要「mesh 传音」能力，另找有许可的实现或自研。

## 3. 三层判定汇总

- 硬件层：只读参考（不自制板）；价值在合规标注与可制造性 checklist。
- 固件层：GPL-3.0 不并主仓；**host 单测组织 + fuzz + 发布证据链**为设计级借鉴。
- 应用层：monster-mesh 无许可 → 排除；MeshCore 生态应用侧由 meshcore-gui（W95-03）覆盖。

## 4. 执行清单

- [x] 三件克隆 + 许可核验（monster-mesh 无 LICENSE 已标注只读不评）
- [x] 各层借鉴点 + 判定
- [ ] （后续工单）loracanary 帧解析 fuzz target + 固件发布证据链
