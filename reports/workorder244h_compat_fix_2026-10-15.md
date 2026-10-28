# 工单 244h 报告 · 惰性导入动机核查 + 修掉 `mod/` 的死 manifest

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `3b3fca4c9cf4`
> 触发：「有一些惰性是因为节省开支的，直接全部启动消费太大，你看看是不是因为这个；
> 兼容可以修复了，自己做掉自己推上去」
> 变更：**删 3 个文件**（`mod/mcpserver/agent_llm_decompile/**`）+ **改 1 个守卫** + 本报告

---

## §0 · 一句话

① **假设成立**：惰性导入确实是为「省启动开销」而设 —— 且有**实测数字**
（MCP 注册冷启动 **4.40 s → 0.083 s，52.8×**；`litellm` 首次 import **8.9 s，占 apiserver 启动的 75%**）。
但省的是**冷启动时间与内存**，不是 API 计费。② 兼容残留（`mod/` 里指向不存在模块的死 manifest）
**已删**，同时把 manifest 守卫**放宽到全树**（此前因那个化石而只能扫 `mcpserver/**`）。

---

## §1 · 惰性导入的动机核查（逐处看代码现场，不猜）

244g 找到的 6 个「靠惰性边存活」的环，其惰性边**全部有明确动机**，分三类：

### 1.1 ✅ 冷启动开销（**用户的假设，实测证实**）

| 出处 | 证据 | 数字 |
|---|---|---|
| **`mcpserver/mcp_registry.py`**（241 的懒注册） | 自述：「冷表：启动时只登记 manifest 占位、**不实例化** agent 类（省掉 import 各种重依赖）」「冷启动省掉 50 个 agent 模块的 import」；且有**回退开关** `MCP_LAZY_REGISTRY=0` | **`tools/boot_profile_mcp.py` 实测**：懒加载 `total=0.0834 s`（instances=0）；旧行为 `total=4.4001 s`（instances=55）⇒ **52.8×** |
| **`apiserver/litellm_lazy.py`**（卷191-B2） | 自述：「`litellm` 首次 import 约 **8.9 秒**（占 apiserver 启动 11.8s 的 **75%**）」；且**刻意不定义模块级 `__getattr__`**（那会让 `from X import litellm` 在导入期就触发求值，懒加载失效——实测踩过） | 8.9 s / 11.8 s |

⇒ **用户的假设对**：直接全部启动确实「消费太大」。但省的是**冷启动时间**（有实测数字），
**不是 LLM API 计费** —— import 不会发起调用。

### 1.2 ✅ 按需加载（同属性能，不是钱）

`system/config.py`（1900+ 行）在**组装 prompt 的分支里**才 `import`
`character_bundle` / `skill_manager` / `mcp_registry.auto_register_mcp` / `mcp_manager.get_mcp_manager`
—— 不建 prompt、不需要 MCP 工具清单时就完全不拉起。代码现场：函数体内 + `if include_tool_instructions:` 等分支内。

### 1.3 ✅ 解循环（不是为了性能）

| 出处 | 证据 |
|---|---|
| `apiserver/routes/extensions_parts/market.py:75` | 注释原文：`# 延迟导入：openclaw 顶部引用本模块，运行时才解析` |
| `apiserver/event_bus/{event_store↔trace}`、`{bus↔surface↔telemetry}` | 单例惰性（`global _x` + 锁）+ 解循环 |
| `agentserver/openclaw/{detector,embedded_runtime,installer}` | 三模块互为前置（installer 起动后要 detector 验证；detector 要 runtime；runtime 要 installer） |
| `mcpserver/antenna_sim/{sim_exec↔sim_runner}` | 执行器与运行器互为前置 |

**结论**：① 对；② 这些惰性**全部是刻意设计且有证据**，不是随手写的
⇒ 244g 守卫的**基线 6 保持不变是对的** —— 它们**不该**被改成 eager，
守卫的作用正是「盯住别有人把惰性改成 eager」。

