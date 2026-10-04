# voice-mcp (garan0613) MCP 封装 SPEC · v1

> 施工方：Trae｜审查：实验田维护者（Hermes）
> 理论锚点：SPEC-Writing-Standard-v3.md（四问 + 十条 + 六条审查）
> 本文档自包含：引用到文件 + 行号，验收可 grep/assert。

---

## 〇、一句话定位

**把 garan0613/voice-mcp（MIT，AI 语音克隆合成 MCP）以「Python 改造接入」方式融合进 scratchpad——上游是 TS/Cloudflare Workers 形态，无法直接进 Python 注册表，故复刻其核心合成逻辑（同一 MiniMax t2a_v2 API 契约），让陆墨能通过统一 MCP 调度「语音克隆合成 / 配置检查」。**

---

## 一、背景与边界

### 背景

scratchpad 的 MCP 工具体系已有 TTS-API（kokoro/edge 通用 TTS）。voice-mcp 补的是**语音克隆**这一档：MiniMax t2a_v2 支持用克隆音色合成，语义与桌面宠「拟人化说话」强相关。上游是 Cloudflare Workers 的 SSE MCP server（`/mcp` 端点，TypeScript），核心工具 `speak` 调 MiniMax t2a API 做克隆合成。

### 接入评估

| 维度 | 结论 |
|------|------|
| 上游形态 | TS + Cloudflare Workers SSE MCP server，非 Python 模块/类 |
| 能否直接注册 | 不能（mcp_registry 只认 Format A：`module` + `class` + `handle_handoff`） |
| 融合方式 | **改造接入**：Python 复刻核心合成逻辑，工具语义与上游 `speak` 对齐 |
| 契约来源 | 上游 `src/index.ts:332-384`（t2a 请求体）、`src/index.ts`（speak 工具） |

### 边界（做 / 不做）

| 做 | 不做 |
|----|------|
| 把 MiniMax t2a_v2 合成封装为 MCP agent（manifest + handler） | 不部署 Cloudflare Worker，不引入 TS 构建链 |
| 提供 `voice_speak`（合成落盘 mp3 + base64）/ `voice_status` 两工具 | 不实现 SSE/流式传输（克隆合成走非流式 `stream:false`） |
| 缺 API Key/GroupId 时优雅降级 `{"status":"error","degraded":true}` | 不把 MiniMax 官方 SDK 拖进主进程（仅 urllib 标准库） |
| 不触碰 NEKO 主链路与主系统核心 | 不做音色管理/克隆训练（MiniMax 控制台侧能力） |

---

## 二、架构设计

```
┌──────────────────────────────────────────────────────┐
│ scratchpad 主进程                                     │
│  ┌────────────────────────────────────────┐           │
│  │ mcp_registry.scan_and_register_mcp_agents() │       │
│  │   └─ mcpserver/voice_mcp_minimax/agent-manifest.json│
│  │        → VoiceMCPMinimaxAgent (voice_mcp_minimax.py)│
│  │              handle_handoff(task) → str             │
│  └────────────────────────────────────────┘           │
└────────────────────────────┬──────────────────────────┘
        HTTPS (Bearer Key)    │ REST 客户端（urllib，仅标准库）
┌─────────────────────────────▼──────────────────────────┐
│ MiniMax t2a_v2 API  https://api.minimaxi.com/v1/t2a_v2  │
│   POST ?GroupId=<id>  body={model:"speech-2.8-hd",      │
│      text, stream:false, voice_setting:{voice_id,...},  │
│      audio_setting:{sample_rate:32000, format:"mp3"}}   │
│   200 → {base_resp:{status_code:0}, data:{audio:hex},   │
│           extra_info:{audio_length,...}}                │
└─────────────────────────────────────────────────────────┘
```

### 组件分层

| 层 | 组件 | 说明 |
|----|------|------|
| L1 接入层 | `mcpserver/voice_mcp_minimax/agent-manifest.json` | 注册 manifest（Format A），声明两工具 |
| L2 桥接层 | `mcpserver/voice_mcp_minimax/voice_mcp_minimax.py:VoiceMCPMinimaxAgent` | 统一 `handle_handoff` + 两工具实现 |
| L3 传输层 | `_call_t2a()`（urllib，60s 超时，失败返回 None） | 对齐上游 t2a 请求契约 |
| L4 上游 | MiniMax t2a_v2 API（云服务，不入本仓） | 克隆语音合成 |

