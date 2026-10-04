# TTS-API MCP 封装 SPEC · v1

> 施工方：Hermes（实验田维护者代施工）｜审查：实验田维护者｜日期：2026-08-16
> 目标：把 babutree/TTS-API（37★，MIT）封装为陆墨 MCP 工具体系的一个 agent。

---

## 〇、一句话定位

**TTS-API 是独立部署的 TTS 网关，不是库。** 封装 = 写一个 HTTP 客户端 agent，通过 OpenAI 兼容端点 `POST /v1/audio/speech` 调它，把「文本 → 音频文件」暴露为 MCP 工具 `tts_speak`。

## 一、四问

| 问 | 答 |
|---|---|
| 边界 | **做**：`tts_speak` / `tts_list_voices` / `tts_health` 三个工具的 HTTP 客户端封装。**不做**：内置模型权重、部署 TTS-API 服务、内联音频播放器 UI |
| 层次 | 在「MCP 工具层」操作，不碰 TTS-API 服务内部、不碰 NEKO 源码、不碰 apiserver 主链路 |
| 关系 | `TTSApiAgent --HTTP--> TTS-API 服务(localhost:8880)`，换掉 TTS-API 只要改 `base_url`，agent 逻辑不变 |
| 目的 | `python -m pytest mcpserver/tts_api/` 全过 = 封装合格 |

## 二、架构

```
MCP 调度(unified_call)
  └─ TTSApiAgent.handle_handoff(task)   # 对齐 material_science 契约
       └─ invoke(command, params)
            ├─ tts_speak     → POST /v1/audio/speech → 音频落盘 → 返回 {path, size_bytes}
            ├─ tts_list_voices → GET /v1/audio/voices
            └─ tts_health     → GET /
```

环境变量（零硬编码，对齐 mcpserver 约束 9）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `TTS_API_BASE_URL` | `http://localhost:8880` | TTS-API 网关地址 |
| `TTS_API_KEY` | 空 | API Key（TTS-API 开 key 认证时必填） |
| `TTS_OUTPUT_DIR` | `/tmp/tts_api` | 音频落盘目录 |

## 三、许可

MIT → 主仓 AGPL v3 允许直接吞。`agent-manifest.json` 已标注 `"license": "MIT"`。

## 四、验收标准（可执行不变量）

```bash
# 1. 测试全过（离线 mock，不依赖真实服务）
python -m pytest mcpserver/tts_api/ -q          # 7 passed

# 2. manifest 含 license（工单验收）
grep -c '"license"' mcpserver/tts_api/agent-manifest.json   # ≥1

# 3. 不碰主流程
git diff --stat -- NEKO apiserver | wc -l       # 0

# 4. 零硬编码密钥
grep -rn "api_key\s*=" mcpserver/tts_api/agent.py | grep -v environ | wc -l   # 0
```

## 五、已知限制

1. **不内置模型**：合成依赖 TTS-API 服务在线，服务没起时 `tts_speak` 返回连接错误（不静默失败）。
2. **返回路径而非字节流**：`handle_handoff` 返回 JSON 字符串，无法承载二进制音频，故音频落盘、上层拿 `path` 再转发（如微信 `MEDIA:<path>`）。
3. **无内联播放器**：上游的 WeChat 风格波形播放器依赖 MCP `ext-apps` UI 扩展，本仓调度层无 structuredContent 通道，暂不复用。

## 六、提交

```
feat(mcp): TTS-API MCP 封装（MIT，/v1/audio/speech 客户端）
```
