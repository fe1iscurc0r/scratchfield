# 工单 244g 报告 · 结构性审计（真环 / 适配完整性）+ 两项环境修复

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `b77cedac3f`
> 触发：「把你[觉得]能做掉的做掉；然后检查有没有**兼容不完善**、以及**没完全适配导致真环**的情况」
> 变更文件：**3 个，全新增** + 三处**环境修复**（不进仓）

---

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增文件 | **3**（1 测试 + 1 工具 + 本报告） |
| 新增守卫 | `tests/test_import_graph_and_adapter_contracts.py`（**4 用例**，纯 `ast`/`json`，**不 import 被测模块**） |
| 新增工具 | `tools/hf_cache_repair.py`（可复用、幂等） |
| `ruff` | 新文件 **All checks passed** |
| **真环结论** | 主干目录 **「全 eager」真环 = 0** ✅（唯一 1 个在 NEKO，按要求不碰） |
| **适配契约** | `adapters` 注册表 **9/9 过契约**；`mcpserver/**` 的 **73 个 manifest 全部可静态解析** ✅ |
| 环境修复 | ① 仓库 venv 装 `pymupdf` → 引擎链三级全通；② **修复 HF 缓存的两处 0 字节损坏 → docling 真跑通** |

---

## §1 · 真环审计：方法比结论更重要

### 1.1 判据

环 ≠ 故障。关键是**边是模块级（eager）还是函数体内（lazy）**：

- **「全 eager」真环** = SCC 里每条边都是模块级 import ⇒ 一导入就必然踩到**半初始化模块**，是真故障；
- **含 lazy 边的环** = 本仓刻意的解环手法（在函数体内 import）⇒ 可存活。

### 1.2 我自己踩的三个方法坑（都影响结论，值得记）

| # | 坑 | 后果 | 修法 |
|---|---|---|---|
| 1 | `__init__.py` 的相对导入基准包算成了**父包** | 包内相对导入全部解析失败 ⇒ 边大量缺失 ⇒ 只报出 9 个环（**少报**） | `__init__.py` 的当前包就是它自己 |
| 2 | `import pkg.sub` 必然先执行 `pkg/__init__` ⇒ 我把这条**隐式父包边**也算进去了 | 「eager 重导出子模块的 `__init__`」把整棵子树吸成一个 **143 节点的假 SCC**（**严重高报**） | 循环检测**只认显式 import**，不展开父包边 |
| 3 | 写守卫时为了「保险」把 base 和 cand **都**加进边 | 等于把坑 2 又引回来，**凭空冒出 3 个「全 eager 真环」**（`agent_governance` / `chem_adapter` / `ook`） | 每个名字**要么**落到子模块**要么**落到 base |

> 坑 3 是**写守卫时新犯的**，被守卫自己报出来 —— 说明「静态图判环」对建模方式极其敏感，
> **不能只信工具输出的数字**，必须逐条回溯到源码。

### 1.3 最终结论（主干范围：`mcpserver` / `apiserver` / `agentserver` / `system` / `tools`）

- **「全 eager」真环 = 0** ✅
- **「靠惰性边存活」的环 = 6**（基线，已写进守卫）：

| SCC | 节点 | lazy / eager 边 | 说明 |
|---|---|---|---|
| `apiserver.agentic_loop_parts` + `routes.*` | 28 | 12 / 54 | 最大 |
| `mcpserver.mcp_manager`·`mcp_registry`·`telemetry`·`system.{config,character_bundle,skill_manager}` | 6 | 6 / 5 | **241 的 hook 所在**（`mcp_manager.unified_call`） |
| `apiserver.event_bus` + `apiserver.telemetry` | 4 | 3 / 1 | |
| `agentserver.openclaw.{detector,embedded_runtime,installer}` | 3 | 4 / **0** | ⚠️ **纯惰性** |
| `apiserver.event_bus.{event_store,trace}` | 2 | 2 / **0** | ⚠️ 纯惰性 |
| `mcpserver.antenna_sim.{sim_exec,sim_runner}` | 2 | 2 / **0** | ⚠️ 纯惰性 |

**三条纯惰性环是最脆的**：谁把那个 import 提到模块级，立刻变真环。守卫会先红。

全仓（含 NEKO/vendor）唯一的「全 eager」真环是
`NEKO...services.theater.numeric_v2_runtime ↔ numeric_v2_store` —— **按要求不碰**。

---

## §2 · 兼容 / 适配完整性审计

