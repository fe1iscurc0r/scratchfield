# 工单 244 完工报告 · toolknit 本地文件处理工作台接入

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥
> 日期：**2026-10-14** · 落点：`mcpserver/toolknit_mcp/`（**下划线**，工单写的连字符见偏差 #1）
> 一句话：把外部 npm 包 `@toolknit/cli` 的本地文件处理能力接进 `mcpserver/`，白名单 8 个工具、
> 零桌面端接触、零既有文件改动、62 用例全绿；顺带实测出 4 条**反直觉的硬事实**并全部做成回归。

---

## §0 · 交付事实（先给可核对的数）

| 项 | 值 |
|---|---|
| 分支 | `feat/w244-toolknit-mcp` |
| 新增文件 | **14 个** = 模块文本 7（`__init__`/`workspace`/`tools`/`server`/`manifest`/`requirements`/`README`）+ 测试 1 + 夹具 4 + 集成图 1 + 报告 1 |
| 既有文件改动 | **0 个** |
| 净新增字节 | **275,923 B**（含 114,618 B 的 `sample.pdf` 夹具） |
| 行尾 | **10 个文本文件**全 LF（另有 4 个二进制夹具，无行尾概念）；`test_deliverable_is_lf_only` 按**显式清单**同时钉住「10」这个数与行尾 |
| `pytest tests/test_toolknit_mcp.py -q` | **62 passed / 0 failed**（89.0 s） |
| `ruff check`（242/243 同款配置） | **All checks passed!** |
| `package-lock.json` / `package.json` | **未带入**（工单 §3.4） |
| 零桌面端接触 | 三个标识串**全仓仅集成图命中 10 行**，其余 0 |
| 不许触碰项 | 不碰 `mcp_assembly` / `mcp/services` / `core/` / `coupled/` / `apiserver/routes/` |

逐文件 blob sha 自证与合并后复核结果见 PR 正文与交付日志。

---

## §1 · 三处拍板（开工前，用户已确认）

| 事项 | 拍板 |
|---|---|
| 落点命名 | `mcpserver/toolknit-mcp/`（连字符，工单原文）→ 改为 **`toolknit_mcp`**（下划线） |
| 三个 PoC 能力 | 「PDF 文本提取 / PPT 转 PDF / 颜色提取」→ **按上游真实能力重构** |
| LibreOffice | **现在安装**（已完成 26.8.1.1） |

---

## §2 · 任务对照

### 任务一（P0）建骨架 —— ✅ 完成

要求 5 件套 → 实交 7 件（多 `agent-manifest.json` 与 `agent-manifest` 所需的接线说明）：

| 工单要求 | 实交 | 说明 |
|---|---|---|
| `server.py` | ✅ | `ToolknitBridge` + `handle_handoff` + 手工复现 CLI（10 个子命令） |
| `tools.py` | ✅ | 8 工具适配 + `run_cli` + JSONL 日志 |
| `workspace.py` | ✅ | 路径纪律 4 条硬规则 |
| `__init__.py` | ✅ | 包文档 + 导出 |
| `README.md` | ✅ | 接入说明 + **10 项偏差表** + 已知边界 |
| `requirements.txt` | ✅ | Python 侧零第三方依赖（说明见 §3） |
| `tests/` | ✅ | 夹具在模块内，测试在仓根 `tests/`（工单 §3.1 的路径） |

**任务一.2 的偏离**：工单要求「在 `pyproject.toml` 或 `requirements.txt` 加 `mcp`、`@toolknit/cli`」。
两条都**不能照字面做**，理由见 §3。

**任务一.3**：✅ 零桌面端接触（见 §6）。

### 任务二（P0）三个核心能力 PoC —— ✅ 完成（且是「真跑」，非空 PoC）

工单点名的三个能力，**其中一个在上游不存在**（预检已实证）：

