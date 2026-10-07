# 射频大脑 M1 自测记录

> 日期：2026-08-13 | 施工：沈遥（Hermes）
> 跑法：三个 phase 测试全跑通

## 实测特征数据（snr=20dB, seed=42）

| 信号 | flatness | SNR(dB) | 包络CV | 候选 | 闭环结果 |
|------|----------|---------|--------|------|---------|
| GFSK | 0.009 | 37.5 | 0.071 | [FSK, GFSK, OOK] | ✅ 收敛 FSK |
| FSK | 0.010 | 37.6 | 0.071 | [FSK, GFSK, OOK] | ✅ 收敛 FSK |
| OOK | 0.017 | 35.2 | **0.852** | [OOK, FSK, GFSK] | ✅ 收敛 OOK |
| 纯噪声 | 0.566 | 8.5 | 0.524 | [] | ✅ 判无信号 |

## 验收对照

- Phase 0：三 schema 字段完整（FeatureVector/Decision/DemodFeedback）✅
- Phase 1：GFSK 候选含 GFSK、纯噪声判无信号 ✅
- Phase 2：兜底路径决策层输出合法 Decision、无信号→unknown ✅
- Phase 3：OOK 精确区分，GFSK/FSK 归大类 ✅

## 实现中发现的真实边界（已写入代码注释）

1. **envelope_cv（包络变异系数）是区分 OOK 的关键特征**——OOK 幅度键控包络剧烈波动(~0.85)，FSK/GFSK 恒定包络(~0.07)。SPEC 原版只靠频谱 flatness，无法区分 OOK 和 GFSK（两者都是单峰+低平坦度），已补上此字段。
2. **噪声判定靠 flatness 不靠 SNR**——纯噪声峰值天然比中位数高 ~10dB，SNR 阈值会误判。改为主判据 flatness≤0.5 + 辅助 SNR。
3. **GFSK vs FSK 在 M1 不可区分**——两者合成信号都是连续相位（cumsum），频谱几乎一致。区分需瞬时相位轨迹（高斯平滑 vs 硬切换），属 Phase 4 接真底座时做。M1 归为「恒定包络频移键控」大类。

## 下一阶段（Phase 4，未施工）

- liquid-dsp（C 库 ctypes 包装）替换 sensor.py 的 numpy 参考
- sdrtrunk（JVM 子进程桥）替换多协议解调
- 接真实 SDR（RTL-SDR / IC-705 CI-V）
- 补 GFSK vs FSK 的瞬时相位轨迹特征

## Phase 4 · LLM 接通（2026-08-13 已完成）

接 DeepSeek 验证「真 LLM 决策」闭环：

- decision_layer 的 prompt 补上 envelope_cv 字段（区分 OOK 的决定性特征，之前漏传导致 LLM 把 OOK 误判 FSK）
- feature_extractor 峰值检测改「显著峰判定」（主峰 -6dB 内 + min_gap=20），修复旁瓣波纹导致的假峰（原 n_peaks=18/23/34，修后=2）
- 新增 test_phase4_llm.py：LLM 端到端闭环

**LLM 决策实测**（DeepSeek-chat，snr=20dB）：
- GFSK → GFSK（conf 0.88，恒定包络+频谱集中）
- FSK → GFSK（conf 0.88，大类内，M1 诚实边界）
- OOK → **OOK（conf 0.90，envelope_cv=0.852 幅度键控）** ← 关键突破
- 噪声 → unknown（正确）

**结论**：LLM 拿到 envelope_cv 后能可靠区分幅度键控 vs 恒定包络，核心命题「LLM 替代人工调参」在仿真层初步成立。真实 SDR 信号留 Phase 4 硬件部分。

## Phase 4 · DSP 判据 + liquid-dsp 底座（2026-08-21）

### GFSK vs FSK 瞬时相位轨迹判据（已落地，突破 M1 大类边界）

新特征 ``freq_transition_slope``：鉴频 → 两级去噪（短滑动均值 + 滑动中值保边）→
p99(|Δf|)/轨迹峰峰值。FSK 硬切换保为孤立尖峰（指标≈ 0.18~0.24），
GFSK 高斯成形是连续坡道（≈ 0.07~0.12），阈值 0.13 分离约 3 倍。
rule_engine 据此在恒定包络分支内细分，正确调制排候选第一。

