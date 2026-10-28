# 工单 244i 报告 · 修复 244d 引入的 nuwa 同步漂移（+ ruff exclude 收口）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-15** · 基线：main `4e4e90f216bb`
> 触发：全量测试套件跑出 **16 failed / 1414 passed**；与**今日开工前基线**（`9c7d2dcfbd`）
> 同批对比后，**15 个为既有/环境问题，只有 1 个是今天引入的** —— 即本单要修的。
> 变更：**1 删改回 3 文件 + `pyproject.toml` 加一行 exclude + 本报告**

---

## §0 · 一句话

244d 的 `ruff --fix` 顺手改了 `github_haul/nuwa-skill/scripts/` 里的 3 个文件，
但它们与 `skills/huashu-nvwa/scripts/` 有**逐字节同步契约**
（`tests/test_spec03_phase34.py::test_nuwa_references_and_scripts_synced` 断言两侧
`read_bytes()` 相等），而 `skills/` 在 ruff 的 exclude 里**没被一起改**
⇒ 两份拷贝漂移 ⇒ 同步测试红。
修复：**3 文件回滚到 244d 之前的字节**（= 镜像当前字节，sha 逐一致）+
**`github_haul` 加入 ruff exclude**（带注释说明契约），`ruff check .` 维持 **0 errors**。

---

## §1 · 怎么定位的（全量套件的 16 个失败 → 1 个真回归）

| 步骤 | 结果 |
|---|---|
| 全量套件（当前 main `4e4e90f216bb`，仓库 venv） | **16 failed / 1414 passed / 4 skipped**（8m28s） |
| 同一批测试文件在**今日开工前基线** `9c7d2dcfbd` 上重跑 | **15 failed / 132 passed** |
| 差集 | **只在当前失败 = 1**：`test_spec03_phase34.py::test_nuwa_references_and_scripts_synced`；只在基线失败 = 0；两边都失败 = **15（既有）** |

⇒ 与今天约 65 个文件的改动量相比，**只引入了 1 个回归**，且已定位、已修。

---

## §2 · 根因

`skills/huashu-nvwa/` 是 `github_haul/nuwa-skill/` 的**镜像**，契约是**逐字节一致**
（测试对 `references/` 与 `scripts/` 逐文件 `read_bytes()` 相等断言）。

- `skills/` 在 ruff 的 `exclude` 里 ⇒ 244d 的 `--fix` **没碰它**；
- `github_haul/` **不在** exclude 里 ⇒ 244d 的 `--fix` 改了上游侧 3 个文件（I001 排序）；
- ⇒ 两侧漂移，同步契约破。

**结构性教训**：对一个「与被 exclude 的镜像有逐字节契约」的目录做 lint，
**必然**造成漂移 —— 这不是「少改一个文件」的疏忽，而是 exclude 清单**缺了一项**。

---

## §3 · 修复

### 3.1 三文件回滚（恢复逐字节一致）

`github_haul/nuwa-skill/scripts/{merge_research,quality_check,srt_to_transcript}.py`
恢复为 244d 之前的字节（= 镜像当前字节）。

**验证（权威判据 = blob 对 blob，不是工作树）**：

| 文件 | 恢复后上游 blob | 镜像 blob | 一致 |
|---|---|---|---|
| merge_research.py | `352d84b4…` | `352d84b4…` | ✅ |
| quality_check.py | `0ce769d2…` | `0ce769d2…` | ✅ |
| srt_to_transcript.py | `c5cedfd0…` | `c5cedfd0…` | ✅ |

### 3.2 `pyproject.toml`：`github_haul` 加入 exclude

```toml
exclude = [
    "NEKO",
    "skills",
    "github_haul",  # 上游素材，与 skills/huashu-nvwa 有逐字节同步契约（见 tests/test_spec03_phase34.py）；
                    # 244d 曾 lint 它导致两侧漂移 —— 见 reports/workorder244i_*.md
    ...
]
```

理由：`github_haul/nuwa-skill` 是**上游素材**，与被 exclude 的镜像有逐字节契约
—— 和 `NEKO`/`vendor`/`skills` 被排除是同一类理由。**不排除它，这个契约迟早再破一次。**

---

## §4 · 验证

| 项 | 结果 |
|---|---|
| `ruff check .`（新 exclude） | **All checks passed**（0 errors 维持） |
| nuwa 同步测试 | **blob 级逐一致** ✅（见 §3.1）；沙盒里的 `full/` 是 `git archive` 提出来的 **CRLF** 树，上游侧被我写成 LF ⇒ 该测试在沙盒里仍显示 EOL 差异（`At index 22: b'\n' != b'\r'`），**纯提取假象** |
| 模拟真实 checkout（两侧同 EOL） | **一致 = True** ✅ |
| 结构守卫四件套 | **60 passed** ✅ |

> ⚠️ 又一次验证了 §R16/R9 的教训：**`git archive` 提出来的树不是 blob 忠实的**
> （本仓 `eol=crlf` ⇒ 全部 CRLF），任何「读工作树文件做字节断言」的测试
> 在 archive 树上都会失真。权威判据永远是 `git cat-file blob` / API base64。

---

## §5 · 其余 15 个失败 = 既有/环境（基线已复现）

在基线 `9c7d2dcfbd` 上同批重跑，**同样 15 个失败**（清单逐条一致）：

| 测试 | 数量 | 初判原因 |
|---|---|---|
| `test_cli_anything_agent.py` | 6 | 注册表/环境相关（与本次改动无关，244d 未触碰该模块） |
| `test_legacy_model_alias.py` | 1 | 全仓别名扫描（环境） |
| `test_rf_workflow.py` | 2 | 含 LF 守卫（archive 提取的行尾假象）+ 需外部仿真器 |
| `test_toolknit_mcp.py` | 5 | 含 **pypdf 版本差异**（仓库 venv 6.19.0 vs 244b 验证时的 6.16.1，产物字节数不同）+ LF 守卫 |
| `test_spec03_phase34.py` | 1 | **即本单修的**（已从基线红 → 绿） |

> 这些**不是本单范围**，留给对应负责人；其中「LF 守卫在 archive 树上失真」这类
> 属于**测试环境**问题，不是仓库问题。

---

## §6 · 教训

1. **给「与被 exclude 的镜像有字节契约」的目录做 lint = 必然漂移**。
   exclude 清单不是「不想 lint 的都扔进去」，而是**契约边界** —— 加目录前要查它有没有镜像契约。
2. **全量套件 + 与基线差集**是抓这类回归的唯一可靠手段：
   244d 当时只跑了 9 个测试文件（127 passed），漏掉了 `test_spec03_phase34`。
3. 又一次：**blob 对 blob 才是权威判据**（工作树/archive 都会被 eol 规则改写）。