| 工单点名 | 上游实况 | 本单交付 | 实测证据 |
|---|---|---|---|
| `pdf_extract_text(path)` | ❌ **不存在**（PDF 子命令无任何文本提取；MCP 侧 46 工具也无） | `pdf_inspect`（元数据） | 3 页 / 114,618 B 夹具 → `pages=3`、`bytes=114618` ✅ |
| `ppt_to_pdf(pptx_path, out_dir)` | ✅ 存在（依赖 LibreOffice） | `ppt_to_pdf` | 2,531 B pptx → **21,052 B PDF、2 页**，`renderer=windows-install` ✅ |
| `extract_palette(image_path)` | ✅ 存在 | `extract_palette` | 双色图 2 色/各 50%/共 1280 像素；纯色图 1 色 ✅ |
| （工单未要求） | qpdf 随包自带 | ➕ `pdf_compress` | 114,618 B → **7,598 B**（high），页数不变 ✅ |

**验收项对照**：

- ✅ `pytest tests/test_toolknit_mcp.py -q` → **62 用例全绿**（工单要求 ≥4：3 happy + 1 边界）
  - happy path：色板（双色/纯色）、PDF 元数据、PDF 压缩、PPTX→PDF（另有 dry-run 与自动唯一命名）
  - 边界：PDF 不存在、相对路径、跨目录、非法工作区名、count 越界、后缀错、产物名逃逸、
    `npx` 缺失、未知工具、参数名写错…
- ✅ 夹具落盘 `mcpserver/toolknit_mcp/tests/_fixtures/sample.pdf` = **114,618 B**（工单要求 ~100 KB）
- ✅ 日志 **JSONL append**（`open(..., "a", newline="\n")`），并有专门用例断言
  「两次调用是**两行**而不是被覆盖」+「失败也记 + 带 error_code」
  +「日志写失败**不影响主调用**」

### 任务三（P1）与既有模块耦合 —— ✅ 完成

| 工单点名 | 实测耦合点 |
|---|---|
| `mcpserver/llm_gateway/` | **0**（四个工具全是确定性文件处理，无需要 LLM 叙述的环节 ⇒ 刻意不引入，连惰性导入都不加） |
| `mcpserver/kicad-mcp/` | **0**（main 全树查询 404，该目录不存在 ⇒ 工单「已有/规划」实为规划未落地） |
| `mcpserver/mcp_registry.py` | **唯一**真实耦合，且**零改动**：新增 manifest 由既有 `glob("**/agent-manifest.json")` 自动发现 |

集成图：`docs/integration-graph/toolknit_mcp.txt`（含依赖图、时序、耦合点、边界、清单）。
**「只改主调用路径，不动现有模块内部接口」→ 本单一个既有文件都没动。**

---

## §3 · 「零 Python 依赖」这个决定的口径（工单任务一.2 的偏离说明）

工单要求在 `requirements.txt` 里加 `mcp` 与 `@toolknit/cli`。**两条都不能照字面做**：

1. **`@toolknit/cli` 不是 Python 包**。实测 PyPI 上 `toolknit-cli` / `toolknit` **均 404**；
   它是 npm 包，由 `npx -y @toolknit/cli@2.3.1` 按需拉起。写进 Python 依赖是**类型错误**。
   本模块对它的依赖声明放在 `agent-manifest.json` 的 `requires.external_binaries`。

2. **`mcp` Python SDK 在本仓并不使用**。实测根 `requirements.txt` **不含 `mcp`**，
   且 `mcpserver/AGENTS.md` 明载本仓原生范式是「子模块 + `agent-manifest.json` +
   `handle_handoff` 契约」（`ALLOWED_MODULE_PREFIXES = ["mcpserver.", "vendor."]`）。
   工单要的**实质**是「Python server 用 subprocess 驱动 npm CLI」——
   本模块完全满足（`tools.run_cli`，`shell=False`），只是接线走仓内既有契约。
   **不为了对齐字面而引一个用不上的 SDK 依赖。**