**实测标定**（sensor 合成，seed 42/7/123）：

| SNR | GFSK slope | FSK slope | 可分？ |
|-----|-----------|-----------|--------|
| 30dB | 0.068 | 0.226 | ✅ ~3.3× |
| 20dB | 0.078~0.081 | 0.227~0.242 | ✅ ~3× |
| 15dB | 0.121 | 0.178 | ✅ 勉强 |
| 10dB | 0.201 | 0.206 | ❌ 重叠（鉴频噪声淹没） |

**实现中发现的真实边界**：

1. sensor.py 原 GFSK 一阶 IIR（α=0.15）平滑不足，轨迹与 FSK 几乎一致——
   改为真高斯脉冲成形（BT≈0.5，跨 3 符号）后判据才成立。
2. SNR 20dB 时鉴频噪声 σ（~31kHz）比频偏（24kHz）还大：单级中值压不住，
   必须「短均值（保边减半噪声）→ 中值（保边压残余）」两级串联。
3. 滑动均值会把硬切换陡边摊到与噪声同量级（均值滤波保不了边），
   中值滤波才是保边去噪的正解。

### liquid-dsp ctypes 后端（骨架已接，对拍待天选7）

- ``liquid_backend.py``：spgramcf 周期图 ctypes 包装（对齐 liquid-dsp 1.6.x API），
  DLL 定位链：``LIQUID_DSP_LIB`` 环境变量 → ``vendor/`` → ``github_haul/physical/liquid-dsp/``。
- ``feature_extractor`` 默认走 liquid（可用时），``force_numpy=True`` 可强制参考路径。
- 降级策略同 rsba1_adapter：DLL 缺失自动回退 numpy，闭环不停摆。
- **对拍验收**（``test_phase4_dsp.py::test_liquid_numpy_feature_parity``）已写好，
  本机无编译链（无 gcc/MSYS2）暂 SKIPPED；天选7 编译出 libliquid 后自动纳入，
  断言语义特征（主峰/带宽/平坦度/SNR）在容差内一致。

### 硬件部分现状（诚实记录）

- 本机无 gcc/MSYS2，liquid-dsp 源码在**天选7**（github_haul/physical/），未编译。
- sdrtrunk JVM 桥：本机有 JDK 21，但无 sdrtrunk 发行包，未接入。
- 真实 SDR（RTL-SDR / IC-705 CI-V）未接，sensor.py 仍是仿真数据源。
- 下一步（天选7）：``./configure && make`` 编译 libliquid → 放 ``vendor/`` 或设
  ``LIQUID_DSP_LIB`` → 跑 ``pytest mcpserver/rf_brain/test_phase4_dsp.py`` 完成对拍。

## Phase 5 · 自主闭环（2026-08-22 已完成）

从「人工点单」到「无人值守」：频谱扫描调度器 → 能量检测 → 候选信号表 →
LLM/规则决策 → 解调 → 失败重试反馈环，一次 ``run_sweep()`` 全自动跑完。

### 新模块

- ``amateur_bands.py``：业余频段白名单（数值与 rsba1_adapter 完全一致，来源
  civ_commands.py），任何设频率入口前置校验，越界抛 ValueError。
- ``scanner.py``：盲扫调度器——能量检测只读 IQ 样本，不感知布点表；中心频
  白名单校验前置（任一越界整体拒绝，不产生半截结果）。
- ``autonomous.py``：闭环编排 ``run_sweep()`` → 逐候选 ``run_loop()`` →
  SweepReport（含误检率/漏检率统计）。

### 误检口径（验收：误检率 <10%）

- 误检 FP = 噪声被判为信号 / 无信号窗口数
- 漏检 FN = 信号被漏检 / 有信号窗口数

### 能量检测标定

阈值 12dB（峰值相对 20% 分位数噪声底，Hanning 窗 + 窗 11 平滑）：

| 信号 | SNR 15dB | 20dB | 30dB |
|------|----------|------|------|
| GFSK | 34.2dB | >37dB | >40dB |
| FSK | 32.8dB | >37dB | >40dB |
| OOK | 33.3dB | >37dB | >40dB |
| 纯噪声（多 seed） | — | ≤8.2dB | — |

