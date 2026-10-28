# 工单 247 · 状态.db 收口（hermes state.db 2.7G 回收 + maint 脚本幂等化 + runbook 落盘）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-247 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_247.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-247-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_247.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 08:14 在 QQ 下令"处理 github mcp 崩溃顺便清理磁盘"。本单 + WO-246/248 同期。
> **施工范围**（已实际完成，沈遥亲自）：
> - 81% → 73%（avail 11G → 16G）：删 ollama CUDA/ROCm runner 3.4G、snap cache 2.5G、journal 783M、syslog 220M
> - `~/.hermes/scripts/maint-state-db.sh` 写好（停网关 → optimize-storage → 拉起），但**未执行**（网关内禁止停网关）
> - 师傅在 orcaterm 跑 `maint-state-db.sh` 即可，预计腾 1–1.5G
> **剩余**：本工单做的是**收口**（脚本改幂等 + runbook + 巡检），不是首次清理

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 一次性大件清掉（ollama / snap / journal / syslog） | ✅ | 5.7G 释放 |
| 2 | state.db 2.7G（FTS trigram 旧布局） | ⚠ 待执行 | 师傅在 orcaterm 跑 `maint-state-db.sh` |
| 3 | `maint-state-db.sh` 是否幂等 | ❌ | 二次跑会再 VACUUM 一次（无害但慢） |
| 4 | 是否有锁文件防并发跑 | ❌ | 没人拦师傅自己再开一个 shell 同时跑 |
| 5 | `docs/operate/disk-cleanup.md` 复盘 runbook | ❌ 未落 | 本工单任务 A |
| 6 | `maint-state-db.sh` 改幂等 + dry-run + 锁文件 | ❌ | 本工单任务 B |
| 7 | 巡检 cron 接入（每周一 09:30 跑一次 df + 关键目录大小） | ❌ | 本工单任务 C |
| 8 | 24 cron 全档 + paused 7 个的处置表 | ❌ | 师傅拍板 6 份落盘时是 17 个 cron，现在 24 个（+7 paused） |

**核心痛点**：
- 师傅不知道哪些东西能删哪些不能（"删 ollama runner"是因为沈遥看了 GPU 型号；下次类似场景谁说了算？）
- state.db 收缩的"为什么能、为什么不能、何时做"没有 runbook
- 24 个 cron 里有 7 个 paused，WO-244 节奏表写 17 个，已与现实脱节

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | ① 磁盘清理 runbook 1 份（含"为什么 / 怎么验证 / 何时不删"）② `maint-state-db.sh` 升级为幂等+锁+dry-run ③ 磁盘巡检脚本 + cron 接入 ④ WO-244 节奏表按 24 个 cron 重新出 |
| **M** Measurable | ① runbook 覆盖 ollama runner / snap cache / journal / state.db 四类；② maint 脚本支持 `--dry-run` / `--skip-vacuum` / `flock` 锁；③ 巡检 cron 周一 09:30 自动推一条"df + 大目录 Top5"；④ 节奏表 24 cron 全列 + paused 7 个有处置建议 |
| **A** Achievable | 纯文档 + 1 个 shell 升级（≤ 100 行）+ 1 个新 cron 注册 + WO-244 节奏表修订 |
| **R** Relevant | 师傅铁律"先查 cron，再做事" + 师傅今天拍板"不要怕删，但要有依据" + "用户对 ROI 极敏锐" |
| **T** Time-bound | 2 天（W2 与 WO-246/248 同期 review） |

## §2 · 任务清单

### 任务 A · 磁盘清理 runbook

新文件 `scratchpad/docs/operate/disk-cleanup.md`：

- **§0 摘要**：今天的释放 5.7G + 4 大类可清理项
- **§1 怎么判断能不能删**：
  - 跑前：`lsof` / `ps` 查持锁，`systemctl is-active` 查服务
  - 准则：服务在跑 → 不删；服务 inactive + 上次用 > 30 天 + 体积 > 100M → 候选
- **§2 四大类清理项**：
  - **ollama runner**：用 `nvidia-smi` / `lspci` 查 GPU。无 GPU → 删 cuda_v*_avx、rocm_avx，留 cpu_avx、cpu_avx2
  - **snap cache**：`/var/lib/snapd/cache/` 装时硬链接，未必能全释放；先 `du -h` 看 top
  - **journal**：`sudo journalctl --vacuum-size=200M`（200M 是阈值，不是必须）
  - **syslog.X**：`truncate -s 0` 旧文件；不要 `rm`