### 数据流（voice_speak）

1. `handle_handoff({"tool_name":"voice_speak","text":...,"voice_id":...})`
2. `_do_speak` → 校验凭据（`_credentials()` 调用时读取环境变量）
3. `_call_t2a(text, vid)` → 解析 JSON
4. 成功 → `data.audio`（hex）→ 落盘 `.cache/minimax_*.mp3`，返回 `{status:"ok", data:{file, audio_base64, ...}}`
5. 上游报错/网络失败 → 返回 `{status:"error", degraded:true}` 不抛异常

---

## 三、施工步骤

| 步 | 内容 | 落盘 |
|----|------|------|
| 1 | 确认上游许可 | MIT（gh api 已验） |
| 2 | 分析上游 t2a 契约（请求体、鉴权头、响应结构） | 见 `src/index.ts:332-384` |
| 3 | 写 handler（仅标准库，调用时读环境变量） | `mcpserver/voice_mcp_minimax/voice_mcp_minimax.py` |
| 4 | 写 manifest（两工具） | `mcpserver/voice_mcp_minimax/agent-manifest.json` |
| 5 | 写单元测试（降级 + 契约 + mock 成功/上游错误路径） | `mcpserver/voice_mcp_minimax/tests/test_voice_mcp_minimax.py` |
| 6 | 运行测试 + registry 注册验证 | 见验收 |

**跨文件依赖签名**（施工方不共享上下文）：
- 调度契约：`async handle_handoff(self, task: Dict[str, Any]) -> str`，对齐 `mcpserver/agent_weather_time/agent_weather_time.py`；`mcp_registry._resolve_entrypoint` 用 Format A（`entryPoint.module` + `entryPoint.class`），见 `mcp_registry.py:70-114`。
- 环境变量：`MINIMAX_API_KEY`、`MINIMAX_GROUP_ID`、`MINIMAX_VOICE_ID`（克隆音色）、`MINIMAX_CACHE_DIR`（默认 `mcpserver/voice_mcp_minimax/.cache`）。
- 上游响应结构：`{base_resp:{status_code,status_msg}, data:{audio:<hex>, status}, extra_info:{audio_length, audio_sample_rate}}`。

---

## 四、关键假设与 fallback

### 可自验假设（施工方本地可验证）

| # | 假设 | 验证方式 |
|---|------|---------|
| A1 | manifest Format A 能注册 | `python -c "from mcpserver.mcp_registry import scan_and_register_mcp_agents as s; assert 'voice_mcp_minimax' in s()"` |
| A2 | handler 仅用标准库、可导入 | `python -c "from mcpserver.voice_mcp_minimax.voice_mcp_minimax import VoiceMCPMinimaxAgent"` |
| A3 | 缺凭据时降级、不抛异常 | pytest 覆盖（见验收） |
| A4 | 环境变量在调用时读取（可注入） | `test_speak_success` / `test_speak_degraded_without_creds` 用 monkeypatch 设/删 env |

### 待联调假设（需真机 / 端到端）

| # | 假设 | 联调时怎么验 |
|---|------|------------|
| B1 | 配置了有效的 `MINIMAX_API_KEY`/`MINIMAX_GROUP_ID`/`MINIMAX_VOICE_ID` | 调 `voice_speak` 得到 `status:"ok"` 与有效 mp3 文件；`voice_status` 的 `ready` 为 true |
| B2 | 账号已有克隆音色 `MINIMAX_VOICE_ID` | 用该音色合成无 1004（voice not found）等上游错误 |

---

## 五、已知限制

| 限制 | 说明 |
|------|------|
| 不做 SSE/流式传输 | 上游是 Workers SSE MCP server；Python 改造接入取「非流式合成」最小语义，实时流式需另接上游 Worker |
| 依赖 MiniMax 云服务与付费配额 | 克隆合成走云端 API，需账号 + 余额；无自托管替代 |
| 音色管理不在本封装 | 音色克隆/训练在 MiniMax 控制台完成，本封装只负责用 `voice_id` 合成 |
| 上游是 TS 形态，本封装不复刻其 Worker 传输层 | 只复刻「合成契约」，工具语义对齐 |

