# NEKO 语音 Pipeline 配置化 · R-01 勘察报告

- 日期：2026-08-24
- 批次：第八批工单（SPEC-13 三链路授粉落地）· R 线 R-01
- 上游参照：ai-bot-pro/achatbot（BSD-3-Clause，89★，基于 apipeline / pipecat 派生 Frame-Processor 架构）
- 勘察范围：achatbot `src/processors/` 的 VAD / Turn / ASR / LLM / TTS 五段接口契约，对照 NEKO 现有 `main_logic/voice_turn`、`voice_input`、`voice_identity`、`asr_client`、`tts_client`
- 纪律：只读勘察；不 copy achatbot 源码，全部按接口描述重写为契约行

---

## 0. 结论摘要

achatbot 的语音链路是**帧驱动的 Processor 流水线**：音频以 `Frame` 形式在各独立 Processor 间单向流动，`VAD / Turn / ASR / LLM / TTS` 各自封装为可独立替换的 Processor，由 pipeline 配置（YAML）按名称组装。五段均有明确的基类抽象与输入输出帧契约。

NEKO 现状是**回调/会话驱动**：ASR 是 `create_asr_session` 回调会话（8 个 worker + provider 注册表），TTS 是 `get_tts_worker` 分发 + priority 注册表（15 个 worker）。TTS 侧已具备与 achatbot 同级别的"配置驱动可插拔"能力（甚至更成熟）；主要差距在 **VAD 段缺少独立 analyzer 抽象**、**LLM 段缺少 processor 抽象层**、以及**整链缺少统一 JSON pipeline 配置**。

R-02 只需做"最小加法"：新增 `voice_pipeline/` 五段抽象基类 + 注册表 + `pipeline_config.json`，把现有 ASR/TTS 会话入口封装为后端，不删旧路径。

---

## 1. achatbot 接口契约提取表

### 1.1 VAD 段

| 项 | 契约 |
|---|---|
| 分析器 | 独立 pip 包（`silero_vad_analyzer`、`webrtc_vad_analyzer`），非主仓源码；产出 `VADStateAudioRawFrame` |
| 输出帧 | `VADStateAudioRawFrame(state=SPEAKING/QUIET, is_final, speech_id, start_at_s, end_at_s, audio, sample_rate, num_channels, sample_width)` |
| 消费处理器 | `VADAudioProcessor` / `VADAudioSaveProcessor`（均继承 `AsyncFrameProcessor`）：按 `speech_id` 聚合说话段 → 产出 `VADAudioRawFrame`（或落盘 wav 产出 `PathAudioRawFrame`） |
| 核心参数 | silero-vad 上游：`threshold≈0.5`、`min_speech_duration_ms≈250`、`speech_pad_ms≈300`；流式状态机 `VADIterator`（`triggered` / `temp_end`） |
| 输入输出 | `AudioRawFrame` → `VADStateAudioRawFrame` → `VADAudioRawFrame`（一段完整语音） |

### 1.2 Turn 段

| 项 | 契约 |
|---|---|
| 机制 | 无独立 turn 目录；turn 由 **VAD/端点事件帧 + aggregator 聚合** 共同完成 |
| 控制帧 | `UserStartedSpeakingFrame` / `UserStoppedSpeakingFrame`（说话起止）；`StartInterruptionFrame`（打断/插话） |
| 聚合器 | `LLMUserResponseAggregator`（继承 `LLMResponseAggregator`）：start=`UserStartedSpeakingFrame`，end=`UserStoppedSpeakingFrame`，accumulator=`TranscriptionFrame`，interim=`InterimTranscriptionFrame`；聚合完成 append 到 `messages` 并 push `LLMMessagesFrame` |
| assistant 侧 | `LLMAssistantResponseAggregator`：start=`LLMFullResponseStartFrame`，end=`LLMFullResponseEndFrame`，accumulator=`TextFrame`，`handle_interruptions=True` |
| 纯文本聚合 | `LLMFullResponseAggregator`：收到 `LLMFullResponseEndFrame` 前累积 `TextFrame`，结束时一次性下发完整 `TextFrame` |
| 语义判定 | 无概率化语义端点；turn 完成 = 「结束说话帧」+ ASR final 文本已到 |

### 1.3 ASR 段

| 项 | 契约 |
|---|---|
| 基类 | `ASRProcessorBase(AsyncAIProcessor)`，`sample_rate=16000` |
| 抽象方法 | `set_model(model)` / `set_language(lang)` / `set_asr_args(**kw)` / `run_asr(audio) -> AsyncGenerator[Frame]` |
| 输入输出 | 消费 `AudioRawFrame` → 产出 `TranscriptionFrame`（final）/ `InterimTranscriptionFrame`（partial） |
| 子类生态 | `deepgram_asr_processor`、`asr_processor`、`asr_live_processor`；pip extras 默认包含 `sense_voice_asr`（阿里 SenseVoice） |
| 可插拔 | 换 ASR 后端 = 换 processor 类 + 配置项，流水线结构不变 |

