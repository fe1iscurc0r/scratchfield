# voice-mcp (shreyaskarnik) MCP 封装 SPEC · v1

> 施工方：Trae（陆墨团队）｜审查：沈遥（Hermes）
> 理论锚点：SPEC-Writing-Standard-v3.md（四问 + 十条 + 六条审查）
> 本文档自包含：引用到文件 + 行号，验收可 grep/assert。

---

## 〇、一句话定位

**把 shreyaskarnik/voice-mcp（Apache-2.0，Claude Code 双向语音 MCP）以「改造接入」方式融合进 scratchpad——上游是 FastMCP stdio + mlx-audio（仅 Apple Silicon 真机），无法直接进 Python 注册表，故复刻其 listen/speak 工具语义：speak 后端可切换（真机 mlx Kokoro → 云服 TTS-API kokoro 同源引擎 → 降级），listen 为真机能力（云服优雅降级）。**

---

## 一、背景与边界

### 背景

scratchpad 的语音层已有多项能力：TTS-API（kokoro/edge 通用 TTS）、voice_mcp_minimax（MiniMax 克隆合成）。shreyaskarnik/voice-mcp 补的是**双向语音交互**这一档：`listen()`（麦克风 + webrtcvad VAD + Voxtral Realtime STT）与 `speak()`（Kokoro TTS 82M，9 语言 / 54 音色）成对出现，并带「对话性内容用语音、技术性内容写终端」的使用哲学。

### 接入评估

| 维度 | 结论 |
|------|------|
| 上游形态 | FastMCP stdio server（Claude Code），TS/Python 混用，mlx-audio 仅 Apple Silicon |
| 能否直接注册 | 不能（mcp_registry 只认 Format A：`module` + `class` + `handle_handoff`） |
| 融合方式 | **改造接入**：Python 复刻 listen/speak 工具语义，后端可切换 |
| 契约来源 | 上游 `server.py:204-226`(listen)、`server.py:229-267`(speak)、`server.py:136-199`(录音+VAD) |
| 许可 | Apache-2.0（gh api 已验，可吞） |

### 边界（做 / 不做）

| 做 | 不做 |
|----|------|
| 复刻 `voice_speak` / `voice_listen` / `voice_status` 三工具 | 不内置 mlx-audio / sounddevice 等重型依赖入主进程（惰性导入 + 降级） |
| speak 后端可切换：真机 mlx Kokoro → 云服 TTS-API kokoro（迂回）→ 降级 | 不复刻 FastMCP stdio 传输层（scratchpad 用 Format A 统一调度） |
| listen 真机路径（VAD + STT，待联调）+ 云服降级 | 不做 macOS 通知 hooks（.claude/hooks，Claude Code 专属） |
| 语言码校验（a/b/e/f/h/i/j/p/z 九种） | 不做音色浏览（上游 `/voice` 是 Claude Code 斜杠命令） |
| 不触碰 NEKO 主链路与陆墨核心 | 不把上游 worker/stdio 进程托管进本仓 |

---

## 二、架构设计

```
┌────────────────────────────────────────────────────────┐
│ scratchpad 主进程                                       │
│  ┌──────────────────────────────────────────┐          │
│  │ mcp_registry.scan_and_register_mcp_agents() │        │
│  │   └─ mcpserver/voice_mcp_bidi/agent-manifest.json    │
│  │        → VoiceMCPBidiAgent (voice_mcp_bidi.py)       │
│  │              handle_handoff(task) → str              │
│  └──────────────────────────────────────────┘          │
└───────────────┬──────────────────────────────┬──────────┘
   speak 后端①      │  speak 后端②（迂回）       │ listen 后端①
   真机 mlx Kokoro  │  HTTPS REST               │ 真机 麦克风+VAD+STT
   (Apple Silicon)  │  TTS-API /api/tts         │ (Apple Silicon)
                    ▼                          ▼
        ┌──────────────────────┐   ┌──────────────────────┐
        │ mlx-community/       │   │ Voxtral-Mini-4B-     │
        │ Kokoro-82M-bf16      │   │ Realtime-2602-int4    │
        └──────────────────────┘   └──────────────────────┘
```

### 组件分层

| 层 | 组件 | 说明 |
|----|------|------|
| L1 接入层 | `mcpserver/voice_mcp_bidi/agent-manifest.json` | 注册 manifest（Format A），声明三工具 |
| L2 桥接层 | `mcpserver/voice_mcp_bidi/voice_mcp_bidi.py:VoiceMCPBidiAgent` | 统一 `handle_handoff` + 三工具 + 后端选择 |
| L3 传输层 | `_call_tts_api()`（urllib，60s 超时） | TTS-API kokoro 迂回后端 |
| L4 真机层 | `_try_local_speak` / `_try_local_listen`（惰性导入 mlx/sounddevice） | 待联调，云服缺依赖自动跳过 |

