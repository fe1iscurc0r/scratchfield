# voice-mcp 双项目接入评估 SPEC · v1

> 施工方：Trae／审查：实验田维护者（Hermes）｜日期：2026-08-16
> 范围：两个同名「voice-mcp」低星项目的接入评估——能否直接用 or 需改造。
> 前置：已 clone 到 `github_haul/mcp/voice-mcp/`（garan）与 `github_haul/mcp/voice-mcp-shreyas/`（shreyas）。

---

## 〇、一句话定位

两个 voice-mcp 都**不能直接进 Python mcpserver**：一个是 TS/Cloudflare 外部服务，一个是 macOS-only 的 stdio 服务。但两者各有可授粉点。

---

## 一、背景与边界

| 项目 | ⭐ | 许可 | 语言 | 形态 | 依赖 |
|---|---|---|---|---|---|
| garan0613/voice-mcp | 33 | MIT | TypeScript | Cloudflare Workers，SSE MCP（`/mcp`） | MiniMax TTS（克隆音色） |
| shreyaskarnik/voice-mcp | 16 | Apache-2.0 | Python | stdio MCP，单文件 `server.py` | **mlx-audio（Apple Silicon Metal）** |

**做**：评估两者接入 scratchpad 的路径与成本。
**不做**：不实现 STT/TTS 后端替换、不在云服部署 CF Worker、不改 NEKO 源码与 apiserver 主链路。

---

## 二、接入评估

### 2.1 garan0613/voice-mcp —— 结论：**可直接接入（作为外部 MCP 服务）**

它本质是**外部 MCP 服务**，不是要并进 Python 主仓的代码。它做的事：

- `speak(text)` 工具 → 调 MiniMax `POST /v1/t2a_v2?GroupId=...`（模型 `speech-2.8-hd`），`voice_setting.voice_id` 用克隆音色，返回 base64 mp3。
- 用 MCP `ext-apps`（`io.modelcontextprotocol/ui`）渲染内联音频播放器（WeChat 风格波形 UI）。

**接入路径**（选其一）：

| 路径 | 成本 | 说明 |
|---|---|---|
| A. 部署到 CF，worker URL 加入 `~/.mcporter/config.json` | 低 | 走 mcporter_bridge 的 `ExternalMCPAgent`，与现有外部服务清单一致 |
| B. 写 Python handler 直接调 MiniMax t2a_v2（复用其 payload 逻辑） | 中 | 沉淀进 `mcpserver/`，但需 MiniMax 凭证（已有 minimax_domestic） |

**依赖**：MiniMax 克隆音色凭证（`MINIMAX_API_KEY` / `MINIMAX_GROUP_ID` / `VOICE_ID`）。**注意**：MiniMax 的音色克隆要上传 10-30s 音频，是账号级能力，不是开箱即用。

### 2.2 shreyaskarnik/voice-mcp —— 结论：**需改造（macOS 硬依赖）**

它是个 273 行单文件 stdio MCP，暴露 `listen()`（STT）+ `speak()`（TTS），但：

- **硬依赖 `mlx-audio`**（`mlx_audio.stt` / `mlx_audio.tts`），只跑在 Apple Silicon（Metal），**Linux 云服无法运行**。
- STT 模型 `Voxtral-Mini-4B-Realtime-2602-int4`（~2.5GB），TTS 模型 `Kokoro-82M-bf16`。

**改造点**（若要接入）：

| 组件 | 原实现 | Linux 替换方案 |
|---|---|---|
| STT | mlx-audio Voxtral | faster-whisper / whisper（CPU 可跑） |
| TTS | mlx-audio Kokoro | **我们已有的 kokoro-onnx + Edge TTS**（memory 已记） |
| VAD | webrtcvad（mode 3）+ 能量兜底 | 同款 webrtcvad 直接可用（跨平台） |

**可授粉点**（不改造也值得抄）：
1. **`stdout is sacred` 纪律**——TTS 播放时 `sys.stdout` 重定向到 devnull，防污染 MCP stdio 通道。这是 stdio MCP 的通用坑，授粉到我们任何 stdio 桥接。
2. **`listen()` 的 VAD 录音逻辑**（`record_until_silence`：30ms 帧 + 1.5s 静音停 + webrtcvad 异常时能量兜底）——与 cascade 的 VAD 互补，这份是「够用就好」的极简实现。
3. **FastMCP lifespan 预加载模型**——首次调用不卡顿。

---

## 三、关键假设与 fallback

| 假设 | 若失效 | fallback |
|---|---|---|
| MiniMax 克隆音色凭证可用 | 无克隆音色账号 | 路径 B 改走我们已有的 Edge TTS / kokoro-onnx，不依赖 MiniMax |
| CF Worker 可部署 | 无 CF 账号/被墙 | 路径 B 写 Python handler，全本地 |
| 云服需要语音能力 | 云服无 mic/扬声器 | voice-mcp 的 TTS 侧仍有价值（NEKO 桌宠出声），STT 侧授粉给 K40 手机端 |

---

## 四、已知限制（具体 + 原因）

1. **garan 的 TTS 输出是 base64 mp3 内联 UI**，依赖 MCP `ext-apps` 扩展渲染——我们当前 `mcp_manager.py` 的 `handle_handoff` 返回纯 JSON 字符串，**没有 structuredContent 通道**，内联播放器 UI 无法复用。音频本体（base64）可复用，播放器 UI 需另做。
2. **shreyas 是 macOS 专属**，`mlx-audio` 的 Metal 依赖无 CPU/CUDA 兜底，Linux 云服 100% 跑不了，只能授粉逻辑。
3. 两者都**不包含许可证问题**（MIT / Apache-2.0 均可吞），但 garan 依赖 MiniMax 商业 API（非开源权重），接入即引入外部付费依赖。

---

## 五、验收标准（可执行不变量）

```bash
# 1. 本评估含"能否直接用"结论
grep -c "可直接接入" docs/voice-mcp-接入评估-SPEC-v1.md    # ≥1
grep -c "需改造" docs/voice-mcp-接入评估-SPEC-v1.md        # ≥1

# 2. 引用到真实源码
grep -c "t2a_v2" docs/voice-mcp-接入评估-SPEC-v1.md        # ≥1
grep -c "mlx-audio" docs/voice-mcp-接入评估-SPEC-v1.md     # ≥1

# 3. 许可已确认
grep -c "MIT" docs/voice-mcp-接入评估-SPEC-v1.md           # ≥1
grep -c "Apache-2.0" docs/voice-mcp-接入评估-SPEC-v1.md    # ≥1

# 4. 不碰主流程（本评估仅落 docs，无代码改动）
git diff --stat -- NEKO apiserver | wc -l                # 0
```

---

*授权：MIT + Apache-2.0 → 主仓 AGPL v3 允许直接吞。本评估为接入前决策，不产生代码改动。*
