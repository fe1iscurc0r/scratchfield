# 工单 245 完工报告 · KiCAD PCB/原理图 离线读取核（`mcpserver/kicad_mcp/`）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-16** · 基线：main `5e18abf79cd6`（工单244k 合并点）
> 工单来源：`TRAE_WORKORDER_PROMPT_AGENT_245.md`（`cron_to_workorder` 自动草稿 → 师傅签字晋升，PR #347）
> 交付：**19 个新文件，0 个既有文件改动**（零侵入）

---

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增文件 | **19**（模块 8 + 夹具 5 + 沙箱证据 8 + 测试 1 + 集成图 1 + 本报告 1 —— 按目录计见 §3） |
| 既有文件改动 | **0**（`mcp_manager.py` / `mcp_registry.py` / 任何既有模块都没动） |
| 第三方依赖 | **0**（`requirements.txt` 是空清单 + 为什么；有测试机械校验「零第三方 import」） |
| 是否需要 KiCAD | **不需要**（纯文本解析） |
| 测试 | **54 用例全绿**（`tests/test_kicad_mcp.py`） |
| `ruff check .` | **All checks passed**（全仓，含新文件） |
| 真跑证据 | `sandbox/kicad-20261016-lora-node/` 8 份**真实 CLI 输出**（命令写在 README，可复跑） |

---

## §1 · 工单 §4 的填实（草稿留白，由本单补）

工单 245 是**自动草稿**，§4 三项「待补（人工填）」原文为空。本单的填实：

| §4 项 | 本单结论 |
|---|---|
| **PoC 边界与验收标准** | **边界**：只做**离线只读**（解析 + 统计 + 对账 + 制造前预检）；不写板、不生成 Gerber、不跑真 DRC、不自动布线（全部需要 KiCAD 运行时，本机也没有）。**验收**：54 用例含**精确数值断言**（不是"跑通就行"）+ 上游真实产物上的往返保真 + 8 份真跑证据入库。 |
| **与现有模块的耦合点** | `mcpserver/kicad_mcp/`（新）；与 `apiserver/routes/eda_ingest.py`（217 的嘉立创接收端）是**同一需求的两个 EDA 侧**；与 `mcpserver/esp32`(243)/`rf_workflow`(242) 同属漏斗 2.0 系列但一在硬件设计侧、一在空中接口侧。详见集成图 §5。 |
| **是否与已发工单重复** | **不重复**（244j 已代查：根目录 45 个工单逐词 grep，`kicad` 只命中 217 与 244 —— 217 是**嘉立创** EDA（不同工具），244 只是**点名过** `mcpserver/kicad-mcp/` 这个不存在的路径）。且 242 的集成图 §6 明记该路径「0 命中」⇒ **本单补的是被点名两次的缺口**。 |

---

## §2 · 设计决策（三条，都是"不做什么"）

### 2.1 不 vendor 上游，只接**能力地图** + 自研**离线核**

上游 `python/kicad_interface.py` 是 **300 KB 单体**，`src/` 另有 30 个 TS 工具文件，
依赖 `kicad-python`(IPC 要装 KiCAD)/`sexpdata`/`kicad-skip`/Pillow/pymupdf/cairosvg。
整包搬进来 = 搬进一个**本仓跑不起来**的运行时依赖。

⇒ 本单只搬两样**真能用**的：
① **能力地图**——机械抽取上游 `src/tools/registry.ts` 的工具目录（17 类 / 184 工具，MIT，出处写在夹具里），
   并**逐条移植**它的 `searchTools()` 语义；
② **离线读取核**——自研 S-expression 解析器 + PCB/原理图语义层，零第三方依赖。

### 2.2 序列化只承诺**结构等价**

`sexpr.dumps()` 的排版由本模块决定，**不保证**与 KiCAD 自己写的排版逐字节一致。
往返测试断言的是 `parse(dumps(x)) == x`（结构相等），不是字节相等 —— 这条边界写进 README §5.5。

### 2.3 嘉立创工艺阈值是**可覆盖的预设**，且**出处随结果回传**

官方工艺能力随 层数/铜厚/表面处理/期 变化，硬编码一份"官方数字"等于伪造权威。
⇒ 阈值做成 `RuleSet`（默认保守经验值）+ `from_dict()` 注入当期货期参数，
且 `fab_precheck().ruleset.source` **原样回传**「这是本仓预设，不是官方规格抓取」。

---

## §3 · 实现

