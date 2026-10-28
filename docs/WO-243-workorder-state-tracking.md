# 工单 243 · 工单状态台账（WO-230 ~ WO-242 进度追踪）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-243 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_243.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-243-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_243.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 13:35 下令"全部出下去"，本单配套 WO-238/239/240 + WO-242 的进度追踪层
> **素材漏斗**：scratchpad 主仓库现有 WO 编号 230/231/232/233/234/235/236/237/238/239/240，共 **11 份已编号**（241 已撤销，242 在本工单）
> **关联工程**：WO-237 RAG 索引层 + WO-238 授粉弹药入仓 + WO-239 论文限流 + WO-240 日报归档 + WO-242 守卫统一封装

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 摸现有 WO 编号分布 | ✅ | 230/231/232/233/237 在线；234/235/236 归档 archived_2026-10-11_run_three |
| 2 | WO-238/239/240/242 落盘状态 | ✅ | 4 份已成文，待 PR merge 进 main |
| 3 | 现有状态文档 | ❌ | `scratchpad/docs/workorders/batch/BATCH-施工状态台账-2026-09-02.md` 仅覆盖 09-02 那一批 |
| 4 | 跨批查看方式 | ❌ | 没有"按主题批量过滤"的视图 |

**核心痛点**：
- 现有 WO 编号已散落 11 份（230-237 + 238-240 + 242），每次师傅问"WO-238 在哪"只能逐文件 grep
- 已有"按批"台账（09-02 那批）但没"按 cron 触发"台账（授粉/论文/日报各有几条混在同一编号空间）
- 没有"已完成/进行中/未启动/被搁置"的状态列

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 落两份索引文件——`docs/workorders/INDEX-active.md`（活跃 WO 表）+ `docs/workorders/INDEX-state-tracking.md`（按状态聚合），并加 cron 维度的 weekly 打表脚本 |
| **M** Measurable | ① INDEX-active 列出 11 份现存 WO（编号 / 标题 / 触发 cron / 状态 / 关联 PR）；② INDEX-state-tracking 按"已 commit / 待 PR merge / Trae 进行中 / 已归档 / 被搁置"5 档分桶；③ weekly 打表脚本 cron-able |
| **A** Achievable | 纯文档 + 1 个 Python 脚本，零代码改动 |
| **R** Relevant | 师傅铁律 #②（合作进度可见性）+ 9 月那批已有同结构台账可参考 |
| **T** Time-bound | 当天（W1 同步推送 PR 与本工单，一起进 review）|

## §2 · 任务清单

### 任务 A · 写 INDEX-active.md

新文件 `scratchpad/docs/workorders/INDEX-active.md`：

| 编号 | 标题 | 触发源（cron / 师傅指令） | 状态 | 关联 PR | 字节 | 落点 |
|------|------|--------------------------|------|---------|------|------|
| WO-230 | 生物质材料科研 agent · 实验设计与执行架构 | 09-11 13 轮跑批 6144 篇论文 | Trae 进行中 | — | — | `research/workorder_drafts/` |
| WO-231 | 生物质材料科研 agent · 知识库 RAG 治理（多模态） | 同上 | 已 commit | — | — | 同上 |
| WO-232 | 生物质材料科研 agent · 候选场景打分 | 同上 | 已 commit | — | — | 同上 |
| WO-233 | 生物质材料科研 agent · 多 Agent 编排 | 同上 | 已 commit | — | — | 同上 |
| WO-234 | ESP32 LoRa 数据稳定性 | 09-11 13 轮跑批 | **archived_2026-10-11_run_three** | — | — | `research/workorder_drafts/archived_2026-10-11_run_three/` |
| WO-235 | PCB 拓扑知识库 | 同上 | **archived_2026-10-11_run_three** | — | — | 同上 |
| WO-236 | 跨线路协议治理 | 同上 | **archived_2026-10-11_run_three** | — | — | 同上 |
| WO-237 | 灵感素材库 RAG（biomass + sdr 双线索引层） | 10-11 RESCORE-V3 高分入选 | 已 commit，PR #325 已 merge（按 W244 系列 Trae 已推 main）| — | 3.8 KB | `research/workorder_drafts/` |
| **WO-238** | 授粉-轮 41 弹药入仓 + RAG 索引 | **cron bda7241fa9c3 10-15 15:06** | **已 commit, PR #345 open** | **#345** | 12.7 KB | `docs/WO-238-…md` |
| **WO-239** | 论文-限流护栏 + 4 授粉跟单 | **cron ad17cd9d341f 10-15 02:15** | **已 commit, PR #345 open** | **#345** | 11.2 KB | `docs/WO-239-…md` |
| **WO-240** | 日报-11 候选 + 4 排除 + 22 haul | **cron a37ffecbd730 10-15 09:06** | **已 commit, PR #345 open** | **#345** | 13.5 KB | `docs/WO-240-…md` |
| **WO-242** | 跨工单守卫脚本（批量守卫封装）| 13:35 师傅指令 | **已 commit（本 PR）, PR #345 open** | **#345** | 4.5 KB | `docs/WO-242-…md` |
| ~~WO-241~~ | ~~授粉-轮 42 无人机飞控+KG-RAG 双线~~ | ~~10-15 14:15 手工跑批~~ | **已撤销**（师傅 13:25 暂停无人机）| — | — | 撤销不入仓 |

