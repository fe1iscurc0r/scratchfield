# DeepSeek Harness (dsh) 解构分析报告

> 分析对象:gitee.com/fe1iscurc0r/deepseek-harness(fork 自 deepseek-ai/deepseek-harness,2026-08-14)
> 规模:TypeScript pnpm monorepo,~2320 个 TS 文件,50+ packages,2 个 apps,含 vendored Cordis fork
> 方法:4 路并行深度解构(核心运行时 / LLM与上下文 / 执行能力层 / 应用与外围)+ 官方架构文档交叉验证

---

## 0. 一句话定位

**dsh 是 DeepSeek 开源的 agent 运行时(harness)**,核心赌注是:

> **把一切模型可见物落到一条可校验、可重放、可分叉的 append-only 事件日志上,再用 Cordis 的插件机制把所有策略面开放为可逆注册。**

"Everything is a plugin" 不是口号——**模型适配器、工具注册表、会话日志、agent loop 本身都是插件**,没有特权核心。`npx @deepseek-ai/dsh web` 即可启动 Web UI(127.0.0.1:3080)。

---

## 1. 顶层架构:Cordis 插件树 + 分层组装

```
启动时:dsh --profile web
   │
   ▼
空 entry list
 + bundle 层(dsh-base → dsh-web-app,按序)
 + profile 层 cordis.patch.yml(用户)
 + home 层 cordis.patch.yml(覆盖所有 profile)
 + --patch CLI overlay
   │
   ▼  同一种 PatchOptions、同一次 applyEntryPatches
Cordis Loader 挂载成插件树(每行一个 fiber)
   │
   ▼
ctx 上出现服务:ctx.sessions / ctx.agents / ctx.llm / ctx.tools / ...
```

**关键机制**:
- **Service 子类 + `super(ctx, 'key')`**:服务即插件类,构造时占位 `ctx.<key>`;`static inject` 声明加载序
- **声明合并(declaration merging)**:每个包向 `Context` 合并服务键、向 `Events` 合并类型化事件——**插件加变体不需改核心文件**
- **effect 可逆**:一切注册返回精确 disposer,插件卸载时反向回滚;`enter → announce` 两段式发布保证观察者永远看不到半成品
- **vendored Cordis fork**:`vendor/` 下整个框架的定制版(Loader 树写回、internal 契约),升级不是换版本号的事
- **web 与 headless 的差异完全是两个 bundle 的 `cordis.patch.yml`**,不写一行 if-else

---

## 2. 核心运行时(packages/core/)

### 2.1 Session — 事件溯源日志(全架构的基石)

- **append-only `SessionEvent` 日志**,seq 连续、全程深冻结、lossless-JSON
- **双层模型**:原始日志(含 `assistant/chunk` 级重放保真)+ **surface 视图**(模型可见历史,由 `surfaceOp: append/replace` 标记维护)
- `deriveMessages()` 从 surface 增量投影模型历史;**compaction 只改视图不改历史**
- **"Model-visible means logged" 三重强制**:
  1. 编译期:`append` 的条件类型让消息事件必须带 surfaceOp
  2. append 边界:`SurfaceManager.validateNext` 预验证(replace 必须完整覆盖、tool result 只能改 content)
  3. dispatch 对账:invariant 插件在 `llm/stream` 上把将发出的 messages 与 `deriveMessages()` 做 JSON 级比对
- `ignorable?: true` 标记:reader 遇到不认识且未标记的事件**必须拒绝重建**——遗忘标记的代价是过度拒绝(安全方向),而不是静默恢复残缺会话

### 2.2 Agent + Agent-loop — turn/step 状态机

