# 工单 244b 完工报告 · toolknit 收尾补强

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥
> 日期：**2026-10-15** · 基线：main `ce466bbc88`（工单244 的 squash 合并点）
> 性质：**补强单** —— 把工单244 交付时如实留下的四个「未落地」项全部做掉
> 一句话：`pdf_extract_text` 缺口用**仓内引擎**补上、LibreOffice 的长路径崩溃**自动绕开**、
> ffmpeg 装上并让 `doctor` 真正看见、许可审计**固化为可重跑脚本**；另修正 244 遗留的 3 处计数错误。

---

## §0 · 交付事实（先给可核对的数）

| 项 | 值 |
|---|---|
| 分支 | `feat/w244b-toolknit-hardening` |
| 变更文件 | **10 个** = 新增 **2**（`pdf_text.py` / `tools/toolknit_license_audit.py`）+ 修改 **8** |
| 交付树内文件 | 17 个（含 4 个二进制夹具与 244 的既有报告，与 main **逐字节一致、未上传**） |
| 行尾 | 变更的文本文件**全 LF**（二进制夹具无行尾概念） |
| `pytest tests/test_toolknit_mcp.py -q` | **88 passed / 1 skipped / 0 failed**（146.53 s） |
| `ruff check`（242/243/244 同款配置） | **All checks passed!** |
| 白名单工具 | 8 → **9**（新增 `pdf_text`） |
| `doctor` | `ok=false / rc=5 / missing=[ffmpeg]` → **`ok=true / rc=0 / missing=[]`** |
| 上游版本漂移 | `npm view @toolknit/cli version` = **2.3.1**（与钉死版一致，无漂移） |

> 唯一 skipped 的是 `test_pdf_text_adapter_engine_loses_page_numbers_if_available` ——
> 本机未装 `docling`/`markitdown`，`pdf_text` 第三级不可用，用例**如实跳过**而非假装通过。

---

## §1 · 四项「未落地」→ 处置对照

| # | 244 报告 §9 的原话 | 244b 处置 | 凭据 |
|---|---|---|---|
| 1 | 「`pdf_extract_text` 不存在 ⇒ 走 `pdf2md_adapter`，或另立工单」 | 新增 `pdf_text`，用**仓内引擎**承接 | 3 页 / **74,901** 字符 / 落盘 `sample.txt`（74,956 B） |
| 2 | 「83 字符边界刻意不拦；要在工具层拦需新立工单」 | **自动降级重试**（仍带显式开关） | 同 91 字符路径：开⇒ ok=True / 关⇒ `PROCESSING_FAILED` |
| 3 | 「`ffmpeg` 未安装」 | 装 **9.0.2**，并定位到 CLI 真正认的入口 | `doctor` 由 `rc=5` 变 `rc=0`、`missing=[]` |
| 4 | 「`buffers@0.1.1` 无许可声明，需先确认」 | **固化为可重跑审计** + 把判断做成断言 | 真包 **109**、0 强/弱 copyleft；表格路径断言进 CI |

---

## §2 · `pdf_text`：补缺口，但不虚构接口

工单原话是「PDF 文本字符串 + 页码位置元数据」。上游**确实没有**该能力（244 预检已实证）。
244b 的做法是**引擎编排**（同族纪律：不写第二套解析）：

| 优先级 | 引擎 | 页码 | 坐标 | 本机实测 |
|---|---|---|---|---|
| 1 | `pypdf` | ✅ 逐页 | ❌ | ✅ **6.16.1** |
| 2 | `pymupdf`（PyMuPDF） | ✅ 逐页 | ✅ `layout=true` 行级 bbox | ✅ **1.28.2** |
| 3 | `pdf2md_adapter`（Docling → MarkItDown） | ❌ 只给整篇 markdown | ❌ | ❌ 未装 |

### 2.1 三条刻意语义（各有回归）

1. **`auto` 走降级链；显式给名 ⇒ 只用它**。理由：显式 `pymupdf` 却悄悄跑 `pypdf`，
   会让所有「换个引擎试试」的排查**失真**。不可用即 `ENGINE_UNAVAILABLE`（不静默替换）。
2. **三级全缺 ⇒ 明确报错 + 安装指引**，绝不返回空文本冒充成功。
3. **截断只作用于返回体**（`max_chars_per_page`，默认 4000；0=不截断）；**落盘文件永远完整**。
   第三级会丢页码 ⇒ 用 `page_numbers=false` + `page_number_note` 明说。

