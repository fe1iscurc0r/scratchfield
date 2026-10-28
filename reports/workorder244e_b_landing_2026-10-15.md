# 工单 244e 完工报告 · 244/244b 的「未落地」四项（B 组）落地

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `26bde1d18c`
> 前置：244c（ci.yml 记录）→ 244d（ruff 314→0）已合并
> 触发：用户「B 你尝试落地吧」（B = 244/244b 报告 §9 的四个未落地项；C 组交接件明确跳过）
> 变更文件：**5 个**（2 新增 + 3 修改）+ 两处**环境修复**（不进仓）

---

## §0 · 四项对照

| # | 244/244b 留的原话 | 本单结论 | 性质 |
|---|---|---|---|
| B-1 | `docling`/`markitdown` 未装 ⇒ `pdf_text` 第三级不可用 | ⚠️ **原判断有误**：查错了解释器。真运行时两级可用（`pypdf` + `adapter`）；已改正文档 | 记录纠正 |
| B-2 | `buffers@0.1.1` 无许可声明，需先确认 | ✅ 做成**已受理清单**（带理由 + 指认守护测试）⇒ `--strict` 从「永远红」变为**可用** | 代码 + 测试 |
| B-3 | winget 的 3 个 0 字节 `ffmpeg*.exe` 占位文件仍在 | ✅ **已修复环境**（可逆）：停用坏 shim + 补 PATH；无环境变量也 `doctor ok=true` | 环境修复 |
| B-4 | 建议定期巡检上游版本 | ✅ 建成**每周一 09:00 的自动化**（发现新版本自动开 Issue） | 自动化 |

---

## §1 · B-1：**原判断有误**（查错了解释器）

244b 写「第三级不可用」时，查的是**托管 venv**（`~/.workbuddy/binaries/python/envs/default`，
本项目跑测试用的隔离环境）。244e 复核了**仓库自己的 venv**（`D:/my git/scratchpad/.venv`，Python 3.12.13）：

| 引擎 | 仓库 venv（**真运行时**） | 托管 venv（244b 的验证环境） |
|---|---|---|
| `pypdf` | ✅ **6.19.0** | ✅ 6.16.1 |
| `pymupdf` | ❌ 未装 | ✅ 1.28.2 |
| `markitdown` | ✅ **0.1.8** | ❌ 未装 |
| `docling` | ✅ **2.130.0**（但见下） | ❌ 未装 |
| `available_chain` | **`['pypdf', 'adapter']`** | `['pypdf', 'pymupdf']` |

⇒ **两边都至少两级可用，只是级别不同**；且 `pdf2md` extra（`docling` + `markitdown`）
**本来就在 `pyproject.toml` 里、也本来就装在仓库 venv 里**。244b 的「未落地」是**误报**。

### 1.1 端到端实测（仓库 venv + main 代码树，3 页 / 114,618 B 夹具）

| 调用 | 结果 |
|---|---|
| `auto` | `ok=true`，`engine=pypdf`，**3 页 / 74,901 字符 / `page_numbers=true`**，落盘 74,956 B |
| `engine="adapter"` | `ok=true`，耗时 **63.0 s**，**`adapter_engine="markitdown"`**，`page_numbers=false`（如设计所述会丢页码） |

### 1.2 ⚠️ 顺带抓到的真实问题：**docling 装了但不能用**

`engine="adapter"` 的日志里写着：

```
[pdf2md] Docling 失败，尝试 MarkItDown 降级:
  docling: RuntimeError: Failed to load image processor from
  D:\ai\cache\huggingface\hub\models--docling-project--docling-layout-heron\snapshots\8f39ad3c…:
  Expecting value: line 1 column 1 (char 0)
```

⇒ **HuggingFace 模型快照损坏/为空**（JSON 解析失败），适配器按设计回退到 MarkItDown。
**「装了 docling」≠「docling 能用」**。要判它请看 `engine_detail.adapter_engine` 与日志里的降级行。
修法：清掉 `HF_HOME`（本机 `D:\ai\cache\huggingface`）下那个损坏的
`models--docling-project--docling-layout-heron` 快照后重跑（会自动重下）。

> **本单不改环境**：这属于「用户机器上的模型缓存」问题，且 docling 只是**质量更好**的一级，
> 有 markitdown 兜底 ⇒ 记录 + 在 README 写明修法，不擅自动用户的缓存目录。

---

## §2 · B-2：把「已受理例外」落成清单，让 `--strict` 可用

244b 引入的审计脚本有个**设计缺陷**：`buffers@0.1.1`（无许可声明）会让 `--strict` **永远失败**
⇒ 没人会用它 ⇒ 这个检查等于没有（「狼来了」）。

本单加了 `ACCEPTED_EXCEPTIONS`（`name@version -> 理由`），并且：

1. **每条必须写清 ① 为什么可接受 ② 哪个测试守着这条边界**（不能是口头豁免）；
2. `risky()` 只报**未受理**项 ⇒ `--strict` 只对**新增**未知项失败；
3. 命中的受理项由 `accepted_note()` 单独打印（带完整理由），**不隐藏**；
4. ⚠️ 上游换版本后 key 会变 ⇒ 受理自动失效、`--strict` 重新报警（**这是有意的**）。

