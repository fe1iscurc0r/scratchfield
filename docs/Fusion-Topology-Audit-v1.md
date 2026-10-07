# 融合总线拓扑审计 v1

> 审查日期: 2026-08-02
> 审查范围: scratchpad (陆墨) × N.E.K.O. (身体) 全融合面
> 排除: hermes-shell (手机端)、蜜罐/部署脚本

---

## 一、进程拓扑（许可证隔离层）

```
┌───── AGPL-3.0 区（scratchpad 进程）─────────────┐
│                                                  │
│  apiserver (FastAPI :8000)                       │
│  ┌─────────────────────────────────────────────┐ │
│  │ 路由层 (13 个路由模块, 16,388 行)              │ │
│  │                                              │ │
│  │ ⬜ 融合自研 (无 AGPL 污染)                     │ │
│  │  ├─ lumo_proxy.py         378 行              │ │
│  │  │   POST /persona/v1/chat/completions       │ │
│  │  │   鉴权: require_proxy_token               │ │
│  │  │   职责: 人格注入 → RAG → 上游 LLM          │ │
│  │  │                                          │ │
│  │  └─ lumo_event.py          197 行             │ │
│  │      POST /api/lumo/event                     │ │
│  │      鉴权: require_proxy_token               │ │
│  │      职责: NEKO→陆墨 6类反向事件接收           │ │
│  │      类型: user_input/asr_result/              │ │
│  │             tts_start/tts_end/                 │ │
│  │             user_action/error                  │ │
│  │                                              │ │
│  │ ⬜ 原有路由 (AGPL 继承, 13 处引用)              │ │
│  │  ├─ agentserver/ (6)    非融合核心             │ │
│  │  ├─ system/ (5)         配置/健康检查           │ │
│  │  └─ voice/ (2)         TTS 模块 (未启用)       │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ═══════════ HTTP 进程边界 ═══════════════════   │
│  (独立程序 API 通信，不触发 GPL/AGPL 传染)          │
│                                                  │
└──────────────────────┬───────────────────────────┘
                       │ HTTP (127.0.0.1)
┌────── Apache 2.0 区 (NEKO 进程) ──────────────────┐
│                                                    │
│  NEKO 三服务器 (neko_launcher_wrapper.py 启动)       │
│  ┌──────────────────────────────────────────────┐  │
│  │ Main Server     :48911                       │  │
│  │   web_app.py    → 注册 lumo_inject_router    │  │
│  │   cross_server.py  → 消息总线 + memory 隔离   │  │
│  │                                              │  │
│  │ Agent Server    :48915                       │  │
│  │ Local Server    :48912 (127.0.0.1 only)      │  │
│  │                                              │  │
│  │ [local-patch] 改动清单 (铁律3 只改 7 个文件):    │  │
│  │  ├─ cross_server.py        speak 分叉+L838    │  │
│  │  ├─ tts_runtime.py         synthesize_ext...  │  │
│  │  ├─ turn.py                mirror_asst_speech │  │
│  │  ├─ persona.py             只读化 409          │  │
│  │  ├─ lumo_inject_router.py  speak/emotion 注入  │  │
│  │  ├─ core_config.py         ASR key 注入       │  │
│  │  └─ app-websocket.js       speak 分支+turnId  │  │
│  └──────────────────────────────────────────────┘  │
│                                                    │
└────────────────────────────────────────────────────┘
```

---

## 二、通信协议拓扑

### 正向（陆墨 → NEKO）

| 端点 | 方法 | 鉴权 | 数据 | 状态 |
|------|------|------|------|------|
| /api/lumo/speak | POST | require_proxy_token | SpeakRequest(text, emotion, lanlan_name) | ✅ M3 |
| /api/lumo/emotion | POST | require_proxy_token | EmotionRequest(emotion, intensity, lanlan_name) | ✅ M3 |

### 反向（NEKO → 陆墨）

| 端点 | 方法 | 鉴权 | 数据 | 状态 |
|------|------|------|------|------|
| /persona/v1/chat/completions | POST | require_proxy_token | OpenAI 兼容 (流式+非流式) | ✅ M1 |
| /api/lumo/event | POST | require_proxy_token | 6 类事件 (LRU去重+时效校验) | ✅ M3 |

### 鉴权体系

| 鉴权类型 | 用途 | 实现 |
|----------|------|------|
| require_local_auth | 原有用户登录 | `apiserver/auth.py` |
| require_proxy_token | 融合进程间通信 | `apiserver/routes/lumo_proxy.py:hmac.compare_digest` |
| LUMO_PROXY_TOKEN 注入 | 启动时生成 32B 随机 | `lumo_fusion.ps1` → wrapper → ConfigManager |

---

## 三、许可证边界（AGPL-3.0 传染分析）

### 现状: 安全

- scratchpad 进程 **不 import NEKO 代码**，仅通过 HTTP 调用
- NEKO 进程 **不 import scratchpad 代码**，仅通过 HTTP 调用
- **GPL/AGPL 传染条款不适用于"独立程序的 API 通信"**
- AGPL 引用仅 13 处（agentserver 6 / system 5 / voice 2），非融合核心路径

### 传染触发条件（当前未触发）