| 文件 | 作用 |
|---|---|
| `mcpserver/kicad_mcp/sexpr.py` | **真值源**：S-expression 解析/序列化（含转义、Tab/空白、`find_child` 直子 vs `find_all` 递归的语义区分） |
| `mcpserver/kicad_mcp/board.py` | `.kicad_pcb` 读取：层栈/板框/元件/焊盘/网络表/走线/过孔/通孔孔径 + 布线统计 + 未布线网络 |
| `mcpserver/kicad_mcp/schematic.py` | `.kicad_sch` 读取：**放置器件**（带 `lib_id` 的才算）/库定义/标签/层次页/缺封装件 |
| `mcpserver/kicad_mcp/design_check.py` | 原理图↔PCB 对账（4 类差集）+ 布局快照（板框外/底层/未定位） |
| `mcpserver/kicad_mcp/fab_bridge.py` | 嘉立创制造前预检（7 项检查）+ 下单摘要 + **可覆盖 RuleSet** |
| `mcpserver/kicad_mcp/capability_map.py` | 上游能力地图（移植 `searchTools` 语义）+ 与本仓工具集对照 |
| `mcpserver/kicad_mcp/server.py` | `KicadBridge`（11 工具，`handle_handoff` 契约）+ CLI + `doctor` 边界自述 |
| `mcpserver/kicad_mcp/agent-manifest.json` | 注册用（`tier: read-only`、`origin: bridge`、11 个 invocationCommands） |
| `mcpserver/kicad_mcp/{README.md,requirements.txt}` | 能力面/边界/复现；零依赖声明 |
| `mcpserver/kicad_mcp/tests/fixtures/` | 5 份夹具（见 §4.2） |
| `mcpserver/kicad_mcp/sandbox/kicad-20261016-lora-node/` | 8 份**真实 CLI 输出** |
| `tests/test_kicad_mcp.py` | 54 用例（真值源 / 语义 / 契约三层） |
| `docs/integration-graph/kicad_mcp.txt` | 依赖图（注册链/内部依赖/数据流/外部依赖/题材对齐/偏差记录/产物） |

---

## §4 · 验证

### 4.1 测试（54 用例，全绿）

| 层 | 用例数 | 关键断言 |
|---|---|---|
| 真值源 `sexpr` | 9 | 往返在**上游真实 KiCAD 产物**上结构相等；5 类畸形输入精确报错 |
| PCB 语义 `board` | 12 | 铜层 4 / 板框 **40.0×28.0** / 厚度 1.6 / 元件 5 / 焊盘 17 / 网络 9（**名字全在**）/ 最小线宽 **0.15** / 走线 13 / 总长 **89.1515** / 过孔 3（0.6/0.3/环 0.15）/ 未布线 `[DIO0]` |
| 原理图 `schematic` | 5 | 上游真实产物抽出 `C9 / 100n / Device:C / C_0603_1608Metric`，3 个库定义被正确排除；TP1 缺封装被抓 |
| 对账 `design_check` | 5 | 四类差集精确：`only_in_schematic=[R2,TP1]`、`only_on_board=[C1]`、值不符 `R1 4k7↔10k`、库前缀容忍开关 |
| 预检 `fab_bridge` | 5 | 合规板 `pass`；违规板 `fail` 且**恰好 5 条**（4 fail + 1 warn）；规则可覆盖后转 `pass`；未知字段报错 |
| 能力地图 | 5 | **17 类 / 159 routed + 32 direct = 184 distinct**（与上游 `getRegistryStats()` 口径一致）；搜索语义 + 20 条上限 |
| 契约层 `server` | 13 | manifest ↔ `_TOOLS` **逐项相等**；entryPoint 真能解析到带 `handle_handoff` 的类；三种错误路径；CLI 冒烟；**零第三方 import 机械校验** |

### 4.2 夹具真实性（**分级说明，不粉饰**）

| 夹具 | 来源 | 真实性 |
|---|---|---|
| `canonical_schematic.kicad_sch` | **上游仓库真实产物**（eeschema 10.0 / version 20260101），MIT | ★★★ 真实 KiCAD 输出 |
| `upstream_capabilities.json` | 机械抽取上游 `registry.ts`，MIT | ★★★ 真实上游数据 |
| `lora_node.kicad_pcb` / `lora_node.kicad_sch` / `risky_traces.kicad_pcb` | **本仓手写**（本机无 KiCAD，无法生成） | ★★☆ 格式合规的手写样本 |

