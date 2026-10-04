# OpenArc 语音栈整合评估

> 2026-08-29 · 来源：SearchSavior/OpenArc（Apache-2.0，511★，扫货日报 8/29 Top3）
> 勘察：README + src/{cli,server,engine} 结构 + AGENTS.md
> 定位：Intel 设备推理引擎——LLM/VLM/Whisper/Kokoro-TTS/Qwen-TTS/Qwen-ASR/Embedding/Rerank 统一 OpenAI 兼容端点，OpenVINO 驱动

## 一句话

OpenArc 把散装的语音/推理栈收敛成**一个服务**：一套 OpenAI 端点管 TTS+ASR+embedding+rerank+LLM，多引擎异步并发，支持 CPU/GPU/NPU。跟 speech-core 已授粉的 kokoro-tts 是"单模型 vs 全家桶"的关系。

## 能力清单

- 端点：`/v1/chat/completions`（LLM/VLM）· `/v1/audio/transcriptions`（whisper/qwen3-asr）· `/v1/audio/speech`（kokoro）· `/v1/embeddings`（qwen3-embedding）· `/v1/rerank`（qwen3-reranker）· `/v1/models`
- 架构：多引擎多任务异步，模型并发加载推理，失败自动卸载
- 硬件：OpenVINO → CPU/GPU/NPU（Intel 生态）
- 工程：Docker 容器化、speculative decoding、流式取消、jinja 模板+AutoTokenizers、每请求 metrics（ttft/prefill_throughput/decode_throughput/tpot/load_time）

## 对比：散装 pipeline vs OpenArc

| 维度 | 现状（speech-core 散装） | OpenArc |
|------|--------------------------|---------|
| TTS | kokoro-tts 独立服务 | 同一服务 /v1/audio/speech |
| ASR | whisper 独立 | 同一服务 /v1/audio/transcriptions |
| Embedding | 独立 | /v1/embeddings |
| 多模型并发 | 各管各的 | 单引擎多任务并发 + 自动卸载 |
| 统一端点 | ❌ | ✅ OpenAI 兼容全套 |
| metrics | 无 | ✅ ttft/tpot/吞吐全套 |

## 关键结论：硬件适配是硬门槛

- **冥王峡谷（Intel CPU）**：OpenVINO 主场，NPU 可用 → **适配**。语音栈一体化候选。
- **天选7（RTX5060/NVIDIA）**：OpenVINO 对 NVIDIA GPU 支持弱 → **不适配**，维持 CUDA 栈。
- **云服**：无 Intel GPU/NPU，仅 CPU 推理 → OpenVINO CPU 可跑但无优势。
- 结论：OpenArc 是"冥王峡谷语音栈一体化"候选，不是全栈替换。

## 可授粉点

| # | 点 | 流向 | 价值 |
|---|-----|------|------|
| 1 | **统一 OpenAI 端点架构**（一套服务管 TTS/ASR/embedding） | NEKO 语音通道（冥王峡谷线） | 散装 pipeline → 单服务，配好即可用 |
| 2 | **每请求 metrics 体系**（ttft/prefill/decode/tpot） | rf_brain/战情面板 | 推理服务可观测性规范，LLM/语音服务统一打点 |
| 3 | **失败自动卸载** | 云服 LLM 服务 | 长期运行服务的内存回收策略 |
| 4 | **speculative decoding**（LLM 加速） | 冥王峡谷本地 LLM | Intel CPU 上 token/s 提升明显 |

## 差距/注意

- OpenVINO 是硬依赖 → 非 Intel 平台不可用
- 活跃开发中（README 自标 under active development），接口可能变
- 我们 speech-core 的 kokoro 集成已有，若冥王峡谷语音栈一体化再评估 OpenArc 整体替换

## 落地建议

- P1：冥王峡谷语音栈若要做一体化，评估 OpenArc Docker 部署（spec 先行，不直接换）
- P2：metrics 打点规范（ttft/tpot）收进战情面板/节点心跳实现
- 不 rush：当前散装能用，OpenArc 是"收敛候选"不是"必须换"
