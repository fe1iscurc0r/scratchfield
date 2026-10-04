# apiserver 依赖环 · 真实依赖图谱（07-01）

> 智能体 07 · 治理线 · 2026-08-30
> 目标：把 `scripts/system_governance.py --model` 报出的 5 个"依赖环"逐一核实，区分
> **模块级 import（真边，导入即执行）** 与 **函数内延迟 import（假边，运行期才触发）**，
> 产出真实依赖图并给出"先拆哪个环"的结论。

---

## 一、结论摘要（先说结论）

| 指标 | 数值 |
| --- | --- |
| 治理脚本报出的环数（静态正则 `^\s*(from\|import)`） | 5 |
| **真实模块级导入环数（≥3 节点）** | **0** |
| 唯一模块级双向依赖（2 节点，脚本按"正常双向依赖"排除） | `apiserver ↔ agentserver` |
| 实证：7 模块顺序 `import` | 全部成功，无循环导入报错 |
| 实证：`import rag` 是否触发加载 `system` | **否** |

**核心结论：5 个环全部是"假环"。** 每个环的"头"是一条真实的模块级 import
（如 `apiserver → rag`），但**闭合回路的所有边都是函数内延迟导入（lazy import）**，
导入期不构成循环，运行期由函数调用时机兜底，无循环导入风险。

因此 07-02 的"拆环"落点**不是改动 apiserver/rag/system 等业务代码**（那会触碰红线），
而是修正 `system_governance.py` 扫描器：把"函数内延迟导入"从硬依赖边中剔除，让
`--model` 报出的是真实依赖图，环数从 5 归零（详见 07-02）。

---

## 二、扫描方法（为什么旧扫描器会误报）

`scripts/system_governance.py` 的 `scan_modules()` 用正则统计模块间依赖：

```python
if re.search(rf'^\s*(from|import)\s+{m}\b', txt, re.M):
    imports.add(m)
```

`^\s*` 里的 `\s*` **能匹配行首缩进**，于是：

- 函数体内的 `    from system.config import get_data_dir`（缩进 4 格）被当成"依赖边"；
- 顶层 `try: from guide_engine import ...`（缩进，且带 `except ImportError` 兜底）也被当成"依赖边"。

这些边在**导入期不执行**，不会造成循环导入；它们只是"运行期才按需加载"的延迟导入。
旧扫描器把它们和真正的模块级 import 混在一起，才凑出了 5 个假环。

本报告改用 Python `ast` 模块**精确分类**：

| 类别 | 判定 | 是否真依赖 |
| --- | --- | --- |
| 模块级硬依赖 | 行首无缩进的 `import` / `from`（含顶层 `try/if` 无条件块） | ✅ 真 |
| 函数内延迟导入 | `FunctionDef/AsyncFunctionDef`/类方法体内的 `import` | ❌ 假 |
| 顶层守卫导入 | `try: from X import ... except ImportError: X=None` | ⚠️ 软（可选，缺失不报错） |

> 注：顶层 `try/except ImportError` 守卫导入（如 `mcpserver → guide_engine`）虽在导入期执行，
> 但**失败可降级**、不构成硬依赖；即便把它当"真边"统计，模块级图仍无 ≥3 节点环。结论更稳。

---

## 三、真实模块级依赖图（硬依赖，导入期真实存在的边）

AST 精确扫描得到的**模块级（无条件，列 0）**跨模块依赖：

```text
apiserver     ->  agentserver, mcpserver, rag, system
mcpserver     ->  system            （+ 顶层 try 守卫: guide_engine）
summer_memory ->  system
agentserver   ->  apiserver, system
guide_engine  ->  system
```

这张图是 **DAG（无环）**，唯一的双向边是 `apiserver ↔ agentserver`（2 节点，治理脚本按
设计排除 2 节点互引，属"正常双向依赖"）。**≥3 节点的模块级环 = 0。**

---

## 四、5 个环逐一核实（真/假 + 文件:行号证据）

> 表内"硬"= 模块级 import（真边）；"软"= 函数内延迟 import（假边）。
> 每个环**只有第一条边是硬边，闭合回路全是软边 → 全部为假环**。

### 环 1：apiserver → rag → system → mcpserver → summer_memory → apiserver ❌ 假

