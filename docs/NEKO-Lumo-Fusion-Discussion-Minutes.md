# NEKO × 陆墨融合指导书 v1.0 多智能体讨论纪要

**讨论日期**: 2026-08-01
**指导书**: docs/NEKO-Lumo-Fusion-Blueprint-v1.0.md
**参与智能体**:
- 铁锚 (kimi2.7code) — 代码可行性审查
- 实验田维护者 (deepseekv4pro) — 架构与安全审视
- 杜赞 (GLM5.2) — 决策与路线图审查
- Hermes (千问3.7plus) — 协调与汇总

---

## 一、三方共识（5 项硬伤必须先修）

### 共识 1：CUA 沙箱路径写错 — 三方一致发现

**指导书原文**: 第四章第1条 `brain/cua/core/engine.py` 移除 `__builtins__`/`os` 暴露

**实际代码**: [computer_use.py:1182-1191](file:///d:/my/git/scratchpad/NEKO/N.E.K.O/brain/computer_use.py#L1182-L1191) 才是真正的 exec 沙箱

```python
exec_env: dict = {"__builtins__": __builtins__}  # 全量暴露
exec_env["os"] = os                               # os.system 可达
exec(code, exec_env)                              # RCE 直通车
```

`brain/cua/core/engine.py` 是 LLM 客户端封装，无任何 exec 调用。

**影响**: 按指导书路径验收会找不到漏洞，M4 安全前置条件形同虚设。

**修复**: 指导书路径改为 `brain/computer_use.py:1182-1191`。

---

### 共识 2：openai_proxy 不注入人格，M1 "陆墨回答" 是假的

**指导书原文**: M1 动作1 "NEKO api_providers.json 新增 lumo provider → scratchpad openai_proxy"

**实际代码**: [openai_proxy.py](file:///d:/my/git/scratchpad/apiserver/routes/openai_proxy.py) 是**透传代理**，直接转发到外部 LLM（默认 DeepSeek），**不调用** `build_system_prompt`、不注入 persona/session/RAG。人格注入逻辑在 [chat.py](file:///d:/my/git/scratchpad/apiserver/routes/chat.py) 的 `/chat` 路由，但该路由非 OpenAI 兼容。

**影响**: NEKO 指向 openai_proxy 后得到的是裸模型回复，违反"单一灵魂"原则。M1 验证标准"陆墨回答"无法达成。

**修复**: scratchpad 新增 persona-aware OpenAI 兼容端点 `/v1/chat/completions`（包装 build_system_prompt + RAG + session），约 150 行。

---

### 共识 3：M3 的 WebSocket 推送协议错配

**指导书原文**: M3 "scratchpad → NEKO ws_router 主动推送"

**实际代码**: NEKO [websocket_router.py](file:///d:/my/git/scratchpad/NEKO/N.E.K.O/main_routers/websocket_router.py) 是**前端协议端点**（接收浏览器音频帧/聊天消息），无外部事件注入接口。scratchpad [websocket_manager.py](file:///d:/my/git/scratchpad/apiserver/websocket_manager.py) 是服务端推送管理器（推给自己前端），非 WS 客户端。

**影响**: M3 会卡在"NEKO 侧没有接收方"。强行复用前端 ws 会触发音频帧处理逻辑。

**修复**: 放弃 ws 推送，改用 REST。NEKO main_server 已有 REST 路由，scratchpad 通过 `POST /api/...` 触发表情/搭话更简单，且不碰 NEKO 源码。

---

### 共识 4：鉴权链路未定义 — M1 隐藏阻塞项

**问题**: scratchpad 的 openai_proxy / persona / chat 全带 `require_local_auth`。NEKO 作为外部客户端如何拿 token、如何鉴权？指导书零字提及。

**影响**: M1 直接卡死。NEKO 调不动 scratchpad 任何带鉴权的接口。

**修复**: 定义进程间共享密钥（环境变量 `LUMO_PROXY_TOKEN`），或 NEKO 启动时从 scratchpad 获取 token。

---

### 共识 5：CUA 沙箱收紧与"不修改 NEKO 源码"铁律自相矛盾

**问题**: 铁律第3条"不修改 NEKO 源码" vs 铁律第4条"CUA 沙箱不收紧前不得接 Agent"。收紧沙箱必须改 `brain/computer_use.py`（NEKO 源码）。

**修复方案**:
- **方案A**: 铁律第3条增加"安全前置豁免"条款，允许修改 computer_use.py
- **方案B**: 沙箱收紧逻辑写到 scratchpad 侧（M4 调用前注入受限 globals），不动 NEKO 源码。但 NEKO 独立运行 CUA 时仍裸露

---

## 二、三方分歧

### 分歧 1："单一灵魂"原则的边界

**杜赞**: "关掉 NEKO 脑子"过于绝对。建议改为"单一决策源 + 单一记忆源 + 单一人格源"，不是关掉所有模型。应保留 NEKO 的：
- emotion_model（情绪标签）— 本地小模型比陆墨额外调 LLM 便宜
- vision_model（视觉理解）— 属"身体感知"
- summary/correction（摘要/纠错）— 内部管线优化

**铁锚/实验田维护者**: 未对此表态，但铁锚确认 NEKO 有 6 个独立 model 角色（conversation/emotion/vision/agent/summary/correction）。

**Hermes 建议**: 采纳杜赞的细化方案。emotion 执行在 NEKO，emotion 记忆在陆墨；vision 留 NEKO；conversation/agent/人格/记忆归陆墨。

### 分歧 2：emotion 归属

**指导书**: 架构图把"情绪 (emotion label)"画在陆墨侧

**杜赞**: 陆墨代码无 emotion 输出端点，NEKO 的 emotion_model 是独立管线。矛盾必须在 M1 之前拍板。

**Hermes 建议**: emotion label 由 NEKO 本地出，回传陆墨存储。理由是成本。

---

## 三、需用户拍板的决策点（7 项）

| # | 决策点 | 选项 | 建议 |
|---|--------|------|------|
| D1 | emotion 归属 | A. 陆墨出 / B. NEKO 出+回传陆墨 | **B**（成本更低） |
| D2 | M1 人格端点 | A. 新建 `/v1/chat/completions` / B. 改造 openai_proxy | **A**（无回归） |
| D3 | M3 通信方式 | A. WebSocket / B. REST | **B**（不碰 NEKO 源码） |
| D4 | CUA 沙箱收紧 | A. 改 NEKO 源码（豁免铁律3）/ B. scratchpad 侧注入 | **A**（更彻底） |
| D5 | 鉴权机制 | A. 环境变量共享密钥 / B. NEKO 启动时获取 token | **A**（更简单） |
| D6 | 记忆一致性 | A. 云服唯一实例（本地走公网）/ B. 本地+云服同步 | **需用户定** |
| D7 | api_providers.json | A. 直接改 NEKO 配置 / B. scratchpad 侧 overlay 注入 | **B**（不被上游冲掉） |

---

## 四、各里程碑可行性汇总

| 里程碑 | 铁锚评估 | 实验田维护者评估 | 杜赞评估 | 综合结论 |
|--------|----------|----------|----------|----------|
| **M1 文本打通** | ⚠️ 需适配（proxy 不带人格） | — | ⚠️ 隐藏阻塞（鉴权+人格） | **需新建 persona-aware 端点 + 定义鉴权** |
| **M2 语音打通** | ✅ 可直接实施 | ⚠️ openai_proxy 伪流式延迟 | ⚠️ 缺 emotion 归属决策 | **基本可行，需先拍板 emotion + 评估流式延迟** |
| **M3 双向事件** | ⚠️ 需适配（无入站端点） | ⚠️ 协议错配（改 REST） | ⚠️ 拆分不足（M3a/M3b） | **改 REST + 拆分为 M3a(单向推送) / M3b(双向搭话)** |
| **M4 Agent 执行** | ⚠️ 需适配（HTTP 桥接） | — | ⚠️ 安全前置没做完不敢接 | **先修沙箱 + 再加 neko_cua 分支** |
| **M5 记忆融合** | — | ⚠️ 多实例无同步 | ⚠️ 无验证标准+"成熟"无定义 | **需另写详细方案** |

---

## 五、指导书勘误清单

| # | 原文 | 实际 | 严重度 |
|---|------|------|--------|
| E1 | `brain/cua/core/engine.py` 移除沙箱 | 应为 `brain/computer_use.py:1182-1191` | CRITICAL |
| E2 | M1 → openai_proxy 实现"陆墨回答" | openai_proxy 是透传，不注入人格 | CRITICAL |
| E3 | M1 → memory_settings 关闭记忆 | memory_settings.py 无总开关，需不启动 memory_server 进程 | HIGH |
| E4 | 8家文本+6家Realtime | 实际19家文本+8家Realtime | MEDIUM |
| E5 | CosyVoice 免费阶跃版 | CosyVoice(DashScope) ≠ StepFun(阶跃) | MEDIUM |
| E6 | 嘴型同步"参数映射" | 前端 RMS 驱动 setMouth | LOW |
| E7 | Agent Server 端口48915 | config/network.py 未定义该端口 | LOW |
| E8 | `.upstream-sha` 记录同步点 | 文件不存在，需创建 | MEDIUM |
| E9 | 第四章只查 Memory/Agent 端口 | monitor_server (48913) 绑定 0.0.0.0 未提及 | HIGH |

---

## 六、补充铁律建议

指导书原有 6 条铁律，建议补充 2 条：

**铁律7（鉴权边界）**: NEKO 跨进程调用 scratchpad 必须定义 token 机制（环境变量 `LUMO_PROXY_TOKEN`），所有跨进程接口必须校验。

**铁律8（配置 overlay）**: NEKO 侧配置变更（如 api_providers.json 加 lumo provider）不直接改 NEKO 文件，通过 scratchpad 侧 overlay 注入，避免上游更新冲掉。

---

## 七、风险清单（按概率×影响排序）

| 排序 | 风险 | 概率 | 影响 | 来源 |
|------|------|------|------|------|
| 1 | CUA 沙箱路径错，没真收紧就接 Agent | 高 | 致命 | 三方共识 |
| 2 | M1 proxy 不带人格，"陆墨脑子"是假的 | 高 | 高 | 铁锚+杜赞 |
| 3 | 鉴权链路未定义，NEKO 调不动 scratchpad | 高 | 高 | 杜赞+实验田维护者 |
| 4 | M3 ws 推送协议错配，卡住 | 高 | 中 | 铁锚+实验田维护者 |
| 5 | emotion 归属矛盾，M2 嘴型无 label | 中 | 中 | 杜赞 |
| 6 | api_providers.json 被上游更新冲掉 | 中 | 中 | 杜赞 |
| 7 | 多实例记忆不一致（笔记本关机场景） | 中 | 中 | 实验田维护者 |
| 8 | monitor_server 0.0.0.0 对话泄露 | 中 | 高 | 实验田维护者 |
| 9 | M5 无验证标准，永久延期 | 中 | 低 | 杜赞 |
| 10 | openai_proxy 伪流式延迟影响 TTS | 中 | 中 | 实验田维护者 |

---

## 八、总结

**战略判断对**: 单一灵魂、关 NEKO 脑子、记忆放最后、不吞 AGPL 进 Apache — 方向正确。

**战术层有 5 处硬伤**: 沙箱引错文件、proxy 不带人格、鉴权未定义、M3 协议错配、记忆一致性空白。

**结论**: 修完 5 处硬伤 + 拍板 7 项决策点后，指导书可指导 M1-M4 落地。M5 形同空白，需另写。

**人力估算**: 单人串行 M1-M4 约 3-4 个月。M1（鉴权+人格端点）和 M4（安全前置）是最可能卡住的里程碑。

---

*纪要由 Hermes (千问3.7plus) 协调生成，铁锚 (kimi2.7code) / 实验田维护者 (deepseekv4pro) / 杜赞 (GLM5.2) 并行审查。*