⇒ 结果：**Python 侧零第三方运行时依赖**（纯标准库），由
`test_module_is_pure_stdlib` 静态扫描 + 白名单钉死。

---

## §4 · 实测出来的 4 条硬事实（都已做成回归，勿当 bug 修）

这一节是本单最有价值的部分：**4 条都与直觉相反**，且全部由测试钉住。
工单写的前提若与这些冲突，以本节的实测为准。

### 4.1 ⭐ `ppt_to_pdf` 的输出路径 **>83 字符**会让 LibreOffice 静默崩

- 现象：`LibreOffice conversion failed: exit code 3221226505`
  （`0xC0000409` fail-fast，**stderr 完全为空** —— 上游只能报一个 exit code）
- 成因：上游把 `-env:UserInstallation=<out>/.toolknit-libreoffice-XXXXXX/profile`
  以 `file:///` URL 传给 soffice，**URL 跨过 127 字符即崩**（`8 + 36 + 84 = 128`）
- 受控实测（同一基准目录，只改输出目录长度，每档各跑 **2 次**）：

  | 长度 | 68 | 71 | 76 | 77 | 78 | 80 | 82 | **83** | **84** | 85 | 86 | 95 | 109 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | 结果 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅/✅ | ❌/❌ | ❌ | ❌ | ❌ | ❌ |

- **与目录层级无关**（专门做了对照）：长而浅（1 层、109 字符）❌；
  短而深（6 层、71 字符）✅
- 对策：工作区根放短路径。工单要求的服务器路径
  `/home/ubuntu/scratchpad/research/<ws>/toolknit-output` ≈ 60 字符，**安全**
- 处置：**不据此拒绝调用**（上游行为会随版本变），只在失败时把这条写进 `hint`；
  用 `test_known_boundary_output_dir_length_limit` **留证** —— 上游若修好，该用例变红，
  那是「该更新文档了」的信号

> **这一条差点让我误判自己的代码有 bug。** 测试最初用 pytest 的 `tmp_path`
> （`%TEMP%\pytest-of-ASUS\pytest-N\toolknit-ws0`，+`toolknit-output` = **87 字符**），
> PPT 用例稳定全红。排查链路：主线程直调 ✅ → 工作线程 ✅ → pytest 外 ✅ →
> 排除 `PYTEST_*` 环境变量 → 排除 `--output-name` → 受控扫描**定位到长度**。
> 测试因此改用**短临时目录**，并加了「环境 TEMP 若太深就直接说清楚」的前置守卫。

### 4.2 `doctor` **不检查** LibreOffice

`doctor` 的 `result` 只有 `version` / `node` / `qpdf` / `ffmpeg` 四个键。
LibreOffice 是**渲染时懒探测**的，只出现在 `ppt to-pdf` 返回体的 `result.renderer`。
⇒ **拿 doctor 判 LibreOffice 必然假阴性**。唯一可靠入口是 `renderer_probe`
（内部即 `ppt to-pdf --dry-run`，实测 **3.2 s**、`output_dir`/`output_path` 均为 `null`、**不写盘**）。

另：`doctor` 在 ffmpeg 缺失时整体返回 `ok:false` / **rc=5**（本机实测），
尽管 qpdf 完全可用 ⇒ 它的 rc **不能**当「工具链是否健康」用。
回归：`test_doctor_does_not_report_libreoffice`。

`renderer_probe` 的探测载荷是**纯标准库现场生成**的 1 页最简 PPTX（实测 1,824 B），
**不向包里塞二进制资产**，也无 repo 相对路径依赖（回归：`test_renderer_probe_needs_no_repo_relative_asset`）。

### 4.3 `image colors --count` 是**上界**不是产量

`solid_red.png`（32×32 纯色）即使传 `--count 2` 也只返回 **1** 个颜色。
⇒ 断言只能写 `returned_count <= requested_count`。回归：
`test_palette_count_is_an_upper_bound_not_a_quota`。