### 数据流（voice_speak）

1. `handle_handoff({"tool_name":"voice_speak","text":...,"voice":...,"lang":...,"speed":...})`
2. 校验：空文本 / 非法 lang / speed 夹取 [0.5, 3.0]
3. 后端选择：① `_try_local_speak`（mlx 可用 → wav 落盘）→ ② `_call_tts_api`（TTS-API 可达 → mp3 落盘）→ ③ 降级 JSON
4. 返回 `{status:"ok"|"error", backend, data:{file, file_size, audio_base64, ...}}`

### 数据流（voice_listen）

1. `handle_handoff({"tool_name":"voice_listen","duration":...})`
2. 真机路径 `_try_local_listen`（sounddevice + mlx STT，待联调）→ 返回转写文本
3. 否则降级 JSON（注明「真机能力」）

---

## 三、施工步骤

| 步 | 内容 | 落盘 |
|----|------|------|
| 1 | 确认上游许可 | Apache-2.0（gh api 已验） |
| 2 | 分析上游 listen/speak 契约、语言码、后端依赖 | 见 `server.py:204-267`、`README.md:62-67` |
| 3 | 写 handler（惰性导入 + 后端切换，仅标准库 HTTP） | `mcpserver/voice_mcp_bidi/voice_mcp_bidi.py` |
| 4 | 写 manifest（三工具） | `mcpserver/voice_mcp_bidi/agent-manifest.json` |
| 5 | 写单元测试（降级 + 语言码 + mock 两成功路径） | `mcpserver/voice_mcp_bidi/tests/test_voice_mcp_bidi.py` |
| 6 | 运行测试 + registry 注册验证 | 见验收 |

**跨文件依赖签名**（施工方不共享上下文）：
- 调度契约：`async handle_handoff(self, task: Dict[str, Any]) -> str`，对齐 `mcpserver/agent_weather_time/agent_weather_time.py`；`mcp_registry._resolve_entrypoint` 用 Format A（`entryPoint.module` + `entryPoint.class`），见 `mcp_registry.py:70-114`。
- 迂回后端 TTS-API 契约（对齐 `mcpserver/tts_api/tts_api.py` 已封装的 `/api/tts`）：`POST {base}/api/tts`，body `{text, engine:"kokoro", voice, speed}`，响应 `audio/mpeg` 字节。
- 环境变量：`VOICE_MCP_CACHE_DIR`（默认 `mcpserver/voice_mcp_bidi/.cache`）、`TTS_API_BASE_URL`（默认 `http://127.0.0.1:8880`）。
- 真机模型仓库：`mlx-community/Kokoro-82M-bf16`（TTS）、`mlx-community/Voxtral-Mini-4B-Realtime-2602-int4`（STT），对齐上游 `server.py:83-84`。

---

## 四、关键假设与 fallback

### 可自验假设（施工方本地可验证）

| # | 假设 | 验证方式 |
|---|------|---------|
| A1 | manifest Format A 能注册 | `python -c "from mcpserver.mcp_registry import scan_and_register_mcp_agents as s; assert 'voice_mcp_bidi' in s()"` |
| A2 | handler 可导入且不因缺 mlx 炸 | `python -c "from mcpserver.voice_mcp_bidi.voice_mcp_bidi import VoiceMCPBidiAgent"` |
| A3 | 云服（无 mlx / 无 TTS-API）speak/listen 优雅降级 | pytest 覆盖（见验收） |
| A4 | 后端优先级 mlx 优先于 TTS-API | `test_speak_uses_local_mlx_first` |

### 待联调假设（需真机 / 端到端）

| # | 假设 | 联调时怎么验 |
|---|------|------------|
| B1 | Apple Silicon 真机装了 mlx-audio + sounddevice + webrtcvad | `voice_speak` 返回 `backend:"mlx-kokoro"` 与有效音频；`voice_listen` 返回转写文本 |
| B2 | 云服部署了 TTS-API（8880）且 kokoro 引擎就绪 | `voice_speak` 返回 `backend:"tts-api-kokoro"` 与有效 mp3 |
| B3 | 麦克风/扬声器硬件正常 | `voice_listen` 能收到语音并转写；`voice_speak` 能播报（真机路径） |

---

## 五、已知限制

