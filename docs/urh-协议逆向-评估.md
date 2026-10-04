# W73-02 URH 无线协议逆向评估

> 上游：github.com/jopohl/urh · GPL-3.0 · 12.6K★ · Python · Blackhat Arsenal 2017/2018

## 1. 项目定位

Universal Radio Hacker（URH）：无线协议逆向 / 信号分析 / 解调的 SIGINT 工具链——从信号到比特到协议全流程。

## 2. 架构拆解

- **信号层**：SDR 采集、频谱分析、解调（ASK/FSK/PSK/OOK 等）。
- **比特层**：同步、去噪、比特流提取。
- **协议层**：消息结构推断、字段标注、模糊测试/重放。

## 3. 与本仓对照

| 维度 | URH | 本仓 |
|---|---|---|
| 信号→比特→协议 | 全流程 GUI 工具 | rtl-ml 勘察（docs/rtl-ml-勘察.md）+ radio-modulation 评估（docs/radio-modulation-评估.md）+ mcpserver/rf_brain |

## 4. 可落地借鉴点（≥3）

1. **「信号→比特→协议」流水线**：URH 的三层流水线（信号解调 → 比特同步 → 协议推断）可作为我们 rf_brain 解调链的架构参考。
2. **标注数据供给 rtl-ml**：URH 的协议逆向产物（标注后的比特流/消息结构）可喂给 rtl-ml 做训练数据。
3. **解调器覆盖**：URH 的多调制解调（ASK/FSK/PSK/OOK）实现，可对照 rf_brain 现有 decoders。

## 5. 许可裁定 + 结论

- **许可**：GPL-3.0 → **只参考设计不融合**（不抄代码）。
- **结论**：参考「三层流水线」架构 + 解调器覆盖清单，不引入 GPL 代码；协议逆向流水线可作为 rf_brain 解调链的对照基准。
