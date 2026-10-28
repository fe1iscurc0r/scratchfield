#!/usr/bin/env bash
# 日报 → 工单草稿 日更 —— 每天 06:00（工单 240 任务二）
#
# 跑 tools/cron_to_workorder.py，把近 24h 的日报抽成工单草稿，落到
# <repo>/research/workorder_drafts/auto_<YYYY-MM-DD>/。
#
# 比其它 cron 晚（06:00）：上游日报多在 02:00 前后产出，晚跑才能扫到当日文件。
#
# 本地试跑：
#   bash cron/cron_to_workorder_daily.sh
#   SCRATCHPAD_REPO=/home/ubuntu/scratchpad bash cron/cron_to_workorder_daily.sh
#   WORKORDER_PERIOD=7d WORKORDER_MAX_TOTAL=3 bash cron/cron_to_workorder_daily.sh
#   bash cron/cron_to_workorder_daily.sh --list-sources      # 只看源解析与路径偏差
#
# ── 接入 crontab（⛔ 未落地，需沈遥协助）────────────────────────────────
# 本机既无 ~/.hermes/cron 也无 crontab（2026-10-14 实测），脚本无法自行注册。
# 请在目标机器上 `crontab -e`，**只追加下面这一行，不要覆写现有 25 条**：
#
#   0 6 * * * SCRATCHPAD_REPO=/home/ubuntu/scratchpad PYTHON_BIN=/usr/bin/python3 /bin/bash /home/ubuntu/scratchpad/cron/cron_to_workorder_daily.sh >> /var/log/cron_to_workorder.log 2>&1
#
# ── 推送给用户微信（⛔ 未落地，需沈遥侧编排）────────────────────────────
# 本脚本只负责「产出草稿 + manifest」。投递归 ~/.hermes/cron 的既有编排
# （见 docs/POLLINATION-FUNNEL-v2-CHANGELOG.md §5.4），不在本仓可验证范围内。
#
# ── 草稿**不自动转** TRAE_WORKORDER_PROMPT_AGENT_*.md ───────────────────
# 设计稿 §5 明确留人工签字环节：看完草稿后手动
#   python3 tools/cron_to_workorder.py --promote <draft> --next-number <n> --apply
# 本脚本绝不调用 --promote。
#
# 环境变量：
#   SCRATCHPAD_REPO       仓库路径（默认取本脚本所在仓库根）
#   WORKORDER_PERIOD      窗口：24h / 48h / 7d / all（默认 24h）
#   WORKORDER_MAX_PER_FILE 每份日报最多抽几条（默认 3）
#   WORKORDER_MAX_TOTAL   本次最多落盘几份草稿（默认 5）
#   M3_API_KEY / M3_API_BASE / M3_MODEL
#                         有 key 走 litellm 归纳，无 key 自动降级为规则模式
#                         （模式会写进 stdout 与每份草稿头部，不静默）
#   PYTHON_BIN            python 解释器（默认 python3）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${SCRATCHPAD_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PERIOD="${WORKORDER_PERIOD:-24h}"
MAX_PER_FILE="${WORKORDER_MAX_PER_FILE:-3}"
MAX_TOTAL="${WORKORDER_MAX_TOTAL:-5}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

TARGET="$REPO/tools/cron_to_workorder.py"
if [ ! -f "$TARGET" ]; then
  echo "[cron-to-workorder] 找不到 $TARGET（SCRATCHPAD_REPO=$REPO）" >&2
  exit 2
fi

echo "[cron-to-workorder] $(date -u +%Y-%m-%dT%H:%M:%SZ) repo=$REPO period=$PERIOD max=$MAX_TOTAL python=$PYTHON_BIN"
cd "$REPO"

# 透传 --list-sources 等只读子命令（供人工排查路径偏差）
if [ "$#" -gt 0 ]; then
  exec "$PYTHON_BIN" "$TARGET" --repo "$REPO" "$@"
fi

exec "$PYTHON_BIN" "$TARGET" --repo "$REPO" --scan \
  --period "$PERIOD" \
  --max-per-file "$MAX_PER_FILE" \
  --max-total "$MAX_TOTAL" \
  --output "$REPO/research/workorder_drafts/auto_$(date +%F)"
