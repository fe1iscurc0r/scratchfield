# toolknit_mcp — 本地文件工作台（PDF / PPT / 图像）

> 工单 244 · 漏斗 2.0 §1.3「轻量猎手 A 类」第 3 单
> **能力来自第三方工具 toolknit**，非本仓组件。

把外部 npm 包 **`@toolknit/cli`**（来自 [`ZihangDong/toolknit-desktop`](https://github.com/ZihangDong/toolknit-desktop)。
Apache-2.0）的本地文件处理能力接入 scratchpad 的 `mcpserver/` 体系。

**不整包 clone**：上游是约 154 MB 的桌面端 monorepo（实测仓库体积 157,367 KB），
而真正能用的是 `@toolknit/cli` 这个 npm 包。本模块只按需 `npx` 拉它，
**零桌面端接触**（见 §4）。

---

## 1 · 对外工具（白名单 9 个）

工单 §4 风险表点明「上游 MCP 协议暴露 46 个工具会导致 LM 工具选择混乱」，
故本模块**只**转发下面这些，其余一律不经由本 server 暴露。

| 工具 | 输入 | 输出 | 写盘 |
|---|---|---|---|
| `extract_palette` | 图片路径（png/jpg/jpeg/webp）、`count`(2-9) | 色板：hex + rgb + hsl + pixels + percentage（按占比降序） | 否 |
| `pdf_inspect` | PDF 路径 | 页数 / 字节 / 文件名 | 否 |
| `pdf_compress` | PDF 路径、`level`(low/medium/high) | 压缩后的 PDF（落工作区） | 是 |
| `ppt_to_pdf` | PPTX 路径、`output_name`、`dry_run` | 渲染出的 PDF + 页数 | 是（`dry_run` 时否） |
| `pdf_text` 🆕 | PDF 路径、`engine`、`max_chars_per_page`、`layout` | **逐页文本（带页码）**；`layout=true` 时附行级 bbox | 是（`<stem>.txt`） |
| `renderer_probe` | — | LibreOffice 可用性 / command / source / version | 否 |
| `doctor` | — | qpdf / ffmpeg / node 状态 | 否 |
| `cli_version` | — | CLI 连通性与实际报告版本 | 否 |
| `workspace_info` | — | 工作区根 / 产物目录 / 日志路径 | 否 |
| `list_tools` | — | 白名单自述 | 否 |

⚠️ **`pdf_text` 是唯一不经 toolknit CLI 的工具**（上游没有 PDF 文本提取能力）——
它用仓内引擎承接该缺口，见 §5.2。

后六个是**只读诊断**（`renderer_probe` / `doctor` / `cli_version` / `workspace_info` /
`list_tools`），用来排障而不是处理内容——`ppt_to_pdf` 失败时先跑 `renderer_probe` 就知道
是不是缺 LibreOffice。

---

## 2 · 与工单的偏差（实测得出，逐条留证）

工单 §0/§2 的若干前提与 npm/GitHub 实况不符。**本模块按实测实现**，偏差如下：

| # | 工单原文 | 实测（2026-10-14） | 本模块处理 |
|---|---|---|---|
| 1 | 落点 `mcpserver/toolknit-mcp/` | **连字符目录 Python 无法 import**；仓内 `mcpserver/` 52 个子目录中含连字符的 **0 个** | 改为 `mcpserver/toolknit_mcp/`（下划线，与 242/243 一致） |
| 2 | `@toolknit/cli` **v3.0.0** | **不存在**。npm 仅 8 个版本：`1.2.7/1.2.8/1.3.0/2.0.0/2.1.0/2.1.1/2.3.0/2.3.1`，latest = **2.3.1** | 钉死 2.3.1（`TOOLKNIT_CLI_VERSION` 可覆盖） |
| 3 | 「`npm pack` 不到 5 MB」 | npm registry `unpackedSize` = **40,866,503 B ≈ 39 MB**（差 8 倍） | 仍不 clone 整仓；如实记录体积 |
| 4 | `pdf_extract_text(path)` 提「文本 + 页码位置元数据」 | **上游该能力不存在**。PDF 子命令只有 `inspect/merge/split/rotate/encrypt/decrypt/compress/enhance/to-image`；MCP 侧 46 个工具里也没有任何 PDF 文本提取 | **244b 已把缺口补上**：新增 `pdf_text`，用**仓内引擎**（pypdf / PyMuPDF / `mcpserver/adapters/pdf2md_adapter`）承接，**逐页提取 ⇒ 天然带页码**；`layout=true` 另给行级 bbox。见 §5.2 |
| 5 | 产物落 `<workspace>/toolknit-output/<uuid>.pdf` | CLI **恒建子目录** `<name>_ppt_to_pdf/` 并写 `<name>.pdf` + `manifest.json` | 落 `<工作区>/toolknit-output/<stem>-<hex8>_ppt_to_pdf/<stem>-<hex8>.pdf`；**唯一性满足**（自动 hex8），多一层子目录是 CLI 固有行为；带 `<stem>` 比裸 uuid 更可追溯 |
| 6 | `package.json` 管 npm 依赖 | 本仓是 Python 后端；**不带 package-lock.json**（工单 §3.4 明确禁止） | 无 `package.json`，只经 `npx` 按需拉 |
| 7 | 依赖含桌面端整仓（Rust 后端 + WebView 前端） | 本仓零桌面端接触 | 见 §4 验证 |
| 8 | `docs/integration-graph/toolknit-mcp.txt` | 仓内既有两份集成图均为下划线（`rf_workflow.txt` / `esp32.txt`） | 落 `docs/integration-graph/toolknit_mcp.txt` |
| 9 | 上游 1626⭐ / 152 forks / push 2026-10-12 | 实测 **1665⭐ / 153 forks / size 157,367 KB / push 2026-10-14T14:08:08Z** | 如实记录（许可核对见 §5） |
| 10 | 「68 桌面工具 + 46 MCP 能力」 | MCP 侧**恰好 46** ✅（工单这个数对）；`ppt` 子命令依赖 LibreOffice | 如实记录 |

---

## 3 · 工作区路径纪律（工单 §1 目标 4）

`workspace.py` 是「路径必须解析到工作区，禁止相对路径 / 跨目录」的 Python 侧实现：

1. **工作区根**由 `TOOLKNIT_WORKSPACE_ROOT` 决定（服务器侧设 `/home/ubuntu/scratchpad/research`），
   未设时回退 `<仓库根>/research`。工单给的是服务器绝对路径 ⇒ 设计成环境变量可覆盖，
   不必改代码。
2. **工作区名只允许单段安全标识符**（`[A-Za-z0-9][A-Za-z0-9._-]{0,63}` 且不含 `..`）
   ⇒ `../etc` / `a/b` / 空串一律拒绝。
3. **输入必须绝对路径且落在工作区内**：先 `resolve()` 解符号链接再判包含，
   再按平台大小写口径 `normcase` 归一 ⇒ 相对路径、跨目录、软链逃逸都拒绝。
4. **输出只落工作区内的约定子目录**，绝不写回源文件所在目录。

判据用 `resolve()` 后的**规范路径**比较而非字符串前缀——否则 `/ws/a/../b` 与符号链接能绕过。

```
TOOLKNIT_WORKSPACE_ROOT=/home/ubuntu/scratchpad/research
└── <workspace-name>/            ← 可选单段名，边界收紧到该目录
    ├── toolknit-output/         ← 产物（PDF 等）
    └── toolknit-logs/
        └── toolknit-calls.jsonl ← 每次 handoff 一行（JSONL append）
```

日志按工单铁律用 **append** 写：`open(..., "a", newline="\n")` 一行一个 JSON，
进程被杀最多坏末行，不会像 `json.dump` 一次性写那样整体报废。

---

## 4 · 零 Tauri 接触（工单 §3.3）

本模块只经 `npx -y @toolknit/cli@2.3.1` 调用 CLI，**不读、不引、不 clone** 上游仓库的
桌面端代码（Rust 后端 + WebView 前端）。

工单 §3.3 要求三个前端标识串在本仓**只应出现在集成图**里。**本模块内 0 命中**——
连本文件也不写它们（文档里只用「桌面端 Rust 后端 / WebView 前端」这类描述，
以免自身破坏那条 0 命中断言）。**确切的 grep 原文与逐条判定见**
`docs/integration-graph/toolknit_mcp.txt` 的「零接触验证」一节。

模块级自证（`tests/test_toolknit_mcp.py` 中的
`test_no_package_lock_or_tauri_contact_in_module` 已把这三条串做成回归：
本模块目录内任何 `.py`/`.json`/`.md`/`.txt` 出现它们即失败）。

---

## 5 · 依赖与许可

**Python 侧零第三方依赖**（详见 `requirements.txt`）。外部依赖：

| 依赖 | 必需性 | 实测（2026-10-15 复核） |
|---|---|---|
| Node ≥ 20.12.0 + `npx` | 必需 | v22.22.2 / npm 10.9.7 ✅ |
| qpdf | 随 npm 包自带 | `<npx 缓存>/…/@toolknit/cli/vendor/qpdf/qpdf.exe` ✅ |
| LibreOffice | 仅 `ppt_to_pdf` | 26.8.1.1 ✅（装好后 CLI **自动发现**，无需环境变量） |
| ffmpeg | 白名单工具均不需要（只影响 `doctor` 的 ok/rc） | ⚠️ 已装 9.0.2，但**必须用 `TOOLKNIT_FFMPEG_PATH` 指向真实文件**（原因见 §5.3） |

### LibreOffice 的两条反直觉事实（实测）

1. **`doctor` 不检查 LibreOffice**——它的 `result` 只有 `version`/`node`/`qpdf`/`ffmpeg`。
   LibreOffice 是渲染时**懒探测**的，只出现在 `ppt to-pdf` 返回体的 `result.renderer`。
   ⇒ 拿 `doctor` 判 LibreOffice 会**假阴性**。要用 `renderer_probe`（内部就是
   `ppt to-pdf --dry-run`，约 3.2 s，不写盘）。
2. **装好即自动发现**：CLI 的候选表含 `%ProgramFiles%\LibreOffice\program\soffice.{com,exe}`
   ⇒ 本机无需设 `TOOLKNIT_LIBREOFFICE_PATH`（该变量仍可用于非标准安装位置）。

依赖缺失时**不假装成功**：`ppt_to_pdf` 原样透出上游的 `DEPENDENCY_MISSING` 并附修复指引
（上游 agent guide 原文要求「缺失时应提示用户安装或配置，不能假装转换成功」）。

---

## 5.1 · 已知边界：输出路径长度 >83 字符会让 LibreOffice 静默崩

**这是本单实测出来的、最不直观的一条**，写在这里以便用户不再踩：

`ppt_to_pdf` 的 `--output-dir` 绝对路径长度 **超过 83 字符**时，soffice 会
**静默 fail-fast**（`exit code 3221226505` = `0xC0000409`，**stderr 为空**）。
上游拿不到任何输出，只能报一句 `LibreOffice conversion failed: exit code …`。

受控实测（同一基准目录，只改输出目录长度，每档各跑 2 次）：

| `--output-dir` 绝对路径长度 | 结果 |
|---|---|
| 68 / 71 / 76 / 77 / 78 / 80 / 82 | ✅ 成功（12~15 s） |
| **83** | ✅ 成功 / 成功 |
| **84** | ❌ 失败 / 失败 |
| 85 / 86 / 95 / 102 / 109 | ❌ 失败（约 6 s 即崩） |

成因：上游把 `-env:UserInstallation=<output-dir>/.toolknit-libreoffice-XXXXXX/profile`
以 `file:///` URL 传给 soffice，**URL 跨过 127 字符即崩**
（`8(file:///) + 36(/…/profile) + 84(输出目录) = 128`）。

**与目录层级无关**（这一点专门做了对照）：

| 形状 | 长度 | 结果 |
|---|---|---|
| 长而浅（1 层，目录名 55 字符） | 109 | ❌ |
| 短而深（6 层） | 71 | ✅ |

⇒ **对策**：把工作区根放在短路径下（如 `C:\tk` 或 `/home/ubuntu/s`）。
Linux 服务器上工单要求的 `/home/ubuntu/scratchpad/research/<workspace>/toolknit-output`
约 60 字符，**安全**；Windows 开发机上 `%TEMP%\pytest-of-ASUS\pytest-N\…` 这类
深层临时目录则**会**踩到（测试因此专门用短临时目录，见 §7）。

本模块**不据此主动拒绝调用**——那是上游行为、会随版本变。**处置（244b 升级）**：
失败时除了把这条写进 `hint`，还会**自动做一次降级重试** ——
若失败**同时**满足〔① 输出路径 >83 ② `error_code == PROCESSING_FAILED`
③ 消息里带 `3221226505` / `0xC0000409`〕，就把这次渲染改到**短临时目录**跑，
成功后再把产物**搬回原落点**（`<工作区>/toolknit-output/`，目录布局与正常路径**完全一致**，
`manifest.json` 内的路径同步改写）。

⇒ 调用方看到的契约不变；返回体用 `path_fallback` 字段如实标注：
`{used, attempted, reason, temp_dir, from, to, moved[], manifest_rewritten}`。

| 开关 | 效果 |
|---|---|
| 默认（不设） | 开启自动降级重试 |
| `TOOLKNIT_NO_PATH_FALLBACK=1` | 关闭；失败原样透出 `PROCESSING_FAILED` |

**受控实测（2026-10-15，同一份 pptx + 同一个 91 字符的 `--output-dir`）**：

| 条件 | 结果 | `path_fallback` |
|---|---|---|
| 默认 | **ok=True**，产物落原落点 `…/toolknit-output/sample-<hex8>_ppt_to_pdf/` | `used=true`，`reason` 记明 91 > 83 + exit 3221226505 |
| `TOOLKNIT_NO_PATH_FALLBACK=1` | ok=False，`error_code=PROCESSING_FAILED` | `{"used": false, "attempted": false}` |

**上游若修复，`test_known_boundary_output_dir_length_limit` 会变红**，
届时删掉本节即可（降级重试会自然不再触发，属于无害冗余）。

## 5.2 · `pdf_text`：把工单原话的缺口补上（244b）

工单点名的 `pdf_extract_text` 在**上游不存在**（§2 偏差 #4）。244b 把它补上，
但**不自研 PDF 解析**——只做引擎编排，按顺序**惰性**导入：

| 优先级 | 引擎 | 给页码？ | 给坐标？ | 仓库 venv（**真运行时**） | 托管 venv（244b 的验证环境） |
|---|---|---|---|---|---|
| 1 | `pypdf` | ✅ 逐页 | ❌ | ✅ 6.19.0 | ✅ 6.16.1 |
| 2 | `pymupdf`（PyMuPDF） | ✅ 逐页 | ✅ `layout=true` 时行级 bbox | ❌ 未装 | ✅ 1.28.2 |
| 3 | `mcpserver/adapters/pdf2md_adapter`（Docling → MarkItDown） | ❌ **只给整篇 markdown** | ❌ | ⚠️ 见下（实走 markitdown） | ❌ 未装 |

> ⚠️ **可用性取决于「哪个解释器在跑」**——这不是配置项，而是环境事实。
> 244b 写「第三级不可用」时查的是**托管 venv**；244e 复核发现问题：**仓库自己的 venv 里
> `docling` 2.130.0 与 `markitdown` 0.1.8 本来就装着**（`pdf2md` extra，见 `pyproject.toml`）。
> ⇒ 真运行时 `available_chain = ['pypdf', 'adapter']`；托管 venv 是 `['pypdf', 'pymupdf']`。
> **两边都至少有两级可用**，只是级别不同。用 `list_tools()` 的 `pdf_text_engines` 现场确认。

**语义（刻意如此）**：

- `engine` 留空或 `auto` ⇒ 走降级链（当前可用者按序尝试）；
  **显式给引擎名 ⇒ 只用它**，不可用就报 `ENGINE_UNAVAILABLE`。
  *理由*：若显式 `pymupdf` 却悄悄跑了 `pypdf`，所有「换个引擎试试」的排查都失去意义。
- **三级全缺 ⇒ 明确报错 + 安装指引**，绝不返回空文本冒充成功。
- 截断只作用于**返回体**（`max_chars_per_page`，默认 4000；`0` 表示不截断）；
  **落盘文件永远完整**。
- 第三级（adapter）**会丢页码** ⇒ 返回体用 `page_numbers=false` +
  `page_number_note` 明说，调用方不必猜。

实测（托管 venv，3 页 / 114,618 B 夹具）：`page_count=3`、`total_chars=74,901`、
`pages[].chars=24,967`、落盘 `toolknit-output/sample.txt`。
`pymupdf` + `layout=true` 时页尺寸 `612×792`、行 `bbox` 如 `[72.0, 40.5, 299.9, 67.98]`。

实测（仓库 venv，244e 复核）：`auto` → `pypdf`，同样 **3 页 / 74,901 字符 / `page_numbers=true`**；
显式 `engine="adapter"` → **`ok=true`，耗时 63.0 s，`adapter_engine="markitdown"`，`page_numbers=false`**。

> ⚠️ **`adapter` 之所以能跑，是靠它自己的降级**：docling 在本机**失败**了 ——
> `Failed to load image processor from …\models--docling-project--docling-layout-heron\snapshots\…: Expecting value: line 1 column 1 (char 0)`
> （HuggingFace 模型快照损坏/为空）⇒ 适配器按设计回退到 MarkItDown。
> **别把「装了 docling」当成「docling 能用」**；要判它请直接看 `engine_detail.adapter_engine`
> 与日志里的 `Docling 失败，尝试 MarkItDown 降级`。
> 若要修 docling：清掉 `HF_HOME`（本机指向 `D:\ai\cache\huggingface`）下那个损坏的
> `models--docling-project--docling-layout-heron` 快照后重跑，它会重新下载。

> 本模块**唯一**引入第三方导入的文件就是 `pdf_text.py`，且全是函数体内惰性导入；
> `__init__` / `workspace` / `tools` / `server` 仍受「零第三方依赖」静态扫描约束。
> 这条缝由 `test_pdf_text_is_the_only_optional_seam` 单独把关（顶层只准标准库、
> 白名单**逐项相等**断言防漂移）。

## 5.3 · ffmpeg：装了也不算数（244b 实测坑）

`@toolknit/cli` 找 ffmpeg **只认三处**，且**拒绝符号链接**
（源码 `lib/ffmpeg-runtime.mjs::resolveFfmpeg`，`lstat().isSymbolicLink()` 为真即拒）：

1. `%APPDATA%\ToolKnit\ffmpeg\ffmpeg.exe`（桌面端托管目录）
2. `<包内>/vendor/ffmpeg/ffmpeg.exe`
3. `TOOLKNIT_FFMPEG_PATH`（要求是**普通文件**）

**PATH 上的 `ffmpeg` 不算**：它最后才退化成裸命令交给 `spawn(shell:false)`。
而 winget 在本机创建的 `%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe`
是 **0 字节填充文件**（符号链接创建失败 / 未开开发者模式）⇒ Node `spawn` 报 `EFTYPE`
⇒ `doctor` 报 `available=false / rc=5`。

⇒ 本机处置：用户级环境变量 `TOOLKNIT_FFMPEG_PATH` 指向 winget 装出来的**真实二进制**，
`doctor` 随即变成 `ok=true / rc=0 / missing=[]`。

反过来说：**`doctor` 的 ok/rc 不可用来判断「工具链是否健康」**——
它会被 ffmpeg 这一项单独拉黑，而本模块白名单工具一个都不用 ffmpeg。

### 5.3.1 · 244e 的处置：把 PATH 上的坏 shim 也修掉

244b 只用了 `TOOLKNIT_FFMPEG_PATH`（应用侧绕过），**PATH 本身仍是坏的** ——
任何不读该变量的程序（shell、node、其它工具）拿到的都是那个 0 字节文件。
244e 做了环境修复（**可逆**，未删除任何东西）：

| 动作 | 内容 |
|---|---|
| 停用坏 shim | `%LOCALAPPDATA%\Microsoft\WinGet\Links\{ffmpeg,ffplay,ffprobe}.exe`（均 **0 字节普通文件**，同目录正常的 winget 链接是 `SymbolicLink`）改名为 `*.exe.broken-winget-20261015` |
| 补 PATH | 把 `…\Gyan.FFmpeg…\ffmpeg-9.0.2-full_build\bin` 追加到**用户级** PATH |

**验证（不带任何环境变量）**：全新 PATH 下 `where ffmpeg` → 真二进制；
`node spawn('ffmpeg',['-version'])` → **rc=0**（这正是 CLI 的检测方式）；
CLI `doctor` → **`ok=true / rc=0 / ffmpeg.available=true`**。

> 若要回滚：把三个 `.broken-winget-20261015` 改回原名，并从用户 PATH 移除那一项即可。

### 许可

上游 `toolknit-desktop` 许可实测为 **Apache-2.0**（工单 §3.7 的硬性前置条件，已核）。
本模块**不 vendor 任何上游代码**，只按需经 `npx` 调用。

依赖树许可审计**已固化为可重跑脚本**（不要只留一句结论——结论会腐烂）：

```bash
python tools/toolknit_license_audit.py                 # 审计钉死版本
python tools/toolknit_license_audit.py --json-out x.json
python tools/toolknit_license_audit.py --strict        # 有 copyleft/无声明则非零退出
```

实测（2026-10-15，`@toolknit/cli@2.3.1`）：**真包 109 个**，0 强 copyleft、0 弱 copyleft。

| 判定 | 个数 | 说明 |
|---|---|---|
| `PERMISSIVE` | 107 | MIT / ISC / Apache-2.0 / 0BSD / BSD-3-Clause / Unlicense 等 |
| `ELECTABLE-PERMISSIVE` | 1 | `jszip@3.10.1` = `(MIT OR GPL-3.0-or-later)` ⇒ **可选 MIT 分支，不传染** |
| `UNKNOWN` | 1 | `buffers@0.1.1` —— **无任何许可声明**（见下） |

**`buffers@0.1.1` 的处置**：引入链 `exceljs@4.4.0 → unzipper@0.10.14 → binary@0.3.0 → buffers@0.1.1`，
**只在 Excel / 表格路径上**；本模块白名单**不含**任何表格类工具，CLI 驱动层也不出现
表格关键词 ⇒ 这条链**不会被走到**，且本仓**不 vendor、不 redistribute**。
这个判断不是留在报告里的一句话——`test_whitelist_never_touches_the_table_path`
让它在每次 CI 里被**重新证明**。

> ⚠️ 对工单244 报告 §7「112 个包」的修正：那次计数用的是「``node_modules`` 下所有
> ``package.json``」，把 3 个**非包清单**（`chart.js/auto/`、`chart.js/helpers/`
> 两个子路径 shim，以及 `music-tempo/docs/`）也算了进去。按 npm 布局规则
> （``node_modules/<name>/package.json``，scope 包为两段）过滤后是 **109 个真包**；
> 且本次审计新增「磁盘枚举 vs 依赖树**集合**一致」校验，实测两侧都是 109、差集为空。

> 署名口径：这是**第三方工具接入**。文档与提交信息里写「来自 toolknit v2.3.1」，
> **不**写「ToolKnit 是本仓组件」。

---

## 6 · 接线方式（仓内原生契约）

对齐同族先例（`mcpserver/rf_workflow/server.py` 的 `RfWorkflowBridge`、
`mcpserver/antenna_sim/tools.py` 的 `AntennaSimBridge`）：

```
mcpserver/toolknit_mcp/agent-manifest.json   (Format A: entryPoint.{module,class})
        ↓ mcpserver/mcp_registry.py :: scan_and_register_mcp_agents()   ← glob **/agent-manifest.json
        ↓ _resolve_entrypoint() → import mcpserver.toolknit_mcp.server → ToolknitBridge
MCPManager.unified_call(task)
        ↓ await bridge.handle_handoff(task) -> JSON 字符串
tools.run_cli()  →  subprocess(["npx","-y","@toolknit/cli@2.3.1", …], shell=False)
```

**不需要改任何既有文件**（不碰 `mcp_assembly` / `mcp/services` 路由健康检查）。

`handle_handoff` 的返回形态与 242/243 完全一致：

```json
{"status": "success" | "error", "message": "…", "data": { …工具原始结果… }}
```

## 7 · 手工复现（每个 PoC 必须可观测）

```bash
# 环境体检
python -m mcpserver.toolknit_mcp.server version
python -m mcpserver.toolknit_mcp.server renderer-probe
python -m mcpserver.toolknit_mcp.server doctor
python -m mcpserver.toolknit_mcp.server list-tools

# 四个 PoC 能力
python -m mcpserver.toolknit_mcp.server palette      --image <abs.png> --count 5
python -m mcpserver.toolknit_mcp.server pdf-inspect  --pdf <abs.pdf>
python -m mcpserver.toolknit_mcp.server pdf-compress --pdf <abs.pdf> --level high
python -m mcpserver.toolknit_mcp.server ppt-to-pdf   --pptx <abs.pptx>
python -m mcpserver.toolknit_mcp.server pdf-text     --pdf <abs.pdf> --engine auto

# 许可审计（可重跑，见 §5 许可）
python tools/toolknit_license_audit.py --strict

# 测试与 lint
python -m pytest tests/test_toolknit_mcp.py -q
python -m ruff check mcpserver/toolknit_mcp tests/test_toolknit_mcp.py tools/toolknit_license_audit.py
```