**实测**：`python tools/toolknit_license_audit.py --strict` → **EXIT=0**，
输出仍打印 `ℹ️ 已受理：buffers@0.1.1（UNKNOWN）⇒ …（完整理由）`；
审计本身仍自洽（**磁盘枚举 109 = 依赖树 109，集合一致**）。

### 2.1 新增离线单测 `tests/test_toolknit_license_audit.py`（30 用例）

审计要联网跑 `npm install` ⇒ **不能进 CI**；但它的**判定逻辑全是纯函数**，
而 244b 第一版正好在三处栽过 ⇒ 把这三条钉成**离线**回归：

| 用例组 | 守什么 |
|---|---|
| `test_classify_*` | `OR` 里存在宽松分支 ⇒ `ELECTABLE-PERMISSIVE`（**不传染**）；`AND` 取最严；认不出 ⇒ `UNKNOWN` |
| `test_is_package_manifest` | 按 npm 布局只认**真包**；包内子路径 shim（`chart.js/auto/`、`music-tempo/docs/`）不算 |
| `test_accepted_exception_*` | 已受理不进 `risky()`；但**新增**未知/强 copyleft **照旧报**；集合不一致永远报 |
| `test_accepted_list_entries_carry_reason_and_guard` | 受理清单每条必须 >60 字理由 **且指认 `test_`** —— 防「口头豁免」 |
| `test_audit_script_is_pure_stdlib_offline` | 脚本必须纯标准库 |

**不联网、不调 npm、0.04 s 跑完。**

---

## §3 · B-3：把 PATH 上的坏 shim 一起修掉（可逆）

244b 只做了**应用侧绕过**（`TOOLKNIT_FFMPEG_PATH`），**PATH 本身仍是坏的** ——
任何不读该变量的程序（shell、node、其它工具）拿到的都是那个 0 字节文件。

**已做的环境修复（未删除任何东西）**：

| 动作 | 内容 |
|---|---|
| 停用坏 shim | `%LOCALAPPDATA%\Microsoft\WinGet\Links\{ffmpeg,ffplay,ffprobe}.exe`（三个都是 **0 字节普通文件**；同目录正常的 winget 链接是 `SymbolicLink`，如 `CompactGUI.exe`）⇒ 改名 `*.exe.broken-winget-20261015` |
| 补 PATH | `…\Gyan.FFmpeg…\ffmpeg-9.0.2-full_build\bin` 追加到**用户级** PATH（长度 1037 → 1169） |

**验证（全程不带 `TOOLKNIT_FFMPEG_PATH`）**：

| 检查 | 结果 |
|---|---|
| 全新 PATH 下 `where ffmpeg` | ✅ 指向 `…\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe` |
| `ffmpeg -version` | ✅ `9.0.2-full_build` |
| **`node spawn('ffmpeg',['-version'])`**（CLI 的检测方式） | ✅ **rc = 0** |
| CLI `doctor` | ✅ **`ok=true / rc=0 / ffmpeg.available=true`** |

> 回滚：三个 `.broken-winget-20261015` 改回原名 + 从用户 PATH 移除那一项。
> `TOOLKNIT_FFMPEG_PATH`（244b 设的）**保留**作双保险 —— CLI 会先看它。

---

## §4 · B-4：上游版本漂移巡检（自动化）

| 项 | 值 |
|---|---|
| 名称 | toolknit 上游版本漂移巡检 |
| ID | `3648bcc9-916e-4a92-8b56-f85e64c7d660` |
| 频率 | **每周一 09:00** |
| 行为 | 取 `npm view @toolknit/cli version` ↔ 从 main 的 `tools.py` 解析钉死版本；**不同**才用 REST API 开 Issue（含新旧版本、发布时间、「升级前必跑」清单、83 字符边界与许可结论需复核的提醒）；**相同**则只报告「无漂移」 |

> 当前状态：latest = 钉死 = **2.3.1**，无漂移。

---

## §5 · 本单的仓内变更（5 文件）

| 文件 | 变更 |
|---|---|
| `tools/toolknit_license_audit.py` | 新增 `ACCEPTED_EXCEPTIONS` + `accepted_note()`；`risky()` 只报未受理；CLI 文案 |
| `tests/test_toolknit_license_audit.py` | **新增**：30 个离线用例 |
| `mcpserver/toolknit_mcp/README.md` | §5.2 引擎表改为**按解释器**两列 + docling 失败实证 + 修法；新增 §5.3.1（PATH 修复，含回滚） |
| `mcpserver/toolknit_mcp/requirements.txt` | 引擎表同上；纠正「第三级不可用」的表述 |
| `reports/workorder244e_b_landing_2026-10-15.md` | 本文件 |

行尾：5 个文件**与各自真 blob 口径逐一致**（全 LF）。

---

## §6 · 未落地 / 需接手

1. **docling 的 HF 模型快照损坏**（§1.2）—— 修它要动用户的缓存目录（`D:\ai\cache\huggingface`），
   **本单未动**。有 markitdown 兜底，功能不受影响；只是拿不到 docling 的版面/表格质量。
2. **B-3 的两个环境改动是「用户机器」级别的**（PATH、改名三个文件）——
   不进仓、不随仓库版本走。换机器/重装需重做（步骤见 README §5.3.1）。
3. **C 组交接件按用户指示跳过**（239/240/241 的 cron 锚点、`AGENT_AUDIT_DIR`、
   `AGENT_GOVERNANCE` 令牌、`HERMES_AGENT_ID_KEY`、台账 241 号混用）。
