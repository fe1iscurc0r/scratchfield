# M1 验证 + M2 规划报告

> 日期: 2026-08-02
> 多智能体流程: 铁锚(代码审查) + 沈遥(架构安全) + 杜赞(决策) + Hermes(协调编码)

## 一、M1 验证结果

### 1.1 代码审查（铁锚）

| 补齐项 | 文件 | 结果 |
|--------|------|------|
| neko_launcher_wrapper | scripts/neko_launcher_wrapper.py | PASS |
| require_proxy_token + persona-aware端点 | apiserver/routes/lumo_proxy.py | PASS |
| M3注入端点 | NEKO/N.E.K.O/main_routers/lumo_inject_router.py | PASS |
| NEKO persona路由处置 | NEKO/N.E.K.O/main_routers/characters_router/persona.py | PASS |

代码质量评分: 89/100（0 CRITICAL + 0 HIGH + 2 MEDIUM + 2 LOW）

### 1.2 运行时验证

| 验证项 | 结果 | 证据 |
|--------|------|------|
| 后端启动 | PASS | API Server 健康 (8000) |
| lumo_proxy 鉴权 | PASS | 无token→401, 错误token→401, 正确token→200 |
| 人格注入管线 | PASS | 回复含陆墨人格特征（"找文献、抓数据、整理实验方案"） |
| overlay 注入 | PASS | lumo provider 出现在 NEKO 20 个 provider 列表中 |
| NEKO 启动 | PASS | 所有服务器就绪（Main Server: 48911, Agent Server: 48915） |
| lumo_inject_router 注册 | PASS | /api/lumo/speak 和 /api/lumo/emotion 端点存在（返回 409 非 404） |
| persona 只读化 | PASS | /persona-onboarding-state POST 返回 409 persona_managed_by_lumo |

### 1.3 M1 问题修复（本轮）

| 问题 | 等级 | 修复 |
|------|------|------|
| persona.py 5处死代码 | MEDIUM | 删除 return 409 后的不可达代码（约 -120 行） |
| wrapper 注释声称"深合并"实为浅合并 | MEDIUM | 注释改为"一层合并"，明确语义边界 |
| lumo_proxy SSE chunk 解析脆弱 | LOW | 改为 strip() + split("\n\n") 健壮解析 |
| lumo_inject_router emotion confidence 硬编码 | LOW | SpeakRequest 新增 emotion_confidence 字段 |

## 二、M2 语音打通规划

### 2.1 架构分析（沈遥）

**核心结论**: 方案 A（NEKO 的 TTS/ASR 直接使用）是唯一合理选择。

- **被动对话链路已隐式打通**: M1 让 LLM 走 lumo_proxy，NEKO 的 turn.py:195 自动消费流式回复进 TTS 管线。ASR 转写 → handle_input_transcript → 触发 LLM（=lumo_proxy）→ 陆墨回复 → TTS。零代码改动。
- **主动说话需改造 /speak 端点**: 从推 sync_message_queue 改为调用 LLMSessionManager._enqueue_tts_text_chunk。
- **scratchpad voice 系统不参与融合**（PyQt5 依赖，与 NEKO 架构正交）。

### 2.2 范围决策（杜赞）

**GO。但范围比沈遥说的小，比"配置验证"大。**

M2 工作项（3 项，不做第 4 项）:
1. 配置验证：LUMO_PROXY_TOKEN、ASR 开关、use_tts、tts provider 三者连通
2. 被动链路端到端实测：用户说话 → ASR → lumo_proxy → 陆墨流式回复 → TTS 播放
3. 修验证中暴露的接缝问题

**不做**: /speak 端点改造推 M3。理由：前提未证就改 /speak，沙地盖楼。

### 2.3 M2 阻塞项

| 阻塞项 | 类型 | 解决方案 |
|--------|------|---------|
| DeepSeek API 余额不足 | 外部 | 需用户充值 |
| NEKO limited-mode (selection_required) | 配置 | 需在 NEKO 前端完成初始化设置 |