⇒ 解析器在**真实产物**上的能力已被证明（schematic 路径）；**PCB 路径**只在本仓手写样本上验证 ——
这是本 PoC 的**已知边界**，写进 README §4。

### 4.3 真跑证据

`sandbox/kicad-20261016-lora-node/` 下 8 份 JSON 由 CLI **真实执行**产出（命令写在同目录 README，
可复跑）。抽样（违规板预检）：

```
verdict = fail
  [fail] MIN_TRACE: 最小线宽 0.08 mm 低于工艺下限 0.127 mm
  [fail] MIN_VIA_DRILL: 最小过孔孔径 0.15 mm 低于工艺下限 0.3 mm
  [fail] MIN_VIA_RING: 最小过孔环宽 0.025 mm 低于工艺下限 0.13 mm
  [fail] LAYER_COUNT: 铜层数 8 超出常规工艺上限 6
  [warn] THICKNESS: 板厚 3.0 mm 不在常备厚度 [0.8, 1.0, 1.2, 1.6, 2.0] 内
```

### 4.4 `ruff check .`

全仓 **All checks passed**（含新模块 8 个 .py + 测试 1 个）。

---

## §5 · 上游事实核查（本次实测，不是转述）

| 项 | 实测 |
|---|---|
| 许可 | **MIT** ✅（工单说的 MIT 正确） |
| stars / forks | **2728 / 369** |
| 体量 | 5,906 KB；`python/kicad_interface.py` **300 KB**、`src/server.ts` 39 KB、`src/tools/` 30 文件 |
| 活跃度 | 创建 2025-04-26，最近推送 **2026-10-01** |
| 工具数 | README 自称 registered 244 / indexed 184 / 17 categories；**实测** `toolCategories` = 17 类 / 159 routed + `directToolNames` = 32 direct ⇒ **184 distinct**（与上游 `getRegistryStats()` 的注释口径一致：7 个工具在两个表里、求和会多算） |
| ⚠️ 后继项目 | 作者已另起 **Konnect**（Rust / **AGPL-3.0**）；README 明确「This Python/TypeScript server **remains fully open (MIT) and maintained**」⇒ 本单只与 **MIT 版**发生关系 |

> 抽取时踩过一个坑并已修正：`toolCategories` 里有 **5 个类别把 `tools:` 写成单行数组**，
> 只处理多行形态会丢掉 5 类并级联（先抽到 12 类/148 工具）。修正后 17 类对齐 README，
> 再对 `directToolNames` 求并集才等于 184。

---

## §6 · 未落地（明确列出）

1. **PCB 夹具非 KiCAD 生成** —— 本机没装 KiCAD。要升级真实性：装 KiCAD 后用 `kicad-cli` 生成
   一张真板，替换/补充 `lora_node.kicad_pcb`。
2. **写板/Gerber/DRC/自动布线** —— 刻意不做（需要 KiCAD 运行时 + Freerouting）。
   上游有这些能力；本模块在 `doctor().cannot` 里逐条声明。
3. **嘉立创工艺阈值未接官方** —— 现为保守预设 + 可覆盖 + 出处回传。要接真值需抓当期货期参数
   （不稳定且有版权问题，故未做）。
4. **上游能力地图只覆盖 indexed 184** —— registered 244 里的另外 60 个不在 `registry.ts` 内，未猜。
5. **未与 `eda_ingest` 打通** —— 本模块读 KiCAD、那条链收嘉立创导出；打通属**独立工作**（需要先有
   两侧数据格式的统一口径）。

---

## §7 · 复现

```bash
# 零依赖：不需要 pip install
.venv/Scripts/python.exe -m mcpserver.kicad_mcp.server doctor
.venv/Scripts/python.exe -m mcpserver.kicad_mcp.server board-summary mcpserver/kicad_mcp/tests/fixtures/lora_node.kicad_pcb
.venv/Scripts/python.exe -m mcpserver.kicad_mcp.server fab-precheck mcpserver/kicad_mcp/tests/fixtures/risky_traces.kicad_pcb
.venv/Scripts/python.exe -m mcpserver.kicad_mcp.server cross-check \
    mcpserver/kicad_mcp/tests/fixtures/lora_node.kicad_sch mcpserver/kicad_mcp/tests/fixtures/lora_node.kicad_pcb
.venv/Scripts/python.exe -m pytest tests/test_kicad_mcp.py -q      # 54 passed
```
