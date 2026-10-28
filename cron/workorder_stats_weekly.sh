#!/usr/bin/env bash
# 工单转化率周报 —— 每周一 08:00（工单 238 任务三）
#
# 跑 tools/workorder_conversion_stats.py，把「工单发放 → 主仓合入」的闭环
# 统计落到 <repo>/reports/workorder_conversion_stats_<YYYY-MM-DD>.md|.json。
#
# 本地试跑：
#   bash cron/workorder_stats_weekly.sh
#   SCRATCHPAD_REPO=/home/ubuntu/scratchpad bash cron/workorder_stats_weekly.sh
#   WORKORDER_STATS_PERIOD=all bash cron/workorder_stats_weekly.sh
#
# ── 接入 crontab（⛔ 需沈遥协助）────────────────────────────────────────
# 本机既无 ~/.hermes/cron 也无 crontab（2026-10-14 实测），因此脚本无法自行
# 注册。请在目标机器上 `crontab -e`，**只追加下面这一行，不要覆写现有 25 条**：
#
#   0 8 * * 1 SCRATCHPAD_REPO=/home/ubuntu/scratchpad /bin/bash /home/ubuntu/scratchpad/cron/workorder_stats_weekly.sh >> /var/log/workorder_stats.log 2>&1
#
#   （cron 的 PATH 很窄，建议改成绝对路径的 python3：
#     PYTHON_BIN=/usr/bin/python3 ...）
#
# ── 报告推送到用户微信主通道（⛔ 未落地，需沈遥侧编排）──────────────────
# 工单 238 §2 任务三.3 要求把报告推到用户微信主通道。本脚本只负责「产出报告
# 文件」；通道投递归 ~/.hermes/cron 的既有编排，不在本仓可验证范围内。
#
# 环境变量：
#   SCRATCHPAD_REPO        仓库路径（默认取本脚本所在仓库根）
#   WORKORDER_STATS_PERIOD 统计窗口，30d / 90d / all / YYYY-MM-DD..YYYY-MM-DD（默认 30d）
#   PYTHON_BIN             python 解释器（默认 python3）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${SCRATCHPAD_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PERIOD="${WORKORDER_STATS_PERIOD:-30d}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

TARGET="$REPO/tools/workorder_conversion_stats.py"
if [ ! -f "$TARGET" ]; then
  echo "[workorder-stats] 找不到 $TARGET（SCRATCHPAD_REPO=$REPO）" >&2
  exit 2
fi

echo "[workorder-stats] $(date -u +%Y-%m-%dT%H:%M:%SZ) repo=$REPO period=$PERIOD python=$PYTHON_BIN"
cd "$REPO"
"$PYTHON_BIN" "$TARGET" --repo "$REPO" --period "$PERIOD"
