# OpenArc 评估报告 · 冥王峡谷语音栈一体化候选（智能体 06 / 06-01）

> 评估对象：SearchSavior/OpenArc（Apache-2.0，511★，Python）
> 源码基线：main @ 92e6e1d（2026-08-22），版本 v2.0.5（pyproject.toml）
> 上游活跃度：created 2025-02-11，last push 2026-08-22，默认分支 main（GitHub API，2026-08-29 采集）
> 评估人：智能体 06｜日期：2026-08-29
> 定位：冥王峡谷语音栈一体化候选——只评估不替换，spec 先行，不写核心代码

---

## 〇、诚实声明（三项，读者先看）

1. **授粉报告缺失**：工单第一步要求对接的 `docs/OpenArc-语音栈-授粉报告.md` **在本仓不存在**——全仓 `grep -ril "openarc"` 对 docs/ 与根目录 *.md 零命中，所有分支（本地 + 远端）文件树亦无 openarc 文件。故本报告**从零建立**，结论全部基于源码核实，而非照抄授粉报告。
2. **源码 clone 缺失后补齐**：工单预设的 `github_haul/OpenArc/` 本机 clone 不存在（github_haul/ 下仅 CLI-Anything / codebase-memory-mcp / easyeda 等）。本轮已浅克隆 `SearchSavior/OpenArc` 到该路径**仅作本地勘察用，未提交进主仓**（遵守工单「不 clone 运行时进主仓」铁律）。
3. **工单硬件表述纠偏**：工单避坑铁律写「冥王峡谷（Intel CPU+NPU）适配」——**与事实不符**。NUC8i7HVK 的 i7-8809G 是 2018 年 Kaby Lake-G：**无 NPU**（OpenVINO NPU 插件需 Meteor Lake/Core Ultra 起）；其主 GPU Radeon RX Vega M GH 是 **AMD 硅，OpenVINO 不支持**。详见 §5 硬件适配矩阵。

---

## 一、这是什么

OpenArc 是一个跑在 OpenVINO 上的**推理服务器**：把 LLM、VLM、Whisper、Kokoro-TTS、Qwen3-TTS、Qwen3-ASR、Embedding、Reranker 八类模型挂到**统一 OpenAI 兼容 HTTP 端点**后面（README:14-15）。技术栈 FastAPI + 每模型异步队列 worker，设备用 Intel CPU / GPU / NPU。

一句话：**OpenArc = 模型服务层（OpenAI 门面），不是编排层。** 它没有 VAD、没有话轮检测、没有打断状态机——这些是 speech-core 的职责（见 §4 对比）。

---

## 二、能力清单（源码核实）

### 2.1 OpenAI 兼容端点（`src/server/routes/openai.py`，prefix `/v1`）

| 端点 | 支持引擎 | 源码位置 | 备注 |
|---|---|---|---|
| `GET /v1/models` | 全部已加载模型 | openai.py:231 | 从 registry 的 openai_model_names 渲染 |
| `POST /v1/completions` | llm | openai.py:470 | 仅文本补全 |
| `POST /v1/chat/completions` | llm | openai.py:254 | 流式 SSE/非流式；Qwen XML `<function=...>` + Hermes `<tool_call>` 双格式工具调用；`reasoning_content` 拆分（`</think>` 判据）；usage |
| `POST /v1/audio/transcriptions` | whisper / qwen3_asr | openai.py:615 | `response_format` 支持 json / verbose_json / diarized_json |
| `POST /v1/audio/speech` | kokoro + qwen3_tts(custom_voice/voice_design/voice_clone) | openai.py:697 | **README:45 写「kokoro only」已过时**——源码 openai.py:714-751 实际三种 Qwen3-TTS 也走此端点；qwen3_tts 支持 PCM 流式（`audio/L16;rate=24000;channels=1`），kokoro 返回整段 WAV |
| `POST /v1/embeddings` | optimum_emb（qwen3-embedding） | openai.py:791 | 见 README #33 |
| `POST /v1/rerank` | optimum_rr（qwen3-reranker） | openai.py:840 | 见 README #39 |

### 2.2 管理面（`src/server/routes/openarc.py`，prefix `/openarc`）