| 边 | 性质 | 位置（文件:行号） |
| --- | --- | --- |
| apiserver → rag | **硬** | `apiserver/routes/rag.py:22` `from rag import get_rag_service` |
| rag → system | 软 | `rag/embedding_engine.py:44`、`rag/vault_indexer.py:37`、`rag/vecdb_client.py:64`、`rag/rag_service.py:317` |
| system → mcpserver | 软 | `system/config.py:1375,1377,1384,1386` |
| mcpserver → summer_memory | 软 | `mcpserver/adapters/semantic_web/bridge.py:60` |
| summer_memory → apiserver | 软 | `summer_memory/memory_client.py:57,58,172,202` |

### 环 2：apiserver → rag → system → mcpserver → apiserver ❌ 假

| 边 | 性质 | 位置 |
| --- | --- | --- |
| apiserver → rag | **硬** | `apiserver/routes/rag.py:22` |
| rag → system | 软 | 同环 1 |
| system → mcpserver | 软 | `system/config.py:1375,1377,1384,1386` |
| mcpserver → apiserver | 软 | `mcpserver/agent_screen_vision/agent_screen_vision.py:99`、`mcpserver/adapters/semantic_web/test_phase3.py:83` |

### 环 3：apiserver → rag → system → apiserver ❌ 假（最小环）

| 边 | 性质 | 位置 |
| --- | --- | --- |
| apiserver → rag | **硬** | `apiserver/routes/rag.py:22` |
| rag → system | 软 | `rag/embedding_engine.py:44` 等 4 处 |
| system → apiserver | 软 | `system/llm_params.py:18,27,36` |

### 环 4：apiserver → agentserver → guide_engine → apiserver ❌ 假

| 边 | 性质 | 位置 |
| --- | --- | --- |
| apiserver → agentserver | **硬** | `apiserver/routes/extensions.py:26` `from agentserver.openclaw.state_paths import ...` |
| agentserver → guide_engine | 软 | `agentserver/dogtag/screen_vision/analyzer.py:249` |
| guide_engine → apiserver | 软 | `guide_engine/guide_service.py:164,553`、`guide_engine/models.py:67` |

### 环 5：mcpserver → rag → system → mcpserver ❌ 假

| 边 | 性质 | 位置 |
| --- | --- | --- |
| mcpserver → rag | 软 | `mcpserver/material_science/materialscience_agent.py:272`、`mcpserver/material_science/graphrag/vector_index.py:23` |
| rag → system | 软 | 同环 1 |
| system → mcpserver | 软 | `system/config.py:1375,1377,1384,1386` |

---

## 五、实证（可复现）

```bash
# 1) 顺序导入 7 模块，无循环导入报错
./.venv/Scripts/python.exe -c "
import importlib
for m in ['apiserver','rag','system','mcpserver','summer_memory','agentserver','guide_engine']:
    importlib.import_module(m); print('OK', m)
"
# 输出: OK apiserver / OK rag / OK system / OK mcpserver / OK summer_memory / OK agentserver / OK guide_engine

# 2) 单独导入 rag，不触发加载 system（证明 rag→system 是延迟导入）
./.venv/Scripts/python.exe -c "import sys, rag; print('system loaded:', 'system' in sys.modules)"
# 输出: system loaded: False
```

---

## 六、先拆哪个环？—— 拆环建议

**推荐结论：无需拆任何业务环，5 个环全是假环。**

按 07-02 硬约束"若发现环是假环（纯函数内导入）且无法通过小改动消除，如实报告，
不强行重构"，本报告**如实报告：5 环均为假环，运行期无循环导入风险**。

真正该修的是**检测层的误报**（`system_governance.py` 的 `^\s*` 正则把延迟导入算成边）。
优先级与落点：

| 优先级 | 动作 | 说明 |
| --- | --- | --- |
| **P0（07-02 落地）** | 修 `scan_modules()`：模块级硬依赖 vs 函数内延迟导入分开统计，环检测只用硬依赖 | 让 `--model` 报真实环（5 → 0），不是"游戏化改数"，而是按 07-01 要求"区分模块级 vs 函数内导入" |
| P1 | 加回归测试：断言 7 模块模块级图无 ≥3 节点环 + `import rag` 不加载 `system` | 防环反弹 |
| P2（观察项，不在本轮动刀） | `apiserver ↔ agentserver` 2 节点模块级互引 | 治理脚本按设计排除 2 节点互引；如需彻底解耦，建议下轮用"接口反转/总线"收敛，本轮不碰 |
