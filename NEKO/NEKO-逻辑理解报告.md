# NEKO（猫娘计划）逻辑理解报告

**审视日期**: 2026-08-01
**审视对象**: d:\my git\NEKO\N.E.K.O（NEKO-windows-src.zip 解压源码）
**参与智能体**: 铁锚（代码审查）、实验田维护者（架构安全）、杜赞（决策审视）、Hermes（本体协调）
**审视模式**: 只读全量审视，未修改/删除任何文件

---

## 一、项目定位

**N.E.K.O** = Networked Emotional Acknowledging Organism（网络型情感知性生命体）

一句话定位：**不是帮你干活的 Agent，也不是陪你角色扮演的聊天前端——而是有现实时间感知、会主动找你、记得你、也能动手帮你的「数字生命」**。

- **License**: Apache 2.0（商业友好，可闭源衍生）
- **Python**: 3.11
- **Steam**: 已上架创意工坊（角色卡/Avatar/语音包 UGC）
- **规模**: ~111MB 源码，三服务器架构

---

## 二、系统架构

### 三服务器进程隔离

| 服务 | 端口 | 职责 |
|------|------|------|
| **Main Server** | 48911 | Web UI、REST API、WebSocket、会话管理、外部 TTS |
| **Memory Server** | 48912 | 对话摄入、近期上下文、事实/反思/人格、recall |
| **Agent Server** | 48915 | 能力状态、任务评估、通道分发、任务结果 |
| 嵌入式插件服务 | 48916 | 用户插件 HTTP（隔离线程） |
| Monitor Server | 48913 | 镜像流（可选） |

### 通信协议分层

```
Browser ──HTTP+WS──> Main :48911
Main ├──HTTP──> Memory :48912
     ├──HTTP control──> Agent :48915
     ├──HTTP proxy──> Plugin :48916
     └──ZeroMQ bridge──> Agent
         PUB  :48961 ──> Agent SUB   (session/lifecycle)
         PUSH :48963 ──> Agent PULL  (analyze requests)
         PULL :48962 <── Agent PUSH  (ACKs/results)
```

**协议选型逻辑**：HTTP 承载可观测的请求-响应；ZeroMQ 专管 Agent 事件桥（低延迟、解耦）。关键："Agent-to-Main results have no HTTP fallback"——Agent 是后台可选任务，丢一次不致命。

---

## 三、核心模块逻辑

### 1. 五维记忆系统（memory/）

| 层 | 文件 | 职责 |
|----|------|------|
| 工作记忆 | `recent.py` | 当前对话上下文，1700 行，临界区+admission generation+CAS |
| 事实记忆 | `facts.py` | LLM 提取原子事实，SHA-256+FTS5 去重 |
| 反思记忆 | `refine.py` | 余弦聚类+LLM 四动作（merge/split/discard/keep） |
| 人格记忆 | `persona/manager.py` | 7 mixin 组合，双锁设计（_alocks + _resolve_alocks） |
| 向量召回 | `embeddings.py` | ONNX 本地 CPU 推理，6 级 fallback gate，sticky disable |

**混合召回管道**：BM25 + 余弦并行 → RRF 融合(k=60) → LLM rerank
- 关键洞察：余弦分不清"主人喜欢猫"和"主人讨厌猫"（≈0.78），LLM 必须留作仲裁
- 向量只是预过滤，不是召回全部

### 2. Agent 执行架构（brain/）

- `agent_session.py`: 会话级 TTL（10 分钟空闲过期），独立于对话 agent
- `computer_use.py`: Kimi 风格 Thought+Action+Code 单步预测
  - VLM 接收截图 → 解析结构化输出 → `_ScaledPyAutoGUI` 坐标缩放（[0,999]→物理像素）→ exec 执行
- `task_executor.py`: 并行评估四通道（qwenpaw > openfang > browser_use > computer_use）
- 取消机制: `threading.Event` + 可中断 sleep + exec 沙箱注入

### 3. 会话管理（main_logic/core/）

- `manager.py`: mixin 模式聚合 11 个能力域（Turn/Lifecycle/Streaming/Focus/Proactive 等）
- `lifecycle.py`: session 启动/关闭/热切换，`_perform_final_swap_sequence` 原子切换
- `turn.py`（1712 行）: 对话轮次核心，处理文本/语音/TTS 管线/voice-echo 抑制
  - **产权门控**（`may_clear_shared_output`）：防止旧请求迟到回调污染新轮次
- `streaming.py`: 实时流输入缓存与 voice/text session 路由

### 4. 插件系统（plugin/）

- `core/host.py`: multiprocessing 子进程隔离 + ZeroMQ 传输
- SDK + 装饰器 API + 生命周期钩子 + 商城 + Steam 工坊
- 战略上一等公民，但 coverage 门禁只对 study_companion 强制 80%

---

## 四、代码质量评估

### 铁锚评分：78/100（有条件通过）

| 等级 | 数量 | 代表问题 |
|------|------|----------|
| HIGH | 2 | CUA exec 安全边界、日志泄露 |
| MEDIUM | 4 | 音频对齐、空实现、日志规范、import 位置 |
| LOW | 5 | 硬编码 TTL、f-string 混用、调试 print、异常捕获、id 去重 |

### 7 大技术亮点

1. **mixin 拆分巨型类** — LLMSessionManager 11 个 mixin，规避单文件膨胀
2. **产权门控** — `may_clear_shared_output` + `active_request_id` 防竞态
3. **混合召回 RRF 融合** — BM25+cosine 并行，RRF(k=60) 融合，与生产系统对齐
4. **向量服务 6 级 fallback gate** — 从 onnxruntime 缺失到推理异常，每级有降级路径
5. **用户轮次指纹与 redact** — SHA-256 指纹，取消任务时幂等 redact
6. **坐标缩放代理** — [0,999] 与 [0,1] 归一化，failsafe 边缘内缩 4px，easeOutQuad tween
7. **deferred task 超时检测** — 防止绑定失败导致任务永远卡在 running