| 端点 | 作用 | 源码位置 |
|---|---|---|
| `POST /openarc/load` | 按配置加载模型 | openarc.py:157 |
| `POST /openarc/unload` | 卸载模型（admin 路径） | openarc.py:172 |
| `GET /openarc/status` | 注册表状态 | openarc.py:188 |
| `GET/POST/DELETE /openarc/models` | 本地模型目录 CRUD（写 openarc.json 配置） | openarc.py:198-302 |
| `GET /openarc/version` | 版本 | openarc.py:305 |
| `GET /openarc/metrics` | psutil CPU/RAM + gpu_metrics + `ov.Core().available_devices` 设备枚举 | openarc.py:320 |
| `POST/GET/DELETE /openarc/downloader` | HuggingFace 模型下载，支持暂停/恢复/取消 | openarc.py:346-398 |
| `POST /openarc/bench` | llama-bench 风格压测，结果落 sqlite（benchmark.py:29） | openarc.py:401 |

健康面：`GET /readyz` **无鉴权**就绪探针（main.py:121-130，为 K8s 编排器设计）。

### 2.3 工程特性逐项核实（工单所列）

| 特性 | 源码证据 | 核实结论 |
|---|---|---|
| 多引擎异步并发 | `WorkerRegistry` 为每个模型开一条 `asyncio.Queue` + 专属 worker task（worker_registry.py:596-669） | ✅ **跨模型并行、单模型内串行**（queue_worker 逐包消费）——比 README 口径更细的真相 |
| 失败自动卸载 | `_commit_completed_packet`：推理异常 → `result_future.set_exception` + `asyncio.create_task(register_unload)` + worker 退出（worker_registry.py:99-109） | ✅ |
| speculative decoding | `openvino_genai.draft_model` + `num_assistant_tokens` XOR `assistant_confidence_threshold` 互斥，默认 3 token（llm.py:229-256, 327-339） | ✅（需额外 draft 模型） |
| 流式取消 | 客户端断连 → request_id 追踪 → `infer_cancel` → `streamer.cancel()`（openai.py:323-329, worker_registry.py:842-865, llm.py:167-181） | ✅ |
| metrics | LLM 七项：load_time / ttft / tpot / prefill_throughput / decode_throughput / decode_duration / token 计数 + stream（llm.py:200-211）；Whisper 六项含 features_extraction（whisper.py:62-68） | ✅ |
| Docker 容器化 | `ghcr.io/searchsavior/openarc:latest` + battlemage 变体，`/dev/dri` 直通，NEO 调参 env（docker-compose.yaml） | ✅ |
| 多 GPU Pipeline Parallel / CPU offload / NPU | README:37-39 声称；NPU 设备枚举见 openarc.py:104-118 | ⚠️ 接口存在，硬件兑现另论（§5） |

### 2.4 依赖重量（pyproject.toml）

Python **≥3.12**；核心：`openvino-genai>=2026.2`、`torch>=2.11`（锁 CPU index）、`optimum[openvino]`、`kokoro/misaki/librosa`（TTS 文本处理）、`fastapi/uvicorn`、`openai-agents/smolagents`（附带 agent 库）、`ddgs/pynput/sounddevice`（桌面交互类，对服务形态是噪音）。文档另建议装 nightly OpenVINO wheels；Qwen3.5 系模型需从源码编译 openvino（docs/models.md）。

**重量结论**：torch + openvino-genai + kokoro 运行时，空载常驻约 1.5-2GB RSS（估），对冥王峡谷 16GB 是显著开销（见 06-02 资源预估）。

### 2.5 工程成熟度

- CI：`.github/workflows/` 含 `run-unit-tests.yml`（pytest）、`build-container-image.yaml`（镜像构建）、`docs.yml`
- 测试：`tests/unit` + `tests/integration` 共 25 个测试文件，覆盖 llm/vlm/whisper/kokoro/qwen3_asr/emb/rr 各引擎
- CLI：click + rich-click，命令 add/load/unload/list/serve/bench/status/tool/device_query
- 文档站：zensical 构建（searchsavior.github.io/OpenArc）；Discord 社区活跃

---

## 三、架构图（源码还原）

