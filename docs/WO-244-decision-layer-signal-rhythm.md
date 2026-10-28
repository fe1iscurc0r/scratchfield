# 工单 244 · 决策层讯报节奏化（每日 17:00 / 每周一 09:00 推送格式标准化）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-244 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_244.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-244-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_244.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 13:35 下令"全部出下去"，本单配套 WO-238/239/240/242/243 形成"产出→台账→决策讯报"闭环
> **素材来源**：
> - 10-15 已存在 17 个 cron job（`hermes cron list` 已盘点）
> - 已有每日早报 cron `2ba664390971` (qqbot, no-agent, 0 7 * * *)
> - 已有周趋势报告 cron `37414dec35c7` (qqbot, 0 8 * * 1)
> **关联 cron**：可与"每周一 09:00 周趋势报告"合并 / 或独立跑

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 盘点全部 17 个 cron | ✅ | 见 §6 表 |
| 2 | 现有"无新增无 alert"风格的脚本 | ⚠️ | 多数 cron 是 no-agent（脚本 stdout 直推），少有"标准讯报格式"层 |
| 3 | 用户读哪条频道最多 | ✅ | qqbot Home（DM）+ 紧急推送（`8df70a55105b`, */5）|
| 4 | 师傅日报 vs 周报分隔是否清晰 | ❌ | 当前每周一 09:00 是"GitHub 扫货日报" cron `a37ffecbd730` 同名"日报"但频率是**每日**——名称容易混淆 |

**核心痛点**：
- 师傅现在每天晚上/早上 QQ 看 3 条 cron（早报 + 安全巡检 + 扫货日报）+ 每周一早看周趋势
- 缺一份"按决策层级（紧急/重要/日常/周度）"的**讯报节奏表**，导致师傅每次都要对照 cron 名问"这条是干啥的"
- 紧急推送 (`*/5`) 跟决策层信号混在一起

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 写一份 `docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md`（决策层讯报节奏表）+ `scripts/runbooks/build_signal_table.py` 自动重排版脚本 + 一个 daily-summary 简易 cron 接入 |
| **M** Measurable | ① 节奏表覆盖全部 17 个 cron；② build_signal_table.py 一次重排出 markdown；③ daily-summary cron 启动后，每天 17:00 给师傅推一条"今日 cron 收成 + 异常" |
| **A** Achievable | 纯文档 + 1 个解析脚本 + 1 个新 cron 注册 |
| **R** Relevant | 师傅铁律"先查 cron，再做事" + "cron 推微信单条多 MEDIA 附件被截断"（10MB 防备） |
| **T** Time-bound | 1 周（W1 与 WO-238/239/240/242/243 同期 review）|

## §2 · 任务清单

### 任务 A · 决策层讯报节奏表

新文件 `scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md`：

#### 按"决策紧迫性"分四档

| 档 | 触发频度 | 触发条件 | 师傅动作 |
|----|---------|---------|---------|
| 🔴 P0 紧急 | `*/5` / `0 *` | 服务挂了 / 鉴权挂了 / 主对话 5xx | 看 `urgent_push_consumer.sh` 通道 |
| 🟡 P1 重要 | `0 7 / 0 8 / 0 9` | 早报 / 安全 / 日报 | 早起 7-9 点三连 |
| 🟢 P2 日常 | `0 3 / 0 4 / 0 2` | 备份 / 蜜饵 / 论文增量 | 不直接读，留档备查 |
| 🟦 P3 周度 | `0 8 * * 1` | 周趋势 / 周授粉 | 周一早上 review |

#### 17 个 cron 全表（按档分桶）