| 检查 | 方法 | 结果 |
|---|---|---|
| `mcpserver/adapters` 注册表的 9 个适配器 | 真 import + `validate_adapter(mod, name)` + `healthcheck()` | **9/9 契约 OK** ✅（`llm4decompile`/`memclaw`/`vulnclaw` 的 `healthcheck=False` 是**预期**：分别缺模型缓存 / 缺依赖 / 缺 API key） |
| `mcpserver/**` 的 **73 个 `agent-manifest.json`** | 真 import `entryPoint.module` + `getattr(class)` + `hasattr(handle_handoff)` | **73/73 全部可解析** ✅ |
| **243 的薄兼容层** `mcpserver/esp32/rlnc` ↔ `mcpserver/rf_brain/rlnc` | 真 import 两边，比 `__all__` 与 **`is` 身份契约** | **完全镜像** ✅：真值源 28 名 / 镜像 30 名（超集）、**缺 0**、身份 28/28 `is` 相同 |
| `mcpserver/material_science/academic_bridge` | `PROJECTS` 里 `call=True` 的 vs `CALLERS` 已实现的 | **0 缺口** ✅（5/5 对齐；`bridge.py:160` 那句 `NotImplementedError` 是**当前不可达的防御分支**） |
| 全仓「死 manifest」（指向不存在模块） | 扫**全树**（不止 `mcpserver/`） | ⚠️ **1 个**：`mod/mcpserver/agent_llm_decompile/agent-manifest.json` → `mcpserver.agent_llm_decompile.*`（**该模块在活的 `mcpserver/` 里不存在**，活的是 `agent_decompile/`） |

### 2.1 那个死 manifest 的影响面（**低**，已实测）

注册器 `scan_and_register_mcp_agents(mcp_dir="mcpserver")` 是
`Path("mcpserver").glob("**/agent-manifest.json")` ⇒ **只扫 `mcpserver/` 下**，
`mod/` **不在扫描范围内** ⇒ **不会影响注册**。

`mod/` 是模块化过程的**快照目录**（内含 `mod/sources/tools/_fix_manifests.py`），
`mod/mcpserver/*` 里的 manifest 靠指向**活的** `mcpserver/*` 才解析得到。
⇒ **建议**：要么把 `mod/mcpserver/agent_llm_decompile/` 删掉、要么在 `mod/README` 标注它是过程快照。
**本单未动**（`mod/` 是别人的产物目录，删它属于策略决定）。

### 2.2 另一处观察（非缺陷）

`mcpserver/rf_brain/format_finder.py`（460 行）**全仓零引用**（含非 `.py` 文件），
其 docstring 自称「协议格式自动发现（**纯 Python 原型**）、参考 urh 设计思路独立实现」⇒
**未接线的原型**，不是坏了。`FormatFinder.find()` 的 `NotImplementedError` 是原型里的 ABC 占位。

---

## §3 · 「能做掉的」：两项环境修复

### 3.1 给仓库 venv 装 `pymupdf` ⇒ 引擎链三级全通

`pdf_text` 的三级引擎链在**真运行时**（`D:/my git/scratchpad/.venv`）的状态：

| 引擎 | 装前 | 装后 |
|---|---|---|
| `pypdf` | ✅ 6.19.0 | ✅ |
| **`pymupdf`** | ❌ | ✅ **1.28.2**（`pip install pymupdf`，dry-run 确认**只加 1 个包、无依赖变更**） |
| `adapter` | ✅（docling+markitdown） | ✅ |
| **`available_chain`** | `['pypdf','adapter']` | **`['pypdf','pymupdf','adapter']`（三级全通）** |

⇒ 现在真运行时也支持 `layout=true`（**行级 bbox** = 工单原话的「页码位置」）。

### 3.2 修复 HF 缓存的两处 0 字节损坏 ⇒ **docling 真跑通**

`pdf_text` 的 `engine="adapter"` 虽然一直 `ok=true`，但日志里始终有
`Docling 失败，尝试 MarkItDown 降级`。追下去发现是**两个模型各自坏了一个文件**：

| 模型 | 坏掉的文件 | 症状 |
|---|---|---|
| `docling-project/docling-layout-heron` | 快照里**全部 6 个文件都是 0 字节** | `Failed to load image processor …: Expecting value: line 1 column 1 (char 0)` |
| `docling-project/docling-models` | `model_artifacts/tableformer/{fast,accurate}/tm_config.json` | `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`（**连文件路径都不给**） |

