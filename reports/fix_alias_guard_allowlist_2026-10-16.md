# 修复「废弃模型别名」守卫在 main 上红着 —— 允许清单补一条历史快照

> 执行：Trae（GitHub 线）｜ 日期：**2026-10-16** ｜ 基线：main `c87368a488`
> 性质：**守卫误伤修复**（1 个测试文件的允许清单 +1 条；不改产品代码、不改扫描器逻辑）
> ⚠️ 该守卫**当前在 main 上就是红的**（`pytest -m core` 会挂）——CI 闸门关着所以红了 2 天没人看见

## §0 · 症状

```
FAILED tests/test_legacy_model_alias.py::test_no_deprecated_alias_outside_allowlist
AssertionError: active 路径仍残留废弃别名 'deepseek-chat'（应统一为 'deepseek-flash'）：
    reports/workorder_conversion_stats_initial_2026-10-11.json:599:
      "title": "feat(w229): 废弃别名 deepseek-chat→deepseek-flash 清扫 + peak_switch 测试/文档 + 模型 ID 兼容矩阵 (#325)"
```

## §1 · 定性：**不是漏清扫，是守卫误伤**

命中的那一行是**统计基线快照里的历史 PR 标题原文**——而那条 PR（#325）的标题**本身就在讲这次清扫**。
也就是说：守卫扫到的不是"还在用旧别名"，而是"**一份记录了这场清扫的历史文档**"。

按守卫**自己的设计哲学**（文件头写得很清楚）：

> `ALLOWED_LEGACY_SITES` 是**显式契约而非遗漏**：只允许「历史证据 / 处置手册」保留旧字面量，每条都写明理由。

这份 JSON 恰好属于"历史证据"类——**改掉它就是伪造历史**（它必须逐字保留 #325 的标题）。
⇒ 正确修法不是去改数据，而是**把它按 A 类（历史证据）加进显式允许清单**，并写明理由。

## §2 · 时间线（为什么守卫作者当时没抓到）

| 时间 | 事件 |
|---|---|
| 2026-10-13 | `4f3d73bcfe` 守卫落地（工单229）——**当时是绿的**（仓里只有 3 处历史证据 + 工单归档） |
| **2026-10-14** | `6e6982059d`（工单238，PR #328）加进 `reports/workorder_conversion_stats_initial_2026-10-11.json`：漏斗 2.0 闭环统计的**首期基线**，内容是 692 行历史 PR/工单记录 ⇒ 其中 L599 = #325 标题原文 |
| 10-14 → 10-16 | 守卫红着，**无人看见**（CI 闸门 `ENABLE_CI_TEST` 未开；`pytest -m core` 没人跑全量） |

⇒ 又是同一类模式：**闸门关着 ⇒ 回归被静默带走**。与本轮修的
`test_import_starowner_utils`（收集中断，同日另单）是姊妹篇。

## §3 · 改法

`ALLOWED_LEGACY_SITES` **+1 条**（C 类·历史快照），理由写进清单本身：

```python
    # C. 历史快照（2026-10-16 补）：统计基线是**历史 PR 标题**的逐字快照，
    #    其 L599 恰好是 #325 的标题原文（那条标题本身就在讲这次清扫）——
    #    改了就是伪造历史。下面的 meta 测试会盯住「仍存在且仍命中」，不会烂成空转。
    "reports/workorder_conversion_stats_initial_2026-10-11.json":
        "历史证据：漏斗 2.0 闭环统计首期基线（692 行 PR/工单记录快照，含 #325 标题原文）",
```

**为什么选"加清单"而不是"教守卫跳过 `reports/**`"**：
跳过整个目录会让**未来**某份 report 里真正混进旧别名时守卫失明；
显式清单 + 理由 + meta 测试（`test_allowlist_entries_exist_and_still_match` 逐条盯"仍存在且仍命中"）
才是这个守卫自己选的防腐烂方式。**不削弱守卫，只把合法历史登记在册。**

## §4 · 验证

| 项 | 结果 |
|---|---|
| `pytest tests/test_legacy_model_alias.py -q` | **6 passed**（主契约 + meta 测试 + 3 个负向对照 + 切换器预设契约） |
| `ruff check tests/test_legacy_model_alias.py` | **All checks passed** |
| 行尾 | main 真 blob 为 **LF**；编辑器把整文件翻成了 CRLF（159/159），**已用字节直写归一回 LF**（7910 B、CRLF=0），并复跑测试/ruff 确认 |
| 扫描器不变 | `scan_legacy_alias` / 负向对照用例**一字未动** ⇒ 守卫的牙齿还在 |

## §5 · 本单在全量基线里的位置（26 failed 的分诊结论，2026-10-16）

全量 `pytest -q`（`tests/`，`-m 'not live'`）：**26 failed / 1587 passed / 12 skipped / 8m16s**。
分诊结果（⚠️ 本地验证树是 `git archive` 解出的，被 `.gitattributes` 的 `* text=auto eol=crlf`
**整体转成 CRLF**，而 main 真 blob 多为 LF ⇒ **行尾类失败全是本地树假象，不是 main 的缺陷**）：

| 类 | 数量 | 判定 |
|---|---|---|
| **行尾守卫误红**（`test_rf_workflow …are_lf`、`test_toolknit_mcp …is_lf_only`） | 2 | **本地树假象**（`full/` 里那些文件是 CRLF；main 真 blob 是 LF） |
| **环境缺依赖/模型/CLI**（`test_academic_*` 6、`test_cli_anything_agent` 7、`test_local_embedder` 5、toolknit pdf 4 等） | ~23 | 本机缺 rdkit/模型/`@toolknit/cli` 等 ⇒ 非缺陷 |
| **真缺陷** | **2** | ① 本单（别名守卫误伤）② `test_import_starowner_utils` 收集中断（**同日另单已修**，PR #356） |

⇒ 修完本单，**全量基线里已知的真缺陷清零**；其余失败需要"blob 忠实的验证场"（§R2）或补依赖才能复判。

## §6 · 复现

```bash
python -m pytest tests/test_legacy_model_alias.py -q     # 6 passed
python -m pytest -m core -q                              # 不再因本条红（其余见 §5 分诊）
```
