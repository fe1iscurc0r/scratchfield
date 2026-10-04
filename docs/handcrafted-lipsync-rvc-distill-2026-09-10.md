# handcrafted-persona-engine · Live2D 唇形同步 & RVC 蒸馏

> 来源: elevenyellow/handcrafted-persona-engine（1363⭐，无 LICENSE，仅蒸馏不融合）
> 蒸馏日期: 2026-09-10 · 蒸馏人: 沈遥
> 代码路径: PersonaEngine.Lib/Live2D/Behaviour/LipSync/ + PersonaEngine.Lib/TTS/RVC/
> 性质: 设计思想提炼，非代码搬运。无 LICENSE 项目，仅做理解参考，禁止复制进仓。

---

## Part A · 唇形同步（用户最关心）

## A0. 双引擎架构

`LipSyncEngine` 枚举（Configuration）：
- **VBridger**：音素驱动（Phoneme-based），快、随处可跑——**主推**，本项目重点蒸馏对象。
- **Audio2Face**：神经引擎（Audio2Face blendshape solver），更高保真、更重。

两个实现：
- `VBridgerLipSyncService`（音素级，949 行，核心）
- `LipSyncAnimationService`（音频能量级，更简单，直接平滑 ParamMouthOpenY）

## A1. 核心数据结构：PhonemePose（音素→口型 9 维向量）

```csharp
public struct PhonemePose {
    MouthOpenY;        // 0-1  嘴张多大
    JawOpen;           // 0-1  下巴开度
    MouthForm;         // -1(撇嘴)~+1(笑) 嘴角上下
    MouthShrug;        // 0-1  嘴唇上耸/紧绷
    MouthFunnel;       // 0-1  嘟嘴前凸
    MouthPuckerWiden;  // -1(宽)~+1(噘)  嘴宽
    MouthPressLipOpen; // -1(抿薄)~0(触)~+1(露齿)
    MouthX;            // -1~1 水平位移
    CheekPuffC;        // 0-1  鼓腮
}
```

映射到一个 **Dictionary<string, PhonemePose>** —— 这就是全部秘密：**一个 IPA 音素对应一组 9 维 Live2D 参数**。这是纯手工调的表（代码注释里标注了每个音素的口型逻辑：塞音要闭唇+鼓腮、擦音要气流形状、鼻音要近闭、元音按开口度）。

示例（从源码提取的真实值）：
| 音素 | MouthOpenY | JawOpen | MouthForm | Funnel | PuckerWiden | PressLip | CheekPuff |
|---|---|---|---|---|---|---|---|
| b | 0 | 0 | 0 | 0 | 0 | -1.0 | 0.6 |
| p | 0 | 0 | 0 | 0 | 0 | -1.0 | 0.8 |
| s | 0 | 0 | +0.3 | 0 | -0.6 | +0.9 | 0 |
| ʃ (sh) | 0.1 | 0 | 0 | 0.9 | 0.6 | 0.2 | 0 |
| w | 0.1 | 0.1 | 0 | 1.0 | 0.9 | -0.3 | 0 |
| m | 0 | 0 | 0 | 0 | 0 | -1.0 | 0 |
| ə (schwa) | 0.3 | 0.3 | 0 | 0 | 0 | 0.5 | 0 |
| i | 0.1 | 0.1 | 0.7 | 0 | -0.8 | 0.8 | 0 |
| SIL | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**授粉要点**：这套表就是"中文拼音口型表"的最佳模板——拼音有 60+ 个声韵母，照这个格式给每个拼音填 9 个参数，就能驱动任何 Live2D 模型。注意它用了 `PhonemePose(pressLip: -1.0f, cheekPuff: 0.6f)` 这种命名参数写法，不传的默认 0，所以很多音素只写差异维度。

## A2. 核心算法：双目标插值 + 指数平滑（⭐ 全项目最精华的动画手法）

### 状态
```csharp
List<TimedPhoneme> _activePhonemes;   // 当前活跃的音素时间轴
PhonemePose _currentTargetPose;       // 当前音素目标
PhonemePose _nextTargetPose;          // 下一个音素目标
float _interpolationT;                // 0→1 插值进度
Dictionary<string,float> _currentParameterValues;  // 当前实际参数值
```