### 4.4 上游**没有** PDF 文本提取

PDF 子命令只有 `inspect/merge/split/rotate/encrypt/decrypt/compress/enhance/to-image`；
MCP 侧 46 个工具里也无任何文本提取。工单点名的 `pdf_extract_text` **不存在**。
仓内该能力在 `mcpserver/adapters/pdf2md_adapter`（Docling / MarkItDown），
本模块**不重复造**，只在 `list_tools().capability_gaps` 里如实列出缺口。

---

## §5 · 工单前提与实况的 10 处偏差（逐条留证）

| # | 工单原文 | 实测（2026-10-14） | 处置 |
|---|---|---|---|
| 1 | 落点 `mcpserver/toolknit-mcp/` | **连字符目录 Python 无法 import**；仓内 `mcpserver/` 52 个子目录含连字符 **0** 个 | 改 `toolknit_mcp` |
| 2 | `@toolknit/cli` **v3.0.0** | **不存在**。npm 仅 8 版本（1.2.7/1.2.8/1.3.0/2.0.0/2.1.0/2.1.1/2.3.0/2.3.1），latest = **2.3.1** | 钉死 2.3.1 |
| 3 | `npm pack` 不到 5 MB | `unpackedSize` = **40,866,503 B ≈ 39 MB**（差 8 倍） | 仍不 clone；如实记录 |
| 4 | `pdf_extract_text` 提文本+页码位置 | **能力不存在**（见 §4.4） | 以 `pdf_inspect` 替代 |
| 5 | 产物落 `<workspace>/toolknit-output/<uuid>.pdf` | CLI **恒建子目录** `<name>_ppt_to_pdf/` | 落 `…/<stem>-<hex8>_ppt_to_pdf/<stem>-<hex8>.pdf`；唯一性满足 |
| 6 | `package.json` 管 npm 依赖 | 本仓是 Python 后端，且 §3.4 禁带 lock | 无 `package.json`，只 `npx` |
| 7 | 1626⭐ / 152 forks / push 10-12 | **1665⭐ / 153 forks / 157,367 KB / push 2026-10-14T14:08:08Z** | 如实记录 |
| 8 | `docs/integration-graph/toolknit-mcp.txt` | 仓内既有两份均为**下划线**（`rf_workflow.txt`/`esp32.txt`） | 落 `toolknit_mcp.txt` |
| 9 | `mcpserver/kicad-mcp/`「已有/规划」 | main 全树 **404** | 认定规划未落地（耦合点 0） |
| 10 | 「68 桌面工具 + 46 MCP 能力」 | MCP 侧**恰好 46** ✅（这个数对） | 如实记录 |

> 这是**第 10 次**「工单写的路径/前提与实况不符」。本单的新形态是
> **「前提三错」**：版本号错（3.0.0 不存在）+ 体积错（差 8 倍）+ 能力错（点名工具不存在）。
> 与 243 的「要新建的东西已存在」、241 的「目录整个不存在」形态都不同。

**§3.7 硬性前置：满足。** 上游许可实测 = **`Apache-2.0`** ✅。

---

## §6 · 零桌面端接触（工单 §3.3）

本模块只经 `npx` 调用 CLI，**不读、不引、不 clone** 上游仓库的桌面端代码。

- 工单要求的三个标识串在本仓**只出现在**
  `docs/integration-graph/toolknit_mcp.txt`（§0.1 给出可直接复制的 grep 原文）
- 本模块内**零命中**，且做成回归 `test_no_package_lock_or_tauri_contact_in_module`
- ⚠️ 该回归**故意把三个串拆成碎片拼装**（`"src" + "-tauri"`）：若写字面量，
  **测试自己就会成为 grep 命中项**，反倒破坏它守护的验收项。
  碎片是否拼对另有反向自证（到集成图里找这三个串）