### 1.4 LLM 段

| 项 | 契约 |
|---|---|
| 基类 | `LLMProcessor(AIProcessor)` |
| 关键方法 | `set_model(model)`、`register_function(function_name, callback)`、`has_function()`、`request_image_frame()`、`start_llm_usage_metrics(tokens)` |
| 输入输出 | 消费 `TextFrame`/`LLMMessagesFrame` → 产出 `TextFrame`（流式增量）+ `LLMFullResponseStartFrame`/`LLMFullResponseEndFrame` |
| 工具调用 | 函数回调注册制：`register_function` 把工具名绑到回调，LLM 请求工具时回调执行 |
| 子类生态 | `openai_llm_processor`、`google_llm_processor`、`litellm_processor` |

### 1.5 TTS 段

| 项 | 契约 |
|---|---|
| 基类 | `TTSProcessorBase(AIProcessor)` |
| 构造参数 | `aggregate_sentences` / `push_text_frames` / `sync_order_send` / `remove_punctuation` |
| 抽象方法 | `set_voice(voice)` / `set_tts_args(**kw)` / `run_tts(text)` |
| 流信息 | `get_stream_info()` → `{sample_rate:16000, sample_width:2, channels:1}` |
| 事件帧 | `TextFrame` 触发 → `TTSStartedFrame` / `TTSSpeakFrame` / `TTSStoppedFrame` / `TTSVoiceUpdateFrame` |
| 句子聚合 | `match_endofsentence()` 按句末标点切句；pip extras 默认包 `tts_edge`（Edge TTS） |
| 子类生态 | `cartesia_tts_processor`、`deepgram_tts_processor`、`elevenlabs_tts_processor`、`openai_tts_processor`、`tts_processor` |

---

## 2. NEKO 现状 → achatbot 参照 → 差距（五段对照表）

| 段 | NEKO 现状（现有契约） | achatbot 参照 | 差距 |
|---|---|---|---|
| VAD | 无独立 VAD analyzer 抽象；`SpeechActivityEvent(NONE/SPEECH_STARTED/CANDIDATE_PAUSE/SPEECH_RESUMED)` 作为"廉价 VAD 事件"挂在 ASR 会话回调 `on_speech_activity`；语音段分段逻辑内嵌在 ASR 会话运行时 | 独立 vad analyzer 包产出 `VADStateAudioRawFrame(state/is_final/speech_id)`，`VADAudioProcessor` 按 speech_id 聚合成 `VADAudioRawFrame` | 缺"帧级 VAD 状态机 + speech_id 分段聚合"的独立抽象；VAD 与 ASR 会话强耦合 |
| Turn | `TurnDetector` Protocol（`on_speech_started`/`evaluate(audio_tail)->TurnEvaluation`/`reset`/`close`）；`TurnDecision(INCOMPLETE/COMPLETE)` + 概率 + generation 防重放；`AsrTurnCapabilities(semantic_endpoint)` 决定是否外挂语义端点检测 | turn = VAD/端点事件帧（`UserStarted/StoppedSpeakingFrame`）+ `LLMUserResponseAggregator` 聚合 ASR final 文本 → `LLMMessagesFrame` | NEKO 的语义端点检测（概率化 evaluate）**强于** achatbot（无概率语义判定）；但缺"说话起止事件帧"与"aggregator 聚合"的显式契约 |
| ASR | `create_asr_session(core_type, config, on_input_transcript, on_connection_error, on_status_message, on_speech_activity, on_turn_endpointed, ...)`；8 workers（dummy/qwen/openai/step/grok/glm/gemini/soniox）+ `_CORE_ASR_ROUTES` 路由表 + provider 注册表 + 凭证校验；`ASR_PROVIDER` 环境变量仅支持 dummy | `ASRProcessorBase` 帧驱动：`AudioRawFrame` → `TranscriptionFrame`；`set_model/set_language/set_asr_args/run_asr` 抽象 | NEKO 已是"provider 可插拔 + 凭证校验"，缺统一帧输入抽象与 `run_asr` 基类契约（R-02 用基类包装 `create_asr_session` 即可对齐） |
| LLM | 无独立 LLM processor 抽象层（LLM 调用在 core 侧，不在 voice 链路内独立成段） | `LLMProcessor`：`set_model`/`register_function`/`has_function`/`request_image_frame`，流式 `TextFrame` + `LLMFullResponseStart/EndFrame` | 缺 LLM 段抽象基类（R-02 先以接口描述占位，不引入新调用路径） |
| TTS | `get_tts_worker(core_api_type, has_custom_voice, voice_id) -> (worker_fn, api_key_override, provider_key)`；`TTSProvider` 注册表按 priority 匹配（gptsovits=10/vllm_omni=20/custom=25/minimax=30/elevenlabs=40/cosyvoice=50/mimo=60/doubao_tts=65）+ capabilities（clone/design/preset）+ `SentenceBuffer` 句子缓冲 | `TTSProcessorBase`：`set_voice/set_tts_args/run_tts` 抽象 + `get_stream_info()` + `TTSStarted/TTSSpeak/TTSStopped` 事件帧 + `match_endofsentence()` 切句 | 注册表/priority/降级机制 NEKO **优于** achatbot；缺统一 `run_tts(text)` 基类契约与事件帧产出（R-02 用基类包装现有 worker） |