- **§3 state.db 单独处置**（链接到任务 B）
- **§4 验证**：
  - 每次清理后跑 `df -h /`
  - 把前后对比落 `docs/operate/disk-cleanup-evidence-YYYY-MM-DD.json`
- **§5 不要删的清单**：
  - `~/.hermes/hermes-agent/venv/`（headroom proxy 占用）
  - `~/.hermes/tools/`（多版本工具并存是为了兼容）
  - `/swap.img`（系统级）
  - 任何 `state.db*`（活动进程持有）

### 任务 B · `maint-state-db.sh` 升级

`scratchpad/docs/operate/disk-cleanup.md` §3 链接到本任务，文件位置保持 `~/.hermes/scripts/maint-state-db.sh`（系统脚本）但**也**复制一份 `scratchpad/scripts/operate/maint-state-db.sh` 作为可审计版本。两者同步（cron 跑系统路径，PR 改仓里路径）。

**新增能力**：
- `--dry-run`：只打印"会做什么"不执行
- `--skip-vacuum`：跳过 VACUUM（已 optimize 过一次就不用再 VACUUM）
- `flock` 锁文件 `/home/ubuntu/.hermes/state.db.lock`：阻止并发跑
- 日志固定 `~/.hermes/logs/maint-state-db-YYYYMMDD-HHMMSS.log`
- 退出码：0=成功，1=网关停不掉，2=optimize 失败，3=网关拉不回来

**参考实现骨架**（Trae 实施）：

```bash
#!/usr/bin/env bash
set -u
LOCK=/home/ubuntu/.hermes/state.db.lock
LOGDIR=/home/ubuntu/.hermes/logs
exec 9>"$LOCK" || exit 99
flock -n 9 || { echo "ALREADY_RUNNING"; exit 1; }
LOG=$LOGDIR/maint-state-db-$(date +%Y%m%d-%H%M%S).log
exec >>"$LOG" 2>&1
ts() { date '+%F %T'; }
echo "[$(ts)] ==== maint start ===="
systemctl --user stop hermes-gateway.service
for i in $(seq 1 45); do
  systemctl --user is-active --quiet hermes-gateway.service || break
  sleep 2
done
timeout 1500 ~/.hermes/hermes-agent/.hermes/bin/hermes sessions optimize-storage --yes
RC=$?
systemctl --user start hermes-gateway.service
sleep 8
if ! systemctl --user is-active --quiet hermes-gateway.service; then
  systemctl --user restart hermes-gateway.service
  sleep 10
fi
echo "[$(ts)] optimize rc=$RC, gateway now $(systemctl --user is-active hermes-gateway.service)"
df -h / | tail -1
```

### 任务 C · 磁盘巡检 cron

新文件 `scratchpad/scripts/operate/disk-watch.sh`：
- 跑 `df -h /` + `du -h --max-depth=1 /home/ubuntu | sort -hr | head -10` + 几个关键目录（`~/.hermes/`, `/var/log/`, `/var/lib/snapd/`）
- 若 `use% > 80%` → 输出红色"⚠" 行
- 推 qqbot Home（师傅账号）

注册：
```bash
hermes cron add \
  --name "磁盘巡检" \
  --schedule "30 9 * * 1" \
  --deliver qqbot \
  --script "scratchpad/scripts/operate/disk-watch.sh" \
  --mode no-agent
```

注意：本工单不要求 Trae 真的 add（涉及 cron 状态机，谨慎）；只写脚本 + 在 runbook 里给命令。**师傅自己 add** 或下次会话师傅在场时 add。

### 任务 D · WO-244 节奏表按 24 cron 重新出

修订 `scratchpad/docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md`（任务 A 已规划但未落，按当前 24 cron 现状重出）：

- 24 cron 全表（按 P0/P1/P2/P3 分桶）—— 参见 §附录 A
- 7 个 paused 处置建议（参考 §附录 B）
- 师傅对"拍板 6 份"的接受（已 10-15 收口）

**附录 A · 24 cron 全表（Trae 必落）**：