分离裕量 4.7 倍（信号 min 32.76dB vs 噪声 max 8.20dB），SNR15dB 全检出、噪声全拒检。

### 实现中发现的真实边界（已修复）

1. **OOK 符号率估计失效**：OOK 基带含直流偏置（0/1 电平），-3dB 带宽测量退化到
   单 FFT bin（500Hz），作为符号率使解调 sps=4000 只剩 1 个符号 → 「符号数不足」。
   修复：``decision_layer._default_params`` 只信任 [1k, 200k] 区间的带宽估计，
   否则回落到传感器默认 48k。修复后 OOK 跨 seed（7/42/123）全部收敛。
2. **玩具解调器对 GFSK/FSK 同一实现**：鉴频路径共用，重试反馈环用 mock 钉住
   decide/demodulate 确定性验收，不依赖具体调制组合的噪声运气。

### 验收结果（test_phase5.py，16 项）

- ✅ 能量阈值分离：三调制 × 三 SNR 全 >12dB，多 seed 噪声全 <12dB
- ✅ 盲扫语义：检测结果 = 纯 IQ 能量函数，与布点表 present 解耦
- ✅ 白名单：144/148MHz 边界放行；131.5M/49M/30.000001M/148.000001M 抛 ValueError
- ✅ 失败重试反馈环：首猜失败 → alternatives 重试 → 收敛
- ✅ run_sweep 端到端：误检率 0%、漏检率 0%（<10% 验收线）、墙钟 <1s（<30s 验收线）
- ✅ 纯噪声环境误检率 0；全信号环境漏检率 0；相邻窗口能量互不污染

全量回归：``52 passed, 1 skipped``（liquid-dsp 对拍仍 SKIPPED，待天选7 编译）。

## Phase 6 · 多协议解码器库（2026-08-23 已完成）

Provider 注册表 + 三个新解码器（APRS/AX.25、PSK31、DTMF），POCSAG 归入注册表。
主流程（``decoders/__init__.py`` 的 ``decode / decode_all / list_decoders``）只消费
注册表，新增协议只需 ``register_decoder`` 装饰器，零主流程改动。

### 架构

- ``decoders/registry.py``：``_DECODERS`` 全局字典 + ``register_decoder`` 装饰器 +
  泛型 ``decode_all()``（遍历全部条目，异常逐条捕获成失败 DecodeResult）。
- 每个解码器模块末尾装饰器自注册，``__init__.py`` 统一导入即完成注册。
- 注册表验收：``list_decoders() == {aprs, psk31, dtmf, pocsag}``、未知名 → 失败结果、
  ``decode_all`` 无协议分支（测试断言返回顺序 = 注册顺序）。

### 三新解码器要点

- **APRS/AX.25（AFSK1200 / Bell 202）**：文本 → AX.25 UI 帧（FCS-16 取补码、低字节先发）
  → bit stuffing（连续 5 个 1 插 0）→ HDLC 0x7E 成帧 → NRZI（bit0 翻转）→ FSK 调制。
  接收：鉴频 → **每符号窗口平均频率（integrate-and-dump）** → NRZI 解码（双极性消极性模糊）
  → 0x7E 同步 → de-stuff → **FCS 残差校验（==0xF0B8）** → 字段解析。
- **PSK31（31.25 baud BPSK + Varicode）**：Varicode 表逐字节转录自 codec2 varicode_table.h，
  运行时按 codec2 截断逻辑重建码字映射。调制 bit1 保相/bit0 翻转；接收 integrate-and-dump
  位定时恢复 + 相邻符号相位差判 bit + 双极性消相位模糊。
- **DTMF（Goertzel，纯 numpy 无 scipy）**：8 音精确频率点积 + 512 点帧 / 160 点步进，
  PEAK_RATIO=5.0 + 连续两帧同键双重拒噪。

### 实现中发现的真实边界（已修复）

1. **AX.25 FCS 是余数的补码**：``crc_ccitt(payload)`` 直接当 FCS 发，接收残差为 0x0000
   而非 0xF0B8。必须 ``(~crc) & 0xFFFF``、低字节先发，残差才 ==0xF0B8。
