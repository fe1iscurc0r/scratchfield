# 工单 240 · 日报→工单自动转化器 · 交付报告

> 委托方：用户 · 执行：Trae（GitHub 线）· 出单：沈遥 · 落地日期：**2026-10-14**
> **数据快照**：main `ce3b5cc489`（2026-10-14）· 全树 `git/trees?recursive=1` = **25,065 条目，`truncated=false`**
> 上游设计稿：`research/workorder_drafts/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md`

---

## 0 · 一句话

漏斗 2.0 的**末端断头路**（日报 → 工单）已打通：新增 `tools/cron_to_workorder.py`，
每天扫日报 → 双门槛筛 → 落盘工单草稿 → 人工签字后 `--promote` 成正式工单。

**但**：工单 §2 列的 5 个 cron 产出路径里，**只有 1 个与实况完全一致**；
「验收第 2 条：cron 在 `crontab -l` 可见」与「推微信」在本机**无法落地**（无 `~/.hermes`、无 `crontab`）——
详见 §3 与 §7，**不粉饰**。

---

## 1 · 交付物

| 文件 | 作用 | 体积 |
|---|---|---:|
| `tools/cron_to_workorder.py` | 主工具：`--scan` / `--list-sources` / `--promote` | 33.8 KB |
| `tools/test_cron_to_workorder.py` | 单元测试 **91 用例** | 23.1 KB |
| `cron/cron_to_workorder_daily.sh` | 每日 06:00 日更脚本（含 crontab 行 + ⛔ 未接入说明） | 3.4 KB |
| `research/workorder_drafts/auto_2026-10-14/WO-245…249-*.md` | **首批 5 份工单草稿**（真实日报产出） | 6.1 KB |
| `research/workorder_drafts/auto_2026-10-14/_manifest.json` | 机器可读台账（源解析 / 去重 / 逐条溯源） | 2.5 KB |
| `reports/cron_to_workorder_launch_2026-10-14.md` | 本报告 | 12.0 KB |

---

## 2 · ⚠️ 路径对账（第六次「工单写的路径不是本仓路径」）

工单 §2 给了 9 个 cron 的产出路径。以 main 全树（25,065 条目，非截断响应）逐条核对：

| cron id | 名称 | 工单写的路径 | 本仓实测 | 判定 |
|---|---|---|---|---|
| `a37ffecbd730` | GitHub 扫货日报 | `docs/GitHub-Sweep-Daily-*.md` | **同左**，3 份（10-11/12/13） | ✅ 一致 |
| `ad17cd9d341f` | 论文流水线-每日增量 | `research/papers/digests/` | `docs/paper-round*/digests/digest-*.md`（**55** 份）+ `授粉点-统一.{md,json}` | ❌ 路径不符 |
| `bda7241fa9c3` | 授粉流水线-超限战轮 | `research/papers/pollination/` | `docs/超限战轮*-授粉报告-*.md`（**24** 份）+ `docs/pollination/batches/*.md`（**16** 份） | ❌ 路径不符 |
| `0081aeb248b2` | DeepSeek-Harness Trending | `docs/DeepSeek-Harness-Trending-*.md` | 0 命中；最接近 `docs/GitHub-Trending-*.md`(2) + `docs/扫货-GH*.md`(2) | ❌ 名不同 |
| `67c43c05f468` | RSS→规则自生成 | `decision_layer/rules/*.yaml` | **无 `decision_layer/` 目录**；全仓 `rules/*.yaml` = **0 命中** | ❌ 源不存在 |
| `67b396815fc3` | 每日安全巡检 | `docs/ops-toolkit-report-*.md` | **0 命中** | ❌ 源不存在 |
| `bcb4b8c8c151` | 系统脉搏体检 | `docs/system-pulse-*.md` | **0 命中** | ❌ 源不存在 |
| 其余 5 个 | — | `local` / `weixin` only | 不在本仓（符合工单「不转工单」判断） | ✅ 一致 |

**处理方式**：`CronSource` 同时保留 `assumed`（工单原文）与 `patterns`（实测），运行时以实测为准；
`--list-sources` 把偏差打印出来，不默默吞掉。这是 `scripts/daily_paper_brief.py` 已有的同一手法
（其 docstring 亦写「工单原假设路径作兼容层」）——**同族工单第二次踩同一个坑**。

**能力边界（诚实版）**：5 个默认源里，本仓能解析出文件的只有 **4 个**；
`67c43c05f468` 在本仓**任何路径下都不存在**，故「覆盖前 5 个 cron」的验收项**在本仓不可能达成**，
须沈遥侧补路径（或确认该 cron 产物本就不入库）。

---

## 3 · 三个任务落地情况

