# handcrafted-persona-engine · 系统骨架蒸馏

> 来源: elevenyellow/handcrafted-persona-engine（1363⭐，无 LICENSE，仅蒸馏不融合）
> 蒸馏日期: 2026-09-10 · 蒸馏人: 实验田维护者
> 代码路径: PersonaEngine.Lib/Assets/ + Bootstrapper/ + ASR/ + LLM/ + Core/Conversation/ + UI/
> 性质: 设计思想提炼，非代码搬运。

---

## 0. 概述

这个项目的"骨架"层解决一个 AI 桌宠最难的产品问题：**让一个对电脑一无所知的人，下载一个 exe 双击后，16GB 的模型自动下载安装、GPU 自动检测、坏文件自动修复、一切就绪**。这是它从"又一个 Demo"变成"可分发产品"的分水岭。

## 1. 资产安装管线（Assets/ + Bootstrapper/）⭐ 杀手锏

### 1.1 核心数据结构

```csharp
InstallManifest(SchemaVersion, ManifestVersion, Assets)  // 清单 = 版本 + 资产列表

AssetEntry(
    Id,               // 资产唯一 ID
    Kind,             // AssetKind（模型/音频/模型文件类型）
    DisplayName,
    Capability,       // 能力（ASR/TTS/LipSync/RVC...）
    ProfileTier,      // ProfileTier（Try/Stream/Build 三档安装档位）
    Required,         // 是否必须
    Source,           // AssetSource（HuggingFace 等）
    InstallPath,
    Sha256,           // ★ 哈希校验
    SizeBytes,
    Gates,            // ★ 特性门控（哪些 feature 需要此资产）
    ExtractArchive,   // 是否解压
    UserAssetCategory // 用户自定义资产类型
)
```

### 1.2 工作流

1. **ManifestLoader** 加载远端清单（JSON，ManifestJsonContext 源生成器序列化）。
2. **Bootstrapper** 启动时：GPU 预检（CUDA 能力检查）→ 逐资产对比本地 Sha256 → 缺失/不匹配 → 下载（断点续传）→ 校验 → 解压。
3. 三档安装档位（ProfileTier）：**Try**（最小下载）/ **Stream**（日常）/ **Build**（≈16GB 全量），用户双击后选档位。
4. `--repair` 重下哈希不符项、`--verify` 只校验不下载、`--offline` 失败即停。

### 1.3 AssetCatalog（运行时资产状态机）★ 设计精华

```csharp
IAssetCatalog
├── GetAssetState(AssetId) → AssetState(Missing/Ready/...)
├── IsFeatureEnabled(FeatureId) → bool
└── GetUserAssets(UserAssetType) → 用户自定义资产列表
```

关键实现点：
- **双缓存快照原子发布**：`Snapshot` 同时持有 asset-state 缓存和 feature 缓存，`Volatile.Write(ref _snapshot, BuildSnapshot())` 一次重建两个——**避免读到"资产已装但 feature 还显示缺失"的中间态**。这细节很高级。
- **UserContentWatcher**：监听用户资产目录（FileSystemWatcher，250ms debounce），变化时自动重建快照并触发 `Changed` 事件——用户往目录里丢一个 Live2D 模型，UI 实时刷新。
- **FrozenDictionary/FrozenSet**：.NET 8+ 不可变字典，查询零锁。
- **FeatureProfileMap**：feature → 所需资产集 + 档位映射，UI 开关背后自动启停资产。

**授粉要点**：这就是"模型管理"的标准答案。云服/NEKO 可以完全照搬这个模式：manifest(JSON) + sha256 + 档位 + 断点下载 + 双快照原子发布。Python 侧用 `asyncio` + 不可变 dataclass + `hashlib` 即可。

## 2. ASR 管线（ASR/）

### 2.1 分层

```
ISpeechTranscriptor            // 一次性转写
IRealtimeSpeechTranscriptor    // 流式转写（RealtimeTranscriptor）
    └── WhisperNetSpeechTranscriptor  // WhisperNet 实现
IVadDetector                   // VAD 检测
    └── SileroVadDetector      // Silero VAD
IVadProbabilityProvider        // 概率提供（供 UI 画波形）
```

### 2.2 事件驱动 VAD ⭐

- `IVadDetector.DetectSegmentsAsync()` 返回 `IAsyncEnumerable<VadSegment>`——**流式枚举**，边检测边吐段。
- `ProbabilityObserved` 事件：~31Hz 触发（16kHz 每 512 sample 一批），实时喂给 UI 的语音活动指示。
- VAD 与转写解耦：VAD 负责"什么时候有人说话"，转写负责"说了什么"，中间通过 VadSegment 衔接。
- `SileroInferenceState` 管理模型状态（Silero 是状态机模型，跨批保持 hidden state）。

**授粉要点**：Python 的 Silero VAD（onnxruntime）完全可以包成 `async generator + 事件`，这套抽象照抄即可。

## 3. LLM 集成（LLM/）

### 3.1 抽象

```csharp
IChatEngine.GetStreamingChatResponseAsync() → IAsyncEnumerable<string> → CompletionReason
IVisualChatEngine / VisualQASemanticKernelChatEngine  // 视觉 QA（截图→提问）
SemanticKernelChatEngine  // 基于 Semantic Kernel 的实现
VisualChatMessage(Query, ImageData)  // 带图消息
```