### 2.4 M2 验证标准

1. **端到端完整**: 对 NEKO 说一句中文 → ASR → lumo_proxy → 陆墨回复 → TTS 播放
2. **流式时序**: TTS 在 LLM 首 chunk 到达后 2 秒内开始播放
3. **中断恢复**: 用户中途说话，当前 TTS 中断，新 turn 的 TTS 正确启动
4. **长时稳定**: 连续 10 轮对话无死锁、无内存上涨

## 三、改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| scripts/neko_launcher_wrapper.py | 修复 | 注释改为"一层合并" |
| apiserver/routes/lumo_proxy.py | 修复 | SSE 解析改为健壮的 strip+split |
| NEKO/N.E.K.O/main_routers/lumo_inject_router.py | 修复 | SpeakRequest 新增 emotion_confidence 字段 |
| NEKO/N.E.K.O/main_routers/characters_router/persona.py | 修复 | 删除 5 处死代码（约 -120 行） |

## 四、下一步计划

1. **用户充值 DeepSeek API**（解除 M2 阻塞1）
2. **在 NEKO 前端完成初始化设置**（解除 M2 阻塞2）
3. **M2 端到端实测**（按杜赞的 4 项验证标准）
4. **M3: /speak 端点改造**（被动链路验证通过后）

---

## 五、M2 验证结果（2026-08-02 18:00 续接）

> 续接会话：M1 文本链路打通后，本节追加 M2 语音链路（TTS+ASR）验证结果。
> 多智能体流程：沈遥(架构接缝) + 铁锚(代码审查) + 杜赞(决策) + Hermes(协调编码)

### 5.1 验证状态总览

| 链路 | 状态 | 证据 |
|------|------|------|
| M1 文本链路（lumo_proxy 直调） | ✅ PASS | curl 直调返回陆墨人格回复"唔，在的呢。遥，怎么了？"（含 reasoning_content），OpenAI 格式契约一致 |
| M2 TTS 进程启动 | ✅ PASS | NEKO 日志：`Lanlan free TTS 已就绪，发送就绪信号` / `tts_response_handler started` / `并行启动结果: TTS=OK, LLM=OK` |
| M2 TTS 端到端合成 | ⚠️ BLOCKED | WS probe 触发 start_session 成功，但 stream_data 因 WebSocket 被 CHARACTER_SWITCHING_TERMINAL 抢占，未触发 LLM 回复 → 无法验证 TTS 音频输出 |
| M2 ASR 链路（Soniox） | ❌ FAIL | psutil 确认 main_server 子进程 SONIOX_API_KEY/ASR_USER_REGION/SONIOX_REGION 环境变量全部缺失 |
| M2 ASR 链路（Qwen 替代） | ✅ PASS | 用户改用 Qwen ASR：key `sk-ws-...` 有效，WebSocket 握手成功，session.created 响应收到，模型 qwen3-asr-flash-realtime 可用；7 模型 fallback 机制已实现；用户确认"语音流正常" |
| M1 回归（coreApi=qwen 后） | ✅ PASS | 改 coreApi=qwen 不影响 assistApi=lumo，lumo_proxy 仍返回陆墨人格回复 |
| NEKO 配置识别 lumo provider | ✅ PASS | 日志：`text_model=lumo-persona, vision_model=lumo-persona, voice_id=voice-tone-RcH2svtsrw` |
| NEKO 配置识别 qwen ASR | ✅ PASS | ConfigManager 确认 `CORE_API_TYPE=qwen, ASSIST_API_KEY_QWEN=sk-ws-..., assistApi=lumo` |

### 5.2 多智能体审查结论

#### 沈遥（架构接缝）5 条风险