2. **NRZI 起始电平错位整帧报废**：发射端起始电平 mark=1，首符号前状态为 0。
   ``(s,1)/(~s,0)`` 两种极性解释都错 1 位；``(s,0)/(~s,1)``（s=(level==0)）才对。
3. **单样本鉴频在加噪下不可用**：相位差分噪声 σ≈0.1rad/样本 ≈ 764Hz，远超 1200/2200Hz
   间 500Hz 判决裕量——SNR 20dB 也全崩（54% 误码）。改每符号窗口平均后 SNR 10dB 零误码。
4. **AX.25 信息字段切到 FCS 尾巴**：``data[16:]`` 把 FCS 两字节并入 info，高字节 >127
   触发 UnicodeDecodeError → 帧被判失败。改为 ``data[16:-2]``。
5. **PSK31 丢首字符**：接收差分解码天然丢首符号，空闲全 1 与首码字头一位合并成无效长码。
   编码侧在空闲前导与数据间插入 ``00`` 字符边界（flush 接收缓冲）解决。
6. **PSK31 噪声误检**：纯噪声偶发解出单字母。幅度一致性 std/mean（真实 BPSK≈0.07、
   噪声 Rayleigh≈0.52）门限 0.35 + 最小可读字符数 3 双重拒检。

### 验收结果（test_phase6.py，16 项）

- ✅ 注册表：四解码器声明式注册、无协议分支、未知名失败、内部异常被捕获
- ✅ APRS：端到端往返 + 低 SNR（10dB × 3 seed）+ FCS 拒垃圾帧
- ✅ PSK31：Varicode 关键码字（含 10bit 最长码 Z）+ 全字符表往返 + 端到端解码
- ✅ DTMF：16 键序列端到端 + 噪声拒检
- ✅ POCSAG：经注册表端到端 + 噪声拒检
- ✅ 主流程健壮性：decode_all 对纯噪声全部拒检（零误报）、内部异常不炸主流程

全量回归：``68 passed, 1 skipped``（liquid-dsp 对拍仍 SKIPPED，待天选7 编译）。

## Phase 7 · IC-705 / SDR 输入抽象（2026-08-23 已完成）

真机集成前置：把 Phase 1-6 的 numpy 仿真复数 IQ 输入，抽象成「实音频帧」
统一输入源（IC-705 USB 声卡输出的正是解调后实音频，48kHz 单声道典型）。
主流程只消费 ``AudioSource.read() → AudioFrame``，不感知后端。

### 架构（provider 注册表，与 decoders/ 注册表同构）

```
device/                  # 输入抽象包
├── base.py              # AudioFrame / AudioSource / iq_from_audio（接口文档本体）
├── registry.py          # register_source / create_source / list_sources
├── ic705.py             # Ic705UsbAudioSource —— IC-705 USB 声卡后端
├── wavfile.py           # WavFileSource —— WAV 离线回放（标准库 wave，零依赖）
└── sim.py               # SimulatedSource —— numpy 仿真注入（默认 DTMF 拨号）
```

数据流：``采集后端 → read() → AudioFrame → frame.to_iq()（Hilbert 实→复基带）
→ decoders.decode_all(iq, sr)``。新增后端 = 新模块 + 一行 ``@register_source``。

### 设计约束落实

1. **依赖无关**：顶层不 import pyaudio/sounddevice。真实采集后端经 ``capture_fn``
   回调注入；无回调时懒加载 pyaudio，未安装抛人类可读 RuntimeError（绝不静默）。
   测试用 monkeypatch 拦截 ``import pyaudio`` 失败验证包仍可导入、离线链路照常。
2. **频段白名单**：携带 ``center_freq_hz`` 的源构造即过 ``amateur_bands.assert_allowed_freq``
   （与 rsba1_adapter.ic705_set_freq → civ_commands.assert_allowed_freq 同一道闸门）；
   433.92M/49M/131.5M 拒绝，145.8M/144.85M 放行。
3. **主流程零分支**：只消费 ``create_source(kind, **kw)``。

### 实现中发现的真实边界