### 2.2 实测值（3 页 / 114,618 B 夹具）

| 项 | 值 |
|---|---|
| `page_count` | **3**（页索引 1/2/3） |
| 每页 `chars` | **24,967**（pypdf）/ 24,968（fitz，差 3 字节是引擎口径） |
| `total_chars` | **74,901** |
| 落盘 | `toolknit-output/sample.txt`，**74,956 B**（含页分隔头） |
| `pymupdf` + `layout=true` | 页尺寸 **612×792**；行 bbox 例 `[72.0, 40.5, 299.9, 67.98]` |
| `engine=adapter`（未装） | `ok=false` / `ENGINE_UNAVAILABLE`，错误里列出**当前可用**引擎 |

### 2.3 依赖缝的守卫拆成三条（防「声明超出守卫范围」）

| 用例 | 守什么 |
|---|---|
| `test_cli_layer_is_pure_stdlib` | `__init__`/`workspace`/`tools`/`server` **任何位置**都不得有第三方 |
| `test_top_level_imports_are_stdlib_only` | **任何**文件的**顶层**只准标准库/兄弟模块（否则「没装也能用」是谎话） |
| `test_pdf_text_is_the_only_optional_seam` | 第三方只准在 `pdf_text.py`、只准惰性、只准白名单，且**逐项相等**断言防两边漂移 |

adapter 按**文件路径**加载（`importlib.util.spec_from_file_location`），
不经 `import mcpserver.adapters` —— 那个包的 `__init__` 带注册副作用，而这里只要它两个纯函数。

---

## §3 · 长输出路径：由「只写 hint」升级为「自动绕开」

244 实测：`--output-dir` 绝对路径 **>83 字符** ⇒ soffice **静默 fail-fast**
（`exit 3221226505` = `0xC0000409`，stderr 为空）。244 只写 `hint`；244b 追加**一次自动降级重试**。

**触发条件（四条同时，刻意保守）**：① 路径 >83 ② `error_code == PROCESSING_FAILED`
③ 消息含 `3221226505`/`0xC0000409` ④ 未设 `TOOLKNIT_NO_PATH_FALLBACK`。
宁可漏救也不误判 —— 误判会把一次真失败变成两次。

**动作**：短临时目录渲染 → 成功后把 `<name>_ppt_to_pdf/` **整个搬回** `out_root`
→ 重写 `manifest.json` 内路径（递归字符串替换，best-effort）→ 清临时目录。
**契约不变**：产物位置与布局与正常路径完全一致。

### 受控实测（同一 pptx、同一个 **91** 字符的 `--output-dir`，只改开关）

| 条件 | 结果 | 原落点内容 | `path_fallback` |
|---|---|---|---|
| 默认（开） | **ok=True** | `toolknit-output/sample-<hex8>_ppt_to_pdf/{<hex8>.pdf, manifest.json}` | `used=true, attempted=true, manifest_rewritten=true` |
| `TOOLKNIT_NO_PATH_FALLBACK=1` | ok=False | 空 | `{"used": false, "attempted": false}` |

`reason` 原文：`输出路径 91 字符 > 实测上限 83，且 soffice 静默 fail-fast（exit code 3221226505 / 0xC0000409）`。

### 留证用例改成**三行受控矩阵**

`test_known_boundary_output_dir_length_limit`：

| 行 | 长度 | 降级开关 | 期望 |
|---|---|---|---|
| 1 | 83 | 关 | 成功（界内） |
| 2 | **84** | **关** | **失败 + `PROCESSING_FAILED` + hint 含「83」**（上游边界留证） |
| 3 | 84 | 开（默认） | 成功 + `path_fallback.used=true`（我们的缓解） |

⚠️ 第 2 行**必须显式关掉降级**。不加开关，这条就变成「测我们自己的缓解」，
而不是「留证上游的边界」—— 两者必须**并排存在**才是同一个受控实验的两个臂。

---

## §4 · ffmpeg：装了也不算数（实测坑）

`@toolknit/cli` 找 ffmpeg **只认三处**，且**拒绝符号链接**
（源码 `lib/ffmpeg-runtime.mjs::resolveFfmpeg`，`lstat().isSymbolicLink()` 为真即拒）：

1. `%APPDATA%\ToolKnit\ffmpeg\ffmpeg.exe`（桌面端托管目录）
2. `<包内>/vendor/ffmpeg/ffmpeg.exe`
3. `TOOLKNIT_FFMPEG_PATH`（要求是**普通文件**）