| 任务 | 要求 | 状态 | 说明 |
|---|---|---|---|
| 一 | 写 `tools/cron_to_workorder.py` | ✅ **完成** | 三子命令齐全；规则模式可离线真跑；LLM 模式代码路径已写但**本机无 key，未实测** |
| 二 | cron `cron_to_workorder_daily` 接入 | ⚠️ **仅脚本落地** | `cron/cron_to_workorder_daily.sh` 已交付并本地跑通；**crontab 注册未落地**（本机 `which crontab` → not found） |
| 三 | 与 WO-238 闭环统计对接 | ✅ **完成** | 草稿与 `TRAE_WORKORDER_PROMPT_AGENT_*.md` 同构（首行 `# 工单 <n> · <标题>` + `> 委托方：…` 头 + `## §N` 节）；`--promote` 已实现且**幂等** |

### 三.1 `--promote` 行为契约（实测）

```
$ python3 tools/cron_to_workorder.py --promote <draft> --next-number 245          # dry-run，不落盘
$ python3 tools/cron_to_workorder.py --promote <draft> --next-number 245 --apply  # 落盘 → exit 0
$ python3 tools/cron_to_workorder.py --promote <draft> --next-number 245 --apply  # 目标已存在 → exit 3，拒绝覆写
```

实测输出（本机验证场）：

```
[promote:DRY-RUN]   首行: '# 工单 246 · arXiv:2608.18272v1 —— …' → '# 工单 245 · arXiv:2608.18272v1 —— …'
[promote:APPLY] 已写入 TRAE_WORKORDER_PROMPT_AGENT_245.md（git status 应显示 ??）
[promote] 目标已存在，拒绝覆写（幂等保护）：TRAE_WORKORDER_PROMPT_AGENT_245.md   ← exit=3
```

验证场根目录 TRAE 工单计数 **45 → 46**，证明落点是仓库根、命名与既有 45 份同构。

---

## 4 · §4 验收对账

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 24h 内 5 个 cron × 1 草稿/天 = 5 草稿/天基线 | ⚠️ **部分** | 单次运行产出 **5 份**（`--max-total 5`），但只覆盖 **4 个** cron —— 第 5 个源本仓不存在（§2） |
| 2 | cron 在 `crontab -l` 可见 | ❌ **未达成** | 本机无 `crontab`（§7） |
| 3 | `--promote` 工作正常 | ✅ 达成 | dry-run / apply / 幂等拒绝三条路径均实测（§3.1） |
| 4 | PR 描述里贴首批草稿路径 | ✅ 达成 | 见 §5；PR 正文复述同一张表 |

补充（任务一自身的验收）：

| 验收项 | 结果 |
|---|---|
| `--period 24h` 跑通 | ✅ `--date 2026-10-13 --period 24h --mtime-fallback off` → 3 份草稿 |
| `auto_<date>/` 落盘 ≥3 份 | ✅ 5 份 |
| 每份草稿 ≤ 2 KB | ✅ 实测 1,130–1,347 B（工具内置 `assert`，超限直接失败） |
| 每个草稿含 来源 cron / 来源报告 / 摘录 / 候选 PoC / 风险评估 | ✅ 有专门用例 `test_generated_draft_contains_all_required_fields` 守 |

---

## 5 · 首批 5 份草稿（真实日报产出，非构造数据）

`research/workorder_drafts/auto_2026-10-14/`

| 草稿 | 来源 cron | 来源报告 | 主题 | 风险 | 体积 |
|---|---|---|---|---|---:|
| `WO-245-mixelpixx-kicad-mcp-server-kicad-pcb-mcp.md` | `a37ffecbd730` | `docs/GitHub-Sweep-Daily-2026-10-11.md` | agent | 中 | 1,217 B |
| `WO-246-arxiv-2608-18272v1-a-agentic-sdr.md` | `ad17cd9d341f` | `docs/paper-round2-2026-08-30/digests/授粉点-统一.md` | sdr | 中 | 1,337 B |
| `WO-247-liminode-agent-memory-cpp-toolkit-esp32.md` | `bda7241fa9c3` | `docs/pollination/batches/GitHub扫货日报-2026-10-09.md` | agent/esp32 | 中 | 1,230 B |
| `WO-248-78-xiaozhi-esp32-mcp-based-chatbot-on-es.md` | `0081aeb248b2` | `docs/扫货-GHtrending-2026-09-02.md` | agent/esp32 | 中 | 1,130 B |
| `WO-249-karmine05-agentic-detector-osquery-agent.md` | `a37ffecbd730` | `docs/GitHub-Sweep-Daily-2026-10-12.md` | agent | 中 | 1,223 B |

选取策略：**按 cron 轮转**（`pick_round_robin`）而非纯按分数取前 N —— 首批草稿的**覆盖面**
（§4.1 要的「每个 cron 至少 1 条」）优先于单源密度。

> ⚠️ 编号 245–249 是 `--cand-base`（本机验证场里 `next_root_number()` = 最大 244 + 1）给出的
> **候选号**，不是已发放工单号。真发放时以 `--promote --next-number <n>` 显式指定，避免撞号。

---

## 6 · 生成模式：规则降级（**未静默**）

工单 §3 任务一要求「用 M3 (minimax) 抽 1-3 条/文件」。本机**无 `M3_API_KEY` / `DIGEST_API_KEY`**，
故实际走**规则模式**：