**根因（与 winget 那个 ffmpeg 是同一类）**：本机未开开发者模式 ⇒ `os.symlink` 不可用 ⇒
HF 快照目录里留下的是 **0 字节普通文件**（不是符号链接、也不是副本）。
而 `blobs/` 里的数据**是完好的**（模型下载本身成功，只是快照没链接上）。

⚠️ **`HF_HUB_DISABLE_SYMLINKS` 这个环境变量在 `huggingface_hub` 1.4.1 里根本不存在**
（只有 `HF_HUB_DISABLE_SYMLINKS_WARNING`，仅不打印警告）⇒ 设了它**没用**（本单实测确认）。

⇒ 解法：向 Hub 取一次「文件名 → blob」映射，把 blob **复制**成快照真文件。**不重新下载**
（342 MB 的两个模型，重建 < 10 s）。已固化为 **`tools/hf_cache_repair.py`**（幂等、`--scan-all`）。

**验证（修复后真跑）**：

| 项 | 修复前 | 修复后 |
|---|---|---|
| `adapter_engine` | `markitdown`（降级） | **`docling`** |
| `adapter_fallback_reason` | `docling: JSONDecodeError…` | **`None`** |
| 耗时 | 46.2 / 63.0 s | **19.9 s** |
| 产出 | — | `ok=true`、`chars=74,819` |

> ⚠️ 一致提醒：**「装了 docling」≠「docling 能用」**——这次就是装了、能 import、
> `engines_status()['adapter']=True`，但**真跑才暴露**两个模型文件是空的。

---

## §4 · 新增守卫（把一次性审计变成长期护栏）

`tests/test_import_graph_and_adapter_contracts.py`，4 用例，**纯静态**（`ast`+`json`，
**不 import 任何被测模块** ⇒ CI 上缺重依赖也能跑）：

| 用例 | 守什么 |
|---|---|
| `test_no_all_eager_import_cycle_in_mainline` | 主干**不得**出现「全 eager 真环」（当前 0）。红了就**不要**去放宽 `SCAN_ROOTS`，而应把那条边改回函数体内 |
| `test_lazy_surviving_cycles_do_not_grow_unnoticed` | 「靠惰性边存活」的环**不得超过基线 6**（只允许减少） |
| `test_every_manifest_entrypoint_resolves_statically` | 每个 manifest 的 `entryPoint` 必须静态落到**真实文件 + 真实 class**（`validate_*` 的离线版） |
| `test_every_registered_adapter_declares_the_three_part_contract` | `_ADAPTERS` 里每个模块都要有 `CAPABILITY`/`healthcheck`/`register`（缺失时 `register_all_adapters` **只 warning 后 continue** ⇒ 静默失效，故必须盯） |

实测：**4 passed**（4.5 s）。

---

## §5 · 未落地 / 需接手

1. **`mod/mcpserver/agent_llm_decompile/` 的死 manifest**（§2.1）—— 影响面低、但确实是一处
   「指向不存在模块」的残留。清理它属于对 `mod/` 这个**过程快照目录**的策略决定，**未擅动**。
2. **`docling-models` 的 `README.md` blob 缺失**（下载时就没落地）—— 只是文档，**不影响加载**；
   `hf_cache_repair.py` 会如实列出（不静默）。需要它就跑一次
   `snapshot_download('docling-project/docling-models')`。
3. **三条「纯惰性」环**（§1.3 标 ⚠️）是结构性脆弱点 —— 已由守卫盯着，**未改代码**
   （解环要动 `agentserver/openclaw`、`apiserver/event_bus`、`mcpserver/antenna_sim` 的调用结构，
   属独立工作）。
4. **`format_finder.py`**（460 行未接线原型）—— 是否接线是产品决定，**未动**。
5. **换机提醒**：`pymupdf`、HF 模型缓存修复都是**机器级**改动，不进仓、不随版本走。

---

## §6 · 复现方式

```bash
# ① 真环审计（静态，不改任何东西）
python - <<'EOF'
import runpy; runpy.run_path("tests/test_import_graph_and_adapter_contracts.py", run_name="__main__")
EOF
python -m pytest tests/test_import_graph_and_adapter_contracts.py -q

# ② 兼容/适配审计（要能 import，故用装了全部依赖的解释器）
python -c "from mcpserver.adapters import _ADAPTERS, validate_adapter; ..."   # 逐适配器过 validate_adapter
python -c "import json,ast,pathlib; ..."                                     # 逐 manifest 静态解析

# ③ HF 缓存修复（幂等；先用 --dry-run 看要改什么）
python tools/hf_cache_repair.py --scan-all --dry-run
python tools/hf_cache_repair.py --scan-all
```