- `ctx.agents` = live 注册表 + AsyncLocalStorage 因果归因(initiator)
- **Inbox 是 durable 的**:每次变更先落 `agent/inbox/spliced` 事件再改内存——崩溃后"取消丢弃了哪些工作"仍可审计
- `ReactLoopAgent`:`idle / maintenance / running` 三相状态机
- **生命周期事务**:`prepare → setup → publish` 可回滚;`dispose()` 严格按序(cancel → whenIdle → scope.dispose → detach),三个 abort 源在资源存在之前就融合注册好
- **取消语义极其彻底**:双 ABORTED 代码区分 body 是否启动;已启动的 promise 必排干;崩溃后由持久化后端补 `turn/end{interrupted}`——**取消后的日志永远合法可重放**

### 2.3 Tools — scoped 注册表 + 守卫执行管道

```
tool/call → tools/pre-execute(allow/deny/ask)
  → ask → ctx.approval(可选 seam,无则降级 deny)
  → monotonic guards(只能拒绝不能放行,顺序无关)
  → tools/execute(around 包装,但 caller signal 强制融合回来)
  → 工具本体(fs/* 事件门在其内部)
  → tools/post-execute(accept/block/replace)
  → finalize → tool/result(深冻结后通知)
```

- **派发可重叠、提交保持模型顺序**:`isConcurrencySafe` 进有界滚动池,exclusive 构成屏障
- **策略即事件监听器**:摘除任何策略插件,核心照常工作,只是退化到裸行为

### 2.4 Scope — 作用域原语(最优雅的设计之一)

- 一条父链两个方向:**注册可见性向下继承,事件准入向上冒泡**
- scope key 就是 agent 对象本身;`ScopedLayers` 基座被 tools/prompt/事件路由共同复用
- 与业务零耦合:只有 key/parent/filter 三个概念

### 2.5 System-prompt — 分层注册表

- section/context/tools/variable 四类贡献;`order` 约定(-100=身份,0=persona,100+=工具指引)
- `complete: true` 的 section 使整段提示词只剩它(persona 完整替换)
- 动态上下文(时间/tmux/AGENTS.md)落成 **durable user-role 快照**——也是 logged 的

---

## 3. LLM 与上下文工程

### LLM seam(packages/llm/)

```ts
abstract class LlmAdapter {
  abstract stream(options: GenerateOptions): AsyncIterable<StreamChunk>
}
```

- `StreamChunk` 封闭联合(block-start/text-delta/tool-call-delta/block-end/usage/finish),`block-end` 直接携带组装好的 ContentBlock——**重组不是每个适配器各自的问题**
- 适配器 throw 归一化为带内 `finish{kind:'error'}`——**消费方只见流不见异常**
- 连接事实**每请求解析**(非 load 时冻结)——key 轮换下一请求即生效
- 新 provider = 一个插件调 `ctx.llm.registerAdapter()`

### 上下文预算的分层防线

```
token-meter(测量)
  → compaction(0.8×contextWindow 阈值触发,摘要替换 surface)
  → tool-result-pruner(无摘要先行削减)
  → spill-policy(超大工具结果移出上下文,换 preview+定位符)
  → BlockAssembler(max-tokens 截断保护)
```

每层职责单一、可独立拆卸。**compaction 崩溃表现为可检测的遗留锁而非假完成**;spill 失败保留原文(绝不允许把成功调用变成错误)。

### Subagent

- 与 LLM 适配器同构的 provider 注册表:spawn(全新)/ fork(带父历史种子)/ acp / codex / claude-code / dsh-sdk
- **toolFilter 是 scoped `tools.restrict()`——可见性即权限**
- fork 种子 = 父日志到最后一个 `turn/end` 的平衡轮次前缀
- 子 agent 失败 resolve(stopReason:'error')不 reject;通信只走 inbox 这一个 FIFO

### skill / plan / goal / todo / workflow

- **skill**:多来源 SKILL.md 分层注册表(rank: project > user > bundled),模型经 `skill` 工具按需加载
- **plan-mode**:纯日志 fold 的软指引状态,`agent/pre-step` 挂接
- **goal**:事件溯源的同会话目标,CAS 语义 `GoalRef{id, revision}`,`goal-round-driver` 复用 inbox 自驱多轮
- **todo**:从会话日志 fold 出的投影,不是独立存储
- **workflow**:模型写 JS 编排脚本,worker_threads + vm 隔离执行;`tool-ralph` 是纯靠组合现有 seam 实现的 Ralph 循环(活例)