```
客户端（NEKO / Hermes / OpenAI SDK / curl）
        │ HTTP（Bearer 可选，默认关鉴权）
        ▼
FastAPI（src/server/main.py）── 中间件：访问日志 + CORS allow_origins=["*"]
   ├─ /v1/*        OpenAI 兼容（openai.py）
   ├─ /openarc/*   管理面 load/unload/status/downloader/bench（openarc.py）
   └─ /readyz      就绪探针（无鉴权）
        │ WorkerPacket = {request_id, id_model, gen_config, result_future | stream_queue}
        ▼
WorkerRegistry（worker_registry.py）——每模型一条 asyncio.Queue → 专属 queue_worker
        │                                    推理异常 ──► register_unload（自动卸载）
        ▼
ModelRegistry（model_registry.py）——生命周期 register_load/unload + on_loaded/on_unloaded 回调
        ▼
引擎实例（三类，按 model_type 路由）
   ├─ ov_genai： LLM / VLM / Whisper   （openvino_genai LLMPipeline，asyncio.to_thread 包阻塞 generate）
   ├─ openvino： Kokoro-82M / Qwen3-ASR / Qwen3-TTS（自研 OpenVINO 前向）
   └─ optimum：  Embedding / Reranker   （optimum-intel）
        ▼
OpenVINO 设备：CPU / GPU(仅 Intel) / NPU(仅 Core Ultra+)——运行时 ov.Core().available_devices 枚举
```

编排要点：**每个模型独立生命周期 + 独立队列 worker**，模型之间互不阻塞；单个模型内请求串行排队。流式路径走 `stream_queue`（文本/PCM 分块），非流式走 `result_future`（一次性结果）。

---

## 四、与 speech-core 对比表

| 维度 | OpenArc | speech-core（现状语音栈参考） |
|---|---|---|
| 定位 | 模型服务层（常驻 HTTP server） | 编排层（C++17 状态机库，零 ML 编排核心） |
| 端点形态 | OpenAI 兼容 HTTP（`/v1/*`） | 进程内 API，可选 ONNX/LiteRT 后端链接 |
| 模型后端 | OpenVINO（CPU/GPU/NPU） | ONNX / LiteRT / 无 / 自定义（换后端=换链接目标） |
| VAD / 话轮 / 打断编排 | ❌ 无（纯模型服务） | ✅ 4 状态滞后 VAD / turn_detector / speech_queue |
| TTS | Kokoro-82M 整段 WAV + Qwen3-TTS 1.7B 三形态（可流式 PCM） | Kokoro 等（ONNX） |
| STT | whisper large-v3 / distil / Qwen3-ASR 0.6B，整段音频非流式 | 流式 STT（streaming） |
| 流式取消 | ✅ request_id 级（断连即取消） | ✅ speech_queue cancel/resume |
| 常驻性 | 常驻 uvicorn + torch 运行时 | 按需链接进宿主进程 |
| 资源 | 重（运行时 ≥1.5-2GB + 模型） | 轻（编排核心零 ML 依赖） |
| 中文 TTS | ✅ Kokoro `z` 语言 zf_*/zm_* 声线（contract_kokoro.py:8-16, 62-65） | ✅ 同 Kokoro |
| 鉴权 | 可选，**默认关** | N/A（进程内） |

**结论**：两者是**互补层不是竞争层**。OpenArc 补齐的是「统一 OpenAI 门面 + 五类模型服务化」，speech-core 补齐的是「VAD/话轮/打断编排」。工单所谓「单模型 vs 全家桶」的对比，真实含义是：**OpenArc 用一套 HTTP 契约收编 STT+TTS+LLM+EMB+Rerank，代价是重运行时 + 常驻服务**；现状则是 speech-core(kokoro) + NEKO edge-tts 分散拼装、零常驻但无统一契约。要不要换，取决于「门面统一性」与「资源/常驻代价」孰轻孰重——详见 06-02 决策树。

---

## 五、硬件适配矩阵（工单三台机器，源码 + OpenVINO 口径核实）

OpenVINO 设备插件支持边界（install.md 明确「supports most OpenVINO devices, including AMD CPUs」——**AMD 只限 CPU**）：

| 插件 | 支持设备 | 说明 |
|---|---|---|
| CPU | Intel / AMD CPU（SSE4.2+） | 通用 |
| GPU | **仅 Intel**（HD/UHD/Arc，Level Zero/OpenCL） | 无 NVIDIA、无 AMD |
| NPU | **仅 Meteor Lake / Core Ultra 起** | Kaby Lake-G 无 |