| 限制 | 说明 |
|------|------|
| listen 真机专属 | 麦克风 + 本地 STT 模型，云服无此能力，只能降级（诚实标注，不假装可跑） |
| speak 云服依赖 TTS-API 部署 | 迂回后端复用 scratchpad 已有 TTS-API 基础设施；未部署则降级 |
| 真机 VAD 自动停止未完整复刻 | `_try_local_listen` 用固定时长录音，完整 VAD 自动停止（对齐上游 `record_until_silence`）留待真机联调补 |
| 不做 macOS 通知 hooks | `.claude/hooks/notify.sh` 是 Claude Code 专属能力，超出 Format A 形态 |

---

## 六、测试用例（纯 Python）

| 用例 | 断言 |
|------|------|
| `test_agent_importable` | `VoiceMCPBidiAgent` 可实例化 |
| `test_handle_handoff_returns_json_string` | 返回可 parse 的 dict |
| `test_unknown_tool_error` | 未知 tool_name 返回 error 而非抛异常 |
| `test_speak_degraded_when_no_backends` | 无后端 → `status=="error"` 且 `data.degraded is True` |
| `test_listen_degraded_on_cloud` | 云服 → `data.degraded is True` |
| `test_speak_empty_text_error` | 空文本返回 error |
| `test_speak_invalid_lang_error` | 非法 lang 返回 error |
| `test_lang_codes_expect_9` | 语言码集合恰为九种 |
| `test_speak_success_via_tts_api` | mock TTS-API → `backend=="tts-api-kokoro"`，落盘 mp3 + base64 可解码回原字节 |
| `test_speak_uses_local_mlx_first` | mlx 可用时优先 `backend=="mlx-kokoro"` |
| `test_listen_success_local` | mock 真机 listen → `data.text=="你好世界"` |
| `test_status_reports_backends` | `voice_status` 正确报告各后端可用性 |

---

## 七、交付物清单

- `mcpserver/voice_mcp_bidi/__init__.py`
- `mcpserver/voice_mcp_bidi/agent-manifest.json`
- `mcpserver/voice_mcp_bidi/voice_mcp_bidi.py`
- `mcpserver/voice_mcp_bidi/tests/test_voice_mcp_bidi.py`
- `docs/voice-mcp-bidi-MCP封装SPEC-v1.md`（本文档）

---

## 八、验收标准（可执行不变量）

```bash
# 1. manifest 存在且含 license 字段（许可可 grep）
test -f mcpserver/voice_mcp_bidi/agent-manifest.json \
  && grep -q '"license": "Apache-2.0"' mcpserver/voice_mcp_bidi/agent-manifest.json \
  && echo "ACCEPT 1: manifest + Apache-2.0 license"

# 2. handler 可导入（缺 mlx 不炸）
python3 -c "from mcpserver.voice_mcp_bidi.voice_mcp_bidi import VoiceMCPBidiAgent; print('ACCEPT 2: import ok')" \
  | grep -q "ACCEPT 2" && echo "ACCEPT 2: handler importable"

# 3. 单元测试全绿（12 passed）
python3 -m pytest mcpserver/voice_mcp_bidi/tests/ -q | grep -q "12 passed" \
  && echo "ACCEPT 3: 12 tests passed"

# 4. registry 能扫描注册 voice_mcp_bidi
python3 -c "from mcpserver.mcp_registry import scan_and_register_mcp_agents as s; assert 'voice_mcp_bidi' in s(); print('ACCEPT 4: registered')" \
  2>&1 | grep -q "ACCEPT 4" && echo "ACCEPT 4: voice_mcp_bidi registered"

# 5. 未触碰主链路（NEKO / apiserver）
git diff origin/main --stat | grep -E "NEKO/N.E.K.O/|apiserver/" \
  && echo "FAIL 5: touched NEKO/apiserver" || echo "ACCEPT 5: no NEKO/apiserver changes"

# 6. 本次仅新增融合文件
git diff origin/main --name-only | grep -vE "^mcpserver/voice_mcp_bidi/|^docs/voice-mcp-bidi" | grep -v "^$" \
  && echo "FAIL 6: touched non-fusion files" || echo "ACCEPT 6: only fusion files changed"
```

---

## 九、提交规范

```bash
git add mcpserver/voice_mcp_bidi/ docs/voice-mcp-bidi-MCP封装SPEC-v1.md
git commit -m "feat(mcp): voice_mcp_bidi MCP 封装

- shreyaskarnik/voice-mcp (Apache-2.0) 改造接入：双向语音（listen+speak）
- speak 后端可切换：真机 mlx Kokoro → 云服 TTS-API kokoro 迂回 → 降级
- listen 真机能力（VAD+Voxtral STT），云服优雅降级；12 tests passed"
```

---

*制定：Trae（陆墨团队）｜理论锚点：SPEC-Writing-Standard-v3.md · 系统工程四原则 · 不变量伴生验收*
