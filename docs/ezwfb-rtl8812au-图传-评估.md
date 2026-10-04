# EZ-WifiBroadcast + rtl8812au 评估（图传演进史 + 驱动标注）

> 2026-09-08 · 卷80 W79-07 · 评估（⚠ GPL-2.0-only 只作架构参考）
> 上游：rodizio1/EZ-WifiBroadcast（GPL-2.0-only，★897）+ svpcom/rtl8812au（GPL-2.0，★161）

## 一、项目定位

- EZ-WifiBroadcast：消费级 WiFi 数字图传经典实现（wfb-ng 的前身/同源），架构参考。
- rtl8812au：wfb-ng 配套网卡驱动（RTL8812AU 芯片选型参考）。

## 二、架构拆解

EZ-WifiBroadcast：单向广播视频流 + 双向遥测的早期形态；rtl8812au：monitor 模式驱动的网卡支持面。

## 三、与本仓对照

图传演进史参考（EZ-WifiBroadcast → wfb-ng 的架构演进路径）；网卡选型清单。

## 四、可落地借鉴点（≥3，仅架构非代码）

1. **单向广播流设计**：视频单向大带宽 + 遥测小带宽回传的不对称链路形态。
2. **演进对照**：EZ-WifiBroadcast → wfb-ng 的架构取舍（FEC/加密/多通道何时引入）。
3. **网卡选型清单**：RTL8812AU 系（monitor 模式支持）的硬件选型参考。

## 五、许可裁定（⚠ 法律硬冲突标注）

**GPL-2.0-only 与主仓 AGPL-3.0 不兼容（GPL-2.0 与 GPL-3.0 是不同世代）**——两件**只作架构/选型参考，不并入、不融合任何代码**。

---
*评估：fe1iscurc0r · 2026-09-08 · 基于上游公开文档，未 clone 源码（GPL-2.0-only 纪律）*