| 档 | cron job_id | 名称 | 频度 | deliver |
|----|-------------|------|------|---------|
| 🔴 | `8df70a55105b` | 紧急推送 | `*/5 * * * *` | origin |
| 🔴 | `d2484a567104` | 自动封禁检查 | `0 * * * *` | origin |
| 🟡 | `2ba664390971` | 每日早报 | `0 7 * * *` | qqbot |
| 🟡 | `67c43c05f468` | RSS→规则自生成 | `30 7 * * 1-5` | qqbot |
| 🟡 | `a37ffecbd730` | GitHub 扫货日报 | `0 9 * * *` | qqbot |
| 🟡 | `67b396815fc3` | 每日安全巡检 | `0 8 * * *` | qqbot |
| 🟡 | `bcb4b8c8c151` | 系统脉搏体检 | `5 7 * * *` | qqbot |
| 🟢 | `3869dd1e933a` | 数据备份 | `0 3 * * *` | local |
| 🟢 | `d22b33160359` | 蜜饵自动刷新 | `0 3 * * *` | local |
| 🟢 | `b073dea9a0aa` | MLA 日志压缩 | `0 4 * * *` | local |
| 🟢 | `0081aeb248b2` | DeepSeek-Harness-每日Trending | `0 1 * * *` | qqbot |
| 🟢 | `ad17cd9d341f` | 论文流水线-每日增量扫+授粉 | `0 2 * * *` | origin |
| 🟢 | `a2b1d1c30ca1` | NEKO#2881 回应监控 | `0 10 * * *` | origin |
| 🟢 | `91dd60d9e7e1` | Gitee 星数回填（凌晨错峰）| `0 3 * * *` | origin |
| 🟢 | `3e8496c76d23` | steam-watchdog | `every 8m` | local |
| 🟦 | `37414dec35c7` | 周趋势报告 | `0 8 * * 1` | qqbot |
| 🟦 | `bda7241fa9c3` | 授粉流水线-超限战轮 | `0 15 * * *` | origin |

**重名警示**：cron 名称里同时出现"日报"和"周趋势"两类——`a37ffecbd730` 命名"GitHub 扫货日报"但实际频率是**每日**（不是周报）；`37414dec35c7` 是唯一**真正的周报**。本节奏表是"按频度定档"，不是按名称。

### 任务 B · build_signal_table.py 自动排版脚本

新文件 `scratchpad/scripts/runbooks/build_signal_table.py`：

```python
#!/usr/bin/env python3
"""从 `hermes cron list` 读取当前 17 个 cron，按 §A 节奏表自动重排
跑一次 = 重生成 §A 表格（避免手动维护漂移）"""
import subprocess, json, re, pathlib, datetime

CRON_CLASSIFY = {
    # name → 档位（按 §A 节奏表口径）
    "紧急推送": "🔴", "自动封禁检查": "🔴",
    "每日早报": "🟡", "RSS→规则自生成": "🟡",
    "GitHub 扫货日报": "🟡", "每日安全巡检": "🟡", "系统脉搏体检": "🟡",
    "数据备份": "🟢", "蜜饵自动刷新": "🟢", "MLA 日志压缩": "🟢",
    "DeepSeek-Harness-每日Trending": "🟢",
    "论文流水线-每日增量扫+授粉": "🟢",
    "NEKO#2881回应监控": "🟢", "Gitee星数回填(凌晨错峰)": "🟢",
    "steam-watchdog": "🟢",
    "周趋势报告": "🟦",
    "授粉流水线-超限战轮": "🟦",  # 每日跑但产出周度
}

def parse_cron_list(text):
    rows = []
    cur = {}
    for line in text.splitlines():
        m_job = re.match(r"\s+(\w+)\s+\[(active|paused)\]", line)
        if m_job:
            if cur: rows.append(cur)
            cur = {"id": m_job.group(1), "state": m_job.group(2)}
        m_name = re.match(r"\s+Name:\s+(.+)", line)
        if m_name: cur["name"] = m_name.group(1).strip()
        m_sched = re.match(r"\s+Schedule:\s+(.+)", line)
        if m_sched: cur["schedule"] = m_sched.group(1).strip()
        m_deliver = re.match(r"\s+Deliver:\s+(.+)", line)
        if m_deliver: cur["deliver"] = m_deliver.group(1).strip()
    if cur: rows.append(cur)
    return rows

if __name__ == "__main__":
    r = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True)
    rows = parse_cron_list(r.stdout)
    rows.sort(key=lambda x: CRON_CLASSIFY.get(x.get("name",""), "🟢") + x["id"])
    out = pathlib.Path("scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md")
    today = datetime.date.today().isoformat()
    print(f"=== {today} cron 节奏重排 ===")
    print(f"| 档 | job_id | 名称 | 频度 | deliver |")
    print(f"|----|--------|------|------|---------|")
    for r in rows:
        flag = CRON_CLASSIFY.get(r["name"], "🟢")
        print(f"| {flag} | `{r['id']}` | {r['name']} | {r['schedule']} | {r['deliver']} |")
```

**验收 grep/assert**：
```bash
# 1. cron 总数 = 17
python3 scratchpad/scripts/runbooks/build_signal_table.py | grep -c "^| [🔴🟡🟢🟦]"  # = 17
# 2. 节奏表 md 含 17 个 cron 条目
grep -c '^| [🔴🟡🟢🟦]' scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md  # = 17 + §A 重排表
```

