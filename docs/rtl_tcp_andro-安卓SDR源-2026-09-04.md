# rtl_tcp_andro 安卓端 SDR 源勘察（phone-mobile-hub 线）

> 2026-09-04 · 92号 A1 · 勘察（不写实现、不抄 GPL 代码）
> 上游：martinmarinov/rtl_tcp_andro-（GitHub，GPL-2.0-or-later，安卓端 RTL-SDR I/Q 源）
> 纪律：**rtl_tcp 协议是公开标准可自由参考；rtl_tcp_andro 实现 GPL-2.0-or-later 只参考设计不抄代码**。

## 一、架构拆解

- `iqsrc://` intent 协议：安卓 App 通过 `iqsrc://rtl_tcp_arguments` 形式暴露 I/Q 源，供其他 App（如 SDR 频谱前端）直接吃数据流。
- rtl_tcp 桥接链路：手机 ↔ 接收机（USB OTG RTL-SDR，或网络 rtl_tcp 服务器）。
- 参数面：host / port / freq / gain / sample_rate。

## 二、映射到 phone-mobile-hub（源→目标→方式→收益）

| 源组件 | 目标模块 | 授粉方式 | 收益 |
|--------|---------|---------|------|
| rtl_tcp_andro I/Q 源 | 移动 SDR 数据层 | intent 协议复用 / rtl_tcp 桥接 | 手机直连 SDR，免电脑 |
| iqsrc:// intent | 频谱前端数据流 | 数据流接口对齐 | App 间 I/Q 互通 |
| 参数面(host/port/freq/gain) | SPEC-SDR 频谱数据层 | 字段对齐 | 元数据标准化 |

## 三、字段对齐表（I/Q 流 + 元数据 vs SPEC-SDR 频谱数据层）

| rtl_tcp_andro | SPEC-SDR 频谱数据层 | 对齐结果 |
|---------------|-------------------|---------|
| freq | center_freq_hz | 已有，需对齐 |
| sample_rate | 采样率 | 已有，需对齐 |
| gain | 增益 | 需补 |
| host/port | 数据源定位 | 需补 |
| 时间戳 | datetime | 需补（对齐 SigMF） |

## 四、rtl_tcp 协议 vs 实现 的许可边界

- **rtl_tcp 协议本身**：公开标准（rtl-sdr 项目协议描述），可自由参考、独立实现。
- **rtl_tcp_andro 实现**：GPL-2.0-or-later——**只参考设计**（intent 协议 / 桥接链路思路），不抄代码。
- **硬冲突风险**：GPL-2.0-only 与 AGPL-3.0 不兼容；主仓用 rtl_tcp 协议独立实现（`rtl_tcp 客户端`）可避免传染，不融 GPL 源码。

## 五、依赖 / 硬件需求

- 需 USB OTG + RTL-SDR 硬件，或网络 rtl_tcp 服务器。
- USB Host API 可行性：安卓侧可用 USB Host API 直连 RTL-SDR（需权限/驱动）。

## 六、接入建议（≥3）

1. **rtl_tcp 客户端独立实现**：按公开协议写纯 Python rtl_tcp 客户端（不依赖 GPL 代码），手机→接收机数据流。
2. **intent 协议对齐**：频谱前端支持 `iqsrc://` intent 作为数据源入口，App 间 I/Q 互通。
3. **元数据字段对齐**：把 host/port/freq/gain/时间戳纳入 SPEC-SDR 频谱数据层（与 SigMF 90号对齐）。

## 七、结论

**接入（分步）**：rtl_tcp 协议层独立实现（公开标准，无传染）→ intent 协议对齐 → 元数据字段标准化；rtl_tcp_andro 实现只作设计参考，不融 GPL 代码。

---
*勘察：fe1iscurc0r · 2026-09-04 · 基于上游公开文档与 rtl_tcp 公开协议，未 clone GPL 源码*