- 验证覆盖：本单交付区（14 个文件）**仅集成图命中 10 行**（含 §0.1 的明文列举与 grep 原文），
  其余 13 个文件 **0 命中**；field 验证场（main 真字节快照 `mcpserver/` + `tests/` + `system/`）
  **0 命中**

---

## §7 · 依赖许可审计（工单 §4 风险表要求）

做法：临时目录 `npm install @toolknit/cli@2.3.1` → `npm ls --all --json` +
**文件系统递归枚举** `package.json`（不用 `node_modules/<name>` 直查——
npm 目录非扁平，直查会把 118/119 全判成 UNKNOWN，第一版就栽在这）。
落盘：`w244_license_audit.json`。

**结论：0 强 copyleft、0 弱 copyleft。**

| 分类 | 数量 | 明细 |
|---|---|---|
| MIT | 85 | — |
| ISC | 13 | — |
| Apache-2.0 | 3 | 含 `@toolknit/cli` 自身 |
| 0BSD | 3 | — |
| MIT/X11 | 2 | — |
| BSD-3-Clause | 2 | — |
| Unlicense | 1 | — |
| `(MIT AND Zlib)` | 1 | 双宽松，无风险 |
| **`ELECTABLE-PERMISSIVE`** | **1** | `jszip@3.10.1 (MIT OR GPL-3.0-or-later)` |
| **`UNKNOWN`** | **1** | `buffers@0.1.1` |

两个需要单独评估的：

1. **`jszip@3.10.1` = `(MIT OR GPL-3.0-or-later)`** —— **双许可 `OR`，可选 MIT 分支**
   ⇒ **不构成传染**。分类器最初把它判成 `STRONG-COPYLEFT`（朴素子串命中），
   已修正为「`OR` 表达式里存在宽松分支 ⇒ ELECTABLE-PERMISSIVE」。
   npm registry 权威元数据复核：latest 3.10.2 的 `license` 同为
   `(MIT OR GPL-3.0-or-later)`，一致。

2. **`buffers@0.1.1` —— 无任何许可声明**（硬证据）：
   - `package.json` **无 `license` / `licenses` 字段**（包内 6 个文件全列出，无 LICENSE）
   - npm registry 该版本与 latest 的 `license` 均为 `null`
   - 声明的上游仓库 `substack/node-buffers` 与 `substack/buffers` **均 404**（仓库已删）
   - 引入链：`exceljs@4.4.0 → unzipper@0.10.14 → binary@0.3.0 → buffers@0.1.1`
     （`npm ls buffers` 实测）
   - **风险评估**：`exceljs` 只在 **Excel/表格路径**上，而本单白名单的四个工具
     （色板 / PDF 元数据 / PDF 压缩 / PPTX→PDF）**完全不经过 exceljs**；
     且本仓**不 vendor、不 redistribute**（只在用户机器上 `npx` 运行时拉取）
   - **建议**：不阻断本单；若将来要暴露 Excel 相关能力，先就此项与沈遥确认

---

## §8 · 本单自己修掉的 7 处问题（全部已回归）