---

## 4. 执行与能力层 — "执行世界"抽象

> 核心论点:**fs 与 subprocess 共享同一坐标系,整体替换这两个 provider 即可把 Bash/PTY/LSP 迁到远程**。E2B POC 实证了这一点——bash-local/terminal-bash/lsp-stdio 无需任何 E2B 分支就在远程沙盒执行。

### 能力 seam 三件套(贯穿全库的模式)

**Service Definition(接口)+ Service Provider(实现,每 context 一个,重复即炸)+ Consumer(通常是模型工具)**

| seam | 关键设计 |
|------|---------|
| `ctx.subprocess` | spawn spec **零默认值**("explicit > implicit");offset-reader 非消耗式读取;terminate 树级 SIGTERM→grace→SIGKILL |
| `ctx.sandbox` | argv 包裹式(bwrap/Landlock/Seatbelt/windows-acl 链);**fail-closed 是接口契约**("silent unconfined passthrough is never legal");denial vs runner-failure 用 stderr 方言分类器区分 |
| `ctx.shell` | request/spec 分离(resolve 才补默认值);`timedOut`/`aborted`/`signal`/`exitCode` **正交独立上报** |
| `ctx.terminals` | 持久 PTY:owner 精确到 Agent;`TerminalWaitReason` 与 shell 存活状态刻意正交 |
| `ctx.fs` | 不透明 `FsTarget` 身份;`editText` 是 provider 级原子变异(版本校验+匹配+替换同一临界区);**策略走事件门**(`fs/write-intent` waterfall)而非服务 |
| `ctx.credentials` | 配置只携带引用(env 名),消费者每次操作现解析;空值处处视为 absent;被只读层遮蔽的引用拒绝写入(`writable:false`) |

### MCP / LSP / code-runtime

- **MCP 只做 client**:`mcp__<server>__<tool>` 桥进 `ctx.tools`;`list_changed` 整代替换(绝不留半套);Resources/Prompts 明确 deferred
- **LSP 恰好四个操作**(定义/引用/实现/hover),封闭联合,无协议逃生舱口
- **code-runtime**:模型写的程序在 host bindings 上跑;失败分类六选一;`isolation` 描述符明确标注"是诊断标签,**不是安全声明**"

### Hooks(Claude Code / Codex 兼容)

- `PreToolUse → tools/pre-execute`、`PostToolUse → tools/post-execute`、`Stop → agent/turn-stopping` 等拦截点映射
- hook 命令经 `ctx.shell` 执行——自动继承凭证净化、超时、进程组杀
- 方言桥是事件监听器,核心 spine 不依赖它们

---

## 5. 应用层

### 双形态 = 两棵 Cordis 树

- **CLI 是极简 profile 启动器**(bin.ts 53 行);第一个不认识的参数之后的全部透传给被启动的树
- **Web = 同进程双面架构**:node 半(webserver/apiproxy/gateway)+ 浏览器半(**第二棵 Cordis 树**,懒 CJS 模块表,执行只注册 factory、物化才跑副作用)
- 每次启动重写空根 `cordis.yml`——防 Loader tree write-back 污染组合基线

### 前端聊天节点机制(亮点)

`ConversationNodeDefinition`:`match/start/update` 事件驱动状态机 + keyed 渲染槽。第三方加一种聊天行 = ① 声明合并类型图 ② 注册 Definition ③ 注册渲染器——**不改中央代码**。"Everything is a plugin" 贯彻到了前端渲染层。

### 三套对外协议

| 协议 | 受众 | 特点 |
|------|------|------|
| `/api` RPC + WS downlink | 自家浏览器前端 | Host 头信任栅栏(防 DNS rebinding);特权方法钉死 loopback |
| SDK(ndjson JSON-RPC over stdio) | TS/Python 子进程 | EOF→SIGTERM→SIGKILL 退出阶梯 |
| ACP(Agent Client Protocol) | Zed 类编辑器 | **automation-only**:只推 committed 文本;权限只有一次性 allow/reject,绝不推断持久授权 |