| 档 | cron job_id | 名称 | 频度 | deliver |
|----|---|---|---|---|
| 🔴 | `8df70a55105b` | 紧急推送 | `*/5 * * * *` | origin |
| 🔴 | `d2484a567104` | 自动封禁检查 | `0 * * * *` | origin |
| 🟡 | `2ba664390971` | 每日早报 | `0 7 * * *` | qqbot |
| 🟡 | `bcb4b8c8c151` | 系统脉搏体检 | `5 7 * * *` | qqbot |
| 🟡 | `67c43c05f468` | RSS→规则自生成 | `30 7 * * 1-5` | qqbot |
| 🟡 | `67b396815fc3` | 每日安全巡检 | `0 8 * * *` | qqbot |
| 🟡 | `a37ffecbd730` | GitHub 扫货日报 | `0 9 * * *` | qqbot |
| 🟢 | `0081aeb248b2` | DeepSeek-Harness-每日Trending | `0 1 * * *` | qqbot |
| 🟢 | `ad17cd9d341f` | 论文流水线-每日增量扫+授粉 | `0 2 * * *` | origin |
| 🟢 | `3869dd1e933a` | 数据备份 | `0 3 * * *` | local |
| 🟢 | `d22b33160359` | 蜜饵自动刷新 | `0 3 * * *` | local |
| 🟢 | `91dd60d9e7e1` | Gitee 星数回填 | `0 3 * * *` | origin |
| 🟢 | `b073dea9a0aa` | MLA 日志压缩 | `0 4 * * *` | local |
| 🟢 | `3e8496c76d23` | steam-watchdog | `every 8m` | local |
| 🟢 | `a2b1d1c30ca1` | NEKO#2881 回应监控 | `0 10 * * *` | origin |
| 🟢 | `bda7241fa9c3` | 授粉流水线-超限战轮 | `0 15 * * *` | origin |
| 🟦 | `37414dec35c7` | 周趋势报告 | `0 8 * * 1` | qqbot |

**附录 B · 7 paused cron 处置建议**（Trae 按师傅拍板填；本工单只要 4 列占位 + 留 1 行 TODO）：

| cron | 名字 | 暂停原因（推测） | 处置建议 |
|---|---|---|---|
| `a3f2e3a24214` | 自动封禁扫描 | iLink 限流后未恢复 | 改 deliver=qqbot 或重 enable 验证 |
| `237c3476ee32` | 蜜罐日志→威胁情报 | 服务下线 | 与 d22b33160359 蜜饵合并 |
| `0d95511915f5` | 自愈+告警扫描 | 与 P0 重复 | 删除（被 d2484a567104 替代） |
| `fc1ceb413faa` | 信息域反制监控 | | 师傅拍板 |
| `737c429dab74` | 静默总报 | 7:05 与 bcb4b8c8c151 撞 | 与脉搏体检合并 |
| `dbe2d4f945c9` | Kali桥心跳检测v2 | | 师傅拍板 |
| `eb67417255c4` | hermes-auto-recover | every 2m 太密 | 改 every 30m 或删 |

## §3 · 验收标准

| 项 | 阈值 |
|---|---|
| 1. runbook 5 节齐全（摘要/判断/四类/state.db/不要删） | 必须 |
| 2. maint 脚本支持 --dry-run + flock + 退出码语义 | 必须 |
| 3. WO-244 节奏表按 24 cron 重出 | 必须 |
| 4. 7 paused cron 处置表占位 | 必须（4 列齐全，第 4 列可 TODO） |
| 5. PR 描述含"清理前 → 清理后" | 必须 |

## §4 · 关联

- WO-246（GitHub MCP 收口）：同一窗口期
- WO-248（SSH 收口）：同一窗口期
- WO-244（节奏表）：本单任务 D 是它的兑现
- 师傅在 orcaterm 跑 `maint-state-db.sh` 是先决条件；本工单**不**触发该执行

## §5 · 验证证据（施工后由 Trae 填）

```
$ ls -lh ~/.hermes/state.db
2.7G
$ bash ~/.hermes/scripts/maint-state-db.sh --dry-run
[2026-10-19 ...] ==== maint start ====
...
$ df -h /
/dev/vda2  59G  36G  21G  63% /
```

## §6 · 编号防撞

- **指令文件**：`TRAE_WORKORDER_PROMPT_AGENT_247.md`（仓库根，input）
- **施工记录**：本文件 `docs/WO-247-*`（output）