1. **DTMF 相邻重复键合并（已知限制，非 Phase7 缺陷）**：``encode_dtmf`` 20ms 静音
   间隔 + 解码器 512 样本滑动帧，相邻重复键会被 streak 去重合并（``"88"→"8"``）。
   Phase6 验收串 ``"1234567890*#ABCD"`` 无相邻重复键故未暴露。真机 ITU 标准间隔
   40-80ms 不受影响；WAV 链路测试改用 ``"8246"`` 规避，解码器语义不改（Phase6 已验收）。
2. **WAV 16-bit 量化后解码仍稳定**：int16 量化（SNR 30dB 合成音频）+ analytic
   变换后 DTMF 全链零丢键（对比 sim 直连）。

### 验收结果（test_phase7.py，21 项 → 铁锚审查后 29 项）

- ✅ 注册表：ic705/wav/sim 三后端注册 + 工厂构造 + 未知名拒绝 + ABC 不可实例化
- ✅ WAV 回放：读回正确、EOF StopIteration、越界频率构造拒绝
- ✅ iq_from_audio：+1000Hz 单边带保留、-1000Hz 清零、实部=原信号
- ✅ IC-705：白名单放行/拒绝、capture_fn 回调驱动 read、max_samples 截断、
      无 pyaudio 时 open 抛可读错误、拦截导入失败包仍可用
- ✅ 契约回归（补 8 项）：sim 越界频率拒绝、wav/sim max_samples 截断、
      duration_s 生效、capture_fn/gen_fn 空帧与 NaN 抛 RuntimeError、gen_fn 收 n
- ✅ 全链路闭环：sim 与 WAV 音频 → to_iq → decode_all 解出 DTMF（真机链路替身）
- ✅ 白名单对齐哨兵：AMATEUR_BANDS 数值 == rsba1_adapter（civ_commands）

全量回归：``89 passed, 1 skipped``（liquid-dsp 对拍仍 SKIPPED，待天选7 编译）。

## 三 agent 联合评审 + 契约修复（2026-08-23）

Phase7 交付后并行召集沈遥（liquid-dsp 调查）、杜赞（方案拍板）、铁锚（代码审查）。

### 铁锚审查（device/ 8 文件，0 CRITICAL / 1 HIGH / 4 MEDIUM / 5 LOW，评分 76/100）

| 级别 | 问题 | 处置 |
|------|------|------|
| HIGH | README 真机示例导入路径错误（`mcpserver.rf_brain.adapters...` 不存在；`ic705_set_freq` 非模块级函数） | ✅ 已修：改 `mcpserver.adapters.rsba1_adapter.adapter` + `Rsba1Ic705Bridge()._tools()["ic705_set_freq"]`，注明规范入口 handle_handoff |
| MED | `device_index` 死参数（`pa.open` 未传 `input_device_index`） | ✅ 已修：`_lazy_pyaudio_stream` 增加参数并透传 |
| MED | wavfile open 异常路径句柄泄漏 + `wave.Error` 未包装 RuntimeError + 重复 open 旧句柄未关 | ✅ 已修：try/finally 关句柄、wave.Error → RuntimeError、重复 open 幂等 |
| MED | sim `_default_gen` 忽略 n → `read(max_samples=256)` 实际返回整帧；`duration_s` 对默认生成器无效 | ✅ 已修：`_default_gen` 增 n 参数并截断 |
| MED | capture_fn/gen_fn 输出无校验（空帧/NaN 静默通过） | ✅ 已修：空帧/NaN 抛人类可读 RuntimeError |
| LOW | base.py docstring 白名单语义歧义 | ✅ 已修：澄清"各后端构造时校验；直接构造由调用方保证" |
| LOW | 白名单缺 430-440MHz（与上游 civ_commands 一致，既定设计） | 不动 |
| LOW | wav read() 无 max_samples 整文件读入（契约"None=后端默认整块"） | 不动（设计如此） |
| LOW | sim 越界/契约路径无测试覆盖 | ✅ 已补 8 项契约回归测试 |

修复后 Phase7 测试 **29/29 全绿**（原 21 + 新补 8），全量 **97 passed, 1 skipped**。

### 沈遥调查（liquid-dsp 对拍 SKIPPED 根因）

- 根因：DLL 全 miss（`LIQUID_DSP_LIB` → `vendor/` → github_haul 全未命中），
  本机无编译链（无 gcc/MSYS2）。
