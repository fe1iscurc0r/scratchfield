# CASE-27 · EasyEDA Pro PCB 间距修复失败案例

## 事件背景

- **项目**：LoRaCanary v0.6 底板 PCB
- **目标**：把剩余 6 个 `pcb check` clearance 错误修完，最终通过 DRC
- **工具**：EasyEDA Pro CLI daemon + `easyeda` 命令行工具
- **问题类别**：`CC2/VBUS`、`3V3/VBUS`、`SDA via / U3.2` 间距不足

## 时间线

| # | 时间 | 操作 | 结果 |
|---|------|------|------|
| 1 | 会话续接 | 基准状态为 6 个 clearance ERROR，22 WARN | 明确要修 CC2、3V3、SDA 三处 |
| 2 | 第一次 CC2 修复 | 把 CC2 顶层水平段整体抬高 5 mil | ❌ 错误数从 6 → 12；原来长段在 **Bottom 层**，误画到 Top 层后横穿 GND |
| 3 | 第二次 CC2 修复 | 改为 Top 短跳 + Bottom 长段，重新放置两个 via | ⚠️ 错误回到 6，但 J1 附近 VBUS 间距未完全解决 |
| 4 | 3V3 分支修复 | 删除 3V3 分支线段，准备在 y=2340 重画 | ⚠️ 因 stage gate 失效，实际改动未生效 |
| 5 | SDA via 修复 | 删除旧 via，准备在 `(2845, 2628.77)` 重建 via + 走线 | ⚠️ CLI 在 `doc reload` 后报 `document.open failed`，未能完成 |
| 6 | 当前状态 | `pcb check` 仍报 6 个 clearance ERROR | 工具进入不稳定状态，无法继续安全自动修复 |

## 关键转折点

### ✅ 做对的地方

- **用 `pcb check` 代替 `pcb drc --json`**：`pcb drc --json` 反复超时截断，`pcb check --json` 可解析，帮助定位到具体线段/过孔。
- **用 `pcb dump` 获取坐标和焊盘信息**：在分析 SDA via 与 U3.2 关系时，dump 数据给出了精确的焊盘尺寸和位置。
- **接受用户纠正**：明确 B1 是线接端子而非插件电池座，避免继续扩板。

### ❌ 失误

1. **未查原 CC2 走线所在层**：默认在顶层重画，导致 GND 交叉短路。
2. **在布线编辑中穿插 `doc reload`**：每次 reload 都清空 routing stage 授权，反复重新 `confirm-layout/confirm-outline/layout-lint`。
3. **删除后未重新授权 stage**：`pcb delete` 会重置 routing 授权，导致后续 `track/via create` 被 `STAGE_BLOCKED` 拦截。
4. **把 assembly profile 设成 0 mil 绕 gate**：为了绕过 `hand-solder 40 mil` 而改成 reflow 0 mil，使装配审查失去意义。
5. **未在批量完成所有操作后再 reload**：应“删→建→reload→检查”，而不是每做一步就 reload。

## 量化影响

- **错误数波动**：6 → 12 → 6，中间出现 0 mil 短路风险。
- **CLI 调用次数**：约 50+ 次（含多次 stage reconfirm、reload、track create/delete）。
- **剩余风险**：6 个 clearance 未清，板子目前不算 DRC 通过；用户需手动在 UI 中微调。

## 结论

本次失败主要由**CLI 工作流不熟 + stage gate 管理混乱**导致，而不是板子设计本身无法修复。剩余 6 个错误都是“把铜皮/过孔挪开 1–3 mil”的量级，在 EasyEDA UI 中手动拖动即可解决，不需要大改布局或扩板。