### 任务 B · 写 INDEX-state-tracking.md

新文件 `scratchpad/docs/workorders/INDEX-state-tracking.md`：

| 状态 | 数量 | WO 编号 |
|------|------|---------|
| ✅ 已 commit + Trae 已 merge 进 main | 3 | WO-231 / 232 / 233 |
| 🟡 已 commit + **本 PR 推 main**（WO-238/239/240/242）| 5 | WO-237 已 merge / **WO-238/239/240/242 待 review merge** |
| 🟢 Trae 进行中（wo 已发，等施工）| 1 | WO-230 |
| 📦 已归档（archived_2026-10-11_run_three）| 3 | WO-234 / 235 / 236 |
| ⛔ 已撤销（师傅暂停）| 1 | ~~WO-241~~ |

**按 cron 触发维度聚合（10-15 跑批对应）**：

| Cron | 触发跑批时间 | 产出 WO 编号 | 状态 |
|------|-------------|-------------|------|
| `bda7241fa9c3` 授粉流水线-超限战轮 | 10-15 15:06 | WO-238 | ⏸ 待 PR #345 merge → Trae 施工 |
| `ad17cd9d341f` 论文流水线-每日增量 | 10-15 02:15 | WO-239 | ⏸ 同上 |
| `a37ffecbd730` GitHub 扫货日报 | 10-15 09:06 | WO-240 | ⏸ 同上 |

**按主题维度聚合**：

| 主题 | WO 编号 |
|------|---------|
| 授粉落点（mcpserver 接入） | WO-238 / ~~WO-241~~ |
| arXiv / 论文 | WO-230/231/232/239 |
| GitHub 扫货 / RAG 索引 | WO-237 / WO-240 |
| 防幻觉守卫 | WO-242 |
| 跨主题台账 | WO-243（**本单**）|

### 任务 C · weekly 打表脚本

新文件 `scripts/workorder_lifecycle/weekly_table.py`：

```python
#!/usr/bin/env python3
"""
按编号顺序扫描 scratchpad/docs/WO-*.md + research/workorder_drafts/WO-*.md，
生成本周活跃工单总表（每周一凌晨跑一次）。
"""
import re, glob, pathlib, datetime, subprocess, json, sys

DOCS = pathlib.Path("scratchpad/docs")
DESIGNS = pathlib.Path("scratchpad/research/workorder_drafts")
ALL_WO = sorted(
    set(int(re.match(r"WO-(\d+)", p.name).group(1))
        for p in DOCS.glob("WO-*.md"))
    | set(int(re.match(r"WO-(\d+)", p.name).group(1))
          for p in DESIGNS.glob("WO-*.md"))
)

TODAY = datetime.date.today()
WEEK_AGO = TODAY - datetime.timedelta(days=7)

def wo_status(num):
    """返回该 WO 的 last-commit mtime + 关联 PR（用 gh api）"""
    paths = list(DOCS.glob(f"WO-{num}-*.md")) + list(DESIGNS.glob(f"WO-{num}-*.md"))
    if not paths:
        return {"status": "missing"}
    p = paths[0]
    commit = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(p)],
                             capture_output=True, text=True).stdout.strip()
    return {"status": "ok", "path": str(p), "ts": int(commit) if commit else 0}

if __name__ == "__main__":
    table = [{"wo": f"WO-{n:03d}", **wo_status(n)} for n in ALL_WO]
    out = {"week_start": WEEK_AGO.isoformat(), "today": TODAY.isoformat(), "rows": table}
    print(json.dumps(out, indent=2, ensure_ascii=False))
```

