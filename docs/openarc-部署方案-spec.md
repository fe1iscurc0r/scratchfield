# OpenArc 冥王峡谷部署方案 spec · 智能体 06 / 06-02

> 状态：**spec 先行，不实际部署**（工单硬约束：不烧资源）
> 读者：实验田维护者（spec+review）/ 部署执行者（执行侧侧 Kali）
> 依据：06-01 评估报告 + SPEC-15（知识底座）+ SPEC-16（MCP 清单）+ speech-core 授粉报告
> 前提结论：冥王峡谷 NUC8i7HVK **仅 CPU 可用 OpenVINO**（无 NPU、Vega M GH AMD 不支持），见 06-01 §5

---

## 一、部署形态选型（先决策，再给步骤）

| 形态 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **A. Docker（官方镜像）** | 官方 `ghcr.io/searchsavior/openarc:latest`（docker-compose.yaml）；依赖打包好，无 Kali PEP 668 问题；`/dev/dri` 直通 | 需 docker daemon（违反 SPEC-16「零常驻守护进程」）；CPU-only 下 NEO GPU 调参无意义；镜像体积大 | **若真要接，首选**，但要用 socket 按需拉起缓解常驻问题 |
| B. uv 源码安装 | 无 docker daemon；可精确锁 commit | Kali PEP 668 → 必须 venv/uv；需装 nightly OpenVINO wheels；torch+openvino 重依赖污染 venv | 备选，仅评估时用 |
| C. 不部署 | 零资源 | — | **默认推荐**（见 §5 决策树） |

**关键矛盾**：OpenArc 是常驻 HTTP 服务，SPEC-16 铁律「零常驻守护进程」直接冲突。**缓解手段**：systemd socket activation（`systemctl start openarc` 时才拉起，空闲自动 `StopIdleSec` 回收），把「常驻」变成「按需」。这与 SPEC-16 对 NEKO 语音「按需，edge-tts/silero_vad ~200MB」的处理方式一致。

---

## 二、Docker 部署步骤（仅「条件接入」时执行，默认不执行）

```bash
# 0) 前置：docker + compose 已在 Kali（若未装则这一步本身违反零常驻，需重新评估）
# 1) 拉镜像并锁版本（活跃开发期，锁 digest 而非 latest）
docker pull ghcr.io/searchsavior/openarc:latest
#    建议改：docker pull ghcr.io/searchsavior/openarc@sha256:<镜像 digest>

# 2) 模型目录：挂载只读卷，模型放 /data/openarc-models（512GB NVMe 数据盘）
mkdir -p /data/openarc-models

# 3) 复写 compose（相对官方 docker-compose.yaml 三处改动）
```

```yaml
services:
  openarc:
    image: ghcr.io/searchsavior/openarc:latest   # 生产锁 digest
    container_name: openarc
    # devices: /dev/dri:/dev/dri   ← 冥王峡谷 Vega M GH AMD 不支持，HD 630 无意义，可删
    volumes:
      - /data/openarc-models:/models:ro          # 只读挂载
    ports:
      - "127.0.0.1:8000:8000"                    # ★ 只绑回环，不暴露局域网
    environment:
      - OPENARC_API_KEY=${OPENARC_API_KEY}       # ★ 强随机密钥
      - OPENARC_API_KEY_REQUIRED=true            # ★ 强制鉴权（默认关，必须开）
      - OPENARC_AUTOLOAD_MODEL=                  # ★ 空：启动不自动加载任何模型（按需 /openarc/load）
      - OPENARC_MODELS_DIR=/models
    restart: "no"                                # ★ 不设 unless-stopped，交给 systemd 按需拉起
```

```bash
# 4) systemd socket activation（把常驻降为按需）
#    openarc.socket: ListenStream=127.0.0.1:8000
#    openarc.service: Requires=openarc.socket; StopIdleSec=300（空闲 5 分钟自动停）
systemctl enable openarc.socket   # 有请求才拉起，无请求不占内存
```

**安全硬要求**（06-01 §7 已标）：①`OPENARC_API_KEY_REQUIRED=true` + 强密钥；②绑 `127.0.0.1`；③`/readyz` 本就无鉴权，只在回环安全。

---

## 三、模型下载清单（kokoro / whisper / qwen3 系列，按优先级）

| 优先级 | 模型（HF） | 用途 | 磁盘(约) | 内存 RSS(约) | 默认装否 |
|---|---|---|---|---|---|
| P0 | `Echo9Zulu/Kokoro-82M-FP16-OpenVINO` | 中文离线 TTS（`z` 语言 zf_*/zm_*） | ~0.4GB | ~0.6GB | ✅ 条件接入唯一默认 |
| P1 | `OpenVINO/whisper-large-v3-int8-ov` | 离线 STT（多语，中文可） | ~1.6GB | ~2.0GB | ⚠️ 视 STT 刚需 |
| P1' | `OpenVINO/distil-whisper-large-v3-int8-ov` | STT 轻量替代（英文向） | ~0.8GB | ~1.2GB | 备选 |
| P1'' | `Echo9Zulu/Qwen3-ASR-0.6B-INT8_ASYM-OpenVINO` | STT 更小（中文强） | ~0.7GB | ~1.0GB | 备选 |
| P2 | `Echo9Zulu/Qwen3-Embedding-0.6B-int8_asym-ov` | 向量 RAG | ~0.7GB | ~1.0GB | ❌ 默认不装（与 SPEC-15 冲突，见 §4） |
| P2 | `OpenVINO/Qwen3-Reranker-0.6B-fp16-ov` | 检索重排 | ~1.2GB | ~1.5GB | ❌ 默认不装 |
| P3 | `Echo9Zulu/Qwen3-4B-Instruct-2507-int4_asym-awq-ov` | LLM | ~2.7GB | ~3.5-4.5GB | ❌ **永不常驻**（违背 SPEC-15/16 拍板） |