| # | 现象 | 根因 | 判定 |
|---|---|---|---|
| 1 | `renderer_probe` 抛 `KeyError: 'slide1'` | 我引用了短键，实际键是全路径 `ppt/slides/slide1.xml` | **我的 bug** |
| 2 | `handle_handoff("list_tools")` 返回「未知工具」 | manifest 声明了 `list_tools`，但 `_TOOLS` 映射漏登记 —— **方法写在类上不等于 LM 调得到** | **真缺陷**（工单 §4 明确要求它可用） |
| 3 | `pdf_compress(output_name="sample.pdf")` 未触发 `OUTPUT_IS_SOURCE` | 产物恒落 `toolknit-output/`，与工作区根的源文件**本就不同路径** | **测试前提错了**（守卫只在源文件本身位于产物目录时可达）；已改为可达场景 + 补一个对照组 |
| 4 | 模块内出现三个桌面端标识串 | README/测试写了字面量，违反 §3.3「只允许集成图命中」 | **违反验收项**；已从 README 移除，测试改为碎片拼装 |
| 5 | PPT 用例在 pytest 下稳定全红 | 非代码问题：`tmp_path` 太长（87 > 83）触发 LibreOffice fail-fast | **环境边界**（见 §4.1）；改用短临时目录 + 前置守卫 |
| 6 | 报告/PR 宣称「**14 个**文本文件全 LF」 | 守卫 `test_deliverable_is_lf_only` 只扫 `PKG_ROOT`，实覆盖 **7** 个模块文件 ⇒ **声明超出守卫范围** | **文档超报**；守卫改为「显式清单 + 计数断言 == **10**」，文档口径同步为「10 个文本文件」（含本行修正） |
| 7 | §0 的「净新增字节」写着旧值 | 报告最后一次编辑后**未回填总数** ⇒ 陈旧数字 | **文档陈旧**；交付前按实测重算并做**不动点校验**（改写后总数不变） |

> 第 6、7 条是**交付前终检**抓出来的（不是测试抓的）—— 它们提醒：
> 「文档里的每个数字都要能复算，且**声明范围不得超过守卫范围**」。
> 第 6 条已顺带变成守卫的一部分（计数断言）。

另有 1 处**产物能力补强**：CLI 失败时原先只回带 `error`/`error_code`，
现补带 **`cli_stderr` / `cli_stdout`**（截断 1200 字符）——
因为上游 `LibreOffice conversion failed: exit code N` 这种只有 message 的错，
真线索在 stderr 里；不回带就是让调用方对着一个 exit code 猜。

---

## §9 · 未落地 / 需接手

1. **`pdf_extract_text` 不存在** ⇒ 若确实需要「PDF 文本 + 页码位置」，请走
   `mcpserver/adapters/pdf2md_adapter`（Docling / MarkItDown），或另立工单。
   本单只用上游真实存在的能力，**不虚构接口**。
2. **`buffers@0.1.1` 无许可声明**（见 §7.2）—— 当前不影响（我们不走 Excel 路径），
   但若要暴露表格生成能力，需先确认。
3. **ffmpeg 未安装** —— 本单四工具均不需要；若将来接音频类上游能力需补装。
4. **LibreOffice 在 Windows 开发机的路径长度边界**（§4.1）—— 服务器侧路径安全，
   但若有人把工作区放到深层临时目录就会踩。若要在**工具层**主动拦截，
   需新立工单（本单刻意不拦，避免与上游行为耦合）。
5. **上游活跃度**：工单 §4 提示「可能还在大改」。本单已钉死 2.3.1；
   建议定期 `npm view @toolknit/cli version` 巡检，升级前重跑本单 62 用例。

---

## §10 · 复现方式

```bash
# 环境体检
python -m mcpserver.toolknit_mcp.server list-tools
python -m mcpserver.toolknit_mcp.server renderer-probe
python -m mcpserver.toolknit_mcp.server doctor

# 三个 PoC（+1）
python -m mcpserver.toolknit_mcp.server palette      --image <abs.png> --count 5
python -m mcpserver.toolknit_mcp.server pdf-inspect  --pdf <abs.pdf>
python -m mcpserver.toolknit_mcp.server pdf-compress --pdf <abs.pdf> --level high
python -m mcpserver.toolknit_mcp.server ppt-to-pdf   --pptx <abs.pptx>

# 测试与 lint
python -m pytest tests/test_toolknit_mcp.py -q
python -m ruff check mcpserver/toolknit_mcp tests/test_toolknit_mcp.py
```

⚠️ 跑 PPT 相关测试前，确保工作区（及 `%TEMP%`）路径**短于 83 字符**（见 §4.1）。