**PATH 上的 `ffmpeg` 不算** —— 它最后才退化成裸命令交给 `spawn(shell:false)`。
而 winget 在本机建的 `%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe`
是 **0 字节填充文件**（符号链接创建失败 / 未开开发者模式；同目录的 `CompactGUI.exe`
是正常的 `lrwxrwxrwx`）⇒ Node `spawn` 报 **`EFTYPE`** ⇒ `doctor` 报 `available=false / rc=5`。

### 溯源实测

| 步骤 | 结果 |
|---|---|
| `winget install Gyan.FFmpeg` | 成功，版本 **9.0.2**（`full_build`，`--enable-static`） |
| 真二进制 | `…\Gyan.FFmpeg…\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe`，**227,823,104 B** |
| 静态自包含验证 | 复制到空临时目录后 `-version` 正常输出版本行 ✅ |
| 裸 `ffmpeg` 走 PATH | ❌ `spawn EFTYPE`（0 字节占位文件） |
| 托管目录方案 | ⚠️ 被 `regularFile()` 的 `!isSymbolicLink` 挡住；放真文件要再拷 **217 MB** ⇒ 不划算 |
| **最终处置** | 用户级环境变量 **`TOOLKNIT_FFMPEG_PATH`** 指向真二进制（零拷贝、零删除、零 PATH 改动） |
| 效果 | `doctor`：`ok=false/rc=5/missing=[ffmpeg]` → **`ok=true/rc=0/missing=[]`** |

**顺带确认既有结论**：`doctor` 的 ok/rc **不能**当「工具链是否健康」用 ——
它会被 ffmpeg 这一项单独拉黑，而本模块白名单工具**一个都不用 ffmpeg**。

---

## §5 · 许可审计固化 + **对 244 报告 §7 的修正**

新增 `tools/toolknit_license_audit.py`（纯标准库、`--json-out`、`--strict`）。
理由：**一次性的结论会腐烂**，上游发一版依赖树就可能变 ⇒ 结论必须能被重跑复算（REFERENCE §R12）。

实测（2026-10-15，`@toolknit/cli@2.3.1`）：**真包 109**，**0 强 copyleft、0 弱 copyleft**。

| 判定 | 个数 | 明细 |
|---|---|---|
| `PERMISSIVE` | 107 | MIT / ISC / Apache-2.0 / 0BSD / BSD-3-Clause / Unlicense 等 |
| `ELECTABLE-PERMISSIVE` | 1 | `jszip@3.10.1` = `(MIT OR GPL-3.0-or-later)` ⇒ 可选 MIT 分支，**不传染** |
| `UNKNOWN` | 1 | `buffers@0.1.1` —— 无任何许可声明 |

### 5.1 ⚠️ 修正 244 报告的「112 个包」

244 用的是「`node_modules` 下所有 `package.json`」，把 **3 个非包清单**也算进去了：

| 被误算的 | 是什么 |
|---|---|
| `chart.js/auto/package.json` | chart.js 的**子路径 shim**（只写 `{"type":"module"}`） |
| `chart.js/helpers/package.json` | 同上 |
| `music-tempo/docs/package.json` | 包内**文档目录**的清单（还声明着旧版本 1.0.1） |

按 npm 布局规则过滤（`node_modules/<name>/package.json`，scope 包两段）后是 **109 个真包**。

### 5.2 脚本第一版的两个**自身缺陷**（已修）

| # | 缺陷 | 后果 | 修法 |
|---|---|---|---|
| 1 | 未过滤子路径 shim | 凭空多出 `chart.js-auto@` / `chart.js-helpers@` 这种**空版本**条目 | 新增 `_is_package_manifest()` 按 npm 布局判定 |
| 2 | 用依赖树**节点数**做交叉校验 | **恒假警报**（同包在树里因嵌套重复出现，实测 **205 节点 vs 112 包**） | 改为比 `name@version` **集合差**（`only_on_disk` / `only_in_tree`） |
| 3 | 分类器朴素子串命中 | `(MIT OR GPL-3.0-or-later)` 被误判强 copyleft | 新增 `ELECTABLE-PERMISSIVE`（`OR` 里存在宽松分支 ⇒ 不传染） |

修后：磁盘枚举 **109** = 依赖树 **109**，集合差为空（`sets_match=true`）。

### 5.3 `buffers@0.1.1`：从「口头结论」升级为「可执行断言」

