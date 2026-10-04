# theseus-cores 评估（W71-06）

> 上游：theseus-cores/theseus-cores（GitLab，11★，Verilog）｜ <https://gitlab.com/theseus-cores/theseus-cores>
> 许可：NOASSERTION（未声明）——**许可待核**，未核前不融合代码

## 1. 项目定位

开源 **FPGA 核**集合：DSP / SDR 数字信号处理核（滤波、调制、相关等），自带测试/验证。

## 2. 架构拆解

- **Verilog 核库**：可综合的 DSP/SDR 处理单元（FFT/FIR/相关器/解调器等）。
- **模块化**：核之间可组合，用于构建 FPGA 信号处理链。
- **自带验证**：每核带 testbench，验证可综合性与功能。

## 3. 与本仓对照

| 维度 | theseus-cores | 本仓 |
|---|---|---|
| 信号处理实现 | FPGA 硬件（Verilog） | rf_brain 纯 Python 模拟 |
| 性能 | 硬件加速（高吞吐） | CPU 软处理 |

**边界结论（验收项）**：FPGA 适合「高吞吐、低延迟、可并行」的 SDR 前端加速（如宽带信道化、相关器）；
MCU/CPU 适合「灵活、可重构、低开发成本」的算法原型——rf_brain 现阶段用 Python 验证算法，
**FPGA 加速是未来高吞吐场景的预留方向**，非当前主线。

## 4. 可落地借鉴点（≥3）

1. **DSP 核目录作 FPGA 加速参考**：未来若 rf_brain 需 FPGA 加速（宽带 FFT/信道化），可参考其核
   划分与接口设计（仅设计级，许可待核不抄代码）。
2. **「核 + testbench」的可验证模块化**：每个 DSP 单元带独立验证的工程范式，借鉴到 rf_brain 的
   模块测试纪律。
3. **可组合信号处理链**：把 DSP 功能拆成可组合核，便于按需拼接不同 SDR 前端。

## 5. 许可裁定

NOASSERTION——**许可待核**，未明确许可前不融合任何代码，仅作设计参考。

## 6. 结论

设计参考级（许可待核）。建议：仅登记，等许可明确后再决定是否入栈；现阶段 rf_brain 用 Python
算法原型，不投入 FPGA。
