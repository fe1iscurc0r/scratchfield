# 工单 249 完工报告 · agent 资产盘存与风险姿态（`mcpserver/agentic_inventory/`）

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `b33bcea2eb`（工单248 合并点）
> 工单来源：`TRAE_WORKORDER_PROMPT_AGENT_249.md`（`cron_to_workorder` 自动草稿 **28 行** → 工单244k 晋升）
> 上游：**[karmine05/agentic-detector](https://github.com/karmine05/agentic-detector)**（MIT，Go，**13★ / 5 fork**，自述 "Detection-only, Fleet-deployable"）
> 交付：**18 个新文件、0 个既有文件改动**

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增文件 | **18**（模块 15 + 测试 1 + 集成图 1 + 本报告 1） |
| 既有文件改动 | **0**（本单未改任何既有路径；交付脚本逐条断言"路径在 main 上不存在"） |
| 第三方依赖 | **0**（被 `ast` 白名单测试守着，不是自述） |
| 需要 osquery / 主机权限 | **不需要**（纯仓内静态扫描） |
| 测试 | **46 用例全绿** |
| `ruff` | **All checks passed**（模块 + 测试） |
| 真跑证据 | `sandbox/inv-20261016-repo-scan/` **7 份**（含受控篡改演示） |
| 实测产出 | **66 行** = 63 `mcp_agent` + 3 `instruction_file`；档位 11 catalog + 55 high；**对账缺口 0** |

## §1 · 工单 §4 的填实（草稿三项全空，由本单定义并在此记录）

| §4 项 | 本单结论 |
|---|---|
| **PoC 边界与验收标准** | **边界**：只做**仓内资产级**扫描（`mcpserver/**/agent-manifest.json` + 指令文件），**不做**主机级进程/端口/家目录扫描（上游那三列刻意不要，理由见 README §3.1）。**验收**：① 对本仓跑出可复算的表（行数 = `find mcpserver -name agent-manifest.json \| wc -l`）；② 对账缺口 0 且**每条缺口都可证伪**（真缺口必须报 / 不适用必须不报，两侧都测）；③ 快照能 diff 出「启动向量变化」；④ 46 用例全绿 + ruff 全绿。 |
| **与现有模块的耦合点** | 落点 `mcpserver/agentic_inventory/`（新）。与 `mcp_registry`/`mcp_manager` 是**被盘对象 vs 盘存器**的关系（以 bridge 形态接入同一条注册链）；与 244g 的 `tests/test_import_graph_and_adapter_contracts.py` 是**可反复跑的盘存 vs CI 闸门**的划界（详见 README §6、集成图 §6）。 |
| **是否与已发工单重复** | **不重复**（244j 代查 + 本单复核：根目录 **50** 个工单（编号 190~249）里，`agentic-detector` / `osquery` / `agentic_inventory` **仅 249 自身命中**；功能最接近的 244g 边界见上）。 |

## §2 · 设计决策

### 2.1 借的是方法论，不是代码
上游是 **Go 写的 osquery 扩展**（要 osquery、要 Fleet、扫主机）；本仓要的是**仓内 agent 资产可见性**。
所以只搬四条方法：**多信号置信度分级**（"Name matching alone never creates a row"）、**evidence 令牌**、
**静态风险姿态**、**sha256 + launch_hash 指纹**（可跨时间 diff）。代码零行复用。

### 2.2「只读不执行」怎么真做到
解析 `entryPoint` 指向的类**不 import 它** —— 而是 module 路径 → 候选 `.py` → `ast.parse` → 找类 → 找
`handle_handoff`。跨文件基类则标 `handoff_uncheckable`（**"判不出" ≠ "没有"**）。
这与上游 "never executes a discovered binary, and never connects to an MCP server" 是同一条纪律。

### 2.3 质量标记与风险标记**分开两列**
工程质量（`no_tests` / `no_readme` / `no_requirements` / `dispatcher_mismatch` / `no_handoff`）与安全风险
（6 个令牌）混在一列会让**两者都失去意义** —— 这是本模块对上游表结构的一处**有意偏离**。

### 2.4 它会扫到自己（自指性质）
`mcpserver/agentic_inventory/agent-manifest.json` 是它自己那张表里的一行，且是 8 个带风险标记的行之一。
实测确认：`band = catalog`、`confidence = 110`、风险 = `cleartext_endpoint,remote_fetch_exec,secret_var_name_in_docs`。
这不是缺陷，是个必须留意的性质：**判据一宽，第一个误报的就是它自己的文档**（§4.1 就是活例）。

## §3 · 实现

| 文件 | 行数 | 是什么 |
|---|---|---|
| `posture.py` | 292 | **判据真值源**：7 个信号权重（和 = 110）、5 个档位、阈值 30 不出行、6 个风险令牌 + 4 条正则 |
| `inventory.py` | 383 | 扫描（manifest / 指令文件）+ 对账 + 指纹 + 快照 + `diff_snapshots` |
| `server.py` | 267 | MCP bridge（**8 工具**）+ argparse CLI |
| `__init__.py` | 71 | 再导出 |
| `agent-manifest.json` | — | `tier=read-only`、`families=[instrument]`、`domains=[security]` |
| `README.md` | — | 方法论 + 三条边界 + **五个真教训** |
| `requirements.txt` | — | 零依赖声明（含"为什么不引 osquery"） |
| `sandbox/inv-20261016-repo-scan/` | — | 7 份 CLI 真跑输出 + 复算自检表 |
| `tests/test_agentic_inventory.py` | — | 46 用例（姿态 / 盘存 / 对账·diff / 契约 四层） |
| `docs/integration-graph/agentic_inventory.txt` | — | 依赖图（含自指说明） |

8 个工具：`inventory` `registry_gaps` `risk_report` `snapshot` `diff` `column_spec` `doctor` `list_tools`
—— manifest 的 `invocationCommands` 与 `_TOOLS` 两处**逐项一致**（有测试守着）。

## §4 · 验证

| 层 | 做法 | 结果 |
|---|---|---|
| 姿态 | 权重和/档位边界/阈值/7 个真实命令行样本（含 `-y` 标志、`pkg @1.2.3` 分开写、`@<ver>` 占位符、中文纯提及） | **全绿** |
| 盘存 | 在**真实仓**上跑；行形状 = `COLUMNS`；每行有 sha256/evidence；内容变→指纹变；坏 manifest 出行不崩 | **全绿** |
| 对账 | 真缺口必须报（缺 `handle_handoff` / 派发表不一致）+ **不适用必须不报**（无 `_TOOLS` 表） | **全绿** |
| 契约 | manifest ↔ 派发表 ↔ `handle_handoff`；快照键数 = 行数（**3 个 AGENTS.md 不许被合并**） | **全绿** |
| 令牌注册表 | **双向**：能产出 ⇒ 必须登记；登记了 ⇒ 必须能产出 | **全绿** |
| 零依赖 | `ast` 扫全部 `.py`，白名单外一律断言失败 | **全绿** |

**数字复算**（不靠抄写）：

```bash
find mcpserver -name agent-manifest.json | wc -l        # 63 = summary.by_type.mcp_agent
python -c "import json;d=json.load(open('mcpserver/agentic_inventory/sandbox/inv-20261016-repo-scan/inventory.json',encoding='utf-8'))['data'];print(d['summary'])"
```

⚠️ **一个"看起来对不上"的数已经解释掉**：指令文件行数本模块报 **3**，而朴素的
`find -name AGENTS.md`（深度 ≤3）会给 **4**。多的那个是 `vendor/polykin/AGENTS.md` ——
`vendor/` 在 `inventory._SKIP_DIRS` 里（外部同步的第三方代码，刻意不盘）。
复算命令已连 `_SKIP_DIRS` 一起写进证据目录 README，**两个数都对，差的那个是设计**。

证据的**幂等性**也测了：连跑两次生成的 7 份 JSON **逐字节相同**（sha256 全等）。

### 4.1 收尾期抓出的四个问题（都留证，不静默修掉）

| # | 现象 | 根因 | 处置 |
|---|---|---|---|
| 1 | 检测器把**自己的 README** 判成"未钉依赖" | 令牌表里那串 `` `npx`/`uvx`/`bunx`/`pnpx` `` 被当成依赖声明 | 收紧包规格识别；与测试表里同形状的 `` \| Node ≥ 20 + `npx` \| `` 判定一致（都**不判**）。证据目录 README 的「两次生成」一节留了对照表 |
| 2 | `diff` 接不上 `snapshot` 的输出 | `snapshot` 写出的是**整份输出**（含 `ok/tool/data`），`diff` 只收内层；且真实快照 24 KB，**Windows 命令行上限约 32 KB 放不下** | 加 `unwrap_snapshot()`（两种形状都收）+ CLI `@文件` 入参 + 2 个新测试；文档里那条一行命令现在真能跑 |
| 3 | `RISK_TOKENS` 有一个**永远不亮**的令牌 | `world_writable` 只登记、没实现 —— 报告里会多一个让人误以为"在监控"的令牌 | 删；并补**反向守卫**测试（注册表 == 可产出集合），杜绝"愿望式登记" |
| 4 | 文档里的实测数字**抄错了**（旧版写 65 行 / 62 mcp_agent / 另一组风险分布） | 手写数字与实测脱节 | 全部改为实测值 + 附**复算命令**；并核出"62"当时就已失真（09:44 之后无任何 manifest 被创建或改动，当时也应 63） |

### 4.2 一次事故与恢复（留证）

收尾时我对 `posture.py` 做的一次区间删除**误删了 4 个仍被引用的正则定义**
（`_SECRETISH` / `_CLEARTEXT` / `_INJECTION` / `_INVISIBLE`），后果：

- `tests/test_agentic_inventory.py` **15 failed / 6 errors**；`ruff` 6 errors；
- 重生成证据时 CLI 崩溃，shell 重定向把 `inventory/registry_gaps/risk_report/snapshot` **写成了 0 字节**。

**恢复方式**：补回定义 → 用**修复前就已落盘的 `risk_report.json` 当真值对拍**（它是崩溃前 09:44 的产物）。
对拍结果：8 行里 **7 行逐字节一致**，唯一差异是 §4.1 第 1 条那个假阳性 —— 这正是"真值对拍能定位问题、
而不是靠猜"的价值。随后 7 份证据全部重生成，并核过行尾（**CRLF = 0**，全 LF）。

> ⚠️ 顺带记一条作业纪律（本单实测，**可复现**）：`grep -c $'\r'` **不能当行尾判据**。
> 同一个写法在本机出现两种结果 —— 对一份纯 LF 探针文件返回 `0`（正确），
> 但对证据目录里的纯 LF 文件却返回**满行数**（`column_spec.json` → 60/60，实测该文件
> `raw.count(b"\r\n") == 0`），即**假阳性**。具体是哪种（参数被吞成空模式 / 还是别的原因）本单没查到根，
> 因此**不猜**：结论只保留可复现的那半句 —— **行尾只信逐字节统计**（`raw.count(b"\r\n")`）。
> 本单最终以字节统计为准（全部文件 `CRLF = 0`）。

## §5 · 未落地（刻意不做，或本单不做）

1. **主机级扫描**（`running` / `pid` / `port`）—— 不扫进程、不枚举家目录、不看监听端口（隐私与纪律）。
2. **不做修复** —— 只出表；改不改是人的事（照上游 detection-only）。
3. **不报密钥的**值** —— 只在**键位**取变量名，且只给名字（审计工具不能自己成为泄漏源）。
4. **不做持续监控** —— 本单只给"能扫 + 能 diff"的能力；要不要挂 cron 是运维决策，不在本单。
5. **不覆盖非 `mcpserver/` 下的 agent 形态** —— 扫描面刻意限定（`INSTRUCTION_NAMES` + `agent-manifest.json`）。

## §6 · 复现

```bash
PY=python                          # 任意 Python 3.11+，零第三方依赖
$PY -m mcpserver.agentic_inventory.server inventory --root .
$PY -m mcpserver.agentic_inventory.server gaps      --root .
$PY -m mcpserver.agentic_inventory.server risks     --root .
$PY -m mcpserver.agentic_inventory.server snapshot  --root . > snap.json
$PY -m mcpserver.agentic_inventory.server columns
$PY -m mcpserver.agentic_inventory.server doctor
$PY -m mcpserver.agentic_inventory.server diff @snap_old.json @snap_new.json   # rug-pull 检测
$PY -m pytest tests/test_agentic_inventory.py -q    # 46 passed
ruff check mcpserver/agentic_inventory/ tests/test_agentic_inventory.py
```

依赖图：`docs/integration-graph/agentic_inventory.txt`
证据目录：`mcpserver/agentic_inventory/sandbox/inv-20261016-repo-scan/`