### 持久化三分离

会话日志(每会话 append-only JSONL,zstd 压缩)/ storage+settings(backend+命名空间,YAML 热提交)/ session-query(派生 SQLite FTS5,与主库分离)。

### 插件生态

第三方插件 = 声明了 `dsh.bundle.patch` 的 npm 包;`dsh plugin add` 是 pnpm 薄转发器,按已安装状态对账;还有一套 **`tool-cordis` 让模型给自己写插件**(node:vm 沙箱,明确"不是安全边界,视同 bash 权限")。

---

## 6. 设计精华 TOP 8(最值得借鉴)

1. **事件溯源 + surface 双层日志**——一份日志服务模型历史/人类 transcript/重放/遥测四种消费者,合法性在 append 边界原子验证
2. **不变量即伴生插件**——架构约束从文档变成可执行检查(`internal/dispatch`、`llm/stream` 对账),生产可卸载
3. **两段式发布(enter/announce)**——观察者永远看不到半成品世界,listener throw 可否决发布并精确回滚
4. **策略走事件门,不走服务**——摘除策略包即退化到裸行为,核心 spine 零依赖
5. **Scope 双向原语**——注册向下继承、事件向上冒泡,一条父链两个方向的对称美
6. **capability seam 三件套 + 每 context 单实现**——整体换执行世界(E2B)成为纯组合层操作
7. **失败纪律分层**——适配器 throw→带内 finish;子任务失败→resolve stopReason;审批无人应答→unavailable→拒绝;**fail-closed 贯穿**
8. **正交事实上报**——timedOut/aborted/signal/exitCode 互不编码;denial/runner-failure/命令失败三路分开——消灭双源真相

## 7. 复杂度与坑(诚实记录)

- **Cordis 心智负担重**:waterfall/emit/serial、fiber/effect、isolate realm——新贡献者上手曲线陡
- **生命周期排序是化石层**:大量注释解释"为什么不能更简单",都是修过的真实 bug
- **vendored Cordis fork**:升级需手动同步,是隐藏的大依赖
- **patch 代数脆弱**:一个 patch 替换目标行整个 config,`dsh --dump-config` 是必备调试手段
- **类型表达不了的时序约束**(usage 先于 finish 等)靠协议级测试兜底
- **Web 面明文承认无认证层**,`--host 0.0.0.0` 刻意不支持

---

## 8. 对陆墨(scratchpad)的借鉴价值

| dsh 的做法 | 可解决陆墨的什么问题 |
|-----------|---------------------|
| 策略走 waterfall 事件门(tools/pre-execute 可 deny) | 陆墨 `_execute_local_tool` 裸 shell 问题——加一个 pre-execute 确认门监听器即可,不用改工具本体 |
| 审批 seam 封闭结果集(allowed-once/rejected/unavailable→拒) | 陆墨高危 action(set_model 改 base_url)需要用户显式确认 |
| scope 原语:per-agent 工具可见性 | 陆墨多角色/多会话的工具集隔离 |
| capability seam:fs/subprocess 抽象 | 陆墨 agentserver 的 0.0.0.0 问题——seam 化后本地/远程是 provider 选择 |
| "model-visible means logged" 不变量 | 陆墨 GRAG 记忆与上下文一致性 |
| compaction 分层预算(token-meter→prune→spill) | 陆墨长会话上下文管理 |
| invariant 伴生插件 | 陆墨"修复没接线"类问题(如 security_utils 死代码)——运行时断言能兜住 |
| profile/bundle/patch 组合代数 | 陆墨的 NEKO 融合配置管理 |

**最推荐先借鉴的**:tools 管道的 pre-execute/guard/post-execute 三段拦截 + 审批 seam——以最小改动堵住陆墨当前最大的安全缺口(LLM 驱动裸执行)。