> ⚠️ 方法论注：我第一版扫描的关键词（`token`/`消费`/`加载`）产生了 **81 条误报**
> （把 `refresh_token`、`消费者`、`importlib` 都当成了动机）。
> **必须读代码现场 + 分类核对**，关键词扫描只能当线索。

---

## §2 · 兼容修复：删掉 `mod/` 里那个死 manifest

### 2.1 来历（查清了才动手）

| 事实 | 证据 |
|---|---|
| `mod/` 是**外部交付的化石快照** | `mod/sources/tools/_fix_manifests.py` 硬编码 `C:\Users\ASUS\Desktop\scratchpad\mcpserver` —— **该路径现在不存在** |
| 化石与活体是**两个不同的 agent**，不是改名 | 化石 `agent_llm_decompile.py`（375 行）= **LLM4Decompile**（HTTP/gRPC 调外部服务）；活体 `agent_decompile.py`（272 行）= **JADX APK/DEX** 反编译 |
| 外部产出物**自己就知道**类名对不上 | `mod/reports/verify/integration_test.py:77` 写着 `# MISMATCH`（`AgentLLMDecompile` vs `LLMDecompileAgent`） |
| 它**从未在活树存在过** | 活的 `mcpserver/` 只有 `agent_decompile/`，没有 `agent_llm_decompile/` |

### 2.2 影响面（已实测，为 0）

注册器是 `scan_and_register_mcp_agents(mcp_dir="mcpserver")` →
`Path("mcpserver").glob("**/agent-manifest.json")` ⇒ **只扫 `mcpserver/`**，
`mod/` **不在范围内** ⇒ 这个死 manifest **从未被注册、也从未报错**，是纯死残留。

### 2.3 处置

**删除** `mod/mcpserver/agent_llm_decompile/`（`__init__.py` / `agent_llm_decompile.py` / `agent-manifest.json`）。

> 为什么不是「补兼容层」：化石 agent 的能力（LLM4Decompile 走外部服务）与活体（JADX）**是不同的东西**，
> 而且它从未在活树存在 ⇒ 补兼容层等于为满足一个化石而新增死代码。
> 若将来要这个能力，应从 git 历史找回 `agent_llm_decompile.py` 单独评估（本单删除的是快照，历史仍在）。

### 2.4 顺带把守卫放宽（这才是「修好」的可验证形态）

244g 的 manifest 守卫**只能扫 `mcpserver/**`**（因为当时 `mod/` 有化石，全树扫会红）。
化石删掉后**放宽到全树**：

| 口径 | manifest 数 | 可解析 |
|---|---|---|
| 244g：只扫 `mcpserver/**` | 58 | ✅ |
| **244h：全树** | **72**（`mcpserver/**` 58 + `mod/mcpserver/**` 14） | ✅ **全部可解析** |

⇒ 以后再有「快照目录里躺着死 manifest」会在 CI 里**当场**暴露，而不是等人工审计。

---

## §3 · 验证

| 项 | 结果 |
|---|---|
| 守卫（放宽后） | **4 passed**（4.76 s）—— 含全树 72 个 manifest 静态解析 |
| 全树 manifest 计数 | **72**（删前 73） |
| `ruff` | All checks passed |
| 合并后 | `mod/mcpserver/agent_llm_decompile/` 三文件 **404**（PR changed_files 与预期一致，含删除） |
| 真环守卫不受影响 | 仍 0 个全 eager 真环；惰性环仍 6 |

---

## §4 · 未落地

1. **`mod/` 整体仍是化石快照**（`mod/sources/`、`mod/reports/` 还在，且引用不存在的机器路径）——
   是否清掉整个 `mod/` 属策略决定，本单只删了**确认坏**的那三件。
2. **`agent_llm_decompile`（LLM4Decompile）这个能力本身**要不要接回活树 —— 产品决定；
   需要时从 git 历史找回（本单删除的是快照，历史仍在）。
3. 三条「纯惰性」环维持原状（守卫盯着）。