### 任务 C · daily-summary cron 接入

新文件 `scratchpad/scripts/runbooks/daily_summary.py`：

```python
#!/usr/bin/env python3
"""17:00 给师傅推"今日 cron 收成 + 异常"——纯文本，无 LLM，无 token
按 cron output dir 目录扫描 ~/.hermes/cron/output/*/，列出今天 0-17 点完成/失败/被截断的跑批
按"决策层讯报节奏表 §A"档位分类汇总"""
import os, json, datetime, pathlib, subprocess, sys
from collections import defaultdict

OUT_DIR = pathlib.Path("/home/ubuntu/.hermes/cron/output")
TODAY = datetime.date.today().isoformat()

# 把所有今天的产出按 job_id 聚类
today_prods = defaultdict(list)
for d in OUT_DIR.iterdir():
    if not d.is_dir(): continue
    for f in d.iterdir():
        if f.name.startswith(TODAY):
            today_prods[d.name].append(f.name)

# 列出 ok / 截断 / 失败（按产出文件大小阈值启发）
def ok_or_warn(size):
    return "🟢" if size > 500 else "🟡" if size > 100 else "🔴"

lines = [f"📡 **今日 cron 收成** {TODAY}"]
for job_id in sorted(today_prods.keys()):
    files = today_prods[job_id]
    total = sum((OUT_DIR/job_id/f).stat().st_size for f in files)
    flag = ok_or_warn(total)
    lines.append(f"{flag} `{job_id}` — {len(files)} 个产出，总 {total//1024} KB")

print("\n".join(lines))
```

**cron 接入**（`hermes cron create`）：
```
Name: 决策层-每日汇总
Schedule: 0 17 * * *
Deliver: qqbot
Script: /home/ubuntu/scratchpad/scripts/runbooks/daily_summary.py
Mode: no-agent
```

**验收 grep/assert**：
```bash
# 1. 脚本可运行
python3 scratchpad/scripts/runbooks/daily_summary.py 2>&1 | head -5
# 期望：📡 **今日 cron 收成** + ≥ 1 行汇总

# 2. cron 注册成功
hermes cron list | grep -c '决策层-每日汇总'  # = 1
```

## §3 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-244-decision-layer-signal-rhythm.md`（本文件）
- **新文件**：
  - `scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md`（任务 A）
  - `scratchpad/scripts/runbooks/build_signal_table.py`（任务 B）
  - `scratchpad/scripts/runbooks/daily_summary.py`（任务 C）
- **新 cron**：`决策层-每日汇总`（任务 C 接入）

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| `hermes cron list` 输出格式改变 → parser 失效 | 任务 B parser 仅按 `Name:` `Schedule:` `Deliver:` 等**已知字段**前缀抽取 |
| 17:00 推 qqbot 跟其他 cron 撞时间 | 选 17:00 是为了错开 0 9 扫货日报 + 0 8 安全巡检 |
| daily-summary 17:00 触发 → 17-24 点 cron 还没跑 | 任务 C 标"今日 0-17 点"，明确时段 |
| build_signal_table.py 输出表格漂移到 doc 难对齐 | 任务 A 写入是**手动**（保留权威版），脚本为**校验** |

**不在本工单范围**：
- 改 cron 名（保留历史命名）
- 写 dashboard / Web UI（留未来工单）
- 跟 WO-243 抢 weekly 节奏（WO-243 周一 04:30 / 本工单工作日 17:00）

## §5 · 验收不变量

```bash
# 1. 节奏表 md 含全部 17 个 cron 条目
grep -c '^| [🔴🟡🟢🟦] | `' scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md  # ≥ 17

# 2. build_signal_table.py 输出 17 条
python3 scratchpad/scripts/runbooks/build_signal_table.py | grep -c '^| [🔴🟡🟢🟦]'  # = 17

# 3. daily-summary 脚本可独立跑
python3 scratchpad/scripts/runbooks/daily_summary.py | head -3

# 4. cron 注册
hermes cron list | grep -c '决策层-每日汇总'   # ≥ 1

# 5. 主流程 0 改
git diff --stat -- NEKO apiserver | wc -l   # = 0
```

## §6 · 关联的 17 个 cron（本工单索引对象）

完整列表见 §A 表——本工单**不改任何 cron**，仅汇总成节奏表 + 加 1 个新 cron（`决策层-每日汇总`）。

---

> 沈遥出单 · 与 WO-238/239/240/242/243 同期进 PR #345 review 链