- 门槛 A（可执行 PoC 入口）：命中 `mcp / server / api / toolkit / framework / engine / 工具 / 框架 / 引擎 / 库…`
- 门槛 B（代码/论文支撑）：命中 `owner/repo` slug、`github.com/...` 或 arXiv 编号
- **摘录 = 原文片段**（不做任何改写，≤80 字）；**候选 PoC 明确标注 `[规则生成]`**
- 模式写进 **stdout、每份草稿头部、manifest 的 `mode` 字段**三处

LLM 路径（`PROMPT_TEMPLATE` = 工单 §6 原文模板；`llm_extract()` 走惰性 `import litellm`）已实现，
**任何 LLM 侧故障（无 key / 无 litellm / 解析失败 / 调用异常）都降级为规则模式并写明降级来源**，
绝不中断扫报。**该路径在本机未实测** —— 请勿把它当成已验证能力。

---

## 7 · ⛔ 未落地项（需沈遥侧接手）

| # | 项 | 实测证据 | 交接内容 |
|---|---|---|---|
| 1 | crontab 注册 | `which crontab` → `not found`；`ls -d ~/.hermes` → `No such file` | 在目标机 `crontab -e` 追加 `cron/cron_to_workorder_daily.sh` 头注里那一行（**不要覆写现有 25 条**） |
| 2 | 微信推送 | 本仓无 push 通道；通道归 `~/.hermes/cron` 编排 | 把 `auto_<date>/_manifest.json` 或草稿目录摘要接进既有日报投递 |
| 3 | 第 5 个 cron 源 | `rules/*.yaml` 全仓 0 命中 | 确认 `67c43c05f468` 产物落点，或确认它本就不入库（则 §4.1 基线应改为「4 个源」） |
| 4 | LLM 实测 | 无 key | 配 `M3_API_KEY` / `M3_API_BASE` / `M3_MODEL` 后跑一次 `--scan`，确认走 `llm(...)` 而非降级 |

---

## 8 · 质量与回归

| 项 | 结果 |
|---|---|
| 行尾 | 全部交付文件 **LF（crlf=0）**；`Path.write_text(..., newline="\n")`，并有 `test_main_writes_lf_only_for_manifest` 守 |
| ruff（仓库 `pyproject.toml`，0.16.8） | `tools/cron_to_workorder.py` + `tools/test_cron_to_workorder.py` → **All checks passed** |
| 单元测试 | **91 passed** |
| 覆盖率相关用例 | 参数解析 / 窗口（含 **clone 场景 mtime 漂移**回归）/ 双门槛 / 去重 / 轮转 / 源重叠守卫 / promote 幂等 / 体积与 LF 契约 |
| 本机 pytest 用时 | 0.72 s |

### 8.1 开发中真发现并修掉的 3 个 bug

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 1 | `bda7241fa9c3` 的候选全被归到 `a37ffecbd730` | `docs/pollination/batches/GitHub扫货日报-*.md` 被**两条源同时认领**，跨源去重时按 source 排序掩盖了归属 | 收紧源定义 + 新增 `find_overlaps()` 守卫，`--list-sources` 会打印重叠；manifest 记录 `source_overlaps` |
| 2 | 论文 digest（55 份）一条都抽不出 | digest 表**没有 slug 列**，首列是 arXiv 编号 → 门槛 B 恒假 | 新增 `extract_arxiv_pid()`，门槛 B 接受 arXiv 编号 |
| 3 | `--output` 在仓外时 `ValueError: is not in the subpath of` | `Path.relative_to` 不容忍仓外路径 | 新增 `rel_to()` 优雅退回绝对 posix |

---

## 9 · 数据快照与可复现口径

- 一切计数以 **main `ce3b5cc489`** 的全树（`git/trees?recursive=1`，25,065 条目，`truncated=false`）为准。
- 首批草稿由 `realrepo` 验证场产出：按 blob sha 从 main 拉取**真实字节**（9 份日报，共 177,687 B），
  未做任何内容改写。**生成脚本本身是确定性的**：同一份输入 + `--mtime-fallback off` 可复现同一批草稿。
- 本机 **无 crontab、无 `~/.hermes`、无 M3 key** ⇒ §4 第 1/2 条与 §6 的 LLM 路径**未达可验证状态**，如实标注。

---

## 10 · 相关文件

| 文件 | 作用 |
|---|---|
| `tools/cron_to_workorder.py` | 本单主工具 |
| `cron/cron_to_workorder_daily.sh` | 日更脚本 |
| `research/workorder_drafts/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md` | 上游设计稿 |
| `docs/POLLINATION-FUNNEL-v2-CHANGELOG.md` | 漏斗 v2 台账（本单已回写） |
| `tools/workorder_conversion_stats.py` | 工单线指标真源（WO-238） |
| `scripts/daily_paper_brief.py` | **同族先例**：同样面对「工单假设路径 vs 实测路径」偏差 |
