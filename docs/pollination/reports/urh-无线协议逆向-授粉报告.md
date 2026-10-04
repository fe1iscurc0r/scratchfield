# urh 无线协议逆向授粉报告 · 2026-08-23（工单 G-01，P0）

**授粉源**: jopohl/urh（GPL-3.0，12.5k★，2025-12 归档）Universal Radio Hacker
**勘察方式**: clone 到 /tmp（GPL 只读），读 3 大模块核心，对照 rf_brain
**对照基线**: mcpserver/rf_brain/（GFSK/FSK/OOK 解调 + LLM 决策 + 频谱感知）
**结论**: urh 的「协议格式自动发现」是 rf_brain 最大的能力缺口——rf_brain 有耳朵（感知）和手（解调），但缺「看懂未知协议结构」的脑。GPL 只读，提取设计不拉代码。

---

## 1. urh 架构拆解

```
urh（三层）
├── signalprocessing/   信号层
│   ├── Signal.py           IQ 信号载入/切片/FFT/降噪
│   ├── Modulator.py        调制器（ASK/FSK/PSK/GFSK/OQPSK 5种 + 高斯滤波 bt=0.5）
│   ├── Filter.py            FIR 滤波（fft_convolve_1d 快速卷积 + 带宽↔长度换算）
│   ├── ProtocolAnalyzer.py 协议帧解析（preamble/sync 定位 → 位流 → 十六进制）
│   └── Encoding.py         编码层（NRZ/Manchester/Differential 等反相编码）
├── awre/               协议格式自动发现（最值钱）
│   ├── FormatFinder.py     迭代字段发现核心（run → perform_iteration）
│   ├── engines/            5 个字段引擎：Address/Length/Checksum/SequenceNumber
│   └── Preprocessor.py     消息预处理
└── simulator/          信号模拟
    ├── Modulator.py        参数化调制 → 波形生成
    └── SimulatorExpressionParser.py  场景条件表达式
```

## 2. 核心数据结构共鸣（对照 rf_brain）

### 2.1 FormatFinder 迭代字段发现 → rf_brain「未知协议结构识别」
`awre/FormatFinder.py:190 perform_iteration`：
- 对每条已知消息类型，跑一轮字段引擎（address/length/checksum/seq）
- 输出字段集合 → `create_common_range_containers` 按共同范围分组
- **1 个容器 = 一个消息类型；>1 个容器 = 消息类型分裂**（多种帧格式出现时自动拆）
- `run(max_iterations=10)` 迭代到不再发现新字段

**为什么值钱**：rf_brain 的 `demod_ref.py` 只会解调已知调制（GFSK/FSK/OOK）得到符号流，但**不知道符号流里的字段结构**（哪几 bit 是 preamble、哪几 bit 是地址、有没有 checksum）。urh 的 FormatFinder 输入一堆已知消息就能自动猜出字段划分——这正是 rf_brain 感知→解调闭环缺的「结构理解」层。授粉后：LLM 决策层拿到的不再是「符号流+BER」，而是「符号流+自动发现的字段边界+消息类型」。

### 2.2 引擎模式（Address/Length/Checksum/SequenceNumber）→ rf_brain 规则引擎扩展
`awre/engines/` 5 个独立引擎各自探测一种字段语义，输出 CommonRange 统一表达。rf_brain 的 `rule_engine.py` 是信号级规则（带宽/调制判据），字段语义级规则（长度字段与后续数据一致、checksum 可验证、序号递增）完全缺失。**引擎模式 = 可插拔字段探测器，每加一种协议认知就加一个引擎**。

### 2.3 Encoding 反相编码层 → rf_brain 符号到比特的缺失环节
`signalprocessing/Encoding.py` 处理 NRZ/Manchester/Differential——rf_brain 的 `demodulate_symbols` 直接输出符号流，**没有编码反转层**。真实设备（遥控器/传感器）普遍用 Manchester/差分编码，缺这层 = 解调对了也读不出数据。

## 3. rf_brain 差距清单（≥5 条）

| # | 差距 | urh 对应 | 授粉方式 | 优先级 |
|---|------|---------|---------|--------|
| 1 | 无协议字段自动发现（只知调制不知结构） | awre/FormatFinder.py | 移植「迭代字段发现 + common range 容器 + 消息类型分裂」设计（GPL 只抄设计，Python 独立实现） | **P0** |
| 2 | 无字段语义引擎（address/length/checksum/seq） | awre/engines/ | 抽 4 个引擎接口 → rf_brain 规则引擎加字段层 | P1 |
| 3 | 无编码反转层（Manchester/差分） | signalprocessing/Encoding.py | 实现 NRZ/Manchester/Diff 解码器（通用技术） | P1 |
| 4 | 调制类型只支持 3 种（GFSK/FSK/OOK） | Modulator.py 5 种（+PSK/OQPSK） | 扩展 PSK 解调（鉴相+符号映射） | P2 |
| 5 | 无 preamble/sync 自动定位 | ProtocolAnalyzer.py | 同步字滑动相关检测 | P1 |
| 6 | 无信号模拟回放（测试真机链路用） | simulator/ | 参数化调制→波形生成，做 rf_brain 回环测试 | P2 |
| 7 | 滤波只有简单 FIR | Filter.py fft_convolve_1d | FFT 卷积加速 + 带宽↔长度自动换算 | P3 |

## 4. 接入路径

```
rf_brain 新旁路模块 protocol_finder/（独立，不改现有 sensor/decision 路径）
├── field_discovery.py     # FormatFinder 设计移植：common_range 容器 + 消息类型分裂
├── engines.py             # 4 字段引擎接口（address/length/checksum/seq）
├── encoding.py            # NRZ/Manchester/差分 解码
└── sync_detect.py         # preamble/sync 滑动相关
验证: 用 urh 导出的已知协议样本（RC 遥控/433M 传感器）跑 field_discovery → 断言字段边界
验收: pytest protocol_finder/ 全过；对 3 种已知协议样本的字段恢复率 ≥80%
```

## 5. 结论

urh 是「协议逆向 IDE」——rf_brain 是「频谱大脑」。授粉方向明确：**urh 的 FormatFinder 字段发现 + engines 语义引擎 + encoding 解码层** 恰好补 rf_brain 的「结构理解」空白，让 LLM 决策层从「猜调制」升级到「猜协议」。GPL-3.0 只读勘察，设计抄写（算法/接口是通用技术），代码独立实现（rf_brain 是 AGPL 主仓，不引 GPL 代码）。

*—— 实验田维护者 · 耳朵有了，手有了，现在要给它一双会读协议的眼睛 🐾*