---

## 五、关键风险

### 架构风险

| ID | 风险 | 严重性 |
|----|------|--------|
| R1 | Persona 缓存污染，event_log 写入失败时 fact 静默丢失 | 中 |
| R2 | 双锁顺序未文档化，未来开发者可能引入死锁 | 中 |
| R3 | 插件 sys.path.insert(0) 污染宿主 import 路径 | 中 |
| R4 | CUA exec 沙箱暴露 os + __builtins__，模型生成代码可 RCE | **严重** |
| R5 | Agent 会话纯内存，重启丢失长任务 | 中 |
| R6 | cross_server bullet 通道用 pickle + 关 SSL 验证 | **严重** |

### 安全风险

| ID | 风险 | 影响 |
|----|------|------|
| S1 | CUA exec 等同无沙箱，prompt injection 经截图可触发 RCE | **必标** |
| S2 | 端口绑定需确认是否 0.0.0.0（Memory/Agent 无鉴权） | 高 |
| S3 | lanlan_name 直接拼进 URL 路径 | 低 |
| S4 | 插件工具 description 是间接 prompt injection 入口 | 中 |
| S5 | CUA 连通性探测失败日志可能泄露 api_key | 中 |

### 资源管理风险

| ID | 风险 | 影响 |
|----|------|------|
| M1 | WS slot maintainer 的 create_task fire-and-forget | 连接泄漏 |
| M2 | AgentSessionManager 单例无清理钩子 | 内存缓慢增长 |
| M3 | PersonaManager _alocks dict 永不收缩 | 角色名空间无限增长时泄漏 |
| M4 | CUA observations 列表在 max_steps 内无上限 | 并发 CUA 内存峰值高 |
| M5 | EmbeddingService ONNX session 关闭路径未见 | 热重载场景内存翻倍 |

---

## 六、与陆墨项目的对比

### 陆墨可借鉴的 5 个点（按优先级）

| 优先级 | 借鉴点 | 说明 |
|--------|--------|------|
| **P1** | 进程隔离的后端架构 | 陆墨 Electron 单进程，FastAPI 崩溃拖垮 UI。把 GRAG+Neo4j 重计算拆到独立进程 |
| **P2** | 分层记忆 + 降级 fallback gate | NEKO 五维分层每层独立可降级。陆墨缺"近期对话压缩层"和"反思层"，图谱挂了不能 crash |
| **P2** | sticky disable 模式 | NEKO 的 EmbeddingService 失败即永久关闭不重试。陆墨的 MCP 工具/图谱检索应照搬 |
| **P3** | 模型 tier 化 + 不传 temperature | LLM 调用收敛到 tier（摘要/纠错/抽取/视觉），未配置就报错。零成本立刻能做 |
| **P3** | Agent 与对话解耦 | Agent 会话独立 + TTL 过期。陆墨若做材料科研 Agent，别塞进对话循环 |

### 陆墨应避免的 3 个坑

1. **不要学 recent.py 的并发复杂度** — 1700 行堆临界区/admission/CAS/锚点。先用简单"压缩+硬上限"，等真有并发问题再加
2. **不要学 NEKO 的隐私政策留白** — privacy.md 只覆盖文档站 GA4，产品本身无政策。陆墨涉及科研数据/文献/可能涉密内容，必须产品级隐私政策
3. **不要学测试覆盖的战略性缺失** — coverage 门禁只对 study_companion 生效。主系统核心模块（记忆/Agent/图谱）必须有强制覆盖门禁

---

## 七、NEKO 技术债务清单

1. **recent.py 并发过度复杂** — 1700 行，维护成本高
2. **测试覆盖不均** — 只 study_companion 强制 80%，e2e 需手动启用
3. **产品级隐私政策缺失** — privacy.md 只覆盖文档站
4. **CPU 检测脆弱** — 为绕杀软误报放弃 py-cpuinfo，自建查表，新 CPU 需手动加
5. **多 provider 集成维护负担** — 14+ AI 服务商、多 TTS、B站/贴吧/Twitch
6. **settings.py 死代码** — LLM 提取路径已被取代，模块注释明说"无调用者"
7. **三服务 + ZMQ + 插件子进程运维复杂度** — 部署/调试/日志归因成本高
8. **Steam 工坊 UGC 合规风险** — 无 UGC 内容审核/年龄分级/版权政策

---

## 八、三方共识

### 最严重的三条问题

1. **CUA exec 沙箱形同虚设**（铁锚 HIGH-1 + 实验田维护者 R4/S1）— `__builtins__` + `os` 暴露 = 任意代码执行，prompt injection 经截图即可触发
2. **cross_server bullet 通道 pickle + 关 SSL**（实验田维护者 R6）— 跨进程反序列化 + MITM 叠加
3. **双锁顺序未文档化**（实验田维护者 R2）— 当前没死锁路径，但未来开发者极易踩雷

### 整体判断

**架构骨架扎实**：进程隔离、降级链、混合召回、事件桥线程模型都踩过坑，工程素养高于行业平均。

**薄弱处明确**：CUA 安全边界和插件隔离边界是两块明显短板。

**一句话总结**：NEKO 是把"AI 伴侣"当系统工程做的开源平台——用进程隔离换稳定性、用 tier 化换可维护性、用 sticky disable 换可用性；陆墨能学的是它的分层降级与进程隔离哲学，该警惕的是它为正确性堆出来的并发复杂度，以及测试与合规的战略性留白。

---

*报告由 Hermes 协调生成，铁锚/实验田维护者/杜赞三智能体并行审视。*