- 可选解：**conda-forge 有 win-64 liquid-dsp 1.6.0 预编译包**（最省力，需装
  conda/mamba）；或 MSYS2 + CMake 自编译丢 `vendor/`；vcpkg 不支持 Windows。
- 测试改法建议：改 skip reason + 加 marker 让跳过可寻址（别降级成同源自比）。

### 杜赞拍板（方案 C：维持现状）

- 本机无接入场景 → skipif + reason 是标准做法，**不需要配置编译环境**。
- DLL 定位为可选加速，缺失降级 numpy 是 feature-flag 式可回退设计（同 rsba1_adapter）。
- 登记待办：天选7 编译出 libliquid 后首跑对拍专验 ctypes 签名；
  日常可用 `pytest -rs` 让 skip 原因可见。
- **不修改测试逻辑**，避免把"外部依赖缺失"伪装成"验收通过"。

### 回退路径日志覆盖（numpy 降级可诊断性加固）

补齐缺失 liquid-dsp 时所有回退路径的日志与测试：

| 路径 | 日志 | 覆盖测试 |
|------|------|----------|
| DLL 候选路径不存在（is_file miss） | `debug` 逐条输出候选路径 | `test_fallback_logs_candidate_miss_and_summary` |
| 全部候选 miss → 降级 numpy | `warning` 摘要（默认 root WARNING 可见，进程内一次） | 同上 |
| CDLL 加载失败（OSError/AttributeError） | `warning` 含失败原因 | `test_load_failure_logs_warning_and_falls_back` |
| CDLL 加载成功 | `info` 含 DLL 路径 | 待补（monkeypatch 伪造成功分支） |
| feature_extractor 后端选择（liquid/numpy 分支） | `debug` 各一条（force_numpy 与不可用分因） | `test_extract_features_logs_numpy_backend_choice` |
| lib 不可用时调用 `power_spectrum` | 抛 RuntimeError（绝不静默） | `test_power_spectrum_raises_when_unavailable` |
| DLL 定位顺序（env → vendor → github_haul） | — | `test_lib_candidates_env_priority`（平台无关） |
| spgramcf_create 返回 NULL | 抛 RuntimeError | 待补（低优先级，与缺失场景正交） |

测试基建：autouse fixture 重置 `_load_attempted/_lib` 模块级缓存，跨测试互不污染。

### 三 agent 第二轮评审（验证结果复核）

沈遥指出验证盲区：caplog 验证 record 产生 ≠ 真实可见——rf_brain 无任何
handler 配置，root 走 lastResort 只放行 WARNING+，**info 摘要真实运行不可见**。
杜赞拍板 + 铁锚复核后落地：

1. 降级摘要 **info → warning**（[liquid_backend.py] 94 行），措辞补
   "本进程不再重试，部署 DLL 后需重启"（`_load_attempted` 粘滞语义显式化）。
   真实进程验证：默认配置下 stderr 可见该 warning（lastResort 放行）。
2. force_numpy 与 liquid-dsp 不可用两因**拆分消息**（消除归因歧义）。
3. 测试补 5 处：摘要断言升 warning + levelno 锁定；P6 加载失败分支新增
   `test_load_failure_logs_warning_and_falls_back`（伪 DLL 本机可测）；
   env 优先级断言改平台文件名动态取（非 win32 不再必失败）。
4. 主流程入口**不加**后端提示日志（杜赞：同一事实不打两遍）。

全量回归 **102 passed, 1 skipped**（liquid 对拍 SKIPPED 符合拍板）。

## 遗留问题（真机配合项 · Phase 7 任务 7.2）

- IC-705 USB 声卡真机采集未验证（需真机 USB 枚举 + 本机音频后端，属任务 7.2 用户配合）。
- 任务 7.2 闭环（UV-K6 发射 / IC-705 接收）待真机：组合方式见 ic705.py 文档
  （rsba1_adapter 设频 → Ic705UsbAudioSource 读音频 → decode_all 解码告警）。
- liquid-dsp 对拍（杜赞拍板维持现状）：天选7 编译出 libliquid 后首跑
  ``test_phase4_dsp.py::test_liquid_numpy_feature_parity`` 专验 ctypes 签名；
  日常 ``pytest -rs`` 查看 skip 原因。不做任何测试逻辑修改。
