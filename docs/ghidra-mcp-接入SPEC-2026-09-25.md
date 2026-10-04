# ghidra-mcp 接入 SPEC（2026-09-25）——固件逆向工具链挂到 Lumo

> 卷153（MCP线）· 落盘：砚 · 状态：**SPEC（未接入；接入实现归后续卷）**
> 参考实现：[`bethington/ghidra-mcp`](https://github.com/bethington/ghidra-mcp)（**Apache-2.0**，3984★，gh api 实测 2026-09-25，非 archived）
> 防重复对照：`docs/LLM4Decompile-MCP-SPEC-v1.md` 是**模型侧**反编译线，本卷是**工具链侧**（规则引擎），互补不重叠。
> 匿名铁律：本文件不写真实姓名。

## 0. 结论先说

**推荐走路径 B（`mcporter_bridge` 外部接入），不把 JVM 拉进 Lumo 后端进程树。**
理由见 §3 的对比表；路径 A（stdio 直挂）保留给"开发期本机直连"与"headless-in-docker"两种场景。

**本机环境实测**（不是"应该能跑"）：

| 前置 | ghidra-mcp 要求 | 本机实测 |
|---|---|---|
| Java | Java 21 LTS | ✅ **Temurin 21.0.12 LTS**（`C:/Program Files/Eclipse Adoptium/jdk-21...`） |
| Python | 3.10+（推荐 uv） | ✅ Python 3.13.2 + **uv 已装** |
| **Ghidra** | **12.1.3**（或兼容版） | ❌ **未安装**（`Program Files` 下无 ghidra）—— 差这一件 |

⇒ 结论：**JVM 层在本机已具备，缺的只是 Ghidra 本体（下载安装即可）**。"本机没有这一层"的说法对 Ghidra 成立，对 Java 不成立。

## 1. 参考实现实测事实（读源码/README/工具目录所得）

| 项 | 事实 |
|---|---|
| 运行形态 | **GUI 插件 + headless server** 双形态（README 自述） |
| 工具规模 | **253 个 MCP 工具全实现**；其中 **GUI 插件暴露 239**、**headless server 暴露 226** |
| 传输 | **`stdio` ｜ `sse` ｜ `streamable-http`** 三种；示例 `--transport streamable-http --mcp-host 127.0.0.1 …`、`http://127.0.0.1:8099` |
| 依赖 | Java 21 LTS、**Ghidra 12.1.3**、Python 3.10+（uv 或 pip+venv） |
| 构建 | **Gradle 为本地默认**（直接读 Ghidra 安装目录里的 jar，无需 install-file）；**Maven 是 CI 同伴**（两端都维护） |
| **脚本执行** | `/run_script_inline`、`/run_ghidra_script` 执行**任意 Java**；**v5.4.1 起默认关闭**（`GHIDRA_MCP_ALLOW_SCRIPTS` 才开）；headless 下开启还会触发 OSGi BundleHost 初始化（数百 ms） |
| 附带 | `docker/`、`ghidra-mcp-setup.ps1`（Windows 安装脚本）、`ghidra_scripts/` |
| 脚本语言注意 | Ghidra 12.1.3 **默认不再启用 Jython**；`.py` 脚本需另装 bundled Jython 扩展，或用 Java 脚本 |

工具分类（按 `tests/endpoints.json` 实测 253 条统计，取前 14 类）：

| 分类 | 数量 | 分类 | 数量 |
|---|---|---|---|
| datatype | 38 | documentation | 14 |
| program | 35 | **xref** | **13** |
| function | 28 | headless | 12 |
| analysis | 21 | utility | 8 |
| listing | 21 | project | 7 |
| debugger | 18 | malware | 5 |
| server | 17 | comment | 5 |

## 2. 本仓两条接入路径的实据（不是设想，是既有约定）

| 路径 | 本仓机制 | 出处 |
|---|---|---|
| **A. 本地 agent 直挂** | 扫描 `mcpserver/<name>/agent-manifest.json` **自动发现**本地 agent；清单含 `entryPoint{module,class}`、`capabilities.invocationCommands[]{command,description,params,example}`、`agentType`、`license`、`UPSTREAM-LICENSE` 惯例；**新适配器默认关**（如 `ENABLE_ADAPTER_CODE_REVIEW=1` 才开） | `mcpserver/adapters/code_review/agent-manifest.json` 等 |
| **B. 外部 MCP 接入** | `mcpserver/mcporter_bridge.py` **加载外部 MCP 服务**（本仓 MCP 总线文档原文：*"扫描 agent-manifest.json 自动发现本地 agent，并通过 `mcporter_bridge` 加载外部 MCP 服务"*） | `mcpserver/mcporter_bridge.py`、`.qoder/repowiki/knowledge/zh/MCP 工具总线与统一调度服务/架构设计.md` |

**一条历史教训（影响选型）**：`mcpserver/adapters/flat_bridges.py` 的 docstring 写明——
Lumo 后端**不创建 FastMCP 实例**、`register_adapters()` 运行期无调用点，导致那批平铺适配器**曾是死代码**；
**真正生效的是 manifest 约定**。⇒ 接 ghidra-mcp 时**不要**照抄平铺适配器写法，走 manifest / 外部桥。

## 3. 路径论证：A（stdio 直挂） vs B（mcporter_bridge 外部接入）

| 维度 | A. stdio 直挂 `mcpserver/` | **B. mcporter_bridge 外部接入（推荐）** |
|---|---|---|
| JVM 归属 | 每次调用拉 JVM / 常驻需自己管 | **JVM 常驻在 Lumo 之外**（Ghidra GUI 或 headless 服务独立进程） |
| 与既有约定契合 | 需自建 manifest 并处理 Ghidra 进程生命周期 | **直接复用现成的外部加载机制**（本仓已有先例） |
| 启动/停止 | 与 Lumo 后端耦合 | **按需启停**：不逆向时不占内存/端口 |
| 失败隔离 | JVM 崩 → 影响后端进程树 | JVM 崩 → 桥只报错，后端不受影响 |
| 传输可选 | 只能 stdio | **HTTP/SSE 任一**（对 dev/容器同样友好） |
| 适用场景 | 开发期本机直连、headless-in-docker（镜像已备） | **常态化接入（推荐）** |

**推荐 B 的核心理由**：Ghidra 是**重运行时**（JVM + 工程库 + 可选 GUI），
把它放进 Lumo 后端的进程树会同时放大会话启动成本、故障面与内存占用；
而本仓**已经有**外部 MCP 的加载通道。路径 A 保留为"本地开发期直连"的快捷方式。

**部署形态建议**（对应仓库自带能力）：
1. **桌面（本机）**：Ghidra GUI + 插件 → 插件开 HTTP/SSE → Lumo 经 `mcporter_bridge` 连 `127.0.0.1:<port>`
2. **无头（服务器/容器）**：`docker/` + headless server（226 工具）→ 同上走外部桥
3. **纯本地开发**：`ghidra-mcp-setup.ps1` 起环境 → stdio 直连（A），仅开发期用

## 4. 首批接入工具 5–8 个（面向 CI-V 协议逆向）

选型依据：CI-V 逆向的核心动作是**"从字节/字符串线索定位解析函数 → 看它如何拆帧 → 交叉引用确认调用点"**，
因此优先取「搜索 / 反编译 / 交叉引用 / 调用图 / 标注」五类，而不是全量 253 个：

| # | 工具（实测 endpoint 名） | 分类 | 在 CI-V 逆向里的用途 |
|---|---|---|---|
| 1 | `/search_byte_patterns` | analysis | 用已知 CI-V 帧头/命令字节（如 0xFE 0xFE 起始 + 地址 + 命令）在固件里定位解析代码 |
| 2 | `/search_strings` + `/list_strings` | listing | 抓 `CI-V`、`IC-705`、`baud`、`0x…` 等线索字符串，锚定相关函数 |
| 3 | `/get_xrefs_to` | xref | 从命令常量/字符串反查**谁在读它** —— 找协议解析入口的标准手法 |
| 4 | `/decompile_function` | function | 把候选函数反编译成可读伪码，核对帧格式（地址/命令/数据/结束符） |
| 5 | `/get_function_xrefs` + `/analyze_call_graph` | xref/analysis | 确认解析函数的调用链（哪个状态机在调它），避免误判孤立函数 |
| 6 | `/search_functions` / `/search_functions_enhanced` | function | 按名称/特征找已识别的收发函数族 |
| 7 | `/rename_symbol` + `/set_comment`（可批量 `/batch_set_comments`） | comment | **把逆向结论固化回 Ghidra 工程**（帧字段命名、命令表注释），让下一轮不必重来 |
| 8 | `/run_ghidra_script`（**默认关，需显式开**） | script | 批量模式扫描（如枚举所有 0xFE 起始的常量）—— 属特权操作，见 §5 |

> 说明：以上 8 个是**首批**；debugger（18 个）、malware（5 个）等类别本批不接（CI-V 逆向用不到动态调试就能拿下大部分）。

## 5. 安全与闸门（与卷151 的 ActGov/LeaseGuard 对接）

1. **脚本执行默认关**是上游的设计（v5.4.1 起）——**本仓接入时必须保持关闭**，
   只在明确需要批量扫描时开，且开的那一刻起 `/run_script_inline` 就是**任意 Java 执行**（等价 shell）。
2. 这条正好落在卷151 [`docs/ActGov-租约守卫-工单特权操作SPEC-轮23.md`](ActGov-租约守卫-工单特权操作SPEC-轮23.md)
   的「特权操作」定义里：**开脚本执行 / 写回工程符号名** 应走**租约式审批**（限时、限范围、可吊销），
   而不是给 agent 常开通道。
3. 只读工具（搜索/反编译/交叉引用）可默认放行；**写类工具**（rename/comment/script/内存块）默认关。

## 6. 对接 RS-BA1 / IC-705 逆向线（首战场景）

现状（本仓已有资产）：`vendor/rsba1-core`（Python 侧远程控制/协议封装）、`apiserver/routes/radio.py`、
`mcpserver/adapters/rsba1_adapter/`（既有适配器）、`mcpserver/rf_brain/`（射频侧工具面）。

**首战目标**：用 Ghidra MCP 把 **CI-V 命令表**从固件/官方固件的解析代码里"挖出来并可复核"：

```
① /search_byte_patterns(0xFE 0xFE)        → 候选帧解析点
② /search_strings("IC-705"|"CI-V"|"baud") → 线索锚点
③ /get_xrefs_to(候选常量/字符串)           → 收敛到解析函数
④ /decompile_function(候选)                → 读出帧结构（地址/命令/数据/结束）
⑤ /get_function_xrefs + /analyze_call_graph → 确认状态机调用路径
⑥ /rename_symbol + /set_comment            → 结论写回工程（可复核）
⑦ 与 vendor/rsba1-core 的命令表**对账**     → 差异即"文档没写但固件支持"的潜在命令
```

**产出物**：CI-V 命令表的**带出处版本**（每条命令标注 Ghidra 里的函数地址/证据），
与 rsba1-core 现有实现比对后给出缺口清单 —— 这是逆向线要的"可复核结论"，不是"我猜"。

## 7. 落地步骤（建议顺序）

1. 装 **Ghidra 12.1.3**（本机缺此件；Java 21 已具备）
2. 按上游 `ghidra-mcp-setup.ps1` / `docker/` 起服务；**保持 `GHIDRA_MCP_ALLOW_SCRIPTS` 关闭**
3. 在 Lumo 侧按 **manifest 约定**写薄适配器（`mcpserver/<name>/agent-manifest.json`），经 `mcporter_bridge` 连外部 MCP
4. 只接 §4 的 8 个只读工具（写类工具默认关，走租约审批）
5. 用一份**已知协议**（RS-BA1/CI-V 现有文档）做**回归**：工具链能否复现已知命令表 → 通过后再上未知固件

## 8. 未决项 / 边界

1. **未做接入实现**：本卷只出 SPEC；适配器骨架留待后续卷（工单也写明"接入实现归后续卷"）。
2. **未装 Ghidra、未跑任何工具**：本机实测只到"Java 21 ✓ / uv ✓ / Ghidra ✗"这一层。
3. **253/239/226 三个数字来自上游 README/工具目录**（实测其 `tests/endpoints.json` 为 253 条），
   实际可调用数随 Ghidra 版本与插件加载情况变化。
4. **内部/外部桥的具体 API**（`mcporter_bridge` 的注册函数名与配置项）未逐行核读 —— 写适配器前需读该模块。
5. 固件来源与合规：本 SPEC 不涉及任何固件分发的合法性判断，实际分析需自行确认来源合规（上游为 Apache-2.0 工具，分析对象的合规性另论）。