引入链 `exceljs@4.4.0 → unzipper@0.10.14 → binary@0.3.0 → buffers@0.1.1` **只在 Excel 路径上**；
本模块白名单不含表格类工具，`tools.py` 也不出现表格关键词 ⇒ 这条链**不会被走到**，
且本仓**不 vendor、不 redistribute**。

`test_whitelist_never_touches_the_table_path` 让这个判断**每次 CI 都被重新证明**，
而不是留在报告里的一句话。

---

## §6 · 本单自己修掉的问题（全部已回归）

| # | 问题 | 根因 | 判定 |
|---|---|---|---|
| 1 | `test_known_boundary_output_dir_length_limit[84-False]` 变红 | **我的降级把 84 那一档救活了** ⇒ 留证用例观察不到上游行为 | **测试前提需要更新**；改为三行矩阵，第 2 行显式关降级 |
| 2 | `_module_root` 把 `import pymupdf  # type: ignore` 判成模块名 `'pymupdf # type: ignore'` | 未剥行尾注释 | **我的 bug** |
| 3 | `_STDLIB_OK` 漏了 `sys` ⇒ 审计脚本误报第三方 | 白名单不全 | **我的 bug** |
| 4 | `data["outputs"]`（相对**工作区**）与 `landed`（相对**落点**）直接比较 | 比较口径不同 | **我的 bug** |
| 5 | 交付目录混入 `ruff_cache/` 与 `__pycache__/` | 我在 deliver 目录里跑过 lint / `py_compile` | **卫生问题**；交付前清理，并复查 17 文件 |
| 6 | PR 正文里 `pdf_text.py` / 审计脚本的字节数是我**手填**的（13,227 / 11,626） | 没先量就写 | **违反「数字要能复算」**；改为实测 18,762 / 14,141 |

### 6.1 顺带修正 244 遗留的计数错误

| 位置 | 244 写的 | 实际 | 说明 |
|---|---|---|---|
| 集成图 §6 标题 | 「**18** 文件」 | **14** | 疑为从 243 文案（18 文件）复制而来 |
| 集成图 §5 | 「只白名单 **8** 个」 | **9**（244b 后） | 新增 `pdf_text` |

> 同一类错误我在写本单集成图 §7.6 时**又犯了一次**（写「修改（7）」而实际列了 8 个文件），
> 已自查抓出并改掉。因此本单同时给 LF 守卫加了**计数断言**
> （`test_deliverable_is_lf_only` 现断言交付文本文件恰为 **13** 个），
> 增删交付文件而忘同步文档 ⇒ **先红**。

---

## §7 · 未落地 / 需接手

1. **`docling` / `markitdown` 未安装** ⇒ `pdf_text` 第三级在本机不可用（前两级可用）。
   **这是如实状态，不是缺陷**：需要 OCR / 表格时按 `requirements.txt` 的引擎表安装即可。
2. **`buffers@0.1.1` 仍无许可声明** —— 本模块不走该链（有回归守着）；
   若将来要暴露表格能力，需先与沈遥确认。
3. **winget 的 3 个 0 字节 `ffmpeg*.exe` 占位文件仍在** `%LOCALAPPDATA%\Microsoft\WinGet\Links\`。
   本模块不受影响（走 `TOOLKNIT_FFMPEG_PATH`），但**任何 PATH 方式的 `ffmpeg` 调用都会失败**。
   修它需删占位文件或开开发者模式重装 —— 属于**环境决策，未擅动**（未删除用户系统上的任何文件）。
4. **上游漂移巡检**：2026-10-15 实测 npm latest 仍为 **2.3.1**（无漂移）。
   升级前请重跑本套用例 + `tools/toolknit_license_audit.py`。

---

## §8 · 复现方式

```bash
# 工具与引擎状态
python -m mcpserver.toolknit_mcp.server list-tools          # 9 工具 + pdf_text_engines
python -m mcpserver.toolknit_mcp.server pdf-text --pdf <abs.pdf> --engine auto
python -m mcpserver.toolknit_mcp.server pdf-text --pdf <abs.pdf> --engine pymupdf --layout
python -m mcpserver.toolknit_mcp.server doctor              # ffmpeg 现应为 available

# 许可审计（可重跑）
python tools/toolknit_license_audit.py --strict

# 测试与 lint
python -m pytest tests/test_toolknit_mcp.py -q
python -m ruff check mcpserver/toolknit_mcp tools tests
```

⚠️ 跑 PPT 相关测试前，确保工作区（及 `%TEMP%`）路径**短于 83 字符**；
若要观察上游边界本身，设 `TOOLKNIT_NO_PATH_FALLBACK=1`。
