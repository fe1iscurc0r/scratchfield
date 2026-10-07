# OpenArc 评审结论 + 落地建议 · 智能体 06 / 06-03

> 读者：沈遥（Hermes）/ 用户
> 依据：06-01 评估报告 + 06-02 部署方案 spec + SPEC-15/16 + speech-core 授粉报告
> 时效：2026-08-29，基于 OpenArc main@92e6e1d（v2.0.5，活跃开发中，接口可能变）

---

## 一、结论（三选一）

# 条件接入 ✅（不是「接入」全栈替换，也不是「不接入」全盘否定）

**明确边界**：接入的只是「OpenArc 的语音模型服务容器（按需、仅 STT/TTS，纯 CPU）」，不是「OpenArc LLM 全家桶」。默认仍维持现状（NEKO edge-tts + speech-core 编排），OpenArc 只做**离线语音兜底通道的候选**。

---

## 二、理由

1. **定位错位 → 不能全栈接**：OpenArc 是常驻 HTTP 模型服务，冥王峡谷 SPEC-15/16 已拍板「不做本地 LLM 常驻 + 零常驻守护进程 + <4GB 预算」。把 OpenArc 当「一体化语音栈」直接替换，会同时撞三条拍板（06-02 §4 对账：仅 Kokoro 2.6GB 可控，挂 LLM 则 11GB 直接违约）。
2. **硬件错位 → 加速叙事不成立**：NUC8i7HVK 无 NPU、主 GPU Vega M GH 是 AMD 不被 OpenVINO 支持、HD 630 iGPU 无实用价值。OpenArc 的「Intel 加速」卖点在冥王峡谷**只剩 CPU**，而纯 CPU 上它对比现状（edge-tts 走网络、speech-core 已有 kokoro）并无硬加速优势（06-01 §5）。
3. **真实价值 → 离线语音兜底**：OpenArc 唯一对冥王峡谷有价值的是「**本地离线 STT/TTS 的统一 OpenAI 端点**」——可解 NEKO edge-tts 依赖 Clash/网络这一已知薄弱点（SPEC-16 已把「NEKO 语音走网络 + Clash」列为可选而非必装的隐患）。这是「条件」的锚点。
4. **可授粉架构 ≥4 条且不依赖 OpenArc 本身**（见 §四）——即便不部署，评估已产出净收益。

---

## 三、前置条件（三选一结论成立的前提，缺一不接）

| # | 前置条件 | 判定依据 |
|---|---|---|
| 1 | **冥王峡谷真机到手 + SPEC-15 底座部署完成**，先有「Hermes 生态实际内存占用」基线 | 没有基线，「余量 ≥8GB」无从判断（06-02 Q3） |
| 2 | **NEKO 语音通道实测出现硬痛点**（断网不可用 / 首包延迟超标 / 审计要求本地化），且**有数据** | 无痛点就维持现状，不引入常驻容器（06-02 Q1） |
| 3 | **锁定上游版本**：接 main@92e6e1d 或官方镜像 digest，而非 `latest` | 活跃开发期接口会变（06-01 §7） |

**不满足即维持现状**：现状（edge-tts 网络 TTS + speech-core 编排 + 可选 silero_vad）在「零常驻 + 低内存」维度仍是最优解。

---

## 四、可授粉点清单（架构借鉴，不依赖 OpenArc 本身，≥4 条）

| # | 授粉点 | 源（源码） | 授粉到哪 | 收益 |
|---|---|---|---|---|
| 1 | **统一 OpenAI 端点门面**：一个服务收编 chat/audio/embeddings/rerank 五类模型，客户端一套 SDK | `src/server/routes/openai.py` 全部 `/v1/*` | speech-core 语音抽象层（LLM/STT/TTS/EMB 统一 HTTP 契约） | 高 |
| 2 | **metrics 体系**：每请求落 ttft/tpot/prefill/decode/load_time + usage 汇总 | llm.py:200-211 `collect_metrics` | NEKO 语音管线延迟测量（ASR 首字延迟、TTS TTFB） | 高 |
| 3 | **失败自动卸载**：推理异常 → 自动 unload 模型防僵尸进程占内存 | worker_registry.py:99-109 `_commit_completed_packet` | Hermes/NEKO 模型服务治理（memory_maas 后端故障自愈） | 高 |
| 4 | **流式取消（断连即收）**：client 断连 → request_id 追踪 → `infer_cancel` → `streamer.cancel()` | openai.py:323-329 + worker_registry.py:842-865 + llm.py:167-181 | TTS 播放打断（barge-in）链路 | 中 |
| 5 | **WorkerPacket 队列编排**：每模型一条 asyncio.Queue + 单 worker + `result_future`/`stream_queue` 双通道 | worker_registry.py:33-77, 596-669 | speech-core `speech_queue` 请求编排 | 中 |
| 6 | **就绪探针 + per-model 配置**：`/readyz` 无鉴权探针 + openarc.json 每模型自描述 + 下载器暂停/恢复 | main.py:121 + openarc.py:198-398 | 运维面（Hermes 服务健康检查） | 中 |
| 7 | **speculative decoding 参数互斥**：`num_assistant_tokens` XOR `assistant_confidence_threshold` 严格互斥 | llm.py:327-339 | 低速硬件提延迟手段记录（未来若上 CPU LLM 场景） | 低 |

> 授粉方式：只抄架构判断（同 speech-core 授粉报告的「不抄代码、抄分层」），不引 OpenArc 依赖进主仓。

---

## 五、一句话给用户

> **默认别换**。OpenArc 在冥王峡谷「无 NPU、主 GPU 不支持」的硬件上只剩 CPU 慢跑，还违背「不做本地 LLM 常驻 + 零常驻」的既定拍板。**只有当 NEKO 语音通道被网络依赖实锤卡死、且只做离线 STT/TTS 兜底时**，才以「按需容器 + 仅 Kokoro/Whisper + 127.0.0.1 + 强鉴权」条件接入。无论接不接，7 条架构可授粉点（统一端点门面 / metrics / 失败自动卸载 / 流式取消 / 队列编排 / 就绪探针 / speculative decoding）都值得落地到 speech-core 语音抽象层。

---

## 六、可执行验收

```bash
grep -c "条件接入" docs/openarc-评审结论.md      # ≥1（结论三选一明确）
grep -c "理由" docs/openarc-评审结论.md          # ≥1
grep -c "前置条件" docs/openarc-评审结论.md      # ≥1
grep -c "可授粉点" docs/openarc-评审结论.md      # ≥1
grep -c "^| [0-9] |" docs/openarc-评审结论.md    # ≥4（可授粉点表格行数 ≥4）
grep -c "活跃开发\|接口可能变" docs/openarc-评审结论.md  # ≥1（时效标注）
```

*结论诚实标注时效：OpenArc 活跃开发中，接口可能变；本评审基于 2026-08-29 的 main@92e6e1d 源码核实。*