### Update 每帧
```csharp
var easedT = Easing.EaseInOutQuad(_interpolationT);
var frameTargetPose = PhonemePose.Lerp(_currentTargetPose, _nextTargetPose, easedT);
SmoothParametersToTarget(frameTargetPose, deltaTime);
ApplySmoothedParameters();
```

两层平滑：
1. **音素间过渡**：当前音素 → 下一音素用 `EaseInOutQuad` 缓动 + `PhonemePose.Lerp` 插值（`_interpolationT` 在音素切换时推进）。这是"口型不是瞬间跳变而是圆润过渡"的关键。
2. **参数逼近**：每个参数向目标用 `Lerp(current, target, SMOOTHING_FACTOR * dt)`，`SMOOTHING_FACTOR = 35.0f`——指数衰减逼近，越快越跟手，越慢越柔。

### 空闲回归
`SMOOTHING_FACTOR=35`（跟手）vs `NEUTRAL_RETURN_FACTOR=15`（回归中性更慢）——**说话快、闭嘴慢**，符合自然表情节奏。`NEUTRAL_THRESHOLD=0.02f`：低于此值视为中性，停止抖动。

### 特殊维度
`CheekPuff` 特殊处理：目标>阈值时按平滑系数上升，否则按 `CHEEK_PUFF_DECAY_FACTOR=80` 快速衰减回 0——鼓腮是爆发性动作，要快收。

## A3. 音素时间轴构建（AppendPhonemes）⭐

TTS 给的是**词级 token 带音素串和起止时间**，唇形同步需要**音素级**时间：

```csharp
foreach token in segment.Tokens:
    tokenDuration = tokenEnd - tokenStart
    timePerPhoneme = tokenDuration / phonemeChars.Count   // 均分
    foreach phChar in SplitPhonemes(token.Phonemes):
        _activePhonemes.Add(new TimedPhoneme(phChar, t, t + timePerPhoneme))
```

- `SplitPhonemes` 会忽略 `ˈ ˌ ː`（重音/音长符号——不影响口型）。
- 时间用 `Math.Max(lastEndTime, token.Start + offset)` 保证**单调不重叠**。
- `_cumulativeTimeOffset`：跨音频块时累计时间偏移，让时间轴连续。

**授粉要点**：这是"词级时间→音素级时间"的最简实现（均分），配 TokenTimingUtils 的加权版本，Python 直接可复刻。

## A4. 播放进度驱动（非自算时钟）⭐

**关键思想**：不用自己的时钟推时间，而是订阅音频播放器的进度事件：

```csharp
_audioProgressNotifier.ChunkPlaybackStarted += HandleChunkStarted;
_audioProgressNotifier.ChunkPlaybackEnded   += HandleChunkEnded;
_audioProgressNotifier.PlaybackProgress     += HandleProgress;
```

`Update(dt)` 里用**实际播放位置**（来自声卡回调）查 `FindPhonemeIndexAtTime(currentTime)`，找到当前音素索引。这样：**音频和口型永远不会漂移**——漂移只来自音频实际播放进度，而不是合成时间轴。

`FindPhonemeIndexAtTime`：先检查当前索引是否还在有效区间（快速路径），再线性向后搜（start ≤ t < end+1ms 容差）。

## A5. 与表情/眨眼的协同

`AnimationServiceBase` + `ILive2DAnimationService` 接口：唇形、表情（Emotion/）、眨眼（IdleBlinkingAnimationService）都是独立 service，各自实现 `Start/Stop/Update`。上层把参数合并写入模型——**唇形只管口部参数，表情管眉毛眼睛，互不打架**。

## Part B · RVC 音色转换管线

## B1. 总体数据流

```
输入音频块 → RVCFilter.Process()
  → AudioPreprocessor（重采样到 16kHz）
  → IF0Predictor（CrepeOnnxSimd / RmvpeOnnx）→ f0 基频
  → ContentVec → 内容特征
  → MelSpectrogram → 频谱
  → OnnxRVC.ProcessAudio（HuBERT 风格特征 + f0 + 频谱 → 转换后音频）
  → 输出重采样回目标采样率
```