| 机器 | CPU | GPU | NPU | OpenArc 可用设备 | 评估 |
|---|---|---|---|---|---|
| **冥王峡谷 NUC8i7HVK** | i7-8809G 4C8T（AVX2） | HD 630 iGPU（Gen9.5，24EU，弱）+ Vega M GH（AMD，**不支持**） | ❌ 无 | **仅 CPU**；HD 630 理论可跑但 24EU 无实用价值 | ⚠️ **OpenVINO 的 Intel 加速卖点在此机不成立**，只剩 CPU 推理 |
| 天选7 | Ryzen | RTX 5060（NVIDIA，**无插件**） | 无 | 仅 CPU | ❌ 不适配（工单铁律核实属实） |
| 云服 | 服务器 CPU | 无 | 无 | 仅 CPU | ❌ 无优势（对比 llama.cpp/vLLM CPU 生态无加分） |

**纠偏结论**：工单「冥王峡谷 Intel CPU+NPU 适配」应改为「**冥王峡谷仅 CPU 可用，无 NPU、主 GPU 不可用**」。因此评估重心不是「哪台机器跑 OpenArc」，而是「**OpenArc 的统一 OpenAI 门面 + 语音模型（纯 CPU 跑）值不值得为冥王峡谷引入**」。

---

## 六、模型矩阵（docs/models.md 核实；体积为 HuggingFace 常规量级**预估**，以实际下载为准）

| 类型 | 模型（HF 仓库） | 体积(约) | 中文 |
|---|---|---|---|
| STT | `OpenVINO/whisper-large-v3-int8-ov` | ~1.6GB | ✅ 多语 |
| STT | `OpenVINO/distil-whisper-large-v3-int8-ov` | ~0.8GB | 英文向 |
| STT | `Echo9Zulu/Qwen3-ASR-0.6B-INT8_ASYM-OpenVINO` | ~0.7GB | ✅ |
| TTS | `Echo9Zulu/Kokoro-82M-FP16-OpenVINO` | ~0.4GB | ✅ `z` 语言 8 女声 + 男声（zf_xiaobei 等） |
| TTS | `Echo9Zulu/Qwen3-TTS-12Hz-{CustomVoice/VoiceDesign/Base}-1.7B-INT8-OpenVINO` | ~2GB/个 | ✅ |
| EMB | `Echo9Zulu/Qwen3-Embedding-0.6B-int8_asym-ov` | ~0.7GB | ✅ |
| Rerank | `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov` | ~1.2GB | ✅ |
| LLM | `Echo9Zulu` 全谱系 int4/int8（Qwen3 1.7B→32B、Hermes-4-70B 等） | 1~40GB | 视模型 |

---

## 七、风险与时效

1. **活跃开发中**：main@92e6e1d（2026-08-22）、v2.0.5、README 自标 under active development、AGENTS.md 自称 bleeding edge。**接口可能变，本报告时效 2026-08-29，接入须锁 commit 或镜像 digest。**
2. **文档与源码漂移**：README:45 的 `/v1/audio/speech` 写「kokoro only」，源码实际已支持三种 Qwen3-TTS——结论须以源码为准。
3. **config.yaml 样例粗糙**：重复键 `qwen3_tts_oscar`、环境变量拼写 `OPENRARC_*`（应为 OPENARC），生产化程度一般。
4. **安全默认值激进**：鉴权默认关（deps.py:16 `OPENARC_API_KEY_REQUIRED` 默认 false）+ CORS `allow_origins=["*"]`（main.py:95-101）+ serve 默认绑 0.0.0.0（serve.py:20）——**上机必须显式开鉴权 + 绑回环**（见 06-02）。
5. **Qwen3.5 系支持非官方**：需源码编译 openvino（docs/models.md）。
6. **体积预估非实测**：本报告所有模型体积、RSS 均为「约/预估」，真机数字以 06-02 部署后 `verify` 为准。

---

## 八、可执行验收

```bash
grep -c "对比表" docs/openarc-评估报告.md              # ≥1
grep -c "适配矩阵" docs/openarc-评估报告.md            # ≥1
grep "worker_registry.py:99" docs/openarc-评估报告.md   # 失败自动卸载源码引用
grep "llm.py:200" docs/openarc-评估报告.md              # metrics 源码引用
grep "无 NPU" docs/openarc-评估报告.md                  # 硬件纠偏声明
grep -c "从零建立\|授粉报告缺失" docs/openarc-评估报告.md # ≥1 诚实声明
```

*授权：Apache-2.0 → 主仓 AGPL v3 允许直接吞；本报告只评估不改造。源码浅克隆归档于 github_haul/OpenArc/（未入库）。*
