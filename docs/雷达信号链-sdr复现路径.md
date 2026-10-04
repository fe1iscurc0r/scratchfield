# 雷达信号链 sdr 复现路径索引（W99-01 · 后续批次指引）

> 2026-09-08 · 基于 PLFM_RADAR AERIS-10 评估（MIT 软件 + CERN-OHL-P 硬件）与 mhostetter/sdr 接入。
> 性质：索引页，不写实现——标后续批次落地。

## 一、结论

AERIS-10 的雷达信号链算法（纯软件部分）已确认可全部落在 `sdr`（mhostetter/sdr，MIT，纯 numpy）上复现：LFM 生成 → 脉冲压缩 → 多普勒 FFT → MTI → CFAR，无需 C++/FPGA。本仓 `tools/radio/sdr_proc.py` 已提供前两环（LFM 生成 `lfm_chirp` + 匹配滤波 `pulse_compress`）。

## 二、信号链逐环映射

| 环节 | sdr/numpy 实现映射 | 现状 |
|------|-------------------|------|
| LFM 生成 | `sdr_proc.lfm_chirp()`（numpy 相位累积） | ✅ 已落地 + 测试 |
| 脉冲压缩（匹配滤波） | `sdr_proc.pulse_compress()`（np.correlate） | ✅ 已落地 + 测试（尖峰验证） |
| 多普勒 FFT | 慢时间维 `np.fft.fft`（逐距离门） | ⬜ 后续批次 |
| MTI（动目标显示） | 快时间/慢时间差分对消（np.diff） | ⬜ 后续批次 |
| CFAR（恒虚警检测） | 单元平均 CFAR（滑窗 + 门限，纯 numpy） | ⬜ 后续批次 |

## 三、后续批次建议（按依赖顺序）

1. **W-next-1**：多普勒 FFT + 距离-多普勒图（输入：`pulse_compress` 输出按 CPI 堆叠）。
2. **W-next-2**：MTI 双脉冲对消 + 三脉冲对消（静止杂波抑制）。
3. **W-next-3**：CA-CFAR 检测器（保护单元/训练单元参数化）+ 检测点输出。

## 四、与本仓 rf_brain 的衔接

- 频谱诊断线：`sdr_proc.spectrum_dbm` 输出直接对齐 SpectrumPanel v2 的 dB 谱格式。
- 检测结果（CFAR 点迹）可作为哨兵网格/态势感知的事件源（防御口径）。

## 五、许可

- sdr：MIT（已 pip 安装 0.0.30，版本记录于本封装 docstring）。
- AERIS-10 软件部分 MIT、硬件 CERN-OHL-P：只参考算法链设计，不抄代码。

---
*索引：fe1iscurc0r · 2026-09-08*