下载方式：`POST /openarc/downloader`（支持暂停/恢复/取消）或 `huggingface-cli download`（需过 Clash，与 NEKO edge-tts 同网）。

---

## 四、资源预估 + 与 SPEC-15/16 冲突分析（16GB 诚实评估）

### 4.1 内存预算对账

| 项 | 常驻/峰值(估) | 依据 |
|---|---|---|
| OpenArc 运行时（uvicorn+torch+openvino，空载） | ~1.5-2GB | 06-01 §2.4 依赖重量 |
| + Kokoro-82M（P0） | +0.6GB → **~2.6GB** | 纯语音单模型 |
| + Whisper-large-v3（P1） | +2.0GB → **~4.6GB** | 语音+STT 全家桶 |
| + Embedding+Reranker（P2） | +2.5GB → **~7GB** | 加检索 |
| + Qwen3-4B LLM（P3） | +4GB → **~11GB** | 全家桶峰值 |

**SPEC-16 预算基线**：Hermes+知识底座 ~2-3GB + 哨兵 <1GB + 语音 ~200MB（edge-tts）≈ **<4GB / 16GB**。

**对账结论**：
- 仅 Kokoro（P0）：2.6GB，**挤占但可控**（余量 13GB 给 OCR/PDF 够）
- Kokoro+Whisper（P0+P1）：4.6GB，**开始挤 Hermes 底座预算**（底座 + 语音 ≈ 7-8GB，余量减半）
- 加 LLM（P3）：11GB，**直接违背 SPEC-15「不做本地 LLM 常驻」+ SPEC-16「<4GB 预算」两条拍板**，无讨论余地

### 4.2 非内存冲突（比内存更硬）

| 冲突项 | SPEC-15/16 铁律 | OpenArc 实际 | 结论 |
|---|---|---|---|
| 常驻守护进程 | 「零常驻，不跑 HTTP 服务（除非必要）」 | uvicorn 常驻 HTTP | ⚠️ 仅 socket 按需可部分缓解 |
| 本地 LLM | 「不做本地 LLM 常驻」 | `/v1/chat/completions` 即 LLM 服务 | ❌ 若挂 LLM 直接违约 |
| CPU 抢占 | i7-8809G 4C8T 全给 Hermes 生态 | 纯 CPU 推理，whisper-large 转写吃满 8 线程 | ⚠️ 转写时 Hermes 卡顿 |
| 嵌入模型重复 | SPEC-15 选 all-MiniLM-L6-v2（~80MB） | OpenArc 提供 Qwen3-Embedding-0.6B | ❌ 换模型 = 全库重新 embed，无收益 |
| 依赖污染 | Kali PEP 668 → venv 隔离 | Docker 隔离（选 A）| ✅ 选 Docker 可解 |
| GPU 加速预期 | 无 | Vega M GH AMD 不支持，HD 630 无意义 | ❌ 零硬件加速收益 |

### 4.3 磁盘

512GB NVMe：全家桶模型 ~6-8GB（06-01 §6 表），**磁盘无压力**，瓶颈全在内存与 CPU。

---

## 五、决策树（什么条件下值得换 / 维持现状）

```
是否引入 OpenArc 进冥王峡谷？
│
├─ Q1. NEKO 语音通道是否出现「硬痛点」且已实测？
│      （edge-tts 依赖 Clash/网络 → 断网不可用 / 首包延迟超标 / 审计要求本地化）
│   ├─ 否，无痛点 ──► 【维持现状】不接入；只授粉架构（见 06-03 可授粉点）
│   └─ 是，有实测数据 ──► 进 Q2
│
├─ Q2. 是否只挂 STT/TTS（绝不挂 LLM 常驻）？
│   ├─ 是 ──► 进 Q3（可行路径）
│   └─ 否，想挂 LLM ──► ❌【不接入】违背 SPEC-15「不做本地 LLM 常驻」，直接否
│
├─ Q3. 冥王峡谷资源余量是否 ≥8GB（底座实测后）？
│   ├─ 是 ──►【条件接入】仅语音容器：Kokoro(+可选 Whisper)，socket 按需 + 127.0.0.1 + 强鉴权
│   └─ 否 ──► 砍到仅 Kokoro（~2.6GB），或【不接入】继续 edge-tts
│
└─ 注：天选7 / 云服 两条线不评估（OpenVINO 无 NVIDIA 支持 / 纯 CPU 无优势，工单铁律）
```

**一句话决策**：默认维持现状；只有当 NEKO 语音通道被网络依赖实锤卡死、且只做离线 STT/TTS 兜底时，才以「按需容器 + 仅语音模型」条件接入。**LLM 全家桶常驻在冥王峡谷永不成立。**

---

## 六、可执行验收（spec 层面，不实际部署）

```bash
grep -c "决策树" docs/openarc-部署方案-spec.md            # ≥1
grep -c "资源预估\|内存\|16GB\|16G" docs/openarc-部署方案-spec.md  # ≥3
grep -c "冲突" docs/openarc-部署方案-spec.md              # ≥3
grep "OPENARC_API_KEY_REQUIRED=true" docs/openarc-部署方案-spec.md # 鉴权硬要求
grep "127.0.0.1" docs/openarc-部署方案-spec.md            # 回环绑定
grep "不实际部署\|spec 先行" docs/openarc-部署方案-spec.md  # 不烧资源声明
```

*本 spec 不含任何已执行的真机部署动作；所有内存/磁盘数字均为「约/预估」，真机数字以部署后 verify 为准。*