## B2. 关键组件

| 组件 | 职责 |
|---|---|
| `RVCFilter` | 总入口：缓冲、分块、缓存、并发保护、选项热更新 |
| `IF0Predictor` | 基频预测抽象（Crepe/RMVPE 两实现，可插拔） |
| `CrepeOnnxSimd` | Crepe: 16kHz, WINDOW=1024, HOP=10ms, 360 音高桶, BATCH=512, **SIMD 扁平数组优化** |
| `RmvpeOnnx` | RMVPE: 更准的 f0 |
| `ContentVec` | 内容特征提取（音色无关） |
| `OnnxRVC` | 核心转换：`OnnxRVC(modelPath, hopsize, vecPath)` + `ProcessAudio()` |
| `RVCVoiceProvider` | 音色库管理（IRVCVoiceProvider） |
| `RvcOverride` | 单次试听覆盖（A/B 对比不同音色） |

## B3. 工程亮点

1. **块式处理**：`ProcessInChunks` 按窗口分块（MinWindowSamples=24000=1s@24kHz），不整段阻塞；`MaxInputDuration=30s` 上限。
2. **试听缓存（AuditionCache）**：`Dictionary + LinkedList LRU`，容量 2——ONNX session 构建是**多秒级**的，缓存最近试听的 (predictor, model) 对，A/B 对比音色不卡。
3. **并发安全**：`SemaphoreSlim _initLock`（初始化互斥）+ `ReaderWriterLockSlim _modelLock`（模型读写）+ `volatile _currentOptions`（无锁读配置）——热更新选项时不撕裂。
4. **优先级/最小样本**：`Priority=100`（音频过滤器链中的顺序），`MinimumSampleCount` 告知上游"少于多少样本别喂我"。
5. **RvcOverride**：试听时不重建全局模型，用 override 换音色——避免打断正在跑的转换。

## B4. 可移植性评估

- **算法可复刻**：f0 预测 + 内容特征 + 频谱 + 神经转换 是 RVC 标准流水线，Python 侧有成熟 RVC 推理实现（`rvc-python` 等，MIT/Apache 许可可查）。
- **不可直接搬**：ONNX 模型（需单独下载，RVC 模型权重许可各不同）、CUDA。
- **授粉建议**：NEKO 若要做"声音克隆"，直接用现成 RVC 推理库（Python），不必复刻 C# 实现；但"试听 LRU 缓存 + 块式处理 + 并发保护"三个工程模式值得抄进自己的音频管线。

## Part C · 可授粉清单（NEKO/Lumo，Python/前端）

| # | 设计 | 授粉难度 | 价值 |
|---|---|---|---|
| 1 | IPA/拼音→9维口型表 | ★（纯数据） | ⭐⭐⭐⭐⭐ 唇形同步地基 |
| 2 | 双目标插值 EaseInOutQuad + Lerp 平滑 | ★★ | ⭐⭐⭐⭐⭐ 口型圆润 |
| 3 | 播放进度事件驱动（不自己算时钟） | ★★ | ⭐⭐⭐⭐⭐ 永不漂移 |
| 4 | 说话快/闭嘴慢双因子 | ★（两个常量） | ⭐⭐⭐⭐ 自然感 |
| 5 | 词级→音素级时间均分 | ★ | ⭐⭐⭐⭐ |
| 6 | 音频过滤器链 Priority/MinimumSampleCount | ★★★ | ⭐⭐⭐ 管道纪律 |
| 7 | 模型试听 LRU 缓存 | ★★★ | ⭐⭐⭐ 体验优化 |
| 8 | 忽略重音/音长符号（ˈˌː） | ★ | ⭐⭐ 细节 |

---
*蒸馏说明：以上基于源码阅读提炼的设计思想与算法流程，非源码复制。项目无 LICENSE，任何落地实现需从零写或选有许可的等价实现。*