1. scratchpad 进程 `import` NEKO 模块 → ❌ Apache 2.0 → AGPL 传染 → 必须开源整个融合体
2. NEKO 进程 `import` scratchpad 模块 → ❌ 反向传染（Apache 2.0 不兼容 AGPL）
3. 把 NEKO 源码文件移入 scratchpad 目录树 → ⚠️ 视同合并，触发传染

### 商业化路径

- 当前: AGPL-3.0（开源） + 商业双许可（需 RTGS2017 授权）
- 目标: 自主版权 → 逐步替换 NagaAgent 继承代码
- 阻断: 商业双许可的 Licensor = RTGS2017，不是你
- **短期内保持开源是唯一合规路径**

---

## 四、责任边界（谁拥有什么）

| 资产 | 归属 | 实现 | 备注 |
|------|------|------|------|
| 人格/记忆 | 陆墨独占 | persona.py 只读化 + 五维记忆关闭 | ✅ |
| 知识库(RAG) | 陆墨独占 | lumo_proxy 旁路 RAG | ✅ |
| LLM 推理 | 陆墨独占 | lumo_proxy 人格注入管线 | ✅ |
| 字幕 DOM | 陆墨指令,NEKO 执行 | send_lanlan_response | ✅ M4 |
| TTS 说话 | 陆墨指令,NEKO 管线 | synthesize_external_text（直接调底层，绕过 mirror_assistant_speech） | ✅ M4 |
| ASR 听 | NEKO 独占 | Qwen ASR (7模型fallback) | ✅ M2 |
| Live2D/VRM | NEKO 独占 | 模型配置文件 | Steam 工坊提取待确认 |
| CUA 操作 | NEKO 独占 | neko_cua 分支(沙箱) | M4 后启动 |
| emotion 情绪 | ⚠️ 断层 | emotion_model=lumo-persona 断裂 | P1 债务 |
| 记忆五维 | ❌ NEKO 侧关闭 | SERVERS 过滤无 memory_server | ✅ |

---

## 五、拓展口清单

| # | 拓展口 | 类型 | 示例用途 |
|---|--------|------|----------|
| 1 | lumo_proxy provider | API 端点 | 换模型/CosyVoice/新材料源 |
| 2 | lumo_event 事件类型 | Pydantic schema | 新事件类型注册 |
| 3 | mirror_meta source | 元数据标记 | 新注入源标记 |
| 4 | 插件 SDK | NEKO 插件系统 | 第三方扩展，不动源码 |
| 5 | Live2D 模型替换 | 配置文件 | Steam 工坊提取/自建模 |
| 6 | ConfigManager injection | 环境变量注入 | 新 key/凭证注入路径 |

---

## 六、调试后门规范（待建设）

### 设计原则

1. **只读** — 只做 dump，不做 write/execute
2. **统一前缀** — 所有端点 `/debug/dump/` 开头，易于清理
3. **proxy_token 鉴权** — 复用 require_proxy_token，不开裸端口
4. **债务标注** — 每条带创建日期 + 计划清理日期

### 建议端点

| 路径 | 用途 | 计划删除 |
|------|------|----------|
| /debug/dump/tts_state | TTS 管线状态 | M4 smoke test 后 |
| /debug/dump/sync_queue | SyncMessageQueue 内容 | M4 smoke test 后 |
| /debug/dump/memory_stats | 五维记忆统计 | M5 后 |
| /debug/dump/rag_hits | RAG 召回命中 | 长期（开发期保留） |

### 债务追踪

```python
# 统一的调试后门标记
DEBUG_PORT_DEBT = {
    "created": "2026-08-02",
    "owner": "M4 smoke test",
    "cleanup_by": "M5 完成",
    "principle": "只读 / proxy_token / 统一前缀"
}
```

---

## 七、M4/M3.2 状态标记

| 项 | 文件 | 行号 | 状态 |
|----|------|------|------|
| synthesize_external_text 完整实现 | tts_runtime.py | 67-168 | ✅ M4 已修（改用直接调底层方法） |
| _speak_tasks GC 保护 | cross_server.py | 827, 866-873 | ✅ 已修 |
| cross_server speak 分叉 | cross_server.py | 855-879 | ✅ M3.1 完成 |
| lumo_inject_router QueueFull | lumo_inject_router.py | - | ✅ M3.1 修 |
| lumo_event LRU off-by-one | lumo_event.py | - | ✅ M3.1 修 |
| emotion_model 断裂 | - | - | ⚠️ P1 债务（M4 后修） |
| naive datetime 收紧 | lumo_event.py | - | ⚠️ M3.2（非 M4） |
| 消息合并原子性 | - | - | ⚠️ M3.2（非 M4） |

---

## 八、AGPL 继承代码位置（13 处引用）

| 文件 | 模块 | 行数 | 处置 |
|------|------|------|------|
| agentserver/openclaw/embedded_runtime.py | 执行层 | 4 处 | 非核心，搁置 |
| agentserver/clawdbot/... | 代理层 | 2 处 | 非核心，搁置 |
| system/ | 系统/配置 | 5 处 | 基础设施，重写成本高 |
| voice/ | TTS 语音模块 | 2 处 | 不在融合路径上，搁置 |

**结论: 13 处 AGPL 引用均不在融合核心路径上，不阻碍 M4-M5。**

---

*审查人: 沈遥 (deepseek-v4-pro)*
*数据来源: scratchpad commit 27cda9f (M4 smoke test 修复后)*
*铁锚修正: 2026-08-02（行号/状态/端点路径核准）*
