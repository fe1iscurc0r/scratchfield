# handcrafted-persona-engine · TTS 引擎蒸馏

> 来源: elevenyellow/handcrafted-persona-engine（1363⭐，无 LICENSE，仅蒸馏不融合）
> 蒸馏日期: 2026-09-10 · 蒸馏人: 实验田维护者
> 代码路径: src/PersonaEngine/PersonaEngine.Lib/TTS/
> 性质: 设计思想提炼，非代码搬运。无 LICENSE 项目，仅做理解参考，禁止复制进仓。

---

## 0. 一句话

这是整个项目里**工程含量最高**的子系统：把 LLM 流式文本 → 增量分句 → 双引擎合成（轻量 Kokoro / 表达力 Qwen3）→ 音素化 → CTC 强制对齐 → token 级时序 → 增量音频块输出，一路都是可插拔接口，且为"低首字延迟 + 边合成边播放"做了大量优化。

## 1. 核心抽象（接口层次）

```
ITtsEngine (生命周期: IDisposable, IsReady/LastInitError/ReadyChanged 事件)
└── TtsOrchestrator        ← 总编排：失败自愈状态机，SynthesizeStreamingAsync()
    └── ISentenceSynthesizer : IAsyncDisposable   ← 单引擎句子合成器
        ├── KokoroSentenceSynthesizer  (轻量, 7 文件)
        └── Qwen3SentenceSynthesizer   (表达力, 12 文件)
    └── ITtsEngineProvider   ← 引擎选择/工厂
    └── ITtsCache            ← 合成缓存 (TtsMemoryCache)
    └── IncrementalSentenceAccumulator ← 流式文本 → 完整句子
```

关键设计：
- `ITtsEngine` 只暴露状态与流式入口，具体引擎完全隔离——**换引擎不动上层**。
- `TtsEngineCapabilities` 枚举 + `TtsEngineInfo(EngineId, Capabilities)` 让上层按能力选择（哪些引擎支持表达力、支持缓存等）。
- `TtsOrchestrator` 有 `_isReady/_lastInitError/ReadyChanged`：初始化失败后上层可监听并重试，不是一次性启动。

## 2. 增量句子积累器（IncrementalSentenceAccumulator）★ 最值得抄的设计

**问题**：LLM 流式吐 token，不能等整段说完再合成（首字延迟爆炸），也不能每个 token 都合成（碎片化、上下文丢失）。

**方案**：
```csharp
Append(chunk)                     // 流式进来先塞 StringBuilder(4096)
TakeCompletedSentences()          // 返回完整句子列表（如果有）
Flush()                           // 流结束时取剩余尾巴
Reset()
```

三个关键优化点：
1. **标点预检**：先查 buffer 里有没有句末标点 `. ! ? ; : —`，**没有就直接返回空**——避免为 ~90% 不含句界的 LLM token 块做昂贵的归一化+分句。
2. **分句后保留最后一段**：`Segment()` 出 N 句，只返回前 N-1 句，最后一句留 buffer 里等后续补全（防止把半截句子切出去）。
3. 归一化（ITextNormalizer）与分句（ISentenceSegmenter）都走接口，OpenNLP 只是默认实现——可换中文分句器。

**授粉要点**：Python 里等价实现 = `append()` + `re.search(r'[。！？；：.!?;:]', buf)` 预检 + `split_sentences()`，几百行内可复刻，直接改善 AI 伴侣流式 TTS 的首字延迟。

## 3. 文本处理管线（TextProcessing/）

```
ITextNormalizer → ISentenceSegmenter → IMlSentenceDetector
    TextNormalizer       SentenceSegmenter     OpenNlpSentenceDetector
    Num2Words            (分句实现)
```

- 数字转词（Num2Words）在 TTS 里是必须的："123" 读成 "one hundred twenty three" 而非逐位。
- 分句器基于 OpenNLP（Java 移植），可替换。

## 4. 音素化（Phonemization/）— 29 个文件，很重

```
IPhonemizer
├── PhonemizerG2P          ← 主入口：文本 → IPA 音素序列
└── IFallbackPhonemizer    ← espeak 兜底（EspeakFallbackPhonemizer/EspeakResolver）
ILexicon                   ← 词典查询（Lexicon + LexiconEntry，JSON 可加载）
IPosTagger                 ← 词性标注（OpenNlpPosTagger）
```

管线：`TextPreprocessor.Preprocess()` → `TokenAligner`（对齐文本/词典）→ `TokenRestructurer`（重组）→ G2P 输出音素。
词性标注参与 G2P 是因为**同形异义词**（read / present）发音不同——靠词性消歧。
兜底链：词典 → 规则 G2P → espeak，逐级降级。

**授粉要点**：中文 TTS 不需要 IPA（用拼音），但这套"词典优先 → 规则 → 兜底"的三级降级思想直接适用拼音转写；词性消歧对英文 G2P 有意义，中文基本不用。

## 5. CTC 强制对齐（Alignment/CtcForcedAligner）★ 技术含量最高

