# DSP-Cpp-filters 滤波链授粉报告 · 2026-08-23（工单 G-02）

**授粉源**: dimtass/DSP-Cpp-filters（MIT，C++ biquad 滤波器库）
**勘察方式**: clone /tmp，读 19 种滤波器实现
**对照基线**: mcpserver/rf_brain/（sensor.py 只生成信号，feature_extractor 只算 envelope 统计）
**核心发现**: **rf_brain 完全没有滤波链**——sensor 生成 IQ 后直接进 feature_extractor 算 envelope_cv，中间没有低通/带通/降噪环节。这是射频信号处理的最小缺失件。

---

## 1. 滤波器对照表（19 种全标注）

| 滤波器 | 类型 | rf_brain 场景 | 价值 |
|--------|------|--------------|------|
| fo_lpf / so_lpf | 一/二阶低通 | envelope 平滑（解调前降噪） | **高** |
| so_butterworth_lpf | 二阶巴特沃斯低通 | 标准低通，最大平坦 | **高** |
| so_butterworth_bpf | 二阶巴特沃斯带通 | 目标频段提取（sensor 后处理） | **高** |
| so_butterworth_hpf | 二阶巴特沃斯高通 | 去直流偏置/基线漂移 | 中 |
| so_bpf / so_bsf | 二阶带通/带阻 | 干扰抑制（临近频道） | 中 |
| so_linkwitz_riley_lpf/hpf | Linkwitz-Riley | 分频网络（SDR 多频段） | 中 |
| fo_apf / so_apf | 全通 | 相位校正 | 低 |
| fo_shelving_low/high | 搁架 | 频谱整形 | 低 |
| so_parametric_cq_boost/cut/ncq | 参数 EQ | 音频侧（TTS 后处理） | 低 |
| biquad / biquad_modified | 通用双二阶 | 基类，自定义滤波器 | 参考 |

**最高价值 3 个**：so_butterworth_lpf（解调前降噪）、so_butterworth_bpf（目标频段提取）、so_lpf（envelope 平滑）——正好补 rf_brain 缺失的信号链入口。

## 2. 核心数据结构共鸣

### 2.1 Biquad 直接型 → rf_brain 滤波基类
`lib/biquad.h` 的 process()：
```cpp
yn = a0*xn + a1*xnz1 + a2*xnz2 - b1*ynz1 - b2*ynz2
```
直接 II 型（Direct Form I），5 个系数 + 4 个状态变量，每样本 5 乘 4 加。**值钱点**：这是教科书级最小实现——Python/numpy 移植 20 行搞定（scipy.signal.lfilter 或手写状态机），无外部依赖。

### 2.2 calculate_coeffs 公式 → 参数化设计
`lib/so_lpf.h`：
```
w = 2π·fc/fs;  d = 1/Q
b = 0.5(1-(d/2)sin(w))/(1+(d/2)sin(w))
g = (0.5+b)cos(w)
a0=(0.5+b-g)/2; a1=0.5+b-g; a2=a0; b1=-2g; b2=2b
```
**值钱点**：fc/Q/fs 三个参数 → 系数，运行时热更新（扫频时 Q 自适应）。rf_brain 的 scanner 扫频时可用：每步切换 fc 只需重算系数，状态变量保留。

## 3. 接入建议（≥3 条）

1. **P0 - 滤波链前置**：sensor.py 生成 IQ 后 → `so_butterworth_bpf(fc, Q)` 目标频段提取 → 再进 feature_extractor。20 行 numpy 移植，收益最大（envelope_cv 现在直接被带外噪声污染）。
2. **P1 - envelope 平滑**：解调前用 so_lpf 平滑 envelope，减少假峰（Phase4 曾修过"显著峰判定修复假峰"——滤波能根治）。对比 envelope_cv 判据在滤波前后差异。
3. **P2 - 扫频热更新**：scanner 每步重算 bpf 系数（fc 随扫频变），状态变量不重置——lib 的 calculate_coeffs 天然支持。
4. 参考 - 音频链（TTS 后处理）用 shelving/parametric EQ。

**桥接成本标注**：C++ 库整体 ctypes 桥接不划算（19 类滤波器核心逻辑 <500 行 C++，numpy 重写更简单）；**只抄公式不引库**（MIT 允许，但 numpy 原生更快）。

## 4. 结论

DSP-Cpp-filters 的价值不在代码（biquad 是通用技术），在**参数化系数公式清单**——19 种滤波器每种都有现成的 fc/Q/fs → 系数公式，抄写成本近乎零。rf_brain 当前信号链断在「sensor → feature_extractor 无滤波」，补一个 butterworth_bpf + lpf 即闭环。

**落地路径**：`rf_brain/filters.py`（numpy 实现 biquad 基类 + butterworth_lpf/bpf/hpf + 扫频热更新 API）→ pytest 滤波特性断言（通带增益≈1、阻带衰减、相位无跳变）。

*—— 实验田维护者 · 信号进来先洗澡，再判断它是什么——滤波是耳朵的耳膜 🐾*
