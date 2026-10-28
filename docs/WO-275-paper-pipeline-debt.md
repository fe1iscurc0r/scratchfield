# WO-275 施工记录 · 论文采集流水线两处工程债

- **执行方**：K3（原派 Trae，Trae 已离场后接手）
- **日期**：2026-10-23
- **基线**：`main@0b40c2d4be67`
- **状态**：**T1 / T3 / T4 已交付**；**T2 只交开关（默认关）**；**cron 两晚验收被外部条件阻塞**

---

## §0 ⚠️ 偏差声明（开工前实测，与工单不符）

工单写的落点 `research/papers/scripts/fetch_arxiv.py`、`research/papers/weekly_pollination.md`、
根 `config.yaml` **在本仓库全部不存在**（全树 23860 文件，`fetch_arxiv` 命中 **0**）。
它们在实际运行采集的那台机器上（`~/research/papers/`）。

按 §B1 纪律 ⇒ **按语义在仓内规范重建**，并把偏差写在这里：

| 工单落点 | 本仓实况 | 本次处置 |
|---|---|---|
| `research/papers/scripts/fetch_arxiv.py` | ❌ 不存在 | 新建 `research/papers_pipeline/pipeline.py`（T1/T3/T4 的可运行参考实现） |
| `research/papers/weekly_pollination.md` | ❌ 不存在 | 不改（见 §5 待办） |
| 根 `config.yaml` | ❌ 不存在 | 改放 `research/papers_pipeline/config.example.yaml`（T2 开关） |

**这意味着**：本单交付的是**语义等价、可验收**的实现；真实机器上那份脚本仍需按同一套改动落地
（三处：进度文件 / `--budget` / 幂等写）。这一点不隐藏。

---

## §1 T1 · 断点续跑 + 预算内自停（已交付）

**实现**（`research/papers_pipeline/pipeline.py`）

| 要求 | 实现 | 位置 |
|---|---|---|
| 进度文件逐类原子写 | 每类完成即 append 一行 `{category, fetched, cursor, ts}` + `flush` + `fsync` | `_append_progress` |
| `--budget <秒>` 到点主动收尾 | 每类开始前检查耗时；超预算打印 `PARTIAL: done=a/b next=<cat> fallback=N` 并 **`return 0`** | `run` |
| 重复运行幂等 | `(category, base_id)` 为键；同 base 新版本**原地更新版本字段**，不追加行 | `_write_items` |
| RSS 回退通道 | `Backend.fetch` 第三返回值 `used_fallback`，计入 `PARTIAL`/`DONE` 行 | `FakeBackend` / `RssBackend` |

**实测（离线 FakeBackend，可复现）**

```
$ python -c "from research.papers_pipeline.pipeline import main; main(['--workdir','/tmp/pp','--budget','60'])"
DONE. categories=31 fallback=8

$ python -c "... main(['--workdir','/tmp/pp','--reconcile'])"
unique_base=217 versions=0 processed=217
```

预算法到点即停（`pytest tests/test_paper_pipeline.py::test_budget_zero_stops_before_any_category`）：

```
PARTIAL: done=0/6 next=cs.AI fallback=0     ← 退出码 0（不是被超时杀掉）
```

**三次连跑 `next=` 依次前进**（`test_budget_stops_midway_and_next_advances`）：
每次都 `PARTIAL` 且 `next` **不重复**，跑到 `DONE` 后再跑一次 **行数不变**（幂等）。

**`kill -9` 续跑**（`test_resume_after_hard_kill_does_not_duplicate`）：
第 1 次在第 3 类开工前被打断 ⇒ `progress.jsonl` **只留 2 条**、corpus 14 行；
第 2 次续跑补齐到 6 类、**每个 `(category, base_id)` 仅一行**（无重复）。

> 说明：本机无法真 `kill -9` 到子进程（测试用 `KeyboardInterrupt` 模拟"死在类目边界"），
> **语义一致**：被杀时没有写入该类的进度，因此下次从该类重来；已写入的不重复。
> 真实 `kill -9` 的验证要在采集机上做（见 §5 待办 1）。

---

## §2 T3 · 版本记录口径（选 a 的语料侧 + b 的对账侧）

**选择与理由**（工单要求二选一并说明）：