**目的**：拿到音频里每个词/音素的起止时间戳——这是唇形同步、字幕、RVC 对齐的基石。

**实现**：wav2vec2.0 CTC 模型（VocabSize=32，`<pad>`=blank，`|`=词界）+ 16kHz 重采样。

核心方法：
```csharp
Align(audio, text, sampleRate)          // 全段对齐
AlignSpokenWindowed(audioWindow, remainingText, sampleRate, windowStartTime)  // 窗口式流式对齐
```

**窗口式对齐（AlignedSpokenWindowed）是亮点**：
1. 对音频窗口跑 wav2vec2 → logits。
2. **GreedyDecode 先粗解码**，跟 `remainingText` 比对（CountSpokenWords）确认"这个窗口里到底说了哪几个词"。
3. 只对**确认出现的词**构建 CTC labels，跑 **ViterbiAlign** 精对齐（含 blank 跳过、重复合并、filler 处理）。
4. 输出相对窗口时间，再 offset 成绝对时间。

**好处**：窗口切哪、切多长不用猜，模型自己告诉你哪些词落地了；避免整段长文本 Viterbi 爆炸，支持流式持续对齐。

配套常量：`SimilarityThreshold=0.5f`、`MaxOverlapSkip=3`（相邻窗口重叠容错）。

## 6. Token 时序分配（TokenTimingUtils）★ 唇形同步的前置

TTS 引擎给的是**词级** (start,end) 边界，但要驱动唇形需要**音素级**时序。`DistributeTimings` 把词的时间区间按权重比例摊到该词的每个 token 上：

```csharp
DistributeTimings(tokens, start, count, startTime, endTime, sliceOffset, weightSelector)
```
- 权重 = token 音素数（clamp ≥1），时间按权重占比切分。
- `sliceOffset` 把所有时间戳平移为相对当前音频片段的（流式场景必须）。

**授粉要点**：这就是"词级时间 → 音素级时间"的标配分摊法，Python 20 行内可复刻。

## 7. 双引擎对比

| 维度 | Kokoro | Qwen3 (expressive) |
|---|---|---|
| 定位 | 轻量、首字快、日常 | 表达力强（情绪/韵律）、重 |
| 文件数 | 7 | 12 |
| 关键类 | KokoroSentenceSynthesizer, KokoroVoiceProvider, KokoroTokenConverter, KokoroVoiceEmbedding | Qwen3SentenceSynthesizer, Qwen3StreamingAudioDecoder, LlamaTtsModel/Gguf, Qwen3Sampler, Qwen3TextTokenizer |
| 推理栈 | ONNX | **GGUF + llama.cpp 系**（Qwen3TtsGgufEngine, GgufEmbeddingManager） |
| 特色 | 轻量 embedding 化音色 | **流式解码器带 KV-cache（8 层 transformer）+ 卷积历史缓冲**，边解码边吐音频块 |

Qwen3 流式解码器（`Qwen3StreamingAudioDecoder`）维护 KV-cache + 卷积历史 buffer——这是"边合成边输出"的关键，不是整句合成完才出声。**这正是 AI 伴侣 TTS 最想要的体验**（首块音频 <1s）。

## 8. 工程亮点汇总（可直接授粉到 NEKO/Lumo）

1. **增量句子积累 + 标点预检**：Python 直接抄，改善流式 TTS 首字延迟。⭐
2. **引擎可插拔 + Capabilities 描述**：TTS 引擎按能力注册/选择，换引擎零侵入。
3. **词级→音素级时间分摊**：TokenTimingUtils，唇形同步前置必备。
4. **窗口式 CTC 对齐（先粗解码确认再精对齐）**：流式场景算力友好。
5. **espeak 兜底链**：词典 → 规则 G2P → espeak，永不死路。
6. **缓存层**（ITtsCache/TtsMemoryCache）：相同句子不重合成，聊天场景命中率高。

## 9. 不可移植 / 依赖

- .NET 9 / Microsoft.ML.OnnxRuntime / CUDA。
- Qwen3 GGUF 路径依赖 llama.cpp 绑定，Python 侧可用 llama-cpp-python 等价。
- wav2vec2 CTC 对齐模型需单独下载（~300MB 级），中文有 wav2vec2-zh 可用。

## 10. 给 NEKO/Lumo 的落地建议（优先级排序）

1. **P0**：增量句子积累器（标点预检版）→ 直接进 LLM→TTS 管道。
2. **P0**：词级→音素级时间分摊 → 唇形同步前置。
3. **P1**：引擎可插拔 + Capabilities（Kokoro/Qwen3 等引擎并存切换）。
4. **P1**：双引擎配置：轻量日常 + 表达力可切换。
5. **P2**：CTC 窗口式对齐（若需要字幕/逐词高亮/唇形强同步）。
6. **P2**：TTS 结果缓存（相同句子幂等）。

---
*蒸馏说明：以上基于源码阅读提炼的设计思想与接口骨架，非源码复制。项目无 LICENSE，任何落地实现需从零写或选有许可的等价库。*