### 3.2 要点

- **流式 + 结构化返回**：`GetStreamingChatResponseAsync` 返回文本流 + 结束原因（CompletionReason：完成/中断/超时），上层据此决定"继续说还是闭嘴"。
- **ITextFilter**：输出过滤链（NameTextFilter 等）——LLM 输出过一遍过滤器再进 TTS/字幕。
- Semantic Kernel 只是实现细节，抽象层允许换任何 provider（OpenAI/Ollama/本地 GGUF）。
- 视觉引擎单独抽象（IVisualChatEngine），桌宠"看屏幕"与"聊天"解耦。

## 4. 对话编排（Core/Conversation/）⭐ 事件总线架构

### 4.1 双适配器对称

```csharp
IInputAdapter  : IAudioInputAdapter / ITextInputAdapter
IOutputAdapter : IAudioOutputAdapter / ITextOutputAdapter
```

输入输出各自抽象，事件流贯穿：

```
SttSegmentRecognizing（部分转写，实时）→ ... → TtsChunkEvent → PortaudioOutputAdapter
```

- `IConversationContext`：Participants（多方）、History（InteractionTurn 列表）、CurrentVisualContext（当前视觉上下文）。
- `MaxTurnsCleanupStrategy`：对话历史上限清理策略（可插拔：按轮数/按 token）。
- `TurnPipelineCoordinator`：把 ASR 段、LLM 响应、TTS 输出串成一个回合的状态机。

### 4.2 要点

- **事件全部是 record**（不可变），`IInputEvent/IOutputEvent` 标记接口区分方向。
- Adapter 模式：麦克风（PortAudio）、扬声器（PortAudio）、文本、字幕各自实现，对话核心不依赖具体 IO。
- 事件记录带 `SessionId/Timestamp/Duration/ProcessingDuration`——可观测性内建。

**授粉要点**：Python asyncio 版 = `asyncio.Queue` + dataclass 事件 + adapter 类，照搬这个对称抽象，对话管线可插拔（换麦克风/换字幕器/换 TTS 零侵入）。

## 5. 健康检查（Health/）

- `Health/Probes/`：探针体系，定期检测 GPU/模型/音频设备状态。
- 结合 `TtsOrchestrator.IsReady/LastInitError/ReadyChanged`：组件就绪状态事件化，UI 实时显示"哪里坏了、怎么修"。
- 这是桌宠"自愈"的基础：探针发现模型坏了 → 触发修复流程（--repair 等价逻辑）。

## 6. UI/Overlay 架构（概览）

```
UI/
├── ControlPanel/    // ImGui 控制面板（dashboard/voice/listening/avatar 面板）
├── Overlay/         // D3D11 透明叠加层（Live2D 渲染在桌面上）
├── Rendering/       // Silk.NET.OpenGL + Spout2（OBS 输出）
│   └── SpoutRegistry/SpoutManager  // Spout 纹理共享 → OBS 捕获
├── Host/            // 窗口宿主
└── Native/          // 原生互操作
```

- **ImGui 控制面板**：所有运行时开关（引擎切换、模型切换、VAD 阈值、试听）都做成实时面板。
- **Spout2**：把渲染画面共享给 OBS（VTuber 推流场景的核心），Windows 特有的纹理共享协议。
- `AnimatedFloat`（指数平滑动画值）：UI 数值变化也平滑，细节控。

## 7. 可授粉清单（云服/NEKO，Python）

| # | 设计 | 授粉难度 | 价值 |
|---|---|---|---|
| 1 | manifest+sha256+档位+断点下载 资产管线 | ★★★ | ⭐⭐⭐⭐⭐ 产品化关键 |
| 2 | 双快照原子发布（避免中间态） | ★★★ | ⭐⭐⭐⭐ 状态一致性 |
| 3 | 用户资产目录 watcher + debounce | ★★ | ⭐⭐⭐⭐ 热插拔模型 |
| 4 | IAsyncEnumerable 流式 VAD + ~31Hz 概率事件 | ★★ | ⭐⭐⭐⭐ 实时语音反馈 |
| 5 | IChatEngine/IVisualChatEngine 分离 | ★ | ⭐⭐⭐ |
| 6 | 输入/输出双适配器对称抽象 | ★★ | ⭐⭐⭐⭐ 管道可插拔 |
| 7 | record 事件 + 可观测性字段 | ★ | ⭐⭐⭐ |
| 8 | 探针式健康检查 + ReadyChanged | ★★ | ⭐⭐⭐ 自愈 |

## 8. 依赖与不可移植项

- Windows x64 / D3D11 / Spout2 / Silk.NET.OpenGL / ImGui（.NET 绑定）。
- NVIDIA CUDA + ONNX Runtime（ASR/TTS/RVC 全走 GPU）。
- .NET 9 + Semantic Kernel + OpenAI SDK。
- 模型资产托管在 HuggingFace，总量 ~16GB。

---
*蒸馏说明：以上基于源码阅读提炼的设计思想与接口骨架，非源码复制。项目无 LICENSE，任何落地实现需从零写或选有许可的等价实现。*