**cron 接入**（轻量）：
```
# 周一凌晨 4:30（与 MLA 日志压缩错开 30 分钟）
30 4 * * 1 /usr/bin/env python3 /home/ubuntu/scratchpad/scripts/workorder_lifecycle/weekly_table.py > /home/ubuntu/.hermes/cron/output/wo-index/<ts>.json
```

**验收 grep/assert**：
```bash
# 1. 两份 INDEX 存在
ls scratchpad/docs/workorders/INDEX-active.md scratchpad/docs/workorders/INDEX-state-tracking.md 2>&1
# 期望：2 个 OK

# 2. weekly 脚本运行成功
python3 scratchpad/scripts/workorder_lifecycle/weekly_table.py | jq '.rows | length'
# 期望：≥ 11

# 3. 同步 cron（用 hermes cron 工具）
hermes cron create --name "WO周表" --schedule "30 4 * * 1" --script scratchpad/scripts/workorder_lifecycle/weekly_table.py --deliver local
```

### 任务 D · 跟 POLLINATION-FUNNEL-v2-CHANGELOG 联动

把这次 3 WO-238/239/240 + WO-242 + WO-243 一次性索引追加进 CHANGELOG：

```bash
# 在已有 CHANGELOG 追加"工单层 v2 索引"
cat >> scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md <<EOF

## 2026-10-15 工单层 v2 索引
- WO-238/239/240/242/243 同步入仓（PR #345）
- INDEX-active.md + INDEX-state-tracking.md 新立
- weekly_table.py cron 接入
EOF
```

**验收 grep/assert**：
```bash
grep -c "2026-10-15 工单层 v2 索引" scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md
# 期望：≥ 1
```

## §3 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-243-workorder-state-tracking.md`（本文件）
- **新文件**：
  - `scratchpad/docs/workorders/INDEX-active.md`
  - `scratchpad/docs/workorders/INDEX-state-tracking.md`
  - `scratchpad/scripts/workorder_lifecycle/weekly_table.py`
- **追加修改**：`scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md`（追加段）
- **可选 cron**：通过 `hermes cron create` 注册

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| INDEX-active 漏列 WO（grep 漏掉） | 走 `glob WO-*.md` 全文扫描，不靠记忆 |
| weekly_table.py 与 cron 工具有路径冲突 | 显式用绝对路径写脚本 + `--deliver local` 不推 QQ |
| 跟 09-02 那批旧台账不连 | 不动 BATCH-施工状态台账-2026-09-02.md，独立新立 |
| 触发本工单的"未配 git pre-commit 的 hook" | 本工单不入 git hooks，仅写文档 + 脚本 |

**不在本工单范围**：
- 改 WooState 字段格式（不留 schema）
- 给 WO 加 `[status: TODO/InProgress/Done]` 标签（今日不动 doc 模板）
- 写 WO 转 workorder_drafts 的自动迁移工具（留下轮）

## §5 · 验收不变量

```bash
# 1. 两份 INDEX 存在
ls scratchpad/docs/workorders/INDEX-{active,state-tracking}.md
# 期望：2 个 OK

# 2. weekly_table.py 可运行
python3 scratchpad/scripts/workorder_lifecycle/weekly_table.py | jq '.rows | length'  # ≥ 11

# 3. CHANGELOG 追加段已落
tail -20 scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md | grep "工单层 v2 索引"
# 期望：1 行命中

# 4. 不动主流程
git diff --stat -- NEKO apiserver | wc -l   # = 0

# 5. 跑 WO-242 的批量守卫跑得起
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-workorders WO-238 WO-239 WO-240 WO-242 WO-243
# 期望：5 行均 FAIL=0
```

## §6 · 与已有工程的关系

| 现有 | 关系 |
|------|------|
| `scratchpad/docs/workorders/batch/BATCH-施工状态台账-2026-09-02.md` | **不动**（09-02 那一批独立台账保留） |
| 11 份现存 WO | **索引对象** |
| WO-242 跨工单守卫 | **依赖**（本任务 C 每周跑一次会触发守卫） |
| POLLINATION-FUNNEL-v2-CHANGELOG | **追加段**（任务 D）|

---

> 沈遥出单 · 同步挂入 PR #345 / 师傅 review 时一并看