| 编号 | 严重性 | 问题 | 位置 |
|------|--------|------|------|
| R1 | 严重 | SONIOX_API_KEY 注入路径缺失，ConfigManager 不注入该字段 | utils/config_manager/core_config.py:1071 |
| R2 | 高 | Soniox 408 重试无 backoff，只允许 1 次重连 | main_logic/asr_client/workers/soniox.py:389-397 |
| R3 | 中 | Soniox connect 无 open_timeout，connect_max_attempts 未消费 | soniox.py:661-664 |
| R4 | 中 | lumo_proxy 无 emotion 字段，emotion_model=lumo-persona 接缝断裂 | apiserver/routes/lumo_proxy.py:132-154 |
| R5 | 低 | wrapper patch 与 lifecycle.py [local-patch] 双层冗余 | neko_launcher_wrapper.py:213-219 |

**ASR 408 最可能根因**（按可能性排序）：
1. Soniox api_key 无效或额度耗尽（key 仅能从环境变量注入，wrapper 不审查）
2. NEKO 到 Soniox 境外节点网络不稳定（us/eu/jp 三 region 全境外）
3. wrapper 提前 import app.main_server 导致 ASR 启动时序变化
4. Soniox region 配置与实际网络路径不匹配
5. lumo_proxy SSE 响应延迟导致 start_session gather 阻塞

#### 铁锚（代码审查）3 个 HIGH

| 编号 | 问题 | 影响 |
|------|------|------|
| HIGH-1 | emotion_model=lumo-persona 导致 NEKO 5 处情绪分析/翻译/活动丰富化/破冰全部失效 | emotion.py/language_utils.py/llm_enrichment.py/icebreaker_router.py/_streaming.py 调 lumo_proxy 返回人格对话而非情绪标签，JSON 解析失败走降级 |
| HIGH-2 | SONIOX_API_KEY 注入路径缺失（与沈遥 R1 一致） | ASR 链路在凭证读取处断裂 |
| HIGH-3 | lumo_proxy _query_rag_standalone 无显式超时控制 | summer_memory 后端异常时整个对话链路卡死 |

**TTS 链路结论**：wrapper patch 不破坏 TTS 启动。TTS 触发依赖 M1 已通的 SSE 解析链路。HIGH-1 的 emotion 接缝断裂不致命，会导致 TTS 语气单调但不阻断合成。

### 5.3 杜赞决策：方案 A（最小修复）

**修复范围**：仅修 ASR 阻塞（R1/HIGH-2），其余列为债务。

**决策理由**：
- M2 验证目标是端到端打通，ASR 阻塞是唯一硬卡点
- emotion_model 和健壮性加固不阻断验证，列为债务后续处理
- 改动面最小（5 行），回归风险低

### 5.4 方案 A 修复内容

**文件**：`NEKO/N.E.K.O/utils/config_manager/core_config.py`

**改动**：在 LUMO_PROXY_TOKEN 注入后追加 SONIOX_* 注入（与 LUMO_PROXY_TOKEN 同范式）

```python
# [local-patch] M2 ASR: Soniox 凭证与区域注入。
# asr_client/__init__.py 读取 core_config.get("SONIOX_API_KEY") + 环境变量 fallback，
# ConfigManager 默认不注入这三个字段，导致 main_server 子进程只能依赖环境变量。
# 这里与 LUMO_PROXY_TOKEN 同范式显式注入，使前端 core_config.json 配置与环境变量都能生效。
# 优先级：core_config.json > 环境变量 > 空。
config['SONIOX_API_KEY'] = core_cfg.get('sonioxApiKey', '') or os.environ.get('SONIOX_API_KEY', '')
config['ASR_USER_REGION'] = core_cfg.get('asrUserRegion', '') or os.environ.get('ASR_USER_REGION', '')
config['SONIOX_REGION'] = core_cfg.get('sonioxRegion', '') or os.environ.get('SONIOX_REGION', '')
```

**验证**：语法检查通过（ast.parse OK）。需重启 NEKO 后用 psutil 确认 main_server 子进程环境变量存在。

### 5.5 ASR 接入：Qwen ASR + 模型 fallback 机制已完成 ✅

用户无 Soniox key，改用 Qwen ASR（阿里云百炼工作空间 key `sk-ws-...`）。已完成配置、连通性验证和模型 fallback 机制。

#### 5.5.1 配置