- **语料侧按 a)**：`corpus` 每个 base 只保留**最新版本**一行（不堆积历史）；
- **对账侧按 b)**：所有统计走**唯一 base 数**，并显式输出 `versions`（版本号 >1 的条数）；
- **未做 a) 的历史侧**（`versions.jsonl`）：原脚本的版本历史不在本仓，无落点可放；
  等真实脚本侧落地时一起做，避免造一个"本仓有、生产没有"的空转文件。

**对账输出**（`--reconcile`）：`unique_base / versions / processed` 三个数，
关系可解释：`unique_base ≤ processed`、`versions ≤ processed`，`processed = unique_base + 无版本历史的重复行数(本实现为 0)`。

```
unique_base=217 versions=0 processed=217     ← 离线 31 类 × 7 条
```

---

## §3 T4 · 类目表 `cs.ES` → `cs.ET`（已交付）

- `CATEGORIES` 31 类，含 `cs.ET`、**不含** `cs.ES`（`test_category_table_uses_cs_et_not_cs_es` 守卫）。
- 依据（沿用派单表实测）：`cat:cs.ES` 返回合法 Atom 但 `totalResults=0`；`cat:cs.ET` 有 8059 条。
- 补跑数据（派单表已做，未复跑）：80 条 / 唯一 base 80 / 本轮全新 71 ⇒ 确认旧表漏了 cs.ET。

---

## §4 T2 · 权重开关（只交开关，**未打开**）

`research/papers_pipeline/config.example.yaml`：

```yaml
collect_weight_overrides:
  enabled: false          # ← 默认关闭，打开前必须所有者明确指令
  when_enabled:
    extra_categories: [physics.app-ph, cs.CE]
    max_results_per_extra: 40
```

- **已就绪，等所有者一句话**。
- 打开后「每轮多抓 N 篇 / 耗时 +M 秒」的估算**尚未实测**（需要真实网络与真实脚本）；
  按 §B1 纪律，**不拍脑袋填数**，等真实环境跑一次后回填到本记录 §7。
- 测试守卫：`test_weight_switch_defaults_off` 断言 `enabled: false` 且两个额外类目在场。

---

## §5 阻塞项（**必须如实记录**）

| # | 阻塞 | 影响 | 解除条件 |
|---|---|---|---|
| 1 | **真实 cron 两晚无截断** 无法验证 | T1 第三项验收未达成 | ①DeepSeek 余额恢复（今日 02:00 `HTTP 402 Insufficient Balance`，余额 **−0.29 元**）②在采集机上按本实现在真实脚本里落地 |
| 2 | 真实脚本不在本仓 | 本次是**语义等价重建**，不是原地改 | 采集机上的 `~/research/papers/scripts/fetch_arxiv.py` 按 §1 三处改动 |
| 3 | `weekly_pollination.md` 那句回填 | 未做 | 该文件不在本仓 |
| 4 | cron 调用方式改写 | 未做（无法访问 cron 定义） | 建议新调用行见下 |

**建议的新 cron 调用行**（替代"靠提示词让 agent 自己 nohup"）：

```
python3 -m research.papers_pipeline.pipeline --online \
        --workdir "$HOME/research/papers/state" --budget 300 >> "$HOME/research/papers/cron.log" 2>&1
```

要点：**带 `--budget`**（到点主动 `exit 0`，不再产生 420 s 截断）、**`--workdir` 固定**（断点可续）、
`>>` 追加日志（不覆盖上一轮）。

---

## §6 验收命令（可复现）

```bash
cd <repo-root>
python -m pytest tests/test_paper_pipeline.py -q          # 期望 8 passed

# 手工跑一轮 + 对账
python -c "from research.papers_pipeline.pipeline import main; main(['--workdir','/tmp/pp','--budget','60'])"
python -c "from research.papers_pipeline.pipeline import main; main(['--workdir','/tmp/pp','--reconcile'])"
```

**实测**：`8 passed in 0.93s`。

---

## §7 待回填

- [ ] T2 打开后的「+N 篇 / +M 秒」实测估算（需真实网络）
- [ ] 真实 `kill -9` 在采集机上的验证输出
- [ ] 两晚真实 cron 日志片段（`PARTIAL` 次数 ≤1 且有 `DONE`）
- [ ] `weekly_pollination.md` 备注句回填（该文件不在本仓）
