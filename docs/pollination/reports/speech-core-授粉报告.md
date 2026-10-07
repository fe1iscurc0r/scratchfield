# speech-core 授粉报告 · 端侧语音管线 → rf_brain / 语音抽象层

> 来源：soniqo/speech-core（68★，Apache-2.0，C++17）
> 审查：沈遥（Hermes）｜日期：2026-08-16
> 定位：融合参考层——C++ 端侧语音基础设施，只读不改造，授粉其「编排/模型分离」架构。

---

## 一、这是什么

speech-core 是面向 Linux/Windows/Android 的 **C++17 端侧语音基础设施**：VAD、流式 STT、说话人分离、TTS、以及把这些串起来的语音 agent 管线。**完全本地 CPU 运行，音频不出设备**。

一句话架构：**编排层与模型层彻底分离**——核心是纯 C++17 状态机（零 ML 依赖），模型后端（ONNX / LiteRT / 无 / 自定义）是可选链接目标。

---

## 二、源领域 → 目标域 映射

| 源（speech-core） | 目标（scratchpad） | 授粉方式 | 收益 |
|---|---|---|---|
| 编排/模型分离（核心零 ML 依赖） | **rf_brain 的「协议无关设备抽象层」** | 同构验证，抄分层 | 高 |
| 抽象接口（STT/TTS/VAD/LLM/Enhancer/AEC） | 陆墨语音层的后端可插拔 | 抄接口设计 | 高 |
| 后端可选（ONNX/LiteRT/无/自定义，换后端=换链接） | rf_brain 换 SDR 后端 | 抄「后端即链接」 | 高 |
| 4 状态滞后 VAD 状态机（`streaming_vad.h`） | cascade 的 VAD 状态机补充 | 参考滞后（hysteresis） | 中 |
| `turn_detector`（话轮边界 + 打断） | NEKO 打断（cascade/aspen 之外第三参考） | 参考 | 中 |
| `speech_queue`（优先级队列 + cancel/resume） | TTS 播放队列的打断恢复 | 参考 | 中 |

---

## 三、核心共鸣（一处最值钱）

### 3.1 编排/模型分离 = 我们 rf_brain 的语音版

speech-core 的 AGENTS.md 明确：

> **编排核心** — 状态机、话轮检测、打断处理、语音队列、对话上下文、流式 VAD 状态机、音频工具。**零 ML 依赖，纯 C++17。**
> 编排目标从不依赖具体模型。切换后端只是构造与链接选择，不需要重写管线。

它把「话轮/打断/队列/状态机」这些**编排逻辑**（纯逻辑，零权重）和「Silero/Parakeet/Kokoro/Whisper」这些**模型实现**（ONNX/LiteRT 后端）拆成两个链接目标：`speech_core`（编排）和 `speech_core_models`（模型）。

**共鸣点**：这正是我们 rf_brain 在射频域做的事——`decision_layer`/`rule_engine`/`loop`（协议无关抽象）与具体 SDR/解调后端分离。speech-core 证明了这套「编排/模型分离」在**语音域**同样成立，且成熟到工业级（68★ + CI 全平台 + 25 个模型矩阵）。**授粉结论：我们的「协议无关抽象层」是跨域的普适架构，语音层可以照 rf_brain 同款分层，不必重新发明。**

### 3.2 4 状态滞后（hysteresis）VAD 状态机

`streaming_vad.h` 用**滞后**（迟滞）防 VAD 抖动——不像 aspen 的单一阈值（0.4 一刀切），而是「进入语音」和「离开语音」用不同阈值/缓冲，避免边界反复横跳。

**共鸣点**：cascade 用 `MIN_SPEECH_CHUNKS=3`（起录需连续 3 帧），aspen 用 `SILENCE_LIMIT=24`（停录需 24 帧静音）——都是滞后的朴素形态。speech-core 把它做成了显式的 4 状态机。三级参考（aspen 最简 / cascade 中等 / speech-core 工业）可以按需选。

---

## 四、难度 × 收益

| 授粉项 | 难度 | 收益 | 建议 |
|---|---|---|---|
| 编排/模型分离架构 | **低**（已有 rf_brain 同构，验证即可） | **高**（语音层分层蓝图） | **授粉到语音层设计** |
| 抽象接口清单（STT/TTS/VAD/LLM/AEC） | 中（需 C++ 或转 Python 重写） | 高（后端可插拔） | 授粉到陆墨语音层接口 |
| 滞后 VAD 状态机 | 低（概念） | 中 | 参考 |
| 模型矩阵（25 个 ONNX/LiteRT 模型） | 中（需跑模型） | 中（K40 端侧语音） | 观望，记清单 |

**总评**：speech-core 不抄代码（C++ 重），抄的是**架构判断**——「编排逻辑零 ML 依赖」这条铁律，跟我们 rf_brain 的协议无关层互相印证。它还是 K40 手机端侧语音的候选基础设施（如果未来 K40 要本地 STT/TTS，它的 Android LiteRT 后端 + 1.2GB 离线语音代理是现成方案）。

---

## 五、可执行验收

```bash
grep -c "编排" docs/speech-core-授粉报告.md          # ≥3
grep -c "协议无关" docs/speech-core-授粉报告.md       # ≥2
grep -c "Apache" docs/speech-core-授粉报告.md         # ≥1
grep -c "难度 × 收益" docs/speech-core-授粉报告.md     # ≥1
git diff --stat -- NEKO apiserver | wc -l             # 0
```

*授权：Apache-2.0 → 主仓 AGPL v3 允许直接吞。只读不改造（C++），授粉架构思想。源码归档在 github_haul/fusion/speech-core/。*
