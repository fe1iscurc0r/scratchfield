# PR Description · WO-238/239/240 Pollination + Daily Sweep + arXiv Follow-up (2026-10-15)

## 标题

docs(workorders): WO-238/239/240 — 授粉轮41弹药入仓 + arXiv 限流护栏 + 日报 11 候选评估

## 摘要

按 2026-10-15 师傅 QQ 13:18 指令"把这三个 cron 产出转成工单"，沈遥已落 3 份工单到 `scratchpad/docs/`：

| 工单 | 字节 | 触发 cron | 任务数 | 关键焦点 |
|------|------|-----------|--------|----------|
| **WO-238** 授粉-轮 41 弹药入仓 | 12.7 KB | `bda7241fa9c3` 15:06 跑批 | 4 任务 | 10 可吞 + 11 暂缓 + 3 P0 接入 + RAG 索引 |
| **WO-239** 论文-限流护栏 + 4 跨域授粉跟单 | 11.2 KB | `ad17cd9d341f` 02:15 跑批 | 3 任务 | fetch_arxiv.py 改造 + Ghostline/Object-Bound/UV-cured/SEPM 4 落地 + 5 跟踪 |
| **WO-240** 日报-11 候选 + 4 排除 + 22 haul 索引 | 13.5 KB | `a37ffecbd730` 09:06 跑批 | 3 任务 | 11 候选三档 + 4 排除二级核验 + 22 haul 归档 |

## 决策背景（师傅口径收敛）

- 师傅 13:25 同意"软件层项目没问题可以推"
- 师傅 13:25 明确**暂停**无人机相关（PX4/ROS2/MavSDK/SLAM 栈），因此同期落盘的"超限战轮 42 无人机飞控+KG-RAG"报告**不入本 PR**——待师傅有精力再单独接单
- 之前认作的"WO-241 接轮 42"已撤销

## 工单细节

### WO-238 焦点
1. 6 个授粉落点（`coupled/reactor-digital-twin/` 等）入 `fe1iscurc0r/scratchpad-knowledge` 中转库
2. 11 个暂缓项走"代发 issue 询问"激活策略，**issue 草稿先给师傅过目**
3. 3 个 P0（vicena-labs / DENG-MIT / BRGM）接 `mcpserver/material_science/`

### WO-239 焦点
1. `fetch_arxiv.py` 加 `--skip-cats` / `--only-cats` / `--sleep-min` 三参数（10-16 02:00 跑批前必完工）
2. 4 条授粉点（Ghostline→ESP32+SX1278 / Object-Bound→NEKO harness / UV-cured→木质素 NPs / SEPM→任务图）落地

### WO-240 焦点
1. 11 个新候选三档分桶（P0 接入 / P1 授粉 / P2 暂缓）
2. 4 个 NOASSERTION 排除项做"许可可信度"二级核验（TEN-framework 反向激活路径、neo4j-labs issue 草稿）
3. 22 个 haul 重复项归档索引（**不重推**）

## Trae 接管执行建议

按 WO 优先级顺序接管：

```
W1 (本周)
├─ WO-238 任务 A: 6 落点入仓 + 守卫
├─ WO-239 任务 A: fetch_arxiv.py 限流护栏 (最急)
├─ WO-240 任务 B: 11 候选评估 md 落盘 (不入仓,只评估)
└─ WO-240 任务 C: 22 haul 索引 + 4 排除核验

W2 (下周)
├─ WO-238 任务 C: 3 个 P0 mcpserver 接入
├─ WO-239 任务 B: 4 份授粉落地 md (Ghostline/Object-Bound/UV-cured/SEPM)
├─ WO-240 任务 B P0-1/P0-2: mcp_gateway + vibe_check 接入
└─ WO-239 任务 C: 5 份跟踪 md
```

## 风险与边界

| 风险 | 缓解 |
|------|------|
| WO-238 任务 C 涉 BRGM ComPASS 双许可 | 接入前确认非商业用途 |
| WO-239 改 fetch_arxiv.py 触发跑批回归 | 加 `--only-cats` 单类重跑兜底 |
| WO-240 P1-4/P1-5 是 AGPL/GPL-3.0 | 严格"只读 schema 不并包" |
| WO-240 11 候选评估需 gh api 实测 | 跑 `anti_hallucination_guard.py` 守卫 |
| 10 个 issue 草稿必须师傅过目 | 草稿先落 `/tmp/issue_bodies/`，师傅拍板才发 |

## 验收不变量（合并）

```bash
# 1. 3 份工单文件存在（已在 working tree）
ls docs/WO-238-pollination-r41-ammunition-intake.md \
   docs/WO-239-arxiv-pollination-rate-limit-and-cross-domain-followup.md \
   docs/WO-240-github-sweep-daily-11-new-and-4-excluded.md
# 期望：3 个 OK

# 2. 守卫 FAIL=0（合并后跑）
python3 ~/scratchpad/scripts/anti_hallucination_guard.py \
  --check-report /tmp/wo238-240_final.md --detect-upstream
# 期望输出：FAIL=0

# 3. 不动 NEKO/apiserver 主流程
git diff --stat -- NEKO apiserver | wc -l
# 期望：0
```

## out of scope（本 PR 不动）

- **WO-241 轮 42 无人机飞控栈** —— 师傅暂停，单独立项
- 任何 PX4 / ROS2 / MavSDK / SLAM / SLAM-code 相关代码改动
- 任何 mavros / Fast-LIO / px4-mpc 文件
- 任何 `vendor/fast-lio2-ego-planner/`、`vendor/mavros-controllers/` 新目录
- 任何 `mcpserver/ros2_mcp/`、`mcpserver/falkordb-mcp/` 新 mcpserver
- 任何 `coupled/drone-*` 目录
- 任何 `docs/授粉报告/HiRAG-*` 等参考报告

> 沈遥 · 2026-10-15 · chore/wo238-240-pollination-and-daily-2026-10-15