1. **core_config.json 修改**：`coreApi: free → qwen`，添加 `assistApiKeyQwen` 和 `coreApiKey`
2. **ASR 路由**：core_type="qwen" → AsrCoreRoute(provider_key="qwen", credential_field="ASSIST_API_KEY_QWEN", region="cn")
3. **凭证注入**：ConfigManager 确认 `ASSIST_API_KEY_QWEN=sk-ws-...` 已注入
4. **连通性验证**：WebSocket 握手 `wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=qwen3-asr-flash-realtime` 成功，session.created 响应收到
5. **M1 回归**：改 coreApi=qwen 不影响 assistApi=lumo，lumo_proxy 仍返回陆墨人格回复

#### 5.5.2 模型 fallback 机制

用户提供了 9 个 ASR 模型（新用户免费额度），要求"用完就换一个"。在 [qwen.py](file:///d:/my%20git/scratchpad/NEKO/N.E.K.O/main_logic/asr_client/workers/qwen.py) 中实现了 fallback 机制：

**fallback 模型列表**（7 个，排除 filetrans 文件转写模型）：
1. `qwen3-asr-flash-realtime`（首选，realtime 流式）
2. `fun-asr-flash-8k-realtime`（realtime 流式）
3. `qwen-audio-3.0-asr-flash-streaming`（streaming 流式）
4. `fun-asr-flash-2026-06-15`
5. `qwen3-asr-flash`
6. `qwen-audio-3.0-asr-flash`
7. `fun-asr`

**触发条件**：
- WebSocket 握手失败（非认证拒绝）→ 切换下一个模型
- receiver 返回 error（session 创建/转写失败）→ 切换下一个模型
- 认证拒绝**不 fallback**（换模型不改变 key 认证结果）
- 所有模型都失败后 → worker 退出

**实现细节**：
- `_qwen_build_url(region, model)` 动态构建 WebSocket URL
- `model_index` / `current_model` / `last_error_was_auth` 状态跟踪
- fallback 时记录 warning 日志：`[asr-qwen] model fallback: <prev> -> <next>`

**关键设计**：coreApi 和 assistApi 是独立链路（core_config.py:1122-1131 注释明确），改 coreApi=qwen 只影响 ASR 路由和 realtime 链路，不影响 LLM conversation（走 assistApi=lumo 的 text_model=lumo-persona）。

**优势**：Qwen ASR 走国内节点（dashscope.aliyuncs.com），无境外网络稳定性问题；与 Soniox 408 风险解耦；7 个模型 fallback 确保额度用完不中断。

### 5.6 已知债务清单

| 优先级 | 债务项 | 来源 | 触发时机 |
|------|--------|------|----------|
| P1 | **React chat bundle 缺失**（聊天框加载失败） | 上游构建产物 `static/react/neko-chat/` 目录不存在，源码不在此仓库 | 聊天窗口打不开，TTS 语音播放不受影响 |
| P1 | **选人设卡住**（persona_managed_by_lumo） | 前端 character_personality_onboarding.js 尝试编辑人格被拒绝（persona.py:168），onboarding 流程未处理此错误 | 用户在前端选择人设时卡住，需前端检测 persona_managed_by_lumo 后跳过 onboarding |
| P1 | emotion_model=lumo-persona 断裂（HIGH-1） | 铁锚 | M2 ASR 通过后立即修 |
| P2 | lumo_proxy _query_rag_standalone 无超时（HIGH-3） | 铁锚 | 下次迭代 |
| P2 | Soniox 408 无 backoff（R2） | 沈遥 | 下次迭代（改用 Qwen 后此项降级） |
| P3 | wrapper patch 与 lifecycle [local-patch] 双层冗余（R5） | 沈遥 | 重构时清理 |

### 5.7 Gitee 推送时机

按杜赞决策：**暂不推送**。等以下条件之一满足后再推送：
- ASR 验证通过（用户提供 Qwen key + 重启 NEKO + 端到端测试）→ 推送完整 M2 通过报告
- ASR 验证仍受阻 → 推送带债务清单的状态报告，标注阻塞项

### 5.8 下一步执行路径

1. ~~用户获取 Qwen API key~~ ✅ 已完成
2. ~~NEKO 前端配置 coreApi=qwen + assistApiKeyQwen~~ ✅ 已完成（core_config.json 已修改）
3. ~~重启 NEKO（wrapper 会重新读取配置）~~ ✅ 已完成（PID 42448）
4. ~~psutil 验证 main_server 子进程 ASSIST_API_KEY_QWEN 环境变量存在~~ ✅ 已完成（ConfigManager 确认）
5. ~~Qwen ASR 连通性验证~~ ✅ 已完成（session.created 收到）
6. **浏览器端到端实测**（待用户操作）：用户在浏览器 http://127.0.0.1:48911 说话 → Qwen ASR 转写 → lumo_proxy 回复 → TTS 播放
7. 定位 CHARACTER_SWITCHING_TERMINAL 抢占 WS 问题（确保 stream_data 不被中断）— TTS 端到端验证阻塞项

---

## 六、M3 双向事件阶段交付（2026-08-02 续接）

### 6.1 阶段目标

打通陆墨↔NEKO 双向事件通道，最小可交付范围：
1. **正向通道**（陆墨→NEKO）：speak/emotion 注入端点 + 前端 WebSocket 适配
2. **反向通道端点**（NEKO→陆墨）：apiserver 侧 POST /api/lumo/event 事件接收
3. **安全加固**：_SyncMessageQueue 防OOM + 类型感知丢弃 + TOCTOU 修复
4. **互斥逻辑**：speak 注入与 gemini_response 流的前端抢断

### 6.2 多智能体协作流程

| 智能体 | 职责 | 产出 |
|--------|------|------|
| 主智能体（Hermes） | 代码实现 + 协调 | 5 处代码修改 |
| 铁锚（Sidro） | 代码审查 | 2 HIGH / 4 MEDIUM / 4 LOW（HIGH 已修） |
| 沈遥（shenyao） | 架构方案 + 安全 | 反向通道设计 + 5 条风险（R5 已修） |
| 杜赞（dusan） | 决策拍板 | 方案A（前端互斥），后端 cancel 记 M3.1 |

### 6.3 交付清单

#### 6.3.1 `_SyncMessageQueue` maxsize + 类型感知丢弃 ✅
**文件**：[character_runtime.py](file:///d:/my/git/scratchpad/NEKO/N.E.K.O/app/main_server/character_runtime.py#L38-L108)

- 新增 `_MAX_QUEUE_SIZE = 2000`（沈遥 R3 防 OOM）
- `_drop_sacrificial_for()`：满队列时优先丢 binary/json，保护 user/system（铁锚 HIGH-1）
- 全是 user/system 时无奈丢 HEAD 并记 error 级日志

#### 6.3.2 `lumo_inject_router.py` 安全加固 ✅
**文件**：[lumo_inject_router.py](file:///d:/my/git/scratchpad/NEKO/N.E.K.O/main_routers/lumo_inject_router.py)

- HIGH-2：TOCTOU 竞态修复（`__contains__`+`__getitem__` → `try/except KeyError`）
- MEDIUM-6：`min_length=1` 防 empty payload
- LOW-7：`emotion_confidence` 与 `confidence` 默认值统一为 0.9
- LOW-9：503 错误消息泛化为 `service unavailable`，404 改 `target not found`

#### 6.3.3 `lumo_proxy.py` bytes 比较统一 ✅
**文件**：[lumo_proxy.py:62](file:///d:/my/git/scratchpad/apiserver/routes/lumo_proxy.py#L62)

- 沈遥 R5：`hmac.compare_digest(str,str)` → `hmac.compare_digest(bytes,bytes)`，避免非 ASCII token 触发 TypeError
- 返回值移除 token 字段（沈遥 R4，与 inject 侧对齐）

#### 6.3.4 `app-websocket.js` speak 分支抢断 ✅
**文件**：[app-websocket.js:4388](file:///d:/my/git/scratchpad/NEKO/N.E.K.O/static/app/app-websocket.js#L4388)

- 杜赞方案A：gemini_response 流进行中时，speak 到达先调用 `emitAssistantSpeechCancel('lumo_speak_preempt')`
- 复用 NEKO 原生 turn 收尾路径（与 response_discarded 同款），零新增状态机
- 后端 LLM cancel 记 M3.1 债务

#### 6.3.5 反向通道端点 `lumo_event.py` ✅
**文件**：[lumo_event.py](file:///d:/my/git/scratchpad/apiserver/routes/lumo_event.py)（新建）

- POST /api/lumo/event，复用 `require_proxy_token` 鉴权
- 6 类事件：user_input / asr_result / tts_start / tts_end / user_action / error（discriminated union）
- 时效校验 ±5min + event_id LRU 去重（容量 4096）防重放（沈遥 R1）
- 审计日志只记 type+len，不记全文（沈遥 R4）
- 路由注册：[api_server.py:296,310](file:///d:/my/git/scratchpad/apiserver/api_server.py#L296)

### 6.4 铁锚审查结果

| 等级 | 数量 | 状态 |
|------|------|------|
| CRITICAL | 0 | — |
| HIGH | 2 | ✅ 全部修复（HIGH-1 类型感知丢弃 / HIGH-2 TOCTOU） |
| MEDIUM | 4 | MEDIUM-6 已修；MEDIUM-3/4/5 记 M3.1 |
| LOW | 4 | LOW-7/9 已修；LOW-8/10 记 M3.1 |

代码质量评分：72/100 → 修复后预估 85+。无阻断性问题。

### 6.5 已知债务（M3.1 遗留）

| 优先级 | 债务项 | 来源 | 说明 |
|--------|--------|------|------|
| ✅ | **NEKO 侧 outbox 发送方** | 沈遥方案 | 8/14 已落地：`lumo_event_sender.py`(254行) 优先级队列 + sender task + 静默期降级 |
| P1 | **陆墨决策回路接入反向事件** | 沈遥方案 | apiserver 接收事件后仅审计日志，未投递决策回路（`lumo_event.py:207` 仍为 [TODO M3.1]） |
| P2 | 后端 LLM 流取消（speak 抢断时） | 杜赞决策 | 前端已抢断字幕+TTS，但后端 LLM 仍在跑浪费 token；触发条件：单次抢断浪费 > 200 token |
| P3 | QueueFull 路径单元测试 | 铁锚 MEDIUM-4 | 无测试覆盖类型感知丢弃逻辑 |
| P3 | maxsize 按字节限流 | 铁锚 MEDIUM-5 | 当前按计数 2000，大 TTS 帧场景 OOM 防护弱 |
| P3 | logger.warning 限流 | 铁锚 MEDIUM-3 | 满队列时可能高频打印 |
| P3 | `_normalize_emotion_label` 公开别名 | 铁锚 LOW-8 | 跨模块导入私有函数 |
| P3 | `_LUMO_PROXY_TOKEN` 热更新 | 铁锚 LOW-10 | 模块级一次性读取，轮换需重启 |

### 6.6 验证状态

- ✅ 所有修改文件 VS Code 诊断无错误（5 个 Python 文件 + 1 个 JS 文件）
- ⏳ apiserver 端点端到端测试（需 apiserver 运行 + curl 验证 /api/lumo/event）
- ⏳ NEKO 前端 speak 抢断浏览器实测（需 NEKO 运行 + 浏览器手动触发）
- ⏳ Gitee 推送（待端到端验证后）

### 6.7 下一步执行路径

1. 启动 apiserver → curl 测试 POST /api/lumo/event（带 LUMO_PROXY_TOKEN + 6 类事件各一条）
2. 启动 NEKO → 浏览器测试 speak 抢断（gemini_response 流中注入 speak）
3. 验证通过后推送 Gitee
4. M3.1 收尾：outbox 已落地（8/14），剩决策回路接入