---

## 六、测试用例（纯 Python）

| 用例 | 断言 |
|------|------|
| `test_agent_importable` | `VoiceMCPMinimaxAgent` 可实例化 |
| `test_handle_handoff_returns_json_string` | 返回可 parse 的 dict |
| `test_speak_degraded_without_creds` | 缺凭据 → `status=="error"` 且 `data.degraded is True` |
| `test_status_reports_not_ready_without_creds` | 缺凭据 → `data.ready is False` |
| `test_speak_empty_text_error` | 空文本返回 error |
| `test_unknown_tool_error` | 未知 tool_name 返回 error 而非抛异常 |
| `test_hex_to_base64_roundtrip` | hex → base64 可解码回原字节 |
| `test_speak_success` | mock t2a 响应 → `status=="ok"`，落盘 mp3 + base64 可解码回原字节 |
| `test_speak_upstream_error` | mock `base_resp.status_code==1004` → `status=="error"` 且 `data.status_code==1004` |
| `test_hex_to_base64_rejects_bad_hex` | 非法 hex 抛 `binascii.Error` |

---

## 七、交付物清单

- `mcpserver/voice_mcp_minimax/__init__.py`
- `mcpserver/voice_mcp_minimax/agent-manifest.json`
- `mcpserver/voice_mcp_minimax/voice_mcp_minimax.py`
- `mcpserver/voice_mcp_minimax/tests/test_voice_mcp_minimax.py`
- `docs/voice-mcp-minimax-MCP封装SPEC-v1.md`（本文档）

---

## 八、验收标准（可执行不变量）

```bash
# 1. manifest 存在且含 license 字段（许可可 grep）
test -f mcpserver/voice_mcp_minimax/agent-manifest.json \
  && grep -q '"license": "MIT"' mcpserver/voice_mcp_minimax/agent-manifest.json \
  && echo "ACCEPT 1: manifest + MIT license"

# 2. handler 可导入
python3 -c "from mcpserver.voice_mcp_minimax.voice_mcp_minimax import VoiceMCPMinimaxAgent; print('ACCEPT 2: import ok')" \
  | grep -q "ACCEPT 2" && echo "ACCEPT 2: handler importable"

# 3. 单元测试全绿（10 passed）
python3 -m pytest mcpserver/voice_mcp_minimax/tests/ -q | grep -q "10 passed" \
  && echo "ACCEPT 3: 10 tests passed"

# 4. registry 能扫描注册 voice_mcp_minimax
python3 -c "from mcpserver.mcp_registry import scan_and_register_mcp_agents as s; assert 'voice_mcp_minimax' in s(); print('ACCEPT 4: registered')" \
  2>&1 | grep -q "ACCEPT 4" && echo "ACCEPT 4: voice_mcp_minimax registered"

# 5. 未触碰主链路（NEKO / apiserver）
git diff origin/main --stat | grep -E "NEKO/N.E.K.O/|apiserver/" \
  && echo "FAIL 5: touched NEKO/apiserver" || echo "ACCEPT 5: no NEKO/apiserver changes"

# 6. 本次仅新增融合文件
git diff origin/main --name-only | grep -vE "^mcpserver/voice_mcp_minimax/|^docs/voice-mcp-minimax" | grep -v "^$" \
  && echo "FAIL 6: touched non-fusion files" || echo "ACCEPT 6: only fusion files changed"
```

---

## 九、提交规范

```bash
git add mcpserver/voice_mcp_minimax/ docs/voice-mcp-minimax-MCP封装SPEC-v1.md
git commit -m "feat(mcp): voice_mcp_minimax MCP 封装

- garan0613/voice-mcp (MIT) 改造接入：Python 复刻 MiniMax t2a_v2 克隆合成
- 两工具：voice_speak / voice_status（仅标准库 REST 客户端）
- 缺凭据优雅降级；环境变量调用时读取，可注入
- 10 tests passed, 0 failures"
```

---

*制定：Trae｜理论锚点：SPEC-Writing-Standard-v3.md · 系统工程四原则 · 不变量伴生验收*