---

## 3. NEKO 差距清单（供 R-02 落地）

1. **缺五段统一抽象**：VAD/Turn/ASR/LLM/TTS 无一组可配置的基类接口（`run()` + `config` 契约），各段散落在 `voice_turn`/`voice_input`/`asr_client`/`tts_client`。
2. **缺后端注册表**：TTS 已有 priority 注册表，ASR 有路由表，但无"按配置名统一查找"的 voice_pipeline 级注册表。
3. **缺 pipeline JSON 配置**：链路组成/顺序/后端名没有一份声明式配置（换后端要动代码或环境变量）。
4. **VAD 与 ASR 强耦合**：VAD 事件经由 ASR 会话回调透出，无独立分段帧。
5. **LLM 段空白**：无 processor 抽象（本轮以接口占位，不新建调用路径）。
6. **降级路径未显式化**：后端缺依赖/未装时应走 dummy/直调旧路径，需在注册表查找失败时显式降级。

---

## 4. 配置化改造建议（R-02 设计输入）

### 4.1 目标形态

```
NEKO/N.E.K.O/main_logic/voice_pipeline/
├── base.py               # 五段抽象基类（VAD/Turn/ASR/LLM/TTS，run()/config 契约）
├── registry.py           # 后端注册表（按配置名查找，缺后端显式降级）
├── pipeline_config.json  # 默认 pipeline 配置（照 round5 §3.2）
└── ...（Edge TTS / ASR 后端封装，降级路径）
```

五段基类统一契约（接口描述，非 achatbot 代码）：

```python
class VoicePipelineStage(ABC):
    """五段统一基类：config 声明式注入，run() 为统一入口。"""
    name: str = ""

    def __init__(self, config: dict): ...
    @abstractmethod
    async def run(self, *args, **kwargs): ...
    @abstractmethod
    def close(self) -> None: ...

class VADStage(VoicePipelineStage): ...   # 帧级 VAD 状态机 + 分段
class TurnStage(VoicePipelineStage): ...  # 语义端点检测（复用 voice_turn.TurnDetector）
class ASRStage(VoicePipelineStage): ...   # 包装 asr_client.create_asr_session
class LLMStage(VoicePipelineStage): ...   # 接口占位（不引新调用路径）
class TTSStage(VoicePipelineStage): ...   # 包装 tts_client.get_tts_worker
```

### 4.2 pipeline JSON 配置示例（照 round5 §3.2）

```json
{
  "version": 1,
  "pipeline": {
    "vad": "silero_vad",
    "turn": "energy_threshold",
    "asr": "sense_voice",
    "llm": "openai",
    "tts": "edge_tts"
  },
  "stage_config": {
    "silero_vad": {
      "threshold": 0.5,
      "min_speech_duration_ms": 250,
      "speech_pad_ms": 300
    },
    "energy_threshold": {
      "silence_timeout_ms": 800,
      "energy_floor": 0.02
    },
    "sense_voice": {
      "sample_rate": 16000,
      "language": "auto"
    },
    "openai": {
      "model": "gpt-4o-mini",
      "base_url": ""
    },
    "edge_tts": {
      "voice": "zh-CN-XiaoxiaoNeural",
      "rate": "+0%"
    }
  },
  "fallback": {
    "asr": "dummy",
    "tts": "dummy"
  }
}
```

### 4.3 换后端只改配置（目标行为）

- `"tts": "edge_tts"` → `"tts": "qwen"`：只改 JSON，registry 按名查 `tts_client` 封装的后端；缺依赖（如 Edge TTS 未装）走 `fallback.tts = "dummy"`，旧直调路径不变。
- `"asr": "sense_voice"` → `"asr": "qwen"`：同理走 `asr_client.create_asr_session` 包装；凭证缺失显式报 `ASR_CREDENTIALS_MISSING` 或降级 dummy。
- `"turn": "energy_threshold"` → `"turn": "semantic"`：从能量阈值端点切到 `voice_turn.TurnDetector` 语义端点，复用现有契约。

---

## 5. 授粉纪律声明

- achatbot 仅作**只读参照**（BSD-3-Clause），未 copy 任何源码；上表全部为按上游公开接口重写的**契约描述**。
- R-02 落地遵循：最小改动加抽象、不删旧路径、缺后端走降级、不碰 NEKO 记忆层。
